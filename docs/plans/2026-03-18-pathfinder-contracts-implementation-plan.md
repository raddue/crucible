# Pathfinder Contract Surface Extraction — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Add opt-in contract surface extraction and cross-repo sync verification to the existing pathfinder analysis pipeline. Tier 1 extracts provider contracts (OpenAPI, Proto, GraphQL, TypeScript types), Tier 2 extracts consumer contracts (what endpoints/RPCs the code actually calls), synthesis cross-references them to detect mismatches (phantom endpoints, deprecated usage, version skew, schema drift), and query mode gains two new contract-aware query types (`consumers`, `safe-to-change`).

**Architecture:** Markdown-only changes across 5 files (0 new, 5 modified). No application code. The implementation extends tier1-analyzer-prompt.md with provider contract extraction, extends tier2-analyzer-prompt.md with consumer contract extraction and GraphQL client patterns, adds a Contract Verification step to synthesis-prompt.md, adds contract-aware queries to query-handler-prompt.md, and updates SKILL.md with checkpoint options and contract documentation. 5 tasks across 3 waves.

**Design doc:** `docs/plans/2026-03-18-pathfinder-contracts-design.md`

---

## Dependency Graph

```
Task 1 (tier1-analyzer-prompt.md) ── no deps ───────────────────────┐
Task 2 (tier2-analyzer-prompt.md) ── no deps ───────────────────────┤
Task 3 (synthesis-prompt.md) ── depends on 1, 2 ───────────────────┤
Task 4 (query-handler-prompt.md) ── depends on 3 ──────────────────┤
Task 5 (SKILL.md) ── depends on 1, 2, 3, 4 ────────────────────────┘
```

---

### Task 1: Extend Tier 1 Analyzer with Provider Contract Extraction

Add provider contract extraction to the existing Tier 1 analyzer prompt. This extends the existing Step 3 ("Proto and API Definitions") to also extract the full contract surface from files it already reads, and adds a new `provider_contracts` output field. A new `Contract Extraction` input field controls whether extraction runs.

- **Files:** `skills/pathfinder/tier1-analyzer-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Read `skills/pathfinder/tier1-analyzer-prompt.md` to confirm the current structure.

2. **Add `Contract Extraction` input section.** After the existing `### Org Names` input section (around line 35) and before the `---` separator that precedes the Process section, add a new input block:

   ```markdown
   ### Contract Extraction

   `[PASTE: "enabled" or "disabled" — when enabled, extract provider contract surfaces from files scanned in Step 3. Default: "enabled" for Tier 1 since contract files are already read at zero extra cost.]`
   ```

3. **Extend Step 3 ("Proto and API Definitions").** The current step (lines 69-74) scans `**/*.proto` and `openapi.yaml`/`swagger.json` and extracts proto imports and API endpoint definitions. Add the following after the existing content within this step:

   First, add GraphQL files to the scan list by changing the scan line from:
   ```
   Scan: `**/*.proto` (excluding `**/node_modules/**`, `**/vendor/**`), `openapi.yaml`, `swagger.json`
   ```
   to:
   ```
   Scan: `**/*.proto` (excluding `**/node_modules/**`, `**/vendor/**`), `openapi.yaml`, `openapi.json`, `swagger.json`, `swagger.yaml`, `**/*.graphql`, `schema.graphql`, `schema.gql`
   ```

   Then add the following after the existing bullet points ("Extract proto imports" and "Extract API endpoint definitions"):

   ```markdown
   **Provider Contract Extraction (when Contract Extraction input is "enabled"):**

   In addition to the existing edge-detection scanning above, extract the full contract surface from each file type:

   - **Proto files:** Extract the full service surface — all `service` names, every `rpc` method with its input and output message types, and whether `[deprecated = true]` is set on each RPC. Record the `package` declaration.
   - **OpenAPI/Swagger specs:** Parse the full spec — all paths with their HTTP methods, the `deprecated` flag on each operation, and the `info.version` field from the spec root.
   - **GraphQL schema files** (`.graphql`, `.gql`): Extract all fields from `type Query`, `type Mutation`, and `type Subscription` blocks — each field's name, argument types, return type, and whether `@deprecated` is present.
   - **TypeScript type packages:** If the repo's `package.json` contains a `types` or `typings` field, this repo publishes a type package. Extract all exported `type` and `interface` names from the file(s) referenced by that field.

   If Contract Extraction is "disabled", skip this extraction entirely and omit the `provider_contracts` field from output. If no contract files are found, output `"provider_contracts": []`.

   **Contract file errors:** If a contract file is malformed or unparseable (invalid YAML/JSON, proto syntax errors, GraphQL syntax errors), log the parse error in `scan_metadata.errors` and skip that file. Do not fail the entire scan. If a contract file exceeds 5000 lines, extract only the first 500 endpoints/RPCs/fields and note the truncation in `scan_metadata.errors`.
   ```

4. **Add `provider_contracts` to the Required Output Format.** In the JSON schema block (starting around line 125), add `provider_contracts` as a new top-level field alongside `service`, `edges`, `unresolved`, `identity_signals`, and `scan_metadata`. Insert it after `identity_signals`:

   ```json
   "provider_contracts": [
     {
       "type": "OpenAPI",
       "file": "docs/openapi.yaml",
       "version": "2.1.0",
       "endpoints": [
         { "method": "POST", "path": "/api/v1/payments", "deprecated": false },
         { "method": "GET", "path": "/api/v1/payments/{id}", "deprecated": false },
         { "method": "GET", "path": "/api/v1/payments/legacy", "deprecated": true }
       ]
     },
     {
       "type": "Proto",
       "file": "proto/payments/v1/payments.proto",
       "package": "acme.payments.v1",
       "services": [
         {
           "name": "PaymentsService",
           "rpcs": [
             { "name": "CreatePayment", "input": "CreatePaymentRequest", "output": "CreatePaymentResponse", "deprecated": false },
             { "name": "GetPayment", "input": "GetPaymentRequest", "output": "PaymentResponse", "deprecated": false }
           ]
         }
       ]
     },
     {
       "type": "GraphQL",
       "file": "schema.graphql",
       "queries": [
         { "name": "payment", "args": ["id: ID!"], "return_type": "Payment", "deprecated": false }
       ],
       "mutations": [
         { "name": "createPayment", "args": ["input: CreatePaymentInput!"], "return_type": "Payment", "deprecated": false }
       ]
     },
     {
       "type": "TypeScript",
       "file": "dist/index.d.ts",
       "package_name": "@acme/shared-types",
       "exported_types": ["PaymentRequest", "PaymentResponse", "OrderStatus"]
     }
   ]
   ```

5. **Add a rule about provider_contracts.** In the **Rules** section (around line 174), add:

   ```markdown
   - When Contract Extraction is "enabled", the `provider_contracts` array must be present in the output (empty array if no contract files found). When "disabled", omit the field entirely.
   ```

**Commit:** `feat: extend tier 1 analyzer with provider contract extraction`

---

### Task 2: Extend Tier 2 Analyzer with Consumer Contract Extraction

Add consumer contract extraction to the existing Tier 2 analyzer prompt. This extends Step 2 ("Grep for Edge Patterns") to also capture what specific endpoints/RPCs the code calls, adds new GraphQL client patterns to the grep list, and adds a new `consumer_contracts` output field. A new `Contract Extraction` input field controls whether extraction runs.

- **Files:** `skills/pathfinder/tier2-analyzer-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Read `skills/pathfinder/tier2-analyzer-prompt.md` to confirm the current structure. Note: the entire prompt is wrapped inside a code fence (opening triple backtick at line 5, closing at the end). All insertions must go INSIDE this code fence.

2. **Add `Contract Extraction` input section.** After the existing `### Organizations` input section (around line 35 inside the code fence), add:

   ```markdown
   ### Contract Extraction

   [PASTE: "enabled" or "disabled" — when enabled, extract consumer contract details (specific endpoints, RPCs, operations called) from pattern matches. When absent or "disabled", skip consumer contract extraction.]
   ```

3. **Add GraphQL client patterns to Step 2.** In the "Grep for Edge Patterns" section (inside the code fence), after the existing gRPC patterns block (ending around line 82), add a new pattern group:

   ```markdown
   **GraphQL clients:**
   - `gql\`` (tagged template literals)
   - `useQuery(`, `useMutation(`, `useSubscription(` (React hooks — Apollo, urql)
   - `graphql(` (generic GraphQL client)
   - `graphql-request` (library import)
   - `ApolloClient`, `createClient` (client instantiation in GraphQL context)
   ```

4. **Add consumer contract extraction logic to Step 2.** After the existing pattern groups (HTTP, Kafka, gRPC, Redis, Elasticsearch, S3, and the new GraphQL) and before Step 3, add a new subsection:

   ```markdown
   **Consumer Contract Extraction (when Contract Extraction input is "enabled"):**

   For each pattern match found above, extract the specific contract element being consumed:

   - **HTTP client matches:** Extract the HTTP method and URL path from the match. Record as a consumed endpoint with `method`, `path`, `file`, and `line`. If the URL is dynamically constructed (template literals, string concatenation with variables), record `"path": "DYNAMIC"`.
   - **gRPC client matches:** Extract the service name and RPC method name from client instantiation patterns (e.g., `NewPaymentsServiceClient(` -> service: `PaymentsService`; `client.CreatePayment(` -> rpc: `CreatePayment`). Record as a consumed RPC with `service`, `rpc`, `file`, and `line`.
   - **GraphQL client matches:** Extract the operation name from the query/mutation string. For `useQuery`/`useMutation` hooks, parse the GraphQL string argument. For `gql` tagged templates, extract the operation name and type (query/mutation/subscription). Record with `type`, `name`, `file`, and `line`.
   - **Package version checks:** For imported contract packages (packages matching org-scoped patterns like `@org/shared-types`), record the version from the manifest.

   **Consumer contract type inference:** Assign `contract_type` based on the detection pattern:
   - HTTP call patterns (`fetch`, `axios`, `http.Get`, etc.) -> `"OpenAPI"`
   - gRPC patterns (`NewServiceClient`, `ServiceStub`) -> `"Proto"`
   - GraphQL patterns (`useQuery`, `gql`) -> `"GraphQL"`
   - Package import patterns -> `"TypeScript"`

   **Key constraint:** Only capture literal/static references. Dynamic route construction is logged with `"path": "DYNAMIC"`. Do not attempt to resolve runtime variables.

   Group consumed contract elements by target service. If no consumer contracts are detected, output `"consumer_contracts": []`.
   ```

5. **Add `consumer_contracts` to the Output Format.** In the JSON schema block (inside the code fence), add `consumer_contracts` as a new top-level field alongside `new_edges`, `upgraded_edges`, `unresolved`, and `scan_metadata`. Insert it after `unresolved`:

   ```json
   "consumer_contracts": [
     {
       "target": "acme/payments-api",
       "contract_type": "OpenAPI",
       "consumed_endpoints": [
         { "method": "POST", "path": "/api/v1/payments", "file": "src/checkout.ts", "line": 42 },
         { "method": "POST", "path": "/api/v1/payments/refund", "file": "src/returns.ts", "line": 87 }
       ]
     },
     {
       "target": "acme/auth-service",
       "contract_type": "Proto",
       "consumed_rpcs": [
         { "service": "AuthService", "rpc": "ValidateToken", "file": "src/middleware/auth.ts", "line": 15 }
       ]
     },
     {
       "target": "acme/gateway",
       "contract_type": "GraphQL",
       "consumed_operations": [
         { "type": "query", "name": "getPayment", "file": "src/queries/payments.ts", "line": 8 }
       ]
     }
   ]
   ```

6. **Add field documentation for `consumer_contracts`.** In the "Field definitions" section after the JSON schema, add:

   ```markdown
   - `consumer_contracts` — Contract elements consumed from target services.
     Only present when Contract Extraction is "enabled".
     - `target`: Qualified `org/repo` of the service being called
     - `contract_type`: One of `OpenAPI`, `Proto`, `GraphQL`, `TypeScript` —
       inferred from the detection pattern, used by synthesis to match against
       the correct provider contract format
     - `consumed_endpoints`: Array of HTTP endpoints called (for OpenAPI type)
     - `consumed_rpcs`: Array of gRPC RPCs called (for Proto type)
     - `consumed_operations`: Array of GraphQL operations called (for GraphQL type)
   ```

7. **Add rules about consumer_contracts.** In the **Rules** section, add:

   ```markdown
   - When Contract Extraction is "enabled", the `consumer_contracts` array must
     be present in the output (empty array if none detected). When "disabled"
     or absent, omit the field entirely.
   - Only capture literal/static references for consumer contracts. Dynamic paths
     get `"path": "DYNAMIC"` — do not attempt to resolve runtime variables.
   ```

**Commit:** `feat: extend tier 2 analyzer with consumer contract extraction`

---

### Task 3: Add Contract Verification Step to Synthesis Prompt

Add a new "Step 2.5: Contract Verification" to the synthesis prompt, between edge resolution (Step 2) and cluster detection (Step 3). This step cross-references provider contracts against consumer contracts for each edge, detects mismatches, adds contract-related fields to topology.json, and generates a new `contract-risks.md` output artifact.

- **Files:** `skills/pathfinder/synthesis-prompt.md` (1 file)
- **Complexity:** High
- **Dependencies:** Task 1, Task 2

**Steps:**

1. Read `skills/pathfinder/synthesis-prompt.md` to confirm the current structure. **Important:** The entire prompt content is wrapped inside a code fence (opening triple backtick at line 5, closing at the end). All insertions must go INSIDE this code fence.

2. **Add Contract Extraction input section.** After the existing `## Crawl Metadata (Crawl Mode Only)` input section (inside the code fence), add:

   ```markdown
   ## Contract Verification

   [PASTE: "enabled" or "disabled" — when "enabled", run contract verification (Step 2.5) and generate contract-risks.md. When "disabled" or absent, skip contract verification entirely. Contract verification requires Tier 2 data (consumer contracts). If tier_depth is 1, only provider contract inventory is available — add contracts to services but skip mismatch detection.]
   ```

3. **Insert Step 2.5: Contract Verification.** After the existing `### Step 2: Edge Resolution` section and before `### Step 3: Cluster Detection` (inside the code fence), add the entire new step:

   ```markdown
   ### Step 2.5: Contract Verification (when Contract Verification input is "enabled")

   Cross-reference provider and consumer contract data to detect mismatches.
   Skip this step entirely if Contract Verification is "disabled" or absent.

   #### Service Contract Inventory

   For each service in the inventory, collect its `provider_contracts` from the
   per-repo Tier 1 results. Add an optional `contracts` field to each service
   in topology.json:

   ```json
   {
     "name": "acme/payments-api",
     "type": "API",
     "contracts": [
       {
         "type": "OpenAPI",
         "file": "docs/openapi.yaml",
         "version": "2.1.0",
         "endpoint_count": 12,
         "deprecated_count": 1
       }
     ]
   }
   ```

   If a service has no provider contracts, set `"contracts": []`. This field
   is added even when tier_depth is 1 (provider inventory without mismatch
   detection).

   #### Edge Contract Matching (requires Tier 2 data)

   For each resolved edge in the topology:

   1. **Look up the provider** (target service) `provider_contracts` from its
      per-repo Tier 1 results.
   2. **Look up the consumer** (source service) `consumer_contracts` from its
      per-repo Tier 2 results.
   3. **Match by contract type** using this table:

      | Consumer `contract_type` | Match against provider | Comparison |
      |-------------------------|----------------------|------------|
      | `OpenAPI` | Provider's `type: "OpenAPI"` contract | Compare consumed HTTP paths against OpenAPI spec endpoints |
      | `Proto` | Provider's `type: "Proto"` contract | Compare consumed RPCs against proto service definitions |
      | `GraphQL` | Provider's `type: "GraphQL"` contract | Compare consumed operations against schema Query/Mutation fields |
      | `TypeScript` | Provider's `type: "TypeScript"` contract | Compare imported type names against exported types |

      If no matching provider contract exists for the consumer's contract type,
      set `contract_sync: "UNKNOWN"` with note "Provider has no [type] contract."

   4. **Add fields to each edge** in topology.json:
      - `contract_sync`: One of `"IN_SYNC"`, `"MISMATCH"`, `"UNKNOWN"`, `"NO_CONTRACT"`
        - `IN_SYNC` — provider contract exists, consumer expectations match
        - `MISMATCH` — one or more mismatches detected
        - `UNKNOWN` — no contract data on one/both sides, or consumer uses only dynamic paths
        - `NO_CONTRACT` — edge type has no parseable contract format (e.g., shared-infrastructure)
      - `consumed_contracts`: Persists the consumer-side contract data on the edge so query mode can find all consumers of a given endpoint without re-reading per-repo files. Copy from the Tier 2 `consumer_contracts` entry for this edge's source-target pair.

      Edge schema addition:
      ```json
      {
        "source": "acme/orders-api",
        "target": "acme/payments-api",
        "type": "HTTP",
        "contract_sync": "MISMATCH",
        "consumed_contracts": {
          "contract_type": "OpenAPI",
          "endpoints": [
            { "method": "POST", "path": "/api/v1/payments" },
            { "method": "POST", "path": "/api/v1/payments/refund" }
          ]
        }
      }
      ```

   #### Mismatch Detection

   For each matched contract pair, detect these four categories of mismatch:

   | Category | Severity | Detection |
   |----------|----------|-----------|
   | **Phantom endpoint/RPC** | HIGH | Consumer calls an endpoint/RPC not in the provider's contract definition |
   | **Deprecated usage** | MEDIUM | Consumer calls an endpoint/RPC marked `deprecated: true` in the provider's contract |
   | **Version skew** | MEDIUM | Consumer's imported package version doesn't match provider's published version. Annotate "may be benign — check changelog" |
   | **Schema drift (typed only)** | MEDIUM | Consumer's generated types (`.d.ts`, `.pb.ts`) reference fields absent from provider's current schema. Only for repos with generated type definitions. |

   **Skip (too noisy):** Schema drift for untyped consumers (JavaScript/Python
   without type definitions), breaking change inference without schema diffing,
   dynamic route inference.

   Record each mismatch in a top-level `contract_mismatches` array in topology.json:

   ```json
   {
     "contract_mismatches": [
       {
         "edge": { "source": "acme/orders-api", "target": "acme/payments-api", "type": "HTTP" },
         "category": "phantom_endpoint",
         "severity": "HIGH",
         "detail": "Consumer calls POST /api/v1/payments/refund — endpoint not in provider's OpenAPI spec",
         "provider": { "file": "docs/openapi.yaml", "version": "2.1.0" },
         "consumer": { "file": "src/returns.ts", "line": 87 }
       },
       {
         "edge": { "source": "acme/orders-api", "target": "acme/payments-api", "type": "HTTP" },
         "category": "deprecated_usage",
         "severity": "MEDIUM",
         "detail": "Consumer calls GET /api/v1/payments/legacy — endpoint marked deprecated in provider's OpenAPI spec",
         "provider": { "file": "docs/openapi.yaml" },
         "consumer": { "file": "src/legacy-compat.ts", "line": 23 }
       }
     ]
   }
   ```

   #### Graceful Degradation

   - No contract files found -> `contracts: []`, edge gets `contract_sync: "NO_CONTRACT"`
   - Contract file malformed/unparseable -> error already logged by Tier 1, `contract_sync: "UNKNOWN"`
   - Consumer is untyped -> skip schema drift, still check phantom endpoints via URL matching
   - Only one side of edge has contract data -> partial analysis, note which side is missing, `contract_sync: "UNKNOWN"`
   - Dynamic consumer paths (`"path": "DYNAMIC"`) -> `contract_sync: "UNKNOWN"` with evidence logged
   - Edge type has no contract format (shared-infra, shared-package) -> `contract_sync: "NO_CONTRACT"`
   ```

4. **Add `contract-risks.md` to Step 5 output artifacts.** In the "Generate Output Artifacts" section (Step 5), after the existing `scan-log.json` artifact description and before the Rules section, add a new artifact:

   ```markdown
   #### File: `contract-risks.md` — Contract Verification Report (when Contract Verification is "enabled")

   Generate this file only when contract verification was enabled and at least
   one edge has contract data. Include these sections:

   - **Risk Summary** — Total mismatches by category and severity. Example:
     "2 HIGH (phantom endpoints), 3 MEDIUM (1 deprecated usage, 1 version skew, 1 schema drift)"

   - **Ranked Mismatch List** — Every mismatch ordered by severity: phantom
     endpoints (HIGH) first, then within MEDIUM: schema drift, version skew,
     deprecated usage. Each entry includes the edge (source -> target), category,
     detail, provider file, and consumer file/line.

   - **Per-Edge Contract Status Table** — Every edge with its `contract_sync`
     status. Columns: Source, Target, Edge Type, Contract Sync, Detail.

   - **Contract Inventory** — Which services have contracts (by type), which
     don't. Example: "28 services have OpenAPI specs, 10 have Proto definitions,
     4 have GraphQL schemas. 15 services have no parseable contracts."

   - **Recommendations** — Actionable suggestions. Examples:
     - "Add OpenAPI spec to acme/orders-worker (no contract found, 3 consumers detected)"
     - "Update acme/checkout-service to stop calling deprecated GET /api/v1/payments/legacy"
     - "Investigate phantom endpoint POST /api/v1/payments/refund called by acme/orders-api"
   ```

5. **Update the topology.json schema in Step 5.** In the existing topology.json schema block, add:

   - An optional `contracts` field to the service object example (after `"metadata"`):
     ```json
     "contracts": [
       {
         "type": "OpenAPI",
         "file": "docs/openapi.yaml",
         "version": "2.1.0",
         "endpoint_count": 12,
         "deprecated_count": 1
       }
     ]
     ```

   - Optional `contract_sync` and `consumed_contracts` fields to the edge object example (after `"evidence"`):
     ```json
     "contract_sync": "IN_SYNC",
     "consumed_contracts": {
       "contract_type": "OpenAPI",
       "endpoints": [
         { "method": "POST", "path": "/api/v1/payments" }
       ]
     }
     ```

   - A new top-level `contract_mismatches` array after the `clusters` array:
     ```json
     "contract_mismatches": []
     ```

6. **Update context self-monitoring priority.** In the "Context Self-Monitoring" section at the end, update the artifact priority order to include contract-risks.md:

   Change:
   ```
   1. `topology.json` first (source of truth — most critical)
   2. `report.md` second (human-readable findings)
   3. Mermaid diagrams last (visual aids)
   ```
   To:
   ```
   1. `topology.json` first (source of truth — most critical)
   2. `report.md` second (human-readable findings)
   3. `contract-risks.md` third (contract verification findings)
   4. Mermaid diagrams last (visual aids)
   ```

**Commit:** `feat: add contract verification step to synthesis prompt`

---

### Task 4: Add Contract-Aware Query Types to Query Handler

Add two new query types (`consumers` and `safe-to-change`) to the query handler prompt. These operate on the persisted `consumed_contracts` and `contract_mismatches` data in topology.json, requiring no re-scanning.

- **Files:** `skills/pathfinder/query-handler-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** Task 3

**Steps:**

1. Read `skills/pathfinder/query-handler-prompt.md` to confirm the current structure. Note: the entire prompt is wrapped inside a code fence (opening triple backtick at line 5, closing at the end). All insertions must go INSIDE this code fence.

2. **Update the Query input section.** Change the comment listing the valid query types from:

   ```
   [PASTE: Query type -- one of: upstream, downstream, blast-radius,
   shared-infra, path]
   ```

   to:

   ```
   [PASTE: Query type -- one of: upstream, downstream, blast-radius,
   shared-infra, path, consumers, safe-to-change]
   ```

3. **Add the two new query type sections.** After the existing `### 5. path <service-A> <service-B>` section and before the `## Rules` section (inside the code fence), add:

   ```markdown
   ### 6. consumers <provider> <endpoint|rpc>

   Find all services that consume a specific contract element (endpoint, RPC,
   or GraphQL operation) from a provider service. Operates on the persisted
   `consumed_contracts` field on edges and the `contract_mismatches` array in
   topology.json — no re-scanning needed.

   - Walk the edges array and collect every edge where `target` matches the
     provider service AND `consumed_contracts` is present.
   - For each matching edge, check the `consumed_contracts` field:
     - For `contract_type: "OpenAPI"`: search `endpoints` array for a match
       on both `method` and `path` against the queried endpoint.
     - For `contract_type: "Proto"`: search `consumed_rpcs` array for a match
       on `service` and `rpc` against the queried RPC.
     - For `contract_type: "GraphQL"`: search `consumed_operations` array for
       a match on `name` against the queried operation.
   - For each matching consumer, also check the `contract_mismatches` array
     for any mismatches on that edge related to the queried element.
   - Return for each consumer:
     - Service name (qualified `org/repo`)
     - File and line evidence from `consumed_contracts`
     - Current `contract_sync` status for the edge
     - Any mismatches specific to the queried endpoint/RPC
     - Whether the endpoint is marked deprecated in the provider's contract
       (check the provider service's `contracts` field)
   - If no consumers are found, return: "No consumers found for [endpoint]
     on [provider]. This endpoint may be unused or consumers may not have
     been scanned."

   ### 7. safe-to-change <provider> <endpoint|rpc>

   Compute the blast radius of modifying or removing a specific contract
   element. Combines `consumers` lookup with transitive downstream BFS.

   1. **Find all direct consumers** of the endpoint/RPC using the same
      traversal as the `consumers` query above.
   2. **For each direct consumer**, run transitive downstream BFS — same
      algorithm as the existing `blast-radius` query (follow edges where the
      consumer is the `target`, using a visited set for cycle detection).
   3. **Compute severity:**
      - 0 direct consumers = "Safe to change — no consumers detected"
      - 1-2 direct consumers = MEDIUM risk
      - 3+ direct consumers = HIGH risk
   4. **Return:**
      - Direct consumer count and list (with file/line evidence)
      - Transitive downstream service count
      - Severity assessment with rationale
      - Whether the endpoint is already marked deprecated
      - Recommendation: if deprecated and 0 consumers, "Safe to remove."
        If not deprecated and has consumers, "Mark as deprecated first,
        then coordinate with N consuming teams."

   **Cycle detection is mandatory** for the transitive BFS portion. Use
   a visited set. Report cycles explicitly.

   Example output format:
   > "POST /api/v1/payments on acme/payments-api:
   > - 4 direct consumers: orders-api, checkout-service, billing-worker, admin-portal
   > - 23 transitive downstream services affected
   > - Severity: HIGH — removing this endpoint would break 4 services
   > - Recommendation: Mark as deprecated first, then coordinate with 4 consuming teams."
   ```

4. **Update the Output Format section.** In the output format description, the existing table has a `Hop Distance` column. For `consumers` and `safe-to-change` queries, the table should also work. Add a note after the existing output format:

   ```markdown
   **For `consumers` and `safe-to-change` queries**, use this adapted structure:

   ### Results

   [For `consumers`: list of consuming services with evidence.
    For `safe-to-change`: direct consumers + transitive impact + severity.]

   ### Details

   | Service | Contract Type | Endpoint/RPC | File | Line | Contract Sync |
   |---------|--------------|--------------|------|------|---------------|
   | org/repo-name | OpenAPI | POST /api/v1/payments | src/checkout.ts | 42 | IN_SYNC |

   ### Blast Radius (safe-to-change only)

   | Metric | Value |
   |--------|-------|
   | Direct consumers | N |
   | Transitive downstream | N |
   | Severity | HIGH/MEDIUM/LOW |

   ### Warnings
   [Any of: endpoint is deprecated, contract_sync is UNKNOWN for some consumers,
   stale services in the consumer list, cycles detected in transitive BFS]
   ```

5. **Update the Rules section.** Add:

   ```markdown
   - For `consumers` and `safe-to-change` queries, if the topology.json has no
     `consumed_contracts` data on edges (contract verification was never run),
     return: "No contract data available. Run pathfinder with contract
     verification enabled (Tier 2 + contract verification option) to populate
     contract data."
   ```

**Commit:** `feat: add consumers and safe-to-change query types to query handler`

---

### Task 5: Update SKILL.md with Contract Verification Documentation

Update SKILL.md to document the contract verification feature: expanded Tier 1 checkpoint options, contract verification flow, new query types, error handling, and guardrails. This is a series of surgical updates to existing sections.

- **Files:** `skills/pathfinder/SKILL.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** Task 1, Task 2, Task 3, Task 4

**Steps:**

1. Read `skills/pathfinder/SKILL.md` to confirm the current structure after any prior changes.

2. **Update the Tier 1 Checkpoint section** (currently around line 188-200). Replace the existing user options block with the expanded version that includes contract information. The checkpoint summary should mention contract counts:

   Change the checkpoint message from:
   ```
   > "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Here's the overview. Would you like me to run a deep code scan for additional edges?"
   ```
   to:
   ```
   > "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). 42 services have parseable contracts (28 OpenAPI, 10 Proto, 4 GraphQL). Here's the overview."
   ```

   Replace the existing user options:
   ```
   **User options:**
   - **Proceed to Tier 2** -- deep code scan for additional edges
   - **Skip to synthesis** -- generate topology from Tier 1 findings only
   - **Abort** -- stop without generating output
   ```
   with:
   ```
   **User options:**
   1. **Proceed to synthesis** -- topology with provider contract inventory (already extracted), but no consumer-side verification
   2. **Run Tier 2 deep scan** -- discover additional edges from source code, no contract verification
   3. **Run Tier 2 + contract verification** -- deep scan AND cross-reference provider/consumer contracts
   4. **Abort** -- stop without generating output

   Provider contracts from Tier 1 are always extracted when contract files are found (zero extra cost — Tier 1 already reads these files). Options 1 and 2 include provider contract data in topology.json but do not run consumer-side matching or mismatch detection. Consumer verification requires Tier 2 (option 3).
   ```

3. **Add contract error handling rows.** In the Error Handling table, add these rows:

   | Error | Response |
   |-------|----------|
   | OpenAPI spec has invalid YAML/JSON | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
   | Proto file has syntax errors | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
   | GraphQL schema has syntax errors | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
   | Contract file too large (>5000 lines) | Extract first 500 endpoints/RPCs, note truncation |
   | Consumer calls >100 endpoints on single provider | Retain all, but note in scan log |

4. **Add contract query types to the Query Mode section.** In the Query Types table (around line 447-453), add two new rows:

   | Query | Description | Example |
   |-------|-------------|---------|
   | `consumers <provider> <endpoint\|rpc>` | List all services consuming a specific contract element | "Who calls POST /api/v1/payments on payments-api?" |
   | `safe-to-change <provider> <endpoint\|rpc>` | Compute blast radius of modifying/removing a contract element | "Is it safe to remove GET /api/v1/payments/legacy?" |

5. **Add contract output artifacts documentation.** After the existing output artifact descriptions in the Phase 3 Synthesis section (around line 241, after the `scan-log.json` bullet), add:

   ```markdown
   6. **`contract-risks.md`** -- Contract verification report: risk summary, ranked mismatch list, per-edge contract status table, contract inventory, and recommendations. Only generated when contract verification is enabled (Tier 2 + contract verification option).
   ```

6. **Add contract guardrails.** In the Guardrails section under "The orchestrator must NOT", add:

   ```markdown
   - Run contract verification without explicit user opt-in (option 3 at Tier 1 checkpoint)
   - Set Contract Extraction to "enabled" in Tier 2 prompts unless the user selected option 3
   ```

7. **Add contract red flags.** In the Red Flags section, add:

   ```markdown
   - Running contract mismatch detection without Tier 2 data (consumer contracts require Tier 2)
   - Silently dropping phantom endpoint or deprecated usage mismatches instead of reporting them
   - Reporting schema drift for untyped consumers (too noisy — skip these)
   ```

**Commit:** `feat: update SKILL.md with contract verification documentation`

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: Tier 1 analyzer provider contract extraction (1 modified file)
- Task 2: Tier 2 analyzer consumer contract extraction (1 modified file)

**Wave 2 (depends on Wave 1):**
- Task 3: Synthesis prompt contract verification step (1 modified file — references output schemas from Tasks 1 and 2)

**Wave 3 (depends on Wave 2):**
- Task 4: Query handler contract-aware query types (1 modified file — references topology schema from Task 3)
- Task 5: SKILL.md contract verification documentation (1 modified file — references all templates from Tasks 1-4)

---

## Verification Checklist

After all tasks complete, verify:

1. **tier1-analyzer-prompt.md:**
   - [ ] `Contract Extraction` input section present
   - [ ] GraphQL files (`*.graphql`, `schema.graphql`, `schema.gql`) added to Step 3 scan list
   - [ ] Provider contract extraction instructions cover all 4 formats (OpenAPI, Proto, GraphQL, TypeScript types)
   - [ ] `provider_contracts` field in output JSON schema with examples for all 4 types
   - [ ] Contract file error handling (malformed, >5000 lines) documented
   - [ ] Rule about `provider_contracts` presence when enabled vs disabled

2. **tier2-analyzer-prompt.md:**
   - [ ] `Contract Extraction` input section present
   - [ ] GraphQL client patterns added to Step 2 grep list (`gql`, `useQuery`, `useMutation`, `useSubscription`, `graphql(`, `graphql-request`, `ApolloClient`, `createClient`)
   - [ ] Consumer contract extraction logic for HTTP, gRPC, GraphQL, and package version
   - [ ] Contract type inference rules documented (HTTP->OpenAPI, gRPC->Proto, GraphQL->GraphQL, package->TypeScript)
   - [ ] `consumer_contracts` field in output JSON schema with examples for all 3 types (OpenAPI, Proto, GraphQL)
   - [ ] `"path": "DYNAMIC"` for dynamically constructed URLs documented
   - [ ] Field definitions for `consumer_contracts` documented

3. **synthesis-prompt.md:**
   - [ ] `Contract Verification` input section present
   - [ ] Step 2.5 inserted between Step 2 (Edge Resolution) and Step 3 (Cluster Detection)
   - [ ] Service contract inventory logic (`contracts` field on services)
   - [ ] Edge-to-contract matching table (4 contract types)
   - [ ] `contract_sync` and `consumed_contracts` fields on edges documented
   - [ ] Mismatch detection for all 4 categories (phantom, deprecated, version skew, schema drift)
   - [ ] `contract_mismatches` top-level array schema with examples
   - [ ] Graceful degradation rules (no contracts, malformed, untyped, dynamic paths, one-sided)
   - [ ] `contract-risks.md` artifact with 5 sections (risk summary, ranked list, status table, inventory, recommendations)
   - [ ] topology.json schema updated with `contracts`, `contract_sync`, `consumed_contracts`, `contract_mismatches`
   - [ ] Context self-monitoring priority includes `contract-risks.md`

4. **query-handler-prompt.md:**
   - [ ] Query type list updated to include `consumers` and `safe-to-change`
   - [ ] `consumers` query logic: traverse edges, check `consumed_contracts`, check `contract_mismatches`, return evidence
   - [ ] `safe-to-change` query logic: consumers lookup + transitive BFS + severity derivation (1-2=MEDIUM, 3+=HIGH)
   - [ ] Output format adapted for contract queries (contract-specific table columns, blast radius table)
   - [ ] Rule about missing contract data (contract verification never run)
   - [ ] Cycle detection mandatory for `safe-to-change` transitive BFS

5. **SKILL.md:**
   - [ ] Tier 1 checkpoint expanded to 4 options (synthesis, Tier 2, Tier 2+contracts, abort)
   - [ ] Checkpoint message includes contract counts (N services have parseable contracts)
   - [ ] Provider contracts described as zero-extra-cost (Tier 1 already reads these files)
   - [ ] Consumer verification requires Tier 2 (option 3)
   - [ ] `consumers` and `safe-to-change` in Query Types table
   - [ ] `contract-risks.md` in output artifact list
   - [ ] Contract error handling rows in Error Handling table (5 new rows)
   - [ ] Contract guardrails (no verification without opt-in, no Tier 2 contract extraction without option 3)
   - [ ] Contract red flags (no mismatch detection without Tier 2, no silent dropping, no schema drift for untyped)
