# Integration and Cost Reference

## Behavior Matrix

| Configuration | Behavior |
|---|---|
| With task | Scouts focus on task-relevant areas |
| With context | Prior decisions passed to scouts alongside task |
| Without task | Full repo recon for audit/project-init cold starts |
| With scope | Explicit scope overrides scout suggestions |
| With modules | Depth agents dispatched after core synthesis |
| No modules | Core layer only — cheapest possible recon |
| With session_id | Structure Scout cached, Pattern Scout always fresh |

## Cost Profile

| Configuration | Agents | Models | Relative Cost |
|---|---|---|---|
| Core only | 2 | 2x Sonnet | Low |
| Core + 1 mechanical module | 3 | 3x Sonnet | Low |
| Core + 1 judgment module | 3 | 2x Sonnet + 1x Opus | Medium |
| Core + 2 modules (mixed) | 4 | 2-3x Sonnet + 1-2x Opus | Medium-High |
| Full repo, no task | 2 | 2x Sonnet | Low (but slower) |

## Dispatches

- `structure-scout-prompt.md` — Structure Scout (Sonnet, Explore)
- `pattern-scout-prompt.md` — Pattern Scout (Sonnet, Explore)
- `impact-analyst-prompt.md` — Impact Analyst (Opus)
- `consumer-mapper-prompt.md` — Consumer Mapper (Sonnet)
- `friction-scanner-prompt.md` — Friction Scanner (Opus)
- `manifest-builder-prompt.md` — Manifest Builder (Sonnet)
- `diagnostic-gatherer-prompt.md` — Diagnostic Gatherer (Opus)
- `readiness-checker-prompt.md` — Readiness Checker (Sonnet)

## Consults

`crucible:cartographer` (consult mode — direct file read of `map.md`)

## Records to

`crucible:cartographer` (recorder dispatch after investigation, using `skills/cartographer-skill/recorder-prompt.md`)

## Called by

`/design` (Phase 2 context + impact-analysis), `/spec` (per-ticket investigation + impact-analysis), `/migrate` (Phase 0 + consumer-registry), `/audit` (Phase 1 code scoping + subsystem-manifest)

## Not called by (investigated, not a fit)

`/debugging` (specialized investigation pipeline), `/build` (inherits via /design), `/prospector` (organic exploration is different), `/project-init` (bootstraps cartographer, complementary purpose). See #147 for rationale.

## Pairs with

`/assay` (sequential — recon produces evidence, assay evaluates options)
