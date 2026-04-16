---
ticket: "#180"
epic: "#180"
title: "Context trust hierarchy for skill file loading"
date: "2026-04-16"
source: "spec"
---

# Context Trust Hierarchy — Implementation Plan

## Tier

**Tier 2.** Documentation + targeted edits to three+ SKILL.md files. No runtime code. No tests beyond grep-style invariant checks.

## Task Graph

```
T1 (trust-hierarchy.md authored)
  └─→ T2 (getting-started/SKILL.md references it)
        ├─→ T3 (/build annotates)
        ├─→ T4 (/design annotates)
        ├─→ T5 (/recon annotates)
        ├─→ T6 (source-driven-development annotates) [conditional on #177]
        └─→ T7 (top-level cross-links)
```

T3–T6 can run in parallel once T2 lands. T7 last.

## Tasks

### T1 — Author `skills/getting-started/trust-hierarchy.md`

Create the canonical framework doc. Must contain:
- Five `## L1` … `## L5` sections (INV-1 checks exactly 5).
- Sources, property, freshness notes per level.
- Conflict resolution rules (higher wins + per-level tie-breakers).
- Annotation convention (`<!-- TRUST: ... -->` marker) with three example stanzas.
- Short "When to re-verify" checklist.

**Verification:** `grep -c '^## L[1-5]' skills/getting-started/trust-hierarchy.md` returns 5.

### T2 — Reference from `skills/getting-started/SKILL.md`

Add a short new section ("Trust Hierarchy") near the bottom linking to `trust-hierarchy.md`. One paragraph + link; keep SKILL.md lean.

**Verification:** `grep -q 'trust-hierarchy' skills/getting-started/SKILL.md`.

### T3 — Annotate `skills/build/SKILL.md`

Add `<!-- TRUST: ... -->` markers at:
- dispatch manifest consumption (L2)
- implementer/subagent report consumption (L4)
- any WebFetch reference (L4)

Add a one-line pointer near the top: "Trust framework: see `skills/getting-started/trust-hierarchy.md`."

**Verification:** `grep -q 'TRUST:' skills/build/SKILL.md`.

### T4 — Annotate `skills/design/SKILL.md`

Markers at:
- external references (WebFetch results → L4)
- recon brief consumption (L2)
- user-pasted content (L5)

**Verification:** `grep -q 'TRUST:' skills/design/SKILL.md`.

### T5 — Annotate `skills/recon/SKILL.md`

Markers at:
- scout dispatch report consumption (L4)
- synthesis input (L4 until cross-verified against L3)

**Verification:** `grep -q 'TRUST:' skills/recon/SKILL.md`.

### T6 — Annotate `skills/source-driven-development/SKILL.md` (conditional)

If #177 has landed, annotate the WebFetch-result handling path as L4. If #177 is not yet merged, **defer** and record as a follow-up for that ticket's author to pick up.

### T7 — Cross-links

Add a one-line reference pointing at `skills/getting-started/trust-hierarchy.md` from the highest-reaching always-loaded entry point available, resolved in this order:

1. `/mnt/e/Coding/crucible/CLAUDE.md` if present at repo root (currently NOT present as of 2026-04-16 — skip).
2. `/mnt/e/Coding/crucible/skills/README.md` if present.
3. Otherwise, add the reference inside `skills/getting-started/SKILL.md` only (already covered by T2) and mark T7 as satisfied-by-T2.

Document the chosen target in the PR description so reviewers can verify.

## Invariants (verification checklist)

- INV-1: trust-hierarchy.md has exactly 5 `## L[1-5]` headings.
- INV-2: getting-started/SKILL.md mentions `trust-hierarchy`.
- INV-3: each of `skills/{build,design,recon}/SKILL.md` contains `TRUST:` at least once.
- INV-4: every `TRUST:` marker in the annotated SKILL.md files includes an `L<N>` classification — `grep -E 'TRUST:' skills/{build,design,recon}/SKILL.md` lines each match `TRUST:.*L[1-5]`.

All four are plain grep checks — suitable for quality-gate.

## Risks / Mitigations

- **Skill-file churn conflict with #176 and #179.** Mitigate by landing this ticket last among the three, or by coordinating section placement via a short convention (TRUST markers go adjacent to the load point, not in a dedicated section — reduces collision surface).
- **Marker pollution.** Over-annotating SKILL.md files degrades readability. Mitigate by adding markers only at *external-content load points*, never on every paragraph.
- **Staleness drift.** The "30 days" threshold for memory is arbitrary. Mitigate by documenting it as a rule-of-thumb rather than hard cutoff; the agent uses judgment.

## Rollout

- Single PR touching ~6 files.
- No migration, no feature flag, no tests beyond grep.
- Quality-gate against the three invariants.
- No runtime risk — pure documentation.

## Done When

- 3 deliverable files (this design, this plan, contract) exist in `docs/plans/`.
- T1–T5 complete; T6 complete or explicitly deferred with a note in #177's tracker; T7 complete.
- INV-1, INV-2, INV-3 all pass.
