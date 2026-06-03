# Detection matrix — `sessionkit` multi-angle fixture (#333 / AC3 / I7)

Records the **designed/intended** 7×7 detection matrix for the seven plants in
[`planted.diff`](planted.diff), the `D` / `D_bug` separability figures, and the
recall-floor / bar statements per the gated plan §7.

> **#333 vs #335 split.** #333 **authors** this fixture and **records** this matrix —
> the matrix below is the diagonal **by construction** (each plant designed so exactly
> one angle can detect it). #335 **runs** the live recall floors on real Claude Code +
> OpenCode harnesses against this same fixture. This artifact is the recorded designed
> matrix, **not** a live two-harness recall run. #333's own verification is the
> matrix-diagonality argument here plus the runnable bug-plant reproductions
> (`selftest.py`); the per-harness recall validation is #335's job.

## The 7×7 matrix

Rows = the seven planted bugs (one per angle). Columns = the seven finder angles
(`shared/delve-engine.md` §4) **run in isolation**. Cell `✓` = that angle detects that
plant; `·` = it does not. Bug angles are listed first (the three that build `T`), then
the four quality angles.

|                         | line-by-line | removed-behavior | cross-file | reuse | simplification | efficiency | altitude |
|-------------------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **P1 line-by-line**     | ✓ | · | · | · | · | · | · |
| **P2 removed-behavior** | · | ✓ | · | · | · | · | · |
| **P3 cross-file**       | · | · | ✓ | · | · | · | · |
| **P4 reuse**            | · | · | · | ✓ | · | · | · |
| **P5 simplification**   | · | · | · | · | ✓ | · | · |
| **P6 efficiency**       | · | · | · | · | · | ✓ | · |
| **P7 altitude**         | · | · | · | · | · | · | ✓ |

**The matrix is diagonal.** Each plant is detected by exactly its intended angle and by
no other.

## Separability figures (recorded EXPLICITLY and SEPARATELY, per §7.3 / §10)

- **`D` = 7** — full-7 separability. Every one of the seven plants is separably
  detectable: no two angles co-detect any plant, so there are seven distinct
  separably-detectable bugs and no merge.
- **`D_bug` = 3** — the three **bug-angle** plants (line-by-line, removed-behavior,
  cross-file) are each separably detectable. No merge among the three bug angles.

`D` and `D_bug` are recorded **distinctly** above (not folded together). Per §7.3 / §10,
any `D < 7` (full-7 merge) or any `D_bug < 3` (a merge among the three bug angles)
**MUST** be recorded as a **named angle-non-separability finding** here. There is **no
merge** in this fixture, so:

> **Angle-non-separability findings: NONE.** `D = 7` (no full-7 merge); `D_bug = 3`
> (no merge among the three bug angles). The full diagonal holds.

## Floor / bar statements (§7.4)

- **Standalone full-7 floor (the #335 standalone-delve path — NOT run here):**
  `D − 1 = 6`. The N−1 one-miss shape: a standalone full-7 delve run over this fixture
  must surface at least 6 of the 7 separable plants (one documented per-harness gap
  tolerated). This floor belongs to #335 / AC6; it is stated here, not exercised.
- **temper-R1 absolute Claude-Code bar (parallel-dispatch path, `external_review=skip`,
  empty `external_candidates`):** surface **all `D_bug` = 3** bug-angle plants —
  **zero-tolerance, no documented gap.** Measured against delve's fan-out alone
  (deterministic across external_review settings). temper-R1 is **not** required to
  surface the four quality-angle plants (outside its bug-angle subset, non-gating).
- **temper-R1 sequential-pass fallback (OpenCode / no-subagent):** inherits the same
  one-documented-gap tolerance as standalone delve — all `D_bug` minus at most one
  documented per-harness gap.

## Per-plant detail + separability argument

Each entry gives location, the detecting angle, a one-line description, and either the
concrete reproduction (bug angles) or why it is Minor/Suggestion non-gating (quality
angles) — plus the explicit argument for why **no other** angle co-detects it.

### P1 — line-by-line (BUG)

- **Location:** `after/sessionkit/tokens.py:66` — in the `planted.diff` `verify_token` hunk.
- **Defect:** `if current < token["exp"] + clock_skew:` — was `<=`. Off-by-one: a token
  presented at its exact `exp + clock_skew` second is now wrongly rejected.
- **Reproduction (runnable):** `selftest.py` → *"token valid at exact expiry-plus-skew
  boundary"* asserts `verify_token(tok, skew, now=1000+ttl+skew) is True`; on `after/`
  it returns `False`. Concrete triggering input: `now == exp + clock_skew`.
- **Why only line-by-line:** it is a single changed operator on a single remaining line
  inside one hunk — the canonical local concrete defect. **Not removed-behavior** (no
  line/branch/check was deleted; a comparison was *modified*, the early-return structure
  is intact). **Not cross-file** (single line, single file, no writer/reader contract
  crossed). Not a quality smell (it is a correctness defect with a triggering input).

### P2 — removed-behavior (BUG)

- **Location:** `after/sessionkit/tokens.py` — `verify_token`, the deleted block in the
  `planted.diff` `verify_token` hunk. The pre-acceptance
  `if token.get("revoked", False): return False` guard (and its comment) is **deleted**.
- **Defect:** the revocation check is gone, so a revoked-but-unexpired token is now
  accepted. A deletion that drops a guarantee callers rely on (revoke ⇒ immediate
  rejection).
- **Reproduction (runnable):** `selftest.py` → *"revoked token is rejected"* asserts
  `verify_token(revoked, skew, now=1000) is False`; on `after/` it returns `True`.
  Concrete triggering input: a token with `revoked == True` still inside its TTL.
- **Why only removed-behavior:** the defect is the **absence** of a check, surfaced only
  by reading what the diff *subtracts*. **Not line-by-line** — a line-by-line scan reads
  the *remaining* changed lines for a local concrete defect; the remaining lines of
  `verify_token` are individually correct (signature check + expiry check both sound).
  The dropped guarantee is invisible unless you audit the subtraction, which is exactly
  removed-behavior's job. **Not cross-file** (single file, no contract crossed). The
  stale docstring still promising "revocation is checked before expiry" reinforces the
  removed-behavior signal — the guarantee the surrounding code documents is now gone.

### P3 — cross-file (BUG)

- **Location:** writer `after/sessionkit/tokens.py:31,42` (`planted.diff` `tokens.py`
  hunk: `uid`→`user_id` in `serialize_claims` and the `issue_token` claims dict);
  reader `after/sessionkit/store.py:26` (`self._by_user[token["uid"]] = token`,
  **unchanged** by the diff).
- **Defect:** the writer renamed the token field `uid`→`user_id` (consistently *within*
  `tokens.py`), but the reader in `store.py` still indexes `token["uid"]`. ONE defect
  spanning two files: `SessionStore.put` raises `KeyError: 'uid'` on any token
  `issue_token` produces.
- **Reproduction (runnable):** `selftest.py` → `store.put(live)` (where
  `live = issue_token(...)`) raises `KeyError: 'uid'` at `store.py:26`. ONE reproduction,
  two files.
- **Why only cross-file:** the rename is **internally consistent** inside `tokens.py`
  (`issue_token` writes `user_id`, `serialize_claims` formats `user_id`, `verify_token`
  reads `user_id`), so a line-by-line scan of the `tokens.py` hunk finds **no local
  defect** — every changed line is self-consistent. The reader in `store.py` is
  **unchanged**, so it is not in the diff hunk at all and a line-by-line/removed-behavior
  scan of the diff never reaches it. The defect exists **only** in the writer↔reader
  interaction across the file boundary — exactly the cross-file tracer's territory (one
  bug, one repro, many files). It is **not** removed-behavior (nothing was deleted; a
  field was renamed) and **not** a recurring no-repro pattern (it has a single concrete
  reproduction, so it is delve's, not audit's).

### P4 — reuse (QUALITY — Minor/Suggestion, non-gating)

- **Location:** `after/sessionkit/store.py:60` — `last_seen` returns `int(time.time())`.
- **Smell:** reimplements the package's single source of truth for the current epoch
  second (`tokens._now()`, which is `int(time.time())`) inline, instead of calling the
  already-imported `_now()` helper. Two copies of the same primitive that would
  predictably need the same future change (e.g. a clock-injection refactor).
- **Why non-gating:** the result is **correct** — `int(time.time())` and `_now()` are
  identical today. It is a maintainability duplication (Suggestion-tier), not a defect
  with a failure scenario. No reproduction exists; behavior is unchanged.
- **Why only reuse:** the duplicated thing is an **existing helper** (`_now`) — the
  reuse angle's exact target. It is **not simplification** (the body is already a single
  expression — nothing to collapse). It is **not efficiency** (`int(time.time())` is not
  more expensive than `_now()`; same cost). It is **not altitude** (it sits in the right
  layer — a store accessor — and touches no IO). Adding the import line `import time` is
  what makes the inline duplication possible and visible to the reuse angle.

### P5 — simplification (QUALITY — Minor/Suggestion, non-gating)

- **Location:** `after/sessionkit/store.py:62` — `has_live_session`, the nested
  `if/else: { if/else: return True/return False }` ladder.
- **Smell:** a four-branch nested ladder that is exactly
  `return self._by_user.get(user_id) is not None and verify_token(...)` — convoluted
  control flow where one boolean expression (or one guard clause) suffices.
- **Why non-gating:** the logic is **correct** for every input (verified against
  present/absent/expired users). It is a readability/convolution Suggestion, not a
  defect; no failure scenario, no reproduction.
- **Why only simplification:** the issue is **convolution of correct logic** — the
  simplification angle's exact target. It is **not line-by-line** (no branch is *wrong*;
  every path returns the right value — a line-by-line scan finds no concrete defect with
  a triggering input). It is **not reuse** (it duplicates no existing helper — `is_live`
  is similar in *intent* but this is independently-correct redundant *control flow*, not
  a re-implemented utility call the reuse angle would cite). It is **not efficiency**
  (the branch ladder is not more expensive than the collapsed form). It is **not
  altitude** (right layer, no IO).

> **Separability note (P5 vs P4):** P5 is kept distinct from reuse by making it
> *redundant control-flow shape*, not a re-implemented helper. `has_live_session`
> duplicates no callable — `is_live` is a different method with the same intent, and the
> reuse angle keys on *re-implementing an existing helper/utility* (P4's `_now` case),
> not on two methods that happen to answer a similar question. So P4 (reuse) and P5
> (simplification) do not co-detect.

### P6 — efficiency (QUALITY — Minor/Suggestion, non-gating)

- **Location:** `after/sessionkit/store.py:81` — `live_fraction`, the in-loop
  `total = len(self._by_user)`.
- **Smell:** recomputes the loop-invariant `len(self._by_user)` on **every** iteration
  instead of once before the loop — avoidable repeated cost on a counting path.
- **Why non-gating:** the result is **correct** (the empty case is guarded up front; the
  fraction is right for all inputs, verified). It is an avoidable-cost Suggestion, not a
  defect; no failure scenario.
- **Why only efficiency:** the issue is **avoidable repeated cost of a correct
  computation** — the efficiency angle's exact target. It is **not line-by-line** (the
  code is correct; no concrete defect / triggering input — the earlier draft's empty-store
  crash was removed precisely so it carries no line-by-line bug). It is **not
  simplification** (the loop is not convoluted; hoisting the invariant is a
  *performance* change, not a control-flow collapse). It is **not altitude** (right
  layer, no IO).

> **Separability note (P6 correctness):** an earlier version assigned `total` only inside
> the loop, which raised `UnboundLocalError` on an empty store — a genuine line-by-line
> defect that would have co-detected with line-by-line and broken the diagonal. It was
> fixed (empty-store guard + `total = 0` init) so the plant is purely an efficiency
> smell with **no** correctness defect. This is the kind of accidental co-detection §7
> warns about; it was caught and removed.

### P7 — altitude (QUALITY — Minor/Suggestion, non-gating)

- **Location:** `after/sessionkit/store.py:86` — `audit_dump`, the
  `with open(log_path, "a") as handle: ... handle.write(...)` block inside the
  in-memory `SessionStore` domain class.
- **Smell:** file-IO / log-transport concern placed inside the in-memory session domain
  store — a layer below where the package keeps filesystem access (`config.py` is the
  documented sole owner of disk IO). The concern sits one layer off from where the
  codebase puts its peers.
- **Why non-gating:** the method is **correct** (it writes exactly one line per user).
  It is a layering/abstraction-level Suggestion, not a defect; no failure scenario.
- **Why only altitude:** the issue is **the wrong abstraction level** — domain logic
  reaching into transport/persistence — the altitude angle's exact target. It is **not
  efficiency** (it is not in a hot path and is not wasteful for what it does — the
  problem is *where it lives*, not its cost; called once, not in a per-request loop). It
  is **not reuse** (it duplicates no existing helper — `config.load_config` *reads* a
  file but there is no existing *write/append-log* helper it bypasses, so the reuse angle
  has nothing to cite). It is **not simplification** (the body is already minimal). It is
  **not a bug angle** (correct behavior, no reproduction).

> **Separability note (P7 vs P4/P6):** P7 is deliberately a **write/append to a new log
> path**, not a *read* of the existing config file — a read would have duplicated
> `config.load_config` and co-detected as **reuse**. It is called once (not in a loop)
> and does trivial work, so it carries no **efficiency** smell. That leaves *placement at
> the wrong layer* as the sole detectable concern → altitude only.

## Summary

- **`D = 7`**, **`D_bug = 3`** — full diagonal, recorded distinctly.
- **Angle-non-separability findings: NONE.**
- Standalone full-7 floor (`D−1 = 6`) is #335's standalone-delve path; the temper-R1
  Claude-Code bar is all `D_bug = 3` bug-angle plants, zero-tolerance,
  `external_review=skip`.
- The three bug-angle plants have runnable reproductions (`selftest.py`); the four
  quality-angle plants are behaviorally correct, non-gating smells with no reproduction.
- This is the designed/intended diagonal authored by construction; live per-harness
  recall validation is #335's job.
