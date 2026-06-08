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
import shutil
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


class TestVerifyWitness(unittest.TestCase):
    """Direct unit coverage of the factored verify_witness + derive_art_name."""

    def _exec_cited(self, exit_code, art="test-output.log", rng="L1-L40"):
        return {"n": 2, "verb": "EXEC",
                "args": f"`grep x f`  exit={exit_code}  dur=0.1s  out={art}#{rng}"}

    def _w(self, kind, expect, ran="TRACE#2"):
        return {"kind": kind, "payload": "x", "expect_fail": expect, "ran": ran}

    def test_pass_regex_match_raises_exact_message(self):
        rv = _import_rv()
        body = "starting\nerror: boom\n3 fail\n"
        with self.assertRaises(rv.LintError) as cm:
            rv.verify_witness(body, self._w("exec", "/error:/"), "PASS", self._exec_cited(0))
        self.assertEqual(
            str(cm.exception),
            "Tier-2: WITNESS expect-fail regex /error:/ matches body of test-output.log "
            "(witness would have fired → PASS rejected)")

    def test_pass_regex_no_match_clean(self):
        rv = _import_rv()
        self.assertTrue(rv.verify_witness("all good\n", self._w("exec", "/error:/"),
                                          "PASS", self._exec_cited(0)))

    def test_pass_exit_clause_match_raises(self):
        rv = _import_rv()
        with self.assertRaises(rv.LintError) as cm:
            rv.verify_witness("body", self._w("exec", "exit!=0"), "PASS", self._exec_cited(1))
        self.assertEqual(
            str(cm.exception),
            "Tier-2: WITNESS expect-fail exit-clause matches actual exit=1 "
            "(witness would have fired → PASS rejected)")

    def test_fail_no_evidence_raises_exact_message(self):
        rv = _import_rv()
        body = "starting tests...\nall tests passed, 220 passed.\n"
        with self.assertRaises(rv.LintError) as cm:
            rv.verify_witness(body, self._w("exec", "/\\d+ fail/"), "FAIL", self._exec_cited(0))
        self.assertEqual(
            str(cm.exception),
            "Tier-2 FAIL: no evidence of failure — exit=0 AND body does not match "
            "expect-fail /\\d+ fail/ (weak positive-evidence check)")

    def test_fail_with_content_match_clean(self):
        rv = _import_rv()
        body = "3 fail, 17 pass\n"
        self.assertTrue(rv.verify_witness(body, self._w("exec", "/\\d+ fail/"),
                                          "FAIL", self._exec_cited(0)))

    def test_s3_asymmetry_grep_read_pass_raises_fail_clean(self):
        rv = _import_rv()
        cited = {"n": 1, "verb": "READ", "args": "src/foo.ts sha256:" + "a" * 64}
        w = self._w("grep", "/error:/", ran="TRACE#1")
        body = "line\nerror: bad\n"
        # PASS leg inspects the READ/WROTE body → raises
        with self.assertRaises(rv.LintError):
            rv.verify_witness(body, w, "PASS", cited)
        # FAIL leg is EXEC-only → never inspects the READ body → clean
        self.assertTrue(rv.verify_witness(body, w, "FAIL", cited))


class TestTier2Witness(unittest.TestCase):
    def _w(self, expect, ran="TRACE#2"):
        return {"kind": "exec", "payload": "x", "expect_fail": expect, "ran": ran}

    def test_range_only_read_ignores_outside_match(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            lines = [f"line {i}\n" for i in range(1, 50)]
            lines[44] = "BOOM here\n"  # line 45 (index 44), outside L1-L40
            (root / "out.log").write_text("".join(lines))
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=out.log#L1-L40"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            # reads ONLY lines 1-40 → BOOM not seen → no raise
            notes = rv.tier2_witness(self._w("/BOOM/"), trace, root, False, "PASS")
            self.assertEqual(notes, [])

    def test_byte_range_1based_inclusive(self):
        # #B is 1-based INCLUSIVE, parallel to #L: #B2-B5 over "xBOOMy\n" reads bytes
        # 2..5 = "BOOM" (endpoint byte 5 'M' included). /BOOM/ matches the cited range →
        # witness would have fired → PASS rejected (raises). A half-open read would yield
        # "OOM" and miss it, so the raise proves the endpoint byte is included.
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "out.log").write_bytes(b"xBOOMy\n")
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=out.log#B2-B5"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            with self.assertRaises(rv.LintError):
                rv.tier2_witness(self._w("/BOOM/"), trace, root, False, "PASS")
            # And the raw range reader returns exactly the inclusive slice.
            self.assertEqual(rv._read_cited_range(root / "out.log", cited), "BOOM")

    def test_a0_start_no_slice_from_end_witness_fires(self):
        # Guard: a=0 start (#B0-B5 / #L0-L5) must NOT slice from the end. Pre-clamp,
        # [a-1:b] = [-1:b] → empty/wrong body for files longer than b → witness silently
        # bypassed → false PASS on disk. The expect-fail pattern sits in the LEADING
        # bytes, so a correct [0:b] read contains it and the witness must FIRE (raise).
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            # "BOOM" in leading bytes; file far longer than b so [-1:b] would be empty.
            (root / "out.log").write_bytes(b"BOOMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n")
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=out.log#B0-B5"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            # Raw reader returns real leading content (not the empty [-1:b] slice).
            # a=0 clamps to 1 → bytes [0:5] = "BOOMx" (5 leading bytes), not "".
            self.assertEqual(rv._read_cited_range(root / "out.log", cited), "BOOMx")
            # Witness fires → PASS rejected (no silent clean).
            with self.assertRaises(rv.LintError):
                rv.tier2_witness(self._w("/BOOM/"), trace, root, False, "PASS")

    def test_a0_line_start_no_slice_from_end_witness_fires(self):
        # Parallel #L0-L5 guard: a=0 line start must clamp to 1, not slice from the end.
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            lines = ["BOOM here\n"] + [f"line {i}\n" for i in range(2, 50)]
            (root / "out.log").write_text("".join(lines))
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=out.log#L0-L5"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            self.assertIn("BOOM", rv._read_cited_range(root / "out.log", cited))
            with self.assertRaises(rv.LintError):
                rv.tier2_witness(self._w("/BOOM/"), trace, root, False, "PASS")

    def test_absent_witness_basename_unverifiable(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=ephemeral.log#L1-L5"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            notes = rv.tier2_witness(self._w("/x/"), trace, root, True, "PASS")
            self.assertEqual(len(notes), 1)
            self.assertIn("UNVERIFIABLE", notes[0])

    def test_absent_witness_pathshaped_strict_raises(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            cited = {"n": 2, "verb": "EXEC", "args": "`x`  exit=0  out=logs/run.log#L1-L5"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            with self.assertRaises(rv.LintError):
                rv.tier2_witness(self._w("/x/"), trace, root, True, "PASS")


class TestCliDispatch(unittest.TestCase):
    def test_tier1_good_receipt_stdin_silent_zero(self):
        good = _load("sample-corpus/receipts.jsonl")[0]["receipt"]
        r = run("--tier1", "-", stdin=good)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_tier1_malformed_exit1_stderr(self):
        r = run("--tier1", "-", stdin="not a receipt")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.strip())

    def test_eval_samples_pass(self):
        r = run("--eval", str(CORPUS / "sample-corpus/receipts.jsonl"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("LINT-PASS", r.stdout)
        self.assertIn("summary: 5/5 receipts passed lint", r.stdout)

    def test_eval_inject_all_fail_but_exit_zero(self):
        # F1: --eval ALWAYS exits 0 for a readable file, even all-LINT-FAIL.
        r = run("--eval", str(CORPUS / "inject/shape-a-skip-claim.jsonl"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("LINT-FAIL", r.stdout)
        self.assertNotIn("LINT-PASS", r.stdout)

    def test_eval_tier2_only_rows_fail(self):
        # 102-inject (PASS) and 105-inject (FAIL) must LINT-FAIL via the Tier-2 path.
        rb = run("--eval", str(CORPUS / "inject/shape-b-witness-matches-expectfail.jsonl"))
        self.assertNotIn("LINT-PASS", rb.stdout)
        self.assertIn("102-inject", rb.stdout)
        rd = run("--eval", str(CORPUS / "inject/shape-d-fail-without-evidence.jsonl"))
        self.assertNotIn("LINT-PASS", rd.stdout)


class TestSelftest(unittest.TestCase):
    def test_selftest_green(self):
        r = run("--selftest")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_selftest_corpus_absent_nonzero(self):
        # Relocate the script where its __file__-anchored CORPUS_DIR does not exist.
        with tempfile.TemporaryDirectory() as td:
            relocated = pathlib.Path(td) / "rcpt_verify.py"
            shutil.copy(SCRIPT, relocated)
            r = subprocess.run([sys.executable, str(relocated), "--selftest"],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("corpus not found", (r.stderr + r.stdout).lower())


if __name__ == "__main__":
    unittest.main()
