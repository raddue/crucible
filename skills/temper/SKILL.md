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

## Non-Goals

Temper reviews **code diffs only**. Use a different skill for:

- **Design docs / plans / concepts** — use `/audit` or `/red-team`.
- **Multi-lens parallel review** (4+ analytical lenses on one artifact) — use `/audit`.
- **Executable cross-component bug-hunting** (adversarial tests against assembled features) — use `/inquisitor`.
- **Security-specific review** with attacker-perspective coverage — use Claude Code's built-in `/security-review` or `/siege` for a deep multi-agent security audit.
- **Iterative red-team of *any* artifact** (not just code diffs) — use `/quality-gate`.

## Relationship to `/quality-gate`

Temper and quality-gate share a loop shape (fresh reviewer each round, stagnation detection, escalate on architectural concerns). They differ in scope and caller:

- **`/quality-gate`** is the generic iterative red-team loop over *any* artifact (design, plan, code, hypothesis, mockup). It is invoked **by artifact-producing skills** as their terminal gate.
- **`/temper`** is the code-diff-specific instance — same loop shape, plus a code-review checklist, plus forge integration (PR metadata, optional post-back). It is **user-facing** for ad-hoc review and is called by build / debugging / finish on diffs.

When in doubt: if the artifact is a code diff, use temper. If it is anything else (or you are inside an artifact-producing skill writing the gate), use quality-gate.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## Dependencies

| Component | Required? | Purpose | Fallback if missing |
|---|---|---|---|
| `git` | Required | Diff resolution, SHA range, default-branch detection | None — abort with clear error |
| Forge CLI (`gh` / `glab` / `bb`) | Optional | PR metadata fetch + optional Step 5 post-back | Probe in order; if all missing, fall through to git-plumbing and ask user for description |
| `crucible-consensus` MCP server | Optional | External-model second opinion via `external_review` | Skip silently |
| `crucible:test-coverage` | Optional | Test-alignment audit when behavioral changes are made | Skip; recommend manually |
| `crucible:checkpoint` | Optional | Pre-fix rollback target (used by build's wrapping) | Skip silently |

## Invocation

```
/temper                          # auto-detect (see Step 1 case 3)
/temper 259                      # PR identifier on the current forge
/temper https://...              # PR URL on any forge
/temper main..HEAD               # explicit SHA range
/temper a1b2c3..d4e5f6           # explicit SHA range
/temper 259 max_rounds=8         # override default 5-round circuit breaker
/temper 259 max_rounds=8 external_review=skip  # skip redundant external_review on re-invocation
```

**Argument shape:** `[PR-id-or-URL | <base>..<head>] [max_rounds=<N>] [external_review=skip]`. No argument means auto-detect.

## How to Request

### Step 1: Resolve the review scope (forge-agnostic)

Determine what to review based on the argument:

**Case 1 — PR number or URL.** Fetch metadata (title, body, base ref, head ref). Forge detection is **CLI-probe order, not hostname-literal** (covers GitHub Enterprise Server and any other GH-flavored host). When the argument is a URL, parse the forge from the URL host first and use **only** the matching CLI (handles fork workflows where `origin` and `upstream` live on different forges). When the argument is a bare PR number, probe CLIs in order against the current `origin`.

**If the argument is a URL,** parse the forge from the URL host and try only the matching CLI:
- `github.com` or any host `gh` authenticates against (GHE) → `gh pr view <id> --json title,body,baseRefName,headRefName,author --repo <owner/repo-from-URL>`
- `gitlab.com` or any GitLab host → `glab mr view <id> --repo <project-from-URL>`
- `bitbucket.org` or any Bitbucket host → `bb pr view <id> --repo <slug-from-URL>`
- Unknown host → fall back to git plumbing (`git fetch <remote> <head-ref>`); ask the user to paste the description.

**If the argument is a bare PR number,** try CLIs in order against the current `origin`:
1. `gh pr view <id> --json title,body,baseRefName,headRefName,author` — covers GitHub and GitHub Enterprise (any host `gh` is authenticated against; verify with `gh auth status --hostname <host>` if needed).
2. `glab mr view <id>` — covers GitLab and self-hosted GitLab.
3. `bb pr view <id>` (or REST) — covers Bitbucket.
4. None of the above succeeded → fall back to git plumbing: `git fetch <remote> pull/<id>/head` (GitHub-style ref) or `git fetch <remote> merge-requests/<id>/head` (GitLab-style); ask the user to paste the description if they want it factored in.

**Distinguish CLI errors from missing CLIs.** A CLI that exits non-zero with "404 / PR not found / authentication required" is *not* a missing-CLI fallback path. Surface the error to the user (e.g., "gh found the PR but auth failed — re-authenticate or paste the diff manually") and pause for instruction. Falling through silently on a CLI error would dispatch a review against the wrong scope.

Map the fetched metadata to `<base>..<head>` SHA range using `git rev-parse <baseRef>` and `git rev-parse <headRef>`.

**Case 2 — SHA range** (argument contains `..`). Use as-is. Metadata is empty: no PR description, just the diff.

**Case 3 — No argument** (auto-detect). Precedence (first match wins):
1. If HEAD is detached (`git symbolic-ref -q HEAD` returns non-zero), **require an explicit argument** — auto-detect is ambiguous in detached state. Abort with a one-line instruction telling the user to pass a SHA range.
2. Try forge-CLI detection of the current branch's PR. If found, treat as Case 1. If the CLI is present but errors (auth-fail, 403, rate-limit, network), surface the error and pause per Case 1's distinguish-error-from-missing rule. Only the unambiguous "no PR for this branch" result advances to step 3.
3. Resolve the upstream default branch via `git symbolic-ref refs/remotes/origin/HEAD` (handles `main`, `master`, `trunk`, or anything else the remote uses). Use `<that-ref>..HEAD` as the SHA range.
4. If no `origin/HEAD` is set (rare; usually means the remote was never properly cloned), check which of `origin/main`, `origin/master`, `origin/trunk` exist. If exactly one exists, use its merge base with HEAD and narrate the fallback (`"[temper] origin/HEAD unset; fell back to origin/<name> as the only main-like ref present"`). If **more than one** exists (legacy repos with both `origin/main` and `origin/master`), **abort** with: `"Multiple main-like refs found (origin/main, origin/master). Pass an explicit <base>..<head> range — the model has no signal which one this branch was cut from."` If none exist, abort with the existing "Cannot determine default branch" message.

**Anti-rationalization:** don't hardcode `gh` calls in the dispatch path. The skill is forge-agnostic — the CLI used is whichever the environment makes available. Skip metadata gracefully on missing CLIs; surface explicit errors on present-but-failing CLIs.

### Step 1.5: Diff preflight (mandatory — runs before dispatch)

Classify the resolved diff before spending a reviewer dispatch on it. Empty / binary / submodule-only diffs are recognized and handled explicitly so they cannot produce silent false-Clean verdicts.

Run `git diff --numstat <base>..<head>` and inspect:

- **Empty diff** (no entries): short-circuit. Return `Clean — no changes to review` immediately. Do not dispatch a reviewer. Callers (build, finish) see this as "Clean" but with `Reason: empty-diff` distinguishable from a substantive Clean.
- **Binary-only diff** (every entry has `-\t-\t<path>` indicating binary): note in `{DESCRIPTION}` that the diff is binary-only and the reviewer cannot inspect content. The reviewer should not produce a Clean verdict against unreviewable content; it should emit `Verdict: Architectural Concern — binary-only diff requires human review`.
- **Submodule pointer-only diff** (changes are entirely in `.gitmodules` or submodule SHA pointers): note in `{DESCRIPTION}` and instruct the reviewer to flag a Suggestion to inspect the submodule contents separately. Do not produce a spurious Clean.
- **Mixed text + binary**: include the text portion normally; note the binary files in `{DESCRIPTION}` so the reviewer doesn't pretend to have read them.
- **Diff too large** (>5,000 added+deleted lines per `numstat`): warn the user and offer to split per-commit or per-file. If the user proceeds anyway, note the over-cap in `{DESCRIPTION}` and dispatch with a context-window degradation warning. This is a soft cap, not a hard block. **Non-interactive callers** (build / debugging / finish dispatching `/temper`): on >5,000-line diffs, proceed automatically with the over-cap note in `{DESCRIPTION}` and emit a `degraded-context` flag in the round metadata. Interactive (standalone) callers retain the offer-to-split flow above.

**Empty-diff caller contract.** Pipeline callers (build / debugging / finish) MUST treat `Reason: empty-diff` as a soft-warn — surface to the user ("temper found no changes between BASE and HEAD; confirm this is intended") before proceeding past the gate. The most common cause is uncommitted work, a wrong base, or detached-HEAD post-rebase. Ad-hoc / standalone callers may proceed silently (the user invoked /temper knowing the state).

### Step 2: Dispatch the temper reviewer

Write the filled template to a dispatch file at the path defined by `shared/dispatch-convention.md` (one file per dispatch-id; see Per-invocation dispatch-id below). Then dispatch a `general-purpose` Task subagent that reads that file as its prompt. Do not paste the filled template directly into the Task tool prompt — the disk-mediated dispatch is what gives the dispatch-id per-invocation uniqueness on disk.

**Placeholders** (four slots, all must be filled before dispatch — these match the section slots in `temper-reviewer.md` exactly):
- `{DESCRIPTION}` — one-line summary of what was implemented. PR title if available, else `Changes in <base>..<head>` / `changes on branch X`. Augment with preflight notes (binary, submodule, oversized) when applicable.
- `{PLAN_REFERENCE}` — PR body / plan / requirements if available, else `(none provided — review against general production-readiness criteria)`.
- `{BASE_SHA}` / `{HEAD_SHA}` — resolved SHA range from Step 1.

Earlier drafts listed `{WHAT_WAS_IMPLEMENTED}` and `{PLAN_OR_REQUIREMENTS}` as separate placeholders. Those names were redundant aliases for `{DESCRIPTION}` and `{PLAN_REFERENCE}` — the template now uses the canonical names in both prose and section slots, so there is exactly one slot per concept.

**Per-invocation dispatch-id** (concurrency isolation). Every `/temper` invocation generates a unique dispatch-id at Step 1: `temper-YYYYMMDDTHHmmss-<6-char-nonce>`. Generate via a cryptographic RNG (e.g., `python -c 'import secrets; print(secrets.token_hex(3))'` for 6 hex chars). If the dispatch file path already exists on disk, regenerate the nonce and retry — never overwrite. The dispatch file path and the `metadata.dispatch_id` field both include this id, so concurrent invocations (e.g., user-initiated overlapping with build's Phase 4) cannot collide. Round numbering remains per-invocation; the dispatch-id disambiguates `(skill, round)` traceability tuples in the external_review MCP and in any session-log consumers.

#### Freshness Boundary

Temper's core principle ("fresh reviewer every round, no anchoring") is convention-plus-mechanism. The mechanism: the reviewer subagent receives **only these inputs** and nothing else:

- The diff itself (`git diff <base>..<head>`)
- The four placeholders above (`{DESCRIPTION}`, `{PLAN_REFERENCE}`, `{BASE_SHA}`, `{HEAD_SHA}`)
- The reviewer template (`temper-reviewer.md`) and its canonical includes (`shared/reviewer-common.md`)

The reviewer **must not** receive:
- Prior-round findings (any round, any reviewer)
- PR review comments (only PR title + body are pulled via the forge CLI; comments are out of scope)
- Fixup-commit subjects and other commit messages — the reviewer subagent is explicitly instructed (in `temper-reviewer.md`) to read diff content only, not `git log` / commit messages. This shifts the boundary from orchestrator-side redaction (unenforceable, since the reviewer runs its own `git` commands) to reviewer-side discipline.
- Any out-of-band notes from the user "for the reviewer's awareness"

This boundary is what makes round-N independent of round-N-1. Step 5's optional post-to-PR happens *after* a round completes; on subsequent rounds, the reviewer is dispatched against the *new* diff, and PR comments (which now contain prior findings) are excluded from the metadata fetch.

### Step 3: Act on feedback and iterate

- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor and Suggestion issues for later (see Severity / Verdict Vocabulary below for how these map)
- Push back if the reviewer is wrong (with reasoning)
- **Record the issue count** (Critical + Important only — Minor and Suggestion do not count toward convergence)

### Step 4: Re-review after fixes (iterative loop)

After fixing Critical/Important issues, dispatch a **NEW fresh temper reviewer subagent** (never the same one — fresh eyes, no anchoring). Compare issue count to prior round.

Evaluate in this order; first match wins:
- **Architectural concerns:** Immediate escalation regardless of round.
- **No Critical/Important issues:** Clean — proceed (terminate the loop).
- **Round number reaches `max_rounds`:** Circuit-breaker — escalate to user with full round history regardless of trajectory (see Max-round circuit breaker subsection below for the message format).
- **Strictly fewer Critical+Important issues than prior round:** Progress — fix and re-review again.
- **Same or more Critical+Important issues than prior round, AND prior round was non-zero:** Stagnation — escalate to user with findings from both rounds.

**Fresh reviewer every round.** Never pass prior findings to the next reviewer.

#### Max-round circuit breaker

The loop is bounded by **5 rounds** by default. A reviewer that produces a strictly-decreasing-but-slow C+I count (e.g., 8 → 7 → 6 → …) would otherwise burn fresh dispatches indefinitely. At round 5 without convergence, escalate to the user with the full round history regardless of trajectory:

> "Temper reached the {max_rounds}-round cap without a clean verdict. Trajectory: [N₁, N₂, …, N_{max_rounds}]. The fix cycle is making progress but slowly. To extend, re-invoke `/temper <scope> max_rounds=N` — this starts a **fresh review loop** with a higher cap (the prior trajectory is informational only; round counting restarts at 1, and the new reviewer has no anchoring from prior rounds). If the remaining issues appear structural rather than fixable in another loop, escalate to design / plan instead."

Callers (build Phase 4) treat round-5 escalation as a soft block: the diff is not approved, the user decides whether to extend, refactor, or accept the remaining findings. The default cap is overridable via trailing skill argument `max_rounds=<N>` for genuine multi-pass remediation; defaults to 5 to keep runaway protection on by default.

#### Done When

- **Clean exit:** A fresh round returns 0 Critical, 0 Important. Verdict `Clean`. Caller may proceed.
- **Stagnation exit:** A round's Critical+Important count is ≥ the prior round's count (no strict decrease) AND the prior round's count was non-zero. Verdict `Stagnation`. Caller escalates to user.
- **Architectural exit:** Any round emits `Architectural Concern`. Verdict `Architectural Concern`. Caller escalates immediately regardless of round number.
- **Circuit-breaker exit:** Round 5 reached without convergence. Verdict `Max-Rounds`. Caller escalates with full round history.

### Step 5 (optional) — Post findings to the PR

This step is an **output convenience, not part of the review contract** — findings are complete after Step 4 regardless of whether they're posted. It exists for users who want the local review surfaced on the PR for asynchronous collaborators.

If the user explicitly asks ("post this to the PR", "leave a review comment"), publish using whichever CLI fits the forge:

- GitHub → `gh pr review <id> --comment --body-file <findings.md>`
- GitLab → `glab mr note <id> -m "$(cat findings.md)"`
- Bitbucket → `bb pr comment <id> --file findings.md` (or REST)
- Unavailable / unknown forge → output the formatted body for the user to paste

**Confirm success explicitly.** Check the CLI's exit code. On non-zero exit, classify the failure mode and respond per the table below — do not silently skip:

| Failure mode | Response |
|---|---|
| Auth-fail (`gh auth status` failure / token expired) / rate-limit (403) / network error | Paste-mode with retry guidance: "Posting failed with `<error>` — re-authenticate / wait and retry, or paste the body manually below." |
| PR closed-without-merge | Paste-mode with conditional guidance: "PR is closed; if you intend to reopen, paste the body. Otherwise the findings remain in your session." |
| PR merged or deleted | Do **not** offer paste-mode. Surface the findings locally: "The PR is no longer postable (merged / deleted). Findings remain in your session for reference." |

Never post without an explicit user instruction. Findings live in the user's session by default.

## Severity / Verdict Vocabulary

The reviewer template (`shared/reviewer-common.md`) uses a 4-tier severity scale and a parallel verdict vocabulary. This section pins the canonical mapping the temper orchestrator uses to compute convergence.

### Severity mapping

| Reviewer emits | Temper counts as | Affects convergence? |
|---|---|---|
| **Critical** | Critical | Yes — must reach 0 to exit Clean |
| **Important** | Important | Yes — must reach 0 to exit Clean |
| **Minor** | Minor | No — informational, surfaced to user |
| **Suggestion** | Minor | No — folded into Minor bucket for orchestrator purposes; preserved verbatim in the report |

**Why fold Suggestion into Minor?** Reviewers sometimes soften real bugs to "Suggestion" as an LLM diplomacy pattern. Folding ensures these are surfaced to the user (not silently dropped) without contaminating the convergence math. If the user identifies a Suggestion that should have been Critical/Important, they can re-dispatch with an explicit prompt to re-grade.

### Verdict mapping

The reviewer template also emits an overall verdict. Two parallel vocabularies exist for historical reasons; temper recognizes both as synonyms:

| Reviewer emits | Temper treats as |
|---|---|
| **Clean** ≡ **Approved** | Clean (exit) |
| **Issues Found** ≡ **Needs Fixes** | Issues Found (continue loop) |
| **Architectural Concern** ≡ **Escalate** | Architectural Concern (immediate escalation) |

The canonical (preferred) names are the left column. The right-column synonyms remain accepted to avoid breaking older reviewer templates.

## External Model Review (Optional)

After dispatching the host temper subagent, optionally call the `external_review` MCP tool for an independent second opinion from external models.

**Preferred dispatch pattern:** dispatch the host reviewer as a background Agent first, call `external_review`, then collect host results — gives effective parallelism where background agents are available. If background agents are not available, run sequentially: host first (must complete; INV-1 below), then external. Do not call external_review first or in a fire-and-forget pattern that would block host result collection.

**Invocation:**

**Cadence:** external_review is called **once per `/temper` invocation, on Round 1** — to provide a second opinion on the initial finding set without multiplying external-API cost across the fix loop. Subsequent rounds rely on the fresh host reviewer alone.

**Re-invocation skip rule:** Re-invoking `/temper` via `max_rounds=N` after a stagnated run normally triggers another Round-1 external_review call. To avoid redundant external API spend on essentially-the-same diff, pass `external_review=skip` as a trailing skill argument. (No automatic same-diff detection — the spec does not define a persistent dispatch-id log across invocations, so skip is explicit-only.)

Call `external_review` with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: the same diff and requirements context given to the host reviewer
- `skill`: `"temper"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "temper", "round": N, "dispatch_id": "<from Step 2>"}` (traceability)

**Per-skill toggle:** The server checks the `skill` argument against `skills.temper` in the external review config. If `false`, the server returns `unavailable`. **Server hyphen-normalization:** `mcp-servers/crucible-consensus/server.py` normalizes hyphens to underscores in the skill name before lookup, so a hyphenated skill name (`red-team`) and its underscored form (`red_team`) resolve to the same toggle. Today temper has no hyphen — the contract works trivially — but the rule is documented here for future renames.

**Config-rename note for opt-out users.** The toggle key was renamed from `code_review` to `temper` on 2026-05-17. If you previously set `skills.code_review: false` to opt out, **rename the key to `skills.temper: false`** to preserve your opt-out. Otherwise the toggle inherits the default `True`.

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

For GitHub PRs only, Claude Code's built-in `/ultrareview <PR>` runs a deeper multi-agent review in a cloud sandbox. After a local `/temper` round, suggest `/ultrareview` to the user when **either** of these holds:

- The local round emitted findings in ≥2 distinct categories from the reviewer-common checklist (Architecture, Correctness, Quality, Testing, TDD Process, Production Readiness — see `shared/reviewer-common.md`), **OR**
- The user explicitly wants a second opinion before merge on a high-stakes change.

"Categories" means the reviewer-common checklist sections, not severity tiers — the trigger is breadth of issue surface, not depth of any single issue.

`/ultrareview` is GitHub-specific; **do not suggest** it for GitLab / Bitbucket / other-forge PRs.

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request review before proceeding.

[Step 1: Resolve scope]
- No argument given; HEAD is on branch `feat/verify`
- gh pr view (current branch) → no PR yet
- origin/HEAD → main; resolved range: origin/main..HEAD
- BASE_SHA=$(git rev-parse origin/main)
- HEAD_SHA=$(git rev-parse HEAD)

[Step 1.5: Preflight]
- numstat: 4 files changed, 87 added, 12 deleted — text diff, in-cap, proceed

[Step 2: Dispatch fresh temper reviewer — Round 1, dispatch-id temper-20260517T150500-a7f3c2]
  Issues: 2 Important (missing progress indicators, no error handling for empty input)
  Minor: 1 (magic number)

You: [Fix both Important issues]

[Step 4: Dispatch NEW fresh temper reviewer — Round 2]
  Issues: 1 Important (error handling catches wrong exception type)

Round 2 (1 issue) < Round 1 (2 issues) → progress, continue

You: [Fix the exception type]

[Step 4: Dispatch NEW fresh temper reviewer — Round 3]
  Issues: 0 Critical/Important
  Minor: 1 (could use named constant)

Verdict: Clean (0 Critical, 0 Important). Proceed to Task 3.
```

## Test Alignment

When behavioral changes were made, consider dispatching `crucible:test-coverage` after temper completes. This catches stale tests, missing coverage, or assertion drift introduced by the fixes.

**Caller context determines who runs it:**
- **Pipelines (build / debugging / finish):** the pipeline orchestrator dispatches `crucible:test-coverage` automatically — temper does not.
- **Standalone / ad-hoc:** the user (or whoever invoked `/temper` directly) is responsible for the hand-off. Recommend `crucible:test-coverage` when the review noted behavioral changes that might affect existing tests, when the diff modified functions with dedicated test files, or when the reviewer said "tests should be updated" without specifics.

This is the single canonical statement of the rule; the workflow sections below cross-link rather than restate.

## Integration with Workflows

**Build pipeline (Phase 4):** Temper runs after each task. Build dispatches `crucible:test-coverage` automatically (see Test Alignment).

**Standalone plan execution:** Temper after each batch (3 tasks). The user dispatches `crucible:test-coverage` afterward if behavioral changes were made.

**Ad-hoc development:** Temper before merge, when stuck, after a complex bug fix. The user dispatches `crucible:test-coverage` afterward if behavioral changes were made.

**Migration note — pre-rename retrospectives.** `crucible:forge` retrospectives written before 2026-05-17 are tagged with `code_review`. Forge's consult-past-lessons step does not auto-alias; if you want the old lessons to surface for `temper`, query both keys. (Out of temper's scope to fix; flagged here so users know.)

## Red Flags

**Never:**
- Skip temper because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback
- Skip re-review after fixes ("the fixes look fine")
- Reuse the same reviewer subagent across rounds
- Pass prior findings to the next reviewer (see Freshness Boundary)
- Hardcode `gh` (or any single forge's CLI) in the dispatch path — temper is forge-agnostic
- Silently fall through on a CLI **error** (vs missing-CLI) — surface the failure to the user
- Run past the 5-round circuit breaker without explicit user instruction
- Post to a PR without explicit user instruction
- Silently skip Step 5 on auth-fail / closed-PR / rate-limit — fall through to paste-mode

**If the reviewer is wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: `temper/temper-reviewer.md`
