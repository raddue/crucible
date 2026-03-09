# Adversarial Tester Skill — Design Doc

**Date:** 2026-03-09
**Status:** Approved (hardened after quality gate round 1)

## Summary

Add a new Crucible skill (`adversarial-tester`) that reads completed implementation and writes up to 5 tests designed to make it break. Targets edge cases, boundary conditions, and failure modes the implementer didn't anticipate.

Inspired by [automated adversarial testing patterns](https://www.latent.space/p/reviews-dead): "a third agent attempts to break what the first agent built, specifically targeting edge cases and failure modes. Red team, blue team — but automated."

## Design Decisions

### 1. Scope Cap: 5 Failure Modes

The adversarial tester identifies and ranks the top 5 most likely failure modes by likelihood and impact. This prevents unbounded test generation while ensuring meaningful coverage of blind spots.

### 2. Standalone Skill with Build Integration

- `adversarial-tester` is a standalone skill invocable independently (`crucible:adversarial-tester`)
- Also integrated into the build pipeline's Phase 3 task execution flow
- Can be used after any implementation work, not just build pipeline tasks
- **Model:** Opus (adversarial reasoning about failure modes requires creative analytical thinking)

### 3. Pipeline Position: After Test Gap Writer

Build Phase 3 task flow becomes:
```
Implementer → Cleanup → Code Review → Test Review → Test Gap Writer → Adversarial Tester → Task complete
```

The adversarial tester runs last because:
- It needs the full, reviewed, cleaned-up implementation to attack
- Test gap writer fills known gaps; adversarial tester finds unknown ones
- Failing adversarial tests trigger implementer fixes before task completion

### 4. Skip Condition (Orchestrator-Assessed)

The **orchestrator** decides whether to skip, not the subagent. Skip when:
- The task diff contains no behavioral source files (e.g., only `.md`, `.json`, `.yaml`, `.uss`, `.uxml`)
- No tests were written during implementation (pure scaffolding)

If borderline, dispatch the adversarial tester — it can still report "No behavioral logic to attack" as a secondary safety valve, but the orchestrator makes the primary call.

### 5. Distinction from Existing Agents

| Agent | Question | Output | Scope |
|-------|----------|--------|-------|
| Red-team | "What's wrong with this artifact?" | Written findings (Fatal/Significant/Minor) | Attacks designs, plans, code quality |
| Test Gap Writer | "What known gaps need filling?" | Executable tests (expected to PASS) | Fills reviewer-identified holes |
| Adversarial Tester | "What runtime behavior will break?" | Executable tests (may PASS or FAIL) | Finds unknown weaknesses in behavior |

### 6. Fix Loop Mechanics

When the adversarial tester's tests are run:

- **All tests PASS:** Implementation is robust against these failure modes. Log results and proceed to task complete.
- **Some tests FAIL:** Real weaknesses found. Dispatch implementer to fix. After fix, re-run all tests (including adversarial). If pass → task complete. If fail → one more fix attempt, then escalate.
- **Tests ERROR (won't compile):** Adversarial tester made a mistake. Discard broken tests, log, proceed to task complete.

**Quality bypass prevention:** If the implementer's fix touches more than 3 files, route through a lightweight code review before completing. Small fixes (1-3 files) proceed directly after tests pass.

### 7. Prompt Template Structure

The `break-it-prompt.md` template must include:

**Input sections:**
- Full diff of the task's changes (`git diff <pre-task-sha>..HEAD`)
- Project test conventions (framework, naming, file locations)
- Cartographer module context (if available)

**Process:**
1. Read the diff and identify the attack surface (public APIs, state transitions, boundary conditions, error paths)
2. Generate candidate failure modes (aim for 8-10 candidates)
3. Rank by likelihood × impact (likelihood: how easily triggered in normal use; impact: severity of consequence)
4. Select top 5 failure modes
5. Write one test per failure mode
6. Run each test and record result (PASS/FAIL/ERROR)

**Report format:**
```
## ADVERSARIAL TEST REPORT

### Summary
- Failure modes identified: N
- Tests written: N
- Tests PASSING (implementation robust): N
- Tests FAILING (weaknesses found): N

### Failure Mode 1: [Title]
- **Attack vector:** [how this breaks]
- **Likelihood:** High/Medium/Low
- **Impact:** High/Medium/Low
- **Test:** `TestClassName.TestMethodName`
- **Result:** PASS/FAIL
- **If FAIL — fix guidance:** [what the implementer should change]

[repeat for each failure mode]
```

**Guardrails (must NOT do):**
- Modify production code
- Write more than 5 tests
- Refactor or "improve" existing tests
- Test implementation details (only test observable behavior)
- Duplicate coverage already provided by existing tests

## Deliverables

### New Files

1. **`skills/adversarial-tester/SKILL.md`** — Standalone skill definition
   - Frontmatter with name, description, trigger conditions
   - Process: read diff, identify attack surface, rank failure modes, write tests
   - Cap at 5 failure modes, ranked by likelihood × impact
   - Output: tests that expose weaknesses + brief rationale per test
   - Fix loop mechanics and outcome handling
   - Skip condition (orchestrator-assessed)

2. **`skills/adversarial-tester/break-it-prompt.md`** — Subagent dispatch template
   - Follows the template structure defined in Design Decision #7
   - Used by build pipeline and standalone invocation

### Modified Files

3. **`skills/build/SKILL.md`** — Add adversarial tester step
   - New step after Test Gap Writer in Phase 3 Step 3
   - Orchestrator-assessed skip condition
   - Fix loop with quality bypass prevention
   - Updated flow diagram

4. **`skills/mockup-builder/SKILL.md`** — De-Riftlock (5 references)
   - Replace "Riftlock UI" → "your project's UI" or equivalent
   - Replace "Riftlock's visual language" → "the project's visual language"
   - Generalize path references

5. **`skills/mockup-builder/references/theme-variables.md`** — De-Riftlock (1 reference)
   - Replace Riftlock-specific path with generic placeholder

6. **`skills/mock-to-unity/SKILL.md`** — De-Riftlock (6 references)
   - Replace `Riftlock/Assets/` paths with generic `Assets/` or `<project>/Assets/`
   - Remove or generalize "riftlock-standards" reference
   - Rename "Riftlock-Specific Rules" section

7. **`skills/debugging/implementer-prompt.md`** — De-Riftlock (1 reference)
   - Replace "Riftlock.Tests.EditMode" namespace example with generic

8. **`README.md`** — Updates (additive only, no existing Riftlock references to clean)
   - Add `adversarial-tester` to Implementation skill table
   - Add "Project Origin" section noting Unity development roots
   - List Unity-specific skills (mockup-builder, mock-to-unity, ui-verify)

## Acceptance Criteria

- [ ] `adversarial-tester` skill is invocable standalone and produces tests
- [ ] Build pipeline dispatches adversarial tester after test gap writer
- [ ] Adversarial tester respects 5 failure mode cap
- [ ] Orchestrator correctly skips adversarial tester for non-behavioral changes
- [ ] When adversarial tests fail, implementer is dispatched and all tests pass before task completion
- [ ] No Riftlock references remain in mockup-builder, mock-to-unity, or debugging skills
- [ ] README includes adversarial-tester and Project Origin section

## Future Enhancement: Mutation Replay

Proposed during innovate phase — a companion step that generates semantic mutations of the implementation (invert conditionals, swap operators, delete early returns) and checks whether existing tests catch them. Surviving mutants reveal tests that touch code but assert nothing meaningful.

Not included in this build because it's a separate concern (validating test *strength* vs. finding *missing* tests). Worth building as a follow-up skill or adversarial-tester extension.

## Testing Strategy

- **Skill content validation**: Verify SKILL.md follows frontmatter schema, cross-references resolve, trigger conditions are clear
- **Build integration**: Verify the new step is correctly placed in the Phase 3 flow diagram and prose
- **De-Riftlock audit**: Grep for "riftlock" (case-insensitive) in all skill files post-cleanup — zero hits expected (excluding docs/plans/)
- **README accuracy**: Verify all skill names in tables match actual skill directories
- **Fix loop validation**: Verify build SKILL.md defines outcome handling for PASS, FAIL, and ERROR cases
