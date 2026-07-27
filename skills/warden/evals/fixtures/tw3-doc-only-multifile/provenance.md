# Ground-truth provenance — `tw3-doc-only-multifile` (INV-P8, pure-doc skip)

Hand-derived from `skills/warden/SKILL.md` (the *Standalone inquisitor-inclusion
predicate* subsection); not recorded from a live run.

- **`reviewer_set` = temper, delve, red-team — inquisitor SKIPPED via block 2.** Block 1
  (escalators): none of `README.md`, `guide.md`, `changelog.md` match the
  INTERFACE/API/SCHEMA or DEPENDENCY/lockfile glob sets (the names deliberately avoid the
  `**/index.*`/`**/schema*`/`**/openapi*`/`**/api/**` over-match cases), no binary path → miss. Block 2
  (pure-doc bounded subtraction): EVERY changed path is a pure-doc `.md` file → **skip
  inquisitor**. This is the token win — an all-docs sweep does not pay for the Opus 5-dim
  fan-out. siege absent (non-security).

- **`verdict` = PASS.** All three running legs clean → PASS.

Schema-gated only; behavioral classification (that a live standalone `/warden` on this
docs-only diff actually skips inquisitor) defers to the install-gated live pass
(Acceptance Gate 2). Not a live run.
