# Repo-Improvement Audit — 2026-06-10 (milestone 16 source record)

**Status:** durable record of the audit whose findings were filed as GitHub issues
**#394–#406** (milestone **16 "Consolidation & Code Quality (2026-06)"**). The lens-level
evidence below previously lived only in machine-local audit scratch
(`~/.claude/.../memory/audit/scratch/2026-06-10T19-29-36/`) and a gitignored handoff;
this file commits it into the repo so the detail, the coverage-map, and the rejected-finding
reasoning are not lost when that scratch is reclaimed.

- **Date:** 2026-06-10
- **Model:** Claude Fable (user-authorized for this audit run; default orchestration model is Opus)
- **Subsystem audited (deep):** `scripts/` — the Python+shell tooling layer (26 tracked files)
- **Methods:** `/audit` on `scripts/` (full protocol: scoping → 4 lenses + consistency-B → blind-spots → synthesis; **21 findings**); `/stocktake` full (52 skills, all 7 structural checkers green; **5 findings**); `/prospector` **Phase-1 only** (7 friction points); orchestrator-level CI/cross-cutting checks.
- **Terminal verdict:** PASS (Tier-B ledger stub, run_id `019eb31a-5b34-7532-b15a-8ac7115bf6c5`).
- **Dedupe baseline:** checked against milestones 3/4/10/12/15, the A0–A60 baseline (#363), and `docs/research/audit-innovate-2026-06-06.md`.

## Headline synthesis

> **The repo's trust/calibration machinery (`rcpt_verify`, the ledger/grudge pipeline) is its
> least-verified code** — selftests/tests are exist-but-unwired or absent exactly where the
> epistemics live. There are **4 FATAL findings across 3 FATAL-bearing issues** (#398 carries
> two — F1 the calibration write/reduce/reconcile pipeline coverage gap + F2 the untested lock
> state machines). Three of the four are in this trust/calibration cluster (receipt linter accepts
> fabricated hashes [BS1]; the calibration write/reduce/reconcile pipeline has zero test coverage
> [F1]; the concurrency/crash-recovery lock state machines are untested [F2]); the fourth is a
> ledger write routed to a dead in-repo path that also leaks finding data into the public tree [C1].

**Recommended remediation order** (leverage-ranked): **#396 → #394 + #395 → #397 → #399 → #398 phase 1**, then the P2 cluster (#402, #401, #400, #403, #406, #404, #405). Rationale: ship the certain S-effort bugs first, then the trust boundary, then the churn-tax reducer, then test coverage.

---

## `/audit scripts/` — lens findings (21)

Severities use the audit rubric: **Fatal** (will corrupt/leak/mislead under conditions that occur), **Significant** (real cost), **Minor** (preference). File:line evidence preserved from the lens reports. "EXECUTED" marks a finding proven by running code, not by inspection.

### Architecture lens (F0 / S2 / M2)

- **A1 (Significant) — Two incompatible package-rooting conventions in the importable cluster.**
  `grudge_query.py:26` does `sys.path.insert(0, HERE)` + `from grudge_append import …`, while 4 siblings + a test (`brier_advisory.py:35`, `reconcile_ledger.py:37`, `render_ledger.py:28`, `backfill-ledger.py:35`, `test_brier_advise.py:26`) do `sys.path.insert(0, REPO_ROOT)` + `from scripts.X import …`. `__init__.py` declares the `scripts.X` package intent; `grudge_query` contradicts it. `brier_advisory` must bridge both (L294-299, L356-357). → **#401**
- **A2 (Significant) — Correctness-critical `_glob_match` verbatim-duplicated.** Identical algorithm at `grudge_query.py:47-57` and `reconcile_ledger.py:522`. The reconcile copy carries the load-bearing rationale ("a fired predicate flips a FAIL's Brier actual 1→0"; cross-host determinism); both feed the same central calibration ledger, so a semantics fix in one silently drifts the other and corrupts Brier scores. Import machinery to share already exists. → **#401**
- **A3 (Minor) — `git rev-parse --show-toplevel` repo-resolution reimplemented per store.** `ledger_append.py:67-84` (`default_repo`) vs `grudge_append.py:50-69` (`resolve_repo`); differ in return shape + env override (`CRUCIBLE_LEDGER_DIR` vs `CRUCIBLE_GRUDGE_DIR`). The two cross-session stores could disagree on repo identity for worktrees/submodules. → **#401**
- **A4 (Minor) — Checker-skeleton replication: WEIGHED, evidence does NOT support consolidation.** `tracked_md()` is byte-identical in `check_crossref.py:77-81`/`check_model_pins.py:201-205`; selftest argv-gate ×3; block-extraction regex idiom ×3. **Verdict: keep one-file-per-checker.** Duplication is shallow (~5-15 lines); the walk-strategy divergence (git-tracked vs `rglob` set-equality vs fixed-list) is **deliberate and load-bearing** — a shared walker would re-expose every strategy as a parameter and reintroduce coupling; one-file-per-checker keeps each gate independently reviewable. Recorded so this is not re-litigated. → noted in **#401** title ("checker skeleton: keep as-is")

**Architectural map:** (1) CI checker family — 7 standalone `check_*.py` gates (6 CI-wired; `check_rt_receipt_contract.py` is the unwired one per C2), zero intra-`scripts` imports, cleanest layer; (2) Ledger pipeline — `ledger_append → {reconcile, render, backfill}`, pure-core/IO layering honored, single write path imported not copied; (3) Grudge store — `grudge_append ← grudge_query`, with `brier_advisory` the bridge node where the rooting conventions collide. **Defects live at the seam between clusters 2 and 3.**

### Blind-spots lens (F1 / S2 / M2)

- **BS1 (FATAL) — Receipt linter accepts undeclared EDIT/WROTE artifacts with fabricated hashes.** `rcpt_verify.py:233-244` — the EDIT/WROTE branch comments *"Allow it … tightening is left as future work. For pilot, we don't hard-fail here."* Tier-2 (`:496-512`, `:626-647`) verifies only *declared* artifacts/cited witness. **EXECUTED:** a receipt with `1 WROTE secrets.env sha256:<bbb…64>` (undeclared file, bogus hash) → LINT verdict **PASS**. Effect-bearing verbs whose hashes bind to nothing are exactly the fabrication class the linter exists to catch. → **#397**
- **BS2 (Significant) — No containment check vs `--root`; `..`/absolute paths resolve out-of-tree.** `rcpt_verify.py:462-493` — `resolve_base` probes absolute-as-is + `root/name` un-normalized (no `realpath`/containment); `is_path_shaped` accepts `../../etc/passwd` and `/etc/passwd`. **EXECUTED:** `resolve_base('../etc/hostname', Path('/tmp'))` → `/tmp/../etc/hostname`. Every Tier-2 disk read flows through here → a receipt can "prove" hashes against files outside the dispatch tree + unbounded arbitrary-file-read while linting attacker-influenced receipts. → **#397**
- **BS3 (Significant) — Missing `run_id`/`skill` collapse to shared "unknown" join key → cross-repo dedup collision + Brier mis-attribution.** `reconcile_ledger.py:100-102` (`ledger_entry_hash = sha256(run_id+":"+skill)`); five call sites do `e.get("run_id","unknown")`. The central store aggregates **every** repo, so two malformed entries from different repos share `ledger_entry_hash("unknown","unknown")`; L-9 reduce collapses them; `caller_dedup` drops the second. No module rejects identity-less entries. → **#402**
- **BS4 (Minor) — Degrade-to-empty `except Exception` across the advisory consumer path.** `brier_advisory.py:349/367/373/300/321/144-147`; CLI always exits 0. Corrupt store / import regression / malformed falsification all collapse to the same silent "no advisory." (Merge candidate with R2.) → **#400**
- **BS5 (Minor) — `"(none)"` empty-sentinel asymmetry across receipt parsers.** `rcpt_verify.py:98` (`parse_artifacts` accepts `"(none)"`) vs `:110-130`/`:146-160` (`parse_trace`/`parse_claims` raise `LintError` on it). **EXECUTED.** Latent hard-FAILs for authors assuming a universal sentinel. → **#397**

### Consistency lens — agent B (F1 / S2 / M1; confirmed 4, rejected 6)

- **C1 (FATAL) — `backfill-ledger.py` writes to an in-repo ledger store no reader reads.** `backfill-ledger.py:39` hardcodes `REPO_ROOT/.crucible/ledger/runs.jsonl`; every other module routes through `default_ledger_dir()` → `~/.claude/crucible/ledger` (`render_ledger.py:44-45`, `reconcile_ledger.py:1031`, `brier_advisory.py:41-44`). `brier_advisory.py:41-42` even documents `.crucible/ledger/` as the WRONG path. Backfill entries land where nothing reads → silently no effect on the corpus, **and** private finding data is written into the PUBLIC repo tree — the exact failure the central-store convention exists to prevent. → **#396**
- **C2 (Significant) — `check_rt_receipt_contract.py` is a green-by-absence gate.** Its docstring (`:26`) claims it "Mirrors check_canonical_drift.py and check_i2_marker.py" — but those ARE CI-wired and it is NOT (`ci.yml:11-24`); no `--selftest`, no paired test. It is the most assertion-dense checker (13 lettered ACs) guarding the #366 contract, which can silently rot. → **#394**
- **C3 (Significant) — `test_catalog.py` exists but is not CI-wired** while sibling suites are (`ci.yml:16` wires `catalog.py check` but not the test; `:18`/`:22` wire `test_rcpt_verify`/`test_brier_advise`). 37 KB largest test file; a regression in `_parse_row`/`_scalar_value`/count-grammar ships green. → **#394**
- **C4 (Minor) — repo-resolution realpath asymmetry.** `ledger_append.py:81-84` (no `realpath`) vs `grudge_append.py:63-67` (canonicalizes). Symlinked repo path → two stores derive different repo labels. → **#401**
- **Rejected with evidence (do not re-file):** `tracked_md()` duplication (byte-identical, not drifted, 4-line wrapper); `_warn`/privacy-guard/env-default parallels (correct per-module parameterization; privacy guard is grudge-only by design); four tree-walk strategies (load-bearing semantics); `compass doctor` (different tool category); `render_ledger` least-tested (coverage, not consistency); backfill hyphen-naming (cosmetic, folded into C1).

### Consistency lens — agent A (triage/ranking)

Ranked flag order (feeds the lenses above): 1 `check_rt_receipt_contract.py` (unwired+no selftest+no test); 2 `backfill-ledger.py` (hyphenated, non-importable); 3 `check_canonical_drift.py`; 4 `check_qg_stagnation_minor.py`; 5 `check_i2_marker.py` (sole `rglob` user); 6 `check_crossref.py`+`check_model_pins.py`; 7 `grudge_append.py`+`ledger_append.py`; 8 `catalog.py`; 9 `compass.py`; 10 `render_ledger.py`. Observations: checker self-verification split 4/4; four tree-walk strategies for one concern; CI-wiring selectively applied; `npm test` broken at repo boundary.

### Robustness lens (F0 / S2 / M1)

- **R1 (Significant) — Two engineered durable-write disciplines, absent from four bare truncating writers.** Locked+atomic: `ledger_append.py:282-326` (mkdir-lock+holder+O_APPEND+fsync), `compass.py:377-393,695` (lock+mkstemp+`os.replace`). Plain truncating writes, no lock: `grudge_append.py:194-198`, `reconcile_ledger.py:1087-1094` (brier-rolling.json), `render_ledger.py:796-797` (weekly-*.md), `calibrate_tolerance.py:182` (calibration.json) — **four** bare writers. (Issue #400's title says "three unlocked" — an undercount; #400's own body lists these four, so a maintainer working #400 should treat four as the real scope.) Grudge's dedup key is deterministic → same-key concurrent writes from parallel sessions race on one path with no lock → torn store. → **#400**
- **R2 (Significant) — Silent warn-and-continue on every read path; no corruption signal anywhere.** `brier_advisory.py:248-281` (`except → return {}`, malformed line dropped); `ledger_reduce.py:45-46` (drops entire last line if no trailing newline); `ledger_append.py:130-135`; `grudge_query.py:80-81,102-114`; `render_ledger.py:95-96`; `reconcile_ledger.py:128-129`. Inconsistent: `backfill-ledger.py:79-83` and `grudge_query.py:39` (`_qwarn`) DO warn — same boundary class mixes warn-and-drop arbitrarily. No doctor-equivalent for ledger/grudge stores (compass has one). → **#400**
- **R3 (Minor) — subprocess git/gh boundary: no shared timeout/failure policy.** `backfill-ledger.py:198-208` (`gh pr list`, no timeout, no except → uncaught abort) vs `ledger_append.py:75-78`/`grudge_append.py:57-61` (`timeout=5, except: pass`). Several sites can hang indefinitely (hung credential helper / network mount). → **#406**

### Test-health lens (F2 / S2 / M1)

- **F1 (FATAL) — Calibration-ledger write/reduce/reconcile pipeline (the epistemic backbone) has zero test coverage.** No test/selftest imports `ledger_append.py` (append/lock/dedup/L-8 truncation), `ledger_reduce.py` (L-9), or `reconcile_ledger.py`'s pure core (`ledger_entry_hash`, `reconcile`, `compute_brier`, `parse_predicate`). `test_brier_advise` covers the READ side only. `reconcile_ledger.py:8-13` documents a deterministic pure core "architected for unit-testability" — an unused seam. A regression corrupts the committed corpus every gating decision trusts. → **#398**
- **F2 (FATAL) — Concurrency/crash-recovery lock protocols untested (2 bespoke state machines).** `ledger_append.py:141-234` (`_try_stale_recovery`+`_acquire_lock`) and `compass.py:92-180`. `compass.py:60-71` even ships a `_test_sleep()` hook (`CRUCIBLE_COMPASS_TEST_SLEEP_MS`) — no test consumes it. No test exercises contention, stale lockdir, dead-PID holder, malformed holder, or the short-write partial-line path. → **#398**
- **S3 (Significant) — Central-store mutators systemically untested as a class.** `grudge_append.py` privacy guard (`:172-178`) — exists because grudges carry private paths and the repo is PUBLIC, so a regression leaks private data; `render_ledger.py` WHS honest-count + 3×-rolling-median inflation detector (the anti-gaming check); `backfill-ledger.py` entry builders. → **#398**
- **S4 (Significant) — Documented "smoke test"/test layers don't exist as code.** `backfill-ledger.py:16` docstring claims "The smoke test exercises the pure core" — no such test. `reconcile_ledger.py:8-13` documented testable core, no tests. Repo-level `npm test` (vitest) finds zero test files, exit 1; `package.json directories.test` → nonexistent `tests/`; CLAUDE.md advertised `npm test`. → **#395** (npm) + **#398** (core)
- **M5 (Minor) — uuid7 invariants unasserted + green-but-unwired tests don't gate.** `uuid7.py:11-22` (version nibble, variant, monotonic sortability unasserted); `test_catalog.py` + `check_rt_receipt_contract.py` green but absent from `ci.yml`. Effective CI coverage is narrower than the test inventory suggests. → **#394** (wiring) + **#398** (asserts)

### Out-of-scope instance bugs (flagged for `/delve`) — 4 batched into #406; the `rcpt_verify:141` span-cap → #397

- `rcpt_verify.py:141` — `check_exec_range_bound` estimates `(b-a)*80` bytes; the 4 KiB witness-span cap is bypassable for long lines. *(tracked in #397)*
- `reconcile_ledger.py:441` — dead branch: `compute_brier` early-returns `{}` when `now_dt is None` (L364-365), so the `_now_iso()` leg is unreachable.
- `ledger_append.py:228-233` — `_acquire_lock` held-but-fresh lock spins ~305s instead of the documented ~5s initial cap.
- `grudge_append.py:75` — `normalize_path` `startswith` on raw string: a sibling dir sharing the repo_root textual prefix is mis-normalized.
- `compass.py:689-693` — lock hash derived from `dirname(path)`: a non-default `--path` hashes a different lockdir, so two writers via different path spellings don't share a lock.

---

## `/stocktake` — skill-suite findings (5)

52 skills evaluated; all 7 structural checkers green. **Verdict table: all 52 = Keep except 4 = Improve** (the 4 Improve verdicts → #404; the doc-hygiene cluster → #406). The **5 findings** here = those 4 Improve verdicts + 1 doc-hygiene cluster (the `recon`/`prospector`/`spec` marker gaps folded into #406). The per-skill verdict table itself was not persisted beyond the session transcript — this summary line is the recoverable record. Findings folded into **#404** (eval-harness improve set) and **#406** (doc hygiene: e.g. `recon/SKILL.md` duplicates the full Investigation Brief template at `:395-448` and again at `:644+`; `recon`/`prospector`/`spec` SKILL.md carry the dispatch-convention CANONICAL marker but no `return-convention.md` marker).

## `/prospector` Phase-1 — architectural friction (7 points)

Genealogy/root-cause/design phases deliberately skipped (deliverable was issues, not a chosen redesign). The 7 friction points were **distilled into the 3 standalone-leverage issues below (#399, #404, #405)**; the remaining 4 either overlapped audit findings already filed (e.g. the checker/ledger-seam frictions subsumed by A1/A2 → #401) or were lower-signal and not separately tracked. The full prospector explorer output was **not persisted beyond these issue bodies** (transcript-only), so only the 3 filed issues are recoverable here. Friction captured in issue bodies:

- **#399** — CI checker pin-strings are verbatim English prose pinned inside the two highest-churn files (`quality-gate/SKILL.md` 65 commits/6mo, `build/SKILL.md` 57) → ongoing edit tax; migrate to structural markers.
- **#404** — `build/evals/` and `temper/evals/` are two heavyweight staged-fixture harnesses sharing zero code; unify before #373 multiplies them.
- **#405** — the dispatch/return protocol exists only as prose re-implemented by ~14 orchestrators (106 CANONICAL links); no executable home, no structural address. Research/design issue.

## Orchestrator-level / calibration-loop finding

- **#403** — `temper` and `delve` emit no calibration-ledger verdicts (8 other skills do). `temper` is the merge gate — its PASS is the single most falsifiable verdict in the suite (`reconcile_ledger` mines post-merge `fix/*`/`hotfix/*` branches), yet it contributes no entry to falsify. The `shared/ledger-append.md` skill enum is already stale.

---

## Finding → issue traceability

| Issue | Title (abbrev.) | Findings folded in |
|---|---|---|
| #394 | Wire 5 orphaned suites/checkers into CI | C2, C3, M5 (wiring); the five = `check_rt_receipt_contract.py`, `test_catalog.py`, `hooks/tests/test-build-routing-advisor.sh`, `hooks/tests/test-gate-ledger-guard.sh`, `hooks/tests/tools/test-build-routing-reconcile.sh` (last three from the orchestrator-level CI cross-check, not the per-file lenses) |
| #395 | Retire/repoint Node toolchain; fix npm test | S4 (npm half) |
| #396 | backfill dead store + public-tree leak | **C1 (FATAL)** |
| #397 | Harden rcpt_verify | **BS1 (FATAL)**, BS2, BS5, rcpt_verify:141 |
| #398 | Unit-test ledger core + lock state machines | **F1 (FATAL)**, **F2 (FATAL)**, S3, S4, M5 (asserts) |
| #399 | Checker pin-strings → structural markers | prospector friction |
| #400 | Atomic writes + corruption surfacing (4 unlocked stores; GH title undercounts as 3) | R1, R2, BS4 |
| #401 | Consolidate ledger/grudge seam | A1, A2, A3, C4 (+ A4 "keep as-is") |
| #402 | Reject identity-less ledger entries | BS3 |
| #403 | temper+delve emit no ledger verdicts | calibration-loop gap |
| #404 | Unify build/temper eval-harness forks | prospector + stocktake Improve |
| #405 | Executable home for dispatch protocol | prospector friction |
| #406 | Sweep: doc hygiene + hook tests + 4 instance bugs | R3, stocktake doc-hygiene, reconcile:441, ledger_append:228, grudge_append:75, compass:689 |

Every lens finding maps to a filed, open issue. The three FATAL-bearing issues are #396, #397, #398.

---

## Coverage-map — what this audit did NOT examine (the audit's own blind spots)

The `/audit scripts/` run read these in full and grounded findings in them: `ledger_append.py`,
`ledger_reduce.py`, `brier_advisory.py`, `catalog.py`, the 7 `check_*.py` checkers, `grudge_append.py`,
`grudge_query.py`, `backfill-ledger.py`, `compass.py`, `.github/workflows/ci.yml`.

**Never read in full by any lens** (only boundaries/wiring discussed):

- `scripts/rcpt_verify.py` (1044L) — the receipt-lint trust boundary. Only its selftest/CI wiring and the BS1/BS2/BS5 sites were examined; the body was not fully audited.
- `scripts/reconcile_ledger.py` (1105L) — the largest module; specific sites grounded findings (A2 `:522`, BS3 `:100-102`, R1/R2 `:1087-1094`/`:128-129`, and the `:441` dead-branch), but the Brier/falsification core and the GIT layer (`L786-1018`, "NOT exercised by unit tests", feeds Brier actual-flips) were not read in full — skimmed at boundaries only.
- `scripts/render_ledger.py` (809L) — skimmed at boundaries only.
- `scripts/calibrate_tolerance.py` (188L) — one write site cited, body unread.
- `scripts/test_rcpt_verify.py` (579L), `scripts/test_catalog.py` (787L), `scripts/build-evals.sh`, `scripts/hooks/pre-push-build-evals.sh` — unread.

**Per-lens "deeper inspection wanted" leads:** full read of `reconcile_ledger.py` (other copied predicates?) and `grudge_query.py`; `reconcile_ledger.py:786-1018` GIT layer; `compass.py:180-1182` field caps + `MUTEX_PAIRS` untested.

> This blind-spot map is the most perishable part of the audit and is **not** captured by any
> #394–#406 issue. It is tracked by dedicated follow-up issue **#408** (milestone 16) so a later
> Opus-session pass can complete coverage of the un-audited trust-critical modules.

## Provenance

- Lens reports (source): `~/.claude/projects/-mnt-coding-Coding-crucible/memory/audit/scratch/2026-06-10T19-29-36/{architecture,blindspots,consistency-a,consistency-b,robustness,testhealth}-findings.md`, `coverage-map.md`, `manifest.md` — machine-local, reclaimable.
- Dispatch manifest: `<scratch>/crucible-dispatch-1781119787/manifest.jsonl` (9 dispatches, all completed).
- Backlog handoff (gitignored): `docs/handoffs/2026-06-10-audit-milestone16-backlog.md`.
