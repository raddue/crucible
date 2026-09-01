---
ticket: "#488"
title: "The receipt name space — what a receipt may legally name, and how it resolves"
date: "2026-08-21"
source: "design"
supersedes: "docs/plans/2026-08-20-488-receipt-name-space-design.md"
---

# #488 criterion 1 — the receipt name space

**Status: design, under gate.** As of round 16 of run `2026-08-21T09-09-39` (dated 2026-08-24), this
document has been red-teamed **sixteen** closed rounds in this lineage (rounds 1–16), and this text
was further updated by a subsequent out-of-band audit pass and eight bounded fix/verify rounds (this
is the eighth), all outside that gate's own round numbering. `artifact-1.md` is 1502 lines / 124328 B; the live document
is strictly larger and grows with every edit including this one — the staleness delta is **at least
1696 lines** and increasing — read that as a dated floor, not a standing property, per §3.3's own
convention for exactly this class of claim. Its predecessor was gated separately, six times, and did
not pass; see the split record below. **Do not read the predecessor's gate history as applying to
this artifact.**

**That round count is a tally of gate iterations, not an evidentiary one, and this document's own §5
(I4) supplies the reason (B3 — Blind Spots F8): the round-current `artifact-N.md` copy §4's remedy
mandates has been written zero of fifteen times since round 1 (rounds 2–16), so each of these fifteen
rounds' receipts hash-vouches for a snapshot that was, by the time of its dispatch, unknown-to-stale
(**at least 1696 lines** stale by this measurement's own line-count floor: `artifact-1.md` is 1502
lines / 124328 B, the live document is strictly larger and growing — a line-count delta, not a byte
or changed-line count) rather than for the bytes actually under review at that round. Read "sixteen
closed rounds" as a count of iterations this document survived; the separate **fifteen** above is the
count of rounds (2–16) dispatched without a round-current copy — see §5 (I4) and §6.**

**Scope:** the name-space ruling only — *what a receipt may legally name, and how it resolves.*
**Two adopted mechanisms sit outside that line, named rather than silently smuggled in (F2 — Scope
Clarity F4):** the `dispatch-convention.md` `Inputs:` field (§3.4 channel 4) is a dispatch-header
schema change, not a name grammar, adopted because the channel-4 counter it denominates has no
committed input list to quantify over otherwise — and the same passage concedes the counter it enables
"carries no pin and no enforcer... is not claimed as verification," so the scope exception buys prose,
not enforcement. The `parse_claims` `(none)`-sentinel clause (I8, widened) is `CLAIMS`-body parser
hygiene, not a name-space rule — `CLAIMS` values are never receipt names — included because it is the
identical unanchored-`return` defect I8 already closes in `parse_artifacts` and `parse_trace`, found
one parser further down during the same audit pass. Both are accepted as adjacent, not as in-scope by
the letter of the line above; a maintainer who wants this scope line to bind literally should read
both as this ticket's deliberate exceptions, not as evidence the boundary is unenforced generally.
**No code changes are made by this document itself** — an earlier draft's *"No code changes in this
arc"* read as covering the ticket's whole implementation, and §8 schedules AC-2, AC-6's T2 and T6,
and I8/T10 as work *"this half can be scheduled and finished on today."* **T7 leg 2 is no longer among
them — §8 now gates it behind a fifth ordering constraint (§4, §8) this sentence did not carry before
this edit.** **AC-2, AC-6's T2, T6 and
T7 leg 2,
and I8/T10 are implementation obligations of this ticket and are in scope for its implementing
change, including the pin re-authoring §3 requires** (the `absolute` and NUL clauses landing in
`parse_artifacts`, and the two named `scripts/test_rcpt_verify.py` pins re-authored in the same
change). Answers #488 criterion 1, and folds **#513** deliberately. Takes **#519** as a stated
constraint.

**Baseline:** `dd06b80` (merged `main`). Every measurement below was taken on that tree, except where a re-run commit is named explicitly.

## Split record — read before using this document

This is the **reduced** half of `docs/plans/2026-08-20-488-receipt-name-space-design.md` (1929
lines, sha256 `530b7f5848973881a53e5f1f744fb60ef2d571a5b8e494323087a1a8eb038878`). That document
combined two separable rulings; the census-floor half was split out to **GH #530** on 2026-08-21.

- **Here:** §3.1–§3.4 — the name grammar and resolution rule. The half that **produces** the census.
- **On #530:** §1.3, §2.7, §3.5, §3.5-F, §3.6, AC-3, AC-5, OQ-1, OQ-7, and pins T4/T5/T8/T9 — the
  floor. The half that **consumes** the census.

**Why.** `/quality-gate` ran six rounds on the combined document (run `2026-08-20T09-05-29`,
trajectory 15 → 10 → 8 → 6 → 7 → 10, closed ESCALATED / DID NOT PASS). §3.1–§3.4 was stable for the
last three rounds; five of six rounds' Fatals and Significants landed on the floor. One defect class
relocated **eight** times without converging — the full ladder is on #530 and is not repeated here.

**The rationale's own outcome, stated rather than left implicit (A4 — Blind Spots F3).** The split
decoupled the *stable* half so it could proceed independently of the floor's continuing rounds. It did
not decouple the *schedule*: C, this document's central adoption, is gated on #530 in every branch
(below), the resolver ruling's acceptance figure and four of eight pins (T1, T1-neg, T3 and T7 leg 1 —
§8's opening note; T11's is OQ-9, undecided) wait on #530, and the split
added a second #530-facing dependency — the I2/§3.2 producer-rollout gate (§3.1 clause 2) — that the
combined document did not have. What proceeds independently today is the C-independent slice, which
§8's opening note states is a no-op at `quality-gate/SKILL.md:36` (A3). That does not mean the split
was the wrong call — five of six gate rounds' Fatals and Significants landed on the floor regardless of
where the document boundary sat — but the stated benefit (independence) and the measured outcome
(still blocked, with one more blocking dependency than before) point different directions, and this
document should say so rather than let the paragraph above stand as the last word on what the split
bought.

**Section numbers are deliberately unchanged from the pre-split original**, so the two documents stay
line-comparable and the gate record above stays auditable. Cut sections are retained as redirect
stubs rather than renumbered away.

⚠ **`§3.1` clause 2 still has an unruled dependency on the floor half, and that
dependency is a BINDING ORDERING GATE, not a disclosure.** Clause 2 emits a `resolved-by-walk`
sub-count whose disposition is **OQ-7**, which moved to #530 unruled. This document specifies the
*note and the counter*; whether that counter is summed into a floor is #530's to decide, and nothing
here presumes the answer. **Binding: C MUST NOT be implemented until either #530
rules OQ-7, or `quality-gate/SKILL.md:36` is amended in the same change** — because C zeroes the
counters `:36` reads on **16 of `live29`'s 29 receipts (55 %)** while the replacement counter is a
name `:36` does not read. **Both horns face #530** — (a) is #530's ruling and (b) edits a line §4
routes to #530, and (b) returns those same 16 receipts to UNVERIFIED, so it nets C's benefit to zero
— which means **C, this document's single adoption, is gated on #530 in every branch, and AC-4 and
AC-6's C-dependent pins with it.** §8 opens with that consequence so the acceptance criteria and
this note cannot be read against each other. See §3.1 clause 2, §3.4 channel 2, §4's `:36` row and
§8.

**A second, narrower gate covers rolling out §3.2's tracked-repo eviction rule to producers** —
the fix-agent-prompt's dispatch-input wiring, which carries §3.2's new hash obligations, **and the
`return-convention.md:104`/`:256` retraction (§4's contradiction-paragraph row), which instructs
every one of the convention's six adopting skills (§3.1 clause 2) to comply — a strictly larger
rollout than the fix-agent-prompt's single dispatch-input line** — because a
compliant producer could in principle produce the identical `:36` flip on a receipt whose only
residual is a tracked repo file, with no C and no #530 ruling required. **§3.3's citation rule is
not gated by the #530-facing gates above** — compliance there is a re-citation to the
orchestrator-supplied `artifact-N.md` copy, which resolves and hash-verifies — a genuine
verification, not a silent flip (see §3.1 clause 2's second ordering paragraph) — **but its
producer-facing rollout carries a third gate, on §4's `:758-760`/`:968` row (§5, I4): counting the
fourth (T7 leg 2's citation-form constraint, §4/§8) and fifth (T7 leg 2's own landing constraint, §4)
named below, **this document states five ordering gates, not two** (§6 states the same count; see
there for the full enumeration). The fix-agent-prompt's dispatch-input wiring and the
`return-convention.md` retraction both carry the
§3.2 dependency; `red-team-prompt.md`'s `:222` edit (§4) rolls out §3.3's resolution-prose half and
carries no such dependency; its `:184`, `:297` and `:329` edits are I4-bearing, carry the third
gate, and MUST NOT ship until §4's `:758-760`/`:968` row lands (§5, I4); so does
`return-convention.md:68`'s §3.3 clause (§4) and `return-convention.md`'s own `12-judge` worked
example (§4) — together the wider of the two I4-bearing files, because `return-convention.md`
reaches every one of the convention's six adopting skills, not only the red-team dispatch body;
neither the #530-facing
dependency nor the third gate applies to the fix-agent-prompt file's own authoring, nor to the
invariant text itself.

---

## 1. The defect

### 1.1 The contradiction as filed

`skills/shared/return-convention.md:104` says both of these in one paragraph:

> `ARTIFACTS` is the set of files this receipt vouches for, **not only the set it created**, so
> declaring a file you merely `READ` is legitimate — but declaring a **repo-relative path**
> (`scripts/foo.py`) does not resolve under the mandated roots. […] Such a declaration hard-FAILs
> under the mandated `--strict`.

The convention blesses and hard-FAILs the same declaration.

### 1.2 The defect underneath it — the name space was never specified

The contradiction is a symptom. The cause is that **`ARTIFACTS` `<name>` has no grammar**.

`return-convention.md:68` defines an artifact line as `<name>  sha256:<hex64>  <size>`.
`parse_artifacts` (`scripts/rcpt_verify.py:232-249`) splits the line, keeps `parts[0:3]`, and raises
only on arity (`ARTIFACTS malformed`) and on the hash field (`ARTIFACTS bad hash`). **`parts[0]` is
never validated.** The legal name space is `\S+`.

Every `<name>` occurrence in the convention (`:41`, `:68`, `:256`, `:413`) states *membership* rules,
never *shape* rules. The one normative-sounding line — `:256`, *"The artifact must resolve under
`--root`"* — sits in the **Scope** section describing Tier-2's behaviour: it constrains the
**linter's disposition**, not the **producer's grammar**. Nothing anywhere tells an author what to
write.

So `resolve_base`'s probe set became the de-facto definition of the legal name space **by accident**.
The grammar admits anything; the linter then retroactively sorts that space into
pass / `UNVERIFIABLE` / `FAIL` according to where the bytes happen to sit.

**This design is the first time the name space is written down.** That reframing is the deliverable:
#488 c1 is not "pick a resolver", it is "the convention has a hole where its name grammar should be".
**Where it is written down:** §3, *Lexical grammar* (the shape rules, enforceable at Tier-1 in
`parse_artifacts`) plus §3.1–§3.3 (the membership and resolution rules, enforceable only at Tier-2).
An earlier draft made this claim and delivered neither half in a checkable form — see §3.

### 1.3 What the floor actually does

> **Moved to #530.** §1.3 was split out of this document on 2026-08-21 and now lives on GH #530 (Tier-2 census floor). It is **not** reduced-scope here — it is a separate open ticket. Section numbers in this document are deliberately unchanged from the pre-split 1929-line original so the two remain comparable.

## 2. Measured evidence

Instruments: `scripts/measure_486_corpus.py` (shipped), plus throwaway scripts written during the
producing dispatch and since **archived off `/tmp`** to
`~/.claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate/scratch/2026-08-20T09-05-29/dispatch-archive/`
(§10). Repo tree clean throughout; nothing in `scripts/` was modified.

### 2.1 Baseline residual — reproduced

| corpus | `unreached` (art+wit) | `not-reachable` (art+wit) | sum |
|---|---|---|---|
| `corpus17` (n=17) | 3+1 = 4 | 4+3 = 7 | **11** |
| `live29` (n=29) | 1+1 = 2 | 30+10 = 40 | **42** |
| `codegate22` (n=22) — published, **withdrawn** (§2.6) | 0 | 0 | **0** |
| `codegate22` (n=22) — **real nested layout**, the decision figure (§2.6) | *(not split)* | *(not split)* | **96** |

All three reproduce `rc=0`. Total floor-relevant residual is **53 rows / 18 unique names / 32
receipts** (`corpus17` 5, `live29` 27, `codegate22` 0) **in the published `codegate22`
configuration**, and **149 rows** with `codegate22` on its real nested layout — **149 is the decision
figure**, and the one an implementer sizes the migration from. The `53` is retained because §2.3,
§3.1 and the #488 amendment all quote it, and every use of it that bears on a rule choice carries
the `codegate22 (real nested)` figure beside it. The receipt figure is distinct `(corpus, receipt)`
pairs over the residual rows of `counterfactual.json`, and it is the same 5 + 27 the pre-split
§1.3 blast-radius table (now #530) reports; the receipt is the unit #488 criterion 3 blocks on, so
understating it understates the promotion cost that #530 must defend. (Deduplicating bare receipt filenames across
corpora gives **28**, a different unit again.)

### 2.2 The residual is four disjoint classes, not one

`live29`'s 30 ARTIFACTS-leg `not-reachable` citations:

| class | count | share |
|---|---|---|
| `round-N-findings.md` — exists at `scratch-…/out-N/`, **one directory below** the probed top level | **19** | **63 %** |
| the **artifact under review** — a gitignored `docs/plans/` doc cited by bare basename | 8 | 27 % |
| `fix5-rerun.log` — never written to the dispatch root at all | 1 | 3 % |
| basenames of tracked repo files (`test_rcpt_verify.py`, `red-team-prompt.md`) — **#513's class** | **2** | **7 %** |

`_resolve_base_one` is a literal join with **no search**, so the dominant class misses by exactly one
directory. **#513's class is 7 %, not the dominant term** — correcting the #488 amendment's framing.

After a bounded walk of the supplied roots, the 9 surviving `live29` artifact-under-review
citations (the 8 above plus the leg's one `unreached` row — §2.5's `art rows 31`) **come from 9 fix
receipts** (`rcpt-2,5,8,11,14,17,20,24,28`). So in `live29`, #513's class
*is* the artifact under review, and it is **100 % of the fix population**.

### 2.3 Counterfactual residual per candidate rule

| rule | corpus17 | live29 | codegate22 (published — **withdrawn**, §2.6) | codegate22 (**real nested** — the decision column) |
|---|---|---|---|---|
| baseline (shipped) | 11 | 42 | 0 | 96 |
| **A** git-object at frozen SHA | 10 | 42 | 0 | 96 |
| **B** repo toplevel probed, tracked-only | 10 | 42 | 0 | 96 |
| **C** bounded walk **under supplied roots** (>1 hit = ambiguity FAIL) | 11 | **14** | 0 | **2** |
| **D** bare basename at top level of a supplied root | 11 | 42 | 0 | 96 |

The `(published)` column is retained **only** so the amendment's figure stays auditable beside the
corrected one. §2.6 withdraws it, and **no rule choice in this document is made from it.** The
decision column for `codegate22` is `(real nested)`, re-measured on `dd06b80`
(`codegate_nested_rules.py` → `baseline=96 A=96 B=96 C=2 (both of them ambiguous>1) D=96`;
96 cited names, 77 unique, all bare). The rule comparison is made from that column and not from
the withdrawn one.

**C's strongest result is in that column, not on `live29`:** **96 → 2**, on the corpus with the
largest residual and the most recent authoring practice — and the same column is the cleanest kill of
A, B and D, each of which resolves **zero** of 96. C's remaining 2 are the intra-root ambiguity
hard-FAILs of §2.5 (`artifact-under-review.diff`, 7 distinct hits; `mutation-battery.log`, 2), i.e.
C refusing a first-hit read, not C failing to resolve.

**A and B each resolve exactly one name across all three corpora** — `skills/warden/SKILL.md`
(re-verified over `counterfactual.json`: `corpus17 11 → A 10, B 10`; `live29 42 → 42, 42`;
`codegate22 (real nested) 96 → 96, 96`). Read that as **1 of 53** in the published configuration —
**1 of 149** on the decision layout, which is the figure the kill should be read from — not 3.
**D is already the shipped rule**, so its column is migration cost, not residual.

### 2.4 Approach A is dead for the class it was filed for — verified twice

`rcpt-11-qg-fix-r4.txt` declares `SKILL.md  sha256:fa509a2a…`. Those bytes **first exist in git at
`dd06b80`, committed 2026-08-18**. The gate that linted the receipt ran **`2026-08-17T16-23-44`**.
The previous commit touching that file is **2026-07-20**, a month earlier.

A fix agent's artifacts are **uncommitted working-tree edits by construction**. Git-object resolution
at any then-available SHA returns month-stale bytes and **hard-FAILs every fix receipt** — strictly
worse than today's silent exit 0. #513's own second proposed remedy is falsified by its own class.

Compounding: **no receipt in any corpus carries a commit SHA — all 68 — because the v1/v1.1 grammar
has no field for one.** A is not merely weak; it is not evaluable without a producer-side grammar
change first.

### 2.5 What C actually does — and the walk that must not be confused with it

Two different walks were measured. Keeping them apart is load-bearing:

- **C (adopted): bounded walk within the already-supplied roots.** On `live29`'s ARTIFACTS leg, **31**
  unresolved entries → **19 resolve, 12 remain**; on the witness leg **11 → 9 resolve, 2 remain**;
  **42 → 14 overall** (§2.3). **19 hash-MATCH, 0 hash-mismatch, 0 ambiguous.** Those
  receipts vouched for the *right bytes*; only the resolver could not reach them.
  **An earlier draft got this backwards, and the correction is the point of the section.** That draft
  read *"33 unresolved entries → 19 resolve, 14 remain"*, which mixed the two legs: the `33` is not
  the ARTIFACTS leg's row count and the `14` is the **whole-corpus** post-C residual, not the
  ARTIFACTS leg's. Both endpoints were wrong in the same direction, so `33 − 19 = 14` was internally
  consistent and reconciled with nothing. The ARTIFACTS leg's **31** is what §2.1's own table already
  implies (art `unreached` 1 + art `not-reachable` 30). Re-derived from `counterfactual.json` on
  `dd06b80`: `art rows 31 {not-reachable 30, unreached 1} C resolves 19 remain 12`;
  `wit rows 11 {not-reachable 10, unreached 1} C resolves 9 remain 2`. The two downstream uses of
  this corpus — §3.3's *"9 of `live29`'s 14 post-C residuals"* and §4's *"9 of `live29`'s 11 post-C
  residual receipts"* — were meant to be re-derived at the same time. §4's is **exact**; §3.3's
  carried the same leg-mixing this correction targets, one section over — `9` is the ARTIFACTS-leg
  row count, `14` is the whole-corpus row count, and the all-legs figure against the all-legs
  denominator is **11 of 14**, corrected at §3.3.
- **C′ (rejected, never proposed): walk over the repo tree.** Resolves `round-3-findings.md` /
  `round-4-findings.md` to the **committed witness fixtures** at
  `eval/ledger-return-protocol/tier2-fixtures/{j,m}/`, and `j-rt-mandated-witness-fires` is
  engineered so a witness pattern *fires* on it. That is grudge `e0f0a6b75692` reproduced by
  construction. Repo-wide basename collisions: `SKILL.md` **52 tracked / 94 in the worktree**
  (observed 2026-08-21; a dated reading, not a standing property, per §3.3 — a git worktree created
  2026-08-23 raises the **worktree** count further, to **146** — of which **94** are untracked —
  without changing the 52-tracked figure), `red-team-prompt.md` 2, 49 colliding tracked basenames
  overall.

**DEC-22 does not reach C.** DEC-22 rejects *widening `_allowed_bases`* — a containment escape. A
walk inside a root already supplied adds **no base** and escapes **no containment**; `_contained`
already holds for every hit. The "already-rejected" framing sometimes attached to C is not
supported by the DEC-22 record.

C is not free. On `codegate22`'s **real** nested layout it correctly hard-FAILs two names —
`artifact-under-review.diff` (**7 hits**, one per round `r1`–`r7`, seven *distinct* files) and
`mutation-battery.log` (2). That is C working as specified, and it is the shape #488's first comment
already recorded someone getting wrong by computing first-hit-wins instead of ambiguity.

### 2.6 `codegate22`'s zero does not mean what the amendment says it means

`measure_486_corpus.py:155-207` (`_codegate22_roots`) measures `codegate22` under a **flat layout
reconstructed in a temp dir at measure time**. The corpus as frozen **nests in `r1`–`r7`** (verified:
9380 nested files, 7 copies of `artifact-under-review.diff`). Re-measured on the real layout it is
**96** — the worst of the three, and second-worst per receipt.

`codegate22` is also not "citing less": 89 ARTIFACTS entries / 83 unique names over 22 receipts
(4.0 per receipt) vs `corpus17`'s 2.8 and `live29`'s 4.2.

So the amendment's *"the newest corpus already meets the pre-committed zero bar today"* is **evidence
about a configuration, not about authoring practice**, and must be withdrawn in that form.

### 2.7 The floor reads counters that cannot see the residual

> **Moved to #530.** §2.7 was split out of this document on 2026-08-21 and now lives on GH #530 (Tier-2 census floor). It is **not** reduced-scope here — it is a separate open ticket. Section numbers in this document are deliberately unchanged from the pre-split 1929-line original so the two remain comparable.

### 2.8 Four errors corrected in #488's own framing

1. *"#513's class dominates `not-reachable`"* — **false**, it is 7 %.
2. *"Every path-shaped residual is under gitignored `docs/plans/`"* — **false**;
   `skills/warden/SKILL.md` is tracked, path-shaped, and is the only name A resolves.
3. *"`docs/plans/…` resolves under no root and no git object"* — **half false.** Resolution is
   existence-based, not tracked-ness-based, so a gitignored **path-shaped** name *does* resolve
   whenever a supplied root sits inside a repo. The twin's two halves need different mechanisms.
4. *"Adding the repo root as a base is already-rejected"* — it is **shipped behaviour** wherever a
   root is in-repo (`_resolve_base_one` probes `repo-root-of-root/name` unconditionally;
   `_allowed_bases` adds that toplevel to the containment union for every root), and it is exercised
   by the entire committed fixture suite. DEC-22 correctly rejects *widening it to production*; the
   mechanism is live, not hypothetical.

---

## 3. The ruling

**ARTIFACTS is the vouched-and-checkable set. TRACE is provenance. They are different sets and the
convention now says so.**

- **`ARTIFACTS`** — every entry MUST resolve, under the roots the orchestrator supplies, by the
  resolution rule in §3.1. A name that cannot resolve is **not legal to declare**.
- **`TRACE`** — `READ`/`EDIT`/`WROTE` may name **anything**, including absolute repo paths, and is
  **not** resolution-checked **by the `ARTIFACTS` leg**. This is not new: #412/#397 already ruled
  `EDIT`/`WROTE` hashes a **deliberate non-gate — decorative provenance**. The ruling writes down a
  split that already exists in the code and stops the two being conflated. **One shipped path is the
  exception, and does resolve a `TRACE` name**: a rangeless witness citing a `READ`/`WROTE`
  entry on a `PASS` verdict falls through `witness_art_name` to `derive_art_name`
  (`rcpt_verify.py:1951`, `:1995`), which returns the first token of that `TRACE` entry's args, and
  `tier2_witness` (`:2786`) then resolves and reads it — see §3.2's consequence paragraph.

### Lexical grammar, and why it is stated separately from the rest of the ruling

§1.2's deliverable is *"the first time the name space is written
down"*, and an earlier draft discharged it through **AC-2** — *"`ARTIFACTS` `<name>` has a stated
grammar; `parse_artifacts` validates it"* — while stating no grammar anywhere. That criterion was
**unsatisfiable as written, in both available readings**, which is worse than being wrong because
AC-2 is this document's own definition of "done":

- Read **strictly** (a lexical predicate over `parts[0]`), the document supplied none, and the only
  lexical predicate that exists — `is_path_shaped` (`rcpt_verify.py:1637-1641`) — is one this
  document **forbids** as the answer twice: §3.4 move 1 adopts the path-shaped root-relative
  citation `out-9/round-9-findings.md` as the recommended remedy for 19 of 30 rows, and §2.8 item 3
  rules that a path-shaped gitignored name *does* resolve. Rejecting path-shaped names at Tier-1
  would also make the Tier-2 `--strict` path-shaped raise (`rcpt_verify.py:1696-1705`) unreachable —
  the exact branch **T6** exists to pin.
- Read **loosely**, AC-2 was **vacuous**: `parse_artifacts`'s entire input is the receipt text —
  its signature is `parse_artifacts(body)` — and the call that matters for AC-2 is the one inside
  `lint_receipt(text)` at `rcpt_verify.py:872`, **Tier-1, whose entire input is the receipt text.**
  (An earlier draft wrote *"`parse_artifacts` is called once, at `rcpt_verify.py:872`"*. Re-run on
  `dd06b80`, `grep -rn "parse_artifacts(" --include=*.py .` returns **nine** call sites:
  `rcpt_verify.py:872`, `:3356` and `:3772`; `measure_474_denominators.py:364` and `:482`;
  `measure_474_corpus.py:53`; `measure_486_corpus.py:295`; `test_measure_486.py:487`; and
  `eval/ledger-return-protocol/tier2-fixtures/_gen.py:428`. The *structural* conclusion is carried
  by the signature and is unaffected; what the "called once" reading understated ninefold is the
  **blast radius of a new raise** in that function, which is the half the costing below must
  answer.) No root, no git handle and no filesystem is in scope there, and all three of the
  document's rules are non-lexical (§3 needs the supplied roots; §3.2 and §3.3 need git). There is
  no predicate over `parts[0]` alone that expresses any of them, so §4's two concrete
  `parse_artifacts` items (`meta`, `size`) are hash/size hygiene and validate `parts[0]` not at all.

**The fix is to separate the two halves and say which enforcement site owns each.**

- **Lexical (Tier-1, `parse_artifacts`).** A legal `ARTIFACTS` `<name>` is a **POSIX-relative
  path**: it matches `[^/\s][^\s]*`, contains no NUL, has no leading `/`, and has no `..`
  path component. Whitespace is already excluded by the line grammar (`return-convention.md:68`
  splits on whitespace), so the operative additions are *not absolute*, *no `..`*, and *no NUL*.
  **All four are producer-normative; only two of them land as a Tier-1 raise** — *not absolute* and
  *no NUL*. *No `..`* is ruled producer-normative **only**, because landing it retires a committed
  security regression pin for a check Tier-2 already performs, and *no whitespace* needs no
  enforcement because the line grammar already makes it unreachable. Which, and why, is the costing
  paragraph below; it is not a detail.
  Path separators are **legal** — a root-relative sub-path is the §3.4 move 1 remedy — and the
  12-hex receipt-hash-prefix form stays legal, because the linter already rules it
  `NOT-APPLICABLE (receipt-hash-prefix, not a file)` at `_unresolved_disposition` and two corpus
  names use it. The one-line sentinel `(none)` remains legal as the empty-set marker, and **only**
  as that (I8).
- **Semantic (Tier-2, `tier2_artifacts` at `rcpt_verify.py:1806`).** Everything else the ruling
  says: the entry MUST resolve under the supplied roots (§3.1), MUST NOT name a tracked repo file
  (§3.2), MUST NOT name a gitignored path or its bare basename (§3.3). These need roots and git and
  are structurally unavailable at Tier-1.

**Costed against every measured population, so the lexical half cannot smuggle in a new hard-FAIL
class past I7.** Re-derived on `dd06b80` over the **362** `ARTIFACTS` names two of the three
populations hold — 258 across the three frozen corpora (`bare` 252, `relative-path` 4, `12-hex` 2)
and 104 across the committed `eval/ledger-return-protocol/**` fixtures (`bare` 101,
`relative-path` 3) — **zero** are absolute, **zero** contain a `..` component, and **zero** contain
whitespace or a NUL. So the rule rejects nothing *those two* populations declare.

**There is a third population, and an earlier draft's conclusion — *"its cost is therefore
prospective only, and that is the honest claim"* — was drawn from a census that stopped one
directory short of it.** `scripts/test_rcpt_verify.py` **constructs receipts that declare the banned
shapes on purpose**, and `scripts/run_tests.sh:103` gates it, so those receipts are evaluated on
every `bash scripts/run_tests.sh`. Measured dynamically rather than by reading: every receipt text
the suite writes to disk or feeds on stdin was captured across a full
`python3 scripts/test_rcpt_verify.py` run on `dd06b80` (**437 tests, 0 failures** against the
shipped build), and each one's `ARTIFACTS` names were read exactly as `parse_artifacts` reads them
(`parts[0]`) — **184 receipt texts, 164 `ARTIFACTS` name occurrences, 31 distinct names**, of which
**four are illegal** under the rule above:

| name | clause it violates | occurrences | constructed at |
|---|---|---|---|
| `../../credentials` | no `..` component | 3 | `test_rcpt_verify.py:5946` |
| an absolute `…/repo/scripts/bar.py` (tempdir path, so it varies per run) | not absolute | 1 | `:5521` |
| `f\x00.txt` | no NUL | 1 | `:4306` |
| `ou\x00t.log` | no NUL | 1 | `:3669` |

**The cost is not the four names, it is the pins they belong to.** A build carrying **only** the
lexical clause inside `parse_artifacts` and no other change, run against the same suite on
`dd06b80`: **437 tests, three failures** — and building each clause on its own attributes them
one-to-one:

| clause | test that goes red | what that test pins |
|---|---|---|
| no `..` | `TestTheWorldWritableRefusalIsMonotone.test_0777_does_not_reach_further_than_0755` (`:5925-5967`) | **siege S-3** — the world-writable-toplevel monotonicity inversion |
| not absolute | `TestARefusedProbeBaseIsDiagnosable.test_an_absolute_cited_name_is_diagnosed_too` (`:5513-5529`) | a refused probe base diagnosed through the **containment union** rather than the candidate list |
| no NUL | `TestHostileReceiptNamesAreEscapedToo.test_a_nul_in_a_receipt_name_never_reaches_the_channel` (`:4305-4310`) | a hostile name degrading to `UNVERIFIABLE` with the NUL escaped off the channel |

All three fail the same way, and it is **worse than red**: the Tier-1 raise fires before Tier-2
runs, so the Tier-2 diagnostic each test asserts on
(`absent under all bases`, `refused as probe base`, `world-writable git toplevel`,
`UNVERIFIABLE: f\x00.txt`) has **no reachable code path left** — the pin is structurally
unreachable, not merely failing. That is the identical failure mode this section already refuses for
path-shape, in the *Read strictly* bullet above — *"Rejecting path-shaped names at Tier-1 would also make the Tier-2
`--strict` path-shaped raise unreachable — the exact branch **T6** exists to pin"* — and the
argument was simply never applied to the clauses that survived it. It is also **quiet on the axis a
maintainer checks**: on the S-3 pin the exit code does not move (1 → 1); only the message and the
census line do.

**What is ruled, clause by clause, because the four do not cost the same thing.**

- **no whitespace — free, and already true.** The line grammar splits on whitespace
  (`return-convention.md:68`), so no name can carry one. Nothing to land, nothing to re-author.
- **no `..` — producer-normative, NOT landed at Tier-1.** It is **redundant for safety**:
  `_contained` (`rcpt_verify.py:1405`) already rejects the traversal at Tier-2 by realpath, which is
  precisely what the shipped build's *green* run of the S-3 test demonstrates (exit 1,
  `absent under all bases`). **"No faithful substitute" is withdrawn as the reason: a faithful
  substitute exists.** A path-shaped, `..`-free relative name whose realpath escapes the containment
  union via a planted symlink — the same construction T3's own second leg (§5) specifies — reproduces
  all four of `TestTheWorldWritableRefusalIsMonotone.test_0777_does_not_reach_further_than_0755`'s
  (`:5925-5967`) assertions and discriminates the keep-walking build identically; it is a one-line
  fixture edit, of exactly the kind this section already mandates at `:5513-5529` and `:4305-4310`
  for the two clauses that do land. **The clause is not landed anyway, for the actual reason: the
  fixture it would retire pins siege S-3, a security regression, and this ruling declines to
  re-author a security fixture as the price of a grammar-only benefit** — `not absolute`'s
  grammar-not-safety benefit (below) buys something `_contained` does not already provide (a name
  space an author can follow); banning `..` at Tier-1 buys nothing the realpath containment test does
  not already carry, so that benefit is not enough to justify touching a security pin. The grammar
  still says a legal name has no `..` component; `parse_artifacts` does not enforce it.

  **Corrected (C4 — Technical Soundness F3): "touches a security fixture" is not actually the
  discriminator, and stating it as one does not survive contact with the two clauses that do land.**
  `TestARefusedProbeBaseIsDiagnosable` and the NUL leg of `TestHostileReceiptNamesAreEscapedToo` are,
  by the same SIEGE-lineage hostile-input standard, security-relevant pins too, and both are
  re-authored in the same change without this ruling declining on that ground. What actually
  distinguishes S-3 is **breadth**, not category: `TestTheWorldWritableRefusalIsMonotone` pins a
  monotonicity property of `_refused_clause` across **multiple** permission levels (0755 → 0777), the
  broadest single regression test any of the three clauses touches, where the faithful substitute this
  section already names would retarget it onto `_contained`'s realpath containment instead — reusing
  the fixture's name and exit-code shape (this document's own claim: same four assertions, same
  discrimination) but not its subject. Whether that is close enough to count as "faithful" or is a
  quiet subject change wearing the original test's name is a threshold this document previously
  asserted as categorical and that turns out to have no categorical content. **OQ-10, new (§9):** does
  `..` land at Tier-1 with S-3 re-targeted at the containment shape (uniform treatment with the other
  two clauses), or does it stay producer-normative only (the status quo this document ships, on the
  breadth argument above rather than the retracted one)? Not decided here, recorded because the prior
  reasoning could not survive its own citation of a parallel case.
- **not absolute — landed at Tier-1, and `:5513-5529` MUST be re-authored in the same change, on
  a stated benefit, not merely a stated cost.** `not absolute` meets the `..` clause's own two-part
  rejection test identically — it is redundant for safety (an absolute name outside the containment
  union already returns `None` from `_contained`, the same mechanism that rejects `..`; measured:
  `resolve_base('/etc/hostname', <tmp root>) → None`) and pin-destroying with no faithful substitute
  (absoluteness *is* the shape `:5513-5529` exercises) — and an earlier draft landed it anyway with
  only the cost stated (*"an absolute name under a supplied root resolves today"*) offered as the
  reason to pay it, never a benefit. **The benefit, stated:** this clause is about the **grammar**,
  not about safety `_contained` does not already provide — §1.2's deliverable is that the name space
  is written down, and a name space of "POSIX-relative path" is a rule an author can follow, where
  "relative except absolute is also fine if it happens to land inside the containment union" is not.
  Landing it at Tier-1 makes the grammar a grammar rather than a membership rule the resolver decides
  after the fact — the exact accident §1.2 diagnoses — which `..`'s producer-normative-only
  treatment cannot buy by itself, since a rule that is only ever normative and never enforced is not
  distinguishable from no rule at all on the one channel (Tier-1 exit code) an implementer can
  script against. **The cost this benefit buys, stated rather than left implicit:** §3.2 mandates a
  tracked repo file's `TRACE` home carry its **absolute** path while §3.1 mandates bare relatives in
  `ARTIFACTS` — a producer moving a name between the two sections, the single most common edit this
  ruling asks producers to perform, now gets a **Tier-1 hard-FAIL** for pasting the wrong one of two
  mandated forms, where today the same paste resolves and verifies. That is a new failure mode
  created by the ruling on the exact edit the ruling requires it to make, and it is priced here
  because I7 is scoped to *"what the **walk** does to the failure taxonomy"* and does not reach it —
  see §4's costing note, which now names this class beside move 1's.
- **no NUL — landed at Tier-1, and the NUL leg at `:4305-4310` MUST be re-authored onto the Tier-1
  message in the same change**, which MUST render the name through `_show_path` so the
  escaping guarantee that leg exists for survives the move rather than being deleted with it. Its
  sibling ANSI-escape leg (`:4312-4315`) is untouched by the rule and keeps the Tier-2 half of the
  same guarantee. **The same benefit test applies, more weakly**: the shipped build already degrades
  a NUL name to `UNVERIFIABLE` with the NUL escaped off the channel (a green committed pin), so the
  safety property this clause states exists before it lands — the benefit here is the same
  grammar-not-safety one, moving a soft `UNVERIFIABLE` to a hard Tier-1 `LintError`, which is a real
  behavioural change (fail loud vs. fail soft) even though the escaping guarantee is not new.

**The honest cost sentence is therefore:** the lexical rule rejects nothing any production receipt
or committed fixture declares; it rejects **four** names the CI suite constructs on purpose; landing
its two enforced clauses retires **two** committed regression pins unless they are re-authored in
the same change, and the third clause is not landed at all because retiring **siege S-3** is not a
price this ruling is willing to pay for a check `_contained` already performs. **I7 is unaffected**
— its terms are *"any further new hard-FAIL class **reaching an orchestrator**"*, and this class
reaches the CI suite, not an orchestrator. AC-2 carries the re-authoring obligation and §4 carries
the row (`scripts/test_rcpt_verify.py`).

### 3.1 Resolution rule (answers sub-question 1)

A legal `ARTIFACTS` name resolves by, in order:

1. literal join of the cited name onto each supplied root, in declaration order (**shipped,
   unchanged**). **A cited name may itself be multi-segment** (`out-9/round-9-findings.md`), in
   which case the join lands **below** that root's top level even though no walk ran — see the note
   below and §3.4 move 1;
2. **NEW — a bounded walk within each supplied root, over the names clause 1 did not resolve.**
   Among those, more than one hit **among the supplied roots' own subtrees** — the walk adds no base
   and **does not enter any root's git toplevel** — is an **ambiguity hard-FAIL**, never a first-hit
   read.

   **Five details the walk cannot be implemented without — two were left to be inferred by an earlier
   draft, and three more (traversal cost/failure, temporal scope, content-vs-path ambiguity) were left
   unruled entirely (C1–C3 — Edge Cases F1/F2/F5).**
   - **Match key.** The walk matches the **full cited name as a relative path** under each root when
     the name is path-shaped, and the **basename** when the name is bare. **It never matches a
     path-shaped name by its basename.** This is not academic and it is not the shape the measurement
     used: `codegate_nested_rules.py` — the script §2.3 quotes for the decision column — computes
     `base = n.rsplit("/",1)[-1]` and walks `root.rglob(base)`, so under *that* rule
     `docs/plans/foo.md` may be resolved to, and hash-verified against, a file at an entirely
     different relative path. The figures are insensitive to the difference today
     (`codegate22`'s 96 residual names are 100 % bare — reproduced: `shapes: Counter({'bare': 96})`;
     `live29`'s only path-shaped residual name is
     `docs/plans/2026-08-07-474-witness-match-fail-open.md`, once on each leg, and it resolves under
     **neither** reading — re-derived: `C=False, hits=0` on both rows), which is precisely the
     problem: **no pin here can discriminate the two readings**, so the divergence would ship
     unpinned into the population **§3.4 move 1 is about to create**, since move 1 tells producers to
     cite `out-9/round-9-findings.md` — a path-shaped root-relative name — for 63 % of the dominant
     class. See AC-4 on what a divergence from 14/2 then means.
   - **Containment.** **Every walk hit is subject to the same #397 containment test as clause 1's
     candidates** — `_contained` (`rcpt_verify.py:1405`) against `_allowed_bases`
     (`rcpt_verify.py:1281-1317`; an earlier draft cited `:1320-1356`, which is `_resolve_base_one`'s
     own body, not `_contained`'s or `_allowed_bases`'s) — and a hit
     whose realpath escapes the union is **discarded, not counted toward ambiguity**. `_contained`
     exists because the cited name is receipt-controlled, i.e. attacker-controlled, and an `rglob` is
     a strictly **larger** candidate surface than a literal join, so the guard matters *more* under
     clause 2, not less. I6's *"containment (`_allowed_bases`) is unchanged; the walk adds no base"*
     is a statement about the **base set** and says nothing about whether hits are containment-tested;
     `codegate_nested_rules.py` applies no `_contained` test at all
     (`for p in root.rglob(base): if p.is_file(): hits.add(...)`). T3 carries a leg for the
     symlink-escape hit.
   - **Traversal cost and failure semantics (C1 — Edge Cases F1).** "Bounded" above means scoped to
     the supplied roots, not a resource bound: no timeout, depth limit or file-count cap is specified,
     and `codegate22`'s own dispatch root proves a supplied root can hold **10,165 files** (§4). A
     walk-time `OSError` (permission-denied, a vanished entry) is a third disposition I7's terms do
     not yet name: silently skip it (fail-open, the grudge this document exists to arrest) or hard-FAIL
     on it (an unenumerated new class). **Ruled:** a walk-time `OSError` on one candidate drops that
     candidate from the hit set without aborting the walk or the lint — the same posture `_contained`
     already takes toward a hit it cannot resolve — so the walk stays inside I7's two enumerated
     classes rather than adding a third; an implementer choosing a file-count or depth cap for
     performance reasons is free to, since no measured corpus makes one load-bearing. Unmeasured, and
     named as such rather than left silent.
   - **Temporal scope (C2 — Edge Cases F2).** The hit set clause 2 counts is the supplied roots'
     subtrees **as they exist at lint time**, and a supplied root can be written throughout the run the
     receipt belongs to — `quality-gate/SKILL.md:968` mandates a write into `<findings-root>` after
     every round, and parallel subagents write into the dispatch root concurrently. So ambiguity and
     resolution are properties of *when* the lint ran, not fixed properties of the receipt: a name that
     resolves cleanly on first lint can become an ambiguity hard-FAIL on a later re-lint, for a file the
     producer never touched and could not have controlled, and the reverse (an ambiguous name resolving
     cleanly once a colliding file is later removed) is equally possible. **Ruled:** clause 2's
     disposition is evaluated once, at the lint invocation that produced the receipt's own verdict; this
     document does not mandate or assume re-lint reproducibility, and a re-lint that disagrees with the
     original is not by itself evidence of a broken build. §3.4 move 1 increases this exposure (it
     recommends citing `out-N/` names that keep being written to for the run's duration), and it is
     priced as a cost of move 1, not of C's walk specifically — I7's enumeration is unaffected because
     the class is a property of *when* the lint runs, not a new hard-FAIL disposition.
   - **Ambiguity counts content, not paths (C3 — Edge Cases F5).** As specified above, ambiguity counts
     **realpaths**, never the declared sha256. Two consequences, of different severity. **(i)
     Byte-identical duplicates are not ambiguity and MUST NOT hard-FAIL.** Multiple walk hits whose
     **content** is identical to each other — a backup copy, or the same file reachable through two
     chunk roots — verify the identical bytes regardless of which is read, so the walk MUST de-duplicate
     hits by content hash before counting: "**more than one hit**" means more than one
     **distinct-content** hit, not more than one path. §2.5's own hash-MATCH figures (19 of `live29`'s
     19 walk-resolved rows) are unaffected by this correction — none of that corpus's hits were
     duplicate paths — so the correction is prospective. **(ii) A planted or coincidental basename
     collision under a world-writable root remains a real, cheap denial-of-verification, and this
     document accepts it rather than closing it.** Content-deduplication does not help here, because the
     planted file's content differs from the real one by construction — the hit set still has more than
     one distinct content, and the walk still cannot tell which is the declared file without either
     resolving to the hash-matching hit (a stronger disambiguation this document does not adopt, because
     it would need its own review against every pin this table already commits, starting with T1's own
     fixture, which depends on ambiguity firing regardless of hash) or refusing to guess (the shipped,
     adopted answer). **Accepted, on the same ground I7(ii) already accepts a class it cannot close**: a
     compliant producer under a world-writable root already has no portability guarantee (§3.1,
     `_refused_clause`), and this is a further instance of that same accepted gap, not a new one — named
     here because C3 measured it as reachable through the walk specifically, which an earlier draft did
     not check.

   **`RESOLVED-BY-WALK: <name> (<relpath-from-root>)` and its census sub-count `resolved-by-walk`
   are keyed on resolution DEPTH, not on which clause resolved.** They MUST fire whenever a cited
   name resolves to a path **below a root's top level** — whether by clause 1's literal join of a
   multi-segment name (§3.4 move 1: `out-9/round-9-findings.md` resolving inside `<findings-root>`
   is this case, not a walk hit) *or* by clause 2's walk finding it deeper still. Both `<name>` and
   `<relpath-from-root>` render through `_show_path` (`rcpt_verify.py:1577`), on the same
   SIEGE-R2BA-4 grounds as every other receipt-supplied name already rendered onto the channel —
   reported beside the floor buckets and **not** summed into them. **Which clause resolved it is a
   parenthetical, not a second mechanism**: the note MAY record `(via clause 1)` / `(via clause 2
   walk)` for whoever reads it, since `resolve_base` (`:1364`) / `_resolve_base_one` (`:1320`) must
   already report *how* a name resolved for §4's other rows, but the counter is the same counter
   either way — a build with two separate counters for the two resolution paths is a broken copy of
   this clause, not a valid one, because it re-opens the exact gap this re-keying closes (a producer
   remedy that resolves via clause 1 must bump the identical counter a walk hit bumps, or the two
   remedies stop being comparable at `:36`). **Whether that counter is summed into a floor is #530's
   decision, not this document's, and it is unruled** — it was carried on the pre-split §3.5 as an
   explicit table row and as **OQ-7**, both of which moved to #530. This document commits only to
   *emitting the note and bumping the counter*; it deliberately does not assert that the counter is
   excluded from anything, because the ground for that exclusion lived in the half that split off. A
   reader implementing §3.1 needs the note and the sub-count and nothing more. This clause is not
   decoration: see §3.4 channel 2. Without it, C silently swallows the only mechanical evidence that
   `quality-gate/SKILL.md:312`/`:951`'s location pin was violated — and without the clause-1 half,
   §3.4 move 1 silently swallows the identical evidence through the remedy this document itself
   recommends.

   **Ordering, binding — in the shape §3.1 already uses for `siege`/#496
   and §5 for I4.** **C MUST NOT be implemented until either (a) #530 rules OQ-7, or (b)
   `quality-gate/SKILL.md:36` is amended in the same change to treat a non-zero `resolved-by-walk`
   as UNVERIFIED.** Which of (a) or (b) is taken is a **maintainer decision and is not made here**;
   what is ruled here is that shipping C with neither is not permitted.

   **The two horns are not equivalent, and an earlier draft presented them as an even choice.**
   Horn (a) is another ticket's ruling. Horn (b) is an edit to `:36`, a surface §4 has **routed to
   #530** (*"No edit to `:36` is scheduled by this document"*) — and on this document's own numbers
   it is **self-cancelling**: amending `:36` to treat a non-zero `resolved-by-walk` as UNVERIFIED
   returns exactly the **16 of `live29`'s 29 receipts (55 %)** that C un-flags, so at the census's
   only live consumer C's measured benefit nets to **zero**. OQ-7 says this of the *floor* horn —
   *"summing the counter puts every one of those rows straight back to blocking and makes adopting C
   buy nothing"* — and the same shape holds at `:36`. So (b) is a **safety** horn, not an equivalent
   one: it makes shipping C harmless rather than useful. **The real choice is "wait for #530" vs
   "ship C knowingly fail-open",** and (b) is the way to take the first while shipping code. The
   consequence for scheduling — that C, this document's single adoption, is therefore gated on #530
   in **every** branch — is recorded in §8, whose acceptance criteria are otherwise silent about it.

   **§3.3 compliance is not a silent flip — it is a genuine verification, falsified 14/14 on both
   corpora; §3.2 compliance is a distinct question with no measured population today.** An earlier
   draft read §3.2's tracked-repo eviction and §3.3's artifact-under-review citation rule as producing
   "the identical flip at `:36`, through the identical mechanism," reasoning that once a producer
   complies and moves the illegal name to `TRACE`, the residual disappears and the receipt reads clean
   "with nothing about that file verified before or after." That is false for §3.3, on both frozen
   corpora, for every receipt in the measured population. §3.3's compliant move for the
   artifact-under-review class is not an eviction to `TRACE` at all — it is a citation to the
   **orchestrator-supplied single-home copy** (`corpus17`'s shipped `artifact-N.md` shape), and that
   copy already exists, at the top level of the supplied findings root, byte-matching. Verified
   directly (`sha256sum` against the frozen findings roots): `live29`'s nine artifact-under-review
   flip receipts (`rcpt-2`, `rcpt-5`, `rcpt-8`, `rcpt-11`, `rcpt-14`, `rcpt-17`, `rcpt-20`, `rcpt-24`,
   `rcpt-28`) each declare an illegal name whose hash matches one of `artifact-2.md` through
   `artifact-10.md`, one-to-one; `corpus17`'s five residual receipts (`rcpt-3`, `rcpt-5`, `rcpt-6`,
   `rcpt-18`, `rcpt-19`) match `artifact-2.md`, `artifact-2.md`, `artifact-3.md`, `artifact-6.md`,
   `artifact-7.md` the same way — three of those five already declare a different `artifact-N.md`
   compliantly **in the same receipt**, so the compliant form is demonstrably available to that
   producer. So the flip §3.3 compliance produces is: the illegal name is replaced by a legal one
   that Tier-2 resolves and hash-verifies. The receipt reads clean **because the artifact under
   review is now genuinely verified** — the opposite of the silent fail-open this document elsewhere
   arrests. **§3.3's rollout is therefore not gated.**

   §3.2 is the separate question, and it has no compensating population to gate against **today**.
   Re-derived at the receipt level from `counterfactual.json` on `dd06b80` — **not**
   `residual_census.py`, which the archive holds but which does not run as shipped (hardcoded
   dead-path input; see AC-4's ⚠ paragraph) — grouping `live29`'s residual rows by receipt: of its
   **27** residual-carrying receipts, **9** flip to clean under I3/§3.3 compliance alone (all
   artifact-under-review-shaped) and **zero** flip under I2/§3.2's tracked-repo class alone — the
   only receipt carrying a tracked-repo residual, `rcpt-22`, also carries a `round-7-findings.md`
   residual (a different, misplaced-file class C addresses, not an I2/I3 shape), so it does not flip
   on I2 alone. `corpus17` flips **5 of its 5 (100 %)** the same way — **4 by §3.3 alone, 1
   (`rcpt-18`) by §3.2 and §3.3 together**, not "all by §3.3's class" as an earlier draft had it:
   `rcpt-18` carries both a tracked repo file (`skills/warden/SKILL.md`) and artifact-under-review
   names, so it needs both invariants to flip — and no `corpus17` receipt flips on §3.2 alone either.
   **This flip census counts declared residual rows and does not model `tier2_artifacts`'s
   raise-and-abandon**: `corpus17/rcpt-18` hard-FAILs first on `fix-journal.md`'s sha256 mismatch
   (§3.4 move 1, T6), so `:36`'s UNVERIFIED disposition — reached only on a lint that *completes* —
   is never assigned to it on today's rule either, and whether it belongs in a "flips from UNVERIFIED
   to clean" population at all is unchecked here; that gap is not particular to `corpus17`. **The
   second ordering gate therefore has no measured supporting population in either corpus today — it
   is prospective, not live** — I2 and I3 are stated as binding invariants by this document itself,
   so a compliant producer could in principle produce a §3.2-alone flip the day this document is read
   as governing guidance, independent of whether C or the walk ever ships; nothing measured says that
   population is non-empty today.
   Therefore: **the producer-facing rollout of I2/§3.2's `TRACE`-eviction rule — both the
   fix-agent-prompt dispatch-input wiring that carries §3.2's new hash obligations (§4) and the
   `return-convention.md:104`/`:256` retraction (§4's contradiction-paragraph row) — MUST NOT
   ship to producers until either (a) #530 rules OQ-7, or (b) `quality-gate/SKILL.md:36` is amended
   in the same change to also treat a receipt whose `TRACE` carries a `PROVENANCE-ONLY:` note naming
   a path-shaped or absolute name (below) as UNVERIFIED.** This gate is **prospective**: its measured
   population is zero receipts in both frozen corpora today (above), so no live rollout is blocked by
   it — it is named in the same shape §3.1's C-gate is named for a population that is live, in case a
   future producer population is not. The invariant I2 itself is **not** gated by this — it is a
   checkable-by-inspection statement of what a legal receipt looks like, unchanged from the moment
   this document is read — what is gated is instructing producers, at scale, to comply, whether that
   instruction travels through the fix-agent-prompt file's dispatch-input wiring or through the
   convention every producer already reads:

   - **The fix-agent-prompt file.** Rollout is the `quality-gate/SKILL.md` dispatch-input edit named
     in §4's fix-agent-prompt row (the line mirroring `:580`'s clause for the verifier), **not the
     prompt file's existence.** The file may be authored and merged on its own; only that one line —
     adding the prompt's content to the fix dispatch's input list — is what this gate withholds, and
     it MUST NOT be added until the gate clears.
   - **`return-convention.md:104`/`:256`.** Unlike the fix-agent-prompt file, this edit has no
     separable authored-but-not-wired state: the convention is already the live document its **six
     adopting skills** — the live adopter set the convention's own header defines
     (`grep -rln "CANONICAL: shared/return-convention.md" skills/`, minus the definition file):
     `build`, `quality-gate/SKILL.md`, `red-team/SKILL.md`, `red-team/red-team-prompt.md`, `siege`,
     `warden` — consume, so the moment the
     retracted `:104`/`:256` bytes land on the machine every one of those six is instructed, with
     no staging path or version pin separating "edited" from "live" (the same shape §4's
     `red-team-prompt.md` row names for that file). The looser `grep -rln "return-convention"
     skills/` returns eleven, but five of those are not adopters: four carry no marker, and the
     fifth is the definition file, which carries the marker only to define it and is excluded by
     `return-convention.md:17-20`. This is the **larger** of the two rollout
     vectors, not a smaller companion to it, and it is gated on the identical terms: the edit itself
     MUST NOT be made until the gate clears.

   **I3/§3.3's rollout is split.** `red-team-prompt.md`'s `:222` edit (§4) rolls out §3.3's
   resolution-prose half, and §3.3 compliance is a genuine verification, not a flip (above), so there
   is no population, live or prospective, for that edit to gate against. Its `:184`, `:297` and
   `:329` edits are I4-bearing and carry the third ordering gate (§5, I4): they MUST NOT ship until
   §4's `:758-760`/`:968` row has landed. This file **is** still the
   dispatched agent's prompt body (`quality-gate/SKILL.md:341`, `:247`; `red-team/SKILL.md:134`,
   `:273`) — the moment the edited bytes are on the machine the skills read from, the next red-team
   dispatch carries them, with no flag, staging path or version pin in this document or in the repo's
   normal workflow that would separate "edited" from "live" — so for this row each edit is still its
   own rollout, and while nothing #530-facing withholds `:222`, the third gate withholds
   `:184`/`:297`/`:329`. §8 schedules only **the root-relative-citation half of `:222`** as
   C-independent, and only once T7's second leg (§5) — the clause-1 depth half of
   `RESOLVED-BY-WALK:` and `resolved-by-walk`, itself C-independent — has landed, a fourth ordering
   constraint stated in the same shape as the other three; the within-root-walk half describes C and
   lands with C, per AC-8. §8 withholds `:184`/`:297`/`:329` until the third gate clears, on the
   terms above, beside AC-1's first half and AC-2.

   **Horn (b), scoped by name shape — its cost stated honestly against the receipt unit rather than
   netted against a population it does not reach.** An earlier draft left horn (b) reading *"a
   `PROVENANCE-ONLY:` note for a name that would have been residual under today's rule"* — a
   predicate the shipped note text (§3.4: `PROVENANCE-ONLY: <name> (declared in TRACE, not
   verified)`, one format, no marker, no reason code) cannot carry, so no reading of `:36` could
   implement it: read narrowly, `:36` cannot tell the evicted class from the ~250 compliant
   provenance entries beside it; read broadly, `:36` marks nearly every receipt UNVERIFIED (§3.4
   measures the note firing 302–330 times over 68 receipts, layout- and truncation-reading-dependent).
   **The fix is to narrow
   which notes `:36` READS, not which notes are EMITTED — no second note format, no reason code, no
   change anywhere to §3.4's single-format MUST or to its "no new I/O, does not resolution-check
   `TRACE`" property.** Horn (b) instead reads only the subset of already-specified
   `PROVENANCE-ONLY:` notes whose `<name>` is **path-shaped or absolute** — `is_path_shaped`
   (`rcpt_verify.py:1637-1641`) for the first half, a leading-`/` check for the second — a predicate
   over the `TRACE` name's own text, decidable with **no git call, no toplevel and no new I/O**,
   because it is the lexical shape §3.2 already mandates for a compliant `TRACE` entry naming a
   tracked repo file (absolute path). **§3.3 mandates no `TRACE` shape at all** — its citation rule
   binds `ARTIFACTS`, not `TRACE`, and the compliant `TRACE` form for the artifact under review is
   the **bare** `READ artifact-N.md` §4's `red-team-prompt.md` row specifies — so this is a §3.2
   shape only, not the "§3.2: absolute; §3.3: path-shaped" pairing an earlier draft named.

   **Measured in the receipt unit `:36` actually reads, horn (b) flags 49 of the 68 frozen receipts
   (72 %)** — `corpus17` 13 of 17, `live29` 21 of 29, `codegate22` 15 of 22 — against the document's
   own costed population of 9 of `live29`'s 27 residual-carrying receipts and 5 of `corpus17`'s 5 (14
   total; SIG-1's correction to the earlier 12/5). **The narrowing does not land where it was
   costed.** Worse, compliance makes the over-fire permanent rather than incidental: §3.2 mandates
   that a tracked repo file's legal `TRACE` home carry its **absolute path**, and a tracked repo file
   is by I2 never in `ARTIFACTS`, so its basename can never match a verified `ARTIFACTS` basename —
   the `PROVENANCE-ONLY:` note for it therefore always fires, absolute, and horn (b) always flags the
   receipt. **A §3.2-compliant `TRACE` entry guarantees permanent UNVERIFIED under horn (b): no
   producer edit clears it, because the shape that triggers the flag is the shape §3.2 requires of a
   compliant producer.** Withdrawn: the earlier draft's *"this does not widen horn (b) past what it
   already costed"* — true of notes (a subset of all fired notes), false of receipts (72 % against a
   costed 20 %), which is the unit that decides anything at `:36`.

   **The 49/68 figure is costed against the flip population; the number that decides whether horn (b)
   is a *safety* move is a different denominator, and this document has not stated it until now: how
   many receipts horn (b) moves from verified to UNVERIFIED that carry no residual today.** Re-derived
   by the same instrument, grouping horn (b)'s 49 receipt-level flags by whether the receipt carries a
   residual row today (the same "residual-carrying" figures the table above already states for
   `live29`/`corpus17`, and §2.6's stated zero for `codegate22`):

   | corpus | n | residual-carrying today (`codegate22` published — **withdrawn**, §2.6) | horn (b) flags | flagged but CLEAN today |
   |---|---|---|---|---|
   | `corpus17` | 17 | 5 | 13 | 9 |
   | `live29` | 29 | 27 | 21 | 2 |
   | `codegate22` (published — withdrawn) | 22 | **0** | 15 | **15** |
   | **total (published)** | **68** | 32 | **49** | **26 (38 % of the corpus)** |

   | corpus | n | residual-carrying today (`codegate22` **real nested** — the decision layout, §2.1) | horn (b) flags | flagged but CLEAN today |
   |---|---|---|---|---|
   | `corpus17` | 17 | 5 | 13 | 9 |
   | `live29` | 29 | 27 | 21 | 2 |
   | `codegate22` (real nested) | 22 | **19** | 15 | **1** |
   | **total (real nested — the decision figure)** | **68** | 51 | **49** | **12 (18 % of the corpus)** |

   `codegate22`'s zero above is the published, **withdrawn** reading (§2.6) and, per §2.1's own rule
   that every use bearing on a rule choice carries both layouts, is retained here **only** so the
   withdrawn figure stays auditable beside the corrected one — **no rule choice below is made from
   it.** Under the decision layout `codegate22` carries **19** residual-carrying receipts, not zero,
   and its flagged-but-clean count is **1**, not 15: it is the **weakest** contributor to the 12
   flagged-but-clean total, not the sharpest. Measured benefit (flips horn (b) prevents, from the flip
   census above): **zero** — the harm it exists to prevent has a measured population of zero receipts
   in both frozen corpora today, the same population "prospective, not live" already describes.
   **Measured cost, decision layout: 12 receipts (18 % of the corpus) moved from verified to
   permanently UNVERIFIED** — permanent for the reason stated in the paragraph above (no producer edit
   clears a §3.2-compliant flag); the published-layout reading gives 26 (38 %), and it is the withdrawn
   figure, not the one a maintainer should schedule from. Horn (b) is therefore not a safety/coverage
   tradeoff with two live sides; it is a guaranteed cost against a benefit that, measured, is zero. It
   remains a documented option below (§8) rather than withdrawn outright, because #530 could in
   principle rule OQ-7 the other way and change the calculus on the C-gate side — but an implementer
   scheduling from this paragraph should read horn (b) as foreclosed by its own numbers, not as a live
   second exit.

   **Horn (b) simultaneously under-fires on the bare-basename `TRACE` eviction §3.4 measured as
   live, and the scoping §3.4 rejected for emission transfers here in the unit that decides
   anything.** §3.4 rejected shape-scoping for *emission* on the ground that a bare `TRACE` basename
   absent from `ARTIFACTS` would go silent — measured there at **185 (flat; not re-derived under the
   real nested layout, where the denominator is 330)** of the 307 flat fires under the
   adopted match key, a shape populated *right now*: `live29/rcpt-22-asreturned.txt` carries
   `red-team-prompt.md` and `test_rcpt_verify.py` bare, at TRACE #7–8, both also declared in that
   receipt's `ARTIFACTS`. Horn (b) emits every note unconditionally, exactly as §3.4 specifies —
   nothing goes silent on the wire. But §6 establishes `quality-gate/SKILL.md:36` as the census's
   **only** reader — "there is no human reader of `ARTIFACTS` names, only `:36` reading counters" —
   so a note horn (b) does not read is, in the only unit that decides anything, indistinguishable
   from one that was never emitted: this is the same argument this document makes against §3.4's
   rejected reading, applied now to the reading rather than the writing, and it transfers rather than
   failing to. Measured: **122 of the 307 flat, no-truncation fires (40 %)** are bare and invisible to
   horn (b) — the cheapest compliant-looking move for a half-obeying producer is to delete the two
   `ARTIFACTS` lines and leave `TRACE` untouched, which `live29/rcpt-22` already shows on disk today.
   **Not re-derived under the nested or truncation-respecting readings** — this ratio is stated only
   against the flat, no-truncation instrument above; a maintainer wanting the nested/ruled pair should
   re-run it rather than infer it from this figure.

   **The narrow population's cost is not re-sized against this exact reading** — no build implements
   the shape-scoped filter at `:36` yet, so the 49-of-68 figure above (re-derived directly against
   the frozen corpora, using `is_path_shaped` and the same verified-basename match key §3.4's own
   table adopts) is the direct receipt-level count this reading produces, stated here rather than
   netted against the smaller costed population it does not reach; if a maintainer wants a narrower
   or differently-keyed reading taken before ruling, that is a #530 input, not a gap in this
   paragraph.

   **Why an ordering gate and not a disclosure.** `quality-gate/SKILL.md:36` is the census's **only
   live consumer** and it reads: *"on any lint whose `TIER2-COVERAGE:` line reports `witness 0/1`,
   or a non-zero `not-reachable` or `unreached`, the orchestrator treats that receipt as
   UNVERIFIED."* C zeroes exactly those counters for the rows it resolves, and `resolved-by-walk` —
   the counter that replaces them — is a name `:36` does not read. Re-derived at the **receipt**
   level from `counterfactual.json` on `dd06b80`, which is the unit `:36` actually operates on:

   | corpus | receipts carrying a residual row today | receipts whose residual rows are **all** resolved by C (UNVERIFIED → clean) |
   |---|---|---|
   | `live29` (n=29) | 27 | **16** |
   | `corpus17` (n=17) | 5 | 0 |

   **Sixteen of `live29`'s 29 receipts (55 %) stop being flagged UNVERIFIED the day C ships**, with
   nothing consuming the replacement counter. That is a strictly fail-open transition on the one
   line this document identifies as the census's only consumer — delivered by a clause this document
   adopts, through a mitigation this document does not control. §3.4 sizes this class in **rows**
   (19 of 30, 63 %) and never in **receipts**, and receipts is the unit that matters here.
   Disclosure is not enough because the document gates two structurally identical dependencies —
   I1 on #496, I4 on the input copy — and an implementer reading §3.1 plus §4 otherwise ships the
   walk and touches `:36` *"not at all"* because §4 tells them to.

Containment (`_allowed_bases`) is **unchanged**. The walk adds no base. Per §2.5, DEC-22 does not
reach it.

**The containment union is the walk's *ceiling*, never its *scope*, and clause 2 no longer says
otherwise.** A wording that counted clause 2's hits *"across the containment union"* would be
counting them across a term this document itself defines, in §2.8 item 4, as a set of **bases**
that includes each supplied root's **git toplevel**. Implemented literally that makes the hit set
the whole repo for any root inside a checkout, i.e. **C′**, which §2.5 rejects by name as *"grudge `e0f0a6b75692` reproduced by
construction"* — and I6 and T3 both say the opposite, so the document contradicted itself on which
rule it was adopting. The divergence is not hypothetical and it bites exactly where the pin would be
written: §6 establishes that the committed fixture roots `eval/ledger-return-protocol/tier2-fixtures/p1..p3`
**do** sit inside the checkout and **do** make the repo a live probed base, where §2.5 measures
`SKILL.md` at **52 tracked / 94 worktree** hits (as dated at §2.5; 146 in the worktree today) and 49
colliding basenames — so under the
containment-union reading the first unresolved bare basename turns into an ambiguity hard-FAIL.
Production escapes only by the accident §6 names (both mandated roots have `toplevel None`), which is
precisely the accident the fixture suite does not reproduce. `_contained` continues to hold over the
containment union, unchanged; the **hit set clause 2 counts** is the supplied roots' subtrees and
nothing else. The measurement the ruling adopts was taken that way — `codegate_nested_rules.py`
rglobs `roots` only — so this wording is what makes the ruled C the same function as the measured C.

**The ambiguity check is a property of clause 2, not of the composite rule.** Clause 1 runs first, so
**a name clause 1 resolves is still a first-hit read**: a basename held both at a supplied root's top
level *and* deeper in that same root resolves silently to `root/name`, and clause 2 never runs on it.
C does not change that shape. **It is not owned by layout pin (b)**, though an earlier draft said
it was: `:54` states pin (b) as *"resolves under any two probed BASES"*, and later fixes the
quantifier as *"the top level of"* two of the four probed bases (`dispatch-root`,
`git-toplevel(dispatch-root)`, `<findings-root>`, `git-toplevel(<findings-root>)`) — a bare basename
nested several directories down inside **one** of those bases joins onto no base, so pin (b) is
silent about it. `:56`'s own *"two-homes case"* is a **different** shape — a name held by both a
root **and that same root's git toplevel**, which **is** two probed bases — not the shape here,
which stays inside one root's subtree. This shape is therefore **unowned**, and T1-neg (§5) records
it as a recorded gap rather than implying it is covered. *"Never a first-hit read"* is therefore
**not** a claim about the composite rule, and §2.5's
preference for C over first-hit-wins does not need it: the true and sufficient claim is that **C
converts the first-hit read of a name clause 1 could not resolve into an ambiguity hard-FAIL**, and
leaves the top-level-plus-nested case exactly where #486 left it. §6 applies here as it does to `:312`: `:54` is
an obligation on the orchestrator with no enforcer on this machine, so the gap is real, is **not**
rescued by the pin, and is recorded as an explicit negative pin in T1 rather than implied away.

**Where a producer's outputs are not under a supplied root, the fix is orchestrator-side.** I1 binds
a producer only once the orchestrator supplies a root that contains that producer's outputs. The
remedy for a name that cannot resolve is to **supply the root** — the #486 remedy `quality-gate`
already took, adding `<findings-root>` as a second root — and **never** to evict the name into
`TRACE`, where it is provenance and is never verified. This is a **precondition** of I1, not a
consequence of it, and it is **not satisfied today for `siege`**: `skills/siege/SKILL.md:21` records
*"Known gap: siege passes exactly one root today, so the per-agent findings files under
`scratch/<run-id>/` do not resolve and their declared sha256 is not recomputed — tracked on #496."*
Adopting I1 before #496 lands would make **every `siege` attacker-agent receipt illegal**, for an
orchestrator-side reason no producer edit can fix, and would resolve #496 in the wrong direction —
making a currently-broken-but-fixable declaration illegal instead of making it resolve. **Therefore
I1 does not bind `siege` until #496 is fixed**, and §4 carries the row and the ordering. No earlier
draft of this document named #496 at all; §4 records why the omission was mechanical rather than
accidental.

**May a receipt name a bare basename of a nested repo file? NO.** Repo files are not under any
supplied root in the shipped configuration, and the walk is bounded to supplied roots. Naming one in
`ARTIFACTS` is illegal. Neither a repo-toplevel probe (B) nor git-object resolution (A) is adopted.
A is falsified by §2.4. **B resolves exactly one name of 53** — `skills/warden/SKILL.md`, §2.3 — **and zero of 96** on the
real `codegate22` layout, i.e. **1 of 149 on the decision figure** (§2.1). The mechanism is why: `ruleB(n) = n in TRACKED and (REPO/n).is_file()` is a
repo-**toplevel** join, so it cannot reach a bare basename such as `red-team-prompt.md` (tracked at
`skills/red-team/red-team-prompt.md`) at all — **the #513 class B was proposed for is precisely the
class B cannot touch.** 1 of 53 is the measured figure, and it agrees with §2.3.

**The portability cost is not charged to B here.** `_refused_clause` (`rcpt_verify.py:1715-1736`)
refuses a world-writable git toplevel as a probed base, but its own docstring states the disposition:
*"a PATH-SHAPED name hard-FAILs under `--strict`; a bare basename stays UNVERIFIABLE at exit 0"* — so
on a WSL drvfs mount, a `chmod -R 777` devcontainer or a umask-000 container clone, B simply **fails
to help** and the names revert to the status quo. What converts "UNVERIFIABLE at exit 0" into a hard
block is **the floor**, which is #530's subject and is **not adopted by this document**. The cost is
therefore real and is recorded on #530; B is rejected here on §2.3's measured grounds (1 of 149),
which do not depend on the floor either way.

### 3.2 Tracked repo files, i.e. #513 (answers sub-question 2)

**A tracked repo file is never an `ARTIFACTS` entry.** Its legal home is a `TRACE` entry carrying its
**absolute path**, in one of two forms. **Derivation, stated because a worked example that hardcodes
one checkout's path is not a portable mandate (§4, `return-convention.md`'s worked-example rows):** a
producer derives the absolute prefix as the repo root returned by `git rev-parse --show-toplevel`, run
from anywhere inside the checkout — not a literal machine path copied from an example.

- **edited** — `EDIT` or `WROTE`, with the **post-edit** hash;
- **read only** — `READ`, with **the hash as read**. A file the receipt never edited has no
  post-edit hash, so an edited-only clause would leave the merely-`READ` declaration of §1.1 — the
  exact shape the defect was filed about — with **no legal home anywhere in this ruling**.

Both forms are provenance, both are unverified, and **both emit the `PROVENANCE-ONLY:` note of
§3.4** — that note is keyed on the **basename** of a `TRACE` name against the basenames of the
`ARTIFACTS` names **that Tier-2 resolved and hash-verified**, never on the verb and never on the
name's shape (§3.4).

**One consequence of this absolute-path mandate, stated because §3's second bullet is qualified for
exactly it.** A producer whose witness is **rangeless** and cites the `TRACE` entry holding this
absolute path gets a `--strict` **hard-FAIL**, not a resolution-unchecked pass: `witness_art_name`
falls through to `derive_art_name` for a rangeless witness on a `PASS` verdict, and `tier2_witness`
resolves and reads whatever name that returns (`rcpt_verify.py:1951`, `:1995`, `:2786`). The
compliant move is a **ranged** witness on a declared artifact, which both mandated prompts
(`red-team-prompt.md:193`, `fix-verifier-prompt.md:89`) already require — so no compliant producer
hits this today, but the shape is not hypothetical: it is the mechanism **T11 leg 3** is built on
(§4, §5), and a receipt that departs from the mandated ranged form finds it.

**Both hash obligations are NEW, and an earlier draft mis-described the first as existing
practice.** That draft justified the `EDIT`/`WROTE` clause as *"exactly as fix receipts already emit
today"*. **This document's own headline exemplar falsifies it.** `rcpt-11-qg-fix-r4.txt` carries
`4 READ …/skills/quality-gate/SKILL.md sha256:fa509a2a…` and `8 EDIT` of the same path with the
**same** hash `fa509a2a…`; likewise the `5`/`9` and `6`/`10` pairs. All three hashes are the files'
**current** contents on `dd06b80` (verified by `git show dd06b80:<path> | sha256sum`), so the `EDIT`
hashes are post-edit and the `READ` hashes assert that the pre-edit content hashed to the post-edit
value. **At least one of each pair is false**, and nothing catches it: §3 rules that `TRACE` hashes
are *"a **deliberate non-gate — decorative provenance**"* per #412/#397. So:

- The clause is stated here as a **new producer obligation**, not as a description of practice.
- **It is a convention, not a check.** Both hash forms remain unenforced provenance per #412; the
  linter will not compare them, this document does not propose that it should, and no pin asserts
  them. A producer that gets the hash wrong produces exactly the receipt above and lints clean.
- **It needs a producer-prose site to live in, and §4 now carries one.** The obligation is not
  self-executing: it must be written into the fix-agent prompt file §4 already says must be
  authored. Compare the care §3.2 takes two paragraphs down, insisting on the
  `verify-log-<chunk-id>-rN.txt` qualifier because an unqualified name *"reintroduces that shape"* —
  the same rigour is owed to a hash this ruling is asking producers to compute.

**A fix agent's `ARTIFACTS` names the verify log it wrote into the dispatch root.** This is available
**4/4** in the #501 gate today, and those files are genuinely producer-authored and pre-receipt
(`verify-log-fix-r1.txt` 10:16:32 vs `rcpt-2-qg-fix-r1.txt` 10:16:43; `WROTE` at TRACE#17).

**This is not new convention — it already exists, one file over.** (An earlier draft cited this
paragraph's three anchors as `:88`/`:89`/`:100`; re-run on `dd06b80`, they are `:89`/`:91`/`:99` —
the drift is +1, +2, −1, not a uniform offset, so each is re-verified rather than shifted by one.)
`skills/quality-gate/fix-verifier-prompt.md:89` already mandates precisely this shape for the fix
**verifier**: *"Witness a file you wrote into the dispatch root … **Name that file
`verify-log-rN.txt`** … Declare that same file in `ARTIFACTS` with its **real** sha256 and size."*
`:91` already forbids the failing shape outright — *"**Do not witness the artifact under review by
its repo-relative path.** It looks like the natural verifier witness, and it is the one shape that
cannot lint."* And `:99` already states this ruling's central split in the convention's own words:
*"placeholders are the norm for `EDIT`/`WROTE` in `TRACE` (those are provenance, deliberately not
gated), but an `ARTIFACTS` hash is a verified claim."*

So §3's ARTIFACTS-vs-TRACE split is **recovered, not invented** — it is already written down for one
role and absent for the adjacent one. **The gap is structural: `skills/quality-gate/` contains
`fix-verifier-prompt.md`, `persistence-checker-prompt.md`, `stagnation-judge-prompt.md` and
`tightened-rubric-addendum.md`, and NO fix-agent prompt file at all** (verified on `dd06b80`). The
fix agent is the only dispatched role in the gate with no prompt document, and it is the role whose
receipts #513 reports as structurally unverifiable. That is the single most economical explanation of
#513 on the table, and it makes the remedy an authoring task rather than a resolver change.

Note also that `fix-verifier-prompt.md:89` carries a **chunk-qualification** requirement
(`verify-log-<chunk-id>-rN.txt`, layout pin (a)) because `N` is a per-chunk counter while the dispatch
root is global to the run — an unqualified name is written twice into one flat root, "the later write
silently replacing the earlier and leaving the earlier receipt's declared sha256 naming bytes no file
on disk has". Any fix-agent prompt must carry the same qualifier or it reintroduces that shape.

**Stated limit, accepted deliberately:** this binds the **test output**, not the **edited bytes**.
The `.patch` files in the #501 dispatch root are **orchestrator**-authored and **postdate** their
receipts by 3–12 minutes (r1 10:16:43 → 10:26:48; r2 13:50:43 → 13:58:18; r4 16:04:57 → 16:16:33),
and `grep -n '\.patch|git diff' skills/quality-gate/SKILL.md` returns zero hits — no fix agent is
instructed to write one. A producer cannot hash a file that does not yet exist, so "the fix agent
already writes a diff" is **causally impossible** and must not be used as justification. Requiring
one would be a **new producer obligation**, not a description of practice; it is **not adopted here**
and is recorded as open question OQ-2.

### 3.3 Gitignored paths (answers sub-question 3)

Split by role:

- **The artifact under review** — the dominant gitignored class (11 of `live29`'s 14 post-C
  residual rows, 9 of its 12 on the ARTIFACTS leg, 9 of its 11 residual receipts; 82 % of
  `corpus17`'s residual) — MUST be named as the **orchestrator-supplied
  single-home copy**, i.e. `corpus17`'s shipped `artifact-N.md` shape. **`corpus17` already does
  this; `live29` regressed away from it.** Citing the original gitignored path, or its bare
  basename, is illegal.
- **Any other gitignored name** is illegal in `ARTIFACTS`. It may appear in `TRACE`.

**The remedy is NOT "copy it into the dispatch root."** `return-convention.md:104` already rules that
*"a second copy under the dispatch root is exactly the two-homes shape that hard-FAILs"*, and
`codegate22` reached `ambiguous == 0` only after deleting 5 cross-root basename collisions. One home,
supplied by the orchestrator.

**This document is an instance of its own subject.** It lives in `docs/plans/`, which is gitignored,
and the `/quality-gate` receipts that gate it will cite it. Under this ruling they must cite the
orchestrator-supplied copy, not this path.

**Which gate is being measured, stated explicitly.** Every measured statement in this
document about "a gate" is a statement about run **`2026-08-20T09-05-29`**, the six-round gate on
this document's **predecessor** (`docs/plans/2026-08-20-488-receipt-name-space-design.md`, 1929
lines). The header's directive — *"Do not read the predecessor's gate history as applying to this
artifact"* — binds the **verdict record**, not the filesystem measurements; but an earlier draft
wrote those measurements in the present tense about *"this gate"* and *"this doc"*, which attaches
the predecessor's run to this artifact in exactly the way the header forbids. They are re-tensed
here. In the predecessor's gate, **rounds 1–4 of 6 were dispatched with no `artifact-N.md` on
disk**, so no round-1-to-4 receipt of that run had a legal name for the artifact under review to
cite; rounds 5 and 6 did (I4).

**The gate that is reviewing this document, as a timestamped observation and not as a standing
property.** That run is `2026-08-21T09-09-39`. **Read the reading below as dated, because a claim
about the state of the gate currently executing a ruling is falsified by the next mandated event in
that same gate** — `quality-gate/SKILL.md:968` mandates a write into that very directory after every
round, so any present-tense sentence about it has a shelf life measured in rounds. An earlier draft
recorded *"no `artifact-1.md`"* here as a live fact, and the ordinary, mandated write that closed the
round falsified it.

**Observed `2026-08-21T23:07 −0700`** in `…/memory/quality-gate/scratch/2026-08-21T09-09-39/`:
`artifact-1.md` **exists** — 124328 B, `mtime 2026-08-21 10:04:11 −0700`, sha256
`7b7fb033f314234a901420d8aa2a917cffd661786f3b4e320557200da71da673`. There is **no
`artifact-2.md`**. The artifact under review at that moment is 123773 B, sha256
`07a4f095d7688361b45d574f625bd4434221d668f7608262a9b95c70576954e6`, and `diff` between the two
reports **104 changed lines**.

**That state is not the gap I4(a) describes, and it is the more dangerous one.** I4(a) is the
*absence* of the supplied copy; what is on disk is a copy that **was** written and is **stale**
against the artifact the current round was dispatched to review. Absence produces a `BLOCKED` or
`TRACE`-only receipt a human reads as a gap. A stale copy produces `artifacts 1/1`, exit 0, a clean
`TIER2-COVERAGE:` line and `quality-gate/SKILL.md:36` marking the receipt **verified** — a census
reporting "verified" about a review of different bytes, fail-open and silent, and produced by
*obeying* the ruling rather than by violating it. The single-home rule is what makes it silent: it
forbids the one citation form (the live repo path) that would have named the bytes actually read.
**I4 now carries a byte-identity precondition for exactly this**, and §4 carries the row that moves
the write from *after* the round to *before* the dispatch. See I4.

### 3.4 Silence is not permitted (grudge `e0f0a6b75692`)

Today an unresolvable declared name emits `UNVERIFIABLE: <name> (no file under root)` on stderr, and
`quality-gate/SKILL.md:36` converts that into UNVERIFIED. If the ruling merely moved those names out
of `ARTIFACTS`, they would emit **nothing** — a recorded advisory replaced by silence, which is the
grudge verbatim and the fail-open shape `_unresolved_disposition`'s own **comment**
(`rcpt_verify.py:1685-1687`, *"NOT SILENT … a declared entry that is neither verified nor mentioned
anywhere on stderr is the fail-open shape"*) forbids. (An earlier draft cited `:1688-1691` and called
it the docstring; that range is the `NOT-APPLICABLE` return plus the coverage-bump block, and the
docstring itself runs `:1645-1675`.)

**Therefore, and for all three `TRACE` verbs:** a `TRACE` entry of **any** verb —
`READ`, `EDIT` or `WROTE` — whose name is absent from `ARTIFACTS` MUST emit
`PROVENANCE-ONLY: <name> (declared in TRACE, not verified)`, with `<name>` rendered through
`_show_path` (`rcpt_verify.py:1577`) on the same SIEGE-R2BA-4 grounds as every other
receipt-supplied name already rendered onto the channel — required *a fortiori* here, not by
analogy, because a `TRACE` name is the **least**-constrained receipt-controlled string in the entire
grammar (§3: `TRACE` may name anything, and the §3 lexical rule and AC-2's Tier-1 raise both bind
`ARTIFACTS` only, so neither reaches this field). This keeps the #412 non-gate intact,
drops the count without dropping visibility, and is the difference between a convention fix and a
counter fix.

**The match key, stated — an earlier draft left it undefined, and the two obvious readings are both
wrong in opposite directions.** *"Absent from `ARTIFACTS`"* is evaluated on the **basename** of the
`TRACE` name against the **basenames of the `ARTIFACTS` names that Tier-2 resolved and
hash-verified**. **A `TRACE` entry whose basename matches a *verified* artifact emits nothing; a
`TRACE` entry whose basename matches an `ARTIFACTS` entry that did not resolve still emits the
note.**

Two readings were available and neither survives measurement. Measured on `dd06b80` across all three
frozen corpora (68 receipts, 416 `READ`/`EDIT`/`WROTE` entries, 258 `ARTIFACTS` names), **stated
under `codegate22`'s two layouts, per §2.1's rule that every use bearing on a rule choice carries
both** — `measure_486_corpus.py`'s pinned **flat** reconstruction, and `codegate22`'s **real
nested** frozen layout (§2.6, §2.3's decision column):

| corpus | `ARTIFACTS` names | `TRACE` R/E/W | fires, **exact-match** | fires, **verified-blind basename** | fires, **verified basename** (the rule) |
|---|---|---|---|---|---|
| `corpus17` | 47 | 80 | 50 | 46 | **59** |
| `live29` | 122 | 171 | 73 | 64 | **111** |
| `codegate22` (flat, `_codegate22_roots()`) | 89 | 165 | 131 | 131 | **137** |
| `codegate22` (real nested) | 89 | 165 | 131 | 131 | **160** |
| **total, `codegate22` flat** | 258 | **416** | **254 (61 %)** | 241 | **307 (74 %)** |
| **total, `codegate22` real nested** | 258 | **416** | **254 (61 %)** | 241 | **330 (79 %)** |

258 `ARTIFACTS` names of which **197 resolve and hash-verify under the flat layout, 119 under the
real nested one** (`codegate22`'s own verified count moves from 83 to 5 — nesting hides most of its
artifacts from the resolver's flat reconstruction, which is exactly what the resolver's real
first-hit behaviour should show and the flat layout does not).

- **Exact-match is wrong** because §3.2 mandates **different name forms by design** —
  absolute paths in `TRACE`, bare basenames in `ARTIFACTS` — so under a receipt compliant with **§3.2**
  the two never string-match, and the note fires on correctly-declared artifacts. (Under §3.3
  compliance for the artifact under review the two string-match exactly, by design — the producer
  `READ`s the same `artifact-N.md` copy it cites in `ARTIFACTS` — which exact-match handles correctly
  and is not the class this key is chosen for.) Its **13**-entry
  divergence from the basename key is exactly the §3.2 class.
- **Verified-blind basename is also wrong, and worse, because it fails silent.** Suppressing on a
  basename match to an `ARTIFACTS` entry that *did not resolve* suppresses a **true** advisory: the
  file really is declared and really is not verified. Measured, evaluating every `ARTIFACTS` entry
  with no raise-and-abandon (the reading these 66/89 figures use — see the truncation-respecting
  reading below): **66 of the 416 entries (flat `codegate22`) / 89 (real nested)** are
  suppressed by the verified-blind key while naming an unverified artifact — and they are
  concentrated in the class §3.3 calls dominant, the **artifact under review** and the
  `round-N-findings.md` 63 % class. Under the truncation rule this section goes on to adopt below,
  the same suppression is **61 flat / 79 nested** — the un-evaluated entries a raise abandons are
  correctly silent either way, and the gap between the two readings is exactly that population.
  Either reading is *"a recorded advisory replaced by silence"*, which is
  this section's own thesis sentence and grudge `e0f0a6b75692` re-entering through the clause
  written to close it.

**This document's own headline exemplar is where the two errors meet, and an earlier draft computed
both halves and never put them beside each other.** `rcpt-11-qg-fix-r4.txt` declares `SKILL.md`,
`return-convention.md`, `red-team-prompt.md`, `verify-log-fix-r4.txt` and
`verify-log-fix-r4-probes.txt` in `ARTIFACTS` while its `TRACE` carries the first three by absolute
path. Re-measured against that receipt's own two roots: **9 R/E/W entries of 11 `TRACE` entries;
9 fire under exact-match, 3 under the verified-blind basename key, 9 under the rule.** The draft
called the six-entry gap *"6 false positives on one receipt"* — but the same section's *"Honest
accounting"* records, of the same five names, that *"moving the three repo files out of `ARTIFACTS`
turns `2/5` into `2/2`"*, i.e. **3 of the 5 do not resolve**. Verified on disk: only
`verify-log-fix-r4.txt` and `verify-log-fix-r4-probes.txt` resolve and hash-match; `SKILL.md`,
`return-convention.md` and `red-team-prompt.md` do not. **All six of those "false positives" are
true positives**, once as `READ` (TRACE#4,5,6) and once as `EDIT` (TRACE#8,9,10).

**The rule needs no new I/O and does not resolution-check `TRACE`.** Whether an `ARTIFACTS` entry
resolved and hash-matched is already computed by `tier2_artifacts` (`rcpt_verify.py:1806`) by the
time the notes list it returns is assembled, so the verified set is in scope at the emission site
for free. Nothing about the **`TRACE`** name is resolved — the comparison stays lexical on the
`TRACE` side — so §3's second bullet (*`TRACE` is not resolution-checked*) is untouched. *"Compare
the file, not the string"* remains unavailable for that reason, and rejecting it was right; what an
earlier draft rejected was only that strawman, leaving the verified-set key unconsidered.

**One consequence of siting the note on the verified set, stated rather than discovered — and an
earlier draft's rule for it cannot be followed as written.** `tier2_artifacts` (`rcpt_verify.py:1806-1950`)
raises on the **first** entry that truncates the loop and abandons the rest of that receipt's
entries — read at that range, there are **five** distinct raise sites: `_unresolved_disposition`'s
`--strict` path-shaped raise, the `--strict` ambiguity raise, `_read_capped`'s over-cap raise, the
unreadable (`OSError`/`MemoryError`) raise, and the sha256 mismatch. The mismatch is the case this
paragraph illustrates, but the property below — the verified set is **partial** on a truncated run —
holds for all five, and the first is not exotic: one `live29` receipt truncates on the `--strict`
path-shaped raise today, not on a mismatch. An earlier draft's remedy borrowed `TestNotesSurviveALintError`'s
shape — *"emit the notes recorded before the raise … rather than treating an un-evaluated entry as
unverified"* — but that pin's four note classes are each decidable **per artifact, at the moment
that artifact is evaluated** (a hash mismatch, a refusal, a v1.1-not-evaluated flag — each is a
positive fact about one entry). `PROVENANCE-ONLY:` is decided by a **negative over the whole
verified set**: a `TRACE` basename is un-noted only if it matches *some* verified `ARTIFACTS`
basename, and that cannot be known until every entry has been tried. Interleaving the emission with
evaluation, as the borrowed shape does, fires the note early for any `TRACE` entry whose match would
have arrived on a *later*, un-evaluated artifact — the false positive a later successful
verification would have suppressed. **The rule instead:** on a run truncated by any raise that
abandons the rest of the entry loop — not only a hash mismatch, per the five sites above — a
`TRACE` entry whose basename matches an `ARTIFACTS` entry that was **not evaluated** emits
**nothing** — neither the note nor its absence is asserted; a `TRACE` entry whose basename matches an
entry that **was** evaluated (verified or not) before the raise still gets its note. The census's
existing `partial` flag is what records that the note set is incomplete.

**This rule is not achievable at the site §4 assigns it as written, and the fix is the mechanism the
codebase already uses one function over.** `tier2_artifacts` (`rcpt_verify.py:1806`) **returns** its
note list by value, and its sole production call site is `notes += tier2_artifacts(artifacts, trace,
root, strict, cov, bodies)` (`:3793`). When the function raises on any of its five truncating sites
— not only a hash mismatch — the `+=` never
executes, so **every** note the function accumulated — not only the ones for un-evaluated entries,
but the ones for entries evaluated and found unverified before the raise too — is discarded by the
`except LintError` handler's `notes + wit_notes` drain (`:3942`, `:3963`, `:3976`). On a truncated
run the note set at that site is **empty**, not partial: the rule above and the shipped mechanism
happen to agree on the un-evaluated half and disagree on the evaluated half, which is worse than
disagreeing on both, because it makes a pin built only against the un-evaluated case go green on a
build that drops everything. `tier2_witness` (`:2633`) was given an out-parameter (`wit_notes` /
`notes_out`) for exactly this reason — mirroring into the caller's list at every exit rather than
returning by value — and `tier2_artifacts` must gain the same idiom for `PROVENANCE-ONLY:` to survive
its own function's raise. Pinned as **T2**'s sixth leg (§5), with a fixture that discriminates both
halves: a `TRACE` entry matching an artifact **evaluated before** the raise (pin: note **is**
emitted) alongside one matching an **un-evaluated** artifact (pin: note is **not** emitted) —
`corpus17/rcpt-18` raises first on a sha256 mismatch (measured, §3.4 move 1) and is the fixture's
model for the un-evaluated half; the evaluated-and-unverified half needs a receipt with an
unverified-but-evaluated entry ahead of the raise, which is not `rcpt-18`'s own shape and must be
constructed.

**The expected volume, stated so an implementer can tell a working build from a broken one — and
stated under both `codegate22` layouts, because the layout moves it.** With the verified basename key
the note fires **307** times over the 68 frozen receipts **with `codegate22` on
`measure_486_corpus.py`'s pinned flat reconstruction**, and **330** with `codegate22` on its **real
nested** layout (§2.1's own rule: every use bearing on a rule choice carries both figures). Per
corpus: `corpus17` **59** (mean 3.5 per receipt, median 3, max 8), `live29` **111** (mean 3.8, median
3, max 9), `codegate22` **137 flat / 160 nested** (mean 6.2 flat / 7.3 nested, median 6, max 16). **A
build emitting ~254 over these corpora has the exact-match key and is mislabelling verified
artifacts; a build emitting ~241 has the verified-blind basename key and is silently dropping true
advisories (66 flat / 89 nested); ~307 (flat) or ~330 (nested) is correct, evaluated with every
`ARTIFACTS` entry tried (the no-truncation reading these three figures use) — the layout an
implementer's corpus actually sits in decides which of the two.**

**A fourth reading is the one this section's own truncation rule (below) actually rules, and it is
not 307/330.** `tier2_artifacts` raises on the first entry that truncates the loop and abandons the
rest, so on the receipts that truncate — measured live in both frozen corpora — the verified basename
key as ruled emits fewer notes than the no-truncation figure above, because an un-evaluated entry's
match now correctly emits nothing rather than firing on a `TRACE` name the loop never reached. Under
that ruled reading the same instrument returns **302 (flat) / 320 (nested)**, and the difference from
307/330 is exactly the notes the un-evaluated key suppresses. **307/330 is the number a build that
ignores this section's own truncation rule emits; 302/320 is the number a compliant build emits.** An
implementer whose build passes T2's sixth leg (the truncated-run pin, below) should expect 302/320
against these corpora, not 307/330 — the two readings are stated together, in the shape §2.1 already
uses for the two `codegate22` layouts, so neither instrument is left contradicting the other. The tell
is three-valued on purpose against the no-truncation reading — the two wrong keys sit on opposite
sides of the right one **under either layout**, so a single "is the number too high?" reading cannot
diagnose it, but "which layout was this measured under?" now can, and an implementer measuring against
the frozen corpora as they sit on disk — nested, per §2.6, §2.3, AC-4, T1 and I7 — is measuring under
the **nested** figure, not the flat one this paragraph previously gave alone; measuring under this
section's own truncation rule, the figure to compare against is 320, not 330.

**Scoping the note by *name shape* was considered and is REJECTED — it would open a sixth silence
channel.** The obvious volume cut is to fire only on `TRACE` names that are path-shaped or absolute
(the §3.2 relocation class), which under the adopted key measures **185 (flat; not re-derived under
the real nested layout, where the denominator is 330)** fires instead of 307
(re-derived on `dd06b80`; under the verified-blind basename key the same scoping measured **168**
against that key's 241, and both pairs are recorded so the comparison is like-for-like). It is
rejected because a **bare** `TRACE` basename absent
from `ARTIFACTS` would then emit **nothing**, and that shape is populated *right now*:
`live29/rcpt-22-asreturned.txt` carries `red-team-prompt.md` and `test_rcpt_verify.py` at TRACE
**#7, #8 as bare `READ` names** (verified on the frozen corpus). §3.2 rules that a tracked repo
file's `TRACE` home carries its **absolute path**, so a *compliant* rewrite of that receipt is in
scope either way — but a producer who evicts the name from `ARTIFACTS` and leaves it bare in `TRACE`
is **non-compliant with §3.2 and silent under the shape-scoped note**, which is precisely
"a recorded advisory replaced by silence" and precisely why §3.2's absolute-path mandate is
load-bearing rather than stylistic. Folding that shape into channel 4 would not rescue it: channel 4
is the **uncounted** channel, so folding it there is *"stating it as covered … the grudge in a
different costume"*. **The volume under the no-truncation instrument this paragraph's 185/307
comparison uses is therefore 307 (flat) / 330 (real nested); the compliant, truncation-respecting
figures remain 302/320 (above).** The **185 (flat; not re-derived under the real nested layout,
where the denominator is 330)** figure
is recorded here so a maintainer who disagrees can overrule this on measured ground rather than
re-deriving it.

**`READ` is in the rule because it is the verb the defect was filed about.** Scoping the note to
`EDIT`/`WROTE` — the two verbs §3.2 has a home for — would exempt the one declaration §1.1 quotes
as the filed contradiction (*"declaring a file you merely `READ` is legitimate"*). That is not a
corner case; it is populated, and the population is the `/quality-gate` **verifier** role:

- `corpus17/rcpt-18-asreturned.txt` (`quality-gate/18-verifier`) declares
  `docs/plans/2026-08-01-warden-aprime-design-review.md`, `skills/warden/SKILL.md` and
  `docs/plans/2026-07-27-warden-baroque-vs-lean-benchmark-design.md` in `ARTIFACTS` and carries them
  at TRACE **#5, #6, #7 as `READ`** (its only non-`READ` entry is `#9 WROTE round-5-ledger.md`, which
  *is* in `ARTIFACTS`). All three are path-shaped and **hard-FAIL today** under the mandated
  `--strict`. Under an `EDIT`/`WROTE`-only note they would become `TRACE READ` entries emitting
  **nothing** — a hard FAIL downgraded to silence.
- `live29/rcpt-22-asreturned.txt` (`quality-gate/22-verifier`) declares `red-team-prompt.md` and
  `test_rcpt_verify.py` — §2.2's #513 class — and carries them at TRACE **#7, #8 as `READ`**. Today:
  `not-reachable (unresolvable-basename)` → `SKILL.md:36` → UNVERIFIED. Under an `EDIT`/`WROTE`-only
  note: nothing.

**Live reproduction, in the gate on this document's predecessor (run `2026-08-20T09-05-29`).**
That run's round-1 red-team receipt — which produced *the predecessor's* round-1 findings, not this
document's — carries `1 READ docs/plans/2026-08-20-488-receipt-name-space-design.md`, a gitignored,
path-shaped name declared **only** in `TRACE`, resolution-unchecked, emitting nothing. Re-linted on `dd06b80`
under the mandated two-root `--strict` invocation, its census reads
`artifacts 1/1 witness 0/1 unreached 0 not-reachable 0 ambiguous 0 wrong-name 0 empty-range 0
discarded 1 (fail-leg-no-exit-evidence) not-applicable 0`, exit 0 — every counter clean, and the
document under review named nowhere the linter reports. That is the shape this clause closes, and it
happened inside the gate on the predecessor of this ruling — which is why it is quoted as a live
reproduction and not as evidence about the run now reading these words (§3.3).

**The silence audit covers six channels — an earlier draft's audit stopped at five, one parser
short. This document closes three outright, keeps a fourth (channel 1) visible on stderr without
closing it at the census, counts most of a fifth, and leaves one open on #530 — corrected below (F2):
an earlier draft of this sentence read "closes four," folding channel 1 into the closed set on the
strength of its own emission alone.** Grudge
`e0f0a6b75692` is "the fail-open direction is silent", so the ruling must account for every way a
name can stop being mentioned — including the one it cannot close. **Channels 5 and 6 are the
cheapest of all six, tied**; channel 4 is the cheapest of the four an earlier draft
enumerated. **"Six channels" describes the silence audit specifically — every way a name stops being
mentioned — and an earlier draft of this sentence stopped there without checking whether a *different*
kind of failure, one that is not silence at all, was still uncounted. One is: item 7 below runs the
opposite direction (a mention appearing, certified, false, rather than a mention disappearing) and is
named separately as silence-***adjacent*** rather than folded into "six," because folding it in would
overstate what the count means:**

1. **A name evicted from `ARTIFACTS` into `TRACE`** — **not closed at the unit that decides anything
   (F2 — Blind Spots F1, Fatal).** `PROVENANCE-ONLY:` fires for all three verbs (T2), so the name is
   never literally unmentioned — it reaches stderr. But §3.1 clause 2's own premise, applied to itself
   rather than left unapplied to the mechanism this document adopts: `quality-gate/SKILL.md:36` is the
   census's only reader, and `PROVENANCE-ONLY:` bumps **no census counter** — no row in §4's table
   gives it one, unlike channel 2's `resolved-by-walk`. By this document's own words (§3.1 clause 2,
   the horn-(b) discussion), a note `:36` does not read is "indistinguishable from one that was never
   emitted" **in the only unit that decides anything**. So channel 1 is an honest stderr advisory, not
   a closure: it keeps the name out of the log's silence, not out of the census's. Retracted in this
   section's closing tally below; its stderr-volume cost is priced in §4's `PROVENANCE-ONLY:` row (G2).
2. **A name that resolves below a root's top level** — whether by C's walk, or by clause 1's own
   literal join of a multi-segment name (§3.4 move 1's recommended citation form) — covered by
   `RESOLVED-BY-WALK:` and the `resolved-by-walk` sub-count of §3.1 clause 2, keyed on depth rather
   than on which clause resolved. (T7, both legs.)
3. **A name the floor's counters structurally cannot attribute to the producer, and a bucket the
   floor does not read at all** — **NOT closed by this document.** It was the pre-split §3.5's
   subject and moved to **#530**, unresolved: six gate rounds failed to state a floor that closes it,
   and the last round's Fatal was precisely this channel reappearing (a receipt whose witness never
   ran scoring zero). **This ruling closes three of six channels outright (2, 5 and 6), keeps a fourth
   (1) visible on stderr without closing it at the census (F2, above), counts most of a fifth (4); channel
   3 is open and is #530's.** Stating channel 1 as closed would be the grudge in a different costume —
   the same overclaim this sentence already refuses for channel 3, applied by an earlier draft to its
   own adopted mechanism instead.
4. **The name leaves the receipt entirely — the producer simply stops declaring it.** **Not closed
   by either note above**, because both are keyed on *presence*: `PROVENANCE-ONLY:` iterates the
   **`TRACE`** entries and fires on absence from the verified `ARTIFACTS` set, so a name in
   **neither** section is iterated by nothing, emits nothing and bumps nothing. Nothing enforces `TRACE` presence either — the mandatory-work check
   (`return-convention.md:162`) is *"for every **action** the skill's RETURN FORMAT declares
   mandatory … TRACE MUST contain the matching verb line"*, which quantifies over declared
   **actions**, never over files touched. Dropping a `READ` of a repo file is structurally
   undetectable by any counter in this ruling **for a path the orchestrator did not supply; for a path
   on the dispatch file's `Inputs:` list (§4), the orchestrator input-coverage report names it — which
   is the "most of a fifth" the tally above credits.**
5. **The whole `ARTIFACTS` set is discarded by one producer-controlled line — `(none)`.**
   **Closed by I8/T10 and by §4's `parse_artifacts` row.** In the shipped
   parser, `(none)` is a **`return`, not a `continue`**, and is not anchored to a single-line body
   (`rcpt_verify.py:240-241`). Measured directly:

   ```
   parse_artifacts(['a.md sha256:…  10','(none)','b.md sha256:…  20'])  -> {}
   parse_artifacts(['a.md sha256:…  10','b.md sha256:…  20','(none)'])  -> {}
   ```

   And end-to-end at the CLI on `dd06b80`, two receipts differing by **one appended line**, linted
   under the mandated `--strict` against a constructed root outside the checkout (one resolving
   artifact, one absent path-shaped name):

   ```
   honest        : Tier-2 --strict: path-shaped artifact docs/plans/absent-path-shaped.md
                   absent under all bases
                   TIER2-COVERAGE: artifacts 1/2 … unreached 1 … partial            EXIT=1
   + "  (none)"  : TIER2-COVERAGE: artifacts 0/0 … unreached 0 not-reachable 0
                   ambiguous 0 …                                                    EXIT=0
   ```

   **It is tied for the cheapest of the six with channel 6 below, and an earlier draft also called it
   *"the only one that defeats a hard-FAIL"*, which is false on every receipt this arc has
   measured.** Where it works,
   it works completely: one *added* line wipes **all** names at once, nullifies **I1, I2 and I3
   simultaneously**, and produces a *cleaner* census than an honest receipt. But three **shipped**
   Tier-1 rules already key on `ARTIFACTS` membership and all three raise before Tier-2 runs once the
   set is empty:

   - **#474/D6** (`rcpt_verify.py:889-894`) — a **ranged** `kind=grep` witness payload must name an
     artifact the receipt itself declares.
   - **`CLAIMS` citation** (`:923-939`) — a non-`TRACE#`, non-12-hex citation must name a declared
     artifact.
   - **`EXEC out=`** (`:897-902`) — an `out=<artifact>#<range>` must name a declared artifact.

   Measured on `dd06b80` by injecting `  (none)` into each of the **68** frozen receipts, in both
   positions (leading and trailing) and linting at Tier-1: **136 of 136 injections are rejected;
   zero survive.** (66 of the 68 lint clean at Tier-1 as-is; the other 2 already reject.) **This
   measurement injects into the `ARTIFACTS` section alone, and is silent about the multi-section
   case.** The `CLAIMS` citation guard used above is itself `(none)`-defeatable, at `parse_claims`
   (`:352-353`, §3.4 channel 6, I8) — a producer who also empties `CLAIMS` in the same receipt
   removes that guard's own input, so the 68-of-68 / 136-of-136 figures hold only once `CLAIMS` is
   intact, and are not evidence against a receipt that empties more than one section at once. On the
   **mandated** red-team receipt shape — `red-team-prompt.md:193` mandates
   `grep:<findings-file>#<range covering L1> … expect-fail=match`, and `fix-verifier-prompt.md:89`
   mandates the same ranged-grep-on-a-declared-artifact shape for the verifier — the demonstration
   is one line:

   ```
   honest        : TIER2-COVERAGE: artifacts 1/1 witness 1/1 … all counters 0     EXIT=0
   + "  (none)"  : WITNESS grep artifact not in ARTIFACTS: round-9-findings.md
                   TIER2-COVERAGE: not-reached (tier1-reject)                     EXIT=1
   ```

   **So the exposure is real but narrow, and it is prospective rather than live.** It reaches only
   receipt shapes carrying none of the three membership-bearing elements — a **rangeless** grep
   witness (`return-convention.md:104`: *"the name you write there is not read as an artifact at
   all"*), an `exec:` or `lint:` witness with no `EXEC out=` and no artifact-citing `CLAIMS`, and the
   `BLOCKED` return. **None of the 68 frozen receipts is such a shape.** The `(none)` defect in
   `parse_artifacts` is nonetheless real and I8/T10 still close it — an unanchored `return` inside a
   loop is not something to leave live because today's receipts happen to be guarded by an adjacent
   rule — but the ruling is **not** unenforceable without it, and T10's priority is that of hardening
   a prospective shape, not of rescuing the ruling.
6. **The whole `TRACE` set is discarded by one producer-controlled line — `(none)` — twenty lines
   below channel 5's parser, and an earlier draft's audit stopped one function short of it.**
   **Closed by I8/T10 (widened) and by §4's `parse_trace` row.** The identical unanchored `return`
   lives at `rcpt_verify.py:259-260`. Measured directly: `parse_trace(['1 READ … ', '2 WROTE …'])`
   returns two entries; appending `(none)` in either position returns `[]`. This channel is **wider**
   than channel 5's, not narrower: §3.2 relocates every tracked repo file into `TRACE`, and this
   ruling's own `PROVENANCE-ONLY:` note (channel 1, above) is the mechanism that iterates `TRACE` —
   so one line nullifies the note this document just adopted for channel 1 (above — a stderr
   advisory, not a census closure, per F2), in the same receipt. None of the three shipped `ARTIFACTS`-membership guards that narrow channel 5's exposure
   applies here; the guards that can catch a wiped `TRACE` are different and narrower still — a
   `WITNESS ran=TRACE#<n>` or a `CLAIMS from=TRACE#<n>` that fails to resolve, or the
   `tests-ran`/`tests-pass` mandatory-work check (`:971-978`) — and a receipt carrying none of those
   (a `red-team` receipt with a rangeless-grep witness citing its findings file, no `TRACE#`
   citation in `CLAIMS`, and no test claim) is not guarded by anything measured here. The parser-level
   defect is real and narrow in the sense channel 5's is — no frozen receipt is such a shape — but its
   guarded population is smaller, so it is named as its own channel rather than folded into 5.

   **T6's defeat by this channel is cheaper to close than I8/T10, and that alternative was not
   weighed.** T6's fixture is **constructed by this document**, and the defeat exists only because
   the constructed fixture's witness does not cite its own declared artifact. Give T6's fixture the
   **mandated** ranged-grep witness on its resolving artifact and `(none)` hard-FAILs at Tier-1
   before the `--strict` raise is reached — **no code change, no new invariant and no new pin** — and
   §2.5's own preference for pins that exercise production shape argues for it independently. I8/T10
   is still wanted, for the prospective shapes above and because the parser defect outlives any one
   fixture; it is no longer T6's only remedy, and T6 should take the cheap one regardless.

   One correction to the note analysis while it is in view: an earlier draft wrote that *"neither of
   the ruling's own notes fires"*. That is right for the **channel-4 counter** — a wiped receipt with
   a full `TRACE` satisfies an `ARTIFACTS`-or-`TRACE` presence test — and backwards for
   `PROVENANCE-ONLY:`, which under an empty `ARTIFACTS` fires on **every** `TRACE` entry, maximally.

   **Severity is not comparable to #529's, which is why this is not routed to a new issue the way
   the `size` defect was.** An unvalidated `size` degrades one field of one entry. `(none)` empties
   the set §3 calls *the vouched-and-checkable set* and on which §5 hangs I1, I2 and I3. §1.2 rests
   the entire reframing (*"the legal name space is `\S+`"*) on a line-by-line reading of these
   eleven lines that enumerates *"raises only on arity and on the hash field"* and did not notice the
   third branch — so this is not an incomplete audit of `parse_artifacts`, it is an audit that
   reached the opposite conclusion from the same eleven lines.

**Channel 4 predates the ruling; the incentive does not.** Before, an unresolvable declared name cost
the producer nothing (`UNVERIFIABLE`, exit 0) — which is precisely why the residual exists to be
measured at all. **After — but only if #530 adopts a floor.** The measured promotion cost was a
**hard block on 27/29 (93 %)** of a real plan gate, per-receipt, and it is now #530's number to
defend, not this document's. What survives the split is narrower and still real: **I1–I3 make the
declarations that produce those blocks illegal**, so the incentive to stop declaring a name exists
under this ruling on its own, floor or no floor. That is the ground the channel-4 counter is
justified on here.

**The producer facing that block has three compliant moves, not two, and only one of them is
silent.** Grading them honestly matters, because the perverse-incentive claim is the sole
justification offered for the channel-4 counter, and it is only true of the second:

1. **Re-cite the name so it resolves — non-silent, producer-side, available today with no resolver
   change at all, and NOT free — an earlier draft called it free and the measured cost is a new
   hard-FAIL class on exactly the population that gets the prefix wrong.** `_resolve_base_one` is a
   literal join of `root / name`, so a **root-relative sub-path** resolves under the shipped rule.
   Measured on `dd06b80` against `live29`'s findings root:

   ```
   resolve_base('round-9-findings.md',       <findings-root>) -> None
   resolve_base('out-9/round-9-findings.md', <findings-root>) -> …/scratch-2026-08-07T23-42-25/out-9/round-9-findings.md
   ```

   That move covers the dominant class outright: re-counted from `counterfactual.json`, **19 of
   `live29`'s 30 ARTIFACTS-leg `not-reachable` rows (63 %)** are `round-N-findings.md`, and **all
   19** sit at `out-N/` **under the supplied findings root**, so all 19 resolve under a
   root-relative citation. **The measured cost, stated rather than waved through**: `out-N/…` is
   **path-shaped**, and `_unresolved_disposition` (`rcpt_verify.py:1696-1705`) hard-raises on an
   unresolved path-shaped name under the mandated `--strict`, where the bare form degrades to
   `UNVERIFIABLE` at exit 0. Measured at the CLI on `dd06b80`, three receipts identical but for the
   `ARTIFACTS`/`WITNESS` name, one root: a bare `round-9-findings.md` is `EXIT=0` (today's 19-row
   class); the right prefix `out-9/round-9-findings.md` is `EXIT=0` with `artifacts 1/1 witness 1/1`
   (move 1 working); the wrong prefix `out-8/round-9-findings.md` is `EXIT=1`,
   `Tier-2 --strict: path-shaped artifact … absent under all bases`. **Which directory is
   `<findings-root>` is decided by the orchestrator, not the producer** — `return-convention.md:104`
   says so in the producer's own second person, and the dispatch loop supplies it — so a producer
   computing the prefix wrong is exactly the population whose model of the root was already wrong,
   the population that produced the 19-row class to begin with. Move 1 therefore hands that
   population a citation shape whose failure mode is a structural `BLOCKED` rather than a note. The
   result is *more* informative than the bare basename **when the prefix is right**, and the
   citation records where the file was written; when it is wrong, it is worse than the bare form it
   replaces. The pre-split floor's own table graded this remedy **producer-attributable** —
   `unresolvable-basename`'s producer edit is *"name a file that resolves under a supplied root"* —
   so any floor #530 adopts that claims no honest move exists would contradict its own grading; that
   grading does not depend on the move being free, and it still holds. **The remedy for the new
   cost is orchestrator-side, not a reason to withdraw move 1**: the dispatch that hands a producer
   `[FINDINGS_OUTPUT_PATH]` MUST also state, in the same header, **which directory is
   `<findings-root>`** — the same `Inputs:` schema field §4 already schedules for the channel-4
   counter (one field, not a new mechanism) — so a producer computing the prefix has the information
   the computation needs. Recorded here because the observation is about the *remedy*, which is
   this document's, and is carried to #530 as a constraint on the floor.
2. **Restructure the artifact's home, or have the orchestrator supply a root that contains it —
   expensive and orchestrator-dependent.** This is the honest scope of the perverse-incentive
   argument: a producer whose outputs are under **no** supplied root, for which §3.1's remedy is
   *"supply the root"* and `siege`/#496 is the worked instance. Move 1 is unavailable there,
   because there is no root to be relative to.
3. **Delete the line — free and silent.**

**The incentive argument therefore holds against move 2's population and not against move 1's, and
the channel-4 counter is justified on that narrower ground.** §6 establishes there is no enforcer
on any of the three — *"Every rule in this ruling is enforced solely by an LLM reading Markdown and
choosing to obey it."* Where move 1 is unavailable, converting a free honest declaration into an
expensive one, and a silent omission into the cheap path, is grudge `e0f0a6b75692` arriving through
the door **this ruling opens** — the same argument §3.4 makes, correctly and at length, about the
`EDIT`/`WROTE`-only scoping of the `PROVENANCE-ONLY:` note.

**The tension in move 1, and why it is now covered rather than merely disclosed.**
`quality-gate/SKILL.md:312` and `:951` pin the round's findings file to the **top level** of
`<findings-root>`, so a producer citing `out-N/round-N-findings.md` is complying with I1 while
**declaring a violation of the location pin** in the name itself. That is a real cost and it does not
cancel move 1. **An earlier draft compared this only to line-deletion and to a silent walk, and won
both comparisons while losing the one that matters**: against *today's* behaviour for these same 19
rows — `not-reachable (unresolvable-basename)` → `:36` → UNVERIFIED — a citation nothing parses is
no more visible than a compliant one, because §6 establishes there is no human reader of `ARTIFACTS`
names, only `:36` reading counters. §3.1 clause 1 now closes that gap directly: `out-N/…`'s
literal-join resolution is a **below-top-level** resolution by clause 1, so it MUST emit
`RESOLVED-BY-WALK:` and bump `resolved-by-walk` on exactly the same terms clause 2's walk hits do
(§3.1). Move 1 is therefore **covered by the same counter** channel 2 invents for the walk, not
merely disclosed as a tradeoff beside it. It also means the migration cost (measured on the
pre-split §1.3, now #530) is, for 63 % of `live29`'s dominant class, a set of one-line citation
edits — which the cost story should say and an earlier draft did not.

**A channel that cannot be closed can still be counted — but only against a set that exists on disk,
and today none does.** The counter requires that **every path the orchestrator handed the
producer appears somewhere in that producer's receipt** — `ARTIFACTS` or `TRACE`, either is
compliant — reporting by name the ones that do not. Its whole justification is that *"that set is one
the producer does not control, which is what makes this a **counter** rather than a **request**"*.

**That set is not machine-readable anywhere, and that half stands on the mechanism alone.**
`skills/shared/dispatch-convention.md:53-55` defines the dispatch-file header as `Pipeline` /
`Phase` / `Task` / `Timestamp` / `Dispatch-Dir`, and then `---`, after which the body is free prose.
There is **no `Inputs:` field and no marked-up input list** — verified by reading the schema, which
is a claim about a committed file and does not depend on any one dispatch surviving — so an
orchestrator implementing the counter as written must scrape paths out of Markdown.

**Re-derived against a dispatch file that still exists.** An earlier draft measured this on
`/tmp/crucible-dispatch-1787328579/1-devils-advocate.md`, reporting 11 path-shaped tokens over 9
distinct files and a **78 %** false-positive rate. **That file has since been deleted and the figure
is no longer reproducible**, so it is recorded as a one-time reading and nothing rests on it. The
same measurement over a red-team dispatch that does survive — the predecessor gate's round-1
dispatch, `…/scratch/2026-08-20T09-05-29/dispatch-archive/5-qg-red-team-r1.md` (6685 B) — gives
**12 path-shaped tokens naming 5 distinct files**: the artifact under review, `red-team-prompt.md`,
`return-convention.md`, `scripts/measure_486_corpus.py` and `memory/pipeline-status.md`, plus 7
further tokens that are directories and name no file at all. The **mandated** red-team receipt shape
(`red-team-prompt.md:184`, `:185`) obliges the producer to name exactly **one** of the five — the
artifact under review, at `READ` — so a body-scraping counter reports **4 of 5 by name**, an **80 %**
false-positive rate on a fully compliant receipt. (An earlier draft cited `:190`, mid-`CLAIMS`; the
`TRACE`/`READ` shape is at `:185`.)

**And the exact rate is unspecified by the rule, which is the finding rather than a caveat.** The
two readings above differ in how a "path token" is tokenised, whether the two citation forms of one
file are deduplicated, and whether a file the dispatch hands over as a *rubric* counts as an input.
**No figure is more correct than another, because the rule as written does not say.** Whichever is
taken, resolving the false positives means the orchestrator exercising judgement about which paths
were "handed over" — which is precisely the producer-independence the sentence claims to have
bought. That makes it a request again, and it is the **mechanism**, not any one percentage, that
carries the conclusion.

**So the counter is adopted, and it is gated on the field it quantifies over.** §4 now carries a
`shared/dispatch-convention.md` row: a structured **`Inputs:`** list in the dispatch-file header
enumerating exactly the paths the producer is handed. **The counter quantifies over that list and
over nothing else** — not over path tokens appearing anywhere in the dispatch body — and **MUST NOT
be implemented before the field exists**, because before it exists the rule has no denominator and
its producer-independence claim is false. Two further limits, stated rather than implied:

- **It covers orchestrator-supplied inputs only.** A file the producer discovered itself and then
  chose not to mention is out of reach of every mechanism in this ruling. That is the residual of
  channel 4, and it is named here rather than left unstated.
- **It carries no pin and no enforcer.** It is orchestrator prose, like `:312` and `:54` and
  everything else §6 enumerates, and §4 carries the surface. It is not claimed as verification.
  Note the disanalogy an earlier draft glossed: `:312` and `:54` describe an artifact placement an
  orchestrator can check with a `stat`, whereas this rule quantifies over a set that does not exist
  in any file — which is why it needs a schema change and they do not.

Consequently, **evicting a name from `ARTIFACTS` without adding a `TRACE` entry is a stated receipt
defect**, not merely an unnamed possibility — which is the difference between an audit that names its
own gap and one that does not reach it.

**Why channel 2 needs its own note — C's second silence.** The dominant residual class (19 of
`live29`'s 30 ARTIFACTS-leg `not-reachable`, **63 %**) is `round-N-findings.md` written **one
directory below** the probed top level, and `quality-gate/SKILL.md:312`/`:951` pin that file to the
**top level** of `<findings-root>`. So those 19 rows are the measured population of a **location-pin
violation**, and today the violation is mechanically visible: the name does not resolve, the census
bumps `not-reachable`, and `SKILL.md:36` — which names this purpose in as many words, "the
replacement signal for the crashed / **wrong-path** case", for "a subagent that crashed, timed out,
**or wrote to the wrong path**" — converts it to UNVERIFIED. C makes all 19 resolve. Without a note,
a findings file written to the wrong place would resolve **silently**, hash-match, and leave a clean
census — and §6 establishes there is no other backstop on this machine: no Crucible hook is
registered, `measure_486_corpus.py` is not in `run_tests.sh`, and every rule here is enforced solely
by an LLM reading Markdown and choosing to obey it.

The counter-argument — that `:312` owns layout and the linter owns resolution, and conflating them is
what made the resolver the de-facto name-space spec (§1.2) — is the right separation *in principle*
and fails *here*, because §6 shows `:312` has no enforcer: the census **was** its enforcer, by
accident. The 19 hash-MATCHes (§2.5) prove the bytes were right in this corpus; they do not make the
class safe, because the failure `:36` exists to catch — a subagent writing where nobody expected — is
exactly the case where the bytes hash-match their own declaration and the **location** is the only
thing wrong. `RESOLVED-BY-WALK:` costs one note and keeps `:312` falsifiable after C. Adopting C
without it would trade #486's location pin for a green counter, which is the grudge again.

**What that note does not buy, stated rather than netted out.** Those rows carry
`not-reachable (unresolvable-basename)` today — a code the pre-split floor summed. After C they
resolve and bump `resolved-by-walk` instead, so **whether they still block is now #530's open
question (OQ-7), not a property of this ruling**. What this document guarantees is only the note and
the sub-count; §6 says there is no enforcer for either. The class is 63 % of `live29`'s ARTIFACTS-leg `not-reachable`
population at the instrument (19 of 30, §2.2), and the largest single class in the linter's own
bullets too: measured this round under the mandated two-root `--strict` invocation, `live29`'s
ARTIFACTS leg emits **10** `round-N-findings.md` `UNVERIFIABLE` bullets against **8** for the
artifact under review and **1** for `fix5-rerun.log`. Moving that class from a blocking counter to a
reported one is a **consequence of C that this document does not itself resolve**. Both horns moved
to #530 as OQ-7: summing the counter puts every one of those rows straight back to blocking and makes
adopting C buy nothing; not summing it means the class is reported and not blocked. **C is adopted
here on §2.3's measured grounds; the blocking question is #530's.**

**Two comparisons this document never runs, named rather than silently decided (A1, A2 — Technical
Soundness F1/F2).** First: C's only measured benefit at `:36` — the census's only live consumer — is
decided entirely by #530's still-open OQ-7 (above), so the trade-off actually facing a maintainer is
not "adopt C" in isolation but "adopt C now, at the costs §4 enumerates (new hard-FAIL classes for
`build`/`siege`/`quality-gate`, four new pins, the lexical clauses' pin re-authoring), against 'defer
C's resolver change to #530, the ticket that already owns OQ-7'" — and this document does not run that
comparison; §2.3's candidate table compares A/B/C/D against each other, never against deferral. Second:
C's entire measured `live29` benefit (§2.3: 42 → 14) is, by this document's own arithmetic, the
identical population §3.4 move 1 already resolves producer-side — 19 of `live29`'s 30 ARTIFACTS-leg
`not-reachable` rows (63 %), all under `out-N/` (§2.2, §3.4) — with no resolver change, no new
hard-FAIL class, and none of C's pins. Move 1 does not reach C's remaining residual (legacy or
non-compliant receipts §6 notes no producer rule enforces), so the two are not identical in coverage —
but the overlap on the population that decides `live29`'s headline figure is total, and no table in
this document runs move-1-alone as a candidate beside C. Both comparisons are left to the maintainer;
this document decides neither.

**The cost of that trade, sized in the unit `:36` reads.** Everything above
sizes this class in **rows** — 19 of 30, 63 %. `quality-gate/SKILL.md:36` does not read rows; it
reads a receipt's census line and treats the whole receipt as UNVERIFIED. Re-derived at the receipt
level from `counterfactual.json` on `dd06b80`: of `live29`'s **27** receipts carrying a residual row
today, **16 have every such row resolved by C** — so 16 of the corpus's 29 receipts (**55 %**) flip
from UNVERIFIED to clean the day C ships (`corpus17`: 0 of 5). **That is why §3.1 clause 2 now carries
a binding ordering gate rather than this disclosure alone.** Naming a consequence and routing it to
the ticket that owns it is what a split is for; leaving it *unordered* while gating two structurally
identical dependencies (I1 on #496, I4 on the input copy) was an asymmetry this document corrects.

**Honest accounting of what the ruling buys.** On `rcpt-11-qg-fix-r4.txt`, moving the three repo
files out of `ARTIFACTS` turns `2/5` into `2/2` — **the same two files are checked before and
after.** The convention half of this ruling is a **producer-hygiene metric**: it measures whether a
producer named things that resolve. It is **not** "receipts became checkable". The part that
genuinely converts silent unverifiables into real verifications is **C** (19 on `live29`), and it is
the resolver half. The doc states this rather than letting a green counter imply otherwise.

**Sized in the unit `:36` reads, because "checked before and after" is a per-artifact statement and
`:36` operates on the whole receipt.** Re-derived at the receipt level (§3.1 clause 2): of
`live29`'s 27 receipts carrying a residual row today, **9 (33 %)** flip from UNVERIFIED to clean
under I3/§3.3 compliance alone, with no C involved, and **zero** by §3.2's tracked-repo class alone
— of the same order as the **16 of 29 (55 %)** C flips. `corpus17`: **5 of 5 (100 %)** — 4 by §3.3
alone, 1 (`rcpt-18`) needing both invariants, since it mixes a tracked repo file with
artifact-under-review names (§3.1 clause 2 states the correction and the raise-and-abandon caveat
this figure shares with `live29`'s). **Every one of the 9 (and the 4 of the 5) is a case where the
underlying file becomes verified** — §3.3's compliant move is a re-citation to the orchestrator-
supplied `artifact-N.md` copy, which resolves and hash-verifies (§3.1 clause 2); the
producer-hygiene metric above is a separate statement and does not speak to whether the cited file
is verified. What is new here is only that the *receipt* also reads as clean at `:36`'s only live
consumer, on the same population — that receipt-level cleanliness now tracks a real verification
rather than masking its absence, which is why this class is not gated (§3.1 clause 2).

7. **Silence-adjacent, not silence — a name is not un-mentioned, it is actively certified as
   verified while violating I2 or I3.** Every one of the six channels above is a way a name stops
   being mentioned. This is the inverse: a mention that appears, resolves, hash-verifies, and reads
   as **more** trustworthy than an honest receipt, while the invariant it names as unconditional
   ("never," §3.2, §3.3) is violated. **Not closed by this document.** A tracked repo file, or a
   gitignored path-shaped name, cited by **repo-relative path** — lexically legal under this
   document's own grammar — against a root whose **git-toplevel** base contains it, resolves via
   clause 1's literal join through `_allowed_bases`'s git-toplevel probe (§2.8 item 4, "shipped
   behaviour... live, not hypothetical"), hash-verifies, and reports `artifacts N/N`, exit 0.
   Reproduced directly on `dd06b80`:

   ```
   resolve_base('scripts/rcpt_verify.py', 'eval/ledger-return-protocol/tier2-fixtures/p1')
     -> /mnt/coding/Coding/crucible/scripts/rcpt_verify.py
   resolve_base('skills/red-team/SKILL.md', 'eval/ledger-return-protocol/tier2-fixtures/p1')
     -> /mnt/coding/Coding/crucible/skills/red-team/SKILL.md
   ```

   Neither is `None`; both are tracked repo files cited by repo-relative path, and I2 says an
   `ARTIFACTS` entry naming either is never legal. **Carried to the full CLI, not left at the
   `resolve_base` layer — a constructed receipt declaring `scripts/rcpt_verify.py` in `ARTIFACTS`
   with its real hash, linted at Tier-2 under `--strict` against the same in-checkout root:**

   ```
   $ python3 scripts/rcpt_verify.py --tier2 --root eval/ledger-return-protocol/tier2-fixtures/p1 \
       --strict receipt.txt
   TIER2-COVERAGE: artifacts 1/1 witness 1/1 unreached 0 not-reachable 0 ambiguous 0 wrong-name 0
                   empty-range 0 discarded 0 not-applicable 0                       EXIT=0
   ```

   `artifacts 1/1` — the tracked repo file resolved and hash-verified, every counter clean, exit 0.
   The identical construction with `docs/plans/2026-02-23-iterative-red-team-design.md` (gitignored,
   path-shaped, not the artifact under review) in place of the tracked file reproduces the same
   `artifacts 1/1 … EXIT=0`, for I3. `tier2_artifacts` (`rcpt_verify.py:1806`)
   contains **zero** tracked-ness or gitignore-status checks over its full 145-line body — verified
   directly: `sed -n '1806,1948p' scripts/rcpt_verify.py | grep -c 'git\|tracked\|gitignor\|ls-files\|check-ignore'`
   returns `0`. It resolves, checks ambiguity, reads, and hash-compares — nothing else. No row in
   this section's own table adds such a check anywhere. This compounds with channel 1's
   `PROVENANCE-ONLY:` note (T2 leg 4): given the 52 tracked `SKILL.md` files this repo holds, a
   producer's legitimate `TRACE READ` of one `SKILL.md` can have its note wrongly suppressed by an
   I2-violating `ARTIFACTS` entry that happens to resolve to a **different** `SKILL.md` of the same
   basename — an incorrect match silencing a correct note, on the same basename-only key channel 1
   adopted for other reasons.

   **The specified remedy, not yet built.** At the resolved branch of `tier2_artifacts`, when a
   resolved artifact's realpath falls under a root's git-toplevel base rather than under the root's
   own supplied subtree — the shape §2.8 item 4 measures as shipped — check whether that realpath,
   relative to the toplevel, is tracked (`git -C <toplevel> ls-files --error-unmatch -- <relpath>`)
   for I2, or git-ignored (`git -C <toplevel> check-ignore -- <relpath>`) for I3; a match is a
   Tier-2 hard-FAIL under `--strict`, naming the violated invariant, mirroring how an absent
   path-shaped name already hard-FAILs at `_unresolved_disposition` (`:1696-1705`). **The identical
   check runs at `tier2_witness`'s own resolved branch, on the same terms** — that function reaches
   the same git-toplevel-probed resolution independently, and a rangeless `kind=grep` witness needs
   no `ARTIFACTS` declaration to reach it at all (§4, §5 give the full mechanics and exit-code
   contract). Gated the same way that mechanism is, deliberately, not as a new unconditional class:
   I7 enumerates only the hard-FAIL classes C's walk creates, and this check is not part of C's
   walk — the git-toplevel probe it inspects is a pre-existing, separate mechanism — so it is named
   and costed at its own site (here, and T11 below) rather than folded into I7, the same treatment
   §3.4 move 1 and the lexical `not absolute` clause already get. Pinned as **T11** (§4, §5). Whether
   it lands ahead of, or gated alongside, #530's floor is **OQ-9**, not decided here. Until it lands,
   I2 and I3 are unconditional statements of what a legal receipt looks like with a demonstrated,
   unclosed gap between that statement and what the linter checks — a gap this document previously
   stated without drawing the enforcement conclusion (§2.8 item 3) and now draws.

### 3.5 The floor must read the buckets it currently cannot see

> **Moved to #530.** §3.5 (including §3.5-F) was split out of this document on 2026-08-21 and now lives on GH #530 (Tier-2 census floor). It is **not** reduced-scope here — it is a separate open ticket. Section numbers in this document are deliberately unchanged from the pre-split 1929-line original so the two remain comparable.

### 3.6 Criterion 4 — pre-registered, prospective

> **Moved to #530.** §3.6 was split out of this document on 2026-08-21 and now lives on GH #530 (Tier-2 census floor). It is **not** reduced-scope here — it is a separate open ticket. Section numbers in this document are deliberately unchanged from the pre-split 1929-line original so the two remain comparable.

## 4. API surface

**Corrected, on the identical grounds the header states one section earlier (F1 — Scope Clarity F1):**
an earlier draft of this line read *"No runtime API changes in this arc,"* which is the header's own
retracted *"No code changes in this arc"* wearing a narrower noun — and it sat directly above rows
mandating new Tier-1 raises (`parse_artifacts`, `parse_trace`, `parse_claims`) and the
`tier2_artifacts`/`tier2_witness` checks T11 specifies, each a behavioural contract change to the
shipped linter. **AC-2, AC-6's T2, T6 and T7 leg 2 are implementation obligations
of this ticket and are in scope for its implementing change**, on the same terms the header states for
the population as a whole. The surfaces this table commits to *future* work are the **semantic**,
#530/`:36`-gated and I4-gated clauses (§3.1's resolution rule, §3.2, §3.3) and the producer-prose
rollout rows — not the lexical Tier-1 raises or the I8/T10 code, which land in this ticket's own
implementing change. **T11's code is not in that set: whether it lands ahead of #530's floor is OQ-9,
undecided here (§8, §9); this table and §5 specify it below so the decision has something to range
over, and neither schedules it.**

| surface | file:line | change |
|---|---|---|
| `ARTIFACTS` name grammar | `skills/shared/return-convention.md:68` | `<name>` constrained normatively for the first time — **split, the same way `:104`/`:256` are gated below.** The **lexical** half (no leading `/`, no NUL; `..` producer-normative only, §3, *Lexical grammar*) is **ungated** — it is checkable by inspection the moment this document is read, the same terms AC-1's first half already uses for "the ruling in §3 is recorded." The **semantic** half (§3.1/§3.2/§3.3's resolution, tracked-file and gitignored rules) lands at the same `:68` paragraph cluster but is the vector §3.1 clause 2's second ordering gate is about — the convention is already the live document its six adopting skills (§3.1 clause 2) consume, with no staging path separating "edited" from "live" — so the semantic clauses at `:68` MUST NOT ship until #530 rules OQ-7 or `:36` is amended in the same change, on the identical terms as `:104`/`:256` — **and its §3.1 resolution clause (I1) MUST NOT ship until #496 lands either** (§5, I1's precondition), because `:68` is where I1 becomes a producer instruction and `siege/SKILL.md` is one of the six adopting skills; landing `:68`'s semantic half on the #530/`:36` gate alone, with #496 unlanded, makes every `siege` attacker-agent receipt illegal the moment it lands, and the `siege` carve-out (§5, I1: *"I1 does not bind `siege` until #496 is fixed"*) is not itself stated in `:68`'s edited text, so a producer reading only the shipped convention has no way to see it — either land `:68`'s I1 clause after #496, or carry the carve-out into the convention text itself in the same change. **And its §3.3 clause (I4) MUST NOT ship until §4's `:758-760`/`:968` row has landed** (§5, I4, the third ordering gate) — the same terms `:184`/`:297`/`:329` carry below, and `:68` — together with `return-convention.md`'s own `12-judge` worked example, below — is the wider of the two files that roll I4 out to producers, because `return-convention.md` reaches every one of the six adopting skills, not only the red-team dispatch body; either land `:68`'s I3/§3.3 clause after that row, or carry the third gate's precondition into the convention text itself in the same change, on the identical terms as the `siege` carve-out above. An implementer editing `:68` for the lexical grammar alone, ahead of either gate, is compliant; instructing the tracked-repo-file, gitignored-path or single-home-citation rules through it is not. **Constraint on both "carry the carve-out/precondition into the convention text itself" alternatives, added this round: any such inline carve-out shipped into a committed skill file MUST cite an observable repo fact (e.g. a named section of a shipped skill file) or a GitHub issue number as its authority — never a `docs/plans/` path, which is gitignored (`.gitignore:7`) and unreadable by the convention file's actual audience, the six adopting skills and their producers. Round 2's attempt to ship the I4 precondition as an inline note citing this very document by its `docs/plans/` path is the demonstrated failure case (see the `12-judge` worked-example row, §4, and its FATAL-1 revert) |
| the contradiction paragraph | `skills/shared/return-convention.md:104` | retract the unqualified "not only the set it created" blessing — **gated**: this edit is the second ordering gate's larger rollout vector (§3.1 clause 2), read by its six adopting skills the moment it lands, and MUST NOT be made until #530 rules OQ-7 or `:36` is amended in the same change |
| Scope restatement | `skills/shared/return-convention.md:256` | move with `:104` — it is the other half of the contradiction, gated on the identical terms |
| `parse_artifacts` | `scripts/rcpt_verify.py:232-249` | **three items, and the third is the largest.** (i) validate `parts[0]` against the **enforced part** of the lexical grammar stated in §3 — no leading `/`, no NUL; the `..` clause is producer-normative and deliberately does **not** land here (§3, *Lexical grammar*). That is the only half of the ruling this function can evaluate, since it sees the receipt text and nothing else — and it is **not** AC-2's whole scope: AC-2 also obliges the two `scripts/test_rcpt_verify.py` pins this raise makes unreachable to be re-authored in the same change. (ii) Verified: the body returns `{"hash", "size"}` only, while the docstring at `:233` claims `{name: {hash, size, meta}}` — the `meta` key does not exist, so every trailing `key=value` is silently discarded and `size` is stored as a string and never compared. The unvalidated `size` is now filed separately as **#529** — a receipt may declare any size and lint clean, in the section §3 calls *vouched and checkable*. (iii) **`(none)` is a `return`, not a `continue`, and is not anchored to a single-line body** (`:240-241`, `if line == "(none)": return {}`) — see **I8 / T10** and §3.4 channel 5. Fix: `(none)` is legal **only** as the sole non-blank line of the `ARTIFACTS` body; a `(none)` co-occurring with any entry is a Tier-1 `LintError`. One line of code. **An earlier draft of this row claimed *"the ruling cannot be enforced without it"*; that is retracted.** Three shipped Tier-1 rules already key on `ARTIFACTS` membership — #474/D6 (`:889-894`), the `CLAIMS` citation rule (`:923-939`) and `EXEC out=` (`:897-902`) — and measured on `dd06b80` they reject an injected `(none)` on **68 of 68** frozen receipts in **both** orderings. The item is worth landing for the shapes those rules do not reach (rangeless-grep witness, `exec:`/`lint:` witness with no citing `CLAIMS`, `BLOCKED`), none of which any measured receipt is; it is hardening, not the ruling's load-bearing member (§3.4 channel 5) |
| `parse_trace` | `scripts/rcpt_verify.py:252-277` (`(none)` sentinel at `:259-260`) | **the identical defect one function down, closed the same way.** `if line == "(none)": return []` is the verbatim `parse_artifacts` bug at a different parser: an unanchored `return` inside the loop, not a `continue`, with no single-line-body anchor. Fix: `(none)` is legal **only** as the sole non-blank line of the `TRACE` body; a `(none)` co-occurring with any entry is a Tier-1 `LintError` — see **I8 / T10** (widened) and §3.4 channel 6. One line of code, same shape as the `ARTIFACTS` fix above. Unlike `parse_artifacts`, no shipped Tier-1 rule keys on `TRACE` membership generally — `ran=TRACE#<n>` and `CLAIMS from=TRACE#<n>` only fire when a receipt cites one, and the `tests-ran`/`tests-pass` mandatory-work check (`:971-978`) only fires when a receipt makes that claim — so this channel's exposure is wider than `ARTIFACTS`'s, not narrower |
| **committed receipt fixtures — the population §4's blast-radius scan never reached** | `eval/ledger-return-protocol/**` | **new.** `grep -rl ARTIFACTS` **outside** `skills/` returns the repo's largest receipt population: the `sample-corpus`, `v11-corpus`, `inject`, `v11-inject`, `tripwire` and `tier2-fixtures` `*.jsonl` corpora, plus `scripts/check_rt_receipt_contract.py` and the three `measure_*.py` scripts. Parsed with the shipped `parse_artifacts` on `dd06b80`: **104 `ARTIFACTS` names**, of which **47 are bare basenames of tracked repo files** (I2-shaped: `round-{3,4,11,12,13}-findings.md`, `test-output.log`, `witness-grep.log`, `dup.log`, `same.log`, `solo.log`, `tampered.log`) and **3 are path-shaped** (`lib/foo.ts`, `build/gone.out`, `d1/second-root.log`, I1/I3 exposure). They are **CI-gated**: `scripts/run_tests.sh:102-106` runs `rcpt_verify.py --selftest`, `test_rcpt_verify.py`, `measure_474_denominators.py`, `test_measure_474.py` and `test_measure_486.py`, and `test_measure_486.py:438` pins `tier2-fixtures/manifest.jsonl` directly. **Recommended, and NOT decided here: I1–I3 do not bind fixtures** — fixtures are linter *inputs*, not producer *returns*, and several are deliberately malformed. That is **OQ-8**, a maintainer decision. What *is* ruled here regardless of OQ-8: **AC-2 lands only the lexical half in `parse_artifacts`** (§3, *Lexical grammar*), which all 104 fixture names already satisfy, so no tracked-ness or path-shape check reaches **this** population and it stays green either way. **That is a statement about `eval/**` and not about `run_tests.sh`**, and an earlier draft of this row made it about the suite: `scripts/test_rcpt_verify.py` is a second gated population that the lexical half **does** reach — see the row below |
| **the CI suite that constructs the banned shapes on purpose — the population §4's blast-radius scan also never reached** | `scripts/test_rcpt_verify.py:5946`, `:5521`, `:4306`, `:3669`; gated at `scripts/run_tests.sh:103` | **new.** The lexical census stopped at `eval/`; `scripts/` is one directory further over and holds receipts declaring the one shape family the rule bans. Dynamic census on `dd06b80` (§3, *Lexical grammar*): **164 `ARTIFACTS` name occurrences, 31 distinct, 4 illegal**. A build carrying only the lexical clause turns **three** committed pins red, and they are structurally unreachable rather than merely failing, because the Tier-1 raise fires before the Tier-2 branch each one asserts on. Two consequences are scheduled here: (i) the **`..`** clause is **not landed** at Tier-1 (producer-normative only) because `_contained` (`:1405`) already carries the traversal guarantee by realpath and banning it retires the **siege S-3** monotonicity pin — a faithful substitute for that fixture does exist (a `..`-free, path-shaped symlink-escape name, §3), but S-3 is a security regression pin and this ruling declines to re-author a security fixture for a grammar-only benefit; (ii) the **absolute** and **NUL** clauses land, and `TestARefusedProbeBaseIsDiagnosable.test_an_absolute_cited_name_is_diagnosed_too` (`:5513-5529`) and the NUL leg of `TestHostileReceiptNamesAreEscapedToo` (`:4305-4310`) MUST be re-authored **in the same change** — the NUL one onto the Tier-1 message, which must render the name through `_show_path` so the escaping guarantee survives the move. `ou\x00t.log` (`:3669`) is illegal too but its test asserts only the absence of a traceback, so it stays green; it is listed so the count is the census's and not the failure list's. **I7 is unaffected**: its terms are *"any further new hard-FAIL class reaching an **orchestrator**"*, and this class reaches the CI suite. **A third consequence, priced rather than left to the `..` clause's stated cost alone (§3):** landing `not absolute` turns a producer's paste of §3.2's mandated absolute `TRACE` form into `ARTIFACTS` — where today it resolves and hash-verifies — into a **Tier-1 hard-FAIL** on the producer's own receipt, at ordinary lint time, not only in this CI suite; that is the class §5's I7 entry now names beside move 1's, on the same precedent |
| **missing** fix-agent prompt | `skills/quality-gate/` | no fix-agent prompt file exists; authoring it is where the #513 ruling lands. **It must carry three things, not one:** (i) the `verify-log-<chunk-id>-rN.txt` naming + `ARTIFACTS` declaration shape `fix-verifier-prompt.md:89` already mandates for the verifier; (ii) §3.2's **two new hash obligations** — post-edit hash on `EDIT`/`WROTE`, as-read hash on `READ` — stated as new obligations, since the exemplar `rcpt-11-qg-fix-r4.txt` shows current practice does **not** distinguish them; (iii) a note that both are unenforced provenance per #412, so a producer knows the rule is a convention and not a check. **Authoring this file is not the same milestone as making the fix agent read it, and both are required.** The file's **existence** is separable from its **rollout**: `quality-gate/SKILL.md:490`ff (*Fix Mechanism*) dispatches `crucible-qg-fix` from the *Scope Anchoring for Fix Agents* list (`:525`ff — scope statement, change boundary, drift detection), which names no prompt file, unlike the verifier's own input list at `:580` (*"4. The full content of `fix-verifier-prompt.md` as the agent's instructions"*). **Rollout is therefore that missing dispatch-input line — add *"The full content of `<fix-agent-prompt>.md` as the agent's instructions"* to the Scope-Anchoring list, mirroring `:580`'s clause for the verifier — not the file's existence.** The file may be authored and merged on its own; the dispatch-input line is the rollout act, and it — not this row's file-authoring work — is what §3.1 clause 2's extended ordering gate binds (see §8, which records that authoring and wiring are two separate, sequenced milestones and that no acceptance criterion below covers either) |
| **`red-team`'s producer prose — the gate's most numerous producer role, and C contradicts it** | `skills/red-team/red-team-prompt.md:222`, `:184`, `:297`, `:329` | **new.** §4's blast-radius arithmetic finds this file (it is one of the four the `grep -rl ARTIFACTS skills/` output quotes) and an earlier draft gave it no row. **Five edits, not four — the fourth in the list below was missing entirely.** **`:222`** restates the contradicted rule in the producer's own second person — *"resolution is a literal join with **no search**, so the bare basename you cite is probed only at that root's top level"* — while §3.4 move 1 asks that same producer to cite `out-N/round-N-findings.md`, a root-relative sub-path that sentence says cannot resolve; it must be re-worded for the within-root walk and for the root-relative citation form. **This file is the dispatch body itself (`quality-gate/SKILL.md:341`, `:247`; `red-team/SKILL.md:134`, `:273`), so the edit IS the rollout — not the same terms as the fix-agent-prompt row above, where the file and its wiring are separable.** §3.1 clause 2's second ordering gate does not reach this row: it binds only I2/§3.2's rollout, and I3/§3.3's rollout — what `:222` edits — is not #530-gated by that clause, because §3.3 compliance is a genuine verification, not a silent flip (§3.1 clause 2). But `:222` is not one edit: its root-relative-citation half is schedulable today only once T7's second leg (§5) — the clause-1 depth half of `RESOLVED-BY-WALK:` and its `resolved-by-walk` sub-count, itself C-independent — has landed, a fourth ordering constraint stated in the same shape as the other three: shipping the citation ahead of the counter reproduces the exact silent fail-open channel 2 exists to prevent, on the 63 % dominant class (§3.4) — beside AC-1's first half and AC-2; its within-root-walk half describes C itself and MUST land in the same change as C, per AC-8 (§8). **`:184`, `:297` and `:329` are a different row in every scheduling sense, because they are I4-bearing, not I3-bearing, and I4 has its own precondition (§5) with no compensating population measured today.** **`:184`** is where the `ARTIFACTS` shape is stated for this role and must carry the §3 grammar — **and must name both the findings file and `artifact-N.md`, with its real sha256**, because I4 is an `ARTIFACTS` invariant and this is the only producer-prose row that gives the gate's most numerous role a legal `ARTIFACTS` name for the artifact under review at all; without it a compliant red-team receipt satisfies I4 nowhere. **`:297` and `:329`**, the two canonical worked-example receipts producers copy, both carry `1  READ   docs/plans/foo-design.md` — a gitignored, path-shaped name declared **only** in `TRACE`, which is verbatim the shape §3.4's *Live reproduction* condemns and the shape I4 replaces; both must carry `READ artifact-N.md` instead, **and both worked examples' `ARTIFACTS` blocks must add `artifact-N.md` to match the `:184` edit**. **These three edits are the producer half of I4's rollout and MUST NOT ship until §4's `:758-760`/`:968` row (below) has landed — the third ordering gate, §5 (I4).** Shipping them first, ahead of that orchestrator-side write, is the shape measured live in the gate reading this document: **fifteen** consecutive rounds dispatched with no round-current `artifact-N.md` (rounds 2–16, observed 2026-08-25 — a dated reading of a live directory, not a standing property; see §3.3), so the compliant move under an unqualified `:184` is either an unresolvable basename (UNVERIFIED) or a citation to a copy **at least 1696 lines stale, and increasing** (a line-count delta, not a byte or changed-line count: `artifact-1.md` is 1502 lines/124328 B, the live document is strictly larger and grows with every edit) with each further edit to the artifact under review, hash-vouching for bytes that are not the artifact reviewed (§5, I4) |
| **`return-convention.md`'s own worked-example receipts — the wider I4 vector's rollout has no row either, and a fix pass walked into the gap twice (see FATAL-2, round-2 red-team verification, and FATAL-1, round-3 red-team verification, which found round 2's note-with-disclaimer attempt unbuildable and reverted it)** | `skills/shared/return-convention.md:291-383` (`## Example Receipts`), `:533-578` (`### Example v1.1 receipts`) | **new, target state only — nothing described in this row has shipped.** The `12-judge` worked example is the only one of the file's seven worked-example receipts that names the artifact under review at all. **Once this row lands**, that example will show the target `artifact-N.md`/`ARTIFACTS` single-home shape directly, as binding producer guidance, with no inline precondition note — round 2 shipped exactly such a note and round 3's verify found it unbuildable (its only citable authority was this gitignored plan file, unreachable by the convention file's six adopting skills; see the constraint added to the `:68` row above) and reverted it. **Until this row lands**, the `12-judge` example continues to cite the artifact the way `red-team-prompt.md`'s own worked examples currently do — `READ docs/plans/foo-design.md` in `TRACE`, `review.md` only in `ARTIFACTS` — on the identical terms as the `red-team-prompt.md:297`/`:329` row above. This closes the asymmetry FATAL-2 found: §4 previously inventoried the narrow I4 vector (`red-team-prompt.md`) and was silent about the wider one (`return-convention.md:68` and its `12-judge` worked example, "the wider of the two files" per §5, I4). **Separately, and not gated by I4:** 4 of the 7 worked receipts in these two ranges hard-FAIL `scripts/rcpt_verify.py --tier1` on `dd06b80` — 3 unintentional (`build/7-implementer` and `build/8-implementer` at `:296`/`:335`, 2× `EXEC range exceeds 4 KiB`; `build/42-implementer` at `:559`, 65-hex `sha256` on two `ARTIFACTS` entries) plus 1 deliberate teaching example (`build/9-implementer` at `:369`, the file's own lint-failure worked example) — pre-existing and not caused by any fix pass. **These blocks ARE gated: `scripts/measure_474_denominators.py` (`run_tests.sh:104`) ROW 6 extracts every fenced `RCPT` block from this file plus `red-team/red-team-prompt.md`, Tier-1-lints each, and asserts three gating equalities — `taught blocks == 10`, `taught LINT-FAIL identities ==` the exact five-identity list, and `taught LINT-PASS count == 5`. Consequence for the fix this row schedules: repairing the 3 unintentional failures moves three identities from `fails` to `passes`, so `measure_474_denominators.py:420-427`'s expected-identity list and expected LINT-PASS count MUST be updated in the same change, or `bash scripts/run_tests.sh` goes red.** Fix in the same change as any further edit to these ranges |
| resolution | `scripts/rcpt_verify.py:1320` `_resolve_base_one` | add the bounded within-root walk; ambiguity = FAIL |
| **`PROVENANCE-ONLY:` note** | `scripts/rcpt_verify.py:1806` `tier2_artifacts` | **new pass over `trace`**, inside the function that already receives **both** `artifacts` and `trace` and that has already computed which declared names resolved and hash-matched — the three inputs the §3.4 match key needs. Emit one note per `READ`/`EDIT`/`WROTE` entry whose basename matches no **verified** `ARTIFACTS` basename, `<name>` rendered through `_show_path` (§3.4). **The note pass MUST write into a caller-supplied out-parameter list, the same idiom `tier2_witness` already uses for `wit_notes`/`notes_out` (`:2633`), not accumulate into the function's own return value** — `tier2_artifacts` raises on the first entry that truncates the loop (a hash mismatch, or one of the function's four other raise sites — §3.4), and the sole production call site (`notes += tier2_artifacts(...)`, `:3793`) never executes that `+=` on any of them, so a return-by-value note list is discarded whole, not partially, on every truncated run, regardless of which raise truncated it. **On a truncated run the correct behaviour is a fourth match key, not `TestNotesSurviveALintError`'s per-artifact shape**: a `TRACE` entry whose basename matches an `ARTIFACTS` entry that was never evaluated emits nothing; one matching an entry evaluated (verified or not) before the raise still emits its note — decidable only with the out-parameter in place, because the note is otherwise a negative over a set the raise never lets the caller see (§3.4, T2 leg 6). **Blast radius, priced rather than left beside a costed sibling row with none (G2; compounds F2):** unlike the `resolved-by-walk` row below, this note changes no census **field** — it has no counter (F2) — so `scripts/test_rcpt_verify.py`'s 76 `TIER2-COVERAGE`-line assertions are not the exposure they are for that row: every one of them extracts the census line by its own `TIER2-COVERAGE:` prefix (`cov_line`/`_line` helpers, `:3120`, `:3405`) before asserting, which is by construction blind to additional stderr lines emitted elsewhere in the same run. Measured directly on `dd06b80`: the suite's only exact-full-stderr assertion (`assertEqual(r.stderr, "")`, `test_rcpt_verify.py:373`) runs under `--tier1`, a mode this note never fires under (the note pass lives inside `tier2_artifacts`, Tier-2 only); no other assertion in the file checks total line count or full-stream equality at Tier-2 (`test_repeated_identical_root_is_byte_identical`, `:2409-2415`, is differential — both runs would gain the identical new lines and still match). **So the note's real cost is not a reddened test suite but an operational one, and it is this one:** `return-convention.md`'s own *"Coverage-line capture"* instruction (`:135`) is written for the **one** `TIER2-COVERAGE:` line; an orchestrator that instead captures the **whole** stderr stream inherits the note's full volume — 302 (flat) / 320 (nested) truncation-respecting notes over 68 receipts (§3.4), mean 3.5–7.3 per receipt — added log/context volume with no row or criterion assessing it before this note ships |
| **`RESOLVED-BY-WALK:` note + `resolved-by-walk` sub-count** | the **resolved** branch of `scripts/rcpt_verify.py:1806` `tier2_artifacts` and of `:2633` `tier2_witness` | **keyed on resolution DEPTH, not on which clause resolved** (§3.1 clause 2, T7 both legs) — a clause-1 literal join of a multi-segment name that lands below a root's top level (§3.4 move 1) MUST fire this note on the same terms a clause-2 walk hit does. `cov` is in scope at the emission site, which is what the census sub-count needs; `resolve_base` (`:1364`) / `_resolve_base_one` (`:1320`) must report *how* a name resolved — clause 1 literal join vs clause 2 walk — so the note MAY record the distinction as a parenthetical, but the counter itself MUST NOT branch on it. Siting the counter bump on the resolved-clause distinction instead of on depth loses move 1's coverage, and a note that never fires for a below-top-level clause-1 hit is indistinguishable from a build with no walk-silence, which is **T7**'s second leg exactly. **The blast radius of adding a member to `_COV_COUNTERS` (`rcpt_verify.py:3565`), priced rather than left as a free `cov`-is-in-scope bump:** `render()` (`:3654-3669`) emits **every** member of that tuple, in order, into the single `TIER2-COVERAGE:` line, so a new counter changes the rendered census string on **every** receipt, verified or not; changes the string `quality-gate/SKILL.md:36` parses; and reddens `scripts/test_rcpt_verify.py` (gated `run_tests.sh:103`) — measured: **76** `TIER2-COVERAGE` references, of which **12** assert the **full literal counter list** as one string: `TestCoverageRendering::test_clean_shape_with_a_not_reachable_code` (`:2588`), `TestCoverageRendering::test_partial_shape_renders_witness_0_0` (`:2599`), `TestCoverageEmission::test_clean_shape` (`:3140`), `TestCoverageEmission::test_partial_shape_on_a_truncated_census` (`:3149`), and `TestZeroDeliveredBytesIsBucketedAsEmptyRange`'s eight assertions (`:5104`, `:5121`, `:5136`, `:5162`, `:5186`, `:5198` against the `TAIL_EMPTY_RANGE`/`TAIL_EMPTY_FILE`/`TAIL_ALL_ZERO`/`TAIL_DISCARDED_EXIT` class constants at `:5070`, `:5072`, `:5074`, `:5078`, plus two inline literals at `:5214`, `:5250`) — measured by adding `resolved-by-walk` to `_COV_COUNTERS` in a scratch copy and running `python3 -m pytest scripts/test_rcpt_verify.py -q`: 1 failed / 436 passed baseline vs. 13 failed / 424 passed patched, with the one baseline failure (`TestRootIsValidated::test_an_empty_root_token_is_rejected_not_resolved_to_cwd`, a scratch-copy artifact) common to both. That requires (i) updating those full-string assertions in the same change, and (ii) confirming `:36`'s reader tolerates it. **The alternative that avoids both**, if the blast radius is judged too much for this ticket: report `resolved-by-walk` **only** as a stderr note plus a reason code attached to an existing counter via `note_code` (`rcpt_verify.py:3647`, which exists for exactly *"a second fact about an item that is already counted"*), leaving the census line's field list unchanged — but then horn (b) of §3.1 clause 2's ordering gate, which depends on `:36` being able to read a distinct signal, must be re-examined against whichever form is chosen. **Neither (i) nor (ii) is assigned to a criterion or gate today, and it should be (G1 — Integration Impact F2):** both are mechanical prerequisites of landing this field correctly, not maintainer calls, so they are gated rather than opened: **landing this field (T7 leg 2, scheduled C-independent per §8) MUST NOT ship until the 12 full-literal-counter-list `TIER2-COVERAGE` assertions named above among `scripts/test_rcpt_verify.py`'s 76 references to that string are updated in the same change and `:36`'s reader is confirmed to tolerate the new field — a fifth ordering constraint, in the same shape as the other four this document already names, not merely a cost note.** (`--eval`'s byte-diff contract is not a third condition here — see OQ-11, below, withdrawn.) |
| **I2/I3 tracked/gitignored hard-FAIL (NEW, §3.4's silence-adjacent seventh channel, T11)** | the **resolved** branch of `scripts/rcpt_verify.py:1806` `tier2_artifacts` **and, independently, of `:2633` `tier2_witness`** — both reach the same **git-toplevel** base through `_allowed_bases`'s probe, each via its own call to `resolve_base` | **new check, not a new note, at both sites — an earlier draft of this row scoped the check to `tier2_artifacts` alone, which leaves `tier2_witness`'s identical resolution path untouched.** When `resolve_base` returns a path under a root's git-toplevel base (the branch §2.8 item 4 measures as shipped), check the resolved realpath, relative to that toplevel: `git -C <toplevel> ls-files --error-unmatch -- <relpath>` for I2, `git -C <toplevel> check-ignore -- <relpath>` for I3 (or the Python `subprocess.run(..., cwd=toplevel)` equivalent). **The `-C`/`cwd=` and the `--` separator are both load-bearing, not stylistic — an earlier draft left the invocation unspecified and a naive reading under-reports the exact violation this check exists to catch:** `git` resolves a bare relative pathspec against the **caller's** cwd, not the toplevel just computed, so run from a subdirectory of the repo a tracked file at the root reads as untracked (reproduced: `git ls-files --error-unmatch CLAUDE.md` from `skills/` → exit 1, "did not match any file(s) known to git"; from the toplevel, or with `-C`, exit 0); and a resolved realpath beginning with `-` is otherwise read as a flag without `--` (reproduced: `git ls-files --error-unmatch -rf` → exit 129, "unknown switch"). **Exit-code contract, stated rather than left as "0 vs. not-0":** `0` = match (Tier-2 hard-FAIL under `--strict`, naming the violated invariant); `1` = no match for either tool (proceed); any other code — `128` (cwd resolves outside every checkout; reproduced from `/tmp`: "fatal: not a git repository"), `129` (bad argument syntax), or an `OSError`/`FileNotFoundError` if `git` is not on `PATH` — is **not** folded into "no match" but reported as its own diagnosable disposition, the same way `_refused_clause` names a refusal distinctly rather than treating it as absence. Sited the same way `_unresolved_disposition`'s path-shaped raise is (`:1696-1705`) but on the **resolved**, not the unresolved, branch. **The identical check runs at `tier2_witness`'s own resolved branch, on the same terms**, because a **rangeless** `kind=grep` witness — whose cited name is read straight off the `TRACE` entry's args and is exempt from the #474/D6 `ARTIFACTS`-membership rule (`:886`, *"Scoped to ranged payloads (rangeless grep keeps today's whole-file behaviour)"*) — resolves and reads clean through `tier2_witness` with no `ARTIFACTS` declaration required at all, bypassing a check sited only at `tier2_artifacts`. Today **neither** function runs any tracked-ness or gitignore check anywhere in its body (§3.4, channel 7; measured `grep -c` over `tier2_artifacts`'s full body returns 0; `tier2_witness` shares the identical `resolve_base` call and has no such check of its own) |
| disposition | `scripts/rcpt_verify.py:1644` `_unresolved_disposition` | count 12-hex in the floor **and** in the denominator — and **only** that. **An earlier draft sited both new notes here, and this function can emit neither.** Its own docstring (`:1644-1647`) is *"the ONE disposition for a cited name that **`resolve_base` returned None for**"*, and both call sites (`:1842`, `:2819`) are reached only on the `None` branch: `RESOLVED-BY-WALK:` fires precisely when the walk **did** resolve, the branch that never calls this function, and `PROVENANCE-ONLY:` is keyed on a **`TRACE`** name that nothing in this function's five-parameter signature carries. The two rows above are where each change compiles; this one keeps the item that really is this function's business |
| findings-file location pin | `skills/quality-gate/SKILL.md:312`, `:951` | **the pin whose stated rationale C dissolves** — both lines justify the top-level pin by *"no search"* resolution, which C ends; see §3.4 channel 2. An earlier draft of this row called them *"the live enforcement point for the 63 % class"*, which contradicts §3.4's own finding that *"`:312` has no enforcer: the census **was** its enforcer, by accident"* |
| **the census's one live consumer** | `skills/quality-gate/SKILL.md:36` | **Moved to #530.** Every change the pre-split ruling made to this line — widening its exemption set, widening its counter domain, moving its `stat`'s object, and promoting its recorded advisory to a hard block — belonged to the floor. **This document changes `:36`'s *text* not at all — but C changes its *behaviour*, and that is a separate fact an earlier draft's "not at all" concealed.** `:36` is the census's only live consumer; C zeroes the counters it reads on 16 of `live29`'s 29 receipts and the replacement counter `resolved-by-walk` is a name `:36` does not read. §3.1 clause 2 therefore carries a **binding ordering gate**: C MUST NOT ship until #530 rules OQ-7 or `:36` is amended in the same change. **No edit to `:36` is scheduled by this document**; the gate is what keeps that safe. One item is carried to #530 explicitly because its omission is *silent*: `:36` stats *the cited findings file*, and the floor's clause (1) stats *the round's `round-N-findings.md` at the top level of `<findings-root>`*. Editing `:36` for the code set while leaving the `stat` on the cited file produces a census that looks identical and scores zero on a subagent killed mid-write |
| **`siege`'s root set — a precondition of I1, not a consequence** | `skills/siege/SKILL.md:21` | supply `<findings-root>` as a second root (**#496**) **before** I1 binds `siege`. Until then every `siege` attacker-agent receipt declares `scratch/<run-id>/` findings files that resolve under no supplied root. Orchestrator-side; §3.1 |
| **the artifact under review has no legal name at *any* round whose input copy was not written, and no TRUSTWORTHY one at any round whose copy is stale — a precondition of I4, not a consequence** | `skills/quality-gate/SKILL.md:758-760`, `:968` | **new, and it covers three gaps of different kinds.** (a) **Specification, round 1:** for small artifacts (design docs, plans, hypotheses, mockups) the orchestrator writes `artifact-1.md` into `<findings-root>` **before round 1's dispatch**, and the round-1 dispatch template cites that name. Today `:758-760` says *"Pass the full artifact content to the red-team subagent. **No preparation needed.**"* and `:968` writes `artifact-N.md` only in the *"After each round, write"* list, as *"the artifact snapshot **after fixes** (input to round N+1)"* — so **no copy exists when the round-1 receipt is authored**, in any of the three corpora. (b) **Compliance, rounds 2+:** `:968` already mandates the write after **each** round and it is not happening. Measured on the six-round gate on this document's **predecessor** (run `2026-08-20T09-05-29`; **not** the run reviewing this document, which is `2026-08-21T09-09-39` — §3.3): its scratch directory now holds **two** `artifact-N.md`, `artifact-4.md` (`14:44:00`) and `artifact-6.md` (`16:33:07`, 14 s before round 6's red-team dispatch, and byte-identical to the predecessor doc). Scored by whether a copy existed when the round's red-team dispatch file was written, **4 of that gate's 6 rounds (1–4) were dispatched without one**; rounds 5 and 6 had one. An earlier draft of this row read *"exactly one `artifact-N.md` … and none for rounds 1–3"* and inferred a re-opening at round 6 that the directory falsifies — withdrawn; the count, not the trend, is what supports (b). No new specification closes (b); per §6 it has no enforcer, and the row records it so the remedy is not read as covering it. (c) **Content, every round — the gap with no `BLOCKED` in it.** `:968` writes `artifact-N.md` as *"the artifact snapshot **after fixes** (input to round N+1)"*, i.e. when a round closes; the artifact keeps being edited afterwards, and nothing re-writes or re-checks the copy at the next round's dispatch. A round dispatched against a stale copy produces a receipt that is legal under I1/I3/I4 and **hash-vouches for bytes that are not the artifact reviewed** — `artifacts 1/1`, exit 0, and `:36` recording it verified. **The change is that the write MOVES**: `artifact-N.md` is written into `<findings-root>` **at round N's dispatch step**, from the artifact that round's dispatch file names, and the dispatch template cites that name — not after the preceding round's fixes. **The name MUST carry the same chunk qualifier `fix-verifier-prompt.md:89` already mandates for `verify-log-<chunk-id>-rN.txt`, for the identical reason (§3.2, B4 — Edge Cases F4): `N` is a per-chunk round counter while `<findings-root>` may be shared across chunks on a chunked gate, so an unqualified `artifact-N.md` is exactly the shape §3.2 already rules must be chunk-qualified or it silently overwrites — the write is `artifact-<chunk-id>-N.md` on a chunked gate, `artifact-N.md` unchanged on a single-chunk one.** An earlier draft of this row specified the write unqualified, reintroducing two paragraphs down the exact shape §3.2 itself refuses; the dispatch template's citation of the name (`:184`, `:68`) must carry the identical qualifier. I4's byte-identity precondition is what makes this checkable; §6 says nothing enforces it. §3.3 records the measured instance, dated. This is the same asymmetry the `siege`/#496 row above records, on the class that is **9 of `live29`'s 11 post-C residual receipts and 9 of `corpus17`'s 11 residual rows** — the dominant one in both. Orchestrator-side; §3.1's *"the remedy is to **supply the root**, never to evict the name into `TRACE`"* has no other way to be true here. **This row is what the third ordering gate (§5, I4) binds the producer-facing half of I4's rollout to** — `red-team-prompt.md`'s `:184`, `:297` and `:329` edits (above), **and `return-convention.md:68`'s §3.3 clause (above), together with `return-convention.md`'s own `12-judge` worked example (above) — the wider of the two files, since `return-convention.md` reaches every one of the convention's six adopting skills and not only the red-team dispatch body** — MUST NOT ship until this row has landed, in the shape §3.1 clause 2 already uses for C and I1's precondition already uses for `siege`/#496. This is not the I4 precondition (§5) restated: that precondition binds whether a round's *receipt* is judged by I4 at all, and is checkable only in the direction that cannot see staleness (§3.3's single-home rule forbids citing the live path to compare against); this gate binds the *prose edit a producer executes*, which `:184` states unconditionally today with no "once the copy is written" qualifier, and `:68` states the same rule to a strictly larger audience |
| **dispatch-file `Inputs:` field — a precondition of the channel-4 counter, not a consequence** | `skills/shared/dispatch-convention.md:53-55` | **new.** The header defines `Pipeline` / `Phase` / `Task` / `Timestamp` / `Dispatch-Dir` and nothing else; the body is free prose, so the set the channel-4 counter quantifies over — *"every path the orchestrator handed the producer"* — **exists in no file**. Add a structured **`Inputs:`** list enumerating exactly those paths. Measured over a surviving red-team dispatch (`…/scratch/2026-08-20T09-05-29/dispatch-archive/5-qg-red-team-r1.md`): 12 path tokens / 5 distinct files, of which the mandated receipt shape names 1, so scraping the body reports 4 of 5 — an **80 % false-positive rate** on a compliant receipt — and the counter's producer-independence claim is false without this field. The earlier `78 %` reading was taken on a dispatch file that has since been deleted and is retained only as a superseded one-time figure; the conclusion rests on the schema, which is committed (§3.4 channel 4). This is the seventh file of §4's union and previously had no row |
| orchestrator input-coverage report (§3.4 channel 4) | `skills/quality-gate/SKILL.md` (dispatch loop) | **new** — report by name every path the dispatch file's **`Inputs:` list** supplied that the returned receipt names in neither `ARTIFACTS` nor `TRACE`. **Ordered after the `dispatch-convention.md` row above**, and quantifying over that list and nothing else. Prose-enforced, no pin |
| mandated invocation **string** | `build:14`, `siege:21`, `quality-gate:30`, `return-convention:135` | **unmoved** — the CLI string is byte-identical before and after; the ruling deliberately does not touch the 4 pins' invocations |
| **probe-set / ambiguity prose *inside* those same lines** | `build:14`, `siege:21`, `quality-gate/SKILL.md:30`, `:52`, `:54`, `:56`, **`:291`**, **`:312`**, **`:784`**, **`:951`**, `return-convention.md:104`, `:135`, **`:256`**, **`red-team/red-team-prompt.md:222`** | **MUST be re-worded** for the within-root walk and intra-root ambiguity — see the note below. `:312` (*"resolution is a literal join with **no search**, so the **bare basename** … is probed only at a root's top level, and a findings file one directory down is unreachable under **any** root by that citation form"*) and `:951` (*"resolution — a literal join, with **no search** — probes only at a root's top level"*) each carry the "no search" prose C contradicts, and an earlier draft of this row omitted both. Re-run on `a764245`, `grep -rn "no search" skills/` returns **9 hits over 3 files** — `quality-gate/SKILL.md` ×6 (`:30`, `:52`, `:291`, `:312`, `:784`, `:951`), `return-convention.md` ×2 (`:104`, `:256`), **`red-team/red-team-prompt.md` ×1** — and the third file is the producer-facing one, which is why it now has a row of its own above. **`:52`, `:291`, `:784` and `:256` are new to this row**: an earlier draft's site list named only 5 of the 9 hits the same re-run grep already totalled, leaving four live "no search" sites with no `MUST be re-worded` row anywhere in this table. `build:14`, `siege:21`, `:54` and `:56` above and `:135` carry the equivalent contradicted claim under prose the "no search" grep does not match — `build:14`/`siege:21` under the distinct string *"never a false FAIL"* (2 hits, both there), `:54`/`:56`/`:135` under no distinctive string at all — see AC-8 below for how each is checked |
| probe-set prose | `skills/quality-gate/SKILL.md:54`, `:56` | the only place the full probe set is written down. **The re-wording must also widen pin (b)'s own quantifier**, from *"resolves under any two probed BASES"* to *"is held at more than one path within the supplied roots' subtrees"* — the quantifier C's clause 2 actually uses — because as written pin (b) does not reach a bare basename nested inside a single root's subtree (§3.1), which is currently unowned by any pin (T1-neg records it as a gap, not a coverage claim) |

**The four pinned lines carry more than their invocation strings, and C contradicts what they carry.**
An earlier draft of this table marked all four "unmoved", which is true of the strings and false of
the lines. Verified on `dd06b80`:

- `return-convention.md:135` — *"each root contributes at most one file (its own top level first,
  then that root's git toplevel) … so a name held at both homes of the **same** root resolves
  silently and only a collision across two roots fires"*. **C fires on intra-root collisions**;
  §2.5's own two examples (`artifact-under-review.diff` 7 hits, `mutation-battery.log` 2) sit inside
  the **single** root `crucible-dispatch-1786228538`.
- `quality-gate/SKILL.md:30` — *"Resolution is a literal join with **no search**"*. **C is a
  search.** `:104` of the convention says the same, and `:54`'s pin (b) enumerates the probe set as
  four bases.
- `build:14` and `siege:21` — *"under a single root the cross-root ambiguity hard-FAIL cannot arise
  at all — an unresolvable bare basename is UNVERIFIABLE, **never a false FAIL**"*. Under C a single
  root with a nested layout **can** produce an ambiguity hard-FAIL.
- `return-convention.md:104` needs **two** edits, not the one this table listed: the
  "not only the set it created" retraction *and* its own "a name sitting at the top level of **two**
  supplied roots is an ambiguity hard-FAIL" / "a literal join with **no search**" clauses.

**Costed, not waved through: `build` and `siege` gain a hard-FAIL class they do not have today.**
Both pass exactly one root, and today a single root cannot produce an ambiguity FAIL. Under C it can,
whenever that root nests two files of the same basename. Today's live roots happen to be flat (three
checked: 0 duplicate basenames) and **neither skill pins flatness** — `codegate22` is standing proof
that a gate dispatch root nests. So this is a real new failure mode for two orchestrators, it is
accepted deliberately (an ambiguity FAIL is C refusing a plausibly-wrong first-hit read, §2.5), and
it is what invariant I7 pins.

**`quality-gate` gains a third one, and an earlier draft costed only the single-root pair.**
`quality-gate` passes **two** roots (`quality-gate/SKILL.md:30`, verified: `--root <dispatch-root>
--root <findings-root>`), and it is the orchestrator producing the most receipts in all three
corpora. Under C it gains a class neither the note above nor I7 named: **a bare basename nested under
the dispatch root *and* nested under the findings root** — two hits among the supplied roots'
subtrees, ambiguity hard-FAIL. Today that shape is `UNVERIFIABLE` at exit 0, because
`return-convention.md:135`'s cross-root rule reaches only names at two roots' **top levels**.

**It is a materially different class from the one `quality-gate` already has, not the same one
described twice.** The existing cross-root class is bounded to **two top-level probes**; the new one
is bounded to **two entire subtrees**, one of which is a gate dispatch root that `codegate22` proves
can hold **10,165 files — 13 at the top level and 10,152 nested, of which 9,380 sit under the seven
round directories `r1`–`r7`** (re-measured on `dd06b80`; the `9,380` is §2.6's figure and the
`10,165` is the whole root, a different denominator) — three orders of magnitude more
surface, on the orchestrator with the most receipts and the strictest mandated invocation. The shape
is live in practice: §3.4 move 1 puts the findings class at `out-N/` under the findings root while
receipts and logs accumulate under the dispatch root, and §3.3 already argues about copies existing
in two places.

**Accepted, on the same ground as the single-root class** — an ambiguity FAIL is C refusing a
plausibly-wrong first-hit read — and **recorded as an unmeasured prediction, which is a weaker
epistemic status than the other two.** No frozen corpus exercises a cross-root **nested** collision
(`codegate22`'s 13 top-level files each have exactly one copy in the whole tree; the intra-root
collisions §2.5 measures sit inside a single root), so this class is **structurally implied by clause
2 and measured by nothing**. T1 carries a leg for it. Naming it is what keeps I7 true: I7's own terms
say *"any **further** new hard-FAIL class reaching an orchestrator is a defect in this ruling"*, and
this class is either named here or it is that defect.

**The producer-side edit surface is not the set of files containing the word `ARTIFACTS`, and an
earlier draft scoped it that way.** That scan is correct as far as it goes — `grep -rl ARTIFACTS
skills/` returns exactly **four** files: `shared/return-convention.md`,
`quality-gate/fix-verifier-prompt.md`, `red-team/red-team-prompt.md`, `quality-gate/SKILL.md` — and it is **exactly why the draft
missed `siege`**: `siege/SKILL.md` never uses the word `ARTIFACTS`, yet it is a producer-configuration
site this ruling binds, and it is where **#496** is recorded. A grammar ruling's blast radius is the
set of receipt **producers and the roots supplied to them**, not the set of files quoting the section
name. The correct scan adds every file that invokes the linter or configures its roots —
`grep -rl rcpt_verify.py skills/` → `build/SKILL.md`, `quality-gate/SKILL.md`, `siege/SKILL.md`,
`shared/dispatch-convention.md`, `shared/return-convention.md` — giving, as the **union of the two
greps quoted in this sentence**, **seven** files, not four. (Five and four, overlapping on
`shared/return-convention.md` and `quality-gate/SKILL.md`: 5 + 4 − 2 = 7. An earlier draft said
*"six"*, which matches neither grep nor their union; the seventh file is
`shared/dispatch-convention.md`, which now has a row of its own in the table above for the
channel-4 input list.) The
narrowness claim is retained for the four `ARTIFACTS`-quoting files and withdrawn for the surface.

**Two of the six adopting skills are absent from this seven-file union, and the grep-based method
cannot see either — the same failure mode this paragraph already diagnoses for `siege`, not yet
applied to itself (D2 — Blind Spots F4).** §3.1 clause 2's own six-skill adopter list — `build`,
`quality-gate/SKILL.md`, `red-team/SKILL.md`, `red-team/red-team-prompt.md`, `siege`, `warden` — names
both `red-team/SKILL.md` and `warden`; neither appears in either grep (`grep -n "rcpt_verify.py\|--root"
skills/warden/SKILL.md skills/red-team/SKILL.md` returns zero hits, re-run on `dd06b80`).
**`red-team/SKILL.md` has a stated reason, and it is a real one, not an oversight left unstated:**
standalone mode runs "**the v1.1 Tier-1 structural linter only**" (`red-team/SKILL.md:159`) — Tier-1
is root-free by construction (§3, *Lexical grammar*: "no root, no git handle and no filesystem is in
scope") — so standalone red-team genuinely has no root to misconfigure; invoked as a `quality-gate`
sub-skill, the roots are `quality-gate/SKILL.md:30`'s, not red-team's own. Its absence from the grep is
therefore correct, and this document should say so rather than leave the gap looking identical to
`warden`'s. **`warden` has no such stated reason, and the question I1's precondition asks for
`siege` — does the orchestrator supply a root containing its producers' outputs? — has not been asked
for it.** `warden` dispatches reviewer subagents directly (temper, delve — not only by delegating to
`quality-gate`/`siege`, which own their own roots when invoked as sub-skills), and this document does
not verify what root, if any, `warden` supplies for those direct dispatches' own receipts. **Not closed
here** — named as an open gap on the same standard I1's precondition already uses for `siege`, not
answered by this ruling.

**`build` is named beside `siege` for the new hard-FAIL class two paragraphs below, but only `siege`
got the precondition, the #496 issue and a row (D1 — Integration Impact F4).** **What is verified:**
`build:14` states plainly that `build` passes exactly one root — the dispatch root — and separately
maintains its own orchestrator-scratch directory at `~/.claude/projects/<project-hash>/memory/`
(`build/SKILL.md:17`, `:142`, `:336`, `:560`) for cairn, ledger and pipeline-state files, which is
**not** supplied to the linter as a root. **What is not verified:** whether `build`'s dominant producer
role — the implementer, per `return-convention.md`'s own `build/7-implementer` worked example —
writes its declared `ARTIFACTS` (a patch, a test-output log) under the dispatch root's top level, the
way the linter's own fixtures assume, or under some other location the way `siege`'s attacker findings
sit under `scratch/<run-id>/`. `build-implementer-prompt.md` states no canonical output location in its
own text; the convention lives in `shared/implementer-common.md` (CANONICAL) and was not read as part
of this scan. **Not closed here** — this row records that the question exists and has not been asked,
the same failure mode this document diagnoses for its own earlier scan of `siege` above; asking it is
future work, not answered by this ruling.

**Two scan errors in this paragraph, both corrected, and the pattern is worth recording.**
(1) An earlier draft appended *"plus 17 `skills/build/evals/fixtures/**/mock-dispatch/*.md`
fixtures"* to the quoted `grep` output. Re-run on `dd06b80`, `grep -rl ARTIFACTS skills/` returns
**four** files and **no** fixture; `grep -rl ARTIFACTS skills/build/evals/` returns **nothing**. The
`17` is a real count of a different set — there are exactly 17 `.md` files under
`skills/build/evals/fixtures/**/mock-dispatch/`, and **none of them contains the string
`ARTIFACTS`**. The union arithmetic (5 + 4 − 2 = 7) never used the 17 and is unaffected, but a
stated `grep` output that does not reproduce, inside the paragraph whose subject is scanning
correctly, is the one place a reader is entitled to take a `grep` at face value.
(2) **Recorded below** — the scan never left `skills/`, and the repo's densest population of the exact
objects this ruling governs is one directory over. Neither error was visible from the text; both were
found by re-running the greps this paragraph quotes. **Take that as the standing instruction for this
section: re-run, do not re-read.**
`quality-gate/fix-verifier-prompt.md:89` **already** mandates the `verify-log-rN.txt` shape and
already forbids naming the artifact under review by its repo-relative path, and `:99` already states
the ARTIFACTS-vs-TRACE split. The convention #513 needs largely exists; it is missing on the **fix**
agent because `skills/quality-gate/` has **no fix-agent prompt file at all** — the only dispatched
role in the gate without one. **Authoring that file is the bulk of the implementation.**

## 5. Invariants

**Checkable by inspection**

- I1 — every `ARTIFACTS` entry resolves under a supplied root, or the receipt is illegal.
  **Precondition, per §3.1:** I1 binds a producer only once the orchestrator supplies a root
  containing that producer's outputs. `siege` does not today (**#496**, `siege/SKILL.md:21`), so
  **I1 does not bind `siege` until #496 lands**; the remedy is orchestrator-side (supply the root),
  never producer-side (evict the name).
- I2 — no `ARTIFACTS` entry names a tracked repo file.
- I3 — no `ARTIFACTS` entry names a gitignored path or its bare basename.
  **Neither has code enforcement today, and this section's own header is misleading for both:
  "checkable by inspection" describes I1 (§3.1) correctly, but I2 and I3 are checkable by inspection
  only in the sense that nothing else checks them either.** `tier2_artifacts`
  (`rcpt_verify.py:1806`) resolves, checks ambiguity, reads and hash-compares; it contains no
  tracked-ness or gitignore-status check, so a tracked repo file or gitignored path-shaped name cited
  by repo-relative path against a root whose git-toplevel base contains it resolves, hash-verifies,
  and lints clean — violating either invariant while reading as **more** verified than an honest
  receipt, not less. This is the failure §3.4's silence audit does not cover, because it runs the
  opposite direction (a false mention, not a missing one); see §3.4's silence-adjacent seventh
  channel for the full demonstration and the specified remedy (**T11**, §4, §5), and **OQ-9** for
  whether it is scheduled ahead of or alongside #530's floor.
- I4 — the artifact under review is named as the orchestrator-supplied single-home copy.
  **Precondition, in the shape I1 already uses for `siege`, and it binds *every* round, not only
  round 1:** I4 binds a round only once the orchestrator has written that round's input copy into
  `<findings-root>` **before that round's dispatch** **and that copy is byte-identical to the
  artifact named in that round's dispatch file**. There are three distinct gaps behind that
  precondition; an earlier draft named only the first, and stated the precondition in a form that
  ruled the copy's *absence* and said nothing about its *content*:
  - **Round 1 is a specification gap.** `quality-gate/SKILL.md:758-760` prepares nothing for small
    artifacts (*"Pass the full artifact content to the red-team subagent. **No preparation
    needed.**"*) and `:968` writes `artifact-N.md` only in the *"After each round, write"* list, so
    at round 1 no copy has been written by anyone and the artifact under review has **no legal
    `ARTIFACTS` name at all**. §4 carries the orchestrator-side row that closes it.
  - **Rounds 2+ are a compliance gap in an obligation that already exists.** `:968` mandates
    `artifact-N.md` after **each** round, unconditionally. Measured in the scratch directory of the
    six-round gate on this document's **predecessor**
    (`…/memory/quality-gate/scratch/2026-08-20T09-05-29/` — not the run reviewing this document,
    which is `2026-08-21T09-09-39`; see §3.3): after four
    completed rounds it holds `round-{1,2,3,4}-findings.md` and exactly **one** `artifact-N.md` —
    `artifact-4.md`, `mtime 2026-08-20T14:44:00`, written after round 4 and **56 seconds before
    round 5's dispatch file** (`16-qg-fix-r5.md`, `14:44:56`). `artifact-1.md`, `artifact-2.md` and
    `artifact-3.md` were never written. So no round of this gate was dispatched with its input copy
    on disk, and **I4 binds none of rounds 1–4**; round 5 is the first round of that gate for which
    the precondition is satisfied.
  - **A copy that exists and is STALE is a third gap, and it is the one with no `BLOCKED` in it.**
    The write `:968` mandates is *"the artifact snapshot **after fixes** (input to round N+1)"* — it
    happens when a round closes, and the artifact keeps being edited afterwards, so the copy's
    content lifecycle is unruled between the write and the next dispatch. A round dispatched against
    a stale copy has a name that is legal under I1/I3/I4 and whose receipt then **hash-vouches for
    bytes that are not the artifact reviewed**: `artifacts 1/1`, exit 0, every counter clean, and
    `quality-gate/SKILL.md:36` recording the receipt as verified. Absence fails loudly; staleness
    fails **silent and clean**, which is the worse of the two and is grudge `e0f0a6b75692`'s
    direction. §3.3 records the measured instance. The byte-identity clause above is what closes it,
    and it is not self-executing: §4's `:758-760` / `:968` row carries the orchestrator-side change,
    which is that the write **moves** from the *"After each round, write"* list to the dispatch step
    and the dispatch template cites the name it just wrote. Per §6 there is no enforcer for it
    either, so this is a stated ordering, not a claim that the gap is closed.

    **Re-measured on `dd06b80` after that gate closed (an earlier draft's inference here was
    false and is withdrawn).** `ls --time-style=full-iso` on
    `…/memory/quality-gate/scratch/2026-08-20T09-05-29/` now shows **two** `artifact-N.md`, not one:

    ```
    artifact-4.md  113695  2026-08-20 14:44:00     18-qg-red-team-r5.md  2026-08-20 15:14:05
    artifact-6.md  157605  2026-08-20 16:33:07     20-qg-red-team-r6.md  2026-08-20 16:33:21
    ```

    `artifact-6.md` hashes to `530b7f5848973881a53e5f1f744fb60ef2d571a5b8e494323087a1a8eb038878` —
    **byte-identical to the 1929-line predecessor design doc named in the split record above**
    (verified by `sha256sum` on both) — and it was written **14 seconds before round 6's red-team
    dispatch file**. So **round 6 did have its input copy on disk at dispatch.** Scoring the six
    rounds of that gate by whether an `artifact-N.md` copy of the artifact under review existed when
    the round's red-team dispatch file was written: rounds **1, 2, 3 and 4 have none** (rounds 1–3
    have no copy at all; `artifact-4.md` postdates round 4's dispatch, `12:05:31`, by 2 h 38 m), and
    rounds **5 and 6 both do**. **4 of 6 rounds non-compliant — and the trend across the run is
    toward compliance, not away from it.**

    **What is withdrawn, and why it matters more than the count.** The earlier draft wrote *"it is
    also the last **so far**"*, *"the directory **still** holds exactly one `artifact-N.md`"*, and
    then converted that currency claim into this document's **only** argument for a specific
    conclusion: *"the compliance gap … **re-opened on the very next round**, which is the **strongest
    available evidence** that (b) needs an enforcer and not a restatement."* Every timestamp it
    quoted is correct and its time-scoped clause is still true — no `artifact-5.md` was written
    between `15:32:09` and `16:03:29` — but the very next round is round 6, and round 6 wrote its
    copy. **The datum the document nominated as its strongest evidence points the other way**, so the
    inference is deleted rather than re-argued. `artifact-6.md` landed **14 h 46 m before this
    document was authored**, i.e. it was checkable at authoring time; a document whose header says
    *"Every measurement below was taken on that tree"* and whose §6 warns that *"a corpus re-frozen
    to pass is not evidence"* cannot carry a superseded scratch reading as its strongest evidence.
    **The (b) gap survives on the count alone** — 4 of 6 rounds dispatched with no input copy, and
    per §6 no enforcer for either half — and that is now the whole of the argument for it.
    §4's remedy row reaches only the round-1 half; the round-2+ half
    needs no new specification, only the existing one obeyed, and per §6 neither half has an
    enforcer.

  Until all three are closed, **I4 does not bind a round whose input copy was not on disk at
  dispatch, or was not byte-identical to the artifact that round's dispatch names**, and that is a
  stated ordering rather than a claim that the gaps do not exist. The predecessor gate's dispatch
  files consequently instruct the reviewer to put the doc in `TRACE`, which is the one move §3.1
  says must **never** be the remedy. The gate reviewing this document is the measured instance of
  the **third** gap, recorded in §3.3 as a dated observation rather than as a standing property of a
  run still in progress; the predecessor's rounds 1–4 are the historical instance of the first two,
  measured on that gate rather than inferred from the two frozen corpora (`corpus17` holds its
  copies; `live29` regressed away from them; the predecessor gate wrote none until round 5 and one
  more at round 6).
  The alternative — sanctioning `TRACE`-only for a round with no copy, and carving it out of
  §3.1's *"never"* — is a maintainer call, **OQ-6**.

  **Ordering, binding — the third such gate this document states, in the shape §3.1 clause 2
  already uses for C and the I1 precondition above already uses for `siege`/#496.** The
  producer-facing edits that make I4's `ARTIFACTS` clause bind at all — `red-team-prompt.md`'s
  `:184` clause and its `:297`/`:329` worked-example `READ`/`ARTIFACTS` lines (§4), **and
  `return-convention.md:68`'s §3.3 clause (§4) and `return-convention.md`'s own `12-judge`
  worked example (§4) — together the wider of the two files, whose `:68` clause and `12-judge`
  worked example are both I4-bearing, because `return-convention.md` reaches every one of the
  convention's six adopting skills and not only the red-team dispatch body** —
  **MUST NOT
  ship until §4's `:758-760`/`:968` row has landed**: the orchestrator-side write moved to round
  N's dispatch step, written from the artifact that round's dispatch file names, with the
  dispatch template citing the name it just wrote. **This is not the precondition two paragraphs
  above, restated.** The precondition binds the *invariant* — whether a round's receipt is judged
  by I4 at all — and is not producer-checkable in the direction that matters: the absence half is
  checkable (`stat`), but the byte-identity half requires comparing `artifact-N.md` against "the
  artifact that round's dispatch file names," and §3.3's single-home rule forbids citing the live
  path, the only handle that would make the comparison possible. This gate instead binds the
  *prose edit a producer executes*: `:184` states its `artifact-N.md` clause unconditionally, with
  no "once the copy is current" qualifier and no instruction to the producer to check — and `:68`
  states the same rule to a strictly larger audience — and §8
  would otherwise schedule either as C-independent and schedulable today. **Measured, on the gate reading this
  document, 2026-08-25** (a reading of a live directory, not a standing property): `ls
  …/scratch/2026-08-21T09-09-39/` holds `round-1`…`round-16-findings.md` and exactly one
  `artifact-N.md` (`artifact-1.md`, 1502 lines/124328 B), so the write `:968` mandates has run zero
  of fifteen times since round 1 (rounds 2–16); the live document is 3198 lines, **a floor of at
  least 1696 lines stale** and increasing with each further edit (a line-count delta, not a byte or
  changed-line count), and the
  compliant move under an unqualified `:184` is to cite it — hash-vouching for bytes that are not
  the artifact reviewed, `artifacts 1/1`, exit 0, `:36` recording it verified. That is the same
  "fail-open and silent, produced by obeying the ruling rather than by violating it" shape §3.3
  names, on the gate's most numerous producer role. **Standing note:** the stale-lines floor above
  is the subtraction of the two measurements this same sentence prints — `artifact-1.md`'s line
  count and the live document's line count — not an independent figure; any future edit that
  changes either operand (most commonly the live line count, which grows every round) MUST re-run
  the subtraction here and at the three other sites **in this document** that cite the resulting
  number (find them with `grep -n '<current figure>'` on this file; as of this writing they are
  this document's lines 16, 25 and 1791 — header ×2 and §4's `red-team-prompt.md` row), so the
  printed floor never again disagrees with its own printed operands. **The subtraction MUST be taken
  against the file as saved after every other edit in the same change has landed, and re-checked
  with `wc -l` after saving — a figure measured before the change's own edits landed does not
  satisfy this note**, even if every other requirement above is met.
- I5 — the mandated-invocation **string** at each of the 4 pins is byte-unchanged by this ruling.
  **Narrowed deliberately:** the *lines* are not unchanged — `build:14`, `siege:21`,
  `quality-gate/SKILL.md:30` and `return-convention.md:135` each also carry probe-set or
  cross-root-only-ambiguity prose that C contradicts, and §4 lists them as a separate edit surface.
  Inspection falsifies the wider claim, so the wider claim is not made.
- I6 — containment (`_allowed_bases`) is unchanged; the walk adds no base.
- I7 — **the complete set of new hard-FAIL classes C's walk creates is the two enumerated here, and
  no other.** **Narrowed to C's walk, deliberately** — an earlier draft's *"any further new
  hard-FAIL class reaching an orchestrator"* read as a claim about every mechanism this document
  adopts, and §3.4 move 1 is a third: a producer-side citation-form recommendation, not part of C,
  that converts a soft `UNVERIFIABLE` into a hard `--strict` BLOCK whenever the prefix is wrong (§3.4
  move 1, measured). I7 does not cover it because I7 is about what the **walk** does to the failure
  taxonomy; move 1's class is named and costed at its own site instead, which is where a reader
  evaluating that specific remedy will look for it. **The `not absolute` lexical clause is a fourth,
  on the same precedent**: it converts a paste of §3.2's mandated absolute `TRACE` form into
  `ARTIFACTS` from a resolving, hash-verifying name into a Tier-1 hard-FAIL (§3, *Lexical grammar*) —
  also not part of C's walk, also named and costed at its own site (§3, and the CI-suite row of this
  table) rather than folded in here. **An earlier draft enumerated only the first and
  scoped the invariant to `build` and `siege`.**
  - **(i) `build` and `siege`** — an **intra-root** basename collision under their single dispatch
    root, and **only** for a collision with no copy at the root's top level (a name clause 1
    resolves never reaches clause 2 — §3.1). Measured: §2.5's two `codegate22` examples.
  - **(ii) `quality-gate`** — a **cross-root nested** collision: a bare basename nested under the
    dispatch root *and* nested under the findings root, on the mandated two-root invocation
    (`quality-gate/SKILL.md:30`). Distinct from the cross-root class `quality-gate` already has,
    which `return-convention.md:135` bounds to the two roots' **top levels**. **Accepted, and
    unmeasured** — no frozen corpus contains the shape; see §4's costing note and T1's second leg.

  Checkable by inspection against §4's costing note; any *further* new hard-FAIL class **created by
  the walk** and reaching an orchestrator is a defect in this ruling, not a consequence of it. **One
  such class was found by inspection and is the reason the I1 precondition above exists:** I1 plus
  any floor #530 adopts would reach `siege` with a second consequence — `not-reachable` on every
  attacker findings file — which by this invariant's own terms would be a defect in the ruling.
  Sequencing #496 ahead of I1 is what keeps I7 true, and it is a **stated ordering**, not a claim
  that the class does not exist.

  **Aggregated in one place, because no single place did before (H1 — Technical Soundness F5).** I7's
  own terms bound only the walk's two classes; three more are named and costed at their own sites
  rather than folded in, and a fourth is added by this fix pass (D3, above). The complete set of new
  Tier-1/Tier-2 hard-FAIL classes this document's ruling creates, wherever each is actually specified:

  1. **I7(i)** — `build`/`siege`, intra-root basename collision (above).
  2. **I7(ii)** — `quality-gate`, cross-root nested collision (above). Accepted and unmeasured.
  3. **§3.4 move 1's wrong-prefix `--strict` block** — a root-relative citation with the wrong prefix
     hard-FAILs where the bare form degraded to `UNVERIFIABLE` (§3.4).
  4. **The `not absolute` lexical clause** — a §3.2-compliant `TRACE` paste into `ARTIFACTS` now
     hard-FAILs at Tier-1 (§3, *Lexical grammar*).
  5. **T11's I2/I3 tracked/gitignored hard-FAIL** — three legs, §3.4 channel 7, below. Scheduling is
     OQ-9.
  6. **T11's degraded-git-environment hard-FAIL** — any exit code outside `{0, 1}` from the
     `ls-files`/`check-ignore` probe (below, D3).

  A maintainer reading only I7 sees two of six. This list is not a new invariant — I7's own scope
  (*"what the walk does to the failure taxonomy"*) is deliberately narrower than the ruling's full
  surface — it is the aggregation I7's own text asks for and does not itself supply.
- I8 — **NEW, and widened to `TRACE` — an earlier draft closed only the `ARTIFACTS` half of an
  identical defect.** `(none)` is legal in the `ARTIFACTS` body **only as its sole non-blank
  line**. A `(none)` co-occurring with any entry is a **Tier-1 `LintError`**, not a silent discard.
  The shipped parser violates this — `rcpt_verify.py:240-241` is `if line == "(none)": return {}`,
  a `return` inside the loop with no single-line-body anchor — so one producer-controlled line
  empties the set §3 calls *the vouched-and-checkable set*, nullifying I1, I2 and I3 at once and
  converting the `--strict` hard-FAIL T6 pins into exit 0 (§3.4 channel 5). Enforcement site:
  `parse_artifacts` (§4). **The identical clause binds `TRACE`.** `(none)` is legal in the `TRACE`
  body **only as its sole non-blank line**, enforced at `parse_trace` (`rcpt_verify.py:259-260`,
  `if line == "(none)": return []` — the verbatim same unanchored `return` inside the parse loop).
  Verified directly at the parser: `parse_trace(['1 READ … ', '2 WROTE … '])` returns two entries;
  appending `(none)` in either position returns `[]` — both entries lost, in either ordering. This is
  the channel that makes `TRACE` load-bearing for the ruling adopted here: §3.2 relocates every
  tracked repo file into `TRACE`, and §3.4's `PROVENANCE-ONLY:` note iterates the `TRACE` entries, so
  one producer-controlled line nullifies both. Enforcement site: `parse_trace` (§4). **The identical
  clause binds `CLAIMS` too.** `(none)` is legal in the `CLAIMS` body **only as its sole non-blank
  line**, enforced at `parse_claims` (`rcpt_verify.py:352-353`, the verbatim same unanchored
  `return []` inside the parse loop, carrying the identical trailing comment as `parse_trace`'s).
  Verified directly at the parser: two `CLAIMS` entries survive intact; appending `(none)` in either
  position returns `[]` — both lost, in either ordering, the same shape as the other two legs. A
  `(none)` there empties the list the `CLAIMS`-citation guard (`:923-939`) iterates, so that guard
  cannot fire either (§3.4 channel 5). Enforcement site: `parse_claims` (§4). **Pinned by
  T10**, because "checkable by inspection" is what the earlier draft's line-by-line reading of these
  same eleven lines already did, and it missed this — three times, once per parser.

**Requires tests**

- T1 — a bare basename that **clause 1 does not resolve** and that then has more than one hit
  **within the supplied roots' subtrees** is an ambiguity hard-FAIL, not a first-hit read. Pin
  against `codegate22`'s real nested layout, where `artifact-under-review.diff` has 7 distinct hits. **The narrowing is not
  cosmetic:** verified on the frozen corpus, that root holds **no** top-level
  `artifact-under-review.diff` — all 7 copies are under `r1`–`r7` — so the fixture exercises only the
  nested-only shape, and a pin written to the wider wording would fail on a top-level-plus-nested
  fixture. **Broken copy (DEC-31):** a build whose clause 2 returns the first hit instead of raising.
  T1 fails against it because the fixture has 7 hits and the assertion is a hard-FAIL, so
  first-hit-wins returns `r1/artifact-under-review.diff` at exit 0 where the pin demands exit 1 —
  the assertion is on the raise, not on the resolution, so it cannot go green on a resolver that
  does not raise.
  **Second leg — NEW: the cross-root nested collision.** `codegate22` exercises the
  intra-root case only, so I7(ii) — `quality-gate`'s two-root class — is pinned by nothing. The leg
  asserts that a bare basename nested under **root A** and nested under **root B** is an ambiguity
  hard-FAIL on a two-root invocation. **The fixture must be constructed** (no frozen corpus holds
  the shape) and, unlike T3's, it may sit outside the checkout: it needs two supplied roots, not a
  git toplevel. **Broken copy (DEC-31):** a build whose clause 2 walks only the **first** root, or
  which de-duplicates hits by basename rather than by realpath — either returns one hit where the
  pin demands two and a raise.
- **T1-neg — NEW, two legs, the negative pins SIG-4's gap requires.** **First leg:** a basename
  held **both** at a supplied root's top level and deeper in that same root resolves **silently to
  `root/name`** at exit 0: C does not fire, clause 2 never runs, and the census is clean. **This is
  NOT `quality-gate/SKILL.md:56`'s "two-homes case"** — an earlier draft of this leg made that
  citation and it is wrong on the text: `:56`'s two homes are a root and that same root's **git
  toplevel**, which are two probed bases, while this shape is a single root's top level versus its
  own subtree, which pin (b) does not quantify over at all (§3.1). The shape is **unowned by any
  pin**, unchanged by this ruling, and pinned here as a recorded gap rather than implied covered.
  **Broken copy (DEC-31):** a build that runs clause 2 unconditionally instead of only over
  clause-1 misses — T1-neg fails against it, because that build finds 2 hits and raises where the
  pin asserts exit 0 and a resolution to `root/name`. **No frozen corpus contains this shape**
  (verified: `codegate22`'s 13 top-level files each have exactly one copy in the whole tree), which
  is itself why nothing measured it; the fixture must be constructed, and per §6 it must live
  **outside** the checkout — T1-neg is in §6's **first** class (its assertion is about the *correct*
  build's disposition), so if the repo were a probed base the pin would report a configuration
  production does not have. Contrast T3 and T11, §6's carve-out class. **Second leg — NEW: the
  top-level-in-A, nested-in-B variant, which sits in neither invariant nor pin.** A bare basename at
  root A's top level and nested under root B: clause 1 resolves it in A (a first-hit read), so
  clause 2 never runs on B's copy; pin (b) does not fire either (B's copy is under no probed base);
  and it is not I7(ii), which is nested-under-**both** A and B. On the mandated two-root
  `quality-gate` invocation this is the likeliest of the unowned shapes to occur, because §3.4 move 1
  puts findings under `out-N/` in one root while receipts and logs accumulate in the other. The pin
  asserts exit 0 and resolution to A's copy; **broken copy (DEC-31):** a build whose clause 2 walks
  both roots unconditionally, finding B's nested copy too and raising ambiguity where the pin
  asserts a clean first-hit resolution.
- T2 — a `TRACE` name absent from `ARTIFACTS` emits `PROVENANCE-ONLY`, and the run is **not** silent
  about it — pinned **once per verb, `READ` / `EDIT` / `WROTE`**, because scoping this to two verbs
  is the defect §3.4 corrects. The `READ` leg's broken copy is the shape that regresses: a receipt
  whose only home for a repo file is a `TRACE READ`, asserted to emit the note, run against a build
  with the note keyed on the verb.
  **Fourth leg — NEW, because §3.4 now states the note's match key and the pin
  must discriminate it.** **A `TRACE` entry carrying a file's ABSOLUTE path, whose BASENAME matches
  an `ARTIFACTS` entry that Tier-2 RESOLVED AND HASH-VERIFIED, emits NOTHING.** The three verb legs
  above must therefore use `TRACE` names *absent* from `ARTIFACTS` under that comparison, and this
  fourth leg uses one *present* under it while differing as a literal string. **Broken copy
  (DEC-31): a build keyed on the literal `parts[0]` string** — the reading the earlier draft's
  wording admitted, which measurably mislabels **13** verified entries across the three corpora as
  *"not verified"*. That build fires on this leg where the pin demands silence.
  **Fifth leg — NEW, and it is the leg the whole match-key clause turns on.** **A `TRACE` entry
  whose basename matches an `ARTIFACTS` entry that FAILED to resolve MUST emit the note.** The
  fixture is one declared name that resolves under a supplied root and one that does not, with a
  `TRACE` entry for each carrying the same basenames by absolute path; the pin asserts **exactly one
  note**, naming the second. **Broken copy (DEC-31): a build keyed on the basenames of *all*
  declared names rather than of the verified ones** — the verified-blind reading, which stays
  **silent** on this leg. It is the copy with the largest measured discriminator in this document,
  **evaluated with every `ARTIFACTS` entry tried (no raise-and-abandon)**:
  across the three frozen corpora it suppresses **66 entries (flat `codegate22`) / 89 entries (real
  nested `codegate22`)** that name unverified artifacts, of which **4 sit on
  `live29/rcpt-22-asreturned.txt` and 4 on `corpus17/rcpt-18-asreturned.txt`, the two largest
  single-receipt contributors under that reading** — and silence is the failure
  direction grudge `e0f0a6b75692` names, so a pin that cannot see it is a pin that cannot defend this
  clause. **Under the truncation rule this section adopts (above), the same discriminator is 61
  flat / 79 nested, and the per-receipt attribution changes with it**: `corpus17/rcpt-18` raises on
  its own first entry's sha256 mismatch, so under the ruled reading it contributes **1**, not 4, and
  `live29/rcpt-22` contributes **2**; neither is then the largest single-receipt contributor — a
  five-way tie at 3 in `live29` (flat) or `codegate22/r2/rcpt-6` at 6 (nested) is. Both readings
  discriminate the leg; only the magnitude and the named exemplar differ, and an implementer building
  against the frozen corpora as they sit on disk should expect the ruled figures. The fixture's
  discriminator count is layout-dependent for the same reason §3.4's volume
  table is; state whichever `codegate22` layout the implementation's own corpus sits in.
  **`rcpt-11-qg-fix-r4.txt`, this document's own worked exemplar (§3.4), is not a member of any of
  the three frozen corpora and does not belong in the sentence above** — re-measured against that
  receipt's own two roots (the qualifier §3.4 already uses for the same receipt), it independently
  suppresses 6, but that figure is outside the frozen-corpora total and must not be added into it.
  Without legs 4 and 5 together the pin cannot separate the three candidate keys, and separating
  them is the entire subject of §3.4's match-key clause.
  **Sixth leg — NEW, the truncated-run key an earlier draft's remedy could not discriminate, and
  which needs BOTH halves in one fixture or it cannot tell "correct" from "notes discarded
  wholesale."** **A `TRACE` entry whose basename matches an `ARTIFACTS` entry left UN-EVALUATED by
  any raise that truncates the entry loop emits NOTHING — neither the note nor its suppression is
  asserted — and a
  `TRACE` entry whose basename matches an entry EVALUATED (verified or not) before the raise still
  emits its note.** The fixture is `corpus17/rcpt-18`'s shape for the un-evaluated half: a first
  entry that hash-mismatches (raising before Tier-2 continues) and a later, unreached entry whose
  basename a `TRACE` entry also carries — the pin asserts **zero** notes for that half, distinguishing
  it from leg 5's *"failed to resolve"* case, which **did** run to completion. The evaluated half
  needs a second entry, ahead of the raise, that is evaluated and unverified, with its own `TRACE`
  match — the pin asserts **one** note for that half. **The fixture must be built twice, once
  truncating on a hash mismatch and once on the `--strict` path-shaped raise** (`_unresolved_disposition`,
  live in `live29` today) — a build that records evaluation status only in the mismatch arm passes the
  first construction and fails the second, and the match key's own text (above) does not privilege
  either raise site over the other. **Broken copy (DEC-31): a build that
  accumulates `PROVENANCE-ONLY:` notes into `tier2_artifacts`'s own return value instead of a
  caller-supplied out-parameter** — the shape that goes green on this leg's un-evaluated half by
  accident (the raise discards the return value before the caller ever sees it, coinciding with the
  ruled "emits nothing") and wrong on the evaluated half (the same discard drops a note the rule says
  MUST fire), which is exactly the coincidence-is-the-trap shape a return-by-value build produces. A
  second broken copy — a build that fires the note on any `TRACE` entry matching an un-evaluated
  `ARTIFACTS` entry, the shape `TestNotesSurviveALintError` sanctions for its own four note classes,
  wrongly transplanted here because this note is a negative over the whole verified set, decidable
  only once every entry has been tried, not a per-artifact fact — fails the un-evaluated half only.
  Without leg 6's both halves, legs 4 and 5 cannot tell a build with the correct out-parameter logic
  from one that discards every note on a truncated run, evaluated or not.
  **Seventh leg — NEW, the escaping guarantee SIEGE-R2BA-4 already won for `ARTIFACTS` names,
  extended to the least-constrained name class in the grammar.** A `TRACE READ` whose name carries a
  NUL and an ANSI escape sequence MUST emit `PROVENANCE-ONLY:` with both neutralised and neither
  reaching the channel raw. **Broken copy (DEC-31): a build interpolating the raw `args` token** —
  the shape `_show_path`'s own docstring says the surrounding code deliberately uses for whole
  `args` strings, which is exactly the field a `PROVENANCE-ONLY:` name is extracted from, so "the
  surrounding code already does it" is not available as a defense for this site the way it is for
  every other `_show_path` call in the file.
- T3 — the walk is bounded to supplied roots and never reaches the repo tree (the C/C′ boundary;
  the fixture-collision case of §2.5 is the negative pin). **Broken copy (DEC-31):** a build whose
  clause 2 rglobs each root's **git toplevel** as well — C′, and the literal reading of the
  containment-union wording §3.1 now removes. T3 fails against it on any fixture root inside the
  checkout: §2.5 measures `round-3-findings.md` / `round-4-findings.md` resolving to the committed
  witness fixtures at `eval/ledger-return-protocol/tier2-fixtures/{j,m}/` (both verified present on
  `dd06b80`), so the broken build resolves where the pin asserts nothing outside the root is reached.

  ⚠ **T3's fixture root MUST sit *inside* a git checkout. T3 is the one pin §6's
  outside-the-checkout rule does not reach, and building it the way §6 says would make it
  vacuous.** A fixture root outside every checkout has `_git_toplevel(root) is None` — verified on
  `dd06b80`: `_git_toplevel(<a fresh /tmp dir>) -> None`, and `_allowed_bases([<that dir>])` returns
  the root alone, where `_allowed_bases([tier2-fixtures/p1])` returns the root **plus
  `/mnt/coding/Coding/crucible`**. A C′ build — one that rglobs "each root's git toplevel" — then has
  **no toplevel to rglob** and behaves identically to correct C, so **T3 goes green against the exact
  build it was written to catch.** Being inside a checkout is what gives C′ a toplevel to reach for
  and is therefore what makes the broken copy discriminate. §6's sentence has been narrowed
  accordingly; T3 is a carve-out (§6) and is named there — T11 is the other (§5).

  **Second leg — NEW: a walk hit that fails containment is discarded, not counted.** Plant,
  inside a supplied root, an in-tree **symlink whose target escapes the containment union** — i.e.
  lies outside **both** the root **and** that root's git toplevel, not merely outside the root —
  named so it collides with a second in-root file of the same basename. **This has to clear the
  whole union, not just the root, because of the ⚠ immediately above: T3's fixture root sits
  *inside* a git checkout, so a symlink target that is merely outside the root but still inside that
  checkout is still `_contained` (it resolves under the root's git-toplevel base), and the correct
  build raises the ambiguity hard-FAIL this leg exists to rule out on exactly that construction — the
  identical conflation of "escapes the root" with "escapes the union" the document's own §3.1 wording
  warns against, in the opposite direction.** The pin asserts the escaping hit is dropped by
  `_contained` and the name therefore resolves to the one legitimate file at exit 0 — **not** an
  ambiguity hard-FAIL on 2 hits, and **never** a read through the symlink. **Broken copy (DEC-31):**
  the walk as the adopted measurement wrote it — `for p in root.rglob(base): if p.is_file():
  hits.add(str(p.resolve()))`, with **no `_contained` test at all** (`codegate_nested_rules.py`,
  §10) — which counts 2 hits and raises. **Negative, stated because it is where an earlier draft's
  fixture failed: a fixture whose symlink target is inside the checkout is a mis-built fixture, not a
  broken build** — such a target stays `_contained`, so the correct build and the no-`_contained`-test
  broken copy both count it and both raise, and the leg fails to discriminate for a reason unrelated
  to the copy's own logic. This leg exists because clause 2 introduces a **new
  candidate source** and an `rglob` is a strictly larger, receipt-controlled surface than clause 1's
  literal join, so the #397 guard matters more there, not less.
- T4, T5 — **moved to #530** (floor pins: 12-hex counted in the floor; the floor exactly as §3.5-F states it).

- T6 — regression pin: an unresolvable path-shaped artifact still fails under `--strict`.
  **Broken copy (DEC-31):** a build that drops the `--strict` path-shaped raise
  (`rcpt_verify.py:1696-1705`) and lets the name degrade to `UNVERIFIABLE` at exit 0 — the shipped
  non-`--strict` disposition, promoted. **The fixture must be constructed, and an earlier draft's
  named discriminator does not discriminate.** That draft used `corpus17/rcpt-18-asreturned.txt`,
  *"whose three path-shaped `ARTIFACTS` names hard-FAIL today"*. At the linter those names are never
  probed: `rcpt-18` raises first on `fix-journal.md`'s sha256 mismatch (measured on the pre-split
  §1.3, now #530), so it exits 1 under
  the **broken** build too and the pin goes green on the build it was written to catch. The only
  receipt of the 68 whose *first* raise is the path-shaped one is `live29/rcpt-2`, and it also exits
  1 without `--strict`, on the `SUPERSEDES` witness-evidence requirement — so **no frozen-corpus
  receipt discriminates this copy**. The repaired fixture is constructed, in a root **outside** the
  checkout per §6 — one resolving artifact beside one path-shaped absent name, `SUPERSEDES: none` —
  and measured at the CLI on `dd06b80` both ways:

  ```
  --strict (the rule)  : Tier-2 --strict: path-shaped artifact docs/plans/absent-path-shaped.md
                         absent under all bases
                         artifacts 1/2 witness 0/0 unreached 1 … partial             EXIT=1
  no --strict (broken) : UNVERIFIABLE: docs/plans/absent-path-shaped.md (no file under root)
                         artifacts 1/2 witness 1/1 unreached 1 …                     EXIT=0
  ```

  The pin demands exit 1 and the broken build exits 0, so the copy genuinely fails.

  ⚠ **T6's regression pin is defeated by a line T6 does not look at, until I8/T10 lands.**
  Appending one `(none)` line to that same fixture receipt empties `ARTIFACTS` before the
  path-shaped name is ever probed, so the `--strict` raise T6 asserts never runs and the receipt
  exits **0** with `artifacts 0/0` and every counter clean — measured at the CLI on `dd06b80`, the
  two receipts differing by exactly one line (§3.4 channel 5). T6 therefore pins the raise against
  *one* way of removing it and not against the cheaper way. **The cheapest close is a one-line
  fixture change, not T10.** The defeat exists only because the constructed fixture's witness does
  not cite its own declared artifact; give the fixture the **mandated** ranged-grep witness on its
  resolving artifact (`red-team-prompt.md:193`'s shape) and the shipped #474/D6 rule
  (`rcpt_verify.py:889-894`) raises at **Tier-1** on the `(none)` receipt before the `--strict` raise
  is reached — verified at the CLI on `dd06b80`, both orderings. **T6 MUST be built that way**: it
  costs no code, no invariant and no pin, and §2.5's preference for pins that exercise production
  shape argues for it on its own. T10 remains wanted for the shapes D6 does not reach, but T6's
  greenness no longer depends on T10 landing with it.
- T7 — **NEW, two legs, because the note is keyed on resolution depth and not on which clause
  resolved.** **First leg:** a name that clause 1's literal join misses and C's walk resolves emits
  `RESOLVED-BY-WALK: <name> (<relpath-from-root>)` and bumps `resolved-by-walk`, which is reported
  and is **not** summed into the floor. The pin's fixture is the 63 % class itself: a
  `round-N-findings.md` one directory below the probed top level, i.e. a live
  `quality-gate/SKILL.md:312` violation, which must remain **countable** after C. Per DEC-31 the
  broken copy is a build in which the walk resolves and returns no note — the exact silent-success
  shape §3.4 channel 2 forbids — and T7 must fail against it before it is trusted green. **Second
  leg — NEW, §3.4 move 1's own remedy.** A **clause-1** root-relative citation one directory down —
  `out-N/round-N-findings.md`, move 1's recommended form — MUST emit the identical note and bump the
  identical counter, with no walk involved. **Broken copy (DEC-31): a build that fires the note on
  walk resolutions only**, the shape §3.1 clause 2 specified before this leg — it would let move 1's
  own recommended citation resolve clean with no note, which is the silent fail-open channel 2 exists
  to prevent, reached through the remedy this document recommends rather than through C.
- T10 — **NEW, and widened to a third leg for `parse_claims`, on top of the second leg for
  `parse_trace`** — a `(none)` line **co-occurring
  with any `ARTIFACTS` entry** is a Tier-1 `LintError` (I8); `(none)` **alone** remains the legal
  empty-set sentinel. **Broken copy (DEC-31): the shipped build itself** — `rcpt_verify.py:240-241`'s
  `return {}`. **Measured on `dd06b80`, which makes this the second of the retained copies with a
  real discriminating run** (T6 is the other). At the parser:

  ```
  parse_artifacts(['a.md sha256:…  10','(none)','b.md sha256:…  20'])  -> {}   # both entries lost
  parse_artifacts(['a.md sha256:…  10','b.md sha256:…  20','(none)'])  -> {}   # both entries lost
  ```

  **The identical assertion binds `TRACE` and `parse_trace` (`:259-260`)**, against the identical
  shipped defect (`return []`). Measured directly on `dd06b80`:

  ```
  parse_trace(['1 READ a.txt sha256:…', '2 WROTE b.txt sha256:…'])              -> [<2 entries>]
  parse_trace(['1 READ a.txt sha256:…', '2 WROTE b.txt sha256:…', '(none)'])    -> []   # both lost
  parse_trace(['(none)', '1 READ a.txt sha256:…'])                              -> []   # both lost
  ```

  **The identical assertion binds `CLAIMS` and `parse_claims` (`:352-353`)**, against the identical
  shipped defect (`return []`, carrying the identical trailing comment as `parse_trace`'s). Measured
  directly on `dd06b80`:

  ```
  parse_claims(['fatal-fixed=2 from=x.md#L1-L5', 'significant-fixed=6 from=x.md#L1-L5'])
                                                                                  -> [<2 entries>]
  parse_claims(['fatal-fixed=2 from=x.md#L1-L5', '(none)'])                      -> []   # both lost
  parse_claims(['(none)', 'fatal-fixed=2 from=x.md#L1-L5'])                      -> []   # both lost
  ```

  A `(none)` here also empties the list the `CLAIMS`-citation guard (`:923-939`) iterates, so that
  guard cannot fire either (§3.4 channel 5).

  And at the CLI, on the constructed T6-shaped root (one resolving artifact + one absent path-shaped
  name, `--strict`, root outside the checkout):

  ```
  honest        : artifacts 1/2 … unreached 1 … partial      EXIT=1
  + "  (none)"  : artifacts 0/0 … unreached 0 …              EXIT=0
  ```

  The pin demands a Tier-1 `LintError` on the second receipt; the shipped build returns exit 0 with a
  clean census, so the copy genuinely fails. **Both orderings must be pinned** — `(none)` before the
  entries and after them — because the defect is an unanchored `return` inside the loop and a fix
  that only skips a *trailing* `(none)` leaves the leading case live.

  ⚠ **T10's CLI-level discrimination depends on a fixture property that must be stated, or the pin
  is vacuous.** The fixture receipt's `WITNESS` **MUST NOT** be a ranged `kind=grep` on a declared
  name, its `CLAIMS` **MUST NOT** cite one, and its `TRACE` **MUST NOT** carry an `EXEC out=` naming
  one — because each of those is a **shipped** Tier-1 membership rule that already raises on a
  `(none)`-carrying receipt (`rcpt_verify.py:889-894`, `:923-939`, `:897-902`), so a T10 fixture
  written from the canonical worked-example receipt at `red-team-prompt.md:297` **passes green
  against the exact build it names as broken** — for the wrong reason, on the wrong rule. (An earlier
  draft cited `:294`; re-run on `dd06b80`, the worked example's `READ` line is at `:297` and `:294`
  points inside its `ARTIFACTS` block.) Measured on `dd06b80`: injecting `(none)` into any of the 68
  frozen receipts is rejected 68/68 in both orderings by those rules alone. The parser-level legs
  above are unaffected and stay the pin's primary evidence; it is the **CLI** leg that carries this
  hazard. **The `TRACE` leg inherits the identical hazard, plus one more**: a fixture whose `WITNESS
  ran=` cites `TRACE#<n>`, or whose `CLAIMS` cites `TRACE#<n>`, or whose `CLAIMS` carries
  `tests-ran`/`tests-pass` with an `EXEC` entry, each independently raises once `TRACE` is wiped
  (`ran=TRACE#N does not resolve`; `CLAIM citation TRACE#N does not resolve`; the mandatory-work check
  at `:971-978`) — for the wrong reason again. **The `CLAIMS` leg inherits the identical hazard from
  the opposite direction**: a fixture whose `CLAIMS` body is what gets wiped is indistinguishable, at
  Tier-1, from one whose `CLAIMS`-citation guard (`:923-939`) itself raises on the wipe (§3.4 channel
  5) — the same wrong-reason failure, one section over. The `TRACE` and `CLAIMS` legs' CLI-level
  construction is therefore
  scheduled alongside the `ARTIFACTS` leg's, on the same avoid-list, widened by these four; it is not
  separately measured here (the parser-level legs above are). Stated here because it would
  otherwise be this arc's **fourth** DEC-31 vacuity, in the pin AC-6 calls *"the cheapest evidence in
  this document and also the most damning"*.
- T8, T9 — **moved to #530** (floor pins: clause (1) reason-code rule; the floor's bucket domain).
- T11 — **NEW — the false-positive-verification gap (§3.4's silence-adjacent seventh channel).**
  **Invocation and exit-code contract, stated precisely — an earlier draft left both to the
  implementer, and the naive reading fails in independently reproducible ways that silently
  under-report the exact invariant this pin exists to enforce.** The subprocess call MUST be
  `git -C <toplevel> ls-files --error-unmatch -- <relpath>` (I2) / `git -C <toplevel> check-ignore
  -- <relpath>` (I3), or the Python `subprocess.run(..., cwd=toplevel)` equivalent — never a bare
  relative pathspec run from whatever cwd the linter process happens to have. Reproduced: `git
  ls-files --error-unmatch CLAUDE.md` from `skills/` (a subdirectory of this repo, not the
  toplevel) against a file tracked at the repo root → exit 1, "did not match any file(s) known to
  git" (a **false** "not tracked"); the identical command from the toplevel, or with `-C`, → exit
  0. Reproduced: the identical command from `/tmp` (no `.git` above it) → exit 128, "fatal: not a
  git repository" — a **different** signal a bare `returncode != 0` check would collapse into the
  same bucket as a legitimate "not tracked." Reproduced: `git ls-files --error-unmatch -rf` (no
  `--` separator, a resolved realpath that happens to start with `-`) → exit 129, "unknown
  switch" — the `--` above is what prevents this. **Exit-code taxonomy:** `0` = match (Tier-2
  hard-FAIL under `--strict`); `1` = no match for either tool (proceed); any other code — `128`,
  `129`, or an `OSError`/`FileNotFoundError` if `git` is not on `PATH` — is reported as its own
  diagnosable disposition, never silently folded into "no match," mirroring how `_refused_clause`
  names a refusal distinctly elsewhere in this document rather than treating it as absence. **The
  disposition, stated rather than left to "reported" alone (D3 — Edge Cases F3): fail-CLOSED, not
  fail-open.** Any code outside `{0, 1}` — a degraded git environment T11 exists to reach, per §3.1's
  own portability paragraph (WSL drvfs, a `chmod -R 777` devcontainer, a umask-000 clone) — is a
  Tier-2 hard-FAIL under `--strict`, on the same terms as the `0` (match) case, but with its own
  distinct message (`I2/I3 check unavailable: <tool> exited <code> (<reason>)`) so a maintainer can
  tell "verified violation" from "could not check" apart. **The alternative (proceed) was considered
  and rejected**: T11 exists to close a false-verified-clean channel, and degrading to "proceed" in
  exactly the environments this document already names as real would silently re-open that same
  channel wherever git itself is degraded — the identical shape T11 was built to arrest, reached
  through T11's own error arm. This is a named addition to the new-hard-FAIL-class count (§5, I7), not
  a silent fail-open — an implementer building T11 should test this arm directly, alongside the three
  legs already specified; this document does not attempt AC-6's full pin/copy recount for this
  addition here, since a dedicated DEC-31 copy for it is a natural next round's addition, not asserted
  here as already counted.
  **First leg, I2.** A tracked repo file cited by repo-relative path, linted against a root whose
  git-toplevel base contains it (§2.8 item 4's shipped shape), MUST hard-FAIL at Tier-2 under
  `--strict`, naming I2 as the violated invariant — not resolve, hash-verify and lint clean.
  **Broken copy (DEC-31): the shipped build itself, like T10 — no construction needed.**
  `tier2_artifacts` contains no tracked-ness check anywhere in its 145-line body (measured:
  `sed -n '1806,1948p' scripts/rcpt_verify.py | grep -c 'git\|tracked\|gitignor\|ls-files\|check-ignore'`
  returns `0`), so it resolves via clause 1's literal join through `_allowed_bases`'s git-toplevel
  probe, hash-matches, and reports `artifacts 1/1`, exit 0 — **measured at the CLI, not only at
  `resolve_base`**: a constructed receipt declaring `scripts/rcpt_verify.py` in `ARTIFACTS`, linted
  at Tier-2 under `--strict` against `eval/ledger-return-protocol/tier2-fixtures/p1` (a root inside
  the checkout), reports `TIER2-COVERAGE: artifacts 1/1 witness 1/1 … all counters 0`, `EXIT=0`
  (§3.4, channel 7). This is the exact shape T11 must fail against. **Second leg, I3.** The identical
  assertion for a gitignored path-shaped name resolving the same way, checked with `git
  check-ignore` instead of `git ls-files`; broken copy is the same shipped build, and the identical
  CLI construction with `docs/plans/2026-02-23-iterative-red-team-design.md` (gitignored,
  path-shaped, not the artifact under review) in `ARTIFACTS` in place of the tracked file reproduces
  the same `artifacts 1/1 … EXIT=0` (§2.8 item 3 already half-notes the resolution half of this leg
  without drawing the enforcement conclusion). **Third leg — NEW: the identical check at
  `tier2_witness`'s (`:2633`) resolved branch, for the leg the first two never reach.** T11's first
  two legs patch only `tier2_artifacts`; `tier2_witness` reaches the identical
  `_allowed_bases`-git-toplevel-probe resolution independently — it calls its own `resolve_base`,
  not `tier2_artifacts`'s — and a **rangeless** `kind=grep` witness is exempt from the #474/D6
  `ARTIFACTS`-membership rule (`:886`, *"Scoped to ranged payloads"*), so its cited name is read
  straight off the `TRACE` entry's args with no `ARTIFACTS` declaration required at all. A rangeless
  grep witness naming a tracked repo file or gitignored path by repo-relative path, against a root
  whose git-toplevel base contains it, MUST hard-FAIL the same way the first two legs do, naming I2
  or I3 — not resolve, read and lint clean. **Broken copy (DEC-31): the shipped build itself, the
  same shape as the first two legs** — verified: `tier2_witness`'s body calls `resolve_base` through
  the same probe and contains no `ls-files`/`check-ignore`/tracked-ness/gitignore check of its own,
  so this leg's broken copy needs no construction, the same way the first two legs' does not. **The
  fixture root MUST sit inside a git checkout, for all three legs** — the same carve-out T3 needs and
  for the identical reason (§6): a root outside every checkout has `_git_toplevel(root) is None`, so
  there is no toplevel for any of the three legs' checks to reach, and a fixture built the way §6's
  general rule says would go green on the exact broken build each leg is meant to catch.

## 6. Test-surface hazard — the committed fixtures cannot pin this

`eval/ledger-return-protocol/tier2-fixtures/` roots `p1`/`p2`/`p3` sit **inside the crucible
checkout**, so `_git_toplevel(p1)` returns the repo and the repo becomes a **live probed base**:

```
resolve_base('scripts/rcpt_verify.py', p1) -> /mnt/coding/Coding/crucible/scripts/rcpt_verify.py
resolve_base('CLAUDE.md',              p1) -> /mnt/coding/Coding/crucible/CLAUDE.md
```

Both mandated **production** roots have `toplevel None`. **The committed fixture suite therefore runs
in a probe configuration no production invocation has**, cannot reproduce the production residual,
and cannot regression-pin any rule about repo-relative names.

**Narrowed here, because stated unqualified the rule makes one of its own pins
vacuous.** The rule, restated with the discriminating condition made explicit:

> **A pin whose assertion is about the *correct* build's disposition needs a fixture root OUTSIDE
> every checkout** — otherwise the repo is a probed base, the pin runs in a configuration no
> production invocation has, and it reports a resolution or a success production cannot have.
> **A pin whose *broken copy* is defined by reaching the git toplevel needs its root INSIDE a
> checkout** — because with `toplevel None` that copy has nothing extra to reach and stops being a
> distinct build at all.

**T1-neg, T6 and any pin measuring the production residual are in the first class, and all say so.**
**T3 was, until T11, the only pin in the second class. T11's own broken copy (§5) is defined the
identical way — a resolution reached through `_allowed_bases`'s git-toplevel probe — so T11 needs
its root inside a checkout for the same reason T3 does, and the carve-out now names two pins, not
one.**

⚠ **Applying the unqualified rule to T3 makes T3 green against the exact build it was written to
catch.** An earlier draft wrote *"Any such pin"*, with no carve-out, and T1-neg — the pin immediately
above T3 in §5 — restated it as a construction requirement for its own fixture, which established the
unqualified reading as this document's intent. But T3's discriminator is the opposite one: a C′ build
reaches the repo through **`_git_toplevel(root)`**, and a root outside every checkout returns `None`
there — verified on `dd06b80` (`_git_toplevel(<fresh /tmp dir>) -> None`;
`_allowed_bases([<that dir>])` returns the root alone, where `_allowed_bases([tier2-fixtures/p1])`
returns the root **plus `/mnt/coding/Coding/crucible`**). So C′ has nothing extra to rglob and
behaves identically to correct C. **T3 needs its root inside a checkout.**

That is not a hypothetical hazard. AC-6 recorded that two vacuous DEC-31 pins had been found in this
arc *"by re-measuring at the linter rather than by reading the prose … neither was visible from the
text"*, and warned that the then-**five** unmeasured copies carried the same risk. **T3 was one of
those five, and its vacuity was not merely unmeasured — it was *entailed by this section's own
instruction*.** AC-6 now records three vacuous pins, not two.

Related, and worse for enforcement: **no Crucible hook is registered on this machine at all.** No
`hooks` key in either repo-local settings file (`.claude/settings.json`,
`.claude/settings.local.json`) registers any Crucible hook, and the user-level
`~/.claude/settings.json` registers none either — a form stated this way so it does not need
re-chasing as the user-level file's own registered key set changes round to round (re-checked
2026-08-24: it currently registers only `Notification`). #520 names
`gate-ledger-guard.sh`; the measured fact is that `build-routing-advisor.sh` and `rcpt-verify-hook.sh`
are unregistered too, and `rcpt-verify-hook.sh:7` is `--tier1`-only and "PURE OBSERVER, NEVER FATAL"
by design. **Every rule in this ruling is enforced solely by an LLM reading Markdown and choosing to
obey it.** A rule that is cheap to state but easy to get subtly wrong has no backstop.

**This document proposes five new binding ordering-gate MUSTs (§3.1 clause 2's #530-or-`:36` gate, the
second gate on I2/§3.2's rollout, the third gate on I4's rollout at §5, T7 leg 2's fourth
constraint on move 1's citation form, and T7 leg 2's own fifth constraint — §4's (i), the 12
full-literal-counter-list `TIER2-COVERAGE` assertion rewrite, and (ii), `:36`'s reader tolerance, §4)
into exactly this enforcement vacuum, and it
has two independent measurements of the base rate to weigh them against and stated neither beside the
gates until now (B1 — Blind Spots F2).** The `:968` write this document's own I4 remedy depends on is an
**existing**, unconditional MUST, and it has run **zero of fifteen times** since round 1 of the gate
reading these words (rounds 2–16; §5, I4; §3.3). The predecessor gate measured the same obligation at
**4 of 6 rounds non-compliant** (§5). No AC, pin, grep or CI check covers any of the five new gates
either — the same absence that let the existing MUST run at 0/15. A maintainer reading "**MUST NOT
ship until X**" five times in this document should read each as a disclosure with the same enforcement
odds as the write that has already failed fifteen times in a row, not as a mechanical block. **AC-9
(§8, added this round) is what retracts this paragraph's implicit resignation rather than merely
restating it**: it obliges a `scripts/check_488_gates.py` guard, on the `check_rt_receipt_contract.py`
precedent, that asserts the ordering XOR for each of the five gates named above — text only in this
pass, a tracked future obligation, not yet the mechanical block this paragraph says does not exist.

Also uncontrolled: `scripts/measure_486_corpus.py` is **not** in `scripts/run_tests.sh`, and the
three corpora live under `~/.claude/projects/…`, not in the repo. No corpus figure is CI-gated on any
machine but this one, so "a corpus re-frozen to pass is not evidence" has no mechanical guard.

## 7. #519 — what this ruling does and does not discharge

**Satisfied:** the constraint was visible when the decision was taken.

**Not discharged, and the doc says so plainly.** Bounding evidence to a dispatch-owned directory is
mildly better for re-execution than a repo path — a patch or log is replayable in a clean tree where
a path at HEAD is not — but the ruling touches **none** of #519's stated substance: *who* re-runs the
witness without handing a contained producer the orchestrator's privileges (#519: *"it may be the
whole problem"*), recoverability of cwd and inputs, or a declared class for legitimately
non-deterministic witnesses. **c1 must not be read as having answered #519.**

## 8. Acceptance criteria

⚠ **Which of these are reachable within this ticket, stated here because §8 is the section a
maintainer reads to schedule the work and an earlier draft left the answer only in §9.** C's
implementation is gated on **#530** per **OQ-7** and §3.1 clause 2, so **AC-4 and AC-6's
C-dependent pins (T1, T1-neg, T3, T7 leg 1) cannot be satisfied before that gate clears.** **T7's
second leg is not one of them in the #530 sense** — the clause-1 depth half of `RESOLVED-BY-WALK:` and
its `resolved-by-walk` sub-count needs no walk and does not wait on #530 (§5, T7) — **but it is not
schedulable today either, on separate grounds (G1, corrected):** landing T7 leg 2 itself (the
`resolved-by-walk` census field) MUST NOT ship until the 12 full-literal-counter-list `TIER2-COVERAGE`
assertions among `scripts/test_rcpt_verify.py`'s 76 references to that string are rewritten in the
same change and `:36`'s reader is confirmed to tolerate
the new field — a fifth ordering constraint (§4, §5), gated here as
plainly as it is gated where G1 landed it. **OQ-11, which this section previously listed as a third
ground, is withdrawn (§9): the `--eval` byte-diff contract is measurably unaffected by a new census
field, so both of the fifth constraint's remaining conditions are mechanical, in-scope implementing
work — T7 leg 2 is therefore schedulable within this ticket's implementing change once the 12
assertions are rewritten in the same change, not blocked on an outstanding maintainer decision.**
Separately, and on top of that: `:222`'s
root-relative-citation half (below, and §4's `red-team-prompt.md` row) MUST NOT ship ahead of T7 leg 2
either — a fourth, distinct ordering constraint, in the same shape as the other three. The
**C-independent** criteria — the ones this half can be scheduled and finished on today — are
**AC-1's first half** (below — a tautology satisfied by this document's own existence, not real
completable work; counted as one of four schedulable items but contributing zero producer-facing work,
E4, below), **AC-2** (the lexical grammar plus I8/T10, **all three parsers**), **AC-6's T2 and T6**, and **AC-7** —
four items, of which AC-1's first half is already discounted to zero above.
**AC-6's T7 leg 2 is gated per the fifth constraint just stated, and T11 is neither listed here nor
among the C-dependent set above — its scheduling is OQ-9, not decided in this document.** Read AC-4
as the acceptance figure C must hit *when* it is built, not as work this ticket can close.

**Stated plainly, because §8 is the section a maintainer schedules from (A3 — Integration Impact F5).**
Walking the C-independent list against this document's own consumer model (§3.1 clause 2, §6), none of
it changes any receipt's disposition at `quality-gate/SKILL.md:36` — the consumer this document names
as the only one. AC-1's first half records the ruling; AC-2's lexical clauses reject nothing any
production receipt or committed fixture declares (§3, *Lexical grammar*); AC-7 posts corrections to a
GitHub issue; T6 is a regression pin; T2's note and T7 leg 2's counter are both real code, but `:36`
reads neither — `resolved-by-walk` is a name `:36` does not read (above), and `PROVENANCE-ONLY:` bumps
no counter at all (F2, above). **The schedulable-today slice is therefore a no-op at this document's
own named consumer.** That does not make it valueless — hardening, regression coverage and an honestly
stated grammar have their own worth — but this document should not be read as delivering a live
behaviour change to `:36` before #530 rules, and an earlier draft of this section never stated that
plainly.

**None of
the seven live criteria below (items 3 and 5 are tombstones for criteria that moved to #530) covers
most of §4's edit surface.** Uncovered: authoring the
fix-agent prompt; wiring it into the fix dispatch; `red-team-prompt.md`'s **I4-bearing** edits
(`:184`, `:297`, `:329` — §4; its `:222` edit is covered, below); the
`return-convention.md:68` `ARTIFACTS`-grammar row's semantic half (**AC-1's first half**, below,
covers only that it is recorded); the `siege`/#496 root row; the `:758-760`/`:968` I4 row (the third
ordering gate, §5); the `dispatch-convention.md` `Inputs:` field; `return-convention.md`'s own
`12-judge` worked-example row (`:291-383`/`:533-578` — §4, also I4-bearing); and the orchestrator
input-coverage report. **Now covered, by AC-8:** the fourteen probe-set / "no search" /
cross-root-ambiguity prose sites C falsifies (`build:14`, `siege:21`, `quality-gate/SKILL.md:30`,
`:52`, `:54`, `:56`, `:291`, `:312`, `:784`, `:951`, `return-convention.md:104`, `:135`, `:256`,
`red-team/red-team-prompt.md:222`) — eleven by the **conjunction of two** greps (`"no search"`, 9
sites; `"never a false FAIL"`, `build:14` + `siege:21`) and the remaining three (`:54`, `:56`,
`return-convention.md:135`) by an explicit by-hand sign-off. **Consequence for #513, stated because the header calls it folded (E2 — Scope
Clarity F2): the fix-agent prompt is where #513's ruling lands (§4), and no acceptance criterion
mentions authoring or wiring it. Satisfying all nine criteria below is therefore compatible with
#513 remaining completely unaddressed — "the criteria are met" and "#513 shipped" are independent
facts, not the same milestone under two names, however the header's "folds #513 deliberately" reads
at a glance.** Of those, the fix-agent prompt's authoring and wiring and
`red-team-prompt.md`'s edits are not one milestone with one schedule, per
§3.1 clause 2's split: **authoring** the fix-agent prompt file and **merging** the
`quality-gate/SKILL.md` dispatch-input line that wires it in are separable — the file may be
authored and merged today (C-independent), while the wiring line MUST NOT be added until the
#530-or-`:36` gate clears. **That gate is blocked on #530 in practice, not merely guarded by a
prospective safeguard**: its only self-serviceable exit, horn (b), is measurably net-negative (§3.1
clause 2 — zero flips prevented, 26 receipts moved from verified to permanently UNVERIFIED under the
withdrawn published `codegate22` layout, **12 under the decision real-nested layout** — §2.1, §3.1
clause 2), so an implementer scheduling from this section should read the wiring line as waiting on
#530. **The
`return-convention.md:104`/`:256` retraction is gated on the identical terms, and is the larger of
the gate's two rollout vectors** — §3.1 clause 2 names it explicitly (this round; an earlier draft
named only the fix-agent-prompt wiring) because the convention is already the live document its six
adopting skills (§3.1 clause 2) consume, so editing it has no authored-but-unwired middle state the
way the fix-agent-prompt file does; the edit itself, not some downstream wiring step, is what this
gate withholds. **Editing `red-team-prompt.md` is split by the third ordering gate (§5, I4), the same
way `:104`/`:256` are split by the second.** Neither half of `:222` is #530-gated: §3.1 clause 2's
second ordering gate binds only I2/§3.2's rollout (the fix-agent-prompt wiring and the
`return-convention.md` retraction), and this row rolls out I3/§3.3, which is not #530-gated because
§3.3 compliance is a genuine verification, not a flip (§3.1 clause 2). But `:222` itself splits, and
only one half is conditionally schedulable today: its **root-relative citation** half (§3.4 move 1)
is shipped behaviour today, but MUST NOT ship to producers until the clause-1 depth half of
`RESOLVED-BY-WALK:` and its `resolved-by-walk` sub-count (T7 leg 2, §5) has landed — a fourth
ordering constraint, stated in the same shape as the other three: shipping the citation without the
counter reproduces the exact silent fail-open channel 2 exists to prevent, on the 63 % dominant
class (§3.4). T7 leg 2 needs no walk and this fourth constraint does not wait on #530 — **but it is
not unconditionally satisfiable before C either**: T7 leg 2 itself (the `resolved-by-walk` census
field) MUST NOT ship until the 12 full-literal-counter-list `TIER2-COVERAGE` assertions among
`scripts/test_rcpt_verify.py`'s 76 references to that string are rewritten in the same change and `:36`'s
reader tolerates the new field — the fifth ordering constraint, both conditions mechanical (OQ-11
withdrawn, §9),
above. Its **within-root-walk** half describes C itself and MUST
land in the same change that lands C, per AC-8. **`:184`'s `artifact-N.md` clause,
the `:297`/`:329` worked-example `READ`/`ARTIFACTS` lines, `return-convention.md:68`'s §3.3
clause, and `return-convention.md`'s own `12-judge` worked example (§4) are all I4-bearing and MUST
NOT ship until
§4's `:758-760`/`:968` row has landed** (§5, I4) — an orchestrator-side precondition this document
does not schedule as done today, and the gate reading these words is the measured instance of what
shipping the I4-bearing half first produces: a copy of `artifact-N.md` that either does not exist
(`not-reachable (unresolvable-basename)`, UNVERIFIED) or is stale and hash-vouches for bytes that are
not the artifact reviewed (§5, I4). The file remains the dispatch body itself, so whichever half
ships must be reviewed and merged with that in mind, not that it is a single schedulable unit.

1. **Split by the second ordering gate (§3.1 clause 2), above.** The ruling in §3 is recorded —
   schedulable today; recording carries no producer-facing instruction. **Stated plainly (E4 — Scope
   Clarity F5): this half is satisfied by the artifact's own existence — true the moment this document
   exists, verified by observing §3 is present rather than by any producer completing work.** It is
   real in the sense that recording the ruling was itself part of the ticket, but counting it as
   schedulable/completable work beside AC-2's, T2's and T6's actual code changes (§8's opening
   note; T7 leg 2 is gated by the fifth ordering constraint and is not in this slice) overstates
   how much of the C-independent slice is real work; a maintainer sizing the
   today-schedulable half should discount this item's contribution to zero rather than one-of-four.
   **"Recorded" means recorded
   in this document, not written into `return-convention.md:68`** — that row is itself split (§4):
   its lexical half is ungated, checkable-by-inspection prose, and its semantic half lands with the
   `:104`/`:256` retraction, on this gate's terms. `return-convention.md:104`
   + `:256` no longer contradict — **gated**; this edit MUST NOT be made until #530 rules OQ-7 or
   `:36` is amended in the same change.
2. **Re-scoped — it now names one half and one site per parser, and the enumeration below is the
   enforcement set, not a restatement of the grammar.** The **lexical** grammar of §3 (*Lexical
   grammar*) is stated, and **`parse_artifacts`, `parse_trace` and `parse_claims` validate that half
   and only that
   half, one parser per body**: for `ARTIFACTS`, relative, no leading `/`, no NUL, `(none)` legal
   only as the sole entry; for `TRACE` and `CLAIMS`, `(none)` legal only as the sole non-blank line —
   **I8, all three parsers** (`rcpt_verify.py:240-241`, `:259-260` and `:352-353`), widened from an
   earlier draft that closed only
   the `ARTIFACTS` half of this identical defect, an under-inclusion §3.4 channel 6 grades as
   **wider** than the `ARTIFACTS`-only reading — and `CLAIMS`'s own copy of the same gap (found this
   round) is wider still, because emptying `CLAIMS` also defeats the `CLAIMS`-citation guard that
   narrows channel 5's exposure — **the `..` clause is producer-normative
   only and is deliberately NOT enforced here** (§3, *Lexical grammar*): it is redundant for safety
   against `_contained`'s realpath containment test, and landing it retires **siege S-3**, a security
   regression pin this ruling declines to re-author for a grammar-only benefit — a faithful
   substitute fixture exists (§3 states it and states why that is not the reason). The **semantic**
   half — resolution under the supplied roots
   (§3.1), the tracked-file rule (§3.2), the gitignored rule (§3.3) — is enforced at
   **`tier2_artifacts` (`rcpt_verify.py:1806`)**, because `parse_artifacts` runs inside
   `lint_receipt(text)` at `rcpt_verify.py:872` with no root, no git handle and no filesystem in
   scope and **cannot evaluate any of them**. **This names where the check MUST live, not that it
   already does for all three clauses it lists — an earlier draft's single present-tense sentence
   here covers §3.1 correctly and is false for §3.2/§3.3 today.** Verified directly (§3.4, channel
   7): `tier2_artifacts`'s body contains zero tracked-ness or gitignore-status checks. §3.1's
   resolution requirement (I1) genuinely is enforced there — an unresolvable name fails exactly as
   this criterion describes. §3.2's and §3.3's rules (I2, I3) are not: a tracked repo file or
   gitignored path-shaped name cited by repo-relative path against a root whose git-toplevel base
   contains it resolves, hash-verifies and lints clean at that same site today, which is the
   opposite of enforcement. **T11 (§5) is the specified, not-yet-built, remedy** that makes this
   sentence true of all three clauses rather than one. The earlier wording (*"`ARTIFACTS` `<name>`
   has a stated grammar; `parse_artifacts` validates it"*) was unsatisfiable under both readings —
   see §3 for the two horns. An earlier draft of this criterion listed `..` alongside the other three
   clauses as if all four landed here; that is the same defect in a new form, and a later draft
   corrected that over-inclusion without checking the criterion for the matching under-inclusion —
   this criterion is what an implementer schedules from (§8), so both defects land the same way: an
   implementer who follows AC-2 exactly ships a build where the `ARTIFACTS` half's `(none)` sentinel
   is closed and the `TRACE` half's is not, which is precisely I8's own headline about the earlier
   draft's original error, one parser over. Landing `..` at Tier-1 would also make
   `TestTheWorldWritableRefusalIsMonotone.test_0777_does_not_reach_further_than_0755`
   (`test_rcpt_verify.py:5925-5967`) structurally unreachable while leaving its exit code unmoved (1
   → 1), so a maintainer checking exit codes would see nothing. **Explicitly NOT in AC-2: any
   tracked-ness or path-shape rejection landed in `parse_artifacts`** — that would turn
   `run_tests.sh:102-106` red on 47 committed fixture entries (§4, `eval/ledger-return-protocol/**`,
   and **OQ-8**) and would make T6's `--strict` branch unreachable.
3. **Moved to #530** — the pre-registered zero-on-the-floor criterion.
4. **Re-worded: C, once implemented, MUST reproduce `live29` 42 → 14 and
   `codegate22` (real nested) 96 → 2** (§2.3). The withdrawn flat-layout `0` is **not** an acceptance
   figure. **The earlier wording — *"C measured on the frozen corpora under the shipped
   implementation"* — was false in the past tense and is withdrawn.** C is **not shipped**:
   `_resolve_base_one` (`rcpt_verify.py:1320`) is a literal join with no search, and §4's own row
   schedules *"add the bounded within-root walk"* as future work. The figures were produced by the
   throwaway simulations `counterfactual.py` and `codegate_nested_rules.py` (§10), **not** by
   `measure_486_corpus.py`, which §2's header lists as the shipped instrument — so a reader taking
   the phrase at face value attributes the number to the wrong instrument, which is the specific
   error the header of this document warns about.

   **Two stated divergences between the simulation and any faithful implementation, so an
   implementer can tell a failed acceptance from a corrected one.** The simulations (i) match
   **path-shaped names by basename** and (ii) apply **no containment test** to walk hits. §3.1
   clause 2 now rules both the other way. The measured corpora are insensitive to both today
   (`codegate22`'s 96 residual names are 100 % bare; `live29`'s single path-shaped residual resolves
   under neither reading), so **14 and 2 should still reproduce** — but if they do not, **the signal
   is to re-derive, not to adjust the target**, and the first two things to check are the match key
   and the containment test.

   **Falsifiable, not open-endedly re-derivable (E1 — Technical Soundness F4 / Scope Clarity F3):
   "re-derive" is bounded to these two named causes, not to any divergence whatsoever.** If a build's
   reproduction of `live29`/`codegate22` diverges from 14/2 **and** the divergence traces to the match
   key or the containment test — the two shortcuts named above — the simulation's figure, not the
   ruled rule, was wrong, and AC-4's target updates to the correctly-derived number, exactly as this
   document has already superseded several of its own earlier-draft figures elsewhere (§2.5, §3.1). If
   the divergence does **not** trace to either of those two causes — the build reproduces neither 14/2
   nor an explicable variant of them — that is evidence of an implementation defect, not grounds to
   re-derive a third time, and AC-4 is not satisfied. This is what keeps AC-4 a real acceptance test
   rather than a number an implementer can always talk their way out of.

   ⚠ **The reproduction path for this criterion is outside the repo, and its exact location
   matters — an earlier draft named a directory that no longer exists.** That draft pointed at
   `/tmp/crucible-dispatch-1787239343/` and made preserving the instruments off `/tmp` *"an
   obligation of whoever implements C"*. **Both halves are withdrawn.** Measured: that `/tmp`
   directory is **gone**, and the preservation **has already happened** — `counterfactual.py`,
   `codegate_nested_rules.py`, `counterfactual.json` and `census-raw.json` all survive, together with
   the producing dispatch's seq-1–20 files, at
   `~/.claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate/scratch/2026-08-20T09-05-29/dispatch-archive/`.
   **The files survive; most of them do not run.** Eight of the archive's scripts —
   `counterfactual.py`, `residual_census.py`, `population.py`, `check_c_bytes.py`, `name_census.py`,
   `r5_measure.py`, `c_repo_variant.py`, `linter_floor_r6.py` — hardcode the **dead** swept path
   (`/tmp/crucible-dispatch-1787239343/`) as their input, their output, or both; measured on
   `dd06b80`: `python3 counterfactual.py` raises `FileNotFoundError` on that path at its very first
   line, and `residual_census.py` does the same, producing no output. **Ten of the archive's eighteen
   scripts run as-is** — they read the frozen-corpora path directly or take no such path at all,
   rather than going through the dead intermediate — **nine of them with substantive output and no
   edit required.** `codegate_nested_rules.py` is one of the ten, and reproduces AC-4's `codegate22
   (real nested)` column directly (`baseline=96 A=96 B=96 C=2 D=96`); two others among the ten,
   `codegate_nested.py` and `codegate_c_detail.py`, independently corroborate this document's own
   decision-column figures — the `96` residual (79-art / 17-wit split) and the seven-hit
   `artifact-under-review.diff` ambiguity, respectively. **So "use it" is not the operative
   instruction — re-point each hardcoded reference at the archive directory above (or a
   `DISPATCH_DIR` environment override) before running it; `counterfactual.py` in particular hardcodes
   the dead path twice (read and write), so patching only the input still errors at the end.** The
   figures themselves are not in question — re-pointing a **copy** of `counterfactual.py` at the
   archived `census-raw.json` reproduces `corpus17 11 → 10/10/11/11`, `live29 42 → C 14`, and
   `codegate_nested_rules.py` reproduces `baseline=96 A=96 B=96 C=2 D=96`, 77 unique, all exact — the
   defect is in the *"use it"* instruction, not in the evidence it points to. What remains true is
   §6's limit: the corpora live under `~/.claude/projects/…`, not in the repo, and *"no corpus figure
   is CI-gated on any machine but this one"* — so the archive is machine-local evidence, not a CI gate, and a reader
   on another machine cannot re-derive `14` or `2` at all. That is a stated limitation of this
   criterion, not a defect the document can close from inside its own change boundary (§10).

   ⚠ **The corpora themselves are a SEPARATE preserved object from the instruments above, and only
   two of the three sit at one path — an earlier draft's enumerated survivor list never named the
   object at all, and a later fix gave it a single path that is not `corpus17`'s.** `live29` and
   `codegate22` live at
   `~/.claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate/evidence-486-tier2-resolution/frozen-corpora/`
   and are covered by that directory's `SHA256SUMS-frozen.txt` (432 entries; `sha256sum -c` from
   that directory). **`corpus17`'s dispatch root is a sibling directory,
   `evidence-474-tier2-resolution/corpus-2026-08-01/`** (`measure_486_corpus.py:144`, `:211-213`,
   which labels the corpus by that path directly) — `SHA256SUMS-frozen.txt` does **not** cover it
   (`grep -c 'corpus-2026-08-01' SHA256SUMS-frozen.txt` → **0** of 432 entries); only its findings
   root (`frozen-corpora/scratch-2026-08-01T21-18-18/`, 77 of the 432 entries) is covered. A
   byte-identical, receipts-only copy of `corpus17` does sit inside
   `frozen-corpora/corpus-2026-08-01/` with its own separate `SHA256SUMS-corpus17.txt` (18 files: 17
   receipts plus the manifest) — but it is **not** the root `measure_486_corpus.py` reads, and
   `SHA256SUMS-frozen.txt` does not cover that directory either. **They are sweep-vulnerable
   machine-local state**: this arc's own gate measured them absent from their paths mid-run (a sweep
   moved them to `~/.claude/backups/`, along with two protected `active-run` markers) and later
   restored; `live29`'s and `codegate22`'s bytes were byte-verified `432/432` against
   `SHA256SUMS-frozen.txt` — which is precisely §6's *"a corpus re-frozen to pass is not evidence"*
   guard satisfied the right way, **for those two.** Running that same check against `corpus17`
   reports `432/432 OK` regardless of `corpus17`'s own state, because none of the 432 lines names
   its root — a reader who takes it as coverage for all three corpora gets a false all-clear on the
   one it omits. **Timestamped observation, not a standing property** (the self-reference rule this
   document states elsewhere binds this sentence too): re-run at `2026-08-23`,

   ```
   python3 scripts/measure_486_corpus.py --corpus corpus17   --expect-size 17
   python3 scripts/measure_486_corpus.py --corpus live29     --expect-size 29
   python3 scripts/measure_486_corpus.py --corpus codegate22 --expect-size 22
   ```

   returns `rc=0` for all three. **`--expect-size` is required** — `measure_486_corpus.py:502`
   raises usage and returns `rc=2` without it, which is what a bare
   `--corpus {corpus17,live29,codegate22}` invocation hits first, before any corpus-location
   question is reached. A future reader getting `rc=2` has a usage error, not a corpus regression,
   and should supply `--expect-size`; a future reader getting `rc=1` with `SKIP: corpus directory
   absent` has the location failure round 3 originally observed, and only then is checking a
   manifest the right next step — `SHA256SUMS-frozen.txt` for `live29`/`codegate22`, or
   `SHA256SUMS-corpus17.txt` (inside the unused `frozen-corpora/corpus-2026-08-01/` copy, not
   `SHA256SUMS-frozen.txt`) for `corpus17` — before concluding AC-4 has regressed.
5. **Moved to #530** — "no allowlist, no per-name tolerance table, no severity downgrade", and the narrowing recorded against it.
6. Invariants **T1, T1-neg, T2, T3, T6, T7, T10 and T11** pinned — the six retained by the split
   plus **T10 and T11, which are new** — **each leg to be verified by the implementer against a
   deliberately-broken copy (DEC-31)**.

   **Recount, restated rather than inherited: eight pins, twenty copies — earlier drafts
   under-counted this table six times, and none of those superseded counts is repeated here so
   none is left to go stale against the next legitimate addition: four missing legs (the
   truncated-run leg, the escaping leg, T1-neg's second leg, T7's second leg); T11 itself (§3.4,
   channel 7) being found and specified; T11's own witness-leg gap (the identical check at
   `tier2_witness`'s resolved branch, untouched by T11's first two legs) being found and a third leg
   added; T2's sixth leg gaining its second, independently-discriminating broken-copy construction;
   T11's three legs being recounted as two broken-copy builds, not three, under this table's own
   one-slot-per-named-shape convention; and T10 gaining a third leg for `parse_claims`, the identical
   `(none)`-sentinel defect a third parser down (I8).**

   | pin | DEC-31 copies | measured? |
   |---|---|---|
   | T1 | first-hit-wins build; **NEW** single-root-walk / basename-dedup build | no |
   | T1-neg | unconditional-walk build; **NEW** top-level-in-A-nested-in-B unconditional-both-roots-walk build | no |
   | T2 | verb-keyed build; **NEW** literal-string-key build; **NEW** verified-blind basename-key build; **NEW** truncated-run return-by-value build; **NEW** truncated-run `TestNotesSurviveALintError`-transplant (interleaved-emission) build; **NEW** raw-`args`-interpolation (unescaped) build | leg 5 **on the corpus** (below); the rest no |
   | T3 | C′ (git-toplevel-rglob) build; **NEW** no-`_contained` build | no |
   | T6 | dropped-`--strict`-raise build | **yes** |
   | T7 | silent-walk build; **NEW** fires-on-clause-2-walk-hits-only build (misses move 1's clause-1 hits) | no |
   | **T10** | **the shipped build itself** (`rcpt_verify.py:240-241`'s `return {}`, **and its `parse_trace` twin at `:259-260`, and its `parse_claims` twin at `:352-353`**) | **yes** |
   | **T11** | **NEW — the shipped build itself** (`tier2_artifacts` with no tracked-ness or gitignore check anywhere in its body, **legs 1–2, I2 and I3**; **leg 3 — the identical gap in `tier2_witness`, same shipped build**) | **legs 1–2 yes; leg 3 argued from the mechanism** |

   Eight legs (T1's second, T1-neg's second, T2's fourth through seventh, T3's second, T7's second)
   contribute **nine** new copies — every new leg contributes exactly one broken-copy construction
   except T2's sixth leg, which names two independently-discriminating ones (the truncated-run
   return-by-value build and the truncated-run `TestNotesSurviveALintError`-transplant build) and so
   contributes two, the same one-table-slot-per-named-shape convention T1's, T1-neg's, T3's and T7's
   own multi-shape legs already use — and two whole pins are new against the six-copies-over-six-pins
   baseline: **T10, widened to three parsers, contributing three copies; T11, new with three legs but
   two
   builds** — legs 1–2 both fail against the same unmodified `tier2_artifacts` (one shared copy, per
   the identical one-table-slot-per-named-shape convention above), leg 3 against the separately-shipped
   `tier2_witness` (a second copy) — **taking the count to twenty over eight**. For reference: the
   pre-split criterion counted fourteen copies over ten pins; T4, T5 (two copies), T8 (four) and T9
   moved to #530 with the floor, carrying **eight** of those with them.

   **AC-6 is satisfied at implementation time, not by this document: the pins do not exist yet, so
   nothing here has been verified against anything** — what §5 supplies is the discriminating input
   for each copy, and this criterion is the obligation to use it.

   **Of the twenty copies, five are measured at the linter, one is measured on the corpus, and
   fourteen are argued from the mechanism.** §5 quotes a discriminating CLI run on `dd06b80` for **T6**
   (one copy), **T10** (all three parsers, three copies) and **T11**'s first two legs (one shared copy) — its
   third leg (`tier2_witness`) is verified by reading the function's body rather than by a constructed
   CLI-level receipt, so it is counted with the argued set below, not the measured five, until an
   implementer or a future round constructs one.
   **T2's fifth leg** — the verified-blind basename-key build — carries a measured
   discriminator of a weaker kind: **66 (flat `codegate22`) / 89 (real nested `codegate22`)**
   suppressed true advisories across the three frozen corpora, computed from the receipts themselves
   rather than from a build, because **no build emits this note at all yet** and a discriminating CLI
   run against one is not constructible today. That is stronger than a mechanism argument and weaker
   than T6's, T10's and T11's, and it is counted separately for exactly that reason — and it is itself the
   one corpus-measured figure in this table that is layout-dependent, so the self-assessment below is
   unstated-configuration-dependent unless the layout is named beside it, which it now is. T6's fixture had to be **constructed**
   — the pre-split draft's named discriminator (`corpus17/rcpt-18`) does not discriminate, because it
   exits 1 under the broken build too. T10's and T11's (legs 1–2) broken builds needed no construction
   at all: **they are the shipped code** (the parser for T10, `tier2_artifacts` for T11's legs 1–2,
   `tier2_witness` for T11's leg 3 — the last needs no construction either, for the same reason, but
   its runs are not yet CLI-measured). **T1 (both legs), T1-neg (both legs), T2 (legs 1-4, 6 — both of
   its named copies — and 7), T3 (both legs), T7 (both legs) and T11 (leg 3)
   are argued from the mechanism and must be confirmed by the implementer against a real broken
   build.**

   ⚠ **This ratio is worse than the pre-split document's and is stated, not smoothed.** Before the
   split, 8 of 14 copies carried a measured discriminator; after the split, **5 of 20** carry one
   at the linter and **6 of 20** counting T2's corpus-measured fifth leg — because the measured ones
   were disproportionately the floor's. The retained half is the
   *less* empirically pinned half, and an implementer should read §5's fourteen mechanism-arguments as
   claims to falsify rather than as findings.

   ⚠ **THREE vacuous DEC-31 pins have now been found in this arc by re-measuring at the linter or
   by reading a pin against a directive, rather than by reading the pin's own prose** — T6's
   (repaired above), T8's leg (8b) (withdrawn, now #530's), and **T3's:
   §6's unqualified *"any such pin needs a fixture root outside the checkout"* entails that T3 goes
   green against the C′ build it was written to catch, because a root outside every checkout has
   `_git_toplevel(root) is None` and C′ then has nothing extra to rglob.** None of the three was
   visible from the text. **T3's is the worst of the three**, because its vacuity was not merely
   unmeasured — it was *mandated* by another section of this same document. Assume the fourteen
   mechanism-argued copies carry the same risk until measured, and prefer re-measuring at the linter
   to re-reading the prose: that is the method that found all three.
7. The corrections in §2.8, §2.6 and §2.3's `codegate22` column are posted to #488. **The
   pre-registration log clause moved to #530 with §3.6** — it registers the floor's corpus, which
   this document no longer adopts, so opening it here would pre-register a bar nothing in this
   document sets.
8. **AC-8, NEW — the prose-rewording surface §6 says has no reader gets the one enforcer §6 says it
   can have.** Every §4 row marked **MUST be re-worded** — the fourteen probe-set / "no search" /
   cross-root-ambiguity prose sites this document's own opening note now enumerates (above) — is
   edited in the same change that lands the mechanism it describes. This is a **conjunction**, not a
   single grep, because the fourteen sites do not all carry the same distinctive string: **both**
   `grep -rn "no search" skills/` **and** `grep -rn "never a false FAIL" skills/` (the latter is
   exactly `build:14` + `siege:21`) MUST return **zero** hits after C lands, over
   `quality-gate/SKILL.md`, `return-convention.md`, `red-team/red-team-prompt.md`, `build/SKILL.md`
   and `siege/SKILL.md` — but the two greps are a **completeness pre-filter, not a correctness
   check**: they establish that every grep-covered site was touched, not that the claim at it was
   corrected. `quality-gate/SKILL.md:54`, `:56` and `return-convention.md:135`
   carry no distinctive string either grep can find, so those three MUST be signed off by hand —
   re-read at the cited line and confirmed no longer contradicted; **and, because this document
   already records that at those same three sites the claim survives string removal without the
   claim changing, nothing prevents the identical gap at the other eleven — so each of the
   fourteen cited lines MUST be re-read and confirmed no longer contradicted, not only the three the
   greps cannot see.** This does not cover the items this section's opening note enumerates
   as Uncovered — they remain uncovered by any criterion and are scheduled by §4 and §5 directly
   rather than by a grep an implementer can run. (Deliberately not restated as a count here: read
   the opening note's list itself as authoritative, so this sentence cannot drift out of sync with
   it the way a repeated number could.)
9. **AC-9, NEW, text only — this criterion does not land in this ticket's own implementing change;
   it is a tracked future obligation, the role AC-2/AC-6/AC-8 already play here for unimplemented
   work.** A `scripts/check_488_gates.py`, wired into `scripts/run_tests.sh` on the precedent of
   `scripts/check_rt_receipt_contract.py` (which already gates four named skill-methodology files,
   including `skills/shared/return-convention.md`, off design-doc acceptance criteria), MUST assert
   the ordering XOR for each of this document's five gates: for each gate, either its precondition
   row has landed (an observable repo fact — a grep or file-content check, not a human reading a
   prose MUST) or the gated edit has not shipped, and the script fails if both are false
   simultaneously. This is not the enforcement mechanism itself — no such script is written by this
   pass — it is the obligation to write one, on the same terms this document's other unimplemented
   criteria already carry.

## 9. Open questions — maintainer decisions, not to be quietly chosen

- **OQ-1 — moved to #530** (what is K in the pre-registered corpus).
- **OQ-2 — does the fix agent get a new obligation to write its own diff?** Deferred, not rejected.
  Verify-log-only binds test output, not edited bytes (§3.2). Adopting it means authoring a
  fix-prompt file that does not exist today.
- **OQ-3 — is `E` (a declared name-kind, e.g. `at=`/`repo=` in the ignored-meta slot) adopted?**
  `parse_artifacts` silently discards trailing `key=value` today, so it needs a parser change either
  way. **Optional** `kind=` is fail-open by default; **mandatory** re-opens the 93 % blast radius.
  Not decided here, and its dependency moved: the pre-split floor made a declared `kind=` the
  **only** sanctioned route to a legal unverifiable name-kind by pulling `receipt-hash-prefix` inside
  the floor. With the floor on #530, **OQ-3 no longer has that forcing function** and can be decided
  on the grammar's own terms — or deferred until #530 rules. The "93 % blast radius" figure above is
  likewise #530's.
- **OQ-4 — the 63 % class.** This design treats it as resolver-side (closed by C) plus the existing
  location pin at `quality-gate/SKILL.md:312`, **and now plus `RESOLVED-BY-WALK`** (§3.1 clause 2,
  §3.4 channel 2, T7) so that a `:312` violation stays countable after C rather than resolving
  silently. That closes the *silence*; it does not decide the remaining question, which is narrower
  than it was: given that the violation is still counted, does `:312` want an **enforcer** of its
  own, or is a reported sub-count enough? If the maintainer wants enforcement, §3 needs a fourth
  clause. **A reported sub-count is worth less than it looks**, because the counter it bumps sits
  outside any floor's sum, so this class may score **zero** after C — which is **OQ-7 on #530**.
  **These two questions must be answered together, across two tickets**, which is a cost of the split
  and is recorded rather than hidden.
- **OQ-5 — do the fixture roots move out of the checkout** (§6), and is that this arc or its own?
  **Answering "yes" is not a free choice among two options that only differ in tidiness (B2 — Blind
  Spots F5): T3 and T11 — the pin set catching the C′ build and the whole I2/I3 false-verification
  channel — are, by §6's own carve-out, the two pins whose *broken* copy is defined by reaching a git
  toplevel, which needs their fixture root **inside** a checkout to have anything to discriminate (§6;
  §5, T3's ⚠ and T11's closing ⚠). A root outside every checkout has `_git_toplevel(root) is None`, so
  both pins go vacuous the moment OQ-5 is answered "yes" — the same vacuity §6 and AC-6 already measure
  T3 as having had once, from a different cause. A maintainer answering OQ-5 in isolation, the way §9
  is written for, can silently re-create that defect a third time.**
- **OQ-6 — round 1 and the artifact under review.** §4 adopts the orchestrator-side remedy: write
  `artifact-N.md` into `<findings-root>` at **every** round's dispatch step, from the artifact that
  round's dispatch file names, so I4 has a legal name from the first round **and a byte-current one
  at every later round** — the round-1 gap and the staleness gap take the same remedy, which is why
  it is one row in §4 and not two. The alternative is to **sanction round-1 `TRACE`-only** for the artifact under
  review, which requires carving an exception out of §3.1's unconditional *"**never** to evict the
  name into `TRACE`"* and saying so in §3.3. Named rather than chosen, because §3.1's "never" is
  one of the ruling's two unconditional clauses and weakening it is not a drafting decision. (§3.3
  sits outside this round's change boundary, so the carve-out is not drafted here either way.)
  **The one case §4's remedy does not itself reach, named rather than left implicit:** a round whose
  `artifact-N.md` was not written into `<findings-root>` at dispatch — the orchestrator-side write
  above failing to run — has no compliant move under §3.1's unconditional "never," because there is
  no orchestrator-supplied copy to cite and no `TRACE`-only carve-out has been sanctioned. That is
  this question's own case, not a second gate: the alternative above (sanctioning round-1
  `TRACE`-only) is the same maintainer decision this case needs, generalized to any round the write
  is missed for, not only round 1.
- **OQ-7 — moved to #530** (is `resolved-by-walk` inside or outside the floor's sum). **It remains
  unruled, and §3.1 clause 2 still depends on it.** **That dependency is a binding
  gate:** C MUST NOT be implemented until either #530 rules OQ-7, or
  `quality-gate/SKILL.md:36` is amended in the same change to treat a non-zero `resolved-by-walk` as
  UNVERIFIED. **Which horn is taken is a maintainer decision and is deliberately not made here.**
  Measured cost of taking neither: 16 of `live29`'s 29 receipts (55 %) stop being flagged UNVERIFIED
  at the census's only live consumer the day C ships, with nothing reading the replacement counter.
  **Both horns are #530-facing, and they are not equivalent:** horn (b) is an edit to a line §4 has
  routed to #530, and it returns those same 16 receipts to UNVERIFIED, so it nets C's benefit at
  `:36` to zero — a *safety* horn, not an *equivalent* one. **Consequence, stated because §8 is
  where it bites:** C is therefore gated on #530 in every branch, and AC-4 and AC-6's C-dependent
  pins with it. See §3.1 clause 2, §4's `:36` row, and §8's opening note. **The same #530-or-`:36`
  gate also covers rolling out §3.2 compliance to producers, via the fix-agent-prompt's dispatch-
  input wiring and via the `return-convention.md:104`/`:256` retraction — the strictly larger of the
  two rollout vectors, since the convention is read by its six adopting skills**
  (§3.1 clause 2's second ordering paragraph) — a narrower, prospective dependency
  from C's, with zero measured live population in either corpus today, though its only
  self-serviceable exit (horn (b)) is measurably net-negative rather than merely narrow (§3.1 clause
  2). **§3.3's rollout is not gated
  by this or by anything #530-facing**: compliance there is a re-citation that resolves and
  hash-verifies, not a flip, so `red-team-prompt.md`'s edits (§4) carry no such dependency.
- **OQ-8 — NEW: do I1–I3 bind the committed receipt fixtures?**
  `eval/ledger-return-protocol/**` holds **104 `ARTIFACTS` names** across the `sample-corpus`,
  `v11-corpus`, `inject`, `v11-inject`, `tripwire` and `tier2-fixtures` corpora — **47 of them
  bare basenames of tracked repo files (I2-shaped), 3 path-shaped (I1/I3 exposure)** — and they are
  CI-gated by `run_tests.sh:102-106`. They are the repo's densest concentration of the exact objects
  this ruling governs, and §4's blast-radius scan never left `skills/`.
  **Recommendation: NO — fixtures are linter *inputs*, not producer *returns*, and several are
  deliberately malformed.** But that is a maintainer call and is **not made here**, because the
  answer changes what "an `ARTIFACTS` entry" means in I1–I3's own quantifier.
  **Both horns, stated.** *Bind them:* 47 committed entries become illegal and the fixture corpora
  must be re-authored — and re-authoring a corpus to pass is the shape §6 warns is not evidence.
  *Do not bind them:* I1–I3 quantify over producer returns only, and the document must say so
  explicitly, or an implementer reading AC-2 lands a tracked-ness check in `parse_artifacts` and
  turns `run_tests.sh` red on 47 entries. **AC-2 has been re-scoped to make the second horn safe
  either way *for this population*** (§3, *Lexical grammar*): only the lexical half lands at Tier-1,
  all 104 fixture names already satisfy it, and no semantic rule reaches `eval/**`. So OQ-8 can be
  answered late without blocking implementation — which is why it is an open question and not a
  second gate. **Do not read that as "`run_tests.sh` stays green either way", which an earlier draft
  did:** the suite gates a **second** receipt population at `run_tests.sh:103` —
  `scripts/test_rcpt_verify.py` — which constructs four names the lexical rule rejects **on
  purpose**, and landing the enforced clauses turns two committed pins structurally unreachable
  unless they are re-authored in the same change. That cost is real, is measured (§3, *Lexical
  grammar*), and is scheduled on AC-2 and in §4; it is simply not OQ-8's question, because those
  receipts are neither producer returns nor `eval/**` fixtures.
- **OQ-9 — NEW: does T11 (the I2/I3 tracked/gitignored hard-FAIL, §3.4's silence-adjacent seventh
  channel) land ahead of, or gated alongside, #530's floor?** Not decided here. **The case for
  scheduling it independently of C:** the mechanism T11 checks — `_allowed_bases`'s git-toplevel
  probe — is not part of C's bounded walk; it is the pre-existing, already-shipped resolution path
  §2.8 item 4 measures, so T11 does not inherit OQ-7's dependency on a floor ruling the way C, T1,
  T1-neg, T3 and T7 leg 1 do (§8's opening note; T7 leg 2 does not either). **The case for gating it anyway:** T11 is a **new**
  Tier-2 hard-FAIL class reaching an orchestrator, on the same class of concern I7 names for C's
  walk, even though I7 itself does not enumerate it (§3.4, channel 7) — and it shares OQ-8's
  question in miniature: `eval/ledger-return-protocol/**`'s 47 tracked-repo-file fixture entries
  (OQ-8) are read as linter *inputs* against constructed test roots, and whether any of those roots
  resolves through a git-toplevel probe the way T11's fixtures must (§6, §5) is not established here
  — if one does, T11 landing could turn a committed fixture red the same way OQ-8 warns a
  `parse_artifacts`-level tracked-ness check would, and the same *"a corpus re-authored to pass is
  not evidence"* guard applies. **Both horns, stated rather than chosen**, in the shape OQ-8 and
  OQ-6 already use for a maintainer call this document does not resolve.
- **OQ-10 — NEW (C4 — Technical Soundness F3): does `..` land at Tier-1, with S-3
  (`TestTheWorldWritableRefusalIsMonotone`) re-targeted at the containment shape instead of retired?**
  Not decided here. §3, *Lexical grammar*, states the reason `..` does not land as "this ruling
  declines to re-author a security fixture as the price of a grammar-only benefit" — but the two
  clauses that *do* land also re-author security-lineage, hostile-input fixtures
  (`TestARefusedProbeBaseIsDiagnosable`, the NUL leg of `TestHostileReceiptNamesAreEscapedToo`), so
  "touches a security fixture" cannot be the actual discriminator. The narrower, breadth-based
  distinction stated at §3 is offered in its place, but it is a threshold, not a categorical rule, and
  the maintainer has not actually set it. Both horns: land `..` uniformly with the other two clauses
  (re-author S-3 onto `_contained`'s realpath containment, the faithful substitute §3 already names),
  or keep it producer-normative only, on the breadth argument rather than the retracted one.
- **OQ-11 — WITHDRAWN, measured (G1 — Integration Impact F2).** Originally posed as: is the `--eval`
  byte-diff contract deliberately broken by the `resolved-by-walk` census field? It is not, and the
  premise was false. The `--eval` byte-diff compares `_eval_text`'s stdout (`rcpt_verify.py:3074-3104`),
  which emits per-record `LINT-PASS`/`LINT-FAIL` rows and a summary and **never the `TIER2-COVERAGE:`
  census** — that line is rendered only on the `--tier2` stderr path via `_Coverage.render()`, which
  `_eval_record` (`:3056-3070`) never constructs. Verified on `dd06b80` by adding `resolved-by-walk` to
  `_COV_COUNTERS` in a scratch copy and diffing: `--eval sample-corpus/receipts.jsonl` output and
  `--selftest` output (including its golden-string assertion) are byte-identical between the baseline
  and patched trees. The `_unresolved_disposition`/`_refused_clause` comments that call the contract
  load-bearing are about `LintError` **message** fidelity, which does reach `_eval_text`, and are
  untouched by a census field. The fifth ordering gate therefore carries **two** conditions, both
  mechanical (the full-string assertion rewrite, `:36`'s reader tolerance — §4, §8), not three; T7 leg
  2 is schedulable within this ticket's implementing change once both are satisfied, with no
  outstanding maintainer decision blocking it.
- **OQ-12 — NEW (E3 — Blind Spots F7): who owns preserving the three frozen corpora and the
  measurement instruments off machine-local, sweep-vulnerable paths?** Every quantitative claim in
  this document depends on state living under `~/.claude/projects/…`, not in the repo, not CI-gated on
  any machine but the authoring one, and already measured **absent mid-run** once (§10). This
  document's own change boundary is cited as the reason it does not fix this (§10, AC-4's ⚠), which
  forecloses the remedy without assigning it anywhere else. Not decided here, and not this document's
  alone to answer: either c1 or a follow-up ticket must take it, and until one does, every figure this
  document cites remains re-derivable only on one machine.

## 10. Provenance

- Dispatch (originally `/tmp/crucible-dispatch-1787239343/`, **since swept**) — `shared-context.md`,
  seq 1–4 (`domain-researcher`, `impact-analyst`, `residual-measurer`, `challenger`),
  `manifest.jsonl`.
- Measurement artifacts: `population.{md,json}`, `counterfactual.json`, `census-raw.json`,
  `measure-{corpus17,live29,codegate22}.txt`, 8 throwaway scripts. Repo tree clean throughout.
  **They survive, and the surviving location is the one to cite:**
  `~/.claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate/scratch/2026-08-20T09-05-29/dispatch-archive/`,
  which holds `counterfactual.py`, `codegate_nested_rules.py`, `counterfactual.json`,
  `census-raw.json` and the seq-1–20 dispatch files. **An earlier draft of this bullet pointed at
  the `/tmp` path and called preserving them off `/tmp` an obligation of whoever implements C; the
  `/tmp` directory is gone and the preservation is already discharged, so both are withdrawn.**
  ⚠ What survives of the warning: `counterfactual.py` and `codegate_nested_rules.py` are what
  produced `live29 42 → 14` and `codegate22 (real nested) 96 → 2` — **not**
  `measure_486_corpus.py`, the shipped instrument §2's header names — and per §6 no corpus figure is
  CI-gated on any machine but this one, so this archive is the **only** way to re-derive the
  ruling's headline figure and it is machine-local. Copying it into the repo is still forbidden by
  this document's change boundary. **Ten of the archive's eighteen scripts run unmodified; eight —
  including `counterfactual.py` itself — hardcode the dead `/tmp/crucible-dispatch-1787239343/`
  path and do not.** Of the ten, `codegate_nested_rules.py` reproduces AC-4's `codegate22 (real
  nested)` column directly, and `codegate_nested.py`/`codegate_c_detail.py` independently
  corroborate its `96` residual and seven-hit `artifact-under-review.diff` figures. **See AC-4's ⚠
  paragraph for which of the eight need re-pointing before use.**
- **The three frozen corpora — a SEPARATE preserved object from the instruments above, and an
  earlier draft's list of what survives never named one.** `live29` and `codegate22` live at
  `~/.claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate/evidence-486-tier2-resolution/frozen-corpora/`
  (the path `measure_486_corpus.py` and `codegate_nested_rules.py` both hardcode) and are covered by
  that directory's `SHA256SUMS-frozen.txt`. **`corpus17` is not**: its dispatch root is the sibling
  `evidence-474-tier2-resolution/corpus-2026-08-01/`, which `SHA256SUMS-frozen.txt` does not cover —
  only its findings root (`frozen-corpora/scratch-2026-08-01T21-18-18/`) is; a byte-identical
  receipts-only copy sits at `frozen-corpora/corpus-2026-08-01/` with its own
  `SHA256SUMS-corpus17.txt`, and neither manifest is `SHA256SUMS-frozen.txt`. **Sweep-vulnerable**:
  this document's own gate measured them moved out of their paths mid-run by an unidentified sweep,
  and restored — **manifest-verifiable for `live29`/`codegate22`**, `sha256sum -c
  SHA256SUMS-frozen.txt` against the manifest that travels beside them, which is what makes
  restoration distinguishable from re-freezing (§6) **for those two**; `corpus17`'s restoration is
  verifiable the same way against its own `SHA256SUMS-corpus17.txt`, not against
  `SHA256SUMS-frozen.txt`, which reports `432/432 OK` regardless of `corpus17`'s state. §2.1 and
  AC-4 carry the corresponding warning; this bullet is what makes §10's own survivor list complete.
- Recon was **folded into the Impact Analyst** rather than dispatched separately — a recorded
  deviation from `/design` Phase 2 Step 0.
- Grudge pre-flight: `e0f0a6b75692` (this file, fixed at `5d1fb15`) — *"the fail-open direction is
  silent"* — carried as a kill test into every dispatch and discharged in §3.4.
- Maintainer decisions taken 2026-08-20: C adopted as the resolver half; #513 answered
  verify-log-only with the limit stated; criterion 4 re-baselined onto a pre-registered prospective
  corpus.
- Leftover, not swept (dated 2026-08-21, the round this bullet was written): `/tmp/measure486-flat-7nl4nwgs`
  (a measurer temp dir; its `rm` was denied in that agent's session). 12 older `measure486-flat-*`
  dirs pre-dated that session. **Neither figure is a standing property** — re-checked 2026-08-24, that
  specific directory no longer exists and **53** `measure486-flat-*` dirs are on disk, a floor that
  will keep moving as further measurer sessions run and none of them sweep.
