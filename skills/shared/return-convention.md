---
version: 1
---

# Return Convention (Ledger Return Protocol)

> Canonical reference for the subagent → orchestrator return channel.
> Every subagent dispatched via `shared/dispatch-convention.md` MUST return exactly one
> Evidence Receipt in the format defined below. Prose outside the receipt is a protocol
> violation.
>
> **This is a shared skill reference, not a CLAUDE.md directive.** Pilot skills
> (`/build`, `/quality-gate`, `/siege`) reference this file via
> `<!-- CANONICAL: shared/return-convention.md -->`. Templates do not duplicate the
> grammar; they link here.

## Purpose

Orchestrators running for hours with O(100+) dispatches cannot afford unbounded prose returns. The receipt format:

1. **Caps the return channel** at ~20 lines per dispatch.
2. **Makes verification structural**: a ~30-line in-context linter catches the overwhelming majority of protocol violations without reading disk.
3. **Closes the silent-skip attack**: the mandatory `WITNESS` line pre-commits a cheapest-falsifier that the orchestrator can replay.
4. **Composes with existing disk-mediated dispatch**: the `<dispatch-id>` in the receipt header is the basename from `dispatch-convention.md`.

## Receipt Grammar (v1)

A receipt is a text block with exactly seven fixed section headers in this order:

```
RCPT v1 <skill>/<dispatch-id>
VERDICT  <PASS|FAIL|BLOCKED>  conf=<N.NN>
ARTIFACTS
  <name>  sha256:<hex64>  <size>[  <key=value>...]
  ...
TRACE
  <N>  <VERB>  <args>
  ...
CLAIMS
  <key>=<value>  from=<citation>  [pattern=<regex>]
  ...
WITNESS    <kind>:<payload>  expect-fail=<signature>  ran=<TRACE#N|SKIPPED:reason|UNRUNNABLE:reason>
SUSPICION  <N.NN>  [ (<one-line note>) ]
NEXT       <one-line re-verification hint>  [; <hint>]
```

### Section bodies

- Multi-line sections (`ARTIFACTS`, `TRACE`, `CLAIMS`): body = the indented lines under the header.
- Single-line sections (`RCPT`, `VERDICT`, `WITNESS`, `SUSPICION`, `NEXT`): body = the rest of the header line, including any bracketed inline note permitted by its field rule.
- No text may appear before the first header, between a header and its body, or after the last section's body.
- **Forward compatibility:** v1 parsers MUST silently ignore any section header appearing **after** `NEXT` that they do not recognize (reserved for Layer 2 `TRIPWIRE:` and later extensions). Unknown headers appearing **before** `NEXT` are a protocol violation.

### Field rules

- **Header line** — `RCPT v1 <skill>/<dispatch-id>`. `<skill>` matches `[a-z][a-z0-9-]*`. `<dispatch-id>` is the dispatch directory basename provided by the orchestrator.
- **VERDICT** — one of `{PASS, FAIL, BLOCKED}`, followed by `conf=<N.NN>` where `N.NN` matches `(0\.\d{2}|1\.00)`.
  - `PASS` — subagent believes its objective was met.
  - `FAIL` — subagent believes its objective was not met.
  - `BLOCKED` — subagent cannot proceed without orchestrator action.
- **ARTIFACTS** — one or more indented lines: `<name>  sha256:<hex64>  <size>` with optional trailing `<key=value>` pairs (e.g. `lines=+142/-38`). Empty ARTIFACTS is written as the literal indented line `(none)`.
- **TRACE** — ordered, 1-indexed. Byte-ranges in `out=` are bounded: form `L<a>-L<b>` or `B<a>-B<b>` with `b - a ≤ 4096 bytes` (or line-count equivalent). Ranges exceeding the bound are a Tier-1 lint failure.
- **CLAIMS** — zero or more `<key>=<value>  from=<citation>` lines. Citation syntax: `TRACE#<N>`, `<artifact>#<byte-range>`, or `<artifact>#$.<jsonpath>`. Optional `pattern=<regex>` asserts the pattern appears in the cited range.
- **WITNESS** — exactly one line. See Witness Protocol below.
- **SUSPICION** — `<N.NN>` matching `(0\.\d{2}|1\.00)`, self-reported. Semantics: *"how much of my own VERDICT should the orchestrator distrust?"* — a claim about uncertainty, not correctness.
- **NEXT** — one line of re-verification hints (semicolon-separated). Use the literal `NEXT  (none)` when no suggestion.

### Closed verb vocabulary

```
READ       <path>  sha256:<hex64>                                  observation, no effect
EDIT       <path>  sha256:<hex64>                                  in-place mutation (post-edit hash)
WROTE      <path>  sha256:<hex64>                                  net-new file created
EXEC       `<cmd>`  exit=<int>  dur=<Ns>  out=<artifact>#<range>   subprocess run
DISPATCHED <skill>/<dispatch-id>  verdict=<PASS|FAIL|BLOCKED>  rcpt-sha256:<hex64>   sub-subagent dispatch
CONSULTED  <reference>                                             web/doc/prior-artifact lookup
SKIPPED    <action>  reason=<short-phrase>                         explicit non-action
```

**Mandatory-work rule.** Each pilot skill's `## Return Format` section names actions that are mandatory for this dispatch type (e.g. `/build` implementers MUST run tests; `/siege` attackers MUST attempt at least one exploit variant). For each mandatory action, the TRACE MUST contain either the matching verb line OR a `SKIPPED <action> reason=<phrase>` line. Silent omission is a lint failure — the whole point of `SKIPPED` is to turn "didn't do it" into a positive protocol event.

### Citation resolution

- `TRACE#N` — valid iff `1 ≤ N ≤ len(TRACE)`.
- `<artifact>#L<a>-L<b>` or `<artifact>#B<a>-B<b>` — valid iff `<artifact>` appears in `ARTIFACTS` and the range is non-empty and within the 4 KiB bound.
- `<artifact>#$.<jsonpath>` — v1 linter verifies only that the artifact appears in ARTIFACTS. Deeper resolution is deferred to v1.1.

## Witness Protocol

The `WITNESS` line pre-commits the single cheapest verification whose result would **contradict** the VERDICT. This is the mechanism that closes the "subagent silently skipped verification" attack: a subagent can omit an `EXEC` line, but it cannot omit `WITNESS` without the linter flagging the receipt.

### Kinds

- **`exec:<oneliner-cmd>`** — a shell command ≤120 characters that would produce `expect-fail` output in the failing world. Default for code-producing dispatches.
- **`grep:<artifact>#<range>  pattern=<regex>`** — a byte-range re-read with a pattern check. Default for research/judge dispatches with no shell. Failing world: the pattern matches.
- **`lint:<rule-name>`** — a named semantic check re-applied to this very receipt. v1 rule vocabulary (closed): `all-claims-cited`, `trace-consistent`, `skip-declared`. Unknown rule names are a Tier-1 lint failure.

### `expect-fail` signature forms

- Non-zero exit: `exit!=0` or `exit=<N>` with `N ≠ 0`.
- Regex: `/…/` whose pattern (excluding delimiters) is ≥ 4 characters and is not wildcard-only (`/.*/` and equivalents rejected).
- Literal fragment: `"…"` whose content is ≥ 4 characters.
- The bare token `match` — used with `kind=grep` to mean *"the pattern declared on the grep line matches the body"*. Failing world: the pattern matches. No length constraint because the pattern itself is already on the WITNESS line.

### `ran=` disposition

- **`ran=TRACE#N`** — subagent already executed the witness. `TRACE#N` must be the matching verb for the kind: `EXEC` for `exec:`; `EXEC`/`READ`/`WROTE` for `grep:` (any verb that touches or produces the artifact being grepped); **any verb** for `lint:` (the citation points at the TRACE entry that most directly produced the state the rule targets — the rule itself is re-applied to the receipt, independent of the cited verb). Tier-2 will read the cited range for `exec:`/`grep:`; for `lint:` Tier-2 re-applies the named rule.
- **`ran=SKIPPED:<short-reason>`** — subagent chose not to execute. When `SKIPPED`, `NEXT` MUST contain the witness payload as a verbatim substring (byte-for-byte match including whitespace). The orchestrator owns the deferred verification via Layer 3 Cairn's `OPEN_OBLIGATIONS`.
- **`ran=UNRUNNABLE:<short-reason>`** — cannot be executed in any foreseeable context. `<short-reason>` must come from the closed vocabulary: `sandbox-restricted`, `tooling-absent`, `platform-incompatible`, `network-unreachable`, `service-unavailable`, `time-budget-exceeded`, `requires-human-input`. **Not permitted on `PASS`** (the silent-skip hole).

`WITNESS` is **mandatory on every receipt**. The literal `WITNESS  (n/a)` is not permitted.

## Parent-Child Receipt Binding

When a subagent dispatches its own subagents (`DISPATCHED` verb), parent-fabricated child verdicts are closed by the following rule:

1. **Orchestrator-side recording.** On accepting any receipt, the orchestrator computes `sha256(normalize(receipt_text))` where `normalize` (a) strips trailing whitespace per line, (b) collapses `\r\n → \n`, (c) ensures exactly one trailing `\n`. It records `{dispatch-id, rcpt-sha256, verdict}` in the dispatch directory's `receipt-ledger.jsonl` (append-only) **synchronously, before returning control to any parent dispatch**.
2. **Parent lint rule.** Every `DISPATCHED <skill>/<dispatch-id> verdict=<V> rcpt-sha256:<H>` line in a parent's TRACE must have a corresponding `receipt-ledger.jsonl` entry with matching `dispatch-id`, `rcpt-sha256`, and `verdict`. Tier-1 rejects on mismatch.
3. **Child lint propagation.** A child receipt that fails lint is recorded in the ledger with `verdict=BLOCKED`. A parent that claims `verdict=PASS` for that child hits the Tier-1 binding check and fails.

## Two-Tier Receipt Linter

The linter is prose-as-pseudocode embedded in each pilot skill. Orchestrators apply it to every received receipt before acting on the subagent's VERDICT.

### Tier 1 — Structural (in-context, zero disk reads)

```
parse receipt into sections by header
fail if any required section is missing, duplicated, or out of order
fail if text appears outside section bodies (inline bracketed notes permitted by a
  field rule ARE body; unknown headers AFTER NEXT are ignored for forward
  compatibility; unknown headers BEFORE NEXT are a failure)

for each CLAIM:
  fail if citation syntax invalid
  fail if citation target (TRACE#N or artifact name) does not resolve in this receipt

for each EXEC in TRACE:
  fail if exit=, dur=, or out= is missing
  fail if out= artifact is absent from ARTIFACTS
  fail if out= byte-range exceeds 4 KiB

for each EDIT / WROTE in TRACE:
  fail if sha256:<hex64> missing OR the hash is not declared in ARTIFACTS

for each DISPATCHED in TRACE:
  fail if rcpt-sha256:<hex64> is missing
  fail if the (dispatch-id, rcpt-sha256, verdict) triple is not present in
    receipt-ledger.jsonl (see Parent-Child Receipt Binding)

mandatory-work check: for every action the skill's RETURN FORMAT declares mandatory
  for this dispatch type, TRACE MUST contain the matching verb line OR a
  SKIPPED <action> line. Silent omission fails.

witness structural check (every verdict):
  fail if WITNESS absent or equal to the literal "(n/a)"
  fail if <kind> not in {exec, grep, lint}
  fail if <kind> = lint and <rule-name> not in {all-claims-cited, trace-consistent,
    skip-declared}
  fail if expect-fail empty, wildcard-only, or < 4 chars (exempt: bare `match` when
    kind=grep, the exit-clause forms, and bare `match` is only valid for kind=grep)
  if VERDICT=PASS: ran= must be TRACE#N or SKIPPED:<reason>  (UNRUNNABLE not permitted)
  if VERDICT=FAIL/BLOCKED and ran=UNRUNNABLE:<reason>: <reason> must be in the closed
    vocabulary
  if ran=TRACE#N: TRACE#N must exist and be the matching verb for the kind
    (exec → EXEC; grep → EXEC/READ/WROTE; lint → any); its out= artifact
    (or receipt-self, for kind=lint) must resolve
  if ran=SKIPPED:<reason>: NEXT must contain the witness payload as a verbatim
    substring (byte-for-byte including whitespace)
```

### Tier 2 — Witness verification (bounded `Read` per verified verdict)

```
if VERDICT=PASS and WITNESS.ran = TRACE#N:
  Read the cited out=<artifact>#<range>  (range ≤ 4 KiB by Tier-1)
  for kind=exec:   fail if TRACE#N.exit matches expect-fail's exit clause, OR
                    the range's text matches the expect-fail regex/fragment
  for kind=grep:   fail if the range's text matches the pattern (failing world)
  for kind=lint:   re-apply the named rule to this receipt; fail if it fires

if VERDICT=FAIL and WITNESS.ran = TRACE#N:
  (weak positive-evidence; grounds-binding limitation documented below)
  Read the cited range
  for kind=exec:   accept if exit≠0 OR range matches expect-fail.
                    reject if BOTH exit indicated success AND range did NOT match —
                    the subagent filed FAIL without any witness firing.
  for kind=grep:   reject if range does NOT match pattern
  for kind=lint:   reject if the rule does NOT fire when re-applied

if ran=SKIPPED or UNRUNNABLE:
  no Tier-2 read. Orchestrator schedules re-verification via Layer 3 Cairn.

if VERDICT=BLOCKED:
  no Tier-2; the dispatch is not trusted for forward progress regardless.
```

**Grounds-binding limitation (known, v1).** Tier-2 `FAIL` is *weak positive evidence* — the witness fired, but the linter cannot structurally prove it fired *for the reason the subagent claimed*. Accepted gap. Mitigated by existing fix-dispatch escalation (the fix agent's own receipt carries its own witness) and by Cairn capturing lingering FAIL receipts in `OPEN_OBLIGATIONS`.

### Lint failure handling

A receipt that fails either tier is treated as structurally `BLOCKED` regardless of its declared VERDICT. The orchestrator surfaces the specific failure to the narration log and either re-dispatches with the lint errors appended to the brief or escalates. The declared VERDICT/CLAIMS are not surfaced to the user until the receipt is valid.

### Cost model

- Tier-1: entirely in-context. Free per receipt.
- Tier-2: one `Read` of a byte-range ≤ 4 KiB per verified verdict (PASS or FAIL with `ran=TRACE#N`). `SKIPPED`/`UNRUNNABLE` defer to Cairn. `BLOCKED` skips Tier-2.

This is the explicit, budgeted price of closing the synthetic-skip attack class: one small range read per trust-relevant receipt.

## Composition

- **`shared/dispatch-convention.md`** — the write channel. Supplies `<dispatch-id>`. Unchanged.
- **Layer 2 — Tripwire Manifest (#203)** — appends a single `TRIPWIRE:` line after `NEXT` (permitted by forward-compatibility clause). A firing Tripwire may cite the receipt's `WITNESS` payload as its re-run target.
- **Layer 3 — Invariant Cairn (#204)** — orchestrator-internal. A receipt with `ran=SKIPPED:…` or `ran=UNRUNNABLE:…` promotes into Cairn's `OPEN_OBLIGATIONS` as a concrete runnable tail, not prose.

## Example Receipts

### PASS — code-writing dispatch (kind=exec, ran=TRACE#N)

```
RCPT v1 build/7-implementer
VERDICT  PASS  conf=0.90
ARTIFACTS
  patch.diff       sha256:9c01aa7f3b4e8d2c6d5a0f1e2b3c4d5e6f708192a3b4c5d6e7f809a1b2c3d4e5  14823  lines=+142/-38
  test-output.log  sha256:a4eef12d93b7c8e5f6017283940a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2  8192
TRACE
  1  READ   src/foo.ts  sha256:22abdd8cde1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b
  2  EDIT   src/foo.ts  sha256:33cdee1fa2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9
  3  EXEC   `bun test src/foo.test.ts`  exit=0  dur=4.2s  out=test-output.log#L1-L220
CLAIMS
  tests-ran=true    from=TRACE#3
  tests-pass=true   from=test-output.log#L200-L220  pattern="220 pass"
  patch-applied=true  from=TRACE#2
WITNESS    exec:`bun test src/foo.test.ts`  expect-fail=/\d+ fail/  ran=TRACE#3
SUSPICION  0.10
NEXT       re-run WITNESS at merge-time
```

### PASS — judge dispatch (kind=grep, ran=TRACE#N)

```
RCPT v1 quality-gate/12-judge
VERDICT  PASS  conf=0.85
ARTIFACTS
  review.md  sha256:b2e7c3a4d5f6e7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2  3120
TRACE
  1  READ   docs/plans/foo-design.md  sha256:dd8cef1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9
  2  WROTE  review.md  sha256:b2e7c3a4d5f6e7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2
CLAIMS
  severity-max=minor  from=review.md#L40-L55  pattern="severity: minor"
  fatal-count=0       from=review.md#L1-L20   pattern="Fatal: 0"
WITNESS    grep:review.md#L1-L80  pattern=/Fatal:\s*[1-9]/  expect-fail=match  ran=TRACE#2
SUSPICION  0.15  (judge dispatch)
NEXT       re-run grep at merge-time
```

### FAIL — implementer hit failing tests (kind=exec, ran=TRACE#N)

```
RCPT v1 build/8-implementer
VERDICT  FAIL  conf=0.95
ARTIFACTS
  patch.diff       sha256:ee7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f  9412
  test-output.log  sha256:ff8091a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0  6240
TRACE
  1  EDIT   src/bar.ts  sha256:4455667788aabbccddeeff00112233445566778899aabbccddeeff0011223344
  2  EXEC   `bun test src/bar.test.ts`  exit=1  dur=3.1s  out=test-output.log#L1-L180
CLAIMS
  tests-ran=true   from=TRACE#2
  tests-pass=false from=test-output.log#L170-L180  pattern="3 fail"
WITNESS    exec:`bun test src/bar.test.ts`  expect-fail=/\d+ fail/  ran=TRACE#2
SUSPICION  0.05
NEXT       dispatch fix-agent with test-output.log#L120-L180
```

### BLOCKED — tooling absent (kind=exec, ran=UNRUNNABLE)

```
RCPT v1 siege/3-attacker
VERDICT  BLOCKED  conf=0.80
ARTIFACTS
  (none)
TRACE
  1  SKIPPED  run-zap  reason=zap-proxy-unavailable-in-sandbox
CLAIMS
WITNESS    exec:`zap-cli quick-scan http://localhost:3000`  expect-fail=/High: \d+/  ran=UNRUNNABLE:tooling-absent
SUSPICION  0.50  (attacker could not execute primary tool)
NEXT       orchestrator re-dispatches with sandbox containing zap-cli
```

### Lint-failure example (rejected by linter)

```
RCPT v1 build/9-implementer
VERDICT  PASS  conf=0.95
ARTIFACTS
  patch.diff  sha256:abc...  512
TRACE
  1  EDIT  src/baz.ts  sha256:def...
CLAIMS
  tests-pass=true  from=TRACE#99     ← CLAIM cites non-existent TRACE#99 (Tier-1 fail)
WITNESS    exec:`echo ok`  expect-fail=/.*/  ran=TRACE#1   ← wildcard expect-fail (Tier-1 fail)
SUSPICION  0.00
NEXT       (none)
```

Any pilot skill applying the linter to this receipt records the failure, treats the dispatch as structurally `BLOCKED`, and re-dispatches with the lint errors appended.

## Integration Checklist for Pilot Skills

Each pilot skill's dispatch prompt template and orchestrator body must:

1. Add a `## Return Format` section at the top of the dispatch template referencing this convention:
   ```
   <!-- CANONICAL: shared/return-convention.md -->
   Return exactly one Evidence Receipt per `shared/return-convention.md`. ONLY the
   receipt — no surrounding prose. See the shared convention for grammar, verb
   vocabulary, and the WITNESS protocol. This dispatch's mandatory actions are:
   <list of actions that MUST appear as a TRACE verb line or SKIPPED entry>.
   ```
2. Add a minimal per-skill receipt example showing a typical PASS for that skill.
3. Add the two-tier linter block (prose pseudocode from this document, trimmed as appropriate) to the orchestrator flow, applied to every Task return.
4. Do NOT inline the grammar. Link to this file.

## Version History

- **v1** (2026-04-20) — Initial. Pilot in `/build`, `/quality-gate`, `/siege`. Bulk rollout across the other 39 skills is a follow-up after eval (see issue #202).
