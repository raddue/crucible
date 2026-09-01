#!/usr/bin/env python3
"""Central-store path resolution + `emit` CLI — restored from
eval/calibration-ledger/test-central-store.py (moved to raddue/crucible-eval
with the rest of that eval harness, #460). Five functions exercise ONLY the
surviving scripts/ledger_append.py module (default_ledger_dir/path, the
`emit` CLI's subprocess behavior, CRUCIBLE_LEDGER_DIR handling, and mixed
v1/v2 append + dedup); the original file's fifth function
(test_mixed_v1_v2_read_dedup_render) had a sixth, render-dependent assertion
(`per_repo` bucketing via the now-deleted render_ledger) that was dropped with
it — its other four assertions (INV-8, writer-side) are restored below as
MixedSchemaTest.

Invokes `emit` via subprocess (unlike scripts/test_ledger_core.py, which is
pure stdlib / no subprocess) — kept in its own file for that reason.

Covers (design §Invariants / contract, #270):
  INV-1 default_ledger_dir() returns a ~-rooted path (never inside the cwd
        tree) when CRUCIBLE_LEDGER_DIR is unset.
  INV-5 `emit` succeeds from a cwd != the script's repo (the core bug).
  INV-6 `emit -` writes to the central default; CRUCIBLE_LEDGER_DIR overrides.
  INV-7 repo auto-populates to the git-toplevel basename inside a git repo;
        cwd basename when not in a git repo; never raises; an explicit
        repo:null is overwritten, not preserved.
  INV-8 mixed v1 (no `repo`, schema_version 1) + v2 rows append and dedup
        without error (writer-side only; the render/`per_repo` half of this
        invariant lived in render_ledger, moved to raddue/crucible-eval, #460).
  INV-9 graceful skip: kill-switch and duplicate `emit` both no-op with exit 0.

Pure stdlib `unittest`. Never touches the real ~/.claude or the in-repo
.crucible/ledger/runs.jsonl — every case writes to a tmp dir.
"""
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

from scripts.ledger_append import (  # noqa: E402
    append, caller_dedup, default_ledger_dir, default_ledger_path, default_repo)

SCRIPT = os.path.join(REPO_ROOT, "scripts", "ledger_append.py")


def _emit(ledger_arg, entry, *, cwd, extra_env=None):
    """Invoke the `emit` CLI by ABSOLUTE script path from `cwd`. The
    absolute-path invocation is the whole point of INV-5: no PYTHONPATH, no
    cwd dependency."""
    env = dict(os.environ)
    env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    env.pop("CRUCIBLE_LEDGER_DIR", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, SCRIPT, "emit", ledger_arg, json.dumps(entry)],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _v2(run_id, skill, repo=None):
    e = {
        "schema_version": 2, "run_id": run_id, "skill": skill, "tier": "A",
        "artifact_type": "code", "verdict": "PASS", "confidence": 0.5,
        "would_have_shipped_without_gate": False, "rounds": 1,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
    }
    if repo is not None:
        e["repo"] = repo
    return e


def _v1(run_id, skill):
    """A legacy v1 row: schema_version 1, NO repo key at all."""
    return {
        "schema_version": 1, "run_id": run_id, "skill": skill, "tier": "A",
        "artifact_type": "code", "verdict": "PASS", "confidence": 0.5,
        "would_have_shipped_without_gate": False, "rounds": 1,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
    }


# --------------------------------------------------------------------------- #
# INV-1 — central default is ~-rooted, never inside the cwd tree              #
# --------------------------------------------------------------------------- #

class DefaultLedgerPathTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("CRUCIBLE_LEDGER_DIR", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["CRUCIBLE_LEDGER_DIR"] = self._saved

    def test_default_dir_is_home_rooted(self):
        d = default_ledger_dir()
        home = os.path.expanduser("~")
        self.assertTrue(d.startswith(home), d)

    def test_default_path_ends_runs_jsonl(self):
        self.assertTrue(
            default_ledger_path().endswith(os.path.join("runs.jsonl")))

    def test_default_dir_not_the_cwd_tree(self):
        self.assertFalse(default_ledger_dir().startswith(os.getcwd()))


# --------------------------------------------------------------------------- #
# INV-5 / INV-6 — emit from a foreign cwd, central default + env override     #
# --------------------------------------------------------------------------- #

class EmitCwdIndependenceTest(unittest.TestCase):
    def test_emit_from_foreign_cwd_lands_in_central_dir(self):
        with tempfile.TemporaryDirectory(prefix="cs-foreign-") as foreign, \
             tempfile.TemporaryDirectory(prefix="cs-central-") as central:
            central_dir = os.path.join(central, "ledger")
            proc = _emit("-", _v2("uuid-1", "siege", repo="x"),
                         cwd=foreign,
                         extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
            self.assertEqual(proc.returncode, 0, proc.stderr)     # INV-5
            rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
            self.assertEqual(len(rows), 1)                        # INV-6
            self.assertEqual(rows[0].get("run_id"), "uuid-1")


# --------------------------------------------------------------------------- #
# INV-7 — repo auto-population (git basename / cwd fallback / never raises)   #
# --------------------------------------------------------------------------- #

class RepoAutoPopulationTest(unittest.TestCase):
    def test_default_repo_never_raises_on_nonexistent_path(self):
        default_repo("/nonexistent/path/should/not/exist")   # must not raise

    def test_non_git_dir_falls_back_to_cwd_basename(self):
        with tempfile.TemporaryDirectory(prefix="cs-nogit-") as nogit:
            sub = os.path.join(nogit, "myproj")
            os.makedirs(sub)
            self.assertEqual(default_repo(sub), "myproj")

    def test_git_repo_resolves_toplevel_basename_from_subdir(self):
        with tempfile.TemporaryDirectory(prefix="cs-git-") as gitparent:
            repo_dir = os.path.join(gitparent, "repo-alpha")
            os.makedirs(os.path.join(repo_dir, "src"))
            try:
                subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True,
                               capture_output=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                self.skipTest("git unavailable")
            got = default_repo(os.path.join(repo_dir, "src"))
            self.assertEqual(got, "repo-alpha")

    def test_emit_autostamps_git_toplevel_not_cwd_subdir(self):
        # Emit from a SUBDIR of the git repo so the git-toplevel basename
        # ("repo-beta") genuinely differs from the cwd basename ("sub") — this
        # exercises which branch fires.
        with tempfile.TemporaryDirectory(prefix="cs-emit-git-") as gp:
            repo_dir = os.path.join(gp, "repo-beta")
            sub_dir = os.path.join(repo_dir, "sub")
            os.makedirs(sub_dir)
            central_dir = os.path.join(gp, "central")
            try:
                subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True,
                               capture_output=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                self.skipTest("git unavailable")
            proc = _emit("-", _v2("uuid-2", "audit"),  # no repo key
                         cwd=sub_dir,
                         extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
            rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("repo"), "repo-beta")

    def test_emit_overwrites_explicit_repo_null(self):
        # The Significant finding this guards: setdefault would have left an
        # explicit repo:null alone instead of auto-filling it.
        with tempfile.TemporaryDirectory(prefix="cs-emit-null-") as gp:
            central_dir = os.path.join(gp, "central")
            entry = _v2("uuid-3", "siege")
            entry["repo"] = None
            proc = _emit("-", entry, cwd=gp,
                         extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
            rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(rows), 1)
            self.assertNotIn(rows[0].get("repo"), (None, ""))


# --------------------------------------------------------------------------- #
# INV-8 — mixed v1/v2 append + dedup (writer-side; render half moved, #460)   #
# --------------------------------------------------------------------------- #

class MixedSchemaTest(unittest.TestCase):
    def setUp(self):
        # append() is a no-op under the kill-switch; pop it for these
        # happy-path cases (mirrors _emit()'s env.pop above).
        self._saved = os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)

    def tearDown(self):
        os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        if self._saved is not None:
            os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = self._saved

    def test_v1_and_v2_rows_append_and_dedup(self):
        with tempfile.TemporaryDirectory(prefix="cs-mixed-") as tmp:
            ledger = os.path.join(tmp, "runs.jsonl")
            ov = os.path.join(tmp, "overflow")
            self.assertTrue(
                append(ledger, _v1("v1-a", "quality-gate"), overflow_dir=ov))
            self.assertTrue(
                append(ledger, _v2("v2-a", "siege", repo="repo-alpha"),
                       overflow_dir=ov))
            self.assertIs(caller_dedup(ledger, "v1-a", "quality-gate"), True)
            self.assertIs(caller_dedup(ledger, "nope", "siege"), False)


# --------------------------------------------------------------------------- #
# INV-9 — graceful skip: kill-switch and duplicate both exit 0, no write      #
# --------------------------------------------------------------------------- #

class GracefulSkipTest(unittest.TestCase):
    def test_kill_switch_exits_zero_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="cs-skip-") as tmp:
            central_dir = os.path.join(tmp, "ledger")
            proc = _emit("-", _v2("ks-1", "siege", repo="x"), cwd=tmp,
                         extra_env={"CRUCIBLE_LEDGER_DIR": central_dir,
                                    "CRUCIBLE_CALIBRATION_DISABLED": "1"})
            self.assertEqual(proc.returncode, 0)
            rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
            self.assertEqual(rows, [])

    def test_duplicate_emit_exits_zero_and_skips(self):
        with tempfile.TemporaryDirectory(prefix="cs-skip-") as tmp:
            central_dir = os.path.join(tmp, "ledger")
            _emit("-", _v2("dup-1", "siege", repo="x"), cwd=tmp,
                  extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
            proc2 = _emit("-", _v2("dup-1", "siege", repo="x"), cwd=tmp,
                          extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
            rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
            self.assertEqual(proc2.returncode, 0, proc2.stderr)
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
