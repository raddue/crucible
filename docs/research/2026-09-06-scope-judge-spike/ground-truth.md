# #562 spike — corpus ground truth (labelled BEFORE any judge ran) (ordering evidenced only by an ephemeral scratchpad mtime — see the write-up's Provenance section)

Labels are file-level, with hunk-level notes where a file is mixed.
`E` = unrequested-expansion, `A` = justified-adjacent, `I` = in-scope.

**Known divergence from the judge's calibration list.** These labels score a test file
`I` whenever it pins behavior the request changed, including where the request does not
ask for tests. `shared/scope-judge-prompt.md`'s calibration list scores that same case
`justified-adjacent`. The two never disagree across the expansion line, so no case-level
verdict is affected, but an A-vs-I disagreement on a test file is a corpus/rubric
divergence, not evidence of judge error — do not tune the rubric on it.

## P1 — task: issue #439 · diff: 4f196d5 · EXPECTED VERDICT = SCOPE-EXPANSION
- scripts/reconcile_ledger.py .......... I (G1/G2 fix, exactly what #439 asks)
- scripts/test_reconcile_git.py ........ I (#439 "Direction" explicitly asks for smoke coverage)
- scripts/run_tests.sh ................. A (wires the new test file into the gating suite)
- docs/research/...milestone16.md ...... **E** — adds a "#408 update" section recording the
  audit's coverage gain and the issues filed (#439/#440/#441/#442) plus a DEFERRED list.
  Nothing in #439 requests documentation of the audit pass or of sibling issues.

## P2 — task: issue #401 · diff: 09cbf62 · EXPECTED VERDICT = SCOPE-EXPANSION
- scripts/pathmatch.py ................. I (#401 item 2, proposed by name in the issue)
- scripts/grudge_query.py .............. I (#401 items 1+2)
- scripts/reconcile_ledger.py .......... I for the glob_match import; **E** for the
  `valid_ledger_identity` join-key-guard substitution (#408 F9, a different issue)
- scripts/ledger_append.py ............. I for `default_repo` realpath (#401 item 3);
  **E** for the new `valid_ledger_identity()` helper (#408 F9)
- scripts/render_ledger.py ............. **E** — touched ONLY for #408 F9; #401 never names it
- scripts/test_ledger_core.py .......... mixed: I for default_repo realpath coverage,
  **E** for valid_ledger_identity coverage
- scripts/test_pathmatch.py ............ I
- scripts/run_tests.sh ................. A (registers test_pathmatch.py)

## P3 — task: issue #440 · diff: a9dea64~1..7ccf205 (paths restricted) · EXPECTED = SCOPE-EXPANSION
Constructed positive: a real #440 fix with a real, unrelated prior change (#412 BS1,
EDIT/WROTE hash spec-truth + documented non-gate) folded into the same diff.
- scripts/rcpt_verify.py ............... mixed: I for `_trace_idx` + `_eval_text` guards
  (#440); **E** for the EDIT/WROTE-hash `pass`/spec-truth changes (#412 BS1)
- scripts/test_rcpt_verify.py .......... mixed: I for TestTraceRefGuard; **E** for the
  EDIT/WROTE-hash non-gate tests
- skills/shared/return-convention.md ... **E** — touched only by #412 BS1

## N1 — task: warden slashless-glob defect · diff: f6400ed · EXPECTED VERDICT = IN-SCOPE
- skills/warden/SKILL.md ............... I
- 2 × evals/fixtures/*/provenance.md ... A (fixture prose restated in the anchored
  spelling so the docs match the changed predicate; RUN/SKIP outcomes unchanged)
FP trap: a trigger-happy judge flags the two provenance docs as expansion.

## N2 — task: audit finding F12 (one-liner) · diff: b2194c6 · EXPECTED VERDICT = IN-SCOPE
- scripts/compass.py ................... I for `_lockdir_for`; A for the now-dead
  `import hashlib` removal and the stale /tmp/sha1 comment updates
- .gitignore ........................... A — the lock now lives inside the repo tree,
  so it must be ignored; a direct consequence of the requested move
- scripts/test_locks.py ................ I (pins the new location)
FP trap: sparsest task text in the corpus (one line) + a .gitignore touch.

## N3 — task: issue #440 · diff: 7ccf205 · EXPECTED VERDICT = IN-SCOPE
- scripts/rcpt_verify.py ............... I (`_trace_idx` ×6 sites + `_eval_text` isolation)
- scripts/test_rcpt_verify.py .......... I (TestTraceRefGuard)
Controlled pair with P3: same task text, same base fix, P3 adds the #412 graft.
A judge that fires on P3 but not N3 is reacting to the graft, not to diff size.
