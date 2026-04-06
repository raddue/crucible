---
ticket: "#130"
title: "Add integration contract assessment to /recon impact-analyst"
date: "2026-04-06"
source: "spec"
---

# Add Integration Contract Assessment to /recon Impact Analyst

## Current State Analysis

The `/recon` impact-analyst depth module (`skills/recon/impact-analyst-prompt.md`, 107 lines) assesses change impact across 5 dimensions: Systems Affected, Integration Risks, Data Impact, Test Impact, and Reversibility.

The "Integration Risks" section currently instructs the agent to look for:
- API contracts that could be violated
- Assumptions that may no longer hold
- Race conditions or ordering dependencies

This is general-level seam analysis. It identifies WHERE integrations exist but doesn't check the HEALTH of those integrations against specific anti-patterns.

## Target State

Add a structured "Integration Contract Assessment" subsection within the existing "Integration Risks" section. When the proposed change touches code that integrates with external systems, the impact analyst evaluates 4 specific integration health checks:

1. **Abstraction check** — Is the external system abstracted behind an interface? Can it be replaced without modifying business logic?
2. **Write direction** — Does the system write directly to another system's tables/storage? Reads are fine; writes should go through staging tables or outbound queues.
3. **Shared schema coupling** — Do two applications share a database schema as their integration mechanism? That's coupling disguised as simplicity.
4. **Fallback path** — Does every integration have a fallback when the external system is down? (manual entry, queue and retry, operator override)

These checks are additive — they complement the existing seam analysis, not replace it.

## Key Decisions

### DEC-1: Embed within existing Integration Risks section (High Confidence)

**Decision:** Add the 4 checks as a subsection within the existing "Integration Risks" section rather than creating a new top-level section.

**Rationale:** The issue explicitly says "add integration contract checks to the Integration Risks section." The checks are a refinement of integration risk assessment, not a separate concern. Adding a new top-level section would fragment the analysis and potentially push the output over the 3,000-token budget.

### DEC-2: Conditional assessment (High Confidence)

**Decision:** The integration contract checks only apply when the change touches code that integrates with external systems. The agent should assess whether integrations are in scope before running these checks.

**Rationale:** Not every change involves integrations. Running these checks on purely internal changes (e.g., refactoring a utility function) would produce empty/irrelevant output.

### DEC-3: Output format matches existing pattern (High Confidence)

**Decision:** Each check produces a bullet point in the same format as existing Integration Risks findings: `**[check name]** — [finding]`.

**Rationale:** Consistency with the existing output format. Consumers of the impact analysis (design, build) don't need to parse a new format.

## Risk Areas

1. **Token budget pressure:** Adding 4 checks to an already 3,000-token budget section could cause output truncation. Mitigated: the checks are conditional (only when integrations are in scope) and produce brief findings (one bullet each).

## Acceptance Criteria

1. Impact-analyst prompt template includes all 4 integration contract checks (abstraction, write direction, shared schema, fallback path)
2. Checks are within the "Integration Risks" section, not a separate top-level section
3. Checks are conditional on the change touching external system integrations
4. Output format matches existing Integration Risks bullet pattern
5. Existing prompt structure (sections, guardrails, token budget) is preserved
