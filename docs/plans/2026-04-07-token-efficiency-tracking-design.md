---
ticket: "#106"
title: "Token Efficiency Tracking for Skills"
date: "2026-04-07"
source: "spec"
---

# Token Efficiency Tracking — Design Document

**Goal:** Give the Crucible skill framework visibility into token consumption per skill invocation, enabling data-driven comparison of skill-assisted vs. baseline task completion and identification of which skills deliver the most efficiency.

**Core tension:** Claude Code does not expose per-invocation token counts through any programmatic API. This design must work within that constraint, building on what IS available (timing, dispatch counts, JSONL session logs, file sizes) rather than pretending exact token counts are obtainable.

## 1. Current State Analysis

### What We Already Track

The framework already captures meaningful operational data:

| Data Source | What It Captures | Where |
|---|---|---|
| Chronicle signals | Skill name, outcome, duration_m, files_touched, skill-specific metrics | `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl` |
| Dispatch manifest | Per-subagent seq, role, phase, status, duration_s, summary | `/tmp/crucible-dispatch-<session-id>/manifest.jsonl` |
| Session metrics log | Subagent dispatch/completion timestamps, model tiers (Opus/Sonnet/Haiku) | `/tmp/crucible-metrics-<session-id>.log` |
| Decision journal | Routing decisions (model selection, tier assignment, escalation) | `/tmp/crucible-decisions-<session-id>.log` |
| Trajectory capture | Full execution trace (opt-in), prompt summaries, outcomes | `~/.claude/projects/<hash>/memory/trajectories/` |

### What We Don't Have

- **Per-invocation input/output token counts.** Claude Code does not surface these in any hook, API response, or log file accessible to skills.
- **API cost data.** No per-request billing information is available to the conversation context.
- **Prompt cache hit rates.** Subagents share prompt caches (per `claude-code-internals.md`), but cache efficiency is invisible to the skill layer.

### Session JSONL Logs

Claude Code persists conversations as JSONL at `~/.claude/projects/<hash>/<session-id>/`. These files contain conversation turns including tool calls and responses. However:

1. **Access timing:** Session logs are written during/after conversation turns. A skill cannot reliably read its own session log mid-execution to extract token counts — the log may not be flushed, and the skill is part of the same conversation being logged.
2. **Format stability:** The JSONL schema is not part of Claude Code's public API. Parsing it creates a fragile dependency on internal implementation details.
3. **Token fields:** Session JSONL entries may or may not include token count fields. Even if present today, this is an implementation detail that could change without notice.

**Decision:** Do not parse session JSONL logs for token data. The coupling is too fragile and the access timing problem makes it unreliable for live instrumentation.

## 2. Feasibility Assessment

### What IS Feasible (High Confidence)

1. **Proxy metrics via timing + dispatch counts.** Duration is already tracked. Subagent counts by model tier are already tracked. These correlate with token consumption — more subagents for longer durations means more tokens.

2. **Input size estimation.** Skills know what they feed to subagents: dispatch file sizes, code file sizes read during investigation, document sizes. We can measure the input payload size in characters/words as a proxy for input tokens.

3. **Dispatch file token estimation.** Every dispatch uses disk-mediated files. The file size of dispatch files (template + expanded context) is a direct proxy for input tokens to that subagent. We already write these files — measuring them costs nothing.

4. **Output size estimation.** Subagent outputs are captured in dispatch file responses, commit diffs, and written artifacts. These are measurable after the fact.

5. **Relative comparison.** Even without exact token counts, we can compare the same task type across runs — "this build used 12 subagents over 45 minutes vs. that build used 23 subagents over 2 hours." Relative comparisons are valid even with proxy metrics.

### What IS NOT Feasible (Current Architecture)

1. **Exact per-invocation token counts.** No mechanism exists to capture these without Claude Code platform changes.

2. **Prompt cache attribution.** Cannot measure how much a subagent's prompt was served from cache vs. computed fresh.

3. **Real-time cost tracking.** No per-request billing data available.

### Estimation Methodology

The core insight: **we can estimate tokens from what we control (inputs we write, outputs we receive) even though we cannot measure what the model processes internally.**

**Character-to-token ratio:** For English text, 1 token ~= 4 characters. For code, 1 token ~= 3.5 characters. These ratios are well-established approximations from tokenizer analysis. We use `chars / 4` as the default estimator, acknowledged as +/-20% accurate.

**What we can measure per dispatch:**

| Metric | Source | Accuracy |
|---|---|---|
| Input estimate (tokens) | Dispatch file size in chars / 4 | +/-20% of actual input tokens for that subagent |
| Output estimate (tokens) | Subagent response length in chars / 4 | +/-20% of actual output tokens |
| System prompt overhead | Constant per model tier (~2000 tokens Opus, ~1500 Sonnet, ~800 Haiku) | Known from public documentation |
| Tool call overhead | Count of tool calls * ~50 tokens average | Rough estimate |

**What we CANNOT measure:**

| Missing | Impact |
|---|---|
| Prompt cache hits | Overestimates cost for cache-warm subagents |
| Internal reasoning tokens | Underestimates total processing (extended thinking not captured) |
| Context window carry-forward | Orchestrator context grows across dispatches; not captured per-dispatch |

**Accuracy guarantee:** Estimates are directionally correct and useful for relative comparison. They should NOT be interpreted as billing-accurate token counts. All reporting must include the disclaimer: "Estimates based on dispatch file sizes. Actual token consumption may vary +/-30%."

## 3. Architecture

### Layered Approach

```
Layer 3: Reporting (stocktake integration, efficiency dashboard)
Layer 2: Aggregation (per-skill totals, trend analysis, comparison)  
Layer 1: Collection (per-dispatch measurements, enriched manifest)
```

### Layer 1: Enriched Dispatch Manifest

Extend the existing `manifest.jsonl` entry format with token estimation fields. The manifest already tracks `duration_s` — adding size-based estimates is a natural extension.

**Extended manifest entry:**

```jsonl
{"seq":1,"file":"1-plan-writer.md","role":"plan-writer","phase":"2","task":null,"status":"completed","duration_s":83,"summary":"Plan written: 8 tasks, 3 waves","input_chars":12840,"output_chars":8200,"model_tier":"opus","tool_calls":5}
```

New fields:
- `input_chars` — dispatch file size in characters (measured before dispatch)
- `output_chars` — subagent response length in characters (measured after completion)
- `model_tier` — "opus", "sonnet", or "haiku" (already tracked in metrics log, now also in manifest)
- `tool_calls` — count of tool invocations by the subagent (if available from response metadata, otherwise null)

**Size constraint:** The manifest entry limit is 4096 bytes (POSIX PIPE_BUF). Adding 4 fields at ~20 chars each is ~80 bytes — well within budget.

**Backward compatibility:** Old manifest entries without these fields are treated as having null values. Reporting gracefully handles missing fields.

### Layer 2: Enriched Chronicle Signal

Extend the chronicle signal with aggregated efficiency metrics computed from the manifest at pipeline completion.

**Extended signal fields (in the metrics bag):**

```jsonl
{
  "v": 2,
  "ts": "2026-04-07T10:00:00Z",
  "skill": "build",
  "outcome": "success",
  "duration_m": 42,
  "branch": "feat/auth-refactor",
  "files_touched": ["src/auth/token.ts"],
  "metrics": {
    "mode": "feature",
    "tasks": 5,
    "tasks_passed": 5,
    "qg_rounds": 3,
    "review_rounds": 2,
    "stagnation": false,
    "efficiency": {
      "total_input_chars": 128400,
      "total_output_chars": 82000,
      "est_input_tokens": 32100,
      "est_output_tokens": 20500,
      "dispatches_by_tier": {"opus": 5, "sonnet": 8, "haiku": 2},
      "active_work_m": 28,
      "wall_clock_m": 42
    }
  }
}
```

The `efficiency` sub-object is optional. Signals without it (v1 signals, signals from before this feature) are valid.

**Schema version bump:** Signal version stays at `v: 1` — the efficiency sub-object is additive and optional. Readers that don't understand `efficiency` ignore it. A v2 bump is reserved for breaking changes.

### Layer 3: Stocktake Efficiency Report

Extend the stocktake skill with an efficiency reporting mode that reads chronicle signals and produces comparative analysis.

**New mode:** `/stocktake efficiency` (or triggered by forge feed-forward when 10+ signals with efficiency data exist).

**Report contents:**

1. **Per-skill efficiency summary** — average estimated tokens per invocation, trend over last N runs
2. **Dispatch breakdown** — which skills use the most subagents, which model tiers, what percentage is review vs. implementation
3. **Duration-to-complexity ratio** — tokens per task (for build), tokens per finding (for quality-gate/siege), tokens per dimension (for design)
4. **Relative comparison** — when the same task type runs multiple times, compare efficiency across runs

### Data Flow

```
Skill invocation starts
  → Orchestrator creates dispatch directory + manifest
  → Per dispatch: measure dispatch file size → write to manifest (input_chars)
  → Per completion: measure response size → append to manifest (output_chars, model_tier)
  → Pipeline completes
  → Forge retrospective reads manifest, computes efficiency aggregate
  → Chronicle signal includes efficiency sub-object
  → Stocktake reads chronicle signals for reporting
```

## 4. Baseline Comparison Framework

The issue asks: "Do skills actually save tokens compared to raw prompting?" This is the hardest question because we cannot run controlled experiments (same task, with and without skills).

### Approach: Structural Baseline Estimation

Instead of running A/B tests, estimate what a no-skill baseline would look like based on structural analysis:

1. **Dispatch overhead baseline.** A skill-less approach would paste all context into a single prompt. The baseline input is: sum of all dispatch file contents + all file contents read during investigation. With skills, this is distributed across subagents with targeted context. The ratio `sum(per-dispatch inputs) / monolithic baseline estimate` measures context efficiency.

2. **Iteration overhead.** Skills add quality gates, review rounds, and red-teaming that a single-prompt approach would skip. This is a tradeoff — more tokens for higher quality. Track `quality_overhead_pct = (review + gate dispatches) / total dispatches` to quantify the investment.

3. **Reuse dividend.** When a skill invocation reuses an existing design doc, plan, or cartographer map, the investigation phase is shorter. Compare investigation dispatch counts for first-run vs. repeat-run on similar tasks.

**Honest limitation:** This framework measures relative efficiency and structural overhead. It cannot prove that skills save tokens in absolute terms because the baseline is estimated, not measured. The framing should be "skills distribute N estimated tokens across M targeted dispatches instead of one monolithic prompt" — which is a structural claim, not a cost claim.

## 5. Integration Points

### Dispatch Convention (shared/dispatch-convention.md)

Add measurement hooks to the existing dispatch protocol:

- **Before dispatch:** Measure dispatch file size → record `input_chars`
- **After completion:** Measure response length → record `output_chars`, `model_tier`, `tool_calls`

This is a protocol-level change that applies to all skills using dispatch-convention, not per-skill instrumentation.

### Forge (forge-skill/SKILL.md)

- Chronicle signal emission (Step 8.5) already reads the metrics log. It would additionally read the manifest to compute the `efficiency` sub-object.
- No change to retrospective format — efficiency data flows through the signal, not the retrospective narrative.

### Stocktake (stocktake/SKILL.md)

- New "efficiency" mode added to the mode table.
- Results cached in `skills/stocktake/results.json` under a new `efficiency` key.

### Build (build/SKILL.md)

- Heaviest user of dispatch — most to gain from tracking.
- Session metrics log already tracks model tiers; manifest enrichment captures the per-dispatch granularity.
- Pipeline summary (Phase 4 Step 9) would include an efficiency summary alongside the existing subagent summary.

## 6. Decision Log

| ID | Decision | Rationale | Alternatives Considered |
|---|---|---|---|
| D1 | Do not parse session JSONL logs | Fragile coupling to Claude Code internals; access timing prevents live use; format not part of public API | Parse JSONL for token fields — rejected due to stability risk |
| D2 | Use char-count / 4 as token estimator | Well-established approximation (+/-20%); zero external dependencies; measurable from data we already write to disk | Tiktoken library — adds Python dependency; cl100k_base tokenizer — requires binary; word count / 0.75 — less accurate for code |
| D3 | Enrich existing manifest rather than new log file | Manifest already exists per dispatch; adding fields is additive; stays within PIPE_BUF limit; no new file management | Separate efficiency log — rejected, adds coordination complexity |
| D4 | Efficiency data in chronicle signal, not retrospective | Signals are machine-readable and aggregatable; retrospectives are narrative and human-readable; efficiency is a metrics concern | Efficiency section in retrospective — rejected, wrong abstraction level |
| D5 | Structural baseline estimation, not A/B testing | Cannot run controlled experiments (no way to run same task with and without skills); structural analysis is honest about limitations | A/B testing — infeasible without task replay; user self-report — subjective and unreliable |
| D6 | Stocktake as the reporting surface | Stocktake already audits skill health; efficiency is a dimension of health; no new skill needed | Dedicated efficiency skill — rejected, would overlap with stocktake; forge — wrong role, forge captures, stocktake reports |
| D7 | No breaking schema changes (v1 signal preserved) | Existing chronicle consumers must not break; additive optional fields are safe | v2 signal schema — rejected, unnecessary for additive changes |

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Token estimates diverge significantly from actual | Medium | Reports mislead about absolute costs | All reporting includes accuracy disclaimer; focus on relative comparison, not absolute counts |
| Manifest size approaches PIPE_BUF limit | Low | Atomic append guarantee lost | Monitor entry sizes; new fields are ~80 bytes on a 4096 byte budget |
| Extended thinking tokens invisible | High | Underestimates total token consumption for Opus subagents | Acknowledge in reporting; extended thinking is a known unmeasurable overhead |
| Prompt cache makes timing unreliable as cost proxy | Medium | Duration varies based on cache warmth, not actual work | Use character counts as primary metric, duration as secondary |
| Stocktake efficiency mode adds maintenance burden | Low | Another mode to keep current | Mode is read-only over existing data; minimal ongoing maintenance |
