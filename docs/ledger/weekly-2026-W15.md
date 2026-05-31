# Crucible Calibration Ledger — 2026-W15

_Generated 2026-05-31T20:27:31Z_

## Crucible caught 0 silent bugs

Forward-captured runs with `would_have_shipped_without_gate: true`, excluding backfilled entries (the honest count, per L-3/L-5).

## Verdict breakdown

- Total runs this week: **2**
- PASS: 2

## Per-skill severity rates (forward-captured only)

_No forward-captured entries this week — rates unavailable. (Backfilled entries carry `severity_histogram: null` by design.)_

_Inflation detector is silent for a skill until 4 weeks of forward-captured data exist for it (§4a bootstrap)._

## Backfilled historical context

2 backfilled entries this week (excluded from the caught headline and from severity rates; `severity_histogram: null` by design):

- PR #162 — `quality-gate` PASS
- PR #152 — `quality-gate` PASS

## Falsified verdicts (cross-link)

Falsified ledger entries (all-time, via the L-9 reduction over `falsification.jsonl`): **0**.

_No falsification data yet (reconciler / Phase 4 not present, or no verdicts falsified)._

## Monthly spot-check

First `/ledger` run of the month — spot-check protocol (advisory, not blocking):

- [ ] Spot-check 5 random `would_have_shipped_without_gate: true` entries — do their `highest_finding` quotes match the rubric in `skills/shared/severity-rubric.md`?
- [ ] Review any inflation alerts above for calibration drift.
