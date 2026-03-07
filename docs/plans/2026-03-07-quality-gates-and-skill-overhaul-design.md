# Quality Gates and Skill Overhaul — Design Document

**Goal:** Evolve crucible's skill system with rigorous iterative red-teaming at every artifact-producing stage, UI-aware debugging, implementation cleanup, skill health monitoring, session metrics, and cleaner naming.

## 1. Quality Gate Skill (New)

A shared skill (`quality-gate`) that provides iterative red-teaming as the core quality mechanism. Every artifact-producing skill calls it via a one-line callout at the end.

### How It Works

- Receives: artifact content, artifact type (design/plan/code/documentation/hypothesis), project context
- Always invoked by default; user can interrupt to skip
- Internally uses the existing red-team iterative loop: fresh Devil's Advocate each round, stagnation detection, escalation
- **Default 3-round cap.** If still finding Fatal issues after 3 rounds of red-teaming and revision, escalate to user. User can override with "keep going" but the default is capped. This prevents unbounded loops when severity categories shift between rounds.

### Invocation Convention

Quality gate is invoked by the **outermost orchestrator only** — not self-invoked by child skills. This avoids double-gating problems that arise because subagents have isolated contexts (a flag set by a parent orchestrator is invisible to a subagent).

**When used standalone** (user invokes `design` or `planning` directly):
- The skill itself is the outermost orchestrator
- It invokes quality gate at the end

**When used as a sub-skill of build:**
- Build is the outermost orchestrator and controls all quality gates
- Child skills (`design`, `planning`) document that they produce artifacts needing gating but do NOT self-invoke quality gate
- Build invokes quality gate at the appropriate pipeline stage

**Skills that produce gateable artifacts:**
- `design` — produces design docs
- `planning` — produces implementation plans
- `debugging` — produces hypotheses (Phase 3.5) and fixes (Phase 5)
- `mockup-builder` — produces mockups
- `mock-to-unity` — produces translation maps and implementations

Each skill's SKILL.md documents: "This skill produces [artifact type]. When used standalone, invoke quality gate after [trigger]. When used as a sub-skill, the parent orchestrator handles gating."

## 2. Debugging Enhancements

Three changes to the debugging skill (renamed from systematic-debugging to debugging):

### A. Hypothesis Red-Team (New Phase 3.5)

After the orchestrator forms a hypothesis in Phase 3, before dispatching the Phase 4 implementer, invoke the quality gate on the hypothesis. A lightweight red-team agent challenges:

- Does the hypothesis explain ALL symptoms, or just some?
- Could the root cause be upstream of what the hypothesis targets?
- If this hypothesis is correct, what other symptoms should we expect? Do we see them?
- Has this pattern been tried and failed before? (check hypothesis log)

If the hypothesis is torn apart, the orchestrator reforms it (or dispatches more investigation) without wasting a full TDD cycle.

### B. Domain Detection Framework

A generic framework where projects declare domain-specific skill hooks in their CLAUDE.md. The debugging skill checks for this configuration during Phase 0 and enriches investigator prompts accordingly.

**Schema (declared in project CLAUDE.md):**

```markdown
## Debugging Domains

| Signal | Domain | Skills | Context |
|--------|--------|--------|---------|
| file paths contain `/UI/`, `USS`, `VisualElement` | ui | mockup-builder, mock-to-unity, ui-verify | docs/mockups/, known USS bugs |
| error mentions `GridWorld`, `Tile`, `hex` | grid | - | grid system architecture |
```

**Signal types:** File path patterns (regex against paths in error/stack trace), error message patterns (regex against error text), user description keywords. Signals are evaluated in order; first match wins. If multiple domains match, the orchestrator loads context for all matching domains.

**Lookup process:** The debugging orchestrator reads the project's CLAUDE.md during Phase 0 (alongside cartographer). It parses the `## Debugging Domains` table if present. For each row, it checks whether any of the bug's known signals (file paths from stack traces, error message text, user description) match the signal pattern.

**When domain is detected, the orchestrator:**
- Auto-loads relevant skill knowledge (reads the referenced skills' SKILL.md files) into investigator prompts
- Adds a domain-specific investigator to Phase 1 (e.g., a UI investigator that runs `ui-verify` in code-audit mode)
- Gives Phase 4 implementer domain skill context so fixes don't introduce domain-specific bugs
- Loads files from the Context column (e.g., reads `docs/mockups/` for UI bugs)

**When no domain table exists in CLAUDE.md:** The debugging skill proceeds normally with no domain enrichment. This is the default — domain detection is opt-in.

**When a referenced skill doesn't exist:** Log a warning ("Domain 'ui' references skill 'mockup-builder' which is not installed — skipping domain enrichment") and proceed without it. Never fail on missing domain config.

### C. Strategic Compact Awareness

After failed fix cycles (looping back from Phase 4 to Phase 1), write the hypothesis log and investigation findings to disk before dispatching new investigation. This is when context pressure is actually high — multiple investigation rounds and a failed implementation have accumulated in context.

The hypothesis log format already exists — this makes it persistent rather than in-memory only. The trigger is deterministic (failed cycle → write to disk) rather than conditional on self-assessed context pressure, which the LLM cannot reliably measure.

## 3. De-Sloppify (Build Phase 3 Addition)

A cleanup agent step added to build Phase 3, firing after each task implementer completes and before the reviewer sees the code.

### How It Works

- Dispatch a fresh cleanup subagent (Opus — judgment calls about what's genuinely unnecessary require strong reasoning)
- Reviews all changes in the working tree from the implementer
- **Can remove test+code pairs together** (the whole point — unnecessary code often has unnecessary tests protecting it)
- Must justify each paired removal specifically in a removal log
- Runs the test suite after cleanup to confirm nothing breaks
- Commits the cleanup separately: `refactor: cleanup task N implementation`

### Removal Categories (Explicit Allowlist)

- Over-defensive error handling for impossible states
- Tests that verify language/framework behavior rather than business logic
- Redundant type checks the type system already enforces
- Commented-out code
- Debug logging

If the agent can't categorize a removal into one of these buckets, it flags it in the log for the reviewer to decide.

### Guardrails

1. **Test suite as safety net** — runs after every removal. Failures mean put it back.
2. **Narrow removal categories** — explicit allowlist, not general "clean up the code"
3. **Reviewer sees the diff** — Pass 1 code review sees both implementer and cleanup commits
4. **Removal log** — every removal logged with one-line justification and category

### Build Flow Position

```
Implementer builds + tests -> De-sloppify cleanup -> Pass 1: Code Review -> ...
```

## 4. Skill Stocktake (New)

A new skill that audits all crucible skills for overlap, staleness, broken references, and quality.

### Modes

- **Quick scan:** Only re-evaluates skills that changed since last run (~5 min)
- **Full stocktake:** Evaluates everything (~20 min)

### Evaluation

- Dispatches an Opus Explore agent with all skill contents and a quality checklist
- Results cached to `skills/stocktake/results.json`
- Each skill gets a verdict: Keep, Improve (with specific action), Retire (with replacement), Merge into X (with target)

### Evaluation Criteria

- Content overlap with other skills
- Scope fit — name, trigger, and content aligned
- Actionability — concrete steps vs vague advice
- Cross-references — do links to other skills still resolve?

### Trigger (Option B — Periodic Nudge)

- Forge feed-forward checks the stocktake results timestamp
- If last run was 30+ days ago (or never), forge surfaces: "Skill stocktake hasn't run in a while"
- User decides whether to run it

### Safety

- Never auto-deletes or auto-modifies skills
- Always presents findings and waits for user confirmation

## 5. Session Metrics

Lightweight metrics report that appears when autonomous work completes and the user is back in the driver's seat.

### Output Format

```
-- Pipeline Complete ----------------------------------------
  Subagents dispatched:  23 (14 Opus, 7 Sonnet, 2 Haiku)
  Active work time:      2h 47m
  Wall clock time:       11h 13m
  Quality gate rounds:   4 (design: 2, plan: 1, impl: 1)
-------------------------------------------------------------
```

### Implementation

- Not a separate skill — baked into build and debugging completion reports
- Orchestrator appends timestamped entries to `/tmp/crucible-metrics-<session-id>.log` on each dispatch/completion
- At completion, reads the log, merges overlapping parallel intervals for active time, computes totals
- Agent count broken down by model tier (Opus/Sonnet/Haiku) for rough cost sense

### Metrics Tracked

- Total subagents dispatched (by type and model tier)
- Active work time (merged parallel intervals, not naive sum)
- Wall clock time (first dispatch to final completion)
- Quality gate rounds (per gate)
- Cycle count (debugging only — hypothesis cycles)

## 6. Skill Renames

| Current | New |
|---------|-----|
| systematic-debugging | debugging |
| brainstorming | design |
| writing-plans | planning |
| requesting-code-review | code-review |
| receiving-code-review | review-feedback |
| finishing-a-development-branch | finish |
| dispatching-parallel-agents | parallel |
| verification-before-completion | verify |
| using-git-worktrees | worktree |
| using-crucible | getting-started |
| writing-skills | skill-authoring |

### Per-Skill Rename Steps

- Rename the directory
- Update the `name:` field in SKILL.md frontmatter
- Update all cross-references in other skills (`crucible:systematic-debugging` → `crucible:debugging`)
- Update README.md skill table

### Migration Plan

Renames touch cross-references across many files. Order of operations:

1. **Audit:** Grep every old name across all skill files to produce a complete reference map
2. **Rename directories:** All 11 at once (atomic — no intermediate state with mixed names)
3. **Update all cross-references:** Every `crucible:old-name` → `crucible:new-name` across all SKILL.md files, prompt templates, and README
4. **Update frontmatter:** `name:` field in each renamed skill's SKILL.md
5. **Verify:** Grep for any remaining old names — should be zero hits
6. **No aliases:** Old names are not preserved. This is a clean break. The README documents the rename table for users upgrading.

### Unchanged Skills

build, red-team, forge, cartographer, innovate, mock-to-unity, mockup-builder, ui-verify, test-driven-development

## 7. Prompt Deduplication (Composition, Not Merging)

Two agent prompts share common structure across skills but have context-specific tuning:

- **Code reviewer** — build's reviewer and standalone code-review share: review checklist, issue classification, report format. They differ on: pipeline context (build reviewer knows about task numbering and plan references).
- **Implementer** — build's implementer and debugging's implementer share: TDD discipline, self-review checklist, report format. They differ on: build implementer references plan tasks; debugging implementer references hypotheses.

**Approach:** Extract shared structure (self-review checklist, report format, TDD discipline) into a reusable snippet file. Each prompt includes the snippet and adds its own context-specific instructions. This is composition, not deduplication — both prompts stay separate files with their own tuning, but the shared parts have a single source of truth.

**Shared snippets:**
- `shared/implementer-common.md` — TDD discipline, self-review checklist, report format
- `shared/reviewer-common.md` — review checklist, issue classification, report format

## 8. Orchestrator Status Narration

Add a hard communication requirement to build and debugging:

**"Between every agent dispatch and every agent completion, output a status update to the user. This is NOT optional — the user cannot see agent activity without your narration. Include: current phase, what just completed, what's being dispatched next, and the task checklist with current status. If you just compacted, re-read the task list and output current status before continuing."**

## 9. README Update

- Reflect all skill renames in the skill table
- Update descriptions to match new capabilities (quality gate, de-sloppify, session metrics)
- Add a "Setup" section with recommended prerequisites:
  - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — required for build's team-based execution (TeamCreate, team_name dispatching). Skills should degrade gracefully without it, but full pipeline orchestration depends on agent teams.
  - `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` — performance recommendation for long-running pipelines
- Clean up superpowers origin references — crucible stands on its own now
- Update the "How It Works" pipeline description to include quality gates and de-sloppify

## 10. Diagnostic Pattern Capture (Cartographer Landmines Extension)

Extend cartographer's existing `landmines.md` format with two optional fields to capture diagnostic intelligence from debugging sessions.

### New Fields

- **`dead_ends`** — Hypotheses that were tried and rejected, with the specific evidence that ruled them out. Framed as "if you go here, check for X condition" rather than "don't go here."
- **`diagnostic_path`** — The diagnostic steps that actually revealed the root cause (not a retroactively idealized "minimal" sequence).

### How It Works

**Writing (post-debugging):**
- Forge's post-debugging retrospective extracts diagnostic patterns using a dedicated extraction subagent (not lightweight — proper quality gate on extraction quality)
- Patterns are written to the relevant module's `landmines.md` in cartographer's existing format
- Staleness tracked via existing cartographer metadata (file paths, timestamps)

**Reading (during debugging):**
- Debugging Phase 0 loads cartographer context as it already does — this includes landmines with the new fields
- **Consumer: Phase 3 (hypothesis formation).** The orchestrator checks landmines for known dead ends BEFORE forming a hypothesis. If a landmine's `dead_ends` field matches a hypothesis the orchestrator is considering, it either skips that hypothesis or adjusts it based on the discriminating evidence.
- **Consumer: Synthesis agent.** After Phase 1, the synthesis agent receives landmines data as additional context to cross-reference against investigator findings. This avoids anchoring bias (investigators work fresh; synthesis cross-references).
- Phase 4 implementer receives relevant landmines so fixes don't repeat known patterns

### Why Not a Separate System

- Cartographer landmines already capture ~70% of what fingerprints would (symptoms, root cause, fix)
- One store, one retrieval surface — no split-recall problem
- No new file format, directory, or retrieval mechanism
- The debugging skill already loads cartographer context in Phase 0

## 11. Agent Teams Graceful Degradation

If build detects agent teams aren't available (TeamCreate fails), it should:
- Output a clear one-time warning recommending `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Fall back to sequential subagent dispatch via regular Agent tool
- Everything still works, just without parallel teammate coordination

## Acceptance Criteria

- [ ] Quality gate skill exists and is invoked by design, planning, debugging, mockup-builder, mock-to-unity
- [ ] Debugging has Phase 3.5 hypothesis red-team and domain detection framework
- [ ] Build Phase 3 includes de-sloppify step with removal log and all guardrails
- [ ] Skill stocktake skill exists with quick/full modes and forge nudge integration
- [ ] Build and debugging report session metrics on completion
- [ ] All 11 skills renamed with all cross-references updated
- [ ] Code reviewer and implementer prompts deduplicated
- [ ] Build and debugging have mandatory status narration requirement
- [ ] README reflects all changes with setup/prerequisites section
- [ ] All internal `crucible:` references use new names
- [ ] Cartographer landmines extended with dead_ends and diagnostic_path fields
- [ ] Forge retrospective includes diagnostic pattern extraction for debugging sessions
- [ ] Build gracefully degrades when agent teams are unavailable
