#!/usr/bin/env python3
"""T-12: predicted_falsifier — parseable predicate fires.

Phase 7 (design §3a). Exercises the reconciler's second pass:
  - A canonical-grammar predicate (`fix touching <file> within Nd`) that a later
    candidate FIRES → a falsification entry with `via: "predicate"`, confidence:high.
  - Precedence: when BOTH the file-intersection walkback AND the predicate fire on
    the same verdict, the predicate-sourced entry wins under L-9 (latest-wins).
  - Sentinel `<DEFERRED:pre-phase-7>` is excluded from BOTH rate denominators.
  - L-10 completion: a FAIL whose predicate fires flips `compute_brier` actual 1→0.

# Path is illustrative; T-12 fixtures use synthetic paths to exercise the predicate
# parser regardless of whether the path exists in the repo.
"""
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
        "gated_files": ["src/auth/token.ts"],
        "timestamp": "2026-01-01T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "predicted_falsifier": None,
    }
    base.update(kw)
    return base


def test_parse_grammar():
    from scripts.reconcile_ledger import parse_predicate
    # touching form
    p = parse_predicate("fix touching src/auth/token.ts within 30d")
    _check("T-12.1 touching form parses",
           p is not None and p.get("form") == "touching"
           and p.get("files") == ["src/auth/token.ts"] and p.get("within_days") == 30,
           f"got {p}")
    # multi-file + glob
    p = parse_predicate("hotfix touching src/auth/*,src/api/login.ts within 14d")
    _check("T-12.2 multi-file + glob parses",
           p is not None and p.get("files") == ["src/auth/*", "src/api/login.ts"]
           and p.get("within_days") == 14,
           f"got {p}")
    # referencing form
    p = parse_predicate("CVE referencing token-refresh within 90d")
    _check("T-12.3 referencing form parses",
           p is not None and p.get("form") == "referencing"
           and p.get("token") == "token-refresh",
           f"got {p}")
    # out-of-range N -> parse failure
    _check("T-12.4 N>365 is a parse failure",
           parse_predicate("fix touching src/foo.py within 999d") is None)
    # free-form -> parse failure
    _check("T-12.5 free-form is a parse failure",
           parse_predicate("something will probably break later") is None)


def test_predicate_fires_high():
    from scripts.reconcile_ledger import reconcile_predicates, ledger_entry_hash
    tmp = tempfile.mkdtemp(prefix="t12-fire-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(
            run_id="run-fire", skill="quality-gate",
            gated_files=["src/auth/token.ts"],
            predicted_falsifier="fix touching src/auth/token.ts within 30d",
            timestamp="2026-01-01T00:00:00Z",
        )]
        candidates = [{
            "commit": "cafe1234",
            "touched_files": ["src/auth/token.ts", "src/auth/refresh.ts"],
            "merge_time": "2026-01-11T00:00:00Z",  # 10d after -> within 30d
        }]
        classifications, appended = reconcile_predicates(
            entries, candidates, fals, now="2026-03-01T00:00:00Z")
        _check("T-12.6 exactly one predicate falsification appended",
               len(appended) == 1, f"got {len(appended)}")
        if appended:
            e = appended[0]
            _check("T-12.7 falsified true via predicate, confidence high",
                   e.get("falsified") is True and e.get("via") == "predicate"
                   and e.get("confidence") == "high"
                   and (e.get("falsified_by") or {}).get("via") == "predicate",
                   f"got {e}")
            _check("T-12.8 keyed by run_id+skill",
                   e.get("ledger_entry_hash")
                   == ledger_entry_hash("run-fire", "quality-gate"),
                   f"got {e.get('ledger_entry_hash')}")
        parseable = [c for c in classifications if c.get("parseable")]
        _check("T-12.9 classified parseable + fired",
               len(parseable) == 1 and parseable[0].get("fired") is True,
               f"got {classifications}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_glob_does_not_cross_slash():
    """Regression (adversarial Finding 1): a `*` glob matches within ONE path
    segment and must NOT cross `/`. `src/auth/*` fires on src/auth/token.ts but
    NOT on src/auth/sub/deep.ts — else an unrelated deep-tree fix would silently
    credit/flip an unrelated verdict (corrupting Brier via the FAIL-flip)."""
    from scripts.reconcile_ledger import reconcile_predicates
    tmp = tempfile.mkdtemp(prefix="t12-glob-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(
            run_id="run-glob", skill="quality-gate",
            gated_files=["src/auth/token.ts"],
            predicted_falsifier="fix touching src/auth/* within 30d",
            timestamp="2026-01-01T00:00:00Z",
        )]
        # Candidate touches ONLY a deeper path that a cross-/ glob would wrongly
        # match. Correct semantics: no fire.
        deep = [{"commit": "deadbeef",
                 "touched_files": ["src/auth/sub/deep/token.ts"],
                 "merge_time": "2026-01-10T00:00:00Z"}]
        _, appended = reconcile_predicates(entries, deep, fals,
                                           now="2026-03-01T00:00:00Z")
        _check("T-12.17 glob `src/auth/*` does NOT fire on deeper src/auth/sub/..",
               len(appended) == 0, f"got {len(appended)}")
        # Direct child IS matched.
        os.path.exists(fals) and os.remove(fals)
        direct = [{"commit": "cafebabe",
                   "touched_files": ["src/auth/session.ts"],
                   "merge_time": "2026-01-10T00:00:00Z"}]
        _, appended2 = reconcile_predicates(entries, direct, fals,
                                            now="2026-03-01T00:00:00Z")
        _check("T-12.18 glob `src/auth/*` fires on direct child src/auth/session.ts",
               len(appended2) == 1, f"got {len(appended2)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sentinel_excluded():
    from scripts.reconcile_ledger import reconcile_predicates
    tmp = tempfile.mkdtemp(prefix="t12-sentinel-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(
            run_id="run-sentinel", skill="quality-gate",
            predicted_falsifier="<DEFERRED:pre-phase-7>",
        )]
        classifications, appended = reconcile_predicates(
            entries, [], fals, now="2026-03-01T00:00:00Z")
        _check("T-12.10 sentinel appends no falsification", len(appended) == 0,
               f"got {len(appended)}")
        sent = [c for c in classifications if c.get("sentinel")]
        _check("T-12.11 sentinel excluded from both rate buckets",
               len(sent) == 1 and sent[0].get("parseable") is False
               and sent[0].get("unparseable") is False,
               f"got {classifications}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_predicate_beats_walkback():
    """When both walkback and predicate fire on the same verdict, the predicate
    entry wins under L-9 (it is appended AFTER the walkback entry)."""
    from scripts.reconcile_ledger import (
        reconcile, reconcile_predicates, ledger_entry_hash)
    from scripts.ledger_reduce import reduce as _reduce
    tmp = tempfile.mkdtemp(prefix="t12-prec-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        with open(ledger, "w", encoding="utf-8") as f:
            import json
            f.write(json.dumps(_entry(
                run_id="run-both", skill="quality-gate",
                gated_files=["src/auth/token.ts"],
                predicted_falsifier="fix touching src/auth/token.ts within 30d",
                timestamp="2026-01-01T00:00:00Z",
            )) + "\n")
        candidates = [{
            "commit": "beef5678",
            "touched_files": ["src/auth/token.ts"],
            "merge_time": "2026-01-08T00:00:00Z",  # within 14d -> walkback would be high (capped medium)
        }]
        # Pass 1: walkback (caps confidence at medium, via:walkback)
        wb = reconcile(ledger, fals, manual, candidates,
                       cross_cut_threshold=20, now="2026-03-01T00:00:00Z")
        _check("T-12.12 walkback capped at medium",
               len(wb) == 1 and wb[0].get("confidence") == "medium"
               and wb[0].get("via") == "walkback",
               f"got {wb}")
        # Pass 2: predicate (appended after -> wins under L-9)
        from scripts.reconcile_ledger import load_jsonl
        reconcile_predicates(load_jsonl(ledger), candidates, fals,
                             now="2026-03-01T00:00:00Z")
        reduced = _reduce(fals)
        h = ledger_entry_hash("run-both", "quality-gate")
        rec = reduced.get(h, {})
        _check("T-12.13 predicate wins precedence (via:predicate, high)",
               rec.get("via") == "predicate" and rec.get("confidence") == "high",
               f"got {rec}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_side_brier_flip():
    """L-10 completion: a FAIL whose predicate fired flips actual 1->0."""
    from scripts.reconcile_ledger import compute_brier, ledger_entry_hash
    h = ledger_entry_hash("r-fail", "quality-gate")
    entries = [_entry(run_id="r-fail", skill="quality-gate", verdict="FAIL",
                      confidence=0.9, predicted_falsifier=None)]
    # No falsification -> FAIL defaults actual=1 -> brier (0.9-1)^2 = 0.01
    b0 = compute_brier(entries, {}, now="2026-03-01T00:00:00Z")
    _check("T-12.14 FAIL with no fired predicate -> brier 0.01",
           abs(b0.get("quality-gate", {}).get("brier", -1) - 0.01) < 1e-9,
           f"got {b0}")
    # Predicate-sourced falsification (via:predicate) -> FAIL actual=0 -> 0.81
    fmap = {h: {"ledger_entry_hash": h, "falsified": True, "cross_cut": False,
                "via": "predicate"}}
    b1 = compute_brier(entries, fmap, now="2026-03-01T00:00:00Z")
    _check("T-12.15 FAIL with fired predicate -> brier 0.81 (actual flipped 1->0)",
           abs(b1.get("quality-gate", {}).get("brier", -1) - 0.81) < 1e-9,
           f"got {b1}")
    # A walkback-only falsification (no via:predicate) must NOT flip a FAIL.
    fmap_wb = {h: {"ledger_entry_hash": h, "falsified": True, "cross_cut": False,
                   "via": "walkback"}}
    b2 = compute_brier(entries, fmap_wb, now="2026-03-01T00:00:00Z")
    _check("T-12.16 FAIL with walkback-only falsification stays actual=1 (brier 0.01)",
           abs(b2.get("quality-gate", {}).get("brier", -1) - 0.01) < 1e-9,
           f"got {b2}")


def main():
    test_parse_grammar()
    test_predicate_fires_high()
    test_glob_does_not_cross_slash()
    test_sentinel_excluded()
    test_predicate_beats_walkback()
    test_fail_side_brier_flip()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
