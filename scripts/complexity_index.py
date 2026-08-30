#!/usr/bin/env python3
"""Complexity index: McCabe cyclomatic-complexity scorer (#558).

Static complexity signal for calibration-weighted dispatch advice: scores
every function in the given files, floors at MIN_COMPLEXITY, optionally
diff-scopes via changed-line sets, and renders a complexity-ranked list.
Stdlib-only by contract (INV-C1); imports limited to ast/argparse/os/re/sys.

Public surface (contract-pinned):
  cyclomatic_complexity(func) -> int
  top_functions(paths, repo_root, limit, min_complexity=MIN_COMPLEXITY,
                changed_lines=None) -> list[dict]
  parse_diff_hunks(diff_text) -> dict[str, set[int]]
"""
import argparse
import ast
import os
import re
import sys

MIN_COMPLEXITY = 15

_EXCLUDED_SUBTREES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
)

_FILE_RE = re.compile(r"^\+\+\+ b/(.+?)\t?$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def cyclomatic_complexity(func):
    """McCabe CC over func.body only (signature/decorator/default excluded).

    Base 1 plus the pinned counting rules: +1 per If (elif desugars to a
    nested If in orelse; bare else +0); +1 per For/AsyncFor/While
    (loop-else +0); +1 per ExceptHandler (finally +0); +1 per Assert;
    +1 per IfExp; len(values)-1 per BoolOp; +1 per comprehension filter;
    +1 per match_case except a bare unguarded wildcard (+0). Bounded
    traversal recurses into every node except nested
    FunctionDef/AsyncFunctionDef/Lambda/ClassDef subtrees (their branches
    belong to their own score — INV-C2).
    """
    total = 1
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _EXCLUDED_SUBTREES):
            continue
        if isinstance(node, ast.If):
            total += 1
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            total += 1
        elif isinstance(node, ast.ExceptHandler):
            total += 1
        elif isinstance(node, ast.Assert):
            total += 1
        elif isinstance(node, ast.IfExp):
            total += 1
        elif isinstance(node, ast.BoolOp):
            total += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            total += len(node.ifs)
        elif isinstance(node, ast.match_case):
            bare_wildcard = (
                isinstance(node.pattern, ast.MatchAs)
                and node.pattern.pattern is None
            )
            if not (bare_wildcard and node.guard is None):
                total += 1
        stack.extend(ast.iter_child_nodes(node))
    return total


def _intersects(path, lineno, end_lineno, changed_lines):
    lines = changed_lines.get(path)
    if not lines:
        return False
    return any(line in lines for line in range(lineno, end_lineno + 1))


def _collect(body, prefix, path, changed_lines, min_complexity, entries):
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = ".".join(prefix + [stmt.name])
            complexity = cyclomatic_complexity(stmt)
            if complexity >= min_complexity:
                if (changed_lines is None
                        or _intersects(path, stmt.lineno, stmt.end_lineno,
                                       changed_lines)):
                    entries.append({
                        "path": path,
                        "qualname": qualname,
                        "complexity": complexity,
                        "lines": stmt.end_lineno - stmt.lineno + 1,
                    })
            _collect(stmt.body, prefix + [stmt.name], path, changed_lines,
                     min_complexity, entries)
        elif isinstance(stmt, ast.ClassDef):
            _collect(stmt.body, prefix + [stmt.name], path, changed_lines,
                     min_complexity, entries)
        else:
            for field, value in ast.iter_fields(stmt):
                if field in ("body", "orelse", "finalbody") and value:
                    _collect(value, prefix, path, changed_lines,
                             min_complexity, entries)
                elif field == "handlers":
                    for handler in value:
                        _collect(handler.body, prefix, path, changed_lines,
                                 min_complexity, entries)
                elif field == "cases":
                    for case in value:
                        _collect(case.body, prefix, path, changed_lines,
                                 min_complexity, entries)


def top_functions(paths, repo_root, limit, min_complexity=MIN_COMPLEXITY,
                  changed_lines=None):
    """Complexity-ranked function entries for the given files.

    repo_root is the only path-resolution basis (never os.getcwd()).
    Excludes entries below min_complexity; sorts by complexity desc,
    line-count desc, path asc, qualname asc; limit=0 means uncapped.
    With changed_lines supplied, only functions whose [lineno, end_lineno]
    range intersects that file's changed-line set surface. Per-file error
    isolation: one unparseable/missing file is swallowed, the rest still
    contribute.
    """
    entries = []
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(repo_root, p)
        try:
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source)
            _collect(tree.body, [], p, changed_lines, min_complexity, entries)
        except Exception:
            continue
    entries.sort(key=lambda e: (-e["complexity"], -e["lines"],
                                e["path"], e["qualname"]))
    if limit and limit > 0:
        entries = entries[:limit]
    return entries


def parse_diff_hunks(diff_text):
    """Unified diff -> {repo-relative path: set of changed new-file lines}.

    Tracks the current filename from `+++ ` lines via the pinned regex
    ^\\+\\+\\+ b/(.+?)\\t?$ (trailing TAB consumed outside the capture
    group); any non-matching `+++` line (e.g. /dev/null, quoted/C-escaped
    paths) resets the current filename to None so following hunks are
    excluded, not mis-attributed. Hunk headers via the pinned regex
    ^@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@: missing count defaults to
    1; new-file range is c..c+count-1; count=0 yields an empty range.
    """
    hunks = {}
    current = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            m = _FILE_RE.match(line)
            current = m.group(1) if m else None
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            lines = hunks.setdefault(current, set())
            lines.update(range(start, start + count))
    return hunks


def _resolve_repo_root():
    out = os.popen("git rev-parse --show-toplevel 2>/dev/null").read().strip()
    return out or os.getcwd()


def _selftest_failures():
    failures = []

    def check(desc, expected, actual):
        if expected != actual:
            failures.append(f"FAIL: {desc}: expected {expected!r}, "
                            f"got {actual!r}")

    def cc(src):
        return cyclomatic_complexity(ast.parse(src).body[0])

    check("base complexity", 1, cc("def f():\n    return 1\n"))
    check("if/elif chain", 4, cc(
        "def f(x):\n"
        "    if x == 1:\n        return 1\n"
        "    elif x == 2:\n        return 2\n"
        "    elif x == 3:\n        return 3\n"
        "    else:\n        return 0\n"))
    check("for loop (+else +0)", 2, cc(
        "def f(xs):\n    for x in xs:\n        pass\n"
        "    else:\n        pass\n    return 0\n"))
    check("async for", 2, cc(
        "async def f(ait):\n    async for x in ait:\n        pass\n"
        "    return 0\n"))
    check("try/except handlers (finally +0)", 4, cc(
        "def f(x):\n    try:\n        return int(x)\n"
        "    except ValueError:\n        return 1\n"
        "    except TypeError:\n        return 2\n"
        "    except KeyError:\n        return 3\n"
        "    finally:\n        pass\n"))
    check("assert", 2, cc("def f(x):\n    assert x\n    return x\n"))
    check("IfExp", 2, cc("def f(x):\n    return 1 if x else 2\n"))
    check("BoolOp len(values)-1", 3, cc(
        "def f(a, b, c):\n    return a and b and c\n"))
    check("comprehension filters", 3, cc(
        "def f(xs):\n    return [x for x in xs if x > 0 if x < 10]\n"))
    check("match cases (bare wildcard +0)", 3, cc(
        'def f(c):\n    match c:\n        case "a":\n            return 1\n'
        '        case "b":\n            return 2\n'
        "        case _:\n            return 0\n"))

    hunks = parse_diff_hunks(
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -2 +2 @@\n"
        "+one line, omitted count defaults to 1\n"
        "@@ -5,3 +5,0 @@\n"
        "-deletion-only hunk yields an empty range\n")
    check("parse_diff_hunks shape", {"mod.py": {2}},
          {k: v for k, v in hunks.items() if v})
    check("parse_diff_hunks deletion-only key", set(),
          hunks.get("mod.py", set()) - {2})

    check("MIN_COMPLEXITY pin", 15, MIN_COMPLEXITY)
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       f".complexity-index-selftest-{os.getpid()}")
    os.makedirs(tmp, exist_ok=True)
    fixture = os.path.join(tmp, "fixture.py")
    try:
        with open(fixture, "w", encoding="utf-8") as fh:
            fh.write("def big(a):\n    x = a\n"
                     + "".join(f"    if x != {i}:\n        x += {i + 1}\n"
                               for i in range(16))
                     + "    return x\n\n"
                       "def small(a):\n    return a\n")
        found = [(e["qualname"], e["complexity"])
                 for e in top_functions(["fixture.py"], tmp, limit=0)]
        check("floor behavior (only >= MIN_COMPLEXITY surfaces)",
              [("big", 17)], found)
    except Exception as exc:
        failures.append(f"FAIL: floor fixture: {exc!r}")
    finally:
        try:
            os.remove(fixture)
        except OSError:
            pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true",
                        help="run in-module smoke assertions and exit 0/1")
    sub = parser.add_subparsers(dest="command")
    p_score = sub.add_parser("score", help="complexity-rank functions in files")
    p_score.add_argument("files", nargs="+", metavar="file",
                         help="repo-relative paths (relative to the git "
                              "toplevel, or cwd outside a git repo)")
    p_score.add_argument("--limit", type=int, default=0,
                         help="cap the number of entries (0 = uncapped)")
    p_score.add_argument("--min-complexity", type=int, default=MIN_COMPLEXITY,
                         help=f"floor (default {MIN_COMPLEXITY})")
    p_score.add_argument("--diff", default=None, metavar="path",
                         help="unified diff file; score only functions "
                              "intersecting its changed hunks")
    args = parser.parse_args(argv)

    if args.selftest:
        failures = _selftest_failures()
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print("OK")
        return 0

    if args.command != "score":
        parser.print_usage(sys.stderr)
        return 2

    changed_lines = None
    if args.diff:
        try:
            with open(args.diff, "r", encoding="utf-8") as fh:
                diff_text = fh.read()
        except OSError as exc:
            print(f"complexity_index: cannot read --diff file: {exc}",
                  file=sys.stderr)
            return 1
        changed_lines = parse_diff_hunks(diff_text)

    repo_root = _resolve_repo_root()
    for entry in top_functions(args.files, repo_root, args.limit,
                               min_complexity=args.min_complexity,
                               changed_lines=changed_lines):
        print(f"{entry['path']}::{entry['qualname']} "
              f"(CC {entry['complexity']}, {entry['lines']} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
