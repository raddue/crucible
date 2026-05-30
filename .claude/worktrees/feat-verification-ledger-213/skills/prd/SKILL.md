---
name: prd
description: "Generate a stakeholder-facing PRD from a design doc. Use when you have a finalized design doc and need a non-technical product requirements document for archival or sharing. Triggers on /prd, 'generate PRD', 'write a PRD', 'product requirements'."
---

# PRD Generator

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Generates a Product Requirements Document (PRD) from a finalized design doc. The PRD reformats technical design decisions into stakeholder-friendly language — problem statement, user stories, requirements, scope, success metrics.

**Announce at start:** "I'm using the PRD skill to generate a product requirements document."

**Core principle:** The PRD derives everything from the design doc. It does not introduce new decisions or requirements — it translates existing technical decisions for a non-technical audience.

## When to Use

- After `/design` or `/build` Phase 1 completes — you have a finalized design doc
- When a stakeholder asks for a PRD, product spec, or requirements document
- When archiving a feature's requirements in Confluence, Jira, Notion, or similar

## Input

The skill needs a design doc path. If not provided, it searches:
1. Check if the user specified a path: `/prd docs/plans/2026-03-23-my-feature-design.md`
2. If no path: scan `docs/plans/` for the most recently modified `*-design.md` file
3. If no design docs found: inform user and stop

## The Process

1. **Read the design doc** — verify it exists and has the expected structure (Overview, acceptance criteria, etc.)
2. **Dispatch a Sonnet PRD Writer** using the prompt template at `skills/build/prd-writer-prompt.md`
   - Input: full design doc text
   - Output: PRD in standard format
3. **Save** to `docs/prds/YYYY-MM-DD-<topic>-prd.md`
4. **Commit:** `docs: add PRD for [feature]`
5. **Report** the file path to the user

## PRD Structure

The generated PRD follows a fixed structure:

1. **Problem Statement** — what problem this solves, in plain language
2. **User Stories / Use Cases** — "As a [role], I want [goal] so that [benefit]"
3. **Requirements** — functional and non-functional, each a testable statement
4. **Scope** — what's included
5. **Out of Scope** — what was explicitly excluded
6. **Success Metrics** — measurable outcomes
7. **Technical Notes** — brief architectural context for stakeholders who want it
8. **Dependencies** — external systems, teams, or services

## Integration

**Called by:**
- **crucible:build** — Phase 1 Step 2.5 (after design finalized, before acceptance tests). Runs by default in feature mode, skipped in refactor mode.

**Standalone usage:**
- `/prd <design-doc-path>` — generate PRD from any design doc
- `/prd` (no args) — auto-detect most recent design doc

**Prompt template:** `skills/build/prd-writer-prompt.md` (shared with build pipeline)

## Red Flags

- Inventing requirements not in the design doc
- Including code, file paths, or architecture diagrams in the PRD
- Writing more than 2 pages — PRDs should be concise
- Skipping sections rather than stating "Not specified in design"
