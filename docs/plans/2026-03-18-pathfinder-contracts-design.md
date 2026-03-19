# Pathfinder Contract Surface Extraction & Cross-Repo Sync Verification

**Date:** 2026-03-18
**Status:** Design approved
**Branch:** worktree-pathfinder-contracts
**Issue:** #41

## Overview

Extends the existing pathfinder analysis pipeline to extract API contracts on both sides of every discovered edge and detect mismatches — phantom endpoints, deprecated usage, version skew, and typed schema drift.

**Not a new mode.** This is an opt-in enhancement to the existing full-scan and crawl pipelines. At the Tier 1 checkpoint, the user chooses whether to enable contract verification alongside or instead of Tier 2 deep scanning.

**How it works:**
1. **Tier 1** gains a `provider_contracts` output — extracts endpoints, RPCs, types from proto/OpenAPI/GraphQL/TypeScript files it already scans
2. **Tier 2** gains a `consumer_contracts` output — extracts which endpoints/RPCs the code actually calls, from patterns it already greps for
3. **Synthesis** gains a **Contract Verification** step — cross-references provider vs consumer contracts per edge, flags mismatches, produces `contract-risks.md`

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
| **GraphQL** | `schema.graphql`, `type Query/Mutation` | GraphQL client calls (HTTP-based) |
| **TypeScript types** | Published `@org/shared-types` package | `import` from that package |

Database migrations / shared-DB contracts are deferred to a future enhancement.

## Tier 1 Extension — Provider Contract Extraction

Tier 1 already scans proto files and OpenAPI specs in Step 3 ("Proto and API Definitions"). The extension adds contract surface extraction from files it already opens.

**New output field** in per-repo JSON: `provider_contracts`

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
    }
  ]
}
```

**What Tier 1 extracts per format:**
- **OpenAPI/Swagger:** All paths with methods, deprecated flag, version from `info.version`
- **Protobuf:** Service names, RPC methods with input/output message types, deprecated options, package version
- **GraphQL:** Query/Mutation/Subscription fields with types, deprecated directives
- **TypeScript types:** Exported type/interface names from published packages (from `package.json` `types` or `typings` field)

**Files scanned** (additions to existing Step 3):
- `*.graphql`, `schema.graphql`, `schema.gql` — new
- Everything else (proto, OpenAPI) is already scanned

**No contract files found** → `provider_contracts: []` — graceful, no error.

## Tier 2 Extension — Consumer Contract Extraction

Tier 2 already greps for HTTP calls, gRPC channels, and message queue patterns. The extension captures *what specifically* the consumer is calling.

**New output field** in per-repo JSON: `consumer_contracts`

```json
{
  "consumer_contracts": [
    {
      "target": "acme/payments-api",
      "type": "HTTP",
      "consumed_endpoints": [
        { "method": "POST", "path": "/api/v1/payments", "file": "src/checkout.ts", "line": 42 },
        { "method": "POST", "path": "/api/v1/payments/refund", "file": "src/returns.ts", "line": 87 }
      ]
    },
    {
      "target": "acme/auth-service",
      "type": "gRPC",
      "consumed_rpcs": [
        { "service": "AuthService", "rpc": "ValidateToken", "file": "src/middleware/auth.ts", "line": 15 }
      ]
    }
  ]
}
```

**What Tier 2 extracts per pattern:**
- **HTTP calls:** Method + path from literal URL strings. Dynamic paths logged as `UNKNOWN`.
- **gRPC calls:** Service name + RPC method from client instantiation patterns.
- **GraphQL queries:** Operation names and queried fields from `query { }` / `mutation { }` blocks.
- **Package version pins:** Version of imported contract packages from manifests.

**Key constraint:** Only literal/static references are captured. Dynamic route construction is logged as `UNKNOWN` — synthesis marks these as `sync_status: "UNKNOWN"` rather than producing false mismatches.

**No consumer contracts detected** → `consumer_contracts: []` — graceful, no error.

## Synthesis Extension — Contract Verification

After edge resolution (Step 2) and before cluster detection (Step 3), synthesis gains a new **Contract Verification** step.

**Process:**

For each edge in the resolved topology:
1. Look up the provider service's `provider_contracts` from per-repo results
2. Look up the consumer service's `consumer_contracts` from per-repo results
3. Match by edge type (HTTP edge → compare OpenAPI endpoints vs consumed HTTP paths, gRPC edge → compare proto RPCs vs consumed RPCs)
4. For each matched contract pair, run mismatch detection

**Mismatch detection — four categories, tiered by confidence:**

| Category | Confidence | Detection Method |
|----------|-----------|------------------|
| **Phantom endpoints** | HIGH | Consumer calls endpoint/RPC not in provider's contract definition |
| **Deprecated usage** | HIGH | Consumer calls endpoint/RPC marked `deprecated: true` in provider's contract |
| **Version skew** | MEDIUM | Consumer's imported package version doesn't match provider's published version. Flagged but annotated "may be benign — check changelog" |
| **Schema drift (typed)** | MEDIUM | Consumer's generated types (`.d.ts`, `.pb.ts`) reference fields absent from provider's current schema. Only for repos with generated type definitions. |

**Skipped (too noisy):**
- Schema drift for untyped consumers (JavaScript/Python without type definitions)
- Breaking change inference without schema diffing
- Dynamic route inference

**Sync status per edge:** Each edge gains a `contract_sync` field:
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

## Output Artifacts

### topology.json — Contract Additions

**Services gain `contracts` field:**
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

**Edges gain `contract_sync` field:**
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
- **Ranked mismatch list** — phantom endpoints (HIGH) → version skew (MEDIUM) → deprecated usage (MEDIUM) → schema drift (LOW)
- **Per-edge contract status table** — every edge with contract_sync status
- **Contract inventory** — which services have contracts, which don't
- **Recommendations** — "Add OpenAPI spec to acme/orders-worker (no contract found)"

### Severity Ranking

| Severity | Category | Rationale |
|----------|----------|-----------|
| HIGH | Phantom endpoint | Consumer calls something that doesn't exist — will fail at runtime |
| HIGH | Schema drift (missing required field) | Consumer expects data provider doesn't send |
| MEDIUM | Version skew | May be benign but warrants investigation |
| MEDIUM | Deprecated usage | Works today, may break tomorrow |
| LOW | Schema drift (extra optional field) | Provider added fields consumer doesn't use — benign |

## User Interaction — Opt-In at Checkpoint

At the existing Tier 1 checkpoint, the options expand:

> "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). 42 services have parseable contracts (28 OpenAPI, 10 Proto, 4 GraphQL).
>
> Options:
> 1. **Proceed to synthesis** — topology only, no contract verification
> 2. **Run Tier 2 deep scan** — discover additional edges from source code
> 3. **Run Tier 2 + contract verification** — deep scan AND cross-reference contracts
> 4. **Run contract verification only** — skip Tier 2, verify contracts on Tier 1 edges"

Contract verification requires Tier 2 data for consumer-side extraction. Option 4 runs a **lightweight Tier 2** scoped to contract extraction only (consumer endpoints/RPCs) without full edge detection.

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
- Dynamic consumer paths → `sync_status: "UNKNOWN"` with evidence logged
- Edge type has no contract format (shared-infra) → `contract_sync: "NO_CONTRACT"`

## Error Handling (Additions)

| Error | Response |
|-------|----------|
| OpenAPI spec has invalid YAML/JSON | Log parse error, skip contract, `sync_status: "UNKNOWN"` |
| Proto file has syntax errors | Log parse error, skip contract, `sync_status: "UNKNOWN"` |
| GraphQL schema has syntax errors | Log parse error, skip contract, `sync_status: "UNKNOWN"` |
| Contract file too large (>5000 lines) | Extract first 500 endpoints/RPCs, note truncation |
| Consumer calls >100 endpoints on single provider | Retain all, but note in scan log |

## Acceptance Criteria

(Numbered 41-52, continuing from diff mode's 23-40)

41. Given a repo with an OpenAPI spec, Tier 1 extracts all endpoints with methods and deprecated flags into `provider_contracts`
42. Given a repo with proto service definitions, Tier 1 extracts all RPCs with input/output types and deprecated options
43. Given a repo with GraphQL schema, Tier 1 extracts Query/Mutation fields with deprecated directives
44. Given consumer code with literal HTTP calls to a known service, Tier 2 extracts the method and path into `consumer_contracts`
45. Given consumer code with gRPC client calls, Tier 2 extracts service name and RPC method
46. Given a provider's OpenAPI spec and a consumer calling an endpoint not in the spec, synthesis flags a phantom endpoint mismatch with severity HIGH
47. Given a provider with deprecated endpoints and a consumer calling them, synthesis flags deprecated usage with severity MEDIUM
48. Given mismatched package versions between provider and consumer manifests, synthesis flags version skew with severity MEDIUM and "may be benign" annotation
49. Given no contract files in a repo, `provider_contracts` is empty and edge `contract_sync` is "NO_CONTRACT" — no errors
50. Given a malformed contract file, the error is logged and `contract_sync` is "UNKNOWN" — scan continues
51. `contract-risks.md` ranks mismatches by severity (phantom > schema drift > version skew > deprecated)
52. Contract verification is opt-in at the Tier 1 checkpoint — never runs without user consent

## Future Enhancements

- **Shared-DB contract verification:** Migration files as provider contracts, query patterns as consumer contracts
- **Schema diffing across versions:** Clone two versions of a provider, diff the contract surface, detect breaking changes
- **Contract coverage score:** What percentage of edges have verifiable contracts on both sides
- **Integration with diff mode:** Track contract changes over time — "this endpoint was added last week and already has 3 consumers"
