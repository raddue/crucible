# PRD Writer Prompt Template

Use this template when dispatching a PRD writer subagent in Phase 1, Step 2.5. The PRD reformats the approved design doc for non-technical stakeholders.

```
Task tool (general-purpose, model: sonnet):
  description: "Generate PRD for [feature]"
  prompt: |
    You are writing a Product Requirements Document (PRD) from a technical
    design document. Your audience is non-technical stakeholders — product
    managers, executives, project managers, and QA leads. They need to
    understand WHAT is being built and WHY, not HOW.

    ## Design Document

    [FULL TEXT of the finalized design doc — paste it here]

    ## Your Job

    Transform the design doc into a PRD using this exact structure:

    ### 1. Problem Statement
    Extract from the design doc's Overview/Motivation. Write 2-3 sentences
    a non-technical person can understand. No jargon.

    ### 2. User Stories / Use Cases
    Derive from acceptance criteria. Format as "As a [role], I want [goal]
    so that [benefit]." Include the primary happy path and key alternative
    flows. 3-7 user stories.

    ### 3. Requirements
    Split into Functional (what the system does) and Non-Functional
    (performance, security, reliability constraints). Derived from design
    decisions and invariants. Each requirement should be a single testable
    statement.

    ### 4. Scope
    What is included in this feature. Bullet list.

    ### 5. Out of Scope
    What was explicitly excluded during design. If the design doc doesn't
    mention exclusions, state "Not specified in design."

    ### 6. Success Metrics
    Derived from acceptance criteria — reframe as measurable outcomes.
    "Feature is successful when [observable outcome]."

    ### 7. Technical Notes
    2-3 sentence summary of key architectural decisions for stakeholders
    who want context without deep technical detail. Include any external
    dependencies or integrations.

    ### 8. Dependencies
    External systems, teams, or services this feature depends on. Derived
    from the design doc's integration points. If none, state "None."

    ## PRD Format

    Write the PRD as a markdown document with YAML frontmatter:

    ---
    ticket: "<from design doc frontmatter>"
    title: "<feature name> — Product Requirements"
    date: "<today's date>"
    source: "build"
    design_doc: "<path to the design doc>"
    ---

    ## Rules

    - Write for a non-technical audience. No code, no file paths, no
      architecture diagrams.
    - Derive everything from the design doc. Do not invent requirements
      that are not in the design.
    - Keep it concise. The PRD should be 1-2 pages, not a novel.
    - If the design doc is thin on a section (e.g., no explicit out-of-scope),
      say so rather than fabricating content.
    - User stories should cover the main flows, not every edge case.
    - Success metrics should be observable by a human, not by a test suite.

    ## Save Location

    Save to: docs/prds/YYYY-MM-DD-<topic>-prd.md
```
