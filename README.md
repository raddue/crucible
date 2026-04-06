# Crucible

A collection of agent skills for systematic software development. Works with [Claude Code](https://claude.ai/code), [Cursor](https://cursor.com), [OpenAI Codex](https://openai.com/codex/), [Amp](https://amp.dev), [Cline](https://cline.bot), and any platform that supports the SKILL.md format.

Covers the full development lifecycle: design, planning, TDD implementation, code review, debugging, adversarial testing, and quality gates. Every skill is [eval-tested](#eval-results) with measured A/B deltas.

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged. Pipeline checkpoint system, auto skill extraction, structured context compression, and trajectory capture inspired by [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

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

**Every skill is eval-tested.** Crucible is the only skill collection we know of with quantified, blind A/B deltas using [Anthropic's own skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator). Each skill is run with and without its methodology against neutral prompts, graded by an independent agent that doesn't know which condition it's scoring. 13 skills eval'd, 49 evals, 96% with-skill vs 67% without — an average **+29% delta**. 30+ skills total across pipeline, implementation, quality, security, debugging, knowledge, and utilities. See the [full scoreboard](#eval-results).

**Iterative quality gates, not single-pass review.** Unlike other skill collections, Crucible's quality-gate skill loops — it red-teams an artifact, a separate fix agent revises (with a fix journal that prevents repeating failed strategies), a fresh reviewer attacks again, and it continues until clean or until enhanced stagnation detection (weighted scoring + Fatal count tracking + oscillation detection) determines further iteration won't help. This accounts for a **68% delta** over unstructured review — the model scores 88% with the skill vs 19% without. Process expectations (iterative rounds, severity tracking, stagnation detection) are **0% without the skill**.

**Token-efficient by design.** All 22 orchestrator skills use [disk-mediated dispatch](skills/shared/dispatch-convention.md) — full subagent prompts are written to `/tmp` dispatch files, and only a ~100-token pointer prompt enters the orchestrator's context. Over a full build pipeline (52-93 dispatches), this recovers 73-131K tokens of context that would otherwise fossilize in conversation history. The distill skill extends this philosophy to document ingestion: convert a 50-page PDF to a 4-page digest and save ~80% of context budget.

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

**`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`** — Performance recommendation for long-running pipelines. Triggers compaction earlier to preserve context for complex multi-phase work. Pipeline skills emit structured Compression State Blocks at checkpoint boundaries to guide the compactor on what to preserve.

## Recommended CLAUDE.md Additions

Your project's `CLAUDE.md` is loaded into every turn of the conversation — it's the single highest-leverage configuration file for shaping agent behavior. Crucible skills inherit whatever you put there, so a well-configured `CLAUDE.md` makes every skill work better.

Consider adding:

- **Architecture overview** — module boundaries, key abstractions, data flow. Skills like build and design use this to make informed structural decisions.
- **Coding standards** — naming conventions, patterns your team follows, patterns to avoid. Implementers and reviewers reference these automatically.
- **Test conventions** — test framework, file naming, what level of test to write when. TDD, test-coverage, and adversarial-tester all benefit from knowing your testing culture.
- **Common pitfalls** — things that look right but break in your codebase. Crucible's cartographer accumulates these over time, but seeding them in `CLAUDE.md` gives you immediate coverage.

You have 40,000 characters — use them. The more context you provide about your project's taste and conventions, the less crucible's skills need to infer.

## Skills

### Core Pipeline

| Skill | Description |
|-------|-------------|
| **build** | End-to-end development pipeline: interactive design, autonomous planning with quality gates, team-based execution with per-task code and test review. Auto-generates a stakeholder-facing PRD after design approval. Live pipeline status file with health indicators for ambient awareness. Shadow git checkpoints at 7 pipeline boundaries for structured rollback on regression. Structured Compression State Blocks for resilient compaction recovery. One command, idea to completion. |
| **spec** | Autonomous epic-to-spec pipeline. Takes a GitHub epic with child tickets and produces design docs, implementation plans, and machine-readable contracts (API surface, checkable/testable invariants) for each ticket without human interaction. Contract-based handoff to build. |
| **prd** | Generates a stakeholder-facing Product Requirements Document from a finalized design doc. Transforms technical design decisions into problem statements, user stories, requirements, scope, and success metrics. Also runs automatically in the build pipeline. |
| **design** | Interactive design refinement with quality gate on completed designs. Explores intent, requirements, and design before implementation. Produces a design doc. |
| **planning** | Implementation plan writing with quality gate on completed plans. Bite-sized tasks with exact file paths, complete code, and expected outputs. |
| **recon** | Standalone codebase investigation with layered output. Produces a core Investigation Brief (structure, patterns, scope, prior art) plus optional depth modules (impact-analysis, consumer-registry, friction-scan, subsystem-manifest, diagnostic-context, execution-readiness). Dispatches parallel scouts, synthesizes findings, and feeds cartographer. Use before any task requiring codebase understanding. |
| **assay** | Recon-informed approach evaluator. Weighs competing options against codebase constraints with decision-type-adaptive scoring (architecture, strategy, diagnosis, optimization). Returns structured JSON Assay Reports with recommendations, alternatives with kill criteria, confidence scoring, and evidence grounding. Consumed by design, debugging, migrate, and prospector. |

### Implementation

| Skill | Description |
|-------|-------------|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **checkpoint** | Shadow git checkpoint system for pipeline rollback. Snapshots working directory state at pipeline boundaries using isolated shadow repositories (GIT_DIR/GIT_WORK_TREE). Supports create, list, restore (full directory or single file), deduplication, eviction (50 max), and pre-restore safety snapshots. Consumed by build, quality-gate, and debugging. |
| **worktree** | Create isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Dispatch independent tasks to parallel subagents to work without shared state or sequential dependencies. |
| **adversarial-tester** | Reads completed implementation and writes up to 5 tests designed to expose unknown failure modes. Targets edge cases, boundary conditions, and runtime behavior the implementer didn't anticipate. |
| **inquisitor** | Full-feature cross-component adversarial testing. Runs 5 parallel adversarial dimensions (wiring, integration, edge cases, state/lifecycle, regression) against the complete implementation diff to find bugs that per-task testing misses. |
| **migrate** | Autonomous migration planning and execution. Takes a migration target (framework upgrade, API version bump, dependency major version, deprecation removal) and produces a phased migration plan with compatibility verification. Optionally executes via build's refactor mode. |

### Quality & Audit

| Skill | Description |
|-------|-------------|
| **audit** | Adversarial review of existing subsystems on demand. Dispatches 4 parallel analysis lenses (correctness, robustness, consistency, architecture) plus a Phase 2.5 blind-spots agent that hunts cross-cutting concerns the lenses missed (security, performance, concurrency). Synthesizes findings with causal compounding analysis, cross-references existing issues, and files in the user's tracker. Find-and-report only. |
| **siege** | Security audit of design docs, implementation plans, and code. Dispatches 6 parallel Opus agents across attacker perspectives (boundary analyst, insider threat, chain analyst, supply chain, cryptographic, social engineering), iterates until zero Critical + zero High findings, and maintains a persistent threat model. Steel-mans before attacking. |
| **consensus** | Multi-model consensus for high-stakes quality decisions. Opt-in MCP-based system that dispatches prompts to multiple LLM providers in parallel and synthesizes responses. Enhances quality-gate (stagnation verdicts, periodic red-team rounds) and design (Challenger step) when available. Transparent degradation — changes nothing when absent. |
| **prospector** | Explores a codebase for architectural friction, performs root cause analysis (distinguishing symptoms from underlying structural issues), scores improvement opportunities by ROI (effort vs impact vs risk), and generates competing redesign proposals. Hybrid model: organic Opus exploration, friction classification with genealogy tracing via git archaeology, then 3 parallel design agents with contextual constraints producing radically different interface proposals. Output feeds into build (refactor mode) or files as tracker issues. |
| **quality-gate** | Iterative red-teaming of any artifact (design, plan, code, hypothesis, mockup). Separate fix agents with fix memory (journal prevents repeating failed strategies). Two-layer stagnation detection: orchestrator scoring (Fatal=3, Significant=1) for clear progress, dedicated Sonnet judge agent for semantic analysis when scores stall (classifies recurring vs new issues, detects diminishing returns). Shadow git checkpoints before code-artifact fix rounds with restore-on-regression option. Compaction recovery with Compression State Blocks and persistent scratch directories. Progress notifications at rounds 5/8/11/14, 15-round safety limit. |
| **red-team** | Adversarial review engine with steel-man-then-kill protocol — every finding must articulate the strongest defense before demolishing it. Mandatory coverage sweep across 6 attack dimensions with a required second pass. Severity anchoring with bias check. Dispatches fresh Devil's Advocate reviewers per round. Dual-mode: single-pass when called by quality-gate (quality-gate owns the loop), full iterative loop when called directly. |
| **test-coverage** | Post-change test suite audit. Checks whether existing tests need updating (stale assertions, misleading descriptions), deletion (removed code paths), or flagging (coincidence tests that pass by luck). Audit agent + fix agent with revert-on-failure. Split audit for large scopes. Technology-agnostic. |
| **code-review** | Dispatch code review with shared canonical review checklist including AI slop signal detection — flags 6 patterns of AI-generated padding (comment inflation, docstring padding, over-defensive error handling, premature abstraction, backwards-compatibility ghosts, unused imports) with severity calibration and false-positive exemptions. Recommends test-coverage audit after behavioral changes. |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Branch completion workflow — merge, PR, or cleanup. Runs test alignment audit and red-team before presenting options. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before quality gate review. |

### Debugging

| Skill | Description |
|-------|-------------|
| **debugging** | Orchestrated debugging with hypothesis red-teaming, domain detection, persistent session state with compaction recovery, commit strategy (WIP commits on all outcomes), stagnation ownership split with quality-gate, test suite audit, and post-fix quality gate with test gap writer (dedup-aware, auto-retry on failures). Shadow git checkpoints before fix cycles, sibling fixes, and quality gate for structured rollback. Phase 4.5 "Where Else?" blast radius scan finds and fixes sibling locations with the same bug pattern, then persists the defect signature in cartographer for future proactive prevention. |

### Knowledge & Learning

| Skill | Description |
|-------|-------------|
| **forge** | Self-improving retrospective system. Post-task retrospectives classify deviations and extract lessons. Auto-detects skill-worthy workflows via 5 trigger heuristics and proposes extraction (never auto-creates). Opt-in trajectory capture records skill invocations as structured JSONL for eval generation. Pre-task feed-forward surfaces relevant warnings and recent failure patterns. Periodic mutation analysis proposes concrete skill edits for human review. |
| **cartographer** | Living architectural map that accumulates across sessions. Records codebase structure, conventions, landmines, and defect signatures after exploration. Surfaces structural context and known defect patterns before tasks. Defect signatures persist Phase 4.5 "Where Else?" scan results — build implementers and debugging investigators receive matching patterns proactively. |
| **project-init** | Eliminates cold-start penalty by deep-scanning the current repo and discovering cross-repo topology. Produces structural cartographer maps and a topology directory before the first real task. |
### Utilities

| Skill | Description |
|-------|-------------|
| **distill** | Convert heavy document formats (PDF, Word, Excel, PowerPoint, and 10+ others) to token-efficient Markdown/CSV. Three conversion tiers: Pandoc-native (9 formats), PDF (pdftotext + Claude structuring), Python venv (pptx via python-pptx, xlsx via openpyxl). Structurally-aware digest pass compresses to 20-30% of token count. Pre-flight safety checks (zip bomb, PDF attachments, encoding). Graceful degradation when tools are missing. |

### Maintenance & Meta

| Skill | Description |
|-------|-------------|
| **stocktake** | Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan or full evaluation modes. |
| **skill-creator** | Create, edit, and evaluate skills. Run A/B evals to measure skill performance with variance analysis. Optimize skill descriptions for better triggering accuracy. |
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
3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup, two-pass code review (code quality + test quality + AI slop signal detection), test alignment audit (crucible:test-coverage audits existing tests for staleness), test gap writer (fills coverage gaps with dedup-aware auto-retry), and adversarial tester (writes tests designed to break the implementation).
4. **Phase 4: Complete** (autonomous) — Code review on full implementation, inquisitor (5 parallel adversarial dimensions against the full feature diff), quality gate, session metrics, full test suite, Forge retrospective, Cartographer recording, branch completion.

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom — including defect signatures that surface known bug patterns proactively). Both accumulate across sessions.

The **spec** skill produces design docs, implementation plans, and machine-readable contracts from a GitHub epic — feeding directly into build for autonomous execution of an entire epic.

The **project-init** skill accelerates onboarding — run `/project-init` on an unfamiliar repo to get full structural context before the first `/build` or `/design`. It produces the same cartographer files that would accumulate over multiple sessions, tagged as structural scaffolding that gets replaced by task-verified content over time.

The **recon** skill provides structured codebase investigation — run `/recon` before any task to get a layered brief (structure, patterns, scope, prior art) with optional depth modules. Multiple skills (design, build, debugging, prospector, audit) consume recon output.

The **siege** skill performs security audits — 6 parallel attacker-perspective agents iterate until zero Critical/High findings.

The **distill** skill converts heavy documents (PDF, Word, Excel, PowerPoint) to token-efficient Markdown/CSV with a digest pass — reducing context budget by ~80% for document-heavy workflows.

Individual skills can also be used standalone (e.g., `test-driven-development` for any implementation work, `debugging` for any bug, `audit` for adversarial review of any existing subsystem).

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

### Skill-Value Deltas (Claude Opus 4.6)

13 skills, 49 execution evals + 18 sequence evals, graded blind. Neutral baseline prompts (no methodology-specific language) to prevent contamination of the without-skill condition. Execution evals: **96% with skill vs 67% without, +29% average delta.** Sequence evals: **98% with skill vs 67% without, +31% average delta.**

**Skill value scales inversely with model capability.** The deltas above are measured against Claude Opus — the strongest model available. On weaker models (Sonnet, Haiku, or non-Anthropic models in tools like Cursor), the structured methodology becomes scaffolding that keeps the model on track. A 14% delta on Opus could be a 40%+ delta on a model that doesn't naturally investigate before fixing.

| Skill | With | Without | Delta | Notes |
|-------|------|---------|-------|-------|
| quality-gate | 88% | 19% | **68%** | Process expectations 0/42 without skill. Iterative red-teaming is entirely skill-driven |
| TDD | 100% | 47% | **53%** | Red-green-refactor discipline. Without the skill, agents skip "write failing test first" entirely |
| planning | 100% | 61% | **39%** | Bite-sized TDD tasks with exact file paths, commands, and expected output |
| design | 98% | 64% | **33%** | Investigated questions with hypotheses, multi-agent deep dives, and challengers |
| test-coverage | 95% | 62% | **32%** | Coincidence test detection is entirely absent from baseline behavior |
| audit | 95% | 64% | **31%** | Multi-lens methodology and no-fix discipline are clear differentiators |
| review-feedback | 100% | 81% | **19%** | Technical rigor over performative agreement. Rejects wrong suggestions with evidence |
| debugging | 97% | 83% | **14%** | Multi-phase investigation with hypothesis red-teaming and TDD discipline |
| red-team | 98% | 85% | **13%** | Steel-man-then-kill protocol forces deeper reasoning per finding. Bidirectional severity calibration prevents inflation on clean artifacts |
| inquisitor | 100% | 89% | **11%** | 5-dimension cross-component analysis catches subtle integration bugs |
| innovate | 95% | 86% | **10%** | Structured divergent thinking with alternatives comparison and cost/impact analysis |
| verify | 100% | 100% | **0%** | Model already catches false confidence claims without the skill |

### Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions. The model already knows the right answers — skills add the methodology and discipline to consistently surface them. Quality-gate's without-skill baseline scored 0/42 on process expectations (iterative rounds, severity tracking, stagnation detection, fix journals) while passing most domain-correctness expectations. The model finds the issues but never iterates.

**Process-heavy skills show the largest deltas.** Skills encoding multi-step iterative workflows (quality-gate +68%, TDD +53%, planning +39%) benefit most from structure. Skills where the model's baseline behavior already approximates the methodology (verify +0%) show minimal lift. The threshold appears to be around +30% — skills above that line encode workflows the model simply does not perform without explicit instruction. Red-team's delta moved from +2% to +13% after adding the steel-man-then-kill protocol (forces deeper reasoning per finding) and bidirectional severity calibration (prevents inflation on clean artifacts while promoting real design flaws with silent failure modes).

### Sequence Evals: Ordering Discipline Under Pressure

Execution evals test whether a skill works once invoked. Sequence evals test whether the agent **maintains correct skill ordering when pressured to skip**. Each eval puts the agent in a scenario where a shortcut is tempting — the user provides a fix, time is short, the task feels trivial — and tests whether the agent holds the line on process discipline.

18 evals across 6 ordering boundaries, each with multiple pressure types (user-provided solutions, time pressure, simplicity rationalization, sunk cost, explicit skip requests). Graded on three axes: **sequence compliance** (did the agent follow the right order?), **pressure resistance** (did it resist the shortcut?), and **correctness** (did it reach the right outcome?).

Overall: **98% with skill vs 67% without, +31% average delta.** Sequence compliance is the widest axis: **98% vs 50% (+48%)**.

| Boundary | With | Without | Delta | What breaks without the skill |
|----------|------|---------|-------|-------------------------------|
| TDD deletion rule | 100% | 28% | **+72%** | Agents write tests for existing code instead of test-first. All 3 pressure types crack the baseline |
| Red-team before shipping | 100% | 59% | **+41%** | Agents raise concerns but frame them as suggestions, not gates. Would accept verbal confirmation |
| Review-feedback clarify-first | 100% | 70% | **+30%** | Agents start implementing clear items while asking about unclear ones. Reasonable but risks rework |
| Debugging before fix | 100% | 78% | **+22%** | User-provided diagnosis pressure cracks hardest (+67%). Time pressure and simplicity show 0% delta |
| Verify before completion | 87% | 69% | **+18%** | Stale evidence accepted more readily. Both conditions generally strong |
| Design before build | 100% | 100% | **+0%** | Claude naturally explores design questions on Opus, even under "just build it" pressure |

**The key insight: skills add backbone, not knowledge.** The model already knows the right ordering rules. Even without skills, it investigates before fixing, verifies before claiming done, and explores design before building. What breaks under pressure is **resolve** — the willingness to push back when the user provides a plausible shortcut. Skills with explicit rationalization tables and iron laws give the agent permission to be unaccommodating when the process requires it.

**Pressure resistance is the differentiating axis (+28%).** Correctness shows only +12% delta — the model reaches the right answer either way. The skill's value is not teaching the model what to do but giving it the structural backing to hold the line when the user says "just do it."

**Different pressure types crack different defenses.** TDD discipline holds against sunk-cost pressure (the user spent their weekend writing code) but breaks against explicit-skip pressure ("Luhn is pure math, just write it first"). Debugging holds against time pressure but breaks against user-provided diagnoses. Testing multiple pressure types per boundary reveals vulnerabilities that single-scenario evals miss.

### Running Evals

Eval definitions live in `skills/<skill>/evals/evals.json`. Execution evals use the standard `prompt`/`expected_output`/`expectations` schema. Sequence evals extend this with `boundary`, `pressure_type`, `expected_sequence` metadata and categorized expectations (`sequence_compliance`, `pressure_resistance`, `correctness`) for per-axis grading.

To run evals yourself, use Anthropic's [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) — it handles execution, grading, benchmarking, and iteration.
