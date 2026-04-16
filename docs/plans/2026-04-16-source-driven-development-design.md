---
ticket: "#177"
epic: "#177"
title: "Source-driven development skill"
date: "2026-04-16"
source: "spec"
---

# Source-Driven Development — Design Doc

## Motivation

Inspired by [addyosmani/agent-skills] `source-driven-development`. Agents routinely
implement against deprecated / renamed / re-signatured APIs using stale training-data
recall. These bugs pass all gates because logic is correct but the API surface is wrong,
and they surface only at runtime (or worse, silently). For a solo dev, this failure class
is disproportionately expensive.

The proposed skill enforces a four-phase loop — **Detect → Fetch → Implement → Cite** —
and bans Stack Overflow, Medium posts, and training-data recall as *primary* sources.

## Goals / Non-goals

**Goals**
- Ship a skill that forces the four-phase loop when touching external APIs.
- Hook `/build` (and optionally `/debugging`, `/migrate`) to dispatch it automatically.
- Require source citations on non-obvious external API usage.
- Surface doc/project-code conflicts to the user rather than silently resolving.

**Non-goals**
- Cross-session doc caching.
- A local docs mirror.
- Deep rewrite of `/build`'s phase structure.

## Architecture

### DEC-1 (medium confidence) — Skill placement

Three options were evaluated:

| Option | Pros | Cons |
|---|---|---|
| A: Standalone skill only | Reusable in any skill (`/debugging`, `/migrate`, ad-hoc) | Easy to forget; relies on the agent remembering |
| B: `/build` phase only | Guaranteed execution during `/build` | Not used by debug/migrate; can't be invoked ad-hoc |
| **C: Both** (recommended) | Coverage across orchestrators + explicit invocation available | Slightly higher maintenance (two integration surfaces) |

**Decision: Option C.** Define the canonical protocol in a standalone skill
(`skills/source-driven-development/SKILL.md`). Add a lightweight invocation hook inside
`skills/build/build-implementer-prompt.md` (and, pending T3, reference points in
`/debugging` and `/migrate`) that dispatches it when external API usage is detected in
the change context.

Reasoning: A pure `/build`-only phase would miss debug-time regressions (where an agent
"fixes" code against a stale API recall). A pure standalone skill would be
under-invoked — solo devs need the guardrail most when they're not thinking about it.
Option C pays a small duplication cost (integration hook + skill body) in exchange for
universal coverage.

Reversibility: high — integration hook is a few lines of implementer-prompt text; it can
be deleted without touching the skill.

### Phase 1 — Detect Stack

Agent identifies frameworks/libraries in scope using layered heuristics:

1. **Manifest scan**: `package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`,
   `go.mod`, `*.csproj`, `Gemfile`, `pom.xml`.
2. **Import scan**: top-of-file imports in the files being modified.
3. **Ticket body**: explicit framework mentions in the task description.
4. **Prompt mentions**: user prompt includes a framework/library name.

Output: a structured list of `{framework, version_if_known, relevant_api_surface}`.
The `relevant_api_surface` is the narrowest plausible section (e.g., "React 19 Server
Components", not "React").

### Phase 2 — Fetch Official Docs

Source hierarchy (DEC-2, **high confidence**):

1. **Official docs** — `docs.<framework>.com`, `<framework>.readthedocs.io`,
   canonical `/docs` on the project's own site.
2. **Official blog / release notes** — for recent/breaking API changes.
3. **Upstream source / type definitions** — public API source in the framework's own
   repo (e.g., `.d.ts` files, exported module signatures). Use when docs lag a release.
4. **Web standards** — MDN, w3c, whatwg specs for browser/platform APIs.
5. **Compatibility tables** — caniuse, kangax compat-table for feature support.

**Explicitly banned as primary sources:**
- Stack Overflow answers
- Medium / dev.to / personal blog posts
- Random GitHub READMEs (unless it is the framework's own upstream repo)
- Training-data recall

Banned sources may be used *only* as secondary corroboration after an official source is
consulted, and must never be cited as the authority.

**Detecting training-data recall** (the hardest to enforce): the skill requires that
*every* non-obvious external API call in the diff carries either (a) a citation footer
or inline comment with a URL + fetch date, or (b) appears already elsewhere in project
code. Absence of both is the signal that the agent wrote the call from recall. This is
checkable by the selection eval (INV-3) and spot-checkable by reviewers.

Fetch via `WebFetch` tool. Capture URL + fetch date.

### Phase 3 — Implement

Agent implements using the documented pattern verbatim. If the project's existing
code deviates from current docs (e.g., uses a deprecated API), the agent **must surface
the conflict to the user** before proceeding, not silently resolve it in either
direction. This is checkable via INV-3 during selection evals and routable to
`/debugging` or a user decision.

### Phase 4 — Cite

Citations are required when using an external API that isn't already used elsewhere in
the project's code (i.e., when the agent is introducing a new API surface). Format
(DEC-3, medium confidence — author picks per change):

- **Commit footer**: `Source: <url> (YYYY-MM-DD)` — preferred for routine usage.
- **Inline code comment**: placed directly above the non-obvious call — preferred when
  the pattern is unintuitive, counter-idiomatic, or version-sensitive.

Citations must include the fetch date so a future reader can detect doc drift.

### Trigger condition (meta-skill integration)

The skill auto-triggers when **all** are true:
- Prompt or change context mentions a framework/library by name, OR files being modified
  import one.
- The change is ≥ 5 LOC of **non-test, non-comment** code touching the external API
  surface (DEC-4, **low confidence** — heuristic threshold, flag for review; tune via T5
  evals).

Trivial changes (typo fixes, formatting, rename-only refactors) skip the skill.

## Key decisions

| ID | Decision | Confidence | Alternatives |
|---|---|---|---|
| DEC-1 | Both standalone skill + `/build` integration hook | medium | standalone only, `/build` phase only |
| DEC-2 | Source hierarchy: official docs > official blog > web standards > compat tables | high | flat equal-weight list |
| DEC-3 | Citation format: commit footer OR inline comment, author's call | medium | mandate one format |
| DEC-4 | 5-LOC triviality threshold | low | no threshold; lines-changed, files-changed, or tokens-changed metric |
| DEC-5 | WebFetch permission scope: add specific doc domains incrementally | high | broad WebFetch(*) grant |

DEC-1 and DEC-4 are flagged for user review.

## Integration points

- **`skills/build/build-implementer-prompt.md`** — add dispatch hook in the implementer
  job description.
- **`skills/build/SKILL.md`** — reference the new skill in the skill list.
- **`skills/recon/SKILL.md`** — reuse recon's "external-reference investigation"
  vocabulary; do not duplicate its investigation patterns.
- **`#176` anti-rationalization tables** — adjacent ticket; both add to `/build` SKILL.md.
  Coordinate section ordering.

## Security considerations

- **External input**: `WebFetch` ingests arbitrary web content into agent context.
  Mitigation: source hierarchy constrains domains; banned-sources list reduces
  prompt-injection attack surface from random blogs.
- **Implicit trust**: skill trusts docs domains. Mitigation: DEC-5 — add domains to
  `WebFetch` allowlist incrementally in `.claude/settings.local.json` (current allow
  list only grants `WebFetch(domain:github.com)`; T3 must extend it per the T2 seed
  table), not a blanket grant.
- **Trust classification (per #180 trust-hierarchy)**: WebFetch results are **L4
  Verify-first** content. The skill must not treat fetched docs as authoritative
  absent verification against L3 (code/tests) or L2 (design/plan) evidence. The
  SDD skill's citation + "implement from source" protocol is the verify-before-use
  duty — citations record the L4 source; implementation still has to match actual
  call-site behavior the agent can run or read.
- Recommend running `siege` on this skill before merge given external-input surface.

## Open questions

- Should `/debugging` and `/migrate` get the same integration hook on first release, or
  only `/build`?
- Should citations be contract-checked (INV) or left as a skill-internal invariant?
- DEC-4's 5-LOC threshold is a guess — needs eval-driven tuning.
