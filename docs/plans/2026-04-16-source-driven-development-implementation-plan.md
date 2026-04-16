---
ticket: "#177"
epic: "#177"
title: "Source-driven development skill"
date: "2026-04-16"
source: "spec"
---

# Source-Driven Development — Implementation Plan

Complexity: **Tier 2 (Medium)**. Six tasks, moderate coupling to `/build` prompt templates.

## Tasks

### T1 — Create `skills/source-driven-development/SKILL.md`

Full protocol body: Detect → Fetch → Implement → Cite. Include:
- Skill frontmatter (name, description, triggers).
- Four phase sections with explicit outputs per phase.
- Source hierarchy with banned-sources list.
- Citation formats (commit footer + inline comment) with examples.
- Trigger heuristics (framework mention + ≥5 LOC).
- Cross-links to `skills/build/SKILL.md` and `skills/recon/SKILL.md`.

**Depends on:** T2 (detection table informs the Detect-phase body).

### T2 — Create `skills/source-driven-development/detect-stack.md`

Reference table mapping common frameworks → canonical doc URLs. Seed rows:
- React → `react.dev`
- Next.js → `nextjs.org/docs`
- Vue → `vuejs.org/guide`
- Django → `docs.djangoproject.com`
- FastAPI → `fastapi.tiangolo.com`
- ASP.NET Core → `learn.microsoft.com/aspnet/core`
- Rails → `guides.rubyonrails.org`
- Express → `expressjs.com`
- PostgreSQL → `postgresql.org/docs`
- Tailwind → `tailwindcss.com/docs`
- TypeScript → `typescriptlang.org/docs`
- MDN for web standards.

Add one-sentence "version signal" notes (e.g., "React 19 = Server Components default").

**Depends on:** none. **Must precede T1.**

### T3 — Update `skills/build/build-implementer-prompt.md` + settings allowlist

Inject a "Source Consultation" paragraph in the implementer's **Your Job** section:
- If change context includes an external framework/library AND change is ≥5 LOC
  (non-test, non-comment), invoke `crucible:source-driven-development` before
  implementation.
- Reference the citation requirement in the definition-of-done block.

Also extend `.claude/settings.local.json` `permissions.allow` with `WebFetch(domain:…)`
entries for each canonical doc host in T2's seed table (react.dev, nextjs.org,
vuejs.org, docs.djangoproject.com, fastapi.tiangolo.com, learn.microsoft.com,
guides.rubyonrails.org, expressjs.com, postgresql.org, tailwindcss.com,
typescriptlang.org, developer.mozilla.org). Current file only grants `github.com`.

**Coordination:** `/build` SKILL.md + implementer prompt are also edited by #176
(anti-rationalization tables), #179, and #180. Order merges so edits do not conflict;
prefer merging #177 after #176 so citation requirement can reference anti-rat rows.

**Depends on:** T1.

### T4 — Update `skills/build/SKILL.md`

Add `source-driven-development` to the referenced-skills list. Coordinate section
ordering with #176 (anti-rationalization tables).

**Depends on:** T1.

### T5 — Selection evals

Add eval cases to `skills/skill-selection-evals/evals/evals.json` and run them via
`skills/skill-selection-evals/scripts/run_selection_eval.py` (runner introduced by
#174 T5b at commit `605bbaa`). **Prerequisite:** rebase `spec/176-180` onto `main`
before T5 so the runner is available on this branch.

The new eval cases must:
- Prompt the agent to implement against a named external API (e.g., "add a React 19
  Server Component that fetches from Supabase").
- Assert `source-driven-development` is in the expected_skill set.
- Include one negative case (pure internal refactor, no externals) where the skill must
  NOT be invoked.
- Cover at least one framework from T2's seed table per major ecosystem (JS, Python,
  .NET) to exercise cross-language detect heuristics.

**Depends on:** T3, plus rebase onto main.

### T6 — Documentation

Add a row for `source-driven-development` to the main skills README / INDEX
(`skills/README.md` or equivalent discovery doc). One-line description plus link.

**Depends on:** T3.

## Dependency graph

```
T2 ──▶ T1 ──▶ T3 ──▶ T5
              │  └──▶ T6
              └──▶ T4
```

T2 → T1 is hard (skill body cites table). T1 → {T3, T4} is hard (integrations reference
the skill). T5, T6 depend on T3.

## Risks

- **WebFetch domain allowlist**: T3's dispatch will fail if `WebFetch(domain:*)` is not
  granted for doc sites. Mitigation: add domains from T2's table to the project
  settings allowlist as part of T3; expand incrementally (DEC-5).
- **DEC-4 triviality threshold miscalibration**: 5 LOC may be wrong. Mitigation: T5
  evals will surface false-positive/false-negative rates.
- **Citation hygiene drift**: authors may skip citations despite the skill. Mitigation:
  consider a post-merge reconciler hook in a follow-up ticket.

## Definition of done

- All six tasks merged.
- T5 evals pass with ≥80% selection accuracy on positive cases and 100% on the negative
  case.
- `siege` clean on the new skill (external-input surface).
- Quality-gate + red-team + innovate run on design + plan (mandated by project memory).
