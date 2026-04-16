---
ticket: "#178"
epic: "#178"
title: "Simplify-ignore hook for protected code regions"
date: "2026-04-16"
source: "spec"
---

# Simplify-ignore hook for protected code regions — Design

## Context

Inspired by [addyosmani/agent-skills]'s `simplify-ignore.sh` (~200 line PreToolUse/PostToolUse hook
that masks marker-delimited code with placeholder hashes while an agent reads a file, then expands
placeholders back on Write). The observed failure this guards against: a "simplifier" agent
repeatedly rewriting intentionally-complex code (state machines, hand-tuned parsers, deliberately
verbose validators) because it reads "simpler" without understanding the constraint.

Crucible's `simplify` skill reviews recently-changed code for reuse / quality / efficiency and
applies fixes. Ticket #178 asks us to give authors an opt-out marker they can wrap around code
the simplifier must leave alone.

**Priority: LOW.** This is a bookmarked idea, not a felt pain. The design is intentionally scoped
down; we document the more-invasive upgrade path as a follow-up rather than build it now.

## Goals

1. Authors can mark a code range as "do not simplify" with an inline comment pair.
2. The `simplify` skill respects those ranges during its review → diff → apply loop.
3. If a simplify-produced diff would modify a protected range, the orchestrator rejects the diff.
4. Marker syntax covers JS/TS, CSS, HTML, and hash-comment languages (shell/YAML/Python) at minimum.

## Non-goals

- Protecting regions from arbitrary edits (e.g. `/build` implementer writes, manual agent edits).
  Scope is limited to the `simplify` skill.
- IDE integration, syntax highlighting for the markers, or tooling to insert them.
- Protecting regions inside binary files, generated files, or minified bundles.

## Design

### DEC-1 (medium confidence): Hook type — pick Option B

Three options considered:

- **Option A — PreToolUse + PostToolUse hooks** (addyosmani's approach). Masks protected ranges
  in Read output with `BLOCK_<hash>` placeholders and unmasks them on Write. Fully transparent to
  the agent. ~200 lines of shell, atomic `mkdir`-based locking, fuzzy-matching if the agent
  rewrites a placeholder, backup/restore lifecycle.
- **Option B — Skill-level marker respect.** The `simplify` skill scans target files for markers
  before dispatching a simplifier subagent, excludes those ranges from the subagent's scope, and
  validates diffs against the protected set before applying.
- **Option C — Dispatch-manifest trust.** Include `protected_ranges: [...]` in the subagent prompt
  and trust it to self-enforce. No validation.

**Decision: Option B** for the MVP.

Reasoning: the ticket is explicitly a bookmark ("worth tracking even if we don't build
immediately"). 200 lines of transparent-hook infrastructure with its own atomic-locking and
restore logic is a lot of surface area to maintain for a problem we haven't actually observed
biting us. Option B delivers every acceptance criterion the `simplify` context cares about
(protected ranges survive the pass, multi-syntax markers, warning diagnostics on malformed
markers) without a file-rewriting hook. If we later observe the problem spreading outside
`simplify` (e.g. `/build` refactor mode eats a protected parser), Option A is a purely additive
upgrade — markers and semantics stay identical.

Reversibility: **high**. Option A reads the same markers; no migration burden.

### DEC-2 (high confidence): Marker syntax

Line-level markers, one-per-line, case-sensitive, longest-prefix-strip when matching:

| Language family        | Start marker                             | End marker                             |
|------------------------|------------------------------------------|----------------------------------------|
| JS / TS / Java / C-like| `// simplify-ignore-start`               | `// simplify-ignore-end`               |
| CSS                    | `/* simplify-ignore-start */`            | `/* simplify-ignore-end */`            |
| HTML / XML / Vue       | `<!-- simplify-ignore-start -->`         | `<!-- simplify-ignore-end -->`         |
| Shell / Python / YAML  | `# simplify-ignore-start`                | `# simplify-ignore-end`                |

Rules:

- Markers must appear on their own line (optionally indented). Trailing explanatory text after
  the marker keyword is allowed and ignored, e.g. `// simplify-ignore-start: hand-tuned hot loop`.
- Pairs nest only trivially (one start → next end closes it). Nested pairs produce a warning and
  the outer pair wins.
- Unbalanced markers (unclosed start, orphan end) produce a warning diagnostic and the skill
  falls back to "protect from marker to EOF" for an unclosed start, and ignores an orphan end.

### DEC-3 (high confidence): Warning diagnostics (AC #4)

The `simplify` orchestrator emits diagnostics in two situations:

1. **Malformed markers** during pre-scan: unclosed start, orphan end, nested pair, marker inside
   a string literal (detected heuristically). Diagnostic lists file + line + reason.
2. **Diff touches a protected range**: after the simplifier subagent returns a diff, the
   orchestrator maps each diff hunk to line ranges and rejects any hunk whose target range
   intersects a protected range. The subagent is asked to retry with the protected ranges
   explicitly excluded; if the retry still violates, the skill aborts the fix and reports.

### Acceptance criteria mapping

| AC                                                         | Mechanism                            |
|------------------------------------------------------------|--------------------------------------|
| Marked blocks survive simplification passes unchanged      | DEC-1 Option B, pre-scan + validation |
| Multi-syntax comment support (JS, HTML, CSS at minimum)    | DEC-2 marker table                   |
| Atomic backup/restore — no data loss on crash              | Trivially satisfied: Option B never rewrites protected regions, so nothing to restore |
| Warning diagnostics for malformed markers                  | DEC-3                                 |

## Alternatives considered

- **Option A (PreToolUse hook)** — rejected for MVP; see DEC-1. Tracked as follow-up for when we
  observe simplify-style rewrites leaking into other skills.
- **Option C (trust-only)** — rejected: AC #1 explicitly says "survive unchanged", which requires
  a validation check, not pure trust.
- **`.simplifyignore` glob file** (analogous to `.gitignore`) — rejected: too coarse. Authors want
  to protect a function body, not an entire file.

## Open questions

- Should we support a `simplify-ignore-file` top-of-file directive that protects the whole file?
  Deferred; easy to add later without breaking range-based markers.
- Should the markers share syntax with a hypothetical future `build-ignore-start` / `refactor-
  ignore-start`? Deferred until we have a second consumer.

## Follow-ups

- **Upgrade to Option A (PreToolUse/PostToolUse hook)** — trigger when any of the following are
  observed:
  1. A non-`simplify` skill (e.g. `/build` refactor mode, `/migrate`) modifies a marked region.
  2. A manual agent edit (user-invoked Write/Edit) destroys a marked region and the author reports
     surprise.
  3. The `simplify` diff-validation gate rejects > 5% of diffs across a rolling 30-day window,
     suggesting the subagent can't self-exclude reliably from prompt alone.
  With the same marker syntax and semantics reused verbatim. Estimated effort: ~2 days including
  the atomic-lock + backup/restore plumbing. No migration needed — existing marked files Just Work
  under Option A.
