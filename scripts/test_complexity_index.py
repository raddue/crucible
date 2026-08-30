#!/usr/bin/env python3
"""Unit tests for scripts/complexity_index.py (#558).

McCabe cyclomatic-complexity scorer, diff-scoping, and CLI for the
complexity-ranked dispatch signal. Pure stdlib `unittest`, direct-import
(repo root on sys.path), tmp-dir fixtures only — no machine state touched.
The real-corpus calibration test reads this worktree's scripts/*.py
read-only.

Run:  python3 scripts/test_complexity_index.py
"""
import ast
import glob
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import complexity_index as ci  # noqa: E402

SCRIPT = os.path.join(HERE, "complexity_index.py")


def _func_node(src):
    return ast.parse(textwrap.dedent(src)).body[0]


def _branchy(name, n_ifs, indent=""):
    lines = [f"{indent}def {name}(a):", f"{indent}    x = a"]
    for i in range(n_ifs):
        lines.append(f"{indent}    if x != {i}:")
        lines.append(f"{indent}        x += {i + 1}")
    lines.append(f"{indent}    return x")
    return "\n".join(lines)


def _cc49(name, total_lines):
    lines = [f"def {name}(x):", "    acc = x"]
    for i in range(48):
        lines.append(f"    if acc != {i}:")
        lines.append(f"        acc += {i + 1}")
    lines.extend(f"    # pad {j}" for j in range(total_lines - len(lines) - 1))
    lines.append("    return acc")
    return "\n".join(lines)


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _complex_module():
    return (
        _branchy("hot_path", 18)
        + "\n\n\n"
        + _branchy("cold_path", 16)
        + "\n\n\n"
        + "def tiny(a):\n    return a\n"
    )


def _git_env():
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="CI Test", GIT_AUTHOR_EMAIL="ci@example.invalid",
        GIT_COMMITTER_NAME="CI Test", GIT_COMMITTER_EMAIL="ci@example.invalid",
    )
    for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env.pop(key, None)
    return env


def _init_repo(root):
    subprocess.run(["git", "init", "-q", root], check=True,
                   capture_output=True, env=_git_env(), timeout=30)
    return root


def _run_cli(args, cwd):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


class CountingRulesTest(unittest.TestCase):
    # contract:cc:inv-t1
    def test_counting_rules(self):
        """contract:cc:inv-t1 — one synthetic fixture per pinned counting rule."""
        cc = ci.cyclomatic_complexity

        self.assertEqual(cc(_func_node("""
            def f():
                return 1
        """)), 1, "base complexity is 1")

        self.assertEqual(cc(_func_node("""
            def f(x):
                if x == 1:
                    return 1
                elif x == 2:
                    return 2
                elif x == 3:
                    return 3
                else:
                    return 4
        """)), 4, "if/elif/elif/else chain: +1 per If, bare else +0")

        self.assertEqual(cc(_func_node("""
            def f(xs):
                for x in xs:
                    pass
                else:
                    pass
                return 0
        """)), 2, "for/else: loop +1, loop-else +0")

        self.assertEqual(cc(_func_node("""
            def f(x):
                while x:
                    x -= 1
                else:
                    pass
                return x
        """)), 2, "while/else: loop +1, loop-else +0")

        self.assertEqual(cc(_func_node("""
            async def f(ait):
                async for x in ait:
                    pass
                return 0
        """)), 2, "async for counts like for")

        self.assertEqual(cc(_func_node("""
            def f(x):
                try:
                    return int(x)
                except ValueError:
                    return 1
                except TypeError:
                    return 2
                except KeyError:
                    return 3
                finally:
                    pass
        """)), 4, "try with 3 except handlers +3; finally +0")

        self.assertEqual(cc(_func_node("""
            def f(x):
                assert x > 0
                return x
        """)), 2, "assert +1")

        self.assertEqual(cc(_func_node("""
            def f(x):
                return 1 if x else 2
        """)), 2, "IfExp +1")

        self.assertEqual(cc(_func_node("""
            def f(a, b, c):
                return a and b and c
        """)), 3, "3-value BoolOp contributes len(values)-1 == 2")

        self.assertEqual(cc(_func_node("""
            def f(xs):
                return [x for x in xs if x > 0 if x < 10]
        """)), 3, "comprehension with 2 filter clauses +2")

        self.assertEqual(cc(_func_node("""
            def f(cmd):
                match cmd:
                    case "start":
                        return 1
                    case "stop":
                        return 2
                    case _:
                        return 0
        """)), 3, "match: 2 concrete cases +2; bare unguarded case _ +0")


class TopFunctionsTest(unittest.TestCase):
    # contract:floor:inv-t2
    def test_floor_excludes_below_min_complexity(self):
        """contract:floor:inv-t2 — functions on both sides of MIN_COMPLEXITY."""
        self.assertEqual(ci.MIN_COMPLEXITY, 15)
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), "\n\n\n".join([
                _branchy("below_floor", 13),
                _branchy("at_floor", 14),
                _branchy("above_floor", 16),
            ]) + "\n")
            entries = ci.top_functions(["mod.py"], root, limit=0)
            self.assertEqual(
                [(e["qualname"], e["complexity"]) for e in entries],
                [("above_floor", 17), ("at_floor", 15)],
            )
            for e in entries:
                self.assertEqual(
                    set(e.keys()), {"path", "qualname", "complexity", "lines"})
                self.assertEqual(e["path"], "mod.py")

    # contract:paths:inv-t4
    def test_repo_root_is_the_only_path_resolution_basis(self):
        """contract:paths:inv-t4 — fixture tree under repo_root A, cwd is B."""
        with tempfile.TemporaryDirectory() as dir_a, \
                tempfile.TemporaryDirectory() as dir_b:
            _write(os.path.join(dir_a, "mod.py"), _branchy("hot", 18) + "\n")
            prev = os.getcwd()
            try:
                os.chdir(dir_b)
                entries = ci.top_functions(["mod.py"], repo_root=dir_a, limit=0)
            finally:
                os.chdir(prev)
            self.assertEqual(
                [(e["path"], e["qualname"], e["complexity"]) for e in entries],
                [("mod.py", "hot", 19)],
            )

    # contract:order:inv-t5
    def test_tie_break_order(self):
        """contract:order:inv-t5 — complexity desc, lines desc, path asc, qualname asc."""
        with tempfile.TemporaryDirectory() as root:
            src = "\n\n\n".join([
                "def short_fn(a):\n"
                "    if a:\n"
                "        a += 1\n"
                "    if a > 1:\n"
                "        a += 2\n"
                "    return a",
                "def long_fn(a):\n"
                "    if a:\n"
                "        a += 1\n"
                + "".join(f"    # pad {i}\n" for i in range(10)) +
                "    if a > 1:\n"
                "        a += 2\n"
                "    return a",
            ]) + "\n"
            _write(os.path.join(root, "mod.py"), src)
            entries = ci.top_functions(["mod.py"], root, limit=0,
                                       min_complexity=1)
            self.assertEqual(
                [(e["qualname"], e["complexity"], e["lines"]) for e in entries],
                [("long_fn", 3, 16), ("short_fn", 3, 6)],
                "equal CC ranks the longer function first",
            )

        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"),
                   _cc49("tier2_witness", 378) + "\n\n\n"
                   + _cc49("lint_receipt", 142) + "\n")
            entries = ci.top_functions(["mod.py"], root, limit=0)
            self.assertEqual(
                [(e["qualname"], e["complexity"], e["lines"]) for e in entries],
                [("tier2_witness", 49, 378), ("lint_receipt", 49, 142)],
                "worked example: equal CC 49, longer body first — an "
                "alphabetical-only tie-break would invert them (l < t)",
            )

        with tempfile.TemporaryDirectory() as root:
            twin = ("def alpha(a):\n"
                    "    if a:\n"
                    "        a += 1\n"
                    "    return a\n")
            twin_b = twin.replace("alpha", "beta")
            _write(os.path.join(root, "a.py"), twin + "\n" + twin_b)
            _write(os.path.join(root, "b.py"), twin + "\n" + twin_b)
            entries = ci.top_functions(["a.py", "b.py"], root, limit=0,
                                       min_complexity=1)
            self.assertEqual(
                [(e["path"], e["qualname"]) for e in entries],
                [("a.py", "alpha"), ("a.py", "beta"),
                 ("b.py", "alpha"), ("b.py", "beta")],
                "full tie: path asc, then qualname asc",
            )

    # contract:nesting:inv-t6
    def test_nested_functions_scored_independently(self):
        """contract:nesting:inv-t6 — outer excludes inner's branches; inner
        surfaces as outer.inner; Class.method and def-in-if found too."""
        nested_src = textwrap.dedent("""
            def outer(a):
                if a:
                    a += 1

                def inner(b):
                    if b == 1:
                        return 1
                    if b == 2:
                        return 2
                    if b == 3:
                        return 3
                    if b == 4:
                        return 4
                    if b == 5:
                        return 5
                    return 0

                if a > 1:
                    a += 2
                return inner(a)
        """)
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), nested_src)
            entries = ci.top_functions(["mod.py"], root, limit=0,
                                       min_complexity=1)
            self.assertEqual(
                {e["qualname"]: e["complexity"] for e in entries},
                {"outer": 3, "outer.inner": 6},
            )

            outer_alone_src = textwrap.dedent("""
                def outer(a):
                    if a:
                        a += 1
                    if a > 1:
                        a += 2
                    return a
            """)
            _write(os.path.join(root, "alone.py"), outer_alone_src)
            alone = ci.top_functions(["alone.py"], root, limit=0,
                                     min_complexity=1)
            self.assertEqual(alone[0]["complexity"], 3)
            self.assertEqual(
                ci.cyclomatic_complexity(
                    ast.parse(nested_src).body[0]),
                alone[0]["complexity"],
                "INV-C2 witness: outer scores identically with/without the "
                "nested function present",
            )

        with tempfile.TemporaryDirectory() as root:
            class_src = textwrap.dedent("""
                class Widget:
                    def render(self, x):
                        if x == 1:
                            return "one"
                        if x == 2:
                            return "two"
                        if x == 3:
                            return "three"
                        return "many"

                    def save(self, y):
                        if y:
                            return True
                        return False
            """)
            _write(os.path.join(root, "cls.py"), class_src)
            entries = ci.top_functions(["cls.py"], root, limit=0,
                                       min_complexity=1)
            self.assertEqual(
                {e["qualname"]: e["complexity"] for e in entries},
                {"Widget.render": 4, "Widget.save": 2},
            )

        with tempfile.TemporaryDirectory() as root:
            lexical_src = textwrap.dedent("""
                FLAG = True
                if FLAG:
                    def shim(z):
                        if z:
                            z += 1
                        if z > 1:
                            z += 2
                        return z


                def carrier(n):
                    if n:
                        def hidden(m):
                            if m:
                                return 1
                            return 0
                        return hidden(n)
                    return 0
            """)
            _write(os.path.join(root, "lex.py"), lexical_src)
            entries = ci.top_functions(["lex.py"], root, limit=0,
                                       min_complexity=1)
            self.assertEqual(
                {e["qualname"]: e["complexity"] for e in entries},
                {"shim": 3, "carrier": 2, "carrier.hidden": 2},
                "a def inside an if block is still found; qualname reflects "
                "its lexical parent",
            )

    # contract:qualname:inv-t3
    def test_multi_file_multi_class_batch(self):
        """contract:qualname:inv-t3 — Class.method entries scored
        independently; limit=0 full-file batch surfaces every file with >=1
        function clearing the floor; diff-scoped files with no changed hunks
        contribute nothing."""
        one_src = ("class Alpha:\n"
                   + _branchy("m1", 16, indent="    ") + "\n\n"
                   + _branchy("m2", 17, indent="    ") + "\n")
        two_src = ("class Beta:\n"
                   + _branchy("m3", 18, indent="    ") + "\n\n\n"
                   + _branchy("top_fn", 15) + "\n")
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "one.py"), one_src)
            _write(os.path.join(root, "two.py"), two_src)
            entries = ci.top_functions(["one.py", "two.py"], root, limit=0)
            self.assertEqual(
                {e["qualname"]: e["complexity"] for e in entries},
                {"Alpha.m1": 17, "Alpha.m2": 18,
                 "Beta.m3": 19, "top_fn": 16},
            )
            self.assertEqual({e["path"] for e in entries}, {"one.py", "two.py"},
                             "every file with a floor-clearing function "
                             "contributes in the full-file case")

            m3_node = [n for n in ast.parse(two_src).body
                       if isinstance(n, ast.ClassDef)][0].body[0]
            changed = {"two.py": {m3_node.lineno + 1}}
            entries = ci.top_functions(["one.py", "two.py"], root, limit=0,
                                       changed_lines=changed)
            self.assertEqual(
                [(e["path"], e["qualname"]) for e in entries],
                [("two.py", "Beta.m3")],
                "file with no changed hunk contributes nothing when "
                "changed_lines is supplied",
            )

    # contract:diffscope:inv-t7
    def test_diff_scoping_and_hunk_parsing(self):
        """contract:diffscope:inv-t7 — changed_lines intersection, additive
        None behavior, and parse_diff_hunks pinned header/filename shapes."""
        src = _branchy("big_a", 16) + "\n\n\n" + _branchy("big_b", 17) + "\n"
        other_src = _branchy("big_c", 18) + "\n"
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "mod.py"), src)
            _write(os.path.join(root, "other.py"), other_src)
            tree = ast.parse(src)
            ranges = {n.name: (n.lineno, n.end_lineno)
                      for n in tree.body if isinstance(n, ast.FunctionDef)}

            changed = {"mod.py": {ranges["big_a"][0] + 1}}
            entries = ci.top_functions(["mod.py", "other.py"], root, limit=0,
                                       changed_lines=changed)
            self.assertEqual(
                [(e["path"], e["qualname"]) for e in entries],
                [("mod.py", "big_a")],
                "only the intersecting function surfaces",
            )

            entries = ci.top_functions(["mod.py", "other.py"], root, limit=0,
                                       changed_lines={"mod.py": set(),
                                                      "other.py": {1}})
            self.assertEqual(
                [(e["path"], e["qualname"]) for e in entries],
                [("other.py", "big_c")],
                "file mapped to an empty set contributes nothing",
            )

            entries = ci.top_functions(["mod.py", "other.py"], root, limit=0,
                                       changed_lines=None)
            self.assertEqual(
                {e["qualname"] for e in entries},
                {"big_a", "big_b", "big_c"},
                "changed_lines=None keeps full-file behavior (additive "
                "parameter regression guard)",
            )

        diff = (
            "diff --git a/mod.py b/mod.py\n"
            "--- a/mod.py\n"
            "+++ b/mod.py\n"
            "@@ -10,0 +11,2 @@\n"
            "+added one\n"
            "+added two\n"
            "@@ -2 +2 @@\n"
            "+replaced single line\n"
            "@@ -5,3 +5,0 @@\n"
            "-gone one\n"
            "-gone two\n"
            "-gone three\n"
            "diff --git a/path with space.py b/path with space.py\n"
            "--- a/path with space.py\n"
            "+++ b/path with space.py\t\n"
            "@@ -1 +1 @@\n"
            "+changed\n"
            "diff --git a/dead.py b/dead.py\n"
            "--- a/dead.py\n"
            "+++ /dev/null\n"
            "@@ -3 +2,2 @@\n"
            "+must not land anywhere\n"
            "+nor this\n"
            "diff --git a/after.py b/after.py\n"
            "--- a/after.py\n"
            "+++ b/after.py\n"
            "@@ -7,0 +8,3 @@\n"
            "+x\n"
            "+y\n"
            "+z\n"
        )
        hunks = ci.parse_diff_hunks(diff)
        self.assertEqual(set(hunks), {"mod.py", "path with space.py",
                                      "after.py"})
        self.assertEqual(hunks["mod.py"], {11, 12, 2},
                         "two hunks merged; omitted new-count defaults to 1, "
                         "NOT 0; deletion-only hunk contributes nothing")
        self.assertEqual(hunks["path with space.py"], {1},
                         "trailing TAB consumed outside the capture group")
        self.assertFalse(any("\t" in k for k in hunks))
        self.assertEqual(hunks["after.py"], {8, 9, 10},
                         "a later matching +++ line restores attribution "
                         "after a /dev/null reset")

        gone = ci.parse_diff_hunks(
            "--- a/gone.py\n+++ b/gone.py\n@@ -2 +1,0 @@\n-removed\n")
        self.assertIn("gone.py", gone)
        self.assertEqual(gone["gone.py"], set(),
                         "deletion-only hunk yields an empty range")

    # contract:calibration:inv-t9
    def test_fire_rate_below_saturation_on_real_corpus(self):
        """contract:calibration:inv-t9 — <=50% of this worktree's
        scripts/*.py register >=1 hit in the full-file configuration."""
        paths = sorted(
            os.path.relpath(p, REPO_ROOT)
            for p in glob.glob(os.path.join(REPO_ROOT, "scripts", "*.py"))
        )
        self.assertGreaterEqual(len(paths), 10)
        entries = ci.top_functions(paths, REPO_ROOT, limit=0,
                                   changed_lines=None)
        for e in entries:
            self.assertIn("scripts/", e["path"])
        hit_files = {e["path"] for e in entries}
        fraction = len(hit_files) / len(paths)
        self.assertLessEqual(
            fraction, 0.50,
            f"floor-15 fire rate {len(hit_files)}/{len(paths)} = "
            f"{fraction:.2f} saturates the signal",
        )

    # contract:isolation:inv-t10
    def test_per_file_error_isolation(self):
        """contract:isolation:inv-t10 — bad files placed BEFORE the good
        files still yield hits for every good file; a one-outer-try
        implementation loses every good file after the first bad one."""
        with tempfile.TemporaryDirectory() as root:
            _write(os.path.join(root, "good_a.py"), _branchy("fn_a", 16) + "\n")
            _write(os.path.join(root, "good_b.py"), _branchy("fn_b", 17) + "\n")
            _write(os.path.join(root, "broken.py"), "def broken(:\n")
            entries = ci.top_functions(
                ["broken.py", "good_a.py", "missing.py", "good_b.py"],
                root, limit=0)
            self.assertEqual(
                {(e["path"], e["qualname"], e["complexity"]) for e in entries},
                {("good_a.py", "fn_a", 17), ("good_b.py", "fn_b", 18)},
            )


class CliTest(unittest.TestCase):
    def test_cli_score_orders_and_floors(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            r = _run_cli(["score", "mod.py"], cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertIn("cold_path", r.stdout)
            self.assertNotIn("tiny", r.stdout)
            self.assertLess(r.stdout.index("hot_path"),
                            r.stdout.index("cold_path"))
            self.assertIn("mod.py::hot_path (CC 19, 39 lines)", r.stdout)
            self.assertIn("mod.py::cold_path (CC 17, 35 lines)", r.stdout)

    def test_cli_limit_and_min_complexity(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            r = _run_cli(["score", "mod.py", "--limit", "1"], cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertNotIn("cold_path", r.stdout)
            r = _run_cli(["score", "mod.py", "--min-complexity", "18"],
                         cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertNotIn("cold_path", r.stdout)
            r = _run_cli(["score", "mod.py", "--min-complexity", "1"],
                         cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("tiny", r.stdout)

    def test_cli_score_diff_scopes_to_hunk(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True,
                           capture_output=True, env=_git_env(), timeout=30)
            subprocess.run(["git", "-C", repo, "commit", "-qm",
                            "chore: baseline"], check=True,
                           capture_output=True, env=_git_env(), timeout=30)
            with open(os.path.join(repo, "mod.py"), encoding="utf-8") as fh:
                text = fh.read()
            _write(os.path.join(repo, "mod.py"),
                   text.replace("    x = a", "    x = a + 1", 1))
            diff = subprocess.run(["git", "-C", repo, "diff", "-U0"],
                                  check=True, capture_output=True, text=True,
                                  env=_git_env(), timeout=30).stdout
            diff_path = os.path.join(root, "fixture.diff")
            _write(diff_path, diff)
            r = _run_cli(["score", "mod.py", "--diff", diff_path], cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertNotIn("cold_path", r.stdout)

    # contract:diffscope:inv-t8
    def test_cli_selftest(self):
        """contract:diffscope:inv-t8 — --selftest CLI exits 0; per the build
        dispatch this tag rides the selftest CLI here (its substantive
        _complexity_hits key-normalization fixture belongs to the
        brier_advisory wiring task)."""
        r = _run_cli(["--selftest"], cwd=REPO_ROOT)
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        self.assertIn("OK", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
