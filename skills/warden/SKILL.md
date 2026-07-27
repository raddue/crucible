---
name: warden
description: 'Consolidated pre-push review gate — runs the full reviewer set (temper, delve, red-team, plus siege/inquisitor when the diff warrants) as one gate and emits a single PASS/BLOCKED verdict. Use when you want the *complete* pre-push bar in one call — "gate this before I push", "run the full review gate", "run all the reviewers", "warden". NOT for a single-reviewer pass: a fresh-eyes code review stays with temper, red-teaming a design/plan stays with quality-gate, a bug-hunt on a diff stays with delve.'
---

# Warden

<!-- CANONICAL: shared/dispatch-convention.md -->
<!-- CANONICAL: shared/return-convention.md -->

## Overview

warden is an **orchestrator-tier pre-push review gate** — a peer of
build/finish/quality-gate, not a find-and-report-only leaf reviewer. It
consolidates the pre-push review passes (temper, delve, red-team, plus
siege/inquisitor when the diff warrants) into a single gate that emits one
PASS/BLOCKED verdict. Like build and finish, warden is permitted to drive
fixes; the report-only rule binds only leaf reviewers.

warden runs each reviewer on its **own** severity scale — there is **no
cross-scale normalization** (`severity-verdict-contract.md`). The gate is a
**disjunction of native gates** (the boolean OR of each leg's native verdict),
and the combined report is sectioned per reviewer, never one merged ranking.

## Reviewer set (native scales, no normalization)

warden runs each reviewer on its **own** severity scale. Cross-scale
conversion is forbidden (`shared/severity-verdict-contract.md:155-174`); the
gate is a **disjunction of native gates**, and the combined report is
**sectioned per reviewer**, never one merged ranking.

The "Runs" column is split by **reviewer-set** (the dispatch parameter
`reviewer-set: full | standalone`): `full` is the build/finish pipeline set,
`standalone` is a bare `/warden` invocation where per-push cost matters.

| Reviewer | Runs (`full`) | Runs (`standalone`) | Native gate predicate (blocks if true) | Notes |
|---|---|---|---|---|
| temper | always | always | `T = {CONFIRMED,PLAUSIBLE} × {Critical,Important}` non-empty | the merge-verdict loop |
| delve | always | always | any kept finding at `{CONFIRMED,PLAUSIBLE} × {Critical,Important}` (trio scale; `PLAUSIBLE@Crit/Imp` is a real regression per contract) | delve is **report-only with no fix loop** — warden applies the predicate to delve's kept findings and owns the fix path (see Fix behavior) |
| red-team (via quality-gate) | always | always | quality-gate verdict ≠ PASS (Fatal>0 ∨ Significant>0) | delegates to existing `crucible:quality-gate` on the `code` artifact to reuse its red-team loop, invoked so the QG leg **re-dispatches siege** exactly as build's Step-6 gate does (warden does **not** suppress the QG-internal siege) — the second of warden's two siege passes (I-W4 / S-A); the leg's marker is **not** build-tagged (see §Verdict marker ownership / I-W7) — warden owns the aggregate verdict marker; it writes **no** calibration ledger entry (each leg self-emits its native entry, I-W8) |
| siege | conditional — security-surface diff (reuse build's existing Step 5.5 trigger) | conditional — same security-surface trigger | Critical>0 ∨ High>0 | heavy 6-agent Opus audit; not run on non-security diffs. **siege is warden's own native leg on its own CVSS scale** (disjunction-of-native-gates, a LOCKED decision). warden sieges **twice**, **coverage-equal to build's two sieges (position redistributed across the two passes)**: warden's own siege leg at step-1 HEAD (≈ build Step 5.5), and the QG red-team leg's internal siege auto-dispatch at `SHA_pre_redteam` (≈ build Step 6) — the QG leg is invoked so it **re-dispatches** its internal siege as build does (warden does **not** suppress it) (I-W4 / S-A) |
| inquisitor | **always (unconditional)** — preserves build Phase 4 Step 4 coverage | conditional — risk-aware predicate (escalators → run; pure-doc-only → skip; else `>1 changed file OR >1 top-level module`). See *Standalone inquisitor-inclusion predicate*. | any adversarial test `Result: FAIL` | heavy 5-dim fan-out. In the `full` set it stays unconditional so a single-file build does **not** lose the inquisitor pass it gets today; the standalone diff-shape trigger is the risk-aware *Standalone inquisitor-inclusion predicate* subsection, where per-push cost matters |

temper and delve share the trio contract scale, so their two legs use one
predicate; the other three keep their own. No leg's severity is converted into
another's.

**inquisitor coverage (S3 resolution).** build Phase 4 Step 4 runs inquisitor
unconditionally today. Making it conditional everywhere would silently narrow
the strongest orchestrator's review coverage on single-file builds. So the
trigger is split by reviewer-set: **unconditional in `full`** (no build
regression), **conditional (multi-file / cross-module) in `standalone`** where
the per-push Opus fan-out cost is the dominant concern. T-W8 asserts the `full`
behavior. Multi-file / cross-module is only block 3 of the richer standalone
trigger — see the *Standalone inquisitor-inclusion predicate* subsection for the
authoritative spec.

### Standalone inquisitor-inclusion predicate

**Orchestrator-followed prose — never executed in CI.** This predicate
decides whether the `standalone` reviewer-set runs inquisitor. It is evaluated by
the orchestrator over the entry diff's git-observable signals; there is **no**
classifier binary and no `gate_logic.py` (a forbidden non-goal). Its behavioral
teeth defer to the install-gated live `/warden` pass (Acceptance Gate 2); CI pins
only that each clause below is *present* (`scripts/check_warden_structure.py`). In
the `full` reviewer-set inquisitor runs unconditionally and this predicate is
never consulted (T-W8 / S3).

Evaluated on the entry diff, in order (escalators dominate; strictly additive):

1. **Escalators → run.** If any changed path matches the INTERFACE/API/SCHEMA glob set,
   or matches the DEPENDENCY/lockfile glob set, or the diff has a binary or otherwise unparseable path
   → **run inquisitor** (fail-safe: unknown → run).
2. **Pure-doc bounded subtraction → skip.** Else if EVERY changed path is a PURE-DOC file
   (`.md`/`.rst`/`.adoc`, any depth) → **skip inquisitor**.
3. **Retained reach clause (today's behavior).** Else if >1 changed file OR >1 top-level module touched
   → **run inquisitor**.
4. **Else → skip inquisitor.**

**INTERFACE/API/SCHEMA glob set** (each matched at any depth, gitignore-style —
every entry is `**/`-anchored, so a nested `internal/rpc/x.proto` matches exactly as
a root-level `x.proto` does): `**/api/**`, `**/*.proto`, `**/openapi*`,
`**/schema*`, `**/migrations/**`, `**/index.*`, `**/__init__.py`, `**/*.graphql`.

**DEPENDENCY/lockfile glob set:** `**/package.json`, `**/*.lock`,
`**/requirements*.txt`, `**/Cargo.toml`, `**/go.mod`, `**/pyproject.toml`.

**PURE-DOC file** = a path whose extension is `.md`, `.rst`, or `.adoc`, matched at
any depth (gitignore-style), **not** a `docs/**` catch-all. `.txt` is **deliberately
excluded** (it names lockfiles / golden-data / config, not documentation-by-
convention). A code file (e.g. `docs/conf.py`), a binary, or an interface authored
under `docs/` is **not** a pure-doc file, so a diff containing one is not all-doc and
does not take block 2.

**Monotonicity (additive except the one bounded block-2 doc-subtraction).** The predicate only ever *adds* inquisitor runs
relative to today's `>1 file OR >1 module` clause (blocks 1 + 3 are a superset of it)
or *removes* a run for a provably-safe all-doc diff (block 2). A single-file
non-escalator code diff still skips exactly as today (block 4). Aside from the one
provably-safe block-2 all-doc subtraction noted above, no input that ran
inquisitor under the old clause now skips it.

**Residual risk.** (a) *Escalator over-match:* several escalator globs swallow common
docs paths — `**/api/**` catches `docs/api/x.md`, `**/index.*` catches `index.md`,
`**/schema*` catches `schema.md`, `**/openapi*` catches `openapi.md`. Because escalators
are evaluated **first and dominate**, the pure-doc skip fires on a **narrower** slice
than the headline "all-docs → skip" implies. The direction is **safe**
(over-inclusive → more inquisitor runs, never fewer); for `openapi.md`/`schema.md`
the run is **intended** (an interface authored as markdown is not a doc). The glob
list is a tunable, not a correctness gate. (b) *SKILL.md-as-behavior:* a multi-file
all-`.md` diff (e.g. an all-SKILL.md change) skips inquisitor via block 2 — safe
because routing/structure regressions in this repo are caught by
`check_warden_structure.py` / selection-evals and the always-on floor
(temper/delve/red-team), not by inquisitor's executable cross-component tests, which
have no target in an all-docs diff.

## Fix behavior

Each leg's fix path is **not** uniform — the earlier "warden drives each
reviewer's existing fix loop" framing was wrong for delve, which has no loop.
And an earlier premise — "each fixer leg commits its own working-tree delta" — is
**false for temper**: temper's fixer **edits the working tree** (its Step 3 fixes
every member of `T`, `temper/SKILL.md:188`) but in **uncommitted mode**
(`temper/SKILL.md:197-198`) **never advances HEAD**. The `git stash create` temper
uses in that mode only snapshots the tree to compute each round's fix-delta scope —
*that snapshot* is what leaves HEAD, the index, and the working tree untouched; it is
**not** how the fix is applied. So temper's edits sit in the working tree,
**uncommitted**, for warden to commit. delve `--fix` and the
quality-gate red-team leg likewise edit the working tree and never commit; only
inquisitor (`inquisitor/SKILL.md:163`) and siege self-commit. So warden cannot assume
"the leg committed its own fix" — it must commit each leg's residual itself, or the
frozen HEAD can omit temper's (or delve's, or the red-team leg's) fixes.

**Universal per-leg residual commit (I-W6).** After **each** fixer leg terminates —
and **before the next fixer leg runs** — warden commits **that leg's residual
working-tree changes, if any**. Under the clean-working-tree precondition (below), a
leg's residual **is** the entire set of uncommitted changes — tracked edits **and
newly-created (untracked) files alike** — so warden commits **all** of it with
`git add -A && git commit` (which stages new files too, so a fixer leg that creates a
new module/test lands it in the frozen HEAD) and a
leg-labeled **non-`fix:`** subject (`chore(warden): temper fixes <run-id>`,
`chore(warden): delve fixes <run-id>`, `chore(warden): red-team fixes <run-id>`, etc. —
see M-c). Committing the full residual (rather than path-scoping it) captures delve's
out-of-scope `--fix` edits **by construction** — the clean-tree base guarantees the only
uncommitted changes (tracked **or** untracked) are the current leg's delta, so there is
nothing unrelated to sweep. A leg that already self-committed (inquisitor, siege) leaves **no residual**, so
the commit is a no-op for it; temper, delve, and the red-team leg — which never commit —
get their edits committed here. This is a **single universal rule**, not a per-leg
special case, and it corrects the false "each fixer leg commits its own delta" premise
to: *warden commits each leg's residual; self-committing legs leave none;
temper/delve/red-team leave working-tree edits that warden commits.* HEAD advances as
each leg completes, so downstream `finish` / PR-creation see every leg's fixes **already
committed**, and — because each residual is committed once, between legs — there is **no
double-commit**.

**Working-tree-clean precondition (the inductive base — ASSERTED on all paths).** For
"commit this leg's residual" to capture only that leg's delta (never unrelated edits),
warden requires a **clean working tree at entry**, and **asserts** it on **every** path:
`git status --porcelain` must be **fully empty** — **no** tracked modifications **and no
untracked files**. This is a hard precondition, not an assumption; the fully-empty check
(rather than "empty for tracked files") is what makes `git add -A && git commit` safe —
the only thing it can stage after a leg is exactly that leg's delta, so per-leg
attribution holds by construction (a pre-existing entry-untracked file could otherwise be
swept into the first leg's `chore(warden):` commit). A standalone `/warden` on a
**dirty-or-untracked** tree **REFUSES** with an
actionable error (`commit, stash, or clean untracked files, then re-run /warden`) —
matching how warden already treats a detached HEAD (require explicit action from the
user). Inside **build**, build **guarantees** this at warden entry (the build Phase 4
clean-tree rule): a dirty **or untracked** tree
at build→warden entry is a **surfaced build/test defect** (warden errors) — it is never
silently swept into the first `chore(warden):` commit. **Standalone `/warden` and
standalone `/finish` both fall to the assert-and-REFUSE rule** (only *build* supplies a
clean-tree guarantee — finish has no clean-tree gate of its own; see §Failure modes,
"Standalone finish … through warden"). Without this asserted base the per-leg residual is not well-defined; it
is the base of the induction that makes the frozen HEAD provably contain every leg's
fixes.

Per leg:

- **temper** — loops+fixes to merge-verdict termination (its own loop), in
  **uncommitted mode** (`temper/SKILL.md:198`, HEAD untouched), so
  **warden commits temper's residual working-tree changes** itself
  (`chore(warden): temper fixes <run-id>`, non-`fix:` per M-c) per the universal rule
  above.
- **quality-gate (red-team leg)** — loops+fixes its red-team rounds (its own
  loop). quality-gate's `code` fixes are **working-tree edits, never committed**: the
  fix agent's capabilities are `apply-edits` + `run-tests` with no git step
  (`quality-gate/SKILL.md:75`), those edits run against the working tree, the pre-qg-fix
  **checkpoint snapshots the working directory as rollback** (`:460` — which only makes
  sense because code fixes mutate that tree), and there is no `git commit` anywhere in
  quality-gate's directory. The leg is invoked so its internal
  siege auto-dispatch runs (warden does **not** suppress it) — warden's second siege
  pass, mirroring build (see the reviewer table / I-W4). So — like temper and delve —
  **warden commits the red-team leg's residual working-tree changes itself** after the loop
  terminates, with a **non-`fix:` subject** (`chore(warden): red-team fixes <run-id>` —
  see M-c). As the **terminal** fixer this commit is made at Ordering step 3; its range
  `SHA_pre_redteam..HEAD` is what the terminating freeze-guard re-checks (Ordering step
  3→4). HEAD advances so downstream `finish` / PR-creation see the red-team fixes
  **already committed**.
- **siege** — loops+fixes to 0 Critical/High (its own loop); **self-commits**, so it
  leaves no residual (the universal commit is a no-op for it).
- **inquisitor** — writes+runs tests and manages its own fix cycle; **self-commits**
  (`inquisitor/SKILL.md:163`), so it leaves no residual.
- **delve** — **report-only, no fix loop** (`delve/SKILL.md:25,125`; runs the
  engine once and reports). warden owns delve's convergence with a **bounded**
  path. On a delve native-gate trip (`{CONFIRMED,PLAUSIBLE} × {Critical,Important}`),
  warden runs `delve --fix`, which applies the unambiguous repairs and **surfaces
  rather than applies** the findings whose repair is ambiguous (`delve/SKILL.md:133`
  — the discriminator is a judgment delve's `--fix` step makes, not a schema field
  on the report). delve `--fix` edits the **working tree only and never commits**
  (`delve/SKILL.md:130`), so **warden commits the applied fixes itself** with a
  **non-`fix:` subject** (`chore(warden): delve fixes <run-id>` — see M-c) before
  re-running plain delve to re-check the
  predicate — this is what gives the delve leg fix commits for the scoped
  re-temper (I-W6) and lands them in the frozen HEAD (S-4). The
  **surfaced-not-applied** findings are the BLOCK set: warden does not auto-fix
  them and **BLOCKs with a named user hand-off**, since the repair is ambiguous
  and there is no safe auto-repair. The re-run loop is **capped at ≤2 re-runs**
  (delve's finder fan-out is non-deterministic, so a one-shot `--fix` need not
  clear a `PLAUSIBLE@Critical`); if the native predicate still trips after the
  cap, warden **BLOCKs with the same named user hand-off** rather than looping
  open-endedly. This gives delve a defined, bounded convergence path instead of a
  leg that can block forever.

**M-c note (`fix:` subject vs reconcile's candidate walk — resolved).**
calibration-reconcile walks merged `fix`/`hotfix` commits as falsification
candidates, so a `fix:`-prefixed intra-gate commit that reached a **merged branch
un-squashed** could be picked up as a candidate falsifying a *prior* verdict over
the same files. To make correctness independent of the downstream repo's merge
strategy, **every warden-owned per-leg residual commit — temper, delve, the red-team
leg, and any other leg whose residual warden commits — must use a non-`fix:` subject**
(`chore(warden): temper fixes <run-id>`, `chore(warden): delve fixes <run-id>`,
`chore(warden): red-team fixes <run-id>`) — **mandated, not optional**. Each is a
warden-authored commit of a leg's working-tree changes, and any could otherwise hit the
identical `fix`/`hotfix` candidate-walk collision. A non-`fix:` subject is never a
candidate in reconcile's `fix`/`hotfix` walk regardless of whether the branch is
squashed, so the subject-prefix collision cannot arise for any warden-owned commit even
in a rebase/merge-commit repo.

**M-c scope gap (inquisitor/siege self-commit is *outside* this mitigation — disclosed).**
The non-`fix:` mandate above binds only **warden-owned** commits. **inquisitor and siege
self-commit** under their own subjects — `inquisitor/SKILL.md:163` uses a `fix:`-style
subject — which warden does **not** control, so an inquisitor/siege **self-commit** that
reaches a merged branch un-squashed can still hit reconcile's `fix`/`hotfix`
candidate-walk collision: the same failure the M-c note removes for warden-owned commits,
but **outside** the reach of warden's non-`fix:` subject mandate. This is **disclosed and
accepted** — closing it would require editing the leg's own SKILL.md subject or
`reconcile_ledger.py`'s candidate walk, both out of scope per Constraint 1 (Option-C:
warden touches no leg emission and no reconcile).

**M-2 caveat (`chore()` also suppresses *legitimate* prior-gate falsifications).** The
non-`fix:` subject is blanket: because `delve --fix` may repair pre-existing
out-of-scope files (M-d), a `chore(warden):` commit that genuinely fixes a bug a
**prior merged gate** missed never enters reconcile's `fix`/`hotfix` candidate walk
(`reconcile_ledger.py:910,914`), so that prior verdict keeps an undeserved Brier point.
This is a small calibration-precision loss, disclosed here; the reconcile tier-filter
fix that would recover it stays out of scope.

**M-d note (delve `--fix` may touch out-of-scope files).** `delve --fix` may edit
**any file a kept finding names**, including files outside the original push scope
(delve's cross-file angle, `delve/SKILL.md:137`). warden commits those **by
construction** — the unscoped per-leg residual commit (above) captures every
uncommitted tracked change, so delve's out-of-scope edits are committed like any other,
not as a special case. The scoped re-temper (Ordering step 2) covers them on temper's
axis, and — because delve is pinned **before** the red-team leg (Ordering step 1) —
the **second siege** (the QG leg's internal auto-dispatch at `SHA_pre_redteam`) re-sieges
over those edits on the security axis. So only **inquisitor does not re-run** on
newly-touched out-of-scope files (it binds its step-1 HEAD, per S-D / S-E). This is a
small accepted coverage asymmetry: temper/delve/siege cover the widened scope; only the
inquisitor leg does not. **M-4 (pushed-footprint expansion):** beyond the *review*
asymmetry, warden **commits and pushes** these out-of-scope `delve --fix` edits — a
scope-expansion of what *ships*, not just of what is reviewed (a user gating a 1-file
change may push edits to unrelated files delve's cross-file angle touched). Disclosed and
accepted.

warden blocks **only if a native gate still trips after that leg's fix path (its
own loop, or warden-owned delve/red-team fixes) terminates**. warden adds no new
fix mechanism beyond running `delve --fix` and committing **each leg's residual
working-tree changes** (temper, delve, and the red-team leg — inquisitor/siege
self-commit and leave no residual), as described above.

## Ordering (F1 — the gate binds a single frozen final artifact)

A gate's verdict is only fully sound if it is evaluated against the **final code
state**. warden enforces this for the legs it re-evaluates on the frozen HEAD —
**temper, delve, and the red-team leg** — by ordering the code-mutating legs and
re-checking after later fixers (below). siege runs **twice** (neither pass at the
frozen HEAD) and inquisitor runs **once** at its step-1 HEAD — accepted cost tradeoffs:

- **siege** runs **twice**, **coverage-equal to build's two sieges (position
  redistributed across the two passes)** — warden's siege#1 runs at step-1 (before the
  step-2 re-temper), whereas build's Step-5.5 siege runs after Step-5's re-temper; the
  step-2 re-temper is covered by siege#2, so this is a position redistribution, not a
  coverage gap: (a) warden's **own siege leg** at the **step-1 HEAD** (≈ build Step 5.5),
  and (b) the **quality-gate red-team leg's internal siege auto-dispatch** at the
  red-team HEAD (`SHA_pre_redteam`, parallel with red-team round 1 — ≈ build Step 6). The
  second siege covers the **step-2 scoped re-temper commits** and delve's `--fix` edits,
  mirroring build's Step-6 siege over its Step-5.5.e re-temper. Re-running the 6-agent
  Opus siege on *every* fix commit would be prohibitively expensive, so neither pass
  binds the **frozen** HEAD: the only window either misses is the **red-team leg's own
  fix rounds** — and build's Step-6 siege runs parallel with red-team round 1, so build
  misses that window too. warden's siege coverage is therefore **coverage-equal to build's
  two sieges (position redistributed across the two passes)** — no coverage reduction
  relative to build.
- **inquisitor** binds its step-1 HEAD (it is excluded from the terminating
  read-only leg per S-D, since it writes tests). Its coverage is delivered by the
  unconditional step-1 run; a later fixer regressing the cross-component surface is
  out of scope for the cheap terminating pass — an accepted tradeoff. **inquisitor is
  the sole leg that binds step-1-only** — siege now runs a second pass at
  `SHA_pre_redteam`.

Because the code-mutating legs edit the shared artifact the other legs already
judged, warden runs them in a **deliberate order** that mirrors build Phase 4
(temper → inquisitor → siege → quality-gate last, `build/SKILL.md:1212-1263`),
committing **each leg's residual working-tree changes as it completes** so the frozen
HEAD provably contains every leg's fixes (see Fix behavior — Universal per-leg residual
commit):

0. **Working-tree-clean precondition (inductive base — ASSERTED).** warden **asserts** a
   **clean working tree at entry** on **all** paths (`git status --porcelain` **fully
   empty** — no tracked modifications **and no untracked files**) — the base that makes
   each per-leg residual commit capture only that leg's delta. Standalone `/warden` on a
   **dirty-or-untracked** tree **REFUSES** with an actionable
   error (`commit, stash, or clean untracked files, then re-run /warden`), matching
   warden's detached-HEAD handling. Inside **build**, **build guarantees** the tree is
   fully clean at warden entry (the build Phase 4 clean-tree rule — which
   **classifies each post-test-run untracked path**: commit a regenerated golden
   file, gitignore an incidental, or surface a still-dirty tree as a build defect;
   that per-path discharge is what makes build's clean-tree guarantee at warden
   entry actually dischargeable, not a bare assertion); a dirty **or
   untracked** tree at build→warden entry is a **surfaced
   build/test defect** — warden errors, it never sweeps it into the first `chore(warden):`
   commit. **Standalone `/warden` and standalone `/finish` both fall to the
   assert-and-REFUSE rule** — only *build* supplies the clean-tree guarantee (finish has
   no clean-tree gate of its own).
1. **Non-terminal fixers first, each residual committed as it terminates.** Run the
   **non-terminal** code-mutating legs — temper, inquisitor, siege, and warden-owned
   delve fixes — to loop-termination first, in the build-mirroring order
   temper → inquisitor → siege, with the **warden-owned `delve --fix` leg pinned among
   these non-terminal fixers, before the red-team leg (step 3)** — so delve's cross-file
   security-relevant edits are already committed when the red-team leg's internal
   **second siege** runs at `SHA_pre_redteam`, keeping them inside that siege's coverage.
   temper (uncommitted mode, `temper/SKILL.md:198`) and delve `--fix` are
   working-tree-only and never commit, so after **each** such leg terminates — and
   **before the next fixer leg runs** — warden **commits that leg's full residual
   working-tree changes, if any** (`git add -A && git commit -m '<subject>'` — stages
   new/untracked files too; no path-scoping), with a leg-labeled
   non-`fix:` subject (`chore(warden): temper fixes <run-id>`, `chore(warden): delve fixes
   <run-id>`, per M-c). Under the fully-empty clean-tree precondition (step 0) that
   residual is exactly the current leg's delta (a new file the leg created is staged and
   committed, and no pre-existing untracked file exists to misattribute). Committing between legs (not batched at the end) keeps
   each residual attributable to the leg that produced it — so every non-terminal leg's
   repairs enter HEAD with correct provenance (S-4; see Fix behavior). inquisitor
   (`inquisitor/SKILL.md:163`) and siege **self-commit**, so their residual is empty and
   the commit is a no-op for them. (The red-team leg is **also** a warden-committed fixer,
   but as the **terminal** fixer its residual is committed at **step 3**, not here.)
2. **Re-temper after later fixers (S1).** After inquisitor's, siege's, or delve's
   fix path terminates, warden re-runs temper **scoped to that leg's fix
   commits** before the red-team leg — mirroring build Step 5 (re-temper on
   inquisitor commits) and Step 5.5.e (re-temper on siege commits). A fix that
   satisfies siege's CVSS gate can still regress temper's maintainability/
   correctness axis; this catches it. The scoped re-temper is itself a temper
   (uncommitted-mode) fixer, so warden **commits its residual too**
   (`chore(warden): temper fixes <run-id>`, per M-c) before proceeding. (This is
   build's existing scoped re-temper, not a new open-ended fixpoint loop.)
3. **Red-team leg (itself a fixer) next.** Once no non-terminal fixer has more
   work, warden captures **`SHA_pre_redteam = HEAD`** and runs the quality-gate
   red-team leg against that HEAD (invoked so its **internal siege auto-dispatch** runs —
   warden does **not** suppress it — warden's **second** siege pass over `SHA_pre_redteam`,
   parallel with red-team round 1, mirroring build's Step-6 siege; see the reviewer table
   / I-W4). This leg **edits the working tree** — it
   loops+fixes its red-team rounds but, like temper and delve, **does not commit** (its
   fix agent has `apply-edits`/`run-tests` and no git step,
   `quality-gate/SKILL.md:75,462`). So **warden commits the red-team leg's residual
   working-tree changes, if any**, here — `chore(warden): red-team fixes <run-id>`,
   non-`fix:` subject per M-c — advancing HEAD **before the terminating leg (step 4)
   and the freeze**. The red-team fix range is then **`SHA_pre_redteam..HEAD`** — a
   distinct, isolable range even though earlier legs also committed. These fixes land
   after the other four gates were evaluated, so they must not ship un-re-reviewed —
   which is exactly what the terminating freeze-guard (step 4) re-checks over **that**
   range.
4. **Read-only instance-bug freeze-guard over the red-team leg's fixes, then
   freeze.** After the red-team leg's fix loop terminates **and warden has committed
   its residual (step 3)**, warden runs **plain delve in its
   native report-only mode** (`delve/SKILL.md:25`, "report only … never gates") over
   **`SHA_pre_redteam..HEAD`** (the red-team leg's fix commits) — a **read-only
   instance-bug freeze-guard**. If the red-team leg made no edits this range is
   **empty**, and the terminating delve reviews an empty range and benignly passes —
   there is no "non-empty range" requirement. warden does **not** pass `--fix` on this
   leg
   (`delve/SKILL.md:25,125`), so it is **provably non-code-mutating** — the
   terminating leg writes **nothing** into the frozen HEAD. This is deliberately
   **NOT** a temper-the-skill re-run: temper-the-skill is a fix loop (its Step 3 is
   "**Fix every member of `T`**", `temper/SKILL.md:188`) and would mutate the frozen
   HEAD. The terminating leg runs **no temper enumeration or adjudication at all** —
   it is plain delve, run once. In particular the freeze-guard **does not pass `--fix`**
   and is **not** a `temper-reviewer` re-run — it is plain report-only delve.

   **Coverage scope (honest, bounded tradeoff).** The terminating leg is a
   **read-only instance-bug freeze-guard** over the red-team leg's fix commits (plain
   delve, report-only, `--fix` not passed → provably non-mutating). temper's broader
   review angles are applied at step 1 and the scoped re-tempers; they are **not**
   re-applied to the red-team fixer's own commits — an accepted, bounded tradeoff of
   the same class build already lives with (e.g. its inquisitor-step-1-only carve-out).
   This closes the coverage question by
   **disclosing the scope**, not by asserting that delve's coverage subsumes
   temper's. **inquisitor is likewise excluded** because it writes tests (S-D):
   including it would land un-re-reviewed test files in the frozen HEAD, breaking the
   very "single, fully-reviewed frozen artifact" guarantee this leg exists to
   provide. inquisitor's coverage is delivered by its **unconditional step-1 run**;
   the accepted tradeoff is that a red-team fix which regresses the cross-component
   surface is **out of scope** for this cheap terminating pass (it would only be
   caught on a subsequent full gate run).

   This pass runs **exactly once** (detect → BLOCK): there is no fix loop, so no
   round cap — warden **BLOCKs** if delve reports any gating finding
   (`{CONFIRMED,PLAUSIBLE}×{Critical,Important}`); it does not re-fix or loop.
   Because this **final leg warden runs is read-only**, the artifact is stable; only
   then is HEAD frozen and the disjunction evaluated on that single frozen final
   artifact, with the verdict bound to the frozen HEAD SHA. Because warden committed
   **every leg's residual as it completed** (temper's and delve's at steps 1–2, the
   red-team leg's in step 3), **the frozen HEAD now contains every leg's fixes** — so
   F1's "single frozen final artifact" guarantee covers temper's uncommitted-mode fixes
   and the red-team leg's own repairs, not only the legs that self-commit. The verdict
   and its marker (and the ledger `gated_files`/SHA) therefore bind a HEAD that
   **contains the fixes that earned the PASS** — closing the broken verdict-to-artifact
   binding F-A raised.

This is codified as invariant **I-W6**.

## Gate + enforcement

warden's verdict is `BLOCKED` if any run reviewer's native gate trips after its
fix path terminates — its own loop, or warden-owned delve/red-team fixes, evaluated
on the frozen final HEAD per the Ordering section (I-W6) — else `PASS`.

**Escalation verdicts are fail-closed (BLOCKED, never PASS).** The native gate
predicates above are stated over *findings*, but a leg can also terminate on an
**escalation** verdict rather than a findings predicate: temper Stagnation /
Architectural / Max-Rounds (`temper/SKILL.md:332`) from the step-1 / scoped
re-temper legs, or the quality-gate red-team leg STAGNATION / ESCALATED. Any such
escalation **propagates as a warden BLOCK (fail-closed) — never a PASS** — the same
handling build Phase 4 already gives a quality-gate escalation today (it does not
swallow it). warden mints no third verdict: an escalation folds into `BLOCKED` and
halts the pipeline like any other block.

**A reviewer sub-dispatch that dies is fail-closed too (an unrun gate is not a
pass).** If a reviewer sub-dispatch **dies** (crashes, times out, or returns no
parseable receipt), warden **surfaces the failed leg and returns `BLOCKED`**
(fail-closed — **an unrun gate is not a pass**), never silently drops it. A
**condition-skipped** leg (siege on a non-security diff, standalone-inquisitor on a
single-file **non-escalator code** diff) is **not** an "unrun gate" for this rule: only a leg that was
*supposed to run* and died triggers the fail-closed BLOCK; a correctly
condition-skipped leg is a **normal PASS input, not a failure** (M5).

Enforcement teeth:

- **Inside build/finish (real teeth):** a `BLOCKED` warden verdict halts the
  pipeline before the push/PR step, exactly like quality-gate non-PASS halts
  Phase 4 today.
- **Standalone `/warden` (honored, not intercepting):** a slash command cannot
  intercept `git push`; standalone warden emits a `BLOCKED` verdict the user
  honors — same enforcement strength finish's soft gate has today, but now
  named and consistent. No git hook (rejected: per-push Opus fan-out cost +
  install friction; may revisit as an opt-in follow-up).

## Verdict marker ownership (F2 — single build-tagged emitter)

Two facts make a naive delegation fail-open: quality-gate *always* writes its
marker even as a sub-skill (`quality-gate/SKILL.md:1111`) and *never* deletes it
("build orchestrator is responsible for their lifecycle"). If warden invoked the
red-team leg with **build's** PipelineID, both the leg and warden would write a
`gate-verdict-*.md` carrying build's PipelineID with potentially divergent
verdicts, and build's most-recent-by-Timestamp verification
(`skills/build/SKILL.md:231-243`) would resolve the ambiguity only by timing luck.
So:

- warden invokes the quality-gate red-team leg with **warden's own run-id** as the
  PipelineID (and `Phase: code`), **not** build's PipelineID. A PipelineID is
  present, so the leg stays **non-interactive** — quality-gate does not drop into
  standalone between-rounds check-in mode (`quality-gate/SKILL.md:1111`; this
  resolves M3) — while its `gate-verdict-<warden-run-id>.md` marker carries
  warden's run-id and therefore **never matches build's PipelineID filter**.
- warden writes the **one** `gate-verdict-*.md` that carries **build's** PipelineID
  (and `Phase: code`), stamped with warden's **aggregate** verdict.
- build's Verdict Marker Verification **read** logic — glob → PipelineID-filter →
  PASS-check (`skills/build/SKILL.md:231-243`) — is **unchanged** and now resolves
  **deterministically**: its filter surfaces exactly one marker (warden's
  aggregate), because the leg's marker is tagged with a different (warden)
  PipelineID.

What **does** change is deferred to **Phase E**: the two build sites that hard-name
`quality-gate` — the recovery re-invoke on a missing/mismatched marker
(`build/SKILL.md:241`) and the Step-6 gate invocation (`build/SKILL.md:1263`) —
must **repoint to `warden`** (Tasks 12/16). If the recovery re-invoke were left
naming `quality-gate`, a crashed/orphaned warden run would recover as a **bare
red-team-only** gate (no temper/delve/inquisitor/siege) — a coverage fail-open in
the recovery path; repointing both to warden closes it. This is invariant **I-W7**.
(This task authors the marker-ownership prose only; it does **not** edit build —
the repoint lands in Phase E.)

## Calibration-ledger entries — each leg self-emits, warden emits none

warden emits **no** `code` calibration entry to `runs.jsonl` — it writes
no calibration row of its own. Each leg **self-emits its native per-skill calibration
entry**, exactly as it does under build today: temper's Tier-A `code` entry
(`temper/SKILL.md:323`), siege's (`siege/SKILL.md:690`), the quality-gate red-team
leg's terminal `code` entry (`quality-gate/SKILL.md:1066`, unconditional), and
delve's and inquisitor's Tier-B **stub** `code` entries (`delve/SKILL.md:164`,
`inquisitor/SKILL.md:222`; `backfilled:false`, no merge verdict — a stub entry, not
*no* entry). None are suppressed, and **no leg's SKILL.md is edited** (Option C).

warden **mirrors build** — the existing orchestrator that dispatches these very
same calibrated legs and has **zero `runs.jsonl` touchpoints** (build self-emits
nothing; every leg emits its own entry, which is what per-skill Brier is *for*).
warden's verdict is a *determined disjunction* of its legs' native verdicts (the
boolean OR), so it carries no predictive content beyond that OR; any aggregate
`confidence` / `predicted_falsifier` would be **synthesized** from the legs — a
double-count. No independent content → no independent calibration row. Per-skill
Brier stays fed by the leg entries, and per-leg falsification resolution (which leg
missed a bug) is **preserved** — it would be *lost* under a single aggregate entry.

**Inherited attribution imprecision (warden neither introduces nor solves it).**
These co-timed leg `code` entries over overlapping files attribute
**earliest-first** in `reconcile_ledger.py`'s skill-blind walkback
(`reconcile_ledger.py:352-377`, no tier and no confidence filter). warden **adds
delve's Tier-B stub entries** — which build's Phase 4 lacked: warden runs delve
several times per gate, each a distinct `run_id` (UUIDv7, **not** deduped by the
`(run_id, skill)` emit key), so a 2-iteration fix path is initial +
(`--fix` + recheck)×2 + step-4 ≈ **up to ~6** distinct stubs — but **no aggregate
row**. The earliest-first, skill-blind attribution is therefore **unchanged in
kind** from build's inherited imprecision: a delve stub can become the earliest
overlapping `code` entry and absorb a future fix's falsification exactly as build's
own **inquisitor** stub already can. **The change from build is one of
degree, not kind (M-5):** ~6× the stub surface (up to ~6 delve stubs per warden run vs build's
single inquisitor stub), which correspondingly **raises** — while keeping bounded —
the probability a low-value stub absorbs a future falsification. It is an inherited,
bounded tradeoff — out of scope to fix (the fix would need the `reconcile_ledger.py`
tier filter this design explicitly rejects) — stated plainly so it is not mistaken
for something warden solved.

Consistent with the LOCKED double-siege decision, warden does **not** pass
`skip_siege`/`force_siege` to the quality-gate red-team leg (they are real
`quality-gate/SKILL.md:187-188` params); suppressing the QG-internal siege would
silently break warden's second siege pass (I-W4). Per-leg forensics at gate time
also live in (a) the sectioned-per-reviewer report (I-W2) and (b) the per-reviewer
receipts bound into `receipt-ledger.jsonl` (see Dispatch + return conventions).
This is invariant **I-W8**.

## Double-run avoidance

warden writes a coverage marker keyed by the **pre-run base SHA** (the HEAD warden
observed at entry, *before* its own fixer legs mutate HEAD) + reviewer-set. Keying
on the pre-run base — not the post-fix HEAD warden itself moves — means a legitimate
immediate re-run over the same starting state matches the marker and is skipped,
rather than misfiring because warden's own fix commits changed HEAD (M4). build's
finish-skip instruction is the **primary** guard; the marker is the backstop so a
standalone warden immediately after a build doesn't re-run the identical set.

**M-b caveat:** the marker is **near-inert exactly when warden committed fixes** —
once warden's fixer legs move HEAD, an immediate re-run's pre-run base is the *new*
post-fix HEAD, which no longer matches the prior run's recorded base, so the skip
does not fire. The marker therefore only helps after a **clean, no-commit** warden
pass; whenever warden actually did work, build's finish-skip is the only guard that
prevents a re-run. This is acceptable (a double-run is wasteful, not incorrect), but
the marker must not be relied on as the de-dup mechanism after a fixing run.

## Routing boundary (warden vs temper / quality-gate / delve)

warden's hardest routing problem is that it **runs temper as a leg**, so the
user-facing intents overlap ("review before I push" vs "is this ready to ship").
This is resolved here, not deferred to selection-evals alone: temper's
description **previously** claimed "before merging" (`temper/SKILL.md:3`) — the exact
push-gate intent warden wants — so the fix also **edited temper's description** to
cede that phrasing (ceded by this change — see §Routing boundary) as well as
constraining warden's. Selection-evals prove point-in-time routing; the
description edit removes the standing overlap (MEMORY #371/#358: description-phrase
collisions are fixed by editing the descriptions, not by evals alone).

The discriminator is **whole-set gate** (warden) vs **single reviewer**
(temper / quality-gate / delve).

**Phrase-ownership split:**

| Phrase / intent | Owner | Why |
|---|---|---|
| "gate this before I push", "run the full review gate", "run all the reviewers", "warden", "review my changes **before I push**" / "**before pushing**" / "**before merging**" | **warden** | wants the whole reviewer set + one verdict; the "before I push" / "before pushing" / "before merging" push-gate fragment is warden-owned even when attached to "review my changes" (M2 / S-C — "before merging" ceded from temper's former description) |
| "is this ready to ship", "review my changes" (bare), "review this PR", "code review", "check the diff" | **temper** (kept) | single fresh-eyes merge-verdict review; temper's existing description keeps these — but a trailing "before I push" / "before pushing" / "before merging" hands the utterance to warden (M2 / S-C) |
| "red-team this", "quality gate this design/plan", "is this design sound" | **quality-gate** | red-team of a typed artifact, not a code push gate |
| "find bugs in this diff", "scan this for defects", "instance-bug sweep" | **delve** | report-only bug finder, not a gate |

A trailing "before I create a PR" / "before a PR" is a review-readiness cue, **not** a
push-gate cue, so it **stays with temper** — *unless* the utterance also carries a gate
cue ("gate", "the full review gate", "before I push" / "before pushing" / "before
merging"), which hands it to warden. (The phrase-ownership table is silent on
"before … a PR" by design: the existing `review my changes before I create a PR`
selection-eval routes to temper and is not flipped by this change.)

warden deliberately does **not** claim temper's "is this ready to ship" / "review
my changes" phrases (I-W3): a fresh-eyes single-reviewer pass stays with temper,
red-teaming a typed design/plan stays with quality-gate, and a report-only bug-hunt
on a diff stays with delve. warden owns only the *whole-set gate* — the discriminator
is *whole-set gate* (warden) vs *single reviewer* (temper / quality-gate / delve).

The boundary is asserted by selection-eval prompts in `skills/skill-selection-evals/`.

## API Surface

- `/warden [scope] [--effort low|medium|high]` — standalone entry. **warden always runs
  its fix loops and commits** — it is a gate that **fixes-then-certifies**, not a
  report-only review — so there is **no `--fix` flag**: temper and the QG red-team leg are
  inherently fix loops, and `delve --fix` runs automatically on a native-gate trip.
  **What warden does to your branch:** it may add `chore(warden):` commits
  (temper/delve/red-team residuals) to the current branch before emitting its verdict.
  - `scope`: PR id | `base..head` range | path | auto-detect (delve's resolver).
  - Returns: sectioned-per-reviewer report + `PASS`/`BLOCKED` verdict + RCPT v1 receipt.
- `Use crucible:warden` (sub-skill) with dispatch context: `PipelineID: <id>`,
  `Phase: code`, `reviewer-set: <full|standalone>`, `dispatch-dir: <path>`.
- warden invokes its **internal quality-gate red-team leg** with `Phase: code` and
  warden's own run-id as `PipelineID` (non-interactive, not build-tagged), and **lets the
  QG leg re-dispatch its internal siege** (warden does **not** suppress it) — warden's
  **second** siege pass, mirroring build's Step-6 siege. warden sieges **twice** per run
  (its own step-1 leg + the QG leg's internal dispatch at `SHA_pre_redteam`), exactly as
  build does (I-W4 / S-A; the no-suppression note lives in §Calibration-ledger entries).
- **`reviewer-set` default (fail-safe toward coverage, S3 / I-W9).** warden distinguishes
  a **sub-skill** invocation from a **standalone** one by the **presence of `Phase` +
  `PipelineID`** in the dispatch context — the *same* detection mechanism quality-gate uses
  (`quality-gate/SKILL.md:186`). Given that discrimination: the standalone `/warden` entry
  (no Phase/PipelineID) defaults to `standalone`; a **sub-skill dispatch (Phase+PipelineID
  present) that omits `reviewer-set` defaults to `full`** — the higher-coverage set,
  matching build's intent — so a mis-edited sub-skill call site that drops just the
  `reviewer-set` parameter cannot silently narrow to conditional inquisitor and lose the
  Step-4 coverage S3 protects. **M-e scope:** this fail-safe covers omitting `reviewer-set`
  *while the dispatch context is present*; it does **not** cover a caller that omits the
  whole Phase+PipelineID context (that caller is detected as standalone and gets the
  narrower set). The concrete case is **standalone finish** (finish invoked *not* from
  build), which legitimately has no build Phase/PipelineID and correctly runs the
  standalone set — a **non-regression** (finish today runs no inquisitor at all), not a
  coverage loss.
- Emits the single `gate-verdict-<id>.md` marker (schema-compatible with quality-gate's)
  carrying the **caller's** `PipelineID` and the aggregate verdict; the internal red-team
  leg's marker is tagged with warden's own run-id and is not build-tagged (F2 / I-W7).
  Writes **no** `code` calibration entry to `runs.jsonl` — each leg self-emits its native
  per-skill entry, mirroring build (I-W8).

## Invariants

**Checkable by inspection:**
- I-W1: warden never converts one reviewer's severity into another's scale (no cross-scale
  map in the skill or its scripts). See §Reviewer set.
- I-W2: the combined report has one section per run reviewer; there is no merged
  cross-reviewer ranking. See §Reviewer set.
- I-W3: warden's frontmatter `description` does not contain the trigger phrases owned by
  temper / quality-gate / delve, **and** temper's description no longer claims the
  push-gate phrasing ("before merging", "before I push") — that phrasing is warden-owned
  (routing-collision guard, both directions). See §Routing boundary.
- I-W4: warden delegates the red-team leg to `crucible:quality-gate` (no independent
  red-team loop reimplemented in warden), invoked with warden's own run-id as PipelineID
  and **letting the QG leg re-dispatch its internal siege** (warden does **not** suppress
  it) — and warden **also** runs siege as its **own** native leg at step-1 HEAD, so siege
  dispatches **twice per run**, coverage-equal to build's two sieges (S-A). **M-1:** exactly
  one gate-driver runs the QG leg exactly once (build cedes its code-gate to warden inside
  build; warden is outermost standalone). See §Calibration-ledger entries for the
  no-suppression detail.
- I-W5: build Phase 4 and finish contain exactly one warden call site each; the individual
  temper/inquisitor/siege/red-team invocations they replaced are gone (no residual
  double-invocation). *(The call-site cutover lands in Phase E — Tasks 12/16.)*
- I-W6: ordering — warden **asserts a clean working tree at entry on all paths** and commits
  **each fixer leg's full residual working-tree changes** (`git add -A && git commit`,
  non-`fix:` subject) as that leg completes — delve pinned **before** the red-team leg;
  it re-runs temper scoped to each later fixer's commits, captures
  `SHA_pre_redteam = HEAD`, runs the red-team leg (letting the QG leg re-dispatch its
  internal siege), then a **read-only plain-delve freeze-guard** over
  `SHA_pre_redteam..HEAD` before the freeze — so the frozen HEAD contains every leg's
  committed fixes (F-A). See §Fix behavior + §Ordering.
- I-W7: single marker + lifecycle — exactly one `gate-verdict-*.md` carries the caller's
  (build's) PipelineID and warden is its sole emitter; the red-team leg's marker carries
  warden's own run-id and never matches the caller's PipelineID filter. The aggregate
  verdict is stamped after the freeze, bound to the post-commit frozen HEAD. See §Verdict
  marker ownership.
- I-W8: legs self-emit; no warden `code` row — warden writes **no** `code` calibration
  entry to `runs.jsonl`; each leg self-emits its native per-skill entry, mirroring build.
  The attribution change from build is one of **degree, not kind (M-5)** — no
  `reconcile_ledger.py` edit and no leg-SKILL.md edit required. See §Calibration-ledger
  entries.
- I-W9: reviewer-set fail-safe default — sub-skill vs standalone is detected by
  Phase+PipelineID presence. A sub-skill dispatch (context present) that omits
  `reviewer-set` defaults to `full` (coverage-preserving); the standalone `/warden` entry
  defaults to `standalone`. No caller silently narrows inquisitor coverage by omitting the
  `reviewer-set` parameter while context is present (S3); the whole-context-omitted case
  (standalone finish) is a non-regression (M-e). See §API Surface.

**Predicate invariants (INV-P namespace — the standalone inquisitor-inclusion predicate,
distinct from `I-W9`).** *Design-reconciliation note:* the design's "New T-W obligations
for INV-P7..INV-P10" is realized here as this INV-P invariants block, **not** as new
numbered `T-Wxx:` obligations — `T-W3` is the only `T-W` entry rewritten, and no `T-W`
numbers are added.

*Checkable by inspection:*
- INV-P1: the predicate is orchestrator-followed prose only — no classifier binary, no
  `gate_logic.py`.
- INV-P2: additive except one bounded subtraction — it only adds inquisitor runs (escalators)
  or removes one for a provably-safe all-doc diff; it narrows today's `>1 file OR >1 module`
  reach ONLY for the provably-safe all-doc case (block 2).
- INV-P3: the retained reach clause `>1 changed file OR >1 top-level module` is preserved
  verbatim as block 3.
- INV-P4: escalators are evaluated first and dominate the pure-doc skip (block order
  1 → 2 → 3 → 4).
- INV-P5: this predicate applies to the `standalone` reviewer-set only; `full` keeps
  inquisitor unconditional (T-W8 / S3).
- INV-P6: the fail-safe direction is toward running — an unknown / binary / unparseable
  path runs inquisitor, never skips it.

*Behavioral — teeth deferred to the live pass (Acceptance Gate 2), not executed in CI:*
- INV-P7: monotonicity — for a fixed file count, flipping a path from non-signal to an
  escalator signal flips skip → run (never the reverse).
- INV-P8: pure-doc bounded — inquisitor is skipped only when EVERY changed path is a
  pure-doc (`.md`/`.rst`/`.adoc`, any depth) file with no escalator; a code/binary sibling
  or an escalator defeats the skip.
- INV-P9: binary/unparseable fail-safe — a binary or otherwise unparseable path forces a
  run (documentation-only clause; in every constructible reachable case it is subsumed by
  block 3, so it retains no isolating CI fixture — deferred to the live pass).
- INV-P10: escalator escalation — a single-file API-glob or dependency-glob diff that
  skipped under the old clause now runs inquisitor.

**Requires tests:**
- T-W1: a diff that trips exactly one native gate (e.g. red-team Significant, everything
  else clean) yields `BLOCKED`.
- T-W2: siege runs on a security-surface diff and is skipped on a non-security diff
  (conditional trigger).
- T-W3: in the **standalone** reviewer-set, inquisitor runs when an escalator matches
  (interface/API/schema glob, dependency/lockfile glob, or a binary/unparseable path), is
  skipped when EVERY changed path is a pure-doc file with no escalator, and otherwise falls
  to the retained reach clause (`>1 changed file OR >1 top-level module` → run, else skip).
- T-W4: the **double-temper** (build Phase-4 temper + finish Step-2 temper) is killed —
  finish no longer re-runs temper after Phase 4. (warden still invokes temper several times
  *internally* — step-1 temper and the scoped re-temper after each later fixer; the step-4
  terminating leg is plain delve, not temper. The invariant is the killed
  cross-orchestrator duplication, not a literal single temper run.)
- T-W5: warden emits exactly one build-`PipelineID`-tagged verdict marker (the aggregate
  verdict) that build's Verdict Marker Verification accepts, and the red-team leg's marker
  (tagged with warden's run-id) is NOT surfaced by build's PipelineID filter (F2 / I-W7).
- T-W6: a clean diff (no native gate trips) yields `PASS`.
- T-W7: selection-eval — `/warden`-style prompts route to warden, not temper/quality-gate/
  delve, and vice-versa — including the "review my changes before I push" collision case →
  warden (M2).
- T-W8: in the **`full`** reviewer-set, inquisitor runs even on a single-file diff
  (unconditional — no regression of build Phase 4 Step 4 coverage; S3).
- T-W9: ordering — a later fixer leg's commits trigger a scoped re-temper before the
  red-team leg; **warden commits each fixer leg's residual** (temper/delve/red-team, all
  non-`fix:` `chore(warden):` subjects) so the frozen HEAD contains them; the red-team leg
  runs before the terminating read-only pass over `SHA_pre_redteam..HEAD` (which is **empty
  and benignly passes when the red-team leg is clean**); and a red-team fix that introduces
  an instance bug into the frozen HEAD is caught by the read-only plain-delve re-check
  (report-only, run exactly once, no fix loop, no inquisitor, BLOCK-on-trip) and yields
  BLOCKED before PASS (I-W6 / S-D).
- T-W10: *retired.* Under Option C warden emits **no** aggregate `code` calibration entry
  (each leg self-emits its native entry to `runs.jsonl`; I-W8), so there is no
  aggregate-emit behavior to assert. The number is left retired rather than renumbered so
  the surrounding Txx references stay stable.
- T-W11: delve leg — an unambiguous kept finding is fixed via `delve --fix` (committed by
  warden with a non-`fix:` `chore(warden): delve fixes <run-id>` subject) and delve re-runs
  until the predicate clears; a **surfaced-not-applied** finding, and a predicate that still
  trips after the **≤2-re-run cap**, both BLOCK with a named user hand-off (delve has no
  loop; S5).
- T-W12: build recovery — a missing/mismatched **warden** verdict marker after a just-run
  gate triggers build to re-invoke **warden** (the full reviewer set), not bare
  `quality-gate` (red-team only), so the recovery path cannot silently downgrade coverage
  (S-B / I-W7). *(The recovery-site repoint lands in Phase E.)*
- T-W13: **siege dispatches twice per warden run** on a security-surface diff — warden's
  own step-1 siege leg **and** the quality-gate red-team leg's internal re-dispatch at
  `SHA_pre_redteam`. Assert warden's QG-leg invocation passes **no** siege-suppression flag,
  so the two-siege mirror of build holds (S-A / I-W4; see §Calibration-ledger entries).
- T-W14: **temper-only fixer → frozen HEAD contains temper's fix (F-A regression).** A diff
  where temper is the sole fixer (temper fixes a Critical **by editing an existing line
  and/or creating a new file**; inquisitor all-PASS; siege clean/skipped; delve clean;
  red-team clean) — warden **commits temper's residual** (via `git add -A && git commit` so
  a **newly-created (untracked) file** is staged too) before the freeze, so the frozen HEAD
  (and the verdict/marker bound to it) **contains temper's fix — including any new file it
  created** (the S1 untracked-drop case); the gate never certifies a SHA that omits the fix
  that earned the PASS (F-A / I-W6 / S1).

## Testing strategy

- **Skill behavior evals** (`skills/warden/evals/`): reviewer-set selection by diff shape,
  disjunctive gate outcomes (per-native-gate trip → BLOCKED), clean-pass, verdict-marker
  emission. Mirror the delve/siege eval-harness pattern (deterministic scorer, CI-gated)
  where the gate logic is mechanical.
- **Selection-evals** (`skills/skill-selection-evals/`): warden-vs-{temper, quality-gate,
  delve} routing boundary.
- **Integration**: build Phase 4 + finish mock-dispatch fixtures updated to assert a single
  warden call site and the killed double-temper.
- Add the new suites to `scripts/run_tests.sh` (single source of truth).

## Failure modes / edge cases

- **Empty / binary-only diff**: warden reports "no changes to review" and returns PASS
  (delve's existing empty-diff handling).
- **A reviewer sub-dispatch dies**: warden surfaces the failed leg and returns `BLOCKED`
  (fail-closed — an unrun gate is not a pass), never silently drops it. A
  **condition-skipped** leg (siege on a non-security diff, standalone-inquisitor on a
  single-file **non-escalator code** diff) is **not** an "unrun gate" for this rule — only a leg that was
  *supposed to run* and died triggers the fail-closed BLOCK; a correctly skipped conditional
  leg is a normal PASS input, not a failure (M5).
- **quality-gate stagnation/escalation on the red-team leg**: warden propagates the
  escalation exactly as build Phase 4 does today; it does not swallow it.
- **Standalone warden on a detached HEAD**: require an explicit scope (delve's rule).
- **Standalone warden on a dirty-or-untracked working tree**: **REFUSE** with an actionable
  error ("commit, stash, or clean untracked files, then re-run `/warden`") — the fully-empty
  (`git status --porcelain`, tracked **and** untracked) clean-tree precondition is asserted,
  not papered over (Ordering step 0 / I-W6). No auto-save/restore machinery: warden pushes
  the precondition back to the user, exactly as it does for a detached HEAD.
- **Standalone finish (not from build) through warden (M3)**: finish today uses
  `crucible:red-team` directly because at finish time there is "no typed artifact." Routed
  through warden, the red-team leg is always `crucible:quality-gate` on artifact `code`,
  invoked with **warden's own run-id** as PipelineID — so it runs non-interactively (no
  between-rounds check-ins) in the standalone-finish path as well as inside build. warden's
  aggregate marker in a standalone finish carries no build PipelineID (there is no build),
  matching quality-gate's standalone-completion-record behavior. **Behavior change
  (disclosed, deliberate):** standalone finish is detected as `standalone` (no build
  clean-tree guarantee — finish has none of its own), so it inherits warden's
  assert-and-REFUSE precondition — `/finish` now **hard-REFUSES** a dirty-or-untracked tree
  at the review step, where it worked on a dirty tree before. An accepted change: the
  per-leg-commit attribution base requires a fully-clean tree.

## Migration & rollback (S4)

The maintainer chose one combined change (warden replaces build Phase 4 Steps 3–6 and
finish Steps 2–3). To keep that intent while giving a concrete regression escape for the
repo's two most load-bearing orchestrators, land it in two commits with a documented
revert:

1. **Land warden as a callable skill first**, with build Phase 4 and finish still wired to
   their **current** paths (no call-site change yet). warden's own evals + selection-evals
   must be green in `run_tests.sh` at this point.
2. **Cut the two call-sites over** to `Use crucible:warden` in a single commit, behind a
   documented **single-commit `git revert`** as the regression escape: the cutover is one
   combined change, so reverting that one commit restores the old Phase-4 Steps 3–6 +
   finish Steps 2–3 dispatch paths in one step. (No `CRUCIBLE_WARDEN=off` env shim — it
   would force build/finish SKILL.md to carry both the old steps and the warden call behind
   an env branch in prose, doubling the maintained surface for no gain over the revert; M6.)
   The old-path code is not deleted in this commit.
3. **Acceptance signal to remove the old steps** (a later commit): warden evals +
   selection-evals + the build/finish integration fixtures green in CI, **and** one real
   build driven end-to-end through warden (a live Phase-4 run producing the correct single
   build-tagged marker and killed double-temper, with each leg self-emitting its native
   calibration entry and warden emitting none). Only after that signal are the old
   Phase-4/finish steps and the shim removed.

This bounds the blast radius: if warden regresses build in live use, the revert restores the
pre-warden behavior in one step, because the old orchestration code still exists until the
acceptance signal fires.

**M-f caveats.** (1) *The one-commit revert is time-boxed.* The single-commit `git revert`
restores the old paths only in the **window between the cutover commit (step 2) and the
old-step-removal commit (step 3)**. After step 3 deletes the old Phase-4/finish steps, a
regression needs a **two-commit revert** (un-cutover + restore the deleted steps), or a
fresh re-add. (2) *no reconcile or leg coupling.* Under Option C warden emits **nothing**
to `runs.jsonl`, so there is genuinely **no** `reconcile_ledger.py` edit **and no
leg-SKILL.md edit** — warden simply does not emit; the legs self-emit their native entries
exactly as under build. This is not warden "solving" a double-entry: warden **avoids adding
a further** co-timed `code` entry by not emitting.

## Acceptance criteria

- `skills/warden/SKILL.md` with non-colliding frontmatter; canonical dispatch + return
  conventions linked, not copied; severity language cites `severity-verdict-contract.md` /
  `severity-rubric.md`.
- Disjunctive native-gate logic + per-reviewer sectioned report + conditional siege +
  reviewer-set-split inquisitor (unconditional in `full`, conditional in `standalone`) +
  warden-owned delve fix path, all per the reviewer table.
- Ordering (I-W6): clean-working-tree precondition **asserted on all paths** (`git status
  --porcelain` **fully empty** — standalone `/warden` **and standalone `/finish`**
  dirty-or-untracked trees **REFUSED**; only **build** guarantees a fully-clean tree at
  entry; no working-tree save/restore machinery); non-terminal fixers first (delve pinned
  **before** the red-team leg) with **warden committing each leg's full residual as it
  completes** (`git add -A && git commit`, non-`fix:` `chore(warden):` subjects;
  inquisitor/siege self-commit → no-op); scoped re-temper after later fixers; red-team leg
  next after capturing `SHA_pre_redteam`, warden commits its residual, then a read-only
  re-check of `SHA_pre_redteam..HEAD` (empty and benignly passing when the red-team leg is
  clean) by **plain delve in its native report-only mode only** (BLOCK-on-trip, run exactly
  once, no fix loop, no inquisitor — S-D) as the terminating leg before HEAD is frozen. The
  frozen HEAD therefore contains **every leg's committed fixes**, so the verdict/marker
  binds a SHA that contains the fixes that earned it (F-A).
- Single build-tagged verdict marker owned by warden (I-W7). warden writes **no** `code`
  calibration entry to `runs.jsonl`; each leg self-emits its native per-skill entry
  (temper/siege Tier-A, quality-gate, delve/inquisitor Tier-B stub), mirroring build — with
  **no `reconcile_ledger.py` edit and no leg-SKILL.md edit** (I-W8).
- build Phase 4 + finish refactored to single warden call sites; the replaced reviewer
  invocations are gone; double-temper gone. The two surviving build `quality-gate` call
  sites — the **Step-6 gate invocation** and the **recovery re-invoke on a
  missing/mismatched marker** — are **repointed to warden** so no path (normal or recovery)
  runs a narrower gate (S-B). *(These build/finish edits land in Phase E — Tasks 12/16;
  this task authors warden's SKILL.md only.)*
- **temper frontmatter description edited** to cede the push-gate phrasing ("before
  merging" / "before I push") to warden while keeping its single-reviewer triggers ("is this
  ready to ship", "review my changes", "review this PR", "code review", "check the diff") —
  the routing-collision fix (S-C / I-W3). *(Phase B/E.)*
- **finish refactor (M-3):** finish Steps 2+3 replaced by a single warden call, and build's
  finish-skip instruction rewritten to tell finish to skip the **warden call** **with the
  test-coverage (Step 2.5) skip preserved**. *(Phase E.)*
- **siege runs twice per warden run, mirroring build (S-A):** warden owns a siege leg at
  step-1 HEAD **and** lets the quality-gate red-team leg re-dispatch its internal siege at
  `SHA_pre_redteam` (warden does **not** suppress it) — coverage-equal to build's two
  sieges; T-W13 asserts it.
- Behavior evals + selection-evals green in `run_tests.sh`; catalog regenerated
  (`scripts/catalog.py`), skill count updated.
