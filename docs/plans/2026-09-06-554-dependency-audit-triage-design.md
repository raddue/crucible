---
ticket: "#554"
date: "2026-09-06"
status: "design"
skill: "dependency-audit"
---
# Design — dependency-audit: severity × dependency-scope triage tree
## 1. Problem
`skills/dependency-audit/SKILL.md` normalizes every ecosystem's severity vocabulary
onto one scale (Critical / High / Moderate / Low / Informational) and then reports a
**flat severity list**. Blocking is a single threshold on that flat list
(`min_blocking_severity`, default `critical`).
That collapses two findings a real triage decision treats very differently:
- a Critical CVE in a package that ships to production, and
- a Critical CVE in a lint plugin that never leaves the developer's laptop.
Both currently render identically and both currently block. The consumer of the audit
(a human, or `build`'s gate ledger) gets no signal about which one to drop everything
for. #554 asks for the missing dimension.
## 2. Scope — and one explicit non-goal
**In scope: dependency-scope reachability.** Is the vulnerable package in the
production dependency closure, or only in the dev/build closure?
**Explicit non-goal: function-level reachability.** This design does NOT determine
whether the vulnerable *function* is actually called from a runtime code path. That is
call-graph analysis (the thing Snyk Reachable Vulns and Semgrep SSC do), it needs a
per-language static analyzer, and it is wrong often enough that a wrong answer silently
downgrades a real Critical.
This distinction is load-bearing and must be stated **in the skill's own output**, not
just here. A reader who sees "runtime-reachable" and assumes "the vulnerable code
actually runs" has been misled by us. The output therefore says **`prod` / `dev` /
`unknown`** — scope words — and the skill carries a one-line statement of what the
classification does and does not mean.
**DEC-1:** Reachability means *dependency scope*, never *call-graph reachability*. The
skill must never emit the bare phrase "runtime-reachable" as a claim about executed
code.
**Trust boundary — no checkout-controlled subprocess.** #554 introduces **no subprocess the
untrusted checkout can steer** (`cargo tree`/`npm audit --omit=dev` are gone — §4.2). The only
interpreter invocations it adds are the skill's own — all first-party, all bound by **one
general hygiene invariant**: **every interpreter invocation this skill makes against
checkout-influenced data is `python3 -I <absolute-first-party-script-path>`, with the working
directory set outside the checkout; never `-c`, never `-m`** (which prepend the current
directory to `sys.path`, letting a planted `json.py`/`os.py`/`sitecustomize.py` shadow a
stdlib import). The **interpreter binary itself** is resolved and pinned outside checkout
influence (an absolute interpreter path or a sanitized `env`/PATH — `PATH`, `PYTHONPATH`,
`LD_PRELOAD`, and user-site are neutralized, not merely the script's `sys.path[0]`), so a
checkout-committed venv or `LD_PRELOAD` cannot hijack the binary (R6-BA2). The
code-requiring operations — the lockfile-closure walk (§4.1), the
path-validation helper (realpath + per-component lstat + resolved-size checks, §4.1/§4.3),
and the per-input sha256 digest computation (§7.6) — are dispatched as subcommands of **one**
hygiene-pinned first-party stdlib script, so the pinned surface is a single file and the
invariant binds every one of them identically (R5-01). Those run the skill's own code against
untrusted *data*. The only new operations beyond them are **non-executing file reads** —
parsing the lockfile the audit
already reads (`package-lock.json`/`npm-shrinkwrap.json`) and the manifest files — plus
rendering their result into `audit-results.md`. Classification is therefore free of the
code-execution / config-steering surface a `cargo tree` or `npm audit --omit=dev`
subprocess would open, which is exactly why neither probe is used (§4.2). Three consequences,
binding on the whole design:
1. Dependency declarations and graph edges are derived from untrusted files; the only
   external-trust input is caller-provided canonical `checkout_root`, and it gates demotion
   eligibility only. Classification remains a **triage aid, not a security boundary** — a checkout can still lie about its own scope
   (every dep declared under `devDependencies`; a `package.json` that hides a production
   import behind a dev table). The classification reflects the manifest's *claim*, not
   ground truth. Every `dev` value is stated at declaration-faithful strength — "absent from
   the recorded production closure/declarations" — never "genuine" or "proved." A second
   read of checkout-controlled files can detect malformed or internally inconsistent data,
   but cannot independently verify scope: the checkout controls both reads. Such checks may
   fail closed to `unknown`; they must not be described as evidence against a malicious or
   incomplete manifest. `unknown` (DEC-2) remains the failure state whenever parsing,
   bounded reads, or declared-graph resolution cannot complete.
2. The reads are **bounded and validated**: the lockfile walk caps lockfile input (64 MiB) and npm manifests (1 MiB each, 64 MiB total) and
   uses a visited-set (no hang on a 1 GiB lockfile or a dependency cycle), and manifest paths
   are resolved (`os.path.realpath`) and containment-checked against the scope root with
   per-component symlink refusal (§4.1). A path containing any character outside the
   printable-ASCII whitelist (U+0020–U+007E) — e.g. an embedded newline that could forge a
   line-start marker — is refused at intake, never opened, never echoed (§4.1/§4.3, R5-05).
   Any violation → `unknown`, never `dev`.
3. Attacker-controlled text rendered anywhere (the `audit-results.md` write and the
   §7.4 prompt) is sanitized to a
   printable-ASCII whitelist (§7.7), so it cannot forge a control token.
Under the default `advisory` gating, scope never affects blocking (§6), so this changes no
caller's blocking behavior. Under `strict`, the operator explicitly opts in to trusting the
manifest's scope declarations — DEC-5 carries that warning (§6).
## 3. The reachability model
Three states, per (manifest, package):
| State | Meaning |
|---|---|
| `prod` | npm: package is in the manifest's recorded production closure. Python: package directly matches a production-mapped declaration in `pyproject.toml` or `requirements.txt`. Neither claim says the package's code executes. |
| `dev` | npm: package is absent from the recorded production closure with a valid DEC-9 token and complete coverage of all recorded npm scopes (§4.1). Python has no dev-mapped declaration under #554: named groups are `unknown` even if called `dev`; the reserved Python token would require an approved explicit dev-only mapping plus all §4.3 gates. Neither classification proves true runtime scope. |
| `unknown` | The ecosystem could not be classified, or the classification probe failed. |
**DEC-2 (fail-safe): `unknown` is triaged exactly as `prod`.** Never as `dev`.
This is the same epistemic stance the skill already takes in Overall Result
Computation — *"INCONCLUSIVE outranks FAILED because unknown coverage is more dangerous
than a known, retryable tool error."* Unknown scope is more dangerous than known-dev
scope, so it inherits the more urgent bucket. A classifier that fails open into `dev`
would let a probe crash silently downgrade a Critical, which is the single worst
failure this feature could have.
`unknown` remains **visibly distinct from `prod` in the output** — it is triaged the
same, but reported as `unknown` so the reader knows the classification is absent rather
than affirmative.
### 3.0 Demotion tokens — `dev` must show its work
**DEC-9.** `dev` is the **only** state that *reduces* urgency. It is therefore the only
one that must carry a receipt. AC-13 deliberately does not require this source-class table to be independent scope evidence: it verifies claim boundaries, not the R7 review's broader fail-safe-independence principle.
Each contributing source (one manifest/package classification) may report `dev` **only if
that contribution carries exactly one token from this closed set and satisfies its ecosystem
method's conditions**. The npm token requires recorded-graph completeness and successful coverage of every recorded npm audit scope (§4.1); the Python token
requires a genuinely dev-mapped declaration, successful supported-manifest parsing, complete bounded-census reads, and declaration gates in
§4.3. No supported Python table is dev-mapped by default in #554: group names do not
establish dev-only scope, so the Python token is reserved and cannot be minted by this
design. If a later explicit dev-only mapping is approved, several dev-mapped tables in one
manifest declaring the same package emit one token using the lexicographically first table name. A deduplicated finding carries one valid token
for each contributing `dev` source (§3.1):
| Token | Emitted when |
|---|---|
| `absent-from-prod-closure` | package present in full findings and absent from §4.1's recorded lockfile closure (`dependencies` + `optionalDependencies` + `peerDependencies` edges; seeds from audit-scanned manifests, not lockfile membership keys — R6-02). Mint only when caller-supplied canonical `scope_root` equals `checkout_root`, every recorded seed resolves, every supported recorded edge is traversed, and every npm scope in the audit manifest scan has a successful valid audit result and required declaration/closure inputs (§4.1). **Declaration-faithful only**: "absent from the *recorded* closure", never "genuinely dev-only". A checkout that omits a manifest or prunes an edge before the run can fabricate this token (R6-01/R7-02/R7-05); §13 records these residuals. |
| `declared-in-dev-manifest:<table>` | Direct Python dep declared in a dev-mapped table and no prod-mapped table in that manifest. Emit only if the bounded census is complete, finds no production-mapped declaration or extras table in any discovered supported manifest, finds no supported `[project].dynamic` declaration containing `dependencies` or `optional-dependencies`, and detects no finite-pattern plausible-but-unscanned Python metadata within its traversal in `checkout_root`; path-less `pip-audit` cannot rule out invisible prod transitives (§4.3). Any unreadable candidate, unparseable supported manifest, or unsupported declaration syntax makes the would-be `dev` contribution `unknown` (R6-04/R7-03/R7-08). Census re-discovers directory inventories and candidate inputs independently of immutable audit manifest list. Caller-supplied `scope_root` must equal `checkout_root`; otherwise the would-be `dev` contribution is `unknown` (CA-3). The `<table>` argument has no eligible values under #554 (§4.3); do not mint this token from PEP 735 or Poetry group names. If a future explicit dev-only mapping is approved, constrain `<table>` to that mapping; if several mapped dev tables declare a package, use the lexicographically first name. A Poetry group `<name>` may be rendered only if it is a **full-string anchor match** `[A-Za-z0-9._-]+` (both ends — R6-06), else the contribution is `unknown` |
**npm recorded-graph completeness rule (not proof of true production scope).** The bounded
parser must read every required npm input, resolve every recorded production seed, and
traverse every supported production edge present in the recorded data. This is a checkable
claim about parser/walk completeness over inputs, not coverage of the auditor's set or true
production set. A checkout that omits a manifest or prunes an edge before the run may still
produce declaration-faithful `dev`; preserve that residual explicitly. If recorded production declarations exist but the resolved set is empty, result is `unknown`; an
empty closure with no recorded production declarations is valid only subject to §4.1 and every
other DEC-9 gate. A malformed resolved set, parse failure, or unresolved seed means `unknown`. Python demotion instead
requires successful declaration parsing and the bounded H4 census (§4.3). Cargo has
**no** source; every cargo finding is `unknown` by construction (DEC-2).
**Evidence/source-class claims (AC-13).** No checkout-controlled source independently
attests actual dependency scope: manifests, lockfiles, audit results, and census inputs remain
controlled by the checkout or registry. The caller-provided canonical `checkout_root` is an
external-trust input; it supports only the claim that caller-declared canonical roots are equal
(`scope_root == checkout_root`), which policy requires before demotion. Equality does not prove
that the root is the whole checkout, scan completeness, or input truthfulness. Same-checkout
reads can detect malformed or internally inconsistent data (for example, a recorded prod
seed with no lock node), but cannot establish that an omitted declaration or edge is false.
A machine-local digest (§7.6) detects changes in observed inputs during compaction recovery;
it does not prove input truthfulness or identify undetected files. The source classification
is explicit:

| Evidence source | Source class | Supported claim | Limitation |
|---|---|---|---|
| Caller-provided canonical `checkout_root` | `external-trust` | Caller-declared checkout root equals canonical `scope_root`; policy permits demotion only when equal | Does not independently prove this is the complete repository root, scan completeness, or checkout contents |
| Scanned `package.json`, npm lockfile, Python manifests/census inputs, audit output | `checkout-consistency` | Detect parse failures, unresolved seeds, selected internal inconsistencies, and changes to observed inputs | Checkout/registry can omit or alter declarations/edges before a run |
| Fixed token grammar, dependency-name parsing, path validation, output sanitization | `format/integrity` | Reject malformed values and prevent structural-marker injection | Does not establish semantic truth or completeness |

No source class turns same-checkout evidence into independent scope proof. AC-13 tests
source classification and claim boundaries; it does not certify a security boundary.
**A `dev` classification with no token, or with a token outside this set, is emitted as
`unknown`.** The token rule is evaluated **per contributing source, before the §3.1
merge**: each source's `dev` contribution must carry exactly one token from the closed set,
or that contribution counts as `unknown`. A merged `dev` finding therefore carries one
valid token **per contributing source** (see §3.1).
`prod` and `unknown` need no token — they are the fail-safe directions, and `unknown`
already carries a free-text reason.
Recorded-graph completeness prevents implementation defects from silently omitting supported
recorded edges or resolving malformed names. It does not detect declarations or edges
omitted before the run. Python transitives remain `unknown` because no dev-mapped direct
declaration token exists (DEC-3).
It is also **greppable**, which is what makes it testable — the structural checker
required by AC-8 can assert the token set is present and closed, that the
untokened-`dev`→`unknown` rule is stated, and that every `Reachability: dev` example in
the skill carries a bracketed token.
### 3.1 Merging across manifests
The existing dedup key is **(package name + CVE ID)**. A package may be `prod` in one
manifest and `dev` in another. Merge is by urgency, most-urgent wins:
```
prod  >  unknown  >  dev
```
So one manifest saying `prod` makes the merged finding `prod`. Only when *every*
contributing source says `dev` is the merged finding `dev`. The per-source values —
including each source's DEC-9 token — are listed in the dedup note so the merge is
auditable. A source whose `dev` contribution has no token (or a token outside DEC-9's
set) counts as `unknown` for merge purposes, per §3.0; two sources separately classifying
the same package as `unknown` (e.g. a PEP 735 group and a non-main Poetry group)
still merge to `unknown`, with no Python demotion token. A future explicit dev-only
mapping would still require a valid token from each source before a `dev` merge. Apply the §4.1 all-scanned-npm-scope gate before merging even successful npm sources.
## 4. Per-ecosystem determination
Per-manifest reachability classification runs only when that manifest produced findings.
**Exception:** the bounded Python declaration census runs once per audit whenever Python
manifests are in scope, including clean repos; it gates `declared-in-dev-manifest` tokens and
must detect a clean production `requirements.txt` even when no manifest produced findings.
### 4.1 Node.js (npm) — recorded lockfile closure, high algorithmic confidence
npm's native `--omit=dev` switch lies — the lockfile `dev` flag is computed over
reachability, not declaration, so a package declared in both `dependencies` and
`devDependencies` is flagged `dev: true` **along with its entire transitive subtree**, and
`--omit=dev` drops the whole subtree (measured §4.5, V2: 47/47 nodes `dev: true`). Rather
than fight that bug with a second `npm audit --omit=dev` subprocess — itself code-execution
surface (a repo-local `.npmrc` steers the registry) — #554 derives prod-scope **purely from
the lockfile the audit already reads — via the §2-general-invariant hygiene-pinned walk
subcommand below, and no other new subprocess**:
**Recorded prod closure.** The seed set is the **production declarations in the paths
recorded by the audit's on-disk manifest scan**: the root `package.json`'s `dependencies` +
`optionalDependencies` + `peerDependencies`, unioned with the same three fields of each
recorded workspace-member `package.json`. Root `peerDependencies`/`optionalDependencies`
seeding is an unverified, fail-safe over-approximation — the §4.5 fixtures verify a
*dependency's* auto-installed peer (V3), not a root peer/optional as an independent prod seed —
and must not be removed, since dropping a real prod seed can shrink the closure and mint a
false `dev` (M2/R-8). Lockfile `packages`-map keys do not select workspace
membership; they resolve and crawl dependency seeds only. Thus a member deleted from the map
cannot silently vanish from the recorded seed, and a scanned member under `apps/web` or
`libs/x` does not need a literal `packages/` prefix. **Scope partition (S1).** The scan
partitions every scanned `package.json` into exactly one npm scope before seeding: each manifest
belongs to the nearest workspace root whose `workspaces` glob patterns match its on-disk path
(the closest enclosing root `package.json` that declares a matching `workspaces` glob), and the
root is its own workspace. A manifest matched by no root's `workspaces` pattern is **not
dropped** — it forms its own single-manifest scope, seeded and gated like any other; an
independent lockfile-less sub-project is a recorded scope whose missing lockfile is a skipped
scope. `workspaces` patterns are checkout-controlled, so a glob edit can only move a manifest
between scopes, never drop it from seeding or from the all-scanned-npm-scope gate (R-2). This
same-checkout source does not prove
that scan omitted no member before the run (R7-02). The lockfile is used only to **resolve and
crawl** those seeds: resolve each seed through the lockfile's `packages`
map (the node for that name) and traverse **each** of that node's `dependencies`,
`optionalDependencies`, and `peerDependencies` fields to the transitive closure (npm
auto-installs peers — npm 7+ records them as lock nodes flagged `peer: true` in the depender's
`peerDependencies`, not `dependencies`; and `optionalDependencies` are installed-and-shipped
packages such as platform binaries, so they must be in the closure too). **`packages` map required (S2).** The walk reads the lockfile's `packages` map, so lockfileVersion 2–3 closures are unambiguous; a lockfile with no `packages` map (a v1 `lockfileVersion`) leaves every seed unresolved and yields `unknown` + a warning naming `lockfileVersion`, never `dev`. **A seed that resolves to no lock node (R5-04/R6-08) is a probe failure**, not a silent skip: the manifest declares a production dependency the lockfile does not contain, so the closure cannot be trusted to cover it → `unknown` + warning for that manifest's findings. There is no lockfile "members table" and no lockfile-derived membership cross-check. An unreadable scanned member `package.json` is a probe failure → `unknown` + warning. A seed recorded in a scanned manifest but absent from the lockfile is likewise `unknown`. These are same-checkout consistency checks, not independent evidence that scan membership or declarations are truthful. A finding whose package is in the recorded closure is `prod`. A `dev` token is refused unless the parent supplies trusted canonical `checkout_root` and it equals canonical `scope_root`; never infer checkout root from repository-controlled files or commands. Missing or unequal roots make a would-be `dev` contribution `unknown`; a package already established as `prod` remains `prod` (CA-3).
**All-scanned-npm-scope demotion gate.** Record every npm scope identified by the audit's own manifest scan, including skipped scopes (for example, missing lockfile) and audit errors. Before any npm `dev` token or merge, require every recorded npm scope to finish successfully with a valid audit result and readable, valid required declaration/closure inputs. A skipped, failed, invalid, or incomplete scope blocks *all* npm `dev` tokens, even without an overlapping package or any findings. Keep independently established `prod`; turn every would-be npm `dev` contribution into `unknown` with a sanitized warning identifying the unavailable recorded scope (§7.7). Recompute merge, triage, and strict blocking from effective values. Existing overall-result precedence for audit failure/skip remains unchanged (§6); where existing result rules permit `BLOCKED`, Critical/High `unknown` blocks under `strict`. This gate covers only scanned/recorded scopes, not manifests omitted before scan (R7-02).
**Intake validation and resource bounds.** The walk opens the lockfile only after
`os.path.realpath()` containment against the scan scope root (a `package-lock.json` symlink
to `/dev/zero` or outside the checkout is refused, lstat-ing each path component), then checks
the *resolved* file's size against the 64 MiB cap (a stat on the name under-reports a
symlink's target) and reads it bounded. This path validation is itself a hygiene-pinned
subcommand of §2's first-party script, not bare Read/Glob logic (R5-01): `realpath`/`lstat`/
`stat` on a resolved path need Python; every such operation shares the single pinned
invocation. Any resolved path containing a non-printable-ASCII character — a POSIX filename
may hold a literal newline, and a newline-bearing manifest/directory name could forge a
line-start `status: complete` sentinel after §4.1's provenance-only checks pass (R5-05) — is
refused at intake → `unknown` + warning, never opened, never echoed. The walk uses an
explicit visited-set (a cyclic
`peerDependencies` chain terminates); any trip → probe failed → `unknown` + warning — so a
crafted 1 GiB lockfile or dependency cycle does not hang the parser. FIFO/device-open risks
remain as disclosed in R7-09. Independently of the 64 MiB lockfile ceiling, the
closure walk caps every scanned root/workspace `package.json` at 1 MiB and their
aggregate at 64 MiB. Apply both limits on every manifest read (including non-empty
closure paths): precheck verified resolved size, then `fstat` the opened fd, reject if
its size exceeds either remaining budget or per-file limit, and read at most the allowed
bytes plus one to detect growth/incomplete reads. Reject a short/incomplete read or
any cap overflow before JSON parsing; close fd, mark the scope's probe failed →
`unknown` + warning, and refuse npm `dev` tokens across recorded scopes. The closure walk is additionally bounded by a fixed node/edge ceiling (at most 1,000,000 nodes visited and 1,000,000 edges traversed; exceeding either → probe failed → `unknown` + warning and refuse npm `dev` tokens across recorded scopes), and the pinned closure-walk subcommand runs under a fixed 60-second wall-clock timeout; a non-zero exit, signal, or timeout is a run-global probe failure → `unknown` + warning that trips the all-scope npm gate for **every** recorded scope (R-4), never only the affected scope. These manifest caps do not replace the lockfile cap, the node/edge ceiling, or the timeout.
**Hardening applies to every manifest open, not just the guard's cold path (FA-2 / R6-02).** The
realpath-containment + per-component symlink refusal + verified-size + printable-ASCII intake
hardening of this paragraph (and §4.3's Python equivalent) applies to **all** opens of
checkout-controlled files — the lockfile, every workspace-member `package.json` the walk
reads on the normal non-empty path (whose paths come from the validated scan, not raw
attacker keys), the census's Python manifests — identically. A checker verifying only
§4.1's empty-closure-guard reads while the every-day member-open path stays unhardened
satisfies AC-12's letter but not its intent.
**fd-based read, final-component TOCTOU closed (BA-3).** The validate-then-open sequence is specified on an open
file descriptor, not a path string: `os.open(path, O_RDONLY|O_NOFOLLOW)`, then `fstat` on the
fd (size and symlink status re-verified *after* open), then read from the fd — so a final-component
swap to a symlink between lstat and open cannot defeat containment (R7-09). Where the
design says “realpath then open”, the realpath containment is a pre-filter and the
fd-based fstat is the binding check; a checkout is additionally assumed not to be mutated
mid-classification; §7.6 detects observed input changes across compaction recovery.
**Node → package-name resolution (load-bearing).** npm has **one canonical name space**:
the **resolved package name** — the name the package is actually released and CVE-keyed
under — is used on **both** the closure side and the finding side (R5-02). A lock node's
resolved name is:
- its `name` field **when the lockfile records one**, and **only then** — npm records `name`
  on sub-package entries **only** for aliased/`?npm:`-spec dependencies (`"logger":
  "npm:winston@3.8.0"` → node `name: "winston"`). Non-aliased lockfileVersion-3 nodes carry
  **no** `name` field; deriving names solely from `node.name` yields an empty closure.
- **else** the suffix after the last `node_modules/` in the lockfile `packages` map key
  (`node_modules/request` → `request`).
**Alias targeting (R6-07).** Resolve each incoming edge to its lock node before
validating its resolved name. A node `name` equal to its ordinary key suffix is accepted
only after ordinary package-name validation; a differing `name` requires a well-formed
`npm:` alias spec on that *incoming edge*, with a valid target equal to node `name`.
For direct seeds the spec comes from the scanned root/workspace manifest declaration;
for transitive `dependencies`/`optionalDependencies`/`peerDependencies` edges it comes
from the recorded depender lock node's edge spec. For example, `prod` declaring
`"logger": "npm:winston@3.8.0"` resolves `node_modules/prod/node_modules/logger`
with `name: "winston"` and traverses it. An absent, malformed, or mismatching alias
target or invalid ordinary name rejects the node → `unknown` + warning for the affected
manifest, never a silently-renamed `dev` (R6-07). This keeps one canonical resolved-name space on both
sides: incoming edges resolve to placed lock nodes first; the closure stores each node's
resolved name, and findings (whose CVE/dedup key is the resolved package name) are matched
against that resolved-name closure.
**Placement-aware resolution (recorded data only):** For each scanned manifest at relative
directory `d` (root: empty), resolve a direct dependency key `x` by npm lookup from `d`:
try `d/node_modules/x`, then the corresponding `node_modules/x` in each ancestor directory
up to root. For a lock node at key `p`, resolve each outgoing dependency/optional/peer edge
`x` from that node's installation directory (`p`), then its ancestor directories up to
root (skip ancestor components named `node_modules` when forming lookup bases). `x` may be scoped (`@scope/name`); preserve its full key, not its last path segment.
Take the first existing valid `packages` entry on this ordered chain; never search all
suffixes or substitute `node_modules/dev-tool/node_modules/x` for a root `x`. Validate
every edge's spec against that selected node's resolved name (§4.1 alias targeting). If
placement, node, edge name/spec, or supported link metadata is missing, ambiguous, or
unsupported, fail the affected scope's probe → `unknown` + warning and no npm `dev` token
(§4.1 all-scanned-scope gate). A scanned workspace manifest at `apps/web/package.json`
uses `apps/web/node_modules/x`, then `apps/node_modules/x`, then `node_modules/x` for
its seeds; it does not use unrelated nested nodes. Workspace-link entries are not
ordinary package nodes: if a selected `node_modules/x` entry declares `link: true`,
require exactly one valid relative `resolved` target whose normalized path is a scanned
workspace directory with a `packages` entry there; validate its path by the same intake
policy, require the target package name to match the incoming key (or its valid `npm:`
alias target), then traverse that target's recorded edges.
Missing target, unscanned target, out-of-root target, contradictory or cyclic link, or
unsupported link shape fails closed. Lockfile keys do not add workspace members. The
resolved names of traversed nodes form the closure membership set; a finding is `prod`
iff its resolved name is in that set. **Name-match floor (S9).** A finding whose reported name
matches **no lock-node resolved name** in its scope is a name-space mismatch, not a proven
absence: it yields `unknown` + a warning, never `dev` and never `absent-from-prod-closure` — an
`npm audit` finding keyed by a declaration alias or a node-path suffix rather than a resolved
name would otherwise fall out of the closure and mint a false demotion (R-3). This is a walk of
recorded placements, not proof
of npm runtime resolution or of declarations/edges omitted before the run (R7-05).
**Empty-closure consistency check (not independent proof):** when the computed closure
is empty, compare it with the production declarations in the `package.json` paths the audit's
manifest scan already recorded. This same-checkout consistency check catches parser or
resolution defects; it does not independently attest that scan membership or declarations
are complete or truthful (§3.0/R7-04). Do not derive membership from lockfile keys or
invent a lockfile members table. Each recorded path is **validated before opening, on the
resolved path**: `os.path.realpath()` the candidate and require the
**resolved** path to fall inside the **resolved** scope root (a normalization-based
containment passes a `packages/x` symlink to `/home/user`, so containment is checked only on
the realpath), reject any candidate whose realpath escapes the root, **reject if any path
component is a symlink** (lstat each component, not just the final `package.json`), reject
any non-printable-ASCII character in the path (§4.1/§4.3, R5-05), and
require the basename to be exactly `package.json`. Any path that fails these checks makes
the probe failed → `unknown` + warning (never opened, never echoed). Otherwise inspect their `dependencies`/`optionalDependencies`/`peerDependencies` —
if any declares a production dependency while the closure is empty, the probe is defective →
`unknown` + warning. If they all agree that no production dependency is declared, the
closure is legitimately empty (a dev-only manifest), and findings proceed to token logic
(each is `dev` only via `absent-from-prod-closure`). Unreadable `package.json` files → probe failed →
`unknown` + warning (the distinction is undecidable, and DEC-2 says take the fail-safe
branch).
These properties describe the recorded-data classifier, not an independent authority:
- Because the walk follows explicit lock-node `dependencies` + `peerDependencies` edges, a
  dual-declared package and its **entire transitive subtree, peers included**, are `prod`
  by construction. This **replaces and subsumes the earlier DEC-7 manifest override**: it
  needs no name match, so it cannot be limited to the declared key itself.
- npm aliases (`"logger": "npm:winston@3.8.0"`) resolve through the lock node's recorded
  package name, so an aliased production dependency is `prod` without any key search — and
  the same resolved name is the closure's membership key, keeping one name space end to end
  (R5-02).
- The walk traverses every supported edge present in the recorded lockfile data and uses one
  canonical resolved-name space. This prevents implementation omissions in the supported
  recorded graph; it cannot detect a manifest or edge omitted before the run. See residuals
  in §13.
**`absent-from-prod-closure`** is minted when a package is present in the full run's
findings and absent from the computed closure. Its meaning is exactly: "not reachable via any
production edge in the recorded, possibly-edited lockfile graph", not "genuinely dev-only".
A hostile checkout can prune a `dependencies` edge before the run and cause a false `dev`;
non-empty graphs do not independently cross-check every production edge (R7-05). That residual
is named in §2 ("triage aid, not a security boundary") and §6's strict warning. The
walk runs as a **hygiene-pinned first-party interpreter invocation per §2's general
invariant** (one of that script's subcommands): `python3 -I
<absolute-path-to-the-skill's-own-walk-script>` — an **absolute script path** (never `-c` or
`-m`, which prepend the current directory to `sys.path`), `-I` (drops `PYTHONPATH` and the
user site), and the working directory set **outside** the checkout. The script is the skill's
own first-party code importing only stdlib; `sys.path[0]` is the script's trusted directory,
never the untrusted checkout, so a planted `json.py`/`os.py`/`sitecustomize.py` at the
checkout root cannot shadow a stdlib import. The checkout supplies *data* (lockfile bytes),
never code. Scope classification is still a triage aid,
not a security boundary: a hostile manifest that declares its critical dep under
`devDependencies` will classify that dep `dev` (§2, §6's strict warning) — a property of
*declared* scope, not of a broken probe.
**Method confidence: high for the recorded graph only** — deterministic graph walk over
the structured lockfile the audit already reads, with no rendered tree, subprocess, or npm
`dev` flag. This does not mean high confidence in the truth/completeness of checkout
declarations (R7-02/R7-05).
### 4.2 Rust (cargo) — unknown, no safe probe
`cargo audit` has no dev/prod switch, and correctly attributing prod-versus-dev scope would
require running `cargo tree`/`cargo metadata` as subprocesses *inside the untrusted checkout*
— and cargo honors a repo-local `.cargo/config.toml` (and `rust-toolchain.toml`, and path
deps that resolve outside any scratch copy) that can execute attacker code as the CI user.
No sandboxing scheme survived the security review: each attempt replaced one
attacker-controlled input channel with a control *narrower* than the channel. Per §3.0's own
principle — decline to classify rather than force a probe into a shape it cannot safely hold
— #554 does **not** classify cargo: every cargo finding is **`unknown`**, triaged as `prod`
(DEC-2), free-text reason "no safe reachability probe; cargo classification out of scope for
#554".
**Confidence: none** — `reachability-method: unavailable`.
### 4.3 Python (pip-audit) — direct-only, low confidence
This is the weak ecosystem and the design says so rather than papering over it.
`pip-audit`'s JSON reports resolved packages **without dependency paths**, so a
transitive vulnerability cannot be attributed to a prod-or-dev root at all.
**DEC-3:** Classify **direct** dependencies from manifest structure. Every
**transitive** finding is `unknown` (→ triaged as `prod`).
A reported package is *direct* iff its PEP 503-normalized name appears in a supported
production-mapped or named-group declaration in that manifest; otherwise it is transitive.
Named groups are `unknown` by default, not dev-only declarations; no Python `dev`
token can be emitted under #554 even when the census is complete. A
matching extras declaration or supported `[project].dynamic` declaration containing `dependencies` or `optional-dependencies` is `unknown`, never `dev`.
**`requirements.txt` — filename convention:**
SKILL.md § Manifest Scanning only ever collects the literal filename `requirements.txt`;
no `requirements-dev.txt`, `requirements/*.txt`, or other `requirements*.txt` variant is
scanned today. This design classifies exactly what is scanned:
| Pattern | Scope |
|---|---|
| `requirements.txt` | `prod` for directly declared findings; otherwise `unknown` |
A richer filename convention (mapping `requirements-dev.txt`, `requirements/prod*.txt`,
etc. by name) is documented here as a **future extension, not implemented by #554**:
expanding the manifest scan's supported set is a separate decision — it adds manifests,
which adds findings, and under the `advisory` default's severity-based blocking that can
add new blocking findings to runs that pass today. That consequence deserves its own
decision, not a side effect of this classification table.
**`pyproject.toml` — table structure:**
| Table | Scope |
|---|---|
| `[project].dependencies` field (PEP 621) | `prod` |
| `[tool.poetry.dependencies]` (legacy main group) | `prod` |
| `[tool.poetry.group.main.dependencies]` (modern main group) | `prod` |
| `[dependency-groups]` (PEP 735), every named group including `dev`/`production` | `unknown` |
| `[tool.poetry.group.<name>.dependencies]` where `<name> != "main"` | `unknown` |
| `[project.optional-dependencies]` (extras) | `unknown` |
| `[tool.poetry.extras]` (extras) | `unknown` |
A direct dependency in a prod-mapped table is `prod` even if it also appears in
a named group. Otherwise a matching group or extras declaration is `unknown` with
a sanitized reason (group selection does not establish dev-only scope), never `dev`;
a Critical such finding is FIX_NOW and blocks under `strict` (§5–§6). Extras can describe shipped optional features, so the presence of any extras table
in any supported manifest discovered by the bounded census under `checkout_root` blocks all Python `dev` demotions under H4.
**Prod-transitive limitation (H4).** `pip-audit` reports resolved packages without dependency paths, so a named-group package may also be transitive of a production dependency. No group is dev-mapped by default; the following gates remain necessary if a future approved mapping makes a Python token eligible. A `declared-in-dev-manifest` token therefore requires a bounded census with no production-mapped declaration or extras table in any discovered supported manifest, no supported `[project].dynamic` declaration containing `dependencies` or `optional-dependencies`, and no finite-pattern plausible-but-unscanned Python metadata detected within the census traversal. The invocation contract accepts caller-provided canonical `checkout_root` alongside existing `scope_root`; caller supplies root provenance from trusted invocation context, outside checkout-controlled files or commands. The helper refuses a Python `dev` token unless both roots are present and equal; a contribution that would otherwise be `dev` becomes `unknown`, while independently supported `prod` remains `prod`. Missing provenance or subdirectory scope means no demotion (CA-3/R7-06).

Attempt the bounded census whenever Python manifests are in scope. Missing `checkout_root`, an inaccessible root, or an unreadable traversed directory makes census incomplete and refuses demotion; do not fall back to `scope_root`. It never follows symlinks and applies manifest-scan exclusions (`node_modules/`, `.git/`, `target/`, `dist/`, `vendor/`, `third_party/`, `.venv/`, `venv/`). Fixed operational limits: 10,000 filesystem entries inspected (files and directories), 64 MiB aggregate candidate-file bytes, and 10 seconds wall-clock. The byte cap matches §4.1's lockfile-read cap; the other ceilings bound census work. These are fail-closed policy limits, not measured completeness claims; exceeding any only prevents `dev` demotion. Any cap hit also makes census incomplete. It records sorted child-name/type digests for every traversed directory and, for each candidate, its normalized path, detection status, supported-file parse status where applicable, and content digest. Candidates include supported `pyproject.toml`/`requirements.txt` files and finite plausible-unscanned forms (`setup.py`, `setup.cfg`, `Pipfile`, `requirements/*.txt`, `requirements-*.txt`). Parse supported files as data. A supported `pyproject.toml` with `[project].dynamic` containing `dependencies` or `optional-dependencies` is unclassifiable and blocks every Python `dev` token. Read and hash plausible-but-unscanned candidate bytes for recovery integrity, but do not interpret or execute them. Census runs independently of immutable `preflight-audit.md`; that list still controls audit-tool runs. Because `pip-audit` provides no dependency paths, any production-mapped declaration in a supported manifest discovered within the bounded census under `checkout_root` blocks every Python `dev` token, even for unrelated packages. Any discovered extras table, supported `[project].dynamic` declaration containing `dependencies` or `optional-dependencies`, or finite-pattern plausible-but-unscanned Python metadata within that traversal also blocks every Python `dev` token because its scope cannot be ruled out safely. A package declared in both prod and named-group tables of one manifest is `prod`; an extras-only or group-only matching finding is `unknown`. Any detected candidate unreadable, or any supported file unparseable, counts as incomplete, not absent (R5-07). The finite detector can miss novel conventions (R7-08).

Each completed Python ecosystem section stores structured provenance indicating whether classification depended on census and the census digest ID; recovery uses that record—not prior `Reachability:` text—to select sections (R7-11). Recovery re-discovers directory inventories and candidates from the same checkout root with the same exclusions and limits, then recomputes and compares the exact census digest inputs: sorted child-name/type records for every traversed directory; for every detected candidate, normalized path, detection status, supported-file parse status where applicable, and content digest; and aggregate counts. Any difference or failed/limited traversal invalidates the census and the sentinel/findings of every section whose stored metadata says classification depended on it; those sections are fully re-audited. Recovery does not change the audit-tool manifest list. Directory digests detect entry additions, deletions, and renames in traversed directories, including undetected names; candidate digests detect bytes only for selected files. They do not detect content changes to undetected files at unchanged paths, inputs outside traversal, or declarations omitted before baseline census (R7-03/R7-08).
**CA-3 (subdir-scoped audits).** For both npm and Python, demotion tokens are refused unless caller-supplied canonical `scope_root` equals canonical `checkout_root`. The helper never infers checkout root from checkout-controlled commands or files. Missing provenance or subdirectory scope means a would-be `dev` contribution is `unknown` (an independently established `prod` remains `prod`); a partial scan cannot claim repo-wide absence.
**BA-4 (census resource bounds).** Run census on every scan where Python manifests are in scope, including clean repos, with fixed caps of 10,000 filesystem entries inspected (files and directories), 64 MiB aggregate candidate-file bytes, and 10 seconds wall-clock (§4.3). Any cap hit, unreadable traversed directory, or incomplete candidate read means census incomplete and `unknown`, never `dev`.
Name extraction is pinned: the declared dependency name is the leading run of
`[A-Za-z0-9._-]` in each declaration key, read before any extras bracket (`[security]`),
version specifier, or environment marker, then PEP 503-normalized — applied symmetrically
to prod-mapped and named-group tables, so `requests[security]>=2.0; python_version>="3.9"`
matches `requests`. An extractor that yields an empty or malformed set is a probe failure.
No default dev-mapped group exists: name extraction and a group named `dev` cannot mint
a `declared-in-dev-manifest` token. Diagnose group-only matches as `unknown`, not `dev`.
Poetry group `<name>` (from `[tool.poetry.group.<name>.dependencies]`) is rendered into the
token only when the *entire* name is a full match of `[A-Za-z0-9._-]+` (anchored both ends,
`fullmatch` — wording identical to the DEC-9 table's, R6-06); a group name containing any
other character, or a quoted-key embedded newline, makes the finding `unknown` — attacker-
controlled table/group text never reaches the rendered bracket. If a later explicit mapping makes this token usable, its rendered group-name
argument is part of §7.7's by-construction sanitized set (it is text the skill renders that
it did not author), so it passes the printable-ASCII whitelist before rendering.
Extras are `unknown` on purpose: an extra is just as often a shipped optional feature
(`mypackage[postgres]`) as it is a dev convenience (`mypackage[test]`). Guessing would
break DEC-2's fail-safe. The `requirements.txt` / `pyproject.toml` reads use the same
`realpath` containment + per-component symlink refusal + verified-size + bounded-read intake validation (1 MiB per Python manifest, 64 MiB aggregate of Python manifest bytes; an over-cap or short/incomplete read is a probe failure → `unknown` + warning, never `dev`) as
§4.1's lockfile — a hygiene-pinned subcommand of §2's first-party script (R5-01), since
`realpath`/`lstat`/`stat` cannot be done with Read/Glob alone. A path containing any
non-printable-ASCII character (e.g. an embedded newline that could forge a line-start marker)
is refused at intake → `unknown` + warning, never opened, never echoed (R5-05); the per-manifest
read record required by H4's positive-completeness invariant records the refusal as a
**not-successfully-read** manifest (§4.3 H4, R5-07).
**Confidence: low.** The existing *"Confidence: Reduced"* notice pattern is reused: a
Python manifest whose findings are majority-`unknown` gets a stated reachability
confidence in the output, so the reader does not over-trust a `dev` classification that
covers only the direct deps.
### 4.4 Confidence is reported, not just held
Each manifest's output section carries the method and confidence actually used:
```
reachability-method: npm-lockfile-closure        confidence: high for recorded graph only
reachability-method: pyproject-table-structure   confidence: low (direct-only; transitives unknown)
reachability-method: unavailable                 confidence: none (all findings unknown)
```
### 4.5 Empirical verification
Every npm claim in §4 was executed rather than asserted. Environment: npm 11.16.0, on the
machine this design was written on. Python §4.3 is manifest-structure reading with no
subprocess; its classification is pinned by the extraction rule there rather than asserted
from a live run. (The cargo fixtures that previously accompanied §4.2 were removed with the
cargo probe — cargo is now `unknown`, no probe to verify.)
| # | Fixture | Result | Confirms |
|---|---|---|---|
| V1 | `lodash@4.17.20` in **both** `dependencies` and `devDependencies` | lockfile node flagged `"dev": true` | npm's `dev` flag is computed over reachability, not declaration — the false-`dev` hole a bare `--omit=dev` differential opens. Motivates the recorded-lockfile closure walk (§4.1), whose claim is limited to recorded data. |
| V2 | `request@2.88.2` in **both** keys, with vulnerable transitives (`form-data`, `qs`, `tough-cookie`) | lockfile flags **47/47** nodes `dev: true` | The dual-declaration mis-flags the whole subtree; walking the lockfile graph (not trusting the flag) keeps the subtree `prod`. Motivates the closure walk |
| V3 | `react-dom@18.3.1` in **both** keys, with `react` as its auto-installed peer (`peer: true`) | `react` is reached only via `react-dom`'s `peerDependencies`, not its `dependencies` | The closure must traverse `peerDependencies`, or an auto-installed peer of a dual-declared prod dep is silently demoted |
| V4 | lockfileVersion-3 nodes, aliased vs non-aliased (`"logger": "npm:itoa@1"` vs plain `request`) | alias node carries `name`; non-aliased node carries **no** `name` (name lives only in the map key) | `node.get('name')` is `None` for every non-aliased node → empty closure. Motivates the field-or-key-suffix rule + empty-closure guard in §4.1 |
| V5 | aliased `"logger": "npm:underscore@1.12.1"` with lock node `node_modules/logger` carrying `name: "underscore"`; `npm audit --json` on npm 11.16.0 | the finding is reported under the **resolved** name `underscore` (the lock node's `name`), while its `nodes` field carries the alias installation path `node_modules/logger` | the finding side must be matched on lock-node **resolved** names, never the declaration alias key or the node-path suffix; §4.1's name-match floor turns any name-mismatched finding into `unknown`, never `dev` (S9/R-3) |
V1–V5 are the findings that shaped §4.1. All are false-`dev` downgrades — the one direction
§9.1 forbids; none was visible from reading tool documentation alone.
## 5. The triage tree
Six rows, because the ticket's four have a hole in them.
| Severity | Scope | Bucket |
|---|---|---|
| Critical / High | `prod` or `unknown` | **FIX_NOW** |
| Critical / High | `dev` | **FIX_NEXT_CYCLE** |
| Moderate | `prod` or `unknown` | **FIX_NEXT_CYCLE** |
| Moderate | `dev` | **DEFER_TRACK** |
| Low | any | **TRACK_ONLY** |
| Informational | any | **TRACK_ONLY** |
**DEC-4 — filling the ticket's hole.** #554's proposed tree lists Critical/High +
reachable, Moderate + prod, Moderate + dev, and Low. It never says what
**Critical/High + dev-only** is; that case falls through the tree as written. It is
assigned **FIX_NEXT_CYCLE**, not DEFER_TRACK: a Critical in a dev or build-time
dependency is still a live supply-chain risk — build-time arbitrary code execution and
CI credential theft are exactly how `event-stream` and `ua-parser-js` did damage, and
neither needed to reach production. It is not drop-everything, but it is not
"defer and track" either.
Existing severity rules flow into the tree unchanged:
- `[no-cvss]` findings are already normalized to **Moderate**; they enter the tree as
  Moderate and carry the `[no-cvss]` flag through.
- **Informational** (CVSS 0.0) already never counts toward blocking. It maps to
  TRACK_ONLY, which never blocks under either gating mode — no behavior change.
## 6. Blocking semantics
**DEC-5:** New skill argument **`reachability_gating`** (string, default `"advisory"`,
case-insensitive; accepted: `"advisory"`, `"strict"`; invalid values rejected before
execution, matching how `min_blocking_severity` validates today).
### `advisory` (default) — no behavior change
Triage classification is computed, reported, and used to group and order the output.
**Blocking is exactly today's rule**: any finding at or above `min_blocking_severity`
blocks, regardless of bucket.
This matters. Today a Critical dev-only CVE blocks. If the tree became authoritative by
default, every existing `/build`, `/quality-gate`-sibling and CI caller would silently
stop blocking on that finding the day this ships — a gate weakening nobody asked for,
delivered as a docs change. The default must not move.
### `strict` — the ticket's tree, opted into
**A finding blocks iff its bucket is FIX_NOW.** Under `strict`,
`min_blocking_severity` is **inert** — the tree is the authority, exactly as
`skip_blocking` supersedes `min_blocking_severity` today rather than composing with it.
Consequences, stated plainly because they cut both ways:
- **Escalation:** `High` + `prod` blocks under `strict` even at the default
  `critical` threshold. Today it does not.
- **De-escalation:** `Critical` + `dev` does NOT block under `strict`. Today it does.
- **De-escalation:** with `min_blocking_severity: moderate`, `strict` blocks *less* than
  `advisory` (a Moderate + prod finding is FIX_NEXT_CYCLE, which does not block).
**Trust warning (binding under `strict`).** `strict` makes *scope* the blocking authority,
and scope is derived from the **untrusted** manifest (§2). A checkout that lies about its
own scope — a Critical production dependency declared under `devDependencies`, or a shipped
transitive hidden from the closure walk — will not block under `strict` where `advisory`
still would. Choosing `strict` opts into *trusting the manifest's scope claims*; it is a
triage-mode convenience, not a stronger security boundary. When `strict` is active,
`audit-results.md` carries a one-line statement of that limitation.
**DEC-6:** Because that last case is genuinely surprising, setting `strict` together
with a non-default `min_blocking_severity` emits a warning into `audit-results.md`:
`min_blocking_severity is inert under reachability_gating: strict — the triage tree is
authoritative`. It is a warning, not an error: the combination is legal and the run
proceeds.
### Precedence, mode-conditional
`skip_blocking: true` still supersedes everything, including `strict`. The precedence is
**mode-conditional**, because under `advisory` `reachability_gating` has no blocking
effect at all (`min_blocking_severity` is the sole authority — DEC-5 and failure mode 5
require a caller that did not opt in to see exactly today's behavior):
```
strict:    skip_blocking  >  reachability_gating (triage tree)  >  min_blocking_severity (inert)
advisory:  skip_blocking  >  min_blocking_severity               # byte-for-byte today's chain
```
The `advisory` chain is byte-for-byte today's; it has no `reachability_gating` term
because that mode never consults it for blocking.
### Result vocabulary is untouched
`CLEAN | FINDINGS | BLOCKED | INCONCLUSIVE | FAILED` gains no new member. Parent
orchestrators (`build`'s gate ledger, `/quality-gate`'s sibling-signal integration)
parse that field; adding a state would break them for no gain. A reachability probe
failure, including the all-scanned-npm-scope demotion gate (§4.1), surfaces as a warning plus `unknown` for would-be `dev`, not as a new result. Under `strict`, Critical/High `unknown` enters FIX_NOW; existing overall-result precedence for skipped/failed audits remains unchanged.
## 7. Output model changes
### 7.1 Per-finding fields
Each finding gains two fields:
```
Reachability: prod
Reachability: dev [<demotion-token>(, <demotion-token>)*]   # token(s) REQUIRED — see DEC-9
Reachability: unknown [<free-text reason>]
Triage: FIX_NOW | FIX_NEXT_CYCLE | DEFER_TRACK | TRACK_ONLY
```
A `dev` finding carries **one token per contributing source** (§3.1), only after the all-scanned-npm-scope gate (§4.1); when more than one,
they are rendered comma-space separated, sorted, in a single bracket. A `dev` line
without a bracketed token from DEC-9's closed set is malformed; the finding is emitted as
`unknown` instead. Concrete example (single contributing source, a non-exempt `dev`
classification the structural checker asserts against):
```
Reachability: dev [absent-from-prod-closure]
```
### 7.2 A `## Triage` section
`audit-results.md` gains a triage section that groups the deduplicated findings by
bucket, in urgency order. This is the section that answers "what do I do now?" — the
thing the flat severity list could not.
```markdown
## Triage
FIX_NOW (2)
- lodash 4.17.20 — CVE-2021-23337 — Critical — prod — fix available: 4.17.21
- axios 0.21.0 — CVE-2020-28168 — High — unknown — fix available: 0.21.1
FIX_NEXT_CYCLE (1)
- webpack-dev-server 3.11.0 — CVE-2021-XXXXX — Critical — dev [absent-from-prod-closure] — fix available: 4.0.0
DEFER_TRACK (1)
- eslint-plugin-x 1.0.0 — CVE-2022-XXXXX — Moderate — dev [absent-from-prod-closure] — no fix available
TRACK_ONLY (3)
- [3 Low/Informational findings]
```
When a deduplicated finding is `dev` under more than one contributing source, the demotion
tokens are rendered comma-space separated, sorted, in a single bracket — e.g.
`dev [absent-from-prod-closure, absent-from-prod-closure]` for one package reported by two npm
roots.
### 7.3 Summary line
The existing severity counts stay (they are the raw signal). One triage line is added
beside them:
```
Result: CLEAN | FINDINGS | BLOCKED | INCONCLUSIVE | FAILED
Critical: N  High: N  Moderate: N  Low: N  Informational: N
Triage: FIX_NOW: N  FIX_NEXT_CYCLE: N  DEFER_TRACK: N  TRACK_ONLY: N
Reachability: prod: N  dev: N  unknown: N   (gating: advisory | strict)
```
When npm coverage is incomplete, add a sanitized warning identifying skipped/failed recorded scope(s); count blocked demotions under `unknown` and derive global triage from effective merged values (§4.1).
### 7.4 The interactive prompt
Today the blocking prompt groups by fix availability ("Fixable (N)" / "No fix available
(M)"). Under `advisory` (the default), the top-level grouping stays **what is blocking
now**: a "Blocking now (severity ≥ `min_blocking_severity`)" group and a "Reported, not
blocking" group, each still split by fix availability within it. The triage bucket is
rendered as a per-finding annotation inside those groups, not as the top-level heading —
under `advisory`, blocking is severity-based (§6), so a bucket like FIX_NEXT_CYCLE can
head a finding that is, in fact, actively blocking this run. Presenting it under that
heading at the exact moment an operator is deciding whether to continue would tell them
the thing that just stopped them is next-cycle work — the same anti-overclaim standard
DEC-1 applies to "runtime-reachable".
Under `strict`, bucket **is** the top-level grouping, replacing the "blocking now" split:
FIX_NOW and "blocking" are the same set by definition there, so grouping by bucket first
is also grouping by blocking status first, with fix availability as the tiebreak inside
each bucket. The existing rationale for the fix-availability grouping is preserved, not
replaced, at the inner level in both modes.
### 7.5 `preflight-audit.md` stays the immutable scan-time record
Reachability is discovered at execution time, so it lands in `audit-results.md`, matching existing tool-availability output. npm production seeds come from root and workspace-member `package.json` paths found by the audit's on-disk manifest scan and recorded in immutable `preflight-audit.md`. Lockfile `packages` keys resolve those seeds and edges only; they do not define workspace membership. Do not infer membership from lockfile layout or invent a lockfile "members table" (R6-02/R7-01). This same-checkout list does not prove a workspace manifest was not omitted before the scan (R7-02). The immutable audit manifest list still controls which manifests receive audit-tool runs. Record outcome and required-input validity for every npm scope in that scan, including skipped/failed scopes; §4.1 gates npm demotion across this recorded set only.
### 7.6 Compaction recovery
**Distinct lifecycles.** A genuine new audit creates/truncates machine-local
`audit-results.md` before manifest scanning and immutable preflight creation. A compaction
resume requires matching run identity and validated existing immutable `preflight-audit.md`;
it opens existing output without truncation and never changes the audit-tool manifest list.
Missing/malformed/mismatched identity or preflight cannot resume: discard old output and
start a fresh audit before scan, or fail closed if a safe new run cannot start. On resume,
validate structured section provenance, sentinel, stored input digests, root values, and
census dependencies before retention. Missing/malformed provenance, incomplete sections,
or changed/failed inputs discard affected sentinel/findings and require full audit and
classifier rerun; invalid run-global npm coverage records invalidate npm demotion-dependent
sections (§4.1). Retain complete unchanged sections other than environment-backed
`pyproject.toml` without rerun. Never re-adopt rendered
`Reachability:`/`Triage:` prose. After all sections finish, regenerate `## Summary` and
`## Triage` globally from retained and re-audited findings, replacing old global sections.
The `status: complete` sentinel per ecosystem section also covers reachability classification: a section is complete only after findings and triage are written. **Recovery re-derives, never re-adopts:** invalidate the sentinel and retained findings for every section whose recorded input digest differs or whose stored census dependency references an invalid census. Re-run the audit and classifier for each invalidated section; never parse prior `Reachability:`/`Triage:` text as authoritative. A digest-matching section remains complete and is not reprocessed **except** an environment-backed `pyproject.toml` section (the sentinel gates other reprocessing; R6-03).

Each completed ecosystem section stores digests of its classification inputs beside the sentinel. Store canonical `scope_root` and the caller-provided canonical `checkout_root` value (or explicit `missing`) in the run input record and bind both values into the classification-input digest; recovery compares them with current caller inputs, and a changed or missing root invalidates demotion-dependent sections. npm inputs are selected lockfile (`package-lock.json` or preferred `npm-shrinkwrap.json`) and the scanned root/workspace `package.json` files. Python section metadata stores whether classification used the run-global census and its digest ID; per-candidate inputs are covered by that census digest. `pip-audit --format json` for `pyproject.toml` audits the installed environment, not the manifest alone: manifest, census, or lockfile digests cannot certify that environment. On every compaction resume unconditionally invalidate every completed environment-backed `pyproject.toml` section, discard its sentinel and all old findings, re-run its audit and classifier, then write only the new section findings. Other complete sections whose actual audit and classification inputs match may be retained; re-derive global dedup/Summary/Triage from retained plus new sections, never aggregate stale environment findings. Any direct input mismatch invalidates that section and forces a full re-audit: probe reruns, findings are re-derived, prior findings are discarded, and `status: complete` stays absent until completion. A stale Critical is never reclassified against changed input. Digest computation uses the hygiene-pinned first-party script (R5-01).

**Run-global census-input digest (R6-03/R7-03).** The census records sorted child-name/type digests for every traversed directory and, for every candidate path matched by the finite detector in §4.3, its normalized path, detector class (`supported` or `plausible-unscanned`), supported-file parse status where applicable, and content digest, plus aggregate counts. An unreadable candidate or incomplete read marks census incomplete; it is never recorded as absent. Directory digests detect entry additions, deletions, and renames within the bounded traversal; candidate digests detect content changes only in selected files. The finite detector does not prove that no other production declaration exists (R7-08). On recovery, rediscover the directory inventories and candidates from caller-provided canonical `checkout_root`, using §4.3's exclusions, symlink policy, bounds, and validation, independently of immutable `preflight-audit.md`; recompute the same canonical digest from the sorted directory records, candidate path/status/content records, and aggregate counts, then compare it to the stored digest. Any difference or failed/limited traversal invalidates the census and the sentinel/findings of every section whose stored metadata says classification depended on it; those sections are fully re-audited. Recovery does not change the audit-tool manifest list. This detects changes to observed tree entries and selected candidate bytes, not truth, content changes in undetected files at unchanged paths, inputs outside traversal, or declarations omitted before baseline census (R7-03/R7-08). The finite detector may miss novel conventions (R7-08); census absence gates recovery only when re-discovered directory and candidate digests match.
**Recovery gate.** Re-run the audit and classification for any incomplete section or section invalidated by missing/malformed provenance, changed inputs, invalid npm coverage, or a census-digest mismatch, and for every environment-backed `pyproject.toml` section on every resume even when its digests match. Retain only other complete sections with valid structured provenance and matching digests; regenerate global Summary/Triage (§7.6).
**Digest-record grammar (R6-05).** Each digest record uses a fixed, unambiguous grammar in
which the path cannot occupy a structural position: `sha256:<hex> : <path>` — digest
lexeme, then `: `, then the path — with the hex fixed-length (64 chars) acting as the
delimited field. A printable-ASCII path may not inject a `: ` lexeme at line start because
the line's first token is forced to `sha256:`; a digest line whose first token is not
`sha256:` is malformed and fails recovery fast (§7.7 marker-integrity applies to *all*
structural positions rendered from checkout-controlled text, not only line terminators —
R6-05 closes the §7.6 quoting gap).
**`audit-results.md` is written outside the checkout.** Its write path is a
machine-local scratch location the untrusted checkout cannot pre-seed; only a genuinely new
run truncates it before scanning; compaction resume preserves it pending validation and
never appends stale sections or accepts checkout-supplied output (§7.6).
`## Triage`, like `## Summary`, is derived **global** state — it groups deduplicated findings
across every manifest and cannot be correct until all manifests have completed. Both are
regenerated wholesale after all manifests complete, and any existing `## Triage` section is
discarded rather than appended to on recovery, exactly as `## Summary` already is.
### 7.7 Untrusted content in `audit-results.md`
`audit-results.md` is read as structured context by downstream consumers (notably `build`'s
gate ledger), and its per-finding fields carry **attacker-controlled text**: package names,
versions, advisory titles, CVE IDs, and the `unknown` free-text reason come straight from the
audited repository and the advisory databases. Every rendering of these values — the
`audit-results.md` write AND the interactive blocking prompt (§7.4) — applies the same two
rules, and the sanitization scope is **by construction, not by enumeration (R5-05)**: sanitize
**everything this skill renders that it did not author itself** — packages names, versions,
advisory titles, CVE IDs, the `unknown` free-text reason, **and every path** (the per-manifest
sections §4.4/§4.3 identify by path, §7.6's per-section digest records identify by path). A
path is just as checkout-controlled as a version string; the §4.1/§4.3 intake already refuses
non-printable-ASCII paths so a newline-bearing path cannot reach rendering, and this rule
covers any remaining path class without naming each one:
- **Sanitize every attacker-controlled value** to a **printable-ASCII whitelist** (U+0020–U+007E),
  replacing every other character with a single space. That drops not only U+0000–U+001F and
  U+007F but also the Unicode line/paragraph separators U+0085 (NEL), U+2028 (LS), U+2029 (PS)
  that still split on `splitlines()` — so no character that can terminate a line survives, a
  value cannot break out of its field, and no ANSI/CSI escape can repaint the prompt.
- **Structural markers are line-start-anchored with closed-set values.** `status: complete`,
  `Reachability:`, and `Triage:` are recognized **only** when they begin a line. Their values
  are closed-set for the markers that have a fixed alphabet (`status: complete` verbatim;
  `Triage:` one of the four buckets (`FIX_NOW | FIX_NEXT_CYCLE | DEFER_TRACK | TRACK_ONLY`, §7.1); a `dev` `Reachability:` value a DEC-9 token). The one
  free-text value — `unknown`'s bracketed reason — is permitted **only because it is
  whitelist-sanitized** (no line terminator survives), so it cannot forge a line-start marker
  despite being drawn from no closed set (R5-05's marker-integrity point). Attacker-controlled
  text is rendered *inside* a finding's
  own field, never at a marker's line-start, so `… Reachability: dev […]` forged mid-field is
  inert: the reader does not treat it as a marker.
This keeps the "Result vocabulary is untouched" promise at the parser level while making the
per-finding fields, the extended sentinel, and the prompt safe against hostile input.
**Downstream-reader contract (CA-2).** The line-start + closed-set marker convention of this section is the contract for *every* reader that interprets `audit-results.md` structurally — including the downstream consumer §7.7 names, `build`'s gate ledger. `build` consumes the `Result:` line only (per §7.3 the vocabulary is unchanged), so hostile `Reachability:`/`Triage:`/`status: complete` text inside a finding field is inert for it; any *other* reader that parses per-finding `Reachability:`/`Triage:` values must apply the same line-start-anchored first-token matching this section specifies, or state its own. The artifact does not extend the line-anchoring convention to readers that do not adopt it; a reader that substring-scans a finding field for `Triage:` is outside this contract and is told so. This reservation belongs to the §8 table row for Output Model, so it is not silently assumed.
## 8. Where this lands in the skill
| SKILL.md section | Change |
|---|---|
| `## Skill Arguments` | add `reachability_gating` and optional caller-supplied canonical `checkout_root` provenance. Missing or unequal provenance refuses npm/Python `dev` demotion; audits continue, and contributions otherwise classified `dev` become `unknown` (supported `prod` stays `prod`). Standalone callers must pass it explicitly to permit demotion. Existing parent callers must not infer it from cwd or checkout data; unless a parent supplies trusted invocation-root provenance, no demotion occurs. Standalone invocations must provide it explicitly to permit demotion. Parent plumbing is not assumed to exist today. |
| `## Ecosystem Detection and Ordering` | note the conditional prod-closure walk (`npm`) |
| new `## Runtime Reachability Classification` | the model, the non-goal, per-ecosystem method, the DEC-9 demotion-token set and recorded-graph completeness rule, placement-aware npm resolution and the all-scanned-npm-scope gate (§4.1), Python named groups unknown by default and dynamic extras blocker (§4.3), npm lockfile-closure method (replacing DEC-7), merge rule, confidence reporting |
| new `## Triage Tree` | the six-row table + DEC-4 rationale |
| `## Overall Result Computation` | restate the BLOCKED row's condition as *at or above `min_blocking_severity`* (advisory) *or bucket == FIX_NOW* (strict), `skip_blocking` false; precedence order otherwise unchanged |
| `## Blocking and Prompting Behavior` | mode-conditional precedence, the `strict` mode, the DEC-6 warning, the DEC-5 trust warning, bucket-first prompt grouping under `strict` only |
| `## Output Model` | per-finding fields (multi-token rendering), `## Triage` section (global derived state), summary lines, `audit-results.md` sanitization (§7.7) + the downstream-reader contract (§7.7, CA-2) |
| new `## Trust Boundary` | the untrusted-checkout model, scope-as-triage-aid-not-boundary, no-new-subprocess (reads only), bounded validated reads, output sanitization |
| `## Compaction Recovery` | fresh-run truncation before scan versus validated same-run resume without truncation; structured provenance/digest validation retains other unchanged sections, always reruns environment-backed `pyproject.toml` sections and invalid/dependent sections, then regenerates global `## Summary` and `## Triage` |
| `## Red Flags` | add the failure modes in §9 |
| `description` frontmatter | **unchanged** — routing must not shift (see §10) |
`skills/quality-gate/SKILL.md` carries a **verbatim duplicate** of the Compaction Recovery
paragraph ("regenerate the Summary section ..."). It must be updated in the same change to
say Summary **and** Triage, or it becomes canonical drift and a recovering `quality-gate`
agent leaves a stale `## Triage` in place.
## 9. Failure modes this design must not have
These become Red Flags in the skill:
1. **Silent downgrade on a failed classification.** A malformed lockfile, an empty
   closure despite recorded production declarations, an unresolved production seed, a resource-bound trip, or a closure-walk subprocess that is killed, times out, or exits non-zero must never make findings `dev`. It makes them `unknown`, which triages
   as `prod`. An empty closure with no recorded production declarations is valid and may mint
   `absent-from-prod-closure` when all other gates pass (eval 1b).
2. **Claiming call-graph reachability.** Reporting `prod` as "the vulnerable code
   runs". It means the package is in the production closure. Nothing more.
3. **Letting a Python direct-dep classification imply the transitives were checked.**
   Transitive findings are `unknown` and say so.
4. **Treating `unknown` as `dev` in the merge.** `prod > unknown > dev`, always.
5. **Moving the default.** `advisory` is the default; a caller that did not opt in must
   see exactly today's blocking behavior.
6. **A probe that exits 0 but returns nothing useful.** Truncated JSON, an empty crate
   list, a shifted output format — none of these trip an exit-code check, and all of
   them would otherwise classify every finding `dev`. DEC-9's token rule catches them:
   no parseable probe output means no token, and no token means `unknown`.
7. **Minting a `dev` classification by reasoning rather than by probe.** "This is
   obviously a lint plugin" is not a token. Only the two demotion tokens in DEC-9's table
   produce one.
8. **Incomplete recorded-graph walk.** A parser that omits a supported recorded edge,
   fails to resolve a recorded production seed, or derives an invalid package name must
   return `unknown`, not mint a demotion token. This catches implementation omissions in
   declared data only; it cannot detect manifests or edges omitted before the run
   (R7-02/R7-05).
9. **Reintroducing a checkout-steerable subprocess probe.** A `cargo tree`/`cargo metadata`
   (or any non-first-party) subprocess run in an untrusted checkout re-opens the code-execution
   surface §4.2 deliberately closed; a probe that requires a checkout-steerable subprocess is
   refused → `unknown`. This does **not** forbid the design's own sanctioned
   first-party invocations — the §2 hygiene-pinned `python3 -I <absolute-path>` subcommands
   (closure walk, path-validation helper, digest computation) — which are the skill's own
   code reading untrusted *data*, not a probe the checkout can steer (R5-01).
10. **Treating scope classification as a security boundary.** The prod/dev split is derived
    entirely from the untrusted manifest and can be lied about (§2's trust boundary); under
    `strict` that lie becomes a blocking decision, which DEC-5's warning names. The demotion
    source is the manifest's own declaration, and the fail-safes that catch a *mis-resolving*
    walk do not catch a checkout that lies about scope, nor a path-less `pip-audit` mapping a
    prod-transitive to `dev`.
## 10. Routing / frontmatter
The `description` frontmatter is the skill's auto-activation trigger. This change adds
capability *inside* the skill, not a new trigger surface — `/dependency-audit`, "audit
dependencies", "scan vulnerabilities", "check CVEs" all still route here and there is no
new phrase that should route here instead of to `siege` or `audit`. **The description is
left byte-identical**, per this repo's rule that changing it changes routing.
## 11. Evals
`skills/dependency-audit/evals/` does not exist today; this creates it with
`evals.json` in the standard shape (`skill_name`, `evals[]` with `id`, `prompt`,
`expected_output`, `files`, `expectations`). Coverage, one eval per load-bearing
decision:
| # | Covers | Asserts |
|---|---|---|
| 1 | npm lockfile closure, mixed prod/dev findings, default gating | Correct buckets per row; Critical dev-only lands FIX_NEXT_CYCLE; blocking is *unchanged* from today (DEC-5 advisory default) |
| 1b | npm **dev-only** manifest (zero prod deps; a vulnerable `devDependencies` package) | The closure is legitimately empty; the finding classifies `dev [absent-from-prod-closure]` with **no** probe-failed warning (the empty-closure guard's re-conditioned path, not the defective-probe path) |
| 2 | `reachability_gating: strict` | High + prod now BLOCKS; Critical + dev does NOT; the DEC-6 inert-`min_blocking_severity` warning fires |
| 3 | Python transitive finding | Classified `unknown`, triaged as `prod`, never silently `dev`; reduced-confidence notice present (DEC-3) |
| 4 | npm lockfile that is malformed / unparseable while findings are non-empty | All that manifest's findings become `unknown` + warning — NOT `dev`; no token can be minted (the empty-closure + resource-bound guards); `Result:` vocabulary unchanged |
| 4b | npm closure walk yields an empty closure in a manifest whose `package.json` declares prod deps | Probe defective → `unknown` + warning; no downgrade (the empty-closure guard's cross-check branch) |
| 5 | Non-overclaim | Output describes scope, not executed code; a request to report "which vulnerable functions are actually called" is answered with the explicit non-goal rather than a fabricated call-graph claim (DEC-1) |
| 6 | npm package declared in **both** `dependencies` and `devDependencies` **with a vulnerable transitive, an auto-installed peer, and an alias** (V2/V3/V4 fixtures) | The dual-declared package, its transitive subtree **and its peer** classify `prod` via the lockfile-closure walk (dep+optional+peer edges), not `dev`; an npm alias (`"logger": "npm:winston@3.8.0"`) and a non-aliased node both resolve to their **single canonical name space** — the resolved name `winston`/`request` on **both** the closure side and the finding side (R5-02); a lock node whose `name` disagrees with its key suffix without a matching direct or transitive incoming `npm:` alias target is rejected → `unknown`; an empty closure with non-empty findings is a probe failure → `unknown` |
| 6a | nested npm alias: prod lock node has `"logger": "npm:winston@3.8.0"` and `node_modules/prod/node_modules/logger` has `name: "winston"`; variants have absent, malformed, or mismatched incoming target | Valid edge traverses and vulnerable `winston` is `prod`; invalid alias fails closed to `unknown` + warning, never a `dev` token; a finding name that matches no lock-node resolved name in its scope yields `unknown` + warning, never `dev` (name-match floor, S9/R-3) (§4.1) |
| 6b | an `apps/web`-style monorepo (`workspaces: ["apps/*"]`, vulnerable prod dep declared only in `apps/web/package.json`, one unrelated root prod dep) | Membership comes from the **audit's on-disk manifest scan**, so `apps/web/package.json` (found on disk, no literal `packages/` prefix needed) is a member and its dep enters the closure — `prod`, not `dev [absent-from-prod-closure]`; workspace membership comes from scanned manifest paths, not lockfile keys; deleting only a lock key cannot rewrite that scan result (R6-02). This same-checkout consistency is not proof that a member was not omitted before scan (R7-02) |
| 6c | npm dual-declared subtree, single lockfile-edge deletion (V2 fixture, R6-01) | Demonstrate R7-05: edge pruning in a non-empty graph can mint `dev [absent-from-prod-closure]`. This is an accepted false-demotion residual, not desired behavior; disclose it explicitly, alongside omitted-manifest R7-02. Do not claim that recorded-graph completeness proves true production scope. |
| 6d | Python repo with a `setup.py` (or `Pipfile`/`requirements/*.txt`) and a named-group dep | Census detects plausible-but-unscanned metadata and refuses token → `unknown` (R6-04); named groups remain `unknown` even with complete census; a subdir-scoped audit or invocation without trusted `checkout_root` cannot permit demotion (CA-3/R7-06) | 
| 6f | two independent recorded npm roots: first has eligible Critical dev `x`; second declares prod `x` but is skipped for missing lockfile or audit error; repeat with failed second root and no overlapping declaration | No npm `dev` token in either case; `x` is `unknown` unless independently established `prod`; sanitized unavailable-coverage warning, strict FIX_NOW and blocking where existing result precedence permits, without changing skipped/error overall-result precedence (§4.1/§6) |
| 6g | Python named-group finding with `[project].dynamic = ["optional-dependencies"]` and no static extras table | Finding `unknown`, never `dev`; census dynamic blocker remains binding if explicit dev-only mapping is later approved (§4.3) |
| 6h | same-run compaction recovery with one complete unchanged `requirements.txt` section and one changed-input npm section | No truncation; validated provenance/digest retains unchanged requirements section without re-audit, discards and re-audits changed npm section, regenerates global Summary/Triage; missing/malformed provenance fails closed (§7.6). Environment-backed pyproject sections are never retained (6l). |
| 6e | Recovery after a clean prod `requirements.txt` is added, deleted, renamed, or modified across the compaction window | Directory-entry digest, candidate-set/status/content digest, or census count mismatches; invalidate census-dependent sections and fully re-audit them. The retained Critical is not silently reclassified `dev` (R6-03/R7-03) | 
| 7 | Untokened `dev` | A `dev` classification presented without a DEC-9 token is emitted as `unknown` and triaged as `prod` |
| 8 | Same (package, CVE) reported by **two sources with divergent scopes** (`requirements.txt` prod + a `pyproject.toml` named group) | The merged finding is `prod` (most-urgent wins); the dedup note lists both per-source values — the `requirements.txt` source as `prod` and the named-group `pyproject.toml` source as `unknown` (not dev-only). Two group-only sources both remain `unknown` without tokens, even with a complete bounded census; disclose finite detector limits (R7-08). |
| 6i | `strict`, only `[dependency-groups]` group `production` (and Poetry non-main `production`) declaring a Critical package, clean census and equal roots | Each group-only contribution is `unknown` with no Python `dev` token; Critical is FIX_NOW and blocks. Group name `dev` is equally not proof of dev-only scope (S1). |
| 6j | root `dependencies.x` with only `node_modules/dev-tool/node_modules/x` in lockfile; control adds correctly placed `node_modules/x`; transitive nested alias edge uses ancestor lookup | Wrong nested node cannot satisfy root seed; failed placement means `unknown` and no npm `dev` token even when other closure nodes exist. Correct placement traverses actual production `x` and its recorded edges; alias matching uses selected incoming edge (S2). |
| 6k | non-empty npm prod closure with a scanned workspace `package.json` larger than 1 MiB, or aggregate manifests larger than 64 MiB | Both caps fail the normal closure walk to `unknown` + warning with no npm `dev` token, regardless of small valid lockfile (S3). |
| 6l | compaction changes active Python virtualenv between completed `pyproject.toml` audit and resume, leaving manifest/census bytes identical; `requirements.txt` section unchanged | Always discard and re-audit environment-backed `pyproject.toml`; retain unchanged requirements section; new pyproject results replace old and global dedup/Summary/Triage regenerated without stale findings (S4). |
| 6m | a root npm scope plus an independent lockfile-less sub-project manifest (`vendor/tool/package.json`) not matched by any root `workspaces` pattern | The unmatched manifest forms its own scope, seeded and gated like the root; its missing lockfile is a skipped scope that blocks all npm `dev` tokens via the all-scanned-npm-scope gate — no scanned manifest is ever dropped from seeding or gating regardless of `workspaces` edits (S1/R-2) |
Per this repo's *Eval before you publish* rule, these twenty-three cases run before the PR.
Prompt evals check user-visible behavior; they do not replace the runtime code-path test
required by AC-14.
## 12. Acceptance criteria
1. `skills/dependency-audit/SKILL.md` documents the three-state reachability model, the
   per-ecosystem determination method, the merge rule, and the six-row triage tree.
2. The explicit non-goal (no call-graph reachability) is stated in the skill itself.
3. `reachability_gating` is documented with `advisory` as the default and `strict` fully
   specified, including the precedence chain and the DEC-6 warning.
4. `audit-results.md`'s schema shows the per-finding `Reachability:`/`Triage:` fields,
   the `## Triage` section, and the Summary triage/reachability lines.
5. The `description` frontmatter is byte-identical to before.
6. Every new `.md` under `skills/dependency-audit/` carries the standalone
   `<!-- MODEL-TIER: security-hard-out -->` marker (`scripts/check_model_pins.py`
   dir-allowlist requires it for *every* `.md` in this directory, pin or no pin).
7. `skills/dependency-audit/evals/evals.json` exists and covers all twenty-three cases in §11
   (1, 1b, 2, 3, 4, 4b, 5, 6, 6a, 6b, 6c, 6d, 6e, 6f, 6g, 6h, 6i, 6j, 6k, 6l, 6m, 7, 8).
8. The DEC-9 demotion-token set is documented as a closed set, the §3.0 recorded-graph completeness rule is
    stated, including the distinction between an empty closure with recorded production declarations (`unknown`)
    and a valid empty closure with none (eligible for `dev` only under §4.1 and all other DEC-9 gates); the
    structural checker pins both branches. The untokened-`dev`→`unknown` rule is stated, and every `Reachability: dev`
    example in the skill carries a bracketed token **from the set** — with at least one
    **non-exempt** concrete `Reachability: dev [<token>]` example pinned in §7.1 so the
    check is not vacuous (the Output Model schema line, being a template, is the one
    documented exemption).
9. A structural checker enforces these invariants, wired into `scripts/run_tests.sh`
    (`bash scripts/run_tests.sh` is green): the DEC-9 token set is present and closed; the
    untokened-`dev`→`unknown` rule is present; the §3.0 recorded-graph completeness rule is present; every
    `Reachability: dev` example carries a bracketed token from the set, matching **both**
    renderings — the per-finding field form `Reachability: dev [<token>]` and the triage
    column form `— dev [<token>] —` — scoped to lines beginning with `Reachability:` or
    `- `, with the single Output Model schema-template line exempt and at least one
    non-exempt positive asserted (AC-8); `reachability_gating` defaults
    to `advisory` (AC-3) and its precedence is mode-conditional — under `advisory` the
    chain is byte-for-byte today's (SP1); the `description` frontmatter is byte-identical
    (AC-5). Prose-shaped
    invariants are pinned via `CONTRACT:` anchors per `scripts/CHECKER_CONVENTIONS.md`
    rather than verbatim English; the checker is stdlib-only, exits 0 clean / 1 with a
    `- <error>` list, ships a `--selftest`, and gets both lines in `scripts/run_tests.sh`,
    matching the existing `check_*.py` shape.
10. `python3 scripts/catalog.py check` and `python3 scripts/check_crossref.py` pass.
11. The `## Compaction Recovery` change is routed and complete: §8 lists it; fresh runs truncate output before scanning, validated same-run compaction resumes
    do not truncate and retain only complete sections with valid structured provenance
    and matching digests; invalid/incomplete/dependent sections are re-audited; the recovery
    step always re-audits environment-backed `pyproject.toml` sections even with matching
    declaration/census digests (which cannot certify the installed environment) and
    regenerates `## Summary` **and** `## Triage`, discarding any existing `## Triage`
    rather than appending; and `skills/quality-gate/SKILL.md`'s duplicated recovery
    paragraph is updated in the same change (else canonical drift).
12. Trust and recovery contracts are stated: scope is declaration-faithful and not a security boundary; no checkout-steerable subprocess is added; callers may pass canonical `checkout_root` provenance from trusted invocation context alongside `scope_root`; missing or unequal provenance blocks demotion, and existing parent callers are not assumed to provide it; each first-party interpreter invocation uses the hygiene invariant; bounded fd-based reads and sanitization apply as specified. The npm closure walk enforces separate 64-MiB lockfile and 1-MiB-per-`package.json`/64-MiB-aggregate manifest ceilings plus a fixed 1,000,000-node/1,000,000-edge ceiling and a fixed 60-second wall-clock subprocess timeout, including non-empty closure paths; unsupported or missing placed seeds/edges and any cap/timeout trip refuse demotion, and a non-zero exit, signal, or timeout of the pinned closure-walk subcommand trips the all-scope npm gate for every recorded scope (R-4), not only the affected scope. PEP 735 and non-main Poetry groups are `unknown` by default, irrespective of group name. Python demotion requires a successful bounded checkout-root census, no production-mapped declaration or extras table in discovered supported manifests, no supported `[project].dynamic` declaration containing `dependencies` or `optional-dependencies`, and no finite-pattern plausible-but-unscanned Python metadata detected within census traversal. Unreadable candidates, unparseable supported manifests, and unsupported declaration syntax refuse demotion. Census exclusions and fixed 10,000-entry/64-MiB/10-second bounds are explicit; the §4.3 Python manifest reads cap each `requirements.txt`/`pyproject.toml` at 1 MiB and their aggregate at 64 MiB, with over-cap or short/incomplete reads refusing demotion. Recovery re-discovers directory entry inventories and candidates independently of the immutable audit-tool manifest list; differences invalidate dependent sections selected by stored structured census metadata, never parsed `Reachability:` text. Directory digests detect entry changes; candidate digests detect selected-file content changes only. Disclose finite-pattern misses (R7-08), digests detect changes rather than truth, and no census proves omitted declarations absent.
13. AC-13 checks the evidence/source-class table in §3.0, with source class (`checkout-consistency`, `format/integrity`, or `external-trust`), supported claim, and limitation. Caller-provided canonical `checkout_root` is the sole `external-trust` input and supports only scope-root equality; it does not prove checkout truth or scan completeness. npm manifest/lockfile checks are checkout consistency; directory/file digests detect changes in observed inputs only; fixed grammar and sanitization provide format integrity. Self-tests reject missing/duplicate sources, mislabelling in-checkout evidence as external trust, same-checkout reads called independent proof, caller provenance overstated as checkout truth, and digests claimed as truth verification. The checker does not prove census completeness.

14. AC-14 requires one runnable stdlib fixture-driven test of the actual first-party
    classifier/parser/census/digest implementation, wired into `bash scripts/run_tests.sh`.
    Direct executable/code-path assertions cover npm recorded direct, transitive, optional,
    peer, and direct/nested alias closure (including wrong/absent alias target), a finding whose
    reported name matches no lock-node resolved name refusing demotion (`unknown`, never `dev`),
    and failed or
    skipped scope inputs refusing all npm `dev` tokens even without name overlap. Python
    assertions cover dynamic `optional-dependencies`, static extras, successful census and
    incomplete candidate/directory reads refusing demotion. Recovery assertions cover
    unchanged requirements-section retention, changed-input digest invalidation and rerun
    selection, and regenerated global Summary/Triage; malformed provenance is rejected.
    Include group-only `production` in PEP 735 and Poetry under `strict` (Critical stays
    `unknown`, no Python `dev` token, blocking); missing direct root `x` with only an
    unrelated nested `node_modules/dev-tool/node_modules/x` versus a correctly placed
    `node_modules/x` control; a >1 MiB scanned workspace `package.json` on a non-empty
    closure path (and aggregate cap overflow), both refusing npm `dev` tokens; and
    unchanged manifest/census bytes with changed virtualenv on resume, forcing a fresh
    environment-backed `pyproject.toml` audit whose findings replace old findings. Run against
    fixture files/directories, not Markdown anchors or prompt responses; checker `--selftest`
    and §11 evals do not substitute for this runtime test. No new dependency.

## 13. Accepted residuals

The supplied R7 report closed in `mode: standard` with 0 Fatal and records 6 Significant, 5 Medium, and 3 Low residuals. Design revision does not claim these are solved. Preserve these concrete limitations in the skill, evals, reviews, QG disclosure, and final report:

- **R7-01 (High):** remove §7.5's stale lockfile-key membership rule and nonexistent "members table". Scanned `package.json` paths seed npm; in-checkout membership checks do not prove scan completeness.
- **R7-02 (High):** deleting a workspace manifest before scan can shrink seeds undetected. Scope-root equality does not detect same-root omission; false declaration-faithful `dev` remains possible.
- **R7-03 (High):** recovery compares traversed-directory entry-name/type digests and observed candidate path/status/content. It catches tree-entry changes inside the bounded traversal, but not content changes to undetected files at unchanged paths, inputs outside the traversal, or declarations omitted before the baseline census.
- **R7-04 (Medium):** package manifests, lockfiles, Python files, and audit output are checkout/registry-controlled. Same-source checks detect malformed/inconsistent inputs only, never independently prove scope.
- **R7-05 (Medium):** pruning one lockfile edge in a non-empty graph can make recorded prod dependency look absent. Output must describe recorded-graph scope, not true runtime scope.
- **R7-06 (Medium):** npm and Python demotion are refused unless caller-supplied canonical `checkout_root` provenance equals canonical `scope_root`; this external-trust input supports only root equality, not checkout truth. Missing or unequal roots leave would-be `dev` contributions as `unknown`.
- **R7-07 (Medium):** modern Poetry `[tool.poetry.group.main.dependencies]` is production; Poetry extras remain `unknown` and any extras table blocks Python `dev` demotion.
- **R7-08 (Medium):** finite plausible-unscanned Python filename patterns miss unknown conventions; examples include `requirements.in`, `pdm.lock`, environment-specific paths, and other names. Never claim exhaustive detection.
- **R7-09 (Low):** `O_NOFOLLOW` protects final component; FIFO/device and component-swap caveats remain under no-mid-classification-mutation assumption.
- **R7-10 (Low):** printable ASCII includes Markdown-active symbols; human-reader presentation risk remains.
- **R7-11 (Low):** affected-section recovery selection must use stored structured provenance/digests, never parse prior `Reachability:` text.

The supplied R7 report contains a count discrepancy: its verdict says 6 Significant/High, 5 Medium, 3 Low (14 total), while its numbered R7-01…R7-11 list contains 3 High, 5 Medium, 3 Low (11 total). Preserve both statements and require fresh review/QG to resolve or disclose the mismatch; do not invent unlisted findings or severities. The report remains source of truth for its finding text. Process caveat: its 3-agent review was self-dispatched without receipts; the report states it is not claiming a receipt-lint blocker on that review. Preserve that limitation; do not treat the report's review process as receipt-verified or invent a blocker it disclaims. No claim of independent verification, true-graph superset, or malicious-checkout detection is permitted.

**Adjudication residual (S2):** a v1 lockfile with no `packages` map leaves every seed unresolved — fail-safe `unknown` plus a warning naming `lockfileVersion`, never `dev` (§4.1).
