# Theme.uss Variable Reference

Source: Your project's Theme.uss file `:root` block only (e.g., `Assets/_Project/Resources/UI/Theme.uss`)
Last synced: 2026-02-26

## Freshness Check

Before using this file, verify the `Last synced` date is current:
1. Check if the project's Theme.uss file has been modified since the `Last synced` date
2. If stale: regenerate this file by reading ONLY the `:root` block from Theme.uss
   - Ignore theme variant selectors (`.theme-outrun`, `.theme-dark`, `.theme-crt`, etc.)
   - Ignore font scale classes, accessibility overlays, and utility classes
   - Extract only the base `:root` variables and their values
3. Update the `Last synced` date to today
4. If Theme.uss cannot be located, note this and proceed with caution — values may be outdated

All mockups MUST use these variables via CSS custom properties. No hardcoded values.
For domain-specific variables not listed here, read the actual Theme.uss `:root` block directly.

## Core UI Chrome

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-bg-base` | rgb(20, 20, 31) | Deepest background, page base |
| `--color-bg-raised` | rgb(26, 26, 39) | Panel backgrounds |
| `--color-bg-surface` | rgb(38, 38, 51) | Card/container backgrounds |
| `--color-bg-elevated` | rgb(51, 51, 64) | Hover states, elevated cards |
| `--color-bg-input` | rgb(31, 31, 46) | Input fields, search boxes |
| `--color-border` | rgb(64, 64, 89) | Default borders |
| `--color-border-strong` | rgb(77, 77, 102) | Emphasized borders |
| `--color-overlay` | rgba(0, 0, 0, 0.7) | Modal overlays |
| `--color-bg-base-translucent` | rgba(20, 20, 31, 0.92) | Translucent base overlay |
| `--color-bg-raised-translucent` | rgba(26, 26, 39, 0.8) | Translucent raised overlay |
| `--color-bg-surface-translucent` | rgba(38, 38, 51, 0.6) | Translucent surface overlay |

## Text

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-text` | rgb(255, 255, 255) | Primary text |
| `--color-text-bright` | rgb(230, 230, 230) | Emphasized text |
| `--color-text-muted` | rgb(204, 204, 204) | Secondary text |
| `--color-text-dim` | rgb(153, 153, 153) | Tertiary/hint text |
| `--color-text-disabled` | rgb(128, 128, 128) | Disabled elements |
| `--color-text-secondary` | rgb(179, 179, 179) | Alternative secondary |

## Brand Accent (Gold/Amber)

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-accent` | rgb(255, 217, 102) | Primary accent |
| `--color-accent-muted` | rgb(230, 179, 77) | Subdued accent |
| `--color-accent-bg` | rgb(51, 38, 26) | Accent background tint |
| `--color-accent-border` | rgba(255, 217, 102, 0.5) | Accent borders |

## Semantic States

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-danger` | rgb(204, 51, 51) | Error, damage, destructive |
| `--color-danger-light` | rgb(255, 77, 77) | Light danger variant |
| `--color-success` | rgb(77, 204, 77) | Success, healing, positive |
| `--color-success-light` | rgb(128, 255, 128) | Light success variant |
| `--color-warning` | rgb(204, 153, 51) | Warnings, caution |
| `--color-info` | rgb(77, 179, 255) | Informational |
| `--color-button` | rgb(64, 115, 191) | Button default |
| `--color-button-hover` | rgb(89, 140, 217) | Button hover |

## Resource Bars

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-health` | rgb(242, 51, 51) | Health bar fill |
| `--color-health-text` | rgb(217, 89, 89) | Health text |
| `--color-health-border` | rgba(255, 77, 77, 0.9) | Health bar border |
| `--color-health-bg` | rgb(13, 13, 26) | Health bar background |
| `--color-energy` | rgb(51, 255, 77) | Energy bar fill |
| `--color-energy-text` | rgb(102, 217, 102) | Energy text |
| `--color-energy-border` | rgba(77, 255, 77, 0.9) | Energy bar border |
| `--color-energy-bg` | rgb(13, 20, 13) | Energy bar background |
| `--color-energy-reserved` | rgb(242, 153, 51) | Reserved energy |
| `--color-xp` | rgb(77, 179, 255) | XP bar fill |
| `--color-xp-text` | rgb(77, 166, 242) | XP text |
| `--color-xp-border` | rgba(102, 179, 255, 0.9) | XP bar border |
| `--color-shield` | rgb(51, 204, 255) | Shield bar fill |
| `--color-shield-text` | rgb(77, 179, 255) | Shield text |
| `--color-shield-border` | rgba(51, 153, 255, 0.8) | Shield bar border |

## Item Rarity

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-rarity-common` | rgb(255, 255, 255) | Common items |
| `--color-rarity-uncommon` | rgb(77, 204, 77) | Uncommon items |
| `--color-rarity-rare` | rgb(77, 128, 230) | Rare items |
| `--color-rarity-epic` | rgb(179, 77, 230) | Epic items |
| `--color-rarity-legendary` | rgb(230, 179, 51) | Legendary items |

## Nanocore Sockets

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-socket-red` | rgb(77, 26, 26) | Red socket background |
| `--color-socket-red-border` | rgb(204, 51, 51) | Red socket border |
| `--color-socket-blue` | rgb(26, 26, 77) | Blue socket background |
| `--color-socket-blue-border` | rgb(51, 51, 204) | Blue socket border |
| `--color-socket-green` | rgb(26, 77, 26) | Green socket background |
| `--color-socket-green-border` | rgb(51, 204, 51) | Green socket border |
| `--color-socket-purple` | rgb(51, 26, 77) | Purple socket background |
| `--color-socket-purple-border` | rgb(153, 51, 204) | Purple socket border |
| `--color-socket-orange` | rgb(77, 51, 26) | Orange socket background |
| `--color-socket-orange-border` | rgb(204, 128, 51) | Orange socket border |
| `--color-socket-teal` | rgb(26, 51, 77) | Teal socket background |
| `--color-socket-teal-border` | rgb(51, 153, 204) | Teal socket border |
| `--color-socket-prismatic` | rgb(51, 51, 51) | Prismatic socket background |
| `--color-socket-prismatic-border` | rgb(204, 204, 204) | Prismatic socket border |

## Nanocore Fill

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-nanocore-red` | rgb(230, 51, 51) | Red nanocore indicator dot |
| `--color-nanocore-blue` | rgb(51, 51, 230) | Blue nanocore indicator dot |
| `--color-nanocore-green` | rgb(51, 230, 51) | Green nanocore indicator dot |

## Nanocore Highlight States

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-match-valid` | rgb(51, 204, 51) | Valid socket match |
| `--color-match-hybrid` | rgb(204, 204, 51) | Hybrid/partial match |
| `--color-match-invalid` | rgb(204, 51, 51) | Invalid socket match |

## Combat Log

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-combat-damage` | rgb(255, 68, 68) | Damage messages |
| `--color-combat-healing` | rgb(68, 255, 68) | Healing messages |
| `--color-combat-miss` | rgb(136, 136, 136) | Miss messages |
| `--color-combat-death` | rgb(255, 0, 0) | Death messages |
| `--color-combat-xp` | rgb(255, 170, 0) | XP gain messages |
| `--color-combat-shield` | rgb(68, 136, 255) | Shield messages |
| `--color-combat-ability` | rgb(255, 255, 255) | Ability use messages |
| `--color-combat-status` | rgb(170, 136, 255) | Status effect messages |
| `--color-combat-item` | rgb(136, 255, 255) | Item use messages |
| `--color-combat-loot` | rgb(255, 255, 68) | Loot messages |
| `--color-combat-system` | rgb(153, 153, 153) | System messages |
| `--color-combat-opportunity` | rgb(255, 170, 0) | Opportunity attack messages |
| `--color-combat-targeting` | rgb(204, 153, 51) | Targeting messages |

## Interactive States

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-border-hover` | rgba(128, 128, 179, 1) | Hover border highlight |
| `--color-sustain-glow` | rgba(51, 204, 255, 1) | Active sustain effect glow |
| `--color-cooldown-overlay` | rgba(0, 0, 0, 0.6) | Cooldown darkening overlay |

## Talent Tree

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-talent-level` | rgb(179, 217, 255) | Level display text |
| `--color-talent-points` | rgb(179, 230, 179) | Points display text |
| `--color-talent-restricted` | rgba(128, 26, 26, 0.8) | Restricted talent background |
| `--color-talent-core-bg` | rgba(77, 128, 77, 0.8) | Core talent background |
| `--color-talent-core-text` | rgb(204, 255, 204) | Core talent text |
| `--color-talent-invested` | rgb(68, 136, 102) | Invested node border |
| `--color-talent-invested-bg` | rgb(26, 42, 31) | Invested node background |
| `--color-talent-maxed` | rgb(200, 168, 74) | Maxed node border |
| `--color-talent-maxed-bg` | rgb(42, 37, 24) | Maxed node background |
| `--color-talent-maxed-text` | rgb(212, 184, 90) | Maxed node text |
| `--color-talent-available` | rgb(85, 119, 170) | Available node border |
| `--color-talent-available-bg` | rgb(21, 26, 36) | Available node background |
| `--color-talent-pending` | rgb(204, 136, 68) | Pending allocation border |
| `--color-talent-pending-badge` | rgb(204, 102, 34) | Pending allocation badge |
| `--color-talent-search-highlight` | rgb(136, 187, 238) | Search match highlight |
| `--color-talent-scaling` | rgb(100, 210, 210) | Scaling info text |
| `--color-talent-scaling-bg` | rgba(17, 24, 37, 1) | Scaling info background |
| `--color-talent-scaling-accent` | rgba(42, 74, 106, 1) | Scaling info accent |
| `--color-talent-effect-border` | rgba(26, 42, 34, 1) | Effect description border |

## Talent Detail Panel

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-bg-detail` | rgb(15, 16, 22) | Detail panel background |
| `--color-talent-cost-bar-bg` | rgb(20, 21, 28) | Cost bar background |
| `--color-talent-cost-bar-border` | rgb(34, 35, 46) | Cost bar border |
| `--color-talent-cost-label` | rgb(102, 119, 136) | Cost label text |
| `--color-talent-cost-value` | rgb(170, 170, 187) | Cost value text |

## Bars & Badges

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-bg-bar` | rgb(22, 23, 31) | Top/bottom bar background |
| `--color-bar-border` | rgb(42, 42, 58) | Bar border |
| `--color-talent-badge-class-bg` | rgb(26, 42, 26) | Class point badge background |
| `--color-talent-badge-class-border` | rgb(42, 74, 42) | Class point badge border |
| `--color-talent-badge-class-text` | rgb(141, 200, 141) | Class point badge text |
| `--color-talent-badge-generic-bg` | rgb(26, 26, 42) | Generic point badge background |
| `--color-talent-badge-generic-border` | rgb(42, 42, 74) | Generic point badge border |
| `--color-talent-badge-generic-text` | rgb(141, 141, 200) | Generic point badge text |
| `--color-talent-badge-stat-bg` | rgb(42, 26, 42) | Stat point badge background |
| `--color-talent-badge-stat-border` | rgb(74, 42, 74) | Stat point badge border |
| `--color-talent-badge-stat-text` | rgb(200, 141, 200) | Stat point badge text |
| `--color-talent-badge-melee-bg` | rgb(42, 26, 26) | Melee type badge background |
| `--color-talent-badge-melee-text` | rgb(204, 119, 102) | Melee type badge text |
| `--color-talent-badge-melee-border` | rgb(74, 42, 42) | Melee type badge border |

## Attribute Pending States

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-attribute-pending-bg` | rgb(20, 26, 24) | Pending attribute background |
| `--color-attribute-pending-text` | rgb(102, 221, 136) | Pending attribute text |
| `--color-attribute-pending-border` | rgb(26, 42, 34) | Pending attribute border |

## Edit Mode

| Variable | Value | Usage |
|----------|-------|-------|
| `--color-edit-mode-border` | rgba(199, 150, 51, 0.8) | Edit mode border highlight |
| `--color-edit-mode-handle` | rgba(200, 150, 50, 0.3) | Edit mode drag handle |

## Typography Scale

| Variable | Value |
|----------|-------|
| `--font-size-xs` | 9px |
| `--font-size-sm` | 10px |
| `--font-size-base` | 11px |
| `--font-size-md` | 12px |
| `--font-size-lg` | 13px |
| `--font-size-xl` | 14px |
| `--font-size-2xl` | 16px |
| `--font-size-3xl` | 20px |
| `--font-size-4xl` | 24px |
| `--font-size-5xl` | 28px |

## Spacing Scale

| Variable | Value |
|----------|-------|
| `--spacing-xs` | 2px |
| `--spacing-sm` | 4px |
| `--spacing-md` | 8px |
| `--spacing-lg` | 12px |
| `--spacing-xl` | 16px |
| `--spacing-2xl` | 20px |
| `--spacing-3xl` | 30px |

## Scrollbar

| Variable | Value |
|----------|-------|
| `--scrollbar-width` | 8px |

## Border Radius

| Variable | Value |
|----------|-------|
| `--radius-sm` | 2px |
| `--radius-md` | 4px |
| `--radius-lg` | 8px |
| `--radius-xl` | 12px |
| `--radius-round` | 20px |

## Border Width

| Variable | Value |
|----------|-------|
| `--border-thin` | 1px |
| `--border-medium` | 2px |
| `--border-thick` | 3px |

## Naming Convention for New Variables

When a mockup needs a variable not in Theme.uss:
- Colors: `--color-<domain>-<purpose>` (e.g., `--color-vendor-price-text`)
- Other: `--<category>-<scale>` (e.g., `--spacing-4xl`)

Document new variables in the mockup's `:root` block with a comment explaining why they're needed.
