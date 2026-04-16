---
ticket: "#176"
epic: "#176"
title: "Anti-rationalization tables for skill hardening"
date: "2026-04-16"
source: "spec"
---

# Implementation Plan

## Overview

Additive-only change. Insert a pre-authored `## Anti-Rationalization Table`
section into each of four `SKILL.md` files. Tables are fully authored in the
design doc — implementation is purely mechanical (locate insertion point, paste
table, verify).

- **Complexity tier:** Tier 1 (docs/config only, no code paths, no tests).
- **Files touched:** 4 (one per skill).
- **Parallelism:** all 4 tasks are independent and safely parallelizable.
- **Dependencies:** none — design doc is self-contained. No other ticket
  dependencies.
- **Backout plan:** revert the commit. No runtime state, no migrations.

## Task Breakdown

### T1: Insert table into `skills/build/SKILL.md`

- **Insertion point:** immediately after line 46 (end of `## Pipeline
  Discipline (Non-Negotiable)` section body, which ends "Run the gate.") and
  before line 48 (`## Gate Ledger Protocol`). This places the table between the
  two non-negotiable preambles and the procedural gate-ledger walkthrough.
- **Action:** Edit tool. Insert the table authored in the design doc under
  heading `## Anti-Rationalization Table — build`.
- **Verification:**
  1. `grep -n 'Anti-Rationalization' skills/build/SKILL.md` returns a line in
     the 47–50 range.
  2. `grep -c '^| ' skills/build/SKILL.md` — count increases by the number of
     data rows + 1 (header) + 1 (separator).
- **Rollback:** `git checkout -- skills/build/SKILL.md`.

### T2: Insert table into `skills/spec/SKILL.md`

- **Insertion point:** after line 39 (end of `## Communication Requirement
  (Non-Negotiable)` section body) and before line 40 (`## Pipeline Status`).
- **Action:** Edit tool. Insert the table under heading
  `## Anti-Rationalization Table — spec`.
- **Verification:**
  1. `grep -n 'Anti-Rationalization' skills/spec/SKILL.md` returns a line in
     the 40–45 range.
  2. Row count check as in T1.
- **Rollback:** `git checkout -- skills/spec/SKILL.md`.

### T3: Insert table into `skills/quality-gate/SKILL.md`

- **Insertion point:** after line 97 (end of `## External Model Review
  (Optional)` / Graceful Degradation section) and before line 99 (`## How It
  Works`). This places it immediately before the procedural walkthrough.
  (If the skill is re-read at implementation time and a `## Non-Skippability`
  section lives closer to the top, prefer placing the table immediately after
  `## Non-Skippability` and before `## Fix Mechanism` — whichever is closer to
  the transition from framing to procedure. Re-verify during implementation.)
- **Action:** Edit tool. Insert the table under heading
  `## Anti-Rationalization Table — quality-gate`.
- **Verification:** as in T1/T2.
- **Rollback:** `git checkout -- skills/quality-gate/SKILL.md`.

### T4: Insert table into `skills/design/SKILL.md`

- **Insertion point:** after line 15 (end of `## Overview`) and before line 17
  (`## The Process`). Design has no `## Communication Requirement`
  non-negotiable preamble, so the overview/process boundary is the correct
  handoff point.
- **Action:** Edit tool. Insert the table under heading
  `## Anti-Rationalization Table — design`.
- **Verification:** as in T1/T2.
- **Rollback:** `git checkout -- skills/design/SKILL.md`.

## Implementation Notes

- **Copy tables verbatim** from the design doc. Do not re-author during
  implementation — the design is intentionally exhaustive so implementation is
  mechanical.
- **Heading format:** use the literal string `## Anti-Rationalization Table —
  <skill>` (em-dash, one space on each side). This is the exact string the
  verification script matches on.
- **Do not modify** existing `## Red Flags` sections. The table is additive.
- **Biome/format:** these are markdown files; no formatter required, but
  preserve UTF-8 em-dashes (not ASCII `--`).
- **Commits:** one commit per task is fine (4 small commits), or one combined
  commit. No preference, so long as each commit message references `#176`.

## Verification Checklist (post-implementation)

- [ ] AC-1: `for f in skills/{build,spec,quality-gate,design}/SKILL.md; do
  grep -l 'Anti-Rationalization' "$f"; done` prints all 4 paths.
- [ ] AC-2: Each table has ≥5 data rows (counted between the heading and the
  next `## ` heading, subtracting 2 for header+separator).
- [ ] AC-3: Each table is in `SKILL.md`, not a sidecar file.
- [ ] AC-4: Each table precedes the first procedural section.
- [ ] Quality gate dispatched on the changed docs before commit (per
  `feedback_quality_gate_always`).
- [ ] Innovate + red-team run on the final set (per `feedback_never_skip_gates`).

## Effort Estimate

- T1–T4: ~5 minutes each = 20 minutes of edit work.
- Quality gate + innovate + red-team: 15–30 minutes.
- Total: <1 hour.
