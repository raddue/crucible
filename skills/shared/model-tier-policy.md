# Model-tier policy

Status: v2 (#392; model-agnostic dispatch slice). Canonical home for role
dispatch profiles, trust restrictions, fallback behavior, and exactly what the
static guardrail does and does not enforce. Skills should request a profile
rather than a provider-specific model ID wherever practical; legacy provider
aliases remain valid during incremental migration. Link here — never copy
(CLAUDE.md).

## Canonical dispatch profiles

| Profile | Intended work | Current Claude Code reference alias |
|---|---|---|
| `high` | Complex analysis, adversarial review, architecture/design judgment | `opus` |
| `standard` | Routine review, synthesis, mechanical fixes, bounded recording | `sonnet` |
| `fast` | Narrow lookup/structural mapping where speed dominates judgment | `haiku` |
| `inherit` | Caller/session model decides; no profile preference | `inherit` |

The role tables below preserve current provider aliases and measured history.
Read `opus`, `sonnet`, and `haiku` there as today's Claude Code mapping of
`high`, `standard`, and `fast`, not as universal runtime requirements. Other
harnesses map profiles through `shared/harness-adapter.md`; where a harness has
no supported mapping, omit the model parameter and use the operator/session
default rather than inventing a provider-specific ID.

## No-stop dispatch resolution

Runtime model routing is a recommendation and trust constraint, never a new
pipeline failure gate:

1. Honor an explicit operator/harness model override.
2. Otherwise map the requested profile through the harness's configured model.
3. Otherwise use the session/harness default.
4. If the requested model or effort is unsupported, omit that unsupported field
   and continue on the best permitted available model.
5. On transient provider faults, retry within the existing dispatch/replay
   protocol, then use another permitted model where available.
6. If no permitted model is available, preserve the pending dispatch and
   continue independent work; do not terminate or restart the whole autonomous
   pipeline solely because one model route failed.

Record the requested profile and actual observed model when the harness exposes
it; `null` actual model means unmeasured, not unauthorized. Calibration claims
must distinguish measured from unmeasured routing and must not fabricate an
actual model. Security/trust and data-egress restrictions still apply: never
route restricted material to an unpermitted provider/model merely to avoid a
fault. If no permitted route exists for restricted work, preserve that work and
continue unrelated tasks.

`scripts/check_model_pins.py` is an author-time repository check; it is not a
runtime dispatch gate and must not be used to stop a live dispatch.

## TL;DR

- **The `high` profile is the default** for every reasoning role except three roles
  that are not Opus-pinned — `crucible-qg-fix` (Sonnet, below), the
  standalone `/red-team` fix dispatch, and dependency-audit's inline path
  (the latter two unpinned/session, residual (a)); the `standard` profile for cheap
  mechanical checks (`crucible-qg-judge` /
  `crucible-qg-verifier`) and for the fix agent (`crucible-qg-fix` — the
  main-loop fix output is re-reviewed on single-model rounds that reach a
  subsequent red-team; **not** bounded on the post-pass quick-fix, the
  fix-agent terminal exits, or any escalation exit — see the row below;
  #537). Current Claude Code aliases: `high` → Opus 4.8, `standard` → Sonnet.
  **Restricted-trust models are nowhere**, except behind an eval-gated pilot;
  the current static checker maps that restriction to the Fable family.
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
case-insensitive) in the static pin-surface forms — line-anchored
`model:`/`model_profile:`, inline `Task tool (... model:`/`model_profile: ...)`,
inline `Agent tool (... model:`/`model_profile: ...)` — under the two rules
above (marked-file pin ban + default-deny marker requirement on the
security-surface set). The neutral `model_profile:` key is scanned so migrating
a security-named file to profile vocabulary cannot evade the marker
requirement. That is the entire author-time enforcement surface; it is not a
runtime dispatch gate.

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
