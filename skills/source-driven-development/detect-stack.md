# Detect Stack — Framework → Canonical Docs Reference Table

Companion to `SKILL.md` Phase 1 (Detect Stack). When the agent identifies a framework in the change context, look it up here to pick the canonical doc host for Phase 2 (Fetch).

Each row is a seed for the WebFetch allowlist in `.claude/settings.local.json` (see DEC-5 — incremental scope).

| Framework | Canonical doc URL | Version signal |
|---|---|---|
| React | https://react.dev | React 19 = Server Components are the default; `use` hook replaces many Suspense patterns. |
| Next.js | https://nextjs.org/docs | Next 15 = App Router stable, `async` request APIs (`cookies()`, `headers()`) are awaited. |
| Vue | https://vuejs.org/guide | Vue 3.5 = Composition API is the documented default; Options API still supported but secondary. |
| Django | https://docs.djangoproject.com | Django 5.x = async views + `GeneratedField` documented; 4.x uses sync-first examples. |
| FastAPI | https://fastapi.tiangolo.com | FastAPI ≥ 0.100 = Pydantic v2 is default; validators renamed (`@field_validator`). |
| ASP.NET Core | https://learn.microsoft.com/aspnet/core | .NET 9 = native AOT + minimal APIs promoted; `WebApplication.CreateBuilder` is canonical entry. |
| Rails | https://guides.rubyonrails.org | Rails 8 = Solid Queue / Solid Cache default; Propshaft replaces Sprockets in new apps. |
| Express | https://expressjs.com | Express 5 = async handlers catch rejections automatically; `req.param()` removed. |
| PostgreSQL | https://www.postgresql.org/docs | Postgres 17 = incremental backups, `MERGE ... RETURNING`; 16 adds logical replication from standby. |
| Tailwind | https://tailwindcss.com/docs | Tailwind v4 = CSS-first config (`@theme`), Oxide engine; v3 JS config still supported but secondary. |
| TypeScript | https://www.typescriptlang.org/docs | TS 5.x = `using` declarations, `const` type parameters, decorators (stage-3). |
| MDN (web standards) | https://developer.mozilla.org | Catch-all for browser / platform APIs (fetch, Streams, Web Components, CSS) — cite when no framework-specific doc applies. |

## Usage

1. Match the framework detected in Phase 1 against the table.
2. Use the listed URL as the Phase 2 WebFetch target (or a narrower sub-path — e.g., `https://react.dev/reference/react/use`).
3. Record URL + fetch date per Phase 4 (Cite).

If a needed doc host is missing, add it in a follow-up: extend both this table and the `WebFetch(domain:…)` allowlist in `.claude/settings.local.json`. Per DEC-5 the allowlist grows incrementally; do not request a blanket `WebFetch(*)`.
