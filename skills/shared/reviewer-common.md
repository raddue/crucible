# Reviewer Common -- Canonical Reference

> This file is the single source of truth for shared reviewer sections.
> Prompt templates that use these sections keep inline copies marked with
> `<!-- CANONICAL: shared/reviewer-common.md#section-name -->` comments.
> When updating, change this file first, then propagate to templates.
>
> **Used by:** `skills/build/build-reviewer-prompt.md`, `skills/code-review/code-reviewer.md`

## Review Checklist

### Architecture and Patterns
- Does it follow project conventions (DI, events, ScriptableObjects, etc.)?
- Is it consistent with existing codebase patterns?
- Are components properly wired (actually connected, not just existing)?
- Sound design decisions?
- Scalability and performance implications?

### Correctness
- Does the implementation match the task requirements / spec?
- Are there logic errors, off-by-one errors, missing null checks?
- Are edge cases handled?
- No scope creep -- implementation matches what was requested?

### Quality
- Clean separation of concerns? Single responsibility per component?
- Clear naming that matches what things DO, not how they work?
- Proper error handling?
- DRY principle followed?
- No overengineering or YAGNI violations?

### Testing
- Tests actually test behavior (not just mock interactions)?
- Edge cases covered?
- Integration tests where needed? (Are complex mock setups masking the need for one?)
- All tests passing?
- Tests are independent and deterministic?
- Tests follow AAA pattern (Arrange, Act, Assert)?

### TDD Process Evidence
- Does the implementer's TDD log list a failure message for each test?
- Do the failure messages make sense (indicate missing feature, not typo/setup error)?
- Does the git history show test-then-implementation ordering?
- If the TDD log is missing or vague, flag it: "TDD log incomplete, cannot verify red-green process"

## Issue Classification

**Per-issue severity levels:**

- **Critical (Must Fix):** Bugs, security issues, data loss risks, broken functionality. The code cannot ship with these.
- **Important (Should Fix):** Architecture problems, missing error handling, test gaps, missing features from the spec. These materially affect quality or correctness.
- **Minor (Nice to Have):** Code style, optimization opportunities, documentation improvements. These improve polish but don't affect correctness.
- **Suggestion:** Not an issue per se -- ideas for future improvement, alternative approaches worth considering.

**Overall verdict levels** (used by build reviewer to classify the review outcome):

- **Clean:** No issues found. Code is ready to merge.
- **Issues Found:** Specific problems identified that need fixing before merge.
- **Architectural Concern:** Fundamental design issue that may require rethinking the approach. Escalate to lead immediately.

## Report Format

**For each issue found:**
- File:line reference (be specific, not vague)
- What's wrong
- Why it matters
- Severity classification
- How to fix (if not obvious)

**Report structure:**

```
### Code Review
- Verdict: Clean | Issues Found | Architectural Concern
- Issues: [specific findings with file:line references]
- Architectural concerns: [if any -- immediate escalation]

### Test Review
- Verdict: Clean | Issues Found
- TDD process: Verified | Incomplete log | No evidence
- Missing coverage: [specific code paths without tests]
- Stale / dead tests: [tests that need updating or removal]

### Overall
- Combined verdict: Approved | Needs Fixes (list them) | Escalate

### Recommendations
[Improvements for code quality, architecture, or process]

### Assessment
Ready to merge? [Yes / No / With fixes]
Reasoning: [Technical assessment in 1-2 sentences]
```

## Verification Principle

**Do Not Trust the Report.**

The implementer's report may be incomplete or optimistic. Verify everything by reading actual code:

- Do NOT take the implementer's word for what was changed -- read the files yourself.
- Do NOT assume tests pass because the report says so -- check the actual test code and results.
- Do NOT assume requirements are met because the report claims they are -- compare implementation against the spec.
- Acknowledge strengths where they exist, but verify claims against actual code.

**DO:**
- Categorize by actual severity (not everything is Critical)
- Be specific (file:line, not vague)
- Explain WHY issues matter
- Acknowledge strengths
- Give a clear verdict

**DON'T:**
- Say "looks good" without checking
- Mark nitpicks as Critical
- Give feedback on code you didn't review
- Be vague ("improve error handling")
- Avoid giving a clear verdict
