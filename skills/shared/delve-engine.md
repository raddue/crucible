# Delve Engine — Instance-Bug Fan-Out + Verify Gate

> The single, Crucible-owned, **harness-portable instance-bug engine**: a parallel fan-out of
> finder angles followed by a one-verifier-per-candidate verify gate. Authored fresh — nothing is
> copied from any existing skill (the built-in `/code-review` fan-out is closed/uncopyable; the
> repo's `code-review` dir is `temper`'s pre-rename iterative-loop ancestor, not a fan-out finder).
>
> **Consumed via** `<!-- CANONICAL: shared/delve-engine.md -->`. The severity scale and verify-gate
> verdict vocabulary this engine emits are NOT defined here — they come from the contract:
> <!-- CANONICAL: shared/severity-verdict-contract.md -->
>
> **Who drives it:** exactly two skills dispatch this engine directly — the `/delve` skill
> (authored in #331) and `temper` (reshaped in #333); `/audit --bugs` (#332) reaches it
> *transitively* by invoking the `/delve` skill. Each caller selects an `angles` subset and a
> `scope` rather than forking the engine. The dispatch **mechanism** (parallel fan-out, with a
> sequential fallback) is the harness-adapter (authored in #329, wired in #334); this doc names
> the mechanism abstractly and contains **no harness-specific call** (I1).

## 1. The cutting rule (load-bearing — what delve owns)

A finding belongs to delve **iff it has one concrete reproduction** — a single defect you can point
at and trigger, *even when it spans multiple files* (the cross-file tracer finds exactly these:
one bug, one reproduction, multiple files). A pattern / property / absence that recurs across sites
with **no single reproduction** is *systemic* and belongs to `audit`, not delve.

> The discriminator is **"is there one concrete reproduction?"**, never file count. A
> single-reproduction bug is never an audit finding; a no-single-repro pattern is never a delve
> finding. This rule is written into every BUG-angle prompt below; the four quality angles (4.4–4.7) are exempt by design (they are capped non-gating and carry no reproduction discriminator).

## 2. Inputs

The engine takes five explicit inputs so all callers drive **one** engine — no per-caller fork:

| Input | Type | Default | Meaning |
|---|---|---|---|
| `scope` | diff \| `base..head` \| path/subsystem \| explicit changed-region set | (required) | What the run reviews. `temper` R2+ passes a fixed changed-region set here; standalone `/delve` passes a diff or a path; `audit --bugs` passes the audited subsystem. The engine never assumes "the whole diff." |
| `angles` | subset of the 7 angles (§4) | all 7 | Which finder angles to run. `temper`'s gate selects the bug angles; `audit --bugs` selects bug angles; standalone `/delve` defaults to all. |
| `effort` | `low` \| `medium` \| `high` \| `max` | `medium` | Recall/cost tier (§3). |
| `cap` | int | `10` | Max ranked findings returned. |
| `external_candidates` | list of **DRAFT** findings (each `{file, line, summary, severity}`, **no verdict**) | empty | An optional candidate feed merged into the pre-dedup candidate pool and **adjudicated by the same verify gate** before any candidate can be kept (§5). Externals arrive as drafts only; any inbound `verdict` is discarded — the verify gate is the sole verdict authority, so an external can never bring its own verdict. Populated ONLY when `temper` runs with `external_review` enabled; empty for standalone `/delve` and `audit --bugs`. |

`scope` and `effort` are echoed onto every output record (§6) so a downstream consumer
(`audit`'s suppress-and-cite gate) can read the run's coverage off the record itself.

## 3. Effort tiers

Effort trades cost for recall. It changes how many candidates each angle proposes and how hard the
verify gate looks — it never changes the angle set (that is `angles`) or the schema.

| Tier | Candidates per angle | Posture |
|---|---|---|
| `low` | ~1–2 | Only high-confidence, obvious defects. Fast triage. |
| `medium` | ~2–3 | Balanced; the default. |
| `high` | ~4–6 | Broad, **recall-biased** — proposes a candidate on any plausible suspicion and lets the verify gate cull. This is the tier `temper` R1 and `audit --bugs` pin. |
| `max` | as many as the angle finds | Exhaustive recall; for deep standalone sweeps where missing a bug costs more than verifier time. Raise `cap` to match — `cap` truncates only the ranked output (§6), so a default `cap` can drop confirmed findings a `max` sweep paid to verify. |

> Recall lives in the **fan-out** (many angles × many candidates); precision lives in the **verify
> gate**. Raising effort widens the fan-out and trusts the gate to drop the noise — it does not
> lower the bar for what survives the gate.

## 4. Finder angles

Seven angles run **in parallel** (one fan-out task each; see §7 for the dispatch mechanism and its
sequential fallback). Each angle independently proposes up to *N* candidate findings (N per §3),
each candidate carrying a draft of the §6 schema. Angles do not see each other's candidates;
overlap is resolved by dedup before the verify gate (§5).

The angles split into **three bug angles** (may emit the full severity scale) and **four quality
angles** (capped at the non-gating tiers per the contract). The severity each angle may emit, and
whether it can gate, is governed entirely by `shared/severity-verdict-contract.md` — the bands
below restate that contract for convenience, they do not redefine it.

### Bug angles (full severity scale)

**4.1 Line-by-line diff scan.** Walk each changed hunk line by line. Hunt concrete local defects:
off-by-one, inverted/elided conditionals, null/none dereference on a reachable path, wrong operator,
swapped arguments, lost early-return, resource left unclosed, a guard that no longer guards what it
guarded. One candidate per concrete defect with a triggering input. Each candidate must name one
concrete triggering input / one concrete reproduction (§1); a recurring pattern with no single repro
is audit's, not delve's. *Not* style, *not* "this could be cleaner" — that is the quality angles.

**4.2 Removed-behavior auditor.** Read what the diff **deletes or weakens**, not what it adds. For
every removed line, dropped branch, loosened check, deleted test, or narrowed type: ask "what real
behavior did this protect, and is that behavior now unprotected?" Propose a candidate when a
removal silently drops a guarantee the surrounding code (or its callers) still relies on. Each
candidate must name one concrete triggering input / one concrete reproduction of the dropped
guarantee (§1); a recurring removed-protection pattern with no single repro is audit's, not delve's.
This is the angle a single holistic reviewer most often misses — it grades the addition and never
audits the subtraction.

**4.3 Cross-file tracer.** Trace **one** concrete defect across file boundaries: a writer in file A
emits a shape/contract that a reader in file B rejects or mishandles; a caller passes what a callee
no longer accepts; an invariant established in one module is violated by an edit in another. The
candidate must name a **single reproduction** that happens to touch multiple files — *not* a pattern
that recurs across many sites (that is audit's systemic territory, §1). One bug, one repro, many
files.

### Quality angles (capped at Minor/Suggestion — never gate)

These propose improvements, never merge-blockers. Per the contract they are capped at
Minor/Suggestion by construction and never enter the tracked set `T`. A concern that is genuinely
Critical/Important is a **bug-angle** finding and is re-attributed to the owning bug angle (and to a
Correctness/Architecture concern), exactly as `reviewer-common.md`'s DRY re-attribution does — it is
never emitted as a Critical "quality" finding.

> **Parallel taxonomy — intentional, not a duplicate (#358).** These angles overlap by intuition
> with the prompt-reviewer *Targeted Lenses* in `shared/reviewer-common.md` but are a deliberately
> separate vocabulary: `Reuse` mirrors the `DRY` lens; `Altitude` is adjacent to — but distinct
> from — `SRP` (abstraction *placement* vs. unit *cohesion*); the lenses' `Surgical Changes` and
> `OCP` have no angle counterpart. The angles lack a precedence / co-fire resolution table (the
> lenses' Surgical-wins, SRP-contains-DRY, co-fire rules) and are capped *by construction*; but both
> share a re-attribution mechanism — a genuinely Critical/Important concern is re-attributed to the
> owning bug angle (mirroring the lenses' DRY escape hatch) rather than emitted as a capped quality
> finding — because the two serve different machines: this portable engine vs. a live gating
> reviewer. Synced by intent, never by shared text.

**4.4 Reuse.** New code that duplicates an existing helper/utility instead of calling it, or two
near-identical blocks introduced in the same diff that would predictably need the same future fix.

**4.5 Simplification.** Logic that is more convoluted than the problem requires: a state machine
where a guard clause suffices, nested conditionals collapsible to one, dead intermediate variables,
needless indirection.

**4.6 Efficiency.** Avoidable cost on a path that matters: a loop that re-derives a loop-invariant,
an O(n²) walk where a lookup exists, a redundant fetch/parse, an allocation in a hot path. Flag only
where the cost is real, not theoretical.

**4.7 Altitude.** The change sits at the wrong level of abstraction: business logic leaking into a
transport layer, a helper that knows too much about its caller, a new public surface that should be
internal, a concern placed one layer off from where the codebase puts its peers.

## 5. Verify gate

The optional `external_candidates` feed is **first merged into the candidate pool** alongside the
internal angle candidates; then **all** candidates (internal + external together) are **deduped** as
one set (same defect proposed by two angles → one candidate, keeping the most specific summary and
the higher severity), so external and internal candidates are deduped cross-origin and externals can
never bypass the gate; then **one verifier per deduped candidate** adjudicates. Externals enter as
DRAFT findings carrying at least `{file, line, summary, severity}` and **no verdict**; any inbound
verdict is discarded here so that every kept verdict — external or internal — is one this gate
assigned. An external's inbound `severity` is likewise a **draft hint only**: the verifier
(re)assigns severity per the contract exactly as it does for an internal candidate, so an external
cannot inject an authoritative (e.g. unverified Critical) severity.

Each verifier adjudicates its candidate against the code and assigns a verdict from the contract:

- **CONFIRMED** — the verifier positively established the defect (reproduced it, or showed the
  faulty path is reachable with concrete inputs). **Kept.**
- **PLAUSIBLE** — credible against the code but the verifier cannot produce a runnable reproduction
  (e.g. it depends on runtime state the verifier can't drive). **Kept.**
- **REFUTED** — the verifier showed it is not a defect (the construct is sound, guarded, or
  unreachable). **Dropped** — it never reaches output.

The verifier also fixes the candidate's `severity` per the contract's scale. The verify gate is
responsible for populating/normalizing the remaining §6 output fields — `failure_scenario`, `scope`,
and `effort` — for **every** kept candidate regardless of origin, so an external need only supply
`{file, line, summary, severity}` on input and the gate produces the complete 8-field output record.
Verdict and severity together decide gating *for callers that gate* (`temper` builds its tracked set
`T` from the kept records); the engine itself does not gate — it emits the kept, ranked set.

> Quality-angle records carry a non-gating verdict **by convention** (the §8 example emits the
> simplification as `PLAUSIBLE`). It is the contract's quality-angle *cap* — not the verdict — that
> makes a quality finding non-gating; a `PLAUSIBLE` on a quality record does **not** mean the verify
> gate attempted and failed to reproduce a readability suggestion.

## 6. Output

The engine returns a list of kept findings (CONFIRMED + PLAUSIBLE), ranked most-severe-first, capped
at `cap` (default 10). `cap` truncates the **ranked output only** — it does not change what the
fan-out proposed or what the verify gate adjudicated. Because ranking is most-severe-first, the
guarantee `cap` gives is only **relative**: it drops the least-severe tail first, so no lesser
finding survives above a dropped greater one. `cap` does **not** guarantee a gating (Critical/Important)
finding is preserved — when the count of Critical/Important findings *alone* exceeds `cap`, gating
findings themselves are truncated. Gating callers (`temper`) must therefore set `cap` high enough to
hold all of `T`, and should treat truncation of a Critical/Important finding as a signal rather than
rely on `cap` to preserve every gating finding. Deep / `max` sweeps that expect many findings should
likewise raise `cap` so a real finding is not truncated. Each
record is **exactly these eight fields** — fixed, no more, no fewer:

```
{
  "file":             "<path>",
  "line":             <int or "lo-hi">,
  "summary":          "<one-line what-and-where>",
  "failure_scenario": "<if X does Y under Z, then OBSERVABLE failure, leading to IMPACT>",
  "severity":         "Critical | Important | Minor | Suggestion",   // per the contract
  "verdict":          "CONFIRMED | PLAUSIBLE",                       // REFUTED never emitted
  "scope":            "<the diff/path range this run was derived over>",
  "effort":           "low | medium | high | max"                    // the tier this run used
}
```

For a non-gating **quality** finding there is no failure to describe, so `failure_scenario` may be a
brief `"none — <reason>"` string (e.g. the §8 example's `"none — readability only"`) rather than the
`if X does Y under Z, then OBSERVABLE failure…` template form; output validators should accept this
shorthand for quality-angle records.

`severity` and `verdict` draw their vocabulary from `shared/severity-verdict-contract.md`; this
engine does not define them. `scope` and `effort` are the same on every record in a run (they
describe the run, not the finding) and exist so `audit`'s suppress-and-cite coverage gate can read
a delve instance's derivation range and tier directly off the record.

## 7. Dispatch (mechanism)

The fan-out (§4) and the per-candidate verify gate (§5) run as parallel subagents **through the
harness-adapter fan-out mechanism** — never a harness-specific call inline (I1). The harness-adapter
(authored in #329, wired in #334) maps "run these angles in parallel" onto whatever primitive the
host harness provides, and supplies a **sequential fallback**: on a harness with no parallel-subagent
primitive, the angles run as *multiple sequential passes* — one pass per angle — never collapsed
into a single in-context pass (the single-pass mode is the recall-poor failure this engine exists to
fix; the adapter warns once that recall may drop under the sequential fallback).

This engine is the thing **dispatched**; it does not dispatch itself. The canonical
`dispatch: delve-engine` marker that the I2 allowlist greps for lives in the BODY of the two direct
dispatchers (`/delve`, `temper`) — added at wiring time (#334) — never in this engine file.

## 8. Worked example (illustrative)

`/delve src/session/ effort=high` over a small auth-token change.

**Fan-out (high effort) proposes, among others:**
- *line-by-line:* `token.ts:42` — `expiresAt` compared with `<` where `<=` was intended; a token
  expiring exactly on the boundary is treated as still valid.
- *removed-behavior:* `token.ts:88` — the diff deleted the `revoked` check that the old code ran
  before accepting a token.
- *cross-file tracer:* writer `token.ts:51` now emits `{exp}` (renamed from `{expiresAt}`) but
  reader `middleware.ts:30` still reads `claims.expiresAt` → every request reads `undefined`.
- *simplification:* `token.ts:60` — a three-branch `if/else if/else` that collapses to one ternary.
- *efficiency:* `middleware.ts:18` — re-parses the JWKS on every request instead of caching it.

**Dedup + verify gate:**
- `token.ts:42` boundary bug → **CONFIRMED / Important**.
- `token.ts:88` removed `revoked` check → **CONFIRMED / Critical** (revoked tokens now accepted).
- `middleware.ts:30` field-rename mismatch → **CONFIRMED / Critical** (all auth breaks).
- `token.ts:60` simplification → **PLAUSIBLE / Suggestion** (quality angle; capped non-gating).
- `middleware.ts:18` JWKS re-parse → the verifier finds it cached one layer up → **REFUTED**, dropped.

**Output (ranked, capped):**

```
[
  {"file":"middleware.ts","line":30,"summary":"reader still reads claims.expiresAt after writer renamed it to exp",
   "failure_scenario":"any request after deploy reads undefined exp, every token is rejected, total auth outage",
   "severity":"Critical","verdict":"CONFIRMED","scope":"src/session/","effort":"high"},
  {"file":"token.ts","line":88,"summary":"revoked-token check removed before acceptance",
   "failure_scenario":"a revoked token is presented, the check is gone, the request is authorized, access-revocation is bypassed",
   "severity":"Critical","verdict":"CONFIRMED","scope":"src/session/","effort":"high"},
  {"file":"token.ts","line":42,"summary":"boundary expiry uses < instead of <=",
   "failure_scenario":"a token presented at its exact expiry second passes the < check, an expired token is accepted for one second",
   "severity":"Important","verdict":"CONFIRMED","scope":"src/session/","effort":"high"},
  {"file":"token.ts","line":60,"summary":"three-branch if/else collapsible to one ternary",
   "failure_scenario":"none — readability only","severity":"Suggestion","verdict":"PLAUSIBLE","scope":"src/session/","effort":"high"}
]
```

The two Criticals and the Important are what a gating caller (`temper`) would put in `T`; the
Suggestion is reported but never gates; the REFUTED JWKS candidate never appears.
