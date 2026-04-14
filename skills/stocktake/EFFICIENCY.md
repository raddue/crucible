# Efficiency Report — Detailed Flow

Reference document for the stocktake skill's efficiency report mode. See [SKILL.md](./SKILL.md) for the main skill definition.

## Step 1: Load Chronicle Data

1. Read `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl`
2. If the file is missing or empty: report "No efficiency data available. Run a pipeline with enriched manifest tracking to begin collecting data." and stop.
3. Filter to signals that have a `metrics.efficiency` sub-object.
4. If fewer than 3 signals have efficiency data: report available data with caveat: "Insufficient data for trend analysis. N signals available, 3+ recommended for meaningful comparison."
5. Report: "N of M total signals include efficiency data." (where M is total signals, N is signals with efficiency).

## Step 2: Per-Skill Summary

Group filtered signals by `skill`. For each skill, compute:
- **Runs**: count of signals
- **Avg Est. Tokens (in+out)**: average of `(est_input_tokens + est_output_tokens)` across runs
- **Avg Duration**: average `duration_m`
- **Avg Dispatches**: average total dispatches (sum of `dispatches_by_tier` values)
- **Rework %**: average `rework_pct` across runs. If `rework_pct` is missing (pre-rework-tracking signal), display "—"
- **Trend**: compare last 3 runs vs prior 3 runs — "improving" (fewer tokens), "stable" (within 10%), or "increasing" (more tokens). "insufficient data" if fewer than 4 runs.

If any skill has average rework >30%, append a note: "**[skill]**: rework >30% — consider reviewing dispatch templates or quality-gate prompts for this skill."

Output:

```
## Skill Efficiency Report
**Period:** <oldest signal date> to <newest signal date>
**Tracked runs:** N
**Disclaimer:** Estimates based on dispatch file sizes (chars/4). Actual token consumption may vary +/-30%.

### Per-Skill Summary
| Skill | Runs | Avg Est. Tokens (in+out) | Rework % | Avg Duration | Avg Dispatches | Trend |
|-------|------|--------------------------|----------|--------------|----------------|-------|
```

## Step 3: Dispatch Breakdown

For each skill, compute dispatch tier distribution and categorize dispatches as review vs. implementation:
- **Opus/Sonnet/Haiku %**: from `dispatches_by_tier` averaged across runs
- **Review %**: dispatches with role containing "reviewer", "red-team", "quality-gate", "adversarial" as a percentage of total
- **Impl %**: remaining dispatches as a percentage of total

Note: Review vs. implementation breakdown requires reading manifest entries (role field). If manifests are not available (only chronicle signals), report "N/A" for these columns.

Output:

```
### Dispatch Breakdown
| Skill | Opus % | Sonnet % | Haiku % | Review % | Impl % |
|-------|--------|----------|---------|----------|--------|
```

## Step 4: Structural Efficiency

For each skill, compute:
- **Avg Input/Dispatch**: average `total_input_chars / total dispatches` — measures context per subagent
- **Context Distribution**: qualitative assessment — "focused" (<5000 chars avg/dispatch), "moderate" (5000-15000), "heavy" (>15000)
- **Quality Overhead %**: `review dispatches / total dispatches * 100` — what fraction of work is quality assurance (requires manifest data; "N/A" if unavailable)

Output:

```
### Structural Efficiency
| Skill | Avg Input/Dispatch | Context Distribution | Quality Overhead % |
|-------|--------------------|-----------------------|--------------------|
```

## Step 5: Baseline Comparison (Structural)

For each skill with sufficient data (3+ runs):
- **Avg Total Context**: average `(total_input_chars + total_output_chars)` per run — total context the pipeline touched
- **Avg Input/Dispatch**: average `total_input_chars / total dispatches` per run — how much context each subagent receives on average
- **Context Focus Ratio**: `avg input per dispatch / avg total context` — lower values mean each subagent sees a smaller slice of the total, indicating effective context distribution
- **Quality Investment**: `review dispatches / total dispatches` — fraction of dispatches dedicated to quality assurance (requires manifest data; "N/A" if only chronicle signals available)

Output:

```
### Baseline Comparison (Structural)
| Skill | Avg Total Context | Avg Input/Dispatch | Context Focus Ratio | Quality Investment |
|-------|-------------------|--------------------|---------------------|--------------------|

**Interpretation:** Context focus ratio measures how much of the total pipeline context each
subagent receives. Lower values mean more focused dispatches. Quality investment shows the
fraction of dispatches dedicated to review, red-team, and quality gates. These are structural
comparisons, not cost savings claims — they measure how the skill distributes work, not what
a monolithic alternative would cost.
```

## Step 6: Cache Results

Save efficiency report data to `skills/stocktake/results.json` under a new `efficiency` key (separate from the skill verdict cache):

```json
{
  "efficiency": {
    "computed_at": "2026-04-07T10:00:00Z",
    "signals_with_efficiency": 15,
    "total_signals": 42,
    "per_skill": {
      "build": { "runs": 8, "avg_est_tokens": 52600, "avg_duration_m": 45, "trend": "stable" },
      "debugging": { "runs": 5, "avg_est_tokens": 25000, "avg_duration_m": 22, "trend": "improving" }
    }
  }
}
```
