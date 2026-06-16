# Bug-hunting task

You are given a Python repository. Write **and run** pytest tests that expose
**bugs** in the code.

The repository is at the path provided to you. Your tests must import the package
from its `src/` directory and run under `python3 -m pytest`.

## Budget

Write at most **5 tests**. Every test must actually execute and either pass or
fail — do **not** describe tests you do not run.

## What to do

1. Read the repository source.
2. Write up to 5 pytest tests that FAIL when a bug is present and PASS when the
   code is correct.
3. Run them with `python3 -m pytest` and iterate until they execute cleanly
   (no collection/import errors).
4. Leave your test file(s) in the repository's test directory.
