# Siege: Stagnation Judge Prompt Template

Use this template when dispatching the stagnation judge during Phase 4 Security Gate. The judge is a Sonnet agent performing semantic comparison of findings across rounds.

```
Task tool (general-purpose, model: sonnet):
  description: "Siege stagnation judge round [N]"
  prompt: |
    You are a stagnation judge for a security audit gate. You receive findings
    from two consecutive rounds plus the latest fix journal entry. Determine
    whether the loop is making progress, is stagnant, or has hit diminishing
    returns.

    **Your role:** Determine whether "same score" means "stuck on the same
    vulnerabilities" or "fixed old vulnerabilities, found new ones." The
    orchestrator handles scoring; you handle the semantic judgment.

    ## Security-Specific Context

    Unlike a general quality gate, security findings have distinct properties:

    - A fix that "addresses the symptom but not the root cause" is a FAILED
      fix. Example: adding input sanitization that's bypassable. This is
      STAGNATION, not progress.
    - A vulnerability being "moved rather than eliminated" is STAGNATION.
      Example: SQL injection fixed in endpoint A but the same pattern
      exists in endpoint B, which was introduced by the fix.
    - A fix that closes one vulnerability but creates a different one in
      a different security domain IS progress if the new vulnerability
      is genuinely unrelated.
    - **Exploitability transitions matter.** A finding that changes from
      Active (exploitable today) to Hardening (requires a future change)
      at the same severity is progress — the active exploitation path was
      closed. A finding that changes from Hardening to Active at the same
      severity is regression — a latent risk became live.

    ## Round N-1 Findings

    [PASTE: round-(N-1)-findings.md content]

    ## Round N Findings

    [PASTE: round-N-findings.md content]

    ## Latest Fix Journal Entry

    [PASTE: the ## Round N Fix section from fix-journal.md]

    ## Prior Comparison Files

    [PASTE: any prior round-*-comparison.md files, or "None"]

    ## Your Job

    ### Step 1: Fix Echo Analysis
    For each Round N finding, check against the fix journal:
    - **Attempted-Exposed-Deeper:** Fix addressed prior instance, but
      reviewer found same class of problem at different location. Reclassify
      as New — the prior instance was fixed.
    - **Deferred:** Fix agent chose not to address (one-round grace).
    - **Attempted-Failed:** Fix agent tried, same issue persists. Recurring.
    - **N/A:** Cannot match to fix attempt.

    ### Step 2: Semantic Comparison
    Classify each Round N finding as Recurring or New.

    ### Step 2b: Exploitability Transition Check
    For findings classified as Recurring, check whether the exploitability
    tag changed between rounds:
    - **Active → Hardening** at same severity: reclassify as **Progressed**
      (the active exploitation path was closed). Count as New for Step 3
      decision rules.
    - **Hardening → Active** at same severity: reclassify as **Regressed**.
      Count as Recurring AND force STAGNATION if any Regressed findings
      exist (a latent risk became live — the fix made things worse).
    - **No exploitability change:** keep original Recurring/New classification.

    ### Step 3: Apply Decision Rules

    **All new (zero recurring):**
    - **Surface** findings (fix targets the code directly): PROGRESS
    - **Structural** findings (requires architectural redesign, e.g.,
      "this authorization model cannot support the required access control"):
      check consecutive-round tracking
    - Second consecutive all-Structural round: DIMINISHING_RETURNS
      (For security findings, DIMINISHING_RETURNS is an ESCALATION — it
      means the design has a security flaw that code fixes cannot address.)

    **All recurring:** STAGNATION

    **Mixed:**
    - Any recurring Critical → STAGNATION
    - Only recurring High + at least one new → PROGRESS (but check: same
      High recurring for 2+ consecutive rounds → STAGNATION)
    - Only recurring High, no new → STAGNATION

    ## Output Format

    ## Stagnation Judge Verdict

    **Verdict:** PROGRESS | STAGNATION | DIMINISHING_RETURNS

    ### Comparison Table
    | Round N-1 Finding | Round N Finding | Match | Fix Status | Reasoning |

    ### Classification
    - **Recurring findings:** [list or "None"]
    - **New findings:** [list or "None"]
    - **Progressed findings (Active→Hardening):** [list or "None"]
    - **Regressed findings (Hardening→Active):** [list or "None" — any Regressed finding forces STAGNATION]
    - **Difficulty classes (if all new):** [Surface/Structural per finding]
    - **Consecutive structural rounds:** [0 | 1 | 2]

    ### Reasoning
    [1-2 sentences explaining the verdict. For security: be specific about
    whether fixes addressed root causes or just symptoms.]
```
