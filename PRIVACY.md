# Privacy Policy

**Last updated:** 2026-09-28

## What Crucible Is

Crucible is a collection of agent skill files (Markdown) that provide methodology instructions to AI coding assistants. It is not software that executes independently.

## Data Collection

Crucible's skills have no independent analytics or telemetry collection of their own, and do not transmit user data to any service operated by their authors themselves, and contain no analytics, telemetry, or tracking. Crucible ships one optional integration, `mcp-servers/crucible-consensus/`, which is inert by default (not registered as an MCP server unless you explicitly configure it) — when enabled, it makes network calls to whichever model provider(s) you configure in `consensus-config.yaml`, governed by that provider's own terms. Crucible's skills also instruct your AI assistant to invoke tools you have installed (for example `gh` for GitHub issues and pull requests, or your assistant's web-fetch tool) — those calls are made by your tools under your control, governed by those services' own terms. **Local storage is real and is disclosed here, not denied:** following these skills writes local files — the quality gate keeps per-round artifact copies and findings under its scratch directory, and appends machine-local calibration rows to the central ledger (`~/.claude/crucible/ledger/runs.jsonl`; `skills/quality-gate/SKILL.md:1018-1026` and the ledger emit path), and `forge`/`cartographer` write local session notes (see `PRIVACY.md`'s `## Local Storage`). None of that leaves the machine on its own; the only outbound calls are the optional consensus provider calls and the tools you have installed, both described above (SP3, round 8).

## Local Storage

Two optional skills (forge and cartographer) store session notes in the local project memory directory on your machine. This data never leaves your device and is fully under your control.

## Third-Party Services

By default, Crucible's skills make no independent third-party model-provider calls; when configured, the optional `crucible-consensus` integration sends the content you pass it to the selected providers. The AI platform you use (Claude Code, Cursor, OpenAI Codex) has its own privacy policy governing how it processes your prompts and code, and any skill instructing it to run `gh`, fetch a URL, or invoke another installed tool does so through that platform's own tool-use surface, under your existing permissions. If you enable the optional `crucible-consensus` MCP integration, it sends the specific content you pass it to whichever provider(s) you configure — review that integration's own documentation before enabling it.

## Contact

For questions about this policy, open an issue at https://github.com/raddue/crucible/issues.
