# Crucible

A collection of [Claude Code](https://claude.ai/code) skills for systematic software development. Covers the full lifecycle: brainstorming, planning, TDD implementation, code review, debugging, and branch completion.

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
| **brainstorming** | Interactive design refinement. Explores intent, requirements, and design before implementation. Produces a design doc. |
| **writing-plans** | Creates detailed TDD implementation plans from specs or requirements. Bite-sized tasks with exact file paths, complete code, and expected outputs. |
| **executing-plans** | Standalone plan executor. Dispatches subagents per task with risk-based iterative review, verification gates, and architectural checkpoints. |

### Implementation

| Skill | Description |
|-------|-------------|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **using-git-worktrees** | Creates isolated git worktrees for feature work with smart directory selection and safety verification. |
| **dispatching-parallel-agents** | Pattern for launching 2+ independent subagents to work without shared state or sequential dependencies. |

### Quality

| Skill | Description |
|-------|-------------|
| **requesting-code-review** | Dispatches a code review subagent to verify work meets requirements. |
| **receiving-code-review** | Anti-sycophancy skill for receiving review feedback. Requires technical rigor and verification, not blind implementation. |
| **verification-before-completion** | Evidence-before-claims discipline. Run verification commands and confirm output before making success claims. |
| **finishing-a-development-branch** | Guides completion of development work — comprehensive review, then structured options for merge, PR, or cleanup. |
| **red-team** | Adversarial review of any artifact. Iterates with fresh reviewers until clean or stagnation. Used on designs, plans, and implementations. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before adversarial review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **systematic-debugging** | Structured investigation before proposing fixes. Includes investigator, pattern analyst, and synthesis subagent templates. |

### Meta

| Skill | Description |
|-------|-------------|
| **using-crucible** | Bootstrap skill. Establishes how to find and use skills, requiring skill invocation before any response. |
| **writing-skills** | TDD applied to process documentation. Create, test, and refine skills with pressure scenarios and rationalization counters. |

## How It Works

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Brainstorm** (interactive) — Refine the idea with the user, produce a design doc
2. **Innovate + Red-Team Design** (autonomous) — Creative enhancement, then adversarial review of the design (iterative until clean)
3. **Plan** (autonomous) — Write implementation plan, review iteratively, innovate, then red-team iteratively
4. **Execute** (autonomous, team-based) — Dispatch implementers per task, iterative code review per task
5. **Red-Team Implementation** (autonomous) — Adversarial review of the complete implementation (iterative until clean)
6. **Complete** — Full test suite, comprehensive code review, branch completion options

Individual skills can also be used standalone (e.g., `crucible:test-driven-development` for any implementation work, `crucible:systematic-debugging` for any bug).

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
- executing-plans skill ported from superpowers with iterative review loops
