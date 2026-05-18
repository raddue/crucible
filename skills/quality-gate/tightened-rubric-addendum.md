# Tightened-Rubric Addendum

This addendum is concatenated to `red-team-prompt.md` body by the quality-gate orchestrator **before Task dispatch**, conditional on either:

1. **Look-harder verification** (Component 1) — first clean round of a chunk gets a same-model re-dispatch under tightened rubric to guard against false-positive PASS verdicts.
2. **Tail-rubric** (Component 2) — once `suppression_threshold ≥ 5` AND LOCAL round ≥ `ceil(suppression_threshold * 0.6)`, every red-team dispatch carries this addendum to suppress late-round severity inflation.

The addendum is the **single source of truth** for tightened-rubric semantics. Both mechanisms reference this file; do not fork the content.

## Apply this addendum to your review

The standard severity rubric in `red-team-prompt.md` still applies. The clauses below **tighten** it without replacing it. Where the standard rubric and this addendum diverge, the addendum governs for Significant and Fatal severity assignment.

### 1. Tightened severity rubric — every Significant requires a concrete failure scenario

Every Significant finding MUST include a **concrete failure scenario** of the form:

> "If [user/condition] does [action] under [state], then [observable failure] occurs, leading to [downstream impact]."

Generic phrasings — "an implementer might be confused", "this could be unclear to future readers", "a reader might misinterpret", "this could lead to bugs in some cases" — are demoted to **Minor**. They are not Significant findings. A Significant finding earns its severity by naming a real failure path; a hand-wave does not.

### 2. Per-finding round-justification check

For each Fatal or Significant finding, affirmatively answer this question in your own head before listing it:

> **"Would this finding alone justify continuing the gate for another round?"**

If the answer is "no" or "probably not", the finding is **demoted to Minor** or dropped. The round-justification check is not aspirational — it is the test that distinguishes a real Significant from an inflated Minor. The convergence tail is precisely where this check matters most.

### 3. Empty receipts are not acceptable

Produce per-dimension justification for cleanliness or surface issues. A receipt that says only "Looks clean" or "No issues found" is **not acceptable** — you must affirmatively name what you checked and why each dimension is clean (or flag the surface issue if it isn't).

Empty receipts mask "I didn't actually look" as "I looked and found nothing." The distinction matters. If you genuinely found nothing on a dimension, say *what you checked* on that dimension and why nothing rose to a finding.

### 4. Anti-rationalization clause

> **Demote freely when the failure scenario is speculative.**

A genuine finding earns its severity by naming a real failure path. An inflated finding costs the user real fix time — and worse, it teaches the convergence loop that any-finding-is-good-enough, which corrodes the gate's signal value over multiple rounds.

Reviewers reading this addendum in the convergence tail (round 6+ on threshold-10 gates, round 4+ on threshold-6, round 3+ on threshold-5) should expect to demote more findings than they would have under the standard rubric. That is the intended behavior of this addendum, not a failure mode.

### 5. Anti-undergrade safety — the undergrade check still applies

The existing **undergrade check** from the standard rubric ("Would I be comfortable shipping this if I own the pager?") still applies in full force. The tightening above suppresses *inflated* findings; it does not suppress *real* findings.

If a finding fails the undergrade check — i.e., shipping the artifact as-is would credibly result in pager pain — it is **promoted to Fatal** regardless of whether you can articulate a concrete-scenario in the format above. The undergrade check overrides the concrete-scenario requirement when it fires.

In other words: this addendum tightens the floor on Significant (concrete-scenario required) without lowering the ceiling on Fatal (undergrade check still promotes).

## Anti-anchoring preservation

This addendum **must not** reference prior rounds, prior reviewers, fixes already attempted, or that any prior review found 0F/0S. You see the artifact as if it is the first review. The orchestrator concatenates this addendum without leaking prior-round context; you should treat the dispatched prompt as the entire scope of context for the review.

The addendum tightens **what counts as a Significant**, not **what you already know about the artifact**.
