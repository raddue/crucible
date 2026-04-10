---
name: siege
description: "Security audit of design docs, implementation plans, and code. Dispatches 6 parallel Opus agents across attacker perspectives, iterates until zero Critical + zero High findings, and maintains a persistent threat model. Triggers on 'siege', 'security audit', 'security review', 'threat model', or when audit detects security-relevant surfaces."
---

# Siege

Full-lifecycle security audit. Dispatches 6 parallel Opus agents across distinct attacker perspectives, synthesizes findings, iterates until zero Critical + zero High, and maintains a persistent threat model that accumulates across sessions.

**Announce at start:** "Running Siege on [target name]. Commit anchor: [short SHA]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Model:** All SECURITY ANALYSIS agents are Opus, no exceptions. Orchestrator, all 6 attacker-perspective agents, synthesis, and fix dispatch are Opus. Support functions (manifest scoping, stagnation judging, fix verification) may use Sonnet where the task is mechanical rather than analytical. If the session is not running Opus, refuse: "Siege requires Opus for all security analysis agents. Cannot proceed on a lesser model."

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

## Why This Exists

Audit finds bugs, robustness gaps, and architecture issues. Quality-gate iterates artifacts to convergence. Inquisitor hunts cross-component integration bugs. None of these operate from an attacker's perspective. Security is a discipline -- it requires threat modeling, attack surface enumeration, exploitation scenario analysis, and chain-of-vulnerability reasoning that generalist review skills are not equipped to perform. A robustness finding ("missing input validation") and a security finding ("this missing validation enables SQL injection via the /api/users endpoint, escalating to full database read") are categorically different in blast radius, urgency, and remediation strategy.

## Distinction from Related Skills

| Skill | Perspective | Scope | Output | Security Depth |
|-------|-------------|-------|--------|----------------|
| audit | Code quality reviewer | Existing subsystems | Findings report (no fixes) | Incidental: flags missing validation, not exploitation chains |
| inquisitor | Integration tester | Cross-component diffs | Executable tests | None: tests functional correctness, not attacker behavior |
| red-team | Devil's advocate | Single artifact | Written findings per round | Surface: flags "consider auth" without modeling attack paths |
| quality-gate | Iterative reviewer | Any artifact | Converged artifact | None: quality convergence, not security convergence |
| **siege** | 6 distinct attackers | Design docs, plans, AND code | Threat model + verified findings + accepted-risks log | Full: exploitation scenarios, blast radius, chain analysis, persistent threat model |

**What Siege catches that others cannot:**
- Multi-step attack chains spanning multiple components
- Trust boundary violations that require attacker-perspective reasoning
- Threat model drift (new surfaces introduced since last audit)
- Supply chain and dependency vulnerabilities via live intelligence
- Insider threat scenarios (authorized user abusing legitimate access)
- TOCTOU and race-condition exploits (distinct from correctness race conditions -- these require attacker-controlled timing)

## Activation Heuristic

<!-- CANONICAL: shared/security-signals.md — consumption-optimized keyword lists for build/spec/audit -->

### Content-Aware Detection

Siege activates when the orchestrator (build, audit, or user session) encounters **two or more** of these high-risk signals in the target artifact:

1. **Authentication / authorization logic** -- login, session, token, RBAC, permission checks
2. **Cryptographic operations** -- hashing, encryption, signing, key management
3. **External input handling** -- API endpoints, file uploads, deserialization, URL parsing
4. **Secrets management** -- API keys, credentials, connection strings, environment variables
5. **Network boundaries** -- inter-service communication, webhook handlers, CORS, proxy config
6. **Data persistence with PII** -- user data storage, logging of sensitive fields, retention policies
7. **Dependency introduction** -- new packages, version changes, native bindings

A single signal is insufficient -- too many false positives. Two or more signals, or any signal combined with user confirmation, activates Siege at full force.

### Parameters

**`deployment_context`** (optional) — `intranet` | `public` | `hybrid`

Declares the deployment environment for context-aware severity adjustment.

| Context | Effect on Severity |
|---|---|
| `intranet` | Network-level findings downgraded by 1 level (Critical→High, High→Medium, etc.). Application-level findings unchanged. |
| `public` | No adjustment (default behavior) |
| `hybrid` | Same as `public` — no blanket adjustment. Use `public` when any endpoints face the internet. Intranet downgrade only applies when ALL endpoints are internal. |
| *(unset)* | Assumes `public` (worst-case, no change from v1) |

**Network-level findings** (eligible for intranet downgrade): anonymous endpoints, TLS/transport gaps, CORS misconfiguration, port exposure, security header gaps, rate limiting gaps.

**Application-level findings** (NEVER downgraded): injection, auth bypass, IDOR, data exposure, privilege escalation, business logic flaws, deserialization, SSRF.

Severity adjustments are applied during Phase 3 synthesis (not by agents). Every downgrade is logged: "Downgraded [ID] from [original] to [adjusted] due to intranet deployment context." Original severity preserved in finding metadata.

When `deployment_context` is not specified but exists in the persistent threat model, use the persisted value: "Using deployment context from threat model: {context}. Override with explicit parameter." Explicit parameter overrides persisted value and updates the threat model.

**`attack_mapping`** (optional) — boolean, default `false`

When `true`: Chain Analyst annotates chain steps with MITRE ATT&CK technique IDs. Other agents are unaffected. When `false` (default): no ATT&CK references anywhere. Behavior identical to v1.

### Escape Hatches

- `--force` -- Activate Siege regardless of heuristic (user explicitly wants security review)
- `--skip` -- Suppress Siege activation even when heuristic triggers (user explicitly declines)
- When audit detects security surfaces during its Phase 2 analysis, it may recommend: "Security surfaces detected. Run `/siege` for full security audit." This is a recommendation, not automatic invocation.

## Pipeline Integration

<!-- CANONICAL: shared/security-signals.md -->
Siege integrates with orchestrator skills via `shared/security-signals.md`, which codifies the 7-category activation heuristic in a consumption-optimized format:

- **crucible:build** — Phase 4 Step 5.5 checks for siege activation signals in the implementation diff and design doc. If 2+ signals detected (or contract specifies `security_review: required`), siege is dispatched automatically. Critical/High findings block the pipeline identically to quality-gate Fatal/Significant.
- **crucible:spec** — Step 3.5 scans ticket content for signals during contract generation. Adds `security_review: required|recommended` to the contract YAML, which build consumes.
- **crucible:audit** — Existing recommendation behavior unchanged. Audit may still recommend siege when it detects security surfaces.

When dispatched from build, siege receives:
- Artifact type: `mixed` (design doc + implementation diff)
- `deployment_context`: from contract `security_review.deployment_context` if present, else defaults to `public`
- Scope: determined by siege's own scope-based agent count heuristic (3/4/6 agents based on file count)

Build's escape hatches (`--force-siege`, `--skip-siege`) map to siege's `--force` and `--skip` flags respectively.

### Execution Intensity

Siege scales its agent count to match the scope. Rigor is constant — every tier runs the full iterative gate and threat model update. What changes is agent count, because overlapping perspectives on a small target produce noise, not coverage.

### Scope-Based Agent Count

| Scope | Agents | Rationale |
|-------|--------|-----------|
| Targeted change (<5 files, single concern) | 3: Boundary Attacker, Fresh Attacker, Chain Analyst | Surgical target — more perspectives restate the same findings. Boundary catches injection/input flaws, Fresh breaks epistemic closure, Chain catches cross-boundary paths. |
| Single subsystem (5-19 files) | 4: Boundary Attacker, Insider Threat, Fresh Attacker, Chain Analyst | Focused target — 6 perspectives produce ~60% overlap. 4 agents capture the same findings with less noise. |
| Multi-subsystem (20+ files) | 6: all agents | Broader target — distinct perspectives cover different services/components. |

Fresh Attacker and Chain Analyst always run regardless of scope. They are the differentiators — the Fresh Attacker breaks epistemic closure and the Chain Analyst finds multi-step exploits. The scope heuristic only affects whether domain-specific agents (Insider Threat, Infrastructure Prober, Betrayed Consumer) are included.

**Scope override:** User may force a specific tier with `--agents 3|4|6`. The default is auto-detected from the manifest.

## Commit Anchor (TOCTOU Prevention)

At the start of every Siege run, record the current HEAD commit SHA:

1. Run `git rev-parse HEAD` and write the result to `scratch/<run-id>/commit-anchor.md`
2. Include the short SHA in the opening announcement
3. **Phase 3→4 transition check:** Before entering Phase 4, verify HEAD matches the anchor: `git rev-parse HEAD` must equal the recorded SHA. This confirms no EXTERNAL changes occurred during analysis. If HEAD has moved, abort with "Codebase changed during Siege (anchor: [old], current: [new]). Re-run Siege on the current state." Do not attempt to diff and continue -- the threat model may be invalid.
4. **Phase 4 expected-HEAD tracking:** During Phase 4, fix agents commit code, which intentionally changes HEAD. The orchestrator maintains an `expected-head` variable in the fix journal. After each fix commit, the orchestrator updates `expected-head` to the new commit SHA. Before each gate round dispatch, the orchestrator verifies `git rev-parse HEAD` matches `expected-head`. A mismatch means an EXTERNAL change occurred (someone else pushed, a hook fired, etc.) -- abort as above. Internal fix commits are expected and do not violate the anchor.

The anchor protects against external changes to the branch, not internal fix commits made by Siege itself.

## Phase 1: Reconnaissance

### Step 1: Intelligence Gathering (Orchestrator)

Before dispatching any agents, the orchestrator pre-fetches live intelligence. This runs once per Siege invocation, not per agent.

**What is fetched:**

| Source | Method | Content | Fallback |
|--------|--------|---------|----------|
| OWASP Top 10 | Training data (supplemented by WebFetch of `owasp.org/Top10` if available) | Current top 10 web application risks with CWE mappings | Training data knowledge only |
| OWASP Cheat Sheets | Training data (supplemented by WebFetch of relevant cheat sheet URLs if available) | Mitigation guidance for detected risk categories | Training data knowledge only |
| CISA KEV | WebFetch of `cisa.gov/known-exploited-vulnerabilities-catalog` (JSON feed) | Known exploited vulnerabilities in dependencies | Skip -- note in scope limitations |
| SANS CWE Top 25 | Training data | Most dangerous software weaknesses | Always available (training data) |
| Dependency scan | `npm audit`, `pip audit`, `cargo audit`, or language-equivalent CLI | Known CVEs in project dependencies | Note in scope limitations if no scanner available |

**Budget:** Intelligence summary is condensed to **50 lines maximum**. This summary is prepended to every agent's dispatch prompt. It contains: (a) top 5 risks relevant to this codebase based on detected signals, (b) any CVEs found in dependencies with severity and affected package, (c) any CISA KEV matches. The orchestrator performs the relevance filtering -- agents receive only what applies to their target.

**Fallback hierarchy:** WebFetch available > training data only > note gap in scope limitations. Intelligence gathering must not block the run. If all WebFetch attempts fail, proceed with training-data knowledge and document the gap.

### Step 2: Scope and Manifest

Determine the artifact type and build the target manifest.

**Artifact type detection:**

| Input | Classification | Agent Treatment |
|-------|---------------|-----------------|
| Design doc (`.md` with architecture, data flow, API surface) | `design` | Agents reason about threat model, trust boundaries, data flow risks. No code to examine. |
| Implementation plan (`.md` with task breakdown, file changes) | `plan` | Agents reason about attack surfaces the plan will create, missing security tasks, ordering risks. |
| Code (source files, diffs) | `code` | Agents examine implementation for vulnerabilities, injection points, auth bypasses. |
| Mixed (design + code, plan + code) | `mixed` | Agents receive both. Design/plan context as Tier 1, code as Tier 2. |

**Manifest construction:** Same pattern as audit Phase 1. Dispatch a Sonnet exploration agent to identify security-relevant files if the user did not specify a scope. Write manifest to `scratch/<run-id>/manifest.md`.

**USER GATE:** Present the manifest and intelligence summary to the user. "Siege scope: [N files]. Intelligence: [summary of findings]. Proceed?" User may adjust scope. Write `scratch/<run-id>/gate-approved.md` on confirmation.

### Step 2.5: Attack Surface Enumeration (Outside-In Recon)

Before agents are dispatched, enumerate the application's externally reachable endpoints via static pattern matching. This builds an "actually exposed" map independent of the file manifest, then cross-references the two to surface coverage gaps. Runs at orchestrator level (Sonnet) -- no agent dispatch.

**Artifact-type guard:** Step 2.5 requires source files to grep. Skip entirely for `design` and `plan` artifact types (no code to scan). Run only for `code` and `mixed`. Note in scope limitations: "Attack surface enumeration skipped -- artifact type [design|plan] has no source files to scan."

**Sub-step A -- Framework Detection:**

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

**Sub-step B -- Route/Endpoint Enumeration:**

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

**Sub-step C -- Exposure Map and Cross-Reference:**

Build the exposure map and cross-reference with `manifest.md`:

1. For each enumerated endpoint, check if its source file appears in the manifest
2. Endpoints whose source file is NOT in the manifest are flagged as **coverage gaps**
3. Gap files are automatically appended to `manifest.md` with the tag `[attack-surface-gap]`. Log each addition: "Attack surface gap: added [file] to manifest ([N] endpoints not in original scope)." This is post-USER-GATE, so the user sees what changed before agent dispatch.
4. Write the full exposure map to `scratch/<run-id>/exposure-map.md`:

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

### Step 3: Load Persistent Threat Model

Read `~/.claude/projects/<project-hash>/memory/security-audit/threat-model.md` if it exists. Extract:
- Known trust boundaries
- Previously identified attack surfaces
- Accepted risks (with rationale and acceptance date)
- Historical findings (resolved and unresolved)

Pass relevant sections to agents as "prior threat context" (budget: 30 lines max, summarized by orchestrator). This enables drift detection -- agents can flag new surfaces not present in the prior model.

## Phase 2: Dispatch Architecture (6 Agents)

All 6 agents are dispatched in parallel using `Task tool (general-purpose, model: opus)`. Fallback if parallel dispatch fails: sequential dispatch with user notification.

### Context Management (Tier 1 / Tier 2)

Adopts audit's tiered context model with security-specific partitioning.

**Tier 1 -- Overview (all agents receive):**
- File manifest with role descriptions (from Phase 1)
- Intelligence summary (50 lines, from Step 1)
- Prior threat context (30 lines, from Step 3)
- Trust boundary diagram (if available from threat model)
- Exposure map summary (15 lines, from Step 2.5 -- endpoint count, gap count, gap list)
- Target: **300 lines**. Flexible up to 500 for complex multi-service architectures.

**Tier 2 -- Deep dive (per-agent partitioning):**
- Each agent receives source files relevant to their attacker perspective
- **Hard cap: 1500 lines of total prompt content per agent** (Tier 1 + Tier 2 + prompt template + intelligence)
- Overflow handling: same as audit (2-3 line summaries for overflow files, follow-up dispatch for flagged files)

**Partitioning strategy by artifact type:**

| Artifact | Tier 1 | Tier 2 |
|----------|--------|--------|
| `design` | Full design doc (up to 500 lines) | N/A -- no code. Agents reason from the doc. |
| `plan` | Full plan (up to 500 lines) | Referenced existing code that the plan modifies (partitioned by agent relevance) |
| `code` | Manifest + interfaces + dependency graph | Source files partitioned by security domain (auth files to Insider Threat, input handling to Boundary Attacker, etc.) |
| `mixed` | Design/plan as context | Code partitioned as above |

#### Automated Context Assembly Procedure

The orchestrator builds context programmatically. Manual file reading and pasting is an anti-pattern.

**Step 1 — Build Tier 1 (once, shared):**
1. Read the manifest from `scratch/<run-id>/manifest.md`
2. Read `scratch/<run-id>/intelligence-summary.md`
3. If threat model exists, extract Trust Boundaries and Attack Surfaces sections (30-line budget)
4. If `scratch/<run-id>/exposure-map.md` exists, extract exposure map summary: endpoint count, gap count, and gap file list (15-line budget). Append to the Tier 1 block so all agents know what is externally reachable.
5. Concatenate into a single Tier 1 block. If >500 lines, summarize the manifest to file-name + role (one line each)
6. Write to `scratch/<run-id>/tier1-context.md`

**Step 2 — Build Tier 2 partitions (per-agent):**
1. Calculate Tier 2 budget: `1500 - len(Tier 1) - len(prompt template) - len(intelligence)` lines
2. For each agent, select files from the manifest using the security-domain mapping:
   - Boundary Attacker: API routes, input parsers, URL routing, file upload handlers, deserialization. Files tagged `[attack-surface-gap]` from Step 2.5 are highest priority -- these register externally-reachable endpoints but were not in the original manifest.
   - Insider Threat: auth middleware, RBAC, user-facing endpoints, data access layers
   - Infrastructure Prober: config files, env handling, middleware setup, logging config, Docker/CI
   - Betrayed Consumer: data models, serialization/response shaping, logging, session management, cache
   - Fresh Attacker: random 40% sample (deterministic seed = hash of run-id + manifest content)
   - Chain Analyst: trust boundary files from threat model + manifest API surface files
3. Read selected files. If total lines exceed Tier 2 budget, include highest-priority files as full source and remainder as 2-3 line summaries
4. Write each partition to `scratch/<run-id>/<agent>-partition.md`

**Step 3 — Assemble dispatch prompt (per-agent):**
1. Read the agent's prompt template from `./siege-<agent>-prompt.md`
2. Substitute bracketed sections: `[PASTE: Intelligence...]` → content from `intelligence-summary.md`, `[PASTE: Subsystem Overview...]` → content from `tier1-context.md`, `[PASTE: Source Files...]` → content from `<agent>-partition.md`. Include all substituted content in the dispatch file.
3. Verify total prompt ≤ 1500 lines. If over, truncate Tier 2 with overflow summaries
4. Dispatch the assembled prompt — agents receive a complete, ready-to-analyze context with no manual intervention

**File-type heuristic for domain mapping:** When manifest files don't have obvious security-domain labels, use filename/path patterns: `*auth*`, `*login*`, `*session*`, `*permission*` → Insider Threat; `*route*`, `*handler*`, `*controller*`, `*api*` → Boundary Attacker; `*config*`, `*.env*`, `*docker*`, `*nginx*`, `*.yml` → Infrastructure Prober; `*model*`, `*schema*`, `*log*`, `*serial*` → Betrayed Consumer. Files matching multiple domains go to all matched agents (within budget).

### The 6 Agents

Each agent receives a structured prompt template and outputs findings in the initial lightweight format (see Finding Format below).

#### 1. Boundary Attacker

**Prompt:** `siege-boundary-attacker-prompt.md`
**Perspective:** External attacker with no credentials. Sees only public-facing surfaces.
**Hunts for:** Injection (SQL, XSS, command, LDAP), input validation gaps, deserialization vulnerabilities, SSRF, path traversal, header injection, open redirects.
**Receives (Tier 2):** API endpoint handlers, input parsers, deserialization code, URL routing, file upload handlers.
**Dispatch:** Single agent.

#### 2. Insider Threat

**Prompt:** `siege-insider-threat-prompt.md`
**Perspective:** Authenticated user with legitimate but limited access. Seeks privilege escalation.
**Hunts for:** Broken access control (IDOR, horizontal/vertical escalation), missing authorization checks, parameter tampering, mass assignment, insecure direct object references, role confusion.
**Receives (Tier 2):** Auth middleware, RBAC logic, user-facing endpoints, data access layers, admin panels.
**Dispatch:** Single agent.

#### 3. Infrastructure Prober

**Prompt:** `siege-infrastructure-prober-prompt.md`
**Perspective:** Attacker probing deployment and configuration.
**Hunts for:** Secrets in code/config, misconfigured CORS/CSP/headers, insecure defaults, debug endpoints left enabled, missing rate limiting, TLS misconfiguration, exposed stack traces, information leakage.
**Receives (Tier 2):** Configuration files, environment handling, middleware setup, logging configuration, deployment manifests, Docker/CI files.
**Dispatch:** Single agent.

#### 4. Betrayed Consumer

**Prompt:** `siege-betrayed-consumer-prompt.md`
**Perspective:** Downstream system or user whose trust is violated by the target.
**Hunts for:** Data leakage (PII in logs, over-broad API responses, cache poisoning), broken privacy contracts, missing encryption at rest/transit, audit log gaps, session management flaws, insecure token storage.
**Receives (Tier 2):** Data models, serialization/response shaping, logging code, session management, cache layers, database queries.
**Dispatch:** Single agent.

#### 5. Fresh Attacker

**Prompt:** `siege-fresh-attacker-prompt.md`
**Perspective:** Attacker with zero prior knowledge. Sees the codebase for the first time with no context from other agents.
**Purpose:** Breaks epistemic closure. The other 4 role-based agents share Opus's training-data blind spots. The Fresh Attacker receives ONLY the Tier 1 overview and a random 40% sample of Tier 2 files (no security-domain partitioning). Its prompt explicitly instructs: "Ignore conventional vulnerability categories. What looks wrong, unusual, or exploitable to you?"
**Receives (Tier 2):** Random sample of manifest files, not security-partitioned. Selection is deterministic per run: seed = hash(run-id + manifest content hash). This ensures different samples when the manifest changes and different samples on re-runs even within the same timestamp (since run-id includes a unique component).
**Dispatch:** Single agent.

#### 6. Chain Analyst

**Prompt:** `siege-chain-analyst-prompt.md`
**Perspective:** Strategic attacker chaining multiple small weaknesses into a high-impact exploit.
**Purpose:** Finds multi-step attack paths that no single-perspective agent would flag. Operates on the coverage map from other agents (NOT their raw findings -- same anti-anchoring principle as audit's blind-spots agent).
**Input:** Tier 1 overview + coverage map (built from agents 1-5's partition records) + Tier 2 source files at trust boundaries and cross-component interfaces.
**Coverage map contents:** The coverage map contains ONLY file-to-agent assignments (which files were sent to which agent) and examination status (examined/overflow-summary/not-examined). Agent assignments in the coverage map are anonymized: use 'Agent-1' through 'Agent-5' instead of perspective names. The Chain Analyst does not need to know WHICH perspective examined each file -- only which files were examined vs. not examined. This preserves anti-anchoring by preventing the Chain Analyst from inferring what attack vectors were already explored. It does NOT contain finding counts, severity, or any information about what agents found. This is deliberately different from audit's coverage map which includes finding counts per lens.
**Trust boundary file selection:** Trust boundary files for the Chain Analyst's Tier 2 come from the persistent THREAT MODEL (Phase 1 Step 3, Trust Boundaries section) and the MANIFEST (Phase 1 Step 2, specifically interfaces and API surface files). They are NEVER selected based on agent findings. If no prior threat model exists, trust boundary files are identified from the manifest by selecting: (a) files at module/service boundaries, (b) API route handlers and middleware, (c) authentication/authorization entry points, (d) data serialization/deserialization interfaces.
**Input budget:** Coverage map: 40 lines max. Remaining budget after Tier 1 + coverage map goes to source files at trust boundary crossings.
**Hunts for:** Authentication bypass chains, data flow paths that cross trust boundaries without re-validation, time-of-check/time-of-use windows exploitable by attackers, dependency chains where a compromised package enables lateral movement.
**Anti-restatement rule:** Every chain must pass the cross-boundary test — vulnerabilities A and B must be in different files or components, connected by a concrete mechanism. A single vulnerability's consequences described in multiple steps is not a chain. Chains that fail this test are rejected.
**Dispatch:** Runs AFTER agents 1-5 complete (needs their partition records for the coverage map). This is the only sequential dependency.

**Write-on-complete:** Each agent writes findings immediately to `scratch/<run-id>/<agent>-findings.md` on completion. Partition records written to `scratch/<run-id>/<agent>-partition.md` before dispatch.

### Consensus Integration

At the start of Phase 2, check whether `consensus_query` MCP tool is available. If available, use `consensus_query(mode: "review")` for one of the 6 agent dispatches (the Chain Analyst, since it performs synthesis-level reasoning where model blind spots are costliest). This replaces the single-model Chain Analyst dispatch, not supplements it. If unavailable, all agents use standard single-model dispatch.

**Output normalization:** The orchestrator normalizes consensus output to the standard 5-line finding format before writing to `chain-analyst-findings.md`. Provenance metadata (which models contributed, confidence scores, agreement levels) is preserved as a comment block at the top of the findings file but is NOT passed to Phase 3 synthesis. Anti-anchoring: synthesis should not weight findings based on which model raised them or how many models agreed.

## Phase 3: Synthesis

Orchestrator reads all 6 findings files from `scratch/<run-id>/`. Steel-man-then-kill: for each finding, the orchestrator first articulates the strongest case that the finding is a false positive, then attempts to refute that case with evidence from the codebase. Findings that survive steel-manning proceed; findings that do not are demoted to "Noted" (below Minor) with the steel-man reasoning documented.

1. **Mechanical dedup (orchestrator, no agent dispatch):**

   The orchestrator runs dedup before steel-manning. This is deterministic and requires no LLM reasoning.

   **Step 1 — Parse:** Read all `<agent>-findings.md` files from `scratch/<run-id>/`. Extract the `<!-- dedup: file=[path] line=[start-end] cwe=[CWE-ID] agent=[agent_name] -->` metadata from each finding into a structured list.

   **Step 2 — Exact dedup:** Group findings by `(file, cwe)`. Within each group, merge findings whose line ranges overlap (e.g., lines 10-25 and lines 15-30 overlap). Keep the finding with the highest severity as the primary; append other agent names as "also flagged by: [agents]". Write merged finding count to the report.

   **Step 3 — Fuzzy dedup (same root cause, different CWEs):** Within the same file, findings from different agents that reference the same function or code block (overlapping line ranges, any CWE) are likely the same root cause seen from different perspectives. Group these as a "cluster" — present as a single finding with the highest severity, noting the multiple CWEs and perspectives. Example: Boundary Attacker flags CWE-89 (SQL injection) on line 42, Betrayed Consumer flags CWE-200 (information exposure) on line 44 of the same function — these are one root cause (unsanitized input reaches a query that leaks data), not two findings.

   **Step 4 — Write dedup summary:** Write `scratch/<run-id>/dedup-summary.md` with: raw finding count, exact-dedup merges, fuzzy-dedup clusters, final deduplicated count. This is the set that enters steel-man-then-kill.
1b. **Design-phase cross-reference:** If this Siege run targets code that had a prior design-phase red-team or Siege run on the design doc, check the threat model's Historical Findings for matches. Tag findings that were already flagged at design time: "Previously flagged in design review — implementation did not address." This helps triage: design-flagged findings that persist into code are higher priority than net-new findings.
2. **Chain detection:** After dedup, scan for findings from different agents that touch the same data flow path or trust boundary. Flag as a chain ONLY when the orchestrator can articulate the specific multi-step exploitation scenario. Proximity alone is not chaining. Assign exploitability to each chain using weakest-link inheritance: if any step is Hardening, the chain is Hardening. A chain is Active only when every step is independently exploitable today.
3. **Severity classification** (no demotion without proof):
   - **Critical:** Exploitable with no authentication, or leads to full system compromise, or affects all users. Equivalent to CVSS 9.0+.
   - **High:** Exploitable with some prerequisites (valid session, specific input), significant data exposure or privilege escalation. CVSS 7.0-8.9.
   - **Medium:** Requires unlikely conditions or provides limited impact. CVSS 4.0-6.9.
   - **Low:** Theoretical, defense-in-depth improvement, or informational.
   - **Severity promotion bias:** When a finding sits between two severity levels, promote. Solo dev, silent security bugs are expensive. Demotion requires concrete proof that the exploitation scenario is infeasible (not merely unlikely).

   **Exploitability tag (required on every finding):**
   Every finding must be tagged with exactly one exploitability class. This is orthogonal to severity — a High/Active is urgent, a High/Hardening is important but not on fire.
   - **Active:** Exploitable in the current codebase without hypothetical preconditions. An attacker can trigger this today.
   - **Hardening:** Not currently exploitable, but the design has a latent weakness that becomes exploitable if a reasonable future change occurs (e.g., a new route added without the same guard, a config flag flipped). These matter — but they are a different urgency than active vulnerabilities.

   The tag appears in both the 5-line initial format and the full report format. The final report groups findings by exploitability within each severity level (Active first, then Hardening).
4. **Deployment context severity adjustment:** When `deployment_context: intranet`, apply network-level downgrade after severity classification:
   - Classify each finding as network-level or application-level using the categories from the Parameters section
   - Network-level findings: downgrade severity by 1 (Critical→High, High→Medium, Medium→Low, Low→Informational)
   - Application-level findings: no change
   - Log each downgrade: `Downgraded [ID] from [original] to [adjusted] — intranet deployment context (network-level finding)`
   - Preserve original severity in finding metadata: `Original-Severity: [severity]`
   - When `deployment_context` is `public`, `hybrid`, or unset: no adjustment
5. **Write initial report** to `scratch/<run-id>/report.md` using the initial lightweight finding format.

## Phase 4: Security Gate (Iterative Loop)

The security gate iterates until **zero Critical + zero High** findings remain, or stagnation is detected.

### Gate Mechanics

Adopts quality-gate's iterative pattern with security-specific scoring.

**Scoring:** Critical = 5, High = 2, Medium = 0 (medium findings are tracked but do not block the gate). Both Active and Hardening findings contribute equally to the gate score — exploitability affects triage priority in the report, not gate blocking. A Critical/Hardening finding ("one reasonable change from full compromise") is too dangerous to pass through.

**Loop:**
1. Present findings from Phase 3 (or latest round) to the fix agent
2. Fix agent remediates Critical and High findings (see Fix Mechanism below). **One commit per finding** — not a batch commit. Each commit message: `fix(security): address [SIEGE-XX-N] — [title]`
3. **Fix approval output (non-blocking):** After the fix round completes, output a per-fix commit table:

   ```
   ## Siege Fix — Round N

   | # | Finding | Approach | Files | Commit |
   |---|---------|----------|-------|--------|
   | 1 | [SIEGE-BA-1] SQL injection | Parameterized query | UserController.cs | abc1234 |
   | 2 | [SIEGE-IT-3] IDOR on /api/records | Added ownership check | RecordService.cs | def5678 |

   **To reject a fix:** `git revert <commit-sha>` (each fix is a separate commit)
   **To accept all:** No action needed — fixes are already applied.
   ```

   The pipeline does NOT pause. The next review round proceeds immediately with the current code state (fixes applied). If the user rejects a fix between rounds, the next review will re-find the vulnerability — this is correct behavior.
4. Dispatch a FRESH review round: 2 agents only (Boundary Attacker + one rotating agent). The rotating agent is selected based on the security domain of files modified by the fix agent: auth/RBAC changes → Insider Threat, data/logging changes → Betrayed Consumer, config/infra changes → Infrastructure Prober, multi-domain or ambiguous → Chain Analyst. On every 3rd round, the Fresh Attacker replaces the rotating domain agent (keeping the count at 2 review agents per round). When the Fresh Attacker is included in a Phase 4 round, it receives the full fix diff plus a random sample of unchanged files from the manifest (same 40% sampling strategy as Phase 2, re-seeded for this round). This preserves its 'fresh eyes on broader context' value -- it reviews the fix AND looks for new issues the fix may have exposed in surrounding code. Full 6-agent re-dispatch is disproportionate for incremental fixes.
4. Score the new findings. Compare to prior round:
   - Strictly lower score = progress, loop again
   - Same or higher score = dispatch Stagnation Judge

In addition to prior-round comparison, track the lowest score achieved in any prior round (the high-water mark). If the current round's score exceeds this minimum by 3 or more points, treat as regression regardless of the stagnation judge's domain-shift assessment.

**Fix mechanism:**

| Artifact Type | Fix Agent | Action |
|---|---|---|
| `design` | Plan Writer subagent (Opus) | Revises design to close the vulnerability |
| `plan` | Plan Writer subagent (Opus) | Adds security tasks, reorders to close gaps |
| `code` | Fix subagent (Opus, new instance) | Patches the vulnerability with verification criteria |

Design and plan fix agents write the revised artifact back to its original path (the design doc or plan file). Review agents read from the same path. Anti-anchoring is maintained because the revised doc contains no revision marks -- the fix agent produces a clean replacement.

**Before dispatching the fix agent (code artifacts only):** If crucible:checkpoint is available, create checkpoint with reason 'pre-siege-fix-round-N'.

After each fix agent commits, update `expected-head.md` with the new HEAD SHA (code artifacts only). For design and plan artifacts, Phase 4 integrity is maintained by the revised artifact at its original path rather than git HEAD tracking. The commit anchor check is skipped for non-code artifacts.

The fix agent writes `expected-head.md` as its final action before returning results to the orchestrator, not the orchestrator after receiving results. This closes the timing gap between commit and HEAD tracking. If compaction occurs during a fix round and `expected-head.md` is stale, recovery should compare HEAD against the most recent fix journal entry's 'Files changed' field -- if the diff matches a plausible fix commit, proceed rather than abort.

**Fix verification:** After each fix agent completes, dispatch a verification check using the finding's Verification Criteria (from the finding format). If the verification criteria specify a concrete check (e.g., grep for parameterized query, confirm endpoint requires auth token, verify header is set), run the check. Use Sonnet for verification -- this is mechanical confirmation, not analytical reasoning. Dispatch using verification criteria from the finding. The verifier checks mechanically: does the fix satisfy the stated verification condition? If the fix does not satisfy the verification criteria, flag the finding as "unresolved" in the fix journal with the failed verification output. Unresolved findings remain in the gate score for the next round.

**Unresolved escalation:** Critical-severity Unresolved: flag as binding with one-round grace. If the same Critical is Unresolved again (persistent verifier disagreement), the binding downgrades to informational -- Sonnet should not permanently override Opus. High-severity Unresolved: appended to fix journal as informational context.

**Fix journal:** Same as quality-gate's fix journal pattern. Maintained in `scratch/<run-id>/fix-journal.md`. Fix agents receive full journal on round 2+. Red-team reviewers NEVER receive the journal (anti-anchoring preserved).

### Anti-Anchoring Rules

1. Clean code only. If the fix agent left comments referencing findings (e.g., `// Fixed: SIEGE-001`), strip them before the next review round.
2. Standardized framing. The dispatch prompt for review agents uses the same framing every round. Do not mention prior rounds, what was fixed, or how many rounds have run.
3. No findings forwarding. Prior round findings are never passed to review agents.

**Stagnation detection:** Same two-layer system as quality-gate. Orchestrator scoring first pass, then Sonnet stagnation judge for semantic comparison. Judge prompt includes security-specific context: "Is the fix addressing the root cause or just the symptom? Is the vulnerability being moved rather than eliminated?"

Siege uses its own stagnation judge prompt (`./siege-stagnation-judge-prompt.md`) with security-specific semantics. The three verdicts:
- **PROGRESS:** Fix addressed root cause; new findings are in different security domains.
- **STAGNATION:** Fix addressed symptom only; same vulnerability persists under different framing (e.g., input sanitization added but bypassable).
- **DIMINISHING_RETURNS:** Remaining findings require architectural redesign (e.g., "this authorization model cannot support the required access control granularity"). Unlike quality-gate, DIMINISHING_RETURNS for security findings is an escalation, not an acceptance -- it means the design has a security flaw.

**Oscillation detection:** If weighted score increases between rounds, escalate immediately as regression. Include checkpoint reference from the prior round's pre-fix checkpoint.

**Safety limit:** 10 rounds (security fixes should converge faster than general quality; 10 rounds indicates a fundamental design issue).

**Progress notification:** After round 3 and every 2 rounds thereafter (rounds 3, 5, 7, 9).

### Escalation and Accepted Risks

Three exit modes beyond clean passage:

- **Clean (zero Critical + zero High):** Gate passes. Medium and Low findings are presented as recommendations. Proceed to Phase 5.
- **Stagnation:** Escalate to user with full round history and recurring findings.
- **User override:** User may acknowledge Critical/High findings and accept the risk. This is NOT silent suppression:
  1. User must provide a written rationale for each accepted finding
  2. Rationale is written to `scratch/<run-id>/accepted-risks.md` with timestamp, finding ID, severity, and user rationale
  3. Accepted risks are appended to the persistent threat model (Phase 5)
  4. Accepted findings are excluded from the gate score on subsequent rounds
  5. Sentinel companion (see below) re-evaluates accepted risks weekly

### False Positive Handling

If the fix agent or user identifies a finding as a false positive:
1. Orchestrator verifies: can the exploitation scenario be concretely demonstrated or is it purely theoretical given the codebase's constraints?
2. If verified false positive: mark as "False Positive" with evidence, exclude from scoring, do not write to threat model
3. If disputed: keep at current severity, note the dispute in the finding. No silent demotion.

## Finding Format

### Initial Findings (Per-Agent Output) -- 5 Lines Max

```
**[ID]** [severity] [Active|Hardening] -- [title]
File: [path]:[line_range] | Agent: [agent_name]
Attack: [1-sentence exploitation scenario]
Evidence: [specific code reference or design element]
Verification: [concrete test or check that confirms the vulnerability]
```

Agents output findings in this format only. No blast radius, no extended analysis. This keeps per-agent output under 30 lines for a typical 5-finding set.

### Structured Dedup Fields

For mechanical deduplication before steel-manning, each finding also includes structured metadata as a comment block:

```
<!-- dedup: file=[path] line=[start-end] cwe=[CWE-ID] agent=[agent_name] -->
```

The orchestrator uses these fields for first-pass mechanical dedup: same file + overlapping line range + same CWE = merge. Steel-man-then-kill runs only on the deduplicated set, reducing synthesis cost.

### Full Report Findings (Critical and High Only) -- Phase 3 Output

Critical and High findings are expanded in the Phase 3 report:

```
### [ID]: [title]
**Severity:** [Critical|High] | **Exploitability:** [Active|Hardening] | **Agent:** [agent_name] | **Chain:** [yes/no]
**File:** [path]:[line_range]

**Exploitation Scenario:**
[2-4 sentences: who attacks, how, what they gain]

**Blast Radius:**
- Data exposure: [what data is at risk]
- User impact: [how many users, what they experience]
- System impact: [lateral movement, persistence, escalation potential]

**Verification Criteria:**
1. [Concrete test or reproduction step]
2. [Expected result that confirms the fix]

**Steel-Man (why this might not be exploitable):**
[1-2 sentences: strongest case for false positive, and why it was rejected]
```

Medium and Low findings remain in the 5-line initial format in the final report.

## Output Format (Final Report)

Written to `scratch/<run-id>/report.md` and presented to the user.

```markdown
# Siege Security Audit Report
**Target:** [subsystem/artifact name]
**Commit Anchor:** [full SHA]
**Date:** [ISO-8601]
**Intelligence:** [sources consulted, gaps noted]
**Artifact Type:** [design|plan|code|mixed]

## Scope Limitations
[What Siege cannot detect -- see Known Limitations. Always present.]

## Attack Chains
[Multi-step chains identified by Chain Analyst, with full exploitation narrative. Chains are the highest-signal output — present them first so the reviewer sees composed threats before individual findings.
Chains inherit exploitability from their weakest link: if ANY step in the chain requires a future change to become exploitable, the entire chain is Hardening. A chain is Active only when every step is independently exploitable today.]

## Critical Findings
### Active Vulnerabilities
[Full report format for each, or "None"]
### Hardening
[Full report format for each, or "None"]

## High Findings
### Active Vulnerabilities
[Full report format for each, or "None"]
### Hardening
[Full report format for each, or "None"]

## Medium Findings
[Initial 5-line format for each, or "None". Medium and Low use the compact 5-line format which includes the exploitability tag per-finding. No Active/Hardening sub-grouping — these severities do not block the gate, so triage ordering is less critical.]

## Low Findings
[Initial 5-line format for each, or "None"]

## Accepted Risks
[Any findings the user acknowledged with rationale, or "None"]

## Threat Model Delta
[New surfaces, retired surfaces, drift from prior model]

## Agent Coverage
[Which agents examined which files -- partition summary]
```

## Persistence

### Threat Model

**Path:** `~/.claude/projects/<project-hash>/memory/security-audit/threat-model.md`

Updated at the end of every Siege run (Phase 5). Accumulates across sessions.

**Structure:**

```markdown
# Threat Model
**Last updated:** [ISO-8601]
**Last commit anchor:** [SHA]
**Deployment context:** [intranet|public|hybrid|unset]

## Trust Boundaries
- [boundary]: [description, files involved]

## Attack Surfaces
- [surface]: [exposure level, last reviewed date, source: exposure-map | manual]
<!-- Phase 5 updates this from exposure-map.md: new endpoints not in prior model are flagged "new attack surface"; endpoints in prior model but absent from current enumeration are flagged "retired surface" in the Threat Model Delta section of the report. -->

## Historical Findings
### [date] -- [target]
- [finding ID]: [severity] [Active|Hardening] [title] -- [status: resolved|accepted|open]

## Accepted Risks
- [finding ID]: [severity] [Active|Hardening] [title] -- Accepted [date] by [user]
  Rationale: [user-provided rationale]
  Next review: [date, set by sentinel schedule]
```

### Accepted Risks Security

Accepted risks contain attacker-relevant information (what is known to be vulnerable and why the team chose not to fix it). Access control:

1. `memory/security-audit/` is added to `.gitignore` by the orchestrator on first Siege run (if not already present). The canonical path is under `~/.claude/projects/`, which is outside the repo. The `.gitignore` entry is a defensive measure for non-standard setups where memory is configured inside the repo. The staging detection warning (point 3) is the primary protection.
2. Threat model and accepted risks are NEVER committed to the repository
3. The orchestrator warns if it detects `threat-model.md` or `accepted-risks.md` in git staging: "Security data detected in git staging. Removing from staging area. These files must not be committed."

### Preferences

**Path:** `~/.claude/projects/<project-hash>/memory/security-audit/preferences.md`

```markdown
## Siege Preferences
- Last scan: [ISO-8601]
- Default scope: [subsystem name or "full"]
- Agent count: [4 or 6, based on last scope size]

## Intelligence Source History
| Source | Last attempt | Status | Notes |
|--------|-------------|--------|-------|
| pnpm audit | 2026-03-30 | success | 2 CVEs found |
| CISA KEV | 2026-03-30 | failed | WebFetch timeout |
| OWASP cheat sheets | never | not attempted | |

On subsequent runs, retry failed sources. If a source fails 3 consecutive times, skip by default but note in scope limitations.
```

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** Identical to audit's communication requirement.

Every status update must include:
1. **Current phase** -- Which phase you are in
2. **What just completed** -- What the last agent reported (finding count, not finding details)
3. **What is being dispatched next** -- What you are about to do and why
4. **Agent status** -- Which agents have reported vs. still in flight

**After compaction:** Re-read the scratch directory and current state before continuing.

## Pipeline Status

Write a status file to `~/.claude/projects/<project-hash>/memory/pipeline-status.md` at every narration point. Same format as audit and build.

### Skill-Specific Body

```
## Agents
- Boundary Attacker: DONE (3 findings)
- Insider Threat: DONE (1 finding)
- Infrastructure Prober: IN PROGRESS
- Betrayed Consumer: PENDING
- Fresh Attacker: PENDING
- Chain Analyst: WAITING (needs agents 1-5)

## Security Gate
- Round: 2 of 10
- Score: 12 -> 7 (progress)
- Critical: 1 -> 0
- High: 3 -> 2
```

### Health State Machine

- **Phase boundaries** (reset to GREEN): Phase 1->2, 2->3, 3->4, 4->5
- **YELLOW:** agent running >10 minutes, security gate round 3+, intelligence fetch failed
- **RED:** multiple agents failed, gate stagnation, commit anchor violated

## Compaction Recovery

### Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/security-audit/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at the start of Phase 1 (e.g., `2026-03-30T09-15-00`).

**Stale cleanup:** At the start of each Siege run, delete scratch directories that are NOT referenced by an `active-run-*.md` marker AND are older than 4 hours. The marker check is the primary protection -- a 10-round gate at 15 min/round can exceed 2 hours, so the time window is a secondary safety net only.

**Active run marker:** Write `~/.claude/projects/<project-hash>/memory/security-audit/active-run-<run-id>.md` at start. Delete on completion. After compaction, glob for active-run markers to locate the run.

**Tool constraint:** All scratch directory operations (create, read, list, delete) must use Write, Read, and Glob tools — NOT Bash. Safety hooks block Bash commands referencing `.claude/` paths.

### File Inventory

| File | Written When | Purpose |
|------|-------------|---------|
| `commit-anchor.md` | Phase 1 start | TOCTOU prevention |
| `manifest.md` | Phase 1 Step 2 | Scoped file list |
| `exposure-map.md` | Phase 1 Step 2.5 | Enumerated endpoints with manifest cross-reference |
| `gate-approved.md` | User confirms scope | Compaction recovery marker |
| `intelligence-summary.md` | Phase 1 Step 1 | Pre-fetched intelligence (50 lines) |
| `<agent>-partition.md` | Before each agent dispatch | Files sent as full source |
| `<agent>-findings.md` | On agent completion | Per-agent findings |
| `coverage-map.md` | Before Chain Analyst dispatch | Agent coverage for chain analysis |
| `tier1-context.md` | Phase 2 Step 1 | Shared Tier 1 context block |
| `dedup-summary.md` | Phase 3 Step 4 | Raw → deduplicated finding counts and merge log |
| `report.md` | Phase 3 | Synthesized findings |
| `fix-journal.md` | Phase 4, per fix round | Cumulative fix history |
| `round-N-score.md` | Phase 4, per round | Weighted score snapshot |
| `round-N-findings.md` | Phase 4, per round | Findings per gate round |
| `round-N-comparison.md` | Phase 4, when judge dispatched | Stagnation judge output |
| `accepted-risks.md` | Phase 4, on user override | Accepted findings with rationale |
| `expected-head.md` | Phase 4, after each fix commit | Current expected HEAD SHA after fix rounds |
| `round-N-verification.md` | Phase 4, after every fix round | Fix verification results per round |

### Recovery Procedure

After compaction:
1. Glob for `active-run-*.md` to locate scratch directory
2. Read `commit-anchor.md`. If `round-N-score.md` files exist (Phase 4 in progress), read `expected-head.md` and verify HEAD against that instead. If no Phase 4 files exist, verify HEAD against commit-anchor.md. Mismatch = abort.
3. Determine phase from file presence:
   - No `gate-approved.md` -> re-present manifest
   - `<agent>-findings.md` files -> count completed agents, dispatch remaining
   - `coverage-map.md` without `chain-analyst-findings.md` -> dispatch Chain Analyst
   - `report.md` without `round-1-score.md` -> enter Phase 4
   - `round-N-score.md` files -> resume gate at round N+1
4. Read `pipeline-status.md` to recover Started timestamp and Recent Events
5. Output status to user before continuing

### Checkpoint Timing

Emit a Compression State Block at each of the following points:
- Phase transitions (1→2, 2→3, 3→4, 4→5)
- Every 2 gate rounds in Phase 4
- Before stagnation judge dispatch
- On health transitions (GREEN→YELLOW, YELLOW→RED, etc.)

**Block content:**
```
## Compression State
- Goal: [current siege objective]
- Skill: siege
- Phase: [current phase and step]
- Health: [GREEN|YELLOW|RED]
- Key Decisions: [severity judgments from Phase 3, accepted risks, stagnation outcomes]
- Active Constraints: [commit anchor SHA, expected-head SHA, gate round, score trajectory]
- Next Steps: [immediate next action]
```

**Recovery step 0:** Before file-based recovery (Recovery Procedure step 1), read the Compression State from `pipeline-status.md` to re-establish context.

### Session Tracking

- **Metrics:** `/tmp/crucible-siege-metrics-<run-id>.log` -- agent dispatches, completion times, finding counts
- **Decision journal:** `/tmp/crucible-siege-decisions-<run-id>.log` -- scoping decisions, severity judgments, steel-man reasoning

## Phase 5: Threat Model Update

After the security gate passes (or user accepts risks and proceeds):

1. Read existing `~/.claude/projects/<project-hash>/memory/security-audit/threat-model.md` (or create if first run)
2. Merge new findings into Historical Findings (resolved findings from fix rounds, accepted risks, open items)
3. Update Trust Boundaries and Attack Surfaces based on analysis. If `scratch/<run-id>/exposure-map.md` exists, merge its endpoints into Attack Surfaces: new endpoints not in the prior model are flagged "new attack surface"; endpoints present in the prior model but absent from the current enumeration are flagged "retired surface" in the Threat Model Delta.
4. Record the Threat Model Delta in the report
5. Write updated threat model to disk
6. **Copy the final report** from `scratch/<run-id>/report.md` to `memory/security-audit/reports/<date>-<target>.md` for persistent access. Scratch directories are cleaned up on subsequent runs; the report copy ensures findings survive cleanup.
7. Verify `memory/security-audit/` is in `.gitignore`
8. Delete scratch directory and active-run marker after Phase 5 completes. This is the final step of every Siege run.

## Sentinel Companion (Separate Skill)

Sentinel is a **separate skill** (`crucible:sentinel`) running on a weekly cron. It is NOT part of Siege's execution -- it is a persistent watchdog that uses Siege's threat model.

### 4 Probes

1. **Dependency drift:** Run `npm audit` / `pip audit` / `cargo audit` and compare against the threat model's last-known dependency state. Flag new CVEs.
2. **Accepted risk review:** Re-evaluate each accepted risk in `threat-model.md`. Has the codebase changed in ways that make the risk more severe? Has a related CVE been published?
3. **Surface drift:** Compare current codebase structure against the threat model's attack surfaces. Flag new files in security-sensitive directories that were not present at last review.
4. **Intelligence check:** Fetch CISA KEV and compare against project dependencies. Flag any new additions.

### Output

Sentinel writes its findings to `memory/security-audit/sentinel-report-<date>.md`. If any probe finds Critical or High issues, it emits a terminal notification: "Sentinel detected [N] security issues since last Siege run. Run `/siege` to investigate."

### Invocation

Sentinel is designed for `cron` or scheduled task execution. It does not require user interaction. Configuration stored in `memory/security-audit/sentinel-config.md`:

```markdown
## Sentinel Configuration
- Schedule: weekly (Sunday 02:00 UTC)
- Last run: [ISO-8601]
- Alert threshold: High (notify on High+, log Medium+)
```

## Prompt Templates

- `./siege-boundary-attacker-prompt.md` -- External attacker perspective dispatch
- `./siege-insider-threat-prompt.md` -- Authenticated user perspective dispatch
- `./siege-infrastructure-prober-prompt.md` -- Infrastructure and config perspective dispatch
- `./siege-betrayed-consumer-prompt.md` -- Downstream trust violation perspective dispatch
- `./siege-fresh-attacker-prompt.md` -- Zero-context cold-start dispatch
- `./siege-chain-analyst-prompt.md` -- Multi-step attack chain analysis dispatch
- `./siege-stagnation-judge-prompt.md` -- Security-specific stagnation judgment dispatch

Prompt templates are created during skill implementation. Each template follows the pattern established by audit's lens prompts: perspective definition, what to hunt for, what NOT to hunt for, input sections (Tier 1 + Tier 2), output format (5-line initial finding format), and context self-monitoring at 50%+ utilization.

## Integration

- **Invoked by:** User directly (`/siege`), or recommended by `crucible:audit` when security surfaces are detected
- **Invokes:** None (Siege is self-contained; it dispatches its own agents)
- **Consults:** `crucible:cartographer` (Mode 2: consult map) for subsystem boundaries and dependency graphs
- **Consults:** `consensus_query` MCP tool for Chain Analyst dispatch (when available)
- **Persistence:** `~/.claude/projects/<project-hash>/memory/security-audit/threat-model.md` (read at start, written at end)
- **Pairs with:** `crucible:build` -- Siege can run after build Phase 4 (implementation) when the activation heuristic triggers
- **Pairs with:** `crucible:audit` -- audit may recommend Siege; Siege never invokes audit
- **Does NOT use:** `crucible:quality-gate` (Siege has its own security-specific gate), `crucible:red-team` (Siege's agents ARE the red team, specialized for security)

### Severity Mapping to Build Pipeline

When Siege findings are passed to the build pipeline or quality-gate, use this mapping:

| Siege Severity | Pipeline Severity |
|----------------|-------------------|
| Critical | Fatal |
| High | Significant |
| Medium | Minor |
| Low | Minor |

Siege reports use Siege vocabulary internally. The mapping applies only when findings cross skill boundaries (e.g., Siege report consumed by build or quality-gate).

## Eval Strategy

Siege effectiveness is measured by:
1. **False positive rate:** Track findings marked as false positives across runs. Target: <15% false positive rate.
2. **Coverage:** Track which CWE categories are flagged vs. present in the codebase. Measure against OWASP Top 10 coverage.
3. **Gate convergence:** Track rounds-to-zero-critical-high. Target: <5 rounds for code artifacts, <3 for design/plan.
4. **Threat model utility:** Track how often sentinel catches real drift vs. noise.
5. **Steel-man accuracy:** Track how often steel-manned dismissals are later proven wrong (finding re-surfaces in production or in a later Siege run).

## Guardrails

**Agents must NOT:**
- Modify any code during Phase 2 (analysis is read-only; fixes happen in Phase 4 only)
- Flag findings without specific evidence (no "consider adding input validation" without pointing to the exact unvalidated input)
- Exceed 5 findings per agent (focus on highest-impact; the Chain Analyst cap is 5 chains). Every **Active** finding must have a concrete, demonstrable exploitation scenario in the CURRENT codebase. **Hardening** findings must name a specific, reasonable future change that would make the weakness exploitable — not hypothetical future code in general, but a concrete change (e.g., "adding a public route that calls this unguarded helper"). Speculative findings that cannot identify either a current exploit or a named future-change trigger are not findings.
- Speculate about vulnerabilities in code they did not receive in their Tier 2 partition
- File findings where no concrete exploitation scenario (Active or Hardening) can be constructed. If unsure, the agent should either commit to the finding (with evidence of a current exploit or a named future-change trigger) or not file it.

**The orchestrator must NOT:**
- Proceed to Phase 2 without user-confirmed manifest
- Demote severity without concrete evidence of infeasibility
- Silently drop accepted risks from the threat model
- Skip the commit anchor verification before Phase 4
- Exceed 1500 lines of total prompt content in any agent dispatch
- Pass findings or fix journal to red-team review agents (anti-anchoring)
- Skip narration between agent dispatches
- Dispatch agents without tracking the running total. Notify user at 20 agent dispatches ("20 agents dispatched so far, continuing gate rounds."). Hard-stop at 40 dispatches without explicit user approval. Include running agent count in progress notifications.
- Commit threat model or accepted risks to the repository

## Red Flags

- Running Siege below the scope-appropriate agent count (3/4/6 -- match the scope, not convenience)
- Treating Siege findings as audit findings (security findings require exploitation scenarios, not just code quality observations)
- Mixing active vulnerabilities and design hardening without the exploitability tag (different urgency, different reviewer response)
- Filing findings where no exploitation scenario (Active or Hardening) can be constructed (wastes reviewer time)
- Skipping the Chain Analyst (the most valuable agent for finding real-world exploits)
- Accepting risks without written rationale (silent suppression)
- Committing `threat-model.md` or `accepted-risks.md` to the repository
- Losing agent results to context compaction (write to disk immediately)
- Running Phase 4 gate on a different commit than the anchor (TOCTOU)
- Demoting severity because "it's unlikely" without proving infeasibility
- Forwarding fix journal or prior findings to review agents (anti-anchoring violation)
- Treating the Fresh Attacker as redundant (it exists specifically to break epistemic closure)

## Known Limitations

**Include this section verbatim in every Siege report under "Scope Limitations."**

1. **No dynamic analysis.** Siege performs static review only. It cannot detect vulnerabilities that require runtime behavior (timing attacks, memory corruption in native code, race conditions that depend on system load).
2. **Model blind spots.** All 6 agents are Opus instances. They share training-data blind spots. The Fresh Attacker and consensus integration (when available) mitigate but do not eliminate this. Novel vulnerability classes not in training data will be missed.
3. **No penetration testing.** Siege does not execute exploits, send malicious payloads, or interact with running systems. Findings are analytical, not proven.
4. **Dependency scanning depth.** Dependency audit tools report known CVEs only. Zero-day vulnerabilities in dependencies are invisible.
5. **Intelligence staleness.** Training-data knowledge of OWASP/SANS/CISA may be outdated. WebFetch supplements this when available but is not guaranteed.
6. **Scope boundary.** Siege reviews what is in the manifest. Vulnerabilities in code outside the manifest (shared libraries, infrastructure-as-code not in scope, third-party services) are not covered.
7. **Social engineering and physical access.** Entirely out of scope.
8. **Cryptographic implementation review.** Siege can identify use of weak algorithms or incorrect API usage, but cannot verify the correctness of custom cryptographic implementations. Recommend dedicated crypto audit for custom crypto.
