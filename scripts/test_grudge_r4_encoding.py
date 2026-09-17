"""R4 encoding + injection tests (#574, #568, `_prefill` code-execution).

Phase R4 of the #558/#559 grudge-guard class redesign (design §5/§9 DEC-5):
nothing a path can contain (TAB / LF / COMMA / backtick / OSC-52) may ever
travel through a character-delimited channel, at any boundary — the hook's
in-memory path lists, the persisted per-sha state, the `--files-from` / `--files`
/ `--by-files` CLI, or a rendered command string.

Design §9 R4 regression fences exercised here, each red-first:

- **T-h** (#574): any path `git diff-tree -z` accepts round-trips through
  persistence UNCHANGED (byte-exact, incl. an invalid-UTF-8 path), persisted
  only via the NUL-delimited `$STATE_DIR/<sha>.files` artifact — and the
  embedded-newline renderer hardening (#606): no attacker path reaches the
  agent-facing block/give-up stderr, in any form.
- **T-i** (§5.1): the `_prefill` paste-me remedy is ONE fixed
  `--files-from=` command; executing it (under BOTH bash and a POSIX-sh-only
  shell) records the grudge correctly and produces NO code execution for a
  backtick / `$(` filename, is not swallowed as a flag for a leading-dash
  filename, and carries an embedded newline byte-exact. No attacker-chosen
  filename appears as verbatim text in the block/give-up stderr.
- **T-k** (#568): a comma-bearing path neither invents nor destroys a match,
  end to end (hook in-memory, `.files` persistence, `--by-files` lookup).
- **T-l** (§5.2 hazard 2): an old-version state document is detected by
  `version`, discarded safely, rewritten fresh — and the discard does not
  produce a freeze.
- **T-n** arm(.files) + arm(skips.log) (SIEGE-R2-H3): a `mkfifo`'d
  `$STATE_DIR/<sha>.files` or `$STATE_DIR/skips.log` allows the Stop within the
  bounded wait, not at the hook's own timeout ceiling; the message degrades
  (no `--files-from` remedy / no `skips.log` remedy) per C-k.
- **T-aa** (SIEGE-R2-H6, C-o): a sha-shaped key
  `deadbeef[$(touch /tmp/marker)]` supplied as a `$STATE_DIR/*.files` filename
  on disk is rejected by the hex-only validation before it can become a
  `declare -a "F_$sha"` name; no marker is created.

Pure stdlib. Never touches real machine state (HOME / CRUCIBLE_GRUDGE_DIR
redirected into tmp trees, exactly like scripts/test_558_559_acceptance.py).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

GRUDGE_APPEND = os.path.join(REPO_ROOT, "scripts", "grudge_append.py")
GRUDGE_QUERY = os.path.join(REPO_ROOT, "scripts", "grudge_query.py")
HOOK = os.path.join(REPO_ROOT, "hooks", "grudge-resolution-guard.sh")

SESSION_START_TS = "2026-01-01T00:00:00.000Z"
STATE_VERSION = 1  # must track STATE_VERSION in hooks/grudge-resolution-guard.sh


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


def _git(repo, *args):
    env = _clean_env(
        GIT_AUTHOR_NAME="R4 Test", GIT_AUTHOR_EMAIL="r4@test.invalid",
        GIT_COMMITTER_NAME="R4 Test", GIT_COMMITTER_EMAIL="r4@test.invalid",
    )
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True,
        env=env, timeout=30,
    )


def _git_bytes(repo, *args):
    """Same as _git but byte-exact stdout (git raw paths can be invalid UTF-8)."""
    env = _clean_env(
        GIT_AUTHOR_NAME="R4 Test", GIT_AUTHOR_EMAIL="r4@test.invalid",
        GIT_COMMITTER_NAME="R4 Test", GIT_COMMITTER_EMAIL="r4@test.invalid",
    )
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True,
        env=env, timeout=30,
    ).stdout


def _git_sha(repo, rev="HEAD"):
    return _git(repo, "rev-parse", rev).stdout.strip()


def _init_repo(root, name="repo"):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "R4 Test")
    _git(repo, "config", "user.email", "r4@test.invalid")
    return repo


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class HookFixture:
    """A repo the real Stop hook runs against, mirroring test_558_559_acceptance."""

    def __init__(self, root, create_store=True):
        self.home = os.path.join(root, "home")
        self.store = os.path.join(root, "store")
        os.makedirs(self.home)
        os.makedirs(self.store)
        self.repo = _init_repo(root)
        self.repo_key = os.path.basename(os.path.realpath(self.repo))
        self.transcript = os.path.join(root, "transcript.jsonl")
        with open(self.transcript, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user",
                                 "timestamp": SESSION_START_TS}) + "\n")
            fh.write(json.dumps({"type": "assistant",
                                 "timestamp": "2026-01-01T00:00:05.000Z"}) + "\n")
        _write_bytes(os.path.join(self.repo, "app.py"), b"VALUE = 0\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "chore: baseline")
        if create_store:
            os.makedirs(os.path.join(self.store, self.repo_key, "grudges"),
                        exist_ok=True)

    @property
    def project_memory(self):
        safe = self.repo.replace("/", "-")
        return os.path.join(self.home, ".claude", "projects", safe, "memory")

    @property
    def guard_dir(self):
        return os.path.join(self.project_memory, "grudge-guard")

    def payload(self, session_id, stop_hook_active=False):
        return json.dumps({
            "session_id": session_id,
            "transcript_path": self.transcript,
            "cwd": self.repo,
            "hook_event_name": "Stop",
            "stop_hook_active": stop_hook_active,
        })

    def env(self, **extra):
        env = _clean_env(HOME=self.home, CRUCIBLE_GRUDGE_DIR=self.store,
                         CLAUDE_PROJECT_DIR=REPO_ROOT)
        env.update(extra)
        return env

    def run(self, session_id, stop_hook_active=False):
        return subprocess.run(
            ["bash", HOOK], input=self.payload(session_id, stop_hook_active),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.repo, env=self.env(), timeout=90,
        )

    def state_json(self, session_id):
        path = os.path.join(self.guard_dir, f"{session_id}.json")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def add_fix_commit(self, rel_paths, message="fix(widget): repair the widget"):
        for p in rel_paths:
            _write_bytes(os.path.join(self.repo, p), b"x\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", message)
        return _git_sha(self.repo)


def _load_grudges(store_base, repo_key):
    d = os.path.join(store_base, repo_key, "grudges")
    out = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if name.endswith(".md"):
                out.append(os.path.join(d, name))
    return out


class TH_DOTFILES_ROUNDTRIP(unittest.TestCase):
    """T-h: byte-exact `$STATE_DIR/<sha>.files` round-trip + #606 renderer."""

    PAYLOADS = [
        b"a\tTAB.py",          # TAB
        b"b\nLF.py",            # LF
        b"c,m.py",             # COMMA
        b"d\\q.py",            # backslash
        b'e"q.py',            # double quote
        "caf\xe9.py".encode("utf-8"),   # non-ASCII, valid UTF-8
        b"bad\xe9.py",        # invalid UTF-8
    ]

    def test_roundtrips_byte_exact_and_never_rendered(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            sha = fx.add_fix_commit([p.decode("utf-8", "surrogateescape")
                                     for p in self.PAYLOADS])
            raw = _git_bytes(fx.repo, "diff-tree", "--root", "--no-commit-id",
                             "--name-only", "-r", "-z", sha)
            expected = sorted(b for b in raw.split(b"\0") if b)

            r = fx.run("sess-r4th")
            self.assertEqual(r.returncode, 2,
                             f"stdout={r.stdout!r} stderr={r.stderr!r}")

            files_path = os.path.join(fx.guard_dir, f"{sha}.files")
            self.assertTrue(os.path.isfile(files_path),
                            f"{files_path} was not written")
            with open(files_path, "rb") as fh:
                persisted = sorted(b for b in fh.read().split(b"\0") if b)
            self.assertEqual(
                expected, persisted,
                "byte-exact dot-files round trip (T-h): a delimited join or "
                "a Unicode-text-typed store would corrupt these paths")

            # #606 / §3.2 message content: no attacker path, in any form
            # (escaped or not), on the agent-facing block stderr.
            for bad in self.PAYLOADS:
                try:
                    text = bad.decode("utf-8", "surrogateescape")
                except Exception:  # pragma: no cover
                    continue
                self.assertNotIn(text, r.stderr,
                                 f"attacker path {text!r} rendered to stderr (T-h/#606)")


class TI_PREFILL_EXECUTES_AND_RECORDS(unittest.TestCase):
    """T-i: the paste-me --files-from remedy works under bash AND POSIX sh,
    records the grudge, and produces no code execution."""

    def test_prefill_executes_and_records_under_bash_and_sh(self):
        marker1 = os.path.join(tempfile.gettempdir(), "r4-pwn-bt")
        marker2 = os.path.join(tempfile.gettempdir(), "r4-pwn-cmd")
        for m in (marker1, marker2):
            if os.path.exists(m):
                os.unlink(m)

        payloads = [
            "src/`touch %s`.py" % marker1,          # backtick -> executes
            "src/$(touch %s).py" % marker2,          # $(...) -> executes
            "-lead.py",                               # leading dash
            "nl\nsep.py",                             # embedded newline
        ]
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            sha = fx.add_fix_commit(payloads)
            r = fx.run("sess-r4i")
            self.assertEqual(r.returncode, 2,
                             f"stdout={r.stdout!r} stderr={r.stderr!r}")

            # oracle (SIEGE-R2-H1/H2): no attacker-controlled free text appears
            # verbatim on the agent-facing stderr, in any form.
            for p in payloads:
                self.assertNotIn(p, r.stderr, f"prefill rendered path {p!r}")

            m = re.search(r'(?m)^[ \t]*(python3 .*--files-from="[^"]+"[ \t]+--candidate-sha=[^ ]+.*)$',
                          r.stderr)
            if m is None:
                self.fail(f"no --files-from prefill in stderr:\n{r.stderr}")
            cmd = m.group(1).strip()
            self.assertNotIn("src/`", cmd.replace("--files-from", ""))
            self.assertIn("--files-from=", cmd)
            self.assertIn(f"--candidate-sha=\"{sha}\"", cmd)

            # executes and records under bash
            self._assert_executes_and_records(fx, cmd, ("bash",), (marker1, marker2))
            # executes and records under a POSIX-sh-only shell
            posix = shutil.which("dash") or shutil.which("busybox") or "/bin/sh"
            self._assert_executes_and_records(fx, cmd, (posix,), (marker1, marker2))

    def _assert_executes_and_records(self, fx, cmd, shell, markers):
        for m in markers:
            if os.path.exists(m):
                os.unlink(m)
        proc = subprocess.run(list(shell) + ["-c", cmd],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=fx.env(),
                              cwd=fx.repo, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         f"{shell[0]} run failed: {proc.stdout!r} {proc.stderr!r}")
        for m in markers:
            self.assertFalse(os.path.exists(m),
                             f"code execution via filename in {shell[0]}!")
        grudges = _load_grudges(fx.store, fx.repo_key)
        self.assertTrue(grudges, "paste-me command did not record a grudge")
        recorded = set()
        for p in grudges:
            with open(p, "r", encoding="utf-8") as fh:
                text = fh.read()
            mm = re.search(r"^files_touched: (.*)$", text, re.M)
            if mm is not None:
                recorded.update(json.loads(mm.group(1)))
        for p in ("src/`touch %s`.py" % markers[0],
                  "src/$(touch %s).py" % markers[1],
                  "-lead.py", "nl\nsep.py"):
            self.assertIn(p, recorded,
                          f"{shell[0]}: grudge did not record {p!r}")


class TK_COMMMA_PATH_NO_INVENT_NO_DESTROY(unittest.TestCase):
    """T-k (#568): a comma-bearing path neither invents nor destroys a match."""

    def test_comma_path_roundtrips_end_to_end(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            # the fix commit touches a comma-bearing path and a plain one
            sha = fx.add_fix_commit(["a,b.py", "c.py"])
            r = fx.run("sess-r4k-block")
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")

            # persists byte-exact into the NUL-delimited .files artifact
            files_path = os.path.join(fx.guard_dir, f"{sha}.files")
            with open(files_path, "rb") as fh:
                persisted = [b.decode("utf-8", "surrogateescape")
                             for b in fh.read().split(b"\0") if b]
            self.assertIn("a,b.py", persisted,
                          "comma path split or destroyed on persistence")

            # record a grudge carrying the comma path via the append CLI
            env = fx.env()
            ap = subprocess.run(
                [sys.executable, GRUDGE_APPEND,
                 "--symptom", "comma path regressed",
                 "--files=a,b.py", "--files=c.py",
                 "--commit", sha,
                 "--repo-root", os.path.realpath(fx.repo),
                 "--repo", fx.repo_key],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=fx.repo, timeout=60,
            )
            self.assertEqual(ap.returncode, 0, f"stderr={ap.stderr!r}")

            # a grudge matching the REAL comma path clears the candidate
            r2 = fx.run("sess-r4k-clear")
            self.assertEqual(r2.returncode, 0,
                             f"comma-path grudge did not clear: {r2.stderr!r}")

    def test_query_comma_path_matches_exactly_one_side(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            _write_bytes(os.path.join(fx.repo, "a,b.py"), b"x\n")
            _write_bytes(os.path.join(fx.repo, "c.py"), b"x\n")
            _write_bytes(os.path.join(fx.repo, "d.py"), b"x\n")
            _git(fx.repo, "add", "-A")
            _git(fx.repo, "commit", "-qm", "chore: seed files")
            sha = _git_sha(fx.repo)

            env = fx.env()
            # write the grudge via the append() API with an explicit, dated
            # date_fixed on/before the candidate's author date (the CLI always
            # stamps today, which a 2026-01-02 candidate would reject).
            rec = subprocess.run(
                [sys.executable, "-c", (
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from scripts.grudge_append import append; "
                    "p = append(symptom='s', files_touched=['a,b.py','c.py'], "
                    "fixed_in_commit=sys.argv[2], repo=sys.argv[3], "
                    "repo_root=sys.argv[4], base_dir=sys.argv[5], "
                    "date_fixed='2026-01-01'); print(p or '')"
                ), REPO_ROOT, sha, fx.repo_key, os.path.realpath(fx.repo),
                   fx.store],
                capture_output=True, text=True, env=env, cwd=fx.repo, timeout=60,
            )
            self.assertEqual(rec.returncode, 0, f"append failed: {rec.stderr!r}")

            def q(*args):
                return subprocess.run(
                    [sys.executable, GRUDGE_QUERY, *args, "--candidate-sha", sha,
                     "--candidate-at", "1767225600", "--repo-root",
                     os.path.realpath(fx.repo), "--repo", fx.repo_key,
                     "--session-root", fx.repo],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env=env, cwd=fx.repo, timeout=60,
                ).stdout.strip()

            # the real comma path matches (not split, not destroyed)
            self.assertTrue(q("--by-files=a,b.py", "--by-files=c.py"))
            # the invented fragments match nothing
            self.assertFalse(q("--by-files=a", "--by-files=b.py"))


class TL_STATE_VERSION_DISCARD(unittest.TestCase):
    """T-l: an old-version state document is detected by `version`, discarded
    safely, rewritten fresh, and the discard does not produce a freeze."""

    def test_old_version_state_discarded_rewritten_no_freeze(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            sha = fx.add_fix_commit(["app.py"])
            r1 = fx.run("sess-r4l")
            self.assertEqual(r1.returncode, 2, f"stderr={r1.stderr!r}")
            self.assertIn("(1/3)", r1.stderr)
            self.assertTrue(os.path.isfile(
                os.path.join(fx.guard_dir, "sess-r4l.json")))

            # poison the state with an OLD-format document: no `version` (the
            # pre-R4 schema), carrying the five legacy fields.
            old = fx.state_json("sess-r4l")
            old.pop("version", None)
            old["sha_files"] = {sha: ["app.py"]}
            path = os.path.join(fx.guard_dir, "sess-r4l.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(old, fh)

            # R1+R2 (journal model): the discarded display doc is separate from
            # the journal, which IS the bound and SURVIVES the discard. The
            # journal already carries one BLOCK from Stop 1, so Stop 2 correctly
            # re-blocks at (2/3) — the counter is derivable from durable
            # evidence, never lost to a display-doc version discard.
            r2 = fx.run("sess-r4l")
            self.assertEqual(r2.returncode, 2, f"stderr={r2.stderr!r}")
            self.assertIn("(2/3)", r2.stderr,
                          "the journal (the bound) must survive a display-doc "
                          "version discard — T-l/a, a pre-R4 state file cannot "
                          "reset durable BLOCK history")

            fresh = fx.state_json("sess-r4l")
            self.assertEqual(fresh.get("version"), STATE_VERSION,
                             "state must be rewritten with the current version")
            self.assertNotIn("sha_files", fresh,
                             "sha_files must not exist as a JSON field (S-2)")
            self.assertTrue(os.path.isfile(
                os.path.join(fx.guard_dir, f"{sha}.files")))

            # the journal-anchored chain is still bounded: an old->new
            # alternation cannot freeze; the (2/3) chain gives up loudly.
            rcs = [r2.returncode]
            for _ in range(2):
                r = fx.run("sess-r4l")
                rcs.append(r.returncode)
            self.assertEqual(rcs, [2, 2, 0],  # (3/3) then give-up; (1/3) was Stop 1
                             f"bound broken after version discard: {rcs}")


class TN_BOUNDED_STATE_WRITES(unittest.TestCase):
    """T-n arms (.files / skips.log): a mkfifo'd target costs the bounded wait,
    never the hook's own timeout ceiling, and C-k degrades the message."""

    def test_mkfifo_dotfiles_write_is_bounded_and_degrades(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            sha = fx.add_fix_commit(["app.py"])
            os.makedirs(fx.guard_dir, exist_ok=True)
            os.mkfifo(os.path.join(fx.guard_dir, f"{sha}.files"))

            start = time.monotonic()
            r = fx.run("sess-r4nf")
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 15,
                            f"mkfifo'd .files write hung {elapsed:.1f}s (T-n "
                            f"arm .files) — the write must be time-bounded")
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            # C-k: the .files target was NOT a readable regular file, so the
            # --files-from remedy must not be printed.
            self.assertNotIn("--files-from", r.stderr,
                             "C-k: --files-from remedy must not be printed "
                             "for an unwritable .files target")

    def test_mkfifo_skipslog_write_is_bounded_and_degrades(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.add_fix_commit(["app.py"])
            os.makedirs(fx.guard_dir, exist_ok=True)
            os.mkfifo(os.path.join(fx.guard_dir, "skips.log"))

            start = time.monotonic()
            r = fx.run("sess-r4ns")
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 15,
                            f"mkfifo'd skips.log probe hung {elapsed:.1f}s "
                            f"(T-n arm skips.log) — probe must be time-bounded")
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            # C-k: the skips.log remedy must not be printed for an
            # unwritable skips.log; the _prefill (regular .files) survives.
            skips_echo = [l for l in r.stderr.splitlines()
                          if "skips.log" in l and ">>" in l]
            self.assertEqual(
                [], skips_echo,
                "C-k: skips.log remedy printed for an unwritable skips.log")


class TAA_CRAFTED_DOTFILES_KEY_REJECTED(unittest.TestCase):
    """T-aa (C-o): a `deadbeef[$(touch marker)]` key on disk is rejected by
    hex-only validation before it becomes a bash identifier; marker not made."""

    def test_crafted_dotfiles_name_is_rejected_no_execution(self):
        # the marker path is slash-free so the crafted NAME stays a single
        # filename component on disk (a `/` would split it into dirs and fail
        # the fixture for the wrong reason).
        marker = "R4MARKER_AA"
        marker_path = os.path.join(tempfile.gettempdir(), marker)
        if os.path.exists(marker_path):
            os.unlink(marker_path)
        crafted = "deadbeef[%s].files" % ("$(touch %s)" % marker)
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            sha = fx.add_fix_commit(["app.py"])
            r1 = fx.run("sess-r4aa")
            self.assertEqual(r1.returncode, 2, f"stderr={r1.stderr!r}")
            # plant the crafted key on disk BEFORE the load branch runs
            with open(os.path.join(fx.guard_dir, crafted), "wb") as fh:
                fh.write(b"injected\0")
            r2 = fx.run("sess-r4aa")
            self.assertFalse(os.path.exists(marker_path),
                             "crafted F_$sha name executed $(...) via nameref "
                             "build (C-o/T-aa) ")
            self.assertEqual(r2.returncode, 2,
                             f"Stop 2 broken by crafted .files key: {r2.stderr!r}")
            self.assertIn("(2/3)", r2.stderr,
                          "stop 2 must re-block with the persisted counter "
                          "(the crafted key must not corrupt grouping)")


EXPECTED_TESTS = 8


def _run_with_count_guard():
    result = unittest.main(exit=False, verbosity=2).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} R4 tests to execute, "
              f"ran {executed} — a test was skipped or dropped", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())