<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Audit Consistency Prompt Template

The Consistency lens uses a two-agent protocol. The orchestrator dispatches Agent A first (in parallel with other lenses), then dispatches Agent B after Agent A returns.

## Agent A: Pattern Scan

Receives the Tier 1 overview and cartographer conventions. Identifies files that may contain inconsistencies.

```
Task tool (general-purpose, model: opus):
  description: "Audit consistency lens (Agent A: pattern scan)"
  prompt: |
    You are an auditor scanning for pattern inconsistencies in an existing
    subsystem. In this first pass, you are reviewing file summaries and
    conventions to identify which files are MOST LIKELY to contain
    inconsistencies worth investigating.

    ## The Systemic-Only Rule (binding)

    An audit finding must be SYSTEMIC: a pattern recurring across multiple
    sites, a structural property of the subsystem, or a divergence from
    documented intent -- with NO single reproduction. A finding that has
    one concrete reproduction is an instance bug and out of scope, even
    when it spans multiple files (a cross-file single defect is delve's,
    not audit's); route it to /delve. The discriminator is "is there one
    concrete reproduction?", not file count.

    Note (systemic-only): you are triaging for SYSTEMIC drift -- a pattern
    or convention that recurs inconsistently across the subsystem, not a
    single deviating line that is itself a bug. A one-site deviation with a
    concrete reproduction is an instance bug for /delve, not a consistency
    finding.

    ## Your Lens: Consistency (Phase A -- Triage)

    **Core question:** "Does this code follow its own patterns?"

    **What you're looking for:**
    - Files whose described responsibilities or interfaces don't follow
      the naming conventions in the conventions doc
    - Files that seem to handle the same concern differently than their
      peers (e.g., one serializer validates on save but another doesn't)
    - Files whose dependency patterns break the subsystem's conventions
    - Groups of similar files where one is structured differently
    - Any file description that hints at mixed paradigms or inconsistent
      error handling approaches

    **What you are NOT looking for:**
    - Logic bugs or correctness issues / single reproducible defects
      (instance bugs -> /delve)
    - A single missing error handler (instance bug -> /delve); systemic
      absence of error-handling discipline is the Robustness lens
    - Architectural concerns like coupling or dependency direction
      (that's the Architecture lens)

    ## Codebase Conventions

    [PASTE: conventions.md from cartographer, if available. If not
    available, note "No conventions document available -- Agent B will
    need to infer conventions from the code itself."]

    ## Subsystem Overview

    [PASTE: Tier 1 overview -- file manifest with role descriptions, key
    interfaces, dependency graph. This IS your summary -- do not expect
    additional file-level summaries.]

    ## Your Job

    1. **Read the overview and conventions.** Build a mental model of what
       consistent code in this subsystem should look like.

    2. **Flag files** that are most likely to contain pattern violations.
       For each flagged file, explain specifically what inconsistency you
       suspect and why.

    3. **Prioritize.** Flag files ranked by likelihood of containing real
       inconsistencies. Agent B has a 1500-line budget for examining full
       source, so fewer high-confidence flags are better than many
       speculative ones. As a rough heuristic, 10-15 files is a practical
       upper bound, but the real constraint is Agent B's line budget.

    ## What You Must NOT Do

    - Do NOT report confirmed findings -- you haven't seen full source yet
    - Do NOT flag files without a specific suspected inconsistency
    - Do NOT flag more than 15 files

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately. Include files triaged so far.
    - Do NOT try to rush through remaining work -- partial triage with
      clear status is better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## CONSISTENCY TRIAGE (AGENT A)

    ### Conventions Summary
    [2-3 sentences: the key patterns this subsystem should follow]

    ### Flagged Files (ranked by suspicion)

    1. **path/to/file.ext**
       - Suspected inconsistency: [specific concern]
       - Why: [what about the overview description triggered suspicion]

    2. **path/to/other.ext**
       - Suspected inconsistency: [specific concern]
       - Why: [reasoning]

    [repeat for each flagged file]

    ### Overall Pattern Observations
    [Any cross-cutting observations about the subsystem's consistency
    that Agent B should be aware of when examining the flagged files]
```

## Agent B: Deep Inspection

Receives full source for Agent A's flagged files. Confirms or rejects suspected inconsistencies.

```
Task tool (general-purpose, model: opus):
  description: "Audit consistency lens (Agent B: deep inspection)"
  prompt: |
    You are an auditor confirming or rejecting suspected pattern
    inconsistencies in an existing subsystem. A prior agent (Agent A)
    scanned the subsystem overview and flagged specific files for
    suspected inconsistencies. Your job is to examine the actual source
    code and determine which suspicions are real.

    ## The Systemic-Only Rule (binding)

    An audit finding must be SYSTEMIC: a pattern recurring across multiple
    sites, a structural property of the subsystem, or a divergence from
    documented intent -- with NO single reproduction. A finding that has
    one concrete reproduction is an instance bug and out of scope, even
    when it spans multiple files (a cross-file single defect is delve's,
    not audit's); route it to /delve. The discriminator is "is there one
    concrete reproduction?", not file count.

    For this lens specifically: a consistency finding is SYSTEMIC drift --
    a PATTERN of a convention applied inconsistently across two or more
    sites (the common case), or a pure STRUCTURAL-PROPERTY consistency
    finding that may carry a single site per the Sites guidance below. A
    single deviating line that is itself a reproducible bug is an instance
    bug -> /delve, not a consistency finding.

    ## Your Lens: Consistency (Phase B -- Confirmation)

    **Core question:** "Does this code follow its own patterns?"

    **What you're looking for:**
    - Naming convention violations (variables, methods, classes, files)
    - Inconsistent error handling approaches across similar files
    - Mixed paradigms within the same subsystem (callbacks vs promises,
      events vs direct calls, etc.)
    - Convention drift -- where a pattern was followed initially but later
      files diverge
    - Inconsistent API surface design across similar components

    ## Codebase Conventions

    [PASTE: conventions.md from cartographer, if available]

    ## Agent A's Triage

    [PASTE: Agent A's full output -- flagged files with suspected
    inconsistencies and overall pattern observations]

    ## Source Files

    [PASTE: Full source for Agent A's flagged files, subject to the
    1500-line hard cap. If Agent A flagged more files than fit, include
    full source for the highest-priority flags and 2-3 line summaries
    for the rest.]

    ## Your Job

    1. **Read Agent A's triage.** Understand what inconsistencies were
       suspected and why.

    2. **Examine the source code.** For each flagged file, determine
       whether the suspected inconsistency is real. Some suspicions from
       overview-only analysis will turn out to be false positives -- that
       is expected and fine.

    3. **Report confirmed findings only.** Each finding must have specific
       code evidence from the source files.

    4. **Prioritize by severity:**
       - **Fatal** -- Inconsistency that will cause bugs (e.g., one code
         path expects a different contract than another)
       - **Significant** -- Inconsistency that harms maintainability or
         will likely cause bugs as the code evolves
       - **Minor** -- Cosmetic inconsistency that doesn't affect behavior

    ## What You Must NOT Do

    - Do NOT suggest fixes (audit is report-only)
    - Do NOT report a single-reproduction finding as a lens finding -- the
      Systemic-Only Rule routes it to /delve; record any you noticed in
      passing under "Out-of-scope instance bugs (noted for /delve)" in your
      output so it is never dropped
    - Do NOT flag correctness bugs / single reproducible defects (-> /delve)
    - Do NOT flag a single missing error handler (-> /delve); systemic
      absence is the Robustness lens
    - Do NOT flag architectural concerns (Architecture lens handles that)
    - Do NOT confirm a PATTERN finding without specific code evidence at
      two or more sites (a one-site deviation with a concrete reproduction
      is an instance bug -> /delve); a pure STRUCTURAL-PROPERTY finding may
      carry a single site or the whole-subsystem marker per the Sites
      guidance in the Output Format
    - Do NOT exceed 5 findings unless you have strong justification

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately.
    - Do NOT try to rush through remaining work -- partial findings with
      clear status are better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## AUDIT CONSISTENCY FINDINGS

    ### Summary
    - Files flagged by Agent A: N
    - Files examined (full source): N
    - Files summarized (not fully examined): N
    - Suspected inconsistencies confirmed: N
    - Suspected inconsistencies rejected: N
    - Issues found: N (Fatal: N, Significant: N, Minor: N)

    ### Finding 1: [Brief title]
    - **Severity:** Fatal/Significant/Minor
    - **File:** path/to/file.ext
    - **Line range:** L42-L58
    - **Sites:** [{file: path/to/a.ext, line: 42}, {file: path/to/b.ext, line: 88}, ...]
      (every site the drift spans -- a representative line at each
      divergent site, plus a site showing the convention the others
      should follow. Two or more sites are required for a PATTERN finding
      (consistency drift is inherently a recurrence across sites, so keep
      2+ here as the norm). A pure STRUCTURAL-PROPERTY finding may carry a
      single site, or the whole-subsystem marker
      `sites: [whole-subsystem]` when no discrete second site exists. A
      divergence-from-intent finding follows the same rule as its
      category.)
    - **Evidence:** [The specific code showing the inconsistency. Quote
      the inconsistent code AND the pattern it should follow.]
    - **Convention violated:** [Which convention or pattern is broken]
    - **Description:** [What's inconsistent and why it matters]

    [repeat for each confirmed finding]

    ### Rejected Suspicions
    [Brief list of Agent A's flags that turned out to be false positives,
    with one-line explanation of why each was rejected]

    ### Out-of-scope instance bugs (noted for /delve)
    [Single-reproduction defects you noticed IN PASSING while analyzing --
    a bug with ONE concrete reproduction, out of scope for this systemic
    lens. Do NOT hunt for these; just record any you happened to see so
    they are never lost. One line each: `file:line -- one-line description`.
    The orchestrator routes these to /delve, or lists them under the
    "Out-of-scope instance bugs (install /delve to triage)" stub when
    /delve is absent. Omit this section if you noticed none.]

    ### Files Needing Deeper Inspection
    [List any summarized files where the summary raised suspicion but
    full source was not available.]
```
