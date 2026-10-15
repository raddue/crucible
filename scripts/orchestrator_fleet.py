#!/usr/bin/env python3
"""Fleet-file CRUD for the Herdr orchestrator skill (skills/orchestrator/SKILL.md).

The skill's step 2 tells the agent to keep worker state in one JSON file
("rewritten on every spawn, rotation, and close"). That hand-editing is the
mechanical part this script owns: atomic read-modify-write against the real
fleet schema, so a crashed/compacted orchestrator can reconstruct exactly what
its workers were doing.

Path defaults to ~/.claude/crucible/orchestrator/<basename(cwd)>-fleet.json,
matching the skill. Stdlib only; writes go through scripts/atomic_write.py.

Subcommands:
  show/init/register/bind/status/remove/meta — the CRUD core; identities come from Herdr receipts
  queue push / queue next                    — FIFO task backlog in the `backlog` field
  ready                                      — schedule the `depends_on` DAG
  sync                                       — reconcile by exact pane and agent-session identity
  log                                        — append one boss-decision line + mirror `next:` into `pending`

ponytail: no lock — one orchestrator owns one repo's fleet file by construction
(the skill forbids two agents in the same checkout). Add mkdir-lock (see
ledger_append.py) only if two orchestrators ever share a cwd.
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys
import csv as _csv
import io as _io
import subprocess as _sp

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.atomic_write import atomic_write_text  # noqa: E402

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".claude", "crucible", "orchestrator")

# Fields callers may set; pane identity is captured only from Herdr receipts.
WORKER_FIELDS = ("worktree", "branch", "issue", "task", "backend", "listagents_name")
_PANE_KEYS = ("pane_id", "terminal_id", "workspace_id", "tab_id")

# _save() only ever stamps this shape (see _now). A fleet file whose `updated_at`
# does not match was written out-of-band — the root cause of the drift `sync`
# reconciles. Flag it on every load so the orchestrator stops trusting a file
# the script didn't write.
_UPDATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_IN_FLIGHT = ("dispatched", "working")


def _now():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_path():
    return os.path.join(DEFAULT_DIR, f"{os.path.basename(os.getcwd())}-fleet.json")


def _blog_path(fleet_path):
    if fleet_path.endswith("-fleet.json"):
        return fleet_path[:-len("-fleet.json")] + "-boss.log"
    return os.path.splitext(fleet_path)[0] + "-boss.log"


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not _UPDATED_AT_RE.match(doc.get("updated_at", "")):
        print(
            f"warning: {path} has updated_at={doc.get('updated_at')!r}, not the "
            f"script's stamp ({_now()} shape). Written out-of-band; treat as "
            f"stale. Run 'sync' before trusting it.",
            file=sys.stderr,
        )
    return doc


def _save(path, doc):
    doc["updated_at"] = _now()
    atomic_write_text(path, json.dumps(doc, indent=2) + "\n")


def _skeleton():
    return {
        "orchestrator": {"me": "", "name": "orchestrator", "workspace": "", "backend": ""},
        "arc": "",
        "build_backend": "",
        "review_backend": "",
        "updated_at": _now(),
        "workers": [],
        "backlog": [],
        "pending": "",
    }


def _find_worker(doc, name):
    return next((w for w in doc.get("workers", []) if w.get("name") == name), None)


def cmd_show(path, raw):
    doc = _load(path)
    if doc is None:
        print("no fleet file", file=sys.stderr)
        return 1
    if raw:
        print(json.dumps(doc))
    else:
        print(json.dumps(doc, indent=2))
    return 0


def cmd_init(path):
    if os.path.exists(path):
        print(f"already exists: {path}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _save(path, _skeleton())
    print(path)
    return 0


def _read_receipt(path):
    try:
        with open(path, encoding="utf-8") as f:
            envelope = json.load(f)
    except (OSError, ValueError) as e:
        print(f"could not read Herdr receipt {path}: {e}", file=sys.stderr)
        return None, None
    result = envelope.get("result")
    if not isinstance(result, dict):
        print("Herdr receipt has no result object", file=sys.stderr)
        return None, None
    return envelope, result

def live_pane(pane_id):
    """Return one live `herdr pane get` record, or None on any failure."""
    try:
        out = _sp.run(["herdr", "pane", "get", pane_id], capture_output=True, text=True, timeout=10)
        if out.returncode:
            return None
        result = json.loads(out.stdout).get("result", {})
        return result.get("pane")
    except (OSError, _sp.SubprocessError, ValueError):
        return None

def _pane_identity(pane, source):
    if (not isinstance(pane, dict) or any(not pane.get(k) for k in _PANE_KEYS) or
            not isinstance(pane.get("revision"), int)):
        return None
    return {**{k: pane[k] for k in _PANE_KEYS}, "created_revision": pane["revision"],
            "creation_source": source}

def _receipt_pane(envelope, result):
    command = envelope.get("id", "")
    kind = result.get("type")
    if command.endswith(":worktree:create") and kind == "worktree_created":
        pane = result.get("root_pane")
    elif command.endswith(":worktree:open") and kind == "worktree_opened":
        if result.get("already_open"):
            print("refusing already-open worktree receipt: pane predates this worker", file=sys.stderr)
            return None
        pane = result.get("root_pane")
    elif command.endswith(":pane:split") and kind == "pane_info":
        pane = result.get("pane")
    elif command.endswith(":pane:move") and kind == "pane_move" and result.get("changed"):
        pane = (result.get("move_result") or result).get("pane")
    else:
        print(f"not a supported Herdr creation/move receipt: command={command!r} type={kind!r}", file=sys.stderr)
        return None
    return _pane_identity(pane, command)

def _set_metadata(w, fields, depends_on):
    for k, v in fields.items():
        if v is not None:
            w[k] = v
    if depends_on:
        deps = w.setdefault("depends_on", [])
        for d in depends_on:
            if d not in deps:
                deps.append(d)

def cmd_register(path, name, receipt_path, status, fields, depends_on=None):
    if not name:
        print("worker name required", file=sys.stderr)
        return 1
    envelope, result = _read_receipt(receipt_path)
    if envelope is None:
        return 1
    identity = _receipt_pane(envelope, result)
    if identity is None:
        print("pane identity missing from creation receipt", file=sys.stderr)
        return 1
    current = live_pane(identity["pane_id"])
    if not current or any(current.get(k) != identity[k] for k in _PANE_KEYS):
        print("live pane no longer matches its creation receipt; refusing registration", file=sys.stderr)
        return 1
    doc = _load(path) or _skeleton()
    w = _find_worker(doc, name)
    if any(item.get("pane_id") == identity["pane_id"] for item in doc.get("workers", []) if item is not w):
        print("pane is already assigned to another worker", file=sys.stderr)
        return 1
    prior = w.get("pane_identity") if w else None
    if prior and prior != identity and w.get("status") not in ("done", "blocked"):
        print("refusing to replace a pane while its worker is not done or blocked", file=sys.stderr)
        return 1
    if prior and identity.get("creation_source", "").endswith(":pane:move"):
        if identity.get("terminal_id") != prior.get("terminal_id"):
            print("pane move receipt does not preserve the recorded terminal identity", file=sys.stderr)
            return 1
    session = prior.get("agent_session") if prior else None
    if session and current.get("agent_session") == session:
        identity.update(agent_name=prior.get("agent_name"), agent_session=session)
    if w is None:
        w = {"name": name}
        doc.setdefault("workers", []).append(w)
    elif prior != identity and prior:
        w.setdefault("pane_history", []).append({
            **prior, "status": w.get("status"), "cleanup": "pending",
            "successor_pane_id": identity["pane_id"],
        })
    w["pane_id"] = identity["pane_id"]
    w["tab_id"] = identity["tab_id"]
    w["pane_identity"] = identity
    if identity.get("agent_session"):
        w["agent_session"] = identity["agent_session"]
    else:
        w.pop("agent_session", None)
    if status:
        w["status"] = status
    _set_metadata(w, fields, depends_on)
    _save(path, doc)
    print(json.dumps(w))
    return 0

def cmd_bind(path, name, receipt_path):
    doc = _load(path)
    w = _find_worker(doc or {}, name)
    if w is None or not w.get("pane_identity"):
        print(f"no registered pane for worker {name!r}", file=sys.stderr)
        return 1
    envelope, result = _read_receipt(receipt_path)
    agent = result.get("agent") if result else None
    if (envelope is None or envelope.get("id") != "cli:agent:start" or
            result.get("type") != "agent_started" or not isinstance(agent, dict)):
        print("expected Herdr agent.start receipt", file=sys.stderr)
        return 1
    identity = w["pane_identity"]
    session = agent.get("agent_session")
    if (agent.get("name") != name or agent.get("pane_id") != identity["pane_id"] or
            not isinstance(session, dict) or not session.get("value")):
        print("agent.start receipt does not identify this worker and pane", file=sys.stderr)
        return 1
    pane = live_pane(identity["pane_id"])
    if (not pane or any(pane.get(k) != identity.get(k) for k in _PANE_KEYS) or
            pane.get("agent_session") != session):
        print("pane changed before agent identity could be bound; refusing", file=sys.stderr)
        return 1
    agents = live_agents()
    live = next((a for a in (agents or []) if a.get("name") == name and a.get("pane_id") == identity["pane_id"]), None)
    if (not live or not identity_matches({**identity, "agent_name": name,
                                          "agent_session": session}, live) or
            live.get("agent_session") != session):
        print("live agent list does not match the agent.start receipt", file=sys.stderr)
        return 1
    identity["agent_name"] = name
    identity["agent_session"] = session
    w["pane_identity"] = identity
    w["agent_session"] = session
    _save(path, doc)
    print(json.dumps(w))
    return 0


def cmd_set_status(path, name, status):
    if not name or not status:
        print("worker name and --status required", file=sys.stderr)
        return 1
    doc = _load(path)
    if doc is None:
        print("no fleet file — run init or upsert first", file=sys.stderr)
        return 1
    w = _find_worker(doc, name)
    if w is None:
        print(f"no worker named {name!r}", file=sys.stderr)
        return 1
    w["status"] = status
    _save(path, doc)
    print(json.dumps(w))
    return 0


def cmd_remove(path, name):
    if not name:
        print("worker name required", file=sys.stderr)
        return 1
    doc = _load(path)
    w = _find_worker(doc or {}, name)
    if w is None:
        print(f"no worker named {name!r}", file=sys.stderr)
        return 1
    if w.get("status") != "done":
        print("refusing to archive a worker that is not done", file=sys.stderr)
        return 1
    doc["workers"].remove(w)
    w["archived_at"] = _now()
    doc.setdefault("archived_workers", []).append(w)
    _save(path, doc)
    print(f"archived {name}; pane identity retained in fleet history (no pane was closed)")
    return 0


def cmd_meta(path, key, value):
    if not key or value is None:
        print("key and value required", file=sys.stderr)
        return 1
    doc = _load(path) or _skeleton()
    if key.startswith("orchestrator."):
        inner = key.split(".", 1)[1]
        doc.setdefault("orchestrator", {})[inner] = value
    else:
        doc[key] = value
    _save(path, doc)
    print(json.dumps(doc))
    return 0


def cmd_queue_push(path, issue, task, branch, worktree, backend):
    doc = _load(path) or _skeleton()
    item = {}
    if issue is not None:
        item["issue"] = issue
    if task:
        item["task"] = task
    if branch:
        item["branch"] = branch
    if worktree:
        item["worktree"] = worktree
    if backend:
        item["backend"] = backend
    if not item:
        print("queue push needs at least one field (--issue/--task/--branch/--worktree/--backend)", file=sys.stderr)
        return 1
    doc.setdefault("backlog", []).append(item)
    _save(path, doc)
    print(json.dumps(item))
    return 0


def cmd_queue_next(path, name, receipt_path, backend):
    doc = _load(path)
    if doc is None or not doc.get("backlog"):
        print("backlog empty — nothing to dispatch", file=sys.stderr)
        return 1
    if _find_worker(doc, name) is not None:
        print(f"worker {name!r} already exists", file=sys.stderr)
        return 1
    envelope, result = _read_receipt(receipt_path)
    identity = _receipt_pane(envelope, result) if envelope else None
    if identity is None:
        return 1
    item = doc["backlog"][0]
    fields = {k: item.get(k) for k in WORKER_FIELDS}
    if backend:
        fields["backend"] = backend
    if cmd_register(path, name, receipt_path, "dispatched", fields) != 0:
        return 1
    doc = _load(path)
    doc["backlog"].pop(0)
    _save(path, doc)
    print(json.dumps(_find_worker(doc, name)))
    return 0


def cmd_ready(path):
    doc = _load(path)
    if doc is None:
        print("no fleet file", file=sys.stderr)
        return 1
    ready, blocked = [], []
    for w in doc.get("workers", []):
        if w.get("status") != "idle":
            continue
        holds = []
        for d in (w.get("depends_on") or []):
            dep = _find_worker(doc, d)
            if dep is None or dep.get("status") != "done":
                holds.append(f"{d} = {dep.get('status') if dep else 'missing'}")
        if holds:
            blocked.append(f"{w['name']} (dep {', '.join(holds)})")
        else:
            ready.append(w["name"])
    print("ready: " + (", ".join(ready) if ready else "(none)"))
    print("blocked: " + (", ".join(blocked) if blocked else "(none)"))
    return 0


def parse_agent_list(text):
    """Parse `herdr agent list` stdout.

    Two shapes seen in the wild: `result.agents` is either a list of dicts
    (structured) or a string of header+CSV rows (line mode). Accept both.
    """
    agents = text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
            agents = parsed["result"].get("agents", parsed["result"])
    except Exception:
        pass
    if isinstance(agents, str):
        return list(_csv.DictReader(_io.StringIO(agents)))
    if isinstance(agents, list):
        return agents
    return []


def live_agents():
    """Run `herdr agent list`; return agent rows, or None on failure."""
    try:
        out = _sp.run(["herdr", "agent", "list"], capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f"herdr agent list failed: {e}", file=sys.stderr)
        return None
    if out.returncode != 0:
        print(f"herdr agent list rc={out.returncode}: {out.stderr.strip()}", file=sys.stderr)
        return None
    return parse_agent_list(out.stdout)


def _realpath(p):
    return os.path.realpath(p) if p else None


def identity_matches(identity, agent, pane=None, require_agent=True):
    """Match a live agent to its recorded pane incarnation and session."""
    if not isinstance(identity, dict) or any(not identity.get(k) for k in _PANE_KEYS):
        return False
    pane = pane if pane is not None else live_pane(identity["pane_id"])
    if not pane or any(pane.get(k) != identity[k] for k in _PANE_KEYS):
        return False
    if not agent or agent.get("pane_id") != identity["pane_id"]:
        return False
    session = identity.get("agent_session")
    if require_agent and (not session or not identity.get("agent_name")):
        return False
    if session and (agent.get("name") != identity["agent_name"] or agent.get("agent_session") != session):
        return False
    return pane.get("agent_session") == session

def reconcile(doc, agents, get_pane=None):
    """Match only exact recorded pane incarnations and bound agent sessions."""
    get_pane = get_pane or live_pane
    matched, stale = [], []
    for w in doc.get("workers", []):
        identity = w.get("pane_identity")
        agent = next((a for a in agents if identity and
                      a.get("name") == identity.get("agent_name") and
                      a.get("pane_id") == identity.get("pane_id") and
                      a.get("agent_session") == identity.get("agent_session")), None)
        pane = get_pane(identity["pane_id"]) if identity and identity.get("pane_id") else None
        if agent is not None and identity_matches(identity, agent, pane):
            matched.append((w["name"], agent.get("pane_id"), agent.get("agent_status"), agent.get("cwd")))
        else:
            stale.append({**w, "_identity_error": "no matching recorded pane/agent identity"})
    return matched, stale


def cmd_sync(path):
    doc = _load(path)
    if doc is None:
        print("no fleet file", file=sys.stderr)
        return 1
    agents = live_agents()
    if agents is None:
        print("sync: could not read live agents from herdr agent list", file=sys.stderr)
        return 2
    matched, stale = reconcile(doc, agents)
    for name, pane_id, agent_status, cwd in matched:
        print(f"MATCHED {name} pane={pane_id} status={agent_status} cwd={cwd}")
    for w in stale:
        print(f"STALE {w.get('name')} ({w.get('_identity_error')}; pane={w.get('pane_id')})")
    if stale:
        print(f"{len(stale)} worker(s) lack a matching recorded pane identity; fail closed", file=sys.stderr)
        return 1
    return 0


def cmd_log(path, event, nxt, pane):
    if not event:
        print("--event required", file=sys.stderr)
        return 1
    blog = _blog_path(path)
    line = f"{_now()}\t{pane or ''}\t{event}"
    if nxt:
        line += f"\tnext: {nxt}"
    os.makedirs(os.path.dirname(blog), exist_ok=True)
    with open(blog, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if nxt:
        doc = _load(path) or _skeleton()
        doc["pending"] = nxt
        _save(path, doc)
    print(line)
    return 0


def _add_field_flags(p):
    for f in WORKER_FIELDS:
        p.add_argument(f"--{f.replace('_', '-')}", dest=f, default=None)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Herdr orchestrator fleet-file CRUD")
    sub = ap.add_subparsers(dest="cmd", required=True)

    show_p = sub.add_parser("show", help="print the fleet file")
    show_p.add_argument("-p", "--path", default=None)
    show_p.add_argument("--raw", action="store_true")

    init_p = sub.add_parser("init", help="create an empty fleet file")
    init_p.add_argument("-p", "--path", default=None)

    reg = sub.add_parser("register", help="record pane identity from a Herdr creation/move receipt")
    reg.add_argument("-p", "--path", default=None)
    reg.add_argument("name")
    reg.add_argument("--receipt-file", required=True)
    reg.add_argument("--status", default=None)
    reg.add_argument("--depends-on", dest="depends_on", action="append", default=None)
    _add_field_flags(reg)

    bind = sub.add_parser("bind", help="bind agent.start receipt to the registered pane")
    bind.add_argument("-p", "--path", default=None)
    bind.add_argument("name")
    bind.add_argument("--receipt-file", required=True)

    st = sub.add_parser("status", help="set one worker's status")
    st.add_argument("-p", "--path", default=None)
    st.add_argument("name")
    st.add_argument("--status", required=True)

    rm = sub.add_parser("remove", help="archive a completed worker; does not close its pane")
    rm.add_argument("-p", "--path", default=None)
    rm.add_argument("name")
    rm.add_argument("--status", default=None)

    mt = sub.add_parser("meta", help="set a top-level field (or orchestrator.<field>)")
    mt.add_argument("-p", "--path", default=None)
    mt.add_argument("key")
    mt.add_argument("value")

    rd = sub.add_parser("ready", help="print which workers' deps are satisfied")
    rd.add_argument("-p", "--path", default=None)

    sy = sub.add_parser("sync", help="reconcile fleet workers against live herdr")
    sy.add_argument("-p", "--path", default=None)

    lg = sub.add_parser("log", help="append a boss-decision line + mirror next: into pending")
    lg.add_argument("-p", "--path", default=None)
    lg.add_argument("--event", required=True)
    lg.add_argument("--next", dest="nxt", default=None)
    lg.add_argument("--pane", default=None)

    q = sub.add_parser("queue", help="task backlog (FIFO)")
    qsub = q.add_subparsers(dest="queue_cmd", required=True)
    qpush = qsub.add_parser("push", help="append one task to the backlog")
    qpush.add_argument("-p", "--path", default=None)
    qpush.add_argument("--issue", type=int, default=None)
    qpush.add_argument("--task", default="")
    qpush.add_argument("--branch", default=None)
    qpush.add_argument("--worktree", default=None)
    qpush.add_argument("--backend", default=None)
    qnext = qsub.add_parser("next", help="atomically pop the first task into a new worker")
    qnext.add_argument("-p", "--path", default=None)
    qnext.add_argument("name")
    qnext.add_argument("--receipt-file", required=True)
    qnext.add_argument("--backend", default=None)

    args = ap.parse_args(argv)
    path = args.path or _default_path()

    if args.cmd == "show":
        return cmd_show(path, args.raw)
    if args.cmd == "init":
        return cmd_init(path)
    if args.cmd == "register":
        fields = {f: getattr(args, f, None) for f in WORKER_FIELDS}
        return cmd_register(path, args.name, args.receipt_file, args.status, fields, args.depends_on)
    if args.cmd == "bind":
        return cmd_bind(path, args.name, args.receipt_file)
    if args.cmd == "status":
        return cmd_set_status(path, args.name, args.status)
    if args.cmd == "remove":
        return cmd_remove(path, args.name)
    if args.cmd == "meta":
        return cmd_meta(path, args.key, args.value)
    if args.cmd == "ready":
        return cmd_ready(path)
    if args.cmd == "sync":
        return cmd_sync(path)
    if args.cmd == "log":
        return cmd_log(path, args.event, args.nxt, args.pane)
    if args.cmd == "queue":
        if args.queue_cmd == "push":
            return cmd_queue_push(path, args.issue, args.task, args.branch, args.worktree, args.backend)
        if args.queue_cmd == "next":
            return cmd_queue_next(path, args.name, args.receipt_file, args.backend)
    return 2


if __name__ == "__main__":
    sys.exit(main())