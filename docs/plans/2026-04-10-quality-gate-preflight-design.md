# Quality Gate: Pre-Flight Dependency Audit Design

**Issue:** #146
**Branch:** feat/quality-gate-preflight-146
**Date:** 2026-04-10
**Source:** spec

## Overview

Add a pre-flight dependency audit step to the quality-gate skill that runs ecosystem-appropriate audit commands (npm audit, cargo audit, pip-audit) before the red-team loop begins. Findings are reported to the orchestrator as an independent parallel signal -- the red-team never sees audit data, preserving anti-anchoring.

## Current State Analysis

### Existing Quality Gate Flow

The quality-gate skill (`skills/quality-gate/SKILL.md`) orchestrates iterative red-teaming of artifacts. For code artifacts, the flow is:

1. Artifact preparation (size-based: small/medium/large)
2. Red-team dispatch loop (fresh reviewer each round)
3. Fix agent dispatch on findings
4. Fix verification
5. Stagnation detection
6. Minor issue handling and cleanup

There is no supply-chain or dependency vulnerability awareness. The red-team reviews code quality, architecture, and correctness -- it does not check whether dependencies have known CVEs.

### What's Missing

1. No manifest scanning or ecosystem detection
2. No audit tool invocation or severity normalization
3. No blocking behavior for critical vulnerabilities
4. No compaction recovery for audit state

## Target State

The quality gate gains a pre-flight phase that runs after the active-run marker is written but before the first red-team round. For code artifacts only:

1. Recursive manifest scan from artifact root
2. Workspace consolidation (npm workspaces)
3. Audit tool availability check
4. Sequential audit execution (Node.js -> Rust -> Python)
5. Severity normalization to common scale
6. Overall result computation (CLEAN/FINDINGS/BLOCKED/INCONCLUSIVE/FAILED)
7. Two output files: `preflight-audit.md` (scan plan) and `audit-results.md` (execution results)

The red-team loop proceeds unchanged. Audit findings surface alongside gate results at completion.

## Key Decisions

### Decision 1: Orchestrator-Level Reporting, Not Red-Team Seeding

**Choice:** Audit findings go to the orchestrator and are surfaced to the user. The red-team never sees them.

**Rationale:** Anti-anchoring is the quality gate's core invariant. Feeding dependency findings to the red-team would bias it toward supply-chain issues at the expense of code quality, architecture, and correctness findings. Two independent signals are more valuable than one contaminated signal.

**Confidence: High.** This was quality-gated through 6 rounds in the issue design phase.

### Decision 2: Artifact-Type Scoping

**Choice:** Pre-flight runs only for `code` artifacts. Unconditionally skipped for design, plan, hypothesis, mockup, and translation.

**Rationale:** Dependency auditing is meaningless for non-code artifacts. No scan, no output, no scratch files.

**Confidence: High.**

### Decision 3: Recursive Manifest Scan with Workspace Consolidation

**Choice:** Walk the directory tree from artifact root collecting all manifest files. Consolidate npm workspace members under their workspace root.

**Rationale:** Monorepos contain multiple manifests. Running `npm audit` per-package in a workspace is redundant and slow. Workspace consolidation audits once from the root.

**Confidence: High.**

### Decision 4: Two Output Files

**Choice:** `preflight-audit.md` (immutable scan plan, written before execution) and `audit-results.md` (incremental execution results with per-section completion sentinels).

**Rationale:** Separation enables compaction recovery. The scan plan is fixed at discovery time; execution results are written incrementally. A section without a `status: complete` sentinel is discarded and re-run on recovery.

**Confidence: High.**

### Decision 5: Severity Normalization

**Choice:** Four-level scale (Critical/High/Moderate/Low) with CVSS boundaries. No-CVSS findings default to Moderate with `[no-cvss]` tag.

**Rationale:** npm uses string labels, cargo/pip use CVSS scores. A common scale enables cross-ecosystem comparison and consistent blocking thresholds.

**Confidence: High.**

### Decision 6: Blocking Behavior

**Choice:** Two skill arguments control blocking: `skip_blocking` (boolean, default false) and `min_blocking_severity` (string, default "critical"). `skip_blocking` supersedes `min_blocking_severity` entirely.

**Rationale:** Default behavior blocks on critical vulnerabilities. Users can lower the threshold or disable blocking entirely. Interactive sessions prompt; non-interactive sessions return BLOCKED to the parent orchestrator.

**Confidence: High.**

## Risk Areas

### Tool Availability

Audit tools may not be installed. The gate handles this gracefully: missing tools produce warnings in `audit-results.md` and contribute to INCONCLUSIVE status. No hard dependency on any tool being present.

### Exit Code Ambiguity

`cargo audit` exit code 1 conflates security advisories with unmaintained-package advisories. May need finer classification at implementation time. For now, exit 1 = findings.

### Python Environment Requirements

`pip-audit` for `pyproject.toml` requires a virtualenv or lockfile. The gate checks this per-manifest and skips with a specific reason when the environment is not ready. `requirements.txt` works without a virtualenv.

### Compaction Mid-Audit

Compaction can occur between ecosystem audits. The sentinel-based recovery design handles this: complete sections are preserved, incomplete sections are re-run.

## Acceptance Criteria

1. Pre-flight audit runs automatically for code artifacts before the first red-team round
2. Pre-flight is unconditionally skipped for non-code artifact types
3. Recursive manifest scan discovers all supported manifest files
4. npm workspace consolidation prevents redundant per-package audits
5. Audit tool availability is checked before invocation; missing tools produce warnings, not errors
6. Severity normalization maps all ecosystems to the common Critical/High/Moderate/Low scale
7. Overall result follows the priority precedence: BLOCKED > FINDINGS > INCONCLUSIVE > FAILED > CLEAN
8. `skip_blocking=true` disables all blocking regardless of severity
9. `min_blocking_severity` controls the blocking threshold (default: critical)
10. `preflight-audit.md` is written before any audit tool runs (immutable scan plan)
11. `audit-results.md` is written incrementally with per-section `status: complete` sentinels
12. Compaction recovery resumes from the first incomplete section
13. Red-team dispatch receives no audit data (anti-anchoring preserved)
14. Audit findings are surfaced to the user alongside gate completion results
15. Zero manifests found completes as a no-op with a note
16. Python manifest deduplication uses (package name + CVE ID) key

## Out of Scope

- Separate severity track for dependency findings
- Changes to stagnation detection or loop termination logic
- Seeding or injecting dependency findings into red-team dispatch
- Transitive dependency pinning or automated fix application
- Re-running pre-flight mid-gate after fix-agent remediation
- License compliance, container scanning, SBOM generation
