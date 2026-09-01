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
# transcript, non-git cwd, absent grudge store — allows. Never fail closed.
#
# Configured in .claude/settings.json:
#   "hooks": { "Stop": [{ "matcher": "*", "hooks": [{ "type": "command",
#     "command": "bash hooks/grudge-resolution-guard.sh", "timeout": 500 }] }] }

# Disable errexit — this hook must never fail fatally (INV-C7)
set +e

MAX_BLOCKS=3

# `git -C <dir>` ONLY chdirs — it does not clear GIT_DIR / GIT_WORK_TREE, which
# outrank discovery-from-cwd. A Stop hook fires in exactly the environments
# where those variables live, so every git call runs with a scrubbed
# environment or it silently targets a different repository and the wrong
# answer is indistinguishable from a right one.
_git() {
  local d="$1"; shift
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_OBJECT_DIRECTORY \
      -u GIT_ALTERNATE_OBJECT_DIRECTORIES -u GIT_COMMON_DIR -u GIT_NAMESPACE \
      -u GIT_CEILING_DIRECTORIES \
      git -C "$d" "$@" 2>/dev/null
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

# ── 8. State file (INV-C12's five fields) + the separate skips log ──────
STATE_FILE="$STATE_DIR/$SESSION_ID.json"
SKIPS_FILE="$STATE_DIR/skips.log"

CRUCIBLE_ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ ! -f "$CRUCIBLE_ROOT/scripts/grudge_query.py" ]; then
  CRUCIBLE_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
fi
QUERY_SCRIPT="$CRUCIBLE_ROOT/scripts/grudge_query.py"
APPEND_SCRIPT="$CRUCIBLE_ROOT/scripts/grudge_append.py"

declare -A SHA_GROUP SHA_FILES BLOCK_COUNTS

_load_maps() {
  while IFS=$'\t' read -r k v; do
    [ -n "$k" ] && SHA_GROUP["$k"]="$v"
  done < <(jq -r '(.sha_group // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)
  while IFS=$'\t' read -r k v; do
    [ -n "$k" ] && SHA_FILES["$k"]="$v"
  done < <(jq -r '(.sha_files // {}) | to_entries[] | "\(.key)\t\(.value | join(","))"' "$STATE_FILE" 2>/dev/null)
  while IFS=$'\t' read -r k v; do
    [ -n "$k" ] && BLOCK_COUNTS["$k"]="$v"
  done < <(jq -r '(.block_counts // {}) | to_entries[] | "\(.key)\t\(.value)"' "$STATE_FILE" 2>/dev/null)
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
    elif _git "$SESSION_ROOT" cat-file -e "${LAST_SHA}^{commit}"; then
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

SCAN_HEAD="$(_git "$SESSION_ROOT" rev-parse HEAD)"

# ── 11. Candidate filter -> THIS Stop's IN-SCOPE SET ────────────────────
# (a) subject matches ^fix[(:]  (b) %at >= seeded_at  (c) >=1 non-.md path.
# The subject is EVERYTHING after the second `|`, so an embedded `|` cannot
# truncate it. --root so a parentless root commit still lists its paths.
IS_SHA=(); IS_AT=(); IS_FILES=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  c_sha="${line%%|*}"
  c_rest="${line#*|}"
  c_at="${c_rest%%|*}"
  c_subj="${c_rest#*|}"
  case "$c_sha" in ''|*[!0-9a-fA-F]*) continue ;; esac
  case "$c_at" in ''|*[!0-9]*) continue ;; esac
  printf '%s' "$c_subj" | grep -qE '^fix[(:]' || continue
  [ "$c_at" -ge "$SEEDED_AT" ] || continue
  c_files="${SHA_FILES[$c_sha]}"
  if [ -z "$c_files" ]; then
    c_raw="$(_git "$SESSION_ROOT" diff-tree --root --no-commit-id --name-only -r "$c_sha")"
    [ -z "$c_raw" ] && continue
    printf '%s\n' "$c_raw" | grep -qvE '\.md$' || continue
    c_files="$(printf '%s' "$c_raw" | tr '\n' ',')"
    c_files="${c_files%,}"
  else
    printf '%s\n' "${c_files//,/$'\n'}" | grep -qvE '\.md$' || continue
  fi
  IS_SHA+=("$c_sha"); IS_AT+=("$c_at"); IS_FILES+=("$c_files")
done < <(printf '%s\n' "$LOG")

# ── 12. Grouping / join / merge / re-arm ────────────────────────────────
_overlap() {
  # _overlap <csv-a> <csv-b> -> 0 iff they share at least one path
  local a b
  local -a AA BB
  local IFS=','
  read -r -a AA <<< "$1"
  read -r -a BB <<< "$2"
  IFS=$' \t\n'
  for a in "${AA[@]}"; do
    [ -z "$a" ] && continue
    for b in "${BB[@]}"; do
      [ "$a" = "$b" ] && return 0
    done
  done
  return 1
}

# Ancestry order (oldest first) so `group_id` is frozen at genuine first sight.
for (( gi=${#IS_SHA[@]}-1; gi>=0; gi-- )); do
  n_sha="${IS_SHA[$gi]}"
  n_files="${IS_FILES[$gi]}"
  # Persisted once from filter (c)'s own diff-tree output; never recomputed,
  # never cleared — the join test needs it after the SHA leaves scope.
  [ -z "${SHA_FILES[$n_sha]}" ] && SHA_FILES["$n_sha"]="$n_files"
  [ -n "${SHA_GROUP[$n_sha]}" ] && continue

  bridged=""
  for s in "${!SHA_GROUP[@]}"; do
    g="${SHA_GROUP[$s]}"
    case " $bridged " in *" $g "*) continue ;; esac
    if _overlap "$n_files" "${SHA_FILES[$s]}"; then
      bridged="$bridged $g"
    fi
  done

  set -- $bridged
  if [ "$#" -eq 0 ]; then
    SHA_GROUP["$n_sha"]="$n_sha"          # new one-member group
  elif [ "$#" -eq 1 ]; then
    j_gid="$1"
    SHA_GROUP["$n_sha"]="$j_gid"
    j_cur="${BLOCK_COUNTS[$j_gid]:-0}"
    if [ "$j_cur" -ge "$MAX_BLOCKS" ]; then
      # Re-arm: min(existing, MAX_BLOCKS-1). A never-blocked joiner is not a
      # logical continuation of a commit the guard already gave up on.
      BLOCK_COUNTS["$j_gid"]=$(( MAX_BLOCKS - 1 ))
    fi
  else
    canon=""; m_max=0
    for g in "$@"; do
      if [ -z "$canon" ] || [ "$g" \< "$canon" ]; then canon="$g"; fi
      m_c="${BLOCK_COUNTS[$g]:-0}"
      [ "$m_c" -gt "$m_max" ] && m_max="$m_c"
    done
    for g in "$@"; do
      [ "$g" = "$canon" ] && continue
      for s in "${!SHA_GROUP[@]}"; do
        [ "${SHA_GROUP[$s]}" = "$g" ] && SHA_GROUP["$s"]="$canon"
      done
      unset "BLOCK_COUNTS[$g]"
    done
    SHA_GROUP["$n_sha"]="$canon"
    # merged_count = min(max(merging counts), MAX_BLOCKS-1), unconditionally.
    [ "$m_max" -gt $(( MAX_BLOCKS - 1 )) ] && m_max=$(( MAX_BLOCKS - 1 ))
    BLOCK_COUNTS["$canon"]="$m_max"
  fi
done

# ── 13. Clearance — SCOPED TO THIS STOP'S IN-SCOPE SET ──────────────────
declare -A SKIP_SET
if [ -f "$SKIPS_FILE" ]; then
  while read -r sk_tok _sk_rest; do
    [ -z "$sk_tok" ] && continue
    sk_norm="$(_git "$SESSION_ROOT" rev-parse --verify "${sk_tok}^{commit}")"
    [ -n "$sk_norm" ] && SKIP_SET["$sk_norm"]=1
  done < "$SKIPS_FILE"
fi

declare -A GROUP_CLEARED
_lookup() {
  # _lookup <args...> -> echoes stdout; sets LOOKUP_RC
  LOOKUP_OUT="$(python3 "$QUERY_SCRIPT" "$@" 2>/dev/null)"
  LOOKUP_RC=$?
}
for (( ci=0; ci<${#IS_SHA[@]}; ci++ )); do
  k_sha="${IS_SHA[$ci]}"
  k_at="${IS_AT[$ci]}"
  k_gid="${SHA_GROUP[$k_sha]}"
  [ -n "${GROUP_CLEARED[$k_gid]}" ] && continue
  if [ -n "${SKIP_SET[$k_sha]}" ]; then
    GROUP_CLEARED["$k_gid"]=1
    continue
  fi
  _lookup --by-commit "$k_sha" --repo-root "$STORE_REPO_ROOT" --repo "$SHARED_KEY" \
          --session-root "$SESSION_ROOT"
  if [ "$LOOKUP_RC" -ne 0 ]; then
    echo "grudge-resolution-guard: clearance lookup failed for $k_sha (exit $LOOKUP_RC) — treating as unresolved" >&2
    continue
  fi
  if [ -n "$LOOKUP_OUT" ]; then
    GROUP_CLEARED["$k_gid"]=1
    continue
  fi
  _lookup --by-files "${SHA_FILES[$k_sha]}" --candidate-sha "$k_sha" --candidate-at "$k_at" \
          --repo-root "$STORE_REPO_ROOT" --repo "$SHARED_KEY" --session-root "$SESSION_ROOT"
  if [ "$LOOKUP_RC" -ne 0 ]; then
    echo "grudge-resolution-guard: clearance lookup failed for $k_sha (exit $LOOKUP_RC) — treating as unresolved" >&2
    continue
  fi
  [ -n "$LOOKUP_OUT" ] && GROUP_CLEARED["$k_gid"]=1
done
# Clearance is a pure counter reset: sha_group / sha_files stay persisted.
for g in "${!GROUP_CLEARED[@]}"; do
  BLOCK_COUNTS["$g"]=0
done

# ── 14. Blocking — CHECK, THEN INCREMENT AT MOST ONCE PER GROUP ─────────
declare -A GROUP_MEMBERS
GROUP_ORDER=()
for (( bi=0; bi<${#IS_SHA[@]}; bi++ )); do
  b_sha="${IS_SHA[$bi]}"
  b_gid="${SHA_GROUP[$b_sha]}"
  [ -n "${GROUP_CLEARED[$b_gid]}" ] && continue
  if [ -z "${GROUP_MEMBERS[$b_gid]}" ]; then
    GROUP_ORDER+=("$b_gid")
    GROUP_MEMBERS["$b_gid"]="$b_sha"
  else
    GROUP_MEMBERS["$b_gid"]="${GROUP_MEMBERS[$b_gid]} $b_sha"
  fi
done

BLOCKING=(); GIVEUP=()
for g in "${GROUP_ORDER[@]}"; do
  cur="${BLOCK_COUNTS[$g]:-0}"
  if [ "$cur" -lt "$MAX_BLOCKS" ]; then
    BLOCK_COUNTS["$g"]=$(( cur + 1 ))
    BLOCKING+=("$g")
  else
    GIVEUP+=("$g")
  fi
done

# ── 16. Checkpoint advance ──────────────────────────────────────────────
# Advances past a commit only once it is cleared or its group exhausted.
LAST_NEW="$SCAN_HEAD"
if [ "${#BLOCKING[@]}" -gt 0 ]; then
  earliest=""
  for (( ei=0; ei<${#IS_SHA[@]}; ei++ )); do
    e_sha="${IS_SHA[$ei]}"
    e_gid="${SHA_GROUP[$e_sha]}"
    for g in "${BLOCKING[@]}"; do
      if [ "$g" = "$e_gid" ]; then earliest="$e_sha"; break; fi
    done
  done
  if [ -n "$earliest" ]; then
    parent="$(_git "$SESSION_ROOT" rev-parse --verify "${earliest}^")"
    if [ -n "$parent" ]; then
      LAST_NEW="$parent"
    else
      # Parentless candidate: the literal sentinel, never a git object id.
      LAST_NEW="ROOT"
    fi
  fi
fi

# ── Persist state atomically (INV-C12's exact five fields) ──────────────
_write_state() {
  local tmp="$STATE_FILE.tmp.$$"
  {
    printf 'L\t%s\n' "$LAST_NEW"
    printf 'S\t%s\n' "$SEEDED_AT"
    for s in "${!SHA_GROUP[@]}"; do printf 'G\t%s\t%s\n' "$s" "${SHA_GROUP[$s]}"; done
    for s in "${!SHA_FILES[@]}"; do printf 'F\t%s\t%s\n' "$s" "${SHA_FILES[$s]}"; done
    for s in "${!BLOCK_COUNTS[@]}"; do printf 'B\t%s\t%s\n' "$s" "${BLOCK_COUNTS[$s]}"; done
  } | jq -R -s '
      split("\n") | map(select(length > 0) | split("\t")) |
      {
        last_checked_sha: ((map(select(.[0] == "L"))[0] // ["L", ""])[1]),
        seeded_at:        (((map(select(.[0] == "S"))[0] // ["S", "0"])[1]) | tonumber),
        sha_group:        (map(select(.[0] == "G")) | map({key: .[1], value: .[2]}) | from_entries),
        sha_files:        (map(select(.[0] == "F")) | map({key: .[1], value: (.[2] | split(","))}) | from_entries),
        block_counts:     (map(select(.[0] == "B")) | map({key: .[1], value: (.[2] | tonumber)}) | from_entries)
      }' > "$tmp" 2>/dev/null
  if [ -s "$tmp" ]; then
    mv -f "$tmp" "$STATE_FILE" 2>/dev/null
  else
    rm -f "$tmp" 2>/dev/null
  fi
}
_write_state

# ── 15. Messages ────────────────────────────────────────────────────────
_prefill() {
  # One fully-resolved, copy-pasteable record-a-grudge command per still-
  # unresolved candidate SHA. --repo-root/--repo are UNCONDITIONALLY the
  # shared-clone pair — exactly the identity step 13's lookup queries — so the
  # recorded grudge clears the very next Stop from ANY worktree of the clone.
  printf '    python3 "%s" --symptom "<one line: what broke>" --files "%s" --commit "%s" --repo-root "%s" --repo "%s"\n' \
    "$APPEND_SCRIPT" "${SHA_FILES[$1]}" "$1" "$STORE_REPO_ROOT" "$SHARED_KEY" >&2
}

for g in "${GIVEUP[@]}"; do
  echo "grudge-resolution-guard: giving up after $MAX_BLOCKS blocks on $g — no grudge or skip entry was ever recorded. Allowing Stop to avoid an unbreakable loop; this commit's grudge compliance was NOT enforced." >&2
  for m in ${GROUP_MEMBERS[$g]}; do
    _prefill "$m"
  done
done

if [ "${#BLOCKING[@]}" -gt 0 ]; then
  # stop_hook_active is consulted ONLY here, to word the message.
  REBLOCK_NOTE=""
  if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
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
    echo "    echo \"$1 <reason>\" >> \"$SKIPS_FILE\"" >&2
  done
  exit 2
fi

exit 0
