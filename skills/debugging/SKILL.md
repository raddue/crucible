---
name: debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional — the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** — Which debugging phase you're in
2. **Hypothesis status** — Current hypothesis being tested (or "forming hypothesis")
3. **What just completed** — What the last agent reported (investigation findings, fix results)
4. **What's being dispatched next** — What you're about to do and why
5. **Cycle count** — Which hypothesis cycle you're on (cycle 1, cycle 2, etc.)

**After compaction:** Re-read the hypothesis log from disk and output current status before continuing.

**This requirement exists because:** Debugging sessions can involve multiple investigation rounds and fix attempts. Without narration, the user has no visibility into which hypotheses have been tried, what evidence was found, or why the orchestrator is pursuing a particular path.

**Execution model:** The orchestrator dispatches all investigation and implementation to subagents. The orchestrator NEVER reads code, edits files, or runs tests directly. It forms hypotheses, dispatches work, and makes decisions based on subagent reports.

**Depth principle:** When in doubt, dispatch MORE investigation agents, not fewer. A bug that looks simple from the surface often has a complex root cause. Spinning up 4-6 focused investigators in parallel costs minutes; missing the root cause costs hours.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't dispatched Phase 1 investigation and received findings back, you cannot propose fixes. If you haven't received a synthesis report, you cannot form a hypothesis. If you haven't formed a hypothesis, you cannot dispatch implementation.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Manager wants it fixed NOW (systematic is faster than thrashing)

---

## The Orchestrator-Subagent Debugging Workflow

All investigation and implementation is delegated to subagents via the Agent tool. The orchestrator handles hypothesis formation, dispatch decisions, and escalation -- nothing else.

### Subagent Model Selection

| Phase | Agent | Model | Rationale |
|-------|-------|-------|-----------|
| Phase 1 | Error Analysis | Opus | Deep code reading and call-chain tracing |
| Phase 1 | Change Analysis | Opus | Cross-file diff analysis |
| Phase 1 | Evidence Gathering | Opus | Multi-component data flow tracing |
| Phase 1 | Reproduction | Opus | Complex reproduction requires reasoning |
| Phase 1 | Deep Dive (any) | Opus | Specialized investigation |
| Synthesis | Consolidation | Sonnet | Summarization of existing findings |
| Phase 2 | Pattern Analysis | Opus | Exhaustive comparison requires depth |
| Phase 4 | Implementation | Opus | TDD + root cause fix |
| Phase 5 | Red-team | Opus | Adversarial analysis |
| Phase 5 | Code review | Opus or Sonnet | Lead decides by fix complexity |

### Workflow Overview

```
Bug reported / test failure / unexpected behavior
    |
    v
Orchestrator: Parse initial context (error message, failing test, user description)
    |
    v
Phase 0: Load codebase context (crucible:cartographer)
    |
    v
Phase 1: Dispatch 3-6 parallel investigation subagents
    |  +-- Error Analysis agent (always)
    |  +-- Change Analysis agent (always)
    |  +-- Evidence Gathering agent (conditional -- multi-component systems)
    |  +-- Reproduction agent (conditional -- intermittent/unclear bugs)
    |  +-- Deep Dive agents (conditional -- 1-2 focused on specific subsystems)
    |
    v
Synthesis agent: Consolidate all Phase 1 findings -> concise root-cause analysis
    |
    v
Phase 2: Pattern Analysis agent (skipped if synthesis identified obvious root cause)
    |
    v
Phase 3: Orchestrator forms hypothesis (no subagent -- lightweight decision-making)
    |
    v
Phase 3.5: Hypothesis Red-Team (crucible:quality-gate on hypothesis)
    |  -> Survives? Proceed to Phase 4.
    |  -> Torn apart? Reform hypothesis or loop back to Phase 1.
    |
    v
Phase 4: Implementation agent (TDD: failing test, fix, verify)
    |
    v
Orchestrator: Verify fix -> Success? Phase 5. Failed? Cleanup, log, loop back.
    -> 3 failures? Escalate to user.
    |
    v
Phase 5: Red-team the fix (crucible:red-team) + Code review (crucible:code-review)
    |
    v
Done.
```

---

### Phase 0: Load Codebase Context

**Before any investigation dispatch,** use `crucible:cartographer` (load mode) to pull module context for the area being investigated. If module files exist, paste them into every investigator's prompt so agents start with structural knowledge instead of wasting turns rediscovering the codebase.

If cartographer data doesn't exist for the relevant area, dispatch a quick Explore agent (`subagent_type="Explore"`, model: haiku) to map the relevant directories and note key files. Include its findings in investigator prompts.

### Domain Detection

Check the project's CLAUDE.md for a `## Debugging Domains` table:

```markdown
| Signal | Domain | Skills | Context |
|--------|--------|--------|---------|
| file paths contain `/UI/`, `USS`, `VisualElement` | ui | mockup-builder, mock-to-unity, ui-verify | docs/mockups/ |
| error mentions `GridWorld`, `Tile`, `hex` | grid | - | grid system architecture |
```

**Signal types:** File path patterns (regex against paths in error/stack trace), error message patterns (regex against error text), user description keywords. Evaluate signals in order; load context for all matching domains.

**When domain is detected:**
- Auto-load referenced skills' SKILL.md into investigator prompts (see Domain Context section in investigator-prompt.md)
- Add a domain-specific investigator to Phase 1
- Give Phase 4 implementer domain skill context
- Load files from the Context column

**When no domain table exists:** Proceed normally. Domain detection is opt-in.

**When a referenced skill doesn't exist:** Log a warning and proceed without domain enrichment. Never fail on missing config.

---

### Phase 1: Investigation (Parallel Subagent Dispatch)

**Prompt template:** `./investigator-prompt.md`

Dispatch 3-6 investigation subagents in parallel using the Agent tool in a single message. All subagents use `subagent_type="general-purpose"`, `model: opus`. Pass all known context (error messages, stack traces, file paths, user description, and cartographer module context from Phase 0) verbatim to each agent -- do not make them search for context you already have.

**Bias toward MORE agents, not fewer.** Each investigator is cheap. Missing a root cause is expensive. When in doubt about whether to dispatch an additional agent, dispatch it.

**Always dispatch:**

1. **Error Analysis Agent** -- Read error messages, stack traces, and logs. Identify the exact failure point, error codes, and what the error is telling us. Trace the call chain backward to the originating bad value.

2. **Change Analysis Agent** -- Check recent changes via git diff, recent commits, new dependencies, config changes, and environmental differences. Identify what changed that could cause this.

**Conditionally dispatch (lean toward dispatching):**

3. **Evidence Gathering Agent** -- For multi-component systems (CI pipelines, API chains, layered architectures). Add diagnostic instrumentation at component boundaries. Log what enters and exits each component. Run once, report where the data flow breaks.

4. **Reproduction Agent** -- For intermittent, timing-dependent, or unclear bugs. Attempt to reproduce consistently. Document exact steps, frequency, and conditions. If not reproducible, gather more data rather than guessing.

5. **Deep Dive Agent(s)** -- For bugs touching multiple subsystems, dispatch 1-2 additional agents each focused on a specific subsystem or code path. Give each a narrow scope: "Investigate how [specific subsystem] handles [specific scenario]." These agents read deeply into a single area rather than scanning broadly.

6. **Dependency/Environment Agent** -- For bugs that might be caused by version mismatches, missing registrations, configuration drift, or framework behavior changes. Check DI registrations, package versions, framework release notes, and environment state.

#### Phase 1 Dispatch Heuristics

| Bug Characteristics | Agents to Dispatch |
|--------------------|--------------------|
| Test failure with clear stack trace | Error + Change + Deep Dive (on the failing subsystem) |
| Vague "something broke" across multiple systems | All six agent types |
| Intermittent / timing-dependent issue | Error + Change + Reproduction + Deep Dive |
| Multi-layer system failure (CI, API chain) | Error + Change + Evidence Gathering + Deep Dive per layer |
| Performance regression | Error + Change + Evidence Gathering + Deep Dive (hot path) |
| "It worked yesterday" | Error + Change + Dependency/Environment |
| Framework/library update broke things | Error + Change + Dependency/Environment + Deep Dive |

#### Context Self-Monitoring (All Phase 1 Agents)

Every investigation subagent prompt MUST include the context self-monitoring block from `./investigator-prompt.md`. Investigators reading large codebases are prime candidates for context exhaustion. If an agent hits 50%+ utilization with significant investigation remaining, it must report partial findings immediately rather than silently degrading.

---

### Synthesis: Consolidate Findings

**Prompt template:** `./synthesis-prompt.md`

After all Phase 1 agents report back, dispatch a single Synthesis agent (model: sonnet) that receives all Phase 1 reports verbatim.

**Trust-but-verify:** The synthesis agent does NOT take investigator claims at face value. It cross-references findings between agents, flags contradictions, and identifies claims that lack concrete evidence (file paths, line numbers, stack traces). Speculative findings are downgraded. Concrete artifacts outrank plausible theories.

**The Synthesis agent produces:**
- A 200-400 word root-cause analysis
- Ranked list of likely causes (most to least probable), each with evidence strength rating
- Cross-references between agent findings (where they agree, where they contradict)
- Identified unknowns or gaps in evidence
- Recommendation: is the root cause obvious, or is pattern analysis needed?

**Skip-ahead rule:** If all Phase 1 agents converge on the same root cause with concrete evidence (not just speculation) and the Synthesis agent confirms it as obvious, the orchestrator may skip Phase 2 and proceed directly to Phase 3 (hypothesis formation).

---

### Phase 2: Pattern Analysis (Skippable)

**Prompt template:** `./pattern-analyst-prompt.md`

Dispatch a single Pattern Analysis agent that receives the synthesis report.

**The Pattern Analysis agent:**
1. Finds working examples of similar code/patterns in the same codebase
2. Compares working examples against the broken code exhaustively
3. Lists every difference, however small -- does not assume "that can't matter"
4. Identifies dependencies, config, environment, and assumptions
5. Reports back with specific differences and their likely relevance

**When to skip:** The orchestrator skips Phase 2 when the synthesis report identifies an obvious root cause with high confidence (all investigation agents agree, clear evidence chain).

---

### Phase 3: Hypothesis Formation (Orchestrator Only -- No Subagent)

This phase stays local to the orchestrator. No subagent dispatch.

The orchestrator:
1. Reads the synthesis report (and Phase 2 report if it was dispatched)
2. Forms a single, specific, testable hypothesis: "I think X is the root cause because Y"
3. Checks the hypothesis log -- do not repeat a hypothesis that already failed
4. Logs the hypothesis before dispatching Phase 4

**Hypothesis discipline:**
- Be specific, not vague. "The null reference is caused by X not being initialized before Y calls it" -- not "something with initialization."
- One hypothesis at a time. Do not bundle multiple theories.
- If you cannot form a hypothesis from the reports, dispatch more investigation -- do not guess.

#### Hypothesis Log Format

Maintain a running log across cycles:

```
## Cycle 1
- Hypothesis: "[specific hypothesis]"
- Based on: [which reports informed this]
- Result: [filled in after Phase 4 completes]

## Cycle 2
- Hypothesis: "[specific hypothesis]"
- Based on: [which reports informed this]
- Result: [filled in after Phase 4 completes]
```

---

### Phase 3.5: Hypothesis Red-Team

Before dispatching the Phase 4 implementer, invoke `crucible:quality-gate` on the hypothesis with artifact type "hypothesis".

The quality gate challenges:
- Does the hypothesis explain ALL symptoms, or just some?
- Could the root cause be upstream of what the hypothesis targets?
- If this hypothesis is correct, what other symptoms should we expect? Do we see them?
- Has this pattern been tried and failed before? (check hypothesis log and cartographer landmines for `dead_ends`)

**If hypothesis survives:** Proceed to Phase 4.
**If hypothesis is torn apart:** Reform the hypothesis or dispatch additional investigation (back to Phase 1) without wasting a full TDD cycle.

---

### Phase 4: Implementation (Single Subagent -- TDD)

**Prompt template:** `./implementer-prompt.md`

Dispatch a single Implementation agent that receives:
- The hypothesis (verbatim)
- Relevant file paths identified during investigation
- Project conventions and test standards
- The hypothesis log (so it knows what was already tried)

**The Implementation agent follows strict TDD:**
1. Write a failing test that reproduces the bug per the hypothesis
2. Run the test -- verify it fails for the expected reason
3. Implement the minimal fix addressing the root cause
4. Run the test -- verify it passes
5. Run the broader test suite -- verify no regressions
6. Report back with a structured Implementation Report

**Implementation discipline:**
- ONE change at a time. No "while I'm here" improvements.
- No bundled refactoring.
- Fix the root cause, not the symptom.
- Uses `crucible:test-driven-development` for proper TDD workflow.

---

### Phase 5: Red-Team and Code Review (Post-Fix Quality Gate)

After Phase 4 succeeds (fix works, tests pass, no regressions), the orchestrator runs two quality gates before declaring done:

**Step 1: Red-team the fix** — Invoke `crucible:red-team` against the changed code. The red-team skill dispatches a fresh Devil's Advocate to adversarially review the fix for:
- Edge cases the fix doesn't handle
- New failure modes introduced by the fix
- Assumptions that could break under different conditions
- Regression risks not covered by the test

If red-teaming finds Fatal or Significant issues, dispatch a fix agent to address them, then re-run red-team per the standard red-team loop. Do NOT skip this — a fix that introduces new risks is not done.

**Step 2: Code review** — After red-teaming passes clean, invoke `crucible:code-review` against the full diff (from before debugging started to HEAD). The code reviewer checks implementation quality, test coverage, and adherence to project conventions.

If code review finds Critical or Important issues, fix them and re-review per the standard code review loop.

**Only after both gates pass clean is the debugging workflow complete.**

### Session Metrics

Throughout the debugging session, the orchestrator appends timestamped entries to `/tmp/crucible-metrics-<session-id>.log`.

At completion, compute and report:

```
-- Debugging Complete ---------------------------------------
  Subagents dispatched:  12 (8 Opus, 4 Sonnet)
  Active work time:      1h 15m
  Wall clock time:       3h 42m
  Hypothesis cycles:     3
  Quality gate rounds:   2 (hypothesis: 1, fix: 1)
-------------------------------------------------------------
```

Additional debugging metric: **hypothesis cycles** (number of hypothesis → investigate → implement cycles before resolution).

### Pipeline Decision Journal

Maintain a decision journal at `/tmp/crucible-decisions-<session-id>.log`:

```
[timestamp] DECISION: <type> | choice=<what> | reason=<why> | alternatives=<rejected>
```

Decision types:
- `investigator-count` — why N investigators dispatched
- `gate-round` — hypothesis red-team results per round
- `escalation` — why orchestrator escalated
- `hypothesis-reform` — why hypothesis was reformed after red-team

---

### Loop-back, Cleanup, and Escalation

After the Implementation agent reports back, the orchestrator evaluates:

**Fix works, no regressions** -- Log the result in the hypothesis log. Use `crucible:verify` to confirm. Then:
- **RECOMMENDED:** Use crucible:forge (retrospective mode) — capture the debugging journey and lessons learned
- **RECOMMENDED:** Use crucible:cartographer (record mode) — persist any new codebase knowledge discovered during investigation
- Proceed to Phase 5.

**Fix works but introduces regressions** -- Start a new investigation cycle targeting the regressions. The original fix stays; the regressions are a new bug.

**Fix does not resolve the issue** -- Before looping back:
1. Log the failure in the hypothesis log with metrics (see Stagnation Detection below)
2. Decide on cleanup: keep the test if it validly reproduces the bug (even if the fix was wrong). Revert both test and fix only if the test was hypothesis-specific and not a valid reproduction.
3. If reversion is needed, dispatch a cleanup subagent (`subagent_type="general-purpose"`) with instructions to: revert the specific files listed in the Implementation Report's "Files changed" field using `git checkout -- <file>`, then verify the test suite passes after revert. Tell the agent which files to revert and whether to keep or remove the test file.
4. Loop back to Phase 1 with the new information from the failed attempt. On loop-back, dispatch MORE agents than the prior cycle, not fewer — widen the investigation.

**Context Preservation:** Before dispatching new investigation after a failed fix cycle, write the hypothesis log and investigation findings to a persistent file on disk (`/tmp/crucible-debug-<session-id>-hypothesis-log.md`). This preserves context across compaction events that occur after multiple investigation rounds and a failed implementation have accumulated in context. The trigger is deterministic (failed cycle → write to disk), not conditional on self-assessed context pressure.

#### Stagnation Detection (from red-team pattern)

Track a stagnation metric across cycles — the hypothesis specificity score:

| Metric | What to Track |
|--------|--------------|
| Root causes identified | How many distinct root causes were surfaced across all investigators |
| Evidence strength | How many findings had concrete evidence (file:line, stack trace, git blame) vs speculation |
| New information | Did this cycle surface information that was NOT available in prior cycles? |

**Stagnation rule:** If Cycle N+1 surfaces no new information compared to Cycle N (same root causes, same evidence, same gaps), the orchestrator STOPS and escalates immediately. Do not dispatch Cycle N+2 — the investigation is stuck, not progressing.

#### Escalation Tiers

| Cycle | Action |
|-------|--------|
| 1 | Normal flow — dispatch 3-6 investigators |
| 2 | Loop back with learnings. Dispatch MORE agents than Cycle 1. Explicitly exclude paths already ruled out. |
| 3 | Final attempt — investigation agents are instructed to look for something fundamentally different from previous hypotheses. Add Deep Dive agents targeting areas not yet investigated. |
| 4 | **No dispatch.** Present the full hypothesis log to the user. Flag as likely architectural problem. Discuss fundamentals before attempting more fixes. |

**Stagnation overrides cycle count:** If stagnation is detected at any cycle (even Cycle 2), escalate immediately rather than waiting for Cycle 4.

**Pattern indicating architectural problem (Cycle 4 or stagnation escalation):**
- Each fix reveals new shared state, coupling, or problems in different places
- Fixes require massive refactoring to implement
- Each fix creates new symptoms elsewhere
- Investigation keeps finding the same root causes but fixes don't resolve them

This is NOT a failed hypothesis -- this is a wrong architecture. Discuss with your human partner before attempting more fixes.

---

## Quick Reference

| Phase | Agent(s) | Key Activities | Success Criteria |
|-------|----------|---------------|------------------|
| **0. Context** | Cartographer + optional Explore | Load module context for investigators | Codebase context ready for prompts |
| **1. Investigation** | 3-6 parallel subagents (Opus) | Read errors, check changes, gather evidence, deep dive, reproduce | Raw findings collected |
| **Synthesis** | 1 subagent (Sonnet) | Consolidate, cross-reference, rank by evidence quality | Concise root-cause analysis |
| **2. Pattern** | 1 subagent (Opus, skippable) | Find working examples, compare exhaustively | Differences identified |
| **3. Hypothesis** | Orchestrator (no subagent) | Form hypothesis, check log | Specific testable hypothesis |
| **3.5 Red-Team** | Quality gate (on hypothesis) | Challenge hypothesis completeness | Hypothesis survives or is reformed |
| **4. Implementation** | 1 subagent (Opus) | TDD fix cycle with evidence log | Bug resolved, tests pass, TDD log |
| **5. Quality Gate** | Red-team + code review | Adversarial review, quality check | Both pass clean |

---

## Quality Gate

This skill produces **hypotheses** (Phase 3.5) and **fixes** (Phase 5). When used standalone, quality gate is invoked at Phase 3.5 (on hypotheses) and Phase 5 (on fixes). When used as a sub-skill, the parent orchestrator may handle gating.

---

## Red Flags -- STOP and Follow Process

If you catch yourself thinking:

**Orchestrator discipline violations:**
- "Let me just read this one file quickly"
- "I'll fix this inline instead of dispatching"
- "I already know what's wrong, I'll skip investigation"
- "Let me just run the tests myself to check"
- "I'll look at the code to confirm before dispatching"

**Communication violations:**
- "Dispatching agents without narrating what you're doing and why"

**Classic debugging traps (still apply):**
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before dispatching Phase 1
- Forming hypotheses before receiving synthesis report
- **"One more fix attempt" (when already at Cycle 3+)**
- **Each fix reveals new problem in different place**

**ALL of these mean: STOP. Return to the correct phase.**

**If 3+ cycles failed:** Escalate to user. Question the architecture. Do not dispatch Cycle 4 agents.

## Your Human Partner's Signals You're Doing It Wrong

**Watch for these redirections:**
- "Is that not happening?" - You assumed without dispatching verification
- "Will it show us...?" - You should have dispatched evidence gathering
- "Stop guessing" - You're proposing fixes without investigation reports
- "Ultrathink this" - Question fundamentals, not just symptoms
- "We're stuck?" (frustrated) - Your dispatched approach isn't working

**When you see these:** STOP. Return to Phase 1. Dispatch fresh investigation.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms does not equal understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |
| "Let me just peek at the code real quick" | Orchestrators dispatch, they don't investigate. Send a subagent. |
| "I'll dispatch implementation without a hypothesis" | No hypothesis = no direction. The agent will guess. Form the hypothesis first. |

## When Process Reveals "No Root Cause"

If systematic investigation reveals issue is truly environmental, timing-dependent, or external:

1. You've completed the process
2. Document what you investigated (the hypothesis log serves as this record)
3. Dispatch an implementation agent to add appropriate handling (retry, timeout, error message)
4. Add monitoring/logging for future investigation

**But:** 95% of "no root cause" cases are incomplete investigation. Dispatch more agents before concluding this.

## Supporting Techniques and Prompt Templates

**Prompt templates** (used when dispatching subagents):
- **`./investigator-prompt.md`** -- Phase 1 investigation agent prompt
- **`./synthesis-prompt.md`** -- Synthesis agent prompt
- **`./pattern-analyst-prompt.md`** -- Phase 2 pattern analysis agent prompt
- **`./implementer-prompt.md`** -- Phase 4 implementation agent prompt

**Supporting techniques** (available in this directory):
- **`root-cause-tracing.md`** -- Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** -- Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** -- Replace arbitrary timeouts with condition polling

**Related skills:**
- **`crucible:test-driven-development`** -- Implementation agent follows TDD for Phase 4
- **`crucible:verify`** -- Verify fix worked before claiming success
- **`crucible:parallel`** -- Phase 1 parallel dispatch pattern
- **`crucible:red-team`** -- Adversarial review in Phase 5 (stagnation detection pattern also used in loop-back)

**Required skills:**
- **`crucible:cartographer`** -- Phase 0: load module context for investigators. Phase 4 completion: record discoveries.

**Recommended skills:**
- **`crucible:forge`** -- Retrospective after fix verified (captures debugging lessons)

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common
