# Bug-hunting task

You are given a Python repository. Write **and run** pytest tests that expose
**cross-component bugs** — defects at the seams between modules (a producer and a
consumer disagreeing, a component not wired to another, state lost across a
lifecycle boundary, an unhandled edge between layers).

The repository is at the path provided to you. Your tests must import the package
from its `src/` directory and run under `python3 -m pytest`.

## Budget

Write at most **5 tests**. Every test must actually execute and either pass or
fail — do **not** describe tests you do not run. Put each test in its **own**
`test_*.py` file and keep it self-contained (import only from `src/`, not a
helper module you wrote): the scorer runs each file in isolation on a pristine
repo, so a file that over-asserts or imports an unharvested helper is discarded
whole.

## What to do

1. Read the repository source.
2. Write up to 5 pytest tests that FAIL when a seam bug is present and PASS when
   the code is correct.
3. Run them with `python3 -m pytest` and iterate until they execute cleanly
   (no collection/import errors).
4. Leave your test file(s) in the repository's test directory.
