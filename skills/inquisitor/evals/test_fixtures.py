#!/usr/bin/env python3
"""Tests for _fixtures.py — variant materialization helper (#424 Phase 1b).

stdlib unittest (harness convention; pytest is the fixture *runner*, not the
unit-test gate). Invoked as a bare script by scripts/run_tests.sh, so bootstrap
repo-root onto sys.path before importing the package.
"""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import _fixtures  # noqa: E402

# git-style unified diff fixing toy bug b1 (return "BUG" -> return "OK").
# -p1 strips the a/ prefix when applied from the variant root.
B1_PATCH = '''\
--- a/src/toy/m.py
+++ b/src/toy/m.py
@@ -1,2 +1,2 @@
 def value():
-    return "BUG"
+    return "OK"
'''

M_PY = 'def value():\n    return "BUG"\n'

MANIFEST = {
    "repo_id": "toy",
    "pkg": "toy",
    "test_dir": "tests",
    "runner_cmd": ["python3", "-m", "pytest", "-q"],
    "bug_ids": ["b1"],
    "n": 1,
}


def _build_toy_repo(root: pathlib.Path):
    (root / "src" / "toy").mkdir(parents=True)
    (root / "src" / "toy" / "__init__.py").write_text("")
    (root / "src" / "toy" / "m.py").write_text(M_PY)
    (root / "fixes").mkdir()
    (root / "fixes" / "b1.patch").write_text(B1_PATCH)
    (root / "manifest.json").write_text(json.dumps(MANIFEST))


class FixturesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.toy = pathlib.Path(self._tmp.name) / "toy"
        self.toy.mkdir()
        _build_toy_repo(self.toy)
        self._dirs = []

    def tearDown(self):
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._tmp.cleanup()

    def _materialize(self, **kw):
        d = _fixtures.materialize_variant(self.toy, **kw)
        self._dirs.append(d)
        return pathlib.Path(d)

    def _m_py(self, d: pathlib.Path) -> str:
        return (d / "src" / "toy" / "m.py").read_text()

    def test_base_has_bug(self):
        d = self._materialize(apply=[])
        self.assertIn("BUG", self._m_py(d))

    def test_all_fixed_applies_every_patch(self):
        d = self._materialize(apply=["b1"])
        self.assertNotIn("BUG", self._m_py(d))
        self.assertIn("OK", self._m_py(d))

    def test_exclude_cancels_apply(self):
        # apply all known bug_ids except the excluded one -> == base here
        d = self._materialize(apply=["b1"], exclude=["b1"])
        self.assertIn("BUG", self._m_py(d))

    def test_load_manifest(self):
        m = _fixtures.load_manifest(self.toy)
        self.assertEqual(m["repo_id"], "toy")
        self.assertEqual(m["n"], 1)
        self.assertEqual(m["bug_ids"], ["b1"])

    def test_load_manifest_n_mismatch_raises(self):
        bad = pathlib.Path(self._tmp.name) / "bad"
        bad.mkdir()
        _build_toy_repo(bad)
        m = dict(MANIFEST, n=2)
        (bad / "manifest.json").write_text(json.dumps(m))
        with self.assertRaises(ValueError):
            _fixtures.load_manifest(bad)

    def test_unknown_bug_id_raises(self):
        with self.assertRaises(ValueError):
            self._materialize(apply=["bX"])

    def test_convenience_wrappers(self):
        b = pathlib.Path(_fixtures.base(self.toy)); self._dirs.append(b)
        af = pathlib.Path(_fixtures.all_fixed(self.toy)); self._dirs.append(af)
        afm = pathlib.Path(_fixtures.all_fixed_minus(self.toy, "b1")); self._dirs.append(afm)
        self.assertIn("BUG", self._m_py(b))
        self.assertNotIn("BUG", self._m_py(af))
        self.assertIn("BUG", self._m_py(afm))  # only bug excluded -> base

    def test_variant_context_manager_cleans_up(self):
        with _fixtures.variant(self.toy, apply=["b1"]) as d:
            dp = pathlib.Path(d)
            self.assertNotIn("BUG", self._m_py(dp))
        self.assertFalse(dp.exists())


if __name__ == "__main__":
    unittest.main()
