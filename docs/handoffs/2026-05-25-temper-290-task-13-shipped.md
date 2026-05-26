# Handoff — #290 Task 13 shipped, Task 14 k1 next

**Mode:** A (Continuation). Continues `docs/handoffs/2026-05-25-temper-290-task-12-pre-switch-done.md`.

## Goal

Run Task 14 POST_SWITCH calibration. Per prior-session user directive: **one cycle (k1) first, then assess** before committing to k2+k3. Aggregate to PRE_SWITCH (Task 12) and fire §7 drift-delta gate.

## State snapshot

- **Branch:** `temper/290-real-pr-fixtures` HEAD `f990c6d`.
- **Tests:** 206 passing (was 205; Task 13 added `test_synth_plan_reference_reads_pr_description`).
- **Pipeline marker:** `phase: 3-blocked-manual-gates` (unchanged).
- **#290 progress:** 17/22 done. 5 remaining: 14 / 16 / 17 / 17b / 18.

## What just completed (Task 13)

Reference switch shipped — `_synth_plan_reference` now reads `pr_description` instead of `expected_output`. This is THE switch under test for §7's drift-delta gate.

- **Commit:** `f990c6d` — `feat(temper/evals): _synth_plan_reference reads pr_description (#290 S4 step 3)`
- **Diff:** `skills/temper/evals/run_evals.py` (line 610: `fixture.get("expected_output", "")` → `fixture.get("pr_description", "")`; docstring updated per plan R1 M13) + `skills/temper/evals/test_lens_runner.py` (new unit test asserting `pr_description` flows through, `expected_output` does NOT)
- **TDD verified:** test fails pre-edit (RED), passes post-edit (GREEN). Full 206-test suite green.
- **Smoke-verified:** staged a 2-trial run on fixture `1a` and grep'd the generated `001-reviewer.md` — `pr_description` body ("Add a `get_timeout_seconds`...") appears under `## What was requested`; `expected_output` body ("Surgical lens fires at Important...") is ABSENT. Switch wired correctly; smoke dispatch dir left on tmpfs (`/run/user/1000/ericr-crucible-dispatch-R-smoke-task13-verify/`, ephemeral — `rm -rf` blocked by safety hook, harmless).

## Next concrete action — Task 14 k1

Per `docs/plans/2026-05-21-temper-290-implementation-plan.md:744`, Task 14 wants k=3 cycles. User explicitly directed **k1 only first, then assess**. Plan:

1. Stage k1:
   ```bash
   python3 -m skills.temper.evals.run_evals stage --source synthetic --trials-override 20 R-postswitch-20260525-k1
   ```
2. Dispatch 200 reviewers via Task-tool delegate-write pattern (~17 waves of 12). Prompt template per Task-12 handoff:
   > "Read NNN-reviewer.md, perform review, write to NNN-result.md.tmp starting `DISPATCH_STATUS: OK\n\n` + body, atomic-rename via `python3 -c 'import os; os.replace(...)'`, return ONLY `DONE`."
3. After all 200 result.md present, write `.collect-status` manually (`{"status": "complete", "errors": 0, "total": 200}` — match Task-12 shape).
4. Score:
   ```bash
   python3 -m skills.temper.evals.run_evals score R-postswitch-20260525-k1 --per-iter
   ```
   **CWD gotcha:** must run from `/mnt/e/Coding/crucible` or `ModuleNotFoundError: No module named 'skills'`.
5. Inspect `skills/temper/evals/.calibrate-state/last_run-R-postswitch-20260525-k1.json` — per-fixture rates.
6. Compare to PRE_SWITCH means (Task-12 handoff §State snapshot):

   | Fixture | PRE_SWITCH mean | Watch threshold |
   |---|---|---|
   | 1a | 0.917 | >0.20 swing = §7 fail |
   | 1b | 0.917 | >0.20 swing |
   | 2 | 0.967 | >0.20 swing |
   | 2-reattrib | 0.967 | >0.20 swing |
   | 3 | 0.983 | >0.20 swing |
   | 4 | 1.000 | >0.20 swing |
   | 5 | 1.000 | >0.20 swing |
   | 6-tenancy-forged-callback | 0.833 | >0.20 swing |
   | 7-rollback-orphan-fk | 0.800 | >0.20 swing (also watch downward trend 0.85→0.80→0.75) |
   | 8-defense-in-depth-not-slop | 0.967 | >0.20 swing |

7. **Assess decision point:**
   - If k1 looks comparable to PRE (all per-fixture swings well under 0.2, no surprises) → proceed to k2+k3 next session (or back-to-back if user OKs).
   - If any fixture swings near or over 0.2 in k1 → escalate (red-team the switch; check leak vs switch-degradation per plan Step 3c cause-discrimination). Do NOT proceed to k2 until cause identified.

## After Task 14: scripts/calibrate_tolerance.py

Unchanged from prior handoff. Three `last_run-R-presplit-20260525-k{1,2,3}.json` artifacts already on disk (gitignored). After Task 14 produces post-switch k=3, run `scripts/calibrate_tolerance.py` to compute `tolerance = round(min(max(2*sigma_worst, 0.447), 0.7), 2)`. Read script end-to-end before invoking; CLI args not yet surfaced.

## Standing directives (still binding)

- **DEC-6 k=3 symmetry** — Tasks 12 ✓, 14 (next, k1 first per user), 16 all use k=3.
- **No `claude -p`** — Task-tool dispatch only.
- **`manifest_hash` excludes `expected_output`** — required at Task 16 since Task 13 now consumes `pr_description`.
- **`baseline.json` `.gitignore` removal** required before Task 16.
- **Force-add `docs/plans/` + `docs/handoffs/`** — `git add -f` for these files (crucible gitignores `docs/plans/`).
- **Never skip QG / innovate / red-team** (`feedback_never_skip_gates`).
- **PR workflow** for non-trivial changes (`feedback_pr_workflow`).
- **Severity bias toward promotion** (`feedback_severity_bias`).
- **Worktree-isolation does NOT actually isolate** — assume all subagents share `/mnt/e/Coding/crucible`.

## Recovery pointers

- **Task 12 PRE_SWITCH artifacts:** `skills/temper/evals/.calibrate-state/last_run-R-presplit-20260525-k{1,2,3}.json` (gitignored, durable).
- **Plan:** `docs/plans/2026-05-21-temper-290-implementation-plan.md`.
- **Design:** `docs/plans/2026-05-21-temper-290-real-pr-fixtures-design.md` (§1(f) superseded → warning-only leak rule).
- **Calibration script:** `scripts/calibrate_tolerance.py`.
- **Prior handoffs:** `docs/handoffs/2026-05-25-temper-290-task-12-pre-switch-done.md`, `2026-05-25-temper-290-task-5.5-baseline-captured.md`.
- **Branch:** `temper/290-real-pr-fixtures` HEAD `f990c6d`.
- **Pipeline marker:** `phase: 3-blocked-manual-gates`.

## Open questions / decisions deferred

1. **Fixture-7 downward trend** (0.85→0.80→0.75 across PRE k-cycles): does POST k1 continue or reverse? Reverse = switch helped; continue = fixture issue not switch issue.
2. **k1 then k2+k3 cadence:** user directed "one cycle then assess" this session. Confirm next session whether assess-pass auto-greenlights k2+k3 back-to-back or wants per-cycle gating.
3. **Task ordering after 14:** plan = 14 → 16 → 17 → 17b → 18. Confirm at decision time.

## Token budget

This session burned ~25K main-context tokens (Task 13 was light: 1 test + 1 line change + smoke). k1 will burn ~80K main + ~7M subagent (one cycle of 200 dispatches). Plenty of headroom; k1+score+compare comfortable in one session if user picks back-to-back next time.
