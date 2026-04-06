---
ticket: "#130"
title: "Recon Integration Contracts — Implementation Plan"
date: "2026-04-06"
source: "spec"
---

# Recon Integration Contracts — Implementation Plan

## Task Overview

2 tasks. Single file modified (prompt template). No code, no runtime dependencies.

### Task 1: Add integration contract assessment to impact-analyst prompt

**Files:** `skills/recon/impact-analyst-prompt.md`
**Complexity:** Low
**Dependencies:** None

Add a structured subsection within the "Integration Risks" section of the prompt. Insert after the existing 3 bullet points (API contracts, assumptions, race conditions) and before the "Data Impact" section.

Content to add:

1. **Conditional framing:** "When the proposed change touches code that integrates with external systems (APIs, databases owned by other teams, third-party services), also assess these integration health checks:"

2. **4 checks:**
   - Abstraction check: Is the external system behind an interface? Could it be swapped without changing business logic?
   - Write direction: Does the system write directly to another system's storage? Flag direct INSERTs/writes to external tables — should use staging tables or outbound queues.
   - Shared schema coupling: Do two applications share a database schema as their integration mechanism? Flag as coupling disguised as simplicity.
   - Fallback path: Does every integration have a fallback when the external system is unavailable? (manual entry with verification flag, queue and retry, operator override)

3. **Output format addition:** Add corresponding output format entries to the "Integration Risks" section of the Output Format block.

### Task 2: Update README

**Files:** `README.md`
**Complexity:** Low
**Dependencies:** Task 1

No README change needed — the recon skill description already covers impact analysis generically. The addition of 4 checks within an existing section doesn't warrant a README update.

Actually, skip this task. The enhancement is internal to an existing prompt template section.

## Dependency Graph

```
Task 1 (prompt template edit) — standalone, no dependencies
```

## Implementation Notes

- **Single file edit.** One prompt template, one section addition.
- **Preserve existing content.** The 3 existing Integration Risks bullets are kept. The 4 new checks are additive.
- **Token budget awareness.** The checks are conditional — they only produce output when integrations are in scope, so they don't inflate every analysis.
