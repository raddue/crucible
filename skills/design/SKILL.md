---
name: design
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Turn ideas into fully formed designs through investigated, collaborative dialogue.

Every significant design question is backed by parallel investigation agents that research the codebase, explore approaches, and assess impact BEFORE the question reaches the user. Questions arrive informed, not naive.

## The Process

### Phase 1: Context Gathering

- **RECOMMENDED:** Use crucible:forge (feed-forward mode) — consult past lessons
- **RECOMMENDED:** Use crucible:cartographer (consult mode) — review codebase map
- Check current project state (files, docs, recent commits)
- Understand the user's initial idea through open conversation

### Phase 2: Investigated Questions

For each design dimension that needs a decision, follow this loop:

#### Step 1: Identify the Design Dimension

Before asking anything, name the decision needed (e.g., "persistence strategy," "component communication pattern," "UI architecture").

#### Step 2: State Your Hypothesis

Write down what you EXPECT to find before dispatching agents. After agents return, compare. **Surprises get highlighted** — they're the most valuable insights.

#### Step 3: Triage Depth

| Tier | When | Effort |
|------|------|--------|
| **Deep dive** | Architectural decisions, integration points, pattern choices, anything constraining future work | 3 parallel agents + challenger |
| **Quick scan** | Implementation approach within decided architecture, which existing pattern to follow | Single codebase scout |
| **Direct ask** | Naming, UI placement, priority ordering — no technical implications | Ask directly |

**Data model dimensions:** Decisions involving database schema, data model, or persistent storage always warrant **Deep dive**. During synthesis, apply the grain test:
- **Grain:** "What is one row in this table?" Must be answerable in a single sentence. Bad signs: rows that mean different things depending on a type column, rows containing multiple independent facts, rows whose identity requires reading application code.
- **Relationships:** Every foreign key tells a story. Parent-child relationships should be obvious from the schema alone. If you need a whiteboard to explain how two tables relate, add an intermediate table or rethink the relationship.
- **Durability:** The schema outlives the application. Design tables as if the application will be replaced but the data must survive. Use simple types, avoid application-specific encoding.

#### Step 4: Dispatch Investigation

**Deep dive** — spawn three agents in parallel (templates in `investigation-prompts.md`):

1. **Codebase Scout** — What does the codebase already do in this area? Existing patterns, conventions, constraints.
2. **Domain Researcher** — What are the viable approaches? Trade-offs, best practices, precedents.
3. **Impact Analyst** — What existing systems does this decision affect? What could break?

Pass the **cascading context** (all prior decisions and rationale) to each agent.

**Quick scan** — dispatch only the Codebase Scout.

#### Step 5: Synthesize

After agents return:

1. **Compare to hypothesis** — note surprises
2. **Check for auto-resolution** — if only one viable path exists, inform the user rather than asking: "Investigation showed X is the only viable approach because [reasons]. Moving on." User can interrupt if they disagree.
3. **Scope absorption test** — If this feature targets an existing system (not greenfield), challenge the assumption that it belongs there. Apply four questions:
   - Does this share the same data model as the host application?
   - Does this share the same interaction pattern (form entry vs. dashboard vs. real-time)?
   - Does this serve the same users with the same workflows?
   - Would this feature survive if the host application were replaced tomorrow?
   If fewer than 3 answers are "yes," flag to the user: "This feature may not belong in [target system] — it only shares [N/4] characteristics. Consider whether it deserves its own application. Each application should be describable in a single sentence — if you need a paragraph, it's doing too much." The user decides; this is a structured nudge, not a veto.
4. **Check for question redirection** — if agents found the wrong question is being asked, redirect: "Was going to ask about X, but investigation revealed the real decision is Y."
5. **Synthesize into 2-3 informed options** with a recommended choice

#### Step 6: Challenge (Deep Dive Only)

Dispatch a **Challenger** agent (template in `investigation-prompts.md`):
- Attacks the recommendation's assumptions
- Checks for conflicts with prior decisions
- Identifies blind spots in the investigation
- Brief output — this is lightweight, not a full red-team

**Multi-model enhancement (when available):** When the `consensus_query`
MCP tool is available and consensus mode `investigate` is enabled, the
Challenger step calls `consensus_query(mode: "investigate")` instead of
dispatching a single Challenger agent. Multiple models attack the
recommendation independently, and the aggregator synthesizes their
challenges. This is structurally stronger than a single-model challenger
because different model families have different assumption sets.

Present multi-model challenge results with provenance: "Challenge
(multi-model, N models): [synthesis]" vs. the standard "Challenge:
[findings]" format.

**Fallback:** If consensus is unavailable, dispatch the standard
single-model Challenger agent.

#### Step 7: Present to User

```
### [Design Dimension]

**Hypothesis:** [what you expected]
**Surprises:** [anything that contradicted expectations — highlight these]

**Investigation:**
- **Codebase:** [2-3 sentence summary]
- **Approaches:** [2-3 sentence summary of viable options]
- **Impact:** [2-3 sentence summary of affected systems]

**Challenge:** [1-2 sentence summary of what the challenger raised]

**Recommendation:** [your recommended option and why]

**Question:** [the refined question, prefer multiple choice]
```

For auto-resolved questions:

```
### [Design Dimension] — Auto-Resolved

[Why only one viable path exists. Decision made.]
*Speak up if you disagree.*
```

#### Step 8: Cascade

After the user answers, add the decision and rationale to the running context. All subsequent agents receive this.

#### Step 9: Stall-Breaker (Conditional)

**Trigger:** The same design dimension has received 2+ user responses without new information surfacing or a decision being made. A "user response" is a reply after the dimension is presented that does not resolve it (asks for more analysis, expresses uncertainty, or revisits a prior option). The initial presentation (Step 7) does not count — the user gets at least two chances to engage before the stall-breaker activates.

When triggered, apply this tiebreaker protocol in order:

1. **Eliminate:** Can you identify a concrete technical reason one option is wrong? If so, eliminate it and present the remaining option as the recommendation.
2. **Reversibility:** Are both options still viable? Pick the one that's simpler to reverse if you're wrong. Two-way doors beat one-way doors.
3. **Ship sooner:** Still stuck? Pick the one that ships sooner. Shipping teaches things deliberation cannot.

**Present the tiebreaker:**
> "We've been deliberating on [dimension] for a while without new information surfacing. Here's my tiebreaker recommendation: **[option]**, because [reason from the protocol above]. If you disagree, tell me — otherwise I'll proceed with this."

The user can always override. This is a structured nudge, not a forced decision. If the user provides genuinely new information (not a restatement of prior concerns), reset the exchange counter and continue normal investigation.

**What "decided" means:** The decision is implemented and no longer being discussed. If the same question keeps resurfacing after a tiebreaker, it hasn't been decided — escalate: "This dimension keeps resurfacing. Would it help to time-box it, or should we move forward and revisit after we see the rest of the design?"

### Phase 3: Design Presentation

Once key dimensions are decided:
- Present design in sections of 200-300 words
- Ask after each section whether it looks right
- Cover: architecture, components, data flow, error handling, testing
- Include an **API Surface** section listing public interfaces with signatures and types
- Include an **Invariants** section listing hard constraints, split into what can be checked by inspection vs. what requires tests
- Be ready to go back and re-investigate if something doesn't make sense

These contract-relevant sections (API Surface, Invariants) give the contract extraction step structured source material rather than requiring post-hoc extraction from prose.

## Before Saving the Design

Scan for gaps (use judgment — not every item applies):

- [ ] **Acceptance criteria** — Concrete and testable?
- [ ] **Testing strategy** — Unit vs integration coverage?
- [ ] **Integration impact** — Touchpoints addressed?
- [ ] **Failure modes** — Invalid data, missing dependencies, unexpected state?
- [ ] **Edge cases** — Boundary conditions?
- [ ] **API surface defined** — Public interfaces with signatures?
- [ ] **Invariants identified** — Hard constraints (checkable vs testable)?
- [ ] **Data model grain** — Can you answer "what is one row?" in a single sentence for every new table? Relationships obvious from schema alone? Schema durable beyond the application?

Raise critical gaps with the user before saving.

## After the Design

- Write to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- Design doc must include YAML frontmatter with the following fields:
  ```yaml
  ---
  ticket: "#NNN"       # Issue/ticket reference
  title: "Design Title"
  date: "YYYY-MM-DD"
  source: "design"     # Provenance tracking — distinguishes from /spec-authored docs
  ---
  ```
- Commit the design document

### Contract Emission

After the design doc is written and the user approves it:

1. **Extract** API surface, invariants (split into checkable/testable), and integration points from the design doc's API Surface and Invariants sections
2. **Present** the extracted contract to the user: "Here's the contract I extracted from the design. Please review before I commit it alongside the design doc."
3. The user can **approve**, **modify**, or **reject** the contract
4. On approval, emit a `YYYY-MM-DD-<topic>-contract.yaml` file alongside the design doc in `docs/plans/`
5. Contract uses the same YAML schema as `/spec` contracts (version 1.0): `api_surface`, `invariants` with `checkable`/`testable` split, `integration_points`, `ambiguity_resolutions`

**Contract asymmetry note:** `/design` extracts contracts post-hoc from prose; `/spec` produces contracts as a first-class output during autonomous decision-making. As a result, `/design` contracts may be less structured — they reflect what was extractable from prose rather than what was deliberately specified. `/build` should apply additional scrutiny to `/design`-sourced contracts.

**Implementation (if continuing):**
- Ask: "Ready to set up for implementation?"
- Use crucible:worktree, then crucible:planning

## Quality Gate

This skill produces **design docs**. When used standalone, invoke `crucible:quality-gate` after the design document is saved and committed. When used as a sub-skill of build, the parent orchestrator handles gating.

## Key Principles

- **Investigated questions** — Never ask a significant question without research backing
- **One question at a time** — Don't overwhelm
- **Auto-resolve when possible** — Don't waste user attention on decided questions
- **Hypothesis-first** — State expectations, highlight surprises
- **Cascading context** — Each decision informs subsequent investigations
- **YAGNI ruthlessly** — Remove unnecessary features
- **Depth-appropriate effort** — Not every question needs deep investigation

## Integration

**Related skills:** crucible:build, crucible:planning, crucible:worktree, crucible:forge, crucible:cartographer, crucible:quality-gate, crucible:spec

**Contract schema:** Shared with `/spec` — see `skills/spec/SKILL.md` for the canonical contract YAML schema (version 1.0). Both `/design` and `/spec` emit contracts that `/build` consumes.

**Prompt templates:** `design/investigation-prompts.md`
