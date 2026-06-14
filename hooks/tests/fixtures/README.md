# PreToolUse Agent-dispatch fixtures (captured for #174 T1)

Captured **2026-04-15** from a live Claude Code session via a temporary
PreToolUse matcher=`"Task"` hook pointed at `/tmp/capture-pretooluse.sh` (hook
reverted post-capture). These fixtures pin the exact JSON shape Claude Code
sends to PreToolUse hooks on subagent dispatches, for downstream
test/fixture use by `hooks/build-routing-advisor.sh`.

## Fixtures

### `agent-pretooluse-sample.json` — PRIMARY

- Role: raw `general-purpose` subagent dispatch.
- Dispatch prompt: `echo hello to stdout` (deterministically NON-build-shaped;
  zero matches against the advisor's classification keywords).
- Purpose: primary fixture for trigger-classification testing (T3, T3.5).
  Load-bearing for T3.5 case 17(a): piped to the hook, stderr MUST be empty
  (no advisory fires because `TOTAL_DISTINCT == 0`).

### `agent-pretooluse-build-internal-sample.json` — SECONDARY

- Role: non-`general-purpose` (`Explore`) subagent dispatch.
- Dispatch prompt: `List files in /tmp, one command only`.
- Substitutes for the plan's original `/build`-internal specialty payload. A
  nested `/build` dispatch was infeasible at capture time because this
  pipeline's `.pipeline-active` marker is load-bearing for the orchestrator;
  an `Explore` dispatch produces an equivalent non-general-purpose payload
  that satisfies T3.5 case 17(b) allowlist-suppression coverage
  (`subagent_type != "general-purpose"` → advisory suppressed).
- Purpose: T3.5 allowlist-suppression testing.

## Empirical extraction paths (verified 2026-04-15)

| Datum | JSON path | Notes |
|---|---|---|
| Tool-name field | `.tool_name` | **NOT** `.tool` — plan line 105 question answered. |
| Tool-name value | `"Agent"` | **NOT** `"Task"` — important divergence from plan / existing RED test assumption. |
| Prompt | `.tool_input.prompt` | |
| Subagent type | `.tool_input.subagent_type` | |
| Session ID | `.session_id` | Top-level string. **Use this instead of `$CLAUDE_SESSION_ID`** (env var is unset). |
| Cwd | `.cwd` | Top-level absolute path (matches git-rev-parse-toplevel result). |
| Transcript path | `.transcript_path` | Confirms Claude Code's dash-sanitized projects-dir convention. |

## Environment findings

| Variable | Exported? | Value | Implication |
|---|---|---|---|
| `CLAUDE_SESSION_ID` | **NO** | — | Plan AC S1-R6 conditional applies. T2 must use payload's `.session_id`, not env var. |
| `CLAUDE_PROJECT_DIR` | YES | `/home/user/crucible` | Matches git-rev-parse; available as an alternative derivation path. |
| `pwd` | — | `/home/user/crucible` | Matches cwd + git-rev-parse. |
| `git rev-parse --show-toplevel` | — | `/home/user/crucible` | Matches. PROJECT_ROOT derivation is portable. |

## Marker-path verification (plan S3-R1)

- Live on-disk `.pipeline-active` marker (this pipeline) observed at:
  `~/.claude/projects/-home-user-crucible/memory/.pipeline-active`
- Derivation rule: `~/.claude/projects/$(echo "$PROJECT_ROOT" | tr '/' '-')/memory/.pipeline-active`
- The `transcript_path` in the captured payload also uses the dash-sanitized
  projects directory (`-home-user-crucible`), confirming Claude Code's
  native convention. **The advisor MUST use `tr '/' '-'`, NOT the sha256
  derivation used by `hooks/session-index.sh`** — those write to different
  directories for unrelated reasons (pre-existing divergence, not this
  ticket's scope).

## Matcher semantics — surprising empirical finding

The capture hook was registered with `"matcher": "Task"` in `settings.json`,
yet fired on a payload whose `tool_name` is `"Agent"`. This implies Claude
Code maintains a legacy alias from `Task` (historical) to `Agent` (current),
or the matcher field is non-strict.

**Recommendation for downstream tasks:**
- T2 hook registration example + T6 README: use matcher `"Agent"` (canonical,
  future-safe). The `"Task"` alias is incidentally observed but should not be
  documented as authoritative.

## Privacy

User-specific values (session UUID, `tool_use_id`, transcript path username)
were replaced with stable fixture placeholders (`fixture-session-...`,
`toolu_fixture_primary` / `_secondary`, `/home/USER/...`). The raw captured
payload remains in the user's local `/tmp/pretooluse-capture.log` and is not
committed.
