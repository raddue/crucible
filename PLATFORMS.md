# Platform Compatibility

Crucible skills use the SKILL.md format published by Anthropic and adopted by Claude Code, Cursor, OpenAI Codex, and others. The core skill instructions (methodology, workflow, quality criteria) are platform-agnostic. Some advanced orchestration features are platform-specific and degrade gracefully.

## Compatibility Tiers

### Tier 1 — Fully Portable

These skills contain methodology instructions only. No platform-specific tool references in their workflow. They work identically on any platform that reads SKILL.md files.

| Skill | What It Does |
|-------|-------------|
| planning | Structured implementation planning with task decomposition |
| design | Interactive design refinement with investigation-driven decisions |
| test-driven-development | Red-green-refactor discipline with rationalization counters |
| verify | Evidence-before-claims verification discipline |
| review-feedback | Technical rigor when processing code review feedback |
| innovate | Divergent creativity injection before adversarial review |
| getting-started | Skill discovery and invocation discipline |
| finish | Branch completion workflow with structured options |

### Tier 2 — Portable with Reduced Capability

These skills use subagent dispatch for parallelism or fresh-perspective reviews. On platforms without subagent support, the methodology still applies — the agent follows the workflow sequentially instead of dispatching parallel reviewers.

| Skill | Platform Feature Used | Degraded Behavior |
|-------|----------------------|-------------------|
| quality-gate | Subagent dispatch for fresh reviewers each round | Agent reviews iteratively in-context (anchoring risk) |
| red-team | Subagent dispatch for Devil's Advocate reviewers | Agent plays Devil's Advocate in-context |
| inquisitor | 5 parallel adversarial dimensions | Dimensions run sequentially |
| code-review | Subagent dispatch for review | Agent reviews in-context |
| parallel | Subagent dispatch for independent tasks | Tasks run sequentially |
| adversarial-tester | Subagent dispatch for test writing | Agent writes tests in-context |
| debugging | Multiple subagent types (investigator, analyst, synthesis) | Agent runs all phases in-context |
| worktree | Git worktree creation | Standard branch-based isolation |
| stocktake | Subagent dispatch for skill auditing | Agent audits sequentially |

### Tier 3 — Platform-Dependent

These skills require features specific to Claude Code. They will not work on other platforms without adaptation.

| Skill | Platform Dependency | Why It Can't Degrade |
|-------|-------------------|---------------------|
| build | Agent teams (TeamCreate, TaskCreate, SendMessage) | Orchestrates 20+ subagents across 4 phases; sequential fallback exists but is Claude Code-specific |
| forge | Persistent memory (`~/.claude/projects/<hash>/memory/forge/`) | Retrospectives must persist across sessions to provide value |
| cartographer | Persistent memory (`~/.claude/projects/<hash>/memory/cartographer/`) | Codebase maps must persist across sessions to accumulate knowledge |

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

Two skills (forge, cartographer) store data in `~/.claude/projects/<project-hash>/memory/`. Other platforms would need an equivalent persistent storage mechanism for these skills to accumulate knowledge across sessions.

## Migration Roadmap

Full cross-platform support would require:

1. **Abstract tool references** — Replace Claude Code tool names in instructional text with platform-agnostic language (e.g., "spawn a subagent" instead of "use the Agent tool")
2. **Platform adapter layer** — Create per-platform configuration that maps abstract operations to concrete tool calls
3. **Storage abstraction** — Define a platform-agnostic storage interface for forge and cartographer
4. **Build skill refactor** — Replace TeamCreate/TaskCreate orchestration with a platform-agnostic dispatch pattern
5. **Namespace resolution** — Map `crucible:` prefix to each platform's skill invocation syntax

These changes are tracked in [issue #21](https://github.com/raddue/crucible/issues/21).
