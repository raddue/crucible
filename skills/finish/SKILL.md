---
name: finish
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests -> Code review -> Red-team -> Present options -> Execute choice -> Clean up.

**Announce at start:** "I'm using the finish skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Code Review (Mandatory)

**Before presenting options, run a full code review.**

**REQUIRED SUB-SKILL:** Use crucible:code-review

1. Get base and head SHAs:
```bash
BASE_SHA=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master)
HEAD_SHA=$(git rev-parse HEAD)
```

2. Check diff size to determine review approach:
```bash
git diff --stat $(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master)...HEAD
```

3. Dispatch a code review subagent (general-purpose) using the `code-review/code-reviewer.md` template with:
   - What was implemented (summary of branch work)
   - The plan or requirements it was built against
   - Base and head SHAs
   - Brief description
   - For large diffs (20+ files changed): provide the `--stat` summary and key files list, let the reviewer pull targeted diffs rather than receiving the entire diff. Consider splitting into multiple focused reviewers -- one per subsystem.

4. Act on feedback:
   - **Critical issues:** Fix immediately. Re-run tests. Do NOT proceed.
   - **Important issues:** Fix before proceeding. Re-run tests.
   - **Minor issues:** Note them. Fix if quick, otherwise include in PR description.

5. If fixes were made, re-run tests to confirm nothing broke.

**Do NOT skip this step.** The orchestrator did lightweight review during execution -- this is the comprehensive review before integration.

### Step 2.5: Test Alignment Audit

**RECOMMENDED SUB-SKILL:** Use crucible:test-coverage (if available) — audit whether existing tests are still aligned with the changes on this branch. Invoke with:
- Code diff: `git diff <base-branch>..HEAD`
- Context: "Finish pre-merge audit for [branch description]"

The test-coverage skill handles its own fix dispatch and revert-on-failure logic. If not available, skip this step.

### Step 2.75: Forge Retrospective

**RECOMMENDED SUB-SKILL:** Use crucible:forge (retrospective mode) — capture what happened vs what was planned while execution context is still fresh. Run this BEFORE red-team so the retrospective has access to the full execution state.

### Step 3: Red-Team the Implementation (Mandatory)

**After code review passes, red-team the full implementation.**

**REQUIRED SUB-SKILL:** Use crucible:red-team

1. Dispatch `crucible:red-team` on the full implementation:
   - Artifact: the complete set of changes on this branch (provide `git diff --stat` and key files)
   - Context: the design doc or plan this was built against
   - Fix mechanism: dispatch fix subagent for any findings
2. The red-team skill handles the iterative loop (fresh Devil's Advocate each round, stagnation detection)
3. Fix all Fatal/Significant findings before proceeding

**Do NOT skip this step.** Code review checks quality; red-teaming checks whether the system will actually work and survive real use.

### Step 4: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 5: Present Options

Present exactly these 4 options:

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Don't add explanation** - keep options concise.

### Step 6: Execute Choice

#### Option 1: Merge Locally

```bash
# Switch to base branch
git checkout <base-branch>

# Pull latest
git pull

# Merge feature branch
git merge <feature-branch>

# Verify tests on merged result
<test command>

# If tests pass
git branch -d <feature-branch>
```

Then: If using a worktree, clean it up (Step 7)

#### Option 2: Push and Create PR

```bash
# Push branch
git push -u origin <feature-branch>

# Create PR
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Test Plan
- [ ] <verification steps>
EOF
)"
```

Then: If using a worktree, clean it up (Step 7)

#### Option 3: Keep As-Is

Report: "Keeping branch <name>."

If using a worktree: "Worktree preserved at <path>."

#### Option 4: Discard

**Confirm first:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
git checkout <base-branch>
git branch -D <feature-branch>
```

Then: If using a worktree, clean it up (Step 7)

### Step 7: Cleanup Worktree (If Applicable)

**Skip this step if not using git worktrees.**

**For Options 1, 2, and 4:**

Check if in worktree:
```bash
git worktree list | grep $(git branch --show-current)
```

If yes:
```bash
git worktree remove <worktree-path>
```

**For Option 3:** Keep worktree.

## Quick Reference

| Option | Merge | Push | Cleanup Branch | Cleanup Worktree (if applicable) |
|--------|-------|------|----------------|----------------------------------|
| 1. Merge locally | Yes | - | Yes | Yes |
| 2. Create PR | - | Yes | - | Yes |
| 3. Keep as-is | - | - | - | - |
| 4. Discard | - | - | Yes (force) | Yes |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Skipping code review**
- **Problem:** Subtle bugs, architectural violations, and style drift make it into the branch
- **Fix:** Always run crucible:code-review before presenting options. The orchestrator's lightweight review during execution is not sufficient.

**Open-ended questions**
- **Problem:** "What should I do next?" -> ambiguous
- **Fix:** Present exactly 4 structured options

**Automatic worktree cleanup**
- **Problem:** Remove worktree when might need it
- **Fix:** Only cleanup worktree for Options 1, 2, and 4 -- and only if actually using worktrees

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

## Red Flags

**Never:**
- Proceed with failing tests
- Skip code review because "it looks fine" or "subagents already reviewed it"
- Skip red-team because "code review already passed"
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request

**Always:**
- Verify tests before code review
- Run full code review before presenting options
- Run red-team after code review passes, before presenting options
- Fix Critical/Important review findings before proceeding
- Present exactly 4 options
- Get typed confirmation for Option 4
- Clean up worktree (if applicable) for Options 1, 2 & 4 only

## Integration

**Called by:**
- **build** (Phase 4) - After all tasks complete

**Pairs with:**
- **worktree** - Cleans up worktree (if applicable)
- **crucible:red-team** — Adversarial review before presenting options. Note: finish uses `crucible:red-team` directly rather than `crucible:quality-gate` because it doesn't produce a typed artifact — it's a pre-completion sanity check, not an iterative gate.

**Recommended:**
- **crucible:test-coverage** — Test alignment audit between code review and red-team (Step 2.5)
- **crucible:forge** — Retrospective between test audit and red-team (Step 2.75)
