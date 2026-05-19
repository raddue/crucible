# Ledger Migration Protocol (L-7)

Invariant **L-7** governs schema evolution of `.crucible/ledger/runs.jsonl`,
`.crucible/ledger/falsification.jsonl`, and any future ledger files.

## Rules

1. **Forward-compatible readers.** Every reader (`/calibration-reconcile`,
   `/ledger`, advisory hooks, `scripts/ledger_reduce.py`) MUST ignore unknown
   keys. New keys appearing in a newer-version line must not cause parse failure
   or silent data drop.

2. **Never-decrease writers.** A writer at schema vN MUST emit every key that
   was present at any previous v1..vN-1. Tier B emitters set deprecated /
   inapplicable keys to **explicit `null`**, never absent. This guarantees
   readers can branch on key presence and never face an undefined absence.

3. **Mandatory migrate scripts ship WITH the version-bump PR.** When a PR
   raises `schema_version` from vN to vN+1, it MUST also add
   `scripts/migrate-ledger-vN-to-vN+1.{sh,py}` in the same commit / PR. No
   migrate script may merge before its corresponding schema bump; no schema
   bump may merge without its migrate script. Reviewers gate on this pairing.

4. **No migrate script ships in Phase 1.** This document establishes the
   convention. The first migrate script ships with a future v2 schema-bump PR
   (not Phase 1). Phase 1's schema is v1; there is nothing to migrate FROM yet.

5. **Tier-B explicit-null requirement.** Tier B stub emitters (red-team, audit,
   inquisitor) emit all schema-required keys explicitly null — see
   `skills/shared/ledger-append.md` §"Tier-B null semantics" for the canonical
   list. This is part of L-7: a schema-vN reader walking schema-vN-1 entries
   relies on the key being present.

## Migration-script contract

A migrate script at `scripts/migrate-ledger-vN-to-vN+1.{sh,py}` MUST:

- Be **idempotent**: re-running on an already-migrated ledger is a no-op.
- Be **backup-first**: write a `.bak.vN` sibling of the ledger before
  modifying in place, and refuse to run if a previous backup exists without
  explicit `--force`.
- Preserve **append-only history** (L-1): never delete or rewrite entries
  semantically; only add/rename keys per the bump.
- Update `schema_version` field on every migrated entry.
- Produce a final summary line: `migrated N entries from vN to vN+1`.

## When NOT to bump

Additive fields (new optional key with `null` default) do NOT require a
schema bump per L-7's forward-compat rule — readers ignore unknown keys.
Bump only when an existing key's **semantics** change or a required field
is **removed**.
