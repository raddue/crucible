---
ticket: "#178"
epic: "#178"
title: "Simplify-ignore hook for protected code regions"
date: "2026-04-16"
source: "spec"
---

# Simplify-ignore hook — Implementation Plan

Scope per design doc DEC-1: **Option B (skill-level marker respect)**. No PreToolUse/PostToolUse
hook, no file-rewriting infrastructure. All logic lives inside the `simplify` skill.

Total effort: ~2 days. Tasks T1 / T2 / T5 are parallelizable. T3 depends on T1+T2. T4 depends on T3.

## Tasks

### T1 — Pre-scan: detect markers before dispatching simplifier (Tier 2)

**Files:** `skills/simplify/SKILL.md` (orchestrator prompt), plus a helper block in the same skill
directory if a script is preferred over inline bash.

**Behavior:** for each file in the simplify target set:

1. Grep for any of the four marker-start variants (`// simplify-ignore-start`,
   `/* simplify-ignore-start */`, `<!-- simplify-ignore-start -->`, `# simplify-ignore-start`).
2. Pair each start with the nearest matching end variant in the same file. Record as
   `{file, start_line, end_line}`.
3. Validate: emit warning for unclosed / orphan / nested markers (DEC-3 case 1).
4. Persist the list as `protected_ranges` in the dispatch manifest the simplifier subagent receives.

**Done when:** a fixture file with `// simplify-ignore-start` / `// simplify-ignore-end` around
lines 10–20 produces `{file: fixture.js, start_line: 10, end_line: 20}` in the pre-scan output.

### T2 — Subagent prompt: declare protected ranges (Tier 2)

**Files:** `skills/simplify/SKILL.md` — subagent dispatch template.

Add a section to the simplifier subagent prompt:

> **Protected ranges.** The following ranges MUST NOT appear in any diff you produce. They are
> marked by authors as intentionally complex and are out of scope for simplification:
> `{{protected_ranges}}`

**Done when:** subagent prompt contains the `{{protected_ranges}}` placeholder and rendering
substitutes the T1 output.

### T3 — Diff validation gate (Tier 2, depends on T1+T2)

**Files:** `skills/simplify/SKILL.md` — post-subagent validation step.

**Behavior:** before applying any subagent-produced diff:

1. Parse each hunk header (`@@ -start,count +start,count @@`) to get target line ranges.
2. For each hunk, check whether its `-` range intersects any protected range for that file.
3. If yes: reject the diff, re-dispatch the subagent once with a reminder. If the retry still
   violates, abort with a diagnostic listing the offending hunk + protected range.

**Done when:** feeding a crafted diff that deletes line 15 of the T1 fixture (inside
protected 10–20) produces a rejection, and feeding a diff that only touches line 25 is applied
normally.

### T4 — Tests (Tier 2, depends on T3)

**Files:** `skills/simplify/tests/fixtures/protected-region.js`, plus a test harness under
`skills/simplify/tests/`.

Cases:

- **INV-3 integration.** Fixture file with a `// simplify-ignore-start/end` block containing
  deliberately verbose code. Run the simplify skill against the file; assert byte-equal content
  inside the marked range after the pass.
- **INV-4 validation.** Feed a synthetic diff hunk targeting a protected line to the T3
  validator; assert it rejects.
- **Marker syntax coverage.** One fixture per language family, named explicitly:
  `protected-region.js`, `protected-region.css`, `protected-region.html`, `protected-region.sh`.
  Each fixture contains one start/end pair around lines 5–10 with deliberately verbose content;
  test asserts pre-scan returns `{start_line: 5, end_line: 10}` for each.
- **Malformed markers.** Fixture with unclosed start → assert warning emitted and pre-scan falls
  back to marker-to-EOF protection.

### T5 — Docs: "Protecting Complex Code" section (Tier 2)

**Files:** `skills/simplify/SKILL.md` — user-facing docs block near the top.

Contents:

- What markers do and when to use them.
- The four syntax variants.
- Note that protection is `simplify`-scoped only (not `/build`, not manual edits) — matches the
  Non-goals in the design doc.
- A one-line note that the feature is opt-in and has zero cost when no markers are present.

## Sequencing

```
T1 ──┐
T2 ──┼── T3 ── T4
T5 ──┘
```

T1 / T2 / T5 can be done in one parallel batch; T3 gates on both T1 and T2; T4 gates on T3.

## Risk notes

- **Heuristic marker-in-string detection (DEC-3 case 1)** is a false-positive risk. Mitigation:
  if unsure, treat as a real marker and let the author adjust. Over-protection is safe;
  under-protection is the failure we're avoiding.
- **Diff hunk → line range mapping** is standard but easy to get off-by-one. Mitigation: use a
  well-tested unified-diff parser, not hand-rolled regex.
- **Rename-through-simplify.** If the simplifier renames a file, the protected ranges need to
  carry over. For MVP, rename + simplify-ignore-markers is out of scope — document as a known
  limitation.

## Rollback

The entire feature is additive inside `simplify/SKILL.md`. Reverting is a single-file revert; no
migration, no data touched, no hook registration to undo.
