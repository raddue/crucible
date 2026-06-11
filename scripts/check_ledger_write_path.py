#!/usr/bin/env python3
"""Regression guard: no scripts/ module may build an in-repo `.crucible/` path (#396).

Invocation (from repo root):
    python3 scripts/check_ledger_write_path.py            # check the tracked tree
    python3 scripts/check_ledger_write_path.py --selftest # run the built-in logic tests

Why this exists
---------------
The calibration ledger and grudge store are machine-local central stores
(`default_ledger_dir()` / `default_grudge_dir()` → ~/.claude/crucible/...,
override via CRUCIBLE_LEDGER_DIR). crucible is a PUBLIC repo and entries carry
private file paths plus verbatim finding quotes, so a writer aimed at the
in-repo `.crucible/` tree both (a) becomes a dead store no reader consumes and
(b) leaks finding data into version control. backfill-ledger.py shipped with
exactly that bug (#396); this guard catches its reintroduction.

What it flags
-------------
This is an AST-based string-literal detector. It parses each scripts/ source and
flags any string CONSTANT whose value is a path-shaped string containing
`.crucible` as a path segment (matches `^[\\w./~+-]*\\.crucible[\\w./~+-]*$` — path
chars only, no spaces/backticks). Because every realistic way of assembling the
in-repo path carries a `.crucible` literal SOMEWHERE in the source —
`os.path.join(..., ".crucible", ...)`, `Path(root) / ".crucible"`,
`root + "/.crucible/ledger"`, a variable `seg = ".crucible"`, an f-string
`f"{root}/.crucible/ledger/runs.jsonl"` (ast exposes the `/.crucible/...`
constant inside the JoinedStr), or a multi-line join — all are caught regardless
of the surrounding call syntax.

What it does NOT flag, and why:
  - Prose. A docstring like ``Reads `.crucible/ledger/runs.jsonl`, groups...`` is
    ONE string constant whose value has spaces + backticks → not path-shaped.
    Comments are not in the AST at all → never reachable.
  - The central store. `os.path.join("~/.claude", "crucible", "ledger")` uses the
    segment `"crucible"` (no leading dot) and `".claude"`; neither value contains
    `.crucible`, and the path-only regex does not match `.claude`.

Residual gap (honest)
---------------------
The detector covers every spelling that puts a `.crucible` STRING LITERAL in the
source. The one residual gap is a path assembled with NO `.crucible` literal
anywhere — e.g. `"." + "crucible"` concatenated at runtime. That is absurdly
contrived and is not claimed to be caught. Also out of scope by design: a
`bytes` literal (`b".crucible"`) — the detector only inspects `str` constants —
and any non-`.py` writer (e.g. a shell script) under `scripts/`, since the scan
is `.py`-only.

Scope is `scripts/` only, deliberately: privacy-isolation tests elsewhere (e.g.
eval/grudge/test-grudge-privacy-isolation.py) construct the in-repo path on
purpose to assert writers AVOID it.

Pure stdlib. No third-party deps.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

# A string value is the in-repo write path iff it is path-shaped (only path
# characters — no spaces, no backticks) AND contains `.crucible` as a segment.
# This matches `.crucible`, `/.crucible/ledger`, `.crucible/ledger/runs.jsonl`,
# but NOT prose (spaces/backticks) and NOT `.claude` (no `.crucible` substring).
_PATH_CRUCIBLE = re.compile(r"^[\w./~+-]*\.crucible[\w./~+-]*$")


def scan_source(text: str) -> list:
    """Return sorted 1-based line numbers in `text` that build an in-repo `.crucible` path.

    `text` is a whole-module source string. It is parsed with `ast`; every
    string constant whose value is a path-shaped `.crucible` segment is flagged
    at its node `lineno`. Raises SyntaxError if `text` does not parse.
    """
    tree = ast.parse(text)
    hits = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _PATH_CRUCIBLE.match(node.value):
                hits.add(node.lineno)
    return sorted(hits)


def check_tree() -> int:
    """Recursively scan every scripts/**/*.py for the in-repo `.crucible/` anti-pattern."""
    # Skip this guard itself by ABSOLUTE path: its _selftest() fixtures embed the
    # anti-pattern as test data, and a check script is never a ledger/grudge
    # writer. Absolute-path compare so a same-named file in a subdir is not
    # skipped by basename.
    self_path = os.path.abspath(__file__)
    violations = []
    for dirpath, dirnames, filenames in os.walk(SCRIPTS_DIR):
        # Prune __pycache__ and any dot-directories in place.
        dirnames[:] = [
            d for d in dirnames if d != "__pycache__" and not d.startswith(".")
        ]
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == self_path:
                continue
            rel = os.path.relpath(path, REPO_ROOT)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                print(f"[check_ledger_write_path] could not read {rel}: {e}", file=sys.stderr)
                return 2
            try:
                linenos = scan_source(text)
            except SyntaxError as e:
                print(
                    f"[check_ledger_write_path] could not parse {rel}: {e}; "
                    "a syntax-broken scripts/ file cannot be scanned for the "
                    "`.crucible/` leak — fix the syntax error.",
                    file=sys.stderr,
                )
                return 2
            for lineno in linenos:
                violations.append((rel, lineno))

    if violations:
        print(
            "FAIL: scripts/ module(s) build an in-repo `.crucible/` path — the "
            "ledger/grudge stores are machine-local (~/.claude/crucible) and this "
            "repo is public. Route through default_ledger_dir()/default_grudge_dir().",
            file=sys.stderr,
        )
        for rel, lineno in violations:
            print(f"  {rel}:{lineno}", file=sys.stderr)
        return 1

    print("OK: no scripts/ module builds an in-repo `.crucible/` path")
    return 0


def _selftest() -> int:
    """Built-in logic tests — no filesystem, no tree dependency.

    Inputs are whole-module source snippets (parsed with AST), and assertions
    check the flagged 1-based line numbers.
    """
    # --- Positives: every realistic reintroduction shape must be caught. ---

    # The exact #396 bug shape (single-line os.path.join).
    bad = 'LEDGER_PATH = os.path.join(REPO_ROOT, ".crucible", "ledger", "runs.jsonl")'
    assert scan_source(bad) == [1], "must flag the in-repo .crucible join"

    # Grudge variant.
    bad_grudge = 'd = os.path.join(repo_root, ".crucible", "grudge")'
    assert scan_source(bad_grudge) == [1], "must flag the in-repo .crucible/grudge join"

    # pathlib operand.
    pathlib_src = 'p = Path(REPO_ROOT) / ".crucible" / "ledger"'
    assert scan_source(pathlib_src) == [1], "must flag a pathlib .crucible operand"

    # String concat.
    concat_src = 'p = REPO_ROOT + "/.crucible/ledger"'
    assert scan_source(concat_src) == [1], "must flag a string-concat .crucible path"

    # Variable-held segment.
    varseg_src = 'seg = ".crucible"\np = os.path.join(REPO_ROOT, seg, "ledger")'
    assert scan_source(varseg_src) == [1], "must flag a variable-held .crucible segment"

    # f-string: ast exposes the `/.crucible/ledger/...` constant inside JoinedStr.
    fstr_src = 'f = open(f"{REPO_ROOT}/.crucible/ledger/runs.jsonl", "a")'
    assert scan_source(fstr_src) == [1], "must flag the .crucible literal inside an f-string"

    # Multi-line os.path.join — the node lineno is the call's first line.
    multiline_src = (
        "p = os.path.join(\n"
        '    REPO_ROOT, ".crucible", "ledger",\n'
        ")\n"
    )
    assert scan_source(multiline_src) == [2], "must flag the .crucible literal in a multi-line join"

    # os.sep.join with a list of segments.
    sepjoin_src = 'p = os.sep.join([REPO_ROOT, ".crucible", "x"])'
    assert scan_source(sepjoin_src) == [1], "must flag an os.sep.join .crucible segment"

    # A `+` after the `.crucible` segment: suffix char-class includes `+`, so the
    # whole literal stays path-shaped and is flagged.
    plus_suffix_src = 'p = "/.crucible/ledger+x"'
    assert scan_source(plus_suffix_src) == [1], "must flag a .crucible path with a `+` in the suffix"

    # --- Negatives: legitimate / prose must NOT be flagged. ---

    # The legitimate central store (no leading dot on `crucible`; `.claude` only).
    good = 'os.path.join(os.path.expanduser("~"), ".claude", "crucible", "ledger")'
    assert scan_source(good) == [], "must NOT flag the ~/.claude/crucible central store"

    # A bare `.claude` path literal must not match the path-only regex.
    claude_path = 'p = "~/.claude/crucible/ledger/runs.jsonl"'
    assert scan_source(claude_path) == [], "must NOT flag a .claude path literal"

    # The fixed backfill line.
    fixed = 'LEDGER_PATH = os.path.join(default_ledger_dir(), "runs.jsonl")'
    assert scan_source(fixed) == [], "must NOT flag the default_ledger_dir() derivation"

    # Prose docstring mentioning the path (spaces + backticks -> not path-shaped):
    # this is render_ledger.py:4 / the SP-3 trap.
    docstr_mod = '"""Reads `.crucible/ledger/runs.jsonl`, groups entries by ISO week."""\n'
    assert scan_source(docstr_mod) == [], "must NOT flag a prose docstring mentioning .crucible/"

    # Prose comment mentioning the path (comments are not in the AST at all):
    # this is brier_advisory.py:42.
    comment_mod = 'x = 1  # writes to, NOT the cwd-relative .crucible/ledger/ the design text\n'
    assert scan_source(comment_mod) == [], "must NOT flag a comment mentioning .crucible/"

    print("selftest OK")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    return check_tree()


if __name__ == "__main__":
    sys.exit(main())
