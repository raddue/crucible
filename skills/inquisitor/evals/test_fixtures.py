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


class ProducerCopyTest(unittest.TestCase):
    """F1+F2+S3: blind producer copy (strip + subset) and subprocess timeout."""

    # the bug-describing prose mirrors the real fixtures: id token + a
    # plain-language defect description + a "The fix …" sentence, in a comment AND
    # a docstring; the GT desc is a verbatim window of that prose.
    DESC = "a None or negative delay is passed straight through to the job"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._tmp.name) / "toy"
        (self.repo / "src" / "toy").mkdir(parents=True)
        (self.repo / "src" / "toy" / "__init__.py").write_text("")
        (self.repo / "src" / "toy" / "m.py").write_text(
            '"""seam exercised here (nt-b1). ' + self.DESC + '."""\n'
            'DEFAULT = "sms"  # BUG nt-b8: ' + self.DESC + '. The fix clamps it.\n'
            'CODE = "nt-keep"  # a runtime string (no leak token) stays intact\n'
            'def value():\n    """' + self.DESC + '"""\n    return DEFAULT\n')
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "conftest.py").write_text("# conftest\n")
        (self.repo / "exemplars").mkdir()
        (self.repo / "exemplars" / "nt-b1.py").write_text("# answer\n")
        (self.repo / "fixes").mkdir()
        (self.repo / "fixes" / "nt-b1.patch").write_text("--- a\n+++ b\n")
        (self.repo / "manifest.json").write_text(json.dumps(MANIFEST))
        (self.repo / "ground-truth-bugs.json").write_text(json.dumps(
            {"bugs": [{"bug_id": "nt-b8", "desc": self.DESC}]}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_strip_removes_comments_and_docstrings_keeps_code(self):
        src = ('"""module doc (pg-b2): ' + self.DESC + '"""\n'
               'X = 1  # BUG nt-b3: bad\n'
               'KEEP = "literal pg value"\n'
               'def f():\n    """fn doc here."""\n    return X\n')
        out = _fixtures._strip_comments_and_docstrings(src)
        # all bug prose + tokens gone
        self.assertNotIn("nt-b3", out)
        self.assertNotIn("pg-b2", out)
        self.assertNotIn("BUG", out)
        self.assertNotIn(self.DESC, out)
        # code preserved; result still compiles
        self.assertIn("X = 1", out)
        self.assertIn("return X", out)
        compile(out, "stripped.py", "exec")
        # M-3: a NON-docstring string literal is left intact (runtime data)
        self.assertIn('KEEP = "literal pg value"', out)
        # no-comment/no-docstring source is returned byte-identical
        clean = "def g():\n    return 7\n"
        self.assertEqual(_fixtures._strip_comments_and_docstrings(clean), clean)

    def test_copy_excludes_answer_key_and_strips_prose(self):
        copy = pathlib.Path(self._tmp.name) / "copy"
        _fixtures.copy_repo_for_producer(self.repo, copy)
        # F2: answer-key paths excluded
        for forbidden in ("exemplars", "fixes", "manifest.json",
                          "ground-truth-bugs.json"):
            self.assertFalse((copy / forbidden).exists())
        # producer-visible subset present
        self.assertTrue((copy / "src" / "toy" / "m.py").exists())
        self.assertTrue((copy / "tests" / "conftest.py").exists())
        # F1: leak tokens AND bug-describing prose stripped, code preserved
        m = (copy / "src" / "toy" / "m.py").read_text()
        self.assertNotIn("nt-b", m)
        self.assertNotIn("BUG", m)
        self.assertNotIn(self.DESC, m)
        self.assertNotIn("The fix", m)
        self.assertIn('DEFAULT = "sms"', m)
        # non-docstring runtime string survived
        self.assertIn('CODE = "nt-keep"', m)

    def test_producer_copy_has_no_gt_description_prose(self):
        # The test whose ABSENCE let F-1 through: materialize a producer copy and
        # assert NONE of the GT bug descriptions survive (adversarial guard, not
        # re-using the strip's own regex).
        copy = pathlib.Path(self._tmp.name) / "copy_desc"
        _fixtures.copy_repo_for_producer(self.repo, copy)
        descs = [self.DESC]
        _fixtures.assert_no_description_leak(copy, descs)  # passes on stripped copy
        # and the guard is ADVERSARIAL: a re-introduced desc window trips it
        (copy / "src" / "toy" / "leak.py").write_text("# " + self.DESC + "\n")
        with self.assertRaises(AssertionError):
            _fixtures.assert_no_description_leak(copy, descs)

    def test_assert_no_leak_raises_on_token_and_path(self):
        copy = pathlib.Path(self._tmp.name) / "copy2"
        _fixtures.copy_repo_for_producer(self.repo, copy)
        _fixtures._assert_no_leak(copy)  # clean copy passes
        # re-introduce a leak token
        (copy / "src" / "toy" / "leak.py").write_text("# BUG nt-b9\n")
        with self.assertRaises(AssertionError):
            _fixtures._assert_no_leak(copy)
        # forbidden path
        copy3 = pathlib.Path(self._tmp.name) / "copy3"
        _fixtures.copy_repo_for_producer(self.repo, copy3)
        (copy3 / "fixes").mkdir()
        with self.assertRaises(AssertionError):
            _fixtures._assert_no_leak(copy3)

    def test_tests_subtree_in_blindness_scope(self):
        # S-1: tests/ is producer-visible (`_PRODUCER_VISIBLE`), so an annotated
        # tests/ file must (a) be stripped by copy_repo_for_producer and (b) be in
        # scope of BOTH leak guards. Drop a test file carrying a leak token + a
        # GT-desc window + "The fix" into the SOURCE repo's tests/, then materialize.
        (self.repo / "tests" / "test_seam.py").write_text(
            '"""seam (nt-b8): ' + self.DESC + '. The fix clamps it."""\n'
            'def test_seam():\n    assert True\n')
        copy = pathlib.Path(self._tmp.name) / "copy_tests"
        _fixtures.copy_repo_for_producer(self.repo, copy)
        # (a) the strip ran over tests/ too: token + prose gone, code preserved
        t = (copy / "tests" / "test_seam.py").read_text()
        self.assertNotIn("nt-b", t)
        self.assertNotIn(self.DESC, t)
        self.assertNotIn("The fix", t)
        self.assertIn("assert True", t)
        # remove the stripped test file so the tests/-empty-except-conftest invariant
        # below does not pre-empt the token/prose guards we exercise next
        (copy / "tests" / "test_seam.py").unlink()
        # (b) a leak token re-introduced into the COPY's tests/ trips _assert_no_leak
        # via the token guard (proving the scope is tests/-inclusive, not src/-only)
        (copy / "tests" / "test_leak.py").write_text("# BUG nt-b9: leak\n")
        with self.assertRaises(AssertionError) as cm:
            _fixtures._assert_no_leak(copy)
        self.assertIn("leaks bug-identity token", str(cm.exception))
        (copy / "tests" / "test_leak.py").unlink()
        # ... and GT-desc prose in a tests/ file trips assert_no_description_leak
        (copy / "tests" / "test_prose.py").write_text("# " + self.DESC + "\n")
        with self.assertRaises(AssertionError):
            _fixtures.assert_no_description_leak(copy, [self.DESC])
        (copy / "tests" / "test_prose.py").unlink()
        # belt-and-suspenders: a clean (no-leak) non-conftest tests/ file is flagged
        # by the tests/-empty-except-conftest invariant
        (copy / "tests" / "test_plain.py").write_text("def test_p():\n    assert 1\n")
        with self.assertRaises(AssertionError) as cm2:
            _fixtures._assert_no_leak(copy)
        self.assertIn("non-conftest file", str(cm2.exception))
        (copy / "tests" / "test_plain.py").unlink()
        # tests/ = conftest.py only passes the guard
        _fixtures._assert_no_leak(copy)

    def test_bytecode_never_reaches_producer_copy(self):
        # S-1: a stray `src/<pkg>/__pycache__/*.pyc` in the committed tree (any
        # in-place import or a pytest run w/o PYTHONDONTWRITEBYTECODE generates one)
        # must NOT ride into the producer sandbox. A `.pyc` is un-strippable and
        # retains every docstring (co_consts) + the absolute source path
        # (co_filename) = the answer key. copy_repo_for_producer ignores bytecode on
        # copy, and _assert_no_leak fails loud if any bytecode reaches a copy.
        import py_compile
        pkg = self.repo / "src" / "toy"
        # a real compiled module whose .pyc genuinely embeds a docstring
        (pkg / "tainted.py").write_text(
            '"""' + self.DESC + ' (nt-b8). The fix clamps it."""\n'
            'VALUE = 1\n')
        py_compile.compile(str(pkg / "tainted.py"), doraise=True)
        cache = pkg / "__pycache__"
        self.assertTrue(cache.exists() and any(cache.glob("*.pyc")),
                        "precondition: a .pyc was generated in the source tree")

        copy = pathlib.Path(self._tmp.name) / "copy_bytecode"
        _fixtures.copy_repo_for_producer(self.repo, copy)

        # (a) NO bytecode rode into the producer copy
        self.assertEqual(list(copy.rglob("*.pyc")), [])
        self.assertEqual(list(copy.rglob("*.pyo")), [])
        self.assertEqual(list(copy.rglob("__pycache__")), [])
        # (b) _assert_no_leak passes on the clean copy
        _fixtures._assert_no_leak(copy)
        # (c) ... and RAISES if a .pyc is planted into the copy (bytecode guard)
        planted = copy / "src" / "toy" / "__pycache__"
        planted.mkdir()
        (planted / "m.cpython-99.pyc").write_bytes(b"\x00\x01\x02")
        with self.assertRaises(AssertionError) as cm:
            _fixtures._assert_no_leak(copy)
        self.assertIn("bytecode", str(cm.exception).lower())
        (planted / "m.cpython-99.pyc").unlink()
        planted.rmdir()
        # (d) ... and RAISES on a bare __pycache__ dir too
        bare = copy / "tests" / "__pycache__"
        bare.mkdir()
        with self.assertRaises(AssertionError) as cm2:
            _fixtures._assert_no_leak(copy)
        self.assertIn("__pycache__", str(cm2.exception))
        bare.rmdir()
        # (e) defense-in-depth: a `.pyc` planted at the copy ROOT (outside any
        # producer-visible subtree) also trips the guard
        root_pyc = copy / "stray.cpython-99.pyc"
        root_pyc.write_bytes(b"\x00\x01\x02")
        with self.assertRaises(AssertionError) as cm3:
            _fixtures._assert_no_leak(copy)
        self.assertIn("bytecode", str(cm3.exception).lower())
        root_pyc.unlink()

    def test_missing_patch_cleans_up_tmp(self):
        # M-1: the missing-patch error path rmtrees its temp dir before raising,
        # matching its two sibling error paths (timeout, patch-reject). Manifest
        # names a bug whose fixes/<id>.patch is absent.
        repo = pathlib.Path(self._tmp.name) / "nopatch"
        (repo / "src").mkdir(parents=True)
        (repo / "fixes").mkdir()
        (repo / "manifest.json").write_text(json.dumps(
            {**MANIFEST, "bug_ids": ["nt-z1"], "n": 1}))
        before = set(pathlib.Path(tempfile.gettempdir()).glob("variant-*"))
        with self.assertRaises(FileNotFoundError):
            _fixtures.materialize_variant(repo, apply=["nt-z1"])
        after = set(pathlib.Path(tempfile.gettempdir()).glob("variant-*"))
        self.assertEqual(after - before, set(),
                         "missing-patch path leaked a /tmp/variant-* dir")

    def test_run_test_in_dir_timeout_maps_to_error(self):
        # A hung test maps to ERROR (non-eligible), not a hang. Use a tiny
        # timeout via monkeypatch to keep the test fast.
        variant = pathlib.Path(self._tmp.name) / "variant"
        (variant / "src" / "toy").mkdir(parents=True)
        (variant / "src" / "toy" / "__init__.py").write_text("")
        (variant / "tests").mkdir()
        (variant / "tests" / "conftest.py").write_text(
            "import pathlib, sys\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))\n")
        hung = pathlib.Path(self._tmp.name) / "test_hung.py"
        hung.write_text("import time\ndef test_h():\n    time.sleep(30)\n")
        orig = _fixtures._SUBPROCESS_TIMEOUT_S
        _fixtures._SUBPROCESS_TIMEOUT_S = 1
        try:
            verdict = _fixtures.run_test_in_dir(variant, str(hung), MANIFEST)
        finally:
            _fixtures._SUBPROCESS_TIMEOUT_S = orig
        self.assertEqual(verdict, "ERROR")


if __name__ == "__main__":
    unittest.main()
