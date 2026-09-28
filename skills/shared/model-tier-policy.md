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
