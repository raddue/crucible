#!/usr/bin/env python3
"""S-2 regression: walkback falls through to next-earliest UNSEEN verdict.

E1(Jan) + E2(Feb), distinct hashes, both gate src/foo.py. candA + candB both
touch src/foo.py and post-date both. Two distinct falsification entries must be
produced — one for E1's hash, one for E2's — not just one (which would deflate
the false-positive count and bias Brier optimistic).
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


def _entry(run_id, ts):
    return {
        "schema_version": 2, "run_id": run_id, "skill": "quality-gate",
        "artifact_type": "code", "verdict": "PASS", "confidence": 0.9,
        "gated_files": ["src/foo.py"], "timestamp": ts,
        "backfilled": False, "falsified": None, "falsified_by": None,
    }


def test_two_fixes_two_verdicts():
    from scripts.reconcile_ledger import reconcile, ledger_entry_hash
    tmp = tempfile.mkdtemp(prefix="s2-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        _write_jsonl(ledger, [
            _entry("E1", "2026-01-01T00:00:00Z"),  # earliest
            _entry("E2", "2026-02-01T00:00:00Z"),
        ])
        candidates = [
            {"commit": "candA", "touched_files": ["src/foo.py"],
             "merge_time": "2026-03-01T00:00:00Z"},
            {"commit": "candB", "touched_files": ["src/foo.py"],
             "merge_time": "2026-03-02T00:00:00Z"},
        ]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=20, lookback_days=30,
            now="2026-05-01T00:00:00Z",
        )
        hashes = {e["ledger_entry_hash"] for e in appended}
        hE1 = ledger_entry_hash("E1", "quality-gate")
        hE2 = ledger_entry_hash("E2", "quality-gate")
        _check("S-2.1 exactly two falsification entries", len(appended) == 2,
               f"got {len(appended)}")
        _check("S-2.2 E1 hash falsified", hE1 in hashes, f"got {hashes}")
        _check("S-2.3 E2 hash falsified", hE2 in hashes, f"got {hashes}")
        # candA (earlier merge) should claim E1 (earliest), candB falls through
        # to E2.
        by_commit = {e["falsified_by"]["commit"]: e["ledger_entry_hash"]
                     for e in appended}
        _check("S-2.4 candA -> E1 (earliest unseen)",
               by_commit.get("candA") == hE1, f"got {by_commit}")
        _check("S-2.5 candB -> E2 (next-earliest unseen)",
               by_commit.get("candB") == hE2, f"got {by_commit}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_two_fixes_two_verdicts()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
