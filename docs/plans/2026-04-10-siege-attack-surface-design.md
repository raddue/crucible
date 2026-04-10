---
ticket: "#117"
epic: "#117"
title: "Siege Attack Surface Discovery -- Outside-In Recon for Phase 1"
date: "2026-04-10"
source: "spec"
---

# Siege Attack Surface Discovery -- Design Document

**Goal:** Add an outside-in attack surface discovery step to Siege Phase 1 that enumerates registered routes/endpoints from static analysis, builds an exposure map, and cross-references it with the file manifest to surface coverage gaps before agents are dispatched.

**Constraint:** Sonnet-level scoping task within existing Phase 1 structure. No new agent dispatch. Static analysis only. Minimal token cost addition.

## 1. Current State Analysis

Siege Phase 1 (Reconnaissance) has three steps:
1. **Intelligence Gathering** -- fetches OWASP, CISA KEV, dependency audit data
2. **Scope and Manifest** -- builds file manifest via Sonnet exploration agent
3. **Load Persistent Threat Model** -- reads prior trust boundaries and attack surfaces

The manifest is file-centric: it lists security-relevant files by path. But it has no concept of what the application actually *exposes* to the network. A file named `UserController.cs` appears in the manifest, but Siege does not know whether it registers `/api/users`, `/api/users/{id}/delete`, or `/admin/impersonate`. The agents receive files but lack a map of the application's externally reachable surface.

**What this misses:**
- Endpoints registered by framework conventions (e.g., ASP.NET attribute routing, Express `app.get()`) that are not in any file the manifest deemed "security-relevant"
- Routes defined in configuration files (e.g., Spring `@RequestMapping`, Rails `routes.rb`) that the manifest's file-type heuristic may skip
- Discrepancies between what files exist and what endpoints are actually routable -- dead code vs. live attack surface

## 2. Design: Outside-In Attack Surface Discovery

### Position in Phase 1

Insert as **Step 2.5: Attack Surface Enumeration** between the existing Step 2 (Scope and Manifest) and Step 3 (Load Persistent Threat Model). It depends on the manifest (needs to know which framework/language the project uses) and feeds into Step 3 (exposure map becomes part of the threat model delta).

### What It Does

Three sub-steps, all executed by the orchestrator (Sonnet-level, no agent dispatch):

#### Sub-step A: Framework Detection

Detect which web framework(s) the project uses by scanning manifest files and project configuration:

| Signal | Framework | Confidence |
|--------|-----------|------------|
| `package.json` with `express` dependency | Express.js | High |
| `package.json` with `fastify` dependency | Fastify | High |
| `package.json` with `@nestjs/core` dependency | NestJS | High |
| `package.json` with `next` dependency | Next.js | High |
| `requirements.txt` or `pyproject.toml` with `flask` | Flask | High |
| `requirements.txt` or `pyproject.toml` with `fastapi` | FastAPI | High |
| `requirements.txt` or `pyproject.toml` with `django` | Django | High |
| `*.csproj` with `Microsoft.AspNetCore` | ASP.NET Core | High |
| `Gemfile` with `rails` | Rails | High |
| `pom.xml` or `build.gradle` with `spring-boot` | Spring Boot | High |
| `go.mod` with `gin-gonic/gin` | Gin (Go) | High |
| `go.mod` with `gorilla/mux` | Gorilla Mux (Go) | High |
| `Cargo.toml` with `actix-web` | Actix Web (Rust) | High |

If no framework is detected, skip the rest of Step 2.5 and note in scope limitations: "No recognized web framework detected -- attack surface enumeration skipped."

Multiple frameworks detected: enumerate all. Note in the exposure map which framework each endpoint belongs to.

#### Sub-step B: Route/Endpoint Enumeration

For each detected framework, apply static grep patterns to extract registered routes. This is pattern-matching, not AST parsing -- it catches the common 90% and documents what it misses.

**Framework-specific patterns:**

| Framework | Pattern | Example Match |
|-----------|---------|---------------|
| Express.js | `(app\|router)\.(get\|post\|put\|patch\|delete\|all\|use)\s*\(` | `app.get('/api/users', ...)` |
| Fastify | `(fastify\|server)\.(get\|post\|put\|patch\|delete\|all)\s*\(` | `fastify.post('/login', ...)` |
| NestJS | `@(Get\|Post\|Put\|Patch\|Delete\|All)\s*\(` | `@Get('users/:id')` |
| Next.js | Files under `app/` or `pages/api/` (convention-based routing) | `app/api/users/route.ts` |
| Flask | `@(app\|blueprint)\.(route\|get\|post\|put\|delete)\s*\(` | `@app.route('/login', methods=['POST'])` |
| FastAPI | `@(app\|router)\.(get\|post\|put\|patch\|delete)\s*\(` | `@router.get('/items/{id}')` |
| Django | `path\(\s*['"]` or `url\(\s*['"]` in `urls.py` | `path('api/users/', views.user_list)` |
| ASP.NET Core | `\[Http(Get\|Post\|Put\|Patch\|Delete)\]` or `\[Route\(` or `MapGet\|MapPost\|MapPut\|MapDelete` | `[HttpGet("api/users/{id}")]` |
| Rails | `(get\|post\|put\|patch\|delete\|resources\|resource)\s` in `routes.rb` | `resources :users` |
| Spring Boot | `@(GetMapping\|PostMapping\|PutMapping\|PatchMapping\|DeleteMapping\|RequestMapping)\s*\(` | `@GetMapping("/api/users")` |
| Gin (Go) | `(r\|router\|group)\.(GET\|POST\|PUT\|PATCH\|DELETE\|Any)\s*\(` | `r.GET("/api/users", ...)` |
| Gorilla Mux (Go) | `(r\|router)\.HandleFunc\s*\(` | `r.HandleFunc("/api/users", handler)` |
| Actix Web (Rust) | `\.(route\|resource)\s*\(` or `#\[get\|post\|put\|patch\|delete\]` | `#[get("/api/users")]` |

**Extraction output per endpoint:**
- HTTP method (or "ANY" if not determinable)
- Route path (raw string from the match)
- Source file and line number
- Framework

**Limitations (documented in output):**
- Dynamic route registration (e.g., `app[method](path)` where method is a variable) is not captured
- Middleware-only routes (e.g., Express `app.use('/api', middleware)`) are captured as "middleware mount" not individual endpoints
- Convention-based routing (Next.js file-based, Rails resources expansion) produces approximate routes, not exact

#### Sub-step C: Exposure Map Construction and Cross-Reference

Build the exposure map and cross-reference with the file manifest.

**Exposure map format** (written to `scratch/<run-id>/exposure-map.md`):

```markdown
# Attack Surface Exposure Map
**Framework(s):** [detected frameworks]
**Enumeration method:** Static pattern matching
**Endpoint count:** [N]

## Endpoints
| # | Method | Route | File | Line | In Manifest |
|---|--------|-------|------|------|-------------|
| 1 | GET | /api/users | src/controllers/UserController.ts | 42 | Yes |
| 2 | POST | /api/login | src/auth/login.ts | 15 | Yes |
| 3 | DELETE | /admin/purge | src/admin/maintenance.ts | 88 | NO -- GAP |

## Coverage Gaps
[Endpoints where the source file is NOT in the manifest]
- `/admin/purge` (src/admin/maintenance.ts:88) -- file not in Siege manifest
- `/api/webhooks/stripe` (src/webhooks/stripe.ts:12) -- file not in Siege manifest

## Scope Limitations
- [framework-specific limitations from sub-step B]
- Dynamic route registration not captured
- Route parameters shown as raw pattern (e.g., `:id`, `{id}`)
```

**Cross-reference logic:**
1. For each endpoint's source file, check if it appears in `manifest.md`
2. If not present: mark as "GAP" -- this is a file that registers a network-reachable endpoint but was not included in the manifest for agent analysis
3. Gap files are automatically added to the manifest with a tag: `[attack-surface-gap]`

**Gap handling:**
- Gap files are added to the manifest before Phase 2 agent dispatch
- Gap files are prioritized for Boundary Attacker's Tier 2 partition (they are externally reachable but were not initially scoped)
- The exposure map summary (endpoint count, gap count, gap list) is appended to the Tier 1 context block so all agents know what is externally reachable

### Token Budget

- Framework detection: ~10 lines of grep output, negligible
- Route enumeration: one grep per framework pattern, results condensed to table rows. Typical project: 20-100 endpoints = 20-100 lines
- Exposure map in Tier 1: endpoint count + gap list only (not full table). Budget: **15 lines max** added to Tier 1 context
- Full exposure map table stays in scratch, available to agents via Tier 2 if needed

**Total token cost addition:** ~200-400 tokens in Tier 1 context. Negligible relative to the 300-500 line Tier 1 budget.

### Integration with Persistent Threat Model

The exposure map feeds Phase 5 (threat model update):
- New endpoints not in prior threat model's Attack Surfaces section are flagged as "new attack surface"
- Endpoints in prior threat model but absent from current enumeration are flagged as "retired surface"
- This enables drift detection across Siege runs

## 3. What This Does NOT Do

- **No dynamic analysis** -- does not start the application or send requests
- **No AST parsing** -- regex/grep patterns only, documented limitations
- **No new agent dispatch** -- orchestrator handles all three sub-steps at Sonnet level
- **No separate phase** -- fits within existing Phase 1 as Step 2.5
- **No OpenAPI/Swagger consumption** -- could be a future enhancement but adds complexity; static grep covers the same ground for source-available targets

## 4. Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| OpenAPI spec parsing | Not all projects have OpenAPI specs; adds a dependency on spec correctness |
| AST-based route extraction | Language-specific tooling required per framework; too heavy for a Sonnet-level task |
| Dynamic crawling (start app, spider endpoints) | Violates "static analysis only" constraint; requires runtime dependencies |
| Separate Phase 0 | Unnecessary structural change; Step 2.5 is naturally sequential after manifest |
| New agent for attack surface | Overkill; grep patterns are mechanical, not analytical |

## 5. Success Criteria

1. Siege Phase 1 enumerates registered endpoints for at least the 13 frameworks listed
2. Files with registered endpoints that are NOT in the manifest are automatically added
3. Agents receive exposure map summary (endpoint count + gaps) in Tier 1 context
4. Gap files are prioritized in Boundary Attacker's Tier 2 partition
5. Token cost of Step 2.5 is under 500 tokens in Tier 1 context
6. When no web framework is detected, step is cleanly skipped with a note in scope limitations
