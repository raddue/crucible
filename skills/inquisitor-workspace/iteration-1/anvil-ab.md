# Inquisitor merge eval — #720

## Matched full-feature A/B
- Eval 1: `skills/inquisitor/evals/evals.json` (10 expectations).
- Arm A: baseline full-feature inquisitor from `origin/dev`; Arm B: merged full-feature inquisitor.
- Same prompt, same `cx/gpt-6-luna[1m]` model/session, both using all five dimensions.
- Baseline: **10/10 (100%)**. Merged: **10/10 (100%)**. Delta: **0 percentage points**.
- Each arm proposed fixes and observable behavioral tests; all tests were clearly marked **NOT WRITTEN / NOT RUN**. No test execution was claimed.

## Limitations
One response per arm and one eval only; both scores hit ceiling. No statistical robustness or generalization claim. This tests full-feature mode, not absorbed per-task Phase 3 mode; add a dedicated per-task eval in a later measurement. The initial 6/10 vs 10/10 comparison was mode-mismatched and is excluded from the A/B delta.

Full prompt, outputs and item-by-item rubric: `/tmp/crucible-720-anvil-matched/`.
