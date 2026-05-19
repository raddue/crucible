#!/usr/bin/env python3
"""T-2: L-2 caller-side dedup discipline.

Invariant L-2 says every ledger entry has a unique (run_id, skill) pair.
`scripts.ledger_append.caller_dedup` is the helper Tier A skills MUST call
before append() to honor this. The append helper itself does NOT scan
runs.jsonl for prior entries.

Assertions:
  1. caller_dedup returns False for fresh ledger (no prior entry).
  2. After append, caller_dedup returns True for matching (run_id, skill).
  3. caller_dedup returns False for matching run_id but different skill.
  4. caller_dedup returns False for different run_id with same skill.
  5. Discipline pattern: skill checks caller_dedup, skips append on dup,
     no second line lands.
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


def _entry(run_id="r1", skill="quality-gate"):
    return {
        "schema_version": 1,
        "run_id": run_id,
        "skill": skill,
        "tier": "A",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": 0.9,
        "artifact_hash": "a" * 64,
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


def main():
    from scripts.ledger_append import append, caller_dedup

    tmp = tempfile.mkdtemp(prefix="t2-dedup-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")
    try:
        # 1: fresh ledger
        _check("T-2.1 caller_dedup False on missing ledger",
               caller_dedup(ledger, "r1", "quality-gate") is False)

        # 2: append, then dedup returns True
        assert append(ledger, _entry("r1", "quality-gate"), overflow_dir=overflow)
        _check("T-2.2 caller_dedup True after matching append",
               caller_dedup(ledger, "r1", "quality-gate") is True)

        # 3: same run_id, different skill
        _check("T-2.3 caller_dedup False for same run_id different skill",
               caller_dedup(ledger, "r1", "siege") is False)

        # 4: different run_id, same skill
        _check("T-2.4 caller_dedup False for different run_id same skill",
               caller_dedup(ledger, "r2", "quality-gate") is False)

        # 5: discipline pattern — caller checks before appending
        def emit_with_dedup(e):
            if caller_dedup(ledger, e["run_id"], e["skill"]):
                return False
            return append(ledger, e, overflow_dir=overflow)

        # Try to double-emit same (r3, quality-gate)
        e = _entry("r3", "quality-gate")
        first = emit_with_dedup(e)
        second = emit_with_dedup(e)
        _check("T-2.5 discipline: first emit succeeds", first is True)
        _check("T-2.5 discipline: second emit skipped via dedup", second is False)
        # Verify only one r3 line in ledger
        r3_count = 0
        with open(ledger) as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("run_id") == "r3" and obj.get("skill") == "quality-gate":
                    r3_count += 1
        _check("T-2.5 ledger has exactly one (r3, quality-gate) line",
               r3_count == 1, f"got {r3_count}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
