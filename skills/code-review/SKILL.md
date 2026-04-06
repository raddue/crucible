---
name: code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
---

# Requesting Code Review

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Dispatch a code review subagent (general-purpose) to catch issues before they cascade.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch code-reviewer subagent:**

Use Task tool with subagent_type="general-purpose". Fill in the template at code-reviewer.md in this directory and pass it as the subagent prompt.

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` - What you just built
- `{PLAN_OR_REQUIREMENTS}` - What it should do
- `{BASE_SHA}` - Starting commit
- `{HEAD_SHA}` - Ending commit
- `{DESCRIPTION}` - Brief summary

**3. Act on feedback and iterate:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if reviewer is wrong (with reasoning)
- **Record the issue count** (Critical + Important only — Minor doesn't count)

**4. Re-review after fixes (iterative loop):**

After fixing Critical/Important issues, dispatch a **NEW fresh code-reviewer subagent** (not the same one — fresh eyes, no anchoring). Compare issue count to prior round:

- **Strictly fewer Critical+Important issues:** Progress — fix and re-review again.
- **Same or more Critical+Important issues:** Stagnation — escalate to user with findings from both rounds.
- **No Critical/Important issues:** Clean — proceed.
- **Architectural concerns:** Immediate escalation regardless of round.

**Fresh reviewer every round.** Never pass prior findings to the next reviewer.

## External Model Review (Optional)

After dispatching the host code-reviewer subagent, optionally call the `external_review` MCP tool for an independent second opinion from external models. The preferred pattern is: dispatch the host reviewer as a background Agent first, call `external_review`, then collect host results — this gives effective parallelism where background agents are available.

**Invocation:**

Call `external_review` with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: the same diff and requirements context given to the host reviewer
- `skill`: `"code_review"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "code_review", "round": N}` (traceability; where N is the current review round)

**Per-skill toggle:** The server checks the `skill` argument against `skills.code_review` in the external review config. If `false`, the server returns `unavailable`.

**Graceful degradation:**
- `external_review` tool not available (MCP server not running): skip silently.
- Response `status` is `"unavailable"` (no config or disabled): skip silently.
- Response `status` is `"partial"` (some models failed): show available reviews, note which models failed.

**Output format:** After the host review output, append each external review in its own section:
```
## External Review — {provider} ({model_id})
{review content}
```

**Contract INV-1:** External review dispatch must never block or delay the host review. If external review times out or fails, the host review stands alone.

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Dispatch fresh code-reviewer subagent — Round 1]
  Issues: 2 Important (missing progress indicators, no error handling for empty input)
  Minor: 1 (magic number)

You: [Fix both Important issues]

[Dispatch NEW fresh code-reviewer subagent — Round 2]
  Issues: 1 Important (error handling catches wrong exception type)

Round 2 (1 issue) < Round 1 (2 issues) → progress, continue

You: [Fix the exception type]

[Dispatch NEW fresh code-reviewer subagent — Round 3]
  Issues: 0 Critical/Important
  Minor: 1 (could use named constant)

Clean — proceed to Task 3.
```

## Test Alignment

When code-review is used standalone (not from build, debugging, or finish — those pipelines handle test-coverage automatically), the caller should consider dispatching `crucible:test-coverage` after code review completes if behavioral changes were made.

This is especially valuable when:
- The review identified behavioral changes that might affect existing tests
- The diff modifies functions/methods that have dedicated test files
- The review noted "tests should be updated" without specifying which ones

## Integration with Workflows

**Build Pipeline:**
- Review after EACH task
- Test-coverage audit after review (handled by build pipeline)
- Catch issues before they compound
- Fix before moving to next task

**Standalone Plan Execution:**
- Review after each batch (3 tasks)
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck
- Consider `crucible:test-coverage` after review if behavioral changes were made

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback
- Skip re-review after fixes ("the fixes look fine")
- Reuse the same reviewer subagent across rounds
- Pass prior findings to the next reviewer

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: code-review/code-reviewer.md
