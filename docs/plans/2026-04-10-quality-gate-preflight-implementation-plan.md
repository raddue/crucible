# Quality Gate: Pre-Flight Dependency Audit Implementation Plan

**Issue:** #146
**Branch:** feat/quality-gate-preflight-146
**Date:** 2026-04-10

## Task Overview

5 implementation tasks in a single phase. All changes are to `skills/quality-gate/SKILL.md` (prompt/skill document, not executable code).

## Phase 1: Skill Document Changes

### Task 1: Add artifact-type scoping and pre-flight entry point

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add a new top-level section "Pre-Flight Dependency Audit" after the "How It Works" section
- Document artifact-type scoping: runs only for `code` artifacts, unconditionally skipped for all others
- Add the pre-flight step to the "How It Works" numbered flow, inserting it between step 1 (receives artifact) and step 2 (prepares artifact) -- the pre-flight runs after the active-run marker is written but before red-team dispatch
- Define the two skill arguments: `skip_blocking` (boolean, default false) and `min_blocking_severity` (string, default "critical", case-insensitive)
- Document invalid argument rejection (before execution begins)

**Complexity:** Low
**Dependencies:** None

### Task 2: Add manifest scanning and ecosystem detection

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add "Manifest Scanning" subsection under Pre-Flight Dependency Audit
- Document recursive walk from artifact root with excluded directories (node_modules, .git, target, dist, vendor, third_party, .venv, venv)
- Document symlink policy (not followed)
- Document supported manifests: package.json, Cargo.toml, requirements.txt, pyproject.toml
- Document npm workspace detection and consolidation logic
- Document Python dual-manifest handling (audit both, deduplicate by package+CVE)
- Document manifest list finalization and immutability (written to preflight-audit.md before execution)
- Document zero-manifest no-op behavior
- Document fixed audit ordering: Node.js -> Rust -> Python

**Complexity:** Low
**Dependencies:** Task 1 (section exists)

### Task 3: Add audit tool invocation and error handling

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add "Audit Tool Invocation" subsection
- Document the tool availability contract (four cases: available, tool missing, tool broken, environment not ready)
- Document per-manifest environment readiness checks (requirements.txt needs no venv, pyproject.toml needs venv or lockfile, Cargo.toml needs Cargo.lock, package.json needs npm)
- Document the audit command table (npm audit --json, cargo audit --json, pip-audit --format json)
- Document exit code contracts per tool (0=clean, 1=findings, 2+=error)
- Document that failures in one audit do not abort others -- all ecosystems run to completion
- Document error handling: distinguish vulnerabilities-found from audit-request-failed

**Complexity:** Low
**Dependencies:** Task 2 (manifest scanning exists)

### Task 4: Add severity normalization, output model, and blocking behavior

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add "Severity Normalization" subsection with the four-level mapping table (Critical/High/Moderate/Low across npm/cargo/pip)
- Document CVSS boundaries (inclusive lower, exclusive upper)
- Document no-CVSS default (Moderate with [no-cvss] tag)
- Add "Output Model" subsection with the two-file schema (preflight-audit.md and audit-results.md)
- Document preflight-audit.md contents (run-id, timestamp, manifest list)
- Document audit-results.md schema with per-section sentinels, tool availability, summary, per-manifest findings
- Document the anti-anchoring notice in audit-results.md
- Add "Overall Result Computation" subsection with priority precedence table (BLOCKED > FINDINGS > INCONCLUSIVE > FAILED > CLEAN)
- Document blocking behavior: interactive prompting vs non-interactive BLOCKED return
- Document `skip_blocking` and `min_blocking_severity` interaction
- Document Python manifest confidence notices (reduced confidence when only pyproject.toml, no lockfile)

**Complexity:** Medium
**Dependencies:** Task 3 (invocation section exists)

### Task 5: Add compaction recovery and red flags

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add "Pre-Flight Compaction Recovery" subsection under the existing "Round History and Compaction Recovery" section
- Document recovery steps: check preflight-audit.md, check audit-results.md for complete sections, resume from first incomplete manifest
- Document that recovery re-invokes the audit tool (no raw output caching)
- Document summary regeneration after all manifests complete
- Add pre-flight-specific entries to the existing "Red Flags" section:
  - Passing audit findings to red-team dispatch
  - Skipping pre-flight for code artifacts without explicit user approval
  - Re-running pre-flight after fix rounds (point-in-time evaluation)
  - Treating INCONCLUSIVE as CLEAN
- Update the "Integration" section to note the pre-flight dependency on audit tools (npm, cargo, pip-audit) as external tool dependencies

**Complexity:** Low
**Dependencies:** Task 4 (output model exists)

## Verification

After all tasks are complete, the modified SKILL.md should:
1. Contain a complete "Pre-Flight Dependency Audit" section with all subsections
2. Integrate cleanly with the existing "How It Works" flow
3. Add pre-flight recovery steps to the existing compaction recovery section
4. Add pre-flight red flags to the existing red flags list
5. Preserve all existing quality-gate behavior unchanged
