# Changelog

Notable changes to the Crucible skill library. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); entries are grouped by
milestone since skills ship as a library rather than a versioned binary.

## v1.8.1 — README eval-figure sync — 2026-06-14

Docs-only patch. The README's headline A/B deltas still carried the Opus 4.6
figures after `docs/evals.md` was re-measured on Opus 4.8; this syncs them and
adds the inverse-capability thesis. No skill behavior changed.

### Changed

- **README eval figures synced to the Opus 4.8 re-measurement** — the headline
  now matches `docs/evals.md`: execution evals **+23%** (52 evals, 475
  assertions, graded blind on Opus 4.8; was the +29% Opus 4.6 figure), and
  `quality-gate` **+55%** (93% vs 38%; was +68%). Sequence/ordering evals remain
  **+31%** (Opus 4.6 — not yet re-run on 4.8), now labeled as such. Added the
  "skill value scales inversely with model capability" framing (+29% on 4.6 →
  +23% on 4.8). (#421 follow-up)

## v1.8.0 — Trust-Machinery Hardening & Test Coverage — 2026-06-12

Two milestones land in this cut: the **Audit & Innovation Remediation** sweep
(milestone 15) and **Consolidation & Code Quality** (milestone 16). The
throughline came from the repo's own `/audit`: the trust/calibration machinery —
the receipt linter, the calibration ledger, the on-disk lock protocols — was the
*least-verified* code in the library, exactly where the epistemics live. So this
release promotes the receipt linter from prose to a runtime tool, unifies the
test runner so CI and local can never drift, and closes the coverage gap on the
"epistemic backbone" with **+159 tests** across three new suites.

### Added

- **Runtime receipt linter** — the Ledger Return Protocol moves from in-context
  pseudocode to an executable `scripts/rcpt_verify.py` (Tier-1 structural +
  Tier-2 witness verification, `--strict`, `--root` containment, `--ledger`
  receipt-ledger binding). Orchestrators (build, siege, quality-gate) now run the
  tool on every received receipt before acting on its verdict. (#369, #382, #388,
  #389, #383)
- **Generated, drift-checked skill catalog** — `scripts/catalog.py` renders
  `docs/skills.md` from each `SKILL.md` frontmatter and fails CI on drift, so the
  catalog can no longer rot out of sync with the skills. (#364)
- **Calibration-weighted dispatch (advisory)** — `brier_advisory.py advise`
  surfaces, as print-only scrutiny hints, which gated files a skill's past *wrong*
  verdicts touched (Brier + falsification + grudge signals). Never scored, never
  blocking. (#372)
- **Fable-5 model-tier guardrail** — `scripts/check_model_pins.py` + a
  `model-tier-policy.md` guard the per-role model pins against an accidental
  downgrade to a non-default tier on recall-critical roles. (#392)
- **Canonical test runner** — `scripts/run_tests.sh` is now the single source of
  truth that `.github/workflows/ci.yml` invokes wholesale, so CI ≡ local with
  zero drift surface; five previously-orphaned suites/checkers were wired in.
  (#394, #395)
- **Calibration-ledger, lock & store test coverage (+159 tests)** — the epistemic
  backbone, previously at zero coverage, gains `scripts/test_ledger_core.py` (89:
  append/dedup/L-8 truncation, L-9 reduce, reconcile/Brier/predicate pure core),
  `scripts/test_locks.py` (23: both bespoke mkdir-lock state machines +
  crash-recovery + a real contention test), and `scripts/test_stores.py` (47:
  grudge privacy guard, honest "caught N" headline + inflation detector, backfill
  pure core). (#398)
- **AST ledger-write-path guard** — `scripts/check_ledger_write_path.py` flags any
  `scripts/**.py` that would write a `.crucible/` path inside a repo tree (the
  store is machine-local and this repo is public). (#396)
- **CONTRACT anchors for CI checkers** — `scripts/CHECKER_CONVENTIONS.md` plus a
  migration of pin-strings on the highest-churn files from verbatim English prose
  to structural `<!-- CONTRACT:NAME -->` anchors, so a benign wording edit no
  longer breaks CI. (#399)
- **Red-team as a first-class Evidence Receipt citizen** — red-team emits a
  structured `RCPT v1.1` receipt that participates in the tripwire manifest and
  supersession sweep like every other gate subagent. (#366)

### Changed

- **rcpt_verify hardening** — `--root` containment closes an arbitrary-file-read,
  `(none)` sentinel parsing is symmetric, and the witness span-cap now measures
  ACTUAL decoded/raw bytes (no U+FFFD inflation). (#397)
- **Receipt mandate scoped to adopting skills** — the return-convention receipt
  requirement applies to the skills that adopt it, not universally. (#368)
- **P0 audit-remediation contract fixes** — dispatch/worktree/cross-reference
  contract corrections plus a `check_crossref.py` invariant, later wired into CI.
  (#367, #365, #385)
- **Cross-skill doc-drift cluster reconciled** — A5/A19/A26/A47/A48/A50. (#370)
- **canonical-drift checker repaired** and the reviewer-lenses vs delve-engine
  angles documented as two *deliberately separate* vocabularies. (#358)

### Fixed

- **backfill ledger repointed** off the dead in-repo `.crucible/` store (a
  public-tree leak risk) onto the machine-local central store. (#396)

### Docs

- **CLAUDE.md test + calibration-ledger claims corrected** to match the
  central-store move and the canonical runner. (#407)
- **2026-06-10 repo-improvement audit committed** in-repo as the milestone-16
  source-of-record (lens findings + executed proofs + finding→issue traceability).
  (#409)

Two lock instance bugs surfaced by the audit (`ledger_append.py` held-but-fresh
spin, `compass.py` dir-scoped lock identity) are deliberately **pinned as labeled
characterization tests** in `test_locks.py`; their fixes remain tracked in #406.

## QG Stagnation-Score Cleanup — 2026-06-05

Makes the quality-gate stagnation *judge* (not the weighted score) Minor-aware,
reconciles the contradicting Minor prose, documents siege-once-on-full-artifact
for chunked gates, and adds a `DR-Cause` telemetry discriminator. The weighted
score (`Fatal=3, Significant=1, Minor=0`) is unchanged. Tickets #260, #258.

### Changed

- **Stagnation judge is Minor-aware.** A new Step-3 Mixed-branch rule in
  `stagnation-judge-prompt.md` classifies `DIMINISHING_RETURNS` when Minors
  recur/accumulate at a flat score with **zero recurring Fatals/Significants**,
  corroborated over 2 rounds via a persisted "Consecutive recurring-Minor rounds"
  counter (analogous to the existing all-Structural counter); fail-open to
  PROGRESS. Reconciled the `## Minor Issue Handling` prose accordingly — Minors
  still never enter the weighted score and never trigger fix rounds, but the
  judge may weigh sustained Minor accumulation at round ≥ threshold. The weighted
  score is unchanged. (#260)
- **Chunked-gate siege scope** is now documented as dispatched **once on the full
  artifact**, not per-chunk, with the acknowledged chunk-local sink tradeoff. (#258)

### Added

- **`DR-Cause` judge discriminator** — a `DR-Cause: minor-accumulation |
  structural-saturation | none` Output-Format line emitted per DIMINISHING_RETURNS
  path (parsed like `Verdict:`), plus a convergence-log-only `dr_cause` field
  (`minor-accumulation | structural-saturation | consensus | null`,
  key-presence-versioned, **no `marker_version` bump**, no verdict-marker field),
  with the canonical denominator rule reconciled to filter on `dr_cause`
  key-presence. The orchestrator composes a distinct minor-accumulation
  DIMINISHING_RETURNS user message at both escalation sites. (#260)
- **`scripts/check_qg_stagnation_minor.py`** — a stdlib structural checker (path-
  pinned to the judge prompt + `quality-gate/SKILL.md`) guarding the Minor-aware
  rule, the counter line, the `DR-Cause` enum, the reconciled Minor prose, and the
  convergence-log `dr_cause` value set; wired into `/stocktake`. (#260)

Disposition: #258(1) fixed (siege-once doc); #258(2) closed accepted/inherent for
short thresholds; #258(3) (`diminishing-returns` rename) closed won't-fix
(contract-risk-exceeds-benefit).

## Review-Trio Reshape — 2026-06-03

Splits the code-review trio on an **instance-vs-systemic** axis. `delve` (new)
owns one-reproduction instance bugs as a portable fan-out engine; `temper` gains
fix-verification convergence; `audit` becomes a systemic-only reporter that
delegates instance bugs to `delve` and complexity to `prospector`. Milestone #13
(epic #338), tickets #328–#336.

### Added

- **`/delve`** — standalone instance-bug reviewer. Drives the shared
  `delve-engine` once (parallel finder fan-out + one-verifier-per-candidate
  verify gate) over a diff, PR, or path and prints ranked, verified defects with
  reproductions. Report-only; `--fix` (working-tree edits) and `--comment`
  (forge post-back) are opt-in. Forge-agnostic. (#331)
- **`shared/delve-engine.md`** — the Crucible-owned, harness-portable
  instance-bug engine: seven finder angles (three bug, four capped non-gating
  quality) plus a one-verifier-per-candidate verify gate. (#330)
- **`shared/severity-verdict-contract.md`** — the single severity scale, the
  verify-gate verdict vocabulary (CONFIRMED / PLAUSIBLE / REFUTED), and the
  gating rule `T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}`, shared by the
  whole trio (one scale, no per-skill fork). (#328)
- **`shared/harness-adapter.md`** — portability convention + per-harness install
  manifest (documented contract + install step, no runtime shim). (#329)
- **`audit --bugs`** — opt-in sub-path that runs `/delve` over the audited
  subsystem and appends a separate instance-bug section using delve's schema. (#332)
- **`audit --drift intent=<path>`** — opt-in divergence-from-intent section
  comparing a subsystem against an explicit intent artifact. (#332)
- **Multi-angle detection fixture** (`skills/temper/evals/fixtures/multi-angle/`)
  and the live Claude-Code recall-floor validation: a standalone full-7-angle
  `delve` fan-out on the parallel-dispatch path recalls 7/7 planted bugs. (#333, #335)
- **I2 marker-allowlist checker** (`scripts/check_i2_marker.py`, a stdlib-only
  Python checker mirroring the repo's existing `scripts/check_*.py` pattern, run
  as `python3 scripts/check_i2_marker.py` and wired into the `/stocktake` skill's
  Phase 1 structural-invariants step) — an anchored, set-equality check that the
  engine-dispatch marker (the column-0 body line `^dispatch: delve-engine`,
  written here only inline/backtick-wrapped as `` `dispatch: delve-engine` ``)
  appears in exactly the two direct dispatchers `{delve, temper}` — any stray
  extra dispatcher or missing one fails. (#336)

### Changed

- **`audit` code path is now systemic-only** — it reports recurring patterns,
  structural properties, and absences with no single reproduction. A defect with
  one concrete reproduction (even across files) is an instance bug and routes to
  `/delve`. (#332)
- **`temper` converges by fix-verification of an enumerated tracked set.** Round 1
  drives `delve-engine` (bug-angle subset, high effort) to enumerate the tracked
  set `T`; later rounds re-verify each member against the fixed code and admit any
  new gating finding the fix introduced. Convergence is the resolution status of
  `T`'s members, never a cross-round Critical+Important count. The fix-loop
  interface is unchanged (`max_rounds`, `external_review=skip` preserved). (#333)
- **Engine-dispatch wiring.** The two direct dispatchers (`/delve`, `temper`)
  carry a column-0 body marker line wiring them to the harness-adapter fan-out
  mechanism; `audit` reaches the engine only transitively via the `/delve` skill
  and carries a separate skill marker. (#334)
- **Per-role subagent model enforcement** for the quality-gate / red-team loop
  via named `crucible-*` agent types (orthogonal #352, shipped alongside). (#352)
- **`audit` non-code path polish bundle.** (1) Non-code lens and blind-spots
  dispatches now read the artifact + supporting context + operating environment
  from a single shared `dispatch-context.md` bundle (assembled once in Phase 1)
  instead of inlining the full context into every per-lens dispatch — the bundle
  is held to a 1500-line ceiling with a deterministic truncation order (artifact
  never truncated). (2) Phase-4 cross-referencing scales down for non-code
  findings (label + title-keyword search, capped, best-effort skip — non-code
  findings have no path/symbol anchor). (3) Tightened the Feasibility vs Risk &
  Dependencies lens-overlap on `plan` artifacts. (4) Scratch + stale cleanup
  documented as best-effort under `.claude/`-path-blocking safety hooks. (5)
  Documented the pipeline-status Read-before-Write first-write requirement. (#256)

### Removed

- **`audit` no longer finds instance bugs by default.** One-reproduction defects
  are `delve`'s; audit's `code` lenses are systemic-only. Mitigate with
  `audit --bugs` (see Migration). (#332)

### Migration

Skills are Markdown — there is **no data migration**. Behavioral notes:

- **`audit` users lose instance bug-finding by default.** Previously `/audit`
  surfaced concrete one-reproduction defects; the reshaped code path is
  systemic-only. To get the old instance-bug coverage, run **`/audit --bugs`**
  (appends a `/delve` instance sweep) or invoke **`/delve`** directly on the diff
  or subsystem. When `/delve` is not installed, audit surfaces an explicit
  out-of-scope stub rather than silently dropping instance findings.
- **`temper` has no interface change.** Round 1 is internally richer (it drives
  the engine fan-out instead of one holistic reviewer), but the invocation shape
  is unchanged — `max_rounds=<N>` and `external_review=skip` work as before. No
  caller update is required.
- **`/delve` is authored fresh** with a clean retrospective slate. It is **not**
  seeded from the repo's `code-review` directory — that lineage is `temper`'s
  ancestor (pre-rename), not delve's. On Claude Code the built-in `/code-review`
  command still exists and is an optional accelerator, never a dependency.
- **OpenCode runtime validation is deferred to the non-gating follow-up #337.**
  The milestone gate (#335) validates Claude Code only; skills remain authored
  harness-neutral via the harness-adapter.

## Calibration Ledger, Regression Memory & Arc-State — 2026-06-01

Backfilled record of the Epistemics Stack milestone (skills shipped 2026-05-20 →
2026-06-01) — the calibration-ledger subsystem and its companion persistence
skills that were not previously recorded here. The calibration ledger is the
epistemic backbone of the Tier-A gate: gate verdicts are appended and later
falsified against merged fixes, turning the suite's "caught a real bug" claims
into measurable calibration scores.

### Added

- **`/compass`** — persistent per-repo arc-state in `docs/compass.md` (current
  arc, last meaningful commit, open loops, next move, don't-forget items).
  Auto-maintained by build, merge-pr, and finish; read by getting-started.
  Tickets #273, #286, #308.
- **`/ledger`** — weekly calibration-ledger renderer: the honest "Crucible
  caught N silent bugs" headline, verdict breakdown, per-skill severity rates,
  and an inflation detector. Backed by `scripts/render_ledger.py`,
  `ledger_append.py`, and `ledger_reduce.py`. Ticket #272.
- **`/calibration-reconcile`** — walks merged fix/hotfix branches to falsify the
  originating gating verdicts, computes per-skill Brier calibration scores, and
  appends a falsification record. Backed by `scripts/reconcile_ledger.py`,
  `brier_advisory.py`, and `calibrate_tolerance.py`. Ticket #270.
- **`/grudge`** — the Book of Grudges: a machine-local, per-repo (never
  committed) cross-session bug graveyard. Every fixed bug is recorded as a
  structured grudge; before touching code, skills query the grudgebook for the
  files in scope and surface past regressions as forced "DO NOT REPEAT" context.
  Backed by `scripts/grudge_append.py` and `grudge_query.py`. Ticket #271.

### Note

The calibration ledger is machine-local central (`~/.claude/crucible/ledger/`)
and is **never committed**; only the fixture kill-switch
(`CRUCIBLE_CALIBRATION_DISABLED=1`) silences it, and only for tests.
