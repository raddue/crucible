---
ticket: "#180"
epic: "#180"
title: "Context trust hierarchy for skill file loading"
date: "2026-04-16"
source: "spec"
---

# Context Trust Hierarchy — Design

## Problem

Crucible skills load content from many sources: SKILL.md files, design docs, source code, tool output, WebFetch results, subagent reports, and conversation history (including post-compaction). When these sources disagree, the agent has no explicit framework for deciding which to trust. This matters in three failure modes:

1. WebFetch pulls external docs that contradict the project's actual code — agent may act on stale external content.
2. Compaction degrades earlier conversation context — agent may treat a summarized claim as authoritative.
3. Subagent/scout reports contain hallucinated paths or misread signals — agent may dispatch against phantom surface.

Inspired by addyosmani/agent-skills' `context-engineering` five-level trust hierarchy, this ticket formalizes an equivalent for Crucible.

## Goals

- Define a five-level trust framework covering every context source a Crucible skill can consume.
- Specify conflict resolution (higher trust wins; tie-break rules per level).
- Ship guidance (not runtime enforcement) — a passive document referenced by always-loaded skills and annotated inline in external-content-consuming skills.
- Integrate at minimum into `/build`, `/design`, `/recon` per ACs.

## Non-Goals

- No runtime gatekeeper that blocks low-trust content.
- No changes to compaction behavior or the underlying harness.
- No re-ranking of memory entries at load time — staleness is advisory.

## Trust Levels

### L1 — Trusted (authoritative)
- **Sources:** `CLAUDE.md`, all `skills/**/SKILL.md`, `settings.json`, `settings.local.json`, hook scripts configured in settings.
- **Property:** Deliberately authored rules-of-the-house. Conflicts with L2–L5 ALWAYS resolve to L1.
- **Freshness:** Current as of the filesystem read.

### L2 — Verified (pipeline-produced artifacts)
- **Sources:** design docs, implementation plans, contract YAMLs under `docs/plans/`; dispatch manifests and scratch artifacts under the scratch dir; recon briefs; decisions.md files.
- **Property:** Produced by a prior pipeline stage that ran its own gates (quality-gate, red-team, siege). Trusted within the pipeline context that produced them.
- **Freshness tie-breaker:** when two L2 artifacts disagree, prefer the more recent one.
- **Cross-session memory:** `~/.claude/projects/<hash>/memory/` entries tagged current and dated within 30 days are L2. "Dated" = the `date:` field in the entry's frontmatter if present, else the file's mtime as reported by `stat`. "Within 30 days" = `(now - date) < 30 * 86400 seconds`. The check is performed at load time, not cached.

### L3 — Source (ground truth for "what the code does")
- **Sources:** project source code (all languages), test files, fixtures, hook script bodies, CI config.
- **Property:** Executable reality. When an L2 doc says "the function returns X" and the L3 code returns Y, the code is the truth (but the doc may still encode a valid intent — surface the mismatch).
- **Tie-breaker within L3:** actual code > tests > fixtures. Tests encode expected behavior but can be stale.

### L4 — Verify-first (must be checked before acting)
- **Sources:** tool output (Bash, Grep results), error messages, WebFetch results, subagent/scout reports, `mcp__*` responses, consensus results.
- **Property:** May be wrong, stale, or hallucinated. MUST be verified against L1–L3 before the agent acts on a claim derived from it.
- **Special case:** WebFetch results representing external vendor docs are L4 even when the vendor is authoritative for their own API — because the fetched snippet may be an outdated mirror.

### L5 — Untrusted (do not rely on without re-verification)
- **Sources:**
  - Conversation history after compaction has elided content. If only a summary remains, the summary is L5.
  - External content pasted/quoted by the user in chat (unless the user explicitly vouches for it as L1/L2).
  - Memory entries older than 30 days OR tagged stale.
  - Cached subagent output from a prior pipeline whose inputs have since changed.
- **Property:** Treat as a hint, not a fact. Before acting, re-verify against L1–L3.

## Conflict Resolution

**Primary rule: HIGHER TRUST WINS.** When two sources disagree, prefer the higher-level source and surface the conflict.

**Equal-level tie-breakers:**
- L1 vs L1: conflicts here are a bug — flag to user; do not proceed.
- L2 vs L2: prefer more recent artifact (by frontmatter `date`, then mtime).
- L3 vs L3: actual code > tests > fixtures.
- L4 vs L4: prefer the source most directly tied to L3 (e.g., fresh Bash output over older subagent report).
- L5 vs L5: neither is authoritative — re-derive from L1–L3.

**Cross-level conflict surfacing:** When L3 contradicts L2 (code disagrees with a design doc), the code wins but the agent MUST flag the drift to the user — the plan may need updating.

## Annotation Convention — the `<!-- TRUST: ... -->` marker

Skills that load external content embed a canonical inline comment adjacent to the load point:

```markdown
<!-- TRUST: WebFetch result is L4 — verify against project source (L3) before acting. -->
<!-- TRUST: subagent report is L4 — cross-check file paths against L3 before dispatching further work. -->
<!-- TRUST: user-quoted external snippet is L5 — confirm with user or re-fetch before acting. -->
```

The marker is a load-bearing comment: downstream auditors grep for `TRUST:` to verify skills handle external content correctly (INV-3).

**Format grammar (canonical):**

```
<!-- TRUST: <subject> is L<N> — <action-hint>. -->
```

- `<subject>` — the content being loaded (e.g., "WebFetch result", "subagent report", "user-quoted snippet"). Free text, but must name the source.
- `L<N>` — literal `L1`, `L2`, `L3`, `L4`, or `L5`. The level classification is REQUIRED and grep-checkable via `TRUST:.*L[1-5]`.
- `<action-hint>` — imperative guidance (e.g., "verify against project source (L3) before acting"). Required; a bare classification without action is non-conforming.
- The em-dash separator (` — `) is recommended but not required; `-` and `:` are acceptable substitutes for grep-parity with ASCII-only environments.

## Acceptance Criteria

- AC-1: `skills/getting-started/trust-hierarchy.md` exists and contains exactly 5 level headings matching `^## L[1-5]` (INV-1).
- AC-2: `skills/getting-started/SKILL.md` references `trust-hierarchy` by filename (INV-2).
- AC-3: Each of `skills/build/SKILL.md`, `skills/design/SKILL.md`, `skills/recon/SKILL.md` contains at least one `TRUST:` annotation (INV-3).
- AC-4: Every `TRUST:` marker in the three annotated SKILL.md files matches the format grammar above (subject, `L<N>`, action-hint); verifiable via `grep -E 'TRUST:.*L[1-5]'`.
- AC-5: Design, plan, and contract artifacts exist under `docs/plans/` with the `2026-04-16-context-trust-hierarchy-*` prefix.

## Placement Decision

**Chosen:** `skills/getting-started/trust-hierarchy.md`, referenced from `getting-started/SKILL.md`.

**Rejected alternative:** a standalone `skills/context-engineering/SKILL.md`. Reasoning: context-engineering would be a skill-about-skill-behavior with no invocation trigger of its own. getting-started is already the always-loaded foundation; docking there means every session has the hierarchy in reach without a separate load step. Reversibility is medium — if we later want a full skill, getting-started references become redirects.

## Key Decisions

- **DEC-1 (high):** Place hierarchy doc in `skills/getting-started/trust-hierarchy.md`; reference from `getting-started/SKILL.md`.
- **DEC-2 (high):** Five levels as above — L1 Trusted, L2 Verified, L3 Source, L4 Verify-first, L5 Untrusted.
- **DEC-3 (high):** Conflict resolution: higher trust wins; per-level tie-breakers specified; cross-level mismatches surfaced to user.
- **DEC-4 (medium):** WebFetch results are L4; consuming skills annotate the load site with the `<!-- TRUST: ... -->` marker.
- **DEC-5 (medium):** Cross-session memory entries are L2 if <30 days old and current, else L5.
- **DEC-6 (high):** `/build`, `/design`, `/recon` SKILL.md must contain at least one `TRUST:` annotation at external-content load points.

## Integration Points

- **#177 source-driven-development:** SDD fetches external vendor docs via WebFetch — must annotate L4 and reference this hierarchy.
- **#179 noticed-but-not-touching:** Also annotates `/build`; coordinate section positioning.
- **#176 anti-rationalization-tables:** Also touches `/build` and `/design`; coordinate section positioning.

## Out of Scope

- Runtime enforcement or a "trust-level linter."
- Modifying compaction behavior or memory eviction.
- Ranking search results by trust at load time.
