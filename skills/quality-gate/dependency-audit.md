---
name: dependency-audit
description: Ecosystem-appropriate dependency vulnerability audit. Walks the project for package.json, Cargo.toml, requirements.txt, pyproject.toml manifests and runs npm/cargo/pip-audit. Produces a structured supply-chain signal with normalized severities. Used by build alongside quality-gate; can also be invoked standalone. Triggers on /dependency-audit, 'audit dependencies', 'scan vulnerabilities', 'check CVEs'.
origin: crucible
---
<!-- MODEL-TIER: security-hard-out -->

# Dependency Audit

Runs ecosystem-appropriate dependency audit commands and produces a normalized supply-chain signal. Independent of code review — produces a separate, parallel signal that callers (build, quality-gate, user) integrate as they choose.

**Announce at start:** "Running dependency audit on [project path]."

**Skill type:** Rigid — follow exactly, no shortcuts.

## When to Use

- **Build pipeline:** Invoked in parallel with quality-gate on code-artifact phases. Both produce independent signals; build's gate ledger integrates them.
- **Standalone:** User runs `/dependency-audit` directly to scan a project ad-hoc.
- **CI / scheduled runs:** Invoked by a cron-style schedule to catch dependency drift between feature work.

## Skill Arguments

**`skip_blocking`** (boolean, default: `false`) — Global override. When `true`, disables ALL blocking regardless of `min_blocking_severity`. Findings are still reported in `audit-results.md` but no blocking occurs and the result is FINDINGS (not BLOCKED). `skip_blocking` supersedes `min_blocking_severity` entirely — they do not interact as independent thresholds.

**`min_blocking_severity`** (string, default: `"critical"`, case-insensitive) — The minimum normalized severity at which a finding triggers blocking. Accepted values: `"critical"`, `"high"`, `"moderate"`, `"low"`. Invalid values are rejected with an error before execution begins. This does not change what gets reported — all findings always appear in `audit-results.md`; it only affects whether the result is BLOCKED vs FINDINGS.

**`scope_root`** (string, default: cwd) — Directory to scan for manifests. Defaults to the current working directory.

## Manifest Scanning

Walk the directory tree from `scope_root`, collecting all manifest files matching the supported set:

| Manifest File | Ecosystem |
|---|---|
| `package.json` | Node.js |
| `Cargo.toml` | Rust |
| `requirements.txt` | Python |
| `pyproject.toml` | Python |

**Excluded directories:** `node_modules/`, `.git/`, `target/`, `dist/`, `vendor/`, `third_party/`, `.venv/`, `venv/`. These contain vendored or installed dependencies, not the project's own manifests.

**Symlinks are not followed** — following them risks infinite recursion in repos with circular symlinks or deeply nested node_modules.

**npm workspace detection:** Before scheduling per-directory `npm audit` runs, inspect each discovered `package.json` for a top-level `"workspaces"` field. If a workspace root is detected, schedule a single `npm audit` from that root directory. Do not schedule separate runs for `package.json` files in subdirectories that are members of that workspace.

**Python dual-manifest handling:** When a directory contains both `requirements.txt` and `pyproject.toml`, audit both. They may represent different dependency sets. Duplicate findings are deduplicated at result-write time in `audit-results.md` using the key **(package name + CVE ID)** — each unique (package, CVE) pair appears once with a note of which sources reported it. Version differences for the same (package, CVE) pair are noted but not double-counted.

**Manifest list finalization:** The manifest list is written to `preflight-audit.md` before any audit tool is invoked. This list is the authoritative scope for the run. If compaction occurs after this point, the audit resumes from the recorded list — it does not re-scan.

**Zero manifests:** If zero manifests are found anywhere in the tree, the audit completes as a no-op and notes this in the output summary.

## Ecosystem Detection and Ordering

Detected manifests are audited in fixed order for deterministic output: **Node.js → Rust → Python**.

| Manifest File | Audit Command | Notes |
|---|---|---|
| `package.json` | `npm audit --json` | Run from workspace root if applicable, otherwise cwd = manifest directory |
| `Cargo.toml` | `cargo audit --json` | Run with cwd = manifest directory |
| `requirements.txt` | `pip-audit --format json -r requirements.txt` | Explicit `-r` flag; does NOT require active venv |
| `pyproject.toml` | `pip-audit --format json` | Requires active venv or lockfile (see below) |

All detected manifests are audited independently (after workspace consolidation). Each runs as an isolated subprocess. A failure in one audit does **not** abort or skip audits for other manifests. **All ecosystems run to completion before the overall result is computed** — a BLOCKED result from one ecosystem does not short-circuit audits for remaining ecosystems.

## Audit Tool Availability

Before invoking any audit tool, the skill checks availability:

| Case | Condition | Action |
|---|---|---|
| **Available** | Tool in PATH, environment ready | Run audit |
| **Tool missing** | Tool not in PATH | Write warning to audit-results.md, surface to user |
| **Tool broken** | Tool found but `--version` fails | Write warning, skip |
| **Environment not ready** | Tool found but required environment absent | Write specific reason, skip with warning |

**Per-manifest environment readiness checks:**

- **`requirements.txt`:** `pip-audit -r requirements.txt` reads the file directly. No virtualenv required. Available if `pip-audit` is on PATH.
- **`pyproject.toml`:** `pip-audit` without `-r` inspects the installed environment. Requires an active virtualenv or a lockfile (`poetry.lock`, `pdm.lock`, `uv.lock`). If neither is present, skip with: "pip-audit requires a virtual environment or lock file for pyproject.toml; results would be unreliable."
- **`Cargo.toml`:** Requires `Cargo.lock` to be present. If absent: "skipped — Cargo.lock absent; run cargo generate-lockfile first."
- **`package.json`:** Requires `package-lock.json` (or `npm-shrinkwrap.json`) in the same directory (or workspace root). If absent: "skipped — no lockfile found; run npm install to generate package-lock.json." `npm` must be on PATH.

**Python manifest confidence:** When only `pyproject.toml` is present (no `requirements.txt` or lockfile in the same directory), include a notice in `audit-results.md`: "**Confidence: Reduced** — No requirements.txt or lock file found. pip-audit is resolving dependencies from pyproject.toml directly. Results may be incomplete."

Tool availability results are written to `audit-results.md` (not `preflight-audit.md`), because they are discovered at execution time, not scan time.

A run where all manifests are skipped (missing tools or environment-not-ready) is reported as **INCONCLUSIVE**, not passing.

## Audit Tool Error Handling

Audit tools exit non-zero for two distinct reasons:

- **Vulnerabilities found** — treated as a successful audit with findings (status: FINDINGS).
- **Audit request failed** (network error, registry timeout, corrupt lockfile) — treated as a failed run (status: FAILED). Warning written, audit continues to next manifest.

**Exit code contracts per tool:**

| Tool | Clean | Findings | Error |
|---|---|---|---|
| `npm audit` | exit 0 | exit 1 | exit 2+ |
| `cargo audit` | exit 0 | exit 1 | exit 2+ |
| `pip-audit` | exit 0 | exit 1 | exit 2+ (or non-zero with unparseable stdout) |

Use exit codes to distinguish outcomes. Do **not** parse stderr substring content to classify results.

## Severity Normalization

Audit tools use different severity vocabularies. The skill normalizes to a common scale. CVSS boundaries are **inclusive on the lower bound, exclusive on the upper** (e.g., a CVSS score of exactly 9.0 is Critical, not High).

| Level | npm audit | cargo audit | pip-audit |
|---|---|---|---|
| **Critical** | `critical` | CVSS >= 9.0 | CVSS >= 9.0 |
| **High** | `high` | CVSS >= 7.0 and < 9.0 | CVSS >= 7.0 and < 9.0 |
| **Moderate** | `moderate` | CVSS >= 4.0 and < 7.0 | CVSS >= 4.0 and < 7.0 |
| **Low** | `low` | CVSS >= 0.1 and < 4.0 | CVSS >= 0.1 and < 4.0 |
| **Informational** | — | CVSS = 0.0 | CVSS = 0.0 |

**CVSS 0.0** findings are classified as **Informational** — reported in `audit-results.md` but never count toward blocking. They do not map to any blocking severity level.

If a finding has no CVSS score (advisory-only, no CVE assigned), it is treated as **Moderate** and flagged with `[no-cvss]` in the output.

## Output Model

The audit produces two files under its scratch directory `scratch/<run-id>/`:

**`preflight-audit.md`** — Scan-time plan. Written before any audit tool runs. Contains **only scan-time information**:
- Run ID and `generated-at` timestamp (ISO-8601)
- Manifest list with path, ecosystem, and deduplication/workspace decisions

This file is **not updated after execution begins**. It is the immutable record of what the scan discovered.

**`audit-results.md`** — Execution-time output. Written incrementally as each ecosystem completes. Contains:
- Tool availability results (discovered at execution time)
- Per-manifest findings with normalized severity
- Deduplication notes (same CVE from multiple sources)
- Reduced-confidence notices
- Overall result

Each ecosystem section ends with a **`status: complete`** sentinel line. A section without this sentinel is considered incomplete and must be discarded and re-run on recovery.

**Schema for `audit-results.md`:**

```markdown
# Dependency Audit
generated-at: <ISO-8601>
run-id: <run-id>

## Tool Availability
- npm audit: available
- cargo audit: available
- pip-audit (requirements.txt): available
- pip-audit (pyproject.toml): unavailable — no venv or lock file

## Summary
Result: CLEAN | FINDINGS | BLOCKED | INCONCLUSIVE | FAILED
Critical: N  High: N  Moderate: N  Low: N  Informational: N

## npm — packages/api/package.json — FINDINGS
[findings list: package, severity, CVE, fix-available]
status: complete

## pip — src/requirements.txt — FINDINGS
## pip — src/pyproject.toml — FINDINGS
[deduplicated: CVE-2024-XXXXX reported by both src/requirements.txt and src/pyproject.toml — counted once]
status: complete

## Warnings
[environment-not-ready, reduced-confidence, or deduplication notes]
```

## Overall Result Computation

When results span multiple manifests with mixed outcomes, the overall `Result:` field uses this precedence (highest wins):

| Priority | Result | Condition |
|---|---|---|
| 1 (highest) | **BLOCKED** | Findings at or above `min_blocking_severity` and `skip_blocking` is false |
| 2 | **FINDINGS** | At least one manifest returned vulnerability findings (below blocking threshold or override active) |
| 3 | **INCONCLUSIVE** | At least one manifest was skipped (tool missing, environment not ready); no findings |
| 4 | **FAILED** | At least one manifest tool errored; no findings and no skips |
| 5 (lowest) | **CLEAN** | All manifests completed without findings |

**INCONCLUSIVE outranks FAILED** because unknown coverage (a manifest exists but was never audited) is more dangerous than a known, retryable tool error.

## Blocking and Prompting Behavior

When a finding at or above `min_blocking_severity` is present and `skip_blocking` is not `true`:

- **Interactive session** (Claude Code can prompt the user): Present the finding summary grouped by fix availability — "Fixable (N)" and "No fix available (M)" — and ask whether to continue or abort. This grouping gives the user immediate signal on remediation effort: all-fixable blockers are a quick `npm audit fix` / `cargo update` away; no-fix blockers may require dependency replacement or acceptance.
- **Non-interactive context** (automated pipeline, piped input): Write `Result: BLOCKED` and return to the parent orchestrator without prompting.

Whether a session is interactive is a **Claude Code runtime property**, not something the skill detects via TTY heuristics or environment inspection.

**Parent-pipeline integration:** When the audit returns with `Result: BLOCKED`, the parent orchestrator (build, quality-gate caller, or direct user invocation) treats this as a blocking signal. The audit does not itself decide what blocking means downstream — it produces the result.

## Compaction Recovery

Read `preflight-audit.md` to recover the manifest list. Then check `audit-results.md` for completed ecosystem sections (those ending with `status: complete` sentinel). Sections without the sentinel are discarded as incomplete. Resume from the first manifest not yet present as a complete section. Recovery re-invokes the audit tool for incomplete manifests — no raw output is cached between compaction events. After all manifests complete, regenerate the Summary section of `audit-results.md`.

## Stale Audit Results

The `generated-at` timestamp marks when results were produced. Results are valid for that point in time only. The audit does **not** re-run after caller-initiated remediation. This is an explicit design boundary: an audit run is a point-in-time evaluation.

## Invocation Convention

`dependency-audit` is invoked:

- **By build** — alongside `crucible:quality-gate` on phase 4 (code-artifact gate). Both run in parallel; build's gate ledger integrates the results.
- **By the user** — directly via `/dependency-audit`.
- **By schedule** — via `/loop` or `/schedule` for periodic supply-chain scans.

`dependency-audit` does NOT invoke `crucible:quality-gate` or `crucible:red-team`. It produces its own signal; consumption is the caller's responsibility.

## Red Flags

- Re-running the audit after caller-initiated remediation within the same run — audit is point-in-time
- Treating INCONCLUSIVE as CLEAN — unknown coverage is more dangerous than no findings
- Merging dependency findings with code review findings — they are independent signals
- Parsing stderr substrings to classify results — use exit codes
- Running on non-code projects with no manifests — emit a no-op and exit; do not error

## Integration

| Skill | Relationship |
|---|---|
| `crucible:build` | Primary caller. Invokes alongside `crucible:quality-gate` on code-artifact phases. |
| `crucible:quality-gate` | Sibling skill. Both produce independent signals on code artifacts; quality-gate consumes the same artifact for adversarial review while this skill audits its dependencies. |
| `crucible:audit` | Audit skill consumes dependency-audit findings as supporting context when auditing subsystems with dependency surface. |
