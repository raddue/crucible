---
name: ledger
description: Render the Crucible calibration ledger weekly report — the honest "Crucible caught N silent bugs" headline, verdict breakdown, per-skill severity rates, and the inflation detector. Triggers on "/ledger", "weekly report", "weekly ledger", "caught N", "quality ledger", "calibration report", "render the ledger".
origin: crucible
---

<!-- CANONICAL: shared/ledger-reduce.md -->

# Ledger weekly renderer

Renders `docs/ledger/weekly-YYYY-Www.md` from `.crucible/ledger/runs.jsonl`
(plus `falsification.jsonl` for the cross-link). The SKILL.md is a thin prompt
wrapper; the source of truth is the testable Python core at
`scripts/render_ledger.py`.

**Skill type:** Utility — direct execution, no subagent dispatch.

## Trigger

Manual `/ledger [--weeks N]` (default `N=1`, the most recent ISO week).

## What it does

Invoke the renderer directly:

```
python3 scripts/render_ledger.py --weeks N
```

That command:

1. Reads `.crucible/ledger/runs.jsonl`. **First-time-ever: if the file is
   MISSING, print "no ledger data yet" and exit 0 — do NOT write an empty
   report.**
2. Groups entries by ISO week (`YYYY-Www`).
3. For each of the most-recent `N` weeks, writes `docs/ledger/weekly-YYYY-Www.md`.

## Algorithm summary

- **Tolerant load** (`load_runs`): skips blank / malformed / partial-trailing
  lines, dedups defensively by `(run_id, skill)` latest-position-wins.
- **Honest "caught N" headline** (`caught_count`): counts entries with
  `would_have_shipped_without_gate == true`, **EXCLUDING `backfilled == true`**.
  Backfilled entries carry `severity_histogram: null` ⇒ WHS `null` (the
  mechanical L-3 rule) and are reported in a SEPARATE "Backfilled historical
  context" section — never in the headline (L-5). This is what test T-5 asserts.
- **Per-skill `significant_rate` / `fatal_rate`** (`week_summary`): computed
  **from forward-captured entries only** (`backfilled == false` AND
  `severity_histogram != null`). Raw rates are printed from week 1.
- **Inflation detector (§4a)** (`inflation_alert`): alerts when a skill's
  `significant_rate` or `fatal_rate` exceeds **3× its 4-week rolling median**.
  **Silent for a skill until 4 weeks of forward data exist** (the v1 bootstrap
  — with no forward history yet, the detector is silent, but raw rates still
  print so a human can eyeball drift).
- **Falsified cross-link** (`falsified_count`): the all-time count of falsified
  verdicts via the **L-9 latest-entry-wins reduction** over
  `falsification.jsonl` (`scripts.ledger_reduce.reduce`, the canonical helper
  cited above). **Graceful degradation:** if `falsification.jsonl` is absent
  (Phase 4 reconciler not built yet), the reduction returns `{}` ⇒ count `0`;
  the renderer never crashes.
- **Monthly spot-check (§4a)**: on the first `/ledger` run of a calendar month,
  the report appends an advisory checklist prompting a spot-check of 5 random
  `would_have_shipped_without_gate: true` entries against
  `skills/shared/severity-rubric.md`.

## Commit citations

Design §4 calls for "findings with commit citations". The v1 schema has **no
commit field** (`artifact_hash` is null for backfill). So:

- **Backfilled entries** (`backfill-<PR>-quality-gate`) cite **`PR #<PR>`**,
  extracted from the deterministic `run_id`.
- **Forward entries** (UUIDv7 `run_id`) have no commit in v1 ⇒ the citation is
  omitted gracefully. No SHAs are invented. A future schema rev capturing the
  gating commit can replace this with a real SHA.

## Honest-count rule (binding)

The headline is `would_have_shipped_without_gate == true` **minus backfilled**.
Backfilled entries seed the corpus but never inflate the caught-N number; they
appear only in the separate historical-context section. Inflation drift is
defended structurally (the 3× detector) and culturally (the monthly spot-check).
