# USS Approximation Patterns

Proven USS/C# recipes for CSS effects that Unity UI Toolkit cannot render directly.

## How to Use
- **mockup-builder**: Consult before designing. When using an approximable CSS effect, reference the specific pattern in your Translation Notes section.
- **mock-to-unity**: Apply during Layer 1-3 implementation when the translation map flags a gap. The pattern tells you exactly what USS/C# to write.

## Pattern Format
Each pattern shows:
- **CSS** — what the mockup uses
- **USS/C#** — what to implement in Unity
- **Notes** — limitations, edge cases, when to use which approach

---

## Shadows & Depth

### 1. Outer Glow (box-shadow: 0 0 Npx color)

**CSS:**
```css
box-shadow: 0 0 8px rgba(255, 45, 120, 0.3);
```

**USS:**
```css
border-width: 2px;
border-color: rgba(255, 45, 120, 0.3);
```

Use `border-color` with the glow color at the desired opacity + `border-width: 2-3px`. This creates a colored border that simulates a soft glow.

**Notes:** Works well for subtle glows. For stronger glows, increase border-width. Does not produce the soft-edge falloff of real box-shadow — the boundary is sharp. For softer appearance, layer a second element behind with slightly larger dimensions and lower opacity.

---

### 2. Inset Glow (box-shadow: inset 0 0 Npx color)

**CSS:**
```css
box-shadow: inset 0 0 8px rgba(200, 168, 74, 0.3);
```

**USS:**
```css
.element__inset-glow {
  position: absolute;
  top: 0; right: 0; bottom: 0; left: 0;
  background-color: rgba(200, 168, 74, 0.1);
}
```

Create a child VisualElement that fills the parent with `position: absolute; top: 0; right: 0; bottom: 0; left: 0;` and a semi-transparent `background-color`. Place it as the first child so it renders behind content.

**Notes:** Reduces the effect to a flat tint rather than a gradient glow. Acceptable for most game UIs.

---

### 3. Drop Shadow (box-shadow: 0 Npx Npx color)

**CSS:**
```css
box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
```

**USS:**
```css
.element__shadow {
  position: absolute;
  top: 4px; left: -2px; right: -2px; bottom: -4px;
  background-color: rgba(0, 0, 0, 0.3);
  border-radius: 8px; /* match parent */
}
```

Create a sibling VisualElement BEFORE the shadowed element with slightly larger dimensions (2-4px each side) and offset down. Give it a dark semi-transparent background-color.

**Notes:** Only use for prominent UI elements (modals, floating panels). For cards in a list, the visual weight isn't worth the extra elements.

---

### 4. Outline Hack (box-shadow: 0 0 0 1px color)

**CSS:**
```css
box-shadow: 0 0 0 1px rgba(255, 217, 102, 0.2);
```

**USS:**
```css
border-width: 1px;
border-color: rgba(255, 217, 102, 0.2);
```

Just use `border-width: 1px` + `border-color`. This is a direct equivalent.

---

### 5. Full-Cell Tint (box-shadow: inset 0 0 0 200px color)

**CSS:**
```css
box-shadow: inset 0 0 0 200px rgba(0, 255, 0, 0.1);
```

**USS:**
```css
background-color: rgba(0, 255, 0, 0.1);
```

Just use `background-color` with the same low-opacity color on the element itself.

---

## Gradients

### 6. Linear Gradient Background

**CSS:**
```css
background: linear-gradient(90deg, transparent, var(--color-accent), transparent);
```

**USS — Approach A (2-step approximation, code-only):**
```css
.gradient-container { flex-direction: row; }
.gradient__left { flex-grow: 1; background-color: rgba(255, 45, 120, 0); }
.gradient__right { flex-grow: 1; background-color: rgba(255, 45, 120, 0.6); }
```

**USS — Approach B (accurate, requires art asset):**

Use a 9-sliced sprite/texture. Create a small gradient image (e.g., 64x4px PNG) and use `background-image: resource("path/to/gradient")` with `-unity-slice-*` settings.

**Notes:** Approach A is code-only but looks stepped. Approach B requires an art asset but looks smooth. For decorative accent lines (1-2px high), Approach A is usually fine.

---

### 7. Repeating Linear Gradient

**CSS:**
```css
background: repeating-linear-gradient(45deg, ...);
```

**USS:**

Use a tiled background image via `resource()`. Create a small tileable pattern image and use `-unity-background-scale-mode: stretch-to-fill` or tile via element repetition.

**Notes:** Always requires an art asset. There is no pure USS/C# way to create repeating patterns.

---

## Pseudo-Elements

### 8. ::before / ::after Decorative Elements

**CSS:**
```css
.window::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(...);
}
```

**C# — Layer 1 (Structure):**
```csharp
var glowLine = new VisualElement();
glowLine.AddToClassList("window__glow-line");
windowElement.Add(glowLine);
```

**USS:**
```css
.window__glow-line {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background-color: var(--color-accent);
  opacity: 0.6;
}
```

Create a real child VisualElement with a descriptive class name. Position with `position: absolute`.

**Notes:** Name the element descriptively (`.window__glow-line`, `.window__bracket-tl`) rather than `.pseudo-before`. The element is a real part of the visual tree. For corner brackets, create 4 positioned elements with partial borders.

---

## Text

### 9. text-transform: uppercase

**CSS:**
```css
text-transform: uppercase;
```

**C#:**
```csharp
label.text = displayText.ToUpper();
```

Apply in the controller at the point where text is set, not in a style callback. USS has no text-transform equivalent.

---

### 10. letter-spacing in em units

**CSS:**
```css
letter-spacing: 0.2em;
```

**USS:**
```css
letter-spacing: 3px; /* 0.2em * 14px ≈ 3px */
```

Convert to px: `em_value * font_size_px`. For example, if font-size is 14px: `0.2 * 14 = 2.8px`.

**Notes:** This is an approximation — if font-size changes, the letter-spacing won't scale. Use the dominant font-size for the element.

---

## Interactive

### 11. :hover / :active States

**CSS:**
```css
.button:hover { background-color: var(--color-bg-elevated); }
```

**USS — this works directly:**
```css
.button:hover {
  background-color: var(--color-bg-elevated);
}
.button:active {
  background-color: var(--color-accent);
}
```

Use USS pseudo-classes directly. They work in Unity UI Toolkit.

**Notes:** Do NOT use C# `PointerEnterEvent`/`PointerLeaveEvent` for hover styling. USS pseudo-classes handle this natively. Only use C# events for hover behavior that changes non-style properties (e.g., showing a tooltip, starting a DOTween animation).

---

### 12. CSS transition

**CSS:**
```css
transition: background-color 0.2s ease;
```

**USS — limited but works for common cases:**
```css
transition-property: background-color;
transition-duration: 0.2s;
transition-timing-function: ease;
```

USS supports `transition-property`, `transition-duration`, `transition-timing-function` for a limited set of animatable properties (background-color, opacity, border-color, translate, rotate, scale).

**Notes:** For complex animations (multi-property, chained, with callbacks), use DOTween in C#. For simple single-property transitions on hover, USS transitions work fine.

---

## Layout

### 13. gap (flex gap)

**CSS:**
```css
gap: var(--spacing-sm);
```

**USS — margin on children:**
```css
.container > * {
  margin-left: var(--spacing-sm);
}
.container > *:first-child {
  margin-left: 0;
}
```

Apply margin to children instead.

**Notes:** For vertical gaps, use `margin-top` instead. The `:first-child` selector zeroes out the first element's margin.

---

### 14. Viewport Units (vw, vh, vmin, vmax)

**CSS:**
```css
max-width: 95vw;
max-height: 90vh;
```

**C# — Layer 3 (Workaround):**
```csharp
float maxWidth = Screen.width * 0.95f;
float maxHeight = Screen.height * 0.9f;
element.style.maxWidth = maxWidth;
element.style.maxHeight = maxHeight;
```

Use `%` relative to parent where possible. For true viewport-relative sizing, compute in C#.

**Notes:** If the element's parent is the root VisualElement (fills the screen), `%` is equivalent to viewport units.

---

### 15. position: fixed

**CSS:**
```css
position: fixed;
bottom: 10px;
left: 10px;
```

**USS — on an element inside the root container:**
```css
position: absolute;
bottom: 10px;
left: 10px;
```

Use `position: absolute` on an element whose parent is the root-level container. USS has no `position: fixed` — everything is relative to the nearest positioned ancestor.

---

## Miscellaneous

### 16. pointer-events: none

**CSS:**
```css
pointer-events: none;
```

**USS:**
```css
picking-mode: Ignore;
```

Direct equivalent with different name.

---

### 17. cursor: grab (and other non-standard cursors)

**CSS:**
```css
cursor: grab;
```

**USS:** USS `cursor` supports a limited set (arrow, text, resize-*, move-arrow). For custom cursors, use C# `CursorManager` or set cursor textures programmatically.

**Notes:** Most game UIs use custom cursor textures anyway. Document the intended cursor in Translation Notes and implement via the project's cursor system.

---

### 18. border-style: dashed

**CSS:**
```css
border-style: dashed;
```

**C# — Layer 3 (Workaround):**
```csharp
element.style.borderTopStyle = BorderStyle.Dashed;
element.style.borderRightStyle = BorderStyle.Dashed;
element.style.borderBottomStyle = BorderStyle.Dashed;
element.style.borderLeftStyle = BorderStyle.Dashed;
```

USS does not support `border-style` variants. Set via inline C#.

---

### 19. backdrop-filter: blur()

**CSS:**
```css
backdrop-filter: blur(8px);
```

**USS — no blur, just translucent:**
```css
background-color: rgba(7, 0, 15, 0.85);
```

No blur available in USS. Use a translucent `background-color` without blur as the closest approximation.

**Notes:** This is a known USS limitation. Document as `[WARN]` in ui-verify reports. The visual difference is noticeable but acceptable for most game UIs — players expect panel backgrounds to be solid-ish.
