# Platform Compatibility

Crucible skills use the SKILL.md format published by Anthropic and adopted by Claude Code, Cursor, OpenAI Codex, and others. The core skill instructions (methodology, workflow, quality criteria) are platform-agnostic. Some advanced orchestration features are platform-specific and degrade gracefully.

## Compatibility Tiers

### Tier 1 — Fully Portable

These skills contain methodology instructions only. No platform-specific tool references in their workflow. They work identically on any platform that reads SKILL.md files. Some reference other crucible skills by name (e.g., `crucible:quality-gate`) — these are inter-skill dependencies, not platform coupling. If the referenced skill is installed, it works; if not, the agent skips it. Incidental use of universal tooling (`git`, `gh`/`glab`) to read or record local state is permitted and does not count as platform coupling — what places a skill here is the absence of subagent dispatch and of any *required* specialized platform feature.

| Skill | What It Does |
|-------|-------------|
| planning | Structured implementation planning with task decomposition |
| test-driven-development | Red-green-refactor discipline with rationalization counters |
| verify | Evidence-before-claims verification discipline |
| review-feedback | Technical rigor when processing code review feedback |
| getting-started | Skill discovery and invocation discipline |
| handoff | Session-handoff doc capturing arc state and the next pickup |
| workshop | Guided tour of the headline orchestrator skills |

### Tier 2 — Portable with Reduced Capability

These skills depend on either subagent dispatch (for parallelism or fresh-perspective reviews) or a *required* specialized external tool — shadow git snapshots, a forge CLI for CI/merge, document converters, or package auditors — that the skill's core function cannot proceed without. On a platform lacking the feature, the methodology still applies but with reduced capability: subagent work runs sequentially in-context, and tool-backed work falls back to manual steps.

| Skill | Platform Feature Used | Degraded Behavior |
|-------|----------------------|-------------------|
| quality-gate | Subagent dispatch for fresh reviewers each round | Agent reviews iteratively in-context (anchoring risk) |
| red-team | Subagent dispatch for Devil's Advocate reviewers | Agent plays Devil's Advocate in-context |
| inquisitor | 5 parallel adversarial dimensions | Dimensions run sequentially |
| temper | Subagent dispatch for review | Agent reviews in-context |
| parallel | Subagent dispatch for independent tasks | Tasks run sequentially |
| adversarial-tester | Subagent dispatch for test writing | Agent writes tests in-context |
| skill-creator | Subagent dispatch for blind A/B skill evals | Eval runs sequentially in-context; quantitative benchmarking skipped |
| assay | Subagent dispatch for approach evaluation (Opus evaluator) | Evaluates approaches in-context |
| prd | Subagent dispatch for PRD authoring (Sonnet writer) | Writes the PRD in-context |
| test-coverage | Subagent dispatch for the test-audit agent (Opus) | Audits tests in-context |
| debugging | Multiple subagent types (investigator, analyst, synthesis) | Agent runs all phases in-context |
| design | Subagent dispatch for parallel investigation + Challenger | Investigation/challenge run in-context |
| innovate | Subagent dispatch for the Innovation proposer (Opus) | Proposal generated in-context |
| finish | `git` + forge CLI (`gh`) for completion; subagent dispatch for code review | Manual completion + in-context review |
| worktree | Git worktree creation | Standard branch-based isolation |
| stocktake | Subagent dispatch for skill auditing | Agent audits sequentially |
| audit | Subagent dispatch for parallel analytical lenses | Lenses run sequentially in-context |
| delve | Subagent dispatch for finder fan-out + verify gate | Finders run sequentially |
| recon | Subagent dispatch for parallel scouts | Scouts run sequentially |
| prospector | Subagent dispatch for parallel exploration | Explores sequentially |
| siege | Parallel attacker-perspective agents (scales 3–6) | Perspectives run sequentially |
| spec | Subagent dispatch for per-ticket investigation | Tickets processed sequentially |
| migrate | Subagent dispatch (recon/assay); build for execution | Planning runs sequentially; execution mode needs build (Tier 3) |
| checkpoint | Shadow git snapshots for pipeline rollback | No automatic rollback; manual git recovery |
| compass | `scripts/compass.py` CLI (POSIX only) | Arc-state file (`docs/compass.md`) maintained by hand |
| merge-pr | `git` + a forge CLI (`gh` or equivalent) for CI checks and merge | Manual merge + CI inspection |
| distill | External document converters (pandoc, pdftotext, LibreOffice) | Cannot ingest binary document formats |
| dependency-audit | External auditors (npm/cargo/pip-audit) | No supply-chain signal produced |
| source-driven-development | Live documentation fetch (web access) | Falls back to (possibly stale) training recall |

### Tier 3 — Platform-Dependent

These skills require features specific to Claude Code. They will not work on other platforms without adaptation.

| Skill | Platform Dependency | Why It Can't Degrade |
|-------|-------------------|---------------------|
| build | Agent teams (TeamCreate, TaskCreate, SendMessage) | Orchestrates 20+ subagents across 4 phases; sequential fallback exists but is Claude Code-specific |
| forge | Persistent memory (`~/.claude/projects/<hash>/memory/forge/`) | Retrospectives must persist across sessions to provide value |
| cartographer-skill | Persistent memory (`~/.claude/projects/<hash>/memory/cartographer/`) | Codebase maps must persist across sessions to accumulate knowledge |
| project-init | Persistent cartographer memory + subagent scan | Onboarding output must persist across sessions, like cartographer's |
| grudge | Machine-local per-repo persistent memory (regression graveyard) | Regression memory must persist across sessions to guard future edits |
| ledger | Machine-local calibration ledger (`~/.claude/crucible/ledger/`) | Calibration history must persist to be meaningful |
| calibration-reconcile | Machine-local ledger + git branch walkback | Falsification needs the persisted verdict history |
| recall | Session activity index maintained by PostToolUse hooks | No event log without the hook infrastructure |
| replay | Pipeline dispatch manifests + checkpoints | Crash recovery needs Claude Code pipeline state |
| consensus | MCP multi-provider model dispatch | Multi-model synthesis needs MCP providers |
| temper-eval-calibrate | Session-dispatch eval harness (Claude Code) | Wraps live session invocations; no portable equivalent |
| temper-eval-collect | Task-tool parallel reviewer dispatch (Claude Code) | Live reviewer dispatch is harness-specific |
| skill-selection-evals | Anthropic skill-creator eval harness | Eval-only; consumed by the blind A/B tooling, not invoked at runtime |

### Tier 4 — Domain-Specific (Unity UI Toolkit)

These skills work on any platform but are only useful for Unity UI Toolkit projects.

| Skill | Domain |
|-------|--------|
| mockup-builder | HTML mockups constrained to Unity Theme.uss variables |
| mock-to-unity | CSS-to-USS translation with Unity 6 bug workarounds |
| ui-verify | Visual comparison of implemented UI against mockup |

## Platform-Specific References

The following Claude Code-specific references appear in skill instructions. These are the items that would need adaptation for full cross-platform support.

### Tool Names

| Claude Code Tool | Purpose | Cross-Platform Equivalent |
|-----------------|---------|--------------------------|
| `Agent` | Spawn subagent for parallel/isolated work | Platform's subagent/subprocess mechanism |
| `TeamCreate` | Create agent team for coordinated parallel work | Not widely available; sequential fallback |
| `TaskCreate` / `TaskUpdate` | Track task state across subagents | Platform's task tracking or manual state |
| `SendMessage` | Communicate between agents | Platform's inter-agent messaging |
| `Read`, `Edit`, `Write` | File operations | Universal (all platforms provide these) |
| `Glob`, `Grep` | File search | Universal (all platforms provide these) |
| `Bash` | Shell execution | Universal (all platforms provide this) |
| `Skill` | Invoke another skill | Platform's skill invocation mechanism |

### Subagent Configuration

| Claude Code Parameter | Purpose | Notes |
|----------------------|---------|-------|
| `subagent_type="general-purpose"` | Full-capability subagent | Default on most platforms |
| `subagent_type="Explore"` | Fast, read-only codebase search | May not have direct equivalent |
| `model: opus` | Use strongest model for complex work | Platform selects model; skill still works |
| `model: sonnet` | Use mid-tier model for routine reviews | Platform selects model; skill still works |
| `model: haiku` | Use fast model for simple lookups | Platform selects model; skill still works |

### Skill Invocation

Skills reference each other using the `crucible:` prefix (e.g., `crucible:quality-gate`, `crucible:test-driven-development`). On Claude Code, this maps to the skill namespace. On other platforms, the invocation syntax may differ but the skill names remain the same.

### Environment Variables

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Enable agent teams for parallel execution | No — skills degrade to sequential |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | Earlier context compaction for long pipelines | No — performance optimization only |

### Persistent Storage

Two skills (forge, cartographer-skill) store data in `~/.claude/projects/<project-hash>/memory/`. Other platforms would need an equivalent persistent storage mechanism for these skills to accumulate knowledge across sessions.

## Migration Roadmap

Full cross-platform support would require:

1. **Abstract tool references** — Replace Claude Code tool names in instructional text with platform-agnostic language (e.g., "spawn a subagent" instead of "use the Agent tool")
2. **Platform adapter layer** — Create per-platform configuration that maps abstract operations to concrete tool calls
3. **Storage abstraction** — Define a platform-agnostic storage interface for forge and cartographer-skill
4. **Build skill refactor** — Replace TeamCreate/TaskCreate orchestration with a platform-agnostic dispatch pattern
5. **Namespace resolution** — Map `crucible:` prefix to each platform's skill invocation syntax

These changes are tracked in [issue #21](https://github.com/raddue/crucible/issues/21).
