# Model-tier policy

Status: v1 (#392). Canonical home for which subagent roles may run which model
tier, why, and exactly what the guardrail does and does not enforce. Skills
that pin a non-default tier link here — link, never copy (CLAUDE.md).

## TL;DR

- **Opus 4.8 is the default** for every reasoning role; Sonnet for cheap
  mechanical checks (`crucible-qg-judge`/`crucible-qg-verifier`). **Fable 5
  nowhere**, except behind an eval-gated pilot.
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
| crucible-qg-fix | inherit | **Constrained by orchestrator policy** — see Enforcement boundary (a) |
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

- **(a) `inherit` / session-model roles.** `crucible-qg-fix` (inherits the
  session model) and dependency-audit's inline-on-session path have no static
  pin to catch. **Operator convention: do not run gate/build/siege — or
  dependency-audit's callers — on a Fable session.** A session-model guard
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
