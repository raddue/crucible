# Ground-truth provenance — `tw3-openapi-md` (F1, escalator dominates docs branch)

Hand-derived from `skills/warden/SKILL.md` (the *Standalone inquisitor-inclusion
predicate* subsection); not recorded from a live run.

- **`reviewer_set` includes inquisitor — via block 1.** Block 1 (escalators) is evaluated
  FIRST: the single changed path `openapi.md` matches `**/openapi*` in the
  INTERFACE/API/SCHEMA glob set → **run inquisitor**. Block 2 (pure-doc) is never reached,
  so the `.md` extension does NOT earn a skip here. This is intended, and stated verbatim
  in SKILL.md's residual-risk note: "for `openapi.md`/`schema.md` the run is intended — an
  interface authored as markdown is not a doc." siege absent (non-security).

- **`verdict` = PASS.** All running legs clean → PASS.

- **What it pins (M4).** That escalators dominate the doc branch — a `.md` filename is not
  a free skip if the name also names an interface/schema. The direction is safe
  (over-inclusive → more inquisitor runs, never fewer).

Schema-gated only; behavioral teeth defer to the install-gated live pass (Acceptance
Gate 2). Not a live run.
