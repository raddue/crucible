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
`crucible-red-team` dispatch) reports PASS, it appends one line naming the model actually in use to
**its own preflight artifact** — a separate file, so no findings-artifact first-line, schema, or
receipt-citation contract is disturbed:

```
<dispatch-dir>/security-preflight.md      # legs dispatched through shared/dispatch-convention.md
scratch/<run-id>/security-preflight.md    # dependency-audit, which has no dispatch dir
```

One line per leg per round, appended (never overwritten):

```
SECURITY-PREFLIGHT: round=<n> leg=<siege|dependency-audit|red-team|...> model=<id|unknown> host=<harness> -- strength not repo-bound; guardrail static-only
```

Non-blocking when `<id>` is `unknown` or any non-Fable model: append the line and proceed. Blocking
when `<id>` is Fable-family: refuse the leg (`BLOCKED`, never PASS) — security-surface work does not
run on a Fable-family model.

Acceptance check: the **consuming orchestrator** reads that file before accepting a security-surface
PASS — a missing file, or a missing line for the round being accepted, is `BLOCKED`, not PASS.
Nothing here asks a receipt to cite a range it was never shaped to cite, and no leg has to move a
line another contract already owns. This holds for the `general-purpose` fallback and look-harder
re-dispatches too. The blocking branch outranks any skip or result-ordering rule in the consuming
skill (e.g. dependency-audit's `skip_blocking`): a hard-out model blocks regardless.
