# Adversarial Tester Skill — Design Doc

**Date:** 2026-03-09
**Status:** Approved

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

### 3. Pipeline Position: After Test Gap Writer

Build Phase 3 task flow becomes:
```
Implementer → Cleanup → Code Review → Test Review → Test Gap Writer → Adversarial Tester → Task complete
```

The adversarial tester runs last because:
- It needs the full, reviewed, cleaned-up implementation to attack
- Test gap writer fills known gaps; adversarial tester finds unknown ones
- Failing adversarial tests trigger implementer fixes before task completion

### 4. Skip Condition

Skip when the task is pure config, documentation, or scaffolding with no behavioral logic to break. The adversarial tester decides this based on the diff — if there's no testable behavior, it reports "No behavioral logic to attack" and exits.

### 5. Distinction from Existing Agents

| Agent | Question | Perspective |
|-------|----------|-------------|
| Red-team | "What's wrong with this design/code?" | Critic reviewing quality |
| Test Gap Writer | "What coverage did the reviewer identify as missing?" | Gap-filler for known holes |
| Adversarial Tester | "How can I make this break?" | Attacker finding unknown weaknesses |

## Deliverables

### New Files

1. **`skills/adversarial-tester/SKILL.md`** — Standalone skill definition
   - Frontmatter with name, description, trigger conditions
   - Process: read diff, identify attack surface, rank failure modes, write tests
   - Cap at 5 failure modes, ranked by likelihood × impact
   - Output: tests that expose weaknesses + brief rationale per test
   - Skip condition for non-behavioral changes

2. **`skills/adversarial-tester/break-it-prompt.md`** — Subagent dispatch template
   - Used by build pipeline to dispatch the adversarial tester as a subagent
   - Includes: diff context, project conventions, test framework info
   - Structured output format for failure modes and tests

### Modified Files

3. **`skills/build/SKILL.md`** — Add adversarial tester step
   - New step after Test Gap Writer in Phase 3 Step 3
   - Skip condition check
   - Failing tests → dispatch implementer to fix before task completion

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

8. **`README.md`** — Updates
   - Add `adversarial-tester` to Implementation skill table
   - Add "Project Origin" section noting Unity development roots
   - List Unity-specific skills (mockup-builder, mock-to-unity, ui-verify)

## Acceptance Criteria

- [ ] `adversarial-tester` skill is invocable standalone and produces tests
- [ ] Build pipeline dispatches adversarial tester after test gap writer
- [ ] Adversarial tester respects 5 failure mode cap
- [ ] Adversarial tester skips non-behavioral changes
- [ ] No Riftlock references remain in mockup-builder, mock-to-unity, or debugging skills
- [ ] README includes adversarial-tester and Project Origin section
- [ ] All existing tests still pass (no regressions)

## Testing Strategy

- **Skill content validation**: Verify SKILL.md follows frontmatter schema, cross-references resolve, trigger conditions are clear
- **Build integration**: Verify the new step is correctly placed in the Phase 3 flow diagram and prose
- **De-Riftlock audit**: Grep for "riftlock" (case-insensitive) in all skill files post-cleanup — zero hits expected (excluding docs/plans/)
- **README accuracy**: Verify all skill names in tables match actual skill directories
