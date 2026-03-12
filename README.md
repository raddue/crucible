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
| **adversarial-tester** | Reads completed implementation and writes up to 5 tests designed to expose unknown failure modes. Targets edge cases, boundary conditions, and runtime behavior the implementer didn't anticipate. |
| **inquisitor** | Full-feature cross-component adversarial testing. Dispatches 5 parallel dimensions (wiring, integration, edge cases, state/lifecycle, regression) against the complete implementation diff to find bugs that per-task testing misses. |

### Quality

| Skill | Description |
|-------|-------------|
| **quality-gate** | Iterative red-teaming of any artifact (design, plan, code, hypothesis, mockup). Loops until clean or stagnation (weighted scoring: Fatal=3, Significant=1). 15-round safety limit. Invoked by artifact-producing skills. |
| **red-team** | Adversarial review engine. Dispatches fresh Devil's Advocate subagents per round with stagnation detection. Used by quality-gate internally. |
| **code-review** | Dispatch code review with shared canonical review checklist. |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Branch completion workflow — merge, PR, or cleanup. Guides completion of development work with comprehensive review. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before quality gate review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **debugging** | Orchestrated debugging with Phase 3.5 hypothesis red-teaming, domain detection, strategic context preservation, and post-fix quality gate with test gap writer (auto-retry on failures). Includes investigator, pattern analyst, and synthesis subagent templates. |

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
| **getting-started** | Skill discovery and invocation discipline. Objective test for when skills apply (code-modifying intent), scoped exceptions for pure information retrieval, escalation clauses when exceptions reveal problems, and anti-rationalization red flags. |
| **skill-creator** | Create new skills, modify and improve existing skills, and measure skill performance. Structured eval/iterate loop with grading, benchmarking, blind A/B comparison, and description optimization. From [anthropics/skills](https://github.com/anthropics/skills) (Apache 2.0). |

## How It Works

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Phase 1: Design** (interactive) — Refine the idea with the user, produce a design doc. Forge feed-forward and Cartographer consult run at start. Design passes through a quality gate (replaces direct red-team).
2. **Phase 2: Plan** (autonomous) — Write implementation plan, review, then quality gate on the plan (replaces direct red-team). Innovate proposes enhancements before the gate.
3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup (removes unnecessary code), code review per task, a test gap writer (fills coverage gaps identified by the test reviewer, with auto-retry if gaps reveal missing implementation), and an adversarial tester (writes tests designed to break the implementation). Cartographer loads module context into subagent prompts.
4. **Phase 4: Complete** (autonomous) — Code review on full implementation, inquisitor (5 parallel adversarial dimensions against the full feature diff), quality gate (replaces direct red-team), session metrics report, full test suite, Forge retrospective, Cartographer recording, branch completion options.

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators that integrate across the pipeline. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom). Both accumulate across sessions.

Individual skills can also be used standalone (e.g., `crucible:test-driven-development` for any implementation work, `crucible:debugging` for any bug).

## Eval Results

Every crucible skill is evaluated using [Anthropic's official skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (`skill-creator`). This is the same eval methodology Anthropic built for measuring whether Claude Code skills actually improve output quality — we use it here to prove that crucible's skills deliver measurable value, not just vibes.

### How It Works

The framework runs a **blind A/B test** for each skill:

1. **With skill** — the prompt is executed following the skill's full methodology
2. **Without skill** — the same prompt is given to vanilla Claude with no skill instructions
3. **Grading** — an independent grader agent scores both outputs against identical expectations, with no knowledge of which condition it's grading

This isolates the skill's contribution. If both conditions score the same, the skill isn't adding value. If the skill condition scores higher, the delta quantifies exactly how much the methodology helps.

### What Gets Measured

Expectations are a mix of **process assertions** and **domain-correctness assertions**:

- **Process** — did the output follow the right methodology? (e.g., "iterates until clean or stagnation", "red-green-refactor cycles visible")
- **Domain correctness** — is the output actually *right*? (e.g., "fix uses parameterized queries", "plan includes database migration for roles")

This dual approach prevents skills from gaming the eval by producing well-formatted garbage. The process has to be right *and* the output has to be correct.

### Iteration 1 — Skill-Value Deltas (Claude Opus 4)

10 skills, 34 evals, graded blind.

| Skill | With | Without | Delta | Notes |
|-------|------|---------|-------|-------|
| quality-gate | 91% | 9% | **82%** | Iterative red-teaming is almost entirely skill-driven |
| innovate | 83% | 17% | **67%** | Structured divergent thinking produces richer output |
| planning | 74% | 26% | **49%** | Task decomposition and quality gates add significant value |
| design | 67% | 33% | **33%** | Investigation-driven design surfaces more options |
| TDD | 67% | 33% | **33%** | Red-green-refactor discipline vs write-code-then-test |
| verify | 63% | 37% | **26%** | Evidence-before-claims catches false confidence |
| review-feedback | 62% | 38% | **24%** | Technical rigor vs blind agreement |
| debugging | 57% | 43% | **15%** | Hypothesis red-teaming catches subtle bugs |
| inquisitor | 53% | 47% | **7%** | Cross-component analysis finds a few extra issues |
| red-team | 51% | 49% | **2%** | Claude already red-teams well without structure |

### Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions. Claude already knows the right answers — skills add the methodology and discipline to consistently surface them. A quality gate that iterates three rounds of red-teaming catches issues that a single-pass review misses, even though the model *could* have found them on the first pass.

**Skill value scales inversely with model capability.** The deltas above are measured against Claude Opus — the strongest model available. On weaker models (Sonnet, Haiku, or non-Anthropic models in tools like Cursor), the structured methodology becomes scaffolding that keeps the model on track. A 2% delta on Opus could be a 20%+ delta on a model that doesn't naturally red-team well.

**Process-heavy skills show the largest deltas.** Skills that encode multi-step iterative workflows (quality-gate at 82%, innovate at 67%) benefit most from structure. Skills where Claude's baseline behavior already approximates the methodology (red-team at 2%) show minimal lift.

### Running Evals

Eval definitions live in `skills/<skill>/evals/evals.json`. Workspace outputs and grading results are in `skills/<skill>-workspace/`. To run evals yourself, use the `skill-creator` skill — it handles execution, grading, benchmarking, and iteration. See [Anthropic's skill-creator docs](https://github.com/anthropics/skills/tree/main/skills/skill-creator) for details.

## Origin

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged.

## Third-Party Skills

| Skill | Source | License |
|-------|--------|---------|
| **skill-creator** | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | Apache 2.0 |

## Project Origin

Crucible was developed for a Unity 6 project. Several skills reflect that Unity development context:

- **mockup-builder** — Creates HTML mockups constrained to Theme.uss variables for Unity UI Toolkit translation
- **mock-to-unity** — Translates mockups into Unity UI Toolkit USS/C# with Unity 6 bug workarounds
- **ui-verify** — Compares implemented UI against mockups via MCP screenshots or structural audit

These skills are usable in any Unity project. All other crucible skills are language- and framework-agnostic.

