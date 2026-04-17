---
ticket: "#174"
title: "One-layer-up enforcement — prevent raw-agent dispatch of build-shaped work"
created: 2026-04-14
status: ready-for-build
---

# Build Routing Enforcement — Design

## Problem

The gate-ledger-guard hook (#168) provides mechanical enforcement WITHIN `/build` invocations — it blocks unauthorized PASS writes, validates PipelineID cross-checks, and ensures the quality gate actually ran. But it can't protect against the failure mode one layer up: **never invoking `/build` at all** and instead dispatching raw general-purpose agents with ad-hoc "spec + implement + PR" instructions.

Observed failure mode (verbatim from session):

> My specific failure today was one layer up — I never invoked /build. I dispatched raw general-purpose agents with ad-hoc "spec + implement + PR" instructions. The gate ledger can't protect against that; it assumes /build is running.

This is the same class of gap as #169 (subagent evidence verification) and #170 (post-push CI) — structural defenses that catch specific bypass patterns that prompt-based guidance alone doesn't stop.

## Why mechanical enforcement is hard here

The gate-ledger-guard works because the signal is discrete and verifiable:
- Trigger: `Status: PASS` written to `build-gate-ledger.md`
- Verification: matching verdict marker exists
- False positive rate: zero (20/20 tests pass)

For an Agent dispatch hook, the signal is inherently heuristic:
- Trigger: "prompt contains words like implement, PR, commit, spec"
- Verification: "is /build running (check pipeline-active marker)?"

False positives abound: recon agents investigating auth implementation, test-coverage audits mentioning "implement", fix agents dispatched by quality-gate, 40 legitimate parallel research dispatches. Tuning tight misses bypasses; tuning loose trains Claude to ignore warnings.

## Proposed two-part defense

### Part 1: getting-started entry (prompt-level)

Add explicit anti-pattern guidance. This is **write-time behavior** — the
instructions fire when the agent is composing a dispatch prompt, *before*
sending the Task/Agent tool call. The guidance reshapes authoring, not
post-hoc review:

```
## Build-shaped work MUST route through /build

BEFORE dispatching a subagent, check whether your prompt includes any of:
- "spec + implement + PR" as a combined workflow
- "implement feature X and open a PR"
- "build this thing end-to-end"
- "design then plan then execute" as a single dispatch
- Any prompt that spans design + implementation + review + merge

STOP. That's /build's job. Dispatching it as a raw agent bypasses the
gate ledger, skips quality gates, and produces no audit trail.

Use /build (or /spec then /build) instead.

If you genuinely have a single-phase task (just a code review, just a
design, just a test audit), raw agent dispatch is fine. The anti-pattern
is the COMBINATION: design+implement+merge as one subagent prompt.
```

Zero false positives. Precise. Educational. (M4)

This section is added under an appropriate existing heading in
`getting-started/SKILL.md` (e.g. alongside skill-selection guidance)
rather than as a floating top-level section. The implementer chooses
placement to match the existing document structure (M4-R2). **Part 1's
placement is chosen by the implementer under existing skill-selection
guidance headers, not as a standalone top-level section** (Min-6):
this improves the likelihood the guidance is read alongside related
routing material.

**Token budget (S4-R3).** `getting-started/SKILL.md` loads into every
session, so every added line has recurring cost. The Part 1 addition
must fit within a ~150-token budget (approximately 20–25 lines of
markdown). If the full anti-pattern list exceeds budget, move the
verbose examples to a linked sub-doc (e.g.
`skills/getting-started/build-routing.md`) and keep the inline
section terse — the inline form must preserve the STOP / "/build's
job" / "COMBINATION is the anti-pattern" beats.

**Token budget math (MIN-6-R7).** Budget is 150 TOKENS (not lines),
measured via a tokenizer compatible with Claude's (e.g., `tiktoken`
with cl100k encoding as a rough approximation). Implementer must
count; line count is a weak proxy and MAY NOT be used as the budget
mechanism.

**Token-budget drift (M-6-R8).** No CI check currently enforces the
150-token Part 1 budget; drift is detected at future design-doc QG
iterations. If Part 1 inflates meaningfully, add a CI check as a
follow-up.

### Part 2: warn-only hook (soft structural)

PreToolUse hook registered on the subagent-dispatch tool. The matcher
is `Task` in current Claude Code; earlier/alternative versions may use
`Agent`. The hook README documents both and specifies the active
version's matcher at install time (M2-R2). The hook MUST register a
matcher distinct from `gate-ledger-guard` (which uses `Write|Edit`);
see M3. The discovery step in S1 below pins the correct matcher.

The hook executes in the order below. **Classification runs BEFORE
the git subprocess call** (Min-7): most dispatches produce no
classification match, so the common-case cost is early-exit with no
git subprocess fork. The git-current-branch call only runs if
classification produced a potential trigger.

Throughout Part 2, **`$PROJECT_MEMORY`** resolves to
`~/.claude/projects/<project-hash>/memory/` (Min-3) — derived
identically to how existing pipeline skills resolve their scratch
directory. **`$PROJECT_MEMORY` derivation (MIN-1-R7):** the hook
derives `$PROJECT_MEMORY` via
`~/.claude/projects/$(pwd | sha256sum | cut -c1-16)/memory/` —
matching `hooks/session-index.sh` which uses the same
`sha256sum | cut -c1-16` of `pwd` derivation.

The hook:

1. Extracts the dispatch prompt from stdin JSON. The exact path
   (`.tool_input.prompt`, `.input.prompt`, etc.) is pinned by capturing
   a real PreToolUse payload during implementation (see S1). Fixture
   committed to `hooks/tests/fixtures/agent-pretooluse-sample.json`.
2. Reads `subagent_type` (or equivalent field). If it is NOT
   `general-purpose` (e.g. an MCP/specialty type), skip — exit 0 with
   no warning (SP2 allowlist).
3. Checks for a single-phase disclaimer in the prompt. If any of
   `just the design`, `design only`, `no implementation`,
   `review only`, `audit only`, `spec only`, `recon only` appear,
   skip — exit 0 (S2).
4. Classifies the prompt against three keyword categories using
   **word-boundary regex** (`\b...\b`) so short tokens don't match
   substrings (`plan` vs `planning`, `commit` vs `commitment`,
   `ship` vs `shipping`, `code` vs `codebase`) (S2-R2). **Case
   sensitivity (MIN-2-R7):** all keyword matching uses `grep -iE`
   for case-insensitive word-boundary regex. `PR` and `pr` both
   match; `ship` and `SHIP` both match.
   - Design: `\b(design|spec|plan)\b` (S3-R4: dropped
     `architect|architecture` — in review/audit prompts these are
     ubiquitous; the Implement-required rule below tolerates the
     tighter Design regex)
   - Implement: `\b(implement|code|create|refactor)\b` — `build`
     deliberately omitted (S1-R3): in this codebase it is a domain
     noun (`/build`, "build skill", "build pipeline") more often than
     a verb, and every meta-conversation about the `/build` skill
     would trip Implement
   - Ship: `\b(PR|commit|merge|push|land|ship)\b`. The lowercase
     word-boundary handles `PR` adequately once Implement is required;
     audit-only prompts that mention PR are protected by the
     Implement-required rule below.

   **Implement-required trigger (S3-R4, density rule revised S3-R6).**
   Trigger fires only when ALL of: Implement has ≥1 word-boundary hit,
   AND (Design OR Ship) has ≥1 hit, AND **the total number of distinct
   matched keywords across ALL matched categories is ≥2** (total-distinct
   rule, S3-R6). This replaces the earlier "at least one category with
   2+ distinct keyword hits" density rule, which had a correctness bug:
   the design's own verbatim motivating prompt "spec + implement + PR"
   (Part 1 line 16) produces Design=1 (spec), Implement=1 (implement),
   Ship=1 (PR) — no single category reaches 2, so the prior rule failed
   to fire on the exact scenario this issue was opened to address. The
   total-distinct formulation still demands multi-category breadth
   (Implement + (Design OR Ship)) so single-category spam cannot trip
   it, while ensuring the motivating example fires.

   Worked examples under the revised rule:
   - "spec + implement + PR" → distinct keywords = 3, Implement ≥1,
     Design ≥1 → **fires** (motivating example canary)
   - "implement X" alone → Design/Ship both 0 → no advisory
   - "implement and code" → Design/Ship both 0 → no advisory
   - "design doc review" → Implement 0 → no advisory

   Rationale: build-shaped work by definition involves producing code.
   A prompt without Implement-category words is review/recon/audit;
   those are legitimate single-phase tasks by this design's own Part 1
   anti-pattern list. Design+Ship alone ("review PR #123 for design
   correctness") is review work and must not fire. Total-distinct ≥2
   catches the motivating example while still requiring multi-category
   breadth to avoid single-category noise.
5. Checks the pipeline-active marker (`$PROJECT_MEMORY/.pipeline-active`
   or equivalent). Treat marker as **active** ONLY when ALL THREE of:
   - File exists and is parseable JSON, `.skill` field is present and
     non-empty, and `.skill` names a known pipeline skill (`build`,
     `spec`, `debugging`, `migrate`) (SP1)
   - `.start_time` is within the last 24 hours (M4-R4: widened from
     8h to accommodate long `/build` runs; branch-equality +
     `.skill` presence provide the real tightness, 24h is just a
     zombie-marker upper bound)
   - `.branch` equals the output of
     `git -C "$PROJECT_ROOT" branch --show-current` at hook
     invocation time, where `$PROJECT_ROOT = $(pwd)` at hook entry
     (same convention as `gate-ledger-guard.sh` and `session-index.sh`)
     (S1-R4: SAME command as the marker-write side
     for symmetric canonicalization — NOT `rev-parse --abbrev-ref
     HEAD`, which returns the literal string `HEAD` on detached HEAD
     while `branch --show-current` returns empty, so the two never
     match during `/checkpoint` restore operations inside `/build`)

   **Detached-HEAD fallback (S1-R4).** If BOTH sides read as empty
   (marker's `.branch` is `""` AND the hook's `branch --show-current`
   returns `""` — i.e. both legitimately detached), fall back to
   `.pipeline_id == $CLAUDE_SESSION_ID`. If those match, treat the
   marker as active. If ONE side is empty and the other non-empty,
   treat as non-matching (fail-open to advisory; the heuristic
   warning is the safe default). This is the single documented
   fallback case.

   *Why session-ID equality is safe here (Min-1).* The session-ID
   equality fallback was rejected as primary suppression mechanism
   (F1-R3) due to runtime semantics uncertainty across subagent
   dispatches. Its use here is narrowly gated on BOTH sides being
   detached (no branch available), making session-ID the only
   remaining identity signal — if that also fails, the advisor fires,
   which is the correct fail-open for heuristic warnings.

   Otherwise the marker is treated as absent — a stale, cross-branch,
   or non-pipeline-skill marker does NOT suppress the advisory.

   **Why branch equality, not session-ID equality (F1-R3 / F2-R3).**
   Prior rounds attempted `.pipeline_id == $CLAUDE_SESSION_ID` to
   scope suppression to the current session. That check is a coin
   flip: either it never matches (making the time window the only
   guard, so a crashed marker zombie-suppresses) or it self-spams
   50–90× per `/build` run. Branch equality is deterministic: the
   marker's `.branch` field is written by `/build` (verified at
   `skills/build/SKILL.md:468`) and the analogous pipeline-start
   steps in `/spec`, `/debugging`, `/migrate` from
   `git branch --show-current`; the hook reads the current branch
   with the SAME command (S1-R4 symmetric canonicalization).
   Crashed markers from an unrelated branch no longer suppress;
   legitimate subagent dispatch during an active pipeline on the
   same branch does. Session-ID equality is retained only as the
   both-sides-detached fallback above.
6. If the Implement-required trigger fires AND no active pipeline
   marker, emit to stderr (M2, advisory reframing; Min-5 uses the
   literal phrase "build-shaped" for transcript search; S2-R4 caps
   the copy at 2 lines to keep per-firing token cost low):
   ```
   ADVISORY: Dispatch looks build-shaped. If single-phase, ignore.
   Else prefer /build (or /spec then /build) for gate coverage.
   ```
7. Always exits 0 (warn only, never block). If the hook script is
   missing or non-executable, Claude Code's normal hook dispatch
   behavior applies — the tool call proceeds unimpeded (M5 graceful
   degradation). Malformed JSON or missing utilities (jq, etc.) cause
   the hook to exit 0 silently. Because the hook is warn-only, this
   is acceptable. If the design ever promotes to blocking (not
   planned), these paths become security-relevant (SP-2-R2).
8. **Kill switch (M5-R2, S2-R3 ratchet).** If the env var
   `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` is set, the hook exits 0
   immediately with no output (no advisory, no processing). The hook
   also honors a sentinel file at
   `$PROJECT_MEMORY/.build-routing-advisor-disabled` for environments
   where env vars are inconvenient. Both checks run before any other
   work.

   **Discoverability (S2-R3, M2-R4).** Whenever the kill switch is
   honored, the hook **overwrites** (not appends)
   `$PROJECT_MEMORY/build-routing-advisor-state.md` with a small
   fixed-schema block (Min-5; schema revised Min-8-R6):
   ```
   last-honored: YYYY-MM-DD
   fires-today: N
   fires-total: N
   last-advisory-at: <ISO-8601 timestamp or empty>
   last-advisory-fingerprint: <hash or empty>
   ```
   **State file schema (Min-8-R6).** The state file schema is **up to
   5 fixed lines**: `last-honored`, `fires-today`, `fires-total`,
   `last-advisory-at`, `last-advisory-fingerprint`. Prior text stating
   "fixed 3-line block" (rounds ≤5) is superseded here. Any future
   fields require a schema version bump.

   **Kill-switch dedup preservation (Min-1-R6).** When the kill switch
   is honored, the state file is NOT wiped wholesale — only the
   `last-honored` field is updated; dedup fields (`last-advisory-at`,
   `last-advisory-fingerprint`) and the `fires-today`/`fires-total`
   counters persist across toggle events so dedup windows and
   measurement are not reset by a brief disable/re-enable.
   `fires-today` is incremented each time the hook emits an advisory
   (reset on date change); `fires-total` is incremented on every
   advisory emission. Both fields are overwritten in place (not
   appended) so the file stays small. This gives users a concrete
   measurement of actual firing rate. State growth is bounded — the
   file remains ≤5 lines (Min-8-R6).

   **`fires-today` reset mechanism (Min-3-R6).** The hook reads the
   state file on every advisory candidate; if the date-stamp tracking
   (either `last-honored`'s date field or an internal last-advisory
   date derived from `last-advisory-at`) does not match today's local
   date, the `fires-today` counter resets to 0 before any increment.
   This reset is lazy — it happens on the next advisory-eligible
   invocation, not continuously — so the state file is not rewritten
   merely because a day turned over with no activity.

   **Reset precision (MIN-5-R7).** On each advisory-eligible
   invocation, the hook compares today's date against the MOST RECENT
   of (`last-honored` date, `last-advisory-at` date). If neither
   field exists OR the most recent date < today, `fires-today` resets
   to 0 before incrementing.

   **Auto-expiry (S2-R3, M3-R4).** If the sentinel file contains a
   `disabled-until: YYYY-MM-DD` line, the hook treats the switch as
   inactive on or after that date (parses line, compares to today in
   local time, re-enables automatically). Parse rules:
   - Timezones are ignored; the comparison uses local date (Min-2:
     date comparison is timezone-naive — no hour resolution. The
     hook README documents this).
   - If multiple `disabled-until:` lines are present, use the FIRST.
   - **Malformed or unparseable dates treat the kill switch as
     PERMANENTLY DISABLED** (fail-safe: honor the user's disable
     intent; never silently re-enable on parse error). When honoring
     a malformed date, the hook writes a line
     `disabled-until-parse-error: <raw value>` into the state file
     alongside `last-honored` for user visibility on typo'd dates.
   - **Matching-line definition (MIN-3-R7):** a matching line is one
     beginning with `disabled-until:` at column 0 — no leading
     whitespace, no comment skipping. Lines not matching
     `^disabled-until: ` (literal, with trailing space) are ignored.

   Users get a natural ratchet back to default-on when a valid
   future date is set and reached; malformed dates preserve the
   user's explicit disable.

**State file writes (MIN-4-R7, M-3-R8).** The hook writes the full
state block to `build-routing-advisor-state.md.tmp` then `mv`s it
into place atomically (per-process atomicity; cross-process is still
last-writer-wins as documented). Concurrent dispatches may race
counter increments by ±1 and may transiently flicker
`last-advisory-fingerprint`. Acceptable for warn-only operation.

**Dedup across parallel scouts (Min-9).** To prevent a single
parallel-scout dispatch batch from producing N identical advisories
in one breath: if the advisor emits an advisory and no active
pipeline marker is established within 5 minutes, subsequent
identical advisories in the same session are suppressed for 5
minutes. State is kept in
`$PROJECT_MEMORY/build-routing-advisor-state.md` (same file as the
kill-switch state), using additional fields (`last-advisory-at`,
`last-advisory-fingerprint`) overwritten in place. Suppressed
dispatches still increment `fires-total` (so measurement remains
honest) but do not emit to stderr.

**`/spec` marker writing (F1 — corrected).** `/spec`, `/debugging`,
and `/migrate` already write `.pipeline-active` with their respective
`skill:` values at entry and clear it at exit (see
`skills/spec/SKILL.md:276`, `skills/debugging/SKILL.md:295`,
`skills/migrate/SKILL.md:187`). The advisor's `.skill` presence check
automatically suppresses during any pipeline skill — **no source
changes to those skills are required**. The round-1 design stated
`/spec` would need updating; that premise was factually wrong and is
retracted here.

**F1 retraction + marker-write invariant reconciled (SIG-3-R7):** The
F1 retraction means no NEW marker-writing logic is required in
`/spec`, `/debugging`, or `/migrate`. If the
marker-write-before-first-dispatch integration test (see AC) discovers
a skill dispatches before its marker-write call, that is a
docstring-ordering fix within the existing `Pipeline-Active Marker`
section of that skill — reordering existing steps, not introducing
new behavior. The F1 retraction stands.

The Implement-required trigger (S3-R4) with single-phase disclaimers
plus advisory framing plus pipeline-skill-active suppression keeps
noise tolerable. The false-positive surface is larger than the four
examples originally enumerated (SP4) — reframing to ADVISORY,
requiring Implement, and suppressing during any pipeline skill are
what make the trigger sustainable.

## Acceptance criteria

- [ ] `getting-started/SKILL.md` has a section on build-shaped work routing with the anti-pattern list and `/build` redirect, framed as **write-time** guidance (M4)
- [ ] `hooks/build-routing-advisor.sh` hook implemented with Implement-required keyword check (S3-R4), single-phase disclaimer skip, `subagent_type` allowlist, and time-bounded/branch-scoped pipeline-skill-active suppression (three-condition: `.skill` known, fresh <24h, `.branch` matches current branch via `git branch --show-current` on BOTH sides)
- [ ] A real PreToolUse stdin payload is captured during implementation and committed to `hooks/tests/fixtures/agent-pretooluse-sample.json`; the hook extraction path is verified against this fixture in tests. Cover BOTH possible tool names (`Task` and `Agent`) — whichever Claude Code emits in this version is the registered matcher; the other is documented in the hook README as a fallback (S1, M3)
- [ ] **`$CLAUDE_SESSION_ID` availability probe (S1-R6).** During S1 fixture capture (the acceptance criterion for real PreToolUse payload), the hook must ALSO log `env | grep CLAUDE_SESSION_ID` output to verify `$CLAUDE_SESSION_ID` is exported to the PreToolUse subprocess environment. If it is NOT set/exported in the hook env, the detached-HEAD fallback and all `pipeline_id`-based checks are non-functional. In that case: replace the detached-HEAD fallback with a `.start_time`-based session-proxy check (same-minute marker write implies same session in practice) and document the reduced protection in `hooks/README.md`. An alternative: source `$PROJECT_MEMORY/.pipeline-active`'s full content and use the `pipeline_id` field alongside any Claude-Code-provided session tracking helper. Because `gate-ledger-guard.sh` already reads `$CLAUDE_SESSION_ID` successfully in this repo, the expected outcome is that the advisor can do the same; this AC exists to confirm that empirically rather than assume it.
- [ ] **If neither `Task` nor `Agent` is the hook matcher in this Claude Code version, `hooks/README.md` documents the fallback (grep on stdin `.tool` field) and the test suite covers it** (M1-R4)
- [ ] Hook matcher is explicitly registered: `build-routing-advisor` uses matcher `Task`; `gate-ledger-guard` runs on every PreToolUse (no matcher restriction). Both hooks execute on every Task dispatch, but their behavior is scoped — `gate-ledger-guard` early-exits on non-Write/Edit tools (O(1) cost). Combined budget applies (M5-R4) (Min-4)
- [ ] Test confirms advisor suppresses when an active marker exists with ANY recognized pipeline skill (`build`, `spec`, `debugging`, `migrate`). **No source changes to `/spec`, `/debugging`, or `/migrate` required** — those skills already write the marker (F1)
- [ ] Hook test asserts marker suppression requires ALL THREE of (`.skill` present and naming a known pipeline skill, `.start_time` within 24h, `.branch` equals current branch from `git branch --show-current`); any missing condition → advisory still emits (F1-R3 / F2-R3, M4-R4)
- [ ] Hook test suite with cases (grouped by coverage area for readability — Min-8; no change to coverage, presentation only):

  *Trigger classification:*
  - Single-category prompt (no advisory)
  - Implement+Design with total distinct ≥2 and no marker (advisory emitted)
  - Implement+Design+Ship (all three) without marker → advisory emitted
  - **MOTIVATING-EXAMPLE CANARY: prompt "spec + implement + PR" (verbatim from Part 1 line 16) → advisory emits** (S3-R6; guarantees the trigger catches its reason-for-existing — Design=1, Implement=1, Ship=1, total distinct=3)
  - **Design+Ship, NO Implement → no advisory** (S3-R4 Implement-required rule)
  - **Implement+Design, two distinct Implement words + one Design word → advisory emits** (S3-R4 / S3-R6)
  - **Implement+Ship, two distinct Ship words + one Implement word → advisory emits** (S3-R4 / S3-R6)
  - **Only one category matches (e.g. "implement and code and refactor") → no advisory** (S3-R6; Implement-required satisfied but Design/Ship both 0, so multi-category breadth fails — replaces prior single-hit-per-category test whose framing conflicts with the new total-distinct rule)
  - **Substring decoy: prompt contains `planning`, `commitment`, `shipping`, `codebase` only → no category match, no advisory** (S2-R2)
  - Trigger prompt with a single-phase disclaimer phrase (e.g. "design only") → no advisory (S2)
  - Trigger prompt with non-`general-purpose` `subagent_type` → no advisory (SP2)

  *Marker suppression:*
  - Implement+Design trigger with `skill: "build"` marker active, fresh, branch matches (no advisory)
  - Implement+Ship trigger with `skill: "spec"` marker active, fresh, branch matches (no advisory)
  - Implement+Design or Implement+Ship with `skill: "debugging"` or `"migrate"` marker active, fresh, branch matches (no advisory, F1)
  - Implement+Ship trigger with **stale** marker (`start_time > 24h` old) → advisory STILL emitted (S3, M3-R2, M4-R4)
  - **Trigger with marker from a DIFFERENT branch (fresh, valid `.skill`, within 24h) → advisory STILL emitted** (F1-R3 / F2-R3)
  - **6h-old marker with MISMATCHED branch → advisory STILL emitted** (Min-3, closes zombie-marker window under branch-match check)
  - **Detached-HEAD symmetric fallback: marker `.branch=""` (written under detached HEAD) AND hook also sees detached HEAD (`branch --show-current` returns empty) AND `.pipeline_id == $CLAUDE_SESSION_ID` → marker active, advisory suppressed** (S1-R4)
  - **Asymmetric detached: marker `.branch=""` AND hook sees non-empty branch (or vice versa) → advisory STILL emits** (S1-R4 fail-open)
  - **Branch-switch-mid-pipeline: `/build` with a `/checkpoint` restore that changes branch mid-run — advisory fires on post-checkout dispatches where current branch ≠ marker `.branch`; behavior is intentional (warn-only, kill-switch available)** (M-2-R8)

  *Graceful degradation:*
  - Malformed JSON → graceful exit 0
  - Missing/non-executable hook script → tool call proceeds (M5)

  *Kill switch:*
  - **Kill switch: `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` → hook exits 0 silently even on Implement+Design+Ship prompts** (M5-R2)
  - **Kill switch: sentinel file `$PROJECT_MEMORY/.build-routing-advisor-disabled` present → hook exits 0 silently** (M5-R2)
  - **Kill-switch discoverability: when honored, `build-routing-advisor-state.md` is OVERWRITTEN with the fixed-schema block (`last-honored`, `fires-today`, `fires-total`; no append growth, no duplicate entries)** (S2-R3, M2-R4, Min-5)
  - **Firing counters: on each advisory emission, `fires-today` and `fires-total` increment; `fires-today` resets on date change** (Min-5)
  - **Kill-switch auto-expiry: sentinel file with `disabled-until: YYYY-MM-DD` in the past → advisor re-enables and emits normally** (S2-R3)
  - **Kill-switch malformed-date fail-safe: sentinel file with unparseable `disabled-until:` value → advisor treats switch as PERMANENTLY DISABLED (no silent re-enable)** (M3-R4)
  - **Kill-switch multiple `disabled-until:` lines → FIRST line wins** (M3-R4)

  *Dedup:*
  - **Dedup: if the advisor emits and no active pipeline marker is established within 5 minutes, subsequent identical advisories in the same session are suppressed for 5 minutes. State is kept in `$PROJECT_MEMORY/build-routing-advisor-state.md` (same file as kill-switch). Test: two back-to-back trigger dispatches in one batch produce exactly ONE advisory, not N** (Min-9)

  *Dogfood:* (see dedicated dogfood ACs below)
- [ ] Hook test asserts that the ADVISORY string is written to stderr (captured via `2>&1` redirection in the test harness) — programmatic, not manual (M1-R2)
- [ ] At least one skill-selection/routing eval (e.g. under `skills/getting-started/evals/` or a comparable location) verifies the model prefers `/build` over raw dispatch for build-shaped prompts; **N ≥ 10 prompts; reported pass rate is the median of 3 runs; pass threshold ≥ 8/10 on the median** for the eval to count as satisfying the AC (SP-3-R2, Min-1). **If the routing eval reports <8/10 median after two wording iterations of Part 1, ESCALATE to the user with the eval transcript before landing. Do NOT loop-tune Part 1 wording indefinitely and do NOT silently weaken the ≥8/10 threshold** (F3-R5). **Iteration calibration (Min-6-R6):** both wording iterations MUST use a FRESH run of 3 seeds. If variance is >2 points between seeds within a single iteration, expand to 5 seeds before interpreting the median — this bounds interpretation risk from a low-N sample.
- [ ] **Part 1 addition to `getting-started/SKILL.md` is ≤ 150 tokens (approximately 20–25 lines); if longer, extract verbose examples to a linked reference doc and keep the inline section terse** (S4-R3). **Compression guidance (Min-4-R6):** if the three beats (STOP / `/build`'s job / COMBINATION) cannot fit under 150 tokens while keeping the 5-bullet anti-pattern list readable, move the 5-bullet list to the linked sub-doc and keep only the first three beats inline. This is the recommended compression path.
- [ ] **Dogfood (pipeline): during implementation, run `/build` on a small real change and assert 0 advisories are emitted during normal `/build` operation** (Min-6)
- [ ] **Marker-write-before-first-dispatch invariant (S2-R6).** Integration test: dispatch `/build` end-to-end on a small real change (reusable with the dogfood AC) and assert that NO advisory is emitted from Phase 1 Step -1 onward, including any dispatches in Phase 1 Step 0 (pre-existing doc detection) or Phase 2 plan-writer dispatch. If any Phase 1 subagent dispatch occurs before the marker write completes, the test fails and `/build` Step -1 must be reordered to write the marker FIRST, no exceptions. Mirror this invariant for `/spec`, `/debugging`, `/migrate` — their marker-write must precede any subagent dispatch.
- [ ] **Dogfood (non-pipeline, S2-R4): during implementation, run a representative NON-PIPELINE session (recon or audit/review on this codebase — no `/build`/`/spec`/`/debugging`/`/migrate` active) and count advisory emissions. Cap: ≤2 advisories per hour of active dispatch activity. If exceeded, tighten trigger (verify S3-R4 Implement-required is working first; if still exceeded, reconsider the total-distinct ≥2 threshold, e.g. raise to ≥3)**
- [ ] **Advisory copy is ≤ 2 lines** (S2-R4, cut from prior 3-line form to reduce per-firing token cost)
- [ ] **Combined PreToolUse hook overhead per Task dispatch (`build-routing-advisor` + `gate-ledger-guard`) MUST be ≤ 200ms P95 measured over ≥20 Task dispatches in a single `/build` run; if exceeded, profile and optimize the advisor (most-common suppression path must be fast)** (M5-R4, threshold upgrade from observational; M-5-R8 clarifies measurement protocol)
- [ ] `hooks/README.md` documents the new hook: matcher name, JSON extraction path (plus `.tool`-field fallback per M1-R4), allowlist, suppression rules (including symmetric branch-equality check and detached-HEAD `.pipeline_id` fallback), and graceful-degradation behavior. **Also (Min-5-R6):** document `gate-ledger-guard`'s null-matcher registration (runs on every PreToolUse) in the SAME document so both hooks' matcher choices are documented side-by-side for reader parity.
- [ ] Hook is registered as warn-only (exits 0, no blocking) with advisory (not accusatory) copy (M2)

## Honest about limits

Even both parts combined won't protect against a determined Claude that rationalizes "this is different, I'll just dispatch raw agents this one time." The only mechanical protection that works there is the user catching it. No hook can substitute for that. What this issue does provide:

- A prompt-level guardrail that makes the anti-pattern explicit
- An ambient warning that creates visibility without friction
- A shared vocabulary (`build-shaped work`) for the failure mode

**Scope decision: ship Part 1 + Part 2 together (F1-R5).** An earlier
iteration of this design considered shipping Part 1 alone and
deferring Part 2 until empirical evidence of need from the routing
eval. That option was rejected in favor of shipping both parts
together: Part 1 provides write-time guidance, Part 2 provides
retrospective signal, and the two complement each other rather than
Part 2 being strictly downstream of Part 1. If post-launch telemetry
shows Part 2's cost exceeds value, removal is a clean follow-up (the
hook is self-contained and disabling it affects no other system).

**Self-firing during bootstrap (F2-R5).** During the implementation of
this very hook, subagent dispatches with prompts like "Implement the
advisor and open a PR" WILL legitimately trip the trigger (Implement
≥1 + Ship ≥1 + total distinct ≥2 via e.g. implement/open/merge/PR). This is
expected and acceptable: (a) the implementer dispatches are few (one
or two scouts during bootstrap); (b) this IS build-shaped work and
SHOULD have routed through `/build` per the policy the hook enforces;
(c) the advisory is retrospective — the dispatch still runs. The
implementer is instructed to run `/build` on a small real change
AFTER the hook lands for the dogfood AC, not during bootstrap. The
bootstrap trigger events are noted and expected, not counted against
the non-pipeline ≤2/hr dogfood cap.

**Part 2 is observational telemetry, not in-flight shaping (S3-R3).**
The advisor fires AFTER the subagent dispatch has been committed by
the parent agent; PreToolUse stderr reaches the parent only on the
subsequent turn. It cannot block, rewrite, or reshape the dispatch
decision in-flight. Its value is retrospective signal — for the
parent agent's next turn and for the user reading the transcript —
not behavioral shaping at authoring time. Write-time behavior change
depends on Part 1 (the `getting-started/SKILL.md` guidance), which
is read before the dispatch is authored. Do not read Part 2 as an
in-flight guardrail.

**Not a peer structural defense to #168 (S3-R2).** Unlike #168's
`gate-ledger-guard` — which uses discrete verifiable signals with a
documented 0% false-positive rate — this advisor is heuristic. The
closest analog is a linter warning, not a hard gate. Its value is
ambient awareness and a shared vocabulary, not enforcement. Consumers
who find it too noisy should disable it via the kill switch (see
M5-R2 above) rather than tune the triggers further. The "Problem"
section's grouping alongside #169/#170 reflects that all three
address post-hoc gaps; it is not a claim of equivalent rigor to #168.

**Performance budget (SP-1-R2).** The hook fires on every Task
PreToolUse (~50–90× per `/build` run). Target per-invocation cost
<= 50ms (jq + grep + test scripts). Implementers should profile and
keep the script lean — large regex engines and subprocess forks will
accumulate.

**Combined hook overhead (Min-4, M5-R4 threshold).**
`gate-ledger-guard` has no matcher restriction, so it runs on every
Task PreToolUse already. The 50ms target applies to
`build-routing-advisor` in isolation. **The combined PreToolUse
overhead per Task dispatch (`build-routing-advisor` +
`gate-ledger-guard`) MUST be ≤ 200ms measured empirically** (upgraded
from observational to hard threshold). Implementers measure combined
cost during a full `/build` run; if exceeded, profile and optimize
the advisor — the most-common path (suppression when marker is
active) must be fast. Document measured numbers in `hooks/README.md`.

**Rejected alternative — PR-creation hook (Min-7).** A PR-creation
hook that checks for a `gate-ledger-id` trailer (discrete signal,
#168-style) was considered. It was rejected because it detects the
failure post-merge rather than at authoring time, and the
"build-shaped work" incident this issue targets happened at dispatch
time, not merge time. The PR-creation hook is tracked as a separate
follow-up (see Related).

## Related

- #168 — gate ledger with enforcement hook (shipped — protects within /build)
- #169 — subagent evidence verification hook (tracked)
- #170 — post-push CI status hook (tracked)
- #173 — skill description + reference extraction rollout (tracked)
