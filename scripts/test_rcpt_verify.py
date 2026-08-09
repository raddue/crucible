#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/rcpt_verify.py.

Run from repo root:  python3 scripts/test_rcpt_verify.py
                  or  python3 -m unittest scripts.test_rcpt_verify -v

No pytest — matches the stdlib-only discipline of rcpt_verify.py itself, and the
flat-in-scripts/ layout of scripts/test_catalog.py (a `scripts/tests/` subdir is
caught by the repo-wide `tests/` .gitignore rule).
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import hashlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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

    def test_samples_lint_exact_verdict(self):
        # #441 gap-5: tightened from a vacuous assertIn({PASS,FAIL,BLOCKED}) — that
        # only pinned "didn't raise". lint_receipt returns each receipt's DECLARED
        # VERDICT when it lints clean, and the sample corpus is MIXED-verdict, so the
        # exact per-receipt map is the real check. (The no-raise sibling is kept
        # separately at test_v1_receipt_not_v11_linted — complementary, not redundant.)
        # Map keyed on dispatch-id (rows carry dispatch-id/skill/receipt, no id).
        EXPECTED = {
            "7-implementer": "PASS",
            "12-judge": "PASS",
            "8-implementer": "FAIL",
            "3-attacker": "BLOCKED",
            "15-reviewer": "FAIL",
        }
        rv = _import_rv()
        for rec in _load("sample-corpus/receipts.jsonl"):
            self.assertIn(rec["dispatch-id"], EXPECTED,
                          f"corpus row {rec['dispatch-id']!r} not in EXPECTED map — add it")
            self.assertEqual(rv.lint_receipt(rec["receipt"]), EXPECTED[rec["dispatch-id"]])

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


class TestV11Extension(unittest.TestCase):
    """v1.1 Tier-1 extension (#369 fast-follow): RCPT v1.1 headers enforce the
    receipt-local subset of return-convention.md §"Linter extension"; RCPT v1
    receipts are NOT subject to it (version-dispatch). Manifest-relative rules
    (SUPERSEDES uniqueness / no-double-supersede / witness-evidence trigger) are
    out of single-receipt scope and NOT tested here."""

    def test_conformant_v11_lints_pass(self):
        rv = _import_rv()
        for rec in _load("v11-corpus/receipts.jsonl"):
            self.assertEqual(rv.lint_receipt(rec["receipt"]), "PASS",
                             rec.get("dispatch-id"))

    def test_each_inject_shape_raises(self):
        rv = _import_rv()
        shapes = sorted((CORPUS / "v11-inject").glob("shape-*.jsonl"))
        self.assertTrue(shapes, "no v11-inject shapes found")
        for shape in shapes:
            for rec in _load(shape.relative_to(CORPUS).as_posix()):
                with self.assertRaises(rv.LintError, msg=f"{shape.name} did not raise"):
                    rv.lint_receipt(rec["receipt"])

    def test_v1_receipt_not_v11_linted(self):
        """A bare RCPT v1 receipt with no TRIPWIRE/SUPERSEDES must still lint
        (version-dispatch): the v1.1 presence rules apply only to v1.1 headers."""
        rv = _import_rv()
        for rec in _load("sample-corpus/receipts.jsonl"):
            self.assertIn(rv.lint_receipt(rec["receipt"]), {"PASS", "FAIL", "BLOCKED"})

    def test_parse_v11_sections_returns_none_for_v1(self):
        rv = _import_rv()
        v1 = _load("sample-corpus/receipts.jsonl")[0]["receipt"]
        self.assertIsNone(rv.parse_v11_sections(v1))

    def test_parse_v11_sections_recovers_tail_for_v11(self):
        rv = _import_rv()
        v11 = _load("v11-corpus/receipts.jsonl")[0]["receipt"]
        parsed = rv.parse_v11_sections(v11)
        self.assertIsNotNone(parsed)
        self.assertIsNotNone(parsed["tripwire"])
        self.assertEqual(parsed["supersedes"], "none")


class TestTier2Ledger(unittest.TestCase):
    """Tier-2 part-3 receipt-ledger binding (#369 PR-B): each DISPATCHED TRACE line
    must resolve to a receipt-ledger.jsonl entry on the (dispatch_id, rcpt_sha256,
    verdict) triple — `phase` is NOT part of the match. Driven by the committed
    tier2-fixtures/ledger-manifest.jsonl rows."""

    def _run_row(self, rv, row):
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            if "ledger_raw" in row:
                led.write_text(row["ledger_raw"])
            else:
                led.write_text("".join(json.dumps(e) + "\n" for e in row["ledger"]))
            sections = rv.parse_receipt(row["receipt"])
            trace = rv.parse_trace(sections["TRACE"])
            try:
                rv.tier2_ledger(trace, led)
                return "pass"
            except rv.LintError:
                return "fail"

    def test_ledger_manifest_rows(self):
        rv = _import_rv()
        rows = _load("tier2-fixtures/ledger-manifest.jsonl")
        self.assertTrue(rows, "no ledger-manifest rows")
        for row in rows:
            self.assertEqual(self._run_row(rv, row), row["expect"], row["id"])

    def test_blocked_child_binds(self):
        """A verdict=BLOCKED DISPATCHED child binds to a verdict=BLOCKED ledger row
        (binding runs regardless of the child's own verdict). Non-vacuity: flipping the
        ledger row's verdict to PASS breaks the triple match and RAISES — proving the
        row's verdict=BLOCKED is load-bearing in the bind."""
        rv = _import_rv()
        h = "e5" * 32
        receipt = (
            "RCPT v1.1 build/5-orchestrator\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n  plan.md  sha256:" + "a1" * 32 + "  900\nTRACE\n"
            "  1  READ  plan.md  sha256:" + "b2" * 32 + "\n"
            "  2  DISPATCHED  build/6-implementer  verdict=BLOCKED  rcpt-sha256:" + h + "\n"
            "CLAIMS\n  dispatched-ok=true  from=TRACE#2\n"
            "WITNESS    lint:trace-consistent  expect-fail=/inconsistent/  ran=TRACE#1\n"
            "SUSPICION  0.00\nNEXT       (none)\n"
        )
        trace = rv.parse_trace(rv.parse_receipt(receipt)["TRACE"])
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            row = {"dispatch_id": "6-implementer", "phase": "build:execute/3",
                   "rcpt_sha256": h, "verdict": "BLOCKED"}
            led.write_text(json.dumps(row) + "\n")
            self.assertEqual(rv.tier2_ledger(trace, led), [])  # binds clean
            # Non-vacuity: flip the verdict so the triple no longer matches → must raise.
            led.write_text(json.dumps({**row, "verdict": "PASS"}) + "\n")
            with self.assertRaises(rv.LintError):
                rv.tier2_ledger(trace, led)

    def test_leaf_receipt_noop(self):
        """A leaf receipt (no DISPATCHED line) under --ledger is a clean no-op: zero
        DISPATCHED entries → tier2_ledger returns [] for both a populated and an empty
        ledger (the dominant case now that --ledger is mandatory)."""
        rv = _import_rv()
        receipt = (
            "RCPT v1.1 build/6-implementer\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n  plan.md  sha256:" + "a1" * 32 + "  900\nTRACE\n"
            "  1  READ  plan.md  sha256:" + "b2" * 32 + "\n"
            "  2  EXEC  `npm test`  exit=0  dur=1.0s  out=test.log#L1-L5\n"
            "CLAIMS\n  tests-green=true  from=TRACE#2\n"
            "WITNESS    exec  expect-fail=/\\d+ fail/  ran=TRACE#2\n"
            "SUSPICION  0.00\nNEXT       (none)\n"
        )
        trace = rv.parse_trace(rv.parse_receipt(receipt)["TRACE"])
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            led.write_text(json.dumps(
                {"dispatch_id": "99-unrelated", "phase": "p", "rcpt_sha256": "f6" * 32,
                 "verdict": "PASS"}) + "\n")
            self.assertEqual(rv.tier2_ledger(trace, led), [])  # populated ledger → noop
            led.write_text("")
            self.assertEqual(rv.tier2_ledger(trace, led), [])  # empty ledger → noop


class TestCliLedger(unittest.TestCase):
    def _ledger_file(self, td, entries):
        p = pathlib.Path(td) / "receipt-ledger.jsonl"
        p.write_text("".join(json.dumps(e) + "\n" for e in entries))
        return p

    def test_cli_match_exit0(self):
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-match"]
        with tempfile.TemporaryDirectory() as td:
            led = self._ledger_file(td, row["ledger"])
            r = run("--tier2", "--ledger", str(led), "-", stdin=row["receipt"])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_cli_mismatch_exit1(self):
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-wrong-hash"]
        with tempfile.TemporaryDirectory() as td:
            led = self._ledger_file(td, row["ledger"])
            r = run("--tier2", "--ledger", str(led), "-", stdin=row["receipt"])
            self.assertEqual(r.returncode, 1)
            self.assertIn("ledger", r.stderr.lower())

    def test_cli_no_ledger_dispatched_is_unverifiable_nonfatal(self):
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-match"]  # receipt has a DISPATCHED line
        r = run("--tier2", "-", stdin=row["receipt"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("UNVERIFIABLE: ledger binding", r.stderr)

    def test_cli_no_ledger_no_dispatched_is_silent(self):
        """A receipt with no DISPATCHED line emits no ledger advisory."""
        v1 = _load("sample-corpus/receipts.jsonl")[0]["receipt"]
        r = run("--tier2", "-", stdin=v1)
        self.assertNotIn("ledger binding", r.stderr)

    def test_cli_malformed_ledger_exit1_no_traceback(self):
        """A malformed-JSONL ledger gives exit 1 + a clean bullet, not a traceback."""
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-match"]  # any receipt with a DISPATCHED line
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            led.write_text("{ not json\n")
            r = run("--tier2", "--ledger", str(led), "-", stdin=row["receipt"])
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("ledger", r.stderr.lower())

    def test_cli_nondict_ledger_exit1_no_traceback(self):
        """A non-dict ledger row gives exit 1 + a clean bullet, not a traceback."""
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-match"]
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            led.write_text('["x"]\n')
            r = run("--tier2", "--ledger", str(led), "-", stdin=row["receipt"])
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("ledger", r.stderr.lower())

    def test_cli_tier1_ledger_ignored_advisory_nonfatal(self):
        """--ledger under --tier1 is never consulted (binding is Tier-2); a mismatching
        ledger must NOT cause a FAIL — it emits a non-fatal advisory and exits 0."""
        rows = {r["id"]: r for r in _load("tier2-fixtures/ledger-manifest.jsonl")}
        row = rows["ledger-wrong-hash"]  # mismatching ledger + a DISPATCHED-line receipt
        with tempfile.TemporaryDirectory() as td:
            led = self._ledger_file(td, row["ledger"])
            r = run("--tier1", "--ledger", str(led), "-", stdin=row["receipt"])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--ledger ignored under --tier1", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


class TestRootContainment(unittest.TestCase):
    """#397 defect 2 — resolve_base must confine resolution to --root (or its git
    toplevel). `..`-traversal and absolute-outside-root names must NOT be read; they
    resolve to None (→ UNVERIFIABLE, or path-shaped+strict FAIL — never an out-of-tree
    disk read while linting attacker-influenced receipts)."""

    def test_resolve_base_rejects_dotdot_traversal(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            outer = pathlib.Path(td)
            (outer / "secret.txt").write_text("TOP SECRET")
            root = outer / "root"
            root.mkdir()
            # `../secret.txt` escapes root → must not resolve to the outer file
            self.assertIsNone(rv.resolve_base("../secret.txt", root))

    def test_resolve_base_rejects_absolute_outside_root(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            outer = pathlib.Path(td)
            (outer / "secret.txt").write_text("TOP SECRET")
            root = outer / "root"
            root.mkdir()
            self.assertIsNone(rv.resolve_base(str(outer / "secret.txt"), root))

    def test_resolve_base_allows_absolute_inside_root(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            f = root / "in.txt"
            f.write_text("OK")
            got = rv.resolve_base(str(f), root)
            self.assertIsNotNone(got)
            self.assertEqual(got.read_text(), "OK")

    def test_resolve_base_rejects_symlink_escape(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            outer = pathlib.Path(td)
            (outer / "secret.txt").write_text("TOP SECRET")
            root = outer / "root"
            root.mkdir()
            link = root / "link.txt"
            link.symlink_to(outer / "secret.txt")  # in-tree name, out-of-tree target
            self.assertIsNone(rv.resolve_base("link.txt", root))

    def test_tier2_artifacts_traversal_strict_fails_not_reads(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            outer = pathlib.Path(td)
            data = b"TOP SECRET"
            (outer / "secret.txt").write_bytes(data)
            root = outer / "root"
            root.mkdir()
            art = {"../secret.txt": {"hash": hashlib.sha256(data).hexdigest(),
                                     "size": str(len(data))}}
            # Even though the out-of-tree file's hash WOULD match, containment forbids
            # the read → strict + path-shaped → FAIL (never a silent hash "proof").
            with self.assertRaises(rv.LintError):
                rv.tier2_artifacts(art, [], root, True)

    def test_resolve_base_repo_toplevel_allowance_boundary(self):
        rv = _import_rv()
        # Pin the repo-toplevel allowance BOUNDARY: a file inside the repo but
        # OUTSIDE --root resolves (the documented repo-allowance), while a
        # `..`-traversal to a file OUTSIDE the repo still returns None.
        with tempfile.TemporaryDirectory() as td:
            parent = pathlib.Path(td)
            outer = parent / "outer"  # the repo
            outer.mkdir()
            (outer / ".git").mkdir()  # dir, so _git_toplevel finds `outer` as repo toplevel
            root = outer / "root"
            root.mkdir()
            (outer / "in-repo.txt").write_text("IN REPO")  # in repo, outside --root
            (parent / "out-of-repo.txt").write_text("OUT OF REPO")  # sibling of repo, outside it
            # in-repo file outside --root resolves via the repo-toplevel allowance
            got = rv.resolve_base("in-repo.txt", root)
            self.assertIsNotNone(got)
            self.assertEqual(got.read_text(), "IN REPO")
            # `../`-traversal from root up past the repo to the out-of-repo file → None
            self.assertIsNone(rv.resolve_base("../../out-of-repo.txt", root))


class TestNoneSentinelSymmetry(unittest.TestCase):
    """#397 defect 3 — the `(none)` empty sentinel is accepted uniformly across
    ARTIFACTS / TRACE / CLAIMS (it already was for ARTIFACTS/NEXT)."""

    def test_parse_trace_accepts_none(self):
        rv = _import_rv()
        self.assertEqual(rv.parse_trace(["  (none)"]), [])

    def test_parse_claims_accepts_none(self):
        rv = _import_rv()
        self.assertEqual(rv.parse_claims(["  (none)"]), [])

    def test_full_receipt_none_trace_and_claims_lints(self):
        rv = _import_rv()
        receipt = (
            "RCPT v1 build/x\n"
            "VERDICT  BLOCKED  conf=0.50\n"
            "ARTIFACTS\n  (none)\n"
            "TRACE\n  (none)\n"
            "CLAIMS\n  (none)\n"
            "WITNESS    exec:`run`  expect-fail=/\\d+ fail/  ran=UNRUNNABLE:tooling-absent\n"
            "SUSPICION  0.00\nNEXT       (none)\n"
        )
        self.assertEqual(rv.lint_receipt(receipt), "BLOCKED")


class TestWitnessSpanCapActual(unittest.TestCase):
    """#397 defect 4 — the Tier-1 (b-a)*80 estimate under-counts long lines; the
    authoritative 4 KiB cap is enforced at Tier-2 against the ACTUAL bytes read."""

    def _w(self, expect="/zzzzz-no-match/", ran="TRACE#2"):
        return {"kind": "exec", "payload": "x", "expect_fail": expect, "ran": ran}

    def test_long_lines_exceed_actual_cap_raises(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            # 40 lines × 200 bytes ≈ 8 KiB actual, but Tier-1 estimate (40-1)*80=3120 < 4096.
            (root / "out.log").write_text("".join("X" * 199 + "\n" for _ in range(40)))
            cited = {"n": 2, "verb": "EXEC", "args": "`run`  exit=0  out=out.log#L1-L40"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            with self.assertRaises(rv.LintError) as cm:
                rv.tier2_witness(self._w(), trace, root, False, "PASS")
            self.assertIn("4 KiB", str(cm.exception))

    def test_short_lines_within_cap_clean(self):
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "out.log").write_text("".join(f"line {i}\n" for i in range(1, 41)))
            cited = {"n": 2, "verb": "EXEC", "args": "`run`  exit=0  out=out.log#L1-L40"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            self.assertEqual(rv.tier2_witness(self._w(), trace, root, False, "PASS"), [])

    def test_byte_range_invalid_utf8_within_cap_no_false_fail(self):
        # 4000 raw bytes of 0xFF: under WITNESS_SPAN_CAP (4096), but each byte decodes
        # to U+FFFD (3 bytes), so len(body_text.encode()) ≈ 12000 would false-FAIL the
        # cap. The raw-bytes measurement must keep this in-budget range clean. Tier-1's
        # #B span is b-a (B1-B4000 → 3999 < 4096), so it passes Tier-1 too.
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "out.log").write_bytes(b"\xff" * 4000)
            cited = {"n": 2, "verb": "EXEC", "args": "`run`  exit=0  out=out.log#B1-B4000"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            self.assertEqual(rv.tier2_witness(self._w(), trace, root, False, "PASS"), [])

    def test_byte_range_raw_span_exceeds_cap_raises(self):
        # The cap is real for #B too: 5000 raw bytes (> 4096) must still raise.
        rv = _import_rv()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "out.log").write_bytes(b"\xff" * 5000)
            cited = {"n": 2, "verb": "EXEC", "args": "`run`  exit=0  out=out.log#B1-B5000"}
            trace = [{"n": 1, "verb": "READ", "args": "a"}, cited]
            with self.assertRaises(rv.LintError) as cm:
                rv.tier2_witness(self._w(), trace, root, False, "PASS")
            self.assertIn("4 KiB", str(cm.exception))


class TestEditWroteHashDeliberateNonGate(unittest.TestCase):
    """#412 (BS1): an undeclared EDIT/WROTE hash is provenance, NOT a verified claim.
    A receipt whose TRACE WROTEs a file that is neither a declared ARTIFACT key nor a
    declared ARTIFACT hash lints PASS — the deliberate trust-model decision
    (return-convention.md "for each EDIT / WROTE in TRACE"), not a hole. This locks it:
    a future "fix" that hard-FAILs undeclared EDIT/WROTE would flip these AND the
    committed clean-pass fixtures + canonical example, so it must be a conscious
    trust-model change, never an accidental one. Both shapes are covered — the
    bare-basename PoC and the path-shaped variant (is_path_shaped True), the case an
    audit is most likely to re-flag as 'but this one looks resolvable.'"""

    BOGUS = "beadfeed" * 8  # 64 hex; matches no declared artifact hash

    def _inject(self, verb, path):
        # Insert an effect-bearing verb whose hash is undeclared and whose path is
        # not an ARTIFACTS key, into the known-good corpus receipt[0]. (Fails LOUD,
        # not silent, if receipt[0]'s shape ever drops its CLAIMS header.)
        base = _load("sample-corpus/receipts.jsonl")[0]["receipt"]
        lines = base.splitlines()
        lines.insert(lines.index("CLAIMS"), f"  4  {verb}  {path}  sha256:{self.BOGUS}")
        return "\n".join(lines)

    def test_bare_basename_poc_still_passes(self):
        rv = _import_rv()
        self.assertEqual(rv.lint_receipt(self._inject("WROTE", "secrets.env")), "PASS")

    def test_path_shaped_poc_still_passes(self):
        rv = _import_rv()
        self.assertEqual(rv.lint_receipt(self._inject("WROTE", "src/secrets.env")), "PASS")

    def test_edit_verb_also_passes(self):
        # The dead branch serves BOTH EDIT and WROTE (rcpt_verify.py:243) — lock both.
        rv = _import_rv()
        self.assertEqual(rv.lint_receipt(self._inject("EDIT", "secrets.env")), "PASS")
        self.assertEqual(rv.lint_receipt(self._inject("EDIT", "src/secrets.env")), "PASS")


class TestTraceRefGuard(unittest.TestCase):
    """#440: a malformed `TRACE#<non-digits>` reference (attacker-influenced
    receipt text) must lint-FAIL cleanly (LintError), NOT raise a raw ValueError
    traceback. Six sites fed `int()` an unvalidated suffix; this locks them, and
    the --eval batch isolation that the ValueError used to break."""

    def _base(self):
        return _load("sample-corpus/receipts.jsonl")[0]["receipt"]

    def _sub(self, text, old, new):
        self.assertIn(old, text, f"fixture drift: {old!r} not in receipt")
        return text.replace(old, new, 1)

    def test_claim_citation_non_numeric_is_lint_error(self):
        rv = _import_rv()
        bad = self._sub(self._base(), "from=TRACE#2", "from=TRACE#2x")
        with self.assertRaises(rv.LintError):
            rv.lint_receipt(bad)

    def test_witness_ran_trailing_junk_is_lint_error(self):
        rv = _import_rv()
        # WITNESS ran= captured greedily → trailing junk reaches int() (the bug
        # hit live during the #412 gate). Must be a clean LintError.
        bad = self._sub(self._base(), "ran=TRACE#3", "ran=TRACE#3 junk")
        with self.assertRaises(rv.LintError):
            rv.lint_receipt(bad)

    def test_cli_malformed_citation_exit1_no_traceback(self):
        bad = self._sub(self._base(), "from=TRACE#2", "from=TRACE#2x")
        r = run("--tier1", "-", stdin=bad)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("ValueError", r.stderr)

    def test_eval_batch_isolates_poisoned_record(self):
        # A good record followed by one whose citation used to crash the WHOLE
        # batch (ValueError escaping _eval_record's LintError-only catch).
        good = self._base()
        bad = self._sub(good, "from=TRACE#2", "from=TRACE#2x")
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "corpus.jsonl"
            p.write_text(
                json.dumps({"dispatch-id": "good", "receipt": good}) + "\n" +
                json.dumps({"dispatch-id": "poisoned", "receipt": bad}) + "\n"
            )
            r = run("--eval", str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("good", r.stdout)
        self.assertIn("poisoned", r.stdout)
        self.assertIn("LINT-FAIL", r.stdout)        # the bad one classified, not crashed
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_eval_batch_isolates_malformed_json_line(self):
        good = self._base()
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "corpus.jsonl"
            p.write_text(
                json.dumps({"dispatch-id": "good", "receipt": good}) + "\n" +
                "{not valid json\n"
            )
            r = run("--eval", str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("good", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class TestParseOutRange(unittest.TestCase):
    def setUp(self):
        self.rv = _import_rv()

    def test_basic_line_range(self):
        r = self.rv.parse_out_range("out=foo.py#L1-L5 mode=x")
        self.assertEqual((r.artifact, r.kind, r.start, r.end), ("foo.py", "L", 1, 5))

    def test_byte_range(self):
        r = self.rv.parse_out_range("out=a.bin#B10-B20")
        self.assertEqual((r.artifact, r.kind, r.start, r.end), ("a.bin", "B", 10, 20))

    def test_mixed_kind_rejected(self):
        self.assertIsNone(self.rv.parse_out_range("out=foo#L1-B5"))

    def test_no_out_returns_none(self):
        self.assertIsNone(self.rv.parse_out_range("pattern=foo ran=TRACE#1"))

    def test_double_range_rejected(self):
        # #442 G6b / F1: the 5 out=#range sites diverge on a double-#range (old L137
        # greedy/last vs the non-greedy first-range readers), so the grammar rejects
        # multi-#range outright — None makes check_exec_range_bound LINT-FAIL at Tier-1,
        # before any Tier-2 site, so all 5 agree.
        self.assertIsNone(self.rv.parse_out_range("out=a#L1-L5#L9-L1"))  # neg second range
        self.assertIsNone(self.rv.parse_out_range("out=a#L1-L5#L9-L9"))  # both valid -> still rejected (tightening)

    def test_hash_in_artifact_rejected(self):
        self.assertIsNone(self.rv.parse_out_range("out=a#b#L1-L5"))

    def test_trailing_nonrange_arg_not_over_rejected(self):
        # the (?!#[LB]\d) lookahead must reject only a trailing second #<range>, not
        # ordinary trailing chars after a well-formed range.
        self.assertEqual(self.rv.parse_out_range("out=a#L1-L5 mode=x")[:4], ("a", "L", 1, 5))
        self.assertEqual(self.rv.parse_out_range("out=a#L1-L5,x")[:4], ("a", "L", 1, 5))


class TestExpectFailPattern(unittest.TestCase):
    def setUp(self):
        self.rv = _import_rv()

    def test_regex_form_returned_verbatim(self):
        self.assertEqual(self.rv._expect_fail_pattern("/err.*/"), "err.*")

    def test_literal_form_is_escaped(self):
        self.assertEqual(self.rv._expect_fail_pattern('"a.b"'), re.escape("a.b"))

    def test_exit_clause_returns_none(self):
        self.assertIsNone(self.rv._expect_fail_pattern("exit!=0"))


class TestParseWitness(unittest.TestCase):
    """#441 gap-3: direct coverage of parse_witness's WITNESS grammar — ~11 LintError
    legs on the security-load-bearing witness line + the happy-path dict shape. None
    was asserted before. parse_witness takes a body = list of lines; line 0 is parsed.
    Several legs share one message (raise 9's /.*/, /.+/, /abc/ all emit the shared
    'wildcard/too-short'), so plain assertRaises(LintError) per leg — not
    assertRaisesRegex on per-leg messages (matches test_each_inject_shape_raises)."""

    def setUp(self):
        self.rv = _import_rv()

    # --- raise legs ---
    def test_empty_body_missing(self):
        # `[]` is falsy -> the `if not body` leg.
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness([])

    def test_empty_string_line_routes_to_missing_ran(self):
        # `[""]` is truthy, so it falls through to line-0 "" -> the missing-ran= leg,
        # NOT the `if not body` "WITNESS missing" leg.
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness([""])

    def test_na_not_permitted(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["(n/a)"])

    def test_missing_ran(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["exec:cmd  expect-fail=exit!=0"])

    def test_missing_expect_fail(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["exec:cmd  ran=2026-06-24"])

    def test_kind_payload_no_colon(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["execcmd  expect-fail=exit!=0  ran=2026-06-24"])

    def test_unknown_kind(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["foo:bar  expect-fail=exit!=0  ran=2026-06-24"])

    def test_lint_rule_unknown(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["lint:bogus-rule  expect-fail=exit!=0  ran=2026-06-24"])

    def test_expect_fail_empty(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["exec:cmd  expect-fail=  ran=2026-06-24"])

    def test_wildcard_or_too_short_regex(self):
        # All three hit the shared "wildcard/too-short" leg. The wildcard-set arm
        # ({".*", ".+"}) is observationally unreachable: both members are 2 chars, so
        # `len(pattern) < 4` short-circuits first. Assert the raise, not which arm.
        for ef in ("/.*/", "/.+/", "/abc/"):
            with self.assertRaises(self.rv.LintError, msg=f"expect-fail={ef}"):
                self.rv.parse_witness([f"exec:cmd  expect-fail={ef}  ran=2026-06-24"])

    def test_literal_too_short(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(['exec:cmd  expect-fail="ab"  ran=2026-06-24'])

    def test_invalid_signature_form(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(["exec:cmd  expect-fail=bogus  ran=2026-06-24"])

    # --- happy paths (assert returned dict fields) ---
    def test_happy_exec_exit_signature(self):
        out = self.rv.parse_witness(["exec:cmd  expect-fail=exit!=0  ran=2026-06-24"])
        self.assertEqual(out["kind"], "exec")
        self.assertEqual(out["payload"], "cmd")
        self.assertEqual(out["expect_fail"], "exit!=0")
        self.assertEqual(out["ran"], "2026-06-24")

    def test_happy_grep_literal(self):
        out = self.rv.parse_witness(['grep:pattern  expect-fail="literal text"  ran=2026-06-24'])
        self.assertEqual(out["kind"], "grep")
        self.assertEqual(out["payload"], "pattern")  # only happy path whose expect-fail has a space — locks space-handling
        self.assertEqual(out["expect_fail"], '"literal text"')

    def test_happy_lint_regex(self):
        out = self.rv.parse_witness(["lint:all-claims-cited  expect-fail=/regexp4/  ran=2026-06-24"])
        self.assertEqual(out["kind"], "lint")
        self.assertEqual(out["payload"], "all-claims-cited")

    def test_happy_signature_forms(self):
        # #474 / D3: `match` USED to be admitted here on kind=exec with no pattern=
        # clause — a bare `match` carries no predicate, so Tier-2 read it as clean
        # (the P0). D3 makes that shape a Tier-1 error two ways over (clause required;
        # bare `match` is kind=grep-only per return-convention.md § "witness structural
        # check"), so this loop
        # keeps only the exit= form and the `match` legs move to the #474 block below.
        # DECLARED CASUALTY: the plan's D3 blast-radius sweep says test_rcpt_verify.py
        # "constructs no bare-`match` witness at all" — this line was that witness.
        for ef in ("exit=-1", "exit!=0"):
            out = self.rv.parse_witness([f"exec:cmd  expect-fail={ef}  ran=2026-06-24"])
            self.assertEqual(out["expect_fail"], ef)


# ─────────────────────────────────────────────────────────────────────────────
# #474 — WITNESS `expect-fail=match` is inert at Tier-2 (P0 fail-open).
# Plan: docs/plans/2026-08-07-474-witness-match-fail-open.md — S1's 22 tests.
# 16 are RED on unmodified main (1, 3-7, 9, 10, 11, 14, 16-20, 22); the other 6
# (2, 8, 12, 13, 15, 21) are regression pins that are GREEN on main and must stay
# green — a red pin means the change broke something, NOT that the pin is wrong.
# ─────────────────────────────────────────────────────────────────────────────

H64 = "ab" * 32                   # syntactically valid sha256 field for builder receipts
COUNTS_HIT = "SEVERITY-COUNTS: fatal=1 significant=3 minor=0\n"
COUNTS_CLEAN = "SEVERITY-COUNTS: fatal=0 significant=0 minor=3\n"
MANDATED_CLAUSE = "pattern=/significant=[1-9]|fatal=[1-9]/"


def _receipt(witness, *, verdict="PASS", conf="0.90", artifacts=(), trace=(),
             claims=("(none)",), nxt="(none)", skill="red-team/1-devils-advocate"):
    """Minimal well-formed v1 receipt wrapped around the WITNESS line under test."""
    lines = [f"RCPT v1 {skill}", f"VERDICT  {verdict}  conf={conf}", "ARTIFACTS"]
    lines += [f"  {n}  sha256:{h}  {s}" for n, h, s in artifacts] or ["  (none)"]
    lines.append("TRACE")
    lines += [f"  {i}  {t}" for i, t in enumerate(trace, 1)] or ["  (none)"]
    lines.append("CLAIMS")
    lines += [f"  {c}" for c in claims]
    lines += [f"WITNESS    {witness}", "SUSPICION  0.10", f"NEXT       {nxt}"]
    return "\n".join(lines) + "\n"


class TestWitnessPatternClause(unittest.TestCase):
    """S1 tests 3, 4, 7, 18, 19, 22 — the `pattern=` clause grammar at Tier-1
    (parse_witness only; zero disk reads)."""

    MANDATED = (f"grep:round-3-findings.md#L1-L1  {MANDATED_CLAUSE}  "
                "expect-fail=match  ran=TRACE#1")

    def setUp(self):
        self.rv = _import_rv()

    # --- test 3 — the clause is extracted, expect_fail keeps its verbatim "match" (D1/D2)
    def test_3_mandated_line_yields_pattern_and_keeps_expect_fail(self):
        out = self.rv.parse_witness([self.MANDATED])
        self.assertEqual(out.get("pattern"), "/significant=[1-9]|fatal=[1-9]/")
        self.assertEqual(out["expect_fail"], "match")

    # --- test 4 — bare `match` with NO clause is a Tier-1 error (D3 rule i),
    #     and bare `match` is kind=grep-only (D3 rule iv)
    def test_4_bare_match_without_clause_raises(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(
                ["grep:round-3-findings.md#L1-L1  expect-fail=match  ran=TRACE#1"])

    def test_4b_bare_match_on_non_grep_kind_raises(self):
        # D3's kind restriction — scope containment for D3's own change: post-D3 an
        # exec:/lint: witness carrying a clause would newly run the reviewer's regex
        # against the EXEC out= body, a shape nothing in the repo produces.
        for kind in ("exec:cmd", "lint:all-claims-cited"):
            with self.assertRaises(self.rv.LintError, msg=kind):
                self.rv.parse_witness([f"{kind}  expect-fail=match  ran=TRACE#1"])
            with self.assertRaises(self.rv.LintError, msg=kind):
                self.rv.parse_witness(
                    [f"{kind}  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1"])

    # --- test 7 — a malformed clause LINT-fails; a quoted literal must NOT
    def test_7_malformed_regex_clause_is_lint_error_not_pattern_error(self):
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                ["grep:f.md#L1-L1  pattern=/[unclosed/  expect-fail=match  ran=TRACE#1"])
        self.assertNotIsInstance(cm.exception, re.error)

    def test_7b_quoted_literal_that_is_not_a_regex_must_not_raise(self):
        # REGRESSION PIN (green on main, must stay green). "**Severity:** Fatal" is
        # the natural predicate over this repo's own findings format and is exactly
        # what D3 prescribes when the /…/ alternation cannot express one. re.compile
        # of the RAW inner text raises `nothing to repeat`; the compile guard runs on
        # the DERIVED (re.escape'd) source, so it is provably inert here (round 9/SIG-2).
        with self.assertRaises(re.error):           # the raw text really is not a regex
            re.compile("**Severity:** Fatal")
        # must not raise — that IS the pin (asserting the new `pattern` key here
        # would make a green pin red on main; that assertion lives in test 3).
        self.rv.parse_witness(
            ['grep:f.md#L1-L1  pattern="**Severity:** Fatal"  expect-fail=match  ran=TRACE#1'])

    # --- test 18 — the payload is parsed ONCE, and payload vs payload_raw are
    #     discriminated (trap (a): a range-shaped substring inside the clause)
    def test_18_payload_parsed_once_and_two_strings_discriminated(self):
        out = self.rv.parse_witness([self.MANDATED])
        self.assertEqual(out["art"], "round-3-findings.md")
        self.assertEqual(out["range_kind"], "L")
        self.assertEqual((out["range_a"], out["range_b"]), (1, 1))
        self.assertEqual(out["payload"], "round-3-findings.md#L1-L1")
        self.assertEqual(out["payload_raw"],
                         f"round-3-findings.md#L1-L1  {MANDATED_CLAUSE}")
        self.assertNotIn("pattern=", out["payload"])
        self.assertIn("pattern=", out["payload_raw"])

    def test_18b_range_shaped_substring_inside_clause_is_not_the_payload_range(self):
        out = self.rv.parse_witness(
            ["grep:round-3-findings.md#L1-L1  pattern=/x#L1-L2/  expect-fail=match  ran=TRACE#1"])
        self.assertEqual((out["range_a"], out["range_b"]), (1, 1))   # NOT 1/2 from the clause
        self.assertEqual(out["art"], "round-3-findings.md")

    # --- test 19 — the UNDELIMITED clause (round 4 / SIG-1): present, compiles,
    #     yet derives None → #474 verbatim. Rejected at Tier-1.
    def test_19_undelimited_clause_raises_at_tier1(self):
        self.assertIsNotNone(re.compile("significant=[1-9]"))   # it really does compile
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(
                ["grep:f.md#L1-L1  pattern=significant=[1-9]  expect-fail=match  ran=TRACE#1"])

    def test_19b_helper_seam_derivation_is_defined_for_exactly_two_forms(self):
        self.assertEqual(self.rv._expect_fail_pattern("match", "/significant=[1-9]/"),
                         "significant=[1-9]")
        self.assertEqual(self.rv._expect_fail_pattern("match", '"literal"'),
                         re.escape("literal"))
        # the documented precondition at the helper seam (D2): the helper is NOT
        # self-defending — Tier-1 rejects the bare form, the helper keeps returning None.
        self.assertIsNone(self.rv._expect_fail_pattern("match", "significant=[1-9]"))

    def test_19c_bare_clause_never_reaches_tier2(self):
        text = _receipt(
            "grep:round-3-findings.md#L1-L1  pattern=significant=[1-9]  "
            "expect-fail=match  ran=TRACE#1",
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError):
            self.rv.lint_receipt(text)

    # --- test 22 — the EMPTY delimited clause (round 9 / SIG-1): #474's second door
    def test_22_empty_clause_raises_with_the_empty_derivation_message(self):
        # The message pin IS the test: len('') = 0 < 4, so an implementation that
        # ships only the floor still raises here and would look green without it.
        for clause in ("//", '""'):
            with self.assertRaises(self.rv.LintError, msg=clause) as cm:
                self.rv.parse_witness(
                    [f"grep:f.md#L1-L1  pattern={clause}  expect-fail=match  ran=TRACE#1"])
            self.assertEqual(
                str(cm.exception),
                f"WITNESS pattern= clause derives an empty regex source: {clause!r}")
            self.assertNotIn("too short", str(cm.exception))   # textually distinct from the floor

    def test_22b_floor_message_is_the_other_one(self):
        # The floor still fires on a short-but-nonempty derivation, with ITS text —
        # so the two dispositions cannot be confused (D3(b)).
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                ["grep:f.md#L1-L1  pattern=/0F/  expect-fail=match  ran=TRACE#1"])
        self.assertEqual(str(cm.exception),
                         "WITNESS pattern= clause too short: '/0F/'")

    def test_22c_empty_derivation_is_the_empty_string_not_none(self):
        # Keeps the two dispositions distinguishable at the helper seam: a "fix"
        # that maps empty → None silently re-enters the Tier-2 hole.
        self.assertEqual(self.rv._expect_fail_pattern("match", "//"), "")
        self.assertEqual(self.rv._expect_fail_pattern("match", '""'), "")

    def test_22d_empty_clause_never_reaches_tier2(self):
        text = _receipt(
            "grep:round-3-findings.md#L1-L1  pattern=//  expect-fail=match  ran=TRACE#1",
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError):
            self.rv.lint_receipt(text)


class TestWitnessTier1Guards(unittest.TestCase):
    """S1 tests 8, 9, 12, 13, 14, 15 — the receipt-level Tier-1 guards (D3/D6).
    Every one of these is disk-free."""

    def setUp(self):
        self.rv = _import_rv()

    # --- test 9 — the DECLARED payload span bound, and its message names the
    #     clause-stripped payload (not the predicate beside it)
    def test_9_declared_span_over_bound_raises_naming_stripped_payload(self):
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                ["grep:round-3-findings.md#B1-B4098  pattern=/significant=[1-9]/  "
                 "expect-fail=match  ran=TRACE#1"])
        self.assertEqual(str(cm.exception),
                         "witness range exceeds 4 KiB: round-3-findings.md#B1-B4098")

    def test_9b_declared_span_inside_bound_is_clean(self):
        # #B is 1-based inclusive, so b-a undercounts by one (D6 signal (i)); assert
        # clear of the boundary rather than on it.
        out = self.rv.parse_witness(
            ["grep:round-3-findings.md#B1-B4000  pattern=/significant=[1-9]/  "
             "expect-fail=match  ran=TRACE#1"])
        self.assertEqual(out["range_b"], 4000)

    def test_9c_line_range_uses_the_sound_1_byte_per_line_floor(self):
        # 4096 < span → reject; a 100-line range (which EXEC's 80-B/line estimate
        # would reject) must NOT be rejected here.
        self.rv.parse_witness(
            ["grep:f.md#L1-L4000  pattern=/significant=[1-9]/  expect-fail=match  ran=TRACE#1"])
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_witness(
                ["grep:f.md#L1-L5000  pattern=/significant=[1-9]/  expect-fail=match  ran=TRACE#1"])

    # --- test 12 — REGRESSION PIN: the committed, CI-gated in-spec shape stays clean
    def test_12_committed_12_judge_witness_stays_clean(self):
        line = ("grep:review.md#L1-L80  pattern=/Fatal:\\s*[1-9]/  "
                "expect-fail=match  ran=TRACE#2")
        self.rv.parse_witness([line])          # must not raise — that IS the pin
        rec = [r for r in _load("sample-corpus/receipts.jsonl")
               if r["dispatch-id"] == "12-judge"][0]
        self.assertIn(line, rec["receipt"], "fixture drift: 12-judge WITNESS line moved")
        self.assertEqual(self.rv.lint_receipt(rec["receipt"]), "PASS")

    # --- test 13 — REGRESSION PIN: rangeless grep payloads are a committed shape
    def test_13_rangeless_grep_payloads_still_lint_clean(self):
        out = self.rv.parse_witness(
            ['grep:pattern  expect-fail="literal text"  ran=2026-06-24'])
        self.assertEqual(out["payload"], "pattern")
        self.assertIsNone(out.get("range_kind"))   # .get: the key is new in S2(b)
        h = self.rv.parse_witness(["grep:boom  expect-fail=/boom/ ran=TRACE#1"])
        self.assertEqual(h["payload"], "boom")
        self.assertIsNone(h.get("range_kind"))
        # …and the committed fixture that carries that exact shape is still there.
        fx = [json.loads(l) for l in
              (CORPUS / "tier2-fixtures/manifest.jsonl").read_text().splitlines() if l.strip()]
        self.assertTrue(any("grep:boom" in json.dumps(r) for r in fx),
                        "fixture drift: rangeless grep fixture h is gone")

    # --- test 14 — ARTIFACTS membership, written against lint_receipt (D6/SIG-1);
    #     parse_witness cannot see ARTIFACTS at all, so a parse-level version of this
    #     test cannot be written — if one appears, S3(5) was implemented at the wrong site.
    def test_14_ranged_grep_artifact_absent_from_artifacts_raises(self):
        text = _receipt(
            f"grep:round-3-findings.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
            artifacts=[("round-2-ledger.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.lint_receipt(text)
        self.assertEqual(str(cm.exception),
                         "WITNESS grep artifact not in ARTIFACTS: round-3-findings.md")

    def test_14b_same_receipt_with_the_artifact_declared_lints_clean(self):
        text = _receipt(
            f"grep:round-3-findings.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"])
        self.assertEqual(self.rv.lint_receipt(text), "PASS")

    def test_14c_membership_is_scoped_to_ranged_payloads(self):
        # A RANGELESS grep payload keeps today's behaviour and is exempt (S3(4)).
        text = _receipt(
            'grep:pattern  expect-fail="literal text"  ran=TRACE#1',
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"])
        self.assertEqual(self.rv.lint_receipt(text), "PASS")

    # --- test 15 — REGRESSION PIN: EXEC's calibration is unmoved by S3's helper split
    def test_15_exec_calibration_and_message_unchanged(self):
        args = "`run`  exit=0  dur=1s  out=a.log#L1-L100"
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.check_exec_range_bound(args)
        self.assertEqual(str(cm.exception), f"EXEC range exceeds 4 KiB: {args}")

    def test_15b_same_declared_range_on_a_grep_witness_does_not_raise(self):
        # The conjunct that catches a shared helper carrying the grep calibration
        # into EXEC (or vice versa): #L1-L100 is over EXEC's 80-B/line estimate and
        # far under the grep path's 1-B/line floor.
        self.rv.parse_witness(          # must not raise — that IS the pin
            ["grep:f.md#L1-L100  pattern=/significant=[1-9]/  expect-fail=match  ran=TRACE#1"])

    # --- test 15d — round-4 / M6: WITNESS_SPAN_CAP is the ONE name for the 4 KiB
    #     budget. `check_span_bound` used to hard-code 4096 thirteen lines above the
    #     constant's declaration, so the two spellings could drift silently. Moving the
    #     cap and re-running both call sites is the discriminator: a hard-coded literal
    #     would ignore it and neither range would newly raise.
    def test_15d_span_cap_is_the_single_constant_both_sites_read(self):
        self.assertEqual(self.rv.WITNESS_SPAN_CAP, 4096)
        self.rv.WITNESS_SPAN_CAP = 10          # fresh module per test (setUp re-imports)
        with self.assertRaises(self.rv.LintError):      # EXEC site, 80 B/line estimate
            self.rv.check_exec_range_bound("`run`  exit=0  out=a.log#B1-B12")
        with self.assertRaises(self.rv.LintError):      # grep site, 1 B/line floor
            self.rv.parse_witness(
                ["grep:f.md#B1-B12  pattern=/significant=[1-9]/  "
                 "expect-fail=match  ran=TRACE#1"])

    def test_15c_exec_negative_range_message_unchanged(self):
        args = "`run`  exit=0  out=a.log#L9-L1"
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.check_exec_range_bound(args)
        self.assertEqual(str(cm.exception), f"EXEC range negative: {args}")

    # --- test 8 — REGRESSION PIN: the ran=SKIPPED NEXT-verbatim check still binds
    #     the FULL payload including the clause (D1 / payload_raw), message pinned
    def test_8_skipped_next_verbatim_check_binds_the_full_payload(self):
        payload_raw = f"round-3-findings.md#L1-L1  {MANDATED_CLAUSE}"
        text = _receipt(
            f"grep:{payload_raw}  expect-fail=match  ran=SKIPPED:tooling-absent",
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"],
            nxt="file the follow-up")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.lint_receipt(text)
        self.assertEqual(
            str(cm.exception),
            "WITNESS ran=SKIPPED requires NEXT to contain witness payload verbatim; "
            f"payload={payload_raw!r}  NEXT='file the follow-up'")

    def test_8b_skipped_passes_when_next_carries_the_full_payload(self):
        payload_raw = f"round-3-findings.md#L1-L1  {MANDATED_CLAUSE}"
        text = _receipt(
            f"grep:{payload_raw}  expect-fail=match  ran=SKIPPED:tooling-absent",
            artifacts=[("round-3-findings.md", H64, "2980")],
            trace=[f"WROTE  round-3-findings.md  sha256:{H64}"],
            nxt=f"re-run {payload_raw} at merge-time")
        self.assertEqual(self.rv.lint_receipt(text), "PASS")


class TestWitness474Tier2(unittest.TestCase):
    """S1 tests 1, 2, 5, 6, 10, 11, 16, 17, 20, 21 — the Tier-2 predicate and the
    body it runs against (D2/D4/D6)."""

    def setUp(self):
        self.rv = _import_rv()
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _write(self, name, text):
        p = self.root / name
        p.write_text(text)
        return p

    def _w(self, line):
        return self.rv.parse_witness([line])

    def _wrote(self, name):
        return [{"n": 1, "verb": "WROTE", "args": f"{name}  sha256:{H64}"}]

    def _exec(self, out, exit_code=0):
        return [{"n": 1, "verb": "EXEC",
                 "args": f"`run`  exit={exit_code}  dur=1s  out={out}"}]

    # --- test 1 — the issue's reproduction, verbatim
    def test_1_mandated_witness_fires_on_a_contradicting_body(self):
        self._write("round-1-findings.md", COUNTS_HIT + "…prose…\n")
        w = self._w(f"grep:round-1-findings.md#L1-L1  {MANDATED_CLAUSE}  "
                    "expect-fail=match  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w, self._wrote("round-1-findings.md"),
                                  self.root, False, "PASS")
        self.assertIn("witness would have fired → PASS rejected", str(cm.exception))
        self.assertIn("round-1-findings.md", str(cm.exception))

    # --- test 2 — REGRESSION PIN: the clean counterpart must not false-BLOCK
    def test_2_clean_round_body_does_not_fire(self):
        self._write("round-1-findings.md", COUNTS_CLEAN + "…prose…\n")
        w = self._w(f"grep:round-1-findings.md#L1-L1  {MANDATED_CLAUSE}  "
                    "expect-fail=match  ran=TRACE#1")
        self.assertEqual(
            self.rv.tier2_witness(w, self._wrote("round-1-findings.md"),
                                  self.root, False, "PASS"), [])

    # --- test 5 — facet (b), WROTE-cited: the payload's own #range is what is read
    def test_5_wrote_cited_payload_range_narrows_the_body(self):
        self._write("f.md", COUNTS_CLEAN + "prose\n" + COUNTS_HIT)
        w = self._w("grep:f.md#L1-L1  expect-fail=/fatal=[1-9]/  ran=TRACE#1")
        # line 3 matches, line 1 does not — a whole-file read false-BLOCKs.
        self.assertEqual(
            self.rv.tier2_witness(w, self._wrote("f.md"), self.root, False, "PASS"), [])

    def test_5b_wrote_cited_payload_range_still_fires_inside_the_range(self):
        self._write("f.md", COUNTS_HIT + "prose\n" + COUNTS_CLEAN)
        w = self._w(f"grep:f.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError):
            self.rv.tier2_witness(w, self._wrote("f.md"), self.root, False, "PASS")

    # --- test 6 — facet (b), EXEC-cited MISMATCH: payload names X, out= names Y
    def test_6_exec_cited_mismatch_reads_the_payload_artifact(self):
        self._write("x.md", COUNTS_HIT)
        self._write("y.log", "all quiet\n" * 5)
        w = self._w(f"grep:x.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w, self._exec("y.log#L1-L5"), self.root, False, "PASS")
        self.assertIn("matches body of x.md", str(cm.exception))
        self.assertNotIn("y.log", str(cm.exception))

    # --- test 10 — Tier-1-legal declared range whose ACTUAL bytes blow the 4 KiB cap
    def test_10_actual_bytes_over_cap_raises_at_tier2(self):
        self._write("big.md", "".join("X" * 199 + "\n" for _ in range(40)))   # ≈8 KiB
        w = self._w("grep:big.md#L1-L40  pattern=/zzzz-no-match/  "
                    "expect-fail=match  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w, self._wrote("big.md"), self.root, False, "PASS")
        self.assertIn("4 KiB", str(cm.exception))

    # --- test 11 — an empty resolved body on a ranged grep witness is a LintError,
    #     while `body_text is None` still returns True (the :640-641 parity contract)
    def test_11_empty_string_body_raises_on_disk_for_both_forms(self):
        self._write("x.md", "one line\n")
        for line in (f"grep:x.md#L50-L60  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
                     "grep:x.md#L50-L60  expect-fail=/fatal=[1-9]/  ran=TRACE#1"):
            with self.assertRaises(self.rv.LintError, msg=line):
                self.rv.tier2_witness(self._w(line), self._wrote("x.md"),
                                      self.root, False, "PASS")

    def test_11b_empty_string_body_raises_on_the_eval_path(self):
        for line in (f"grep:x.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
                     "grep:x.md#L1-L1  expect-fail=/fatal=[1-9]/  ran=TRACE#1"):
            with self.assertRaises(self.rv.LintError, msg=line):
                self.rv._eval_tier2(self._w(line), self._wrote("x.md"),
                                    {"x.md": ""}, "PASS")

    def test_11c_body_none_still_returns_clean(self):
        # REGRESSION PIN (green on main): `None` is documented lint.py parity
        # (`art_name not in artifact_bodies`), NOT the empty-string case.
        line = f"grep:x.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1"
        w = self._w(line)
        self.assertTrue(self.rv.verify_witness(None, w, "PASS",
                                               self._wrote("x.md")[0]))
        self.rv._eval_tier2(w, self._wrote("x.md"), {}, "PASS")      # no body → clean

    def test_11d_empty_body_on_the_fail_leg_stays_clean(self):
        # The empty-body guard is PASS-scoped (round 4 / MIN-2): a FAIL + grep +
        # EXEC-cited witness reads the UN-narrowed out= range and must not newly raise.
        self._write("y.log", "")
        w = self._w("grep:x.md#L1-L1  expect-fail=/fatal=[1-9]/  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w, self._exec("y.log#L1-L5"), self.root, False, "FAIL")
        self.assertIn("no evidence of failure", str(cm.exception))   # not the empty-body guard

    # --- test 16 — kind=grep + expect-fail=/…/, payload range NARROWER than out=
    def test_16_payload_range_narrower_than_out_range_is_what_is_read(self):
        self._write("verify-log.txt", "0\n" * 5 + "post-fix lines: 673\n" + "0\n" * 5)
        w = self._w("grep:verify-log.txt#L1-L1  expect-fail=/[1-9][0-9]/  ran=TRACE#1")
        # today's linter reads out=#L1-L11 and matches the unrelated `67` at line 6
        self.assertEqual(
            self.rv.tier2_witness(w, self._exec("verify-log.txt#L1-L11"),
                                  self.root, False, "PASS"), [])

    # --- test 17 — FAIL-leg pattern threading (both legs)
    def test_17_fail_leg_matching_body_supplies_evidence(self):
        self._write("y.log", COUNTS_HIT)
        w = self._w(f"grep:y.log#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1")
        self.assertEqual(
            self.rv.tier2_witness(w, self._exec("y.log#L1-L1"), self.root, False, "FAIL"), [])

    def test_17b_fail_leg_nonmatching_body_keeps_the_byte_identical_message(self):
        self._write("y.log", COUNTS_CLEAN)
        w = self._w(f"grep:y.log#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w, self._exec("y.log#L1-L1"), self.root, False, "FAIL")
        self.assertEqual(
            str(cm.exception),
            "Tier-2 FAIL: no evidence of failure — exit=0 AND body does not match "
            "expect-fail match (weak positive-evidence check)")

    # --- test 20 — the --strict path-shaped class change (§0e flip class 3)
    def test_20_strict_pathshaped_hardfail_becomes_unverifiable(self):
        w = self._w(f"grep:round-1-findings.md#L1-L1  {MANDATED_CLAUSE}  "
                    "expect-fail=match  ran=TRACE#1")
        trace = [{"n": 1, "verb": "WROTE",
                  "args": f"/nonexistent/abs/round-1-findings.md  sha256:{H64}"}]
        notes = self.rv.tier2_witness(w, trace, self.root, True, "PASS")
        self.assertEqual(
            notes, ["UNVERIFIABLE: witness round-1-findings.md (no file under root)"])

    # --- test 21 — REGRESSION PIN: on FAIL, artifact AND range both stay with
    #     derive_art_name; neither comes from the payload
    def test_21_fail_leg_keeps_artifact_and_range_together(self):
        self._write("y.log", "MARKERY here\nMARKERY again\n" + "filler\n" * 8)
        self._write("x.md", "filler\n" * 4 + "MARKERX here\nMARKERX again\n")
        trace = self._exec("y.log#L1-L2")
        # the body is y.log sliced at the out= range → the Y marker supplies evidence
        w_hit = self._w("grep:x.md#L5-L6  expect-fail=/MARKERY/  ran=TRACE#1")
        self.assertEqual(self.rv.tier2_witness(w_hit, trace, self.root, False, "FAIL"), [])
        # …and the X marker (present only in the payload's file+range) does NOT
        w_miss = self._w("grep:x.md#L5-L6  expect-fail=/MARKERX/  ran=TRACE#1")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(w_miss, trace, self.root, False, "FAIL")
        self.assertEqual(
            str(cm.exception),
            "Tier-2 FAIL: no evidence of failure — exit=0 AND body does not match "
            "expect-fail /MARKERX/ (weak positive-evidence check)")


# ─────────────────────────────────────────────────────────────────────────────
# #474 quality gate, round 1 — the three code findings (SIG-1, SIG-2, SIG-3).
# Tests 24-26 are RED against the S2-S6 implementation; test 23 pins a divergence
# that implementation introduced and this round documents rather than removes.
# ─────────────────────────────────────────────────────────────────────────────


class TestRound1RangelessMatch(unittest.TestCase):
    """SIG-1 — `expect-fail=match` requires a ranged payload. Deleting the `#L1-L1`
    from the mandated witness turned off ARTIFACTS membership, the span bound, the
    payload-sourced body and the empty-body rejection all at once, and reproduced
    #474 verbatim: a clean PASS on a findings file declaring nonzero counts."""

    def setUp(self):
        self.rv = _import_rv()

    # --- test 24 — the escape itself
    def test_24_rangeless_match_payload_raises_at_tier1(self):
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                [f"grep:round-1-findings.md  {MANDATED_CLAUSE}  "
                 "expect-fail=match  ran=TRACE#1"])
        self.assertEqual(
            str(cm.exception),
            "WITNESS expect-fail=match requires a ranged grep payload "
            "(grep:<artifact>#<range>): 'round-1-findings.md'")

    def test_24b_the_reproduction_receipt_no_longer_lints_clean(self):
        # The full shape SIG-1 executed: undeclared artifact, no range, PASS verdict.
        # Pre-fix this receipt was accepted at Tier-1 and its predicate was then run
        # against derive_art_name's file — one the witness never names.
        text = _receipt(
            f"grep:round-1-findings.md  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
            trace=[f"READ  design.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError):
            self.rv.lint_receipt(text)

    def test_24c_ranged_counterpart_is_accepted_so_the_range_is_the_discriminator(self):
        # Same line plus `#L1-L1` plus the declaration the range now requires: clean.
        # Without this conjunct test 24 is satisfiable by rejecting every grep witness.
        text = _receipt(
            f"grep:round-1-findings.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1",
            artifacts=[("round-1-findings.md", H64, "2980")],
            trace=[f"READ  design.md  sha256:{H64}"])
        self.assertEqual(self.rv.lint_receipt(text), "PASS")

    # --- test 25 — REGRESSION PIN: the committed rangeless shapes are untouched.
    #     They carry `expect-fail=/…/`, not `match`, which is what makes SIG-1's
    #     predicate free (measured: 0 of 14 `match` sites are rangeless).
    def test_25_rangeless_non_match_signatures_still_lint_clean(self):
        for line in ('grep:boom  expect-fail=/boom/ ran=TRACE#1',
                     'grep:pattern  expect-fail="literal text"  ran=2026-06-24'):
            out = self.rv.parse_witness([line])      # must not raise — that IS the pin
            self.assertIsNone(out["range_kind"], msg=line)
        # …and the committed fixture carrying the first of them is still there.
        fx = [json.loads(l) for l in
              (CORPUS / "tier2-fixtures/manifest.jsonl").read_text().splitlines() if l.strip()]
        self.assertTrue(any("grep:boom" in json.dumps(r) for r in fx),
                        "fixture drift: rangeless grep fixture h is gone")


class TestRound1ClauseBesideNonMatch(unittest.TestCase):
    """SIG-2 — the clause ladder used to live inside `if expect_fail == "match"`, while
    the strip that removes the clause from the payload is unconditional for kind=grep.
    A clause beside a `/regex/` or `"literal"` signature was therefore stripped,
    validated by nothing, and silently discarded at Tier-2."""

    def setUp(self):
        self.rv = _import_rv()

    # --- test 26 — the two shapes D3(a)/(d) exist to reject passed one branch over
    def test_26_malformed_clause_is_rejected_on_the_non_match_path_too(self):
        for clause, expected in (
                ("//", "WITNESS pattern= clause derives an empty regex source: '//'"),
                ("/[unclosed/", None),                       # message carries re's text
                ("/0F/", "WITNESS pattern= clause too short: '/0F/'"),
                ("bare-token",
                 'WITNESS pattern= clause must be /regex/ or "literal": \'bare-token\''),
        ):
            with self.assertRaises(self.rv.LintError, msg=clause) as cm:
                self.rv.parse_witness(
                    [f"grep:f.md#L1-L1  pattern={clause}  "
                     "expect-fail=/zzzz-never/  ran=TRACE#1"])
            self.assertNotIsInstance(cm.exception, re.error)
            if expected is not None:
                self.assertEqual(str(cm.exception), expected)
            else:
                self.assertIn("WITNESS pattern= clause is not a valid regex",
                              str(cm.exception))

    def test_26b_a_wellformed_clause_beside_a_non_match_signature_is_rejected(self):
        # The realistic error SIG-2 names: a reviewer sharpens the clause and leaves a
        # stale `expect-fail=/…/` from an earlier draft. Two declared predicates, and
        # the linter used to evaluate the stale one and report clean.
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                ["grep:f.md#L1-L1  pattern=/significant=[1-9]/  "
                 "expect-fail=/zzzz-never/  ran=TRACE#1"])
        self.assertEqual(
            str(cm.exception),
            "WITNESS pattern= clause is only meaningful with expect-fail=match "
            "(got expect-fail='/zzzz-never/'); the clause would be silently ignored")

    def test_26c_the_discarded_predicate_can_no_longer_reach_tier2(self):
        # End-to-end: the body says fatal=1, the CLAUSE would fire on it, the stale
        # signature would not. Pre-fix: LINT-PASS. It must now never get that far.
        text = _receipt(
            "grep:f.md#L1-L1  pattern=/fatal=[1-9]/  expect-fail=/zzzz-never/  ran=TRACE#1",
            artifacts=[("f.md", H64, "40")],
            trace=[f"WROTE  f.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError):
            self.rv.lint_receipt(text)

    def test_26d_pins_that_the_clause_and_signature_paths_stay_separable(self):
        # No-false-BLOCK conjunct: a clause-free `/regex/` signature and a clause-plus-
        # `match` signature both still lint clean, so 26/26b/26c are not satisfiable by
        # rejecting anything that carries either token.
        self.rv.parse_witness(
            ["grep:f.md#L1-L1  expect-fail=/significant=[1-9]/  ran=TRACE#1"])
        self.rv.parse_witness(
            [f"grep:f.md#L1-L1  {MANDATED_CLAUSE}  expect-fail=match  ran=TRACE#1"])


class TestRound1InlineDiskDisposition(unittest.TestCase):
    """SIG-3 — fixture-(m) shape given INLINE bodies: the witness payload names one
    artifact, the cited EXEC's `out=` names another, and `artifact_bodies` supplies
    only the latter. D4 re-pointed the PASS-leg read at the payload artifact, so
    `bodies.get` misses, `body_text` is None, and the --eval leg returns clean while
    the same receipt on disk raises.

    These tests PIN that divergence rather than removing it — see verify_witness's
    "DISK vs --eval DIVERGENCE 2" for why failing the inline leg closed would create a
    disposition divergence instead of removing one. What they must show is that the
    mismatch branch is really taken (not merely asserted about) and that the fixture
    corpus can no longer drift into the shape unnoticed."""

    WITNESS = ("grep:round-4-findings.md#L1-L1  "
               "pattern=/significant=[1-9]|fatal=[1-9]/  expect-fail=match  ran=TRACE#2")

    def setUp(self):
        self.rv = _import_rv()
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _rec(self, bodies):
        text = _receipt(
            self.WITNESS,
            artifacts=[("round-4-findings.md", H64, "81"), ("witness-grep.log", H64, "62")],
            trace=[f"WROTE  round-4-findings.md  sha256:{H64}",
                   "EXEC   `grep -nE significant round-4-findings.md`  exit=0  dur=0.1s  "
                   "out=witness-grep.log#L1-L2"],
            claims=["severity-max=fatal  from=round-4-findings.md#L1-L1"],
            skill="red-team/4-devils-advocate")
        return {"dispatch-id": "4-devils-advocate", "receipt": text,
                "artifact_bodies": bodies}

    # --- test 23 — the mismatch branch, exercised on both legs of the same receipt
    def test_23_inline_leg_is_clean_when_bodies_omit_the_payload_artifact(self):
        rec = self._rec({"witness-grep.log": COUNTS_HIT})
        disp, info = self.rv._eval_record(rec)
        self.assertEqual(disp, "LINT-PASS", info)
        # …and the branch that produced it really is the missing-body one.
        sections = self.rv.parse_receipt(rec["receipt"])
        witness = self.rv.parse_witness(sections["WITNESS"])
        trace = self.rv.parse_trace(sections["TRACE"])
        art, from_payload = self.rv.witness_art_name(witness, trace[1], "PASS")
        self.assertTrue(from_payload)
        self.assertEqual(art, "round-4-findings.md")
        self.assertNotIn(art, rec["artifact_bodies"])
        # …and the derivation D4 REPLACED would have hit: without this conjunct the
        # test passes on an implementation where the re-point was never applied and
        # `bodies.get` was always going to find the cited artifact.
        self.assertEqual(self.rv.derive_art_name(trace[1], "PASS"), "witness-grep.log")
        self.assertIn("witness-grep.log", rec["artifact_bodies"])

    def test_23b_the_same_receipt_on_disk_raises(self):
        rec = self._rec({"witness-grep.log": COUNTS_HIT})
        (self.root / "round-4-findings.md").write_text(COUNTS_HIT)
        (self.root / "witness-grep.log").write_text(COUNTS_HIT)
        sections = self.rv.parse_receipt(rec["receipt"])
        witness = self.rv.parse_witness(sections["WITNESS"])
        trace = self.rv.parse_trace(sections["TRACE"])
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(witness, trace, self.root, False, "PASS")
        self.assertEqual(
            str(cm.exception),
            "Tier-2: WITNESS expect-fail regex /significant=[1-9]|fatal=[1-9]/ matches "
            "body of round-4-findings.md (witness would have fired → PASS rejected)")

    def test_23c_supplying_the_payload_artifact_inline_makes_the_legs_agree(self):
        # The control: keyed on the artifact the witness actually verifies, the inline
        # leg reaches the same LINT-FAIL. So 23/23b are a body-availability divergence,
        # not a rule disagreement — which is exactly what the docstring claims.
        rec = self._rec({"round-4-findings.md": COUNTS_HIT})
        disp, info = self.rv._eval_record(rec)
        self.assertEqual(disp, "LINT-FAIL")
        self.assertIn("matches body of round-4-findings.md", info)

    def test_23d_crosscheck_rejects_a_row_that_does_not_supply_what_it_verifies(self):
        # The guard that keeps the fixture corpus out of this shape: an artifact_bodies
        # row whose ranged grep witness verifies an artifact it does not supply is
        # coverage that cannot fail, and selftest step (iv) now says so.
        rec = self._rec({"witness-grep.log": COUNTS_HIT})
        problems = self.rv._selftest_crosscheck(rec, rec["artifact_bodies"])
        self.assertTrue(
            any("coverage that cannot fail" in p for p in problems), problems)
        self.assertTrue(any("round-4-findings.md" in p for p in problems), problems)

    def test_23e_the_committed_grep_inline_row_passes_that_guard(self):
        # No-false-BLOCK conjunct + a pin on the one committed kind=grep
        # artifact_bodies row: it supplies the artifact it verifies, so the new guard
        # is silent on it and step (iv) still compares dispositions as before.
        rows = [json.loads(l) for l in
                (CORPUS / "inject/shape-e-grep-witness-inline-body.jsonl")
                .read_text().splitlines() if l.strip()]
        self.assertTrue(rows, "fixture drift: the kind=grep inline-body inject row is gone")
        for rec in rows:
            problems = self.rv._selftest_crosscheck(rec, rec["artifact_bodies"])
            self.assertEqual(
                [p for p in problems if "coverage that cannot fail" in p], [])


class TestRound2DuplicateClause(unittest.TestCase):
    """Round-2 / SIG-1 — `_WITNESS_CLAUSE_RE` is `\\s*$`-anchored, so on a payload
    carrying TWO `pattern=` tokens `re.search` binds the LAST one and leaves the first
    sitting inertly inside `payload`. Only the last is shape-checked by
    `_check_clause_shape` and only the last is evaluated at Tier-2, so APPENDING ONE
    TOKEN to the mandated red-team witness restored #474 verbatim: a clean PASS over a
    findings body declaring nonzero counts, with the author's real predicate demoted to
    dead text. The winning clause is the trailing one — the one an appender controls.

    Two declared predicates ACROSS fields is already a hard reject (test 26b), and
    `return-convention.md` ships the reason as normative text: the receipt declares two
    predicates and the linter cannot know which the author meant. Two predicates INSIDE
    one field is the same ambiguity, so it gets the same answer — rejected, never
    silently resolved by position."""

    def setUp(self):
        self.rv = _import_rv()

    # --- test 27 — the escape itself
    def test_27_two_pattern_clauses_raise_at_tier1(self):
        line = (f"grep:round-9-findings.md#L1-L1  {MANDATED_CLAUSE}  "
                "pattern=/zzzz-no-match/  expect-fail=match  ran=TRACE#2")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness([line])
        self.assertEqual(
            str(cm.exception),
            "WITNESS carries more than one pattern= clause: "
            "'round-9-findings.md#L1-L1  pattern=/significant=[1-9]|fatal=[1-9]/  "
            "pattern=/zzzz-no-match/'")

    def test_27b_the_reproduction_receipt_no_longer_lints_clean(self):
        # The shape SIG-1 executed end-to-end: the mandated witness with one extra
        # never-matching clause appended. Pre-fix this was a clean Tier-1 PASS and the
        # appended clause was the only one Tier-2 ever evaluated.
        text = _receipt(
            f"grep:round-9-findings.md#L1-L1  {MANDATED_CLAUSE}  "
            "pattern=/zzzz-no-match/  expect-fail=match  ran=TRACE#2",
            artifacts=[("round-9-findings.md", H64, "2980")],
            trace=[f"READ  design.md  sha256:{H64}",
                   f"WROTE  round-9-findings.md  sha256:{H64}"])
        with self.assertRaises(self.rv.LintError):
            self.rv.lint_receipt(text)

    def test_27c_a_third_clause_is_rejected_by_the_same_rule(self):
        # The re-search runs against the STRIPPED payload, so the rule is on "more than
        # one" and not on "exactly two": N clauses collapse to the same rejection.
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.parse_witness(
                ["grep:f.md#L1-L1  pattern=/aaaa/  pattern=/bbbb/  pattern=/cccc/  "
                 "expect-fail=match  ran=TRACE#1"])
        self.assertIn("more than one pattern= clause", str(cm.exception))

    def test_27d_the_single_clause_counterpart_is_still_accepted(self):
        # No-false-BLOCK conjunct: without it, 27/27b/27c are satisfiable by rejecting
        # every clause-carrying witness — which would take the whole D3 ladder with it.
        out = self.rv.parse_witness(
            [f"grep:round-9-findings.md#L1-L1  {MANDATED_CLAUSE}  "
             "expect-fail=match  ran=TRACE#2"])
        self.assertEqual(out["pattern"], "/significant=[1-9]|fatal=[1-9]/")
        self.assertEqual(out["payload"], "round-9-findings.md#L1-L1")

    # --- test 28 — REGRESSION PIN: the rule is scoped to payloads a clause was really
    #     EXTRACTED from, so a rangeless grep payload whose SEARCH TEXT contains the
    #     literal `pattern=` is untouched. The token has to be non-trailing to reach
    #     this branch at all: a trailing `pattern=<bare>` is extracted as a clause and
    #     already raises via _check_clause_shape (test 26), which would make a pin
    #     written on that shape pass for an unrelated reason.
    def test_28_rangeless_payload_carrying_a_nontrailing_pattern_token_is_untouched(self):
        out = self.rv.parse_witness(
            ["grep:find pattern= here  expect-fail=/boom/  ran=TRACE#1"])
        self.assertIsNone(out["pattern"])
        self.assertEqual(out["payload"], "find pattern= here")
        self.assertIsNone(out["range_kind"])

    def test_28b_the_committed_rangeless_shapes_are_unmoved(self):
        for line in ('grep:boom  expect-fail=/boom/ ran=TRACE#1',
                     'grep:pattern  expect-fail="literal text"  ran=2026-06-24'):
            out = self.rv.parse_witness([line])   # must not raise — that IS the pin
            self.assertIsNone(out["pattern"], msg=line)
        fx = [json.loads(l) for l in
              (CORPUS / "tier2-fixtures/manifest.jsonl").read_text().splitlines() if l.strip()]
        self.assertTrue(any("grep:boom" in json.dumps(r) for r in fx),
                        "fixture drift: rangeless grep fixture h is gone")


class TestRound2FailLegIsNotEvaluated(unittest.TestCase):
    """Round-2 / SIG-2 — a PIN ON A DEFERRAL, not on a fix. `witness_art_name` scopes
    the payload-sourced artifact to `verdict == "PASS"`; on FAIL the body lookup falls
    back to `derive_art_name`, which is EXEC-`out=`-only on that leg. The mandated
    red-team witness cites `ran=TRACE#N` → a `WROTE`, so `art_name` is None,
    `tier2_witness` returns before reading anything, and the Tier-2 witness rules are
    dead — EVEN WHERE THE ARTIFACT RESOLVES PERFECTLY, which is what makes this
    distinct from the `--root` condition the Scope paragraph already names.

    Round 1 of every red-team dispatch is a FAIL by construction, and that FAIL receipt
    is the supersession anchor the fix agent cites. Reversing the asymmetry is a
    convention change (see verify_witness's ASYMMETRY note) and is deferred to the
    Tier-2 resolution issue. This test exists so the deferral is load-bearing: if the
    FAIL leg is ever made to verify, this goes red and the docs get corrected with it."""

    WITNESS = ("grep:round-7-findings.md#L1-L1  "
               "pattern=/significant=[1-9]|fatal=[1-9]/  expect-fail=match  ran=TRACE#2")

    def setUp(self):
        self.rv = _import_rv()
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _parts(self, verdict):
        text = _receipt(
            self.WITNESS, verdict=verdict,
            artifacts=[("round-7-findings.md", H64, str(len(COUNTS_HIT.encode())))],
            trace=[f"READ  design.md  sha256:{H64}",
                   f"WROTE  round-7-findings.md  sha256:{H64}"],
            claims=["severity-max=significant  from=round-7-findings.md#L1-L1"],
            skill="red-team/7-devils-advocate")
        sections = self.rv.parse_receipt(text)
        return (self.rv.parse_witness(sections["WITNESS"]),
                self.rv.parse_trace(sections["TRACE"]))

    def test_29_fail_leg_with_a_wrote_cited_witness_reads_nothing(self):
        # The body is on disk, under --root, and the predicate matches it.
        (self.root / "round-7-findings.md").write_text(COUNTS_HIT)
        witness, trace = self._parts("FAIL")
        notes = self.rv.tier2_witness(witness, trace, self.root, True, "FAIL")
        self.assertEqual(notes, [])          # no raise AND no UNVERIFIABLE note
        # …and the branch that produced that is the None-art_name one, not a miss.
        art, from_payload = self.rv.witness_art_name(witness, trace[1], "FAIL")
        self.assertIsNone(art)
        self.assertFalse(from_payload)

    def test_29b_the_identical_receipt_on_PASS_does_fire(self):
        # The discriminator: same witness, same body, same root — only the verdict
        # differs. Without this conjunct 29 is satisfiable by a resolution failure.
        (self.root / "round-7-findings.md").write_text(COUNTS_HIT)
        witness, trace = self._parts("PASS")
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv.tier2_witness(witness, trace, self.root, True, "PASS")
        self.assertIn("matches body of round-7-findings.md", str(cm.exception))


# --- #474 / round-3 S5 — the CLI bound on witness-predicate evaluation ------------
#
# COST DISCIPLINE: none of these tests waits out the real 5-second bound. The handler
# is exercised by CALLING IT (test_30), and the end-to-end conversion runs with the
# bound INJECTED down to 50 ms (test_32) — the timer plumbing is identical, only the
# duration differs, so the test costs ~0.05 s and still proves that a catastrophic
# predicate returns a LintError instead of hanging. The real 5-second constant is
# pinned separately, as a value (test_30b), which costs nothing.
CATASTROPHIC = "/(a+)+$/"
CATASTROPHIC_BODY = "a" * 34 + "b\n"      # non-matching ⇒ full backtracking blow-up


class TestWitnessTimeoutBound(unittest.TestCase):
    def setUp(self):
        self.rv = _import_rv()
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _catastrophic_receipt(self):
        note = self.root / "verify-note.md"
        note.write_text(CATASTROPHIC_BODY)
        h = hashlib.sha256(note.read_bytes()).hexdigest()
        return _receipt(
            f"grep:verify-note.md#L1-L1  pattern={CATASTROPHIC}  "
            "expect-fail=match  ran=TRACE#1",
            verdict="PASS",
            artifacts=[("verify-note.md", h, str(note.stat().st_size))],
            trace=[f"WROTE  verify-note.md  sha256:{h}"],
            skill="quality-gate/9-fix-verifier")

    def _benign_receipt(self):
        note = self.root / "verify-note.md"
        note.write_text("all fixes verified\n")
        h = hashlib.sha256(note.read_bytes()).hexdigest()
        return _receipt(
            "grep:verify-note.md#L1-L1  pattern=/UNRESOLVED/  "
            "expect-fail=match  ran=TRACE#1",
            verdict="PASS",
            artifacts=[("verify-note.md", h, str(note.stat().st_size))],
            trace=[f"WROTE  verify-note.md  sha256:{h}"],
            skill="quality-gate/9-fix-verifier")

    # --- test 30 — the handler itself, driven directly: no signal, no wall clock
    def test_30_alarm_handler_raises_LintError(self):
        with self.assertRaises(self.rv.LintError) as cm:
            self.rv._witness_alarm(signal.SIGALRM, None)
        self.assertEqual(str(cm.exception), self.rv.WITNESS_TIMEOUT_MSG)

    # --- test 30b — the shipped bound and its message, pinned byte-for-byte. The
    #     message changed in round 4 (M3): the bound wraps tier2_witness, which does
    #     resolve_base + a whole-file read_text() + read_bytes() before re.search, so
    #     the old wording blamed the predicate for what may be a slow artifact read.
    def test_30b_bound_and_message_are_the_mandated_ones(self):
        self.assertEqual(self.rv.WITNESS_TIMEOUT_S, 5)
        self.assertEqual(
            self.rv.WITNESS_TIMEOUT_MSG,
            "witness evaluation exceeded 5s "
            "(predicate backtracking or a slow/large artifact read)")
        # it must not re-narrow to the predicate alone — that is the claim M3 falsified
        self.assertNotIn("witness predicate exceeded", self.rv.WITNESS_TIMEOUT_MSG)

    # --- test 31 — importing the module installs NOTHING. _gen.py, sweep.py and this
    #     very test module import rcpt_verify; a handler installed at import time would
    #     silently change SIGALRM for all three.
    def test_31_import_installs_no_sigalrm_handler(self):
        before = signal.getsignal(signal.SIGALRM)
        _import_rv()
        self.assertIs(signal.getsignal(signal.SIGALRM), before)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    # --- test 32 — end-to-end: a catastrophic predicate under the mandated invocation
    #     lint-FAILs with the timeout message instead of hanging. Bound injected to 50 ms.
    def test_32_catastrophic_predicate_becomes_a_LintError_not_a_hang(self):
        self.rv.WITNESS_TIMEOUT_S = 0.05
        err = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(self._catastrophic_receipt(), "tier2",
                                        self.root, True)
        elapsed = time.monotonic() - started
        self.assertEqual(rc, 1)
        self.assertEqual(err.getvalue().strip(), self.rv.WITNESS_TIMEOUT_MSG)
        self.assertLess(elapsed, 2.0)        # it did NOT wait out the real predicate
        # the finally disarmed the timer even on the raising path
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    # --- test 33 — a NORMAL predicate is unaffected, and the bound leaves no residue
    def test_33_normal_predicate_unaffected_and_timer_cleared(self):
        before = signal.getsignal(signal.SIGALRM)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(self._benign_receipt(), "tier2",
                                        self.root, True)
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertIs(signal.getsignal(signal.SIGALRM), before)

    # --- test 33b — the discriminator for 33: the same benign shape with a predicate
    #     that DOES match still fails on the ordinary expect-fail path, so 33's pass is
    #     a real clean verdict and not a witness that was never evaluated.
    def test_33b_benign_shape_still_fires_on_a_matching_predicate(self):
        note = self.root / "verify-note.md"
        note.write_text("UNRESOLVED: one finding remains\n")
        h = hashlib.sha256(note.read_bytes()).hexdigest()
        text = _receipt(
            "grep:verify-note.md#L1-L1  pattern=/UNRESOLVED/  "
            "expect-fail=match  ran=TRACE#1",
            verdict="PASS",
            artifacts=[("verify-note.md", h, str(note.stat().st_size))],
            trace=[f"WROTE  verify-note.md  sha256:{h}"],
            skill="quality-gate/9-fix-verifier")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(text, "tier2", self.root, True)
        self.assertEqual(rc, 1)
        self.assertIn("matches body of verify-note.md", err.getvalue())

    # --- test 34 — round-4 / M4: the bound BORROWS the process-wide ITIMER_REAL, so it
    #     must hand it back. The old finally called setitimer(ITIMER_REAL, 0)
    #     unconditionally and discarded setitimer's return value — the previous timer —
    #     silently cancelling an in-process caller's own alarm. 30 s is far outside the
    #     test's runtime, so a surviving timer is unambiguous.
    def test_34_a_callers_pre_armed_itimer_survives_the_bound(self):
        prev_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, lambda *a: None)
        signal.setitimer(signal.ITIMER_REAL, 30)
        self.addCleanup(signal.signal, signal.SIGALRM, prev_handler)
        self.addCleanup(signal.setitimer, signal.ITIMER_REAL, 0)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(self._benign_receipt(), "tier2", self.root, True)
        self.assertEqual(rc, 0, err.getvalue())
        remaining = signal.getitimer(signal.ITIMER_REAL)[0]
        self.assertGreater(remaining, 0.0)      # was 0.0 before the fix: cancelled

    def test_34b_with_no_caller_timer_the_bound_still_leaves_none_armed(self):
        # Discriminator for 34: the restore must be conditional on there having BEEN a
        # timer, not a blanket re-arm. (test_33 pins the same property end-to-end; this
        # states it as 34's counterpart so the pair reads as one rule.)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.rv._verify_single(self._benign_receipt(), "tier2", self.root, True)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    # --- test 35 — round-4 / M7: signal.setitimer/SIGALRM are Unix-only. Simulated by
    #     removing the attribute rather than by needing a non-Unix machine. Before the
    #     guard this raised AttributeError, which `except LintError` does not catch, so
    #     --tier2 aborted with a traceback where it used to emit a verdict.
    def test_35_tier2_degrades_to_unbounded_where_setitimer_is_absent(self):
        sentinel = object()
        saved = getattr(signal, "setitimer", sentinel)
        del signal.setitimer
        self.addCleanup(lambda: saved is not sentinel
                        and setattr(signal, "setitimer", saved))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(self._benign_receipt(), "tier2", self.root, True)
        self.assertEqual(rc, 0, err.getvalue())

    def test_35b_the_unbounded_fallback_still_evaluates_the_predicate(self):
        # Discriminator for 35: without this, a fallback that skipped tier2_witness
        # entirely would also return 0.
        note = self.root / "verify-note.md"
        note.write_text("UNRESOLVED: one finding remains\n")
        h = hashlib.sha256(note.read_bytes()).hexdigest()
        text = _receipt(
            "grep:verify-note.md#L1-L1  pattern=/UNRESOLVED/  "
            "expect-fail=match  ran=TRACE#1",
            verdict="PASS",
            artifacts=[("verify-note.md", h, str(note.stat().st_size))],
            trace=[f"WROTE  verify-note.md  sha256:{h}"],
            skill="quality-gate/9-fix-verifier")
        sentinel = object()
        saved = getattr(signal, "setitimer", sentinel)
        del signal.setitimer
        self.addCleanup(lambda: saved is not sentinel
                        and setattr(signal, "setitimer", saved))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = self.rv._verify_single(text, "tier2", self.root, True)
        self.assertEqual(rc, 1)
        self.assertIn("matches body of verify-note.md", err.getvalue())


if __name__ == "__main__":
    unittest.main()
