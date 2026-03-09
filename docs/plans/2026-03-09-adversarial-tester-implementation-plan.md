# Adversarial Tester — Implementation Plan

**Goal:** Add a new `adversarial-tester` skill to crucible, integrate it into the build pipeline's Phase 3, de-Riftlock three existing skills, and update the README.

**Architecture:** Markdown-only changes across 8 files (2 new, 6 modified). No application code.

**Design doc:** `docs/plans/2026-03-09-adversarial-tester-design.md`

---

## Dependency Graph

```
Task 1 (new skill files) ──────────────────────┐
Task 2 (build integration) ── depends on 1 ────┤
Task 3 (de-Riftlock skills) ── no deps ────────┤
Task 4 (README update) ── depends on 1, 2, 3 ──┘
```

---

### Task 1: Create Adversarial Tester Skill

Create the standalone skill definition and subagent dispatch template.

**Files (2):**
- Create: `skills/adversarial-tester/SKILL.md`
- Create: `skills/adversarial-tester/break-it-prompt.md`

**Complexity:** Medium
**Dependencies:** None

**Steps:**

1. Create `skills/adversarial-tester/` directory.

2. Write `skills/adversarial-tester/SKILL.md` with:
   - Frontmatter: `name: adversarial-tester`, description triggers on "break it", "adversarial test", "stress test implementation", "find weaknesses", or any task seeking to expose unknown failure modes in completed implementation
   - Overview: Reads completed implementation and writes up to 5 tests designed to make it break. Targets edge cases, boundary conditions, and failure modes the implementer didn't anticipate.
   - Model: Opus (adversarial reasoning about failure modes requires creative analytical thinking)
   - Announce at start: "I'm using the adversarial-tester skill to find weaknesses in this implementation."
   - Distinction table (from design doc Decision #5): Red-team vs Test Gap Writer vs Adversarial Tester — question asked, output type, scope
   - Process section:
     1. Read the implementation diff
     2. Identify attack surface (public APIs, state transitions, boundary conditions, error paths)
     3. Generate 8-10 candidate failure modes
     4. Rank by likelihood x impact
     5. Select top 5
     6. Write one test per failure mode
     7. Run each test and record result
   - Cap: maximum 5 failure modes, ranked by likelihood x impact
   - Output: ADVERSARIAL TEST REPORT with summary + per-failure-mode details (format from design doc Decision #7)
   - Guardrails (must NOT do):
     - Modify production code
     - Write more than 5 tests
     - Refactor or "improve" existing tests
     - Test implementation details (only observable behavior)
     - Duplicate coverage already provided by existing tests
   - Fix loop mechanics (from design doc Decision #6):
     - All PASS: implementation is robust, log and proceed
     - Some FAIL: dispatch implementer to fix, re-run, one more attempt then escalate
     - Tests ERROR: adversarial tester mistake, discard broken tests, proceed
     - Quality bypass prevention: fix touches 3+ files -> lightweight code review before completing
   - Skip condition (orchestrator-assessed, from design doc Decision #4):
     - Task diff contains no behavioral source files (only .md, .json, .yaml, .uss, .uxml)
     - No tests were written during implementation (pure scaffolding)
     - If borderline, dispatch — the subagent can report "No behavioral logic to attack"
   - Quality gate section: "This skill produces **adversarial tests**. When used standalone, the tests themselves are the quality mechanism — no additional quality gate needed. When used within the build pipeline, the orchestrator handles outcome routing."
   - Integration section:
     - Called by: `crucible:build` (Phase 3, after test gap writer)
     - Uses: `crucible:test-driven-development` patterns for test writing
     - Pairs with: `crucible:code-review` (lightweight review if fix touches 3+ files)

3. Write `skills/adversarial-tester/break-it-prompt.md`:
   - This is the subagent dispatch template
   - Format: follows the same pattern as `skills/build/test-gap-writer-prompt.md` (Task tool dispatch block)
   - Framing: "You are an adversarial tester. Your job is to find the top 5 ways this implementation will break at runtime."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: git diff <pre-task-sha>..HEAD — the implementer's changes]`
     - `[PASTE: Project test conventions from CLAUDE.md or cartographer]`
     - `[PASTE: Cartographer module context, if available]`
   - Process (from design doc Decision #7):
     1. Read the diff and identify the attack surface (public APIs, state transitions, boundary conditions, error paths)
     2. Generate candidate failure modes (aim for 8-10)
     3. Rank by likelihood x impact
     4. Select top 5
     5. Write one test per failure mode, following project test conventions
     6. Run each test and record result (PASS/FAIL/ERROR)
   - Report format: ADVERSARIAL TEST REPORT (exact format from design doc)
   - Guardrails block (no production code mods, max 5 tests, no refactoring, no implementation detail testing, no duplicating existing coverage)
   - Context self-monitoring block (same pattern as other subagent prompts: report at 50%+ utilization)
   - What NOT to do list:
     - Do NOT modify production code
     - Do NOT refactor or improve existing tests
     - Do NOT write more than 5 tests
     - Do NOT test internal implementation details — only observable behavior
     - Do NOT duplicate coverage already provided by existing tests or test gap writer

**Commit:** `feat: create adversarial-tester skill and break-it prompt template`

---

### Task 2: Integrate Adversarial Tester into Build Pipeline

Add the adversarial tester step to build SKILL.md Phase 3, after the Test Gap Writer.

**Files (1):**
- Modify: `skills/build/SKILL.md`

**Complexity:** Medium
**Dependencies:** Task 1

**Steps:**

1. Update the flow diagram (currently lines 195-204) to include Adversarial Tester after Test Gap Writer:
   ```dot
   digraph review {
     "Implementer builds + tests" -> "De-sloppify cleanup";
     "De-sloppify cleanup" -> "Pass 1: Code Review";
     "Pass 1: Code Review" -> "Implementer fixes code findings";
     "Implementer fixes code findings" -> "Pass 2: Test Review";
     "Pass 2: Test Review" -> "Implementer fixes test findings";
     "Implementer fixes test findings" -> "Test Gap Writer";
     "Test Gap Writer" -> "Adversarial Tester";
     "Adversarial Tester" -> "Task complete";
   }
   ```

2. Add a new `#### Adversarial Tester` section after the Test Gap Writer section (after line 221). Content:

   After the test gap writer completes (or is skipped), dispatch an **Adversarial Tester** (Opus) using `skills/adversarial-tester/break-it-prompt.md`:

   1. Input: Full diff of the task's changes (`git diff <pre-task-sha>..HEAD`), project test conventions, cartographer module context (if available)
   2. The adversarial tester identifies the top 5 most likely failure modes, writes one test per mode, and runs them
   3. Outcome handling:
      - **All tests PASS:** Implementation is robust. Log results and proceed to task complete.
      - **Some tests FAIL:** Real weaknesses found. Dispatch implementer to fix. Re-run all tests (including adversarial). If pass -> task complete. If fail -> one more fix attempt, then escalate to user.
      - **Tests ERROR (won't compile):** Adversarial tester mistake. Discard broken tests, log, proceed to task complete.
   4. Quality bypass prevention: If the implementer's fix touches more than 3 files, route through a lightweight code review before completing.
   5. Commit adversarial tests: `test: adversarial tests for task N`

   **Skip this step when:**
   - The task diff contains no behavioral source files (only `.md`, `.json`, `.yaml`, `.uss`, `.uxml`)
   - No tests were written during implementation (pure scaffolding)

3. Add `skills/adversarial-tester/break-it-prompt.md` to the Prompt Templates list. Follow the existing cross-skill reference pattern used for red-team and innovate (lines 339-341 of build SKILL.md):
   ```
   - `crucible:adversarial-tester` — `skills/adversarial-tester/break-it-prompt.md`
   ```
   Add this in the "Red-team and innovate prompts live in their respective skills" section, since the adversarial tester is also a standalone skill with its own prompt template.

4. No "How It Works" summary exists in build SKILL.md (that section is in README.md only). Skip this step.

**Commit:** `feat: integrate adversarial tester into build pipeline Phase 3`

---

### Task 3: De-Riftlock Skills

Remove all Riftlock-specific references from skills that should be project-agnostic. Replace with generic equivalents.

**Files (4):**
- Modify: `skills/mockup-builder/SKILL.md` (5 replacements)
- Modify: `skills/mockup-builder/references/theme-variables.md` (1 replacement)
- Modify: `skills/mock-to-unity/SKILL.md` (6 replacements)
- Modify: `skills/debugging/implementer-prompt.md` (1 replacement)

**Complexity:** Low
**Dependencies:** None

**Steps:**

1. Edit `skills/mockup-builder/SKILL.md` — 5 replacements:
   - Line 3 (frontmatter description): `"for Riftlock UI"` -> `"for your project's UI"`
   - Line 8 (opening paragraph): `"for Riftlock UI"` -> `"for your project's UI"`
   - Line 15 (Before Starting, step 2): `"Riftlock's visual language"` -> `"the project's visual language"`
   - Line 79 (What This Skill Does NOT Do): `"Riftlock's established dark sci-fi visual language"` -> `"the project's established visual language"`
   - Line 86 (After Creating the Mockup): `"Riftlock's visual language"` -> `"the project's visual language"`

2. Edit `skills/mockup-builder/references/theme-variables.md` — 1 replacement:
   - Line 3: `"Source: \`Riftlock/Assets/_Project/Resources/UI/Theme.uss\`"` -> `"Source: Your project's Theme.uss file (e.g., \`Assets/_Project/Resources/UI/Theme.uss\`)"`

3. Edit `skills/mock-to-unity/SKILL.md` — 6 replacements:
   - Line 12: `"riftlock-standards"` -> `"your project's coding standards"` (full sentence: "When writing C# controllers (Layers 1, 3, 4), your project's coding standards apply to all C# code.")
   - Line 24: `"Riftlock/Assets/_Project/Resources/UI/"` -> `"Assets/_Project/Resources/UI/"` (or `"<project>/Assets/_Project/Resources/UI/"`)
   - Line 25: `"Riftlock/Assets/_Project/Scripts/Systems/UI/<subsystem>/"` -> `"Assets/_Project/Scripts/Systems/UI/<subsystem>/"`
   - Line 26: `"Riftlock/Assets/_Project/Resources/UI/Theme.uss"` -> `"Assets/_Project/Resources/UI/Theme.uss"`
   - Line 101: `"Riftlock/Assets/_Project/Resources/UI/Theme.uss"` -> `"Assets/_Project/Resources/UI/Theme.uss"` (one occurrence — the "add it to" path; the "Also update" reference to mockup-builder does not contain Riftlock)
   - Line 131: `"## Riftlock-Specific Rules"` -> `"## Unity 6 Rules"` (the rules are Unity 6 specific, not Riftlock specific — FontManager, StyleSheet loading, ScrollView height bug, etc.)

4. Edit `skills/debugging/implementer-prompt.md` — 1 replacement:
   - Line 39: `"Riftlock.Tests.EditMode"` -> `"MyProject.Tests.EditMode"` (this is inside a placeholder comment showing example conventions, so a generic project name is appropriate)

5. Verification: After all edits, grep for "riftlock" (case-insensitive) across `skills/` directory. Expected: zero hits. (Hits in `docs/plans/` are expected and acceptable — historical documents are not updated.)

**Commit:** `refactor: de-Riftlock mockup-builder, mock-to-unity, and debugging skills`

---

### Task 4: Update README

Add adversarial-tester to the skill table and add a Project Origin section.

**Files (1):**
- Modify: `README.md`

**Complexity:** Low
**Dependencies:** Task 1, Task 2, Task 3

**Steps:**

1. Add `adversarial-tester` to the **Implementation** skill table (after `parallel`, around line 54). New row:
   ```
   | **adversarial-tester** | Reads completed implementation and writes up to 5 tests designed to expose unknown failure modes. Targets edge cases, boundary conditions, and runtime behavior the implementer didn't anticipate. |
   ```

2. Update the **How It Works** Phase 3 description (line 100) to mention the adversarial tester. Current text:
   ```
   3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup (removes unnecessary code), code review per task, and a test gap writer (fills coverage gaps identified by the test reviewer). Cartographer loads module context into subagent prompts.
   ```
   Updated text:
   ```
   3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup (removes unnecessary code), code review per task, a test gap writer (fills coverage gaps identified by the test reviewer), and an adversarial tester (writes tests designed to break the implementation). Cartographer loads module context into subagent prompts.
   ```

3. Add a **## Project Origin** section after the "## Origin" section (currently at line 107). Content:

   ```markdown
   ## Project Origin

   Crucible was developed alongside [Riftlock](https://github.com/raddue/riftlock), a Unity 6 roguelike. Several skills reflect that Unity development context:

   - **mockup-builder** — Creates HTML mockups constrained to Theme.uss variables for Unity UI Toolkit translation
   - **mock-to-unity** — Translates mockups into Unity UI Toolkit USS/C# with Unity 6 bug workarounds
   - **ui-verify** — Compares implemented UI against mockups via MCP screenshots or structural audit

   These skills are usable in any Unity project. All other crucible skills are language- and framework-agnostic.
   ```

**Commit:** `docs: add adversarial-tester to README and add Project Origin section`

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: Create adversarial tester skill (2 new files)
- Task 3: De-Riftlock skills (4 modified files)

**Wave 2 (depends on Wave 1):**
- Task 2: Integrate into build pipeline (depends on Task 1)

**Wave 3 (depends on all prior):**
- Task 4: Update README (depends on Tasks 1, 2, 3)

---

## Verification Checklist

After all tasks complete, run these checks:

1. **Adversarial tester SKILL.md validation:**
   - Has valid frontmatter (`name:`, `description:`)
   - References `break-it-prompt.md` (file exists in same directory)
   - Cross-references resolve: `crucible:build`, `crucible:test-driven-development`, `crucible:code-review`

2. **Build SKILL.md flow diagram:**
   - Contains `"Test Gap Writer" -> "Adversarial Tester"` in the dot graph
   - Contains `"Adversarial Tester" -> "Task complete"` in the dot graph
   - Adversarial Tester section exists after Test Gap Writer section

3. **Zero Riftlock hits in skills/:**
   - `grep -ri "riftlock" skills/` returns zero results
   - `grep -ri "riftlock" docs/plans/` is expected to have hits (historical, acceptable)

4. **README accuracy:**
   - `adversarial-tester` appears in the Implementation skill table
   - Phase 3 description mentions adversarial tester
   - "Project Origin" section exists and lists mockup-builder, mock-to-unity, ui-verify

5. **Cross-reference resolution:**
   - `skills/adversarial-tester/break-it-prompt.md` exists (referenced by SKILL.md and build SKILL.md)
   - `skills/adversarial-tester/SKILL.md` exists (referenced by build SKILL.md prompt templates list)
   - All `crucible:` references in new content point to existing skill directories
