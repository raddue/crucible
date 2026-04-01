# Claude Code Internals — Skill Developer Reference

> Reference for crucible skill authors. Documents Claude Code's internal
> architecture patterns relevant to designing effective skills.
>
> **Last updated:** 2026-03-31
> **Source:** Public documentation, npm package analysis, community research

## Context Window Management

Claude Code manages context through three compaction layers:

### 1. Microcompaction (Continuous, Proactive)

- Runs continuously during a session
- Offloads bulky tool outputs to disk while keeping a "hot tail" of recent results visible
- Older tool results are stored by reference (file path) rather than fully in context
- Uses dynamic "output headroom" budgets — NOT a fixed threshold
- **Implication for skills:** Large tool outputs from early in a session are already being managed. Skills don't need to manually truncate tool results — but they DO need to persist critical state to disk because tool results will be evicted.

### 2. Auto-Compaction (Reactive, When Context Fills)

- Triggers when free context drops below reserved headroom (~25% remaining in VS Code, varies by client)
- Generates structured summaries covering: user intent, completed work, errors/corrections, active work, pending tasks, key references
- Post-compaction: re-reads 5 most recently accessed files to restore productivity
- **Implication for skills:** Compression State Blocks and handoff manifests are designed to survive auto-compaction's summarization. Structured blocks with clear delimiters (`===COMPRESSION_STATE===`) are more likely to be preserved than unstructured narrative.

### 3. Manual Compaction (/compact)

- User-triggered via `/compact` command with optional focus hint
- Cannot be triggered programmatically (no hook, MCP, or API mechanism)
- Fires PreCompact/PostCompact hooks
- **Implication for skills:** Cannot be incorporated into automated pipelines. Skills must design for auto-compaction recovery, not rely on manual triggers.

## Subagent Execution Models

Claude Code supports three execution models for subagents:

### Fork
- Inherits parent context and shares prompt cache
- Cache-optimized — cheapest model for short read-only tasks
- **When to use:** Researchers, quick lookups, reviewers that need parent context
- **Crucible usage:** Good for read-only investigation agents in debugging

### Teammate
- Separate pane in tmux/iTerm
- Communicates via file-based mailbox
- Independent context window
- **When to use:** Long-running parallel work that shouldn't pollute orchestrator context
- **Crucible usage:** Build pipeline's implementers and reviewers; quality-gate's red-team agents

### Worktree
- Own git worktree with isolated branch per agent
- Full filesystem isolation
- **When to use:** Parallel implementation tasks that touch the same files
- **Crucible usage:** Build pipeline feature work, parallel task waves

## CLAUDE.md

- Loaded into **every single turn** of the conversation
- 40,000 character budget
- Contains: project architecture, coding standards, file conventions, team patterns
- **Implication for skills:** Skills can reference CLAUDE.md content without re-stating it. If the project has a well-configured CLAUDE.md, skills get that context for free on every turn.

## Tool Architecture

### Tool Partitioning
- **Concurrent tools:** Read-only operations (Read, Glob, Grep, WebFetch) — can run in parallel
- **Serialized tools:** Mutating operations (Edit, Write, Bash) — run one at a time
- **Implication for skills:** Dispatch multiple read-only research agents in parallel freely. Serialized tools are the bottleneck — minimize unnecessary writes.

### Built-in Tool Count
- 66+ built-in tools as of March 2026
- Partitioned into the concurrent/serialized categories above

## Session Persistence

- Conversations saved as JSONL at `~/.claude/projects/<hash>/<session-id>/`
- `--continue` resumes last session; `--resume <session-id>` resumes specific session
- Long sessions accumulate session memory: structured summaries of task specs, file lists, workflow state, errors, learnings
- **Implication for skills:** Resuming a session is better than starting fresh. Skills that persist state to disk (forge, cartographer, checkpoint) enable effective session resumption.

## Permission System

Three permission modes:
- **Bypass:** No permission checks (dangerous but fast)
- **Allow-edits (acceptEdits):** Auto-allows file edits in working directory
- **Auto:** LLM classifier predicts which actions the user would approve; recommended mode

**Implication for skills:** Design skills to work within the auto permission model. Avoid requiring dangerous operations that the classifier would block. When dangerous operations are necessary (git reset, force push), document them clearly so the user can pre-approve.

## Prompt Cache Sharing

Subagents share prompt caches with their parent. This means:
- Parallelism is cheap — spinning up 5-10 subagents doesn't multiply cache costs
- Fork execution model maximizes cache hits
- **Implication for skills:** Don't avoid parallelism for cost reasons. The prompt cache makes parallel subagent dispatch nearly free compared to sequential dispatch.

## Interruption Architecture

- Streaming architecture makes interruption cheap
- Stopping mid-generation doesn't waste tokens beyond what was already consumed
- **Implication for skills:** Design skills so users can safely interrupt. Checkpoint early, persist state often. The user stopping a pipeline mid-run should be recoverable, not catastrophic.
