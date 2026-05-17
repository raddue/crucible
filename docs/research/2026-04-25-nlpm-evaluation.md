# NLPM-for-Claude Evaluation

**Date:** 2026-04-25
**Issue:** [#216](https://github.com/raddue/crucible/issues/216)
**Subject:** [xiaolai/nlpm-for-claude](https://github.com/xiaolai/nlpm-for-claude) (MIT, ~1 month old; 25 stars per `gh api repos/xiaolai/nlpm-for-claude` on 2026-04-25 — note: issue #216 body cites 22 stars; growth in the interim)
**Decision:** **Adopt the rule corpus (option B).** Skip the tooling integration. Re-evaluate scorer integration once the maintainer publishes more rules and case studies.

---

## TL;DR

The 50 R-rules are a genuinely good NL-artifact style guide. Triage breakdown: 35 rules already followed (a), 13 worth adopting (b — covered by 12 action lines because R19+R20 share one entry), 2 incompatible (c). The (b) bucket is what gets folded into `/skill-creator` and `/quality-gate` as cited checklist items; the (c) bucket — primarily R05's 500-line cap — represents friction with Crucible's orchestrator-skill topology that is real today but contestable on measured-token-cost grounds. We don't adopt the scorer wholesale until that measurement exists.

The scoring tooling itself — deterministic per-artifact penalty scoring — is suspect for Crucible specifically. The hard 500-line cap (R05) would mark every orchestrator skill we own as "context bloat," which is a topology disagreement, not a quality finding. Per-artifact scores also can't see the cross-skill orchestration that's the largest source of Crucible's measured value.

Adopting NLPM as a hard pre-merge gate would block legitimate orchestrator PRs. Adopting it as an optional manual tool offers little over "the user can install it themselves." Adopting the rule corpus as cited reference material in `/skill-creator` and `/quality-gate` is the highest-leverage option that doesn't require changing pipeline mechanics.

---

## Method

NLPM cloned to `/tmp` for source-only inspection. No Claude Code plugin install — that requires user authorization and modifies `~/.claude/`. Acceptance criteria that depend on actually running `/nlpm:score` are listed as **deferred for user execution** at the end of this doc.

What was done:
- Read `RULES.md`, `skills/nlpm/rules/SKILL.md` (full 50 rules), `skills/nlpm/scoring/SKILL.md` (penalty tables for 13 artifact types), `README.md`, command shells under `commands/`.
- Inventoried Crucible skill-file sizes against R05's 500-line threshold.
- Triaged each of the 50 rules into (a) already-followed, (b) worth adopting, (c) incompatible.
- Compared NLPM's audit model to Crucible's `/stocktake` and `/quality-gate`.

What is **not** in this evaluation:
- Actual `/nlpm:score` output against `skills/`.
- Actual `/nlpm:check` cross-component results.
- An NL-TDD trial run on a small skill.

These three remain as deferred acceptance items (see end).

---

## What NLPM Is

NLPM treats markdown-driven AI artifacts (skills, agents, commands, hooks, CLAUDE.md, prompts, plugin manifests) as programs that can be linted. Eight commands (`/nlpm:ls`, `/nlpm:score`, `/nlpm:check`, `/nlpm:fix`, `/nlpm:trend`, `/nlpm:test`, `/nlpm:init`, `/nlpm:security-scan`) operate on a 100-point deterministic penalty rubric across 13 artifact types.

Claude-native — no external models, no API keys. Same artifact, same penalties, same number. Default pass threshold 70.

The rule corpus is split into 11 sections: Universal (R01–R03), Skills (R04–R08), Agents (R09–R13), Commands (R14–R18), Shared Partials (R19–R20), Rules files (R21–R26), Hooks (R27–R32), CLAUDE.md (R33–R39), Prompts (R40–R42), Orchestration (R43–R47), Plugins (R48–R50).

---

## Triage of the 50 Rules

### (a) Already followed by Crucible — 35 rules

R01 (no vague quantifiers), R02 (every line earns tokens), R03 (positive framing) — Crucible's anti-rationalization tables and severity calibration rules already encode these.

R04 (description as trigger, not summary) — `/getting-started` enforces this and every Crucible skill description follows the "Use when X / triggers on Y" shape.

R10 (model matches task complexity) — Crucible's reviewer-model selection tables (`Reviewer Model Selection (Lead Decides Per-Task)` in build, similar tables in design and quality-gate) explicitly route by complexity tier. Note: R10 literally checks the `model:` frontmatter field on agent files; Crucible expresses model selection as runtime prose tables instead because it doesn't ship Claude Code agent files. Same intent, different mechanism.

R11 (least-privilege tools), R13 (mission → steps → boundaries → format prompt structure) — Crucible's dispatch prompt files (`build-implementer-prompt.md`, `build-reviewer-prompt.md`, etc.) follow this; would benefit from a slightly more rigorous audit but are mostly there.

R14 (numbered steps), R16 (exact output format), R17 (error paths), R18 (`argument-hint` for input-taking commands) — all standard in Crucible orchestrator skills.

R22 (rules must be enforceable), R26 (no internal conflicts) — Crucible's rules are stated as concrete actions, not exhortations.

R27 (case-sensitive event names), R28 (field name matches hook type), R29 (referenced scripts exist), R30 (`${CLAUDE_PLUGIN_ROOT}` for paths), R31 (fail-open), R32 (block on PreToolUse, advise on PostToolUse) — Crucible hooks (session-index, build-routing-advisor, safety-guard) follow these.

R33 (build/run command), R34 (test command), R35 (architecture overview), R36 (`@` imports resolve), R37 (no stale references), R38 (instructive over descriptive), R39 (no conflicts with rules) — `CLAUDE.md` (and the equivalents in user memory under `MEMORY.md`) follow these.

R40 (five-layer prompt structure), R41 (exact output format), R42 (injection resistance for untrusted input) — Crucible dispatch prompts are L1+ in the five-layer hierarchy.

R43 (parallel-when-independent), R44 (QC gate between AI and output), R45 (cost gate before expensive AI phases), R46 (state file for resumability), R47 (max retry count on loops) — Crucible's build/quality-gate/debugging implement all five explicitly: build's pipeline phases serialize while wave dispatches parallelize; quality-gate IS a QC gate; cost gates appear in build's metrics-tracking; pipeline-active markers + checkpoint files + dispatch manifests are the state file; quality-gate's 15-round safety limit is an R47 cap.

R48 (`name` as only required plugin manifest field) — applies to plugin packaging, would apply if Crucible publishes as a Claude plugin.

### (b) Worth adopting — 13 rules (12 action lines; R19+R20 share one entry)

R06 (code examples must be runnable, not pseudocode) — Crucible could be more rigorous about this in some skill bodies. Worth adding to `/skill-creator`'s checklist.

R07 (scope note when related skills exist) — Crucible has overlap between `audit`, `red-team`, `temper`, `siege`, and `quality-gate`. Cross-references exist but are inconsistent. Adopting R07 as a `/stocktake` audit dimension would surface dead pointers and missing pointers.

R08 (patterns over theory) — Crucible's larger orchestrator skills sometimes drift toward theory in their preamble sections. R08 as a quality-gate criterion for skill artifacts would catch this.

R09 (mandatory `<example>` blocks for agents) — Crucible doesn't ship Claude Code agent files, but the principle applies to dispatch prompt files. Cite R09 in `/skill-creator` for any prompt template authoring.

R12 (output format defined in body) — Crucible's dispatch prompt files mostly define output format but a few rely on implicit "report findings" framing. R12 as a `/quality-gate` check for prompt artifacts would catch the looser ones.

R19 + R20 (shared partials must declare `user-invocable: false` and a purpose-stating `description`) — Crucible has 11 files under `skills/shared/`. Verified frontmatter on `cairn-convention.md`, `dispatch-convention.md`, `return-convention.md`: each declares only `version: 1`. No `description`, no `user-invocable`. Under NLPM's Shared Partials penalty table this would produce -35 per partial (R19 missing `user-invocable: false` -25 + R20 description doesn't state purpose -10). This is the most concrete real-quality finding NLPM would surface against Crucible. Worth a one-pass audit + frontmatter pass across all 11 partials. Adopting R19 wholesale is the action; the (c) bucket below intentionally excludes R19 because the verified gap makes the convention-churn defense untenable.

R21 (bold imperative + rationale: "**Use X.** Without it, Y breaks because Z.") — Crucible's anti-rationalization tables already use this pattern. Worth standardizing across all rule statements in skill bodies.

R23 (rule files under 500 lines combined) — applies to `.claude/rules/` which Crucible doesn't use heavily. If we add a `.claude/rules/` directory, R23 is the budget.

R24 (don't duplicate tooling) — Crucible's pre-flight dependency audit in quality-gate already does this for npm/cargo/pip. R24 as a meta-rule for any future Crucible-shipped lint guidance.

R25 (path-scope rules when possible) — relevant for any future `.claude/rules/` work; defer.

R49 (CLAUDE.md for Claude, README for humans) — the README trim shipped in #215 (PR #221) just enforced this. Keep enforcing.

R50 (bump version in four places when shipping plugin) — applies if and when Crucible packages as a Claude plugin (currently pending marketplace review per `MEMORY.md`).

### (c) Incompatible with Crucible — 2 rules (plus a relocation note)

R05 (under 500 lines) — **friction with Crucible's orchestrator topology, deferred pending measurement.** Crucible orchestrator skill sizes:

| Skill | Lines | NLPM verdict |
|---|---|---|
| build/SKILL.md | 1466 | -10 (>500) |
| debugging/SKILL.md | 1032 | -10 (>500) |
| recon/SKILL.md | 935 | -10 (>500) |
| quality-gate/SKILL.md | 758 | -10 (>500) |
| audit/SKILL.md | 618 | -10 (>500) |
| forge/SKILL.md | 609 | -10 (>500) |
| finish/SKILL.md | 427 | -5 (400–500) |
| getting-started/SKILL.md | 93 | clean |

Crucible's design choice is that an orchestrator agent reads its skill once and gets the entire phased pipeline. Splitting `build/SKILL.md` into `build`, `build-design-phase`, `build-plan-phase`, `build-execute-phase`, `build-completion-phase` defeats the point — the orchestrator wouldn't see Phase 4 logic when starting Phase 1, would have to chain skill invocations, and would lose the cumulative invariants that make the pipeline coherent.

**Counter-argument worth engaging:** R05 itself recommends "Split into scoped sub-skills with cross-references." The NLPM-blessed pattern is `build` loading `build-design-phase.md`, `build-execute-phase.md` etc. via skill imports — the orchestrator *would* see all phases via cross-references, and could pay tokens only for the phase currently in flight. If 70% of `/build` invocations only need Phase 1 logic, the import pattern saves real runtime tokens. The objection isn't that splitting is impossible; it's that Crucible's cumulative invariants (Tripwire Manifest, Invariant Cairn, Receipt Linter rules that fire across phase boundaries) currently *assume* whole-pipeline visibility in one read. Splitting would require reworking the invariant-propagation mechanics, which is a real piece of work but not a categorical objection. A measured study comparing token cost of single-file vs. import-chain orchestrators would be the right basis for revisiting R05; until then, the conflict claim should read as "deferred pending measurement," not "topology disagreement."

R05 is uncontroversial for atomic-task skills; remains genuinely contested for multi-phase pipeline skills.

R15 (handle empty input — for commands that take input) — Crucible's slash-command skills handle this in skill body prose but not always with a defined empty-input branch. Many Crucible skills are designed to be invoked with arguments via build/spec/etc., not directly. Skip-but-watch.

(R19 was originally listed as incompatible on convention-churn grounds — moved to (b) above after frontmatter inspection confirmed the gap is real, the penalty is real, and the audit is finite scope.)

(Sub-rules under R09 / R10 / R12 about agent-file enforcement don't map because Crucible doesn't ship Claude Code `/agents/*.md` files. They map by analogy to dispatch prompt files and are covered under (b) R09/R12 — see above.)

---

## Penalty Model Concerns (separate from rules)

Even setting aside R05, three concerns make NLPM's penalty scores a poor pre-merge signal for Crucible:

1. **Per-artifact scores miss orchestration value.** Crucible's measured eval deltas (per `README.md`'s eval results table — slated to relocate to `docs/evals.md` after PR #221 merges: `quality-gate` +68%, `TDD` +53%, `planning` +39%) come from how skills compose, not from per-skill markdown quality. NLPM scores `build/SKILL.md` in isolation; it can't see that `build` invokes `design`, which invokes `recon`, which feeds `cartographer`. A high NLPM score on a skill that ships broken integration is worse than a low NLPM score on a skill that orchestrates well.

2. **Determinism cuts both ways.** Same artifact, same score is good for regression tracking (a -3 delta on a SKILL.md edit is meaningful). But the absolute number is anchored to the NLPM author's penalty priors, which were not derived from measured eval deltas. We cannot trust the absolute score; we can trust the delta-on-edit.

3. **`/stocktake` and `/quality-gate` already do most of this work.** `/stocktake` audits cross-skill structure (overlap, staleness, broken refs); `/quality-gate` runs adversarial reviews on artifacts. NLPM's `/nlpm:check` is a thinner version of `/stocktake`; `/nlpm:score` is a shallower version of `/quality-gate` for skill-shaped artifacts. The NL-TDD spec-first mode is interesting but overlaps with `skill-creator`'s existing eval loop.

---

## Decision: Adopt the Rule Corpus

**Action items, in order:**

1. Add a new file `skills/skill-creator/nlpm-rules-reference.md` containing the (b)-bucket rules (R06, R07, R08, R09, R12, R19, R20, R21, R23, R24, R25, R49, R50) with one-line "why this matters for Crucible" notes and a credit/link to the upstream NLPM repo (MIT compatibility verified — credit + link suffices). Note: the immediate concrete payoff is the R19+R20 frontmatter audit on `skills/shared/` — that work should ship as part of action item 1 or as its own follow-up ticket.
2. Update `/skill-creator` SKILL.md to load that file as a checklist when authoring new skills or major skill rewrites.
3. Update `/quality-gate`'s red-team prompt template (artifact type `design` and `code` when target is a skill file) to cite the (b)-bucket rules as additional review dimensions.
4. **Do not** integrate `/nlpm:score` into `/build` Phase 4, `/merge-pr`, or CI. R05 alone makes this block legitimate orchestrator changes.
5. Document the (a)-bucket alignment in `docs/architecture.md` or a new `docs/skill-quality-rubric.md` so future contributors know which conventions Crucible already enforces and which were imported from NLPM.

**Why not adopt fully:** Per-artifact-score blind-spot to orchestration value is the load-bearing reason — the scorer can't see the cross-skill composition that drives Crucible's measured eval deltas. R05's 500-line friction is a secondary factor and is conceded as deferred-pending-measurement (see (c) section). A hard gate on a rubric that scores in isolation will block legitimate orchestrator changes without quality gain. Revisit once R05's import-chain alternative has a measured token-cost study.

**Why not adopt as optional tool:** Lighter than rule-corpus adoption, the user can already manually run `claude plugin install nlpm@xiaolai` themselves. A "Crucible recommends NLPM" line in the README is fine if the maintainer wants to add it; doesn't need a ticket.

**Why not pass entirely:** The rule corpus is genuinely good. ~13 of 50 rules are worth incorporating. Even the (a)-bucket alignment is useful as documentation — it surfaces discipline that's currently implicit in Crucible's skill bodies.

---

## Follow-up tickets to file

If this decision lands:

1. **`feat(skill-creator): incorporate NLPM rule corpus as authoring checklist`** — implement action items 1 and 2 above.
2. **`feat(quality-gate): cite NLPM (b)-bucket rules in skill-artifact red-team prompts`** — implement action item 3. Specifically: add the (b)-bucket rule list to `skills/red-team/red-team-prompt.md` as additional review dimensions when the artifact under review is a SKILL.md or dispatch prompt file. Do NOT add to `skills/quality-gate/SKILL.md` itself (orchestrator framing) or to `shared/external-review-prompt.md` (independent perspective should not be biased by an internal rubric).
3. **`docs: document Crucible's skill-quality rubric and NLPM alignment`** — implement action item 5.
4. **(Deferred / optional) `research: re-evaluate NLPM scorer integration once upstream stabilizes`** — revisit in 6 months. If NLPM gains more stars / more case studies / a way to scope rules per-skill-type (e.g., let orchestrator skills opt out of R05), reconsider tooling integration.

---

## Deferred acceptance items (require user execution)

These items from the issue's acceptance criteria need NLPM installed in your environment. They can be checked off after you run them; this evaluation should still stand if the actual scores roughly track the rubric-fit reasoning above.

- [ ] `claude plugin install nlpm@xiaolai --scope project` in a throwaway branch
- [ ] `/nlpm:ls` to confirm artifact discovery
- [ ] `/nlpm:score skills/` over the full tree, capture raw scores + penalty breakdowns to `docs/plans/2026-04-25-nlpm-eval-scores.md` (gitignored per Crucible convention)
- [ ] Identify top-5 / bottom-5 scored skills; record whether the rankings track intuition (Crucible's strongest by eval-delta are quality-gate, TDD, planning, design, test-coverage, audit per the eval results table in `README.md` / `docs/evals.md` after PR #221 merges)
- [ ] Sample 3 findings from low-scored skills; classify each as **real issue** / **style opinion** / **rubric-mismatch noise**
- [ ] `/nlpm:check` for cross-component consistency; compare to `/stocktake` output
- [ ] (Optional) Try NL-TDD on a small trial skill

**Decision can move in either direction based on actual scorer output:**

- If scores **contradict** this evaluation — e.g., `build` scores 90 instead of the predicted ~75, or the rule-corpus picks turn out to be repetitive in real artifacts — file a follow-up ticket and reopen the decision (probably toward "pass" or a narrower rule subset).
- If scores **confirm** the rubric-fit reasoning AND the per-skill regression signal looks useful (e.g., consistent low scores on the orchestrators that are known to be bloated, consistent high scores on tightly-scoped skills like `verify` or `getting-started`), upgrade the decision to "adopt as optional manual tool" — add a `Recommended tools` line in the README pointing to NLPM with the caveat that orchestrator skills opt out of R05.
- If scores fall in the middle (some signal, some noise), the rule-corpus-only decision stands.

---

## Caveats

- One month old, 25 stars at time of evaluation (issue body's "22 stars" was earlier). Not battle-tested across many codebases.
- Penalty values reflect the NLPM author's priors. We have no measured-delta evidence that, e.g., a `-10` for >500 lines correlates with worse Claude Code outcomes.
- The rule corpus may evolve. R01–R50 today; R01–R60 in six months. The (a)/(b)/(c) triage above is a snapshot.
- This evaluation is source-read-only; the actual scorer was not run against Crucible's tree. The triage stands on rule-content judgment, not on observed score behavior.
