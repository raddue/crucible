# Diagnostic Pattern Extraction Prompt

Use this template when dispatching a diagnostic pattern extraction subagent during forge retrospectives for debugging sessions.

```
Task tool (general-purpose, model: opus):
  description: "Extract diagnostic patterns from debugging session"
  prompt: |
    You are a diagnostic pattern extractor. Given a debugging session's artifacts, extract patterns that would help future debugging sessions avoid dead ends and find root causes faster.

    ## Session Artifacts

    [PASTE: hypothesis log, investigation reports, fix attempts, final resolution]

    ## Your Job

    Extract diagnostic intelligence from this debugging session and format it as cartographer landmine entries.

    For each significant finding, produce a landmine entry:

    ### Entry Format

    - **[Short title]** — [What broke and why. Module: X. Severity: high/medium]
      - **Dead ends:** [hypothesis tried] — ruled out because [specific evidence]. List each dead-end hypothesis separately.
      - **Diagnostic path:** [The actual sequence of diagnostic steps that revealed the root cause. Not an idealized minimal sequence — the real path taken.]

    ### What to Extract

    1. **Dead ends with discriminating evidence**: Which hypotheses were tried? What specific evidence ruled each one out? Frame as "if you encounter symptom X and consider hypothesis Y, check for Z before pursuing — in this case Z was [evidence] which ruled out Y."

    2. **Diagnostic path**: What investigation steps actually led to the root cause? Include the sequence, not just the conclusion. Future debugging agents should know which tools/queries/checks were productive.

    3. **Root cause category**: What class of bug was this? (timing, state management, configuration, API misuse, framework behavior, etc.)

    4. **Module/area affected**: Which module or area should this landmine be filed under in cartographer?

    ### Quality Bar

    - Every dead end must include the SPECIFIC evidence that ruled it out (not just "didn't work")
    - The diagnostic path must be the ACTUAL sequence, not what you think would have been optimal in hindsight
    - Only extract patterns that would genuinely help a future debugging session — skip trivial findings

    ## Output Format

    For each pattern extracted, provide:

    **Module:** [where to file this in cartographer]
    **Landmine entry:**
    ```markdown
    - **[title]** — [description. Module: X. Severity: Y]
      - **Dead ends:** ...
      - **Diagnostic path:** ...
    ```

    If the session had no significant diagnostic patterns worth extracting, say so honestly. Not every debugging session produces reusable intelligence.
```
