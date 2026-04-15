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

### Part 2: warn-only hook (soft structural)

PreToolUse hook registered on the subagent-dispatch tool. The exact
matcher name varies by Claude Code version — known values are `Task`
and `Agent`. The hook MUST register a matcher distinct from
`gate-ledger-guard` (which uses `Write|Edit`); see M3. The discovery
step in S1 below pins the correct matcher.

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
4. Classifies the prompt against three keyword categories:
   - Design: `design|spec|plan`
   - Implement: `implement|build|code|create|refactor`
   - Ship: `PR|commit|merge|push|land|ship`

   Trigger fires if **any 2 of the 3** categories match (S2). The prior
   3-AND rule was too tight; design-skipping (implement+ship, no design)
   is the more common build-shaped failure.
5. Checks the pipeline-active marker (`$PROJECT_MEMORY/.pipeline-active`
   or equivalent). Treat marker as **active** ONLY when ALL of:
   - File exists and is parseable JSON
   - `.skill` field is present and non-empty (any pipeline skill —
     `build`, `spec`, or future additions — suppresses) (SP1)
   - `.start_time` is within the last 8 hours (S3)
   - `.pipeline_id` equals `$CLAUDE_SESSION_ID` (S3)

   Otherwise the marker is treated as absent — a stale or cross-session
   marker does NOT suppress the advisory.
6. If the 2-of-3 trigger fires AND no active pipeline marker, emit to
   stderr (M2, advisory reframing):
   ```
   ADVISORY: This dispatch looks build-shaped. If single-phase, ignore.
   If spanning design -> implement -> ship, prefer /build (or /spec
   then /build) for gate coverage.
   ```
7. Always exits 0 (warn only, never block). If the hook script is
   missing or non-executable, Claude Code's normal hook dispatch
   behavior applies — the tool call proceeds unimpeded (M5 graceful
   degradation).

**`/spec` marker writing (SP1).** `/spec` currently dispatches
build-shaped scouts (3 per ticket × N tickets) without writing
`.pipeline-active`, which would produce cascading false-positive
advisories under the looser 2-of-3 trigger and train users to ignore
stderr — the exact failure mode we are trying to prevent. This design
REQUIRES that `/spec` be updated to write `.pipeline-active` with
`skill: "spec"` at entry and clear it at exit, mirroring `/build`'s
pattern. The advisor then suppresses for any active pipeline skill.

The 2-of-3 trigger with single-phase disclaimers plus advisory framing
plus pipeline-skill-active suppression keeps noise tolerable. The
false-positive surface is larger than the four examples originally
enumerated (SP4) — reframing to ADVISORY and suppressing during any
pipeline skill are what make the looser trigger sustainable.

## Acceptance criteria

- [ ] `getting-started/SKILL.md` has a section on build-shaped work routing with the anti-pattern list and `/build` redirect, framed as **write-time** guidance (M4)
- [ ] `hooks/build-routing-advisor.sh` hook implemented with 2-of-3 keyword check, single-phase disclaimer skip, `subagent_type` allowlist, and time-bounded/session-scoped pipeline-skill-active suppression
- [ ] A real PreToolUse stdin payload is captured during implementation and committed to `hooks/tests/fixtures/agent-pretooluse-sample.json`; the hook extraction path is verified against this fixture in tests. Cover BOTH possible tool names (`Task` and `Agent`) — whichever Claude Code emits in this version is the registered matcher; the other is documented in the hook README as a fallback (S1, M3)
- [ ] Hook matcher is explicitly registered and does NOT overlap with `gate-ledger-guard` (Write|Edit) (M3)
- [ ] `/spec` writes `.pipeline-active` with `skill: "spec"` at entry and clears on exit; test confirms advisor suppresses during `/spec` runs (SP1)
- [ ] Hook test suite with cases:
  - Single-category prompt (no advisory)
  - 2-of-3 with `skill: "build"` marker active, fresh, same session (no advisory)
  - 2-of-3 with `skill: "spec"` marker active, fresh, same session (no advisory, SP1)
  - 2-of-3 with no marker (advisory emitted)
  - 2-of-3 with **stale** marker (`start_time` >24h old) → advisory STILL emitted (S3)
  - 2-of-3 with marker from a different `pipeline_id` → advisory STILL emitted (S3)
  - 2-of-3 with a single-phase disclaimer phrase (e.g. "design only") → no advisory (S2)
  - 2-of-3 with non-`general-purpose` `subagent_type` → no advisory (SP2)
  - 3-of-3 without marker → advisory emitted
  - Malformed JSON → graceful exit 0
  - Missing/non-executable hook script → tool call proceeds (M5)
- [ ] Stderr-visibility manual verification: implementer confirms the ADVISORY string actually surfaces to the operating agent's context during a real dispatch (M1)
- [ ] At least one skill-selection/routing eval (e.g. under `skills/getting-started/evals/` or a comparable location) verifies the model prefers `/build` over raw dispatch for build-shaped prompts (SP3)
- [ ] `hooks/README.md` documents the new hook: matcher name, JSON extraction path, allowlist, suppression rules, and graceful-degradation behavior
- [ ] Hook is registered as warn-only (exits 0, no blocking) with advisory (not accusatory) copy (M2)

## Honest about limits

Even both parts combined won't protect against a determined Claude that rationalizes "this is different, I'll just dispatch raw agents this one time." The only mechanical protection that works there is the user catching it. No hook can substitute for that. What this issue does provide:

- A prompt-level guardrail that makes the anti-pattern explicit
- An ambient warning that creates visibility without friction
- A shared vocabulary (`build-shaped work`) for the failure mode

## Related

- #168 — gate ledger with enforcement hook (shipped — protects within /build)
- #169 — subagent evidence verification hook (tracked)
- #170 — post-push CI status hook (tracked)
- #173 — skill description + reference extraction rollout (tracked)
