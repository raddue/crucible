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

### 8. Destination-Bearing Construct (structurally detected)

Not a keyword scan. Reads two inputs — a **host baseline** and a **shape match** — from the
`git diff` and the tree it lives in:

- **Host baseline (source + staleness policy).** The set of hosts already referenced by project code,
  computed once per run by a case-insensitive `git grep -Eo` at the comparison **base** SHA over
  `https?://[^/ ]+` literals and over module specifiers (`from "…"`, `require("…")`, `import … "…"`)
  whose first segment parses as host-qualified (contains `//` or `.`). Only host literals and
  host-qualified specifiers are extracted; anything else (hosts assembled at runtime from variables)
  returns **uncertain**, not "not contacted". No cache — recomputed against `base` each run, bounding
  staleness by the run itself.
- **Shape match over the diff:** (1) a call-expression containing a URL/host literal; (2) an assignment
  to an identifier matching a `url|endpoint|webhook|callback|dsn|tracking`-shaped name; (3) a call
  signature in the **finite SDK-init table** — initialised to `Sentry.init(`, the
  PostHog/`analytics`-family init, `Datadog`, New Relic, Mixpanel, and Segment init calls, each a bare
  entry, extended only by adding a row never by keyword inference; or (4) a package-manifest
  dependency/scripts/postinstall entry that adds or invokes a host/shim, or a registry/proxy/mirror
  assignment in a config file (`.npmrc` `registry=`, `proxy=`/`mirror=`/`registry=` keys in
  `.npmrc`/`.yarnrc`/`.cargo/config`-shaped files), whose value is a host literal visible in the diff.
  This fourth primitive detects only dependency/package and registry/proxy/mirror/install-hook additions
  whose destination is a **host literal visible in the diff** — it does **not** reach the
  named-shim-runtime-hidden form (see the detector residual below).

**Single-match trigger.** A shape match fires **only when** its resolved destination is a host **not in
the baseline** — a *new* host the diff introduces. Excluded by construction: same-host literals,
relative-origin URLs (`fetch("/api/x")`), test-file paths (`*/test/*`, `*/tests/*`, `*_test.*`,
`*.test.*`), and string literals not inside a call/assignment expression — **except** in the
package-manifest and registry/proxy/mirror config-file contexts, where a bare
`postinstall`/`registry`/`mirror`/`proxy` value is itself the destination-bearing construct and is
matched in place. Unlike the seven keyword categories, **a single bounded match is sufficient on its
own** to trigger siege — independent of the 2-of-7 threshold — because a new-host destination is
exactly the construct class this rule exists to catch. The existing 2-of-7 threshold is otherwise
unchanged.

**Cannot-conclusively-classify.** If a shape token is present **and** its destination is unresolvable
from the diff (the identifier matches the shape or an `https?://` literal is present but the host is
assembled from variables not in the diff — baseline extraction returns **uncertain**), report
**"cannot conclusively classify"**. Zero shape tokens → skip (nothing to classify).

**Detector residual (stated, not papered over).** The named-shim-runtime-hidden form — a dependency
whose smuggled destination lives only in the published package's runtime/postinstall code, with no host
literal in the diff (`npm i <attacker-shim>` + `import … from "attacker-shim"`) — is **not
detector-reachable** and emits zero shape tokens. It is covered by the disclosure half (DEC-5's
fourth-class declaration makes the shim destination-bearing, so a conforming author mints a ledger entry
or emits a "did not copy" decline signal), not by this trigger.

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
