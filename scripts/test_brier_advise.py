#!/usr/bin/env python3
"""Eval harness for the `advise` subcommand on brier_advisory.py (#372).

Covers the calibration-weighted-dispatch DispatchAdvice merge: the three
signals (Brier / grudge / falsification), the bounds, the silence rules, and
the never-raise contract. Pure stdlib `unittest`. In-repo fixtures only — the
machine-local central store is never touched (CRUCIBLE_LEDGER_DIR /
CRUCIBLE_GRUDGE_DIR overrides + a tmp git repo).

Pure-core cases (`_falsification_hits`, `_render_advice`) import directly.
Cases that exercise the grudge path (which flows resolve_repo -> git rev-parse
of the cwd -> survivors() on-disk check) run `advise` as a subprocess with cwd
set to a tmp `git init` repo, per the plan's S-1 fixture recipe.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import brier_advisory as ba  # noqa: E402

SCRIPT = os.path.join(HERE, "brier_advisory.py")


def _entry_hash(run_id, skill):
    import hashlib
    return hashlib.sha256((run_id + ":" + skill).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Pure-core unit tests (no IO)                                                #
# --------------------------------------------------------------------------- #

class FalsificationHitsTest(unittest.TestCase):
    def _runs(self):
        return [
            {"run_id": "r1", "skill": "siege", "gated_files": ["a.py", "b.py"]},
            {"run_id": "r2", "skill": "siege", "gated_files": ["c.py"]},
            {"run_id": "r3", "skill": "siege", "backfilled": True,
             "gated_files": ["a.py"]},   # backfilled -> excluded
            {"run_id": "r4", "skill": "delve", "gated_files": ["a.py"]},  # other skill
            {"run_id": "r5", "skill": "siege"},  # missing gated_files -> skip row
        ]

    def test_hit_requires_falsified_hash_and_file_intersection(self):
        falsified = {_entry_hash("r1", "siege")}
        hits = ba._falsification_hits(self._runs(), falsified, "siege", {"a.py"})
        self.assertEqual(hits, {"a.py": 1})

    def test_non_intersecting_file_no_hit(self):
        falsified = {_entry_hash("r1", "siege")}
        hits = ba._falsification_hits(self._runs(), falsified, "siege", {"zzz.py"})
        self.assertEqual(hits, {})

    def test_backfilled_excluded(self):
        falsified = {_entry_hash("r3", "siege")}
        hits = ba._falsification_hits(self._runs(), falsified, "siege", {"a.py"})
        self.assertEqual(hits, {})

    def test_suite_wide_join_is_skill_scoped_on_hash(self):
        # r4 is delve; querying skill=siege must not hit it (hash includes skill).
        falsified = {_entry_hash("r4", "delve")}
        hits = ba._falsification_hits(self._runs(), falsified, "siege", {"a.py"})
        self.assertEqual(hits, {})

    def test_missing_gated_files_row_skipped_not_fatal(self):
        falsified = {_entry_hash("r5", "siege")}
        # r5 has no gated_files; must not raise, must just contribute nothing.
        hits = ba._falsification_hits(self._runs(), falsified, "siege", {"a.py"})
        self.assertEqual(hits, {})

    def test_count_is_distinct_runs(self):
        falsified = {_entry_hash("r1", "siege"), _entry_hash("r2", "siege")}
        hits = ba._falsification_hits(self._runs(), falsified, "siege",
                                      {"a.py", "c.py"})
        self.assertEqual(hits, {"a.py": 1, "c.py": 1})


class RenderAdviceTest(unittest.TestCase):
    def test_all_silent_is_empty(self):
        self.assertEqual(ba._render_advice("siege", None, {}, {}), "")

    def test_topk_cap_and_overflow(self):
        fals = {f"f{i}.py": 1 for i in range(8)}
        out = ba._render_advice("siege", None, fals, {})
        self.assertIn("calibration-weighted dispatch", out)
        self.assertIn("(+3 more)", out)   # 8 files, cap 5 -> +3
        # never an absolute path
        self.assertNotIn("/tmp", out)

    def test_ranked_hit_count_desc(self):
        fals = {"low.py": 1, "high.py": 9}
        out = ba._render_advice("siege", None, fals, {})
        self.assertLess(out.index("high.py"), out.index("low.py"))

    def test_brier_line_included_when_present(self):
        out = ba._render_advice("siege", "[calibration] Brier 0.40", {}, {"x.py": 1})
        self.assertIn("Brier 0.40", out)
        self.assertIn("x.py", out)


# --------------------------------------------------------------------------- #
# Subprocess / IO tests                                                       #
# --------------------------------------------------------------------------- #

def _run_advise(skill, files, *, env, cwd=None, diff=None):
    cmd = [sys.executable, SCRIPT, "advise", skill]
    if diff is not None:
        cmd.extend(["--diff", diff])
    cmd.extend(files)
    return subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=cwd, timeout=30,
    )


class SilenceTest(unittest.TestCase):
    """Silence/never-raise cases short-circuit before the grudge path, so they
    need only a tmp CRUCIBLE_LEDGER_DIR — no git fixture."""

    def _env(self, ledger_dir, **extra):
        env = dict(os.environ)
        env["CRUCIBLE_LEDGER_DIR"] = ledger_dir
        env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        env.update(extra)
        return env

    def test_killswitch_silent_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            env = self._env(d, CRUCIBLE_CALIBRATION_DISABLED="1")
            r = _run_advise("siege", ["a.py"], env=env)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")

    def test_no_store_silent_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            # empty ledger dir: no brier, no falsification, no grudge match
            env = self._env(d, CRUCIBLE_GRUDGE_DIR=d)
            r = _run_advise("siege", ["a.py"], env=env)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")

    def test_corrupt_runs_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            # falsification.jsonl present (so the falsification path runs) +
            # corrupt runs.jsonl: must degrade to silent, not crash.
            with open(os.path.join(d, "falsification.jsonl"), "w") as f:
                f.write(json.dumps({"ledger_entry_hash": "h", "falsified": True}) + "\n")
            with open(os.path.join(d, "runs.jsonl"), "w") as f:
                f.write("{ this is not json\n")
            env = self._env(d, CRUCIBLE_GRUDGE_DIR=d)
            r = _run_advise("siege", ["a.py"], env=env)
            self.assertEqual(r.returncode, 0)


class GrudgeFixtureTest(unittest.TestCase):
    """Grudge signal end-to-end: git-init repo with real on-disk files +
    CRUCIBLE_GRUDGE_DIR, advise run as a subprocess with cwd in that repo."""

    def _git(self, repo, *args):
        subprocess.run(["git", "-C", repo, *args], check=True,
                       capture_output=True, text=True)

    def test_grudge_hit_fires_for_surviving_file(self):
        with tempfile.TemporaryDirectory() as repo, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            # real on-disk file so survivors() keeps it
            open(os.path.join(repo, "auth.py"), "w").close()
            self._git(repo, "init", "-q")
            repo_real = os.path.realpath(repo)
            repo_base = os.path.basename(repo_real)
            # Grudges live at <base>/<repo-basename>/grudges/<hash>.md and are
            # filtered at read time on realpath(repo_root) equality. The fixture
            # must therefore carry valid `---` frontmatter AND repo_root set to
            # this tmp repo's realpath, or load_grudges() drops it.
            gdir = os.path.join(grudgedir, repo_base, "grudges")
            os.makedirs(gdir, exist_ok=True)
            grudge = (
                "---\n"
                "id: g1\n"
                f"repo_root: {repo_real}\n"
                "files_touched: [\"auth.py\"]\n"
                "symptom: past regression in auth\n"
                "date_fixed: 2026-06-01\n"
                "---\n"
                "Body: do not reintroduce the auth bypass.\n"
            )
            with open(os.path.join(gdir, "g1.md"), "w") as f:
                f.write(grudge)
            env = dict(os.environ)
            env["CRUCIBLE_LEDGER_DIR"] = ledger
            env["CRUCIBLE_GRUDGE_DIR"] = grudgedir
            env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
            r = _run_advise("siege", ["auth.py"], env=env, cwd=repo)
            self.assertEqual(r.returncode, 0)
            # grudge-only (no falsification.jsonl) but the grudge must surface
            self.assertIn("auth.py", r.stdout)


class FalsificationE2ETest(unittest.TestCase):
    """End-to-end falsification join through the CLI: a real falsification.jsonl
    keyed by ledger_entry_hash(run_id, skill) + a runs.jsonl row carrying that
    run must surface the gated file under 'past wrong verdicts touched'. Closes
    the coverage gap between the pure-unit `_falsification_hits` cases and the
    live `dispatch_advice` IO path (reduce() + ledger_entry_hash import)."""

    def _env(self, ledger_dir):
        env = dict(os.environ)
        env["CRUCIBLE_LEDGER_DIR"] = ledger_dir
        # point the grudge store at an empty dir so only falsification can fire
        env["CRUCIBLE_GRUDGE_DIR"] = ledger_dir
        env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        return env

    def _write_store(self, d, *, run_id, skill, gated_files, backfilled=False):
        with open(os.path.join(d, "falsification.jsonl"), "w") as f:
            f.write(json.dumps({
                "ledger_entry_hash": _entry_hash(run_id, skill),
                "falsified": True,
            }) + "\n")
        with open(os.path.join(d, "runs.jsonl"), "w") as f:
            row = {"run_id": run_id, "skill": skill, "gated_files": gated_files}
            if backfilled:
                row["backfilled"] = True
            f.write(json.dumps(row) + "\n")

    def test_falsified_run_surfaces_gated_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_store(d, run_id="run-xyz", skill="siege",
                              gated_files=["a.py"])
            r = _run_advise("siege", ["a.py"], env=self._env(d))
            self.assertEqual(r.returncode, 0)
            self.assertIn("past wrong verdicts touched", r.stdout)
            self.assertIn("a.py", r.stdout)

    def test_backfilled_falsified_run_no_hit(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_store(d, run_id="run-bf", skill="siege",
                              gated_files=["a.py"], backfilled=True)
            r = _run_advise("siege", ["a.py"], env=self._env(d))
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")

    def test_wrong_skill_no_hit(self):
        with tempfile.TemporaryDirectory() as d:
            # falsified run is for delve; querying siege must not hit it
            # (ledger_entry_hash embeds the skill).
            self._write_store(d, run_id="run-delve", skill="delve",
                              gated_files=["a.py"])
            r = _run_advise("siege", ["a.py"], env=self._env(d))
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")


# --------------------------------------------------------------------------- #
# Complexity signal (#558): the 4th dispatch_advice signal                    #
# --------------------------------------------------------------------------- #

def _branchy_fn(name, n_ifs):
    """Module-level function fixture source; CC == 1 + n_ifs."""
    lines = [f"def {name}(a):", "    x = a"]
    for i in range(n_ifs):
        lines.append(f"    if x != {i}:")
        lines.append(f"        x += {i + 1}")
    lines.append("    return x")
    return "\n".join(lines) + "\n"


def _branchy_method(name, n_ifs):
    """Class-method fixture source (one indent level); CC == 1 + n_ifs."""
    lines = [f"    def {name}(self, a):", "        x = a"]
    for i in range(n_ifs):
        lines.append(f"        if x != {i}:")
        lines.append(f"            x += {i + 1}")
    lines.append("        return x")
    return "\n".join(lines) + "\n"


class ComplexityHitsTest(unittest.TestCase):
    """_complexity_hits direct-import cases. The tmp fixture dir becomes the
    repo root: resolve_repo() falls back to the realpath of the cwd outside a
    git repo, so no IO escapes the tmp tree."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(self._tmp.name)
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def _write(self, name, text):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def _fixture_batch(self):
        # file_a.py: module-level alpha (CC 17) + Handler.process (CC 18).
        self._write("file_a.py",
                    _branchy_fn("alpha", 16)
                    + "\n\nclass Handler:\n" + _branchy_method("process", 17))
        # file_b.py: beta (CC 16).
        self._write("file_b.py", _branchy_fn("beta", 15))
        # file_c.py: nothing clears MIN_COMPLEXITY.
        self._write("file_c.py", "def trivial(a):\n    return a\n")

    # contract:qualname:inv-t3
    def test_complexity_hits_groups_by_file(self):
        """contract:qualname:inv-t3 — Multi-file, multi-class batch in the
        full-file case (changed_lines=None): EVERY file with >=1 function
        clearing the floor yields exactly one entry — that file's first
        (highest-CC) function — and Class.method qualnames carry their own
        independent score."""
        self._fixture_batch()
        hits = ba._complexity_hits(["file_a.py", "file_b.py", "file_c.py"])
        self.assertEqual(hits, {
            "file_a.py": ("Handler.process", 18),
            "file_b.py": ("beta", 16),
        })

    def test_complexity_hits_diff_scoped_no_hunks_contribute_nothing(self):
        """Diff-scoped variant: a file with no changed hunks (absent key OR an
        empty line set) contributes nothing even when it carries
        floor-clearing functions."""
        self._fixture_batch()
        hits = ba._complexity_hits(
            ["file_a.py", "file_b.py"], changed_lines={"file_b.py": {2}})
        self.assertEqual(hits, {"file_b.py": ("beta", 16)})
        self.assertEqual(
            ba._complexity_hits(["file_a.py"],
                                changed_lines={"file_a.py": set()}),
            {})

    # contract:diffscope:inv-t8
    def test_complexity_hits_normalizes_changed_lines_keys(self):
        """contract:diffscope:inv-t8 — Un-normalized changed_lines keys
        (./-prefixed AND absolute) still intersect a repo-relative file list,
        and the file list itself is normalized the same way. A
        _complexity_hits that skipped key normalization would score zero
        intersections on this fixture."""
        self._fixture_batch()
        changed = {
            "./file_a.py": {2},
            os.path.join(self.repo, "file_b.py"): {2},
        }
        hits = ba._complexity_hits(["file_a.py", "file_b.py"],
                                   changed_lines=changed)
        self.assertEqual(hits, {
            "file_a.py": ("alpha", 17),
            "file_b.py": ("beta", 16),
        })
        unnormalized_files = ba._complexity_hits(
            ["./file_a.py", os.path.join(self.repo, "file_b.py")])
        self.assertEqual(unnormalized_files, {
            "file_a.py": ("Handler.process", 18),
            "file_b.py": ("beta", 16),
        })


class ComplexityFmtTest(unittest.TestCase):
    """Pure rendering cases for the complexity signal."""

    def test_fmt_complexity_cc_desc_then_file_asc_and_cap(self):
        hits = {f"f{i}.py": (f"fn{i}", 20 + i) for i in range(8)}
        out = ba._fmt_complexity(hits)
        self.assertTrue(out.startswith("f7.py::fn7 (CC 27)"), out)
        self.assertIn("(+3 more)", out)   # 8 hits, cap 5 -> +3
        self.assertNotIn("f2.py", out)    # 6th-highest CC is past the cap
        tie = ba._fmt_complexity({"b.py": ("g", 19), "a.py": ("f", 19)})
        self.assertEqual(tie, "a.py::f (CC 19), b.py::g (CC 19)")

    def test_render_advice_complexity_none_identical_to_empty(self):
        base = ba._render_advice("siege", None, {"x.py": 1}, {})
        self.assertEqual(
            base,
            ba._render_advice("siege", None, {"x.py": 1}, {},
                              complexity_hits=None))
        self.assertEqual(
            base,
            ba._render_advice("siege", None, {"x.py": 1}, {},
                              complexity_hits={}))
        self.assertEqual(
            ba._render_advice("siege", None, {}, {}, complexity_hits=None),
            "")
        self.assertEqual(
            ba._render_advice("siege", None, {}, {}, complexity_hits={}),
            "")

    def test_render_advice_complexity_line_and_footer(self):
        out = ba._render_advice("siege", None, {}, {},
                                complexity_hits={"mod.py": ("hot_path", 19)})
        self.assertIn("- high complexity: mod.py::hot_path (CC 19)", out)
        self.assertIn(
            "- suggested weighting: give the named files/functions extra "
            "reviewer attention this run.", out)


class ComplexitySignalE2ETest(unittest.TestCase):
    """Complexity signal end-to-end through the advise CLI, per the S-1
    recipe: tmp `git init` repo holding a committed two-function fixture
    module (hot_path clears the floor INSIDE the edited hunk, cold_path
    clears it OUTSIDE), `git diff -U0` captured to a fixture file, and empty
    tmp CRUCIBLE_LEDGER_DIR / CRUCIBLE_GRUDGE_DIR so only the complexity
    signal can fire."""

    def _git(self, repo, *args):
        env = dict(os.environ)
        env.update(GIT_AUTHOR_NAME="Advise Test",
                   GIT_AUTHOR_EMAIL="advise@example.invalid",
                   GIT_COMMITTER_NAME="Advise Test",
                   GIT_COMMITTER_EMAIL="advise@example.invalid")
        return subprocess.run(["git", "-C", repo, *args], check=True,
                              capture_output=True, text=True, env=env,
                              timeout=30)

    def _env(self, ledger_dir, grudge_dir, **extra):
        env = dict(os.environ)
        env["CRUCIBLE_LEDGER_DIR"] = ledger_dir
        env["CRUCIBLE_GRUDGE_DIR"] = grudge_dir
        env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        env.update(extra)
        return env

    def _fixture_repo(self, root):
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.name", "Advise Test")
        self._git(repo, "config", "user.email", "advise@example.invalid")
        mod = (_branchy_fn("hot_path", 18)      # CC 19
               + "\n\n\n"
               + _branchy_fn("cold_path", 16)   # CC 17
               + "\n\n\n"
               + "def tiny(a):\n    return a\n")
        with open(os.path.join(repo, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(mod)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "chore: baseline")
        return repo

    def _edit_first_line_inside_hot(self, repo):
        path = os.path.join(repo, "mod.py")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "    x = a\n" in text
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("    x = a", "    x = a + 1", 1))

    # contract:cli:inv-t11
    def test_advise_diff_surfaces_only_intersecting_complexity_line(self):
        """contract:cli:inv-t11 — advise <skill> --diff <fixture> <file>
        end-to-end renders ONLY the file::func complexity line intersecting
        the fixture diff's changed hunk (the F1 regression test: fails
        immediately if --diff is dropped from the advise subparser or
        disconnected from dispatch_advice)."""
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            self._edit_first_line_inside_hot(repo)
            diff = self._git(repo, "diff", "-U0").stdout
            self.assertTrue(diff.strip(), "fixture edit produced an empty diff")
            diff_path = os.path.join(root, "fixture.diff")
            with open(diff_path, "w", encoding="utf-8") as fh:
                fh.write(diff)
            r = _run_advise("inquisitor", ["mod.py"],
                            env=self._env(ledger, grudgedir), cwd=repo,
                            diff=diff_path)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("calibration-weighted dispatch", r.stdout)
            self.assertIn("- high complexity: mod.py::hot_path (CC 19)",
                          r.stdout)
            self.assertNotIn("cold_path", r.stdout)
            self.assertNotIn("tiny", r.stdout)

    def test_silent_when_no_function_clears_floor(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            with open(os.path.join(repo, "trivial.py"), "w",
                      encoding="utf-8") as fh:
                fh.write("def tiny(a):\n    return a\n")
            r = _run_advise("siege", ["trivial.py"],
                            env=self._env(ledger, grudgedir), cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertEqual(r.stdout.strip(), "")

    def test_full_file_high_cc_fires_with_rendering_and_footer(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            r = _run_advise("siege", ["mod.py"],
                            env=self._env(ledger, grudgedir), cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("- high complexity: ", r.stdout)
            # group-by-file keeps only mod.py's FIRST (highest-CC) entry
            self.assertIn("mod.py::hot_path (CC 19)", r.stdout)
            self.assertNotIn("cold_path", r.stdout)
            self.assertIn(
                "- suggested weighting: give the named files/functions extra "
                "reviewer attention this run.", r.stdout)

    def test_killswitch_silences_complexity_signal(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            env = self._env(ledger, grudgedir,
                            CRUCIBLE_CALIBRATION_DISABLED="1")
            r = _run_advise("siege", ["mod.py"], env=env, cwd=repo)
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertEqual(r.stdout.strip(), "")

    def test_missing_diff_file_degrades_to_full_file_exit0(self):
        """An unreadable --diff degrades changed_lines to None (full-file
        across ALL advised files), warns on stderr, and preserves exit 0.
        Discriminating shape: an empty hunks map (or a crash) would hide
        mod2.py entirely, so mod2.py surfacing proves changed_lines degraded
        to None."""
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            with open(os.path.join(repo, "mod2.py"), "w",
                      encoding="utf-8") as fh:
                fh.write(_branchy_fn("warm_path", 15))   # CC 16
            r = _run_advise("siege", ["mod.py", "mod2.py"],
                            env=self._env(ledger, grudgedir), cwd=repo,
                            diff=os.path.join(root, "no-such.diff"))
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("mod.py::hot_path", r.stdout)
            self.assertIn("mod2.py::warm_path", r.stdout)
            self.assertIn("brier_advisory WARN", r.stderr)

    def test_dispatch_advice_changed_lines_none_keeps_full_file(self):
        """dispatch_advice(..., changed_lines=None) renders identically to
        today's call shape (full-file behavior preserved for existing call
        sites)."""
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger, \
                tempfile.TemporaryDirectory() as grudgedir:
            repo = self._fixture_repo(root)
            old_cwd = os.getcwd()
            keys = ("CRUCIBLE_LEDGER_DIR", "CRUCIBLE_GRUDGE_DIR",
                    "CRUCIBLE_CALIBRATION_DISABLED")
            saved = {k: os.environ.get(k) for k in keys}
            try:
                os.chdir(repo)
                os.environ["CRUCIBLE_LEDGER_DIR"] = ledger
                os.environ["CRUCIBLE_GRUDGE_DIR"] = grudgedir
                os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
                baseline = ba.dispatch_advice("siege", ["mod.py"])
                explicit = ba.dispatch_advice("siege", ["mod.py"],
                                              changed_lines=None)
                self.assertEqual(baseline, explicit)
                self.assertIn("mod.py::hot_path (CC 19)", baseline)
                self.assertNotIn("cold_path", baseline)
            finally:
                os.chdir(old_cwd)
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


# Executed-test-count guard — the Python counterpart of the bash carrier's
# EXPECTED_CHECKS pin (hooks/tests/test-grudge-resolution-guard.sh). `unittest`
# exits 0 on a fully skipped suite, so a return code alone cannot distinguish
# "every contract test passed" from "every contract test was skipped, dropped
# or renamed away". Assert how many tests actually EXECUTED: collected, minus
# skips, minus expected-failures/unexpected-successes (all three keep a test in
# testsRun while neutering its assertions). Bump this when adding a test.
EXPECTED_TESTS = 29


def _run_with_count_guard():
    """Run the suite; fail loudly if fewer than EXPECTED_TESTS actually ran."""
    result = unittest.main(exit=False).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        # argv selects a subset (single test, -k, --failfast): the total is not
        # comparable, so report the exemption instead of asserting a wrong count.
        print("NOTE: executed-count guard not applied — argv selects a subset: "
              + " ".join(sys.argv[1:]), file=sys.stderr)
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} contract tests to execute, "
              f"ran {executed} ({result.testsRun} collected, {len(inert)} "
              f"skipped/expected-failed) — a test was skipped, dropped or "
              f"renamed", file=sys.stderr)
        for case, reason in inert:
            print(f"  did not execute: {case} ({reason})", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())
