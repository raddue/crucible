# Phase-1b seeded repos (fixtures)

Hermetic, runnable synthetic Python packages with deliberately-seeded
**cross-component seam bugs** — the substrate the Phase-1b execution eval scores
arms against. See `docs/plans/2026-06-15-inquisitor-phase1b-execution-eval-design.md`
§3 (fixtures) and §4 (the differential oracle) for the full construct.

## Per-repo layout (`fixtures/<repo-id>/`)

```
src/<pkg>/...               # all-buggy source tree (committed = base state)
tests/                      # empty dir + conftest.py; arms/oracle write test files here
fixes/<bug_id>.patch        # one independently-revertible patch per seeded bug
exemplars/<bug_id>.py       # fixture-build BEHAVIORAL exemplar test for each bug
ground-truth-bugs.json      # blind-authored bug list (schema below), off_axis tagged post-blind
ground-truth-bugs.provenance.md   # blind boundary + post-blind off_axis pass record
manifest.json               # repo id, pkg, test dir, runner cmd, bug ids, n
```

### Committed substrate is annotated; the producer copy is NOT

The committed `src/` annotates each seeded bug with its id + a plain-language
description (`# BUG nt-b8: …`, `(nt-b1)`) — build scaffolding for the maintainer
and the oracle, NOT a producer-visible artifact. The **producer never sees the
committed tree**: `stage_exec`'s `copy_for` builds the agent sandbox with
`_fixtures.copy_repo_for_producer`, which (F2) copies ONLY `src/` + `tests/` —
never `exemplars/`, `fixes/`, `ground-truth-bugs*`, or `manifest.json` — and (F1)
**strips all comments and docstrings from every producer-visible `*.py` (both the
copied `src/` AND `tests/` subtrees)**, so no leak token or bug-describing prose
survives (token-aware, code byte-identical). `scripts/check_fixture_producer_blind.py`
+ `_fixtures._assert_no_leak` + `_fixtures.assert_no_description_leak` (stage-time
assertions) enforce, **across every producer-visible subtree (`src/` and `tests/`,
not `src/` alone)**, that no producer copy carries a bug-id token, GT-description
prose, or an answer-key path; `_assert_no_leak` additionally machine-checks the
`tests/`-is-empty-except-`conftest.py` invariant. The oracle scores from this
committed tree (`_FIXTURES_DIR`), not from the producer copy, so the annotations
never reach the measured arm yet remain available to scoring.

## Variants (materialized, never committed)

The oracle and the fixture-build invariant checker materialize three variant
classes from the committed base + the per-bug patches (see `_fixtures.py`):

- **`base`** — the source tree as committed (every seeded bug live).
- **`all-fixed`** — base + every `fixes/<bug_id>.patch` applied.
- **`all-fixed-minus-Bᵢ`** — base + every patch **except** Bᵢ's (one per bug).

All patches are authored **against the committed base** and touch **disjoint
files or disjoint base-line ranges**, so they compose order-independently and
zero-fuzz: `all-fixed` and every `all-fixed-minus-Bᵢ` apply cleanly.

## `manifest.json` schema

```json
{
  "repo_id": "notify",
  "pkg": "notify",
  "test_dir": "tests",
  "runner_cmd": ["python3", "-m", "pytest", "-q"],
  "bug_ids": ["nt-b1", "nt-b2", "..."],
  "n": 8
}
```

`len(bug_ids) == n` is an invariant (`load_manifest` asserts it).

## `ground-truth-bugs.json` schema

```json
{
  "_provenance": "see ground-truth-bugs.provenance.md",
  "bugs": [
    {
      "bug_id": "nt-b1",
      "desc": "epoch-int written into a field the consumer reads as an ISO timestamp",
      "off_axis": false,
      "fix_patch": "fixes/nt-b1.patch"
    }
  ],
  "interacting_sets": []
}
```

- **`bug_id`** — stable id; matches `fixes/<bug_id>.patch` and `exemplars/<bug_id>.py`.
- **`desc`** — behavioral description of the observably-wrong output (authored blind).
- **`off_axis`** — `true` for defects outside the 5 dimension lenses (Wiring /
  Integration / Edge Cases / State & Lifecycle / Regression), so the bare arms
  (WITHOUT/POOL) get fair credit.
- **`fix_patch`** — repo-relative path to the patch that fixes ONLY this bug.
- **`interacting_sets`** — list of `bug_id` lists; the audited escape for a
  genuinely co-violable pair that fixture construction could not avoid (§3, §4).
  Empty is the norm — independence is the rule.

## Blind ground-truth discipline

GT is authored from the source tree + factual context only, **blind to the
dimension taxonomy** (the 5 lens titles and the four arm names WITH/POOL/MID/
WITHOUT are the leak set). The exact blind input is recorded in
`ground-truth-bugs.provenance.md`; `scripts/check_fixture_gt_provenance.py`
asserts no leak.

**`off_axis` is tagged in a separate post-blind pass** (§3): after blind GT
authoring is sealed, a role that authors no arm's tests and is not the GT author
applies the `off_axis` tag. The provenance file records this as a distinct,
post-blind step.

## Behavioral-independence (the fixture-construction invariant)

The seeded bugs in each repo MUST be pairwise **behaviorally independent**: no
two bugs may be co-violable by a single behavioral assertion. Concretely, each
bug Bᵢ's exemplar test is:

- **GREEN on `all-fixed`** (passes when nothing is broken),
- **RED on the full-buggy base** (it actually catches a real bug),
- **RED on its own `all-fixed-minus-Bᵢ`** (removing only Bᵢ's fix re-breaks it),
- **GREEN on every *other* `all-fixed-minus-Bⱼ` (j≠i)** (no co-violable pairs).

This is what makes §4's leave-one-out attribution clean and arm-neutral without
a specificity gate. `scripts/check_fixture_independence.py` verifies it.
