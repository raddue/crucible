#!/usr/bin/env python3
"""S-3 regression: manual attribution is authoritative and can CREATE a match.

A manual-attribution entry for a hash the algorithm does NOT match (candidate
touches unrelated files) STILL produces a falsification entry reflecting the
manual fields. Manual is read FIRST and overrides the algorithm.
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


def _write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_manual_creates_attribution():
    from scripts.reconcile_ledger import reconcile, ledger_entry_hash
    tmp = tempfile.mkdtemp(prefix="s3-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        # A ledger entry the algorithm would NOT match (candidate touches an
        # unrelated file). The entry itself need not even be present in the
        # ledger — manual attribution is keyed purely by hash.
        _write_jsonl(ledger, [{
            "schema_version": 2, "run_id": "rNoMatch", "skill": "quality-gate",
            "artifact_type": "code", "verdict": "PASS", "confidence": 0.9,
            "gated_files": ["src/unrelated.py"], "timestamp": "2026-01-01T00:00:00Z",
            "backfilled": False,
        }])
        h = ledger_entry_hash("rNoMatch", "quality-gate")
        _write_jsonl(manual, [{
            "ledger_entry_hash": h,
            "falsified": True,
            "confidence": "medium",
            "reasoning": "human spotted a missed false-positive",
            "cross_cut": False,
        }])
        # Candidate touches a file with NO overlap -> algorithm matches nothing.
        candidates = [{
            "commit": "deadbeef",
            "touched_files": ["src/totally_other.py"],
            "merge_time": "2026-02-01T00:00:00Z",
        }]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=20, lookback_days=30,
            now="2026-05-01T00:00:00Z",
        )
        match = [e for e in appended if e.get("ledger_entry_hash") == h]
        _check("S-3.1 manual entry produced despite no algorithm match",
               len(match) == 1, f"got {len(match)} of {len(appended)}")
        if match:
            e = match[0]
            _check("S-3.2 manual falsified preserved", e.get("falsified") is True,
                   f"got {e.get('falsified')}")
            _check("S-3.3 manual confidence preserved",
                   e.get("confidence") == "medium", f"got {e.get('confidence')}")
            _check("S-3.4 manual reasoning preserved",
                   "human spotted" in (e.get("reasoning") or ""),
                   f"got {e.get('reasoning')}")
        # No algorithmic entry should have been produced (no overlap).
        _check("S-3.5 only the manual entry produced", len(appended) == 1,
               f"got {len(appended)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_manual_creates_attribution()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
