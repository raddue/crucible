# Contents

- Verdict Marker

## Verdict Marker

After Minor Issue Handling completes and before cleanup begins, write a verdict marker file to a stable location outside the scratch directory. This marker survives scratch cleanup and serves as a cross-skill consistency signal for the build orchestrator's gate ledger.

**Closure precondition:** Apply `loop.md` › Run-completeness guard before any PASS.
Severity closure alone is insufficient. Resolve the terminal outcome, including any
incomplete stages, before constructing its ledger entry or publishing its marker.

**When:** After Minor Issue Handling (the quick-fix pass on consolidated minors) and before cleanup. Written on ALL exit paths — PASS, FAIL, STAGNATION, and ESCALATED. The Verdict field reflects the actual outcome.

**Path:** `~/.claude/projects/<project-hash>/memory/quality-gate/gate-verdict-<run-id>.md`

**Format:** Key-value pairs, one per line. `MarkerVersion: 2` MUST be the FIRST line, `ArtifactHash` the SECOND. Field ordering below is canonical for writers:

```
MarkerVersion: 2
ArtifactHash: <sha256-hex of FULL pre-chunking artifact bytes, computed once at gate start>
ChunkHash: <sha256-hex of this chunk's bytes>   # chunked gates only, per-chunk markers only; omit on non-chunked markers and on the cross-chunk integration marker
Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION
Reason: clean-pass | siege-blocked | consensus-stagnation-pre-threshold | sustained-regression | no-op-fix | no-op-with-architectural-candidate | user-skipped | 15-round-circuit-breaker | stagnation-judge | single-round-regression | diminishing-returns | architectural-block-from-fix-agent | persistent-finding-corroborated | caller-detected-failure | severity-counts-discrepancy | incomplete-run
Phase: <phase name from invoking orchestrator, omit if standalone>
PipelineID: <pipeline-id from invoking orchestrator, omit if standalone>
Rounds: <total round count>
FinalScore: <weighted score from last round>
MaxScore: <highest weighted score observed across all rounds>
ScoreTrajectory: <comma-separated per-round weighted scores; on chunked gates, chunk boundaries are marked with `|` between two commas (e.g., `6,4,3,|,5,3,1,0,|,4,2,1`); parsers must split on `,` and treat `|` tokens as chunk separators rather than integers, e.g., 6,4,5,4,3,0>
MinorTrajectory: <comma-separated per-round Minor counts, sourced from round-N-score.md; chunk boundaries marked with `|` between two commas, exactly mirroring ScoreTrajectory; always present on post-deploy v2 markers; written on ALL terminal verdicts in the verdict-marker write step (#362)>
MinorAdvisory: density | trajectory | density+trajectory   # OMIT when no advisory fired (omit-when-none, parallel to CoFiredExits); computed ONLY on the clean-pass exit — see Clean-Pass Minor Advisory (#362)
SuppressedRegressions: <count of pre-threshold rounds with suppressed-signal != none>
NoOpFixes: <count of rounds with no-op-fix = true>
CoFiredExits: <comma-separated list of suppressed co-firing exits, omit if none>
ConsensusAvailable: true | false
ConsensusRoundsRun: <int — count of rounds where consensus_query returned status in {complete, partial}>
LookHarderRounds: <comma-separated list of LOCAL round numbers where look-harder fired NON-CLEAN; on chunked gates, elements are `<chunk_id>:<local_round>` per the canonical grammar — see Chunked Gate section; OMIT this field entirely when empty (omit-when-empty, parallel to CoFiredExits)>
LookHarderFiredCount: <int — count of look-harder dispatches (clean + non-clean, NOT skipped); always present, defaults to 0; invariant: len(LookHarderRounds) ≤ LookHarderFiredCount>
LookHarderSkippedReason: circuit-breaker | tail-rubric-already-applied   # OMIT unless look-harder was skipped on a candidate-clean round; per-run, first reason recorded if multiple skips occur; circuit-breaker wins over tail-rubric-already-applied on co-fire
PersistentFindingRounds: <comma-separated list of LOCAL round numbers where persistent_finding_count ≥ 1; on chunked gates, elements are `<chunk_id>:<local_round>`; OMIT this field entirely when empty (parallel to LookHarderRounds)>
PersistentCheckCount: <int — count of persistence-checker dispatches (error dispatches DO count); always present, defaults to 0; invariant: len(PersistentFindingRounds) ≤ PersistentCheckCount>
<!-- CONTRACT:qg-fan-out-marker-fields:START -->FanOutRounds: <comma-separated list of LOCAL round numbers where fix-generated-count ≥ 1; on chunked gates, elements are `<chunk_id>:<local_round>`; OMIT this field entirely when empty (parallel to PersistentFindingRounds, #546)>
FanOutCheckCount: <int — count of fix-generated-defect checker rounds (error dispatches and orchestrator-side fail-open interceptions DO count, round 6 M1 — the S4/F1 interception paths increment this with no subagent dispatch); always present, defaults to 0; invariant: len(FanOutRounds) ≤ FanOutCheckCount>
FanOutErrorCount: <int — count of rounds whose round-(N+1)-fix-generated.md carries status: error — whether the checker returned it or the orchestrator wrote it in the checker's place (round 6 M1's interception paths increment this exactly as they increment FanOutCheckCount, round 7 S2) (subset of FanOutCheckCount); always present, defaults to 0; invariant: FanOutErrorCount ≤ FanOutCheckCount; base-rate estimator is len(FanOutRounds) / (FanOutCheckCount - FanOutErrorCount), not len(FanOutRounds) / FanOutCheckCount (round 3, F2)><!-- CONTRACT:qg-fan-out-marker-fields:END -->
SiegeDispatched: true | false
SiegeReason: detected | force | skip-requested | no-security-surface
SiegeVerdict: PASS | ESCALATED | STAGNATION | UNAVAILABLE (omit if SiegeDispatched=false)
SiegeFindings: <count of Critical+High siege findings, omit if SiegeDispatched=false>
CostCapSignals: <DR-fire-count>+<cost-cap-fire-count>/<rounds>
Mode: <standard | full>
ResidualSignificant: <count on terminal qualifying fresh-review set, deduplicated by finding identity; full PASS is always 0>
ResidualMinor: <count on terminal qualifying fresh-review set, deduplicated by finding identity>
Timestamp: <ISO-8601>
RunID: <quality-gate run-id — identical to the model-assurance inventory's run_id; never write a duplicate RunID field>
MarkerFinality: chunk-milestone | final-integration
FinalArtifactHash: <sha256-hex from `gated_hash` in scripts/qg_model_assurance.py (artifact_hash over the inventory's persisted gated path set and deletion set, and persisted `gated.mode`; sha256 of the bytes when the mode is `document`), frozen after all fixes>
ModelAssurance: verified | configured | unknown
ModelAssuranceInventory: <inventory-path> sha256:<inventory-digest>
Severity-Histogram: <json — e.g., {"fatal":0,"significant":0,"minor":0,"nit":0}>
Gated-Files: <json-list — e.g., ["src/foo.py","src/bar.py"]>
Highest-Finding: "<one-line quote of the most severe finding, or empty string if none>"
```

<!-- CANONICAL: shared/ledger-append.md -->

**Ledger emit at verdict-emit.** When emitting your terminal verdict, also emit one JSONL line to the **central ledger** (`~/.claude/crucible/ledger/runs.jsonl`, override `CRUCIBLE_LEDGER_DIR`) via the `emit` CLI per the canonical protocol at `skills/shared/ledger-append.md` — resolve `scripts/ledger_append.py` by absolute path from the plugin root and run `python3 <script> emit - '<json>'` (`-` = central default). The `emit` CLI owns the mechanics: it honors `CRUCIBLE_CALIBRATION_DISABLED=1` as a graceful skip, dedups by `(run_id, skill)` (L-2), and auto-fills `repo` + `schema_version` — so you only construct the entry. Attempt this emit before publishing a PASS marker or return summary, after the other Run-completeness checks have resolved the verdict. Deliberately omitting the emit attempt is an incomplete run and cannot yield PASS. An attempted emit that fails remains non-blocking: warn and record the failure in the verdict explanation and return summary. If the script can't be resolved after attempting resolution, warn to stderr and record that outcome; this documented fallback does not block the gate. Record CLI dedup or fixture-only `CRUCIBLE_CALIBRATION_DISABLED=1` skips explicitly too; never set the kill-switch to bypass a production emit. A failed attempt, dedup, or documented skip must not be represented as a persisted ledger entry.
**`model_resolution` populator (Tier A only — #493).** Before constructing the
ledger entry, build `model_resolution` as an object keyed by role name (`red-team`,
`qg-fix`, `qg-verifier`, `qg-judge` — whichever of these four this round actually
dispatched), each value a JSON array of `{ran, basis, prov}` objects per
`skills/shared/ledger-append.md`'s `model_resolution` shape section, one array
entry per dispatch of that role this round (a role dispatched more than once in one
round — e.g. `qg-fix` across multiple fix-loop iterations — contributes multiple
array entries, oldest first). **Consensus reviewer keying (S3/S7, round 2).** The reviewer key is
`consensus` only when the emitter actually received and used a **completed or
partial consensus REVIEW result for this round** — the
`consensus_query(mode="review")` call that produces red-team findings at
`skills/quality-gate/loop.md` › Multi-Model Red-Team Review. Two pitfalls are fixed here:
- **Mode (S7):** `skills/quality-gate/receipt-consensus.md` and `skills/quality-gate/stagnation.md` also invoke
  `consensus_query(mode="verdict")` for the stagnation judge *later in the same
  round*. That result's `per_model` describes the **judge**, not the artifact
  reviewer, and the two arrays can differ (separate call, separate
  failures/bridges). Capture and retain the `mode="review"` result at dispatch
  time and source the `consensus` key **only** from it. Never use the
  verdict-mode result for the reviewer key; the consensus stagnation judge is
  **not** represented in `model_resolution` (design §9 reserves no key for it).
- **Eligibility is not occurrence (S3):** `skills/quality-gate/loop.md`
  falls back to a single red-team when consensus is unavailable on an eligible
  round. On that reachable path the key must be `red-team` — the model that
  actually reviewed — not `consensus`. Never key from calendar/config
  eligibility alone. The fallback is recorded via the single-model rule below
  (the red-team agent def's own pin), and on that path `consensus` must be
  **absent**: an unavailable result still carries a nonempty `per_model` of
  attempted-but-failed members (`mcp-servers/crucible-consensus/aggregator.py:179-205`
  builds `per_model` from **all** attempted responses), so keying from the list's
  presence would attribute reviewers whose results were never used. Pass the
  review result's use status explicitly (`review_used` below); do not infer it
  from a non-`None` list (S1, round 5). **Test:** an unavailable consensus result
  that falls back to a red-team pass yields only the `red-team` key, and a
  two-member `per_model` from the verdict-mode call does not leak into it.

**A `consensus` entry is sourced from the retained `mode="review"` result's
`per_model` list** (`ConsensusResult.to_dict()["per_model"]`,
`mcp-servers/crucible-consensus/aggregator.py:179-184`; built from **all**
responses including failures, and bridged `external_review` members arrive in
this same list via `additional_responses`). Every element is uniformly
`{ran, basis, prov}` with:
- `ran`: `"unknown"` for **every** consensus member (S2, round 4) —
  `per_model[i].model_id` is copied from the provider *config*
  (`mcp-servers/crucible-consensus/providers.py`: every `query()` returns
  `self.config.model_id`; no adapter reads the endpoint-reported name), so it
  records what was *requested*, not what ran. Design §9 defines `ran` as an
  endpoint-reported ID or `unknown`; until an adapter returns the response's
  model name, `unknown` is the only honest value.
- `basis`: `indeterminate` for **every** consensus member — nothing endpoint-
  observed backs a rung, so `asserted` must not be stamped on a config alias
  that may be retargeted (S2/S4). The members' *count* still attests the
  review call's returned membership.
- `prov`: `intent` (v1).
If the emitter has no membership list, it must first read the round's persisted
review result back from disk (`<findings-root>/round-<N>-review-result.json`, written at
dispatch time — see **Recovery across compaction (S3, round 9)** below) before falling
back to `null`. Only a genuinely absent on-disk record justifies a null: a value merely
lost from memory by a checkpoint is recoverable and must be recovered, not discarded.
**Test (S2/S4/S7):** a review-mode result of three
members (`responded` true/true/false, mixed vendors) and a verdict-mode result of
one member (different `model_id`) → the `consensus` array holds **three**
`{unknown, indeterminate, intent}` entries — membership from the *review* call,
never the verdict call; and an alias case where the config `model_id` differs
from the endpoint-reported name still yields `ran: "unknown"` (no adapter
observes the response name today).

**Recovery across compaction (S3, round 9).** The gate checkpoints every three rounds
and carries recovery state from disk (`skills/quality-gate/recovery.md` › Compaction recovery), so a review result living only in memory across the review→verdict seam
is a normal lifecycle transition, not an edge case. Persist the review-mode `per_model`
list and its use status to `<findings-root>/round-<N>-review-result.json` **at dispatch time,
before any other dispatch**, and read that file back at terminal emit before deciding
the row. The `null` branch stays only for a genuinely unavailable record — nothing
persisted and nothing in memory.

**Rollback invalidates the record (S5, round 10).** Retention across compaction and
invalidation on rollback are different requirements: existing recovery discards an
incomplete `round-(N+1)-*.md` (`skills/quality-gate/recovery.md`) but would leave
this JSON in place, so a replayed round could consume a stale `review_used`/`per_model`
and falsely attribute an abandoned review. Two rules prevent that: the JSON records the
**review dispatch id** it was written for, and the emitter consumes it **only** when that
id matches the review dispatch of the current (completed) round; and on incomplete-round
recovery the corresponding JSON is deleted alongside the discarded Markdown state, while
a fallback or no-review path overwrites (or removes) the file rather than leaving it
stale. Item 4(c) exercises exactly this replay.

**Chunk coordinate (SP3, round 11).** The round counter is LOCAL per chunk while
the scratch dir is shared, so a flat `<scratch>/round-<N>-review-result.json` lets
chunk K's local round 1 overwrite chunk K−1's record (and a rollback delete the
wrong chunk's evidence). The record therefore lives at the top level of **that
round's findings root** — `<scratch>` on a non-chunked gate, `<scratch>/chunk-K` for
the in-progress chunk of a chunked gate (`skills/quality-gate/artifact-preflight.md`) — and
carries its `chunk`, its **local** round, and the review dispatch id. Consumption
requires all three to match the current completed round; rollback deletion is
scoped to that same findings root. **Test:** two chunks whose local round 1 both
persist a record must both survive, and a rollback in one chunk must not delete the
other chunk's record (nor force a false `null` row).

**Cross-chunk integration round (S4, round 12).** The integration round's directory
is the reserved `cross-chunk` (INV-A15), which no `chunk-K` substitution names — the
gate pins a home for none of its round files (`skills/quality-gate/recovery.md`). It
therefore gets its own root and coordinate here: the record is
`<scratch>/cross-chunk/round-N-review-result.json` with coordinate
`chunk="cross-chunk"`, and its rollback scope is that directory only. Test it
against a preceding chunk's **same local round**: recovery must read the integration
record rather than that chunk's, and neither rollback may delete the other's.

**The record home is not the findings root (S5, round 13).** `skills/quality-gate/recovery.md`
leaves **every** integration-round file home and the `<findings-root>` itself unpinned
(`recovery.md` › Round History and Compaction Recovery), so pinning this record's path is not enough: the
round's findings, journal, coverage and linter second root can land elsewhere or nowhere
while the emitter still reads a `cross-chunk` record. This plan therefore does **not** pin
that layout unilaterally — it **blocks the integration populator** until the gate's
integration findings root is pinned, and it must fail loud, not write silently:
the run asserts that the record's directory **is** that round's findings root -
`test "$(dirname "$record")" = "$FINDINGS_ROOT"` and
`test "$(dirname "$record")" = "$(dirname "$ROUND_FINDINGS")"` - and never against
the **receipt's** directory: the receipt legitimately lives in the dispatch root or is
piped to the linter as `-` (`skills/quality-gate/loop.md`), so comparing the two is
unsatisfiable for the normal layout and would stop every integration round instead of
verifying co-location (F1, round 17). A missing `$FINDINGS_ROOT` refuses the round, naming
the missing-root gap rather than emitting a record no linter root covers. (#746: the integration findings root is now pinned to `<scratch-dir>/cross-chunk/` — artifact-preflight.md › Cross-chunk layout — so `$FINDINGS_ROOT` for the integration round is that directory.)

**Row unit (S5, round 2).** The Tier-A ledger row is emitted **once per gate
run** (`skills/quality-gate/recovery.md`), but `model_resolution` describes
**only the round that produced this emitted verdict** (the terminal round) —
the only round whose `per_model` the emitter can trust at emit time. Earlier
rounds' contributors are deliberately **excluded** and must not be inferred
from this row; cross-round aggregation is out of scope of this task.
**Test:** a gate whose round 1 is a consensus review and whose terminal round is
a single-model PASS emits a `model_resolution` for the terminal round only.

**Fixer provenance (F1, round 8).** "Only the verdict-producing round" must not be
read as "only that round's *reviewer*". The accepted artifact is normally produced
by the **previous** round's `qg-fix` dispatch — round N fixes, round N+1 reviews the
revised artifact and PASSes, and the single row is emitted at N+1 — so a row built
from N+1 alone would carry the reviewer but drop the fixer that produced the accepted
revision. That is the *normal successful* path, and it is exactly the model flip
design §9 creates this field to expose. The row must therefore include the **final
accepted artifact's producing `qg-fix` dispatch** (plus any post-pass quick-fix)
alongside the terminal round's reviewers; only that fixer contributes, so discarded
earlier fix attempts remain excluded. The orchestrator supplies it as a `qg-fix`
entry in the `roles` map (acceptance case 13). An explicit design amendment is the
only alternative to this attribution — a maintainer checkpoint, not a plan decision.

**Maintainer checkpoints (S3, S5) — do NOT record approval as granted.** Two
design-level questions are unresolved and block any claim beyond the above:
(a) design §9 says `consensus` is present exactly when a round is
consensus-*eligible*, which is inconsistent with the pre-existing
unavailable-consensus fallback path; (b) design §9 does not pin whether
`model_resolution` is per-round or run-wide, so a run-wide intent would require
persisting per-round `per_model` in round history at review time (a
design-level change); (c) at/above the stagnation threshold,
`consensus_query(mode="verdict")` **replaces** the single `qg-judge` dispatch
(`skills/quality-gate/stagnation.md`), so the consensus judge that actually
decided termination can be absent from the row entirely — design §9 reserves no key
for it, and inventing a separate verdict-judge consensus key is an architectural
change the plan must not make on its own (S4, round 5); (d) `quality-gate` step 5.4
re-dispatches `crucible-red-team` for **look-harder** on a candidate-clean
consensus-eligible round, so one round can legitimately contain *both* a consensus
review and an ordinary red-team dispatch. Design §9 promises the consensus-vs-single
distinction from the key **name alone**, which a round holding both keys breaks —
the plan records the look-harder dispatch under `red-team` and must not silently pool
it with the ordinary reviewer, but a site-discriminating key (or a documented
exclusion) is a design amendment needing approval (S1, round 6); (e) design §9
defines `ran` as an *endpoint-reported* id or `unknown`, so a static brand alias must
not be recorded as the model that ran — likewise a design-interpretation question the
plan stops on (S2, round 6).
(f) design §9 defines the `consensus` array as **one element per *polled*
member** with a uniform `{unknown, indeterminate, intent}` shape, but
`aggregator.py:185-205` also returns failed attempted members (`responded` false)
and can return a partial result — so a row cannot distinguish "three models
reviewed" from "three polled, one failed", even though design §9 claims the field
can express "three vendors voted" and reads the consensus-vs-single distinction
from the key **name** alone (S2, round 7). The plan does **not** invent a
status-bearing element or a separate participation field: pending approval it
scopes the array to **attempted membership**, forbids reading its length as
evidence of votes or cross-model coverage, and pins that reading with a
partial-result acceptance case (case 12). Approval of a status-bearing uniform
element or participation field would supersede the scoping; that choice is a
design amendment needing approval, not a plan decision.
**Before finalizing the keying, row-unit, or `ran` behavior, the plan stops for
explicit maintainer approval** on all six; this plan implements the honest fallback,
the final-round-only reading, uniform `{unknown, indeterminate, intent}`, and an
explicit **documented exclusion** of the verdict-mode judge (named as excluded from
cross-model comparability) rather than a silent omission — and does **not** invent
the design's intent or record approval as granted. **Test:** one configured consensus
member plus one bridged external response must yield **two** entries — the
membership *count* reflects the review call, while each entry is
`{unknown, indeterminate, intent}` under S2's config-vs-endpoint rule (no
adapter observes the endpoint-reported model name).

**Type-resolution fallback (S1, round 4).** When the harness cannot resolve an
agent type and the dispatch runs as `general-purpose` on the inherited/session
model (`skills/quality-gate/loop.md`, plus Task 9's new qg-verifier and
qg-judge warnings), the named agent def was **not** dispatched. Recording its
nominal `model:` pin as `ran` would log an inherited Opus verifier as `sonnet`,
or an inherited Sonnet red-team as `opus` — precisely the model flip this feature
exists to expose. For any dispatch that hit a type-resolution failure, write
`{"ran": "unknown", "basis": "indeterminate", "prov": "intent"}` (or an actual
fallback model ID, if one is observed) — never the absent def's pin. The one-time
fallback warning does not retro-correct stored `model_resolution`.

For each **single-model** dispatch: `ran` is `unknown` and `basis`
`indeterminate` in v1 — design §9 defines `ran` as an endpoint-reported id or
`unknown`, and the dispatch's static `model:` pin (e.g. `opus`, `sonnet`) is
*requested*, not observed: no `RESOLVED:` producer or transcript oracle ships
(design §6.2). Recording the alias would pool a silent provider-side fallback with
the requested model, so the requested pin is not carried in `ran` at all (S2,
round 6). `basis` becomes `asserted` (brand→rung table,
`skills/shared/model-tier-policy.md` §6.1) only when an observed resolution exists
to back it. `prov` is `intent` in v1, unconditionally, for every entry: the only
available source is the agent def's static pin and the brand table — exactly the
manifest-derived path design §9 classifies as `intent`, not `receipt`. Do not write
`prov: "receipt"`; it becomes reachable only once the `RESOLVED:`-producer follow-up
(Task 13) ships.

If the round dispatches none of
the four `MODEL-REQ`-bearing roles (a pure look-harder or escalation round), set
`model_resolution: null` for that verdict entry **only if the round contributed
no reviewer data at all** — no in-scope single-model role **and** no actually
used review-mode consensus result (SP2, round 3); a consensus-only clean round is
non-null via the `consensus` key. Never an empty object, which
would falsely claim "checked, found nothing" rather than "not applicable this
round." **Every array element is uniformly `{ran, basis, prov}` (S4):** an earlier
draft capped each role array at 32 entries by inserting a `{"elided": <N>}`
element between the retained head and tail; that element is not
`{ran, basis, prov}`, so it broke design §9/T19's uniform-array contract precisely
when the cap activated, with no reader scoped to handle it. The cap and the marker
are removed. The unbounded-size residual design §9 already discloses stands:
`append()`'s 16384-byte row cap drops an oversize row rather than truncating it and
`_truncate_payload` does not cover this field, so a very large array can lose its
whole row through that pre-existing disclosed path — reported by `append()`, not
hidden behind an undocumented array element. See
`skills/shared/ledger-append.md`'s `model_resolution` shape section.


**`model_assurance` emit (optional, #746).** Tier-A rows may carry `"model_assurance": {"state": "<ModelAssurance>", "inventory": "<path>", "digest": "<sha256>"}` sourced from the terminal marker's `ModelAssurance`/`ModelAssuranceInventory` fields, per `skills/shared/ledger-append.md`'s `model_assurance` shape section. Display-only: this emit may be skipped, deduplicated, or fail without changing the durable inventory or the verdict, and the terminal-round-only `model_resolution` above keeps its original shape and scope.

**`predicted_falsifier` (Phase 7 prediction market).** When constructing the entry, set `predicted_falsifier` to a pre-registered, machine-checkable predicate ONLY when `verdict ∈ {PASS, FAIL}` AND `artifact_type == "code"`; otherwise `null` (all escalation verdicts — STAGNATION/ESCALATED/ARCHITECTURAL/SUSTAINED_REGRESSION — and all non-code artifact types). In one sentence, describe the future evidence that would prove this verdict wrong, using the canonical grammar where possible: `{verb} touching {file-or-glob[,file-or-glob,...]} within {N}d` (e.g., `fix touching src/auth/token.ts within 30d`). Free-form prose is permitted but counts as "unparseable" for auto-checking. Max 256 chars. Full grammar (three forms, verbs, glob/hash/token variants) is the canonical `predicted_falsifier` protocol in `skills/shared/ledger-append.md`. Do NOT write the retired `"<DEFERRED:pre-phase-7>"` sentinel.

**MarkerVersion semantics:** Every verdict marker written by this version of the gate or later carries `MarkerVersion: 2` as its first line. Consumers gate version-aware parsing on this stamp:

- `MarkerVersion: 1` or absent ⇒ legacy marker. Consumers MUST treat any missing field as `null` (unknown), NOT as `false`/`0`/`[]`.
- `MarkerVersion: 2` ⇒ this version's marker. Missing fields are semantically empty per the **omit-when-empty** convention enumerated above (e.g., absent `LookHarderRounds` means "no non-clean look-harder rounds"; absent `LookHarderSkippedReason` means "look-harder was not skipped").

The convergence-log mirrors this stamp via `marker_version` (see Convergence Telemetry).

**ArtifactHash semantics:** `ArtifactHash` is the sha256 hex of the FULL pre-chunking artifact's bytes, computed once at gate start. For non-chunked gates this is the single artifact's hash. For chunked gates, every per-chunk verdict marker AND the cross-chunk integration round's marker carry the **same** `ArtifactHash` — it identifies the artifact across all chunks of a single gate run AND across multiple gate runs on the same byte content (regardless of chunking strategy). Forge consumers use `ArtifactHash` for same-artifact cross-run comparison, including the revisit trigger for the `tail-rubric-already-applied` skip.

`ChunkHash` (chunked gates only): sha256 hex of the specific chunk's bytes. Present on per-chunk markers in chunked gates only. **Omitted from non-chunked-gate markers and from the cross-chunk integration round's marker.** `ArtifactHash` is the canonical cross-run identifier; `ChunkHash` is internal-only for per-chunk recovery scenarios.

**Model-assurance fields (#746).** Per-chunk markers on a chunked gate are `MarkerFinality: chunk-milestone`; only the marker emitted after the complete integration is `final-integration`, and only after every manifest-listed chunk has terminal status and all mandatory cross-chunk consensus membership is consumed (loop.md › Model Assurance Inventory). Callers selecting a PASS marker must verify final-integration status, the complete chunk roster, and exact run/artifact binding — never select latest PASS by timestamp, and a chunk milestone's local assurance is non-qualifying: it must never be selected or displayed as whole-gate high assurance. Before terminal marker emit, reconcile the run inventory, the final artifact, and the explicit chunk/consensus roster; bind `RunID` to the inventory's run ID and `ModelAssuranceInventory` to its path and SHA-256 digest. `FinalArtifactHash` is computed only by `gated_hash` (`artifact_hash`), never ad hoc (for example as a diff hash), and is frozen **after** all fixes including the post-PASS Minor quick-fix, before marker emit; the gated path set and deletion set are persisted in the inventory (`gated`) with the terminal-schema write so callers can recompute it, and the hash binds the worktree root; `ArtifactHash` stays the pre-gate input hash and is never used for accepted-output comparison. `ModelAssurance` is the output of `marker_assurance` in `scripts/qg_model_assurance.py`, never a reading of the rows' own `assurance` labels: it is `verified` only when `reconcile_evidence` proves it against host-owned evidence, else `assurance_state` (the weakest state over the run-wide inventory's consumed critical invocations, at most `configured`); a row's `assurance` label is never an input to `verified`, so a portable run with no host adapter writes `configured` or `unknown`. Missing or incomplete evidence downgrades this field, never the Verdict. If `gated_hash`, the terminal-schema write (`write_inventory(..., terminal=True)`), or `marker_assurance` cannot run (no terminal inventory, a non-git root for a multi-file set, a row without `kind`, any error), omit `ModelAssuranceInventory` (or write it `unknown`) and write `FinalArtifactHash: unknown` and `ModelAssurance: unknown`; this never changes `Verdict` or blocks marker emit, and `qg-verified` callers then fail closed. If the final-integration precondition above is unmet on a PASS (for example a mandatory consensus member recorded `unused`), the integration marker still carries `MarkerFinality: final-integration` with `ModelAssurance: unknown` — never `chunk-milestone`, which callers reject. A non-chunked terminal marker is `MarkerFinality: final-integration`. `Gated-Files` is the inventory's `gated.paths` minus `gated.deleted`, so `action_allowed` can compare the two; when no gated set exists (no terminal inventory), write the reviewed file list. Non-PASS exits write the same fields truthfully. Display `HIGH-ASSURANCE QG PASS` (and let build/warden record `QGModelAssurance: verified`) only for a `final-integration` marker whose `ModelAssurance` is `marker_assurance` output `verified`; otherwise label the result `PASS (QG model assurance: configured|unknown)`.

**Verdict enum semantics:**
- `PASS`: gate exited cleanly under active mode (`0 Fatal` on standard's required fresh reverify; `0 Fatal, 0 Significant` on full) and satisfied the Run-completeness guard.
- `FAIL`: caller-detected gate failure outside the normal exit paths (reserved for build's gate ledger). Quality-gate itself never writes `Verdict: FAIL`. The FAIL value exists in the enum for callers (build's gate ledger) that need to record a downstream-detected failure of the gate's output; such callers write `Reason: caller-detected-failure` alongside it.
- `STAGNATION`: stagnation judge declared STAGNATION at round ≥ `suppression_threshold`
- `ESCALATED`: any other escalation routed to the user (15-round limit, diminishing returns, single-round regression at round ≥ `suppression_threshold`)
- `ARCHITECTURAL`: fix-agent flagged architectural concern (any round); see Architectural Concerns Exit
- `SUSTAINED_REGRESSION`: `score(N) > score(N-1) > score(N-2)` triggered the hard exit (any round)

**Reason token mapping (which exit-path writes which token):**
- `clean-pass` — Verdict: PASS. The only valid Reason for PASS.
- `incomplete-run` — Verdict: ESCALATED, when the run stops with required stages omitted, substituted without a documented fallback, or unverified and no other non-PASS exit already determines the verdict. List those stages with round/chunk coordinates in the verdict explanation and return summary. This outcome cannot satisfy a caller's PASS requirement.
- `siege-blocked` — Verdict: ESCALATED, from the Siege verdict-mapping rule (`SiegeDispatched: true AND SiegeVerdict != PASS`).
- `consensus-stagnation-pre-threshold` — Verdict: ESCALATED, from the Pre-Threshold Consensus Carve-Out.
- `sustained-regression` — Verdict: SUSTAINED_REGRESSION, from the sustained-regression hard exit.
- `no-op-fix` — Verdict `ESCALATED`. The fix agent returned a byte-identical artifact, OR the verifier marked every targeted finding Unresolved, AND no architectural-candidate flag was set from a prior round. Distinct from `no-op-with-architectural-candidate`, which applies when the architectural-candidates list is non-empty.
- `no-op-with-architectural-candidate` — Verdict: ESCALATED, from the no-op→architectural promotion path when the re-dispatch also returns a no-op.
- `user-skipped` — Verdict: ESCALATED, from the interactive check-in's escalate-now/skip response or an out-of-band user interrupt.
- `15-round-circuit-breaker` — Verdict: ESCALATED, from the 15-round global safety limit.
- `stagnation-judge` — Verdict: STAGNATION, from the stagnation judge declaring STAGNATION at round ≥ `suppression_threshold`.
- `single-round-regression` — Verdict: ESCALATED, from a single-round score increase at round ≥ `suppression_threshold`.
- `diminishing-returns` — Verdict: ESCALATED, from the judge's DIMINISHING_RETURNS verdict.
- `architectural-block-from-fix-agent` — Verdict: ARCHITECTURAL, from the fix agent's `VERDICT: ARCHITECTURAL_BLOCK` declaration.
- `persistent-finding-corroborated` — Verdict: STAGNATION, from the orchestrator's post-judge verdict-level promotion rule (Component 4). Recorded when the stagnation judge returned PROGRESS but `persistent_finding_count ≥ 1` AND round ≥ `suppression_threshold` AND round N's verifier had ≥1 `Resolved` finding (NOT fully no-op). See `## Stagnation Detection > Persistence Check` for the promotion logic.
- `caller-detected-failure` — Verdict: FAIL. Valid ONLY when `Verdict: FAIL`; written by callers (e.g., build's gate ledger) recording a downstream-detected failure of the gate's output. Quality-gate itself never writes this combination.
- `severity-counts-discrepancy` — Verdict: ESCALATED, from the Score source rule's Empty-work-order exception (step 7): a discrepancy-blocked round (or discrepancy-demoted look-harder round) whose orchestrator-counted population is 0 Fatal/0 Significant. See Exit Precedence slot #4.

**Fragile-pass detection:** Downstream consumers (build's gate ledger, forge retrospectives, future telemetry) detect a fragile pass via `Verdict: PASS AND (SuppressedRegressions > 0 OR MaxScore > FinalScore + max(2, ceil(suppression_threshold / 3)) OR NoOpFixes > 0 OR ConsensusAvailable: false)`. The `max(2, ceil(threshold/3))` term scales the score-swing tolerance to the convergence window: a code/design/plan gate (threshold 10) tolerates a 4-point swing; a hypothesis gate (threshold 3) tolerates 2 points. (Note: fragile-pass detection intentionally uses `ceil` — slightly more permissive tolerance — while the consensus/notification *cadence* uses `max(1, // 3)` floor for a precise per-round schedule. The two formulas serve different purposes and are not expected to match.) The rationale is that longer convergence windows naturally produce larger transient scores, and a flat `+2` would over-flag normal convergence on artifacts allowed more rounds. A fragile pass is still a PASS — these fields are advisory signal for human review or telemetry filtering, not for failing the gate. `MaxScore` is computed under the #561-widened population; runs whose convergence-log entries predate that change (no `score_population` key, per the Score source rule's comparability note) are excluded from fragility-rate denominators.

**Fragile-pass disjunct partitioning (advisory).** Consumers SHOULD partition `ConsensusAvailable: false` from the other disjuncts (SuppressedRegressions, MaxScore drift, NoOpFixes) when reporting fragility rates. The consensus disjunct reflects a **cross-model coverage gap** — the gate ran against a single model family and correlated blind spots are possible. The other disjuncts reflect **within-loop convergence instability**. Each consumer may choose to display them as separate metrics rather than a single fragility boolean; collapsing the two onto one axis obscures the underlying cause of the fragility flag.

**Tool:** Write tool (not Bash) since the path is under `.claude/`.

**Standalone invocations:** When quality-gate is invoked directly (not by build), the `Phase` and `PipelineID` fields are omitted. The marker is still written — it serves as a completion record even without pipeline context.

**Stale cleanup exclusion:** Verdict markers are NOT subject to the 2-hour stale cleanup that applies to scratch directories. They are deleted by the build orchestrator after writing the corresponding gate ledger entry. Orphaned markers (from crashed runs) are cleaned up during the build skill's ledger initialization.
