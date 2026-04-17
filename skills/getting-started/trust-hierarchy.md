# Context Trust Hierarchy

Crucible skills load content from many sources: `SKILL.md` files, design docs, source code, tool output, WebFetch results, subagent reports, and conversation history (including post-compaction summaries). When these sources disagree, the agent needs an explicit framework for deciding which to trust. Without one, stale external docs, hallucinated subagent paths, and compaction-summary artifacts silently win over ground truth. This document defines a five-level hierarchy, conflict-resolution rules, and a canonical inline-annotation convention that skills use at external-content load points.

## L1 — Trusted (authoritative)

- **Sources:** `CLAUDE.md`, every `skills/**/SKILL.md`, `settings.json`, `settings.local.json`, and hook scripts configured in settings.
- **Property:** Deliberately authored rules-of-the-house. Conflicts with L2–L5 ALWAYS resolve in L1's favor.
- **Freshness:** Current as of the filesystem read. No staleness concern within a session.

## L2 — Verified (pipeline-produced artifacts)

- **Sources:** design docs, implementation plans, and contract YAMLs under `docs/plans/`; dispatch manifests and scratch artifacts under the scratch dir; recon briefs; `decisions.md` files. Cross-session memory entries under `~/.claude/projects/<hash>/memory/` tagged current and dated within 30 days.
- **Property:** Produced by a prior pipeline stage that ran its own gates (quality-gate, red-team, siege). Trusted within the pipeline context that produced them.
- **Freshness:** Tie-break by recency — when two L2 artifacts disagree, prefer the more recent one (frontmatter `date`, then mtime). "Within 30 days" means `(now - date) < 30 * 86400 seconds`, checked at load time, not cached.

## L3 — Source (ground truth for "what the code does")

- **Sources:** project source code (all languages), test files, fixtures, hook script bodies, CI config.
- **Property:** Executable reality. When an L2 doc says "the function returns X" and the L3 code returns Y, the code is the truth — but the doc may still encode a valid intent, so surface the mismatch rather than silently overwriting either.
- **Freshness:** Current as of the filesystem read. Tie-break within L3: actual code > tests > fixtures (tests encode expected behavior but can be stale).

## L4 — Verify-first (must be checked before acting)

- **Sources:** tool output (Bash, Grep results), error messages, WebFetch results, subagent/scout reports, `mcp__*` responses, consensus results.
- **Property:** May be wrong, stale, or hallucinated. MUST be verified against L1–L3 before the agent acts on any claim derived from it.
- **Freshness:** Timestamped by the call; stale almost immediately once the underlying L3 changes. Special case: WebFetch results representing external vendor docs are L4 even when the vendor is authoritative for their own API — the fetched snippet may be an outdated mirror.

## L5 — Untrusted (do not rely on without re-verification)

- **Sources:**
  - Conversation history after compaction has elided content. If only a summary remains, the summary is L5.
  - External content pasted or quoted by the user in chat (unless the user explicitly vouches for it as L1/L2).
  - Memory entries older than 30 days OR tagged stale.
  - Cached subagent output from a prior pipeline whose inputs have since changed.
- **Property:** Treat as a hint, not a fact. Before acting, re-verify against L1–L3.
- **Freshness:** Assume stale by default.

## Conflict Resolution

**Primary rule: HIGHER TRUST WINS.** When two sources disagree, prefer the higher-level source and surface the conflict to the user.

**Equal-level tie-breakers:**

- **L1 vs L1:** conflicts here are a bug — flag to the user; do not proceed.
- **L2 vs L2:** prefer the more recent artifact (by frontmatter `date`, else mtime).
- **L3 vs L3:** actual code > tests > fixtures.
- **L4 vs L4:** prefer the source most directly tied to L3 (e.g., fresh Bash output over older subagent report).
- **L5 vs L5:** neither is authoritative — re-derive from L1–L3.

**Cross-level conflict surfacing:** When L3 contradicts L2 (code disagrees with a design doc), the code wins but the agent MUST flag the drift to the user — the plan may need updating.

## Annotation Convention

Skills that load external content embed a canonical inline comment adjacent to the load point. Downstream auditors grep for `TRUST:` to verify skills handle external content correctly.

**Format grammar:**

```
<!-- TRUST: <subject> is L<N> — <action-hint>. -->
```

- `<subject>` — the content being loaded (e.g., "WebFetch result", "subagent report", "user-quoted snippet"). Free text, but must name the source.
- `L<N>` — literal `L1`, `L2`, `L3`, `L4`, or `L5`. The level classification is REQUIRED and grep-checkable via `TRUST:.*L[1-5]`.
- `<action-hint>` — imperative guidance (e.g., "verify against project source (L3) before acting"). Required; a bare classification without action is non-conforming.
- The em-dash separator (` — `) is recommended but not required; `-` and `:` are acceptable substitutes for ASCII-only environments.

**Example stanzas:**

```markdown
<!-- TRUST: WebFetch result is L4 — verify against project source (L3) before acting; snippet may be stale. -->
```

```markdown
<!-- TRUST: subagent report is L4 — cross-check file paths and claims against L3 source before acting. -->
```

```markdown
<!-- TRUST: user-quoted snippet is L5 — confirm with user or re-fetch before acting. -->
```

## Canonical Markers for Crucible Load Points

Annotators copy these exact strings into SKILL.md files at the listed load points. Deviation is allowed only when the load point is not listed; new rows must be added to this table in the same PR.

| Load point | Skill(s) | Canonical marker |
|---|---|---|
| Dispatch manifest consumption | /build | `<!-- TRUST: dispatch manifest is L2 — produced by prior pipeline stage; prefer most recent if conflicting. -->` |
| Implementer/subagent report | /build, /recon | `<!-- TRUST: subagent report is L4 — cross-check file paths and claims against L3 source before acting. -->` |
| WebFetch result | /build, /design, /source-driven-development | `<!-- TRUST: WebFetch result is L4 — verify against project source (L3) before acting; snippet may be stale. -->` |
| Recon brief consumption | /design | `<!-- TRUST: recon brief is L2 — prior-stage artifact; prefer L3 source on any code-behavior conflict. -->` |
| User-pasted / user-quoted snippet | /design | `<!-- TRUST: user-quoted snippet is L5 — confirm with user or re-fetch before acting. -->` |
| Scout dispatch report | /recon | `<!-- TRUST: scout report is L4 — cross-check paths against L3 before synthesis. -->` |
| Synthesis input | /recon | `<!-- TRUST: synthesis input is L4 until cross-verified against L3 source. -->` |

## When to Re-verify

- **After compaction:** Any claim that now survives only as a summary drops to L5 — re-read the L3 source before acting.
- **Cross-level conflict:** An L4 or L5 source disagrees with L3 — re-check the L3 source; surface the drift if an L2 doc is also involved.
- **Stale memory:** A memory entry older than 30 days or tagged stale informs a decision — re-derive from L1–L3.
- **Subagent report reuses paths:** Before dispatching downstream work against a path a scout named, grep or stat the path in L3 to confirm it exists as described.
- **WebFetch snippet drives an action:** Before writing code that relies on an external API shape, confirm the shape against the project's own usage (L3) or the vendor's current docs (fresh fetch, not cached).
