# USS Effect Decision Registry

Canonical USS/C# patterns chosen for this project. Consult before implementing any USS approximation to ensure cross-panel visual consistency.

New entries are appended when an effect intent has no prior decision. Existing entries are binding — use the same technique across all panels unless you explicitly fork with justification.

## How to Use

- **mock-to-unity Step 2:** Before choosing an approximation pattern for a flagged CSS effect, check this registry. If a prior decision exists for the same effect intent, use that exact approach. If none exists, choose from `uss-approximation-patterns.md`, implement it, and append a new entry here.
- **mockup-builder Translation Notes:** Reference registry entries when documenting which approximation pattern applies.
- **ui-verify:** Flag implementations that use a different technique than the registry prescribes for the same effect intent.

## Entry Format

```
## [Effect Intent Name]
- **Intent:** [What the viewer should perceive — e.g., "glowing border on interactive elements"]
- **Decision:** [Exact USS/C# pattern chosen, with reference to approximation pattern number]
- **First used:** [feature-name] (YYYY-MM-DD)
- **NOT:** [Rejected alternatives and why]
```

## Decisions

*(Empty — entries are added as panels are implemented. The first panel to use each effect intent establishes the canonical pattern.)*
