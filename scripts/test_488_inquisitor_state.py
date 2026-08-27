#!/usr/bin/env python3
"""#488 c1 — inquisitor, State & Lifecycle dimension.

Cross-component tests for the ASSEMBLED #488 c1 build (base fa108d2 -> cc34349).
Each one exercises state that is created by one component and consumed by
another, which is the class of defect a per-task adversarial tester structurally
cannot see: it only ever saw one task's diff.

Run from repo root:  python3 scripts/test_488_inquisitor_state.py

WHY A SEPARATE FILE, not more classes on scripts/test_488_name_space.py.
`scripts/dec31_sweep.py` pins `TOTAL_TESTS` — a hard-coded snapshot of the NUMBER
of tests in test_488_name_space.py — and every one of its sixteen rows fails when
that count moves. Appending here keeps that count where it is, so these tests
cannot themselves perturb the very harness one of them measures.
"""
import contextlib
import hashlib
import importlib.util
import io
import pathlib
import signal
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent


def _import(name):
    """Import a scripts/ module by path — they are scripts, not a package."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rv = _import("rcpt_verify")


def _receipt(*, artifacts, trace, witness, verdict="PASS", claims=("(none)",)):
    lines = [f"RCPT v1 red-team/1-devils-advocate",
             f"VERDICT  {verdict}  conf=0.90", "ARTIFACTS"]
    lines += [f"  {n}  sha256:{h}  {s}" for n, h, s in artifacts]
    lines.append("TRACE")
    lines += [f"  {i}  {t}" for i, t in enumerate(trace, 1)]
    lines.append("CLAIMS")
    lines += [f"  {c}" for c in claims]
    lines += [f"WITNESS    {witness}", "SUSPICION  0.10", "NEXT       (none)"]
    return "\n".join(lines) + "\n"


class _RootCase(unittest.TestCase):
    """A dispatch root OUTSIDE the checkout, as §6 requires of every fixture root."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = pathlib.Path(self.td.name)

    def plant(self, relname, body):
        p = self.root / relname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return hashlib.sha256(body.encode()).hexdigest(), str(len(body))


# --------------------------------------------------------------------------
# Attack vector 2 — the DEC-31 mutant harness pins TOTAL_TESTS, a snapshot of
# another file's state, and scripts/run_tests.sh now runs it on every commit.
# The pin is state with a lifecycle: it is valid only until the suite it counts
# changes, and NOTHING enforces that the two move together. This is exactly the
# seam a per-task tester cannot see — Task 7 measured the count, and warden
# leg-1's temper fixes (a LATER commit, cc34349) added tests to the counted
# file. Observable behaviour under test: the harness's own baseline row, on the
# UNMUTATED shipped tree, must be clean.
# --------------------------------------------------------------------------
class TestASecondIdenticalRunInOneProcessRendersTheSameVerdict(_RootCase):

    def test_two_back_to_back_runs_are_byte_identical_on_both_channels(self):
        h, size = self.plant("sub/deep.md", "payload\n")
        other, osize = self.plant("elsewhere.md", "other\n")
        text = _receipt(
            artifacts=[("deep.md", h, size), ("elsewhere.md", other, osize)],
            trace=["READ sub/deep.md", "READ untouched.md"],
            witness="lint:all-claims-cited  expect-fail=exit!=0  ran=TRACE#1")
        rcpt = self.root / "rcpt.txt"
        rcpt.write_text(text)
        argv = ["--tier2", "--root", str(self.root), str(rcpt)]

        runs = []
        for _ in range(2):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = rv.main(list(argv))
            runs.append((code, err.getvalue()))

        self.assertEqual(
            runs[0], runs[1],
            "the second in-process run of an identical invocation did not "
            "reproduce the first: some accumulator, cache or module-level "
            "state survived the first run")
        # The run must actually have exercised the accumulators it is asserting
        # about, or the equality above is vacuous.
        self.assertIn("TIER2-COVERAGE:", runs[0][1])
        self.assertIn("RESOLVED-BY-WALK:", runs[0][1])
        self.assertIn("PROVENANCE-ONLY:", runs[0][1])


# --------------------------------------------------------------------------
# Attack vector 4 — process-global teardown. `_witness_bound` installs a SIGALRM
# handler and arms ITIMER_REAL for the duration of tier2_witness. That is the
# only PROCESS-WIDE state this feature mutates, and #488 added new code INSIDE
# the bound (the witness leg's `_emit_walk_note` site, rcpt_verify.py:3474). A
# leaked handler or a leaked one-shot timer would fire inside whatever ran next
# — the next receipt in a batch, or the importing harness — which is a failure
# no single-run test can observe.
# --------------------------------------------------------------------------
class TestTheWitnessBoundLeavesNoProcessWideResidue(_RootCase):

    def test_the_handler_and_the_timer_are_restored_on_both_exits(self):
        if not hasattr(signal, "SIGALRM"):
            self.skipTest("no SIGALRM on this platform")
        before_handler = signal.getsignal(signal.SIGALRM)
        before_timer = signal.getitimer(signal.ITIMER_REAL)

        # (a) a CLEAN witness leg, and (b) one that RAISES out of the bound.
        h, size = self.plant("f.md", "line one\nSECRET token\n")
        for expect_fail, should_raise in (("/NOTHERE/", False),
                                          ("/SECRET/", True)):
            text = _receipt(
                artifacts=[("f.md", h, size)],
                trace=["READ f.md"],
                witness=f"exec:probe  expect-fail={expect_fail}  ran=TRACE#1")
            sections = rv.parse_receipt(text)
            trace = rv.parse_trace(sections["TRACE"])
            witness = rv.parse_witness(sections["WITNESS"])
            raised = False
            try:
                rv.tier2_witness(witness, trace, self.root, True, "PASS",
                                 rv._Coverage(), {}, {}, [])
            except rv.LintError:
                raised = True
            self.assertEqual(should_raise, raised,
                             f"fixture for expect-fail={expect_fail} is inert")

            self.assertIs(
                before_handler, signal.getsignal(signal.SIGALRM),
                f"tier2_witness left its SIGALRM handler installed "
                f"(expect-fail={expect_fail}); the next thing this process "
                f"runs would take a WitnessTimeout it never armed")
            self.assertEqual(
                before_timer, signal.getitimer(signal.ITIMER_REAL),
                f"tier2_witness left ITIMER_REAL armed "
                f"(expect-fail={expect_fail})")


if __name__ == "__main__":
    unittest.main(verbosity=1)
