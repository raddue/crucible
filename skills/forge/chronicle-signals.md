# Chronicle Signals Reference

Chronicle signals are always-on operational metrics appended after every significant task retrospective (Step 8.5). They contain no prompt content or task descriptions — only operational facts. No redaction is required.

## Signal Schema

Each signal is a single JSON line appended to `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl`:

- `v`: 1 (schema version)
- `ts`: ISO-8601 completion timestamp
- `skill`: The Crucible skill that just completed
- `outcome`: From retrospective's outcome field (success/failure/partial)
- `duration_m`: Wall clock minutes from start to completion
- `branch`: Current git branch
- `files_touched`: Project-relative paths of files modified during the skill invocation
- `metrics`: Skill-specific metrics bag (see table below)

If the file or directory doesn't exist, create it.

## Efficiency Sub-Object Computation

The `metrics.efficiency` sub-object is computed from enriched manifest data when available. If no enriched manifest entries exist (pre-enrichment run), omit the sub-object entirely — no zeros, no nulls.

When enriched entries exist:

1. Locate the dispatch directory from the `.dispatch-active-*` marker in the pipeline's scratch directory, or from the metrics log.
2. Read `manifest.jsonl` from the dispatch directory.
3. Check whether any manifest entries have `input_chars` populated (non-null). If none do, skip.
4. If enriched entries exist, compute:
   - `total_input_chars`: sum of all `input_chars` values (skip nulls)
   - `total_output_chars`: sum of all `output_chars` values (skip nulls)
   - `est_input_tokens`: `total_input_chars / 4` (rounded to nearest integer)
   - `est_output_tokens`: `total_output_chars / 4` (rounded to nearest integer)
   - `dispatches_by_tier`: count of dispatches grouped by `model_tier` (e.g., `{"opus": 5, "sonnet": 8, "haiku": 2}`) — skip null tiers
   - `est_rework_tokens`: for any `seq` with a failed/errored entry followed by a retry, sum the retry's `(input_chars + output_chars) / 4`. `0` if no retries occurred.
   - `rework_pct`: `est_rework_tokens / (est_input_tokens + est_output_tokens) * 100`, rounded to 1 decimal
   - `active_work_m`: from existing metrics log computation (overlapping parallel intervals merged)
   - `wall_clock_m`: from existing duration computation
5. Include as `metrics.efficiency` in the signal entry.

## Signal Examples

**With efficiency (enriched manifest data available):**
```jsonl
{"v":1,"ts":"2026-03-25T10:00:00Z","skill":"build","outcome":"success","duration_m":42,"branch":"feat/auth-refactor","files_touched":["src/auth/token.ts","src/auth/refresh.ts"],"metrics":{"mode":"feature","tasks":5,"tasks_passed":5,"qg_rounds":3,"review_rounds":2,"stagnation":false,"efficiency":{"total_input_chars":128400,"total_output_chars":82000,"est_input_tokens":32100,"est_output_tokens":20500,"est_rework_tokens":4200,"rework_pct":8.0,"dispatches_by_tier":{"opus":5,"sonnet":8,"haiku":2},"active_work_m":28,"wall_clock_m":42}}}
```

**Without efficiency (pre-enrichment or no manifest data):**
```jsonl
{"v":1,"ts":"2026-03-25T10:00:00Z","skill":"build","outcome":"success","duration_m":42,"branch":"feat/auth-refactor","files_touched":["src/auth/token.ts","src/auth/refresh.ts"],"metrics":{"mode":"feature","tasks":5,"tasks_passed":5,"qg_rounds":3,"review_rounds":2,"stagnation":false}}
```

## Metrics Bag by Skill

| Skill | Metrics |
|-------|---------|
| build | mode, tasks, tasks_passed, qg_rounds, review_rounds, stagnation |
| debugging | hypotheses, root_cause_category, where_else_hits |
| quality-gate | artifact_type, rounds, fatals_found, stagnation |
| design | questions_investigated, auto_resolved |
| planning | task_count, review_rounds |
| audit | findings_count, lenses_dispatched |
| code-review | rounds, findings_by_severity |
| TDD | cycles, red_green_refactor_count |
| *all skills* | efficiency (optional sub-object, present only when enriched manifest data exists) |

## Signal Scope Rule

Emit one signal per top-level skill invocation, not per sub-skill dispatch. When build calls quality-gate internally, quality-gate does NOT emit its own signal — its metrics are captured in build's metrics bag. Standalone invocations of quality-gate, code-review, etc. DO emit signals.

This is self-enforcing: forge retrospective only runs at the end of a top-level skill invocation, so Step 8.5 naturally fires once per top-level skill. Sub-skills called within build do not trigger their own forge retrospective.

## Chronicle Signals Without Retrospective

Any skill that completes a significant task SHOULD append a minimal chronicle signal if no forge retrospective is expected to run. The minimal signal uses `outcome` from the skill's own completion status, `files_touched` from `git diff --name-only`, and whatever metrics are available in context. Chronicle signals require no redaction (they contain no prompt content), so the fallback path is simpler than trajectory fallback. This ensures chronicle data is captured even when forge does not run.

## Summary Regeneration (Feed-Forward Context)

During feed-forward (Mode 2, Step 3.5), the chronicle summary is regenerated when `signals.jsonl` is newer than `summary.md`:

1. Read all signals from `signals.jsonl`
2. Compute:
   - **Hotspots:** Group `files_touched` by cartographer module (if module maps exist) or by directory prefix. A module qualifies as a hotspot when it has 3+ signals with friction indicators (`stagnation=true`, `metrics.qg_rounds>2`, `skill="debugging"`, or `outcome="failure"/"stagnation"`). Show top 5 hotspots sorted by signal count.
   - **Skill Performance:** Aggregate runs, avg duration, avg QG rounds, stagnation rate, success rate per skill. Cap at 8 rows.
   - **Trends:** Compare last 10 signals vs prior 10 for key metrics.
   - **Recent Friction:** Last 5 signals with friction indicators.
3. **Hard cap at 100 lines** — drop Trends and Recent Friction sections first if needed.
4. Write regenerated summary to `chronicle/summary.md`
