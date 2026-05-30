---
name: mockup-builder
description: Use when creating a visual mockup, UI prototype, or HTML reference for your project's UI. Triggers on "mockup", "prototype", "UI reference", "design a panel", "mock up", or any task producing a visual HTML file for later Unity UI Toolkit implementation.
---

# Mockup Builder

Create HTML mockups for your project's UI that are constrained to Theme.uss variables and designed for direct translation to Unity UI Toolkit.

**Skill type:** Rigid — follow exactly.

## Before Starting

1. Read `references/theme-variables.md` for the Theme.uss variable catalog. **Freshness check:** verify the `Last synced` date is current. If the project's Theme.uss has been modified since that date, regenerate theme-variables.md from Theme.uss's `:root` block only (see the Freshness Check instructions in theme-variables.md).
2. Read `skills/shared/uss-approximation-patterns.md` to understand what CSS effects are achievable in USS and how to approximate those that aren't.
3. Read `skills/mock-to-unity/references/css-to-uss-mapping.md`, specifically the "CSS Properties Not Available in USS" section, for the hard-block list of features that MUST NOT be used in mockups.
4. Read existing mockups in `docs/mockups/` for visual language reference — but note that mockups created before this skill may use hardcoded hex values and lack CSS variables. Use them only to understand the project's visual language (colors, proportions, layout patterns), NOT as CSS architecture exemplars.

## Constraints

These are non-negotiable. Every mockup must satisfy all of them.

**Theming:**
- All colors use CSS custom properties mirroring Theme.uss (e.g., `var(--color-bg-base)`)
- All sizes/spacing use Theme.uss scale variables (`--spacing-*`, `--font-size-*`, `--radius-*`, `--border-*`)
- No hardcoded hex/rgb values anywhere in CSS. New colors get a new `--color-*` variable in `:root` with a comment explaining why
- This ensures players can create and share custom themes
- The `:root` block is a LOCAL COPY of Theme.uss values for browser rendering. Values MUST match `references/theme-variables.md` exactly. Do not redefine existing variables with different values. If you need a value that doesn't exist, add a new variable with a descriptive name and document it in the Translation Notes.

**Layout:**
- Flexbox only. No CSS grid — USS does not support it
- No absolute positioning except for overlay elements (modals, tooltips, context menus)
- No CSS transforms except simple `translateY` for hover lift effects (these need C# in Unity)

**USS Feasibility:**
- **Hard-blocked:** Do not use any CSS feature listed in `skills/mock-to-unity/references/css-to-uss-mapping.md` under "CSS Properties Not Available in USS." These have no USS equivalent and no viable approximation. This includes but is not limited to: text-shadow, @media queries, display: grid/inline, calc(), clamp(), viewport units (vw/vh/vmin/vmax).
- **Allowed with mandatory Translation Notes:** The following CSS features CAN be used to communicate design intent but MUST have a corresponding entry in the Translation Notes section documenting the specific USS approximation pattern from `skills/shared/uss-approximation-patterns.md`:
  - box-shadow, linear-gradient, repeating-linear-gradient, `::before`/`::after`, text-transform, transition, cursor (non-standard values), border-style: dashed, letter-spacing in em units, backdrop-filter, animation/@keyframes
- A missing translation note for an allowed-with-notes feature is a quality-gate failure.

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

- **Hover/active states:** CSS `:hover` and `:active` → USS supports these as pseudo-classes. Use USS selectors directly (e.g., `.button:hover { background-color: ... }`). Do NOT use C# PointerEnterEvent/PointerLeaveEvent for hover styling — that pattern is outdated.
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

The quality gate reviewer MUST check:
1. **USS Feasibility** — no hard-blocked CSS features used (reference css-to-uss-mapping.md "CSS Properties Not Available in USS")
2. **Translation Notes** — every allowed-with-notes feature has a documented USS approximation pattern from `skills/shared/uss-approximation-patterns.md`
3. **:root Value Match** — all `:root` variable values match `references/theme-variables.md` (after freshness check)
4. **Theming Compliance** — all values use `var()` references, no hardcoded hex/rgb values
5. **Layout Compliance** — flexbox only, BEM naming, HTML hierarchy maps 1:1 to VisualElement tree

Items 1-3 are **blocking** — they guarantee downstream translation failure if not fixed before proceeding to mock-to-unity.
