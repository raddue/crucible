#!/usr/bin/env python3
"""#488 c1 — inquisitor / Integration dimension: cross-component tests.

Run from repo root:  python3 scripts/test_488_inquisitor_integration.py

These are NOT per-task tests. Each one drives the CLI through the MANDATED
two-root production invocation (`quality-gate/SKILL.md` › Receipt Linter:
`--tier2 --strict --root <dispatch-root> --root <findings-root>`) and asserts a
fact that only emerges when two or more components are wired together — the
Tier-1 v1.1 rules against the Tier-2 leg dispatch, the ARTIFACTS leg's carry
against the witness leg's read, or the parser's `(none)` sentinel against the
provenance advisory and the census. A per-task adversarial tester saw one task's
diff and could not reach any of them.

Own FILE rather than new classes in `scripts/test_488_name_space.py`,
deliberately: `scripts/dec31_sweep.py` pins that suite's exact test COUNT
(`TOTAL_TESTS`) and each mutant row's exact failing-test SET, so appending here
would redden the DEC-31 harness on the count guard and on every row these tests
reach. The cost is stated so it is not discovered later: the sweep runs
`SUITE = "scripts/test_488_name_space.py"` and nothing else, so the pins in THIS
file are not exercised against the fifteen deliberately-broken builds.
"""
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rcpt_verify.py"
H64 = "a" * 64


def census(stderr):
    """The single TIER2-COVERAGE: line, or '' when the run emitted none."""
    for l in stderr.splitlines():
        if l.strip().startswith("TIER2-COVERAGE:"):
            return l.strip()
    return ""


class _TwoRootCase(unittest.TestCase):
    """The mandated two-root shape: a dispatch root and a findings root, both
    OUTSIDE the checkout so no committed file can satisfy a cited name by
    accident, and SIBLINGS rather than nested (`quality-gate/SKILL.md` › layout
    pin (b): `<findings-root>` is the run's scratch directory, not a
    subdirectory of the dispatch root)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.dispatch = base / "dispatch"
        self.findings = base / "scratch"
        self.dispatch.mkdir()
        self.findings.mkdir()

    def plant(self, root, relname, body):
        p = pathlib.Path(root) / relname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return hashlib.sha256(body.encode()).hexdigest(), str(len(body))

    def verify(self, text, name="rcpt.txt"):
        p = self.dispatch / name
        p.write_text(text)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--tier2", "--strict",
             "--root", str(self.dispatch), "--root", str(self.findings), str(p)],
            capture_output=True, text=True)


# --------------------------------------------------------------------------
# Attack vector 2 — the ARTIFACTS leg's hashed-AND-MATCHED buffer must reach
# the witness leg when the two legs SPELL the same file differently, which
# return-convention.md § "Citation resolution" mandates they do.
# --------------------------------------------------------------------------
class TestTheTwoLegsBindOneBufferAcrossTwoSpellingsOfOneFile(_TwoRootCase):
    """SIEGE-R2BA-1's REALPATH key, at the CLI, on the two-root line.

    `tier2_artifacts` carries each hash-matched buffer under BOTH the declared
    ARTIFACTS name and the resolved realpath, and `tier2_witness` consults the
    name first and the realpath second. The existing pins for that carry
    (`TestRangelessGrepReportsWhetherTheReadWasBound` in
    `scripts/test_rcpt_verify.py`) declare the artifact and cite it in TRACE
    under the SAME spelling and against ONE root, so they exercise the NAME key
    only — the realpath key can be deleted and they stay green.

    This fixture is the shape the convention actually mandates: the findings
    file is declared in ARTIFACTS by BARE BASENAME (the findings-file location
    pin) and cited in TRACE by ABSOLUTE PATH (§3.2's mandated TRACE form), and
    a RANGELESS `kind=grep` witness takes its artifact name from that cited
    TRACE entry verbatim — so the name key MISSES by construction and only the
    realpath key can bind.

    Why the failure would be silent, and why that makes it this dimension's
    business: an unbound run still reads real bytes, still evaluates the
    predicate, and is still billed `witness 1/1` at exit 0. The only difference
    is that the predicate ran against a SECOND, independent read of a file the
    reviewed subagent owns — the mid-lint swap window the carry was written to
    close — reported on two advisory channels and nowhere in the exit code.
    """

    def setUp(self):
        super().setUp()
        h, s = self.plant(self.findings, "round-3-findings.md",
                          "# Round 3 findings\nFatal: 0\n")
        self.out = self.verify("\n".join([
            "RCPT v1 red-team/1-devils-advocate",
            "VERDICT  PASS  conf=0.90",
            "ARTIFACTS",
            f"  round-3-findings.md  sha256:{h}  {s}",
            "TRACE",
            f"  1  WROTE  {self.findings}/round-3-findings.md  sha256:{h}",
            "CLAIMS",
            "  (none)",
            "WITNESS    grep:round-3-findings.md  "
            "expect-fail=/Fatal: [1-9]/  ran=TRACE#1",
            "SUSPICION  0.10",
            "NEXT       (none)",
        ]) + "\n")

    def test_the_run_verifies_both_legs(self):
        # Non-vacuity: the fixture reaches the witness leg and both legs
        # complete, so the assertions below are about a run that happened.
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        c = census(self.out.stderr)
        self.assertIn("artifacts 1/1", c, c)
        self.assertIn("witness 1/1", c, c)

    def test_the_predicate_is_bound_to_the_bytes_the_other_leg_hashed(self):
        """`unhashed-body` is the census's DISAGREEMENT code and the
        `independent read` note is its stderr twin. Both would appear if the
        realpath key stopped covering the two-spellings case — on a receipt
        whose file WAS hash-verified on the same run."""
        c = census(self.out.stderr)
        self.assertIn("wrong-name 1 (rangeless-grep-payload)", c, c)
        self.assertNotIn("unhashed-body", c, c)
        self.assertNotIn("independent read", self.out.stderr)

    def test_the_absolute_trace_citation_is_not_reported_as_unverified(self):
        """The provenance advisory's basename key is the third component in
        this seam: §3.2 makes the two legs spell one file differently BY
        DESIGN, so a build that keyed the advisory on the literal name would
        call this verified file unverified on the same stderr that bills it
        `artifacts 1/1`."""
        self.assertNotIn("PROVENANCE-ONLY:", self.out.stderr)


# --------------------------------------------------------------------------
# Attack vector 3 — `(none)` empties ARTIFACTS; three independent channels
# must each still say that the witness ran against a file nothing hashed.
# --------------------------------------------------------------------------
class TestAnEmptyArtifactsSetCannotSilenceTheUnhashedWitnessRead(_TwoRootCase):
    """T3's `(none)` sentinel against T2's provenance advisory against the
    witness leg's billing — three components, one receipt.

    `(none)` is the one legal spelling that empties ARTIFACTS wholesale, so it
    is also the cheapest way for a receipt author to arrange that NOTHING is
    hash-verified. A rangeless `kind=grep` witness carries no
    ARTIFACTS-membership rule (#412 deliberately does not gate the cited
    TRACE entry's name), so the predicate still resolves a real file, reads it
    and runs — and the run still exits 0 with `witness 1/1`.

    What must not go quiet is the reporting, on all three channels at once:
    the census's disagreement code, the witness leg's `independent read` note,
    and the provenance advisory for the TRACE entry naming a file no ARTIFACTS
    line declares. Each is produced by a different component from a different
    fact, and every one of them is what an operator (or #488's proposed
    `--strict` floor) reads to tell this run apart from a genuine
    verification. A per-task tester could see at most one of the three.
    """

    def setUp(self):
        super().setUp()
        # A REAL file the receipt never declares: the witness resolves and
        # reads it, and no sha256 is ever recomputed for it.
        self.plant(self.findings, "round-3-findings.md",
                   "# Round 3 findings\nFatal: 0\n")
        self.out = self.verify("\n".join([
            "RCPT v1 red-team/1-devils-advocate",
            "VERDICT  PASS  conf=0.90",
            "ARTIFACTS",
            "  (none)",
            "TRACE",
            f"  1  WROTE  round-3-findings.md  sha256:{H64}",
            "CLAIMS",
            "  (none)",
            "WITNESS    grep:round-3-findings.md  "
            "expect-fail=/Fatal: [1-9]/  ran=TRACE#1",
            "SUSPICION  0.10",
            "NEXT       (none)",
        ]) + "\n")

    def test_the_witness_still_ran_and_the_run_still_exits_zero(self):
        # Non-vacuity: this is the shape the three channels have to describe.
        # A build that hard-FAILed here would pass the three assertions below
        # for the wrong reason.
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        c = census(self.out.stderr)
        self.assertIn("artifacts 0/0", c, c)
        self.assertIn("witness 1/1", c, c)

    def test_the_census_carries_the_disagreement_code(self):
        c = census(self.out.stderr)
        self.assertIn("wrong-name 1 (rangeless-grep-payload,unhashed-body)", c, c)

    def test_the_witness_leg_says_the_read_was_independent(self):
        self.assertIn("UNVERIFIABLE: witness round-3-findings.md "
                      "(predicate evaluated against an independent read", self.out.stderr)

    def test_the_trace_citation_of_that_undeclared_name_is_not_silent(self):
        """The provenance advisory keys on the VERIFIED basename set, which
        `(none)` leaves empty — so the emitter must still walk TRACE and report
        the citation. Silence here is grudge e0f0a6b75692's direction: one
        `(none)` line buying quiet on every undeclared read in the receipt."""
        self.assertIn("PROVENANCE-ONLY: round-3-findings.md "
                      "(declared in TRACE, not verified)", self.out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
