# Model-tier policy

Status: v1 (#392). Canonical home for which subagent roles may run which model
tier, why, and exactly what the guardrail does and does not enforce. Skills
that pin a non-default tier link here — link, never copy (CLAUDE.md).

## TL;DR

- **Opus 4.8 is the default** for every reasoning role except three roles
  that are not Opus-pinned — `crucible-qg-fix` (Sonnet, below), the
  standalone `/red-team` fix dispatch, and dependency-audit's inline path
  (the latter two unpinned/session, residual (a)); Sonnet for cheap
  mechanical checks (`crucible-qg-judge` /
  `crucible-qg-verifier`) and for the fix agent (`crucible-qg-fix` — the
  main-loop fix output is re-reviewed on single-model rounds that reach a
  subsequent red-team; **not** bounded on the post-pass quick-fix, the
  fix-agent terminal exits, or any escalation exit — see the row below;
  #537). **Fable 5 nowhere**, except behind an eval-gated pilot.
- **Eval-before-default:** no role flips model tier without its own A/B eval
  showing a lift that justifies Fable's **~2.6× effective cost** (2× sticker
  price × ~1.3× tokenizer overhead — Fable uses the Opus-4.7 tokenizer).
- `scripts/check_model_pins.py` (CI + `/stocktake`) fails any fable-family pin
  on a `<!-- MODEL-TIER: security-hard-out -->`-marked file and any
  security-surface file missing that marker.

## The offensive/defensive boundary — UNVERIFIED working hypothesis

Fable 5 has hard safety limits: on cybersecurity, biology, chemistry, and
model-distillation content it **blocks its own response and silently falls
back to Opus 4.8** — per-response, inside the provider, **undetectable with
current primitives** (the repo's fallback-detection keys on type-resolution
failure, and `message.model` is whole-run granularity only).

We *hypothesize* the block targets **offensive generation** (exploits,
attacks) rather than **defensive/constructive** work (feature code, planning,
defect review). **This is unverified.** Anthropic safety classifiers have
historically fired on *topic*, not *intent*, so the safe default is:

> **Treat ALL security-adjacent roles — including defensive review — as
> fallback-prone.** No security-adjacent role flips to Fable until the
> boundary-verification probe (below) resolves the question.

## Role taxonomy

| Role | Pin today | Disposition |
|---|---|---|
| siege (6 attackers, judge, fix) | opus (hard-required) | **HARD-OUT** — offensive cyber is Fable's blocked surface; static pins checker-enforced |
| dependency-audit | none (inline on session model) | **HARD-OUT marker (tripwire only)** — CVE/vuln analysis; marker catches only a future explicit pin, not the inline-on-session path |
| crucible-red-team | opus | **OUT (keep Opus)** — calibration-recall-critical; static pin checker-enforced |
| crucible-qg-judge / qg-verifier | sonnet | **OUT (keep Sonnet)** — mechanical; a fable flip is waste, not unsafe (unmarked) |
| crucible-qg-fix | sonnet | **OUT (keep Sonnet)** — fix agent / plan reviser; per-round red-team re-review on single-model rounds — a weaker fix is *caught* on rounds that reach a subsequent red-team; the cost is **at least** an extra round and is not bounded above (#528 §1 measures fix-authored defects breeding across generations, and §4 shows the stagnation judge scores the catch as PROGRESS, so the extra rounds are not observable to the loop); see `harness-adapter.md` Mapping 1b for the sites this bound does not cover (post-pass quick-fix, fix-agent terminal exits, any escalation exit) (#537). The `Eval-before-default` rule is **waived** for this downgrade, with the downstream per-round Opus red-team re-review as a partial measurement surrogate — it addresses output quality but not the rule's other named concern (calibration distribution); round-count and calibration-distribution effects remain unmeasured and are tracked in #539. Counter-evidence to weigh: #528 measures a 38% iatrogenic rate under the pre-#537 `inherit` fixer (tier unrecorded in the issue). **(unmarked)** — a future fable pin here is not checker-blocked; mark the file if the re-review bound is ever removed. |
| red-team fix dispatch (standalone/finish) | none (subagent on inherited/session model) | **Constrained by orchestrator policy** — see residual (a) |
| build implementer, delve/inquisitor, audit lenses | opus | **ELIGIBLE-PENDING-VERIFICATION** — probe-gated + eval-gated, NOT checker-blocked |
| plan/spec-writer (`build/plan-writer-prompt.md`, `spec/spec-writer-prompt.md`) | opus | **ELIGIBLE — pilot candidate** (eval-gated; a silent fallback here is harmless: fallback floor = Opus 4.8, no Tier-A verdict) |

## Eval-before-default rule

A model swap changes both output quality and the calibration distribution, so
every flip is A/B-measured, never assumed — and the eval fixtures must be
scoped so a silent Fable→Opus fallback cannot contaminate the measured Fable
arm (for the plan/spec-writer pilot: **non-security planning tasks only**).
Keep a flip iff the measured lift justifies ~2.6×; otherwise revert. The
pilot's keep/revert evidence requirements live in issue #392 (item 4 + AC3).

## Enforcement boundary — what the checker covers, exactly

`scripts/check_model_pins.py` is a static scan over **tracked `*.md`** files
(`git ls-files`, so untracked/unstaged additions are invisible until staged —
a PR-time gate, not an author-time one).

**It ENFORCES:** fable-family pins (`fable`, any `claude-fable-*` id,
case-insensitive) in the three static pin-surface forms — frontmatter
`model:`, inline `Task tool (... model: ...)`, inline
`Agent tool (... model: ...)` — under the two rules above (marked-file pin
ban + default-deny marker requirement on the security-surface set). That is
the entire enforcement surface.

**It does NOT enforce (disclosed residuals — operator convention, not
checker guarantee):**

- **(a) `inherit` / session-model roles.** Dependency-audit's inline-on-session
  path has no static pin to catch (`crucible-qg-fix` was the other member of
  this residual until #537 pinned it to Sonnet). The standalone-or-`finish`-driven `/red-team`
  fix-mechanism dispatch (`red-team/SKILL.md` fix-mechanism table) is now a
  member by the same "no static pin to catch" test — it stayed on the
  inherited/session model when `crucible-qg-fix` pinned away from it (#537;
  see #538). **Operator convention: do not run gate/build/siege — or
  red-team's full-loop fix dispatch (standalone or `finish`-driven), or dependency-audit's callers — on a Fable
  session.** A session-model guard
  hook is a named follow-up, not a v1 deliverable.
- **(b) Consensus membership.** On consensus-eligible rounds the single-model
  red-team dispatch and siege's offensive Chain Analyst are *replaced* by
  `consensus_query`, whose membership lives in untracked
  `.claude/consensus-config.yaml` (raw model ids, a `.yaml` — structurally
  outside this checker's scope). **Operator convention: no fable-family
  consensus member.** A consensus-config lint is a named follow-up.
- **(c) Any other untracked operator config.**

## Boundary-verification probe (gates all security-adjacent flips)

Before any security-adjacent role flips: dispatch a Fable-pinned agent at a
representative **defensive** review task (sanitizer / auth flow / injection
defense) and a representative **offensive** task; capture `message.model`
per run; observe which falls back. This converts the hypothesis into
evidence (or falsifies it). Out-of-v1; tracked in #392's follow-ups.

## Marker convention

Files in the security-surface set carry `<!-- MODEL-TIER: security-hard-out -->`
in the header region (immediately after YAML frontmatter for `SKILL.md` /
agent files — for live agent system prompts like `agents/crucible-red-team.md`
it must stay adjacent to the frontmatter, never inside the instructional body;
immediately after the DISPATCH comment for siege prompt templates). The marker
means "this static pin must never become fable" — it does NOT assert the file
runs Opus today (`siege-stagnation-judge-prompt.md` runs Sonnet and is still
marked, by dir-allowlist membership). Known residual: a future security skill
named outside the stems and dir allowlist bypasses default-deny — the
convention narrows the enumeration gap, it does not close it.

## Capability + trust vocabulary (#493)

Status: v1. A `MODEL-REQ` declaration (below) expresses what a role's *pipeline site*
needs and what trust it requires — not which Anthropic tier happens to satisfy that
today. It is declarative only: it binds nowhere except via
`scripts/check_model_pins.py`'s authoring-time consistency checks. It does not
replace the `model:` frontmatter pin, which remains the only field any harness
actually resolves against.

### Role-classes (pipeline-site properties, not endpoint predicates)

| Role-class | Minimum rung | Meaning |
|---|---|---|
| `recall-critical-review` | R2 | The site's output is trusted as an adversarial catch — a weaker model's miss is invisible until it ships. |
| `generative-checked` | R1 | The site generates artifact content, but a **downstream check** verifies it before it ships — a fresh reviewer, a test run, or a human (design §2.2; QG's fresh red-team re-review is one instance, not the definition). |
| `mechanical-predicate` | R0 | The site's verdict is decided by a **written rule or a re-runnable search**, not a generative judgment call (design §2.2). |

Two further tokens are not one of the three evidenced role-classes; the second is a legal fail-safe selector:

- **`accepts-offensive-security`** — a true *endpoint-side* flag, independent of
  role-class, marking a role whose task legitimately includes offensive-security
  content (exploit authorship, attack payloads). Combinable with any role-class.
- **`unclassified`** — the legal fail-safe *selector* (accepted as a `<role-class>` by the parser) for a role this taxonomy does not yet
  cover. Its only legal `on-unknown` is `refuse` (below) — an unclassified role must
  never silently proceed or degrade.

### Capability rungs

`R0` (mechanical) ⊆ `R1` (checked-generative) ⊆ `R2` (recall-critical) is **asserted**
via the brand→rung table below, not **attested** via a fixture that measures the
model actually clearing the bar. Fixture-based rung attestation is design §2.4 and
is explicitly out of scope for v1
(see the fixture-attestation follow-up issue filed for #493).

### Brand → rung table (asserted, v1)

| Brand | Rung |
|---|---|
| `opus` | R2 |
| `sonnet` | R1 |
| `haiku` | R0 |

Any other brand token (a non-Claude-Code harness's own model id, `fable`, or an
unrecognized string) resolves to **no rung** — treated as `indeterminate`, never
silently mapped to a rung by guesswork.

### Trust axis

- **`egress`** — an ordered ladder `none < first-party < third-party`. A `MODEL-REQ`
  line's `egress=<level>` declares the **most permissive** level the role tolerates;
  an operator's own egress ceiling may only **narrow** it, never widen it.
- **`no-retention` / `no-training`** — unordered obligations, present or absent.

An unsatisfiable capability×trust pairing is a Report-Only **authoring error** —
flagged, never silently resolved by relaxing trust to fit (see Report-Only rules,
`scripts/check_model_pins.py`).

### Resolution states

Four states, each with a different remedy:

| State | Meaning |
|---|---|
| `attested` | Verified against a real fixture. Not produced by anything in v1. |
| `asserted` | Taken on faith from the brand→rung table. What every Claude Code declaration produces today. |
| `unsatisfied` | The resolved rung is below the declaration's requirement. |
| `indeterminate` | The harness or brand is not one this table covers. |

### `MODEL-REQ` grammar

A standalone HTML-comment line, adjacent to frontmatter (same placement rule as the
`MODEL-TIER` marker: immediately after YAML frontmatter, never inside the
instructional body). This is **design §12's grammar, unchanged** — role-class first (this order is **enforced** by the parser, not merely displayed — S1, round 12);
rung second, **no leading vocabulary-version token**:

```
<!-- MODEL-REQ: <role-class> <rung> [accepts-offensive-security] [no-retention]
     [no-training] [ctx>=N] egress=<level> on-unknown=<value>
     [bounded-by=<citation>] -->
```

Vocabulary versioning has exactly one home in design §12 already: design §2.1's
`RESOLVED: vocab=` / `<!-- VOCAB-VERSION: v1 -->` mechanism, anchored by the
`VOCAB-VERSIONS` history block below (design §12 states even that is unwired today).
No second version slot is added to the declaration line. (An earlier draft of this
plan added a mandatory leading `<vocab>` token and made `<rung>` optional for
`unclassified`; both were unapproved changes to design §12's settled API surface and
are removed — this plan implements design §12 verbatim, not a variant of it.)

- `<role-class>` — one of `recall-critical-review`, `generative-checked`,
  `mechanical-predicate`, or `unclassified`.
- `<rung>` — **mandatory for every role-class**, one of `R0`/`R1`/`R2`, exactly as
  design §12 writes it. **Design §12 lists `unclassified` as a legal role-class while
  making `<rung>` unconditional, and does not define which rung an unclassified role
  carries.** The checker enforces the token's syntactic presence (§12's grammar) and does
  **not** interpret a rung on an `unclassified` line. It **accepts** such a
  declaration syntactically (S5, round 12): rejecting a design-legal declaration would
  make the checker recognise a *narrower* language than the approved grammar, and the
  previous unconditional hard-fail could not have been lifted by approving the rung.
  The unresolved item is the rung's *meaning*, not the syntax, and authoring such a
  declaration still waits on the approval below. **Before any
  `unclassified` declaration is authored or the checker is relied on for that
  combination, the plan stops for explicit maintainer approval** defining the rung
  semantics (approve a concrete rung, or approve an explicit grammar exemption for
  `unclassified`). This plan does **not** invent that meaning and does **not** record
  approval as granted; no `unclassified` declaration is in scope here.
- `accepts-offensive-security` — optional flag, combinable with any selector.
- `egress=<level>` — **mandatory**, one of `none`/`first-party`/`third-party` (design
  §3.1's ordered ladder); an unrecognised value is a hard fail, same as an
  unrecognised `<selector>`. Mandatory, not optional, because design §8's rule
  ("every security-surface role declares `egress=first-party` at most") is
  unstatable if the token can be omitted.
- `ctx>=<N>`, `no-retention`, `no-training` — optional trust/context fields.
  `ctx>=<N>`'s `<N>` must be a plain integer optionally suffixed `k`/`m`
  (e.g. `200k`); anything else is a hard fail.
- `on-unknown=<value>` — **mandatory**, one of:
  - `refuse` — mandatory for `recall-critical-review`, `unclassified`, and any
    declaration carrying `accepts-offensive-security`.
  - `degrade-with-disclosure` — legal **only** for `generative-checked`; requires a
    mandatory `bounded-by=<citation>`.
  - `proceed` — legal **only** for `mechanical-predicate`.
- `bounded-by=<citation>` — mandatory iff `on-unknown=degrade-with-disclosure`;
  illegal (and meaningless — hard fail) otherwise. `<citation>` is **either** a
  `file:line` **or** a role name naming the downstream check the disclosure claims
  bounds it — design §12's two alternatives, both accepted (S3, round 11): a role
  name `[a-z][a-z0-9-]*` (e.g. `red-team`, `crucible-qg-verifier`) or a path with a
  **positive** line (`model-tier-policy.md:51`). The checker verifies the
  citation's **shape** only; that the named check exists and actually bounds the
  disclosure is a semantic claim asserted at Task 6, **not** mechanically verified
  here (S3, round 11) — a `file:line` that names no real check is still an
  authoring defect Task 6 owns.

Example (`crucible-qg-fix`'s own declaration, Task 6):

```
<!-- MODEL-REQ: generative-checked R1 ctx>=200k egress=first-party on-unknown=degrade-with-disclosure bounded-by=model-tier-policy.md:51 -->
```

### Unsatisfiable pairs disclosed for v1

A named, versioned literal (design §3.3/§12) — three pairs, checked by
`check_model_req_report_only()` (Task 5):

- `{R2, egress=none}` — unsatisfiable on most racks today (design §3.3). This is the
  *driver's future local-orchestrator endgame* pin, not what this plan's own
  declarations use in Task 6 (which pin each role to its actual deployment's
  `egress=first-party`, per design §8) — so it is Report-Only-checked but does not
  fire against this plan's four declarations on day one.
- `{R2, no-retention}` — unsatisfiable under some vendor postures (design §3.3). Same
  treatment; does not fire against this plan's four declarations on day one.
- `accepts-offensive-security` × basis `indeterminate` (the #392 boundary-
  verification probe has never been run, so no endpoint resolves it, design §8) —
  unsatisfiable on *any* endpoint today, including the incumbent Anthropic install
  `crucible-red-team` runs on (design §3.3, §8). Report-Only, permanent until design
  §2.4's fixture attestation lands. **This is the one pair that does fire on day
  one**, against `agents/crucible-red-team.md`'s own declaration — expected, not
  a defect, and disclosed as such at the point the declaration is authored (#493).

All three graduate to hard-fail together, per design §7.2/§3.3, when the #392
boundary-verification probe has run and at least one endpoint resolves
`accepts-offensive-security` to `attested` or `unsatisfied`.

### `VOCAB-VERSIONS` history

<!-- VOCAB-VERSION: v1 -->

| Version | Introduced | Notes |
|---|---|---|
| `v1` | #493 | Initial role-class/rung/trust vocabulary. |
