---
name: mockup-builder
description: Use when creating a visual mockup, UI prototype, or HTML reference for your project's UI. Triggers on "mockup", "prototype", "UI reference", "design a panel", "mock up", or any task producing a visual HTML file for later Unity UI Toolkit implementation.
---

# Mockup Builder

Create HTML mockups for your project's UI that are constrained to Theme.uss variables and designed for direct translation to Unity UI Toolkit.

**Skill type:** Rigid — follow exactly.

## Before Starting

1. Read `references/theme-variables.md` for the full Theme.uss variable catalog
2. Read existing mockups in `docs/mockups/` for visual language reference — but note that mockups created before this skill may use hardcoded hex values and lack CSS variables. Use them only to understand the project's visual language (colors, proportions, layout patterns), NOT as CSS architecture exemplars.
3. If the feature has a design doc in `docs/plans/`, read it for requirements

## Constraints

These are non-negotiable. Every mockup must satisfy all of them.

**Theming:**
- All colors use CSS custom properties mirroring Theme.uss (e.g., `var(--color-bg-base)`)
- All sizes/spacing use Theme.uss scale variables (`--spacing-*`, `--font-size-*`, `--radius-*`, `--border-*`)
- No hardcoded hex/rgb values anywhere in CSS. New colors get a new `--color-*` variable in `:root` with a comment explaining why
- This ensures players can create and share custom themes

**Layout:**
- Flexbox only. No CSS grid — USS does not support it
- No absolute positioning except for overlay elements (modals, tooltips, context menus)
- No CSS transforms except simple `translateY` for hover lift effects (these need C# in Unity)

**Naming:**
- BEM class naming that maps to USS selectors (e.g., `.talent-node`, `.talent-node__icon`, `.talent-node--maxed`)
- HTML hierarchy must map 1:1 to the intended VisualElement tree

**Output:**
- Single self-contained HTML file — no external dependencies
- Save to `docs/mockups/<feature>-mockup.html`

## Mockup Structure

Every mockup follows this structure:

```
1. :root block
   - All CSS variables from Theme.uss used by this mockup
   - Any new variables with explanatory comments

2. Component CSS
   - Uses only var() references, never raw values
   - Flexbox layout only
   - BEM class names

3. HTML structure
   - Class names match USS selector intent
   - Hierarchy maps to VisualElement tree
   - Data-attributes for state variants (data-state="maxed", etc.)

4. Translation Notes (visible footer section)
   - CSS features that need C# equivalents (hover → PointerEnterEvent)
   - Properties known to fail in USS (height in ScrollView)
   - Any new Theme.uss variables this mockup introduces
```

## Translation Notes Section

At the bottom of every mockup, include a visible `<section class="translation-notes">` covering:

- **Hover/active states:** CSS `:hover` and `:active` → need C# `PointerEnterEvent`/`PointerLeaveEvent` callbacks
- **Text overflow:** CSS `text-overflow: ellipsis` → may need C# truncation logic
- **Transitions:** CSS `transition` → need DOTween or manual interpolation
- **ScrollView children:** Any element inside a scrollable area using height/min-height → must be inline C# (Unity 6 USS bug)
- **New variables:** List any `--color-*` or `--spacing-*` variables not yet in Theme.uss
- **Absolute positioning:** Document which overlay elements use it and why

## What This Skill Does NOT Do

- Push for "bold", "unexpected", or "distinctive" aesthetics — match the project's established visual language
- Use CSS features without USS equivalents (grid, multi-column, custom properties in calc(), etc.)
- Create multi-file mockups — always single HTML file
- Generate Unity code — that is `mock-to-unity`'s job

## After Creating the Mockup

1. If a browser is available, open the mockup to verify rendering. Otherwise, review the HTML/CSS source for structural correctness and consistency with the project's visual language.
2. Review the Translation Notes section for completeness
3. Commit the mockup file to git

## Quality Gate

This skill produces **mockups**. When used standalone, invoke `crucible:quality-gate` after the mockup is created and committed. When used as a sub-skill of build, the parent orchestrator handles gating.
