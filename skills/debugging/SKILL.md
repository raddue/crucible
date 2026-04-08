---
name: debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

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

**After compaction:** Re-read the session state from the scratch directory (see Session State below) and output current status before continuing.

**This requirement exists because:** Debugging sessions can involve multiple investigation rounds and fix attempts. Without narration, the user has no visibility into which hypotheses have been tried, what evidence was found, or why the orchestrator is pursuing a particular path.

**Execution model:** The orchestrator dispatches all investigation and implementation to subagents. The orchestrator NEVER reads code, edits files, or runs tests directly. It forms hypotheses, dispatches work, and makes decisions based on subagent reports.

**Depth principle:** When in doubt, dispatch MORE investigation agents, not fewer. A bug that looks simple from the surface often has a complex root cause. Spinning up 4-6 focused investigators in parallel costs minutes; missing the root cause costs hours.

## Pipeline Status

Write a status file to `~/.claude/projects/<hash>/memory/pipeline-status.md` at every narration point. This file is overwritten (not appended) and provides ambient awareness for the user in a second terminal.

### Write Triggers

Write the status file at every point where the Communication Requirement mandates narration: before dispatch, after completion, phase transitions, health changes, escalations, and after compaction recovery.

### Status File Format

The status file uses this structure (overwritten in full each time):

```
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write — persisted across compaction>
**Skill:** debugging
**Phase:** <current phase, e.g. "Synthesis", "4 — Implementation">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from Started>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

### Skill-Specific Body

Append after the shared header:

```
## Investigation
- Hypothesis: "Missing null check in event handler dispatch chain"
- Cycle: 2 of 4 max
- Phase 4 fix attempts: 1 (WIP commit pending verification)

## Compression State
Goal: [original user request / bug report]
Key Decisions:
- [accumulated decisions, max 10]
Active Constraints:
- [constraints affecting remaining investigation]
Next Steps:
1. [immediate next action]
2. [subsequent actions]
```

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): Phase 0->1, 1->Synthesis, Synthesis->2, 2->3, 3->4, 4->4.5, 4.5->5. Sub-phases (3.5, within Phase 3) do NOT reset.
- **YELLOW:** hypothesis cycle 3+, quality gate round 5+, fix retry in progress
- **RED:** escalation pending, stagnation detected, 3 fix failures reached

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence (e.g., "Third hypothesis attempted. Consider narrowing the search space or providing additional context.").

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Phase 1 [cycle 2] Investigating: null check hypothesis | GREEN | 34m`
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery

After compaction, before re-writing the status file:
0. Read the `## Compression State` section from `pipeline-status.md` — recover Goal, Key Decisions, Active Constraints, and Next Steps. If absent, skip to step 1.
1. Read the rest of `pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from internal state files (see Session State below)
3. Emit a Compression State Block into the conversation to seed the new context window
3.5. **Read session index summary (supplementary):** If the CSB Scratch State contains a `Session Index:` path, or if globbing `~/.claude/projects/<hash>/memory/session-index/*/summary.md` finds a recent file, read `summary.md`. Include the Activity Timeline, Files Modified, and Key Decisions sections in the post-compaction narration. If no session index exists, skip silently — this step is purely additive. If `summary.md` lacks detail for a specific event type (e.g., errors, hypothesis changes, file modifications), use `/recall` to query `events.jsonl` with filters for targeted recovery.
4. Write the updated status file
5. Output inline status to CLI

## Session State and Compaction Recovery

The debugging skill writes session state to disk at **every phase transition**, not just on failure. This ensures compaction recovery works regardless of when it occurs.

**Scratch directory:** `/tmp/crucible-debug-<session-id>/` where `<session-id>` is a timestamp generated at the start of the debugging session.

**Write at each phase transition:**
- `phase-state.md`: current phase, cycle count, current hypothesis (if formed)
- `hypothesis-log.md`: running hypothesis log (updated at Phase 3, after Phase 4 results)
- `synthesis-report.md`: latest synthesis report (written after Synthesis completes)
- `implementation-details.md`: cumulative record of implementation attempts — what was tried, which files changed, regressions encountered, why it failed (appended after each Phase 4)
- `where-else-state.md`: Phase 4.5 state — pre-Phase-4.5 SHA, generalized pattern, siblings found/fixed/remaining (written during Phase 4.5, read during compaction recovery)

At each phase transition, in addition to writing session state files, emit a Compression State Block into the conversation. The block captures the reasoning layer (goal, decisions, constraints, next steps) that the session state files do not.

### Checkpoint Timing

Emit a Compression State Block at:
- **Phase transitions:** 0→1, Synthesis→3, 3.5→4, 4.5→5 — emit a **Phase Handoff Manifest** (see below) instead of a Compression State Block at these major boundaries. Other transitions (1→Synthesis, Synthesis→2, 2→3, 3→3.5, 4→4.5) continue to use CSBs.
- **Hypothesis cycles:** After each hypothesis is formed or invalidated
- **Fix attempts:** After each Phase 4 implementation attempt completes (success or failure)
- **Escalations:** Before any escalation to user
- **Health transitions:** On any GREEN->YELLOW or YELLOW->RED transition

**Context hygiene:** After synthesis completes, raw Phase 1 investigation reports are superseded by the synthesis report. The orchestrator should rely on the synthesis report going forward, not the raw reports. After Phase 4 completes (success or failure), the Phase 2 pattern analysis report is superseded by the implementation results. This keeps the orchestrator lean across long sessions.

**Compaction recovery:**
0. Check for handoff manifests (`handoff-*-to-*.md`) in the scratch directory. If the most recent manifest exists, use its Inputs, Decisions, and Constraints to reconstruct state for the current phase — this supersedes session state files for phase-boundary recovery. If no manifest exists, continue with standard recovery.
1. Read `phase-state.md` to determine current phase and cycle.
2. Read `hypothesis-log.md` for hypothesis history.
3. Read `synthesis-report.md` for latest investigation findings.
4. Read `implementation-details.md` for prior fix attempts.
5. Read `where-else-state.md` (if exists) for Phase 4.5 progress — which siblings have been fixed, which remain.
6. Output status to user and continue from the current phase.

**Cleanup:** Delete scratch directory and `.pipeline-active` marker after debugging completes (Phase 5 passes clean or escalation to user).

### Phase Handoff Manifest

At major phase boundaries (0→1, Synthesis→3, 3.5→4, 4.5→5), write a **handoff manifest** to the scratch directory instead of emitting a Compression State Block. The manifest defines exactly what the next phase needs — an allowlist. Everything not on the manifest is shed.

**Format:**

```markdown
# Phase Handoff: N → M
**Timestamp:** ISO-8601
**Goal:** [original bug report, verbatim]

## Inputs for Phase M
- **[Input name]:** [disk path or inline value]

## Decisions Carried Forward
- [DEC-N] [decision]: [reasoning, one line]

## Active Constraints
- [constraint affecting remaining work]

## Shed Receipt
- [what was shed] → [where it lives on disk]
```

**Rules:**
- After writing the manifest, emit an explicit **shed statement**.
- After writing the manifest, update `## Compression State` in pipeline-status.md with manifest contents.
- CSBs continue at non-major-boundary checkpoint triggers (1→Synthesis, Synthesis→2, 2→3, 3→3.5, 4→4.5, hypothesis cycles, fix attempts, escalations, health transitions).
- **Backward compatibility:** If no manifest exists at a recovery point, fall back to CSB-based recovery.

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
| Synthesis | Consolidation | Opus | Cross-referencing, contradiction detection, and causal reasoning — not just summarization |
| Phase 2 | Pattern Analysis | Opus | Exhaustive comparison requires depth |
| Phase 4 | Implementation | Opus | TDD + root cause fix |
| Phase 4.5 | "Where Else?" scan | Opus | Cross-codebase pattern matching and sibling fixing |
| Phase 5 | Red-team | Opus | Adversarial analysis |
| Phase 5 | Code review | Opus or Sonnet | Lead decides by fix complexity |
| Phase 5 | Test gap writer | Opus | Test authoring requires reasoning |

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
Orchestrator: Verify fix -> Success? Phase 4.5. Failed? Cleanup, log, loop back.
    -> 3 failures? Escalate to user. If checkpoints exist: "Checkpoints available from prior fix cycles. Restore to a known-good state before manual investigation?"
    |
    v
Phase 4.5: "Where Else?" scan — find and fix sibling locations
    |
    v
Phase 5: Quality-gate the fix (crucible:quality-gate) + Code review (crucible:code-review)
    |
    v
Test Gap Writer (if reviews flagged missing coverage)
    |
    v
Done.
```

---

### Phase -1: Pipeline-Active Marker Check

Before any dispatch work, check for a crashed prior debugging session:

1. **Check `<scratch>/.pipeline-active`** (where `<scratch>` is `~/.claude/projects/<hash>/memory/`)
2. **Not found:** Write the pipeline-active marker (JSON with `pipeline_id` set to current session ID, `skill` set to `"debugging"`, `phase` set to `"0"`, `start_time` set to current ISO-8601 timestamp, `scratch_dir` and `dispatch_dir` paths, `branch` from `git branch --show-current`, `baseline_sha` from `git rev-parse HEAD`). Proceed to Phase 0.
3. **Found, same `pipeline_id`:** Compaction recovery (existing behavior). Do not re-write the marker.
4. **Found, different `pipeline_id`:** Previous debugging session crashed. Check marker's `branch` against current branch — if mismatched, warn the user which branch the crashed session was on. Present to user:
   > "Previous debugging session on branch [marker.branch] crashed. Start fresh? [yes]"
   Delete the stale marker. Write a fresh marker. Proceed to Phase 0. (Full replay orchestration for debugging is deferred -- detection and cleanup only for now.)

**Marker cleanup:** Delete `.pipeline-active` after debugging completes (Phase 5 passes clean or escalation to user), alongside the existing scratch directory cleanup.

### Phase 0: Load Codebase Context

**Before any investigation dispatch,** use `crucible:cartographer` (load mode) to pull module context for the area being investigated. If module files exist, include them in every investigator's dispatch file so agents start with structural knowledge instead of wasting turns rediscovering the codebase.

**Defect signature loading (for investigators):**
1. Glob `defect-signatures/*.md` (excluding `*.non-matches.md`) from the cartographer storage directory
2. For each signature, read its `Modules` field and match against the investigation area's modules:
   - Read each cartographer module file's `Path:` field
   - A file is in a module if the file path starts with the module's `Path:` value
   - When the investigation spans multiple modules, load signatures for all matched modules
   - **Directory prefix fallback:** When no cartographer modules exist, match if any target file path starts with any of the signature's `Modules` directory prefixes
3. For matching signatures, validate all file paths still exist on disk — drop stale entries silently
4. Inject into the `[DEFECT_SIGNATURES]` section of `investigator-prompt.md`:
   - Generalized pattern (always)
   - Confirmed siblings list (always)
   - Unresolved siblings list (always)
   - Non-match companion file IS loaded for investigators, truncated to 50 entries at load time with note "(list truncated to 50 most recent entries)"
5. **`Last loaded` update:** Loading is pure-read. After all investigator dispatches complete, batch-update the `Last loaded` field to today on all signatures that were loaded.

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

#### Phase Handoff: 0 → 1

Before dispatching investigation agents:

1. Write `handoff-0-to-1.md` with:
   - **Goal:** bug report / user description, verbatim
   - **Inputs for Phase 1:** cartographer module paths, defect signature paths (with match notes), domain context (if any), error messages / stack traces (verbatim), reproduction steps (if any)
   - **Decisions Carried Forward:** (typically empty at this point)
   - **Active Constraints:** user-stated constraints
   - **Shed Receipt:** raw cartographer exploration output → module files on disk
2. Emit shed statement: "Phase 0 context shed. Module files, defect signatures, and error context captured in manifest. Raw exploration output is not carried forward."
3. Update `## Compression State` in pipeline-status.md.
4. Do NOT emit a Compression State Block.

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

After all Phase 1 agents report back, dispatch a single Synthesis agent (model: opus) that receives all Phase 1 reports verbatim.

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

#### Phase Handoff: Synthesis → 3

Before the orchestrator forms a hypothesis (whether Phase 2 ran or was skipped):

1. Write `handoff-synthesis-to-3.md` with:
   - **Goal:** original bug report, verbatim
   - **Inputs for Phase 3:** synthesis report path, pattern analysis report path (or "skipped" with reason), hypothesis log path (empty if cycle 1), key file paths surfaced during investigation
   - **Decisions Carried Forward:** skip-phase-2 decision (if applicable), investigator-count decision
   - **Active Constraints:** constraints from investigation findings
   - **Shed Receipt:** raw Phase 1 investigation reports (3-6 agent reports) → synthesis report captures consolidated findings
2. Emit shed statement: "Investigation context shed. Synthesis report captures consolidated findings. Raw investigator reports are not carried forward."
3. Update `## Compression State` in pipeline-status.md.
4. Do NOT emit a Compression State Block.

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

#### Phase Handoff: 3.5 → 4

Before dispatching the implementation agent:

1. Write `handoff-3.5-to-4.md` with:
   - **Goal:** original bug report, verbatim
   - **Inputs for Phase 4:** validated hypothesis (verbatim), target file paths, conventions path, hypothesis log path, implementation details log path (if prior cycles exist)
   - **Decisions Carried Forward:** hypothesis rationale, red-team survival notes
   - **Active Constraints:** constraints on the fix approach
   - **Shed Receipt:** red-team round details, hypothesis formation reasoning → hypothesis log captures outcomes; gate round details are shed
2. Emit shed statement: "Hypothesis formation context shed. Validated hypothesis, target files, and hypothesis log on disk. Red-team round details are not carried forward."
3. Update `## Compression State` in pipeline-status.md.
4. Do NOT emit a Compression State Block.

---

### Phase 4: Implementation (Single Subagent -- TDD)

**RECOMMENDED SUB-SKILL:** Use crucible:checkpoint — create checkpoint with reason "pre-debug-fix-cycle-N" (where N is the hypothesis cycle count) before dispatching the implementation agent. If the fix attempt fails or introduces regressions, this checkpoint allows clean rollback without relying on WIP commit revert mechanics.

**Prompt template:** `./implementer-prompt.md`

Dispatch a single Implementation agent that receives:
- The hypothesis (verbatim)
- Relevant file paths identified during investigation
- Project conventions and test standards
- The hypothesis log (so it knows what hypotheses were already tried)
- The implementation details log from prior cycles (so it knows what code-level approaches were tried, which files were changed, and why they failed — see `implementation-details.md` in the scratch directory)

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

### Commit Strategy

**After Phase 4 completes**, if the implementer modified any files, create a WIP commit regardless of outcome:

```
git commit -m "fix(wip): [hypothesis summary]"        # on success
git commit -m "fix(wip-failed): [hypothesis summary]"  # on failure or regressions
```

This gives every outcome path a clean revert target (`git revert <sha>`), gives Phase 5 code review a real diff, and isolates Phase 5 test modifications from the core fix. If the full pipeline succeeds, the final commit message is amended to drop the `(wip)` prefix. If Phase 5 requires changes (test audit updates, gap test additions), those are committed as separate follow-up commits.

On loop-back (failed fix or user-requested revert), `git revert <wip-sha>` cleanly undoes all Phase 4 changes including new files.

If Phase 4.5 ran (sibling commits exist): use `git revert <pre-4.5-sha>..HEAD` instead of `git revert <wip-sha>`. This reverts all sibling commits plus the original WIP commit in one operation. See Phase 4.5 below.

**Phase 4.5 sibling commits:** Each sibling fix uses the prefix `fix(sibling):` with a descriptive message. Example: `fix(sibling): add icon initialization to StashScreen.OnEnable`

---

### Phase 4.5: "Where Else?" Blast Radius Scan

**RECOMMENDED SUB-SKILL:** Use crucible:checkpoint — create checkpoint with reason "pre-where-else" before dispatching the scan agent. This replaces the need to manually track the pre-Phase-4.5 SHA for revert mechanics — the checkpoint captures the full working directory state.

After Phase 4 succeeds and the WIP commit is created, dispatch the "Where Else?" scan agent to find and fix analogous locations in the codebase that have the same bug pattern. Phase 4.5 does NOT run on loop-back paths (fix failed, regressions found).

**Prompt template:** `./where-else-prompt.md`

**Pre-Phase-4.5 SHA:** Immediately after the Phase 4 WIP commit succeeds, record its SHA. This is the last commit before any sibling work begins. Store it in `where-else-state.md` in the scratch directory.

#### Three Input Signals

The scan agent receives three sources of information:

1. **The fix diff** — `git diff <pre-fix-sha>..HEAD`. The structural pattern of what changed: what was missing, what was added, and what makes a location "analogous."
2. **Cartographer module context** — If cartographer data is available from Phase 0, structurally similar modules (other screens, panels, managers, handlers that follow the same architectural pattern as the fixed code).
3. **Implementer's "Analogous Locations" report** — The Phase 4 implementer's observations about locations they noticed during the fix that may have the same pattern. This is the highest-quality signal — the implementer was already reading the code.

#### Existing Defect Signatures (Fourth Input Signal)

When dispatching the Phase 4.5 scan agent, load matching defect signatures from cartographer as additional context:
- **Selection:** Load at most 3 matching signatures. Treat `Last loaded: never` as oldest. Sort by `Last loaded` descending. Tiebreak by `Date` descending.
- **Module matching:** Same as build/debug load — read each cartographer module file's `Path:` field; match if any target file path starts with the module's `Path:` value. Fall back to directory prefix matching if no cartographer modules exist.
- **What to load:** Signature file (generalized pattern, confirmed siblings, unresolved siblings) plus non-match companion file paths only (without full reason text). The scan agent can read individual companion files on demand if it needs the reasoning.
- **Guidance to scan agent:** Prioritize evaluating candidates NOT listed as confirmed non-matches in existing signatures, but may still evaluate non-match locations if context budget allows. If the new scan confirms the same pattern still exists in a previously-cleared location, note this as a "stale non-match" in the report.

#### Scan Agent Behavior

1. **Analyze the fix pattern.** Read the diff. Extract the structural pattern. Produce a 2-3 sentence generalized pattern description.
2. **Build candidate list.** Combine all three input signals, deduplicate candidates.
3. **Evaluate each candidate.** Read the code at that location. Determine if the same pattern/omission exists. If yes: write a justification explaining WHY this location matches semantically (not just structurally). If no: record as skipped with reason.
4. **Fix confirmed siblings.** For each confirmed sibling:
   - Apply the same fix pattern
   - Run tests
   - If tests pass: commit with `fix(sibling): <description>`
   - If tests fail: revert that single commit, record as "reverted — test failure", continue with remaining candidates
   - After each fix (or revert), update `where-else-state.md` in the scratch directory
5. **Report back.** Structured report:

```
## Where Else? Scan Report

### Generalized Pattern
[2-3 sentence pattern description]

### Candidates Evaluated: N

### Siblings Fixed: N
- [file:path] — [commit SHA] — Justification: [why this matches]
- ...

### Siblings Skipped: N
- [file:path] — Reason: [why this doesn't match]
- ...

### Siblings Reverted: N
- [file:path] — Test failure: [summary of what failed]
- ...
```

#### Compaction Recovery

Phase 4.5 maintains state in `<scratch-dir>/where-else-state.md` to survive session compaction. The file is updated after each sibling fix. On compaction recovery, the agent reads this file to:
- Skip siblings already fixed
- Resume from where it left off with remaining siblings
- Recover the pre-Phase-4.5 SHA (needed for revert mechanics)
- Recover the generalized pattern (avoids re-deriving from the diff)

#### Rules

- Apply the SAME fix pattern — do not invent new approaches for siblings
- One commit per sibling — clean revert granularity
- If tests fail for a sibling, revert and continue — do not debug the sibling
- Do not modify the original fix
- If no candidates are found, report "No analogous locations found" and proceed to Phase 5
- No cap on sibling count — fix all confirmed siblings

#### Defect Signature Persistence

After the Phase 4.5 scan agent reports back, persist the scan results as a cartographer defect signature. This is orchestrator-managed — the recorder only writes files.

**Skip condition:** Do not write a signature when Phase 4.5 reports "No analogous locations found" (0 candidates evaluated). A pattern with no siblings and no non-matches has no evaluation ledger worth persisting.

**Step 1: Dedup check (orchestrator)**
1. Glob `~/.claude/projects/<hash>/memory/cartographer/defect-signatures/*.md` (excluding `*.non-matches.md`)
2. Read each file's `## Generalized Pattern` section only (each is 2-3 sentences; 20 patterns is ~1000-1500 tokens)
3. Compare semantically with the new scan report's generalized pattern
4. **Dedup rubric:** Two patterns are duplicates if they describe the same root cause in the same codebase area. Different areas or different root causes = distinct signatures. When in doubt, treat as distinct — a near-duplicate is recoverable via pruning, a false merge is not.
5. If a match is found, set `update_path` to the existing file path (the recorder will merge into it rather than creating new)
6. If no match, the recorder creates a new file using the content hash slug

**Step 2: Pre-write pruning (orchestrator)**
When count of existing signatures would exceed 20 after writing:
1. Build the pruning-eligible set: exclude signatures where `Last loaded: never` AND `Date` is less than 30 days old
2. Sort by `Last loaded` date ascending; `Last loaded: never` sorts oldest
3. Among ties, prune the oldest by `Date` field
4. Write-before-delete ordering: dispatch the recorder first, then delete pruned files after the recorder succeeds

**Step 3: Dispatch recorder (orchestrator)**
Dispatch a Sonnet cartographer recorder agent using `crucible:cartographer` recorder-prompt.md with the "Record defect signature" directive. Provide:
- Phase 4.5 scan report (generalized pattern, confirmed siblings, reverted siblings, skipped siblings)
- Original fix metadata (file path, commit SHA, commit message summary, issue number)
- Cartographer module names from Phase 0 (or directory prefix fallbacks)
- `update_path` if dedup found a match (from Step 1)

**Step 4: Post-recorder validation (orchestrator)**
After the recorder returns, validate:
1. The signature file exists on disk
2. Sibling entries are within the 30-entry cap
3. The `Modules` field contains valid cartographer module names or directory prefixes
If validation fails, log the failure — the signature is not surfaced to consumers.

**Step 5: Rename on merge (orchestrator)**
If `update_path` was provided (merge case): rename the file to use today's date prefix while keeping the original slug. `YYYY-MM-DD-<slug>.md` becomes `<today>-<slug>.md`. If a companion non-match file exists, rename it to match. This ensures merged signatures do not lose age protection.

**Ordering:** Dispatch the recorder and wait for completion, then perform the `Last loaded` batch update (see below). This prevents write races between the recorder and the batch update targeting the same file.

**`Last loaded` batch update:** After all subagent dispatches for the current phase complete (including the recorder), batch-update the `Last loaded` field on all defect signatures that were loaded during Phase 0 or Phase 4.5. The recorder sets `Last loaded` to today on `update_path` writes, so skip those files during the batch update.

**Over-count recovery:** If count exceeds 20 after a failed prune (e.g., all signatures are age-protected), the next invocation's pre-recorder pruning pass cleans up before writing.

#### Phase Handoff: 4.5 → 5

Before invoking the quality gate on the fix:

1. Write `handoff-4.5-to-5.md` with:
   - **Goal:** original bug report, verbatim
   - **Inputs for Phase 5:** full diff (`git diff <pre-fix-sha>..HEAD`), conventions path, test file paths, Where Else report path (or "no siblings found"), defect signature path (if written)
   - **Decisions Carried Forward:** root cause, fix approach, sibling fix decisions
   - **Active Constraints:** constraints on review scope
   - **Shed Receipt:** Phase 4 TDD cycle details, Phase 4.5 candidate evaluation reasoning → fix is in the diff, sibling results in the report
2. Emit shed statement: "Implementation context shed. Fix diff, test files, and sibling report on disk. TDD cycle details and candidate evaluation reasoning are not carried forward."
3. Update `## Compression State` in pipeline-status.md.
4. Do NOT emit a Compression State Block.

---

### Phase 5: Red-Team and Code Review (Post-Fix Quality Gate)

**RECOMMENDED SUB-SKILL:** Use crucible:checkpoint — create checkpoint with reason "pre-debug-gate" before invoking the quality gate. If gate fix rounds degrade the fix, this is the rollback target.

After Phase 4.5 completes (or Phase 4 succeeds if no Phase 4.5 ran), the orchestrator runs quality gates before declaring done:

**Step 1: Quality-gate the fix** — Invoke `crucible:quality-gate` with artifact type "code" against the changed code. Quality-gate dispatches fresh red-team reviewers to adversarially review the fix for:
- Edge cases the fix doesn't handle
- New failure modes introduced by the fix
- Assumptions that could break under different conditions
- Regression risks not covered by the test

Quality-gate handles iteration tracking, stagnation detection, compaction recovery, and user checkpoints. Do NOT invoke `crucible:red-team` directly — always go through quality-gate for iteration management.

**Step 2: Code review** — After red-teaming passes clean, invoke `crucible:code-review` against the full diff (from before debugging started to HEAD). The code reviewer checks implementation quality, test coverage, and adherence to project conventions.

If code review finds Critical or Important issues, fix them and re-review per the standard code review loop.

**Step 2.5: Test suite audit** — Invoke `crucible:test-coverage` (if available) against the changed code and affected test files. This audits whether existing tests need updating, removal, or modification after the fix. Three categories:
- **Tests to update** — assertions, descriptions, or setup now wrong or misleading given the fix (includes stale assertions expecting old values)
- **Tests to delete** — tests for removed code paths
- **Coincidence tests** — tests whose setup exercises changed code but assertions verify unrelated properties (flagged for judgment, not auto-fixed)

If `crucible:test-coverage` is not available, skip this step. The test gap writer (Step 3) handles missing coverage but NOT stale/misleading existing tests — this step fills that gap.

The test-coverage skill handles its own fix dispatch and revert-on-failure logic internally. It returns a structured report with actions taken.

**Step 3: Test gap writer** — If the code reviewer or red-teamer identified missing test coverage for the fix, dispatch a Test Gap Writer agent (Opus) using `./test-gap-writer-prompt.md`. Input: reviewer gap findings + fix diff + test-coverage audit report (if available from Step 2.5). The agent writes tests only for gaps specifically flagged in the review — no scope creep. Before writing a new test for a flagged gap, verify no existing test already covers this path (it may have been updated by the test-coverage audit). Tests should PASS immediately since the behavior already exists from the fix. The agent reports per-test PASS/FAIL results. Skipped when reviews report zero coverage gaps.

**If all tests PASS:** Debugging workflow is complete.

**If some tests FAIL** (gaps reveal incomplete fix coverage):
1. Dispatch a fresh implementer (Opus) with the failing test(s), their failure messages, gap descriptions, and the original bug context (hypothesis, root cause)
2. Implementer fixes the incomplete coverage, re-runs ALL test gap writer tests (not just failures — catches regressions from the fix)
3. If all tests pass after fix: commit (`fix: address test gap failures for debugging fix`), debugging workflow is complete
4. If tests still fail after one fix attempt: **escalate to user** with:
   - The original bug and confirmed root cause
   - What was fixed in Phase 4
   - Which test gaps were detected by reviewers
   - What the retry implementer attempted
   - Which tests still fail and their current failure messages

**If Phase 5 quality-gate escalates** (stagnation or round limit): Present the quality-gate findings to the user alongside the fix. The user decides:
- **(a) Accept the fix** with known issues noted
- **(b) Revert and loop back** — revert the WIP commit (or range revert `<pre-4.5-sha>..HEAD` if Phase 4.5 ran) and loop back to Phase 1 with the quality-gate findings as new investigation context
- **(c) Stop debugging** — end the session with the current state

This is user-gated, not automatic. The orchestrator does not decide whether to loop back from Phase 5 on its own.

**Only after all gates pass clean (and any test gaps are filled or escalated) is the debugging workflow complete.**

### Session Metrics

Throughout the debugging session, the orchestrator appends timestamped entries to `/tmp/crucible-metrics-<session-id>.log`.

**Dispatch measurement protocol:** On every subagent dispatch, the orchestrator follows the enriched manifest protocol from `shared/dispatch-convention.md`:
- **Before dispatching:** Measure the dispatch file size in characters. Record `input_chars` and `model_tier` in the manifest entry.
- **After dispatch returns:** Measure the subagent response length in characters. Record `output_chars` and `tool_calls` (if available) in the manifest completion entry.

At completion, read the metrics log and manifest, then compute and report:

```
-- Debugging Complete ---------------------------------------
  Subagents dispatched:  12 (8 Opus, 4 Sonnet)
  Active work time:      1h 15m
  Wall clock time:       3h 42m
  Hypothesis cycles:     3
  Quality gate rounds:   2 (hypothesis: 1, fix: 1)
  Est. input tokens:    ~15,200 (60,800 chars)
  Est. output tokens:   ~9,800 (39,200 chars)
  Token estimate note:  Based on dispatch file sizes (chars/4). Actual consumption may vary +/-30%.
-------------------------------------------------------------
```

Additional debugging metric: **hypothesis cycles** (number of hypothesis → investigate → implement cycles before resolution).

**Efficiency summary computation:** Read `manifest.jsonl` from the dispatch directory. Sum `input_chars` and `output_chars` across all completed entries (skip nulls). Divide each by 4 for token estimates. Count dispatches grouped by `model_tier`. Include these in the debugging completion report alongside existing metrics.

### Pipeline Decision Journal

Maintain a decision journal at `/tmp/crucible-decisions-<session-id>.log`:

```
[timestamp] DECISION: <type> | choice=<what> | reason=<why> | alternatives=<rejected>
```

Decision types:
- `investigator-count` — why N investigators dispatched
- `skip-phase-2` — why Phase 2 was skipped (or not)
- `gate-round` — hypothesis red-team results per round
- `escalation` — why orchestrator escalated
- `hypothesis-reform` — why hypothesis was reformed after red-team

---

### Loop-back, Cleanup, and Escalation

After the Implementation agent reports back, the orchestrator evaluates four possible outcomes:

**Fix works, no regressions** -- Log the result in the hypothesis log. Proceed to Phase 4.5 ("Where Else?" blast radius scan). After Phase 4.5 completes, proceed to Phase 5. After Phase 5 passes clean:
- **RECOMMENDED:** Use crucible:forge (retrospective mode) — capture the debugging journey and lessons learned
- **Chronicle signal fallback:** If forge retrospective will not run (user declined, session ending),
  append a minimal chronicle signal directly:
  - Construct signal: `v=1`, `ts=now`, `skill="debugging"`, `outcome` from fix verification,
    `duration_m` from session timing, `branch` from git, `files_touched` from `git diff --name-only`,
    `metrics={hypotheses count, root_cause_category from fix, where_else_hits count}`
  - Append as a single JSON line to `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl`
  - If forge retrospective WILL run, skip this step (forge Step 8.5 handles it)
- **RECOMMENDED:** Use crucible:cartographer (record mode) — persist any new codebase knowledge discovered during investigation

**Test passes immediately (no fix applied)** -- The implementer's reproduction test passed before any fix was written. Two possibilities:
1. **Bug was already resolved** (by investigation side effects, environment change, or prior cycle). Verify by running the original reproduction steps. If the original bug is gone: proceed to Phase 5 but **skip Step 1 (quality-gate on code)** since there is no code change. Go directly to Step 2 (code review) scoped to the reproduction test file only.
2. **Test doesn't reproduce the bug** (hypothesis was wrong about the reproduction). Log the hypothesis as "wrong — test did not reproduce" in the hypothesis log. Revert the WIP commit (`git revert <wip-sha>`) to remove the non-reproducing test. Loop back to Phase 3 to reform the hypothesis, or Phase 1 if the root cause itself is in question.

**Fix works but introduces regressions** -- Start a new investigation cycle targeting the regressions. The original fix stays; the regressions are a new bug. **Critical:** Pass the original bug context (hypothesis, fix applied, original root cause) to the new investigation agents as background context, with the constraint: "The original fix must not be reverted. Investigate why the fix caused regressions and propose an additive solution."

**Fix does not resolve the issue** -- Before looping back:
1. Log the failure in the hypothesis log with metrics (see Stagnation Detection below)
2. **Test triage:** Dispatch a quick Opus subagent to read the test and the hypothesis log, then decide: keep the test (if it validly reproduces the bug regardless of the failed fix) or remove it (if it was hypothesis-specific and doesn't reproduce the actual bug). The orchestrator does not make this judgment directly — it requires reading code.
3. **Revert the WIP commit** using `git revert <wip-sha>` (see Commit Strategy above). This cleanly undoes all Phase 4 changes including any new files created during refactoring. If Phase 4.5 ran (sibling commits exist): use `git revert <pre-4.5-sha>..HEAD` instead of `git revert <wip-sha>` to revert all sibling commits plus the original WIP commit.
   - If triage decided **"keep the test"**: dispatch a subagent to recover the test file from the reverted commit (`git checkout <wip-sha> -- <test-file-path>`) and commit it separately (`test: preserve reproduction test from cycle N`).
   - If triage decided **"remove the test"**: no further action — the revert already removed it.
4. Verify the working tree is clean: dispatch the cleanup agent to run `git status` and report any remaining modifications or untracked files. If any remain, clean them up before proceeding.
5. Loop back to Phase 1 with the new information from the failed attempt. On loop-back, dispatch MORE agents than the prior cycle, not fewer — widen the investigation.

**Context Preservation:** Session state is written to disk at every phase transition (see Session State and Compaction Recovery above). On failed cycles, additionally append implementation details (fix attempted, files changed, regressions, why it failed) to `implementation-details.md` in the scratch directory. This gives the next Phase 4 implementer actionable context about what was tried at the code level, not just the hypothesis level.

#### Stagnation Detection (from red-team pattern)

**Stagnation ownership:** The debugging skill's stagnation detector owns **cycle-to-cycle** decisions (loop back vs escalate). Quality-gate's stagnation detector owns **within-gate** decisions (round-to-round within a single Phase 3.5 or Phase 5 invocation). When quality-gate escalates within a gate (e.g., hypothesis keeps getting torn apart), the debugging orchestrator counts that as a **failed cycle** and updates the hypothesis log accordingly before deciding whether to loop back. Quality-gate history from prior invocations does not carry over — each gate invocation starts fresh.

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
| **Synthesis** | 1 subagent (Opus) | Consolidate, cross-reference, rank by evidence quality | Concise root-cause analysis |
| **2. Pattern** | 1 subagent (Opus, skippable) | Find working examples, compare exhaustively | Differences identified |
| **3. Hypothesis** | Orchestrator (no subagent) | Form hypothesis, check log | Specific testable hypothesis |
| **3.5 Red-Team** | Quality gate (on hypothesis) | Challenge hypothesis completeness | Hypothesis survives or is reformed |
| **4. Implementation** | 1 subagent (Opus) | TDD fix cycle with evidence log | Bug resolved, tests pass, TDD log |
| **4.5. Where Else?** | 1 subagent (Opus) + 1 recorder (Sonnet) | Find and fix sibling locations; persist defect signature | Siblings fixed, signature written (if 1+ candidates) |
| **5. Quality Gate** | Red-team + code review | Adversarial review, quality check | Both pass clean |
| **5b. Test Audit** | Test coverage skill (conditional) | Audit existing tests for staleness after fix | Stale tests updated/removed |
| **5c. Test Gaps** | Test gap writer (Opus, conditional) | Write tests for reviewer-flagged gaps | All gap tests pass |

---

## Quality Gate

This skill produces **hypotheses** (Phase 3.5) and **fixes** (Phase 5).

**When used standalone:** Debugging is the outermost orchestrator and MUST invoke quality-gate at Phase 3.5 (on hypotheses) and Phase 5 (on fixes). These gates are non-negotiable regardless of fix size — a "one-liner" fix is not exempt.

**When used as a sub-skill:** The parent orchestrator is responsible for dispatching gates (per the Invocation Convention: "Skills NEVER self-invoke quality-gate"). If you are unsure whether you are standalone or a sub-skill, invoke the gate — double-gating is preferable to no gating.

**The only legitimate skip** is at Phase 5 when there is no code change (bug was already resolved). Do not extrapolate from this — it applies only to the specific "no code change" scenario, not to "small" or "trivial" changes.

**Gate tracking:** Before declaring done, verify that Phase 3.5 (hypothesis gate) and Phase 5 (fix gate, unless legitimately skipped for no-code-change) each show round count >= 1 with clean final rounds. If any gate was skipped with explicit user approval, record it as `USER_SKIP`.

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

**Quality gate violations:**
- "This fix is too small to need a quality gate"
- "It's just a one-liner, the gate won't find anything"
- Skipping Phase 3.5 or Phase 5 quality gate without explicit user approval
- Declaring a quality gate "done" after fixing findings without a clean verification round (fixing is not passing)
- Extrapolating from the "no code change" skip to justify skipping on small changes
- Interpreting general user feedback as approval to skip a quality gate that has not yet run

**Compression State violations:**
- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block at a major phase boundary (0→1, Synthesis→3, 3.5→4, 4.5→5) instead of writing a handoff manifest
- Skipping the shed statement after a manifest write
- Emitting a Compression State Block with stale or missing Key Decisions (decisions must be cumulative across all prior blocks)
- Allowing the Goal field to drift across successive Compression State Blocks (must match original user request)
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest
- Treating session index summary as authoritative over CSB state (session index is supplementary narrative, CSB is authoritative state)

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

## User-Provided Diagnosis Traps

The rationalizations above are self-originated — you talking yourself out of process. The traps below are user-originated — the user (reasonably, in good faith) providing a diagnosis that tempts you to skip investigation. These are harder to resist because accommodating the user feels helpful.

| User says | You think | Reality |
|-----------|-----------|---------|
| "I found the bug, here's the fix" | "Their analysis looks right, I'll verify quickly and apply" | User diagnoses are hypotheses, not conclusions. Verify independently — plausible ≠ confirmed. |
| "The stack trace points right to it" | "The evidence is clear, skip to fix" | Stack traces show where errors surface, not where they originate. The throw site is often a symptom, not the cause. |
| "This is blocking N engineers" | "Speed matters more than process right now" | A wrong fix under time pressure creates two problems: the original bug plus the bad fix. Systematic debugging is faster than guess-and-check, especially under pressure. |
| "Same bug as last sprint" | "Apply the same fix pattern" | Same symptom ≠ same cause. The prior fix may have been incomplete, or a different root cause produces identical symptoms. |
| "Just add error handling around it" | "That'll prevent the crash at least" | Error handling that silences the symptom is camouflage, not a fix. The root cause persists and will surface elsewhere. |
| "It's obviously X, I just need you to fix it" | "The user has more context, trust their judgment" | Trust their observations (symptoms, timeline, reproduction steps). Verify their conclusions (root cause, fix). These are different things. |
| "We can investigate later, just patch it now" | "Pragmatism — ship the fix, investigate in a follow-up" | 'Investigate later' means 'never investigate.' The patch becomes the permanent fix. Do it right now. |

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
- **`./where-else-prompt.md`** -- Phase 4.5 "Where Else?" scan agent prompt
- **`./test-gap-writer-prompt.md`** -- Phase 5 test gap writer prompt (when reviews flag missing coverage)

**Supporting techniques** (available in this directory):
- **`root-cause-tracing.md`** -- Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** -- Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** -- Replace arbitrary timeouts with condition polling

**Related skills:**
- **`crucible:test-driven-development`** -- Implementation agent follows TDD for Phase 4
- **`crucible:verify`** -- Verify fix worked before claiming success
- **`crucible:parallel`** -- Phase 1 parallel dispatch pattern
- **`crucible:quality-gate`** -- Adversarial review in Phase 5 (iteration tracking, stagnation detection, compaction recovery)
- **`crucible:red-team`** -- Invoked indirectly via quality-gate (stagnation detection pattern also used in loop-back)
- **`crucible:test-coverage`** -- Phase 5 Step 2.5: audit existing tests for staleness, needed updates, or removal after the fix (if available)

**Does not dispatch /recon or /assay** -- uses specialized investigation agents (Error Analysis, Change Analysis, Evidence Gathering, Reproduction) that are categorically different from structural investigation. Hypothesis evaluation uses quality-gate, not assay. See #147 for rationale.

**Required skills:**
- **`crucible:cartographer`** -- Phase 0: load module context for investigators and defect signatures. Phase 4 completion: record discoveries. Phase 4.5 completion: persist defect signature via recorder dispatch.

**Recommended skills:**
- **`crucible:forge`** -- Retrospective after fix verified (captures debugging lessons)
- **`crucible:checkpoint`** -- Shadow git checkpoints before implementation, sibling fixes, and quality gate (pre-debug-fix-cycle-N, pre-where-else, pre-debug-gate). Provides structured rollback for fix attempts and sibling work.

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common
