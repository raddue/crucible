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

Create `scripts/check_canonical_links.py` with only the module docstring, the `MATCH_RE` regex, a `selftest()` that asserts the I6 cases below, and stub definitions for the helpers the selftest calls (`find_links`, `resolve_target`, `in_scan_scope`, `carrier_pin_violations`, `linked_from_violations`, `linked_from_paths`, `i4_violations`, `i5_violations`, `i9_doc_violations`, `i9_hook_violations`) that return empty/false so each case fails on its assertion, not on an import/NameError. Run it: every case FAILS because the resolver/pins are not yet implemented. This establishes RED.

The I6 cases (from design §7) are:
1. A valid `<!-- CANONICAL: shared/severity-verdict-contract.md -->` at column 0 → `MATCH_RE` matches, target `shared/severity-verdict-contract.md` extracted, and it resolves (file exists).
2. A missing target — `<!-- CANONICAL: shared/no-such-file.md -->` at column 0 → resolution reports `- <file>:<line> broken link` and tree check exits 1.
3. Suffix forms — `#anchor`: `<!-- CANONICAL: shared/delve-engine.md#cutting-rule -->` → target path `shared/delve-engine.md` extracted cleanly (anchor dropped from the path); `— Section`: `<!-- CANONICAL: shared/implementer-common.md — TDD Discipline -->` → path `shared/implementer-common.md` extracted cleanly (the em-dash suffix dropped from the path). Both are live shapes — the `— Section` form has 16+ occurrences in the tree (e.g. `skills/build/build-implementer-prompt.md:52`).
4. A 4-space-indented occurrence at column 4 → matched (leading whitespace allowed).
5. A blockquote/list-prefixed occurrence — `> <!-- CANONICAL: shared/... -->` and `- <!-- CANONICAL: shared/... -->` → matched.
6. Preamble-before-`CANONICAL:` — `<!-- Compass emit — orchestrator only (D14). CANONICAL: shared/... -->` → matched (must-match; the `merge-pr/SKILL.md:210` shape).
7. Backtick-wrapped decoy — `` `<!-- CANONICAL: shared/x.md -->` `` mid-sentence → NOT matched.
8. Mid-prose decoy with text before `<!--` on the same line (`> it lives in <!-- CANONICAL: shared/dispatch-convention.md --> and ...`) → NOT matched (the `harness-adapter.md:13` shape). Same for the four named decoys `CLAUDE.md:32`, `harness-adapter.md:152`, `:273`, `severity-verdict-contract.md:9` (all reworded forms in the selftest fixtures).
9. Scan-scope exclusion — a path under `docs/plans/` or `docs/handoffs/` does not enter the tracked-file set even though it matches the regex (the 241-242 backtick-span shape is excluded by scope, not by the matcher).
10. Consumer set-equality — with an artificial file list containing only 2 of the 3 consumers, the pin fails; with a fake 4th file carrying `shared/change-sizing.md`, it fails; with exactly the 3, it passes.
11. Two-way pin — a `**Linked from:**` line that disagrees with the scanned set fails; a malformed line (missing backtick) fails; a matching line passes.
12. I4/I5/I9 — a forbidden token outside §8 fails; a `5,000` line lacking `temper`/`delve` fails; a gating token within ±5 lines of a hook (the link line, or the temper/delve firing-clause anchor) fails; all clean cases pass.

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
I5_TOKEN = "5,000"
I5_REQUIRE = ("temper", "delve")
I9_TOKENS = ("STOP", "hard stop", "BLOCK", "must not proceed")
I9_WINDOW = 5
HOOK_ANCHOR = "CONTRACT:change-sizing-hook"


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


def in_scan_scope(path: str) -> bool:
    # A tracked `.md` path enters the scan unless it sits under docs/plans/ or
    # docs/handoffs/ (documented scope decision, design §6).
    return not path.startswith(SCAN_EXCLUDE_PREFIXES)


def fmt(s: set[str]) -> str:
    return "{" + ",".join(sorted(s)) + "}"


def carrier_pin_violations(carriers: set[str]) -> list[str]:
    """I3 (scanned-tree half): the tracked files carrying the change-sizing link
    must equal CONSUMERS exactly — a missing consumer and a stray fourth both
    fail."""
    if carriers == CONSUMERS:
        return []
    return [f"- consumer set is {fmt(carriers)} expected {fmt(CONSUMERS)}"]


def linked_from_violations(linked: set[str]) -> list[str]:
    """I3 (two-way half): the doc's `**Linked from:**` list must equal CONSUMERS
    exactly, so updating one side but not the other fails."""
    if linked == CONSUMERS:
        return []
    return [f"- **Linked from:** list is {fmt(linked)} expected {fmt(CONSUMERS)}"]


def linked_from_paths(lines: list[str]) -> list[str]:
    """Parse the `**Linked from:**` header line into its backticked path list.

    The line is a `> ` blockquote-prefixed line (the doc's header blockquote), so
    the leading `>` marker(s) are stripped before the `**Linked from:**` marker is
    located; the list is then read as backticked, comma-separated POSIX-relative
    paths — nothing else. A missing/malformed backtick yields an empty list, which
    the two-way pin then rejects.
    """
    for line in lines:
        stripped = line.lstrip()
        while stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        if stripped.startswith("**Linked from:**"):
            return re.findall(r"`([^`]+)`", stripped)
    return []


def section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(start, end) line indices for the section opened by `heading`, ending at
    the next `## ` heading (or EOF). None if the heading is absent."""
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def i4_violations(lines: list[str]) -> list[str]:
    """I4: forbidden tokens must appear only under the `## 8.` section
    (the non-adoption table). A hit anywhere else fails."""
    bounds = section_bounds(lines, "## 8.")
    errs = []
    for i, line in enumerate(lines):
        for tok in I4_TOKENS:
            if tok in line and (bounds is None or not (bounds[0] <= i < bounds[1])):
                errs.append(f"- I4 token {tok!r} appears outside §8 (line {i + 1})")
    return errs


def i5_violations(lines: list[str]) -> list[str]:
    """I5: the `5,000` token must sit on a line that also carries `temper` or
    `delve` — it names their context cap, never change-sizing's own threshold."""
    errs = []
    for i, line in enumerate(lines):
        if I5_TOKEN in line and not any(r in line for r in I5_REQUIRE):
            errs.append(f"- I5 token {I5_TOKEN!r} lacking temper/delve (line {i + 1})")
    return errs


def i9_doc_violations(lines: list[str]) -> list[str]:
    """I9 (doc half): no gating token anywhere in change-sizing.md."""
    errs = []
    for i, line in enumerate(lines):
        for tok in I9_TOKENS:
            if tok in line:
                errs.append(f"- I9 gating token {tok!r} in change-sizing.md (line {i + 1})")
    return errs


def i9_hook_violations(path: str, lines: list[str]) -> list[str]:
    """I9 (hook half): no gating token within ±I9_WINDOW lines of the consumer's
    sizing hook. Each consumer's hook is located by BOTH its CANONICAL link line —
    the one line that MATCH_RE-matches with target `shared/change-sizing.md` — AND
    its `HOOK_ANCHOR` marker on the firing-clause line, and the ±I9_WINDOW window
    around each such line is grepped for the token set. Both are needed: finish's
    link and hook are adjacent, but temper and delve keep the link in the header
    cluster while their firing clause lands ~100 lines below, so only the anchor
    locates the real hook there."""
    errs = []
    centers = []
    for i, line in enumerate(lines):
        m = MATCH_RE.match(line)
        if (m and m.group(1) == CHANGE_SIZING) or HOOK_ANCHOR in line:
            centers.append(i)
    for c in centers:
        lo = max(0, c - I9_WINDOW)
        hi = min(len(lines), c + I9_WINDOW + 1)
        for j in range(lo, hi):
            for tok in I9_TOKENS:
                if tok in lines[j]:
                    errs.append(
                        f"- I9 gating token {tok!r} within ±{I9_WINDOW} lines of "
                        f"{path}'s sizing hook (line {j + 1})"
                    )
    return errs


def main() -> int:
    files = tracked_md_files()
    errs: list[str] = []

    # I2 — every tracked CANONICAL link resolves (no broken links).
    for f in files:
        for ln, target in find_links(read(f)):
            if not resolve_target(target):
                errs.append(f"- {f}:{ln} broken link")

    # I3 — two-way consumer pin (scanned tree + doc's `**Linked from:**` list).
    carriers = {
        f for f in files
        if any(t == CHANGE_SIZING for _, t in find_links(read(f)))
    }
    errs += carrier_pin_violations(carriers)

    doc = "skills/" + CHANGE_SIZING
    if (ROOT / doc).is_file():
        doc_lines = read(doc)
        errs += linked_from_violations(set(linked_from_paths(doc_lines)))
        errs += i4_violations(doc_lines)
        errs += i5_violations(doc_lines)
        errs += i9_doc_violations(doc_lines)

    # I9 — hook neighborhoods per consumer.
    for f in CONSUMERS:
        if (ROOT / f).is_file():
            errs += i9_hook_violations(f, read(f))

    if errs:
        print("\n".join(errs))
        return 1
    print("OK — canonical links resolve; I3/I4/I5/I9 pins hold.")
    return 0


def selftest() -> int:
    """Built-in regression cases for the 12 I6 cases (in-memory fixtures, never
    the live tree)."""
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # Case 1 — valid column-0 link matches and resolves (file exists).
    one = find_links(["<!-- CANONICAL: shared/severity-verdict-contract.md -->"])
    check(one == [(1, "shared/severity-verdict-contract.md")], f"case1 match: {one}")
    check(resolve_target("shared/severity-verdict-contract.md"), "case1 resolve")

    # Case 2 — missing target yields a broken link (reported file:line, exit 1).
    two = find_links(["<!-- CANONICAL: shared/no-such-file.md -->"])
    check(two == [(1, "shared/no-such-file.md")], f"case2 match: {two}")
    check(not resolve_target("shared/no-such-file.md"), "case2 does not resolve")

    # Case 3 — `#anchor` and `— Section` suffix forms; path extracted cleanly.
    check(
        find_links(["<!-- CANONICAL: shared/delve-engine.md#cutting-rule -->"])
        == [(1, "shared/delve-engine.md")],
        "case3 anchor dropped from path",
    )
    check(
        find_links(["<!-- CANONICAL: shared/implementer-common.md — TDD Discipline -->"])
        == [(1, "shared/implementer-common.md")],
        "case3 em-dash suffix dropped from path",
    )

    # Case 4 — 4-space-indented occurrence matched.
    check(
        find_links(["    <!-- CANONICAL: shared/x.md -->"]) == [(1, "shared/x.md")],
        "case4 indent matched",
    )

    # Case 5 — blockquote / list prefix matched.
    check(find_links(["> <!-- CANONICAL: shared/x.md -->"]) == [(1, "shared/x.md")],
          "case5 blockquote matched")
    check(find_links(["- <!-- CANONICAL: shared/x.md -->"]) == [(1, "shared/x.md")],
          "case5 list matched")

    # Case 6 — preamble-before-CANONICAL matched (the merge-pr/SKILL.md:210 shape).
    check(
        find_links([
            "<!-- Compass emit — orchestrator only (D14). CANONICAL: shared/compass-protocol.md -->"
        ]) == [(1, "shared/compass-protocol.md")],
        "case6 preamble matched",
    )

    # Case 7 — backtick-wrapped decoy NOT matched.
    check(find_links(["`<!-- CANONICAL: shared/x.md -->` mid-sentence"]) == [],
          "case7 backtick decoy not matched")

    # Case 8 — mid-prose decoy and the four named decoys NOT matched.
    decoys = [
        "> it lives in <!-- CANONICAL: shared/dispatch-convention.md --> and ...",  # harness-adapter.md:13
        "rules live in `shared/` referenced via `<!-- CANONICAL: shared/x.md -->`.",  # CLAUDE.md:32
        "> `<!-- CANONICAL: shared/x.md -->` installed alongside",  # harness-adapter.md:152
        "referenced via `<!-- CANONICAL: ... -->`.",  # harness-adapter.md:273
        "**Consumed via** `<!-- CANONICAL: shared/severity-verdict-contract.md -->` — link",  # severity-verdict-contract.md:9
    ]
    for d in decoys:
        check(find_links([d]) == [], f"case8 decoy not matched: {d!r}")

    # Case 9 — scan-scope exclusion: docs/plans/ and docs/handoffs/ never enter
    # the tracked set even though their lines match the matcher.
    check(find_links(["<!-- CANONICAL: shared/x.md -->"]) == [(1, "shared/x.md")],
          "case9 matcher still matches")
    check(not in_scan_scope("docs/plans/2026-09-10-553-change-sizing-plan.md"),
          "case9 docs/plans excluded")
    check(not in_scan_scope("docs/handoffs/foo.md"), "case9 docs/handoffs excluded")
    check(in_scan_scope("skills/temper/SKILL.md"), "case9 skill file in scope")

    # Case 10 — consumer set-equality.
    three = set(CONSUMERS)
    two = {f for f in CONSUMERS if f != "skills/finish/SKILL.md"}
    four = three | {"skills/other/SKILL.md"}
    check(carrier_pin_violations(two) != [], "case10 missing consumer fails")
    check(carrier_pin_violations(four) != [], "case10 extra consumer fails")
    check(carrier_pin_violations(three) == [], "case10 exact set passes")

    # Case 11 — two-way pin (`**Linked from:**`).
    good = ("> **Linked from:** `skills/temper/SKILL.md`, `skills/delve/SKILL.md`, "
            "`skills/finish/SKILL.md`")
    check(set(linked_from_paths([good])) == three, "case11 good line parsed")
    check(linked_from_violations(set(linked_from_paths([good]))) == [],
          "case11 matching line passes")
    disagree = "> **Linked from:** `skills/temper/SKILL.md`, `skills/delve/SKILL.md`"
    check(linked_from_violations(set(linked_from_paths([disagree]))) != [],
          "case11 disagreement fails")
    malformed = ("> **Linked from:** skills/temper/SKILL.md, skills/delve/SKILL.md, "
                 "skills/finish/SKILL.md")
    check(linked_from_paths([malformed]) == [], "case11 malformed -> empty set")
    check(linked_from_violations(set(linked_from_paths([malformed]))) != [],
          "case11 malformed line fails")

    # Case 12 — I4 / I5 / I9.
    doc_clean = [
        "# Change Sizing",
        "## 8. Comment-prefix vocabulary",
        "| Nit: | trio Minor |",
        "| FYI | no equivalent |",
        "| Optional: / Consider: | trio Suggestion |",
        "## Anti-patterns",
    ]
    check(i4_violations(doc_clean) == [], "case12 i4 clean")
    doc_i4_bad = [
        "# Change Sizing",
        "Nit: a forbidden tier outside §8",
        "## 8. Comment-prefix vocabulary",
        "| Nit: | trio Minor |",
        "## Anti-patterns",
    ]
    check(i4_violations(doc_i4_bad) != [], "case12 i4 token outside §8 fails")
    check(i5_violations(["caps at 5,000 lines because temper's recall degrades"]) == [],
          "case12 i5 with temper passes")
    check(i5_violations(["our own threshold is 5,000 lines"]) != [],
          "case12 i5 without temper/delve fails")
    hook_good = [
        "<!-- CANONICAL: shared/change-sizing.md -->",
        "Sizing thresholds are advisory, never gates on.",
    ]
    hook_bad = [
        "<!-- CANONICAL: shared/change-sizing.md -->",
        "must not proceed if the diff is oversized.",
    ]
    check(i9_hook_violations("skills/finish/SKILL.md", hook_good) == [],
          "case12 i9 hook clean")
    check(i9_hook_violations("skills/finish/SKILL.md", hook_bad) != [],
          "case12 i9 gating token near hook fails")
    sep = ["placeholder"] * 120
    anchor_clean = (["<!-- CANONICAL: shared/change-sizing.md -->"] + sep
                    + ["- **Reviewability note** (fires past ~300 lines) ... <!-- CONTRACT:change-sizing-hook -->"])
    anchor_bad = (["<!-- CANONICAL: shared/change-sizing.md -->"] + sep
                  + ["- **Reviewability note**: must not proceed if oversized. <!-- CONTRACT:change-sizing-hook -->"])
    check(i9_hook_violations("skills/temper/SKILL.md", anchor_clean) == [],
          "case12 i9 anchor (100+ lines from link) clean")
    check(i9_hook_violations("skills/temper/SKILL.md", anchor_bad) != [],
          "case12 i9 gating token near firing-clause anchor fails")
    check(i9_doc_violations(["advisory only, never gates"]) == [], "case12 i9 doc clean")
    check(i9_doc_violations(["hard stop here"]) != [], "case12 i9 doc token fails")

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — all 12 I6 cases behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
```

All four checks plus `selftest()` are now fully specified in-code: the missing `I5_TOKEN`/`I5_REQUIRE` constants; the `**Linked from:**` parse (which reads the list off the `> ` blockquote-prefixed header line after stripping the blockquote marker); and I9's hook-location rule (each consumer's hook is located by BOTH its `MATCH_RE`-matched link line AND its `CONTRACT:change-sizing-hook` firing-clause anchor — the anchor is what reaches temper's/delve's firing clauses ~100 lines below their header link — and each such line's `±I9_WINDOW` neighborhood is grepped for gating tokens). This mirrors the sibling checkers: `main()` aggregates the error list, printing `- <error>` lines and exiting `1` when non-empty.

**Step 4: Run `--selftest`** → Expected: PASS (every I6 case green).

**Step 5: Run `python3 scripts/check_canonical_links.py`** → Expected: exit 1 with the I3 empty-consumer-set error `- consumer set is {} expected {skills/delve/SKILL.md,skills/finish/SKILL.md,skills/temper/SKILL.md}` (no consumer links to `shared/change-sizing.md` yet). No broken-link errors at this stage: the 83 live links all still resolve, and no tracked file links to the not-yet-existing doc. The missing-target broken-link path (a real link to a nonexistent target) is a resolution failure, already pinned by selftest case 2 where it belongs.

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

(Note: the `**Consumed via**` line above is kept safe by its leading `**Consumed via**` prose
prefix, not by the backticks — the prefix means the line does not begin at column 0 with `<!--`,
so `MATCH_RE` does not match it even un-wrapped. The backticks are kept as defense-in-depth; do
not rely on them alone to keep the line off the I3 consumer scan.)

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

**Step 2: Add the sixth classification bullet.** After the `>5,000`-line bullet (`:126`) and its blank slot (`:127`), append one bullet to the `inspect:` list — outside the `>5,000` branch, gated by the shared ~300 firing condition. The bullet carries an inline `CONTRACT:change-sizing-hook` anchor (per `CHECKER_CONVENTIONS.md` §1) so I9's hook-location grep reaches this firing clause, which sits ~110 lines below the header link:

```markdown
- **Reviewability note** (when added+deleted exceeds ~300 lines, per `change-sizing.md`): record the changed-line count as a non-gating round-metadata note and name the applicable splitting strategy. Independent of the `degraded-context` flag in the `>5,000` bullet above — a different axis. <!-- CONTRACT:change-sizing-hook -->
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

**Step 2: Extend the Step 3 run-level line (diff scope).** The hook fires only when the diff's measured changed-line count exceeds the doc's ~300 middle band (per §1) — the shared ~300 firing condition from design §5; below that band it emits nothing. When it fires, append this one clause to the run-level `scope`/`effort` line (`:120`), for **diff** scope only, carrying an inline `CONTRACT:change-sizing-hook` anchor (per `CHECKER_CONVENTIONS.md` §1) so I9's hook-location grep reaches this firing clause, which sits ~100 lines below the header link:

```markdown
scope/effort — sizing: ~<count> changed lines (past the ~300 reviewability band, per `change-sizing.md`); split via <named strategy>. <!-- CONTRACT:change-sizing-hook -->
```

(with `<count>` the numstat added+deleted total recorded at the resolve step, and `<named strategy>` one of the four from `change-sizing.md` §4 — Stack / By file group / Horizontal / Vertical.) The clause is never an eight-field record (no single reproduction ⇒ fails `delve-engine`'s cutting rule) and never in the ledger row. For **path** scope, no diff exists, so no sizing observation is printed — a specified outcome, not an omission.

**Step 3: Run `python3 scripts/check_canonical_links.py`** → Expected: I3 RED `{temper, delve}` (2 of 3).

**Step 4: Commit** `git add skills/delve/SKILL.md && git commit -m "feat(delve): #553 link change-sizing + scope-level sizing report"`

---

### Task 5: Link + hook in `finish` (point-of-use)

**Files:**
- Modify: `skills/finish/SKILL.md:101` (between `:100` "Do not silently pick the first match." and `:102` `### Step 5`)

**Step 1: Add link + hook together at the point of use** (finish consults sizing once, at Step 4/5 where the base ref exists — so the link lives here, not in the header which carries only `dispatch-convention`):

```markdown
<!-- CANONICAL: shared/change-sizing.md -->
Measure `git diff --numstat <base>..HEAD` (two-dot, matching temper's two-dot range — both diff the base ref's tip against HEAD, never the merge base). If past the ~300 reviewability band (per `change-sizing.md` §1), say so and name the applicable strategy. Advisory input to the merge-vs-PR-vs-stack choice, not a gate.
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