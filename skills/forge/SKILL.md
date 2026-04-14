---
name: forge
description: "Runs structured post-mortem retrospectives after completed tasks, producing scored entries in memory/forge/retrospectives/ and updating patterns.md with aggregated lessons learned. Before new tasks, performs feed-forward review of accumulated patterns and chronicle signals to surface targeted warnings. When 10+ retrospectives accumulate with recurring deviations, generates concrete skill mutation proposals for human review. Use when: a task finishes and you need to reflect on what went wrong or what worked, when starting a task and want to review past lessons, when asking 'what did I learn', or when proposing skill improvements from accumulated data."
---

# Forge

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Self-improving retrospective system. After tasks complete, runs structured retrospectives. Before tasks begin, consults accumulated lessons. Periodically proposes concrete skill edits based on evidence.

**Core principle:** The agent that never reviews its own performance never improves. The Forge closes the loop.

**Announce at start:** "I'm using the forge skill to [run a retrospective / consult past lessons / propose skill improvements]."

## When to Use

```dot
digraph forge_modes {
    "Task just completed?" [shape=diamond];
    "Starting new task?" [shape=diamond];
    "10+ retros + recurring pattern?" [shape=diamond];
    "Run Retrospective" [shape=box];
    "Run Feed-Forward" [shape=box];
    "Run Mutation Analysis" [shape=box];
    "Not applicable" [shape=box];

    "Task just completed?" -> "Run Retrospective" [label="yes"];
    "Task just completed?" -> "Starting new task?" [label="no"];
    "Starting new task?" -> "Run Feed-Forward" [label="yes"];
    "Starting new task?" -> "10+ retros + recurring pattern?" [label="no"];
    "10+ retros + recurring pattern?" -> "Run Mutation Analysis" [label="yes"];
    "10+ retros + recurring pattern?" -> "Not applicable" [label="no"];
}
```

**Three modes:**
- **Retrospective** — after any significant task (build, debug, plan execution, branch finish)
- **Feed-Forward** — before design, planning, or execution begins
- **Mutation Proposals** — when enough data accumulates (10+ retrospectives, 3+ of same deviation type)

**Significant task** = anything that used `crucible:build`, `crucible:debugging`, or `crucible:finish`. Simple questions and file reads do not qualify.

## Storage

All data lives in the project memory directory:

```
~/.claude/projects/<project-hash>/memory/forge/
  retrospectives/
    YYYY-MM-DD-HHMMSS-<slug>.md    # Individual entries (<40 lines each)
  patterns.md                       # Aggregated patterns (max 200 lines)
  mutation-proposals/
    YYYY-MM-DD-<topic>.md           # Skill mutation proposals
  skill-proposals/
    YYYY-MM-DD-<topic>.md           # Skill extraction proposals
  chronicle/
    signals.jsonl                   # Always-on execution signals (1 line per skill completion)
    summary.md                      # Bounded summary (~100 lines, regenerated on read)
```

**Context budget:** `patterns.md` MUST stay under 200 lines. `chronicle/summary.md` MUST stay under 100 lines. Both are loaded into context during feed-forward. Individual retrospective files are NOT loaded during feed-forward — only during mutation analysis.

**Chronicle is always-on** — no config toggle. Signals contain no prompt content or task descriptions, only operational metrics (skill name, duration, outcome, files touched, skill-specific counts). This is separate from trajectory capture, which remains opt-in.

**Skill-Worthy Patterns section format** (within `patterns.md`):

```markdown
## Skill-Worthy Patterns

- **[Pattern name]** (count: N, last seen: YYYY-MM-DD): [Description]
  - Status: none | proposed ([path]) | accepted | rejected
```

## Trajectory Capture (Opt-In)

Trajectory capture records structured data about real skill invocations for eval generation. It is OFF by default and requires explicit opt-in via `~/.claude/projects/<hash>/memory/trajectory-config.json`. If the file does not exist or `enabled` is false, skip all trajectory recording silently.

For full configuration, redaction rules, storage layout, and failure handling, see [`trajectory-capture.md`](./trajectory-capture.md).

---

## Mode 1: Post-Task Retrospective

### When to Trigger

After any skill that completes a significant task reports success. The calling skill (or orchestrator) invokes `crucible:forge` in retrospective mode.

### The Process

0. **Capture raw execution metrics** (if trajectory capture is enabled):
   Before dispatching the retrospective analyst, gather and hold in context:
   - Skill name that just completed
   - Start timestamp (from pipeline status "Started" field or session start)
   - End timestamp (current time)
   - Tool call count estimate (from execution summary or narration log)
   - Error recovery event count (how many times an error was encountered and retried)
   - User acceptance signal (did the user approve the output, request changes, or reject it?)
   - Phases reached (for build: design/plan/execute/review; for debugging: investigate/hypothesize/fix/verify; etc.)
   - Completion status (did the skill reach its natural end?)

   These raw metrics are NOT written to disk yet. They are held in context for
   step 8 (trajectory recording) after the retrospective completes, where they
   are merged with the retrospective's analytical output (deviation type, outcome,
   tags) to form the complete trajectory entry.

   If trajectory capture is disabled, skip this step.

1. Dispatch a **Retrospective Analyst** subagent (Sonnet) using `./retrospective-prompt.md`
2. Provide: task description, the plan (if any), actual execution summary, skills used, duration estimate
3. Subagent returns structured retrospective entry
4. Write entry to `~/.claude/projects/<project-hash>/memory/forge/retrospectives/YYYY-MM-DD-HHMMSS-<slug>.md`
5. Update `patterns.md` — read current file, merge new findings, rewrite
6. For debugging sessions, the retrospective also extracts diagnostic patterns using a dedicated extraction subagent (Opus). Dispatch using `./diagnostic-extraction-prompt.md`. Patterns are written to cartographer's landmines via `crucible:cartographer` (record mode) with `dead_ends` and `diagnostic_path` fields. Tag dead-end entries with `(source: debugging)`.
6b. For build sessions with QG fix journals: glob for `~/.claude/projects/<project-hash>/memory/quality-gate/fix-journal-*.md`. For each handoff file found:
    a. Read `landmines.md` and check for existing entries matching the same module + same failed approach (same file path AND same module AND 3+ non-stopword shared terms). If matching entries exist, skip extraction — handoff was already processed. Delete the handoff file.
    b. If no match: dispatch the diagnostic extraction subagent (Opus) using `./diagnostic-extraction-prompt.md` with the QG-specific addendum (see that file's "Source Context: Quality Gate Fix Journal" section). Tag dead-end entries with `(source: qg)`.
    c. Write extracted dead ends to cartographer's landmines via `crucible:cartographer` (record mode).
    d. Delete the handoff file after successful extraction.
    e. **Cap-pressure behavior:** If `landmines.md` is within 10 lines of its 100-line cap, write only Fatal-severity dead ends. At cap, skip and emit a chronicle signal: `{ "event": "dead_end_cap_skip", "module": "<module>", "source": "qg" }`.
7. For build sessions with a decision journal, the retrospective also extracts
   substantive design decisions. The retrospective analyst identifies decisions
   that are NOT operational routing (reviewer-model, gate-round, task-grouping,
   cleanup-removal types from the journal) but are substantive design choices
   (technology selection, API design, architecture, constraint trade-offs).
   These are passed to a cartographer recorder dispatch with the
   "Extract decisions for cartographer" directive, alongside the module
   mapping from the build session's task list and design doc.
8. **Trajectory recording** (if trajectory capture is enabled):
   Check config, construct the trajectory entry from execution data and retrospective output, run the redaction pass, and append to the appropriate JSONL file. See [`trajectory-capture.md`](./trajectory-capture.md) for the full entry schema, redaction rules, and file routing logic.
8.5. **Chronicle signal** (always-on — runs regardless of trajectory capture config):
   Construct a signal entry with skill name, outcome, duration, branch, files touched, and skill-specific metrics. Compute the efficiency sub-object from enriched manifest data if available. Append as a single JSON line to `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl`. Emit one signal per top-level skill invocation only (sub-skills do not emit their own signals). See [`chronicle-signals.md`](./chronicle-signals.md) for the full signal schema, efficiency computation, metrics bag by skill, and examples.

9. **Skill extraction check (all sessions):** Evaluate the just-produced
   retrospective entry against the following trigger heuristics. If ANY
   trigger fires, dispatch a Skill Extraction Analyst subagent (Sonnet)
   using `./extraction-analyst-prompt.md`.

   **Trigger heuristics (ANY fires = dispatch analyst):**
   - **Complexity**: Execution summary references 5+ distinct tool calls or
     subagent dispatches in a non-trivial sequence (sequential steps with
     dependencies, not parallel reads of unrelated files)
   - **Error recovery**: "What Went Wrong" describes errors that were overcome
     AND "What Worked" credits a specific approach for the recovery
   - **User correction**: Execution summary notes user redirection that led
     to a successful outcome different from the original approach
   - **Novel workflow**: "What Worked" describes a pattern not present in any
     existing skill's SKILL.md description frontmatter (check skill names
     and descriptions against the pattern)
   - **Recurrence**: The positive pattern in "What Worked" matches an existing
     entry in patterns.md "Skill-Worthy Patterns" with count >= 2, AND no
     proposal has been generated for it yet

   **Dispatch input:** retrospective entry, execution summary, existing skill
   names/descriptions, existing proposals in skill-proposals/ and
   mutation-proposals/.

   **Handle output:**
   - "No proposal warranted" -> Record pattern name in patterns.md
     Skill-Worthy Patterns section (increment count or add new entry)
   - NEW SKILL proposal -> Write to skill-proposals/YYYY-MM-DD-<topic>.md,
     update patterns.md entry with status: proposed
   - EXTEND EXISTING proposal -> Write to mutation-proposals/YYYY-MM-DD-<topic>.md
     with `source: extraction` tag, update patterns.md entry with status: proposed

   This step is RECOMMENDED, not REQUIRED. Failure does not break the
   retrospective. If the analyst cannot determine skill-worthiness, record
   the pattern and move on.

### Update Rules for patterns.md

1. Read the current `patterns.md` (create if first retrospective)
2. Increment counts based on new retrospective
3. Recalculate percentages and trends
4. Add new warnings only if a pattern appears **2+ times** (single occurrences stay in individual files only)
5. Prune warnings that have not occurred in the last 10 retrospectives (pattern may be resolved)
6. Keep total file **under 200 lines** — compress or remove stale entries
7. Write the updated file
8. Update the "Skill-Worthy Patterns" section:
   - If the retrospective's "What Worked" section describes a reusable pattern, add or increment it
   - Each entry: pattern name, occurrence count, last-seen date, proposal status (none|proposed|accepted|rejected)
   - Maximum 10 entries, 2 lines each
   - Prune patterns not seen in last 10 retrospectives (same rule as warnings)
   - Mark patterns as "resolved" (compress to single line) when their proposal has been accepted or rejected

### After Writing

If total retrospective count >= 10 AND any deviation type has 3+ occurrences, suggest to user:
> "Forge has accumulated enough data for skill improvement proposals. Would you like to run mutation analysis?"

If a skill extraction proposal was generated in step 9, notify the user:
> "Forge detected a skill-worthy workflow: [proposed skill name or extension target]. Proposal written to [path]. When you're ready, you can use skill-creator with this proposal as a starting point."

Do NOT prompt for immediate action. The notification is informational. The user
decides when (or whether) to act on it.

### Fallback Recording Without Retrospective

When a significant skill completes but no forge retrospective runs (user declines, session ending), skills SHOULD still write minimal trajectory entries and chronicle signals to avoid data loss. See [`trajectory-capture.md`](./trajectory-capture.md) and [`chronicle-signals.md`](./chronicle-signals.md) for fallback recording details.

---

## Mode 2: Pre-Task Feed-Forward

### When to Trigger

Before `crucible:design`, `crucible:planning`, or `crucible:build` begins its core work.

### The Process

1. Check if `~/.claude/projects/<project-hash>/memory/forge/patterns.md` exists
2. **Cold start (no file):** Report "No prior retrospective data for this project. Proceeding without feed-forward." Return immediately. No subagent needed.
3. **Data exists:** Read `patterns.md` (under 200 lines — safe for context)
3.5. **Chronicle context** (always-on):
    a. Check if `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl` exists
    b. If not found: skip (cold start — no chronicle data yet)
    c. If found: compare `signals.jsonl` mtime with `chronicle/summary.md` mtime. If `summary.md` doesn't exist or is stale, regenerate it (see [`chronicle-signals.md`](./chronicle-signals.md) for regeneration logic — computes hotspots, skill performance, trends, recent friction; hard cap 100 lines).
    d. Load `chronicle/summary.md` into context alongside `patterns.md`
    e. Pass both to the Feed-Forward Advisor in Step 4
3.7. **Dead-end context** (if cartographer data exists):
    a. Check if `~/.claude/projects/<project-hash>/memory/cartographer/landmines.md` exists
    b. If not found: skip (no dead-end data yet)
    c. If found: identify the upcoming task's target file paths from the task description. Resolve each to a cartographer module via `Path:` prefix matching (same logic as Cartographer Mode 3 Load step 7). Scan `landmines.md` for entries with file paths resolving to the same modules.
    d. If 0 matching entries: skip
    e. If 1+ matching entries: extract the matching entries (both `source: qg` and `source: debugging`). Pass to the Feed-Forward Advisor in Step 4 under the "Dead-End Context" section.
    **Note:** Forge scans `landmines.md` directly rather than routing through Cartographer Mode 3 Load to avoid coupling — feed-forward works even when no Cartographer consult runs in the current session.
4. Dispatch a **Feed-Forward Advisor** subagent (Sonnet) using `./feed-forward-prompt.md`
4b. **Trajectory context** (if trajectory capture is enabled):
    Also read `~/.claude/projects/<hash>/memory/trajectories/failed_trajectories.jsonl`
    and extract the 5 most recent failure entries for the upcoming skill type.
    Pass these to the Feed-Forward Advisor alongside patterns.md.
    The advisor can surface trajectory-specific warnings like:
    - "Last 3 build invocations failed at the execute phase with error recovery"
    - "Debugging tasks on this project have a 40% failure rate — consider more
      investigation before committing to a fix"
    If no trajectory data exists, skip this addition.
5. Provide: the patterns file content, chronicle summary (if available from Step 3.5), AND a brief description of the upcoming task
6. Subagent returns 3-5 targeted warnings/adjustments relevant to THIS task
7. Surface warnings to the calling skill's orchestrator as bias adjustments (not hard blockers)

### Cold Start Lifecycle

- **First task:** No feed-forward (no data). Retrospective runs after completion. This produces data.
- **Second task:** Feed-forward has 1 data point. Advisor notes "limited data" but still surfaces any relevant warning.
- **After 3+ tasks:** Chronicle hotspots start to form. Summary becomes useful.
- **After 5+ tasks:** Feed-forward becomes meaningfully useful.
- **After 10+ tasks:** Mutation proposals become available. Chronicle trends become meaningful.

---

## Mode 3: Skill Mutation Proposals

### When to Trigger

When `patterns.md` shows 10+ total retrospectives AND recurring patterns (3+ occurrences of same deviation type). Can also be invoked manually.

### The Process

1. Read `patterns.md` and ALL individual retrospective files in `retrospectives/`
2. Dispatch a **Mutation Analyst** subagent (Opus) using `./mutation-proposal-prompt.md`
3. Provide: the full patterns file, all retrospective entries, and a list of current skill names
4. Subagent analyzes patterns and proposes concrete skill edits
5. Write proposals to `~/.claude/projects/<project-hash>/memory/forge/mutation-proposals/YYYY-MM-DD-<topic>.md`
6. Surface proposals to the user — **NEVER auto-modify skills**

### The Iron Law of Mutations

```
NEVER AUTO-MODIFY SKILLS. PROPOSALS ONLY.
```

The Forge produces proposals for human review. It does not edit skill files. It does not dispatch subagents to edit skill files. It does not suggest "just making this small change." Every mutation requires explicit human approval.

---

## Integration

### Skills That Should Call Forge

| Calling Skill | Mode | When | What to Pass |
|---------------|------|------|--------------|
| `crucible:build` | Feed-Forward | Phase 1 start | Feature description |
| `crucible:build` | Retrospective | Phase 4, after red-team, before finishing | Full build summary |
| `crucible:debugging` | Retrospective | After fix verified | Bug description + hypothesis log |
| `crucible:debugging` | Retrospective (diagnostic extraction) | After fix verified | Session artifacts → cartographer landmines with `dead_ends` + `diagnostic_path` |
| `crucible:finish` | Retrospective | After Step 3, before Step 4 | Branch summary + review findings |
| `crucible:design` | Feed-Forward | Before first question | Topic description |
| `crucible:build` | Retrospective (decision extraction) | After fix verified | Decision journal + task list → cartographer decisions via recorder |
| Any skill | Trajectory Record | After retrospective step 7 | Execution data + retrospective output (opt-in only) |
| Any skill | Chronicle Signal | After retrospective step 8 | Execution metrics (always-on) |

**Forge is RECOMMENDED, not REQUIRED.** It is a learning accelerator, not a quality gate. Skipping it does not produce broken output — it misses an opportunity to learn.

**Skill extraction** is an internal step within Mode 1 (Retrospective). It does
not require any calling skill to pass additional data -- the retrospective entry
itself provides the input. The extraction analyst may read existing skill
descriptions from the skill directories to check for overlap.

## Quick Reference

| Mode | Trigger | Model | Template | Output |
|------|---------|-------|----------|--------|
| Retrospective | Task completes | Sonnet | `retrospective-prompt.md` | Entry file + patterns.md update |
| Feed-Forward | Task begins | Sonnet | `feed-forward-prompt.md` | 3-5 targeted warnings |
| Mutation | 10+ retros + manual | Opus | `mutation-proposal-prompt.md` | Proposal doc for human review |

## Red Flags

**Never:**
- Skip retrospective because "task was simple" — simple tasks reveal patterns too (2 min max)
- Let `patterns.md` exceed 200 lines — prune entries not seen in last 10 retros
- Auto-modify any skill file or auto-create skills — Iron Law: proposals only, humans decide
- Load individual retrospective files into feed-forward (context bloat)
- Run mutation analysis with fewer than 10 retrospectives — below that, patterns are noise
- Treat feed-forward warnings as hard blockers — they are bias adjustments, not constraints
- Propose skills for trivial or project-specific workflows (single-step, domain-specific infra)
- Store raw user prompts in trajectory files — only prompt hashes and redacted summaries
- Write a trajectory entry without completing the full redaction pass
- Include prompt content or task descriptions in chronicle signals — operational metrics only

**Always:**
- Run retrospective after significant tasks — "I'll do it later" means never
- Check for `patterns.md` before design/planning; handle cold start gracefully
- Write mutation/extraction proposals to disk for human review before notifying
- Check `trajectory-config.json` before any trajectory operation; never auto-enable
- Append a chronicle signal after every significant task retrospective (Step 8.5)
- Cross-reference `skill-proposals/` before generating new proposals to avoid duplicates
- If `>30%` of retrospectives trigger extraction proposals, tighten the heuristics

## Prompt Templates

- `./retrospective-prompt.md` — Post-task retrospective analyst dispatch
- `./feed-forward-prompt.md` — Pre-task feed-forward advisor dispatch
- `./mutation-proposal-prompt.md` — Skill mutation analyst dispatch
- `./diagnostic-extraction-prompt.md` — Debugging session diagnostic pattern extraction dispatch
- `./extraction-analyst-prompt.md` -- Skill-worthy workflow detection and proposal generation dispatch
