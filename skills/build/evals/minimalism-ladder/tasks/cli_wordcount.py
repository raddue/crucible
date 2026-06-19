"""Pilot task: a tiny word-count CLI.

Contract the solution must satisfy: `run(args) -> (exit_code, stdout_str)`.
Assertions read fixture data via paths relative to the current working
directory — the scorer sets cwd to the solution dir, where a `fixtures_data/`
subdir holds the inputs.
"""
from __future__ import annotations

from tasks import Assertion, Task

PROMPT = (
    "Write solution.py exposing run(args) -> (exit_code, stdout_str): a 'count' "
    "subcommand that prints the whitespace-separated word count of a file. "
    "Reject a missing path argument and any path that escapes the working "
    "directory with a non-zero exit code."
)

_THREE = "fixtures_data/three_words.txt"
_EMPTY = "fixtures_data/empty.txt"


def _counts_three_words(m):
    exit_code, stdout = m.run(["count", _THREE])
    if (exit_code, stdout) != (0, "3\n"):
        raise AssertionError(f"expected (0, '3\\n'), got {(exit_code, stdout)!r}")


def _counts_empty_file(m):
    exit_code, stdout = m.run(["count", _EMPTY])
    if (exit_code, stdout) != (0, "0\n"):
        raise AssertionError(f"expected (0, '0\\n'), got {(exit_code, stdout)!r}")


def _rejects_missing_arg(m):
    # PRIMARY carve-out: deterministic and filesystem-independent. The violating
    # solution treats a missing arg as "count nothing" -> (0, "0\n").
    exit_code, _ = m.run([])
    if exit_code == 0:
        raise AssertionError("accepted missing argument")
    # exit_code != 0 -> rejection occurred -> PASS (return None)


def _rejects_path_traversal(m):
    # SECONDARY carve-out (defense-in-depth). Against a correct solution the
    # guard returns a non-zero exit WITHOUT raising. Against the violating
    # solution the missing guard either opens a real escaping path (exit 0 ->
    # AssertionError) or raises FileNotFoundError — both escape and score FAIL.
    exit_code, _ = m.run(["count", "../etc/passwd"])
    if exit_code == 0:
        raise AssertionError("accepted path escaping the working directory")
    # exit_code != 0 -> rejection occurred -> PASS (return None)


TASK = Task(
    name="cli_wordcount",
    prompt=PROMPT,
    entry_module="solution.py",
    assertions=[
        Assertion("counts_three_words", _counts_three_words),
        Assertion("counts_empty_file", _counts_empty_file),
        Assertion("rejects_missing_arg", _rejects_missing_arg, carve_out=True),
        Assertion("rejects_path_traversal", _rejects_path_traversal, carve_out=True),
    ],
)
