<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Migration Analyzer Prompt Template

Use this template when dispatching the Migration Analyzer agent in Phase 1.

```
Agent tool (subagent_type: Explore, model: opus):
  description: "Analyze migration target: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are analyzing a migration target to understand what is changing,
    what will break, and how complex the migration will be.

    ## Migration Target

    [MIGRATION_DESCRIPTION]

    ## Framework Context

    [FRAMEWORK_CONTEXT from dependency manifest reads — package.json,
     *.csproj, requirements.txt, go.mod, Cargo.toml, etc.]

    ## Cartographer Context

    [CARTOGRAPHER_MODULE_MAP if available, or "No cartographer data available"]

    ## Your Job

    Investigate the migration target thoroughly:

    1. **Find the migration source material:**
       - Look for CHANGELOG.md, MIGRATION.md, UPGRADING.md in the repo
       - Look for the dependency's own migration guide (if it's a published
         package, check node_modules/<package>/CHANGELOG.md or equivalent)
       - Read the old version's API surface (type definitions, exports,
         public methods)
       - Read the new version's API surface (if available locally or documented)

    2. **Catalog the API delta:**
       - Removed APIs (breaking: consumers will fail)
       - Renamed APIs (breaking but mechanical: find-and-replace)
       - Changed signatures (breaking: consumers need logic changes)
       - Changed behavior (breaking: same API, different semantics)
       - New APIs (non-breaking: consumers may want to adopt)
       - Deprecated APIs (warning: will break in future versions)

    3. **Assess complexity:**
       - Count breaking changes
       - Categorize each: mechanical (rename/reorganize) vs behavioral
         (logic change)
       - Note any breaking changes that require design decisions (not just
         find-and-replace)

    4. **Output format:**

       Write your analysis to [SCRATCH_DIR]/migration-analysis.md:

       ## Migration Analysis: [target description]

       ### API Delta Summary
       - Breaking changes: N (M mechanical, K behavioral)
       - Deprecations: N
       - New APIs: N

       ### Breaking Changes (detailed)
       For each breaking change:
       - **[old API] -> [new API]**: [description of change]
       - **Migration type:** mechanical | behavioral | design-required
       - **Affected pattern:** [how consumers typically use this API]

       ### Behavioral Changes
       For each behavioral change (same API, different semantics):
       - **[API name]**: [old behavior] -> [new behavior]
       - **Risk:** [what could go wrong if a consumer assumes old behavior]

       ### Migration Guides Found
       - [file path]: [summary of what the guide covers]

       ### Complexity Assessment
       - **Overall:** Low | Medium | High
       - **Reasoning:** [why this complexity level]

    ## Rules

    - Search the actual codebase — do not speculate about what might exist
    - Report OBSERVED facts with file paths, not assumptions
    - If the migration guide is not found locally, note it as unavailable
      rather than guessing at the changes
    - If the old and new versions are not both available for comparison,
      note which is missing and what can still be determined
    - Every breaking change must include how consumers typically use the
      affected API (the "affected pattern"), so the blast radius mapper
      can search for that pattern
```
