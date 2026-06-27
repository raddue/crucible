#!/usr/bin/env python3
"""`stage` mechanics for the siege eval harness (#373) — fully synthetic, no live
agents. Asserts stage writes a well-formed stage-manifest.json enumerating one cell
per fixture with the siege dispatch note + result_file.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.siege.evals import run_evals  # noqa: E402


class TestStage(unittest.TestCase):
    def setUp(self):
        # Point resolve_dispatch_dir at an isolated temp root (it honors
        # XDG_RUNTIME_DIR) so the test never touches a real /tmp dispatch dir.
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._tmp.name
        # Track any temp fixture dirs created under the real _FIXTURES_DIR so
        # tearDown removes them — they must never pollute the committed tree.
        self._fixture_dirs = []

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._prev
        self._tmp.cleanup()
        for d in self._fixture_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_stage_writes_wellformed_manifest(self):
        dispatch_dir = run_evals.stage("test-stage-1")
        manifest_path = dispatch_dir / "stage-manifest.json"
        self.assertTrue(manifest_path.exists())
        m = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(m["run_id"], "test-stage-1")
        self.assertEqual(m["engine"], "siege")
        self.assertGreaterEqual(m["fixtures"], 1)
        self.assertEqual(len(m["cells"]), m["fixtures"])

        # The committed `webshop` fixture must be staged with a usable cell.
        ws = next(c for c in m["cells"] if c["fixture_id"] == "webshop")
        self.assertEqual(ws["result_file"], "webshop-findings.json")
        self.assertIn("skills/siege/evals/fixtures/webshop", ws["scope"])
        self.assertIn("/siege", ws["dispatch_note"])
        self.assertIn("DISPATCH_STATUS: OK", ws["dispatch_note"])
        self.assertIn(".collect-status", ws["dispatch_note"])

    def test_stage_named_fixture(self):
        dispatch_dir = run_evals.stage("test-stage-named", fixture="webshop")
        m = json.loads((dispatch_dir / "stage-manifest.json").read_text("utf-8"))
        self.assertEqual([c["fixture_id"] for c in m["cells"]], ["webshop"])

    def test_stage_unknown_fixture_raises(self):
        with self.assertRaises(ValueError):
            run_evals.stage("test-stage-x", fixture="does-not-exist")

    def test_stage_fixture_without_manifest(self):
        # A fixture with GT + provenance but NO manifest.json passes the optional-manifest
        # provenance gate, so stage() must NOT crash on it (MW1) — it must stage a cell
        # using the repo-relative fallback scope.
        fid = "tmp-no-manifest-fixture"
        fdir = run_evals._FIXTURES_DIR / fid
        self.assertFalse(fdir.exists(), "stale temp fixture left from a prior run")
        self._fixture_dirs.append(fdir)
        fdir.mkdir()
        (fdir / "ground-truth-bugs.json").write_text(
            json.dumps({"bugs": []}), encoding="utf-8")
        # No manifest.json on purpose.

        dispatch_dir = run_evals.stage("test-stage-no-manifest")  # must not raise
        m = json.loads((dispatch_dir / "stage-manifest.json").read_text("utf-8"))
        cell = next(c for c in m["cells"] if c["fixture_id"] == fid)
        # Repo-relative fallback scope (manifest absent → manifest.get default).
        self.assertEqual(cell["scope"], f"skills/siege/evals/fixtures/{fid}")
        self.assertEqual(cell["result_file"], f"{fid}-findings.json")

    def test_stage_refuses_existing_dir_without_force(self):
        run_evals.stage("test-stage-dup")
        with self.assertRaises(FileExistsError):
            run_evals.stage("test-stage-dup")
        # force re-stages cleanly
        run_evals.stage("test-stage-dup", force=True)


if __name__ == "__main__":
    unittest.main()
