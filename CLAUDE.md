# Crucible — Claude Code Guidelines

## Project overview
Crucible is a collection of Claude Code **skills** — a methodology library for
systematic software development (design → plan → TDD → review → quality-gate),
plus the orchestration plumbing they share. This repo is *meta*: the work here is
authoring and tuning skills, not building an app. Skills live one-per-directory
under `skills/` (each has a `SKILL.md` with `name`/`description` frontmatter +
Markdown workflow). `shared/` holds canonical conventions every skill links to;
`eval/` + per-skill `evals/` hold the A/B eval harness; `hooks/` are Claude Code
lifecycle hooks; `docs/` is the catalog, architecture, and measured eval deltas.

## Running & testing
- Internal TS/JS tests: `npm test` (vitest).
- Skill behavior evals: defined in `skills/<skill>/evals/evals.json`, run via
  Anthropic's skill-creator (blind A/B); measured deltas live in `docs/evals.md`.
- Install for live use: symlink skills into Claude Code —
  `ln -sf "$PWD"/skills/* ~/.claude/skills/`. Editing a skill's `SKILL.md`
  changes its behavior immediately on next activation.
- Catalog + architecture: `docs/skills.md`, `docs/architecture.md`.

## Project-specific rules (authoring skills)
- **Frontmatter is the trigger.** Every `SKILL.md` needs `name` + a tight
  one-line `description` — the description is what auto-activates the skill, so
  changing it changes routing. Test routing impact before loosening it.
- **Link canonical conventions, never copy them.** Dispatch, return, and cairn
  rules live in `shared/` and are referenced via `<!-- CANONICAL: shared/x.md -->`.
  Duplicating them into a skill causes drift — link instead.
- **Dispatch + return protocol is load-bearing.** Subagent dispatch is
  disk-mediated (`shared/dispatch-convention.md`); every subagent returns exactly
  one structured Evidence Receipt (`shared/return-convention.md`). Don't invent a
  per-skill format — orchestrators lint these and will reject prose.
- **Find-and-report-only skills don't edit code.** `red-team`, `audit`,
  `code-review` report findings; they must not modify the artifact under review.
- **The calibration ledger is the epistemic backbone.** Tier-A gate verdicts
  append to `.crucible/ledger/runs.jsonl` (committed). The
  `CRUCIBLE_CALIBRATION_DISABLED=1` kill-switch is fixture-only — never silence
  production verdicts.
- **Eval before you publish.** A skill change ships with its evals run; prefer
  anti-rationalization tables + stagnation detection over trusting the model to
  not shortcut under pressure.

## Quality gate (non-negotiable)

Never skip `/quality-gate` on any artifact — design docs, plans, code, even
"small" or "obvious" changes. "Let's just do it quick" or "this is small" does
NOT mean skip the gate. Only an explicit "skip the quality gate" overrides this.
It has caught real bugs that would otherwise have shipped; running it always
costs less than shipping the defect. (This repo *defines* the gate — eat the
dogfood.)

## Working principles

### 1. Think before coding
Don't assume. Don't hide confusion. Surface tradeoffs. State assumptions; if
uncertain, ask. If multiple interpretations exist, present them. If a simpler
approach exists, say so. If something is unclear, stop and name it.

### 2. Simplicity first
Minimum code that solves the problem, nothing speculative. No features beyond
what was asked, no abstractions for single-use code, no error handling for
impossible scenarios. If 200 lines could be 50, rewrite it.

### 3. Surgical changes
Touch only what you must. Don't "improve" adjacent code, don't refactor what
isn't broken, match existing style. Remove orphans your changes created; leave
pre-existing dead code (mention it, don't delete it). Every changed line should
trace to the request.

### 4. Goal-driven execution
Define success criteria, loop until verified. "Fix the bug" → "write a test that
reproduces it, then make it pass." For multi-step tasks, state a brief plan with
a verify step for each.

## Using Crucible

These skills are installed (symlinked into `~/.claude/skills`) and auto-activate
by description — including while you work on Crucible itself. Full tour:
`/workshop`.

Headline orchestrators:
- `/build` — idea → working code (design → plan → TDD → quality-gate → PR)
- `/design`, `/planning` — when the design doc or plan is itself the deliverable
- `/debugging` — any bug, test failure, or unexpected behavior
- `/temper` — iterative fresh-eyes review of a PR or <base>..<head> range
- `/quality-gate` — red-team any artifact until clean
- `/recon` — investigate unfamiliar code before starting a task
- `/audit` / `/siege` — adversarial subsystem review / security audit
- `/skill-creator` — create, modify, and eval skills in *this* repo
- `/finish`, `/handoff`, `/forge` — wrap-up, session handoff, retrospective

Run `/skills` for the full catalog.
