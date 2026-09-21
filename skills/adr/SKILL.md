---
name: adr
description: Write, supersede, and maintain Architecture Decision Records (docs/decisions/) for technical choices that had real, seriously-considered alternatives and would be costly to reverse. Use on "write an ADR", "record this decision", or when recording a choice that a design or PR already settled. Matches the target repo's existing ADR convention before imposing one, and declines with a reason when a decision does not meet the bar — not for routine design docs, implementation plans, session handoffs, the pre-push/merge wrap-up itself (that belongs to `finish` / `merge-pr`), or answering "why did we choose X" from an ADR that already exists (that's a read, owned by `recall` / `recon`).
---

# Architecture Decision Records

Write, supersede, and maintain Architecture Decision Records. An ADR records a
decision the user already made — why it was made, what was rejected, and what it
costs to reverse. It is not a gate, a review, or a prompt to re-decide.

**Announce at start:** "I'm using the adr skill to record a decision."

## Eligibility — run first, write nothing when it fails

Run the eligibility test before writing anything. All three conditions must hold:

1. **Real alternatives.** At least one other approach was seriously considered
   and rejected — with a reason that is not "we didn't think of it."
2. **Costly to reverse.** Undoing the decision later means migrating data,
   breaking a public interface, re-training people, or re-running work.
3. **Rationale not durably recorded.** The reasoning is not written down in one
   findable place a future reader would actually check — scattered across commit
   messages, issue threads, test docstrings, or policy-table rows counts as *not
   recorded*, even though it technically exists somewhere.

If any condition fails, refuse: write no file, and report which condition failed
and why. Refusal is a correct outcome, not a failure.

**Cap — at most one ADR per firing (at most two per `/build`).** When several
dimensions of one document pass all three conditions, write only the single most
durable dimension. Rank by condition-2's kind, highest first: **data/schema
migration > public-interface break > re-training people > re-running work**; a
tie within a kind is broken by your judgment, and the reason is narrated in the
declined-by-cap report. Report the rest as declined-by-cap, by name.

## Match the target repo's convention first

Before writing, establish what convention the *target repo* already uses, in
this precedence order:

1. Explicit tool config — `.adr-dir`, `.adr.json`, an `adr-tools` setup.
2. Existing decision files — `docs/decisions/`, `docs/adr/`, `doc/adr/`,
   `docs/architecture/decisions/`, `adr/`, `Documentation/Decisions/`.
3. Project instructions — `CLAUDE.md`, `CONTRIBUTING.md`, `AGENTS.md` naming an
   ADR location or format.
4. Crucible default (only when 1–3 come up empty).

Match: **location**, **file extension/markup**, **filename pattern**, **numbering
sequence** (continue it; never restart at 1), and **section heading set** (reuse
theirs rather than imposing the template below).

**Conflict rule.** If the evidence disagrees (e.g. `.adr-dir` points at
`doc/adr` but files live in `docs/decisions`), surface the conflict and ask.
Never silently pick one, and never introduce a second scheme alongside an
existing one.

**Never drop the alternatives-and-reasons content.** If the matched heading set
has no `Alternatives Considered` section, fold that content into the matched
`Context` (or nearest equivalent) under an explicit "Alternatives considered:"
lead-in, and narrate the adaptation.

## Numbering

Default `docs/decisions/NNNN-kebab-title.md`, zero-padded to 4. Before claiming
`N`: `git fetch --all --prune`, then scan (a) `docs/decisions/` including
uncommitted files, and (b) `git log --all --diff-filter=A --name-only --
docs/decisions/`. Claim `max(both) + 1`.

Numbers are permanent once they reach the default branch. A genuine post-merge
collision (the race the numbering re-check makes rare, not impossible) is
repaired by renaming the second-merged file to the next free number and adding a
`Renumbered-from ADR-<original>` line below its `## Status` state token.

## Lifecycle

Three states: `PROPOSED` (drafted, decision not yet ratified), `ACCEPTED` (in
force — the normal state of an ADR recording a decision already made), and
`SUPERSEDED by ADR-NNNN` (replaced; carries a pointer to the replacing ADR).

Superseding is always a **two-file edit**: the new ADR's `## Status` gains a
`Supersedes ADR-NNNN` line below its state token, and the old ADR's state token
is rewritten to `SUPERSEDED by ADR-MMMM`. Old ADRs are never deleted or
rewritten in place.

## Template

```markdown
# ADR-0007: <Decision in imperative form>

## Status
ACCEPTED

## Date
2026-09-10

## Context
<Forces and constraints, in timeless language.>

## Decision
<What was chosen, plainly.>

## Alternatives Considered

### <Alternative A>
- Pros: …
- Cons: …
- Rejected: <the specific reason, not "worse">

## Consequences
<What this makes easy, what it makes hard, what must now be true.>
```

Where a rejected alternative cannot be sourced from the repo, record the omission
explicitly — a single `Rejected: (no alternative recoverable from the repo
record)` line — rather than leaving the section empty or inventing an
alternative.

## Outputs

| Outcome | What you write |
|---|---|
| Accept | `<detected-dir>/NNNN-kebab-title.md` |
| Supersede | The above **plus** an edit to the superseded ADR's `## Status` (both or neither) |
| Refuse | No file; a one-paragraph report naming the failed condition |

## Integration

**Called by:** `crucible:design` (Hook 1, writes `PROPOSED` at design time) and
`crucible:finish` (Hook 2, promotes to / writes `ACCEPTED` before the review
gate). Also usable standalone — `/adr` or "write an ADR".