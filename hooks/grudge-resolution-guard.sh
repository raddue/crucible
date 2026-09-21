#!/usr/bin/env bash
# hooks/grudge-resolution-guard.sh
# Stop hook for #559 — grudge write-discipline. Blocks a Stop (exit 2) while a
# `fix(*)` commit that landed in this session's window, and touched at least one
# non-`.md` file, still has neither a grudge record nor a skips.log entry.
# Bounded at MAX_BLOCKS=3 blocks per block-count group, then gives up loudly so
# a session can never be trapped in an unbreakable block-continue loop.
#
# Exit 0 = allow, exit 2 = block (Claude Code's Stop contract only blocks on 2).
# Every infra failure — missing jq/git, malformed payload, unreadable
# transcript, non-git cwd, absent grudge store, unwritable state dir — allows.
# Never fail closed.
#
# Configured in .claude/settings.json:
#   "hooks": { "Stop": [{ "matcher": "*", "hooks": [{ "type": "command",
#     "command": "bash hooks/grudge-resolution-guard.sh", "timeout": 500 }] }] }

# Disable errexit — this hook must never fail fatally (INV-C7)
set +e

# LC_ALL=C, and it must be LC_ALL rather than LC_NUMERIC: `$EPOCHREALTIME` is
# rendered with the LOCALE'S radix character, so under de_DE / fr_FR / es_ES /
# pt_BR / ru_RU and friends bash emits `1788995310,670161`. `${EPOCHREALTIME%%.*}`
# then strips NOTHING (there is no `.` to match), and `$(( 1788995310,670161 ))`
# parses that comma as C's COMMA OPERATOR — evaluating to the trailing
# microseconds field alone (~10^5), forever below a ~10^9 deadline. `_budget_ok`
# would answer "budget remains" on every call and the whole #603 budget below
# would be a silent no-op, with no error output, in exactly the fail-open
# direction it exists to prevent. `LC_NUMERIC=C` alone cannot fix it: an
# inherited LC_ALL outranks LC_NUMERIC, and an inherited LC_ALL is precisely the
# reproducing case. Nothing else here regresses under C: `_git` already runs
# under `env -i`, `date -u -d` parses the transcript's ISO-8601 stamps
# locale-independently, and python3 auto-enables UTF-8 mode under a C locale
# (PEP 540), so non-ASCII paths still round-trip through grudge_query.py.
export LC_ALL=C

MAX_BLOCKS=3
MAX_SECONDS="${CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS:-8}"
case "$MAX_SECONDS" in ''|*[!0-9]*) MAX_SECONDS=8 ;; esac
# Base 10 EXPLICITLY. The all-digits test above accepts `08`, `09` and `010`,
# and bash reads a leading zero as OCTAL: `$(( $(date +%s) + 08 ))` is a "value
# too great for base" arithmetic error that leaves $BUDGET_DEADLINE EMPTY — every
# later `_budget_ok` comparison then errors too and degrades the Stop to an
# unenforced allow — while `010` raises no error and silently means 8 seconds,
# not 10. Normalising once HERE, rather than at the arithmetic use site, keeps
# the number used for the deadline and the number printed in `_budget_out`'s
# message the same value.
MAX_SECONDS=$(( 10#$MAX_SECONDS ))

# `git -C <dir>` ONLY chdirs — it does not clear the environment, and git obeys
# TWO families of inherited variable that outrank anything this hook says:
#   * repository LOCATION — GIT_DIR, GIT_WORK_TREE, … — which outrank
#     discovery-from-cwd and silently retarget every query at another repo;
#   * repository CONFIGURATION — GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM,
#     GIT_CONFIG_PARAMETERS (git's own `-c` transport, which git EXPORTS to
#     every hook it spawns), and the INDEXED
#     GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n triple — which leave
#     the repo alone and change what git REPORTS about it
#     (`i18n.logOutputEncoding`, `log.showSignature`, `core.quotePath` …).
# A Stop hook fires in exactly the environments where both families live, and
# either one turns a correct block into a silent allow: the wrong answer is
# indistinguishable from a right one.
#
# This is therefore an ALLOWLIST, not a denylist — `env -i` plus the two
# variables the hook genuinely needs: PATH (git must be findable at all) and
# HOME (git's per-user config, where a legitimate `safe.directory` lives). A
# denylist CANNOT be complete here even in principle: GIT_CONFIG_KEY_n is
# INDEXED, so the set of names to drop is unbounded and no literal `env -u`
# list can name them all. Everything git needs about the repository it is
# being asked about arrives as an argument.
_git() {
  local d="$1"; shift
  env -i PATH="$PATH" HOME="$HOME" git -C "$d" "$@" 2>/dev/null
}

# ── Per-Stop wall-clock budget (issue #603) ─────────────────────────────
# Per-invocation cost grows in THREE attacker-chosen inputs — candidate count
# (up to the --max-count=500 scan, and accumulable turn-over-turn through
# future-dated author times), files per commit, and the stored grudge count
# each grudge_query.py lookup must see — so neither the scan cap nor any
# structural filter can bound wall time (362 s measured on one Stop). The one
# input-independent bound is a wall-clock budget. Once it is spent the hook
# gives up on the WHOLE call and degrades LOUDLY to allow (exit 0), matching
# the never-fail-closed contract: an attacker can stall a Stop for at most
# MAX_SECONDS, never block it. The allow is a rescan-on-next-Stop, not a
# clearance: the checkpoint (step 16) only advances on a normal pass.
#
# The clock is bash's `$EPOCHREALTIME` (bash >=5) — a builtin, so a check
# costs integer arithmetic, not a subprocess. That matters in `_overlap`'s
# nested loop, where a `date` per call would re-add the very cost this budget
# exists to bound. On older bash it falls back to a whole-second `date +%s`,
# which still bounds to ~1 s past the deadline at the loop boundaries below.
_budget_ok() {
  if [ -n "${EPOCHREALTIME:-}" ]; then
    [ "$(( ${EPOCHREALTIME%%.*}+0 ))" -lt "$BUDGET_DEADLINE" ]
  else
    [ "$(date +%s)" -lt "$BUDGET_DEADLINE" ]
  fi
}
_budget_out() {
  echo "grudge-resolution-guard: per-Stop wall-clock budget (${MAX_SECONDS}s) reached before the candidate set was fully checked — allowing this Stop to bound per-invocation cost; grudge compliance was NOT enforced for every candidate (issue #603). Any unresolved fix(*) commit will be scanned again on a later Stop." >&2
  exit 0
}

# ── 1. Read stdin ───────────────────────────────────────────────────────
INPUT="$(cat)"
if [ -z "$INPUT" ]; then
  exit 0
fi

# ── 2. PROJECT_ROOT / PROJECT_MEMORY (build-routing-advisor.sh:141-143) ──
PROJECT_ROOT="$(_git "$(pwd)" rev-parse --show-toplevel)"
if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT="$(pwd)"
fi
PROJECT_DIR_SAFE="$(echo "$PROJECT_ROOT" | tr '/' '-')"
PROJECT_MEMORY="$HOME/.claude/projects/$PROJECT_DIR_SAFE/memory"
SESSION_ROOT="$PROJECT_ROOT"

# ── 3. Execution-evidence breadcrumb, BEFORE either kill-switch ─────────
# A kill-switched invocation still records that the hook ran; only the
# expensive detection work below is skipped.
STATE_DIR="$PROJECT_MEMORY/grudge-guard"
mkdir -p "$STATE_DIR" 2>/dev/null
touch "$STATE_DIR/.last-run" 2>/dev/null

# ── 4. Kill-switches (env first, then sentinel file) ────────────────────
if [ "${CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD:-}" = "1" ]; then
  echo "grudge-resolution-guard: disabled via env var — fix(*) commits are not being checked for grudge compliance" >&2
  exit 0
fi
SENTINEL="$PROJECT_MEMORY/.grudge-resolution-guard-disabled"
if [ -f "$SENTINEL" ]; then
  echo "grudge-resolution-guard: disabled via sentinel file $SENTINEL — fix(*) commits are not being checked for grudge compliance" >&2
  exit 0
fi

# The budget is measured from here — every cheaper setup step (stdin, project
# derivation, breadcrumb, kill-switches) has already run, but nothing below
# (dependency probe, payload parse, git scans, candidate diff-tree fan-out,
# grouping, clearance subprocesses) is input-independent work. A zero budget
# therefore trips on the very first check.
BUDGET_DEADLINE=$(( $(date +%s) + MAX_SECONDS ))
if ! _budget_ok; then
  _budget_out
fi

# ── 5. Dependencies + payload ───────────────────────────────────────────
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi
if ! command -v git >/dev/null 2>&1; then
  exit 0
fi
if ! printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1; then
  exit 0   # malformed JSON
fi
# The payload's own session id, NEVER $CLAUDE_SESSION_ID.
SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)"
if [ -z "$SESSION_ID" ]; then
  exit 0   # no session identity -> no state file is written
fi
# SESSION_ID is untrusted stdin and is used below as a PATH COMPONENT
# ($STATE_DIR/$SESSION_ID.json, and the tmp name that `mv -f` lands on it), so
# a payload of `../../../../settings` writes guard state on top of a file the
# user owns. A Claude Code session id is a UUID-shaped token, so the id is
# checked against a strict ALLOWLIST rather than by blocklisting `..` or `/`:
# a blocklist has to anticipate every escape, an allowlist only has to name
# what a real id contains. Rejection degrades to a LOUD ALLOW, per this hook's
# own never-fail-closed contract (header, lines 10-11) — never a block, and
# never a fallback to a shared default path, which a second session would then
# collide with. The offending value is never echoed back: it is
# attacker-shaped text on its way to a terminal.
_reject_session_id() {
  echo "grudge-resolution-guard: refusing a session_id that is not a plain identifier (allowed: A-Za-z0-9_-, at most 128 characters) — it names this session's state file and could otherwise be written outside $STATE_DIR. Allowing Stop; grudge compliance is NOT enforced." >&2
  exit 0
}
case "$SESSION_ID" in *[!A-Za-z0-9_-]*) _reject_session_id ;; esac
if [ "${#SESSION_ID}" -gt 128 ]; then
  _reject_session_id
fi
TRANSCRIPT_PATH="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)"
# stop_hook_active is read ONLY to word the block message below; it never
# gates allow/block (INV-C8 — the one-shot-nag failure FATAL-B fixed).
STOP_HOOK_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)"

# ── 6. Must be inside a git work tree ───────────────────────────────────
if [ "$(_git "$(pwd)" rev-parse --is-inside-work-tree)" != "true" ]; then
  exit 0
fi

# ── 7. Store-presence bootstrap (both identity keys) ────────────────────
GRUDGE_ROOT="${CRUCIBLE_GRUDGE_DIR:-$HOME/.claude/crucible/grudge}"
WORKTREE_KEY="$(basename "$(realpath "$SESSION_ROOT" 2>/dev/null || echo "$SESSION_ROOT")")"
# `dirname` is mandatory: the bare realpath names the `.git` DIRECTORY, and
# load_grudges' repo_root filter then rejects every record.
GIT_COMMON_ABS="$(cd "$SESSION_ROOT" 2>/dev/null && realpath "$(_git . rev-parse --git-common-dir)" 2>/dev/null)"
STORE_REPO_ROOT="$(dirname "$GIT_COMMON_ABS" 2>/dev/null)"
SHARED_KEY="$(basename "$STORE_REPO_ROOT" 2>/dev/null)"
if [ ! -d "$GRUDGE_ROOT/$WORKTREE_KEY" ] && [ ! -d "$GRUDGE_ROOT/$SHARED_KEY" ]; then
  echo "grudge-resolution-guard: no grudge store found for this repo at $GRUDGE_ROOT (checked this worktree and the shared clone root) — see skills/grudge/SKILL.md to start one" >&2
  exit 0
fi

# ── 7.5. Outcome witness (design §5b) — write-ONLY execution evidence ─────────
# Written OUTSIDE $STATE_DIR (C-i), so wiping $STATE_DIR (mechanism 3, #581)
# cannot erase the proof that the hook ran and how it terminated. The hook
# NEVER reads it (C-h) — only the reader (scripts/grudge_guard_doctor.py
# --grudge-guard) does. A divergence between witness and journal is therefore
# the DETECTOR's signal, never a second term in a decision (§5b.2).
#   <epoch>\t<session-id>\t<repo-basename>\t<outcome>\t<nonce-or-->
#   outcome ∈ BLOCK | GIVEUP | CLEARED | DEGRADE:<reason-code> (closed vocab:
#   journal-quarantined, witness-write-failed, journal-write-failed,
#   harness-drift — never free text, SIEGE-R2-M5). The <nonce-or--> field
#   carries the BLOCK's batch nonce (minting one is the forger-unseen event);
#   terminal/DEGRADE lines fall back to `-`.
WITNESS_DIR="${CRUCIBLE_GRUDGE_GUARD_WITNESS_DIR:-$HOME/.claude/crucible/grudge-guard}"
WITNESS_FILE="$WITNESS_DIR/outcomes.tsv"
_witness_outcome() {
  local outcome="$1" nonce="${2:--}" epoch row
  [ -n "${SESSION_ID:-}" ] || return 0
  mkdir -p "$WITNESS_DIR" 2>/dev/null || return 0
  if [ -n "${EPOCHREALTIME:-}" ]; then
    epoch="${EPOCHREALTIME%%.*}"
  else
    epoch="$(date +%s 2>/dev/null)"
  fi
  [ -n "$epoch" ] || epoch=0
  row="$(printf '%s\t%s\t%s\t%s\t%s' "$epoch" "$SESSION_ID" "$SHARED_KEY" "$outcome" "$nonce")"
  # Bounded wait (siege S-17 / SIEGE-R2-H3): a same-uid actor that mkfifos the
  # fixed witness path turns `>>` into a blocking open, which a post-command
  # `|| :` cannot short-circuit — `timeout 1` costs the bound, never the hook's
  # own budget, and a failure never affects a verdict (C-h/C-i).
  timeout 1 bash -c 'printf "%s\n" "$1" >> "$2" || :' _ "$row" "$WITNESS_FILE" 2>/dev/null || :
}

# ── 8. State file (INV-C12: version + four fields) + separate skips log ─
STATE_FILE="$STATE_DIR/$SESSION_ID.json"
SKIPS_FILE="$STATE_DIR/skips.log"

CRUCIBLE_ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ ! -f "$CRUCIBLE_ROOT/scripts/grudge_query.py" ]; then
  CRUCIBLE_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
fi
QUERY_SCRIPT="$CRUCIBLE_ROOT/scripts/grudge_query.py"
APPEND_SCRIPT="$CRUCIBLE_ROOT/scripts/grudge_append.py"

declare -A SHA_GROUP BLOCK_COUNTS PRIOR_COUNTS PRIOR_GROUP LAST_BLOCK_NONCE

# ── State document format version (INV-C12, §5.2 hazard 2) ─────────────
# R4 removes the `sha_files` JSON field (its per-sha path list can hold a
# byte jq cannot carry, S-2) and persists touched files only as the
# NUL-delimited `$STATE_DIR/<sha>.files` sibling artifact. A state document
# whose `version` disagrees with this build was written by a different hook
# generation; its fields are not trusted (they may carry the removed schema)
# and the file is discarded so this Stop rewrites it fresh on the next scan.
STATE_VERSION=1
# Only a document that actually PARSES participates in the version gate — an
# empty or non-JSON file is the baseline's `BASELINE_READABLE` case (loud
# allow), not a competing-version discard.
if [ -f "$STATE_FILE" ] && jq -e 'type == "object"' "$STATE_FILE" >/dev/null 2>&1; then
  STORED_VERSION="$(jq -r '.version // 0' "$STATE_FILE" 2>/dev/null)"
  case "$STORED_VERSION" in ''|*[!0-9]*) STORED_VERSION=0 ;; esac
  if [ "$STORED_VERSION" != "$STATE_VERSION" ]; then
    rm -f "$STATE_FILE" 2>/dev/null
  fi
fi

# ── The durable baseline the block predicate (step 14b) measures against ─
# What was ON DISK for this session when this Stop began, read with NO
# acceptance gate of any kind — not step 9/10's `seeded_at`/checkpoint test,
# not any other. A baseline taken after that gate cannot detect a freeze: the
# gate is free to discard the very counters termination depends on (it does,
# for an unresolvable checkpoint and for a `seeded_at` of 0), and a Stop that
# then recomputes the same counter up from zero would read its own write back
# as "progress" every single time. Non-numeric counters are ignored rather
# than trusted. An empty baseline is trustworthy in exactly one case: there
# was NO state file to read, i.e. a genuine first Stop, whose counters really
# did start at 0. A file that EXISTS but yields no document is a different
# state and must not be read as that one — its counters could say anything,
# so calling the baseline 0 is not "the safe direction": it is precisely what
# makes a frozen counter look like fresh progress on every Stop (truncate the
# state file before each Stop and the guard blocks at (1/3) forever). Step 9's
# `[ -f "$STATE_FILE" ]` already tells the two apart, so record which one this
# is: not a baseline of 0, but NO MEASURABLE BASELINE, which step 14b refuses.
BASELINE_READABLE=1
if [ -f "$STATE_FILE" ] && ! jq -e 'type == "object"' "$STATE_FILE" >/dev/null 2>&1; then
  BASELINE_READABLE=0
fi
while IFS=$'\t' read -r pk pv; do
  case "$pv" in ''|*[!0-9]*) continue ;; esac
  [ -n "$pk" ] && PRIOR_COUNTS["$pk"]="$pv"
done < <(jq -r '(.block_counts // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)
while IFS=$'\t' read -r pk pv; do
  [ -n "$pk" ] && [ -n "$pv" ] && PRIOR_GROUP["$pk"]="$pv"
done < <(jq -r '(.sha_group // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)

_load_maps() {
  while IFS=$'\t' read -r k v; do
    [ -n "$k" ] && SHA_GROUP["$k"]="$v"
  done < <(jq -r '(.sha_group // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)
  while IFS=$'\t' read -r k v; do
    [ -n "$k" ] && BLOCK_COUNTS["$k"]="$v"
  done < <(jq -r '(.block_counts // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)
  # The per-sha touched-file list lives ONLY in the NUL-delimited
  # `$STATE_DIR/<sha>.files` artifacts (§5/S-2/INV-C12) — never in the JSON.
  _load_files
}

# C-o (SIEGE-R2-H6): a candidate sha used to build a bash identifier.
# Hex-only + bounded length, the same shape the hook applies to SESSION_ID.
_sha_key_ok() {
  case "$1" in ''|*[!0-9a-fA-F]*) return 1 ;; esac
  [ "${#1}" -ge 4 ] && [ "${#1}" -le 64 ]
}

# C-o funnel: EVERY bash identifier named after a sha goes through here, from
# BOTH branches — the fresh `diff-tree` scan AND the `.files` load — so no
# branch can concatenate an unvalidated sha into `declare -a "F_$sha"`.
_sha_array_set() {
  local sha="$1"; shift
  _sha_key_ok "$sha" || return 1
  # `-g`: the F_<sha> arrays are hook-global state (grouping, clearances, and
  # the message rendering read them long after this function returns); a bare
  # `declare -a` inside a function would scope them to this call.
  declare -g -a "F_$sha"
  declare -n _sa="F_$sha"
  _sa=("$@")
  unset -n _sa
  return 0
}

_sha_array_has() {
  # 0 iff the per-sha array F_$1 is already loaded (a persisted candidate's
  # paths were restored at hook start from its `<sha>.files` artifact).
  declare -n _ah="F_$1"
  local n=0
  [ "${#_ah[@]}" -gt 0 ] && n=1
  unset -n _ah
  [ "$n" -eq 1 ]
}

_load_files() {
  local f sha p _files=()
  for f in "$STATE_DIR"/*.files; do
    [ -e "$f" ] || continue
    sha="${f##*/}"; sha="${sha%.files}"
    _files=()
    while IFS= read -r -d '' p; do _files+=("$p"); done < "$f"
    # C-o: the sha from the FILENAME is validated inside the funnel before
    # it can name an array; a crafted name (`deadbeef[$(...)].files`) is
    # skipped, never concatenated into `declare -a "F_$sha"`.
    _sha_array_set "$sha" "${_files[@]}"
  done
  return 0
}

# SIEGE-R2-H3 / S-17 shape: EVERY hook-side write to an attacker-derivable or
# fixed `$STATE_DIR` path is wrapped in a bounded `timeout`, so a `mkfifo`'d
# target turns the append's opening redirect into a blocking open that ends at
# the 1s bound, never at the hook's own timeout ceiling. `|| :` is applied
# TWICE: the append's own failure is absorbed inside the child (best-effort
# write), and `timeout`'s 124 is absorbed outside — the write must never
# affect a block/allow verdict. C-k decides the remedy from what landed.
_write_state_files() {
  local target="$1"; shift
  timeout 1 bash -c 't="$1"; shift; printf "%s\0" "$@" >> "$t" || :' \
    _ "$target" "$@" || :
}

# ── 8b. The journal (R1+R2, §3) — the bound ---------------------------------
# `$STATE_DIR/$SESSION_ID.journal` is an append-only event log — one O_APPEND
# write per event, never rewritten, never reset, and every write is a single
# write(2) of one complete line ending in `\n`. C-a forbids rewriting,
# truncating, or deleting it, with exactly one named exception: C-q's
# quarantine-and-re-arm (§3.2) on an UNMEASURABLE read. Records:
#
#     <epoch>\tBLOCK\t<candidate-sha>\t<nonce>
#     <epoch>\tCLEAR\t<candidate-sha>
#     <epoch>\tGIVEUP\t<candidate-sha>
#
# Candidate SHAs and nonces are hex, so no field can carry a path byte (C-b).
#
# The block decision (§3.2) reads the journal THREE times at three different
# points, and the three reads must not be collapsed (§3.1 OBS-1):
#   1. read(g)                    — BEFORE this Stop's own append (eligibility)
#   2. ordinal max over members   — AFTER this Stop's own append (arbitration)
#   3. display_count(g)           — AFTER this Stop's own append (the (n/3) msg)
# _journal_read_group does all per-member counting in a SINGLE pass (T-cc,
# SIEGE-R2-H5 — not one re-read per member).
JOURNAL_FILE="$STATE_DIR/$SESSION_ID.journal"
JOURNAL_QUARANTINE_LINES=50000

# The nonce (§3.1): 16 lowercase hex from /dev/urandom; $$+$RANDOM+$EPOCHREALTIME
# (in hex) only if /dev/urandom is unreadable (M-6: the pipeline's own exit
# status is untrusted, so the fallback is validated to exactly 16 lowercase
# hex; anything else is treated as a failed append — never a record written
# short or empty, C-b).
_journal_nonce() {
  local n
  n="$(head -c8 /dev/urandom 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')"
  case "$n" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f])
      printf '%s' "$n"; return 0 ;;
  esac
  n="$(printf '%x' "$$")$(printf '%x' "${RANDOM:-0}")$(printf '%x' "${EPOCHREALTIME%%.*}${EPOCHREALTIME##*.}")"
  n="${n:0:16}"
  case "$n" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f])
      printf '%s' "$n"; return 0 ;;
  esac
  return 1
}

# S-17/SIEGE-R2-H3: EVERY hook-side write to a fixed $STATE_DIR path is wrapped
# in a bounded `timeout` (a mkfifo'd journal arena would otherwise block the
# append's open). A single `printf` to an O_APPEND fd is one write(2) of one
# complete line. NOTE: unlike the best-effort `.files`/witness writes (`|| :`),
# the journal append's RETURN STATUS is load-bearing — append_succeeded is a
# block-predicate conjunct (§3.2), so a failed write surfaces as a loud allow,
# never as a silent block. timeout's 124 (hung mkfifo) is equally a failure.
_journal_write_line() {
  local line="$1"
  timeout 1 bash -c 'printf "%s\n" "$1" >> "$2"' _ "$line" "$JOURNAL_FILE" 2>/dev/null
  return $?
}

# _record_line <TYPE> <nonce|''> <sha> — append one well-formed journal record.
_record_line() {
  local typ="$1" nonce="$2" sha="$3" epoch
  case "$typ" in
    BLOCK)
      [ -n "$nonce" ] || return 1
      epoch="$(date +%s 2>/dev/null)"
      _journal_write_line "$epoch	BLOCK	$sha	$nonce" ;;
    CLEAR)
      epoch="$(date +%s 2>/dev/null)"
      _journal_write_line "$epoch	CLEAR	$sha" ;;
    GIVEUP)
      epoch="$(date +%s 2>/dev/null)"
      _journal_write_line "$epoch	GIVEUP	$sha" ;;
    *) return 1 ;;
  esac
}

# _journal_append_group <TYPE> <nonce|''> <member-sha...>
# One line per member for BLOCK (all sharing the same nonce); one line per
# member for CLEAR/GIVEUP. Sets APPEND_OK=0/1: the append_succeeded conjunct is
# all-or-nothing over the batch (§3.1: a partially-landed batch counts as a
# failed append — the landed lines stay, C-a, over-count is row 10's open
# escape, not silently removed).
_journal_append_group() {
  local typ="$1" nonce="$2"; shift 2
  local m ok=1
  APPEND_OK=1
  [ "$#" -gt 0 ] || { APPEND_OK=0; return 1; }
  for m in "$@"; do
    case "$typ" in
      BLOCK)  [ -n "$nonce" ] || { APPEND_OK=0; } ;;
    esac
    _record_line "$typ" "$nonce" "$m" || ok=0
  done
  APPEND_OK=$ok
}

# ── The single-pass journal read (§8: _journal_read, _journal_read_group) ─
# ABSENT means NO journal FILE exists yet (SP-1) — nothing else. A present,
# parseable file with no lines for a member is COUNT(0). Any line that is not a
# full well-formed BLOCK/CLEAR/GIVEUP record (torn, concatenated) makes the read
# UNMEASURABLE (S2), never silently skipped; a journal past
# JOURNAL_QUARANTINE_LINES also reads UNMEASURABLE (SIEGE-R2-H5). Both read
# primitives share ONE pass over the file (T-cc).
#
# Globals after the pass (for the given names):
#   JR_ABSENT / JR_UNMEASURABLE / JR_COUNT  — exactly one is 1
#   JB[<sha>]  — blocks(m): BLOCK lines since the last CLEAR/GIVEUP for m
#   JBLAST[<sha>] — CLEAR | GIVEUP | BLOCK | "" ("" = no record for m yet)
_journal_pass() {
  JR_ABSENT=0; JR_UNMEASURABLE=0; JR_COUNT=0
  declare -g -A JB=() JBLAST=()
  # T-cc instrumentation (inert in production): one trace line per journal-file
  # pass, tagged by J_TRACE_HELD so the GROUP read can be distinguished from the
  # display/ordinal reads. T-cc asserts read_group is a SINGLE pass over the
  # file, never one full-log re-read per member.
  if [ -n "${CRUCIBLE_GRUDGE_GUARD_JOURNAL_TRACE:-}" ]; then
    printf "pass %s\n" "${J_TRACE_HELD:-plain}" >> "$CRUCIBLE_GRUDGE_GUARD_JOURNAL_TRACE" 2>/dev/null || :
  fi
  if [ ! -f "$JOURNAL_FILE" ]; then
    JR_ABSENT=1
    return 0
  fi
  if [ ! -r "$JOURNAL_FILE" ]; then
    JR_UNMEASURABLE=1
    return 0
  fi
  local n=0 line f1 f2 f3 f4
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    if [ "$n" -gt "$JOURNAL_QUARANTINE_LINES" ]; then
      JR_UNMEASURABLE=1
      return 0
    fi
    IFS=$'\t' read -r f1 f2 f3 f4 <<< "$line"
    case "$f2" in
      BLOCK)
        case "$f1" in ''|*[!0-9]*) JR_UNMEASURABLE=1; return 0 ;; esac
        case "$f3" in ''|*[!0-9a-fA-F]*) JR_UNMEASURABLE=1; return 0 ;; esac
        case "$f4" in ''|*[!0-9a-fA-F]*) JR_UNMEASURABLE=1; return 0 ;; esac
        [ "${JBLAST[$f3]:-}" = "CLEAR" ] && JB[$f3]=0
        [ "${JBLAST[$f3]:-}" = "GIVEUP" ] && JB[$f3]=0
        JB[$f3]=$(( ${JB[$f3]:-0} + 1 ))
        JBLAST[$f3]=BLOCK
        ;;
      CLEAR|GIVEUP)
        case "$f1" in ''|*[!0-9]*) JR_UNMEASURABLE=1; return 0 ;; esac
        case "$f3" in ''|*[!0-9a-fA-F]*) JR_UNMEASURABLE=1; return 0 ;; esac
        JB[$f3]=0
        JBLAST[$f3]=$f2
        ;;
      *)
        JR_UNMEASURABLE=1
        return 0
        ;;
    esac
  done < "$JOURNAL_FILE"
  JR_COUNT=1
  return 0
}


# _journal_read <candidate-sha> — echo COUNT:<n> | ABSENT | UNMEASURABLE
_journal_read() {
  local sha="$1"
  _journal_pass "$sha"
  if [ "$JR_UNMEASURABLE" -eq 1 ]; then echo UNMEASURABLE; return 0; fi
  if [ "$JR_ABSENT" -eq 1 ]; then echo ABSENT; return 0; fi
  echo "COUNT:${JB[$sha]:-0}"
}

# _journal_read_group <sha...> — echo UNMEASURABLE | ABSENT | COUNT:<n>
# (§3.2 S1: any member UNMEASURABLE dominates; all ABSENT → ABSENT; else the
# max over members reading a count — an ABSENT member contributes nothing to
# the max, C-j.)
_journal_read_group() {
  J_TRACE_HELD=group
  _journal_pass "$@"
  J_TRACE_HELD=""
  if [ "$JR_UNMEASURABLE" -eq 1 ]; then echo UNMEASURABLE; return 0; fi
  if [ "$JR_ABSENT" -eq 1 ]; then echo ABSENT; return 0; fi
  local m mx=0
  for m in "$@"; do
    [ "${JB[$m]:-0}" -gt "$mx" ] && mx="${JB[$m]:-0}"
  done
  echo "COUNT:$mx"
}

# _journal_ordinal <nonce> <sha...> — after this Stop's own BLOCK lines landed.
# This Stop's position: for each member, the count of BLOCK lines for m since
# the last CLEAR, up to and including the line carrying this Stop's own nonce.
# The group's ordinal conjunct is the MAX over members, <= MAX_BLOCKS (§3.4).
# If a member's own nonce line is not present (the append-and-recount cannot
# locate it), that member is UNMEASURABLE (§3.2) — echo UNMEASURABLE.
_journal_ordinal() {
  local nonce="$1"; shift
  local m n mx=0 found=1
  for m in "$@"; do
    n=$(_ordinal_of "$m" "$nonce")
    [ -z "$n" ] && { echo UNMEASURABLE; return 0; }
    [ "$n" -gt "$mx" ] && mx="$n"
  done
  echo "$mx"
}

# _ordinal_of <sha> <nonce> — per-member helper: this Stop's own position, or ""
# when the nonce line cannot be found in the member's BLOCK history.
_ordinal_of() {
  local sha="$1" nonce="$2"
  _journal_pass "$sha"
  if [ "$JR_UNMEASURABLE" -eq 1 ] || [ "$JR_ABSENT" -eq 1 ]; then
    echo ""
    return 0
  fi
  # Re-scan for the exact nonce line for this member and count BLOCK lines since
  # the last CLEAR up to and including it.
  local line f1 f2 f3 f4 cnt=0 own=0 last=""
  while IFS= read -r line || [ -n "$line" ]; do
    IFS=$'\t' read -r f1 f2 f3 f4 <<< "$line"
    case "$f2" in
      BLOCK)
        [ "$f3" = "$sha" ] || continue
        [ "$last" = "CLEAR" ] && cnt=0
        [ "$last" = "GIVEUP" ] && cnt=0
        cnt=$((cnt + 1))
        last=BLOCK
        if [ "$f4" = "$nonce" ]; then echo "$cnt"; return 0; fi
        ;;
      CLEAR|GIVEUP)
        [ "$f3" = "$sha" ] || continue
        cnt=0
        last="$f2"
        ;;
    esac
  done < "$JOURNAL_FILE"
  echo ""
}

# C-q (§3.2): the SINGLE named exception to C-a. Rename (never rewrite or
# delete) the journal to <session>.journal.corrupt.<epoch>, then start a fresh,
# empty journal so every candidate re-reads COUNT(0) and re-nags loudly — the
# conservative direction (D-1). The malformed evidence survives intact for
# grudge_guard_doctor. Called ONLY on an UNMEASURABLE read.
_journal_quarantine() {
  local epoch
  epoch="$(date +%s 2>/dev/null)"
  [ -e "$JOURNAL_FILE" ] && mv -f "$JOURNAL_FILE" "$JOURNAL_FILE.corrupt.$epoch" 2>/dev/null
  : > "$JOURNAL_FILE" 2>/dev/null
  _witness_outcome "DEGRADE:journal-quarantined" "-"
  echo "grudge-resolution-guard: journal was unreadable/malformed — quarantined to $JOURNAL_FILE.corrupt.$epoch (DEGRADE:journal-quarantined); every candidate re-nags from count 0; grudge compliance checked normally from now" >&2
}

# _display_count <member-sha...> — after this Stop's own append: COUNT( max over
# members of blocks(m) ), evaluated for the (n/3) message ONLY. Never one of
# block(g)'s conjuncts (§3.1 OBS-1, C-j: no clamp, never coercing
# ABSENT/UNMEASURABLE to 0).
_display_count() {
  _journal_pass "$@"
  local m mx=0
  for m in "$@"; do
    [ "${JB[$m]:-0}" -gt "$mx" ] && mx="${JB[$m]:-0}"
  done
  echo "$mx"
}

# ── 9/10. Pick the scan range ───────────────────────────────────────────
FIRST_SCAN=1
SEEDED_AT=""
LOG=""
if [ -f "$STATE_FILE" ]; then
  LAST_SHA="$(jq -r '.last_checked_sha // ""' "$STATE_FILE" 2>/dev/null)"
  STORED_AT="$(jq -r '.seeded_at // 0' "$STATE_FILE" 2>/dev/null)"
  case "$STORED_AT" in ''|*[!0-9]*) STORED_AT=0 ;; esac
  if [ -n "$LAST_SHA" ] && [ "$STORED_AT" -gt 0 ]; then
    if [ "$LAST_SHA" = "ROOT" ]; then
      # Parentless checkpoint sentinel: keep the state and re-scan the full
      # history, so the root candidate stays in scope. NEVER a git object id —
      # the SHA-1 empty tree fails the cat-file peel below (it is a tree) and
      # does not exist at all in a --object-format=sha256 repo.
      SEEDED_AT="$STORED_AT"
      FIRST_SCAN=0
      _load_maps
      LOG="$(_git "$SESSION_ROOT" log --no-merges --max-count=500 --format='%H|%at|%s' HEAD)"
    # SHAPE FIRST, THEN EXISTENCE. `cat-file -e` resolves any revision
    # expression, so a stored SYMBOLIC ref — e.g. the literal `HEAD` — passes
    # it and the range below becomes `HEAD..HEAD`, i.e. permanently empty:
    # silent non-enforcement with no give-up message. Only a full object id
    # (40 hex for sha1, 64 for sha256) or the `ROOT` sentinel above is ever
    # written by step 16, so anything else is a corrupt checkpoint.
    elif [[ "$LAST_SHA" =~ ^([0-9a-fA-F]{40}|[0-9a-fA-F]{64})$ ]] \
         && _git "$SESSION_ROOT" cat-file -e "${LAST_SHA}^{commit}"; then
      SEEDED_AT="$STORED_AT"
      FIRST_SCAN=0
      _load_maps
      LOG="$(_git "$SESSION_ROOT" log --no-merges --format='%H|%at|%s' "${LAST_SHA}..HEAD")"
    fi
    # else: unresolvable checkpoint -> discard state, fall through to the
    # first-Stop full scan below (a permanent condition, not transient).
  fi
fi

if [ "$FIRST_SCAN" = "1" ]; then
  if [ -z "$TRANSCRIPT_PATH" ] || [ ! -r "$TRANSCRIPT_PATH" ]; then
    exit 0
  fi
  EARLIEST_TS="$(jq -r '.timestamp // empty' "$TRANSCRIPT_PATH" 2>/dev/null | grep -v '^$' | sort | head -1)"
  if [ -n "$EARLIEST_TS" ]; then
    SEEDED_AT="$(date -u -d "$(printf '%s' "$EARLIEST_TS" | sed -E 's/\.[0-9]+//')" +%s 2>/dev/null)"
  fi
  case "$SEEDED_AT" in ''|*[!0-9]*) SEEDED_AT="" ;; esac
  if [ -z "$SEEDED_AT" ]; then
    SEEDED_AT="$(date -u +%s)"
    echo "grudge-resolution-guard: no timestamped record found in the transcript — seeding the session window from wall-clock now; fix(*) commits made earlier in this session may be missed" >&2
  fi
  LOG="$(_git "$SESSION_ROOT" log --no-merges --max-count=500 --format='%H|%at|%s' HEAD)"
fi

# `--verify --quiet` + the `^{commit}` peel, NOT a bare `rev-parse HEAD`: on an
# UNBORN HEAD (a repo with zero commits) the bare form prints the literal string
# `HEAD` on stdout and exits 128, and that string would then be persisted as
# `last_checked_sha`. This form prints nothing, so `LAST_NEW` persists as "" and
# step 9's `[ -n "$LAST_SHA" ]` guard routes the next Stop into a full scan.
SCAN_HEAD="$(_git "$SESSION_ROOT" rev-parse --verify --quiet "HEAD^{commit}")"

# ── 11. Candidate filter -> THIS Stop's IN-SCOPE SET ────────────────────
# (a) subject matches ^fix[(:]  (b) %at >= seeded_at  (c) >=1 non-.md path.
# The subject is EVERYTHING after the second `|`, so an embedded `|` cannot
# truncate it. --root so a parentless root commit still lists its paths.
_has_non_md() {
  # "$@" = one RAW path per ARGUMENT — never a delimited string. BOTH branches
  # of filter (c) — the fresh diff-tree and the persisted `.files` load — call
  # THIS one predicate, so the two can never disagree about the same commit.
  #
  # Taking an ARRAY rather than a delimited string is the whole point. Every
  # string form has some byte it cannot carry: git's display form cannot carry a
  # non-ASCII byte, a `"` or a `\` (it C-quotes them), and a newline-joined
  # string cannot carry a path that CONTAINS a newline — which is legal on every
  # POSIX filesystem, and which split `docs/a<LF>b.md` into `docs/a` (not .md,
  # so "at least one non-.md path") plus `b.md`, turning a DOCUMENTATION-ONLY
  # fix(*) commit into a candidate. That is the same INV-T14 violation the
  # quoting bug caused, by a different byte class. An argument vector is
  # delimiter-free, so it is correct for EVERY byte a path can hold and needs no
  # enumeration of shapes.
  local p
  for p in "$@"; do
    case "$p" in *.md) ;; *) return 0 ;; esac
  done
  return 1
}

IS_SHA=(); IS_AT=()
while IFS= read -r line; do
  # One `git diff-tree` subprocess may follow per candidate — the first of the
  # two attacker-multiplied fan-outs this budget bounds.
  _budget_ok || _budget_out
  [ -z "$line" ] && continue
  c_sha="${line%%|*}"
  c_rest="${line#*|}"
  c_at="${c_rest%%|*}"
  c_subj="${c_rest#*|}"
  case "$c_sha" in ''|*[!0-9a-fA-F]*) continue ;; esac
  case "$c_at" in ''|*[!0-9]*) continue ;; esac
  printf '%s' "$c_subj" | grep -qE '^fix[(:]' || continue
  [ "$c_at" -ge "$SEEDED_AT" ] || continue
  if ! _sha_array_has "$c_sha"; then
    # `-z` (NUL-delimited RAW paths) is load-bearing, not a style choice.
    # Without it `diff-tree --name-only` prints git's DISPLAY form, which
    # C-quotes any path holding a non-ASCII byte, a `"` or a `\`
    # (`"docs/caf\303\251.md"`) — and a quoted line ends in `.md"`, not `.md`,
    # so the docs-only exclusion below reads it as a non-.md path and a
    # DOCUMENTATION-ONLY fix(*) commit becomes a candidate and blocks, against
    # INV-T14. The predicate must see the path, not its rendering. The raw form
    # is also what gets persisted into the `<sha>.files` artifact, and therefore
    # what the `--by-files` clearance lookup and the Step-15 prefill use.
    #
    # The NUL delimiter is kept end to end, into an ARRAY. Translating it to a
    # newline first (`tr '\0' '\n'`) only swaps one impossible delimiter for
    # another: NUL is the single byte a path cannot contain, a newline is not.
    c_paths=()
    while IFS= read -r -d '' c_p; do
      c_paths+=("$c_p")
    done < <(_git "$SESSION_ROOT" diff-tree --root --no-commit-id --name-only -r -z "$c_sha")
    [ "${#c_paths[@]}" -eq 0 ] && continue
    _has_non_md "${c_paths[@]}" || continue
    # C-o funnel: only a hex-validated sha may name an in-hook array.
    _sha_array_set "$c_sha" "${c_paths[@]}" || continue
    # Persist the path list ONCE, byte-exact, as the NUL-delimited
    # `$STATE_DIR/<sha>.files` artifact (§5/S-2/S6) — never a delimited JSON
    # field. Bounded write (SIEGE-R2-H3): a mkfifo'd target holds the open for
    # the 1s timeout, never for the hook's own timeout ceiling.
    _write_state_files "$STATE_DIR/$c_sha.files" "${c_paths[@]}"
  else
    declare -n _cf="F_$c_sha"
    _has_non_md "${_cf[@]}" || continue
    unset -n _cf
  fi
  IS_SHA+=("$c_sha"); IS_AT+=("$c_at")
done < <(printf '%s\n' "$LOG")

# ── 12. Grouping / join / merge / re-arm ────────────────────────────────
_overlap() {
  # _overlap <sha-a> <sha-b> -> 0 iff their touched-file sets share a path.
  # Both sides are the per-sha F_<sha> argument vectors (loaded fresh or from
  # the `.files` artifacts) — never a comma- or newline-joined string (DEC-5).
  # A real array carries every byte a path can hold; a delimited string cannot.
  # The step-12 grouping hotspot: called once per candidate pair (~n^2), each
  # compare squaring the files-per-commit — the pure-CPU half of issue #603.
  # The clock is a bash builtin, so this check is arithmetic, not a subprocess.
  _budget_ok || _budget_out
  # ponytail: the check gates the CALL, not each path pair — one candidate
  # pair whose file lists are both enormous can run past the budget in a
  # single call. Moving the check into the inner loop would bound even that,
  # at the cost of an arithmetic op per string compare on the hot path; the
  # measured 362 s case (500 candidates x 30 files) trips between calls.
  local a b
  declare -n _aa="F_$1" _bb="F_$2"
  for a in "${_aa[@]}"; do
    [ -z "$a" ] && continue
    for b in "${_bb[@]}"; do
      [ "$a" = "$b" ] && { unset -n _aa _bb; return 0; }
    done
  done
  unset -n _aa _bb
  return 1
}

# Ancestry order (oldest first) so `group_id` is frozen at genuine first sight.
for (( gi=${#IS_SHA[@]}-1; gi>=0; gi-- )); do
  _budget_ok || _budget_out
  n_sha="${IS_SHA[$gi]}"
  # The per-sha array was set in filter (c) (fresh scan) or restored from its
  # `<sha>.files` artifact at hook start; never recomputed, never cleared —
  # the join test needs it after the SHA leaves scope.
  [ -n "${SHA_GROUP[$n_sha]}" ] && continue

  bridged=""
  for s in "${!SHA_GROUP[@]}"; do
    g="${SHA_GROUP[$s]}"
    case " $bridged " in *" $g "*) continue ;; esac
    if _overlap "$n_sha" "$s"; then
      bridged="$bridged $g"
    fi
  done

  set -- $bridged
  if [ "$#" -eq 0 ]; then
    SHA_GROUP["$n_sha"]="$n_sha"          # new one-member group
  elif [ "$#" -eq 1 ]; then
    j_gid="$1"
    SHA_GROUP["$n_sha"]="$j_gid"
    # R1+R2: NO legacy re-arm. The design drops re-arm leniency outright
    # (§3.1, F1) — a joiner of an already-exhausted group reads its own
    # journal count, never a re-armed headroom. `block_counts` is a display
    # value derived from the journal (§3.1) and set in step 14; nothing here
    # mutates it.
  else
    canon=""
    for g in "$@"; do
      if [ -z "$canon" ] || [ "$g" \< "$canon" ]; then canon="$g"; fi
    done
    for g in "$@"; do
      [ "$g" = "$canon" ] && continue
      for s in "${!SHA_GROUP[@]}"; do
        [ "${SHA_GROUP[$s]}" = "$g" ] && SHA_GROUP["$s"]="$canon"
      done
      # Display-only merge collapse: the loser group key leaves the state
      # document so `.block_counts|length` reflects the surviving groups
      # (§3.4 M-3: the persisted map is a display cache, never a decision
      # input). The merged count is NOT computed here — F1 drops the clamp; the
      # journal-derived display value is set in step 14.
      unset "BLOCK_COUNTS[$g]"
    done
    SHA_GROUP["$n_sha"]="$canon"
  fi
done

# C-m: every `--by-files` construction is the single joined token
# `--by-files=<path>`, one per touched path — never a space-separated or
# comma-joined token (a value beginning with `-` would be consumed as a flag).
_by_files_args() {
  BY_ARGS=()
  local p
  declare -n _bf="F_$1"
  for p in "${_bf[@]}"; do
    BY_ARGS+=("--by-files=$p")
  done
  unset -n _bf
}

# ── 13. Clearance — SCOPED TO THIS STOP'S IN-SCOPE SET ──────────────────
declare -A SKIP_SET
if [ -f "$SKIPS_FILE" ]; then
  # `|| [ -n "$sk_tok" ]`: `read` exits non-zero on a final line with no
  # trailing newline, which would silently drop the last skip — on the hook's
  # primary user-facing escape hatch.
  while read -r sk_tok _sk_rest || [ -n "$sk_tok" ]; do
    [ -z "$sk_tok" ] && continue
    sk_norm="$(_git "$SESSION_ROOT" rev-parse --verify "${sk_tok}^{commit}")"
    [ -n "$sk_norm" ] && SKIP_SET["$sk_norm"]=1
  done < "$SKIPS_FILE"
fi

declare -A GROUP_CLEARED GROUP_CLEARED_DURABLE DURABLE_BY_COMMIT
_lookup() {
  # _lookup <args...> -> echoes stdout; sets LOOKUP_RC
  LOOKUP_OUT="$(python3 "$QUERY_SCRIPT" "$@" 2>/dev/null)"
  LOOKUP_RC=$?
}
_lookup_ok() {
  # One lookup, and the ONE place the SIG-3 per-candidate degradation note is
  # worded. Returns non-zero (leaving the candidate unresolved: a PRIMARY
  # caller `continue`s, a FALLBACK caller merely declines to clear — see step
  # 13's ordering note) iff the lookup could not be believed. All four lookups (each
  # of --by-commit / --by-files under each identity key) route through here on
  # purpose: with a copy of this branch per lookup the copies MASKED each other — deleting either one, or rewording the by-files
  # one, turned no test red, because no fixture can fail the second lookup
  # without failing the first. Reads the enclosing loop's $k_sha.
  _lookup "$@"
  if [ "$LOOKUP_RC" -eq 2 ]; then
    # grudge_query.py reserves 2 for argparse's own bad-argument exit and 3 for
    # an internal error, so the two are distinguishable — and they need very
    # different words. Exit 2 is a PERMANENT argv-shape bug in this hook, not a
    # transient store degradation: no retry, no later session, and no correctly
    # recorded grudge can ever clear this candidate. Saying "lookup failed …
    # treating as unresolved" here reports a bug as weather.
    echo "grudge-resolution-guard: clearance lookup for $k_sha was REJECTED as a malformed command line (exit 2) — this is a permanent defect in the hook's argument construction, not a degraded store: no grudge record can clear this commit until it is fixed. Treating as unresolved; use the skips.log escape hatch below." >&2
    return 1
  fi
  if [ "$LOOKUP_RC" -ne 0 ]; then
    echo "grudge-resolution-guard: clearance lookup failed for $k_sha (exit $LOOKUP_RC) — treating as unresolved" >&2
    return 1
  fi
  return 0
}
_worktree_fallback() {
  # True when a SECOND, worktree-keyed identity is worth asking about.
  #
  # Step 7 arms this guard when EITHER identity key has a store dir, but the
  # shared-clone key is the only one the lookups below pass. The two differ
  # exactly inside a linked worktree — and that is where the records land:
  # `scripts/grudge_append.py`'s `resolve_repo()` keys a record by
  # `git rev-parse --show-toplevel`, i.e. the WORKTREE, whenever no
  # `--repo`/`--repo-root` is given, which is how both `skills/grudge/SKILL.md`
  # write mode and `skills/merge-pr/SKILL.md` Step 7.5 call it. So a correctly
  # recorded grudge was invisible to step 13 and the candidate blocked anyway,
  # to MAX_BLOCKS and then to an unenforced give-up. Querying the identities
  # step 7 arms on restores that invariant.
  #
  # Armed on PATH IDENTITY, not on `$WORKTREE_KEY != $SHARED_KEY`: those are
  # basenames, and `git worktree add ~/wt/proj` off `~/src/proj` makes them
  # equal while the two roots are still different directories — which left the
  # fallback disarmed in exactly the shape it exists for. `-ef` compares
  # device+inode, so it also sees through symlinks and `..`.
  [ ! "$SESSION_ROOT" -ef "$STORE_REPO_ROOT" ] && [ -d "$GRUDGE_ROOT/$WORKTREE_KEY" ]
}
for (( ci=0; ci<${#IS_SHA[@]}; ci++ )); do
  # Each uncleared candidate can spawn two to four `python3 grudge_query.py`
  # subprocesses (a second attacker-multiplied fan-out), so the budget is
  # checked before — not after — the clearance lookups.
  _budget_ok || _budget_out
  k_sha="${IS_SHA[$ci]}"
  k_at="${IS_AT[$ci]}"
  k_gid="${SHA_GROUP[$k_sha]}"
  # A DURABLE clear closes the group's scan: skips.log / a by-commit identity
  # match settle its persisted counter, and nothing a later member could add
  # changes that. A group cleared only TRANSIENTLY (by by-files) is NOT closed:
  # it earned this Stop's allowance but no durable reset, and a sibling may
  # still hold the by-commit evidence that upgrades the group to a reset. So
  # the durable doors (skip, by-commit) run for every not-yet-durably-cleared
  # member, and only the transient by-files doors are gated on the group being
  # entirely uncleared.
  [ -n "${GROUP_CLEARED_DURABLE[$k_gid]}" ] && continue
  if [ -n "${SKIP_SET[$k_sha]}" ]; then
    # skips.log is a PERSISTED, commit-identity-keyed user decision: durable.
    GROUP_CLEARED["$k_gid"]=1
    GROUP_CLEARED_DURABLE["$k_gid"]=1
    DURABLE_BY_COMMIT["$k_sha"]=1
    continue
  fi
  # ORDER IS LOAD-BEARING: BOTH PRIMARY (shared-key) lookups run before EITHER
  # worktree fallback, and only a primary may abandon the candidate.
  # Interleaving them put a fallback's `|| continue` in front of the shared
  # `--by-files` lookup, so a merely DEGRADED secondary store — an unreadable
  # `$GRUDGE_ROOT/$WORKTREE_KEY/grudges` (mode 000, foreign uid after a
  # sudo/container run, a stale NFS mount) — suppressed a clearance the primary
  # would have granted, blocking a resolved candidate to MAX_BLOCKS. A failed
  # FALLBACK therefore leaves the candidate unresolved WITHOUT `continue`ing:
  # the primaries have already answered, and an unbelievable extra opinion must
  # not retract them.
  # The by-commit lookup resolves a COMMIT IDENTITY in the object store —
  # branch-independent, so it is monotone across ordinary `git checkout`; only a
  # rebase that orphans the object stops it. A match is durable evidence.
  _lookup_ok --by-commit "$k_sha" --repo-root "$STORE_REPO_ROOT" "--repo=$SHARED_KEY" \
             --session-root "$SESSION_ROOT" || continue
  if [ -n "$LOOKUP_OUT" ]; then
    GROUP_CLEARED["$k_gid"]=1
    GROUP_CLEARED_DURABLE["$k_gid"]=1
    DURABLE_BY_COMMIT["$k_sha"]=1
    continue
  fi
  # The by-files lookup keys on survivors() = os.path.exists in the CURRENT
  # WORKING TREE (#608). A `git checkout` to a branch where the grudge's files
  # are absent silently revokes it, so the clearance perspective granted by it
  # is not monotone. It still clears THIS Stop (the resolution is visible right
  # now — the t19g/t23dash by-files clearances depend on that), but it must NOT
  # spend the PERSISTED block counter: a held reset on flippable evidence is
  # exactly how each false->true->false branch cycle restores full MAX_BLOCKS.
  if [ -z "${GROUP_CLEARED[$k_gid]}" ]; then
    _by_files_args "$k_sha"
    _lookup_ok "${BY_ARGS[@]}" --candidate-sha "$k_sha" --candidate-at "$k_at" \
               --repo-root "$STORE_REPO_ROOT" "--repo=$SHARED_KEY" --session-root "$SESSION_ROOT" || continue
    if [ -n "$LOOKUP_OUT" ]; then
      # TRANSIENT, so this candidate is NOT done: `continue`ing here would skip
      # the worktree by-commit door below for THIS SAME candidate — the
      # same-member form of the cross-member shadowing the group gating above
      # fixes. In a linked worktree (the shape _worktree_fallback exists for)
      # the candidate's own grudge is recorded worktree-keyed WITH a
      # fixed_in_commit, while some older, unrelated shared-store grudge can
      # match by files first; jumping to the next candidate would leave the
      # group transient despite its own durable commit-identity evidence.
      GROUP_CLEARED["$k_gid"]=1
    fi
  fi
  if _worktree_fallback; then
    if _lookup_ok --by-commit "$k_sha" --repo-root "$SESSION_ROOT" "--repo=$WORKTREE_KEY" \
                  --session-root "$SESSION_ROOT" && [ -n "$LOOKUP_OUT" ]; then
      GROUP_CLEARED["$k_gid"]=1
    GROUP_CLEARED_DURABLE["$k_gid"]=1
    DURABLE_BY_COMMIT["$k_sha"]=1
      continue
    fi
    if [ -z "${GROUP_CLEARED[$k_gid]}" ]; then
      _by_files_args "$k_sha"
      if _lookup_ok "${BY_ARGS[@]}" --candidate-sha "$k_sha" --candidate-at "$k_at" \
                    --repo-root "$SESSION_ROOT" "--repo=$WORKTREE_KEY" --session-root "$SESSION_ROOT" \
         && [ -n "$LOOKUP_OUT" ]; then
        GROUP_CLEARED["$k_gid"]=1
      fi
    fi
  fi
done
# Clearance is a durable counter reset: sha_group stays persisted; the
# per-sha `<sha>.files` artifacts stay on disk.
# R1+R2 (§3.1/§3.2): the durable `CLEAR` is minted per durably-demonstrated
# member, written to the JOURNAL (a skips.log line naming m, or a grudge
# resolving m by --by-commit identity — both branch-independent). A by-files
# (working-tree) resolution clears THIS Stop (GROUP_CLEARED) but mints no
# CLEAR (C-n, §3.1 mechanism 6). Durability lives in the journal now, not in
# the state JSON's mutable counter.
declare -A DURABLE_CLEARED
for g in "${!GROUP_CLEARED_DURABLE[@]}"; do
  for s in "${!SHA_GROUP[@]}"; do
    [ "${SHA_GROUP[$s]}" = "$g" ] || continue
    # `done(m)` is per-member: only members whose OWN resolution was durable
    # this Stop get a CLEAR line (F-1 / §3.6). The group being durably cleared
    # as a whole (any member durable) does NOT fan a CLEAR out to every member.
    :
  done
done
# Per-member durable evidence is collected in step 13: skips.log line naming
# the member, or a --by-commit match for that member (the SKIP_SET/by-commit
# branches above set GROUP_CLEARED_DURABLE at the GROUP level because this
# Stop's block decision is group-scoped, but the journal CLEAR must be
# per-demonstrated-member). Re-derive the per-member set from SKIP_SET and the
# durable-commit lookups the same way step 13 did, so the journal never extends
# a durable reset to a co-member that earned nothing.
for s in "${!SKIP_SET[@]}"; do DURABLE_CLEARED["$s"]=0; done
for s in "${!DURABLE_BY_COMMIT[@]}"; do DURABLE_CLEARED["$s"]=0; done
if [ "${#DURABLE_CLEARED[@]}" -gt 0 ]; then
  _journal_append_group CLEAR "" "${!DURABLE_CLEARED[@]}"
  if [ "$APPEND_OK" -ne 1 ]; then
    echo "grudge-resolution-guard: could not persist the durable CLEAR to the journal — a cleared member will not be retired from scope; blocking continues. This is a degraded loud allow, never a silent reset." >&2
  else
    # Witness CLEARED (healthy terminal event, §5b.2): one line per clearing
    # Stop, carrying the last known BLOCK batch nonce the clear resolves.
    _clear_nonce="-"
    for _cm in "${!DURABLE_CLEARED[@]}"; do
      _cg="${SHA_GROUP[$_cm]:-}"
      if [ -n "$_cg" ] && [ -n "${LAST_BLOCK_NONCE[$_cg]:-}" ]; then
        _clear_nonce="${LAST_BLOCK_NONCE[$_cg]}"
        break
      fi
    done
    _witness_outcome CLEARED "$_clear_nonce"
  fi
fi

# ── 14. Blocking — THE JOURNAL BLOCK PREDICATE (§3.2) ────────────────────
# block(g) holds iff every conjunct holds, decided per §3.2's loud-allow table:
#   ( read(g) = COUNT(n) ∧ n < MAX_BLOCKS
#     ∨ read(g) = ABSENT ∧ ¬(stop_hook_active present ∧ true) )
#   ∧ append_succeeded(this Stop's BLOCK\t<m>\t<nonce> for EVERY member m of g)
#   ∧ ( max over m in g of blocks(m) ) <= MAX_BLOCKS   -- ordinal, after append
# Every other combination is a LOUD ALLOW (the table's rows), and a give-up
# retirement appends GIVEUP\t<m> per member whose OWN blocks(m) >= MAX_BLOCKS.
# The read is taken BEFORE this Stop's own append (timing 1, §3.1 OBS-1); the
# ordinal conjunct (timing 2) and display_count (timing 3) are taken after.

# §3.2 done(m): "m is in scope for the next Stop iff ¬done(m)" — a member whose
# most recent journal record is CLEAR or GIVEUP is RETIRED and must not be a
# blocking candidate (cheap single journal pass over the candidate set, minting
# nothing).
_journal_pass "${IS_SHA[@]}"

declare -A GROUP_MEMBERS
GROUP_ORDER=()
for (( bi=0; bi<${#IS_SHA[@]}; bi++ )); do
  b_sha="${IS_SHA[$bi]}"
  b_gid="${SHA_GROUP[$b_sha]}"
  [ -n "${GROUP_CLEARED[$b_gid]}" ] && continue
  [ "${JBLAST[$b_sha]:-}" = "CLEAR" ] && continue
  [ "${JBLAST[$b_sha]:-}" = "GIVEUP" ] && continue
  if [ -z "${GROUP_MEMBERS[$b_gid]}" ]; then
    GROUP_ORDER+=("$b_gid")
    GROUP_MEMBERS["$b_gid"]="$b_sha"
  else
    GROUP_MEMBERS["$b_gid"]="${GROUP_MEMBERS[$b_gid]} $b_sha"
  fi
done

# stop_hook_active presence (§3.5, INV-C8 clause 2 amended): the flag exists
# for the ABSENT row only — and only as a conjunct that FORBIDS a block.
STOP_HOOK_ACTIVE_PRESENT="$(printf '%s' "$INPUT" | jq 'has("stop_hook_active")' 2>/dev/null)"
STOP_HOOK_ACTIVE_TRUE=0
if [ "$STOP_HOOK_ACTIVE_PRESENT" = "true" ] && [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  STOP_HOOK_ACTIVE_TRUE=1
fi

BLOCKING=()
declare -A GIVEUP_SHAS
_nonce_batch() {
  local g="$1"; shift
  local nonce APPEND_OK ordinal
  nonce="$(_journal_nonce)"
  if [ -z "$nonce" ]; then
    echo "grudge-resolution-guard: nonce generation failed (M-6) — journal append treated as failed; loud allow" >&2
    return 1
  fi
  _journal_append_group BLOCK "$nonce" "$@"
  if [ "$APPEND_OK" -ne 1 ]; then
    echo "grudge-resolution-guard: journal append failed for at least one member of group $g — an unwritable \$STATE_DIR is a bound the hook cannot honour; loud allow ($STATE_DIR)" >&2
    return 1
  fi
  ordinal="$(_journal_ordinal "$nonce" "$@")"
  if [ -z "$ordinal" ] || [ "$ordinal" = "UNMEASURABLE" ]; then
    echo "grudge-resolution-guard: could not locate this Stop's own nonce in group $g's BLOCK history — UNMEASURABLE; loud allow" >&2
    return 1
  fi
  if [ "$ordinal" -gt "$MAX_BLOCKS" ]; then
    # §3.4: this Stop's batch lost the ordinal race (a concurrent Stop already
    # used this ordinal); its BLOCK lines are retained (C-a) and it allows.
    echo "grudge-resolution-guard: lost the ordinal race for group $g (max $ordinal > $MAX_BLOCKS) — loud allow; retained BLOCK lines are an over-count, not a reset" >&2
    return 1
  fi
  BLOCKING+=("$g")
  BLOCK_COUNTS["$g"]="$(_display_count "$@")"
  LAST_BLOCK_NONCE["$g"]="$nonce"
  _witness_outcome BLOCK "$nonce"
  return 0
}
_giveup_loud() {
  # §3.2 give-up row: append GIVEUP\t<m> for each member whose OWN
  # blocks(m) >= MAX_BLOCKS this Stop; only those retire. Under-MAX co-members
  # stay in scope (FATAL-2 / §3.6 with per-member done(m)).
  local g="$1"; shift
  local m own
  for m in "$@"; do
    own="$(_journal_read "$m")"
    case "$own" in
      COUNT:*)
        [ "${own#COUNT:}" -ge "$MAX_BLOCKS" ] || continue
        GIVEUP_SHAS[$m]="${own#COUNT:}" ;;
    esac
  done
  [ "${#GIVEUP_SHAS[@]}" -gt 0 ] || return 0
  _journal_append_group GIVEUP "" "${!GIVEUP_SHAS[@]}"
  # Witness GIVEUP (healthy terminal event, §5b.2): the nonce of the last BLOCK
  # line this group's give-up resolves, when one was recorded this session.
  _witness_outcome GIVEUP "${LAST_BLOCK_NONCE[$g]:--}"
  return 0
}

QUARANTINED=0
for g in "${GROUP_ORDER[@]}"; do
  _budget_ok || _budget_out
  members="${GROUP_MEMBERS[$g]}"
  set -- $members

  # Timing 1: read(g) BEFORE this Stop's own append.
  grp_read="$(_journal_read_group "$@")"
  case "$grp_read" in
    UNMEASURABLE)
      # §3.2 UNMEASURABLE row → loud allow. C-q: if the journal is malformed or
      # past the line ceiling, quarantine ONCE and re-arm (COUNT(0) re-nag).
      if [ "$QUARANTINED" -eq 0 ]; then
        _journal_quarantine
        QUARANTINED=1
      fi
      echo "grudge-resolution-guard: journal read UNMEASURABLE for group $g — loud allow; grudge compliance NOT enforced this Stop" >&2
      ;;
    ABSENT)
      if [ "$STOP_HOOK_ACTIVE_PRESENT" = "true" ] && [ "$STOP_HOOK_ACTIVE_TRUE" -eq 1 ]; then
        # unaccountable → loud allow (no journal file + the flag is set).
        echo "grudge-resolution-guard: no journal yet and stop_hook_active is true — unaccountable; loud allow" >&2
      elif [ "$STOP_HOOK_ACTIVE_PRESENT" != "true" ]; then
        # §3.5: the flag field is missing from the payload → harness-drift note.
        echo "grudge-resolution-guard: stop_hook_active is absent from the payload — harness drift suspected; loud allow (§3.5)" >&2
      else
        # ABSENT ∧ active=false → genuine first Stop; n = 0, may block.
        # Attempt the block: this fall-through sets the nonce decisions below.
        if ! _nonce_batch "$g" "$@"; then
          :  # loud allow already printed
        fi
      fi
      ;;
    COUNT:*)
      n="${grp_read#COUNT:}"
      if [ "$n" -lt "$MAX_BLOCKS" ]; then
        _nonce_batch "$g" "$@"
      else
        # give-up row: read(g) = COUNT(n), n >= MAX_BLOCKS.
        _giveup_loud "$g" "$@"
      fi
      ;;
  esac
done

# ── 14a. The block attempt — append_succeeded + ordinal conjunct (§3.2/§3.4)
# _nonce_batch <group> <member...>
# Appends this Stop's BLOCK\t<m>\t<nonce> line for EVERY member of the group
# (same nonce for the whole batch — §3.1). On success re-reads and computes the
# ordinal max over members up to this Stop's own nonce. Blocks (adds to
# BLOCKING) only when: append_succeeded AND ordinal max <= MAX_BLOCKS. Any
# failure is a loud allow, never a silent block; the landed lines stay (C-a).


# ── 14b. Display refresh — `.block_counts` is a DISPLAY-only value (§3.1/§8):
# the (n/3) message and the state-JSON `block_counts` are computed from the
# journal AFTER this Stop's own appends, per group (max over members of
# blocks(m)); it is never read back as the bound (OBS-1). Every group that
# still has members mapped (in-scope, blocked, cleared, or merged) is
# refreshed, so a durable CLEAR this Stop re-reads its members as COUNT(0).
for _g in "${!SHA_GROUP[@]}"; do
  BLACK=(); _g_black=" "
  for _m in "${!SHA_GROUP[@]}"; do
    [ "${SHA_GROUP[$_m]}" = "${SHA_GROUP[$_g]}" ] || continue
    case " $_g_black " in *" $_m "*) continue ;; esac
    _g_black="$_g_black $_m "
    BLACK+=("$_m")
  done
  [ "${#BLACK[@]}" -gt 0 ] || continue
  BLOCK_COUNTS["${SHA_GROUP[$_g]}"]="$(_display_count "${BLACK[@]}")"
done

# ── 16. Checkpoint advance (§3.2 C-p) ────────────────────────────────────
# last_checked_sha = parent of `git merge-base --octopus` of the in-scope set;
# floor-exclusive, so the merge-base itself stays inside floor..HEAD. The
# in-scope set is the members that are NOT done(m) (done = most recent record
# CLEAR or GIVEUP in the journal — a durable clear or give-up this Stop, or
# earlier). HEAD when the set is empty; the committed empty-tree sentinel
# ("ROOT") when the merge-base is a parentless root. Transient (by-files)
# clears never advance — a by-files member is ¬done and stays in scope.
IN_SCOPE=()
for s in "${IS_SHA[@]}"; do
  _journal_pass "$s"
  last_record="${JBLAST[$s]:-}"
  if [ "$last_record" != "CLEAR" ] && [ "$last_record" != "GIVEUP" ]; then
    IN_SCOPE+=("$s")
  fi
done

LAST_NEW="$SCAN_HEAD"
if [ "${#IN_SCOPE[@]}" -gt 0 ]; then
  mb="$(_git "$SESSION_ROOT" merge-base --octopus "${IN_SCOPE[@]}")"
  if [ -n "$mb" ]; then
    parent="$(_git "$SESSION_ROOT" rev-parse --verify "${mb}^")"
    if [ -n "$parent" ]; then
      LAST_NEW="$parent"
    else
      # Parentless merge-base: the committed empty-tree sentinel, never a git
      # object id (a parentless root has no ^; the loader's ROOT branch rescans).
      LAST_NEW="ROOT"
    fi
  else
    LAST_NEW="$SCAN_HEAD"
  fi
fi

# ── Persist state atomically (INV-C12: version + four display/checkpoint
# fields — `sha_files` is NOT a field; per-sha files live in `.files`). The
# journal is the bound; this document is display + checkpoint only (C-f: its
# write is flock-guarded best-effort, never a decision input, §3.4).
_write_state() {
  local tmp="$STATE_FILE.tmp.$$"
  {
    printf 'V\t%s\n' "$STATE_VERSION"
    printf 'L\t%s\n' "$LAST_NEW"
    printf 'S\t%s\n' "$SEEDED_AT"
    for s in "${!SHA_GROUP[@]}"; do printf 'G\t%s\t%s\n' "$s" "${SHA_GROUP[$s]}"; done
    for s in "${!BLOCK_COUNTS[@]}"; do printf 'B\t%s\t%s\n' "$s" "${BLOCK_COUNTS[$s]}"; done
  } | jq -R -s '
      split("\n") | map(select(length > 0) | split("\t")) |
      {
        version:          (((map(select(.[0] == "V"))[0] // ["V", "0"])[1]) | tonumber),
        last_checked_sha: ((map(select(.[0] == "L"))[0] // ["L", ""])[1]),
        seeded_at:        (((map(select(.[0] == "S"))[0] // ["S", "0"])[1]) | tonumber),
        sha_group:        (map(select(.[0] == "G")) | map({key: .[1], value: .[2]}) | from_entries),
        block_counts:     (map(select(.[0] == "B")) | map({key: .[1], value: (.[2] | tonumber)}) | from_entries)
      }' > "$tmp" 2>/dev/null
  if [ ! -s "$tmp" ]; then
    rm -f "$tmp" 2>/dev/null
    return 1
  fi
  # flock -n: a lock failure skips only this display write, never the bound
  # decision (C-f, §3.4). Kernel-released on fd close, non-blocking.
  { flock -n 9
    if ! mv -f "$tmp" "$STATE_FILE" 2>/dev/null; then
      rm -f "$tmp" 2>/dev/null
      return 1
    fi
  } 9<"$STATE_DIR"
  return 0
}
_write_state

# ── 15. Messages ────────────────────────────────────────────────────────
# C-k + S-17 (SIEGE-R2-H3): the printed `>> skips.log` remedy promises the
# target is writable. PROVING that by appending is itself a write to a fixed
# $STATE_DIR path, so the probe is time-bounded — a mkfifo'd skips.log costs
# the 1 s bound, never the hook's own timeout — and a failed probe only
# degrades the message, never a verdict.
_skips_probe_ok() {
  timeout 1 bash -c 'printf "" >> "$1"' _ "$SKIPS_FILE" 2>/dev/null
}

_prefill() {
  # Exactly ONE fixed, copy-pasteable record-a-grudge command per still-
  # unresolved candidate SHA: `--files-from` names the NUL-delimited
  # `$STATE_DIR/<sha>.files` artifact, which the shell passes through UNPARSED
  # — no element of any filename can become shell syntax or a rendered path
  # (§3.2 message content, SIEGE-R2-H1/H2). --repo-root/--repo remain
  # UNCONDITIONALLY the shared-clone pair — exactly the identity step 13's
  # lookups query — so the recorded grudge clears the very next Stop from ANY
  # worktree of the clone.
  #
  # C-k: printed only when the target is a readable REGULAR file this Stop has
  # on disk — a missing or mkfifo'd target would hand the maintainer a dead
  # command, so it degrades to SHA-and-count-only instead.
  local sha="$1" files_path
  files_path="$STATE_DIR/$sha.files"
  if [ -f "$files_path" ]; then
    printf '    python3 "%s" --files-from="%s" --candidate-sha="%s" --symptom "<one line: what broke>" --repo-root "%s" --repo="%s"\n' \
      "$APPEND_SCRIPT" "$files_path" "$sha" "$STORE_REPO_ROOT" "$SHARED_KEY" >&2
  fi
}

# Give-up (NEW-F): one message naming ALL retired member SHAs in the same Stop,
# SHA + count only — never any touched-file name on any channel (§3.2).
if [ "${#GIVEUP_SHAS[@]}" -gt 0 ]; then
  retired=""
  for m in "${!GIVEUP_SHAS[@]}"; do
    c="${GIVEUP_SHAS[$m]}"
    [ -z "$retired" ] || retired="$retired, "
    retired="${retired}${m:0:9}(+$c) "
  done
  echo "grudge-resolution-guard: giving up after $MAX_BLOCKS blocks on $retired — no grudge or skip entry was ever recorded for these commits. Allowing Stop to avoid an unbreakable loop; their grudge compliance was NOT enforced. (Record a grudge to clear an in-scope sibling; exhausted members are retired per-member.)" >&2
  for m in "${!GIVEUP_SHAS[@]}"; do
    _prefill "$m"
  done
fi

if [ "${#BLOCKING[@]}" -gt 0 ]; then
  # stop_hook_active is consulted only to WORD the message — never a gate
  # (INV-C8 clause 2 amended: a conjunct that forbids a block only).
  REBLOCK_NOTE=""
  if [ "$STOP_HOOK_ACTIVE_TRUE" -eq 1 ]; then
    REBLOCK_NOTE=" (this is a re-block after your last turn)"
  fi
  echo "grudge-resolution-guard: blocked — ${#BLOCKING[@]} unresolved fix(*) group(s):$REBLOCK_NOTE" >&2
  for g in "${BLOCKING[@]}"; do
    members="${GROUP_MEMBERS[$g]}"
    listed="$(printf '%s' "$members" | tr ' ' ',' | sed 's/,/, /g')"
    echo "  $listed — attempt (${BLOCK_COUNTS[$g]}/$MAX_BLOCKS) — record a grudge, or skip it:" >&2
    for m in $members; do
      _prefill "$m"
    done
    set -- $members
    if _skips_probe_ok; then
      echo "    echo \"$1 <reason>\" >> \"$SKIPS_FILE\"" >&2
    fi
  done
  exit 2
fi

exit 0
