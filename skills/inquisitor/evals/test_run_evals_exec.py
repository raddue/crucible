#!/usr/bin/env python3
"""Phase-1b execution-mode tests for stage_exec()/score_exec() (#424).

stdlib unittest. stage_exec is exercised against the real seeded `notify` repo
(small); score_exec against a fast toy fixture (b1/b2/b3) with canned harvested
test files, so the oracle math is pinned without live agents. Covers C2 (4-arm
manifest), C3 (--pilot floor), C4 (collect contract), D1-D4 (oracle rates, 4
deltas, WITHOUT ceiling, pilot band, KEEP statistic).
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import run_evals  # noqa: E402

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
        a = pathlib.Path(d) / "a"; b = pathlib.Path(d) / "b"
        a.write_text(before); b.write_text(after)
        out = subprocess.run(["diff", "-u", str(a), str(b)],
                             capture_output=True, text=True).stdout
    return "\n".join([f"--- a/{path}", f"+++ b/{path}"] + out.splitlines()[2:]) + "\n"


def _build_toy_fixture(root: pathlib.Path, off=("b3",)):
    (root / "src" / "toy").mkdir(parents=True)
    (root / "src" / "toy" / "__init__.py").write_text("")
    (root / "src" / "toy" / "calc.py").write_text(CALC)
    (root / "tests").mkdir()
    (root / "tests" / "conftest.py").write_text(CONFTEST)
    (root / "fixes").mkdir()
    for bid, after in (("b1", CALC_A), ("b2", CALC_B), ("b3", CALC_C)):
        (root / "fixes" / f"{bid}.patch").write_text(_diff("src/toy/calc.py", CALC, after))
    (root / "manifest.json").write_text(json.dumps(
        {"repo_id": "toy", "pkg": "toy", "test_dir": "tests",
         "runner_cmd": ["python3", "-m", "pytest", "-q"],
         "bug_ids": ["b1", "b2", "b3"], "n": 3}))
    (root / "ground-truth-bugs.json").write_text(json.dumps(
        {"_provenance": "x", "interacting_sets": [], "bugs": [
            {"bug_id": b, "desc": "d", "off_axis": (b in off),
             "fix_patch": f"fixes/{b}.patch"} for b in ("b1", "b2", "b3")]}))


class StageExecTest(unittest.TestCase):
    """C2/C3: stage_exec over the real seeded `notify` repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": self._tmp.name, "USER": "tester"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_four_arm_manifest_and_prompt_hashes(self):
        dd = run_evals.stage("exec-notify", repo="notify", trials=1)
        m = json.loads((dd / "stage-manifest.json").read_text())
        self.assertEqual(m["mode"], "phase1b-exec")
        self.assertEqual(m["arms"], ["with", "pool", "mid", "without"])
        self.assertEqual(m["repos"], ["notify"])
        cells = {(c["arm"], c["trial"]): c for c in m["cells"]}
        # 12 producers per cell: WITH 5 + POOL 5 + MID 1 + WITHOUT 1
        self.assertEqual(len(cells[("with", 1)]["producers"]), 5)
        self.assertEqual(len(cells[("pool", 1)]["producers"]), 5)
        self.assertEqual(len(cells[("mid", 1)]["producers"]), 1)
        self.assertEqual(len(cells[("without", 1)]["producers"]), 1)
        total_producers = sum(len(c["producers"]) for c in m["cells"])
        self.assertEqual(total_producers, 12)
        # each producer has a materialized repo copy under the dispatch dir
        for c in m["cells"]:
            for p in c["producers"]:
                self.assertTrue((dd / p["repo_copy"] / "manifest.json").exists())
        # §9 hash relationships
        ph = m["prompt_shas"]
        self.assertEqual(ph["pool"], ph["without"])          # POOL parity
        self.assertEqual(ph["with_scaffold"], ph["mid_scaffold"])  # scaffold parity
        self.assertNotEqual(ph["neutral_proxy"], ph["without"])
        self.assertNotEqual(ph["neutral_proxy"], ph["with_scaffold"])

    def test_pilot_neutral_proxy_only_and_trials_floor(self):
        dd = run_evals.stage("exec-pilot", repo="notify", pilot=True, trials=3)
        m = json.loads((dd / "stage-manifest.json").read_text())
        self.assertEqual(m["mode"], "pilot")
        self.assertEqual(m["arms"], ["neutral-proxy"])
        self.assertEqual({c["arm"] for c in m["cells"]}, {"neutral-proxy"})
        self.assertEqual(len(m["cells"]), 3)                 # 1 repo × 3 trials
        # floor: --pilot rejects trials < 3
        with self.assertRaises(ValueError):
            run_evals.stage("exec-pilot-bad", repo="notify", pilot=True, trials=2)


class ScoreExecTest(unittest.TestCase):
    """D1-D4 + C4: score_exec over a toy fixture with canned harvested tests."""

    def setUp(self):
        self._disp = tempfile.TemporaryDirectory()
        self._fix = tempfile.TemporaryDirectory()
        self._ev = tempfile.TemporaryDirectory()
        self.fixtures = pathlib.Path(self._fix.name)
        _build_toy_fixture(self.fixtures / "toy")
        self.evals = pathlib.Path(self._ev.name)
        self._env = mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": self._disp.name, "USER": "tester"})
        self._env.start()
        self._pf = mock.patch.object(run_evals, "_FIXTURES_DIR", self.fixtures)
        self._pe = mock.patch.object(run_evals, "_EVALS_DIR", self.evals)
        self._pf.start(); self._pe.start()
        self._ws = 0

    def tearDown(self):
        self._pe.stop(); self._pf.stop(); self._env.stop()
        self._disp.cleanup(); self._fix.cleanup(); self._ev.cleanup()

    def _test_file(self, body):
        self._ws += 1
        ws = pathlib.Path(self._disp.name) / f"ws{self._ws}"
        ws.mkdir()
        p = ws / "test_agent.py"
        p.write_text(body)
        return str(p)

    def _catch(self, *bugs):
        """A test body that catches exactly the named toy bugs (b1/b2/b3)."""
        checks = {"b1": "a() == 10", "b2": "b() == 20", "c3": "c() == 30",
                  "b3": "c() == 30"}
        conds = " and ".join(checks[x] for x in bugs)
        return ("from toy.calc import a, b, c\n"
                f"def test():\n    assert {conds}\n")

    def make_run(self, run_id, mode, trials, cell_caught, *, collect=True):
        """cell_caught: {(arm,repo,trial): [list of test bodies]}."""
        dd = run_evals.resolve_dispatch_dir(run_id)
        dd.mkdir(parents=True, exist_ok=True)
        arms = (run_evals._PILOT_ARMS if mode == "pilot" else run_evals._EXEC_ARMS)
        repos = ["toy"]
        cells = []
        for (arm, repo, trial), bodies in cell_caught.items():
            rf = f"{repo}-t{trial}-{arm}-tests.json"
            tfiles = [self._test_file(b) for b in bodies]
            (dd / rf).write_text(json.dumps(
                {"dispatch_status": "OK", "test_files": tfiles}))
            cells.append({"repo_id": repo, "trial": trial, "arm": arm,
                          "producers": [{"agent": 1, "dispatch_file": "x",
                                         "repo_copy": "x"}],
                          "result_file": rf})
        (dd / "stage-manifest.json").write_text(json.dumps(
            {"run_id": run_id, "mode": mode, "arms": list(arms),
             "trials": trials, "repos": repos, "cells": cells}))
        if collect:
            (dd / ".collect-status").write_text("complete")
        return dd

    def last_run(self):
        return json.loads((self.evals / "last_run.json").read_text())

    def test_decision_run_rates_and_four_deltas(self):
        # WITH catches all 3 bugs; POOL 2; MID 1; WITHOUT 1. Single trial.
        cc = {
            ("with", "toy", 1): [self._catch("b1", "b2", "b3")],
            ("pool", "toy", 1): [self._catch("b1", "b2")],
            ("mid", "toy", 1): [self._catch("b1")],
            ("without", "toy", 1): [self._catch("b1")],
        }
        rc = run_evals.score(self.make_run("d1", "phase1b-exec", 1, cc) and "d1")
        self.assertEqual(rc, 0)
        lr = self.last_run()
        self.assertEqual(lr["mode"], "phase1b-exec")
        self.assertEqual(lr["graded_bugs"], 3)
        self.assertAlmostEqual(lr["arm_rates"]["with"]["rate"], 1.0)
        self.assertAlmostEqual(lr["arm_rates"]["without"]["rate"], 1 / 3)
        for k in ("with_without", "with_pool", "pool_without", "with_mid"):
            self.assertIn(k, lr["deltas"])
        # primary delta is positive (WITH 1.0 - WITHOUT 0.333)
        self.assertAlmostEqual(lr["deltas"]["with_without"]["paired"], 2 / 3)

    def test_without_ceiling_and_keep_statistic(self):
        # WITHOUT catches 1/3 = 33% <= 70% on the (only) repo -> ceiling broken.
        cc = {
            ("with", "toy", 1): [self._catch("b1", "b2", "b3")],
            ("pool", "toy", 1): [self._catch("b1", "b2")],
            ("mid", "toy", 1): [self._catch("b1")],
            ("without", "toy", 1): [self._catch("b1")],
        }
        run_evals.score(self.make_run("d2", "phase1b-exec", 1, cc) and "d2")
        lr = self.last_run()
        self.assertTrue(lr["without_ceiling_broken"])
        ks = lr["keep_statistic"]
        self.assertEqual(ks["statistic"], "beyond_spread")
        self.assertIn("trial_spread", ks["_note"])          # explicitly rejected
        self.assertTrue(ks["sign_holds_2of3"])              # WITH > WITHOUT on the repo
        self.assertIn("beyond_spread", ks)

    def test_off_axis_diagnostic(self):
        # b3 is off_axis; WITH catches it, WITHOUT does not.
        cc = {
            ("with", "toy", 1): [self._catch("b1", "b2", "b3")],
            ("pool", "toy", 1): [self._catch("b1")],
            ("mid", "toy", 1): [self._catch("b1")],
            ("without", "toy", 1): [self._catch("b1")],
        }
        run_evals.score(self.make_run("d3", "phase1b-exec", 1, cc) and "d3")
        oa = self.last_run()["off_axis_diagnostic"]
        self.assertEqual(oa["with"]["total"], 1)            # only b3 is off_axis
        self.assertEqual(oa["with"]["pass"], 1)
        self.assertEqual(oa["without"]["pass"], 0)

    def test_collect_contract_union_over_producers(self):
        # WITH cell unions multiple harvested test files (the 5-agent union, C4):
        # two files each catching one bug -> WITH caught {b1,b2}.
        cc = {
            ("with", "toy", 1): [self._catch("b1"), self._catch("b2")],
            ("pool", "toy", 1): [self._catch("b1")],
            ("mid", "toy", 1): [self._catch("b1")],
            ("without", "toy", 1): [self._catch("b1")],
        }
        run_evals.score(self.make_run("d4", "phase1b-exec", 1, cc) and "d4")
        lr = self.last_run()
        self.assertEqual(lr["arm_rates"]["with"]["per_repo"]["toy"], 2)  # b1+b2 union

    def test_pilot_band(self):
        # neutral-proxy catches 1/3 = 33% < 40% -> soften.
        cc = {("neutral-proxy", "toy", t): [self._catch("b1")] for t in (1, 2, 3)}
        rc = run_evals.score(self.make_run("p1", "pilot", 3, cc) and "p1")
        self.assertEqual(rc, 0)
        lr = self.last_run()
        self.assertEqual(lr["mode"], "pilot")
        band = lr["pilot_band"]["per_repo"]["toy"]
        self.assertAlmostEqual(band["mean_rate"], 1 / 3)
        self.assertEqual(band["verdict"], "soften")

    def test_collect_status_gating(self):
        cc = {(a, "toy", 1): [self._catch("b1")]
              for a in run_evals._EXEC_ARMS}
        self.make_run("g1", "phase1b-exec", 1, cc, collect=False)
        self.assertEqual(run_evals.score("g1", allow_incomplete=False), 1)

    def test_incomplete_grid_refused(self):
        # only the WITH cell present for a complete run -> refused.
        cc = {("with", "toy", 1): [self._catch("b1")]}
        self.assertEqual(
            run_evals.score(self.make_run("g2", "phase1b-exec", 1, cc) and "g2"), 1)


if __name__ == "__main__":
    unittest.main()
