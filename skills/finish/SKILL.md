---
name: finish
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup
---

# Finishing a Development Branch

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

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

**RECOMMENDED SUB-SKILL:** Use crucible:test-coverage — audit whether existing tests are still aligned with the changes on this branch. Invoke with:
- Code diff: `git diff <base-branch>..HEAD`
- Affected test files: test files in the diff or test files that import changed modules
- Context: "Finish pre-merge audit for [branch description]"

The test-coverage skill handles its own fix dispatch and revert-on-failure logic.

**Skip this step when:**
- The branch diff contains no behavioral source changes (only `.md`, `.json`, `.yaml`, config files)
- Build told finish to skip Step 2.5 (test-coverage already ran per-task in Phase 3)

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

### Step 3.5: Noticed But Not Touching — Optional Issue Conversion

Check for `docs/plans/*-noticed.md` files matching the current pipeline (date + ticket-slug). If one exists and contains entries, prompt:

```
Found <N> noticed-but-not-touching entries in <noticed.md path>. Convert any to GitHub issues?
```

On confirmation, display a numbered list of entries and ask which to convert. For each selected entry, create an issue via `gh issue create` using the entry's `noticed`, `why it matters`, and `suggested follow-up` fields. Skip silently if no matching `-noticed.md` file exists.

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

## MANDATORY CHECKPOINT - DO NOT SKIP

### Step 5.5: Pre-Push Validation (Non-Negotiable)

**BLOCK semantics:** you CANNOT proceed to Option 1 (merge) or Option 2 (push + PR) until local validation passes. A failing check is a hard stop. Do not push "then fix in CI"; do not merge "then fix on main."

**Detect the project's toolchain once** (read `package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, etc. before running anything). Run only the checks that actually apply. Silently-missing tools are NOT a pass — they are an "unknown" that must be resolved by either running the real tool or explicitly documenting its absence. Never use `2>/dev/null || true` patterns that hide failures.

**Validation matrix (run every applicable check; each must exit 0):**

| Ecosystem | Type-check | Lint | Tests |
|---|---|---|---|
| TypeScript/Node | `npx tsc --noEmit` (if `tsconfig.json` present) | `npm run lint` or `pnpm lint` or `biome check` (whichever the repo configures) | `npm test` / `pnpm test` / `vitest run` / `jest` |
| Rust | (compiler via test) | `cargo clippy --all-targets -- -D warnings` | `cargo test --all` |
| Python | `mypy` or `pyright` (if configured) | `ruff check` or `flake8` (whichever is configured) | `pytest` |
| Go | (compiler via test) | `go vet ./...` | `go test ./...` |

**If a check is not configured for this repo, say so explicitly in the narration** ("no type-check configured — skipping") rather than silencing the command. If uncertain whether a check is configured, ask the user; do not assume.

**On ANY non-zero exit code: STOP.** Report the failure, dispatch a fix, and re-run the full matrix from scratch. Do not partially re-run — a fix in one layer can regress another.

### Step 5.6: Post-Push CI Monitoring (Option 2 only)

**BLOCK semantics:** after `gh pr create` returns the PR URL, you CANNOT report success to the user until CI has finished AND passed. "Pushed" is not "done."

```bash
# Watch checks to completion — blocks until all checks resolve
gh pr checks <pr-number> --watch
```

`--watch` streams check status and exits with the final aggregate code (0 = all pass, non-zero = at least one failure/cancellation). If `--watch` is unavailable in the installed `gh` version, poll:

```bash
while true; do
  STATUS=$(gh pr checks <pr-number> --json state --jq '[.[] | .state] | unique')
  echo "$STATUS"
  echo "$STATUS" | grep -qE '"PENDING"|"QUEUED"|"IN_PROGRESS"' || break
  sleep 20
done
```

**If any check fails:** diagnose the failure from CI logs (`gh run view <run-id> --log-failed` or `gh pr checks <pr-number>`), dispatch a fix, push, and re-watch. Do NOT report success on a red PR, and do NOT leave the watch running while moving on to another task — CI failure is an actionable blocker that takes precedence.

**If checks are entirely absent** (repo has no CI configured): record that in the final report so the user knows local validation was the only gate, and recommend they add CI.

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

**Repository Safety Check (before push):**
```bash
# Check if repo is public
IS_PRIVATE=$(gh repo view --json isPrivate -q .isPrivate)
```
If the repo is public: scan the PR title, body, and commit messages for proprietary company information, internal names, internal URLs, or sensitive data. STOP and confirm with the user if anything looks sensitive. This check is mandatory — a prior incident involved filing proprietary information to a public repo.

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

**Skipping pre-push validation**
- **Problem:** "Tests passed during /build so this should be fine" — but refactors between Phase 3 and finish, plus drift in companion files, can silently break the build. Pushing broken code wastes CI minutes and creates a red PR for reviewers.
- **Fix:** Always run Step 5.5's full validation matrix before Option 1 merge or Option 2 push. Every applicable check must exit 0.

**Silencing validation failures**
- **Problem:** `2>/dev/null || true` patterns hide tool failures and make "no output" indistinguishable from "tool missing" — a failing tsc looks identical to a repo without TypeScript.
- **Fix:** Detect the toolchain from manifest files first, then run only the checks that apply with strict exit-code discipline. Explicitly narrate skipped checks rather than silencing errors.

**Pushing and moving on**
- **Problem:** `git push` returns, `gh pr create` returns a URL, task feels done. CI runs later, fails, and nobody notices until the next review session.
- **Fix:** Block on `gh pr checks <pr-number> --watch` (or equivalent poll loop). Treat a red PR as a hard stop — never report success to the user on a failing PR.

## Red Flags

**Never:**
- Proceed with failing tests
- Skip code review because "it looks fine" or "subagents already reviewed it"
- Skip red-team because "code review already passed"
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request
- Push code that has not passed the full local validation matrix in Step 5.5
- Use `|| true` or `2>/dev/null` to silence a validation check — skipped checks must be narrated, not hidden
- Report success to the user after `gh pr create` without confirming all CI checks pass
- Abandon a watched PR to work on something else — a red PR is an actionable blocker

**Always:**
- Verify tests before code review
- Run full code review before presenting options
- Run red-team after code review passes, before presenting options
- Fix Critical/Important review findings before proceeding
- Detect the project toolchain from manifest files before Step 5.5 dispatch
- Run every applicable validation check with strict exit-code discipline
- Watch CI to completion after push (`gh pr checks --watch`) before declaring Option 2 done
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
- **crucible:merge-pr** — Handles merge execution with CI verification (Step 6, Option 2)

## Gate Execution Ledger

Before completing this skill, confirm every mandatory checkpoint was executed:

- [ ] Test verification
- [ ] Code review
- [ ] Test alignment audit (if applicable)
- [ ] Red-team review
- [ ] Pre-push validation passed
- [ ] Repository safety checked (if public repo, Option 2)

**If any checkbox is unchecked, STOP. Go back and execute the missed gate.**
