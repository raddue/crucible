#!/usr/bin/env python3
"""Zero-token multi-language vulnerability pattern matcher (#629).

LLM-free, deterministic, stdlib-only. Reads the curated per-language regex
ruleset (`scripts/vuln_rules.json`) and matches source files line by line,
reporting line-level hits. This is the `~0 tokens` baseline catch that runs
before/alongside the LLM passes in siege/red-team — a distinct, reproducible
signal rather than LLM verbatim.

Usage:
    python3 scripts/vuln_ruleset.py [FILE|DIR ...]

Hits are printed as `path:line: [category] rule-id — message`. Directories are
walked recursively. Unknown extensions are skipped (matched per language by a
file's extension via the ruleset `ext` lists). Exit 0 on success, non-zero on
error (missing ruleset, unreadable target).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

_DEFAULT_RULESET = None


def _rules_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "vuln_rules.json")


class Rule:
    """A compiled per-language pattern rule."""

    __slots__ = ("lang", "id", "category", "severity", "pattern", "message", "_re")

    def __init__(self, lang, id_, category, severity, pattern, message):
        self.lang = lang
        self.id = id_
        self.category = category
        self.severity = severity
        self.pattern = pattern
        self.message = message
        self._re = re.compile(pattern)

    def search(self, text):
        return self._re.search(text)


class Hit:
    """A single line-level match."""

    __slots__ = ("path", "line", "rule", "column")

    def __init__(self, path, line, rule, column):
        self.path = path
        self.line = line
        self.rule = rule
        self.column = column

    def render(self):
        return (f"{self.path}:{self.line}: [{self.rule.category}] "
                f"{self.rule.id} — {self.rule.message}")


class Ruleset:
    """Loaded, validated, dexed-by-language ruleset."""

    def __init__(self, rules, ext_index):
        self.rules = rules
        self.ext_index = ext_index  # ext (lowercase, no dot) -> language name

    def language_for(self, path):
        ext = pathlib.Path(path).suffix.lower().lstrip(".")
        return self.ext_index.get(ext)

    def rules_for(self, lang):
        return [r for r in self.rules if r.lang == lang]


def load_rules(rules_file):
    """Load and validate the ruleset JSON into a Ruleset. Raises on bad data."""
    with open(rules_file, encoding="utf-8") as fh:
        data = json.load(fh)
    languages = data.get("languages")
    if not isinstance(languages, dict) or not languages:
        raise ValueError("ruleset missing non-empty 'languages' object")
    rules = []
    ext_index = {}
    seen_ids = set()
    for name, conf in sorted(languages.items()):
        for ext in conf.get("ext", []):
            ext_index[ext.lower().lstrip(".")] = name
        for raw in conf.get("rules", []):
            rule = Rule(
                lang=name,
                id_=raw["id"],
                category=raw["category"],
                severity=raw.get("severity", "medium"),
                pattern=raw["pattern"],
                message=raw["message"],
            )
            if rule.id in seen_ids:
                raise ValueError(f"duplicate rule id {rule.id!r}")
            seen_ids.add(rule.id)
            rules.append(rule)
    return Ruleset(rules, ext_index)


def infer_language(path, ruleset=None):
    """Map a file path to a ruleset language name by extension, or None."""
    if ruleset is None:
        ruleset = default_ruleset()
    return ruleset.language_for(path)


def default_ruleset():
    """Lazily-loaded default Ruleset from the bundled JSON."""
    global _DEFAULT_RULESET
    if _DEFAULT_RULESET is None:
        _DEFAULT_RULESET = load_rules(_rules_path())
    return _DEFAULT_RULESET


def match_language(code, lang, ruleset):
    """Match `code` against all rules for `lang`. Returns list[Hit].

    `ruleset` may be a Ruleset instance or a path to the JSON file (loaded
    on demand). Path is left blank (caller attaches it via scan_file).
    """
    if not isinstance(ruleset, Ruleset):
        ruleset = load_rules(ruleset)
    hits = []
    for rule in ruleset.rules_for(lang):
        for lineno, line in enumerate(code.splitlines(), 1):
            m = rule.search(line)
            if m:
                hits.append(Hit("", lineno, rule, m.start() + 1))
    return hits


def scan_file(path, ruleset):
    """Scan one file; returns list[Hit] with the file path attached."""
    lang = ruleset.language_for(path)
    if lang is None:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            code = fh.read()
    except (OSError, IOError):
        return []
    hits = []
    for rule in ruleset.rules_for(lang):
        for lineno, line in enumerate(code.splitlines(), 1):
            m = rule.search(line)
            if m:
                hits.append(Hit(path, lineno, rule, m.start() + 1))
    return hits


def scan_iter(paths, ruleset):
    """Iterate files/dirs, yielding line-level hits in deterministic order."""
    for target in paths:
        p = pathlib.Path(target)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    yield from scan_file(str(child), ruleset)
        elif p.is_file():
            yield from scan_file(str(p), ruleset)


def cli(argv, out=sys.stdout):
    try:
        ruleset = default_ruleset()
    except (OSError, ValueError) as exc:
        out.write(f"vuln_ruleset: {exc}\n")
        return 1
    if not argv:
        out.write("usage: vuln_ruleset.py [FILE|DIR ...]\n")
        return 2
    for target in argv:
        if not os.path.exists(target):
            out.write(f"vuln_ruleset: no such file or directory: {target}\n")
            return 2
    for hit in scan_iter(argv, ruleset):
        out.write(hit.render() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))