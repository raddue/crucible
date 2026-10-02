#!/usr/bin/env python3
"""Deterministic Warden regressions; inject clocks/failures, never long stalls."""
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

    def test_load_only_session_members(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "aaaaaaaa.files").write_bytes(b"needed.py\0")
            Path(d, "bbbbbbbb.files").write_bytes(b"other-session.py\0")
            r = shell(functions("_load_files", "_sha_key_ok", "_sha_array_set") + f'''
STATE_DIR={d!r}; declare -A SHA_GROUP=([aaaaaaaa]=aaaaaaaa)
_budget_ok() {{ return 0; }}
_budget_out() {{ exit 99; }}
_load_files
declare -p F_aaaaaaaa
declare -p F_bbbbbbbb 2>/dev/null && exit 1
exit 0
''')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("needed.py", r.stdout)

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
        def comparisons(n):
            r = shell(functions("_overlap") + f'''
_budget_ok() {{ return 0; }}
_budget_out() {{ exit 99; }}
F_aaaa=(); F_bbbb=()
for ((i=0;i<{n};i++)); do F_aaaa+=("a$i"); F_bbbb+=("b$i"); done
set -x
_overlap aaaa bbbb
''')
            self.assertEqual(r.returncode, 1, r.stderr)
            return sum(line.startswith('+ [ ') for line in r.stderr.splitlines())
        self.assertLessEqual(comparisons(40), 2 * comparisons(20))

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


if __name__ == "__main__":
    unittest.main()
