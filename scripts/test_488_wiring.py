#!/usr/bin/env python3
"""#488 c1 — inquisitor/Wiring: cross-component connection tests.

Run from repo root:  python3 scripts/test_488_wiring.py

These are NOT more acceptance tests for the receipt name space; `scripts/
test_488_name_space.py` owns that. Each class here asserts that a component this
build ADDED is actually connected to the component it was wired into — the seam
a per-task adversarial tester could not see, because it only ever held one task's
diff.

DELIBERATELY A SEPARATE FILE: `skills/` is outside `dec31_sweep.py`'s
`COPY_DIRS`, so `TestTheCensusLineMatchesTheConventionItDeclares`, which reads
`skills/shared/return-convention.md`, could not have lived in
`scripts/test_488_name_space.py`.

Attack vectors 1 and 2 (the sweep's kept tree vs. `run_tests.sh`'s `$TMPDIR`
trap; the sweep's hard-pinned `TOTAL_TESTS`) were FIXED and their tests promoted
to the permanent `scripts/test_dec31_sweep_harness.py`, which IS gated.

Wired into `scripts/run_tests.sh` (the two vectors above having been fixed and
promoted is what made that safe to do).
"""
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "rcpt_verify.py"
CONVENTION = REPO / "skills" / "shared" / "return-convention.md"
RULING = REPO / "docs" / "plans" / "2026-08-21-488-c1-name-space-reduced.md"


def receipt(*, artifacts=(), trace=(), verdict="PASS"):
    """A minimal well-formed RCPT v1 receipt, same shape as the acceptance
    suite's helper. The `lint:` witness kind is deliberate: a ranged `grep:`
    witness carries an ARTIFACTS-membership rule that would reject these
    fixtures at Tier-1 for an unrelated reason."""
    lines = ["RCPT v1 red-team/1-devils-advocate",
             f"VERDICT  {verdict}  conf=0.90", "ARTIFACTS"]
    lines += [f"  {n}  sha256:{h}  {s}" for n, h, s in artifacts] or ["  (none)"]
    lines.append("TRACE")
    lines += [f"  {i}  {t}" for i, t in enumerate(trace, 1)] or ["  (none)"]
    lines += ["CLAIMS", "  (none)",
              "WITNESS    lint:all-claims-cited  expect-fail=exit!=0  ran=TRACE#1",
              "SUSPICION  0.10", "NEXT       (none)"]
    return "\n".join(lines) + "\n"


class TestTheCensusLineMatchesTheConventionItDeclares(unittest.TestCase):
    """ATTACK VECTOR 3 — this build added an EIGHTH counter (`resolved-by-walk`) to
    the single `TIER2-COVERAGE:` line, and that line is a three-party contract:
    `rcpt_verify.py` produces it, `skills/shared/return-convention.md` declares its
    field list verbatim in a code fence, and `skills/quality-gate/SKILL.md` (:36,
    :296) is the live consumer that reads counters out of it and captures it into
    `round-N-coverage.md`.

    A new counter inserted at the wrong POSITION, or documented at a position it is
    not emitted at, desynchronises producer and contract while every existing test
    still passes — the acceptance suite asserts substrings like `resolved-by-walk 1`,
    which are position-blind, and `scripts/test_rcpt_verify.py`'s full-literal
    assertions were rewritten from the code rather than from the convention.

    This test takes the CONVENTION as the authority and compares it against a live
    CLI run, which is the direction no existing test checks. It cannot live in
    `scripts/test_488_name_space.py`: `dec31_sweep.py` does not copy `skills/` into
    its mutant trees, so a test reading the convention would error on all 16 rows."""

    def _documented_fields(self):
        fence = re.search(r"^```\n(TIER2-COVERAGE: artifacts .*?)\n```",
                          CONVENTION.read_text(), re.M | re.S)
        self.assertIsNotNone(fence, "the convention's census fence moved")
        line = fence.group(1)
        # Strip the two ratios and the optional trailing flag; what remains is the
        # ordered counter-name list, each followed by its `<n>` placeholder.
        line = line.replace("TIER2-COVERAGE: ", "")
        line = re.sub(r"^artifacts <verified>/<applicable> "
                      r"witness <verified>/<applicable> ", "", line)
        line = line.replace(" [partial]", "")
        toks = line.split()
        return [t for t in toks if t != "<n>"]

    def _emitted_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            body = "hello\n"
            (root / "note.txt").write_text(body)
            h = hashlib.sha256(body.encode()).hexdigest()
            text = receipt(artifacts=[("note.txt", h, len(body))],
                           trace=[f"WROTE  note.txt  sha256:{h}"])
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--tier2", "--root", str(root), "-"],
                input=text, capture_output=True, text=True)
        line = next((l.strip() for l in proc.stderr.splitlines()
                     if l.strip().startswith("TIER2-COVERAGE:")), "")
        self.assertTrue(line, proc.stderr)
        self.assertNotIn("not-reached", line, proc.stderr)
        rest = re.sub(r"^TIER2-COVERAGE: artifacts \d+/\d+ witness \d+/\d+ ",
                      "", line)
        rest = rest.replace(" partial", "")
        # Counter names alternate with their integer values; a counter that
        # recorded reason codes also carries them as a `(a, b)` parenthetical in
        # its own printed position, which is not part of the field list.
        rest = re.sub(r"\([^)]*\)", "", rest)
        return [t for t in rest.split() if not t.isdigit()]

    def test_the_counter_names_and_their_order_are_the_documented_ones(self):
        self.assertEqual(
            self._emitted_fields(), self._documented_fields(),
            "the TIER2-COVERAGE: field list rcpt_verify.py emits is not the one "
            "skills/shared/return-convention.md declares; quality-gate/SKILL.md "
            "reads this line.")


class TestTheRulingDocumentIsTrackedAndNotJustPresent(unittest.TestCase):
    """ATTACK VECTOR 4 — `docs/plans/` is gitignored, and this build re-includes ONE
    file with a `.gitignore` negation (`docs/plans/*` + `!…-488-c1-…md`) because
    `scripts/test_488_name_space.py`'s AC-1 test reads it and `dec31_sweep.py` copies
    `docs/` into every mutant tree.

    Both of those check the WORKING COPY. On the machine that wrote the file it is
    on disk whether or not git tracks it, so if the negation ever regresses — a
    merge, or a revert of `docs/plans/*` back to `docs/plans/` — every local check
    stays green and the breakage appears only in a fresh clone: AC-1 fails and all
    sixteen sweep rows skew by the +1 failure / +1 error its own docstring warns
    about ("`docs` is NOT optional").

    That is a CI-only failure whose cause is a line in `.gitignore`, three
    components away from either test. This asserts the property the ignore rule
    actually has to hold."""

    def test_the_ruling_is_tracked_by_git(self):
        rel = RULING.relative_to(REPO).as_posix()
        proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                              cwd=REPO, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         f"{rel} is not tracked by git; a fresh clone will not "
                         f"have it. {proc.stderr.strip()}")

    def test_the_ruling_is_not_ignored(self):
        rel = RULING.relative_to(REPO).as_posix()
        proc = subprocess.run(["git", "check-ignore", "-v", rel],
                              cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(
            proc.returncode, 0,
            f"{rel} matches a .gitignore rule ({proc.stdout.strip()}); the "
            "negation that re-includes it has regressed.")


if __name__ == "__main__":
    unittest.main(verbosity=1)
