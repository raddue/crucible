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
- `$PROJECT_MEMORY` derivation: `~/.claude/projects/$(echo -n "$(pwd)" | sha256sum | cut -c1-16)/memory/` (mirrors `hooks/session-index.sh:38-39` EXACTLY — `echo -n`, no trailing newline). **CRITICAL:** using `echo` without `-n` produces a different SHA-256 hash (trailing newline included), silently directing the hook to an empty directory and breaking marker suppression during real `/build` runs. Any code path deriving this hash MUST use `echo -n`.
- `docs/plans/` and `hooks/tests/fixtures/` paths are gitignored — every commit in those paths uses `git add -f` (existing branch convention).
- Token budgeting for Part 1 uses `tiktoken` cl100k locally; no CI gate.
- Tests must use `set +e` patterns where the hook's `set +e` matters; capture stderr with `2> "$stderr_file"`.

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
3. Temporarily register it in **`~/.claude/settings.json`** (user-global, matching the scope of `gate-ledger-guard` per #168 README) under `PreToolUse` (no matcher), invoking `bash /tmp/capture-pretooluse.sh`. Revert this exact registration line before commit.
4. In an interactive Claude Code session, dispatch a single `general-purpose` subagent with any test prompt (e.g. "echo hello").
5. Inspect `/tmp/pretooluse-capture.log`. Identify:
   - Top-level tool field: `.tool` vs `.tool_name`
   - Prompt path: `.tool_input.prompt` vs `.input.prompt`
   - Subagent type path: `.tool_input.subagent_type` vs equivalent
   - Whether `CLAUDE_SESSION_ID` is set
6. Save the captured JSON object verbatim to `/mnt/e/Coding/crucible/hooks/tests/fixtures/agent-pretooluse-sample.json`. Strip any user-private content.
7. Document findings in a comment header of the fixture file:
   ```
   # Captured 2026-04-14 from Claude Code <version>
   # Tool name field: .tool
   # Prompt path: .tool_input.prompt
   # Subagent type path: .tool_input.subagent_type
   # CLAUDE_SESSION_ID exported: yes/no
   ```
8. Remove the temporary capture hook from `~/.claude/settings.json`. Delete `/tmp/capture-pretooluse.sh` and `/tmp/pretooluse-capture.log`.
9. **Settings-diff guard:** Before committing the fixture commit, run `git diff -- ~/.claude/settings.json` (or equivalent inspection of that file vs. its pre-T1 state — e.g. `diff` against a backup taken in step 1). Verify the temporary registration was reverted; no settings-diff should appear in the working tree associated with this commit. If a diff remains, restore the original settings before proceeding.
10. Commit fixture: `git add -f hooks/tests/fixtures/agent-pretooluse-sample.json && git commit -m "test(hooks): pin PreToolUse Task fixture for #174"`.

### Acceptance

- Fixture file exists at the path above and parses as JSON.
- Header comment records the canonical extraction path AND the `$CLAUDE_SESSION_ID` availability finding.
- If `$CLAUDE_SESSION_ID` is **not** exported, T2's design changes per AC S1-R6 (note in T2 step list).

---

## Task 2 — Implement `hooks/build-routing-advisor.sh`

**Files:** 1 (`hooks/build-routing-advisor.sh`)
**Complexity:** High
**Review-Tier:** 3
**Dependencies:** Task 1

### Goal

Implement the full advisor flow per design Part 2. Single bash script; no helper modules. Mirrors `gate-ledger-guard.sh` style.

### Required behavior (in execution order)

0. **Matcher registration (prerequisite, verified by T2 step list):** register `build-routing-advisor` in **`~/.claude/settings.json` (user-global scope, identical to `gate-ledger-guard` per #168 README)** under `PreToolUse` with `matcher: "Task"` (primary; fallback `Agent` per T1 finding) and `timeout: 500` (ms). Verify the entry does NOT conflict with `gate-ledger-guard`'s null-matcher registration — the two entries coexist as separate hooks, one null-matcher (gate-ledger-guard) and one `Task`-matcher (build-routing-advisor).
1. `set +e`. Read stdin into `INPUT`. Exit 0 on empty stdin.
2. **Step 1a — Compute `$PROJECT_MEMORY` FIRST** (before kill-switch block below, so the switch can reference `$PROJECT_MEMORY` without ambiguity): `PROJECT_HASH="$(echo -n "$(pwd)" | sha256sum | cut -c1-16)"` then `PROJECT_MEMORY="$HOME/.claude/projects/$PROJECT_HASH/memory"`. **Derivation MUST match `hooks/session-index.sh:38-39` exactly: `echo -n "$(pwd)" | sha256sum | cut -c1-16`.** Trailing-newline mismatch (using `echo` without `-n`) produces a different hash, silently directs the hook to an empty directory, and is a suppression-bug — MUST be caught by the T3.5 trailing-newline canary.

   **Kill switch** (runs after `$PROJECT_MEMORY` is computed):
   - If `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` → update state file at `$PROJECT_MEMORY/build-routing-advisor-state.md` with `last-honored: $(date +%Y-%m-%d)` (preserving dedup fields and counters per Min-1-R6) then exit 0.
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
   - If trigger does not fire, exit 0.
9. **Pipeline-active marker check** (only reached if trigger fires):
   - `MARKER="$PROJECT_MEMORY/.pipeline-active"`. If absent → marker not active.
   - Parse with jq. Require `.skill` present and in `{build, spec, debugging, migrate}`.
   - **`.start_time` format pin:** per `skills/build/SKILL.md:468`, the marker writes `start_time` as ISO-8601 via `date -u +%Y-%m-%dT%H:%M:%S`. Parse via `START_EPOCH=$(date -d "$START_TIME" +%s 2>/dev/null)`. If parse fails (empty/non-zero exit), treat marker as STALE → marker not active → advisory still emits (do not silently honor a marker with an unparseable timestamp).
   - Require parsed `.start_time` within 24h of `date -u +%s`.
   - Read current branch: `CUR_BRANCH=$(git -C "$(pwd)" branch --show-current 2>/dev/null)`.
   - **Branch comparison (explicit branches — no accidental-correctness via `"" == ""`):**
     - If BOTH `.branch` and `$CUR_BRANCH` are non-empty AND equal → active (proceed to 24h + skill checks above).
     - Else if BOTH are empty AND `.pipeline_id == $CLAUDE_SESSION_ID` → active (detached-HEAD symmetric fallback).
     - Otherwise (asymmetric empty, or non-empty mismatch) → NOT active.
   - If marker is active, exit 0.
10. **Dedup check (Min-9):**
    - Read state file `$PROJECT_MEMORY/build-routing-advisor-state.md`.
    - Compute fingerprint: `echo "$PROMPT" | sha256sum | cut -c1-16`.
    - If `last-advisory-fingerprint` matches AND `last-advisory-at` is within 5 minutes → suppressed: increment `fires-total` only, do NOT emit, write state atomically, exit 0.
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
    - Schema (≤5 lines):
      ```
      last-honored: YYYY-MM-DD
      fires-today: N
      fires-total: N
      last-advisory-at: <ISO-8601 or empty>
      last-advisory-fingerprint: <hash or empty>
      ```
    - **Atomic-write race note (MIN-4-R7):** per-process atomicity is via temp-file + `mv`; cross-process is last-writer-wins. ±1 counter races and fingerprint flicker across concurrent processes are ACCEPTED. Do NOT add `flock` or any file locking. The state file is advisory telemetry, not a correctness-critical ledger.
14. `exit 0`.

### Implementation notes

- All `git`, `jq`, `sha256sum`, `date` failures → exit 0 silently. Never fatal.
- **`mkdir -p` placement (explicit):** the FIRST line of step 13 is `mkdir -p "$PROJECT_MEMORY"`. Do NOT place it elsewhere; do NOT rely on this note alone — the prologue belongs in the step body.
- If T1 found `$CLAUDE_SESSION_ID` is NOT exported, replace step 9's detached-HEAD fallback with a `.start_time`-within-60-seconds session-proxy check and document the reduction in T6.
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

**Pre-authorized exception (F4 correctness fix):** the test harness line 30 currently reads `PROJECT_HASH="$(echo "$FAKE_PROJECT" | sha256sum | cut -c1-16)"` (missing `-n`). This is a reviewer-confirmed bug — the canonical `hooks/session-index.sh:38-39` uses `echo -n`, and the real pipeline skills write markers under the `echo -n` hash. T3 MUST update line 30 to `PROJECT_HASH="$(echo -n "$FAKE_PROJECT" | sha256sum | cut -c1-16)"` (and remove/update the now-inaccurate line 29 comment about pwd trailing newline — replace with a comment stating "match session-index.sh exactly: echo -n, no trailing newline"). Also delete the unused line-28 `printf` assignment that's immediately overwritten. This is the ONLY pre-authorized test edit in T3; all other test concerns still ESCALATE.

### Steps

1. Run `bash /mnt/e/Coding/crucible/hooks/tests/test-build-routing-advisor.sh`.
2. For each failing test:
   - Read the test's setup, prompt, and expected behavior.
   - Trace the hook flow against the inputs.
   - Fix the **hook** (never the test — tests are spec).
3. Common likely failures and fixes:
   - **Test 1 (motivating canary):** classification regex must catch `spec`, `implement`, `PR` with word boundaries; total distinct = 3 ≥ 2 satisfies trigger.
   - **Test 3 (marker suppression):** marker path uses fake `$HOME` per test harness. Hook must derive `$PROJECT_MEMORY` from `echo -n "$(pwd)" | sha256sum | cut -c1-16` (matching `hooks/session-index.sh:38-39`) — test harness line 30 must also use `echo -n` (see pre-authorized exception above).
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

1. **Dedup-across-parallel-scouts (Min-9):** two near-simultaneous invocations with identical prompt → exactly ONE advisory emitted (stderr check across both captures); `fires-total` reflects both (count-all), `last-advisory-fingerprint` matches, second invocation's stderr is empty.
   - **Race tolerance (per Min-4-R7):** under parallel invocation, the second invocation should observe the first's `last-advisory-fingerprint` and suppress. `fires-total` may race ±1 under concurrency — the test ACCEPTS `fires-total ∈ {1, 2}` after two parallel dispatches of the same prompt. The exactly-one-emission stderr assertion is the hard contract; the counter is best-effort.
2. **Kill-switch auto-expiry:** sentinel with `disabled-until: <yesterday>` → advisor proceeds normally (trigger fires if classification matches); state records expiry path.
3. **Malformed `disabled-until` fail-safe:** sentinel with `disabled-until: not-a-date` → PERMANENTLY DISABLED; stderr empty; state records `disabled-until-parse-error`.
4. **Multiple `disabled-until:` lines:** sentinel with two `disabled-until:` lines (first = future, second = past) → FIRST wins; advisor honored.
5. **Asymmetric detached-HEAD:** marker `.branch` empty, current branch `feat/x` (or vice versa) → NOT active; advisory fires.
6. **Branch-switch-mid-pipeline:** marker written on branch A; test runs with current branch B → NOT active; advisory fires.
7. **Substring decoys (negative cases):** prompts containing `planning`, `commitment`, `shipping`, `codebase` as substrings (not whole-word matches) → classification does NOT fire on these alone; verify word-boundary regex correctness. One test case per decoy (4 cases) or a single combined case asserting all four do not trigger.
8. **`subagent_type` non-allowlist cases (all four):** separate cases for `code-reviewer`, `researcher`, arbitrary `custom-agent`, and `""` (empty string) → all exit 0 without emission. (The existing 10-case suite covers `general-purpose`; this extends to the other branches of the allowlist gate.)
9. **Missing-hook-script graceful path:** rename the hook temporarily and invoke via the registered matcher in a sandboxed settings.json → Claude Code does not hard-fail; document Claude Code's observed behavior.
   - **Drop criterion (explicit):** if this case cannot be implemented in <30 lines of bash without modifying Claude Code's hook dispatcher, DROP from T3.5 and move to T7 dogfood as a documented manual verification step. Do not allow this case to balloon the harness.
10. **Perf P95 (informational precursor to T7):** run 20 back-to-back advisor invocations against the fixture, capture wall-clock via `time`, assert P95 ≤100ms for advisor-alone (combined check stays in T7). Uses external timing per revision #12.
11. **Stderr `2>&1` capture assertion (programmatic):** explicit case asserting that the advisor's ADVISORY string is captured via `2>&1` (or equivalent stderr-to-file redirection) in the test harness and matched via `grep -F "ADVISORY:"`. No manual inspection — the assertion is `grep -Fq "ADVISORY:" "$captured"` against the redirected output.
12. **Matcher-neither-Task-nor-Agent fallback:** verify behavior when neither matcher name is correct — the hook falls back to `jq -r '.tool'` (or `.tool_name`) grep on stdin; if that ALSO fails (returns null/empty), the hook exits 0 silently with no stderr. Test asserts: exit code 0, empty stderr, no state-file mutation.
13. **Kill-switch toggle preserves dedup fields:** sequence — (a) emit an advisory (fingerprint + timestamp recorded in state); (b) set kill switch (env var or sentinel); (c) invoke hook → honored, dedup fields preserved per Min-1-R6; (d) remove kill switch; (e) re-trigger within 5-min dedup window with the same prompt → second trigger MUST be deduped (fingerprint preserved across the toggle, no second advisory emitted).
14. **Literal `build-shaped` regression guard:** trivial assertion that the advisory stderr contains the exact literal token `build-shaped` (`grep -Fq "build-shaped"`). Catches future copy edits that might drop or rename the token (the tests grep for it; the README documents it; the dogfood scripts grep for it).
15. **State-file bounded growth ≤5 lines:** run a sequence of (advisory emit + kill-switch set + sentinel with `disabled-until` expiry + reset/eligible re-fire), then assert `[ "$(wc -l < $STATE_FILE)" -le 5 ]`. Schema must remain ≤5 lines across all state transitions; this catches accidental appends/duplicate-key bloat.
16. **Trailing-newline regression canary (F4):** fixture writes a valid pipeline-active marker at `$HOME/.claude/projects/<echo-n hash>/memory/.pipeline-active` (computed with `echo -n "$(pwd)" | sha256sum | cut -c1-16`). Pipe a build-shaped prompt to the hook; assert the hook FINDS the marker and suppresses (exit 0, empty stderr). If the hook were to use `echo` without `-n`, it would look in a DIFFERENT directory, miss the marker, and emit an advisory — this test fails. Fail message must mention "PROJECT_HASH echo -n mismatch" to make the diagnosis obvious.
17. **Real-fixture pass-through:** `bash hooks/build-routing-advisor.sh < hooks/tests/fixtures/agent-pretooluse-sample.json` — hook exits 0; stderr either empty (fixture's prompt is non-build-shaped) OR contains `ADVISORY:` (fixture's prompt is build-shaped). Either outcome passes; the assertion is that the hook does not crash and the extraction path returns the prompt.
18. **Trigger-classification (a) Implement+Design, density=2:** prompt `"implement refactor of design"` → Implement=2 distinct (implement, refactor), Design=1, Ship=0, TOTAL_DISTINCT ≥2 → advisory emits. Comment cites Trigger-Classification rule "Implement≥1 AND (Design≥1 OR Ship≥1) AND total-distinct≥2".
19. **Trigger-classification (b) Implement+Design+Ship (all three):** prompt `"design, implement, and commit"` → all three categories =1, TOTAL_DISTINCT=3 → advisory emits.
20. **Trigger-classification (c) Design+Ship, no Implement:** prompt `"design doc + merge PR"` → Design=1, Ship=2, Implement=0 → NO advisory (Implement-required rule).
21. **Trigger-classification (d) Only-Implement, multiple distinct:** prompt `"implement and code and refactor"` → Implement=3, Design=0, Ship=0 → NO advisory (single-category-only fails; Design≥1 OR Ship≥1 required).
22. **Trigger-classification (e) Implement+Ship, Implement=1 Ship=2:** prompt `"implement X and commit, push"` → Implement=1, Ship=2 distinct → advisory emits.

### Steps

1. APPEND cases to `hooks/tests/test-build-routing-advisor.sh`. Do NOT create a separate extended file. Original 10 cases remain unmodified at the top of the file (except the F4 line-30 `echo -n` fix authorized in T3); new cases follow as additional test functions invoked by the same runner.
1a. **Dynamic TOTAL:** update the harness's `TOTAL` to be computed at the end as `TOTAL=$((PASSED + FAILED))` rather than hardcoded to 10. This avoids drift whenever T3.5 appends cases (and any future additions). The final `Results: X/Y passed` line MUST use the computed TOTAL.
2. Implement each case above using the same harness conventions as the RED canary (fake `$HOME`, `pwd`-derived `$PROJECT_MEMORY` using `echo -n`, stderr capture via `2>&1` or `2> "$stderr_file"`, exit-code assertion).
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
4. If >150 tokens: extract the bullet list to `skills/getting-started/build-routing.md` and keep only the STOP / `/build`'s job / COMBINATION beats inline (per Min-4-R6 compression path).
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
5. If median <8/10: iterate Part 1 wording (T4) ONCE, rerun with FRESH 3 seeds. If still <8/10: iterate Part 1 ONCE more, rerun. If still <8/10 after two wording iterations → STOP and ESCALATE to user per F3-R5.
   - **ESCALATE operational definition:** (a) do NOT commit a weakened threshold; (b) do NOT loop-tune Part 1 wording beyond 2 iterations; (c) write the eval transcript (per-seed pass/fail breakdown, failing prompts, reasoning traces) to a file under `docs/plans/` (git-add-forced); (d) surface the decision to the user via the failure path below.
   - **Operational mechanics (no 'blocked-on-user' state in `/build`):** `/build` does NOT support a "blocked-on-user-decision" state. The implementer EXITS T5 with a non-zero exit code and a clear error message that points to the eval transcript path. The orchestrator (Phase 3 runner) surfaces the failure to the user. The user then decides one of: (i) accept a lower threshold via manual override recorded in the plan (new sub-task in this plan, not a silent edit); (ii) revise Part 1 further as a new sub-plan task; (iii) close the ticket. There is no in-pipeline pause — the failure is the signal.
6. If variance between seeds in any iteration is >2 points, expand to 5 seeds before interpreting median (Min-6-R6).
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
- `### State File`: schema and bounded growth (≤5 lines).
- `### Performance`: combined budget with `gate-ledger-guard` ≤200ms P95 over ≥20 dispatches; record measured numbers from T7.
- `### Graceful Degradation`: missing jq, malformed JSON, missing utilities → exit 0 silently.
- `### Testing`: `bash hooks/tests/test-build-routing-advisor.sh` — case count is dynamic; insert the current count by running `grep -c '^test_' hooks/tests/test-build-routing-advisor.sh` at README-update time and embedding that number (or phrase as "see test file for current count"). Do NOT hardcode "10 cases" — T3.5 appends more.

Append to "Gate Ledger Guard" section a brief note (Min-5-R6):
> Registered in user-global `~/.claude/settings.json`. Matcher: none — this hook intercepts every PreToolUse event and filters internally for Write/Edit. By contrast, `build-routing-advisor` registers `matcher: "Task"` in the SAME `~/.claude/settings.json`. Both hooks' scope (user-global) and matcher choices are documented for parity.

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

1. **Pipeline dogfood:**
   - Pick a small real change (e.g. typo fix or one-line README edit on a scratch branch).
   - Run `/build`. Count advisory emissions in transcripts (`grep -c "build-shaped"`).
   - Assert count == 0. If not, investigate: marker write-before-first-dispatch ordering (see T8) or classification false positives.
2. **Perf measurement during pipeline dogfood (EXTERNAL timing — do NOT modify the hook source):**
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
3. Repeat for `/spec` (line 276), `/debugging` (line 295), `/migrate` (line 187). **"Lightweight smoke run" (operational definition):** either (a) stub one test scenario for each skill — a minimal invocation that reaches the first subagent-dispatch point, assert the marker is written BEFORE any Task PreToolUse fires, and assert no advisory was emitted during that first dispatch; OR (b) if stub scenarios are too heavy, degrade to static analysis — read each SKILL.md and verify the Pipeline-Active Marker write instruction appears textually BEFORE the first `Task tool` invocation in the document (use `grep -n` to show the line numbers and assert marker-write line number < first Task-dispatch line number). Record which method (a or b) was used in the T8 commit message.
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

### Purpose

Convert advisor warnings into discrete, verifiable post-hoc signal. For each merged PR in a window, answer the binary question: "Did this PR's branch write `Status: PASS` to `build-gate-ledger.md`?" — the exact #168 signal. If NO → #174 failure mode occurred (branch merged without /build running). Combine with advisor fire counts from `build-routing-advisor-state.md` and session-index `general-purpose` Task dispatch counts to produce a precision/recall estimate.

### Why this task exists

Design's Honest-about-limits states: "If post-launch telemetry shows Part 2's cost exceeds value, removal is a clean follow-up." That telemetry is hollow without a ground-truth oracle. The reconciler IS the oracle. Without it, the advisor is unverifiable forever and the design's removal clause is unactionable.

### Steps

1. **Create tool directory:** `mkdir -p hooks/tests/tools/`. Create `hooks/tests/tools/build-routing-reconcile.sh`. Start with standard crucible bash header (`set +e`, graceful degradation on missing utilities).

2. **Accept arguments:** `--since <date>` (default: 14 days ago), `--repo <path>` (default: cwd), `--output <file>` (default: stdout). Validate inputs; on bad args print usage and exit 2.

3. **Enumerate merged PRs in window:** `git -C "$REPO" log --merges --since="$SINCE" --pretty=format:'%H|%s|%cI'`. Parse each merge commit; extract PR branch via `git show --first-parent <sha>` or `git log <sha>^1..<sha>^2`. Skip merges that aren't PR-shaped.

4. **For each PR branch, check gate-ledger signal:** Run `git -C "$REPO" log <branch-tip> -- build-gate-ledger.md` OR equivalently grep the ledger's git history for a commit on the branch that wrote `Status: PASS`. Binary outcome: HAS_GATE_PASS=true|false.

5. **If HAS_GATE_PASS=false, flag the PR:** Record PR number, branch name, merge date, commits on branch count. This is the #174 failure-mode signal.

6. **Enrich with advisor fire data:** For each flagged PR, check `$PROJECT_MEMORY/build-routing-advisor-state.md` snapshots (if available — the state file is overwritten, so historical data is in session-index or git-committed retros). Count advisory fires during the branch's lifetime.

7. **Enrich with session-index Task dispatch data:** Grep `~/.claude/projects/<hash>/memory/session-index/*/events.jsonl` for `Task` tool invocations with `subagent_type=general-purpose` within the branch's timeframe. Count.

8. **Emit markdown report:** For each flagged PR: `- PR #N (branch: X, merged YYYY-MM-DD): M advisories fired, K general-purpose dispatches, L commits on branch.` Aggregate at the end: total flagged PRs, total PRs in window, approximate advisor precision (flagged-with-advisory / total-advisories-in-window).

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
