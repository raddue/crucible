#!/usr/bin/env python3
"""T-9: L-8 truncation + sidecar + oversize rejection.

Assertion groups:
  1. gated_files = 501 → 500 in ledger, gated_files_truncated=1, confidence unchanged,
     sidecar present with all 501 paths.
  2. highest_finding = 300 chars → 256 chars in ledger.
  3. >16 KiB line even after truncation → append rejected, no line in ledger.
  4. Reconciler fallback: sidecar present → full list; sidecar absent → unfalsifiable.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def _base_entry():
    return {
        "schema_version": 1,
        "run_id": "test-run-t9",
        "skill": "quality-gate",
        "tier": "A",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": 0.91,
        "artifact_hash": "b" * 64,
        "chunk_hash": None,
        "gated_files": [],
        "findings_count": 0,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
        "highest_finding": None,
        "would_have_shipped_without_gate": False,
        "rounds": 1,
        "timestamp": "2026-05-19T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": None,
        "predicted_falsifier": None,
    }


def _simulated_reconciler_load(ledger_entry, overflow_dir):
    """Preview of Phase 4 contract:
    - If gated_files_truncated > 0 AND sidecar present: use sidecar's full list.
    - If gated_files_truncated > 0 AND sidecar absent: log warning + mark unfalsifiable.
    - Else: use ledger's gated_files as-is.
    Returns (file_list, unfalsifiable_flag, warning_msg_or_None).
    """
    truncated = ledger_entry.get("gated_files_truncated", 0)
    if not truncated:
        return list(ledger_entry.get("gated_files", [])), False, None
    sidecar = os.path.join(overflow_dir, f"{ledger_entry['run_id']}.{ledger_entry['skill']}.txt")
    if os.path.exists(sidecar):
        with open(sidecar) as f:
            return [ln.strip() for ln in f if ln.strip()], False, None
    return [], True, f"sidecar missing for {ledger_entry['run_id']}.{ledger_entry['skill']}"


def test_group1_gated_files_truncation():
    from scripts.ledger_append import append
    tmp = tempfile.mkdtemp(prefix="t9-g1-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")
    try:
        entry = _base_entry()
        entry["gated_files"] = [f"path/f{i}" for i in range(501)]
        entry["confidence"] = 0.91
        ok = append(ledger, entry, overflow_dir=overflow)
        _check("T-9.1 append returned True", ok)
        with open(ledger) as f:
            row = json.loads(f.readline())
        _check("T-9.1 ledger gated_files count == 500", len(row["gated_files"]) == 500,
               f"got {len(row['gated_files'])}")
        _check("T-9.1 gated_files_truncated == 1", row["gated_files_truncated"] == 1,
               f"got {row['gated_files_truncated']}")
        _check("T-9.1 confidence NOT demoted", row["confidence"] == 0.91,
               f"got {row['confidence']}")
        sidecar = os.path.join(overflow, "test-run-t9.quality-gate.txt")
        _check("T-9.1 sidecar exists", os.path.exists(sidecar))
        with open(sidecar) as f:
            paths = [ln.strip() for ln in f if ln.strip()]
        _check("T-9.1 sidecar has all 501 paths", len(paths) == 501, f"got {len(paths)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_group2_highest_finding_truncation():
    from scripts.ledger_append import append
    tmp = tempfile.mkdtemp(prefix="t9-g2-")
    ledger = os.path.join(tmp, "runs.jsonl")
    try:
        entry = _base_entry()
        entry["run_id"] = "test-run-t9-g2"
        entry["highest_finding"] = "x" * 300
        ok = append(ledger, entry, overflow_dir=os.path.join(tmp, "overflow"))
        _check("T-9.2 append returned True", ok)
        with open(ledger) as f:
            row = json.loads(f.readline())
        _check("T-9.2 highest_finding truncated to 256 chars",
               len(row["highest_finding"]) == 256, f"got {len(row['highest_finding'])}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_group3_oversize_rejection():
    from scripts.ledger_append import append
    tmp = tempfile.mkdtemp(prefix="t9-g3-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")
    try:
        entry = _base_entry()
        entry["run_id"] = "test-run-t9-g3"
        # `comment` is a free-text field — not subject to truncation; use it to force >16 KiB.
        entry["comment"] = "z" * 20000
        ok = append(ledger, entry, overflow_dir=overflow)
        _check("T-9.3 oversize append returned False (rejected)", ok is False)
        _check("T-9.3 ledger file does NOT contain the oversize line",
               (not os.path.exists(ledger)) or os.path.getsize(ledger) == 0)
        # S-3 fix: NO orphan sidecar when ledger append is rejected.
        sidecar = os.path.join(overflow, "test-run-t9-g3.quality-gate.txt")
        _check("T-9.3 no orphan sidecar after oversize rejection",
               not os.path.exists(sidecar))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_group5_oversize_truncated_no_orphan_sidecar():
    """S-3 regression: 501 gated_files + oversize comment → rejected, no sidecar."""
    from scripts.ledger_append import append
    tmp = tempfile.mkdtemp(prefix="t9-g5-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")
    try:
        entry = _base_entry()
        entry["run_id"] = "test-run-t9-g5"
        entry["gated_files"] = [f"p/f{i}" for i in range(501)]
        entry["comment"] = "z" * 20000  # force >16 KiB even after truncation
        ok = append(ledger, entry, overflow_dir=overflow)
        _check("T-9.5 oversize-after-truncation rejected", ok is False)
        sidecar = os.path.join(overflow, "test-run-t9-g5.quality-gate.txt")
        _check("T-9.5 no orphan sidecar when line rejected post-truncation",
               not os.path.exists(sidecar))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_group4_reconciler_fallback():
    from scripts.ledger_append import append
    tmp = tempfile.mkdtemp(prefix="t9-g4-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")
    try:
        entry = _base_entry()
        entry["run_id"] = "test-run-t9-g4"
        entry["gated_files"] = [f"p/f{i}" for i in range(501)]
        append(ledger, entry, overflow_dir=overflow)
        with open(ledger) as f:
            row = json.loads(f.readline())

        # 4a: sidecar PRESENT → reconciler uses full list.
        files, unfalsifiable, warn = _simulated_reconciler_load(row, overflow)
        _check("T-9.4a sidecar present → full 501 paths recovered",
               len(files) == 501 and not unfalsifiable, f"got {len(files)} unfals={unfalsifiable}")

        # 4b: sidecar REMOVED → reconciler logs warning + marks unfalsifiable.
        sidecar = os.path.join(overflow, "test-run-t9-g4.quality-gate.txt")
        os.unlink(sidecar)
        files, unfalsifiable, warn = _simulated_reconciler_load(row, overflow)
        _check("T-9.4b sidecar absent → unfalsifiable flag set",
               unfalsifiable and warn is not None and files == [],
               f"unfals={unfalsifiable} warn={warn} files={len(files)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_group1_gated_files_truncation()
    test_group2_highest_finding_truncation()
    test_group3_oversize_rejection()
    test_group4_reconciler_fallback()
    test_group5_oversize_truncated_no_orphan_sidecar()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
