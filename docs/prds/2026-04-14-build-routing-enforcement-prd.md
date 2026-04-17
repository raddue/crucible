---
ticket: "#174"
title: "Build Routing Enforcement — Product Requirements"
date: "2026-04-14"
source: "build"
design_doc: "docs/plans/2026-04-14-build-routing-enforcement-design.md"
---

# Build Routing Enforcement — Product Requirements

## 1. Problem Statement

When an AI agent needs to build and ship a feature, it should use the project's established pipeline tool (`/build`), which includes automatic quality checks and an audit trail. However, agents can bypass this entirely by receiving informal "just do it" instructions that send them straight to writing code and opening a pull request — skipping all safety gates. This feature adds two layers of protection that catch that shortcut before or shortly after it happens.

## 2. User Stories / Use Cases

**As a project maintainer**, I want agents to be reminded at the moment they are about to do "design + implement + merge" as one freeform task, so that I know quality gates were not silently skipped.

**As a developer reviewing the session transcript**, I want to see a visible advisory when an agent dispatch looks like it should have gone through `/build`, so that I can investigate whether proper gates ran.

**As a user who finds the advisory noisy**, I want a simple kill switch (an environment variable or a file) to silence warnings for a session or a date range, so that legitimate exceptions don't pollute my output.

**As a user running a legitimate single-phase task** (code review only, design only, recon only), I want the system to recognize my task is not build-shaped and stay silent, so that I don't get false warnings.

**As a user running an active `/build` pipeline**, I want dispatches made within that pipeline to be automatically recognized as sanctioned and suppressed from triggering warnings, so that normal operation is noise-free.

**As a stakeholder auditing AI activity**, I want firing counters (daily and all-time) recorded automatically, so that I can measure how often the routing advisory fires in practice.

## 3. Requirements

### Functional

- The system MUST add written guidance to the agent's startup instructions that explicitly names the "design + implement + merge in one freeform dispatch" pattern as an anti-pattern and directs agents to `/build` instead.
- The guidance MUST be placed alongside existing skill-selection instructions so it is read in context.
- The system MUST register a background check that inspects each new agent dispatch for keywords indicating combined design, implementation, and shipping intent.
- The check MUST fire an advisory to the transcript only when all of: at least one implementation-intent word is present, and at least one design-intent or shipping-intent word is present, and the total number of distinct matched keywords is two or more.
- The check MUST stay silent when a single-phase disclaimer phrase appears in the prompt (e.g., "design only," "review only," "recon only").
- The check MUST stay silent when the dispatch is not a general-purpose agent type (specialty agents are exempt).
- The check MUST stay silent when an active pipeline is detected on the current branch that was started within the last 24 hours.
- The advisory text MUST be two lines or fewer and use the phrase "build-shaped" for searchability.
- The check MUST exit without blocking — it warns only; the dispatch always proceeds.
- A kill switch MUST be available via environment variable (`CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1`) or a sentinel file, either of which silences all warnings.
- The kill switch MUST support an optional expiry date; after that date the switch deactivates automatically (a malformed date keeps the switch permanently on as a safe default).
- A state file MUST track daily and all-time advisory firing counts, the last advisory timestamp, and kill-switch activity; this file MUST stay at or under five lines.
- Identical back-to-back advisories within a five-minute window MUST be deduplicated to one, to prevent a batch of parallel dispatches from flooding the transcript.

### Non-Functional

- The background check MUST add no more than 200 ms combined overhead (with existing hooks) per agent dispatch, measured at the 95th percentile over at least 20 dispatches.
- Keyword matching MUST use word-boundary rules so partial-word matches (e.g., "planning" matching "plan") do not trigger false positives.
- Keyword matching MUST be case-insensitive.
- The guidance added to startup instructions MUST be at or under 150 tokens to limit recurring session cost.
- The check MUST degrade gracefully: malformed input, missing utilities, or a non-executable hook must all result in silent exit (no crash, no block).
- Pipeline-active detection MUST require all three conditions simultaneously (known pipeline skill, started within 24 hours, current branch matches marker) to prevent stale or cross-branch markers from suppressing warnings.

## 4. Scope

- Written anti-pattern guidance added to the agent startup skill file under existing skill-selection headings.
- A new background hook (`build-routing-advisor`) registered on agent dispatch events.
- Keyword classification logic with Implement-required trigger and multi-category breadth requirement.
- Single-phase disclaimer detection and subagent-type allowlist.
- Pipeline-active suppression using branch-scoped, time-bounded marker detection.
- Kill switch via environment variable and/or sentinel file, with optional expiry date.
- Firing-rate counters and dedup state persisted to a small fixed-schema state file.
- A test suite covering trigger classification, marker suppression, graceful degradation, kill-switch behavior, and dedup.
- A routing evaluation (10+ prompts, 3-run median, pass threshold ≥ 8/10) confirming agents prefer `/build` over raw dispatch for build-shaped prompts.
- A dogfood run: a real `/build` invocation confirming zero advisories during normal pipeline operation.
- Documentation in `hooks/README.md` covering matcher, suppression rules, kill switch, and graceful degradation.

## 5. Out of Scope

- Blocking agent dispatches outright — this feature is advisory only; no dispatch is prevented.
- A pull-request creation hook that checks for a gate-ledger trailer (tracked as a separate follow-up).
- Changes to the `/spec`, `/debugging`, or `/migrate` skills — those already write the pipeline-active marker and require no modification.
- Automated continuous enforcement of the 150-token budget in CI (tracked as a possible follow-up if drift is observed).

## 6. Success Metrics

- Feature is successful when a routing evaluation of 10+ build-shaped prompts shows agents choosing `/build` over raw dispatch at a median rate of 8 out of 10 or better across 3 independent runs.
- Feature is successful when a complete `/build` run on a real change produces zero advisory emissions from the hook, confirming normal pipeline operation is noise-free.
- Feature is successful when a non-pipeline session (recon or audit work, no active pipeline) produces no more than 2 advisories per hour of active dispatch activity.
- Feature is successful when the advisory text appears in the session transcript and is searchable by the phrase "build-shaped."
- Feature is successful when the kill switch, when activated, produces zero advisory output and updates the state file correctly.

## 7. Technical Notes

The feature is implemented in two complementary parts: written guidance inserted into the agent's startup file (which shapes behavior before a dispatch is authored), and a lightweight shell hook that inspects each dispatch after the fact and emits a transcript warning if needed. The hook uses word-boundary keyword matching and a pipeline-active marker file to keep false positives low. Both parts are self-contained and can be disabled or removed without affecting any other system.

## 8. Dependencies

- The existing pipeline-active marker written by `/build`, `/spec`, `/debugging`, and `/migrate` — the hook reads this file to determine whether a sanctioned pipeline is running. No changes to those skills are required.
- Standard shell utilities (`jq`, `grep`, `git`) available in the hook execution environment.
- The Claude Code hook registration mechanism (PreToolUse on `Task` dispatches).
