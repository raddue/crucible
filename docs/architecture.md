# Architecture

How Crucible's skills compose. The catalog at [skills.md](skills.md) lists every skill; this doc explains how the orchestrator skills (build, debugging, spec, migrate) chain them and where the recommended-but-optional accelerators (forge, cartographer) plug in.

## The build pipeline

The **build** skill is the main entry point for feature development. It chains through four phases:

1. **Phase 1: Design** (interactive) — Refine the idea with the user, produce a design doc. Forge feed-forward and Cartographer consult run at start. Design passes through a quality gate.
2. **Phase 2: Plan** (autonomous) — Write implementation plan, review, then quality gate on the plan. Innovate proposes enhancements before the gate.
3. **Phase 3: Execute** (autonomous, team-based) — Dispatch implementers per task, de-sloppify cleanup, two-pass code review (code quality + test quality + AI slop signal detection), test alignment audit (crucible:test-coverage audits existing tests for staleness), test gap writer (fills coverage gaps with dedup-aware auto-retry), and adversarial tester (writes tests designed to break the implementation).
4. **Phase 4: Complete** (autonomous) — Code review on full implementation, inquisitor (5 parallel adversarial dimensions against the full feature diff), quality gate, session metrics, full test suite, Forge retrospective, Cartographer recording, branch completion.

Phase 4 also runs a conditional security pass and a supply-chain scan around the gate. **crucible:siege** is dispatched at Step 5.5 — sequentially *before* the quality gate — but only when security signals are detected (or siege is forced); if it completes clean, the build continues to the gate. **dependency-audit** (npm/cargo/pip-audit) runs alongside the gate as an independent supply-chain signal. Both can block completion, yet are deliberately kept out of the gate's weighted score (INV-2 — the score sums only the host red-team's own Fatal/Significant findings; siege, dependency-audit, and external-model signals are all excluded) and out of red-team's input (anti-anchoring: a sibling signal shares the artifact, never the reviewer's context).

## Knowledge accelerators

The **forge** and **cartographer** skills are recommended (not required) knowledge accelerators. Forge learns about agent behavior (process wisdom), Cartographer learns about the codebase (domain wisdom — including defect signatures that surface known bug patterns proactively). Both accumulate across sessions.

The **project-init** skill accelerates onboarding — run `/project-init` on an unfamiliar repo to get full structural context before the first `/build` or `/design`. It produces the same cartographer files that would accumulate over multiple sessions, tagged as structural scaffolding that gets replaced by task-verified content over time.

## Investigation and decision layers

The **recon** and **assay** skills provide the investigation and decision-evaluation layer. Recon produces a layered investigation brief (structure, patterns, scope, prior art) with optional depth modules. Assay evaluates competing approaches with constraint_fit scoring and kill criteria. Both are dispatched automatically by design (Phase 2), spec (per-ticket investigation), migrate (Phase 0 + User Gate), and audit (Phase 1 scoping). They're also usable standalone — `/recon` before any task, `/assay` for any architectural decision.

## Spec → build handoff

The **spec** skill produces design docs, implementation plans, and machine-readable contracts from a GitHub epic — feeding directly into build for autonomous execution of an entire epic.

## Security audits

The **siege** skill performs security audits — 6 parallel attacker-perspective agents iterate until zero Critical/High findings.

## External model perspectives

**External model review** adds independent non-Anthropic perspectives to temper, quality-gate, red-team, and inquisitor. Unlike consensus (which requires multiple models and synthesizes), external review works with a single provider and returns raw per-model analysis. On consensus-eligible quality-gate rounds, external responses are bridged into consensus. Configure in [consensus-config-example.yaml](../skills/consensus/consensus-config-example.yaml) under `external_review:`.

## Crash recovery and A/B experimentation

The **replay** skill provides crash recovery and A/B experimentation for any pipeline. When a build crashes at Phase 4, replay reads the dispatch manifest, verifies completed artifacts, restores the checkpoint, and resumes from the first incomplete entry — 10 minutes instead of 90. For A/B testing, `--mutate` swaps dispatch templates and replays historical pipelines to measure skill changes. Build, debugging, spec, and migrate all write pipeline-active markers for automatic crash detection.

## Session continuity

The **recall** skill queries the session activity index — a searchable log of file edits, git operations, test runs, and errors maintained by PostToolUse hooks. Compaction recovery steps in build, debugging, and spec re-read session state after context compression. Skills emit semantic events (phase transitions, design decisions) via an outbox pattern for cross-skill continuity.

The **compass** skill maintains per-repo arc-state in `docs/compass.md` (current arc, last meaningful commit, open loops, next move, don't-forget items). It is auto-maintained by build, merge-pr, and finish, and read by getting-started, so a new session can recover *where the work was* without re-deriving it from git.

## Calibration and regression memory

These skills make Crucible's quality claims falsifiable and let past defects guard future ones. The **calibration ledger** is the epistemic backbone: Tier-A gate verdicts are appended to a machine-local central store (`~/.claude/crucible/ledger/`, never committed). **calibration-reconcile** later walks merged fix/hotfix branches to falsify those verdicts and computes per-skill Brier scores; **ledger** renders the weekly report — the honest "Crucible caught N silent bugs" headline, verdict breakdown, per-skill severity rates, and an inflation detector. The **grudge** skill (the Book of Grudges) is the complementary regression memory: every fixed bug is recorded as a machine-local, per-repo grudge, and skills query it for the files in scope before touching code, surfacing past regressions as forced "DO NOT REPEAT" context.

## Token efficiency

Token efficiency tracking enriches dispatch manifests with character-count estimates (chars/4 ≈ tokens). The `/stocktake efficiency` command reads chronicle signals to produce per-skill cost breakdowns, dispatch tier distribution, and structural baseline comparisons.

The **distill** skill converts heavy documents (PDF, Word, Excel, PowerPoint) to token-efficient Markdown/CSV with a digest pass — reducing context budget by ~80% for document-heavy workflows.

## Standalone use

Individual skills can also be used standalone (e.g., `test-driven-development` for any implementation work, `debugging` for any bug, `audit` for adversarial review of any existing subsystem or document).
