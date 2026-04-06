# Dispatch Mediation — Implementation Plan

**Goal:** Eliminate ~73-131K tokens of dead weight from orchestrator conversation history by replacing inline subagent prompts with disk-mediated dispatch (write expanded prompt to file, send ~50-token pointer via Agent/Task tool). Add structured execution trace via dispatch manifest.

**Architecture:** Markdown-only changes across ~93 files. No application code. All changes are to skill definitions (SKILL.md), prompt templates, and a new shared convention document.

**Design doc:** `docs/plans/2026-04-05-dispatch-mediation-design.md`

---

## Dependency Graph

```
Task 1 (Phase 0: baseline measurement) ──────────── GATE ──┐
Task 2 (Phase 1: primacy eval) ── depends on 1 ────────────┤
Task 3 (Phase 2: hybrid fallback) ── depends on 2, only    │
         if degradation detected ───────────────────────────┤
Task 4 (convention doc) ── depends on 1 pass; 2 for mode ──┤
Task 5 (Phase 2.5: pointer length validation) ── dep 4 ────┤
Task 6 (Wave 1 rollout: build + debugging) ── dep 4, 5 ────┤
Task 7 (Wave 2 rollout: quality-gate, design, spec,        │
         planning-adjacent) ── dep 6 ──────────────────────┤
Task 8 (Wave 3 rollout: security + investigation) ── dep 6 ┤
Task 9 (Wave 4 rollout: remaining skills) ── dep 6 ────────┤
Task 10 (sweep + invariant verification) ── dep 6-9 ───────┘
```

**Phase gates:**
- Task 1 is a hard prerequisite. If measured savings < 20K tokens, descope to manifest-only (skip Tasks 2-9, write a manifest-only convention doc instead).
- Task 2 determines whether full disk-mediated or hybrid mode is used. Task 3 only runs if Phase 1 shows degradation.
- Tasks 7, 8, 9 can proceed in parallel after Task 6 validates the pattern.

---

### Task 1: Phase 0 — Baseline Token Measurement

**Hard gate for entire effort. Do not proceed to any other task until this passes.**

Run one real pipeline (e.g., `/build` on issue #126) with token observation enabled via #106 instrumentation. **Fallback if #106 is not yet available:** capture a pipeline session log, extract Agent/Task tool call bodies, and estimate tokens via word-count proxy (words × 1.3). This removes the hard dependency on #106. Measure:

1. Dump context window contents at key pipeline checkpoints: after Phase 2 dispatches (planning), after Phase 3 dispatches (implementation), at pipeline end
2. Record total tokens consumed by Agent/Task tool call bodies (the `prompt` parameter contents that fossilize in orchestrator history)
3. Record how much autocompact actually reduces those bodies between phases
4. Calculate: projected savings = total tool-call-body tokens minus tokens autocompact already removes

**Decision gate:**
- **Pass (>= 20K projected savings):** Proceed to Task 2
- **Fail (< 20K projected savings):** Descope to manifest-only. Write a simplified convention doc covering only `manifest.jsonl` tracing. Skip Tasks 2-9, write Task 10 as a manifest-only sweep.

**Deliverable:** Measurement report written to `docs/plans/2026-04-05-dispatch-mediation-phase0-results.md` with raw numbers and go/no-go decision.

- **Files:** 1 (measurement report)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** #106 instrumentation (preferred) or manual word-count proxy (fallback)
- **Atomic:** true — measurement only, no skill edits
- **Restructuring-only:** false
- **Safe-partial:** true — produces a report; no side effects
- **Rollback:** N/A (no repo changes)
- **Tests to verify:** Report file exists with go/no-go decision

---

### Task 2: Phase 1 — Primacy Eval

Run the primacy eval to determine whether subagents treat disk-read context equivalently to inline context. This validates the core assumption before touching any skill files.

**Templates to test (4):**
| Template | Injected % | Dispatch type |
|---|---|---|
| `build-reviewer` | 50% | Agent tool |
| `investigator` (debugging) | 71% | Agent tool |
| `red-team` | 82% | Agent tool |
| `plan-reviewer` (build) | — | Task tool (teammate) |

**Procedure per template:**
1. Expand template with realistic fixture data from issue #126 (primary) plus one large-context fixture (8+ files, 3+ modules)
2. Inject one canary fact per fixture (fabricated entity name, e.g., `_xq7_verifyOAuthNonce`)
3. **Control:** dispatch subagent with full expanded prompt inline (current behavior) — 8-10 reps
4. **Test:** write expanded prompt to dispatch file, dispatch with pointer prompt — 8-10 reps
5. Compare: entity reference count, code reference count, canary fact presence

**Pass criteria:**
- Test mean within 1 std dev of control mean on entity and code reference counts
- Every canary fact correctly referenced in test runs
- No structural degradation in output format

**Deliverable:** Eval results written to `docs/plans/2026-04-05-dispatch-mediation-primacy-eval-results.md`.

**Budget note:** ~64-80 subagent runs at Opus pricing. **Cost control:** If eval runs exceed $100, reduce to 5 reps per template with wider confidence intervals. Minimum 5 reps for statistical significance.

- **Files:** 1-2 (eval results + optional fixture files)
- **Complexity:** High
- **Review-Tier:** 3
- **Dependencies:** Task 1 (must pass)
- **Atomic:** true — eval only, no skill edits
- **Restructuring-only:** false
- **Safe-partial:** true — produces eval data; no side effects
- **Rollback:** N/A (no repo changes)
- **Tests to verify:** Eval report exists with pass/degraded/fail per template

---

### Task 3: Phase 2 — Hybrid Fallback (Conditional)

**Only execute if Task 2 shows degradation on any template.**

If primacy effects are observed:
1. Design hybrid pointer prompt (~200-300 tokens): role + key constraints + instruction summary inline, heavy context (diffs, findings, cartographer data) on disk
2. Re-run eval on degraded templates with hybrid approach — 8-10 reps each
3. Confirm hybrid recovers quality to within 1 std dev of control
4. Update convention doc draft to specify hybrid mode rules and 300-token ceiling

**Deliverable:** Updated eval results showing hybrid recovery. Convention doc updated for hybrid mode.

- **Files:** 1-2 (updated eval results, convention doc draft)
- **Complexity:** High
- **Review-Tier:** 3
- **Dependencies:** Task 2 (only if degradation detected)
- **Atomic:** true — eval only
- **Restructuring-only:** false
- **Safe-partial:** true
- **Rollback:** N/A (no repo changes)
- **Tests to verify:** Hybrid eval results show recovery to within 1 std dev of control

---

### Task 4: Write Shared Convention Document

Create `skills/shared/dispatch-convention.md` — the canonical reference for all orchestrator skills.

**Contents (~50-80 lines):**
1. `version: 1` frontmatter
2. When to use disk-mediated dispatch vs. paste-only (bright-line: <500 tokens + Task tool + no file access)
3. Dispatch directory naming: `/tmp/crucible-dispatch-<session-id>/`
4. Session ID sourcing (reuse pipeline's existing ID; generate timestamp-based if standalone)
5. File naming: `<N>-<template-name>.md`
6. Dispatch file header format (4-line audit trail)
7. Pointer prompt format, 80-token target, 120-token hard ceiling (or 300 for hybrid)
8. Pointer prompt rules (role specificity, no file lists, "Begin by reading that file")
9. Sub-skill inheritance (use parent's dispatch directory and seq counter)
10. Fallback for missing dispatch directory path (glob + last-modified)
11. Compaction recovery (`.dispatch-active-<session-id>` marker in the pipeline's project-scoped memory directory)
12. Manifest (`manifest.jsonl`) format and fields
13. Manifest write-before-dispatch protocol
14. Cleanup strategy (copy manifest on success, full dir on failure)
15. Paste-only exclusions list (QG stagnation judge, fix verifier, prospector analysis under 500 tokens)
16. Note: relationship to CLAUDE.md (convention is shared skill reference, not CLAUDE.md directive; CLAUDE.md must not duplicate dispatch rules)
17. Note: stocktake should flag paste-only dispatches exceeding 500 tokens
18. Note: manifest schema is designed to be chronicle-compatible. When the chronicle system is live, the cleanup step should transform completed manifest entries into chronicle signals (per-dispatch granularity vs current per-skill-run). This wiring is deferred to the chronicle implementation — the convention doc documents the intent so the manifest schema doesn't drift.

Mode determination: full disk-mediated (default) or hybrid (only if Task 3 was triggered and validated).

- **Files:** 1 (`skills/shared/dispatch-convention.md`)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** Task 1 (must pass). Task 2 result determines mode selection (full vs hybrid), but convention doc can be drafted in parallel with Task 2.
- **Atomic:** true — single new file, no existing file edits
- **Restructuring-only:** false (new file)
- **Safe-partial:** true — additive, no behavioral change until skills reference it
- **Rollback:** `git revert` to pre-task commit
- **Tests to verify:** File exists; grep for `version: 1`; grep for key sections (manifest, pointer prompt, cleanup)

---

### Task 5: Phase 2.5 — Pointer Prompt Length Validation

Before rollout, validate that the 80-token target / 120-token ceiling holds for all ~73 dispatch templates.

1. For each template file, compose a realistic pointer prompt using the template's role and a representative dispatch file path
2. Count tokens (approximate: word count x 1.3 as rough proxy, or use tiktoken if available)
3. Report the top 10 longest pointer prompts
4. For any exceeding 80 tokens: confirm role description cannot be shortened without losing error-diagnostic specificity
5. For any exceeding 120 tokens: propose shortened role descriptions

**Deliverable:** Validation report as a section appended to the Phase 0 results doc, or as a standalone note. List of any templates requiring role shortening.

- **Files:** 1 (validation report / addendum)
- **Complexity:** Low
- **Review-Tier:** 1
- **Dependencies:** Task 4
- **Atomic:** true — analysis only
- **Restructuring-only:** false
- **Safe-partial:** true
- **Rollback:** N/A
- **Tests to verify:** Report exists with per-template token counts

---

### Task 6: Wave 1 Rollout — Build + Debugging (Highest Dispatch Volume)

These two skills account for the majority of pipeline dispatches and have the most templates. Rolling them out first validates the pattern at scale.

**Skills:** build (10 templates), debugging (6 templates)

**Per-skill SKILL.md changes:**
1. Add `<!-- CANONICAL: shared/dispatch-convention.md -->` reference comment
2. Add dispatch section sentence: "All subagent dispatches use disk-mediated dispatch (see shared/dispatch-convention.md)."
3. Remove any "paste X into prompt" / "paste relevant" language for subagent dispatch
4. Add dispatch directory initialization instructions (session ID, marker file)
5. Add manifest write instructions (before/after each dispatch)
6. Add cleanup instructions (pipeline completion phase)
7. Add compaction recovery instructions (glob for `.dispatch-active-*` marker, read `manifest.jsonl` for last seq counter)

**Per-template changes (17 files):**
Add 3-line comment header to each:
```markdown
<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
```

**Sub-step: paste language cleanup.** For each template, replace dispatch-method instructions ("paste it here, don't make the subagent read the file" and similar) with neutral placeholder text like `[FULL TEXT of the design doc]`. Grep for `paste.*into|paste it|paste them|paste relevant|don't make the subagent read` across all files touched in this wave.

**Build templates (11):**
- `acceptance-test-writer-prompt.md`
- `architecture-reviewer-prompt.md`
- `build-implementer-prompt.md`
- `build-reviewer-prompt.md`
- `cleanup-prompt.md`
- `contract-test-writer-prompt.md`
- `plan-reviewer-prompt.md`
- `plan-writer-prompt.md`
- `prd-writer-prompt.md`
- `refactor-implementer-addendum.md`
- `test-gap-writer-prompt.md`

**Debugging templates (6):**
- `implementer-prompt.md`
- `investigator-prompt.md`
- `pattern-analyst-prompt.md`
- `synthesis-prompt.md`
- `test-gap-writer-prompt.md`
- `where-else-prompt.md`

- **Files:** 19 (2 SKILL.md + 17 templates)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** Task 4, Task 5
- **Atomic:** true — each skill's changes are self-contained
- **Restructuring-only:** false (paste language cleanup modifies template instructions beyond adding headers)
- **Safe-partial:** true — skills work independently; partial rollout is safe
- **Rollback:** `git revert` to pre-task commit
- **Tests to verify:** grep for `<!-- DISPATCH: disk-mediated` in all 16 template files; grep for `dispatch-convention.md` in both SKILL.md files; grep -L for "paste into prompt" / "paste relevant" in both SKILL.md files (should return nothing)

---

### Task 7: Wave 2 Rollout — Quality-Gate, Design, Spec, Code-Review, Finish, Planning-Adjacent

Skills that participate in design/planning phases or are invoked as sub-skills by build/debugging.

**Skills and templates:**
- **quality-gate** — 2 templates (`fix-verifier-prompt.md`, `stagnation-judge-prompt.md`). Note: both are paste-only exclusion candidates per the design. Add the DISPATCH comment header noting exclusion status. SKILL.md still gets the convention reference.
- **design** — 1 multi-prompt file (`investigation-prompts.md`). Each of the 4 distinct prompt sections within gets a comment header.
- **spec** — 2 templates (`integration-check-prompt.md`, `spec-writer-prompt.md`)
- **code-review** — 1 file (`code-reviewer.md`)
- **finish** — 0 template files (dispatches inline from SKILL.md). SKILL.md changes only.
- **innovate** — 1 template (`innovate-prompt.md`). Called by build/design; included in Wave 2 since those skills are dispatchers.
- **consensus** — 3 templates (`aggregation-investigate-prompt.md`, `aggregation-review-prompt.md`, `aggregation-verdict-prompt.md`). Uses MCP not Agent tool, but templates get comment headers for consistency.

**Per-skill SKILL.md changes:** Same pattern as Task 6 (canonical ref, dispatch section sentence, remove paste language, add dispatch init/manifest/cleanup).

**Template changes (11 files, plus multi-prompt sections in design):**
Add the 3-line comment header. For paste-only exclusions (QG stagnation judge, fix verifier), use:
```markdown
<!-- DISPATCH: paste-only | Exempt from disk-mediated dispatch (<500 tokens,
     no file access). See shared/dispatch-convention.md -->
```

**Sub-step: paste language cleanup.** Same grep-and-replace procedure as Task 6 — update any dispatch-method instructions from "paste it here, don't make the subagent read" to neutral placeholder text across all files touched in this wave.

- **Files:** 18 (7 SKILL.md + 11 template files)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** Task 6 (validates the pattern works at scale before broader rollout)
- **Atomic:** true — per-skill changes are independent
- **Restructuring-only:** false (paste language cleanup modifies template instructions beyond adding headers)
- **Safe-partial:** true
- **Rollback:** `git revert` to pre-task commit
- **Tests to verify:** grep for `<!-- DISPATCH:` in all template files; grep for `dispatch-convention.md` in all 7 SKILL.md files; grep -L for "paste into prompt" in all 7 SKILL.md files (should return nothing)

---

### Task 8: Wave 3 Rollout — Security + Investigation Skills (incl. Red-Team)

Skills focused on adversarial analysis that tend to have high injected-context ratios.

**Skills and templates:**
- **siege** — 7 templates (betrayed-consumer, boundary-attacker, chain-analyst, fresh-attacker, infrastructure-prober, insider-threat, stagnation-judge). Note: `siege-stagnation-judge-prompt.md` may be a paste-only exclusion candidate — verify payload size.
- **audit** — 6 templates (architecture, blindspots, consistency, correctness, robustness, scoping)
- **adversarial-tester** — 1 template (`break-it-prompt.md`)
- **inquisitor** — 1 template (`inquisitor-prompt.md`)
- **red-team** — 1 template (`red-team-prompt.md`). Dispatching orchestrator with explicit paste language ("paste it, don't make the subagent read files") — must convert to disk-mediated dispatch.

**Per-skill SKILL.md changes:** Same pattern as Task 6.

**Template changes (16 files):** 3-line comment header on each.

**Sub-step: paste language cleanup.** Same grep-and-replace procedure as Task 6 — update any dispatch-method instructions across all files touched in this wave.

- **Files:** 21 (5 SKILL.md + 16 templates)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** Task 6 (validates the pattern)
- **Atomic:** true
- **Restructuring-only:** false (paste language cleanup modifies template instructions beyond adding headers)
- **Safe-partial:** true
- **Rollback:** `git revert` to pre-task commit
- **Tests to verify:** grep for `<!-- DISPATCH:` in all 16 template files; grep for `dispatch-convention.md` in all 5 SKILL.md files

---

### Task 9: Wave 4 Rollout — Remaining Skills

Skills with moderate template counts or specialized dispatch patterns.

**Skills and templates:**
- **migrate** — 5 templates (blast-radius-mapper, compatibility-designer, migration-analyzer, phase-planner, wave-grouper)
- **project-init** — 4 templates (init-recorder, neighbor-scanner, partition-explorer, topology-recorder). Note: project-init already uses a similar disk-write pattern for outputs — verify no conflict with the new dispatch input directory.
- **prospector** — 5 templates (analysis, design-competitor, explorer, genealogist, root-cause). Note: `analysis-prompt.md` is a paste-only exclusion candidate per the design — validate payload stays under 500 tokens.
- **recon** — 8 templates (consumer-mapper, diagnostic-gatherer, friction-scanner, impact-analyst, manifest-builder, pattern-scout, readiness-checker, structure-scout)
- **test-coverage** — 2 templates (test-audit, test-fix)
- **forge-skill** — 5 templates (retrospective, diagnostic-extraction, extraction-analyst, feed-forward, mutation-proposal)
- **cartographer-skill** — 1 template (`recorder-prompt.md`). Has explicit "paste into the subagent's dispatch prompt" language — must convert to disk-mediated dispatch.

**Per-skill SKILL.md changes:** Same pattern as Task 6.

**Template changes (30 files):** 3-line comment header on each (paste-only variant for exclusion candidates).

**Sub-step: paste language cleanup.** Same grep-and-replace procedure as Task 6 — update any dispatch-method instructions across all files touched in this wave. Cartographer's `recorder-prompt.md` specifically has "paste into the subagent's dispatch prompt" language that must be neutralized.

- **Files:** 37 (7 SKILL.md + 30 templates)
- **Complexity:** Medium
- **Review-Tier:** 2
- **Dependencies:** Task 6 (validates the pattern)
- **Atomic:** true
- **Restructuring-only:** false (paste language cleanup modifies template instructions beyond adding headers)
- **Safe-partial:** true
- **Rollback:** `git revert` to pre-task commit
- **Tests to verify:** grep for `<!-- DISPATCH:` in all 30 template files; grep for `dispatch-convention.md` in all 7 SKILL.md files

---

### Task 10: Sweep and Invariant Verification

Final verification pass across all 21 skills and ~73 templates. No new edits — this is audit only.

**Checks:**
1. **No paste language:** `grep -ri "paste .*(into\|relevant\|it\|them).*prompt\|paste it.*read\|paste them\|don't make the subagent read" skills/*/SKILL.md skills/*/*.md` — must return zero matches for dispatch-related contexts (some SKILL.md files may use "paste" for non-dispatch purposes; verify context). This also covers template files modified in Tasks 6-9.
2. **All templates tagged:** Every `*-prompt.md`, `*-prompts.md`, and `code-reviewer.md` file in the 21 skills has a `<!-- DISPATCH:` comment (either `disk-mediated` or `paste-only`)
3. **Convention referenced:** All 21 orchestrator SKILL.md files contain `dispatch-convention.md`
4. **Convention doc valid:** `skills/shared/dispatch-convention.md` exists, has `version: 1`, covers all required sections
5. **Pointer prompt length:** Re-verify top 10 longest pointer prompts are under 120 tokens
6. **Paste-only threshold:** Verify paste-only exclusions (QG stagnation judge, QG fix verifier, prospector analysis) have payloads under 500 tokens with realistic data

**Deliverable:** Verification checklist (pass/fail per check). Any failures become fixup commits.

- **Files:** 0 (audit only; fixups if needed)
- **Complexity:** Low
- **Review-Tier:** 1
- **Dependencies:** Tasks 6, 7, 8, 9 (all waves complete)
- **Atomic:** true — read-only audit
- **Restructuring-only:** N/A
- **Safe-partial:** true
- **Rollback:** N/A
- **Tests to verify:** All 6 checks pass; grep commands return expected results

---

## Summary

| Task | Phase | Files | Complexity | Review-Tier | Dependencies |
|---|---|---|---|---|---|
| 1. Baseline measurement | Phase 0 | 1 | Medium | 2 | #106 (preferred) or word-count proxy (fallback) |
| 2. Primacy eval | Phase 1 | 1-2 | High | 3 | Task 1 |
| 3. Hybrid fallback | Phase 2 | 1-2 | High | 3 | Task 2 (conditional) |
| 4. Convention doc | — | 1 | Medium | 2 | Task 1 (must pass); Task 2 for mode (can draft in parallel) |
| 5. Pointer length validation | Phase 2.5 | 1 | Low | 1 | Task 4 |
| 6. Wave 1 (build, debugging) | Phase 3 | 19 | Medium | 2 | Tasks 4, 5 |
| 7. Wave 2 (QG, design, spec, code-review, finish, innovate, consensus) | Phase 3 | 18 | Medium | 2 | Task 6 |
| 8. Wave 3 (siege, audit, adversarial-tester, inquisitor, red-team) | Phase 3 | 21 | Medium | 2 | Task 6 |
| 9. Wave 4 (migrate, project-init, prospector, recon, test-coverage, forge-skill, cartographer-skill) | Phase 3 | 36 | Medium | 2 | Task 6 |
| 10. Sweep + verification | — | 0 | Low | 1 | Tasks 6-9 |

**Total files touched:** ~93 (1 new convention doc + 21 SKILL.md edits + ~73 template headers + measurement/eval reports)

**Parallelizable:** Tasks 7, 8, 9 can run in parallel after Task 6 validates the pattern. Tasks 1-5 are strictly sequential.
