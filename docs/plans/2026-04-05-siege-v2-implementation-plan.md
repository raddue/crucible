---
ticket: "#123"
title: "Siege v2 — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Siege v2 — Implementation Plan

## Task Overview

7 tasks across 3 waves. Wave 1: SKILL.md changes (deployment context + fix approval gate). Wave 2: agent prompt template updates (reproduction sections + dependency depth). Wave 3: ATT&CK scoping (Chain Analyst only).

## Wave 1: SKILL.md Core Changes

### Task 1: Add deployment_context parameter and severity adjustment

**Files:** `skills/siege/SKILL.md`
**Complexity:** Medium
**Dependencies:** None

Add to Invocation API section:
- `deployment_context` parameter with values: `intranet`, `public`, `hybrid`, unset
- Default behavior when unset: assume `public` (no change from v1)

Add to Phase 3 (Synthesis) section:
- Severity adjustment rules for network-level findings when `deployment_context: intranet`
- Downgrade by 1 level for network-level findings only (anonymous endpoints, TLS gaps, CORS, port exposure, header gaps)
- Application-level findings (injection, auth bypass, data exposure, IDOR) never downgraded
- Audit trail: log each downgrade with original severity, adjusted severity, and reason
- Preserve original severity in finding metadata

Define the network-level finding classifier:
- Network-level: findings about endpoints that should be restricted, transport security, port exposure, CORS, security headers
- Application-level: findings about code logic, data handling, auth/authz, injection, business logic

### Task 2: Add fix agent approval gate

**Files:** `skills/siege/SKILL.md`
**Complexity:** Medium
**Dependencies:** None

Modify Phase 4 (Security Gate) fix mechanism:
- After each fix round, output a per-fix commit table with: finding ID, approach, files changed, commit SHA
- Include reject instructions: "To reject a fix: `git revert <commit-sha>` (each fix is a separate commit)"
- The pipeline does NOT pause — next review round proceeds immediately
- If user rejects a fix between rounds, the next review will re-find the vulnerability (correct behavior)

Ensure fix agent creates one commit per finding (not a batch commit). Each commit message references the finding ID: `fix(security): address [SIEGE-XX-N] — [title]`

### Task 3: Add deployment_context to threat model persistence

**Files:** `skills/siege/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1

Update Phase 5 (Threat Model Update):
- Persist `deployment_context` in the threat model header when set
- On subsequent runs, if `deployment_context` is not specified but exists in the threat model, use the persisted value with a note: "Using deployment context from threat model: {context}. Override with explicit parameter."
- If explicit parameter conflicts with persisted value, use the explicit parameter and update the threat model

## Wave 2: Agent Prompt Template Updates

### Task 4: Add reproduction sections to all 6 agent prompts

**Files:** `skills/siege/boundary-attacker-prompt.md`, `skills/siege/insider-threat-prompt.md`, `skills/siege/infrastructure-prober-prompt.md`, `skills/siege/betrayed-consumer-prompt.md`, `skills/siege/fresh-attacker-prompt.md`, `skills/siege/chain-analyst-prompt.md`
**Complexity:** High (6 files, each needs domain-specific reproduction patterns)
**Dependencies:** None

Add `## Reproduction` section to each agent's per-finding output format:
- 1-3 concrete commands (curl, PowerShell, SQL, etc.)
- Expected output showing vulnerability is present
- Expected output after fix

Domain-specific examples per agent:
- **Boundary Attacker:** curl commands with injection payloads, malformed inputs
- **Insider Threat:** curl commands with different auth tokens showing unauthorized access
- **Infrastructure Prober:** file path checks, config value greps, header inspections
- **Betrayed Consumer:** curl responses showing over-broad data, log greps showing PII
- **Fresh Attacker:** whatever format suits the finding
- **Chain Analyst:** multi-step reproduction (step 1: do X, step 2: use result to do Y)

Ensure reproduction commands are read-only demonstrations, not destructive. Add a note to each prompt: "Reproduction commands must be non-destructive and read-only."

### Task 5: Expand Infrastructure Prober for deep dependency scanning

**Files:** `skills/siege/infrastructure-prober-prompt.md`
**Complexity:** Medium
**Dependencies:** None

Add "Dependency Deep Scan" section to Infrastructure Prober prompt:

**Transitive dependency checks:**
- .NET: `dotnet list package --vulnerable --include-transitive`
- Node: `npm audit --all` (verify devDependencies included)
- Python: `pip-audit` or `safety check` fallback
- Go: `govulncheck ./...`
- Rust: `cargo audit`

**Vendored asset scanning:**
- Glob static asset directories: `wwwroot/`, `public/`, `static/`, `dist/`, `vendor/`, `lib/`
- Identify JS/CSS libraries by filename patterns and header comments
- Cross-reference major libraries (jQuery, Bootstrap, Moment.js, Lodash, Angular, React, Vue) against known CVEs

**Framework detection:** Use Phase 1 reconnaissance data to select appropriate commands. Skip transitive scanning if framework is unrecognized.

Update finding format for dependency findings:
```
**[ID]** [severity] -- Vulnerable dependency: [package@version]
File: [manifest-path or asset-path]
Attack: [1-sentence exploitation scenario for this CVE]
Evidence: [CVE ID, advisory URL, or version comparison]
Verification: [command to verify fix, e.g., "dotnet list package --vulnerable | grep [package]"]
## Reproduction
[command showing vulnerable version present]
```

## Wave 3: ATT&CK Scoping

### Task 6: Add attack_mapping parameter to SKILL.md

**Files:** `skills/siege/SKILL.md`
**Complexity:** Low
**Dependencies:** None

Add to Invocation API:
- `attack_mapping` parameter, boolean, default false
- When true: Chain Analyst includes ATT&CK technique IDs in chain analysis
- When false: no ATT&CK references anywhere (identical to v1)

Add to Phase 2 agent dispatch:
- Pass `attack_mapping` flag to Chain Analyst dispatch only
- Other agents unchanged regardless of flag

### Task 7: Add ATT&CK mapping section to Chain Analyst prompt

**Files:** `skills/siege/chain-analyst-prompt.md`
**Complexity:** Low
**Dependencies:** Task 6

Add conditional section to Chain Analyst prompt (included only when `attack_mapping: true`):
- After each chain step, annotate with ATT&CK technique ID (e.g., T1078, T1068, T1190)
- Add `## ATT&CK Mapping` section at end of chain analysis output
- Mapping shows: chain step → technique ID → technique name → tactic

When `attack_mapping: false` (default), this section is omitted from the dispatch — Chain Analyst prompt is identical to v1.

## Dependency Graph

```
Task 1 (deployment context) ← Task 3 (threat model persistence)
Task 2 (fix approval) — independent
Task 4 (reproduction sections) — independent
Task 5 (dependency depth) — independent
Task 6 (attack_mapping param) ← Task 7 (Chain Analyst ATT&CK)
```

All Wave 1 tasks are independent of Wave 2 tasks. Wave 3 is independent of Waves 1-2.

## Implementation Notes

- **All changes are additive.** When new parameters are unset, behavior is identical to v1.
- **Agent prompts are the primary implementation target.** Most changes are prompt engineering, not code.
- **Disk-mediated dispatch.** All prompt template changes must preserve the `<!-- DISPATCH: disk-mediated -->` header per `skills/shared/dispatch-convention.md`.
- **Test via real-world run.** The best validation is running `/siege` on a codebase with known vulnerabilities and verifying the new features work.
