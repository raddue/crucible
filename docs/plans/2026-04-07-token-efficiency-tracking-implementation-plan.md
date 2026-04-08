---
ticket: "#106"
title: "Token Efficiency Tracking — Implementation Plan"
date: "2026-04-07"
source: "spec"
---

# Token Efficiency Tracking — Implementation Plan

## Task Overview

8 tasks across 3 waves. Wave 1: feasibility spike + manifest enrichment (the foundation). Wave 2: chronicle integration + forge wiring (aggregation layer). Wave 3: stocktake reporting + build pipeline integration (reporting layer).

## Wave 1: Foundation — Feasibility Spike + Manifest Enrichment

### Task 1: Feasibility spike — measure what session JSONL actually contains

**Files:** None modified (investigation only)
**Complexity:** Small
**Dependencies:** None

Investigate the actual content of Claude Code session JSONL files at `~/.claude/projects/<hash>/<session-id>/`:
- Determine whether token count fields are present in session log entries
- Document the entry schema (fields, types, structure)
- Assess whether entries can be correlated to specific subagent dispatches
- Determine flush timing (can a skill read its own session log mid-execution?)

**Output:** A findings document at `docs/plans/2026-xx-xx-token-tracking-spike-results.md` with:
- Annotated sample entries (redacted)
- Field inventory with types
- Assessment of each field's reliability for token estimation
- Go/no-go recommendation on session log parsing

**Done when:** Findings document committed with clear go/no-go on session log parsing. If go: update the design doc to incorporate session log data. If no-go (expected): confirm the char-count proxy approach and proceed to Task 2.

### Task 2: Enrich dispatch manifest with size fields

**Files:** `skills/shared/dispatch-convention.md`
**Complexity:** Medium
**Dependencies:** Task 1 (confirms approach)

Update the dispatch convention to include measurement steps in the protocol:

1. Add to "Protocol: Write Before Dispatch" section:
   - Before dispatching: measure dispatch file size in characters → include `input_chars` in the manifest entry
   - After dispatch returns: measure response length in characters → include `output_chars`, `model_tier`, `tool_calls` in the completion entry

2. Update the "Entry Format" section:
   - Add `input_chars`, `output_chars`, `model_tier`, `tool_calls` to the field list
   - Document that these fields are optional (null for pre-enrichment entries)
   - Add note about backward compatibility

3. Update the example entry to show the new fields.

4. Add a "Token Estimation" subsection under the manifest section:
   - Document the chars/4 estimation methodology
   - State the +/-20% accuracy expectation
   - List known blind spots (extended thinking, prompt cache, context carry-forward)

**Done when:** `dispatch-convention.md` updated with measurement protocol and field definitions. No code changes — this is a protocol document update.

### Task 3: Implement measurement in a reference skill

**Files:** `skills/build/SKILL.md`
**Complexity:** Medium
**Dependencies:** Task 2

Update the build skill's dispatch orchestration to implement the enriched manifest protocol:

1. In Phase 2 (planning) and Phase 3 (execution) dispatch logic:
   - Before writing manifest "dispatched" entry: read dispatch file, measure `len(content)` → `input_chars`
   - After subagent returns: measure response length → `output_chars`
   - Record model tier from the dispatch decision → `model_tier`
   - Record tool call count if available from response → `tool_calls` (null if not available)

2. In Phase 4 Step 9 (pipeline summary):
   - Read manifest, compute totals: `sum(input_chars)`, `sum(output_chars)`, dispatch count by tier
   - Add efficiency summary to the pipeline completion report (alongside existing subagent summary)

3. Extend the Session Metrics section to include efficiency metrics in the completion summary block.

**Done when:** Build SKILL.md includes manifest measurement instructions and efficiency summary in pipeline report. A test build run produces manifest entries with the new fields populated.

## Wave 2: Aggregation — Chronicle Integration + Forge Wiring

### Task 4: Extend chronicle signal with efficiency sub-object

**Files:** `skills/forge-skill/SKILL.md`
**Complexity:** Medium
**Dependencies:** Task 2, Task 3

Update the forge skill's chronicle signal emission (Step 8.5):

1. After reading the metrics log, also read `manifest.jsonl` from the dispatch directory (path available from `.dispatch-active-*` marker or from metrics log).

2. Compute efficiency aggregate from manifest entries:
   - `total_input_chars`: sum of all `input_chars` values
   - `total_output_chars`: sum of all `output_chars` values
   - `est_input_tokens`: `total_input_chars / 4` (rounded)
   - `est_output_tokens`: `total_output_chars / 4` (rounded)
   - `dispatches_by_tier`: count of dispatches grouped by `model_tier`
   - `active_work_m`: from existing metrics log computation
   - `wall_clock_m`: from existing duration computation

3. Include as `efficiency` sub-object in the signal's `metrics` bag.

4. Update the "Metrics bag by skill" table to document the `efficiency` sub-object availability for all skills that use dispatch.

5. Handle missing data gracefully: if manifest has no `input_chars` fields (pre-enrichment run), omit the `efficiency` sub-object entirely rather than emitting zeros.

**Done when:** Forge SKILL.md updated. A forge retrospective after a build run produces a chronicle signal with the `efficiency` sub-object populated.

### Task 5: Add efficiency fields to debugging skill

**Files:** `skills/debugging/SKILL.md`
**Complexity:** Small
**Dependencies:** Task 2

Mirror Task 3's manifest measurement changes for the debugging skill:
- Add `input_chars`/`output_chars`/`model_tier` measurement to dispatch orchestration
- Add efficiency summary to the debugging completion report

This is the second-heaviest dispatch user after build.

**Done when:** Debugging SKILL.md includes manifest measurement instructions. Both build and debugging produce enriched manifests.

### Task 6: Propagate to remaining orchestrator skills

**Files:** Multiple SKILL.md files (design, quality-gate, siege, audit, spec, migrate, etc.)
**Complexity:** Small (per skill, but many skills)
**Dependencies:** Task 2

Since the measurement protocol is defined in the shared `dispatch-convention.md`, all orchestrator skills that reference it will pick up the protocol. This task verifies each one:

1. For each skill that dispatches subagents (identified by `<!-- CANONICAL: shared/dispatch-convention.md -->` comment):
   - Verify the skill's dispatch logic is compatible with the enriched manifest fields
   - Add skill-specific efficiency metrics to the skill's pipeline summary if applicable
   - No changes needed if the skill simply follows dispatch-convention without custom logic

2. Skills requiring updates (custom dispatch logic):
   - `build` — Done in Task 3
   - `debugging` — Done in Task 5
   - `siege` — May need per-lens efficiency breakdown
   - `spec` — May benefit from per-ticket efficiency tracking
   - Others — Follow convention, likely no changes needed

**Done when:** All orchestrator skills confirmed compatible with enriched manifest. Skills with custom dispatch logic updated.

## Wave 3: Reporting — Stocktake Integration + Baseline Comparison

### Task 7: Add efficiency mode to stocktake

**Files:** `skills/stocktake/SKILL.md`
**Complexity:** Large
**Dependencies:** Task 4 (needs chronicle signals with efficiency data)

Add a new mode to stocktake:

1. **Mode table update:**

   | Mode | Trigger | Duration |
   |------|---------|----------|
   | Quick scan | `results.json` exists (default) | ~5 min |
   | Full stocktake | `results.json` absent, or `/stocktake full` | ~20 min |
   | Efficiency report | `/stocktake efficiency` | ~5 min |

2. **Efficiency report flow:**
   - Read `chronicle/signals.jsonl`
   - Filter to signals with `efficiency` sub-object
   - Group by skill
   - Compute per-skill: average est_input_tokens, average est_output_tokens, average duration_m, average dispatches, trend (last 5 runs)
   - Compute cross-skill: total estimated tokens across all tracked runs, busiest skill, most efficient skill (tokens per unit of work)

3. **Report format:**

   ```
   ## Skill Efficiency Report
   **Period:** <oldest signal date> to <newest signal date>
   **Tracked runs:** N
   **Disclaimer:** Token estimates based on dispatch file sizes (chars/4). Actual consumption may vary +/-30%.

   ### Per-Skill Summary
   | Skill | Runs | Avg Est. Tokens (in+out) | Avg Duration | Avg Dispatches | Trend |
   |-------|------|--------------------------|--------------|----------------|-------|

   ### Dispatch Breakdown
   | Skill | Opus % | Sonnet % | Haiku % | Review % | Impl % |
   |-------|--------|----------|---------|----------|--------|

   ### Structural Efficiency
   | Skill | Avg Input/Dispatch | Context Distribution | Quality Overhead % |
   |-------|--------------------|-----------------------|--------------------|
   ```

4. **Cache in results.json** under a new `efficiency` key (separate from the skill verdict cache).

**Done when:** `/stocktake efficiency` produces a report from chronicle signal data. Report includes per-skill breakdown, dispatch analysis, and structural efficiency metrics.

### Task 8: Baseline comparison framework

**Files:** `skills/stocktake/SKILL.md` (extend efficiency mode)
**Complexity:** Medium
**Dependencies:** Task 7

Add baseline comparison to the efficiency report:

1. **Monolithic baseline estimate:** For each tracked run, compute what a single-prompt approach would require:
   - `baseline_input = sum(all dispatch input_chars) + sum(all file reads referenced in dispatches)`
   - This is an overestimate (a monolithic prompt might not need all files), but it's the structural worst-case.

2. **Context distribution metric:** `avg_input_per_dispatch / monolithic_baseline` — measures how much the skill distributes context vs. loading everything at once.

3. **Quality investment metric:** `review_dispatches / total_dispatches` — what fraction of work is quality assurance.

4. **Add to report:**

   ```
   ### Baseline Comparison (Structural)
   | Skill | Avg Monolithic Est. | Avg Distributed Est. | Distribution Ratio | Quality Investment |
   |-------|---------------------|----------------------|--------------------|--------------------|

   **Interpretation:** Distribution ratio < 1.0 means the skill sends less context per dispatch
   than a monolithic approach would require. Quality investment shows the fraction of dispatches
   dedicated to review, red-team, and quality gates.
   ```

**Done when:** Efficiency report includes baseline comparison section with structural metrics. Report honestly frames these as structural comparisons, not cost savings claims.

## Definition of Done (Overall)

1. `dispatch-convention.md` defines the enriched manifest protocol with measurement steps
2. Build and debugging skills implement manifest enrichment
3. Forge emits chronicle signals with efficiency sub-objects
4. Stocktake has an efficiency reporting mode that reads chronicle signals
5. All reporting includes accuracy disclaimers
6. No breaking changes to existing manifest or chronicle signal consumers
7. Feasibility spike results documented (confirming or updating the proxy approach)
