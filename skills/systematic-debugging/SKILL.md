---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

**Execution model:** The orchestrator dispatches all investigation and implementation to subagents. The orchestrator NEVER reads code, edits files, or runs tests directly. It forms hypotheses, dispatches work, and makes decisions based on subagent reports.

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

All investigation and implementation is delegated to subagents via the Task tool. The orchestrator handles hypothesis formation, dispatch decisions, and escalation -- nothing else.

### Workflow Overview

```
Bug reported / test failure / unexpected behavior
    |
    v
Orchestrator: Parse initial context (error message, failing test, user description)
    |
    v
Phase 1: Dispatch 2-4 parallel investigation subagents
    |  +-- Error Analysis agent (always)
    |  +-- Change Analysis agent (always)
    |  +-- Evidence Gathering agent (conditional -- multi-component systems)
    |  +-- Reproduction agent (conditional -- intermittent/unclear bugs)
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
Phase 4: Implementation agent (TDD: failing test, fix, verify)
    |
    v
Orchestrator: Verify fix -> Success? Done. Failed? Cleanup, log, loop back.
    -> 3 failures? Escalate to user.
```

---

### Phase 1: Investigation (Parallel Subagent Dispatch)

**Prompt template:** `./investigator-prompt.md`

Dispatch 2-4 investigation subagents in parallel using the Task tool in a single message. All subagents use `subagent_type="general-purpose"`. Pass all known context (error messages, stack traces, file paths, user description) verbatim to each agent -- do not make them search for context you already have.

**Before dispatching:** Use crucible:cartographer (load mode) — if module files exist for the area being investigated, paste them into each investigator's prompt so they don't waste time re-discovering codebase structure.

**Always dispatch:**

1. **Error Analysis Agent** -- Read error messages, stack traces, and logs. Identify the exact failure point, error codes, and what the error is telling us.

2. **Change Analysis Agent** -- Check recent changes via git diff, recent commits, new dependencies, config changes, and environmental differences. Identify what changed that could cause this.

**Conditionally dispatch:**

3. **Evidence Gathering Agent** -- For multi-component systems (CI pipelines, API chains, layered architectures). Add diagnostic instrumentation at component boundaries. Log what enters and exits each component. Run once, report where the data flow breaks.

4. **Reproduction Agent** -- For intermittent, timing-dependent, or unclear bugs. Attempt to reproduce consistently. Document exact steps, frequency, and conditions. If not reproducible, gather more data rather than guessing.

#### Phase 1 Dispatch Heuristics

| Bug Characteristics | Agents to Dispatch |
|--------------------|--------------------|
| Test failure with clear stack trace | Error + Change |
| Vague "something broke" across multiple systems | All four agents |
| Intermittent / timing-dependent issue | Error + Change + Reproduction |
| Multi-layer system failure (CI, API chain) | Error + Change + Evidence Gathering |
| Performance regression | Error + Change + Evidence Gathering |

---

### Synthesis: Consolidate Findings

**Prompt template:** `./synthesis-prompt.md`

After all Phase 1 agents report back, dispatch a single Synthesis agent that receives all Phase 1 reports verbatim.

**The Synthesis agent produces:**
- A 200-400 word root-cause analysis
- Ranked list of likely causes (most to least probable)
- Identified unknowns or gaps in evidence
- Recommendation: is the root cause obvious, or is pattern analysis needed?

**Skip-ahead rule:** If all Phase 1 agents converge on the same root cause and the Synthesis agent confirms it as obvious, the orchestrator may skip Phase 2 and proceed directly to Phase 3 (hypothesis formation).

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

### Loop-back, Cleanup, and Escalation

After the Implementation agent reports back, the orchestrator evaluates:

**Fix works, no regressions** -- Done. Log the result in the hypothesis log. Use `crucible:verification-before-completion` to confirm. Then:
- **RECOMMENDED:** Use crucible:forge (retrospective mode) — capture the debugging journey and lessons learned
- **RECOMMENDED:** Use crucible:cartographer (record mode) — persist any new codebase knowledge discovered during investigation

**Fix works but introduces regressions** -- Start a new investigation cycle targeting the regressions. The original fix stays; the regressions are a new bug.

**Fix does not resolve the issue** -- Before looping back:
1. Log the failure in the hypothesis log
2. Decide on cleanup: keep the test if it validly reproduces the bug (even if the fix was wrong). Revert both test and fix only if the test was hypothesis-specific and not a valid reproduction.
3. If reversion is needed, dispatch a cleanup subagent (`subagent_type="general-purpose"`) with instructions to: revert the specific files listed in the Implementation Report's "Files changed" field using `git checkout -- <file>`, then verify the test suite passes after revert. Tell the agent which files to revert and whether to keep or remove the test file.
4. Loop back to Phase 1 with the new information from the failed attempt.

#### Escalation Tiers

| Cycle | Action |
|-------|--------|
| 1 | Normal flow |
| 2 | Loop back with learnings from Cycle 1 |
| 3 | Final attempt -- investigation agents are instructed to look for something fundamentally different from previous hypotheses |
| 4 | **No dispatch.** Present the full hypothesis log to the user. Flag as likely architectural problem. Discuss fundamentals before attempting more fixes. |

**Pattern indicating architectural problem (Cycle 4 escalation):**
- Each fix reveals new shared state, coupling, or problems in different places
- Fixes require massive refactoring to implement
- Each fix creates new symptoms elsewhere

This is NOT a failed hypothesis -- this is a wrong architecture. Discuss with your human partner before attempting more fixes.

---

## Quick Reference

| Phase | Agent(s) | Key Activities | Success Criteria |
|-------|----------|---------------|------------------|
| **1. Investigation** | 2-4 parallel subagents | Read errors, check changes, gather evidence, reproduce | Raw findings collected |
| **Synthesis** | 1 subagent | Consolidate, rank, identify unknowns | Concise root-cause analysis |
| **2. Pattern** | 1 subagent (skippable) | Find working examples, compare exhaustively | Differences identified |
| **3. Hypothesis** | Orchestrator (no subagent) | Form hypothesis, check log | Specific testable hypothesis |
| **4. Implementation** | 1 subagent | TDD fix cycle | Bug resolved, tests pass |

---

## Red Flags -- STOP and Follow Process

If you catch yourself thinking:

**Orchestrator discipline violations:**
- "Let me just read this one file quickly"
- "I'll fix this inline instead of dispatching"
- "I already know what's wrong, I'll skip investigation"
- "Let me just run the tests myself to check"
- "I'll look at the code to confirm before dispatching"

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
- **`crucible:verification-before-completion`** -- Verify fix worked before claiming success
- **`crucible:dispatching-parallel-agents`** -- Phase 1 parallel dispatch pattern

**Recommended skills:**
- **`crucible:forge`** -- Retrospective after fix verified (captures debugging lessons)
- **`crucible:cartographer`** -- Load module context for investigators, record discoveries after fix

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common
