# Delve eval harness (#373)

A regression harness for `delve` (the instance-bug finder). The oracle is a
**deterministic matcher** (`_matcher.py`) — NOT an LLM judge — so scoring is LLM-free
and the scorer + fixtures + harness tests are **CI-gated** (real regression
protection). The live `/delve` run between `stage` and `score` is **manual/periodic**:
it produces a recorded findings JSON that the deterministic scorer consumes. This
mirrors inquisitor's split (deterministic harness-tests in CI; the live decision-run
out of CI).

## Invocation (module form)

Run from the repo root (the package uses relative imports, so `-m` is required):

```
python3 -m skills.delve.evals.run_evals stage <run-id> [--fixture ID] [--force]
python3 -m skills.delve.evals.run_evals score <run-id> [--allow-incomplete]
```

`stage` prints the dispatch dir path.

## The matcher (oracle)

A recorded finding `F` **matches** a planted bug `B` iff ALL hold:

1. **same file** (repo-relative POSIX, normalized — backslashes → `/`, leading `./`
   stripped).
2. **line overlap**: `F`'s line (an `int`, `"12"`, or `"12-15"` range) intersects
   `[B.line_lo − slop, B.line_hi + slop]`, with `slop = 2` (tolerate off-by-a-line
   drift).
3. **signature gate**: ≥1 of `B.signature` (lowercased substring tokens) appears in
   `F.summary` (falling back to `F.failure_scenario`). This cuts positional
   false-positives — a finding at the right line about the **wrong** defect does not
   score.

Matching is **bipartite, one-to-one, maximum-cardinality** (Kuhn augmenting-path):
candidate edges are *visited* in ranked order — by overlap size, then signature-hit
count, with a deterministic tie-break by `bug_id` then finding index — so among all
maximum matchings the result is deterministic and high-weight. Each planted bug is
credited at most once, each finding consumed at most once. Metrics:

- **recall** = matched planted bugs / total planted bugs.
- **false-positive rate** = unmatched kept findings / total kept findings.
- **off-axis recall** (advisory) = recall restricted to `off_axis: true` bugs.

A recorded finding whose `line` is unparseable (e.g. `null`, `""`, `"abc"`, `"12-"`)
is counted as an **unmatched false positive** (and `score` warns to stderr + reports a
per-cell `malformed_findings` count) — it is neither silently dropped nor allowed to
crash the run.

## Workflow (stage → manual collect → score)

1. **`stage <run-id>`** writes `stage-manifest.json` to the dispatch dir, enumerating
   one cell per fixture: `{fixture_id, scope, result_file, dispatch_note}`. It prints
   the dispatch dir.

2. **collect** (manual — there is no `collect` subcommand). For each cell, follow its
   `dispatch_note`:
   - Run `/delve <scope>` (the engine's normal invocation).
   - Save the engine's ranked **8-field** findings JSON array (`file`, `line`,
     `summary`, `failure_scenario`, `severity`, `verdict`, `scope`, `effort`) to the
     cell's `result_file` in the dispatch dir.
   - Prepend `DISPATCH_STATUS: OK` then a blank line before the JSON (use
     `DISPATCH_STATUS: ERROR` if the dispatch failed — that cell scores 0).
   - **Path form:** save each finding's `file` **verbatim** — the harness reconciles
     the cell's `scope` prefix at score time, so a `file` recorded bare
     (`inventory.py`) OR scope-prefixed (`<scope>/inventory.py`) both join to the
     ground-truth (fixture-relative) form. No manual path rewriting is needed.
   - When every cell is recorded, write an empty `.collect-status` file in the
     dispatch dir.

3. **`score <run-id>`** reads `stage-manifest.json` + the recorded findings, runs the
   matcher against each fixture's `ground-truth-bugs.json`, and writes
   `skills/delve/evals/last_run.json` + `results.md` (both git-ignored). It **refuses**
   without `.collect-status` unless `--allow-incomplete` (which stamps
   `complete: false` — smoke/debug only).

## Fixtures

`fixtures/<repo>/`:
- a tiny hermetic module with deliberately **planted defects** at known file:line;
- `ground-truth-bugs.json` — the planted bugs:
  `{bug_id, file, line_lo, line_hi, signature[], desc, off_axis, severity}`;
- `ground-truth-bugs.provenance.md` — the **verbatim blind-author input**, with the
  `signature` tokens + `desc` strings WITHHELD (so the recorded run is scored against
  an unbiased oracle);
- `manifest.json` — `{repo_id, scope, bug_ids, n}`.

`scripts/check_delve_gt_provenance.py` proves the blind boundary held (the provenance
file contains none of the withheld signature/desc strings).

## Files

- `run_evals.py` — `stage` + `score` (no `collect`).
- `_matcher.py` — the deterministic matcher (delve-original).
- `_dispatch_paths.py`, `_runid.py` — copied from temper. The drift check
  `scripts/check_delve_helper_drift.py` is **function-scoped** to the functions delve
  imports, so the copies may omit temper's unused helpers without reddening CI.
- `test_matcher.py`, `test_run_evals_stage.py`, `test_run_evals_score.py`,
  `test_runid.py` — the gating unit tests (run by `scripts/run_tests.sh`).

**Deferred (post-merge, not in CI):** the live `/delve` decision run that produces the
actual recall/FP numbers, recorded in `docs/evals.md`. The **siege** slice is a
separate follow-up on #373 (same pattern under `skills/siege/evals/`).
