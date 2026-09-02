#!/usr/bin/env python3
"""Adversarial runtime tests for scripts/complexity_index.py (#558).

Attacks, not contracts: malformed/hostile inputs against observable CLI and
API behavior. Pure stdlib `unittest`, direct-import (repo root on sys.path),
tmp-dir fixtures only — no machine state touched.

Run:  python3 scripts/test_complexity_index_adversarial.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import complexity_index as ci  # noqa: E402

SCRIPT = os.path.join(HERE, "complexity_index.py")

_BRANCHY = ("def hot(a):\n    x = a\n"
            + "".join(f"    if x != {i}:\n        x += {i + 1}\n"
                      for i in range(16))
            + "    return x\n")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _run_cli(args, cwd):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


class AdversarialTest(unittest.TestCase):
    def test_attack_non_utf8_diff_file_must_not_crash_cli(self):
        """Failure mode: --diff points at a binary/non-UTF-8 file (wrong
        file, gzipped diff). The CLI's read path only guards OSError, so a
        UnicodeDecodeError escapes as an uncaught traceback. Robust
        behavior: nonzero exit with the same clean one-line diagnostic used
        for a missing --diff file, and no traceback."""
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), _BRANCHY)
            diff_path = os.path.join(root, "bad.diff")
            with open(diff_path, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x01garbage\xff\x81")
            r = _run_cli(["score", "mod.py", "--diff", diff_path], cwd=root)
            self.assertNotEqual(r.returncode, 0,
                                "a binary --diff file must not score as a "
                                "success")
            self.assertNotIn(
                "Traceback", r.stderr,
                "UnicodeDecodeError from a binary --diff file escapes as an "
                "uncaught exception instead of a clean diagnostic")
            self.assertIn("cannot read --diff file", r.stderr)

    def test_attack_utf8_bom_source_silently_dropped(self):
        """Failure mode: a Python source file carries a UTF-8 BOM — legal
        Python (CPython accepts BOM-prefixed source), common in
        Windows-edited repos. Reading with plain utf-8 leaves the BOM in
        the string and ast.parse rejects it, so the file is silently
        dropped. Robust behavior: the function surfaces exactly as in the
        BOM-free twin file."""
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "bom.py"), "w",
                      encoding="utf-8-sig") as fh:
                fh.write(_BRANCHY)
            _write(os.path.join(root, "plain.py"), _BRANCHY)
            twin = ci.top_functions(["plain.py"], root, limit=0)
            self.assertEqual(
                [(e["qualname"], e["complexity"]) for e in twin],
                [("hot", 17)], "sanity: BOM-free twin surfaces")
            entries = ci.top_functions(["bom.py"], root, limit=0)
            self.assertEqual(
                [(e["qualname"], e["complexity"]) for e in entries],
                [("hot", 17)],
                "valid Python source with a UTF-8 BOM is silently scored "
                "as zero — the file vanishes from the index")

    def test_attack_duplicate_paths_double_count(self):
        """Failure mode: the same file reaches the batch twice (caller
        concatenates overlapping path sources, argv repeats a file). Each
        occurrence is scored independently, so every function is reported
        twice and the ranked signal double-counts. Robust behavior: one
        entry per (path, qualname)."""
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), _BRANCHY)
            entries = ci.top_functions(["mod.py", "mod.py"], root, limit=0)
            self.assertEqual(
                [(e["path"], e["qualname"], e["complexity"])
                 for e in entries],
                [("mod.py", "hot", 17)],
                "duplicate input paths double-report every function — the "
                "ranked signal counts the same function twice")

    def test_attack_binary_source_file_isolated_in_batch(self):
        """Failure mode: a non-UTF-8/binary file masquerading as .py sits
        BEFORE good files in the batch (read raises UnicodeDecodeError — a
        different exception class than the SyntaxError/missing-file cases
        covered elsewhere). Robust behavior: the bad file is swallowed and
        every good file still contributes."""
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "bin.py"), "wb") as fh:
                fh.write(b"\x00\x01\xff\xfedef not_python(\n")
            _write(os.path.join(root, "good_a.py"), _BRANCHY)
            _write(os.path.join(root, "good_b.py"),
                   _BRANCHY.replace("hot", "cold"))
            entries = ci.top_functions(
                ["bin.py", "good_a.py", "good_b.py"], root, limit=0)
            self.assertEqual(
                {(e["path"], e["qualname"], e["complexity"])
                 for e in entries},
                {("good_a.py", "hot", 17), ("good_b.py", "cold", 17)},
                "a decode-error file must be isolated like any other bad "
                "file; the rest of the batch still contributes")

    def test_attack_cli_outside_any_git_repo(self):
        """Failure mode: the CLI runs in a cwd that is not inside a git
        repository (scratch checkout, tarball extract). repo-root
        resolution shells out to `git rev-parse`; if its empty output is
        mishandled the fallback breaks and every file scores as missing.
        Robust behavior: cwd fallback, correct ranked output, exit 0."""
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), _BRANCHY)
            self.assertFalse(
                os.path.exists(os.path.join(root, ".git")),
                "fixture must not be a git repo")
            r = _run_cli(["score", "mod.py"], cwd=root)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("mod.py::hot (CC 17, 35 lines)", r.stdout,
                          "outside a git repo the CLI must fall back to "
                          "cwd and still score")
            self.assertNotIn("Traceback", r.stderr)


# Executed-test-count guard — the Python counterpart of the bash carrier's
# EXPECTED_CHECKS pin (hooks/tests/test-grudge-resolution-guard.sh). `unittest`
# exits 0 on a fully skipped suite, so a return code alone cannot distinguish
# "every contract test passed" from "every contract test was skipped, dropped
# or renamed away". Assert how many tests actually EXECUTED: collected, minus
# skips, minus expected-failures/unexpected-successes (all three keep a test in
# testsRun while neutering its assertions). Bump this when adding a test.
EXPECTED_TESTS = 5


def _run_with_count_guard():
    """Run the suite; fail loudly if fewer than EXPECTED_TESTS actually ran."""
    result = unittest.main(exit=False, verbosity=2).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        # argv selects a subset (single test, -k, --failfast): the total is not
        # comparable, so report the exemption instead of asserting a wrong count.
        print("NOTE: executed-count guard not applied — argv selects a subset: "
              + " ".join(sys.argv[1:]), file=sys.stderr)
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} contract tests to execute, "
              f"ran {executed} ({result.testsRun} collected, {len(inert)} "
              f"skipped/expected-failed) — a test was skipped, dropped or "
              f"renamed", file=sys.stderr)
        for case, reason in inert:
            print(f"  did not execute: {case} ({reason})", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())
