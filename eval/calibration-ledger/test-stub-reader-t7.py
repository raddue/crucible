#!/usr/bin/env python3
"""T-7: Tier-B stub-reader tolerance contract.

Phase 2 ("Tier expansion") gets to "5 gating skills append": quality-gate and
siege emit Tier A FULL entries; red-team, audit, inquisitor emit Tier B STUB
entries with the calibration fields EXPLICITLY null (keys present, value null)
per shared/ledger-append.md "Tier-B null semantics".

This is a reader-tolerance contract test: a minimal /ledger-style reduction must
NOT crash on null calibration fields and must NOT miscount the honest "caught N"
headline (would_have_shipped_without_gate == True, excluding backfilled and
excluding null-WHS Tier B stubs).

The test builds entries itself via append() into a temp ledger — it does NOT
touch the real .crucible/ledger/runs.jsonl.

Assertions:
  1. All 5 lines (2 Tier A + 3 Tier B) read without crashing on null fields.
  2. WHS "caught" count counts only Tier A True entries (null WHS excluded).
  3. Exactly 5 distinct skill values appear.
  4. Each Tier B entry has the calibration keys PRESENT with value null
     (the json line literally contains the key), not absent.
  5. Each Tier A entry has tier=="A" + a dict severity_histogram;
     each Tier B entry has tier=="B".
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


def _tier_a(run_id, skill, *, whs):
    """A full Tier A entry: severity_histogram a real dict, WHS a real bool."""
    fatal = 1 if whs else 0
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
        "gated_files": ["src/foo.py"],
        "findings_count": fatal,
        "severity_histogram": {"fatal": fatal, "significant": 0, "minor": 0, "nit": 0},
        "highest_finding": "boom" if whs else None,
        "would_have_shipped_without_gate": bool(whs),
        "rounds": 1,
        "timestamp": "2026-05-19T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": None,
        "predicted_falsifier": "<DEFERRED:pre-phase-7>",
    }


def _tier_b(run_id, skill):
    """A Tier B stub: calibration fields EXPLICITLY null (keys present)."""
    return {
        "schema_version": 1,
        "run_id": run_id,
        "skill": skill,
        "tier": "B",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": None,
        "artifact_hash": "b" * 64,
        "chunk_hash": None,
        "gated_files": ["src/bar.py"],
        "findings_count": None,
        "severity_histogram": None,
        "highest_finding": None,
        "would_have_shipped_without_gate": None,
        "rounds": None,
        "timestamp": "2026-05-19T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": None,
        "predicted_falsifier": None,
    }


def reduce_ledger(ledger_path):
    """Minimal /ledger-style reduction.

    Loads the JSONL, skips blank / partial-trailing lines, and computes:
      - total: count of parsed entries
      - caught: count of would_have_shipped_without_gate == True,
        EXCLUDING backfilled (and null-WHS entries naturally excluded since
        None is not True)
      - skills: the set of distinct skill values
    Must tolerate null calibration fields without crashing.
    """
    total = 0
    caught = 0
    skills = set()
    if not os.path.exists(ledger_path):
        return {"total": 0, "caught": 0, "skills": skills}
    with open(ledger_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # partial trailing line — skip
                continue
            total += 1
            skills.add(obj.get("skill"))
            if obj.get("would_have_shipped_without_gate") is True and not obj.get("backfilled"):
                caught += 1
    return {"total": total, "caught": caught, "skills": skills}


def main():
    from scripts.ledger_append import append, caller_dedup

    tmp = tempfile.mkdtemp(prefix="t7-stub-reader-")
    ledger = os.path.join(tmp, "runs.jsonl")
    overflow = os.path.join(tmp, "overflow")

    # 2 Tier A full entries (one with WHS True so "caught" is non-zero),
    # 3 Tier B stub entries. Distinct run_ids; honor caller_dedup discipline.
    entries = [
        _tier_a("r-qg", "quality-gate", whs=True),
        _tier_a("r-siege", "siege", whs=False),
        _tier_b("r-rt", "red-team"),
        _tier_b("r-audit", "audit"),
        _tier_b("r-inq", "inquisitor"),
    ]

    raw_b_lines = {}
    try:
        for e in entries:
            if caller_dedup(ledger, e["run_id"], e["skill"]):
                continue
            assert append(ledger, e, overflow_dir=overflow), f"append failed for {e['skill']}"

        # Capture the raw on-disk JSON line for each Tier B skill (assertion 3).
        with open(ledger, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("tier") == "B":
                    raw_b_lines[obj["skill"]] = line

        red = reduce_ledger(ledger)

        # 1. Reader does not crash on nulls and reads all 5 lines.
        _check("T-7.1 reducer reads all 5 entries without crashing",
               red["total"] == 5, f"total={red['total']}")

        # 2. WHS caught count = only Tier A True entries (null WHS excluded).
        _check("T-7.2 caught count is exactly 1 (Tier A True only; null WHS excluded)",
               red["caught"] == 1, f"caught={red['caught']}")

        # 3. Exactly 5 distinct skill values.
        _check("T-7.3 exactly 5 distinct skill values",
               len(red["skills"]) == 5, f"skills={sorted(red['skills'])}")

        # 4. Each Tier B entry has the calibration keys PRESENT with value null
        #    (the raw json line literally contains the key, value is JSON null).
        null_keys = [
            "severity_histogram", "highest_finding",
            "would_have_shipped_without_gate", "findings_count",
            "confidence", "chunk_hash", "rounds", "predicted_falsifier",
        ]
        for skill in ("red-team", "audit", "inquisitor"):
            line = raw_b_lines.get(skill, "")
            obj = json.loads(line) if line else {}
            for k in null_keys:
                present = k in obj
                is_null = obj.get(k, "MISSING") is None
                _check(f"T-7.4 Tier B {skill}: key '{k}' present and null",
                       present and is_null,
                       f"present={present} value={obj.get(k, 'MISSING')!r}")
            # explicit gated_files_truncated:0 and comment:null on Tier B stubs
            _check(f"T-7.4 Tier B {skill}: gated_files_truncated == 0",
                   obj.get("gated_files_truncated") == 0,
                   f"got {obj.get('gated_files_truncated')!r}")
            _check(f"T-7.4 Tier B {skill}: comment is null",
                   "comment" in obj and obj.get("comment") is None,
                   f"got {obj.get('comment', 'MISSING')!r}")

        # 5. Tier A => tier A + dict severity_histogram; Tier B => tier B.
        by_skill = {}
        with open(ledger, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                obj = json.loads(line)
                by_skill[obj["skill"]] = obj
        for skill in ("quality-gate", "siege"):
            obj = by_skill[skill]
            _check(f"T-7.5 Tier A {skill}: tier == 'A'", obj.get("tier") == "A")
            _check(f"T-7.5 Tier A {skill}: severity_histogram is a dict",
                   isinstance(obj.get("severity_histogram"), dict),
                   f"got {type(obj.get('severity_histogram')).__name__}")
        for skill in ("red-team", "audit", "inquisitor"):
            _check(f"T-7.5 Tier B {skill}: tier == 'B'",
                   by_skill[skill].get("tier") == "B")
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
