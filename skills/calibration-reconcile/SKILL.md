---
name: calibration-reconcile
description: Reconcile the Crucible calibration ledger — walk merged fix/hotfix branches to falsify the originating gating-verdicts, compute per-skill Brier calibration scores, and append a falsification log. Triggers on "/calibration-reconcile", "reconcile ledger", "reconcile calibration", "falsify verdicts", "brier score", "calibration reconcile", "compute brier".
origin: crucible
---

<!-- CANONICAL: shared/ledger-reduce.md -->

# Calibration reconciler

Walks fix branches to **falsify** the gating-verdicts that should have caught
the bug, computes per-skill **Brier calibration scores**, and writes a
falsification log to the **central ledger** `~/.claude/crucible/ledger/`
(override `CRUCIBLE_LEDGER_DIR`). The SKILL.md is a thin prompt wrapper; the
source of truth is the testable Python core at `scripts/reconcile_ledger.py`.

**Skill type:** Utility — direct execution, no subagent dispatch.

## Trigger

Manual `/calibration-reconcile [--lookback-days N]` (default `N=30`).

## Kill-switch

If `CRUCIBLE_CALIBRATION_DISABLED=1`, the CLI **skips entirely** (graceful
no-op exit 0) before any git or filesystem work. The forward-capture path
(`scripts/ledger_append.py`) honors the same switch, so the whole calibration
subsystem can be disabled with one env var.

## What it does

Invoke the reconciler directly. Resolve `scripts/reconcile_ledger.py` by
**absolute path** from the plugin root (it self-locates its own modules via
`__file__`, so no `PYTHONPATH` is needed and it runs from any cwd):

```
python3 <plugin_root>/scripts/reconcile_ledger.py --lookback-days 30
```

It reads `runs.jsonl` and `manual-attribution.jsonl` from the central store and
**writes** `falsification.jsonl` (append-only, L-1/L-9) + `brier-rolling.json`
(gitignored) into that SAME dir.

## Algorithm (design §3 steps 1–6)

> Scope limit: this implements steps 1–6 ONLY. The predicted-falsifier
> predicate parser / "second pass" is **Phase 7 and explicitly out of scope**.

1. **Candidate set** (git layer, `discover_candidates`): `fix/*` `hotfix/*`
   branches merged in the last `--lookback-days` (default 30) + `regression`-
   labelled closed issues with a referenced commit (best-effort; if `gh` is
   unavailable, skip silently). Each candidate carries `touched_files` (from
   `git show --name-only <merge-sha>`) and `merge_time`.
2. **Cross-cut detector** (`cross_cut_threshold_from`): threshold = **p90 of
   fix-branch sizes over the prior 90 days** (a DISTINCT window from the 30-day
   candidate lookback); **bootstrap to a fixed 20** until ≥30 samples exist. A
   candidate with `len(touched_files) > threshold` is tagged `cross_cut: true`.
   Cross-cut candidates may still get a `confidence: low` attribution but are
   **EXCLUDED from the Brier denominator**.
3. **Walkback** (`reconcile`): for each candidate, find the **EARLIEST** ledger
   entry where ALL of: (a) `gated_files ∩ touched_files` non-empty, (b) entry
   `timestamp` < candidate `merge_time`, (c) `artifact_type == "code"`, (d)
   `backfilled == false`. If found, record a falsification entry marking it
   `falsified: true` with `falsified_by: {commit, reason, confidence, cross_cut}`.
4. **Confidence scoring:** `high` when intersection ≥1 file AND merge within 14
   days of the verdict AND `cross_cut == false`; `medium` when 14–30 days AND
   `cross_cut == false`; `low` when >30 days OR `cross_cut == true` OR
   multi-file fixes (>5 files but ≤ the cross-cut threshold).
5. **Manual override** (`read_manual_attribution`): read
   `manual-attribution.jsonl` **first**; entries there (keyed by
   `ledger_entry_hash`) override the algorithm's attribution. Missing file ⇒
   empty overrides (no error). An entry may carry an optional `signal_type`
   (`manual_override` (default) | `bad_implementation`) — see
   [Non-code `bad_implementation` signal](#non-code-bad_implementation-signal).
6. **Kill-switch:** see above — `CRUCIBLE_CALIBRATION_DISABLED=1` ⇒ no-op exit.

## Brier scoring (contract L-10)

Per-skill calibration is the Brier score over each skill's **falsifiable
sample**:

```
brier = mean((confidence - actual)^2)
```

- **actual = 1** iff the verdict was CORRECT: a `PASS` NOT marked falsified, OR
  any `FAIL` (at v1 every FAIL ⇒ actual=1, since predicted-falsifier predicates
  are Phase 7).
- **actual = 0** iff WRONG: a `PASS` that WAS marked `falsified: true` (looked
  up in the **L-9 latest-entry-wins reduction** over `falsification.jsonl` via
  `scripts.ledger_reduce.reduce`, the canonical helper cited above).
- **Falsifiable sample filters (ALL must hold):** `artifact_type == "code"`
  **OR** a non-code verdict carrying a `bad_implementation` falsification (see
  below); `backfilled == false`; `verdict ∈ {PASS, FAIL}` with
  `confidence >= 0.5`; entry older than the 30-day grace period; AND if a
  matching falsification entry exists, its `cross_cut` must be `false`.
- **Verdict-type classifier (T-11):** only `PASS`/`FAIL` count. `STAGNATION`,
  `ESCALATED`, `ARCHITECTURAL`, `SUSTAINED_REGRESSION` are excluded from both
  numerator AND denominator.
- Skills with **<5 falsifiable verdicts** are excluded from the advisory (we
  still compute `n`; just don't gate). The advisory threshold is `brier > 0.25`
  (consumed in Phase 6 — here we only compute and store).

## Non-code `bad_implementation` signal

Auto-falsification (walkback + predicted_falsifier) is code-artifact-centric: a
verdict is only falsified when a later fix/revert touches a gated path or fires a
predicate. That can **never reach a non-code verdict** (a design-doc or plan
`PASS`), and it misses the case where a `PASS` was accepted but the resulting
implementation later proved bad for reasons no path-touching fix captures — a
design-level wrong call, downstream rework, or an abandoned approach.

To score those, a human adds a `manual-attribution.jsonl` entry with
`signal_type: "bad_implementation"`:

```json
{"ledger_entry_hash": "<sha256(run_id:skill)>", "falsified": true,
 "confidence": "high", "signal_type": "bad_implementation",
 "reasoning": "design PASS led to a full rework of the persistence layer"}
```

- It is a **PASS-side marker**: "a verdict accepted as PASS led to a bad
  implementation." On a `PASS` it sets `actual = 0` (the verdict was
  overconfident); on a `FAIL` it is out-of-contract and silently ignored.
- It works for **non-code** artifacts (`design`/`plan`/…): such a verdict is
  admitted into the Brier sample **only** when it carries this signal — absent it,
  a non-code verdict's outcome is unknown and stays excluded (we never assume a
  non-code PASS was correct just because nothing falsified it). The usual filters
  still apply (PASS/FAIL, `confidence >= 0.5`, outside grace, non-cross-cut), so a
  Tier-B `confidence: null` verdict is render-counted but not Brier-scored.
- It also works on a **code** PASS (downstream rework that no path-touching fix
  caught), flipping `actual` like any other PASS falsification.

`/ledger` breaks the falsified count down by source (`walkback` / `predicate` /
`manual_override` / `bad_implementation`).

## Outputs

- **`falsification.jsonl`** — APPEND-ONLY (L-1/L-9). Each entry:
  `{ledger_entry_hash, falsified, falsified_by, confidence, reasoning, cross_cut}`
  — plus an optional `signal_type` (`manual_override` | `bad_implementation`) on
  manual-attribution-sourced entries.
- **`brier-rolling.json`** (gitignored) —
  `{"<skill>": {"n": int, "brier": float, "last_updated": "<iso>"}, ...}`.
