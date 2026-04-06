---
ticket: "#123"
title: "Siege v2 — Environment Context, Fix Approval, Runtime Proof, Dependency Depth, ATT&CK Scoping"
date: "2026-04-05"
source: "spec"
---

# Siege v2 — Design Document

**Goal:** Five improvements to the Siege security audit skill, driven by findings from the first real-world external codebase audit. Items 1-3 are high priority; items 4-5 are incremental.

**Constraint:** All changes are additive or opt-in. Existing Siege behavior is unchanged when new features are not used.

## 1. Current State Analysis

Siege v1 is a 5-phase security audit engine dispatching 6 parallel Opus agents across attacker perspectives, iterating until zero Critical + zero High findings. It was validated on an external ASP.NET Core 10 codebase (~7,800 LOC, 60+ files, Dapper/SQL Server, intranet deployment behind Windows Auth).

**What the real-world run revealed:**
- 14 unique findings (19 raw, deduped). 0 Critical, 2 High, 6 Medium, 6 Low. Gate score 4, passed after 1 fix round.
- Multi-agent corroboration worked (Insider Threat + Chain Analyst independently flagged the same authorization gap)
- Both Highs were already on the developer's roadmap — Siege independently arrived at the same conclusion
- Most valuable new finding was a Medium (signoff forgery) not previously considered

**What needs improvement:**
1. Internal-network-only issues were flagged at Medium when the app has zero internet exposure
2. Fix agent chose an implementation approach without developer input
3. All findings are purely analytical — no concrete reproduction commands
4. Dependency scanning is surface-level (top-level packages only)
5. ATT&CK is wrong for application-level code review (CWE/OWASP are the right fit)

## 2. Improvement 1: Environment Context Awareness (High Priority)

### Problem

Siege flagged an anonymous health endpoint and SMTP on port 25 without TLS at Medium severity — both are non-issues for an intranet app behind Windows Auth with zero internet exposure. Without deployment context, agents assume worst case.

### Design

Add an optional `deployment_context` parameter to Siege invocation:

```
/siege
  deployment_context: "intranet"   # optional — intranet | public | hybrid
```

**Values:**

| Context | Meaning | Effect on Severity |
|---|---|---|
| `intranet` | Internal network only, no internet exposure | Network-level findings downgraded by 1 level. Application-level findings unchanged. |
| `public` | Internet-facing, untrusted users | No adjustment (current default behavior) |
| `hybrid` | Internal app with some external-facing endpoints | Same as `public` (no blanket adjustment). Users with mixed exposure should use `public` — the intranet downgrade only applies when ALL endpoints are internal. |
| *(unset)* | Unknown | Assume worst case = `public` (no change from v1) |

**Severity adjustment rules:**
- "Downgraded by 1 level" means Critical→High, High→Medium, Medium→Low, Low→Informational
- Only network-level findings qualify for downgrade (anonymous endpoints, TLS gaps, CORS misconfig, port exposure, header gaps)
- Application-level findings (injection, auth bypass, data exposure, IDOR) are NEVER downgraded — an insider on the network can still exploit these
- The downgrade is applied during Phase 3 synthesis, not by individual agents — agents report raw findings, the orchestrator adjusts severity based on context
- Every downgrade is logged: "Downgraded [ID] from [original] to [adjusted] due to intranet deployment context"
- The original severity is preserved in the finding metadata so the user sees both

**Implementation location:** SKILL.md Phase 3 (Synthesis). No changes to agent prompts — agents always report worst-case. The orchestrator applies context-aware adjustments after synthesis.

### DEC-1: Orchestrator-side adjustment, not agent-side (High confidence)

**Decision:** Agents always assume worst-case. The orchestrator adjusts severity in Phase 3.

**Alternatives considered:**
- Pass deployment_context to agents and let them self-adjust: Risks inconsistent calibration across 6 agents with different perspectives
- Let agents see the context but not adjust: Adds prompt complexity for no benefit

**Reasoning:** Centralized adjustment is consistent and auditable. Agents produce raw signal; orchestrator applies policy.

## 3. Improvement 2: Fix Agent Approval Gate (High Priority)

### Problem

The fix agent chose an implementation approach without consulting the developer. For a small-scope app that's fine, but for larger codebases it could create technical debt if the pattern gets replicated.

### Design

After the fix agent generates its approach but before writing code, output the approach as a "suggested fix" that the user can review.

**Mechanism: Suggest-then-apply (option C from the issue)**

1. Fix agent generates the fix and commits it to a separate commit
2. The orchestrator reports: "Fix generated for [finding]. Review the diff before accepting."
3. The fix is already committed — rejecting is a `git revert <commit-sha>`
4. This is **non-blocking**: the pipeline continues to the next review round immediately. The user can reject fixes asynchronously.

**Why option C over A or B:**
- **(A) Block and wait:** Breaks the walk-away workflow. The user has to babysit.
- **(B) Auto-select simpler approach:** Removes user veto. Less control.
- **(C) Generate but mark as suggested:** Non-blocking, full veto power, fix is already in a separate commit so rejecting is trivial.

**Output format (after each fix round):**

```
## Siege Fix — Round N

| # | Finding | Approach | Files | Commit |
|---|---------|----------|-------|--------|
| 1 | [SIEGE-BA-1] SQL injection in UserController | Parameterized query via Dapper | UserController.cs | abc1234 |
| 2 | [SIEGE-IT-3] IDOR on /api/records/{id} | Added ownership check in middleware | RecordService.cs, AuthMiddleware.cs | def5678 |

**To reject a fix:** `git revert <commit-sha>` (each fix is a separate commit)
**To accept all:** No action needed — fixes are already applied.
```

**Pipeline interaction:** The pipeline does NOT pause. The next review round sees the current code state (with fixes applied). If the user rejects a fix between rounds, the next review round will re-find the vulnerability — this is correct behavior.

### DEC-2: Non-blocking suggest-then-apply (High confidence)

**Decision:** Fixes are applied immediately but clearly documented per-commit for easy rejection.

**Reasoning:** Preserves the autonomous walkaway pipeline while giving the developer full veto power on each fix independently.

## 4. Improvement 3: Runtime Verification Suggestions (High Priority)

### Problem

All findings are analytical. Reviewing developers must reverse-engineer the exploitation path themselves to verify findings.

### Design

Each finding includes a `## Reproduction` section with concrete commands that demonstrate the vulnerability. These are proof-of-concept commands, not weaponized exploits.

**Agent prompt addition (all 6 agents):**

After each finding, include:

```
## Reproduction
[1-3 concrete commands (curl, PowerShell, SQL, etc.) that demonstrate this vulnerability]
[Expected output showing the vulnerability is present]
[Expected output after fix is applied]
```

**Scope:**
- HTTP endpoints: `curl` commands with specific payloads
- SQL injection: parameterized vs. unparameterized query comparison
- Auth bypass: requests with/without valid tokens showing response differences
- Config issues: specific file paths and values to check
- IDOR: requests with different user contexts showing unauthorized access

**Not in scope:**
- Automated execution of reproduction commands (Siege is static analysis)
- Full exploit chains (individual PoC per finding only)
- Commands that would damage data or state (read-only demonstrations)

**No gating flag needed:** If you're running a security audit, you've already opted into seeing this.

**Implementation location:** Agent prompt templates. Add the reproduction section to the per-agent finding format in each agent's prompt template (`boundary-attacker-prompt.md`, `insider-threat-prompt.md`, etc.). The Phase 3 synthesis carries reproduction sections through to the final report.

### DEC-3: Inline in agent prompts, not a post-processing step (High confidence)

**Decision:** Agents generate reproduction commands inline with each finding.

**Reasoning:** The agent that found the vulnerability has the deepest context about how to reproduce it. A post-processing agent would need to re-derive the exploitation path.

## 5. Improvement 4: Deeper Dependency Scanning (Incremental)

### Problem

Current dependency scanning is surface-level — only checks top-level packages via `dotnet list package --vulnerable`, `npm audit`, etc. Misses transitive dependencies and vendored assets.

### Design

Expand the Infrastructure Prober's scope to include:

**Transitive dependency checks:**
- .NET: `dotnet list package --vulnerable --include-transitive`
- Node: `npm audit --all` (includes transitive by default, but verify devDependencies)
- Python: `pip-audit` (or `safety check` if pip-audit unavailable)

**Vendored asset scanning:**
- Glob for JS/CSS libraries in static asset directories (`wwwroot/`, `public/`, `static/`, `dist/`)
- Extract version from file headers or filenames (e.g., `jquery-3.6.0.min.js`)
- Cross-reference against known vulnerabilities (agent's training data is sufficient for major libraries — jQuery, Bootstrap, Moment.js, Lodash, etc.)

**Implementation location:** Infrastructure Prober agent prompt template. Add a "Dependency Deep Scan" section to the existing prompt. The prober already runs package vulnerability checks — this expands the scope.

**Framework detection:** The prober already identifies the tech stack in Phase 1 reconnaissance. Use this to select the right transitive dependency command. If the stack is unrecognized, skip transitive scanning (graceful degradation).

### DEC-4: Expand Infrastructure Prober, don't add a new agent (High confidence)

**Decision:** Add dependency depth to the existing Infrastructure Prober rather than creating a 7th agent.

**Reasoning:** The prober already handles dependency scanning. Adding depth is a natural extension. A separate agent would add dispatch overhead and require coordination with the prober's existing scope.

## 6. Improvement 5: ATT&CK Scoping (Incremental)

### Problem

MITRE ATT&CK is designed for enterprise network-level threats (lateral movement, persistence, C2). It's the wrong taxonomy for application-level code review findings. CWE and OWASP are the correct fit for finding-level classification.

### Design

**Scope ATT&CK to Chain Analyst only, off by default.**

The Chain Analyst already connects individual findings into multi-step exploitation paths (kill chains). ATT&CK technique IDs formalize that mapping for teams that use ATT&CK in their threat models.

**New optional parameter:**

```
/siege
  attack_mapping: true   # optional, default false
```

When enabled:
- Chain Analyst annotates each chain step with the relevant ATT&CK technique ID (e.g., T1078 for valid account abuse, T1068 for privilege escalation)
- Chain Analyst output includes a `## ATT&CK Mapping` section with technique IDs linked to chain steps
- Other agents do NOT use ATT&CK — they continue using CWE/OWASP for finding-level classification

When disabled (default): No ATT&CK references anywhere. Behavior identical to v1.

**Implementation location:** Chain Analyst prompt template only. Add a conditional section that includes ATT&CK mapping instructions when `attack_mapping` is enabled.

### DEC-5: Off by default, Chain Analyst only (High confidence)

**Decision:** ATT&CK is opt-in and scoped to the one agent where it adds value.

**Reasoning:** Most teams don't use ATT&CK for application security. Adding it everywhere would create noise. The Chain Analyst is the natural fit because it already builds kill chains.

## 7. Risk Areas

| Risk | Severity | Mitigation |
|---|---|---|
| Deployment context downgrade hides real vulnerabilities | Medium | Only network-level findings downgraded. Application-level findings never adjusted. Original severity preserved in metadata. |
| Reproduction commands could be used maliciously | Low | Commands are read-only demonstrations, not weaponized. If you're running a security audit, you've already opted in. |
| Fix approval gate adds friction | Low | Non-blocking. Pipeline continues. User rejects asynchronously via git revert. |
| Transitive dep scanning adds runtime to Phase 1 | Low | Commands are fast (<10s). Framework detection gates which commands run. |
| ATT&CK mapping adds complexity to Chain Analyst | Low | Off by default. Conditional prompt section. |

## 8. Acceptance Criteria

1. `deployment_context` parameter (intranet/public/hybrid) adjusts network-level finding severity with audit trail
2. Fix agent outputs per-fix commit table with reject instructions after each fix round
3. All 6 agent prompt templates include `## Reproduction` section format in findings
4. Infrastructure Prober checks transitive dependencies (framework-specific commands)
5. Infrastructure Prober scans vendored assets in static directories
6. `attack_mapping` parameter enables ATT&CK technique IDs on Chain Analyst output only
7. All changes are additive — unset parameters produce identical v1 behavior
8. Deployment context downgrade only applies to network-level findings, never application-level
