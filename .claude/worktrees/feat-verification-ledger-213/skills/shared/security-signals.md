---
version: 1
---

# Security Signal Detection

> Shared reference for security signal detection consumed by build, spec, and audit.
> For full heuristic semantics, see `skills/siege/SKILL.md` § Activation Heuristic.

## Signal Categories

Seven categories of security-sensitive content. Each category is independently matched — one keyword hit per category is sufficient to count that category as detected.

### 1. Authentication / Authorization

Keywords: `login`, `session`, `token`, `RBAC`, `permission`, `auth`, `JWT`, `OAuth`, `SAML`, `ACL`, `role`, `access control`, `identity`, `SSO`, `MFA`, `2FA`

### 2. Cryptographic Operations

Keywords: `hash`, `encrypt`, `decrypt`, `sign`, `verify`, `key management`, `certificate`, `TLS`, `SSL`, `HMAC`, `AES`, `RSA`, `bcrypt`, `argon2`, `scrypt`, `cipher`, `digest`, `PKI`

### 3. External Input Handling

Keywords: `API endpoint`, `upload`, `deserializ`, `parse`, `URL`, `request body`, `webhook`, `form input`, `input validation`, `sanitiz`, `user input`, `query parameter`, `file upload`, `multipart`

### 4. Secrets Management

Keywords: `API key`, `credential`, `connection string`, `environment variable`, `secret`, `password`, `.env`, `vault`, `key rotation`, `service account`, `bearer token`

### 5. Network Boundaries

Keywords: `inter-service`, `webhook handler`, `CORS`, `proxy`, `gateway`, `gRPC`, `REST API`, `WebSocket`, `HTTP endpoint`, `reverse proxy`, `load balancer`, `ingress`, `egress`

### 6. Data Persistence with PII

Keywords: `user data`, `PII`, `personal data`, `GDPR`, `retention`, `logging sensitive`, `email address`, `phone number`, `SSN`, `data protection`, `anonymiz`, `pseudonymiz`, `data subject`

### 7. Dependency Introduction

Keywords: `new package`, `npm install`, `pip install`, `cargo add`, `version bump`, `native binding`, `dependency`, `third-party`, `supply chain`, `package.json`, `requirements.txt`, `Cargo.toml`

## Activation Threshold

**2+ distinct categories** must match to activate siege. A single category match is insufficient (too many false positives).

| Matched Categories | Action |
|---|---|
| 0 | No security review needed. Silent skip. |
| 1 | `security_review: recommended` in contract. Build logs but does not dispatch siege. |
| 2+ | `security_review: required` in contract. Build dispatches siege automatically. |

## Scanning Targets

Signal detection scans text content. The scan targets vary by consuming skill:

| Skill | Scan Targets |
|---|---|
| **spec** | Ticket body, investigation findings, design doc content |
| **build** | Design doc content, `git diff <base-sha>..HEAD` (changed file contents) |
| **audit** | Existing behavior — audit performs its own security surface detection |

Scanning is case-insensitive keyword matching. One keyword hit per category is sufficient — do not count multiple hits within the same category.

## Contract Field: `security_review`

Optional top-level field in the contract YAML schema (version 1.0). Presence indicates security signals were detected during spec writing. Absence means no signals detected.

```yaml
security_review:
  status: required | recommended
  signals_detected:
    - category: "auth"
      evidence: "ticket mentions login flow and JWT token handling"
    - category: "external_input"
      evidence: "design doc includes REST API endpoint definitions"
  deployment_context: public | intranet | hybrid  # optional
```

### Field Semantics

| Field | Required | Description |
|---|---|---|
| `status` | Yes | `required` (2+ signals) or `recommended` (1 signal) |
| `signals_detected` | Yes | Non-empty array of matched categories with evidence text |
| `signals_detected[].category` | Yes | One of: `auth`, `crypto`, `external_input`, `secrets`, `network`, `pii_data`, `dependencies` |
| `signals_detected[].evidence` | Yes | Brief description of what triggered this category |
| `deployment_context` | No | Flows to siege's `deployment_context` parameter if present |

### Escape Hatches

These are passed as flags when invoking build:

- `--force-siege` — Dispatch siege regardless of signal count (maps to siege `--force`)
- `--skip-siege` — Suppress siege even when signals/contract require it (maps to siege `--skip`)
