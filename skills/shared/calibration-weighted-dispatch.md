---
version: 1
---

# Calibration-Weighted Dispatch (advisory)

> Canonical convention for the pre-dispatch calibration hint the fan-out skills
> surface to their reviewers. Cited via
> `<!-- CANONICAL: shared/calibration-weighted-dispatch.md -->` from `siege`,
> `quality-gate`, `inquisitor`, `delve`, and `audit`.
> `scripts/check_calibration_dispatch.py` grep-asserts every consumer carries
> the marker + invocation and inlines no copied prose.
>
> The importable single source of truth is the `advise` subcommand of
> `scripts/brier_advisory.py`. Spec: `#372`.

## 1. What it is

Before a skill fans out reviewers, it asks the calibration store *where to look
harder this run* and passes that hint into each reviewer's dispatch context. The
hint is the **`DispatchAdvice`** block — a small, bounded set of scrutiny lines
merged from three independent signals:

- **Brier scrutiny (skill-level)** — "my last N verdicts had a Brier of X; treat
  my outputs with extra scrutiny." Reuses `advisory_line` verbatim.
- **Falsification file-hits (file-level)** — files where *this suite's own gate
  verdict was later proven wrong* by `/calibration-reconcile`.
- **Grudge file-hits (file-level)** — files carrying past *bugs* recorded in the
  Book of Grudges (`#271`).

`DispatchAdvice` shape (header + ≤4 signal lines + footer; omit any silent
signal; all silent ⇒ no output at all):

```
[calibration-weighted dispatch] advisory only — does not change any verdict or score.
- scrutiny: <advisory_line text>                  # Brier, omitted if silent
- past wrong verdicts touched: a.py (2), b.py (1)  # falsification, omitted if none
- past regressions on file: c.py (3), d.py (1)     # grudge, omitted if none
- suggested weighting: give the named files extra reviewer attention this run.
```

**Bounds (the block can never balloon):** each file list is capped at the top
`ADVICE_FILE_TOPK = 5` files, ranked hit-count desc then path asc, with overflow
rendered as `(+N more)`; filenames are repo-relative (never absolute); there is
no per-grudge prose or reasoning dump.

## 2. The `advise` contract

```
python3 scripts/brier_advisory.py advise <skill> [file ...]
```

- `<skill>` — the dispatching skill's own calibration key (e.g. `siege`, `delve`).
- `[file ...]` — the gated files about to be reviewed (repo-relative, `./`-, or
  absolute; same path tolerance as `grudge_query.py`). May be empty — then only
  the skill-level Brier signal can fire.
- **stdout** — the `DispatchAdvice` block when ≥1 signal fires; **nothing** when
  silent.
- **exit code** — always `0`. This is an advisory, never a gate. Internal errors
  are caught, optionally warned to stderr, and produce silent stdout — never a
  non-zero exit a caller might misread as "block."

**Silence rules** (any ⇒ that signal contributes nothing; all silent ⇒ no output):

- **Kill-switch:** `CRUCIBLE_CALIBRATION_DISABLED=1` ⇒ the entire command is
  silent (single check, reuses `_disabled()`).
- **Brier:** silent per the existing `advisory_line` rules (pre-bootstrap,
  >30-day-stale, n<5, Brier≤0.25, malformed).
- **Falsification:** silent when there is no `falsification.jsonl`, or no
  non-backfilled falsified entry's `gated_files` intersect `[file ...]`.
- **Grudge:** silent when the grudge store is empty/absent or no grudge matches
  `[file ...]`.

**Invariants (load-bearing):**

- **Advisory-only / never-score.** `DispatchAdvice` is injected into reviewer
  *context* as scrutiny hints. It is NOT a finding, is NOT scored, and is NEVER
  an input to any verdict, weighted score, or stagnation calculation.
- **Never-block / never-raise.** Each component is wrapped so an internal error
  degrades that signal to empty; `advise` always returns a string and always
  exits 0.
- **Kill-switch silent.** `CRUCIBLE_CALIBRATION_DISABLED=1` silences the whole
  block (this is fixture-only for production verdicts elsewhere, but here it is
  the consumer-side mute).
- **Central store never committed.** The calibration ledger and grudge store live
  under `~/.claude/crucible/` (honoring `CRUCIBLE_LEDGER_DIR` / `CRUCIBLE_GRUDGE_DIR`).
  They are machine-local; crucible is a PUBLIC repo. Nothing under that path is
  ever committed — in-repo fixtures only.

## 3. Consumer obligation

Each consuming skill carries the CANONICAL marker plus a short invocation at its
own natural pre-fan-out point — context-only and best-effort, never a copy of
the prose above:

```markdown
<!-- CANONICAL: shared/calibration-weighted-dispatch.md -->
**Calibration-weighted dispatch (advisory).** Before fanning out reviewers,
resolve `scripts/brier_advisory.py` by absolute path from the plugin root and
run `python3 <script> advise <this-skill> <file list…>`. If it prints a
DispatchAdvice block, include it verbatim in each reviewer's dispatch context as
scrutiny hints (NOT as findings, NOT scored). Best-effort: on empty output or any
error, dispatch normally. See `shared/calibration-weighted-dispatch.md`.
```

The step is **not structurally uniform** across the five — each skill's fan-out
shape and file-list source differ, so the landing point and file derivation are
per-skill:

| Skill | Where the step lands | How it derives its file list |
|---|---|---|
| `siege` | Its existing pre-fan-out point (first-class gated files). | Reuse siege's gated-file list directly. |
| `quality-gate` | Its existing grudge pre-flight injection point — **round 1 only**, beside the grudge pre-flight, so INV-A11 / the look-harder fresh-dispatch contract are untouched. | Reuse the gate's gated-file list directly. |
| `inquisitor` | Immediately before the 5-dimension adversarial fan-out. | `git diff --name-only <base>..HEAD` per inquisitor's base derivation. |
| `delve` | The engine-dispatch context (no inline fan-out): attach the block to the per-angle finder prompt context. | Derive from its review target (diff / path / PR). |
| `audit` | The Phase-1 lens fan-out. | Derive from the audited subsystem's files. |

`<this-skill>` is each skill's own calibration key.

## 4. Why round-1-only for quality-gate

`DispatchAdvice` is injected at the **same point as the existing grudge
pre-flight**. For quality-gate — the one consumer with an iterative between-round
loop — that is **round 1 only**, exactly like the grudge pre-flight it sits
beside. It flows into the **reviewer** dispatch context (it tells the reviewer
where to look harder); it is NOT prior-round findings. So quality-gate's
between-round anti-anchoring contract is untouched: INV-A11 and the look-harder
fresh-dispatch strip per-round context from the red-team prompt, and round-1-only
injection never feeds those later rounds. The other four consumers perform a
single fan-out, so "once, at the fan-out point" is trivially consistent.

## Known v1 limitation

At ship the falsification and Brier signals are **inert for every skill** — no
`falsification.jsonl` exists in the central store yet, and both share the same
`falsification_exists` precondition. Only the grudge signal can fire at v1. The
join algorithm is correct and lights up automatically as falsification history
accumulates; this is a known limitation, not a defect.
