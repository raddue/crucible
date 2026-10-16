# Investigation Workflow

## Contents

- [Phase 1: Cartographer consult](#phase-1-cartographer-consult)
- [Phase 2: Scout dispatch](#phase-2-scout-dispatch)
- [Phase 3: Core synthesis](#phase-3-core-synthesis-orchestrator-local)
- [Phase 4: Depth modules](#phase-4-depth-module-dispatch)
- [Phase 5: Persistent-map feedback](#phase-5-cartographer-feedback)

## Phase 1: Cartographer Consult

Before dispatching scouts, check for existing cartographer data.

1. Read `map.md` from cartographer storage directory (direct file read via Read tool — no agent dispatch)
   - Storage path: `~/.claude/projects/<project-hash>/memory/cartographer/map.md`
2. **If map exists:** Extract relevant module context for scouts. Pass module files, conventions, and landmines as the `[CARTOGRAPHER]` placeholder content.
3. **If cold start (no map):** Set `[CARTOGRAPHER]` to "No cartographer data — explore from scratch." Proceed normally.
4. **Provenance tracking:** Instruct scouts to annotate findings sourced from cartographer with `(cartographer)` in their output. Freshly discovered findings are unmarked. This lets consumers distinguish verified-from-memory vs. discovered-now.

## Phase 2: Scout Dispatch

### Session Cache Check

If `session_id` is provided:
1. Check for cached Structure Scout report at: `~/.claude/projects/<project-hash>/memory/recon/sessions/<session_id>/structure-scout.md`
2. **If cached report exists:** Skip Structure Scout dispatch. Use cached report. Mark Structure Scout as `cached` in pipeline status.
3. **If no cache:** Dispatch normally. After completion, write report to cache path with a metadata line prepended: `<!-- cached-commit: [HEAD SHA] -->`. This line is used for invalidation checks.

Pattern Scout always runs fresh — its output varies with cascading context.

### Dispatch

Dispatch both scouts in parallel (or just Pattern Scout if Structure Scout is cached). These snippets show Claude Code's native call-level `model:` parameter; retain the neutral profile labels in bookkeeping, map profiles per `shared/harness-adapter.md` on other harnesses, and omit unsupported model fields.

**Structure Scout:**
```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Structure Scout: map project layout for [task summary]"
```
- Template: `./structure-scout-prompt.md`
- Fill placeholders: `[TASK]`, `[SCOPE]`, `[CONTEXT]`, `[CARTOGRAPHER]`
- **Default values for absent parameters:**
  - `[TASK]` → "Full repository scan — no specific task"
  - `[SCOPE]` → "No scope constraint — explore entire repository"
  - `[CONTEXT]` → "No prior decisions"

**Pattern Scout:**
```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Pattern Scout: discover conventions and prior art for [task summary]"
```
- Template: `./pattern-scout-prompt.md`
- Fill placeholders: `[TASK]`, `[SCOPE]`, `[CONTEXT]`, `[CARTOGRAPHER]`

<!-- TRUST: scout report is L4 — cross-check paths against L3 before synthesis. -->
On completion, write raw scout reports to scratch directory:
- `<scratch>/structure-scout-report.md`
- `<scratch>/pattern-scout-report.md`

Narrate: "Scouts complete. Synthesizing core brief. [N conflicts detected.]"

## Phase 3: Core Synthesis (Orchestrator-Local)

<!-- TRUST: synthesis input is L4 until cross-verified against L3 source. -->
**No synthesis subagent.** The orchestrator reads both scout reports and assembles the Investigation Brief directly.

### Scope Merging

**If caller provided explicit `scope:` parameter:** Use it directly. Skip scout suggestions entirely.

**Otherwise, merge scout suggestions:**

1. **In Scope:** Union of both scouts' `suggested_scope.in_scope` paths.
   - Paths suggested by **both** scouts: marked `high confidence`
   - Paths suggested by **only one** scout: marked `medium confidence` with attribution (e.g., "suggested by Structure Scout")

2. **Contested paths:** When one scout includes a path and the other excludes it:
   - Place under `### Contested` in Scope Boundaries (not excluded)
   - Include reasoning from each scout
   - **Consumer guidance:** Contested paths should be treated as in-scope unless the consumer has a specific reason to exclude them. The annotation signals lower confidence, not a decision for the consumer to make.

3. **Out of Scope:** Uncontested exclusions — both scouts agree to exclude, or only one scout mentions exclusion and the other is silent.

### Contradiction Detection

Cross-check the two scout reports for conflicting evidence. Examples:
- Structure Scout maps a directory as inactive but Pattern Scout finds live test references to it
- Scouts disagree on module boundaries or build system identification
- One scout identifies a file as an entry point, the other doesn't mention it despite covering the same area

Surface contradictions in `## Conflicts` section with:
- The tension described
- Evidence from Structure Scout (claim + evidence)
- Evidence from Pattern Scout (claim + evidence)
- Confidence assessment (which is stronger and why, or "unresolved")

Conflicts are high-value cartographer feed-back material.

### Cartographer Conflict Resolution

When scouts report `cartographer-conflict` findings, apply this adjudication table:

| Condition | Both scouts agree? | Evidence type | Action |
|---|---|---|---|
| Path no longer exists + both agree | Yes | Negative (absence) | **Auto-update** — path evidence is verifiable |
| Positive assertion + both agree | Yes | Positive (file exists, pattern found) | **Auto-update** — new finding is grounded |
| Both agree, no supporting evidence | Yes | Neither | **Unresolved** — agreement alone insufficient (correlated input priors) |
| Deletion from cartographer | Yes or No | Any | **Always unresolved** — requires user confirmation |
| Single scout only | No | Any | **Unresolved** — prevents single-scout hallucination |

**Why agreement alone is insufficient:** Both scouts receive the same cartographer context and task description as input. Their exploration is correlated, not independent. Two correlated errors do not constitute independent verification. Auto-update requires agreement PLUS verifiable evidence.

For auto-update actions: queue the update for Phase 5 (Cartographer Feedback).
For unresolved actions: surface in the `## Conflicts` section of the brief.

### Causal Keyword Set

The canonical list of causal-language keywords used by both the Causal Claim
Verification step and the Phase 3 Ledger Assembly re-scan. Both steps MUST
reference this set by name; do not re-list keywords inline. **This set is
referenced by name from (a) Causal Claim Verification and (b) Ledger Assembly
step (below) — update in both uses when modifying.**

    fixes, causes, is the bug, is the fix, will resolve, root cause is,
    caused by, resolved by, because, due to, leads to, responsible for,
    the culprit, breaks because, stems from, triggers, originates,
    accounts for, cascades from, propagates from, results in, arises from,
    comes from, introduced by, source of, →, explains why, the reason *
    is, is why * fails

Keyword matching is case-insensitive with word-boundary semantics (the
keyword must not be embedded inside a larger word). Phrase patterns with `*`
allow up to 5 intervening words between the anchors.

### Causal Claim Verification

After contradiction detection, scan both scout reports for causal language
using the **Causal Keyword Set** defined above.

For each match, verify the finding has at least ONE of:

  (a) Repro test cited (file + test name)
  (b) Math or logic derivation included in the finding
  (c) Both scouts reached the same claim independently, where "same claim"
      is defined by the **Claim Equivalence** rule below.

If none of (a)/(b)/(c) hold, DEMOTE the finding to an Open Question with this
format:

    **Question:** [scout-name proposed: "X causes Y"]. Not verified.
    **Why it matters:** If true, resolves Y; if false, misdirects investigation.
    **Resolvable by:** [repro test / math derivation / second-scout corroboration]

Causal claims that pass verification appear in their normal brief section
(e.g., Project Structure, Existing Patterns) unchanged. Demoted claims appear
in Open Questions with the verification gap explicit.

Scout-supplied confidence labels are ADVISORY — this lint checks for evidence,
not self-labels. A scout-tagged `[confidence: high]` claim without (a)/(b)/(c)
is still demoted.

#### Claim Equivalence

Two causal claims A and B are "the same claim" if their normalized token sets
satisfy **token Jaccard ≥ 0.70**:

1. Normalize: lowercase, strip punctuation, split on whitespace → token set.
2. Compute |A ∩ B| / |A ∪ B|. If ≥ 0.70, A and B are pairwise-equivalent.
3. **Transitive closure (union-find).** Build a graph over all claims with an
   edge for each pairwise-equivalent pair. The connected components
   (computed via union-find) are the equivalence classes. This yields a
   deterministic result independent of comparison order — if A ↔ B and
   B ↔ C but A and C do not pairwise match, A, B, C still form one class.

The same Claim Equivalence rule is used by the Phase 3 Ledger Assembly
dedup step (see below). Criterion (c) and Ledger Assembly dedup share this
one canonical definition.

### Ledger Assembly

After Causal Claim Verification, assemble the `## Verification Ledger`
section of the Investigation Brief. The ledger covers Phase 3 core-scout
causal claims only — depth-module (Phase 4) claims are out of scope.

**Algorithm:**

1. **Re-scan** both scout reports for causal-keyword matches using the
   **Causal Keyword Set** defined above. For each match, check whether
   the lint demoted the finding to Open Questions; this drives the
   disposition.
2. **Deduplicate** using the **Claim Equivalence** rule (token Jaccard
   ≥ 0.70 + transitive-closure via union-find — same rule used by
   Causal Claim Verification criterion (c)). Claims in one equivalence
   class merge into a single ledger entry.
3. **For each merged claim:**
   - **(a) Evidence source.** Extract `[evidence: <method>:<anchor>]`
     from the scout finding. If missing, fall back to lint-internal
     evidence:
       - If lint (a) cited a repro test (`file:test_name`) → `method:
         repro-test`, `evidence: <file:test>`.
       - If lint (b) cited a math/logic derivation → `method: math`,
         `evidence: <one-line summary>`.
       - If neither → `method: none`, `evidence: —` (em-dash U+2014).
   - **(b) Dual-scout override.** If lint criterion (c) fired for this
     merged claim, override to `method: dual-scout`, `evidence:
     structure-scout, pattern-scout`. **Tie-break:** if EITHER scout
     tagged `structural-only` for this claim, DO NOT override —
     `structural-only` takes precedence, disposition stays `awaiting`.
     **Merged-claim tag tie-break:** if dedup merged two claims and BOTH
     scouts emitted non-structural-only `[evidence:]` tags (lint (c) did
     not fire), use the Pattern Scout's tag (richer conventions anchor).
   - **(c) Disposition:**
       - `method: structural-only` → `awaiting` (overrides lint verdict;
         `awaiting` has exactly one producer).
       - Otherwise, lint passed (a/b/c) → `confirmed`.
       - Otherwise → `demoted`.
4. **Assign ordinal** `L-NN` (zero-padded 2 digits, monotonic within the
   brief; continue as 3-digit `L-100+` if the brief exceeds 99 entries —
   informational, not an error).
5. **Append to the ledger section.** Per-entry format:

       - **L-NN** — <claim text> — method: `<method>`, evidence: `<anchor>`, disposition: `<disposition>`

   The ledger section is the **last core-brief section** (after
   `## Open Questions`). Empty state (zero causal-keyword matches from
   step 1) emits only the section header plus the canonical HTML-comment
   placeholder:

       ## Verification Ledger
       <!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per skills/recon/verification-ledger.md. -->

   The same placeholder is used for both empty and populated states —
   see `## Verification Ledger Convention`.

6. **Write the assembled brief** (including the ledger) to
   `<scratch>/investigation-brief.md` at the end of Phase 3. This is the
   **core brief**. This step also closes an existing latent gap where
   `investigation-brief.md` was referenced by Persisted Artifacts and
   Compaction Recovery but no phase wrote it.

   Phase 4's depth-module append is a recon-internal re-write of this
   file, permitted by I-2 (consumer skills may not mutate it; recon
   itself may). See Phase 4 Output Handling for the serialized re-write
   rule.

### Open Questions Aggregation

After contradiction detection, aggregate open questions from both scout reports:

1. Collect all items from each scout's `### Open Questions` section
2. Deduplicate — merge questions about the same unknown from both scouts
3. Tag each question with:
   - **Relevant to:** which consumer skills would need this answer (e.g., `/design`, `/build`)
   - **Resolvable by:** what specific investigation or human input would answer it (e.g., "check with team lead", "run integration tests", "read module X in detail")
4. If depth modules also report open questions, merge those in during Phase 4

Open questions that get resolved in subsequent pipeline phases are high-value cartographer recordings — feed them back in Phase 5.

### Assemble the Investigation Brief

Build the Investigation Brief markdown with all core sections:

```markdown
# Investigation Brief
**Brief version:** 1
**Task:** [task description or "Full repository scan"]
**Scope:** [constrained path or "Full repo"]
**Depth modules:** [list or "Core only"]
**Cartographer state:** [consulted / cold start / N/A]
**Commit:** [HEAD SHA at investigation time]

## Project Structure
[From Structure Scout report — module layout, entry points, build system, key directories]

## Existing Patterns
[From Pattern Scout report — conventions, naming, test patterns, abstractions]

## Scope Boundaries
### In Scope
- [path/area] — [why] — [confidence: high/medium]
### Out of Scope
- [path/area] — [why excluded]
### Contested
<!-- Only present if scope conflict between scouts -->
- [path/area] — [scout reasoning from each side]

## Prior Art
[From Pattern Scout report]
- **[Description]** — [file paths] — [relevance to current task]

<!-- If Pattern Scout emitted `### Prior Knowledge Documents`, merge those
     entries in here with a source-derived tag so consumers can distinguish
     code prior art from written prior knowledge. Tag by source directory:
       docs/handoffs/ → (handoff doc)
       docs/postmortems/ → (postmortem)
       docs/retros/, docs/retrospectives/ → (retro)
       docs/decisions/, docs/adr/ → (ADR)
       docs/incidents/ → (incident)
       repo-root HANDOFF.md / POSTMORTEM.md / DECISIONS.md → (handoff doc) / (postmortem) / (decision record)
     Preserve the quoted passage sub-bullet from the scout report. -->
<!-- Only present if Pattern Scout returned Prior Knowledge Documents: -->
- **(handoff doc) [Doc title]** — `path/to/doc.md` (mtime YYYY-MM-DD) — [relevance]
  - [Quoted passage with line reference]

## Conflicts
<!-- Only present if contradictions detected between scouts -->
- **[Tension]** — Structure Scout: [claim + evidence]. Pattern Scout: [claim + evidence]. Confidence: [assessment].

## Open Questions
<!-- Aggregated from scouts and depth modules — what recon couldn't determine -->
- **[Question]** — [Why it matters] — Relevant to: [consumer list] — Resolvable by: [specific investigation or human input]

## Verification Ledger
<!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per skills/recon/verification-ledger.md. -->
<!-- Populated entries, if any: -->
- **L-NN** — [claim text] — method: `<method>`, evidence: `<anchor>`, disposition: `<confirmed | demoted | awaiting>`
```

## Overflow Handling

### Scout Report Overflow

**Detection:** Use line count as a proxy for token budget. If a scout report exceeds 80 lines (scoped) or 160 lines (full-repo), apply overflow handling. Depth modules: 120 lines (80 for readiness-checker). Lines are mechanically countable; token counts are not.

If a scout report exceeds its budget:

1. **Task-aware truncation:** Sections relevant to the current task retain full content (including reasoning prose needed for contradiction detection). Out-of-scope sections are reduced to headings + first-level bullets.
2. **If still over budget:** Request a scoped re-run from the scout with a narrower scope constraint.
   - Narrate: "Scout [name] exceeded token budget. Re-running with narrowed scope: [new scope]."
   - The re-run replaces the original report (not appended).
3. **Flag truncated sections** with `(truncated)` so consumers can request full detail.

### Depth Module Overflow

Same policy applies to depth module outputs (3,000 token budget, 2,000 for readiness-checker):
1. Task-aware truncation first
2. Scoped re-run if still over
3. Flag truncated sections

## Phase 4: Depth Module Dispatch

Resolve the effective modules list by evaluating these branches in order:

1. **Explicit empty list (`modules: []`)** — opt-out. Skip auto-inclusion
   and dispatch nothing.
2. **Otherwise, run Auto-Inclusion below** — this may prepend
   `diagnostic-context` to the caller's list (or produce a singleton list
   from an omitted `modules:`).
3. **Dispatch** the resulting list if non-empty. Dispatch **after** core
   synthesis completes — depth agents receive core findings as input context.

### Auto-Inclusion for Debugging Tasks

If the caller-provided `task:` parameter contains any of these case-insensitive
substrings, auto-include `diagnostic-context` as the FIRST entry in modules:

    bug, bugs, crash, crashes, crashing, broken, breaks, wrong, incorrect,
    regression, regressed, fail, failing, failure, error, investigate,
    diagnose, why does, why is, glitch, inverted behavior, appears inverted

**Matching semantics:** Case-insensitive. Single-word keywords match with
word-boundary semantics — `error` matches "fix this error" but NOT
"error-handling"; `fail` matches "request fails" but NOT "failover". This
reduces false positives on feature work that references error-adjacent
domains.

Multi-word keywords (`why does`, `why is`, etc.) match as contiguous token
sequences, also case-insensitive, with word-boundaries anchored at each end
of the phrase.

**Opt-out:** If caller passed `modules: []` (explicitly empty), suppress
auto-inclusion — the empty list signals "core only, no auto-detection."

**Idempotency:** Skip auto-inclusion if caller's modules list already contains
`diagnostic-context`.

**Narration:** When auto-including, narrate: "Debugging task detected (keyword:
'[match]'). Auto-including diagnostic-context. Pass modules: [] to opt out."

**Pipeline status:** Append under a new `## Auto-Included Modules` section in
`pipeline-status.md`: `diagnostic-context | reason=keyword: '[match]'`.

### Dispatch

When multiple modules are requested, dispatch them in parallel. Each depth agent receives the assembled core Investigation Brief via the `[CORE_BRIEF]` placeholder.

| Module | Agent | Profile | Claude Code dispatch | Template |
|---|---|---|---|---|
| `impact-analysis` | Impact Analyst | high | `Agent tool (subagent_type: Explore, model: opus)` | `./impact-analyst-prompt.md` |
| `consumer-registry` | Consumer Mapper | standard | `Agent tool (subagent_type: Explore, model: sonnet)` | `./consumer-mapper-prompt.md` |
| `friction-scan` | Friction Scanner | high | `Agent tool (subagent_type: Explore, model: opus)` | `./friction-scanner-prompt.md` |
| `subsystem-manifest` | Manifest Builder | standard | `Agent tool (subagent_type: Explore, model: sonnet)` | `./manifest-builder-prompt.md` |
| `diagnostic-context` | Diagnostic Gatherer | high | `Agent tool (subagent_type: Explore, model: opus)` | `./diagnostic-gatherer-prompt.md` |
| `execution-readiness` | Readiness Checker | standard | `Agent tool (subagent_type: Explore, model: sonnet)` | `./readiness-checker-prompt.md` |

### Placeholder Filling

- `[CORE_BRIEF]` — the assembled core Investigation Brief (all core sections)
- `[TASK]` — the original task description
- `[SCOPE]` — scope constraint (if provided)
- `[TARGET]` — for `consumer-registry` only: the migration target symbol/module. Extract from `context.target` if provided; fall back to the full `task:` string if absent. **Validation:** If `consumer-registry` is requested and neither `context.target` nor `task` is provided, reject with error: "consumer-registry requires a target — provide context.target or task."

### Output Handling

- Write each depth module output to scratch as individual files (e.g.,
  `<scratch>/impact-analysis.md`) as each module returns. Individual module
  files are safe under parallel dispatch — each file has exactly one
  writer.
- **Serialize the brief re-write.** Do NOT re-write
  `<scratch>/investigation-brief.md` incrementally after each module
  returns — Phase 4 Dispatch runs depth modules in parallel, and
  interleaved re-writes race. Instead:
    1. Wait until ALL dispatched depth modules have completed (or failed
       per the Depth Module Failure rules below).
    2. Append all completed depth-module sections to the in-memory brief
       after the core sections, separated by `---`, in a deterministic
       order: the order modules appear in the resolved effective modules
       list (see Phase 4 opening — the list produced by branches 1/2/3,
       including any auto-inclusion prepend).
    3. Perform exactly one re-write of `<scratch>/investigation-brief.md`
       with the fully-assembled brief (core + all depth sections) AFTER
       ALL depth modules complete. Per-module writes are forbidden.
- This serialized-write rule satisfies INV-11 without requiring
  cross-writer coordination. If Phase 4 is skipped (no depth modules
  requested), the Phase 3 write from Ledger Assembly step 6 stands as
  the final on-disk brief — no Phase 4 re-write occurs.
- Narrate after each module's individual completion: "Depth module [name]
  complete. Returning Investigation Brief." The brief re-write itself is
  internal; no separate narration required.

### Depth Module Failure

On failure (timeout, error, or agent did not return useful output):
- Deliver the core brief — it is always complete before depth modules start
- Flag the failed module in the brief:
  ```
  ## [Module Name]
  *Agent did not complete — request this module again or investigate manually.*
  ```
- Narrate: "Depth module [name] failed: [timeout / error]. Core brief delivered without this module."

## Phase 5: Cartographer Feedback

After the Investigation Brief is assembled (core + any depth modules):

### Falsification Grep (pre-recorder)

Before the cartographer recorder dispatch, grep the following scopes
(canonicalized from #211 doc-mining — see
`skills/recon/pattern-scout-prompt.md`) for lines containing
`Recon claim falsified:`:

- `docs/handoffs/`
- `docs/postmortems/`
- `docs/retros/`, `docs/retrospectives/`
- `docs/decisions/`, `docs/adr/`
- `docs/incidents/`
- Repo root: `HANDOFF.md`, `POSTMORTEM.md`, `DECISIONS.md`

For each hit:

1. Strip any leading markdown list prefix (`- `, `* `, `+ `), blockquote
   marker (`> `), or leading whitespace from the matched line.
2. Pass the stripped sentence payload to the cartographer recorder
   (dispatched in the step below) as a new landmine:

       "Recon previously claimed X; later falsified. Do not re-assert
       without fresh evidence."

   The inline claim text carried in each falsification sentence is the
   load-bearing evidence — no round-trip verification to originating
   briefs (AMB-5).

3. If grep finds zero hits, skip silently — emit no landmine dispatch
   for this step (INV-10 negative case).

4. If a hit is malformed (missing run-id, garbled format), pass the raw
   stripped line to the cartographer recorder with a best-effort note.
   Do not abort.

**Handoff-doc falsification sentence convention.** The grep target
format is documented in `## Verification Ledger Convention` below.
Consumer skills (e.g., `/build`, `/debugging`, `/design`) adopt the
convention opportunistically in separate tickets.

After the Falsification Grep step above, the rest of Phase 5 proceeds as
documented: check for new information (step 1), dispatch cartographer
recorder if needed (step 2). Falsification-grep landmines and new-info
updates are both passed to the SAME recorder dispatch if one occurs — do
not dispatch the recorder twice.

1. **Check for new information:** Compare scout findings against cartographer context provided in Phase 1.
2. **If scouts discovered new information not in the map:** Dispatch cartographer recorder (standard profile; Claude Code uses `model: sonnet`):
   ```
   Task tool (general-purpose, model: sonnet):
     description: "Cartographer recording for recon findings"
   ```
   Use [`cartographer/recorder-prompt.md`](cartographer/recorder-prompt.md), the persistent-map recorder template. Note: this is `Task tool`, not `Agent tool (Explore)` — the recorder needs write access to the memory directory. Pass scout findings as input following the recorder's expected format.
   - Include auto-update resolutions from cartographer conflict adjudication
   - New module files, conventions, or landmines flow into cartographer storage
   - **Narrate auto-updates:** "Auto-updating persistent map: [description]. Review with `/recon` persistent-map mode." Auto-updates must be visible — silent persistent changes affect all future sessions.
3. **If nothing new:** Skip recorder dispatch.

**Key constraint:** `/recon` is read-only on the codebase. Cartographer writes go to the memory directory, not the repo.
