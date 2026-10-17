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
> milestone **validates** Claude Code at runtime (#335); OpenCode runtime validation is the
> non-gating follow-up #337. Codex / Cursor / Pi runtime validation is a further follow-up, not a
> milestone gate.

## 1. Supported harnesses

| Harness | Command/skill model | Subagent primitive | Built-in review (accelerator only) | Validation status |
|---|---|---|---|---|
| **Claude Code** | `.claude/skills/<name>/SKILL.md`, `name`/`description` frontmatter | Task / Agent tool (parallel) + disk-mediated dispatch (`shared/dispatch-convention.md`) | `/code-review` built-in (optional) | **Validated this milestone (#335)** |
| **OpenCode** | `.opencode/commands/<name>.md`, `description`/`agent`/`subtask` frontmatter, `$ARGUMENTS` + `@file` includes | `subtask: true` command (parallel where the host model supports it) | none — BYO reference harness | **Runtime validation: non-gating follow-up #337** |
| **Codex CLI** | prompt file in the Codex prompts dir, prompt metadata header | sequential in-context (no first-class parallel-subagent primitive) → **degradation fallback** | `@codex review` (closed product feature, optional) | Authored-to; runtime validation deferred |
| **Cursor** | rule / command file in the Cursor commands location | sequential in-context → **degradation fallback** | Bugbot (closed, server-side, optional) | Authored-to; runtime validation deferred |
| **Pi** | `~/.pi/agent/agents/<name>.md`; invoke skill by path | `subagent` + disk-mediated dispatch (`shared/dispatch-convention.md`) | none | Authored-to-spec; live validation pending |

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
| Dispatch agent selection | model-critical roles use named agent types (`agents/<role>.md`), whose native selector is host-specific (Claude Code details in Mapping 1b); profile requests remain neutral | `agent:` (named agent profile), resolved by operator/host configuration | n/a | n/a |
| "this command spawns a subagent" | n/a (decided in body) | `subtask: true` | n/a (sequential) | n/a (sequential) |
| Argument substitution | body reads invocation args | `$ARGUMENTS` token | prompt arg convention | command arg convention |
| File include | body reads paths via tools | `@file` include | prompt include | rule include |

**Install note.** When porting a Claude skill to OpenCode, the `name`/`description` collapse to the
file name + `description:`, and you ADD `agent:` + `subtask: true` to make the fan-out run as
subtasks. Nothing in the authored body changes — only the frontmatter is re-expressed per this row.

**Marker note.** The engine-dispatch marker (`` `dispatch: delve-engine` ``) is deliberately NOT one
of these frontmatter fields — it lives as a column-0 body line under a `## Dispatch` heading (see §7),
so that no harness's frontmatter loader parses or strips it.

<!-- CANONICAL: shared/model-tier-policy.md -->
## 2b. Mapping 1b — Per-role model tier intent and host bindings

The quality-gate / red-team loop is **recall-critical**: historical measurements found stronger
reviewers surfaced Fatals missed by weaker reviewers. Role intent requests `high` for red-team and
`standard` for mechanical/fix roles, independent of orchestrator tier. Host enforcement varies:
Claude Code can bind roles through native agent selectors; Pi gate roles fail closed per
`shared/dispatch-convention.md`; other hosts may use operator/session defaults. This mapping records
known host bindings and limitations; Crucible does not globally enforce profile-to-model selection.

**Profile requests.** Neutral tiers (`high`, `standard`, `fast`, `inherit`) express role intent; `model_profile` is policy/manifest vocabulary, not native tool syntax. Crucible does not globally select providers. Host-specific selectors and enforcement are documented below; operator configuration owns actual mappings. No Jev integration ships in Crucible, and Jev remains optional/off by default. The maintainer-selected target mapping for any future optional Jev integration is `high`→Sol/high, `standard`→Luna/xhigh, `fast`/Haiku→Luna/low; the last supersedes #651's original Haiku→Luna/medium request. This target is documentation only; no Jev per-dispatch API or model/effort verification is integrated. Where hosts use defaults, profile application is unverified and no-stop dispatch behavior remains.

**Role → profile (authored intent; host-local concrete mappings are operator configuration):**

| Role (agent type) | Profile / current alias | Why |
|---|---|---|
| `crucible-red-team` | **high** | Recall-critical adversarial review (every **single-model** red-team round, look-harder, Devil's Advocate, depth-calibration second reviewer, re-review). The load-bearing profile request. |
| `crucible-qg-judge` | **standard** | Stagnation judge — mechanical cross-round finding comparison; cheap. |
| `crucible-qg-verifier` | **standard** | Fix verifier **+** persistence checker — mechanical structural checks; cheap. One def, reused. |
| `crucible-qg-fix` | **standard** | Fix agent / Plan Writer (main loop, re-reviewed on single-model rounds by the `high`-profile red-team) **+** post-pass minor quick-fix. Cheap under any orchestrator; the **main-loop** fix output is re-reviewed by the `high`-profile red-team on single-model rounds — a weaker fix is *caught* on rounds that reach a subsequent red-team; the cost is **at least** an extra round and is not bounded above (#528 §1 measures fix-authored defects breeding across generations, and §4 shows the stagnation judge scores the catch as PROGRESS, so the extra rounds are not observable to the loop) (#537). **Not covered:** the post-pass quick-fix; the two fix-related terminal exits (agent-declared `ARCHITECTURAL_BLOCK`; orchestrator-detected no-op → `ESCALATED`); and any escalation exit (e.g. stagnation, sustained regression, diminishing returns, the 15-round circuit breaker), where a fix that is reviewed but rejected costs gate termination, not an extra round (#528 measures a 38% iatrogenic rate under the pre-#537 `inherit` fixer (tier unrecorded in the issue)); nor is context-window overflow — #537 measured this role's per-turn `cache_read` at 145 K–196 K, the highest of any subagent class, on a bare `sonnet` pin with no `[1m]` suffix (see `check_model_pins.py`'s bracket-suffix convention), and an overflowing dispatch's disposition is undefined by the current spec — the No-Op Fix Detector (`SKILL.md:511-514`) is defined over a produced artifact and cannot fire on a missing one, and the documented crashed-dispatch handling (`:36`, `:673`) records and continues rather than escalating; this is a real gap, not merely "an extra round"; measuring actual headroom is a #539 follow-up item — on consensus-eligible rounds the reviewer tier is operator-owned (see the Consensus-mode caveat / residual (b)), so the bound holds only for single-model rounds. Round-count and calibration-distribution effects of this flip are unmeasured — #539. |

**Consensus-mode caveat.** Consensus-mode red-team rounds (quality-gate's Multi-Model Red-Team Review) resolve their model membership through the operator's `consensus_query` configuration, NOT the `crucible-red-team` profile request — on those rounds the operator owns the consensus member tier. The requested `high` profile scopes to single-model dispatches.

**Standalone-`/quality-gate` red-team mode fix dispatch — deliberate exclusion, not an oversight.** These pins cover the quality-gate fix sites; the standalone-`/red-team` fix-mechanism dispatch (`quality-gate/red-team-mode.md` fix-mechanism table — Plan Writer / Fix subagent) is intentionally left on the inherited model (it is caller/artifact-determined — that table routes "Standalone → caller decides"). As of #537, `crucible-qg-fix` requests `standard` and this standalone site is **no longer inherit-equivalent to it** — the standalone site now silently tracks the orchestrator's own model while the QG fix loop does not. This divergence is a known, unresolved gap; re-evaluating whether the standalone site should also pin is separate follow-up work, tracked in #538.

**Namespacing (the `crucible-` prefix is deliberate).** Claude Code discovers agent types from
`<project>/.claude/agents/` AND `~/.claude/agents/`, and on a name collision the **higher-priority
location wins** — priority order: managed > `--agents` CLI > `.claude/agents/` (project) >
`~/.claude/agents/` (user) > plugin (official subagents docs, "Choose the subagent scope"; confirmed
via claude-code-guide 2026-06-03). Because Crucible installs these defs at **user level** for
cross-project reach, a consuming project's own same-named `<project>/.claude/agents/` def would
silently shadow the Crucible one. The `crucible-` prefix on every agent-type `name` / `subagent_type`
makes that collision implausible — it is the deliberate guard against the shadow.

**Claude Code selector precedence.** `CLAUDE_CODE_SUBAGENT_MODEL` env > call-level `model:` > agent-definition `model:` > session inherit. Agent definitions bind the four Crucible gate-role selectors below the call-level selector; the user-level symlink install is required for those definitions to resolve. An installed host mapping is not a Crucible runtime guarantee, and other hosts must use their own adapter or operator/session defaults.

**Global override caution.** `CLAUDE_CODE_SUBAGENT_MODEL` takes precedence over the native red-team selector and can change its model. Gate operators who rely on the Claude Code defaults should leave this unset or verify the observed model. If overriding profiles, the operator owns that choice.

**Optional Jev boundary.** Jev does not integrate with Crucible dispatch here. The target pairs above are documentation only; any future Jev adapter must be separately specified, opt-in, and report resolved model/effort or unavailable. Jev is not required.

**Prose model words in skill bodies are descriptive, not binding.** Change a role's requested tier in the profile-intent declaration; host-local binding stays outside Crucible policy.

**Per-harness expression:**

| Harness | How the per-role tier is expressed | Status |
|---|---|---|
| **Claude Code** | `~/.claude/agents/crucible-<role>.md` uses native `model:` selectors (symlinked from `<repo>/agents/`); high→Opus, standard→Sonnet, fast→Haiku where those selectors are present. Skill prose states requested tier. | Native binding exists; operator may override via `CLAUDE_CODE_SUBAGENT_MODEL`. Verify observed model when a run requires confirmation. |
| **OpenCode** | An `agent:` profile per role, named with the intended profile; the skill's OpenCode frontmatter names the profile. | **Authored-to-spec, UNCONFIRMED.** Mapping 1 establishes only that OpenCode reads the `agent:` key — NOT that an `agent:` profile can pin a *model*. #337 confirms. If it cannot, OpenCode degrades to the operator-default floor below without stopping dispatch. |
| **Codex / Cursor** | no first-class per-agent model pin | **Unverified profile:** omit unsupported profile/model fields; model = whatever the harness runs or operator configures. Record actual model when available and disclose profile intent is unverified. No recall guarantee is provided by Crucible on this host. |
| **Pi** | `subagents.agentOverrides.<role>.model` + `thinking` (operator-configured profile-to-model mapping) | No Crucible runtime enforcement; without an external mapper, use session/operator default and disclose unverified profile intent. Jev remains optional and its future integration is not implemented here. |

**Observed model is evidence, requested profile is intent (#335 cross-link).** Two readouts must not be conflated:
- The session-index `model_tier` field (`dispatch-convention.md`) records the orchestrator's
  pre-dispatch request. It is intent, not proof that the host applied the requested profile.
- Claude Code may expose the model actually used in its subagent transcript at
  `<project>/<session-id>/subagents/agent-<id>.jsonl` via `message.model`; filter the
  `<synthetic>` sentinel. This can verify a particular run when available, but Crucible does
  not enforce or re-route based on that observation. If the observed model cannot be read, actual
  model is unverified; a profile request alone must not be reported as a model guarantee.

## 3. Mapping 2 — Command-file location

Where the installed file goes. This is the only path an installer needs to write.

| Harness | Location | Invoked as |
|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` (or a plugin-namespaced skills dir) | `/<name>` (the `/code-review` name collision is resolved per-harness via plugin namespacing, not by deleting the capability — design §3) |
| OpenCode | `.opencode/commands/<name>.md` | `/<name>` |
| Codex CLI | the Codex prompts directory (prompt file) | the harness's prompt-invocation convention |
| Cursor | the Cursor commands / rules location | the harness's command-invocation convention |
| Pi | `agents/pi/*.md` symlinked to `~/.pi/agent/agents/` | Crucible skills remain loaded from skill paths; subagent profiles use machine-local `agentOverrides`. |

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
| Pi | `subagent` workflow (`runs.all`) | parallel fan-out using roster roles; protocol defined in `shared/dispatch-convention.md` |

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
- **Agent defs (Claude Code native selectors, Mapping 1b):** symlink `<repo>/agents/*.md` →
  `~/.claude/agents/` (user-level, mirroring the `skills/` symlink — `ln -sf "$PWD"/agents/*
  ~/.claude/agents/`), so `crucible-red-team` / `crucible-qg-judge` / `crucible-qg-verifier` /
  `crucible-qg-fix` are discoverable in every project. Without this step the named `subagent_type`s
  fail to resolve and the requested profile becomes unverified (see Mapping 1b's host limitations / the
  quality-gate fallback warnings). On Claude Code an uninstalled `subagent_type` surfaces as a
  catchable **Task-tool resolution error** — not a silent substitution of a default agent — and that
  observable error is what fires the non-silent fallback warning (hence the trigger is the
  type-resolution failure, not a transcript read). A harness that silently substitutes a default on an
  unknown type cannot fire that warning, so on such a harness install MUST be verified out-of-band —
  this manifest is that check. A symlink that **resolves to a stale clone** (rather than a
  missing/broken symlink) is a class of install fault this tripwire cannot see either: the manifest
  checks *existence* of the four names, not content freshness, so any agent-def *content* change —
  not just this one — requires an explicit install re-verification (verify by resolving the symlink's
  target path and diffing full content against the repo source, e.g.:
  ```
  readlink -f ~/.claude/agents/<name>.md            # must print <repo>/agents/<name>.md
  diff -q <repo>/agents/<name>.md ~/.claude/agents/<name>.md
  ```
  (macOS/BSD `readlink` lacks `-f`; use `python3 -c "import os,sys;print(os.path.realpath(sys.argv[1]))" ~/.claude/agents/<name>.md` instead.)
  — not by inspecting the session roster, which surfaces name/description/tools but not `model:`)
  rather than trusting the symlink's mere presence. Bare-name `subagent_type` resolution for these four defs is **verified
  for the user-level symlink install** (`~/.claude/agents/`, where agents load by bare `name`). Under a
  **plugin install**, Claude Code namespaces plugin agents (`crucible:crucible-red-team`), and
  bare-name `subagent_type` resolution for plugin-provided agents is **UNCONFIRMED** — the docs specify
  scoping for `@`-mention / `--agent`, not for the Task-tool `subagent_type` field (cf. the OpenCode
  row's "Authored-to-spec, UNCONFIRMED" / "#337 confirms" status). Until plugin-scoped dispatch is confirmed, the
  documented Claude Code native binding is available through the **symlink install**; a plugin install whose bare type
  fails to resolve takes the documented **non-silent fallback** above, not silent degradation.
- **Frontmatter:** `name:` + `description:` (Mapping 1).
- **Invoked:** `/<name>` (e.g. `/delve`, `/temper`, `/audit`). `/code-review` built-in stays an
  optional accelerator (I1), never a dependency.
- **Dispatch:** Task / Agent tool, disk-mediated per `shared/dispatch-convention.md` (Mapping 3). Full
  parallel fan-out. Profile-critical roles request the named agent types above; actual model applies
  only where host-native mapping is configured and observed.
- **Degrades:** does not — parallel primitive present.
- **Comments:** forge CLI rows in Mapping 5 (§6) via shell; paste-mode otherwise.

### OpenCode *(runtime validation: non-gating follow-up #337 — BYO reference harness)*
- **Where:** `.opencode/commands/<name>.md`; shared files installed alongside.
- **Agent profiles (Mapping 1b):** author one `agent:` profile per role and name it from the skill
  frontmatter. **Authored-to-spec, unconfirmed** — whether an OpenCode `agent:` profile can apply a
  requested tier is #337's confirmation; otherwise profile intent is unverified and host default applies.
- **Frontmatter:** `description:` + `agent:` + `subtask: true`; body uses `$ARGUMENTS` and `@file`
  includes (Mapping 1).
- **Invoked:** `/<name>`.
- **Dispatch:** one `subtask: true` per angle (Mapping 3).
- **Degrades:** if the host model cannot run subtasks concurrently, falls to Mapping 4 sequential
  passes with the one-time recall warning.
- **Comments:** same forge CLI rows via shell; paste-mode otherwise.

### Codex CLI *(authored-to; runtime validation deferred)*
- **Where:** the Codex prompts directory (prompt file + metadata header).
- **Agent profiles (Mapping 1b):** no first-class per-agent model pin; profile requests are unverified
  unless operator configuration provides mapping. Crucible makes no recall guarantee on this host.
- **Frontmatter:** prompt metadata `name`/description (Mapping 1).
- **Invoked:** the harness's prompt-invocation convention.
- **Dispatch:** no first-class parallel-subagent primitive → **Mapping 4 sequential passes** (one per
  angle) + one-time recall warning.
- **Comments:** `@codex review` is a closed accelerator, not a dependency; `--comment` uses the forge
  CLI rows via shell, else paste-mode.

### Cursor *(authored-to; runtime validation deferred)*
- **Where:** the Cursor commands / rules location.
- **Agent profiles (Mapping 1b):** no first-class per-agent model pin; profile requests are unverified
  unless operator configuration provides mapping. Crucible makes no recall guarantee on this host.
- **Frontmatter:** rule name + description (Mapping 1).
- **Invoked:** the harness's command-invocation convention.
- **Dispatch:** no first-class parallel-subagent primitive → **Mapping 4 sequential passes** + one-time
  recall warning.
- **Comments:** Bugbot is a closed accelerator, not a dependency; `--comment` uses the forge CLI rows,
  else paste-mode.

### Pi *(authored-to-spec; live validation pending)*
- **Where:** symlink `agents/pi/*.md` to `~/.pi/agent/agents/`; invoke Crucible skills through Pi's skill loader or by reading the skill path.
- **Agent profiles:** machine-local `subagents.agentOverrides.<role>.{model,thinking}` binds profile to physical model. Gate-bearing roles block on missing/mismatched bindings; do not inherit or self-review.
- **Dispatch:** `subagent` with the roster role; parallel fan-out via one `runs.all` workflow, per `shared/dispatch-convention.md`.
- **Comments:** forge CLI rows if a shell is available, else paste-mode.

> **Drift risk (design §9, R5).** This is a documented contract, not a runtime check, so it can drift
> from a harness's actual behavior as harnesses evolve. The milestone's defense is the #335 portability
> validation (Claude Code against the fixture) — runtime evidence for the reference harness — with the
> OpenCode runtime floor as the non-gating follow-up #337, plus the I2 grep test for the marker
> invariant. Codex / Cursor / Pi rows are
> authored-to-spec and should be confirmed against the live harness before relying on them.
