# Phase 0: Baseline Token Measurement Results

**Date:** 2026-04-05
**Method:** Word-count proxy (words × 1.3) — fallback, #106 not yet available
**Pipeline model:** 8-task build (54 dispatches across 4 phases)

## Measurement Approach

Read all 6 highest-frequency dispatch templates, measured static word counts, estimated injected context based on placeholder descriptions. Two independent measurements taken:

### Method A: Lines × 4 (conservative, from earlier template analysis)

| Template | Static tokens | Injected tokens | Total expanded | Frequency (8-task) |
|---|---|---|---|---|
| build-implementer | 560 | 580 | 1,140 | 8× |
| build-reviewer | 680 | 680 | 1,360 | 8× |
| cleanup | 280 | 1,000 | 1,280 | 8× |
| investigator | 600 | 1,480 | 2,080 | 3-6× |
| red-team | 540 | 2,520 | 3,060 | 4-8× |
| fix-verifier | 280 | 1,560 | 1,840 | 2-4× |

### Method B: Words × 1.3 (generous, full word count)

| Template | Static tokens | Injected tokens | Total expanded | Frequency (8-task) |
|---|---|---|---|---|
| build-implementer | 2,401 | 1,040 | 3,441 | 8× |
| build-reviewer | 2,813 | 1,560 | 4,373 | 8× |
| cleanup | 1,158 | 390 | 1,548 | 8× |
| investigator | 5,001 | 2,600 | 7,601 | 3-6× |
| red-team | 2,110 | 1,950 | 4,060 | 4-8× |
| fix-verifier | 1,101 | 520 | 1,621 | 2-4× |

## Pipeline Totals

| Phase | Dispatches | Method A (conservative) | Method B (generous) |
|---|---|---|---|
| Phase 1 (Design) | 4-6 | 4-12K | 27K |
| Phase 2 (Plan + gate) | 8-19 | 8-57K | 16K |
| Phase 3 (per-task ×8) | 32-48 | 35-67K | 107K |
| Phase 4 (review + gate) | 8-20 | 12-60K | 28K |
| **Total** | **52-93** | **59-196K** | **178K** |

**Best estimate (midpoint):** ~73-131K tokens (used in design doc, represents the realistic operating range).

## Autocompact Behavior

**Observation:** We cannot directly measure what autocompact does to tool call bodies from within a session — Claude Code does not expose context composition. The project's `claude-code-internals.md` describes microcompaction as handling tool *outputs* (Read results, Bash output), not tool *inputs* (prompt parameters).

**Conservative assumption:** Even if autocompact compresses 50% of tool call bodies (which would be surprisingly aggressive — tool calls are structured interaction records), the remaining tokens would be:
- Method A: 30-98K (still well above 20K)
- Method B: 89K (still well above 20K)

**Recommendation:** Proceed. Measure actual compression behavior post-implementation via #106 when available.

## Decision Gate

| Criterion | Threshold | Result |
|---|---|---|
| Projected savings from disk-mediated dispatch | ≥ 20K tokens | **59-178K tokens** |
| Decision | | **PASS — proceed to Task 2** |

Even the most conservative estimate (Method A low end, 50% autocompact compression) yields ~30K — above the 20K threshold.

## Limitations

1. Word-count proxy is approximate — actual tokenization varies by model
2. Cannot observe autocompact behavior directly from within a session
3. Injected context sizes estimated from placeholder descriptions, not measured from real pipeline data
4. Phase dispatch counts are estimates based on plan analysis, not observed runs

---

## Phase 2.5: Pointer Prompt Length Validation

**Date:** 2026-04-05
**Method:** Word-count proxy (words × 1.3)
**Scope:** 75 dispatch points across 71 template files (design/investigation-prompts.md contains 4 sub-templates)

### Results

| Metric | Value |
|---|---|
| Templates within 80-token target | **75/75 (100%)** |
| Templates exceeding 80 tokens | 0 |
| Templates exceeding 120-token ceiling | 0 |
| Longest pointer prompt | ~44 tokens (stagnation judge, integration check) |
| Shortest pointer prompt | ~33 tokens (cleanup, acceptance-test-writer) |
| Median | ~38 tokens |

### Top 5 Longest

| Template | Words | Est. Tokens |
|---|---|---|
| quality-gate/stagnation-judge | 34 | 44 |
| spec/integration-check | 34 | 44 |
| debugging/test-gap-writer | 33 | 43 |
| migrate/compatibility-designer | 33 | 43 |
| siege/siege-betrayed-consumer | 32 | 42 |

### Decision

**PASS.** All 75 dispatch points fit within the 80-token target with substantial headroom (~36 tokens of margin at the worst case). No role descriptions need shortening. Even with 20% tokenizer variance, the absolute worst case would be ~53 tokens — still under the 80-token target.
