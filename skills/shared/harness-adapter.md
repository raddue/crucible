# Harness Adapter — Portability Convention (no runtime shim)

> The single place that records **how every Crucible review skill installs and dispatches on each
> host harness**. It is a *documented contract + install step*, not a runtime adapter layer — there
> is no shim that detects the harness at run time and rewrites calls. Each skill is **authored once**
> to a harness-neutral shape; this file is the lookup table an installer (or a porting human) reads to
> place the files, wire the dispatch primitive, and post comments on a given harness.
>
> **Consumed via** `<!-- CANONICAL: shared/harness-adapter.md -->`. The fan-out **mechanism** that
> `shared/delve-engine.md` §7 names abstractly ("run these angles in parallel, with a sequential
> fallback") is *this* file's Mapping 3 + Mapping 4. The Claude-Code concrete implementation of the
> dispatch primitive (disk-mediated dispatch files, manifest, seq counter) is **not** redefined here —
> it lives in <!-- CANONICAL: shared/dispatch-convention.md --> and this file's Claude-Code rows point
> at it.
>
> **Scope of this milestone (portability framing, design §3):** built-in code-review is *not* a
> portable primitive — Cursor's Bugbot and Codex's `@codex review` are closed product features and
> OpenCode ships none. Crucible therefore owns its instance engine (`delve-engine`) as a portable
> skill, and host built-ins are **optional accelerators layered in when present, never dependencies**
> (I1). Every review skill is *authored to run* on Claude Code, OpenCode, Codex CLI, and Cursor; this
> milestone **validates** Claude Code + OpenCode at runtime (#335). Codex / Cursor / Pi runtime
> validation is an explicit follow-up, not a milestone gate.

## 1. Supported harnesses

| Harness | Command/skill model | Subagent primitive | Built-in review (accelerator only) | Validation status |
|---|---|---|---|---|
| **Claude Code** | `.claude/skills/<name>/SKILL.md`, `name`/`description` frontmatter | Task / Agent tool (parallel) + disk-mediated dispatch (`shared/dispatch-convention.md`) | `/code-review` built-in (optional) | **Validated this milestone (#335)** |
| **OpenCode** | `.opencode/commands/<name>.md`, `description`/`agent`/`subtask` frontmatter, `$ARGUMENTS` + `@file` includes | `subtask: true` command (parallel where the host model supports it) | none — BYO reference harness | **Validated this milestone (#335)** |
| **Codex CLI** | prompt file in the Codex prompts dir, prompt metadata header | sequential in-context (no first-class parallel-subagent primitive) → **degradation fallback** | `@codex review` (closed product feature, optional) | Authored-to; runtime validation deferred |
| **Cursor** | rule / command file in the Cursor commands location | sequential in-context → **degradation fallback** | Bugbot (closed, server-side, optional) | Authored-to; runtime validation deferred |
| **Pi** | unknown / BYO | unknown → assume **degradation fallback** until probed | unknown | Unknown / BYO; not authored-against |

> The five mappings below are keyed by these harness names. Where a harness lacks a primitive, the
> mapping says **which fallback** applies — never "unsupported". A skill that cannot fan out in
> parallel still runs (Mapping 4); a skill that cannot post to a forge still surfaces its findings
> (Mapping 5). Degradation is bounded and documented, never silent.

## 2. Mapping 1 — Frontmatter fields

What metadata each harness reads at the top of a command/skill file, and how the trio's authored
fields map onto it. The authored source of truth is the Claude-Code `name` + `description` pair (as in
`skills/delve/SKILL.md`, `skills/temper/SKILL.md`); other harnesses are derived from it at install.

| Field (authored intent) | Claude Code | OpenCode | Codex CLI | Cursor |
|---|---|---|---|---|
| Skill identifier | `name:` | (file name `<name>.md`; no `name` key) | prompt metadata `name`/title | command/rule name |
| Trigger + one-line purpose | `description:` (triggers live here) | `description:` | prompt metadata description | rule description |
| Dispatch agent selection | model-critical roles use named agent types (`agents/<role>.md`, `model:` frontmatter — `crucible-red-team`=opus, `crucible-qg-judge`/`crucible-qg-verifier`=sonnet, `crucible-qg-fix`=inherit; see Mapping 1b); other dispatches stay per-call general-purpose (Task tool picks) | `agent:` (named agent profile) | n/a | n/a |
| "this command spawns a subagent" | n/a (decided in body) | `subtask: true` | n/a (sequential) | n/a (sequential) |
| Argument substitution | body reads invocation args | `$ARGUMENTS` token | prompt arg convention | command arg convention |
| File include | body reads paths via tools | `@file` include | prompt include | rule include |

**Install note.** When porting a Claude skill to OpenCode, the `name`/`description` collapse to the
file name + `description:`, and you ADD `agent:` + `subtask: true` to make the fan-out run as
subtasks. Nothing in the authored body changes — only the frontmatter is re-expressed per this row.

**Marker note.** The engine-dispatch marker (`` `dispatch: delve-engine` ``) is deliberately NOT one
of these frontmatter fields — it lives as a column-0 body line under a `## Dispatch` heading (see §7),
so that no harness's frontmatter loader parses or strips it.

## 2b. Mapping 1b — Per-role model tiers (recall-critical dispatch model enforcement)

The quality-gate / red-team loop is **recall-critical**: an Opus reviewer finds Fatals a Sonnet
reviewer misses (an Opus orchestrator caught 2 Fatals in 1 round that a Sonnet orchestrator missed in
8). When the model is left to "whatever the orchestrator passes / inherits", a Sonnet orchestrator
**silently degrades the red-team to Sonnet**. The fix (#352) is to bind the model **per role** so the
review tier is enforced independent of the orchestrator. This mapping records the per-role tiers and
how each harness expresses (or degrades on) the binding.

**Role → model tier (authored intent):**

| Role (agent type) | Tier | Why |
|---|---|---|
| `crucible-red-team` | **opus** | Recall-critical adversarial review (every **single-model** red-team round, look-harder, Devil's Advocate, depth-calibration second reviewer, re-review). The load-bearing pin. |
| `crucible-qg-judge` | **sonnet** | Stagnation judge — mechanical cross-round finding comparison; cheap. |
| `crucible-qg-verifier` | **sonnet** | Fix verifier **+** persistence checker — mechanical structural checks; cheap. One def, reused. |
| `crucible-qg-fix` | **inherit** | Fix agent / Plan Writer (main loop, re-reviewed each round by the now-Opus red-team) **+** post-pass minor quick-fix. Inheriting keeps it cheap under a Sonnet orchestrator and strong under an Opus one; a weaker fixer costs at most an extra round, never a missed bug. |

**Consensus-mode caveat.** Consensus-mode red-team rounds (quality-gate's Multi-Model Red-Team Review) resolve their model membership through the operator's `consensus_query` configuration, NOT the `crucible-red-team` pin — on those rounds the operator owns the consensus member tier. The Opus pin scopes to single-model dispatches.

**Standalone-`/red-team` fix dispatch — deliberate exclusion, not an oversight.** These pins cover the quality-gate fix sites; the standalone-`/red-team` fix-mechanism dispatch (`red-team/SKILL.md` fix-mechanism table — Plan Writer / Fix subagent) is intentionally left on the inherited model (it is caller/artifact-determined — that table routes "Standalone → caller decides") and is inherit-equivalent to `crucible-qg-fix` today. A future editor who moves `crucible-qg-fix` off `inherit` should re-evaluate that standalone red-team fix site too, or it stays a silent escapee on the inherited model.

**Namespacing (the `crucible-` prefix is deliberate).** Claude Code discovers agent types from
`<project>/.claude/agents/` AND `~/.claude/agents/`, and on a name collision the **higher-priority
location wins** — priority order: managed > `--agents` CLI > `.claude/agents/` (project) >
`~/.claude/agents/` (user) > plugin (official subagents docs, "Choose the subagent scope"; confirmed
via claude-code-guide 2026-06-03). Because Crucible installs these defs at **user level** for
cross-project reach, a consuming project's own same-named `<project>/.claude/agents/` def would
silently shadow the Crucible one. The `crucible-` prefix on every agent-type `name` / `subagent_type`
makes that collision implausible — it is the deliberate guard against the shadow.

**Precedence (why the agent-def `model:` actually binds).** The model is resolved by the chain
`CLAUDE_CODE_SUBAGENT_MODEL` env > call-level `model:` > **agent-def `model:`** > session inherit
(official subagents docs `https://code.claude.com/docs/en/subagents.md`, "Choose a model"; confirmed
via claude-code-guide 2026-06-03). Two consequences are load-bearing: (1) the agent-def `model:`
**does** override the inherited session model — that is what defeats the Sonnet-orchestrator
degradation; (2) a **call-level `model:`** would override the agent-def, so the rewired dispatches
**drop the call-level `model:`** entirely — the agent def is the single binding source. `model:
inherit` is a documented-valid value (omitting the field has the same effect), which is why
`crucible-qg-fix` may carry it explicitly.

**Global `CLAUDE_CODE_SUBAGENT_MODEL` sits above the pin — keep it off gate machines.** Because it
tops the precedence chain, exporting it (e.g. to `sonnet`) re-degrades the recall-critical red-team by
overriding the `crucible-red-team` Opus pin — so do not set it on a machine that runs the gate. This is
operator-controlled and deliberate (a machine-wide choice, bounded like the operator-default floor
documented for Codex/Cursor/Pi), NOT the silent orchestrator-inherit degradation #352 targets.

**Prose model words in the skill bodies are descriptive, not binding.** Phrases like "a dedicated Sonnet
agent" or "single Sonnet judge" describe today's intent — the agent def's `model:` is the single binding
source; to change a role's tier, edit the agent def, not the prose.

**Per-harness expression:**

| Harness | How the per-role tier is expressed | Status |
|---|---|---|
| **Claude Code** | `~/.claude/agents/crucible-<role>.md` with `model:` frontmatter (symlinked from `<repo>/agents/`). The agent-def `model:` binds via the precedence chain above. | **Confirmed** mechanism (docs; runtime-proven by the on-disk transcript read in the enforcement-proof note below). |
| **OpenCode** | An `agent:` profile per role, named with the intended tier; the skill's OpenCode frontmatter names the profile. | **Authored-to-spec, UNCONFIRMED.** Mapping 1 establishes only that OpenCode reads the `agent:` key — NOT that an `agent:` profile can pin a *model*. #335 confirms. If it cannot, OpenCode degrades to the operator-default floor below. |
| **Codex / Cursor / Pi** | no first-class per-agent model pin | **Degradation:** model = whatever the harness runs; the recall guarantee relies on the **operator setting a strong default model**. Bounded and documented, never silent. |

**Enforcement is proven by the on-disk subagent transcript model, not a pre-dispatch intent field
(#335 cross-link).** Two readouts must not be conflated:
- The session-index `model_tier` field (`dispatch-convention.md`) is set from the dispatch
  **decision** — the orchestrator's PRE-dispatch intent, before the subagent runs. It would report
  `opus` even if the agent-def silently failed to bind. **It cannot prove enforcement.**
- Claude Code writes each Task/Agent subagent dispatch to a per-subagent on-disk transcript at
  `<project>/<session-id>/subagents/agent-<id>.jsonl`, whose **assistant** records carry
  `message.model` = the model the subagent **actually ran on** (empirically confirmed to exist on this
  machine: Opus and Sonnet values observed across real transcripts; the `<synthetic>` sentinel is real
  and must be filtered). Enforcement is proven by reading that file and confirming `crucible-red-team`
  executed on `claude-opus-4-*` (qg-* on `claude-sonnet-4-*`). A
  model-discriminating *behavioral* fixture is explicitly out of scope (a behavioral PASS is consistent
  with the pin having silently failed). This direct read is the #335 runtime defense against the
  "documented contract can drift" risk below.

## 3. Mapping 2 — Command-file location

Where the installed file goes. This is the only path an installer needs to write.

| Harness | Location | Invoked as |
|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` (or a plugin-namespaced skills dir) | `/<name>` (the `/code-review` name collision is resolved per-harness via plugin namespacing, not by deleting the capability — design §3) |
| OpenCode | `.opencode/commands/<name>.md` | `/<name>` |
| Codex CLI | the Codex prompts directory (prompt file) | the harness's prompt-invocation convention |
| Cursor | the Cursor commands / rules location | the harness's command-invocation convention |
| Pi | unknown / BYO | unknown |

> Shared engine/convention files (`shared/delve-engine.md`, `shared/severity-verdict-contract.md`,
> `shared/dispatch-convention.md`, **this file**) are *referenced by* the skills via
> `<!-- CANONICAL: ... -->` and are installed alongside the skills wherever the harness keeps skill
> assets; they are not themselves invokable commands.

## 4. Mapping 3 — Subagent dispatch mechanism

How "run the finder angles (and one verifier per candidate) as parallel subagents" — `delve-engine`
§7 — maps onto each harness's primitive. The engine names the mechanism abstractly and makes **no
harness-specific call inline** (I1); this row is where the abstract name becomes concrete.

| Harness | Parallel-fan-out primitive | Concrete protocol |
|---|---|---|
| Claude Code | Task / Agent tool, multiple dispatches in one turn | **disk-mediated dispatch** — `shared/dispatch-convention.md` (dispatch dir, `manifest.jsonl`, seq counter, pointer prompts). This is the reference implementation. |
| OpenCode | `subtask: true` commands, one per angle | spawn the angle subtasks; the host model runs them concurrently where it can |
| Codex CLI | **none** → Mapping 4 sequential fallback | run angles as multiple sequential passes (§5) |
| Cursor | **none** → Mapping 4 sequential fallback | run angles as multiple sequential passes (§5) |
| Pi | unknown → assume Mapping 4 fallback | sequential passes until a primitive is confirmed |

**Caller vs. mechanism (design §5.1, r3fix-S5).** This adapter is the dispatch **mechanism** that
`delve-engine` *invokes* to run its angles — it is **not** a caller of the engine. The engine's two
direct dispatchers are exactly the `/delve` skill and `temper`; each carries the canonical column-0
`` `dispatch: delve-engine` `` marker line (added at wiring time, #334). This adapter file does **not**
carry that marker line — it is the thing the engine dispatches *through*, not a file that dispatches
the engine — and so is **not** in the I2 allowlist `{delve, temper}`. (See §7 for the marker grammar;
naming the marker phrase inline here, backtick-wrapped, never as a column-0 line, is exactly what keeps
this file out of the anchored grep.)

## 5. Mapping 4 — Graceful degradation (sequential passes)

When a harness has **no parallel-subagent primitive**, the engine still runs its angles — but as
**multiple sequential passes, one pass per angle** — never collapsed into a single in-context pass.

> The single collapsed in-context pass (one agent asked to "find everything" in one go) is **exactly
> the recall-poor failure this redesign exists to fix** — it is the floor we are climbing off, not a
> fallback we may land on. The sequential fallback preserves the multi-angle *coverage* (each angle is
> still a fresh, focused pass) and trades only latency for it (r7fix-min). "Graceful" means bounded and
> coverage-preserving, not free.

**Protocol on a no-subagent harness:**

1. Run each finder angle as its own sequential pass (one per angle in `delve-engine` §4 — the bug
   angles plus any selected quality angles), each pass scoped to the same `scope`/`effort`.
2. Run the verify gate as its own pass(es) after dedup — one verifier per deduped candidate,
   sequentially.
3. **Warn once** (not per angle) that recall MAY drop under sequential passes relative to a true
   parallel fan-out, so the operator can choose a higher `effort` to compensate.

This is why the milestone's recall floor (AC6) is gated on **both** the Claude-Code parallel path AND
the OpenCode sequential-fallback path against the same fixture: a fan-out bug that silently drops an
angle must fail the parallel floor and must not be masked by the sequential path, and vice-versa.

## 6. Mapping 5 — Forge / comment posting + paste-fallback

The portable primitive behind `delve --comment` (I9 / AC2) and `temper` Step 5. `--comment` detects
the active forge and posts inline; when no forge is detected **or the harness lacks a posting
primitive**, it falls back to **paste-mode** — printing the formatted body for the operator to paste.
The fallback **never silently drops the comment** (I9).

**Forge detection is CLI-probe order, not a hostname literal.** For a PR *URL*, parse the forge from
the host and use only the matching CLI; for a bare PR *number*, probe the CLIs in order against the
current `origin`. A CLI that exits non-zero with "404 / not found / auth required" is a **real error**
to surface and pause on — **not** a silent fall-through to the next CLI (that would post against the
wrong scope).

| Forge | Detect | Post inline |
|---|---|---|
| GitHub / GHE | `gh` CLI present and authed for the host | `gh pr review <id> --comment --body-file <findings.md>` |
| GitLab | `glab` CLI | `glab mr note <id> -m "$(cat findings.md)"` |
| Bitbucket | `bb` CLI (or REST) | `bb pr comment <id> --file findings.md` (or REST) |
| Self-hosted of a known forge | matching CLI configured for the host | the matching row above |
| No forge / unknown host / no posting primitive | — | **paste-mode**: print the body for the operator to paste |

**Per-harness posting primitive.** The CLIs above are environment tools, not harness features — any
harness that can run shell commands reaches the same forge rows. A harness that **cannot** run the
forge CLI (sandboxed, no shell, unknown) takes the **paste-mode** row directly. Either way the body is
surfaced, never dropped.

**Never silent-drop (I9).** On a non-zero post, first **re-query PR state** with the matching CLI
before classifying, then:

| Failure mode | Response |
|---|---|
| Auth-fail / token expired / rate-limit (403) / network error | Paste-mode with retry guidance |
| PR closed-without-merge | Paste-mode with conditional guidance ("paste if you intend to reopen") |
| PR merged or deleted | Surface locally (no paste offer) — findings remain in session |
| Forge cannot report state (unknown host / REST gap / probe errored) | **Default to paste-mode** — a transient/unclassifiable error surfaces the body, never swallows it |

This table is the shared backing for `delve` Step 5 and `temper` Step 5, so "forge-agnostic like
temper" is a real adapter mapping, not a prose analogy.

## 7. The dispatch marker is body prose, not frontmatter

The canonical engine-dispatch marker — the line `` `dispatch: delve-engine` `` — lives as a **column-0
body line under a `## Dispatch` heading** in the two direct dispatchers (`/delve`, `temper`), added at
wiring time (#334). It is deliberately **NOT** a YAML frontmatter key.

**Why it matters for portability (the reason it belongs in this file):** every harness frontmatter
loader in §2 — Claude Code's skill loader, OpenCode's `.opencode/commands/` schema, Codex's prompt
metadata — parses the fenced `---` block and may strip or reject keys it does not recognize. A marker
placed *inside* frontmatter could be silently dropped by a loader on some harness, breaking the I2
grep on that harness. Placed in the **body**, after the closing `---`, it is prose that no loader
touches — the I2 allowlist test reads it with the **anchored** pattern `grep -rn '^dispatch:
delve-engine'`, and the loaders never see it as configuration. Body placement is therefore the
portable choice, not an arbitrary one.

**Marker grammar (binding on every file, including this one).** No file may reproduce the bare marker
phrase at **column 0** in running prose — documentation, changelog, workshop, and *this adapter file*
reference it only **inline / backtick-wrapped / reworded**, never as the first characters of a line.
The `^` anchor in the grep is exactly what makes such prose mentions safe: they are discussed but never
*start* a line, so the anchored pattern passes over them while matching only the two real column-0
dispatch lines. The I2 test asserts **set equality** — the set of files carrying a column-0
`^dispatch: delve-engine` line must EQUAL exactly `{delve, temper}` — so a stray third file (this one
included) that accidentally began a line with the bare phrase would FAIL the test, not merely be
tolerated.

## 8. Per-harness install manifest

For each harness: **where files go · how it is invoked · what degrades · how comments post.** This is
the install checklist — concrete enough to install by (AC6 doc portion).

### Claude Code *(validated #335)*
- **Where:** `skills/<name>/SKILL.md` under `.claude/skills/` (or plugin-namespaced); shared
  `shared/*.md` installed alongside, referenced via `<!-- CANONICAL: ... -->`.
- **Agent defs (model enforcement, Mapping 1b):** symlink `<repo>/agents/*.md` →
  `~/.claude/agents/` (user-level, mirroring the `skills/` symlink — `ln -sf "$PWD"/agents/*
  ~/.claude/agents/`), so `crucible-red-team` / `crucible-qg-judge` / `crucible-qg-verifier` /
  `crucible-qg-fix` are discoverable in every project. Without this step the named `subagent_type`s
  fail to resolve and the recall guarantee degrades (see Mapping 1b's degradation note / the
  quality-gate fallback warning). On Claude Code an uninstalled `subagent_type` surfaces as a
  catchable **Task-tool resolution error** — not a silent substitution of a default agent — and that
  observable error is what fires the non-silent fallback warning (hence the trigger is the
  type-resolution failure, not a transcript read). A harness that silently substitutes a default on an
  unknown type cannot fire that warning, so on such a harness install MUST be verified out-of-band —
  this manifest is that check. Bare-name `subagent_type` resolution for these four defs is **verified
  for the user-level symlink install** (`~/.claude/agents/`, where agents load by bare `name`). Under a
  **plugin install**, Claude Code namespaces plugin agents (`crucible:crucible-red-team`), and
  bare-name `subagent_type` resolution for plugin-provided agents is **UNCONFIRMED** — the docs specify
  scoping for `@`-mention / `--agent`, not for the Task-tool `subagent_type` field (cf. the OpenCode
  row's "Authored-to-spec, UNCONFIRMED" / "#335 confirms" status). Until plugin-scoped dispatch is confirmed, the
  model-enforcement guarantee is delivered by the **symlink install**; a plugin install whose bare type
  fails to resolve takes the documented **non-silent fallback** above, not silent degradation.
- **Frontmatter:** `name:` + `description:` (Mapping 1).
- **Invoked:** `/<name>` (e.g. `/delve`, `/temper`, `/audit`). `/code-review` built-in stays an
  optional accelerator (I1), never a dependency.
- **Dispatch:** Task / Agent tool, disk-mediated per `shared/dispatch-convention.md` (Mapping 3). Full
  parallel fan-out. Model-critical roles route through the named agent types above (Mapping 1b).
- **Degrades:** does not — parallel primitive present.
- **Comments:** forge CLI rows in Mapping 5 (§6) via shell; paste-mode otherwise.

### OpenCode *(validated #335 — BYO reference harness)*
- **Where:** `.opencode/commands/<name>.md`; shared files installed alongside.
- **Agent defs (model enforcement, Mapping 1b):** author one `agent:` profile per role
  (`crucible-red-team`=opus, etc.) and name it from the skill frontmatter. **Authored-to-spec,
  unconfirmed** — whether an OpenCode `agent:` profile can pin a model is #335's confirmation; if it
  cannot, this row degrades to the operator-default floor (set a strong default model).
- **Frontmatter:** `description:` + `agent:` + `subtask: true`; body uses `$ARGUMENTS` and `@file`
  includes (Mapping 1).
- **Invoked:** `/<name>`.
- **Dispatch:** one `subtask: true` per angle (Mapping 3).
- **Degrades:** if the host model cannot run subtasks concurrently, falls to Mapping 4 sequential
  passes with the one-time recall warning.
- **Comments:** same forge CLI rows via shell; paste-mode otherwise.

### Codex CLI *(authored-to; runtime validation deferred)*
- **Where:** the Codex prompts directory (prompt file + metadata header).
- **Agent defs (model enforcement, Mapping 1b):** no first-class per-agent model pin → **degrades**;
  the recall guarantee relies on the operator setting a strong default model.
- **Frontmatter:** prompt metadata `name`/description (Mapping 1).
- **Invoked:** the harness's prompt-invocation convention.
- **Dispatch:** no first-class parallel-subagent primitive → **Mapping 4 sequential passes** (one per
  angle) + one-time recall warning.
- **Comments:** `@codex review` is a closed accelerator, not a dependency; `--comment` uses the forge
  CLI rows via shell, else paste-mode.

### Cursor *(authored-to; runtime validation deferred)*
- **Where:** the Cursor commands / rules location.
- **Agent defs (model enforcement, Mapping 1b):** no first-class per-agent model pin → **degrades**;
  the recall guarantee relies on the operator setting a strong default model.
- **Frontmatter:** rule name + description (Mapping 1).
- **Invoked:** the harness's command-invocation convention.
- **Dispatch:** no first-class parallel-subagent primitive → **Mapping 4 sequential passes** + one-time
  recall warning.
- **Comments:** Bugbot is a closed accelerator, not a dependency; `--comment` uses the forge CLI rows,
  else paste-mode.

### Pi *(unknown / BYO — not authored-against)*
- **Where / invoked / frontmatter:** unknown until probed.
- **Dispatch:** assume **Mapping 4 sequential passes** until a parallel primitive is confirmed.
- **Comments:** forge CLI rows if a shell is available (unconfirmed for Pi), else paste-mode (the universal floor).

> **Drift risk (design §9, R5).** This is a documented contract, not a runtime check, so it can drift
> from a harness's actual behavior as harnesses evolve. The milestone's defense is the #335 portability
> validation (Claude Code + OpenCode against the same fixture) — runtime evidence for the two reference
> harnesses — plus the I2 grep test for the marker invariant. Codex / Cursor / Pi rows are
> authored-to-spec and should be confirmed against the live harness before relying on them.
