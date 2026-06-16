#!/usr/bin/env python3
"""Differential leave-one-out oracle for Phase-1b (#424, design §4).

Deterministic, no LLM anywhere in the scoring path. Given an arm's harvested test
file(s) and a seeded fixture repo, decide which seeded bugs the tests CAUGHT, by
re-running the tests against pristine materialized variants:

    caught(Bᵢ) ⟺ ∃ test t such that ALL of:
        (1) t is GREEN on all-fixed                 (passes when nothing is broken)
        (2) t is RED   on the full-buggy base       (MANDATORY — catches a real bug)
        (3) t is RED   on all-fixed-minus-Bᵢ        (removing only Bᵢ's fix re-breaks it)

No specificity gate: under the §3 behavioral-independence invariant a test red on
`minus-Bᵢ` can only be red because Bᵢ is the sole unfixed bug there, so a broad test
red on several `minus-Bᵢ` is correctly credited to EACH of those independent bugs
(arm-neutral). ERROR/collection-failure is NOT green and NOT red (rc table in
`_fixtures.rc_to_verdict`). Every (test, variant) verdict is twice-run flake-guarded,
including the all-fixed / base anchors. The oracle harvests ONLY the test files and
runs them on pristine variants, so agent source edits / self-reported pass-fail are
irrelevant.

A registered `interacting_set` (the rare audited escape for a genuinely co-violable
pair) is credited once via the set's combined `minus`-variant; its members are
excluded from the per-bug leave-one-out so the set isn't double-counted.
"""
from pathlib import Path

from . import _fixtures

GREEN, RED, ERROR = "GREEN", "RED", "ERROR"


def _stable(variant_dir, test_file, manifest):
    """Twice-run flake guard: the verdict if stable across two runs, else None."""
    v1 = _fixtures.run_test_in_dir(variant_dir, test_file, manifest)
    v2 = _fixtures.run_test_in_dir(variant_dir, test_file, manifest)
    return v1 if v1 == v2 else None


def caught_bugs(test_files, repo_dir, *, interacting_sets=()):
    """Return {"caught": set, "broad_test_catches": dict, "flaky_discards": int}.

    `caught` holds the bug_ids the tests caught (plus one "+"-joined id per
    registered interacting set credited). `broad_test_catches` maps each crediting
    test path -> how many bugs it isolated (reported, NOT gating). `flaky_discards`
    counts tests discarded for an unstable (test, variant) verdict.
    """
    repo_dir = Path(repo_dir)
    manifest = _fixtures.load_manifest(repo_dir)
    bug_ids = list(manifest["bug_ids"])
    sets = [sorted(s) for s in (interacting_sets or [])]
    members = {b for s in sets for b in s}
    non_set = [b for b in bug_ids if b not in members]

    test_files = [Path(t) for t in test_files]
    caught = set()
    broad = {}
    flaky = 0

    # --- eligibility: GREEN on all-fixed AND RED on base (anchors twice-run) ---
    eligible = []
    with _fixtures.variant(repo_dir, apply=bug_ids) as af, \
         _fixtures.variant(repo_dir, apply=[]) as base:
        for t in test_files:
            va = _stable(af, t, manifest)
            if va is None:
                flaky += 1
                continue
            if va != GREEN:
                continue  # fails even fully-corrected -> pinned to no seeded bug
            vb = _stable(base, t, manifest)
            if vb is None:
                flaky += 1
                continue
            if vb != RED:
                continue  # catches no real bug (nothing to expose)
            eligible.append(t)

    if not eligible:
        return {"caught": caught, "broad_test_catches": broad, "flaky_discards": flaky}

    # --- minus-variant matrix (cost opt: only eligible tests reach the minuses) ---
    matrix = {}  # key -> {test_path: verdict-or-None};  key = bug_id | ("set", tuple)
    for b in non_set:
        with _fixtures.variant(repo_dir, apply=bug_ids, exclude=[b]) as mv:
            matrix[b] = {t: _stable(mv, t, manifest) for t in eligible}
    for s in sets:
        with _fixtures.variant(repo_dir, apply=bug_ids, exclude=s) as mv:
            matrix[("set", tuple(s))] = {t: _stable(mv, t, manifest) for t in eligible}

    # --- per-test crediting; a test flaky on ANY minus is discarded entirely ---
    for t in eligible:
        if any(matrix[k][t] is None for k in matrix):
            flaky += 1
            continue
        isolated = 0
        for b in non_set:
            if matrix[b][t] == RED:
                caught.add(b)
                isolated += 1
        for s in sets:
            if matrix[("set", tuple(s))][t] == RED:
                caught.add("+".join(s))
                isolated += 1
        if isolated:
            broad[str(t)] = isolated

    return {"caught": caught, "broad_test_catches": broad, "flaky_discards": flaky}
