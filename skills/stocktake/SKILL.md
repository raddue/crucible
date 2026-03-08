---
name: stocktake
description: Audits all crucible skills for overlap, staleness, broken references, and quality. Quick scan or full evaluation modes.
origin: crucible
---

# Skill Stocktake

Audits all crucible skills for overlap, staleness, broken references, and quality.

**Announce at start:** "I'm using the stocktake skill to audit skill health."

## When to Activate

- User invokes `/stocktake` or asks to audit skills
- Forge feed-forward nudges when results are 30+ days stale
- After adding, removing, or significantly modifying multiple skills

## Modes

| Mode | Trigger | Duration |
|------|---------|----------|
| Quick scan | `results.json` exists (default) | ~5 min |
| Full stocktake | `results.json` absent, or `/stocktake full` | ~20 min |

**Results cache:** `skills/stocktake/results.json`

## Quick Scan Flow

1. Read `skills/stocktake/results.json`
2. Identify skills that have changed since `evaluated_at` timestamp (compare file mtimes)
3. If no changes: report "No changes since last run." and stop
4. Re-evaluate only changed skills using the same evaluation criteria
5. Carry forward unchanged skills from previous results
6. Output only the diff
7. Save updated results to `skills/stocktake/results.json`

## Full Stocktake Flow

### Phase 1 — Inventory

Enumerate all skill directories under `skills/`. For each:
- Read SKILL.md frontmatter (name, description, origin)
- Collect file mtime
- Note file count and total line count

Present inventory table:

| Skill | Files | Lines | Last Modified | Description |
|-------|-------|-------|---------------|-------------|

### Phase 2 — Quality Evaluation

Dispatch an Opus Explore agent with all skill contents and the evaluation checklist.

Each skill is evaluated against:

- [ ] Content overlap with other skills checked
- [ ] Scope fit — name, trigger, and content aligned
- [ ] Actionability — concrete steps vs vague advice
- [ ] Cross-references — do `crucible:` links resolve to existing skills?

Each skill gets a verdict:

| Verdict | Meaning |
|---------|---------|
| Keep | Useful and current |
| Improve | Worth keeping, specific improvements needed |
| Retire | Low quality, stale, or cost-asymmetric |
| Merge into [X] | Substantial overlap with another skill; name the merge target |

**Reason quality requirements** — the `reason` field must be self-contained and decision-enabling:
- For **Retire**: state (1) what specific defect was found, (2) what covers the same need instead
- For **Merge**: name the target and describe what content to integrate
- For **Improve**: describe the specific change needed (what section, what action)
- For **Keep**: restate the core evidence for the verdict

### Phase 3 — Summary Table

| Skill | Verdict | Reason |
|-------|---------|--------|

### Phase 4 — Consolidation

1. **Retire / Merge**: present detailed justification per skill before confirming with user
2. **Improve**: present specific improvement suggestions with rationale
3. Save results to `skills/stocktake/results.json`

## Results File Schema

`skills/stocktake/results.json`:

```json
{
  "evaluated_at": "2026-03-07T10:00:00Z",
  "mode": "full",
  "skills": {
    "skill-name": {
      "path": "skills/skill-name/SKILL.md",
      "verdict": "Keep",
      "reason": "Concrete, actionable, unique value for X workflow",
      "mtime": "2026-01-15T08:30:00Z"
    }
  }
}
```

## Safety

- **Never auto-deletes or auto-modifies skills**
- Always presents findings and waits for explicit user confirmation
- Archive/delete operations always require user approval

## Integration

- **crucible:forge** — Feed-forward checks stocktake results timestamp; nudges when 30+ days stale
- Evaluation is blind: same checklist applies regardless of skill origin

## Red Flags

- Deleting or modifying skills without user confirmation
- Treating the checklist as a numeric score rather than holistic judgment
- Writing vague verdicts ("unchanged", "overlaps") instead of decision-enabling reasons
