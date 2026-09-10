# ADR-0002: Keep the calibration ledger machine-local

## Status
ACCEPTED

## Date
2026-09-10

## Context

Crucible's quality-gate emits calibration verdicts into a central store. That
store is the epistemic backbone of the repo's quality claims: tier-A gate
verdicts, per-skill calibration, and the reconciliation that decides whether a
verdict was right. It is a machine-local append-only JSONL at
`~/.claude/crucible/ledger/runs.jsonl`.

This repository is public. Committing the ledger would publish the raw record of
every session's gate verdicts. There is also a deliberate 11-row test fixture
committed in-repo at `.crucible/ledger/runs.jsonl` (schema/corpus reference),
which is a different file from the production store and must not be confused with
it.

## Decision

Keep the production calibration ledger at `~/.claude/crucible/ledger/runs.jsonl`,
never committed. Retain the 11-row in-repo fixture at `.crucible/ledger/runs.jsonl`
deliberately, as a schema/corpus reference (its former readers moved to the
private `raddue/crucible-eval` repo, per #460).

## Alternatives Considered

### Commit the ledger to version control
- Pros: the corpus would be shareable and diffable across the team.
- Cons: publishes gate verdicts and machine-local session data to a public repo;
  raw verdict JSONL is not a source artifact anyone should consume as code.
- Rejected: the ledger is private operational data, not documentation.

### Delete the 11-row fixture now that its readers moved out
- Pros: removes a file that could be read as production data.
- Cons: the fixture is the retained schema/corpus reference and test seed for
  emission-side helpers vendored by `raddue/crucible-eval` (#460).
- Rejected: keep it as a deliberate reference; it is distinct from the production
  store and documented as such.

## Consequences

Makes the calibration ledger machine-local, so quality claims are falsifiable
locally but never published. Requires the `CRUCIBLE_CALIBRATION_DISABLED=1`
kill-switch path and the in-repo fixture to be kept distinct from the production
store, which the write-path guard (`scripts/check_ledger_write_path.py`) enforces.