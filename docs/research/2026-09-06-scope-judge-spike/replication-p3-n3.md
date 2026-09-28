# P3 / N3 replication — 2026-09-06, run 2

Why: `raw-run1.md` (run 1, 07:51 state) recorded P1/P2/N1/N2 only; P3 and N3 were left
"(pending)" and their outputs were not written to disk at run time. That evidence gap was
caught in review and this replication closed it. The ORIGINAL dispatch files were still on
disk and byte-identical, so re-running them is a true replication of run 1's inputs, not a
new experiment:
  /tmp/crucible-dispatch-1788706194/3-scope-judge.md  (P3)
  /tmp/crucible-dispatch-1788706194/6-scope-judge.md  (N3)
Model: Sonnet, one dispatch each, no repo access (same as run 1).

## Case-level (compared against ground-truth.md, pre-registered)

| case | expected | run-1 verdict | run-2 verdict | run-1 flagged | run-2 flagged | run-1 conf | run-2 conf |
|---|---|---|---|---|---|---|---|
| P3 | SCOPE-EXPANSION | SCOPE-EXPANSION | SCOPE-EXPANSION | all 3 files | all 3 files | high | high |
| N3 | IN-SCOPE | IN-SCOPE | IN-SCOPE | none | none | medium | medium |

Case-level verdict, flagged set, and CONFIDENCE all reproduced exactly, 2/2.

## Hunk-level: 3 of P3 run 1's 9 groups differ from ground truth, 2 crossing the expansion line

`scripts/rcpt_verify.py`, the `_eval_text` try/except around `json.loads`, and its test
`test_eval_batch_isolates_malformed_json_line` (inside `TestTraceRefGuard` in
`scripts/test_rcpt_verify.py`):
  ground truth ... in-scope for both (#440's "per-record fault isolation" amplifier,
                    and the test covering it)
  P3 run 1 `_eval_text` ......................... unrequested-expansion   <- WRONG
  P3 run 1 `test_eval_batch_isolates_..._line` ... unrequested-expansion   <- WRONG (same
                                                                              root cause)
  P3 run 2 `_eval_text` ......................... in-scope (its own group)   <- RIGHT
  P3 run 2 `test_eval_batch_isolates_..._line` .. folded into TestTraceRefGuard
                                                   :: in-scope ............... <- RIGHT
  N3 run 1 `_eval_text` ......................... in-scope                <- RIGHT
  N3 run 2 `_eval_text` ......................... in-scope                <- RIGHT

`scripts/rcpt_verify.py`, the `_selftest_crosscheck` 6th `int(TRACE#...)` site (~L994) —
ground truth labels every `_trace_idx` site `I` (`ground-truth.md` P3: "`_trace_idx` +
`_eval_text` guards"; N3: "`_trace_idx` x6 sites") — a THIRD group that does not match:
  P3 run 1 `_selftest_crosscheck` ............... justified-adjacent      <- WRONG (does
                                                                              not cross
                                                                              the expansion
                                                                              line)
  P3 run 2 (folds into "all call sites :: in-scope") ...................... RIGHT
  N3 run 1 `_selftest_crosscheck` ............... in-scope                <- RIGHT
  N3 run 2 `_selftest_crosscheck` ............... justified-adjacent      <- WRONG (flips
                                                                              the other way)

Both `_eval_text` errors trace to one root misjudgment: P3 run 1 mis-scoped the
`_eval_text` guard as `unrequested-expansion`, and that misjudgment propagated to the
test covering the same code, which run 1 labelled `unrequested-expansion` too. The third
mismatch is independent — a `justified-adjacent`-vs-`in-scope` label on
`_selftest_crosscheck` that does not cross the expansion line — but this one is **not**
covered by `ground-truth.md`'s known-divergence note, which is scoped to test files: it
is a genuine judge/ground-truth disagreement on production code, and the same site flips
the opposite way in the N3 pair below. So run 1 P3's 9
classification groups carry 3 labels that differ from ground truth, not 2 — 2 of them
crossing the expansion line (one root judgment error) plus this one that does not.

Run 2's P3 (a different, 7-group partition that folds the malformed-JSON test into
`TestTraceRefGuard`) matched ground truth on the `_eval_text` pair, and instead reached
its SCOPE-EXPANSION verdict via the three #412-graft groups (ARTIFACTS hash comment
rewrite, TestEditWroteHashDeliberateNonGate, return-convention.md) — the correct grounds,
and the same grounds the ground truth labels E. Run 2's P3 also folded
`_selftest_crosscheck` into "all call sites :: in-scope," matching ground truth — run 2
P3 matches ground truth on all 7 of its groups.

Run 1's N3 NOTE named two hunks — `_selftest_crosscheck` and `_eval_text`; run 2's named
`_selftest_crosscheck` only. Both runs flagged the 6th site as judgment-dependent; only
run 1 also flagged `_eval_text`.

## What this establishes, precisely

1. CONFIDENCE is REPRODUCIBLE: identical values on both cases across two runs.
2. CONFIDENCE does NOT track correctness: P3 returned `high` in both runs, accompanying a
   WRONG hunk label in run 1 and a RIGHT one in run 2. Same input, same self-report,
   opposite accuracy. Any rule keying an action on `high` is unsupported.
3. Case-level output (verdict + flagged file set) is STABLE under replication, 2/2.
4. Hunk-level labels are NOT stable: run 1 P3 had 3 of 9 groups differ from ground truth,
   2 of them crossing the expansion line (one root cause, propagated to its test) and a
   third that does not (a justified-adjacent-vs-in-scope mismatch on
   `_selftest_crosscheck`); run 2's different 7-group partition matched ground truth on
   all groups. The same `_selftest_crosscheck` site also flips the opposite way across
   the N3 pair — a second, independent hunk-level instability present in both replicated
   pairs.

This is the first variance data in the spike. n=2 cases x 2 runs — still small, but it is
measured rather than assumed, and it replaces run 1's unretained P3/N3 numbers.

## Cost (recovered post-hoc)
Token counts and wall time were not captured at run time for this replication (run 2).
They were recovered post-hoc from the session transcript's per-dispatch `<usage>` records
— the same route and the same caveat as run 1's P3/N3 cost figures (see `raw-run1.md` and
`cost-recovery.md`): P3 run 2 = 58,513 tokens / 58.4s, N3 run 2 = 58,422 tokens / 78.7s.
Unlike cost, this replication's judge *outputs* (below) were captured live, not
recovered — do not conflate the two provenances (see the write-up's Cost section).

---

## Run 2 — raw judge outputs

Captured at run time from the two subagent returns (Sonnet, one dispatch each, no repo
access), against the same byte-identical dispatch files run 1 used.

### P3 — run 2

```
VERDICT: SCOPE-EXPANSION
FLAGGED: scripts/rcpt_verify.py, scripts/test_rcpt_verify.py, skills/shared/return-convention.md

CLASSIFICATION:
- scripts/rcpt_verify.py | hunks: @@ -217,+22 (_TRACE_REF_RE/_trace_idx helper) :: in-scope
  why: implements the requested shared trace-index guard helper (Direction: "Shared _resolve_trace_idx helper... isdigit() or tokenize").
- scripts/rcpt_verify.py | hunks: @@ -280,-298,-330,-678,-727,-994 (int(...) -> _trace_idx(...) at all call sites) :: in-scope
  why: applies the shared guard "at all 5 sites" as the request's Direction explicitly asks.
- scripts/rcpt_verify.py | hunks: @@ -764,+15 (_eval_text try/except around json.loads) :: in-scope
  why: implements "per-record fault isolation" for the --eval batch path the request's Amplifier section calls for (a poisoned line must not abort the whole batch).
- scripts/rcpt_verify.py | hunks: @@ -245,13 +261,18 (ARTIFACTS EDIT/WROTE hash comment rewrite, #412) :: unrequested-expansion
  why: documents/relitigates the separate #412 "deliberate non-gate" decision about EDIT/WROTE hash verification; the request is scoped to the int()/ValueError crash class (#440) and never mentions ARTIFACTS-hash gating.
- scripts/test_rcpt_verify.py | hunks: TestTraceRefGuard class :: in-scope
  why: is exactly the "parse_witness / parse-layer raise-surface tests... so the clean-LintError contract is pinned" the request's Direction asks for.
- scripts/test_rcpt_verify.py | hunks: TestEditWroteHashDeliberateNonGate class :: unrequested-expansion
  why: locks down #412's EDIT/WROTE hash non-gate behavior, a separately-identified concern the request does not mention or ask to be tested.
- skills/shared/return-convention.md | hunks: @@ -150,7 +150,7 (EDIT/WROTE hash-verification wording) :: unrequested-expansion
  why: rewrites the contract prose for the #412 EDIT/WROTE hash decision, which traces to no item in this request (this request's scope is the TRACE# int()/ValueError crash class).

CONFIDENCE: high
NOTE: none
```

### N3 — run 2

```
VERDICT: IN-SCOPE
FLAGGED: none

CLASSIFICATION:
- scripts/rcpt_verify.py [| hunks: _TRACE_REF_RE + _trace_idx helper; call-site swaps at lint_receipt CLAIM/WITNESS/tests-pass blocks (~L280/298/330), tier2_witness (~L678), _eval_tier2 (~L727)] :: in-scope
  why: directly implements the requested "shared _resolve_trace_idx helper... applied at all 5 sites" fix for the 5 named unguarded-int production sites.
- scripts/rcpt_verify.py [| hunks: _selftest_crosscheck idx parse (~L994, was ~L970)] :: justified-adjacent
  why: same unguarded int(TRACE#) pattern the shared helper was built to close; leaving this one call site on raw int() would keep an identical hole in the trust boundary the fix otherwise seals, though it wasn't among the 5 sites the request enumerated by line number.
- scripts/rcpt_verify.py [| hunks: _eval_text try/except around json.loads] :: in-scope
  why: implements the request's "broaden _eval_record[-path]'s except for per-record fault isolation" amplifier fix — a malformed line must be classified per-record, not abort the whole --eval batch, and this is the point in the read loop where that isolation has to happen since no record object exists yet to hand to _eval_record.
- scripts/test_rcpt_verify.py [| hunks: TestTraceRefGuard class, all 5 test methods] :: in-scope
  why: request's Direction explicitly asks to "Add the parse_witness / parse-layer raise-surface tests... so the clean-LintError contract is pinned," and these tests cover exactly the citation/witness malformed-TRACE# repros and the batch-isolation amplifier described in the request.

CONFIDENCE: medium
NOTE: the _selftest_crosscheck site (~L994) is not one of the 5 line numbers the request enumerated, so its justified-adjacent classification rests on judgment about "same class, uncounted instance" rather than an explicit calibration example.
```

## Provenance asymmetry (stated because it matters)

Run 2's outputs were captured at run time. Run 1's were recovered from the session
transcript after the fact (see `raw-run1.md`). Both are verbatim, but they are not equally
strong evidence, and the run-1 recovery only became possible because the transcript happened
to be retained. This asymmetry is the single clearest practical lesson of the spike: a
scope-judge adoption must write the judge's output to disk at dispatch time.
