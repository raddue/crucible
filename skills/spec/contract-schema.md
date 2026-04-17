# Contract Schema (version 1.0)

Machine-readable contracts solve the core challenge of two async agents communicating about interdependent work. Prose is ambiguous — two LLMs reading the same paragraph extract different implications. Contracts make the seams structural.

This file is the canonical schema reference for `/spec` contracts. `/design` emits contracts using the same schema. `/build` consumes contracts via this schema.

## Schema

```yaml
# docs/plans/YYYY-MM-DD-<topic>-contract.yaml
version: "1.0"
ticket: "#123"
epic: "#100"
title: "Brief ticket title"
date: "2026-03-21"

# Public API surface -- what this ticket exposes
api_surface:
  - name: "FunctionOrClassName"
    type: "function|class|interface|endpoint|event"
    signature: "def function_name(param: Type) -> ReturnType"  # human-readable
    params:  # structured for machine comparison
      - name: "param"
        type: "Type"
        required: true
    returns: "ReturnType"
    description: "One-line purpose"
  - name: "/api/v2/resource"
    type: "endpoint"
    method: "POST"
    request_schema: "{ field: Type }"
    response_schema: "{ field: Type }"
    description: "One-line purpose"

# Hard constraints -- if violated, the implementation is wrong
# Split into checkable (verified by inspection) and testable (require runtime tests)
invariants:
  checkable:
    - id: "INV-1"
      description: "Must not add a runtime dependency on X"
      verification: "No import/require of X in production code"
      check_method: "grep"  # grep | code-inspection | file-structure
    - id: "INV-2"
      description: "Must be idempotent"
      verification: "Calling twice with same input produces same result"
      check_method: "code-inspection"
  testable:
    - id: "INV-3"
      description: "Response time < 200ms for the common case"
      verification: "Benchmark test with representative data"
      test_tag: "contract:perf:inv-3"  # implementer must write a test with this tag
    - id: "INV-4"
      description: "Must handle concurrent writes without data loss"
      verification: "Concurrent test with 10 writers"
      test_tag: "contract:concurrency:inv-4"

# Cross-ticket dependencies -- which other contracts this references
integration_points:
  - contract: "2026-03-21-auth-refactor-contract.yaml"
    ticket: "#124"
    relationship: "consumes"
    surface: "AuthService.validate_token"
    notes: "Depends on the new token format from #124"

# Security review directive -- optional, present when security signals detected
# during spec writing. Consumed by /build Phase 4 Step 5.5 to dispatch siege.
# Omit entirely if no signals detected. See shared/security-signals.md.
security_review:                           # OPTIONAL
  status: "required"                       # required (2+ signals) | recommended (1 signal)
  signals_detected:
    - category: "auth"                     # auth | crypto | external_input | secrets | network | pii_data | dependencies
      evidence: "ticket mentions login flow and JWT tokens"
    - category: "external_input"
      evidence: "design doc includes API endpoint definitions"
  deployment_context: "public"             # OPTIONAL — public | intranet | hybrid

# Decisions made where multiple viable paths existed
ambiguity_resolutions:
  - id: "AMB-1"
    decision: "Chose event-driven over polling"
    confidence: "high"
    alternatives: ["Polling every 5s", "WebSocket push"]
    reasoning: "Event-driven aligns with existing message bus; polling adds unnecessary load"
    reversibility: "Medium -- would require changing 3 consumers"
```

## Version Rejection Rule

Consumers encountering an unknown schema version must **reject** the contract with a clear error rather than silently ignoring unknown fields. This prevents silent incompatibility when the schema evolves.

## Invariant Categories

- **Checkable invariants** (`checkable`): Can be verified by code inspection, grep, or structural analysis during quality gate. The `check_method` field indicates how:
  - `grep` -- simple pattern matching in production code
  - `code-inspection` -- reading and reasoning about code
  - `file-structure` -- checking file existence/organization

- **Testable invariants** (`testable`): Cannot be verified by inspection alone -- they require runtime behavior. Each testable invariant has a `test_tag` that the implementer must use when writing the corresponding test. The quality gate verifies that a test with the matching tag exists and passes, but the implementer is responsible for writing a test that actually validates the invariant. This is an honest boundary: the quality gate can check that the test exists and passes, but cannot guarantee the test faithfully represents the invariant.

## Contract Cascading

When `/spec` resolves an ambiguity or defines an API surface on ticket N that affects ticket M:
1. The dependency graph identifies the impact.
2. Ticket M's contract is updated with the integration point.
3. Ticket M's spec-writing agent receives the upstream contract as context.
4. If ticket M is already in progress (same wave), the wave-based re-queuing mechanism handles the conflict -- ticket M is re-queued to the next wave where it will be re-processed with the upstream contract available.

## Required Fields Summary

| Field | Required | Notes |
|-------|----------|-------|
| `version` | Yes | Must be `"1.0"` |
| `ticket` | Yes | `"#NNN"` format |
| `epic` | Yes | `"#NNN"` format |
| `title` | Yes | Brief ticket title |
| `date` | Yes | `YYYY-MM-DD` format |
| `api_surface` | Yes | At least one entry |
| `api_surface[].type` | Yes | `function`, `class`, `interface`, `endpoint`, or `event` |
| `api_surface[].params` | Conditional | Required for `function`, `class`, `interface` types |
| `invariants` | Yes | Must have at least one checkable or testable |
| `invariants.checkable[].check_method` | Yes | `grep`, `code-inspection`, or `file-structure` |
| `invariants.testable[].test_tag` | Yes | Pattern: `contract:<category>:<id>` |
| `security_review` | No | Optional; present when security signals detected (see `shared/security-signals.md`) |
| `security_review.status` | Conditional | Required when `security_review` present. `required` or `recommended` |
| `security_review.signals_detected` | Conditional | Required when `security_review` present. Non-empty array of `{category, evidence}` |
| `integration_points` | No | May be empty if no cross-ticket deps |
| `ambiguity_resolutions` | No | May be empty if all decisions were high-confidence |
