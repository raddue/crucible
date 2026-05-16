# Severity Rubric

Canonical severity definitions for adversarial review across crucible skills (quality-gate, red-team, siege, audit, inquisitor, build). Anchor for both Opus and Sonnet roles so finding severities are interpreted consistently across models.

## Three-tier Scale

Findings fall into one of three severity tiers. Use the most severe applicable tier; do not stack severities.

### Fatal

A finding that, if shipped, will cause the artifact to fail at its primary purpose. Examples:

- **Code:** Logic errors that cause incorrect output, data corruption, unbounded resource use, security vulnerabilities (RCE, injection, auth bypass), crashes under normal input, broken core feature contract.
- **Design / plan:** A decision that violates a stated constraint, a missing component required by the goal, an architectural choice incompatible with the rest of the system.
- **Hypothesis:** An explanation incompatible with the observed evidence.

A Fatal finding is **load-bearing for the artifact's claim to be correct**. If a reasonable user could reach the buggy state through the documented flow, it is Fatal. If reaching it requires a malicious actor or specific concurrency, it may still be Fatal — the question is impact, not access.

Fatal contributes **3 points** to the weighted score (Fatal=3, Significant=1, Minor=0).

### Significant

A finding that meaningfully degrades the artifact's quality but does not prevent it from working. Examples:

- **Code:** Missing error handling at non-trust-boundary sites, missing validation on internal callers, inefficient algorithms that would matter at scale, missing tests for non-critical paths, API ergonomics issues.
- **Design / plan:** Underspecified component, missing rationale for a non-obvious decision, missing edge case in scope, unclear acceptance criteria.
- **Hypothesis:** A plausible-but-incomplete explanation that needs evidence to confirm.

Significant findings should be fixed in the same PR/cycle but do not block initial usefulness. A user encountering one will be frustrated, not stopped.

Significant contributes **1 point** to the weighted score.

### Minor

A finding worth fixing eventually but with negligible immediate impact. Examples:

- **Code:** Naming inconsistencies, missing comments where the WHY is obvious, formatting drift, redundant code, tests that pass but could be more rigorous.
- **Design / plan:** Wording polish, minor formatting, redundancy with another section.

Minor findings accumulate across rounds without triggering fix loops. The orchestrator may quick-fix them after the gate passes (see quality-gate's Minor Issue Handling).

Minor contributes **0 points** to the weighted score.

## Adjudication Rules (cross-model)

When a Sonnet agent (stagnation judge, fix verifier) reads severity labels assigned by an Opus agent (red-team, fix agent), apply these rules:

1. **Trust the source-of-truth label.** The red-team agent that produced the finding owns its severity. Do not silently re-score.
2. **Flag disagreements explicitly.** If the consuming agent (judge, verifier) reads a label that disagrees with its own assessment, surface the disagreement in its receipt: `severity-disagreement: <finding-id> labeled=<X> assessed=<Y> reason=<sentence>`. Do not override.
3. **Sonnet does not permanently override Opus.** When verifier marks a Fatal as Unresolved twice running, the verdict downgrades to informational (per quality-gate's Fix Verification rules). The same principle applies to the stagnation judge: if the judge's STAGNATION verdict contradicts the orchestrator's score-strictly-improving signal, prefer the orchestrator.

## Edge Cases

- **A finding that affects only a subset of users:** If the affected subset is non-trivial (≥1% of expected use cases, OR any safety/security path), severity follows what happens to the affected subset. A Fatal-for-1% finding is Fatal, not Significant.
- **Defense-in-depth gaps:** Missing a redundant safety check is Significant, not Fatal, unless the primary check is also unsound.
- **Findings about findings (meta-issues):** Tooling problems (e.g., "the test suite doesn't run") are Significant unless they prevent the artifact from being shipped at all.

## Anti-Patterns

Do not:

- Upgrade a finding to Fatal because the reviewer feels strongly about it. Severity is impact-based, not enthusiasm-based.
- Downgrade a finding to Minor because it would be inconvenient to fix. Convenience is not a severity input.
- Stack severities ("Significant-plus", "low Fatal"). The scale is three-tier; commit to one.
- Apply this rubric to findings outside adversarial review (e.g., feature requests, refactoring suggestions). It's calibrated for "what's broken / what's wrong," not "what could be better."
