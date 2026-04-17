# Settings Patch — WebFetch Allowlist for source-driven-development (#177 T3)

**Status:** Deferred from PR — safety-guard hook blocks Claude from editing `.claude/settings.local.json`. User to apply manually post-merge.

**Rationale:** Adds doc-fetch allowlist per DEC-5 incremental-scope policy.

## Proposed diff

Extend `.claude/settings.local.json` `permissions.allow` with the 12 `WebFetch(domain:…)` entries below, one per doc host from `skills/source-driven-development/detect-stack.md`:

```json
"WebFetch(domain:react.dev)",
"WebFetch(domain:nextjs.org)",
"WebFetch(domain:vuejs.org)",
"WebFetch(domain:docs.djangoproject.com)",
"WebFetch(domain:fastapi.tiangolo.com)",
"WebFetch(domain:learn.microsoft.com)",
"WebFetch(domain:guides.rubyonrails.org)",
"WebFetch(domain:expressjs.com)",
"WebFetch(domain:postgresql.org)",
"WebFetch(domain:tailwindcss.com)",
"WebFetch(domain:typescriptlang.org)",
"WebFetch(domain:developer.mozilla.org)"
```

## How to apply

1. Open `.claude/settings.local.json`.
2. Locate the `permissions.allow` array (currently contains `WebFetch(domain:github.com)` plus other entries).
3. Append the 12 lines above. Preserve JSON array comma rules.
4. Save. No restart required — Claude Code reloads settings on next tool call.

## Verification

After applying, a Phase 2 WebFetch from `skills/source-driven-development/SKILL.md` should succeed against any of the 12 domains without a permission prompt. If a prompt appears, the entry is missing or mis-spelled.

## Notes

- DEC-5 (high confidence): incremental scope, **no** blanket `WebFetch(*)` grant. Add new doc hosts only as the `detect-stack.md` table grows.
- Keep this file in sync with `detect-stack.md` — if that table adds a framework, add a matching `WebFetch(domain:…)` line here in the follow-up commit.
