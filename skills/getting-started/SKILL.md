---
name: getting-started
description: Use when starting any conversation - establishes how to find and use skills, requiring skill activation before ANY response including clarifying questions
---

# Using Crucible Skills

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
| Implementing from a mockup/visual spec | mock-to-unity |
| Creating a UI mockup | mockup-builder |
| Writing implementation code | test-driven-development |
| Claiming work is done | verify → finish |
| Receiving code review feedback | review-feedback |
| Onboarding to an unfamiliar codebase | project-init |

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
2. **Implementation skills second** (mock-to-unity, TDD) — guide execution

"Build X" → design first, then build.
"Fix this bug" → debugging first, then domain skills.

## Skill Types

**Rigid** (TDD, debugging, verify): Follow exactly. Don't adapt away discipline.
**Flexible** (patterns, design): Adapt principles to context.

The skill itself tells you which.

## User Instructions

Instructions say WHAT, not HOW. "Add X" or "Fix Y" doesn't mean skip workflows.
