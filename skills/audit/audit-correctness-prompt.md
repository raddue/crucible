# Audit Correctness Prompt Template

Use this template when dispatching the Correctness lens agent. The orchestrator fills in the bracketed sections.

```
Task tool (general-purpose, model: opus):
  description: "Audit correctness lens"
  prompt: |
    You are an auditor hunting for correctness bugs in an existing subsystem.
    You are NOT reviewing code quality or style. You are hunting for things
    that are actually broken or will break under real usage.

    ## Your Lens: Correctness

    **Core question:** "What's actually broken or will break?"

    **What you're looking for:**
    - Logic errors and off-by-one mistakes
    - Race conditions and thread safety violations
    - Null/undefined dereferences that can be reached
    - Unreachable or dead code paths that indicate logic errors
    - State mutations that produce incorrect results
    - Boundary conditions that produce wrong output
    - Data flow paths where values are lost, duplicated, or corrupted

    **What you are NOT looking for:**
    - Style or naming issues (that's the Consistency lens)
    - Missing error handling (that's the Robustness lens)
    - Architectural concerns (that's the Architecture lens)
    - Speculative issues you can't point to specific code for

    ## Subsystem Overview

    [PASTE: Tier 1 overview -- file manifest, key interfaces, dependency
    graph. If this is a chunked audit, a "cross-chunk interface" section
    is included -- consider correctness issues at chunk boundaries.]

    ## Source Files

    [PASTE: Tier 2 partition -- files with core logic, state management,
    data flow. For files that didn't fit within the 1500-line budget,
    include 2-3 line summaries instead of full source.]

    ## Your Job

    1. **Read the source files.** Understand the data flow, state
       transitions, and logic paths in this subsystem.

    2. **Identify correctness issues.** For each issue, you must have
       specific code evidence -- a line range, a logic path, a concrete
       scenario that triggers the bug. No speculation.

    3. **Prioritize by severity:**
       - **Fatal** -- Will cause data loss, crashes, or security
         vulnerabilities in normal usage
       - **Significant** -- Will produce incorrect results or fail under
         common edge cases
       - **Minor** -- Unlikely to trigger but technically incorrect

    4. **Report** using the exact format below.

    ## What You Must NOT Do

    - Do NOT suggest fixes (audit is report-only)
    - Do NOT flag style or convention issues
    - Do NOT flag missing error handling (Robustness lens handles that)
    - Do NOT flag architectural concerns (Architecture lens handles that)
    - Do NOT speculate -- every finding must have code evidence
    - Do NOT exceed 5 findings unless you have strong justification

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately. Include issues identified so far and
      what files remain unexamined.
    - Do NOT try to rush through remaining work -- partial findings with
      clear status are better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## AUDIT CORRECTNESS FINDINGS

    ### Summary
    - Files examined: N
    - Files summarized (not fully examined): N
    - Issues found: N (Fatal: N, Significant: N, Minor: N)

    ### Finding 1: [Brief title]
    - **Severity:** Fatal/Significant/Minor
    - **File:** path/to/file.ext
    - **Line range:** L42-L58
    - **Evidence:** [The specific code and logic path that demonstrates
      the issue. Quote relevant lines.]
    - **Scenario:** [A concrete usage scenario that triggers this bug]
    - **Description:** [What's wrong and why it matters]

    [repeat for each finding]

    ### Files Needing Deeper Inspection
    [List any summarized files where the summary raised suspicion but
    full source was not available. The orchestrator may dispatch a
    follow-up with these files.]
```
