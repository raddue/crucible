#!/usr/bin/env python3
"""Runtime receipt linter (Ledger Return Protocol). Tier-1 (v1 structural, a verbatim
port of the former eval-only eval/ledger-return-protocol/lint.py, removed in #369) +
Tier-2 parts 1-2 (disk sha256 + witness byte-range). stdlib-only, argparse-free.
Exit 0=pass, 1=fail; bullets on stderr.

Usage:
  rcpt_verify.py [--tier1|--tier2] [--root DIR] [--strict] [FILE|-]
  rcpt_verify.py --selftest
  rcpt_verify.py --eval FILE.jsonl
"""
from __future__ import annotations
import json, re, sys, hashlib, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "eval/ledger-return-protocol"


class LintError(Exception):
    pass


# ── Tier-1 (v1 structural) — ported VERBATIM from the former eval-only lint.py
#    (SECTIONS..lint_receipt, the eval-validated v1 layer; lint.py removed in #369).
#    Do NOT re-derive: the differential oracle gate proved byte-equivalence before
#    lint.py was deleted (the permanent CI guard is --selftest).
SECTIONS = ["RCPT", "VERDICT", "ARTIFACTS", "TRACE", "CLAIMS", "WITNESS", "SUSPICION", "NEXT"]
UNRUNNABLE_VOCAB = {
    "sandbox-restricted", "tooling-absent", "platform-incompatible",
    "network-unreachable", "service-unavailable", "time-budget-exceeded",
    "requires-human-input",
}
LINT_RULES = {"all-claims-cited", "trace-consistent", "skip-declared"}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONF = re.compile(r"^(0\.\d{2}|1\.00)$")


def parse_receipt(text):
    """Parse receipt into {section: body_lines} dict. Body lines preserve
    their original content (including leading whitespace)."""
    lines = text.splitlines()
    if not lines:
        raise LintError("empty receipt")
    # First line must be RCPT v1 or v1.1
    header_m = re.match(r"^RCPT v(1(?:\.1)?) (.+)$", lines[0])
    if not header_m:
        raise LintError("first line must start with 'RCPT v1 ' or 'RCPT v1.1 '")
    sections = {"RCPT": [header_m.group(2)]}
    current = None
    for line in lines[1:]:
        stripped = line.lstrip()
        matched = None
        for name in SECTIONS[1:]:
            if line.startswith(name):
                matched = name
                break
        if matched:
            if matched in sections:
                raise LintError(f"section {matched} duplicated")
            rest = line[len(matched):].lstrip()
            sections[matched] = [rest] if rest else []
            current = matched
        else:
            if current is None:
                raise LintError(f"prose before first section header: {line!r}")
            sections[current].append(line)
    # Check order (unknown sections after NEXT ignored — but SECTIONS list is the strict v1 set)
    got_order = [s for s in SECTIONS if s in sections]
    if got_order != SECTIONS[:len(got_order)]:
        raise LintError(f"sections out of order: got {got_order}")
    missing = [s for s in SECTIONS if s not in sections]
    if missing:
        raise LintError(f"missing required sections: {missing}")
    return sections


def parse_artifacts(body):
    """Returns {name: {hash, size, meta}} from ARTIFACTS body lines."""
    out = {}
    # body is indented lines; skip blanks and "(none)"
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line == "(none)":
            return {}
        parts = line.split()
        if len(parts) < 3:
            raise LintError(f"ARTIFACTS malformed: {raw!r}")
        name, hash_field, size = parts[0], parts[1], parts[2]
        if not hash_field.startswith("sha256:") or not HEX64.match(hash_field[len("sha256:"):]):
            raise LintError(f"ARTIFACTS bad hash: {raw!r}")
        out[name] = {"hash": hash_field[len("sha256:"):], "size": size}
    return out


def parse_trace(body):
    """Returns list of {n, verb, args_str} entries."""
    out = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            raise LintError(f"TRACE malformed: {raw!r}")
        n_str, verb = parts[0], parts[1]
        args = parts[2] if len(parts) == 3 else ""
        if not n_str.isdigit():
            raise LintError(f"TRACE index not integer: {raw!r}")
        if verb not in {"READ", "EDIT", "WROTE", "EXEC", "DISPATCHED", "CONSULTED", "SKIPPED"}:
            raise LintError(f"TRACE unknown verb: {verb!r}")
        out.append({"n": int(n_str), "verb": verb, "args": args})
    for i, entry in enumerate(out, start=1):
        if entry["n"] != i:
            raise LintError(f"TRACE indices not 1-based contiguous: expected {i} got {entry['n']}")
    return out


def check_exec_range_bound(args_str):
    """out=<artifact>#<range> — check range ≤ 4 KiB."""
    m = re.search(r"out=\S+#([LB])(\d+)-\1(\d+)", args_str)
    if not m:
        raise LintError(f"EXEC missing out= or bad range: {args_str}")
    kind, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    if b < a:
        raise LintError(f"EXEC range negative: {args_str}")
    span_bytes = (b - a) if kind == "B" else (b - a) * 80  # 80 bytes/line conservative estimate
    if span_bytes > 4096:
        raise LintError(f"EXEC range exceeds 4 KiB: {args_str}")


def parse_claims(body):
    out = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        # pattern= may be quoted (containing spaces) or a /regex/ form or bare
        m = re.match(
            r'^([^\s=]+)=(\S+)\s+from=(\S+)(?:\s+pattern=("[^"]*"|/[^/]*/|\S+))?$',
            line,
        )
        if not m:
            raise LintError(f"CLAIM malformed: {raw!r}")
        out.append({"key": m.group(1), "value": m.group(2), "citation": m.group(3), "pattern": m.group(4)})
    return out


def parse_witness(body):
    if not body:
        raise LintError("WITNESS missing")
    line = body[0].strip()
    if line == "(n/a)":
        raise LintError("WITNESS is '(n/a)' — not permitted under any verdict")
    # form: <kind>:<payload>  expect-fail=<sig>  ran=<disp>
    # expect-fail sig may be /regex/ or "literal" which can contain spaces.
    # Anchor on `  ran=` (last occurrence) and split backwards.
    if "  ran=" not in line and " ran=" not in line:
        raise LintError(f"WITNESS missing ran= clause: {line!r}")
    head, _, ran = line.rpartition("ran=")
    head = head.rstrip()
    if not head.endswith(" "):
        # ran= must be preceded by whitespace
        pass
    # head now ends before " ran=". Find " expect-fail=" (first occurrence after payload).
    if "expect-fail=" not in head:
        raise LintError(f"WITNESS missing expect-fail= clause: {line!r}")
    kind_payload, _, expect_fail = head.rpartition("expect-fail=")
    kind_payload = kind_payload.rstrip()
    expect_fail = expect_fail.strip()
    if ":" not in kind_payload:
        raise LintError(f"WITNESS kind:payload malformed: {line!r}")
    kind, _, payload = kind_payload.partition(":")
    kind = kind.strip()
    payload = payload.strip()
    ran = ran.strip()
    if kind not in {"exec", "grep", "lint"}:
        raise LintError(f"WITNESS kind unknown: {kind!r}")
    if kind == "lint" and payload not in LINT_RULES:
        raise LintError(f"WITNESS lint rule unknown: {payload!r}")
    # expect-fail validation
    if not expect_fail:
        raise LintError("WITNESS expect-fail empty")
    if expect_fail.startswith("/") and expect_fail.endswith("/"):
        pattern = expect_fail[1:-1]
        if len(pattern) < 4 or pattern in {".*", ".+"}:
            raise LintError(f"WITNESS expect-fail wildcard/too-short: {expect_fail!r}")
    elif expect_fail.startswith('"') and expect_fail.endswith('"'):
        if len(expect_fail[1:-1]) < 4:
            raise LintError(f"WITNESS expect-fail literal too short: {expect_fail!r}")
    elif not re.match(r"^(exit!=0|exit=-?\d+|match)$", expect_fail):
        raise LintError(f"WITNESS expect-fail not a valid signature form: {expect_fail!r}")
    return {"kind": kind, "payload": payload.strip(), "expect_fail": expect_fail, "ran": ran.strip()}


def lint_receipt(text):
    sections = parse_receipt(text)
    # VERDICT
    verdict_body = sections["VERDICT"]
    if not verdict_body:
        raise LintError("VERDICT empty")
    vm = re.match(r"^(PASS|FAIL|BLOCKED)\s+conf=(\S+)\s*$", verdict_body[0])
    if not vm:
        raise LintError(f"VERDICT malformed: {verdict_body[0]!r}")
    verdict = vm.group(1)
    if not CONF.match(vm.group(2)):
        raise LintError(f"VERDICT conf malformed: {vm.group(2)!r}")
    artifacts = parse_artifacts(sections["ARTIFACTS"])
    trace = parse_trace(sections["TRACE"])
    claims = parse_claims(sections["CLAIMS"])
    witness = parse_witness(sections["WITNESS"])
    # EXEC out= artifact must exist; range bound
    for entry in trace:
        if entry["verb"] == "EXEC":
            check_exec_range_bound(entry["args"])
            m = re.search(r"out=(\S+?)#", entry["args"])
            if m and m.group(1) not in artifacts:
                raise LintError(f"EXEC out= artifact not in ARTIFACTS: {m.group(1)}")
        elif entry["verb"] in {"EDIT", "WROTE"}:
            m = re.search(r"sha256:([0-9a-f]{64})", entry["args"])
            if not m:
                raise LintError(f"{entry['verb']} missing sha256: {entry['args']}")
            if m.group(1) not in {a["hash"] for a in artifacts.values()}:
                # artifact may be an on-disk path not re-declared; for lint purposes accept
                # only if the entry's path itself is in ARTIFACTS as key
                path_m = re.match(r"^(\S+)", entry["args"])
                if path_m and path_m.group(1) not in artifacts:
                    # Allow it — file may not be re-emitted as an ARTIFACT; a tightening
                    # is left as future work. For pilot, we don't hard-fail here.
                    pass
        elif entry["verb"] == "DISPATCHED":
            if not re.search(r"rcpt-sha256:[0-9a-f]{64}", entry["args"]):
                raise LintError(f"DISPATCHED missing rcpt-sha256: {entry['args']}")
    # CLAIM citations must resolve
    for c in claims:
        cit = c["citation"]
        if cit.startswith("TRACE#"):
            idx = int(cit[len("TRACE#"):])
            if not 1 <= idx <= len(trace):
                raise LintError(f"CLAIM citation TRACE#{idx} does not resolve")
        else:
            art_name = cit.split("#", 1)[0]
            # Receipt-hash prefix citations (used by SUPERSEDES justification)
            # are valid without appearing in ARTIFACTS. Layer 2 verifies the
            # hash resolves in the manifest.
            if re.match(r"^[0-9a-f]{12}$", art_name):
                continue
            if art_name not in artifacts:
                raise LintError(f"CLAIM citation artifact not listed: {art_name}")
    # WITNESS ran resolution + rules
    ran = witness["ran"]
    if verdict == "PASS":
        if ran.startswith("UNRUNNABLE"):
            raise LintError("WITNESS ran=UNRUNNABLE not permitted on PASS")
    if ran.startswith("TRACE#"):
        idx = int(ran[len("TRACE#"):])
        if not 1 <= idx <= len(trace):
            raise LintError(f"WITNESS ran=TRACE#{idx} does not resolve")
        verb = trace[idx - 1]["verb"]
        if witness["kind"] == "exec" and verb != "EXEC":
            raise LintError(f"WITNESS kind=exec requires ran= to point to EXEC (got {verb})")
        if witness["kind"] == "grep" and verb not in {"EXEC", "READ", "WROTE"}:
            raise LintError(f"WITNESS kind=grep requires ran= to point to EXEC/READ/WROTE (got {verb})")
    elif ran.startswith("SKIPPED:"):
        next_body = " ".join(sections["NEXT"])
        if witness["payload"] not in next_body:
            raise LintError(
                f"WITNESS ran=SKIPPED requires NEXT to contain witness payload verbatim; "
                f"payload={witness['payload']!r}  NEXT={next_body!r}"
            )
    elif ran.startswith("UNRUNNABLE:"):
        reason = ran[len("UNRUNNABLE:"):]
        if reason not in UNRUNNABLE_VOCAB:
            raise LintError(f"UNRUNNABLE reason not in closed vocabulary: {reason!r}")
    else:
        raise LintError(f"WITNESS ran= form unknown: {ran!r}")
    # mandatory-work: tests run OR tests-related CLAIM must be backed by EXEC/SKIPPED
    claim_keys = {c["key"] for c in claims}
    if {"tests-ran", "tests-pass"} & claim_keys:
        has_exec = any(e["verb"] == "EXEC" for e in trace)
        has_skipped = any(e["verb"] == "SKIPPED" and "tests" in e["args"].lower() for e in trace)
        if not (has_exec or has_skipped):
            raise LintError("tests-ran/tests-pass claim but no EXEC and no SKIPPED tests entry")
        # Check claim points at an EXEC and success-claim is consistent with exit code
        if not has_skipped:
            for c in claims:
                if c["key"] in {"tests-ran", "tests-pass"} and c["citation"].startswith("TRACE#"):
                    idx = int(c["citation"][len("TRACE#"):])
                    cited = trace[idx - 1]
                    if cited["verb"] != "EXEC":
                        raise LintError(f"CLAIM {c['key']} cites TRACE#{idx} which is {cited['verb']}, not EXEC")
                    # Consistency: tests-pass=true must not cite a non-zero-exit EXEC
                    if c["key"] == "tests-pass" and c["value"] == "true":
                        em = re.search(r"exit=(-?\d+)", cited["args"])
                        if em and int(em.group(1)) != 0:
                            raise LintError(
                                f"CLAIM tests-pass=true cites TRACE#{idx} with exit={em.group(1)} "
                                f"(structural contradiction)"
                            )
    return verdict


# ── Tier-2 shared base resolution ───────────────────────────────────────────
def resolve_base(name: str, root: pathlib.Path):
    """Probe {root, repo-root-of-root, absolute-as-is} in fixed order; return the
    FIRST base where the file exists, else None. repo-root = git toplevel of `root`
    (NOT this script's checkout). Used by part-1 hash, part-2 witness read, and --strict."""
    cands = []
    p = pathlib.Path(name)
    if p.is_absolute():
        cands.append(p)
    else:
        cands.append(root / name)
        repo = _git_toplevel(root)
        if repo:
            cands.append(repo / name)
    for c in cands:
        if c.is_file():
            return c
    return None


def _git_toplevel(start: pathlib.Path):
    d = start if start.is_dir() else start.parent
    for cur in [d, *d.parents]:
        if (cur / ".git").exists():   # .exists() is DELIBERATE — handles the git-worktree
            return cur                # `.git`-*file* gitlink (not a dir); do NOT "tighten"
    return None   # stdlib-only: walk for .git rather than shelling out to git


def is_path_shaped(name: str) -> bool:
    """True if name carries a path separator or is absolute (a 'concrete path');
    False for a bare basename. The --strict FAIL-vs-UNVERIFIABLE discriminator.
    Intentionally POSIX-`/`-only (committed-corpus shape space)."""
    return ("/" in name) or pathlib.Path(name).is_absolute()


def tier2_artifacts(artifacts, trace, root, strict):
    """Part 1. For each ARTIFACTS <name>: resolve_base; if found, recompute sha256
    and compare (mismatch -> FAIL). If absent: path-shaped + strict -> FAIL;
    else UNVERIFIABLE (non-fatal). Returns list of UNVERIFIABLE notes; raises LintError on FAIL."""
    notes = []
    for name, meta in artifacts.items():
        resolved = resolve_base(name, root)
        if resolved is not None:
            actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if actual != meta["hash"]:
                raise LintError(f"Tier-2: ARTIFACTS {name} sha256 mismatch (disk={actual[:12]} receipt={meta['hash'][:12]})")
            # <size> is parsed-but-not-validated, matching lint.py
        else:
            if strict and is_path_shaped(name):
                raise LintError(f"Tier-2 --strict: path-shaped artifact {name} absent under all bases")
            notes.append(f"UNVERIFIABLE: {name} (no file under root)")
    return notes


def derive_art_name(cited, verdict):
    """Derive the body-lookup artifact name from the cited TRACE entry, EXACTLY as
    lint.py's tier2_verify (PASS: EXEC out= OR READ/WROTE cited path) and
    tier2_verify_fail (FAIL: EXEC out= only) do. Returns None when no body lookup
    applies (→ clean). Shared by verify_witness (message/control) and the --eval
    caller (body fetch) so the two Tier-2 paths cannot diverge on art_name."""
    m = re.search(r"out=(\S+?)#([LB]\d+-[LB]\d+)", cited["args"]) if cited["verb"] == "EXEC" else None
    if verdict == "FAIL":
        # tier2_verify_fail — EXEC-only (lint.py:370-373)
        if not m:
            return None
        return m.group(1)
    # verdict == PASS — tier2_verify (lint.py:315-326)
    if not m and cited["verb"] in {"READ", "WROTE"}:
        path_m = re.match(r"^(\S+)", cited["args"])
        return path_m.group(1) if path_m else None
    if m:
        return m.group(1)
    return None


def verify_witness(body_text, witness, verdict, cited) -> bool:
    """Pure expect-fail decision core — the ONE shared, deliberately-non-verbatim
    factor of lint.py's tier2_verify (verdict=PASS) and tier2_verify_fail (verdict=FAIL).
    Returns True if the witness is clean; RAISES LintError with the BYTE-IDENTICAL
    message string of the source function on the branch that would FAIL (message
    fidelity is load-bearing for the --eval byte-diff). `cited` = the WHOLE parsed
    cited TRACE entry; `body_text` = the resolved body for derive_art_name(cited, verdict)
    (None ⇒ no body ⇒ clean, reproducing lint.py's `art_name not in artifact_bodies: return`).
    Shared by the disk reader (cited #L/#B range) and the --eval inline-body path.

    ASYMMETRY (reproduced exactly): the PASS leg (tier2_verify) inspects the body for
    grep-kind READ/WROTE witnesses; the FAIL leg (tier2_verify_fail) body lookup is
    EXEC-only — so the SAME grep:READ/WROTE witness whose body matches expect-fail
    raises under PASS but returns clean under FAIL. derive_art_name keys this on verdict."""
    if not witness["ran"].startswith("TRACE#"):
        return True
    art_name = derive_art_name(cited, verdict)
    if art_name is None:
        return True
    if body_text is None:
        return True  # reproduces lint.py `if art_name not in artifact_bodies: return`
    kind = witness["kind"]
    expect_fail = witness["expect_fail"]
    body = body_text
    if verdict == "FAIL":
        # tier2_verify_fail (lint.py:377-390)
        exit_m = re.search(r"exit=(-?\d+)", cited["args"])
        exit_success = exit_m and int(exit_m.group(1)) == 0
        pattern = None
        if expect_fail.startswith("/") and expect_fail.endswith("/"):
            pattern = expect_fail[1:-1]
        elif expect_fail.startswith('"') and expect_fail.endswith('"'):
            pattern = re.escape(expect_fail[1:-1])
        content_match = bool(pattern and re.search(pattern, body))
        if exit_success and not content_match:
            raise LintError(
                f"Tier-2 FAIL: no evidence of failure — exit=0 AND body does not match "
                f"expect-fail {expect_fail} (weak positive-evidence check)"
            )
        return True
    # verdict == PASS — tier2_verify (lint.py:330-355)
    if kind == "exec":
        em = re.match(r"exit(!?=)(-?\d+)", expect_fail)
        if em:
            op, n = em.group(1), int(em.group(2))
            exit_m = re.search(r"exit=(-?\d+)", cited["args"])
            if exit_m:
                actual = int(exit_m.group(1))
                failed = (actual != 0) if op == "!=" else (actual == n)
                if failed:
                    raise LintError(
                        f"Tier-2: WITNESS expect-fail exit-clause matches actual exit={actual} "
                        f"(witness would have fired → PASS rejected)"
                    )
            return True
    # regex / literal expect-fail
    pattern = None
    if expect_fail.startswith("/") and expect_fail.endswith("/"):
        pattern = expect_fail[1:-1]
    elif expect_fail.startswith('"') and expect_fail.endswith('"'):
        pattern = re.escape(expect_fail[1:-1])
    if pattern and re.search(pattern, body):
        raise LintError(
            f"Tier-2: WITNESS expect-fail regex /{pattern}/ matches body of {art_name} "
            f"(witness would have fired → PASS rejected)"
        )
    return True


def _read_cited_range(path: pathlib.Path, cited):
    """Read ONLY the cited #L<a>-L<b> (line) / #B<a>-B<b> (byte) range from disk.
    Deliberate (M2): lint.py's inline tier2_verify reads the WHOLE body, but the disk
    reader reads only the cited range (fixture-4(g)-guarded). READ/WROTE entries carry
    no #range → read whole file (the grep-on-READ/WROTE path; not in natural corpus)."""
    m = re.search(r"out=\S+?#([LB])(\d+)-[LB](\d+)", cited["args"])
    if not m:
        return path.read_text()
    kind, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    # Ranges are 1-based; a<1 is malformed, clamp to 1 so `[a-1:b]` never slices from
    # the END (a=0 → [-1:b], an empty/wrong body that silently bypasses the witness).
    if a < 1:
        a = 1
    # Both #L (line) and #B (byte) ranges are 1-based INCLUSIVE: #L1-L5 = 5 lines,
    # #B1-B5 = bytes 1..5 = 5 bytes (parallel symmetric forms per return-convention).
    if kind == "L":
        lines = path.read_text().splitlines(keepends=True)
        return "".join(lines[a - 1:b])  # 1-based inclusive
    return path.read_bytes()[a - 1:b].decode("utf-8", errors="replace")  # 1-based inclusive


def tier2_witness(witness, trace, root, strict, verdict):
    """Part 2. Resolve the cited TRACE artifact via resolve_base, read ONLY the cited
    #L/#B range from disk, then call the shared verify_witness. Absent witness file:
    path-shaped + --strict -> FAIL; else UNVERIFIABLE (non-fatal). Returns UNVERIFIABLE
    notes; raises LintError on FAIL (incl. verify_witness's byte-identical messages)."""
    if not witness["ran"].startswith("TRACE#"):
        return []
    idx = int(witness["ran"][len("TRACE#"):])
    if not 1 <= idx <= len(trace):
        return []
    cited = trace[idx - 1]
    art_name = derive_art_name(cited, verdict)
    if art_name is None:
        return []
    resolved = resolve_base(art_name, root)
    if resolved is None:
        if strict and is_path_shaped(art_name):
            raise LintError(f"Tier-2 --strict: witness artifact {art_name} absent under all bases")
        return [f"UNVERIFIABLE: witness {art_name} (no file under root)"]
    body_text = _read_cited_range(resolved, cited)
    verify_witness(body_text, witness, verdict, cited)  # raises on FAIL
    return []


def _eval_tier2(witness, trace, bodies, verdict):
    """Reproduce lint.py:411-418's Tier-2 dispatch for the --eval inline-body path,
    routed through the shared verify_witness (PASS→tier2_verify, FAIL→tier2_verify_fail).
    Raises LintError (byte-identical message) on FAIL; the caller prints it as LINT-FAIL."""
    if not witness["ran"].startswith("TRACE#"):
        return
    idx = int(witness["ran"][len("TRACE#"):])
    if not 1 <= idx <= len(trace):
        return
    cited = trace[idx - 1]
    art_name = derive_art_name(cited, verdict)
    body_text = bodies.get(art_name) if art_name else None
    verify_witness(body_text, witness, verdict, cited)


def _eval_record(rec):
    """Classify one --eval record exactly as lint.py's main() loop does (Tier-1 then,
    if inline artifact_bodies + verdict in {PASS,FAIL}, the Tier-2 dispatch via the shared
    verify_witness). Returns ('LINT-PASS', verdict) or ('LINT-FAIL', error_string)."""
    receipt_text = rec.get("receipt")
    try:
        verdict = lint_receipt(receipt_text)
        bodies = rec.get("artifact_bodies", {})
        if bodies and verdict in {"PASS", "FAIL"}:
            sections = parse_receipt(receipt_text)
            trace = parse_trace(sections["TRACE"])
            witness = parse_witness(sections["WITNESS"])
            _eval_tier2(witness, trace, bodies, verdict)
        return ("LINT-PASS", verdict)
    except LintError as e:
        return ("LINT-FAIL", str(e))


def _eval_text(path) -> str:
    """The full --eval stdout (per-line columns + leading-`\\n` summary), byte-exact.
    Shared by run_eval (prints it) and run_selftest's golden-string assertion, so the
    printed format and the CI-pinned format can never drift."""
    out = []
    total = 0
    passed = 0
    for line in _read_path_arg(path).splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if not rec.get("receipt"):
            continue
        total += 1
        disp, info = _eval_record(rec)
        did = rec.get("dispatch-id", "?")
        if disp == "LINT-PASS":
            out.append(f"{did:30s}  LINT-PASS  ({info})")
            passed += 1
        else:
            out.append(f"{did:30s}  LINT-FAIL  {info}")
    out.append(f"\nsummary: {passed}/{total} receipts passed lint")
    return "\n".join(out) + "\n"


def run_eval(path) -> int:
    """Port of lint.py main(): per-line LINT-PASS/LINT-FAIL on stdout + trailing summary.
    ALWAYS exits 0 for a readable file (F1) — per-record verdicts are stdout-only, never
    the process exit code, so run-eval.sh's pipefail greps over all-FAIL inject shapes."""
    sys.stdout.write(_eval_text(path))
    return 0


def _read_jsonl(path):
    return [json.loads(l) for l in pathlib.Path(path).read_text().splitlines() if l.strip()]


def run_selftest() -> int:
    """CI gate: (i) v1 corpus classification via the --eval Tier-2 dispatch; (iii) Tier-2
    disk fixtures; (iv) inline-vs-disk cross-check; (v) --eval stdout golden-string.
    Exit 0 iff all pass; non-zero (never silent) on any failure or absent corpus."""
    if not CORPUS_DIR.is_dir():
        sys.stderr.write(f"corpus not found at {CORPUS_DIR}\n")
        return 1
    problems = []

    # (i) v1 corpus — 5 samples lint-pass; 7 injections LINT-FAIL via the --eval Tier-2
    #     dispatch (the 2 Tier-2-only rows 102/105 raise in verify_witness, NOT lint_receipt).
    for rec in _read_jsonl(CORPUS_DIR / "sample-corpus/receipts.jsonl"):
        disp, info = _eval_record(rec)
        if disp != "LINT-PASS":
            problems.append(f"sample {rec.get('dispatch-id','?')} expected LINT-PASS, got LINT-FAIL: {info}")
    inject_shapes = sorted((CORPUS_DIR / "inject").glob("shape-*.jsonl"))
    if not inject_shapes:
        problems.append("no inject/shape-*.jsonl found")
    for shape in inject_shapes:
        for rec in _read_jsonl(shape):
            if not rec.get("receipt"):
                continue
            disp, info = _eval_record(rec)
            if disp != "LINT-FAIL":
                problems.append(f"inject {shape.name}/{rec.get('dispatch-id','?')} "
                                f"expected LINT-FAIL, got {disp} ({info})")

    # (iii) Tier-2 disk fixtures — each fixture's expect realized against REAL files.
    fx_dir = CORPUS_DIR / "tier2-fixtures"
    for fx in _read_jsonl(fx_dir / "manifest.jsonl"):
        got = _selftest_run_fixture(fx, fx_dir / fx["root"])
        if got != fx["expect"]:
            problems.append(f"fixture {fx['id']} expected {fx['expect']}, got {got}")

    # (iv) cross-check: inline --eval verdict == disk tier2_witness verdict for the inject
    #      rows carrying artifact_bodies (102/105). Also asserts the silent corpus invariant
    #      that the inline body equals its cited #L/#B range (disk reads only the range).
    for shape in inject_shapes:
        for rec in _read_jsonl(shape):
            bodies = rec.get("artifact_bodies")
            if not bodies:
                continue
            problems.extend(_selftest_crosscheck(rec, bodies))

    # (v) --eval stdout golden-string — pins the run-eval.sh-grepped byte format in CI.
    golden = (fx_dir / "eval-golden.txt").read_text()
    captured = _eval_text(CORPUS_DIR / "sample-corpus/receipts.jsonl")
    if captured != golden:
        problems.append("--eval stdout does NOT match committed eval-golden.txt (byte-format drift)")

    if problems:
        for p in problems:
            sys.stderr.write(f"selftest FAIL: {p}\n")
        return 1
    print("selftest OK: v1 corpus + Tier-2 fixtures + cross-check + golden-string")
    return 0


def _selftest_run_fixture(fx, root) -> str:
    """Run one committed Tier-2 fixture through Tier-1 + Tier-2; return 'pass'|'fail'."""
    try:
        text = fx["receipt"]
        verdict = lint_receipt(text)
        sections = parse_receipt(text)
        artifacts = parse_artifacts(sections["ARTIFACTS"])
        trace = parse_trace(sections["TRACE"])
        witness = parse_witness(sections["WITNESS"])
        tier2_artifacts(artifacts, trace, root, fx["strict"])
        if verdict in {"PASS", "FAIL"}:
            tier2_witness(witness, trace, root, fx["strict"], verdict)
        return "pass"
    except LintError:
        return "fail"


def _selftest_crosscheck(rec, bodies):
    """Materialize an artifact_bodies inject's body to disk, run the disk tier2_witness
    path, and assert it agrees with the inline --eval path. Returns a list of problems."""
    import tempfile
    problems = []
    text = rec["receipt"]
    did = rec.get("dispatch-id", "?")
    verdict = lint_receipt(text)
    sections = parse_receipt(text)
    trace = parse_trace(sections["TRACE"])
    witness = parse_witness(sections["WITNESS"])
    idx = int(witness["ran"][len("TRACE#"):])
    cited = trace[idx - 1]
    art = derive_art_name(cited, verdict)
    inline_disp = _eval_record(rec)[0]
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = bodies.get(art)
        if body is not None:
            (root / art).parent.mkdir(parents=True, exist_ok=True)
            (root / art).write_text(body)
            # corpus invariant: inline body == cited range (disk reads only the range)
            cited_range = _read_cited_range(root / art, cited)
            if cited_range != body:
                problems.append(f"crosscheck {did}: inline body != cited range "
                                f"(disk path reads only the range — fixture invariant broken)")
        try:
            tier2_witness(witness, trace, root, False, verdict)
            disk_disp = "LINT-PASS"
        except LintError:
            disk_disp = "LINT-FAIL"
    if disk_disp != inline_disp:
        problems.append(f"crosscheck {did}: inline={inline_disp} != disk={disk_disp}")
    return problems


def _usage_exit():
    sys.stderr.write(__doc__)
    return 2


def _read_path_arg(path):
    """Read the top-level path argument, returning its text. Raises _PathReadError
    (clean one-line stderr + usage exit 2) on a missing/unreadable file — instead of
    leaking a FileNotFoundError/OSError traceback. Only guards the path read itself;
    malformed JSON *content* inside a readable file is out of scope (left to json.loads)."""
    try:
        return pathlib.Path(path).read_text()
    except OSError:
        raise _PathReadError(path)


class _PathReadError(Exception):
    def __init__(self, path):
        super().__init__(path)
        self.path = path


def _verify_single(text, mode, root, strict) -> int:
    """Single-receipt mode: Tier-1 (always) + Tier-2 (if --tier2). Exit 0 on pass,
    1 on any LintError (bullet on stderr). UNVERIFIABLE notes are advisory (stderr, non-fatal)."""
    try:
        verdict = lint_receipt(text)
        if mode == "tier2":
            sections = parse_receipt(text)
            artifacts = parse_artifacts(sections["ARTIFACTS"])
            trace = parse_trace(sections["TRACE"])
            witness = parse_witness(sections["WITNESS"])
            notes = tier2_artifacts(artifacts, trace, root, strict)
            if verdict in {"PASS", "FAIL"}:
                notes += tier2_witness(witness, trace, root, strict, verdict)
            for n in notes:
                sys.stderr.write(n + "\n")
    except LintError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage_exit()
    if argv[0] == "--selftest":
        return run_selftest()
    if argv[0] == "--eval":
        if len(argv) != 2:
            return _usage_exit()
        return run_eval(argv[1])
    # single-receipt mode — hand-parse flags (mirror check_*.py simplicity)
    mode = "tier1"
    root = None
    strict = False
    path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tier1":
            mode = "tier1"
        elif a == "--tier2":
            mode = "tier2"
        elif a == "--strict":
            strict = True
        elif a == "--root":
            i += 1
            if i >= len(argv):
                return _usage_exit()
            root = pathlib.Path(argv[i])
        elif a == "-" or not a.startswith("--"):
            path = a
        else:
            return _usage_exit()
        i += 1
    if root is None:
        root = pathlib.Path.cwd()
    text = sys.stdin.read() if path in (None, "-") else _read_path_arg(path)
    return _verify_single(text, mode, root, strict)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except _PathReadError as e:
        sys.stderr.write(f"rcpt_verify: cannot read {e.path}\n")
        sys.exit(2)
