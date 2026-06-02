#!/usr/bin/env python3
"""v1.1 follow-ups (#341 / #342 / #343).

#343 — auto-check the `hash` (verb-gated revert-only) and `referencing`
       predicted_falsifier forms; both move out of `uncheckable` into the
       hit-rate denominator. Pure matchers `_hash_fired` / `_referencing_fired`
       + shared `predicate_checkable`.
#342 — `signal_type: bad_implementation` non-code calibration signal: threaded
       through the manual-attribution pass and admitted into `compute_brier`.
#341 — Tier B stub emission wiring in verify / test-coverage / review-feedback
       (prose lint).

Mirrors eval/calibration-ledger style: pure functions, synthetic fixtures.
"""
import os
import re
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
        "artifact_hash": "deadbeefcafe0000",
        "gated_files": ["src/auth.py"],
        "timestamp": "2026-01-01T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "predicted_falsifier": None,
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# #343 hash — verb-gated revert-only (V-1)                                     #
# --------------------------------------------------------------------------- #

def test_hash_fired():
    from scripts.reconcile_ledger import (
        _hash_fired, _parse_iso, parse_predicate, reconcile_predicates,
        ledger_entry_hash, load_jsonl,
    )
    edt = _parse_iso("2026-01-01T00:00:00Z")
    gated = ["src/auth.py"]

    # V-1a fires: revert of the verdict's artifact, touching a gated file, in-window.
    p = parse_predicate("revert of artifact_hash=deadbeef within 30d")
    rc = [{"commit": "rev1", "touched_files": ["src/auth.py"],
           "merge_time": "2026-01-11T00:00:00Z", "message": 'Revert "x"'}]
    _check("V-1a hash revert in-window touching gated file fires",
           _hash_fired(p, edt, rc, gated, "deadbeefcafe0000") is not None)

    # V-1b verb gate: a non-revert verb never fires even with a matching candidate.
    pf = parse_predicate("fix of artifact_hash=deadbeef within 30d")
    _check("V-1b non-revert verb (fix) does NOT fire",
           _hash_fired(pf, edt, rc, gated, "deadbeefcafe0000") is None)

    # hash-bind: a predicate naming a DIFFERENT artifact than its verdict cannot fire.
    pother = parse_predicate("revert of artifact_hash=feedface within 30d")
    _check("V-1b' hash naming a different artifact does NOT fire (bind)",
           _hash_fired(pother, edt, rc, gated, "deadbeefcafe0000") is None)
    _check("V-1b'' null entry artifact_hash → bind fails → no fire",
           _hash_fired(p, edt, rc, gated, None) is None)

    # V-1c `without touching` exclusion.
    pw = parse_predicate("revert of artifact_hash=deadbeef without touching src/tests/* within 30d")
    rc_tests = [{"commit": "rev2", "touched_files": ["src/tests/x.py", "src/auth.py"],
                 "merge_time": "2026-01-11T00:00:00Z", "message": 'Revert "x"'}]
    _check("V-1c without-touching: candidate touching an excluded path does NOT fire",
           _hash_fired(pw, edt, rc_tests, gated, "deadbeefcafe0000") is None)
    rc_clean = [{"commit": "rev3", "touched_files": ["src/auth.py"],
                 "merge_time": "2026-01-11T00:00:00Z", "message": 'Revert "x"'}]
    _check("V-1c' without-touching: candidate touching only gated (not excluded) fires",
           _hash_fired(pw, edt, rc_clean, gated, "deadbeefcafe0000") is not None)

    # V-1d out-of-window revert candidate → no fire.
    rc_old = [{"commit": "rev4", "touched_files": ["src/auth.py"],
               "merge_time": "2026-03-01T00:00:00Z", "message": 'Revert "x"'}]
    _check("V-1d out-of-window revert does NOT fire",
           _hash_fired(p, edt, rc_old, gated, "deadbeefcafe0000") is None)

    # V-1e end-to-end: reconcile_predicates with revert_candidates appends via:predicate.
    tmp = tempfile.mkdtemp(prefix="v1-hash-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(run_id="r-hash", artifact_hash="deadbeefcafe0000",
                          gated_files=["src/auth.py"],
                          predicted_falsifier="revert of artifact_hash=deadbeef within 30d")]
        _, appended = reconcile_predicates(
            entries, [], fals, now="2026-03-01T00:00:00Z", revert_candidates=rc)
        ok = len(appended) == 1 and appended[0].get("via") == "predicate" \
            and appended[0].get("confidence") == "high"
        _check("V-1e end-to-end revert-hash → via:predicate, high", ok, f"got {appended}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# #343 referencing — word-boundary (V-2)                                       #
# --------------------------------------------------------------------------- #

def test_referencing_fired():
    from scripts.reconcile_ledger import (
        _referencing_fired, _parse_iso, parse_predicate, reconcile_predicates,
    )
    edt = _parse_iso("2026-01-01T00:00:00Z")

    # V-2a token matches message in-window → fired.
    p = parse_predicate("cve referencing token-refresh within 90d")
    rc = [{"commit": "c1", "message": "hotfix token-refresh leak",
           "merge_time": "2026-01-20T00:00:00Z"}]
    _check("V-2a referencing token in message fires",
           _referencing_fired(p, edt, rc) is not None)

    # V-2b token absent / out-of-window → no fire.
    rc_absent = [{"commit": "c2", "message": "unrelated change",
                  "merge_time": "2026-01-20T00:00:00Z"}]
    _check("V-2b token absent → no fire", _referencing_fired(p, edt, rc_absent) is None)
    rc_late = [{"commit": "c3", "message": "token-refresh", "merge_time": "2026-09-01T00:00:00Z"}]
    _check("V-2b' out-of-window → no fire", _referencing_fired(p, edt, rc_late) is None)

    # V-2c word-boundary: `auth` must not match `authentication`.
    pa = parse_predicate("fix referencing auth within 30d")
    _check("V-2c `auth` does NOT fire on 'refactor authentication'",
           _referencing_fired(pa, edt, [{"commit": "c4", "message": "refactor authentication",
                                         "merge_time": "2026-01-10T00:00:00Z"}]) is None)
    _check("V-2c' `auth` fires on 'fix auth bug'",
           _referencing_fired(pa, edt, [{"commit": "c5", "message": "fix auth bug",
                                        "merge_time": "2026-01-10T00:00:00Z"}]) is not None)

    # issue/PR tokens that start with a non-word char (the \b defect).
    ph = parse_predicate("fix referencing #341 within 30d")
    _check("V-2c'' `#341` fires on 'closes #341' but not '#3419'",
           _referencing_fired(ph, edt, [{"commit": "c6", "message": "closes #341",
                                        "merge_time": "2026-01-10T00:00:00Z"}]) is not None
           and _referencing_fired(ph, edt, [{"commit": "c7", "message": "ref #3419",
                                            "merge_time": "2026-01-10T00:00:00Z"}]) is None)

    # V-2d case-insensitivity.
    pt = parse_predicate("cve referencing Token-Refresh within 90d")
    _check("V-2d case-insensitive token match",
           _referencing_fired(pt, edt, [{"commit": "c8", "message": "patch token-refresh",
                                        "merge_time": "2026-01-10T00:00:00Z"}]) is not None)

    # V-2e end-to-end via reconcile_predicates(reference_candidates=...).
    tmp = tempfile.mkdtemp(prefix="v2-ref-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        entries = [_entry(run_id="r-ref",
                          predicted_falsifier="cve referencing token-refresh within 90d")]
        _, appended = reconcile_predicates(
            entries, [], fals, now="2026-06-01T00:00:00Z", reference_candidates=rc)
        _check("V-2e end-to-end referencing → via:predicate",
               len(appended) == 1 and appended[0].get("via") == "predicate", f"got {appended}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# #343 dispatch + render (V-3)                                                 #
# --------------------------------------------------------------------------- #

def test_dispatch_and_render():
    from scripts.reconcile_ledger import (
        parse_predicate, predicate_checkable, reconcile_predicates,
    )
    from scripts.render_ledger import predicate_rates

    # V-3a predicate_checkable.
    _check("V-3a touching checkable",
           predicate_checkable(parse_predicate("fix touching a.py within 30d")) is True)
    _check("V-3a referencing checkable",
           predicate_checkable(parse_predicate("cve referencing tok within 30d")) is True)
    _check("V-3a revert-hash checkable",
           predicate_checkable(parse_predicate("revert of artifact_hash=deadbeef within 30d")) is True)
    _check("V-3a fix-hash NOT checkable",
           predicate_checkable(parse_predicate("fix of artifact_hash=deadbeef within 30d")) is False)

    # V-3b predicate_rates: touching+referencing+revert-hash count in `parseable`,
    # a fix-hash counts `uncheckable`. (Entries old enough to be outside grace.)
    entries = [
        _entry(run_id="t", skill="quality-gate",
               predicted_falsifier="fix touching src/auth.py within 30d"),
        _entry(run_id="r", skill="quality-gate",
               predicted_falsifier="cve referencing token-refresh within 90d"),
        _entry(run_id="h", skill="quality-gate",
               predicted_falsifier="revert of artifact_hash=deadbeef within 30d"),
        _entry(run_id="fh", skill="quality-gate",
               predicted_falsifier="fix of artifact_hash=deadbeef within 30d"),
    ]
    rates = predicate_rates(entries, {}, now="2026-06-01T00:00:00Z")
    qg = rates.get("quality-gate", {})
    _check("V-3b touching+referencing+revert-hash → parseable=3",
           qg.get("parseable") == 3, f"got {qg}")
    _check("V-3b fix-hash → uncheckable=1", qg.get("uncheckable") == 1, f"got {qg}")

    # V-3c keyword-only threading: the old positional call shape is untouched.
    tmp = tempfile.mkdtemp(prefix="v3-thread-")
    try:
        fals = os.path.join(tmp, "falsification.jsonl")
        te = [_entry(run_id="r-t", gated_files=["src/auth.py"],
                     predicted_falsifier="fix touching src/auth.py within 30d")]
        cands = [{"commit": "c", "touched_files": ["src/auth.py"],
                  "merge_time": "2026-01-11T00:00:00Z"}]
        _, appended = reconcile_predicates(te, cands, fals, now="2026-03-01T00:00:00Z")
        _check("V-3c positional touching call unchanged (fires)",
               len(appended) == 1 and appended[0].get("via") == "predicate", f"got {appended}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# #342 signal_type + scoped Brier (V-4)                                        #
# --------------------------------------------------------------------------- #

def test_bad_implementation_signal():
    from scripts.reconcile_ledger import (
        reconcile, compute_brier, ledger_entry_hash, load_jsonl,
    )

    # V-4a/b manual attribution threads signal_type top-level + into falsified_by.
    tmp = tempfile.mkdtemp(prefix="v4-sig-")
    try:
        ledger = os.path.join(tmp, "runs.jsonl")
        fals = os.path.join(tmp, "falsification.jsonl")
        manual = os.path.join(tmp, "manual-attribution.jsonl")
        h = ledger_entry_hash("r-design", "quality-gate")
        with open(manual, "w") as f:
            import json
            f.write(json.dumps({"ledger_entry_hash": h, "falsified": True,
                                "confidence": "high", "signal_type": "bad_implementation",
                                "reasoning": "design call led to downstream rework"}) + "\n")
        with open(ledger, "w") as f:
            pass
        appended = reconcile(ledger, fals, manual, [], cross_cut_threshold=20,
                             now="2026-03-01T00:00:00Z")
        e = appended[0] if appended else {}
        _check("V-4a signal_type at top level of falsification entry",
               e.get("signal_type") == "bad_implementation", f"got {e}")
        _check("V-4a' signal_type injected into falsified_by",
               (e.get("falsified_by") or {}).get("signal_type") == "bad_implementation", f"got {e}")

        # V-4b default signal_type is manual_override; user-supplied falsified_by gets it too.
        manual2 = os.path.join(tmp, "manual2.jsonl")
        fals2 = os.path.join(tmp, "fals2.jsonl")
        with open(manual2, "w") as f:
            import json
            f.write(json.dumps({"ledger_entry_hash": h, "falsified": True,
                                "falsified_by": {"commit": "abc", "reason": "x"}}) + "\n")
        appended2 = reconcile(ledger, fals2, manual2, [], cross_cut_threshold=20,
                             now="2026-03-01T00:00:00Z")
        e2 = appended2[0] if appended2 else {}
        _check("V-4b default signal_type is manual_override",
               e2.get("signal_type") == "manual_override", f"got {e2}")
        _check("V-4b' user-supplied falsified_by gets signal_type injected",
               (e2.get("falsified_by") or {}).get("signal_type") == "manual_override", f"got {e2}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # V-4c scoped Brier: a NON-CODE design PASS WITH a bad_implementation attribution
    # is admitted with actual=0 → sq_err (0.9-0)^2 = 0.81.
    h = ledger_entry_hash("r-d", "design")
    entries = [_entry(run_id="r-d", skill="design", artifact_type="design",
                      verdict="PASS", confidence=0.9, predicted_falsifier=None)]
    fmap = {h: {"ledger_entry_hash": h, "falsified": True, "cross_cut": False,
                "signal_type": "bad_implementation"}}
    b = compute_brier(entries, fmap, now="2026-03-01T00:00:00Z")
    _check("V-4c non-code PASS + bad_implementation → brier 0.81",
           abs(b.get("design", {}).get("brier", -1) - 0.81) < 1e-9, f"got {b}")

    # V-4d a non-code verdict WITHOUT a bad_implementation attribution stays EXCLUDED.
    b0 = compute_brier(entries, {}, now="2026-03-01T00:00:00Z")
    _check("V-4d non-code PASS, no attribution → excluded (no design score)",
           "design" not in b0, f"got {b0}")

    # V-4e a non-code Tier B verdict (confidence null) + bad_implementation → NOT Brier-scored.
    eb = [_entry(run_id="r-b", skill="audit", artifact_type="design", tier="B",
                 verdict="PASS", confidence=None, predicted_falsifier=None)]
    hb = ledger_entry_hash("r-b", "audit")
    fmapb = {hb: {"ledger_entry_hash": hb, "falsified": True, "cross_cut": False,
                  "signal_type": "bad_implementation"}}
    bb = compute_brier(eb, fmapb, now="2026-03-01T00:00:00Z")
    _check("V-4e non-code Tier B (confidence null) → NOT Brier-scored",
           "audit" not in bb, f"got {bb}")

    # V-4g (gate S1): bad_implementation is PASS-side. A NON-code FAIL carrying it
    # is out-of-contract → must NOT be admitted (would otherwise score actual=1
    # and improve Brier for free).
    hf = ledger_entry_hash("r-df", "design")
    ef = [_entry(run_id="r-df", skill="design", artifact_type="design",
                 verdict="FAIL", confidence=0.9, predicted_falsifier=None)]
    fmapf = {hf: {"ledger_entry_hash": hf, "falsified": True, "cross_cut": False,
                  "signal_type": "bad_implementation"}}
    bf = compute_brier(ef, fmapf, now="2026-03-01T00:00:00Z")
    _check("V-4g non-code FAIL + bad_implementation → excluded (PASS-side only)",
           "design" not in bf, f"got {bf}")


def test_render_breakdown():
    # V-4f render breakdown counts bad_implementation separately.
    from scripts.render_ledger import falsified_breakdown
    tmp = tempfile.mkdtemp(prefix="v4f-")
    try:
        import json
        fals = os.path.join(tmp, "falsification.jsonl")
        rows = [
            {"ledger_entry_hash": "a", "falsified": True, "via": "walkback"},
            {"ledger_entry_hash": "b", "falsified": True, "via": "predicate"},
            {"ledger_entry_hash": "c", "falsified": True,
             "falsified_by": {"manual_override": True}},
            {"ledger_entry_hash": "d", "falsified": True, "signal_type": "bad_implementation",
             "falsified_by": {"manual_override": True, "signal_type": "bad_implementation"}},
        ]
        with open(fals, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        bd = falsified_breakdown(fals)
        ok = (bd.get("walkback") == 1 and bd.get("predicate") == 1
              and bd.get("manual_override") == 1 and bd.get("bad_implementation") == 1)
        _check("V-4f breakdown: walkback/predicate/manual_override/bad_implementation each 1",
               ok, f"got {bd}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# #341 wiring lint (V-5)                                                       #
# --------------------------------------------------------------------------- #

def test_wiring_lint():
    skills = ["verify", "test-coverage", "review-feedback"]
    for name in skills:
        path = os.path.join(REPO_ROOT, "skills", name, "SKILL.md")
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            _check(f"V-5 {name}: SKILL.md present", False, path)
            continue
        _check(f"V-5 {name}: emits via ledger_append.py",
               "ledger_append.py" in text, "missing emit invocation")
        _check(f"V-5 {name}: Tier B stub",
               re.search(r'"tier"\s*:\s*"B"|tier["\s:]+B', text) is not None,
               "missing tier B marker")
        _check(f"V-5 {name}: standalone-only precondition",
               "standalone" in text.lower(), "missing standalone-only gate")
        _check(f"V-5 {name}: kill-switch mention",
               "CRUCIBLE_CALIBRATION_DISABLED" in text, "missing kill-switch")
        _check(f"V-5 {name}: never-block clause",
               re.search(r"never block|must never block|does not block|not block the",
                         text, re.I) is not None, "missing never-block clause")


def main():
    test_hash_fired()
    test_referencing_fired()
    test_dispatch_and_render()
    test_bad_implementation_signal()
    test_render_breakdown()
    test_wiring_lint()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
