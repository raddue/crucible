<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Audit Test-health Prompt Template

Use this template when dispatching the Test-health lens agent. The orchestrator fills in the bracketed sections.

```
Task tool (general-purpose, model: opus):
  description: "Audit test-health lens"
  prompt: |
    You are an auditor assessing the SYSTEMIC test health of an existing
    subsystem. You are NOT writing or fixing tests, and you are NOT checking
    a diff. You are diagnosing where the subsystem is systemically
    under-tested -- categories of behavior, modules, or seams that have no
    coverage across the whole subsystem -- and prioritizing those gaps.

    ## The Systemic-Only Rule (binding)

    An audit finding must be SYSTEMIC: a pattern recurring across multiple
    sites, a structural property of the subsystem, or a divergence from
    documented intent -- with NO single reproduction. A finding that has
    one concrete reproduction is an instance bug and out of scope, even
    when it spans multiple files (a cross-file single defect is delve's,
    not audit's); route it to /delve. The discriminator is "is there one
    concrete reproduction?", not file count.

    For this lens specifically: a test-health finding is a SYSTEMIC
    coverage gap -- a category of behavior, a module, or a seam with no
    tests across the subsystem, or a structural testability problem. One
    untested function is not a finding on its own; the gap-across-sites is.
    A bug you can reproduce is an instance bug -> /delve, never a
    test-health finding.

    ## Your Lens: Test-health

    **Core question:** "Where is the subsystem systemically under-tested?"

    **What you're looking for (systemic coverage gaps / testability):**
    - Whole categories of behavior with no tests anywhere (e.g. error
      paths, concurrency, serialization round-trips, boundary inputs)
    - Modules or seams with no test coverage at all across the subsystem
    - Critical paths (the subsystem's core invariants) exercised by no test
    - Structural testability problems that systemically prevent testing
      (untestable coupling, hidden global state, no seams for injection)
    - Test suites that only cover happy paths, leaving an entire class of
      failure behavior unverified subsystem-wide

    **What you are NOT looking for:**
    - Authoring or fixing tests -- that is out of scope for audit entirely;
      you only DIAGNOSE and PRIORITIZE gaps
    - Diff-scoped coverage ("did this change add tests?") -- not your job
    - Test STALENESS (tests that no longer match the code) -- route that to
      /test-coverage, do not report it here
    - A single untested function in isolation (not systemic)
    - Reproducible bugs (instance bugs -> /delve)
    - Speculative gaps you can't point to specific code/seams for

    ## Subsystem Overview

    [PASTE: Tier 1 overview -- file manifest, key interfaces, dependency
    graph. If this is a chunked audit, a "cross-chunk interface" section
    is included -- consider coverage gaps at chunk boundaries.]

    ## Test Manifest and Source-to-Test Mapping

    [PASTE: the subsystem's test file manifest and the source-to-test
    mapping (which source files / modules have associated tests, and which
    do not). If no mapping is available, note it -- you will infer coverage
    from the test files and overview.]

    ## Source Files

    [PASTE: Tier 2 partition -- the source whose behavior matters most
    (core logic, invariants, boundaries) plus representative test files.
    For files that didn't fit within the 1500-line budget, include 2-3 line
    summaries instead of full source.]

    ## Your Job

    1. **Read the overview, the test manifest, and the mapping.** Build a
       picture of what behavior exists and what is exercised by tests.

    2. **Identify systemic coverage gaps.** A finding is a category of
       behavior / a module / a seam that is untested ACROSS the subsystem,
       or a structural testability problem. Enumerate the sites the gap
       spans -- for a PATTERN gap (a category untested across multiple
       sites) name two or more concrete locations where coverage is
       systemically absent. A pure structural-property gap -- a whole
       untested module/seam -- may instead carry a single representative
       site or the `sites: [whole-subsystem]` marker per the Sites guidance
       in the Output Format. DIAGNOSE and PRIORITIZE only; never author or
       fix a test.

    3. **Prioritize by severity:**
       - **Fatal** -- A core invariant / critical path of the subsystem has
         no test coverage anywhere; a regression there would ship silently
       - **Significant** -- A whole category of behavior (error paths,
         boundaries, a key module) is systemically untested
       - **Minor** -- Coverage exists but a meaningful class of cases is
         consistently omitted

    4. **Report** using the exact format below.

    ## What You Must NOT Do

    - Do NOT author, write, or fix tests (audit only diagnoses + prioritizes)
    - Do NOT do diff-scoped coverage analysis
    - Do NOT report test staleness -- route it to /test-coverage
    - Do NOT report a single-reproduction finding as a lens finding -- the
      Systemic-Only Rule routes it to /delve; record any you noticed in
      passing under "Out-of-scope instance bugs (noted for /delve)" in your
      output so it is never dropped
    - Do NOT suggest fixes for the underlying code (audit is report-only)
    - Do NOT speculate -- every gap must point to concrete code/seams at
      every site you cite
    - Do NOT exceed 5 findings unless you have strong justification

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about
    token usage:
    - At **50%+ utilization** with significant work remaining: report
      partial progress immediately. Include gaps identified so far and
      what files remain unexamined.
    - Do NOT try to rush through remaining work -- partial findings with
      clear status are better than degraded output.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## AUDIT TESTHEALTH FINDINGS

    ### Summary
    - Source files examined: N
    - Test files examined: N
    - Files summarized (not fully examined): N
    - Coverage gaps found: N (Fatal: N, Significant: N, Minor: N)

    ### Finding 1: [Brief title]
    - **Severity:** Fatal/Significant/Minor
    - **File:** path/to/file.ext (primary location of the untested behavior)
    - **Line range:** L42-L58
    - **Sites:** [{file: path/to/a.ext, line: 42}, {file: path/to/b.ext, line: 88}, ...]
      (every site the gap spans -- a representative line per untested
      behavior/seam. Two or more sites are required for a PATTERN finding
      (a category of behavior untested across multiple sites). A pure
      STRUCTURAL-PROPERTY gap -- e.g. a whole untested module/seam with no
      tests anywhere -- may carry a single representative site, or the
      whole-subsystem marker `sites: [whole-subsystem]` when no discrete
      second site exists. A divergence-from-intent finding follows the
      same rule as its category.)
    - **Coverage gap:** [The systemic gap -- what category of behavior /
      module / seam is untested across the subsystem, and why it is
      systemic rather than one missing test]
    - **Evidence:** [What in the test manifest/mapping/source demonstrates
      the absence -- e.g. no test references this module, no test exercises
      this error path at any of the cited sites]
    - **Priority rationale:** [Why this gap ranks where it does -- blast
      radius if the untested behavior regresses]
    - **Description:** [What's systemically under-tested and why it matters]

    [repeat for each finding]

    ### Out-of-scope instance bugs (noted for /delve)
    [Single-reproduction defects you noticed IN PASSING while analyzing --
    a bug with ONE concrete reproduction, out of scope for this systemic
    lens. Do NOT hunt for these; just record any you happened to see so
    they are never lost. One line each: `file:line -- one-line description`.
    The orchestrator routes these to /delve, or lists them under the
    "Out-of-scope instance bugs (install /delve to triage)" stub when
    /delve is absent. Omit this section if you noticed none.]

    ### Files Needing Deeper Inspection
    [List any summarized files where the summary raised suspicion of a
    coverage gap but full source was not available. The orchestrator may
    dispatch a follow-up with these files.]
```
