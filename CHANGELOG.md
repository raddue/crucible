# Changelog

Notable changes to the Crucible skill library. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); entries are grouped by
milestone since skills ship as a library rather than a versioned binary.

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
