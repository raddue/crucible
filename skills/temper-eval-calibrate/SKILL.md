---
name: temper-eval-calibrate
description: Wrapper skill that runs k iterations of (stage → collect-behavior → score) for #290 calibration sweeps. Replaces bash for-loops that cannot invoke session skills. Default k=3. Inlines collect-dispatch behavior per iteration. Idempotent resume via per-iteration sentinels under skills/temper/evals/.calibrate-state/.
model: opus
---

<!-- CANONICAL: shared/dispatch-convention.md -->

# Temper Eval Harness — Calibrate Wrapper

**Invocation:**
```
/temper-eval-calibrate <run-id-prefix> [--k N] [--source SOURCE] [--fixture <id>]
                                       [--write-baseline] [--compare-baseline]
                                       [--trials-override N] [--max-parallel N]
                                       [--timeout N]
```

**Pre-conditions:**
- A Claude Code session is active
- `<run-id-prefix>` matches `^[A-Za-z0-9_][A-Za-z0-9_-]{0,28}$` (I-9; aligned with `_runid.py`'s `_PREFIX_RE`; reserves 3 chars for `-<i>` suffix)

**Post-conditions:**
- For each `i in 1..k`, `skills/temper/evals/.calibrate-state/<prefix>-<i>-complete` exists AND `skills/temper/evals/.calibrate-state/last_run-<prefix>-<i>.json` exists with `run_id == <prefix>-<i>`
- A per-iteration summary line is emitted to stdout

## Procedure

### Step 0: Ordering precondition (2P-FE-6 R3 + F-R4-1, S-1 R5)

**Task 13 (per-iter wiring) lands BEFORE this skill is invoked — verified by sequential task numbering.** Per F-R4-1, Task 13 lands BOTH the `--per-iter` argparse declaration AND the `main()` wiring in a SINGLE atomic commit (Task 4 intentionally omits the argparse declaration to eliminate any silent-drop window). Because Task 13 is numbered ahead of Task 14, operators following the plan sequentially will have `--per-iter` wired before this skill's SKILL.md exists to be invoked. Defense-in-depth: if Task 13 is somehow skipped, `score --per-iter` will raise an argparse "unrecognized arguments" error (no silent drop) — the calibrate skill's Step 3e shell-out will fail loud rather than clobbering shared state.

### Step 1: Validate prefix and k (I-9, M-2)

- `<run-id-prefix>` must match `^[A-Za-z0-9_][A-Za-z0-9_-]{0,28}$` (M-FE-3 R3); refuse with explicit error if not.
- `--k` (default 3) must be in `[1, 99]` inclusive; refuse if out-of-range. <!-- 2P-R4-2: k cap 99 ties to _PREFIX_RE's 3-char suffix reservation; k>=100 would overflow into a 4-char suffix and silently push the resulting run-id past the 32-char _RUN_ID_RE ceiling. -->

### Step 2: Resolve calibrate-state directory

`STATE_DIR = skills/temper/evals/.calibrate-state/`. If it does not exist, create it (`mkdir -p`).

### Step 3: For each iteration `i in 1..k`

#### 3a. Compute RUN_ID

`RUN_ID = "<prefix>-<i>"`.

#### 3b. Resume idempotency check (SP-β, SP-4, AC-12)

If BOTH of the following are true, **skip iteration entirely** (no stage, no collect, no score, no billing):
- `skills/temper/evals/.calibrate-state/<prefix>-<i>-complete` exists
- `skills/temper/evals/.calibrate-state/last_run-<prefix>-<i>.json` exists AND its `run_id` field equals `<prefix>-<i>`

Print: `[skip] iteration <i>: already complete`.

#### 3c. Stage

Shell out via Bash tool: `python -m skills.temper.evals.run_evals stage "$RUN_ID" [--source ...] [--fixture ...] [--trials-override ...] [--timeout ...]`

Pass through whatever flags the user supplied.

#### 3d. Collect-dispatch behavior (inlined; see /temper-eval-collect spec)

Execute the full procedure documented in `skills/temper-eval-collect/SKILL.md` Steps 1–8 against `RUN_ID`.

**Version pin (M1 R8):** this inline-execution reference is pinned to the Steps-1–8 shape at calibrate-skill author time. If `skills/temper-eval-collect/SKILL.md` is later edited (e.g. a Step 4.5 is added, or steps are renumbered), this calibrate skill MUST be re-validated against the new step set — there is NO automatic inheritance. Treat collect SKILL.md edits as breaking changes for the calibrate skill until re-verified.

This includes:
- Run-id validation (I-9)
- Dispatch-dir stat (SP-3 step 1)
- Atomicity probe (SP-3 step 2, F-1)
- Stale `.tmp` cleanup
- Stage-manifest read with optional `--timeout` override
- Idempotency-aware wave dispatch (max_parallel default 6)
- Atomic per-seq result-file writes with DISPATCH_STATUS sentinels
- `manifest.jsonl` per-dispatch appends
- I-10 10 MB result-size ceiling
- `.collect-status` write with `fsync` (I-12)

The inlined behavior satisfies I-7, I-8, I-10, I-12 identically to standalone `/temper-eval-collect`.

#### 3e. Score (with per-iteration output)

Shell out: `python -m skills.temper.evals.run_evals score "$RUN_ID" --per-iter [--write-baseline] [--compare-baseline]`

The `--per-iter` flag is REQUIRED here (F1): it tells `score` to write to `skills/temper/evals/.calibrate-state/last_run-<prefix>-<i>.json` instead of the shared `last_run.json`. Without `--per-iter`, iterations would clobber each other's output AND collide with operator-owned `last_run.json` artifacts. There is NO run-id-shape heuristic; the routing is explicit.

If score returns 2 (fatal), abort all remaining iterations and surface the error.

#### 3f. Write completion sentinel

On successful score, write `skills/temper/evals/.calibrate-state/<prefix>-<i>-complete` with content `complete-<ISO-8601>`.

#### 3g. Print per-iteration summary

`[iter <i>/<k>] RUN_ID=<RUN_ID> score=<rc>`

### Step 4: Final consolidation (M-3)

After ALL k iterations succeed (every iteration's `.calibrate-state/<prefix>-<i>-complete` sentinel is present), copy `skills/temper/evals/.calibrate-state/last_run-<prefix>-<k>.json` to `skills/temper/evals/last_run.json` (the shared output the `--compare-baseline` workflow expects). This is unconditional on success — not optional.

**Pre-copy verification (mirrors the sentinel-pair discipline in Step 3b):**
1. Verify `last_run-<prefix>-<k>.json` exists. If absent, refuse to clobber `last_run.json` and exit with the fatal error `"iteration k completion sentinel present but per-iter file missing at <path>; refusing to consolidate."`
2. Parse the file as JSON. If parsing fails, refuse with `"per-iter file at <path> is malformed JSON; refusing to consolidate."`
3. Confirm the `run_id` field equals `<prefix>-<k>`. If it does not, refuse with `"per-iter file at <path> carries run_id=<actual>, expected <prefix>-<k>; refusing to consolidate."`
4. Only after all three checks pass, perform the copy.

If ANY iteration failed (sentinel missing, score returned 2, or stage refused), do NOTHING in this step: leave `last_run.json` untouched so the operator can inspect the per-iter files manually without a clobbered shared state.

Rationale: the original "optionally copy" wording produced two equally-valid downstream states (shared file = last iter vs. shared file = stale) with no operator signal to disambiguate. The all-or-nothing rule eliminates the ambiguity. Revisit only if best-or-median canonicalization is genuinely needed (defer to a follow-up ticket).

## Failure Modes

- **Stage fails:** abort remaining iterations; surface the stage error.
- **Collect crashes mid-wave:** next invocation resumes from missing seqs in that iteration's dispatch dir; once that iteration completes, the calibrate sentinel is written and subsequent iterations proceed.
- **Score fails (rc=1):** continue to next iteration (a single iteration FAIL is data, not a blocker for k=3).
- **Score returns rc=2 (fatal):** abort all remaining iterations.

## Invariants

This skill enforces: M-2 (k cap 1..99), I-9 (prefix regex), AC-12 (resume idempotency).
