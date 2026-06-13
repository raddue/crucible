# Eval Results

Crucible skills are evaluated using [Anthropic's official skill evaluation framework](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (`skill-creator`). 12 skills carry **execution evals** (the table below); a separate **sequence-eval** suite covers ordering boundaries (further down). This is the same eval methodology Anthropic built for measuring whether skills actually improve output quality — we use it here to prove that Crucible's skills deliver measurable value, not just vibes.

## How It Works

The framework runs a **blind A/B test** for each skill:

1. **With skill** — a neutralized task (methodology-specific language stripped) is executed with the skill's full methodology applied
2. **Without skill** — the same neutralized task is given to the model with no skill instructions
3. **Grading** — each output is scored by an independent blind grader against identical expectations, with no knowledge of which condition it's grading

Neutralizing the task (so neither arm is *told* to "run a quality gate" or "run the inquisitor") is what isolates the skill itself rather than the prompt's wording.

This isolates the skill's contribution. If both conditions score the same, the skill isn't adding value. If the skill condition scores higher, the delta quantifies exactly how much the methodology helps.

## What Gets Measured

Expectations are a mix of **process assertions** and **domain-correctness assertions**:

- **Process** — did the output follow the right methodology? (e.g., "iterates until clean or stagnation", "red-green-refactor cycles visible")
- **Domain correctness** — is the output actually *right*? (e.g., "fix uses parameterized queries", "plan includes database migration for roles")

This dual approach prevents skills from gaming the eval by producing well-formatted garbage. The process has to be right *and* the output has to be correct.

## Skill-Value Deltas (Claude Opus 4.8 — re-measured 2026-06-13)

12 execution-eval skills, 52 evals, 475 assertions, graded blind. Both conditions receive the **same neutralized task** — methodology-specific language ("run a quality gate", "run the inquisitor") and any evaluator hints are stripped, so the without-skill arm is never told which methodology to run; the only difference between arms is whether the skill is applied. **Execution evals: 93% with skill vs 70% without, +23% overall delta.**

> This section previously reported the Claude Opus 4.6 run (**+29%** overall). The same suite on the stronger Opus 4.8 base model compresses to **+23%** — consistent with the inverse-capability thesis below and pointing in the direction it predicts. This is suggestive, not a controlled proof: the two runs differ in more than the base model (the methodology was also corrected between them), so the 6-point move can't be cleanly attributed to capability alone. The 4.6 figures remain in git history. The **sequence evals** further down have **not** been re-run on 4.8 and still reflect Opus 4.6.

**Skill value scales inversely with model capability.** The structured methodology is scaffolding that keeps a model on track; the more capable the base model, the less lift it adds. The same suite moved **+29% on Opus 4.6 → +23% on Opus 4.8** — one datapoint consistent with that thesis (with the methodology caveat above, not a controlled comparison). The trend is not monotonic: the overall delta compressed, but a few individual skills' deltas rose on the stronger model. On weaker models (Sonnet, Haiku, or non-Anthropic models in tools like Cursor), we *expect* the deltas to widen substantially — a skill that adds little on Opus could project to a much larger delta on a model that doesn't natively follow that discipline. That widening is a prediction, not yet measured.

| Skill | With | Without | Delta | Notes |
|-------|------|---------|-------|-------|
| quality-gate | 93% | 38% | **+55%** | Iterative red-teaming is entirely skill-driven; the baseline does one review pass and stops. Largest delta even on the strongest model |
| TDD | 94% | 50% | **+44%** | Red-green-refactor discipline. Without the skill, agents write code-then-tests or skip "write failing test first" |
| design | 100% | 64% | **+36%** | Investigated questions with hypotheses, multi-agent deep dives, and challengers vs a single one-shot design |
| audit | 72% | 38% | **+34%** | Multi-lens methodology and no-fix discipline. (Absolute with-rate is capped because the multi-lens protocol is partly dispatch-based and this run executed as a single agent with no nested fan-out — so the multi-agent value wasn't exercised here — but the delta over baseline is still large) |
| test-coverage | 92% | 73% | **+19%** | Coincidence/alignment-gap detection; the baseline checks surface coverage only |
| innovate | 100% | 86% | **+14%** | Structured divergent alternatives with cost/impact analysis vs a shorter improvement list |
| debugging | 96% | 83% | **+13%** | Multi-angle investigation before forming a hypothesis. The 4.8 baseline is already strong here but less systematic |
| review-feedback | 100% | 95% | **+5%** | Near-ceiling baseline on 4.8 — the model already rebuts wrong suggestions with evidence; small residual lift |
| red-team | 93% | 88% | **+5%** | The 4.8 baseline already finds most issues; steel-man-then-kill adds a modest edge (was +13% on 4.6) |
| planning | 100% | 100% | **+0%** | On 4.8 the baseline already produces bite-sized, well-specified plans; the structure no longer adds measurable lift (was +39% on 4.6 — the clearest case of capability erasing a delta) |
| verify | 96% | 100% | **−4%** | Within grading noise (n=27, a 1-assertion swing). The model catches false-confidence claims with or without the skill — was +0% on 4.6 |
| inquisitor | 85% | 93% | **−8%** | This run executed as a single agent (no nested dispatch occurred), so the skill's core value — multi-agent cross-component *dispatch* — wasn't exercised, while the 4.8 baseline reviews the diff strongly on its own. The remaining gap is within grading noise (n=27, a 2-assertion swing); treat as ≈0, not a regression (was +11% on 4.6) |

## Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions — the model already knows the right answers; skills add the methodology and discipline to consistently surface them. Quality-gate is the clearest example: the without-skill baseline finds many of the same issues but almost never *iterates* (no rounds, no severity tracking, no stagnation check, no fix journal), so it passes domain-correctness while failing the process assertions the skill exists to enforce.

**Process-heavy skills show the largest deltas.** Skills encoding multi-step iterative workflows (quality-gate +55%, TDD +44%, design +36%, audit +34%) benefit most from structure. Skills whose baseline behavior already approximates the methodology on a strong model (planning +0%, verify −4%, inquisitor −8%) show no measurable lift — and as the base model gets stronger those deltas shrink toward zero (planning fell from +39% on 4.6 to +0% on 4.8). The skills above the ~+13% line encode workflows the model does not reliably perform unprompted; the skills below it encode discipline the model now largely self-supplies on Opus 4.8 but would still need on weaker models.

## Sequence Evals: Ordering Discipline Under Pressure (Claude Opus 4.6)

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
