# Trajectory Capture Reference

Trajectory capture records structured data about real skill invocations for eval generation. It is OFF by default and requires explicit opt-in.

## Configuration

Check for `~/.claude/projects/<hash>/memory/trajectory-config.json` before any trajectory operation. If the file does not exist or `enabled` is false, skip all trajectory recording silently.

Config schema:

```json
{
  "enabled": false,
  "max_entries": 500,
  "include_prompt_summary": true,
  "additional_redact_patterns": []
}
```

- `enabled`: Master switch. Default false.
- `max_entries`: Maximum entries per JSONL file before oldest are pruned. Default 500.
- `include_prompt_summary`: Whether to include the one-line redacted prompt summary. If false, `prompt_summary` is set to "[omitted]". Default true.
- `additional_redact_patterns`: List of regex strings for project-specific secret patterns applied during the redaction pass.

## Storage

All trajectory data lives alongside other forge data:

```
~/.claude/projects/<hash>/memory/trajectories/
  trajectory_samples.jsonl     # Successful completions
  failed_trajectories.jsonl    # Failures, partial completions, aborts
```

## First-Enable Notification

When trajectory capture is first enabled (config file is created or `enabled` transitions from false to true), output to the user:

"Trajectory capture is now enabled. Here is what this means:
- After each significant skill invocation, a structured record is appended to
  ~/.claude/projects/<hash>/memory/trajectories/
- Records include: skill name, duration, tool call count, outcome, and a redacted
  task summary. Raw prompts are NEVER stored.
- A redaction pass runs before every write to strip file paths, secrets, and
  sensitive content.
- You can inspect the JSONL files at any time. They are human-readable.
- To disable, set enabled: false in trajectory-config.json or delete the file."

## Redaction Rules

Before writing ANY trajectory entry, apply these redaction steps in order:

1. **Prompt summary generation**: Do NOT copy the user's prompt. Instead, generate
   a one-line summary that captures the task TYPE without revealing specific content.
   Good: "Add authentication middleware to REST API"
   Bad: "Add JWT auth to the Acme Corp billing API at /srv/acme/billing/api.py"
   If `include_prompt_summary` is false in config, set `prompt_summary` to "[omitted]".

2. **File path normalization**: Replace absolute paths with project-relative paths.
   Replace home directory segments with `~`. Replace username segments with `[user]`.
   Example: `/home/alice/projects/myapp/src/auth.py` becomes `~/projects/myapp/src/auth.py`
   or `src/auth.py` if within the project root.

3. **Secret pattern matching**: Scan all string fields for patterns matching:
   - API keys (strings matching `[A-Za-z0-9_-]{20,}` preceded by key/token/secret/api)
   - Connection strings (containing `://` with credentials)
   - Environment variable references with values (`KEY=value` patterns)
   - Bearer tokens, JWT strings (three dot-separated base64 segments)
   Replace matches with `[REDACTED]`.

4. **Custom patterns**: Apply each regex in `additional_redact_patterns` from the
   config file against all string fields. Replace matches with `[REDACTED]`.

5. **Set `redacted` flag**: Only set `redacted: true` after steps 1-4 complete
   successfully. If any step fails, do NOT write the entry.

## Redaction Failure

If the redaction pass cannot complete (e.g., malformed config, regex error), log a
warning and skip trajectory recording for this invocation. Do NOT write an unredacted
entry. Trajectory capture is a nice-to-have — it must never leak sensitive data.

## Trajectory Entry Schema (Step 8)

When recording a trajectory after a retrospective:

a. Check `~/.claude/projects/<hash>/memory/trajectory-config.json` — if missing
   or `enabled: false`, skip entirely.
b. Construct the raw trajectory entry from execution data available in context:
   - `trajectory_id`: Generate a UUID
   - `timestamp`: ISO-8601 of when the skill invocation started
   - `skill`: The Crucible skill that was invoked (build, debugging, audit, etc.)
   - `completed`: Whether the skill ran to its natural completion
   - `outcome`: Derived from the retrospective's `outcome` field (success/partial/failure)
   - `duration_ms`: From pipeline status timestamps or session timing
   - `tool_call_count`: Estimated from execution summary
   - `error_recovery_events`: Count of error-then-retry sequences observed
   - `user_acceptance`: Whether the user accepted the output (accepted/rejected/modified/unknown)
   - `phases_reached`: For multi-phase skills, which phases completed
   - `deviation_type`: From the retrospective entry
   - `prompt_hash`: SHA-256 of the original user prompt
   - `prompt_summary`: One-line redacted summary (if `include_prompt_summary` is true)
   - `redacted`: Set to true only after redaction pass completes
   - `tags`: From the retrospective entry's tags
c. Run the redaction pass (see Redaction Rules above).
d. Append the entry as a single JSON line to the appropriate file:
   - If `completed == true` AND `outcome == "success"`: append to `trajectory_samples.jsonl`
   - Otherwise: append to `failed_trajectories.jsonl`
e. Check file size: if the target file exceeds `max_entries` lines, remove the
   oldest entries (from the top of the file) to bring it back to `max_entries`.

## Trajectory Recording Without Retrospective

Forge retrospective is RECOMMENDED but not REQUIRED. When a significant skill
completes but no retrospective is triggered (user declines, session ending, quick
task), trajectory data would be lost.

To handle this, any skill that completes a significant task SHOULD write a
minimal trajectory entry if:
- Trajectory capture is enabled
- No forge retrospective is expected to run in this session

The minimal entry uses `deviation_type: "unknown"`, `tags: []`, and
`outcome` based on the completion signal alone (success if the skill reported
success, failure if it reported failure, partial otherwise). The entry still
goes through the full redaction pass.

This ensures trajectory data is captured even when forge does not run, at the
cost of less-rich analytical fields. The skill-creator's eval generation pipeline
handles entries with `deviation_type: "unknown"` by clustering on execution
metrics alone.
