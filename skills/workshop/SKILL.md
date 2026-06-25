---
name: workshop
description: Tour of the Crucible workshop — the headline orchestrators users invoke directly. Use when the user asks "what skills are available?", "where do I start?", "what should I use for X?", "give me a tour of Crucible", "what are the main commands?", or any onboarding-style question. Also use after onboarding a new user or when someone needs to pick the right tool for a specific task. This is the on-demand catalog tour; the silent conversation-start activation protocol itself is getting-started.
---

# Workshop

A curated tour of the headline Crucible skills — the orchestrators a user typically invokes directly. Crucible ships ~52 skills total, but most of those are sub-skills that orchestrators dispatch internally. This skill is the **front door**: when you don't know which command to type, start here.

**Skill type:** Reference. Read this skill when the user is choosing what to do; do not dispatch subagents from it.

## Pick by what you're doing

### Starting fresh on something new

| Skill | When to reach for it |
|---|---|
| `/build` | Going from idea to working code. The full pipeline — design → plan → TDD execute → quality gate → PR. One command, complete arc. |
| `/design` | You want to explore design space before any code. Produces a design doc. Build runs this internally; invoke directly when the design itself is the deliverable. |
| `/planning` | You already have a spec or requirements and need a multi-step implementation plan. Build runs this too; invoke directly for plan-only work. |
| `/spec` | You have a GitHub epic with child tickets and want autonomous spec generation (design + plan + contracts per ticket) without human interaction. |

### Mid-feature work

| Skill | When to reach for it |
|---|---|
| `/temper` | Iterative code review on a PR or `<base>..<head>` range. Loops fresh-eyes reviewers until clean. Forge-agnostic (GitHub / GitLab / Bitbucket / self-hosted). Renamed from `/code-review` on 2026-05-17. |
| `/debugging` | Any bug, test failure, or unexpected behavior. Hypothesis loop, fix dispatch, verification. |
| `/quality-gate` | Iterative red-team on any artifact (design doc, plan, code, hypothesis, mockup). Loops until clean or stagnation. Invoked by other orchestrators; invoke directly when the artifact is standalone. |
| `/migrate` | Framework upgrade, API version bump, major dependency change, deprecation removal. Produces a phased migration plan and optionally executes it via build's refactor mode. |

### Inspection and discovery

| Skill | When to reach for it |
|---|---|
| `/delve` | Instance-bug review of a diff or path — parallel finder angles + verify gate, prints ranked, verified defects with reproductions. Report-only (no merge verdict, no fix loop; `--fix` / `--comment` are opt-in). Use when "find bugs in this diff", "scan this file for defects", or you want concrete reproducible bugs. |
| `/audit` | **Systemic** review of an existing subsystem or non-code artifact (design / plan / concept) — recurring patterns, structural drift, absences with no single reproduction. Four lenses per artifact type, find-and-report only (does not fix). Instance bugs route to `/delve` via `--bugs`; complexity to `/prospector`. Use when "this has accumulated cruft nobody's looked at in months." |
| `/siege` | Security audit. Six parallel attacker-perspective Opus agents, iterates until zero Critical/High. Heavy — reserve for security PRs, scheduled reviews, or post-incident. |
| `/recon` | Codebase investigation. Layered Investigation Brief with structure / patterns / scope / prior-art. Use before any task that needs codebase understanding you don't have. |
| `/prospector` | Architectural friction finder. Explores the codebase for refactor candidates and proposes competing redesigns. Use when "what should I refactor next?" |

> **`/delve` vs `/recon` / `/prospector` — different machines.** `/delve` hunts concrete *instance bugs* in a specific diff or path (one defect, one reproduction). `/recon` and `/prospector` *explore* unfamiliar code — recon maps structure / patterns / prior-art before a task; prospector finds architectural friction and proposes redesigns. Reach for `/delve` when you have a **change** and want its bugs; reach for recon / prospector when you have a **codebase** and want to understand or improve it. Within the review trio: `/delve` = instance bugs (one-shot), `/audit` = systemic patterns, `/temper` = merge gate + iterative fix loop.

### Wrapping up and reflecting

| Skill | When to reach for it |
|---|---|
| `/finish` | Implementation is complete, tests pass, and you need to decide how to integrate — merge, PR, cleanup. Guides the completion decision. |
| `/forge` | A significant task just completed. Writes a retrospective; proposes skill mutations after 10+ retrospectives accumulate. Compounding knowledge accelerator. |
| `/handoff` | End-of-session. Writes a handoff doc for the next session — continuation of current arc, or proposed next pickup if the current arc is wrapping. |

## Quick reference by trigger phrase

| User says… | Reach for |
|---|---|
| "Let's build X" / "Implement Y" | `/build` |
| "Review my PR" / "Code review" | `/temper` |
| "Find bugs in this diff" / "Scan this file for defects" | `/delve` |
| "I have a bug" / "Test is failing" | `/debugging` |
| "Audit this design" / "Review this plan" | `/audit` |
| "Check the save system for bugs" | `/audit` (systemic) or `/audit --bugs` (+ `/delve` instance sweep) |
| "Security review" / "Threat model" | `/siege` |
| "What does X do?" / "How does this codebase work?" | `/recon` |
| "What should I refactor?" | `/prospector` |
| "Run quality gate on this" | `/quality-gate` |
| "Upgrade React to 19" / "Remove deprecated APIs" | `/migrate` |
| "I'm done, what's next?" | `/finish` |
| "Write a retrospective" | `/forge` |
| "End of session, write a handoff" | `/handoff` |

## Pipelines (composition)

The big skills compose. The most common pipelines:

- **Full feature:** `/build` is the canonical one. Internally runs `/design` → `/planning` → execute → `/temper` per task → `/inquisitor` → `/quality-gate` → `/finish`.
- **Standalone design + plan:** `/design` produces a doc → user reviews → `/planning` produces a plan → execute manually or feed to `/build`.
- **Post-merge reflection:** `/forge` after a significant arc; `/handoff` at session boundary.
- **Recon-first:** `/recon` before `/build` or `/design` when the codebase is unfamiliar.

## What's not in this list (intentionally)

Crucible has ~52 skills; this list curates ~15. Skills omitted here are either:
- **Sub-skills** dispatched by orchestrators (e.g., `red-team`, `inquisitor`, `adversarial-tester`, `checkpoint`, `verify`, `assay`, `innovate`, `cartographer-skill`) — invoked indirectly, not part of the user-facing menu.
- **Domain-specific** (e.g., `mock-to-unity`, `ui-verify`, `mockup-builder`) — load when their domain triggers.
- **Utility / meta** (e.g., `skill-creator`, `stocktake`, `recall`, `replay`, `worktree`, `parallel`, `merge-pr`, `distill`, `test-coverage`, `review-feedback`, `consensus`, `getting-started`, `project-init`, `test-driven-development`) — domain knowledge or workflow plumbing rather than direct-invocation commands.

Run `/skills` (Claude Code built-in) for the full catalog.

## See also

- `README.md` — top-level pitch, install, what-you-get bullets
- `docs/architecture.md` — how the orchestrators compose
- `docs/skills.md` — full 52-skill catalog with eval deltas
