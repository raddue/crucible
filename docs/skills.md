# Skills

The full Crucible skill catalog. Skills are the unit of methodology — each one encodes a specific workflow (TDD, quality gates, debugging, etc.) that the agent follows when invoked. See [architecture.md](architecture.md) for how the orchestrator skills (build, debugging, spec, migrate) chain these together.

<!-- CATALOG:START -->
## Core Pipeline

| Skill | Description |
|---|---|
| **build** | End-to-end development pipeline: interactive design, autonomous planning with quality gates, team-based execution with per-task code and test review. Live pipeline status file with health indicators for ambient awareness. Shadow git checkpoints at 7 pipeline boundaries for structured rollback on regression. Structured Compression State Blocks for resilient compaction recovery. Pipeline-active markers enable automatic crash detection and resume via `/replay`. Token efficiency tracking enriches dispatch manifests for cost visibility. Implementers record out-of-scope observations in a "Noticed But Not Touching" section that the orchestrator reconciles into a per-pipeline `docs/plans/*-noticed.md` file, preserving scope discipline without losing signal. One command, idea to completion. Migration mode (absorbed `migrate`, #720) plans and executes framework upgrades, API version bumps, dependency major versions and deprecation removals as a phased migration plan with compatibility verification, consumer waves and rollback points, running each phase through the pipeline. |
| **spec** | Autonomous epic-to-spec pipeline. Takes a GitHub epic with child tickets and produces design docs, implementation plans, and machine-readable contracts (API surface, checkable/testable invariants) for each ticket without human interaction. Dispatches /recon per ticket for investigation context and design's approach-evaluation subflow for architectural decisions with confidence-based autonomous routing. Contract-based handoff to build. |
| **design** | Interactive design refinement with quality gate on completed designs. Dispatches /recon at Phase 2 start for structural context, then explores dimensions via Domain Researcher + Impact Analyst. Deep Dive dimensions use its approach-evaluation subflow for constraint_fit scoring, kill criteria, and confidence grounded by recon's Open Questions. Its innovation pass proposes one addition before review; decision-record workflow drafts durable ADRs. Produces a design doc. |
| **planning** | Implementation plan writing with quality gate on completed plans. Bite-sized tasks with exact file paths, complete code, and expected outputs. |
| **recon** | Codebase investigation with layered output. Produces a core Investigation Brief (structure, patterns, scope, prior art) plus optional depth modules (impact-analysis, consumer-registry, friction-scan, subsystem-manifest, diagnostic-context, execution-readiness). Dispatches parallel scouts, synthesizes findings, and feeds cartographer. Called by design, spec, migrate, and audit; also usable standalone before any task requiring codebase understanding. |
| **replay** | Pipeline crash recovery and A/B experimentation. Reads dispatch manifests, partitions into completed/incomplete at phase boundaries, restores shadow git checkpoints, reconstructs orchestrator state from disk, and re-dispatches from the first incomplete entry. Three modes: resume (automatic crash recovery), A/B (`--mutate` to swap dispatch templates and compare outcomes), and dry-run (verify resume feasibility without executing). Cross-session capable — new conversation, old manifest, no shared context needed. |

## Implementation

| Skill | Description |
|---|---|
| **test-driven-development** | Red-green-refactor discipline. Write failing test first, minimal implementation, refactor. Enforced rigorously with rationalization counters. |
| **source-driven-development** | Enforces a Detect → Fetch → Implement → Cite loop when touching third-party APIs. Consults official docs (not Stack Overflow, Medium, or training-data recall), classifies WebFetch results as L4 Verify-first per the trust hierarchy, and records a `Source: <url> (YYYY-MM-DD)` citation at the call site so doc drift is detectable later. Auto-dispatched by build when an implementer touches external frameworks above a LOC threshold. |
| **checkpoint** | Shadow git checkpoint system for pipeline rollback. Snapshots working directory state at pipeline boundaries using isolated shadow repositories (GIT_DIR/GIT_WORK_TREE). Supports create, list, restore (full directory or single file), deduplication, eviction (50 max), and pre-restore safety snapshots. Consumed by build, quality-gate, and debugging. |
| **worktree** | Create isolated git worktrees for feature work with smart directory selection and safety verification. |
| **parallel** | Dispatch independent tasks to parallel subagents to work without shared state or sequential dependencies. |
| **inquisitor** | Writes up to 5 adversarial tests for one task's runtime failure modes, or runs 5 parallel dimensions (wiring, integration, edge cases, state/lifecycle, regression) against a full-feature diff. Triggers on 'break it', 'adversarial test', 'stress test implementation', 'find weaknesses', and cross-component bug-hunting. |

## Quality & Audit

| Skill | Description |
|---|---|
| **delve** | Standalone instance-bug reviewer. Drives the shared `delve-engine` once — a parallel finder fan-out (line-by-line, removed-behavior, cross-file, plus four capped non-gating quality angles) followed by a one-verifier-per-candidate verify gate — over a diff, PR, or path, and prints ranked, verified defects with reproductions. Report-only: no merge verdict, no fix loop (`--fix` edits the working tree, `--comment` posts to the forge, both opt-in). Forge-agnostic. One of exactly two direct drivers of `delve-engine` (the other is temper). Owns one-reproduction instance bugs; systemic patterns are audit's, exploration is recon/prospector's. |
| **audit** | Adversarial **systemic** review of code subsystems or non-code artifacts (design docs, plans, concepts). Code path is systemic-only: recurring patterns, structural properties, and absences with no single reproduction — instance bugs route to `/delve` via the opt-in `--bugs` sub-path; complexity/hotspots to `/prospector`. Dispatches 4 parallel lenses adapted to the artifact type (code: architecture, consistency, robustness, test-health) plus blind-spots, synthesizes with causal compounding analysis, cross-references existing issues, and files in the user's tracker. Opt-in `--drift intent=<path>` adds a divergence-from-intent section. Find-and-report only. |
| **siege** | Security audit of design docs, implementation plans, and code. Dispatches 3/4/6 parallel Opus agents (scope-based) across attacker perspectives (Boundary Attacker, Insider Threat, Infrastructure Prober, Betrayed Consumer, Fresh Attacker, Chain Analyst), iterates until zero Critical + zero High findings, and maintains a persistent threat model. Steel-mans before attacking. Hardened detection dimensions include cross-query authz predicate consistency, non-HTML sink taint flow (Markdown/SARIF/logs), external-trigger DoS enumeration with per-stack grep anchors, and parser-library hardening checks. |
| **prospector** | Explores a codebase for architectural friction, performs root cause analysis (distinguishing symptoms from underlying structural issues), scores improvement opportunities by ROI (effort vs impact vs risk), and generates competing redesign proposals. Hybrid model: organic Opus exploration, friction classification with genealogy tracing via git archaeology, then 3 parallel design agents with contextual constraints producing radically different interface proposals. Output feeds into build (refactor mode) or files as tracker issues. |
| **quality-gate** | Iterative adversarial gate with fresh red-team reviewers, fix verification and stagnation detection. Standalone red-team mode preserves the direct full loop and single-pass reviewer semantics; optional multi-model consensus supports review and stagnation judgment. Dependency-audit preflight scans npm, Cargo and Python manifests as an independent supply-chain signal, also runnable alone. |
| **test-coverage** | Post-change test suite audit. Checks whether existing tests need updating (stale assertions, misleading descriptions), deletion (removed code paths), or flagging (coincidence tests that pass by luck). Audit agent + fix agent with revert-on-failure. Split audit for large scopes. Technology-agnostic. |
| **temper** | Iterative code-diff review loop for production readiness. Drives the shared `delve-engine` (bug-angle subset, high effort) to enumerate a tracked set `T` of gating findings, then runs fresh-eyes fix-verification rounds until every member is resolved or discharged and no new gating finding entered — convergence is the resolution status of an enumerated set, never a cross-round count. Forge-agnostic (GitHub / GitLab / Bitbucket / self-hosted) on a PR id or `<base>..<head>` range; optional forge post-back. Recommends test-coverage audit after behavioral changes. Renamed from `/code-review` (2026-05-17). One of exactly two direct drivers of `delve-engine` (the other is delve). |
| **review-feedback** | Process code review feedback with technical rigor. Requires verification, not blind implementation. |
| **verify** | Verify work before claiming completion. Evidence-before-claims discipline — run verification commands and confirm output before making success claims. |
| **finish** | Guides completed work through test and review gates, then presents merge, PR, keep, or discard choices. For explicit PR merges, verifies CI, working-tree and repository safety, local tests, post-merge health, and cleanup. |
| **warden** | Consolidated pre-push review gate — runs the full reviewer set (temper, delve, red-team, plus siege/inquisitor when the diff warrants) as one gate and emits a single PASS/BLOCKED verdict. Use when you want the *complete* pre-push bar in one call — "gate this before I push", "run the full review gate", "run all the reviewers", "warden". NOT for a single-reviewer pass: a fresh-eyes code review stays with temper, red-teaming a design/plan stays with quality-gate, a bug-hunt on a diff stays with delve. |

## Debugging

| Skill | Description |
|---|---|
| **debugging** | Orchestrated debugging with hypothesis red-teaming, domain detection, persistent session state with compaction recovery, commit strategy (WIP commits on all outcomes), stagnation ownership split with quality-gate, test suite audit, and post-fix quality gate with test gap writer (dedup-aware, auto-retry on failures). Shadow git checkpoints before fix cycles, sibling fixes, and quality gate for structured rollback. Phase 4.5 "Where Else?" blast radius scan finds and fixes sibling locations with the same bug pattern, then persists the defect signature in cartographer for future proactive prevention. |

## Knowledge & Learning

| Skill | Description |
|---|---|
| **project-init** | Eliminates cold-start penalty by deep-scanning the current repo and discovering cross-repo topology. Produces structural cartographer maps and a topology directory before the first real task. |
| **grudge** | The Book of Grudges — cross-session bug graveyard. Every fixed bug is recorded as a structured "grudge"; before touching code, skills query the grudgebook for the files in scope and surface past regressions as forced "DO NOT REPEAT" context. Read mode (pre-flight) and write mode (on bug resolution / fix(*) PR). Machine-local, per-repo, never committed. Triggers on /grudge, "check grudges", "record a grudge", "any past bugs here", "regression oracle", "bug graveyard". |

## Utilities

| Skill | Description |
|---|---|
| **distill** | Convert heavy document formats (PDF, Word, Excel, PowerPoint, and 10+ others) to token-efficient Markdown/CSV. Three conversion tiers: Pandoc-native (9 formats), PDF (pdftotext + Claude structuring), Python venv (pptx via python-pptx, xlsx via openpyxl). Structurally-aware digest pass compresses to 20-30% of token count. Pre-flight safety checks (zip bomb, PDF attachments, encoding). Graceful degradation when tools are missing. |

## Maintenance & Meta

| Skill | Description |
|---|---|
| **stocktake** | Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan, full evaluation, or efficiency report modes. Efficiency mode reads chronicle signals to produce per-skill token cost breakdowns, dispatch tier distribution, and structural baseline comparisons. |
| **anvil** | Create new skills, modify and improve existing skills, and measure skill performance (formerly skill-creator). Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy. |
| **getting-started** | Skill discovery and invocation discipline. Objective test for when skills apply, scoped exceptions for pure information retrieval, and anti-rationalization red flags. Includes the five-level trust hierarchy (L1 Trusted → L5 Untrusted) framework for resolving conflicts between loaded content from different sources. Also the session-continuity hub: bundled flat references for compass arc state (`docs/compass.md` read/update/doctor/compress), forge retrospectives / feed-forward / 10+-retro mutation proposals, handoff docs, recall session-history queries, and the workshop catalog tour. |
| **orchestrator** | Use when the user wants a Claude Code session inside Herdr (a terminal multiplexer for coding agents) to act as the "team boss" driving multiple parallel Crucible worker sessions — spinning workers up, checking on them, retiring them, and reporting consolidated status. Trigger on "orchestrator", "team boss", "coordinate sessions", "spin up workers", "Herdr orchestrator", or any request to fan Crucible work out across several live Herdr sessions rather than do it all in this one session. Requires HERDR_ENV=1 — if this session isn't inside Herdr, say so and stop rather than trying to substitute a different fan-out mechanism (that's `batch`/`convoy`'s job, not this skill's). |

## Eval & Maintenance (internal)

| Skill | Description |
|---|---|
| **cartographer-skill** | Use when exploring unfamiliar code and want to persist what you learn, when starting a task and want to consult known codebase structure, or when collaborators need module-specific context for implementation or review |
| **temper-eval-collect** | Live-dispatch phase of temper eval harness. Reads stage-manifest.json from a pre-staged dispatch dir; fans Task-tool reviewer dispatches in parallel (max 6); writes per-seq result files; exits. Single bounded session. Pairs with `python -m skills.temper.evals.run_evals stage` and `score`. |
| **temper-eval-calibrate** | Wrapper skill that runs k iterations of (stage → collect-behavior → score) for #290 calibration sweeps. Replaces bash for-loops that cannot invoke session skills. Default k=3. Inlines collect-dispatch behavior per iteration. Idempotent resume via per-iteration sentinels under skills/temper/evals/.calibrate-state/. |
| **skill-selection-evals** | Eval-only skill for measuring skill routing accuracy. Not invoked directly — contains selection evals that test whether the agent picks the correct skill for a given prompt. |

<!-- CATALOG:END -->
