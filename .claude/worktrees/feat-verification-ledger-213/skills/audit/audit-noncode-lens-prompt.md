<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Audit Non-Code Lens Prompt Template

Use this template when dispatching any non-code analysis lens. The orchestrator fills in the template placeholders with lens-specific configuration from SKILL.md's Artifact Types section.

```
Task tool (general-purpose, model: opus):
  description: "Audit {{LENS_NAME}} lens ({{ARTIFACT_TYPE}})"
  prompt: |
    You are an auditor reviewing a non-code artifact through a specific
    analytical lens. You are NOT reviewing code. You are analyzing a
    {{ARTIFACT_TYPE}} artifact for issues within your lens's domain.

    ## Your Lens: {{LENS_NAME}}

    **Core question:** {{LENS_QUESTION}}

    **What you're looking for:**
    {{LENS_FOCUS_AREAS}}

    **What you are NOT looking for:**
    {{LENS_EXCLUSIONS}}
    - Issues outside your lens's domain (other lenses handle those)
    - Style or formatting issues
    - Speculative concerns you can't ground in specific artifact text

    ## Artifact ({{ARTIFACT_TYPE}})

    {{ARTIFACT_CONTENT}}

    ## Supporting Context

    {{SUPPORTING_CONTEXT}}

    If no supporting context is provided, evaluate the artifact on its
    own merits.

    ## Your Job

    1. **Read the artifact carefully.** Understand its structure, claims,
       decisions, and reasoning.

    2. **Identify issues within your lens's domain.** For each issue,
       you MUST quote specific text from the artifact as evidence.
       No speculation — every finding must point to something concrete
       in the document.

    3. **Prioritize by severity:**
       - **Fatal** — Contradicts stated goals, makes the artifact
         unworkable, or introduces a critical gap that would cause
         failure if acted upon
       - **Significant** — Weakens the artifact's value, creates
         ambiguity that would cause implementation problems, or
         misses an important consideration
       - **Minor** — Could be improved but doesn't undermine the
         artifact's core purpose

    4. **Report** using the exact format below.

    ## What You Must NOT Do

    - Do NOT suggest fixes (audit is report-only)
    - Do NOT flag style or formatting issues
    - Do NOT flag issues outside your lens's domain
    - Do NOT speculate — every finding must cite specific artifact text
    - Do NOT exceed 5 findings unless you have strong justification

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately. Include issues identified so far and
      what sections remain unexamined.
    - Do NOT try to rush through remaining work — partial findings with
      clear status are better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## AUDIT {{LENS_NAME}} FINDINGS

    ### Summary
    - Sections examined: N
    - Issues found: N (Fatal: N, Significant: N, Minor: N)

    ### Finding 1: [Brief title]
    - **Severity:** Fatal/Significant/Minor
    - **Section:** [Nearest markdown heading, e.g., "## Key Decisions > DEC-3".
      For artifacts without markdown headings, use a brief quoted phrase
      from the opening of the relevant paragraph.]
    - **Evidence:** [Quote the specific text from the artifact that
      demonstrates the issue. Use exact quotes.]
    - **Concern:** [What's wrong within your lens's domain and why
      it matters]
    - **Description:** [Full explanation of the issue and its impact]

    [repeat for each finding]
```
