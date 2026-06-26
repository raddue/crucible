#!/usr/bin/env python3
"""`stage` mechanics for the delve eval harness (#373) — fully synthetic, no live
agents. Asserts stage writes a well-formed stage-manifest.json enumerating one cell
per fixture with the dispatch note + result_file.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.delve.evals import run_evals  # noqa: E402


class TestStage(unittest.TestCase):
    def setUp(self):
        # Point resolve_dispatch_dir at an isolated temp root (it honors
        # XDG_RUNTIME_DIR) so the test never touches a real /tmp dispatch dir.
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._tmp.name

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._prev
        self._tmp.cleanup()

    def test_stage_writes_wellformed_manifest(self):
        dispatch_dir = run_evals.stage("test-stage-1")
        manifest_path = dispatch_dir / "stage-manifest.json"
        self.assertTrue(manifest_path.exists())
        m = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(m["run_id"], "test-stage-1")
        self.assertEqual(m["engine"], "delve")
        self.assertGreaterEqual(m["fixtures"], 1)
        self.assertEqual(len(m["cells"]), m["fixtures"])

        # The committed `sample` fixture must be staged with a usable cell.
        sample = next(c for c in m["cells"] if c["fixture_id"] == "sample")
        self.assertEqual(sample["result_file"], "sample-findings.json")
        self.assertIn("skills/delve/evals/fixtures/sample", sample["scope"])
        self.assertIn("/delve", sample["dispatch_note"])
        self.assertIn("DISPATCH_STATUS: OK", sample["dispatch_note"])
        self.assertIn(".collect-status", sample["dispatch_note"])

    def test_stage_named_fixture(self):
        dispatch_dir = run_evals.stage("test-stage-named", fixture="sample")
        m = json.loads((dispatch_dir / "stage-manifest.json").read_text("utf-8"))
        self.assertEqual([c["fixture_id"] for c in m["cells"]], ["sample"])

    def test_stage_unknown_fixture_raises(self):
        with self.assertRaises(ValueError):
            run_evals.stage("test-stage-x", fixture="does-not-exist")

    def test_stage_refuses_existing_dir_without_force(self):
        run_evals.stage("test-stage-dup")
        with self.assertRaises(FileExistsError):
            run_evals.stage("test-stage-dup")
        # force re-stages cleanly
        run_evals.stage("test-stage-dup", force=True)


if __name__ == "__main__":
    unittest.main()
