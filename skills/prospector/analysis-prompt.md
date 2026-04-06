<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Analysis Prompt Template

Use this template when dispatching the structured analysis agent for a friction point. The orchestrator fills in the bracketed sections.

```
Task tool (general-purpose, model: sonnet):
  description: "Structured analysis for friction point [N]: [brief title]"
  prompt: |
    You are a structural analysis agent. Your job is to evaluate a specific friction point — classify its type, identify the applicable architectural philosophy, assess blast radius, and produce a design brief that competing design agents can consume without reading raw source code.

    ## Input: Friction Point

    [PASTE: Friction point description — title, location (file list), friction description, severity, frequency]

    ## Input: Genealogy Data

    [PASTE: Genealogy classification and key commits — if available; if not: "No genealogy data available."]

    ## Input: Reference Material

    [PASTE: Relevant REFERENCE.md section — only the applicable taxonomy entry, philosophy mapping, and dependency category definition. NOT the entire reference doc.]

    ## Input: Source Files

    [PASTE: Source files — subject to 2000-line hard cap on total prompt content. ~200 lines reserved for REFERENCE.md content, leaving ~1800 for friction description + genealogy + root cause + framework context + change metrics + source + this template.]

    ## Input: Root Cause Summary

    [PASTE: Mechanically extracted root cause summary (max 10 lines) containing four verbatim fields from root cause agent output:
    1. Root cause type (1 line)
    2. Root cause statement (1 line)
    3. Pattern-level fix (1-2 lines)
    4. Framework-native solution (1-2 lines)
    For convergence clusters, append: "Cluster scope: merged from friction points #X, #Y, #Z — addresses shared root cause as a unit."
    For Medium/Low-severity findings without root cause analysis: "Root cause not analyzed -- severity below threshold." or a one-line note from a neighboring High-severity finding if applicable.]

    ## Input: Trajectory Data

    [PASTE: Trajectory data if available. Contains trajectory status
    (NEW, STABLE, ACCELERATING, DECLINING) and metric history from
    prior runs. If no prior runs: "No trajectory data available."]

    ## Input: Framework Context

    [PASTE: Framework context block from Phase 0.5 — language, runtime version, DI framework, test framework, UI/web framework, other domain-relevant frameworks with versions. If no frameworks detected: "No framework context available."]

    ## Input: Change Metrics (from Genealogy)

    [PASTE: Structured change metrics extracted from genealogy output:
    - Change frequency (hottest file): [commits/6mo, rate, filename]
    - Change frequency (range across N files): [lowest]-[highest] commits/6mo
    - Bug-fix commit count (hottest file): [count, filename]
    - Bug-fix commit count (range): [lowest]-[highest]
    If no genealogy data available: "No change metrics available."]

    ## Your Job

    0. **Check if this is a convergence cluster.** You may receive a
       cluster of merged friction points sharing a root cause. If so,
       analyze the cluster as a unit — your design brief should address
       the shared root cause, not individual symptoms. Individual
       symptom descriptions are preserved for context.

    1. **Read the provided source files and friction description.** Understand the module boundaries, public interfaces, caller patterns, and data flow in the friction area.

    2. **Classify the friction type** from the REFERENCE.md taxonomy provided. Match the detection signals in the reference material against what you observe in the source. Use evidence — do not classify without specific code observations.

    3. **Identify the applicable architectural philosophy/framework** based on the friction type classification and the philosophy mappings in the reference material.

    4. **Incorporate genealogy data into your effort estimate** (if available):
       - Incomplete Migrations and Vestigial Structures are typically lower effort — the design direction is known or the work is deletion
       - Accretion and Original Sin are typically higher effort — the design must be invented from scratch
       - Forced Marriage is medium effort — separation requires careful interface design
       - Indeterminate: rely on structural analysis alone for effort estimate

    5. **Classify the dependency category** from the reference material (in-process, local-substitutable, remote-but-owned, true external). This determines what testing strategies are valid for design agents.

    6. **Assess improvement impact** (High/Medium/Low) and **estimated effort** (High/Medium/Low). Justify both with specific evidence. Refine effort estimate using genealogy data when available.

    7. **Split friction into comprehension vs modification dimensions:**
       - Comprehension friction: How hard is it to understand this code? (High/Medium/Low)
       - Modification friction: How hard is it to change this code safely? (High/Medium/Low)
       - Primary dimension: Which dimension dominates? (Comprehension / Modification / Both)

    8. **Compute the ROI / leverage score:**
       - Leverage: How many future changes does fixing this unblock or simplify? (High/Medium/Low)
       - Use the change metrics input to ground your assessment — high change frequency and bug-fix counts indicate high leverage
       - Leverage is distinct from impact. Impact = "how much does fixing this improve the area." Leverage = "how much does fixing this improve everything else."

    9. **Check for framework-native solutions:**
       - Using the framework context and root cause summary, identify whether the project's DI framework, language, or test framework has built-in patterns that address this friction
       - For High-severity findings with root cause data: use the root cause agent's framework pattern investigation (which patterns are used vs unused)
       - For Medium/Low-severity findings: use the Phase 0.5 framework hint only and note that pattern-level usage has not been verified
       - Assess applicability: would the framework pattern solve the root cause, or just the symptom?

    10. **Assess cost of inaction** using these decision rules:
        - **Defensible — low-activity code:** Modification friction is Low AND hottest file's change frequency is monthly-or-less AND zero bug-fix commits for the hottest file. The code causes friction but nobody is paying the cost frequently enough to justify investment.
        - **Defensible — comprehension-only friction in stable code:** Primary friction dimension is Comprehension (not Modification) AND the hottest file has fewer than 2 modifications per quarter. The code is hard to read but rarely needs to be read.
        - **Not defensible (override):** If the code is blocking known planned work, inaction is never defensible regardless of the above rules.
        Even when inaction is defensible, complete all output sections — the finding proceeds to candidate selection but is demoted to "Track Only" tier.

    11. **Extract the design brief components:**
       - Interface surface: the current public API — key type definitions and public method/function signatures verbatim from source
       - Caller patterns: the 3-5 most common ways callers currently invoke the target — concrete code snippets
       - Structural summary: module boundaries, data flow direction, dependency graph fragment

    12. **Incorporate trajectory data** (if available): If the friction
        point is ACCELERATING, flag this in the ROI Assessment as
        additional evidence for high leverage. If DECLINING, note that
        prior interventions may be working. If STABLE across multiple
        runs, note that the friction is persistent and not self-resolving.
        Trajectory data should inform the cost-of-inaction assessment —
        an ACCELERATING friction point is harder to justify as defensible
        inaction.

    ## What You Must NOT Do

    - Do NOT speculate about problems you can't point to evidence for in the provided source
    - Do NOT classify friction without evidence from the source code in your prompt (you are a Task tool dispatch — you receive pasted source, not file access)
    - Do NOT exceed the structured output format — design agents depend on this exact structure
    - The design brief must contain enough concrete detail for design agents to produce accurate interface proposals without reading raw source code

    ## Context Self-Monitoring

    If you reach 50%+ context utilization, prioritize: classification first, then friction dimensions and ROI assessment, then cost of inaction, then design brief. A complete classification with friction dimensions is more useful than a complete design brief with missing classification.

    ## Output Format

    Report using this EXACT structure (plain text, no code fences):

    ## ANALYSIS: [Friction point title]

    ### Classification
    - **Friction type classification:** [Which category from the taxonomy]
    - **Applicable philosophy/framework:** [Which architectural philosophy and why]
    - **Causal origin:** [From genealogy if available — type, key commits, effort implication. If no genealogy data: "No genealogy data available."]

    ### Cluster
    - **Modules involved:** [List of modules/files]
    - **Why they're coupled:** [Shared types, call patterns, co-ownership]
    - **Dependency category:** [In-process / Local-substitutable / Remote-but-owned / True external]

    ### Impact Assessment
    - **Estimated improvement impact:** High/Medium/Low — [brief justification]
    - **Estimated effort:** High/Medium/Low — [brief justification, refined by genealogy]

    ### Friction Dimensions
    - **Comprehension friction:** High/Medium/Low -- [How hard is it to understand this code?]
    - **Modification friction:** High/Medium/Low -- [How hard is it to change this code safely?]
    - **Primary dimension:** Comprehension | Modification | Both

    ### ROI Assessment
    - **Leverage score:** High/Medium/Low -- [How many future changes does this unblock or simplify?]
    - **Leverage justification:** [Concrete evidence -- e.g., "every new screen type requires editing this file"]
    - **Change frequency:** [From change metrics input -- how often is this code modified? monthly/weekly/daily]
    - **Bug correlation:** [From change metrics input -- how many bug-fix commits touch this area?]

    ### Framework Check
    - **Framework patterns available:** [List any DI framework, language, or test framework features that address this friction -- or "None identified"]
    - **Pattern evidence source:** [Root cause investigation (High-severity)] or [Framework hint only (Medium/Low-severity -- pattern usage not verified)]
    - **Applicability:** [Would the framework pattern actually solve the root cause, or just the symptom?]

    ### Cost of Inaction
    - **Change frequency (hottest file):** [From change metrics input -- headline metric: commits/6mo, rate, filename]
    - **Change frequency (range):** [One-line range across all files in scope]
    - **Bug origin rate (hottest file):** [From change metrics input -- bug-fix commits for hottest file]
    - **Blocking planned work:** Yes/No -- [Is this friction blocking any known planned work?]
    - **Inaction assessment:** [1-2 sentences: Is doing nothing a defensible option here? Apply the decision rules.]

    ### Design Brief

    #### Interface Surface Summary
    [Current public API: key type definitions, public method/function signatures — verbatim from source]

    #### Top Caller Patterns
    [3-5 most common usage patterns showing how callers currently invoke the target — code snippets]

    #### Structural Summary
    [Module boundaries, data flow direction, dependency graph fragment]
```
