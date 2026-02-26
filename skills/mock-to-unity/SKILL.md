---
name: mock-to-unity
description: Use when implementing Unity UI Toolkit code from a mockup, HTML reference, screenshot, or visual spec. Triggers on "implement this mockup", "translate to USS", "build this UI", "match the mock", "UI looks wrong", "fix the layout", "spacing is off", "doesn't look like the design", or any task turning a visual reference into Unity UI Toolkit USS/C# code.
---

# Mock to Unity

Translate visual mockups into Unity UI Toolkit code (USS/C#) with structural fidelity. Prevents drift through a mandatory translation map, layered implementation, and self-verification.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Related skills:** When writing C# controllers (Layers 1, 3, 4), `riftlock-standards` applies to all C# code. After implementation, `test-driven-development` applies for controller tests.

## Architecture Decision: Programmatic C# (Not UXML)

Build VisualElement trees programmatically in C# — do not use UXML. The project has moved to programmatic construction because `styleSheets.Add(Resources.Load<StyleSheet>())` silently fails in Unity 6 (Issue #412). UXML-based workflows depend on stylesheet loading that is broken.

**Exception:** If the target panel already uses UXML (check the existing controller), follow its pattern rather than mixing approaches.

## File Placement

| Output | Location |
|--------|----------|
| USS files | `Riftlock/Assets/_Project/Resources/UI/` |
| C# controllers | `Riftlock/Assets/_Project/Scripts/Systems/UI/<subsystem>/` |
| Theme.uss variable additions | `Riftlock/Assets/_Project/Resources/UI/Theme.uss` |

If unsure which subsystem directory, grep for similar controllers or check the cartographer module maps.

## Step 1: Read the Mockup

Read the full source mockup before writing any code.

- **HTML file:** Read the complete file. If too large, read in sections and summarize each section's structure, variables, and layout.
- **Screenshot/image:** Describe every visible element, its approximate position, colors, text, spacing, and hierarchy. Assign BEM class names based on the visual hierarchy. Estimate colors by matching to the nearest Theme.uss variable. Estimate spacing by matching to the nearest `--spacing-*` value. Document estimation uncertainty in the translation map.
- **Text/ASCII:** Parse the described structure into a mental model of containers and elements.

Do not skip this step. Do not skim. The mockup is the source of truth for the entire implementation.

## Step 2: Produce a Translation Map

Write a structured mapping document before any implementation code. This is the checkpoint that catches drift early.

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
Confirm every CSS variable exists in Theme.uss. Read `~/.claude/skills/mockup-builder/references/theme-variables.md` for the catalog:
```
var(--color-bg-base)       → exists in Theme.uss     [ok]
var(--color-vendor-price)  → NOT in Theme.uss         [needs adding]
```

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

## Step 3: User Checkpoint

Present the translation map. Wait for approval before writing code. Explicitly state:
- Number of elements in the hierarchy
- Number of USS properties that translate directly
- Number of items flagged for inline C# workarounds
- Any new Theme.uss variables needed

If operating autonomously (e.g., as a subagent in a build pipeline), skip the wait but still produce the map in output for traceability.

## Step 4: Implement in Layers

Build in this order. Do not skip layers or combine them.

**Layer 1 — Structure:** VisualElement hierarchy only. No styling. Create all containers and elements matching the translation map hierarchy. Verify element names and nesting depth match.

**Layer 2 — USS Styling:** Write USS selectors using Theme.uss variables. Reference the translation map for every property. Use `var()` references exclusively — no hardcoded values. For any variable flagged as "needs adding to Theme.uss" in the translation map, add it to `Riftlock/Assets/_Project/Resources/UI/Theme.uss` in the appropriate section with a comment. Also update `~/.claude/skills/mockup-builder/references/theme-variables.md` to include the new variable.

**Layer 3 — Inline C# Workarounds:** For every item flagged in the translation map's bug zone flags and property gaps. Each workaround gets a code comment:
```csharp
// USS bug: height ignored inside ScrollView children (Unity 6)
// See: Theme.uss variable --spacing-3xl = 30px
element.style.height = 30;
```

**Layer 4 — Interactive Behavior:** Hover states via `PointerEnterEvent`/`PointerLeaveEvent`, click handlers, drag registration, context menu wiring.

## Step 5: Self-Verify

Verification is layer-appropriate — not every layer needs a screenshot:

**Layer 1 (Structure):** Code-level audit only. Verify element count, names, and nesting depth match the translation map. No screenshot needed — unstyled elements are meaningless visually.

**Layer 2 (USS Styling):** Screenshot comparison is now useful. Take a screenshot if UI is reachable. Compare layout, colors, and spacing against the mockup. Note that inline workarounds are pending — some visual gaps are expected.

**Layer 3 (Inline Workarounds):** Screenshot should now closely match the mockup. Compare and fix any remaining drift.

**Layer 4 (Interactive):** Final verification. All visual and behavioral elements should match.

**If UI is NOT reachable** (requires specific game state like level 25, combat, NPC interaction):
Fall back to code-level structural audit — invoke the `ui-verify` skill in code-audit mode.

## Riftlock-Specific Rules

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

For the full Theme.uss variable catalog, read `~/.claude/skills/mockup-builder/references/theme-variables.md`.
For CSS-to-USS property mapping, read `references/css-to-uss-mapping.md`.
