---
name: recon
description: "Standalone codebase investigation. Produces a layered Investigation Brief with core findings (structure, patterns, scope, prior art) plus optional depth modules. Dispatches parallel scouts, synthesizes findings, and feeds cartographer. Use before a specific task requiring codebase understanding — task-scoped to the surface that task touches (for first-time whole-repo onboarding with cross-repo topology, use project-init, which bootstraps the cartographer data recon consults)."
---

# Recon

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- Trust framework: see [skills/getting-started/trust-hierarchy.md](../getting-started/trust-hierarchy.md). -->

Structured, parallel codebase investigation with a layered output model. Produces a core Investigation Brief that all consumers share, plus optional depth modules for consumer-specific needs.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Models:**
- Core scouts: Sonnet (via Explore agents)
- Judgment depth agents (impact-analysis, friction-scan, diagnostic-context): Opus
- Mechanical depth agents (consumer-registry, subsystem-manifest, execution-readiness): Sonnet
- Orchestrator: runs on whatever model the session uses

**Announce at start:** "Running recon [with task: X / full repo scan] [scope: Y / full repo]."

## Invocation API

```
/recon
  task: "Add REST endpoint for user profiles"       # optional — omit for full repo scan
  context: { decisions: [...], constraints: [...] }   # optional — structured prior decisions
  session_id: "design-20260404-abc123"                # optional — enables cross-invocation caching
  modules: ["impact-analysis", "execution-readiness"] # optional — depth modules to produce
  scope: "src/api/"                                   # optional — directory constraint
```

### Parameters

**`task`** (optional)
Free-text description of the task being investigated. Scouts focus exploration on task-relevant areas. Omit for a full repository scan.

**`context`** (optional)
Structured prior decisions from a parent skill (e.g., accumulated design choices from `/design`'s dimension loop). Passed to scouts alongside the task. Scouts consider these decisions during investigation — avoiding areas already decided, focusing on interfaces affected by prior choices.

- **Input budget:** 4,000 tokens default. Parent skills should compact decisions before passing — each decision as a key-value pair with one-sentence rationale plus affected interfaces.
- **Exceeding budget:** Orchestrator warns but does not reject. Caller proceeds at the cost of reduced scout context budget.
- **Total scout input:** task + context + cartographer should stay under 8,000 tokens for effective exploration.

Distinct from `task:` which describes *what* to investigate; `context:` describes *what's already been decided*.

**Recognized context keys:**
- `decisions` — list of prior design/implementation decisions
- `constraints` — list of constraints affecting investigation
- `target` — specific symbol/module for `consumer-registry` depth module (used by `/migrate`). Falls back to the `task:` string if absent.

**`session_id`** (optional)
Enables cross-invocation caching within a session. When provided, the Structure Scout report is cached and reused on subsequent invocations with the same session_id. Pattern Scout always runs fresh (its output varies with cascading context). Parent skills generate the session_id (e.g., `/design` uses its run timestamp). Without a session_id, no caching occurs.

**`modules`** (optional)
List of depth modules to produce after core synthesis. Valid values:

| Module | Agent | Model | Primary Consumer |
|---|---|---|---|
| `impact-analysis` | Impact Analyst | Opus | `/design`, `/build` |
| `consumer-registry` | Consumer Mapper | Sonnet | `/migrate` |
| `friction-scan` | Friction Scanner | Opus | `/prospector` |
| `subsystem-manifest` | Manifest Builder | Sonnet | `/audit` |
| `diagnostic-context` | Diagnostic Gatherer | Opus | `/debugging` |
| `execution-readiness` | Readiness Checker | Sonnet | `/build` |

Most invocations request 0-1 depth modules. Omit for core-only output (cheapest).

**Auto-inclusion:** Debugging-keyword tasks automatically add `diagnostic-context` (see Phase 4 Auto-Inclusion). Pass `modules: []` (explicit empty list) to suppress auto-inclusion — omitting `modules:` does not suppress it.

**`scope`** (optional)
Directory constraint. When provided, overrides scout scope suggestions entirely — scouts constrain exploration to the given path(s). Cheaper, faster.

### Behavior Matrix

| Configuration | Behavior |
|---|---|
| With task | Scouts focus on task-relevant areas |
| With context | Prior decisions passed to scouts alongside task |
| Without task | Full repo recon for audit/project-init cold starts |
| With scope | Explicit scope overrides scout suggestions |
| With modules | Depth agents dispatched after core synthesis |
| No modules | Core layer only — cheapest possible recon |
| With session_id | Structure Scout cached, Pattern Scout always fresh |

### Cost Profile

| Configuration | Agents | Models | Relative Cost |
|---|---|---|---|
| Core only | 2 | 2x Sonnet | Low |
| Core + 1 mechanical module | 3 | 3x Sonnet | Low |
| Core + 1 judgment module | 3 | 2x Sonnet + 1x Opus | Medium |
| Core + 2 modules (mixed) | 4 | 2-3x Sonnet + 1-2x Opus | Medium-High |
| Full repo, no task | 2 | 2x Sonnet | Low (but slower) |

## Communication Requirements (Non-Negotiable)

Recon narrates its progress at these points — **every one is mandatory**:

1. **Before dispatching scouts** — "Dispatching Structure Scout and Pattern Scout [with cartographer context / cold start]."
2. **After scout completion, before synthesis** — "Scouts complete. Synthesizing core brief. [N conflicts detected.]"
3. **After depth module completion, before returning** — "Depth module [name] complete. Returning Investigation Brief."
4. **On overflow re-run** — "Scout [name] exceeded token budget. Re-running with narrowed scope: [new scope]."
5. **On cartographer conflict** — "Cartographer conflict detected: [brief description]. Flagged as [auto-updated / unresolved]."
6. **On depth module failure** — "Depth module [name] failed: [timeout / error]. Core brief delivered without this module."

### Direct vs. Sub-Skill Invocation

**When invoked directly** (user calls `/recon`): narration is output to the user in real time.

**When invoked as sub-skill** (called by `/design`, `/build`, etc.): narration lines are included at the top of the returned Investigation Brief under a `## Recon Progress` section. The parent skill can relay these to the user or discard them.

### Pipeline Status

At each narration point, write `pipeline-status.md` to the scratch directory with:

```markdown
# Pipeline Status
**Phase:** dispatching | synthesizing | depth-modules | complete
**Progress:** [free-text description]
**Timestamp:** [ISO-8601]

## Scouts
- Structure Scout: [pending | running | complete | failed | cached]
- Pattern Scout: [pending | running | complete | failed]

## Depth Modules
<!-- Only present if modules requested -->
- [module-name]: [pending | running | complete | failed]

## Cartographer
- Consult: [consulted | cold start | N/A]
- Record: [pending | dispatched | complete | skipped]
```

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

Dispatch both scouts in parallel (or just Pattern Scout if Structure Scout is cached):

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
       <!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per the convention in skills/recon/SKILL.md. -->

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
<!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per the convention in skills/recon/SKILL.md. -->
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

| Module | Agent | Dispatch | Template |
|---|---|---|---|
| `impact-analysis` | Impact Analyst | `Agent tool (subagent_type: Explore, model: opus)` | `./impact-analyst-prompt.md` |
| `consumer-registry` | Consumer Mapper | `Agent tool (subagent_type: Explore, model: sonnet)` | `./consumer-mapper-prompt.md` |
| `friction-scan` | Friction Scanner | `Agent tool (subagent_type: Explore, model: opus)` | `./friction-scanner-prompt.md` |
| `subsystem-manifest` | Manifest Builder | `Agent tool (subagent_type: Explore, model: sonnet)` | `./manifest-builder-prompt.md` |
| `diagnostic-context` | Diagnostic Gatherer | `Agent tool (subagent_type: Explore, model: opus)` | `./diagnostic-gatherer-prompt.md` |
| `execution-readiness` | Readiness Checker | `Agent tool (subagent_type: Explore, model: sonnet)` | `./readiness-checker-prompt.md` |

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
2. **If scouts discovered new information not in the map:** Dispatch cartographer recorder:
   ```
   Task tool (general-purpose, model: sonnet):
     description: "Cartographer recording for recon findings"
   ```
   Use the existing `crucible:cartographer-skill` skill's `recorder-prompt.md` template (at `skills/cartographer-skill/recorder-prompt.md`). Note: this is `Task tool`, not `Agent tool (Explore)` — the recorder needs write access to the memory directory. Pass scout findings as input following the recorder's expected format.
   - Include auto-update resolutions from cartographer conflict adjudication
   - New module files, conventions, or landmines flow into cartographer storage
   - **Narrate auto-updates:** "Auto-updating cartographer: [description]. Review with `/cartographer consult`." Auto-updates must be visible — silent persistent changes affect all future sessions.
3. **If nothing new:** Skip recorder dispatch.

**Key constraint:** `/recon` is read-only on the codebase. Cartographer writes go to the memory directory, not the repo.

## Output and Return

Return the Investigation Brief as the agent output (inline return to parent skill).

The brief follows the exact template from the design, including the metadata block:

```markdown
# Investigation Brief
**Brief version:** 1
**Task:** [task description or "Full repository scan"]
**Scope:** [constrained path or "Full repo"]
**Depth modules:** [list or "Core only"]
**Cartographer state:** [consulted / cold start / N/A]
**Commit:** [HEAD SHA at investigation time]

## Project Structure
...

## Existing Patterns
...

## Scope Boundaries
### In Scope
...
### Out of Scope
...
### Contested
...

## Prior Art
...

## Conflicts
...

## Open Questions
...

## Verification Ledger
<!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per the convention in skills/recon/SKILL.md. -->
...

---
<!-- Depth modules below, only present if requested -->

## Impact Analysis
...

## Consumer Registry
...

## Friction Scan
...

## Subsystem Manifest
...

## Diagnostic Context
...

## Execution Readiness
**Test command:** ...
**Lint command:** ...
**CI checks:** ...
**Manual verification:** ...
```

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

### For recon maintainers

- Ledger format and assembly: see Phase 3 `### Ledger Assembly`.
- Disposition semantics and Claim Equivalence: see Phase 3
  `### Causal Claim Verification` + `#### Claim Equivalence`.
- Phase 5 grep-to-landmine flow: see Phase 5 `### Falsification Grep`.
- Brief write location: `<scratch>/investigation-brief.md` (INV-6 /
  INV-11).

## Design Principles

- **Read-only** — `/recon` never modifies the codebase
- **Cartographer-aware** — consults first, feeds back after
- **Layered** — core is cheap and universal; depth is on-demand and consumer-specific
- **Evidence-grounded** — produces constraints and evidence, not opinions
- **Prior art is first-class** — finding existing patterns to follow is the single biggest quality lever
- **Assumptions are explicit** — annotated inline on relevant findings, not in a standalone block
- **Token-efficient** — structured markdown, no JSON boilerplate, Sonnet for mechanical work

## Guardrails / Red Flags

- Never modify the codebase
- Never dispatch depth agents before core synthesis completes
- Never skip narration between dispatches
- Never exceed context budgets without overflow handling
- Never auto-update cartographer without both-scout agreement + verifiable evidence
- Never return depth module output without the core brief
- Never let an unverified causal claim reach the brief's main sections — demote to Open Questions per the Causal Claim Verification step
- Never skip auto-inclusion of diagnostic-context on a debugging task unless caller explicitly passed `modules: []`

## Integration

**Dispatches:**
- `structure-scout-prompt.md` — Structure Scout (Sonnet, Explore)
- `pattern-scout-prompt.md` — Pattern Scout (Sonnet, Explore)
- `impact-analyst-prompt.md` — Impact Analyst (Opus)
- `consumer-mapper-prompt.md` — Consumer Mapper (Sonnet)
- `friction-scanner-prompt.md` — Friction Scanner (Opus)
- `manifest-builder-prompt.md` — Manifest Builder (Sonnet)
- `diagnostic-gatherer-prompt.md` — Diagnostic Gatherer (Opus)
- `readiness-checker-prompt.md` — Readiness Checker (Sonnet)

**Consults:** `crucible:cartographer-skill` (consult mode — direct file read of `map.md`)

**Records to:** `crucible:cartographer-skill` (recorder dispatch after investigation, using `skills/cartographer-skill/recorder-prompt.md`)

**Called by:** `/design` (Phase 2 context + impact-analysis), `/spec` (per-ticket investigation + impact-analysis), `/migrate` (Phase 0 + consumer-registry), `/audit` (Phase 1 code scoping + subsystem-manifest)

**Not called by (investigated, not a fit):** `/debugging` (specialized investigation pipeline), `/build` (inherits via /design), `/prospector` (organic exploration is different), `/project-init` (bootstraps cartographer, complementary purpose). See #147 for rationale.

**Pairs with:** `/assay` (sequential — recon produces evidence, assay evaluates options)
