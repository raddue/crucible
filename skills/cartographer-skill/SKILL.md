---
name: cartographer
description: Use when exploring unfamiliar code and want to persist what you learn, when starting a task and want to consult known codebase structure, or when a subagent needs module-specific context for implementation or review
---

# Cartographer

## Overview

Living architectural map of the codebase that accumulates across sessions. After exploration, captures what was learned. Before tasks, surfaces relevant structural knowledge. Subagents receive module-specific context so they don't make wrong assumptions.

**Core principle:** The agent that re-discovers the same codebase every session wastes the first 20% of every task. The Cartographer remembers the terrain.

**Announce at start:** "I'm using the cartographer skill to [record what I learned about this area / consult the codebase map / load module context for a subagent]."

## When to Use

```dot
digraph cartographer_modes {
    "Just explored unfamiliar code?" [shape=diamond];
    "Starting a new task?" [shape=diamond];
    "Dispatching a subagent?" [shape=diamond];
    "Record Discovery" [shape=box];
    "Consult Map" [shape=box];
    "Load Module Context" [shape=box];
    "Not applicable" [shape=box];

    "Just explored unfamiliar code?" -> "Record Discovery" [label="yes"];
    "Just explored unfamiliar code?" -> "Starting a new task?" [label="no"];
    "Starting a new task?" -> "Consult Map" [label="yes"];
    "Starting a new task?" -> "Dispatching a subagent?" [label="no"];
    "Dispatching a subagent?" -> "Load Module Context" [label="yes, if module file exists"];
    "Dispatching a subagent?" -> "Not applicable" [label="no"];
}
```

**Three modes:**
- **Record** — after significant exploration during build, debugging, or investigation
- **Consult** — before brainstorming, planning, or execution (pairs with `crucible:forge` feed-forward)
- **Load** — when dispatching implementer/reviewer/investigator subagents into a mapped area

## Storage

All data lives in the project memory directory:

```
~/.claude/projects/<project-hash>/memory/cartographer/
  map.md                # High-level module map (max 200 lines)
  conventions.md        # Codebase patterns and conventions (max 150 lines)
  landmines.md          # Non-obvious things that break (max 100 lines)
  modules/              # Per-module detail files (max 100 lines each)
    funding.md
    auth.md
    events.md
    ...
```

### File Size Caps

| File | Max Lines | Loaded By | When |
|------|-----------|-----------|------|
| `map.md` | 200 | Orchestrator | Consult mode (every task start) |
| `conventions.md` | 150 | Implementer subagents | Pasted into dispatch prompt |
| `landmines.md` | 100 | Reviewer/red-team subagents | Pasted into dispatch prompt |
| `modules/<name>.md` | 100 each | Subagents working in that area | Pasted into dispatch prompt |

**The orchestrator only ever loads `map.md`.** Everything else stays in subagent contexts.

---

## Mode 1: Record Discovery

### When to Trigger

After any significant exploration — the agent read 5+ files, traced a call chain, investigated a module's behavior, or discovered something non-obvious about the codebase. This happens naturally during `crucible:build`, `crucible:systematic-debugging`, and `crucible:executing-plans`.

### The Process

1. Dispatch a **Cartographer Recorder** subagent (Sonnet) using `./recorder-prompt.md`
2. Provide: list of files explored, what was learned, any surprises or gotchas discovered
3. Subagent returns structured updates for the relevant files
4. Write or update the appropriate files:
   - New module discovered → create `modules/<name>.md`
   - Existing module, new info → update `modules/<name>.md`
   - New convention identified → update `conventions.md`
   - New landmine found → update `landmines.md`
   - Module map changed → update `map.md`

### What Gets Recorded

**Module files (`modules/<name>.md`):**

```markdown
# <Module Name>

**Path:** src/funding/
**Responsibility:** [One sentence — what this module owns]
**Boundary:** [What does NOT belong here]

## Key Components

- `ComponentName` — [what it does, 1 line]
- `AnotherComponent` — [what it does, 1 line]

## Dependencies

- **Depends on:** [modules this one imports/calls]
- **Depended on by:** [modules that import/call this one]

## Contracts

- [Implicit or explicit contracts: "processEvent() must be idempotent"]
- [API constraints: "lender API supports single lookups only, no batch"]

## Gotchas

- [Non-obvious behavior: "webhook handler deduplicates via processEvent()"]
- [Historical context: "batch wrapper attempted 2024, reverted — see PR #234"]

## Last Updated

[ISO date, session context]
```

**Conventions file (`conventions.md`):**

```markdown
# Codebase Conventions

## Error Handling
- [How errors are handled: thrown, returned, Result type, etc.]

## Naming
- [File naming, function naming, variable conventions]

## Testing
- [Test patterns, helpers, fixtures — "use createTestLoan() from test/fixtures.js"]
- [What's flaky, what to avoid]

## API Patterns
- [How API handlers are structured]
- [Validation, auth, response format patterns]

## Last Updated

[ISO date]
```

**Landmines file (`landmines.md`):**

```markdown
# Landmines

Things that break non-obviously. Subagents reviewing or red-teaming should check these.

## Active Landmines

- **[Short title]** — [What breaks and why. Module: X. Severity: high/medium]
- **[Short title]** — [What breaks and why. Module: X. Severity: high/medium]

## Resolved Landmines

- ~~[Short title]~~ — [Resolved in session YYYY-MM-DD. How it was fixed.]

## Last Updated

[ISO date]
```

**Map file (`map.md`):**

```markdown
# Codebase Map — [Project Name]

**Last updated:** [ISO date]
**Modules mapped:** N
**Coverage:** [rough % of codebase with module files]

## Module Overview

| Module | Path | Responsibility | Mapped Detail |
|--------|------|----------------|---------------|
| funding | src/funding/ | Lender communication | Yes |
| auth | src/auth/ | Authentication/authorization | Yes |
| events | src/events/ | Event processing pipeline | No (explored, not yet detailed) |

## High-Level Dependencies

```dot
digraph deps {
    auth -> funding;
    events -> funding;
    api -> auth;
    api -> events;
}
```

## Unmapped Areas

- [Directories/modules not yet explored]

## Key Architectural Decisions

- [Top-level decisions: "monorepo with shared types", "event-driven between services"]
```

### Update Rules

1. Read the existing file before writing (merge, don't overwrite)
2. New information adds to existing sections — does not replace unless correcting an error
3. Contradictions: flag to user. "Map says X but I observed Y. Which is correct?"
4. Enforce line caps — if a module file hits 100 lines, split into sub-modules or compress
5. Mark resolved landmines with strikethrough, prune after 10 sessions
6. Update `map.md` module table whenever a new module file is created

---

## Mode 2: Consult Map

### When to Trigger

Before `crucible:brainstorming`, `crucible:writing-plans`, `crucible:executing-plans`, or `crucible:build` begins its core work. Runs alongside `crucible:forge` feed-forward.

### The Process

1. Check if `~/.claude/projects/<project-hash>/memory/cartographer/map.md` exists
2. **Cold start (no file):** Report "No codebase map exists for this project. Will record discoveries during this session." Return immediately.
3. **Data exists:** Read `map.md` (under 200 lines — safe for context)
4. Surface relevant information to the orchestrator:
   - Which modules are likely involved in this task?
   - Are there known landmines in those areas?
   - What dependencies should be considered?
5. No subagent needed — the orchestrator reads `map.md` directly and applies it

### Cold Start Lifecycle

- **First session:** No map. Agent explores normally. Record mode captures what's found. Map begins.
- **Second session:** Map has partial coverage. Consult surfaces what's known, notes gaps.
- **After 5+ sessions:** Map covers the areas the agent works in most. Feed-forward is consistently useful.
- **After 20+ sessions:** Comprehensive coverage of the active codebase.

---

## Mode 3: Load Module Context

### When to Trigger

When dispatching an implementer, reviewer, investigator, or any subagent that will work in a mapped module area.

### The Process

1. Identify which module(s) the subagent will touch (from the task description and file paths)
2. Check if `modules/<name>.md` exists for those modules
3. If yes: read the module file(s) and paste into the subagent's dispatch prompt
4. Also paste `conventions.md` into implementer prompts
5. Also paste `landmines.md` into reviewer and red-team prompts
6. If no module file exists: dispatch without it (subagent explores normally, record afterwards)

### What Each Subagent Type Gets

| Subagent Type | Gets `conventions.md` | Gets `landmines.md` | Gets `modules/*.md` |
|---------------|----------------------|---------------------|---------------------|
| Implementer | Yes | No | Yes (relevant modules) |
| Code Reviewer | No | Yes | Yes (relevant modules) |
| Red-Team | No | Yes | Yes (relevant modules) |
| Investigator (debug) | No | No | Yes (relevant modules) |
| Plan Writer | No | No | No (uses map.md via orchestrator) |

---

## Integration

### With Forge

Cartographer and Forge are complementary:
- **Forge** learns about agent behavior (process wisdom): "You tend to over-engineer"
- **Cartographer** learns about the codebase (domain wisdom): "This module has 14 consumers"
- **Together** they eliminate the `wrong-assumption` deviation type that Forge keeps logging

During feed-forward, both run:
1. `crucible:forge` feed-forward → process warnings
2. `crucible:cartographer` consult → structural awareness

During retrospective, Forge captures whether the Cartographer's information was accurate or stale.

### Skills That Should Call Cartographer

| Calling Skill | Mode | When | What to Pass |
|---------------|------|------|--------------|
| `crucible:build` | Consult | Phase 1 start (with forge feed-forward) | Task description |
| `crucible:build` | Load | Phase 3, each implementer/reviewer dispatch | Module names + file paths |
| `crucible:build` | Record | Phase 4, after completion | Files explored, modules touched |
| `crucible:executing-plans` | Consult | Step 1 (Load Plan) | Plan summary |
| `crucible:executing-plans` | Load | Each task dispatch | Module names + file paths |
| `crucible:executing-plans` | Record | Step 4 (Final Report) | New discoveries |
| `crucible:systematic-debugging` | Load | Phase 1 investigator dispatch | Module names |
| `crucible:systematic-debugging` | Record | After fix verified | What was learned |

**Cartographer is RECOMMENDED, not REQUIRED.** Like Forge, it is a knowledge accelerator, not a quality gate.

## Quick Reference

| Mode | Trigger | Model | Template | Orchestrator Cost |
|------|---------|-------|----------|-------------------|
| Record | After exploration | Sonnet | `recorder-prompt.md` | ~800 tokens (result only) |
| Consult | Task begins | None (direct read) | N/A | ~4K tokens (map.md) |
| Load | Subagent dispatch | None (direct read) | N/A | 0 (subagent context only) |

## Red Flags

**Never:**
- Load ALL module files into the orchestrator (context bloat)
- Let `map.md` exceed 200 lines or module files exceed 100 lines
- Overwrite existing module information without merging
- Record speculative information ("I think this might...") — only record observed facts
- Load `landmines.md` into implementers (biases toward fear, not action)
- Load `conventions.md` into reviewers (they should judge what IS, not what SHOULD be)

**Always:**
- Read existing file before updating (merge, don't replace)
- Flag contradictions to the user
- Record discoveries after significant exploration
- Check for module files before dispatching subagents
- Enforce line caps — compress or split if approaching limits

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "I'll remember this for the next task" | You won't. You're ephemeral. Write it down. |
| "This module is too simple to document" | Simple modules get modified carelessly. Document the boundary. |
| "The code is self-documenting" | Contracts, dependencies, and gotchas are NOT in the code. |
| "Map is stale, ignore it" | Stale maps with a flag are better than no map. Note what's wrong. |
| "Too many modules to map" | Map what you touch. Coverage grows naturally. |
| "Subagent doesn't need module context" | Wrong assumptions are the #1 deviation type. Context prevents them. |

## Common Mistakes

**Mapping everything at once**
- Problem: Agent tries to read the entire codebase and build a complete map in one session
- Fix: Map incrementally. Only record what you actually explored during real work. Coverage grows over sessions.

**Stale information**
- Problem: Module file says "uses REST API v2" but codebase migrated to v3
- Fix: When contradictions are observed, flag to user and update. Add "Last Updated" dates. Forge retrospectives will catch stale-map-related wrong-assumptions.

**Module files too granular**
- Problem: One file per class, 50 module files, maintenance nightmare
- Fix: Module = directory-level grouping. One file per logical module (5-15 total for most projects). Only split if a module file hits 100 lines.

**Loading module context for unrelated areas**
- Problem: Task touches `auth/`, subagent gets `funding.md` context
- Fix: Only load module files for modules the subagent will actually touch. Map the task to modules first.

## Prompt Templates

- `./recorder-prompt.md` — Post-exploration discovery recorder dispatch
