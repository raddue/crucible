---
ticket: "#174"
title: "Build Routing Enforcement — Implementation Plan"
created: 2026-04-14
status: ready-for-execution
design: docs/plans/2026-04-14-build-routing-enforcement-design.md
prd: docs/prds/2026-04-14-build-routing-enforcement-prd.md
red-canary: hooks/tests/test-build-routing-advisor.sh
---

# Build Routing Enforcement — Implementation Plan

## Overview

Implement the two-part defense from the design doc:

- **Part 1:** ≤150-token addition to `skills/getting-started/SKILL.md` describing the build-shaped-work anti-pattern.
- **Part 2:** `hooks/build-routing-advisor.sh` — a warn-only PreToolUse hook on `Task` that emits an ADVISORY when a `general-purpose` subagent dispatch looks build-shaped and no active pipeline marker matches.

The 10-test acceptance suite at `hooks/tests/test-build-routing-advisor.sh` (already RED) is the GREEN contract. All other ACs from the design doc are layered around that core.

## Innovation proposal (#174 T9)

Per the innovate pass, a post-merge reconciler (T9) is appended to convert the advisor from heuristic-unverifiable to empirically-tunable. The reconciler answers a discrete binary question for each merged PR in a window: did the branch write `Status: PASS` to `build-gate-ledger.md`? The conjunction `(merged PR) ∧ (no gate-ledger PASS)` is the exact #174 failure mode — a ground-truth oracle that makes the design's "remove Part 2 if telemetry shows cost > value" clause actionable. T9 is a standalone read-only utility (no cross-system impact) and may land in the same PR as T1–T8 or a follow-up.

## Conventions

- All paths absolute under `/mnt/e/Coding/crucible/`.
- Bash style follows `hooks/gate-ledger-guard.sh`: `set +e`, jq null-safety with `// empty`, graceful `exit 0` on any utility failure, stdin via `INPUT="$(cat)"`.
- `$PROJECT_MEMORY` derivation: `~/.claude/projects/$(echo "$PROJECT_ROOT" | tr '/' '-')/memory/` (Claude Code's native dash-sanitized-path convention — empirically verified). **CRITICAL (S3-R1 supersedes F4):** the previous plan used `echo -n "$(pwd)" | sha256sum | cut -c1-16` matching `hooks/session-index.sh`, but empirical verification showed `/build` writes markers to the dash-sanitized Claude-native path (e.g. `~/.claude/projects/-mnt-e-Coding-crucible/memory/.pipeline-active`). `session-index.sh`'s sha256 derivation writes its OWN session-index artifacts to a DIFFERENT directory — that divergence is pre-existing and unrelated to this ticket. The advisor MUST match the marker-writer's convention, not session-index's. Any code path deriving `$PROJECT_MEMORY` MUST use `tr '/' '-'` against the git-toplevel-resolved `$PROJECT_ROOT`. `PROJECT_ROOT` resolution: `PROJECT_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"` — walks upward to the repo root so cwd drift does not break derivation.
- `docs/plans/` and `hooks/tests/fixtures/` paths are gitignored — every commit in those paths uses `git add -f` (existing branch convention).
- Token budgeting for Part 1 uses `tiktoken` cl100k locally; no CI gate.
- Tests must use `set +e` patterns where the hook's `set +e` matters; capture stderr with `2> "$stderr_file"`.
- **tr lossiness (M1 acknowledgment):** `tr '/' '-'` is a lossy sanitization (Claude Code's convention, not this plan's choice). If two absolute paths would collide post-sanitization (e.g. `/a/b-c` and `/a-b/c` both map to `-a-b-c`), they map to the same memory dir. Not a crucible-specific concern — inherited from Claude Code's path convention.

## Dependency Graph

```
T1 (fixture) ─> T2 (hook impl) ─> T3 (RED → GREEN ack tests) ─> T3.5 (extended AC coverage) ─> T7 (dogfood + perf) ─> T8 (marker-write integration)
     │                │                                                                             ^
     └──────> T6 (README) ─────────────────────────────────────────────────────────────────────── ┘
                    │        │
                    └────────┴───> T9 (post-merge reconciler, standalone)

T4 (SKILL.md Part 1, independent) ─> T5 (routing eval)
```

Edges: T1 → T2; T2 → T3; T3 → T3.5; T3.5 → T7; T7 → T8; T1 → T6; T2 → T6; T6 → T7; T4 → T5; T2 → T9; T6 → T9.

No circular deps. T4 is independent of T2/T3 and can land at any time; T5 gates on T4 only. T7's README perf numbers require T6's structure to exist first (T6 → T7). T9 consumes the state file written by T2 and is documented in the README produced by T6; it does NOT gate T7 or T8 and may defer to a follow-up PR after #174 merges.

### Subagent wave grouping

- **Wave A:** T1, T2, T3 (fixture + hook + RED→GREEN)
- **Wave B:** T4, T5 (SKILL.md Part 1 + routing eval, independent track)
- **Wave C:** T6, T7, T8 (README + dogfood/perf + marker-write integration)
- **Wave D:** T9 (post-merge reconciler, standalone) — optional late-wave task; if time/context is tight, defer to a follow-up PR after #174 merges. Explicitly documented as deferrable.

T3.5 runs between Wave A and Wave C (it extends T3 coverage before dogfood).

---

## Task 1 — Capture PreToolUse fixture + verify env

**Files:** 2 (`hooks/tests/fixtures/agent-pretooluse-sample.json`, scratch capture script — discarded after use)
**Complexity:** Low
**Review-Tier:** 1
**Dependencies:** None

### Goal

Pin the exact JSON shape Claude Code sends to PreToolUse for `Task` (or `Agent`) tool dispatches. This shape determines the jq extraction path used in T2. Also confirm `$CLAUDE_SESSION_ID` is exported into the hook subprocess (per AC S1-R6).

### Steps

1. Create `/mnt/e/Coding/crucible/hooks/tests/fixtures/` if absent.
2. Write a temporary capture hook at `/tmp/capture-pretooluse.sh`:
   ```bash
   #!/usr/bin/env bash
   set +e
   PAYLOAD="$(cat)"
   {
     echo "=== payload ==="
     echo "$PAYLOAD"
     echo "=== env CLAUDE_SESSION_ID ==="
     env | grep CLAUDE_SESSION_ID || echo "(unset)"
   } >> /tmp/pretooluse-capture.log
   exit 0
   ```
3. **Hook registration with EXPLICIT pre-dispatch backup (S4-R4 — no EXIT trap):**
   a. FIRST, copy current settings to a NAMED backup: `cp ~/.claude/settings.json ~/.claude/settings.json.bak-pretooluse-capture`. This backup is the revert source used by explicit step 6.5 below.
   b. **Implementer note — why no trap:** Claude Code's Bash tool resets shell state between invocations. An EXIT trap installed in one Bash tool call fires when THAT invocation's shell exits — typically BEFORE the capture dispatch happens in a separate later invocation. Trap-based auto-revert is therefore unreliable across Bash-tool boundaries. The explicit revert step 6.5 is MANDATORY. If execution aborts before step 6.5 runs, the `~/.claude/settings.json` leak must be manually cleaned up by restoring from the backup; the backup file's existence post-run is an integrity failure signal.
   c. Register the capture hook in **`~/.claude/settings.json`** (user-global, matching the scope of `gate-ledger-guard` per #168 README) under `PreToolUse` with `matcher: "Task"` (NOT null-matcher — this limits blast radius to Task dispatches only; a global null-matcher registration leaked by an unhandled abort would impact every future session's every tool call), invoking `bash /tmp/capture-pretooluse.sh`.
   d. Perform the capture-dispatch sequence (steps 4–6). Revert is performed by EXPLICIT step 6.5 below, not by any trap.
4. In an interactive Claude Code session, dispatch a single `general-purpose` subagent with a **deterministically NON-build-shaped** test prompt. Use exactly `"echo hello to stdout"` — this prompt contains none of the advisor's classification keywords (no `design|spec|plan|implement|code|create|refactor|PR|commit|merge|push|land|ship` matches under `grep -ioE '\b...\b'`), so `TOTAL_DISTINCT = 0` and the advisor's trigger cannot fire regardless of marker state. This determinism is load-bearing for T3.5 case 17(a): that case pipes this fixture to the hook and asserts an EMPTY stderr / unchanged state-file mtime; a build-shaped fixture prompt would defeat the assertion. **Wrap the dispatch in a capture that writes to `/tmp/pretooluse-capture-raw.log`** (the capture hook's destination is parameterized via an env var or a dedicated capture script variant; the hook body writes its payload line-by-line to whichever log path is currently configured). This is the RAW `general-purpose` payload — the authoritative fixture for classification testing.
5. **MANDATORY `/build` dispatch (marker-path verification) — capture FIRST internal payload:** Dispatch `/build` on a scratch branch (a --dry-run style invocation if /build supports it; otherwise use a scratch branch and DO NOT merge/push — implementer SHOULD plan to ABORT the /build run after Phase 1 Step -1 writes the marker: reading the on-disk marker is all we need; we don't need /build to complete). **The ABORT leaks a `.pipeline-active` marker into `$PROJECT_MEMORY` because /build's EXIT-trap cleanup does not run on interrupted runs — step 6.5's explicit `rm -f` handles this per SIG-1-R5; if you skip step 6.5, manually remove the marker before moving on.** Before this dispatch, reconfigure the capture hook to write to `/tmp/pretooluse-capture-build.log`; the capture script writes the FIRST payload it sees and then short-circuits subsequent writes (so the log pins exactly one payload — the first `/build-internal` specialty dispatch). This is an internal specialty payload (e.g. planning, code-reviewer) — useful for verifying the allowlist suppression path. The `/build` dispatch's primary purpose is still marker-write verification (below), but the captured payload is ALSO committed as a secondary fixture. Wait for the marker to appear at the expected path. This step is MANDATORY — do NOT proceed to step 5a/6 without a verified on-disk marker path. Running only `echo hello to stdout` via a raw subagent does NOT exercise `/build`'s marker writer and leaves the path derivation unvalidated.
5a. Inspect BOTH `/tmp/pretooluse-capture-raw.log` AND `/tmp/pretooluse-capture-build.log`. **Verify non-empty payload FIRST (for each):**
   - Assert `[ -s /tmp/pretooluse-capture-raw.log ]` AND `[ -s /tmp/pretooluse-capture-build.log ]` (both size > 0 bytes) AND each log contains the literal string `=== payload ===`.
   - If empty after 2 dispatch attempts, ESCALATE — do NOT proceed to fixture commit with an empty or fabricated payload.
   - If non-empty but the payload JSON lacks any `.tool_input.prompt` OR `.input.prompt` OR `.prompt` field, ESCALATE — the extraction path is fundamentally unknown; do not guess.
   - Also log `git -C "$(pwd)" rev-parse --show-toplevel` output during the real capture dispatch and verify it resolves to the crucible repo root (`/mnt/e/Coding/crucible`). If it does not, the hook's `PROJECT_ROOT` resolution will be wrong at runtime.
   - **Also verify on-disk pipeline-active marker location:** during (or just after) a real `/build` dispatch, assert that `.pipeline-active` exists at `~/.claude/projects/$(echo "$(git rev-parse --show-toplevel)" | tr '/' '-')/memory/.pipeline-active`. If the actual on-disk path uses a DIFFERENT scheme (e.g. sha256 or something novel), the advisor's derivation MUST match whatever `/build` actually writes — update T2's derivation and flag in the fixture header. The `tr '/' '-'` convention is the current empirically verified derivation; future Claude Code versions could change it.

   Identify in the payload:
   - Top-level tool field: `.tool` vs `.tool_name`
   - Prompt path: `.tool_input.prompt` vs `.input.prompt`
   - Subagent type path: `.tool_input.subagent_type` vs equivalent
   - Whether `CLAUDE_SESSION_ID` is set
6. Save BOTH captured JSON objects verbatim:
   - The RAW `general-purpose` payload from `/tmp/pretooluse-capture-raw.log` → `/mnt/e/Coding/crucible/hooks/tests/fixtures/agent-pretooluse-sample.json` (PRIMARY fixture — used for classification testing).
   - The `/build-internal` specialty payload from `/tmp/pretooluse-capture-build.log` → `/mnt/e/Coding/crucible/hooks/tests/fixtures/agent-pretooluse-build-internal-sample.json` (SECONDARY fixture — used for allowlist-suppression coverage in T3.5 case 17).
   Strip any user-private content from both.

   **Size cap check (S1-R2) — performed BEFORE step 6.5 deletes the logs:** verify `[ $(stat -c%s /tmp/pretooluse-capture-raw.log) -le 10485760 ] && [ $(stat -c%s /tmp/pretooluse-capture-build.log) -le 10485760 ]` (≤10MB each). If either log exceeded 10MB, record the size in the fixture header (investigate — the payload should be ≤1MB per dispatch). Logs are then deleted by step 6.5 regardless of success/failure.
6.5. **MANDATORY explicit revert step (finally-style, executed as a distinct step — NOT a trap):**
   ```bash
   # S4-R4 explicit revert (settings + capture logs)
   cp ~/.claude/settings.json.bak-pretooluse-capture ~/.claude/settings.json
   rm -f ~/.claude/settings.json.bak-pretooluse-capture
   rm -f /tmp/pretooluse-capture-raw.log /tmp/pretooluse-capture-build.log

   # SIG-1-R5 cleanup: also remove any leaked .pipeline-active marker from aborted /build.
   # Step 5's /build run is ABORTED after the marker is written (we don't let /build complete),
   # so /build's normal EXIT-trap cleanup does NOT fire. Without this explicit rm, a stale
   # marker leaks into $PROJECT_MEMORY and contaminates (a) T3 / T3.5 test fixtures that
   # assume a clean memory dir, and (b) T7 dogfood's pipeline-dogfood step — a leaked marker
   # would suppress otherwise-correct advisory firings and produce a false-clean result.
   rm -f "$HOME/.claude/projects/$(git rev-parse --show-toplevel | tr '/' '-')/memory/.pipeline-active"
   ```
   This step MUST be executed immediately after the captures at step 6 complete, before any fixture-commit step. If this step is skipped/aborted, the settings.json leak must be manually cleaned up; the named backup file's post-run presence is the integrity failure signal.
7. Document findings in a comment header of EACH fixture file:
   ```
   # Captured 2026-04-14 from Claude Code <version>
   # Fixture role: primary (raw general-purpose) | secondary (build-internal specialty)
   # Tool name field: .tool
   # Prompt path: .tool_input.prompt
   # Subagent type path: .tool_input.subagent_type
   # subagent_type value in this payload: <e.g. general-purpose | planning | code-reviewer>
   # CLAUDE_SESSION_ID exported: yes|no
   # verified on-disk marker path: <absolute path to .pipeline-active observed during T1 step 5 /build dispatch>
   ```
   Both `CLAUDE_SESSION_ID exported:` and `verified on-disk marker path:` fields are MANDATORY in the primary fixture header (the secondary fixture MUST also record the marker path for cross-check — it is the payload captured contemporaneously with the marker write). If either is unknown, record `(not verified)` and ESCALATE — do NOT commit the fixture with unverified fields (T3 step 0 pre-check will reject it).
8. Cleanup + settings-diff guard (post-capture verification):
   - Delete the temporary capture hook file: `rm -f /tmp/capture-pretooluse.sh`. (Settings.json revert and log cleanup were handled by step 6.5.)
   - Assert `[ ! -f ~/.claude/settings.json.bak-pretooluse-capture ]` — the backup file MUST have been deleted by step 6.5. Its continued presence indicates step 6.5 did not complete (integrity failure signal).
   - Diff `~/.claude/settings.json` against a pre-T1 baseline captured before step 3a (implementer captures this baseline as `~/.claude/settings.json.pre-t1-baseline` at T1 start; delete it after the diff passes). If any diff exists, the revert in step 6.5 failed — ESCALATE and do NOT commit.
   - If the backup file still exists: step 6.5 was interrupted. Manually run `cp ~/.claude/settings.json.bak-pretooluse-capture ~/.claude/settings.json && rm ~/.claude/settings.json.bak-pretooluse-capture` to restore, then retry.
   - **Marker-leak invariant (SIG-1-R5):** assert `[ ! -f "$HOME/.claude/projects/$(git rev-parse --show-toplevel | tr '/' '-')/memory/.pipeline-active" ]`. If present, the T1 step 5 ABORT leaked a marker past step 6.5's explicit cleanup — manually remove before proceeding; document why the cleanup didn't fire.
9. Commit fixtures: `git add -f hooks/tests/fixtures/agent-pretooluse-sample.json hooks/tests/fixtures/agent-pretooluse-build-internal-sample.json && git commit -m "test(hooks): pin PreToolUse Task fixtures (raw + build-internal) for #174"`.

### Acceptance

- BOTH fixture files exist and parse as JSON:
  - `hooks/tests/fixtures/agent-pretooluse-sample.json` — raw `general-purpose` payload (primary).
  - `hooks/tests/fixtures/agent-pretooluse-build-internal-sample.json` — `/build-internal` specialty payload (secondary; for allowlist-suppression coverage).
- The on-disk `.pipeline-active` verification at step 5a is MANDATORY — an implementer MUST run a real `/build` dispatch (step 5, not `echo hello to stdout`) to confirm the marker's actual on-disk path before committing the fixtures.
- BOTH capture logs were verified non-empty (size > 0, contains `=== payload ===`); one of `.tool_input.prompt` / `.input.prompt` / `.prompt` is present in each. Otherwise ESCALATED (no fabricated fixture committed).
- The secondary fixture's `.tool_input.subagent_type` is NOT `general-purpose` (if it is, recapture — the build-internal specialty branch of T3.5 case 17 would be meaningless with a raw payload).
- Each fixture header records its role (primary/secondary), the canonical extraction path, the `subagent_type` value observed, AND the `$CLAUDE_SESSION_ID` availability finding.
- Each fixture header records the verified on-disk `.pipeline-active` path during a real `/build` dispatch and confirms it matches `~/.claude/projects/$(echo "$(git rev-parse --show-toplevel)" | tr '/' '-')/memory/.pipeline-active`. Any divergence is flagged and resolved before T2 begins.
- If `$CLAUDE_SESSION_ID` is **not** exported, T2's design changes per AC S1-R6 (note in T2 step list).
- Capture logs verified ≤10MB each before deletion (via `stat -c%s` in step 6 pre-revert); explicit revert step 6.5 confirmed to have deleted both logs and the named backup file `~/.claude/settings.json.bak-pretooluse-capture`.
- **Post-capture settings invariant (S4-R4):** after step 6.5, `diff ~/.claude/settings.json ~/.claude/settings.json.pre-t1-baseline` is empty AND `[ ! -f ~/.claude/settings.json.bak-pretooluse-capture ]`. If any diff exists OR the backup file persists, the revert failed; ESCALATE and do NOT commit.
- **Post-capture marker invariant (SIG-1-R5):** `.pipeline-active` does NOT exist at the project-memory path after step 6.5. Verify via `[ ! -f "$HOME/.claude/projects/$(git rev-parse --show-toplevel | tr '/' '-')/memory/.pipeline-active" ]`. If present, the T1 abort leaked a marker — manually remove before proceeding.

---

## Task 2 — Implement `hooks/build-routing-advisor.sh`

**Files:** 1 (`hooks/build-routing-advisor.sh`)
**Complexity:** High
**Review-Tier:** 3
**Dependencies:** Task 1

### Goal

Implement the full advisor flow per design Part 2. Single bash script; no helper modules. Mirrors `gate-ledger-guard.sh` style.

### Execution-order overview (MIN-3 lazy derivation)

To keep the non-trigger hot path as cheap as possible, `$PROJECT_ROOT` / `$PROJECT_MEMORY` are derived LAZILY — only after classification has confirmed the dispatch is build-shaped. The canonical ordering is:

1. `set +e`; read stdin into `INPUT`; exit 0 on empty.
2. **Kill-switch env-var check** (no `$PROJECT_ROOT` needed): if `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1`, perform the S4-R2 short-circuit / RMW flow. The env-var branch derives `$PROJECT_ROOT` / `$PROJECT_MEMORY` internally (to locate the state file) — that derivation is scoped to the kill-switch branch only.
3. `command -v jq` dependency check.
4. Tool-name, prompt, subagent-type extraction; allowlist gate; disclaimer skip.
5. **Classification** (grep-only on `$PROMPT`; no git subprocess).
6. **Early exit if trigger does not fire.**
7. **ONLY NOW** derive `PROJECT_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"` and `PROJECT_MEMORY="$HOME/.claude/projects/$(echo "$PROJECT_ROOT" | tr '/' '-')/memory"`.
8. Sentinel-file kill-switch branch (needs `$PROJECT_MEMORY`).
9. Pipeline-active marker check.
10. Dedup check + lazy `fires-today` reset.
11. Emit advisory (stderr, 2 lines).
12. Atomic state-file update.
13. `exit 0`.

The numbered list below (`Required behavior (in execution order)`) describes the DETAILS of each branch. Where the detailed text still references `$PROJECT_MEMORY` BEFORE step 7 above, that is scoped to the kill-switch env-var branch only — the non-kill-switch hot path must NOT touch `$PROJECT_ROOT` until classification fires.

### Required behavior (in execution order)

0. **Matcher registration (prerequisite, verified by T2 step list):** register `build-routing-advisor` in **`~/.claude/settings.json` (user-global scope, identical to `gate-ledger-guard` per #168 README)** under `PreToolUse` with `matcher: "Task"` (primary; fallback `Agent` per T1 finding) and `timeout: 500` (ms). Verify the entry does NOT conflict with `gate-ledger-guard`'s null-matcher registration — the two entries coexist as separate hooks, one null-matcher (gate-ledger-guard) and one `Task`-matcher (build-routing-advisor).
1. `set +e`. Read stdin into `INPUT`. Exit 0 on empty stdin.
2. **Step 1a — Compute `$PROJECT_ROOT` then `$PROJECT_MEMORY` FIRST** (before kill-switch block below, so the switch can reference `$PROJECT_MEMORY` without ambiguity):
   - `PROJECT_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"` — walks upward via git-toplevel so cwd drift between dispatches does not break derivation. If not inside a git repo, falls back to `pwd` (advisor will then see no marker and fire if classification triggers — correct behavior for raw dispatches outside any repo).
   - `PROJECT_DIR_SAFE="$(echo "$PROJECT_ROOT" | tr '/' '-')"` then `PROJECT_MEMORY="$HOME/.claude/projects/$PROJECT_DIR_SAFE/memory"`.
   - **Rationale (S3-R1 supersedes F4):** the previous plan used sha256(pwd) matching `hooks/session-index.sh:38-39`, but empirical verification showed `/build` writes `.pipeline-active` to the dash-sanitized Claude-native path (e.g. `~/.claude/projects/-mnt-e-Coding-crucible/memory/.pipeline-active`). `session-index.sh` writes its own session-index artifacts to a DIFFERENT directory under a sha256 hash — a pre-existing divergence unrelated to this ticket. The advisor MUST match the MARKER-WRITER's convention (`tr '/' '-'`), not session-index's. The echo-n-vs-echo trailing-newline concern (F4) is moot under this derivation; F4 is historical.

   **Kill switch** (runs after `$PROJECT_MEMORY` is computed):
   - If `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` → **write-elision short-circuit (S4-R2):** if the state file already records today's date as `last-honored`, exit 0 WITHOUT rewriting the file:
     ```bash
     STATE_FILE="$PROJECT_MEMORY/build-routing-advisor-state.md"
     grep -q "^last-honored: $(date +%Y-%m-%d)$" "$STATE_FILE" 2>/dev/null && exit 0
     ```
     Otherwise, perform an explicit read-modify-write to update `last-honored` while PRESERVING dedup fields and counters per Min-1-R6. RMW preserves dedup fields across kill-switch toggles per Min-1-R6. Short-circuit elision (S4-R2) skips this block when `last-honored` already equals today's date.

     **IMPORTANT (S2-R4): state file content must be column-0 anchored — no leading whitespace.** If you copy this block from the markdown, STRIP any leading indentation before pasting into the hook source. Alternatively use `<<-EOF` with TAB-only indentation (POSIX `<<-` strips leading TABS only — NOT spaces). The `grep '^field:'` read path relies on column-0 anchoring; an indented heredoc body produces indented state-file lines and subsequent reads silently return empty, silently corrupting dedup/counter preservation.

     The following heredoc is shown at column 0 — DO NOT re-indent when pasting into the hook source:

```bash
# Read existing values (default to empty/0 if absent)
FIRES_TODAY="$(grep '^fires-today:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 || echo 0)"
FIRES_TOTAL="$(grep '^fires-total:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 || echo 0)"
LAST_ADV_AT="$(grep '^last-advisory-at:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2- || echo '')"
LAST_ADV_FP="$(grep '^last-advisory-fingerprint:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 || echo '')"

# Construct full 5-line block; write via tmp+mv per step 13 atomic-write pattern
mkdir -p "$PROJECT_MEMORY"
cat > "$STATE_FILE.tmp" <<EOF
last-honored: $(date +%Y-%m-%d)
fires-today: $FIRES_TODAY
fires-total: $FIRES_TOTAL
last-advisory-at: $LAST_ADV_AT
last-advisory-fingerprint: $LAST_ADV_FP
EOF
mv "$STATE_FILE.tmp" "$STATE_FILE"

# Self-check (S2-R4): assert column-0 anchoring — if the heredoc body was accidentally
# indented (common footgun), the first line will not match. 2P-3-R5: do NOT destroy the
# state file on regression — preserve it for forensics. The advisor is warn-only and the
# worst case is a single run with skewed dedup telemetry; deleting the file would wipe
# all prior fires-total / last-advisory-fingerprint history (irreversible) on a heredoc
# regression that is almost certainly a code change on the hook side, not a user action.
grep -q '^last-honored: ' "$STATE_FILE" || {
  echo "advisor: state-file column-0 invariant broken; preserving for forensics" >&2
  exit 0
}
exit 0
```
     **Rationale:** kill-switch is honored ~50–90× per `/build` run; without the elision above the state file is rewritten on every honored invocation causing no-op write amplification. `last-honored` has DATE granularity only — within the same day, repeated kill-switch invocations are no-op short-circuits (this is intentional for perf). The explicit RMW is ONLY executed on the first kill-switch invocation of each new day; naive `echo > $STATE_FILE` would wipe dedup state on that first invocation and silently break Min-1-R6.
   - If sentinel `$PROJECT_MEMORY/.build-routing-advisor-disabled` exists:
     - **Matching-line definition (MIN-3-R7):** a matching line is one beginning with `disabled-until:` at column 0 — no leading whitespace, no comment skipping. Use literal regex `^disabled-until: ` (trailing space required).
     - Parse FIRST matching line. If the file contains multiple matching lines, use only the FIRST; ignore the rest.
     - If date parses AND today's local date < parsed date → honor switch, update `last-honored`, exit 0.
     - If date parses AND today >= parsed date → switch expired (auto-expiry path), continue with advisor flow.
     - If date does NOT parse → write `disabled-until-parse-error: <raw>` to state, honor switch (PERMANENTLY DISABLED fail-safe per malformed `disabled-until`), exit 0.
     - If sentinel exists with no `disabled-until:` line → honor switch indefinitely, update `last-honored`, exit 0.
3. **Dependency check:** `command -v jq` — if missing, exit 0 silently.
4. **Tool name extraction:** `TOOL=$(echo "$INPUT" | jq -r '.tool // .tool_name // empty')`. If `TOOL` not in `Task|Agent`, exit 0.
5. **Prompt + subagent extraction:** use the canonical path discovered in T1. Try `.tool_input.prompt` first, then `.input.prompt`. Same for `subagent_type`. If both null, exit 0 (malformed JSON path covered).
6. **Allowlist:** if `subagent_type` is set AND not equal to `general-purpose`, exit 0. Implementer note: an empty-string `subagent_type` is treated as SPECIALTY (not `general-purpose`) and the advisor suppresses — rationale: a missing/empty type is indistinguishable from MCP types in the allowlist contract.
7. **Disclaimer skip:** case-insensitive grep for any of `just the design`, `design only`, `no implementation`, `review only`, `audit only`, `spec only`, `recon only`. If matched, exit 0.
8. **Classification (BEFORE any git subprocess; Min-7).** Use EXACTLY ONE method — pinned (no alternatives):
   - `DESIGN_HITS=$(echo "$PROMPT" | grep -ioE '\b(design|spec|plan)\b' | wc -l)`
   - `IMPLEMENT_HITS=$(echo "$PROMPT" | grep -ioE '\b(implement|code|create|refactor)\b' | wc -l)`
   - `SHIP_HITS=$(echo "$PROMPT" | grep -ioE '\b(PR|commit|merge|push|land|ship)\b' | wc -l)`
   - `TOTAL_DISTINCT=$(echo "$PROMPT" | grep -ioE '\b(design|spec|plan|implement|code|create|refactor|PR|commit|merge|push|land|ship)\b' | tr '[:upper:]' '[:lower:]' | sort -u | wc -l)`
   - **Trigger condition:** `IMPLEMENT_HITS >= 1` AND (`DESIGN_HITS >= 1` OR `SHIP_HITS >= 1`) AND `TOTAL_DISTINCT >= 2`.
   - Worked example (comment in source): `# "spec + implement + PR" → DESIGN=1, IMPLEMENT=1, SHIP=1, TOTAL_DISTINCT=3 → fires`.
   - **TOTAL_DISTINCT soundness note (M5, inline comment in hook source):** `# TOTAL_DISTINCT uses 'tr [:upper:] [:lower:] | sort -u | wc -l' to count DISTINCT lowercased hits across all three categories. The review confirmed 'sort -u' is sound for this purpose (dedup is per-line and category words are single-token, so no subword overlap risk). Do not replace with per-category wc -l addition — that would double-count words that appear in multiple categories, which none currently do, but the sort -u form is future-proof.`
   - If trigger does not fire, exit 0.
9. **Pipeline-active marker check** (only reached if trigger fires):
   - `MARKER="$PROJECT_MEMORY/.pipeline-active"`. If absent → marker not active.
   - Parse with jq. Require `.skill` present and in `{build, spec, debugging, migrate}`.
   - **`.start_time` format pin:** per `skills/build/SKILL.md:468`, the marker writes `start_time` as ISO-8601 via `date -u +%Y-%m-%dT%H:%M:%S`. Parse via `START_EPOCH=$(date -d "$START_TIME" +%s 2>/dev/null)`. If parse fails (empty/non-zero exit), treat marker as STALE → marker not active → advisory still emits (do not silently honor a marker with an unparseable timestamp).
   - Require parsed `.start_time` within 24h of `date -u +%s`.
   - Read current branch: `CUR_BRANCH=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null)`. (Uses `$PROJECT_ROOT` — the git-toplevel-resolved root from step 1a — not raw `$(pwd)`, which could drift.)
   - **Branch comparison (explicit branches — no accidental-correctness via `"" == ""`):**
     - If BOTH `.branch` and `$CUR_BRANCH` are non-empty AND equal → active (proceed to 24h + skill checks above).
     - Else if BOTH are empty AND `.pipeline_id == $CLAUDE_SESSION_ID` → active (detached-HEAD symmetric fallback).
     - Otherwise (asymmetric empty, or non-empty mismatch) → NOT active.
   - If marker is active, exit 0.
10. **Dedup check (Min-9):**
    - Read state file `$PROJECT_MEMORY/build-routing-advisor-state.md`.
    - Compute fingerprint: `echo "$PROMPT" | sha256sum | cut -c1-16`. **Fingerprint truncation to 64 bits (16 hex chars) matches the `session-index.sh` convention (M3-R4).** Collision probability is negligible at expected prompt volumes (birthday bound ~4 billion distinct prompts before ~50% collision — the advisor observes at most ~1000s of distinct prompts per project lifetime).
    - If `last-advisory-fingerprint` matches AND `last-advisory-at` is within 5 minutes → suppressed: increment `fires-total` only, do NOT emit, write state atomically, exit 0.
    - **Fingerprint identity (SP1):** fingerprint is SHA256 of the FULL prompt text. Near-identical prompts (differing by scout index, timestamp, or single character) produce DIFFERENT fingerprints → both fire. This is an ACCEPTED LIMITATION — the advisor is warn-only, and false duplicates are preferable to false suppressions (which would silently hide the #174 failure mode). Do not introduce fuzzy matching; the SP2 5-min dedup window concern about silencing a second build-shaped dispatch is subsumed by this — different-prompt second dispatches are expected to fire again.
11. **Lazy `fires-today` reset (Min-3-R6):** reset is LAZY — performed ONLY on advisory-eligible invocation (this step is reached only after trigger fires, marker not active, dedup not suppressed), never continuously. On each eligible invocation, compare today's local date against the MOST RECENT of (`last-honored` date, `last-advisory-at` date). If neither exists OR the most recent is older than today → reset `fires-today` to 0 BEFORE incrementing in step 13.
12. **Emit advisory** to stderr (exactly 2 lines, includes literal `build-shaped`):
    ```
    ADVISORY: Dispatch looks build-shaped. If single-phase, ignore.
    Else prefer /build (or /spec then /build) for gate coverage.
    ```
13. **State file update (atomic write):**
    - **First line of this step:** `mkdir -p "$PROJECT_MEMORY"` (ensures parent exists before any tmp-file write).
    - Increment `fires-today` and `fires-total`.
    - Set `last-advisory-at: <ISO-8601 UTC>`.
    - Set `last-advisory-fingerprint: <hash>`.
    - Write to `$PROJECT_MEMORY/build-routing-advisor-state.md.tmp` then `mv` into place.
    - Schema (≤5 required lines, plus 1 optional schema-version line):
      ```
      last-honored: YYYY-MM-DD
      fires-today: N
      fires-total: N
      last-advisory-at: <ISO-8601 or empty>
      last-advisory-fingerprint: <hash or empty>
      schema-version: 1          # OPTIONAL 6th line; reserved for future breaking-schema changes
      ```
    - **Schema versioning (MIN-6):** the optional 6th line `schema-version: 1` is ignored by the current hook. The hook accepts files with OR without this line. Future schema changes MAY bump the version and use it to detect incompatible fields. The T3.5 case 15 "state-file bounded growth ≤5 lines" check is relaxed to ≤6 lines to accommodate the optional schema-version line when present.
    - **Atomic-write race note (MIN-4-R7):** per-process atomicity is via temp-file + `mv`; cross-process is last-writer-wins. ±1 counter races and fingerprint flicker across concurrent processes are ACCEPTED. Do NOT add `flock` or any file locking. The state file is advisory telemetry, not a correctness-critical ledger.
14. `exit 0`.

### Implementation notes

- All `git`, `jq`, `sha256sum`, `date` failures → exit 0 silently. Never fatal.
- **`mkdir -p` placement (explicit):** the FIRST line of step 13 is `mkdir -p "$PROJECT_MEMORY"`. Do NOT place it elsewhere; do NOT rely on this note alone — the prologue belongs in the step body.
- If T1 found `$CLAUDE_SESSION_ID` is NOT exported, replace step 9's detached-HEAD fallback with a `.start_time`-within-**5-minute** session-proxy check (not 60 seconds — avoids the brief-gap false positive noted in SP1). 5-minute window is a pragmatic compromise between stale-marker safety (covered by the 24h upper bound and S3 branch/pipeline_id checks) and legitimate-gap tolerance across consecutive dispatches. Document the reduction in T6. **M9-R4 assumption (documented):** the 5-minute `.start_time`-based session-proxy fallback ASSUMES consecutive dispatches within a pipeline occur within 5 minutes of the marker write. Long Phase 3 execution (e.g. lengthy subagent runs) MAY exceed this window, in which case legitimate pipeline dispatches beyond the 5-minute mark will be misclassified as NOT ACTIVE and the advisor will emit false-positive advisories. This edge case is ACCEPTED — the advisor is warn-only, and the alternative (unbounded session-proxy) would defeat the stale-marker safety property.
- **Worktree state sharing (SP3):** the advisor state file lives in `$PROJECT_MEMORY/` which is shared across worktrees of the same repo (all worktrees resolve to the same `$PROJECT_ROOT` via git-toplevel). Dedup fingerprints will consequently be shared across concurrent worktree sessions. This is ACCEPTABLE: the advisor is warn-only and the shared fingerprint just coalesces duplicate advisories (not a correctness issue). Worktree-specific dedup would require per-worktree state files — out of scope.
- Performance: classification uses one `grep -ioE` per category against `<<< "$PROMPT"` — no temp files. Target ≤50ms per invocation.

### Acceptance

- File created at `/mnt/e/Coding/crucible/hooks/build-routing-advisor.sh`.
- `chmod +x` applied.
- Manual `bash hooks/build-routing-advisor.sh < hooks/tests/fixtures/agent-pretooluse-sample.json` exits 0 cleanly.
- `bash -n` parses without syntax errors.

---

## Task 3 — Drive acceptance tests RED → GREEN

**Files:** 0–1 (only the hook from T2, possibly minor fixes; no changes to test file)
**Complexity:** Medium
**Review-Tier:** 2
**Dependencies:** Task 2

### Goal

`bash hooks/tests/test-build-routing-advisor.sh` reports `Results: 10/10 passed` and exits 0.

**Critical boundary:** the test file at `hooks/tests/test-build-routing-advisor.sh` is pre-existing (RED canary committed 1450ed3). T3's job is to make the HOOK pass the tests, NOT to modify the tests. **Tests are the spec.** If a test appears wrong, ESCALATE to the user rather than modifying it.

**Pre-authorized exception (S3-R1 correctness fix — supersedes F4):** the test harness currently derives `PROJECT_HASH` via `sha256sum` (either with or without `echo -n`). S3-R1 supersedes the earlier F4 `echo` vs `echo -n` fix entirely: the sha256 derivation is WRONG regardless of echo variant. `/build` writes `.pipeline-active` to Claude Code's native dash-sanitized path (`~/.claude/projects/-mnt-e-Coding-crucible/memory/.pipeline-active`), not any sha256-hashed path. T3 MUST update the harness to use `PROJECT_HASH="$(echo "$FAKE_PROJECT" | tr '/' '-')"` (note: `tr`, NOT `sha256sum`; the variable name is retained for readability but the value is now a dash-sanitized path segment, not a hash). Update the adjacent comment to state: "Match Claude Code's native marker-writer convention: tr '/' '-' on the absolute path. (Previous sha256 derivation was incorrect — see S3-R1.) The echo-n-vs-echo concern (historical F4) is moot under the tr derivation." Also delete any unused overwritten `printf`/`echo` assignments. This is the ONLY pre-authorized test edit in T3; all other test concerns still ESCALATE.

**S2-R2 pre-authorized exception (third-derivation case):** If T1's on-disk `.pipeline-active` verification finds a derivation OTHER than `tr '/' '-'` (e.g. a future Claude Code version changes the convention — sha256 returns, or some new scheme appears), the implementer IS authorized to update the derivation consistently across: the hook source (T2), the T3 test harness, T3.5 case 16 (PROJECT_HASH canary), and T6 README — in a SINGLE ATOMIC COMMIT. The new canonical derivation is recorded in the fixture header (T1 step 7) and in a note appended to the plan's Conventions section. Any OTHER test modifications still require escalation. This exception exists because the derivation is empirically load-bearing and a version-drift discovery during T1 must not stall the whole plan; it is narrowly scoped to the derivation change alone.

### Steps

0. **T3 fixture pre-check (mandatory before test run):** Before running the test harness, T3 verifies the fixture header at `hooks/tests/fixtures/agent-pretooluse-sample.json` records `CLAUDE_SESSION_ID exported: yes|no` AND `verified on-disk marker path: <path>`. If either field is missing OR set to `(not verified)`, ESCALATE — T1 was not completed correctly (the mandatory `/build` dispatch at T1 step 5 was skipped); do NOT attempt to make tests GREEN on an unvalidated fixture.
1. Run `bash /mnt/e/Coding/crucible/hooks/tests/test-build-routing-advisor.sh`.
2. For each failing test:
   - Read the test's setup, prompt, and expected behavior.
   - Trace the hook flow against the inputs.
   - Fix the **hook** (never the test — tests are spec).
3. Common likely failures and fixes:
   - **Test 1 (motivating canary):** classification regex must catch `spec`, `implement`, `PR` with word boundaries; total distinct = 3 ≥ 2 satisfies trigger.
   - **Test 3 (marker suppression):** marker path uses fake `$HOME` per test harness. Hook must derive `$PROJECT_MEMORY` from `echo "$PROJECT_ROOT" | tr '/' '-'` (Claude Code's native dash-sanitized-path convention — matches `/build`'s actual marker-writer location) — test harness must also use the `tr '/' '-'` derivation (see pre-authorized exception above).
   - **Test 5 (stale marker):** ensure `start_time` 24h check uses `date -d` parsing or epoch math; `48 hours ago` must NOT suppress.
   - **Test 6 (different branch):** `.branch != $CUR_BRANCH` → not active. Verify `git -C "$(pwd)" branch --show-current` against `test-branch` value from the fake repo.
   - **Test 7 (disclaimer):** "design only" must hit the disclaimer regex BEFORE classification.
   - **Test 9 (kill switch env):** kill switch must run BEFORE jq dependency check (env var check needs no utilities) — actually order is: read stdin, check env var, then jq.
   - **Test 10 (malformed JSON):** jq returning empty `.tool` → exit 0 cleanly.
4. After all 10 pass, commit hook + fixture: `git commit -am "feat(hooks): build-routing-advisor (#174)"`.

### Acceptance

- `Results: 10/10 passed` printed.
- Test script exit code 0.
- Hook diff committed.
- **T3 is NOT considered complete** until T3.5's extended-coverage cases also pass (see below).

---

## Task 3.5 — Extended AC coverage (close 10-case vs ~25+ design-AC gap)

**Files:** 1 (`hooks/tests/test-build-routing-advisor.sh` — APPEND cases; do NOT create a new test file)
**Complexity:** Medium
**Review-Tier:** 2
**Dependencies:** Task 3

### Goal

Reconcile the 10-case RED canary against the ~25+ design-enumerated ACs. Decision: **APPEND extended cases to `hooks/tests/test-build-routing-advisor.sh`** so the plan does not rely on dogfood + manual for AC classes that are cheaply automatable. The original 10 cases remain the authoritative GREEN contract; T3.5 cases are added to the SAME file. The test runner stays single-file. **Do NOT create `test-build-routing-advisor-extended.sh`** — earlier draft language allowing that is rescinded.

### Required additional cases (each appended to the existing single-file harness)

1. **Dedup-across-parallel-scouts (Min-9):** two near-simultaneous invocations with identical prompt → assert 1 OR 2 advisories (±1 race tolerance per Min-4-R7) emitted across both captures; `last-advisory-fingerprint` matches the prompt hash. Parallel invocation deduplication is best-effort under last-writer-wins; both advisories firing is acceptable.
   - **Race tolerance (per Min-4-R7):** under parallel invocation, the second invocation MAY observe the first's `last-advisory-fingerprint` and suppress, but if the two invocations interleave between the read and the atomic `mv` both may emit. The test ACCEPTS advisory-count ∈ {1, 2} and `fires-total ∈ {1, 2}`. Neither an exact-1 nor exact-2 assertion is a correctness requirement — the advisor is warn-only and best-effort deduplication is the contract. Do NOT add locking to tighten this; it would violate Min-4-R7.
2. **Kill-switch auto-expiry:** sentinel with `disabled-until: <yesterday>` → advisor proceeds normally (trigger fires if classification matches); state records expiry path.
3. **Malformed `disabled-until` fail-safe:** sentinel with `disabled-until: not-a-date` → PERMANENTLY DISABLED; stderr empty; state records `disabled-until-parse-error`.
4. **Multiple `disabled-until:` lines:** sentinel with two `disabled-until:` lines (first = future, second = past) → FIRST wins; advisor honored.
5. **Asymmetric detached-HEAD:** marker `.branch` empty, current branch `feat/x` (or vice versa) → NOT active; advisory fires.
6. **Branch-switch-mid-pipeline:** marker written on branch A; test runs with current branch B → NOT active; advisory fires.
7. **Substring decoys (negative cases):** prompts containing `planning`, `commitment`, `shipping`, `codebase` as substrings (not whole-word matches) → classification does NOT fire on these alone; verify word-boundary regex correctness. One test case per decoy (4 cases) or a single combined case asserting all four do not trigger.
8. **`subagent_type` non-allowlist cases (all four):** separate cases for `code-reviewer`, `researcher`, arbitrary `custom-agent`, and `""` (empty string) → all exit 0 without emission. (The existing 10-case suite covers `general-purpose`; this extends to the other branches of the allowlist gate.)
9. **Missing-hook-script graceful path:** rename the hook temporarily and invoke via the registered matcher in a sandboxed settings.json → Claude Code does not hard-fail; document Claude Code's observed behavior.
   - **Drop criterion (explicit):** if this case cannot be implemented in <30 lines of bash without modifying Claude Code's hook dispatcher, DROP from T3.5 and move to T7 dogfood as a documented manual verification step. Do not allow this case to balloon the harness.
10. **Perf P95 (informational precursor to T7) — M2-R4 threshold alignment:** run 20 back-to-back advisor invocations against the fixture, capture wall-clock via `time`, assert **P95 ≤200ms measured via method (a)** (matches the combined T7 budget; advisor-alone is informational, not a hard gate here). **Flake tolerance (MIN-5-R5 collapsed):** accept the case if **P95 <250ms** — bash-startup noise on slow CI runners (~10–20ms) is absorbed by this envelope. The previous dual-gate `P90 ≤150ms AND P95 <250ms` is collapsed to a single `P95 <250ms` check: P90 is redundant given P95 (a run that blows P90 but stays under P95 is already absorbed by the envelope the P95 number describes, and dual-gating produces redundant failure modes without catching any new signal). The previous 100ms advisor-alone threshold is rescinded because (i) it duplicated a stricter gate already enforced in T7 method (a), and (ii) under bash-startup cost it produced spurious flakes on slow runners. Uses external timing per revision #12.
11. **Stderr `2>&1` capture assertion (programmatic):** explicit case asserting that the advisor's ADVISORY string is captured via `2>&1` (or equivalent stderr-to-file redirection) in the test harness and matched via `grep -F "ADVISORY:"`. No manual inspection — the assertion is `grep -Fq "ADVISORY:" "$captured"` against the redirected output.
12. **Matcher-neither-Task-nor-Agent fallback:** verify behavior when neither matcher name is correct — the hook falls back to `jq -r '.tool'` (or `.tool_name`) grep on stdin; if that ALSO fails (returns null/empty), the hook exits 0 silently with no stderr. Test asserts: exit code 0, empty stderr, no state-file mutation.
13. **Kill-switch toggle preserves dedup fields:** sequence — (a) emit an advisory (fingerprint + timestamp recorded in state); (b) set kill switch (env var or sentinel); (c) invoke hook → honored, dedup fields preserved per Min-1-R6; (d) remove kill switch; (e) re-trigger within 5-min dedup window with the same prompt → second trigger MUST be deduped (fingerprint preserved across the toggle, no second advisory emitted).
14. **Literal `build-shaped` regression guard:** trivial assertion that the advisory stderr contains the exact literal token `build-shaped` (`grep -Fq "build-shaped"`). Catches future copy edits that might drop or rename the token (the tests grep for it; the README documents it; the dogfood scripts grep for it). **Two-line assertion (M5):** same case also asserts the ADVISORY stderr is EXACTLY 2 lines: `[ "$(grep -c '^' "$stderr_file")" -eq 2 ]`. Catches future copy bloat (multi-line advisories cost context budget across every dispatch and break the 200ms budget accounting).
15. **State-file bounded growth ≤6 lines:** run a sequence of (advisory emit + kill-switch set + sentinel with `disabled-until` expiry + reset/eligible re-fire), then assert `[ "$(wc -l < $STATE_FILE)" -le 6 ]`. Schema must remain ≤5 required lines plus an optional 6th `schema-version:` line (MIN-6) across all state transitions; this catches accidental appends/duplicate-key bloat.
16. **PROJECT_HASH derivation canary (S3-R1; supersedes F4):** fixture writes a valid pipeline-active marker at `$HOME/.claude/projects/<tr-sanitized path>/memory/.pipeline-active` (computed with `echo "$PROJECT_ROOT" | tr '/' '-'` where `PROJECT_ROOT` is the fake project path under the harness's fake `$HOME`). Pipe a build-shaped prompt to the hook; assert the hook FINDS the marker and suppresses (exit 0, empty stderr). If the hook were to use ANY sha256-based derivation (either `echo` or `echo -n` variant), or any other scheme, it would look in a DIFFERENT directory, miss the marker, and emit an advisory — this test fails. Fail message must mention "PROJECT_HASH derivation mismatch: hook must look at `~/.claude/projects/$(echo $PROJECT_ROOT | tr '/' '-')/memory/.pipeline-active`" to make the diagnosis obvious. (Historical note: earlier drafts named this the "trailing-newline canary" / "F4 canary"; S3-R1 rescopes it to the tr derivation.)
17. **Real-fixture pass-through (TWO payloads — primary + secondary):**
    - (a) **Primary (raw general-purpose, non-build-shaped) — deterministic assertion.** Pipe `hooks/tests/fixtures/agent-pretooluse-sample.json` to the hook:
      `bash hooks/build-routing-advisor.sh < hooks/tests/fixtures/agent-pretooluse-sample.json`.
      Expected: (1) exit 0; (2) stderr is EMPTY (no `ADVISORY:` string); (3) state-file mtime UNCHANGED (capture `stat -c%Y "$STATE_FILE"` before and after; if the state file does not exist both before and after, that also passes the "unchanged" assertion).
      Rationale: per T1 step 4, the primary fixture's captured prompt is the deterministically NON-build-shaped string `"echo hello to stdout"` (TOTAL_DISTINCT = 0 under the advisor's trigger regex). Because `subagent_type=general-purpose` the allowlist gate does NOT short-circuit — the full pipeline runs through classification and early-exits at step 6 (trigger does not fire) without emitting an advisory and without writing state. Both the full-pipeline path and the no-emission / no-write outcome are simultaneously verified by this single case.
      **Note:** a `CRUCIBLE_ADVISOR_DEBUG` flag was considered in review as an alternative way to observe classifier execution on a build-shaped fixture; it was REJECTED as scope creep. The deterministic non-build-shaped fixture design above suffices — classifier execution is proven by the (allowlist pass-through) ∧ (no emission) ∧ (no state write) conjunction, which is only possible if classification ran and early-exited at step 6.
    - (b) **Secondary (build-internal specialty):** `bash hooks/build-routing-advisor.sh < hooks/tests/fixtures/agent-pretooluse-build-internal-sample.json` — hook exits 0; since `subagent_type` is a specialty type (e.g. `planning`, `code-reviewer`), the allowlist EARLY-EXITS. Assert: stderr is empty (no ADVISORY), and the state file is NOT mutated (compare mtime before/after). This verifies the allowlist suppression path works with a REAL payload captured contemporaneously with a real `/build` dispatch, not a synthetic fake.
    Both sub-cases are required. Early draft language using only the primary fixture is rescinded — a raw-only pass-through would trivially pass on the allowlist path and provide no real coverage.
18. **Trigger-classification (a) Implement+Design, density=2:** prompt `"implement refactor of design"` → Implement=2 distinct (implement, refactor), Design=1, Ship=0, TOTAL_DISTINCT ≥2 → advisory emits. Comment cites Trigger-Classification rule "Implement≥1 AND (Design≥1 OR Ship≥1) AND total-distinct≥2".
19. **Trigger-classification (b) Implement+Design+Ship (all three):** prompt `"design, implement, and commit"` → all three categories =1, TOTAL_DISTINCT=3 → advisory emits.
20. **Trigger-classification (c) Design+Ship, no Implement:** prompt `"design doc + merge PR"` → Design=1, Ship=2, Implement=0 → NO advisory (Implement-required rule).
21. **Trigger-classification (d) Only-Implement, multiple distinct:** prompt `"implement and code and refactor"` → Implement=3, Design=0, Ship=0 → NO advisory (single-category-only fails; Design≥1 OR Ship≥1 required).
22. **Trigger-classification (e) Implement+Ship, Implement=1 Ship=2:** prompt `"implement X and commit, push"` → Implement=1, Ship=2 distinct → advisory emits.
23. **Kill-switch same-day skip-write (S4-R2):** set `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1`. (a) First invocation: state file absent or stale → advisor honors switch, writes `last-honored: <today>`, exits 0; capture the state file's mtime as `MTIME1`. (b) Sleep 1 second. (c) Second invocation (same day): advisor must short-circuit WITHOUT writing — assert `stat -c%Y $STATE_FILE` equals `MTIME1` (mtime unchanged). (d) Exit code 0 both times; no stderr from either. Fail message must mention "write-elision short-circuit on same-day kill-switch — expected no state-file write, got mtime change".
24. **State-file column-0 invariant (S2-R4):** after ANY write path that mutates the state file (kill-switch RMW, advisory emit, dedup suppression counter bump), assert `head -1 "$STATE_FILE" | grep -q '^last-honored: '` — the first line MUST begin at column 0 with the `last-honored:` key (no leading whitespace). Also assert each of the other required keys (`fires-today:`, `fires-total:`, `last-advisory-at:`, `last-advisory-fingerprint:`) appears at column 0 somewhere in the file via `grep -q '^<key>: ' "$STATE_FILE"`. This guards against the heredoc-indentation footgun: an indented heredoc body produces indented state-file lines and subsequent `grep '^field:'` reads silently return empty. If any assertion fails, the test fails with message "state file lines not column-0 anchored — heredoc indentation regression; see S2-R4 in plan".

### Steps

1. APPEND cases to `hooks/tests/test-build-routing-advisor.sh`. Do NOT create a separate extended file. Original 10 cases remain unmodified at the top of the file (except the F4 line-30 `echo -n` fix authorized in T3); new cases follow as additional test functions invoked by the same runner.
1a. **Per-case isolation (M2):** between every test case, `rm -rf "$FAKE_HOME"` and recreate from scratch. The harness's test dispatcher MUST enforce this in a shared setUp/tearDown wrapper that wraps each case — no case may leak state (state files, sentinels, markers) into the next case. Add this wrapper once; reference it from each appended case.
1a. **Dynamic TOTAL:** update the harness's `TOTAL` to be computed at the end as `TOTAL=$((PASSED + FAILED))` rather than hardcoded to 10. This avoids drift whenever T3.5 appends cases (and any future additions). The final `Results: X/Y passed` line MUST use the computed TOTAL.
2. Implement each case above using the same harness conventions as the RED canary (fake `$HOME`, `$PROJECT_MEMORY` derived via `echo "$PROJECT_ROOT" | tr '/' '-'` against the fake project path per S3-R1, stderr capture via `2>&1` or `2> "$stderr_file"`, exit-code assertion).
3. Run until all appended cases pass alongside the original 10.
4. Commit: `git commit -m "test(hooks): extended AC coverage for build-routing-advisor (#174)"`.

### Acceptance

- All extended cases pass.
- Original 10-case suite still passes (no regression).
- T3 + T3.5 together constitute the GREEN bar for Phase 3; Phase 3 cannot close T3 until T3.5 is also green.

---

## Task 4 — Add Part 1 to `skills/getting-started/SKILL.md`

**Files:** 1–2 (`skills/getting-started/SKILL.md`, optionally `skills/getting-started/build-routing.md`)
**Complexity:** Low
**Review-Tier:** 1
**Dependencies:** None (can run parallel with T2/T3)

### Goal

Add a ≤150-token (cl100k) section under existing skill-selection guidance per Min-6 placement note.

### Prerequisites

- `tiktoken` Python package available for token counting (`pip install tiktoken`). If not installable in the execution environment, FALLBACK to either (a) the `claude` CLI tokenizer if it exposes one, or (b) a word-based proxy calibrated once against a known cl100k sample. **Concrete calibration procedure:** measure the current `## When Skills Apply (Always Invoke)` section of `skills/getting-started/SKILL.md` with tiktoken cl100k — record token count T and word count W; the calibration ratio is T/W. Apply this ratio to the Part 1 addition's word count as the tiktoken-free proxy, with a 15% safety margin (aim for proxy-tokens ≤128 so actual ≤150).

### Steps

1. **Placement (section-heading reference, not line numbers):** BEFORE inserting, verify the section headings `## When Skills Apply (Always Invoke)` and `## When Skills Don't Apply` exist in the current `skills/getting-started/SKILL.md` (e.g. `grep -nE '^## When Skills (Apply|Don'\''t)' skills/getting-started/SKILL.md`). If both exist, insert the new `###` subsection AFTER `## When Skills Apply (Always Invoke)` and BEFORE `## When Skills Don't Apply`. If EITHER heading is missing or the text has drifted, **ESCALATE to the plan reviewer with a proposed alternative placement** (the closest stable semantic anchor adjacent to skill-selection guidance) — do not silently insert at a different location.
2. Draft the inline section (target ~120 tokens; keep margin under 150):
   ```markdown
   ### Build-shaped work routes through /build

   BEFORE dispatching a subagent, check whether the prompt combines design + implementation + review/merge (e.g. "spec + implement + PR", "implement X and open a PR", "build this end-to-end"). STOP — that is /build's job.

   Dispatching it as a raw agent bypasses the gate ledger, skips quality gates, and leaves no audit trail. Use /build (or /spec then /build).

   Single-phase tasks (just a review, just a design, just a test audit) remain fine for raw dispatch. The anti-pattern is the COMBINATION.
   ```
3. Token-count locally:
   ```bash
   python3 -c "import tiktoken; print(len(tiktoken.get_encoding('cl100k_base').encode(open('/tmp/section.md').read())))"
   ```
   **M7-R4 calibration-reference drift fallback:** if the `## When Skills Apply (Always Invoke)` heading (the calibration sample named in the T4 Prerequisites block) is renamed or removed from `skills/getting-started/SKILL.md` at the time of implementation, use the FIRST `##`-level heading of `skills/getting-started/SKILL.md` as the calibration sample instead. Record WHICH heading was used (verbatim text) in the T4 commit message so future audits can reproduce the calibration ratio.
4. If >150 tokens: extract the bullet list to `skills/getting-started/build-routing.md` and keep only the STOP / `/build`'s job / COMBINATION beats inline (per Min-4-R6 compression path). **2P-2-R5 — discoverability requirement:** if compression is taken (Part 1 exceeds 150 tokens and the sub-doc is created), the inline section in `skills/getting-started/SKILL.md` MUST include a markdown link `See [build-routing.md](build-routing.md) for examples` (or equivalent prose linking the exact filename) so the sub-doc is discoverable from the main skill file. An orphaned sub-doc with no inline link defeats the compression tradeoff — readers land on the abbreviated inline guidance without knowing the examples exist.
5. Commit: `git commit -am "docs(skills): add build-shaped-work routing guidance to getting-started (#174)"`.

### Acceptance

- Inline section ≤150 tokens (cl100k).
- Contains literal phrases: `STOP`, `/build`, `COMBINATION`.
- Section header is `###` (third-level under existing structure).

---

## Task 5 — Routing eval

**Files:** 1 (`skills/getting-started/evals/build-routing-evals.json` OR appended to `skills/skill-selection-evals/evals/evals.json`)
**Complexity:** Medium
**Review-Tier:** 2
**Dependencies:** Task 4

### Goal

N≥10 selection-eval prompts that present build-shaped intents; expected_skill = `build`. Median pass over 3 seeds must be ≥8/10. Iteration calibration per Min-6-R6: 3 seeds default, expand to 5 if variance >2.

### Steps

1. Add 10 selection evals to `skills/skill-selection-evals/evals/evals.json` (preferred — keeps eval infrastructure consolidated). Use existing schema:
   ```json
   {
     "id": "build-routing-01",
     "dimension": "direct",
     "boundary": "build-vs-raw-dispatch",
     "prompt": "Implement a rate limiter for the API and open a PR.",
     "expected_skill": "build",
     "common_mistakes": ["raw-dispatch", "design"],
     "context": "Build-shaped: design + implement + ship in one prompt.",
     "reasoning": "Combination of implement + PR triggers /build per #174 routing guidance.",
     "difficulty": "easy"
   }
   ```
2. Required prompt diversity (10 prompts):
   - 3 explicit "spec + implement + PR" variants.
   - 3 "implement X and open a PR" variants.
   - 2 "build feature end-to-end" variants.
   - 2 boundary cases that should still pick `build` (e.g. "design and ship the new auth flow").
3. Run the eval per the existing harness 3 times (different seeds).
4. Compute median pass rate.
5. If median <8/10: iterate Part 1 wording (T4) ONCE, rerun with FRESH 3 seeds. If still <8/10: iterate Part 1 ONCE more, rerun. If still <8/10 after two wording iterations → STOP and ESCALATE per F3-R5 / S3-R2.
   - **ESCALATE operational definition (S3-R2 — does NOT rely on orchestrator exit-code semantics):** the escalation is surfaced via TWO durable artifacts that the user can find regardless of orchestrator retry behavior:
     1. **Sentinel file (primary):** write `docs/plans/ESCALATION-174-T5-routing-eval.md` containing the eval transcript — median score, per-seed pass/fail breakdown, per-prompt results, failing prompts with reasoning traces, and the exact wording iterations tried (diffs of the Part 1 section across iterations). Before `exit 2`, COMMIT the sentinel so it is preserved across branch-switch: `git add -f docs/plans/ESCALATION-174-T5-routing-eval.md && git commit -q -m 'chore: record T5 routing-eval escalation (#174)'`. An uncommitted sentinel will be lost if the orchestrator checks out a different branch before the user inspects the working tree.
     2. **Decision journal entry:** append to `/tmp/crucible-decisions-<session-id>.log` (session id from `$CLAUDE_SESSION_ID` if set, else `$$`): `[<ISO-8601 timestamp>] DECISION: routing-eval | choice=escalate-after-2-iterations | reason=median <8/10 after 2 wording iterations | alternatives=none`.
     3. **Exit code:** exit with code 2 (distinguishes from ordinary failure exit 1). The orchestrator MAY retry on non-zero exit — that is fine; the SENTINEL FILE is the source of truth for the user-facing escalation, not the exit code.
     4. **Stderr message:** the message printed to stderr MUST reference BOTH the sentinel file path (`docs/plans/ESCALATION-174-T5-routing-eval.md`) AND the decision journal entry (`/tmp/crucible-decisions-<session-id>.log`). Example: `T5 ESCALATE after 2 wording iterations. Sentinel: docs/plans/ESCALATION-174-T5-routing-eval.md. Decision journal: /tmp/crucible-decisions-<session-id>.log. Median <8/10; do NOT silently lower threshold.`
     5. (a) do NOT commit a weakened threshold; (b) do NOT loop-tune Part 1 wording beyond 2 iterations; (c) both artifacts above MUST be in place before exit.
   - **Acceptance contract:** the sentinel file and decision journal entry are the primary escalation artifacts. Exit code 2 is advisory only — the orchestrator MAY retry, but the sentinel file is the source of truth for the user-facing escalation. This removes the dependency on orchestrator-specific exit-code handling (which may conflict with /build's auto-retry semantics).
   - **Operational mechanics (no 'blocked-on-user' state in `/build`):** `/build` does NOT support a "blocked-on-user-decision" state. The implementer EXITS T5 (code 2) after writing artifacts. The orchestrator surfaces the failure to the user via the transcript; the user finds the sentinel file. The user then decides one of: (i) accept a lower threshold via manual override recorded in the plan (new sub-task in this plan, not a silent edit); (ii) revise Part 1 further as a new sub-plan task; (iii) close the ticket. There is no in-pipeline pause — the artifacts are the signal.
6. If variance between seeds in any iteration is >2 points, expand to 5 seeds before interpreting median (Min-6-R6).
6a. **Iteration ceiling (M2):** maximum 3 evaluation rounds × 5 seeds = ≤15 eval runs total before escalation. Do NOT loop indefinitely on borderline scores — once the ceiling is hit, ESCALATE per step 5.
7. Commit: `git commit -am "eval(skills): routing eval for build-shaped dispatches (#174)"`.

### Acceptance

- ≥10 prompts added.
- Median pass over 3 (or 5) seeds ≥8/10.
- Eval JSON parses.

---

## Task 6 — Update `hooks/README.md`

**Files:** 1 (`hooks/README.md`)
**Complexity:** Low
**Review-Tier:** 1
**Dependencies:** Task 1, Task 2

### Goal

Document the new hook side-by-side with `gate-ledger-guard`. Document `gate-ledger-guard`'s null-matcher registration in the same doc (Min-5-R6). **Both hooks are registered in user-global `~/.claude/settings.json` (identical scope)** — document them side-by-side as such.

### Required content (new section after "Gate Ledger Guard")

- Heading: `## Build Routing Advisor`
- One-paragraph summary: warn-only PreToolUse hook on `Task` matcher; emits ADVISORY when subagent dispatch looks build-shaped and no pipeline marker matches.
- `### Setup`: **user-global `~/.claude/settings.json`** snippet with `matcher: "Task"` (and fallback note for `Agent` if T1 found that name) and `timeout: 500`. Note explicitly: same scope as `gate-ledger-guard` (per #168 README), not `.claude/settings.json` at the repo root.
- `### How It Works`: ordered list of execution steps (kill switch → allowlist → disclaimer skip → classify → marker check → dedup → emit), naming the three classification categories and the Implement-required + total-distinct ≥2 trigger rule.
- `### JSON Extraction Path`: cite the canonical path from T1's fixture header (e.g. `.tool_input.prompt`, `.tool_input.subagent_type`, `.tool` for tool name) and the `.tool`-field fallback (M1-R4).
- `### Suppression Rules`: marker must have `.skill` in {build, spec, debugging, migrate}, `.start_time` <24h, `.branch == git branch --show-current`. Symmetric detached-HEAD `.pipeline_id == $CLAUDE_SESSION_ID` fallback.
- `### Kill Switch`: env var `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` and sentinel `$PROJECT_MEMORY/.build-routing-advisor-disabled` (with optional `disabled-until: YYYY-MM-DD` line; malformed → permanently disabled fail-safe).
- `### Cross-project firing (M6)`: "This hook is registered user-globally in `~/.claude/settings.json`. It fires on subagent dispatches from ANY project where the user works. Outside crucible, there is no `.pipeline-active` marker so suppression never applies; a build-shaped dispatch in an unrelated project will emit the advisory. For per-project disable, create the sentinel file `<project-root>/.build-routing-advisor-disabled` (preferred — does not require shell init). The env-var path `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` requires the user's shell init (e.g. `.bashrc`, `.zshrc`, or a shell-init wrapper) since hook subprocesses do NOT auto-source `.envrc` or direnv hooks — a `.envrc`-only export will NOT propagate. The design accepts this cross-project fire surface as a tradeoff for the broader enforcement."
- `### State File`: schema and bounded growth (≤5 lines).
- `### Performance`: combined budget with `gate-ledger-guard` ≤200ms P95 over ≥20 dispatches; record measured numbers from T7.
- `### Graceful Degradation`: missing jq, malformed JSON, missing utilities → exit 0 silently.
- `### Testing`: `bash hooks/tests/test-build-routing-advisor.sh` — case count is dynamic; insert the current count by running `grep -c '^test_' hooks/tests/test-build-routing-advisor.sh` at README-update time and embedding that number (or phrase as "see test file for current count"). Do NOT hardcode "10 cases" — T3.5 appends more.
- `### Static-analysis fallback (T8) — known brittleness (M6)`: note that T8's method (b) static-analysis check (grep line-number of marker-write < grep line-number of first Task dispatch in each pipeline skill's SKILL.md) is brittle against future markdown reorganization. If pipeline-skill SKILL.md files are restructured (headings renamed, sections reordered, Task invocation documented in a different syntax), this check can silently pass on broken ordering or fail on correct ordering. Future pipeline-skill refactors MUST update this check alongside the SKILL.md change.

Append to "Gate Ledger Guard" section a brief note (Min-5-R6):

**MIN-5 pre-documentation step:** Before documenting `gate-ledger-guard`'s matcher, READ `~/.claude/settings.json` and record the ACTUAL matcher value (null/empty, `Write|Edit`, or other). Document the VERIFIED value. Do NOT claim `null-matcher` without verification. If the actual matcher is something other than null (e.g. `Write|Edit`), the parity note below MUST be updated to reflect reality.

> Registered in user-global `~/.claude/settings.json`. Matcher: <VERIFIED VALUE — read from settings.json before writing this paragraph>. If null/empty: this hook intercepts every PreToolUse event and filters internally for Write/Edit. If a concrete matcher is set (e.g. `Write|Edit`): Claude Code filters upstream, no internal filtering needed. By contrast, `build-routing-advisor` registers `matcher: "Task"` in the SAME `~/.claude/settings.json`. Both hooks' scope (user-global) and matcher choices are documented for parity.

### Acceptance

- Both new section and parity note present.
- Markdown lints (no broken headings).
- Commit: `git commit -am "docs(hooks): document build-routing-advisor + matcher parity (#174)"`.

---

## Task 7 — Dogfood runs (pipeline + non-pipeline) + perf measurement

**Files:** 0 (measurement artifacts only; numbers transcribed into `hooks/README.md`)
**Complexity:** Medium
**Review-Tier:** 2
**Dependencies:** Task 3, Task 6

### Goal

Validate two ACs:
- **Pipeline dogfood:** run `/build` on a small real change → 0 advisories during normal `/build` operation.
- **Non-pipeline dogfood:** run a representative recon/audit session → ≤2 advisories per hour of active dispatch activity.
- **Perf:** combined `build-routing-advisor` + `gate-ledger-guard` ≤200ms P95 over ≥20 Task dispatches in the `/build` run.

### Steps

0. **Setup — state-file reset (M8-R4):** before EACH dogfood run (pipeline dogfood at step 1 AND non-pipeline dogfood at step 3), RESET the state file to a clean baseline:
   ```bash
   rm -f "$PROJECT_MEMORY/build-routing-advisor-state.md"
   ```
   Dogfood runs MUST start from a clean state-file baseline so advisory-fire counts and dedup timestamps from prior runs do not contaminate the measurement. Without this reset, a prior run's `fires-total` counter and `last-advisory-fingerprint` can silently suppress advisories in the current run, producing a false-clean result. Re-run this reset between the pipeline run (step 1) and the non-pipeline run (step 3).

1. **Pipeline dogfood:**
   - Pick a small real change (e.g. typo fix or one-line README edit on a scratch branch).
   - Run `/build`. Count advisory emissions in transcripts (`grep -c "build-shaped"`).
   - Assert count == 0. If not, investigate: marker write-before-first-dispatch ordering (see T8) or classification false positives.
2. **Perf measurement during pipeline dogfood (EXTERNAL timing — do NOT modify the hook source). Measurement honesty (M4) — single-method gate:**
   - **Method (a) — fixture-based P95 (THE gate):** `time bash hook < fixture` over 20 warm-cache runs. This is the proxy that is actually measurable and is the hard ≤200ms combined P95 gate.
   - **MIN-3-R5 simplification:** the previous "method (b) real-run P95 via Claude Code internal telemetry" path is removed — no public runtime hook-timing API exists, so method (b) was decoration that always degraded to "not measurable" in practice and obscured the fact that method (a) is the gate. The README MUST include a brief statement under the measurement section: "Real-run P95 not measurable without Claude Code runtime timing API; fixture P95 (method a) is the proxy by design."
   - **Bash startup cost (SP5):** method (a) measurements include bash startup (~10–20ms on WSL) per invocation. The 200ms combined-overhead budget is sized to accommodate this. Advisor-alone logic time (isolated from shell startup) is NOT measurable without Claude Code internal instrumentation — out of scope. Record the bash-startup component in the README measurement section as a note so the number is interpretable.
   - **Cache warmup:** before the measurement window, run 2 warmup invocations of EACH hook against the fixture (4 total invocations) and DISCARD their timings. This warms the FS cache and avoids cold-cache bias. Record the measurement section in `hooks/README.md` under the heading **"P95 (warm cache, N=20)"** to make the methodology explicit.
   - Wrap hook invocations with external timing via `time bash hooks/build-routing-advisor.sh < fixture` (and same for `gate-ledger-guard`) over ≥20 dispatches during a real `/build` run. Alternative: use `/usr/bin/time -f '%e'` for machine-parseable seconds, or `date +%s%N` before/after the `bash` invocation in a wrapper script — the key constraint is **the hook source file is NOT modified for measurement**.
   - Capture per-invocation wall-clock into `/tmp/hook-perf.log` (wrapper-level), one line per invocation: `advisor:<ms>` and `guard:<ms>`.
   - Compute two P95 numbers:
     - **`build-routing-advisor` alone** (informational).
     - **`build-routing-advisor` + `gate-ledger-guard` combined** per dispatch — HARD threshold ≤200ms P95 (M5-R8).
   - If combined P95 exceeds 200ms, profile and optimize the most-common path (e.g. earlier exit when `TOOL` not in allowlist, or skipping state-file reads when trigger cannot fire). No instrumentation to remove because none was added to the hook source.
   - Record BOTH measured P95 numbers (advisor-alone AND combined) in the `### Performance` section of `hooks/README.md` via T7's README edit step below. Advisor-alone is informational context; combined is the gated number.
3. **Non-pipeline dogfood:**
   - Run a representative recon/audit session on this codebase (no `/build`/`/spec`/`/debugging`/`/migrate`).
   - Track elapsed wall-clock with active dispatch.
   - Count advisory emissions (`grep -c "build-shaped"` in transcript or state file `fires-total` delta).
   - Assert ≤2 advisories per hour. If exceeded:
     - Verify Implement-required rule is enforced (re-check classification logic).
     - If still exceeded, raise total-distinct threshold from ≥2 to ≥3 in T2 hook (one-line change).
4. Commit perf numbers in README update: `git commit -am "docs(hooks): record measured advisor perf numbers (#174)"`.
5. **Manual verification (if T3.5 case 9 dropped):** if the missing-hook-script graceful path (T3.5 case 9) was dropped per its explicit drop criterion, perform it manually here: rename `hooks/build-routing-advisor.sh` to `hooks/build-routing-advisor.sh.disabled` temporarily; run one Task dispatch in an interactive Claude Code session; verify Claude Code's hook dispatcher handles the missing-script case (either advisory silently absent, or CC logs an error — document which). Restore the script. Record the observed behavior as a `### Missing-script behavior` subsection under `## Build Routing Advisor` in `hooks/README.md`.

### Acceptance

- Pipeline dogfood: 0 advisories during `/build`.
- Non-pipeline dogfood: ≤2 advisories/hr.
- Combined hook P95 ≤200ms over ≥20 dispatches.
- Numbers recorded in `hooks/README.md`.

---

## Task 8 — Marker-write-before-first-dispatch integration test

**Files:** 0–4 (potentially `skills/build/SKILL.md`, `skills/spec/SKILL.md`, `skills/debugging/SKILL.md`, `skills/migrate/SKILL.md` — docstring-ordering only if bug found)
**Complexity:** Medium
**Review-Tier:** **Conditional Tier 3** — Tier 2 if T8 is verification-only (no SKILL.md edits); Tier 3 if any reordering is required in any of the four pipeline-skill `SKILL.md` files. Even docstring-only changes to those four files have outsized blast radius (every `/build`, `/spec`, `/debugging`, `/migrate` invocation reads them). **The implementer MUST declare the applicable tier at the END of T8 Step 1** based on whether any advisory fired during the T7 dogfood run:
- If T7 dogfood emitted 0 advisories from Phase 1 Step -1 onward → T8 is a no-op verification → **Tier 2**.
- If any advisory fired, forcing reordering in ≥1 SKILL.md → **Tier 3** (cross-system review required before merge).
**Dependencies:** Task 7

### Goal

Per AC S2-R6: assert no advisory fires from Phase 1 Step -1 onward of `/build`, including Phase 1 Step 0 and Phase 2 plan-writer dispatch. Mirror for `/spec`, `/debugging`, `/migrate`.

### Steps

1. Reuse the pipeline-dogfood `/build` run from T7. Inspect transcripts/state file for any advisory emission during Phase 1 or Phase 2 subagent dispatches.
2. If any advisory fires before marker write completes:
   - Open the offending skill (e.g. `skills/build/SKILL.md`).
   - Locate the Pipeline-Active Marker section (around line 468 for build).
   - Reorder the documented steps so marker-write precedes any subagent dispatch.
   - **Docstring-ordering fix only** — no behavioral logic change (per SIG-3-R7).
3. Repeat for `/spec` (line 276), `/debugging` (line 295), `/migrate` (line 187). **"Lightweight smoke run" (operational definition):** either (a) stub one test scenario for each skill — a minimal invocation that reaches the first subagent-dispatch point, assert the marker is written BEFORE any Task PreToolUse fires, and assert no advisory was emitted during that first dispatch; OR (b) if stub scenarios are too heavy, degrade to static analysis — read each SKILL.md and verify the Pipeline-Active Marker write instruction appears textually BEFORE the first dispatch invocation. **Specific grep pattern (SP4 + M5-R4 tightening):** use `grep -nE '^[[:space:]]*Task tool \(general-purpose' $SKILL_FILE` as the first-dispatch match pattern. This matches the specific crucible dispatch-convention preamble (`Task tool (general-purpose ...)`), NOT generic mentions of the word "Task" or broad `subagent_type`/`Agent tool` prose. The previous pattern `subagent_type|Agent tool.*dispatch|dispatch.*Agent` was too permissive and produced false positives on documentation prose mentioning the dispatch API. A bare `grep -n 'Task'` (matching the word in any context, e.g. a heading "Task decomposition") remains explicitly rejected. Assert marker-write line number < first-matched-dispatch line number. Record which method (a or b) was used in the T8 commit message.

**M6-R4 (docstring vs actual-execution distinction):** if the static-analysis grep finds a dispatch BEFORE the marker-write section AND the actual EXECUTION ordering is also wrong (not just docstring text-reordering), ESCALATE rather than silently docstring-reorder. Verify by reading the skill's orchestration flow (e.g. the skill's step-by-step runtime sequence, not only its "Pipeline-Active Marker" documentation section). Docstring-reordering only corrects DOCUMENTATION drift; if the skill actually dispatches before writing the marker at runtime, that is a BEHAVIORAL bug out of scope for this plan (F1 retraction) and must be surfaced to the plan reviewer rather than papered over with a docstring swap.
4. Re-run the relevant pipeline skill on a tiny scratch change for each that needed reordering. Confirm 0 advisories.
5. If no reordering needed, document the verification in the commit message:
   - `test(integration): verified marker-write-before-dispatch invariant for /build /spec /debugging /migrate (#174)`
6. If reordering was needed:
   - `fix(skills): reorder marker-write before first subagent dispatch (#174)`

### Acceptance

- `/build` end-to-end on a small real change emits 0 advisories from Phase 1 Step -1 onward.
- `/spec`, `/debugging`, `/migrate` verified analogously (lightweight smoke run for each).
- Any reordering fix is docstring-only; no new behavior introduced.

---

## Task 9 — Post-Merge Reconciler (`hooks/tests/tools/build-routing-reconcile.sh`)

**Files:** `hooks/tests/tools/build-routing-reconcile.sh` (new, ~100 LOC) — 1 file
**Complexity:** Low-Medium (git + jq + text aggregation, read-only)
**Review-Tier:** 2 (Standard — single-system behavioral change, but read-only utility with no cross-system impact; keeps Tier 2 per escalation rules since it introduces a new tool)
**Dependencies:** T2 (hook writes state file consumed by reconciler), T6 (README documents tool)

**M10-R4 — degradation honesty:** if the session-index Task-indexing coverage check (step 0 below) fails — i.e. `hooks/session-index.sh` does NOT index `Task` tool invocations — then T9 DEGRADES to a gate-ledger-audit-only mode. In the degraded form, T9 produces the `(merged PR) ∧ (no gate-ledger PASS)` signal (step 4's binary outcome) WITHOUT the advisor-fire-count / general-purpose-dispatch-count correlation from step 7. In degraded form, T9 does NOT support the "remove Part 2 if cost > value" decision that the innovate proposal promised, because that decision requires both signals together (flagged-PR count AND per-PR advisor fire count) to compute a precision estimate. Deferral of T9 to a separate PR is ACCEPTABLE when the enrichment is unavailable — document the degradation in the reconciler's header comment AND in `hooks/README.md` under the T9 section, so the promised decision surface is not silently promised while actually unactionable. **MIN-4-R5 strengthening:** if T9 degrades to gate-ledger-audit-only, the innovate-pass `remove-Part-2-if-cost-exceeds-value` decision CANNOT be automated from T9's output alone — deferral to a separate PR with archived advisor state is the prerequisite for that decision path (state-file archiving does not exist yet; see step 6's "state-file historical enrichment is NOT available at first run" caveat). Explicitly: in degraded mode, T9's output is an input to a manual review by the maintainer, not an actionable automated signal. This honest-limits statement MUST appear verbatim in `hooks/README.md` under the T9 section to prevent a false precision claim downstream.

### Purpose

Convert advisor warnings into discrete, verifiable post-hoc signal. For each merged PR in a window, answer the binary question: "Did this PR's branch write `Status: PASS` to `build-gate-ledger.md`?" — the exact #168 signal. If NO → #174 failure mode occurred (branch merged without /build running). Combine with advisor fire counts from `build-routing-advisor-state.md` and session-index `general-purpose` Task dispatch counts to produce a precision/recall estimate.

### Why this task exists

Design's Honest-about-limits states: "If post-launch telemetry shows Part 2's cost exceeds value, removal is a clean follow-up." That telemetry is hollow without a ground-truth oracle. The reconciler IS the oracle. Without it, the advisor is unverifiable forever and the design's removal clause is unactionable.

**T9 vs Min-7 reconciliation (SP4):** T9 is post-hoc telemetry, NOT a gate. The Min-7 PR-creation hook was rejected because it proposed GATING merges; T9's read-only post-hoc audit does not gate anything — it surfaces historical data to `/forge` for eventual tuning decisions. This distinction is load-bearing for the deferral rationale: T9 may land in the same PR as #174 or as a follow-up, but it never blocks anything.

### Steps

0. **Verify session-index Task-dispatch coverage (M3):** before relying on session-index for general-purpose dispatch counts, confirm `hooks/session-index.sh` actually indexes `Task` tool invocations. Run `grep -nE 'Task|subagent_type' hooks/session-index.sh` and inspect the logic. If Task dispatches are NOT indexed by session-index, T9's general-purpose-dispatch-count enrichment is UNAVAILABLE — in that case, scope T9 down to the `(merged PR) ∧ (no gate-ledger PASS)` signal only (step 4's binary outcome), without the session-index enrichment in step 7. Document the scoping decision inline in the reconciler's header comment.
1. **Create tool directory:** `mkdir -p hooks/tests/tools/`. Create `hooks/tests/tools/build-routing-reconcile.sh`. Start with standard crucible bash header (`set +e`, graceful degradation on missing utilities).

2. **Accept arguments:** `--since <date>` (default: 14 days ago), `--repo <path>` (default: cwd), `--output <file>` (default: stdout). Validate inputs; on bad args print usage and exit 2.

3. **Enumerate merged PRs in window (M4-R4 — squash-merge primary path):** use the GitHub API as the PRIMARY PR-discovery mechanism, because squash-merged PRs have no second parent and are invisible to `git log --merges`:

   ```bash
   gh pr list --state merged --search "base:main merged:>=$SINCE" --json number,headRefName,mergeCommit,mergedAt --limit 200
   ```

   Parse each PR's `headRefName`, `mergeCommit.oid`, and `mergedAt`. This handles BOTH squash-merges (no merge commit parent structure) AND true merge commits uniformly. Fallback: `git -C "$REPO" log --merges --since="$SINCE" --pretty=format:'%H|%s|%cI'` is used ONLY for non-PR merges (e.g. direct merges outside GitHub) or when `gh` is unavailable. For the fallback path, extract PR branch via `git show --first-parent <sha>` or `git log <sha>^1..<sha>^2` and skip merges that aren't PR-shaped. Record which path was used in the reconciler output so consumers know the coverage (API-primary vs git-log-fallback).

4. **For each PR branch, check gate-ledger signal:** Run `git -C "$REPO" log <branch-tip> -- build-gate-ledger.md` OR equivalently grep the ledger's git history for a commit on the branch that wrote `Status: PASS`. Binary outcome: HAS_GATE_PASS=true|false.

5. **If HAS_GATE_PASS=false, flag the PR:** Record PR number, branch name, merge date, commits on branch count. This is the #174 failure-mode signal.

6. **State-file historical enrichment is NOT available at first run:** the state file is overwritten (no archive mechanism exists). Reconciler output relies on `(merged PR) ∧ (no gate-ledger PASS)` alone (step 4's binary outcome). State-file archiving is a follow-up; do not attempt per-PR advisor-fire enrichment from the live state file.

7. **Enrich with session-index Task dispatch data:** session-index writes under a DIFFERENT directory than the marker-writer (pre-existing divergence — session-index uses sha256 of pwd). Grep `~/.claude/projects/<session-index-dir>/memory/session-index/*/events.jsonl` for `Task` tool invocations with `subagent_type=general-purpose` within the branch's timeframe. Count. Document this directory split inline as a comment in the reconciler: the two data sources live in different subdirectories under `~/.claude/projects/` and both must be consulted.

8. **Emit markdown report:** For each flagged PR: `- PR #N (branch: X, merged YYYY-MM-DD): M advisories fired, K general-purpose dispatches, L commits on branch.` Aggregate at the end: total flagged PRs, total PRs in window, **flagged PR count and enrichment data (actual advisor precision requires archived advisor state; the current implementation shows last-known state only — the state file is overwritten between runs, so historical fire counts per-PR are approximate at best)** (M3 scope honesty).

9. **Output modes:** plain markdown (default), JSON (`--json`), append to `/forge` scratchpad (`--forge`).

10. **Test with a synthetic 2-PR fixture:** write a tiny test that exercises the tool against a temp repo with 2 merge commits (one with gate-ledger PASS, one without). Assert the flagged count is exactly 1.

11. **Commit:** `feat: post-merge reconciler for build-routing advisor telemetry (#174)`. Use `git add -f` for the hook-tests path.

### Acceptance

- Tool runs cleanly against the crucible repo with `--since "14 days ago"` and exits 0.
- Synthetic 2-PR fixture test passes: exactly 1 flagged PR.
- Report is well-formed markdown (or valid JSON with `--json`).
- T9 does NOT block T7 or T8; may defer to a follow-up PR.

---

## Risk + landmine notes

- **T2 (advisor hook)** is High complexity / Tier 3 due to: cross-system dependencies (reads pipeline-active marker written by 4 skills, depends on `$CLAUDE_SESSION_ID` env, registers a Claude Code matcher), new public surface (kill switch + state file schema), and landmine proximity to `gate-ledger-guard` (both run on every PreToolUse).
- **T1 fixture capture** is mandatory for T2 correctness. If the canonical extraction path is wrong, every test that uses non-fixture-derived JSON could spuriously pass while the production hook fails on real Claude Code dispatches.
- **T5 routing eval** carries an explicit ESCALATE step — do NOT silently weaken the ≥8/10 threshold to make it pass.
- **T7 perf 200ms P95** is a HARD threshold (M5-R8). If exceeded, fix before merging — do not defer.
- **T8 reordering fixes (if needed)** must remain docstring-ordering only. Behavioral changes to pipeline skills are out of scope per F1 retraction and SIG-3-R7.

## Out-of-scope (explicitly deferred)

- PR-creation hook with `gate-ledger-id` trailer (Min-7 rejected alternative; tracked separately).
- CI token-budget check for Part 1 (M-6-R8: drift detected at future design-doc QG).
- Behavioral changes to `/spec`, `/debugging`, `/migrate` marker writing (F1 retraction).
- Promoting advisor from warn-only to blocking.
