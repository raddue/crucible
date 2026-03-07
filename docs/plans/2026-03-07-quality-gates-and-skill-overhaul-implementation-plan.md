# Quality Gates and Skill Overhaul — Implementation Plan

**Goal:** Evolve crucible's skill system with quality gates, debugging enhancements, implementation cleanup, skill health monitoring, session metrics, cleaner naming, prompt composition, orchestrator narration, diagnostic pattern capture, and graceful degradation.

**Architecture:** Markdown-only changes across ~50 files. No application code. All changes are to skill definitions (SKILL.md), prompt templates, shared snippets, and the README.

**Design doc:** `docs/plans/2026-03-07-quality-gates-and-skill-overhaul-design.md`

---

## Dependency Graph

```
Task 1 (renames) ─────────────────────────────────────┐
Task 2 (shared snippets) ────────────────────────────┐ │
Task 3 (quality gate) ── depends on 1 ───────────────┤ │
Task 4 (prompt dedup: implementer) ── depends on 1,2 │ │
Task 5 (prompt dedup: reviewer) ── depends on 1,2  ──┤ │
Task 6 (design + planning gate) ── depends on 1,3  ──┤ │
Task 7 (debugging enhancements) ── depends on 1,3  ──┤ │
Task 8 (de-sloppify) ── depends on 1  ───────────────┤ │
Task 9 (session metrics) ── depends on 1,7,8  ───────┤ │
Task 10 (orchestrator narration) ── depends on 1  ────┤ │
Task 11 (skill stocktake) ── depends on 1  ──────────┤ │
Task 12 (diagnostic pattern capture) ── depends on 1 ─┤ │
Task 13 (agent teams degradation) ── depends on 1  ──┤ │
Task 14 (mockup/mock-to-unity gate) ── depends on 1,3│ │
Task 15 (README update) ── depends on ALL above  ─────┘ │
                                                         │
```

---

### Task 1: Rename All 11 Skills (Atomic)

**Files:**
- Rename: `skills/systematic-debugging/` -> `skills/debugging/`
- Rename: `skills/brainstorming/` -> `skills/design/`
- Rename: `skills/writing-plans/` -> `skills/planning/`
- Rename: `skills/requesting-code-review/` -> `skills/code-review/`
- Rename: `skills/receiving-code-review/` -> `skills/review-feedback/`
- Rename: `skills/finishing-a-development-branch/` -> `skills/finish/`
- Rename: `skills/dispatching-parallel-agents/` -> `skills/parallel/`
- Rename: `skills/verification-before-completion/` -> `skills/verify/`
- Rename: `skills/using-git-worktrees/` -> `skills/worktree/`
- Rename: `skills/using-crucible/` -> `skills/getting-started/`
- Rename: `skills/writing-skills/` -> `skills/skill-authoring/`
- Modify: All 11 renamed SKILL.md files (update `name:` frontmatter field)
- Modify: `skills/build/SKILL.md` (update all `crucible:` references)
- Modify: `skills/build/plan-writer-prompt.md` (update `crucible:writing-plans` reference)
- Modify: `skills/build/build-implementer-prompt.md` (no old-name references — clean)
- Modify: `skills/debugging/SKILL.md` (update all `crucible:` references, post-rename)
- Modify: `skills/forge-skill/SKILL.md` (update all `crucible:` references)
- Modify: `skills/cartographer-skill/SKILL.md` (update all `crucible:` references)
- Modify: `skills/red-team/SKILL.md` (update `crucible:` references)
- Modify: `skills/design/SKILL.md` (update `crucible:` references, post-rename)
- Modify: `skills/finish/SKILL.md` (update `crucible:` references, post-rename)
- Modify: `skills/worktree/SKILL.md` (update references, post-rename)
- Modify: `skills/skill-authoring/SKILL.md` (update `crucible:systematic-debugging` reference, post-rename)
- Modify: `skills/innovate/SKILL.md` (no old-name references — clean)
- Modify: `README.md` (update skill table names and all references)

**Dependencies:** None

**Steps:**

1. Audit: grep all old names across the entire repo to produce a complete reference map. The old->new mapping is:
   - `systematic-debugging` -> `debugging`
   - `brainstorming` -> `design`
   - `writing-plans` -> `planning`
   - `requesting-code-review` -> `code-review`
   - `receiving-code-review` -> `review-feedback`
   - `finishing-a-development-branch` -> `finish`
   - `dispatching-parallel-agents` -> `parallel`
   - `verification-before-completion` -> `verify`
   - `using-git-worktrees` -> `worktree`
   - `using-crucible` -> `getting-started`
   - `writing-skills` -> `skill-authoring`

2. Rename all 11 directories using `git mv`:
   ```
   git mv skills/systematic-debugging skills/debugging
   git mv skills/brainstorming skills/design
   git mv skills/writing-plans skills/planning
   git mv skills/requesting-code-review skills/code-review
   git mv skills/receiving-code-review skills/review-feedback
   git mv skills/finishing-a-development-branch skills/finish
   git mv skills/dispatching-parallel-agents skills/parallel
   git mv skills/verification-before-completion skills/verify
   git mv skills/using-git-worktrees skills/worktree
   git mv skills/using-crucible skills/getting-started
   git mv skills/writing-skills skills/skill-authoring
   ```

3. Update `name:` frontmatter in each renamed skill's SKILL.md to match the new directory name (e.g., `name: systematic-debugging` -> `name: debugging`).

4. Update all cross-references across ALL skill files. Every `crucible:old-name` becomes `crucible:new-name`. The complete reference map from the audit (see grep results):
   - `skills/build/SKILL.md`: `crucible:brainstorming` -> `crucible:design`, `crucible:writing-plans` -> `crucible:planning`, `crucible:requesting-code-review` -> `crucible:code-review`, `crucible:finishing-a-development-branch` -> `crucible:finish`
   - `skills/build/plan-writer-prompt.md`: `crucible:writing-plans` -> `crucible:planning`
   - `skills/debugging/SKILL.md` (post-rename): `crucible:requesting-code-review` -> `crucible:code-review`, `crucible:verification-before-completion` -> `crucible:verify`, `crucible:dispatching-parallel-agents` -> `crucible:parallel`
   - `skills/forge-skill/SKILL.md`: `crucible:systematic-debugging` -> `crucible:debugging`, `crucible:finishing-a-development-branch` -> `crucible:finish`, `crucible:brainstorming` -> `crucible:design`, `crucible:writing-plans` -> `crucible:planning`
   - `skills/cartographer-skill/SKILL.md`: `crucible:systematic-debugging` -> `crucible:debugging`, `crucible:brainstorming` -> `crucible:design`, `crucible:writing-plans` -> `crucible:planning`
   - `skills/red-team/SKILL.md`: `crucible:requesting-code-review` -> `crucible:code-review`, `crucible:finishing-a-development-branch` -> `crucible:finish`
   - `skills/design/SKILL.md` (post-rename): `crucible:using-git-worktrees` -> `crucible:worktree`, `crucible:writing-plans` -> `crucible:planning`
   - `skills/finish/SKILL.md` (post-rename): `crucible:requesting-code-review` -> `crucible:code-review`
   - `skills/worktree/SKILL.md` (post-rename): Update integration references (`brainstorming` -> `design`, `finishing-a-development-branch` -> `finish`)
   - `skills/skill-authoring/SKILL.md` (post-rename): `crucible:systematic-debugging` -> `crucible:debugging`
   - `README.md`: Update all skill names in the table and body text

5. Also update any bare name references (not prefixed with `crucible:`) in integration sections, e.g., `**brainstorming** (Phase 4)` -> `**design** (Phase 4)` in worktree/SKILL.md, and `requesting-code-review/code-reviewer.md` path references in finish/SKILL.md -> `code-review/code-reviewer.md`.

6. Verify: grep for any remaining old names. Should be zero hits outside of `docs/plans/` (historical plans are not updated).

**Commit:** `refactor: rename 11 skills and update all cross-references`

---

### Task 2: Create Shared Prompt Snippets

**Files:**
- Create: `skills/shared/implementer-common.md`
- Create: `skills/shared/reviewer-common.md`

**Dependencies:** None (can run in parallel with Task 1, but referenced content uses new names starting in Task 4)

**Steps:**

1. Create `skills/shared/` directory.

2. Create `skills/shared/implementer-common.md` by extracting the shared structure from `skills/build/build-implementer-prompt.md` and `skills/debugging/implementer-prompt.md`:
   - TDD discipline block (the RED-GREEN-COMMIT-REFACTOR cycle steps)
   - Self-review checklist (Completeness, Quality, Discipline, Testing sections — these are nearly identical)
   - Context self-monitoring block (50%+ utilization warning)
   - Report format: TDD Evidence Log format and example entries
   - Mark each section with clear headers so consuming prompts can reference them

3. Create `skills/shared/reviewer-common.md` by extracting shared structure from `skills/build/build-reviewer-prompt.md` and `skills/code-review/code-reviewer.md`:
   - Review checklist categories (Architecture, Correctness, Quality, Testing)
   - Issue classification scheme (Critical/Important/Minor for code-review, Clean/Issues/Architectural for build-reviewer — normalize to one scheme)
   - Report format structure (Verdict, Issues with file:line, Recommendations, Assessment)
   - "Do Not Trust" verification principle

4. Each snippet file should have a header comment explaining it is a shared component and which prompts include it.

**Commit:** `feat: create shared prompt snippets for implementer and reviewer`

---

### Task 3: Create Quality Gate Skill

**Files:**
- Create: `skills/quality-gate/SKILL.md`

**Dependencies:** Task 1 (uses new skill names in cross-references)

**Steps:**

1. Create `skills/quality-gate/` directory.

2. Write `skills/quality-gate/SKILL.md` with:
   - Frontmatter: `name: quality-gate`, description triggers on artifact review gating
   - Overview: Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills
   - How It Works:
     - Receives artifact content, artifact type (design/plan/code/documentation/hypothesis), project context
     - Always invoked by default; user can interrupt to skip
     - Uses existing `crucible:red-team` iterative loop internally
     - Default 3-round cap: if still finding Fatal issues after 3 rounds, escalate to user
   - Invocation Convention:
     - Invoked by the outermost orchestrator only — not self-invoked by child skills
     - Standalone: skill itself is outermost, invokes quality gate at end
     - As sub-skill of build: build controls gating, child skills document but do not self-invoke
   - Skills that produce gateable artifacts (with artifact type and trigger):
     - `crucible:design` — design docs — after design is saved
     - `crucible:planning` — implementation plans — after plan passes review
     - `crucible:debugging` — hypotheses (Phase 3.5) and fixes (Phase 5)
     - `crucible:mockup-builder` — mockups — after mockup is created
     - `crucible:mock-to-unity` — translation maps and implementations
   - Integration section listing calling skills
   - Red flags and rationalization prevention

**Commit:** `feat: create quality-gate skill`

---

### Task 4: Deduplicate Implementer Prompts (Composition)

**Files:**
- Modify: `skills/build/build-implementer-prompt.md`
- Modify: `skills/debugging/implementer-prompt.md`

**Dependencies:** Task 1, Task 2

**Steps:**

1. Edit `skills/build/build-implementer-prompt.md`:
   - Replace the inline TDD discipline section with a reference: `[Include shared/implementer-common.md: TDD Discipline]`
   - Replace the inline self-review checklist with: `[Include shared/implementer-common.md: Self-Review Checklist]`
   - Replace the inline context self-monitoring with: `[Include shared/implementer-common.md: Context Self-Monitoring]`
   - Replace the inline TDD Evidence Log format with: `[Include shared/implementer-common.md: Report Format]`
   - Keep build-specific sections intact: team communication, task description template, build-specific "Your Job" framing

2. Edit `skills/debugging/implementer-prompt.md`:
   - Same substitutions for shared sections
   - Keep debugging-specific sections intact: hypothesis template, "The Iron Law" (no fix without failing test), hypothesis-specific self-review items (scope, unexpected findings), debugging-specific report format fields (test result before/after fix, regressions, files changed)

3. Add a note in each prompt template's header comment: "This prompt uses shared snippets from `skills/shared/implementer-common.md`. When dispatching, paste the shared snippet content inline — subagents cannot read skill files."

**Commit:** `refactor: deduplicate implementer prompts via shared snippets`

---

### Task 5: Deduplicate Reviewer Prompts (Composition)

**Files:**
- Modify: `skills/build/build-reviewer-prompt.md`
- Modify: `skills/code-review/code-reviewer.md`

**Dependencies:** Task 1, Task 2

**Steps:**

1. Edit `skills/build/build-reviewer-prompt.md`:
   - Replace inline review checklist with: `[Include shared/reviewer-common.md: Review Checklist]`
   - Keep build-specific sections: two-pass structure (Pass 1 Code + Pass 2 Test), task spec template, implementer report template, TDD process evidence checking

2. Edit `skills/code-review/code-reviewer.md`:
   - Replace inline review checklist with: `[Include shared/reviewer-common.md: Review Checklist]`
   - Keep code-review-specific sections: git range template, production readiness checks, example output

3. Add header comments noting shared snippet usage and inline-paste requirement for subagents.

**Commit:** `refactor: deduplicate reviewer prompts via shared snippets`

---

### Task 6: Add Quality Gate to Design and Planning Skills

**Files:**
- Modify: `skills/design/SKILL.md`
- Modify: `skills/planning/SKILL.md`

**Dependencies:** Task 1, Task 3

**Steps:**

1. Edit `skills/design/SKILL.md`:
   - Add quality gate documentation after "After the Design" section:
     - "This skill produces **design docs**. When used standalone, invoke `crucible:quality-gate` after the design document is saved and committed. When used as a sub-skill of build, the parent orchestrator handles gating."
   - Add `crucible:quality-gate` to integration/related skills

2. Edit `skills/planning/SKILL.md`:
   - Add quality gate documentation after the plan is saved:
     - "This skill produces **implementation plans**. When used standalone, invoke `crucible:quality-gate` after the plan is saved. When used as a sub-skill of build, the parent orchestrator handles gating."
   - Add `crucible:quality-gate` to integration/related skills

**Commit:** `feat: add quality gate invocation to design and planning skills`

---

### Task 7: Debugging Enhancements (Phase 3.5, Domain Detection, Strategic Compact)

**Files:**
- Modify: `skills/debugging/SKILL.md`
- Modify: `skills/debugging/investigator-prompt.md`

**Dependencies:** Task 1, Task 3

**Steps:**

1. Edit `skills/debugging/SKILL.md` — add Phase 3.5 (Hypothesis Red-Team):
   - Insert new section between Phase 3 and Phase 4 in the workflow
   - Phase 3.5: After hypothesis formation, before Phase 4 dispatch, invoke `crucible:quality-gate` on the hypothesis with artifact type "hypothesis"
   - Quality gate challenges:
     - Does the hypothesis explain ALL symptoms, or just some?
     - Could the root cause be upstream of what the hypothesis targets?
     - If this hypothesis is correct, what other symptoms should we expect? Do we see them?
     - Has this pattern been tried and failed before? (check hypothesis log)
   - If hypothesis is torn apart: orchestrator reforms or dispatches more investigation
   - Update the workflow overview diagram to include Phase 3.5
   - Update the Quick Reference table to include Phase 3.5

2. Edit `skills/debugging/SKILL.md` — add Domain Detection Framework:
   - Add new section in Phase 0 (after cartographer context loading):
     - Read the project's CLAUDE.md for a `## Debugging Domains` table
     - Schema: `| Signal | Domain | Skills | Context |`
     - Signal types: file path patterns, error message patterns, user description keywords
     - When domain detected: auto-load referenced skills' SKILL.md, add domain investigator to Phase 1, give Phase 4 implementer domain context, load Context column files
     - When no table exists: proceed normally (opt-in)
     - When referenced skill missing: log warning, proceed without
   - Keep the section concise (design doc has full spec, skill just needs the operational instructions)

3. Edit `skills/debugging/SKILL.md` — add Strategic Compact Awareness:
   - In the loop-back section (after "Fix does not resolve the issue"), add:
     - "Before dispatching new investigation: write the hypothesis log and investigation findings to a persistent file on disk (`/tmp/crucible-debug-<session-id>-hypothesis-log.md`). This preserves context across compaction events that occur after multiple investigation rounds and a failed implementation."
   - This is a single paragraph addition to the existing loop-back section

4. Edit `skills/debugging/SKILL.md` — add quality gate documentation:
   - "This skill produces **hypotheses** (Phase 3.5) and **fixes** (Phase 5). When used standalone, quality gate is invoked at Phase 3.5 and Phase 5. When used as a sub-skill, the parent orchestrator may handle gating."

5. Edit `skills/debugging/investigator-prompt.md`:
   - Add a "Domain Context" section placeholder in the prompt template (after Codebase Context):
     ```
     ## Domain Context (if detected)

     [If the debugging orchestrator detected a domain match in Phase 0,
     paste domain-specific skill knowledge and context files here.
     If no domain was detected, omit this section.]
     ```

**Commit:** `feat: add Phase 3.5 hypothesis red-team, domain detection, strategic compact to debugging`

---

### Task 8: De-Sloppify (Build Phase 3 Addition)

**Files:**
- Modify: `skills/build/SKILL.md`
- Create: `skills/build/cleanup-prompt.md`

**Dependencies:** Task 1

**Steps:**

1. Edit `skills/build/SKILL.md` — add de-sloppify step to Phase 3:
   - In Step 3 (Execute Tasks), after "Implementer reports completion" and before "spawn Reviewer teammate", insert:
     - **De-Sloppify Cleanup:** Dispatch a fresh cleanup subagent (Opus) using `./cleanup-prompt.md`
     - Reviews all changes in the working tree from the implementer
     - Can remove test+code pairs together (must justify each in removal log)
     - Runs test suite after cleanup to confirm nothing breaks
     - Commits cleanup separately: `refactor: cleanup task N implementation`
   - Update the review flow diagram:
     ```
     Implementer builds + tests -> De-sloppify cleanup -> Pass 1: Code Review -> ...
     ```
   - Add `./cleanup-prompt.md` to the Prompt Templates list

2. Create `skills/build/cleanup-prompt.md`:
   - Prompt template for dispatching the cleanup subagent
   - Framing: "You are a cleanup agent. Review the implementer's changes and remove unnecessary code."
   - Explicit removal categories (allowlist):
     - Over-defensive error handling for impossible states
     - Tests that verify language/framework behavior rather than business logic
     - Redundant type checks the type system already enforces
     - Commented-out code
     - Debug logging
   - Paired removal rule: can remove test+code pairs together, must justify each in removal log with category
   - If removal doesn't fit a category, flag for reviewer
   - Must run test suite after every removal
   - Report format: removal log with one-line justification and category per removal

**Commit:** `feat: add de-sloppify cleanup step to build Phase 3`

---

### Task 9: Session Metrics (Build and Debugging Completion Reports)

**Files:**
- Modify: `skills/build/SKILL.md`
- Modify: `skills/debugging/SKILL.md`

**Dependencies:** Task 1, Task 7, Task 8

**Steps:**

1. Edit `skills/build/SKILL.md` — add session metrics to Phase 4 (Completion):
   - Add a metrics tracking requirement:
     - Orchestrator appends timestamped entries to `/tmp/crucible-metrics-<session-id>.log` on each subagent dispatch and completion
     - At completion (before reporting to user), read the log and compute:
       - Total subagents dispatched (by type: implementer, reviewer, plan writer, etc. and by model tier: Opus/Sonnet/Haiku)
       - Active work time (merged parallel intervals)
       - Wall clock time (first dispatch to final completion)
       - Quality gate rounds (per gate: design, plan, implementation)
   - Add the output format block from the design doc
   - Place this after "Compile summary" and before "Report to user"

2. Edit `skills/debugging/SKILL.md` — add session metrics to completion:
   - Same metrics tracking requirement, placed after Phase 5 (before the "done" conclusion)
   - Additional metric: cycle count (hypothesis cycles)
   - Same output format

**Commit:** `feat: add session metrics to build and debugging completion reports`

---

### Task 10: Orchestrator Status Narration (Build and Debugging)

**Files:**
- Modify: `skills/build/SKILL.md`
- Modify: `skills/debugging/SKILL.md`

**Dependencies:** Task 1

**Steps:**

1. Edit `skills/build/SKILL.md`:
   - Add a new top-level section after "Overview" called "## Communication Requirement (Non-Negotiable)":
     - "Between every agent dispatch and every agent completion, output a status update to the user. This is NOT optional — the user cannot see agent activity without your narration."
     - Include: current phase, what just completed, what's being dispatched next, and the task checklist with current status
     - "If you just compacted, re-read the task list and output current status before continuing."
   - Add to Red Flags: "Silently dispatching agents without status updates"

2. Edit `skills/debugging/SKILL.md`:
   - Add the same communication requirement section after "Overview"
   - Adapted for debugging phases: current phase, hypothesis being tested, what investigation/implementation agent just reported, what's being dispatched next
   - Add to Red Flags: "Dispatching agents without narrating what you're doing and why"

**Commit:** `feat: add mandatory orchestrator status narration to build and debugging`

---

### Task 11: Skill Stocktake (New Skill)

**Files:**
- Create: `skills/stocktake/SKILL.md`

**Dependencies:** Task 1

**Steps:**

1. Create `skills/stocktake/` directory.

2. Write `skills/stocktake/SKILL.md` with:
   - Frontmatter: `name: stocktake`, description triggers on skill audit/health check
   - Overview: Audits all crucible skills for overlap, staleness, broken references, and quality
   - Modes:
     - **Quick scan:** Re-evaluates skills changed since last run (~5 min)
     - **Full stocktake:** Evaluates everything (~20 min)
   - Evaluation process:
     - Dispatches an Opus Explore agent with all skill contents and a quality checklist
     - Results cached to `skills/stocktake/results.json`
     - Each skill gets a verdict: Keep, Improve (with action), Retire (with replacement), Merge into X (with target)
   - Evaluation criteria:
     - Content overlap with other skills
     - Scope fit (name, trigger, content aligned)
     - Actionability (concrete steps vs vague advice)
     - Cross-references (do links resolve?)
   - Trigger: Forge feed-forward checks results timestamp; if 30+ days or never, surfaces nudge
   - Safety: Never auto-deletes or auto-modifies. Presents findings, waits for confirmation.
   - Integration: Called manually or nudged by forge feed-forward

**Commit:** `feat: create skill stocktake skill`

---

### Task 12: Diagnostic Pattern Capture (Cartographer Landmines Extension)

**Files:**
- Modify: `skills/cartographer-skill/SKILL.md`
- Modify: `skills/cartographer-skill/recorder-prompt.md`
- Modify: `skills/forge-skill/SKILL.md`

**Dependencies:** Task 1

**Steps:**

1. Edit `skills/cartographer-skill/SKILL.md`:
   - In the `landmines.md` format section, add two optional fields:
     - `dead_ends` — Hypotheses tried and rejected, with evidence that ruled them out. Framed as "if you go here, check for X" not "don't go here"
     - `diagnostic_path` — The diagnostic steps that actually revealed the root cause (actual sequence, not idealized)
   - Update the landmines template:
     ```markdown
     - **[Short title]** — [What breaks and why. Module: X. Severity: high/medium]
       - **Dead ends:** [hypothesis tried] — ruled out because [evidence]. (Optional)
       - **Diagnostic path:** [steps that found root cause]. (Optional)
     ```
   - In Mode 3 (Load Module Context), add note: debugging investigators and synthesis agents receive landmines with dead_ends and diagnostic_path for hypothesis cross-referencing

2. Edit `skills/cartographer-skill/recorder-prompt.md`:
   - Add `dead_ends` and `diagnostic_path` to the landmine entry format
   - Add guidance: "For debugging-originated landmines, include dead_ends (hypotheses tried and evidence that ruled them out) and diagnostic_path (steps that found the root cause)"

3. Edit `skills/forge-skill/SKILL.md`:
   - In the retrospective section, add: "For debugging sessions, the retrospective subagent also extracts diagnostic patterns using a dedicated extraction step. Patterns are written to cartographer's landmines via `crucible:cartographer` (record mode) with `dead_ends` and `diagnostic_path` fields."
   - Update the integration table: add a row for debugging retrospective -> cartographer recording

**Commit:** `feat: extend cartographer landmines with diagnostic pattern capture`

---

### Task 13: Agent Teams Graceful Degradation

**Files:**
- Modify: `skills/build/SKILL.md`

**Dependencies:** Task 1

**Steps:**

1. Edit `skills/build/SKILL.md`:
   - In Phase 3, Step 1 (Create Team and Task List), add a graceful degradation block:
     - "If `TeamCreate` fails (agent teams not available), output a clear one-time warning:"
       ```
       Warning: Agent teams are not available. Recommended: set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
       Falling back to sequential subagent dispatch via Agent tool.
       ```
     - "Fall back to sequential subagent dispatch via the regular Task tool (without `team_name`). Everything still works — independent tasks run sequentially instead of in parallel."
   - Add to the Context Management section: "If agent teams are unavailable, the lead dispatches tasks sequentially via Task tool. Task tracking still uses TaskCreate/TaskUpdate for state management."

**Commit:** `feat: add graceful degradation when agent teams are unavailable`

---

### Task 14: Add Quality Gate to Mockup-Builder and Mock-to-Unity

**Files:**
- Modify: `skills/mockup-builder/SKILL.md`
- Modify: `skills/mock-to-unity/SKILL.md`

**Dependencies:** Task 1, Task 3

**Steps:**

1. Edit `skills/mockup-builder/SKILL.md`:
   - Add quality gate documentation after "After Creating the Mockup":
     - "This skill produces **mockups**. When used standalone, invoke `crucible:quality-gate` after the mockup is created and committed. When used as a sub-skill of build, the parent orchestrator handles gating."

2. Edit `skills/mock-to-unity/SKILL.md`:
   - Add quality gate documentation after Step 5 (Self-Verify):
     - "This skill produces **translation maps** and **implementations**. When used standalone, invoke `crucible:quality-gate` after self-verification. When used as a sub-skill of build, the parent orchestrator handles gating."

**Commit:** `feat: add quality gate invocation to mockup-builder and mock-to-unity`

---

### Task 15: Update README

**Files:**
- Modify: `README.md`

**Dependencies:** Tasks 1-14 (all prior tasks)

**Steps:**

1. Update the skill table to reflect all renames (Task 1 already updated names; this pass updates descriptions):
   - `design` (was brainstorming) — update description
   - `planning` (was writing-plans) — update description
   - `debugging` (was systematic-debugging) — update description to mention Phase 3.5, domain detection
   - `code-review` (was requesting-code-review) — update description
   - `review-feedback` (was receiving-code-review) — update description
   - `finish` (was finishing-a-development-branch) — update description
   - `parallel` (was dispatching-parallel-agents) — update description
   - `verify` (was verification-before-completion) — update description
   - `worktree` (was using-git-worktrees) — update description
   - `getting-started` (was using-crucible) — update description
   - `skill-authoring` (was writing-skills) — update description

2. Add new skills to the table:
   - `quality-gate` — in Quality section: "Iterative red-teaming of any artifact. Default 3-round cap. Invoked by design, planning, debugging, mockup-builder, and mock-to-unity."
   - `stocktake` — in Meta section: "Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan or full evaluation modes."

3. Update the "How It Works" pipeline description to include quality gates and de-sloppify:
   - Phase 2: mention quality gate on design
   - Phase 3: mention quality gate on plan
   - Phase 4: mention de-sloppify cleanup step between implementer and reviewer
   - Phase 5: mention quality gate on implementation

4. Add a "## Setup" section after "## Installation":
   - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — required for build's team-based execution; skills degrade gracefully without it
   - `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` — performance recommendation for long-running pipelines

5. Clean up the "## Origin" section:
   - Remove superpowers-specific references
   - Keep it brief: "Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained."

6. Add a "## Rename History" subsection (or note) documenting the rename table for users upgrading from pre-overhaul versions.

**Commit:** `docs: update README with new skills, setup section, pipeline changes`

---

### Task 16: Forge Stocktake Nudge Integration

**Files:**
- Modify: `skills/forge-skill/feed-forward-prompt.md`

**Dependencies:** Task 1, Task 11

**Steps:**

1. Edit `skills/forge-skill/feed-forward-prompt.md`:
   - Add a section to the feed-forward advisor prompt: "Also check for skill stocktake staleness: if `skills/stocktake/results.json` exists, check its timestamp. If last run was 30+ days ago (or if the file doesn't exist), include this advisory: 'Skill stocktake hasn't run in [N] days (or never). Consider running `crucible:stocktake` to audit skill health.'"
   - This is a lightweight addition to the existing feed-forward prompt

**Commit:** `feat: add stocktake staleness nudge to forge feed-forward`

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: Rename all 11 skills
- Task 2: Create shared prompt snippets

**Wave 2 (depends on Wave 1):**
- Task 3: Create quality gate skill (depends on 1)
- Task 4: Deduplicate implementer prompts (depends on 1, 2)
- Task 5: Deduplicate reviewer prompts (depends on 1, 2)
- Task 8: De-sloppify (depends on 1)
- Task 10: Orchestrator narration (depends on 1)
- Task 11: Skill stocktake (depends on 1)
- Task 12: Diagnostic pattern capture (depends on 1)
- Task 13: Agent teams degradation (depends on 1)

**Wave 3 (depends on Wave 2):**
- Task 6: Quality gate in design + planning (depends on 1, 3)
- Task 7: Debugging enhancements (depends on 1, 3)
- Task 14: Quality gate in mockup-builder + mock-to-unity (depends on 1, 3)
- Task 9: Session metrics (depends on 1, 7, 8)
- Task 16: Forge stocktake nudge (depends on 1, 11)

**Wave 4 (depends on everything):**
- Task 15: README update (depends on all)
