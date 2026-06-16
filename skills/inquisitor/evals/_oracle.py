#!/usr/bin/env python3
"""Differential leave-one-out oracle for Phase-1b (#424, design §4).

Deterministic, no LLM anywhere in the scoring path. Given an arm's harvested test
file(s) and a seeded fixture repo, decide which seeded bugs the tests CAUGHT, by
re-running the tests against pristine materialized variants:

    caught(Bᵢ) ⟺ ∃ test t such that ALL of:
        (1) t is GREEN on all-fixed                 (passes when nothing is broken)
        (2) t is RED   on the full-buggy base       (MANDATORY — catches a real bug)
        (3) t is RED   on all-fixed-minus-Bᵢ        (removing only Bᵢ's fix re-breaks it)

No specificity gate: the `minus-Bᵢ` variant has only Bᵢ unfixed (every other bug's
fix is applied), so under the §3 behavioral-independence invariant any deterministic
RED there is attributable to Bᵢ's misbehavior — regardless of the test's intent. A
broad test red on several `minus-Bᵢ` is therefore correctly credited to EACH of those
independent bugs (arm-neutral). This is a property of the VARIANT, not of the exemplar
matrix; it transfers to arbitrary producer tests.

S-3 residual (documented, not gated this round): the transfer argument above holds
*only* under §3 disjointness — that `minus-Bᵢ` has exactly one behavioral fault and
the patches are behaviorally disjoint. `check_fixture_independence.py` PROVES that
for the hand-authored EXEMPLARS, but it cannot prove it for an arbitrary producer
test, which could assert a compound property whose single RED on `minus-Bᵢ` AND
`minus-Bⱼ` is credited to both even though it depends on the *conjunction* rather
than each bug independently. Because such a test red-on-all-fixed is already filtered
by the GREEN-on-all-fixed eligibility gate, the residual is narrow; it inflates
absolute catch counts symmetrically across arms (so it does not bias the *delta*),
but it can inflate the absolute rate feeding the WITHOUT *absolute* ceiling
(`_WITHOUT_CEILING`). Rather than add per-test specificity gating this round, the
scorer surfaces a per-arm `conjunction_inflation.tests_crediting_3plus_bugs`
diagnostic in `last_run.json` so an operator can spot conjunction-driven inflation
before trusting the ceiling. (Justification for stopping at doc+diagnostic: full
gating would require an audited specificity rule per producer test, which the
exemplar-only independence proof does not support; the diagnostic makes the residual
observable, which the absolute-ceiling read needs, without a new unproven gate.)

ERROR/collection-failure is NOT green
and NOT red (rc table in `_fixtures.rc_to_verdict`). Every (test, variant) verdict is
twice-run flake-guarded, including the all-fixed / base anchors. The oracle harvests
ONLY the test files and runs them on pristine variants, so agent source edits /
self-reported pass-fail are irrelevant.

SCORING UNIT IS THE FILE (S1): each harvested test FILE is run as one pytest
invocation and gated whole — it must be GREEN on all-fixed and RED on base to be
eligible, and is discarded entirely if flaky on any minus-variant or if it ERRORs
(see `errored_discards`). A file bundling several test functions shares that fate:
one over-strict / flaky / import-erroring function sinks the file's other catches.
Producers are therefore told (budget section, every arm uniformly) to write
one self-contained test per file, so this file-as-unit penalty is symmetric across
arms; `flaky_discards` + `errored_discards` (all-fixed anchor) +
`errored_minus_discards` (a stable ERROR on a minus-Bᵢ variant) make every discard
channel observable (the base-anchor ERROR is the one documented exception — see
`caught_bugs`).

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
    """Return {"caught": set, "broad_test_catches": dict, "flaky_discards": int,
    "errored_discards": int, "errored_minus_discards": int}.

    `caught` holds the bug_ids the tests caught (plus one "+"-joined id per
    registered interacting set credited). `broad_test_catches` maps each crediting
    test path -> how many bugs it isolated (reported, NOT gating). `flaky_discards`
    counts tests discarded for an unstable (test, variant) verdict.

    `errored_discards` (S2) counts tests that ERROR'd (collection/import failure —
    e.g. a harvested test importing a producer-authored helper that wasn't
    harvested) on the ALL-FIXED anchor and so were ruled ineligible. ERROR is not
    GREEN, so such a test can never be credited; surfacing the count makes a catch
    that leaked into ERROR observable in last_run.json rather than silently lost.
    Scope note (second-pass #1): this counter covers ERROR on the all-fixed anchor
    ONLY. A test that is GREEN on all-fixed but ERRORs on the *base* anchor (the
    `vb != RED` branch below) is dropped as "catches no real bug" without a counter
    — an unusual shape (a catch that imports/collects under all-fixed but not under
    the buggy base) and symmetric across arms, so it is left uncounted by design;
    the observability claim is therefore scoped to the all-fixed anchor.

    `errored_minus_discards` (S-1) closes the THIRD ERROR channel: an eligible test
    (GREEN on all-fixed, RED on base) that returns a stable ERROR on a specific
    `minus-Bᵢ` variant. There `matrix[k][t] == ERROR` is neither flaky (`is None`)
    nor a credit (`== RED`), so the bug Bᵢ is silently uncredited for that test.
    The exemplars are proven ERROR-free on every variant by the independence checker,
    but an ARBITRARY producer test can take an import/collection-time path under the
    one buggy minus-variant that it does not take under all-fixed/base — losing a
    real catch with no trace. This counter increments once per (test, minus-variant)
    ERROR cell so that loss is observable in last_run.json. Credit semantics are
    unchanged (an ERROR cell is still not a credit); only the discard is now counted.
    With this counter every discard channel — flaky, all-fixed ERROR, minus-variant
    ERROR — is observable; the base-anchor ERROR remains uncounted by design (above).
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
    errored = 0
    errored_minus = 0

    # --- eligibility: GREEN on all-fixed AND RED on base (anchors twice-run) ---
    eligible = []
    with _fixtures.variant(repo_dir, apply=bug_ids) as af, \
         _fixtures.variant(repo_dir, apply=[]) as base:
        for t in test_files:
            va = _stable(af, t, manifest)
            if va is None:
                flaky += 1
                continue
            if va == ERROR:
                # collection/import failure on fully-corrected code: ineligible,
                # but surface it (S2) — a real catch may be hiding in here.
                errored += 1
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
        return {"caught": caught, "broad_test_catches": broad,
                "flaky_discards": flaky, "errored_discards": errored,
                "errored_minus_discards": errored_minus}

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
        # S-1: a stable ERROR on a minus-variant is neither flaky nor a credit; the
        # bug behind that cell is silently uncredited for this test. Count each such
        # cell so the lost catch is observable (credit semantics unchanged).
        errored_minus += sum(1 for k in matrix if matrix[k][t] == ERROR)
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

    return {"caught": caught, "broad_test_catches": broad,
            "flaky_discards": flaky, "errored_discards": errored,
            "errored_minus_discards": errored_minus}
