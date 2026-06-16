#!/usr/bin/env python3
"""Tests for _oracle.py — the differential leave-one-out scorer (#424 Phase 1b §4).

stdlib unittest. Built against canned test files + a toy 3-bug repo (b1/b2/b3) —
no live agents, no real fixtures. Covers the §9 testable invariants: leave-one-out
necessity + mandatory red-on-base, no specificity gate (coarse test credited to
EACH independent bug), ERROR != green, source-edits-ignored, incidental silencing,
interacting-bug attribution, registered interacting_set, and the twice-run flake
guard (incl. anchors).
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import _oracle  # noqa: E402

# Toy calc.py: a()/b()/c() well-SEPARATED so per-bug diff -u hunks are
# context-disjoint and compose order-independently at zero fuzz.
PAD = "\n_p1 = 0\n_p2 = 0\n_p3 = 0\n_p4 = 0\n_p5 = 0\n"
CALC = ("def a():\n    return 1\n" + PAD +
        "\ndef b():\n    return 2\n" + PAD +
        "\ndef c():\n    return 3\n")
CALC_A = CALC.replace("    return 1\n", "    return 10\n", 1)
CALC_B = CALC.replace("    return 2\n", "    return 20\n", 1)
CALC_C = CALC.replace("    return 3\n", "    return 30\n", 1)

CONFTEST = ("import pathlib, sys\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))\n")


def _diff(path, before, after):
    with tempfile.TemporaryDirectory() as d:
        a = pathlib.Path(d) / "a"
        b = pathlib.Path(d) / "b"
        a.write_text(before)
        b.write_text(after)
        out = subprocess.run(["diff", "-u", str(a), str(b)],
                             capture_output=True, text=True).stdout
    return "\n".join([f"--- a/{path}", f"+++ b/{path}"] + out.splitlines()[2:]) + "\n"


def _build_toy(root: pathlib.Path):
    (root / "src" / "toy").mkdir(parents=True)
    (root / "src" / "toy" / "__init__.py").write_text("")
    (root / "src" / "toy" / "calc.py").write_text(CALC)
    (root / "tests").mkdir()
    (root / "tests" / "conftest.py").write_text(CONFTEST)
    (root / "fixes").mkdir()
    (root / "fixes" / "b1.patch").write_text(_diff("src/toy/calc.py", CALC, CALC_A))
    (root / "fixes" / "b2.patch").write_text(_diff("src/toy/calc.py", CALC, CALC_B))
    (root / "fixes" / "b3.patch").write_text(_diff("src/toy/calc.py", CALC, CALC_C))
    (root / "manifest.json").write_text(json.dumps(
        {"repo_id": "toy", "pkg": "toy", "test_dir": "tests",
         "runner_cmd": ["python3", "-m", "pytest", "-q"],
         "bug_ids": ["b1", "b2", "b3"], "n": 3}))


class OracleTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._tmp.name) / "toy"
        self.repo.mkdir()
        _build_toy(self.repo)
        self._wsi = 0

    def tearDown(self):
        self._tmp.cleanup()

    def write_test(self, body: str) -> pathlib.Path:
        """Write a canned test file into a fresh 'agent workspace' dir."""
        self._wsi += 1
        ws = pathlib.Path(self._tmp.name) / f"ws{self._wsi}"
        ws.mkdir()
        p = ws / "test_agent.py"
        p.write_text(body)
        return p

    def caught(self, body, **kw):
        return _oracle.caught_bugs([self.write_test(body)], self.repo, **kw)


class LeaveOneOut(OracleTestBase):
    def test_leave_one_out_credits_isolated_bug(self):
        r = self.caught("from toy.calc import a\ndef test():\n    assert a() == 10\n")
        self.assertEqual(r["caught"], {"b1"})

    def test_mandatory_red_on_base(self):
        # green on all-fixed AND green on base -> catches nothing real -> no credit
        r = self.caught("def test():\n    assert True\n")
        self.assertEqual(r["caught"], set())

    def test_not_green_on_all_fixed_credits_nothing(self):
        # red even on the fully-corrected repo -> pinned to no seeded bug
        r = self.caught("def test():\n    assert False\n")
        self.assertEqual(r["caught"], set())

    def test_incidental_silencing_not_credited(self):
        # the b1 test is GREEN on minus-b2 (b1 fixed there) -> NOT credited to b2
        r = self.caught("from toy.calc import a\ndef test():\n    assert a() == 10\n")
        self.assertNotIn("b2", r["caught"])
        self.assertNotIn("b3", r["caught"])


class ErrorTruthTable(OracleTestBase):
    def test_error_on_all_fixed_is_not_green(self):
        # import error -> ERROR (rc 2) on every variant incl all-fixed -> ineligible
        r = self.caught("import does_not_exist_xyz\ndef test():\n    assert True\n")
        self.assertEqual(r["caught"], set())

    def test_no_tests_collected_is_error_not_green(self):
        # no test_ function -> rc 5 -> ERROR on all-fixed -> ineligible (not a hidden catch)
        r = self.caught("x = 1\n")
        self.assertEqual(r["caught"], set())

    def test_errored_discard_is_surfaced(self):
        # S2: a test ERRORing on all-fixed (e.g. importing an unharvested helper)
        # is ineligible AND counted in errored_discards (not silently lost).
        r = self.caught("import does_not_exist_xyz\ndef test():\n    assert True\n")
        self.assertEqual(r["caught"], set())
        self.assertEqual(r["errored_discards"], 1)
        self.assertEqual(r["flaky_discards"], 0)

    def test_clean_run_reports_zero_errored_discards(self):
        r = self.caught("from toy.calc import a\ndef test():\n    assert a() == 10\n")
        self.assertEqual(r["caught"], {"b1"})
        self.assertEqual(r["errored_discards"], 0)
        self.assertEqual(r.get("errored_minus_discards", 0), 0)

    def test_minus_variant_error_is_surfaced(self):
        # S-1: an eligible test (GREEN on all-fixed, RED on base via `assert a()==10`)
        # that takes a COLLECTION-time import error on exactly the minus-b3 variant.
        # The module-level trap fires only when a/b are fixed but c is NOT — i.e.
        # all-fixed-minus-b3 (a=10,b=20,c=3). On all-fixed (c=30) and on base (a=1)
        # the condition is False, so collection succeeds there. The b3 cell is a
        # stable ERROR: neither flaky nor a credit — it MUST bump errored_minus_discards
        # so the lost b3 catch is observable, not silently dropped.
        body = ("from toy.calc import a, b, c\n"
                "if a() == 10 and b() == 20 and c() == 3:\n"
                "    import does_not_exist_xyz  # collection-time ERROR on minus-b3 only\n"
                "def test():\n    assert a() == 10\n")
        r = self.caught(body)
        self.assertEqual(r["caught"], {"b1"})       # b1 still credited (RED on minus-b1)
        self.assertNotIn("b3", r["caught"])         # b3 lost to the ERROR cell
        self.assertEqual(r["errored_minus_discards"], 1)
        self.assertEqual(r["errored_discards"], 0)  # all-fixed anchor collected fine
        self.assertEqual(r["flaky_discards"], 0)    # the ERROR is stable, not flaky


class SourceEditsIgnored(OracleTestBase):
    def test_source_edits_ignored(self):
        # The test file lives in an 'agent workspace' that ALSO contains a decoy
        # fixed source. The oracle materializes the pristine FIXTURE repo and runs
        # only the harvested test there, so the workspace source is neutralized.
        ws = pathlib.Path(self._tmp.name) / "dirty_ws"
        (ws / "src" / "toy").mkdir(parents=True)
        (ws / "src" / "toy" / "calc.py").write_text(CALC_A)  # decoy: b1 "fixed"
        t = ws / "test_agent.py"
        t.write_text("from toy.calc import a\ndef test():\n    assert a() == 10\n")
        r = _oracle.caught_bugs([t], self.repo)
        self.assertEqual(r["caught"], {"b1"})  # caught against pristine fixture, decoy ignored


class BroadTestNoSpecificityGate(OracleTestBase):
    def test_broad_test_credited_to_each_independent_bug(self):
        r = self.caught(
            "from toy.calc import a, b\n"
            "def test():\n    assert a() == 10 and b() == 20\n")
        self.assertEqual(r["caught"], {"b1", "b2"})  # NOT zeroed
        # broad_test_catches records the test isolated 2 bugs, but it is NOT in caught
        self.assertEqual(sum(r["broad_test_catches"].values()), 2)
        self.assertNotIn("broad_test_catches", r["caught"])

    def test_interacting_bug_attributed_via_leave_one_out(self):
        # total==30 is red on base (a=1,b=2) AND on minus-b1 (a=1,b=20 -> a!=10);
        # b2 is fixed in minus-b1, so the catch is correctly attributed to b1 (and b2).
        r = self.caught(
            "from toy.calc import a, b\n"
            "def test():\n    assert a() + b() == 30\n")
        self.assertEqual(r["caught"], {"b1", "b2"})


class RegisteredInteractingSet(OracleTestBase):
    def test_registered_interacting_set_credited_once(self):
        # AND-interaction: passes if EITHER b1 or b2 is fixed -> GREEN on single
        # minus, RED only on the combined minus-{b1,b2}. Registered -> credited once.
        body = ("from toy.calc import a, b\n"
                "def test():\n    assert a() == 10 or b() == 20\n")
        r = _oracle.caught_bugs([self.write_test(body)], self.repo,
                                interacting_sets=[["b1", "b2"]])
        self.assertEqual(r["caught"], {"b1+b2"})


class FlakeGuard(OracleTestBase):
    def test_flaky_test_discarded(self):
        # alternates RED/GREEN across the twice-run on the all-fixed anchor (counter
        # file in cwd=variant persists across the two subprocess runs).
        body = ("import pathlib\n"
                "c = pathlib.Path('flaky_counter.txt')\n"
                "n = (int(c.read_text()) if c.exists() else 0) + 1\n"
                "c.write_text(str(n))\n"
                "def test():\n    assert n % 2 == 0\n")
        r = self.caught(body)
        self.assertEqual(r["caught"], set())
        self.assertGreaterEqual(r["flaky_discards"], 1)


if __name__ == "__main__":
    unittest.main()
