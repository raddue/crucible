#!/usr/bin/env python3
"""Cross-cut detector bootstrap + denominator exclusion.

- cross_cut_threshold_from(sizes) returns 20 when < 30 samples.
- returns the p90 when >= 30 samples (a known list whose p90 != 20).
- A candidate with len(touched_files) > threshold is tagged cross_cut: true and
  is EXCLUDED from the Brier denominator.
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


def test_bootstrap_under_30():
    from scripts.reconcile_ledger import cross_cut_threshold_from
    sizes = [100] * 10  # only 10 samples
    t = cross_cut_threshold_from(sizes)
    _check("CC.1 <30 samples -> bootstrap 20", t == 20, f"got {t}")
    _check("CC.2 empty -> bootstrap 20", cross_cut_threshold_from([]) == 20,
           f"got {cross_cut_threshold_from([])}")


def test_p90_at_or_above_30():
    from scripts.reconcile_ledger import cross_cut_threshold_from
    # 30 samples: 1..30. p90 (nearest-rank: ceil(0.9*30)=27th value) = 27.
    # Whatever the exact percentile convention, it must be != 20 and within range.
    sizes = list(range(1, 31))
    t = cross_cut_threshold_from(sizes)
    _check("CC.3 >=30 samples -> p90 (not the bootstrap 20)", t != 20,
           f"got {t}")
    _check("CC.4 p90 in plausible upper range (>=25)", t >= 25, f"got {t}")


def test_cross_cut_tag_and_denominator_exclusion():
    from scripts.reconcile_ledger import reconcile, compute_brier, ledger_entry_hash, load_jsonl
    tmp = tempfile.mkdtemp(prefix="cc-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        # A forward PASS verdict, old enough to be falsifiable.
        entry = {
            "schema_version": 2, "run_id": "run-CC", "skill": "quality-gate",
            "artifact_type": "code", "verdict": "PASS", "confidence": 0.9,
            "gated_files": ["src/foo.py"], "timestamp": "2026-01-01T00:00:00Z",
            "backfilled": False, "falsified": None, "falsified_by": None,
        }
        _write_jsonl(ledger, [entry])
        threshold = 5
        # Candidate touching 6 files > threshold 5 -> cross_cut: true
        candidates = [{
            "commit": "bigfix",
            "touched_files": ["src/foo.py", "a", "b", "c", "d", "e"],
            "merge_time": "2026-01-08T00:00:00Z",
        }]
        appended = reconcile(
            ledger, fals, manual, candidates,
            cross_cut_threshold=threshold, lookback_days=30,
            now="2026-03-01T00:00:00Z",
        )
        match = [e for e in appended if e.get("ledger_entry_hash") ==
                 ledger_entry_hash("run-CC", "quality-gate")]
        _check("CC.5 cross-cut candidate still produces an entry",
               len(match) == 1, f"got {len(match)}")
        if match:
            _check("CC.6 entry tagged cross_cut: true",
                   match[0].get("cross_cut") is True,
                   f"got {match[0].get('cross_cut')}")

        # Now Brier: the cross-cut falsification must be excluded from the
        # denominator -> this skill has n == 0 falsifiable verdicts.
        from scripts.ledger_reduce import reduce
        fmap = reduce(fals)
        entries = load_jsonl(ledger)
        brier = compute_brier(entries, fmap, now="2026-03-01T00:00:00Z")
        n = brier.get("quality-gate", {}).get("n", None)
        _check("CC.7 cross-cut verdict excluded from Brier denominator (n==0)",
               n == 0 or "quality-gate" not in brier,
               f"got brier={brier}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_bootstrap_under_30()
    test_p90_at_or_above_30()
    test_cross_cut_tag_and_denominator_exclusion()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
