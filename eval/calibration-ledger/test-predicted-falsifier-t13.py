#!/usr/bin/env python3
"""T-13: predicted_falsifier — unparseable predicate falls through.

Phase 7 (design §3a). A free-form (non-canonical-grammar) predicate:
  - is classified `unparseable_predicate: true`;
  - does NOT auto-falsify (the predicate pass appends nothing for it);
  - leaves the file-intersection walkback's outcome unaltered;
  - is counted in `/ledger`'s per-skill `unparseable_predicate_rate`.

# Path is illustrative; T-13 fixtures use synthetic paths to exercise the predicate
# parser regardless of whether the path exists in the repo.
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
        "predicted_falsifier": None,
    }
    base.update(kw)
    return base


def test_unparseable_no_autofalsify():
    from scripts.reconcile_ledger import reconcile_predicates
    tmp = tempfile.mkdtemp(prefix="t13-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(
            run_id="run-vague", skill="quality-gate",
            gated_files=["src/foo.py"],
            predicted_falsifier="this will probably regress someday",
        )]
        # A candidate that DOES touch the gated file — proving the predicate pass
        # does not fire on it (it would only fire a parseable predicate).
        candidates = [{
            "commit": "abad1dea",
            "touched_files": ["src/foo.py"],
            "merge_time": "2026-01-05T00:00:00Z",
        }]
        classifications, appended = reconcile_predicates(
            entries, candidates, fals, now="2026-03-01T00:00:00Z")
        _check("T-13.1 unparseable predicate appends NO falsification",
               len(appended) == 0, f"got {len(appended)}")
        unp = [c for c in classifications if c.get("unparseable")]
        _check("T-13.2 classified unparseable_predicate:true",
               len(unp) == 1 and unp[0].get("parseable") is False
               and unp[0].get("sentinel") is False,
               f"got {classifications}")
        # falsification.jsonl must be empty (or absent) — predicate pass wrote nothing.
        wrote = os.path.exists(fals) and os.path.getsize(fals) > 0
        _check("T-13.3 falsification.jsonl untouched by predicate pass",
               not wrote, f"file non-empty: {wrote}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_walkback_unaltered():
    """The existing walkback still falsifies via file-intersection on an
    unparseable-predicate verdict — the predicate pass does not suppress it."""
    from scripts.reconcile_ledger import reconcile
    tmp = tempfile.mkdtemp(prefix="t13-wb-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        with open(ledger, "w", encoding="utf-8") as f:
            f.write(json.dumps(_entry(
                run_id="run-vague2", skill="quality-gate",
                gated_files=["src/foo.py"],
                predicted_falsifier="vague prose, not grammar",
                timestamp="2026-01-01T00:00:00Z",
            )) + "\n")
        candidates = [{
            "commit": "deadc0de",
            "touched_files": ["src/foo.py"],
            "merge_time": "2026-01-08T00:00:00Z",
        }]
        wb = reconcile(ledger, fals, manual, candidates,
                       cross_cut_threshold=20, now="2026-03-01T00:00:00Z")
        _check("T-13.4 walkback still falsifies the verdict",
               len(wb) == 1 and wb[0].get("falsified") is True
               and wb[0].get("via") == "walkback",
               f"got {wb}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ledger_unparseable_rate():
    """/ledger surfaces the unparseable predicate in the per-skill rate."""
    from scripts.render_ledger import predicate_rates
    entries = [
        _entry(run_id="r1", skill="quality-gate",
               predicted_falsifier="fix touching src/foo.py within 30d"),   # parseable
        _entry(run_id="r2", skill="quality-gate",
               predicted_falsifier="hand-wavy future breakage"),            # unparseable
        _entry(run_id="r3", skill="quality-gate",
               predicted_falsifier="<DEFERRED:pre-phase-7>"),               # sentinel (excluded)
        _entry(run_id="r4", skill="quality-gate", predicted_falsifier=None),  # null (not a predicate)
    ]
    rates = predicate_rates(entries, {}, now="2026-03-01T00:00:00Z")
    qg = rates.get("quality-gate", {})
    _check("T-13.5 total non-null predicates excludes sentinel + null (==2)",
           qg.get("total_non_null") == 2, f"got {qg}")
    _check("T-13.6 unparseable_rate == 1/2 == 0.5",
           abs(qg.get("unparseable_rate", -1) - 0.5) < 1e-9, f"got {qg}")
    _check("T-13.7 parseable denominator == 1 (sentinel + unparseable excluded)",
           qg.get("parseable") == 1, f"got {qg}")
    _check("T-13.8 no predicate fired -> hit_rate 0.0",
           qg.get("hit_count") == 0 and qg.get("hit_rate") == 0.0, f"got {qg}")


def test_referencing_form_uncheckable_not_in_hitrate():
    """Regression (adversarial Finding 2): `referencing`/`hash` forms parse but
    aren't auto-checkable at v1. They must NOT sit in the hit-rate denominator
    (which would structurally drag siege's rate to 0 — siege is steered toward
    `referencing`). They still count in total_non_null (unparseable_rate denom)
    but are NOT unparseable."""
    from scripts.render_ledger import predicate_rates
    entries = [
        _entry(run_id="t1", skill="siege",
               predicted_falsifier="fix touching src/foo.py within 30d"),   # touching -> hit-rate denom
        _entry(run_id="t2", skill="siege",
               predicted_falsifier="CVE referencing token-refresh within 90d"),  # uncheckable
        _entry(run_id="t3", skill="siege",
               predicted_falsifier="revert of artifact_hash=deadbeef within 30d"),  # uncheckable
    ]
    rates = predicate_rates(entries, {}, now="2026-03-01T00:00:00Z")
    sg = rates.get("siege", {})
    _check("T-13.9 parseable (hit-rate denom) == 1 (touching only)",
           sg.get("parseable") == 1, f"got {sg}")
    _check("T-13.10 uncheckable == 2 (referencing + hash)",
           sg.get("uncheckable") == 2, f"got {sg}")
    _check("T-13.11 total_non_null == 3, unparseable == 0",
           sg.get("total_non_null") == 3 and sg.get("unparseable") == 0,
           f"got {sg}")
    _check("T-13.12 unparseable_rate == 0.0 (none are free-form prose)",
           sg.get("unparseable_rate") == 0.0, f"got {sg}")


def main():
    test_unparseable_no_autofalsify()
    test_walkback_unaltered()
    test_ledger_unparseable_rate()
    test_referencing_form_uncheckable_not_in_hitrate()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
