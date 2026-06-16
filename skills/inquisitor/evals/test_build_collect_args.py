#!/usr/bin/env python3
"""Tests for _build_collect_args.build() — the Phase-1b no-judge dispatch args (#424).

stdlib unittest. Synthesizes an exec/pilot stage-manifest and asserts the producer
unit list is correct and judge-free.
"""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import _build_collect_args  # noqa: E402

_JUDGE_KEYS = {"dim_paths", "mid_path", "without_path", "items", "judge_prompt"}


def _exec_manifest():
    cells = []
    specs = [("with", 5), ("pool", 5), ("mid", 1), ("without", 1)]
    for arm, k in specs:
        cells.append({
            "repo_id": "notify", "trial": 1, "arm": arm,
            "producers": [{"agent": i, "dispatch_file": f"{arm}-{i}.md",
                           "repo_copy": f"copies/notify-t1-{arm}-p{i}"}
                          for i in range(1, k + 1)],
            "result_file": f"notify-t1-{arm}-tests.json"})
    return {"run_id": "x", "mode": "phase1b-exec",
            "arms": ["with", "pool", "mid", "without"], "trials": 1,
            "repos": ["notify"], "cells": cells}


class BuildCollectArgsTest(unittest.TestCase):
    def _write(self, manifest):
        d = pathlib.Path(self._tmp.name)
        (d / "stage-manifest.json").write_text(json.dumps(manifest))
        return d

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_exec_producer_units(self):
        d = self._write(_exec_manifest())
        obj = _build_collect_args.build(d)
        self.assertEqual(obj["mode"], "phase1b-exec")
        self.assertEqual(len(obj["units"]), 12)            # 5+5+1+1
        for u in obj["units"]:
            self.assertTrue(pathlib.Path(u["dispatch_file"]).is_absolute())
            self.assertTrue(pathlib.Path(u["repo_copy"]).is_absolute())
            self.assertTrue(u["result_file"].endswith("-tests.json"))
            self.assertIn(u["arm"], ("with", "pool", "mid", "without"))
        # no Phase-1 judge inputs leaked into the args object or any unit
        self.assertFalse(_JUDGE_KEYS & set(obj))
        for u in obj["units"]:
            self.assertFalse(_JUDGE_KEYS & set(u))
        # WITH/POOL contribute 5 producers each, all pointing at the cell result_file
        with_units = [u for u in obj["units"] if u["arm"] == "with"]
        self.assertEqual(len(with_units), 5)
        self.assertEqual(len({u["result_file"] for u in with_units}), 1)

    def test_pilot_units(self):
        m = {"run_id": "x", "mode": "pilot", "arms": ["neutral-proxy"], "trials": 3,
             "repos": ["notify"],
             "cells": [{"repo_id": "notify", "trial": t, "arm": "neutral-proxy",
                        "producers": [{"agent": 1,
                                       "dispatch_file": "neutral-proxy-prompt-eval.md",
                                       "repo_copy": f"copies/notify-t{t}-np-p1"}],
                        "result_file": f"notify-t{t}-neutral-proxy-tests.json"}
                       for t in (1, 2, 3)]}
        obj = _build_collect_args.build(self._write(m))
        self.assertEqual(obj["mode"], "pilot")
        self.assertEqual(len(obj["units"]), 3)
        self.assertEqual({u["arm"] for u in obj["units"]}, {"neutral-proxy"})

    def test_phase1_manifest_self_explaining_error(self):
        # M-2: a Phase-1 (no-`mode`, dispatch_files-shaped) manifest must fail with a
        # clear "exec/pilot-only" message, not a raw KeyError on cell["producers"].
        d = self._write({"run_id": "x", "dispatch_files": ["a.md", "b.md"]})
        with self.assertRaises(SystemExit) as cm:
            _build_collect_args.build(d)
        self.assertIn("exec/pilot-only", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
