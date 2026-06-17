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
| inquisitor | 85% | 93% | **−8%** | This run executed as a single agent (no nested dispatch occurred), so the skill's core value — multi-agent cross-component *dispatch* — wasn't exercised, while the 4.8 baseline reviews the diff strongly on its own. The remaining gap is within grading noise (n=27, a 2-assertion swing); treat as ≈0, not a regression (was +11% on 4.6). A dedicated harness (#424) has since exercised the dispatch directly: Phase 1 found no *identification-breadth* lift from the fan-out, and Phase 1b found no lift from the dimension *taxonomy* — but Phase 1b's execution measurement shows a real **+29 pp lift (execution harness, detection axis) from parallel test-writing breadth** over a bare baseline — see *Inquisitor Fan-Out* / *Phase 1b* below |

## Key Findings

**Skills add process, not knowledge.** Domain-correctness assertions pass at similar rates for both conditions — the model already knows the right answers; skills add the methodology and discipline to consistently surface them. Quality-gate is the clearest example: the without-skill baseline finds many of the same issues but almost never *iterates* (no rounds, no severity tracking, no stagnation check, no fix journal), so it passes domain-correctness while failing the process assertions the skill exists to enforce.

**Process-heavy skills show the largest deltas.** Skills encoding multi-step iterative workflows (quality-gate +55%, TDD +44%, design +36%, audit +34%) benefit most from structure. Skills whose baseline behavior already approximates the methodology on a strong model (planning +0%, verify −4%, inquisitor −8%) show no measurable lift — and as the base model gets stronger those deltas shrink toward zero (planning fell from +39% on 4.6 to +0% on 4.8). The skills above the ~+13% line encode workflows the model does not reliably perform unprompted; the skills below it encode discipline the model now largely self-supplies on Opus 4.8 but would still need on weaker models. (Inquisitor is the exception that proves the rule: its **single-agent** suite delta is ≈0, but its dedicated execution harness shows a **+29 pp** lift (detection axis) once the parallel fan-out actually fires — the lift lives in the multi-agent breadth the single-agent suite never exercises. See *Phase 1b* below.)

## Inquisitor Fan-Out: A Direct Identification-Breadth Measurement (#424, Claude Opus 4.8)

The inquisitor row above (**−8%**) came from the standard single-agent execution suite, where the skill's core mechanism — the 5-way parallel cross-component *dispatch* — never fired. A dedicated three-arm harness (`skills/inquisitor/evals/`) measures that mechanism directly: it stages the real fan-out and grades each arm against a blind, **skill-independent ground-truth bug list** (K=19 bugs across 3 feature diffs), authored from the raw diffs rather than inquisitor's dimension taxonomy. Phase 1 measures **identification breadth only** — dimension agents *describe* tests but do not run them (the fixtures are text diffs with no runner).

- **WITH** — the real 5-way dimension fan-out + a 6th aggregation agent
- **MID** — one agent applying all 5 lenses sequentially + the same aggregation framing (holds the scaffolding constant, varying only the fan-out delivery)
- **WITHOUT** — one bare, neutralized-baseline agent

**Result (5 trials, majority-collapsed per bug):**

| Arm | Bugs identified | Rate |
|-----|-----------------|------|
| WITH (fan-out) | 17 / 19 | 0.895 |
| MID (1 agent, all lenses) | 17 / 19 | 0.895 |
| WITHOUT (bare prompt) | 19 / 19 | **1.000** |

| Paired delta | Mean | Per-trial spread | Noise floor (no-α) | Outside noise? |
|---|---|---|---|---|
| WITH − MID (the fan-out itself) | **0.00** | [−0.11, +0.16] | 0.086 | no |
| WITH − WITHOUT (total methodology) | **−0.04** | [−0.11, 0.00] | 0.051 | no |

**The fan-out adds no identification breadth on Opus 4.8.** Five parallel fresh subagents (WITH) identified the same *net count* of bugs as one sequential all-lenses agent (MID) — net paired delta WITH−MID = 0.00 — so the dispatch's extra cost (5 dimension agents + an aggregation pass vs one) buys nothing *for bug identification*. They were not, however, the same bug *set*: the two arms diverged per-fixture in offsetting directions (MID caught one bug on fixture 1 that WITH missed; WITH caught one bug on fixture 3 that MID missed — one bug each way, netting to ~0), so the fan-out was not strictly dominated — but the net breadth delta is still zero and inside the noise. The full methodology landed slightly *below* a bare "review this diff for cross-component bugs" prompt (−0.04), and that bare prompt identified **all 19** bugs. No delta clears the re-run noise band (`beyond_spread` false everywhere). This confirms the −8% was not merely an artifact of dispatch-not-firing: when the dispatch *does* fire, it still adds nothing on this axis. (The judges' prose preambles produced asymmetric malformed-verdict counts — most on WITH — but malformed lines grade as FAIL, so the scoring is conservative against the fan-out, not for it.)

**Why this is inconclusive, not condemning.** (1) **Ceiling effect** — WITHOUT scored 100% on every fixture, so these diffs have no headroom to reveal a positive delta; on Opus 4.8 the bugs are salient enough that a bare prompt finds them all. (2) **Execution is unmeasured** — Phase 1 stubs the test-writing/running half, which is where the fan-out's value (independent agents writing and *running* targeted tests) would show. The on-/off-axis split does not rescue the result either: on off-axis bugs (outside the 5 lenses) WITH and MID each scored 8/9 vs WITHOUT's 9/9. Per #424's go/no-go, a non-positive Phase-1 delta escalates to **Phase 1b** — a one-time seeded-repo execution measurement — before any redesign/demotion; it is a bounded deferral, not a verdict that the skill has no value.

## Inquisitor Phase 1b: Execution Measurement Resolves It — Verdict KEEP (#424, Claude Opus 4.8)

Phase 1b has now run, and it closes the two gaps that made Phase 1 inconclusive. It replaces the text-diff fixtures with **three seeded Python repositories** so agents actually *write and run* pytest tests (the half of the skill Phase 1 stubbed), and it **softens the fixtures** until a no-skill baseline leaves real headroom (breaking the WITHOUT=100% ceiling). It also adds a fourth arm to separate two things Phase 1 conflated — parallel *breadth* versus the dimension *taxonomy*:

- **WITH** — the real 5-way dimension fan-out (each agent a different lens)
- **POOL** — 5 *undifferentiated* agents: same parallel breadth, no dimension labels (isolates "does the fan-out help" from "do the dimension *labels* help")
- **MID** — one agent, all 5 lenses, sequential
- **WITHOUT** — one bare, neutralized-baseline agent

Each arm's test files are harvested and re-run by a **leave-one-out differential oracle** against pristine fixture variants: a bug counts as caught only if a test is red on the buggy code, green when the code is fixed, and red again when that one bug is reintroduced (no LLM judge — agent self-report is decoupled from scoring). 4 arms × 3 repos × 5 trials = 60 cells; **180 producer agents** (WITH and POOL run 5 test-writers per cell, MID and WITHOUT 1 each), K=24 graded bugs (6 on-axis + 2 off-axis per repo).

**Result (5 trials, leave-one-out oracle):**

| Arm | Bugs caught | Rate | On-axis only (18) |
|-----|-------------|------|-------------------|
| WITH (5-dim fan-out) | 15 / 24 | **0.625** | 11 / 18 = 0.611 |
| POOL (5 undiff. agents) | 15 / 24 | 0.625 | 11 / 18 = 0.611 |
| MID (1 agent, all lenses) | 11 / 24 | 0.458 | 8 / 18 = 0.444 |
| WITHOUT (bare prompt) | 9 / 24 | **0.375** | 6 / 18 = 0.333 |

| Paired delta | Mean | Noise floor (MDE) | Outside noise? |
|---|---|---|---|
| WITH − WITHOUT (deployment) | **+0.292** | 0.129 | **yes** |
| WITH − POOL (the dimension taxonomy) | +0.05 | 0.048 | no |
| WITH − MID (fan-out vs one agent) | +0.225 | 0.066 | — |

**Verdict: KEEP.** WITH catches **62.5%** of seeded bugs vs the bare baseline's **37.5%** — a **+29 pp** paired lift (see below) that clears the re-run noise band (`beyond_spread` true) and holds with a **positive sign in all three repos** (notify +0.25, rbac +0.30, paginate +0.33). The headline **+29 pp** is the gate's statistic — the *paired* WITH−WITHOUT delta (0.2917), computed per trial then averaged — which is why it differs from the 25 pp you get by subtracting the two arm rates (62.5 − 37.5): those arm rates are *majority-vote-collapsed* (a bug counts for an arm only if it is caught in a majority of the repeated trials), whereas the paired delta averages each trial's raw (uncollapsed) catch-rate difference — so the gap is a majority-vote artifact, not a property of pairing. The baseline had real headroom this time (WITHOUT means **0.375 / 0.525 / 0.225** (notify / rbac / paginate) — all below the 0.70 ceiling), so the lift is signal, not a floor artifact. On-axis-only (stripping the off-axis bugs that dilute the headline) the delta holds at **+0.278** (arm-mean); the conjunction-inflation check finds one WITH test crediting ≥3 bugs (removing it leaves the delta intact), and zero tests were discarded as flaky or errored.

**The lift is breadth, not taxonomy.** WITH and POOL tie exactly at the aggregate rate (both 15/24), and their *paired* delta is a small +0.05 that does not clear the re-run band (MDE 0.048, `beyond_spread` false) — so no taxonomy lift is resolvable at this sample size, not a demonstrated zero. Both score above the single-agent arms. The value comes from running **five parallel test-writers**, not from the dimension *labels* that tell each one what to look for — a single agent given the full inquisitor framing (MID, 0.458) beats the bare baseline by only +0.08 (arm-mean). So Phase 1's finding survives in a sharper form: **no dimension-taxonomy lift is resolvable here, but the parallel execution breadth adds a real +29 pp** — exactly the half Phase 1 could not see because it stubbed the test-running and ceilinged the baseline. The verdict binds the **detection axis** only (triage/aggregation and the fix-cycle were out of scope and are not condemned). The breadth-vs-structure result carries forward to the minimalism investigation (#425).

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
