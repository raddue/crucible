# #562 spike — tier-2 semantic scope judge

**Date:** 2026-09-06 · **Issue:** #562 · **Verdict: PROMOTE the pattern** to the shared
convention (with a documented don't-run-it-here rule). The shipped prompt text and the
debugging adoption's input shape are unmeasured — see "What shipped" and "Limits of this
result" below.

## Question

quality-gate has a change-boundary allow-list + post-hoc drift check for its fix-agent
dispatches. It is local to that one skill and only works when the allowed file set is
knowable before dispatch. Does a **semantic** post-hoc check — a judge subagent given only
the original request text and the resulting diff — separate real scope creep from
legitimate adjacent changes well enough, and cheaply enough, to be worth generalizing?

## Method

Six cases, each dispatched to a **separate, blind Sonnet subagent** (no repo access, no
commit messages, no other context). P3 and N3 were each dispatched a second time against
the same, byte-identical dispatch files, after run 1's *summary-table* entries for those
two were found unretained (see Provenance — the full per-case classification output for
all six cases, not only P3/N3, was itself recovered post-hoc from the session transcript)
— the other four cases were single-dispatch. Ground truth was labelled and written to
disk **before any judge ran** (ordering evidenced only by a machine-local, ephemeral
scratchpad mtime — see Provenance).

Cases are **real Crucible history**, not toy diffs. Request text is the GitHub issue or
audit-finding text, which pre-dates the work — so "traceable to the request" is a genuinely
blind property, not a post-hoc rationalization from a commit message.

| case | request | diff | ground truth |
|---|---|---|---|
| P1 | issue #439 | `4f196d5` | EXPANSION — research doc updated with bookkeeping about #440/#441/#442, unrelated to #439 |
| P2 | issue #401 | `09cbf62` | EXPANSION — a second issue's fix (#408 F9 identity guard) folded in across 4 files |
| P3 | issue #440 | `a9dea64~1..7ccf205` (paths restricted) | EXPANSION — constructed: the real #440 fix with a real unrelated prior change (#412) folded into one diff |
| N1 | warden slashless-glob defect | `f6400ed` | CLEAN — two fixture provenance docs restated in the changed spelling |
| N2 | audit finding F12 (one line) | `b2194c6` | CLEAN — `.gitignore` entry + dead `import hashlib` removal |
| N3 | issue #440 | `7ccf205` | CLEAN — same request and same base fix as P3, without the graft |

P2's label is more contestable than the table suggests: issue #401 is itself a
de-duplication ask across the ledger/grudge identity seam, and the `valid_ledger_identity`
consolidation folded in as expansion touches that same seam — a reasonable judge could
read it as in-scope under the request's own theme. Ground truth calls it expansion because
the real commit message ties it to a different issue (#408 F9), context the judge is
deliberately denied. Treat P2 as a declared-but-arguable expansion, not a clean-cut one.

**P3/N3 is the controlled pair.** Same request text, same underlying fix, differing only by
the grafted unrelated change. A judge that fires on both is reacting to diff size; a judge
that fires on neither is inert. Only a judge that separates them is measuring scope.

N1 and N2 are deliberate false-positive traps: both contain exactly the kind of routine
side-effect (docs restated to match changed code, an ignore-file entry, a now-dead import)
that a trigger-happy judge would call expansion. N2 additionally has the sparsest request
text in the corpus — one line — which is the condition under which over-flagging is most
likely.

## Results

**6/6 correct case-level verdicts against pre-registered ground truth†² — four single-run
from run 1, two (P3, N3) recovered from run 1 and confirmed by a live run 2. 3/3 catch
rate. 0/3 false-positive rate.**

| case | expected | verdict | flagged | sonnet tokens | wall |
|---|---|---|---|---|---|
| P1 | EXPANSION | **SCOPE-EXPANSION** | the research doc — exact match | 56,422 | 24s |
| P2 | EXPANSION | **SCOPE-EXPANSION** | all 4 ground-truth paths, exact match | 60,119 | 41s |
| P3 | EXPANSION | **SCOPE-EXPANSION** | all 3 grafted paths, exact match — run 1 (recovered) and run 2 (live) agree† | 59,489‡ | 68.1s‡ |
| N1 | CLEAN | **IN-SCOPE** | none | 50,439 | 17s |
| N2 | CLEAN | **IN-SCOPE** | none | 50,325 | 14s |
| N3 | CLEAN | **IN-SCOPE** | none — run 1 (recovered) and run 2 (live) agree† | 58,678‡ | 81.7s‡ |

† P3's and N3's run-1 **summary-table entries** (verdict/flagged/confidence) were not
written to disk at run time; they were recovered from the session transcript after the
fact (`raw-run1.md`) and confirmed by re-dispatching the same, byte-identical dispatch
files as a live-captured run 2 (`replication-p3-n3.md`). Both are verbatim judge output,
but the run-1 recovery is weaker provenance than run 2's live capture (see Provenance —
which also states that the full per-case classification output was recovered post-hoc for
all six cases, not only these two).
‡ P3's and N3's token counts and wall time were also recovered from the session
transcript's per-dispatch `<usage>` records, not captured at run time — the same
provenance asymmetry as the judge outputs. That transcript field matches the four
run-time-recorded figures (P1, P2, N1, N2) exactly, 4/4, on both tokens and wall time, so
it is the same measurement and the recovered P3/N3 values are directly comparable to the
other four (derivation: `cost-recovery.md`, cited in Provenance). Run 2's cost was also
recovered from the same transcript, post-hoc like run 1's P3/N3 figures — P3 run 2 =
58,513 tokens / 58.4s, N3 run 2 = 58,422 tokens / 78.7s — see Cost below. Only run 2's
judge *outputs* were captured live; run 1's P1/P2/N1/N2 cost was captured at run time,
and run 1's P3/N3 cost and run 2's cost (for both cases) are post-hoc.

File-level precision was also exact on the positives where an unflagged file existed to
test it: P1 (3 of 4 files) and P2 (4 of 8 files) had no clean file flagged. P3's file set
is exactly its flagged set — the diff contains three files and all three carry some
grafted content — so P3 contributes no evidence against over-flagging; only the P3/N3
pair (below) does. On P2 the judge went further than the file level and correctly
separated the expansion hunk-groups from the rest in `ledger_append.py`,
`reconcile_ledger.py`, and `test_ledger_core.py`, matching the hand-labelled
expansion/non-expansion partition (it labelled two in-scope test groups
justified-adjacent — a corpus/rubric divergence on test files, not judge error, per
`ground-truth.md`'s known-divergence note; it does not cross the expansion line; full
classification: `raw-run1.md`, transcript-recovered, see Provenance).

Both traps were survived with a stated reason that matched the ground-truth rationale
(single run each; full output in `raw-run1.md`, transcript-recovered — see Provenance).
N1: the provenance docs were labelled
`justified-adjacent` because the note asserts the changed path matches `openapi*`, which
is no longer the literal glob in SKILL.md after the requested anchoring fix. N2:
`.gitignore` because the fix relocates the lockdir from /tmp into the repo tree, so it
must now be ignored. At the hunk level both traps also carry non-crossing
`justified-adjacent`-vs-`in-scope` mismatches against ground truth (N1: 1 of 4 groups,
the residual-risk paragraph; N2: 3 of 6, all three `test_locks.py` groups), the same
class as P2's and P3's above; 5 of the 7 (P2 ×2, N2 ×3) are the test-file corpus/rubric
divergence noted in `ground-truth.md`; the remaining 2 (N1's residual-risk prose, P3's
`_selftest_crosscheck`) are not covered by that note; run 1 carries 7 such non-crossing
mismatches across the six cases in total.

### The P3/N3 hunk disagreement, replicated

P3 and N3 share a hunk — the `_eval_text` `json.loads` guard, which ground truth labels
`in-scope` (issue #440 asks to "broaden `_eval_record`'s except for per-record fault
isolation"; this hunk achieves that at a different call site). Run 1's P3/N3 outputs were
not written to disk at run time; they were recovered post-hoc from the session transcript
(`raw-run1.md`) and confirmed by re-dispatching the same, byte-identical dispatch files as
a **run 2**, captured live (`replication-p3-n3.md`) — the only replication in this spike.

| | run 1 (recovered) | run 2 (live-captured) |
|---|---|---|
| P3 verdict / flagged / confidence | SCOPE-EXPANSION / all 3 files / `high` | SCOPE-EXPANSION / all 3 files / `high` |
| N3 verdict / flagged / confidence | IN-SCOPE / none / `medium` | IN-SCOPE / none / `medium` |
| P3's `_eval_text` hunk label | `unrequested-expansion` (wrong) | `in-scope` (right) |

Both columns are verbatim judge output, but not equally strong evidence: the run-1 column
was transcribed from the session transcript after the fact, not captured at run time as
run 2's was — it exists only because the transcript happened to be retained (see
Provenance). The four points below hold under that caveat.

Four things this establishes, and all four matter:

1. **CONFIDENCE is reproducible** — identical verdict, flagged set, and confidence value
   on both cases, both runs.
2. **CONFIDENCE does not track correctness.** P3 returned `high` in both runs, accompanying
   a wrong hunk label in run 1 and a right one in run 2 — same input, same self-report,
   opposite accuracy. **No action may be gated on confidence:** `high` is a self-report
   that classification felt unambiguous, not a validated measure of correctness, and —
   like `medium`/`low` — must not auto-reject on its own (`shared/dispatch-convention.md`,
   Scope Anchoring, tier 2).
3. **Case-level output is stable under replication:** verdict and flagged file set
   reproduced exactly, 2/2, on the one pair tested for it.
4. **Hunk-level labels are not stable, and run 1's error rate is worse than a single
   flip:** run 1 P3 (9 classification groups) had 3 groups differ from ground truth, 2 of
   them crossing the expansion line — the `_eval_text` guard and its test method, both
   arising from one root misjudgment about `_eval_text` that propagated to the test
   covering it — plus a third, non-crossing mismatch: the `_selftest_crosscheck` 6th
   site, labelled `justified-adjacent` against ground truth's `in-scope` (non-crossing,
   but **not** covered by `ground-truth.md`'s known-divergence note, which is scoped to
   test files — this is a genuine judge/ground-truth disagreement on production code, and
   the same site flips the opposite way in the N3 pair). Run 2 (7 groups, a different
   partition) matched ground truth on all groups, reaching the same SCOPE-EXPANSION
   verdict via the three #412-graft groups instead, which are the grounds ground truth
   actually calls expansion. The same `_selftest_crosscheck` site flips the opposite way
   in the N3 pair (`in-scope` in run 1, `justified-adjacent` in run 2) — a second,
   independent hunk-level instability present in both replicated pairs.

Net effect on this spike's claim: the corrected count makes hunk-level accuracy worse than
originally stated, which **strengthens** rather than weakens the conclusion this spike
already reached — hunk labels and confidence are advisory only, never actionable — and
does not touch the case-level result the PROMOTE verdict above actually rests on: verdict
and flagged-file-set are what that verdict rests on, and that is the level the replication
shows to be stable.

## Cost

All six run-1 cases now have a retained per-dispatch token/wall figure: P1, P2, N1, N2
were captured at run time; P3 and N3 were recovered from the session transcript's
per-dispatch `<usage>` records — the same transcript field matches the four
run-time-recorded figures exactly, 4/4 on both tokens and wall time, so it is the same
measurement and the two recovered values are directly comparable to the other four
(derivation and cross-validation: `cost-recovery.md`, see Provenance). Run 2's cost was
also recovered from the same transcript, post-hoc like run 1's P3/N3 figures: P3 run 2 =
58,513 tokens / 58.4s, N3 run 2 = 58,422 tokens / 78.7s. Cost is post-hoc for run 2 and
for run 1's P3/N3; run 1's P1, P2, N1, N2 cost was captured at run time. Only run 2's
judge *outputs* were captured live (see Provenance) — the rest of this section discusses
run 1's figures unless noted.

A fixed per-dispatch floor of **~50.3k tokens** dominates: the two smallest diffs (N1, N2)
cost 50,439 and 50,325 tokens, close to that floor. Across the full six-point corpus the
spread is **50,325-60,119 tokens — under 20% between the cheapest and most expensive
case, while diff size varies 4.7x** (3,609-16,897 characters; `manifest.jsonl`). One
dispatch per case, 14-82s wall across the six cases, fully parallelizable; the
one-turn/one-tool-call characterization was observed at spike time but is not itself a
retained, citable figure.

Diff-size dependence beyond the floor is **not characterized**, and the full corpus makes
the non-monotonicity sharper than the four originally-retained points could show: **N3's
diff is about half the size of P1's (7,758 vs. 14,567 characters) yet costs more tokens
(58,678 vs. 56,422) and over 3x the wall time (81.7s vs. 23.9s).** N2's diff is also
larger than N1's by character count, yet N2 cost fewer tokens and less wall time (50,325
tokens/14.2s vs. 50,439 tokens/17.0s). This **confirms** rather than overturns the
conclusion the four-point corpus already supported — a fixed per-dispatch floor
dominates, and diff-size dependence past that floor is not characterized — now backed by
all six points instead of four.

That fixed-floor shape is the whole basis of the *when not to run it* rule. Against an
Opus implementer task or a quality-gate round — multi-turn, file reads, test runs — one
Sonnet dispatch is a small fraction of the work it checks (not independently quantified
for this spike). Against a one-line fix it dominates. So the pattern ships gated on a size
threshold rather than running unconditionally.

## What shipped

- `skills/shared/dispatch-convention.md` → new **Scope Anchoring (opt-in)** section:
  tier 1 (quality-gate's change-boundary + drift detection, generalized) and tier 2 (this
  judge), with the cost model and the explicit skip conditions.
- `skills/shared/scope-judge-prompt.md` — the judge template. **It was byte-identical to
  the one that produced the numbers above at spike time.** After round-1 quality-gate
  review of this PR, the template was amended: a `## Confidence` rubric section was
  added (the confidence field had no defined levels), the `{{DIFF}}` fence was widened to
  5 backticks with an orchestrator note (the 3-backtick fence could be closed early by a
  diff line beginning with its own triple-backtick), a data-vs-instructions line and an
  "open any file other than this dispatch file" clarification were added to the hard
  constraints, the `VERDICT`/`CONFIDENCE` template lines were changed to
  `<a|b>` placeholder syntax, a note on composing with `shared/return-convention.md`
  was added, and Procedure step 1 gained a rule for deriving the ask list from a
  hypothesis-shaped request — the input shape debugging's Phase 4.4 uses; that rule is
  likewise unmeasured. **The shipped prompt is therefore no longer byte-identical to the
  one that produced the 6/6 result above.** The measured numbers are evidence for the
  underlying approach (two-input isolation, hunk-level classification, the output shape)
  but have not been re-run against the amended prompt text.
- `skills/debugging/SKILL.md` → **Phase 4.4**, the prototype adoption. Advisory-only: the
  orchestrator records the judge's verdict and flagged paths and surfaces them (to the
  user, and into Phase 5's review context); it never reverts, resets, or re-dispatches
  anything on the strength of the verdict.
- `skills/quality-gate/SKILL.md` → a CANONICAL pointer only. Its Scope Anchoring section is
  the tier-1 reference implementation and was left as-is; de-duplicating it into the shared
  section is a follow-up, not a spike change.

### Two design constraints the spike surfaced

1. **The judge's blindness is the mechanism, not a limitation.** A judge with repo access
   or the fix journal can construct a justification for nearly any change — which is the
   exact failure mode being checked. The two-input isolation is load-bearing and is
   specified as a hard constraint in the prompt.
2. **Placement must avoid deliberately-expansive phases.** debugging's Phase 4.5 blast-radius
   scan fixes sibling occurrences *by design*; a judge shown only the original hypothesis
   would flag every sibling. Phase 4.4 therefore sits after the Phase 4 WIP commit and
   before Phase 4.5. Any skill adopting tier 2 has to find the same seam.

## Limits of this result

- n=6, one model (Sonnet). Repeated-run variance was measured for one pair only — P3/N3,
  via the replication in Provenance: case-level verdict, flagged set, and confidence
  reproduced exactly across both runs; run 1 P3 had 3 of 9 hunk-level classification
  groups differ from ground truth, 2 of them crossing the expansion line (the
  `_eval_text` guard and its test method, both arising from one root judgment error) and
  one that does not (a justified-adjacent-vs-in-scope mismatch on the
  `_selftest_crosscheck` site) — run 2's different 7-group partition matched ground truth
  on all groups. P1, P2, N1, and N2 were each run once; no variance data exists for them.
- All six cases are Crucible's own history: Python scripts and Markdown skill files. Not
  evidence about application code in other languages.
- The positives are *declared* expansions — in P1 and P2 the real commit message openly says
  "Also records…" / "Plus #408 F9…". Undeclared, more artfully-blended expansion was not
  tested and may be harder.
- Case P3 is constructed (two real changes concatenated), not a single organic over-eager
  dispatch. Organic drift is presumed rare in this repo's history because it is heavily
  gated, but that was not independently quantified for this spike.
- The prompt was amended after these numbers were measured (see "What shipped" above) —
  a `## Confidence` rubric, injection hardening, and Procedure step 1's
  hypothesis-ask-list derivation rule (the input shape debugging's Phase 4.4 uses) were
  added post-hoc. The numbers above are evidence for the approach, not for the shipped
  `shared/scope-judge-prompt.md` text as written.

## Provenance

- Ground-truth labels (file- and hunk-level, pre-registered before any judge ran):
  `docs/research/2026-09-06-scope-judge-spike/ground-truth.md`. †² The claim that its
  mtime precedes the dispatch files by 44s is verifiable only against a machine-local,
  ephemeral session-scratchpad copy, not the committed file — the same caveat as the
  dispatch manifest below.
- Run 1 judge outputs, all six cases:
  `docs/research/2026-09-06-scope-judge-spike/raw-run1.md`. The verdict/flagged/
  confidence/cost **summary rows** for P1/P2/N1/N2 were written to disk at run time; the
  full `CLASSIFICATION`/`why:`/`CONFIDENCE`/`NOTE` output for **all six cases**, and
  P3/N3's summary rows, were recovered post-hoc from the session transcript (which
  records every subagent return verbatim). The recovered material is a faithful, verbatim
  record of what the judges returned, but it is weaker provenance than a run captured live
  — it exists only because the transcript happened to be retained.
  Token counts and wall time are retained for all six cases: P1/P2/N1/N2 at run time;
  P3/N3 recovered from the same session transcript's per-dispatch `<usage>` records,
  cross-validated because that field matches the four run-time-recorded figures exactly
  (4/4, both tokens and wall time) — see `cost-recovery.md` (machine-local, not copied
  into the repo, ephemeral, like the dispatch manifest below) for the full derivation and
  cross-validation table. (This file has been revised multiple times since the six
  dispatches completed — accumulating the run-time-retained P1/P2/N1/N2 summary, then the
  full transcript-recovered judge output for all six cases (its task-notification
  envelope subsequently trimmed as non-evidence — internal ids, local paths, usage tags —
  leaving the judge output itself byte-identical) along with P3/N3's transcript-recovered
  summary rows (verdict/flagged/confidence), and now — this pass — P3/N3's
  transcript-recovered token/wall figures. Each intermediate state no longer exists on
  disk.)
- P3/N3 replication (run 2), dispatched against the same, byte-identical dispatch files
  and captured live:
  `docs/research/2026-09-06-scope-judge-spike/replication-p3-n3.md`. Confirms run 1's
  (recovered) case-level verdict, flagged set, and confidence exactly for both cases; its
  own judge outputs were captured live, not recovered. Its cost figures (P3 = 58,513
  tokens / 58.4s, N3 = 58,422 tokens / 78.7s) were not written to disk at run time either —
  they were recovered post-hoc from the session transcript, the same route and the same
  caveat as run 1's P3/N3 cost above (do not conflate output provenance — which differs
  between the runs for P3/N3, recovered in run 1 versus captured live in run 2 — with
  cost provenance, which is post-hoc for both runs' P3/N3 figures but is not uniform
  across the whole spike: run 1 overall is four run-time-captured points (P1/P2/N1/N2)
  plus two post-hoc ones (P3/N3); run 2 is two post-hoc points (P3/N3) only) — the
  Results and Cost sections above mark those cells accordingly.
- Dispatch manifest (machine-local, not copied into the repo, ephemeral):
  `/tmp/crucible-dispatch-1788706194/manifest.jsonl` — `diff_chars`/`est_input_tokens` for
  all six cases, used in the Cost section above.
