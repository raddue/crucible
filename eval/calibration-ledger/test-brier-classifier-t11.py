#!/usr/bin/env python3
"""T-11: Brier verdict-type classifier + polarity.

Fixture A: 1 PASS (not falsified) + 1 FAIL (no predicate) + 1 each of
  STAGNATION / ESCALATED / ARCHITECTURAL / SUSTAINED_REGRESSION, all
  confidence:0.9, backfilled:false, cross_cut:false, artifact_type:"code",
  timestamps >30d before now.
  Assert: (a) denominator n == 2 (only PASS+FAIL); (b) both have actual=1;
  (c) brier == (0.9-1)**2 == 0.01 exact.

Fixture B: a single PASS, confidence:0.9, WITH a falsification.jsonl entry
  (cross_cut:false) marking it falsified within window -> actual=0 ->
  brier == (0.9-0)**2 == 0.81 exact when it's the only entry.
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


def _entry(run_id, verdict, **kw):
    base = {
        "schema_version": 2, "run_id": run_id, "skill": "quality-gate",
        "artifact_type": "code", "verdict": verdict, "confidence": 0.9,
        "gated_files": ["src/foo.py"],
        "timestamp": "2026-01-01T00:00:00Z",  # >30d before 2026-03-01
        "backfilled": False, "falsified": None, "falsified_by": None,
    }
    base.update(kw)
    return base


def test_fixture_a_classifier():
    from scripts.reconcile_ledger import compute_brier
    entries = [
        _entry("r-pass", "PASS"),
        _entry("r-fail", "FAIL"),
        _entry("r-stag", "STAGNATION"),
        _entry("r-esc", "ESCALATED"),
        _entry("r-arch", "ARCHITECTURAL"),
        _entry("r-reg", "SUSTAINED_REGRESSION"),
    ]
    brier = compute_brier(entries, {}, now="2026-03-01T00:00:00Z")
    qg = brier.get("quality-gate", {})
    _check("T-11.A1 denominator n == 2 (only PASS+FAIL)",
           qg.get("n") == 2, f"got {qg}")
    # actual=1 for both -> brier = (0.9-1)^2 = 0.01
    _check("T-11.A2 brier == 0.01 exact",
           qg.get("n") == 2 and abs(qg.get("brier", -1) - 0.01) < 1e-9,
           f"got {qg.get('brier')}")


def test_fixture_b_falsified_pass():
    from scripts.reconcile_ledger import compute_brier, ledger_entry_hash
    entries = [_entry("r-onlypass", "PASS")]
    h = ledger_entry_hash("r-onlypass", "quality-gate")
    # Reduced falsification map: this PASS was marked falsified, cross_cut false.
    fmap = {h: {"ledger_entry_hash": h, "falsified": True, "cross_cut": False}}
    brier = compute_brier(entries, fmap, now="2026-03-01T00:00:00Z")
    qg = brier.get("quality-gate", {})
    _check("T-11.B1 denominator n == 1", qg.get("n") == 1, f"got {qg}")
    # actual=0 -> brier = (0.9-0)^2 = 0.81
    _check("T-11.B2 brier == 0.81 exact",
           qg.get("n") == 1 and abs(qg.get("brier", -1) - 0.81) < 1e-9,
           f"got {qg.get('brier')}")


def main():
    test_fixture_a_classifier()
    test_fixture_b_falsified_pass()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
