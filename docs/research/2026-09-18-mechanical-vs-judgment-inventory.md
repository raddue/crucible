# Spike #643 — How much of Crucible's skill logic can move from prose to deterministic scripts?

- **Date:** 2026-09-18
- **Branch:** `research/643-skill-scripting-spike`
- **Scope:** `skills/*/SKILL.md` (52 skills) + `skills/shared/*.md` (21 files) on this branch's survey snapshot. This document implements no conversions (issue non-goal).
- **Deliverable:** qualitative classification inventory (section → bucket → one-line reason), candidate priorities, seed follow-up tickets. Original shared-section and weighted-residency estimates are omitted because manual estimates are not reproducible from retained artifacts.
- **Snapshot:** corpus and qualitative candidate priorities describe the survey as of 2026-09-18. PR #644 later implemented parts of the first four recommendations; status appears in §7.

---

## 1. Corpus and method

| Measure | Value |
|---|---|
| SKILL.md files | 52 |
| shared/*.md files | 21 |
| Total corpus bytes | 1,938,609 |
| — of which SKILL.md | 1,585,010 |
| — of which shared/ | 353,599 |
| Lines beginning `## ` counted (including fenced examples) | 930 |
| `CANONICAL` marker/reference occurrences (skill → shared doc) | counted, §3.3 |

**Method.** Counted lines beginning `## ` across corpus, including fenced examples. Inventory names selected shared-doc sections (§3) and summarizes mechanical areas by skill (§4); it is not a row-per-heading classification of all 930 lines. Bucket assignments and candidate priorities are qualitative. Original shared-section size estimates were manual, overlapped, and cannot be reproduced from retained artifacts; removed here. §4 retains rough per-skill reading-scope size hints; they are not byte partitions or additive. This document makes no mechanical-byte share, token-residency, or turn-savings claim. Buckets:

- **Mechanical (scriptable)** — fixed right answer given inputs: format/grammar validation, path/artifact resolution, bundling/coverage accounting, quantized decision tables, aggregation math, ledger/marker/status writes, git-state checks.
- **Judgment (stays prose)** — right output depends on model reasoning over the artifact's substance: review findings, design tradeoffs, hypothesis formation, adversarial content, subjective quality assessment.
- **Hybrid** — mechanical core wrapped in judgment-driven dispatch/scoping (e.g. a mechanical scoring rule decides *whether* an agent round runs, but the round is judgment).

Each shared-doc inventory row identifies a section and a concrete mechanism or reason. Skill rows summarize the mechanical slots and judgment core by skill; they do not enumerate all `##` headings individually. Rows flagged `✓` were verified by reading the body; rows flagged `~` are inferred from the section's stated purpose in its heading plus cross-references, not read line-by-line. A `#` marker after a shared-doc row means the behavior is already mechanized (script/hook exists) and is not a new conversion candidate.

**Bucket-size caveat.** Classification is qualitative, not a byte-accurate partition; some headings mix mechanical and judgment content. Corpus bytes do not imply token residency, conversion value, or runtime cost.

---

## 2. Headline findings

1. **Shared conventions contain deterministic procedures**, alongside judgment and already-mechanized behavior. This is a qualitative finding, not a percentage or token estimate. `ledger-append.md` contained about 22.8KB of fenced Python source in the survey snapshot: `ledger_append.py` was reproduced verbatim, while the `uuid7.py` excerpt was abridged; PR #644 removed both live-code reference blocks.
2. **Canonical-reference fan-out is a candidate to measure, not a savings estimate.** The survey snapshot has 31 literal references to `shared/dispatch-convention.md`, plus `ledger-append.md` (10), `return-convention.md` (8), and `cairn-convention.md` (5). These counts are occurrences, not unique skills or observed runtime loads.
3. **Linked-doc load varies by skill.** This survey did not measure token residency per activation or separate mechanical from judgment tokens.
4. **A concrete drift failure is on record.** `scripts/second_pass_scorer.py`'s docstring describes five live-verified in-place inversions of one scoring rule that left phrase-pin checkers green. Its scorer/eval caught behavior those checkers missed; this demonstrates a failure mode, not its frequency across the corpus.
5. **Pipeline-status prose was duplicated at survey time**: `Pipeline Status` blocks exist in 6 skills (build, debugging, audit, siege, migrate, spec). PR #644 added `shared/pipeline-status-convention.md` and a build link; follow-up adoption remains. Similar near-duplication exists for `Checkpoint Timing`, `Phase Handoff Manifest`, and `Scratch Directory` bookkeeping.
6. **Invariant references are not equivalent to independent definitions.** Quality-gate defines invariant IDs; Warden defines 10 `INV-P` predicates. Recon and red-team cite quality-gate IDs rather than defining independent sets. Counts are not aggregated here; the repo has 4 `check_qg_*.py` checkers, and they cover only part of the prose contracts.
7. **The follow-up backlog separates deletion from new tooling.** Some prose duplicated shipped scripts (ledger-append Reference Python); other candidates are deterministic algorithms that still need implementation and adoption (verdict-marker composition, gate-ledger verification, replay resume). The former is deletion; the latter requires tooling.

---

## 3. Shared convention files — `skills/shared/*.md` (21)

### 3.1 Mechanical (scriptable)

| File · section | Bucket | One-line reason |
|---|---|---|---|
| `return-convention.md` § Receipt Grammar (v1) # | Mech ✓ | Fixed 7-section header order, field grammars (`[a-z][a-z0-9-]*`, `conf=(0\.\d{2}\|1\.00)`), closed verb vocabulary — all parseable. |
| `return-convention.md` § Witness Protocol + `expect-fail`/`expect-absent`/`ran=` # | Mech ✓ | Deterministic signature forms, polarity rules, closed `UNRUNNABLE` vocabulary, `ran=`/verb matching rules — the rcpt_verify grammar spec. |
| `return-convention.md` § Two-Tier Receipt Linter # | Mech ✓ | Literal "fail if …" pseudocode; already ported to `scripts/rcpt_verify.py`; orchestrators should not re-read prose as fallback. |
| `return-convention.md` § Parent-Child Receipt Binding # | Mech ✓ | `sha256(normalize(receipt))` + snake_case ledger keys + skill-qualified phase stamping — deterministic. |
| `return-convention.md` § Tripwire Manifest (Layer 2) | Hybrid ✓ | Layer-2 sweep is a manifest-hash/ref reconciliation (mechanical core), but `SUPERSEDES` resolution is grounds-binding judgment (documented at length). |
| `dispatch-convention.md` § Dispatch directory / file naming / header # | Mech ✓ | Fixed path `<N>-<template-name>.md`, 4-line audit header, seq pre-allocation — deterministic. |
| `dispatch-convention.md` § Pointer prompt format | Mech ✓ | 80–120 token ceilings, hard rule list ("no file lists, no context") — checkable constraints. |
| `dispatch-convention.md` § Scope Anchoring tier 1 | Mech ✓ | `git diff --name-only` boundary check + reject condition — mechanical by design. |
| `dispatch-convention.md` § Scope Anchoring tier 2 | Judgment ✓ | The scope judge is a judgment subagent (already measured #562, and shipped as shared/scope-judge-prompt.md). Not scriptable; the *schedule/parse* of its verdict is the only mechanical bit. |
| `dispatch-convention.md` § Graphify consult | Mech ✓ | Staleness-state → dispatch-action decision table (`fresh`/`stale:N≤5`/else) — quantized table. |
| `dispatch-convention.md` § Pipeline-Active Marker | Mech ✓ | JSON schema, 4-step lifecycle, branch-match resume check — deterministic. |
| `dispatch-convention.md` § Compaction Recovery marker | Mech ✓ | Two-line marker format, seq-recovery glob rule — deterministic. |
| `dispatch-convention.md` § Dispatch Manifest | Mech ✓ | `manifest.jsonl` schema, write-before/after protocol, **token estimation aggregation math (chars/4, rework %) is arithmetic**. |
| `dispatch-convention.md` § Receipt Ledger | Mech ✓ | 4-key JSONL rows, snake_case keys, cleanup copy rules — deterministic. |
| `dispatch-convention.md` § Cleanup / Failure handling | Mech ✓ | Copy/delete step list, abort-on-missing-file rule — deterministic. |
| `ledger-append.md` § Emit protocol + kill-switch + WHS + marker→field mapping + lock protocol + L-2 dedup + L-8 truncation + L-9 # | Mech ✓ | Most is the spec of `scripts/ledger_append.py`; the executable semantics (emit-or-skip, dedup by `(run_id, skill)`, mkdir-lock) already live in the script. |
| `ledger-append.md` § **Reference Python — `scripts/ledger_append.py` / `scripts/uuid7.py`** # | Mech ✓ | Survey snapshot contained **about 22.8KB of fenced Python source**: `ledger_append.py` was verbatim; the `uuid7.py` excerpt was abridged. PR #644 removed these copies. |
| `cairn-convention.md` § File layout + line-shape grammars | Mech ✓ | Four-section schema, regex grammars per body line (`^I-\d{2}(?: supersedes I-\d{2})?: .+$` etc.), ≤240-char caps — parseable. |
| `cairn-convention.md` § Phase Entry Check | Mech ✓ | Literal "fail if …" lint list — deterministic. |
| `cairn-convention.md` § Reconciliation Pass | Mech ✓ | Rule 1 (LEDGER count = ledger entries), Rule 2 (closure-trailer forms), Rule 3 (12-hex prefix uniqueness), Rule 5 (counter-arithmetic) are deterministic; Rule 4 is a judgment decision point (kept prose). |
| `cairn-convention.md` § Read rules / Shedding license / Recovery | Mech ✓ | Fixed re-read cadence + run-id pathing — deterministic. |
| `cairn-convention.md` § Budget pressure | Hybrid ✓ | Line-cap rules mechanical; *what to compact* incl. summary-of-summaries is judgment. |
| `harness-adapter.md` § Mappings 1–5 (frontmatter fields, command-file location, subagent dispatch, sequential fallback, forge posting) | Mech ✓ | Portability mapping tables harness → mechanism — deterministic selection. |
| `harness-adapter.md` § Mapping 1b — per-role model tiers | Mech ✓ | Role → tier pin table, checker-enforced via `scripts/check_model_pins.py`; the *why* (offensive/defensive boundary) stays prose. |
| `harness-adapter.md` § Per-harness install manifest | Mech ✓ | Install commands per harness — deterministic. |
| `security-signals.md` (whole; includes nested detector section below) | Mech ✓ | Seven keyword categories + 2-of-7 activation threshold + category-8 structural rule + contract YAML field — detection table and decision rule. |
| `security-signals.md` § Automated detector (Sentry/PostHog/…) — subset of row above | Mech ✓ | Finite SDK-init table + single-match trigger — deterministic; `vuln_ruleset.py`/`vuln_rules.json` covers a related detector surface. This nested row is not a separate section-size total. |
| `severity-verdict-contract.md` § Severity scale table | Mech ✓ | 4-tier definitions with gating-band column (C/I vs Minor/Suggestion) — quantized table. |
| `severity-verdict-contract.md` § Verdicts + T-set rule | Mech ✓ | `T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}`, full verdict×severity matrix — pure decision table. |
| `severity-verdict-contract.md` § Finder-angle severity caps | Mech ✓ | "quality angles capped at Minor/Suggestion by construction; bug angles may emit full scale" — table + cap rule. |
| `severity-verdict-contract.md` § Anti-patterns | Judgment ✓ | Prohibitions that stop a reviewer from doing the wrong thing — behavioral guidance, not computation. |
| `session-index-convention.md` (whole) | Mech ✓ | Outbox path computation (`sha256sum \| cut -c1-16`), append schema, event-type tables, seq=0 rule, path-discovery rules — deterministic; emit side is de-hooked (session-index.sh drains), emit composition is prose. |
| `fetched-content-containment.md` § endpoint rule + DEC-5 + ledger ERE + append-only lifecycle | Mech ✓ | Authoritative POSIX-ERE for `- FETCHED-ENDPOINT FE-<n> | <host> | <url> | <date> | <state>` + append-only rules — the ledger *shape* is mechanical, though "is this an outbound destination?" is the judgment-adjacent call it wraps. |
| `fetched-content-containment.md` § extraction allowlist + prohibitions + anti-rationalization | Judgment ✓ | "Is fetched text a usage example?" / "would this obey the fetched text?" — judgment calls on content substance. |
| `uss-approximation-patterns.md` (whole) | Mech ✓ | 19 CSS→USS/C# recipes = deterministic translation table; *choosing* which pattern applies is judgment (mock-to-unity/mockup-builder do that). |
| `uss-effect-decisions.md` (whole) | Mech ✓ | Lookup-or-append decision registry — mechanical bookkeeping. |
| `change-bundling-convention.md` # | Mech ✓ | Already scripted (`scripts/change_bundling.py`); retained only for the coverage-guarantee semantics. **Non-goal, not re-litigated.** |
| `compass-protocol.md` # | Mech ✓ | Already scripted (`scripts/compass.py`, `hooks/`-adjacent invariants); protocol is the script's spec. **Non-goal.** |

### 3.2 Judgment (stays prose)

| File · section | Bucket | One-line reason |
|---|---|---|---|
| `reviewer-common.md` § Review Checklist (Targeted Lenses: Surgical Changes, DRY, SRP, OCP) | Judgment ✓ | Lens definitions and their precedence/co-fire rules are partially mechanical (see severity caps), but the finding *content* — is this hunk scope-bleed, is this a real duplication — is substance reasoning. |
| `external-review-prompt.md` (whole) | Judgment ✓ | A code reviewer's brief: severity calibration examples + "DON'T pad" norms — content judgment. |
| `scope-judge-prompt.md` (whole) | Judgment ✓ | Traces diff→request semantics; the only mechanical bits are the hard constraints (data-region boundaries) and output format. |
| `severity-rubric.md` (whole) | Judgment ✓ | Fatal/Significant/Minor definitions keyed to artifact impact — subjective assessment; the 3/1/0 weighted scoring that *consumes* it is mechanical but small. |
| `change-sizing.md` (whole) | Judgment ✓ | Explicitly "advisory — never gating"; thresholds are human-reviewability heuristics, and the doc says so repeatedly. |
| `delve-engine.md` § 1 (cutting rule) / § 4 (finder angles) / § 5 (verify gate) | Judgment ✓ | "Single concrete reproduction vs systemic" and finder/verifier reasoning are substance judgment. |
| `delve-engine.md` § 2 (params), § 3 (effort tiers), § 6 (output schema), § 7 (dispatch) | Mech ✓ | Fixed param/schema/fan-out tables and record shape — deterministic; the engine already delegates mechanism to harness-adapter. |
| `model-tier-policy.md` § rationale/boundary | Judgment ✓ | Eval-before-default reasoning, offensive/defensive boundary, calibration distribution — policy judgment. |
| `model-tier-policy.md` § role→tier table + enforcement boundary | Mech ✓ | Pins table + what `check_model_pins.py` does/doesn't enforce — deterministic surface, mixture with the policy prose above. |
| `implementer-common.md` § Self-Review Checklist / discipline | Judgment ✓ | Self-assessment questions — judgment. |
| `implementer-common.md` § TDD sub-skill invocation + TDD Evidence Log format | Mech ✓ | Fixed RED/GREEN/COMMIT/REFACTOR loop steps and a REQUIRED log format; the test-writing itself is judgment. |

### 3.3 Canonical-reference occurrences

Counts are literal occurrences of `CANONICAL: shared/<file>` references in skill files, including inline references and quoted examples. They are not unique skills or measured runtime reads.

| Shared doc | `CANONICAL` marker/reference occurrences |
|---|---|
| `dispatch-convention.md` | **31** |
| `ledger-append.md` | **10** |
| `return-convention.md` | **8** |
| `compass-protocol.md` | 6 |
| `cairn-convention.md` | 5 |
| `fetched-content-containment.md` | 3 |
| `change-sizing.md` | 3 |
| `severity-verdict-contract.md` | 2 |
| `security-signals.md` | 2 |
| `delve-engine.md` | 2 |
| `change-bundling-convention.md` # | 2 |
| `harness-adapter.md` | ~0 inline (referenced by engine) |

---

## 4. Skill inventory — `skills/*/SKILL.md` (52)

### 4.1 Mechanical-dominant skills (scriptable core, small judgment wrapper)

| Skill | Key mechanical sections (rough size hints) | Bucket | One-line reason |
|---|---|---|---|
| `checkpoint` | whole skill (1.5k) | Mech ✓ | Shadow-repo mkdir/commit/restore/ls are deterministic Bash instructions; no checkpoint helper script exists in this corpus. |
| `compass` # | whole skill (1.3k) | Mech ✓ | Already `scripts/compass.py`; SKILL.md is CLI usage. **Non-goal.** |
| `grudge` # | whole skill (1.1k) | Mech ✓ | Read/write already `scripts/grudge_query.py` + `grudge_append.py`; schema + invocation are the residual prose. |
| `merge-pr` | Step 1–7 (1.6k) + bash blocks (~1k) | Mech ✓ | CI-status check, working-tree check, repo-safety check, test detection, merge execution, post-merge CI watch, cleanup — deterministic git/gh/bash sequence with 3-retry null guards. The human-checkpoint framing ("MANDATORY CHECKPOINT") is process, not judgment. |
| `finish` | Step 1–6 + pre-push validation + merge/PR bash (4.3k) | Mech ✓ | `git merge-base`-derived base branch, merge commands, PR create, `gh pr checks --watch` disambiguation logic — all deterministic shell. The option *presentation* (which of 4 options to offer) is the judgment tail. |
| `worktree` | Steps 1–5 + verify baseline (0.65k) | Mech ✓ | Project-name detection, path computation, `git worktree add`, per-ecosystem setup commands, clean-baseline verification — deterministic shell. |
| `dependency-audit` | Manifest walk + per-ecosystem tools + Computation (2.8k) | Mech ✓ | Walk for package.json/Cargo.toml/requirements.txt/pyproject.toml → run npm/cargo/pip-audit → **BLOCKED > FINDINGS > INCONCLUSIVE > FAILED > CLEAN precedence table** — pure decision table (body-read). |
| `distill` | Phases 0–5 + Shell Safety (2.3k) | Mech ✓ | Tool availability check, input resolution, conversion commands, digest/health-check steps — deterministic shell/prose pipeline. |
| `stocktake` | Efficiency-report computation Steps 1–6 (1.3k) | Mech ✓ | Chronicle loading, per-skill aggregation (averages, rework %, trend rules "<4 runs / ±10%"), report table — arithmetic described as prose (body-read). |
| `recall` | Invocation/query patterns (0.6k) | Mech ✓ | Fixed query verbs + filters over the activity index — deterministic lookup syntax. |
| `replay` | Steps 1–5: manifest parse, dedup-by-seq, phase-boundary resolution, artifact verify (git-log matching), checkpoint correlation, re-dispatch manifest continuation (1.5k) + mutation/diff output (1.0k) | Mech ✓ | All deterministic data processing (body-read): "last entry per seq authoritative", phase-complete predicate, fallback cascade. Judgment-free by design. |
| `temper-eval-collect` / `temper-eval-calibrate` | whole (0.98k + 0.57k) | Mech ✓ | Stage-manifest reads, seq idempotency, wave dispatch counting, error-ratio computation — harness mechanics. |

### 4.2 Hybrid — mechanical core + judgment dispatch/scoping

| Skill | Mechanical slots | Judgment core | Bucket |
|---|---|---|---|
| `build` | Gate Ledger Protocol (1.8k: PipelineID gen `date -u +build-…`, ledger format, status-set gate check, verdict-marker verification glob/filter/sort/verify/delete, skip hatch); Pipeline Status (1.9k); Compression State (1.6k); Phase Handoff Manifest (0.4k); Checkpoint Timing (0.4k); Impact Manifest (0.5k); Mock Dispatch Mode (0.6k) | Phase 1/2/3 design-plan-execute judgment; red-team/innovate rounds | Hybrid ✓ |
| `quality-gate` | Receipt Linter (→ rcpt_verify hook); Verdict Marker (40-field KV schema, field order, enum vocab, cross-field invariants, sha256 computation, omit-when-empty rules); Convergence Telemetry (JSONL field semantics, chunk-boundary parsing); Round History/Compaction Recovery (checkpoint writes, round-score files, marker reconciliation); Implementation Invariants (prose-checkable); Artifact prep/chunking; Minor Issue Handling; Fix Mechanism + fan-out telemetry; Escalation/exit-precedence; Security detection routing (→ security-signals) | Stagnation judge (score math mechanical, "genuinely new or whack-a-mole" judgment); red-team rounds; anti-anchoring | Hybrid ✓ |
| `warden` | Reviewer-set selection (which legs run for which artifact class — decision table); large-diff bundling (→ change_bundling.py); double-run avoidance; verdict-marker ownership; 10 defined `INV-P` predicates; migration/rollback; acceptance criteria | Each reviewer leg's findings | Hybrid ✓ |
| `siege` | Activation heuristic (→ security-signals, 1.3k); Phase 3 finding dedup fields (0.9k); finding/report formats (1.1k); calibration ledger emit Tier A (1.0k → ledger_append); threat-model persistence (1.6k); compaction/status (1.1k); agent-coverage table (0.4k) | 6 attacker perspectives; exploit attempts; findings severity | Hybrid ✓ |
| `audit` | `--bugs` sub-path (→ delve; 1.0k); suppress-and-cite gate (0.5k); code-finding schema incl. mandatory `sites` (0.7k); pipeline-status + compaction recovery (0.95k + 0.9k); coverage map (1.6k); Phase 2/3 orchestration steps (1.2k + 1.1k) | The audit lenses themselves (systemic findings judgment) | Hybrid ✓ |
| `temper` | Scope resolution + diff preflight (1.7k: forge-agnostic range resolution, oversized-diff cap); Terminal Verdict Emit (2.0k — verdict→ledger mapping, PF-glob construction algorithm: depth-correct directory globs vs verbatim root files vs cap truncation — genuinely algorithmic, body-read); display-vocabulary/taxonomy (0.7k) | Round-1 delve-engine drive (9.4k — verification verdicts, discharge decisions), iterate-on-feedback loops | Hybrid ✓ |
| `inquisitor` | 5-dimension fan-out dispatch (parallel scaffolding, 1.1k); dedup/consolidation rules; report format | Each dimension's adversarial reasoning | Hybrid ✓ |
| `recon` | Scout/dispatch fan-out structure; verification-ledger convention (0.7k); falsification-grep protocol; depth-module dispatch (0.9k); scratch/compaction (0.7k) | Scout synthesis, brief content (structure/patterns/prior art) | Hybrid ✓ |
| `spec` | Wave construction (0.4k), dependency/cycle detection (0.6k), skip logic (0.5k), contract schema validation (0.6k), per-ticket lifecycle (0.4k), status/compaction (1.1k) | Per-ticket investigation + autonomous decision-making (1.2k) | Hybrid ✓ |
| `red-team` | Loop rules (0.6k), stagnation detection threshold rules (0.7k), issue-classification table (0.4k), ledger cost-cap (0.5k), fix-mechanism table (0.9k) | Devil's-advocate findings + severity + fix review | Hybrid ✓ |
| `debugging` | Orchestrator-subagent workflow scaffolding (4.9k — phase state machine), Phase 4.5 Where-Else scan report schema (5.4k, structured fields: Generalize/Evaluated/Fixed/Skipped/Reverted), session metrics (0.5k), pipeline status (2.1k) | Root-cause hypothesis formation (0.7k), red-team loop, pattern analysis | Hybrid ✓ |
| `prospector` | Dependency-category taxonomy (0.6k), merge-confidence rules (0.8k), source-prioritization/convergence clusters (1.2k), trajectory snapshot (0.5k), phase orchestration | Architecture-friction judgment + competing designs (0.6k+) | Hybrid ✓ |
| `forge` | Mode 1 retrospective trigger rules + update rules (1.1k), trajectory capture/redaction (0.9k), storage (0.5k), skill-mutation proposal protocol (0.8k) | Retrospective content (lessons, skill-worthy patterns) | Hybrid ✓ |
| `migrate` | Phase 0 pre-flight (0.5k), blast-radius mapping (0.6k), decompose-into-phases rules/legacy patterns (0.5k), consumer-wave planning (0.4k), status/compaction (0.8k), model allocation (0.4k) | Compatibility-layer design, migration-target analysis | Hybrid ✓ |
| `parallel` | Pre-dispatch file-overlap analysis (0.5k), manifest/dispatch protocol (0.3k), verification (0.3k) | Identifying independent domains (0.6k) — genuinely judgment | Hybrid ✓ |
| `project-init` | Tier-1 deep scan phases (1.2k incl. partition/fan-out/size caps), Tier-2 cross-repo discovery (1.1k incl. manifest parsing, local-sibling detection, relevance ranking), re-invocation merge (0.5k) | What to record, CLAUDE.md proposal content, ranking *judgment* | Hybrid ✓ |
| `cartographer-skill` | Storage + file-size caps (0.4k), template structures for module-map/landmines/decisions (0.7k), update rules + defect-signature recording format (0.5k) | What's worth recording, generalized-pattern content | Hybrid ✓ |
| `adr` | Eligibility gate (0.4k — gate logic), numbering (0.2k), template (0.2k), status lifecycle transitions (0.3k) | Which alternative, why chosen, consequence assessment | Hybrid ✓ |
| `anvil` | Eval harness run protocol (1.9k — spawn all runs same turn, capture timing, grade aggregation, viewer launch), commit-message format (0.4k), description-optimization loop (1.5k — includes A/B mechanics but writing the new description is judgment) | Interview/research, SKILL.md content, feedback interpretation | Hybrid ✓ |
| `verify` | Gate function/iron-law checklist (0.4k) | Whether evidence genuinely demonstrates completion | Hybrid ✓ |
| `test-coverage` | Test-run detection, output format (0.3k), report template (0.2k) | Whether a test is stale/needs-update/obsolete — content judgment | Hybrid ✓ |
| `review-feedback` | Calibration-ledger emit stub (0.3k → ledger_append) | All of it — the skill is "how to engage with feedback" | Hybrid ✓ (mechanical tail) |
| `handoff` | Step 0 nothing-to-hand-off check (0.2k), output-contract format (0.3k) | Continuation vs backlog judgment + content | Hybrid ✓ |
| `getting-started` | Trust-hierarchy + dispatch table (0.3k) | Onboarding content | Hybrid ✓ (mostly judgment) |
| `consensus` | Parallel dispatch + aggregation mechanics (0.7k, MCP servers) | Synthesis judgment | Hybrid ✓ |

### 4.3 Judgment-dominant skills (stays prose; mechanical tails noted)

| Skill | Why judgment | Mechanical tail |
|---|---|---|
| `design` | Brainstorming into designs, dimension exploration, tradeoff presentation | Contract emission (0.4k), phase-process scaffolding (0.5k) |
| `assay` | Weighing options vs constraints, confidence scoring, kill criteria | Report schema (0.3k) |
| `adversarial-tester` | Inventing plausible failure modes for an implementation | Report format (0.3k), skip condition (0.2k) |
| `delve` (skill) | Owns the delve-engine judgment (repro-verifiable defects) | Scope resolution + preflight (0.9k — forge-agnostic range, diff size cap) |
| `planning` | Plan quality/content | Header + task-structure formats (0.6k), refactoring-task metadata (0.3k) |
| `source-driven-development` | Detect→fetch→implement→cite protocol on real artifacts | Fetched-endpoint ledger use (→ fetched-content-containment) |
| `test-driven-development` | Test authoring, level selection | RED/GREEN/REFACTOR gate steps (0.3k mechanical cadence), evidence-log format (0.2k) |
| `mock-to-unity` | Translation judgment per effect | USS/UXML scaffold generation protocol (0.5k), Unity-6 rules checklist (0.3k), ui-verify handoff (0.2k) |
| `mockup-builder` | Visual-design decisions | Mockup structure + Translation Notes format (0.3k) |
| `ui-verify` | Visual comparison judgment | Step 2b code-level structural audit (0.3k — checklist), delta-report schema (0.2k) |
| `workshop`, `skill-selection-evals` | Catalog/routing content | negligible |
| `orchestrator` | Fleet coordination judgment | Worktree/workspace creation commands (0.5k), context-monitor fields (0.2k) |
| `innovate` | Divergent-creativity content | Scratch dir + run marker + sweep-mode bookkeeping (0.8k), compaction (0.3k) |


---

## 5. Already-mechanized (non-goal, listed for completeness — do NOT re-litigate)

Per the issue's explicit non-goals, these operations already have a script or deterministic shell procedure; residual opportunity is *prose shrinkage*, not new machinery:

- **Receipt linting** → `scripts/rcpt_verify.py` + `hooks/rcpt-verify-hook.sh` (return-convention § Two-Tier Linter is the spec).
- **Change bundling** → `scripts/change_bundling.py` (change-bundling-convention).
- **Compass** → `scripts/compass.py` (compass-protocol).
- **Calibration ledger** → `scripts/ledger_append.py`, `scripts/uuid7.py` (ledger-append) — the scripts are shipped; §6 ticket #1 records the prose-copy deletion opportunity identified at survey time.
- **Checkpoint** — deterministic Bash instructions in `skills/checkpoint/SKILL.md`; no checkpoint helper script exists in this corpus.
- **Grudge** → `scripts/grudge_query.py`, `scripts/grudge_append.py`.
- **Security-signals keyword detection (partial)** → `scripts/vuln_ruleset.py` + `vuln_rules.json` (adjacent surface; no full activation CLI).
- **QG second-pass scoring** → `scripts/second_pass_scorer.py` + `run_second_pass_evals.py` (the motivating drift case).
- **QG invocation-channel check** → `scripts/check_settings_surface.py`; the repo also has 33 `scripts/check_*.py` checkers (phrase-pin + drift — see limits §8).

---

## 6. Candidate priorities

### 6.1 Model

This survey did not measure residency or execution-turn savings. The candidates below are qualitative priorities based on repeated procedural work, known deterministic rules, and the 2026-09-18 survey snapshot; they are not a measured or ranked cost forecast. Canonical-reference occurrence counts in §3.3 do not establish runtime loads.

### 6.2 Candidate list (prioritized qualitatively)

| # | Candidate | Scope | Rationale | Status / note |
|---|---|---|---|---|
| 1 | **Delete embedded Reference-Python from `ledger-append.md`** | `ledger-append.md` | Remove source copies now maintained as executable scripts. | Behavior-neutral deletion; done in #644 |
| 2 | `dispatch.py` — seq alloc, dispatch-file header, manifest write-before/after, cleanup | `dispatch-convention.md` | Repeated deterministic dispatch bookkeeping. | Core script in #644; selective adoption remains |
| 3 | **Pipeline-status adoption + `pipeline_status.py`** | Six skill status blocks | Repeated status lifecycle and duplicated convention. | Core implemented in #644; selective adoption remains |
| 4 | `cairn.py check` — Phase Entry Check + Reconciliation Pass | Cairn checks in adopting skills | Repeated deterministic schema and ledger validation. | Core script in #644; consumer wiring remains |
| 5 | `gate-marker.py` — verdict marker + convergence telemetry writer | Quality-gate marker and telemetry | Schema, hashing, and cross-field validation are deterministic. | Candidate; not implemented |
| 6 | `gate-ledger.py` (extend `hooks/gate-ledger-guard.sh`) | Build gate ledger protocol | Marker discovery, ordering, validation, and cleanup are deterministic. | Candidate; not implemented |
| 7 | Prose-shrink the scripted receipt linter | Receipt linter spec | Reduce repeated instructions while preserving divergence notes and required CLI calls. | Prose shrink only; no new machinery |
| 8 | `security-signals.py scan` — keyword categories 1–7 + 2-of-7 threshold | `security-signals.md` categories 1–7 | Automate keyword matching and threshold only. Category 8 is structurally matched and out of scope; retain its existing review handling separately. | Candidate; not implemented |
| 9 | `verdict_gate.py` — T-set / severity-cap oracle | Severity-verdict contract | Apply fixed verdict and severity-cap tables consistently. | Candidate; not implemented |
| 10 | `emit` extension — temper terminal-verdict construction (incl. PF-glob algorithm) | Temper terminal-verdict emit | Automate deterministic verdict-row construction and PF-glob rules. | Candidate; not implemented |
| 11 | `merge-pr.py` / `worktree.py` / finish git-op wrappers | Merge, finish, and worktree procedures | Automate state checks while preserving human checkpoints. | Lower-frequency candidate |
| 12 | `dep-audit` result computation + `stocktake` report renderer | Dependency-audit and stocktake summaries | Apply precedence table and render fixed report fields. | Small candidate |

### 6.3 Measurement needed

A future cost estimate should retain its measurement script, define non-overlapping token boundaries, distinguish model-visible prose from code/examples, and measure actual reference loading and operation frequency. This survey supplies none of those measurements; its priorities are qualitative.

---

## 7. Seed follow-up build tickets

Suggested phasing at survey time. No ticket re-litigates a non-goal.

**Post-survey status:** PR #644 merged on 2026-09-21 (merge commit `31fd5ec4f2824ee0e53a630f987e7a0a786f0b1b`; https://github.com/raddue/crucible/pull/644), after this branch's 2026-09-18 survey snapshot. It implemented the ledger-append prose purge plus initial `cairn.py`, `dispatch.py`, and `pipeline_status.py` scripts. Dispatch aggregation (`summary`) was deliberately omitted because forge already owns that calculation. PR #644 added runtime pointers in shared conventions; selective consumer adoption remains. Treat tickets 1–4 below as original recommendations, not an unstarted backlog.

**Tier 1 — original top recommendations (status below):**

1. **Ledger-append prose purge — done in #644.** PR #644 removed the live-code reference copies; no follow-up build needed.
2. **`scripts/dispatch.py` — core shipped in #644.** `seq`, `before`, `after`, and `cleanup`; follow-up is selective consumer adoption. Keep token/rework aggregation in forge; no duplicate `summary` command.
3. **`scripts/pipeline_status.py` — core shipped in #644.** `write` and `compact` plus canonical convention and tests. Follow-up: selectively adopt the canonical link/runtime pointer and remove duplicated shared protocol prose, preserving skill-specific bodies and health triggers.
4. **`scripts/cairn.py` — core shipped in #644.** `check` and `reconcile` plus tests. Follow-up: wire runtime checks into cairn-adopting skills; retain in-context witness/manifest checks and Rule 4 supersession decision.

**Tier 2 — next (per-skill, gate-shaped):**

5. **`scripts/gate_marker.py`** — `write` (verdict marker) + `append-convergence` (telemetry JSONL) validating field order, enum vocab, omit-when-none, cross-field invariants. Test: field-order violation, invariant `len(FanOutRounds) ≤ FanOutCheckCount` breach, chunk-boundary `|` parsing.
6. **`scripts/gate_ledger.py`** (or fold into #5) — ledger format write + the 7-step verdict-marker verification loop; keep `hook/gate-ledger-guard.sh` as the enforcement layer.
7. **`scripts/security_signals_scan.py`** — match keyword categories 1–7 and apply their 2-of-7 threshold over prose/diff inputs; return category matches and threshold result, not a final `security_review` verdict. Category 8 (Destination-Bearing Construct) is out of scope: its base-tree host baseline, shape matches, single-match trigger, and uncertain outcome remain governed by `skills/shared/security-signals.md`. Callers must combine Category 8 handling before deciding siege activation; an unimplemented or uncertain Category 8 check must not mean "no signal." Wire categories 1–7 into build/spec without changing Category 8 behavior.
8. **`scripts/verdict_gate.py`** — `T = {CONFIRMED,PLAUSIBLE}×{Critical,Important}` membership + finder-angle severity-cap table; consumed by temper round bookkeeping and delve output normalization.

**Tier 3 — opportunistic (low frequency, high ceremony):**

9. **`scripts/temper_emit.py`** — terminal-verdict row construction incl. the PF-glob algorithm (depth-correct per-directory globs, root-file verbatim, cap truncation, escalation→null rules). Extends `ledger_append.py`, doesn't replace it.
10. **`scripts/merge_pr_steps.py` / `scripts/worktree.py`** — the git-op wrappers; worthwhile only if the ceremony (checkpoints, human confirmations) can stay in prose while the *state checks* move to scripts.
11. **`scripts/dep_audit_compute.py`** + **`scripts/stocktake_report.py`** — precedence-table evaluate + report renderer. Small, do when passing by.
12. **Prose-shrink pass (no new machinery):** return-convention linter section → single block "run `rcpt_verify.py --tier2 --strict --root …`" + keep only the *deliberate divergence* notes; severity-verdict-contract anti-patterns stays; dispatch-convention Scope-Anchoring §2 stays (judgment).

---

## 8. Limits (so this is checkable, not vibes)

- **Estimation base**: corpus bytes, file counts, `## ` heading count, and literal canonical-reference occurrences are measured inputs reproduced by the appendix. Section classifications and candidate priorities are qualitative; token residency, mechanical share, and turn savings are not measured or claimed.
- **Bucket-confidence flags**: `✓` = body-read, `~` = heading-inferred. No rows are flagged `~`; inventory rows summarize selected sections rather than classifying every heading.
- **PR status evidence**: PR #644's merge commit and URL are recorded in §7. Snapshot-era recommendations remain distinct from post-merge status.
- **Prompt-cache sensitivity**: prompt-cache effects, cache ratios, and spend are not measured.
- **Phrase-pin checkers are not behavior oracles.** `second_pass_scorer.py` documents five live-verified prose inversions that phrase-pinning missed. This demonstrates why executable oracles need behavior-focused fixtures; it does not quantify prevalence across skills.
- **Pipeline-status duplication**: at survey time, blocks across 6 skills were adapted, not verbatim. Follow-up canonicalization must keep per-skill bodies and health triggers rather than replacing them wholesale.
- This survey does not assess *which* scripts should run at dispatch-time vs a hook vs CI — that's for the build tickets, not this spike.

## Appendices

**Reproduce corpus measurements** (bytes, skill/shared file counts, `## `-prefixed lines, literal canonical-reference occurrences):

```bash
python3 - <<'PY'
from collections import Counter
from pathlib import Path
import re

skills = sorted(Path('skills').glob('*/SKILL.md'))
shared = sorted(Path('skills/shared').glob('*.md'))
files = skills + shared
links = Counter()
headings = 0
for path in files:
    text = path.read_text()
    headings += sum(line.startswith('## ') for line in text.splitlines())
for path in skills:
    links.update(re.findall(r'CANONICAL: shared/([^ >]+)', path.read_text()))
size = sum(path.stat().st_size for path in files)
print(f'skills={len(skills)} shared={len(shared)} bytes={size} ##-lines={headings}')
for target, count in links.most_common():
    print(f'{target}: {count}')
PY
```

This reproduces corpus measures, not the qualitative classifications or priorities. The temporary scripts used for the original section estimates/similarity are not retained.

**Scripts referenced above:** runtime/helpers include `rcpt_verify.py`, `ledger_append.py`, `uuid7.py`, `compass.py`, `change_bundling.py`, `grudge_query.py`, `grudge_append.py`, `vuln_ruleset.py`, `vuln_rules.json`, `second_pass_scorer.py`, `run_second_pass_evals.py`, `verify_comment_positions.py`, `pathmatch.py`, `atomic_write.py`, and `catalog.py`; the repo also has 33 `scripts/check_*.py` checkers and hooks `gate-ledger-guard.sh`, `rcpt-verify-hook.sh`, `session-index.sh`, `session-summary.sh`, and `build-routing-advisor.sh`.
