# Crucible

A collection of agent skills for systematic software development. Works with [Claude Code](https://claude.ai/code), [Cursor](https://cursor.com), [OpenAI Codex](https://openai.com/codex/), [Amp](https://amp.dev), [Cline](https://cline.bot), and any platform that supports the SKILL.md format.

51 skills across the full development lifecycle — design, planning, TDD implementation, code review, debugging, adversarial testing, and quality gates. 12 core skills are [eval-tested](docs/evals.md) with measured A/B deltas: **+23%** on execution evals (52 evals, 475 assertions, graded blind on Claude Opus 4.8) and **+31%** on sequence/ordering evals (18 evals, Opus 4.6 — not yet re-run on 4.8).

Skill value scales inversely with model capability: the same execution suite moved **+29% on Opus 4.6 → +23% on Opus 4.8**. The methodology is scaffolding that keeps a model on track, so the stronger the base model, the less lift it adds — one datapoint consistent with that thesis (not a controlled comparison — the two runs differ in more than the base model, since the methodology was also corrected between them, so the move can't be cleanly attributed to capability alone; see the [eval caveats](docs/evals.md)). On weaker models (Sonnet, Haiku, or non-Anthropic models in Cursor/Codex), we *expect* the deltas to widen — a prediction, not yet measured.

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged. Pipeline checkpoint system, auto skill extraction, structured context compression, and trajectory capture inspired by [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## Marketplace

| Platform | Status |
|----------|--------|
| Claude Code | Pending review |
| [skills.sh](https://skills.sh) | `npx skills add raddue/crucible` |
| Cursor / Codex / Amp / Cline | Compatible — same SKILL.md format |

## What you get

- **Iterative quality gates, not single-pass review** — `quality-gate` loops until clean (red-team → fix → fresh re-review), with weighted stagnation detection. Measured **+55% delta** (93% with vs 38% without — the largest delta in the suite even on Opus 4.8; see [eval results](docs/evals.md)).
- **Full pipeline orchestration** — `build` chains design → plan → execute → complete with shadow-git checkpoints, crash recovery, and structured compaction-state blocks. One command, idea to merged PR.
- **Adversarial testing at every level** — `adversarial-tester` writes tests designed to break the implementation; `inquisitor` runs 5 parallel attack dimensions against the full feature diff; `siege` runs 6 attacker-perspective security agents until zero Critical/High.
- **Token-efficient by design** — orchestrators use [disk-mediated dispatch](skills/shared/dispatch-convention.md): full subagent prompts go to `/tmp`, only ~100-token pointers enter orchestrator context. A full build saves 73-131K tokens of fossilized context.
- **Self-calibrating, not self-certifying** — gate verdicts append to a machine-local calibration ledger; `/calibration-reconcile` walks merged `fix/*` branches to falsify past verdicts and score each skill's [Brier](https://en.wikipedia.org/wiki/Brier_score) calibration, `/ledger` renders the honest "caught N silent bugs" headline with a rolling-median inflation detector, and the [Book of Grudges](skills/grudge/SKILL.md) surfaces past regressions on the files you're about to touch. Receipts between orchestrator and subagents are checked by a runtime linter (`scripts/rcpt_verify.py`), so a fabricated verdict can't pass unwitnessed.
- **Crash-resilient and session-continuous** — `replay` resumes interrupted pipelines from the last phase boundary (10 minutes, not 90); `recall` queries a searchable session activity index that survives compaction.
- **Forge-agnostic iterative code review** — `temper` runs fresh-eyes review loops on PRs from any platform (GitHub, GitLab, Bitbucket, self-hosted) or raw `<base>..<head>` ranges. Multi-round convergence with stagnation detection; optional external-model second opinion via MCP. Renamed from `/code-review` to avoid collision with Claude Code's built-in `/review`.

See [docs/architecture.md](docs/architecture.md) for how the orchestrator skills compose, and [docs/skills.md](docs/skills.md) for the full catalog.

## Install

### Claude Code

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
ln -sf ~/repos/crucible/skills/* ~/.claude/skills/
mkdir -p ~/.claude/agents
ln -sf ~/repos/crucible/agents/* ~/.claude/agents/
```

Or, when available on the marketplace: `claude plugin install raddue/crucible`. Note: the per-role model pins are currently delivered by the symlink install above — under a plugin install the agent types are namespaced (`crucible:…`) and bare-name dispatch resolution is unconfirmed (see [harness-adapter §8](skills/shared/harness-adapter.md#8-per-harness-install-manifest)).

### Cursor / OpenAI Codex / Amp / Cline

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
```

Then point your platform at the cloned skills directory. See [Cursor plugin docs](https://cursor.com/docs/plugins/building) and [Codex skills docs](https://developers.openai.com/codex/skills/). Some advanced features (parallel subagent dispatch, agent teams, persistent memory) are platform-specific and degrade gracefully — see [PLATFORMS.md](PLATFORMS.md).

## Setup essentials

**Run in auto mode** for autonomous pipelines (`/build`, `/debugging`, long `/quality-gate` runs). Auto mode lets Claude execute tool calls without per-action prompts while still confirming destructive operations. It supersedes earlier `--dangerously-skip-permissions` guidance.

**Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`** for build's parallel team execution. Without it, independent tasks fall back to sequential dispatch — everything still works, just slower.

**Recommended but optional:** enable the `forge` (retrospectives) and `cartographer` (codebase map) knowledge accelerators — they compound skill quality over time. See [docs/architecture.md](docs/architecture.md).

For hooks (session activity index, build routing advisor), MCP-based external model review, autocompact tuning, and other Claude Code specifics, see [docs/configuration.md](docs/configuration.md).

## Documentation

- [docs/skills.md](docs/skills.md) — full catalog of all 51 skills
- [docs/architecture.md](docs/architecture.md) — how the orchestrator skills compose
- [docs/configuration.md](docs/configuration.md) — Claude Code settings, hooks, MCP, env vars
- [docs/evals.md](docs/evals.md) — full eval methodology and per-skill A/B deltas
- [PLATFORMS.md](PLATFORMS.md) — cross-platform compatibility notes
