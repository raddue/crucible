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

def _run_advise(skill, files, *, env, cwd=None):
    return subprocess.run(
        [sys.executable, SCRIPT, "advise", skill, *files],
        capture_output=True, text=True, env=env, cwd=cwd, timeout=30,
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


if __name__ == "__main__":
    unittest.main()
