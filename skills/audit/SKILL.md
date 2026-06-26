---
name: audit
description: "Adversarial review of code subsystems or non-code artifacts (design docs, plans, concepts) through parallel analytical lenses. Triggers on 'audit', 'review subsystem', 'audit this design', 'review this plan', 'audit concept', 'check the save system', 'examine the UI code', or any task requesting adversarial review of existing artifacts."
---

# Audit

Adversarial review of code subsystems or non-code artifacts. Dispatches parallel analysis agents across four lenses adapted to the artifact type, synthesizes findings, and offers to file them in the user's issue tracker.

**Announce at start:** "Running audit on [target name] (type: [artifact type])."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Purpose:** Review existing subsystems in a repo and report findings. Distinct from quality-gate (which fixes artifacts in a loop) -- audit is find-and-report only.

**Code path is SYSTEMIC-ONLY.** On the `code` artifact type, audit reports **systemic health** — recurring patterns, structural properties, and absences across the subsystem, with **no single reproduction**. A defect with one concrete reproduction (even across multiple files) is an **instance bug** and belongs to `/delve`, not audit; audit routes it there (via the opt-in `--bugs` sub-path) or surfaces it under an explicit out-of-scope stub when `/delve` is absent. Maintainability/complexity/hotspot depth delegates to `/prospector`. See **The Systemic-Only Rule** below — it governs every code-path lens. (The non-code paths — design / plan / concept — are unchanged.)

**Model:** Opus (orchestrator and analysis agents). Sonnet (scoping exploration). If the orchestrator session is not running Opus, warn: "Audit requires Opus-level reasoning for synthesis. Results may be degraded."

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

## Artifact Types

Audit supports 4 artifact types, each with tailored analytical lenses:

| Artifact Type | Lens 1 | Lens 2 | Lens 3 | Lens 4 |
|---|---|---|---|---|
| `code` (default) | Architecture | Consistency | Robustness (systemic) | Test-health |
| `design` | Technical Soundness | Integration Impact | Edge Cases | Scope Clarity |
| `plan` | Feasibility | Risk & Dependencies | Completeness | Assumptions |
| `concept` | Problem-Solution Fit | Feasibility & Cost | Stakeholder Alignment | Blind Assumptions |

The `code` lenses are **systemic only** (see The Systemic-Only Rule). Maintainability/complexity is **not** a lens — audit delegates it to `/prospector`. Instance bugs are **not** a lens — audit delegates them to `/delve` via the opt-in `--bugs` sub-path.

### Invocation

```
/audit save/load                                          # code (default) — systemic health
/audit save/load --bugs                                   # + instance-bug sweep via /delve
/audit save/load --drift intent=docs/plans/save-design.md # + divergence-from-intent section
/audit docs/plans/2026-04-01-auth-design.md               # auto-detects design
/audit docs/plans/2026-04-01-plan.md artifact_type: plan   # explicit type
/audit "We should build a CLI tool that..."               # auto-detects concept
```

**Parameters:**
- `target` (required) — subsystem name, file path, or freeform text
- `artifact_type` (optional) — `code | design | plan | concept`. Auto-detected if omitted.
- `--drift intent=<path>` (optional, **code path only**) — opt-in mode. Adds a Drift section comparing the subsystem to the explicit intent artifact at `<path>` (design / spec / ADR / contract) and reporting divergence only. Keys on the supplied artifact, **not** git history; never auto-discovers one. `--drift` without `intent=` is a **usage error**. Without `--drift` the Drift section is neither produced nor advertised. See **`--drift` Mode** below.
- `--bugs` (optional, **code path only**) — also run `/delve` over the subsystem and append instance bugs in a SEPARATE "Instance Bugs (via delve)" section using delve's own schema. Enables the suppress-and-cite cross-check. See **`--bugs` Sub-Path** below.

### Auto-Detection

Priority chain when `artifact_type` is not provided:

1. Directory or subsystem name → `code` (existing behavior)
2. File with code extension (`.py`, `.ts`, `.go`, etc.) → `code`
3. YAML frontmatter `source` field is authoritative when present and matches a known value: `source: "design"` or `source: "spec"` → `design`; `source: "plan"` → `plan`. **Conflict check:** if `source` is set but title text disagrees (e.g., `source: "design"` with title "implementation plan"), warn the user: "Frontmatter says [type] but title suggests [other-type]. Treating as [source value] — pass `artifact_type:` explicitly to override." For unknown `source` values (e.g., `"retrospective"`), do not infer — fall through to rule 6.
4. No frontmatter `source` field, but title contains "implementation plan" → `plan`
5. No file path (freeform text input) → `concept`
6. Ambiguous → ask user: "I detected a markdown document but can't determine its type. Is this a design doc, plan, or concept?"

**Limitation:** Frontmatter-based detection relies on Crucible's `source` field convention. Repos without this convention will hit the "ambiguous → ask user" fallback more often. The explicit `artifact_type` parameter is the reliable path for any repo.

## The Systemic-Only Rule (code path)

Every `code`-path lens — Architecture, Consistency, Robustness (systemic), Test-health, the Phase 2.5 Blind-spots agent, and the opt-in `--drift` prompt — is governed by this rule. It is written verbatim into each of those prompts (invariant I3) and is repeated here as the orchestrator-side guardrail:

> An audit finding must be SYSTEMIC: a pattern recurring across multiple sites, a structural property of the subsystem, or a divergence from documented intent — with **NO single reproduction**. A finding that has one concrete reproduction is an **instance bug** and out of scope, even when it spans multiple files (a cross-file single defect is delve's, not audit's); route it to `/delve`. The discriminator is **"is there one concrete reproduction?"**, not file count.

**What this removes from audit's code path:** the old instance `Correctness` and `Robustness` lenses are gone. Single-site correctness/robustness bugs are `/delve`'s. audit's kept `Robustness (systemic)` lens covers only subsystem-wide robustness **patterns / absences** (e.g. "no locking discipline across any mutation path", "no boundary validates input anywhere") — never a single-site robustness bug.

**Delegation contracts:**
- **Maintainability / complexity / hotspots → `/prospector`** (it owns git-churn metrics + redesign). Not an audit lens.
- **Instance bugs → `/delve`** (only when the user passes `--bugs`; see `--bugs` Sub-Path). When `/delve` is not installed, see the `/delve`-absent fallback.
- **Test authoring → out of scope** for audit (audit never authors or fixes tests); test **staleness → `test-coverage`**. The Test-health lens only diagnoses + prioritizes systemic coverage gaps; it is never diff-scoped.

### Code Finding Schema — mandatory `sites`

Every systemic code finding carries, in addition to the common fields, a mandatory enumeration of the sites the pattern spans:

```
sites: [{file, line}, {file, line}, ...]
```

`sites` is a first-class field of audit's core code-output schema. A representative line per site is acceptable (e.g. a function header, or — for a "validates nothing at any boundary" property — a site with no single firing line). **The `sites` requirement is conditioned on the finding's category (per the three-way Systemic-Only Rule):** a PATTERN finding (a recurrence across sites) enumerates **two or more** sites; a pure STRUCTURAL-PROPERTY finding (e.g. a god object, an in-memory-only design, a missing layer) may carry a **single** representative site or the `sites: [whole-subsystem]` marker when no discrete second site exists; a divergence-from-intent finding follows the rule for its own category. The everywhere-absence case already described stays as-is (an absence-property site with no single firing line). The `/delve`-absent fallback and the `--bugs` suppress-and-cite coverage check both rely on `sites`, so it is never omitted on a code finding; a `whole-subsystem` marker is treated exactly like an absence-property site — **never covered** by any single delve instance (so a finding carrying it never reaches FULL coverage and always falls to PARTIAL → report-whole). (Non-code findings use `section`, not `sites` — see Non-Code Finding Format.)

## `--drift` Mode (code path, opt-in)

Drift compares the subsystem against an **explicit intent artifact** and reports divergence from it. It exists alongside `/prospector` without colliding: **prospector keys on git history** ("how did it get this way", churn, vestigial structure); **Drift keys on a design artifact** ("does it still match what we said").

- Runs **only** under `audit --drift intent=<path>`. The `<path>` is an explicit design / spec / ADR / contract artifact.
- **`--drift` without `intent=` is a usage error** — report it and stop; never auto-discover an intent artifact (auto-discovery would reopen the prospector collision).
- Reports **divergence only**. It must never silently re-derive friction from scratch — that is prospector's job.
- Without `--drift`, the Drift section is **neither produced nor advertised** (no dead-by-default section).
- **Drift carries the Systemic-Only Rule (I8):** a single-reproduction intent-divergence (one site bypassing a documented contract, with a concrete reproduction) is a delve instance — route it to `/delve`, do not report it as a Drift finding. A divergence-from-intent with no single repro is an audit Drift finding: a PATTERN divergence recurs across **two or more sites**, while a whole-subsystem STRUCTURAL divergence (e.g. a mandated layer/store the subsystem lacks entirely) may carry a **single** representative site or the `sites: [whole-subsystem]` marker — mirroring the Code Finding Schema's category-conditioned `sites` rule. Drift findings carry `sites`.

Operationally: when `--drift intent=<path>` is passed, the orchestrator reads the intent artifact, dispatches the Drift lens via `audit-drift-prompt.md` (which embeds the Systemic-Only Rule), and folds its findings into Phase 3 synthesis under a "Drift / Intent" theme.

## `--bugs` Sub-Path (code path, opt-in)

`--bugs` is the **sole data channel** by which audit cross-checks its systemic findings against concrete instance bugs. When passed, audit itself invokes the `/delve` **skill** over the subsystem and has delve's emitted instance records in hand.

**Invocation contract (pinned by construction):** audit invokes `/delve` with **`effort=high`** and **`scope` = the full audited subsystem** (the same subsystem audit reports on). audit MUST drive delve at `high`, not delve's unstated default (which could be `medium`). The `/audit` API has no effort param of its own; `--bugs` always pins high + full-subsystem, so the suppress-and-cite scope/effort precondition holds by construction.

**Output — a SEPARATE section.** delve's findings are appended under a clearly-headed **"Instance Bugs (via delve)"** section using delve's own eight-field schema (`{file, line, summary, failure_scenario, severity, verdict, scope, effort}`) — **never inline-merged** into audit's systemic findings.

### Suppress-and-cite gate

The "cite delve, don't re-report" rule fires **only** on the `--bugs` channel (audit has no other substrate to read delve records from; the same-session / out-of-band path is dropped — there is no specified store where delve persists records for audit to discover).

- **Suppression is per-finding, all-or-nothing at FULL coverage.** audit suppresses (cites-not-reports) a WHOLE systemic finding only when EVERY one of its enumerated `sites` is covered by a qualifying delve instance, citing those instances instead of re-reporting them.
- **Coverage match is NOT exact `{file,line}` equality.** audit's systemic lens picks a representative line per site while delve reports the line where the defect FIRES, so the same defect routinely carries a different line integer in the two records. A delve instance **covers** an audit site when they share the same `file` **AND** fall within the same enclosing symbol/function — or, when no enclosing symbol resolves, within a `±K`-line window. **`K = 10` lines, a single RUN-LEVEL config value** — fixed per run, not a per-call or per-implementer choice, so coverage verdicts stay deterministic within a run. **Absence-property sites are never covered.** A site with no resolvable line / no enclosing symbol (an everywhere-absence property, e.g. "no boundary validates input anywhere") is treated as **never covered** by any delve instance — a single-firing-line instance bug cannot cover an everywhere-absence — so a finding carrying such a site can never reach FULL coverage and always falls to PARTIAL → report-whole.
- **PARTIAL coverage → report the WHOLE finding.** When some-but-not-all sites are covered, audit reports the WHOLE systemic finding with a **"not cross-checked / partially covered"** note and cites delve for the covered sites within that finding. It NEVER emits a residual finding over only the uncovered sites.
- **Without `--bugs`:** audit has no instance set to read — it reports systemic patterns normally and notes **"instances not cross-checked (run audit --bugs to cross-check)."**

**Scope/effort guard (forward-looking, defense-in-depth — NOT done-gating).** Suppression requires delve's recorded `scope` to cover the audited sites AND delve's recorded `effort` tier to be **at or above high** (anything below high is always insufficient). On the only current channel (`--bugs`), this precondition is satisfied **vacuously by construction** (it pins high + full-subsystem), so the "delve scope/effort insufficient → don't suppress" branch is **not reachable today** — it is a forward-looking guard for any future additional channel that might supply delve records at lower effort or narrower scope, kept so an incomplete instance set can never mask a real systemic finding. It is distinct from the PARTIAL-coverage branch above, which IS reachable on the `--bugs` path.

### `/delve`-absent fallback

The Systemic-Only Rule suppresses re-reporting a single-reproduction finding **only when `/delve` is installed** to receive the routing. When `/delve` is NOT installed, audit MUST still surface single-reproduction findings — it does not silently drop them. Such findings are emitted under an explicit **"Out-of-scope instance bugs (install /delve to triage)"** stub section, assembled (Phase 3) from the per-lens **"Out-of-scope instance bugs (noted for /delve)"** sections each code lens records when it notices a single-reproduction defect in passing. Absent delve, a finding would otherwise be neither reported (Systemic-Only Rule) nor routed (no `/delve`) — a silent drop of a real instance bug, the exact recall hole this redesign closes. The stub keeps the finding visible until delve is installed; audit never both suppresses a finding AND lacks a routing target. (audit core ships before delve per the milestone dependency graph, so the fallback is load-bearing, not hypothetical.)

### Non-Code Lens Configurations

#### `design` — Design Documents

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Technical Soundness | "Are the technical decisions well-reasoned?" | Trade-off analysis quality, constraint identification, decision-evidence alignment, alternative exploration depth | Integration concerns (Integration Impact lens), boundary conditions (Edge Cases lens), scope questions (Scope Clarity lens) |
| Integration Impact | "How does this design interact with existing systems?" | Breaking changes identified, migration path, dependency awareness, blast radius assessment | Decision quality (Technical Soundness lens), boundary conditions (Edge Cases lens), scope questions (Scope Clarity lens) |
| Edge Cases | "What happens at the boundaries?" | Failure modes addressed, boundary conditions, concurrent usage, data edge cases, degraded-mode behavior | Decision quality (Technical Soundness lens), integration concerns (Integration Impact lens), scope questions (Scope Clarity lens) |
| Scope Clarity | "Is the scope well-defined and appropriate?" | Non-goals stated, scope-to-problem fit, YAGNI compliance, acceptance criteria testability | Decision quality (Technical Soundness lens), integration concerns (Integration Impact lens), boundary conditions (Edge Cases lens) |

#### `plan` — Strategic Plans, Implementation Plans, PRDs

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Feasibility | "Can this actually be executed as described?" | Resource requirements vs availability, timeline realism, skill/capability assumptions, tooling prerequisites | Risk identification (Risk & Dependencies lens), missing sections (Completeness lens), environmental assumptions (Assumptions lens). **Sequencing-risk-of-resource-exhaustion belongs to Risk & Dependencies** — Feasibility owns "can the resource constraint be satisfied at all"; Risk owns "what happens if it is satisfied unevenly or in the wrong order." |
| Risk & Dependencies | "What could derail execution?" | External dependency risks, sequencing risks, single points of failure, rollback provisions, blast radius of partial failure | Execution feasibility (Feasibility lens), missing sections (Completeness lens), environmental assumptions (Assumptions lens). **Whether a resource constraint can be met at all belongs to Feasibility** — Risk owns the consequences of uneven or mis-sequenced satisfaction, not the bare can-it-be-met question. |
| Completeness | "What's missing from this plan?" | Phases covered, milestones defined, success criteria measurable, testing strategy present, communication plan | Execution feasibility (Feasibility lens), risk identification (Risk & Dependencies lens), environmental assumptions (Assumptions lens) |
| Assumptions | "What's being taken for granted?" | Environmental assumptions, team capacity assumptions, technical assumptions, timeline assumptions, stakeholder alignment assumptions | Execution feasibility (Feasibility lens), risk identification (Risk & Dependencies lens), missing sections (Completeness lens) |

#### `concept` — Product Concepts, Proposals, Early-Stage Ideas

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Problem-Solution Fit | "Does this concept solve a real problem?" | Problem definition clarity, target audience identified, value proposition specificity, differentiation from existing solutions | Build feasibility (Feasibility & Cost lens), stakeholder concerns (Stakeholder Alignment lens), hidden assumptions (Blind Assumptions lens) |
| Feasibility & Cost | "Is this achievable and worth the investment?" | Build vs buy analysis, resource requirements, timeline expectations, opportunity cost, maintenance burden | Problem-solution fit (Problem-Solution Fit lens), stakeholder concerns (Stakeholder Alignment lens), hidden assumptions (Blind Assumptions lens) |
| Stakeholder Alignment | "Who needs to agree and will they?" | Decision-makers identified, conflicting incentives surfaced, adoption path realistic, organizational readiness | Problem-solution fit (Problem-Solution Fit lens), build feasibility (Feasibility & Cost lens), hidden assumptions (Blind Assumptions lens) |
| Blind Assumptions | "What is this concept taking for granted?" | Market assumptions, user behavior assumptions, technical assumptions, competitive landscape assumptions, sustainability assumptions | Problem-solution fit (Problem-Solution Fit lens), build feasibility (Feasibility & Cost lens), stakeholder concerns (Stakeholder Alignment lens) |

### Non-Code Finding Format

Non-code findings use the same severity levels (Fatal/Significant/Minor) but replace code-specific fields:

| Field | Code | Non-Code |
|---|---|---|
| Location | `file` + `line_range` | `section` (nearest markdown heading, e.g., `## Key Decisions > DEC-3`) |
| Lens-specific | `failure_pattern`, `impact`, `convention_violated`, `coverage_gap`, `intent_reference` | `concern` |
| Evidence | Code quotes | Document text quotes |

For artifacts without markdown headings, `section` uses a brief quoted phrase from the opening of the relevant paragraph.

The non-code field names `convention_violated` / `impact` intentionally overlap the code lenses' fields but are path-disjoint — the non-code and code paths never run together for a single artifact, so there is no ambiguity.

### Non-Code Blind-Spots Categories

When auditing non-code artifacts, the blind-spots agent hunts for document-level gaps:

- Internal contradictions (artifact says X in one section, Y in another)
- Unstated assumptions (decisions depending on undocumented conditions)
- Missing stakeholder perspectives (who would disagree with this?)
- Scope boundary gaps (what's just outside scope that could cause problems?)
- Silent dependencies (external factors assumed to remain true)
- Logical leaps (conclusions not supported by the preceding argument)

## Dispatch

On the opt-in `--bugs` path, audit invokes the **`/delve` skill** — not `delve-engine` directly — at `effort=high` over the full audited subsystem; `/delve` is the file that dispatches the engine. audit therefore carries a **separate skill marker** (`dispatch: delve`), **not** the engine marker `dispatch: delve-engine`, and is **out of scope** for the I2 engine-marker allowlist grep (whose anchored `^dispatch: delve-engine` set is exactly `{delve, temper}`). The `/delve` skill it invokes itself fans out through the harness-adapter mechanism (with the sequential fallback applying inside delve's engine fan-out where no parallel-subagent primitive exists), so audit issues a single skill call rather than driving the fan-out itself. When `/delve` is not installed, the `/delve`-absent fallback above keeps single-reproduction findings visible rather than dropping them.

dispatch: delve

## Why This Exists

Per-task quality gates (red-team, inquisitor) review artifacts produced during development. But the bugs that accumulate in stable code -- the ones nobody's looked at critically in months -- live in subsystems that passed their original review but have drifted, accrued inconsistencies, or developed subtle failure modes. The audit skill performs a focused adversarial review of any existing subsystem on demand.

## Distinction from Related Skills

| Skill | Reviews | When | Fixes? | Scope |
|-------|---------|------|--------|-------|
| red-team | A single artifact just produced | During creation | Yes (loop) | One doc/plan/impl |
| inquisitor | A complete implementation diff | During build phase 4 | Yes (automated fix cycle) | Changes only (diffs) |
| delve | **Instance bugs** — one concrete defect with a reproduction (even across files) | On demand | `--fix` (working tree) | A diff or a path |
| temper | The merge **gate** verdict | On a PR / diff | Yes (fix-verification loop) | A diff |
| **audit** | **Systemic** code health (patterns / structural properties / absences, no single repro) + non-code artifacts | On demand | No (reports only) | Existing subsystem or document |

audit and delve split on **instance vs systemic**: a finding with one concrete reproduction is delve's (route via `--bugs`); a no-single-repro pattern across the subsystem is audit's. The discriminator is "is there one concrete reproduction?", not file count.

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user AND touch `scratch/<run-id>/heartbeat.md` (overwrite with the current timestamp).** This is NOT optional -- the user cannot see agent activity without your narration, and the heartbeat file is what protects an in-flight audit from being deleted by a concurrent invocation's stale-cleanup pass (see Scratch Directory).

Every status update must include:
1. **Current phase** -- Which phase you're in
2. **What just completed** -- What the last agent reported
3. **What's being dispatched next** -- What you're about to do and why
4. **Lens status** -- Which lenses have reported vs. still in flight, finding counts so far

**After compaction:** Re-read the scratch directory and current state before continuing. See the Compaction Recovery section (orchestrator-level recovery) below.

**Examples of GOOD narration:**
> "Phase 2: Architecture and Robustness (systemic) lenses complete (2 findings, 1 finding). Test-health still in flight. Consistency Agent A returned -- flagged 6 files, dispatching Agent B."

> "Phase 2 complete. All 4 lenses reported: 14 total findings. Moving to Phase 3 synthesis."

> "Phase 2 (design audit): Technical Soundness and Integration Impact complete (3 findings, 1 finding). Edge Cases and Scope Clarity still in flight."

## Pipeline Status

Write a status file to `~/.claude/projects/<hash>/memory/pipeline-status.md` at every narration point. This file is overwritten (not appended) and provides ambient awareness for the user in a second terminal.

**Read-then-Write on the first write of a run.** The Write tool refuses to overwrite a pre-existing file that has not been Read in the current session, so a `pipeline-status.md` left behind by a prior skill run makes the *first* status write fail with "File has not been read yet." On the FIRST status write of an audit run, Read the existing `pipeline-status.md` first (its contents belong to another run — ignore them) and then Write. Subsequent writes within the same run need no re-Read — except after a compaction, which resets the session's read-tracking, so the first write post-compaction must Read first (the Compaction Recovery / Pipeline Status step already does this).

### Write Triggers

Write the status file at every point where the Communication Requirement mandates narration: before dispatch, after completion, phase transitions, health changes, escalations, and after compaction recovery. At each of these write points, also touch `scratch/<run-id>/heartbeat.md` (overwrite with current timestamp) so the stale-cleanup heuristic can distinguish in-flight audits from abandoned ones during long dispatch gaps.

### Status File Format

The status file uses this structure (overwritten in full each time):

```
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write — persisted across compaction>
**Skill:** audit
**Phase:** <current phase, e.g. "2 — Analysis">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from Started>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

### Skill-Specific Body

Append after the shared header:

```
## Lenses (code audit)
- Architecture: DONE (2 findings)
- Consistency: IN PROGRESS
- Robustness (systemic): DONE (1 finding)
- Test-health: PENDING
- Blind-spots: PENDING
- Drift / Intent: PENDING (only under --drift)

## Lenses (design audit — example)
- Technical Soundness: DONE (3 findings)
- Integration Impact: DONE (1 finding)
- Edge Cases: IN PROGRESS
- Scope Clarity: PENDING
- Blind-spots: PENDING
```

Use the lens names matching the current artifact type.

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): Phase 1->2, 2->2.5, 2.5->3, 3->4
- **YELLOW:** lens agent running longer than 10 minutes, blind-spots agent finds significant gap
- **RED:** multiple lens agents fail, user gate timeout

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence (e.g., "Architecture lens running >10 minutes. May be processing a large subsystem — check if scope needs narrowing.").

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Phase 2 [3/4 lenses] Robustness complete (2 findings) | GREEN | 22m` (denominator is the dispatched Phase-2 lens count: 4 by default, 5 under `--drift`)
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery (Pipeline Status)

After compaction, before re-writing the status file:
1. Read the existing `pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from internal state files
3. Write the updated status file
4. Output inline status to CLI

## Design Decisions

1. **Find and report only** -- no fixing. Audit surfaces issues; user decides what to act on.
2. **Cross-reference existing open issues** -- avoid filing duplicates, using whatever tools are available in the environment.
3. **Issue filing format is user's choice** -- offer individual issues per finding OR one umbrella issue with checklist. Let user pick.
4. **Tracker-agnostic** -- the skill stores which tracker and project the user uses, not how to use it. The agent uses whatever tools are available in the environment (MCP servers, CLIs, APIs) to interact with the tracker. If the agent can't figure out how to file, it asks the user. If the user mentions a different tracker or project during an invocation, update the stored preference.

## Preferences Storage

Stored in `~/.claude/projects/<project-hash>/memory/audit/preferences.md`:

```markdown
## Issue Tracker
- Tracker: github
- Project: owner/repo
```

First audit run: ask the user which tracker and project. Persist for future runs. Update if user indicates a change.

## Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/audit/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at the start of Phase 1 (e.g., `2026-03-15T14-30-00`). This same identifier is used for all scratch files and session logs throughout the run.

All relative paths in this document (e.g., `scratch/<run-id>/manifest.md`) are relative to `~/.claude/projects/<project-hash>/memory/audit/`.

**Stale cleanup is best-effort.** Both the start-of-run stale-cleanup here and the Phase 4 end-of-run cleanup delete directories under `~/.claude/projects/`. In environments where a safety hook blocks shell access to `.claude/` paths, those deletes fail; treat a blocked delete as a no-op (do not retry or escalate). A blocked GC simply defers reaping — scratch directories accumulate harmlessly until a run executes in a context where the delete is permitted. Never let a failed cleanup abort or degrade an audit.

**Stale cleanup:** At the start of each audit run, delete scratch directories whose **`heartbeat.md` mtime** (or, if `heartbeat.md` is absent, the most-recent file mtime inside the directory) is older than 1 hour. The orchestrator writes `scratch/<run-id>/heartbeat.md` at every narration point (see Communication Requirement and Pipeline Status Write Triggers), so an active audit always has a fresh heartbeat even during the long Phase 2 dispatch → first lens completion gap when no other scratch files are being written. Do not delete directories whose heartbeat is within the 1-hour window (they belong to concurrent or long-running sessions).

**User-gate exceptions to stale cleanup.** User gates can idle for hours between the orchestrator's last narration and the user's response, during which no heartbeat is refreshed. Two exceptions protect these directories:
1. **Pending gate:** Never delete a scratch directory containing `gate-pending.md` unless its heartbeat is older than 24 hours (a catastrophic-abandonment cap distinct from the 1-hour active-work threshold).
2. **Post-approval idle:** Never delete a scratch directory containing `gate-approved.md` UNLESS it also contains a terminal marker (`report.md`). A `gate-approved.md` without `report.md` indicates an in-flight run whose orchestrator may be paused between dispatches.

## Session Tracking

- **Metrics:** Log agent dispatches, completion times, finding counts to `/tmp/crucible-audit-metrics-<run-id>.log`
- **Decision journal:** Log scoping decisions, chunking rationale, dedup merges to `/tmp/crucible-audit-decisions-<run-id>.log`

The `<run-id>` is the same timestamp used for the scratch directory.

## Compaction Recovery (Orchestrator)

After context compaction, the orchestrator must first determine whether this is a code or non-code audit:

### Step 1: Detect Audit Type

Read `scratch/<run-id>/artifact-type.md`. If present and not `code`, follow non-code recovery. If absent, follow code recovery (existing behavior). **Marker-absent semantics:** because Phase 1 Non-Code Path writes this marker as its FIRST action (before validation, before any other work), absence is unambiguous — it means either a code audit OR a crash before type detection completed (which implies no Phase 1 work occurred). Both cases are safely handled by defaulting to code recovery.

### Code Recovery (artifact_type: code)

1. Read `scratch/<run-id>/` to determine current state:
   - `manifest.md` exists → Phase 1 scoping is complete (whether produced by recon's subsystem-manifest or the fallback scoping agent -- both write the same format)
   - `gate-approved.md` exists → user confirmed scope, Phase 2 can proceed
   - `<lens>-partition.md` files → those lenses' Tier 2 source partitions are recorded
   - `<lens>-findings.md` files → those lenses have reported
   - `consistency-a-findings.md` without `consistency-b-findings.md` → Agent B still needed
   - `blindspots-findings.md` exists → Phase 2.5 is complete
   - `report.md` exists → Phase 3 synthesis is complete, proceed to Phase 4
2. Re-read relevant files from disk based on current phase
3. Output current status to user before continuing
4. Continue with the appropriate phase

**Phase-specific recovery (code):**
- **Phase 1:** If `manifest.md` exists but `gate-approved.md` does not, re-present the manifest to the user for confirmation.
- **Phase 2:** Check which lenses have findings files. Dispatch any remaining lenses.
- **Phase 2.5:** If all four systemic lens findings files (plus `drift-findings.md` when `--drift` was passed) exist but `blindspots-findings.md` does not, rebuild the coverage map from partition records and findings files (see Coverage Map Construction), then dispatch the blind-spots agent. If `blindspots-findings.md` exists but `blindspots-followup-findings.md` does not, re-read `blindspots-findings.md` for a "Files Needing Deeper Inspection" section. If present and the audit is under the ~20 agent cap, dispatch the follow-up (writing to `blindspots-followup-findings.md`); otherwise mark for the standard "Areas not fully covered" disclosure in the Phase 3 report. If both `blindspots-findings.md` and `blindspots-followup-findings.md` exist, or if `blindspots-findings.md` exists and has no "Files Needing Deeper Inspection" section, Phase 2.5 is complete.
- **Phase 3:** If compaction occurs during synthesis, re-read all findings files (including blindspots) and re-run synthesis. This is safe — synthesis is idempotent.
- **Phase 4:** If `report.md` exists, re-read it and continue with cross-referencing/filing.

### Non-Code Recovery (artifact_type: design | plan | concept)

(The artifact type was already recovered by Step 1 above via `artifact-type.md`.)

1. **Phase 1 recovery:** If `artifact-type.md` exists but `gate-approved.md` does not, re-present the scope summary to the user for confirmation. The over-ceiling case needs no special recovery handling: the warning is informational and the truncated bundle (Supporting Context and Operating Environment trimmed to empty) is deterministically rebuilt by the existing "dispatch-context.md absent → re-run step 4.5" rule below, so re-presenting the scope summary is the only step required. **Supporting-context recovery:** If `gate-approved.md` is absent and `supporting-context.md` is absent, re-run step 4 (supporting-context gathering). If `supporting-context.md` exists, reuse it as-is rather than re-running step 4 (avoids non-deterministic re-resolution). If `dispatch-context.md` is absent, re-run step 4.5 (shared dispatch-bundle assembly: artifact + supporting context + operating environment) before proceeding to Phase 2 — this applies to all non-code types including `design`, because step 4.5 always writes the bundle file (with the operating-environment section stubbed for skipped design artifacts), so absence unambiguously means lost-to-compaction.
2. **Phase 2 recovery:** Look for `<lens-name-kebab>-findings.md` files matching the type's lens names (e.g., `technical-soundness-findings.md` for design). Dispatch any lenses that don't have findings files.
3. **Phase 2.5 recovery:** If all 4 lens findings exist but `noncode-blindspots-findings.md` does not, build the lens summary and dispatch the non-code blind-spots agent. If `noncode-blindspots-findings.md` exists, Phase 2.5 is complete.
4. **Phase 3/4 recovery:** Same as code path — re-read findings, re-run synthesis if needed, continue with reporting.

## Phase 1: Scoping

### Code Path (artifact_type: code)

1. User names a subsystem ("save/load", "UI", "networking")
2. Consult cartographer data if it exists for subsystem boundaries
3. **Dispatch recon** with subsystem-manifest module:

   ```
   /recon
     task: "Subsystem manifest for audit: <subsystem name>"
     scope: "<subsystem-path or cartographer-identified boundary>"
     modules: ["subsystem-manifest"]
   ```

   Parse the subsystem manifest from recon's brief to produce the file list + role descriptions for the USER GATE. Write to `scratch/<run-id>/manifest.md` in the same format the scoping agent produces (file paths + brief role descriptions). This format compatibility ensures all downstream code (Phase 2, compaction recovery) works without modification.

   **On recon failure:** "Recon failed: [reason]. Falling back to scoping exploration agent." Dispatch the fallback scoping agent: `Agent tool (subagent_type: Explore, model: sonnet)` using `audit-scoping-prompt.md` (existing behavior).

4. If the subsystem cannot be cleanly scoped (files share no common dependency chain, naming convention, or functional cohesion), report the scoping difficulty to the user and ask for clarification or a file list.
5. **Output:** A manifest of files belonging to the subsystem (paths + brief role descriptions). Write to `scratch/<run-id>/manifest.md`.

**USER GATE:** Before presenting the manifest, write `scratch/<run-id>/gate-pending.md` (contents: timestamp + "awaiting user scope approval") so stale-cleanup protects this directory across an idle gate (see Scratch Directory). Present the manifest to the user. Do not proceed to Phase 2 until the user confirms the scope is correct. User may add/remove files or refine the boundary. When the user approves, delete `gate-pending.md` and write `scratch/<run-id>/gate-approved.md` (contents: timestamp + user confirmation) as a compaction recovery marker.

If the user removes all files or the manifest is empty: abort cleanly with "No files in scope -- audit cancelled."

### Non-Code Path (artifact_type: design | plan | concept)

No scoping agent needed — the artifact IS the scope. The orchestrator:

1. **Detect or confirm type:** Apply auto-detection (see Auto-Detection above) or use explicit `artifact_type`.
2. **Write type marker (FIRST action):** Immediately write `scratch/<run-id>/artifact-type.md` containing the detected type, *before* artifact validation or any other Phase 1 work. This file is the compaction recovery marker for non-code audits. Writing it first eliminates the ambiguity window where compaction between type detection and marker write would force recovery into the wrong branch. After this write, marker absence reliably indicates either (a) a code audit, or (b) a crash before type detection (which means no Phase 1 work happened) — both safely handled by the code-recovery default.
3. **Validate artifact:** Read the file or accept freeform text input. If file does not exist, abort.
4. **Gather supporting context:** Parse the artifact for references:
   - Markdown links (`[text](path)`)
   - File paths (`path/to/file.ext`)
   - Issue references (`#NNN`)
   - Explicit "see also" references
   - **Project-memory references** — bare filenames or relative paths that match Crucible-style memory conventions (see Project-Memory Reference Resolution below)
   - **Skill name references** — names of skills the artifact mentions (e.g., "the `project-standards` skill", "`feedback_use_component_library`")

   For each referenced file that exists locally: read and include as supporting context. For issue references: fetch title and body via `gh issue view`. **Soft cap: 800 lines total.** This bounds the Supporting Context section of the shared dispatch-context bundle (step 4.5), which the lens agents read as a file alongside the artifact (~300-500 lines) and operating environment (≤500 lines). These are per-section soft caps and can sum above the bundle's hard ceiling; step 4.5 enforces the actual 1500-line ceiling on the assembled bundle via a deterministic truncation order, with Supporting Context truncated first. If exceeded: prioritize files referenced in decision-critical sections (Key Decisions, Risk Areas) over background references. Truncate with note: "[truncated — 800-line context cap reached]". If no references found: proceed with artifact-only context.

   **Project-Memory Reference Resolution.** A reference that does not resolve repo-relative is tried against the project-memory directory at `~/.claude/projects/<project-hash>/memory/`:
   - If the reference is a path (e.g., `memory/cartographer/conventions.md`), try `<project-memory-root>/cartographer/conventions.md`.
   - If the reference is a bare filename matching `<prefix>_<rest>.md` where prefix is one of `user`, `feedback`, `project`, `reference` (Crucible memory convention) OR matches a date-prefixed retrospective pattern `YYYY-MM-DD-*.md`, search for it under `<project-memory-root>/` (root), `<project-memory-root>/cartographer/`, and `<project-memory-root>/forge/retrospectives/`. **Search order is fixed:** project-memory root → cartographer/ → forge/retrospectives/. **First match wins; only one file is resolved per bare reference** (no merging, no duplicate inclusion across locations). Stale-marker annotation (below) still applies to the winning file if applicable.
   - If the reference is a skill name (matches an entry in the available-skills list), include the skill's one-line description as supporting context. Skill body is opt-in via explicit user instruction; do NOT auto-include skill SKILL.md (token cost).
   - **Path-collision resolution:** prefer repo-relative match over project-memory match if both exist.
   - **No project hash known:** when the orchestrator cannot determine the project hash (e.g., running outside Claude Code, or `~/.claude/projects/<hash>/` is not discoverable from cwd), skip the project-memory fallback AND surface a one-line note at the Phase 1 user gate: "Project-memory references not resolved — project hash undetermined; supporting context may be incomplete." This parallels the stale-memory annotation pattern and gives the user visibility into the degraded context so dev/CI/worktree variance is not silent.
   - **Stale-memory annotation:** when a resolved memory file has a "stale" marker in frontmatter (some Crucible setups inject one for memories older than 30 days, or based on mtime), the orchestrator includes the file content with a leading note: "**Note: this memory was marked stale (mtime: <date>); verify current relevance before relying on its claims.**" Do not silently include stale memories without annotation.

   **4a. Persist resolved supporting context (mandatory continuation of step 4):** At the end of this step, write the bundled supporting context (resolved file list, fetched issue bodies, project-memory inclusions, truncation notes, stale-memory annotations) to `scratch/<run-id>/supporting-context.md`. This is the compaction recovery marker for step 4 — it captures the prioritization and resolution decisions so they don't silently re-run with different results.
4.5. **Gather operating-environment context (plan and concept artifacts: mandatory; design artifacts: predicate-gated).** For `plan` and `concept` artifact types, the Feasibility and Risk & Dependencies lenses cannot meaningfully assess an artifact in the abstract — they need to know what the executor actually has. **For `design` artifacts, the skip decision is determined by a concrete predicate (not orchestrator judgment):**

   **Design skip predicate.** Skip the gather (write stub) ONLY if **both** conditions hold:
   1. The artifact has no `## Execution` section AND no `## Implementation` section (case-insensitive heading match), AND
   2. The artifact names no skill in its body or frontmatter. Skill-detection clause (any match disqualifies the skip):
      - `/skill-name` invocations (slash form), OR
      - Backtick-quoted skill names matching the available-skills list, OR
      - `skill:` frontmatter field, OR
      - **Case-insensitive natural-language patterns** against the available-skills list: `"the <name> skill"`, `"via <name>"`, `"using <name> skill"`, `"<name> skill"` (bare name + " skill"). Example: a reference like "executed by the audit skill" fires the predicate (because `audit` is in the available-skills list and the pattern `"the audit skill"` matches), so the gather runs and operating-environment is collected.

   Otherwise gather normally — the design has executor-touching content that needs grounded constraints.

   When the predicate skips the gather, the bundle below is still written in full; only its **Operating Environment section** becomes the stub `## Operating Environment\n(skipped — design artifact, predicate-determined no-op)`. Because the bundle file is always written for every non-code type, absence of the file unambiguously means "lost to compaction" during recovery. The stub is a *determined* no-op (driven by the predicate), not an arbitrary skip.

   Inspect:
   - The project's `CLAUDE.md` for toolchain / build / framework constraints
   - Any cartographer module map (`memory/cartographer/conventions.md` or similar) for architectural constraints. If the module map is flagged stale (mtime > 30 days or explicit stale marker), include the staleness note rather than the stale claims.
   - The skill(s) the artifact names as its execution vehicle (e.g., `/audit`, `/build`, `/debugging`) — pull their hard caps, budgets, and red flags from the named skill's SKILL.md
   - The tracker conventions from `preferences.md` if present

   Bundle these into a `## Operating Environment` block. **Soft cap: 500 lines.** If empty (no relevant constraints found), record `## Operating Environment\n(none detected)` — the lens prompts treat an empty block as a no-op.

   **Assemble the shared dispatch-context bundle (closing action of this step).** Write `scratch/<run-id>/dispatch-context.md` as the SINGLE shared context every Phase 2/2.5 non-code agent reads, with exactly these three sections in order:
   - `## Artifact (<type>)` — the full artifact content (the audited file's text, or, for a freeform `concept`, the input text). This is the only persisted copy of the artifact, so freeform input is not lost to compaction.
   - `## Supporting Context` — the bundle written to `supporting-context.md` in step 4 (reuse it verbatim; if step 4 found no references, write `(none)`).
   - `## Operating Environment` — the block assembled above (real, `(none detected)`, or the design-skip stub).

   Lens dispatches reference this one file by path instead of each dispatch copy-pasting the artifact + ≤800 supporting + ≤500 environment lines (~N× the bundle across N lenses). The win is *where the bytes live*: the large artifact/supporting/operating-environment content is lifted out of **each** per-lens dispatch — the per-lens dispatch file now carries the lens template plus a one-line pointer to the bundle, not N copies of the content — so the bundle is read once and referenced N times instead of inlined N times. (The Task-tool pointer prompt stays within dispatch-convention's ≤120-token sizing; the dispatch file itself remains the full lens template, which the bundle pointer keeps from ballooning, not from being tiny.) Separately, the **shared bundle** is governed by its own explicit **1500-line hard ceiling** — applied as a distinct backstop, not merely by the per-section soft caps (which sum to ~1800 — the truncatable overhead alone is ≤1300, and a large never-truncated artifact pushes the bundle over — and so cannot enforce the ceiling on their own).

   **Bundle hard ceiling and truncation order.** The `## Artifact` section is the irreducible floor — **NEVER truncated**, because it is the thing under review. If the assembled bundle would exceed **1500 lines total**, truncate the supporting/operating-environment overhead around the artifact deterministically: the `## Supporting Context` section first (lowest priority; it already carries the step-4 "[truncated …]" logic), then the `## Operating Environment` section if the bundle is still over. Record any truncation applied here in the affected section with a note: "[truncated — 1500-line bundle ceiling reached]". This bounds the supporting + operating-environment **overhead** added around the artifact, not the artifact's own volume. The degenerate case where the artifact alone exceeds 1500 lines (an unusually large single-pass non-code artifact, since the non-code path has no chunking escape) is just this truncation order taken to its limit: dropping `## Supporting Context` then `## Operating Environment` trims **both to empty**, leaving the artifact plus the truncation notes. This is mechanical and deterministic — re-running step 4.5 on the same artifact reproduces the identical truncated bundle — so there is no special state to record and nothing for recovery to get wrong. Surface it as an informational note at the Phase-1 user gate (step 5): the artifact alone exceeds the ceiling, so Supporting Context and Operating Environment were dropped, and the user MAY narrow scope. Narrowing is just the normal scope-confirmation flow (re-scope the artifact, re-run from step 4) — not a special degenerate branch, and it needs no special marker.

   Anti-rationalization (plan/concept only): skipping this step because "the constraints are obvious" produces generic feasibility findings ("sampling is generally hard") instead of concrete ones grounded in the executor's actual caps. For plan/concept, always run. (For `design`, the skip path is governed by the predicate above, not orchestrator judgment.)
5. **Present user gate:** Before presenting, write `scratch/<run-id>/gate-pending.md` (contents: timestamp + "awaiting user scope approval") so stale-cleanup protects this directory across an idle gate (see Scratch Directory). Then prompt: "Auditing [artifact name] as a [type]. Supporting context: [list of referenced docs, if any]. Operating environment: [one-line summary of bundled constraints, if any]. [if the artifact alone exceeds the 1500-line ceiling: note that Supporting Context and Operating Environment were dropped to fit; you may narrow scope.] Proceed?"
6. **Write gate marker:** On approval, delete `gate-pending.md` and write `scratch/<run-id>/gate-approved.md` (same as code path).

## Phase 2: Analysis

### Non-Code Dispatch (artifact_type: design | plan | concept)

Dispatch: `Task tool (general-purpose, model: opus)` per lens, in parallel, using `audit-noncode-lens-prompt.md` with lens-specific instruction injection.

For each of the 4 lenses matching the artifact type (see Artifact Types table):
1. Fill the template placeholders: `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, `{{LENS_EXCLUSIONS}}`, `{{ARTIFACT_TYPE}}`, and `{{DISPATCH_CONTEXT_PATH}}` (the absolute path to `scratch/<run-id>/dispatch-context.md`). The artifact content, supporting context, and operating environment are **not** inlined per-lens — they live once in the shared dispatch-context bundle (assembled in Phase 1 step 4.5) and each lens reads them from that file. This keeps the artifact/context bytes out of every lens dispatch (read once from the bundle, not copy-pasted once per lens). For `design` artifacts where Phase 1 skipped the operating-environment gather, the bundle's Operating Environment section is the stub `(skipped — design artifact, predicate-determined no-op)` — the prompt template handles this no-op case.
2. Dispatch via disk-mediated dispatch
3. Write findings to `scratch/<run-id>/<lens-name-kebab>-findings.md` (e.g., `technical-soundness-findings.md`)

**Key differences from code path:**
- Full artifact content available to each lens via the shared dispatch-context bundle (no Tier 1/Tier 2 tiering — non-code artifacts are small)
- All single-agent (no dual-agent Consistency pattern)
- No partition records (all lenses see the full artifact)
- Findings use `section` instead of `file` + `line_range`, and `concern` instead of lens-specific code fields

After all 4 lenses complete, proceed to Phase 2.5 (non-code blind-spots).

### Code Dispatch (artifact_type: code)

Dispatch: `Task tool (general-purpose, model: opus)` per lens, in parallel (matching inquisitor pattern). Fallback if parallel dispatch fails: dispatch sequentially via `Task tool (general-purpose, model: opus)`, with a one-time note to user: "Parallel dispatch unavailable -- running analysis lenses sequentially."

<!-- CANONICAL: shared/calibration-weighted-dispatch.md -->
**Calibration-weighted dispatch (advisory).** Before the lens fan-out, derive the file list from the audited subsystem's manifest files, resolve `scripts/brier_advisory.py` by absolute path from the plugin root, and run `python3 <script> advise audit <file list…>`. If it prints a DispatchAdvice block, add it verbatim to the Tier 1 overview every lens agent receives, as scrutiny hints (NOT as findings, NOT scored). Best-effort: on empty output or any error, dispatch normally. See `shared/calibration-weighted-dispatch.md`.

**Write-on-complete:** As each agent completes, immediately write its findings to `scratch/<run-id>/<lens>-findings.md`. Do not wait for Phase 3. For the Consistency lens, use distinct filenames: `consistency-a-findings.md` for Agent A's triage output, `consistency-b-findings.md` for Agent B's confirmed findings.

**Write partition records:** Before dispatching each lens, write the list of files sent as **full source** (not overflow summaries) to `scratch/<run-id>/<lens>-partition.md` (one file path per line). For Consistency, write only `consistency-b-partition.md` (Agent A receives the Tier 1 overview, not a Tier 2 source partition, so no partition record is needed for Agent A). These records are used by Phase 2.5 to build the coverage map and must survive compaction. Files sent as 2-3 line overflow summaries are NOT included in partition records -- those files count as never-examined for blind-spots purposes.

**Note on Consistency Agent A triage:** Agent A reads the Tier 1 overview and triages all manifest files, flagging some for Agent B. Files Agent A did not flag appear as "never-examined" in the coverage map. This is intentional -- overview-level triage (reading a 1-line role description) is categorically different from source-level examination. The blind-spots agent examining those files for security, performance, and concurrency issues is valuable regardless of Consistency triage.

### Context Management

**Tier 1 -- Overview:** The orchestrator builds a condensed summary of the subsystem: file manifest with role descriptions, key public interfaces/contracts, dependency graph. **Target: 500 lines. Flexible up to 800 lines for subsystems with complex API surfaces.** If the subsystem exceeds what can be summarized in 800 lines, chunk the subsystem (see Chunking below).

**Tier 2 -- Deep dive:** The orchestrator partitions source files across agents by relevance to their lens. **Hard cap: 1500 lines of total prompt content per agent** (Tier 1 overview + Tier 2 source + prompt template). If a lens requires more files than fit, the orchestrator generates brief summaries of overflow files (2-3 lines per file: path, responsibility, key interfaces) and includes those instead of full source. If an agent's findings reference a summarized file, the orchestrator may dispatch a **follow-up agent** for that lens with the flagged files at full source.

### Chunking (Large Subsystems)

If the subsystem is too large to summarize within the 800-line Tier 1 cap:

- Split by dependency subgraph -- files that call each other stay together. Prefer natural boundaries (directories, modules, namespaces).
- **Soft cap: 4 chunks maximum.** If more than 4 chunks would be needed, advise the user to narrow the subsystem scope instead.
- Present the chunking plan at the Phase 1 user gate. Show the full agent-budget breakdown so the user approves the **worst-case** total, not a partial slice:
  - **Scoping:** 1 agent (mandatory — recon or fallback scoping agent, run in Phase 1)
  - **Per chunk:** 6 agents (mandatory — Architecture, Consistency-A, Consistency-B, Robustness-systemic, Test-health, Blind-spots), **plus 1 Drift agent per chunk when `--drift` is passed** (the Drift lens is dispatched per chunk alongside the others)
  - **Cross-chunk blind-spots:** 1 agent (mandatory if N>1, else 0)
  - **Optional blind-spots follow-ups:** up to N agents (one per chunk, dispatched only when a chunk's blind-spots agent lists "Files Needing Deeper Inspection" AND budget allows)
  - **Formula:** `1 (scoping) + N × 6 (per-chunk) + (N if --drift else 0) (per-chunk Drift) + (1 if N>1 else 0) (cross-chunk) + up to N (optional follow-ups)`
  - **Worst-case for N=4 (no `--drift`):** `1 + 24 + 0 + 1 + 4 = 30 agents` — over the 20-agent hard cap; re-gate per the agent-budget rule (narrow scope, reduce chunks, or raise the cap). With `--drift` the per-chunk Drift term adds N (e.g. `+4` at N=4).
  - Message: "This subsystem is large. I'll audit it in N chunks. Worst-case agent budget: [scoping 1] + [N×6 per-chunk] + [N per-chunk Drift if --drift] + [cross-chunk 1 if N>1] + [up to N optional follow-ups] = [worst-case total]. Mandatory floor (no follow-ups): [1 + N×6 + (N if --drift) + cross-chunk]. Chunk descriptions: [list]. Approve worst-case total?"
- **20-agent budget is a HARD CAP, tracked across all phases.** The orchestrator maintains a running count of dispatched agents. Before any dispatch that would cross the cap (chunked analysis lenses, blind-spots, follow-ups, cross-chunk), if the projected total exceeds the user-approved number, re-gate: present the projected total and the remaining work, and ask the user whether to (a) raise the cap, (b) skip optional dispatches (follow-ups first, then cross-chunk blind-spots), or (c) abort.
- Each chunk gets its own set of analysis agents.
- Synthesis (Phase 3) merges findings across all chunks.
- Cross-chunk concerns: the Tier 1 overview for each chunk includes a "cross-chunk interface" section describing how this chunk interacts with others. All lenses receive this section and should consider cross-chunk issues within their domain.

### The 4 Lenses

Each lens is dispatched as a parallel agent using its prompt template. All four code lenses are **systemic only** and carry the Systemic-Only Rule (I3); a finding with one concrete reproduction is `/delve`'s, not a lens finding.

All lenses output structured findings with these common fields: `{severity, file, line_range, evidence, description}`, plus the mandatory **`sites: [{file,line}, ...]`** enumeration on every code finding (see Code Finding Schema). Individual lenses add lens-specific fields (e.g., Robustness-systemic adds `failure_pattern`, Architecture adds `impact`, Consistency adds `convention_violated`, Test-health adds `coverage_gap` and `priority_rationale`, and — under `--drift` — Drift adds `intent_reference`). These canonical snake_case identifiers correspond to the bold human labels the prompt output templates emit: `failure_pattern` ↔ "Failure pattern:", `impact` ↔ "Impact:", `convention_violated` ↔ "Convention violated:", `coverage_gap` ↔ "Coverage gap:", `priority_rationale` ↔ "Priority rationale:", and `intent_reference` ↔ "Intent reference:". The orchestrator maps between identifier and label when preserving these fields. The orchestrator's Phase 3 deduplication uses the common fields for matching; lens-specific fields are preserved in the final report.

**Maintainability / complexity is not a lens** — when hotspot / complexity / churn depth is wanted, audit calls `/prospector` (delegation, not duplication). **Instance correctness / single-site robustness bugs are not lenses** — they route to `/delve` via `--bugs`.

#### Architecture

**Prompt:** `audit-architecture-prompt.md`
**Question:** "Is this well-structured?"
**Looks for:** Coupling issues, abstraction leaks, missing contracts, dependency direction violations, god objects, circular dependencies.
**Gets:** Tier 1 overview + public API surfaces.
**Dispatch:** Single agent.

#### Consistency

**Prompt:** `audit-consistency-prompt.md`
**Question:** "Does this code follow its own patterns?"
**Looks for:** Pattern violations, naming drift, convention breaks, inconsistent error handling styles, mixed paradigms — across the subsystem (systemic drift, not a single deviating line that is itself a bug).
**Dispatch:** Two sequential agents (orchestrator dispatches Agent A, reads results, then dispatches a separate Agent B).

- **Agent A:** Receives the Tier 1 overview (which includes the file manifest with role descriptions) + conventions.md from cartographer if available. The overview IS the summary -- do not add additional file-level summaries. Returns: list of files flagged for suspected inconsistencies with rationale. Subject to the 1500-line hard cap.
- **Agent B:** Receives full source for Agent A's flagged files only. Subject to the same 1500-line hard cap. If Agent A flags more files than fit, the orchestrator applies the same overflow-summary mechanism (summarize overflow files, include full source for highest-priority flags, dispatch follow-up if needed). Returns: confirmed findings with evidence.
- **Zero-flag case:** If Agent A flags zero files, the orchestrator skips Agent B dispatch and writes empty marker files: `consistency-b-findings.md` and `consistency-b-partition.md` each containing only `(no files flagged for deep review)`. Downstream consumers — compaction recovery, Phase 3 reading list, Coverage Map construction — treat these markers as "Phase 2 complete for Consistency" and proceed without error.
- **Timing:** Agent A dispatches in parallel with the other three lenses. Agent B dispatches after Agent A completes. The orchestrator proceeds to Phase 3 once all lenses (including Consistency Agent B) have reported. The other three lenses may finish earlier -- this is expected and acceptable.

#### Robustness (systemic)

**Prompt:** `audit-robustness-prompt.md`
**Question:** "Where is the subsystem's robustness discipline systemically absent?"
**Looks for:** Subsystem-wide robustness **patterns / absences** only — e.g. "no locking discipline across any mutation path", "no boundary validates input anywhere", "errors swallowed at every I/O site". The finding is the absence-across-sites, enumerated in `sites`.
**Does NOT look for:** a single-site missing error handler, one unclosed resource, one unvalidated input — those are single-reproduction instance bugs and route to `/delve`.
**Gets:** Files at system boundaries, I/O, serialization, mutation paths.
**Dispatch:** Single agent.

#### Test-health

**Prompt:** `audit-testhealth-prompt.md`
**Question:** "Where is the subsystem systemically under-tested?"
**Looks for:** Codebase-wide systemic coverage gaps — categories of behavior, modules, or seams with no tests across the subsystem; structural testability problems. **Diagnose + prioritize only.**
**Does NOT do:** author or fix tests (out of scope for audit); diff-scoped coverage checks; test **staleness** (route staleness to `test-coverage`).
**Gets:** Tier 1 overview + test file manifest + source-to-test mapping.
**Dispatch:** Single agent.

## Phase 2.5: Blind Spots

### Non-Code Blind-Spots (artifact_type: design | plan | concept)

Dispatch: `Task tool (general-purpose, model: opus)` using `audit-noncode-blindspots-prompt.md`. Runs AFTER all Phase 2 non-code lenses have reported, BEFORE Phase 3 synthesis.

**No coverage map needed** — all lenses see the full artifact. Instead, the orchestrator builds a **lens summary** with this format:

```
## Lens Summary
- **[Lens Name]** — [Core Question]. Findings: N (Fatal: N, Significant: N, Minor: N). Focus areas: [brief list].
[repeat for each lens]
```

The blind-spots agent reads the full artifact from the shared dispatch-context bundle's `## Artifact` section (`scratch/<run-id>/dispatch-context.md`, the same file the lenses read — no separate artifact copy) and receives the lens summary, then hunts for document-level gaps (see Non-Code Blind-Spots Categories above). Write findings to `scratch/<run-id>/noncode-blindspots-findings.md`.

**No follow-up dispatches** for non-code (the artifact is fully visible to the blind-spots agent — there are no "never-examined files").

### Code Blind-Spots (artifact_type: code)

Dispatch: `Task tool (general-purpose, model: opus)` using `audit-blindspots-prompt.md`. Runs AFTER all Phase 2 lenses have reported (including Consistency Agent B), BEFORE Phase 3 synthesis.

**Purpose:** The four lenses share structural blind spots -- issues that fall between lenses, emerge from combinations of findings, or belong to categories no single lens covers (security, performance, concurrency, silent failures). A fresh agent hunts specifically in those gaps.

**Write-on-complete:** Write findings to `scratch/<run-id>/blindspots-findings.md`.

### Coverage Map (not raw findings)

The blind-spots agent does NOT receive raw findings from the other lenses. Instead, the orchestrator builds a **coverage map** -- a condensed summary of where the other lenses looked, without the evidence details that cause anchoring. This preserves independent judgment while directing attention to uncovered areas.

**Coverage map format** (orchestrator generates this from the lens findings files and Tier 2 partition records):

```
## Coverage Map

### Files Examined by Lens (included in Tier 2 source)
- path/to/file.ext: Architecture (1 finding), Robustness-systemic (1 finding)
- path/to/other.ext: Consistency (1 finding), Test-health (0 findings)
- path/to/examined-clean.ext: Architecture (0 findings)

### Files Never Examined (in manifest but not in any Tier 2 source)
- path/to/genuinely-unseen.ext
- path/to/another-unseen.ext
```

**Target: 30-50 lines.** No finding summaries, no concern category descriptions (the agent already knows the four — or five under `--drift` — lenses' domains from its prompt). Just the file-to-lens mapping and the examined/never-examined distinction. This maximizes source code budget.

### Coverage Map Construction (Orchestrator)

To build the coverage map:
1. Read all partition records from disk: `architecture-partition.md`, `consistency-b-partition.md`, `robustness-partition.md`, `testhealth-partition.md`, and `drift-partition.md` (only when `--drift` was passed -- the Drift lens runs in Phase 2, per chunk when chunked, and writes a Tier 2 source partition, so its examined files must join the examined set or they would be miscounted as never-examined). These list the files each lens received as full source (written during Phase 2). Union of all partition files = the **examined set**. **Zero-flag marker handling:** if a partition file contains only the marker `(no files flagged for deep review)` (written by the Consistency zero-flag case), treat it as contributing **zero files** to the examined set — do not include the marker string as a path. The Consistency lens then contributes only to coverage from Agent A's triage (which is not source-level examination); its Tier 2 examination contribution is zero, and files only flagged by no other lens correctly appear in the never-examined set.
2. Read the Phase 1 manifest. Any manifest file NOT in the examined set = **never examined**.
3. Read all findings files: architecture, consistency-b, robustness, testhealth, and drift (only when `--drift` was passed). Do NOT include consistency-a (triage only). Extract finding counts per lens per file.
4. Overlay finding counts onto the examined set. Files in the examined set with no findings get "(0 findings)" for the lenses that examined them.
5. List examined files with lens names and finding counts. List never-examined files separately.
6. If the map exceeds 50 lines, abbreviate by grouping never-examined files by directory instead of listing individually.

### Input

The blind-spots agent receives:
- Tier 1 overview (same as other lenses)
- Coverage map (see above, ~30-50 lines)
- Targeted source files. Subject to the same 1500-line hard cap as other lenses.

### Source File Selection

**Priority order (strict -- not a judgment call):**
1. **At least 60% of source file budget** goes to **never-examined** files (not in any lens's Tier 2 source partition). These are the genuine blind spots -- code no lens read.
2. **Remaining budget** goes to files flagged by multiple lenses (interaction points where cross-cutting concerns are likeliest).

If there are no never-examined files (every manifest file was in at least one Tier 2 partition), allocate the full budget to multi-lens interaction points.

**Narration:** Status update when dispatching ("Phase 2.5: All 4 lenses complete. Dispatching blind-spots agent to hunt cross-cutting concerns.") and when it completes ("Phase 2.5 complete. Blind-spots agent found N additional findings. Moving to Phase 3 synthesis.").

### Follow-Up Dispatches

If the blind-spots agent lists files in "Files Needing Deeper Inspection" AND the audit is under the ~20 agent budget, dispatch one follow-up blind-spots agent with those files at full source. The follow-up receives the same coverage map but new source files. Write follow-up findings to `scratch/<run-id>/blindspots-followup-findings.md`. Phase 3 synthesis reads this file if it exists.

If the audit is at or near the agent budget, skip the follow-up and include the "Files Needing Deeper Inspection" list in the Phase 3 report as "Areas not fully covered."

### Chunked Audits

For chunked subsystems, the blind-spots agent runs **once per chunk** (not once for all chunks), receiving that chunk's coverage map + cross-chunk interface section. This keeps each dispatch within the 1500-line hard cap.

**Cross-chunk blind spots:** After all per-chunk blind-spots agents complete, dispatch one additional **cross-chunk blind-spots agent** (using `audit-blindspots-prompt.md`, with the cross-chunk overview substituted for the per-chunk coverage map -- so it carries the same Systemic-Only Rule and the `### Out-of-scope instance bugs (noted for /delve)` channel Phase 3 step 6 collects). This agent receives a purpose-built cross-chunk overview (NOT all individual coverage maps stacked):
- A single merged view (~50-80 lines) listing only boundary files (files that appear in multiple chunks' interface sections) with their lens coverage across chunks
- Source files from those cross-chunk boundaries
- Subject to the same 1500-line hard cap

Per-chunk interior coverage is irrelevant to cross-chunk analysis -- keep it out. This agent targets issues that span chunk boundaries (e.g., one chunk deserializes input, another trusts it without validation). Write findings to `scratch/<run-id>/blindspots-crosschunk-findings.md`. Skip this dispatch if the subsystem is single-chunk.

**Cross-chunk boundary overview construction (orchestrator):**
1. Identify boundary files: files that appear in 2+ chunks' Tier 1 "cross-chunk interface" sections.
2. For each boundary file, collect lens coverage from all chunks' partition records + finding counts from all chunks' findings files.
3. Format as: `path/file.ext: Chunk A [Architecture (1), Robustness-systemic (0)], Chunk B [Consistency (2)]`
4. List only boundary files. Interior files are irrelevant to cross-chunk analysis.
5. If >80 lines, group by chunk boundary pair (e.g., "Chunk A <-> Chunk B boundary files").

After all blind-spots agents complete, findings from all chunks (including cross-chunk) flow into Phase 3 synthesis.

### Compounding Risk Analysis

The blind-spots agent does NOT analyze compounding risks from existing findings. That responsibility belongs to Phase 3 synthesis, which already reads all findings and deduplicates. Adding a synthesis step for compounding is natural and costs zero additional agents. See Phase 3 below.

## Phase 3: Synthesis

### Reading Findings

**Code audits:** Read `architecture-findings.md`, `consistency-b-findings.md`, `robustness-findings.md`, `testhealth-findings.md`, `blindspots-findings.md`, and if they exist: `blindspots-followup-findings.md`, `blindspots-crosschunk-findings.md`, `drift-findings.md` (only when `--drift` was passed). Do NOT read `consistency-a-findings.md` (triage data, not confirmed findings).

**Non-code audits:** Read `<lens-name-kebab>-findings.md` for each of the 4 type-specific lenses (e.g., `technical-soundness-findings.md`, `integration-impact-findings.md`, `edge-cases-findings.md`, `scope-clarity-findings.md` for design), plus `noncode-blindspots-findings.md`.

1. **Deduplicate:** When two findings reference the same location and describe the same underlying concern, merge into one finding noting both lenses. For code audits, match on overlapping `sites` (shared `file` + same enclosing symbol / `±K` window, `K=10` — the same coverage-match rule the suppress-and-cite gate uses; an absence-property site with no resolvable line/enclosing-symbol is never covered, exactly as in that gate). For non-code audits, match on identical `section` headings. Use common fields (severity, evidence, description) for similarity comparison. Preserve lens-specific fields from both. **Tie-breaking rule:** When in doubt, keep both findings as separate items but note they may be related. Err on the side of presenting more findings rather than silently merging.
2. **Compounding risks:** After dedup, scan pairs of findings from different lenses that touch the same file or related files. Flag as compounding ONLY when you can articulate the specific mechanism by which the two findings combine into a worse problem (e.g., "this systemic robustness absence means malformed input reaches every mutation path, where the consistency drift in error handling lets one path silently corrupt state"). File proximity alone is not compounding -- the findings must be causally related. Add a "Compounding" tag with the mechanism description to the grouped output.
3. **Severity-rank:** Fatal first, then Significant, then Minor.
4. **Group by theme** (e.g., "Error Handling," "State Management," "API Contracts"). When `--drift` ran, Drift findings group under a "Drift / Intent" theme.
5. **`--bugs` suppress-and-cite (code audits with `--bugs` only):** Before writing the report, apply the suppress-and-cite gate (see `--bugs` Sub-Path). For each systemic finding, compare its `sites` against the delve instance records: FULL coverage → suppress the finding and cite the covering delve instances; PARTIAL coverage → keep the WHOLE finding with a "not cross-checked / partially covered" note citing delve for covered sites. delve's instances are written verbatim into the report's separate **"Instance Bugs (via delve)"** section (delve's own schema), never merged into the systemic findings.
6. **Assemble the out-of-scope instance-bug stub (code audits):** Collect the `### Out-of-scope instance bugs (noted for /delve)` entries that each lens recorded in its output -- read the SAME set of findings files as the reading list above (architecture, consistency-b, robustness, testhealth, blindspots, and if they exist blindspots-followup, blindspots-crosschunk, and drift under `--drift`; never consistency-a) -- these are single-reproduction defects the lenses noticed in passing while hunting systemic patterns. Deduplicate by `file:line` + description. Then, depending on the delve channel: **with `--bugs`** delve already triaged the full subsystem, so fold these into the delve cross-check rather than double-reporting (a recorded bug already covered by a delve instance is dropped in favor of delve's record); any recorded instance bug NOT matched to a delve instance is appended to the **"Instance Bugs (via delve)"** section as an *audit-noted uncovered instance* (never dropped); **without `--bugs` but with `/delve` installed**, note that they route to `/delve` and offer `audit --bugs`; **when `/delve` is absent**, emit the deduped list under the **"Out-of-scope instance bugs (install /delve to triage)"** stub. A recorded instance bug is NEVER silently dropped -- this is the recall-hole closure the Systemic-Only Rule depends on.
7. **Write report** to `scratch/<run-id>/report.md`.

## Phase 4: Reporting

1. Present the ranked, grouped findings to user.

2. **Cross-reference existing issues:** Using whatever tools are available in the environment (MCP servers, CLIs, etc.), search for existing open issues using specific file paths and error descriptions from findings as search terms.
   - **Budget (code findings):** Cross-reference the top 10 findings by severity (Fatal first, then Significant). Check at most 2-3 search queries per finding — code findings carry `file`/`sites` that map to natural path and symbol search terms.
   - **Non-code findings (design / plan / concept) — scaled-down strategy:** non-code findings carry a `section` (a markdown heading), not a `file`/symbol, so there is nothing to grep by path. Do NOT run the per-finding code search above. Instead search by (a) the audited issue's labels when the artifact maps to a tracked issue, and (b) keywords from the document title — capped at **5 queries total for the whole run** (not per-finding). If neither anchor exists (no tracked issue, generic title), skip cross-referencing entirely and note "cross-referencing skipped — non-code findings have no symbol/path anchors." Cross-referencing here is best-effort; the absence of a match is never itself a finding.
   - If the tracker is slow or unresponsive after 3+ failed/timed-out queries, skip remaining cross-references.
   - Present at most 2-3 candidate matches per finding.
   - Flag likely duplicates with "Possible existing issue: [reference]" -- never silently drop a finding; let user decide.
   - If cross-referencing isn't possible (no tools available, tracker not configured), skip it and just present findings.

3. Ask user: **"File as individual issues, one umbrella issue with checklist, or skip filing?"**
   - If filing: use available environment tools to create issues with structured body (severity tag, file references, evidence snippet).

4. **Record to cartographer (code audits only):** After completion, dispatch cartographer recorder (Mode 1) with the Phase 1 manifest only. The manifest was deliberately scoped during exploration and is reliable structural data. Do NOT feed incidental observations from Phase 2 bug-hunting agents to cartographer -- those are unverified structural inferences. **Skip for non-code audits** — no subsystem manifest to record.

5. **Cleanup:** Delete `scratch/<run-id>/` after all applicable Phase 4 steps have resolved (filing decision made; cartographer step run-or-skipped per artifact type). Do not clean up prematurely -- the report on disk is needed for compaction recovery during Phase 4. **Cleanup is best-effort** (see Scratch Directory): where a safety hook blocks shell access to `.claude/` paths, the delete may fail — treat that as a no-op, not an error, and do not retry or escalate. The next run's stale-cleanup is the authoritative GC (itself best-effort under the same constraint); a lingering directory is harmless.

## Terminal Verdict Emit

<!-- CANONICAL: shared/ledger-append.md -->

At the end of the audit's report/output (Phase 4, after the ranked findings are presented and before scratch cleanup), emit ONE **Tier B STUB** JSONL line to the **central ledger** (`~/.claude/crucible/ledger/runs.jsonl`) via the `emit` CLI per the canonical protocol at `skills/shared/ledger-append.md` — resolve `scripts/ledger_append.py` by absolute path from the plugin root and run `python3 <script> emit - '<json>'`.

- The `emit` CLI owns the mechanics: graceful skip on `CRUCIBLE_CALIBRATION_DISABLED=1` (L-6), dedup by `(run_id, skill="audit")` (L-2), and auto-fill of `repo` + `schema_version`. If the script can't be resolved, warn to stderr and skip — never block.
- Populate ONLY meaningful values (`repo` is auto-filled by the `emit` CLI): `schema_version: 2`, `run_id` (UUIDv7 via `scripts/uuid7.py`), `skill: "audit"`, `tier: "B"`, `verdict` (audit is find-and-report; a completed report → `PASS`; an early abort/escalation routed to the user → `ESCALATED`), `timestamp` (ISO-8601 UTC), `gated_files` (the manifest files reviewed, repo-relative; for non-code artifacts the audited file path), `artifact_type` (`code` | `design` | `plan`; map `concept` → `other`).
- Set ALL calibration fields EXPLICITLY null per the "Tier-B null semantics" of `shared/ledger-append.md`: `severity_histogram`, `highest_finding`, `would_have_shipped_without_gate`, `findings_count`, `confidence`, `chunk_hash`, `rounds`, `predicted_falsifier` — all `null`. Also `gated_files_truncated: 0` and `comment: null`. Keep `backfilled: false`, `falsified: null`, `falsified_by: null`.

## Prompt Templates

### Code Audit Templates

- `audit-scoping-prompt.md` -- Phase 1 subsystem scoping dispatch (`Agent tool, subagent_type: Explore, model: sonnet`)

Analysis lens templates (all use `Task tool, general-purpose, model: opus`; all carry the Systemic-Only Rule and emit the `sites` field):
- `audit-architecture-prompt.md` -- Architecture lens dispatch
- `audit-consistency-prompt.md` -- Consistency lens dispatch (documents two-agent protocol)
- `audit-robustness-prompt.md` -- Robustness (systemic) lens dispatch — subsystem-wide patterns/absences only
- `audit-testhealth-prompt.md` -- Test-health lens dispatch — systemic coverage gaps, diagnose + prioritize only

Opt-in mode template (`Task tool, general-purpose, model: opus`):
- `audit-drift-prompt.md` -- Drift / Intent dispatch, used ONLY under `--drift intent=<path>` (carries the Systemic-Only Rule; consumes the explicit intent artifact)

Blind-spots template (`Task tool, general-purpose, model: opus`):
- `audit-blindspots-prompt.md` -- Phase 2.5 gap-hunting dispatch (receives coverage map; carries the Systemic-Only Rule)

> The instance `Correctness` lens and its `audit-correctness-prompt.md` template were **removed** in the systemic-only reshape — single-site correctness/robustness bugs route to `/delve` via `--bugs`.

### Non-Code Audit Templates

- `audit-noncode-lens-prompt.md` -- Parameterized lens dispatch for all non-code artifact types. Orchestrator fills `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, `{{LENS_EXCLUSIONS}}`, `{{ARTIFACT_TYPE}}`, and `{{DISPATCH_CONTEXT_PATH}}` (the artifact, supporting context, and operating environment are read by the agent from the shared bundle at that path, not inlined per dispatch).
- `audit-noncode-blindspots-prompt.md` -- Non-code blind-spots dispatch (receives lens summary; reads the artifact from the shared dispatch-context bundle, not coverage map)

Each analysis template includes:
- Dispatch metadata (for orchestrator reference): `Task tool (general-purpose, model: opus)`
- The lens definition and what to look for
- Placeholders for: Tier 1 overview, Tier 2 source partition
- Output format with common fields (`severity, file, line_range, evidence, description`) plus lens-specific fields
- Instruction: "Only flag issues you can point to specific code evidence for. No speculative findings."
- Context self-monitoring (report partial progress at 50%+ utilization)

## Guardrails

**Analysis agents must NOT:**
- Modify any code (audit is read-only)
- Flag issues without specific code evidence (no speculation)
- **Report a single-reproduction (instance) finding as a code-lens finding** — the Systemic-Only Rule routes it to `/delve` (or the `/delve`-absent stub). A code finding must be systemic: a multi-site pattern, a structural property, or an intent divergence, with no single reproduction.
- Overlap with another lens's findings (if borderline, the more specific lens owns it)
- Exceed 5 findings per lens without strong justification (focus on highest-impact issues). Exception: blind-spots lens cap is 8 findings due to its multi-category scope.

**The orchestrator must NOT:**
- Proceed to Phase 2 without user-confirmed scoping manifest
- File issues without explicit user approval
- Silently drop findings that match existing issues (always show, let user decide)
- **Silently drop a single-reproduction finding when `/delve` is absent** — surface it under the "Out-of-scope instance bugs (install /delve to triage)" stub.
- **Run Drift without `--drift intent=<path>`, auto-discover an intent artifact, or advertise a Drift section when `--drift` was not passed.**
- **Re-derive maintainability/complexity/hotspot friction inline** — delegate to `/prospector`. **Author or fix tests** — Test-health diagnoses + prioritizes only; staleness routes to `test-coverage`.
- Exceed 1500 lines of total prompt content in any agent dispatch — this cap governs inlined prompt content per dispatch, and for non-code the shared dispatch-context bundle is held to the same 1500-line ceiling via the step-4.5 truncation order (artifact never truncated; Supporting Context then Operating Environment trimmed if over)
- Feed Phase 2 structural inferences to cartographer (Phase 1 manifest only)
- Skip narration between agent dispatches (Communication Requirement)
- Dispatch more than ~20 agents without user awareness (chunking approval includes agent count)
- Offer or dispatch remediation actions in Phase 4. Audit is find-and-report only. If the user requests fixes after reviewing the report, instruct them to invoke `/build` or `/debugging` separately — do not propose "would you like me to fix this?" or dispatch fix agents from within the audit run.

## Red Flags

- Treating this as a fix loop (audit reports, it does not fix)
- **Reporting an instance bug (one concrete reproduction) as a systemic finding** — it is `/delve`'s, even across multiple files
- **Suppressing a single-reproduction finding when `/delve` is absent** instead of surfacing it under the out-of-scope stub
- **Re-implementing maintainability/complexity analysis** instead of delegating to `/prospector`; **authoring or fixing tests** instead of diagnosing systemic gaps
- **Running or advertising Drift without `--drift intent=<path>`**, or auto-discovering an intent artifact
- Hardcoding tracker-specific commands (use available environment tools)
- Losing agent results to context compaction (write to disk immediately)
- Skipping session metrics or decision journal
- Cleaning up scratch directory before Phase 4 is fully complete

## Integration

| Skill | How Used | When |
|-------|----------|------|
| `crucible:recon` | Subsystem-manifest module | Phase 1 Code Path (subsystem scoping via structured manifest). Fallback: dispatch scoping agent via `audit-scoping-prompt.md`. |
| `crucible:cartographer-skill` | Consult mode | Phase 1 (subsystem scoping and conventions) |
| `crucible:cartographer-skill` | Record mode | Phase 4 (Phase 1 manifest only) |
| `crucible:delve` | Instance-bug sweep | Code path, opt-in `--bugs`: invoked as a SKILL at `effort=high` over the full subsystem; feeds the suppress-and-cite gate. (audit reaches `delve-engine` only transitively through `/delve`; it carries the separate `dispatch: delve` skill marker — see the Dispatch section.) |
| `crucible:prospector` | Maintainability / complexity / hotspot depth | Code path, on request — audit delegates rather than re-deriving git-churn friction |
| `crucible:test-coverage` | Test **staleness** | Code path — Test-health routes staleness here (Test-health itself only diagnoses systemic coverage gaps) |

- **Dispatches:** Code audit templates (architecture, consistency [2 agents], robustness-systemic, test-health, blind-spots; drift when `--drift`) and non-code templates (noncode-lens [parameterized], noncode-blindspots). Scoping via recon (primary) or `audit-scoping-prompt.md` (fallback). Instance bugs delegated to the `/delve` skill on `--bugs`.
- **Pairs with:** `crucible:forge` -- audit findings could inform retrospective if they reveal systemic patterns
- **Called by:** Standalone only (user invokes directly). Not part of any pipeline.
- **Does NOT use:** `crucible:quality-gate` (audit is not a fix loop), `crucible:red-team` (designed for single artifacts), `crucible:assay` (audit is find-and-report, not decision evaluation)
