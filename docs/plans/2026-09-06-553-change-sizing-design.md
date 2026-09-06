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
  (`skills/temper/SKILL.md:25`). Consumers are **temper, delve, finish**.
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
| temper | `git diff --numstat` at Step 1.5 (`:120`) + non-gating round-metadata flags (`:123`, `:124`, `:126`) | ~2 lines |
| delve | same numstat preflight (`:95`) + a run-level scope/effort report line (`:120`) | ~2 lines |
| finish | a resolved base ref after Step 4 (`:85-100`) | ~4 lines |

**Everything the hook emits is advisory. Sizing never gates, anywhere.**
`delve` never gates at all (`:122`); `temper`'s Clean condition is closed over the
tracked set `T` (`:289`) and adding sizing would redefine Clean; `finish`'s only
hard stops are warden `BLOCKED` (`:52`) and a Step 5.5 non-zero exit (`:123`).
An oversized-but-correct branch must remain mergeable.

## 4. The artifact — `skills/shared/change-sizing.md`

House style follows the newest shared/ docs (`severity-verdict-contract.md`,
`delve-engine.md`): H1 with em-dash subtitle, a blockquote header declaring
purpose + scope boundary + `**Consumed via**` idiom + `**Used by:**` consumer
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
   | `Critical:` | trio `Critical` (gating) |
   | *(no prefix)* = required | trio `Important` (gating) |
   | `Nit:` | trio `Minor` (non-gating) |
   | `Optional:` / `Consider:` | trio `Suggestion` (non-gating) |
   | `FYI` | no equivalent — the trio reports every kept finding at its own tier |

   The C/I gating band (`severity-verdict-contract.md:58-74`) already does the
   work `(no prefix) = required` does. Adopting the prefixes would be a second
   name for a distinction the repo already makes — the exact drift the
   link-don't-copy rule exists to prevent — and §6 forbids `Nit` by name. State
   the reopening condition: unifying the two existing scales is a separate,
   larger change, and this doc does not attempt it.
9. **Anti-patterns** (`Do not:` list), including the source's
   "I'll split this change later" → split before submitting, not after.

### Non-goals (stated in the doc)

The doc must **not**: define/extend/alias/map any severity or verdict vocabulary;
make any threshold gating; restate or move the 5,000-line context caps or relate
itself to `cap`/`cap-saturation` (findings counts, not lines); claim `/audit`'s
systemic territory ("too much changed at once" as a no-single-reproduction
pattern); overlap the `altitude` angle or the `Surgical Changes` lens (which
judge *where* code sits and *scope bleed*, not *how many lines*); prescribe
engine inputs; or add a mandatory checklist item to any consumer.

## 5. Consumer integration

| Consumer | Insertion point | Pointer says |
|---|---|---|
| **temper** | after `SKILL.md:15`, joining the header CANONICAL cluster (`:8`, `:11`, `:14`) | Sizing thresholds are human-reviewability guidance temper *surfaces*, never gates on; sizing never enters `T`; distinct from Step 1.5's 5,000-line context cap; the named strategies are what `:126`'s "split per-commit or per-file" resolves to. Hook: a non-gating round-metadata note at Step 1.5 alongside `degraded-context`. |
| **delve** | after `SKILL.md:15`, same header cluster shape (`:8`, `:11`, `:14`) | delve is report-only and never gates, so a sizing observation is a property of the *run's scope*, printed on the Step 3 run-level line — never an eight-field record (no single reproduction ⇒ fails delve-engine's cutting rule, `delve-engine.md:19-27`) and never in the ledger row. |
| **finish** | point-of-use, between `SKILL.md:100` and `:102` — i.e. after Step 4 resolves the base ref, before Step 5 presents options | Measure `git diff --numstat <base>..HEAD`; if past the reviewable band, say so and name the applicable strategy. Advisory input to the merge-vs-PR-vs-stack choice. |

`finish` uses point-of-use placement because that is its existing idiom — its
other canonical links sit mid-file at the step that uses them (`:171`, `:282`),
not in the header. Placement is **after** warden (Step 2, `:43-56`), because
warden hard-REFUSES on an unclean tree and a sizing advisory before that gate
would be noise on a run about to refuse. It is **not** added to the Gate
Execution Ledger checklist (`:455-465`) — every item there is mandatory and an
unchecked box means STOP.

**Why round-metadata and not a Suggestion finding, in temper.** A Suggestion
record implies a finder angle, and `severity-verdict-contract.md:99-107`'s
angle→severity map has no angle that owns "diff size". A metadata flag carries no
severity and no verdict, so it sits outside I11's surface entirely. (There is
precedent for the other choice — `temper:124` raises a Suggestion from inside
preflight for the submodule case — so this is a judgment call, recorded as such.)

## 6. API surface

One new script, `scripts/check_canonical_links.py`, stdlib-only, exit 0 clean /
1 with a `- <error>` list per `scripts/CHECKER_CONVENTIONS.md` §3.

```
python3 scripts/check_canonical_links.py            # check the tracked tree
python3 scripts/check_canonical_links.py --selftest # built-in logic tests
```

**Shape: globbing over `git ls-files "*.md"`**, never `*.py`. Path-pinning cannot
express "*every* CANONICAL link resolves" — it would need the file list up front,
which is the thing that drifts. Scanning only `*.md` satisfies
`CHECKER_CONVENTIONS.md` §2's self-match discipline the same way
`check_i2_marker.py` does: the checker's own source is unreachable.

**Match rule.** After stripping leading whitespace and optional blockquote (`>`)
and list (`-`/`*`/`+`) markers, the line must *start with* the CANONICAL comment:

```
^[ \t]*(?:>[ \t]*)*(?:[-*+][ \t]+)?<!--[ \t]*CANONICAL:[ \t]*(shared/[^\s#>]+\.md)(#\S*)?[ \t]*(?:[^>]*?)-->
```

Verified empirically against the tree at HEAD `1888642`: **82 links, 10 targets,
0 broken.** A general checker is therefore green on day one — no scope trap.

This rule is deliberately chosen over a strict whole-line anchor, which misses
two real links: `skills/siege/SKILL.md:52` (list item with trailing prose) and
`skills/shared/delve-engine.md:10` (blockquote). It excludes all four known
decoys — `CLAUDE.md:32` (`shared/x.md`, illustrative), `harness-adapter.md:152`
and `:273` (`<!-- CANONICAL: ... -->` ellipsis placeholders), and the
backtick-wrapped `**Consumed via**` self-reference at
`severity-verdict-contract.md:9` — because each begins with prose or a backtick,
not the comment. **The new doc's own `**Consumed via**` header line must stay
backtick-wrapped mid-line for this reason**, or it counts as a fourth consumer.

## 7. Invariants

**Checkable (by inspection / grep):**
- I1 — `skills/shared/change-sizing.md` exists.
- I2 — every `<!-- CANONICAL: shared/*.md -->` link in a tracked `.md` resolves to
  an existing `skills/<target>`. *(check_method: the new checker)*
- I3 — the set of files carrying `<!-- CANONICAL: shared/change-sizing.md -->` is
  exactly `{skills/temper/SKILL.md, skills/delve/SKILL.md, skills/finish/SKILL.md}` —
  set **equality**, so both a missing consumer and a stray fourth fail.
- I4 — `change-sizing.md` contains no `Nit`, `FYI`, `Optional:`, or `Consider:`
  token outside its §8 non-adoption table, and defines no severity tier.
- I5 — `change-sizing.md` does not restate the number 5,000 as its own threshold.

**Testable (require the test to run):**
- I6 — `--selftest` passes: resolving link OK; missing target detected with
  `file:line`; `#anchor` and `— Section` suffix forms matched with the path
  extracted cleanly; 4-space-indented occurrence matched; each of the four decoy
  forms NOT matched; consumer set-equality fails on both a missing and an extra
  consumer.
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
3. Each consumer's advisory hook is present, non-gating, and placed at the
   specified step.
4. `scripts/check_canonical_links.py` exists, passes `--selftest`, and exits 0 on
   the tree.
5. Both `run` lines are in `scripts/run_tests.sh`.
6. `bash scripts/run_tests.sh` is green.
7. No severity/verdict vocabulary is added anywhere.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Reader fuses the ~1000 reviewability threshold with the 5,000 context cap and assumes 5,000 supersedes it — making the doc dead on arrival inside temper | §7 of the doc states the two axes explicitly; both consumer pointers repeat the distinction in one clause |
| Thresholds get cargo-culted into a hard gate | §5's "when a large change is acceptable" escape valve, plus the advisory-everywhere rule in §3, plus an anti-pattern row |
| §8's non-adoption table re-introduces the forbidden vocabulary by quoting it | The tokens appear only inside a table whose column header is "Source prefix" and whose stated purpose is refusal; I4 pins that they appear nowhere else |
| The general link checker later false-FAILs on a legitimately new comment form | The match rule and its four excluded decoys are documented in the checker docstring; loosening the regex is a deliberate edit, not a silent one |
| A future skill adds a fourth `change-sizing.md` consumer and I3's set-equality fails | Intended — the failure is the signal to update the pin deliberately. Documented in the checker docstring. |
