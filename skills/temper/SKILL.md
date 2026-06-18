---
name: temper
description: Iteratively review code changes for production readiness through fresh-eyes review loops. Use when completing tasks, implementing major features, or before merging — including when the user says "review this PR", "review my changes", "code review", "check the diff", or "is this ready to ship". Works on PRs from any forge (GitHub, GitLab, Bitbucket, self-hosted) or on raw git SHA ranges.
---

# Temper

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/delve-engine.md -->
The finder angles, the verify gate, the effort tiers, the `cap` semantics, and the eight-field output schema are NOT redefined here — they live in `shared/delve-engine.md`. `/temper` **drives** that engine: Round 1 dispatches it (bug-angle subset, high effort) to enumerate the tracked set `T`, and each later round drives it again over the fixed regions to hunt new gating findings (Track A, Step 4).

<!-- CANONICAL: shared/severity-verdict-contract.md -->
The `severity` and `verdict` vocabularies, and the gating rule `T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}`, are the contract's — not temper's (I11). See `shared/severity-verdict-contract.md`; temper consumes that gating rule to build `T` and defines no scale or verdict of its own.

Like tempering steel after forging — iterative heat-and-quench cycles that set final hardness and elasticity — `/temper` runs successive fresh-eyes review rounds until the change converges. Round 1 drives the **delve-engine fan-out** (bug-angle subset) to enumerate a tracked set `T` of gating findings; each later round re-verifies whether every member of `T` is resolved against the fixed code and admits any new gating finding the fix introduced. The loop exits when `T` is fully resolved and no new gating finding entered.

**Core principle:** Review early, review often. Fresh eyes every round — but the per-round instrument is the engine's **parallel finder fan-out + verify gate** (plus a per-member re-verification pass), **not** one holistic reviewer. Convergence is the resolution status of an enumerated finding set, never a cross-round count comparison. (Distinct from `/audit`: temper drives delve-engine's *instance-bug* fan-out — one-reproduction defects; `/audit` runs *systemic* lenses — different machines.)

**Renamed from `/code-review` (2026-05-17)** to avoid collision with Claude Code's built-in `/review` command. Same iteration behavior; the argument shape and platform-agnostic PR support are new.

## Non-Goals

Temper reviews **code diffs only**. Use a different skill for:

- **Design docs / plans / concepts** — use `/audit` or `/red-team`.
- **Systemic multi-site pattern review** — subsystem-wide patterns, absences, or structural drift with **no single reproduction** — use `/audit`. (temper itself drives delve-engine's parallel fan-out for *instance-bug* enumeration — one-reproduction defects; it does not defer that wholesale to `/audit`. The boundary is the reproduction discriminator: one concrete reproduction is temper/delve's; a no-single-repro pattern is `/audit`'s.)
- **Executable cross-component bug-hunting** (adversarial tests against assembled features) — use `/inquisitor`.
- **Security-specific review** with attacker-perspective coverage — use Claude Code's built-in `/security-review` or `/siege` for a deep multi-agent security audit.
- **Iterative red-team of *any* artifact** (not just code diffs) — use `/quality-gate`.

## Relationship to `/quality-gate`

Temper and quality-gate share a loop shape (fresh reviewer each round, stagnation detection, escalate on architectural concerns). They differ in scope and caller:

- **`/quality-gate`** is the generic iterative red-team loop over *any* artifact (design, plan, code, hypothesis, mockup). It is invoked **by artifact-producing skills** as their terminal gate.
- **`/temper`** is the code-diff-specific instance — same loop shape, plus forge integration (PR metadata, optional post-back), plus the fix-verification convergence model. It is **user-facing** for ad-hoc review and is called by build / debugging / finish on diffs.

temper **drives `shared/delve-engine.md`** for its finding enumeration — it is the engine's fix-verification *loop* driver, in contrast to `/delve`, which runs the same engine **once** and never loops or emits a merge verdict.

When in doubt: if the artifact is a code diff, use temper. If it is anything else (or you are inside an artifact-producing skill writing the gate), use quality-gate.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## Dependencies

| Component | Required? | Purpose | Fallback if missing |
|---|---|---|---|
| `git` | Required | Diff resolution, SHA range, default-branch detection, per-round working-tree snapshots (`git stash create`, §3.8) | None — abort with clear error |
| `shared/delve-engine.md` | Required | The parallel finder fan-out + verify gate temper drives to enumerate `T` (R1) and hunt new gating findings (R2+ Track A) | None — abort; temper has no engine of its own |
| `shared/severity-verdict-contract.md` | Required | The `T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}` gating rule and the severity/verdict vocabulary (I11 — temper defines none of its own) | None — abort; temper coins no scale or verdict |
| Forge CLI (`gh` / `glab` / `bb`) | Optional | PR metadata fetch + optional Step 5 post-back | Probe in order; if all missing, fall through to git-plumbing and ask user for description |
| `crucible-consensus` MCP server | Optional | External-model candidate feed via `external_review` (R1-only `external_candidates`, see External Model Review) | Skip silently — gather no external candidates (≡ `external_review=skip`) |
| `crucible:test-coverage` | Optional | Test-alignment audit when behavioral changes are made | Skip; recommend manually |
| `crucible:checkpoint` | Optional | **Fallback** per-round working-tree snapshot mechanism for the uncommitted-mode fix-delta derivation (§3.8); the **primary** mechanism is `git stash create` (no dependency), so checkpoint stays optional. Also a pre-fix rollback target when build wraps temper. | Skip silently — `git stash create` is the primary path |

## Invocation

```
/temper                          # auto-detect (see Step 1 case 3)
/temper 259                      # PR identifier on the current forge
/temper https://...              # PR URL on any forge
/temper main..HEAD               # explicit SHA range
/temper a1b2c3..d4e5f6           # explicit SHA range
/temper 259 max_rounds=8         # override default 5-round circuit breaker
/temper 259 max_rounds=8 external_review=skip  # skip redundant external_review on re-invocation
```

**Argument shape:** `[PR-id-or-URL | <base>..<head>] [max_rounds=<N>] [external_review=skip]`. No argument means auto-detect.

## How to Request

### Step 1: Resolve the review scope (forge-agnostic)

Determine what to review based on the argument:

**Case 1 — PR number or URL.** Fetch metadata (title, body, base ref, head ref). Forge detection is **CLI-probe order, not hostname-literal** (covers GitHub Enterprise Server and any other GH-flavored host). When the argument is a URL, parse the forge from the URL host first and use **only** the matching CLI (handles fork workflows where `origin` and `upstream` live on different forges). When the argument is a bare PR number, probe CLIs in order against the current `origin`.

**If the argument is a URL,** parse the forge from the URL host and try only the matching CLI:
- `github.com` or any host `gh` authenticates against (GHE) → `gh pr view <id> --json title,body,baseRefName,headRefName,author --repo <owner/repo-from-URL>`
- `gitlab.com` or any GitLab host → `glab mr view <id> --repo <project-from-URL>`
- `bitbucket.org` or any Bitbucket host → `bb pr view <id> --repo <slug-from-URL>`
- Unknown host → fall back to git plumbing (`git fetch <remote> <head-ref>`); ask the user to paste the description.

**If the argument is a bare PR number,** try CLIs in order against the current `origin`:
1. `gh pr view <id> --json title,body,baseRefName,headRefName,author` — covers GitHub and GitHub Enterprise (any host `gh` is authenticated against; verify with `gh auth status --hostname <host>` if needed).
2. `glab mr view <id>` — covers GitLab and self-hosted GitLab.
3. `bb pr view <id>` (or REST) — covers Bitbucket.
4. None of the above succeeded → fall back to git plumbing: `git fetch <remote> pull/<id>/head` (GitHub-style ref) or `git fetch <remote> merge-requests/<id>/head` (GitLab-style); ask the user to paste the description if they want it factored in.

**Distinguish CLI errors from missing CLIs.** A CLI that exits non-zero with "404 / PR not found / authentication required" is *not* a missing-CLI fallback path. Surface the error to the user (e.g., "gh found the PR but auth failed — re-authenticate or paste the diff manually") and pause for instruction. Falling through silently on a CLI error would dispatch a review against the wrong scope.

Map the fetched metadata to `<base>..<head>` SHA range using `git rev-parse <baseRef>` and `git rev-parse <headRef>`.

**Case 2 — SHA range** (argument contains `..`). Use as-is. Metadata is empty: no PR description, just the diff.

**Case 3 — No argument** (auto-detect). Precedence (first match wins):
1. If HEAD is detached (`git symbolic-ref -q HEAD` returns non-zero), **require an explicit argument** — auto-detect is ambiguous in detached state. Abort with a one-line instruction telling the user to pass a SHA range.
2. Try forge-CLI detection of the current branch's PR. If found, treat as Case 1. If the CLI is present but errors (auth-fail, 403, rate-limit, network), surface the error and pause per Case 1's distinguish-error-from-missing rule. Only the unambiguous "no PR for this branch" result advances to step 3.
3. Resolve the upstream default branch via `git symbolic-ref refs/remotes/origin/HEAD` (handles `main`, `master`, `trunk`, or anything else the remote uses). Use `<that-ref>..HEAD` as the SHA range.
4. If no `origin/HEAD` is set (rare; usually means the remote was never properly cloned), check which of `origin/main`, `origin/master`, `origin/trunk` exist. If exactly one exists, use its merge base with HEAD and narrate the fallback (`"[temper] origin/HEAD unset; fell back to origin/<name> as the only main-like ref present"`). If **more than one** exists (legacy repos with both `origin/main` and `origin/master`), **abort** with: `"Multiple main-like refs found (origin/main, origin/master). Pass an explicit <base>..<head> range — the model has no signal which one this branch was cut from."` If none exist, abort with the existing "Cannot determine default branch" message.

**Anti-rationalization:** don't hardcode `gh` calls in the dispatch path. The skill is forge-agnostic — the CLI used is whichever the environment makes available. Skip metadata gracefully on missing CLIs; surface explicit errors on present-but-failing CLIs.

### Step 1.5: Diff preflight (mandatory — runs before dispatch)

Classify the resolved diff before spending an engine dispatch on it. Empty / binary / submodule-only diffs are recognized and handled explicitly so they cannot produce silent false-Clean verdicts. (This preflight runs **ahead of** the R1 delve-engine dispatch — see Step 2's short-circuit ordering — so no engine cost is spent on a non-substantive diff.)

Run `git diff --numstat <base>..<head>` and inspect:

- **Empty diff** (no entries): short-circuit. Return `Clean — no changes to review` immediately. Do not dispatch the engine. Callers (build, finish) see this as "Clean" but with `Reason: empty-diff` distinguishable from a substantive Clean.
- **Binary-only diff** (every entry has `-\t-\t<path>` indicating binary): note in the engine `scope` description / round metadata that the diff is binary-only and content cannot be inspected. Do not produce a Clean verdict against unreviewable content; surface `Architectural — binary-only diff requires human review`.
- **Submodule pointer-only diff** (changes are entirely in `.gitmodules` or submodule SHA pointers): note it in the round metadata and flag a Suggestion to inspect the submodule contents separately. Do not produce a spurious Clean.
- **Mixed text + binary**: pass the text portion normally as the engine `scope`; note the binary files in the round metadata so they are not treated as reviewed.
- **Diff too large** (>5,000 added+deleted lines per `numstat`): warn the user and offer to split per-commit or per-file. If the user proceeds anyway, note the over-cap in the round metadata and dispatch with a context-window degradation warning. This is a soft cap, not a hard block. **Non-interactive callers** (build / debugging / finish dispatching `/temper`): on >5,000-line diffs, proceed automatically with the over-cap note and emit a `degraded-context` flag in the round metadata. Interactive (standalone) callers retain the offer-to-split flow above.

**Empty-diff caller contract.** Pipeline callers (build / debugging / finish) MUST treat `Reason: empty-diff` as a soft-warn — surface to the user ("temper found no changes between BASE and HEAD; confirm this is intended") before proceeding past the gate. The most common cause is uncommitted work, a wrong base, or detached-HEAD post-rebase. Ad-hoc / standalone callers may proceed silently (the user invoked /temper knowing the state).

### Step 2: Round 1 — drive delve-engine, enumerate the tracked set `T`

Round 1 is a **recall pass + enumeration**. Drive `shared/delve-engine.md` to find all gating defects in the diff, then build the tracked set `T` from its kept records.

**Short-circuit ordering (two distinct short-circuits at two stages — the order is load-bearing):**
1. **Step 1.5 preflight runs FIRST, AHEAD of the R1 engine dispatch.** The empty / whitespace-only / binary-only / submodule-pointer-only diff short-circuit (Step 1.5) fires **before any engine call** — so no engine cost is ever spent on a non-substantive diff. The `Reason: empty-diff` Clean (no reviewer dispatched) is preserved exactly. The R1 engine dispatch happens **only after** the preflight admits a substantive, reviewable diff.
2. **The empty-`T` short-circuit is a DISTINCT, LATER condition** — reached only when the preflight already admitted a real diff AND the R1 engine **ran successfully** and enumerated nothing gating. It is **not** the empty-diff case (empty-diff = "nothing to review, no engine call"; empty-`T` = "the engine reviewed a real diff and found no Critical/Important CONFIRMED/PLAUSIBLE finding"). The guarded check below applies to this second condition only.

**The R1 engine drive.** Dispatch `shared/delve-engine.md` once with:
- `scope` = the full diff (`<base>..<head>` from Step 1).
- `angles` = the **bug-finding subset** only: `line-by-line`, `removed-behavior`, `cross-file`. (The four quality angles are excluded — they are capped non-gating per the contract and never enter `T`.)
- `effort` = **high** (recall-biased; the tier delve-engine §3 pins for a gating hunt).
- `cap` = set **explicitly HIGH**, well above the expected `|T|`. delve-engine §6: `cap` truncates the ranked output and does **not** guarantee a gating finding is preserved, so a Critical/Important above the cap would be silently dropped. Do **not** leave it at the default `10`.

The fan-out and the per-candidate verify gate run through the harness-adapter dispatch mechanism — temper issues **no harness-specific call inline** (I1). On a harness with no parallel-subagent primitive, the adapter's sequential fallback runs the angles one pass per angle (it warns once that recall may drop).

**Build `T` from the kept records.** From the engine's kept eight-field records, `T` = the gating 2×2 of the contract (§3): every kept record whose verdict is `CONFIRMED` **or** `PLAUSIBLE` **and** whose severity is `Critical` **or** `Important`. `PLAUSIBLE@C/I` gates even without a runnable repro — that is the recall hole this model closes. (Reference `shared/severity-verdict-contract.md` for the gating rule; temper copies no table.)

**Identity key vs. adjudication payload (distinct).** Each member of `T` has:
- A **five-field identity / dedup key** — `{file, line, summary, severity, verdict}` — used to dedup `T` and carry a member forward across rounds. (A subset of the engine's eight-field record; `failure_scenario`, `scope`, `effort` are not needed to distinguish one member from another.)
- The **full originating eight-field delve-engine record** (delve-engine §6 — `{file, line, summary, failure_scenario, severity, verdict, scope, effort}`), retained per member keyed by that identity. This is the adjudication input the R2+ per-member re-verifier (Track B, Step 4) receives — it needs `failure_scenario` to re-derive REFUTED-after-fix / a code-based downgrade against the fixed code. The identity key is the carry-forward handle; the eight-field record is the adjudication payload.

Each member also carries a **transient `readjudicated` boolean** — per-round auxiliary state, **NOT** part of the identity key (two members with identical identity tuples are the same member regardless of `readjudicated`). Initialize a newly-enumerated R1 member to `readjudicated = false`.

**Empty-`T`-at-R1 short-circuit (guarded — two-part sanity check).** If the R1 engine drive (reached only past the Step 1.5 preflight) yields an **empty `T`**, short-circuit to **Clean** **only after both**:
1. **The engine actually executed (non-error).** Confirm a well-formed result (a list of kept records, possibly empty) — not a dispatch error, timeout, empty-string output, or a degraded "no subagent primitive" abort. An error result is **not** an empty `T`: do not short-circuit; surface it as a dispatch failure / re-attempt, never as Clean.
2. **`cap` did not truncate the GATING subset.** Key on the **Critical/Important kept-record count**, not the total kept count: short-circuit only if the C/I kept-record count is **strictly below `cap`** AND `T` is empty. (A non-gating Minor/Suggestion tail filling `cap` is harmless — a gating finding is lost to truncation only when the **C/I subset alone** reaches `cap`.) If the C/I kept-record count **equals or exceeds `cap`**, treat it as gating-subset truncation — do **not** short-circuit.

**Scope of this guard — empty-`T` only.** This C/I-saturation guard decides solely whether a genuinely-**empty** `T` may short-circuit to Clean. When `T` is **non-empty**, a cap-saturated C/I set means "proceed to fix a (large) `T`," **never** "re-run R1": the enumerated members are already a valid gating `T` and the loop proceeds to Step 3; R2+'s changed-region fan-out + cheap full-diff sweep (Step 4 Track A) re-hunts the whole range each round and admits any gating finding the R1 cap dropped.

**Bounded re-run (no unbounded loop).** When `T` is empty AND the C/I subset is cap-saturated, re-run R1 **exactly once** at a **doubled `cap`**:
- Non-empty `T` → proceed to fix `T` (Issues-Found path); no further re-run.
- Empty `T` with C/I subset now strictly below the doubled `cap` → genuine empty-`T`, short-circuit to Clean.
- Empty `T` but C/I subset **still** at/above the doubled `cap` → **do NOT re-run again.** Proceed with the (empty) `T` and emit a **`cap-saturation` signal** in the round metadata (analogous to `degraded-context`, Step 1.5) so the caller sees "the gating set could not be bounded under cap" — surfaced as a degraded/indeterminate verdict requiring human attention, **never** a clean Clean and never a runaway re-run loop. At most ONE doubled-cap re-run ever occurs.

If the C/I count is strictly below `cap` on the first run, no gating finding was truncated, so an empty `T` is genuine even if the non-gating tail consumed the rest of `cap` — short-circuit to Clean directly, no re-run.

**Per-invocation dispatch-id** (concurrency isolation). Every `/temper` invocation generates a unique dispatch-id at Step 1: `temper-YYYYMMDDTHHmmss-<6-char-nonce>`. Generate via a cryptographic RNG (e.g., `python -c 'import secrets; print(secrets.token_hex(3))'` for 6 hex chars). If a dispatch file path already exists on disk, regenerate the nonce and retry — never overwrite. The dispatch file path and the `metadata.dispatch_id` field both include this id, so concurrent invocations (e.g., user-initiated overlapping with build's Phase 4) cannot collide. Round numbering remains per-invocation; the dispatch-id disambiguates `(skill, round)` traceability tuples in the external_review MCP and in any session-log consumers. (The R2+ Track-B per-member dispatches extend this stem with a `-m<NN>` member suffix — see Step 4.) Dispatches are disk-mediated per `shared/dispatch-convention.md`: write the filled prompt/inputs to a dispatch file (one file per dispatch-id), then dispatch a Task subagent that reads that file — never paste inputs directly into the Task tool prompt.

#### Freshness Boundary

Temper's core principle ("fresh agent every round, no anchoring beyond the enumerated `T`") is convention-plus-mechanism. Each round uses a **fresh agent** — no reviewer reuse — with one deliberate, documented exception: the R2+ per-member re-verifier (Track B) **must receive `T`** (the enumerated tracked set is its input — that *is* fix-verification). The exception is scoped to `T` only.

The R2+ Track-B verifier receives, across the boundary, **only these inputs** and nothing else:
- The fixed code range to adjudicate against (the whole fixed tree per §3.8 — `{FIXED_BASE_SHA}` / `{FIXED_HEAD_SHA}`, see Step 4).
- Per member of `T`: its **full originating eight-field delve-engine record** keyed by the 5-field identity, plus the transient `readjudicated` flag.

It **must not** receive:
- Any prior-round **prose reports**, round narratives, or fixer rationale narrative (only the enumerated `T` records cross the boundary — not "everything the last round said").
- PR review comments (only PR title + body are pulled via the forge CLI; comments are out of scope).
- Commit messages / fixup-commit subjects — the verifier is instructed (in `temper-reviewer.md`) to read diff/code content only, not `git log`. The no-`git log` anchoring guard still holds; this shifts the boundary from orchestrator-side redaction (unenforceable, since the verifier runs its own `git`) to verifier-side discipline.
- Any out-of-band notes from the user "for the reviewer's awareness."

This boundary is what keeps round-N independent of round-N-1 apart from the sanctioned `T` carry. Step 5's optional post-to-PR happens *after* a round completes; on subsequent rounds the fresh agent is dispatched against the *fixed* code, and PR comments (which now contain prior findings) are excluded from the metadata fetch.

### Step 3: Act on feedback and iterate

- **Record `T` membership**, NOT a count. For each member persist its **five-field identity** (`{file, line, summary, severity, verdict}`), its full eight-field record, and its `readjudicated` flag. Convergence keys on the resolution status of these enumerated members — never on a Critical+Important count compared across rounds.
- Fix every member of `T`. A **`PLAUSIBLE@C/I`** member gets the **same fix priority as a `CONFIRMED`** one — it is a real regression the verifier could only call PLAUSIBLE for lack of a runnable repro, not a doubtful finding (per the contract / delve-engine). Fix priority follows **severity**, not verdict.
- Note Minor and Suggestion findings for later (non-gating — they never enter `T`; see Severity / Verdict Vocabulary below).
- Push back if a finding is wrong (with reasoning). Note that a repro-less `PLAUSIBLE@C/I` is **not** discharged by fixer prose — it discharges only via the §3.3 paths re-derived against the fixed code (Step 4).

### Step 4: Rounds 2+ — fix-verification loop

After fixing the members of `T`, each round R ≥ 2 runs **two SEPARATE dispatch tracks against the FIXED code**. They are not the same dispatch and not the same gate. Both use fresh agents (no reviewer reuse); the only prior-round input that crosses the freshness boundary is the enumerated `T` (§3.7, Freshness Boundary above).

**Fixed-region derivation (the `scope` Track A receives).** Per round R, compute the **incremental changed-region set** = the regions the fixer touched since the prior round's verification pass, PLUS a cheap full-diff regression backstop:
- **Committed mode** (HEAD advanced since R-1, `HEAD@R != HEAD@R-1`): fix delta = `diff(HEAD@R-1 .. HEAD@R)`.
- **Uncommitted mode** (fixes applied to the working tree, `HEAD@R == HEAD@R-1`): snapshot the working tree at each round boundary via **`git stash create`** (it builds a tree/commit object capturing tracked working-tree modifications and prints its SHA **without touching HEAD, the index, or the working tree** — the fixer is never disturbed; `crucible:checkpoint` is the documented fallback). Fix delta = `diff(snapshot@R-1 .. working-tree@R)`. Record each round's snapshot SHA in the per-invocation round metadata keyed by `(dispatch_id, round)` (the same structure carrying `readjudicated` flags and round verdicts); the snapshot is a dangling object addressed by SHA, kept out of `refs/`. Mode is selected **per round boundary** by checking whether HEAD advanced, so a run may switch modes round-to-round.
- **PLUS a cheap full-diff regression backstop** — a sweep over the whole `base..head` range, kept cheap (it is a backstop), to catch a regression outside the touched hunks that a narrow fix-delta scope would miss (the exact hole the old count-delta model had).
- **Cleanup:** snapshot objects are transient — at the END of the gate run (any terminal verdict) temper drops the recorded SHAs from its metadata; the dangling objects are then reclaimed by normal `git gc`. No snapshot survives past the invocation.

#### Track A — hunt NEW gating findings (delve-engine fan-out)

Drive `shared/delve-engine.md` over the round-R changed-region set above (incremental fix delta + cheap full-diff sweep) as `scope`, bug-angle subset, with `cap` set **explicitly HIGH** — well above the expected count of *new* gating findings a single round's fix can introduce (mirror R1's cap reasoning; the default `cap=10` is insufficient for a gating hunt). The fan-out proposes new candidates; each passes through delve-engine's **own verify gate** (one verifier per deduped candidate). **This is delve-engine's only R2+ job: hunting NEW findings** — the engine has no per-member re-verification input, so re-verification of `T` does **not** route through it.

A new candidate the gate assigns **CONFIRMED/PLAUSIBLE @ Critical/Important** is admitted to `T` with `readjudicated = false` (the new-member admission gate). **Raw fan-out output is never admitted directly**; an unverified, REFUTED, or below-C/I candidate stays out of `T`.

**Track-A `cap-saturation` signal.** Apply the same gating-subset truncation check Step 2 applies at R1: if the Track-A **Critical/Important kept-record count reaches `cap`** (equals or exceeds it), the admitted new-finding set may be truncated — a new gating finding the fix introduced could sit above the cap. In that case the round is **not** read as a clean "no new gating finding entered"; surface a `cap-saturation` signal in the round metadata. The Clean condition's "no new gating finding entered" (Done When) is satisfiable only when Track-A's C/I kept-record count is **strictly below `cap`** (gating set provably un-truncated). (Key on the C/I subset, not the total kept count — a non-gating tail filling `cap` is harmless.)

#### Track B — re-verify each `t ∈ T` (temper-owned per-member dispatch)

Re-verification is **temper-owned**, separate from the engine fan-out. For each member `t ∈ T`, dispatch **one fresh `temper-reviewer.md` adjudicator** (one per member) to adjudicate **that single member** against the **WHOLE round-R fixed tree**. `temper-reviewer.md` re-applies the **contract's** verdicts/severity (CONFIRMED / PLAUSIBLE / REFUTED + severity, per `shared/severity-verdict-contract.md` §2) to the fixed code — it defines **no** verdict vocabulary of its own (I11) and needs **no** delve-engine input. It is a temper template, dispatched through the harness-adapter subagent mechanism, fed the member's full eight-field record — **not** a delve-engine verify-gate adjudicator.

**Track-B adjudication range = the WHOLE FIXED TREE, never the incremental delta** (the most important Track-A-vs-Track-B distinction). For each member the adjudicator re-checks `t.failure_scenario` against `original base .. round-R fixed-tree`:
- **Uncommitted mode:** `original base .. working-tree-snapshot@R` (the `git stash create` snapshot SHA), NOT `diff(snapshot@R-1 .. working-tree@R)`.
- **Committed mode:** `original base .. HEAD@R`.

A member's `failure_scenario` may live in code the fixer did **not** touch this round; if Track-B re-verified against only the incremental delta, that member's code would be absent from the diff and the adjudicator would falsely conclude **RESOLVED-by-absence**, re-opening the recall hole. Re-verifying against the whole fixed tree guarantees a member whose defect persists in unchanged code is correctly re-affirmed STILL-GATING.

**Per-member dispatch contract (Track-B slots — see §5 of the plan / `temper-reviewer.md`):**
- `{MEMBER_RECORD}` — the full eight-field delve-engine record for the single member being adjudicated, JSON-serialized, keyed by its 5-field identity. `failure_scenario` is the construct re-checked against the fixed code.
- `{FIXED_BASE_SHA}` = the **original base** (the same base R1 enumerated against — NOT the prior round's HEAD/snapshot).
- `{FIXED_HEAD_SHA}` = the **round-R fixed-tree ref** — the `git stash create` snapshot SHA (uncommitted mode) or `HEAD@R` (committed mode).
- `{READJUDICATED}` — the member's transient `readjudicated` flag carried across the boundary; the adjudicator **sets** the flag on emitting its per-member outcome (feeds the §3.5 defer-once-only bookkeeping).

**One-dispatch-file-per-member rule.** N members in a round ⇒ **N per-member dispatch files**, each adjudicating exactly one member — there is no aggregate "review all of `T` in one dispatch." This preserves fresh-eyes isolation per member.

**Per-member dispatch-id scheme.** Each per-member dispatch extends the per-invocation stem (`temper-YYYYMMDDTHHmmss-<6hex>`, Step 2) with a zero-padded **member-index suffix `-m<NN>`** (e.g. `temper-20260603T101500-a7f3c2-m01`, `…-m02`). Sharing the round stem but differing in `-m<NN>` means N concurrent per-member dispatch files cannot collide on disk; if a generated path already exists, regenerate-and-retry / never-overwrite as for the base id. Each per-member `metadata.dispatch_id` carries the full `…-<6hex>-m<NN>` id.

(R1 dispatches no `temper-reviewer.md` — it is pure delve-engine enumeration. Track A never uses `temper-reviewer.md`; `temper-reviewer.md` is the Track-B per-member re-verifier only.)

#### Per-member outcomes (no temper-owned vocabulary, I11)

`temper-reviewer.md` re-applies the contract verdicts/severity to the fixed code and emits, per member, one of:
- **RESOLVED** — re-applying the contract verdict no longer establishes the defect (it would now be REFUTED, or the construct/path is gone). Member leaves `T`.
- **REFUTED-after-fix** (repro-less `PLAUSIBLE@C/I` only) — the adjudicator actively **re-derives the contract's REFUTED verdict** against the fixed code (the suspect construct is provably gone). A **DISCHARGE** — member leaves `T`. (Same REFUTED verdict from the contract, re-applied; temper coins no new verdict.)
- **DOWNGRADED** (code-based) — the adjudicator re-assigns `severity` per the contract's scale to a tier below C/I against the fixed code → it leaves the gating 2×2 (folds to Minor/Suggestion, reported verbatim). A **DISCHARGE** — member leaves `T`.
- **STILL-GATING** — re-applying the contract re-affirms CONFIRMED/PLAUSIBLE @ C/I against the fixed code → stays in `T`.
- **ESCALATE** (repro-less `PLAUSIBLE@C/I` only) — the adjudicator can **neither** re-derive REFUTED **nor** downgrade → the member is **escalation-eligible** (architectural / human-ack path, §3.3).

#### Discharge path for repro-less `PLAUSIBLE@C/I` members (§3.3)

A repro-less `PLAUSIBLE@C/I` could otherwise trap `T` non-empty forever. Each round the adjudicator **RE-ADJUDICATES** it against the fixed code. It discharges **ONLY** by becoming **REFUTED-after-fix** or by a **code-based severity downgrade below C/I**. It **NEVER** discharges on **fixer rationale alone** — prose-discharge of a repro-less PLAUSIBLE is the exact recall hole this redesign closes.

A member the adjudicator can neither re-derive-REFUTED nor downgrade is **escalation-eligible**. Escalation is **NOT** a DISCHARGE: such a member is neither RESOLVED nor DISCHARGED, so it **stays LIVE in `T` and BLOCKS Clean**. It does **not** silently leave `T` to permit a Clean in the same run — instead the **loop** routes to the terminal **Architectural** verdict (handing it to human-ack) once the previously-seen unresolved subset is solely escalation-eligible (branch table below). It leaves the loop *by escalating*, never by silent accept. (The fixer-rationale-the-verifier-accepts path remains available **only** for genuinely-CONFIRMED findings the fixer argues are false positives — the verifier still adjudicates the rationale — and does **not** apply to repro-less `PLAUSIBLE@C/I`.)

#### Verdict logic (§3.4 / §3.5)

**New-member admission gate.** A new gating finding enters `T` in round R **only after** Track A's verify gate assigns it CONFIRMED/PLAUSIBLE @ C/I; it initializes `readjudicated = false`.

**"Previously-seen" boundary.** A member is **previously-seen in round R iff it was in `T` at the END of round R-1.** A member admitted in round R is **NOT previously-seen until R+1** — so in its admitting round it cannot trip Stagnation. R1's enumerated `T` is the end-of-R1 set; members survive into R2 as previously-seen. R1 has no prior round, so Stagnation can never fire on R1.

Evaluate the round (the Stagnation / branch-table logic is subordinate to escalation):

- **Clean** = every member of `T` is **RESOLVED or DISCHARGED** (RESOLVED, or DISCHARGED via §3.3 — REFUTED-after-fix or a code-based downgrade-below-C/I only) **AND** no new gating finding entered this round. An escalation-eligible unresolved member is **neither RESOLVED nor DISCHARGED**, stays live in `T`, and **BLOCKS Clean** — temper never emits Clean while a live escalation-eligible member is in `T` (I6). Such a member leaves the gate by the loop routing to **Architectural**, never by silent removal so a Clean can be emitted.
  - **A new-admit round is NEVER Clean (→ Issues-Found).** Any round in which Track A admits **≥ 1 new gating member** is non-Clean and resolves to **Issues-Found** (loop continues) — **regardless of how the carried `T` resolved that round.** Even if every previously-seen member RESOLVED/DISCHARGED, the "no new gating finding entered" condition fails. The new member enters with `readjudicated = false` and becomes Clean-blocking and Stagnation-eligible only from R+1. Clean is reachable only in a round that **both** resolves/discharges all carried members **and** admits no new gating finding.
- **Issues Found** = `T` has unresolved members; loop continues. (Reported into the round report, but loop-continuing — not a terminal verdict.)
- **Stagnation** = the **previously-seen unresolved subset** of `T` does **NOT shrink** across two consecutive (non-deferred) rounds — no previously-seen member became resolved/discharged. Judged **only** on the previously-seen unresolved subset; fires **regardless of newly-admitted members** (resolving one old member while admitting one new is progress; resolving zero old members while admitting new ones trips Stagnation). The earliest evaluation is R2-vs-(end-of-R1). **Termination is guaranteed by the round cap (Max-Rounds), NOT by Stagnation** — Stagnation is an early-exit optimization. A **Defer round does NOT count** in the consecutive-round sequence (it is skipped; the next non-deferred round compares against the last non-deferred prior evaluation). Earliest a member whose only prior round was its defer can FIRE Stagnation is **R+2** (eligible to contribute a non-shrink observation at R+1; two consecutive non-deferred non-shrinking evaluations are required to fire).
- **Defer one round** (TRANSIENT continuation outcome) — continues the loop (like Issues-Found), **suppresses Stagnation this round** (the branch fired instead of declaring Stagnation), and **consumes one round against Max-Rounds**. **Once-only per member**, keyed on `readjudicated`: deferring **sets** the flag; a member whose flag is already set does NOT defer again. Not a merge verdict the user sees.

**Before declaring Stagnation, branch on WHY the non-shrinking previously-seen unresolved subset did not shrink** (these rows are EXHAUSTIVE over composition of a **non-empty, non-shrinking** subset — the empty case is Clean / Issues-Found, not here; the verdict is total, no silent fall-through to Max-Rounds):

| Subset composition (non-empty, non-shrinking) | Verdict |
|---|---|
| SOLELY escalation-eligible members (repro-less `PLAUSIBLE@C/I` the adjudicator can neither re-derive-REFUTED nor downgrade) | **Architectural** (needs human adjudication — not wheel-spinning) |
| SOLELY members not yet re-adjudicated this round (`readjudicated == false`) | **Defer one round** (give each its re-adjudication pass) |
| **MIXED** escalation-eligible + not-yet-re-adjudicated, with **NO** genuinely-stuck member | **Defer one round** (next round reduces to SOLELY escalation-eligible → Architectural, or shrinks normally) |
| **Any subset containing ≥1 genuinely-stuck member** (`readjudicated == true` AND not escalation-eligible AND still unresolved), regardless of what else it contains | **Stagnation** (real churn: a member that could resolve via fix but the fixer keeps failing) |

- **Stagnation is SUBORDINATE to escalation.** When the previously-seen unresolved subset is SOLELY escalation-eligible, the loop routes to **Architectural** immediately — it does **NOT** wait for the 2-round Stagnation antecedent.
- **"Genuinely stuck" = `readjudicated == true && !escalation-eligible && unresolved`** — it has had its re-verification pass against the fixed code and is still gating, and is not escalation-eligible. Fully observable (no counterfactual). A member still `readjudicated == false` is awaiting its first re-verification pass (→ Defer), not genuinely stuck.
- **Defer is regrounded on a RE-VERIFICATION event, not a fix event** — a member defers iff it has not yet had a Track-B re-verification pass against the fixed code since its admitting round (exactly `readjudicated == false`). "Fix-attempted" cannot distinguish a defer-eligible member from a stuck one (Step 3 fixes all unresolved C/I every round, so a carried member was already fix-attempted in its admitting round).
- This table operates over the **previously-seen** unresolved subset only; a member admitted *this* round contributes nothing to any row, so the "SOLELY not-yet-re-adjudicated" row is populated by previously-seen members carried in still `readjudicated == false`, never by freshly-admitted ones.
- **Drip caveat:** under continuous new-member admission (each round Track A admits a fresh finding that defers once), Stagnation may never fire — Max-Rounds is then the operative terminator. Correctness-safe (the loop still halts at the cap, no false Clean); confirms Stagnation is an optimization, not the termination guarantee.

#### Max-round circuit breaker

The loop is bounded by **5 rounds** by default — the **termination guarantee** (Stagnation is only an early-exit optimization). At round `max_rounds` without a terminal verdict, escalate to the user with `T`'s unresolved members:

> "Temper reached the {max_rounds}-round cap without resolving every member of the tracked set `T`. Unresolved members: [{file:line — summary — severity/verdict} for each live member of `T`]. To extend, re-invoke `/temper <scope> max_rounds=N` — this starts a **fresh review loop** with a higher cap (the new loop re-enumerates `T` from scratch; round counting restarts at 1, and the fresh agents have no anchoring from prior rounds beyond a re-enumerated `T`). If the remaining members appear structural rather than fixable in another loop, escalate to design / plan instead."

Callers (build Phase 4) treat the cap escalation as a soft block: the diff is not approved; the user decides whether to extend, refactor, or accept the remaining members. Overridable via trailing `max_rounds=<N>`; defaults to 5 to keep runaway protection on by default.

#### Done When

The outcomes split into **four terminal merge verdicts** (the loop settles on exactly one and STOPS) and **two non-terminal loop-continuation outcomes** (the loop CONTINUES). Do **not** call this "five terminal verdicts."

**Terminal merge verdicts (loop STOPS):**
- **Clean** — every member of `T` is RESOLVED or DISCHARGED (§3.3 only), AND no new gating finding entered this round. Caller may proceed.
- **Stagnation** — the previously-seen unresolved subset did not shrink across two consecutive non-deferred rounds AND the subset contains ≥1 genuinely-stuck member (branch table). Caller escalates to user.
- **Architectural** — the previously-seen unresolved subset is solely escalation-eligible (repro-less `PLAUSIBLE@C/I` the adjudicator can neither re-derive-REFUTED nor downgrade), or any round emits an architectural concern. Caller escalates immediately, regardless of round number (subordinate-to-escalation: this pre-empts the Stagnation antecedent).
- **Max-Rounds** — `max_rounds` reached without a terminal verdict. The termination guarantee. Caller escalates with `T`'s unresolved members.

**Non-terminal loop-continuation outcomes (loop CONTINUES):**
- **Issues-Found** — `T` has unresolved members (or a new gating finding was admitted this round). **Reported into the round report but loop-continuing** — it is emitted (so it appears in the caller-visible verdict set) yet does not terminate the loop.
- **Defer-one-round** — the sanctioned one-round grace (once-only per member, keyed on `readjudicated`). An internal continuation state the user does not see as a merge verdict; it suppresses Stagnation that round and consumes one round against Max-Rounds.

### Step 5 (optional) — Post findings to the PR

This step is an **output convenience, not part of the review contract** — findings are complete after Step 4 regardless of whether they're posted. It exists for users who want the local review surfaced on the PR for asynchronous collaborators.

If the user explicitly asks ("post this to the PR", "leave a review comment"), publish using whichever CLI fits the forge:

- GitHub → `gh pr review <id> --comment --body-file <findings.md>`
- GitLab → `glab mr note <id> -m "$(cat findings.md)"`
- Bitbucket → `bb pr comment <id> --file findings.md` (or REST)
- Unavailable / unknown forge → output the formatted body for the user to paste

**Confirm success explicitly.** Check the CLI's exit code. On non-zero exit, classify the failure mode and respond per the table below — do not silently skip:

| Failure mode | Response |
|---|---|
| Auth-fail (`gh auth status` failure / token expired) / rate-limit (403) / network error | Paste-mode with retry guidance: "Posting failed with `<error>` — re-authenticate / wait and retry, or paste the body manually below." |
| PR closed-without-merge | Paste-mode with conditional guidance: "PR is closed; if you intend to reopen, paste the body. Otherwise the findings remain in your session." |
| PR merged or deleted | Do **not** offer paste-mode. Surface the findings locally: "The PR is no longer postable (merged / deleted). Findings remain in your session for reference." |

Never post without an explicit user instruction. Findings live in the user's session by default.

## Terminal Verdict Emit

<!-- CANONICAL: shared/ledger-append.md -->

When temper reaches a **terminal merge verdict** — whether the loop settles on one (Done When — Clean, Stagnation, Architectural, or Max-Rounds), the `cap-saturation` degraded/indeterminate loop-exit (Step 2/4), or a **pre-loop Step 1.5 preflight short-circuit** (empty / binary-only / submodule-pointer-only diff) that terminates before any engine dispatch; **never** on the loop-continuation outcomes Issues-Found / Defer-one-round — emit ONE **Tier A** JSONL line to the **central ledger** (`~/.claude/crucible/ledger/runs.jsonl`, override `CRUCIBLE_LEDGER_DIR`) via the `emit` CLI per the canonical protocol at `skills/shared/ledger-append.md` — resolve `scripts/ledger_append.py` by absolute path from the plugin root and run `python3 <script> emit - '<json>'` (`-` = central default). The `emit` CLI owns the mechanics: it honors `CRUCIBLE_CALIBRATION_DISABLED=1` as a graceful skip, dedups by `(run_id, skill="temper")` (L-2), and auto-fills `repo` + `schema_version`. If the script can't be resolved, warn to stderr and skip — a missing emit must NEVER block or alter the merge verdict.

**Emit precondition — suppress the zero-files Clean.** If the terminal verdict is the empty-diff Clean short-circuit (Step 1.5, `Clean — no changes to review`, Reason: empty-diff) — or, more generally, any verdict whose resolved `gated_files` is empty — **skip the emit entirely and write NO row.** A review of zero files carries no falsifiable calibration signal: a Clean over an empty `gated_files` would produce a degenerate `predicted_falsifier` (`fix touching  within 30d`) that `reconcile_ledger.py`'s `parse_predicate` rejects as unparseable, polluting temper's unparseable-rate, and would also breach the canonical "MANDATORY non-null `predicted_falsifier` on a code PASS" rule. So this short-circuit emits nothing.

The other two **Step 1.5 preflight short-circuits** map as follows, so none is left to the emitter's guess. (a) **Binary-only diff** surfaces `Architectural — binary-only diff requires human review`; emit it as `verdict: ARCHITECTURAL` (with `predicted_falsifier: null`, like every Architectural exit) — its `gated_files` is non-empty but the content was unreviewable, so it is an Architectural human-review escalation, not a Clean. (b) **Submodule-pointer-only diff** raises a Suggestion and explicitly never produces a Clean; it has no terminal Done-When verdict and no reviewable code content, so — like the empty-diff Clean — it is a no-falsifiable-signal review: **suppress the emit entirely, write NO row.**

temper is the merge gate, so its `Clean` (PASS) is the single most-falsifiable verdict in the suite: `reconcile_ledger.py`'s falsification walker mines post-merge `fix/*`/`hotfix/*` branches — the exact evidence that a Clean verdict was wrong. Construct the entry from **in-process verdict state** (do NOT re-parse any on-disk artifact):

- `schema_version: 2`, `run_id` (UUIDv7 via `scripts/uuid7.py`), `skill: "temper"`, `tier: "A"`, `artifact_type: "code"` (temper always reviews a code diff), `timestamp` (ISO-8601 UTC).
- `verdict` — map temper's terminal merge verdict onto the ledger enum: **Clean → `PASS`**, **Stagnation → `STAGNATION`**, **Architectural → `ARCHITECTURAL`**, **Max-Rounds → `ESCALATED`**, **cap-saturation / degraded-indeterminate exit → `ESCALATED`** (it reached no determinate conclusion — "**never** a clean Clean" and not an Architectural structural conclusion — so it is an escalation). (temper never writes `FAIL` or `SUSTAINED_REGRESSION`.)
- `gated_files` — the changed files in the resolved review scope (`git diff --name-only` over the range, repo-relative), known at verdict time from Step 1.
- `artifact_hash` — sha256 hex of the reviewed diff/artifact bytes; `chunk_hash: null` (temper does not chunk).
- `confidence: null` — temper produces **no** scalar terminal-verdict confidence anywhere in its workflow (it emits verdicts + per-finding severity, never a terminal-verdict confidence number), so it emits `confidence: null` rather than inventing one. `reconcile_ledger.py`'s Brier admission gate (`if not isinstance(confidence, (int, float)): continue`, plus `MIN_CONFIDENCE = 0.5`) cleanly excludes `null`, so temper rows contribute **no** Brier sample — a freely-invented number would instead make temper's Brier meaningless and bias it high. temper's calibration signal is the **`predicted_falsifier` hit-rate** (the meaningful signal for a merge gate), not a confidence score.
- `severity_histogram: null`, `findings_count: null`, `highest_finding: null` — temper gates on its own sanctioned trio scale (`T = {CONFIRMED, PLAUSIBLE} × {Critical, Important}`), and **no sanctioned conversion** exists from that trio scale to the ledger's separate severity-rubric histogram scale (fatal/significant/minor/nit) — `shared/severity-verdict-contract.md` §5 states "**No normative conversion exists**" and the reader-intuition correspondence is explicitly "never a computed mapping" you may build a rule/score/gate on. So temper emits these count-family fields **null** — like a Tier-B stub on the count axis — while remaining **Tier A** on the prediction axis (it still carries `verdict`, `gated_files`, and a non-null `predicted_falsifier` on a non-empty-diff PASS; `confidence` is `null` — see above).
- `would_have_shipped_without_gate: null` — mechanically `null` whenever `severity_histogram` is `null`, per the canonical L-3 rule. Do not set it by hand.
- `rounds` (total round count), `gated_files_truncated: 0`, `comment: null`, `backfilled: false`, `falsified: null`, `falsified_by: null`.
- `predicted_falsifier` — set a pre-registered, machine-checkable predicate ONLY on a **PASS that reviewed a non-empty diff** (Clean with non-empty `gated_files`); the empty-diff Clean emits no row at all (see the emit precondition above), so the pf question never arises for it. Use the canonical grammar `fix touching <gated_files joined by ","> within 30d` — the file-list is itself a **comma-joined set of patterns** the reconciler ORs together (`_predicate_fired`: a candidate fires when any touched file matches **any** pattern). Prefer the explicit comma-joined verbatim file list whenever it fits under the 256-char cap. Only when it would exceed the cap, collapse it to a **comma-joined list of per-directory globs**: replace each touched file `dir/.../name` with its **immediate-parent-directory glob** `dir/.../*` and dedupe, yielding one `*` glob per distinct parent directory — except a touched file at the **repo root** (a single path segment, no parent directory) is emitted **verbatim** and **never** collapsed to a bare `*` glob, since `_glob_match` would match a bare `*` (1 segment) against every root-level file (1 segment) and over-credit an unrelated root-file fix as a falsification. This is depth-correct because the reconciler's matcher treats `*` as **not** crossing `/` (`_glob_match` requires equal segment counts), so `src/auth/sub/*` covers `src/auth/sub/token.ts` while `src/auth/*` covers `src/auth/login.ts` — a **single** common-prefix glob like `src/auth/*` is wrong precisely because it cannot match files at a deeper level (`src/auth/sub/token.ts`), under-reporting falsifications. If even the deduped per-directory glob list does not fit under the cap, emit the **verbatim comma-joined file list truncated to the cap** (drop whole trailing patterns; never a single shallower glob). Full grammar in the `predicted_falsifier` protocol of `shared/ledger-append.md`. For every escalation verdict (`STAGNATION` / `ARCHITECTURAL` / `ESCALATED` — the last now including the cap-saturation/degraded-indeterminate exit mapped to `ESCALATED`) set it `null`. Net: pf is non-null **only** on a non-empty-diff PASS; `null` on STAGNATION / ARCHITECTURAL / ESCALATED; and absent (no row) on the empty-diff Clean. Do NOT write the retired `"<DEFERRED:pre-phase-7>"` sentinel.

**Tool:** Bash (run the `emit` CLI). Emit AFTER the verdict is settled and surfaced; the emit is advisory and never gates.

## Dispatch

temper drives `shared/delve-engine.md` through the harness-adapter **fan-out mechanism** (`shared/harness-adapter.md` §4, §7), disk-mediated per `shared/dispatch-convention.md` — never a harness-specific call inline (I1). Round 1 drives the engine (high effort, bug-angle subset) to enumerate the tracked set `T`; Rounds 2+ re-hunt the changed range the same way. Where a harness has no parallel-subagent primitive, the adapter's **sequential fallback** (§5) runs the angles as multiple sequential passes, warning once that recall may drop.

temper is one of the **exactly two** files that dispatch `delve-engine` directly (the other is `delve`). The canonical engine-dispatch marker line follows; the I2 allowlist test keys on it with the anchored pattern `grep -rn '^dispatch: delve-engine'`:

dispatch: delve-engine

## Severity / Verdict Vocabulary

temper defines **no** severity scale and **no** verdict vocabulary of its own (I11). The four-tier severity scale (Critical / Important / Minor / Suggestion), the verify-gate verdicts (CONFIRMED / PLAUSIBLE / REFUTED), and the gating rule are the contract's — see `shared/severity-verdict-contract.md` (canonical-included in the header; this section references it, it does **not** copy its tables).

### The gating rule (tracked set `T`)

Convergence keys on the **tracked set `T`**, computed by temper from the engine's `{severity, verdict}` kept records per the contract §3:

> **`T` = { CONFIRMED, PLAUSIBLE } × { Critical, Important }**

A kept finding enters `T` **iff** its verdict is CONFIRMED or PLAUSIBLE **and** its severity is Critical or Important. A `PLAUSIBLE@C/I` gates even without a runnable repro (the recall hole this model closes). Minor and Suggestion are **both non-gating** — they never enter `T` (reported verbatim, never dropped). See the contract's full verdict × severity matrix; temper adds nothing to it. There is **no** count-delta mapping and **no** Suggestion-folding-into-Minor: convergence is the resolution status of `T`'s enumerated members, never a count.

### Verdict synonyms

Two parallel vocabularies for temper's **merge verdict** exist for historical reasons; temper recognizes both as synonyms:

| Canonical | Accepted synonym |
|---|---|
| **Clean** | **Approved** |
| **Issues Found** | **Needs Fixes** |
| **Architectural** | **Architectural Concern** ≡ **Escalate** |

The left column is canonical; the right-column synonyms remain accepted to avoid breaking older callers.

### temper merge-verdict set (Done When taxonomy)

These are temper's **loop outcomes** — distinct from the contract's per-finding verify-gate verdicts above. **Four terminal merge verdicts:** Clean, Stagnation, Architectural, Max-Rounds. **Two non-terminal loop-continuation outcomes:** Issues-Found (reported but loop-continuing) and Defer-one-round (internal continuation state). Each is defined in **Done When** (Step 4).

## External Model Review (Optional)

When enabled, `external_review` is a **candidate source for the R1 verify gate**, not a parallel scored reviewer. External findings inject into delve-engine's `external_candidates` input on **Round 1 only**; the **same verify gate** adjudicates them (CONFIRMED / PLAUSIBLE / REFUTED + severity) before any can enter `T`. They never bypass the gate and never run as a separate scored pass.

- **`external_review=skip`** (default-on stays): no external candidates; delve's fan-out is the only candidate source.
- **enabled:** external findings inject into the R1 `external_candidates` feed; the verify gate adjudicates them cross-origin with the internal fan-out candidates. R1-only.

**Prose → `external_candidates` DRAFT transform (the wiring step).** temper's `external_review` step emits free-form prose findings; delve-engine's `external_candidates` input (delve-engine §2) takes a list of **DRAFT** records, each `{file, line, summary, severity}` with **NO verdict**. So temper converts each external prose finding into one draft record: extract `file`/`line` from its location, `summary` from its one-line what-and-where, and a **severity DRAFT hint** from its stated severity. Per delve-engine §2/§5: any inbound `verdict` is discarded (the verify gate is the sole verdict authority) and the inbound `severity` is a **draft hint only** that the gate re-assigns per the contract — so a malformed/over-stated external severity cannot inject an authoritative Critical. The drafts merge into delve-engine's pre-dedup candidate pool and are adjudicated alongside the internal fan-out candidates.

**Cadence (R1-only) + documented limitation.** External candidates are gathered **once per `/temper` invocation, on Round 1 only** — to second-opinion the initial finding set without multiplying external-API cost across the fix loop. R2+ do **not** re-run external_review: an external candidate REFUTED on R1 cannot re-enter `T`; fix-introduced regressions are caught by delve's own R2+ fan-out (changed-region scan + cheap full-diff sweep, Step 4 Track A), not by re-running external_review.

**Re-invocation skip rule:** Re-invoking `/temper` via `max_rounds=N` after a stagnated run normally triggers another R1 external candidate gather. To avoid redundant external API spend on essentially-the-same diff, pass `external_review=skip`. (No automatic same-diff detection — skip is explicit-only.)

Gather external candidates by calling `external_review` with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: the same diff and requirements context the R1 engine drive receives
- `skill`: `"temper"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "temper", "round": 1, "dispatch_id": "<from Step 2>"}` (traceability)

**Per-skill toggle:** The server checks the `skill` argument against `skills.temper` in the external review config. If `false`, the server returns `unavailable` and temper gathers no external candidates. **Server hyphen-normalization:** `mcp-servers/crucible-consensus/server.py` normalizes hyphens to underscores in the skill name before lookup, so a hyphenated skill name (`red-team`) and its underscored form (`red_team`) resolve to the same toggle. Today temper has no hyphen — the contract works trivially — but the rule is documented here for future renames.

**Config-rename note for opt-out users.** The toggle key was renamed from `code_review` to `temper` on 2026-05-17. If you previously set `skills.code_review: false` to opt out, **rename the key to `skills.temper: false`** to preserve your opt-out. Otherwise the toggle inherits the default `True`.

**Graceful degradation → skip (gather no external candidates, ≡ `external_review=skip`).** When the external source is degraded, temper silently gathers no external candidates and the engine run proceeds on its own fan-out:
- `external_review` tool not available (MCP server not running): gather none.
- Response `status` is `"unavailable"` (no config or disabled): gather none.
- Response `status` is `"partial"` (some models failed): feed the available external findings as drafts; note which models failed.

Either way the R1 engine drive proceeds — the external feed never blocks or delays it; on external failure the fan-out stands alone.

## Cross-Reference to Deep Cloud Review

For GitHub PRs only, Claude Code's built-in `/ultrareview <PR>` runs a deeper multi-agent review in a cloud sandbox. After a local `/temper` round, suggest `/ultrareview` to the user when **either** of these holds:

- The round's findings span **≥2 distinct delve-engine finder angles** (e.g. a line-by-line defect *and* a cross-file mismatch, or a removed-behavior regression *and* a quality concern — angles defined in `shared/delve-engine.md` §4), **OR**
- The user explicitly wants a second opinion before merge on a high-stakes change.

"Distinct angles" means the engine's finder angles, not severity tiers — the trigger is breadth of issue surface, not depth of any single issue.

`/ultrareview` is GitHub-specific; **do not suggest** it for GitLab / Bitbucket / other-forge PRs.

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request review before proceeding.

[Step 1: Resolve scope]
- No argument given; HEAD is on branch `feat/verify`
- gh pr view (current branch) → no PR yet
- origin/HEAD → main; resolved range: origin/main..HEAD
- BASE_SHA=$(git rev-parse origin/main)
- HEAD_SHA=$(git rev-parse HEAD)

[Step 1.5: Preflight]
- numstat: 4 files changed, 87 added, 12 deleted — text diff, in-cap, proceed

[Step 2: Round 1 — drive delve-engine (bug-angle subset, effort=high, cap=20), dispatch-id temper-20260603T150500-a7f3c2]
  Engine ran non-error; C/I kept-count (2) < cap → T genuine, not truncated.
  Enumerate T (2 members):
    t1  verify.py:40  CONFIRMED / Important  — no error handling for empty input
    t2  verify.py:55  PLAUSIBLE / Important  — progress callback may fire after cancellation (no runnable repro)
  Minor: 1 (magic number) — non-gating, not in T.
  Each member: readjudicated=false.

You: [Fix both members of T — t2 (PLAUSIBLE@Important) gets the same fix priority as t1 (CONFIRMED)]

[Step 4: Round 2 — Track A (delve-engine over fix delta + cheap full-diff sweep, cap=20) + Track B (one temper-reviewer per member, against the WHOLE fixed tree)]
  Track B — re-verify carried members:
    t1 → RESOLVED (empty-input guard now present)
    t2 → REFUTED-after-fix (DISCHARGE: the post-cancellation callback path is provably gone) — leaves T
  Track A — NEW gating finding admitted to T (readjudicated=false):
    t3  verify.py:48  CONFIRMED / Important  — the new guard swallows a real I/O error
  All carried members resolved/discharged, BUT a new gating finding entered this round.
  → Verdict: Issues-Found (NOT Clean — a new-admit round is never Clean). Loop continues.

You: [Fix t3]

[Step 4: Round 3 — Track A + Track B]
  Track B — re-verify carried member:
    t3 → RESOLVED (I/O error now re-raised)
  Track A — no new gating finding admitted; C/I kept-count (0) < cap (un-truncated).
  Every member of T resolved/discharged AND no new gating finding entered.
  → Verdict: Clean. Proceed to Task 3.
```

The Round-2 verdict is **Issues-Found, not Clean**, even though both carried members resolved — Track A admitted a new gating finding (`t3`), and a new-admit round is never Clean. Clean is reached only in Round 3, which resolves the carried member and admits no new gating finding.

## Test Alignment

When behavioral changes were made, consider dispatching `crucible:test-coverage` after temper completes. This catches stale tests, missing coverage, or assertion drift introduced by the fixes.

**Caller context determines who runs it:**
- **Pipelines (build / debugging / finish):** the pipeline orchestrator dispatches `crucible:test-coverage` automatically — temper does not.
- **Standalone / ad-hoc:** the user (or whoever invoked `/temper` directly) is responsible for the hand-off. Recommend `crucible:test-coverage` when the review noted behavioral changes that might affect existing tests, when the diff modified functions with dedicated test files, or when the reviewer said "tests should be updated" without specifics.

This is the single canonical statement of the rule; the workflow sections below cross-link rather than restate.

## Integration with Workflows

**Build pipeline (Phase 4):** Temper runs after each task. Build dispatches `crucible:test-coverage` automatically (see Test Alignment).

**Standalone plan execution:** Temper after each batch (3 tasks). The user dispatches `crucible:test-coverage` afterward if behavioral changes were made.

**Ad-hoc development:** Temper before merge, when stuck, after a complex bug fix. The user dispatches `crucible:test-coverage` afterward if behavioral changes were made.

**Migration note — pre-rename retrospectives.** `crucible:forge` retrospectives written before 2026-05-17 are tagged with `code_review`. Forge's consult-past-lessons step does not auto-alias; if you want the old lessons to surface for `temper`, query both keys. (Out of temper's scope to fix; flagged here so users know.)

## Red Flags

**Never:**
- Skip temper because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback
- Skip re-review after fixes ("the fixes look fine")
- Reuse the same reviewer subagent across rounds
- Pass prior-round prose / commit messages / fixer rationale to the next agent — only the enumerated `T` records cross the freshness boundary (see Freshness Boundary)
- **Compare Critical+Important counts across rounds** — convergence is the resolution status of `T`'s enumerated members, never a count delta
- **Discharge a repro-less `PLAUSIBLE@C/I` member on fixer prose** — it discharges only via REFUTED-after-fix or a code-based downgrade re-derived against the fixed code (§3.3)
- **Defer a member twice** — Defer-one-round is once-only per member (keyed on `readjudicated`)
- **Emit Clean in a round that admitted a new gating finding**, even if every carried member resolved — that round is Issues-Found
- Hardcode `gh` (or any single forge's CLI) in the dispatch path — temper is forge-agnostic
- Silently fall through on a CLI **error** (vs missing-CLI) — surface the failure to the user
- Run past the 5-round circuit breaker without explicit user instruction
- Post to a PR without explicit user instruction
- Silently skip Step 5 on auth-fail / closed-PR / rate-limit — fall through to paste-mode

**If the reviewer is wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: `temper/temper-reviewer.md`
