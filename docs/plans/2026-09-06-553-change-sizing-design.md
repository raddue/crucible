---
ticket: "#553"
title: "Change-sizing convention in shared/"
date: "2026-09-06"
source: "design"
---

# Design — `shared/change-sizing.md` (#553)

## 1. Problem

Nothing in Crucible tells an implementer or reviewer when a diff is too big, and
nothing gives named strategies for splitting one. `temper` and `delve` each carry
a >5,000-line **context-window** cap, but that is a question about whether the
*reviewing agent* can hold the diff — not about whether the change *should exist
at that size*. `finish` presents merge/PR/stack options with no size input at
all. The judgment is absent, not merely duplicated.

## 2. Locked inputs (maintainer decisions — not re-litigated here)

- **D1 — Third consumer is `delve`, not `code-review`.** `skills/code-review/`
  does not exist in this repo; `temper` *is* the renamed `/code-review`
  (`skills/temper/SKILL.md:21`). Consumers are **temper, delve, finish**.
- **D2 — The comment-severity prefix vocabulary is NOT built.** The issue's
  proposed `Critical:` / `Nit:` / `Optional:` / `Consider:` / `FYI` collides with
  `skills/shared/severity-verdict-contract.md:166`, which names `Nit` verbatim as
  a forbidden invented tier under invariant **I11**. The issue's own escape hatch
  ("or explain in the doc why they stay distinct") is taken instead: the doc
  carries a reasoned non-adoption section and adds no vocabulary.

## 3. Scope decision — reference plus minimal behavioral hook

A canonical doc that no skill consults is decoration. The issue's gap statement
("each reinventing or **omitting** this judgment") describes a behavioral gap.
Each of the three consumers already has the data at the point of insertion, so
the hook is small:

| Consumer | Already has | Hook cost |
|---|---|---|
| temper | `git diff --numstat` at Step 1.5 (`:120`) + non-gating round-metadata flags (`:123`, `:124`, `:126`) | ~3 lines (a sixth classification bullet appended after `:126`, positioned outside the `>5,000` branch but still gated by the shared ~300 firing condition — see §5) |
| delve | same numstat preflight (`:90`, diff scope only) + a run-level scope/effort report line (`:120`) | ~2 lines |
| finish | a resolved base ref after Step 4 (`:85-100`) | ~4 lines |

**Everything the hook emits is advisory. Sizing never gates, anywhere.**
`delve` never gates at all (`:122`); `temper`'s Clean condition is closed over the
tracked set `T` (`:289`) and adding sizing would redefine Clean; `finish`'s only
hard stops are warden `BLOCKED` (`:54`) and a Step 5.5 non-zero exit (`:123`).
An oversized-but-correct branch must remain mergeable.

## 4. The artifact — `skills/shared/change-sizing.md`

House style follows the newest shared/ docs (`severity-verdict-contract.md`,
`delve-engine.md`): H1 with em-dash subtitle, a blockquote header declaring
purpose + scope boundary + `**Consumed via**` idiom + `**Linked from:**` link-carrier
list, numbered `## N.` sections, closing `## Anti-patterns` opening with `Do not:`.
Target length ~110-140 lines — peer range for a doc of this scope
(`severity-rubric.md` 65, `security-signals.md` 94, `model-tier-policy.md` 118).

### Section plan

1. **Reviewability thresholds.** The ~100 / ~300 / ~1000 changed-line table.
   Adapted from `addyosmani/agent-skills@main`
   `skills/code-review-and-quality/SKILL.md` §Change Sizing and
   `skills/git-workflow-and-versioning/SKILL.md` §5.
2. **What counts as "one change".** One self-contained modification addressing
   one thing, including its tests, leaving the system functional. One part of a
   feature — not the whole feature. Without this, "~100 lines" is an arbitrary
   number.
3. **File size is a separate signal.** ~1000 *total* lines in one file is an
   inspection signal distinct from ~1000 *changed* lines: a small diff can push
   an already-large file past a healthy boundary. Decompose, then add.
4. **Splitting strategies** — the four named strategies as a table:
   | Strategy | How | When |
   |---|---|---|
   | Stack | Submit a small change, start the next on top of it | Sequential dependencies |
   | By file group | Separate changes for groups needing different reviewers | Cross-cutting concerns |
   | Horizontal | Shared code/stubs first, then consumers | Layered architecture |
   | Vertical | Smaller full-stack slices of the feature | Feature work |
   **Grounded in this repo's existing machinery** (innovate, partial accept —
   see §11). The four strategies are not abstractions here; `/planning` already
   produces three of them under other names, and naming the correspondence is
   what makes "split it" actionable rather than aspirational:
   - **Stack** ≡ a sequential `Dependencies` chain across plan tasks.
   - **By file group** ≡ planning's **Consumer Migration Fan-Out**
     (`skills/planning/SKILL.md:124-135`), which already fans independent
     consumer migrations into parallel tasks — that *is* By-file-group, unnamed.
   - **Horizontal** ≡ planning's shared-code-first task ordering.
   - **Vertical** ≡ full-stack slices.
   - §2's "one change, system still functional after" ≡ `/build`'s plan-writer
     `safe-partial: true` rollback annotation (`skills/build/plan-writer-prompt.md:112`,
     `skills/build/SKILL.md:1145`).

   This is doc content only. It adds no consumer, no link, and no hook to
   `/planning`.
5. **When a large change is acceptable.** Complete file deletions; mechanical or
   automated refactors where the reviewer verifies intent, not every line;
   generated files. **This escape valve is load-bearing** — without it the
   thresholds get cargo-culted into a hard gate, which §3 forbids.
6. **Separate refactoring from feature work.** Two changes, submitted separately;
   small cleanups may ride along at reviewer discretion.
7. **These are not context-window caps.** One explicit paragraph: `temper:126`
   and `delve:95` cap diffs at >5,000 lines because a *reviewing agent's* recall
   degrades past that (remedy flag: `degraded-context`). This doc's numbers are
   about a *human* missing a defect or being unable to revert. Same unit
   (`numstat` lines), different axis, 5× apart. Neither supersedes the other and
   this doc does not move the 5,000 number. The one legitimate contact point:
   temper's "offer to split per-commit or per-file" (`:126`) is an unnamed
   instance of Stack / By-file-group; §4 names it.
8. **Comment-prefix vocabulary — deliberately not adopted (#553).** The reasoned
   non-decision, in the house form of `severity-verdict-contract.md:155-160`
   ("no normative conversion exists … that is a separate, larger change; this
   contract deliberately does not attempt it"). Content: the source's five
   prefixes are already the trio's four tiers plus a gating flag —

   | Source prefix | Existing Crucible equivalent |
   |---|---|
   | `Critical:` | trio `Critical` |
   | *(no prefix)* = required | trio `Important` |
   | `Nit:` | trio `Minor` |
   | `Optional:` / `Consider:` | trio `Suggestion` |
   | `FYI` | no equivalent — the trio reports every kept finding at its own tier |

   Which of these tiers gate is defined once, in `severity-verdict-contract.md`
   (link, don't restate — the C/I gating band lives there, not here). Adopting
   the source's prefixes as a parallel scale would be a second name for a
   distinction the repo already makes — the exact drift the link-don't-copy rule
   exists to prevent — and `severity-verdict-contract.md` §6 forbids `Nit` by
   name. State the reopening condition: unifying the two existing scales is a
   separate, larger change, and this doc does not attempt it.
9. **Anti-patterns** (`Do not:` list), including the source's
   "I'll split this change later" → split before submitting, not after.

### Non-goals (stated in the doc)

The doc must **not**: define, extend, or normatively convert any severity or
verdict vocabulary (§8 may name the source's prefixes solely to record
non-adoption, and must cite `severity-verdict-contract.md` for the gating band
rather than restating it); make any threshold gating; state a line threshold of
its own that equals or supersedes the 5,000-line context caps, or relate itself
to `cap`/`cap-saturation` (findings counts, not lines) — §7 may cite the
5,000-line caps, attributed to temper/delve, solely to distinguish this doc's
axis from theirs; claim `/audit`'s systemic territory ("too much changed at
once" as a no-single-reproduction pattern); overlap the `altitude` angle or the
`Surgical Changes` lens (which judge *where* code sits and *scope bleed*, not
*how many lines*); prescribe engine inputs; or add a mandatory checklist item to
any consumer.

## 5. Consumer integration

**Firing condition (shared across all three hooks).** Each hook fires only when
the measured changed-line count exceeds the doc's middle band (~300, per §1);
below that it emits nothing. This is stated once, here, rather than once per
cell — the cells below differ only in *where* the note lands and *what channel*
carries it.

| Consumer | Insertion point | Pointer says |
|---|---|---|
| **temper** | after `SKILL.md:15`, joining the header CANONICAL cluster (`:8`, `:11`, `:14`) | Sizing thresholds are human-reviewability guidance temper *surfaces*, never gates on; sizing never enters `T`; distinct from Step 1.5's 5,000-line context cap; the named strategies are what `:126`'s "split per-commit or per-file" resolves to. Hook: a sixth bullet appended to the `:122-126` classification list (slot `:127`, currently blank) — positioned outside the `>5,000` bullet, and its emission still obeys the shared ~300 firing condition stated above (not "unconditional") — records the changed-line count as a non-gating round-metadata note. Independent of the `degraded-context` flag in the `>5,000` bullet: different axis, see `change-sizing.md` §7. |
| **delve** | after `SKILL.md:15`, same header cluster shape (`:8`, `:11`, `:14`) | For **diff** scope, delve is report-only and never gates, so a sizing observation is a property of the *run's scope*, printed on the Step 3 run-level line — never an eight-field record (no single reproduction ⇒ fails delve-engine's cutting rule, `delve-engine.md:19-27`) and never in the ledger row. For **path** scope there is no diff to measure; the run-level line carries no changed-line observation (optionally the doc's §3 total-file-size signal instead) — "no sizing line" is a specified outcome for path scope, not an implementation accident. |
| **finish** | point-of-use, between `SKILL.md:100` and `:102` — i.e. after Step 4 resolves the base ref, before Step 5 presents options | Measure `git diff --numstat <base>..HEAD` (two-dot, matching temper's two-dot `git diff --numstat <base>..<head>` at `:120` — both diff the base ref's *tip* against HEAD, never the merge base — so the two consumers measure the same range on the same branch); if past the reviewable band, say so and name the applicable strategy. Advisory input to the merge-vs-PR-vs-stack choice. |

`finish` uses point-of-use placement because the sizing measurement needs
Step 4's resolved base ref, which does not exist before that step runs. Its
header (`:10`) carries only the `dispatch-convention` boilerplate every
dispatching skill has; the two canonical links it has today (`:171`, `:282`,
both `compass-protocol`) are duplicated markers for a mechanism finish
*performs* at two emit points, whereas a sizing convention is something finish
*consults* once, at the step whose data it needs — the `:10` category, not the
compass-emit category. Placement is **after** warden (Step 2, `:43-56`),
because warden hard-REFUSES on an unclean tree and a sizing advisory before
that gate would be noise on a run about to refuse. It is **not** added to the
Gate Execution Ledger checklist (`:455-465`) — every item there is mandatory
and an unchecked box means STOP.

**Why round-metadata and not a Suggestion finding, in temper.** A Suggestion
record implies a finder angle, and `severity-verdict-contract.md:99-107`'s
angle→severity map has no angle that owns "diff size". A metadata flag carries no
severity and no verdict, so it sits outside I11's surface entirely. (There is
precedent for the other choice — `temper:124` raises a Suggestion from inside
preflight for the submodule case — so this is a judgment call, recorded as such.)

## 6. API surface

One new script, `scripts/check_canonical_links.py`, stdlib-only, exit 0 clean /
1 with a `- <error>` list per `scripts/CHECKER_CONVENTIONS.md` §3. It has two
responsibilities:

```
python3 scripts/check_canonical_links.py            # check the tracked tree
python3 scripts/check_canonical_links.py --selftest # built-in logic tests
```

**Responsibility 1 — general link resolution.** Glob `git ls-files "*.md"`,
never `*.py`, then apply the documented scan-scope exclusion below. Path-pinning
cannot express "*every* CANONICAL link resolves" for *this* half of the check —
it would need the file list up front, which is the thing that drifts.

**Scan scope (documented, the way `check_crossref.py` documents its scope
decisions).** The scan excludes `docs/plans/` and `docs/handoffs/`. Design docs
and handoff docs discuss links in prose and in backtick-wrapped examples; this
design doc is a live counterexample — its line 242 carries a
`<!-- CANONICAL: shared/dispatch-convention.md -->` that sits inside a backtick
span opened on line 241, presented as an example mid-prose mention, not as a real
link. Excluding these two doc directories is what keeps such incidental prose
mentions out of the link set. This is a scope decision, not `CHECKER_CONVENTIONS.md`
§2's self-match discipline; the discipline actually adopted from §2 is **column-0
anchoring** (the match rule below requires the comment opener to be the first
non-blank content on the line, after optional whitespace/blockquote/list markers),
which is the same remedy `check_i2_marker.py` uses — extension filtering
(`*.md`-vs-`*.py`) is not one of §2's three remedies and is not claimed as one.

**Match rule.** After stripping leading whitespace and optional blockquote (`>`)
and list (`-`/`*`/`+`) markers, the line must start with `<!--`, and the
comment's content — before any further checks — must contain `CANONICAL:`:

```
^[ \t]*(?:>[ \t]*)*(?:[-*+][ \t]+)?<!--[^>]*?CANONICAL:[ \t]*(shared/[^\s#>]+\.md)(#\S*)?[ \t]*(?:[^>]*?)-->
```

This tolerates a preamble inside the comment before the keyword (e.g.
`<!-- Compass emit — orchestrator only (D14). CANONICAL: shared/... -->`), which
the naive "`CANONICAL:` must immediately follow `<!--`" rule silently misses —
including a real, live link (`skills/merge-pr/SKILL.md:210`) that has exactly
that shape. Verified empirically against the tree at HEAD `1888642` (the tree
as of the commit before this design doc was itself added — pinning the census
to a fixed pre-existing commit, rather than this doc's own moving HEAD, avoids
the self-reference trap discussed below), re-run after adding the preamble
tolerance: **83 links, 10 targets, 0 broken** (up from an undercounted 82/10
under the naive rule; `shared/compass-protocol.md` has **6** consumers, not 5).

This rule is deliberately chosen over a strict whole-line anchor, which misses
two real links: `skills/siege/SKILL.md:52` (list item with trailing prose) and
`skills/shared/delve-engine.md:10` (blockquote).

The rule that separates a real link from a mention is: the comment opener
(`<!--`, after any allowed blockquote/list prefix) must be the first non-blank
content on the line — nothing, not even prose, may precede it. Every
`CANONICAL:`-bearing line that is *not* a link fails that test for one of two
reasons: it is backtick-wrapped or otherwise not a bare HTML comment at all
(e.g. `` `<!-- CANONICAL: shared/x.md -->` `` inside a sentence), or the comment
sits mid-prose with text before `<!--` on the same line (e.g. `> it lives in
<!-- CANONICAL: shared/dispatch-convention.md --> and ...`,
`harness-adapter.md:13`). Enumerated against the same HEAD `1888642` tree under
this rule: **18** tracked lines contain `CANONICAL:` but do not match —
including the four previously-named decoys (`CLAUDE.md:32`,
`harness-adapter.md:152` and `:273`, and the backtick-wrapped
`severity-verdict-contract.md:9` self-reference) and the mid-prose form above.
One of the 18 is itself a doc-directory prose mention
(`docs/plans/2026-08-21-488-c1-name-space-reduced.md:730`, an indented `grep`
example), so the checker's scan scope (above) drops it from the *running*
non-match count; the link count (83) is unaffected because every one of the 83
resolves under `skills/`.
(This design doc itself contains `CANONICAL:`-bearing lines that are
backtick-wrapped or prose-prefixed and so do not match — but one of them, line
242, would be scored as a real link by a naive line-by-line rule, because its
comment sits inside a backtick span that wraps the line boundary. The
scan-scope exclusion of `docs/plans/`, not luck, is what keeps that line — and
this doc's prose mentions of the not-yet-existing `shared/change-sizing.md` —
out of the link set; the census at `1888642` is pinned to the pre-doc tree for
the same reason, so the numbers don't shift when this file is re-edited.) **The
new doc's own `**Consumed via**` header line must stay backtick-wrapped mid-line
for this reason**, or it counts as a fourth consumer.

**Responsibility 2 — consumer set-equality pin.** In addition to resolving
every link, the checker hard-codes one `check_i2_marker.py`-shaped assertion:
the set of tracked `.md` files with a line that matches the rule above for
target `shared/change-sizing.md` equals exactly
`{skills/temper/SKILL.md, skills/delve/SKILL.md, skills/finish/SKILL.md}` — a
missing expected file or a stray extra one both fail. I3 (§7) is this
assertion; it is computed with the same match rule as Responsibility 1, never a
bare `grep`, so a backtick-wrapped or prose-prefixed mention of the string in
`docs/` (including this design doc itself) never enters the set.

## 7. Invariants

**Checkable (by inspection / grep):**
- I1 — `skills/shared/change-sizing.md` exists.
- I2 — every `<!-- CANONICAL: shared/*.md -->` link in a tracked `.md` resolves to
  an existing `skills/<target>`. *(check_method: the new checker)*
- I3 — the set of files carrying `<!-- CANONICAL: shared/change-sizing.md -->`
  (per §6's match rule, not a bare `grep`) is exactly
  `{skills/temper/SKILL.md, skills/delve/SKILL.md, skills/finish/SKILL.md}` —
  set **equality**, so both a missing consumer and a stray fourth fail — **and**
  that same set equals the `**Linked from:**` line in `change-sizing.md`'s own
  header, so a consumer change that updates one but not the other also fails.
  The field is named `**Linked from:**` rather than `**Used by:**` because the
  in-tree `**Used by:**` means the *paraphraser* set — `reviewer-common.md:8`
  and `implementer-common.md:8` each list two prompt-template files that
  paraphrase content, not the N files that carry the link — a distinct meaning
  the pinned link-carrier set must not overload. The checker parses exactly
  this one-line format: backticked full POSIX-relative paths
  `` `skills/<name>/SKILL.md` ``, comma-separated, nothing else.
- I4 — the forbidden tokens (`Nit`, `FYI`, `Optional:`, `Consider:`) appear in
  `change-sizing.md` only inside its §8 non-adoption table (the lines under the
  `## 8.` heading), nowhere else. *(check_method: the new checker greps
  `change-sizing.md` for each token and asserts every hit's line falls under
  `## 8.`; I6 pins a token placed outside §8 as a must-fail case.)* The
  no-new-tier rule is AC 7 (§9), enforced via §8's citation of
  `severity-verdict-contract.md` rather than a separate grep.
- I5 — the token `5,000` appears in `change-sizing.md` only on lines that also
  contain `temper` or `delve` (it may cite the 5,000-line *context cap* as
  temper's/delve's, but never state it as its own reviewability threshold).
  *(check_method: the new checker greps every `5,000` line and requires
  `temper` or `delve` on the same line.)*
- I9 — a gating token (`STOP`, `hard stop`, `BLOCK`, `must not proceed`) does
  not appear within ±5 lines of any consumer's sizing hook, nor anywhere in
  `change-sizing.md`. *(check_method: the new checker — the same mechanism as
  I4/I5 — greps the three hook neighborhoods and the whole doc for the token
  set; a hit fails. This is the mechanical pin that makes "sizing never gates"
  (§3) an assertion rather than prose alone, and I6 pins a gating token placed
  next to a hook as a must-fail case.)*

**Testable (require the test to run):**
- I6 — `--selftest` passes: resolving link OK; missing target detected with
  `file:line`; `#anchor` and `— Section` suffix forms matched with the path
  extracted cleanly; 4-space-indented occurrence matched; a preamble-before-
  `CANONICAL:` comment (the `merge-pr:210` shape) matched as a **must-match**
  case; each of the four named decoy forms NOT matched; a bare, non-backtick-
  wrapped comment sitting mid-prose after other text on the same line (the
  `harness-adapter.md:13` shape) NOT matched as a **must-not-match** case; a
  `<!-- CANONICAL: shared/x.md -->` at column 0 whose line continues an inline
  backtick span opened on the previous line (this doc's 241-242 shape), and a
  bare comment inside a `docs/plans/`- or `docs/handoffs/`-shaped path, both
  NOT matched (the scan-scope exclusion, not the matcher, excludes them — the
  selftest pins both negations); consumer set-equality fails on both a missing
  and an extra consumer; the two-way pin (§7 I3) fails when the
  `**Linked from:**` line disagrees with the scanned set, and fails when that
  line is malformed (a missing backtick would otherwise read as an empty set);
  a forbidden token outside §8, a `5,000` line lacking `temper`/`delve`, and a
  gating token beside a hook all fail (I4/I5/I9).
- I7 — the tree check exits 0 on the post-change tree.
- I8 — `bash scripts/run_tests.sh` stays green end-to-end.

## 8. Testing strategy

TDD order: write `--selftest` cases first (they encode I6 and fail against an
empty checker), then the checker, then the doc and the three consumer edits —
so I3's set-equality goes RED (0 of 3 consumers) → GREEN (3 of 3).

Wire two `run` lines into `scripts/run_tests.sh` in the
`# --- Structural / canonical checks ---` block, immediately after the
`check_crossref.py` pair and before `catalog.py check`, selftest line first per
house rule.

No behavior evals are needed: the three consumer edits add a non-gating advisory
and change no routing description, so skill triggering is unaffected. (Frontmatter
`description` fields are untouched — the repo rule is that the description is the
trigger.)

## 9. Acceptance criteria

1. `skills/shared/change-sizing.md` exists with §§1-9 above, ~110-140 lines,
   matching shared/ house style.
2. temper, delve, and finish each carry the CANONICAL link at the specified
   insertion point with a consumer-specific pointer — not three copies of one
   sentence.
3. Each consumer's advisory hook is present, non-gating (I9's gating-token grep
   passes), placed at the specified step, and fires only above the doc's middle
   band — the ~300 condition is stated once in §5 and encoded in each hook's own
   text, verified by inspection. No narrated example artifact is produced:
   §8 performs no behavior evals (that narrow "no behavior evals" covers
   routing; it does not hide a firing-condition test, which this AC instead
   satisfies by inspecting the hook text itself).
4. `scripts/check_canonical_links.py` exists, passes `--selftest`, resolves
   every CANONICAL link, and asserts the I3 consumer-set equality against
   **both** the scanned tree **and** `change-sizing.md`'s own `**Linked from:**`
   line (parsed per the one-line format in §7); it also enforces I4, I5, and I9
   via their grep checks, and exits 0 on the tree.
5. Both `run` lines are in `scripts/run_tests.sh`.
6. `bash scripts/run_tests.sh` is green.
7. No new severity/verdict tier or normative conversion is added anywhere; §8's
   table is refusal-only and cites `severity-verdict-contract.md` for the gating
   band rather than restating it.
8. I4, I5, and I9 hold: no forbidden vocabulary outside §8, no `5,000` line
   that omits `temper`/`delve`, and no gating token beside a hook or in
   `change-sizing.md` (all three enforced by the new checker, not inspection
   alone).

## 10. Risks

| Risk | Mitigation |
|---|---|
| Reader fuses the ~1000 reviewability threshold with the 5,000 context cap and assumes 5,000 supersedes it — making the doc dead on arrival inside temper | §7 of the doc states the two axes explicitly; both consumer pointers repeat the distinction in one clause |
| Thresholds get cargo-culted into a hard gate | §5's "when a large change is acceptable" escape valve, the advisory-everywhere rule in §3, an anti-pattern row, and I9's gating-token grep (no `STOP`/`hard stop`/`BLOCK`/`must not proceed` beside any hook) |
| §8's non-adoption table re-introduces the forbidden vocabulary by quoting it | The tokens appear only inside a table whose column header is "Source prefix" and whose stated purpose is refusal; I4's section-scoped grep enforces that they appear nowhere outside §8 (and I6 pins an out-of-§8 token as a must-fail) |
| The general link checker later false-FAILs on a legitimately new comment form | The match rule and its documented negative set are recorded in the checker docstring; loosening the regex is a deliberate edit, not a silent one |
| A new comment form is a real link the checker's match rule does not cover — the checker false-**PASS**es, staying green while a real link goes unverified (the failure mode F1 found in this design's own authoring: `merge-pr/SKILL.md:210`) | The match rule tolerates a preamble inside the comment (§6), closing the known instance; the checker's negative-set enumeration (§6) is exhaustive against the tree at authoring time rather than assumed from named decoys, and I6's selftest pins both a must-match and a must-not-match near-boundary case so a future regression here is caught by `--selftest`, not just by the tree scan |
| A future skill adds a fourth `change-sizing.md` consumer and I3's set-equality fails | Intended — the failure is the signal to update the pin deliberately. Documented in the checker docstring. |
| The doc's `**Linked from:**` header line and the checker's I3 pin are two copies of the same consumer set that could drift apart (there is in-tree precedent: `reviewer-common.md:8`'s list vs. `check_canonical_drift.py`) | I3 is a two-way pin (§7): it asserts the scanned set against **both** the tracked files **and** the `**Linked from:**` line, so a fourth consumer fails CI until both are updated, not just the checker's internal set — and the distinct `**Linked from:**` name avoids overloading the in-tree `**Used by:**` paraphraser meaning |
| §4's grounding lines name `/planning` and `/build` machinery without either skill linking back, so an edit there could silently invalidate them | The named anchors (`/planning`'s **Consumer Migration Fan-Out**, `/build`'s `safe-partial` rollback annotation) are stable section/field names, not line numbers; a rename would surface at the next stocktake. Accepted as low-severity doc drift, not defended by a checker. |
| The §6 scan-scope exclusion of `docs/plans/`/`docs/handoffs/` means a future design or handoff doc carrying a real, broken `<!-- CANONICAL: shared/*.md -->` link would be silently unverified (no live link exists in either directory today, so nothing is masked now) | The exclusion is directory-shaped, not mention-shaped; a future real CANONICAL link added under `docs/plans/`/`docs/handoffs/` must also be recorded in the checker docstring / scan scope deliberately. |

## 11. Innovate disposition (partial accept)

Innovate proposed adding **`planning` as a fourth consumer**, with a CANONICAL
link and a `**Change shape:**` field in planning's plan-document header.

**Accepted:** the strategy-grounding content, folded into §4 above. Its core
argument is correct and sharp — this doc's own anti-pattern is "split before
submitting, not after," yet all three named consumers observe a *finished* diff
(temper and delve review one; finish is at the merge). As designed, the doc only
ever speaks at moments where acting on its main advice costs a rebase. Naming the
correspondence between the four strategies and planning's existing machinery is
the cheapest way to make the advice reach plan time, and it costs ~10 lines of
doc content with no new consumer, link, hook, or gating path.

**Declined:** the fourth consumer and the `**Change shape:**` header field, on
three grounds.

1. **It opens a gating path the other three do not.** `/planning` routes into
   `/quality-gate`, which *does* gate. A red-teamer reading `change-sizing.md`
   through a planning link could raise a sizing finding that blocks a plan —
   directly against §3's advisory-everywhere rule. Innovate identified this risk
itself and proposed to manage it with pointer wording; a constraint defended
only by prose in the very document a red-teamer is reading is not defended.
The three accepted consumers are not in that position: I9's gating-token grep
pins their non-gating constraint mechanically, where innovate's proposed
planning mitigation was prose alone.
2. **A plan has nothing to measure.** Every hook in §5 sits where the data
   already exists (`numstat`, a resolved base ref). A plan has no diff, so
   `**Change shape:**` is an uncheckable free-text field — innovate conceded it
   "can get reflexively filled with 'one change'". Uncheckable fields in a
   mandatory header template are checkbox theater, and §4's non-goals already
   forbid adding a mandatory checklist item to a consumer.
3. **Its strongest in-tree evidence does not survive checking.** Innovate cited
   `skills/build/SKILL.md:1324` as "literally the reinventing #553 names". The
   line is `"2-3 per subagent, ~10 files max" refers to plan design` — a
   *context-budget* heuristic on the same axis as temper's 5,000-line cap, not a
   reviewability judgment. It is a third instance of the axis §7 exists to
   separate, not evidence of the gap #553 names.

If plan-time sizing turns out to matter, adding `planning` later is a one-line
link — the design keeps that door open and I3's set-equality pin makes the
addition deliberate rather than silent.

**Runners-up, both correctly rejected, one worth filing.**
- *Reverse-link/orphan check* (every `shared/*.md` must have ≥1 consumer):
  rejected on measurement, and the measurement replicates — **7 of 17 shared docs
  have zero CANONICAL consumers today** (`external-review-prompt`,
  `harness-adapter`, `model-tier-policy`, `session-index-convention`,
  `severity-rubric`, `uss-approximation-patterns`, `uss-effect-decisions`). It
  would be RED on day one, destroying the "green on day one" property. That
  orphan set is independently interesting — `severity-rubric.md` is canonical for
  the whole quality-gate family and is reachable by no CANONICAL link — but it is
  not #553's problem. **File as its own issue.**
- *Ledger covariate* (record `numstat` alongside gate verdicts so the borrowed
  ~100/~300/~1000 numbers become falsifiable against this repo's own history):
  the genuinely "harder to add later" idea, but it touches `ledger-append.md`,
  `ledger_append.py`, `check_ledger_append_doc_drift.py`, and the out-of-repo
  `crucible-eval` reader, and §4's non-goals forbid sizing in delve's ledger row.
  **File as its own issue.**
