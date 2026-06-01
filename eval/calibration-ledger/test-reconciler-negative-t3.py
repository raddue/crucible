#!/usr/bin/env python3
"""T-3: reconciler negative case.

An injected candidate touching files with NO overlap with any entry's
`gated_files` produces NO falsification entry.
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
        "run_id": "run-N",
        "skill": "quality-gate",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": 0.9,
        "gated_files": ["src/unrelated.py"],
        "timestamp": "2026-01-01T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
    }
    base.update(kw)
    return base


def test_no_overlap_no_falsification():
    from scripts.reconcile_ledger import reconcile
    tmp = tempfile.mkdtemp(prefix="t3-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        _write_jsonl(ledger, [_entry(gated_files=["src/unrelated.py"])])
        candidates = [{
            "commit": "cafe1234",
            "touched_files": ["src/totally_other.py", "docs/readme.md"],
            "merge_time": "2026-01-05T00:00:00Z",
        }]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=20, lookback_days=30,
            now="2026-03-01T00:00:00Z",
        )
        _check("T-3.1 no falsification entries appended",
               len(appended) == 0, f"got {len(appended)}")
        # falsification file should be empty / absent
        exists = os.path.exists(fals)
        lines = []
        if exists:
            with open(fals, encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        _check("T-3.2 falsification.jsonl has no entries", len(lines) == 0,
               f"got {len(lines)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_no_overlap_no_falsification()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
