# Model-selection guardrail

Crucible skills and agent definitions specify roles and tasks, not model IDs or tiers. Model selection
belongs to the host harness and operator; do not add model selectors to dispatch calls or agent/skill
frontmatter.

## Security marker

`<!-- MODEL-TIER: security-hard-out -->` marks files whose security-sensitive work must not receive a
Fable-family model selector. The marker is a static guardrail, not a model assignment.

Why it exists: Fable-family models are reported to block offensive-security content and to fall back
to another model without telling the caller (working hypothesis, never measured here). A silent
fallback would make a recall-critical security reviewer nondeterministic, so marked files reject the
selector outright instead of relying on runtime detection.

`scripts/check_model_pins.py` scans tracked Markdown for Fable-family selectors in frontmatter and
inline `Task`/`Agent` calls. It rejects selectors in marked files and requires the marker on the
security-surface files in its allowlist. Known gaps (documented in the checker, not enforced):
untracked/unstaged files are invisible to `git ls-files`; the name-stem set applies only to files that
already carry a selector; a nested parenthesis before `model:` truncates the scan; fenced
counter-examples are stripped before scanning. The checker cannot inspect runtime host configuration
or model selection made outside these static forms — it is a static gate, never a runtime guarantee.

Keep `agents/crucible-red-team.md` marker adjacent to frontmatter. Do not remove or weaken the checker
or marker requirement.

## Operator rule

Do not run `quality-gate`, `build`, `siege`, `dependency-audit`, or a security `consensus` panel on a
Fable-family session. Repo-side enforcement is static-only; this part is operator-owned. Nothing
repo-side binds review strength any more — `docs/decisions/0003-host-selected-models.md` records
that as an accepted risk, with the mitigation and the reason no mechanical preflight check ships.

## Capability + trust vocabulary (#493)

Status: v1. A `MODEL-REQ` declaration (below) expresses what a role's *pipeline site*
needs and what trust it requires — not which Anthropic tier happens to satisfy that
today. It is declarative only: it binds nowhere except via
`scripts/check_model_pins.py`'s authoring-time consistency checks. It does not select a model and does not reinstate one: under ADR-0003 the host
harness and operator choose, and nothing repo-side binds that choice — these
declarations are authoring-time vocabulary for `scripts/check_model_pins.py`
consistency checks, not a dispatch-time selector.

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
| `asserted` | Taken on faith from the brand→rung table — and only when an observed resolution exists to back it. Nothing in this repo produces it today: #651 removed every `model:` pin, so no declaration resolves to a brand at all. |
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
  *driver's future local-orchestrator endgame* posture, not what this plan's own
  declarations use in Task 6 (which declare each role at its actual deployment's
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
