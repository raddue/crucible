# Eval Results

13 core Crucible skills are evaluated using [Anthropic's official skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (`skill-creator`). This is the same eval methodology Anthropic built for measuring whether skills actually improve output quality — we use it here to prove that Crucible's skills deliver measurable value, not just vibes.

## How It Works

The framework runs a **blind A/B test** for each skill:

1. **With skill** — the prompt is executed following the skill's full methodology
2. **Without skill** — the same prompt is given to the model with no skill instructions
3. **Grading** — an independent grader agent scores both outputs against identical expectations, with no knowledge of which condition it's grading

This isolates the skill's contribution. If both conditions score the same, the skill isn't adding value. If the skill condition scores higher, the delta quantifies exactly how much the methodology helps.

## What Gets Measured

Expectations are a mix of **process assertions** and **domain-correctness assertions**:

- **Process** — did the output follow the right methodology? (e.g., "iterates until clean or stagnation", "red-green-refactor cycles visible")
- **Domain correctness** — is the output actually *right*? (e.g., "fix uses parameterized queries", "plan includes database migration for roles")

This dual approach prevents skills from gaming the eval by producing well-formatted garbage. The process has to be right *and* the output has to be correct.

## Skill-Value Deltas (Claude Opus 4.6)

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

## Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions. The model already knows the right answers — skills add the methodology and discipline to consistently surface them. Quality-gate's without-skill baseline scored 0/42 on process expectations (iterative rounds, severity tracking, stagnation detection, fix journals) while passing most domain-correctness expectations. The model finds the issues but never iterates.

**Process-heavy skills show the largest deltas.** Skills encoding multi-step iterative workflows (quality-gate +68%, TDD +53%, planning +39%) benefit most from structure. Skills where the model's baseline behavior already approximates the methodology (verify +0%) show minimal lift. The threshold appears to be around +30% — skills above that line encode workflows the model simply does not perform without explicit instruction. Red-team's delta moved from +2% to +13% after adding the steel-man-then-kill protocol (forces deeper reasoning per finding) and bidirectional severity calibration (prevents inflation on clean artifacts while promoting real design flaws with silent failure modes).

## Sequence Evals: Ordering Discipline Under Pressure

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

## Running Evals

Eval definitions live in `skills/<skill>/evals/evals.json`. Execution evals use the standard `prompt`/`expected_output`/`expectations` schema. Sequence evals extend this with `boundary`, `pressure_type`, `expected_sequence` metadata and categorized expectations (`sequence_compliance`, `pressure_resistance`, `correctness`) for per-axis grading.

To run evals yourself, use Anthropic's [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) — it handles execution, grading, benchmarking, and iteration.
