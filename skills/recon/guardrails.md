# Guardrails

## Design Principles

- **Read-only** — `/recon` never modifies the codebase
- **Cartographer-aware** — consults first, feeds back after
- **Layered** — core is cheap and universal; depth is on-demand and consumer-specific
- **Evidence-grounded** — produces constraints and evidence, not opinions
- **Prior art is first-class** — finding existing patterns to follow is the single biggest quality lever
- **Assumptions are explicit** — annotated inline on relevant findings, not in a standalone block
- **Token-efficient** — structured markdown, no JSON boilerplate, standard for mechanical work

## Guardrails / Red Flags

- Never modify the codebase
- Never dispatch depth agents before core synthesis completes
- Never skip narration between dispatches
- Never exceed context budgets without overflow handling
- Never auto-update cartographer without both-scout agreement + verifiable evidence
- Never return depth module output without the core brief
- Never let an unverified causal claim reach the brief's main sections — demote to Open Questions per the Causal Claim Verification step
- Never skip auto-inclusion of diagnostic-context on a debugging task unless caller explicitly passed `modules: []`
