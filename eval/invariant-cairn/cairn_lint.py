#!/usr/bin/env python3
"""
Reference implementation of the Invariant Cairn linter (Layer 3).

This is an eval artifact — the canonical linter lives as prose pseudocode in
`skills/shared/cairn-convention.md`. This Python version lets the test suite
confirm the schema rules and Phase Entry Check behave as specified.

Implements:
- Schema parsing + line-shape grammars
- Phase Entry Check (structural)
- Reconciliation Pass rules 1–5 against provided receipt-ledger + tripwire
  manifest + active-run marker

Usage:
  python3 cairn_lint.py check <cairn.md>
  python3 cairn_lint.py reconcile <cairn.md> <receipt-ledger.jsonl> <manifest.json> <active-run.md>
"""
import json
import re
import sys
from pathlib import Path


SECTIONS = ["PHASE", "INVARIANTS", "OPEN_OBLIGATIONS", "LEDGER"]
MAX_LINE_LEN = 240
SUMMARY_MAX = 80
HARD_BUDGET_LINES = 200


class CairnError(Exception):
    pass


def parse_cairn(text):
    """Parse cairn text into {section: body_lines}. Body lines preserve content."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# Cairn — "):
        raise CairnError("first line must start with '# Cairn — '")
    sections = {}
    current = None
    header_order = []
    for line in lines[1:]:
        m = re.match(r"^## (PHASE|INVARIANTS|OPEN_OBLIGATIONS|LEDGER)\s*$", line)
        if m:
            name = m.group(1)
            if name in sections:
                raise CairnError(f"section {name} duplicated")
            sections[name] = []
            header_order.append(name)
            current = name
            continue
        if current is None:
            if line.strip() == "":
                continue
            raise CairnError(f"prose before first section header: {line!r}")
        sections[current].append(line)
    if header_order != SECTIONS:
        raise CairnError(f"sections out of order: got {header_order}, expected {SECTIONS}")
    return sections


PHASE_KEYS = ("phase", "started-at", "parent-skill")
INV_RE = re.compile(r"^I-\d{2}(?: supersedes I-\d{2})?: .+$")
OBL_RE = re.compile(r"^- \[[ x]\] .+$")
LEDGER_RE = re.compile(
    r"^[a-z][a-z0-9-]*/\d+(?:-\d+)?\s*\|\s*dispatches=\d+\s+receipts=\d+\s+verdict=(?:PASS|FAIL|MIXED)\s*\|\s*.+$"
)


def check_body_nonblank(lines):
    """Return list of non-blank, non-HTML-comment body lines."""
    return [l for l in lines if l.strip() and not l.strip().startswith("<!--")]


def phase_entry_check(text):
    """Apply the full Phase Entry Check. Raises CairnError on failure."""
    sections = parse_cairn(text)
    # Total line budget
    total_lines = sum(1 for _ in text.splitlines())
    if total_lines > HARD_BUDGET_LINES:
        raise CairnError(f"cairn exceeds hard budget: {total_lines} > {HARD_BUDGET_LINES}")

    # PHASE
    phase_body = check_body_nonblank(sections["PHASE"])
    if len(phase_body) != 3:
        raise CairnError(f"PHASE body must have exactly 3 lines, got {len(phase_body)}")
    # Line 1: phase: <name> / <counter>  (spaces around /; <name> is single token)
    m = re.match(r"^phase: (\S+) / (\d+)$", phase_body[0].strip())
    if not m:
        raise CairnError(
            f"PHASE line 1 malformed (expected 'phase: <name> / <counter>' with spaces around '/'): "
            f"{phase_body[0]!r}"
        )
    # Lines 2, 3: started-at / parent-skill with any non-empty value
    for i, key in enumerate(PHASE_KEYS[1:], start=1):
        m = re.match(rf"^{key}: (.+)$", phase_body[i].strip())
        if not m:
            raise CairnError(f"PHASE line {i+1} malformed (expected '{key}: …'): {phase_body[i]!r}")

    # INVARIANTS
    inv_body = check_body_nonblank(sections["INVARIANTS"])
    seen_ords = []
    for raw in inv_body:
        line = raw.strip()
        if not INV_RE.match(line):
            raise CairnError(f"INVARIANTS line malformed: {line!r}")
        if len(line) > MAX_LINE_LEN:
            raise CairnError(f"INVARIANTS line exceeds {MAX_LINE_LEN} chars: {len(line)}")
        if line.endswith(": TODO") or line.endswith(": TODO fill this in"):
            raise CairnError(f"INVARIANTS TODO placeholder: {line!r}")
        ord_m = re.match(r"^I-(\d{2})", line)
        ord_n = int(ord_m.group(1))
        if seen_ords and ord_n <= seen_ords[-1]:
            raise CairnError(f"INVARIANTS ordinals not strictly increasing: I-{ord_n:02d} after I-{seen_ords[-1]:02d}")
        seen_ords.append(ord_n)

    # OPEN_OBLIGATIONS
    obl_body = check_body_nonblank(sections["OPEN_OBLIGATIONS"])
    for raw in obl_body:
        line = raw.strip()
        if not OBL_RE.match(line):
            raise CairnError(f"OPEN_OBLIGATIONS line malformed: {line!r}")
        if len(line) > MAX_LINE_LEN:
            raise CairnError(f"OPEN_OBLIGATIONS line exceeds {MAX_LINE_LEN} chars: {len(line)}")

    # LEDGER
    ledger_body = check_body_nonblank(sections["LEDGER"])
    for raw in ledger_body:
        line = raw.strip()
        if not LEDGER_RE.match(line):
            raise CairnError(f"LEDGER line malformed: {line!r}")
        # Check summary clause ≤ SUMMARY_MAX chars
        last_pipe = line.rfind("|")
        summary = line[last_pipe + 1:].strip()
        if len(summary) > SUMMARY_MAX:
            raise CairnError(f"LEDGER summary exceeds {SUMMARY_MAX} chars: {len(summary)}")

    return sections


def parse_phase(phase_body_lines):
    """Return dict with phase name, counter, started-at, parent-skill.
    Safe under malformed input — raises CairnError rather than AttributeError."""
    body = check_body_nonblank(phase_body_lines)
    if not body:
        raise CairnError("PHASE body empty")
    m = re.match(r"^phase: (\S+) / (\d+)$", body[0].strip())
    if not m:
        raise CairnError(f"PHASE line 1 malformed: {body[0]!r}")
    return {
        "phase": m.group(1),
        "counter": int(m.group(2)),
    }


def parse_ledger_tail(ledger_body_lines):
    """Return the tail LEDGER entry's phase + counter, or (None, None) if empty."""
    body = check_body_nonblank(ledger_body_lines)
    if not body:
        return None, None
    last = body[-1].strip()
    m = re.match(r"^([a-z][a-z0-9-]*)/(\d+)(?:-(\d+))?\s*\|", last)
    phase = m.group(1)
    counter = int(m.group(3)) if m.group(3) else int(m.group(2))
    return phase, counter


def parse_ledger_counts(ledger_body_lines):
    """Return list of dicts per LEDGER line."""
    out = []
    for raw in check_body_nonblank(ledger_body_lines):
        line = raw.strip()
        m = re.match(
            r"^([a-z][a-z0-9-]*)/(\d+)(?:-(\d+))?\s*\|\s*dispatches=(\d+)\s+receipts=(\d+)\s+verdict=(\w+)",
            line,
        )
        if not m:
            continue
        out.append({
            "phase": m.group(1),
            "counter": int(m.group(2)),
            "counter_high": int(m.group(3)) if m.group(3) else None,
            "dispatches": int(m.group(4)),
            "receipts": int(m.group(5)),
            "verdict": m.group(6),
        })
    return out


def parse_obligations(obl_body_lines):
    """Return list of obligations with parsed trailers."""
    out = []
    for raw in check_body_nonblank(obl_body_lines):
        line = raw.strip()
        closed = line.startswith("- [x] ")
        ref_m = re.search(r"\[ref:\s*([^\]]+)\]", line)
        closed_by_m = re.search(r"\[closed-by:\s*([^\]]+)\]", line)
        reason_m = re.search(r"\[reason:\s*([^\]]+)\]", line)
        out.append({
            "text": line,
            "closed": closed,
            "ref": ref_m.group(1).strip() if ref_m else None,
            "closed_by": closed_by_m.group(1).strip() if closed_by_m else None,
            "reason": reason_m.group(1).strip() if reason_m else None,
        })
    return out


def parse_invariants(inv_body_lines):
    out = []
    for raw in check_body_nonblank(inv_body_lines):
        line = raw.strip()
        ref_m = re.search(r"\[ref:\s*([0-9a-f]{12})\]", line)
        sup_m = re.match(r"^I-(\d{2}) supersedes I-(\d{2}):", line)
        out.append({
            "text": line,
            "ord": int(re.match(r"^I-(\d{2})", line).group(1)),
            "ref": ref_m.group(1) if ref_m else None,
            "supersedes": int(sup_m.group(2)) if sup_m else None,
        })
    return out


def reconciliation_pass(sections, receipt_ledger, tripwire_manifest, active_run_marker, cairn_run_id):
    """Apply the 5-rule reconciliation pass. Raises CairnError on failure."""
    # Rule 3: Active-run singleton (detection)
    if active_run_marker is None:
        raise CairnError("Rule 3: active-run.md missing (run is not terminally sealed per caller)")
    marker_m = re.match(r"^run-id:\s*(\S+)", active_run_marker.strip())
    if not marker_m:
        raise CairnError(f"Rule 3: active-run.md malformed: {active_run_marker!r}")
    marker_run_id = marker_m.group(1)
    if marker_run_id != cairn_run_id:
        raise CairnError(f"Rule 3: active-run run-id ({marker_run_id}) does not match cairn ({cairn_run_id})")

    # Rule 5 (and precedence over Rule 1): PHASE vs LEDGER tail
    phase = parse_phase(sections["PHASE"])
    ledger_phase, ledger_tail_counter = parse_ledger_tail(sections["LEDGER"])
    if ledger_tail_counter is None:
        if phase["counter"] >= 2:
            raise CairnError(
                f"Rule 5: PHASE counter={phase['counter']} but LEDGER empty — compaction hit between "
                f"transition write and ack; escalate"
            )
    else:
        # Gap check
        if phase["counter"] > ledger_tail_counter + 1:
            raise CairnError(
                f"Rule 5: PHASE counter={phase['counter']} > LEDGER tail counter {ledger_tail_counter} + 1; "
                f"phase completion line(s) skipped — escalate"
            )

    # Rule 1: LEDGER dispatch-count consistency
    ledger_entries = parse_ledger_counts(sections["LEDGER"])
    # Index by hash_prefix for obligation/invariant lookups (closed-by and ref use hash prefixes)
    ledger_by_id = {r["hash_prefix"]: r for r in receipt_ledger}
    for entry in ledger_entries:
        # Count ledger entries whose dispatch-id begins with "<phase>/<counter>-"
        prefix = f"{entry['phase']}/{entry['counter']}-"
        matching = [r for r in receipt_ledger if r["dispatch_id"].startswith(prefix)]
        if len(matching) != entry["dispatches"]:
            # Only allow Rule 1 local repair in the narrow scope (current in-progress phase)
            # — here we just surface the mismatch.
            raise CairnError(
                f"Rule 1: LEDGER {entry['phase']}/{entry['counter']} says dispatches={entry['dispatches']}, "
                f"receipt-ledger has {len(matching)}"
            )

    # Rule 2: OPEN_OBLIGATIONS closure evidence
    obligations = parse_obligations(sections["OPEN_OBLIGATIONS"])
    for obl in obligations:
        if not obl["closed"]:
            continue
        if obl["closed_by"] is None:
            raise CairnError(f"Rule 2: closed obligation missing [closed-by: …]: {obl['text']!r}")
        cb = obl["closed_by"]
        if cb.startswith("SUPERSEDED_BY="):
            later_prefix = cb[len("SUPERSEDED_BY="):]
            # Must appear in tripwire_manifest as an original SUPERSEDED_BY that prefix
            # with later verdict PASS
            mt = tripwire_manifest.get("supersessions", {})
            orig = obl.get("ref")
            if orig is None or mt.get(orig) != later_prefix:
                raise CairnError(
                    f"Rule 2: peer-supersession close cites SUPERSEDED_BY={later_prefix} but "
                    f"tripwire manifest does not confirm this for obligation's ref={orig}"
                )
            later = ledger_by_id.get(later_prefix)
            if not later or later["verdict"] != "PASS":
                raise CairnError(
                    f"Rule 2: peer-supersession close cites {later_prefix} which is not PASS in receipt-ledger"
                )
        elif re.match(r"^[0-9a-f]{12}$", cb):
            # Direct close
            r = ledger_by_id.get(cb)
            if not r:
                raise CairnError(f"Rule 2: closed-by {cb} not in receipt-ledger")
            if r["verdict"] != "PASS":
                raise CairnError(f"Rule 2: closed-by {cb} verdict={r['verdict']}, expected PASS")
            # If obligation originated from a SKIPPED witness (ref present), closing receipt's
            # witness must be ran=TRACE#N
            if obl.get("ref"):
                witness_ran = r.get("witness_ran", "")
                if witness_ran.startswith("SKIPPED:") or witness_ran.startswith("UNRUNNABLE:"):
                    raise CairnError(
                        f"Rule 2: obligation with ref={obl['ref']} closed by receipt {cb} whose "
                        f"witness ran={witness_ran} (must be ran=TRACE#N)"
                    )
        elif re.match(r"^[a-z][a-z0-9-]*/\d+$", cb):
            # Explicit discharge — requires [reason: …]
            if not obl["reason"]:
                raise CairnError(
                    f"Rule 2: explicit-discharge close {cb} missing [reason: …]: {obl['text']!r}"
                )
        else:
            raise CairnError(f"Rule 2: unknown closed-by form: {cb!r}")

    # Rule 4: Invariant-receipt liveness (decision point)
    invariants = parse_invariants(sections["INVARIANTS"])
    superseded = tripwire_manifest.get("supersessions", {})
    # Build set of invariant ordinals that have been superseded in-cairn
    superseded_in_cairn = {i["supersedes"] for i in invariants if i["supersedes"] is not None}
    # Also count explicit-discharge entries referencing I-NN
    reviewed_ords = set()
    for obl in obligations:
        m = re.search(r"I-(\d{2}) reviewed against supersession", obl["text"])
        if m and obl["closed"]:
            reviewed_ords.add(int(m.group(1)))
    for inv in invariants:
        if inv["supersedes"] is not None:
            continue  # this IS a superseding invariant
        if inv["ref"] is None:
            continue  # pinned-only, no liveness check
        if inv["ref"] not in ledger_by_id:
            raise CairnError(
                f"Rule 4: I-{inv['ord']:02d} [ref: {inv['ref']}] not present in receipt-ledger"
            )
        if inv["ref"] in superseded:
            if inv["ord"] in superseded_in_cairn or inv["ord"] in reviewed_ords:
                continue  # decision recorded
            raise CairnError(
                f"Rule 4: I-{inv['ord']:02d} [ref: {inv['ref']}] is SUPERSEDED_BY="
                f"{superseded[inv['ref']]} but cairn has not recorded a decision (supersede or discharge)"
            )


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "check":
        text = Path(sys.argv[2]).read_text()
        try:
            phase_entry_check(text)
            print(f"PASS  phase-entry-check")
        except CairnError as e:
            print(f"FAIL  {e}")
            sys.exit(1)
    elif mode == "reconcile":
        if len(sys.argv) != 6:
            print("Usage: cairn_lint.py reconcile <cairn.md> <receipt-ledger.jsonl> <manifest.json> <active-run.md>")
            sys.exit(2)
        text = Path(sys.argv[2]).read_text()
        ledger = [json.loads(l) for l in Path(sys.argv[3]).read_text().splitlines() if l.strip()]
        manifest = json.loads(Path(sys.argv[4]).read_text())
        active = Path(sys.argv[5]).read_text() if Path(sys.argv[5]).exists() else None
        try:
            sections = phase_entry_check(text)
            # Extract run-id from the cairn's own header line (authoritative).
            first_line = text.splitlines()[0]
            run_id_m = re.match(r"^# Cairn — (\S+)", first_line)
            run_id = run_id_m.group(1) if run_id_m else ""
            reconciliation_pass(sections, ledger, manifest, active, run_id)
            print(f"PASS  reconciliation")
        except CairnError as e:
            print(f"FAIL  {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
