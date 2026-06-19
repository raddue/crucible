"""Focused unit tests for loc.count_non_test_source_loc.

The acceptance suite already pins the fixture counts (loc_sample=5, bloated >
minimal, test files excluded); these cover the line-classification edge cases
the design calls out as load-bearing for the headline metric.
"""
from __future__ import annotations

import loc


def _count(tmp_path, files):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return loc.count_non_test_source_loc(tmp_path)


def test_string_literal_that_looks_like_comment_counts(tmp_path):
    # A "#"-prefixed line inside a string literal is a real source line.
    body = 's = "# not a comment"\n'
    assert _count(tmp_path, {"a.py": body}) == 1


def test_inline_trailing_comment_counts(tmp_path):
    body = "x = 1  # trailing comment\n"
    assert _count(tmp_path, {"a.py": body}) == 1


def test_blank_and_comment_only_lines_excluded(tmp_path):
    body = "\n# comment only\n   \n    # indented comment\nx = 1\n"
    assert _count(tmp_path, {"a.py": body}) == 1


def test_empty_dir_is_zero(tmp_path):
    assert loc.count_non_test_source_loc(tmp_path) == 0


def test_multiple_source_files_sum(tmp_path):
    files = {"a.py": "x = 1\ny = 2\n", "b.py": "z = 3\n"}
    assert _count(tmp_path, files) == 3


def test_underscore_test_suffix_excluded(tmp_path):
    files = {"solution.py": "x = 1\n", "solution_test.py": "y = 2\nz = 3\n"}
    assert _count(tmp_path, files) == 1
