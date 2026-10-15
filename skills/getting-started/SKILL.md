---
name: getting-started
description: Use when starting any conversation - establishes how to find and use skills, requiring skill activation before ANY response including clarifying questions (the conversation-start bootstrap protocol). Also the session-continuity hub - triggers on "compass", "current arc", "project state", "arc state", "where was I" (read/update/doctor/compress docs/compass.md); "retrospective", "forge", "consult past lessons", "propose skill improvements" (forge retrospective, feed-forward, 10+ retrospective mutation proposals); "handoff", "write a handoff", "end of session" (handoff doc); "recall", "session history", "what did I edit", "recall errors" (activity-index queries); and "skills available", "what skills are available?", "where do I start?", "what should I use for X?", "tour", "give me a tour of Crucible" (workshop catalog tour).
---

# Using Crucible Skills

## Session Context (Compass)

<!-- CANONICAL: shared/compass-protocol.md -->

Read current arc state before the dispatch table. Requires Python 3 (stdlib only, no install). Silent no-op on non-Crucible repos or missing compass file (the script's `read()` fast-returns empty on `FileNotFoundError`).

```bash
test -f scripts/compass.py && python scripts/compass.py read --compact 2>/dev/null || true
```

If the output is non-empty, print it verbatim so the user sees session-resume context. If the output contains `[STALE]`, surface that to the user. Do NOT emit `compass update` from this bootstrap step — the bootstrap reads only. Writes happen only through the lifecycle callers (`build`, `merge-pr`, `finish`) or an explicit user request handled via [compass.md](compass.md).

## Repo Memory

Read committed decisions and rules after compass state. Requires Python 3 (stdlib only); falls back to `grep`. This is L2 context, not authority over `CLAUDE.md`/`AGENTS.md` or accepted ADRs.

```bash
plugin_root="$(realpath "<this-skill-base-dir>/../..")"
python3 "$plugin_root/scripts/memory.py" read --limit 30 2>/dev/null \
  || { test -f docs/memory.md && grep -E '^- \[(decision|rule)\] ' docs/memory.md | tail -30; } \
  || true
```

## Bundled References

Compass, forge, handoff, recall, and the workshop tour live here as flat reference files; they are no longer separate skills, so `/compass`, `/forge`, `/handoff`, `/recall`, and `/workshop` do not exist as slash commands. Reach them by invoking `/getting-started` (or letting it auto-activate on the description triggers) with the request, e.g. `/getting-started handoff`, `/getting-started recall errors`, `/getting-started compass doctor`, `/getting-started retrospective`, `/getting-started tour`. Then read and follow only the matching file below — its mechanics are authoritative and unchanged.

**Invocation arguments.** Argument substitution applies only to this invoked body, never to reference files read afterward. Capture the invocation arguments here and hand them to the reference explicitly:

- Arguments (may be empty): $ARGUMENTS
- First word selects the reference when it names one (`compass`, `forge`/`retrospective`, `handoff`, `recall`, `workshop`/`tour`); otherwise route on the request text. The remaining words are that reference's **caller arguments**.
- If this line still shows a literal dollar-sign `ARGUMENTS` placeholder (no substitution happened, e.g. auto-activation or a harness without substitution), treat the arguments as **empty**.
- `handoff.md` reads caller arguments in Step 0 step 2 and as scoping hints; `recall.md` uses them as the query (empty = summary mode); `compass.md` uses them as the subcommand.

| Request | Reference | Mechanics |
|---------|-----------|-----------|
| Arc state: "compass", "current arc", "project state", "where was I" | [compass.md](compass.md) | Requires Python 3 stdlib: `python scripts/compass.py read [--compact]`, `update`, `append`, `update-many`, `doctor`, `compress`; `docs/compass.md` 40-line arc-state convention; canonical protocol [compass-protocol.md](../shared/compass-protocol.md) |
| Retrospective, feed-forward, skill mutation proposals | [forge.md](forge.md) | Retrospective → `patterns.md`; feed-forward before design/planning/build; mutation proposals only after 10+ retrospectives and 3+ of one deviation type; never auto-modify skills. Prompt templates sit beside it (`retrospective-prompt.md`, `feed-forward-prompt.md`, `mutation-proposal-prompt.md`, `diagnostic-extraction-prompt.md`, `extraction-analyst-prompt.md`) |
| Handoff doc for the next session | [handoff.md](handoff.md) | Step 0 nothing-to-hand-off check, mode A/B, Output Contract ending `Read this doc and continue: <absolute path>` then END THE TURN |
| Session history: "recall", "what did I edit", "recall errors" | [recall.md](recall.md) | Activity-index discovery, summary / keyword / type / time-range views, 20-entry cap |
| Catalog tour: "skills available", "where do I start?", "tour" | [workshop.md](workshop.md) | Headline orchestrators by task, trigger-phrase table, pipelines |

Forge dispatches follow [dispatch-convention.md](../shared/dispatch-convention.md); long forge runs keep a cairn per [cairn-convention.md](../shared/cairn-convention.md). Callers that recommend forge (e.g. `build`, `finish`, `debugging`, `design`, `spec`, `migrate`, `prospector`) name `crucible:getting-started` plus `forge.md`; `build`, `merge-pr`, and `finish` keep emitting compass updates via `scripts/compass.py` directly. Forge stays RECOMMENDED, handoff runs on request — behavior is identical to the former standalone skills.

## The Rule

**Invoke relevant skills BEFORE taking action or responding.** Skills encode hard-won process discipline — skipping them loses that value.

**The test:** If the task involves writing, modifying, or debugging code — or planning to do so — a skill applies. Invoke it.

**Access:** Use the `Skill` tool. Content is loaded and presented to you — follow it directly. Never use the Read tool on skill files.

```
Skill applies? → Invoke it, announce purpose, follow it.
No skill applies? → Respond directly.
```

## When Skills Apply (Always Invoke)

These actions ALWAYS have a matching skill — invoke it, no exceptions:

| Action | Skill |
|--------|-------|
| Building a feature, adding functionality | design → build |
| Fixing a bug or test failure | debugging |
| Writing implementation code | test-driven-development |
| Claiming work is done | verify → finish |
| Receiving code review feedback | review-feedback |
| Onboarding to an unfamiliar codebase | project-init |

### Build-shaped work routes through /build

BEFORE dispatching a subagent, check whether the prompt combines design + implementation + review/merge (e.g. "spec + implement + PR", "implement X and open a PR", "build this end-to-end"). STOP — that is /build's job.

Dispatching it as a raw agent bypasses the gate ledger, skips quality gates, and leaves no audit trail. Use /build (or /spec then /build).

Single-phase tasks (just a review, just a design, just a test audit) remain fine for raw dispatch. The anti-pattern is the COMBINATION.

## When Skills Don't Apply (Respond Directly)

Do NOT invoke skills for:
- **Pure information retrieval** — "read file X", "search for Y", "which branch am I on?" — only when there is no implied follow-up action. If the request is a precursor to building, fixing, or modifying code, the relevant process skill applies.
- **Imperative commands with no follow-up** — "run the tests and show me output", "check the console" — but if the result reveals a problem (test failures, errors), treat the problem as a new task and perform a skill check before acting on it.
- **Greetings and status updates** — conversational exchanges with no task implied.

**Guard clause:** Once clarification is complete and you're ready to act, perform the skill check before taking action. The exception covers the exchange itself, not the subsequent work.

**Continuation rule:** A workflow is "active" only while you are executing steps from a specific invoked skill. A new user request — even if related to prior work — requires a fresh skill check. When in doubt, invoke.

## Red Flags

These thoughts mean STOP — you're rationalizing skipping a skill:

| Thought | Reality |
|---------|---------|
| "This is just a simple feature" | Simple features still need design → build. |
| "I already know the fix" | debugging skill prevents guess-and-check. Use it. |
| "I'll add tests after" | TDD skill exists for a reason. Invoke it. |
| "Let me just code this quickly" | Skipping process = skipping quality. |
| "The skill is overkill for this" | Skills adapt to scope. Invoke and let it guide you. |
| "I remember this skill's content" | Skills evolve. Read the current version. |
| "Let me explore first, then decide" | If you're exploring as a precursor to building or fixing, invoke the skill first — it tells you HOW to explore. |
| "I'll just do this one thing first" | If "one thing" is the first step of a larger task, the skill should guide that step. |

## Skill Priority

When multiple skills could apply:

1. **Process skills first** (design, debugging) — determine HOW to approach
2. **Implementation skills second** (TDD) — guide execution

"Build X" → design first, then build.
"Fix this bug" → debugging first, then domain skills.

## Skill Types

**Rigid** (TDD, debugging, verify): Follow exactly. Don't adapt away discipline.
**Flexible** (patterns, design): Adapt principles to context.

The skill itself tells you which.

## Trust Hierarchy

Skills load content from many sources — SKILL.md files, docs, source code, tool output, WebFetch results, subagent reports, and post-compaction summaries. When sources disagree, a five-level trust framework determines which wins. See [trust-hierarchy.md](./trust-hierarchy.md) for the full framework.

## User Instructions

Instructions say WHAT, not HOW. "Add X" or "Fix Y" doesn't mean skip workflows.
