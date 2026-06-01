#!/usr/bin/env python3
"""S-1 regression: Brier grace filter fails CLOSED on unparseable `now`.

When `_parse_iso(now)` cannot parse, age cannot be evaluated, so the falsifiable
sample is empty — compute_brier returns {} rather than admitting (fail-open)
verdicts younger than the grace period.
"""
import os
import sys

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


def _entry(run_id, verdict="PASS", **kw):
    base = {
        "schema_version": 2, "run_id": run_id, "skill": "quality-gate",
        "artifact_type": "code", "verdict": verdict, "confidence": 0.9,
        "gated_files": ["src/foo.py"], "timestamp": "2026-01-01T00:00:00Z",
        "backfilled": False, "falsified": None, "falsified_by": None,
    }
    base.update(kw)
    return base


def test_unparseable_now_returns_empty():
    from scripts.reconcile_ledger import compute_brier
    # These entries WOULD qualify under a valid `now` far in the future.
    entries = [_entry("r-a", "PASS"), _entry("r-b", "FAIL")]
    # Sanity: with a valid `now` these are admitted (n==2).
    valid = compute_brier(entries, {}, now="2026-06-01T00:00:00Z")
    _check("S-1.0 sanity: valid now admits the sample (n==2)",
           valid.get("quality-gate", {}).get("n") == 2, f"got {valid}")
    # Fail-closed: unparseable now -> {}.
    out = compute_brier(entries, {}, now="not-a-date")
    _check("S-1.1 unparseable now -> {} (fail-closed)", out == {},
           f"got {out}")
    # Other unparseable forms.
    for bad in ["", "2026-13-99", "yesterday", None]:
        o = compute_brier(entries, {}, now=bad)
        _check(f"S-1.2 unparseable now ({bad!r}) -> {{}}", o == {}, f"got {o}")


def main():
    test_unparseable_now_returns_empty()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
