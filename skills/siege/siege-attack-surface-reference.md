# Attack Surface Reference

Reference material for Siege Phase 1 Step 2.5 (Attack Surface Enumeration).

## Framework Detection

Scan manifest files and project configuration to detect which web framework(s) the project uses:

| Signal | Framework |
|--------|-----------|
| `package.json` with `express` dependency | Express.js |
| `package.json` with `fastify` dependency | Fastify |
| `package.json` with `@nestjs/core` dependency | NestJS |
| `package.json` with `next` dependency | Next.js |
| `requirements.txt` or `pyproject.toml` with `flask` | Flask |
| `requirements.txt` or `pyproject.toml` with `fastapi` | FastAPI |
| `requirements.txt` or `pyproject.toml` with `django` | Django |
| `*.csproj` with `Microsoft.AspNetCore` | ASP.NET Core |
| `Gemfile` with `rails` | Rails |
| `pom.xml` or `build.gradle` with `spring-boot` | Spring Boot |
| `go.mod` with `gin-gonic/gin` | Gin (Go) |
| `go.mod` with `gorilla/mux` | Gorilla Mux (Go) |
| `Cargo.toml` with `actix-web` | Actix Web (Rust) |

If no framework is detected, skip the rest of Step 2.5 and note in scope limitations: "No recognized web framework detected -- attack surface enumeration skipped." Multiple frameworks: enumerate all.

## Route/Endpoint Enumeration Grep Patterns

For each detected framework, grep project files using these patterns to extract registered routes:

| Framework | Grep Pattern | Example Match |
|-----------|-------------|---------------|
| Express.js | `(app\|router)\.(get\|post\|put\|patch\|delete\|all\|use)\s*\(` | `app.get('/api/users', ...)` |
| Fastify | `(fastify\|server)\.(get\|post\|put\|patch\|delete\|all)\s*\(` | `fastify.post('/login', ...)` |
| NestJS | `@(Get\|Post\|Put\|Patch\|Delete\|All)\s*\(` | `@Get('users/:id')` |
| Next.js | Files under `app/` or `pages/api/` (convention-based routing) | `app/api/users/route.ts` |
| Flask | `@(app\|blueprint)\.(route\|get\|post\|put\|delete)\s*\(` | `@app.route('/login', methods=['POST'])` |
| FastAPI | `@(app\|router)\.(get\|post\|put\|patch\|delete)\s*\(` | `@router.get('/items/{id}')` |
| Django | `path\(\s*['"]` or `url\(\s*['"]` in `urls.py` files | `path('api/users/', views.user_list)` |
| ASP.NET Core | `\[Http(Get\|Post\|Put\|Patch\|Delete)\]` or `\[Route\(` or `Map(Get\|Post\|Put\|Delete)\(` | `[HttpGet("api/users/{id}")]` |
| Rails | `(get\|post\|put\|patch\|delete\|resources\|resource)\s` in `config/routes.rb` | `resources :users` |
| Spring Boot | `@(GetMapping\|PostMapping\|PutMapping\|PatchMapping\|DeleteMapping\|RequestMapping)\s*\(` | `@GetMapping("/api/users")` |
| Gin (Go) | `(r\|router\|group)\.(GET\|POST\|PUT\|PATCH\|DELETE\|Any)\s*\(` | `r.GET("/api/users", ...)` |
| Gorilla Mux (Go) | `(r\|router)\.HandleFunc\s*\(` | `r.HandleFunc("/api/users", handler)` |
| Actix Web (Rust) | `\.(route\|resource)\s*\(` or `#\[(get\|post\|put\|patch\|delete)\]` | `#[get("/api/users")]` |

For each match, extract: HTTP method (or "ANY" if indeterminate), route path (raw string), source file path, line number, framework name.

**Auth-signal heuristic (best-effort):** For each endpoint, scan surrounding context (same file, same route registration block) for auth middleware or decorator patterns: `[Authorize]`, `@RequireAuth`, `authenticate`, `isAuthenticated`, `requireLogin`, `@login_required`, `@permission_required`, `auth_guard`, `AuthGuard`, `before_action :authenticate`. Classify each endpoint as `auth: yes | no | unknown`. This is approximate -- false negatives are expected (auth applied at router level may not appear near the route). The classification feeds the exposure map's "Auth" column and helps prioritize: `auth: no` endpoints are highest priority for Boundary Attacker partitioning.

**Limitations (documented in exposure map):**
- Dynamic route registration (method/path from variables) is not captured
- Middleware-only mounts (e.g., `app.use('/api', ...)`) are recorded as "middleware mount", not individual endpoints
- Convention-based routing (Next.js file-based, Rails `resources` expansion) produces approximate routes
- Auth-signal heuristic is best-effort: router-level or middleware-chain auth may not appear near the route definition, producing false `auth: unknown` classifications

## Exposure Map Format

Write the full exposure map to `scratch/<run-id>/exposure-map.md`:

```markdown
# Attack Surface Exposure Map
**Framework(s):** [detected frameworks]
**Enumeration method:** Static pattern matching
**Endpoint count:** [N]

## Endpoints
| # | Method | Route | File | Line | Auth | In Manifest |
|---|--------|-------|------|------|------|-------------|
| 1 | GET | /api/users | src/controllers/UserController.ts | 42 | yes | Yes |
| 2 | DELETE | /admin/purge | src/admin/maintenance.ts | 88 | no | NO -- GAP |

## Coverage Gaps
- `/admin/purge` (src/admin/maintenance.ts:88) -- file not in Siege manifest
[list all gaps]

## Scope Limitations
[framework-specific limitations from sub-step B]
```

**Line budget:** The exposure map summary appended to Tier 1 context (Step 1 of Automated Context Assembly) is capped at **15 lines**: endpoint count, gap count, and the gap list. The full endpoint table remains in `scratch/<run-id>/exposure-map.md` only.
