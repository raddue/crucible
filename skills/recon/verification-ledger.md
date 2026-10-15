# Verification Ledger

## Contents

- [Convention and scope](#verification-ledger-convention)
- [Empty state](#empty-state)
- [Falsification sentence](#handoff-doc-falsification-sentence-for-consumer-skills)
- [Maintainer notes](#for-recon-maintainers)

## Verification Ledger Convention

The `## Verification Ledger` section of the Investigation Brief is a
reader-friendly markdown record of causal claims made by recon. Per
DEC-2 / AMB-1, this is a **convention, not a regex-enforced contract** —
consumers that eventually need machine parseability will add a regex
contract then (flagged in the design's Open Questions).

### Scope

- Phase 3 core-scout causal claims only.
- Depth-module (Phase 4) claims are OUT OF SCOPE in MVP. A follow-up
  ticket may extend both the causal-lint and the ledger to depth modules.
- The ledger is the last core-brief section (after `## Open Questions`).
  Phase 4 depth modules are appended after the core brief, separated by
  `---` per existing convention.

### Per-entry format (reader-friendly, not a grammar)

    - **L-NN** — <claim text> — method: `<method>`, evidence: `<anchor>`, disposition: `<disposition>`

- **Ordinal `L-NN`** — zero-padded 2 digits, monotonic within the brief.
  Overflows to 3-digit `L-100+` are informational (brief is unusually
  large), not errors.
- **method** — one of `grep | read | math | glob | repro-test |
  dual-scout | structural-only | none`. A textual convention, not a
  regex-enforced enum.
- **evidence** — an anchor:
    - `file:line` for `grep`, `read`, `structural-only`
    - one-line derivation for `math`
    - glob pattern for `glob`
    - `<file>:<test>` for `repro-test`
    - `structure-scout, pattern-scout` for `dual-scout` (note the comma
      is part of the value, NOT a field separator — any future machine
      parser MUST respect backtick quoting)
    - em-dash `—` (U+2014) for `none` (plain hyphen also accepted by the
      reader-friendly convention; canonical form is em-dash)
- **disposition** — one of `confirmed | demoted | awaiting`.
    - `confirmed` — Causal-lint (a/b/c) satisfied.
    - `demoted` — lint failed; finding also moved to `## Open Questions`.
      The ledger entry is retained so future runs see "recon knew this
      was unverified."
    - `awaiting` — produced ONLY by `[evidence: structural-only:<anchor>]`.
      Claim is structurally verified but causally hypothetical; invites
      downstream falsification. Lint silent-failures produce `demoted`
      with a narrated warning, NOT `awaiting`.

### Empty state

If Phase 3's re-scan finds zero causal-keyword matches, the ledger is:

```
## Verification Ledger
<!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per the convention in skills/recon/SKILL.md. -->
```

The same placeholder comment is used for both empty and populated states
(single canonical form). A brief with keyword matches that were all
demoted by the lint still produces populated ledger entries with
`disposition: demoted` — it is NOT empty state.

### Handoff-doc falsification sentence (for consumer skills)

Downstream skills that discover a ledger claim was wrong record the
falsification in any markdown under the #211 doc-mining scopes
(`docs/handoffs/`, `docs/postmortems/`, `docs/retros/`,
`docs/retrospectives/`, `docs/decisions/`, `docs/adr/`, `docs/incidents/`,
or `HANDOFF.md` / `POSTMORTEM.md` / `DECISIONS.md` at repo root).

**Canonical sentence format (single line):**

    Recon claim falsified: L-<NN> from brief <run-id> — `<claim text verbatim>` — evidence: <what proved it wrong>.

Conventions:

- Wrap claim text in backticks (markdown code syntax) — renders cleanly
  even when claim text contains quotes or special characters. If claim
  text contains a literal backtick, escape with `` \` `` or abbreviate
  with `...` and reference the originating brief.
- **Keep the sentence on a single line** (no hard wrap) — grep returns
  one line per match. Abbreviate long claim text with `...`.
- Inline claim text so the falsification survives brief pruning.
- `<run-id>` is copy-pasted from the brief metadata block.
- **No identifier hash required.** Sentence format is the contract.
- Authoring skill may add its own signature (commit SHA, author) inline
  as prose — not formalized.

**Consumer contract:** briefs are write-once. Consumers never mutate
recon scratch brief files — they record falsifications in handoff docs
under their own control, which the next `/recon` run surfaces via Phase 5
falsification-grep and doc-mining.

In a repo with an ADR corpus (`docs/decisions/`), record the falsification
sentence under a trailing `## Falsifications` heading (created on first append),
so it cannot land under `## Status` or `## Decision`. <!-- CONTRACT:adr-falsification-home -->

### For recon maintainers

- Ledger format and assembly: see Phase 3 `### Ledger Assembly`.
- Disposition semantics and Claim Equivalence: see Phase 3
  `### Causal Claim Verification` + `#### Claim Equivalence`.
- Phase 5 grep-to-landmine flow: see Phase 5 `### Falsification Grep`.
- Brief write location: `<scratch>/investigation-brief.md` (INV-6 /
  INV-11).
