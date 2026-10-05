#!/usr/bin/env python3
"""Deterministic Warden regressions; inject clocks/failures, never long stalls."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from test_grudge_guard_journal import HookFixture

HOOK = ROOT / "hooks/grudge-resolution-guard.sh"


def functions(*names):
    text = HOOK.read_text()
    return "\n".join(re.search(r"^" + re.escape(n) + r"\(\) \{\n.*?^\}",
                               text, re.M | re.S).group() for n in names)


def shell(code):
    return subprocess.run(["bash", "-c", code], text=True, capture_output=True,
                          timeout=20)


class Warden(unittest.TestCase):
    def test_budget_preserves_already_decided_messages(self):
        for giveup in (False, True):
            with self.subTest(giveup=giveup), tempfile.TemporaryDirectory() as d:
                fx = HookFixture(d)
                fx.ensure_store()
                shas = [fx.commit([f"f{i}.py"]) for i in range(2)]
                os.makedirs(fx.guard_dir, exist_ok=True)
                if giveup:
                    Path(fx.guard_dir, "sess.journal").write_text("".join(
                        f"1\tBLOCK\t{s}\t{n:016x}\n" for s in shas for n in range(3)))
                # Deterministic deadline: expires once any group decided a verdict.
                text = re.sub(r"^_budget_ok\(\) \{\n.*?^\}", '''_budget_ok() {
  [ "${#BLOCKING[@]}" -eq 0 ] && [ "${#GIVEUP_SHAS[@]}" -eq 0 ]
}''', HOOK.read_text(), count=1, flags=re.M | re.S)
                copy = Path(d, "hook.sh")
                copy.write_text(text)
                r = subprocess.run(["bash", str(copy)], input=fx.payload("sess"),
                                   text=True, capture_output=True, cwd=fx.repo,
                                   env=fx.env(), timeout=20)
                self.assertEqual(r.returncode, 0 if giveup else 2, r.stderr)
                self.assertIn("giving up" if giveup else "blocked", r.stderr)
                self.assertIn("budget", r.stderr)
                self.assertFalse(Path(fx.guard_dir, "sess.json").exists(),
                                 "budget-limited pass must not advance checkpoint")

    def test_failed_giveup_matches_journal_witness_and_message(self):
        for succeeds in (0, 1):
            with self.subTest(successful_appends=succeeds), tempfile.TemporaryDirectory() as d:
                fx = HookFixture(d)
                fx.ensure_store()
                shas = [fx.commit(["shared.py"]) for _ in range(2)]
                os.makedirs(fx.guard_dir, exist_ok=True)
                journal = Path(fx.guard_dir, "sess.journal")
                journal.write_text("".join(f"1\tBLOCK\t{s}\t{n:016x}\n"
                                          for s in shas for n in range(3)))
                # Fail real journal writes after zero/one successful GIVEUP rows.
                text = HOOK.read_text().replace('_record_line() {',
                    '_record_line() {\n'
                    '  if [ "$1" = GIVEUP ]; then\n'
                    f'    [ "${{giveup_writes:-0}}" -lt {succeeds} ] || return 1\n'
                    '    giveup_writes=$(( ${giveup_writes:-0} + 1 ))\n'
                    '  fi')
                copy = Path(d, "hook.sh")
                copy.write_text(text)
                r = subprocess.run(["bash", str(copy)], input=fx.payload("sess"),
                    text=True, capture_output=True, cwd=fx.repo, env=fx.env(), timeout=20)
                self.assertEqual(r.returncode, 0, r.stderr)
                rows = journal.read_text().splitlines()
                retired = {row.split("\t")[2] for row in rows if "\tGIVEUP\t" in row}
                self.assertEqual(len(retired), succeeds)
                witness = Path(fx.home, ".claude/crucible/grudge-guard/outcomes.tsv")
                self.assertNotIn("\tGIVEUP\t", witness.read_text() if witness.exists() else "")
                self.assertNotIn("giving up after", r.stderr)
                self.assertIn("retirement incomplete", r.stderr)
                for sha in set(shas) - retired:
                    self.assertIn(sha, r.stderr)

    def test_oversized_active_mapped_artifact_advances_on_repeated_stops(self):
        with tempfile.TemporaryDirectory() as d:
            fx = HookFixture(d)
            fx.ensure_store()
            sha = fx.commit(["app.py"])
            first = fx.run("sess")
            self.assertEqual(first.returncode, 2, first.stderr)
            state = Path(fx.guard_dir, "sess.json")
            self.assertIn(sha, state.read_text())
            # A mapped, still-in-scope artifact used to restart its 2000-path
            # scan at the first record each Stop. Git owns immutable commit
            # paths, so this oversized stale cache need not be read at all.
            Path(fx.guard_dir, f"{sha}.files").write_bytes(b"unneeded.py\0" * 2000)
            text = re.sub(r"^_budget_ok\(\) \{\n.*?^\}", '''_budget_ok() {
  budget_calls=$(( ${budget_calls:-0} + 1 ))
  [ "$budget_calls" -lt 150 ]
}''', HOOK.read_text(), count=1, flags=re.M | re.S)
            copy = Path(d, "hook.sh")
            copy.write_text(text)
            for attempt in (2, 3):
                r = subprocess.run(["bash", str(copy)], input=fx.payload("sess", True),
                    text=True, capture_output=True, cwd=fx.repo, env=fx.env(), timeout=20)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn(f"({attempt}/3)", r.stderr)
                self.assertNotIn("budget", r.stderr)
                self.assertTrue(state.exists())

    def test_real_oversized_candidate_retires_loudly_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            fx = HookFixture(d)
            fx.ensure_store()
            sha = fx.commit([f"wide/{i}.py" for i in range(4200)])
            copy = Path(d, "hook.sh")
            copy.write_text(HOOK.read_text())
            for attempt in range(2):
                r = subprocess.run(["bash", str(copy)], input=fx.payload("sess"),
                    text=True, capture_output=True, cwd=fx.repo,
                    env=fx.env(CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS="20"), timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertNotIn("budget", r.stderr)
                self.assertEqual(json.loads(Path(fx.guard_dir, "sess.json").read_text())
                                 ["last_checked_sha"], sha)
                if attempt == 0:
                    self.assertIn("too many paths", r.stderr)
                    self.assertIn("NOT enforced", r.stderr)
                else:
                    self.assertNotIn("too many paths", r.stderr,
                                     "second Stop should not restart the same candidate")

    def test_oversized_retired_mapped_artifact_does_not_starve_new_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            fx = HookFixture(d)
            fx.ensure_store()
            sha = fx.commit([f"old/{i}.py" for i in range(150)])
            first = fx.run("sess")
            self.assertEqual(first.returncode, 2, first.stderr)
            state = Path(fx.guard_dir, "sess.json")
            artifact = Path(fx.guard_dir, f"{sha}.files")
            self.assertEqual(artifact.read_bytes().count(b"\0"), 150)
            # The mapped SHA remains in state but is durably retired and out of
            # the scan range. Only the new, small commit needs path hydration.
            fx.add_skip(sha)
            cleared = fx.run("sess", True)
            self.assertEqual(cleared.returncode, 0, cleared.stderr)
            new_sha = fx.commit(["old/149.py"])
            self.assertIn(sha, state.read_text())
            text = re.sub(r"^_budget_ok\(\) \{\n.*?^\}", '''_budget_ok() {
  budget_calls=$(( ${budget_calls:-0} + 1 ))
  [ "$budget_calls" -lt 90 ]
}''', HOOK.read_text(), count=1, flags=re.M | re.S)
            copy = Path(d, "hook.sh")
            copy.write_text(text)
            for attempt in (1, 2):
                r = subprocess.run(["bash", str(copy)], input=fx.payload("sess", True),
                    text=True, capture_output=True, cwd=fx.repo, env=fx.env(), timeout=20)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn(f"({attempt}/3)", r.stderr)
                self.assertNotIn("budget", r.stderr)
                groups = json.loads(state.read_text())["sha_group"]
                self.assertEqual(groups[new_sha], groups[sha],
                                 "lazy overlap must preserve historical group identity")

    def test_giveup_reads_once(self):
        r = shell(functions("_giveup_loud", "_journal_read") + '''
MAX_BLOCKS=3; passes=0; declare -A GIVEUP_SHAS=() LAST_BLOCK_NONCE=() JB=()
_journal_pass() { echo pass >> "$trace"; JR_ABSENT=0; JR_UNMEASURABLE=0; JR_BUDGET=0; JB[a]=3; JB[b]=3; }
_journal_append_group() { :; }
_witness_outcome() { :; }
trace=$(mktemp); trap 'rm -f "$trace"' EXIT
_giveup_loud group a b
wc -l < "$trace"
''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "1")

    def test_append_stops_when_budget_expires(self):
        r = shell(functions("_journal_append_group") + '''
attempts=0
_budget_ok() { [ "$attempts" -lt 1 ]; }
_record_line() { attempts=$((attempts+1)); return 0; }
_journal_append_group BLOCK aaaaaaaaaaaaaaaa a b c
printf '%s %s' "$attempts" "$APPEND_OK"
''')
        self.assertEqual(r.stdout, "1 0", r.stderr)

    def test_failed_append_stops_batch(self):
        r = shell(functions("_journal_append_group") + '''
attempts=0
_budget_ok() { return 0; }
_record_line() { attempts=$((attempts+1)); return 1; }
_journal_append_group BLOCK aaaaaaaaaaaaaaaa a b c
printf '%s %s' "$attempts" "$APPEND_OK"
''')
        self.assertEqual(r.stdout, "1 0", r.stderr)

    def test_skips_probe_once_per_stop(self):
        with tempfile.TemporaryDirectory() as d:
            fx = HookFixture(d)
            fx.ensure_store()
            for i in range(3):
                fx.commit([f"f{i}.py"])
            # Count the actual probe function without changing its result.
            copy = Path(d, "hook.sh")
            copy.write_text(HOOK.read_text().replace('_skips_probe_ok() {',
                '_skips_probe_ok() {\n  echo probe >> "$PROBE_TRACE"'))
            trace = Path(d, "probes")
            r = subprocess.run(["bash", str(copy)], input=fx.payload("sess"),
                text=True, capture_output=True, cwd=fx.repo,
                env=fx.env(PROBE_TRACE=str(trace)), timeout=20)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertEqual(len(trace.read_text().splitlines()), 1)

    def test_load_only_requested_sha_from_git(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "aaaaaaaa.files").write_bytes(b"needed.py\0")
            Path(d, "bbbbbbbb.files").write_bytes(b"other-session.py\0")
            r = shell(functions("_load_files", "_sha_key_ok", "_sha_array_set") + f'''
STATE_DIR={d!r}; SESSION_ROOT={d!r}; declare -A SHA_GROUP=([aaaaaaaa]=aaaaaaaa)
_budget_ok() {{ return 0; }}
_budget_out() {{ exit 99; }}
_git() {{ printf 'needed.py\\0'; }}
_load_files aaaaaaaa
declare -p F_aaaaaaaa
declare -p F_bbbbbbbb 2>/dev/null && exit 1
exit 0
''')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("needed.py", r.stdout)
            self.assertNotIn("other-session.py", r.stdout)

    def test_journal_read_stops_at_budget_without_partial_retirement(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "journal")
            p.write_text("1\tCLEAR\taaaa\n" + "1\tBLOCK\tbbbb\taaaaaaaa\n" * 1000)
            r = shell(functions("_journal_pass") + f'''
JOURNAL_FILE={str(p)!r}; JOURNAL_QUARANTINE_LINES=50000
calls=0
_budget_ok() {{ calls=$((calls+1)); [ "$calls" -lt 2 ]; }}
_journal_pass
printf '%s %s %s' "${{JR_BUDGET:-0}}" "${{#JBLAST[@]}}" "$calls"
''')
            self.assertEqual(r.stdout, "1 0 2", r.stderr)

    def test_state_keys_validated_before_nameref(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "state.json")
            p.write_text('{"sha_group":{"aaaa[1]":"bbbb","cccc":"bad[group]","dddd":"eeee"}}')
            r = shell(functions("_load_maps", "_sha_key_ok") + f'''
STATE_FILE={str(p)!r}; declare -A SHA_GROUP=() BLOCK_COUNTS=()
_load_files() {{ :; }}
_load_maps
printf '%s' "${{!SHA_GROUP[*]}}"
''')
            self.assertEqual(r.stdout, "dddd", r.stderr)

    def test_overlap_has_linear_work(self):
        # Count WORK, not one command's spelling. `comparisons()` used to sum
        # only `+ '['` lines, so the same number of real comparisons written as
        # `[[ "$a" == "$b" ]]` (traced as `+ [[`) scored 0 and the fence went
        # green on a quadratic _overlap. Count every test/comparison command
        # either way, plus the _seen hash writes, which are the other half of
        # the per-path work.
        def work(n):
            r = shell(functions("_overlap", "_sha_array_has") + f'''
_budget_ok() {{ return 0; }}
_budget_out() {{ exit 99; }}
_git() {{ echo 'unexpected git fallback' >&2; exit 98; }}
F_aaaa=(); F_bbbb=()
for ((i=0;i<{n};i++)); do F_aaaa+=("a$i"); F_bbbb+=("b$i"); done
set -x
_overlap aaaa bbbb
''')
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertNotIn('unexpected git fallback', r.stderr)
            commands = sum(line.startswith("+ '['") or line.startswith("+ [[")
                           for line in r.stderr.splitlines())
            writes = sum("_seen[" in line for line in r.stderr.splitlines())
            return commands + writes
        # Measured on HEAD: 62 at n=20, 122 at n=40, 182 at n=60 — exactly 3
        # per path plus a constant of 2. The bound is per-PATH and absolute,
        # not a ratio: a 2x ratio cannot see a constant-factor slowdown by
        # construction ((40k+c)/(20k+c) < 2 for every k), so doubling the
        # per-element cost is invisible. 5 units per path leaves ~65% headroom
        # over the measured 3.0, while a nested-loop _overlap costs n*n and
        # blows through it from the first path.
        measured = {n: work(n) for n in (20, 40, 60)}
        for n, w in measured.items():
            self.assertLessEqual(w, 5 * n,
                                 f"{n} paths must cost O(n), not O(n^2)")
        self.assertGreater(measured[20], 0, "trace must observe array comparisons")
        # The absolute bound still shares slack with a fixed per-call overhead.
        # Bound the SLOPE too, which cancels every constant term: no fixed
        # number of extra operations can move it, only extra work per path.
        # 3.5 per path is 17% above the measured 3.0 and far below the n^2
        # mutant, so it sees a constant factor on any single unit of the
        # per-element work that the 5n bound lets through.
        slope = (measured[60] - measured[20]) / 40
        self.assertLessEqual(slope, 3.5,
                             f"per-path cost grew to {slope} (measured "
                             f"{measured[20]}@20, {measured[60]}@60)")

    def test_pass_count_premise_uses_child_status(self):
        text = (ROOT / "hooks/tests/test-grudge-resolution-guard.sh").read_text()
        # Replay the actual caller with a helper returning ALLOW, after a prior
        # successful BLOCK: a subshell cannot update the caller's stale RC.
        start = text.index('T28P2=')
        end = text.index('check 388', start)
        r = shell('RC=2\nt28_passes() { RC=0; T28_PASSES=6; echo 6; }\n'
                  + text[start:end] + '\nprintf "status=%s" "$T28P12_RC"')
        self.assertTrue(r.stdout.endswith("status=0"), r.stdout + r.stderr)

    def test_malformed_journal_does_not_publish_partial_retirement(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "journal")
            p.write_text("1\tCLEAR\taaaa\nmalformed\n")
            r = shell(functions("_journal_pass") + f'''
JOURNAL_FILE={str(p)!r}; JOURNAL_QUARANTINE_LINES=50000
_budget_ok() {{ return 0; }}
_journal_pass
printf '%s %s' "$JR_UNMEASURABLE" "${{#JBLAST[@]}}"
''')
            self.assertEqual(r.stdout, "1 0", r.stderr)


EXPECTED_TESTS = 15


def _run_with_count_guard():
    # A test method can be deleted without any other test noticing, so the
    # count is pinned the way the sibling journal suite pins its own
    # (#581/#603 fences were bypassed exactly this way once already). A named
    # run (sys.argv) is exempt so the bash carrier can address one test.
    result = unittest.main(exit=False, verbosity=2).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} warden tests, "
              f"ran {executed}", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())
