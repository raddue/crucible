<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Phase Planner Prompt Template

Use this template when dispatching the Phase Planner agent in Phase 3.

```
Task tool (model: opus):
  description: "Decompose migration into phases: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are decomposing a migration into safe, ordered phases. Each phase
    must leave the codebase in a working state.

    ## Migration Analysis

    [MIGRATION_ANALYSIS — paste contents of migration-analysis.md]

    ## Blast Radius

    [BLAST_RADIUS — paste contents of blast-radius.md]

    ## Your Job

    Produce an ordered list of migration phases. The critical invariant is:

    **Safe stopping point:** After completing any phase, the codebase MUST
    compile, all tests MUST pass, and both old and new code paths MUST
    function correctly (during coexistence phases).

    ### Phase Decomposition Rules

    1. **Never remove the old API before all consumers are migrated.**
       The old API stays until the explicit cleanup phase.

    2. **Introduce the new version before creating compatibility layers.**
       The new dependency/API must be available before shims can delegate to it.

    3. **Create compatibility layers before migrating consumers.**
       Shims allow old and new code to coexist safely during migration.

    4. **Migrate consumers in waves, not all at once.**
       Use the consumer dependency graph to determine wave order.

    5. **Remove compatibility layers only after all consumers are migrated.**
       This is a separate, explicit phase — never combined with consumer migration.

    6. **Remove old version only after compatibility layers are removed.**
       This is the final phase.

    ### Standard Phase Templates

    **Dependency major version upgrade:**
    1. Add new version alongside old (feature mode)
    2. Add compatibility adapters (feature mode)
    3a-3N. Migrate consumer waves (refactor mode, one phase per wave)
    4. Remove compatibility adapters (refactor mode)
    5. Remove old version (refactor mode)

    **API deprecation removal:**
    1. Identify and document all callers (analysis — already done)
    2a-2N. Update caller waves to use replacement API (refactor mode)
    3. Remove deprecated API (refactor mode)

    **Framework upgrade (e.g., React Router v5 to v6):**
    1. Add new framework version alongside old (feature mode)
    2. Add compatibility/coexistence layer (feature mode)
    3a-3N. Migrate component/route waves (refactor mode)
    4. Remove compatibility layer (refactor mode)
    5. Remove old framework version (refactor mode)

    Adapt the template to the specific migration. Not all migrations need
    compatibility layers (simple rename migrations may skip phases 2 and 4).

    ### Output Format

    Write to [SCRATCH_DIR]/phase-plan.md:

    ## Migration Phase Plan: [target description]

    ### Phase [N]: [Description]
    - **Build mode:** feature | refactor
    - **Affected files:** [list of files or "files matching pattern X"]
    - **Affected repos:** [list if cross-repo, or "current repo only"]
    - **Estimated effort:** Low | Medium | High
    - **Dependencies:** Phase N-1 (or "none" for Phase 1)
    - **Safe stopping point verification:**
      - [ ] Codebase compiles
      - [ ] All existing tests pass
      - [ ] [Phase-specific verification criterion]
    - **Description:** [What this phase does and why it's a separate phase]

    ### Compatibility Layer Needed?
    - **Yes/No:** [determination]
    - **Reason:** [why or why not]

    ### Legacy Migration Pattern Checklist

    After structuring the phases, verify the plan against these operational
    patterns. Flag any violations in a "Pattern Compliance" section at the
    end of the phase plan.

    1. **Map the territory:** Are there operational unknowns (manual processes,
       workarounds, tribal knowledge) that the technical analysis didn't
       capture? Flag them as risks requiring user confirmation before cutover.
    2. **Build alongside:** Does the plan include a coexistence period where
       old and new systems run in parallel? If not, justify why hard cutover
       is acceptable.
    3. **Cut over by group:** Do consumer migration waves (Phase 3a-3N) map
       to user groups or teams, not just code modules? If applicable, identify
       rollout groups.
    4. **Don't migrate data unless you must:** Are any phases flagged as data
       migration? If so, verify the migration is genuinely required — not just
       assumed. Flag data migration phases as high-risk.
    5. **Kill the old system:** Does the plan include an explicit decommission
       step as the final phase? Include criteria for when decommission triggers
       (last user migrated, parallel period complete).

    ## Rules

    - Every phase must satisfy the safe stopping point invariant
    - Each phase specifies its build mode (feature for additive, refactor
      for restructuring)
    - Consumer migration must be broken into waves using the dependency
      graph from the blast radius analysis
    - If the migration analysis shows <5 consumers and all are independent,
      a single consumer migration phase is acceptable
    - Phase effort estimates should account for the number of affected files
      and the complexity of changes per file
    - If the blast radius includes cross-repo consumers, note which phases
      require cross-repo coordination
```
