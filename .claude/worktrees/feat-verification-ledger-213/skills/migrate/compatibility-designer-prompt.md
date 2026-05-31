<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Compatibility Designer Prompt Template

Use this template when dispatching the Compatibility Layer Designer agent in Phase 4.

```
Task tool (model: opus):
  description: "Design compatibility layer for migration: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are designing the compatibility layer that allows old and new code
    to coexist during a migration. This is the safety mechanism that makes
    incremental migration possible.

    ## Migration Analysis (API Delta)

    [MIGRATION_ANALYSIS — paste contents of migration-analysis.md]

    ## Phase Plan

    [PHASE_PLAN — paste contents of phase-plan.md, especially which phases
     require coexistence]

    ## Your Job

    For each breaking change that requires a coexistence period, design a
    shim or adapter that allows old consumers to keep working while new
    consumers use the new API.

    ### Coexistence Patterns

    Choose the appropriate pattern for each shim:

    **1. Strangler Fig (old wraps new)**
    - The old interface remains but delegates to the new implementation
    - Old consumers call the old API; it internally calls the new API
    - Best when: the new API is a superset or refinement of the old
    - Example: `oldFunction(a, b)` internally calls `newFunction({a, b, defaults})`

    **2. Facade (new wraps old)**
    - A new interface is created that delegates to the old implementation
    - New consumers call the new API; it internally calls the old API
    - Best when: you want to start writing new code against the new API
      before the old implementation is replaced
    - Example: `newClient.send(msg)` internally calls `oldClient.post(msg.body)`

    **3. Dual Registration**
    - Both old and new implementations are registered simultaneously
    - A router/factory decides which to use based on context
    - Best when: different consumers need different versions during migration
    - Example: DI container registers both `IAuthV2` and `IAuthV3`

    ### Output Format

    Write to [SCRATCH_DIR]/compatibility-spec.md:

    ## Compatibility Layer Specification

    ### Shim [N]: [Name]
    - **Breaking change:** [which breaking change this shim covers]
    - **Pattern:** strangler-fig | facade | dual-registration
    - **Old interface:** [what old consumers call]
    - **New interface:** [what new consumers call]
    - **Mapping:** [old call] -> [shim] -> [new call]
    - **Direction:** old-to-new | new-to-old
    - **Files to create:** [new files for the shim]
    - **Files to modify:** [existing files that need wiring changes]
    - **Tests required:**
      - [ ] Old consumer calling old API through shim produces correct result
      - [ ] New consumer calling new API directly produces correct result
      - [ ] Old and new consumers can operate simultaneously without interference
    - **Removal criteria:** [when this shim can be safely deleted]
      - All consumers in the consumer registry have been migrated off the old API
      - No import/reference to the shim exists outside of test files
      - All shim tests can be deleted without reducing real coverage

    ### Summary
    - **Total shims:** N
    - **Estimated shim LOC:** [rough estimate]
    - **Shims that can share infrastructure:** [any shims that can be combined]

    ## Rules

    - Every shim must have bidirectional tests (old path works, new path works)
    - Shims must be self-contained — removing a shim should require deleting
      only the shim files and removing the wiring, not modifying consumer code
    - Do not over-engineer shims. A shim is temporary scaffolding, not
      permanent architecture. Prefer the simplest pattern that works.
    - If a breaking change affects <3 consumers and all are in the same
      module, a shim may be unnecessary — note this as "direct migration
      recommended" instead of designing a shim
    - Removal criteria must be concrete and checkable (not "when it seems
      safe" but "when grep for OldAPI returns only test files")
```
