# Spike #643 — How much of Crucible's skill logic can move from prose to deterministic scripts?

- **Date:** 2026-09-18
- **Branch:** `research/643-skill-scripting-spike`
- **Scope:** `skills/*/SKILL.md` (52 skills) + `skills/shared/*.md` (21 files) on this branch's survey snapshot. This document implements no conversions (issue non-goal).
- **Deliverable:** classification inventory (section → bucket → one-line reason), token/turn cost estimate for mechanical-classified prose, ranked savings, seed follow-up tickets.
- **Snapshot:** corpus and candidate ranking describe the survey as of 2026-09-18. PR #644 later implemented parts of the first four recommendations; status appears in §7.

---

## 1. Corpus and method

| Measure | Value |
|---|---|
| SKILL.md files | 52 |
| shared/*.md files | 21 |
| Total corpus bytes | 1,938,609 (~**485k tokens** at bytes/4) |
| — of which SKILL.md | 1,585,010 (~396k tok) |
| — of which shared/ | 353,599 (~88k tok) |
| Lines beginning `## ` counted (including fenced examples) | 930 |
| `CANONICAL` marker/reference occurrences (skill → shared doc) | counted, §3.3 |

**Method.** Counted lines beginning `## ` across the corpus, including headings inside fenced examples. The inventory names shared-doc sections in §3 and summarizes mechanical areas by skill in §4; it is not a row-per-heading classification of all 930 lines. Buckets:

- **Mechanical (scriptable)** — fixed right answer given inputs: format/grammar validation, path/artifact resolution, bundling/coverage accounting, quantized decision tables, aggregation math, ledger/marker/status writes, git-state checks.
- **Judgment (stays prose)** — right output depends on model reasoning over the artifact's substance: review findings, design tradeoffs, hypothesis formation, adversarial content, subjective quality assessment.
- **Hybrid** — mechanical core wrapped in judgment-driven dispatch/scoping (e.g. a mechanical scoring rule decides *whether* an agent round runs, but the round is judgment).

Each shared-doc inventory row identifies a section and a concrete mechanism or reason. Skill rows summarize the mechanical slots and judgment core by skill; they do not enumerate all `##` headings individually. Rows flagged `✓` were verified by reading the body; rows flagged `~` are inferred from the section's stated purpose in its heading plus cross-references, not read line-by-line. A `#` marker after a shared-doc row means the behavior is already mechanized (script/hook exists) and is not a new conversion candidate.

**Honest caveat on bucket sizes.** Estimated *residency* (tokens loaded into context) ≠ *conversion value*. A 9k-token judgment section that ships zero determinism is worth less than a 1.5k-token mechanical section executed 30× per run. The cost ranking (§6) is the usable output; the inventory is the substrate.

---

## 2. Headline findings

1. **Estimated ~75–80% of shared-doc bytes are mechanical** (≈69k tokens of ≈88k), dominated by five protocol docs: `return-convention.md` (19.7k), `ledger-append.md` (11.5k), `dispatch-convention.md` (9.2k), `harness-adapter.md` (7.5k), `cairn-convention.md` (4.8k). A large fraction is already mechanized (non-goal). `ledger-append.md` contained about 22.8KB of fenced Python source in the survey snapshot: `ledger_append.py` was reproduced verbatim, while the `uuid7.py` excerpt was abridged; PR #644 removed both live-code reference blocks.
2. **The top lever is potential aggregate fan-out, not file size.** The survey snapshot has 31 literal references to `shared/dispatch-convention.md` and estimates its mechanical share at ~95% → ≈8.7k tokens × 31 ≈ **270k gross weighted-residency tokens** if each reference's containing skill loads the full doc once. This is a scenario sum, not measured re-reads per dispatch or phase. `ledger-append.md` (10 references), `return-convention.md` (8), `cairn-convention.md` (5).
3. **The highest-load skills pay a mechanical toll before doing any judgment.** Baseline gross residency estimates per full skill activation: canonical shared mechanical docs add siege 49.3k tok, quality-gate 45.2k, red-team 40.4k, build 37.1k, warden 30.3k, temper/delve 29.4k each, audit/inquisitor/test-coverage/orchestrator 20.7k each. These are estimates, not measured token consumption.
4. **A concrete drift failure is on record.** `scripts/second_pass_scorer.py`'s docstring describes five live-verified in-place inversions of one scoring rule that left phrase-pin checkers green. Its scorer/eval caught behavior those checkers missed; this demonstrates a failure mode, not its frequency across the corpus.
5. **Pipeline-status prose was duplicated at survey time**: `Pipeline Status` blocks exist in 6 skills (build, debugging, audit, siege, migrate, spec). PR #644 added `shared/pipeline-status-convention.md` and a build link; follow-up adoption remains. Similar near-duplication exists for `Checkpoint Timing`, `Phase Handoff Manifest`, and `Scratch Directory` bookkeeping.
6. **79 INV-* invariants are defined in prose** (quality-gate 63, warden 11, recon 3, red-team 2), but only a handful have runtime checkers (4 `check_qg_*.py`). The majority are prose-only *contracts* the model must hold in context, not artifacts a script verifies.
7. **The follow-up backlog separates deletion from new tooling.** Some prose duplicated shipped scripts (ledger-append Reference Python); other candidates are deterministic algorithms that still need implementation and adoption (verdict-marker composition, gate-ledger verification, replay resume). The former is deletion; the latter requires tooling.

---

## 3. Shared convention files — `skills/shared/*.md` (21)

### 3.1 Mechanical (scriptable)

| File · section | Est. tok | Bucket | One-line reason |
|---|---|---|---|
| `return-convention.md` § Receipt Grammar (v1) # | 3.9k | Mech ✓ | Fixed 7-section header order, field grammars (`[a-z][a-z0-9-]*`, `conf=(0\.\d{2}\|1\.00)`), closed verb vocabulary — all parseable. |
| `return-convention.md` § Witness Protocol + `expect-fail`/`expect-absent`/`ran=` # | 3.3k | Mech ✓ | Deterministic signature forms, polarity rules, closed `UNRUNNABLE` vocabulary, `ran=`/verb matching rules — the rcpt_verify grammar spec. |
| `return-convention.md` § Two-Tier Receipt Linter # | 8.4k | Mech ✓ | Literal "fail if …" pseudocode; already ported to `scripts/rcpt_verify.py`; the 8.4k of prose is what orchestrators must still not re-read as fallback. |
| `return-convention.md` § Parent-Child Receipt Binding # | 1.3k | Mech ✓ | `sha256(normalize(receipt))` + snake_case ledger keys + skill-qualified phase stamping — deterministic. |
| `return-convention.md` § Tripwire Manifest (Layer 2) | 4.7k | Hybrid ✓ | Layer-2 sweep is a manifest-hash/ref reconciliation (mechanical core), but `SUPERSEDES` resolution is grounds-binding judgment (documented at length). |
| `dispatch-convention.md` § Dispatch directory / file naming / header # | 1.6k | Mech ✓ | Fixed path `<N>-<template-name>.md`, 4-line audit header, seq pre-allocation — deterministic. |
| `dispatch-convention.md` § Pointer prompt format | 0.9k | Mech ✓ | 80–120 token ceilings, hard rule list ("no file lists, no context") — checkable constraints. |
| `dispatch-convention.md` § Scope Anchoring tier 1 | 1.5k | Mech ✓ | `git diff --name-only` boundary check + reject condition — mechanical by design. |
| `dispatch-convention.md` § Scope Anchoring tier 2 | 2.8k | Judgment ✓ | The scope judge is a judgment subagent (already measured #562, and shipped as shared/scope-judge-prompt.md). Not scriptable; the *schedule/parse* of its verdict is the only mechanical bit. |
| `dispatch-convention.md` § Graphify consult | 1.1k | Mech ✓ | Staleness-state → dispatch-action decision table (`fresh`/`stale:N≤5`/else) — quantized table. |
| `dispatch-convention.md` § Pipeline-Active Marker | 1.1k | Mech ✓ | JSON schema, 4-step lifecycle, branch-match resume check — deterministic. |
| `dispatch-convention.md` § Compaction Recovery marker | 0.7k | Mech ✓ | Two-line marker format, seq-recovery glob rule — deterministic. |
| `dispatch-convention.md` § Dispatch Manifest | 1.8k | Mech ✓ | `manifest.jsonl` schema, write-before/after protocol, **token estimation aggregation math (chars/4, rework %) is arithmetic**. |
| `dispatch-convention.md` § Receipt Ledger | 1.2k | Mech ✓ | 4-key JSONL rows, snake_case keys, cleanup copy rules — deterministic. |
| `dispatch-convention.md` § Cleanup / Failure handling | 0.9k | Mech ✓ | Copy/delete step list, abort-on-missing-file rule — deterministic. |
| `ledger-append.md` § Emit protocol + kill-switch + WHS + marker→field mapping + lock protocol + L-2 dedup + L-8 truncation + L-9 # | 3.9k | Mech ✓ | Most is the spec of `scripts/ledger_append.py`; the executable semantics (emit-or-skip, dedup by `(run_id, skill)`, mkdir-lock) already live in the script. |
| `ledger-append.md` § **Reference Python — `scripts/ledger_append.py` / `scripts/uuid7.py`** # | **5.7k** | Mech ✓ | Survey snapshot contained **about 22.8KB of fenced Python source**: `ledger_append.py` was verbatim; the `uuid7.py` excerpt was abridged. PR #644 removed these copies. |
| `cairn-convention.md` § File layout + line-shape grammars | 1.9k | Mech ✓ | Four-section schema, regex grammars per body line (`^I-\d{2}(?: supersedes I-\d{2})?: .+$` etc.), ≤240-char caps — parseable. |
| `cairn-convention.md` § Phase Entry Check | 0.9k | Mech ✓ | Literal "fail if …" lint list — deterministic. |
| `cairn-convention.md` § Reconciliation Pass | 1.8k | Mech ✓ | Rule 1 (LEDGER count = ledger entries), Rule 2 (closure-trailer forms), Rule 3 (12-hex prefix uniqueness), Rule 5 (counter-arithmetic) are deterministic; Rule 4 is a judgment decision point (kept prose). |
| `cairn-convention.md` § Read rules / Shedding license / Recovery | 0.8k | Mech ✓ | Fixed re-read cadence + run-id pathing — deterministic. |
| `cairn-convention.md` § Budget pressure | 0.6k | Hybrid ✓ | Line-cap rules mechanical; *what to compact* incl. summary-of-summaries is judgment. |
| `harness-adapter.md` § Mappings 1–5 (frontmatter fields, command-file location, subagent dispatch, sequential fallback, forge posting) | 3.2k | Mech ✓ | Portability mapping tables harness → mechanism — deterministic selection. |
| `harness-adapter.md` § Mapping 1b — per-role model tiers | 2.2k | Mech ✓ | Role → tier pin table, checker-enforced via `scripts/check_model_pins.py`; the *why* (offensive/defensive boundary) stays prose. |
| `harness-adapter.md` § Per-harness install manifest | 1.7k | Mech ✓ | Install commands per harness — deterministic. |
| `security-signals.md` (whole; includes nested detector section below) | 2.0k | Mech ✓ | 7 keyword categories + 2-of-7 activation threshold + category-8 single-match + contract YAML field — pure detection table. |
| `security-signals.md` § Automated detector (Sentry/PostHog/…) — subset of row above | 0.4k | Mech ✓ | Finite SDK-init table + single-match trigger — deterministic; note existing `vuln_ruleset.py`/`vuln_rules.json` covers a related detector surface. Do not add this nested estimate to the whole-file total. |
| `severity-verdict-contract.md` § Severity scale table | 0.9k | Mech ✓ | 4-tier definitions with gating-band column (C/I vs Minor/Suggestion) — quantized table. |
| `severity-verdict-contract.md` § Verdicts + T-set rule | 1.1k | Mech ✓ | `T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}`, full verdict×severity matrix — pure decision table. |
| `severity-verdict-contract.md` § Finder-angle severity caps | 1.2k | Mech ✓ | "quality angles capped at Minor/Suggestion by construction; bug angles may emit full scale" — table + cap rule. |
| `severity-verdict-contract.md` § Anti-patterns | 1.2k | Judgment ✓ | Prohibitions that stop a reviewer from doing the wrong thing — behavioral guidance, not computation. |
| `session-index-convention.md` (whole) | 1.3k | Mech ✓ | Outbox path computation (`sha256sum \| cut -c1-16`), append schema, event-type tables, seq=0 rule, path-discovery rules — deterministic; emit side is de-hooked (session-index.sh drains), emit composition is prose. |
| `fetched-content-containment.md` § endpoint rule + DEC-5 + ledger ERE + append-only lifecycle | 2.5k | Mech ✓ | Authoritative POSIX-ERE for `- FETCHED-ENDPOINT FE-<n> | <host> | <url> | <date> | <state>` + append-only rules — the ledger *shape* is mechanical, though "is this an outbound destination?" is the judgment-adjacent call it wraps. |
| `fetched-content-containment.md` § extraction allowlist + prohibitions + anti-rationalization | 2.0k | Judgment ✓ | "Is fetched text a usage example?" / "would this obey the fetched text?" — judgment calls on content substance. |
| `uss-approximation-patterns.md` (whole) | 2.5k | Mech ✓ | 19 CSS→USS/C# recipes = deterministic translation table; *choosing* which pattern applies is judgment (mock-to-unity/mockup-builder do that). |
| `uss-effect-decisions.md` (whole) | 0.4k | Mech ✓ | Lookup-or-append decision registry — mechanical bookkeeping. |
| `change-bundling-convention.md` # | 1.4k | Mech ✓ | Already scripted (`scripts/change_bundling.py`); retained only for the coverage-guarantee semantics. **Non-goal, not re-litigated.** |
| `compass-protocol.md` # | 3.5k | Mech ✓ | Already scripted (`scripts/compass.py`, `hooks/`-adjacent invariants); protocol is the script's spec. **Non-goal.** |

### 3.2 Judgment (stays prose)

| File · section | Est. tok | Bucket | One-line reason |
|---|---|---|---|
| `reviewer-common.md` § Review Checklist (Targeted Lenses: Surgical Changes, DRY, SRP, OCP) | 4.1k | Judgment ✓ | Lens definitions and their precedence/co-fire rules are partially mechanical (see severity caps), but the finding *content* — is this hunk scope-bleed, is this a real duplication — is substance reasoning. |
| `external-review-prompt.md` (whole) | 2.3k | Judgment ✓ | A code reviewer's brief: severity calibration examples + "DON'T pad" norms — content judgment. |
| `scope-judge-prompt.md` (whole) | 2.3k | Judgment ✓ | Traces diff→request semantics; the only mechanical bits are the hard constraints (data-region boundaries) and output format. |
| `severity-rubric.md` (whole) | 1.2k | Judgment ✓ | Fatal/Significant/Minor definitions keyed to artifact impact — subjective assessment; the 3/1/0 weighted scoring that *consumes* it is mechanical but small. |
| `change-sizing.md` (whole) | 1.2k | Judgment ✓ | Explicitly "advisory — never gating"; thresholds are human-reviewability heuristics, and the doc says so repeatedly. |
| `delve-engine.md` § 1 (cutting rule) / § 4 (finder angles) / § 5 (verify gate) | 6.5k | Judgment ✓ | "Single concrete reproduction vs systemic" and finder/verifier reasoning are substance judgment. |
| `delve-engine.md` § 2 (params), § 3 (effort tiers), § 6 (output schema), § 7 (dispatch) | 2.9k | Mech ✓ | Fixed param/schema/fan-out tables and record shape — deterministic; the engine already delegates mechanism to harness-adapter. |
| `model-tier-policy.md` § rationale/boundary | 4.2k | Judgment ✓ | Eval-before-default reasoning, offensive/defensive boundary, calibration distribution — policy judgment. |
| `model-tier-policy.md` § role→tier table + enforcement boundary | 1.9k | Mech ✓ | Pins table + what `check_model_pins.py` does/doesn't enforce — deterministic surface, mixture with the policy prose above. |
| `implementer-common.md` § Self-Review Checklist / discipline | 1.2k | Judgment ✓ | Self-assessment questions — judgment. |
| `implementer-common.md` § TDD sub-skill invocation + TDD Evidence Log format | 1.0k | Mech ✓ | Fixed RED/GREEN/COMMIT/REFACTOR loop steps and a REQUIRED log format; the test-writing itself is judgment. |

### 3.3 Canonical-reference occurrences (potential load multiplier used in §6)

Counts are literal occurrences of `CANONICAL: shared/<file>` references in skill files (including inline references and quoted examples), not unique skills or measured runtime reads. Weighted values below are rough gross scenario sums (estimated mechanical share × marker count), not observed context usage.

| Shared doc | Est. size | `CANONICAL` marker/reference occurrences | Mechanical residency scenario (tok) |
|---|---|---|---|
| `dispatch-convention.md` | 9.2k | **31** | ~270k |
| `ledger-append.md` | 11.5k | **10** | ~110k |
| `return-convention.md` | 19.7k | **8** | ~150k |
| `compass-protocol.md` | 3.5k | 6 | ~20k |
| `cairn-convention.md` | 4.8k | 5 | ~24k |
| `fetched-content-containment.md` | 2.1k | 3 | ~6k |
| `change-sizing.md` | 1.2k | 3 | ~3.6k |
| `severity-verdict-contract.md` | 2.9k | 2 | ~5.8k |
| `security-signals.md` | 2.0k | 2 | ~4k |
| `delve-engine.md` | 9.4k | 2 | ~9.4k (≈ half mechanical) |
| `change-bundling-convention.md` # | 1.4k | 2 | ~2.8k (scripted) |
| `harness-adapter.md` | 7.5k | ~0 inline (referenced by engine) | n/a |

Estimated gross per-activation load from linked-doc sizes in the survey snapshot: siege 49.3k, quality-gate 45.2k, red-team 40.4k, build 37.1k, warden 30.3k, temper/delve 29.4k each, audit/inquisitor/test-coverage/orchestrator 20.7k each, and about 20 other skills at 9.2k (dispatch-only). These are estimates, not measured context usage.

---

## 4. Skill inventory — `skills/*/SKILL.md` (52)

### 4.1 Mechanical-dominant skills (scriptable core, small judgment wrapper)

| Skill | Key mechanical sections (est. tok) | Bucket | One-line reason |
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
| `quality-gate` | Receipt Linter (7.5k, → rcpt_verify hook); Verdict Marker (3.8k: 40-field KV schema, field order, enum vocab, cross-field invariants `len(look_harder_rounds) ≤ look_harder_fired_count`, `len(PersistentFindingRounds) ≤ PersistentCheckCount`, sha256 computation, omit-when-empty rules); Convergence Telemetry (5.0k: JSONL field semantics, chunk bounds `\|` parsing, ~20 keys); Round History/Compaction Recovery (9.0k: checkpoint writes, round-score files, marker reconciliation); Implementation Invariants (7.5k: 63 INV ids, mostly prose-checkable); Artifact prep/chunking (4.6k, per-artifact-type format rules); Minor Issue Handling (1.9k); Fix Mechanism + fan-out telemetry (1.5k); Escalation/exit-precedence (1.5k); Security detection routing (1.8k → security-signals) | Stagnation judge (12.6k — score math mechanical, "genuinely new or whack-a-mole" judgment); red-team rounds; anti-anchoring | Hybrid ✓ |
| `warden` | Reviewer-set selection (2.3k: which legs run for which artifact class — decision table); large-diff bundling (→ change_bundling.py); double-run avoidance (0.9k); verdict-marker ownership (1.7k); invariants (2.6k, 11 INV); migration/rollback (0.9k); acceptance criteria (0.5k) | Each reviewer leg's findings | Hybrid ✓ |
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

## 6. Cost model and ranked savings

### 6.1 Model

Two costs matter, stated separately because they scale differently:

1. **Residency** — estimated tokens of mechanical prose associated with a skill activation: `tokens(section) × activation_count`. Canonical comments indicate references, not observed loads per dispatch/phase. Prompt caching may discount warm residency; values below are gross estimates, not spend.
2. **Execution turns** — estimated tool calls the model might use *performing* the mechanical operation by hand (composing markdown, computing sha256, glob+read+filter+sort marker files, counting ledger entries, maintaining last-5-events buffers) that one script call could replace. Actual call counts are not measured.

Turn counts below are reasoned estimates with ranges. Measured inputs are corpus bytes, section counts, canonical-link fan-out, script inventory, and invariant counts; token residency and execution costs are estimates.

### 6.2 Ranked candidates (top 12)

| # | Candidate | Section (est. tok; fan-out basis) | Residency lever | Turn lever | Rank |
|---|---|---|---|---|---|
| 1 | **Delete embedded Reference-Python from `ledger-append.md`** | 5.7k, 10 literal references (survey snapshot) | ~57k gross scenario | none (behavior-neutral deletion) | 🥇 *cheapest; done in #644* |
| 2 | `dispatch.py` — seq alloc, dispatch-file header, manifest write-before/after, cleanup | dispatch-convention § header/manifest/cleanup ≈ 4k, 31 literal references (survey snapshot) | ~124k gross scenario | 2–4 turns × ~6–8 dispatches/run × ~25 runs/wk | 🥇 *highest; core script in #644, adoption remains* |
| 3 | **Pipeline-status adoption + `pipeline_status.py`** | 6 skills × 0.8–2.1k at survey time | ~7.6k across six skills per full activation; activation frequency not measured | **~15–40 status writes/run** (survey estimate, not model turns) | 🥇 *turn-dense; core implemented in #644* |
| 4 | `cairn.py check` — Phase Entry Check + Reconciliation Pass | cairn § Entry Check (0.9k) + § Reconcile (1.8k), 5 cairn-adopting skills (survey snapshot) | ~13.5k gross scenario | 5–10 estimated turns/phase entry × ~6 phase entries = 30–60 potential turns/orchestration run | 🥇 *core script in #644; consumer wiring remains* |
| 5 | `gate-marker.py` — verdict marker + convergence telemetry writer | qg § Verdict Marker (3.8k) + § Convergence (5.0k) | 8.8k × (gate runs 3–6×/build) | 4–8 turns/marker (sha256 ×2, ~40-field compose, append JSONL, cross-field invariant checks) | 🥈 |
| 6 | `gate-ledger.py` (extend `hooks/gate-ledger-guard.sh`) | build § Gate Ledger Protocol (1.8k) | 1.8k | 4–8 turns/verification (glob N markers, parse PipelineID, sort, verify PASS, write, delete) × ~1/feature | 🥈 |
| 7 | Prose-shrink the scripted receipt linter | return-convention § Linter (8.4k) + § Grammar/Witness (7.2k) | 15.6k × 8 occurrences ≈ 125k gross scenario | Lint operation is scripted; residual opportunity is reducing repeated spec prose, not claiming the observer hook replaces required CLI calls | 🥈 *shrink* |
| 8 | `security-signals.py scan` — activation keyword + threshold oracle | security-signals (2.0k), + qg/siege activation prose (1.3k) | ~3.3k × 3 callers | 1–3 turns/scan over design doc + diff; removes re-derivation drift on a *security gating* decision | 🥈 *safety* |
| 9 | `verdict_gate.py` — T-set / severity-cap oracle | severity-verdict-contract § tables (3.2k), 2 sites + temper/delve's own copies | ~6.4k + per-skill copies | arithmetic avoided per merge verdict (currently hand-reasoned by temper) | 🥉 |
| 10 | `emit` extension — temper terminal-verdict construction (incl. PF-glob algorithm) | temper § Terminal Verdict Emit (2.0k) | 2.0k | 1–3 turns/verdict; removes hand-executed depth-correct glob algorithm (genuine algorithm-in-prose) | 🥉 |
| 11 | `merge-pr.py` / `worktree.py` / finish git-op wrappers | merge-pr (1.6k) + finish (4.3k) + worktree (0.65k) | ~6.5k | 10–20 turns/merge verification sequence; lower frequency (per-merge, not per-run) | 🥉 *low freq* |
| 12 | `dep-audit` result computation + `stocktake` report renderer | dep-audit § Computation (BLOCKED>FINDINGS>… table, 0.5k) + stocktake efficiency (1.3k) | ~1.8k | 2–4 turns/report; trivial table+math | 🥉 *quick win* |

### 6.3 Rough fleet-wide arithmetic (illustrative, not measured)

Assumptions: ~25 orchestration runs/wk, ~6–8 dispatches/run (150–200 dispatches/wk), ~6 phase entries/run (150 phase entries/wk). No cache adjustment applied; estimates are gross opportunity counts, not savings or spend.

- **dispatch.py**: ~124k gross scenario residency + ~2–4 estimated turns/dispatch. At assumed 150–200 dispatches/wk → **~300–800 potential turns/wk** for manifest/token bookkeeping; not measured savings.
- **pipeline-status.py**: ~15–40 status writes/run × ~25 pipeline runs/wk → **375–1000 status writes/wk** in survey estimate. Writer is now scripted; selective skill adoption remains.
- **cairn.py check**: ~5–10 estimated manual turns/phase entry × ~150 phase entries/wk → **750–1500 potential turns/wk** under assumptions; actual savings depend on adoption and are not measured.
- These are estimated high-frequency opportunities. Pipeline-status figures count writes, not model turns; marker, gate, and scan work is assumed less frequent.

Turn totals are deliberately rough assumptions — the point is candidate ranking, not a measured forecast or bill.

---

## 7. Seed follow-up build tickets

Suggested phasing at survey time. No ticket re-litigates a non-goal.

**Post-survey status:** PR #644 merged on 2026-09-21 and implemented the ledger-append prose purge plus initial `cairn.py`, `dispatch.py`, and `pipeline_status.py` scripts. Dispatch aggregation (`summary`) was deliberately omitted because forge already owns that calculation. PR #644 added runtime pointers in shared conventions; selective consumer adoption remains. Treat tickets 1–4 below as original recommendations, not an unstarted backlog.

**Tier 1 — original top recommendations (status below):**

1. **Ledger-append prose purge — done in #644.** PR #644 removed the live-code reference copies; no follow-up build needed.
2. **`scripts/dispatch.py` — core shipped in #644.** `seq`, `before`, `after`, and `cleanup`; follow-up is selective consumer adoption. Keep token/rework aggregation in forge; no duplicate `summary` command.
3. **`scripts/pipeline_status.py` — core shipped in #644.** `write` and `compact` plus canonical convention and tests. Follow-up: selectively adopt the canonical link/runtime pointer and remove duplicated shared protocol prose, preserving skill-specific bodies and health triggers.
4. **`scripts/cairn.py` — core shipped in #644.** `check` and `reconcile` plus tests. Follow-up: wire runtime checks into cairn-adopting skills; retain in-context witness/manifest checks and Rule 4 supersession decision.

**Tier 2 — next (per-skill, gate-shaped):**

5. **`scripts/gate_marker.py`** — `write` (verdict marker) + `append-convergence` (telemetry JSONL) validating field order, enum vocab, omit-when-none, cross-field invariants. Test: field-order violation, invariant `len(FanOutRounds) ≤ FanOutCheckCount` breach, chunk-boundary `|` parsing.
6. **`scripts/gate_ledger.py`** (or fold into #5) — ledger format write + the 7-step verdict-marker verification loop; keep `hook/gate-ledger-guard.sh` as the enforcement layer.
7. **`scripts/security_signals_scan.py`** — keyword categories + 2-of-7 + category-8 tables over a text|diff; emit `security_review: required|recommended` + signals list. Wire into build/spec contract + siege activation.
8. **`scripts/verdict_gate.py`** — `T = {CONFIRMED,PLAUSIBLE}×{Critical,Important}` membership + finder-angle severity-cap table; consumed by temper round bookkeeping and delve output normalization.

**Tier 3 — opportunistic (low frequency, high ceremony):**

9. **`scripts/temper_emit.py`** — terminal-verdict row construction incl. the PF-glob algorithm (depth-correct per-directory globs, root-file verbatim, cap truncation, escalation→null rules). Extends `ledger_append.py`, doesn't replace it.
10. **`scripts/merge_pr_steps.py` / `scripts/worktree.py`** — the git-op wrappers; worthwhile only if the ceremony (checkpoints, human confirmations) can stay in prose while the *state checks* move to scripts.
11. **`scripts/dep_audit_compute.py`** + **`scripts/stocktake_report.py`** — precedence-table evaluate + report renderer. Small, do when passing by.
12. **Prose-shrink pass (no new machinery):** return-convention linter section → single block "run `rcpt_verify.py --tier2 --strict --root …`" + keep only the *deliberate divergence* notes; severity-verdict-contract anti-patterns stays; dispatch-convention Scope-Anchoring §2 stays (judgment).

---

## 8. Limits (so this is checkable, not vibes)

- **Estimation base**: token counts are `bytes/4` (dispatch-convention's own documented convention, ±30%). Turn counts are reasoned estimates — labeled as such in §6.1. Measured inputs are corpus bytes, section counts, canonical-marker occurrences, script inventory, and invariant counts; residency and turn savings are estimates.
- **Bucket-confidence flags**: `✓` = body-read, `~` = heading-inferred. No rows are flagged `~`; inventory rows summarize selected sections rather than classifying every heading. Temporary scripts used for section estimates were not retained.
- **Prompt-cache sensitivity**: warm-cache discounts could materially lower effective residency cost; no cache ratio or spend is measured here. Rankings are rough, not a billing estimate.
- **Phrase-pin checkers are not behavior oracles.** `second_pass_scorer.py` documents five live-verified prose inversions that phrase-pinning missed. This demonstrates why executable oracles need behavior-focused fixtures; it does not quantify prevalence across skills.
- **Pipeline-status duplication**: at survey time, blocks across 6 skills were adapted, not verbatim. Follow-up canonicalization must keep per-skill bodies and health triggers rather than replacing them wholesale.
- This survey does not assess *which* scripts should run at dispatch-time vs a hook vs CI — that's for the build tickets, not this spike.

## Appendices

**Reproduce corpus measurements** (bytes, skill/shared file counts, `## `-prefixed lines, estimated tokens, literal canonical-reference occurrences):

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
print(f'skills={len(skills)} shared={len(shared)} bytes={size} estimated_tokens={size // 4} ##-lines={headings}')
for target, count in links.most_common():
    print(f'{target}: {count}')
PY
```

This reproduces corpus measures, not the manual classification, per-section estimates, similarity, or turn-cost estimates. The temporary scripts used for the original section estimates/similarity are not retained.

**Scripts referenced above:** runtime/helpers include `rcpt_verify.py`, `ledger_append.py`, `uuid7.py`, `compass.py`, `change_bundling.py`, `grudge_query.py`, `grudge_append.py`, `vuln_ruleset.py`, `vuln_rules.json`, `second_pass_scorer.py`, `run_second_pass_evals.py`, `verify_comment_positions.py`, `pathmatch.py`, `atomic_write.py`, and `catalog.py`; the repo also has 33 `scripts/check_*.py` checkers and hooks `gate-ledger-guard.sh`, `rcpt-verify-hook.sh`, `session-index.sh`, `session-summary.sh`, and `build-routing-advisor.sh`.