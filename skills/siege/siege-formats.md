# Siege Finding and Report Formats

Templates for findings output and final report structure.

## Initial Findings (Per-Agent Output) -- 5 Lines Max

```
**[ID]** [severity] [Active|Hardening] -- [title]
File: [path]:[line_range] | Agent: [agent_name]
Attack: [1-sentence exploitation scenario]
Evidence: [specific code reference or design element]
Verification: [concrete test or check that confirms the vulnerability]
```

Agents output findings in this format only. No blast radius, no extended analysis. This keeps per-agent output under 30 lines for a typical 5-finding set.

### Structured Dedup Fields

For mechanical deduplication before steel-manning, each finding also includes structured metadata as a comment block:

```
<!-- dedup: file=[path] line=[start-end] cwe=[CWE-ID] agent=[agent_name] -->
```

The orchestrator uses these fields for first-pass mechanical dedup: same file + overlapping line range + same CWE = merge. Steel-man-then-kill runs only on the deduplicated set, reducing synthesis cost.

## Full Report Findings (Critical and High Only) -- Phase 3 Output

Critical and High findings are expanded in the Phase 3 report:

```
### [ID]: [title]
**Severity:** [Critical|High] | **Exploitability:** [Active|Hardening] | **Agent:** [agent_name] | **Chain:** [yes/no]
**File:** [path]:[line_range]

**Exploitation Scenario:**
[2-4 sentences: who attacks, how, what they gain]

**Blast Radius:**
- Data exposure: [what data is at risk]
- User impact: [how many users, what they experience]
- System impact: [lateral movement, persistence, escalation potential]

**Verification Criteria:**
1. [Concrete test or reproduction step]
2. [Expected result that confirms the fix]

**Steel-Man (why this might not be exploitable):**
[1-2 sentences: strongest case for false positive, and why it was rejected]
```

Medium and Low findings remain in the 5-line initial format in the final report.

## Final Report Template

Written to `scratch/<run-id>/report.md` and presented to the user.

```markdown
# Siege Security Audit Report
**Target:** [subsystem/artifact name]
**Commit Anchor:** [full SHA]
**Date:** [ISO-8601]
**Intelligence:** [sources consulted, gaps noted]
**Artifact Type:** [design|plan|code|mixed]

## Scope Limitations
[What Siege cannot detect -- see Known Limitations. Always present.]

## Attack Chains
[Multi-step chains identified by Chain Analyst, with full exploitation narrative. Chains are the highest-signal output — present them first so the reviewer sees composed threats before individual findings.
Chains inherit exploitability from their weakest link: if ANY step in the chain requires a future change to become exploitable, the entire chain is Hardening. A chain is Active only when every step is independently exploitable today.]

## Critical Findings
### Active Vulnerabilities
[Full report format for each, or "None"]
### Hardening
[Full report format for each, or "None"]

## High Findings
### Active Vulnerabilities
[Full report format for each, or "None"]
### Hardening
[Full report format for each, or "None"]

## Medium Findings
[Initial 5-line format for each, or "None". Medium and Low use the compact 5-line format which includes the exploitability tag per-finding. No Active/Hardening sub-grouping — these severities do not block the gate, so triage ordering is less critical.]

## Low Findings
[Initial 5-line format for each, or "None"]

## Accepted Risks
[Any findings the user acknowledged with rationale, or "None"]

## Threat Model Delta
[New surfaces, retired surfaces, drift from prior model]

## Agent Coverage
[Which agents examined which files -- partition summary]
```
