---
name: ui-verify
description: Use when verifying Unity UI matches a mockup, after implementing UI from a visual reference, when a user shares a screenshot showing UI drift, when checking theming compliance, or when UI looks wrong. Triggers on "verify", "compare to mock", "does this match", "check the UI", "screenshot shows wrong", "UI looks wrong", "fix the layout", "spacing is off", "colors are off", "doesn't look like the design", "visual bug", or completing any UI implementation task.
---

# UI Verify

Compare implemented Unity UI against its source mockup. Produces a structured delta report identifying exactly what drifted and what needs fixing.

**Skill type:** Flexible — checklist adapts to scope, but the read-compare-delta structure is mandatory.

## Step 0: Locate the Source Mockup

Before verification, identify the source of truth:

1. If the mockup path was provided by the user or in a task description, use that.
2. Otherwise, check `docs/mockups/` for a file matching the feature name (e.g., `talent-ui-mockup.html` for the talent panel).
3. If no mockup exists for this feature, report that verification requires a source mockup and fall back to a theming compliance audit only (Step 3, Theming Compliance and Bug Workarounds categories).

## Step 1: Capture Current State

**If UI is reachable** in current game state:
```
mcp__UnityMCP__manage_scene(action="screenshot", include_image=true)
```
Frame the scene view on the target panel first if needed.

**If UI is NOT reachable** (requires level 25, combat state, NPC interaction, etc.):
Skip to Step 2b (code-level audit). Do not ask the user for a screenshot — that happens naturally during playtesting.

## Step 2a: Visual Comparison

Re-read the source mockup file. Actually re-read it — do not rely on prior context or memory. The mockup may have been updated, and context drift is the problem this skill exists to solve.

Compare the screenshot against the mockup using the checklist in Step 3.

## Step 2b: Code-Level Structural Audit

When screenshots are unavailable, read the implementation source files and compare directly against the mockup CSS/HTML:

**USS file audit:**
- Open the USS file and the mockup CSS side by side (read both)
- Compare every property value — does each USS selector match its CSS counterpart?
- Are all values using `var()` Theme.uss references? Flag any hardcoded values.

**C# controller audit:**
- Read the controller that builds the VisualElement tree
- Compare element hierarchy against mockup HTML nesting
- Verify element names match mockup class names
- Check for inline style workarounds where the translation map flagged them

**Bug workaround audit:**
- Any ScrollView children using height/min-height → must be inline C#, not USS
- Runtime UIDocuments → must call `FontManager.ApplyToRoot(root)`
- No `styleSheets.Add(Resources.Load<StyleSheet>())` patterns

## Step 3: Comparison Checklist

Evaluate each category. Mark each as pass, fail, or warning.

| Category | What to Compare |
|----------|----------------|
| **Layout** | Flex directions, element order, nesting depth, container structure |
| **Spacing** | Padding, margins, gaps — compare against mockup's `--spacing-*` values |
| **Colors** | Background, text, border — compare against Theme.uss variables used in mockup |
| **Typography** | Font sizes, weights, letter-spacing — compare against `--font-size-*` scale |
| **Borders & Radius** | Border widths, colors, corner radius values |
| **Interactive States** | Hover, active, disabled, selected — are callbacks wired? |
| **Theming Compliance** | All values via Theme.uss variables? Any hardcoded colors or sizes? |
| **Bug Workarounds** | USS bug zones handled correctly? FontManager called? |
| **Cross-Panel Consistency** | Effect techniques match the USS Effect Decision Registry (`skills/shared/uss-effect-decisions.md`)? Flag any deviations. |

## Step 4: Delta Report

Produce a structured report using this format:

**Confidence tags:**
- `[PASS-visual]` — verified via screenshot comparison (high confidence)
- `[PASS-code]` — verified via code-level structural audit only (lower confidence — means "the code looks right" not "the output looks right")
- `[FAIL]` — mismatch found
- `[WARN]` — USS limitation, documented in translation map or uss-approximation-patterns.md

Use `[PASS-visual]` when a screenshot was compared. Use `[PASS-code]` when only code-level audit was performed (Step 2b). This distinction lets downstream consumers know which findings are high-confidence visual checks and which are structural inferences.

```
## UI Verification: [Component Name]
Source: docs/mockups/[feature]-mockup.html
Method: [screenshot | code-audit]

### Results
[PASS-visual] Layout: hierarchy matches (N containers, correct flex directions)
[FAIL] Spacing: top-bar padding is 8px, mockup uses --spacing-xl (16px)
[FAIL] Color: search-box border hardcoded #2a2a3a, should be var(--color-border)
[PASS-visual] Typography: font sizes match scale
[PASS-code] Borders: widths and radius correct (code-level check only)
[WARN] Interactive: hover states not yet wired (Layer 4 pending)
[FAIL] Theming: 2 hardcoded color values found
[PASS-visual] Bug workarounds: ScrollView height handled via inline C#

### Action Items
1. Fix top-bar padding: change 8px → var(--spacing-xl)
2. Fix search-box border: replace #2a2a3a → var(--color-border)
3. Replace hardcoded colors at [file:line] and [file:line]
```

## Step 5: Fix or Report

**If acting as the implementer:** Fix each failed item. After fixes, re-run verification (loop back to Step 1). Continue until all items pass or are documented as known limitations.

**If acting as a reviewer:** Report the delta to the implementing agent or user. Do not fix — the implementer owns the code.

## Quality Gate

This skill produces **delta reports**. When used standalone, invoke `crucible:quality-gate` after the delta report is produced if significant failures remain unresolved. When used as a sub-skill of mock-to-unity (Step 6), the parent skill handles iteration — quality-gate is not needed.

## Scope Adaptation

This skill adapts to verification scope:

- **Full panel:** Run all checklist categories
- **Single component:** Focus on that component's categories, skip layout if container structure isn't changing
- **Theming audit only:** Focus on Theming Compliance and Colors categories
- **Post-correction check:** Focus on previously-failed categories from the last delta report
- **No mockup available:** Theming Compliance and Bug Workarounds categories only
