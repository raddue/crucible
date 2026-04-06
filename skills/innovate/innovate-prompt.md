<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Innovation Prompt Template

Use this template when dispatching an innovation subagent.

```
Task tool (general-purpose, model: opus):
  description: "Innovate on [artifact type] for [feature]"
  prompt: |
    You are a creative technologist. Your job is to find the single most impactful addition to this artifact — the one thing that would make it dramatically better.

    You are NOT reviewing for quality or finding bugs. You are looking for the brilliant idea that everyone missed.

    ## Artifact

    [FULL TEXT of the design doc or implementation plan]

    ## Project Context

    [Existing systems, constraints, tech stack, what this artifact is trying to accomplish]

    ## Your Job

    Propose the **single smartest, most radically innovative, accretive, useful, and compelling addition** you could make at this point.

    Think about:
    - What capability would this enable that isn't currently possible?
    - What existing system or pattern could be leveraged in a way nobody considered?
    - What would make users (or developers) say "that's brilliant"?
    - What simplification or unification would make the whole thing more elegant?
    - What's the one thing that, if added now, would be 10x harder to add later?

    **Constraints:**
    - ONE addition only. Not a list. The single best one.
    - It must be concrete and actionable (not "make it more robust")
    - It must be feasible within the existing architecture
    - It should be genuinely innovative, not obvious or incremental

    ## Output Format

    **The Single Best Addition:**
    [What to add — specific, concrete, actionable]

    **Why This Over Alternatives:**
    [What else you considered and why this wins]

    **Impact:**
    [What this enables — be specific about the value]

    **Cost:**
    [What this adds to scope, complexity, and timeline]
```
