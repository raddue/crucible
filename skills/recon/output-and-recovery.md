# Output And Recovery

## Output and Return

Return the Investigation Brief as the agent output (inline return to parent skill).

The brief follows the exact core template assembled in
[Phase 3 — Assemble the Investigation Brief](#assemble-the-investigation-brief)
(metadata block + core sections through the Verification Ledger). Do not re-echo
that template here — it is the single source so the two copies cannot drift.

When depth modules ran, append their sections after a `---` separator, in this
order (only the requested modules' sections appear):

1. `## Impact Analysis`
2. `## Consumer Registry`
3. `## Friction Scan`
4. `## Subsystem Manifest`
5. `## Diagnostic Context`
6. `## Execution Readiness` — **Test command** / **Lint command** / **CI checks** / **Manual verification**

**When invoked as sub-skill:** Include `## Recon Progress` section at the top with all narration lines from the run.

## Scratch Directory and Context Management

### Scratch Path

`~/.claude/projects/<project-hash>/memory/recon/scratch/<run-id>/`

- `<run-id>` is a timestamp (e.g., `20260404-143022`)
- Access restricted to Write/Read/Glob tools — no Bash commands against `.claude/` paths

### Persisted Artifacts

| File | Purpose |
|---|---|
| `structure-scout-report.md` | Raw Structure Scout output |
| `pattern-scout-report.md` | Raw Pattern Scout output |
| `impact-analysis.md` | Depth module output (if requested) |
| `consumer-registry.md` | Depth module output (if requested) |
| `friction-scan.md` | Depth module output (if requested) |
| `subsystem-manifest.md` | Depth module output (if requested) |
| `diagnostic-context.md` | Depth module output (if requested) |
| `execution-readiness.md` | Depth module output (if requested) |
| `investigation-brief.md` | Final assembled brief |
| `pipeline-status.md` | Current pipeline status |

### Session Caching

Structure Scout reports are cached for cross-invocation reuse within a session:
- Cache path: `~/.claude/projects/<project-hash>/memory/recon/sessions/<session_id>/structure-scout.md`
- When `session_id` is provided, check this path before dispatching Structure Scout
- **Invalidation:** If the cached report's commit SHA (from the `<!-- cached-commit: ... -->` metadata line) differs from current HEAD, discard the cache and re-dispatch. Narrate: "Structure Scout cache invalidated (codebase changed: [old SHA] → [new SHA]). Re-running fresh." This handles cases where the codebase changes mid-session and ensures the parent skill knows the structural basis changed.
- Session cache files follow the same 24-hour stale cleanup as run directories

### Stale Directory Cleanup

At orchestrator startup, prune scratch directories older than 24 hours. Check directory timestamps via Glob and remove stale entries.

**Do not clean scratch until the Investigation Brief is returned to the caller.** Compaction recovery depends on scratch contents being available until the full brief is delivered.

## Compaction Recovery

If the orchestrator hits a compaction boundary mid-run:

1. **Read scratch directory listing** — determine which files exist
2. **Determine phase:**
   - No scout reports → still in Phase 1 or 2, restart from Phase 1
   - Scout reports exist, no `investigation-brief.md` → Phase 3 (synthesis), re-read scout reports
   - Brief exists, no depth module files for requested modules → Phase 4, dispatch remaining modules
   - All expected files present → Phase 5 or complete
3. **Re-read relevant files** from scratch to reconstruct state
4. **Read `pipeline-status.md`** for last known phase and progress
5. **Output status** to user before continuing
6. **Continue** from the determined phase

File presence is the completion signal — no health state machine needed.

## Error Handling

| Scenario | Behavior |
|---|---|
| Scout failure/timeout | Produce partial brief with available sections. Flag missing: `*Scout did not complete — section unavailable.*` |
| Depth module failure | Core brief still delivered. Failed module flagged. |
| No task + no scope + no modules | Valid invocation. Produces core-only full-repo brief. |
| Cartographer unavailable | Scouts explore from scratch (cold-start path). No error. |
| Both scouts fail | Return empty brief with all sections flagged as unavailable. Escalate to caller. |
| Context parameter exceeds budget | Warn but do not reject. Proceed at reduced scout context budget. |

## Brief Schema Stability

The Investigation Brief is consumed by 6+ skills. Section headers are the contract surface — consumers parse by header to extract relevant sections.

**Stable (changing requires updating all consumer templates):**
- Brief metadata fields: `Brief version`, `Task`, `Scope`, `Depth modules`, `Cartographer state`, `Commit`
- Core section headers: `## Project Structure`, `## Existing Patterns`, `## Scope Boundaries`, `## Prior Art`, `## Conflicts`

**Semi-stable (additive, consumers opt-in):**
- `## Open Questions` — present when scouts report unknowns. Consumers that need it parse for it; consumers that don't can ignore it. Not yet validated by consumer integration — promoted to stable once 2+ consumers confirm they consume it.
- `## Verification Ledger` — present in every brief (may contain only an HTML-comment placeholder when no causal claims detected). Consumers that do not parse the ledger can ignore it; the section is additive. The per-entry format is a reader-friendly convention, not a strict grammar.

**Semi-stable (consumers that request specific modules depend on these):**
- Depth module section headers: `## Impact Analysis`, `## Consumer Registry`, `## Friction Scan`, `## Subsystem Manifest`, `## Diagnostic Context`, `## Execution Readiness`
- Execution Readiness structured subfields: `Test command`, `Lint command`, `CI checks`, `Manual verification` — parsed by `/build`, must not be renamed without updating consumers

**Unstable (internal content, not parsed by header):**
- Content within sections — formatting, subheadings, bullet structure may evolve

**Process:** Any change to a stable or semi-stable header is a breaking change. The PR must update all consumer skill templates that reference the changed header. **Exception: adding a new semi-stable header is additive and non-breaking.** Consumers that don't parse the new section are unaffected. Renaming or semantically changing an existing header is still breaking. Adding new depth modules is non-breaking.

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
