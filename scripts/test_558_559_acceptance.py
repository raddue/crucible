#!/usr/bin/env python3
"""Acceptance tests for #558 + #559 (RED wrapper, written BEFORE the feature).

Coarse, feature-level end-to-end tests for:
  #558 — complexity-ranked dispatch signal: `scripts/complexity_index.py`
         (McCabe CC, diff-scoping) wired as the 4th advisory signal inside
         `scripts/brier_advisory.py advise ... --diff`.
  #559 — grudge write-discipline Stop hook `hooks/grudge-resolution-guard.sh`
         backed by `scripts/grudge_query.py --by-commit` / `--by-files`.

These are acceptance tests, NOT unit tests: the contract's 27 tagged
invariants (contract:*:inv-tN) get fine-grained unit tests during
implementation. Every test here drives the real scripts/hook through
subprocesses against tmp git repos and tmp stores — the machine's real state
is never touched (HOME / CRUCIBLE_GRUDGE_DIR / CRUCIBLE_LEDGER_DIR are all
redirected into tmp dirs). Wired into scripts/run_tests.sh (#579), so a later
regression in the feature it pins is caught by the gating suite.

Pure stdlib `unittest`:  python3 scripts/test_558_559_acceptance.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

COMPLEXITY_SCRIPT = os.path.join(REPO_ROOT, "scripts", "complexity_index.py")
BRIER_SCRIPT = os.path.join(REPO_ROOT, "scripts", "brier_advisory.py")
GRUDGE_APPEND = os.path.join(REPO_ROOT, "scripts", "grudge_append.py")
HOOK = os.path.join(REPO_ROOT, "hooks", "grudge-resolution-guard.sh")

SESSION_START_TS = "2026-01-01T00:00:00.000Z"


def _clean_env(**extra):
    env = dict(os.environ)
    for key in ("CRUCIBLE_CALIBRATION_DISABLED",
                "CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD",
                "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env.pop(key, None)
    # The developer's own git config is not part of the fixture. `_git` runs
    # with check=True and the hook shells out to git too, so an ambient
    # `commit.gpgsign = true` (or `color.ui`, `diff.external`, `core.hooksPath`,
    # a commit template…) turned this gating suite red for reasons unrelated to
    # #558/#559 — 10 of 11 tests errored. Neutralising both config layers closes
    # the class; `hooks/tests/test-grudge-resolution-guard.sh` does the narrower
    # per-repo `git config commit.gpgsign false`. Callers may still override.
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.update(extra)
    return env


def _git(repo, *args):
    env = _clean_env(
        GIT_AUTHOR_NAME="Acceptance Test", GIT_AUTHOR_EMAIL="acc@example.invalid",
        GIT_COMMITTER_NAME="Acceptance Test", GIT_COMMITTER_EMAIL="acc@example.invalid",
    )
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True,
        env=env, timeout=30,
    )


def _git_sha(repo, rev="HEAD"):
    return _git(repo, "rev-parse", rev).stdout.strip()


def _init_repo(root, name="repo"):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Acceptance Test")
    _git(repo, "config", "user.email", "acc@example.invalid")
    return repo


def _branchy(name, n_ifs):
    lines = [f"def {name}(a):", "    x = a"]
    for i in range(n_ifs):
        lines.append(f"    if x != {i}:")
        lines.append(f"        x += {i + 1}")
    lines.append("    return x")
    return "\n".join(lines)


def _complex_module(hot_ifs=18, cold_ifs=16):
    return (
        _branchy("hot_path", hot_ifs)
        + "\n\n\n"
        + _branchy("cold_path", cold_ifs)
        + "\n\n\n"
        + "def tiny(a):\n    return a\n"
    )


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _edit_first_line_inside_hot(repo, mod_rel="mod.py"):
    path = os.path.join(repo, mod_rel)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "    x = a\n" in text
    _write(path, text.replace("    x = a", "    x = a + 1", 1))


def _capture_u0_diff(repo, out_path):
    diff = _git(repo, "diff", "-U0").stdout
    assert diff.strip(), "fixture edit produced an empty diff"
    _write(out_path, diff)
    return out_path


class ComplexityScoreCliTest(unittest.TestCase):
    """#558 — end-to-end `complexity_index.py score` CLI behavior."""

    def test_score_ranks_complex_functions_above_floor_in_cc_desc_order(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            r = subprocess.run(
                [sys.executable, COMPLEXITY_SCRIPT, "score", "mod.py"],
                cwd=repo, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertIn("cold_path", r.stdout)
            self.assertNotIn("tiny", r.stdout)
            self.assertLess(
                r.stdout.index("hot_path"), r.stdout.index("cold_path"),
                "higher-CC function must sort first",
            )

    def test_score_diff_surfaces_only_function_intersecting_the_hunk(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: baseline")
            _edit_first_line_inside_hot(repo)
            diff_path = _capture_u0_diff(repo, os.path.join(root, "fixture.diff"))
            r = subprocess.run(
                [sys.executable, COMPLEXITY_SCRIPT, "score", "mod.py",
                 "--diff", diff_path],
                cwd=repo, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("hot_path", r.stdout)
            self.assertNotIn("cold_path", r.stdout)


class AdviseDiffSignalTest(unittest.TestCase):
    """#558 — the 4th signal reaches the rendered advice end-to-end."""

    def test_advise_diff_surfaces_only_intersecting_complexity_line(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as ledger_dir, \
                tempfile.TemporaryDirectory() as grudge_dir:
            repo = _init_repo(root)
            _write(os.path.join(repo, "mod.py"), _complex_module())
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: baseline")
            _edit_first_line_inside_hot(repo)
            diff_path = _capture_u0_diff(repo, os.path.join(root, "fixture.diff"))
            env = _clean_env(
                HOME=os.path.join(root, "home"),
                CRUCIBLE_LEDGER_DIR=ledger_dir,
                CRUCIBLE_GRUDGE_DIR=grudge_dir,
            )
            os.makedirs(env["HOME"], exist_ok=True)
            r = subprocess.run(
                [sys.executable, BRIER_SCRIPT, "advise", "inquisitor",
                 "--diff", diff_path, "mod.py"],
                cwd=repo, capture_output=True, text=True, env=env, timeout=60,
            )
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            self.assertIn("calibration-weighted dispatch", r.stdout)
            self.assertIn("high complexity", r.stdout)
            self.assertIn("mod.py::hot_path", r.stdout)
            self.assertNotIn("cold_path", r.stdout)


def _stop_payload(session_id, transcript_path, repo, stop_hook_active=False):
    return json.dumps({
        "session_id": session_id,
        "transcript_path": transcript_path,
        "cwd": repo,
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
    })


def _hook_env(home, store, **extra):
    env = _clean_env(HOME=home, CRUCIBLE_GRUDGE_DIR=store,
                     CLAUDE_PROJECT_DIR=REPO_ROOT)
    env.update(extra)
    return env


def _run_hook(repo, payload, env):
    return subprocess.run(
        ["bash", HOOK], input=payload, capture_output=True, text=True,
        cwd=repo, env=env, timeout=60,
    )


class _HookFixture:
    def __init__(self, root, create_store=True):
        self.home = os.path.join(root, "home")
        self.store = os.path.join(root, "store")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.store, exist_ok=True)
        self.repo = _init_repo(root)
        self.repo_key = os.path.basename(os.path.realpath(self.repo))
        self.transcript = os.path.join(root, "transcript.jsonl")
        _write(self.transcript,
               json.dumps({"type": "user", "timestamp": SESSION_START_TS}) + "\n"
               + json.dumps({"type": "assistant",
                             "timestamp": "2026-01-01T00:00:05.000Z"}) + "\n")
        _write(os.path.join(self.repo, "app.py"), "VALUE = 0\n")
        _write(os.path.join(self.repo, "notes.md"), "# notes\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "chore: baseline")
        _write(os.path.join(self.repo, "notes.md"), "# notes\n\nmore prose\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "fix(docs): expand notes")
        self.docs_sha = _git_sha(self.repo)
        _write(os.path.join(self.repo, "app.py"), "VALUE = 1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "fix(widget): repair the widget")
        self.fix_sha = _git_sha(self.repo)
        if create_store:
            os.makedirs(os.path.join(self.store, self.repo_key, "grudges"),
                        exist_ok=True)

    def payload(self, session_id, stop_hook_active=False):
        return _stop_payload(session_id, self.transcript, self.repo,
                             stop_hook_active)

    def env(self, **extra):
        return _hook_env(self.home, self.store, **extra)

    def run(self, payload, env=None):
        return _run_hook(self.repo, payload, env or self.env())


class StopHookBlockTest(unittest.TestCase):
    """#559 — an in-session fix(*) commit with no grudge blocks the Stop."""

    def test_stop_hook_blocks_unresolved_fix_commit(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            r = fx.run(fx.payload("sess-block"))
            self.assertEqual(
                r.returncode, 2,
                f"stdout={r.stdout!r} stderr={r.stderr!r}",
            )
            self.assertIn(fx.fix_sha[:7], r.stderr)
            self.assertIn("(1/3)", r.stderr)
            self.assertNotIn(fx.docs_sha[:7], r.stderr)


class StopHookClearanceTest(unittest.TestCase):
    """#559 — hook -> grudge_query.py --by-commit -> store seam."""

    def test_stop_hook_allows_after_matching_grudge_record(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            env = fx.env()
            r = subprocess.run(
                [sys.executable, GRUDGE_APPEND,
                 "--symptom", "widget exploded on launch",
                 "--files", "app.py",
                 "--commit", fx.fix_sha,
                 "--repo-root", os.path.realpath(fx.repo),
                 "--repo", fx.repo_key],
                capture_output=True, text=True, env=env, cwd=root, timeout=60,
            )
            self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
            r2 = fx.run(fx.payload("sess-cleared"))
            self.assertEqual(
                r2.returncode, 0,
                f"stdout={r2.stdout!r} stderr={r2.stderr!r}",
            )

    def test_stop_hook_skip_entry_clears_shared_file_group(self):
        """One skip entry naming a member of a shared-file group clears the
        WHOLE group (both members) at the next Stop. The base fixture's
        inherited fix(widget) commit (app.py, a disjoint one-member group) is
        pre-neutralized with a matching grudge so the only unresolved
        candidates at this scenario's Stops are the shared.py group members.
        """
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            env = fx.env()
            r0 = subprocess.run(
                [sys.executable, GRUDGE_APPEND,
                 "--symptom", "widget exploded on launch",
                 "--files", "app.py",
                 "--commit", fx.fix_sha,
                 "--repo-root", os.path.realpath(fx.repo),
                 "--repo", fx.repo_key],
                capture_output=True, text=True, env=env, cwd=root, timeout=60,
            )
            self.assertEqual(r0.returncode, 0, f"stderr: {r0.stderr}")
            _write(os.path.join(fx.repo, "shared.py"), "S = 0\n")
            _git(fx.repo, "add", "-A")
            _git(fx.repo, "commit", "-qm", "chore: add shared")
            _write(os.path.join(fx.repo, "shared.py"), "S = 1\n")
            _git(fx.repo, "add", "-A")
            _git(fx.repo, "commit", "-qm", "fix(shared): part one")
            sha_a = _git_sha(fx.repo)
            _write(os.path.join(fx.repo, "shared.py"), "S = 2\n")
            _git(fx.repo, "add", "-A")
            _git(fx.repo, "commit", "-qm", "fix(shared): part two")
            r1 = fx.run(fx.payload("sess-group"))
            self.assertEqual(r1.returncode, 2, f"stderr={r1.stderr!r}")
            m = re.search(r"(/[^\s\"']*grudge-guard/skips\.log)", r1.stderr)
            self.assertIsNotNone(
                m, f"block message must carry the skips.log path: {r1.stderr!r}")
            skips_path = m.group(1)
            os.makedirs(os.path.dirname(skips_path), exist_ok=True)
            with open(skips_path, "a", encoding="utf-8") as fh:
                fh.write(f"{sha_a} intentional acceptance-test fixture\n")
            r2 = fx.run(fx.payload("sess-group", stop_hook_active=True))
            self.assertEqual(
                r2.returncode, 0,
                f"one skip for a same-group member must clear the whole group: "
                f"stdout={r2.stdout!r} stderr={r2.stderr!r}",
            )


class StopHookBoundedBlockingTest(unittest.TestCase):
    """#559 — MAX_BLOCKS=3 safety valve: blocks 1-3, gives up on the 4th."""

    def test_stop_hook_gives_up_after_three_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            rcs, stderrs = [], []
            for i in range(4):
                r = fx.run(fx.payload("sess-bound", stop_hook_active=(i > 0)))
                rcs.append(r.returncode)
                stderrs.append(r.stderr)
            self.assertEqual(
                rcs, [2, 2, 2, 0],
                f"stderrs={stderrs!r}",
            )
            self.assertIn("(1/3)", stderrs[0])
            self.assertIn("(2/3)", stderrs[1])
            self.assertIn("(3/3)", stderrs[2])
            self.assertIn("giving up", stderrs[3])


class StopHookDegradationTest(unittest.TestCase):
    """#559 — never block on infra failure: allow (exit 0) instead."""

    def test_allows_when_no_grudge_store_exists(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root, create_store=False)
            r = fx.run(fx.payload("sess-nostore"))
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")
            self.assertIn("no grudge store", r.stderr.lower())

    def test_allows_when_killswitch_set(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            env = fx.env(CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD="1")
            r = fx.run(fx.payload("sess-kill"), env)
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")
            self.assertIn("disabled", r.stderr.lower())

    def test_allows_on_malformed_payload(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            r = fx.run("{ this is not json")
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")

    def test_allows_when_jq_is_missing(self):
        with tempfile.TemporaryDirectory() as root:
            fx = _HookFixture(root)
            nojq = os.path.join(root, "nojq-bin")
            os.makedirs(nojq)
            for cmd in ("bash", "sh", "cat", "grep", "sed", "awk", "cut",
                        "date", "head", "tail", "sort", "tr", "uniq", "mkdir",
                        "touch", "rm", "mv", "cp", "ls", "ln", "dirname",
                        "basename", "realpath", "readlink", "pwd", "env",
                        "git", "python3", "python", "wc", "mktemp", "stat",
                        "find", "xargs", "tee", "chmod", "sleep", "uname"):
                src = shutil.which(cmd)
                if src:
                    os.symlink(src, os.path.join(nojq, cmd))
            env = fx.env(PATH=nojq)
            r = fx.run(fx.payload("sess-nojq"), env)
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")


class GitEnvIsolationTest(unittest.TestCase):
    """The suite's own git calls must not read the developer's git config.

    `_git` runs with `check=True`, so any ambient global/system setting that
    makes a fixture command fail turns the whole suite red for a reason that has
    nothing to do with #558/#559: `commit.gpgsign = true` with no usable key
    errored 10 of the 11 tests here. This suite is gating (#579), so that is a
    gating failure. Asserted behaviourally — stage a hostile global config, then
    drive the suite's own helpers through it — rather than by inspecting the env
    dict, so it stays true of whatever mechanism provides the isolation.
    """

    def test_fixture_git_survives_a_hostile_global_gitconfig(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = os.path.join(root, "hostile.gitconfig")
            _write(cfg, "[commit]\n\tgpgsign = true\n"
                        "[gpg]\n\tprogram = /bin/false\n"
                        "[color]\n\tui = always\n")
            saved = os.environ.get("GIT_CONFIG_GLOBAL")
            os.environ["GIT_CONFIG_GLOBAL"] = cfg
            try:
                repo = _init_repo(root, name="hostile-repo")
                _write(os.path.join(repo, "f.py"), "V = 0\n")
                _git(repo, "add", "-A")
                _git(repo, "commit", "-qm", "chore: baseline")
                self.assertRegex(_git_sha(repo), r"^[0-9a-f]{40}$")
            finally:
                if saved is None:
                    os.environ.pop("GIT_CONFIG_GLOBAL", None)
                else:
                    os.environ["GIT_CONFIG_GLOBAL"] = saved


# Executed-test-count guard (#579) — mirrors the pin in
# scripts/test_complexity_index.py. `unittest` exits 0 on a suite whose tests
# were dropped, renamed or skipped, so a return code alone cannot distinguish
# "every acceptance test passed" from "every acceptance test vanished". Assert
# how many tests actually EXECUTED: collected, minus skips, minus
# expected-failures/unexpected-successes (all three keep a test in testsRun
# while neutering its assertions). Bump this when adding a test.
EXPECTED_TESTS = 12


def _run_with_count_guard():
    """Run the suite; fail loudly if fewer than EXPECTED_TESTS actually ran."""
    result = unittest.main(exit=False, verbosity=2).result
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
        print(f"ERROR: expected {EXPECTED_TESTS} acceptance tests to execute, "
              f"ran {executed} ({result.testsRun} collected, {len(inert)} "
              f"skipped/expected-failed) — a test was skipped, dropped or "
              f"renamed", file=sys.stderr)
        for case, reason in inert:
            print(f"  did not execute: {case} ({reason})", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())
