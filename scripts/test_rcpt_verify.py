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
import re
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
        for ef in ("exit=-1", "match"):
            out = self.rv.parse_witness([f"exec:cmd  expect-fail={ef}  ran=2026-06-24"])
            self.assertEqual(out["expect_fail"], ef)


if __name__ == "__main__":
    unittest.main()
