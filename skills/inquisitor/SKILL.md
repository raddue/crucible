---
name: inquisitor
description: "Use when a full feature is assembled and you want to hunt cross-component bugs before final quality gate. Runs 5 parallel adversarial dimensions against the complete implementation diff. Triggers on 'inquisitor', 'hunt bugs', 'cross-component test', 'find integration issues', or automatically in build pipeline Phase 4."
---

# Inquisitor

Hunt cross-component bugs by dispatching 5 parallel adversarial dimensions against the full feature diff. Each dimension writes and runs tests targeting a different class of failure mode that per-task testing misses.

**Announce at start:** "I'm using the inquisitor skill to hunt cross-component bugs across the full implementation."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Model:** Opus (orchestrating parallel adversarial subagents requires precise coordination)

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

## Why This Exists

Per-task adversarial testing (Phase 3) sees one task's diff. It catches bugs within each task's scope. But the bugs you find instantly after a big feature lands live in the **seams** -- wiring that's almost right, state that initializes in one task but gets consumed in another, edge cases that only appear when the whole feature is assembled.

The inquisitor sees the FULL diff and attacks the interactions.

## Distinction from Related Skills

| Agent | Question | Output | Scope |
|-------|----------|--------|-------|
| Red-team | "What's wrong with this artifact?" | Written findings (Fatal/Significant/Minor) | Attacks designs, plans, code quality |
| Adversarial Tester | "What runtime behavior breaks?" | Executable tests (per-task) | Single task's changes |
| **Inquisitor** | "What breaks between components?" | Executable tests (full feature) | Cross-component interactions across all tasks |

## The 5 Dimensions

Each dimension is a parallel subagent with a specific attack lens. All 5 are dispatched simultaneously.

### Dimension 1: Wiring

**Question:** "Is everything actually connected?"

**Looks for:**
- New classes/components that exist but are never instantiated or registered
- Missing service registrations (DI container bindings)
- Missing event subscriptions (published but nobody listens, or listener never subscribed)
- Interface implementations that aren't bound
- New entry points (menu items, buttons, routes, commands) that don't trigger the new code
- Factory methods or builders that don't include new types

**Test style:** Instantiate the system and verify new components are reachable and callable through their intended entry points.

### Dimension 2: Integration

**Question:** "Do the new pieces talk to each other correctly?"

**Looks for:**
- Data format mismatches between producer and consumer components
- Type assumption mismatches (producer sends int, consumer expects float)
- Ordering assumptions (A must happen before B, but nothing enforces it)
- Missing data transformations between components
- API contracts that don't match between caller and callee
- Events published with wrong payload shape or missing fields

**Test style:** Set up 2+ new components and verify data flows correctly end-to-end through the interaction chain.

### Dimension 3: Edge Cases

**Question:** "What happens at the boundaries?"

**Looks for:**
- Null/empty inputs at every new public API surface
- Zero and negative values where only positives are expected
- Maximum values and overflow conditions
- Empty collections passed to methods expecting non-empty
- Strings with special characters (empty, whitespace-only, extremely long)
- Boundary conditions at state transition thresholds

**Test style:** Call new APIs with boundary inputs and verify graceful handling (no crash, correct error, or documented behavior).

### Dimension 4: State & Lifecycle

**Question:** "Is state managed correctly across the feature?"

**Looks for:**
- Initialization order dependencies (A must init before B, but nothing enforces it)
- Missing disposal/cleanup (IDisposable, Unsubscribe, RemoveListener, event detachment)
- Stale references after disposal (use-after-dispose)
- State mutations that aren't thread-safe when they should be
- Singleton assumptions that don't hold in the actual runtime
- State not reset between uses (pooling, recycling, scene transitions)

**Test style:** Exercise lifecycle sequences (create, use, dispose, re-create) and verify correct behavior at each stage.

### Dimension 5: Regression

**Question:** "Did we break anything that used to work?"

**Looks for:**
- Existing methods whose return values or side effects changed subtly
- Modified base classes affecting derived class behavior
- Changed default values, constructor signatures, or parameter ordering
- Modified event handling order or priority
- Changed error handling (swallowing exceptions that used to propagate, or vice versa)
- Moved or renamed things that other code depends on

**Test style:** Exercise existing functionality through paths that touch newly modified code, verifying prior behavior is preserved.

## Process

### Step 1: Determine the Full Feature Diff

Compute the diff covering ALL implementation changes:

- **Pipeline mode:** The build orchestrator provides the base commit SHA. Use `git diff <base-sha>..HEAD`.
- **Standalone mode:** Use `git merge-base HEAD main` (or the user-specified base branch) to find the diverge point. Use `git diff <merge-base>..HEAD`.

If the diff is empty or contains only non-behavioral files (`.md`, `.json`, `.yaml`, `.uss`, `.uxml`), report "No behavioral changes to investigate" and stop.

### Step 2: Dispatch 5 Parallel Inquisitor Subagents

For each dimension, dispatch a fresh subagent (Opus) using `./inquisitor-prompt.md`:

- Pass the full diff
- Pass the dimension name and its focus areas (from the dimension definitions above)
- Pass project test conventions (from CLAUDE.md or cartographer)
- Pass cartographer module context if available
- Each subagent identifies 3-5 attack vectors, writes one test per vector, runs them, and reports

**All 5 dimensions are dispatched in parallel.** Do not wait for one to finish before starting another.

Status update format while dispatching:
> "Inquisitor: dispatching 5 dimensions in parallel — Wiring, Integration, Edge Cases, State & Lifecycle, Regression."

### Step 3: Collect and Aggregate Reports

When all 5 subagents complete, aggregate their reports into a single INQUISITOR REPORT (see Report Format below).

Classify overall results:
- **All PASS across all dimensions:** Feature is robust. Report results and proceed.
- **Some FAIL in one or more dimensions:** Weaknesses found. Proceed to fix cycle (Step 4).
- **All ERROR in a dimension:** Discard that dimension's broken tests. Note in report. Proceed with remaining dimensions.

Status update format:
> "Inquisitor complete: Wiring 3/3 PASS, Integration 4/4 PASS, Edge Cases 3/5 PASS (2 FAIL), State 4/4 PASS, Regression 3/3 PASS. Dispatching fixes for 2 edge case failures."

### Step 4: Fix Cycle (Only if FAILs Exist)

For each dimension with FAIL results:

1. Dispatch a **Fixer** subagent (Opus) with:
   - The failing test(s) and their attack vector descriptions
   - The relevant source files identified in the failure
   - Fix guidance from the inquisitor's report
2. Fixer implements the fix and runs ALL tests (including the previously-failing adversarial tests)
3. If the fix touches **3+ files:** dispatch a lightweight code review before accepting
4. After fix, re-run ONLY the dimension that had failures to verify
5. **Max 2 fix attempts per dimension.** If a dimension still has FAILs after 2 attempts, escalate to user with full context.

**Cascading fix detection:** If fixes for one dimension cause failures in another dimension's tests, escalate to user immediately -- this indicates a deeper design issue that automated fixes can't resolve.

Commit passing fixes: `fix: inquisitor [dimension] findings`

### Step 5: Final Report

Output the aggregated INQUISITOR REPORT including fix outcomes. The report must include:
- Whether any fixes were made (so the build orchestrator knows whether to re-run code review)
- The pre-inquisitor commit SHA (so the build orchestrator can scope the re-review diff)

## Report Format

```
## INQUISITOR REPORT

### Summary
- Dimensions dispatched: 5
- Total attack vectors tested: N
- Tests PASSING (robust): N
- Tests FAILING (weaknesses found): N
- Tests ERROR (discarded): N
- Dimensions clean: N/5
- Fix cycles required: N

### Dimension: Wiring
#### Attack Vector 1: [Title]
- **What was tested:** [specific wiring concern]
- **Likelihood:** High/Medium/Low
- **Impact:** High/Medium/Low
- **Test:** `TestClassName.TestMethodName`
- **Result:** PASS/FAIL
- **If FAIL -- fix guidance:** [what to change]

[repeat for each attack vector]

### Dimension: Integration
[same structure]

### Dimension: Edge Cases
[same structure]

### Dimension: State & Lifecycle
[same structure]

### Dimension: Regression
[same structure]

### Fix Outcomes (if applicable)
- [Dimension]: [N] failures fixed in [N] attempts
- [Dimension]: [N] failures escalated to user

### Fix Footprint
- Pre-inquisitor SHA: [commit SHA before any fixes]
- Files changed by fixes: [N]
- Code review re-run recommended: YES/NO
```

## Guardrails

**Inquisitor subagents must NOT:**
- Modify production code (only the Fixer modifies code)
- Write more than 5 tests per dimension (25 total max across all dimensions)
- Refactor or "improve" existing tests
- Test implementation details -- only observable behavior
- Duplicate coverage already provided by per-task adversarial tests or test gap writer
- Attack the same vector from multiple dimensions (if overlap, the more specific dimension owns it)

**The orchestrator must NOT:**
- Skip dimensions without justification
- Accept a "no issues found" report without verifying the subagent actually wrote and ran tests
- Continue past a FAIL without either fixing or escalating
- Run more than 2 fix attempts per dimension

## Pipeline Integration

When used within the build pipeline (Phase 4):

- **Runs after:** code-review on full implementation (obvious issues already fixed)
- **Runs before:** quality-gate on full implementation (gate reviews final state including inquisitor fixes)
- **Input:** `git diff <base-sha>..HEAD` where base-sha is the commit before Phase 3 execution began
- **Orchestrator provides:** base SHA, project test conventions, cartographer module context

The build orchestrator handles the inquisitor as a single step. It does NOT invoke the inquisitor's fix cycle independently -- the inquisitor skill manages its own fix cycle internally and reports the final outcome.

## Standalone Usage

Invoke directly with `/inquisitor` when you want to assault a feature branch:

1. Determine base branch (default: `main`, or user-specified)
2. Compute merge-base: `git merge-base HEAD <base-branch>`
3. Run the full inquisitor process against `git diff <merge-base>..HEAD`
4. Report results
5. If FAILs found: ask user whether to fix automatically or just report

## Skip Condition

The **orchestrator** (not this skill) decides whether to skip. When used standalone, use your judgment:
- Skip if the diff contains only non-behavioral files (docs, config, assets)
- If borderline, run the process -- a dimension can report "No attack surface for this dimension" if the diff genuinely has nothing relevant

## Quality Gate

This skill produces **adversarial tests across 5 dimensions**. The tests themselves are the quality mechanism. When used in the build pipeline, the quality-gate that follows reviews the final state including any inquisitor fixes. No additional quality gate is needed on the inquisitor's own output.

## External Model Review (Optional)

**Disabled by default** due to cost: with N external models, this adds 5*N API calls per inquisitor run (one per dimension per model).

Only active if `skills.inquisitor` is explicitly set to `true` in external review config. If the `external_review` MCP tool is unavailable or the call fails for any dimension, skip silently and proceed with host findings only.

Per-dimension: after dispatching the host Opus subagent for each dimension, call the `external_review` MCP tool with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: same diff + dimension-specific framing (dimension name, focus areas, attack lens)
- `skill`: `"inquisitor"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "inquisitor", "dimension": "<dimension_name>"}` (traceability)

Append external perspectives per dimension alongside the host subagent's findings in the dimension section of the INQUISITOR REPORT. External findings inform fix guidance but do not independently trigger fix cycles — only host-written executable test failures drive fixes.

## Integration

- **Called by:** `crucible:build` (Phase 4, after code-review, before quality-gate)
- **Dispatches:** 5 parallel subagents (one per dimension) using `./inquisitor-prompt.md`
- **May dispatch:** Fixer subagents for FAIL results, lightweight code-review if fix touches 3+ files
- **Uses:** `crucible:cartographer` context (when available) for module-aware attack surface analysis
- **Pairs with:** `crucible:adversarial-tester` (per-task, Phase 3) -- inquisitor is the full-feature complement
- **Prompt template:** `inquisitor-prompt.md` (for dimension subagent dispatch)

**Multi-model consensus:** Not applicable. Inquisitor dimensions write and run executable tests, requiring local filesystem and test runner access. See `skills/consensus/SKILL.md` for exclusion rationale.
