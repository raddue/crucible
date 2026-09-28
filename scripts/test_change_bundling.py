"""Tests for scripts/change_bundling.py — the single source of truth for
deterministic changed-file selection + bundling (#630).

Pins the two load-bearing contracts the issue's acceptance criteria demand:
(1) a review over a many-file diff produces **per-file coverage** — every
changed file is assigned to exactly one bundle, with no silent skips — and
(2) the assignment is **deterministic** — same input set, same bundles,
regardless of input order or run.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.change_bundling import bundle_files, coverage_report, select_reviewable  # noqa: E402


class ParseNameStatusTest(unittest.TestCase):
    def test_parses_status_letters_and_paths(self):
        from scripts.change_bundling import parse_git_name_status
        entries = parse_git_name_status(
            "A\tsrc/added.ts\nM\tsrc/auth/token.ts\nD\tsrc/removed.ts\n")
        self.assertEqual(
            entries,
            [("A", "src/added.ts"),
             ("M", "src/auth/token.ts"),
             ("D", "src/removed.ts")])

    def test_rename_keeps_new_path(self):
        from scripts.change_bundling import parse_git_name_status
        entries = parse_git_name_status("R100\told/name.ts\tnew/name.ts\n")
        self.assertEqual(entries, [("R", "new/name.ts")])


class SelectReviewableTest(unittest.TestCase):
    def test_deletions_excluded_with_reason(self):
        selected, excluded = select_reviewable(
            [("M", "src/a.ts"), ("D", "src/removed.ts")])
        self.assertEqual(selected, ["src/a.ts"])
        self.assertEqual(excluded, [("src/removed.ts", "deleted")])

    def test_binary_excluded_with_reason(self):
        selected, excluded = select_reviewable(
            [("M", "assets/logo.png"), ("M", "src/a.ts")])
        self.assertEqual(selected, ["src/a.ts"])
        self.assertEqual(excluded, [("assets/logo.png", "binary")])

    def test_added_modified_copied_kept(self):
        selected, _ = select_reviewable(
            [("A", "src/x.ts"), ("M", "src/y.ts"),
             ("C", "src/z.ts"), ("R", "src/w.ts")])
        self.assertEqual(selected, ["src/w.ts", "src/x.ts", "src/y.ts", "src/z.ts"])


class BundleFilesTest(unittest.TestCase):
    def test_locale_siblings_bundle_together(self):
        bundles = bundle_files([
            "resources/message_en.properties",
            "resources/message_zh.properties",
            "resources/message_de.properties",
        ])
        self.assertEqual(len(bundles), 1)
        self.assertEqual(
            bundles[0],
            ["resources/message_de.properties",
             "resources/message_en.properties",
             "resources/message_zh.properties"])

    def test_locale_base_and_variants_bundle(self):
        bundles = bundle_files([
            "resources/message_en.properties",
            "resources/message.properties",
        ])
        self.assertEqual(len(bundles), 1)

    def test_distinct_dirs_stay_separate(self):
        bundles = bundle_files(["src/a.ts", "other/x.py"])
        self.assertEqual(len(bundles), 2)

    def test_same_dir_bundles_together(self):
        bundles = bundle_files(
            ["src/auth/token.ts", "src/auth/handler.ts", "other/x.py"])
        self.assertEqual(
            sorted([sorted(b) for b in bundles]),
            sorted([
                sorted(["src/auth/handler.ts", "src/auth/token.ts"]),
                ["other/x.py"],
            ]))

    def test_deterministic_regardless_of_input_order(self):
        files = [
            "resources/message_en.properties",
            "resources/message_zh.properties",
            "src/auth/token.ts",
            "src/auth/handler.ts",
            "other/x.py",
        ]
        a = bundle_files(list(reversed(files)))
        b = bundle_files(files)
        self.assertEqual(a, b)

    def test_size_cap_splits_large_dir(self):
        files = [f"src/big/f{i:02d}.py" for i in range(25)]
        bundles = bundle_files(files)
        self.assertGreater(len(bundles), 1)
        for b in bundles:
            self.assertLessEqual(len(b), 10)


class CoverageReportTest(unittest.TestCase):
    def test_every_change_covered_exactly_once(self):
        changed = [
            "resources/message_en.properties",
            "resources/message_zh.properties",
            "src/auth/token.ts",
            "other/x.py",
        ]
        selected, excluded = select_reviewable(
            [("M", path) for path in changed] + [("D", "src/removed.ts")])
        bundles = bundle_files(selected)
        report = coverage_report(
            changed + ["src/removed.ts"], bundles, excluded)

        # every changed file gets exactly one coverage row
        self.assertEqual(
            sorted(report["all"]), sorted(changed + ["src/removed.ts"]))
        self.assertEqual(
            sorted(report["bundled"]), sorted(changed),
            "every reviewable change must be in exactly one bundle")
        self.assertEqual(
            sorted(report["skipped"]), sorted(["src/removed.ts"]),
            "non-reviewable changes are explicitly reported, never silent")
        for path in changed:
            self.assertEqual(report["assignment"].count(path), 1,
                             f"{path} must be assigned to exactly one bundle")

    def test_missing_file_raises_not_silent(self):
        changed = ["src/a.ts", "src/orphaned.ts"]
        bundles = bundle_files(["src/a.ts"])
        # orphaned.ts is neither bundled nor explicitly skipped → must raise.
        with self.assertRaises(ValueError):
            coverage_report(changed, bundles, [])


if __name__ == "__main__":
    unittest.main()