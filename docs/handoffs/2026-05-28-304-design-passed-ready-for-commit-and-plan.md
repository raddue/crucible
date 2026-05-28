# Handoff — #304 build skill eval gate v0.1, design PASSED, ready for commit + /plan

**Mode:** A (Continuation). Design doc written and self-QG'd through 2 rounds (cost-capped per #303 discipline). Doc is uncommitted on `build/304-eval-gate`. Next concrete steps: commit the design, then run `/plan` to produce the implementation plan.

## Goal

Ship #304 v0.1: a runnable eval gate for the `build` skill, 4 fixtures (b1 simple-feature, b2 multi-file, b3 bugfix, b4 design-required), stubbed sub-skills, k=3 majority-threshold scoring.

## State snapshot

- **Worktree:** `/mnt/games/Coding/crucible/.worktrees/304-eval-gate/`
- **Branch:** `build/304-eval-gate` (off main `952d057`)
- **Uncommitted:** `docs/plans/2026-05-28-304-build-eval-gate-design.md` (~240 lines, design doc — needs commit)
- **Working tree (main checkout):** stale `M docs/compass.md` (updated to #304 arc + open loops refreshed; uncommitted), plus ambient untracked items (`.claude/`, `.envrc`, `.mcp.json`, `docs/handoffs/` — all expected)
- **Issue:** [#304](https://github.com/raddue/crucible/issues/304) — OPEN, no branch/PR yet other than this one
- **Related shipped this arc:** #303 (cost-cap heuristic) merged as PR #306 (`952d057`). #290 v0.1 merged as PR #302 (`6dcfa16`). #305 (#303 v1.0 follow-up) filed during #303.

## Next concrete action

1. `cd /mnt/games/Coding/crucible/.worktrees/304-eval-gate`
2. `git add -f docs/plans/2026-05-28-304-build-eval-gate-design.md` (force-add — `docs/plans/` is gitignored per crucible convention)
3. Commit message: `docs(304): v0.1 design — eval gate for build skill (QG-passed)`
4. Invoke `/plan` on the design doc. Standard /plan flow: Plan Writer → Plan Reviewer → /innovate → /quality-gate. Apply #303 cost-cap discipline here too (3-round cap, exit early on diminishing returns).

## Design summary (so /plan doesn't have to re-derive)

5 key decisions locked in `docs/plans/2026-05-28-304-build-eval-gate-design.md`:

- **DEC-1** CI deferred to v0.2. Ship via `scripts/build-evals.sh` + opt-in `scripts/hooks/pre-push-build-evals.sh` (reminder, not gate). No Makefile bootstrap.
- **DEC-2** Fresh harness in `skills/build/evals/`, no shared extraction. ~200 lines of duplicated scaffolding accepted as cost of scope containment.
- **DEC-3** Stub mechanism via `BUILD_EVAL_MOCK_DIR` + `BUILD_EVAL_MODE` + `BUILD_EVAL_USER_INPUT_DIR` env vars. **Single intercept point** at the `shared/dispatch-convention.md` boundary (not per-call touches). Build SKILL.md edit: 40-60 lines, one new section + 3-5 inline checks.
- **DEC-4** Observation via `manifest.jsonl` (per-dispatch trace) + `git diff` + `build-gate-ledger.md` + working-tree presence. No new instrumentation in build.
- **DEC-5** k=3 majority threshold (≥2/3 PASS). Acknowledges orchestrator LLM non-determinism. No drift-delta calibration in v0.1 (relevant once real-PR fixtures land in v0.2).

4 fixtures, expected to live under `skills/build/evals/fixtures/{b1,b2,b3,b4}/`:
- **b1 simple-feature** — probes minimum-ceremony orchestration
- **b2 multi-file** — probes plan dependency ordering
- **b3 bugfix** — uses `BUILD_EVAL_MODE=refactor` to sidestep interactive mode-detection
- **b4 design-required** — uses empty `BUILD_EVAL_USER_INPUT_DIR` + `.pipeline-active` phase=1 as halt-for-input signal

Open Questions in design doc (4 items, all with recommendations) cover: build SKILL.md edit QG batching, mock granularity, `finish` mocking, test isolation.

## Suggested approach for /plan

- Plan should produce ~6-8 tasks. Rough decomposition:
  1. Harness scaffolding (`run_evals.py`, `fixture_loader.py`, `expectations.py`, `mock_dispatcher.py`)
  2. Build SKILL.md Mock Dispatch Mode section + intercept edits
  3. Each fixture as its own task (b1, b2, b3, b4) — fixtures are independent
  4. README + scripts (`scripts/build-evals.sh`, `scripts/hooks/pre-push-build-evals.sh`)
  5. Smoke fixture (build without env vars on trivial task — mitigates HIGH risk on DEC-3)
- Highest-risk task: build SKILL.md edit. Plan should put it early so subsequent fixture tasks can verify against the edited build.
- Plan-time decision: should fixtures use real `git init` + commit for the seed/ tree, or just plain file trees? Probably plain file trees; the harness creates the git context.

## QG findings history (from this session)

Round 1 raised: F1 (DEC-3 underspecified intercept), F2 (mock-id mismatch), S1 (HOME insufficient), S2 (b3 interactive mode-detection), S3 (b4 halt signal wrong), S4 (determinism claim shaky), S5 (pre-push hook is reminder not gate), M1-M5. All addressed in round 2. Round 2 introduced no new Fatals/Significants → PASS at cost-cap budget.

## Standing directives

- **#303 cost-cap discipline** applies to every adversarial round in this arc. /plan, /quality-gate on the plan, /build's Phase 4 review — all cap at 3 rounds, exit on diminishing returns. The full ceremony for THIS arc's design produced 0 agent dispatches (refine-only pass + inline QG); /plan should make similar judgment calls.
- **No `claude -p`** (per project memory standing directive from prior arcs).
- **Force-add `docs/plans/` + `docs/handoffs/`** — these dirs are gitignored.
- **PR workflow** for non-trivial changes. #304 is a multi-file arc; expect PR not direct-to-main.
- **Worktree pattern:** crucible uses `.worktrees/<branch-suffix>/` (gitignored). The branch is `build/304-eval-gate`.
- **Compass:** `docs/compass.md` was updated this session (uncommitted in main checkout) to drop shipped loops (#290, #297, #303) and add #304 as current arc, #305 as new open loop. Next session should verify/commit compass alongside other artifacts, or let `build` orchestrator re-emit it.

## Recovery pointers

- **Design doc:** `docs/plans/2026-05-28-304-build-eval-gate-design.md` (uncommitted on `build/304-eval-gate`)
- **Issue body:** `gh issue view 304` — the original draft design brief (now superseded by the design doc)
- **Reference harness:** `skills/temper/evals/` — pattern source for run_evals.py shape (don't extract, just reference)
- **Dispatch convention:** `skills/shared/dispatch-convention.md` — the intercept point for DEC-3
- **Build SKILL.md:** `skills/build/SKILL.md` — 1440 lines. Relevant sections for the edit: top-level dispatch sections, Phase 1 Step -1 (pipeline-active marker), Mode Detection section.
- **Prior backlog handoff:** `docs/handoffs/2026-05-26-temper-290-shipped-pivot-backlog.md` — context on why #304 was the top pick after #290 v0.1 shipped.
- **Memory state:** project memory dir `/home/rickr/.claude/projects/-mnt-games-Coding-crucible/memory/` is COLD (new OS install). No forge retrospectives, no cartographer map, no auto-memory. This session ran cold-start. Future sessions will accumulate memory organically.
- **Skills install:** all 56 skills (crucible + caveman/cavecrew) are globally installed at `~/.claude/skills/` (symlinks to `/mnt/games/Coding/crucible/skills/` and `~/.claude/sources/caveman/skills/`). Survives sessions, available in every repo.

## Open questions / deferred decisions

1. **Build SKILL.md edit QG batching.** Recommendation in design doc: batch (mock toggle is no-op when env var unset). /plan can confirm.
2. **Mock file granularity.** Design recommends per-dispatch (`<seq>-<template>.md`). /plan should pin the schema concretely.
3. **`finish` mocking.** Design recommends always "dry-run completed" verdict. /plan needs to spec the mock content.
4. **Test isolation tmpdir lifecycle.** Design says preserve-on-FAIL, clean-on-PASS. /plan needs to spec the cleanup invariant.
5. **Should compass.md update commit go on this branch or main?** Conservative: commit on main as a separate chore. Aggressive: bundle with the #304 PR. No standing convention.

## Next on deck (after #304)

If #304 ships cleanly, next pickups per #290 backlog handoff (still relevant):
- **#305** — #303 v1.0 (triage table, Override vocab, Exit Precedence slot)
- **#294/#295/#296** — #267 follow-ups (Tenancy/Rollback polish)
- **#292** — propagate lens awareness into shared/external-review-prompt.md
- **#291** — temper lens-health telemetry (pre-#304 data; #304's evals may produce some of what this needs)
