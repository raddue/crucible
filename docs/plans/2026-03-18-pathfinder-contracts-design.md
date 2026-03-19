# Pathfinder Contract Surface Extraction & Cross-Repo Sync Verification

**Date:** 2026-03-18
**Status:** Design approved, quality-gated
**Branch:** worktree-pathfinder-contracts
**Issue:** #41

## Overview

Extends the existing pathfinder analysis pipeline to extract API contracts on both sides of every discovered edge and detect mismatches — phantom endpoints, deprecated usage, version skew, and typed schema drift.

**Not a new mode.** This is an opt-in enhancement to the existing full-scan and crawl pipelines. At the Tier 1 checkpoint, the user chooses whether to enable contract verification alongside Tier 2 deep scanning.

**How it works:**
1. **Tier 1** gains a `provider_contracts` output — extracts endpoints, RPCs, types from proto/OpenAPI/GraphQL/TypeScript files it already scans
2. **Tier 2** gains a `consumer_contracts` output — extracts which endpoints/RPCs the code actually calls, from patterns it already greps for
3. **Synthesis** gains a **Contract Verification** step — cross-references provider vs consumer contracts per edge, flags mismatches, produces `contract-risks.md`
4. **Query mode** gains contract-aware queries — `consumers` and `safe-to-change` queries against the persisted contract data

**Invocation** (unchanged — contract verification is a pipeline option, not a new mode):
```
crucible:pathfinder <org>                  # at Tier 1 checkpoint, user opts into contracts
crucible:pathfinder crawl <org>/<repo>     # same — opt-in at checkpoint
```

## Contract Formats Supported

| Format | Provider Signal | Consumer Signal |
|--------|----------------|-----------------|
| **Protobuf** | `service`/`rpc` declarations in `.proto` files | Generated stubs, `NewServiceClient(` calls |
| **OpenAPI/Swagger** | `openapi.yaml` / `swagger.json` | HTTP calls to matching paths |
| **GraphQL** | `schema.graphql`, `type Query/Mutation` | GraphQL client library calls (`useQuery`, `gql`, `graphql-request`) |
| **TypeScript types** | Published `@org/shared-types` package | `import` from that package |

Database migrations / shared-DB contracts are deferred to a future enhancement.

## Tier 1 Extension — Provider Contract Extraction

Tier 1 already scans proto files and OpenAPI specs in Step 3 ("Proto and API Definitions"). The extension adds contract surface extraction from files it already opens.

### Prompt Changes to `tier1-analyzer-prompt.md`

**Step 3 ("Proto and API Definitions")** gains additional instructions after the existing proto/OpenAPI scanning:

1. Add `*.graphql`, `schema.graphql`, `schema.gql` to the scan list
2. After extracting proto imports (existing behavior), also extract the full service surface: service names, all RPC methods with input/output message types, and the `[deprecated = true]` option on each
3. After extracting API endpoint definitions (existing behavior), also parse the full OpenAPI spec: all paths with methods, deprecated flags, and the `info.version` field
4. For GraphQL files: extract all `type Query`, `type Mutation`, `type Subscription` fields with their argument and return types, and `@deprecated` directives
5. For TypeScript type packages (detected via `package.json` `types` or `typings` field): extract exported type and interface names

**New output field** added to the Required Output Format JSON schema: `provider_contracts`

```json
{
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
    }
  ]
}
```

**No contract files found** → `provider_contracts: []` — graceful, no error.

**Rule added to Rules section:** "If contract verification is not enabled (orchestrator passes `contracts_enabled: false`), skip provider contract extraction entirely — do not add the `provider_contracts` field."

## Tier 2 Extension — Consumer Contract Extraction

Tier 2 already greps for HTTP calls, gRPC channels, and message queue patterns. The extension captures *what specifically* the consumer is calling.

### Prompt Changes to `tier2-analyzer-prompt.md`

**Step 2 ("Grep for Edge Patterns")** gains additional extraction logic and new GraphQL patterns:

1. **For existing HTTP matches:** In addition to detecting the edge, also extract the HTTP method and URL path from the match. Record as a consumed endpoint with method, path, file, and line.
2. **For existing gRPC matches:** In addition to detecting the edge, also extract the service name and RPC method from client instantiation patterns. Record as a consumed RPC.
3. **New GraphQL client patterns** added to grep list:
   - `gql\`` (tagged template literals)
   - `useQuery(`, `useMutation(`, `useSubscription(` (React hooks — Apollo, urql)
   - `graphql(` (generic GraphQL client)
   - `graphql-request` (library import)
   - `ApolloClient`, `createClient` (client instantiation in GraphQL context)
   For each match, extract the query/mutation name and fields from the GraphQL string if parseable.
4. **For existing package version checks:** Record the version of imported contract packages from manifests.

**New output field** added to the Output Format JSON schema: `consumer_contracts`

```json
{
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
}
```

**Consumer contract type inference:** The `contract_type` field is inferred from the detection pattern:
- HTTP call patterns (`fetch`, `axios`, etc.) → `"OpenAPI"`
- gRPC patterns (`NewServiceClient`, `ServiceStub`) → `"Proto"`
- GraphQL patterns (`useQuery`, `gql`) → `"GraphQL"`
- Package import patterns → `"TypeScript"`

This enables synthesis to match consumer contracts against the correct provider contract format (see Edge-to-Contract Matching below).

**Key constraint:** Only literal/static references are captured. Dynamic route construction is logged as a consumed endpoint with `"path": "DYNAMIC"` — synthesis marks these as `contract_sync: "UNKNOWN"` rather than producing false mismatches.

**No consumer contracts detected** → `consumer_contracts: []` — graceful, no error.

**Rule added:** "If contract verification is not enabled (orchestrator passes `contracts_enabled: false`), skip consumer contract extraction entirely."

## Synthesis Extension — Contract Verification

After edge resolution (Step 2) and before cluster detection (Step 3), synthesis gains a new **Contract Verification** step.

### Prompt Changes to `synthesis-prompt.md`

Add a new **Step 2.5: Contract Verification** between edge resolution and cluster detection.

### Process

For each edge in the resolved topology:
1. Look up the **provider** (target) service's `provider_contracts` from per-repo results
2. Look up the **consumer** (source) service's `consumer_contracts` from per-repo results
3. **Match by contract type** using the edge-to-contract matching rules (see below)
4. For each matched contract pair, run mismatch detection

### Edge-to-Contract Matching

A provider may have multiple contract formats (e.g., OpenAPI AND proto). The consumer's `contract_type` field determines which provider contract to match against:

| Consumer `contract_type` | Match against provider | Rule |
|-------------------------|----------------------|------|
| `OpenAPI` | Provider's `type: "OpenAPI"` contract | Compare consumed HTTP paths against OpenAPI spec endpoints |
| `Proto` | Provider's `type: "Proto"` contract | Compare consumed RPCs against proto service definitions |
| `GraphQL` | Provider's `type: "GraphQL"` contract | Compare consumed operations against schema Query/Mutation fields |
| `TypeScript` | Provider's `type: "TypeScript"` contract | Compare imported type names against exported types |

If no matching provider contract exists for the consumer's contract type, set `contract_sync: "UNKNOWN"` with note "Provider has no [type] contract."

### Mismatch Detection

Four categories, with consistent severity:

| Category | Severity | Detection Method |
|----------|----------|------------------|
| **Phantom endpoint/RPC** | HIGH | Consumer calls endpoint/RPC not in provider's contract definition |
| **Deprecated usage** | MEDIUM | Consumer calls endpoint/RPC marked `deprecated: true` in provider's contract |
| **Version skew** | MEDIUM | Consumer's imported package version doesn't match provider's published version. Annotated "may be benign — check changelog" |
| **Schema drift (typed only)** | MEDIUM | Consumer's generated types (`.d.ts`, `.pb.ts`) reference fields absent from provider's current schema. Only for repos with generated type definitions. |

**Skipped (too noisy):**
- Schema drift for untyped consumers (JavaScript/Python without type definitions)
- Breaking change inference without schema diffing
- Dynamic route inference

### Sync Status

Each edge gains a `contract_sync` field:
- `IN_SYNC` — provider contract exists, consumer expectations match
- `MISMATCH` — one or more mismatches detected (detail in `contract_mismatches`)
- `UNKNOWN` — no contract data available on one or both sides, or consumer uses only dynamic paths
- `NO_CONTRACT` — edge type doesn't have a parseable contract format (e.g., shared-infrastructure edges)

## Provider vs Consumer Identification

- **Provider** = repo that owns the contract file (proto service declarations, OpenAPI spec, GraphQL schema, published type package)
- **Consumer** = repo on the other side of the edge (imports proto, makes HTTP calls, depends on type package)
- **Monorepo internals** = mark as `shared-package` / `bidirectional` — intra-repo contract verification deferred
- **Bidirectional services** (A calls B, B calls A back) = each repo is provider AND consumer on different edges — handled naturally since contracts are per-edge

Edge direction already tells us which side is which. Tier 1 extracts what a repo *exposes*. Tier 2 extracts what a repo *calls*. Synthesis matches them by edge identity.

## Contract-Aware Query Mode

Extends query mode with two new query types that operate on persisted contract data in `topology.json`. No re-scanning needed.

### New Query Types

| Query | Description | Example |
|-------|-------------|---------|
| `consumers <provider> <endpoint\|rpc>` | List all services consuming a specific contract element | "Who calls POST /api/v1/payments on payments-api?" |
| `safe-to-change <provider> <endpoint\|rpc>` | Compute blast radius of modifying/removing a contract element | "Is it safe to remove GET /api/v1/payments/legacy?" |

### `consumers` Query

Traverses `contract_mismatches` and per-service `consumer_contracts` to find every service that calls the specified endpoint/RPC. Returns:
- List of consuming services with file/line evidence
- Current `contract_sync` status for each consumer's edge
- Whether the endpoint is marked deprecated

### `safe-to-change` Query

Combines `consumers` with blast-radius BFS:
1. Find all direct consumers of the endpoint/RPC
2. For each consumer, run transitive downstream BFS (same as existing blast-radius query)
3. Return: direct consumer count, transitive impact count, severity assessment

Example output:
> "POST /api/v1/payments on acme/payments-api:
> - 4 direct consumers: orders-api, checkout-service, billing-worker, admin-portal
> - 23 transitive downstream services affected
> - Severity: HIGH — removing this endpoint would break 4 services"

### Prompt Changes to `query-handler-prompt.md`

Add the two new query types to the query handler's routing logic. The handler receives `topology.json` which already contains `contracts` on services and `contract_mismatches` at the top level — no additional data needed.

## Output Artifacts

### topology.json — Contract Additions

**Services gain optional `contracts` field:**
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

**Edges gain optional `contract_sync` field:**
```json
{
  "source": "acme/orders-api",
  "target": "acme/payments-api",
  "type": "HTTP",
  "contract_sync": "MISMATCH"
}
```

**New top-level `contract_mismatches` array:**
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

### contract-risks.md — Human-Readable Report

New output artifact alongside existing `report.md`:
- **Risk summary** — total mismatches by category and severity
- **Ranked mismatch list** — ordered by severity: phantom endpoints (HIGH) first, then version skew and deprecated usage (MEDIUM), then schema drift (MEDIUM)
- **Per-edge contract status table** — every edge with `contract_sync` status
- **Contract inventory** — which services have contracts, which don't
- **Recommendations** — "Add OpenAPI spec to acme/orders-worker (no contract found)"

### Severity Ranking (Canonical)

| Severity | Category | Rationale |
|----------|----------|-----------|
| HIGH | Phantom endpoint/RPC | Consumer calls something that doesn't exist — will fail at runtime |
| MEDIUM | Version skew | May be benign but warrants investigation |
| MEDIUM | Deprecated usage | Works today, may break tomorrow |
| MEDIUM | Schema drift (typed, missing field) | Consumer expects data provider may not send |

Within the same severity level, report ordering is: phantom > schema drift > version skew > deprecated.

## User Interaction — Opt-In at Checkpoint

At the existing Tier 1 checkpoint, the options expand:

> "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). 42 services have parseable contracts (28 OpenAPI, 10 Proto, 4 GraphQL).
>
> Options:
> 1. **Proceed to synthesis** — topology only, no contract verification
> 2. **Run Tier 2 deep scan** — discover additional edges from source code
> 3. **Run Tier 2 + contract verification** — deep scan AND cross-reference contracts"

Contract verification requires Tier 2 data for consumer-side extraction, so it is only available alongside Tier 2 (option 3). Provider contracts from Tier 1 are always extracted when contract files are found (zero extra cost — Tier 1 already reads these files), but consumer matching and mismatch detection require Tier 2.

## Crawl Mode Compatibility

Contract verification works transparently with crawl mode:
- Provider contracts extracted during Tier 1 analysis at each crawl depth
- Consumer contracts extracted if Tier 2 is opted into after crawl completes
- Synthesis cross-references contracts same as full scan
- Crawl metadata (importance, depth) preserved alongside contract data

## Graceful Degradation

- No contract files found → `contracts: []`, edge gets `contract_sync: "NO_CONTRACT"`
- Contract file malformed/unparseable → log error in scan-log.json, skip, `contract_sync: "UNKNOWN"`
- Consumer is untyped → skip schema drift, still check phantom endpoints via URL matching
- Only one side of edge has contract data → partial analysis, note which side is missing
- Dynamic consumer paths → `contract_sync: "UNKNOWN"` with evidence logged
- Edge type has no contract format (shared-infra) → `contract_sync: "NO_CONTRACT"`

## Error Handling (Additions)

| Error | Response |
|-------|----------|
| OpenAPI spec has invalid YAML/JSON | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
| Proto file has syntax errors | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
| GraphQL schema has syntax errors | Log parse error, skip contract, `contract_sync: "UNKNOWN"` |
| Contract file too large (>5000 lines) | Extract first 500 endpoints/RPCs, note truncation |
| Consumer calls >100 endpoints on single provider | Retain all, but note in scan log |

## Acceptance Criteria

(Numbered 41-56, continuing from diff mode's 23-40)

41. Given a repo with an OpenAPI spec, Tier 1 extracts all endpoints with methods and deprecated flags into `provider_contracts`
42. Given a repo with proto service definitions, Tier 1 extracts all RPCs with input/output types and deprecated options
43. Given a repo with GraphQL schema, Tier 1 extracts Query/Mutation fields with deprecated directives
44. Given consumer code with literal HTTP calls to a known service, Tier 2 extracts the method and path into `consumer_contracts`
45. Given consumer code with gRPC client calls, Tier 2 extracts service name and RPC method
46. Given consumer code with GraphQL client calls (useQuery, gql, graphql-request), Tier 2 extracts operation names into `consumer_contracts`
47. Given a provider's OpenAPI spec and a consumer calling an endpoint not in the spec, synthesis flags a phantom endpoint mismatch with severity HIGH
48. Given a provider with deprecated endpoints and a consumer calling them, synthesis flags deprecated usage with severity MEDIUM
49. Given mismatched package versions between provider and consumer manifests, synthesis flags version skew with severity MEDIUM and "may be benign" annotation
50. Given no contract files in a repo, `provider_contracts` is empty and edge `contract_sync` is "NO_CONTRACT" — no errors
51. Given a malformed contract file, the error is logged and `contract_sync` is "UNKNOWN" — scan continues
52. `contract-risks.md` ranks mismatches by severity (HIGH first, then MEDIUM by category order: phantom > schema drift > version skew > deprecated)
53. Contract verification is opt-in at the Tier 1 checkpoint — never runs without user consent
54. Query mode `consumers <provider> <endpoint>` returns all services consuming the specified endpoint with evidence
55. Query mode `safe-to-change <provider> <endpoint>` returns consumer count + transitive blast radius
56. A provider with both OpenAPI and Proto contracts matches consumer contracts by the consumer's `contract_type` field, not by edge type alone

## Future Enhancements

- **Shared-DB contract verification:** Migration files as provider contracts, query patterns as consumer contracts
- **Schema diffing across versions:** Clone two versions of a provider, diff the contract surface, detect breaking changes
- **Contract coverage score:** What percentage of edges have verifiable contracts on both sides
- **Integration with diff mode:** Track contract changes over time — "this endpoint was added last week and already has 3 consumers"
