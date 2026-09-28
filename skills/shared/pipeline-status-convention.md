---
version: 1
---

# Pipeline Status Convention

Canonical reference for the per-run ambient status file shared by the
long-running orchestrators (`build`, `debugging`, `audit`, `siege`, `migrate`,
`spec`). Each skill references this file via
`<!-- CANONICAL: shared/pipeline-status-convention.md -->` and keeps only its
**skill-specific body** (Task Progress / Quality Gates / … ) plus its own
YELLOW/RED trigger heuristics — the shared protocol below is not duplicated
per skill (duplicating it caused drift).

**This is a shared skill reference, not a CLAUDE.md directive.**

## Runtime tool (preferred — the protocol below is the spec + fallback)

`python3 scripts/pipeline_status.py write --skill <s> --phase <text> --health
GREEN|YELLOW|RED [--suggested-action ".."] [--event ".."] ... [--body-file
<skill-body.md>]` rewrites the file atomically (single `write()`). It enforces
the health state machine and the last-5 events buffer; the orcheter's narration
becomes one call instead of hand-composing the file. `compact` prints the
recoverable subset for compaction recovery.

## File

- **Path:** `~/.claude/projects/<project-hash>/memory/pipeline-status.md`
  (`<project-hash>` = `sha256(cwd)[:16]`, same as the session-index convention).
- **Overwritten in full** at every write (never appended). Ambient awareness
  for the user in a second terminal; distinct from `build-gate-ledger.md`
  (which is the append-only gate-verdict audit trail).

## Write triggers

At every point the Communication Requirement mandates narration: before
dispatch, after completion, phase transitions, health changes, escalations,
and after compaction recovery.

## Header format

```markdown
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write — persisted across compaction>
**Skill:** <skill name>
**Phase:** <current phase, e.g. "3 — Execute (Autonomous)">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from **Started**>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

## Health state machine

Transitions are **one-directional within a phase**: `GREEN → YELLOW → RED`.
**Phase boundaries reset to GREEN.** A backward transition within the same
phase is a protocol violation — `pipeline_status.py` refuses it (fail-closed).
The *triggers* that map a situation to YELLOW/RED are skill-specific (e.g. a
review loop on round 3+, a quality-gate round 5+, a retry in progress, an
escalation pending, stagnation detected, failing tests) — each skill documents
its own; the machine is shared.

When YELLOW or RED, include a concrete `**Suggested Action:**`.

## Inline CLI format

- **Minor transitions** (dispatch, completion): one-liner, e.g.
  `Phase 3 [4/8] Task 4 IN REVIEW (pass 1) | GREEN | 1h 12m`
- **Phase changes / escalations:** expanded block with `---` separators
- **Health transitions:** always expanded, old → new

## Compaction recovery

The `## Compression State` sub-section of the skill-specific body (Goal / Key
Decisions / Active Constraints / Next Steps) is written alongside the status
file at checkpoint boundaries and is the first section read on recovery.
`pipeline_status.py compact` prints Phase / Started / Recent Events / the
skill-specific body for seeding a post-compaction context window.

## Skill-specific body

Each skill appends its own sections after `## Recent Events` (e.g. build's
`## Task Progress`, `## Quality Gates`, `## Checkpoints`, `## Compression
State`). That body is the only per-skill prose retained in the skill's SKILL.md
once it adopts this convention.