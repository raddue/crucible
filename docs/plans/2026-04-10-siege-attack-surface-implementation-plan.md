---
ticket: "#117"
title: "Siege Attack Surface Discovery -- Implementation Plan"
date: "2026-04-10"
source: "spec"
---

# Siege Attack Surface Discovery -- Implementation Plan

## Task Overview

3 tasks in a single wave. All changes are to `skills/siege/SKILL.md`. No agent prompt templates are modified -- the exposure map flows through existing Tier 1/Tier 2 context mechanisms.

## Wave 1: SKILL.md Changes

### Task 1: Add Step 2.5 -- Attack Surface Enumeration

**Files:** `skills/siege/SKILL.md`
**Complexity:** Medium
**Dependencies:** None

Insert a new "Step 2.5: Attack Surface Enumeration" section between the existing Step 2 (Scope and Manifest) and Step 3 (Load Persistent Threat Model) in Phase 1.

Content to add:
1. **Sub-step A: Framework Detection** -- table of framework detection signals (package.json dependencies, csproj references, Gemfile entries, etc.) mapping to framework names. Fallback: skip Step 2.5 if no framework detected, note in scope limitations.
2. **Sub-step B: Route/Endpoint Enumeration** -- table of grep patterns per framework for extracting registered routes. Each match yields: HTTP method, route path, source file, line number. Document limitations (dynamic registration, middleware mounts, convention-based routing approximation).
3. **Sub-step C: Exposure Map and Cross-Reference** -- build exposure map table (method, route, file, line, in-manifest flag). Cross-reference each endpoint's source file against manifest.md. Files with endpoints NOT in manifest are flagged as gaps.

**Placement:** After the "USER GATE" paragraph at the end of Step 2, before "### Step 3: Load Persistent Threat Model".

### Task 2: Add Gap Handling and Context Integration

**Files:** `skills/siege/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1

Add gap-handling rules to Step 2.5:
1. Gap files (endpoints not in manifest) are automatically appended to manifest.md with tag `[attack-surface-gap]`
2. Exposure map written to `scratch/<run-id>/exposure-map.md`

Modify Phase 2 context assembly:
1. In "Step 1 -- Build Tier 1", add: append exposure map summary (endpoint count + gap list, 15 lines max) to tier1-context.md
2. In "Step 2 -- Build Tier 2 partitions", add: Boundary Attacker partition prioritizes `[attack-surface-gap]` files from the manifest

Add to File Inventory table:
- `exposure-map.md` -- written Phase 1 Step 2.5 -- "Enumerated endpoints with manifest cross-reference"

### Task 3: Add Threat Model Integration

**Files:** `skills/siege/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1

Modify the Persistence > Threat Model section:
1. In the Attack Surfaces subsection, note that exposure map endpoints feed the "Attack Surfaces" entries
2. New endpoints not in prior threat model are flagged "new attack surface" in the Threat Model Delta
3. Endpoints in prior threat model but absent from current enumeration are flagged "retired surface"

This enables drift detection: if an endpoint existed in the last Siege run but no longer appears in the codebase, it surfaces in the report's Threat Model Delta section.

## Verification

After all tasks, confirm:
1. Phase 1 has Step 2.5 between Step 2 and Step 3
2. Framework detection table covers Express, Fastify, NestJS, Next.js, Flask, FastAPI, Django, ASP.NET Core, Rails, Spring Boot, Gin, Gorilla Mux, Actix Web
3. Route enumeration patterns are documented per framework
4. Gap files flow into manifest and Boundary Attacker partition
5. Exposure map summary appears in Tier 1 context rules
6. `exposure-map.md` appears in File Inventory
7. Threat model delta references exposure map for drift detection
