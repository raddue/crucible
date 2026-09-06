# #562 spike — tier-2 semantic scope judge

**Date:** 2026-09-06 · **Issue:** #562 · **Verdict: PROMOTE** (with a documented
don't-run-it-here rule)

## Question

quality-gate has a change-boundary allow-list + post-hoc drift check for its fix-agent
dispatches. It is local to that one skill and only works when the allowed file set is
knowable before dispatch. Does a **semantic** post-hoc check — a judge subagent given only
the original request text and the resulting diff — separate real scope creep from
legitimate adjacent changes well enough, and cheaply enough, to be worth generalizing?

## Method

Six cases, each dispatched to a **separate, blind Sonnet subagent** (one dispatch, no repo
access, no commit messages, no other context). Ground truth was labelled and written to
disk **before any judge ran**.

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

**P3/N3 is the controlled pair.** Same request text, same underlying fix, differing only by
the grafted unrelated change. A judge that fires on both is reacting to diff size; a judge
that fires on neither is inert. Only a judge that separates them is measuring scope.

N1 and N2 are deliberate false-positive traps: both contain exactly the kind of routine
side-effect (docs restated to match changed code, an ignore-file entry, a now-dead import)
that a trigger-happy judge would call expansion. N2 additionally has the sparsest request
text in the corpus — one line — which is the condition under which over-flagging is most
likely.

## Results

**6/6 correct case verdicts. 3/3 catch rate. 0/3 false-positive rate.**

| case | expected | verdict | flagged | sonnet tokens | wall |
|---|---|---|---|---|---|
| P1 | EXPANSION | **SCOPE-EXPANSION** | the research doc — exact match | 56,422 | 24s |
| P2 | EXPANSION | **SCOPE-EXPANSION** | all 4 ground-truth paths, exact match | 60,119 | 41s |
| P3 | EXPANSION | **SCOPE-EXPANSION** | all 3 grafted paths, exact match | 59,489 | 68s |
| N1 | CLEAN | **IN-SCOPE** | none | 50,439 | 17s |
| N2 | CLEAN | **IN-SCOPE** | none | 50,325 | 14s |
| N3 | CLEAN | **IN-SCOPE** | none | 58,678 | 82s |

File-level precision was also exact on the positives — no clean file was flagged in any of
the three. On P2 the judge went further than the file level and correctly split
`ledger_append.py`, `reconcile_ledger.py`, and `test_ledger_core.py` into in-scope and
expansion hunk-groups, matching the hand-labelled split.

Both traps were survived with the right *reason*, not by luck. N1: the provenance docs were
labelled `justified-adjacent` because "the note asserts the changed path matches `openapi*`,
which is no longer the literal glob after the requested anchoring." N2: `.gitignore` because
"the fix relocates the lockdir into the repo tree, so it must now be ignored."

### The one disagreement, and why it is the most useful result

P3 and N3 share a hunk — the `_eval_text` `json.loads` guard. P3's judge called it
`unrequested-expansion`; N3's judge called it `in-scope`. Ground truth says in-scope, so
P3's call is a hunk-level over-flag.

It did not change either verdict, and it is genuinely arguable: issue #440 asks to "broaden
`_eval_record`'s except for per-record fault isolation" and the change achieves that at a
different call site for a different malformed-input shape.

The load-bearing part: **N3's judge returned `CONFIDENCE: medium` and named this exact hunk
as the reason**, unprompted — "a stricter reading could move either to justified-adjacent
instead — verdict is unchanged either way." Every other case returned `CONFIDENCE: high`.
Self-reported confidence tracked real ambiguity on the one case that had any. That is what
makes the verdict safe to act on: high-confidence expansion is worth a re-dispatch,
medium/low is advisory only.

## Cost

Two payload sizes give a rough scaling law: **~45k fixed + ~2.7× the diff's own token
size**, one dispatch, one turn, one tool call (reading its own dispatch file), 14–82s wall,
fully parallelizable. The cost is dominated by fixed per-subagent overhead, not by the diff.

That shape is the whole basis of the *when not to run it* rule. Against an Opus implementer
task or a quality-gate round — multi-turn, file reads, test runs — one Sonnet dispatch is
single-digit percent of the work it checks. Against a one-line fix it dominates. So the
pattern ships gated on a size threshold rather than running unconditionally.

## What shipped

- `skills/shared/dispatch-convention.md` → new **Scope Anchoring (opt-in)** section:
  tier 1 (quality-gate's change-boundary + drift detection, generalized) and tier 2 (this
  judge), with the cost model and the explicit skip conditions.
- `skills/shared/scope-judge-prompt.md` — the judge template, **byte-identical to the one
  that produced these numbers**.
- `skills/debugging/SKILL.md` → **Phase 4.4**, the prototype adoption.
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

- n=6, single run per case, one model (Sonnet). No variance measurement across repeated
  runs of the same case — the P3/N3 disagreement on a shared hunk is a hint that hunk-level
  labels are less stable than case-level verdicts.
- All six cases are Crucible's own history: Python scripts and Markdown skill files. Not
  evidence about application code in other languages.
- The positives are *declared* expansions — in P1 and P2 the real commit message openly says
  "Also records…" / "Plus #408 F9…". Undeclared, more artfully-blended expansion was not
  tested and may be harder.
- Case P3 is constructed (two real changes concatenated), not a single organic over-eager
  dispatch. Organic drift is rare in this repo's history precisely because it is heavily
  gated — a search of 120 commits found only two self-declared instances.
