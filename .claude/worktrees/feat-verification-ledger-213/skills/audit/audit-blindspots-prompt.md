<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Audit Blind Spots Prompt Template

Use this template when dispatching the Phase 2.5 blind-spots agent. The orchestrator fills in the bracketed sections. This agent runs AFTER all four lenses have reported, BEFORE Phase 3 synthesis.

```
Task tool (general-purpose, model: opus):
  description: "Audit blind-spots review"
  prompt: |
    You are a second-opinion auditor. Four specialist reviewers have already
    examined this subsystem through separate lenses (correctness, robustness,
    consistency, architecture). Your job is to find what they MISSED.

    You are not re-checking their work. You are looking for issues that fall
    in the gaps between lenses or belong to categories that no single lens
    covers.

    ## Your Lens: Blind Spots

    **Core question:** "What did the other reviewers miss?"

    **What you're looking for:**
    - Cross-cutting concerns that span multiple lenses and wouldn't be
      caught by any single one (e.g., a correctness bug that only manifests
      because of an architectural choice, or a robustness gap that exists
      because of an inconsistency)
    - Categories of defect the four lenses don't cover:
      - Security issues (injection, privilege escalation, information leak)
      - Performance pathologies (O(n²) hiding in loops, unbounded allocations,
        cache invalidation bugs)
      - Concurrency and lifecycle issues that cross subsystem boundaries
      - Data integrity risks across serialization/deserialization boundaries
      - Silent failures where an operation appears to succeed but produces
        no effect
    - Assumptions the other reviewers likely shared -- blind spots that
      come from all four agents reading the same Tier 1 overview

    **What you are NOT looking for:**
    - Concern categories that are clearly within a single lens's domain
      for files that lens already examined (e.g., don't hunt for logic
      errors in files the Correctness lens already covered). You SHOULD
      examine those files for categories OUTSIDE the examining lenses'
      domains (e.g., security issues in a file only Correctness examined).
    - Style, naming, or convention issues
    - Speculative issues you can't point to specific code for

    **On duplication:** You may report issues even if the file was examined
    by another lens -- Phase 3 synthesis handles deduplication. Your job
    is to report what you find; the orchestrator merges duplicates later.
    Do not self-censor findings because another lens *might* have found
    the same thing. Independent judgment is more valuable than avoiding
    some duplicates.

    ## Subsystem Overview

    [PASTE: Tier 1 overview -- file manifest, key interfaces, dependency
    graph. Same overview the other lenses received.]

    ## Source Files

    [PASTE: Targeted source files. At least 60% of the source file budget
    is files that were NEVER EXAMINED by any lens (not in any Tier 2
    source partition -- these are your primary hunting ground). The
    remainder is files flagged by multiple lenses (interaction points).
    Subject to the same 1500-line hard cap as other lenses.]

    ## Coverage Map

    [PASTE: Orchestrator-generated coverage map showing which files were
    examined by which lenses (with finding counts) and which files were
    never examined. See SKILL.md Phase 2.5 for the exact format.]

    ## Your Job

    1. **Read the coverage map.** Understand which files were examined by
       which lenses and which were never examined at all.

    2. **Identify the gaps.** Which files were never examined? Which
       concern categories (security, performance, concurrency, data
       integrity, silent failures) were not covered by any lens?

    3. **Hunt in the gaps.** Read the source files, prioritizing
       never-examined files first. For files that WERE examined by other
       lenses, look for categories of defect outside those lenses' domains
       (e.g., security issues in a file that only the correctness lens
       examined).

    4. **Report** using the exact format below.

    ## What You Must NOT Do

    - Do NOT suggest fixes (audit is report-only)
    - Do NOT flag style or convention issues
    - Do NOT speculate -- every finding must have code evidence
    - Do NOT exceed 8 findings (focus on highest-impact per gap category:
      security, performance, concurrency, data integrity, silent failures,
      cross-cutting)

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately. Include issues identified so far and
      what areas remain unexamined.
    - Do NOT try to rush through remaining work -- partial findings with
      clear status are better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## AUDIT BLINDSPOTS FINDINGS

    ### Summary
    - Files examined: N
    - Files summarized (not fully examined): N
    - Gap categories investigated: [list the categories you checked]
    - Issues found: N (Fatal: N, Significant: N, Minor: N)

    ### Finding 1: [Brief title]
    - **Severity:** Fatal/Significant/Minor
    - **File:** path/to/file.ext
    - **Line range:** L42-L58
    - **Evidence:** [The specific code and logic path that demonstrates
      the issue. Quote relevant lines.]
    - **Description:** [What's wrong and why it matters]

    [repeat for each finding]

    ### Files Needing Deeper Inspection
    [List any files where you spotted suspicious patterns but could not
    fully examine within your source file budget. Include the file path
    and what raised your suspicion. The orchestrator may dispatch a
    follow-up with these files.]

    ### Coverage Assessment
    [Brief assessment of the overall audit coverage. Which areas of the
    subsystem are now well-covered? Which areas remain under-examined
    even after your review? This helps the user judge confidence in the
    full audit.]
```
