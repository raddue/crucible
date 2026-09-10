# Change Sizing — Reviewability Thresholds + Splitting Strategies

> **Guidance-only** sizing advice for implementers and reviewers: when a change is too
> big to review safely, and how to split one. **Advisory — never gating, anywhere.** No
> consumer turns a size reading into a verdict, a gate, a merge refusal, or a checklist
> item. Scope: changed-line counts and total file size as *human-reviewability* signals —
> **not** the context-window caps `temper`/`delve` apply at >5,000 lines (a different axis;
> see §7).
>
> **Consumed via** `<!-- CANONICAL: shared/change-sizing.md -->` — link this file, never
> copy its tables (copying causes drift).
>
> **Linked from:** `skills/temper/SKILL.md`, `skills/delve/SKILL.md`, `skills/finish/SKILL.md`

## 1. Reviewability thresholds

A human reviewer holds a diff in working memory to spot defects and to know how to revert
it. Three thresholds, keyed to *changed* lines (`git diff --numstat` added+deleted),
with `above ~1000` as the tail:

| Changed lines | Reviewability |
|---|---|
| ~ up to 100 | Comfortably reviewable in one pass. |
| ~ up to 300 | Needs structure (split by concern or by commit). |
| ~ up to 1000 | Hard: reviewer invariants degrade; prefer splitting. |
| above ~1000 | Split before asking a reviewer to approve it. |

These are heuristics, not rules. Small is not automatically correct, and large is not
automatically wrong — the gate is *reviewability*, not a count.

## 2. What counts as "one change"

One self-contained modification addressing **one** thing, including its tests, leaving the
system functional. One part of a feature, not the whole feature. Without this definition,
"~100 lines" is an arbitrary number.

## 3. File size is a separate signal

~1000 *total* lines in a single file is an inspection signal distinct from ~1000 *changed*
lines: a small diff can push an already-large file past a healthy boundary. Decompose, then
add.

## 4. Splitting strategies

| Strategy | How | When |
|---|---|---|
| Stack | Submit a small change, start the next on top of it. | Sequential dependencies. |
| By file group | Separate changes for groups needing different reviewers. | Cross-cutting concerns. |
| Horizontal | Shared code/stubs first, then consumers. | Layered architecture. |
| Vertical | Smaller full-stack slices of the feature. | Feature work. |

These map onto machinery the repo already has: **Stack** ≡ a `Dependencies` chain across
plan tasks; **By file group** ≡ planning's **Consumer Migration Fan-Out**
(`skills/planning/SKILL.md`); **Horizontal** ≡ planning's shared-code-first ordering;
**Vertical** ≡ full-stack slices. §2's "system still functional after" is `/build`'s
plan-writer `safe-partial` rollback annotation.

## 5. When a large change is acceptable

Complete file deletions; mechanical or automated refactors where the reviewer verifies
intent, not every line; generated files. This escape valve is load-bearing — without it the
thresholds get cargo-culted into a hard rule, which §3 forbids.

## 6. Separate refactoring from feature work

Two changes, submitted separately; small cleanups may ride along at reviewer discretion.

## 7. These are not context-window caps

`temper`'s **Diff too large** bullet and `delve`'s **Oversized diff** bullet cap diffs at >5,000 lines.
A *reviewing agent's* recall degrades past that (remedy flag: `degraded-context`). This
doc's numbers are about a *human* missing a defect or being unable to revert. Same unit
(`numstat` lines), different axis, 5× apart. Neither supersedes the other, and this doc does
not move temper/delve's 5,000-line caps. The one legitimate contact point: `temper`'s "offer
to split per-commit or per-file" is an unnamed instance of Stack / By-file-group; §4 names it.

## 8. Comment-prefix vocabulary — deliberately not adopted (#553)

The source's `Critical:`/`Nit:`/`Optional:`/`Consider:`/`FYI` prefixes overlap the trio's
four tiers plus a gating flag:

| Source prefix | Existing Crucible equivalent |
|---|---|
| `Critical:` | trio `Critical` |
| *(no prefix)* = required | trio `Important` |
| `Nit:` | trio `Minor` |
| `Optional:` / `Consider:` | trio `Suggestion` |
| `FYI` | no equivalent — the trio reports every kept finding at its own tier |

Which of these gate is defined once, in `shared/severity-verdict-contract.md` — link, don't
restate. Adopting the source's prefixes as a parallel scale would be a second name for a
distinction the repo already makes. Unifying the two existing scales is a separate, larger
change; this doc does not attempt it.

## Anti-patterns

Do not: treat a threshold as a merge gate; add a sizing item to a mandatory checklist; split
for splitting's sake when the change is already one reviewable unit; or promise to "split
this change later" — split before submitting, not after.