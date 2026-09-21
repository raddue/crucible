# Crucible Hooks

Hook scripts for Claude Code's lifecycle events.

## Session Activity Index

The session activity index continuously logs high-value session events (file edits, git operations, test runs, errors) to a persistent JSONL file on disk. This index survives context compaction and powers the `/recall` skill.

### Setup

Add the following to your `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "bash hooks/session-index.sh", "timeout": 500 }
        ]
      }
    ]
  }
}
```

> Each event entry needs a `matcher` plus a nested `hooks` array whose items carry `"type": "command"`. A flat `{ "command": ... }` entry parses but Claude Code silently ignores it, so the hook never fires. `timeout` is in seconds.

### Verification

After enabling the hook, perform a file edit or git commit. Then check for the session index:

```bash
ls ~/.claude/projects/*/memory/session-index/*/events.jsonl
```

If the file exists and contains JSON entries, the hook is working.

### How It Works

1. **PostToolUse hook** (`session-index.sh`) fires after every tool use
2. Classifies the event: file edits, file creates, git commits, git checkouts, test runs, errors
3. Skips read-only operations (Read, Glob, Grep, cat, ls, etc.) to avoid noise
4. Appends a structured JSONL entry to `events.jsonl`
5. Every 20 events (or on phase changes), triggers the summary writer

The **summary writer** (`session-summary.sh`) reads `events.jsonl` and produces a rolling `summary.md` capped at ~2000 tokens. Pipeline skills read this summary during compaction recovery.

### Storage Location

```
~/.claude/projects/<project-hash>/memory/session-index/<session-id>/
  events.jsonl      # append-only event log
  summary.md        # rolling narrative summary
  outbox.jsonl      # temporary: semantic events from skills (drained by hook)
```

- **Project hash:** SHA-256 of the project directory, truncated to 16 chars (matches checkpoint convention)
- **Session ID:** `$CLAUDE_SESSION_ID` env var, or the most recent session directory, or a new epoch-based ID
- **Retention:** Session directories older than 7 days are cleaned up automatically

### Semantic Events (Outbox Pattern)

Pipeline skills can emit semantic events (decisions, phase changes) by writing to `outbox.jsonl` in the session index directory. The hook drains the outbox into `events.jsonl` on its next invocation. See `skills/shared/session-index-convention.md` for the event schema and examples.

### Disabling

Remove the `PostToolUse` entry from your `settings.json`. Existing session index data remains on disk and can be queried with `/recall` until it ages out (7-day retention).

### Dependencies

- `jq` must be installed and on the PATH
- `sha256sum` (standard on Linux, coreutils on macOS) — falls back to `shasum -a 256` when absent, so minimal/older macOS still works

## Gate Ledger Guard

External enforcement hook for the build pipeline's gate ledger. Blocks unauthorized `Status: PASS` writes to `build-gate-ledger.md` when no matching quality-gate verdict marker exists. This is the mechanical enforcement layer — Claude cannot bypass it because it runs as an external process.

### Setup

**Installed automatically** when the crucible plugin is enabled — `.claude-plugin/plugin.json` registers this hook on the `PreToolUse` event (matcher `Write|Edit`) via `${CLAUDE_PLUGIN_ROOT}`, so no manual configuration is needed. See the MIN-5-R6 Parity Note below for details.

For a non-plugin install (running this hook standalone), add the following to your `.claude/settings.local.json` (machine-local, untracked) or `~/.claude/settings.json` (user-level) — never a committed `.claude/settings.json` (see Hook Registration Surface below):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "bash /absolute/path/to/crucible/hooks/gate-ledger-guard.sh", "timeout": 500 }
        ]
      }
    ]
  }
}
```

> **Note:** `"matcher": "*"` — the hook intercepts all PreToolUse events and filters internally for Write and Edit tool calls. This ensures both tools are gated. (You may narrow to `"matcher": "Write|Edit"` to let Claude Code filter upstream; the hook's internal target-path check makes either choice safe.) For the manual path, use an absolute path (S1/CHAIN-N5: a repo-relative path is cwd-dependent).

### Verification

After enabling the hook, test it by attempting to write a PASS status to a gate ledger without a verdict marker. The hook should block with:

```
BLOCKED: Cannot write PASS to gate ledger — no matching verdict marker found.
```

### How It Works

1. **PreToolUse hook** (`gate-ledger-guard.sh`) fires before every Write/Edit tool call
2. Checks if the write target is `build-gate-ledger.md` — exits 0 (allows) for all other files
3. Compares incoming content against the existing file to detect new `Status: PASS` entries per phase
4. If a new PASS is detected, cross-checks against verdict markers in `~/.claude/projects/<hash>/memory/quality-gate/`:
   - PipelineID must match between the ledger content and the verdict marker
   - Verdict must be `PASS`
   - Phase field must match (Phase 1 = "design", Phase 2 = "plan", Phase 4 = "code")
5. Blocks Phase 3 PASS writes (Phase 3 uses COMPLETE, not PASS)
6. **Graceful degradation:** On any infrastructure failure (missing `jq`, missing directories, malformed JSON), exits 0 to avoid blocking legitimate work

### Testing

Run the test suite:

```bash
bash hooks/tests/test-gate-ledger-guard.sh
```

27 test cases covering: non-ledger writes, non-PASS writes, valid markers, missing markers, PipelineID mismatch, missing jq, missing directories, malformed JSON, COMPLETE writes, wrong-phase markers, Phase 3 PASS blocking, first-run bypass, INFERRED-to-PASS promotion, Edit tool PASS introduction, trailing-space PASS, missing PipelineID, PipelineID change detection, legacy `.tool`/`.input` fallback (Write and Edit paths), indented old_string, backslash old_string, double-space phase headers, and non-canonical `build-gate-ledger.md` paths ignored.

`bash hooks/tests/test-plugin-manifest-hooks.sh` separately checks that `.claude-plugin/plugin.json` actually declares the `PreToolUse` registration described above (matcher, `type: command`, `${CLAUDE_PLUGIN_ROOT}` path) — a wiring check, not a runtime liveness check (#591 item 3).

### Dependencies

- `jq` must be installed and on the PATH (gracefully degrades if missing)

### MIN-5-R6 Parity Note

Registered via the plugin, not via manual settings.json (#591). This section previously claimed the hook was "Registered in user-global `~/.claude/settings.json`. Matcher: `Write|Edit` (verified ... on 2026-04-15)" — that was never true; no settings.json ever installed this hook, which is why it sat inert. The durable fact is that `.claude-plugin/plugin.json` declares a `PreToolUse` hook for this script (matcher `Write|Edit`, command `bash "${CLAUDE_PLUGIN_ROOT}/hooks/gate-ledger-guard.sh"`) (#591 item 3), so enabling the plugin installs it automatically. The manual `~/.claude/settings.json` / `.claude/settings.local.json` registration shown in the Setup section above is a fallback for non-plugin installs — redundant, not required, once the plugin is enabled. Whether a given reader's own settings.json additionally declares a redundant `PreToolUse` entry for this script is machine-local and can drift between developers — check your own files rather than trusting a hook inventory recorded here. `build-routing-advisor` (below) remains in the state this hook used to be in: it is NOT registered via the plugin, and its Setup section is a manual-registration instruction, not a description of an existing registration.

## Build Routing Advisor

Warn-only PreToolUse hook on the `Agent` matcher (canonical per T1; legacy `Task` alias honored for back-compat). It inspects subagent dispatch payloads and emits a 2-line ADVISORY on stderr when the dispatch prompt looks build-shaped (design + implement + ship keywords) and no active pipeline marker matches the current branch. The hook always exits 0 — it never blocks — and its sole output is the advisory text on stderr. It complements `gate-ledger-guard` (which enforces ledger writes) by catching the earlier failure mode of dispatching a general-purpose subagent for multi-phase work instead of routing through `/build`.

### Setup

Add the following to **user-global `~/.claude/settings.json`** (NOT `.claude/settings.json` at the repo root — same scope as `gate-ledger-guard`, per the #168 README convention). **The one stated exception to that convention is `grudge-resolution-guard.sh` (#559)**, which registers repo-scoped in the committed `.claude/settings.json` at the repo root: it is a *blocking* hook whose subject matter is crucible-only (grudge write-discipline for this repo's own `fix(*)` commits), so it must not fire — let alone block a Stop — in every unrelated project the maintainer works in, the way a user-global registration would. See Grudge Resolution Guard below.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          { "type": "command", "command": "bash /absolute/path/to/crucible/hooks/build-routing-advisor.sh", "timeout": 500 }
        ]
      }
    ]
  }
}
```

> **Matcher note:** `Agent` is the canonical tool name per T1's payload-capture finding. Older Claude Code builds emitted the legacy alias `Task`; the hook accepts either internally. If your build emits `Task`, register the matcher as `Task` instead — the hook script handles both values via its internal `case "$TOOL" in Task|Agent)` branch.

### How It Works

1. **Read stdin** — cat the JSON payload; empty → exit 0.
2. **Env-var kill-switch** (runs BEFORE jq/extraction so every invocation honors it cheaply): if `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1`, derive a scoped `PROJECT_ROOT` / `PROJECT_MEMORY`, short-circuit if today's `last-honored` is already recorded, otherwise explicit-RMW the state file preserving counters + dedup fields, then exit 0.
3. **jq dependency check** — missing jq → exit 0.
4. **Tool-name extraction** — `.tool_name // .tool // empty`; accept `Task|Agent`, else exit 0.
5. **Prompt + subagent_type extraction** — `.tool_input.prompt`, `.tool_input.subagent_type`; both empty → exit 0. Also read `.session_id` from the payload (NOT `$CLAUDE_SESSION_ID`, which is not exported).
6. **Allowlist gate** — only `subagent_type == "general-purpose"` is advisable; empty or specialty subagent_type → exit 0 (empty treated as SPECIALTY — indistinguishable from MCP types).
7. **Disclaimer skip** — anchored regex on start-of-prompt or after sentence-boundary punctuators, matching `just the design`, `design only`, `no implementation`, `review only`, `audit only`, `spec only`, `recon only` → exit 0.
8. **Classification** — three categories counted via `grep -ioE '\b…\b'`:
   - **Design:** `design`, `spec`, `plan`
   - **Implement:** `implement`, `code`, `create`, `refactor`
   - **Ship:** `PR`, `commit`, `merge`, `push`, `land`, `ship`

   `TOTAL_DISTINCT` is the number of distinct lowercased keywords hit across all three categories (via `sort -u | wc -l`).

   **Trigger rule:** `IMPLEMENT ≥ 1 AND (DESIGN ≥ 1 OR SHIP ≥ 1) AND TOTAL_DISTINCT ≥ 2`. If not triggered → exit 0.
9. **Lazy PROJECT_ROOT derivation** (MIN-3) — `git rev-parse --show-toplevel` on the current cwd; falls back to `pwd` outside a git repo. Prevents cwd drift between dispatches from breaking derivation.
10. **Sentinel kill-switch** — if `$PROJECT_MEMORY/.build-routing-advisor-disabled` exists, honor it (with optional auto-expiry — see Kill Switch below).
11. **Marker check** — inspect `$PROJECT_MEMORY/.pipeline-active` (see Suppression Rules).
12. **Dedup** — SHA256(prompt) truncated to 16 hex chars; suppress if same fingerprint within 5 minutes (increments `fires-total` but not `fires-today`, no advisory emitted).
13. **Emit advisory** — exactly 2 lines on stderr:
    - `ADVISORY: Dispatch looks build-shaped. If single-phase, ignore.`
    - `Else prefer /build (or /spec then /build) for gate coverage.`
14. **Atomic state write** — `cat > state.tmp && mv state.tmp state` with updated counters and fingerprint.

### JSON Extraction Path

Per T1's payload-capture finding, the canonical JSON paths are:

- **Tool name:** `.tool_name` (canonical), with `.tool` accepted as a legacy fallback (M1-R4).
- **Prompt:** `.tool_input.prompt` (with `.input.prompt` as legacy fallback).
- **Subagent type:** `.tool_input.subagent_type` (with `.input.subagent_type` as legacy fallback).
- **Session id:** `.session_id` from the payload itself — **`$CLAUDE_SESSION_ID` is NOT exported to hook subprocesses**, so the env-var path is unreliable. Always read `.session_id` from stdin JSON.

### Suppression Rules

The pipeline-active marker at `$PROJECT_MEMORY/.pipeline-active` suppresses the advisory when ALL of the following hold:

- `.skill` ∈ `{build, spec, debugging, migrate}`
- `.start_time` parses as ISO-8601 (`^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}`) AND is within 24h of now. Unparseable or non-ISO-8601 values are treated as **stale**, not silently honored (plan line 275) — a numeric literal like `"0"` would parse via GNU `date -d` as today's midnight and spuriously suppress the advisory; the regex prefilter prevents this.
- Branch match:
  - Both `.branch` and `git branch --show-current` non-empty and equal → active.
  - **Detached-HEAD symmetric fallback:** both empty AND payload `.session_id == .pipeline_id` → active. When session-id match is unavailable (either side empty), fall back to a **5-minute `.start_time` session-proxy window** (M9-R4, T2 adjustment).
  - Asymmetric empty or explicit branch mismatch → NOT active (plan S3).

### Kill Switch

Two disable paths:

- **Env var:** `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1`. Note: hook subprocesses do NOT auto-source `.envrc` or direnv hooks, so this must be exported from the user's shell init (`.bashrc`, `.zshrc`, or a shell-init wrapper). A `.envrc`-only export will NOT propagate to the hook.
- **Sentinel file:** `$PROJECT_MEMORY/.build-routing-advisor-disabled` (preferred — does not require shell init). Optional contents:
  - A line `disabled-until: YYYY-MM-DD` enables **auto-expiry** — when `date -d` on the value succeeds and today is before the parsed date, the hook honors the sentinel; after the date, the sentinel is ignored (fall-through to normal advisor flow).
  - A **malformed** `disabled-until:` value (unparseable by `date -d`) is treated as **permanently disabled** (fail-safe), and the raw value is preserved under `disabled-until-parse-error:` in the state file for forensics (FIX 4 / Min-1-R6 / 2P-3-R5).
  - Sentinel file with no `disabled-until:` line at all → honored indefinitely.

### Cross-project firing (M6)

> This hook is registered user-globally in `~/.claude/settings.json`. It fires on subagent dispatches from ANY project where the user works. Outside crucible, there is no `.pipeline-active` marker so suppression never applies; a build-shaped dispatch in an unrelated project will emit the advisory. For per-project disable, create the sentinel file `$PROJECT_MEMORY/.build-routing-advisor-disabled` (preferred — does not require shell init). The env-var path `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` requires the user's shell init (e.g. `.bashrc`, `.zshrc`, or a shell-init wrapper) since hook subprocesses do NOT auto-source `.envrc` or direnv hooks — a `.envrc`-only export will NOT propagate. The design accepts this cross-project fire surface as a tradeoff for the broader enforcement.

### State File

Path: `$PROJECT_MEMORY/build-routing-advisor-state.md`

Schema (column-0-anchored, one field per line; bounded growth ≤6 lines default, up to 7 under the parse-error branch):

```
last-honored: YYYY-MM-DD
fires-today: <int>
fires-total: <int>
last-advisory-at: YYYY-MM-DDTHH:MM:SSZ
last-advisory-fingerprint: <16 hex chars>
```

Optional fields:

- `schema-version: 1` — reserved for forward-compatible schema migrations; preserved across RMW operations.
- `disabled-until-parse-error: <raw value>` — present only under the sentinel parse-error path (fail-safe branch); records the malformed `disabled-until:` value for forensics.

All writes are atomic (`cat > .tmp && mv .tmp state`). Every read uses `tr -d '\r'` to tolerate CRLF line endings (FIX 1).

### Performance

Combined budget with `gate-ledger-guard`: **≤200ms P95** over ≥20 Agent/Task dispatches. The advisor's hot-path cost is dominated by a handful of `grep`/`jq` invocations on a small stdin payload plus one atomic state-file rewrite.

**P95 (warm cache, N=20, method (a) per plan line 605):**
- `build-routing-advisor` alone (non-build-shaped fixture): 44 ms
- `build-routing-advisor` alone (build-shaped fixture, trigger fires): 122 ms
- `gate-ledger-guard` alone (non-ledger Write fixture): 18 ms
- **Combined per-dispatch P95 (advisor build-shaped + guard): 138 ms** — hard gate ≤200ms: PASS

Bash startup cost: ~10–20ms per invocation on WSL (SP5); budget accommodates this.
Real-run P95 not measurable without Claude Code runtime timing API; fixture P95 is the proxy by design.

### Graceful Degradation

The hook must never fail fatally (`set +e` at top, exit 0 on every path):

- Missing `jq` → exit 0.
- Malformed JSON (jq parse failure) → `empty` results cascade → exit 0.
- Missing utilities (`sha256sum`, `date`, etc.) → degraded check skipped, exit 0.
- State-file column-0 invariant broken → preserve file for forensics, exit 0 (warn-only).

### Testing

```bash
bash hooks/tests/test-build-routing-advisor.sh
```

Current case count: **34** (10 RED canary + 24 T3.5 extended); see the test file for the full breakdown by case name.

### Static-analysis fallback (T8) — known brittleness (M6)

T8's method-(b) static-analysis check greps line-numbers in pipeline-skill `SKILL.md` files (marker-write line number vs. first Task-dispatch line number). This check is **brittle against future markdown reorganization**: if pipeline-skill `SKILL.md` files are restructured (headings renamed, sections reordered, Task invocation documented in a different syntax), the check can silently pass on broken ordering or fail on correct ordering. **Future pipeline-skill refactors MUST update this check alongside the SKILL.md change** to keep the ordering invariant enforced.

## Post-Merge Reconciler (T9)

Read-only telemetry utility at `hooks/tests/tools/build-routing-reconcile.sh`. For each merged PR in a configurable window, it answers the binary question: **"Did this PR's branch write `Status: PASS` to `build-gate-ledger.md`?"** — the #174 ground-truth oracle. PRs with no gate-ledger PASS are flagged as candidates for the #174 failure mode (branch merged without `/build` running).

### Invocation

```bash
# Markdown report to stdout (default)
bash hooks/tests/tools/build-routing-reconcile.sh --since "14 days ago"

# JSON, to a file, for an arbitrary repo
bash hooks/tests/tools/build-routing-reconcile.sh --repo /path/to/repo --since 2026-04-01 --json --output report.json

# Append to the local /forge scratchpad
bash hooks/tests/tools/build-routing-reconcile.sh --forge
```

Arguments: `--since <date>`, `--repo <path>`, `--output <file>`, `--json`, `--forge`. The tool is READ-ONLY: it never mutates repo state, never registers as a hook, and never gates anything. It is intended for manual invocation by the maintainer (or a periodic cron/CI job).

### Testing

```bash
bash hooks/tests/tools/test-build-routing-reconcile.sh
```

Synthetic 2-PR fixture: one branch seeds `Status: PASS` in the ledger, one does not. Asserts flagged count == 1.

### Degraded mode (M10-R4) — honest limits

This reconciler currently runs in **gate-ledger-audit-only mode** because `hooks/session-index.sh` does NOT index `Task` tool invocations (verified via `grep -nE 'Task|subagent_type' hooks/session-index.sh` → no matches). The following honest-limits statement is reproduced verbatim from the plan's T9 M10-R4 requirement:

> In degraded mode, T9's output is an INPUT to manual maintainer review — NOT an actionable automated signal for the "remove Part 2 if cost > value" decision promised by the design's Honest-about-limits clause. That decision requires archived advisor state + session-index Task coverage, neither of which exists yet. Deferral to a separate PR with archived advisor state is the prerequisite for automating that decision.

Two capabilities MUST be added before the reconciler can support the promised precision/recall / cost-value decision path:

1. **Session-index `Task` tool indexing** — so per-PR `general-purpose` dispatch counts can be computed (plan step 7).
2. **State-file archiving** for `build-routing-advisor-state.md` — so per-PR advisor fire counts can be correlated historically (plan step 6; the live state file is overwritten, so historical enrichment is unavailable at first run).

### PR discovery path

Primary: `gh pr list --state merged --search "base:main merged:>=<SINCE>"` (handles squash-merged PRs uniformly). Fallback: `git log --merges --since=<SINCE>` (misses squash-merges; reports `pr_discovery_path: git-log-fallback` in the output so consumers know the coverage).

## Receipt Verifier (SubagentStop, #369)

`hooks/rcpt-verify-hook.sh` is a **never-fatal, pure-observer** SubagentStop advisory.
When a subagent stops, it extracts the last text-bearing assistant message from the
transcript and — if it carries an `RCPT v1` receipt block — runs the Tier-1 structural
lint (`scripts/rcpt_verify.py --tier1 -`) over it, emitting a 2-line ADVISORY on stderr
if the receipt is malformed. It **always exits 0** and performs **NO writes** (it does
not block, edit, or record anything).

### Setup (opt-in — NOT auto-enabled)

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "bash /absolute/path/to/crucible/hooks/rcpt-verify-hook.sh", "timeout": 500 }
        ]
      }
    ]
  }
}
```

### How It Works

1. Reads the SubagentStop JSON on stdin; `transcript_path` via `jq`. Missing `jq` /
   `python3` / empty or unreadable transcript → `exit 0` silently.
2. Selects the **last** record with `.message.role == "assistant"` whose content yields
   non-empty text (a verbatim string, or the concatenated `.text` of `type=="text"`
   blocks). Unrecognized shape / parse error / no text → `exit 0` silently.
3. Gate: if the text contains no `RCPT v1` token → `exit 0` silently. Otherwise extracts
   from the first column-0 `RCPT v1 ` line to end-of-message.
4. Resolves the linter from **this hook script's own installed location**
   (`$(dirname "$0")/../scripts/rcpt_verify.py`) — NOT from `git rev-parse
   --show-toplevel` on the session's cwd, which would pick up whatever repo
   the session happens to be visiting (SIEGE-CA-4/IP-1: a repo containing an
   unrelated file at that path would get it executed with the agent's full
   privileges). Gates on `[ -f "$LINTER" ]`, so a SubagentStop still exits 0
   silently with no spurious advisory if the install is broken.
5. Pipes the receipt block to `--tier1 -`. On non-zero, prints the `[rcpt-verify]`
   advisory (first stderr bullet) and **still exits 0**.

### Testing

```bash
bash hooks/tests/test-rcpt-verify-hook.sh
```

### Dependencies

`jq` and `python3` — both absent-tolerant (the hook exits 0 silently when either is
missing). No `git` dependency beyond the optional repo-root resolution (absent → exit 0).

## Grudge Resolution Guard

Blocking **Stop** hook enforcing grudge write-discipline for this repo (#559). It is crucible's first Stop hook and its first hook that blocks the turn: while a `fix(*)` commit that landed in this session's window — and touched at least one non-`.md` file — still has neither a grudge record nor a `skips.log` entry, the hook exits 2 and Claude Code refuses the Stop. It backstops the LLM-authored grudge-recording steps in `skills/debugging/SKILL.md` and `skills/merge-pr/SKILL.md` Step 7.5: those still do the recording, this catches the case where they were skipped. Every block is bounded — see MAX_BLOCKS below — so a session can never be trapped.

### Setup (opt-in — NOT committed; #604)

#559 originally shipped this hook registered in a committed `.claude/settings.json`. That is an RCE surface (GH-604 / siege S-1: a reviewer's `gh pr checkout N` would run the branch's Stop hook and whatever `scripts/` helper it names with the reviewer's privileges), so — like every other hook on this page — this one is registered **per-machine** and never in a committed `.claude/settings.json`. Register it for one machine, to `.claude/settings.local.json` (repo-local, gitignored) or user-global `~/.claude/settings.json`, referencing the hook by its absolute installed path (`$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh`), `type: command`, `timeout: 500`:

```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh\"", "timeout": 500 } ] } ] } }
```

Scope is deliberately repo-local (this hook *blocks* the turn on crucible-only subject matter; it must never fire in an unrelated project). `check_settings_surface.py` keeps the committed-config prohibition mechanical (see the Hook Registration Surface section below). Missing registration = the hook never fires = #559 compliance is simply not enforced on that machine (fail-open).

The hook caps its own per-invocation work with a **per-Stop wall-clock budget** (`CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS`, default `8`, issue #603): candidate count (up to the `--max-count=500` scan, and accumulable turn-over-turn through future-dated author times), files per commit, and the stored grudge count are all attacker-multiplied inputs, and when the budget is spent the hook degrades **loudly to allow** (`exit 0`) rather than stall the Stop — 362 s measured on a single Stop before the budget existed. `timeout: 500` is retained only as the ceiling for the one failure class the loud-allow cannot help with: a hook that *hangs* outright (a `git` call against a corrupted or network-mounted repo that never returns), where the budget's own clock never advances.

`timeout: 500` (seconds) matches this repo's other hooks, but for a blocking Stop hook it is deliberately **not** the bound the hook relies on. The hook caps its own per-invocation work with a **per-Stop wall-clock budget** (`CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS`, default `8`, issue #603): candidate count (up to the `--max-count=500` scan, and accumulable turn-over-turn through future-dated author times), files per commit, and the stored grudge count are all attacker-multiplied inputs, and when the budget is spent the hook degrades **loudly to allow** (`exit 0`) rather than stall the Stop — 362 s measured on a single Stop before the budget existed. `500` is retained only as the ceiling for the one failure class the loud-allow cannot help with: a hook that *hangs* outright (a `git` call against a corrupted or network-mounted repo that never returns), where the budget's own clock never advances.

### How It Works

1. **Stop hook** (`grudge-resolution-guard.sh`) fires on every Stop event. Exit 0 allows, exit 2 blocks — Claude Code's Stop contract only blocks on 2.
2. Derives `PROJECT_ROOT` / `PROJECT_MEMORY` and touches `$PROJECT_MEMORY/grudge-guard/.last-run` as execution evidence, **before** either kill-switch, so even a disabled invocation records that it ran.
3. **Session window** — on the first Stop of a session it seeds `seeded_at` from the earliest timestamp in the transcript (falling back, loudly, to wall-clock now) and scans `git log --no-merges --max-count=500`; later Stops rescan only `<last_checked_sha>..HEAD`. The first scan therefore reaches **backwards** over commits made earlier in the same session.
4. **Candidate filter** — a commit is in scope when its subject matches `^fix[(:]`, its author date is `>= seeded_at`, and it touched at least one non-`.md` path. Documentation-only fixes never block.
5. **Grouping** — candidates that share changed files are grouped, so one grudge clears the whole group rather than one commit at a time.
6. **Clearance** — a group clears when `grudge_query.py` finds a matching grudge (looked up by commit and by changed files, under the shared-clone identity so any worktree of the clone counts), or when any member SHA appears in `$PROJECT_MEMORY/grudge-guard/skips.log`.
7. **Bounded blocking** — each still-unresolved group carries a block counter; the message reads `attempt (n/3)`. At `MAX_BLOCKS=3` the hook **gives up loudly** and allows the Stop, stating plainly that compliance was not enforced. A block is only ever issued when this Stop can prove its counter advanced on disk; if it cannot, the Stop is allowed instead, because a frozen counter would make the loop unbreakable.
8. **Never fail closed** — missing `jq`/`git`, a malformed payload, an unreadable transcript, a non-git cwd, an absent grudge store, an unwritable state dir, or a spent cost budget all exit 0.
9. **Cost budget** — a per-Stop wall-clock budget (`CRUCIBLE_GRUDGE_GUARD_MAX_SECONDS`, default `8` s) is checked around every potentially-expensive step: the `--max-count=500` scan, the per-candidate `git diff-tree` fan-out, the file-similarity grouping (`_overlap`, whose nested loop squares candidate count × files-per-commit), and the `grudge_query.py` clearance subprocesses. When the budget is spent the hook prints a loud degradation note and allows the Stop (`exit 0`) — an attacker-chosen input can stall a Stop for at most the budget, never for a whole turn (#603). The allow is a *rescan-on-next-Stop*, not a clearance: the `last_checked_sha` checkpoint only advances on a normal pass, so an unresolved `fix(*)` commit whose Stop ran out of budget is checked again next time, under the same budget.

The block message and the give-up note each carry, above the `skips.log` escape hatch, a fully-resolved copy-pasteable `grudge_append.py` command — one per still-unresolved candidate SHA — prefilled with the hook's own clearance identity (`--repo-root`/`--repo`) and the candidate's NUL-delimited touched-path file (`--files-from="$STATE_DIR/<sha>.files"`, which the shell passes through unparsed; the hook renders no file name). Recording the grudge is then one paste plus a symptom line (Innovate incorporation (2026-08-30)).

### State

```
$PROJECT_MEMORY/grudge-guard/
  <session-id>.json   # version, last_checked_sha, seeded_at, sha_group, block_counts
  <sha>.files         # NUL-delimited touched paths for a candidate (one per sha)
  skips.log           # one `<sha> <reason>` line per deliberately-skipped commit
  .last-run           # touched on every invocation (execution evidence)
```

`skips.log` is a flat file, deliberately separate from the per-session JSON, so it survives across sessions and can be appended by hand. A state document whose `version` disagrees with the hook's `STATE_VERSION` is discarded and re-written fresh on the next scan.

### Kill Switch

Two disable paths, both honored **after** the `.last-run` breadcrumb so a disabled invocation is still visible:

- **Env var:** `CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD=1`. As with the other hooks, this must be exported from shell init — hook subprocesses do not source `.envrc`/direnv.
- **Sentinel file:** `$PROJECT_MEMORY/.grudge-resolution-guard-disabled` (preferred — no shell init needed). Either path prints a loud stderr note that `fix(*)` commits are not being checked.

> **Per-worktree residual:** `$PROJECT_MEMORY` is derived from `git rev-parse --show-toplevel`, so each worktree of the same clone gets its OWN memory directory — and therefore its own sentinel and its own `skips.log`. Disabling the hook in one worktree does not disable it in another; a skip recorded in one worktree does not clear the commit in another. (Grudge *records* are unaffected: clearance queries use the shared-clone identity deliberately, so a recorded grudge clears every worktree.)

### Verification

Registration and execution evidence (did the hook actually *fire*) are two different questions. Whether the hook is registered on THIS machine is a per-machine, untracked fact — `scripts/check_settings_surface.py` enforces the prohibition on *committed* config, and the `.claude/settings.local.json` / `~/.claude/settings.json` registration above is checked the way any per-machine config is: by inspecting your own files, not a hook inventory. Execution evidence is `$PROJECT_MEMORY/grudge-guard/.last-run` (outside the repo, so it survives `git clean`). End a turn and inspect the breadcrumb's mtime:

```bash
date > /tmp/before-stop-time
# ... end the turn, let Stop fire ...
PROJECT_MEMORY="$HOME/.claude/projects/$(git rev-parse --show-toplevel | tr / -)/memory"
test "$PROJECT_MEMORY/grudge-guard/.last-run" -nt /tmp/before-stop-time && echo "hook fired" || echo "hook did NOT fire"
```

`$PROJECT_MEMORY` is spelled out rather than referenced by name on purpose: it is a variable computed *inside* the hook's own process and is not exported to your shell, so a `test "$PROJECT_MEMORY/..."` copied verbatim would expand to an empty prefix and error on a missing operand instead of giving a clean pass/fail. Run this snippet once on a real checkout after this lands — it is the one property no fixture or check script can substitute for.

## Hook Registration Surface (#604)

Repo-owned hooks (`hooks/*.sh`) are registered in **per-machine, untracked config** —
never in a committed `.claude/settings.json`. A committed `settings.json` that
registers an executable hook turns every PR checkout into an arbitrary-code
execution surface on the reviewer's machine (GH-604, siege S-1): Claude Code's
directory trust is per-directory, so checking out a branch inside an
already-`/trust`ed repo does not re-prompt, and a reviewer's `gh pr checkout N`
runs the branch's hook (and whatever `scripts/` helper it names) with the
reviewer's full privileges on the next Stop.

The per-machine settings registration points are `.claude/settings.local.json`
(machine-local, untracked — the whole `.claude/` directory is git-ignored, and
`scripts/check_settings_surface.py` fails the gate if any of it is re-tracked)
and user-global `~/.claude/settings.json` (the `build-routing-advisor`
convention). Both make the hook's execution surface opt-in per machine rather
than automatic per clone. A registration command must reference the hook by its
**absolute installed path** (or `$CLAUDE_PROJECT_DIR`); the machine that
installed it is the machine that accepts the surfaced code.

A third, distinct mechanism is the plugin manifest: `.claude-plugin/plugin.json`
may declare a `hooks.PreToolUse` entry (as `gate-ledger-guard` now does, #591),
which fires only after the user explicitly enables the crucible plugin on their
machine. This is per-machine opt-in exactly like the settings points — enabling
a plugin is an affirmative execute-code grant, not a checkout side-effect — so
it does not create the GH-604 surface. The prohibition above targets committed
`.claude/settings.json`, which auto-loads on checkout without fresh consent.

Review rule: every PR touching a `hooks/` or `scripts/` diff (or
`.claude-plugin/plugin.json`, which carries hook-execution config — command,
matcher, timeout) gets full review before merge — those files execute with the
maintainer's privileges.

### Testing

```bash
bash hooks/tests/test-grudge-resolution-guard.sh   # hook behavior
python3 scripts/check_settings_surface.py --selftest   # registration surface (pre-quick)
python3 scripts/check_settings_surface.py
```


### Dependencies

- `jq` — required for payload parsing and state I/O; absent → exit 0 (allow).
- `git` — absent, or a cwd outside a work tree → exit 0 (allow).
- `python3` — runs `scripts/grudge_query.py` for clearance lookups.
- **GNU coreutils `date`** — the `seeded_at` derivation uses `date -u -d "<transcript timestamp>" +%s`. BSD/macOS `date` has no `-d` and yields an empty epoch; under the hook's `set +e` that falls through to the wall-clock fallback and, in the degenerate case, to a hook that never blocks. That degradation is fail-open by design (consistent with the never-fail-closed contract), but on macOS install `coreutils` and put `gdate`'s GNU `date` first on PATH if you want real enforcement.
