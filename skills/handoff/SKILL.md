---
name: handoff
description: Write a handoff doc for the next session — either continuing the current arc, or proposing the natural next pickup if the current arc is wrapping up.
origin: crucible
---

# Handoff

Write a handoff document so a fresh agent (with no memory of this conversation) can pick up where we left off.

**Skill type:** Rigid — follow the process; omit-over-fill is preferred over padding.

**Execution model:** Direct execution by the orchestrator. No subagent dispatch.

**Announce at start:** Output `[handoff] Writing handoff document...` before any processing.

**Do not start or continue the work itself.** Your only job here is to produce the handoff file. If you notice something that needs doing, write it as an open question — don't go fix it.

## Step 0 — Nothing-to-hand-off check

Before writing anything, sanity-check that there's actually something to hand off. Run these sub-steps in order:

1. **Git detect.** Run `git rev-parse --is-inside-work-tree`. If it fails (not a git repo), ask the user where to write the file and what scope counts as "the project," then proceed using whatever they say. Skip git-specific verification steps in the rest of the process when in this mode. **This step always runs first regardless of `$ARGUMENTS`.**
2. **Argument check.** If `$ARGUMENTS` (see bottom of this file) is non-empty, treat it as sufficient evidence of an arc and skip step 3. Proceed to Mode selection.
3. **Work-existence check.** Is there session work, in-flight changes (`git status` shows modifications/staged), recent commits on a non-default branch, or an active line of investigation in the conversation? If **none of the above** apply (fresh session, clean tree, no real conversation history): tell the user there's nothing to hand off, suggest they invoke `/handoff` again after doing some work, and **stop**. Do not create a file.

## Two modes — pick one

Survey the current session and the project state, then decide:

**(A) Continuation handoff** — when there's clearly an in-progress arc:
- Mid-feature, mid-PR, mid-debug, mid-refactor — anything with concrete next steps
- The current ticket/issue isn't done yet
- A pipeline (build/QG/inquisitor/etc.) is paused mid-flight
- The user paused work but the line of investigation is active

**(B) Backlog handoff** — when the current arc is genuinely wrapping up:

If you're in mode A but want to mention upcoming-pickup candidates, add a brief "Next on deck" subsection to the Continuation handoff — don't switch modes.

- Just merged the last item in a milestone, epic, or wave
- The remaining open items in the active scope are out of scope for engineering (design/balance/content)
- The user just said "we're done with X" or similar
- We hit a natural decision point (e.g., "pivot to a different track")

When in doubt between (A) and (B), pick (A) — losing context is more costly than losing pickup recommendations.

## What goes in a Continuation handoff

Lead with **what to do next** — a fresh agent should be able to start the very next concrete action within 60 seconds of reading. Then layer in the context they need to act sensibly.

Sections to consider, in this order. **Skip any section that would only contain restated generalities or filler — empty omission is preferred over padding.** "Required" means "include if there's something real to put in it."

1. **Goal** — one line. What is the next agent trying to accomplish?
2. **State snapshot** — branch, last commit SHA, what's merged, what's in-flight, what's blocked
3. **Next concrete action** — the literal first thing to do (e.g., "run X, then Y based on its output")
4. **Suggested approach** — how to structure the work, ordered steps, gotchas to watch for
5. **Standing directives** — preferences/constraints from this session that the next agent must respect (TDD, MCP tools, no-skip QG, PR workflow, etc.). Pull from project `CLAUDE.md` and `MEMORY.md` if those exist; otherwise capture from conversation.
6. **Recovery pointers** — where to read more (memory files, cartographer, prior handoffs, related issues/PRs)
7. **Open questions / decisions deferred** — anything the user and current agent left undecided that the next agent shouldn't quietly choose for them

## What goes in a Backlog handoff

Lead with **what just shipped** so the next agent understands what's now stable. Then propose pickups, ordered by what makes the most sense to do next given the actual state of the codebase and project.

Same omit-over-filler rule applies.

1. **What just shipped** — the closing arc, in plain terms. Link the PRs/issues/branches.
2. **Why we're at a natural break** — the reasoning that prompted backlog mode (milestone code-complete, epic done, decision pivot, etc.)
3. **Backlog candidates** — survey open work in the relevant scope. For each candidate:
   - Identifier (issue number, ticket ID, TODO file path) + title + one-line summary
   - Why it's a sensible next pickup (size, scope alignment, dependency status)
   - What it would NOT be a good fit for (so the user can rule it out fast)
4. **Recommended order** — short ranked list with the rationale for the top pick
5. **Pointers** — anything else the next agent or user should read before choosing

## Process

1. **Read the room.** Survey the conversation, recent git log, recent PRs/issues, and the project's `MEMORY.md` / `CLAUDE.md` (if present) to understand current state.

   For mode B, also identify the **scope** of the just-shipped arc by reading the most recent merged PRs/commits and the tickets they close. State the inferred scope (milestone, epic, label, or topic name) explicitly at the top of the handoff doc. If the scope is genuinely ambiguous (multiple plausible milestones), surface 2-3 candidates and ask the user which to use before continuing.

2. **Decide A vs B.** State your choice and one-line reason at the top of the doc.

3. **Source the backlog (mode B only).** Detect the project's issue tracker before querying:
   - Check `git remote -v`. If `github.com` and `gh` is on PATH → `gh issue list`.
   - If `gitlab.com` and `glab` is on PATH → `glab issue list`.
   - When invoking `gh issue list` / `glab issue list`, filter by the milestone, epic label, or topic identified in step 1 (e.g., `gh issue list --milestone 'Hex Phase 3'` or `--label epic:foo`). Only fall back to an unfiltered list if no scope can be derived from the session.
   - Otherwise: ask the user where the backlog lives, or fall back to surveying TODOs (`docs/plans/`, `docs/todo.md`, `TODO.md`, in-tree `// TODO:` comments). **Never invent issue numbers** — if you can't find a real source, say so and ask the user.

4. **Verify load-bearing claims, with a budget.** Spend at most a handful of tool calls verifying things you're about to cite (current branch name, last commit SHA, PR numbers, file paths, function names). If a claim can't be cheaply verified, mark it `(unverified)` in the doc rather than digging deeper. Don't audit the entire codebase.

5. **Write the file.** Detect the project's handoff convention before choosing a path:
   - Check for an existing `docs/handoffs/`, `handoffs/`, or `.handoffs/` directory in the project root. If one exists, use it and match the filename style of the most recent file in that directory (`ls -t | head` it).
   - If none exists, default to `docs/handoffs/YYYY-MM-DD-<short-topic-slug>.md`. Create the directory if needed and note the new convention in the doc itself.
   - For backlog handoffs, the topic slug should signal the scope (e.g., `<milestone-or-epic>-backlog`).
   - **If a same-day, same-topic file already exists**, do not clobber and do not append. Instead, create a new file with `-pt2` (or `-pt3`, etc.) appended to the slug, and reference the prior file's path in the new file's first paragraph. The `HANDOFF:` line then points unambiguously at the freshest content.

6. **Output the file path** — see Output Contract below.

## Output Contract

The user explicitly asked for the file location in the response. Make it impossible to miss:

- Print a brief 1–3 sentence summary of what's in the file (mode A or B, key topic).
- Then end your response with **exactly one line**, on its own, with no surrounding code fence or trailing commentary. Do NOT wrap the line in backticks or a code fence — emit it as plain text. Format: `HANDOFF: <absolute path>`. Example: `HANDOFF: /home/user/project/docs/handoffs/2026-04-19-foo.md`
- "Absolute path" means either (a) the path your file-write tool returned, OR (b) `<repo-root>/<relative-path>` where repo-root comes from `git rev-parse --show-toplevel`. Native path separators are fine (Windows backslashes are acceptable). In the non-git fallback mode (see Step 0), use whatever absolute path the user directed you to write to.
- If you skipped writing a file (per Step 0), end with: `HANDOFF: (none — nothing to hand off)` — same no-fence rule applies.

## Quality bar

- A handoff that the next agent has to ask the user "what was I doing?" is a failed handoff.
- Every claim that names a file, function, branch, or PR is a claim the file/function/branch/PR existed when the handoff was written. Verify load-bearing ones (within the budget in step 4); mark unverified ones as `(unverified)`.
- No filler. If a section has nothing real to put in it, omit it.
- Don't invent context. If you don't know whether a decision was made, write the open question rather than guessing the answer.
- Use absolute dates (e.g., `2026-04-19`), not relative (`yesterday`, `this week`) — handoffs are read days or weeks later.

---

Additional user instructions for this handoff (may be empty — if empty, proceed with the defaults above; if non-empty, treat as scoping/emphasis hints, not as a replacement for the process):

$ARGUMENTS
