---
ticket: "#93"
title: "Semantic dedup for landmine dead-end entries"
date: "2026-04-06"
source: "spec"
---

# Semantic Dedup for Landmine Dead-End Entries

## Current State

Cartographer's recorder prompt (lines 119-123) uses a simple dedup rule: "preserve each distinct failure description as a separate bullet." This is a human-readable instruction — the recorder agent uses judgment to decide if two dead-end descriptions are the same. There's no structured dedup heuristic.

The issue describes a term-overlap heuristic (same file path AND same module AND 3+ shared terms) that was attacked across QG rounds 3, 4, and 7. The current state is actually simpler — the recorder just uses LLM judgment with the instruction "preserve each distinct failure description."

## Change

Replace the informal dedup instruction with explicit semantic dedup guidance in the recorder prompt. Since the recorder is already a Sonnet agent, we don't need a separate dedup dispatch — the recorder performs dedup as part of its normal write operation.

**Enhanced dedup instruction:**

When adding a new dead-end entry to an existing landmine, the recorder must:

1. Read all existing dead-end bullets for that landmine entry
2. For each existing bullet, assess: "Does the new dead-end describe the same failure mechanism and reach the same conclusion as this existing entry?"
3. **DUPLICATE** — Same failure mechanism, same conclusion, possibly different wording → skip the new entry
4. **DISTINCT** — Different failure mechanism OR different conclusion → add as new bullet

**Key distinction:** Two entries that mention the same file but describe different failure modes are DISTINCT. Two entries that describe the same failure mode but use different wording are DUPLICATE.

**Examples:**
- "Timeout in auth when Redis is down" vs "Timeout in auth when Postgres is down" → DISTINCT (different failure mechanism)
- "Redis connection timeout causes auth failure" vs "Auth fails because Redis connection times out" → DUPLICATE (same mechanism, different wording)

## Key Decisions

### DEC-1: Enhance recorder instructions, not add separate dedup agent (High Confidence)

The recorder is already Sonnet — it can do semantic comparison. A separate dedup dispatch adds latency and cost for something that happens within the recorder's existing context window. The recorder already reads existing entries before writing.

## Acceptance Criteria

1. Recorder prompt includes explicit semantic dedup instructions with examples
2. DUPLICATE/DISTINCT framework defined
3. Same-file-different-failure-mode explicitly called out as DISTINCT
4. No new agents or dispatch templates needed
