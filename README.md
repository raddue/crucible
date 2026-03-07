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

## Skills

### Core Pipeline

| Skill | Description |
|-------|-------------|
| **build** | End-to-end development pipeline: interactive brainstorming, autonomous planning with adversarial review, team-based execution with per-task code and test review. One command, idea to completion. |
| **design** | Interactive design refinement. Explores intent, requirements, and design before implementation. Produces a design doc. |
| **planning** | Creates detailed TDD implementation plans from specs or requirements. Bite-sized tasks with exact file paths, complete code, and expected outputs. |

### Design & UI

| Skill | Description |
|-------|-------------|
| **mockup-builder** | Creates HTML mockups constrained to Theme.uss variables, flexbox-only layout, and BEM naming. Ensures mockups are designed for direct translation to Unity UI Toolkit with player-customizable theming. |
| **mock-to-unity** | Translates mockups into Unity UI Toolkit code via structured CSS→USS mapping, layered implementation (structure → styling → workarounds → interaction), and per-layer self-verification. Bakes in Unity 6 USS bug workarounds. |
| **ui-verify** | Compares implemented UI against source mockup using MCP screenshots or code-level structural audit. Produces structured delta reports with [PASS]/[FAIL]/[WARN] per category. |

### Implementation

| Skill | Description |
|-------|-------------|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **worktree** | Creates isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Pattern for launching 2+ independent subagents to work without shared state or sequential dependencies. |

### Quality

| Skill | Description |
|-------|-------------|
| **code-review** | Dispatches a code review subagent to verify work meets requirements. |
| **review-feedback** | Anti-sycophancy skill for receiving review feedback. Requires technical rigor and verification, not blind implementation. |
| **verify** | Evidence-before-claims discipline. Run verification commands and confirm output before making success claims. |
| **finish** | Guides completion of development work — comprehensive review, then structured options for merge, PR, or cleanup. |
| **red-team** | Adversarial review of any artifact. Iterates with fresh reviewers until clean or stagnation. Used on designs, plans, and implementations. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before adversarial review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **debugging** | Structured investigation before proposing fixes. Includes investigator, pattern analyst, synthesis subagent templates, and post-fix red-team/code-review quality gate. |

### Knowledge & Learning

| Skill | Description |
|-------|-------------|
| **forge** | Self-improving retrospective system. Post-task retrospectives classify deviations and extract lessons. Pre-task feed-forward surfaces relevant warnings. Periodic mutation analysis proposes concrete skill edits for human review. |
| **cartographer** | Living architectural map that accumulates across sessions. Records codebase structure, conventions, and landmines after exploration. Surfaces structural context before tasks. Loads module-specific knowledge into subagent prompts. |

### Meta

| Skill | Description |
|-------|-------------|
| **getting-started** | Bootstrap skill. Establishes how to find and use skills, requiring skill invocation before any response. |
| **skill-authoring** | TDD applied to process documentation. Create, test, and refine skills with pressure scenarios and rationalization counters. |

## How It Works

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Brainstorm** (interactive) — Refine the idea with the user, produce a design doc. Forge feed-forward and Cartographer consult run at start.
2. **Innovate + Red-Team Design** (autonomous) — Creative enhancement, then adversarial review of the design (iterative until clean)
3. **Plan** (autonomous) — Write implementation plan, review iteratively, innovate, then red-team iteratively
4. **Execute** (autonomous, team-based) — Dispatch implementers per task, iterative code review per task. Cartographer loads module context into subagent prompts.
5. **Red-Team Implementation** (autonomous) — Adversarial review of the complete implementation (iterative until clean)
6. **Complete** — Full test suite, comprehensive code review, Forge retrospective, Cartographer recording, branch completion options

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators that integrate across the pipeline. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom). Both accumulate across sessions.

Individual skills can also be used standalone (e.g., `crucible:test-driven-development` for any implementation work, `crucible:debugging` for any bug).

## Origin

Forked from [obra/superpowers](https://github.com/obra/superpowers) with modifications:

- `superpowers:` namespace replaced with `crucible:`
- Build skill consolidates the full pipeline (brainstorm through completion)
- Code review dispatch uses general-purpose subagent + prompt template (no custom subagent type)
- Writing-plans execution handoff removed (build handles execution)
- Dead/redundant skills trimmed
- Iterative review loops everywhere (fresh reviewer each round, stagnation detection, no hard caps)
- Standalone red-team skill with iterative adversarial review
- Standalone innovate skill for creative enhancement before red-teaming
- Forge skill for post-task retrospectives, pre-task feed-forward, and skill mutation proposals
- Cartographer skill for persistent codebase mapping across sessions
- Systematic debugging Phase 5: post-fix red-team and code review quality gate
