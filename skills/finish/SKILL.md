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

**REQUIRED SUB-SKILL:** Use crucible:temper

1. Get base and head SHAs:
```bash
BASE_SHA=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master)
HEAD_SHA=$(git rev-parse HEAD)
```

2. Check diff size to determine review approach:
```bash
git diff --stat $(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master)...HEAD
```

3. Dispatch a code review subagent (general-purpose) using the `temper/temper-reviewer.md` template with:
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

**Detect the project's toolchain first** by reading manifest files at repo root: `package.json`, `Cargo.toml`, `pyproject.toml` / `requirements.txt`, `go.mod`, `*.csproj` / `*.sln`, `Gemfile`, `build.gradle` / `pom.xml`. Run only the checks that actually apply.

- **Monorepo / polyglot root:** if multiple manifests coexist at root (e.g., a Rust product with a Node.js tooling script), scope validation to whichever ecosystem owns the files changed in the diff (`git diff --name-only <base>...HEAD`). If ambiguous, ask the user before running the full matrix.
- **Nested manifests:** if the diff touches files under a subdirectory with its own manifest, scope to that subdirectory.

Silently-missing tools are NOT a pass — they are an "unknown." Either run the real tool, or narrate the skip ("no type-check configured — skipping"), or ask the user. Never mask a failure with `|| true` or `2>/dev/null`.

**Validation matrix (run every applicable check; each must exit 0 unless its documented exit-code contract says otherwise):**

| Ecosystem | Type-check | Lint | Format | Tests |
|---|---|---|---|---|
| TypeScript/Node | `npx tsc --noEmit` (if `tsconfig.json`) | `npm run lint` / `pnpm lint` / `biome check` (whichever the repo configures) | `prettier --check .` / `biome format --check` (whichever configured) | `npm test` / `pnpm test` / `vitest run` / `jest` |
| Rust | `cargo check --all-targets --all-features` | `cargo clippy --all-targets --all-features -- -D warnings` | `cargo fmt -- --check` | `cargo test --workspace --all-features` |
| Python | `mypy` or `pyright` (if configured) | `ruff check` / `flake8` (whichever configured) | `ruff format --check` / `black --check` (whichever configured) | `pytest` |
| Go | (compiler via `go build ./...`) | `go vet ./...` (add `golangci-lint run` if configured) | `out=$(gofmt -l .) && [ -z "$out" ]` (preserves gofmt exit code AND fails non-zero on drift) | `go test ./...` |
| .NET | `dotnet build -p:TreatWarningsAsErrors=true` (portable across Linux/macOS/Windows; covers type + warnings-as-errors) | Roslyn analyzers via the same `-p:TreatWarningsAsErrors=true` + any configured analyzer package | `dotnet format --verify-no-changes` | `dotnet test` |
| Ruby | (runtime only) | `bundle exec rubocop` (covers Layout + Style + Lint) | covered by Lint (or `bundle exec standardrb` if configured instead of rubocop) | `bundle exec rspec` / `bundle exec rake test` |
| Java/Kotlin | (compiler via `./gradlew build`) | `./gradlew checkstyleMain spotbugsMain` or `./mvnw spotbugs:check` (if configured) | `./gradlew spotlessCheck` (if configured) | `./gradlew test` or `./mvnw test` |

For ecosystems not in this matrix, extend it: manifest → type-check → lint → format-check → test. Do not skip an ecosystem because it isn't listed.

**Exit-code interpretation:** treat each tool's documented exit-code contract authoritatively, not just 0 vs non-0. Example: `gh pr checks` exits 8 for "checks pending" — a legitimate non-terminal state, not a failure. The rule is "never mask an exit code without interpreting it," not "non-zero is always failure." If a tool's contract is unclear, treat non-zero as failure and ask the user.

**On ANY unhandled non-zero exit (after exit-code interpretation): STOP.** Report the failure, dispatch a fix, and re-run the full matrix from scratch. Do not partially re-run — a fix in one layer can regress another.

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

<!-- CANONICAL: shared/compass-protocol.md -->
**Compass emit (after local merge + tests pass):**

Run `compass update` (atomic multi-field) to emit `last_meaningful_commit` plus arc-closure. Capture the merge commit SHA and subject first. The `next_move` value comes from the caller's `--value` argument if provided, otherwise preserve the existing `next_move` (omit `--set next_move` entirely), or pass an empty string if no prior value exists.

```bash
MERGE_SHA=$(git rev-parse HEAD)
MERGE_SUBJECT=$(git log -1 --pretty=%s)

# If caller provided a next_move value:
python scripts/compass.py update \
  --set last_meaningful_commit --value "${MERGE_SHA}:${MERGE_SUBJECT}" \
  --set current_arc --value '' \
  --set next_move --value '<caller-provided-or-empty>'

# If no next_move value was provided by caller, omit --set next_move
# so the existing value is preserved:
python scripts/compass.py update \
  --set last_meaningful_commit --value "${MERGE_SHA}:${MERGE_SUBJECT}" \
  --set current_arc --value ''
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

# Create PR and capture the URL gh emits (the PR it just created).
# This is the only deterministic PR reference — using `gh pr view`
# instead would use branch-to-PR mapping, which breaks on repos
# with multiple open PRs per branch.
PR_URL=$(gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Test Plan
- [ ] <verification steps>
EOF
)")
PR_NUMBER="${PR_URL##*/}"

# Guard: if gh pr create failed (e.g., a PR already exists for this branch),
# PR_URL is empty — surface the real diagnostic instead of falling through
# into CI monitoring and emitting a misleading "CI failed" message.
if [ -z "$PR_URL" ] || [ -z "$PR_NUMBER" ]; then
  echo "gh pr create did not return a PR URL — possible duplicate PR. Inspect: gh pr list --head <feature-branch>"
  exit 1
fi
```

**Post-Push CI Monitoring (Non-Negotiable):** after `gh pr create` returns, you CANNOT report success to the user until CI has finished AND passed. "Pushed" is not "done." BLOCK on the watch + empty-check assertion below. Fail closed on any non-zero result that isn't the "no CI configured" case:

```bash
# Primary: --watch streams status and returns aggregate exit code.
# Exit 0 = all terminal passes OR no checks configured (must disambiguate).
# Non-zero = at least one check failed/cancelled.
gh pr checks "$PR_NUMBER" --watch
WATCH_RC=$?

# Disambiguate the no-CI case from real success.
CHECK_COUNT=$(gh pr checks "$PR_NUMBER" --json bucket --jq 'length')

if [ "$CHECK_COUNT" = "0" ]; then
  echo "No CI checks configured — record in final report and recommend adding CI"
elif [ "$WATCH_RC" -ne 0 ]; then
  echo "CI failed (watch exit $WATCH_RC)"; exit 1
else
  echo "CI green"
fi
```

**Fallback (if `--watch` cannot run):** poll until all checks reach a terminal state, then assert the bucket set is a subset of `{pass, skipping}` (allow-list, not deny-list — an unknown future bucket value must fail closed). Use gh's normalized `bucket` field, not raw `state` values, to avoid missing edge states like `NEUTRAL`, `ACTION_REQUIRED`, or lowercase legacy commit-status values.

**gh exit-code contract:** per gh's own documentation, `gh pr checks` exits 0 when all checks terminal-passed, 1 when at least one check terminal-failed, 8 when at least one is still pending, and other values for tool errors (auth, network, rate-limit). Both 0 and 1 are terminal — the fallback's assertion block disambiguates pass from fail via the bucket set. 8 means continue polling. Anything else means gh itself couldn't determine state.

```bash
while true; do
  BUCKETS=$(gh pr checks "$PR_NUMBER" --json bucket --jq '[.[].bucket] | unique')
  RC=$?
  echo "CI buckets: $BUCKETS"
  case "$RC" in
    0|1) break ;;                                 # 0 = all pass, 1 = at least one failed; both terminal — assertion classifies
    8) sleep 20 ;;                                # at least one pending — keep polling
    *) echo "gh pr checks errored (rc=$RC) — cannot determine CI state"; exit 1 ;;
  esac
done

# Three terminal cases: empty (no CI), all allow-list (green), or anything else (red).
if [ "$BUCKETS" = "[]" ]; then
  echo "No CI checks configured — record in final report and recommend adding CI"
elif echo "$BUCKETS" | jq -e 'all(. == "pass" or . == "skipping")' >/dev/null; then
  echo "CI green"
else
  echo "CI not all-green: $BUCKETS"; exit 1
fi
```

If the exit is non-zero (either via `--watch` or the explicit assertion): diagnose from CI logs (`gh run view <run-id> --log-failed` or `gh pr checks "$PR_NUMBER"`), dispatch a fix, **re-run Step 5.5's full validation matrix** (the fix can regress local checks), push, and re-watch. Do NOT report success on a red PR. Do NOT leave the watch running while moving on to another task — CI failure is an actionable blocker that takes precedence.

If the block exits with the "No CI checks configured" message, record that in the final report so the user knows local validation was the only gate, and recommend they add CI.

<!-- CANONICAL: shared/compass-protocol.md -->
**Compass emit (after `gh pr checks --watch` returns green):**

Run `compass update` (provisional arc-closure only). Do NOT emit `last_meaningful_commit` — CI green does not mean merged; the subsequent `/merge-pr` invocation writes the SHA. The `next_move` value comes from the caller's `--value` argument if provided, otherwise preserve the existing `next_move` (omit `--set next_move` entirely), or pass an empty string if neither.

```bash
# If caller provided a next_move value:
python scripts/compass.py update \
  --set current_arc --value '' \
  --set next_move --value '<caller-provided-or-empty>'

# If no next_move value was provided by caller, omit --set next_move
# so the existing value is preserved:
python scripts/compass.py update \
  --set current_arc --value ''
```

Then: If using a worktree, clean it up (Step 7)

#### Option 3: Keep As-Is

<!-- Options 3 and 4 intentionally emit no compass update — work is neither merged nor CI-green. -->

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
- **Fix:** Always run crucible:temper before presenting options. The orchestrator's lightweight review during execution is not sufficient.

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
- Mask a non-zero exit code without interpreting it against the tool's documented contract (e.g., `|| true`, `2>/dev/null`). Known non-failure non-zero codes must be matched to their meaning — `gh pr checks` exit 8 is "checks pending," not failure. When a tool's contract is unclear, treat non-zero as failure.
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
- [ ] Post-push CI monitoring completed green (Option 2 only)

**If any checkbox is unchecked, STOP. Go back and execute the missed gate.**
