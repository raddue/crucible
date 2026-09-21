#!/usr/bin/env python3
"""cairn.py — deterministic Phase Entry Check + Reconciliation Pass for Layer 3 cairns.

Executable transcription of the two mechanical procedures in
`skills/shared/cairn-convention.md` (## Phase Entry Check, ## Reconciliation Pass).
The prose there is the canonical spec; this module is its single executable
implementation, so an in-place prose inversion can only flip behavior by also
changing the spec (mirroring scripts/second_pass_scorer.py's oracle role).

Invocation (from repo root):

    python3 scripts/cairn.py check <cairn-file> [--expect-phase <name>/<counter>]
    python3 scripts/cairn.py reconcile <cairn-file> \
        [--ledger <receipt-ledger.jsonl>] [--active-run <active-run.md>]

Exit codes: 0 = pass, 1 = lint/reconciliation failure (abort/escalate), 2 = usage.

Pure stdlib. Grammars are transcribed verbatim from `## Line-shape grammars`.
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Grammars (verbatim from skills/shared/cairn-convention.md "Line-shape grammars")
# ---------------------------------------------------------------------------

RE_CAIRN_TITLE = re.compile(r"^#\s*Cairn\s*[\u2013\u2014-]+\s*(.+?)\s*$")
RE_PHASE_BODY = re.compile(r"^(phase|started-at|parent-skill): .+$")
RE_INVARIANT = re.compile(r"^I-(\d{2})(?: supersedes I-(\d{2}))?: (.*)$")
RE_OBLIGATION = re.compile(r"^- \[([ x])\] (.*)$")
RE_LEDGER = re.compile(
    r"^([a-z][a-z0-9-]*)/(\d+)(?:-(\d+))?\s*\|\s*"
    r"dispatches=(\d+)\s+receipts=(\d+)\s+verdict=(PASS|FAIL|MIXED)\s*\|\s*(.*)$"
)
RE_SKILL_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
RE_12HEX = re.compile(r"^[0-9a-fA-F]{12}$")

SECTION_ORDER = ["PHASE", "INVARIANTS", "OPEN_OBLIGATIONS", "LEDGER"]


class CairnError(Exception):
    pass


def _is_blank_or_comment(line):
    s = line.strip()
    return s == "" or s.startswith("<!--")


def _load_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n")


def _load_jsonl(path):
    """Return list of dict entries; tolerant of ragged final line. Missing file -> None."""
    import os
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_cairn(text):
    """Split a cairn file body into {run_id, sections: {NAME: [content lines]}.

    Content lines = non-blank, non-HTML-comment lines strictly inside a section.
    Raises CairnError on structural problems (title/section order/prose outside).
    """
    lines = text.split("\n")
    if not lines:
        raise CairnError("empty file")

    # find title
    m = RE_CAIRN_TITLE.match(lines[0].strip()) if lines else None
    # allow leading blank/comment lines before title
    title_idx = None
    run_id = None
    for i, ln in enumerate(lines):
        if _is_blank_or_comment(ln):
            continue
        m = RE_CAIRN_TITLE.match(ln.strip())
        if m:
            title_idx = i
            run_id = m.group(1)
            break
        raise CairnError("no `# Cairn — <run-id>` title line found")
    if title_idx is None:
        raise CairnError("no `# Cairn — <run-id>` title line found")

    # locate section headers after title (track file order for the order check)
    positions = {}
    found_order = []
    for i in range(title_idx + 1, len(lines)):
        ln = lines[i].strip()
        if ln in ("## PHASE", "## INVARIANTS", "## OPEN_OBLIGATIONS", "## LEDGER"):
            name = ln[3:]
            if name in positions:
                raise CairnError(f"duplicate section header {ln}")
            positions[name] = i
            found_order.append(name)
        elif ln.startswith("## "):
            raise CairnError(f"unknown section header: {ln!r}")

    # missing sections (all four are required)
    missing = [s for s in SECTION_ORDER if s not in positions]
    if missing:
        raise CairnError("missing section(s): " + ", ".join("## " + s for s in missing))
    # prose between title and the first section header is outside every section body
    first = min(positions.values())
    for i in range(title_idx + 1, first):
        if not _is_blank_or_comment(lines[i]):
            raise CairnError(f"prose between title and first section header: {lines[i].strip()[:40]!r}")
    # order check (requires all four present, so this is a strict equality)
    if found_order != SECTION_ORDER:
        raise CairnError("sections out of order: " + " -> ".join(found_order))

    sections = {}
    for s in SECTION_ORDER:
        start = positions[s] + 1
        # end = next header line (any ## ) after start
        end = len(lines)
        for i in range(start, len(lines)):
            if lines[i].strip().startswith("## "):
                end = i
                break
        body = [ln.rstrip("\n") for ln in lines[start:end]]
        sections[s] = body

    # prose-outside check happens in check() via grammars; here expose raw bodies.
    return {"run_id": run_id, "sections": sections}


def _section_content_lines(body):
    return [ln for ln in body if not _is_blank_or_comment(ln)]


def _parse_phase(phase_value):
    # "phase: <name> / <counter>"  — value = text after "phase: "
    m = re.match(r"^\s*(.*?)\s*/\s*(\d+)\s*$", phase_value)
    if not m:
        raise CairnError(f"{phase_value!r} (expected '<name> / <count>')")
    return m.group(1).strip(), int(m.group(2))


# ---------------------------------------------------------------------------
# Phase Entry Check
# ---------------------------------------------------------------------------

def phase_entry_check(text, expect_phase=None):
    """Return list of error strings (empty == pass)."""
    errors = []

    # the error list from parse comes first
    try:
        parsed = parse_cairn(text)
    except CairnError as e:
        return [str(e)]

    sections = parsed["sections"]
    # (all four sections are guaranteed present by parse_cairn)

    # ---- PHASE body: exactly three lines, phase/started-at/parent-skill, in order
    phase_lines = _section_content_lines(sections["PHASE"])
    if len(phase_lines) != 3:
        errors.append(
            f"PHASE section must have exactly 3 content lines (phase, started-at, parent-skill); got {len(phase_lines)}"
        )
    else:
        expect_keys = ["phase", "started-at", "parent-skill"]
        for i, (ln, key) in enumerate(zip(phase_lines, expect_keys)):
            if not ln.startswith(key + ":"):
                errors.append(f"PHASE line {i + 1}: expected key {key!r}, got {ln[:40]!r}")
                break
        # parent-skill grammar
        ps = phase_lines[2]
        try:
            val = ps.split(":", 1)[1].strip()
        except IndexError:
            val = ""
        if not RE_SKILL_NAME.match(val):
            errors.append(f"parent-skill violates grammar [a-z][a-z0-9-]*: {val!r}")

        # phase value format <name> / <counter>
        pval = phase_lines[0].split(":", 1)[1].strip()
        try:
            _parse_phase(pval)
        except CairnError as e:
            errors.append(f"phase value malformed: {e}")

        # expect-phase comparison (exact string match after 'phase: ')
        if expect_phase is not None:
            actual = phase_lines[0].split(":", 1)[1].strip()
            if actual != expect_phase.strip():
                errors.append(
                    f"phase value {actual!r} != orchestrator's expected next phase {expect_phase.strip()!r}"
                )

    # ---- INVARIANTS body
    for ln in _section_content_lines(sections["INVARIANTS"]):
        m = RE_INVARIANT.match(ln)
        if not m:
            errors.append(f"INVARIANTS line violates grammar: {ln[:60]!r}")
            continue
        if len(ln) > 240:
            errors.append(f"INVARIANTS line exceeds 240 chars ({len(ln)}): {ln[:40]!r}")
        fact = m.group(3).strip()
        if fact == "TODO" or re.match(r"^TODO\b", fact):
            errors.append(f"INVARIANTS fact is the literal TODO stub: {ln[:60]!r}")

    # invariant ordinals: leading must be 01,02,03...; superseded must be < leading
    ordinal_lines = [ln for ln in _section_content_lines(sections["INVARIANTS"]) if RE_INVARIANT.match(ln)]
    leading = []
    for ln in ordinal_lines:
        m = RE_INVARIANT.match(ln)
        leading.append(int(m.group(1)))
        if m.group(2) is not None:
            sup = int(m.group(2))
            if not (1 <= sup < leading[-1]):
                errors.append(f"INVARIANTS superseded ordinal I-{sup:02d} invalid on line {ln[:60]!r}")
    for i, n in enumerate(leading, start=1):
        if n != i:
            errors.append(
                f"INVARIANTS ordinal out of order/missing/duplicate: expected I-{i:02d}, got I-{n:02d}"
            )
            break

    # ---- OPEN_OBLIGATIONS body
    for ln in _section_content_lines(sections["OPEN_OBLIGATIONS"]):
        if not RE_OBLIGATION.match(ln):
            errors.append(f"OPEN_OBLIGATIONS line violates grammar: {ln[:60]!r}")
            continue
        if len(ln) > 240:
            errors.append(f"OPEN_OBLIGATIONS line exceeds 240 chars ({len(ln)}): {ln[:40]!r}")

    # ---- LEDGER body
    for ln in _section_content_lines(sections["LEDGER"]):
        m = RE_LEDGER.match(ln)
        if not m:
            errors.append(f"LEDGER line violates grammar: {ln[:60]!r}")
            continue
        summary = m.group(7)
        if len(summary) > 80:
            errors.append(f"LEDGER summary exceeds 80 chars ({len(summary)}): {summary[:40]!r}")

    return errors


# ---------------------------------------------------------------------------
# Reconciliation Pass
# ---------------------------------------------------------------------------

def _parse_ledger_lines(sections):
    out = []
    for ln in _section_content_lines(sections.get("LEDGER", [])):
        m = RE_LEDGER.match(ln)
        if not m:
            continue
        out.append({
            "raw": ln,
            "phase": m.group(1),
            "counter": int(m.group(2)),
            "high": int(m.group(3)) if m.group(3) else None,
            "dispatches": int(m.group(4)),
            "receipts": int(m.group(5)),
            "verdict": m.group(6),
            "summary": m.group(7),
        })
    return out


def _resolve_prefix(prefix, ledger):
    """Return list of matching ledger rows whose rcpt_sha256 starts with prefix(12hex)."""
    if ledger is None:
        return None  # ledger absent
    hits = []
    p = prefix.lower()
    for row in ledger:
        sha = str(row.get("rcpt_sha256", "")).lower()
        if sha[:12] == p:
            hits.append(row)
    return hits


def reconciliation_pass(text, ledger=None, active_run_text=None, cairn_path=None,
                       ledger_provided=False):
    """Return dict {ok: bool, escalations: [str], notes: [str]}.

    ledger: parsed receipt-ledger.jsonl rows (None = no ledger data).
    ledger_provided: True iff the caller passed a --ledger path (so a None
    ledger means "file missing/unreadable", not "receipt-less cairn").
    cairn_path: path to the cairn file, for the Rule 3 filename run-id check.
    """
    escalations = []
    notes = []

    try:
        parsed = parse_cairn(text)
    except CairnError as e:
        return {"ok": False, "escalations": [str(e)], "notes": []}

    sections = parsed["sections"]
    title_run_id = parsed["run_id"]

    phase_lines = _section_content_lines(sections.get("PHASE", []))
    if len(phase_lines) != 3:
        return {"ok": False, "escalations": ["PHASE section malformed (run phase-entry check first)"], "notes": []}
    try:
        pname, pcounter = _parse_phase(phase_lines[0].split(":", 1)[1].strip())
    except CairnError as e:
        return {"ok": False, "escalations": [f"PHASE phase value malformed: {e}"], "notes": []}
    parent_skill = phase_lines[2].split(":", 1)[1].strip()

    ledger_lines = _parse_ledger_lines(sections)

    # filen-name run-id (Rule 3 authority)
    filename_run_id = None
    if cairn_path:
        fn = os.path.basename(cairn_path)
        if fn.startswith("cairn-") and fn.endswith(".md"):
            filename_run_id = fn[len("cairn-"):-len(".md")]
        if filename_run_id is not None and filename_run_id != title_run_id:
            notes.append(f"title run-id {title_run_id!r} != filename run-id {filename_run_id!r}")

    # ---- Rule 5 (precedence over Rule 1): phase-transition atomicity witness
    if not ledger_lines:
        if pcounter >= 2:
            escalations.append(
                "rule5: PHASE counter >= 2 but LEDGER empty (auto-compaction hit "
                "between phase-transition write and ack)"
            )
    else:
        tail = ledger_lines[-1]
        tail_counter = tail["high"] if tail["high"] is not None else tail["counter"]
        if pcounter != tail_counter + 1:
            direction = "skipped phase-completion lines" if pcounter > tail_counter + 1 else "PHASE counter lagged LEDGER tail"
            escalations.append(
                f"rule5: PHASE counter {pcounter} != LEDGER tail counter {tail_counter} + 1 ({direction})"
            )

    # ---- Rule 1: LEDGER dispatch count consistency
    declared_dispatches = any(ll["dispatches"] > 0 for ll in ledger_lines)
    if ledger is None:
        if ledger_provided:
            escalations.append("rule1: --ledger path provided but file missing/unreadable")
        elif declared_dispatches:
            escalations.append(
                "rule1: LEDGER declares dispatches>0 but no receipt ledger supplied (receipt-less no-op does not apply)"
            )
        else:
            notes.append("rule1: receipt-less cairn (no dispatches declared) — rule 1 no-op")
    else:
        for ll in ledger_lines:
            if ll["high"] is not None:
                notes.append(f"rule1: range line (per-line count not checkable): {ll['phase']}/{ll['counter']}-{ll['high']}")
                continue
            key = f"{parent_skill}:{ll['phase']}/{ll['counter']}"
            actual = sum(1 for r in ledger if str(r.get("phase", "")) == key)
            if actual != ll["dispatches"]:
                escalations.append(
                    f"rule1: LEDGER {ll['phase']}/{ll['counter']} declares dispatches={ll['dispatches']} "
                    f"but receipt-ledger.jsonl has {actual} entries for phase {key!r}"
                )
        # narrow local-repair condition is orchestrator judgment, surfaced as guidance
        if any(str(r.get("phase", "")) for r in ledger):
            notes.append(
                "rule1: local repair is permitted ONLY when PHASE and LEDGER-tail agree on the "
                "current phase AND the only discrepancy is trailing receipts for the in-progress "
                "phase — an orchestrator judgment, not auto-certified here (escalate by default)."
            )

    # ---- Rule 2: OPEN_OBLIGATIONS closure evidence
    for ln in _section_content_lines(sections.get("OPEN_OBLIGATIONS", [])):
        m = RE_OBLIGATION.match(ln)
        if not m:
            continue
        checked = m.group(1) == "x"
        body = m.group(2)
        closed = re.findall(r"\[closed-by: ([^\]]*)\]", body)
        reason = re.findall(r"\[reason: ([^\]]*)\]", body)

        if not checked:
            if closed:
                escalations.append(f"rule2: open [ ] obligation carries closed-by: {ln[:60]!r}")
            continue

        if len(closed) != 1:
            escalations.append(f"rule2: closed [x] obligation must carry exactly one [closed-by: …]: {ln[:60]!r}")
            continue
        cb = closed[0]
        if RE_12HEX.match(cb):
            if ledger is None:
                escalations.append(f"rule2: direct-close {cb} requires a receipt ledger: {ln[:60]!r}")
                continue
            hits = _resolve_prefix(cb, ledger)
            if len(hits) == 0:
                escalations.append(f"rule2: closed-by {cb} resolves to no ledger entry (absence → escalate)")
            elif len(hits) > 1:
                escalations.append(f"rule2: closed-by {cb} prefix collides across {len(hits)} entries")
            else:
                if hits[0].get("verdict") != "PASS":
                    escalations.append(f"rule2: closed-by {cb} resolves to verdict={hits[0].get('verdict')!r}, expected PASS")
                else:
                    notes.append(f"rule2: direct-close {cb} → PASS receipt (ran= disposition verified in-context by orchestrator)")
        elif cb.startswith("SUPERSEDED_BY="):
            suffix = cb[len("SUPERSEDED_BY="):]
            if not RE_12HEX.match(suffix):
                escalations.append(f"rule2: peer-supersession close carries non-12-hex later-prefix {suffix!r}: {ln[:60]!r}")
            else:
                notes.append(f"rule2: peer-supersession close ({cb}) — Layer 2 manifest check is in-context, not file-verifiable")
        elif re.match(r"^[a-z][a-z0-9-]*/\d+$", cb):
            if len(reason) != 1 or len(reason[0]) > 80:
                escalations.append(f"rule2: phase/counter discharge {cb} needs exactly one [reason: ≤80 chars]: {ln[:60]!r}")
            else:
                notes.append(f"rule2: discharge by orchestrator judgment ({cb})")
        else:
            escalations.append(f"rule2: unknown [closed-by: {cb}] form: {ln[:60]!r}")

    # ---- Rule 3: active-run singleton (detection-only)
    if active_run_text is not None:
        m = re.search(r"run-id:\s*(\S+)", active_run_text)
        if filename_run_id is None:
            notes.append("rule3: cairn filename not in `cairn-<run-id>.md` shape — run-id check skipped")
        elif not m:
            escalations.append("rule3: active-run.md missing run-id field")
        elif m.group(1) != filename_run_id:
            escalations.append(f"rule3: active-run run-id {m.group(1)!r} != cairn filename run-id {filename_run_id!r}")
        else:
            notes.append("rule3: active-run run-id matches cairn filename")
    else:
        notes.append("rule3: no active-run.md provided (singleton not checked)")

    # ---- Rule 4: invariant-receipt liveness (decision point)
    seen_ref = False
    for ln in _section_content_lines(sections.get("INVARIANTS", [])):
        m = RE_INVARIANT.match(ln)
        if not m:
            continue
        refs = re.findall(r"\[ref: ([^\]]*)\]", m.group(3))
        for ref in refs:
            seen_ref = True
            if not RE_12HEX.match(ref):
                escalations.append(f"rule4: [ref: {ref}] is not a 12-hex prefix")
                continue
            if ledger is None:
                escalations.append(f"rule4: invariant cites receipt {ref} but no ledger (absence → escalate)")
                continue
            hits = _resolve_prefix(ref, ledger)
            if len(hits) == 0:
                escalations.append(f"rule4: [ref: {ref}] resolves to no ledger entry (absence → escalate)")
            elif len(hits) > 1:
                escalations.append(f"rule4: [ref: {ref}] prefix collides across {len(hits)} entries")
            else:
                notes.append(f"rule4: [ref: {ref}] resolves uniquely")
    if seen_ref:
        notes.append(
            "rule4: Layer 2 SUPERSEDED_BY state is in-context only — if the manifest marks a "
            "cited receipt superseded, the orchestrator MUST record a superseding invariant or a "
            "closed obligation before proceeding (decision point, not file-checkable)."
        )

    return {"ok": not escalations, "escalations": escalations, "notes": notes}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_report(kind, errors_or_pass):
    if kind == "check":
        if not errors_or_pass:
            print("CAIRN CHECK: PASS")
        else:
            print("CAIRN CHECK: FAIL")
            for e in errors_or_pass:
                print(f"  - {e}")


def main(argv):
    p = argparse.ArgumentParser(prog="cairn.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="Phase Entry Check (structural lint)")
    c.add_argument("file")
    c.add_argument("--expect-phase", default=None)

    r = sub.add_parser("reconcile", help="Reconciliation Pass")
    r.add_argument("file")
    r.add_argument("--ledger", default=None)
    r.add_argument("--active-run", default=None)

    a = p.parse_args(argv)

    text = open(a.file, encoding="utf-8").read()

    if a.cmd == "check":
        errs = phase_entry_check(text, a.expect_phase)
        _print_report("check", errs)
        return 1 if errs else 0

    if a.cmd == "reconcile":
        ledger = _load_jsonl(a.ledger) if a.ledger else None
        active = None
        if a.active_run:
            try:
                active = open(a.active_run, encoding="utf-8").read()
            except OSError:
                active = None
        rep = reconciliation_pass(text, ledger=ledger, active_run_text=active,
                                  cairn_path=a.file, ledger_provided=a.ledger is not None)
        if rep["ok"]:
            print("CAIRN RECONCILE: PASS")
            for n in rep["notes"]:
                print(f"  ~ {n}")
            return 0
        print("CAIRN RECONCILE: ESCALATE")
        for e in rep["escalations"]:
            print(f"  ! {e}")
        for n in rep["notes"]:
            print(f"  ~ {n}")
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))