#!/usr/bin/env python3
"""T-2: reconciler positive case.

A forward ledger entry (backfilled:false, artifact_type:code) whose `gated_files`
intersect an injected candidate's `touched_files`, with the candidate `merge_time`
within 14 days AFTER the entry's `timestamp`, gets falsified with confidence: high.

Drives the PURE reconcile() with an INJECTED candidate list — no real git.
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
        "run_id": "run-X",
        "skill": "quality-gate",
        "tier": "A",
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


def test_positive_high_confidence():
    from scripts.reconcile_ledger import reconcile, ledger_entry_hash
    tmp = tempfile.mkdtemp(prefix="t2-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        _write_jsonl(ledger, [_entry(run_id="run-X", skill="quality-gate",
                                     gated_files=["src/foo.py"],
                                     timestamp="2026-01-01T00:00:00Z")])
        candidates = [{
            "commit": "deadbeef",
            "touched_files": ["src/foo.py", "src/bar.py"],
            # 7 days after the verdict -> within 14d -> high
            "merge_time": "2026-01-08T00:00:00Z",
        }]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=20, lookback_days=30,
            now="2026-03-01T00:00:00Z",
        )
        _check("T-2.1 exactly one falsification entry appended",
               len(appended) == 1, f"got {len(appended)}")
        if appended:
            e = appended[0]
            expect_hash = ledger_entry_hash("run-X", "quality-gate")
            _check("T-2.2 entry hashed by run_id+skill",
                   e.get("ledger_entry_hash") == expect_hash,
                   f"got {e.get('ledger_entry_hash')}")
            _check("T-2.3 falsified == true", e.get("falsified") is True,
                   f"got {e.get('falsified')}")
            _check("T-2.4 confidence == high", e.get("confidence") == "high",
                   f"got {e.get('confidence')}")
            _check("T-2.5 falsified_by.commit recorded",
                   (e.get("falsified_by") or {}).get("commit") == "deadbeef",
                   f"got {e.get('falsified_by')}")
            _check("T-2.6 cross_cut false", e.get("cross_cut") is False,
                   f"got {e.get('cross_cut')}")
        # And it should have been written to the falsification file
        with open(fals, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        _check("T-2.7 falsification.jsonl has one line", len(lines) == 1,
               f"got {len(lines)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_positive_high_confidence()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
