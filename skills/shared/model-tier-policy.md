# Model-selection guardrail

Crucible skills and agent definitions specify roles and tasks, not model IDs or tiers. Model selection
belongs to the host harness and operator; do not add model selectors to dispatch calls or agent/skill
frontmatter.

## Security marker

`<!-- MODEL-TIER: security-hard-out -->` marks files whose security-sensitive work must not receive a
Fable-family model selector. The marker is a static guardrail, not a model assignment.

`scripts/check_model_pins.py` scans tracked Markdown for Fable-family selectors in frontmatter and
inline `Task`/`Agent` calls. It rejects selectors in marked files and requires the marker on the
security-surface files in its allowlist. It cannot inspect untracked files, runtime host configuration,
or model selection made outside these static forms.

Keep `agents/crucible-red-team.md` marker adjacent to frontmatter. Do not remove or weaken the checker
or marker requirement.
