#!/usr/bin/env bash
# hooks/tests/test-grudge-resolution-guard.sh
# Test suite for the #559 grudge-resolution Stop-hook seam.
#
# The Stop hook itself lives at hooks/grudge-resolution-guard.sh; later tasks
# add its scenarios to THIS file. Task 6's cases below exercise only the seam it
# consumes — `python3 scripts/grudge_query.py --by-commit / --by-files` — as a
# subprocess with HOME and CRUCIBLE_GRUDGE_DIR redirected into a temp tree, so
# no real machine state is ever read or written.
#
# Every scenario carries its contract invariant tag on the marker comment above
# it (with `checks=N`, N = the number of `check` calls in that scenario's block)
# and on each of its check names.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QUERY="$REPO_ROOT/scripts/grudge_query.py"

PASSED=0
FAILED=0
TOTAL=0

# ── Setup temp tree ─────────────────────────────────────────────────────
TMPROOT="$(mktemp -d)"
FAKE_HOME="$TMPROOT/fakehome"

cleanup() {
  # LOAD-BEARING: the exit-3 fixtures leave mode-000 store directories behind
  # and `rm -rf` cannot descend into them. Without the restore the suite leaks
  # the tmp tree AND exits 1 with every check passing.
  chmod -R u+rwX "$TMPROOT" 2>/dev/null || true
  rm -rf "$TMPROOT"
}
trap cleanup EXIT

mkdir -p "$FAKE_HOME"
export HOME="$FAKE_HOME"

# ── Helpers ─────────────────────────────────────────────────────────────
# String-equality check (rc values compare fine as strings, and stdout/stderr
# assertions need the same reporting), reported in the house PASS/FAIL style.
check() {
  local test_num="$1"
  local test_name="$2"
  local expected="$3"
  local actual="$4"

  TOTAL=$((TOTAL + 1))
  if [ "$actual" = "$expected" ]; then
    echo "Test $test_num: $test_name... PASS"
    PASSED=$((PASSED + 1))
  else
    echo "Test $test_num: $test_name... FAIL (expected [$expected], got [$actual])"
    FAILED=$((FAILED + 1))
  fi
}

new_repo() {
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init -q -b main
  git -C "$d" config user.name "Grudge Seam Test"
  git -C "$d" config user.email "grudge-seam@test.invalid"
  git -C "$d" config commit.gpgsign false
}

commit_all() {
  # commit_all <repo> <message> [author-date]
  local d="$1" msg="$2" when="${3:-2026-05-01T09:00:00+00:00}"
  git -C "$d" add -A
  GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
    git -C "$d" commit -q -m "$msg"
}

at_of() { git -C "$1" log -1 --format=%at "$2"; }
sha_of() { git -C "$1" rev-parse "$2"; }

stem_of() { local p="${1##*/}"; echo "${p%.md}"; }

append_grudge() {
  # append_grudge <base_dir> <repo> <repo_root> <symptom> <files-csv> <commit> <date_fixed>
  local out
  out="$(python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from scripts.grudge_append import append
base, repo, root, symptom, files, commit, date_fixed = sys.argv[2:9]
p = append(symptom=symptom, files_touched=files.split(","),
           fixed_in_commit=commit, repo=repo, repo_root=root,
           base_dir=base, date_fixed=(date_fixed or None))
print(p or "")
' "$REPO_ROOT" "$1" "$2" "$3" "$4" "$5" "$6" "$7")"
  if [ -z "$out" ]; then
    echo "FIXTURE ERROR: append() refused to write a grudge for $2" >&2
    exit 1
  fi
  echo "$out"
}

QUERY_TZ=""
run_query() {
  # run_query <store_base> <args...>; sets OUT / ERR / RC
  local store="$1"; shift
  set +e
  OUT="$(env HOME="$FAKE_HOME" CRUCIBLE_GRUDGE_DIR="$store" \
    ${QUERY_TZ:+TZ="$QUERY_TZ"} \
    python3 "$QUERY" "$@" 2>"$TMPROOT/last-stderr.txt")"
  RC=$?
  set -e
  ERR="$(cat "$TMPROOT/last-stderr.txt")"
}

has() {
  # has <haystack> <needle> -> "yes"/"no"
  case "$1" in *"$2"*) echo "yes" ;; *) echo "no" ;; esac
}

nonempty() { if [ -n "$1" ]; then echo "yes"; else echo "no"; fi; }

# ========================================================================
# INV-T15 — exact fixed_in_commit match via --by-commit
# ========================================================================
# contract:match:inv-t15 checks=4
R1="$TMPROOT/r15"; new_repo "$R1"; R1="$(cd "$R1" && pwd -P)"
echo "print('v0')" > "$R1/app.py"
commit_all "$R1" "base"
echo "print('v1')" >> "$R1/app.py"
commit_all "$R1" "fix(app): patch the widget"
C15="$(sha_of "$R1" HEAD)"
C15_SHORT="$(git -C "$R1" rev-parse --short=7 HEAD)"

S15A="$TMPROOT/store15a"
P15A="$(append_grudge "$S15A" k15a "$R1" "widget exploded" "app.py" "$C15_SHORT" "2026-05-01")"
run_query "$S15A" --by-commit "$C15" --repo-root "$R1" --repo k15a --session-root "$R1"
check 1 "full 40-char SHA matches stored 7-char abbrev, rc — contract:match:inv-t15" 0 "$RC"
check 2 "full 40-char SHA matches stored 7-char abbrev, stem — contract:match:inv-t15" "$(stem_of "$P15A")" "$OUT"

S15B="$TMPROOT/store15b"
append_grudge "$S15B" k15b "$R1" "pruned commit grudge" "app.py" \
  "deadbeef00000000000000000000000000000000" "2026-05-01" >/dev/null
run_query "$S15B" --by-commit "$C15" --repo-root "$R1" --repo k15b --session-root "$R1"
check 3 "unresolvable stored SHA is a miss not an error, rc — contract:match:inv-t15" 0 "$RC"
check 4 "unresolvable stored SHA is a miss not an error, stdout — contract:match:inv-t15" "" "$OUT"

# ========================================================================
# INV-T16 — >=2-survivor subset + UTC date monotonicity
# ========================================================================
# contract:match:inv-t16 checks=13
R2="$TMPROOT/r16"; new_repo "$R2"; R2="$(cd "$R2" && pwd -P)"
for f in a.py b.py c.py zz.py; do echo "v0 # $f" > "$R2/$f"; done
commit_all "$R2" "base" "2026-04-01T09:00:00+00:00"
for f in a.py b.py c.py; do echo "v1 # $f" >> "$R2/$f"; done
commit_all "$R2" "fix(core): repair a, b and c" "2026-06-01T12:00:00+00:00"
C16="$(sha_of "$R2" HEAD)"
AT16="$(at_of "$R2" HEAD)"

# (a) survivors subset of candidate files, date_fixed before candidate -> match
S16A="$TMPROOT/store16a"
P16A="$(append_grudge "$S16A" k16a "$R2" "a and b regressed together" "a.py,b.py" "" "2026-05-15")"
run_query "$S16A" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16a --session-root "$R2"
check 5 "2-file subset with earlier date_fixed matches, rc — contract:match:inv-t16" 0 "$RC"
check 6 "2-file subset with earlier date_fixed matches, stem — contract:match:inv-t16" "$(stem_of "$P16A")" "$OUT"

# (b) 30+ days old, still date_fixed-before the candidate -> STILL matches
S16B="$TMPROOT/store16b"
P16B="$(append_grudge "$S16B" k16b "$R2" "ancient a/b regression" "a.py,b.py" "" "2026-01-05")"
run_query "$S16B" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16b --session-root "$R2"
check 7 "grudge 5 months old is not time-bounded, rc — contract:match:inv-t16" 0 "$RC"
check 8 "grudge 5 months old is not time-bounded, stem — contract:match:inv-t16" "$(stem_of "$P16B")" "$OUT"

# (c) partial overlap (grudge names zz.py, untouched by the candidate) -> no match
S16C="$TMPROOT/store16c"
append_grudge "$S16C" k16c "$R2" "a and zz regressed together" "a.py,zz.py" "" "2026-05-15" >/dev/null
run_query "$S16C" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16c --session-root "$R2"
check 9 "intersection without subset does not match, rc — contract:match:inv-t16" 0 "$RC"
check 10 "intersection without subset does not match, stdout — contract:match:inv-t16" "" "$OUT"

# (d) date_fixed AFTER the candidate author date -> no match
S16D="$TMPROOT/store16d"
append_grudge "$S16D" k16d "$R2" "a and b fixed after the candidate" "a.py,b.py" "" "2026-06-02" >/dev/null
run_query "$S16D" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16d --session-root "$R2"
check 11 "date_fixed after candidate does not match, rc — contract:match:inv-t16" 0 "$RC"
check 12 "date_fixed after candidate does not match, stdout — contract:match:inv-t16" "" "$OUT"

# (e) late-evening commit in a negative UTC offset: local 06-29, UTC 06-30.
#     Run under a non-UTC TZ so a regression to local rendering is discriminated
#     on any host (on a UTC host both renderings agree and the case is vacuous).
echo "v2 # a" >> "$R2/a.py"; echo "v2 # b" >> "$R2/b.py"
commit_all "$R2" "fix(core): late evening in PDT" "2026-06-29T17:30:00-07:00"
C16E="$(sha_of "$R2" HEAD)"
AT16E="$(at_of "$R2" HEAD)"
S16E="$TMPROOT/store16e"
P16E="$(append_grudge "$S16E" k16e "$R2" "utc boundary regression" "a.py,b.py" "" "2026-06-30")"
QUERY_TZ="America/Los_Angeles"
run_query "$S16E" --by-files "a.py,b.py" --candidate-sha "$C16E" --candidate-at "$AT16E" \
  --repo-root "$R2" --repo k16e --session-root "$R2"
QUERY_TZ=""
check 13 "author date compared in UTC not local time, rc — contract:match:inv-t16" 0 "$RC"
check 14 "author date compared in UTC not local time, stem — contract:match:inv-t16" "$(stem_of "$P16E")" "$OUT"

# (f) three malformed hand-written records that MUST be reached before the valid
#     one: each carries a realpath-matching repo_root (else load_grudges drops it
#     silently), each date_fixed record names >=2 existing files that subset the
#     candidate (else survivors() never reaches the >=2 branch), and all are
#     named `0-*` so sorted(os.listdir) examines them before the hex stem.
S16F="$TMPROOT/store16f"
P16F="$(append_grudge "$S16F" k16f "$R2" "valid record behind the malformed ones" "a.py,b.py" "" "2026-05-15")"
G16F="$S16F/k16f/grudges"
cat > "$G16F/0-nodate.md" <<EOF
---
schema: 1
hash: 0nodate000000
repo: k16f
repo_root: $R2
fixed_in_commit:
symptom: hand-written record with the date key absent
root_cause:
files_touched: ["a.py", "b.py"]
anti_pattern_signature: ""
---
## Repro

## Why this kept happening

EOF
cat > "$G16F/0-baddate.md" <<EOF
---
schema: 1
hash: 0baddate0000
repo: k16f
repo_root: $R2
fixed_in_commit:
symptom: hand-written record with an unparseable date
root_cause:
files_touched: ["a.py", "b.py"]
anti_pattern_signature: ""
date_fixed: not-a-date
---
## Repro

## Why this kept happening

EOF
cat > "$G16F/0-badfiles.md" <<EOF
---
schema: 1
hash: 0badfiles000
repo: k16f
repo_root: $R2
fixed_in_commit:
symptom: hand-written record whose file list is a bare integer
root_cause:
files_touched: 5
anti_pattern_signature: ""
date_fixed: 2026-05-15
---
## Repro

## Why this kept happening

EOF
run_query "$S16F" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16f --session-root "$R2"
check 15 "malformed records are silent misses not exit 3, rc — contract:match:inv-t16" 0 "$RC"
check 16 "malformed records are silent misses not exit 3, stem — contract:match:inv-t16" "$(stem_of "$P16F")" "$OUT"
check 17 "all four records actually loaded (scanned=4) — contract:match:inv-t16" yes "$(has "$ERR" "scanned=4")"

# ========================================================================
# INV-T17 — ==1-survivor structural (patch-id) match
# ========================================================================
# contract:match:inv-t17 checks=4
R3="$TMPROOT/r17"; new_repo "$R3"; R3="$(cd "$R3" && pwd -P)"
echo "v0" > "$R3/feat.py"
commit_all "$R3" "base" "2026-04-01T09:00:00+00:00"
git -C "$R3" checkout -q -b topic
echo "v1-topic" > "$R3/feat.py"
commit_all "$R3" "fix(feat): the real fix" "2026-05-02T09:00:00+00:00"
S17="$(sha_of "$R3" HEAD)"
git -C "$R3" checkout -q main
git -C "$R3" checkout -q -b other
echo "v2-other" > "$R3/feat.py"
commit_all "$R3" "fix(feat): a different change to the same file" "2026-05-03T09:00:00+00:00"
D17="$(sha_of "$R3" HEAD)"
git -C "$R3" checkout -q main
git -C "$R3" merge --squash -q topic >/dev/null
commit_all "$R3" "fix(feat): squashed onto main" "2026-06-01T12:00:00+00:00"
C17="$(sha_of "$R3" HEAD)"
AT17="$(at_of "$R3" HEAD)"

S17A="$TMPROOT/store17a"
P17A="$(append_grudge "$S17A" k17a "$R3" "feat broke on launch" "feat.py" "$S17" "2026-05-02")"
run_query "$S17A" --by-files "feat.py" --candidate-sha "$C17" --candidate-at "$AT17" \
  --repo-root "$R3" --repo k17a --session-root "$R3"
check 18 "squashed rewrite matches by patch-id, rc — contract:match:inv-t17" 0 "$RC"
check 19 "squashed rewrite matches by patch-id, stem — contract:match:inv-t17" "$(stem_of "$P17A")" "$OUT"

S17B="$TMPROOT/store17b"
append_grudge "$S17B" k17b "$R3" "coincidental filename only" "feat.py" "$D17" "2026-05-03" >/dev/null
run_query "$S17B" --by-files "feat.py" --candidate-sha "$C17" --candidate-at "$AT17" \
  --repo-root "$R3" --repo k17b --session-root "$R3"
check 20 "same filename with a different patch does not match, rc — contract:match:inv-t17" 0 "$RC"
check 21 "same filename with a different patch does not match, stdout — contract:match:inv-t17" "" "$OUT"

# ========================================================================
# INV-T25 — store-root / session-root split
# ========================================================================
# contract:worktree:inv-t25 checks=16
R4="$TMPROOT/r25"; new_repo "$R4"; R4="$(cd "$R4" && pwd -P)"
for f in x.py y.py z.py; do echo "v0 # $f" > "$R4/$f"; done
commit_all "$R4" "base" "2026-04-01T09:00:00+00:00"
echo "v1 # x" >> "$R4/x.py"
commit_all "$R4" "fix(x): repair x" "2026-06-01T12:00:00+00:00"
C25="$(sha_of "$R4" HEAD)"
S25="$TMPROOT/store25"
append_grudge "$S25" k25 "$R4" "x regressed" "x.py" "$C25" "2026-05-01" >/dev/null
append_grudge "$S25" k25 "$R4" "y regressed" "y.py" "" "2026-05-01" >/dev/null
append_grudge "$S25" k25 "$R4" "z regressed" "z.py" "" "2026-05-01" >/dev/null

run_query "$S25" --by-commit "$C25" --repo-root "$R4/.git" --repo k25 --session-root "$R4"
check 22 ".git dir as store root filters every record out — contract:worktree:inv-t25" yes "$(has "$ERR" "scanned=0 matched=0")"
run_query "$S25" --by-commit "$C25" --repo-root "$R4" --repo k25 --session-root "$R4"
check 23 "dirname'd checkout root sees all three records — contract:worktree:inv-t25" yes "$(has "$ERR" "scanned=3 matched=1")"

R5="$TMPROOT/r25wt"; new_repo "$R5"; R5="$(cd "$R5" && pwd -P)"
echo "v0" > "$R5/feat.py"
commit_all "$R5" "base" "2026-04-01T09:00:00+00:00"
git -C "$R5" branch wt
git -C "$R5" checkout -q -b topic
echo "v1" > "$R5/feat.py"
commit_all "$R5" "fix(feat): the fix" "2026-05-02T09:00:00+00:00"
S25WT="$(sha_of "$R5" HEAD)"
git -C "$R5" checkout -q main
git -C "$R5" merge -q --ff-only topic
git -C "$R5" checkout -q wt
git -C "$R5" merge --squash -q topic >/dev/null
commit_all "$R5" "fix(feat): squashed on the worktree branch" "2026-06-01T12:00:00+00:00"
C25WT="$(sha_of "$R5" HEAD)"
AT25WT="$(at_of "$R5" HEAD)"
git -C "$R5" checkout -q main
W25="$TMPROOT/r25wt-linked"
git -C "$R5" worktree add -q "$W25" wt
W25="$(cd "$W25" && pwd -P)"
S25B="$TMPROOT/store25b"
P25B="$(append_grudge "$S25B" k25b "$R5" "feat regressed in the worktree" "feat.py" "$S25WT" "2026-05-02")"

run_query "$S25B" --by-files "feat.py" --candidate-sha "$C25WT" --candidate-at "$AT25WT" \
  --repo-root "$R5" --repo k25b --session-root "$W25"
check 24 "session-root worktree resolves HEAD for the match, rc — contract:worktree:inv-t25" 0 "$RC"
check 25 "session-root worktree resolves HEAD for the match, stem — contract:worktree:inv-t25" "$(stem_of "$P25B")" "$OUT"
run_query "$S25B" --by-files "feat.py" --candidate-sha "$C25WT" --candidate-at "$AT25WT" \
  --repo-root "$R5" --repo k25b --session-root "$R5"
check 26 "other worktree's HEAD makes the stored fix an ancestor, rc — contract:worktree:inv-t25" 0 "$RC"
check 27 "other worktree's HEAD makes the stored fix an ancestor, stdout — contract:worktree:inv-t25" "" "$OUT"

# (c) survivors() binds to --session-root, not to --repo-root. wt-only.py exists
#     ONLY in the linked worktree, so the same grudge has 2 survivors under
#     $W25 (-> the >=2 subset branch, which matches) and 1 under $R5 (-> the
#     structural branch). fixed_in_commit is empty, so the structural branch can
#     never match: a survivors() bound to --repo-root takes it under $W25 too
#     and loses the match.
echo "v0 # wt-only" > "$W25/wt-only.py"
commit_all "$W25" "feat(wt): a file only the linked worktree has" "2026-06-02T12:00:00+00:00"
C25WTO="$(sha_of "$W25" HEAD)"
AT25WTO="$(at_of "$W25" HEAD)"
S25C="$TMPROOT/store25c"
P25C="$(append_grudge "$S25C" k25c "$R5" "feat and the worktree-only file regressed" "feat.py,wt-only.py" "" "2026-05-02")"

run_query "$S25C" --by-files "feat.py,wt-only.py" --candidate-sha "$C25WTO" --candidate-at "$AT25WTO" \
  --repo-root "$R5" --repo k25c --session-root "$W25"
check 28 "survivors() sees the worktree-only file (>=2 subset branch), rc — contract:worktree:inv-t25" 0 "$RC"
check 29 "survivors() sees the worktree-only file (>=2 subset branch), stem — contract:worktree:inv-t25" "$(stem_of "$P25C")" "$OUT"
run_query "$S25C" --by-files "feat.py,wt-only.py" --candidate-sha "$C25WTO" --candidate-at "$AT25WTO" \
  --repo-root "$R5" --repo k25c --session-root "$R5"
check 30 "checkout root sees one survivor so the structural branch runs, rc — contract:worktree:inv-t25" 0 "$RC"
check 31 "checkout root sees one survivor so the structural branch runs, stdout — contract:worktree:inv-t25" "" "$OUT"

# (d) find_by_commit resolves BOTH SHAs against --session-root. The fix commit
#     lives in $R1 only while the store is keyed to $R2, so resolving either
#     side against --repo-root loses the match. A linked worktree cannot
#     discriminate this: it shares its checkout's object store and refs, so a
#     worktree-only commit rev-parses identically from either root (measured).
S25D="$TMPROOT/store25d"
P25D="$(append_grudge "$S25D" k25d "$R2" "widget exploded in the other checkout" "a.py" "$C15_SHORT" "2026-05-01")"
run_query "$S25D" --by-commit "$C15" --repo-root "$R2" --repo k25d --session-root "$R1"
check 32 "--by-commit resolves both SHAs against --session-root, rc — contract:worktree:inv-t25" 0 "$RC"
check 33 "--by-commit resolves both SHAs against --session-root, stem — contract:worktree:inv-t25" "$(stem_of "$P25D")" "$OUT"
run_query "$S25D" --by-commit "$C15" --repo-root "$R2" --repo k25d --session-root "$R2"
check 34 "a session root that cannot resolve the SHA is a miss, rc — contract:worktree:inv-t25" 0 "$RC"
check 35 "a session root that cannot resolve the SHA is a miss, stdout — contract:worktree:inv-t25" "" "$OUT"

# (e) --session-root is consumed by the two lookups ONLY. The ordinary query
#     path must be byte-identical with and without it, even when it names an
#     unrelated checkout ($R2, whose store key holds none of $R4's records).
run_query "$S25" x.py --repo-root "$R4" --repo k25
Q25_OUT="$OUT"
run_query "$S25" x.py --repo-root "$R4" --repo k25 --session-root "$R2"
check 36 "ordinary query path ignores --session-root — contract:worktree:inv-t25" "$Q25_OUT" "$OUT"
check 37 "the ordinary query probe is non-vacuous — contract:worktree:inv-t25" yes "$(nonempty "$Q25_OUT")"

# ========================================================================
# INV-T26 — --by-commit exit-code contract (three outcomes)
# ========================================================================
# contract:cli:inv-t26 checks=7
R6="$TMPROOT/r26"; new_repo "$R6"; R6="$(cd "$R6" && pwd -P)"
echo "v0" > "$R6/app.py"
commit_all "$R6" "base" "2026-04-01T09:00:00+00:00"
B26="$(sha_of "$R6" HEAD)"
echo "v1" >> "$R6/app.py"
commit_all "$R6" "fix(app): repair app" "2026-06-01T12:00:00+00:00"
C26="$(sha_of "$R6" HEAD)"
S26="$TMPROOT/store26"
P26="$(append_grudge "$S26" k26 "$R6" "app regressed" "app.py" "$C26" "2026-05-01")"

run_query "$S26" --by-commit "$C26" --repo-root "$R6" --repo k26 --session-root "$R6"
check 38 "match exits 0 — contract:cli:inv-t26" 0 "$RC"
check 39 "match prints the record stem, not fixed_in_commit — contract:cli:inv-t26" "$(stem_of "$P26")" "$OUT"
run_query "$S26" --by-commit "$B26" --repo-root "$R6" --repo k26 --session-root "$R6"
check 40 "resolvable but unmatched SHA exits 0 — contract:cli:inv-t26" 0 "$RC"
check 41 "resolvable but unmatched SHA prints nothing — contract:cli:inv-t26" "" "$OUT"

if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: unreadable-store fixture (--by-commit) needs a non-root uid"
else
  chmod 000 "$S26/k26/grudges"
  run_query "$S26" --by-commit "$C26" --repo-root "$R6" --repo k26 --session-root "$R6"
  check 42 "unreadable store exits 3 — contract:cli:inv-t26" 3 "$RC"
  check 43 "unreadable store writes a stderr diagnostic — contract:cli:inv-t26" yes "$(nonempty "$ERR")"
  check 44 "unreadable store prints nothing on stdout — contract:cli:inv-t26" "" "$OUT"
fi

# ========================================================================
# INV-T27 — --by-files exit-code contract (three outcomes)
# ========================================================================
# contract:cli:inv-t27 checks=7
R7="$TMPROOT/r27"; new_repo "$R7"; R7="$(cd "$R7" && pwd -P)"
for f in p.py q.py r.py; do echo "v0 # $f" > "$R7/$f"; done
commit_all "$R7" "base" "2026-04-01T09:00:00+00:00"
for f in p.py q.py r.py; do echo "v1 # $f" >> "$R7/$f"; done
commit_all "$R7" "fix(core): repair p, q and r" "2026-06-01T12:00:00+00:00"
C27="$(sha_of "$R7" HEAD)"
AT27="$(at_of "$R7" HEAD)"
S27="$TMPROOT/store27"
P27="$(append_grudge "$S27" k27 "$R7" "p and q regressed" "p.py,q.py" "" "2026-05-01")"

run_query "$S27" --by-files "p.py,q.py,r.py" --candidate-sha "$C27" --candidate-at "$AT27" \
  --repo-root "$R7" --repo k27 --session-root "$R7"
check 45 "subset match exits 0 — contract:cli:inv-t27" 0 "$RC"
check 46 "subset match prints the record stem — contract:cli:inv-t27" "$(stem_of "$P27")" "$OUT"
run_query "$S27" --by-files "r.py" --candidate-sha "$C27" --candidate-at "$AT27" \
  --repo-root "$R7" --repo k27 --session-root "$R7"
check 47 "clean miss exits 0 — contract:cli:inv-t27" 0 "$RC"
check 48 "clean miss prints nothing — contract:cli:inv-t27" "" "$OUT"

if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: unreadable-store fixture (--by-files) needs a non-root uid"
else
  chmod 000 "$S27/k27/grudges"
  run_query "$S27" --by-files "p.py,q.py,r.py" --candidate-sha "$C27" --candidate-at "$AT27" \
    --repo-root "$R7" --repo k27 --session-root "$R7"
  check 49 "unreadable store exits 3 — contract:cli:inv-t27" 3 "$RC"
  check 50 "unreadable store writes a stderr diagnostic — contract:cli:inv-t27" yes "$(nonempty "$ERR")"
  check 51 "unreadable store prints nothing on stdout — contract:cli:inv-t27" "" "$OUT"
fi

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASSED/$TOTAL passed"

# TOTAL accumulates per `check`, so a skipped scenario shrinks the denominator
# instead of failing. Pin the expected count so the loss is loud: only a root
# uid may run fewer (the two chmod-000 fixtures), and even then it is announced.
EXPECTED_CHECKS=51
ROOT_SKIPPED_CHECKS=6
if [ "$TOTAL" -ne "$EXPECTED_CHECKS" ]; then
  if [ "$(id -u)" -eq 0 ] && [ "$TOTAL" -eq "$((EXPECTED_CHECKS - ROOT_SKIPPED_CHECKS))" ]; then
    echo "SKIPPED: $ROOT_SKIPPED_CHECKS of $EXPECTED_CHECKS checks did not run (root uid cannot exercise the unreadable-store paths)"
  else
    echo "ERROR: expected $EXPECTED_CHECKS checks, ran $TOTAL — a scenario was skipped or dropped"
    exit 1
  fi
fi

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
