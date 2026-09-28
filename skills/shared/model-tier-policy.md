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
Fable-family session. Repo-side enforcement is static-only; this part is operator-owned.

## Security-surface preflight

Model strength for security work is no longer repo-bound, so the orchestrator makes the residual
visible instead of letting a security PASS imply a model guarantee. Before any security-sensitive leg
(`siege`, `dependency-audit`, a `quality-gate` red-team round on a security surface, or a
`crucible-red-team` dispatch) reports PASS, it records one line naming the model actually in use at
the **top of that leg's findings artifact** — receipt grammar allows no free prose, so the line lives
in the artifact, not in the receipt. Position: line 1 where the artifact has no mandated first line
(`siege`); otherwise the line immediately after the mandated one — a `quality-gate` red-team findings
file keeps `SEVERITY-COUNTS: fatal=… significant=… minor=…` on line 1 (its receipt cites `#L1-L1`)
and takes the preflight line directly beneath it; `audit-results.md` takes it above its
`# Dependency Audit` heading:

```
SECURITY-PREFLIGHT: model=<id|unknown> host=<harness> -- strength not repo-bound; guardrail static-only
```

Non-blocking when `<id>` is `unknown` or any non-Fable model: record the line and proceed. Blocking
when `<id>` is Fable-family: refuse the leg (`BLOCKED`, never PASS) — security-surface work does not
run on a Fable-family model.

Acceptance check: the leg's receipt must cite the artifact range containing the line, and a
security-surface PASS whose findings artifact carries no `SECURITY-PREFLIGHT` line is `BLOCKED`, not
PASS — including when the round ran on the `general-purpose` fallback or as a look-harder
re-dispatch. The blocking branch outranks any skip or result-ordering rule in the consuming skill
(e.g. dependency-audit's `skip_blocking`): a hard-out model blocks regardless.
