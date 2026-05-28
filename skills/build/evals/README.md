# build-evals — eval gate for the build skill

`build` is the highest-leverage orchestrator in Crucible. Every "implement this" session routes through it. Without a gate, prompt edits to `skills/build/SKILL.md` ship blind. This harness gives the gate.

**v0.1 scope** (see `docs/plans/2026-05-28-304-build-eval-gate-design.md`):

- 4 mocked fixtures covering build's main orchestration paths (`b1` simple-feature, `b2` multi-file, `b3` bugfix/refactor, `b4` design-required halt)
- 1 smoke fixture verifying the eval-gate toggle is a no-op when env vars are unset
- k=3 majority threshold per fixture (manual replicates; no Python-driven orchestrator)
- No CI; no real-PR fixtures; no drift-delta calibration (v0.2)

## How the toggle works

Build's `## Mock Dispatch Mode (eval-gate)` section in SKILL.md is enabled when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set. Three env vars together replace the parts of build's runtime that would otherwise dispatch real subagents or ask the user questions:

| Env var | Behavior when set | When unset |
|---|---|---|
| `CRUCIBLE_BUILD_EVAL_MOCK_DIR` | Each `Use crucible:<skill>` / Task tool invocation is replaced by reading `<seq>-<template-name>.md` (fallback `<template-name>.md`) from this dir and treating it as the subagent's return | Real dispatch (production behavior) |
| `CRUCIBLE_BUILD_EVAL_MODE` | Pre-set answer (`feature` or `refactor`) to build's Mode Detection question | Build asks the user normally |
| `CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR` | Per-turn AskUserQuestion answers from `turn-<N>.md`; missing turn → halt | Build asks the user normally |

The dispatch file is still written normally (trace integrity); only the Task/Agent tool invocation is substituted. Missing mock → fast-fail with `MockNotFound` (no silent fallthrough).

## Running a fixture

```sh
# 1. Stage: prepares a tmpdir + env, returns JSON
python3 -m skills.build.evals.run_evals stage --fixture b1-simple-feature
#   { "workdir": "...", "env": { "CRUCIBLE_BUILD_EVAL_MOCK_DIR": "...", "HOME": "...", ... } }

# 2. In a fresh shell, cd to the workdir and export env vars
WD=/tmp/build-evals-work/b1-simple-feature-<hash>
cd "$WD"
export HOME="$WD/.home"
export CRUCIBLE_BUILD_EVAL_MOCK_DIR=".../mock-dispatch"
/build "Add a function get_user_email(user_id) to src/users.py..."

# 3. Score after build exits
python3 -m skills.build.evals.run_evals score --fixture b1-simple-feature --build-output "$WD"
```

The script wrapper does the same thing:

```sh
bash scripts/build-evals.sh stage --fixture b1-simple-feature
```

## k=3 majority threshold

Build's orchestrator (the LLM driving it) is non-deterministic. With sub-skills mocked from disk, expectation evaluation is deterministic — but build's orchestration path can vary across runs on identical inputs. **k=3 majority** is the noise filter: each fixture is run 3 times, fixture PASSes iff ≥2/3 trials satisfy all expectations.

k=3 is a coarse filter, not a statistical test. It does not measure the false-pass rate. v0.2 (real-PR fixtures + drift-delta) will quantify the rate.

## Smoke fixture (`smoke-no-mock`)

The mocked fixtures cannot prove that the production (unmocked) path still works — by construction, they never exercise it. The smoke fixture genuinely runs `/build` with real subagent dispatches against a trivial task, with **all three** `CRUCIBLE_BUILD_EVAL_*` env vars deliberately omitted from `stage`'s returned env dict. If smoke FAILS, build's SKILL.md edit broke production — rollback the SKILL.md edit before continuing.

- k=1 (real dispatch is expensive — ~10-30 minutes)
- Excluded from `run-all` by default; opt-in via `--include-smoke` (when run-all lands; v0.1 is manual)

## Test isolation

`stage` creates a fresh tmpdir as the project root, copies the fixture's `seed/` into it, runs `git init && commit` to establish a baseline, writes the baseline SHA to `<workdir>/.eval-baseline-sha` (used by the `working_tree_unchanged_from` expectation's `BASELINE` placeholder), and sets `HOME=<workdir>/.home` so build's `~/.claude/projects/<hash>/memory/` writes land in the tmpdir.

In v0.1 tmpdirs are **always preserved** (no automatic cleanup) — remove `/tmp/build-evals-work/` manually when done. `score` does not delete the workdir on PASS, and `stage` does not create a per-run dispatch session; both are v0.2 follow-ups.

## Adding a new fixture

1. Create `fixtures/<id>/fixture.json` with `id`, `task`, `expectations`. Optional: `mode` (`feature` or `refactor`), `no_mock: true` (for smoke-style fixtures), `_notes` (string, soft documentation).
2. Create `fixtures/<id>/seed/` with the starting file tree.
3. Create `fixtures/<id>/mock-dispatch/` with one `<seq>-<template>.md` per expected dispatch (or `<template>.md` for templates that fire multiple times).
4. Optional: `fixtures/<id>/mock-user-input/` with `turn-<N>.md` files for AskUserQuestion replies (or leave empty to test halt-for-input, as b4 does).
5. Run `stage`; in a fresh shell, run `/build "<task>"`; run `score`. Iterate.

Mock files follow the `<seq>-<template-name>.md` schema (e.g. `1-plan-writer.md`). When the orchestrator dispatches a template multiple times with equivalent expected outputs, drop the seq prefix: `plan-writer.md` is the fallback for ANY seq.

If `MockNotFound` fires on a template you didn't anticipate, rename your file to match what build actually dispatched. Do NOT add silent fallthrough — fast-fail is the design.

## Expectation types

| Type | Fields | What it checks |
|---|---|---|
| `file_exists` | `path` | path exists under workdir |
| `file_does_not_exist` | `path` | path is absent under workdir |
| `file_contains` | `path`, `pattern` | substring match |
| `function_defined` | `file`, `name` | AST-parsed; matches FunctionDef, AsyncFunctionDef, ClassDef, or class methods |
| `manifest_contains_dispatch` | `skill`, `count_min`, `count_max` | substring match against template/skill fields in manifest.jsonl |
| `manifest_does_not_contain` | `skill` | count==0 |
| `gate_ledger_phase_status` | `phase`, `status` | parses `build-gate-ledger.md` for the phase block's Status line |
| `working_tree_unchanged_from` | `baseline_sha` (or `"BASELINE"` to resolve from `<workdir>/.eval-baseline-sha`) | `git diff --quiet <sha>` |

Python-only for `function_defined` in v0.1.

## Pre-push reminder hook

`scripts/hooks/pre-push-build-evals.sh` is an opt-in reminder (not a gate) that fires when a push includes changes to `skills/build/SKILL.md` or build dispatch prompt templates. It prints a reminder asking whether the fixtures were re-run; it does not block the push. Install with:

```sh
cp scripts/hooks/pre-push-build-evals.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

Real enforcement (CI gate) is a v0.2 follow-up.

## Layout

```
skills/build/evals/
├── README.md                  (this file)
├── __init__.py
├── conftest.py                (makes the harness importable in tests)
├── expectations.py            (pluggable checkers)
├── fixture_loader.py          (load fixture.json → Fixture dataclass)
├── mock_dispatcher.py         (load(seq, template), load_user_input(turn))
├── run_evals.py               (stage/score + CLI)
├── test_expectations.py
├── test_fixture_loader.py
├── test_mock_dispatcher.py
├── test_run_evals.py
└── fixtures/
    ├── b1-simple-feature/    (feature mode, design skipped)
    ├── b2-multi-file/        (feature mode, design fires, dependency order)
    ├── b3-bugfix/            (refactor mode, contract-test-writer dispatch)
    ├── b4-design-required/   (feature mode, design returns NEEDS_CLARIFICATION, build halts)
    └── smoke-no-mock/        (real dispatch — verifies toggle is a no-op when unset)
```

Self-tests live alongside the modules (`skills/build/evals/test_*.py`) so the project-level `tests/` gitignore rule doesn't catch them. Run them with `pytest skills/build/evals/`.
