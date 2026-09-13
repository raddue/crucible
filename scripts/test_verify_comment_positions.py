#!/usr/bin/env python3
"""Tests for scripts/verify_comment_positions.py — the deterministic
comment-position verification step (#628).

Review skills (delve, temper) emit `file:line` refs straight from the LLM with no
check the cited line actually matches the claimed content. This suite pins the
deterministic gate that runs BEFORE a finding reaches the user:

  - every `{file, line}` ref must resolve to an existing line in the tree;
  - if the finding's summary names symbol(s)/snippet(s) that DO occur in the file,
    at least one must occur on the cited line (else position drift is REJECTED);
  - if no named symbol occurs in the file at all (pure-prose comment, or a
    removed-code reference), the ref degrades to provenance-only: VERIFIED if the
    line exists, never a hard reject (a removed-behavior finding legitimately
    names code that no longer exists).

Pure stdlib `unittest`. Never touches a real repo — every case builds a tmp tree."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.verify_comment_positions import extract_symbols  # noqa: E402
from scripts.verify_comment_positions import verify_record  # noqa: E402


def _tree(files: dict) -> str:
    """Build a tmp dir from {relpath: content}; returns the root as str."""
    root = tempfile.mkdtemp(prefix="verify_cp_")
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return root


class ExtractSymbolsTest(unittest.TestCase):
    def test_backtick_span_is_one_symbol(self):
        self.assertEqual(extract_symbols("reader reads `claims.expiresAt` at mid"),
                         ["claims.expiresAt"])

    def test_double_quoted_symbol(self):
        self.assertEqual(extract_symbols('check "revoked" gone'), ["revoked"])

    def test_operators_in_quotes(self):
        self.assertEqual(extract_symbols("boundary uses `<` instead of `<=`"),
                         ["<", "<="])

    def test_plain_identifiers_pulled_too(self):
        self.assertEqual(extract_symbols("reader still reads claims.expiresAt"),
                         ["claims.expiresAt"])

    def test_dotted_identifier_single_token(self):
        self.assertEqual(extract_symbols("mid uses token.exp past expiry"),
                         ["token.exp"])

    def test_apostrophe_does_not_pair_with_backtick(self):
        # regression #633: prose like "token's `expiresAt`" previously let the
        # apostrophe pair as an opening quote and a LATER backtick as its
        # closer, extracting the junk span "s " — "s" appears on nearly every
        # line, so `any(s in cited)` passed and genuine drift was VERIFIED.
        self.assertEqual(extract_symbols("token's `expiresAt` compared with `<`"),
                         ["expiresAt", "<"])


class VerifyRecordPositionsTest(unittest.TestCase):
    FILES = {
        "src/token.ts": "package token\n\n"
                        "export const exp = 60\n"
                        "export function mid() {\n"
                        "  return claims.expiresAt <= now\n"
                        "}\n",
    }

    def _verify(self, record, root=None, window=0):
        return verify_record(record, root or _tree(self.FILES), window=window)

    def test_missing_file_rejected(self):
        status, reason = self._verify(
            {"file": "src/nope.ts", "line": 1, "summary": "x"})
        self.assertEqual(status, "REJECTED")
        self.assertIn("resolve", reason)

    def test_line_beyond_eof_rejected(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": 99, "summary": "x"})
        self.assertEqual(status, "REJECTED")

    def test_malformed_line_rejected(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": "abc", "summary": "x"})
        self.assertEqual(status, "REJECTED")

    def test_symbol_on_cited_line_verified(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": 5,
             "summary": "`claims.expiresAt` compared with `<` where `<=`"})
        self.assertEqual(status, "VERIFIED")

    def test_position_drift_rejected(self):
        # symbol exists in the file but on line 5, NOT on cited line 3.
        status, reason = self._verify(
            {"file": "src/token.ts", "line": 3, "summary": "`expiresAt` here"})
        self.assertEqual(status, "REJECTED")
        self.assertIn("line", reason)

    def test_window_allows_adjacent_symbol(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": 4, "summary": "`expiresAt` bound"},
            window=1)
        self.assertEqual(status, "VERIFIED")

    def test_range_line_verified(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": "5-5", "summary": "`expiresAt` exp"})
        self.assertEqual(status, "VERIFIED")

    def test_range_beyond_eof_rejected(self):
        status, _ = self._verify(
            {"file": "src/token.ts", "line": "5-99", "summary": "x"})
        self.assertEqual(status, "REJECTED")

    def test_removed_code_prose_degrades_to_provenance(self):
        # summary names no code still present in the file → provenance-only PASS.
        status, reason = self._verify(
            {"file": "src/token.ts", "line": 2,
             "summary": "revoked-token check removed before acceptance"})
        self.assertEqual(status, "VERIFIED")
        self.assertIn("provenance", reason)

    def test_existing_line_with_named_symbol_degrade(self):
        # a named symbol appears in the file but the line is prose/blank:
        # that still counts as drift (symbol is somewhere, just not cited).
        status, _ = self._verify(
            {"file": "src/token.ts", "line": 2, "summary": "`expiresAt` here"})
        self.assertEqual(status, "REJECTED")


class CliTest(unittest.TestCase):
    def _run(self, root, records, *args):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f)
        try:
            return subprocess.run(
                [sys.executable,
                 os.path.join(REPO_ROOT, "scripts", "verify_comment_positions.py"),
                 "--root", root, path, *args],
                capture_output=True, text=True)
        finally:
            os.unlink(path)

    def test_exit_zero_all_verified(self):
        root = _tree({"a.py": "# place\nL1\nL2 L3\n"})
        proc = self._run(root, [{"file": "a.py", "line": 3, "summary": "`L2` `L3`"}])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERIFIED", proc.stdout)

    def test_exit_one_on_drift(self):
        root = _tree({"a.py": "# place\nL1\nL2\n"})
        proc = self._run(root, [{"file": "a.py", "line": 1, "summary": "`L2`"}])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("REJECTED", proc.stdout)

    def test_unverifiable_prose_counts_as_pass(self):
        root = _tree({"a.py": "# place\nL1\nL2\n"})
        proc = self._run(root, [{"file": "a.py", "line": 2,
                                 "summary": "remove the whole check"}])
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()