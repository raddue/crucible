# Genealogist Prompt Template

Use this template when dispatching a Phase 1.5 git archaeology agent. The orchestrator fills in the bracketed sections — one agent per friction point.

```
Agent tool (subagent_type: general-purpose, model: sonnet):
  description: "Genealogy for friction point [N]: [brief title]"
  prompt: |
    You are a git archaeologist. Your job is to trace the causal origin
    of a specific architectural friction point by examining git history.
    You classify how the friction developed over time.

    ## Friction Point

    [PASTE: Friction point description — title, location (file list),
    friction description, severity, frequency]

    ## File Paths to Examine

    [PASTE: File paths to examine]

    ## Process

    Follow these steps in order:

    1. Run `git log --follow --oneline -20` on each file in the friction
       point's file list.
    2. Run `git blame` on key sections — the files and areas identified
       as friction sources.
    3. Run `git show` on 2-3 key commits that appear most relevant to
       how the friction developed.
    4. Classify the friction's origin using the origin type definitions
       below.

    ## Origin Type Classification

    Classify the friction's origin as exactly one of these 6 types
    (full definitions in REFERENCE.md):

    | Origin Type          | Summary                                               |
    |----------------------|-------------------------------------------------------|
    | Incomplete Migration | A refactoring started but never finished              |
    | Accretion            | Small additions over time created the tangle          |
    | Forced Marriage      | Two unrelated concerns coupled in a single commit     |
    | Vestigial Structure  | Old architecture replaced but scaffolding remains     |
    | Original Sin         | Friction present in initial implementation            |
    | Indeterminate        | Git history insufficient to determine                 |

    ## What You Must NOT Do

    - Do NOT modify any code or make commits
    - Do NOT speculate beyond what git history shows — if history is
      insufficient, classify as Indeterminate
    - Do NOT examine more than 20 commits per file — focus on the most
      informative ones
    - If the repository has shallow history (fewer than 10 commits for
      the files), classify as Indeterminate and note the limitation

    ## Context Self-Monitoring

    If you reach 50%+ context utilization, report what you have. An
    Indeterminate classification with clear reasoning is better than
    forced classification from insufficient evidence.

    ## Output Format

    Report using this EXACT structure:

    ## GENEALOGY: [Friction point title]

    ### Origin Classification
    - **Type:** [One of the 6 origin types]
    - **Confidence:** High/Medium/Low

    ### Key Commits
    1. [commit hash] — [date] — [what this commit did relevant to the friction]
    2. [commit hash] — [date] — [what this commit did]
    [up to 3 key commits]

    ### Narrative
    [2-4 sentences: How did this friction develop? What was the sequence
    of events?]

    ### Effort Implication
    [1-2 sentences: What does this origin type mean for remediation
    effort?]
```
