# CSS to USS Property Mapping

Quick reference for translating CSS properties to Unity UI Toolkit USS equivalents.

## Direct Translations (CSS → USS)

These translate 1:1 with identical or near-identical syntax:

| CSS Property | USS Property | Notes |
|-------------|-------------|-------|
| `display: flex` | `display: flex` | Only flex is supported |
| `flex-direction` | `flex-direction` | row, column, row-reverse, column-reverse |
| `flex-wrap` | `flex-wrap` | wrap, nowrap |
| `flex-grow` | `flex-grow` | Number |
| `flex-shrink` | `flex-shrink` | Number |
| `flex-basis` | `flex-basis` | Length or auto |
| `align-items` | `align-items` | flex-start, center, flex-end, stretch |
| `align-self` | `align-self` | Same as align-items |
| `justify-content` | `justify-content` | flex-start, center, flex-end, space-between, space-around |
| `width` / `height` | `width` / `height` | px, %, auto |
| `min-width` / `min-height` | `min-width` / `min-height` | height broken in ScrollView |
| `max-width` / `max-height` | `max-width` / `max-height` | px, % |
| `margin` | `margin` | px, %, auto (shorthand works) |
| `padding` | `padding` | px, % (shorthand works) |
| `position: absolute` | `position: absolute` | Relative to parent |
| `top/right/bottom/left` | `top/right/bottom/left` | For absolute positioning |
| `overflow: hidden` | `overflow: hidden` | hidden, visible, scroll |
| `opacity` | `opacity` | 0-1 |
| `background-color` | `background-color` | rgb(), rgba(), var() |
| `border-width` | `border-width` | Shorthand or per-side |
| `border-color` | `border-color` | rgb(), rgba(), var() |
| `border-radius` | `border-radius` | Shorthand or per-corner (`border-top-left-radius`, etc.) |
| `color` | `color` | Text color |
| `font-size` | `font-size` | px only |
| `-unity-font-style` | `-unity-font-style` | bold, italic, bold-and-italic, normal |
| `letter-spacing` | `letter-spacing` | px |
| `word-spacing` | `word-spacing` | px |
| `white-space` | `white-space` | normal, nowrap |
| `visibility` | `visibility` | visible, hidden |
| `cursor` | `cursor` | Limited set (arrow, text, resize-*, etc.) |
| `:focus` | `:focus` | USS pseudo-class — works directly |

## CSS Properties That Need C# Workarounds

| CSS Property | USS Status | C# Workaround |
|-------------|-----------|----------------|
| `gap` | Not supported | Apply `margin` to children instead |
| `:hover` | Not supported in USS | Register `PointerEnterEvent` / `PointerLeaveEvent` callbacks |
| `:active` | Not supported in USS | Register `PointerDownEvent` / `PointerUpEvent` callbacks |
| `transition` | `transition` exists but limited | Prefer DOTween for complex animations |
| `transform` | `translate`, `rotate`, `scale` | Separate properties, not shorthand `transform` |
| `text-overflow: ellipsis` | `-unity-text-overflow-position` | May need C# string truncation |
| `box-shadow` | Not supported | Fake with nested elements + border/background |
| `linear-gradient` | Not supported in background | Use multiple layered elements |
| `text-transform` | Not supported | Apply in C# (`ToUpper()`, etc.) |

## CSS Properties Not Available in USS

| CSS Property | Alternative |
|-------------|-------------|
| `display: grid` | Use nested flex containers |
| `display: inline` | Not available — everything is flex |
| `float` | Not available — use flex layout |
| `z-index` | Element order in hierarchy determines draw order |
| `box-shadow` | Nested elements with backgrounds |
| `text-shadow` | Not supported (overlay text elements as workaround) |
| `background-image: url()` | Use `background-image: resource()` or `-unity-background-image-tint-color` |
| `@media` queries | Not supported — use C# screen size checks |
| `animation` / `@keyframes` | DOTween or manual C# interpolation |

## USS-Only Properties (No CSS Equivalent)

| USS Property | Purpose |
|-------------|---------|
| `-unity-font` | Font asset reference |
| `-unity-font-definition` | Font asset reference (preferred in Unity 6) |
| `-unity-text-align` | Text alignment (upper-left, middle-center, etc.) |
| `-unity-background-image-tint-color` | Tint color for background images |
| `-unity-slice-*` | 9-slice border settings |
| `-unity-overflow-clip-box` | Clip box for overflow |

## Unity 6 USS Bugs (Non-Negotiable Workarounds)

### Height in ScrollView
`height` and `min-height` on elements nested inside ScrollView children are silently ignored.
**Workaround:** Set via inline C# (`element.style.height = value`).

### StyleSheet Loading
`styleSheets.Add(Resources.Load<StyleSheet>())` loads the asset but rules are silently ignored.
**Workaround:** Embed styles in an already-loaded USS file, or use inline C# styles.

### Runtime UIDocument Text
`ScriptableObject.CreateInstance<PanelSettings>()` does not load fonts.
**Workaround:** Call `FontManager.ApplyToRoot(root)` on every runtime-created UIDocument.

### Runtime UIDocument Dimensions
Runtime-created UIDocument rootVisualElement resolves to 0x0 with percentage/flex sizing.
**Workaround:** Use explicit pixel dimensions (e.g., 1920x1080).
