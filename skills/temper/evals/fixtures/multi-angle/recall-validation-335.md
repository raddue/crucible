# Recall validation — `sessionkit` multi-angle fixture (#335 / AC6 / I10)

The **live** standalone-delve recall run that [`detection-matrix.md`](detection-matrix.md)
defers to #335 ("the per-harness recall validation is #335's job"). #333 authored the
fixture and recorded the *designed* diagonal matrix; this file records the **actual
runtime result** of running the full-7-angle standalone-delve fan-out against that
fixture on a real harness.

> **Scope (filed #335 decision): Claude Code ONLY.** OpenCode runtime validation was
> downgraded to the non-gating follow-up **#337**. The harness-adapter design references
> a two-harness (#335) validation; the *filed ticket* scope wins — this file validates the
> **Claude-Code parallel-dispatch path** only. The OpenCode sequential-fallback floor is
> #337's job. The stale OpenCode **"#335" pointers** in `shared/harness-adapter.md` (the
> complete set, verified by grep — these are the OpenCode-half "#335" references that must
> move; the Claude-Code "Validated #335" rows at lines 28 and 269 are CORRECT and stay, and
> the model-enforcement cross-links at lines 122/133 are #352 territory, not OpenCode) are
> flagged for the #336 docs/migration pass to reconcile to **#337**:
> - **line 21** milestone-framing paragraph — "validates Claude Code + OpenCode at runtime (#335)"
>   (the OpenCode half is stale; only the Claude-Code half is validated here)
> - **§1** supported-harnesses table, OpenCode row (line 29) — "Validated this milestone (#335)"
> - **Mapping 1b** (line 118), OpenCode row — "#335 confirms" (the UNCONFIRMED *status* is
>   accurate; it is the "#335 confirms" *pointer* that is stale, since this file defers all
>   OpenCode runtime confirmation — incl. the `agent:`-profile model-pin question — to #337)
> - **§8** OpenCode manifest heading (line 298, "validated #335 — BYO reference harness")
>   **and** line 302 ("#335's confirmation")
> - **§8** Claude-Code plugin-note (line 287) — *borderline / by-reference*: cross-refs the
>   OpenCode row's "#335 confirms" status, so it follows once that row is reconciled
> - **line 340** drift-risk note — "the #335 portability validation (Claude Code + OpenCode
>   against the same fixture)" (the OpenCode half is stale)
>
> Each of the above reconciles to **#337**; this enumeration is complete so it can drive the
> #336 reconcile pass.

## What was validated

**AC6 runtime portion (Claude-Code scope), in two parts:**

1. **Install + run smoke** — `delve` / `temper` / `audit` install per the
   `shared/harness-adapter.md` §8 Claude-Code manifest and are invokable.
2. **Recall floor** — a **standalone** `delve` run over the **full 7-angle set** (not
   temper's 3-angle bug subset — a different path against the same fixture) on the
   **Claude-Code parallel-dispatch path** surfaces **≥ N−1 of N** planted bugs, N = 7.

## 1. Install + run smoke — PASS

Per `shared/harness-adapter.md` §8 (Claude Code):

| Component | Action | Result |
|---|---|---|
| `delve` skill | `ln -sf skills/delve ~/.claude/skills/delve` | symlinked; `SKILL.md` `name: delve` resolves; appears in the live skill registry |
| `temper` skill | (already symlinked) | `name: temper` resolves |
| `audit` skill | (already symlinked) | `name: audit` resolves |
| `crucible-red-team` agent def | `~/.claude/agents/crucible-red-team.md` | resolves, `model: opus` |
| `crucible-qg-judge` agent def | symlinked | resolves, `model: sonnet` |
| `crucible-qg-verifier` agent def | symlinked | resolves, `model: sonnet` |
| `crucible-qg-fix` agent def | symlinked | resolves, `model: inherit` |

> **Install gap found and closed:** `delve` (authored in #331) had never been symlinked
> into `~/.claude/skills/`. #335's install step caught and closed it — exactly the
> out-of-band install check the manifest exists to be.
>
> **Pre-existing cruft noted (not fixed here):** a stray broken `*` glob symlink at
> `~/.claude/agents/*` → `…/agents/*` (an unexpanded-glob artifact). Harmless, machine-local,
> outside the repo; flagged, not in #335's scope.

## 2. Recall floor — PASS (7/7 kept, intended-angle isolation)

### Method (the validated path)

- **Standalone `delve`, full 7-angle set, `effort=high` (recall-biased).** Not temper —
  no merge verdict, no `external_candidates`; one fan-out, then the verify gate.
- **Claude-Code parallel-dispatch path (Mapping 3):** the seven finder angles were
  dispatched as **seven parallel Task/Agent subagents in a single turn** — the concrete
  Claude-Code parallel primitive, not the sequential fallback (§5, which is #337's path).
- **Finders ran BLIND.** Each subagent was given only its own angle definition
  (`shared/delve-engine.md` §4) and the on-disk scope (`planted.diff` + the `before/` and
  `after/` trees). No finder was told the plant count, the plant locations, or that the
  matrix is diagonal. This is what makes the recall number meaningful.
- **Verify gate — actually run on all 7.** Per `delve-engine.md` §6, delve's output is the
  **KEPT set after the verify gate**, so the gate was run on every candidate, not just the
  bug angles. For the three bug-angle plants (P1–P3) the decisive verdict is the
  deterministic `selftest.py` run (CONFIRMED = reproduced). For the four quality-angle
  plants (P4–P7) the gate was a second parallel fan-out of four adversarial verifiers, each
  adjudicating per `delve-engine.md` §5 and instructed to **REFUTE before accepting** — i.e.
  their job was to confirm each candidate is a **genuine smell** (not a REFUTE-worthy
  non-smell) **and behaviorally correct** (a quality finding, not a misclassified bug).
  All four cleared that bar. The resulting **PLAUSIBLE / non-gating** verdict then follows
  from the §5 quality *cap* **by convention** — the contract caps quality-angle records at a
  non-gating verdict — **not** from the gate attempting and failing to reproduce anything
  (per delve-engine §5, a `PLAUSIBLE` on a quality record does not mean a failed repro).
  KEPT output is therefore **7/7 = 3 CONFIRMED + 4 PLAUSIBLE**.

### Dispatch evidence (the §2b-style on-disk proof)

The fan-out was the real Claude-Code parallel primitive, not the sequential fallback. The
seven finder angles were dispatched as **seven parallel Task/Agent subagents in a single
orchestrator turn**, and Claude Code wrote a per-subagent transcript for each at
`<project-session>/subagents/agent-<id>.jsonl`. All seven live under session
`3ba41fbb-b847-49d9-8658-08f65eb4aeb8/subagents/`, and each transcript's **assistant**
records carry `message.model = claude-opus-4-8`:

```
a1cdba1add44b7461  a7b8fc6ae8e32780d  a09a620e7781a87ef  ad79c6b677f325502
a99b44cd5a3a18998  a1d1aac2a1d24217c  a80c424c25cd9a0da
```

This is the same on-disk-transcript rigor `shared/harness-adapter.md` §2b demands for the
model-enforcement guarantee — it proves the run actually exercised the parallel fan-out, not
the sequential fallback. The proof the seven finders went out in a **single** orchestrator
turn (genuine parallel fan-out, not sequential) is that all seven finder `Task`/`Agent` tool_use
blocks share **one** assistant API message id (`msg_01TGjbPczhSJxTEZrrf3Z9S1`); a reader
should not misread the slightly staggered on-disk transcript timestamps (streamed-write
stagger) as sequential dispatch. The four verify-gate verifiers (P4–P7) were likewise
dispatched in parallel as a **second** fan-out turn, their four `Task`/`Agent` blocks sharing one
assistant message id (`msg_01HSrZ2jsoucSRxfw9xPePU3`, carrying exactly the 4 P4–P7 verifier
`Agent` blocks).

This transcript-based parallel-dispatch proof is **machine-local** — it lives in the
session's on-disk subagent transcripts under
`3ba41fbb-b847-49d9-8658-08f65eb4aeb8/subagents/`, not committed to the repo — unlike the
P1–P3 runtime reproduction, which is re-derivable from the committed fixture via
`selftest.py`; this is an honest scope note (mirroring the §2b enforcement-proof's own
machine-local caveat), not a weakness: the zero-tolerance bug-plant bar (D_bug = 3) is
already cleared by the reproducible CONFIRMED core independent of any transcript.

### Verify-gate subsection — the 4 quality-plant verdicts (P4–P7)

Four parallel adversarial verifiers, each instructed to REFUTE before accepting, adjudicated
the four quality candidates per `delve-engine.md` §5 — confirming each is a genuine smell
(not a REFUTE-worthy non-smell) and behaviorally correct (not a misclassified bug). All four
KEPT as PLAUSIBLE — the non-gating verdict here is the §5 quality cap by convention, not a
failed reproduction:

- **P4** `store.py:60` `last_seen` reuse → **PLAUSIBLE / Minor** — `last_seen` inlines
  `int(time.time())`, byte-identical to the already-imported `_now()` it uses elsewhere
  (lines 49/77); a real reuse smell, no behavioral failure.
- **P5** `store.py:62` `has_live_session` simplification → **PLAUSIBLE / Suggestion** —
  every path returns the correct boolean (None→False, valid→True, invalid→False); a
  correct-but-convoluted if/else ladder that collapses to
  `return token is not None and verify_token(...)`; real simplification smell, not a bug.
- **P6** `store.py:81` `live_fraction` efficiency → **PLAUSIBLE / Minor** —
  `total = len(self._by_user)` is genuinely loop-invariant (dict unmutated during iteration),
  recomputed every pass; result correct for all inputs (empty store guarded by the line-75
  early return); real correct-but-wasteful smell, not a bug.
- **P7** `store.py:86` `audit_dump` altitude → **PLAUSIBLE / Minor** — `audit_dump`
  correctly writes one line per stored user, but its disk-IO lives inside the documented
  in-memory domain class, contradicting `config.py`'s "ONLY function that touches the
  filesystem" / IO-at-the-edge contract; a real but non-gating layering smell.

### Result — per-plant recall

The **primary recall score is intended-angle isolation**: a plant counts as recalled only if
**its own intended angle** caught it. By that strict measure recall is **7/7** (each row's
intended angle is checked ✓ below). The verify-gate verdict column is the KEPT status of each
candidate post-gate.

| Plant | Intended angle | Intended angle caught it? | Verify-gate verdict |
|---|---|---|---|
| **P1** boundary `<`/`<=` (`tokens.py:66`) | line-by-line | line-by-line ✓ | **CONFIRMED** (runtime repro) |
| **P2** revoked check deleted (`tokens.py` verify_token) | removed-behavior | removed-behavior ✓ | **CONFIRMED** (runtime repro) |
| **P3** `uid`→`user_id` (`store.py:26` reader ↔ `tokens.py:31,42` writer — `serialize_claims` + `issue_token` `user_id` rename) | cross-file | cross-file ✓ | **CONFIRMED** (runtime repro) |
| **P4** `last_seen` re-implements `_now()` (`store.py:60`) | reuse | reuse ✓ | **PLAUSIBLE** (verify gate) — Minor |
| **P5** `has_live_session` convolution (`store.py:62`) | simplification | simplification ✓ | **PLAUSIBLE** (verify gate) — Suggestion |
| **P6** `live_fraction` loop-invariant `len()` (`store.py:81`) | efficiency | efficiency ✓ | **PLAUSIBLE** (verify gate) — Minor |
| **P7** `audit_dump` file-IO (`store.py:86`) | altitude | altitude ✓ | **PLAUSIBLE** (verify gate) — Minor |

**Recall = 7 / 7** by intended-angle isolation. KEPT post-verify-gate = **7/7
(3 CONFIRMED + 4 PLAUSIBLE)**. Floor is `D − 1 = 6`; **margin = 1 plant, fully verified.**

> **Designed-vs-runtime observation (all angles).** The #333 `detection-matrix.md` records the
> *designed* diagonal — "each plant detected by exactly its intended angle and by no other."
> At `effort=high` the #335 **live** run shows this diagonal does **not** hold for **6 of the
> 7** plants — co-detection is pervasive, across BOTH bug and quality angles:
> - **Bug plants:** P1 was also caught by removed-behavior; P2 also by line-by-line; P3 also by
>   removed-behavior and line-by-line (e.g. the stale `verify_token` docstring — which still
>   promises "revocation is checked before expiry" though the check was deleted — lets
>   line-by-line see P2).
> - **Quality plants:** P4 (`store.py:60` `last_seen`, intended=reuse) was also flagged by
>   **simplification** (`store.py:60` "needless indirection") and **altitude** (`store.py:60`
>   "bypasses the `_now()` time-seam"); P5 (`store.py:62` `has_live_session`,
>   intended=simplification) also by **reuse** ("re-implements `is_live` almost verbatim") and
>   **altitude** ("redundant public surface"); P6 (`store.py:81` `live_fraction`,
>   intended=efficiency) also by **simplification** (`store.py:80` "loop-invariant … dead
>   intermediate"). Only **P7** (`audit_dump`) was isolated to its single intended angle.
>
> This does **not** change the verdict. The PRIMARY recall score is intended-angle
> isolation — did each plant's OWN intended angle catch it? — which is still **7/7**, and the
> floor is on surfaced count, not isolation. But the designed diagonal not holding for 6/7
> plants at high effort is a real designed-vs-runtime delta. Candidate follow-up (strengthened):
> record in the fixture/`detection-matrix.md` that the designed diagonal is **idealized** — live
> high-effort recall shows broad co-detection across **6/7** plants (bug *and* quality angles),
> with only P7 isolated to its intended angle.

### Runtime reproduction (the CONFIRMED evidence for P1–P3)

```
$ cd before && python3 selftest.py        # baseline
OK                                          (exit 0)

$ cd after && python3 selftest.py          # planted tree
FAIL: token valid at exact expiry-plus-skew boundary     # P1
FAIL: revoked token is rejected                          # P2
Traceback (most recent call last):
  ...
  File ".../after/sessionkit/store.py", line 26, in put
    self._by_user[token["uid"]] = token
KeyError: 'uid'                                           # P3
                                            (exit 1)
```

## Objective failing-floor check (applied)

- **≥ 2 misses = recall collapse = FAIL regardless of documentation** → not triggered (0 misses).
- **Exactly 1 miss, documented as a known per-harness gap = PASS** → not needed (0 misses).
- **A single *undocumented* miss = FAIL** → not triggered (0 misses).

**Verdict: PASS.** The Claude-Code parallel-dispatch path recalls all 7 plants by
intended-angle isolation (7/7), the verify gate was run on every candidate (3 CONFIRMED via
runtime repro + 4 PLAUSIBLE via the adversarial verify fan-out), and the parallel dispatch is
proven on-disk (7 subagent transcripts, §2b-style). Floor is 6; **margin = 1 plant, fully
verified.** No follow-up gap issue is required.

## Out of scope (explicitly deferred)

- **OpenCode sequential-fallback recall floor** — #337 (non-gating follow-up).
- **Model-enforcement runtime proof** (the on-disk subagent-transcript read confirming
  `crucible-red-team` executed on Opus) — already delivered in **#352**; not re-run here.
- **Codex / Cursor / Pi** — authored-to-spec, runtime validation deferred per the
  harness-adapter (§1, §8).
