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

Add the following to your `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "bash hooks/gate-ledger-guard.sh", "timeout": 500 }
        ]
      }
    ]
  }
}
```

> **Note:** `"matcher": "*"` — the hook intercepts all PreToolUse events and filters internally for Write and Edit tool calls. This ensures both tools are gated. (You may narrow to `"matcher": "Write|Edit"` to let Claude Code filter upstream; the hook's internal target-path check makes either choice safe.) The maintainer's actual user-global registration uses `Write|Edit` (see the MIN-5-R6 Parity Note below); the `*` shown here is simply the simplest illustrative form.

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

17 test cases covering: non-ledger writes, non-PASS writes, valid markers, missing markers, PipelineID mismatch, missing jq, missing directories, malformed JSON, COMPLETE writes, wrong-phase markers, Phase 3 PASS blocking, first-run bypass, INFERRED-to-PASS promotion, Edit tool PASS introduction, trailing-space PASS, missing PipelineID, and PipelineID change detection.

### Dependencies

- `jq` must be installed and on the PATH (gracefully degrades if missing)

### MIN-5-R6 Parity Note

Registered in user-global `~/.claude/settings.json`. Matcher: `Write|Edit` (verified by reading `~/.claude/settings.json` on 2026-04-15). Because a concrete matcher is set, Claude Code filters upstream and only Write/Edit PreToolUse events reach the hook — no internal filtering is needed for other tool families. The hook still internally filters by target path (`build-gate-ledger.md`) and exits 0 for every other file. By contrast, `build-routing-advisor` registers `matcher: "Agent"` (canonical per T1; legacy alias `"Task"` also honored) in the SAME user-global `~/.claude/settings.json`. Both hooks share scope (user-global, not `.claude/settings.json` at the repo root) and are documented side-by-side so the matcher choices are explicit for parity.

## Build Routing Advisor

Warn-only PreToolUse hook on the `Agent` matcher (canonical per T1; legacy `Task` alias honored for back-compat). It inspects subagent dispatch payloads and emits a 2-line ADVISORY on stderr when the dispatch prompt looks build-shaped (design + implement + ship keywords) and no active pipeline marker matches the current branch. The hook always exits 0 — it never blocks — and its sole output is the advisory text on stderr. It complements `gate-ledger-guard` (which enforces ledger writes) by catching the earlier failure mode of dispatching a general-purpose subagent for multi-phase work instead of routing through `/build`.

### Setup

Add the following to **user-global `~/.claude/settings.json`** (NOT `.claude/settings.json` at the repo root — same scope as `gate-ledger-guard`, per the #168 README convention):

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

> This hook is registered user-globally in `~/.claude/settings.json`. It fires on subagent dispatches from ANY project where the user works. Outside crucible, there is no `.pipeline-active` marker so suppression never applies; a build-shaped dispatch in an unrelated project will emit the advisory. For per-project disable, create the sentinel file `<project-root>/.build-routing-advisor-disabled` (preferred — does not require shell init). The env-var path `CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1` requires the user's shell init (e.g. `.bashrc`, `.zshrc`, or a shell-init wrapper) since hook subprocesses do NOT auto-source `.envrc` or direnv hooks — a `.envrc`-only export will NOT propagate. The design accepts this cross-project fire surface as a tradeoff for the broader enforcement.

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
