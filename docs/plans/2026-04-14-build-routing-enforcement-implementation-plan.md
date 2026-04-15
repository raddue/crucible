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

## Conventions

- All paths absolute under `/mnt/e/Coding/crucible/`.
- Bash style follows `hooks/gate-ledger-guard.sh`: `set +e`, jq null-safety with `// empty`, graceful `exit 0` on any utility failure, stdin via `INPUT="$(cat)"`.
- `$PROJECT_MEMORY` derivation: `~/.claude/projects/$(echo "$(pwd)" | sha256sum | cut -c1-16)/memory/` (mirrors `hooks/session-index.sh`).
- `docs/plans/` and `hooks/tests/fixtures/` paths are gitignored — every commit in those paths uses `git add -f` (existing branch convention).
- Token budgeting for Part 1 uses `tiktoken` cl100k locally; no CI gate.
- Tests must use `set +e` patterns where the hook's `set +e` matters; capture stderr with `2> "$stderr_file"`.

## Dependency Graph

```
T1 (fixture) ─┬─> T2 (hook impl) ─> T3 (RED → GREEN ack tests)
              │                       │
              └──> T6 (README)        ├──> T4 (SKILL.md Part 1) ─> T5 (routing eval)
                                      │
                                      └──> T7 (dogfood + perf)
                                                  │
                                                  └──> T8 (marker-write integration test)
```

No circular deps. T1 unblocks both T2 and T6 (extraction path documentation). T4 and T5 are gated on T3 only insofar as the eval runs after Part 1 lands; technically T4 could land in parallel with T2/T3.

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
3. Temporarily register it in `.claude/settings.json` under `PreToolUse` (no matcher), invoking `bash /tmp/capture-pretooluse.sh`.
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
8. Remove the temporary capture hook from `.claude/settings.json`. Delete `/tmp/capture-pretooluse.sh` and `/tmp/pretooluse-capture.log`.
9. Commit fixture: `git add -f hooks/tests/fixtures/agent-pretooluse-sample.json && git commit -m "test(hooks): pin PreToolUse Task fixture for #174"`.

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

1. `set +e`. Read stdin into `INPUT`. Exit 0 on empty stdin.
2. **Kill switch** (before any other work):
   - If `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` → update state file `last-honored: $(date +%Y-%m-%d)` (preserving dedup fields and counters per Min-1-R6) then exit 0.
   - Compute `$PROJECT_MEMORY` (sha256 of pwd, first 16 chars).
   - If sentinel `$PROJECT_MEMORY/.build-routing-advisor-disabled` exists:
     - Parse FIRST `^disabled-until: ` line.
     - If date parses AND today's local date < parsed date → honor switch, update `last-honored`, exit 0.
     - If date parses AND today >= parsed date → switch expired, continue.
     - If date does NOT parse → write `disabled-until-parse-error: <raw>` to state, honor switch (PERMANENTLY DISABLED fail-safe), exit 0.
     - If sentinel exists with no `disabled-until:` line → honor switch indefinitely, update `last-honored`, exit 0.
3. **Dependency check:** `command -v jq` — if missing, exit 0 silently.
4. **Tool name extraction:** `TOOL=$(echo "$INPUT" | jq -r '.tool // .tool_name // empty')`. If `TOOL` not in `Task|Agent`, exit 0.
5. **Prompt + subagent extraction:** use the canonical path discovered in T1. Try `.tool_input.prompt` first, then `.input.prompt`. Same for `subagent_type`. If both null, exit 0 (malformed JSON path covered).
6. **Allowlist:** if `subagent_type` is set AND not equal to `general-purpose`, exit 0.
7. **Disclaimer skip:** case-insensitive grep for any of `just the design`, `design only`, `no implementation`, `review only`, `audit only`, `spec only`, `recon only`. If matched, exit 0.
8. **Classification (BEFORE any git subprocess; Min-7).** Use `grep -iEc` with word boundaries:
   - Design: `\b(design|spec|plan)\b`
   - Implement: `\b(implement|code|create|refactor)\b`
   - Ship: `\b(PR|commit|merge|push|land|ship)\b`
   - Compute distinct keyword counts per category by extracting matched words via `grep -ioE` then `sort -u`.
   - Trigger condition: `implement_count >= 1` AND (`design_count >= 1` OR `ship_count >= 1`) AND `total_distinct_across_categories >= 2`.
   - If trigger does not fire, exit 0.
9. **Pipeline-active marker check** (only reached if trigger fires):
   - `MARKER="$PROJECT_MEMORY/.pipeline-active"`. If absent → marker not active.
   - Parse with jq. Require `.skill` present and in `{build, spec, debugging, migrate}`.
   - Require `.start_time` parseable AND within 24h of `date -u +%s`.
   - Read current branch: `CUR_BRANCH=$(git -C "$(pwd)" branch --show-current 2>/dev/null)`.
   - Require `.branch == $CUR_BRANCH`.
   - **Detached-HEAD fallback:** if both marker `.branch` and `$CUR_BRANCH` are empty AND `.pipeline_id == $CLAUDE_SESSION_ID` → marker active. Otherwise asymmetric empty → not active.
   - If marker is active, exit 0.
10. **Dedup check (Min-9):**
    - Read state file `$PROJECT_MEMORY/build-routing-advisor-state.md`.
    - Compute fingerprint: `echo "$PROMPT" | sha256sum | cut -c1-16`.
    - If `last-advisory-fingerprint` matches AND `last-advisory-at` is within 5 minutes → suppressed: increment `fires-total` only, do NOT emit, write state atomically, exit 0.
11. **Reset `fires-today`:** compare today's local date against most recent of (`last-honored` date, `last-advisory-at` date). If neither exists OR most recent < today → reset `fires-today` to 0.
12. **Emit advisory** to stderr (exactly 2 lines, includes literal `build-shaped`):
    ```
    ADVISORY: Dispatch looks build-shaped. If single-phase, ignore.
    Else prefer /build (or /spec then /build) for gate coverage.
    ```
13. **State file update (atomic write):**
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
14. `exit 0`.

### Implementation notes

- All `git`, `jq`, `sha256sum`, `date` failures → exit 0 silently. Never fatal.
- Use `mkdir -p "$PROJECT_MEMORY"` before any state write.
- If T1 found `$CLAUDE_SESSION_ID` is NOT exported, replace step 9's detached-HEAD fallback with a `.start_time`-within-60-seconds session-proxy check and document the reduction in T6.
- Performance: classification uses one `grep -iEc` per category against `<<< "$PROMPT"` — no temp files. Target ≤50ms per invocation.

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

### Steps

1. Run `bash /mnt/e/Coding/crucible/hooks/tests/test-build-routing-advisor.sh`.
2. For each failing test:
   - Read the test's setup, prompt, and expected behavior.
   - Trace the hook flow against the inputs.
   - Fix the **hook** (never the test — tests are spec).
3. Common likely failures and fixes:
   - **Test 1 (motivating canary):** classification regex must catch `spec`, `implement`, `PR` with word boundaries; total distinct = 3 ≥ 2 satisfies trigger.
   - **Test 3 (marker suppression):** marker path uses fake `$HOME` per test harness. Hook must derive `$PROJECT_MEMORY` from `pwd | sha256sum | cut -c1-16` consistently — test does this same derivation at line 30.
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

---

## Task 4 — Add Part 1 to `skills/getting-started/SKILL.md`

**Files:** 1–2 (`skills/getting-started/SKILL.md`, optionally `skills/getting-started/build-routing.md`)
**Complexity:** Low
**Review-Tier:** 1
**Dependencies:** None (can run parallel with T2/T3)

### Goal

Add a ≤150-token (cl100k) section under existing skill-selection guidance per Min-6 placement note.

### Steps

1. Identify placement: insert after the "When Skills Apply (Always Invoke)" table (line 35) but before "When Skills Don't Apply" (line 37). This keeps it adjacent to skill-selection guidance.
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
5. If median <8/10: iterate Part 1 wording (T4) ONCE, rerun with FRESH 3 seeds. If still <8/10: iterate Part 1 ONCE more, rerun. If still <8/10 after two wording iterations → STOP and ESCALATE to user with eval transcript per F3-R5.
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

Document the new hook side-by-side with `gate-ledger-guard`. Document `gate-ledger-guard`'s null-matcher registration in the same doc (Min-5-R6).

### Required content (new section after "Gate Ledger Guard")

- Heading: `## Build Routing Advisor`
- One-paragraph summary: warn-only PreToolUse hook on `Task` matcher; emits ADVISORY when subagent dispatch looks build-shaped and no pipeline marker matches.
- `### Setup`: settings.json snippet with `matcher: "Task"` (and fallback note for `Agent` if T1 found that name) and `timeout: 500`.
- `### How It Works`: ordered list of execution steps (kill switch → allowlist → disclaimer skip → classify → marker check → dedup → emit), naming the three classification categories and the Implement-required + total-distinct ≥2 trigger rule.
- `### JSON Extraction Path`: cite the canonical path from T1's fixture header (e.g. `.tool_input.prompt`, `.tool_input.subagent_type`, `.tool` for tool name) and the `.tool`-field fallback (M1-R4).
- `### Suppression Rules`: marker must have `.skill` in {build, spec, debugging, migrate}, `.start_time` <24h, `.branch == git branch --show-current`. Symmetric detached-HEAD `.pipeline_id == $CLAUDE_SESSION_ID` fallback.
- `### Kill Switch`: env var `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` and sentinel `$PROJECT_MEMORY/.build-routing-advisor-disabled` (with optional `disabled-until: YYYY-MM-DD` line; malformed → permanently disabled fail-safe).
- `### State File`: schema and bounded growth (≤5 lines).
- `### Performance`: combined budget with `gate-ledger-guard` ≤200ms P95 over ≥20 dispatches; record measured numbers from T7.
- `### Graceful Degradation`: missing jq, malformed JSON, missing utilities → exit 0 silently.
- `### Testing`: `bash hooks/tests/test-build-routing-advisor.sh` (10 cases).

Append to "Gate Ledger Guard" section a brief note (Min-5-R6):
> Matcher: none — this hook intercepts every PreToolUse event and filters internally for Write/Edit. By contrast, `build-routing-advisor` registers `matcher: "Task"`. Both hooks' matcher choices are documented for parity.

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
2. **Perf measurement during pipeline dogfood:**
   - Wrap each PreToolUse hook invocation with timing. Add temporary instrumentation:
     ```bash
     T0=$(date +%s%N)
     # ... existing hook body ...
     T1=$(date +%s%N); echo "advisor: $(( (T1-T0)/1000000 ))ms" >> /tmp/hook-perf.log
     ```
   - Same for `gate-ledger-guard`. Run a `/build` invocation that produces ≥20 Task dispatches.
   - Compute P95 of summed (advisor + guard) per dispatch.
   - Assert P95 ≤200ms. If exceeded, profile and optimize the most-common path (early-exit when no classification match). Remove instrumentation before commit.
   - Record measured P95 numbers in the `### Performance` section of `hooks/README.md` (T6).
3. **Non-pipeline dogfood:**
   - Run a representative recon/audit session on this codebase (no `/build`/`/spec`/`/debugging`/`/migrate`).
   - Track elapsed wall-clock with active dispatch.
   - Count advisory emissions (`grep -c "build-shaped"` in transcript or state file `fires-total` delta).
   - Assert ≤2 advisories per hour. If exceeded:
     - Verify Implement-required rule is enforced (re-check classification logic).
     - If still exceeded, raise total-distinct threshold from ≥2 to ≥3 in T2 hook (one-line change).
4. Commit perf numbers in README update: `git commit -am "docs(hooks): record measured advisor perf numbers (#174)"`.

### Acceptance

- Pipeline dogfood: 0 advisories during `/build`.
- Non-pipeline dogfood: ≤2 advisories/hr.
- Combined hook P95 ≤200ms over ≥20 dispatches.
- Numbers recorded in `hooks/README.md`.

---

## Task 8 — Marker-write-before-first-dispatch integration test

**Files:** 0–4 (potentially `skills/build/SKILL.md`, `skills/spec/SKILL.md`, `skills/debugging/SKILL.md`, `skills/migrate/SKILL.md` — docstring-ordering only if bug found)
**Complexity:** Medium
**Review-Tier:** 2
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
3. Repeat for `/spec` (line 276), `/debugging` (line 295), `/migrate` (line 187).
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
