#!/usr/bin/env python3
"""GIT-layer integration tests for reconcile_ledger.py (#439 / #441).

The GIT layer (`discover_candidates`, `_touched_files`, `fix_branch_sizes`) is
the SOLE producer of the falsification input the well-tested pure core consumes
to flip a Brier `actual`. Before this file it had ZERO coverage (#441), and that
gap hid a Fatal (#439): walkback falsification was a no-op in practice because
(a) `git show --name-only` without `--first-parent` suppresses merge diffs, and
(b) squash-merged `fix(...)` commits are not `--merges` so were never discovered.

These tests build a real on-disk git repo (a merge of a `fix/*` branch AND a
squash-style `fix(...)` commit) and run the GIT layer with cwd inside it — the
same integration style as test_brier_advise.py. Pure stdlib unittest; no central
store is touched.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import reconcile_ledger as rl  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, text=True)


def _write(repo, name, content="x\n"):
    with open(os.path.join(repo, name), "w") as f:
        f.write(content)


class GitLayerFalsificationTest(unittest.TestCase):
    """Builds: base commit → fix/foo branch (2 files) merged --no-ff →
    a squash-style `fix(parser): … (#NN)` commit (1 file) → a non-fix commit
    and a `prefix(...)` decoy. Both real fix landings must be discovered with
    non-empty touched_files."""

    def _build_repo(self, repo):
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        _write(repo, "a.txt", "1\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "base")
        # real merge of a fix/* branch (2 files)
        _git(repo, "checkout", "-qb", "fix/foo")
        _write(repo, "b.txt")
        _write(repo, "c.txt")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "work on fix")
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "--no-ff", "-q", "fix/foo", "-m", "Merge branch 'fix/foo'")
        # squash-style fix landing (single non-merge commit, conventional subject, 1 file)
        _write(repo, "d.txt")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fix(parser): handle empty input (#123)")
        # decoys that must NOT be discovered
        _write(repo, "e.txt")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "feat(core): unrelated feature")
        _write(repo, "f.txt")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "prefix(x): not a fix")

    def test_discover_candidates_finds_merge_and_squash_with_files(self):
        with tempfile.TemporaryDirectory() as repo:
            self._build_repo(repo)
            old = os.getcwd()
            os.chdir(repo)
            try:
                cands = rl.discover_candidates(30)
            finally:
                os.chdir(old)
        touched = sorted(sorted(c["touched_files"]) for c in cands)
        # Exactly the two real fix landings, each with its real files.
        self.assertEqual(len(cands), 2, f"expected merge+squash, got {cands}")
        self.assertIn(["b.txt", "c.txt"], touched)   # merge diff (was [] pre-fix)
        self.assertIn(["d.txt"], touched)            # squash commit (was undiscovered)
        for c in cands:
            self.assertTrue(c["touched_files"], f"empty touched_files: {c}")
            self.assertTrue(c["merge_time"])

    def test_fix_branch_sizes_counts_merge_and_squash(self):
        with tempfile.TemporaryDirectory() as repo:
            self._build_repo(repo)
            old = os.getcwd()
            os.chdir(repo)
            try:
                sizes = rl.fix_branch_sizes(90)
            finally:
                os.chdir(old)
        # merge brought 2 files, squash brought 1; decoys contribute nothing.
        self.assertEqual(sorted(sizes), [1, 2], f"got {sizes}")


class FixCommitSubjectTest(unittest.TestCase):
    """Pure matcher for squash-merged conventional-commit fix subjects (#441)."""

    def test_matches_conventional_fix_subjects(self):
        for s in ("fix: x", "fix(scope): x", "fix(rcpt_verify): #412 (#438)",
                  "fix(core)!: breaking", "hotfix: urgent", "HotFix(x): y"):
            self.assertTrue(rl._is_fix_commit_subject(s), s)

    def test_rejects_non_fix_subjects(self):
        for s in ("feat(x): y", "prefix(x): y", "affix: y", "fixture: y",
                  "chore: fix typo", "refactor: fix naming", "", "fix"):
            self.assertFalse(rl._is_fix_commit_subject(s), s)


class CrossCutThresholdBoundaryTest(unittest.TestCase):
    """cross_cut_threshold_from p90-vs-bootstrap boundary at N=30 (#441)."""

    def test_below_min_samples_uses_bootstrap(self):
        self.assertEqual(rl.cross_cut_threshold_from([5] * 29),
                         rl.BOOTSTRAP_CROSS_CUT)

    def test_at_min_samples_uses_p90(self):
        # 30 samples: nearest-rank p90 = ceil(0.9*30)=27th of sorted 1..30 → 27.
        self.assertEqual(rl.cross_cut_threshold_from(list(range(1, 31))), 27)


class FixMergeSubjectTest(unittest.TestCase):
    """#441 gap-1 residual: pure matcher for MERGE-commit subjects naming a fix/* or
    hotfix/* branch. The squash analog `_is_fix_commit_subject` has a pure test; the
    merge matcher's anchor invariant (matches `fix/`/`hotfix/` at a branch boundary but
    NOT mid-word `prefix/`/`affix/`/`suffix/`, S-4) was only exercised via the
    integration repo build, never asserted directly — a regex edit could regress the
    anchor undetectably."""

    def test_matches_fix_and_hotfix_branch_merges(self):
        for s in ("Merge branch 'fix/foo'", "merge hotfix/x", "fix/bar at start",
                  "Merge remote-tracking branch \"fix/baz\"", "x /fix/y", "HotFix/Y"):
            self.assertTrue(rl._is_fix_merge_subject(s), s)

    def test_rejects_midword_and_non_fix_subjects(self):
        for s in ("prefix/x", "affix/x", "suffix/y", "feat/x",
                  "Merge branch 'feature'", "", "fix:"):
            self.assertFalse(rl._is_fix_merge_subject(s), s)


class DiscoverRevertAndReferenceTest(unittest.TestCase):
    """#343 git-layer discovery (revert + referencing) was untested (#408 F16c)."""

    def _base(self, repo):
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        _write(repo, "a.txt", "1\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "base")

    def test_discover_revert_candidates_finds_canonical_revert(self):
        with tempfile.TemporaryDirectory() as repo:
            self._base(repo)
            _write(repo, "a.txt", "2\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-qm", "feat: a thing")
            _git(repo, "revert", "--no-edit", "HEAD")   # subject: Revert "feat: a thing"
            old = os.getcwd()
            os.chdir(repo)
            try:
                cands = rl.discover_revert_candidates(30)
            finally:
                os.chdir(old)
            self.assertTrue(cands, "expected the canonical revert commit")
            rc = cands[0]
            self.assertTrue(rc["message"].startswith("Revert"))
            self.assertIn("a.txt", rc["touched_files"])
            self.assertTrue(rc["merge_time"])

    def test_discover_reference_commits_matches_token(self):
        with tempfile.TemporaryDirectory() as repo:
            self._base(repo)
            _write(repo, "b.txt")
            _git(repo, "add", ".")
            _git(repo, "commit", "-qm", "chore: closes #341 — wrap up")
            old = os.getcwd()
            os.chdir(repo)
            try:
                cands = rl.discover_reference_commits(["#341"], 30)
            finally:
                os.chdir(old)
            self.assertTrue(cands, "expected the #341-referencing commit")
            self.assertIn("#341", cands[0]["message"])

    def test_gh_regression_commits_graceful_without_remote(self):
        # gh absent → FileNotFoundError → graceful [] (not a crash). Patching the
        # global subprocess.run intercepts the function's `subprocess.run(...)`
        # call deterministically and offline (no real gh, no network).
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            out = rl._git_gh_regression_commits()
        self.assertEqual(out, [])


class MainOrchestrationTest(unittest.TestCase):
    """End-to-end main() wiring (discover → reconcile → predicate pass → brier
    write) was untested (#408 F16c). Builds a repo with a squash `fix(...)`
    commit and a stale ledger PASS whose gated_files intersect it; asserts the
    walkback falsifies the PASS and brier-rolling.json is written."""

    def test_main_walkback_falsifies_and_writes_brier(self):
        saved = os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        try:
            with tempfile.TemporaryDirectory() as repo:
                _git(repo, "init", "-q", "-b", "main")
                _git(repo, "config", "user.email", "t@t")
                _git(repo, "config", "user.name", "t")
                _write(repo, "auth.py", "1\n")
                _git(repo, "add", ".")
                _git(repo, "commit", "-qm", "base")
                _write(repo, "auth.py", "2\n")
                _git(repo, "add", ".")
                _git(repo, "commit", "-qm", "fix(auth): patch hole (#9)")

                ledger = os.path.join(repo, "runs.jsonl")
                with open(ledger, "w", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "run_id": "r1", "skill": "siege", "verdict": "PASS",
                        "confidence": 0.9, "artifact_type": "code",
                        "backfilled": False, "gated_files": ["auth.py"],
                        "timestamp": "2020-01-01T00:00:00Z",   # >30d old
                    }) + "\n")
                fals = os.path.join(repo, "fals.jsonl")
                brier = os.path.join(repo, "brier.json")

                old = os.getcwd()
                os.chdir(repo)
                try:
                    rc = rl.main([
                        "--ledger", ledger, "--falsification", fals,
                        "--manual-attribution", os.path.join(repo, "m.jsonl"),
                        "--brier-out", brier, "--lookback-days", "3650",
                    ])
                finally:
                    os.chdir(old)

                self.assertEqual(rc, 0)
                self.assertTrue(os.path.exists(fals), "no falsification written")
                with open(fals, encoding="utf-8") as f:
                    rows = [json.loads(ln) for ln in f if ln.strip()]
                self.assertTrue(any(r["falsified_by"]["via"] == "walkback"
                                    for r in rows), rows)
                self.assertTrue(os.path.exists(brier), "no brier-rolling written")
                with open(brier, encoding="utf-8") as f:
                    self.assertIn("siege", json.load(f))
        finally:
            if saved is not None:
                os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = saved


if __name__ == "__main__":
    unittest.main()
