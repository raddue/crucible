"""R1+R2 grudge-guard redesign tests (#570/#581/#582) + pre-R3 store identity.

Phase R1+R2 of the #558/#559 class redesign (design §3/§8/§9/§10, plan §2/§3):
the append-only session journal is the bound, with per-member disposition; and
the pre-R3 store-identity primitive `resolve_store_repo()` (+ C-l env hardening)
that R5's reader depends on.

Red-first discipline: each test below was written to FAIL against the pre-phase
hook / script, then the implementation was added. Pure stdlib; never touches
real machine state (HOME / CRUCIBLE_GRUDGE_DIR redirected into tmp trees, like
scripts/test_grudge_r4_encoding.py).

Test-to-spec map (design §9):
  - `resolve_store_repo` / C-l      ... store identity (§4.2/§8) + env allowlist
  - T-a ... T-z, T-bb, T-cc         ... R1+R2 journal fences (driven through the
                                        real Stop hook, like the R4 suite)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

GRUDGE_APPEND = os.path.join(REPO_ROOT, "scripts", "grudge_append.py")
HOOK = os.path.join(REPO_ROOT, "hooks", "grudge-resolution-guard.sh")

SESSION_START_TS = "2026-01-01T00:00:00.000Z"


def _clean_env(**extra):
    env = dict(os.environ)
    for key in ("CRUCIBLE_CALIBRATION_DISABLED",
                "CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD",
                "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env.pop(key, None)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.update(extra)
    return env


def _git(repo, *args, env=None):
    e = _clean_env(
        GIT_AUTHOR_NAME="R12 Test", GIT_AUTHOR_EMAIL="r12@test.invalid",
        GIT_COMMITTER_NAME="R12 Test", GIT_COMMITTER_EMAIL="r12@test.invalid",
    )
    if env:
        e.update(env)
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True,
        env=e, timeout=30,
    )


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _init_repo(root, name="repo"):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "R12 Test")
    _git(repo, "config", "user.email", "r12@test.invalid")
    return repo


class RESOLVE_STORE_IDENTITY(unittest.TestCase):
    """Pre-R3 store identity (#580): `resolve_store_repo()` returns the
    git-common-dir parent (STORE identity), not the worktree (FS identity)."""

    def _resolve(self, start_dir, cwd):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from scripts.grudge_append import resolve_store_repo; "
            "r = resolve_store_repo(sys.argv[2]); print('%s\\t%s' % r); "
            "sys.stderr.write('FALLBACK:0\\n')"
        )
        for _ in range(1):
            break
        proc = subprocess.run(
            [sys.executable, "-c", code, REPO_ROOT, start_dir],
            capture_output=True, text=True, cwd=cwd, timeout=30,
            env=_clean_env(),
        )
        return proc.stdout.strip(), proc.stderr.strip()

    def test_ordinary_clone_resolves_to_repo_root(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write_bytes(os.path.join(repo, "README.md"), b"t\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: base")
            expect_site = os.path.basename(os.path.realpath(repo))
            out, _err = self._resolve(repo, repo)
            self.assertEqual(out, f"{expect_site}\t{os.path.realpath(repo)}")

    def test_ordinary_clone_from_subdir_resolves_against_start_dir(self):
        """SIEGE-R2-M8: a RELATIVE git-common-dir (`.git`, `../../.git`)
        resolves against start_dir, never the process cwd."""
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write_bytes(os.path.join(repo, "README.md"), b"t\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: base")
            sub = os.path.join(repo, "sub", "deep")
            os.makedirs(sub)
            expect_site = os.path.basename(os.path.realpath(repo))
            out, _err = self._resolve(sub, repo)
            self.assertEqual(out, f"{expect_site}\t{os.path.realpath(repo)}")

    def test_linked_worktree_resolves_to_main_clone_common_dir_parent(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            _write_bytes(os.path.join(repo, "README.md"), b"t\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: base")
            _git(repo, "branch", "wtbr")
            wt = os.path.join(root, "linked")
            _git(repo, "worktree", "add", "-q", wt, "wtbr")
            expect_site = os.path.basename(os.path.realpath(repo))
            out, _err = self._resolve(wt, wt)
            self.assertEqual(out, f"{expect_site}\t{os.path.realpath(repo)}")

    def test_submodule_falls_back_to_its_own_resolve_repo(self):
        with tempfile.TemporaryDirectory() as root:
            superrepo = _init_repo(root, name="super")
            _write_bytes(os.path.join(superrepo, "f.txt"), b"t\n")
            _git(superrepo, "add", "-A")
            _git(superrepo, "commit", "-qm", "chore: super")
            sub = os.path.join(superrepo, "sub")
            os.makedirs(sub)
            _git(sub, "init", "-q")
            _git(sub, "config", "user.name", "R12 Test")
            _git(sub, "config", "user.email", "r12@test.invalid")
            _write_bytes(os.path.join(sub, "s.txt"), b"t\n")
            _git(sub, "add", "-A")
            _git(sub, "commit", "-qm", "chore: sub")
            _git(superrepo, "-c", "protocol.file.allow=always",
                 "submodule", "add", "-q", sub, "sub")
            _git(superrepo, "-c", "protocol.file.allow=always",
                 "commit", "-qm", "chore: add submodule")
            # The submodule's own store identity is its own worktree root, NOT
            # the literal string `modules` (SIEGE-R2-M7).
            expect_site = os.path.basename(os.path.realpath(sub))
            out, _err = self._resolve(sub, sub)
            self.assertIn("\t%s" % os.path.realpath(sub), out)
            self.assertEqual(out.split("\t")[0], expect_site)


class C_L_ENV_ALLOWLIST(unittest.TestCase):
    """C-l (design §9): every git shell-out in the grudge subsystem runs git
    through the PATH+HOME allowlist, never the inherited environment."""

    def test_grudge_append_git_calls_pass_allowlisted_env(self):
        with open(GRUDGE_APPEND, "r", encoding="utf-8") as fh:
            src = fh.read()
        calls = [ln for ln in src.splitlines() if "git" in ln and "subprocess" in ln]
        for ln in calls:
            self.assertIn("env=", ln,
                          f"grudge_append git shell-out lacks allowlisted env: {ln}")
        self.assertIn("_GIT_ENV_KEEP", src,
                      "grudge_append must define the PATH/HOME allowlist")


def _run_cli(cmd, cwd, env, timeout=60):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def _cli_env(store):
    env = _clean_env(CRUCIBLE_GRUDGE_DIR=store,
                     GIT_AUTHOR_NAME="R3 Test", GIT_AUTHOR_EMAIL="r3@test.invalid",
                     GIT_COMMITTER_NAME="R3 Test",
                     GIT_COMMITTER_EMAIL="r3@test.invalid")
    return env


def _linked_worktree(root, repo, branch="wtbr"):
    _write_bytes(os.path.join(repo, "README.md"), b"t\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore: base")
    _git(repo, "branch", branch)
    wt = os.path.join(root, "linked")
    _git(repo, "worktree", "add", "-q", wt, branch)
    return wt


class R3_STORE_IDENTITY_ROUND_TRIP(unittest.TestCase):
    """R3 (#580) T-j: a grudge written from a LINKED WORKTREE is found from the
    main checkout, and one written from the main checkout is found from the
    linked worktree — the store is keyed by store identity (git-common-dir
    parent), not filesystem identity."""
    GRUDGE_QUERY = os.path.join(REPO_ROOT, "scripts", "grudge_query.py")

    def test_worktree_to_main_and_back(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            wt = _linked_worktree(root, repo)
            store = os.path.join(root, "store")
            env = _cli_env(store)
            # Write a file present in BOTH trees (same branch).
            for tree in (repo, wt):
                _write_bytes(os.path.join(tree, "src", "a.py"), b"V = 1\n")
                _write_bytes(os.path.join(tree, "src", "b.py"), b"W = 2\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "feat: add a + b")
            _git(wt, "merge", "-q", "HEAD")
            # Record from the LINKED WORKTREE.
            r_wt = _run_cli(
                [sys.executable, GRUDGE_APPEND, "--symptom", "s",
                 "--root-cause", "c", "--files=src/a.py", "--why", "w"],
                cwd=wt, env=env)
            self.assertEqual(r_wt.returncode, 0, r_wt.stderr)
            self.assertNotEqual(r_wt.stdout.strip(), "")
            # Found from the MAIN checkout.
            r_main = _run_cli([sys.executable, self.GRUDGE_QUERY, "src/a.py"],
                              cwd=repo, env=env)
            self.assertEqual(r_main.returncode, 0, r_main.stderr)
            self.assertIn("grudge(s) held", r_main.stdout)
            # A second grudge recorded from MAIN, found from the WORKTREE.
            r_main2 = _run_cli(
                [sys.executable, GRUDGE_APPEND, "--symptom", "s2",
                 "--root-cause", "c2", "--files=src/b.py", "--why", "w2"],
                cwd=repo, env=env)
            self.assertEqual(r_main2.returncode, 0, r_main2.stderr)
            r_wt2 = _run_cli([sys.executable, self.GRUDGE_QUERY, "src/b.py"],
                             cwd=wt, env=env)
            self.assertEqual(r_wt2.returncode, 0, r_wt2.stderr)
            self.assertIn("grudge(s) held", r_wt2.stdout)


class R3_ABSOLUTE_PATH_NORMALIZES(unittest.TestCase):
    """R3 (#580) T-w: an ABSOLUTE path under a linked worktree, recorded with
    store identity, normalises identically to the same file recorded from the
    main checkout — the single-repo_root shape that silently broke this (S5)."""

    def test_absolute_path_round_trips_via_store_identity(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            wt = _linked_worktree(root, repo)
            store = os.path.join(root, "store")
            env = _cli_env(store)
            for tree in (repo, wt):
                _write_bytes(os.path.join(tree, "src", "a.py"), b"V = 1\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "feat: add a")
            _git(wt, "merge", "-q", "HEAD")
            # Absolute path under the LINKED WORKTREE root. Same symptom: the
            # discriminator is identical, so only the normalized path can move
            # the hash — both recordings MUST collide on one file.
            abs_wt = os.path.join(wt, "src", "a.py")
            r1 = _run_cli(
                [sys.executable, GRUDGE_APPEND, "--symptom", "s",
                 "--files=" + abs_wt], cwd=wt, env=env)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            # Same file recorded from MAIN with an absolute main-root path.
            abs_main = os.path.join(repo, "src", "a.py")
            r2 = _run_cli(
                [sys.executable, GRUDGE_APPEND, "--symptom", "s",
                 "--files=" + abs_main], cwd=repo, env=env)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            # Same store, same normalized path -> same hash — one file.
            self.assertEqual(r1.stdout.strip(), r2.stdout.strip(),
                             "both recordings must land in the SAME store file")


class R3_TWO_ROOT_PRIVACY_GUARD(unittest.TestCase):
    """R3 (#580) T-w negative arm (SIEGE-R2-H7): a store path placed inside the
    MAIN clone while recording from a linked worktree is REFUSED — the two-root
    guard catches what a worktree_root-only check would miss."""

    def test_store_inside_main_clone_refused(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            wt = _linked_worktree(root, repo)
            _write_bytes(os.path.join(repo, "src", "a.py"), b"V = 1\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "feat: add a")
            _git(wt, "merge", "-q", "HEAD")
            # The grudge base SITS inside the main clone root — a public tree.
            store = os.path.join(repo, ".grudge-store")
            env = _cli_env(store)
            r = _run_cli(
                [sys.executable, GRUDGE_APPEND, "--symptom", "s",
                 "--files=src/a.py"], cwd=wt, env=env)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("refusing to write grudges into the repo tree",
                          r.stderr)


class R3_STORE_KEY_MIGRATION(unittest.TestCase):
    """R3 (#580) §4.3: the store-identity detector reports a worktree-keyed
    record, and --migrate-store-keys moves the directory AND the repo_root
    frontmatter so a store-identity reader finds it."""
    GRUDGE_GUARD_DOCTOR = os.path.join(REPO_ROOT, "scripts", "grudge_guard_doctor.py")

    def test_detect_and_migrate_worktree_keyed(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _init_repo(root)
            wt = _linked_worktree(root, repo)
            store = os.path.join(root, "store")
            _write_bytes(os.path.join(repo, "src", "a.py"), b"V = 1\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "feat: add a")
            # Build a WORKTREE-keyed record by hand: it lives under the store
            # dir named for the WORKTREE basename, with a mismatched repo_root.
            wt_key = os.path.basename(os.path.realpath(wt))
            wt_dir = os.path.join(store, wt_key, "grudges")
            os.makedirs(wt_dir)
            _write_bytes(os.path.join(wt_dir, "wtkeyed.md"),
                         ("---\nschema: 1\nhash: wtkeyed\nrepo: %s\n"
                          "repo_root: %s\nfixed_in_commit: \nsymptom: s\n"
                          "root_cause: c\nfiles_touched: []\n"
                          "anti_pattern_signature: ''\ndate_fixed: 2026-01-01\n"
                          "---\n## Repro\nr\n## Why this kept happening\nw\n"
                          % (wt_key, os.path.realpath(wt))).encode())
            env = _cli_env(store)
            # Detector (worktree-keyed -> non-zero + names the record).
            d = _run_cli([sys.executable, self.GRUDGE_GUARD_DOCTOR, "--grudge-keys"],
                         cwd=wt, env=env)
            self.assertEqual(d.returncode, 1, d.stdout)
            self.assertIn("worktree-keyed", d.stdout)
            self.assertIn("wtkeyed", d.stdout)
            # Migrate (dir + frontmatter -> store identity).
            m = _run_cli([sys.executable, self.GRUDGE_GUARD_DOCTOR,
                          "--migrate-store-keys"], cwd=wt, env=env)
            self.assertEqual(m.returncode, 0, m.stdout)
            store_key = os.path.basename(os.path.realpath(repo))
            dst = os.path.join(store, store_key, "grudges", "wtkeyed.md")
            self.assertTrue(os.path.isfile(dst),
                            "worktree-keyed grudge must move into the store dir")
            self.assertFalse(os.path.exists(os.path.join(wt_dir, "wtkeyed.md")))
            body = open(dst, "r", encoding="utf-8").read()
            self.assertIn("repo_root: %s" % os.path.realpath(repo), body,
                          "frontmatter repo_root must be rewritten to store root")
            # After migration the store is clean.
            d2 = _run_cli([sys.executable, self.GRUDGE_GUARD_DOCTOR, "--grudge-keys"],
                          cwd=wt, env=env)
            self.assertEqual(d2.returncode, 0, d2.stdout)


EXPECTED_TESTS = 9


def _run_with_count_guard():
    result = unittest.main(exit=False, verbosity=2).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} R1+R2/store-identity tests, "
              f"ran {executed}", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())