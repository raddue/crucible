# Minimalism-ladder eval harness (Phase 1 — harness only)

A standalone **live-codegen → execute → measure-LOC** eval harness for the
`#425` minimalism-ladder investigation. It scores candidate solutions on two
axes at once: do they stay **correct** (incl. absolute "carve-out" behaviours
that must never be deleted), and how **few non-test source lines** do they take?

This is **not** the parent mock-orchestration eval. The sibling A/B harness
(`skills/build/evals/run_evals.py` / `expectations.py` / `mock_dispatcher.py`)
mocks dispatch and checks orchestration behaviour against recorded expectations.
This subdir instead *runs real code* in a subprocess-free, in-process scorer and
counts its LOC. It deliberately reuses **none** of those parent modules.

> **Phase 1 scope:** the harness only. There is **no live LLM codegen** here yet
> — Phase 1 scores pre-generated fixture solution dirs. Wiring a real generator
> into the `codegen` seam, running the WITH/WITHOUT measurement, and any ladder
> *adoption* are Phase 2 of `#425`.

## Public API (importable as flat top-level names)

The committed dir name is hyphenated (the design's committed home), so it is not
a dotted package. `conftest.py` puts this dir on `sys.path`; the modules import
as `loc`, `scorer`, `decision`, `tasks`.

- **`loc.count_non_test_source_loc(solution_dir) -> int`** — the headline metric.
  Counts lines that, after `strip()`, are non-empty and don't start with `#`,
  across non-test `.py` files (test file = stem `startswith("test_")` or
  `endswith("_test")`). A deliberately simple line counter, not a tokenizer.
- **`tasks`** — `TASKS: dict[str, Task]` (`cli_wordcount`, `fixture_loader`),
  `load_task(name)`, `Task` (`.assertions`, `.carve_out_assertions`),
  `Assertion(name, check, carve_out=False)`. Each `check(solution_module)`
  returns `None` on pass and **raises** on fail. A carve-out check that asserts a
  *rejection* catches its expected exception internally and raises only when the
  rejection did **not** occur.
- **`scorer.score_solution(task, solution_dir, *, codegen=None) -> TrialResult`**
  — loads `solution.py` under a unique module name, runs each assertion with cwd
  set to `solution_dir` (restored even on raise), and returns a frozen
  `TrialResult(non_test_source_loc, assertion_pass_rate, carve_out_passed)`
  (`assertion_pass_rate` is over the non-carve-out correctness assertions only;
  carve-outs are graded separately by `carve_out_passed`). Any exception
  escaping a check counts as a fail. **`codegen` is the Phase-2 seam**
  (a `Callable[[Task], Path]` that would generate and return a solution dir);
  unused in Phase 1 — pass a populated `solution_dir` and leave it `None`.
- **`decision.decide(with_results, without_results, *, band="iqr") -> str`** in
  `{"adopt", "skip", "reject", "expand"}`. Ordered: reject → 0-LOC floor guard →
  correctness gate → reduction <15% → majority → borderline (expand if `n<10`
  else skip) → plain band-overlap → adopt. Bands are IQR by default
  (`statistics.quantiles(..., method="inclusive")`); `band="minmax"` is the
  alternative. Bands are SEPARATED iff `WITH_Q3 < WITHOUT_Q1`.

## Layout

```
loc.py / scorer.py / decision.py   # harness modules (stdlib only)
tasks/                             # pilot-task package (cli_wordcount, fixture_loader)
test_*.py                          # focused unit tests
test_acceptance.py                 # integration "done" definition
conftest.py                        # sys.path + fixture-collection guard
fixtures/                          # READ-ONLY pre-generated solution dirs (inputs, not tests)
```

`fixtures/` holds `minimal` / `bloated` / `carveout_violating` solution dirs per
task; they are **read-only inputs** to the scorer — do not edit them.

## Constraints

- **Stdlib only** — no external runtime deps (the bands use `statistics`).
- This dir stays a **non-package** (driven by `conftest.py`); `tasks/` *is* a
  package. Do not add a top-level `__init__.py` here.

## Running

```sh
python3 -m pytest skills/build/evals/minimalism-ladder/ -q
```

Requires `pytest` (the suite uses fixtures/parametrize). CI provisions
`pytest==9.0.3`; the gating `scripts/run_tests.sh` invokes exactly this command.
