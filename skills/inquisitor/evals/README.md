# Inquisitor fan-out eval harness (#424, Phase 1 + Phase 1b)

A bespoke harness that fires inquisitor's real fan-out **structure** over seeded
fixtures and records a delta. It mirrors temper's `stage` / `score` split — Python
owns deterministic mechanics; the live orchestrator agent owns the two things Python
can't do (dispatch + judgement). **Two phases live behind the manifest `mode`
field** (the Phase-1 path is byte-untouched):

- **Phase 1** (`mode` absent) — the **three-arm** identification-breadth measurement
  with the **execution half stubbed** (real dimension lenses + test *reasoning*;
  tests are *described*, not run). See
  `docs/plans/2026-06-13-inquisitor-fanout-eval-harness-design.md`. A non-positive
  delta here is *inconclusive*, not condemning (the design's go/no-go).
- **Phase 1b** (`mode:"phase1b-exec"` / `mode:"pilot"`) — the terminal **detection-
  axis** measurement: real write-AND-run execution against hermetic seeded repos,
  scored by a deterministic differential oracle (no LLM judge). 4 arms + an
  oracle; see the "Phase 1b" section below and
  `docs/plans/2026-06-15-inquisitor-phase1b-execution-eval-design.md`.

The sections that follow describe the **Phase-1** three-arm path; the **Phase-1b**
four-arm execution path is documented in its own section near the end.

## The three arms

| Arm | Composition | Measures |
|-----|-------------|----------|
| **WITH** | 5 parallel dimension subagents (`inquisitor-dimension-prompt-eval.md`, execution stubbed) → a 6th aggregation subagent (`aggregation-prompt.md`) | the methodology with execution stubbed |
| **MID** | ONE agent given the **same WITH per-dimension procedural shell** (relentless-hunter persona, `## Your Job` steps, NOT-do guard, Report Format) but with all 5 lenses applied sequentially in one pass + the same aggregation framing | holds the procedural scaffold + lenses + aggregation constant with WITH, varying ONLY the fan-out delivery |
| **WITHOUT** | ONE agent, the bare neutral prompt | the unstructured baseline |

`WITH − WITHOUT` is the **primary** (total methodology) delta. Because MID carries
the **same per-dimension procedural scaffold** as WITH (reused from
`inquisitor-dimension-prompt-eval.md`, not a bare lens list), `WITH − MID` isolates
**only the fan-out delivery mechanism** — 5 parallel fresh subagents vs 1 sequential
agent — holding the lens content and the procedural methodology constant.
`MID − WITHOUT` is the combined dimension-scaffolding + procedure component.

## Invocation (module form)

Run from the repo root (the package uses relative imports, so `-m` is required):

```
python3 -m skills.inquisitor.evals.run_evals stage <run-id> [--trials N] [--fixture ID]
python3 -m skills.inquisitor.evals.run_evals score <run-id> [--allow-incomplete]
```

`--trials` defaults to **5** (the decision-run count; smoke runs may use 1–3; odd
counts recommended for the per-bug majority). `stage` prints the dispatch dir path.

## Workflow

1. **`stage`** renders, per `fixture × trial`, the three-arm dispatch files —
   **WITH = 6** (5 dimension dispatches + 1 aggregation dispatch), **MID = 1**,
   **WITHOUT = 1** — plus, **once**, the two shared deterministic prompt files
   `aggregation-prompt.md` and `judge-prompt.md` (byte-identical across all
   arms/cells; hashed in `stage-manifest.json`). It writes `stage-manifest.json`
   enumerating every cell.

2. **collect** (this document — the live orchestrator runs it; there is no
   `collect` subcommand). For each cell, read the manifest and dispatch the staged
   prompts **verbatim** — you author no framing, you paste staged files:
   - **WITH:** dispatch the 5 `*-with-dim*.md` dimension subagents **in parallel**,
     then dispatch the `*-with-agg.md` aggregation subagent fed the 5 dimension
     reports through the staged `aggregation-prompt.md`; it emits the one aggregated
     WITH report.
   - **MID:** dispatch the single `*-mid.md` all-lenses subagent.
   - **WITHOUT:** dispatch the single `*-without.md` neutral subagent.
   - **judge:** for each `(fixture, arm, trial)`, dispatch one judge subagent with
     the staged `judge-prompt.md` **verbatim** + that arm's output + the cell's
     tagged item list (below). Write each judge's output to the cell's
     `result_file` from the manifest using the `DISPATCH_STATUS: OK\n\n<body>`
     sentinel. Write `.collect-status` when every cell is done.

3. **`score`** reads `stage-manifest.json` + the judge verdict files and writes
   `skills/inquisitor/evals/last_run.json` + `results.md` (both git-ignored). It
   **refuses** to run without `.collect-status` unless `--allow-incomplete` (which
   stamps `complete: false` — smoke/debug only; the go/no-go must read a
   `complete: true` run).

## The judge contract (what the live judge grades, and what it emits)

The judge grades a single **tagged-union item list** per `(fixture, arm, trial)`,
**strictly per item** — for each item it answers *"Is THIS specific issue
identified in the arm's output? PASS / FAIL"*, never "which arm is better" (the
verbosity-bias control). The list is the union of two pools, each item carrying a
`tag`:

- **`primary`** — the K skill-independent ground-truth bugs from
  `ground-truth-bugs.json` (authored blind; the PRIMARY graded pool). Each
  primary item's `id` is its ground-truth `bug_id` (e.g. `f1-b1`).
- **`secondary`** — the dimension-bucketed `evals.json` expectations (a SECONDARY
  diagnostic pool only). Each secondary item's `id` is that expectation's
  index/key.

The single judge dispatch grades the whole tagged list — there is **no** second
judge pass; `score` then **partitions** the per-item verdicts by `tag` (`primary`
→ `graded_bugs` + the paired `deltas`; `secondary` → the `secondary_diagnostic`
block).

**Secondary-pool exclusion (collect-time):** drop **fixture-1 expectation #8** (the
dimension-counting, treatment-aligned expectation) from the secondary item list, so
the judge grades **26** secondary expectations (10−1 + 9 + 8) and
`secondary_diagnostic.graded_expectations == 26`, not 27.

**Per-item verdict-record output schema** — the judge emits **one JSON object per
graded item**, one per line, with exactly these fields (this is the exact format
`score` parses, so the live judge output and the parser cannot drift):

```
{"id": "f1-b1", "tag": "primary", "verdict": "PASS"}
{"id": "expectation-3", "tag": "secondary", "verdict": "FAIL"}
```

A `primary` item's `id` is its ground-truth `bug_id`; a `secondary` item's `id` is
its expectation index/key. A missing or malformed record for an item is counted as
`FAIL` and tallied into `malformed_verdicts`.

`scripts/check_judge_prompt_contract.py` pins this contract in CI (the `tag` /
`primary` / `secondary` references **and** the `id`+`tag`+`verdict` output record);
the unit tests feed only *synthetic* verdict files, so they cannot catch a judge
prompt that grades the wrong shape.

## `last_run.json` (what `score` computes)

Per-arm pass rates (`with`/`mid`/`without`, **majority-collapsed** per bug across
trials — strict majority PASS, an even-N tie → FAIL), the three paired `deltas`
(each carrying `paired` = the **mean of the per-trial paired deltas**, `trial_spread`
min–max band, `mde_heuristic`, and — for `with_without`/`with_mid` — `beyond_spread`),
`malformed_verdicts` per arm, `per_fixture` rates, `off_axis_diagnostic` (per-arm
rates over only the `off_axis: true` primary bugs — makes the design's T1 bias-control
machine-visible), and `secondary_diagnostic`.

`deltas` carries a `_note`: **`paired` is the mean of per-trial deltas and does NOT
equal `rate_with − rate_without`** (the per-arm rate is the majority-collapsed value,
a different collapse rule). `beyond_spread` is forced `false` for `trials < 3` (a 1–2
trial band trivially excludes zero).

`mde_heuristic` = `1.96 × sample-stdev(per-trial paired deltas, ddof=1) / sqrt(trials)`
(null for `trials < 2`) — an explicitly **no-α** noise-floor figure, not a
significance test.

## Files

- `run_evals.py` — `stage` + `score` (no `collect`).
- `inquisitor-dimension-prompt-eval.md` — the WITH dimension template (the real
  lenses, execution stubbed) **and the single source of lens content**: its
  `## Dimension Reference` blocks feed both the WITH per-dimension renders and the
  MID all-lenses render (no lens text is duplicated).
- `aggregation-prompt.md`, `judge-prompt.md` — the two shared staged prompts.
- `ground-truth-bugs.json` — the blind-authored primary bug list, with
  `ground-truth-bugs.provenance.md` (the exact blind input) +
  `scripts/check_ground_truth_provenance.py` proving the blind boundary held.
- `_dispatch_paths.py`, `_runid.py` — copied from temper. The drift check
  `scripts/check_inquisitor_helper_drift.py` is **function-scoped** to the functions
  inquisitor imports (`resolve_dispatch_dir` / `fixture_sha` / `template_sha` /
  `validate_run_id`), so `_runid.py` may omit temper's unused `sanitize_summary` /
  `validate_prefix` without reddening CI.
- `test_run_evals_stage.py`, `test_run_evals_score.py`, `test_runid.py` — the gating
  unit tests (stdlib `unittest`, run by `scripts/run_tests.sh`).

**Deferred (post-merge, not in CI):** the live integration run that produces the
actual delta (dispatches live Opus agents), recording it in `docs/evals.md`, and the
Phase-2 go/no-go log on #424.

## Phase 1b — seeded-repo execution measurement (4 arms + a deterministic oracle)

Phase 1 measured *identification breadth* with the run step stubbed and a 100%
ceiling. Phase 1b is the terminal **detection-axis** measurement: real
write-AND-run execution against hermetic seeded repos, scored by a deterministic
differential oracle (no LLM judge). See
`docs/plans/2026-06-15-inquisitor-phase1b-execution-eval-design.md`.

It is **forked behind the manifest `mode` field** so the Phase-1 path above is
byte-untouched: a manifest with no `mode` runs the 3-arm judge `score`; a
`mode:"phase1b-exec"` / `mode:"pilot"` manifest runs `score_exec` (the oracle).

**Arms (4):** WITH (5 lensed agents), POOL (5 bare agents — the pooling-only
control), MID (1 all-lenses agent), WITHOUT (1 bare agent). `WITH−WITHOUT` is the
primary; `WITH−POOL` isolates lenses; `POOL−WITHOUT` isolates pooling; `WITH−MID`
parallel-vs-sequential. Per-**agent** 5-test budget (no per-arm 25 ceiling — the
per-arm scaling IS the pooling treatment).

**CLI:**

```
python3 -m skills.inquisitor.evals.run_evals stage <run-id> --exec [--repo ID] [--trials N]
python3 -m skills.inquisitor.evals.run_evals stage <run-id> --pilot [--repo ID] [--trials N>=3]
python3 -m skills.inquisitor.evals.run_evals score <run-id> [--allow-incomplete]
```

`--exec` stages all 4 arms over the seeded repos (one repo copy per producer);
`--pilot` stages the hash-pinned neutral proxy only (≥3-trial floor) for the §5
fixture-difficulty calibration band (40–70%).

**Collect-output contract (C4 — what the human collector writes per cell).** Each
cell's `result_file` (named `<key>-tests.json` in `stage-manifest.json`) is a JSON
object the collector writes after the producer agent finishes. `_exec_cell_caught`
hard-depends on two fields and **fails loud** on either:
- `"dispatch_status": "OK"` — anything else aborts `score` for that run.
- `"test_files": [...]` — the producer's harvested test files as **ABSOLUTE**
  paths. A relative path is a fatal error (the oracle runs each file against
  pristine variants from a different cwd, so a relative path would silently miss).
The oracle harvests only these test files; it ignores any agent source edits or
self-reported pass/fail.

**Files:**

- `fixtures/<repo>/` — 3 hermetic seeded Python repos (`notify`, `rbac`,
  `paginate`), ~8 behaviorally-independent cross-component seam bugs each, with
  per-bug `fixes/<id>.patch` + `exemplars/<id>.py` + blind `ground-truth-bugs.json`
  (+ provenance). Format spec in `fixtures/README.md`.
- `_fixtures.py` — variant materialization (`base` / `all-fixed` /
  `all-fixed-minus-Bᵢ`, zero-fuzz `patch -p1`) + the shared `run_test_in_dir` +
  `rc_to_verdict` (rc 5 = ERROR).
- `_oracle.py` — the leave-one-out + mandatory-red-on-base scorer (no specificity
  gate — the `minus-Bᵢ` *variant* has only Bᵢ unfixed, so any RED there is Bᵢ's; a
  broad test is credited to EACH independent bug; twice-run flake guard;
  registered-`interacting_set` escape). Harvests test files only → runs on pristine
  variants, so agent source edits / self-reported pass-fail are irrelevant. The
  scoring unit is the FILE (one over-strict/flaky/import-erroring function sinks the
  file); discards are surfaced as `flaky_discards` + `errored_discards` (all-fixed
  anchor) + `errored_minus_discards` (a stable ERROR on a minus-Bᵢ variant — every
  discard channel observable), and the prompts ask for one self-contained test per
  file so the penalty is arm-uniform.
- `without-prompt-eval.md` — the bare execution prompt, the **single source**:
  `pool-prompt-eval.md` is byte-identical; `neutral-proxy-prompt-eval.md` is it with
  the cross-component framing removed.
- `_build_collect_args.py` — the no-judge producer dispatch list for collect.
- `test_fixtures.py`, `test_oracle.py`, `test_run_evals_exec.py`,
  `test_build_collect_args.py` — gating unit tests.

**CI guards (in `run_tests.sh`):** `check_fixture_independence.py` (the green/red
leave-one-out matrix + patch disjointness), `check_fixture_gt_provenance.py` (blind
boundary + post-blind off_axis), `check_fixture_producer_blind.py` (the producer
copy is blind: no answer-key path, no leak token, no GT-description prose — incl.
a concatenated-docstring `--selftest`; stripped `src/` still compiles),
`check_inquisitor_phase1b_invariants.py` (POOL/scaffold/neutral hashes, 5-test
budget, arm sets, KEEP statistic = `beyond_spread`).

**KEEP statistic:** the §7 go/no-go reads `beyond_spread` on `with_without` (NOT
`trial_spread`) + positive sign on ≥2/3 repos, with a **WITHOUT-keyed** ceiling
check. `score_exec` surfaces these inputs in `last_run.json`; it emits no
keep/condemn verdict (the human reads the §7 branches).

**Local-dev note (M-2):** the oracle shells `python3 -m pytest` and maps the rc via
`_fixtures.rc_to_verdict` (0→GREEN, 1→RED, else→ERROR). CI pins `pytest==9.0.3`; run
local fixture/oracle checks against the **same pin** so the rc→verdict mapping (esp.
the rc-5 "no tests collected"→ERROR convention) matches CI.

**Deferred (explicit opt-in, NOT in this build):** the ~180-agent live decision
run (and the cheap neutral-proxy pilot before it), recording the result in
`docs/evals.md` / #424.
