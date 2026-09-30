# Design: SUPERSEDES trust redesign (#586)

**Issue:** GH #586 · **Date:** 2026-09-30 · **Base:** `origin/dev` @ `5272a9a`
**Status:** design only, no code changes. Needs its own `/quality-gate` pass before implementation.
**Related:** #584 (origin of the check), #567 (CHAIN-1 detector class), #585 (trust boundary;
[design](2026-09-06-585-auth-boundary-design.md) §8.5 assigns C4's fabricated-row half here).
An earlier, much longer draft exists outside the repo (worktree `fix/586-supersedes-redesign`,
`docs/plans/2026-09-06-586-supersedes-referential-integrity-design.md`, gitignored, never
committed). This document reaches the same structural recommendation and is the one to gate.

## 1. Problem

`tier2_supersedes_existence(supersedes, ledger_path)` (`scripts/rcpt_verify.py`) accepts a
receipt's `SUPERSEDES: <prefix>[,<prefix>…]` if each prefix `startswith`-matches exactly one
distinct `rcpt_sha256` in the `--ledger` file (`receipt-ledger.jsonl`).

The trust decision behind it is: **resolve a key the receipt supplies against a store the
reviewed subagent can write, and treat "found" as a fact about the world.** The ledger sits
in the dispatch root, which the reviewed subagent owns (same uid, same filesystem, per #585).
So every property of the lookup (the key's grammar, which file is read, what it contains,
what population uniqueness is checked against, cost, and what absence means) is controlled
by the party being checked. Point-fixing one property leaves the others open. That is why
the function has been patched twice in one gate and is still broken.

## 2. The four bypasses (plus the folded Low)

| # | Finding | Link the attacker controls | Severity |
|---|---|---|---|
| 1 | Missing `--ledger` file hard-FAILs via `LintError` (red-team F1). A fail-open degrade would reopen #584: the subagent deletes the ledger and gets the advisory path. | Absence semantics | Fatal (judgment call) |
| 2 | Symlinked `--ledger`: read via `_read_and_fstat_artifact`, no `O_NOFOLLOW`. Point it at a sibling dispatch's ledger to retire any predecessor whose prefix exists there (siege CHAIN-N2). | Store identity | High |
| 3 | No prefix grammar (spec says `<hash-prefix-12>`). A 1-char prefix can pass CLAIMS membership and ledger uniqueness, while the orchestrator's Sweep checks uniqueness against a *different* population (the manifest) (siege CHAIN-N3). | Key grammar, store population | High |
| 4 | SIEGE-BA-2's perf fix still does `sha256_values[lo:]`, which copies O(L−lo) per prefix. The complexity class is unchanged, and the regression test never exercises adversarial `lo=0` (siege FA2-3). | Lookup cost | High |
| 4b | Empty/whitespace prefix matches everything on a single-distinct-value ledger (siege R2BA-5). | Key grammar | Low |

A fifth mechanism makes the class undeniable. **Append one ledger line** with a minted
`rcpt_sha256` that starts with the fabricated prefix, and the existence check passes. No
symlink, race, or odd prefix is needed. Fixing 1–4 leaves this open.

## 3. Options

**A. Harden the lookup in place.** Add `O_NOFOLLOW`, a `^[0-9a-f]{12}$` grammar, a real
bisect-with-early-stop, and reject empty prefixes. *Rejected.* It closes 2, 3, 4 and 4b, but
it does not close the self-minted row (L3) or the absence dilemma (#1). Each patch has its
own residual. This is the per-link approach #567 records as relocating the class instead of
closing it.

**B. Authenticate the ledger (MAC / signature / hash chain).** *Rejected.* #585 §7.2 already
settles it: there is nowhere to keep a key out of the subagent's reach.

**C. Move the ledger out of the dispatch root.** *Rejected as a closure.* It is obscurity at
the same uid (#585 Tier 4). It may still ship as blast-radius reduction, but it does not
answer #586.

**D. Invert the trust direction (recommended).** Stop resolving a receipt-supplied key
against any store. The orchestrator already holds the authoritative value in context: the
Tripwire Manifest's 12-hex prefix of `sha256(normalize(receipt))` for every receipt it
accepted (`skills/shared/return-convention.md`, Tripwire Manifest and Sweep). The Sweep
already names the "manifest-holding layer" as the owner of SUPERSEDES existence and
uniqueness. #584 substituted the subagent-writable ledger for that layer. Pass the expected
set on argv instead:

```
rcpt_verify.py --tier2 ... --expect-supersedes <none | hex12[,hex12]{0,7}>   (repeatable; set)
```

- The receipt cites `none`: the leg does not run.
- The receipt cites tokens and the flag is absent: **hard FAIL** (exit 1). This is safe
  because argv cannot be "missing on disk". An absent flag is an orchestrator error, not an
  environmental state, so the fail-open horn of #1 no longer exists.
- The receipt cites tokens and the flag is `none`: hard FAIL.
- Every cited token must match `^[0-9a-f]{12}$` (Tier-1) **and** be an exact member of the
  declared set. There is no `startswith` and no ambiguity question.
- A declared token that is not cited is not an error. Whether a mandated retirement actually
  happened is an outcome the orchestrator checks after the Sweep.
- `none` mixed with tokens is a usage error (exit 2).

`tier2_supersedes_existence` and its `--ledger` read are **deleted**. `--ledger` stays for
`tier2_ledger`'s DISPATCHED binding. That binding is #585 C4's other half and is out of
scope here.

## 4. Why D closes the class

| Link | Under D |
|---|---|
| Key grammar (#3, #4b) | Fixed 12-hex allowlist plus set **equality**. No partial-match operator remains. |
| Store identity (#2) | No path is opened, so there is nothing to symlink. |
| Store contents (self-minted row) | There is no store. |
| Store population (#3) | The set is enumerated by the orchestrator, not grown by the subagent. |
| Lookup cost (#4) | O(cited tokens) set lookups. The token count is capped at 8 at Tier-1. |
| Absence (#1) | An argv value cannot be absent-on-disk, so hard FAIL is safe. |

**Residuals (named, not closed).**

- **R1:** the orchestrator must pass the right set. This is in-context state, and the same
  #585 boundary applies: the orchestrator edge is not closable in-band.
- **R2:** the manifest is in-context only and is not restored by the cairn Recovery Protocol
  (#585 A5 / SIEGE-C1). After compaction the orchestrator has no durable trusted source for
  the set. Remedy: make the manifest durable, or have the protocol say the set must be
  recomputed from receipts the orchestrator re-reads. This is filed separately and it
  **blocks rollout**. Until it is fixed, a post-compaction orchestrator must pass
  `--expect-supersedes none` (fail closed: no retirement) rather than rebuild the set from
  the ledger.
- **R3:** "no-already-superseded" becomes checkable in the orchestrator's manifest. The
  verifier cannot do it.
- **R4:** keyword/header recognition of `SUPERSEDES:` lines (#567 CHAIN-1) is a different
  class and is still owned by #567.

## 5. Migration

1. Add a Tier-1 grammar and cap on the `SUPERSEDES` value (`^[0-9a-f]{12}$`, ≤ 8 tokens).
2. Add `--expect-supersedes`. The receipt-cites-and-flag-absent case is a hard FAIL
   **from day one**. There is no advisory period, because an advisory is the #1 fail-open.
3. Update every mandated command line (`skills/quality-gate/SKILL.md`,
   `skills/siege/SKILL.md`, `skills/build/SKILL.md`, and the Sweep in
   `skills/shared/return-convention.md`) to pass the manifest-derived set, in the same PR as
   step 2.
4. Delete `tier2_supersedes_existence` and its tests. Replace them with the tests in §6.
5. Resolve R2 first, or ship the documented fail-closed fallback with it.

Steps 2–4 land as one change. Shipping the flag without the call-site updates hard-FAILs
every legitimate supersession.

## 6. Acceptance criteria

- **AC-1** The receipt cites `abc123abc123` with no `--expect-supersedes`: exit 1, and the
  bullet names the flag.
- **AC-2** The cited token is not in the declared set: exit 1, naming the token. This holds
  even when a ledger row minted to match that token is present (the self-minted-row repro).
- **AC-3** A symlinked or missing `--ledger` has no effect on the SUPERSEDES outcome, in
  either direction.
- **AC-4** The prefixes `a`, empty, whitespace, 13-hex, and uppercase hex are Tier-1 lint
  failures.
- **AC-5** 9 cited tokens are a Tier-1 failure. `none` mixed with tokens in the flag gives
  exit 2.
- **AC-6** With 8 cited tokens and a ledger of 10^6 rows, runtime does not depend on ledger
  size (the leg reads no ledger).
- **AC-7** The legitimate path works: a receipt cites a subset of the declared set and gets
  exit 0 under the mandated `--tier2 --strict` command line.
- **AC-8** `grep -n tier2_supersedes_existence scripts/rcpt_verify.py` finds nothing.
- **AC-9** Every mandated command line in `skills/` that lints receipts which may carry
  SUPERSEDES passes `--expect-supersedes`. This is enforced by a structural checker in
  `scripts/run_tests.sh`.
- **AC-10** R2 is resolved or its fail-closed fallback is documented in
  `skills/shared/cairn-convention.md` before AC-1 is enforced in production.

## 7. Open question for the maintainer

Is R2's fail-closed fallback acceptable (after compaction, no supersession is possible until
a re-dispatch)? Or must the manifest be made durable first? The recommendation is to accept
the fallback: it costs a re-dispatch, never integrity.
