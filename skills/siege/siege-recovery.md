# Siege Recovery Reference

Recovery procedures, file inventory, and checkpoint timing for compaction resilience.

## File Inventory

| File | Written When | Purpose |
|------|-------------|---------|
| `commit-anchor.md` | Phase 1 start | TOCTOU prevention |
| `manifest.md` | Phase 1 Step 2 | Scoped file list |
| `exposure-map.md` | Phase 1 Step 2.5 | Enumerated endpoints with manifest cross-reference |
| `gate-approved.md` | User confirms scope | Compaction recovery marker |
| `intelligence-summary.md` | Phase 1 Step 1 | Pre-fetched intelligence (50 lines) |
| `<agent>-partition.md` | Before each agent dispatch | Files sent as full source |
| `<agent>-findings.md` | On agent completion | Per-agent findings |
| `coverage-map.md` | Before Chain Analyst dispatch | Agent coverage for chain analysis |
| `tier1-context.md` | Phase 2 Step 1 | Shared Tier 1 context block |
| `dedup-summary.md` | Phase 3 Step 4 | Raw -> deduplicated finding counts and merge log |
| `report.md` | Phase 3 | Synthesized findings |
| `fix-journal.md` | Phase 4, per fix round | Cumulative fix history |
| `round-N-score.md` | Phase 4, per round | Weighted score snapshot |
| `round-N-findings.md` | Phase 4, per round | Findings per gate round |
| `round-N-comparison.md` | Phase 4, when judge dispatched | Stagnation judge output |
| `accepted-risks.md` | Phase 4, on user override | Accepted findings with rationale |
| `expected-head.md` | Phase 4, after each fix commit | Current expected HEAD SHA after fix rounds |
| `round-N-verification.md` | Phase 4, after every fix round | Fix verification results per round |

## Recovery Procedure

After compaction:
1. Glob for `active-run-*.md` to locate scratch directory
2. Read `commit-anchor.md`. If `round-N-score.md` files exist (Phase 4 in progress), read `expected-head.md` and verify HEAD against that instead. If no Phase 4 files exist, verify HEAD against commit-anchor.md. Mismatch = abort.
3. Determine phase from file presence:
   - No `gate-approved.md` -> re-present manifest
   - `<agent>-findings.md` files -> count completed agents, dispatch remaining
   - `coverage-map.md` without `chain-analyst-findings.md` -> dispatch Chain Analyst
   - `report.md` without `round-1-score.md` -> enter Phase 4
   - `round-N-score.md` files -> resume gate at round N+1
4. Read `pipeline-status.md` to recover Started timestamp and Recent Events
5. Output status to user before continuing

**Recovery step 0:** Before file-based recovery (Recovery Procedure step 1), read the Compression State from `pipeline-status.md` to re-establish context.

## Checkpoint Timing

Emit a Compression State Block at each of the following points:
- Phase transitions (1->2, 2->3, 3->4, 4->5)
- Every 2 gate rounds in Phase 4
- Before stagnation judge dispatch
- On health transitions (GREEN->YELLOW, YELLOW->RED, etc.)

**Block content:**
```
## Compression State
- Goal: [current siege objective]
- Skill: siege
- Phase: [current phase and step]
- Health: [GREEN|YELLOW|RED]
- Key Decisions: [severity judgments from Phase 3, accepted risks, stagnation outcomes]
- Active Constraints: [commit anchor SHA, expected-head SHA, gate round, score trajectory]
- Next Steps: [immediate next action]
```
