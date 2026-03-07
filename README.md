# Crucible

A collection of [Claude Code](https://claude.ai/code) skills for systematic software development. Covers the full lifecycle: design, planning, TDD implementation, code review, debugging, and branch completion.

## Installation

Clone into your Claude Code skills directory:

```bash
git clone git@github.com:raddue/crucible.git ~/.claude/skills/crucible
```

Or symlink if you prefer keeping the repo elsewhere:

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
ln -s ~/repos/crucible/skills/* ~/.claude/skills/
```

## Setup

### Recommended Configuration

**`--dangerously-skip-permissions`** — Crucible is designed for long-running autonomous pipelines (build, debugging) that complete complex development tasks without user intervention. We recommend running with `--dangerously-skip-permissions` paired with a **safety hook** or other failsafe system to prevent destructive actions. See [safety hook examples](https://docs.anthropic.com/en/docs/claude-code/hooks) for setup guidance.

**`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`** — Required for build's team-based parallel execution (TeamCreate, team_name dispatching). Skills degrade gracefully without it — independent tasks run sequentially instead of in parallel.

**`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`** — Performance recommendation for long-running pipelines. Triggers compaction earlier to preserve context for complex multi-phase work.

## Skills

### Core Pipeline

| Skill | Description |
|-------|-------------|
| **build** | End-to-end development pipeline: interactive design, autonomous planning with quality gates, team-based execution with per-task code and test review. One command, idea to completion. |
| **design** | Interactive design refinement with quality gate on completed designs. Explores intent, requirements, and design before implementation. Produces a design doc. |
| **planning** | Implementation plan writing with quality gate on completed plans. Bite-sized tasks with exact file paths, complete code, and expected outputs. |

### Design & UI

| Skill | Description |
|-------|-------------|
| **mockup-builder** | Creates HTML mockups constrained to Theme.uss variables, flexbox-only layout, and BEM naming. Ensures mockups are designed for direct translation to Unity UI Toolkit with player-customizable theming. |
| **mock-to-unity** | Translates mockups into Unity UI Toolkit code via structured CSS-to-USS mapping, layered implementation (structure, styling, workarounds, interaction), and per-layer self-verification. Bakes in Unity 6 USS bug workarounds. |
| **ui-verify** | Compares implemented UI against source mockup using MCP screenshots or code-level structural audit. Produces structured delta reports with [PASS]/[FAIL]/[WARN] per category. |

### Implementation

| Skill | Description |
|-------|-------------|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **worktree** | Create isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Dispatch independent tasks to parallel subagents to work without shared state or sequential dependencies. |

### Quality

| Skill | Description |
|-------|-------------|
| **quality-gate** | Iterative red-teaming of any artifact (design, plan, code, hypothesis, mockup). Default 3-round cap. Invoked by artifact-producing skills. |
| **code-review** | Dispatch code review with shared canonical review checklist. |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Branch completion workflow — merge, PR, or cleanup. Guides completion of development work with comprehensive review. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before quality gate review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **debugging** | Orchestrated debugging with Phase 3.5 hypothesis red-teaming, domain detection, and strategic context preservation. Includes investigator, pattern analyst, synthesis subagent templates, and post-fix quality gate. |

### Knowledge & Learning

| Skill | Description |
|-------|-------------|
| **forge** | Self-improving retrospective system. Post-task retrospectives classify deviations and extract lessons. Pre-task feed-forward surfaces relevant warnings. Periodic mutation analysis proposes concrete skill edits for human review. |
| **cartographer** | Living architectural map that accumulates across sessions. Records codebase structure, conventions, and landmines after exploration. Surfaces structural context before tasks. Loads module-specific knowledge into subagent prompts. |

### Maintenance

| Skill | Description |
|-------|-------------|
| **stocktake** | Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan or full evaluation modes. Forge's feed-forward advisor checks stocktake results staleness and nudges when results are 30+ days old. |

### Meta

| Skill | Description |
|-------|-------------|
| **getting-started** | Introduction to finding and using crucible skills. Establishes how to find and use skills, requiring skill invocation before any response. |
| **skill-authoring** | Guide for creating and testing new skills. TDD applied to process documentation — create, test, and refine skills with pressure scenarios and rationalization counters. |

## How It Works

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Phase 1: Design** (interactive) — Refine the idea with the user, produce a design doc. Forge feed-forward and Cartographer consult run at start. Design passes through a quality gate (replaces direct red-team).
2. **Phase 2: Plan** (autonomous) — Write implementation plan, review, then quality gate on the plan (replaces direct red-team). Innovate proposes enhancements before the gate.
3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup per task, then code review per task. Cartographer loads module context into subagent prompts.
4. **Phase 4: Complete** (autonomous) — Quality gate on the full implementation (replaces direct red-team), session metrics report, full test suite, Forge retrospective, Cartographer recording, branch completion options.

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators that integrate across the pipeline. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom). Both accumulate across sessions.

Individual skills can also be used standalone (e.g., `crucible:test-driven-development` for any implementation work, `crucible:debugging` for any bug).

## Origin

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged.

## Rename History

The following skills were renamed in the quality gates overhaul (March 2026):

| Previous Name | Current Name |
|---------------|-------------|
| systematic-debugging | debugging |
| brainstorming | design |
| writing-plans | planning |
| requesting-code-review | code-review |
| receiving-code-review | review-feedback |
| finishing-a-development-branch | finish |
| dispatching-parallel-agents | parallel |
| verification-before-completion | verify |
| using-git-worktrees | worktree |
| using-crucible | getting-started |
| writing-skills | skill-authoring |

Old names are not preserved as aliases. Update any references in your CLAUDE.md or scripts.
