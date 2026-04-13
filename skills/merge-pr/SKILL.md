---
name: merge-pr
description: "Use when merging a PR after implementation is complete - verifies CI, runs local tests, checks repo safety, and monitors post-merge health. Triggers on 'merge pr', 'merge this', 'land this PR', or any task executing a PR merge."
---

# Merging a Pull Request

## Overview

Safely merge a PR with full CI verification, local test validation, and post-merge health monitoring.

**Core principle:** Verify CI -> Check working tree -> Repo safety scan -> Local tests -> Merge -> Post-merge CI -> Cleanup.

**Announce at start:** "I'm using the merge-pr skill to safely land this PR."

## The Process

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 1: CI Status Check

**Verify all CI checks pass before anything else:**

```bash
gh pr checks <pr-number>
```

**If any checks are failing:**
```
CI checks failing. Cannot merge.

FAILED:
- <check-name>: <url>
- <check-name>: <url>

Fix these before attempting merge.
```

Stop. Don't proceed to Step 2.

**If checks are pending:** Wait. Re-check with `gh pr checks <pr-number>` after a reasonable interval. Don't proceed until all checks resolve.

**If all checks pass:** Continue to Step 2.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 2: Working Tree Check

**Verify no uncommitted work is hiding:**

```bash
git status
```

**If untracked or modified files exist:**
```
Working tree is not clean:

Untracked:
- <file>
- <file>

Modified:
- <file>

Should these be committed before merge? (y/n)
```

Stop. Wait for user decision. If user says yes, commit them first. If user says no, proceed.

**If working tree is clean:** Continue to Step 3.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 3: Repository Safety Check

**Determine repo visibility:**

```bash
gh repo view --json isPrivate -q .isPrivate
```

**If the repo is PUBLIC (`false`):**

1. Scan the PR body for sensitive content:
```bash
gh pr view <pr-number> --json body -q .body
```

2. Scan commit messages:
```bash
gh pr view <pr-number> --json commits --jq '.commits[].messageHeadline'
```

3. Look for: proprietary company names, internal tool references, API keys, internal URLs, employee names, infrastructure details.

4. **If anything looks sensitive:**
```
PUBLIC REPO — potential sensitive content detected:

- PR body: <what was found>
- Commits: <what was found>

Confirm this is safe to merge publicly? (y/n)
```

Stop. Wait for explicit confirmation.

**If the repo is private:** Note it and continue.

**If all clear:** Continue to Step 4.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 4: Local Test Suite

**Run the project's test suite locally:**

```bash
# Detect and run the appropriate test command
npm test / cargo test / pytest / go test ./... / dotnet test
```

**If tests fail:**
```
Local tests failing (<N> failures). Cannot merge.

[Show failures]

Fix these before merge.
```

Stop. Don't proceed to Step 5.

**If tests pass:** Continue to Step 5.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 5: Merge Execution

**Only reach this step after ALL above checkpoints pass.**

Ask the user:
```
All checks passed. Merge method?

1. Merge commit
2. Squash and merge
3. Rebase and merge
```

Wait for choice. Then execute:

```bash
# Option 1
gh pr merge <pr-number> --merge

# Option 2
gh pr merge <pr-number> --squash

# Option 3
gh pr merge <pr-number> --rebase
```

**If merge fails:**
- **Conflict:** Report conflicting files. Suggest resolution steps.
- **Branch protection:** Report which rules blocked the merge. Suggest what's needed (approvals, status checks, etc.).
- **Other:** Show the error verbatim. Don't retry automatically.

**If merge succeeds:** Continue to Step 6.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 6: Post-Merge CI Verification

**Don't walk away after merge. Verify CI on the target branch:**

```bash
# Get the target branch (don't assume main)
TARGET_BRANCH=$(gh pr view <pr-number> --json baseRefName -q .baseRefName)

gh run list --branch $TARGET_BRANCH --limit 5
```

**If a run is in progress:**
```bash
gh run watch <run-id>
```

**If post-merge CI fails:**
```bash
gh run view <run-id> --log-failed
```

Surface the failure summary to the user immediately:
```
POST-MERGE CI FAILURE on $TARGET_BRANCH:

Run: <run-id>
Failed step: <step-name>
Error: <summary>

This needs immediate attention. The target branch is broken.
```

Do NOT proceed to cleanup until the user acknowledges the failure and decides next steps.

**If post-merge CI passes:** Continue to Step 7.

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 7: Cleanup

**Ask before deleting anything:**

```
Merge complete. Clean up branches?

- Delete remote branch origin/<branch-name>? (y/n)
- Delete local branch <branch-name>? (y/n)
```

Wait for confirmation. Then execute as directed:

```bash
# Delete remote branch
git push origin --delete <branch-name>

# Delete local branch
git branch -d <branch-name>

# Switch to target branch
git checkout main && git pull
```

Report final state:
```
PR #<number> merged successfully.
Branch <branch-name> cleaned up.
Main branch CI: passing.
```

## Common Mistakes

**Merging without checking CI**
- **Problem:** Land a PR with failing checks, break the target branch
- **Fix:** Always run `gh pr checks` first. No exceptions.

**Skipping local tests**
- **Problem:** CI passed but local environment reveals failures CI doesn't catch
- **Fix:** Always run the local test suite before merge

**Not monitoring post-merge CI**
- **Problem:** Merge succeeds but the combined result breaks main. Nobody notices for hours.
- **Fix:** Always watch the post-merge CI run. Surface failures before moving on.

**Force-merging past branch protection**
- **Problem:** Bypass safety rules, merge broken or unreviewed code
- **Fix:** Never use `--admin` flag. Report the protection rule and let the user resolve it properly.

**Deleting branches without confirmation**
- **Problem:** Lose branch reference before user is ready
- **Fix:** Always ask before deleting. Both local and remote.

## Red Flags

**Never:**
- Merge with failing CI
- Merge with failing local tests
- Skip the repo safety check on public repos
- Move on after merge without checking post-merge CI
- Delete branches without confirmation
- Use `--admin` to bypass branch protection
- Retry a failed merge automatically without user input

**Always:**
- Check CI status before anything else
- Run local tests even if CI passed
- Scan public repos for sensitive content in PR body and commits
- Watch post-merge CI to completion
- Get explicit confirmation before branch deletion
- Report post-merge CI failures immediately

## Integration

**Called by:**
- **finish** (Step 6, Option 2) — When user chooses PR merge, finish delegates the actual merge execution to merge-pr

**Relationship to finish:**
- **/finish** handles the *decision*: verify tests, code review, red-team, present options (merge, PR, keep, discard)
- **/merge-pr** handles the *execution*: CI verification, safety checks, merge mechanics, post-merge monitoring
- finish owns the pre-merge quality gates (review, red-team); merge-pr owns the merge-time safety gates (CI, repo safety, post-merge health)

**Pairs with:**
- **verify** — Can be used to double-check claims before merge
- **worktree** — If merging from a worktree, cleanup coordination

## Gate Execution Ledger

Before completing this skill, confirm every mandatory checkpoint was executed:

- [ ] CI status verified
- [ ] Working tree clean
- [ ] Repository safety checked
- [ ] Local tests passed
- [ ] Merge executed
- [ ] Post-merge CI verified
- [ ] Cleanup completed

**If any checkbox is unchecked, STOP. Go back and execute the missed gate.**
