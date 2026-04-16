---
ticket: "#176"
epic: "#176"
title: "Anti-rationalization tables for skill hardening"
date: "2026-04-16"
source: "spec"
---

# Design: Anti-Rationalization Tables for Skill Hardening

## Motivation

Inspired by [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills).
Every skill there ships a small table listing excuses the agent might invent to
skip required work paired with a documented rebuttal and a hard rule.

Crucible's quality gates catch skipped work *after the fact* — anti-rationalization
tables intercept the excuse *before the agent commits to a shortcut*. Preventive
and detective controls are complementary. For a solo-dev workflow where silent
bugs are expensive (see `feedback_severity_bias`, `feedback_quality_gate_always`,
`feedback_never_skip_gates`), a preventive layer layered on top of the existing
detective layer is a strict upgrade.

## Current State

Each of the four target skills has a `## Red Flags` section (except `design`,
which has none):

- `skills/build/SKILL.md:1270` — `## Red Flags` (15 bullet items, several of which
  are already rationalization-shaped: "Skipping a REQUIRED quality gate because
  the task seems 'small', 'simple', or 'trivial'").
- `skills/spec/SKILL.md:788` — `## Red Flags` (10 bullets, includes similar
  rationalizations).
- `skills/quality-gate/SKILL.md:651` — `## Red Flags` (~20 bullets covering
  orchestrator-side failure modes).
- `skills/design/SKILL.md` — no Red Flags section; has `## Key Principles` at
  line 253.

These Red Flags lists are unstructured negative examples. They list the
*behaviors* to avoid but not the *excuses* that generate those behaviors, and
they lack a paired rebuttal or binding rule per entry. They also sit late in the
skill (line 1270 in `build/SKILL.md`, after the phase walkthrough), which means
they only fire as a conscience check rather than a top-of-mind guardrail.

## Target State

Each of the four target skills gains a new section `## Anti-Rationalization
Table` with a 3-column markdown table:

```markdown
| Rationalization | Rebuttal | Rule |
|---|---|---|
| "It's a small change, skip the gate" | Small changes have the same bug density per line. QG always finds something. | Size is never a valid reason to skip the gate. |
```

**Co-loading (AC line 2):** tables live in `SKILL.md` itself, not a sidecar
reference file. The whole SKILL.md loads when the skill activates; sidecar
reference files only load when referenced.

**Placement:** near the top of the skill, after `## Communication Requirement`
or equivalent non-negotiable preamble, and BEFORE the phase/process walkthrough.
This is the highest-attention region of the skill — the agent is still reading
framing, not procedure. Specific per-skill insertion points are listed in the
implementation plan.

**Size:** 5–8 entries per skill, prioritizing the most common rationalizations
derived from each skill's existing Red Flags plus user-memory feedback.

## Key Decisions

| ID | Decision | Confidence |
|---|---|---|
| DEC-1 | 3-column format `Rationalization \| Rebuttal \| Rule` as specified in the ticket | High |
| DEC-2 | Inline in SKILL.md, never in a sidecar reference file (AC line 2) | High |
| DEC-3 | Place the table after the non-negotiable preamble and before the process/phase walkthrough; for `design/`, place after `## Overview` and before `## The Process` | Medium |
| DEC-4 | Seed rationalizations from (a) each skill's existing Red Flags section, (b) `feedback_never_skip_gates` ("stop. skipping. steps.", skipping QG/innovate/red-team), (c) `feedback_quality_gate_always` ("just 31 lines", "it's only a prompt", "I verified manually") | Medium |
| DEC-5 | 5 entries minimum (AC), 8 maximum — pick the most impactful; do not dilute with generic tropes | High |
| DEC-6 | Do NOT modify or remove the existing Red Flags sections — the table is additive. Red Flags remain as a behavior checklist; the table catches the rationalization upstream | High |

## Pre-Authored Tables (Per Skill)

These are the full tables the implementation plan will insert verbatim.
Implementers should not re-author them during the implementation phase.

### `skills/build/SKILL.md`

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This task is small/simple/trivial, the quality gate would just find nits." | Small changes have the same bug density per line as large ones. QG has never run on a Crucible artifact without finding at least one real issue. | Run the quality gate on every phase artifact, regardless of size. |
| "Phase N looks fine, I can skip the gate and move on." | Self-assessment of artifact quality is exactly the bias the gate exists to counter. "Looks fine" is the failure mode, not a pass criterion. | Phase transitions are BLOCKED without a verified PASS verdict marker for the prior phase. |
| "The fix agent addressed the findings, so the gate is done." | Fixing is not passing. Fix rounds routinely introduce new issues or incompletely resolve old ones. A clean verification round is required. | The gate is only complete after a fresh red-team round returns 0 Fatal, 0 Significant. |
| "The user said 'looks good' / 'move on' — that's approval to skip the gate." | General feedback is not skip approval. Only an unambiguous instruction that explicitly references the gate counts. | Require literal `SKIP GATE` (or equivalent explicit phrase) before recording `Status: SKIPPED`. |
| "I can fix this one finding myself instead of dispatching a fix agent." | Orchestrator-applied fixes conflate coordination with remediation and bypass the fix journal. Every fix — even trivial — goes through a fix agent. | Orchestrator never edits the artifact directly; always dispatch the fix agent. |
| "Innovate/red-team seem redundant on top of the quality gate, I'll skip them." | They are not redundant. Innovate is divergent; red-team is adversarial; QG is iterative remediation. Skipping any one of them is a documented regression (`feedback_never_skip_gates`). | Run innovate and red-team on every artifact, every time. |
| "I'll just finish the task list and narrate at the end." | Long-running autonomous pipelines are invisible without narration. Silent runs prevent the user from intervening or learning. | Narrate before every dispatch and after every completion — non-negotiable. |

### `skills/spec/SKILL.md`

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This ticket is small, I can skip the per-document quality gate." | Ticket size does not predict specification defects. Small tickets frequently hide ambiguity that only QG surfaces. | Run the quality gate on every design doc and every implementation plan, regardless of ticket size. |
| "All per-document gates passed, the integration check is unnecessary." | Per-document PASS does not imply cross-ticket consistency. Contracts drift between tickets even when each is individually clean. | Always run the end-of-run integration quality gate after the per-ticket gates pass. |
| "The ticket body looks clear, I can skip the investigation and go straight to writing." | Ticket bodies consistently under-specify. Without investigation, autonomous decisions are made without grounding and surface as block-confidence alerts downstream. | Investigate the codebase before writing any design content; cite investigation artifacts in the design doc. |
| "The decision looks obvious, I'll record it as high-confidence without alternatives." | Listing alternatives is a forcing function for honest confidence calibration. Skipping it hides the fact that no alternatives were considered. | Every decision logs ≥1 alternative or is explicitly marked `no-alternatives: true` with justification. |
| "I can save state in context memory instead of the scratch directory." | Context is lost on compaction. Scratch-directory state is load-bearing for recovery. | Every orchestrator state change writes to the scratch directory before narrating. |
| "The user's general 'looks good' counts as approval to skip a gate." | Only an unambiguous instruction specifically referencing the gate is skip approval. | Record `Status: SKIPPED` only after explicit gate-referencing skip instruction. |

### `skills/quality-gate/SKILL.md`

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This finding is minor, I'll just fix it inline instead of dispatching a fix agent." | Orchestrator-applied fixes break separation of concerns and corrupt the fix journal. Fix-agent overhead for trivial fixes is negligible; the risk of conflation is not. | All fixes route through the fix agent — no exceptions, no matter how small. |
| "Round N fixed everything, I can return PASS without another red-team round." | Fixing is not passing. A fresh red-team round is the verification step. Skipping it is a skip disguised as a pass. | The gate is only PASS after a fresh red-team round returns 0 Fatal, 0 Significant. |
| "The red-team finding is wrong / overblown, I'll mark it resolved without a fix." | Rationalizing away findings defeats the point of adversarial review. If a finding is wrong, the fix agent explicitly justifies dismissal in the fix journal — the orchestrator does not dismiss findings unilaterally. | Every Fatal/Significant finding is either fixed or documented as dismissed by the fix agent with reasoning. |
| "The score went up but I can tell it's close, skip the stagnation judge." | Stagnation detection uses weighted score, not orchestrator intuition. Score-based inline judgment is the exact failure the judge exists to catch. | Dispatch the stagnation judge whenever score is not strictly lower than the prior round. |
| "Round 15 hit — I'll squeeze in one more round, surely the next will pass." | The 15-round limit is a circuit breaker, not a suggestion. Exceeding it silently is how runaway loops happen. | At round 15, escalate to the user with full round history — never silently continue. |
| "Pre-flight dependency audit is noise for this artifact, skip it." | The audit only runs on `code` artifacts, and on code artifacts it's mandatory. Dependency drift is a documented source of shipped bugs. | Run the dependency audit on every `code` artifact; skip silently only for non-code types. |
| "The user said 'move on', that's approval to skip the gate." | General feedback is never skip approval. Skip requires an unambiguous instruction specifically referencing the gate. | Only an explicit, gate-referencing instruction counts as skip approval. |

### `skills/design/SKILL.md`

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This decision is obvious, I can skip the hypothesis step." | The hypothesis step is a forcing function for noticing surprises — the most valuable output of investigation. Skipping it loses the contrast. | Write the hypothesis before dispatching investigation agents, even when the answer feels obvious. |
| "One investigation agent is enough, I don't need the Challenger." | The Challenger catches assumption blind spots that the recommendation agent inherited. Skipping it is how bad designs ship. | Deep Dive dimensions always dispatch the Challenger (or multi-model consensus challenge when available). |
| "Quick scan is fine for this data-model decision." | Data-model decisions always warrant Deep Dive — schema outlives the application. Quick scans have repeatedly missed grain/durability issues. | Any dimension touching schema/data model/persistent storage is Deep Dive, not Quick scan. |
| "The recommendation is clear, I can skip presenting alternatives." | Presenting 2–3 options keeps the user in the decision loop. Auto-resolving without alternatives is only allowed when investigation proves a single viable path. | Present 2–3 options per dimension unless the investigation explicitly shows one viable path; record the justification. |
| "The feature obviously belongs in this system, skip the scope absorption test." | The test is cheap (4 yes/no questions) and has repeatedly flagged features that didn't belong. | Run the scope absorption test whenever adding a feature to an existing system. |
| "The user is still deliberating, I'll keep asking for more analysis." | After 2 non-resolving user responses, the stall-breaker protocol (eliminate / reversibility / ship-sooner) applies. | Activate the stall-breaker protocol on the 3rd user exchange on the same dimension without resolution. |

## Seed Sources (Provenance)

- **Skill Red Flags sections:** `build/SKILL.md:1270`, `spec/SKILL.md:788`,
  `quality-gate/SKILL.md:651`. These supplied the "small/simple/trivial"
  rationalization, the "fixing is not passing" rebuttal, and the
  "looks good / move on" discussion.
- **User memory `feedback_quality_gate_always`:** "just 31 lines", "it's only a
  prompt", "I verified invariants manually" — seeded the build and quality-gate
  entries.
- **User memory `feedback_never_skip_gates`:** "stop. skipping. steps.",
  "skipping because it seems straightforward" — seeded the "innovate/red-team
  redundant" entry for build.
- **Skill process text:** the `design/` table entries come from the skill's own
  Phase 2 steps (Hypothesis at step 2, Challenger at step 6, scope absorption
  at step 5, stall-breaker at step 9, data-model deep-dive at step 3).

## Acceptance Criteria (Testable)

- AC-1: `grep -l 'Anti-Rationalization' skills/{build,spec,quality-gate,design}/SKILL.md`
  returns all 4 paths. (Covers ticket AC "at least 4 core skills have tables".)
- AC-2: Each table has ≥5 data rows. Counted by: lines matching `^\|` between
  the `## Anti-Rationalization Table` heading and the next `## ` heading,
  minus 2 (header row + separator row). (Covers ticket AC "≥5 entries".)
- AC-3: Table is in `SKILL.md` (not a sidecar reference file). Verified by path
  in AC-1. (Covers ticket AC "load with the skill".)
- AC-4: Each table sits before the first process/phase/walkthrough section
  (`## The Process`, `## Gate Ledger Protocol`, `## Orchestration Flow`,
  `## How It Works`). Verified by line ordering in a post-implementation
  inspection pass.

## Risks

- **Drift:** tables become stale if skills evolve and entries aren't refreshed.
  Mitigated by positioning near Red Flags so the next editor sees both and
  updates in sync.
- **Dilution:** adding too many entries reduces signal per entry. Mitigated by
  DEC-5 cap of 8 entries per skill.
- **Placement conflicts:** future skill reorganization may displace the table.
  Mitigated by choosing the section heading `## Anti-Rationalization Table`
  (unique, greppable) so future edits can relocate it without losing it.
- **False sense of security:** the table prevents stated rationalizations but
  not novel ones. Mitigated by retaining the Red Flags section and the quality
  gate itself — this is defense-in-depth, not a replacement.

## Non-Goals

- Rewriting Red Flags sections (they stay as-is — table is purely additive).
- Automated enforcement of the table (quality gate is already the enforcement
  layer).
- Adding tables to skills outside the four named in the ticket.
- A sidecar reference file or shared YAML schema — explicitly ruled out by
  AC line 2.
