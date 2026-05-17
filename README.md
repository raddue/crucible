# Crucible

A collection of agent skills for systematic software development. Works with [Claude Code](https://claude.ai/code), [Cursor](https://cursor.com), [OpenAI Codex](https://openai.com/codex/), [Amp](https://amp.dev), [Cline](https://cline.bot), and any platform that supports the SKILL.md format.

42 skills across the full development lifecycle — design, planning, TDD implementation, code review, debugging, adversarial testing, and quality gates. Every skill is [eval-tested](docs/evals.md) with measured A/B deltas (49 execution evals + 18 sequence evals, +29% / +31% average).

Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged. Pipeline checkpoint system, auto skill extraction, structured context compression, and trajectory capture inspired by [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## Marketplace

| Platform | Status |
|----------|--------|
| Claude Code | Pending review |
| [skills.sh](https://skills.sh) | `npx skills add raddue/crucible` |
| Cursor / Codex / Amp / Cline | Compatible — same SKILL.md format |

## What you get

- **Iterative quality gates, not single-pass review** — `quality-gate` loops until clean (red-team → fix → fresh re-review), with weighted stagnation detection. Measured **+68% delta** (see [eval results](docs/evals.md)).
- **Full pipeline orchestration** — `build` chains design → plan → execute → complete with shadow-git checkpoints, crash recovery, and structured compaction-state blocks. One command, idea to merged PR.
- **Adversarial testing at every level** — `adversarial-tester` writes tests designed to break the implementation; `inquisitor` runs 5 parallel attack dimensions against the full feature diff; `siege` runs 6 attacker-perspective security agents until zero Critical/High.
- **Token-efficient by design** — orchestrators use [disk-mediated dispatch](skills/shared/dispatch-convention.md): full subagent prompts go to `/tmp`, only ~100-token pointers enter orchestrator context. A full build saves 73-131K tokens of fossilized context.
- **Crash-resilient and session-continuous** — `replay` resumes interrupted pipelines from the last phase boundary (10 minutes, not 90); `recall` queries a searchable session activity index that survives compaction.
- **Forge-agnostic iterative code review** — `temper` runs fresh-eyes review loops on PRs from any platform (GitHub, GitLab, Bitbucket, self-hosted) or raw `<base>..<head>` ranges. Multi-round convergence with stagnation detection; optional external-model second opinion via MCP. Renamed from `/code-review` to avoid collision with Claude Code's built-in `/review`.

See [docs/architecture.md](docs/architecture.md) for how the orchestrator skills compose, and [docs/skills.md](docs/skills.md) for the full catalog.

## Install

### Claude Code

```bash
git clone git@github.com:raddue/crucible.git ~/repos/crucible
ln -sf ~/repos/crucible/skills/* ~/.claude/skills/
```

Or, when available on the marketplace: `claude plugin install raddue/crucible`.

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

- [docs/skills.md](docs/skills.md) — full catalog of all 42 skills
- [docs/architecture.md](docs/architecture.md) — how the orchestrator skills compose
- [docs/configuration.md](docs/configuration.md) — Claude Code settings, hooks, MCP, env vars
- [docs/evals.md](docs/evals.md) — full eval methodology and per-skill A/B deltas
- [PLATFORMS.md](PLATFORMS.md) — cross-platform compatibility notes
