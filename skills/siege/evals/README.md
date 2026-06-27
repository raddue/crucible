# Siege eval harness (#373)

<!-- MODEL-TIER: security-hard-out -->

A regression harness for `siege` (the security-audit engine). The oracle is the SAME
**deterministic matcher** (`_matcher.py`) the delve harness uses — NOT an LLM judge — so
scoring is LLM-free and the scorer + fixtures + harness tests are **CI-gated** (real
regression protection). The live `/siege` run between `stage` and `score` is
**manual/periodic**: it produces recorded threat findings that the deterministic scorer
consumes. This is the second vertical slice of #373 (delve was first); the matcher and
the `_dispatch_paths.py` / `_runid.py` helpers are **copied from delve** and kept
AST-identical by `scripts/check_siege_helper_drift.py` (copy + drift-check, #424
precedent — not a premature shared-lib extraction, per the #404 reframe).

## Invocation (module form)

Run from the repo root (the package uses relative imports, so `-m` is required):

```
python3 -m skills.siege.evals.run_evals stage <run-id> [--fixture ID] [--force]
python3 -m skills.siege.evals.run_evals score <run-id> [--allow-incomplete]
```

`stage` prints the dispatch dir path.

## The matcher (oracle)

Identical to delve's. A recorded finding `F` **matches** a planted vuln `B` iff ALL hold:

1. **same file** (repo-relative POSIX, normalized — backslashes → `/`, leading `./`
   stripped).
2. **line overlap**: `F`'s line (an `int`, `"19"`, or `"19-20"` range) intersects
   `[B.line_lo − slop, B.line_hi + slop]`, with `slop = 2`.
3. **signature gate**: ≥1 of `B.signature` (lowercased substring tokens) appears in
   `F.summary` (falling back to `F.failure_scenario`). This cuts positional
   false-positives — a finding at the right line about the **wrong** vuln does not score.

Matching is **bipartite, one-to-one, maximum-cardinality** (Kuhn augmenting-path).
Metrics: **recall** (matched planted vulns / total), **false-positive rate** (unmatched
kept findings / total kept), **off-axis recall** (advisory; restricted to `off_axis`
vulns), and **severity agreement** (advisory; see below).

## The siege findings-adapter (the delve→siege delta)

The ONLY substantive change from delve is the adapter (`_adapt_siege_findings`): siege's
threat-finding records carry siege's fields rather than delve's 8-field records. The
adapter maps each onto the matcher's generic shape before matching:

- `summary` ← `title` (the finding headline)
- `failure_scenario` ← `attack` (the 1-sentence exploitation scenario) joined with
  `evidence`, so a signature token quoted only in the attack/evidence line still scores
- `file`, `line` pass through (the matcher normalizes/parses them)
- `severity` feeds the **severity-agreement advisory** ONLY

A record that already uses the generic `summary`/`failure_scenario` keys is honored
as-is (so the unit tests can write either form).

**Severity agreement is ADVISORY — NOT part of recall/FP.** Detection is the core metric;
severity calibration is a separate concern (per the design). For each matched
(vuln, finding) pair where BOTH carry a `severity`, the harness records whether they
agree (case-insensitive). The `{Critical, High, Medium}` enum constrains the **planted
GT** severities only (the GT-integrity check enum-validates the ground-truth side). A
recorded **finding** may carry any severity (including `Low`); it is simply scored as
agree/disagree against the matched GT vuln — an out-of-GT-enum finding severity just
counts as a disagreement, never an error.

## Workflow (stage → manual collect → score)

1. **`stage <run-id>`** writes `stage-manifest.json` to the dispatch dir, one cell per
   fixture: `{fixture_id, scope, result_file, dispatch_note}`. It prints the dispatch dir.

2. **collect** (manual — there is no `collect` subcommand). For each cell, follow its
   `dispatch_note`:
   - Run `/siege <scope>` (the engine's normal invocation).
   - Save siege's threat findings as a JSON array (`{id, severity, exploitability, title,
     file, line, cwe, attack, evidence, agent}`) to the cell's `result_file`.
   - **Path form:** save each finding's `file` **verbatim** — the harness reconciles the
     cell's `scope` prefix at score time, so bare (`app.py`) OR scope-prefixed
     (`<scope>/app.py`) both join to the ground-truth form. No manual path rewriting.
   - Prepend `DISPATCH_STATUS: OK` then a blank line before the JSON (use
     `DISPATCH_STATUS: ERROR` if the dispatch failed — that cell scores 0).
   - When every cell is recorded, write an empty `.collect-status` file in the dispatch dir.

3. **`score <run-id>`** adapts the recorded findings, runs the matcher against each
   fixture's `ground-truth-bugs.json`, and writes `skills/siege/evals/last_run.json` +
   `results.md` (both git-ignored). It **refuses** without `.collect-status` unless
   `--allow-incomplete` (which stamps `complete: false` — smoke/debug only). A recorded
   finding whose `line` is unparseable is counted as an unmatched false-positive (and
   warned), not silently dropped and not crashing the run.

## Fixtures

`fixtures/<repo>/`:
- a tiny hermetic module with deliberately **planted vulnerabilities** at known
  file:line (the `webshop` fixture: SQLi, unsafe deserialization, broken access control,
  IDOR, SSRF, path-traversal [off_axis]);
- `ground-truth-bugs.json` — the planted vulns:
  `{bug_id, file, line_lo, line_hi, signature[], desc, off_axis, severity}` with
  `severity ∈ {Critical, High, Medium}`;
- `ground-truth-bugs.provenance.md` — the **verbatim blind-author input**, with the
  `signature` tokens + `desc` strings WITHHELD (so the recorded run is scored against an
  unbiased oracle);
- `manifest.json` — `{repo_id, scope, bug_ids, n}`.

`scripts/check_siege_gt_provenance.py` proves the blind boundary held AND is a total,
complete GT-schema validator (structure + per-field types + `line_lo<=line_hi` +
non-empty string signature + bool off_axis + `severity ∈ {Critical, High, Medium}` +
unique bug_ids + manifest consistency).

## Files

- `run_evals.py` — `stage` + `score` + the siege findings-adapter (siege-original).
- `_matcher.py`, `_dispatch_paths.py`, `_runid.py` — copied from delve; the drift check
  `scripts/check_siege_helper_drift.py` is **function-scoped** (it pins siege's copies
  AST-identical to delve's for every imported function + the `_RUN_ID_RE` /
  `_DEFAULT_LINE_SLOP` constants).
- `test_matcher.py`, `test_run_evals_stage.py`, `test_run_evals_score.py`,
  `test_runid.py` — the gating unit tests (run by `scripts/run_tests.sh`).

**Deferred (post-merge, not in CI):** the live `/siege` decision run that produces the
actual recall/FP numbers, recorded in `docs/evals.md`. The remaining #373 orchestrators
are staged follow-ups (the design establishes the reusable pattern).
