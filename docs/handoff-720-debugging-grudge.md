# Continuation handoff — #720 debugging/grudge merge

## Goal
Finish #720 merge `grudge` into `debugging`, then open PR against `dev`. Do not merge PR.

## State snapshot
- Branch: `chore/720-debugging-grudge`, worktree `/home/rickr/.herdr/worktrees/crucible/chore-720-debugging-grudge`; base `dev` has been merged.
- Latest commit: `10b7b1d update grudge architecture reference`; seven commits ahead of `origin/dev`; working tree was clean at handoff.
- `skills/grudge/` deleted. Verbatim read/write mechanics copied into `skills/debugging/SKILL.md`; build/quality-gate references repointed; merge-pr still writes fix(*) grudges and now points to debugging section.
- Debugging description includes all requested trigger phrases. Selection eval cases route record/pre-flight intents to debugging; `common_mistakes` excludes expected skill.
- Updated catalog/docs, hooks, encoding invariant fixture path, wiring test.

## Next action
Continue the full suite: `bash scripts/run_tests.sh` timed out at 300 seconds while running `skills/inquisitor/evals/test_oracle.py`; output before timeout showed passing tests. Rerun with a longer/background monitor and confirm final exit status.

Then run `/anvil` A/B eval for debugging and record actual before/after delta in `docs/evals.md` (not yet done). Run `/temper` on branch vs `origin/dev`; resolve findings, rerun gates. Push branch and create PR to `dev` referencing #720; do not merge. Report PR number.

## Constraints and risks
- Stay inside assigned worktree. No mesh. Maintainer polls via Herdr.
- User requested `/handoff` + push WIP + stop at ~25% context. Context threshold not met; this handoff was triggered because full suite run timed out, but user instructed to stop after handoff. No push done yet; push WIP from this branch before resuming.
- Project requires quality gate on every artifact and external fresh-eyes review for lane-written verdicts; user specifically requested `/temper`.
- User requests caveman mode. Final answer must include PR number when eventually created.

## Verification so far
- `python3 scripts/catalog.py check` passed after count refresh.
- `python3 scripts/check_grudge_encoding_invariants.py` passed.
- `python3 eval/grudge/test-grudge-wiring.py` passed all 10 assertions.
- `bash scripts/run_tests.sh` did not finish; command timed out, so suite status unknown.
