---
name: executing-plans
description: Use when you have a written implementation plan to execute, whether sequential or parallel, same-session or separate
---

# Executing Plans

## Overview

Load plan, review critically, dispatch all tasks to subagents with maximum parallelism and risk-based review.

**Core principle:** The orchestrator dispatches, monitors, and verifies — it does NOT implement. Every task goes to a subagent unless it's trivially small. Execute the entire plan end-to-end, only stopping for hard blockers.

**Context budget:** On a 20-task plan, the orchestrator should end the session having used context primarily for: reading the plan, creating todos, writing subagent prompts, reading subagent results, lightweight review, and the final report — NOT for reading/writing implementation code.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## The Process

### Step 1: Load and Review Plan
1. **RECOMMENDED SUB-SKILL:** Use crucible:forge (feed-forward mode) — consult past lessons before starting
2. **RECOMMENDED SUB-SKILL:** Use crucible:cartographer (consult mode) — review codebase map for structural awareness
3. Read plan file
4. Extract all tasks with full text — subagents should never read the plan file themselves
5. Review critically — identify any questions or concerns about the plan
6. If concerns: Raise them with your human partner before starting
7. If no concerns: Create TodoWrite and proceed

### Step 2: Analyze Task Dependencies, Shared Files, and Risk

Before executing, perform dependency and risk analysis:

1. **Identify independent vs dependent tasks** — independent tasks have no shared state or sequential dependencies; dependent tasks must run after another completes.
2. **Identify shared files** — tasks that modify the same file are NOT independent, even if they implement different features. Serialize them or group them into a single subagent.
3. **Assess task risk** — classify each task for review frequency (see Review Strategy below).
4. **Map execution waves** — group independent tasks into parallel waves, with verification gates between waves.

- Independent tasks MUST be parallelized
- Dependent tasks and shared-file tasks run sequentially
- Maximize concurrency — if 5 tasks are truly independent, launch all 5 in parallel

### Step 3: Execute All Tasks via Subagents
**Do NOT batch into groups of 3. Do NOT pause for feedback. Execute continuously.**

**The orchestrator delegates — it does not implement.** All tasks go to subagents unless they meet the trivial threshold (see below).

For each task (or wave of parallel tasks):
1. Mark as in_progress
2. Write subagent prompt using `./implementer-prompt.md` template
3. Launch subagents — all independent tasks in a single message (multiple Task tool calls)
4. When subagents complete, perform review based on task risk level (see Review Strategy)
5. Run verification gate before launching next wave (tests, compilation)
6. Incorporate learnings from completed subagents into prompts for next wave
7. Mark as completed
8. Immediately launch next wave — no waiting for user input

#### Trivial Threshold — When the Orchestrator Can Act Inline

The orchestrator may do a task itself ONLY if ALL of these are true:
- Single file, single edit (< 5 lines changed)
- No verification step needed (no tests to run, no compilation to check)
- It would take longer to write the subagent prompt than to do it

Examples: adding an import, toggling a config value, fixing a typo. Everything else goes to a subagent.

#### Subagent Prompt Guidelines

Use the `./implementer-prompt.md` template. Key principles:

- Always use `subagent_type="general-purpose"` for implementation tasks
- Pass the plan step text verbatim — don't make subagents read the plan file
- Include file paths so the subagent doesn't waste context searching
- Include project conventions (DI framework, naming, test style)
- **RECOMMENDED:** Use crucible:cartographer (load mode) — paste relevant module files, conventions.md, and landmines.md into subagent prompts
- Include verification criteria from the plan
- For sequential tasks: include the result/output from the prior subagent
- Ask subagents to report unexpected findings — relay these to subsequent subagents
- Subagents should ask questions if unclear, not guess

#### Review Strategy — Risk-Based

Not all tasks need the same review rigor. Assess each task's risk level during Step 2:

**High risk — Spec compliance + Code quality review (both iterative):**
- Core systems (DI containers, bootstrapping, data models, state management)
- Public APIs or interfaces consumed by other systems
- Security-sensitive code (auth, permissions, input validation)
- Tasks with complex or ambiguous requirements

Dispatch `./spec-reviewer-prompt.md` subagent first — verify the implementation matches the spec. Then dispatch code quality reviewer via `crucible:requesting-code-review`. Both use the iterative review loop (see below). Both must pass before proceeding.

**Medium risk — Code quality review only (iterative):**
- New features with clear requirements
- Multi-file refactoring
- Test infrastructure changes

Dispatch code quality reviewer via `crucible:requesting-code-review`. Uses the iterative review loop.

**Low risk — Lightweight orchestrator review only:**
- Simple additions following established patterns
- Config changes, straightforward implementations
- Changes well-covered by existing test suites

Orchestrator reads the subagent's result message, skims the diff if needed, checks for unexpected findings. No reviewer subagent needed.

**Trivial — No review (verification gate is sufficient):**
- Same tasks that meet the trivial threshold for inline execution
- The wave-level verification gate (tests/compilation) provides coverage

#### Iterative Review Loop (All Reviewer Types)

When a reviewer finds issues:

1. **Record the issue count** — count Critical + Important issues (for code review) or Fatal + Significant issues (for spec review).
2. **Dispatch a new fix subagent** with:
   - The original task description
   - The reviewer's specific findings (verbatim)
   - The files that need changes
   - Instructions to fix ONLY the identified issues, not refactor or expand scope
3. **Dispatch a NEW fresh reviewer** after fixes (different subagent, no prior context).
4. **Compare issue count to prior round:**
   - **Strictly fewer issues:** Progress — loop again from step 1.
   - **Same or more issues:** Stagnation — escalate to user with findings from both rounds.
5. **Architectural concerns:** Immediate escalation regardless of round.

**Fresh reviewer every round.** Never pass prior findings to the next reviewer. No anchoring.

For trivial fixes (typo in a variable name, missing null check): the orchestrator may fix inline if it meets the trivial threshold. Everything else goes to a fix subagent.

**Do NOT** have the orchestrator fix complex review findings inline — that pulls implementation details into the orchestrator's context, defeating the context budget.

#### Verification Gates

After each wave of parallel tasks completes (not after every individual task):

1. **Run the FULL test suite** — not just tests for the current wave's tasks. A subagent's changes might break something a prior task built. Only the full suite catches cross-task regressions.
2. **Check compilation** — ensure no build errors across the entire project.
3. If failures: identify which subagent's work caused the regression before launching fixes.
4. If clean: proceed to next wave immediately.

**Fail fast** — don't pipeline blindly. Catching issues between waves prevents error cascading where later tasks build on broken foundations.

#### Architectural Checkpoint — Zoom Out

On plans with 10+ tasks, individual task correctness doesn't guarantee the whole system coheres. The orchestrator must pause at natural breakpoints to assess the big picture.

**When to trigger:**
- After completing ~50% of tasks, OR
- After completing a major subsystem (a logical grouping of related tasks), OR
- Whenever the orchestrator notices subagents reporting unexpected findings that suggest design drift

Whichever comes first. For plans under 10 tasks, skip this — the finishing-a-development-branch review covers it.

**How to run:**
1. Dispatch an architecture reviewer subagent using `./architecture-reviewer-prompt.md`
2. Provide: the original plan, a summary of completed tasks, the remaining tasks, and diff guidance (see below)
3. The reviewer assesses cohesion, not individual task quality

**Handling large diffs:** On a 20-task plan at 50%, the full diff can be thousands of lines. Don't dump it all into the prompt — let the reviewer subagent pull what it needs:
- Provide a `git diff --stat` summary (files changed + line counts) so the reviewer knows the scope
- List the key files/systems touched by completed tasks
- Let the reviewer read specific files and diffs as needed rather than receiving the entire diff upfront
- For very large implementations (20+ files changed), consider splitting into multiple focused reviewers: one per subsystem

**Act on findings:**
- **Design drift detected:** Stop and discuss with your human partner before continuing. The remaining tasks may need adjustment.
- **Minor cohesion concerns:** Log them, adjust subagent prompts for remaining tasks to address them, continue.
- **All clear:** Continue execution.

**This is NOT a code review.** It's asking "do the pieces fit together? Is the emerging system what the plan intended?" Code quality and spec compliance are handled by their respective reviews.

#### Failure Protocol

When a subagent fails or produces poor results:

1. **First attempt:** Retry with enriched context (include the error, add more file content, clarify the ambiguity)
2. **Second attempt:** Orchestrator does the task inline as fallback
3. **Repeated failures across tasks:** Stop and ask the user — the plan may have gaps

### Step 4: Final Report
After ALL tasks are complete:
- **RECOMMENDED SUB-SKILL:** Use crucible:forge (retrospective mode) — capture plan vs actual execution
- **RECOMMENDED SUB-SKILL:** Use crucible:cartographer (record mode) — persist new codebase knowledge discovered during execution
- Show summary of everything implemented
- Show final verification output (tests, compilation, etc.)
- Note any issues encountered and how they were resolved
- Note any unexpected findings reported by subagents

### Step 5: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use crucible:finishing-a-development-branch
- Follow that skill to verify tests, run comprehensive code review, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker that prevents ALL remaining tasks (missing dependency, repeated test failures)
- Plan has critical gaps preventing starting
- You don't understand an instruction and guessing could cause damage
- Verification fails repeatedly with no clear fix
- Multiple subagents fail on different tasks (plan may be flawed)
- Review loop stagnates (same or more issues after fixes)

**For minor issues:** Log them, work around if possible, and include in the final report. Do NOT stop the entire run for recoverable problems.

**Ask for clarification rather than guessing on destructive or irreversible actions.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Prompt Templates

- `./implementer-prompt.md` — Template for dispatching implementer subagents
- `./spec-reviewer-prompt.md` — Template for spec compliance review (high-risk tasks)
- `./architecture-reviewer-prompt.md` — Template for mid-plan architectural checkpoint (10+ task plans)
- Code quality review uses `crucible:requesting-code-review`

## Remember
- The orchestrator dispatches and reviews — it does not implement
- All tasks go to subagents unless trivially small (< 5 lines, single file, no verification)
- Identify shared files during dependency analysis — shared file = not independent
- Assess task risk: high -> spec + quality review, medium -> quality review, low -> orchestrator skim, trivial -> verification gate only
- All review loops are iterative: fresh reviewer each round, escalate on stagnation
- Architectural checkpoint at ~50% or after completing a major subsystem (10+ task plans)
- Paste plan step text into subagent prompts — don't make subagents read the plan file
- Ask subagents to report unexpected findings — relay to subsequent tasks
- Verification gates between waves, not blind pipelining
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Do NOT pause between tasks for feedback — run continuously
- Stop only when truly blocked, not for routine check-ins
- Never start implementation on main/master branch without explicit user consent

## Integration

**Required workflow skills:**
- **crucible:writing-plans** - Creates the plan this skill executes
- **crucible:requesting-code-review** - Code quality review for medium/high-risk tasks (iterative)
- **crucible:finishing-a-development-branch** - Complete development after all tasks

**Recommended workflow skills:**
- **crucible:forge** — Feed-forward at Step 1, retrospective at Step 4
- **crucible:cartographer** — Consult at Step 1, load at subagent dispatch, record at Step 4

**Optional workflow skills:**
- **crucible:using-git-worktrees** - Set up isolated workspace (skip for projects where only one IDE instance can run, e.g. Unity)

**Subagents should use:**
- **crucible:test-driven-development** - Subagents follow TDD for each task
