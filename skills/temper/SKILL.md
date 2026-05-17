---
name: temper
description: Iteratively review code changes for production readiness through fresh-eyes review loops. Use when completing tasks, implementing major features, or before merging — including when the user says "review this PR", "review my changes", "code review", "check the diff", or "is this ready to ship". Works on PRs from any forge (GitHub, GitLab, Bitbucket, self-hosted) or on raw git SHA ranges.
---

# Temper

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Like tempering steel after forging — iterative heat-and-quench cycles that set final hardness and elasticity — `/temper` runs successive fresh-eyes code reviews until the artifact converges. Each round dispatches a new reviewer with no prior-round context (no anchoring). The loop exits when a fresh reviewer returns clean.

**Core principle:** Review early, review often. Fresh eyes every round.

**Renamed from `/code-review` (2026-05-17)** to avoid collision with Claude Code's built-in `/review` command. Same iteration behavior; the argument shape and platform-agnostic PR support are new.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## Invocation

```
/temper                          # auto-detect: current branch's PR if one exists, else origin/main..HEAD
/temper 259                      # PR identifier on the current forge
/temper https://...              # PR URL on any forge
/temper main..HEAD               # explicit SHA range
/temper a1b2c3..d4e5f6           # explicit SHA range
```

**Argument shape:** `[PR-id-or-URL | <base>..<head>]`. No argument means auto-detect.

## How to Request

### Step 1: Resolve the review scope (forge-agnostic)

Determine what to review based on the argument:

1. **PR number or URL** — fetch metadata (title, body, base ref, head ref) using whatever CLI is available for the detected forge. Detect forge from `git remote get-url origin`:
   - `github.com` → try `gh pr view <id> --json title,body,baseRefName,headRefName,author`
   - `gitlab.com` or self-hosted GitLab → try `glab mr view <id>` (or REST)
   - `bitbucket.org` → try `bb pr view <id>` (or REST)
   - Other / unavailable CLI → fetch the PR head via `git fetch <remote> <head-ref>` and proceed with the diff alone; ask the user to paste the description if they want it factored into the review brief

   Map the fetched metadata to `<base>..<head>` SHA range using `git rev-parse <baseRef>` and `git rev-parse <headRef>`.

2. **SHA range** (argument contains `..`) — use as-is. Metadata is empty: no PR description, just the diff.

3. **No argument** — try forge-CLI detection of the current branch's PR. If found, treat as case 1. Otherwise default to `origin/main..HEAD` (or the merge base of the current branch and main).

**Anti-rationalization:** don't hardcode `gh` calls. The skill is forge-agnostic — the CLI used is whichever the environment makes available. Skip metadata gracefully on missing CLIs rather than failing the review.

### Step 2: Dispatch the temper reviewer

Use the Task tool with `subagent_type="general-purpose"`. Fill in the template at `temper-reviewer.md` in this directory and pass it as the subagent prompt.

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` — derived from PR title if available, else `Changes in <base>..<head>`
- `{PLAN_OR_REQUIREMENTS}` — PR body if available, else `(none provided — review against general production-readiness criteria)`
- `{BASE_SHA}` / `{HEAD_SHA}` — resolved SHA range from Step 1
- `{DESCRIPTION}` — one-line summary (PR title or "changes on branch X")

### Step 3: Act on feedback and iterate

- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if the reviewer is wrong (with reasoning)
- **Record the issue count** (Critical + Important only — Minor doesn't count)

### Step 4: Re-review after fixes (iterative loop)

After fixing Critical/Important issues, dispatch a **NEW fresh temper reviewer subagent** (never the same one — fresh eyes, no anchoring). Compare issue count to prior round:

- **Strictly fewer Critical+Important issues:** Progress — fix and re-review again.
- **Same or more Critical+Important issues:** Stagnation — escalate to user with findings from both rounds.
- **No Critical/Important issues:** Clean — proceed.
- **Architectural concerns:** Immediate escalation regardless of round.

**Fresh reviewer every round.** Never pass prior findings to the next reviewer.

### Step 5 (optional) — Post findings to the PR

If the user explicitly asks ("post this to the PR", "leave a review comment"), publish using whichever CLI fits the forge:

- GitHub → `gh pr review <id> --comment --body-file <findings.md>`
- GitLab → `glab mr note <id> -m "$(cat findings.md)"`
- Bitbucket → `bb pr comment <id> --file findings.md` (or REST)
- Unavailable / unknown forge → output the formatted body for the user to paste

Never post without an explicit user instruction. Findings live in the user's session by default.

## External Model Review (Optional)

After dispatching the host temper subagent, optionally call the `external_review` MCP tool for an independent second opinion from external models. The preferred pattern is: dispatch the host reviewer as a background Agent first, call `external_review`, then collect host results — this gives effective parallelism where background agents are available.

**Invocation:**

Call `external_review` with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: the same diff and requirements context given to the host reviewer
- `skill`: `"temper"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "temper", "round": N}` (traceability; N is the current review round)

**Per-skill toggle:** The server checks the `skill` argument against `skills.temper` in the external review config. If `false`, the server returns `unavailable`.

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

## Cross-Reference to Deep Cloud Review

For GitHub PRs only, Claude Code's built-in `/ultrareview <PR>` runs a deeper multi-agent review in a cloud sandbox. After a local `/temper` round, suggest `/ultrareview` to the user when:
- The local round found significant issues across multiple categories, OR
- The user wants a second opinion before merge on a high-stakes change

`/ultrareview` is GitHub-specific; do not suggest it for GitLab/Bitbucket/other-forge PRs.

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request review before proceeding.

[Resolve scope]
- No PR yet; default to origin/main..HEAD
- BASE_SHA=$(git rev-parse origin/main)
- HEAD_SHA=$(git rev-parse HEAD)

[Dispatch fresh temper reviewer — Round 1]
  Issues: 2 Important (missing progress indicators, no error handling for empty input)
  Minor: 1 (magic number)

You: [Fix both Important issues]

[Dispatch NEW fresh temper reviewer — Round 2]
  Issues: 1 Important (error handling catches wrong exception type)

Round 2 (1 issue) < Round 1 (2 issues) → progress, continue

You: [Fix the exception type]

[Dispatch NEW fresh temper reviewer — Round 3]
  Issues: 0 Critical/Important
  Minor: 1 (could use named constant)

Clean — proceed to Task 3.
```

## Test Alignment

When `/temper` is used standalone (not from build, debugging, or finish — those pipelines handle test-coverage automatically), the caller should consider dispatching `crucible:test-coverage` after temper completes if behavioral changes were made.

This is especially valuable when:
- The review identified behavioral changes that might affect existing tests
- The diff modifies functions/methods that have dedicated test files
- The review noted "tests should be updated" without specifying which ones

## Integration with Workflows

**Build Pipeline:**
- Temper after EACH task
- Test-coverage audit after temper (handled by build pipeline)
- Catch issues before they compound
- Fix before moving to next task

**Standalone Plan Execution:**
- Temper after each batch (3 tasks)
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Temper before merge
- Temper when stuck
- Consider `crucible:test-coverage` after temper if behavioral changes were made

## Red Flags

**Never:**
- Skip temper because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback
- Skip re-review after fixes ("the fixes look fine")
- Reuse the same reviewer subagent across rounds
- Pass prior findings to the next reviewer
- Hardcode `gh` (or any single forge's CLI) in the dispatch path — temper is forge-agnostic

**If the reviewer is wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: `temper/temper-reviewer.md`
