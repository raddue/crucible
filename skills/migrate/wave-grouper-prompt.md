# Wave Grouper Prompt Template

Use this template when dispatching the Consumer Wave Grouper agent in Phase 5.

```
Task tool (model: sonnet):
  description: "Group consumers into migration waves: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are grouping consumers into migration waves — ordered batches where
    all consumers in a wave can be migrated independently and in parallel.

    ## Consumer Registry

    [CONSUMER_REGISTRY — paste the consumer registry from blast-radius.md]

    ## Phase Plan

    [PHASE_PLAN — paste contents of phase-plan.md]

    ## Your Job

    Assign every consumer to a wave using topological sort on the consumer
    dependency graph.

    ### Algorithm

    1. **Build the dependency graph:**
       - From the consumer registry, extract consumer-to-consumer dependencies
       - Consumer A depends on consumer B if:
         a. A imports B, AND
         b. B uses the old API (so B must be migrated before A can safely
            work with the new API)
       - If A imports B but B does NOT use the old API, there is no migration
         dependency (A does not depend on B for wave ordering)

    2. **Topological sort:**
       - Wave 1: consumers with NO dependencies on other consumers
         (leaf nodes in the dependency graph)
       - Wave 2: consumers whose dependencies are ALL in Wave 1
       - Wave 3: consumers whose dependencies are ALL in Waves 1-2
       - Continue until all consumers are assigned

    3. **Independence verification:**
       - Within each wave, verify NO consumer depends on another consumer
         in the same wave
       - If a circular dependency is found within a wave: flag it and escalate
         to the orchestrator. Circular dependencies cannot be auto-resolved.

    4. **Cross-repo grouping (if applicable):**
       - Group consumers by repository within each wave
       - Each repo within a wave can be migrated independently
       - Note any cross-repo dependencies that constrain wave ordering

    ### Output Format

    Write to [SCRATCH_DIR]/wave-plan.md:

    ## Consumer Wave Plan

    ### Wave [N]
    **Consumers:** [count]
    **Independence verified:** yes | no (with explanation)
    **Estimated effort:** [sum of consumer migration complexities]

    | Consumer | Repo | Complexity | Breaking Changes |
    |----------|------|------------|-----------------|
    | path/to/file.ts | current | low | renamed API only |
    | path/to/other.ts | current | medium | signature change |
    | org/other-repo | other-repo | high | behavioral change |

    ### Dependency Graph Summary
    - Total consumers: N
    - Total waves: M
    - Longest dependency chain: K waves
    - Circular dependencies: none | [list]

    ### Cross-Repo Coordination (if applicable)
    - Repos involved: [list]
    - Wave [N] requires coordination between: [repos]
    - CI pipeline considerations: [any cross-repo CI dependencies]

    ## Rules

    - Every consumer from the registry must appear in exactly one wave
    - Wave 1 must contain only consumers with no dependencies
    - A consumer's wave number must be strictly greater than all of its
      dependencies' wave numbers
    - If all consumers are independent, a single wave is acceptable
    - For cross-repo migrations: consumers in different repos are independent
      unless the pathfinder topology shows a direct dependency between them
    - Flag any consumer that appears in the registry but has no usage_pattern
      — it may be a false positive from the blast radius scan
    - Prefer fewer, larger waves over many small waves (reduces phase count
      and overhead), as long as independence is maintained
```
