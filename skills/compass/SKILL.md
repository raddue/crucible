---
name: compass
description: Read or update the per-repo arc-state file (docs/compass.md). Tracks current arc, last meaningful commit, open loops, next move, and don't-forget items. Auto-maintained by build, merge-pr, finish; read by getting-started. Use "compass read" to inspect project state, "compass update" to set a field, "compass doctor" to validate, "compass compress" when at cap. Triggers on "compass", "current arc", "project state", "what am I working on", "arc state", "where was I".
origin: crucible
---

<!-- CANONICAL: shared/compass-protocol.md -->

# Compass

A single `docs/compass.md` per repo that answers "where am I, what's the next move, what will I forget?" Auto-maintained by the skills that mark meaningful lifecycle events; read by `getting-started` at every session entry.

**Skill type:** Utility — direct execution, no subagent dispatch.

**Platform:** POSIX only (Linux, WSL2, macOS). Native Windows not supported in v1.

## When to use

| Situation | Action |
|-----------|--------|
| "What arc am I on?" / session reorientation | `compass read` or `compass read --compact` |
| Inspect full file | `compass read` |
| Manually set a field | `compass update --field <name> --value <value>` |
| File is at the 40-line cap | `compass compress` |
| Suspect schema drift or parse error | `compass doctor` |

Most users never invoke compass directly — it fires automatically through `build`, `merge-pr`, and `finish`.

## File location

`docs/compass.md` — committed to the repo (C-9 invariant). Verified by `git check-ignore docs/compass.md`.

## Schema

```markdown
# Compass

**Current arc:** #NNN: <one-line subject>
**Last meaningful commit:** `<sha>` — <one-line subject>
**Updated:** YYYY-MM-DD HH:MM:SS

## Open loops
- <one line each, max 5 visible>

## Next move
<one paragraph, max 5 lines>

## Don't forget
- <terse, max 3>
```

40-line hard cap (D4). Exceeding it raises `CompassFullError` (exit 2) — no data written. Run `compass compress` or edit manually before retrying.

## CLI reference

```
python scripts/compass.py <subcommand> [args]
```

| Subcommand | Notes |
|------------|-------|
| `read` | Print full `docs/compass.md`. |
| `read --compact` | 3-5 line summary (`[ARC]`, `[NEXT]`, `[OPEN]`, `[STALE]`). Used by `getting-started`. |
| `update --field X --value Y` | Set scalar field. List fields: repeat `--value` for each element (destructive replace). |
| `update --field X --value Y --value Z` | Set list field to `[Y, Z]`. |
| `append --field X --value Y` | Append one entry to a list field with dedup. |
| `update-many --field X --value Y --field Z --value W` | Atomic multi-field patch under one lock. |
| `doctor` | Validate schema, check line count, report stale status. |
| `compress` | v1.1 stub — exits 0 with advisory to edit manually or wait for v1.1. |

**Fields:** `current_arc` (scalar), `last_meaningful_commit` (scalar), `next_move` (scalar), `open_loops` (list, cap 5 visible / 10 hard), `dont_forget` (list, cap 3).

**Grammar constraints:**
- `current_arc` must match `#NNN: <subject>` (leading `#` required) or be empty string (arc-closure).
- `last_meaningful_commit` must contain a colon (`sha:subject`). `<pending>` and `<pending-merge:#NNN>` are valid sentinels.
- Setting `current_arc` to `<pending>` directly raises `ValueError` — that sentinel is internal to bootstrap only.
- `current_arc` subjects cannot contain the literal substring ` @ ` (space-at-space) — known v1 grammar restriction (D8.5 delimiter conflict).

## Integration points

Compass is auto-maintained at four lifecycle moments. Direct invocation is rarely needed.

| Skill | Event | Fields written |
|-------|-------|----------------|
| `build` | After Gate Ledger Initialization + resume decision, before Phase 1 IN_PROGRESS. Skipped on resume path. | `current_arc` |
| `merge-pr` | After `gh pr merge` succeeds and post-merge CI passes. | `last_meaningful_commit` |
| `finish` Option 1 | After local merge + tests pass. | `last_meaningful_commit` + arc-closure (`current_arc=''`, `next_move`) |
| `finish` Option 2 | After `gh pr checks --watch` returns green. | provisional arc-closure only (`current_arc=''`, `next_move`) |

`finish` Options 3 and 4 emit nothing. `getting-started` reads (never writes) via `compass read --compact`.

Sub-agents spawned inside these skills must not emit compass updates (D14 — best-effort in v1).

**Error policy:** compass emits are best-effort. A failed emit must not fail the enclosing pipeline.

## Multi-arc collision (D8/D8.5)

When `current_arc` is set to a new non-empty arc while an arc is already active, the prior arc is pushed onto `open_loops` as `[paused] #NNN: <subject> @ <timestamp>`. On resume (setting `current_arc` back to a paused arc's ticket), the paused entry is removed from `open_loops`.

Direct writes to `open_loops` by integration sites are prohibited (D8 direct-write invariant). Only manual user intervention sets `open_loops` directly.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CRUCIBLE_COMPASS_STALE_DAYS` | `14` | Days before `[STALE]` tag appears in compact output. Read per-call inside `read()` only. |
| `CRUCIBLE_COMPASS_TEST_SLEEP_MS` | `0` | Bounded `[0, 5000]` ms sleep inside `_acquire_lock` for test-orchestrated contention. Intentional; do not remove. |

## Key invariants

- **C-9:** `docs/compass.md` is NOT gitignored. Verified via `git check-ignore docs/compass.md`.
- **C-4:** 40-line hard cap. Any write producing >40 lines is rejected; no partial write occurs.
- **D11:** Idempotency — same `update --field X --value Y` applied twice yields the same state. True no-ops do not bump `Updated:`.
- **D14:** Compass emits only from skill orchestrators, never from sub-agents (best-effort, v1).

For full protocol details — lock mechanics, RMW flow, bootstrap sentinel, compact rendering spec, and invariants index — see `skills/shared/compass-protocol.md`.
