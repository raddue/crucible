---
name: mock-to-unity
description: Use when implementing Unity UI Toolkit code from a mockup, HTML reference, screenshot, or visual spec. Triggers on "implement this mockup", "translate to USS", "build this UI", "match the mock", "UI looks wrong", "fix the layout", "spacing is off", "doesn't look like the design", or any task turning a visual reference into Unity UI Toolkit USS/C# code.
---

# Mock to Unity

Translate visual mockups into Unity UI Toolkit code (USS/C#) with structural fidelity. Prevents drift through a mandatory translation map, layered implementation, and self-verification.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Related skills:** When writing C# controllers (Layers 1, 3, 4), your project's coding standards apply to all C# code. After implementation, `test-driven-development` applies for controller tests. After self-verification, `crucible:quality-gate` validates the output.

## Architecture Decision: Programmatic C# (Not UXML)

Build VisualElement trees programmatically in C# — do not use UXML. The project has moved to programmatic construction because `styleSheets.Add(Resources.Load<StyleSheet>())` silently fails in Unity 6 (Issue #412). UXML-based workflows depend on stylesheet loading that is broken.

**Exception:** If the target panel already uses UXML (check the existing controller), follow its pattern rather than mixing approaches.

## File Placement

| Output | Location |
|--------|----------|
| USS files | `Assets/_Project/Resources/UI/` |
| C# controllers | `Assets/_Project/Scripts/Systems/UI/<subsystem>/` |
| Theme.uss variable additions | `Assets/_Project/Resources/UI/Theme.uss` |

If unsure which subsystem directory, grep for similar controllers or check the cartographer module maps.

## Step 1: Read the Mockup

Read the full source mockup before writing any code.

- **HTML file:** Read the complete file. If too large, read in sections and summarize each section's structure, variables, and layout.
- **Screenshot/image:** Describe every visible element, its approximate position, colors, text, spacing, and hierarchy. Assign BEM class names based on the visual hierarchy. Estimate colors by matching to the nearest Theme.uss variable. Estimate spacing by matching to the nearest `--spacing-*` value. Document estimation uncertainty in the translation map.
- **Text/ASCII:** Parse the described structure into a mental model of containers and elements.

Do not skip this step. Do not skim. The mockup is the source of truth for the entire implementation.

## Step 2: Produce a Translation Map

Write a structured mapping document before any implementation code. This is the checkpoint that catches drift early. **Persist the translation map to `docs/plans/<feature>-translation-map.md` and commit it.** All subsequent steps reference this file on disk, not conversation context.

### Selectors
Map every CSS class to its USS selector:
```
.talent-node          → .talent-node
.talent-node__icon    → .talent-node__icon
.talent-node--maxed   → .talent-node--maxed
```

### Properties
Map every CSS property to USS equivalent. Flag gaps:
```
padding: var(--spacing-md)     → padding: var(--spacing-md)        [direct]
gap: var(--spacing-sm)         → not supported in USS               [use margin on children]
text-overflow: ellipsis        → needs C# truncation                [inline workaround]
:hover background change       → PointerEnterEvent callback         [C# layer 4]
```

### Variables
Confirm every CSS variable exists in Theme.uss. Read the mockup-builder skill's references/theme-variables.md for the catalog:
```
var(--color-bg-base)       → exists in Theme.uss     [ok]
var(--color-vendor-price)  → NOT in Theme.uss         [needs adding]
```

**:root Value Validation:** For each `:root` variable in the mockup, verify its VALUE matches the mockup-builder skill's `references/theme-variables.md` (which reflects Theme.uss `:root`). Flag value mismatches — these cause the mockup to render differently in browser vs Unity:
```
var(--color-bg-base): rgb(20, 20, 31) in mockup → rgb(20, 20, 31) in Theme.uss   [ok]
var(--color-bg-base): rgb(25, 25, 40) in mockup → rgb(20, 20, 31) in Theme.uss   [MISMATCH - fix mockup or update Theme.uss]
```

### Effect Decision Registry

Before choosing a USS approximation pattern for any flagged CSS effect:
1. Read `skills/shared/uss-effect-decisions.md`
2. If a prior decision exists for the same effect intent (e.g., "outer glow on interactive elements"), use that exact pattern — do not choose a different approximation
3. If no prior decision exists, choose from `skills/shared/uss-approximation-patterns.md`, implement it, and append a new entry to the registry after the implementation is verified
4. To deliberately deviate from a registry decision, document the justification in the translation map and note it as a fork in the registry entry

This ensures visual consistency across all panels. Panel 15 should use the same glow technique as Panel 1.

### Hierarchy
Map HTML nesting to VisualElement tree:
```
div.talent-panel               → VisualElement "talent-panel"
  div.top-bar                  →   VisualElement "top-bar"
    div.search-wrapper         →     VisualElement "search-wrapper"
      input.search-box         →       TextField "search-box"
    div.points-display         →     VisualElement "points-display"
```

### Bug Zone Flags
Flag known Unity 6 USS issues:
- `[SCROLLVIEW]` — height/min-height inside ScrollView children → inline C# required
- `[FONTMANAGER]` — new runtime UIDocument → `FontManager.ApplyToRoot(root)` required
- `[STYLESHEET]` — do not use `styleSheets.Add(Resources.Load<StyleSheet>())` — embed in existing USS or inline C#
- `[DIMENSIONS]` — runtime UIDocument rootVisualElement resolves to 0x0 with percentage/flex sizing → use explicit pixel dimensions

## Step 2.5: Generate Structural Scaffold

After the translation map is written to disk, generate a structural scaffold — a starting C# file that mechanically derives from the map:

1. **Full VisualElement tree** from the Hierarchy section — every element with its correct class name assigned via `AddToClassList()`, in the correct nesting order. This eliminates name drift between map and code.

2. **Extra elements for USS approximation patterns** — for each gap flagged in the Properties section that references an approximation pattern requiring additional elements (shadow siblings for Pattern 3, inset-glow children for Pattern 2, glow-line children for Pattern 8, gradient segments for Pattern 6), insert the extra VisualElements at the correct position in the tree with TODO comments:
   ```csharp
   // USS approximation: outer glow (Pattern 1) — see uss-approximation-patterns.md
   // TODO: verify border-width and border-color values match translation map
   ```

3. **Bug zone stubs** at every site flagged `[SCROLLVIEW]`, `[FONTMANAGER]`, `[DIMENSIONS]` in the Bug Zone Flags section:
   ```csharp
   // [SCROLLVIEW] USS height ignored inside ScrollView children (Unity 6)
   // TODO: set value from translation map — var name: --spacing-3xl
   scrollChild.style.height = new StyleLength(/* TODO */);
   ```

4. **Effect Decision Registry references** — for each approximation pattern used, include a comment noting the registry decision (if one exists) or marking it as a new decision to be registered after verification.

The scaffold is the **starting point** for Layer 1, not a separate deliverable. Layer 1 becomes "review and fill in the scaffold" rather than "build the tree from scratch." Layer 2 USS can immediately target the scaffold's class names. Layer 3 fills in the TODO stubs.

**Include the scaffold in the Step 3 checkpoint** so the user can review structure before implementation begins.

**The scaffold is generated by the implementing agent, not by an external tool.** The agent reads its own translation map and mechanically produces the C# file. This is deterministic template expansion, not creative work.

## Step 3: User Checkpoint

Present the translation map AND the structural scaffold. Wait for approval before proceeding to Layer implementation. Explicitly state the element count, approximation-pattern elements added, and bug zone stubs included.

- Number of elements in the hierarchy
- Number of USS properties that translate directly
- Number of items flagged for inline C# workarounds
- Any new Theme.uss variables needed

If operating autonomously (e.g., as a subagent in a build pipeline), skip the wait but still produce the map in output for traceability.

## Step 4: Implement in Layers

Build in this order. Do not skip layers or combine them.

**Layer 1 — Structure:** Start from the Step 2.5 scaffold. Review the generated VisualElement tree, fill in any remaining structural details, and verify element count and nesting depth match the translation map. The scaffold provides the correct class names and approximation-pattern elements — do not rename or restructure unless the translation map is wrong.

**Layer 2 — USS Styling:** Write USS selectors using Theme.uss variables. Reference the translation map for every property. Use `var()` references exclusively — no hardcoded values. For any variable flagged as "needs adding to Theme.uss" in the translation map, add it to `Assets/_Project/Resources/UI/Theme.uss` in the appropriate section with a comment. Also update the mockup-builder skill's references/theme-variables.md to include the new variable.

**Layer 3 — Inline C# Workarounds:** For every item flagged in the translation map's bug zone flags and property gaps. Each workaround gets a code comment:
```csharp
// USS bug: height ignored inside ScrollView children (Unity 6)
// See: Theme.uss variable --spacing-3xl = 30px
element.style.height = 30;
```

**Layer 4 — Interactive Behavior:** Hover/active states use USS pseudo-classes (`:hover`, `:active`) — these work directly in USS. Only use C# `PointerEnterEvent`/`PointerLeaveEvent` for hover behavior that changes non-style properties (e.g., showing a tooltip, triggering animations via DOTween). Click handlers, drag registration, context menu wiring remain in C#.

## Step 5: Self-Verify

Verification is layer-appropriate — not every layer needs a screenshot:

**Layer 1 (Structure):** Code-level audit only. Verify element count, names, and nesting depth match the translation map. No screenshot needed — unstyled elements are meaningless visually.

**Layer 2 (USS Styling):** Screenshot comparison is now useful. Take a screenshot if UI is reachable. Compare layout, colors, and spacing against the mockup. Note that inline workarounds are pending — some visual gaps are expected.

**Layer 3 (Inline Workarounds):** Screenshot should now closely match the mockup. Compare and fix any remaining drift.

**Layer 4 (Interactive):** Final verification. All visual and behavioral elements should match.

**If UI is NOT reachable** (requires specific game state like level 25, combat, NPC interaction):
Fall back to code-level structural audit — invoke the `ui-verify` skill in code-audit mode.

## Step 6: Mandatory ui-verify

After self-verification (Step 5) passes, invoke `crucible:ui-verify` as a mandatory cross-check:

1. Invoke `crucible:ui-verify` with the mockup path and translation map path (`docs/plans/<feature>-translation-map.md`)
2. ui-verify forces a fresh re-read of the mockup and produces a structured delta report
3. Loop until: all categories pass (`[PASS-visual]` or `[PASS-code]`), OR remaining deltas are documented as USS limitations (`[WARN]` with reference to `skills/shared/uss-approximation-patterns.md`)
4. Do NOT skip this step. Self-verification (Step 5) checks your own work. ui-verify checks against the source of truth with a fresh read.

## Quality Gate

This skill produces **translation maps** and **implementations**. When used standalone, invoke `crucible:quality-gate` after ui-verify (Step 6) completes. When used as a sub-skill of build, the parent orchestrator handles gating.

The gate reviews:
1. **Translation map completeness** — every mockup element mapped, translation map persisted to `docs/plans/<feature>-translation-map.md`
2. **USS approximation patterns applied** — every flagged gap has a documented workaround from `skills/shared/uss-approximation-patterns.md` that was actually implemented
3. **ui-verify delta report** — no unresolved `[FAIL]` items (only `[PASS-visual]`, `[PASS-code]`, or `[WARN]` for documented USS limitations)

## Unity 6 Rules

These are non-negotiable. Violations are bugs.

| Rule | Reason |
|------|--------|
| Every runtime UIDocument calls `FontManager.ApplyToRoot(root)` | Text invisible without it (Issue #187) |
| Never use `styleSheets.Add(Resources.Load<StyleSheet>())` | Rules silently ignored in Unity 6 (Issue #412) |
| Height/min-height inside ScrollView → inline C# only | USS values silently ignored (Unity 6 bug) |
| All colors via Theme.uss `var()` variables | Player-customizable themes requirement |
| Cross-UIDocument coords use `RuntimePanelUtils.ScreenToPanel()` | Each UIDocument has its own panel coordinate space |
| Equipment slot drop handlers guard `payload.Type` | Prevents null-ref on non-Item drags |

## Reference

For the full Theme.uss variable catalog, read the mockup-builder skill's references/theme-variables.md.
For CSS-to-USS property mapping, read `references/css-to-uss-mapping.md`.
