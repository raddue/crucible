# Change-Sizing Convention (#553) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Add `skills/shared/change-sizing.md` (reviewability thresholds + four named splitting strategies), link it via `<!-- CANONICAL: shared/change-sizing.md -->` from temper/delve/finish with a small non-gating advisory hook in each, and add `scripts/check_canonical_links.py` wired into `run_tests.sh`.

**Architecture:** One canonical shared doc that the three consumers link (never copy), plus a stdlib-only structural checker that (a) resolves every CANONICAL link in the tracked tree, (b) pins the three-consumer set-equality via a two-way `**Linked from:**` assertion, and (c) grep-pins the "sizing never gates" / "no new vocabulary" constraints (I4/I5/I9). TDD order: checker selftest → checker → doc → three consumers → wiring.

**Tech Stack:** Markdown + Python stdlib only. No new dependencies. `bash scripts/run_tests.sh` is the single gating entry point.

**Source of truth:** `docs/plans/2026-09-06-553-change-sizing-design.md` (approved, round-3 clean pass). Every `file:line` below was verified against that spec.

---

### Task 1: Create the checker selftest + implementation

**Files:**
- Create: `scripts/check_canonical_links.py`

**Step 1: Write the checker's `--selftest` cases first (they encode I6 and fail against the empty skeleton)**

Create `scripts/check_canonical_links.py` with only the module docstring, the `MATCH_RE` regex, and a `selftest()` that asserts the I6 cases below. Run it: every case FAILS because the resolver/pins are not yet implemented. This establishes RED.

The I6 cases (from design §7) are:
1. A valid `<!-- CANONICAL: shared/severity-verdict-contract.md -->` at column 0 → `MATCH_RE` matches, target `shared/severity-verdict-contract.md` extracted, and it resolves (file exists).
2. A missing target — `<!-- CANONICAL: shared/no-such-file.md -->` at column 0 → resolution reports `- <file>:<line> broken link` and tree check exits 1.
3. `#anchor` form — `<!-- CANONICAL: shared/delve-engine.md#cutting-rule -->` → target path `shared/delve-engine.md` extracted cleanly (anchor dropped from the path, kept in the raw group).
4. A 4-space-indented occurrence at column 4 → matched (leading whitespace allowed).
5. A blockquote/list-prefixed occurrence — `> <!-- CANONICAL: shared/... -->` and `- <!-- CANONICAL: shared/... -->` → matched.
6. Preamble-before-`CANONICAL:` — `<!-- Compass emit — orchestrator only (D14). CANONICAL: shared/... -->` → matched (must-match; the `merge-pr/SKILL.md:210` shape).
7. Backtick-wrapped decoy — `` `<!-- CANONICAL: shared/x.md -->` `` mid-sentence → NOT matched.
8. Mid-prose decoy with text before `<!--` on the same line (`> it lives in <!-- CANONICAL: shared/dispatch-convention.md --> and ...`) → NOT matched (the `harness-adapter.md:13` shape). Same for the four named decoys `CLAUDE.md:32`, `harness-adapter.md:152`, `:273`, `severity-verdict-contract.md:9` (all reworded forms in the selftest fixtures).
9. Scan-scope exclusion — a path under `docs/plans/` or `docs/handoffs/` does not enter the tracked-file set even though it matches the regex (the 241-242 backtick-span shape is excluded by scope, not by the matcher).
10. Consumer set-equality — with an artificial file list containing only 2 of the 3 consumers, the pin fails; with a fake 4th file carrying `shared/change-sizing.md`, it fails; with exactly the 3, it passes.
11. Two-way pin — a `**Linked from:**` line that disagrees with the scanned set fails; a malformed line (missing backtick) fails; a matching line passes.
12. I4/I5/I9 — a forbidden token outside §8 fails; a `5,000` line lacking `temper`/`delve` fails; a gating token within ±5 lines of a hook fails; all clean cases pass.

The selftest is written against in-memory fixture lists, never the live tree (so it is deterministic and cannot self-match).

**Step 2: Run `python3 scripts/check_canonical_links.py --selftest`** → Expected: FAIL (resolver/pins undefined).

**Step 3: Implement the checker (complete)**

Write the full implementation — stdlib-only, exit 0 clean / 1 with `- <error>` lines per `CHECKER_CONVENTIONS.md` §3:

```python
#!/usr/bin/env python3
"""CANONICAL link checker (#553 change-sizing).

Invocation (from repo root):
    python3 scripts/check_canonical_links.py              # check tracked tree
    python3 scripts/check_canonical_links.py --selftest   # built-in logic tests

Responsibility 1 — general link resolution. Every `<!-- CANONICAL: shared/*.md -->`
link in a tracked `.md` resolves to an existing `skills/<target>`. Scan scope:
`git ls-files "*.md"` minus `docs/plans/` and `docs/handoffs/` (documented scope
decision — design docs / handoffs carry prose + backtick examples; see the design
doc §6). Column-0 anchoring per CHECKER_CONVENTIONS.md §2: the match rule below.

Responsibility 2 — consumer set-equality pin (I3). The tracked `.md` files carrying
`<!-- CANONICAL: shared/change-sizing.md -->` equal exactly
{skills/temper/SKILL.md, skills/delve/SKILL.md, skills/finish/SKILL.md}, AND equal
`change-sizing.md`'s own `**Linked from:**` list (backticked full POSIX-relative
paths, comma-separated).

Plus I4/I5/I9 grep pins (design §7). Stdlib only.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {"node_modules", ".git", ".worktrees"}

# Match rule (design §6). Built so this source file never self-matches.
MATCH_RE = re.compile(
    r'^[ \t]*(?:>[ \t]*)*(?:[-*+][ \t]+)?<!--[^>]*?CANONICAL:[ \t]*'
    r'(shared/[^\s#>]+\.md)(#\S*)?[ \t]*(?:[^>]*?)-->'
)

SCAN_EXCLUDE_PREFIXES = ("docs/plans/", "docs/handoffs/")
CHANGE_SIZING = "shared/change-sizing.md"
CONSUMERS = {
    "skills/temper/SKILL.md",
    "skills/delve/SKILL.md",
    "skills/finish/SKILL.md",
}
I4_TOKENS = ("Nit", "FYI", "Optional:", "Consider:")
I9_TOKENS = ("STOP", "hard stop", "BLOCK", "must not proceed")
I9_WINDOW = 5


def tracked_md_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()
    return [f for f in out if not f.startswith(SCAN_EXCLUDE_PREFIXES)]


def find_links(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line_no, target) for every line matching MATCH_RE."""
    found = []
    for i, line in enumerate(lines, 1):
        m = MATCH_RE.match(line)
        if m:
            found.append((i, m.group(1)))
    return found


def read(path: str) -> list[str]:
    return (ROOT / path).read_text(encoding="utf-8").splitlines()


def resolve_target(target: str) -> bool:
    # target is `shared/x.md`; resolve to `skills/shared/x.md`.
    return (ROOT / "skills" / target).is_file()
```

Then implement the four checks and `selftest()`. The exact shape mirrors the sibling checkers (`check_i2_marker.py`, `check_crossref.py`): a `main(argv)` returning list-of-error-strings, exit `1` + `- <error>` lines when non-empty.

**Step 4: Run `--selftest`** → Expected: PASS (every I6 case green).

**Step 5: Run `python3 scripts/check_canonical_links.py`** → Expected: exit 1 with `- skills/... missing` errors ONLY for `shared/change-sizing.md` (the doc does not exist yet); no other broken links, because the 83 live links all resolve.

**Step 6: Commit** `git add scripts/check_canonical_links.py && git commit -m "feat(checker): #553 canonical link resolver + I3/I4/I5/I9 pins (selftest-first)"`

---

### Task 2: Write `skills/shared/change-sizing.md`

**Files:**
- Create: `skills/shared/change-sizing.md`

**Step 1: Write the complete doc** (house style per `severity-verdict-contract.md` / `delve-engine.md`; target ~110-140 lines). Content (verbatim intent from design §4 — write it out, do not summarize):

```markdown
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
it. Three bands, keyed to *changed* lines (`git diff --numstat` added+deleted):

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

`temper:126` and `delve:95` cap diffs at >5,000 lines because a *reviewing agent's* recall
degrades past that (remedy flag: `degraded-context`). This doc's numbers are about a *human*
missing a defect or being unable to revert. Same unit (`numstat` lines), different axis, 5×
apart. Neither supersedes the other, and this doc does not move temper/delve's 5,000-line
caps. The one legitimate contact point: `temper`'s "offer to split per-commit or per-file" is
an unnamed instance of Stack / By-file-group; §4 names it.

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
```

(Note: the `**Consumed via**` line above stays backtick-wrapped mid-line — the checker's own
regex would otherwise read it as a fourth consumer of `change-sizing.md` and trip I3.)

**Step 2: Run `python3 scripts/check_canonical_links.py`** → Expected: the `shared/change-sizing.md` target now exists, so resolution errors drop; the checker instead reports the I3 RED `- consumer set is {} expected {temper,delve,finish}` (no links yet).

**Step 3: Commit** `git add skills/shared/change-sizing.md && git commit -m "docs(shared): #553 change-sizing convention (thresholds + splitting strategies)"`

---

### Task 3: Link + hook in `temper`

**Files:**
- Modify: `skills/temper/SKILL.md:15` (after header CANONICAL cluster) and `:127` (sixth classification bullet)

**Step 1: Add the CANONICAL link after the existing cluster.** After the `severity-verdict-contract` block that ends at `:15`, add one link block (comment + one pointer line, mirroring the existing three):

```markdown
<!-- CANONICAL: shared/change-sizing.md -->
Sizing thresholds are human-reviewability guidance temper *surfaces*, never gates on: sizing never enters `T`; distinct from Step 1.5's 5,000-line context cap; the named strategies are what the "split per-commit or per-file" offer resolves to.
```

**Step 2: Add the sixth classification bullet.** After the `>5,000`-line bullet (`:126`) and its blank slot (`:127`), append one bullet to the `inspect:` list — outside the `>5,000` branch, gated by the shared ~300 firing condition:

```markdown
- **Reviewability note** (when added+deleted exceeds ~300 lines, per `change-sizing.md`): record the changed-line count as a non-gating round-metadata note and name the applicable splitting strategy. Independent of the `degraded-context` flag in the `>5,000` bullet above — a different axis.
```

**Step 3: Run `python3 scripts/check_canonical_links.py`** → Expected: I3 RED now reports `{temper}` present (1 of 3). Confirm no gating token tripped I9's ±5-line window.

**Step 4: Commit** `git add skills/temper/SKILL.md && git commit -m "feat(temper): #553 link change-sizing + non-gating sizing note"`

---

### Task 4: Link + hook in `delve`

**Files:**
- Modify: `skills/delve/SKILL.md:15` (header cluster) and `:120` (Step 3 run-level line)

**Step 1: Add the CANONICAL link after the existing cluster (after `:15`):**

```markdown
<!-- CANONICAL: shared/change-sizing.md -->
Sizing thresholds are human-reviewability guidance delve *reports*, never gates on: a sizing observation is a property of the run's scope, never a verdict or a record field.
```

**Step 2: Extend the Step 3 run-level line (diff scope).** For **diff** scope, add a one-clause sizing observation to the run-level `scope`/`effort` line — never an eight-field record (no single reproduction ⇒ fails `delve-engine`'s cutting rule) and never in the ledger row. For **path** scope, no diff exists, so no sizing observation is printed — a specified outcome, not an omission.

**Step 3: Run `python3 scripts/check_canonical_links.py`** → Expected: I3 RED `{temper, delve}` (2 of 3).

**Step 4: Commit** `git add skills/delve/SKILL.md && git commit -m "feat(delve): #553 link change-sizing + scope-level sizing report"`

---

### Task 5: Link + hook in `finish` (point-of-use)

**Files:**
- Modify: `skills/finish/SKILL.md:101` (between `:100` "Do not silently pick the first match." and `:102` `### Step 5`)

**Step 1: Add link + hook together at the point of use** (finish consults sizing once, at Step 4/5 where the base ref exists — so the link lives here, not in the header which carries only `dispatch-convention`):

```markdown
<!-- CANONICAL: shared/change-sizing.md -->
Measure `git diff --numstat <base>..HEAD` (two-dot, matching temper's two-dot range — both diff the base ref's tip against HEAD, never the merge base). If past the reviewable band, say so and name the applicable strategy. Advisory input to the merge-vs-PR-vs-stack choice, not a gate.
```

**Step 2: Run `python3 scripts/check_canonical_links.py`** → Expected: I3 GREEN — consumer set now exactly `{temper, delve, finish}`, and the `**Linked from:**` line agrees (two-way pin passes).

**Step 3: Commit** `git add skills/finish/SKILL.md && git commit -m "feat(finish): #553 link change-sizing + advisory sizing input"`

---

### Task 6: Wire the checker into `run_tests.sh`

**Files:**
- Modify: `scripts/run_tests.sh` — insert two `run` lines in the `# --- Structural / canonical checks ---` block, immediately after the `check_crossref.py` pair (`:95`) and before `catalog.py check` (`:96`), selftest-first per house rule.

```bash
run python3 scripts/check_canonical_links.py --selftest
run python3 scripts/check_canonical_links.py
```

**Step 2: Run `python3 scripts/check_canonical_links.py --selftest` and the tree check** → Expected: both green.

**Step 3: Run `bash scripts/run_tests.sh`** → Expected: all suites pass (this is I8 / AC 6).

**Step 4: Commit** `git add scripts/run_tests.sh && git commit -m "test: #553 wire check_canonical_links into gating suite"`

---

## Task dependencies

Sequential: Task 1 (checker, incl. selftest) → Task 2 (doc, unblocks I3 resolution path) → Tasks 3-5 (consumers; independent of each other, may be parallel) → Task 6 (wiring, last).

## Acceptance criteria (from design §9)

1. `skills/shared/change-sizing.md` exists with §§1-9, ~110-140 lines, shared/ house style.
2. temper/delve/finish each carry the CANONICAL link at the specified point with a consumer-specific pointer (not three copies of one sentence).
3. Each hook is present, non-gating (I9 passes), at the specified step, firing only above the ~300 middle band.
4. `scripts/check_canonical_links.py` passes `--selftest`, resolves every link, and asserts I3 against both the scanned tree and `**Linked from:**`; enforces I4/I5/I9; exits 0 on the tree.
5. Both `run` lines in `run_tests.sh`.
6. `bash scripts/run_tests.sh` green.
7. No new severity/verdict tier; §8's table is refusal-only.
8. I4/I5/I9 hold.