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
# Extra VAR=value words injected into the query's environment (word-split on
# purpose). Used to prove an inherited GIT_DIR cannot override --session-root.
QUERY_ENV=""
run_query() {
  # run_query <store_base> <args...>; sets OUT / ERR / RC
  local store="$1"; shift
  set +e
  OUT="$(env HOME="$FAKE_HOME" CRUCIBLE_GRUDGE_DIR="$store" \
    ${QUERY_TZ:+TZ="$QUERY_TZ"} ${QUERY_ENV:-} \
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
# contract:match:inv-t15 checks=6
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

# The same unresolvable 40-char token on BOTH sides. A _resolve_commit that
# passed its argument through instead of returning None would compare the two
# raw strings, find them equal, and report a false match.
S15C="$TMPROOT/store15c"
BOGUS15="cafebabe11111111111111111111111111111111"
append_grudge "$S15C" k15c "$R1" "both sides unresolvable" "app.py" "$BOGUS15" "2026-05-01" >/dev/null
run_query "$S15C" --by-commit "$BOGUS15" --repo-root "$R1" --repo k15c --session-root "$R1"
check 5 "identical unresolvable SHAs on both sides are a miss, rc — contract:match:inv-t15" 0 "$RC"
check 6 "identical unresolvable SHAs on both sides are a miss, stdout — contract:match:inv-t15" "" "$OUT"

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
check 7 "2-file subset with earlier date_fixed matches, rc — contract:match:inv-t16" 0 "$RC"
check 8 "2-file subset with earlier date_fixed matches, stem — contract:match:inv-t16" "$(stem_of "$P16A")" "$OUT"

# (b) 30+ days old, still date_fixed-before the candidate -> STILL matches
S16B="$TMPROOT/store16b"
P16B="$(append_grudge "$S16B" k16b "$R2" "ancient a/b regression" "a.py,b.py" "" "2026-01-05")"
run_query "$S16B" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16b --session-root "$R2"
check 9 "grudge 5 months old is not time-bounded, rc — contract:match:inv-t16" 0 "$RC"
check 10 "grudge 5 months old is not time-bounded, stem — contract:match:inv-t16" "$(stem_of "$P16B")" "$OUT"

# (c) partial overlap (grudge names zz.py, untouched by the candidate) -> no match
S16C="$TMPROOT/store16c"
append_grudge "$S16C" k16c "$R2" "a and zz regressed together" "a.py,zz.py" "" "2026-05-15" >/dev/null
run_query "$S16C" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16c --session-root "$R2"
check 11 "intersection without subset does not match, rc — contract:match:inv-t16" 0 "$RC"
check 12 "intersection without subset does not match, stdout — contract:match:inv-t16" "" "$OUT"

# (d) date_fixed AFTER the candidate author date -> no match
S16D="$TMPROOT/store16d"
append_grudge "$S16D" k16d "$R2" "a and b fixed after the candidate" "a.py,b.py" "" "2026-06-02" >/dev/null
run_query "$S16D" --by-files "a.py,b.py,c.py" --candidate-sha "$C16" --candidate-at "$AT16" \
  --repo-root "$R2" --repo k16d --session-root "$R2"
check 13 "date_fixed after candidate does not match, rc — contract:match:inv-t16" 0 "$RC"
check 14 "date_fixed after candidate does not match, stdout — contract:match:inv-t16" "" "$OUT"

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
check 15 "author date compared in UTC not local time, rc — contract:match:inv-t16" 0 "$RC"
check 16 "author date compared in UTC not local time, stem — contract:match:inv-t16" "$(stem_of "$P16E")" "$OUT"

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
check 17 "malformed records are silent misses not exit 3, rc — contract:match:inv-t16" 0 "$RC"
check 18 "malformed records are silent misses not exit 3, stem — contract:match:inv-t16" "$(stem_of "$P16F")" "$OUT"
check 19 "all four records actually loaded (scanned=4) — contract:match:inv-t16" yes "$(has "$ERR" "scanned=4")"

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
check 20 "squashed rewrite matches by patch-id, rc — contract:match:inv-t17" 0 "$RC"
check 21 "squashed rewrite matches by patch-id, stem — contract:match:inv-t17" "$(stem_of "$P17A")" "$OUT"

S17B="$TMPROOT/store17b"
append_grudge "$S17B" k17b "$R3" "coincidental filename only" "feat.py" "$D17" "2026-05-03" >/dev/null
run_query "$S17B" --by-files "feat.py" --candidate-sha "$C17" --candidate-at "$AT17" \
  --repo-root "$R3" --repo k17b --session-root "$R3"
check 22 "same filename with a different patch does not match, rc — contract:match:inv-t17" 0 "$RC"
check 23 "same filename with a different patch does not match, stdout — contract:match:inv-t17" "" "$OUT"

# ========================================================================
# INV-T25 — store-root / session-root split
# ========================================================================
# contract:worktree:inv-t25 checks=20
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
check 24 ".git dir as store root filters every record out — contract:worktree:inv-t25" yes "$(has "$ERR" "scanned=0 matched=0")"
run_query "$S25" --by-commit "$C25" --repo-root "$R4" --repo k25 --session-root "$R4"
check 25 "dirname'd checkout root sees all three records — contract:worktree:inv-t25" yes "$(has "$ERR" "scanned=3 matched=1")"

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
check 26 "session-root worktree resolves HEAD for the match, rc — contract:worktree:inv-t25" 0 "$RC"
check 27 "session-root worktree resolves HEAD for the match, stem — contract:worktree:inv-t25" "$(stem_of "$P25B")" "$OUT"
run_query "$S25B" --by-files "feat.py" --candidate-sha "$C25WT" --candidate-at "$AT25WT" \
  --repo-root "$R5" --repo k25b --session-root "$R5"
check 28 "other worktree's HEAD makes the stored fix an ancestor, rc — contract:worktree:inv-t25" 0 "$RC"
check 29 "other worktree's HEAD makes the stored fix an ancestor, stdout — contract:worktree:inv-t25" "" "$OUT"

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
check 30 "survivors() sees the worktree-only file (>=2 subset branch), rc — contract:worktree:inv-t25" 0 "$RC"
check 31 "survivors() sees the worktree-only file (>=2 subset branch), stem — contract:worktree:inv-t25" "$(stem_of "$P25C")" "$OUT"
run_query "$S25C" --by-files "feat.py,wt-only.py" --candidate-sha "$C25WTO" --candidate-at "$AT25WTO" \
  --repo-root "$R5" --repo k25c --session-root "$R5"
check 32 "checkout root sees one survivor so the structural branch runs, rc — contract:worktree:inv-t25" 0 "$RC"
check 33 "checkout root sees one survivor so the structural branch runs, stdout — contract:worktree:inv-t25" "" "$OUT"

# (d) find_by_commit resolves BOTH SHAs against --session-root. The fix commit
#     lives in $R1 only while the store is keyed to $R2, so resolving either
#     side against --repo-root loses the match. A linked worktree cannot
#     discriminate this: it shares its checkout's object store and refs, so a
#     worktree-only commit rev-parses identically from either root (measured).
S25D="$TMPROOT/store25d"
P25D="$(append_grudge "$S25D" k25d "$R2" "widget exploded in the other checkout" "a.py" "$C15_SHORT" "2026-05-01")"
run_query "$S25D" --by-commit "$C15" --repo-root "$R2" --repo k25d --session-root "$R1"
check 34 "--by-commit resolves both SHAs against --session-root, rc — contract:worktree:inv-t25" 0 "$RC"
check 35 "--by-commit resolves both SHAs against --session-root, stem — contract:worktree:inv-t25" "$(stem_of "$P25D")" "$OUT"
run_query "$S25D" --by-commit "$C15" --repo-root "$R2" --repo k25d --session-root "$R2"
check 36 "a session root that cannot resolve the SHA is a miss, rc — contract:worktree:inv-t25" 0 "$RC"
check 37 "a session root that cannot resolve the SHA is a miss, stdout — contract:worktree:inv-t25" "" "$OUT"

# (e) --session-root is consumed by the two lookups ONLY. The ordinary query
#     path must be byte-identical with and without it, even when it names an
#     unrelated checkout ($R2, whose store key holds none of $R4's records).
run_query "$S25" x.py --repo-root "$R4" --repo k25
Q25_OUT="$OUT"
run_query "$S25" x.py --repo-root "$R4" --repo k25 --session-root "$R2"
check 38 "ordinary query path ignores --session-root — contract:worktree:inv-t25" "$Q25_OUT" "$OUT"
check 39 "the ordinary query probe is non-vacuous — contract:worktree:inv-t25" yes "$(nonempty "$Q25_OUT")"

# (f) the same "consumed only by the two lookups" clause for the remaining
#     non-lookup paths: --stats and --cull. Both must behave identically with
#     and without --session-root.
S25F="$TMPROOT/store25f"
append_grudge "$S25F" k25f "$R4" "x regressed" "x.py" "$C25" "2026-05-01" >/dev/null
append_grudge "$S25F" k25f "$R4" "y regressed" "y.py" "" "2026-05-01" >/dev/null
append_grudge "$S25F" k25f "$R4" "z regressed" "z.py" "" "2026-05-01" >/dev/null

run_query "$S25F" --stats --repo-root "$R4" --repo k25f
ST25_OUT="$OUT"
run_query "$S25F" --stats --repo-root "$R4" --repo k25f --session-root "$R2"
check 40 "--stats path ignores --session-root — contract:worktree:inv-t25" "$ST25_OUT" "$OUT"
check 41 "the --stats probe is non-vacuous — contract:worktree:inv-t25" yes "$(has "$ST25_OUT" "3 held for k25f")"

# --cull must still cull. The record is keyed to $R25CR, where both its files
# have been deleted, while $R25CS is a SECOND checkout that still holds files of
# the same names. A --session-root that reached load_grudges would filter the
# record out (its repo_root is $R25CR) and cull nothing; one that reached
# survivors() would find both files alive in $R25CS and also cull nothing. The
# expected `culled 1` therefore discriminates BOTH leak shapes; asserting `--cull
# 0` against a healthy store would discriminate neither.
R25CR="$TMPROOT/r25cull"; new_repo "$R25CR"; R25CR="$(cd "$R25CR" && pwd -P)"
for f in gone-a.py gone-b.py keep.py; do echo "v0 # $f" > "$R25CR/$f"; done
commit_all "$R25CR" "base" "2026-04-01T09:00:00+00:00"
R25CS="$TMPROOT/r25cull-session"; new_repo "$R25CS"; R25CS="$(cd "$R25CS" && pwd -P)"
for f in gone-a.py gone-b.py; do echo "v0 # $f" > "$R25CS/$f"; done
commit_all "$R25CS" "base" "2026-04-01T09:00:00+00:00"
S25G="$TMPROOT/store25g"
append_grudge "$S25G" k25g "$R25CR" "both files later deleted" "gone-a.py,gone-b.py" "" "2026-05-01" >/dev/null
rm -f "$R25CR/gone-a.py" "$R25CR/gone-b.py"

run_query "$S25G" --cull --repo-root "$R25CR" --repo k25g --session-root "$R25CS"
check 42 "--cull judges staleness against --repo-root not --session-root — contract:worktree:inv-t25" yes "$(has "$ERR" "culled 1 settled")"
run_query "$S25G" --stats --repo-root "$R25CR" --repo k25g
check 43 "the culled record is really gone from the store — contract:worktree:inv-t25" yes "$(has "$OUT" "0 held for k25g")"

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
check 44 "match exits 0 — contract:cli:inv-t26" 0 "$RC"
check 45 "match prints the record stem, not fixed_in_commit — contract:cli:inv-t26" "$(stem_of "$P26")" "$OUT"
run_query "$S26" --by-commit "$B26" --repo-root "$R6" --repo k26 --session-root "$R6"
check 46 "resolvable but unmatched SHA exits 0 — contract:cli:inv-t26" 0 "$RC"
check 47 "resolvable but unmatched SHA prints nothing — contract:cli:inv-t26" "" "$OUT"

if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: unreadable-store fixture (--by-commit) needs a non-root uid"
else
  chmod 000 "$S26/k26/grudges"
  run_query "$S26" --by-commit "$C26" --repo-root "$R6" --repo k26 --session-root "$R6"
  check 48 "unreadable store exits 3 — contract:cli:inv-t26" 3 "$RC"
  check 49 "unreadable store writes a stderr diagnostic — contract:cli:inv-t26" yes "$(nonempty "$ERR")"
  check 50 "unreadable store prints nothing on stdout — contract:cli:inv-t26" "" "$OUT"
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
check 51 "subset match exits 0 — contract:cli:inv-t27" 0 "$RC"
check 52 "subset match prints the record stem — contract:cli:inv-t27" "$(stem_of "$P27")" "$OUT"
run_query "$S27" --by-files "r.py" --candidate-sha "$C27" --candidate-at "$AT27" \
  --repo-root "$R7" --repo k27 --session-root "$R7"
check 53 "clean miss exits 0 — contract:cli:inv-t27" 0 "$RC"
check 54 "clean miss prints nothing — contract:cli:inv-t27" "" "$OUT"

if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: unreadable-store fixture (--by-files) needs a non-root uid"
else
  chmod 000 "$S27/k27/grudges"
  run_query "$S27" --by-files "p.py,q.py,r.py" --candidate-sha "$C27" --candidate-at "$AT27" \
    --repo-root "$R7" --repo k27 --session-root "$R7"
  check 55 "unreadable store exits 3 — contract:cli:inv-t27" 3 "$RC"
  check 56 "unreadable store writes a stderr diagnostic — contract:cli:inv-t27" yes "$(nonempty "$ERR")"
  check 57 "unreadable store prints nothing on stdout — contract:cli:inv-t27" "" "$OUT"
fi

# ========================================================================
# 0 survivors -> no match
# ========================================================================
# Untagged on purpose: the contract states this clause in find_by_files'
# api_surface description, which carries no test_tag, and it is neither
# inv-t16's >=2-survivor branch nor inv-t17's ==1-survivor branch.
R8="$TMPROOT/r0surv"; new_repo "$R8"; R8="$(cd "$R8" && pwd -P)"
for f in gone1.py gone2.py kept.py; do echo "v0 # $f" > "$R8/$f"; done
commit_all "$R8" "base" "2026-04-01T09:00:00+00:00"
echo "v1 # kept" >> "$R8/kept.py"
commit_all "$R8" "fix(kept): repair kept" "2026-06-01T12:00:00+00:00"
C0S="$(sha_of "$R8" HEAD)"
AT0S="$(at_of "$R8" HEAD)"
S0S="$TMPROOT/store0surv"
append_grudge "$S0S" k0s "$R8" "both named files were deleted later" "gone1.py,gone2.py" "" "2026-05-01" >/dev/null
# Deleted AFTER the record is written, so survivors() returns [] at query time.
# Without `if not surv: continue` the ==1 branch indexes surv[0], raises
# IndexError, and the outer handler turns a contract-mandated miss into exit 3.
rm -f "$R8/gone1.py" "$R8/gone2.py"
run_query "$S0S" --by-files "kept.py" --candidate-sha "$C0S" --candidate-at "$AT0S" \
  --repo-root "$R8" --repo k0s --session-root "$R8"
check 58 "a 0-survivor grudge is a miss not an IndexError, rc" 0 "$RC"
check 59 "a 0-survivor grudge is a miss, stdout" "" "$OUT"
check 60 "the 0-survivor record was actually loaded (scanned=1 matched=0)" yes "$(has "$ERR" "scanned=1 matched=0")"

# ========================================================================
# candidate paths are normalized before the subset test
# ========================================================================
# Untagged on purpose: the normalization is find_by_files' own, not a clause of
# any tagged invariant. Every other fixture passes already-normalized
# repo-relative POSIX paths, so the normalize_path call is never discriminated.
R9="$TMPROOT/rnorm"; new_repo "$R9"; R9="$(cd "$R9" && pwd -P)"
for f in a.py b.py c.py; do echo "v0 # $f" > "$R9/$f"; done
commit_all "$R9" "base" "2026-04-01T09:00:00+00:00"
for f in a.py b.py c.py; do echo "v1 # $f" >> "$R9/$f"; done
commit_all "$R9" "fix(core): repair a, b and c" "2026-06-01T12:00:00+00:00"
CN="$(sha_of "$R9" HEAD)"
ATN="$(at_of "$R9" HEAD)"
SN="$TMPROOT/storenorm"
PN="$(append_grudge "$SN" knorm "$R9" "a and b regressed together" "a.py,b.py" "" "2026-05-15")"
# survivors() are stored repo-relative; this candidate list mixes ./-prefixed,
# absolute and bare forms, so the subset test holds only if the candidate side
# is normalized against --session-root first.
run_query "$SN" --by-files "./a.py,$R9/b.py,c.py" --candidate-sha "$CN" --candidate-at "$ATN" \
  --repo-root "$R9" --repo knorm --session-root "$R9"
check 61 "./-prefixed and absolute candidate paths still subset-match, rc" 0 "$RC"
check 62 "./-prefixed and absolute candidate paths still subset-match, stem" "$(stem_of "$PN")" "$OUT"

# ========================================================================
# git-environment isolation, session-root canonicalisation, ref/object
# disambiguation, and root-commit patch-ids
# ========================================================================
# Untagged on purpose: these are robustness properties of the git seam itself,
# not clauses of any tagged contract invariant. Each pair is control + attack,
# so a fix that merely broke the control could not pass.

# (a) `git -C <dir>` only chdirs — it does NOT clear GIT_DIR/GIT_WORK_TREE,
#     which outrank discovery-from-cwd. A Stop hook firing while a git hook is
#     on the stack inherits them, and every git call in the lookup would run
#     against the WRONG repository, producing a miss indistinguishable from a
#     genuine one.
RA1="$TMPROOT/adv1a"; new_repo "$RA1"; RA1="$(cd "$RA1" && pwd -P)"
echo "v0" > "$RA1/app.py"; commit_all "$RA1" "base" "2026-04-01T09:00:00+00:00"
echo "v1" >> "$RA1/app.py"; commit_all "$RA1" "fix(app): repair app" "2026-06-01T12:00:00+00:00"
CA1="$(sha_of "$RA1" HEAD)"
RB1="$TMPROOT/adv1b"; new_repo "$RB1"; RB1="$(cd "$RB1" && pwd -P)"
echo "unrelated" > "$RB1/other.py"; commit_all "$RB1" "base" "2026-04-01T09:00:00+00:00"
SA1="$TMPROOT/storeadv1"
PA1="$(append_grudge "$SA1" kadv1 "$RA1" "app regressed" "app.py" "$CA1" "2026-05-01")"

QUERY_ENV=""
run_query "$SA1" --by-commit "$CA1" --repo-root "$RA1" --repo kadv1 --session-root "$RA1"
check 63 "git-env control: a clean environment matches" "$(stem_of "$PA1")" "$OUT"
QUERY_ENV="GIT_DIR=$RB1/.git GIT_WORK_TREE=$RB1"
run_query "$SA1" --by-commit "$CA1" --repo-root "$RA1" --repo kadv1 --session-root "$RA1"
QUERY_ENV=""
check 64 "an inherited GIT_DIR must not override --session-root" "$(stem_of "$PA1")" "$OUT"

# (b) git resolves a repository from any subdirectory, so --by-commit keeps
#     working from one; but files_touched are stored repo-relative, so joining
#     them onto a subdirectory session_root makes every stored path "not exist"
#     and the grudge look 0-survivor. --session-root DEFAULTS TO CWD and a Stop
#     hook's cwd is routinely a subdirectory, so this is the default path.
RV2="$TMPROOT/advsub"; new_repo "$RV2"; RV2="$(cd "$RV2" && pwd -P)"
mkdir -p "$RV2/sub"
for f in a.py b.py c.py; do echo "v0 # $f" > "$RV2/$f"; done
echo keep > "$RV2/sub/keep.txt"
commit_all "$RV2" "base" "2026-04-01T09:00:00+00:00"
for f in a.py b.py c.py; do echo "v1 # $f" >> "$RV2/$f"; done
commit_all "$RV2" "fix(core): repair a, b and c" "2026-06-01T12:00:00+00:00"
CV2="$(sha_of "$RV2" HEAD)"; ATV2="$(at_of "$RV2" HEAD)"
SV2="$TMPROOT/storeadvsub"
PV2="$(append_grudge "$SV2" kadvsub "$RV2" "a and b regressed" "a.py,b.py" "" "2026-05-15")"

run_query "$SV2" --by-files "a.py,b.py,c.py" --candidate-sha "$CV2" --candidate-at "$ATV2" \
  --repo-root "$RV2" --repo kadvsub --session-root "$RV2"
check 65 "session-root control: the checkout root matches" "$(stem_of "$PV2")" "$OUT"
run_query "$SV2" --by-files "a.py,b.py,c.py" --candidate-sha "$CV2" --candidate-at "$ATV2" \
  --repo-root "$RV2" --repo kadvsub --session-root "$RV2/sub"
check 66 "a --session-root inside the checkout still matches" "$(stem_of "$PV2")" "$OUT"

# (c) `rev-parse --verify <s>^{commit}` prefers a REF named <s> over the object
#     whose abbreviation is <s>, announcing it only as "refname is ambiguous"
#     on stderr — which _git discards. A tag named like a short SHA (release
#     tooling and `git branch $(git rev-parse --short HEAD)` produce them) would
#     otherwise give BOTH a false positive on the unrelated commit and a false
#     negative on the real fix.
RV3="$TMPROOT/advref"; new_repo "$RV3"; RV3="$(cd "$RV3" && pwd -P)"
echo "v0" > "$RV3/app.py"; commit_all "$RV3" "the real fix" "2026-04-01T09:00:00+00:00"
AV3="$(sha_of "$RV3" HEAD)"
AV3S="$(git -C "$RV3" rev-parse --short=7 "$AV3")"
echo "v1" >> "$RV3/app.py"; commit_all "$RV3" "an unrelated later commit" "2026-06-01T12:00:00+00:00"
BV3="$(sha_of "$RV3" HEAD)"
git -C "$RV3" tag "$AV3S" "$BV3"          # a tag NAMED like AV3's abbreviation
SV3="$TMPROOT/storeadvref"
PV3="$(append_grudge "$SV3" kadvref "$RV3" "app regressed" "app.py" "$AV3S" "2026-05-01")"

run_query "$SV3" --by-commit "$BV3" --repo-root "$RV3" --repo kadvref --session-root "$RV3"
check 67 "an ambiguous ref name must not match an unrelated commit" "" "$OUT"
run_query "$SV3" --by-commit "$AV3" --repo-root "$RV3" --repo kadvref --session-root "$RV3"
check 68 "the stored abbreviation still matches its own commit" "$(stem_of "$PV3")" "$OUT"

# (d) `diff-tree -p <root-commit>` prints nothing without --root, so _patch_id
#     returns "" and _structural_match's bool() guard can never match a
#     parentless fix — precisely the case the checkpoint sentinel exists for.
#     The non-root twin carries the identical patch and matches already, so the
#     miss is the absent flag, not a different patch.
RV4="$TMPROOT/advroot"; new_repo "$RV4"; RV4="$(cd "$RV4" && pwd -P)"
echo readme > "$RV4/README"; commit_all "$RV4" "base" "2026-04-01T09:00:00+00:00"
git -C "$RV4" checkout -q --orphan fixbranch
git -C "$RV4" rm -q -rf . >/dev/null 2>&1 || true
printf 'the fix\n' > "$RV4/feat.py"; git -C "$RV4" add feat.py
GIT_AUTHOR_DATE="2026-05-02T09:00:00+00:00" GIT_COMMITTER_DATE="2026-05-02T09:00:00+00:00" \
  git -C "$RV4" commit -q -m "fix(feat): the real fix, as a root commit"
FIXV4="$(sha_of "$RV4" HEAD)"
git -C "$RV4" checkout -q main
printf 'the fix\n' > "$RV4/feat.py"; git -C "$RV4" add feat.py
GIT_AUTHOR_DATE="2026-06-01T12:00:00+00:00" GIT_COMMITTER_DATE="2026-06-01T12:00:00+00:00" \
  git -C "$RV4" commit -q -m "fix(feat): re-landed on main"
CV4="$(sha_of "$RV4" HEAD)"; ATV4="$(at_of "$RV4" HEAD)"
# non-root twin of FIXV4: same patch, also off HEAD
git -C "$RV4" checkout -q -b twin main~1
printf 'the fix\n' > "$RV4/feat.py"; git -C "$RV4" add feat.py
GIT_AUTHOR_DATE="2026-05-02T09:00:00+00:00" GIT_COMMITTER_DATE="2026-05-02T09:00:00+00:00" \
  git -C "$RV4" commit -q -m "fix(feat): non-root twin"
TWINV4="$(sha_of "$RV4" HEAD)"
git -C "$RV4" checkout -q main

SV4T="$TMPROOT/storeadvroottwin"
PV4T="$(append_grudge "$SV4T" kadvroott "$RV4" "feat regressed" "feat.py" "$TWINV4" "2026-05-02")"
run_query "$SV4T" --by-files "feat.py" --candidate-sha "$CV4" --candidate-at "$ATV4" \
  --repo-root "$RV4" --repo kadvroott --session-root "$RV4"
check 69 "root-commit control: a non-root fix with the same patch matches" "$(stem_of "$PV4T")" "$OUT"
SV4="$TMPROOT/storeadvroot"
PV4="$(append_grudge "$SV4" kadvroot "$RV4" "feat regressed" "feat.py" "$FIXV4" "2026-05-02")"
run_query "$SV4" --by-files "feat.py" --candidate-sha "$CV4" --candidate-at "$ATV4" \
  --repo-root "$RV4" --repo kadvroot --session-root "$RV4"
check 70 "a root commit as the stored fix still matches by patch-id" "$(stem_of "$PV4")" "$OUT"


# ========================================================================
# Stop-hook fixtures (#559 Task 7). Everything below drives the real hook
# `hooks/grudge-resolution-guard.sh` as a subprocess against a per-case tmp
# tree: its own HOME (so $PROJECT_MEMORY lands in the fixture), its own
# CRUCIBLE_GRUDGE_DIR store, and its own `git init` repo. No real machine
# state is read or written.
# ========================================================================
HOOK="$REPO_ROOT/hooks/grudge-resolution-guard.sh"

# Per-case fixture root. Sets HC_ROOT/HC_HOME/HC_STORE/HC_REPO/HC_KEY/
# HC_CWD/HC_TRANSCRIPT. The transcript's earliest ISO-8601 `.timestamp` is
# 2026-01-01T00:00:00Z, so `commit_all`'s default 2026-05-01 author date is
# inside the session window and 2025-* dates are outside it.
hook_case() {
  local name="$1"
  HC_ROOT="$TMPROOT/hook-$name"
  HC_HOME="$HC_ROOT/home"
  HC_STORE="$HC_ROOT/store"
  mkdir -p "$HC_HOME" "$HC_STORE"
  HC_REPO="$HC_ROOT/repo"
  new_repo "$HC_REPO"
  HC_REPO="$(cd "$HC_REPO" && pwd -P)"
  HC_KEY="$(basename "$HC_REPO")"
  HC_CWD="$HC_REPO"
  HC_TRANSCRIPT="$HC_ROOT/transcript.jsonl"
  {
    echo '{"type":"user","timestamp":"2026-01-01T00:00:00.000Z"}'
    echo '{"type":"assistant","timestamp":"2026-01-01T00:00:05.000Z"}'
  } > "$HC_TRANSCRIPT"
  mkdir -p "$HC_STORE/$HC_KEY/grudges"
}

# $PROJECT_MEMORY for a given project root, using the hook's own derivation
# (hooks/build-routing-advisor.sh:141-143).
mem_dir() { printf '%s/.claude/projects/%s/memory' "$HC_HOME" "$(printf '%s' "$1" | tr '/' '-')"; }
guard_dir() { printf '%s/grudge-guard' "$(mem_dir "$1")"; }

# Extra VAR=value words injected into the hook's environment (word-split on
# purpose), e.g. the env-var kill-switch.
HOOK_ENV=""
_invoke_hook() {
  # reads $TMPROOT/last-payload.json; sets OUT / ERR / RC.
  # Deliberately NOT a pipeline: with `pipefail` set, a hook that exits
  # before draining stdin would SIGPIPE the writer and report 141.
  set +e
  OUT="$(cd "$HC_CWD" && env HOME="$HC_HOME" CLAUDE_PROJECT_DIR="$REPO_ROOT" \
    CRUCIBLE_GRUDGE_DIR="$HC_STORE" ${HOOK_ENV:-} \
    bash "$HOOK" <"$TMPROOT/last-payload.json" 2>"$TMPROOT/last-stderr.txt")"
  RC=$?
  set -e
  ERR="$(cat "$TMPROOT/last-stderr.txt")"
}

run_hook() {
  # run_hook <session_id> [stop_hook_active]
  printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"Stop","stop_hook_active":%s}' \
    "$1" "$HC_TRANSCRIPT" "$HC_CWD" "${2:-false}" > "$TMPROOT/last-payload.json"
  _invoke_hook
}

run_hook_raw() {
  # run_hook_raw <raw stdin payload>
  printf '%s' "$1" > "$TMPROOT/last-payload.json"
  _invoke_hook
}

st() {
  # st <project-root> <session-id> <jq filter> — read the per-session state file
  jq -r "$3" "$(guard_dir "$1")/$2.json" 2>/dev/null || echo "STATE-READ-FAILED"
}

add_skip() {
  # add_skip <project-root> <line>
  local d; d="$(guard_dir "$1")"
  mkdir -p "$d"
  echo "$2" >> "$d/skips.log"
}

exists() { if [ -e "$1" ]; then echo "yes"; else echo "no"; fi; }

# ========================================================================
# INV-T12 — bounded blocking (1/3)(2/3)(3/3) then give up, with the
# Step-15 grudge_append.py prefill on both the block and the give-up path
# ========================================================================
# contract:hook:inv-t12 checks=16
hook_case t12
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "# notes" > "$HC_REPO/notes.md"
commit_all "$HC_REPO" "chore: baseline"
printf '# notes\n\nmore prose\n' > "$HC_REPO/notes.md"
commit_all "$HC_REPO" "fix(docs): expand notes"
T12_DOCS="$(sha_of "$HC_REPO" HEAD)"
echo "VALUE = 1" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): repair the widget"
T12_FIX="$(sha_of "$HC_REPO" HEAD)"

run_hook s12
check 71 "Stop 1 blocks — contract:hook:inv-t12" 2 "$RC"
check 72 "Stop 1 carries the (1/3) counter — contract:hook:inv-t12" yes "$(has "$ERR" "(1/3)")"
check 73 "Stop 1 names the unresolved candidate — contract:hook:inv-t12" yes "$(has "$ERR" "$T12_FIX")"
check 74 "docs-only fix is never named — contract:hook:inv-t12" no "$(has "$ERR" "$T12_DOCS")"
check 75 "Stop 1 prefills grudge_append.py — contract:hook:inv-t12" yes "$(has "$ERR" "grudge_append.py")"
check 76 "prefill carries the shared-clone --repo-root — contract:hook:inv-t12" yes "$(has "$ERR" "--repo-root \"$HC_REPO\"")"
# `=`-joined, not space-separated: a `--repo`/`--files` VALUE that begins
# with `-` (a legal POSIX path, and git sorts it first) is read by argparse as
# a stray option, so the printed remedy would not run. See inv-t23 below.
check 77 "prefill carries the shared-clone --repo key — contract:hook:inv-t12" yes "$(has "$ERR" "--repo=\"$HC_KEY\"")"
check 78 "prefill carries the candidate's sha_files — contract:hook:inv-t12" yes "$(has "$ERR" "--files=\"app.py\"")"
run_hook s12 true
check 79 "Stop 2 re-blocks — contract:hook:inv-t12" 2 "$RC"
check 80 "Stop 2 carries the (2/3) counter — contract:hook:inv-t12" yes "$(has "$ERR" "(2/3)")"
run_hook s12 true
check 81 "Stop 3 re-blocks — contract:hook:inv-t12" 2 "$RC"
check 82 "Stop 3 carries the (3/3) counter — contract:hook:inv-t12" yes "$(has "$ERR" "(3/3)")"
run_hook s12 true
check 83 "Stop 4 allows — contract:hook:inv-t12" 0 "$RC"
check 84 "Stop 4 says it is giving up — contract:hook:inv-t12" yes "$(has "$ERR" "giving up")"
check 85 "give-up path still prefills grudge_append.py — contract:hook:inv-t12" yes "$(has "$ERR" "grudge_append.py")"
check 86 "give-up prefill names the candidate SHA — contract:hook:inv-t12" yes "$(has "$ERR" "$T12_FIX")"

# ========================================================================
# INV-T13 — FATAL-C: candidacy uses the AUTHOR date, not the committer date
# ========================================================================
# contract:hook:inv-t13 checks=6
hook_case t13ctl
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): in-window fix"
run_hook s13ctl
check 87 "control: an in-window fix does block — contract:hook:inv-t13" 2 "$RC"

hook_case t13
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline" "2025-05-01T09:00:00+00:00"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): pre-session fix" "2025-06-01T09:00:00+00:00"
# `git commit --amend` with no date env rewrites the COMMITTER date to now and
# leaves the AUTHOR date alone — FATAL-C's own source shape.
git -C "$HC_REPO" commit -q --amend --no-edit
T13_FIX="$(sha_of "$HC_REPO" HEAD)"
T13_AT="$(git -C "$HC_REPO" log -1 --format=%at)"
T13_CT="$(git -C "$HC_REPO" log -1 --format=%ct)"
check 88 "fixture really rewrote the committer date — contract:hook:inv-t13" yes \
  "$(if [ "$T13_CT" -gt "$T13_AT" ]; then echo yes; else echo no; fi)"
run_hook s13
check 89 "author date before seeded_at is not a candidate — contract:hook:inv-t13" 0 "$RC"
check 90 "the rebased commit is never named — contract:hook:inv-t13" no "$(has "$ERR" "$T13_FIX")"

# Filter (b) is `%at >= seeded_at`, so a fix commit landing EXACTLY on the
# session's first transcript timestamp is INSIDE the window. Every other
# fixture puts months between the two, where `>=` and `>` agree.
hook_case t13edge
echo "V = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline" "2025-12-01T09:00:00+00:00"
echo "V = 1" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): repair on the boundary" "2026-01-01T00:00:00+00:00"
T13EDGE="$(sha_of "$HC_REPO" HEAD)"
run_hook s13edge
check 283 "a fix commit dated exactly at seeded_at is in scope — contract:hook:inv-t13" 2 "$RC"
check 284 "the boundary candidate is named — contract:hook:inv-t13" yes "$(has "$ERR" "$T13EDGE")"

# ========================================================================
# INV-T14 — trigger shapes: .md-only, non-.md, `fix:` colon form, merges,
# and a parentless ROOT fix commit
# ========================================================================
# contract:hook:inv-t14 checks=26
hook_case t14md
echo "# notes" > "$HC_REPO/notes.md"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
printf '# notes\n\nmore\n' > "$HC_REPO/notes.md"; commit_all "$HC_REPO" "fix(docs): prose only"
T14MD="$(sha_of "$HC_REPO" HEAD)"
run_hook s14md
check 91 "an all-.md fix commit never blocks — contract:hook:inv-t14" 0 "$RC"
check 92 "an all-.md fix commit is never named — contract:hook:inv-t14" no "$(has "$ERR" "$T14MD")"

hook_case t14code
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T14CODE="$(sha_of "$HC_REPO" HEAD)"
run_hook s14code
check 93 "one non-.md path makes a fix commit a candidate — contract:hook:inv-t14" 2 "$RC"
check 94 "the non-.md candidate is named — contract:hook:inv-t14" yes "$(has "$ERR" "$T14CODE")"

hook_case t14colon
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix: colon-no-scope repair"
T14COLON="$(sha_of "$HC_REPO" HEAD)"
run_hook s14colon
check 95 "a fix: colon subject qualifies identically — contract:hook:inv-t14" 2 "$RC"
check 96 "the colon-form candidate is named — contract:hook:inv-t14" yes "$(has "$ERR" "$T14COLON")"

hook_case t14merge
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" checkout -q -b topic
echo "feature" > "$HC_REPO/feature.py"; commit_all "$HC_REPO" "chore: branch work"
git -C "$HC_REPO" checkout -q main
GIT_AUTHOR_DATE="2026-05-01T09:00:00+00:00" GIT_COMMITTER_DATE="2026-05-01T09:00:00+00:00" \
  git -C "$HC_REPO" merge -q --no-ff -m "fix(widget): merge the topic branch" topic
T14MERGE="$(sha_of "$HC_REPO" HEAD)"
run_hook s14merge
check 97 "a merge commit with a fix( subject never qualifies — contract:hook:inv-t14" 0 "$RC"
check 98 "the merge commit is never named — contract:hook:inv-t14" no "$(has "$ERR" "$T14MERGE")"

# A repo whose ROOT commit is the fix. Stop 2 must report (2/3): reporting
# (1/3) again would mean item 16's parentless-checkpoint sentinel was skipped
# and the state was discarded every Stop.
hook_case t14root
echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): initial repair"
T14ROOT="$(sha_of "$HC_REPO" HEAD)"
run_hook s14root
check 99 "a parentless root fix commit blocks — contract:hook:inv-t14" 2 "$RC"
check 100 "root-commit Stop 1 reports (1/3) — contract:hook:inv-t14" yes "$(has "$ERR" "(1/3)")"
run_hook s14root true
check 101 "root-commit Stop 2 re-blocks — contract:hook:inv-t14" 2 "$RC"
check 102 "root-commit Stop 2 reports (2/3), not (1/3) — contract:hook:inv-t14" yes "$(has "$ERR" "(2/3)")"

# Filter (c) must test the PATH, not git's rendering of it. `diff-tree
# --name-only` C-quotes any path holding a non-ASCII byte, a `"` or a `\`
# (core.quotePath defaults on), and a quoted line ends `.md"` — so read as a
# display string these three documentation-only commits all look like they
# touch a non-.md path, and all three BLOCK, against this invariant's first
# clause. Every other .md fixture here is named `notes.md`, which cannot tell.
hook_case t14mdutf8
mkdir -p "$HC_REPO/docs"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
printf 'prose\n' > "$HC_REPO/docs/café.md"
commit_all "$HC_REPO" "fix(docs): non-ASCII note name"
T14U="$(sha_of "$HC_REPO" HEAD)"
run_hook s14mdutf8
check 285 "an all-.md fix commit with a non-ASCII name never blocks — contract:hook:inv-t14" 0 "$RC"
check 286 "the non-ASCII .md commit is never named — contract:hook:inv-t14" no "$(has "$ERR" "$T14U")"

hook_case t14mdquote
mkdir -p "$HC_REPO/docs"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
printf 'prose\n' > "$HC_REPO/docs/no\"te.md"
commit_all "$HC_REPO" "fix(docs): note name with a double quote"
T14Q="$(sha_of "$HC_REPO" HEAD)"
run_hook s14mdquote
check 287 "an all-.md fix commit whose name holds a quote never blocks — contract:hook:inv-t14" 0 "$RC"
check 288 "the quote-named .md commit is never named — contract:hook:inv-t14" no "$(has "$ERR" "$T14Q")"

# The byte class `-z` alone does NOT close: a path may legally CONTAIN a
# newline. Reading git's NUL-delimited output back through a newline-delimited
# string splits `docs/a<LF>b.md` into `docs/a` (no `.md` suffix) and `b.md`, so
# filter (c) concludes "at least one non-.md path" and this documentation-only
# commit BLOCKS — the same INV-T14 violation the quoting bug caused, by a
# different byte. The predicate now takes an argument VECTOR, which has no
# delimiter to collide with and is therefore correct for every byte at once.
hook_case t14mdnewline
mkdir -p "$HC_REPO/docs"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
printf 'prose\n' > "$HC_REPO/docs/$(printf 'a\nb.md')"
commit_all "$HC_REPO" "fix(docs): note name holding a newline"
T14NL="$(sha_of "$HC_REPO" HEAD)"
run_hook s14mdnewline
check 324 "an all-.md fix commit whose name holds a newline never blocks — contract:hook:inv-t14" 0 "$RC"
check 325 "the newline-named .md commit is never named — contract:hook:inv-t14" no "$(has "$ERR" "$T14NL")"

# The same byte in the BLOCKING direction, across two Stops. The path is
# `src/a.md<LF>b.py`: it is a CODE path (it ends `.py`), so Stop 1 must block
# from the fresh diff-tree — but everything before the newline ends `.md`, so
# Stop 2 is only correct if the persisted sha_files still carries the whole
# path. The stored encoding is a comma-joined value on ONE line, so the newline
# is folded onto the comma delimiter at the store rather than left to truncate
# the record; without the fold the stored value is just `src/a.md`, the commit
# reads as documentation-only on Stop 2, and enforcement silently stops.
hook_case t14nlcode
mkdir -p "$HC_REPO/src"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
printf 'code\n' > "$HC_REPO/src/$(printf 'a.md\nb.py')"
commit_all "$HC_REPO" "fix(widget): code path holding a newline"
run_hook s14nlcode
check 326 "a newline-named code path blocks on Stop 1 — contract:hook:inv-t14" 2 "$RC"
run_hook s14nlcode true
check 327 "the persisted branch still blocks it on Stop 2 — contract:hook:inv-t14" yes \
  "$(has "$ERR" "(2/3)")"

# The same path beside a code path IS a candidate, and what lands in sha_files
# is the raw path — which is what the --by-files clearance lookup and the
# Step-15 prefill are then handed. Stop 2 re-derives candidacy from that stored
# value, so filter (c)'s persisted branch is pinned here too.
hook_case t14mdmixed
mkdir -p "$HC_REPO/docs"; echo "VALUE = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; printf 'prose\n' > "$HC_REPO/docs/café.md"
commit_all "$HC_REPO" "fix(widget): code plus a non-ASCII note"
T14X="$(sha_of "$HC_REPO" HEAD)"
run_hook s14mdmixed
check 289 "a non-ASCII .md beside a code path still blocks — contract:hook:inv-t14" 2 "$RC"
check 290 "sha_files stores the raw path, not git's quoted form — contract:hook:inv-t14" true \
  "$(st "$HC_REPO" s14mdmixed "(.sha_files[\"$T14X\"] | index(\"docs/café.md\")) != null")"
run_hook s14mdmixed true
check 291 "the persisted-sha_files branch agrees on Stop 2 — contract:hook:inv-t14" yes "$(has "$ERR" "(2/3)")"

# Filter (a) is `^fix[(:]`: anchored, and the character right after `fix`
# decides. Only near-miss subjects can tell it from a bare `^fix` or from an
# unanchored `fix[(:]` — every subject above is a well-formed positive.
hook_case t14fixup
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fixup! chore: baseline"
run_hook s14fixup
check 292 "a fixup! subject is not a fix( subject — contract:hook:inv-t14" 0 "$RC"

hook_case t14hotfix
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "hotfix(core): tighten the bound"
run_hook s14hotfix
check 293 "the ^ anchor keeps hotfix(core): out of the trigger set — contract:hook:inv-t14" 0 "$RC"

# The subject is EVERYTHING after the SECOND `|` of the --format line. A greedy
# strip would leave `b pipeline` here and the commit would silently stop being
# a candidate — the case the parser calls out by name.
hook_case t14pipe
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the a|b pipeline"
run_hook s14pipe
check 294 "a | inside the subject cannot truncate it — contract:hook:inv-t14" 2 "$RC"

# ========================================================================
# INV-T18 — skips.log clears by SHA, tolerantly
# ========================================================================
# contract:skip:inv-t18 checks=7
_t18_case() {
  # _t18_case <name>; leaves T18_FIX / T18_BASE set
  hook_case "$1"
  echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
  T18_BASE="$(sha_of "$HC_REPO" HEAD)"
  echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
  T18_FIX="$(sha_of "$HC_REPO" HEAD)"
}

_t18_case t18full
add_skip "$HC_REPO" "$T18_FIX deliberately skipped"
run_hook s18full
check 103 "a skips.log line naming the candidate clears it — contract:skip:inv-t18" 0 "$RC"

_t18_case t18other
add_skip "$HC_REPO" "$T18_BASE a different commit entirely"
run_hook s18other
check 104 "a skips.log line naming another SHA clears nothing — contract:skip:inv-t18" 2 "$RC"

_t18_case t18abbrev
add_skip "$HC_REPO" "$(git -C "$HC_REPO" rev-parse --short=7 "$T18_FIX") abbreviated skip"
run_hook s18abbrev
check 105 "a 7-char abbreviation clears the 40-char candidate — contract:skip:inv-t18" 0 "$RC"

_t18_case t18junk
add_skip "$HC_REPO" "zzzzzzz not a resolvable object"
run_hook s18junk
check 106 "an unresolvable skip token clears nothing — contract:skip:inv-t18" 2 "$RC"
check 107 "an unresolvable skip token never errors the Stop — contract:skip:inv-t18" yes "$(has "$ERR" "(1/3)")"

# `read` exits non-zero on a final line with no trailing newline, so a plain
# `while read` drops it — silently, on the hook's primary escape hatch. An
# operator who uses `printf`/`echo -n`, or an editor with no final-newline,
# writes exactly this file.
_t18_case t18nonl
mkdir -p "$(guard_dir "$HC_REPO")"
printf '%s deliberately skipped' "$T18_FIX" > "$(guard_dir "$HC_REPO")/skips.log"
run_hook s18nonl
check 233 "a lone skips.log line with no trailing newline still clears — contract:skip:inv-t18" 0 "$RC"

_t18_case t18nonl2
mkdir -p "$(guard_dir "$HC_REPO")"
{ printf '%s an earlier, terminated line\n' "$T18_BASE"
  printf '%s deliberately skipped' "$T18_FIX"; } > "$(guard_dir "$HC_REPO")/skips.log"
run_hook s18nonl2
check 234 "an unterminated LAST line among several still clears — contract:skip:inv-t18" 0 "$RC"

# ========================================================================
# INV-T22 — first-Stop seeding
# ========================================================================
# contract:hook:inv-t22 checks=12
hook_case t22
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "# notes" > "$HC_REPO/notes.md"
commit_all "$HC_REPO" "chore: baseline"
printf '# notes\n\nmore\n' > "$HC_REPO/notes.md"; commit_all "$HC_REPO" "fix(docs): expand notes"
T22_PARENT="$(sha_of "$HC_REPO" HEAD)"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T22_HEAD="$(sha_of "$HC_REPO" HEAD)"
run_hook s22
check 108 "a first-turn fix commit blocks on the first Stop — contract:hook:inv-t22" 2 "$RC"
check 109 "first Stop reports (1/3) — contract:hook:inv-t22" yes "$(has "$ERR" "(1/3)")"
check 110 "last_checked_sha seeds to the blocked commit's first parent — contract:hook:inv-t22" \
  "$T22_PARENT" "$(st "$HC_REPO" s22 '.last_checked_sha')"
check 111 "last_checked_sha is NOT seeded to HEAD — contract:hook:inv-t22" no \
  "$(has "$(st "$HC_REPO" s22 '.last_checked_sha')" "$T22_HEAD")"
run_hook s22 true
check 112 "the second Stop re-blocks — contract:hook:inv-t22" 2 "$RC"
check 113 "the second Stop reports (2/3) — contract:hook:inv-t22" yes "$(has "$ERR" "(2/3)")"

hook_case t22empty
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
T22E_HEAD="$(sha_of "$HC_REPO" HEAD)"
run_hook s22empty
check 114 "a first Stop with no candidates allows — contract:hook:inv-t22" 0 "$RC"
check 115 "the seeded state carries exactly INV-C12's five fields — contract:hook:inv-t22" \
  "block_counts,last_checked_sha,seeded_at,sha_files,sha_group" \
  "$(st "$HC_REPO" s22empty '[keys[]]|sort|join(",")')"
check 116 "a candidate-free first Stop seeds last_checked_sha to HEAD — contract:hook:inv-t22" \
  "$T22E_HEAD" "$(st "$HC_REPO" s22empty '.last_checked_sha')"
check 117 "seeded_at is an integer epoch, not a string — contract:hook:inv-t22" \
  number "$(st "$HC_REPO" s22empty '.seeded_at|type')"

# seeded_at is the transcript's EARLIEST timestamp — not its last record and
# not its first line. Every other fixture's two records are five seconds apart
# while every commit date is months away, so earliest-vs-latest cannot move a
# verdict there. Here the LATER record is written first and the fix commit
# falls between the two.
hook_case t22earliest
{ echo '{"type":"user","timestamp":"2026-06-01T00:00:00.000Z"}'
  echo '{"type":"assistant","timestamp":"2026-05-01T00:00:00.000Z"}'; } > "$HC_TRANSCRIPT"
echo "V = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline" "2026-04-01T09:00:00+00:00"
echo "V = 1" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): mid-window repair" "2026-05-15T09:00:00+00:00"
run_hook s22earliest
check 295 "the session window opens at the transcript's earliest record — contract:hook:inv-t22" 2 "$RC"
check 296 "seeded_at is that earliest record's epoch — contract:hook:inv-t22" \
  "$(date -u -d "2026-05-01T00:00:00Z" +%s)" "$(st "$HC_REPO" s22earliest '.seeded_at')"

# ========================================================================
# INV-T23 — graceful degradation + the .last-run evidence trail.
# The kill-switch and malformed-JSON cases live INSIDE this scenario's block
# (G1: a tag may be named only by `check` calls in its own block, and every
# such call counts toward `checks=`), since INV-T23's own description pins
# "EVERY invocation (allowed/blocked/kill-switched) touches .last-run" and
# "first-ever invocation mkdir -p's grudge-guard/ before any kill-switch
# check". They additionally support INV-C8's grep-checked degradation clause.
# ========================================================================
# contract:hook:inv-t23 checks=88
hook_case t23nongit
mkdir -p "$HC_ROOT/notgit"
HC_CWD="$HC_ROOT/notgit"
run_hook s23nongit
check 118 "a non-git cwd allows — contract:hook:inv-t23" 0 "$RC"

hook_case t23nosid
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook_raw "$(printf '{"transcript_path":"%s","cwd":"%s","hook_event_name":"Stop","stop_hook_active":false}' \
  "$HC_TRANSCRIPT" "$HC_REPO")"
check 119 "a payload with no .session_id allows — contract:hook:inv-t23" 0 "$RC"
check 120 "a payload with no .session_id writes no state file — contract:hook:inv-t23" 0 \
  "$(find "$(guard_dir "$HC_REPO")" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l)"

hook_case t23blocked
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
rm -f "$(guard_dir "$HC_REPO")/.last-run"
run_hook s23blocked
check 121 "a BLOCKED invocation touches .last-run — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")/.last-run")"

hook_case t23quiet
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
rm -f "$(guard_dir "$HC_REPO")/.last-run"
run_hook s23quiet
check 122 "an ALLOWED invocation touches .last-run — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")/.last-run")"

rm -f "$(guard_dir "$HC_REPO")/.last-run"
HOOK_ENV="CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD=1"
run_hook s23quiet
HOOK_ENV=""
check 123 "the env-var kill-switch allows — contract:hook:inv-t23" 0 "$RC"
check 124 "the env-var kill-switch says it is disabled — contract:hook:inv-t23" yes "$(has "$ERR" "disabled")"
check 125 "an env-kill-switched invocation still touches .last-run — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")/.last-run")"

rm -f "$(guard_dir "$HC_REPO")/.last-run"
mkdir -p "$(mem_dir "$HC_REPO")"
touch "$(mem_dir "$HC_REPO")/.grudge-resolution-guard-disabled"
run_hook s23quiet
rm -f "$(mem_dir "$HC_REPO")/.grudge-resolution-guard-disabled"
check 126 "the sentinel-file kill-switch allows — contract:hook:inv-t23" 0 "$RC"
check 127 "the sentinel-file kill-switch says it is disabled — contract:hook:inv-t23" yes "$(has "$ERR" "disabled")"
check 128 "a sentinel-kill-switched invocation still touches .last-run — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")/.last-run")"

# First-EVER invocation on a kill-switched setup: grudge-guard/ does not exist
# yet, so the mkdir -p must run before the kill-switch check or the breadcrumb
# is never created at all.
hook_case t23killfirst
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
HOOK_ENV="CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD=1"
run_hook s23killfirst
HOOK_ENV=""
check 129 "a first-ever kill-switched invocation mkdir -p's grudge-guard/ — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")")"
check 130 "a first-ever kill-switched invocation touches .last-run — contract:hook:inv-t23" yes \
  "$(exists "$(guard_dir "$HC_REPO")/.last-run")"

# An unresolvable stale last_checked_sha must discard state and re-run the
# first-Stop full scan, not allow for the rest of the session.
hook_case t23stale
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
mkdir -p "$(guard_dir "$HC_REPO")"
cat > "$(guard_dir "$HC_REPO")/s23stale.json" <<'STALEJSON'
{"last_checked_sha":"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef","seeded_at":1767225600,
 "sha_group":{},"sha_files":{},"block_counts":{}}
STALEJSON
run_hook s23stale true
check 131 "an unresolvable last_checked_sha re-scans instead of allowing — contract:hook:inv-t23" 2 "$RC"
check 132 "the re-scan is a fresh first-Stop scan at (1/3) — contract:hook:inv-t23" yes "$(has "$ERR" "(1/3)")"

# SIG-3: a clearance lookup that fails internally degrades PER CANDIDATE
# (still blocked), never into a whole-Stop allow.
hook_case t23lookup
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T23L_FIX="$(sha_of "$HC_REPO" HEAD)"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: clearance-lookup degradation fixture needs a non-root uid"
else
  chmod 000 "$HC_STORE/$HC_KEY/grudges"
  run_hook s23lookup
  check 133 "an unreadable store still blocks the candidate — contract:hook:inv-t23" 2 "$RC"
  check 134 "the degraded Stop still counts as (1/3) — contract:hook:inv-t23" yes "$(has "$ERR" "(1/3)")"
  check 135 "the failed lookup is announced with its SHA — contract:hook:inv-t23" yes \
    "$(has "$ERR" "clearance lookup failed for $T23L_FIX")"
  check 136 "the failed lookup is treated as unresolved — contract:hook:inv-t23" yes \
    "$(has "$ERR" "treating as unresolved")"
  chmod 755 "$HC_STORE/$HC_KEY/grudges"
fi

hook_case t23malformed
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook_raw "{ this is not json"
check 137 "a malformed JSON payload allows — contract:hook:inv-t23" 0 "$RC"

# An unpersistable state file must degrade to ALLOW: with no durable state every
# Stop is a fresh first Stop, the counter restarts at (1/3), MAX_BLOCKS is never
# reached — and both escape hatches (skips.log and the sentinel) live under that
# same directory, so the loop would be unbreakable. `memory` is created as a
# regular FILE, so `mkdir -p .../memory/grudge-guard` fails with ENOTDIR for
# every uid, root included.
hook_case t23nostate
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23nostate
check 220 "premise: this fixture blocks while the state file IS writable — contract:hook:inv-t23" 2 "$RC"
rm -rf "$(mem_dir "$HC_REPO")"
mkdir -p "$(dirname "$(mem_dir "$HC_REPO")")"
: > "$(mem_dir "$HC_REPO")"
run_hook s23nostate true
check 221 "an unpersistable state file allows instead of blocking — contract:hook:inv-t23" 0 "$RC"
check 222 "the degraded Stop says the state could not be persisted — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
run_hook s23nostate true
check 223 "the next Stop allows too — no unbreakable (1/3) loop — contract:hook:inv-t23" 0 "$RC"

# `git -C` only chdirs: an inherited GIT_DIR/GIT_WORK_TREE still outranks it, so
# without the hook's `env -u` scrub every git call would silently resolve the
# OTHER repo and the guard would degrade into a silent, stderr-free allow.
hook_case t23gitenv
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T23GE_FIX="$(sha_of "$HC_REPO" HEAD)"
T23GE_OTHER="$HC_ROOT/otherrepo"
new_repo "$T23GE_OTHER"
T23GE_OTHER="$(cd "$T23GE_OTHER" && pwd -P)"
echo "OTHER = 0" > "$T23GE_OTHER/other.py"
commit_all "$T23GE_OTHER" "chore: unrelated baseline"
HOOK_ENV="GIT_DIR=$T23GE_OTHER/.git GIT_WORK_TREE=$T23GE_OTHER"
run_hook s23gitenv
HOOK_ENV=""
check 224 "an inherited GIT_DIR cannot redirect the hook git calls — contract:hook:inv-t23" 2 "$RC"
check 225 "the session repo own candidate is still named — contract:hook:inv-t23" yes \
  "$(has "$ERR" "$T23GE_FIX")"

# The other half of the same scrub: git's CONFIGURATION environment. These do
# not retarget the repo, they change what git REPORTS about it — and each of
# the three channels below silently turned this exact fixture into an allow,
# with nothing at all on stderr. GIT_CONFIG_KEY_n is INDEXED, so no literal
# drop list can ever be complete; the wrapper runs `env -i` with an allowlist
# instead, and one check per channel pins that.
_t23cfg_case() {
  hook_case "$1"
  echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
  echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
  T23CFG_FIX="$(sha_of "$HC_REPO" HEAD)"
}

_t23cfg_case t23cfgidx
HOOK_ENV="GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=i18n.logOutputEncoding GIT_CONFIG_VALUE_0=UTF-16"
run_hook s23cfgidx
HOOK_ENV=""
check 320 "an inherited GIT_CONFIG_COUNT/KEY/VALUE cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"
check 321 "the candidate survives the indexed config channel — contract:hook:inv-t23" yes \
  "$(has "$ERR" "$T23CFG_FIX")"

_t23cfg_case t23cfgglobal
printf '[i18n]\n\tlogOutputEncoding = UTF-16\n' > "$HC_ROOT/attacker.gitconfig"
HOOK_ENV="GIT_CONFIG_GLOBAL=$HC_ROOT/attacker.gitconfig GIT_CONFIG_SYSTEM=/dev/null"
run_hook s23cfgglobal
HOOK_ENV=""
check 322 "an inherited GIT_CONFIG_GLOBAL cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"

_t23cfg_case t23cfgparams
HOOK_ENV="GIT_CONFIG_PARAMETERS='i18n.logoutputencoding=UTF-16'"
run_hook s23cfgparams
HOOK_ENV=""
check 323 "an inherited GIT_CONFIG_PARAMETERS cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"

# The three checks above name channels the OLD denylist already named, so they
# cannot tell an allowlist from a denylist that merely got longer. These three
# can: not one of them appears in any drop list this hook has ever carried, and
# each one alone flipped the same fixture from enforcing to a silent allow. The
# property being pinned is "NOTHING outside the allowlist reaches git" — an
# enumeration of names rots the way the denylist did, so the fixtures are
# chosen from OUTSIDE every enumeration in the source.
#
# GIT_CONFIG_SYSTEM is the one that matters most: it is in the very config
# family the allowlist was introduced for, and it was in neither drop list.
_t23cfg_case t23cfgsystem
printf 'this is not valid git config\n' > "$HC_ROOT/bad.gitconfig"
HOOK_ENV="GIT_CONFIG_SYSTEM=$HC_ROOT/bad.gitconfig"
run_hook s23cfgsystem
HOOK_ENV=""
check 328 "an inherited GIT_CONFIG_SYSTEM cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"

# GIT_OBJECT_DIRECTORY and GIT_COMMON_DIR are two of Task 6's seven
# repository-location variables that the hook suite never pinned;
# GIT_COMMON_DIR is the one the hook's OWN store identity is derived from.
_t23cfg_case t23objdir
HOOK_ENV="GIT_OBJECT_DIRECTORY=$HC_ROOT/nonexistent-objects"
run_hook s23objdir
HOOK_ENV=""
check 329 "an inherited GIT_OBJECT_DIRECTORY cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"

_t23cfg_case t23commondir
git init -q "$HC_ROOT/decoy" >/dev/null 2>&1
HOOK_ENV="GIT_COMMON_DIR=$HC_ROOT/decoy/.git"
run_hook s23commondir
HOOK_ENV=""
check 330 "an inherited GIT_COMMON_DIR cannot disable enforcement — contract:hook:inv-t23" 2 "$RC"

# C1′. `test -s "$STATE_FILE"` is NOT the durability predicate the termination
# argument needs: a non-empty file left by an EARLIER successful persist
# satisfies it while the counter inside is frozen, so the block never reaches
# MAX_BLOCKS. The three fixtures below are the three shapes of "this Stop's own
# write did not land" — dir unwritable mid-session, a truncated file that can
# never be repaired, and a write whose `mv` succeeds but cannot be read back.
# Each blocks forever against a file-existence gate and allows against a
# verified-write gate.
hook_case t23frozen
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23frozen
check 235 "premise: Stop 1 blocks while the state dir is writable — contract:hook:inv-t23" 2 "$RC"
check 236 "premise: Stop 1 left a non-empty state file behind — contract:hook:inv-t23" yes \
  "$(if [ -s "$(guard_dir "$HC_REPO")/s23frozen.json" ]; then echo yes; else echo no; fi)"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the mid-session-unwritable fixture needs a non-root uid"
else
  # The disk fills (or perms change) BETWEEN two Stops. The stale file stays.
  chmod 500 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
  run_hook s23frozen true
  check 237 "a state dir gone unwritable mid-session allows — contract:hook:inv-t23" 0 "$RC"
  check 238 "the un-persisted Stop announces the failure — contract:hook:inv-t23" yes \
    "$(has "$ERR" "could not persist state")"
  check 239 "it never blocks on the frozen counter — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"
  run_hook s23frozen true
  check 240 "the Stop after that allows too — no unbreakable (2/3) loop — contract:hook:inv-t23" 0 "$RC"
  chmod 700 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
fi

# The ENOSPC shape: jq's output was truncated mid-write, so a NON-EMPTY but
# invalid state file landed and the now-unwritable dir can never be repaired.
# Every later Stop re-parses it as a first scan and re-blocks at (1/3).
hook_case t23trunc
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23trunc
check 241 "premise: Stop 1 blocks while the state dir is writable — contract:hook:inv-t23" 2 "$RC"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the truncated-state fixture needs a non-root uid"
else
  printf '{\n  "last_checked_sha": "0000",\n  "seeded_' > "$(guard_dir "$HC_REPO")/s23trunc.json"
  chmod 500 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
  run_hook s23trunc true
  check 242 "a truncated state file on an unwritable dir allows — contract:hook:inv-t23" 0 "$RC"
  check 243 "the truncated-state Stop announces the failure — contract:hook:inv-t23" yes \
    "$(has "$ERR" "could not persist state")"
  check 244 "it never blocks at a permanent (1/3) — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"
  run_hook s23trunc true
  check 245 "the Stop after that allows too — no unbreakable (1/3) loop — contract:hook:inv-t23" 0 "$RC"
  chmod 700 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
fi

# A DIRECTORY at the state path: `mv -f "$tmp" "$STATE_FILE"` moves the tmp
# INSIDE it and exits 0, and `test -s` is true of a directory — so both a
# file-existence gate and an mv-return-code gate pass while nothing durable was
# written. Only reading the file back catches it. Needs no special uid.
hook_case t23noreadback
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23noreadback
check 246 "premise: Stop 1 blocks with a normal state file — contract:hook:inv-t23" 2 "$RC"
rm -f "$(guard_dir "$HC_REPO")/s23noreadback.json"
mkdir -p "$(guard_dir "$HC_REPO")/s23noreadback.json"
check 247 "premise: the state path still satisfies test -s — contract:hook:inv-t23" yes \
  "$(if [ -s "$(guard_dir "$HC_REPO")/s23noreadback.json" ]; then echo yes; else echo no; fi)"
run_hook s23noreadback true
check 248 "a write that cannot be read back allows — contract:hook:inv-t23" 0 "$RC"
check 249 "the unreadable-back Stop announces the failure — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
check 250 "it never blocks at a permanent (1/3) — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"

# C1". The third mechanism of the same class, and the one that shows why the
# gate has to be PROGRESS and not landing: the hook writes, ITSELF, a state
# file with `seeded_at: 0` (the transcript's earliest timestamp is the unix
# epoch, so step 10's own derivation yields 0). That document lands perfectly
# and reads back byte-for-byte — and is then REJECTED by the next Stop's own
# loader at line 159, which throws `block_counts` away with it. Against any
# landing-only gate every Stop is a fresh first Stop at (1/3), forever, with no
# degradation note at all. Only comparing the counter now on disk against the
# counter that was on disk BEFORE the Stop catches it. Needs no special uid and
# no external tampering.
hook_case t23seed0
printf '{"type":"user","timestamp":"1970-01-01T00:00:00.000Z"}\n' > "$HC_TRANSCRIPT"
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23seed0
check 251 "premise: the epoch-transcript Stop 1 blocks — contract:hook:inv-t23" 2 "$RC"
check 252 "premise: the hook derived seeded_at 0 itself — contract:hook:inv-t23" 0 \
  "$(st "$HC_REPO" s23seed0 '.seeded_at')"
check 253 "premise: that write did persist a counter of 1 — contract:hook:inv-t23" 1 \
  "$(st "$HC_REPO" s23seed0 '[.block_counts[]]|add')"
run_hook s23seed0 true
check 254 "a counter its own loader discards is never blocked on — contract:hook:inv-t23" 0 "$RC"
check 255 "the un-advanced-counter Stop announces the failure — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
check 256 "it never blocks at a permanent (1/3) — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"
run_hook s23seed0 true
check 257 "the Stop after that allows too — no unbreakable (1/3) loop — contract:hook:inv-t23" 0 "$RC"

# The one state where "the counter on disk reached MAX_BLOCKS" is NOT this
# Stop's own achievement: a stale on-disk counter already at MAX_BLOCKS, under
# a state file the loader rejects (`seeded_at: 0`), on a dir where no write can
# ever land. This Stop legitimately computes 1 — but 3 is what is on disk, and
# a progress test that read the disk value without also demanding it be the
# value THIS Stop computed would see "3 >= MAX_BLOCKS" and block, forever. The
# durability half of the predicate is what refuses it.
hook_case t23stalemax
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T23SM_FIX="$(sha_of "$HC_REPO" HEAD)"
mkdir -p "$(guard_dir "$HC_REPO")"
cat > "$(guard_dir "$HC_REPO")/s23stalemax.json" <<STALEMAXJSON
{"last_checked_sha":"$T23SM_FIX","seeded_at":0,
 "sha_group":{"$T23SM_FIX":"$T23SM_FIX"},"sha_files":{"$T23SM_FIX":["app.py"]},
 "block_counts":{"$T23SM_FIX":3}}
STALEMAXJSON
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the stale-at-MAX_BLOCKS fixture needs a non-root uid"
else
  chmod 500 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
  run_hook s23stalemax true
  check 258 "a stale counter already at MAX_BLOCKS is not this Stop's progress — contract:hook:inv-t23" 0 "$RC"
  check 259 "the stale-at-MAX_BLOCKS Stop announces the failure — contract:hook:inv-t23" yes \
    "$(has "$ERR" "could not persist state")"
  check 260 "it never blocks on a counter it did not write — contract:hook:inv-t23" no \
    "$(has "$ERR" "attempt (")"
  chmod 700 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
fi

# C1‴. Step 12 is allowed to LOWER a counter — re-arm sets a joined,
# already-exhausted group back to MAX_BLOCKS-1, and the merge clamp does the
# same for a bridge. So this Stop can compute exactly the value that is already
# stale on disk, and `now == want` then holds by coincidence rather than by a
# write. (a) is the re-arm shape: a group at 3 on disk, a new SHA joining it,
# and a dir that can no longer be written. Re-arm 3->2, increment 2->3, the
# write fails, the untouched on-disk 3 reads back as "the 3 this Stop
# computed" — and the bound disjunct waved it through, at (3/3), forever.
hook_case t23rearm
echo "A = 0" > "$HC_REPO/a.py"; commit_all "$HC_REPO" "chore: baseline"
echo "A = 1" > "$HC_REPO/a.py"; commit_all "$HC_REPO" "fix(core): repair a" "2026-05-02T09:00:00+00:00"
run_hook s23rearm
run_hook s23rearm true
run_hook s23rearm true
check 261 "premise: three Stops walk the group to (3/3) — contract:hook:inv-t23" yes "$(has "$ERR" "(3/3)")"
check 262 "premise: the on-disk counter really reached MAX_BLOCKS — contract:hook:inv-t23" 3 \
  "$(st "$HC_REPO" s23rearm '[.block_counts[]]|add')"
echo "A = 2" > "$HC_REPO/a.py"; commit_all "$HC_REPO" "fix(core): repair a again" "2026-05-03T09:00:00+00:00"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the re-arm-at-MAX_BLOCKS fixture needs a non-root uid"
else
  chmod 500 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
  run_hook s23rearm true
  check 263 "a re-armed group on an unwritable dir allows — contract:hook:inv-t23" 0 "$RC"
  check 264 "the re-armed Stop announces the failure — contract:hook:inv-t23" yes \
    "$(has "$ERR" "could not persist state")"
  check 265 "it never blocks at a permanent (3/3) — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"
  run_hook s23rearm true
  check 266 "the Stop after that allows too — no unbreakable (3/3) loop — contract:hook:inv-t23" 0 "$RC"
  chmod 700 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
fi

# (b) the merge shape of the same coincidence, with no re-arm involved: two
# DISTINCT groups both at MAX_BLOCKS on disk, bridged by one new SHA that
# touches both their files, on a dir that can no longer be written. The clamp
# collapses them to MAX_BLOCKS-1, the increment restores MAX_BLOCKS, and the
# merged group's members carry an on-disk MAX_BLOCKS baseline of their own.
hook_case t23mergemax
echo "A = 0" > "$HC_REPO/a.py"; echo "B = 0" > "$HC_REPO/b.py"
commit_all "$HC_REPO" "chore: baseline"
echo "A = 1" > "$HC_REPO/a.py"; commit_all "$HC_REPO" "fix(a): repair a" "2026-05-02T09:00:00+00:00"
echo "B = 1" > "$HC_REPO/b.py"; commit_all "$HC_REPO" "fix(b): repair b" "2026-05-03T09:00:00+00:00"
run_hook s23mergemax
run_hook s23mergemax true
run_hook s23mergemax true
check 267 "premise: two independent groups each reach MAX_BLOCKS — contract:hook:inv-t23" "3,3" \
  "$(st "$HC_REPO" s23mergemax '[.block_counts[]]|sort|join(",")')"
echo "A = 2" > "$HC_REPO/a.py"; echo "B = 2" > "$HC_REPO/b.py"
commit_all "$HC_REPO" "fix(core): bridge a and b" "2026-05-04T09:00:00+00:00"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the merge-at-MAX_BLOCKS fixture needs a non-root uid"
else
  chmod 500 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
  run_hook s23mergemax true
  check 268 "a merge of exhausted groups on an unwritable dir allows — contract:hook:inv-t23" 0 "$RC"
  check 269 "the merged Stop announces the failure — contract:hook:inv-t23" yes \
    "$(has "$ERR" "could not persist state")"
  check 270 "it never blocks on the clamped-then-restored counter — contract:hook:inv-t23" no \
    "$(has "$ERR" "attempt (")"
  run_hook s23mergemax true
  check 271 "the Stop after the merge allows too — contract:hook:inv-t23" 0 "$RC"
  chmod 700 "$(guard_dir "$HC_REPO")" "$(mem_dir "$HC_REPO")"
fi

# A state file that EXISTS but yields no document is not a genuine first Stop.
# Truncated to empty before every Stop, each Stop re-scans from scratch,
# computes 1, writes 1, reads 1 back — and against a baseline read as 0 that
# looks like progress every time, so the guard blocks at (1/3) forever while
# nothing durable ever survives. The baseline is not 0 here; it is unmeasurable.
hook_case t23wiped
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23wiped
check 272 "premise: Stop 1 blocks at (1/3) with a normal state file — contract:hook:inv-t23" yes \
  "$(has "$ERR" "(1/3)")"
: > "$(guard_dir "$HC_REPO")/s23wiped.json"
run_hook s23wiped true
check 273 "a state file emptied before every Stop allows — contract:hook:inv-t23" 0 "$RC"
check 274 "the unmeasurable-baseline Stop announces the failure — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
check 275 "it never blocks at a permanent (1/3) — contract:hook:inv-t23" no "$(has "$ERR" "attempt (")"
: > "$(guard_dir "$HC_REPO")/s23wiped.json"
run_hook s23wiped true
check 276 "the Stop after that allows too — no unbreakable (1/3) loop — contract:hook:inv-t23" 0 "$RC"

# _prior_block_count has two halves and each is load-bearing on its own. Both
# fixtures below use `seeded_at: 0`, which step 9's loader rejects, so the
# in-memory counters start empty and this Stop legitimately computes 1 — while
# a 1 is already durably on disk. Progress therefore hinges entirely on the
# baseline lookup finding that 1.
# (a) the DIRECT same-id lookup: the on-disk sha_group is empty, so no member
#     walk can reach the counter; only PRIOR_COUNTS[$g] does.
hook_case t23priordirect
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T23PD_FIX="$(sha_of "$HC_REPO" HEAD)"
mkdir -p "$(guard_dir "$HC_REPO")"
cat > "$(guard_dir "$HC_REPO")/s23priordirect.json" <<PRIORDIRECTJSON
{"last_checked_sha":"$T23PD_FIX","seeded_at":0,
 "sha_group":{},"sha_files":{},"block_counts":{"$T23PD_FIX":1}}
PRIORDIRECTJSON
run_hook s23priordirect true
check 277 "a counter reachable only by the same-id lookup is still a baseline — contract:hook:inv-t23" 0 "$RC"
check 278 "the same-id-baseline Stop announces the failure — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
check 279 "it never re-blocks at (1/3) against its own stale counter — contract:hook:inv-t23" no \
  "$(has "$ERR" "attempt (")"

# (b) the MEMBER WALK: the counter is on disk under the group id the member
#     carried THEN, which is not the id step 12 mints now, so the direct
#     same-id lookup misses it and only following the member back reaches it.
hook_case t23priorwalk
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
T23PW_FIX="$(sha_of "$HC_REPO" HEAD)"
mkdir -p "$(guard_dir "$HC_REPO")"
cat > "$(guard_dir "$HC_REPO")/s23priorwalk.json" <<PRIORWALKJSON
{"last_checked_sha":"$T23PW_FIX","seeded_at":0,
 "sha_group":{"$T23PW_FIX":"oldgroupid"},"sha_files":{},
 "block_counts":{"oldgroupid":1}}
PRIORWALKJSON
run_hook s23priorwalk true
check 280 "a counter reachable only through the member walk is still a baseline — contract:hook:inv-t23" 0 "$RC"
check 281 "the renamed-group-baseline Stop announces the failure — contract:hook:inv-t23" yes \
  "$(has "$ERR" "could not persist state")"
check 282 "it never re-blocks at (1/3) against a renamed stale counter — contract:hook:inv-t23" no \
  "$(has "$ERR" "attempt (")"

# session_id is untrusted payload text used as a state-file NAME. Nothing else
# in this file pins where a PRESENT one may write — inv-t23 covers only a
# missing one. `../../../../settings` resolves out of the state dir and into
# $HC_HOME/.claude/, i.e. onto a file the user owns.
hook_case t23sid
mkdir -p "$HC_HOME/.claude"
printf '{"model":"opus"}\n' > "$HC_HOME/.claude/settings.json"
echo "V = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook "../../../../settings"
check 297 "a traversing session_id degrades to an allow — contract:hook:inv-t23" 0 "$RC"
check 298 "a traversing session_id writes nothing outside the state dir — contract:hook:inv-t23" \
  '{"model":"opus"}' "$(cat "$HC_HOME/.claude/settings.json")"
check 299 "the refused session_id is announced loudly — contract:hook:inv-t23" yes \
  "$(has "$ERR" "not a plain identifier")"

# A transcript with records but NO .timestamp seeds from wall-clock now and
# says so. No other fixture omits the field, so the fallback branch and its
# pinned warning are otherwise never executed at all; wall-clock now is far
# later than the fixture's commit dates, so the Stop allows.
hook_case t23nots
{ echo '{"type":"user"}'; echo '{"type":"assistant"}'; } > "$HC_TRANSCRIPT"
echo "V = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s23nots
check 300 "a transcript carrying no timestamp allows — contract:hook:inv-t23" 0 "$RC"
check 301 "the wall-clock fallback warns loudly — contract:hook:inv-t23" yes \
  "$(has "$ERR" "no timestamped record")"

# An unreadable transcript is an infra failure, not an empty session window:
# exit 0 BEFORE any state is written, so the next Stop still gets a real first
# scan. Reading it as "no timestamps" instead would seed and persist state.
hook_case t23notr
echo "V = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
HC_TRANSCRIPT="$HC_ROOT/transcript-that-does-not-exist.jsonl"
run_hook s23notr
check 302 "an unreadable transcript allows — contract:hook:inv-t23" 0 "$RC"
check 303 "an unreadable transcript writes no state — contract:hook:inv-t23" no \
  "$(exists "$(guard_dir "$HC_REPO")/s23notr.json")"

# ========================================================================
# INV-T24 — store-presence bootstrap across BOTH identity keys
# ========================================================================
# contract:hook:inv-t24 checks=22
# (a) the linked-worktree shape: the worktree's own basename key has no store
#     dir, but the shared-clone key does — enforcement must still run.
hook_case t24wt
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbr
T24_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24_WT" wtbr
T24_WT="$(cd "$T24_WT" && pwd -P)"
echo "VALUE = 1" > "$T24_WT/app.py"
commit_all "$T24_WT" "fix(widget): repair inside the linked worktree"
T24_FIX="$(sha_of "$T24_WT" HEAD)"
HC_CWD="$T24_WT"
check 138 "fixture: the worktree key really differs from the shared key — contract:hook:inv-t24" no \
  "$(has "$(basename "$T24_WT")" "$HC_KEY")"
run_hook s24wt
check 139 "shared-clone store present blocks from a linked worktree — contract:hook:inv-t24" 2 "$RC"
check 140 "the worktree candidate is named — contract:hook:inv-t24" yes "$(has "$ERR" "$T24_FIX")"
# The prefill's identity pair is UNCONDITIONALLY the shared clone's. This is the
# only fixture where that is discriminating: here the worktree pair
# (linked/, "linked") and the shared-clone pair ($HC_REPO, "$HC_KEY") differ.
check 231 "prefill uses the shared-clone --repo-root, not the worktree's — contract:hook:inv-t24" yes \
  "$(has "$ERR" "--repo-root \"$HC_REPO\"")"
check 232 "prefill uses the shared-clone --repo key, not the worktree key — contract:hook:inv-t24" yes \
  "$(has "$ERR" "--repo=\"$HC_KEY\"")"

# (b) neither key has a store dir -> allow once, loudly.
hook_case t24none
rm -rf "$HC_STORE/$HC_KEY"
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): repair the widget"
run_hook s24none
check 141 "both store keys absent allows — contract:hook:inv-t24" 0 "$RC"
check 142 "both store keys absent says so — contract:hook:inv-t24" yes "$(has "$ERR" "no grudge store")"

# (c) The clearance LOOKUP's identity pair, not just the prefill's. The design
#     pins BOTH to the shared-clone pair with no conditional branch, and a
#     linked worktree is the only shape where the worktree pair and the
#     shared-clone pair differ — so it is the only shape that can tell them
#     apart. A grudge recorded under the shared-clone identity must clear a
#     candidate seen from inside the worktree: the round trip the design's
#     worktree-identity closure claims, exercised end to end.
hook_case t24wtc
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbrc
T24C_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24C_WT" wtbrc
T24C_WT="$(cd "$T24C_WT" && pwd -P)"
echo "VALUE = 1" > "$T24C_WT/app.py"; echo "L = 1" > "$T24C_WT/lib.py"
commit_all "$T24C_WT" "fix(widget): repair from inside the linked worktree"
T24C_FIX="$(sha_of "$T24C_WT" HEAD)"
HC_CWD="$T24C_WT"
run_hook s24wtc
check 304 "premise: the worktree candidate blocks with an empty store — contract:hook:inv-t24" 2 "$RC"
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "the widget regressed" "app.py" "$T24C_FIX" "2026-04-01" >/dev/null
run_hook s24wtc true
check 305 "a shared-clone grudge clears a worktree candidate by commit — contract:hook:inv-t24" 0 "$RC"

# (d) the same round trip through the --by-files lookup: this grudge records no
#     commit, so --by-commit misses and the file-set branch has to carry it.
hook_case t24wtf
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbrf
T24F_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24F_WT" wtbrf
T24F_WT="$(cd "$T24F_WT" && pwd -P)"
echo "VALUE = 1" > "$T24F_WT/app.py"; echo "L = 1" > "$T24F_WT/lib.py"
commit_all "$T24F_WT" "fix(widget): repair from inside the linked worktree"
HC_CWD="$T24F_WT"
run_hook s24wtf
check 306 "premise: the by-files candidate blocks with an empty store — contract:hook:inv-t24" 2 "$RC"
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "app and lib regressed" "app.py,lib.py" "" "2026-04-01" >/dev/null
run_hook s24wtf true
check 307 "a shared-clone grudge clears a worktree candidate by files — contract:hook:inv-t24" 0 "$RC"

# (e) the same round trip through the OTHER identity — the one the writers
#     actually use. `grudge_append.resolve_repo()` keys a record by
#     `git rev-parse --show-toplevel`, i.e. the WORKTREE, whenever no
#     --repo/--repo-root is passed, and neither skills/grudge nor merge-pr
#     Step 7.5 passes them. Step 7 arms on either key, so step 13 must query
#     either key: a worktree-keyed grudge has to clear a worktree candidate.
hook_case t24wtown
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbrown
T24O_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24O_WT" wtbrown
T24O_WT="$(cd "$T24O_WT" && pwd -P)"
echo "VALUE = 1" > "$T24O_WT/app.py"; echo "L = 1" > "$T24O_WT/lib.py"
commit_all "$T24O_WT" "fix(widget): repair from inside the linked worktree"
T24O_FIX="$(sha_of "$T24O_WT" HEAD)"
HC_CWD="$T24O_WT"
run_hook s24wtown
check 333 "premise: no worktree-keyed grudge yet, so the candidate blocks — contract:hook:inv-t24" 2 "$RC"
append_grudge "$HC_STORE" "$(basename "$T24O_WT")" "$T24O_WT" "the widget regressed" \
  "app.py" "$T24O_FIX" "2026-04-01" >/dev/null
run_hook s24wtown true
check 334 "a worktree-keyed grudge clears a worktree candidate — contract:hook:inv-t24" 0 "$RC"

# (f) and through the --by-files lookup, which is a SECOND fallback site: this
#     grudge records no commit, so the by-commit fallback misses too and only
#     the file-set one can carry it. Without its own fixture that branch is
#     deletable with every other check still green.
hook_case t24wtownf
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbrownf
T24OF_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24OF_WT" wtbrownf
T24OF_WT="$(cd "$T24OF_WT" && pwd -P)"
echo "VALUE = 1" > "$T24OF_WT/app.py"; echo "L = 1" > "$T24OF_WT/lib.py"
commit_all "$T24OF_WT" "fix(widget): repair from inside the linked worktree"
HC_CWD="$T24OF_WT"
run_hook s24wtownf
check 335 "premise: the by-files worktree candidate blocks first — contract:hook:inv-t24" 2 "$RC"
append_grudge "$HC_STORE" "$(basename "$T24OF_WT")" "$T24OF_WT" "app and lib regressed" \
  "app.py,lib.py" "" "2026-04-01" >/dev/null
run_hook s24wtownf true
check 336 "a worktree-keyed grudge clears a worktree candidate by files — contract:hook:inv-t24" 0 "$RC"

# (g) LOOKUP ORDER. Both PRIMARY (shared-key) lookups must run before EITHER
#     worktree fallback, and a degraded FALLBACK must not abandon the
#     candidate. Interleaved the other way, a worktree store that merely cannot
#     be READ — mode 000, a foreign uid after a sudo/container run, a stale NFS
#     mount — made the fallback's `|| continue` swallow a clearance the shared
#     `--by-files` primary would have granted, blocking a resolved candidate to
#     MAX_BLOCKS and then to the unenforced give-up.
hook_case t24order
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbrord
T24R_WT="$HC_ROOT/linked"
git -C "$HC_REPO" worktree add -q "$T24R_WT" wtbrord
T24R_WT="$(cd "$T24R_WT" && pwd -P)"
echo "VALUE = 1" > "$T24R_WT/app.py"; echo "L = 1" > "$T24R_WT/lib.py"
commit_all "$T24R_WT" "fix(widget): repair from inside the linked worktree"
HC_CWD="$T24R_WT"
run_hook s24order
check 337 "premise: the ordering fixture's candidate blocks with an empty store — contract:hook:inv-t24" 2 "$RC"
# The worktree store DIR has to exist for the fallback to arm at all; only its
# `grudges/` payload is made unreadable, so `-d` still sees it.
T24R_STORE="$HC_STORE/$(basename "$T24R_WT")/grudges"
mkdir -p "$T24R_STORE"
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP: the unreadable-worktree-store ordering fixture needs a non-root uid"
else
  chmod 000 "$T24R_STORE"
  run_hook s24order true
  check 338 "premise: the unreadable worktree store really degrades a lookup — contract:hook:inv-t24" yes \
    "$(has "$ERR" "clearance lookup failed")"
  check 339 "premise: it still blocks while nothing has cleared it — contract:hook:inv-t24" 2 "$RC"
  append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "app and lib regressed" \
    "app.py,lib.py" "" "2026-04-01" >/dev/null
  run_hook s24order true
  check 340 "a degraded worktree fallback cannot suppress the shared by-files clearance — contract:hook:inv-t24" 0 "$RC"
  chmod 700 "$T24R_STORE"
fi

# (h) The fallback arms on PATH IDENTITY, not on basename inequality.
#     `git worktree add ~/wt/proj` off `~/src/proj` gives both roots the SAME
#     basename, so a `$WORKTREE_KEY != $SHARED_KEY` guard disarms in exactly
#     the shape the fallback exists for, and the worktree-keyed grudge (e)/(f)
#     show the writers produce goes unseen all over again.
hook_case t24eqbase
echo "VALUE = 0" > "$HC_REPO/app.py"; echo "L = 0" > "$HC_REPO/lib.py"
commit_all "$HC_REPO" "chore: baseline"
git -C "$HC_REPO" branch wtbreq
mkdir -p "$HC_ROOT/elsewhere"
T24E_WT="$HC_ROOT/elsewhere/$HC_KEY"
git -C "$HC_REPO" worktree add -q "$T24E_WT" wtbreq
T24E_WT="$(cd "$T24E_WT" && pwd -P)"
check 341 "fixture: the worktree basename EQUALS the shared key — contract:hook:inv-t24" yes \
  "$(has "$(basename "$T24E_WT")" "$HC_KEY")"
echo "VALUE = 1" > "$T24E_WT/app.py"; echo "L = 1" > "$T24E_WT/lib.py"
commit_all "$T24E_WT" "fix(widget): repair from the equal-basename worktree"
T24E_FIX="$(sha_of "$T24E_WT" HEAD)"
HC_CWD="$T24E_WT"
run_hook s24eqbase
check 342 "premise: the equal-basename worktree candidate blocks — contract:hook:inv-t24" 2 "$RC"
append_grudge "$HC_STORE" "$(basename "$T24E_WT")" "$T24E_WT" "the widget regressed" \
  "app.py" "$T24E_FIX" "2026-04-01" >/dev/null
run_hook s24eqbase true
check 343 "a worktree-keyed grudge clears when the basenames collide — contract:hook:inv-t24" 0 "$RC"

# ========================================================================
# INV-T19 — grouping by changed-file overlap, one increment per group per
# Stop, and the clearance counter reset
# ========================================================================
# contract:group:inv-t19 checks=51
# (a) two candidates sharing NO files -> two independent one-member groups
hook_case t19a
echo "A = 0" > "$HC_REPO/a.py"; echo "B = 0" > "$HC_REPO/b.py"
commit_all "$HC_REPO" "chore: baseline"
echo "A = 1" > "$HC_REPO/a.py"; commit_all "$HC_REPO" "fix(a): repair a"
T19A_A="$(sha_of "$HC_REPO" HEAD)"
echo "B = 1" > "$HC_REPO/b.py"; commit_all "$HC_REPO" "fix(b): repair b"
T19A_B="$(sha_of "$HC_REPO" HEAD)"
run_hook s19a
check 143 "disjoint candidates block — contract:group:inv-t19" 2 "$RC"
check 144 "disjoint candidates are two groups in one message — contract:group:inv-t19" yes \
  "$(has "$ERR" "2 unresolved fix(*) group(s)")"
check 145 "the first disjoint candidate is named — contract:group:inv-t19" yes "$(has "$ERR" "$T19A_A")"
check 146 "the second disjoint candidate is named — contract:group:inv-t19" yes "$(has "$ERR" "$T19A_B")"
check 147 "sha_group records two distinct group ids — contract:group:inv-t19" 2 \
  "$(st "$HC_REPO" s19a '[.sha_group[]]|unique|length')"
check 148 "each disjoint group has its own counter — contract:group:inv-t19" 2 \
  "$(st "$HC_REPO" s19a '.block_counts|length')"
add_skip "$HC_REPO" "$T19A_A skipping only the a.py fix"
run_hook s19a true
check 149 "clearing one group leaves the other blocking — contract:group:inv-t19" 2 "$RC"
check 150 "only the still-unresolved group is reported — contract:group:inv-t19" yes \
  "$(has "$ERR" "1 unresolved fix(*) group(s)")"
check 151 "the cleared candidate is no longer named — contract:group:inv-t19" no "$(has "$ERR" "$T19A_A")"
check 152 "the independent counter advanced to (2/3) — contract:group:inv-t19" yes "$(has "$ERR" "(2/3)")"

# (b) two candidates sharing a file -> ONE group, one counter, and one skip
#     naming EITHER same-Stop member clears both
hook_case t19b
echo "S = 0" > "$HC_REPO/shared.py"
commit_all "$HC_REPO" "chore: baseline"
echo "S = 1" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(shared): part one"
T19B_A="$(sha_of "$HC_REPO" HEAD)"
echo "S = 2" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(shared): part two"
T19B_B="$(sha_of "$HC_REPO" HEAD)"
run_hook s19b
check 153 "file-sharing candidates block — contract:group:inv-t19" 2 "$RC"
check 154 "file-sharing candidates collapse to one group — contract:group:inv-t19" yes \
  "$(has "$ERR" "1 unresolved fix(*) group(s)")"
check 155 "both members of the group are named — contract:group:inv-t19" yes \
  "$(if [ "$(has "$ERR" "$T19B_A")" = yes ] && [ "$(has "$ERR" "$T19B_B")" = yes ]; then echo yes; else echo no; fi)"
check 156 "the group has a single counter entry — contract:group:inv-t19" 1 \
  "$(st "$HC_REPO" s19b '.block_counts|length')"
check 157 "both SHAs map to the same frozen group_id — contract:group:inv-t19" true \
  "$(st "$HC_REPO" s19b ".sha_group[\"$T19B_A\"] == .sha_group[\"$T19B_B\"]")"
check 158 "the counter incremented once, not once per member — contract:group:inv-t19" 1 \
  "$(st "$HC_REPO" s19b ".block_counts[.sha_group[\"$T19B_A\"]]")"
add_skip "$HC_REPO" "$T19B_B one skip for the second member"
run_hook s19b true
check 159 "one skip naming either member clears the whole group — contract:group:inv-t19" 0 "$RC"

# (c)+(d) transitive A-B / B-C overlap makes ONE 3-member group that takes
#         three Stops to exhaust
hook_case t19c
for f in x y z w; do echo "V = 0" > "$HC_REPO/$f.py"; done
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/x.py"; echo "V = 1" > "$HC_REPO/y.py"
commit_all "$HC_REPO" "fix(a): x and y"
T19C_A="$(sha_of "$HC_REPO" HEAD)"
echo "V = 2" > "$HC_REPO/y.py"; echo "V = 1" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "fix(b): y and z"
T19C_B="$(sha_of "$HC_REPO" HEAD)"
echo "V = 2" > "$HC_REPO/z.py"; echo "V = 1" > "$HC_REPO/w.py"
commit_all "$HC_REPO" "fix(c): z and w"
T19C_C="$(sha_of "$HC_REPO" HEAD)"
run_hook s19c
check 160 "the transitive trio blocks — contract:group:inv-t19" 2 "$RC"
check 161 "A-B/B-C with no direct A-C is ONE group — contract:group:inv-t19" yes \
  "$(has "$ERR" "1 unresolved fix(*) group(s)")"
check 162 "all three SHAs are recorded in sha_group — contract:group:inv-t19" 3 \
  "$(st "$HC_REPO" s19c '.sha_group|length')"
check 163 "all three share one group id — contract:group:inv-t19" 1 \
  "$(st "$HC_REPO" s19c '[.sha_group[]]|unique|length')"
check 164 "A and C join transitively despite no shared file — contract:group:inv-t19" true \
  "$(st "$HC_REPO" s19c ".sha_group[\"$T19C_A\"] == .sha_group[\"$T19C_C\"]")"
check 165 "Stop 1 leaves block_counts at 1 — contract:group:inv-t19" 1 \
  "$(st "$HC_REPO" s19c ".block_counts[.sha_group[\"$T19C_B\"]]")"
check 166 "Stop 1 reports (1/3) — contract:group:inv-t19" yes "$(has "$ERR" "(1/3)")"
run_hook s19c true
check 167 "Stop 2 re-blocks the trio — contract:group:inv-t19" 2 "$RC"
check 168 "Stop 2 leaves block_counts at 2 — contract:group:inv-t19" 2 \
  "$(st "$HC_REPO" s19c ".block_counts[.sha_group[\"$T19C_B\"]]")"
check 169 "Stop 2 reports (2/3) — contract:group:inv-t19" yes "$(has "$ERR" "(2/3)")"
run_hook s19c true
check 170 "Stop 3 re-blocks the trio — contract:group:inv-t19" 2 "$RC"
check 171 "Stop 3 leaves block_counts at 3 — contract:group:inv-t19" 3 \
  "$(st "$HC_REPO" s19c ".block_counts[.sha_group[\"$T19C_B\"]]")"
check 172 "Stop 3 reports (3/3) — contract:group:inv-t19" yes "$(has "$ERR" "(3/3)")"
run_hook s19c true
check 173 "Stop 4 gives up on the trio — contract:group:inv-t19" 0 "$RC"

# (e) clearance-then-rejoin (FATAL-1 r2): a joiner must NOT inherit the
#     cleared group's spent counter
hook_case t19e
echo "H = 0" > "$HC_REPO/hub.py"
commit_all "$HC_REPO" "chore: baseline"
echo "H = 1" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c): first hub fix"
T19E_C="$(sha_of "$HC_REPO" HEAD)"
run_hook s19e
check 174 "the first hub fix blocks — contract:group:inv-t19" 2 "$RC"
check 175 "the first hub fix reports (1/3) — contract:group:inv-t19" yes "$(has "$ERR" "(1/3)")"
run_hook s19e true
check 176 "the first hub fix re-blocks — contract:group:inv-t19" 2 "$RC"
check 177 "the first hub fix reports (2/3) — contract:group:inv-t19" yes "$(has "$ERR" "(2/3)")"
check 178 "block_counts reached 2 before clearance — contract:group:inv-t19" 2 \
  "$(st "$HC_REPO" s19e ".block_counts[.sha_group[\"$T19E_C\"]]")"
add_skip "$HC_REPO" "$T19E_C clearing the first hub fix"
run_hook s19e true
check 179 "the cleared group allows — contract:group:inv-t19" 0 "$RC"
check 180 "clearance resets block_counts to 0 — contract:group:inv-t19" 0 \
  "$(st "$HC_REPO" s19e ".block_counts[.sha_group[\"$T19E_C\"]]")"
echo "H = 2" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(d): second hub fix"
T19E_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s19e true
check 181 "a new joiner on a cleared group blocks — contract:group:inv-t19" 2 "$RC"
check 182 "the joiner starts at (1/3), not (3/3) — contract:group:inv-t19" yes "$(has "$ERR" "(1/3)")"
check 183 "the joiner is named — contract:group:inv-t19" yes "$(has "$ERR" "$T19E_D")"
check 184 "the already-cleared member is not named — contract:group:inv-t19" no "$(has "$ERR" "$T19E_C")"
check 185 "the joiner lands in the same persisted group — contract:group:inv-t19" true \
  "$(st "$HC_REPO" s19e ".sha_group[\"$T19E_D\"] == .sha_group[\"$T19E_C\"]")"
run_hook s19e true
check 186 "the joiner re-blocks at (2/3) — contract:group:inv-t19" yes "$(has "$ERR" "(2/3)")"
run_hook s19e true
check 187 "the joiner re-blocks at (3/3) — contract:group:inv-t19" yes "$(has "$ERR" "(3/3)")"

# (f) the GRUDGE half of the clearance clause: one recorded grudge naming ONE
#     member of a shared-file group clears the whole group (exact-commit match).
#     The grudge names the OLDER member and carries a fixed_in_commit that is
#     reachable from HEAD, so the file-set branch cannot match it.
hook_case t19f
echo "S = 0" > "$HC_REPO/shared.py"
commit_all "$HC_REPO" "chore: baseline"
echo "S = 1" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(shared): part one"
T19F_A="$(sha_of "$HC_REPO" HEAD)"
echo "S = 2" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(shared): part two"
run_hook s19f
check 226 "premise: the un-grudged pair blocks — contract:group:inv-t19" 2 "$RC"
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "shared.py regressed" "shared.py" \
  "$T19F_A" "2026-05-01" >/dev/null
run_hook s19f true
check 227 "one grudge naming either same-Stop member clears both — contract:group:inv-t19" 0 "$RC"

# (g) the file-set half: a grudge with NO fixed_in_commit, two surviving files
#     that are a subset of the candidate's, and date_fixed on or before the
#     candidate's UTC author date, clears it with no commit id involved.
hook_case t19g
echo "P = 0" > "$HC_REPO/p.py"; echo "Q = 0" > "$HC_REPO/q.py"
commit_all "$HC_REPO" "chore: baseline"
echo "P = 1" > "$HC_REPO/p.py"; echo "Q = 1" > "$HC_REPO/q.py"
commit_all "$HC_REPO" "fix(pq): repair p and q"
run_hook s19g
check 228 "premise: the un-grudged candidate blocks — contract:group:inv-t19" 2 "$RC"
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "p and q regressed together" "p.py,q.py" \
  "" "2026-04-01" >/dev/null
run_hook s19g true
check 229 "a commit-less grudge clears via the file-set match — contract:group:inv-t19" 0 "$RC"

# (h) group_id is frozen at the group's OLDEST member — the first commit the
#     guard ever saw — not at whichever member the grouping loop reaches first.
#     Every other group-identity assertion in this file is relational
#     (`A == B`, `unique|length`), and a newest-first walk satisfies all of them
#     while naming the group after the wrong commit.
hook_case t19h
echo "S = 0" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "chore: baseline"
echo "S = 1" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(c): first touch of shared"
T19H_C="$(sha_of "$HC_REPO" HEAD)"
echo "S = 2" > "$HC_REPO/shared.py"; commit_all "$HC_REPO" "fix(d): second touch of shared"
T19H_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s19h
check 308 "the group id is the OLDEST member's own SHA — contract:group:inv-t19" "$T19H_C" \
  "$(st "$HC_REPO" s19h ".sha_group[\"$T19H_C\"]")"
check 309 "the later member carries that same frozen id — contract:group:inv-t19" "$T19H_C" \
  "$(st "$HC_REPO" s19h ".sha_group[\"$T19H_D\"]")"

# ========================================================================
# INV-T20 — clearance is scoped to THIS Stop's in-scope set (round-14 Fatal 1)
# ========================================================================
# The complementary fixture — asserting C2 is ALLOWED unblocked on the join
# Stop — must FAIL against the implementation; that is the regression this
# scenario exists to catch.
# contract:group:inv-t20 checks=13
hook_case t20
echo "H = 0" > "$HC_REPO/hub.py"
commit_all "$HC_REPO" "chore: baseline"
echo "H = 1" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c1): first hub fix"
T20_C1="$(sha_of "$HC_REPO" HEAD)"
run_hook s20
check 188 "C1 blocks on its first Stop — contract:group:inv-t20" 2 "$RC"
check 189 "C1's first Stop reports (1/3) — contract:group:inv-t20" yes "$(has "$ERR" "(1/3)")"
add_skip "$HC_REPO" "$T20_C1 skipping C1"
run_hook s20 true
check 190 "the skip clears C1 — contract:group:inv-t20" 0 "$RC"
check 191 "last_checked_sha advances past the cleared C1 — contract:group:inv-t20" \
  "$(sha_of "$HC_REPO" HEAD)" "$(st "$HC_REPO" s20 '.last_checked_sha')"
check 192 "sha_group still holds C1 after clearance — contract:group:inv-t20" true \
  "$(st "$HC_REPO" s20 '.sha_group|has("'"$T20_C1"'")')"
check 193 "sha_files still holds C1 after clearance — contract:group:inv-t20" true \
  "$(st "$HC_REPO" s20 '.sha_files|has("'"$T20_C1"'")')"
echo "H = 2" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c2): second hub fix"
T20_C2="$(sha_of "$HC_REPO" HEAD)"
run_hook s20 true
check 194 "C2 joining C1's persisted group is BLOCKED — contract:group:inv-t20" 2 "$RC"
check 195 "C2 is named in the block message — contract:group:inv-t20" yes "$(has "$ERR" "$T20_C2")"
check 196 "C1's old skip confers nothing on C2 — contract:group:inv-t20" yes "$(has "$ERR" "(1/3)")"
check 197 "C2 really did join C1's persisted group — contract:group:inv-t20" true \
  "$(st "$HC_REPO" s20 ".sha_group[\"$T20_C2\"] == .sha_group[\"$T20_C1\"]")"
# The grudge half of the same clause: a recorded grudge naming the joiner does
# clear the persisted group on the next Stop.
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "hub.py regressed again" "hub.py" \
  "$T20_C2" "2026-05-01" >/dev/null
run_hook s20 true
check 230 "a grudge naming the joiner clears the persisted group — contract:group:inv-t20" 0 "$RC"

# The NEGATIVE grudge case — the half of the clause the eight skip-path checks
# above leave unpinned. Same clause, other door: "persisted membership alone is
# never sufficient for a member to confer or receive clearance". The grudge
# names an OUT-OF-SCOPE persisted member (C1, already behind last_checked_sha),
# so the group must NOT clear; only a grudge naming a commit in THIS Stop's
# in-scope set may. Check 230 above is the in-scope positive; this is its
# out-of-scope negative. A step-13 loop that ran --by-commit over every
# persisted member of the group instead of over IS_SHA passes every other check
# in this file — including the frozen acceptance oracle — and reds only here.
# The grudge's fixed_in_commit is reachable from HEAD, so (as in t19f) the
# one-survivor file-set branch cannot match it either.
hook_case t20b
echo "H = 0" > "$HC_REPO/hub.py"
commit_all "$HC_REPO" "chore: baseline"
echo "H = 1" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c1): first hub fix"
T20B_C1="$(sha_of "$HC_REPO" HEAD)"
run_hook s20b
add_skip "$HC_REPO" "$T20B_C1 skipping C1"
run_hook s20b true
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "hub.py regressed" "hub.py" \
  "$T20B_C1" "2026-05-01" >/dev/null
echo "H = 2" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c3): later hub fix"
T20B_C3="$(sha_of "$HC_REPO" HEAD)"
run_hook s20b true
# Fixture premise, asserted as a hard abort rather than a `check` so the tag
# arithmetic above is unchanged: the candidate must really have joined C1's
# persisted group. On a private group the two checks below would pass while
# pinning nothing.
if [ "$(st "$HC_REPO" s20b ".sha_group[\"$T20B_C3\"] == .sha_group[\"$T20B_C1\"]")" != "true" ]; then
  echo "FIXTURE ERROR: t20b candidate did not join C1's persisted group" >&2
  exit 1
fi
check 331 "a grudge naming an out-of-scope persisted member does not clear the group — contract:group:inv-t20" 2 "$RC"
check 332 "the never-before-seen candidate still blocks at (1/3) — contract:group:inv-t20" yes "$(has "$ERR" "(1/3)")"

# ========================================================================
# INV-T21 — join / merge re-arm
# ========================================================================
# contract:group:inv-t21 checks=45
# (a) two disjoint count-1 groups bridged by a NEW candidate: merged count is
#     max(1,1)=1, plus this Stop's single increment -> persisted 2. A summing
#     implementation persists 3; a no-increment one persists 1.
hook_case t21a
for f in x y z; do echo "V = 0" > "$HC_REPO/$f.py"; done
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/x.py"; echo "V = 1" > "$HC_REPO/y.py"
commit_all "$HC_REPO" "fix(c): x and y"
T21A_C="$(sha_of "$HC_REPO" HEAD)"
echo "V = 1" > "$HC_REPO/z.py"; commit_all "$HC_REPO" "fix(d): z only"
T21A_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s21a
check 198 "the two pre-merge groups block — contract:group:inv-t21" 2 "$RC"
check 199 "they start as two distinct groups — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21a '.block_counts|length')"
check 200 "each pre-merge group is at 1 — contract:group:inv-t21" "1" \
  "$(st "$HC_REPO" s21a '[.block_counts[]]|unique|map(tostring)|join(",")')"
echo "V = 2" > "$HC_REPO/y.py"; echo "V = 2" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "fix(e): y and z bridge"
T21A_E="$(sha_of "$HC_REPO" HEAD)"
run_hook s21a true
check 201 "the bridging candidate is blocked on the merge Stop — contract:group:inv-t21" 2 "$RC"
check 202 "the bridging candidate is named — contract:group:inv-t21" yes "$(has "$ERR" "$T21A_E")"
check 203 "the merge collapses to one counter — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21a '.block_counts|length')"
check 204 "merged count is max(1,1)+1 = 2 — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21a ".block_counts[.sha_group[\"$T21A_E\"]]")"
check 205 "all three bridged SHAs share the canonical id — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21a '[.sha_group[]]|unique|length')"
add_skip "$HC_REPO" "$T21A_C one skip for the merged group"
run_hook s21a true
check 206 "one skip clears the whole merged group — contract:group:inv-t21" 0 "$RC"

# (b) a NEW member joining an EXHAUSTED group re-arms it to MAX_BLOCKS-1
hook_case t21b
echo "H = 0" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "chore: baseline"
echo "H = 1" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(c): hub fix"
T21B_C="$(sha_of "$HC_REPO" HEAD)"
run_hook s21b; run_hook s21b true; run_hook s21b true
check 207 "the group is exhausted after three Stops — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21b ".block_counts[.sha_group[\"$T21B_C\"]]")"
echo "H = 2" > "$HC_REPO/hub.py"; commit_all "$HC_REPO" "fix(d): second hub fix"
T21B_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s21b true
check 208 "joining an exhausted group re-arms and blocks — contract:group:inv-t21" 2 "$RC"
check 209 "the new member is named on the join Stop — contract:group:inv-t21" yes "$(has "$ERR" "$T21B_D")"
check 210 "re-arm min(3,2)=2 plus one increment persists 3 — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21b ".block_counts[.sha_group[\"$T21B_D\"]]")"
run_hook s21b true
check 211 "the Stop after the re-armed block allows — contract:group:inv-t21" 0 "$RC"
check 212 "the give-up note re-fires after the re-arm — contract:group:inv-t21" yes "$(has "$ERR" "giving up")"

# (c) two EQUAL-count exhausted groups bridged by one new SHA still block
hook_case t21c
echo "V = 0" > "$HC_REPO/x.py"; echo "V = 0" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/x.py"; commit_all "$HC_REPO" "fix(c): x only"
T21C_C="$(sha_of "$HC_REPO" HEAD)"
echo "V = 1" > "$HC_REPO/z.py"; commit_all "$HC_REPO" "fix(d): z only"
T21C_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s21c; run_hook s21c true; run_hook s21c true
check 213 "both groups exist before the merge — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21c '.block_counts|length')"
check 214 "both groups are exhausted at 3 — contract:group:inv-t21" "3" \
  "$(st "$HC_REPO" s21c '[.block_counts[]]|unique|map(tostring)|join(",")')"
echo "V = 2" > "$HC_REPO/x.py"; echo "V = 2" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "fix(e): x and z bridge"
T21C_E="$(sha_of "$HC_REPO" HEAD)"
run_hook s21c true
check 215 "an equal-count (3,3) merge still blocks — contract:group:inv-t21" 2 "$RC"
check 216 "the bridging SHA is named — contract:group:inv-t21" yes "$(has "$ERR" "$T21C_E")"
check 217 "the equal-count merge collapses to one counter — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21c '.block_counts|length')"
check 218 "min(max(3,3),2)=2 plus one increment persists 3 — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21c ".block_counts[.sha_group[\"$T21C_E\"]]")"
run_hook s21c true
check 219 "the Stop after the equal-count merge allows — contract:group:inv-t21" 0 "$RC"

# (d) UNEQUAL counts — the only shape that can tell the merge's max() from a
#     min(). (a) merges 1 with 1 and (c) merges 3 with 3, and on equal inputs
#     max, min, first-wins and last-wins are the same function. Here C's group
#     stands at 2 and D's at 1 when E bridges them: max(2,1), clamped to
#     MAX_BLOCKS-1, is 2, plus this Stop's single increment — so the merge Stop
#     blocks at (3/3) and the NEXT Stop gives up. A min-taking merge persists 2,
#     reports (2/3), and inverts block-vs-allow on the Stop after.
hook_case t21d
for f in x y z; do echo "V = 0" > "$HC_REPO/$f.py"; done
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/x.py"; echo "V = 1" > "$HC_REPO/y.py"
commit_all "$HC_REPO" "fix(c): x and y"
T21D_C="$(sha_of "$HC_REPO" HEAD)"
run_hook s21d
check 310 "the older group blocks on its own first Stop — contract:group:inv-t21" 2 "$RC"
echo "V = 1" > "$HC_REPO/z.py"; commit_all "$HC_REPO" "fix(d): z only"
T21D_D="$(sha_of "$HC_REPO" HEAD)"
run_hook s21d true
check 311 "the younger candidate arrives as a second counter — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21d '.block_counts|length')"
check 312 "the older counter stands at 2 before the merge — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21d ".block_counts[.sha_group[\"$T21D_C\"]]")"
check 313 "the younger counter stands at 1 before the merge — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21d ".block_counts[.sha_group[\"$T21D_D\"]]")"
echo "V = 2" > "$HC_REPO/y.py"; echo "V = 2" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "fix(e): y and z bridge"
T21D_E="$(sha_of "$HC_REPO" HEAD)"
run_hook s21d true
check 314 "the unequal-count merge blocks on the merge Stop — contract:group:inv-t21" 2 "$RC"
check 315 "the unequal merge reports (3/3), not (2/3) — contract:group:inv-t21" yes "$(has "$ERR" "(3/3)")"
check 316 "the unequal merge collapses to one counter — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21d '.block_counts|length')"
check 317 "min(max(2,1),2)=2 plus one increment persists 3 — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21d ".block_counts[.sha_group[\"$T21D_E\"]]")"
# The canonical id of a merged group is the lexicographically LOWER of the ids
# it merged, asserted CONCRETELY: every other id assertion here is relational,
# and a higher-wins rule satisfies all of them.
check 318 "the merged group takes the lexicographically lower id — contract:group:inv-t21" \
  "$(printf '%s\n%s\n' "$T21D_C" "$T21D_D" | LC_ALL=C sort | head -1)" \
  "$(st "$HC_REPO" s21d ".sha_group[\"$T21D_E\"]")"
run_hook s21d true
check 319 "the Stop after the unequal-count merge gives up — contract:group:inv-t21" 0 "$RC"

# (e) THREE groups merging on ONE bridging SHA. (a)-(d) all merge exactly two,
#     and at arity 2 a wrong n-ary reduction is right by construction: a fold
#     that unsets only one loser, or that canonicalises by visit order rather
#     than by id, cannot be told from the real thing. Here C's group stands at
#     2 and D's and E's at 1 when F bridges all three: max(2,1,1) clamped to
#     MAX_BLOCKS-1 is 2, plus this Stop's single increment — so the merge Stop
#     blocks at (3/3) and the NEXT Stop gives up.
#
#     Why (2,1,1) and not three PAIRWISE-distinct counts: the merge clamps to
#     MAX_BLOCKS-1 = 2, so 2 and 3 are indistinguishable in the persisted
#     result, and a (3,2,1) staging would let a rule that happened to pick the
#     count-2 group pass as if it were max(). With a UNIQUE maximum and both
#     other groups at 1, "take the canonical group's count", "take the min"
#     and "take the last group visited" each persist 2 where max() persists 3.
#
#     Why the canonical id is the MIDDLE one in the merge's visit order (a
#     premise this fixture ASSERTS below, after check 348, because nothing in
#     the hook's contract fixes bash's iteration order): the
#     merge walks the bridged groups in the hook's own iteration order (C, D,
#     E for these SHAs) and the lowest id, D, sits second — so a canonical
#     rule of "take the first visited" picks C and "take the last visited"
#     picks E, and both fail check 352. One rival cannot be separated here:
#     the maximum sits on the FIRST group visited, so "take the first
#     visited group's count" coincides with max(). Moving the maximum to the
#     middle to kill that one would put the lowest id first or last and
#     revive one of the two canonical rules — the middle slot buys exactly
#     one of the two, and the id rules are the ones arity 2 cannot reach at
#     all.
hook_case t21e
for f in x y z; do echo "V = 0" > "$HC_REPO/$f.py"; done
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/x.py"; commit_all "$HC_REPO" "fix(c): older x fix"
T21E_C="$(sha_of "$HC_REPO" HEAD)"
run_hook s21e
check 344 "the oldest of the three groups blocks on its own first Stop — contract:group:inv-t21" 2 "$RC"
echo "V = 1" > "$HC_REPO/y.py"; commit_all "$HC_REPO" "fix(d): y only"
T21E_D="$(sha_of "$HC_REPO" HEAD)"
echo "V = 1" > "$HC_REPO/z.py"; commit_all "$HC_REPO" "fix(e): z only"
T21E_E="$(sha_of "$HC_REPO" HEAD)"
run_hook s21e true
T21E_CANON="$(printf '%s\n%s\n%s\n' "$T21E_C" "$T21E_D" "$T21E_E" | LC_ALL=C sort | head -1)"
# Fixture premise, asserted as a hard abort rather than a `check` so the tag
# arithmetic is unchanged: the group holding the MAXIMUM count must not also be
# the lowest-id one, or "take the canonical group's count" coincides with
# max() and the whole point of this fixture is gone. `commit_all` pins the
# author and committer dates, so these three SHAs — and therefore this
# ordering — are reproducible; if a reworded message ever shifts them the
# fixture must be re-staged, not quietly kept.
if [ "$T21E_CANON" = "$T21E_C" ]; then
  echo "FIXTURE ERROR: t21e's max-count group is also the canonical (lowest) id" >&2
  exit 1
fi
check 345 "three distinct groups exist before the merge — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21e '.block_counts|length')"
check 346 "the oldest group holds the unique maximum, 2 — contract:group:inv-t21" 2 \
  "$(st "$HC_REPO" s21e ".block_counts[.sha_group[\"$T21E_C\"]]")"
check 347 "the middle group stands at 1 before the merge — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21e ".block_counts[.sha_group[\"$T21E_D\"]]")"
check 348 "the youngest group stands at 1 before the merge — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21e ".block_counts[.sha_group[\"$T21E_E\"]]")"
# Fixture premise #2, asserted the same way and for the same reason as #1: the
# canonical (lowest) id must sit in the MIDDLE of the merge's visit order, or
# "take the first visited" / "take the last visited" coincides with it and check
# 352 stops killing those two mutants. That order is bash's associative-array
# iteration order over SHA_GROUP (`for s in "${!SHA_GROUP[@]}"`) — a property of
# the bash build and the key set, NOT of the SHA-derived lexicographic order
# premise #1 guards, so a different bash or a re-staged fixture could move the
# group to first or last with every check still passing and the fixture silently
# reduced to what arity 2 already covers.
#
# Reconstructed from the hook's own persisted state, the way the merge Stop will
# reconstruct it: `_write_state` emits sha_group in the order the PREVIOUS Stop
# iterated it, the merge Stop's `_load_maps` inserts those keys in that order,
# and then iterates. Re-inserting them here into an array of our own, under the
# same bash that runs the hook, models that load-then-iterate step rather than
# assuming the file order survives it.
T21E_ORDER="$(st "$HC_REPO" s21e '.sha_group|keys_unsorted|join(" ")')"
unset T21E_VISIT_MAP; declare -A T21E_VISIT_MAP
for s in $T21E_ORDER; do T21E_VISIT_MAP["$s"]=1; done
T21E_VISIT=()
for s in "${!T21E_VISIT_MAP[@]}"; do T21E_VISIT+=("$s"); done
if [ "${#T21E_VISIT[@]}" -ne 3 ] || [ "${T21E_VISIT[1]}" != "$T21E_CANON" ]; then
  echo "FIXTURE ERROR: t21e's canonical (lowest) id is not the MIDDLE group of the merge's visit order (${T21E_VISIT[*]:-<none>}) — 'take the first visited' or 'take the last visited' now coincides with the real rule and check 352 no longer kills both canonicalisation mutants. Re-stage the fixture." >&2
  exit 1
fi
echo "V = 2" > "$HC_REPO/x.py"; echo "V = 2" > "$HC_REPO/y.py"; echo "V = 2" > "$HC_REPO/z.py"
commit_all "$HC_REPO" "fix(f): x, y and z bridge"
T21E_F="$(sha_of "$HC_REPO" HEAD)"
run_hook s21e true
check 349 "the three-group merge blocks on the merge Stop — contract:group:inv-t21" 2 "$RC"
check 350 "the three-group merge reports (3/3), not (2/3) — contract:group:inv-t21" yes "$(has "$ERR" "(3/3)")"
check 351 "the three-group merge collapses to one counter — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21e '.block_counts|length')"
# 351 says ONE counter is left; this says WHICH, concretely. A merge that
# canonicalises by visit order rather than by id still collapses to exactly one
# counter — just the wrong one — and a fold that drops only one of the two
# losers leaves the surviving loser's id in this key list as well.
check 352 "the sole surviving counter is the lexicographically lowest of all THREE ids — contract:group:inv-t21" \
  "$T21E_CANON" "$(st "$HC_REPO" s21e '.block_counts|keys|join(",")')"
check 353 "min(max(2,1,1),2)=2 plus one increment persists 3 — contract:group:inv-t21" 3 \
  "$(st "$HC_REPO" s21e ".block_counts[.sha_group[\"$T21E_F\"]]")"
check 354 "all four bridged SHAs share the canonical id — contract:group:inv-t21" 1 \
  "$(st "$HC_REPO" s21e '[.sha_group[]]|unique|length')"
check 355 "the bridging SHA is named on the merge Stop — contract:group:inv-t21" yes "$(has "$ERR" "$T21E_F")"
run_hook s21e true
check 356 "the Stop after the three-group merge gives up — contract:group:inv-t21" 0 "$RC"

# ========================================================================
# INV-T22 (extension) — the checkpoint may only ever hold a real object id
#
# A bare `git rev-parse HEAD` on an UNBORN HEAD (a repo with zero commits)
# prints the literal string `HEAD` on stdout and exits 128, and `_git`
# swallows the stderr. Persisting that string as `last_checked_sha` is silent
# non-enforcement forever: on the NEXT Stop `cat-file -e HEAD^{commit}` DOES
# resolve (HEAD is a valid symbolic ref by then), so step 9 takes the
# incremental branch and scans `HEAD..HEAD` — always empty. No block, no
# give-up message, no trace. Both halves are asserted: step 10 must not write
# the string, and step 9 must not believe it if some other writer does.
# ========================================================================
# contract:hook:inv-t22 checks=4
hook_case t22unborn
run_hook s22u            # repo has ZERO commits: HEAD is unborn
check 320 "an unborn HEAD allows — contract:hook:inv-t22" 0 "$RC"
check 321 "an unborn HEAD never persists the literal string HEAD — contract:hook:inv-t22" \
  no "$(st "$HC_REPO" s22u '.last_checked_sha' | grep -qx 'HEAD' && echo yes || echo no)"
echo "V = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): repair the widget"
T22U_FIX="$(sha_of "$HC_REPO" HEAD)"
run_hook s22u true
check 322 "a fix(*) after an unborn-HEAD Stop is still seen — contract:hook:inv-t22" 2 "$RC"
check 323 "the post-unborn candidate is named — contract:hook:inv-t22" yes "$(has "$ERR" "$T22U_FIX")"

# Defence in depth: `cat-file -e` cannot tell an object id from a symbolic ref
# that happens to resolve, so step 9 gates on SHAPE first. Poison the stored
# checkpoint with `HEAD` directly — a shape-blind step 9 scans HEAD..HEAD and
# allows; a shape-checked one discards the checkpoint and re-scans in full.
# contract:hook:inv-t22 checks=3
hook_case t22symref
echo "V = 0" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "chore: baseline"
echo "V = 1" > "$HC_REPO/app.py"
commit_all "$HC_REPO" "fix(widget): repair the widget"
T22S_FIX="$(sha_of "$HC_REPO" HEAD)"
T22S_DIR="$(guard_dir "$HC_REPO")"
mkdir -p "$T22S_DIR"
printf '{"session_id":"s22s","seeded_at":1767225600,"last_checked_sha":"HEAD","block_counts":{},"sha_group":{},"sha_files":{}}' \
  > "$T22S_DIR/s22s.json"
run_hook s22s true
check 324 "a symbolic-ref checkpoint is not believed — contract:hook:inv-t22" 2 "$RC"
check 325 "the candidate hidden behind HEAD..HEAD is named — contract:hook:inv-t22" \
  yes "$(has "$ERR" "$T22S_FIX")"
check 326 "the poisoned checkpoint is replaced by a real object id — contract:hook:inv-t22" \
  yes "$(st "$HC_REPO" s22s '.last_checked_sha' | grep -Eqx '[0-9a-fA-F]{40}|[0-9a-fA-F]{64}' && echo yes || echo no)"

# ========================================================================
# INV-T23 (extension) — a leading-dash path must not make clearance
# unreachable, and must not be MISREPORTED as a transient degradation
#
# `-` is a legal first byte of a POSIX path and git sorts it first, so step
# 11's comma-joined path list can BEGIN with `-`. Passed as a separate option
# value (`--by-files "$CSV"`) argparse rejects it as a stray option and
# grudge_query.py exits 2 — permanently, for every session, no matter what
# grudge is recorded. The `=`-joined single-argv form cannot be mistaken for
# an option. The step-15 prefill has the same argv boundary (`--files`), so
# the printed remedy must be runnable for such a commit too.
# ========================================================================
# contract:hook:inv-t23 checks=5
hook_case t23dash
echo "V = 0" > "$HC_REPO/-dash.py"; echo "V = 0" > "$HC_REPO/other.py"
commit_all "$HC_REPO" "chore: baseline"
T23D_BASE="$(sha_of "$HC_REPO" HEAD)"
echo "V = 1" > "$HC_REPO/-dash.py"; echo "V = 1" > "$HC_REPO/other.py"
commit_all "$HC_REPO" "fix(widget): repair the widget"
check 327 "fixture: the leading-dash path is really in the candidate — contract:hook:inv-t23" \
  yes "$(has "$(git -C "$HC_REPO" diff-tree --no-commit-id --name-only -r HEAD)" "-dash.py")"
run_hook s23d
check 328 "with no grudge recorded the dash candidate blocks — contract:hook:inv-t23" 2 "$RC"
check 329 "the prefilled remedy uses the =-joined --files form — contract:hook:inv-t23" \
  yes "$(has "$ERR" '--files="-dash.py')"
# fixed_in_commit names the unrelated baseline, so ONLY --by-files can clear.
append_grudge "$HC_STORE" "$HC_KEY" "$HC_REPO" "dash path regression" \
  "-dash.py,other.py" "$T23D_BASE" "2026-05-01" >/dev/null
run_hook s23dclear
check 330 "a by-files grudge clears a leading-dash candidate — contract:hook:inv-t23" 0 "$RC"
check 331 "no clearance-lookup note is printed for a dash path — contract:hook:inv-t23" \
  no "$(has "$ERR" "clearance lookup")"

# ========================================================================
# INV-T28 — issue #603: the per-Stop wall-clock budget bounds
# per-invocation cost in ATTACKER-CHOSEN inputs. Candidate count (up to the
# --max-count=500 scan, accumulable turn-over-turn via future-dated author
# times), files per commit, and the stored grudge count each multiply the
# work one Stop does; 362 s was measured on a single Stop. The only
# input-independent bound is a wall-clock budget. Spending it must degrade
# LOUDLY to allow (exit 0) — the never-fail-closed contract — so an attacker
# can stall a Stop for at most the budget, never for a whole turn.
# ========================================================================
# contract:hook:inv-t28 checks=4
hook_case t28ctl
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): in-window fix"
run_hook s28ctl
check 357 "an unresolved fix still blocks under the default budget — contract:hook:inv-t28" 2 "$RC"
check 358 "the block path prints no budget-exceeded note — contract:hook:inv-t28" no "$(has "$ERR" "budget")"
hook_case t28zero
echo "VALUE = 0" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "chore: baseline"
echo "VALUE = 1" > "$HC_REPO/app.py"; commit_all "$HC_REPO" "fix(widget): in-window fix"
HOOK_ENV="CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS=0"
run_hook s28zero
check 359 "a spent budget allows, never blocks — contract:hook:inv-t28" 0 "$RC"
check 360 "a spent budget prints the loud degradation reason — contract:hook:inv-t28" yes "$(has "$ERR" "budget")"
HOOK_ENV=""

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASSED/$TOTAL passed"

# Checks 220+ (round-1 review) and 233+ (round-2 review) are numbered from the
# end on purpose: they sit inside their own scenario blocks, so renumbering in
# place would have rewritten every later check id and broken the mutation
# report's citations.
# TOTAL accumulates per `check`, so a skipped scenario shrinks the denominator
# instead of failing. Pin the expected count so the loss is loud: only a root
# uid may run fewer (the chmod-000 and chmod-500 fixtures, which root bypasses),
# and even then it is announced.
EXPECTED_CHECKS=372
ROOT_SKIPPED_CHECKS=32
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
