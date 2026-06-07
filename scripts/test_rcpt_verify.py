#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/rcpt_verify.py.

Run from repo root:  python3 scripts/test_rcpt_verify.py
                  or  python3 -m unittest scripts.test_rcpt_verify -v

No pytest — matches the stdlib-only discipline of rcpt_verify.py itself, and the
flat-in-scripts/ layout of scripts/test_catalog.py (a `scripts/tests/` subdir is
caught by the repo-wide `tests/` .gitignore rule).
"""
import importlib.util
import json
import pathlib
import hashlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rcpt_verify.py"
REPO = pathlib.Path(__file__).resolve().parent.parent
CORPUS = REPO / "eval/ledger-return-protocol"


def run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True,
    )


def _import_rv():
    spec = importlib.util.spec_from_file_location("rcpt_verify", SCRIPT)
    rv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rv)
    return rv


def _load(name):
    return [json.loads(l) for l in (CORPUS / name).read_text().splitlines() if l.strip()]


class TestSkeleton(unittest.TestCase):
    def test_no_args_usage_nonzero(self):
        r = run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", (r.stderr + r.stdout).lower())

    def test_exposes_main(self):
        rv = _import_rv()
        self.assertTrue(hasattr(rv, "main"))


class TestV1CorpusEquivalence(unittest.TestCase):
    """Tier-1 port must classify the corpus identically to lint.py: the 5 sample
    receipts lint-pass; the 5 Tier-1 injections raise from lint_receipt; the 2
    Tier-2-only rows (102-inject/105-inject — the ONLY artifact_bodies carriers)
    return cleanly from lint_receipt (their catch fires via the Tier-2 path)."""

    def test_samples_lint_pass(self):
        rv = _import_rv()
        for rec in _load("sample-corpus/receipts.jsonl"):
            self.assertIn(rv.lint_receipt(rec["receipt"]), {"PASS", "FAIL", "BLOCKED"})

    def test_injections_partition_by_artifact_bodies(self):
        rv = _import_rv()
        inject_dir = CORPUS / "inject"
        # M5: glob so a future inject shape is auto-covered (don't hard-code names).
        shapes = sorted(inject_dir.glob("shape-*.jsonl"))
        self.assertTrue(shapes, "no inject/shape-*.jsonl found")
        for shape_path in shapes:
            for rec in _load(f"inject/{shape_path.name}"):
                try:
                    rv.lint_receipt(rec["receipt"])
                    raised = False
                except rv.LintError:
                    raised = True
                if rec.get("artifact_bodies"):
                    # Tier-2-only rows (102/105) — lint_receipt must NOT raise; their
                    # catch is asserted via the --eval / verify_witness path (Task 6/8).
                    self.assertFalse(
                        raised,
                        f"{rec.get('dispatch-id','?')} carries artifact_bodies "
                        f"(Tier-2-only) — lint_receipt must NOT raise",
                    )
                else:
                    self.assertTrue(
                        raised,
                        f"{shape_path.name}/{rec.get('dispatch-id','?')} should Tier-1 LINT-FAIL",
                    )


class TestBaseResolution(unittest.TestCase):
    def test_resolve_base_binds_root_first(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            (repo / ".git").mkdir()
            sub = repo / "sub"
            sub.mkdir()
            # file exists under both --root (sub) and repo-root
            (sub / "f.txt").write_text("ROOT")
            (repo / "f.txt").write_text("REPO")
            got = rv.resolve_base("f.txt", sub)
            self.assertEqual(got.read_text(), "ROOT")

    def test_resolve_base_falls_to_repo_root(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            (repo / ".git").mkdir()
            sub = repo / "sub"
            sub.mkdir()
            (repo / "only-at-repo.txt").write_text("REPO")
            got = rv.resolve_base("only-at-repo.txt", sub)
            self.assertIsNotNone(got)
            self.assertEqual(got.read_text(), "REPO")

    def test_resolve_base_absent_basename_none(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(rv.resolve_base("nope.md", pathlib.Path(td)))

    def test_git_toplevel_handles_worktree_gitlink_file(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            wt = pathlib.Path(td)
            # worktree: .git is a FILE (gitlink), not a dir
            (wt / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n")
            self.assertEqual(rv._git_toplevel(wt), wt)

    def test_is_path_shaped(self):
        rv = _import_rv()
        self.assertTrue(rv.is_path_shaped("src/foo.ts"))
        self.assertFalse(rv.is_path_shaped("findings.md"))
        self.assertTrue(rv.is_path_shaped("/tmp/x"))


class TestTier2Artifacts(unittest.TestCase):
    def _art(self, name, data):
        return {name: {"hash": hashlib.sha256(data).hexdigest(), "size": str(len(data))}}

    def test_matching_hash_no_raise(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "f.txt").write_bytes(b"hello")
            notes = rv.tier2_artifacts(self._art("f.txt", b"hello"), [], root, False)
            self.assertEqual(notes, [])

    def test_tampered_hash_raises(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "f.txt").write_bytes(b"changed")
            with self.assertRaises(rv.LintError):
                rv.tier2_artifacts(self._art("f.txt", b"hello"), [], root, False)

    def test_absent_basename_unverifiable_even_strict(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            notes = rv.tier2_artifacts(self._art("findings.md", b"x"), [], root, True)
            self.assertEqual(len(notes), 1)
            self.assertIn("UNVERIFIABLE", notes[0])

    def test_absent_pathshaped_strict_raises(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            with self.assertRaises(rv.LintError):
                rv.tier2_artifacts(self._art("src/foo.ts", b"x"), [], root, True)

    def test_absent_pathshaped_nonstrict_unverifiable(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            notes = rv.tier2_artifacts(self._art("src/foo.ts", b"x"), [], root, False)
            self.assertEqual(len(notes), 1)
            self.assertIn("UNVERIFIABLE", notes[0])


if __name__ == "__main__":
    unittest.main()
