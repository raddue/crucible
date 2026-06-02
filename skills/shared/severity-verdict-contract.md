# Severity + Verdict Contract — Review Trio

> **Sole authority** for the severity scale and verify-gate verdict vocabulary used by
> the **review trio** — `delve` / `delve-engine`, `temper`, and `audit`. Per invariant
> **I11**, no trio skill defines its own severity scale or verdict vocabulary; they emit
> and consume the ones pinned here. (**I11**: no review-trio skill defines its own
> severity scale or verdict vocabulary — this contract is that single source.)
>
> **Consumed via** `<!-- CANONICAL: shared/severity-verdict-contract.md -->` — link this
> file, never copy its tables (copying causes drift).
>
> **Producers / consumers:**
> - `shared/delve-engine.md` (to be authored in #330) — **will emit** `{severity, verdict}`
>   per this contract on every record.
> - `temper` — already **emits** this 4-tier Critical/Important/Minor/Suggestion scale today; #333
>   reshapes it to also **consume** the verdict-keyed gating rule below to build its tracked set `T`.
> - `audit` (reshaped in #332) — emits systemic findings on this severity scale and, under
>   `--bugs`, consumes delve's `{severity, verdict}` records. **Until #332 lands, audit still
>   emits on the 3-tier `severity-rubric.md` scale; its migration onto this contract is part of
>   the Review-Trio Reshape.** See **Relationship to `severity-rubric.md`** below.
>
> **Scope boundary:** this contract governs the trio's **instance-bug / merge-gate** vocabulary.
> It does **not** replace `shared/severity-rubric.md` (the quality-gate family's adversarial
> convergence-scoring scale). See **Relationship to `severity-rubric.md`** below.

## 1. Severity scale

Four tiers. Use the single most severe applicable tier; do not stack (no "low-Critical",
no "Important+"). Severity sets the gating *band*; §3 combines it with the verify-gate
verdict to decide whether a finding actually gates.

| Severity | Meaning | In gating band (C/I)? |
|---|---|---|
| **Critical** | If shipped, the change fails at its primary purpose: data loss/corruption, crash on a reachable path, security hole (RCE/injection/auth bypass), broken core contract. | **Yes** |
| **Important** | Meaningfully degrades correctness or robustness but the change still works: a real defect on a non-primary path, a missing check at a trust boundary, a regression a user would hit but route around. | **Yes** |
| **Minor** | Worth fixing eventually, negligible immediate impact: naming, redundancy, a non-critical missing test, a small inefficiency. | No |
| **Suggestion** | An optional improvement or nicety; nothing is wrong if it ships as-is. | No |

**Critical and Important are the gating band ("C/I").** Minor and Suggestion are **both
non-gating** — neither ever enters the tracked set `T`. They are reported verbatim, never
dropped, but they do not block a Clean verdict.

## 2. Verdict vocabulary

The verify gate assigns exactly one verdict to each candidate it adjudicates. (The gate
mechanism — dedup, verifier dispatch — is defined in `delve-engine.md`, not here; this
contract pins only the vocabulary and what each verdict means for gating.)

| Verdict | Meaning | Kept? |
|---|---|---|
| **CONFIRMED** | The verifier reproduced or otherwise positively established the defect against the code. | Kept |
| **PLAUSIBLE** | The verifier finds the defect credible against the code but cannot produce a runnable reproduction (e.g. it depends on runtime state the verifier cannot drive). | Kept |
| **REFUTED** | The verifier showed the candidate is not a defect (the suspect construct is sound, guarded, or unreachable). | **Dropped** |

`REFUTED` candidates are dropped at the gate and never appear in output. `CONFIRMED` and
`PLAUSIBLE` candidates are kept and carried into the ranked findings.

## 3. The gating rule (tracked set `T`)

`temper`'s merge gate keys on the **tracked set `T`** — the findings that gate merge. `T` is
computed **by `temper`** from the `{severity, verdict}` records `delve-engine` emits (and the
records `audit --bugs` cross-checks); `delve-engine` and `audit --bugs` **emit** those records
but do not themselves compute `T`. A kept finding enters `T` **iff** its verdict is `CONFIRMED`
**or** `PLAUSIBLE` **and** its severity is `Critical` **or** `Important`:

> **T = { CONFIRMED, PLAUSIBLE } × { Critical, Important }**

The full verdict × severity matrix (every cell defined — no implicit behavior):

| | Critical | Important | Minor | Suggestion |
|---|---|---|---|---|
| **CONFIRMED** | **enters `T`** (gates) | **enters `T`** (gates) | reported at its own tier, non-gating | reported at its own tier, non-gating |
| **PLAUSIBLE** | **enters `T`** (gates) | **enters `T`** (gates) | reported at its own tier, non-gating | reported at its own tier, non-gating |
| **REFUTED** | dropped | dropped | dropped | dropped |

Reading the matrix:

- **Only the top-left 2×2 gates.** A `PLAUSIBLE@{Critical,Important}` finding gates even
  without a runnable repro — a real regression the verifier can only call PLAUSIBLE must still
  block merge (closing the recall hole this trio exists to fix). It is `temper`'s discharge
  path — not this contract — that decides how such a member later leaves `T`.
- **Below C/I, verdict stops mattering for gating.** A `CONFIRMED@Suggestion` is reported at its
  own Suggestion tier and never gates — handled exactly as a `Minor` finding is. A `PLAUSIBLE`
  below C/I is handled the same way. A finding below C/I **leaves the merge gate** but keeps its
  severity tier verbatim in the report (§1: do not stack severities) — leaving the gate is **not**
  a tier rewrite.
- **`REFUTED` is dropped at every severity** — it never reaches output, so its severity is moot.

`audit --bugs` consumes the same kept set (`CONFIRMED` + `PLAUSIBLE`) when cross-checking its
systemic findings against delve instances; the C/I gating column is `temper`-specific (audit
does not gate merge), but the scale and verdicts are identical.

## 4. Finder angle → severity mapping

`delve-engine` runs seven finder angles. Every angle is covered here so a record's severity is
never angle-ambiguous. The **verify gate** assigns the verdict (§2) independently of the angle;
this table pins the **severity band each angle may emit**.

| Finder angle | Class | Severity band it may emit | Can it gate? |
|---|---|---|---|
| line-by-line diff scan | **bug** | Critical / Important / Minor / Suggestion | yes (when CONFIRMED/PLAUSIBLE @ C/I) |
| removed-behavior auditor | **bug** | Critical / Important / Minor / Suggestion | yes (when CONFIRMED/PLAUSIBLE @ C/I) |
| cross-file tracer | **bug** | Critical / Important / Minor / Suggestion | yes (when CONFIRMED/PLAUSIBLE @ C/I) |
| reuse | quality | **Minor / Suggestion only** (capped) | **no** |
| simplification | quality | **Minor / Suggestion only** (capped) | **no** |
| efficiency | quality | **Minor / Suggestion only** (capped) | **no** |
| altitude | quality | **Minor / Suggestion only** (capped) | **no** |

- The three **bug angles** (line-by-line, removed-behavior, cross-file tracer) may emit the full
  scale; whether they gate is decided by §3 against the verify-gate verdict.
- The four **quality angles** (reuse, simplification, efficiency, altitude — angle names defined by
  `shared/delve-engine.md`, #330) are **capped at Minor/Suggestion by construction** — they never
  emit Critical or Important, so they **never enter `T` regardless of verdict** (a `CONFIRMED@Minor`
  reuse finding is still non-gating). This mirrors, *as an analogy of ceiling-discipline only* (not a
  one-to-one angle→lens mapping), the per-lens Minor ceilings `shared/reviewer-common.md` places on
  its *quality* lenses (DRY / SRP / OCP); reviewer-common's Surgical-Changes lens is a scope/bug lens
  that may emit Critical/Important and is **not** one of these four quality angles. A genuinely
  Critical/Important concern that surfaces while
  running a quality angle is a **bug-angle finding** and is re-attributed to the owning bug angle
  (and to a Correctness/Architecture concern), exactly as reviewer-common's DRY re-attribution
  escape hatch already does — it is not emitted as a Critical "quality" finding.

This makes "every finder angle × every verdict/severity" total: bug angles span the full matrix
of §3; quality angles occupy only the two non-gating rows/columns and are ineligible for `T` by
the cap, never by an ad-hoc rule.

## 5. Relationship to `shared/severity-rubric.md`

The repo has a **second, older** severity scale and the two **coexist by design** — they serve
different machines:

| | This contract | `severity-rubric.md` |
|---|---|---|
| **Scale** | Critical / Important / Minor / Suggestion (4-tier) | Fatal / Significant / Minor (3-tier) |
| **Verdicts** | CONFIRMED / PLAUSIBLE / REFUTED (verify gate) | none (red-team assigns severity directly) |
| **Purpose** | Instance-bug **merge gate** for the review trio | **Adversarial convergence scoring** (weighted Fatal=3 / Significant=1 / Minor=0) |
| **Used by** | `delve` / `delve-engine`, `temper`, `audit` (after its #332 reshape) | `quality-gate`, `red-team`, `siege`, `audit` (until #332), `inquisitor`, `build` (per `severity-rubric.md`'s own consumer declaration) |

**`audit` is mid-migration and appears in both columns during the transition.** Today it emits on
`severity-rubric.md`'s 3-tier scale; the Review-Trio Reshape (#332) moves its systemic findings onto
*this* contract's 4-tier scale. On completion of #332, audit emits only on this contract and leaves
`severity-rubric.md`'s consumer list. This is the one sanctioned dual-membership, and it is temporary
by construction — it is **not** a standing fork (I11), it is a scheduled migration. (`ledger`
references `severity-rubric.md` for a monthly spot-check advisory, not as a scale consumer, so it is
not listed here.)

`severity-rubric.md`'s weighted points (3/1/0) drive the quality-gate family's stagnation math;
that math would break if its scale were swapped for this one. Therefore:

- This contract is the **sole authority for the review trio only**. I11 ("no skill forks its own
  severity scale") is scoped to the trio: a trio skill may not invent a *new* trio severity scale.
- It does **not** govern, replace, or convert the `severity-rubric.md` adversarial-scoring scale.
  A quality-gate-family skill using Fatal/Significant/Minor is **not** "forking a scale" — it is
  using the separate, sanctioned scoring system.
- **No normative conversion exists** between the two. As a reader's intuition only (never a
  computed mapping): Critical ≈ Fatal, Important ≈ Significant, Minor/Suggestion ≈ Minor. Do not
  build any rule, score, or gate on that correspondence — it is illustrative, not a contract.

If a future milestone unifies the two scales, that is a separate, larger change; this contract
deliberately does not attempt it.

## 6. Anti-patterns

Do not:

- **Invent a new trio scale** ("Blocker", "Nit") — emit one of the four tiers (I11).
- **Stack severities** — one tier per finding.
- **Gate on Minor or Suggestion** — only the C/I band gates; both lower tiers are non-gating.
- **Gate on a quality-angle finding** — quality angles are capped non-gating; re-attribute a real
  C/I concern to a bug angle instead of raising a quality finding to Critical/Important.
- **Keep a `REFUTED` candidate** — it is dropped at the gate, not down-severitied into output.
- **Discharge a `PLAUSIBLE@C/I` member on prose alone** — that is `temper`'s discharge rule, not
  this contract; here, `PLAUSIBLE@C/I` simply gates.
- **Convert between this scale and `severity-rubric.md`** — they coexist; there is no mapping.
