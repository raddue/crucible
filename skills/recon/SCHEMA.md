# Brief Schema Stability

The Investigation Brief is consumed by 6+ skills. Section headers are the contract surface — consumers parse by header to extract relevant sections.

**Stable (changing requires updating all consumer templates):**
- Brief metadata fields: `Brief version`, `Task`, `Scope`, `Depth modules`, `Cartographer state`, `Commit`
- Core section headers: `## Project Structure`, `## Existing Patterns`, `## Scope Boundaries`, `## Prior Art`, `## Conflicts`

**Semi-stable (additive, consumers opt-in):**
- `## Open Questions` — present when scouts report unknowns. Consumers that need it parse for it; consumers that don't can ignore it. Not yet validated by consumer integration — promoted to stable once 2+ consumers confirm they consume it.

**Semi-stable (consumers that request specific modules depend on these):**
- Depth module section headers: `## Impact Analysis`, `## Consumer Registry`, `## Friction Scan`, `## Subsystem Manifest`, `## Diagnostic Context`, `## Execution Readiness`
- Execution Readiness structured subfields: `Test command`, `Lint command`, `CI checks`, `Manual verification` — parsed by `/build`, must not be renamed without updating consumers

**Unstable (internal content, not parsed by header):**
- Content within sections — formatting, subheadings, bullet structure may evolve

**Process:** Any change to a stable or semi-stable header is a breaking change. The PR must update all consumer skill templates that reference the changed header. Adding new depth modules is non-breaking.
