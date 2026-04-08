<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Blast Radius Mapper Prompt Template

Use this template when dispatching the Blast Radius Mapper agent in Phase 2.

```
Agent tool (subagent_type: general-purpose, model: sonnet):
  description: "Map blast radius for migration: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are mapping the blast radius of a migration — every file, module,
    and consumer that will be affected by the changes.

    ## Migration Analysis

    [MIGRATION_ANALYSIS — paste contents of migration-analysis.md from Phase 1]

    ## Cartographer Context

    [CARTOGRAPHER_MODULE_DATA if available, or "No cartographer data available"]

    ## Recon Consumer Registry

    [CONSUMER_REGISTRY — consumer registry from /recon's consumer-registry depth
    module, if available. Contains pre-discovered direct consumers with usage
    patterns and migration complexity. If "No consumer registry available", perform
    full direct consumer discovery in Step 1.]

    ## Your Job

    Map every consumer of the APIs being migrated. Be exhaustive — a missed
    consumer causes a runtime failure after migration.

    ### Step 1: Consumer Discovery and Augmentation

    For each breaking change in the migration analysis:

    **If consumer registry is available from recon:**
    1. **Verify the registry** — spot-check 3-5 consumers from the registry to
       confirm they still reference the old API (registry may be from a cached
       recon run)
    2. **Augment with missed consumers** — search for any direct consumers NOT
       in the registry (grep/glob for imports, function calls, type references,
       and configuration references to the old API that recon missed)
    3. **Trace indirect dependents** — for each direct consumer (from registry +
       newly discovered), check if other code depends on it
    4. **Map test coverage** — which test files exercise the affected code paths?
    5. **Check configuration/wiring** — DI registrations, config files, build
       scripts, CI pipelines that reference the target

    **If NO consumer registry available (recon failed):**
    1. **Search for direct consumers** — grep/glob for imports, function calls,
       type references, and configuration references to the old API
    2. **Trace indirect dependents** — for each direct consumer, check if other
       code depends on it (imports it, calls it, extends it)
    3. **Map test coverage** — which test files exercise the affected code paths?
       Look for test files that import or reference the migration target
    4. **Check configuration/wiring** — DI registrations, config files, build
       scripts, CI pipelines that reference the target

    ### Step 2: Consumer Registry

    Write the complete consumer registry to [SCRATCH_DIR]/blast-radius.md.

    #### Impact Manifest

    **Target:** [what's being migrated]
    **Direct consumers:** N files
    **Indirect dependents:** N files
    **Test coverage:** N test files
    **Configuration references:** N files
    **Cross-repo consumers:** N repos (or "not mapped")

    #### Consumer Registry

    For each consumer, one entry:

    - **consumer:** <file path or org/repo>
      **usage_pattern:** "calls TargetClass.method(args)" or "imports X from Y"
      **breaking_change:** [which breaking change from the analysis affects this consumer]
      **migration_complexity:** low | medium | high
      **independent:** true | false
      **reason_if_dependent:** "shares state with <other consumer>" (only if not independent)

    #### Dependency Graph

    List consumer-to-consumer dependencies (consumer A depends on consumer B):
    - [consumer A] -> [consumer B]: [reason]

    This graph is used by the Wave Grouper to assign consumers to waves.

    ## Rules

    - Search the actual codebase — do not speculate about consumers
    - Every consumer entry must include a specific file path and usage pattern
    - If a consumer uses multiple affected APIs, list each usage separately
    - Independence means: migrating this consumer does not require migrating
      any other consumer first. If consumer A imports consumer B, and consumer B
      uses the old API, then A depends on B (A is not independent)
    - Err on the side of marking consumers as dependent rather than independent
      — a missed dependency causes a broken intermediate state
```
