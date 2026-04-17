# Scratch Directory (spec)

**Canonical path:** `~/.claude/projects/<project-hash>/memory/spec/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at run start (e.g., `2026-03-21T14-30-00`). All state is persisted to disk — the orchestrator never relies solely on context memory for critical state.

## Shared Files (written only by the orchestrator)

- **`invocation.md`** — Written at run start. Contains: epic URL, extraction method used, user preferences (auto-PR yes/no).
- **`scope-units.json`** — Extracted ticket list with titles and numbers.
  ```json
  {
    "tickets": [
      { "number": "#123", "title": "Add auth middleware" },
      { "number": "#124", "title": "Refactor token validation" }
    ]
  }
  ```
- **`dependency-graph.json`** — DAG of ticket dependencies. Updated by the orchestrator after each wave completes, incorporating discoveries from teammates.
  ```json
  {
    "edges": [
      { "from": "#124", "to": "#123", "reason": "Token validation depends on auth middleware interface" }
    ]
  }
  ```
- **`wave-schedule.json`** — Ordered list of execution waves, each containing a list of ticket numbers. Updated when dependency discovery causes re-queuing.
  ```json
  {
    "waves": [
      { "wave": 1, "tickets": ["#123", "#125", "#127"] },
      { "wave": 2, "tickets": ["#124", "#126"] }
    ]
  }
  ```
- **`contracts/`** — Directory containing committed contract YAML files, indexed by ticket number. Cross-referenced during cascading.
- **`decisions.md`** — Append-only log of autonomous decisions across all tickets. Each entry: ticket number, decision ID, choice made, alternatives considered, confidence score. Updated by the orchestrator after each wave completes using teammate outputs.
- **`ticket-status.json`** — Per-ticket status tracking. Updated only by the orchestrator.
  ```json
  {
    "#123": { "status": "committed", "reason": null, "wave": 1 },
    "#124": { "status": "pending", "reason": null, "wave": 2 },
    "#125": { "status": "failed", "reason": "Contract validation failed after retry", "wave": 1 }
  }
  ```
  Valid statuses: `pending`, `investigating`, `dependency-check`, `writing`, `validating`, `committed`, `failed`, `blocked`, `re-queued`, `needs-respec`.
  Terminal states: `committed`, `failed`, `blocked`, `needs-respec`.

## Per-Ticket Directories (written by teammates)

Each teammate writes exclusively to `scratch/<run-id>/tickets/<ticket-number>/`. This prevents concurrent modification of shared files when multiple teammates run in parallel within a wave.

- **`tickets/<ticket-number>/output/`** — Design doc, implementation plan, and contract produced by this ticket's teammate.
- **`tickets/<ticket-number>/decisions.md`** — Decisions made during this ticket's investigation. The orchestrator merges these into the shared `decisions.md` after the wave completes.
- **`tickets/<ticket-number>/discoveries.json`** — New dependency discoveries found during investigation.
  ```json
  {
    "dependencies": [
      { "from": "#123", "to": "#126", "reason": "Auth middleware needs event bus from #126" }
    ]
  }
  ```
- **`tickets/<ticket-number>/status.json`** — This ticket's final status and any error details. The orchestrator merges into shared `ticket-status.json` after the wave completes.
  ```json
  {
    "status": "committed",
    "alerts": [
      { "ticket": "#123", "confidence": "medium", "decision": "DEC-1", "summary": "Chose Redis over Postgres for session store" }
    ]
  }
  ```

## Orchestrator Reconciliation

After each wave completes, the orchestrator reads all per-ticket directories from that wave and updates the shared state files (dependency graph, decisions log, ticket status, wave schedule). This serialized update eliminates race conditions while preserving parallel execution within waves.

**Contract cascading:** After reconciliation, copy newly emitted contracts from `tickets/<ticket-number>/output/` into the shared `contracts/` directory so downstream waves have access to upstream contracts.

## Stale Cleanup

Delete scratch directories older than 24 hours at run start, but only when ALL tickets in that directory's `ticket-status.json` are in `committed` status. Directories containing any ticket in `needs-respec`, `blocked`, or `failed` status are preserved regardless of age — these terminal states expect re-invocation and user action, and deleting them would lose the recovery context.

## Project-Hash Recovery

If the expected scratch directory is not found at the canonical path (e.g., because the repo moved or the project hash changed), search all project hashes under `~/.claude/projects/*/memory/spec/scratch/` for any `invocation.md` containing the current epic URL. If a match is found, adopt that scratch directory for the current run. If no match is found, start a fresh run.
