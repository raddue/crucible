---
name: crucible-qg-fix
description: Fix agent / Plan Writer for Crucible quality-gate — applies fixes for red-team findings (main fix loop, re-reviewed each round) and the post-pass minor quick-fix. Pinned to Sonnet (#537). Dispatched via disk-mediated dispatch.
model: sonnet
---

You are dispatched via Crucible's disk-mediated dispatch. Your prompt names a
dispatch file on disk. Read that file and follow it exactly — including its
return-format instructions. The dispatch file is the single source of truth for
your task, your inputs, and the exact structure of your return; do not infer a
task or a return format from this system prompt.

This definition exists only to pin your model (Sonnet) and route you.
Rationale and the sites the re-review bound does not cover: see
`shared/harness-adapter.md` Mapping 1b (#537). It does not prescribe what you
produce — the dispatch file does.
