# Crucible

A collection of agent skills for systematic software development. Works with [Claude Code](https://claude.ai/code), [Cursor](https://cursor.com), [OpenAI Codex](https://openai.com/codex/), [Amp](https://amp.dev), [Cline](https://cline.bot), and any platform that supports the SKILL.md format.

Covers the full development lifecycle: design, planning, TDD implementation, code review, debugging, adversarial testing, and quality gates. Every skill is [eval-tested](#eval-results) with measured A/B deltas.

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged.

### Marketplace Availability

| Platform | Status |
|----------|--------|
| Claude Code | Pending review |
| [skills.sh](https://skills.sh) | `npx skills add raddue/crucible` |
| Cursor | Compatible |
| OpenAI Codex | Compatible |
| Amp | Compatible |
| Cline | Compatible |

## Why Crucible?

**Every skill is eval-tested.** Crucible is the only skill collection we know of with quantified, blind A/B deltas using [Anthropic's own skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator). Each skill is run with and without its methodology against identical prompts, graded by an independent agent that doesn't know which condition it's scoring. The result is a measured delta — not "we think this helps" but "this skill improves output quality by 49% on planning tasks." See the [full scoreboard](#iteration-1--skill-value-deltas-claude-opus-4).

**Iterative quality gates, not single-pass review.** Unlike other skill collections, Crucible's quality-gate skill loops — it red-teams an artifact, the author revises, a fresh reviewer attacks again, and it continues until clean or until weighted stagnation detection determines further iteration won't help. This alone accounts for an 82% delta over unstructured review.

**Full pipeline orchestration.** The build skill chains design, planning, execution, and completion into a single autonomous pipeline. It dispatches parallel implementers, runs two-pass code review per task, fills test coverage gaps, writes adversarial tests designed to break the implementation, and runs a 5-dimension cross-component inquisitor before the final quality gate.

**Adversarial testing at every level.** Crucible doesn't just review code, it actively tries to break it. The adversarial-tester writes tests designed to expose unknown failure modes. The inquisitor attacks the full feature diff across 5 dimensions (wiring, integration, edge cases, state/lifecycle, regression). The quality gate dispatches fresh Devil's Advocate reviewers each round to avoid anchoring bias.

**Language- and framework-agnostic.** Crucible was originally built for Unity game development, and includes optional [Unity UI Toolkit skills](#unity-ui-domain-specific) for that workflow. But the core skills — planning, TDD, quality gates, debugging, adversarial testing — work on any codebase in any language. The methodologies are about *how* you develop, not *what* you're building.

## Installation

### Claude Code

Clone and symlink into your skills directory:

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
ln -sf ~/repos/crucible/skills/* ~/.claude/skills/
```

Or install as a plugin (when available on the marketplace):

```bash
claude plugin install raddue/crucible
```

### Cursor

Skills follow the same SKILL.md format. Clone and configure as a plugin source:

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
```

See [Cursor plugin docs](https://cursor.com/docs/plugins/building) for adding external skill directories.

### OpenAI Codex

Skills are compatible with Codex's SKILL.md discovery:

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
```

See [Codex skills docs](https://developers.openai.com/codex/skills/) for registering skill sources.

### Cross-Platform Notes

All skills use the SKILL.md format published by Anthropic and adopted across platforms. Some advanced features (parallel subagent dispatch, agent teams, persistent memory) are platform-specific and degrade gracefully — see [PLATFORMS.md](PLATFORMS.md) for compatibility details.

## Setup (Claude Code)

These settings are specific to Claude Code. Other platforms have equivalent configuration — see [PLATFORMS.md](PLATFORMS.md) for details.

**`--dangerously-skip-permissions`** — Crucible is designed for long-running autonomous pipelines (build, debugging) that complete complex development tasks without user intervention. We recommend running with `--dangerously-skip-permissions` paired with a **safety hook** or other failsafe system to prevent destructive actions. See [safety hook examples](https://docs.anthropic.com/en/docs/claude-code/hooks) for setup guidance.

**`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`** — Required for build's team-based parallel execution. Skills degrade gracefully without it — independent tasks run sequentially instead of in parallel. This applies to all platforms where parallel subagent dispatch is not available.

**`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`** — Performance recommendation for long-running pipelines. Triggers compaction earlier to preserve context for complex multi-phase work.

## Skills

### Core Pipeline

| Skill | Description |
|-------|-------------|
| **build** | End-to-end development pipeline: interactive design, autonomous planning with quality gates, team-based execution with per-task code and test review. One command, idea to completion. |
| **design** | Interactive design refinement with quality gate on completed designs. Explores intent, requirements, and design before implementation. Produces a design doc. |
| **planning** | Implementation plan writing with quality gate on completed plans. Bite-sized tasks with exact file paths, complete code, and expected outputs. |

### Implementation

| Skill | Description |
|-------|-------------|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **worktree** | Create isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Dispatch independent tasks to parallel subagents to work without shared state or sequential dependencies. |
| **adversarial-tester** | Reads completed implementation and writes up to 5 tests designed to expose unknown failure modes. Targets edge cases, boundary conditions, and runtime behavior the implementer didn't anticipate. |
| **inquisitor** | Full-feature cross-component adversarial testing. Runs 5 parallel adversarial dimensions (wiring, integration, edge cases, state/lifecycle, regression) against the complete implementation diff to find bugs that per-task testing misses. |

### Quality

| Skill | Description |
|-------|-------------|
| **quality-gate** | Iterative red-teaming of any artifact (design, plan, code, hypothesis, mockup). Loops until clean or stagnation (weighted scoring: Fatal=3, Significant=1). 15-round safety limit. Invoked by artifact-producing skills. |
| **red-team** | Adversarial review engine. Dispatches fresh Devil's Advocate reviewers per round with stagnation detection. Used by quality-gate internally. |
| **code-review** | Dispatch code review with shared canonical review checklist. |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Branch completion workflow — merge, PR, or cleanup. Guides completion of development work with comprehensive review. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before quality gate review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **debugging** | Orchestrated debugging with hypothesis red-teaming, domain detection, strategic context preservation, and post-fix quality gate with test gap writer (auto-retry on failures). |

### Knowledge & Learning

| Skill | Description |
|-------|-------------|
| **forge** | Self-improving retrospective system. Post-task retrospectives classify deviations and extract lessons. Pre-task feed-forward surfaces relevant warnings. Periodic mutation analysis proposes concrete skill edits for human review. |
| **cartographer** | Living architectural map that accumulates across sessions. Records codebase structure, conventions, and landmines after exploration. Surfaces structural context before tasks. |
| **project-init** | Eliminates cold-start penalty by deep-scanning the current repo and discovering cross-repo topology. Produces structural cartographer maps and a topology directory before the first real task. |

### Maintenance & Meta

| Skill | Description |
|-------|-------------|
| **stocktake** | Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan or full evaluation modes. |
| **getting-started** | Skill discovery and invocation discipline. Objective test for when skills apply, scoped exceptions for pure information retrieval, and anti-rationalization red flags. |

### Unity UI (Domain-Specific)

These skills are for [Unity UI Toolkit](https://docs.unity3d.com/Manual/UIElements.html) projects. All other crucible skills are language- and framework-agnostic.

| Skill | Description |
|-------|-------------|
| **mockup-builder** | Creates HTML mockups constrained to Theme.uss variables, flexbox-only layout, and BEM naming. Designed for direct translation to Unity UI Toolkit with player-customizable theming. |
| **mock-to-unity** | Translates mockups into Unity UI Toolkit code via structured CSS-to-USS mapping, layered implementation, and per-layer self-verification. Bakes in Unity 6 USS bug workarounds. |
| **ui-verify** | Compares implemented UI against source mockup using screenshots or code-level structural audit. Produces structured delta reports with [PASS]/[FAIL]/[WARN] per category. |

## How It Works

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Phase 1: Design** (interactive) — Refine the idea with the user, produce a design doc. Forge feed-forward and Cartographer consult run at start. Design passes through a quality gate.
2. **Phase 2: Plan** (autonomous) — Write implementation plan, review, then quality gate on the plan. Innovate proposes enhancements before the gate.
3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup, code review per task, test gap writer (fills coverage gaps with auto-retry), and adversarial tester (writes tests designed to break the implementation).
4. **Phase 4: Complete** (autonomous) — Code review on full implementation, inquisitor (5 parallel adversarial dimensions against the full feature diff), quality gate, session metrics, full test suite, Forge retrospective, Cartographer recording, branch completion.

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom). Both accumulate across sessions.

The **project-init** skill accelerates onboarding — run `/project-init` on an unfamiliar repo to get full structural context before the first `/build` or `/design`. It produces the same cartographer files that would accumulate over multiple sessions, tagged as structural scaffolding that gets replaced by task-verified content over time.

Individual skills can also be used standalone (e.g., `test-driven-development` for any implementation work, `debugging` for any bug).

## Eval Results

Every crucible skill is evaluated using [Anthropic's official skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (`skill-creator`). This is the same eval methodology Anthropic built for measuring whether skills actually improve output quality — we use it here to prove that crucible's skills deliver measurable value, not just vibes.

### How It Works

The framework runs a **blind A/B test** for each skill:

1. **With skill** — the prompt is executed following the skill's full methodology
2. **Without skill** — the same prompt is given to the model with no skill instructions
3. **Grading** — an independent grader agent scores both outputs against identical expectations, with no knowledge of which condition it's grading

This isolates the skill's contribution. If both conditions score the same, the skill isn't adding value. If the skill condition scores higher, the delta quantifies exactly how much the methodology helps.

### What Gets Measured

Expectations are a mix of **process assertions** and **domain-correctness assertions**:

- **Process** — did the output follow the right methodology? (e.g., "iterates until clean or stagnation", "red-green-refactor cycles visible")
- **Domain correctness** — is the output actually *right*? (e.g., "fix uses parameterized queries", "plan includes database migration for roles")

This dual approach prevents skills from gaming the eval by producing well-formatted garbage. The process has to be right *and* the output has to be correct.

### Iteration 1 — Skill-Value Deltas (Claude Opus 4.6)

10 skills, 35 evals, graded blind.

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
| red-team | 51% | 49% | **2%** | Model already red-teams well without structure |

### Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions. The model already knows the right answers — skills add the methodology and discipline to consistently surface them. A quality gate that iterates three rounds of red-teaming catches issues that a single-pass review misses, even though the model *could* have found them on the first pass.

**Skill value scales inversely with model capability.** The deltas above are measured against Claude Opus — the strongest model available. On weaker models (Sonnet, Haiku, or non-Anthropic models in tools like Cursor), the structured methodology becomes scaffolding that keeps the model on track. A 2% delta on Opus could be a 20%+ delta on a model that doesn't naturally red-team well.

**Process-heavy skills show the largest deltas.** Skills that encode multi-step iterative workflows (quality-gate at 82%, innovate at 67%) benefit most from structure. Skills where the model's baseline behavior already approximates the methodology (red-team at 2%) show minimal lift.

### Running Evals

Eval definitions live in `skills/<skill>/evals/evals.json`. To run evals yourself, use Anthropic's [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) — it handles execution, grading, benchmarking, and iteration.
