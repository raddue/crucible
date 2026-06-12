#!/usr/bin/env python3
"""Phase 3 (#398) — central-store mutator tests (grudge / render_ledger / backfill).

The store mutators were systemically untested as a class (audit S3/S4). They are
the highest-blast-radius helpers in the suite:
  - `grudge_append` carries a PRIVACY GUARD (it refuses to write the grudge store
    into the repo tree, because grudges carry private file paths and this repo is
    PUBLIC) — a regression there leaks private paths into a public git history.
  - `grudge_query` parses untrusted on-disk grudge files and runs a user-authored
    `anti_pattern_signature` regex under a SIGALRM wall-clock budget.
  - `render_ledger` computes the honest "caught N silent bugs" headline and the
    3x-rolling-median inflation detector (the anti-gaming check).
  - `backfill-ledger` builds synthetic ledger entries; its module docstring used
    to claim "the smoke test exercises the pure core" while NO such test existed
    (this file is now that coverage; the docstring is corrected in the same PR).

Pure stdlib `unittest`. Every store path is a tmp dir; the machine-local central
stores (`~/.claude/crucible/{grudge,ledger}`) are never touched. `filter_ignored`
runs against a throwaway `git init` repo, never the crucible repo.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from scripts import grudge_append as ga  # noqa: E402
from scripts import grudge_query as gq  # noqa: E402
from scripts import render_ledger as rl  # noqa: E402

# backfill-ledger.py is hyphenated → not importable by name; load it from path.
_bf_spec = importlib.util.spec_from_file_location(
    "backfill_ledger", os.path.join(HERE, "backfill-ledger.py"))
bf = importlib.util.module_from_spec(_bf_spec)
_bf_spec.loader.exec_module(bf)


# --------------------------------------------------------------------------- #
# grudge_append — normalize_path / _is_inside                                  #
# --------------------------------------------------------------------------- #

class GrudgeNormalizeTest(unittest.TestCase):
    def test_backslashes_to_posix(self):
        self.assertEqual(ga.normalize_path("a\\b\\c.py", "/repo"), "a/b/c.py")

    def test_absolute_made_repo_relative(self):
        self.assertEqual(ga.normalize_path("/repo/src/a.py", "/repo"), "src/a.py")

    def test_leading_dot_slash_and_trailing_slash_stripped(self):
        self.assertEqual(ga.normalize_path("./src/dir/", "/repo"), "src/dir")

    def test_relative_outside_repo_left_alone(self):
        # A plain relative path not under repo_root is returned cleaned, not abs.
        self.assertEqual(ga.normalize_path("src/a.py", "/repo"), "src/a.py")


class GrudgeIsInsideTest(unittest.TestCase):
    def test_child_under_parent_true(self):
        with tempfile.TemporaryDirectory() as d:
            child = os.path.join(d, "a", "b")
            os.makedirs(child)
            self.assertTrue(ga._is_inside(child, d))

    def test_sibling_not_inside(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a")
            b = os.path.join(d, "b")
            os.makedirs(a)
            os.makedirs(b)
            self.assertFalse(ga._is_inside(a, b))

    def test_parent_equals_child_is_inside(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(ga._is_inside(d, d))


# --------------------------------------------------------------------------- #
# grudge_append — append() PRIVACY GUARD (load-bearing: public repo)           #
# --------------------------------------------------------------------------- #

class GrudgePrivacyGuardTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()      # stand-in for the (public) repo tree
        self.outside = tempfile.mkdtemp()   # a store location OUTSIDE the repo

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_refuses_to_write_store_inside_repo_tree(self):
        # base_dir INSIDE repo_root → target grudges dir is inside the repo →
        # the privacy guard must refuse (return None) and write NOTHING. This is
        # the guard that keeps private paths out of the PUBLIC git history.
        inside_base = os.path.join(self.repo, ".claude", "grudge")
        path = ga.append(
            symptom="auth bypass regression",
            files_touched=["src/auth/token.py"],
            repo="myrepo", repo_root=self.repo, base_dir=inside_base,
        )
        self.assertIsNone(path)
        # Nothing was created anywhere under the repo tree.
        self.assertFalse(os.path.exists(os.path.join(inside_base, "myrepo")))

    def test_writes_when_store_is_outside_repo(self):
        path = ga.append(
            symptom="auth bypass regression",
            files_touched=["src/auth/token.py"],
            anti_pattern_signature="verify_token",
            repo="myrepo", repo_root=self.repo, base_dir=self.outside,
        )
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertNotIn(os.path.realpath(self.repo),
                         os.path.realpath(path))   # store lives outside the repo
        # Intent-precise: the written grudge file's directory is NOT inside the
        # repo tree (the privacy invariant the substring check only approximates).
        self.assertFalse(ga._is_inside(os.path.dirname(path), self.repo))

    def test_idempotent_overwrite_on_same_key(self):
        kw = dict(symptom="same symptom", files_touched=["a.py"],
                  anti_pattern_signature="sig", repo="r",
                  repo_root=self.repo, base_dir=self.outside)
        p1 = ga.append(**kw)
        p2 = ga.append(**kw)
        self.assertEqual(p1, p2)   # overwrite-on-key, not a second file
        grudges = [n for n in os.listdir(os.path.dirname(p1))
                   if n.endswith(".md")]
        self.assertEqual(len(grudges), 1)

    def test_no_files_skipped(self):
        self.assertIsNone(ga.append(
            symptom="x", files_touched=[], repo="r",
            repo_root=self.repo, base_dir=self.outside))

    def test_empty_discriminator_skipped(self):
        # no anti_pattern_signature AND no symptom → nothing to key on → skip.
        self.assertIsNone(ga.append(
            symptom="", files_touched=["a.py"], repo="r",
            repo_root=self.repo, base_dir=self.outside))


# --------------------------------------------------------------------------- #
# grudge_query — parse_grudge / _path_match / survivors / load_grudges         #
# --------------------------------------------------------------------------- #

class ParseGrudgeTest(unittest.TestCase):
    def _write(self, d, name, text):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_valid_frontmatter_parses_files_and_signature(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "g.md",
                            '---\n'
                            'repo_root: /repo\n'
                            'files_touched: ["a.py", "b.py"]\n'
                            'anti_pattern_signature: "verify_token"\n'
                            '---\n'
                            'body text\n')
            g = gq.parse_grudge(p)
            self.assertEqual(g["files_touched"], ["a.py", "b.py"])
            self.assertEqual(g["anti_pattern_signature"], "verify_token")

    def test_triple_dash_inside_value_does_not_truncate(self):
        # The split is on a '---' alone on its own line; a '---' inside a value
        # (or body) must NOT truncate the frontmatter and drop files_touched.
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "g.md",
                            '---\n'
                            'symptom: regression --- see PR\n'
                            'files_touched: ["a.py"]\n'
                            '---\n'
                            'body with --- a horizontal rule\n')
            g = gq.parse_grudge(p)
            self.assertEqual(g["files_touched"], ["a.py"])
            self.assertEqual(g["symptom"], "regression --- see PR")

    def test_missing_frontmatter_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "g.md", "no frontmatter here\n")
            self.assertIsNone(gq.parse_grudge(p))

    def test_unterminated_frontmatter_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "g.md", "---\nfiles_touched: [\"a.py\"]\n")
            self.assertIsNone(gq.parse_grudge(p))


class PathMatchTest(unittest.TestCase):
    def test_exact_equality(self):
        self.assertTrue(gq._path_match("src/a.py", "src/a.py"))

    def test_literal_with_metachars_matches_itself_first(self):
        # A real filename containing glob metachars (Next.js dynamic route) must
        # match itself by exact equality before the metachar/glob path.
        self.assertTrue(gq._path_match("pages/[id].js", "pages/[id].js"))

    def test_glob_stored_pattern(self):
        self.assertTrue(gq._path_match("src/auth/token.py", "src/auth/*"))
        self.assertFalse(gq._path_match("src/auth/sub/x.py", "src/auth/*"))

    def test_non_match(self):
        self.assertFalse(gq._path_match("src/a.py", "src/b.py"))


class SurvivorsTest(unittest.TestCase):
    def test_existing_file_survives_missing_does_not(self):
        with tempfile.TemporaryDirectory() as repo:
            open(os.path.join(repo, "live.py"), "w").close()
            grudge = {"files_touched": ["live.py", "gone.py"]}
            self.assertEqual(gq.survivors(grudge, repo), ["live.py"])

    def test_glob_entry_survives_iff_matches_a_real_file(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "src", "auth"))
            open(os.path.join(repo, "src", "auth", "token.py"), "w").close()
            self.assertEqual(
                gq.survivors({"files_touched": ["src/auth/*"]}, repo),
                ["src/auth/*"])
            self.assertEqual(
                gq.survivors({"files_touched": ["src/none/*"]}, repo), [])


class LoadGrudgesRepoRootFilterTest(unittest.TestCase):
    def test_same_basename_repo_does_not_bleed(self):
        # load_grudges filters on realpath(repo_root) equality, so a grudge whose
        # repo_root differs is excluded even if it lives under the same basename
        # dir (fix #3 — same-named repos cannot bleed into each other).
        with tempfile.TemporaryDirectory() as base, \
                tempfile.TemporaryDirectory() as repo_root:
            gdir = ga.grudges_dir("myrepo", base)
            os.makedirs(gdir)
            mine = ('---\nrepo_root: %s\nfiles_touched: ["a.py"]\n'
                    'anti_pattern_signature: ""\n---\nbody\n' % repo_root)
            theirs = ('---\nrepo_root: /some/other/repo\n'
                      'files_touched: ["b.py"]\nanti_pattern_signature: ""\n'
                      '---\nbody\n')
            with open(os.path.join(gdir, "mine.md"), "w") as f:
                f.write(mine)
            with open(os.path.join(gdir, "theirs.md"), "w") as f:
                f.write(theirs)
            loaded = gq.load_grudges("myrepo", repo_root, base)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["files_touched"], ["a.py"])


class SignatureHitTest(unittest.TestCase):
    def _repo_with_file(self, d, relpath, content):
        full = os.path.join(d, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

    def test_regex_signature_hits(self):
        with tempfile.TemporaryDirectory() as repo:
            self._repo_with_file(repo, "src/auth.py", "def verify_token(): pass")
            self.assertTrue(
                gq._signature_hit(r"verify_\w+", ["src/auth.py"], repo))

    def test_no_hit_when_absent(self):
        with tempfile.TemporaryDirectory() as repo:
            self._repo_with_file(repo, "src/auth.py", "def login(): pass")
            self.assertFalse(
                gq._signature_hit(r"verify_\w+", ["src/auth.py"], repo))

    def test_bad_regex_falls_back_to_literal_substring(self):
        # An invalid regex must not crash the pre-flight; it degrades to a
        # literal substring search (fix #7). "[" is an unterminated char class.
        with tempfile.TemporaryDirectory() as repo:
            self._repo_with_file(repo, "a.py", "weird [unclosed token here")
            self.assertTrue(gq._signature_hit("[unclosed", ["a.py"], repo))

    def test_off_main_thread_degrades_to_literal_not_crash(self):
        # SIGALRM can only be armed on the main thread; off the main thread the
        # matcher degrades to literal substring matching rather than raising.
        # If the `threading.current_thread() is threading.main_thread()` guard
        # (grudge_query.py ~L182-185) were removed, _signal.signal(SIGALRM, ...)
        # would be invoked off-thread and raise ValueError. So we ALSO assert no
        # exception propagated AND that the thread ran the call to completion —
        # without that guard `result["ok"]` would never be set. Not timing-based.
        with tempfile.TemporaryDirectory() as repo:
            self._repo_with_file(repo, "a.py", "contains NEEDLE somewhere")
            result = {}

            def run():
                try:
                    result["hit"] = gq._signature_hit("NEEDLE", ["a.py"], repo)
                    result["ok"] = True
                except BaseException as e:  # noqa: BLE001
                    result["error"] = repr(e)

            t = threading.Thread(target=run)
            t.start()
            t.join(timeout=10)
            self.assertFalse(t.is_alive(), "off-thread matcher did not finish")
            self.assertNotIn("error", result,
                             "off-thread signature match must not raise "
                             "(main-thread SIGALRM guard regressed): "
                             + result.get("error", ""))
            self.assertTrue(result.get("ok"))
            self.assertTrue(result.get("hit"))


# --------------------------------------------------------------------------- #
# render_ledger — caught_count (honest headline) / inflation_alert             #
# --------------------------------------------------------------------------- #

class CaughtCountTest(unittest.TestCase):
    def test_counts_whs_true_forward_entries(self):
        entries = [
            {"would_have_shipped_without_gate": True},
            {"would_have_shipped_without_gate": True},
            {"would_have_shipped_without_gate": False},
            {"would_have_shipped_without_gate": None},
        ]
        self.assertEqual(rl.caught_count(entries), 2)

    def test_backfilled_excluded_even_if_whs_forced_true(self):
        # The exclusion keys on `backfilled` itself, not merely WHS being null —
        # a pathological backfilled entry with WHS forced True is still excluded.
        entries = [
            {"would_have_shipped_without_gate": True, "backfilled": True},
            {"would_have_shipped_without_gate": True},
        ]
        self.assertEqual(rl.caught_count(entries), 1)


class InflationAlertTest(unittest.TestCase):
    def test_silent_until_baseline_weeks_met(self):
        rates = {"siege": {"significant_rate": 1.0, "fatal_rate": 0.0}}
        base = {"siege": {"significant_median": 0.01, "fatal_median": 0.0,
                          "weeks": 3}}   # < MIN_BASELINE_WEEKS (4)
        self.assertEqual(rl.inflation_alert(rates, base), [])

    def test_fires_on_significant_rate_over_3x_median(self):
        rates = {"siege": {"significant_rate": 0.40, "fatal_rate": 0.0}}
        base = {"siege": {"significant_median": 0.10, "fatal_median": 0.0,
                          "weeks": 4}}   # 0.40 > 3 * 0.10
        alerts = rl.inflation_alert(rates, base)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["skill"], "siege")

    def test_fires_on_fatal_rate_over_3x_median(self):
        rates = {"siege": {"significant_rate": 0.0, "fatal_rate": 0.20}}
        base = {"siege": {"significant_median": 0.0, "fatal_median": 0.05,
                          "weeks": 5}}   # 0.20 > 3 * 0.05
        self.assertEqual(len(rl.inflation_alert(rates, base)), 1)

    def test_no_fire_at_exactly_3x_boundary(self):
        # inflation_alert uses a STRICT `>` (sig > 3 * sig_med, render_ledger.py
        # L253), so a rate EXACTLY at 3x the median must NOT fire. Pins the
        # boundary against an accidental flip to `>=`.
        rates = {"siege": {"significant_rate": 0.30, "fatal_rate": 0.0}}
        base = {"siege": {"significant_median": 0.10, "fatal_median": 0.0,
                          "weeks": 4}}   # 0.30 == 3 * 0.10 → strict > is False
        self.assertEqual(rl.inflation_alert(rates, base), [])

    def test_no_fire_within_3x(self):
        rates = {"siege": {"significant_rate": 0.25, "fatal_rate": 0.0}}
        base = {"siege": {"significant_median": 0.10, "fatal_median": 0.0,
                          "weeks": 4}}   # 0.25 < 3 * 0.10 = 0.30
        self.assertEqual(rl.inflation_alert(rates, base), [])

    def test_zero_median_never_fires(self):
        # median 0 → no multiplier can be exceeded (the sig_med > 0 guard).
        rates = {"siege": {"significant_rate": 0.9, "fatal_rate": 0.0}}
        base = {"siege": {"significant_median": 0.0, "fatal_median": 0.0,
                          "weeks": 6}}
        self.assertEqual(rl.inflation_alert(rates, base), [])

    def test_missing_baseline_silent(self):
        rates = {"newskill": {"significant_rate": 1.0, "fatal_rate": 1.0}}
        self.assertEqual(rl.inflation_alert(rates, {}), [])


# --------------------------------------------------------------------------- #
# backfill-ledger — pr_to_entry / build_entries / filter_ignored (pure core)   #
# --------------------------------------------------------------------------- #

class PrToEntryTest(unittest.TestCase):
    def _pr(self, **over):
        pr = {"number": 320, "mergedAt": "2026-05-01T00:00:00Z",
              "files": [{"path": "src/a.py"}, {"path": "src/b.py"}]}
        pr.update(over)
        return pr

    def test_maps_pr_to_backfill_entry(self):
        e = bf.pr_to_entry(self._pr())
        self.assertEqual(e["run_id"], "backfill-320-quality-gate")
        self.assertEqual(e["skill"], "quality-gate")
        self.assertEqual(e["verdict"], "PASS")
        self.assertEqual(e["gated_files"], ["src/a.py", "src/b.py"])
        self.assertEqual(e["timestamp"], "2026-05-01T00:00:00Z")
        self.assertTrue(e["backfilled"])
        # WHS / severity / predicted_falsifier are null → inert for caught-N + Brier.
        self.assertIsNone(e["would_have_shipped_without_gate"])
        self.assertIsNone(e["severity_histogram"])
        self.assertIsNone(e["predicted_falsifier"])

    def test_accepts_filename_key_too(self):
        # _file_path accepts the older `filename` shape so a gh version bump can't
        # silently empty gated_files.
        e = bf.pr_to_entry(self._pr(files=[{"filename": "old/shape.py"}]))
        self.assertEqual(e["gated_files"], ["old/shape.py"])

    def test_path_filter_can_empty_gated_files_but_entry_kept(self):
        e = bf.pr_to_entry(self._pr(), path_filter=lambda ps: [])
        self.assertEqual(e["gated_files"], [])
        self.assertEqual(e["run_id"], "backfill-320-quality-gate")


class BuildEntriesTest(unittest.TestCase):
    NOW = "2026-06-01T00:00:00Z"

    def _pr(self, number, merged_at):
        return {"number": number, "mergedAt": merged_at,
                "files": [{"path": "a.py"}]}

    def test_inside_window_kept_outside_dropped(self):
        prs = [self._pr(1, "2026-05-25T00:00:00Z"),   # within 30d
               self._pr(2, "2026-01-01T00:00:00Z")]   # older than 30d
        out = bf.build_entries(prs, lookback_days=30, now_iso=self.NOW)
        self.assertEqual([e["run_id"] for e in out],
                         ["backfill-1-quality-gate"])

    def test_missing_number_or_mergedat_skipped(self):
        prs = [{"mergedAt": "2026-05-25T00:00:00Z", "files": []},   # no number
               {"number": 5, "files": []}]                          # no mergedAt
        self.assertEqual(bf.build_entries(prs, 30, self.NOW), [])

    def test_unparseable_mergedat_skipped(self):
        prs = [self._pr(7, "not-a-date")]
        self.assertEqual(bf.build_entries(prs, 30, self.NOW), [])

    def test_in_batch_dedup_by_run_id(self):
        prs = [self._pr(9, "2026-05-25T00:00:00Z"),
               self._pr(9, "2026-05-26T00:00:00Z")]   # same number → same run_id
        out = bf.build_entries(prs, 30, self.NOW)
        self.assertEqual(len(out), 1)


class FilterIgnoredTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True,
                       capture_output=True)
        # Hermetic: `git check-ignore` honors the host's GLOBAL excludes
        # (core.excludesFile, e.g. ~/.config/git/ignore) in addition to this
        # repo's .gitignore. A contributor/CI host whose global excludes happen
        # to match an input path (e.g. `src/a.py` or `*.py`) would otherwise
        # flake the test. Point THIS repo's excludesFile at /dev/null (always
        # empty) so only the .gitignore we write below is consulted. Scoped to
        # the tmp repo — the user's real global git config is untouched.
        subprocess.run(["git", "-C", self.repo, "config",
                        "core.excludesFile", "/dev/null"], check=True,
                       capture_output=True)
        with open(os.path.join(self.repo, ".gitignore"), "w") as f:
            f.write(".claude/\n*.log\n")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_drops_ignored_keeps_complement_in_order(self):
        paths = [".claude/x.md", "src/a.py", "debug.log", "src/b.py"]
        kept = bf.filter_ignored(paths, self.repo)
        self.assertEqual(kept, ["src/a.py", "src/b.py"])   # order preserved

    def test_empty_input_returns_empty(self):
        self.assertEqual(bf.filter_ignored([], self.repo), [])

    def test_fails_open_keeps_all_paths_on_check_ignore_error(self):
        # rc 128 (or any rc not in {0,1}) means git couldn't determine ignore
        # status. filter_ignored FAILS OPEN — keeps ALL input paths rather than
        # silently emptying gated_files (backfill-ledger.py L95-103). Deterministic
        # via a mocked subprocess; no real git repo or repo_root needed.
        fake = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="boom")
        with mock.patch.object(bf.subprocess, "run", return_value=fake):
            kept = bf.filter_ignored(["a.py", "b.py"], "/tmp/whatever")
        self.assertEqual(kept, ["a.py", "b.py"])   # all kept, order preserved


class BackfillDocstringTest(unittest.TestCase):
    def test_module_docstring_does_not_overclaim_a_nonexistent_smoke_test(self):
        # The docstring used to assert "The smoke test exercises the pure core"
        # while no such test existed (audit S4). This suite IS that coverage;
        # the docstring must no longer claim an in-module smoke test exists.
        self.assertNotIn("smoke test exercises the pure core",
                         bf.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
