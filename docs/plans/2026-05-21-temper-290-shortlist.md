# Temper #290 — Real-PR Fixture-Mining Shortlist (Task 1 / F1)

Pre-flight shortlist of merged Crucible PRs suitable for real-PR fixture authoring.
Consumed by Task 7. One row per lens (Surgical / DRY / SRP / OCP / Mixed).

Plausibility gates applied (per implementation-plan §Task 1 / Design SP2 AND-tightened):

- **Criterion A:** injection LOC is ≥20 LOC from the diff's first added line within the
  chosen slice, AND ≥10 LOC into the slice's content from slice start.
- **Criterion B:** fixture includes ≥1 unchanged-context file (matching fixture `4`'s
  structure) with ≥30 LOC of content (no 3-line stub padding).
- **Tenant-grep:** clean against `\btenant_id\b|\borg_id\b|\brealm_id\b|\brealm_name\b|\btenant_realm\b|\bworkspace_id\b|\baccount_id\b|\bcustomer_id\b`.
- **`_LENS_RE`:** no `^Lens:` line in slice.
- **Merge confirmed:** SHA present in `git log` on `main`.

Search window: last ~30 merged Crucible PRs (initial recon shortlist consumed; no
widening needed — every lens hit on the first pass).

## Shortlist

| lens | PR# | sha | file | line_range | rationale | tenant_grep_status | lens_re_status |
|------|-----|-----|------|------------|-----------|--------------------|----------------|
| Surgical | #281 | dc05109 | scripts/ledger_append.py | L47-L75 | `_truncate_payload` is a tightly scoped helper with one purpose (apply L-8 truncation on a shallow copy, return overflow). Comment cites the specific review finding (S-3) that motivated it. Surrounding 299-line file provides ample slice content (≥30 LOC slice trivially; full file unchanged-context candidate). Injection point near the `if isinstance(gated, list)` branch sits ~17 LOC into slice / well within the 20-LOC-from-diff-first-line constraint when the slice opens at the function header. | PASS | PASS |
| DRY | #284 | 8c3c269 | scripts/compass.py | L911-L1010 | `_parse_single` (L911) and `_parse_multi` (L1000-area) are structurally parallel argparse-style loops over `argv` — same `while i < len(argv)` skeleton, same `tok == "--field"`/`--value` branches, parallel error-message shape. Classic DRY-violation slice: two near-identical state machines that should share a tokenizer. 1165-LOC file gives unchanged-context fodder elsewhere (e.g. `_acquire_lock`, `_parse`, `_render` 100+ LOC chunks). Slice ≥30 LOC; injection target well inside content. | PASS | PASS |
| SRP | #162 | a99728f | mcp-servers/crucible-consensus/server.py | L23-L90 | The `ServerState` dataclass refactor encapsulates five previously-global mutable state variables (`_config`, `_providers`, `_project_dir`, `_external_config`, `_external_providers`) into a single cohesive owner with one responsibility (server lifecycle state). `initialize()` rewires to populate the dataclass; `_get_state()` provides single-point access for all `_handle_*` consumers. Textbook SRP win. 286-line file post-merge; unchanged-context companions (`aggregator.py`, `providers.py`) ship in the same PR. | PASS | PASS |
| OCP | #298 | 8cc4821 | skills/temper/evals/run_evals.py | L782-L855 | New `stage` and `score` subparser arms added to `_parse_args` (L784-L798), with parallel dispatch in `main()` (L824-L851: `if args.cmd == "stage":` / `if args.cmd == "score":`). Legacy mock/replay path preserved unchanged below — the file is *extended* with new arms, not modified at existing call sites. Definition broadened per plan Step 2 to include subparser/dispatch additions (handler-map / elif-chain / dict-dispatch / registry). 941-LOC file; unchanged-context companions in same PR (`_dispatch_paths.py`, `bootstrap_snapshot.py`). Slice ≥70 LOC content; injection sites well past 20-LOC threshold. | PASS | PASS |
| Mixed | #293 | cd5cbf7 | skills/temper/evals/lens_runner.py | L178-L260 | Pairs **DRY + OCP**: (1) DRY — `category_finding_fires` (L207) is a near-line-by-line mirror of `lens_finding_fires` (L190) with `category` swapped for `lens`, `_severity_at_least` helper extracted (L186) and reused by both. (2) OCP — adds a new "Category" arm to the finding-discriminator dimension (parallel to existing `Lens:` axis), with mutex-tripwire WARN preserving the existing dispatcher. Slice spans both functions plus `category_finding_does_not_fire` (L240). 457-LOC post-merge file; unchanged-context: same PR's `test_lens_runner.py` (190 LOC added) and pre-#293 sibling `evals.json`. | PASS | PASS |

## Candidates considered + rejected

- **#301 (910105c) `skills/temper/temper-reviewer.md`** — Rejected. 4-line markdown-only
  diff; fails Criterion A (no 20-LOC-from-diff distance possible within slice) and the
  unchanged-context companion would have to be the full reviewer template, which is
  unfair to a "small-fix-amid-realistic-code" framing.
- **#200 (190b6bf) `skills/innovate/SKILL.md`** — Rejected. Markdown-only; no executable
  code surface; bypasses Criterion A's intent (lens evals target code reasoning, not
  prose-edit detection).
- **#284 (8c3c269) `scripts/compass.py` — for OCP** — Rejected as OCP candidate (kept
  for DRY). The `elif` chains exist but are intra-function (parse-state branches), not
  the dispatcher/strategy/handler-map widening the lens targets. Better OCP fit lives
  in #298's subparser registration.
- **#162 (a99728f) `aggregator.py` `parse_aggregation_output` regex→raw_decode swap —
  for Surgical** — Rejected to avoid double-use of #162 (already taken for SRP).
  Substantively viable but would violate the "one PR per lens where possible" implicit
  diversity goal; #281's `_truncate_payload` is an equally clean Surgical fixture from
  a distinct PR.
- **#207 (7ff0080) `eval/invariant-cairn/cairn_lint.py`** — Considered but deferred.
  383-LOC new file; lens-fit unclear without a deeper read (lint engine has multiple
  concerns: parsing, validation, reporting). Re-evaluate in Task 7 if a primary
  candidate falls through review.
- **#190 (0ef3d50) siege prompts** — Rejected. Markdown prompt-engineering deltas;
  same disqualifier as #200/#301.
- **#150 (258500a) replay/dispatch convention** — Rejected. 430-LOC markdown skill
  doc + dispatch-convention.md text changes; no executable surface.

## Fallback path

OCP-FALLBACK **not applied**. #298's subparser-arm addition (`stage`, `score`) satisfies
the plan's widened OCP definition (new arm in dispatcher / strategy / handler-map /
elif-chain / dict-dispatch / registry). No drop to synthetic-with-extra-noise needed.

## Provenance

- Author: Phase 3 Task 1 (#290 build pipeline).
- Search method: `gh pr list --state merged --limit 30` + `git show --stat <sha>`
  walk over the recon-shortlisted PRs plus a sweep of the broader last-30 window.
- Tier-3 self-review: every row re-validated against Criterion A + B + tenant-grep +
  `_LENS_RE` before commit. No "synthetic-with-extra-noise" candidates from the
  OR-escape path were accepted.
