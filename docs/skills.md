# Skills

The full Crucible skill catalog. Skills are the unit of methodology — each one encodes a specific workflow (TDD, quality gates, debugging, etc.) that the agent follows when invoked. See [architecture.md](architecture.md) for how the orchestrator skills (build, debugging, spec, migrate) chain these together.

<!-- CATALOG:START -->
## Core Pipeline

| Skill | Description |
|---|---|
| **build** | End-to-end development pipeline: interactive design, autonomous planning with quality gates, team-based execution with per-task code and test review. Live pipeline status file with health indicators for ambient awareness. Shadow git checkpoints at 7 pipeline boundaries for structured rollback on regression. Structured Compression State Blocks for resilient compaction recovery. Pipeline-active markers enable automatic crash detection and resume via `/replay`. Token efficiency tracking enriches dispatch manifests for cost visibility. Implementers record out-of-scope observations in a "Noticed But Not Touching" section that the orchestrator reconciles into a per-pipeline `docs/plans/*-noticed.md` file, preserving scope discipline without losing signal. One command, idea to completion. |
| **spec** | Autonomous epic-to-spec pipeline. Takes a GitHub epic with child tickets and produces design docs, implementation plans, and machine-readable contracts (API surface, checkable/testable invariants) for each ticket without human interaction. Dispatches /recon per ticket for investigation context and /assay for architectural decisions with confidence-based autonomous routing. Contract-based handoff to build. |
| **design** | Interactive design refinement with quality gate on completed designs. Dispatches /recon at Phase 2 start for structural context, then explores dimensions via Domain Researcher + Impact Analyst. Deep Dive dimensions use /assay for structured evaluation with constraint_fit scoring, kill criteria, and confidence grounded by recon's Open Questions. Produces a design doc. |
| **planning** | Implementation plan writing with quality gate on completed plans. Bite-sized tasks with exact file paths, complete code, and expected outputs. |
| **recon** | Codebase investigation with layered output. Produces a core Investigation Brief (structure, patterns, scope, prior art) plus optional depth modules (impact-analysis, consumer-registry, friction-scan, subsystem-manifest, diagnostic-context, execution-readiness). Dispatches parallel scouts, synthesizes findings, and feeds cartographer. Called by design, spec, migrate, and audit; also usable standalone before any task requiring codebase understanding. |
| **replay** | Pipeline crash recovery and A/B experimentation. Reads dispatch manifests, partitions into completed/incomplete at phase boundaries, restores shadow git checkpoints, reconstructs orchestrator state from disk, and re-dispatches from the first incomplete entry. Three modes: resume (automatic crash recovery), A/B (`--mutate` to swap dispatch templates and compare outcomes), and dry-run (verify resume feasibility without executing). Cross-session capable — new conversation, old manifest, no shared context needed. |
| **assay** | Recon-informed approach evaluator. Weighs competing options against codebase constraints with decision-type-adaptive scoring (architecture, strategy, diagnosis, optimization). Returns structured JSON Assay Reports with recommendations, alternatives with kill criteria, confidence scoring, and evidence grounding. Called by design, spec, and migrate. |

## Implementation

| Skill | Description |
|---|---|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **source-driven-development** | Enforces a Detect → Fetch → Implement → Cite loop when touching third-party APIs. Consults official docs (not Stack Overflow, Medium, or training-data recall), classifies WebFetch results as L4 Verify-first per the trust hierarchy, and records a `Source: <url> (YYYY-MM-DD)` citation at the call site so doc drift is detectable later. Auto-dispatched by build when an implementer touches external frameworks above a LOC threshold. |
| **checkpoint** | Shadow git checkpoint system for pipeline rollback. Snapshots working directory state at pipeline boundaries using isolated shadow repositories (GIT_DIR/GIT_WORK_TREE). Supports create, list, restore (full directory or single file), deduplication, eviction (50 max), and pre-restore safety snapshots. Consumed by build, quality-gate, and debugging. |
| **worktree** | Create isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Dispatch independent tasks to parallel subagents to work without shared state or sequential dependencies. |
| **adversarial-tester** | Reads completed implementation and writes up to 5 tests designed to expose unknown failure modes. Targets edge cases, boundary conditions, and runtime behavior the implementer didn't anticipate. |
| **inquisitor** | Full-feature cross-component adversarial testing. Runs 5 parallel adversarial dimensions (wiring, integration, edge cases, state/lifecycle, regression) against the complete implementation diff to find bugs that per-task testing misses. |
| **migrate** | Autonomous migration planning and execution. Takes a migration target (framework upgrade, API version bump, dependency major version, deprecation removal) and produces a phased migration plan with compatibility verification. Optionally executes via build's refactor mode. |

## Quality & Audit

| Skill | Description |
|---|---|
| **delve** | Standalone instance-bug reviewer. Drives the shared `delve-engine` once — a parallel finder fan-out (line-by-line, removed-behavior, cross-file, plus four capped non-gating quality angles) followed by a one-verifier-per-candidate verify gate — over a diff, PR, or path, and prints ranked, verified defects with reproductions. Report-only: no merge verdict, no fix loop (`--fix` edits the working tree, `--comment` posts to the forge, both opt-in). Forge-agnostic. One of exactly two direct drivers of `delve-engine` (the other is temper). Owns one-reproduction instance bugs; systemic patterns are audit's, exploration is recon/prospector's. |
| **audit** | Adversarial **systemic** review of code subsystems or non-code artifacts (design docs, plans, concepts). Code path is systemic-only: recurring patterns, structural properties, and absences with no single reproduction — instance bugs route to `/delve` via the opt-in `--bugs` sub-path; complexity/hotspots to `/prospector`. Dispatches 4 parallel lenses adapted to the artifact type (code: architecture, consistency, robustness, test-health) plus blind-spots, synthesizes with causal compounding analysis, cross-references existing issues, and files in the user's tracker. Opt-in `--drift intent=<path>` adds a divergence-from-intent section. Find-and-report only. |
| **siege** | Security audit of design docs, implementation plans, and code. Dispatches 3/4/6 parallel Opus agents (scope-based) across attacker perspectives (Boundary Attacker, Insider Threat, Infrastructure Prober, Betrayed Consumer, Fresh Attacker, Chain Analyst), iterates until zero Critical + zero High findings, and maintains a persistent threat model. Steel-mans before attacking. Hardened detection dimensions include cross-query authz predicate consistency, non-HTML sink taint flow (Markdown/SARIF/logs), external-trigger DoS enumeration with per-stack grep anchors, and parser-library hardening checks. |
| **consensus** | Multi-model consensus for high-stakes quality decisions. Opt-in MCP-based system that dispatches prompts to multiple LLM providers in parallel and synthesizes responses. Enhances quality-gate (stagnation verdicts, periodic red-team rounds) and design (Challenger step) when available. Transparent degradation — changes nothing when absent. |
| **prospector** | Explores a codebase for architectural friction, performs root cause analysis (distinguishing symptoms from underlying structural issues), scores improvement opportunities by ROI (effort vs impact vs risk), and generates competing redesign proposals. Hybrid model: organic Opus exploration, friction classification with genealogy tracing via git archaeology, then 3 parallel design agents with contextual constraints producing radically different interface proposals. Output feeds into build (refactor mode) or files as tracker issues. |
| **quality-gate** | Iterative red-teaming of any artifact (design, plan, code, hypothesis, mockup). Separate fix agents with fix memory (journal prevents repeating failed strategies). Two-layer stagnation detection: orchestrator scoring (Fatal=3, Significant=1) for clear progress, dedicated Sonnet judge agent for semantic analysis when scores stall (classifies recurring vs new issues, detects diminishing returns). Shadow git checkpoints before code-artifact fix rounds with restore-on-regression option. Compaction recovery with Compression State Blocks and persistent scratch directories. Progress notifications at rounds 5/8/11/14, 15-round safety limit. |
| **red-team** | Adversarial review engine with steel-man-then-kill protocol — every finding must articulate the strongest defense before demolishing it. Mandatory coverage sweep across 6 attack dimensions with a required second pass. Severity anchoring with bias check. Dispatches fresh Devil's Advocate reviewers per round. Dual-mode: single-pass when called by quality-gate (quality-gate owns the loop), full iterative loop when called directly. |
| **test-coverage** | Post-change test suite audit. Checks whether existing tests need updating (stale assertions, misleading descriptions), deletion (removed code paths), or flagging (coincidence tests that pass by luck). Audit agent + fix agent with revert-on-failure. Split audit for large scopes. Technology-agnostic. |
| **temper** | Iterative code-diff review loop for production readiness. Drives the shared `delve-engine` (bug-angle subset, high effort) to enumerate a tracked set `T` of gating findings, then runs fresh-eyes fix-verification rounds until every member is resolved or discharged and no new gating finding entered — convergence is the resolution status of an enumerated set, never a cross-round count. Forge-agnostic (GitHub / GitLab / Bitbucket / self-hosted) on a PR id or `<base>..<head>` range; optional forge post-back. Recommends test-coverage audit after behavioral changes. Renamed from `/code-review` (2026-05-17). One of exactly two direct drivers of `delve-engine` (the other is delve). |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Branch completion workflow — merge, PR, or cleanup. Runs test alignment audit and red-team before presenting options. Pre-push validation gate with toolchain-auto-detection + ecosystem matrix (TS/Node, Rust, Python, Go, .NET, Ruby, Java/Kotlin) and strict exit-code discipline. Post-push CI monitoring with `gh pr checks --watch` + allow-list bucket assertion — blocks on red PRs and disambiguates the no-CI-configured case. |
| **innovate** | Divergent creativity injection. Proposes the single most impactful addition before quality gate review. |
| **dependency-audit** | Ecosystem-appropriate dependency vulnerability audit. Walks the project for package.json, Cargo.toml, requirements.txt, pyproject.toml manifests and runs npm/cargo/pip-audit. Produces a structured supply-chain signal with normalized severities. Used by build alongside quality-gate; can also be invoked standalone. Triggers on /dependency-audit, 'audit dependencies', 'scan vulnerabilities', 'check CVEs'. |

## Debugging

| Skill | Description |
|---|---|
| **debugging** | Orchestrated debugging with hypothesis red-teaming, domain detection, persistent session state with compaction recovery, commit strategy (WIP commits on all outcomes), stagnation ownership split with quality-gate, test suite audit, and post-fix quality gate with test gap writer (dedup-aware, auto-retry on failures). Shadow git checkpoints before fix cycles, sibling fixes, and quality gate for structured rollback. Phase 4.5 "Where Else?" blast radius scan finds and fixes sibling locations with the same bug pattern, then persists the defect signature in cartographer for future proactive prevention. |

## Knowledge & Learning

| Skill | Description |
|---|---|
| **forge** | Self-improving retrospective system. Post-task retrospectives classify deviations and extract lessons. Auto-detects skill-worthy workflows via 5 trigger heuristics and proposes extraction (never auto-creates). Opt-in trajectory capture records skill invocations as structured JSONL for eval generation. Pre-task feed-forward surfaces relevant warnings and recent failure patterns. Periodic mutation analysis proposes concrete skill edits for human review. |
| **project-init** | Eliminates cold-start penalty by deep-scanning the current repo and discovering cross-repo topology. Produces structural cartographer maps and a topology directory before the first real task. |
| **grudge** | The Book of Grudges — cross-session bug graveyard. Every fixed bug is recorded as a structured "grudge"; before touching code, skills query the grudgebook for the files in scope and surface past regressions as forced "DO NOT REPEAT" context. Read mode (pre-flight) and write mode (on bug resolution / fix(*) PR). Machine-local, per-repo, never committed. Triggers on /grudge, "check grudges", "record a grudge", "any past bugs here", "regression oracle", "bug graveyard". |
| **compass** | Read or update the per-repo arc-state file (docs/compass.md). Tracks current arc, last meaningful commit, open loops, next move, and don't-forget items. Auto-maintained by build, merge-pr, finish; read by getting-started. Use "compass read" to inspect project state, "compass update" to set a field, "compass doctor" to validate, "compass compress" when at cap. Triggers on "compass", "current arc", "project state", "what am I working on", "arc state", "where was I". |

## Utilities

| Skill | Description |
|---|---|
| **distill** | Convert heavy document formats (PDF, Word, Excel, PowerPoint, and 10+ others) to token-efficient Markdown/CSV. Three conversion tiers: Pandoc-native (9 formats), PDF (pdftotext + Claude structuring), Python venv (pptx via python-pptx, xlsx via openpyxl). Structurally-aware digest pass compresses to 20-30% of token count. Pre-flight safety checks (zip bomb, PDF attachments, encoding). Graceful degradation when tools are missing. |
| **recall** | Query session history from the session activity index. Four modes: full summary (no args), keyword search, type filter (errors/decisions/edits/commits/tests/phases), and time range (last N minutes/hours). Graceful degradation when no session index exists. Consumed by compaction recovery steps in build, debugging, and spec. |

## Maintenance & Meta

| Skill | Description |
|---|---|
| **stocktake** | Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan, full evaluation, or efficiency report modes. Efficiency mode reads chronicle signals to produce per-skill token cost breakdowns, dispatch tier distribution, and structural baseline comparisons. |
| **merge-pr** | PR merge workflow with full safety scaffolding: CI verification, working-tree check, repo safety scan, local test validation, merge, post-merge CI monitoring, and branch cleanup. Stops on red CI or unsafe state rather than forcing through. |
| **skill-creator** | Create, edit, and evaluate skills. Run A/B evals to measure skill performance with variance analysis. Optimize skill descriptions for better triggering accuracy. |
| **getting-started** | Skill discovery and invocation discipline. Objective test for when skills apply, scoped exceptions for pure information retrieval, and anti-rationalization red flags. Includes the five-level trust hierarchy (L1 Trusted → L5 Untrusted) framework for resolving conflicts between loaded content from different sources. |
| **handoff** | Write a handoff doc for the next session — either continuing the current arc, or proposing the natural next pickup if the current arc is wrapping up. |
| **ledger** | Render the Crucible calibration ledger weekly report — the honest "Crucible caught N silent bugs" headline, verdict breakdown, per-skill severity rates, and the inflation detector. Triggers on "/ledger", "weekly report", "weekly ledger", "caught N", "quality ledger", "calibration report", "render the ledger". |
| **calibration-reconcile** | Reconcile the Crucible calibration ledger — walk merged fix/hotfix branches to falsify the originating gating-verdicts, compute per-skill Brier calibration scores, and append a falsification log. Triggers on "/calibration-reconcile", "reconcile ledger", "reconcile calibration", "falsify verdicts", "brier score", "calibration reconcile", "compute brier". |
| **workshop** | Tour of the Crucible workshop — the headline orchestrators users invoke directly. Use when the user asks "what skills are available?", "where do I start?", "what should I use for X?", "give me a tour of Crucible", "what are the main commands?", or any onboarding-style question. Also use after onboarding a new user or when someone needs to pick the right tool for a specific task. |

## Unity UI (Domain-Specific)

These skills are for [Unity UI Toolkit](https://docs.unity3d.com/Manual/UIElements.html) projects. All other Crucible skills are language- and framework-agnostic.

| Skill | Description |
|---|---|
| **mockup-builder** | Creates HTML mockups constrained to Theme.uss variables, flexbox-only layout, and BEM naming. Designed for direct translation to Unity UI Toolkit with player-customizable theming. |
| **mock-to-unity** | Translates mockups into Unity UI Toolkit code via structured CSS-to-USS mapping, layered implementation, and per-layer self-verification. Bakes in Unity 6 USS bug workarounds. |
| **ui-verify** | Compares implemented UI against source mockup using screenshots or code-level structural audit. Produces structured delta reports with [PASS]/[FAIL]/[WARN] per category. |

## Eval & Maintenance (internal)

| Skill | Description |
|---|---|
| **cartographer-skill** | Use when exploring unfamiliar code and want to persist what you learn, when starting a task and want to consult known codebase structure, or when collaborators need module-specific context for implementation or review |
| **temper-eval-collect** | Live-dispatch phase of temper eval harness. Reads stage-manifest.json from a pre-staged dispatch dir; fans Task-tool reviewer dispatches in parallel (max 6); writes per-seq result files; exits. Single bounded session. Pairs with `python -m skills.temper.evals.run_evals stage` and `score`. |
| **temper-eval-calibrate** | Wrapper skill that runs k iterations of (stage → collect-behavior → score) for #290 calibration sweeps. Replaces bash for-loops that cannot invoke session skills. Default k=3. Inlines collect-dispatch behavior per iteration. Idempotent resume via per-iteration sentinels under skills/temper/evals/.calibrate-state/. |
| **skill-selection-evals** | Eval-only skill for measuring skill routing accuracy. Not invoked directly — contains selection evals that test whether the agent picks the correct skill for a given prompt. |

<!-- CATALOG:END -->
