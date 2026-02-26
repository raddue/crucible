# Crucible Design Skills — Design Document

**Date:** 2026-02-26
**Status:** Draft
**Problem:** Agents drift from visual mockups when implementing Unity UI Toolkit code. Structure/layout and visual fidelity are the primary drift vectors. Multiple correction rounds are needed because agents lose mockup context as conversation grows.

## Overview

Three new crucible skills that form a pipeline for design-to-code UI work in Riftlock:

| Skill | Type | Purpose |
|-------|------|---------|
| `mockup-builder` | Rigid | Create HTML mockups constrained to Theme.uss variables, flexbox-only, with translation notes |
| `mock-to-unity` | Rigid | Translate mockups via structured mapping → layered implementation → self-verification |
| `ui-verify` | Flexible | Compare implementation against mockup, produce delta checklist, fix or report |

**Relationship to Anthropic originals:** These replace `frontend-design` and `playground` entirely for Riftlock. Crucible is its own thing. Anthropic skills were used as structural inspiration only.

**Key constraint:** All UI must be themeable. Colors and font styles come from Theme.uss variables exclusively. Players can create and share custom themes by providing an alternative Theme.uss.

---

## Skill 1: `mockup-builder`

**Location:** `~/.claude/skills/mockup-builder/SKILL.md`
**Triggers when:** Agent is asked to create a visual mockup, prototype, or UI reference for Riftlock.
**Skill type:** Rigid — follow exactly.

### Core Constraints

1. **All colors must use CSS custom properties** that mirror Theme.uss variables (e.g., `var(--color-bg-base)`). The skill includes the full variable mapping from `Riftlock/Assets/_Project/Resources/UI/Theme.uss`.
2. **All sizes/spacing use the Theme.uss scale** (`--spacing-xs` through `--spacing-3xl`, `--font-size-xs` through `--font-size-5xl`, `--radius-sm` through `--radius-round`, `--border-thin` through `--border-thick`).
3. **No hardcoded hex values.** If a mockup needs a new color, it defines a new `--color-*` variable in the `:root` block and documents why.
4. **Layout must use flexbox only.** No CSS grid, no absolute positioning except for overlays. USS supports flexbox but not CSS grid.
5. **Output is a single self-contained HTML file** saved to `docs/mockups/<feature>-mockup.html`.
6. **BEM class naming** matching USS selector conventions.
7. **Includes a "Translation Notes" section** at the bottom of the HTML — visible comments calling out anything that won't translate 1:1 to USS (e.g., "this hover effect needs C# PointerEnterEvent", "this text-overflow needs C# truncation").

### Generated Mockup Structure

```
1. :root block — all CSS variables mirroring Theme.uss
2. Component CSS — using only variables, flexbox layout
3. HTML structure — class names follow BEM, hierarchy maps to VisualElement tree
4. Translation Notes footer — visible section documenting USS gaps
```

### What This Skill Does NOT Do

- Does not push for "bold" or "unexpected" aesthetics — mockups match Riftlock's established dark sci-fi visual language
- Does not use CSS grid, transforms (except simple translateY for hover), or CSS features without USS equivalents
- Does not hardcode any visual values

---

## Skill 2: `mock-to-unity`

**Location:** `~/.claude/skills/mock-to-unity/SKILL.md`
**Triggers when:** Agent is asked to implement UI from a mockup, or any task involving turning a visual reference into Unity UI Toolkit code.
**Skill type:** Rigid — follow exactly, no shortcuts.

### Process (Mandatory Order)

#### Step 1: Read the Mockup Completely

Agent must read the full HTML mockup file before writing any code. No skimming, no "I'll figure it out as I go." If the mockup is too large for one read, read it in sections and summarize each.

#### Step 2: Produce a Translation Map

Before any implementation, agent writes a structured mapping:

- **Selectors:** Every CSS class → USS selector name
- **Properties:** Every CSS property → USS equivalent (or flag as "needs inline C#" with reason)
- **Variables:** Every CSS variable → Theme.uss variable (confirm it exists, or flag as "needs adding to Theme.uss")
- **Hierarchy:** HTML nesting → VisualElement tree with named elements
- **Bug zone flags:**
  - Anything inside a ScrollView that uses height/min-height → flag for inline C#
  - Any new runtime UIDocument → flag for FontManager.ApplyToRoot()
  - Any stylesheet loading → flag against Resources.Load pattern

#### Step 3: User Checkpoint

Agent presents the translation map and waits for approval before writing code. This catches structural drift before it becomes code.

#### Step 4: Implement in Layers

- **Layer 1: Structure** — VisualElement hierarchy only, no styling. Verify element tree matches mockup HTML nesting.
- **Layer 2: USS styling** — Using Theme.uss variables. Write USS selectors matching the translation map.
- **Layer 3: Inline C# workarounds** — For USS bug zones flagged in Step 2. Each workaround gets a code comment explaining why USS doesn't work here.
- **Layer 4: Interactive behavior** — Hover states via C# callbacks, drag handlers, click events.

#### Step 5: Self-Verify After Each Layer

Agent takes a screenshot via `mcp__UnityMCP__manage_scene(action="screenshot", include_image=true)` and compares against the mockup. If drift is detected, fix before moving to next layer. If screenshot is not possible (UI requires specific game state), fall back to code-level structural audit (see `ui-verify` skill).

### Riftlock-Specific Rules (Baked In)

- Every runtime UIDocument gets `FontManager.ApplyToRoot(root)`
- No `styleSheets.Add(Resources.Load<StyleSheet>())` — embed in existing USS or use inline C#
- Height/min-height inside ScrollView children → inline C# only
- All colors via Theme.uss variables, never hardcoded
- Cross-UIDocument operations use `RuntimePanelUtils.ScreenToPanel()`
- Equipment slot drop handlers must guard against non-Item payload types

---

## Skill 3: `ui-verify`

**Location:** `~/.claude/skills/ui-verify/SKILL.md`
**Triggers when:** After implementing UI from a mockup, when user shares a screenshot showing drift, or on-demand for any "does this match the mock?" check.
**Skill type:** Flexible — comparison checklist adapts to scope, but the read → compare → delta structure is mandatory.

### Process

#### Step 1: Capture Current State

Take a screenshot via MCP (`manage_scene action="screenshot" include_image=true`). If verifying a specific panel, frame the scene view on it first.

**If screenshot is not possible** (UI requires unreachable game state like level 25 prodigy selection), skip directly to code-level structural audit (Step 2b).

#### Step 2a: Visual Comparison (when screenshot available)

Re-read the source mockup HTML file (actually re-read it, don't rely on memory). Compare screenshot against mockup on the structured checklist.

#### Step 2b: Code-Level Structural Audit (fallback)

Read the actual USS/C# source and compare property values against the mockup's CSS values:
- Read USS file, compare every property value against mockup CSS
- Read C# controller, verify VisualElement hierarchy matches HTML nesting
- Confirm every `--color-*` and `--spacing-*` variable reference matches mockup usage
- Verify USS bug workarounds are in place (inline height in ScrollView, FontManager call)
- Check for hardcoded values that should be Theme.uss variables

#### Step 3: Structured Comparison Checklist

| Category | What to Compare |
|----------|----------------|
| Layout | Flex directions, element order, nesting depth |
| Spacing | Padding, margins, gaps vs. mockup's `--spacing-*` values |
| Colors | Background, text, border colors vs. Theme.uss variables |
| Typography | Font sizes, weights vs. `--font-size-*` scale |
| Borders & radius | Widths, colors, corner radius |
| Interactive states | Hover, active, disabled — are they wired? |
| Theming compliance | All values using Theme.uss variables? Any hardcoded values? |

#### Step 4: Produce Delta Report

```
✅ Layout: hierarchy matches (3 containers, correct flex directions)
❌ Spacing: top-bar padding is 8px, mockup shows --spacing-xl (16px)
❌ Color: search-box border using hardcoded #2a2a3a, should be var(--color-border)
✅ Typography: font sizes match scale
⚠️ Workaround needed: detail-panel height inside ScrollView — needs inline C#
```

#### Step 5: Fix or Report

If the agent is the implementer, fix each ❌ item and re-verify. If the agent is a reviewer, report the delta to the implementing agent or user.

---

## Crucible Integration

`using-crucible` routes design work through these skills:

1. Agent asked to create UI mockup → **`mockup-builder`**
2. Agent asked to implement UI from mockup → **`mock-to-unity`**
3. Agent asked to verify UI matches mockup → **`ui-verify`**
4. Agent finishing UI implementation → **`ui-verify`** automatically (self-verification)

Process skills (brainstorming, debugging) still apply first per crucible priority rules. These are implementation skills that guide execution.

---

## Theme.uss Variable Categories (Reference)

The mockup-builder skill will include the full current variable list from Theme.uss:

- **Core UI Chrome:** `--color-bg-base`, `--color-bg-raised`, `--color-bg-surface`, `--color-bg-elevated`, `--color-bg-input`, `--color-border`, `--color-border-strong`, `--color-overlay`
- **Text:** `--color-text`, `--color-text-bright`, `--color-text-muted`, `--color-text-dim`, `--color-text-disabled`
- **Brand Accent:** `--color-accent`, `--color-accent-muted`, `--color-accent-bg`, `--color-accent-border`
- **Semantic States:** `--color-danger`, `--color-success`, `--color-warning`, `--color-info`, `--color-button`, `--color-button-hover`
- **Resource Bars:** health, energy, xp, shield (with text/border/bg variants)
- **Item Rarity:** common through legendary
- **Nanocore Sockets:** red, blue, green, purple, orange, teal, prismatic
- **Typography Scale:** `--font-size-xs` (9px) through `--font-size-5xl` (28px)
- **Spacing Scale:** `--spacing-xs` (2px) through `--spacing-3xl` (30px)
- **Border Radius:** `--radius-sm` (2px) through `--radius-round` (20px)
- **Border Width:** `--border-thin` (1px) through `--border-thick` (3px)
- **Domain-specific:** Combat log, talent tree, interactive states, edit mode

New variables should follow the naming convention: `--color-<domain>-<purpose>` or `--<category>-<scale>`.
