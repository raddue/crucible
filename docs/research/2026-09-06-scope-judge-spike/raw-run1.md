# Run 1 — raw judge outputs (all six cases)

**Provenance.** These are the verbatim outputs of the six run-1 scope-judge dispatches
(Sonnet, one dispatch each, no repo access), against the dispatch files in
`/tmp/crucible-dispatch-1788706194/`. At run time only the P1/P2/N1/N2 rows of the summary
table below were written to disk; P3's and N3's rows were left `(pending)` at run time and
their verdict/flagged/confidence values — like the full per-case outputs for all six cases —
were **recovered from the session transcript on 2026-09-07**
(`~/.claude/projects/.../b464e40c-a450-4707-aa5b-afa3608d7e83.jsonl`), which records each
subagent return verbatim. Each block below is the judge's own output verbatim, from `VERDICT:` through its closing
`NOTE:`; the transcript's surrounding task-notification envelope (internal task ids, local
file paths, token usage) has been trimmed away as non-evidence, and nothing inside the
judge's output was altered. They are therefore a faithful record of what the judges returned,
but they were transcribed after the fact rather than captured at run time — a weaker
provenance than run 2's, and the reason the spike now writes judge output to disk as it goes.

Timestamps below are the transcript's own, UTC.

## Summary

| case | expected | verdict | flagged | confidence | tokens | wall |
|---|---|---|---|---|---|---|
| P1 | SCOPE-EXPANSION | SCOPE-EXPANSION | docs/research/2026-06-10-audit-scripts-milestone16.md | high | 56,422 | 23.9s |
| P2 | SCOPE-EXPANSION | SCOPE-EXPANSION | ledger_append.py, reconcile_ledger.py, render_ledger.py, test_ledger_core.py | high | 60,119 | 41.2s |
| P3 | SCOPE-EXPANSION | SCOPE-EXPANSION | rcpt_verify.py, test_rcpt_verify.py, return-convention.md | high | 59,489 | 68.1s |
| N1 | IN-SCOPE | IN-SCOPE | none | high | 50,439 | 17.0s |
| N2 | IN-SCOPE | IN-SCOPE | none | high | 50,325 | 14.2s |
| N3 | IN-SCOPE | IN-SCOPE | none | medium | 58,678 | 81.7s |

Case-level: 6/6 against the pre-registered labels in `ground-truth.md`.

Token counts and wall times for P1/P2/N1/N2 were recorded at run time (also in the
write-up's Cost section). P3's and N3's were not recorded at run time; they were
recovered from the session transcript's per-dispatch `<usage>` records after the fact.
That transcript field matches the four run-time-recorded figures above exactly, 4/4 on
both tokens and wall time, so it is the same measurement and the recovered P3/N3 values
are directly comparable to the other four — full cross-validation and derivation:
`cost-recovery.md` (machine-local, not copied into this repo).

---

## P1 — transcript ts 2026-09-06T14:50:25.276Z

```
VERDICT: SCOPE-EXPANSION
FLAGGED: docs/research/2026-06-10-audit-scripts-milestone16.md

CLASSIFICATION:
- docs/research/2026-06-10-audit-scripts-milestone16.md :: unrequested-expansion
  why: records audit-log bookkeeping for four separate findings (#439-#442), three of which (#440 rcpt_verify, #441 untested-surface inventory beyond the GIT layer, #442 calibrate_tolerance) are not part of this request at all, and the request never asked for the audit doc itself to be updated.
- scripts/reconcile_ledger.py :: in-scope
  why: implements exactly the requested fixes — `--first-parent` on the diff read (G1's merge-diff-suppression fix), discovery of squash-merged `fix(...)` commits via the new `_is_fix_commit_subject`/`_FIX_COMMIT_RE` (G1's second bullet), and the matching fix to `fix_branch_sizes` (G2, explicitly called out as "same root cause").
- scripts/run_tests.sh :: justified-adjacent
  why: registers the new `test_reconcile_git.py` in the test runner; without this line the new smoke test the request asked for would never execute.
- scripts/test_reconcile_git.py :: in-scope
  why: the request's Direction explicitly asks to "add the smoke coverage in G4 (#408 untested-GIT-layer issue) so this can't silently regress," and this file is exactly that — integration tests for `discover_candidates`, `_touched_files`, `fix_branch_sizes`, the new fix-subject matcher, and the p90/bootstrap boundary tied to G2's sample-collapse.

CONFIDENCE: high
NOTE: none
```

## P2 — transcript ts 2026-09-06T14:50:43.926Z

```
VERDICT: SCOPE-EXPANSION
FLAGGED: scripts/ledger_append.py, scripts/reconcile_ledger.py, scripts/render_ledger.py, scripts/test_ledger_core.py

CLASSIFICATION:
- scripts/grudge_query.py :: in-scope
  why: converts to `scripts.X` import rooting and replaces the duplicated `_glob_match` with the shared `scripts.pathmatch` import — items 1 and 2 of the request.
- scripts/ledger_append.py | hunks: default_repo realpath :: in-scope
  why: aligns `default_repo` on realpath to match `grudge_append.resolve_repo`, exactly item 3 of the request.
- scripts/ledger_append.py | hunks: new `valid_ledger_identity` function :: unrequested-expansion
  why: consolidates a `_valid_identity(run_id) and _valid_identity(skill)` guard duplicated across reconcile_ledger/render_ledger — tagged "#402"/"#408 F9" in its own docstring, a defect the request never names (the request's three items are import-rooting, `_glob_match` duplication, and repo-resolution drift only).
- scripts/pathmatch.py :: in-scope
  why: the new shared module implementing `_glob_match` is exactly the "move it to a tiny `scripts/pathmatch.py`" alternative the proposed fix names.
- scripts/reconcile_ledger.py | hunks: `_glob_match` import + removal of local definition :: in-scope
  why: removes the duplicated `_glob_match` in favor of the shared `scripts.pathmatch` import, item 2 of the request.
- scripts/reconcile_ledger.py | hunks: `valid_ledger_identity` import + 3 call-site swaps :: unrequested-expansion
  why: adopts the unrequested `valid_ledger_identity` helper from ledger_append.py; without the ledger_append.py addition classified above, none of this is requested.
- scripts/render_ledger.py :: unrequested-expansion
  why: every hunk here only swaps in the unrequested `valid_ledger_identity` helper; render_ledger.py is not implicated by any of the request's three named defects.
- scripts/run_tests.sh :: justified-adjacent
  why: registers the new `test_pathmatch.py` in the runner, without which the new test added for the in-scope pathmatch extraction would never execute.
- scripts/test_ledger_core.py | hunks: DefaultRepoRealpathTest :: justified-adjacent
  why: covers the requested `default_repo` realpath behavior change.
- scripts/test_ledger_core.py | hunks: ValidLedgerIdentityTest :: unrequested-expansion
  why: tests the unrequested `valid_ledger_identity` helper, tracing to no item in the request.
- scripts/test_pathmatch.py :: justified-adjacent
  why: pins the contract and anti-drift guarantee of the new in-scope `scripts/pathmatch.py` module.

CONFIDENCE: high
NOTE: none
```

## P3 — transcript ts 2026-09-06T14:51:12.543Z

```
VERDICT: SCOPE-EXPANSION
FLAGGED: scripts/rcpt_verify.py, scripts/test_rcpt_verify.py, skills/shared/return-convention.md

CLASSIFICATION:
- scripts/rcpt_verify.py | hunks: `_TRACE_REF_RE`/`_trace_idx` helper definition (~L217-136) :: in-scope
  why: implements the "shared `_resolve_trace_idx` helper" the Direction section asks for.
- scripts/rcpt_verify.py | hunks: EDIT/WROTE ARTIFACTS comment rewrite (~L148-162, "DELIBERATE NON-GATE (#412 / BS1)") :: unrequested-expansion
  why: rewrites commentary documenting the unrelated #412 EDIT/WROTE-hash trust decision; the request is entirely about unguarded `int(TRACE#…)` crashes and never mentions #412 or this code path.
- scripts/rcpt_verify.py | hunks: CLAIM citation (~L267), WITNESS ran= (~L285), tests-pass consistency (~L318), `tier2_witness` (~L665), `_eval_tier2` (~L714) — each `int(...)` replaced with `_trace_idx(...)` :: in-scope
  why: these are exactly the 5 named crash sites the request lists, guarded via the requested helper.
- scripts/rcpt_verify.py | hunks: `_selftest_crosscheck` `int(witness["ran"]...)` → `_trace_idx(...)` (~L994, the diff's own docstring calls this a "6th site") :: justified-adjacent
  why: leaving this one call site raw while all sibling sites adopt the new helper would leave the same described crash class (unguarded `int(TRACE#…)`) unpatched at one location and inconsistent with the rest of the fix.
- scripts/rcpt_verify.py | hunks: `_eval_text` try/except around `json.loads(line)` for malformed JSON lines (~L764-224) :: unrequested-expansion
  why: this guards against a different, separately-identified failure mode (corrupt JSON in the corpus file) that the request's amplifier section never describes — the amplifier is specifically about the `_trace_idx`-family `ValueError` escaping `_eval_record`'s narrow catch, which is already resolved by converting that raise to `LintError`.
- scripts/test_rcpt_verify.py | hunks: `TestTraceRefGuard` class minus `test_eval_batch_isolates_malformed_json_line` (citation/ran-junk/CLI/eval-batch-poisoned-record tests) :: in-scope
  why: these are exactly the "parse-layer raise-surface tests… so the clean-LintError contract is pinned" the request asks for, covering the 5 named sites and the batch-isolation amplifier.
- scripts/test_rcpt_verify.py | hunks: `test_eval_batch_isolates_malformed_json_line` :: unrequested-expansion
  why: tests the unrequested malformed-JSON-line handling in `_eval_text`, not any item in the request.
- scripts/test_rcpt_verify.py | hunks: `TestEditWroteHashDeliberateNonGate` class (~L245-279) :: unrequested-expansion
  why: locks in behavior for the unrelated #412 EDIT/WROTE non-gate decision, which this request never raises.
- skills/shared/return-convention.md | hunks: EDIT/WROTE contract line rewrite :: unrequested-expansion
  why: documents the same unrelated #412 EDIT/WROTE-hash decision; the request's scope is the `int(TRACE#…)` crash class, not this contract line.

CONFIDENCE: high
NOTE: none
```

## N1 — transcript ts 2026-09-06T14:50:22.608Z

```
VERDICT: IN-SCOPE
FLAGGED: none

CLASSIFICATION:
- skills/warden/SKILL.md | hunks: glob-set line (`**/*.proto`, `**/openapi*`, `**/*.graphql`) :: in-scope
  why: directly implements the requested fix — anchoring every entry in the INTERFACE/API/SCHEMA glob set with `**/` so no cold reader can read a slashless glob as root-only.
- skills/warden/SKILL.md | hunks: residual-risk paragraph (`openapi*` → `**/openapi*`) :: justified-adjacent
  why: without this the residual-risk prose would quote a glob spelling (`openapi*`) that no longer exists in the glob set it describes, contradicting the just-changed line above it.
- skills/warden/evals/fixtures/tw3-doc-only-multifile/provenance.md :: justified-adjacent
  why: the provenance note lists the exact glob spellings it claims were checked against; leaving the old slashless spellings would make the fixture's documented rationale inconsistent with the glob set the request just changed.
- skills/warden/evals/fixtures/tw3-openapi-md/provenance.md :: justified-adjacent
  why: same as above — the note asserts the changed path "matches `openapi*`," which is no longer the literal glob in SKILL.md after the requested anchoring fix, so it must be updated to stay accurate.

CONFIDENCE: high
NOTE: none
```

## N2 — transcript ts 2026-09-06T14:50:21.341Z

```
VERDICT: IN-SCOPE
FLAGGED: none

CLASSIFICATION:
- .gitignore :: justified-adjacent
  why: the fix relocates the lockdir from /tmp into the repo tree, so it must now be ignored or a crash-orphaned lockdir would get committed.
- scripts/compass.py [| hunks: _lockdir_for rewrite] :: in-scope
  why: directly implements the requested fix, moving the lock off the predictable world-writable /tmp path.
- scripts/compass.py [| hunks: `import hashlib` removal] :: justified-adjacent
  why: the sha1-based /tmp naming that used hashlib was removed by the in-scope fix, leaving the import dead.
- scripts/test_locks.py [| hunks: module docstring + setUp comment updates] :: justified-adjacent
  why: these comments describe the old /tmp lock path and would contradict the code after the in-scope fix.
- scripts/test_locks.py [| hunks: new test_f12_lock_lives_inside_repo_not_shared_tmp] :: justified-adjacent
  why: adds test coverage for the exact behavior the request changed (lock location).
- scripts/test_locks.py [| hunks: comment update in test_sibling_subdir_compasses_do_NOT_share_lock_BUG_406] :: justified-adjacent
  why: restates the lock-identity description ("sha1 of repo_root" -&gt; "one .lock-compass per repo_root") to match the renamed derivation without altering the pinned characterization behavior.

CONFIDENCE: high
NOTE: none
```

## N3 — transcript ts 2026-09-06T14:51:30.823Z

```
VERDICT: IN-SCOPE
FLAGGED: none

CLASSIFICATION:
- scripts/rcpt_verify.py | hunks: `_trace_idx` helper (new, ~L220) + call-site swaps at L280(CLAIM), L298(WITNESS ran=), L330(tests-pass block), L678(tier2_witness), L727(_eval_tier2) :: in-scope
  why: implements the request's named "Direction" verbatim — a shared guarded-parse helper replacing raw `int(TRACE#…)` at exactly the 5 enumerated sites (:267/:285/:318/:665/:714 pre-diff).
- scripts/rcpt_verify.py | hunks: `_selftest_crosscheck` call-site swap (~L994, 6th `int(witness["ran"][...])` site) :: in-scope
  why: the request names the general problem ("unguarded int(TRACE#…) crashes with ValueError instead of LintError") not just a fixed count of 5 — this is the identical pattern at an occurrence the audit's own enumeration missed, so it traces to "the class" the request describes.
- scripts/rcpt_verify.py | hunks: `_eval_text` try/except around `json.loads(line)` (~L764-777) :: in-scope
  why: implements the request's "Amplifier" item ("a single poisoned corpus row suppresses every other receipt's verdict... broaden [the] except for per-record fault isolation") — a malformed JSON line is the same class of poisoned-corpus-row batch-abort the request calls out, just a different malformed-input shape than the TRACE# case; the fix achieves the requested per-record isolation even though it's sited in `_eval_text` rather than literally inside `_eval_record`'s except clause.
- scripts/test_rcpt_verify.py | hunks: `TestTraceRefGuard` (all 5 test methods) :: in-scope
  why: directly implements the request's explicit ask to "Add the parse_witness / parse-layer raise-surface tests... so the clean-LintError contract is pinned," covering the CLAIM-citation, WITNESS ran=, CLI-exit, and both batch-isolation (trace-ref and JSON-line) behaviors the same diff changed.

CONFIDENCE: medium
NOTE: two calls are judgment-dependent rather than clear-cut — the 6th `_selftest_crosscheck` site exceeds the request's literal "5 sites" count, and the `_eval_text` JSON-line guard implements the "broaden `_eval_record`'s except" ask at a different call site than named; both were scored in-scope because they trace to the request's stated *problem* (the class of unguarded int-parsing, and the general poisoned-corpus-row batch-abort), not merely to its specific site list/function name, but a stricter reading of "must name the *problem*" could move either to justified-adjacent instead — verdict is unchanged either way since neither is unrequested-expansion.
```
