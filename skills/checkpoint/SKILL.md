---
name: checkpoint
description: Shadow git checkpoint system for pipeline rollback. Creates working directory snapshots without modifying the project's git history. Invoked by build, quality-gate, and debugging orchestrators at pipeline boundaries.
origin: crucible
---

# Checkpoint

Shadow git checkpoint system that snapshots and restores working directory state using an isolated git repository. The project's `.git` history is never touched.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Execution model:** No modes, no subagent dispatch. The consuming orchestrator (build, quality-gate, debugging) follows these instructions directly when taking or restoring checkpoints.

## Shadow Repository Setup

Initialize once per session, on first checkpoint request:

1. **Compute directory hash:** SHA-256 of the absolute working directory path, truncated to 16 characters.
   ```
   echo -n "/absolute/path/to/project" | sha256sum | cut -c1-16
   ```

2. **Shadow repo path:** `~/.claude/projects/<project-hash>/checkpoints/<dir-hash>/`

3. **Initialize:** If the shadow repo does not exist:
   ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git init
   ```

4. **Write `.gitignore`** in the shadow repo (not the project):
   ```
   node_modules/
   .env
   .env.*
   __pycache__/
   .git/
   venv/
   .venv/
   dist/
   build/
   .next/
   *.pyc
   .DS_Store
   ```

5. **Health check:** Before every operation, verify:
   ```bash
   GIT_DIR=<shadow-path> git rev-parse --git-dir
   ```
   If this fails, reinitialize the shadow repo and warn: "Shadow repo was corrupt — reinitialized. Prior checkpoints are lost."

**Tool constraint:** All shadow repo operations MUST use the Bash tool with explicit `GIT_DIR` and `GIT_WORK_TREE` environment variables. Never use Write/Read/Glob for shadow repo git operations. Never run git commands without these env vars — bare `git` commands would affect the project repo.

## Pre-Check: Directory Size

Before the first checkpoint in a session, count files in the working directory (excluding ignored paths):

```bash
find <working-dir> -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/venv/*' -not -path '*/.venv/*' -type f | wc -l
```

If count exceeds 50,000: skip all checkpoints for this directory with warning "Directory has >50,000 files — checkpoints disabled for performance." Cache this decision for the session (do not re-count).

## Create Checkpoint

1. **Deduplication:** Read the latest commit timestamp from the shadow repo:
   ```bash
   GIT_DIR=<shadow-path> git log -1 --format=%ct 2>/dev/null
   ```
   If the current time minus the commit timestamp is less than 1 second, skip this checkpoint (deduplication).

2. **Stage all files:**
   ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git add -A
   ```

3. **Commit:**
   ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git commit -m "<reason> | <timestamp> | <source-skill>" --allow-empty-message
   ```
   The `<reason>` is a structured string (e.g., `pre-design-gate`, `pre-wave-3`, `pre-qg-fix-round-2`). The `<source-skill>` is the consuming skill name (build, quality-gate, debugging).

4. **Record the commit hash** as the checkpoint ID.

5. **Update manifest:** Append an entry to `checkpoint-manifest.md` in the shadow repo directory (outside the git tree):
   ```
   | <hash-8-chars> | <timestamp> | <reason> | <source-skill> |
   ```

6. **Eviction:** After commit, count entries in `checkpoint-manifest.md`. If count exceeds 50 (configurable — orchestrators may override), remove the oldest entries from the manifest. Git objects for evicted commits are cleaned up by the Prune step.

## List Checkpoints

Read `checkpoint-manifest.md` from the shadow repo directory. Display in most-recent-first order:

```
| Hash     | Timestamp           | Reason              | Source       |
|----------|---------------------|----------------------|--------------|
| a1b2c3d4 | 2026-03-24 12:45:30 | pre-wave-3           | build        |
| e5f6g7h8 | 2026-03-24 12:30:15 | pre-plan-gate        | build        |
```

## Restore (Full Directory)

1. **Create a pre-restore safety checkpoint** with reason `pre-restore-safety` and source `checkpoint`. This enables "undo the undo."

2. **Restore:**
   ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git checkout <hash> -- .
   ```

3. **Verify:** Run the project's test suite or relevant subset to confirm the restored state is healthy.

4. **Report:** "Restored to checkpoint `<hash>` (`<reason>`). Safety checkpoint created at `<safety-hash>` — use this to undo the restore."

## Restore (Single File)

1. **Create a pre-restore safety checkpoint** with reason `pre-restore-safety-file` and source `checkpoint`.

2. **Restore:**
   ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git checkout <hash> -- <file-path>
   ```

3. **Report:** "Restored `<file-path>` from checkpoint `<hash>` (`<reason>`)."

## Prune

Run at session start (before first checkpoint) to reclaim space:

1. ```bash
   GIT_DIR=<shadow-path> GIT_WORK_TREE=<working-dir> git gc --prune=now
   ```

2. Read `checkpoint-manifest.md` and verify each entry's hash exists:
   ```bash
   GIT_DIR=<shadow-path> git cat-file -t <hash>
   ```
   Remove entries with invalid hashes (orphaned by prior gc).

## Compaction Recovery

The checkpoint manifest and shadow repo persist across compaction because they live in `~/.claude/projects/` (not in `/tmp/` or in-memory).

After compaction:
1. Recompute the directory hash from the current working directory path
2. Check if `~/.claude/projects/<project-hash>/checkpoints/<dir-hash>/` exists
3. If yes: read `checkpoint-manifest.md` to recover available checkpoints
4. If no: checkpoints are unavailable for this session (no error — the pipeline continues without checkpoint protection)

No active marker file is needed — the shadow repo's existence IS the marker. The directory hash computation is deterministic from the working directory path.

## Red Flags

- **NEVER** modify the project's `.git` directory
- **NEVER** run git commands without `GIT_DIR` and `GIT_WORK_TREE` env vars
- **NEVER** take a checkpoint mid-wave — wait for all parallel agents to complete before snapshotting
- **NEVER** auto-restore without user confirmation — always present restore as an option, not an action
- **NEVER** delete the shadow repo without explicit user request

## Integration

Consuming skills:
- **crucible:build** — Pipeline boundary checkpoints (pre-design-gate, pre-plan-gate, pre-wave-N, pre-cleanup-task-N, pre-code-review, pre-inquisitor, pre-impl-gate)
- **crucible:quality-gate** — Pre-fix-round checkpoints for code artifacts (pre-qg-fix-round-N)
- **crucible:debugging** — Pre-implementation, pre-sibling, and pre-quality-gate checkpoints (pre-debug-fix-cycle-N, pre-where-else, pre-debug-gate)
