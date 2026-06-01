#!/usr/bin/env python3
"""T-6: manual attribution override.

A manual-attribution.jsonl entry keyed by ledger_entry_hash overrides the
algorithm's attribution. Here the algorithm would falsify (high confidence)
but the manual override says NOT falsified (and a different confidence). Manual
must win.
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


def _entry(**kw):
    base = {
        "schema_version": 2,
        "run_id": "run-M",
        "skill": "quality-gate",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": 0.9,
        "gated_files": ["src/foo.py"],
        "timestamp": "2026-01-01T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
    }
    base.update(kw)
    return base


def test_manual_override_wins():
    from scripts.reconcile_ledger import reconcile, ledger_entry_hash
    tmp = tempfile.mkdtemp(prefix="t6-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        h = ledger_entry_hash("run-M", "quality-gate")
        _write_jsonl(ledger, [_entry(run_id="run-M", skill="quality-gate",
                                     gated_files=["src/foo.py"])])
        # Manual override: human reviewed, says this verdict was NOT a false
        # positive (not falsified), overriding the algorithm.
        _write_jsonl(manual, [{
            "ledger_entry_hash": h,
            "falsified": False,
            "confidence": "high",
            "reasoning": "human-reviewed: fix unrelated to gated change",
            "cross_cut": False,
        }])
        # Candidate that WOULD trigger an algorithmic falsification (overlap +
        # within 14d).
        candidates = [{
            "commit": "deadbeef",
            "touched_files": ["src/foo.py"],
            "merge_time": "2026-01-08T00:00:00Z",
        }]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=20, lookback_days=30,
            now="2026-03-01T00:00:00Z",
        )
        # The manual override should be emitted (and win) for this hash.
        match = [e for e in appended if e.get("ledger_entry_hash") == h]
        _check("T-6.1 an entry exists for the overridden hash",
               len(match) == 1, f"got {len(match)}")
        if match:
            e = match[0]
            _check("T-6.2 manual override wins: falsified == False",
                   e.get("falsified") is False, f"got {e.get('falsified')}")
            _check("T-6.3 manual confidence wins",
                   e.get("confidence") == "high", f"got {e.get('confidence')}")
            _check("T-6.4 manual reasoning preserved",
                   "human-reviewed" in (e.get("reasoning") or ""),
                   f"got {e.get('reasoning')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_manual_override_wins()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
