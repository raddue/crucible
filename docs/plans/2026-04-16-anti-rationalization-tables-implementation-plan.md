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
  2. The awk block in the post-impl Verification Checklist (AC-2) reports
     `5 ≤ data-row-count ≤ 8` for `skills/build/SKILL.md`.
- **Rollback:** `git checkout -- skills/build/SKILL.md`.

### T2: Insert table into `skills/spec/SKILL.md`

- **Insertion point:** after the `## Communication Requirement
  (Non-Negotiable)` section body (ends at line 38 with the example-narration
  blockquote; line 39 is blank) and before line 40 (`## Pipeline Status`).
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
  Verified headings (line numbers as of HEAD `4b8eb02`): `## Consensus
  Detection` (20), `## External Model Review (Optional)` (40), `## How It
  Works` (99), `## Non-Skippability` (134). Note: `## Non-Skippability` sits
  AFTER `## How It Works`, so the before-`## How It Works` placement is the
  correct framing/procedure boundary. If lines have shifted at implementation
  time, re-locate the first heading whose body begins the procedural
  walkthrough and insert immediately before it.
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

- [ ] AC-1: `for f in skills/build/SKILL.md skills/spec/SKILL.md skills/quality-gate/SKILL.md skills/design/SKILL.md; do
  grep -l 'Anti-Rationalization' "$f"; done` prints all 4 paths.
- [ ] AC-2: For each of the 4 files, the awk block below prints a data-row
  count of 5–8 (inclusive) between the `## Anti-Rationalization Table` heading
  and the next `## ` heading:

  ```bash
  for f in skills/build/SKILL.md skills/spec/SKILL.md skills/quality-gate/SKILL.md skills/design/SKILL.md; do
    awk '
      /^## Anti-Rationalization Table/ {in_tbl=1; next}
      in_tbl && /^## / {in_tbl=0}
      in_tbl && /^\|/ {n++}
      END {print FILENAME": "(n>=2?n-2:0)" data rows"}
    ' "$f"
  done
  ```

  (Subtracts 2 for the header row and the `|---|` separator row; asserts
  `5 ≤ count ≤ 8` per DEC-5.)
- [ ] AC-3: All 4 paths in AC-1 end in `SKILL.md` (not a sidecar file).
- [ ] AC-4: For each file, the line number of `## Anti-Rationalization Table`
  is less than the line number of the first procedural heading listed in
  INV-4 of the contract. Quick check:

  ```bash
  for f in skills/build/SKILL.md skills/spec/SKILL.md skills/quality-gate/SKILL.md skills/design/SKILL.md; do
    tbl=$(grep -n '^## Anti-Rationalization Table' "$f" | head -1 | cut -d: -f1)
    proc=$(grep -nE '^## (The Process|Gate Ledger Protocol|Pipeline Status|Orchestration Flow|How It Works|Phase [0-9])' "$f" | head -1 | cut -d: -f1)
    echo "$f: table@${tbl} proc@${proc}"
    [ -n "$tbl" ] && [ -n "$proc" ] && [ "$tbl" -lt "$proc" ] || echo "  FAIL"
  done
  ```
- [ ] AC-5 (heading format, load-bearing): exactly one match per file for the
  em-dash heading — `grep -c '^## Anti-Rationalization Table — ' <file>`
  returns `1` for all 4 files. ASCII `--` will fail this check, protecting
  INV from accidental ASCII substitution.
- [ ] INV-5 (additive-only): `git diff HEAD~N -- skills/*/SKILL.md` on the
  #176 commits shows no deletions inside existing `## Red Flags` blocks.
- [ ] Quality gate dispatched on the changed docs before commit (per
  `feedback_quality_gate_always`).
- [ ] Innovate + red-team run on the final set (per `feedback_never_skip_gates`).

## Effort Estimate

- T1–T4: ~5 minutes each = 20 minutes of edit work.
- Quality gate + innovate + red-team: 15–30 minutes.
- Total: <1 hour.
