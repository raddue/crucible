# Quality Gates and Skill Overhaul — Design Document

**Goal:** Evolve crucible's skill system with rigorous iterative red-teaming at every artifact-producing stage, UI-aware debugging, implementation cleanup, skill health monitoring, session metrics, and cleaner naming.

## 1. Quality Gate Skill (New)

A shared skill (`quality-gate`) that provides iterative red-teaming as the core quality mechanism. Every artifact-producing skill calls it via a one-line callout at the end.

### How It Works

- Receives: artifact content, artifact type (design/plan/code/documentation/hypothesis), project context
- Always invoked by default; user can interrupt to skip
- When called by a parent skill that already orchestrates gating (e.g., build), the parent sets a flag and the gate skips (avoiding double red-teaming)
- Internally uses the existing red-team iterative loop: fresh Devil's Advocate each round, stagnation detection, escalation
- No round cap — loops as long as each round finds strictly fewer Fatal+Significant issues

### Skills That Call It

- `design` (currently brainstorming) — after saving the design doc
- `planning` (currently writing-plans) — after saving the plan
- `debugging` (currently systematic-debugging) — Phase 3.5 (hypothesis) and Phase 5 (fix)
- `mockup-builder` — after creating the mockup
- `mock-to-unity` — after the translation map, and after final implementation
- Any future artifact-producing skill

### Parent Skip Convention

When a parent skill (build, debugging) already orchestrates its own red-team passes, it sets a context flag. The quality gate checks for this flag and skips if present. This prevents double red-teaming while ensuring standalone skill invocations still get gated.

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

When domain is detected, the orchestrator:
- Auto-loads relevant skill knowledge into investigator prompts
- Adds domain-specific investigators to Phase 1
- Gives Phase 4 implementer domain skill context so fixes don't introduce domain-specific bugs

### C. Strategic Compact Awareness

Between phases, if context pressure is high: write the hypothesis log and investigation findings to disk, then compact before proceeding. The hypothesis log format already exists — this makes it persistent rather than in-memory only.

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
- Update all cross-references in other skills (`crucible:systematic-debugging` -> `crucible:debugging`)
- Update README.md skill table

### Unchanged Skills

build, red-team, forge, cartographer, innovate, mock-to-unity, mockup-builder, ui-verify, test-driven-development

## 7. Prompt Deduplication

Two agent prompts are duplicated across skills:

- **Code reviewer** — used by `code-review` (canonical) and `build` (copy). Canonicalize in `code-review/code-reviewer.md`, have build reference it.
- **Implementer** — used by `build` (canonical) and `debugging` (copy). Canonicalize in `build/build-implementer-prompt.md`, have debugging reference it.

## 8. Orchestrator Status Narration

Add a hard communication requirement to build and debugging:

**"Between every agent dispatch and every agent completion, output a status update to the user. This is NOT optional — the user cannot see agent activity without your narration. Include: current phase, what just completed, what's being dispatched next, and the task checklist with current status. If you just compacted, re-read the task list and output current status before continuing."**

## 9. README Update

- Reflect all skill renames in the skill table
- Update descriptions to match new capabilities (quality gate, de-sloppify, session metrics)
- Add a "Performance Tips" section with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` recommendation
- Clean up superpowers origin references — crucible stands on its own now
- Update the "How It Works" pipeline description to include quality gates and de-sloppify

## Acceptance Criteria

- [ ] Quality gate skill exists and is invoked by design, planning, debugging, mockup-builder, mock-to-unity
- [ ] Debugging has Phase 3.5 hypothesis red-team and domain detection framework
- [ ] Build Phase 3 includes de-sloppify step with removal log and all guardrails
- [ ] Skill stocktake skill exists with quick/full modes and forge nudge integration
- [ ] Build and debugging report session metrics on completion
- [ ] All 11 skills renamed with all cross-references updated
- [ ] Code reviewer and implementer prompts deduplicated
- [ ] Build and debugging have mandatory status narration requirement
- [ ] README reflects all changes with performance tips section
- [ ] All internal `crucible:` references use new names
