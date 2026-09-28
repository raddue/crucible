#!/usr/bin/env python3
"""Tests for scripts/vuln_ruleset.py — the zero-token multi-language
vulnerability pattern matcher (#629).

The matcher is pure, LLM-free, stdlib-only: it maps a source file's language
from its extension, runs the curated per-language regex rules from
`scripts/vuln_rules.json` line by line, and reports line-level hits. This
suite pins:
  - the ruleset file's integrity (parse, unique ids, compilable patterns);
  - per-language matching (a hit fires on the right language only);
  - line-level hit reporting (the acceptance-criteria "line-level hits");
  - the runnable CLI surface (acceptance "runnable matcher").

stdlib unittest, run via `python3 scripts/test_vuln_ruleset.py` and wired into
scripts/run_tests.sh — matching the repo's existing script-test conventions.
"""
import importlib.util
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import vuln_ruleset  # noqa: E402

RULES_FILE = os.path.join(HERE, "vuln_rules.json")


class RulesetIntegrityTest(unittest.TestCase):
    """The ruleset file itself must stay well-formed, unique, and runnable."""

    def setUp(self):
        with open(RULES_FILE, encoding="utf-8") as fh:
            self.ruleset = json.load(fh)

    def test_ruleset_has_multiple_languages(self):
        langs = self.ruleset.get("languages", {})
        self.assertGreaterEqual(len(langs), 3,
                                "acceptance: rules across multiple languages")

    def test_every_language_defines_extensions_and_rules(self):
        for lang, conf in self.ruleset["languages"].items():
            self.assertTrue(conf.get("ext"), f"{lang}: non-empty ext list")
            self.assertTrue(conf.get("rules"), f"{lang}: non-empty rules list")

    def test_every_rule_has_required_fields_and_unique_id(self):
        seen = set()
        for lang, conf in self.ruleset["languages"].items():
            for rule in conf["rules"]:
                for key in ("id", "category", "severity", "pattern", "message"):
                    self.assertIn(key, rule, f"{lang}/{rule} missing {key!r}")
                self.assertNotIn(rule["id"], seen, f"duplicate rule id {rule['id']}")
                seen.add(rule["id"])

    def test_every_pattern_compiles(self):
        for lang, conf in self.ruleset["languages"].items():
            for rule in conf["rules"]:
                re.compile(rule["pattern"])  # raises re.error if invalid

    def test_ruleset_loads_via_matcher(self):
        rules = vuln_ruleset.load_rules(RULES_FILE)
        self.assertTrue(rules)


class MatchLanguageTest(unittest.TestCase):
    """Per-language matching: a rule for lang X must not fire on lang Y."""

    def test_python_sql_injection_fstring(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
        hits = vuln_ruleset.match_language(code, "python", RULES_FILE)
        self.assertTrue(any(h.rule.id == "py-sqli-execute" for h in hits))

    def test_javascript_xss_innerhtml(self):
        code = "document.getElementById('x').innerHTML = userInput;"
        hits = vuln_ruleset.match_language(code, "javascript", RULES_FILE)
        self.assertTrue(any(h.rule.id == "js-xss-innerhtml" for h in hits))

    def test_go_sql_concat_fmt_sprintf(self):
        code = 'rows, err := db.Query(fmt.Sprintf("SELECT * FROM u WHERE id=%s", id))'
        hits = vuln_ruleset.match_language(code, "go", RULES_FILE)
        self.assertTrue(any(h.rule.id == "go-sqli-sprintf" for h in hits))

    def test_java_command_injection_getruntime(self):
        code = 'Process p = Runtime.getRuntime().exec(cmd);'
        hits = vuln_ruleset.match_language(code, "java", RULES_FILE)
        self.assertTrue(any(h.rule.id == "java-cmd-exec" for h in hits))

    def test_php_sql_injection_superglobal(self):
        code = 'mysqli_query($conn, "SELECT 1 WHERE a=" . $_GET["id"]);'
        hits = vuln_ruleset.match_language(code, "php", RULES_FILE)
        self.assertTrue(any(h.rule.id == "php-sqli-superglobal" for h in hits))

    def test_python_rule_does_not_fire_on_javascript(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
        hits = vuln_ruleset.match_language(code, "javascript", RULES_FILE)
        self.assertFalse(any(h.rule.id == "py-sqli-execute" for h in hits))


class LineLevelHitsTest(unittest.TestCase):
    """Acceptance: matcher produces line-level hits, correctly attributed."""

    def _lines(self, code):
        return code.splitlines()

    def test_hit_reports_correct_line_number(self):
        code = '(\n  "safe",\n  cursor.execute(f"SELECT * FROM u WHERE id={x}"),\n)\n'
        hits = vuln_ruleset.match_language(code, "python", RULES_FILE)
        sqli = [h for h in hits if h.rule.id == "py-sqli-execute"]
        self.assertEqual(len(sqli), 1)
        self.assertEqual(sqli[0].line, 3)


class ConfLanguageTest(unittest.TestCase):
    def test_infer_language_by_extension(self):
        self.assertEqual(vuln_ruleset.infer_language("app.py"), "python")
        self.assertEqual(vuln_ruleset.infer_language("app.ts"), "javascript")
        self.assertEqual(vuln_ruleset.infer_language("api.go"), "go")
        self.assertEqual(vuln_ruleset.infer_language("noext"), None)

    def test_match_language_unknown_returns_empty(self):
        self.assertEqual(vuln_ruleset.match_language("x", "unknown", RULES_FILE), [])


class CliTest(unittest.TestCase):
    """Acceptance: a runnable matcher producing line-level hits via CLI."""

    def test_cli_single_file_reports_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "demo.py"
            p.write_text('x = 1\ncursor.execute(f"SELECT * FROM t WHERE a={a}")\n',
                         encoding="utf-8")
            out = io.StringIO()
            rc = vuln_ruleset.cli([str(p)], out=out)
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("demo.py:2", text)
            self.assertIn("py-sqli-execute", text)

    def test_cli_clean_file_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "clean.py"
            p.write_text('x = 1\nprint("ok")\n', encoding="utf-8")
            out = io.StringIO()
            rc = vuln_ruleset.cli([str(p)], out=out)
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue(), "")

    def test_cli_directory_recurses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "a.py").write_text('cursor.execute(f"SELECT * FROM t")\n',
                                       encoding="utf-8")
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.go").write_text('db.Query(fmt.Sprintf("SELECT * FROM t"))\n',
                                      encoding="utf-8")
            (sub / "c.py").write_text('print("clean")\n', encoding="utf-8")
            out = io.StringIO()
            rc = vuln_ruleset.cli([str(root)], out=out)
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("a.py:1", text)
            self.assertIn("b.go:1", text)
            self.assertNotIn("c.py", text)

    def test_cli_missing_file_errors(self):
        out = io.StringIO()
        rc = vuln_ruleset.cli(["/no/such/file.py"], out=out)
        self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()