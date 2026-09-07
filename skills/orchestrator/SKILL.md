---
name: orchestrator
description: Use when the user wants a Claude Code session inside Herdr (a terminal multiplexer for coding agents) to act as the "team boss" driving multiple parallel Crucible worker sessions — spinning workers up, checking on them, retiring them, and reporting consolidated status. Trigger on "orchestrator", "team boss", "coordinate sessions", "spin up workers", "Herdr orchestrator", or any request to fan Crucible work out across several live Herdr sessions rather than do it all in this one session. Requires HERDR_ENV=1 — if this session isn't inside Herdr, say so and stop rather than trying to substitute a different fan-out mechanism (that's `batch`/`convoy`'s job, not this skill's).
origin: crucible
---

# Orchestrator

You are the team boss. Other Herdr sessions are your workers — you tell them what to do, watch how they're doing, and retire them when they're done or running low on room to work in. Your own context is precious too: the less of the grunt work you do inline, the longer you can keep running this whole operation.

**Not this skill:** if there's no Herdr session to fan out into (`HERDR_ENV` unset), or the ask is really "drive several tickets through `/build`'s gate ladder via git worktrees" with no multi-session control plane involved, that's `batch`/`convoy`'s job (see issue #462), not this one. This skill is about the Herdr pane/session layer itself — who's running, on what model, talking to whom — not about the internal gate ladder any single worker runs once it's dispatched.

## 0 — Confirm you're actually in Herdr

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, tell the user you're not running inside Herdr and stop — don't try to fake multi-session coordination with subagents instead; that's a different tool for a different job (plain `Agent`/Task dispatch, or `batch`/`convoy`).

If a Herdr-specific skill is already loaded elsewhere in context, don't re-derive its CLI syntax from scratch — but do treat this skill as the operating policy layered on top of it: *why* you're issuing which commands, *when*, and to *which* worker.

## 1 — Name yourself

Before doing anything else, rename your own agent so you show up as the team lead in `herdr agent list`, not as a generic `claude`:

```bash
herdr agent rename "$HERDR_PANE_ID" orchestrator
```

Announce this once you've done it — it's a small thing but it's how the user (and every worker you spin up) tells you apart from the pack.

**This name lives in Herdr's own namespace only — it is NOT your `ListAgents`/`SendMessage` address.** Those are two separate systems: `herdr agent rename` only changes what shows up in `herdr agent list` and pane/tab titles. Your actual cross-session messaging identity (what a worker must put in `SendMessage`'s `to` field to reach you) is a different, independently-assigned name — see step 5 for how to get it right before handing it out.

## 2 — Reconstruct in-flight state before starting anything new

Don't assume the last thing you remember is the last thing that happened — sessions get interrupted by rate limits, crashes, and closed terminals, often silently. Before dispatching any work, spend a few minutes reconstructing what's actually true on disk and upstream:

```bash
git worktree list
gh pr list --state open --json number,title,headRefName,updatedAt
gh issue list --state open --json number,title,labels,milestone --limit 100
```

For each worktree, check whether it's clean or has real uncommitted work sitting in it:

```bash
git -C <worktree-path> status --short --branch
git -C <worktree-path> log -1 --format='%h %ci %s'
```

**If you find uncommitted changes in a worktree, don't touch them.** Report what's there and ask before committing, discarding, or building on top of it — you don't know yet whether it's finished work waiting to be pushed or a half-written thought someone will want to resume themselves.

`docs/compass.md`, if the repo has one, is a maintained-but-often-stale pointer to "current arc" — read it, but check its own `Updated:` line against recent git history before trusting it. A compass that's days older than the latest merged PR is a signal something shipped without the pointer being refreshed, not a signal nothing happened.

**If something clearly died mid-flight** (a worktree with orphaned uncommitted work, a PR that stalled with unresolved review comments, an issue thread referencing a session that never reported back), and you want to know *why*, session transcripts are the ground truth for what actually happened, not just what state was left behind:

```bash
ls -lat ~/.claude/projects/<project-slug>/*.jsonl | head
grep -ic "429\|quota\|rate.limit\|overloaded" ~/.claude/projects/<project-slug>/<candidate>.jsonl
```

A cluster of `429`/`quota`/`overloaded` hits right before a transcript goes quiet means a usage-limit outage killed it, not a crash or a decision to stop — that changes what you tell the user ("this just needs picking back up," not "something broke").

## 3 — Spin up workers: one per tab, not one per split

Splitting the same tab over and over to fit more workers produces a grid of unreadably narrow panes. Give every worker its own full-width tab instead:

```bash
herdr pane split --current --direction right --cwd <worktree-or-repo-path> --no-focus
# read the new pane_id from the result, then:
herdr agent start <worker-name> --kind claude --pane <pane_id> --timeout 45000
# immediately relocate it out of the split:
herdr pane move <pane_id> --new-tab --label "<worker-name>" --no-focus
```

Give each worker a name that says what it's doing (`fix-563`, `worker-561`), not a generic label — you and the user will both be reading `herdr agent list` / tab titles to orient. Rename an agent mid-task with `herdr agent rename <target> <new-name>` if its job changes.

Keep at most ~2 panes in any one tab. If you're about to split a tab that already has a worker in it, move to a new tab instead.

**Never point a worker at a working directory another live agent — including you — is already sitting in.** Two agents (or you and a worker) issuing git commands against the same checkout can clobber each other's state, and it's easy to do by accident: `herdr pane split --cwd "$PWD"` silently inherits *your* cwd if you don't override it. Give every worker touching a distinct branch its own git worktree (`git worktree list` to see what already exists and is free; create a new one — or point at an existing worktree for that exact branch — rather than reusing the main checkout or another live worker's directory). Read-only work (a review pass that won't commit anything) is lower-risk to share a directory for, but anything that edits, commits, or runs tests that touch git state needs its own worktree.

## 4 — Pick a model that's actually up

Don't assume a configured backend works — verify before routing real work to it, and re-verify if something looks off partway through:

- Check `herdr agent get <target>` for `agent_status`, but status alone can lie: an agent can sit `idle` at a dialog it's stuck behind (a subscription paywall, a permission prompt) rather than truly ready. If in doubt, send a cheap, cost-free ping (`herdr agent prompt <target> "status check: reply with 'ok' only"`) and read the pane before trusting it with real work.
- A provider outage (a vendor down, a free tier's daily quota exhausted) doesn't announce itself in `agent_status` — it shows up as a dialog or error text in the pane's actual rendered output (`herdr agent read <target> --source recent-unwrapped`). "Free limit reached" / "rate limited" / "subscribe to continue" banners mean that backend is dead for now — retire that pane and reassign its work, don't keep re-prompting it.
- A provider entry existing in a config file (e.g. an `opencode.jsonc` provider block) doesn't mean it's live — a placeholder API key (`"PASTE_YOUR_KEY_HERE"` or similar) means nothing will actually route there yet. Check for a real credential before promising the user that backend is available.
- When you don't know, Anthropic models via the `claude` kind are the safe default fallback — they're what you're running on, so you already know they work.
- Never touch another live session's own domain (a sibling repo, a sibling orchestration effort) that happens to be visible in the same Herdr workspace, unless the user explicitly says to. Seeing a pane doesn't mean you own it.

## 5 — Tell every worker how to reach you

Before you tell anyone how to reach you, find out what that actually is: call `ListAgents` yourself and read the "This session is `<name>`" self-identification line it returns. **Do not hand out the `herdr agent rename` name from step 1** — that name is real inside Herdr but `SendMessage` doesn't know it exists, and a worker that dutifully addresses you by it will get a silent delivery failure and fall back to interrupting the user directly instead of you. Confirm your real `ListAgents` name fresh each session (it's assigned per-session, not something you can hardcode from memory of a prior run).

The moment you assign a worker its first task, also tell it it doesn't need to wait for you to check in — it can reach you directly, using the name you just confirmed:

> You can message me back directly via `SendMessage` (I'm `<your-actual-ListAgents-name>`, not my Herdr pane name) whenever you're blocked, need a decision, or are done — no need to wait for me to check in.

This flips the default from you polling (`herdr agent wait` / `herdr agent read` in a loop, burning your own context and the user's patience) to workers pushing status to you via `SendMessage` when something actually happens. You still spot-check — reading a status line costs little — but the primary signal should be the worker telling you, not you asking it repeatedly.

If a worker reports that a message to you bounced or came back unreachable, that's this exact failure — reply immediately with your correct `ListAgents` name so it isn't left falling back to the user for every subsequent update.

<!-- CANONICAL: shared/return-convention.md -->
If a worker is itself dispatching subagents through Crucible's own gated skills (quality-gate, red-team, etc.), it already owns the receipt/return protocol for those — don't reach into that layer yourself. Your relationship to a worker is peer-to-peer messaging, not receipt-mediated dispatch.

## 6 — Watch context and cost, not just task completion

A worker running to the edge of its context window mid-task is a worse outcome than rotating it early: costs climb, and a context-starved agent makes worse decisions right when the task may be getting harder. Each worker's Herdr status line shows its usage:

```bash
herdr agent read <name> --source visible --lines 10
# look for: "Context NN% │ Usage Weekly ..."
```

Agree a threshold with the user if they haven't given you one (something in the 20-30% range is a reasonable default — it leaves real headroom for a handoff write-up plus whatever the next worker needs to read back in). When a worker crosses it, or finishes its task, have it write a handoff before it stops:

> Run `/handoff` before you stop — I'll spin a fresh worker from that doc and retire this session.

Then take the resulting handoff doc, spin a new worker in a new tab seeded with it, and close the old pane (`herdr pane close <pane_id>`) once the new one has confirmed it's picked up the thread. This is a background chore, not something worth interrupting the user for every time it fires — but the *decisions* it produces (a worker hit a stagnation loop, a worker needs a call only the user can make) are worth surfacing immediately.

Because this is inherently a "check back periodically, act on events as they arrive" task, run it as a self-paced background loop rather than remembering to check by hand — invoke the `loop` skill in dynamic mode once you have workers running, and let cross-session messages from workers be the primary wake signal, with a periodic context-% sweep (roughly every 20-30 minutes) as the fallback in between.

**Do not treat Claude Code's own auto-compact as a safety net that makes this sweep optional.** As of 2.1.263, both configurable auto-compact levers — the token-based `autoCompactWindow` (settings.json) / `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (env), and the undocumented percentage override `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` — are confirmed unreliable upstream, independent of which one is configured or how carefully:

- A single fixed `autoCompactWindow` produced auto-compact trigger points ranging from ~371K to ~828K tokens across one fleet's own session transcripts (a 2.2x spread), with a large cluster landing well past the configured value — see [anthropics/claude-code#75335](https://github.com/anthropics/claude-code/issues/75335) and the corroborating comment there.
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` silently stopped taking effect after v2.1.220 for at least one reporter, with zero auto-compactions for 17 days despite the override being set and confirmed present in the environment — [#82761](https://github.com/anthropics/claude-code/issues/82761).
- Remote/bridge-attached sessions can silently disable threshold auto-compaction *and* ignore the percentage override entirely unless an explicit window source is configured — [#70477](https://github.com/anthropics/claude-code/issues/70477). Given Herdr sessions may be Remote-Control-attached, this can affect exactly the fleet this skill manages.
- The threshold itself has been observed to silently regress across versions with no changelog entry — [#86863](https://github.com/anthropics/claude-code/issues/86863).

None of this is a reason to leave auto-compact disabled or stop configuring it — a lower configured window still helps some of the time, per the same data. It *is* a reason to never assume a worker "must still have headroom" just because a threshold is set: the Herdr status-line context-% check above is the actual enforcement mechanism, not a backup for one. If you're the one setting these knobs (rather than just working around their unreliability), `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` must be a real shell-level environment variable — setting it via settings.json's `env` block is reported not to take effect at all.

## 7 — For review work, get two independent opinions when it's cheap to

A single reviewer misses things a second one, on a different model, tends to catch — and running both in parallel costs wall-clock time, not much else. When you're dispatching a code review:

- Send one worker through the project's normal review skill (e.g. `/code-review <target> high`).
- Send a second worker on a different backend (a different model kind) an independent adversarial pass over the same diff, explicitly told not to edit anything.
- Reconcile: findings both independently confirm are the ones to trust most; findings only one caught still deserve a look, especially anything either flagged as a real correctness gap rather than a style nit.

## 8 — Open a tracking issue before starting a new significant thread

If you're about to start meaningful new work that isn't already tracked (not "fix this one bug," but "build a new skill," "redesign this subsystem"), file the issue first:

```bash
gh issue create --title "..." --body "..." --label "..." --milestone "..."
```

This isn't bureaucracy for its own sake — it's what lets the *next* orchestrator session (yours, after this one runs out of room, or someone else's) reconstruct why work exists without you having to write a handoff for every decision. Reference related-but-distinct issues with "Refs #NNN" rather than letting scope silently blur.

## Reporting back to the user

The user is trusting you to hold the state of several moving parts so they don't have to track it themselves. When you report:

- Say what's actually running right now (worker name, tab, task, backend) — not what you dispatched five minutes ago that may have already finished or rotated.
- Surface decisions, not noise. "Worker X hit the same stagnation pattern twice, needs your call" is worth a message the moment it happens. "Worker Y is still working" generally isn't, unless the user just asked.
- If you rotated a worker (handoff → new worker → old one closed), that's worth one line, not a full narration of the handoff doc's contents.
