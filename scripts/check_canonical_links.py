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
I4_MATCHERS = [
    (t, re.compile(r"\b" + re.escape(t) + (r"\b" if t[-1].isalnum() else ""), re.ASCII))
    for t in I4_TOKENS
]
I5_TOKEN = "5,000"
I5_RE = re.compile(r"(?<![0-9,])5,000(?![0-9,])")
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
    """Return (1-based line_no, target) for every line matching MATCH_RE.

    Match rule is deliberately column-0-anchored with no fence state — the same
    discipline as check_i2_marker.py. In-fence CANONICAL lines in dispatch
    templates render inside a ``` block but ARE live links, not examples."""
    return [(i, m.group(1)) for i, line in enumerate(lines, 1)
            for m in [MATCH_RE.match(line)] if m]


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
            return [p.strip() for p in re.findall(r"`([^`]+)`", stripped)]
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
        for tok, pat in I4_MATCHERS:
            if pat.search(line) and (bounds is None or not (bounds[0] <= i < bounds[1])):
                errs.append(f"- I4 token {tok!r} appears outside §8 (line {i + 1})")
    return errs


def i5_violations(lines: list[str]) -> list[str]:
    """I5: the `5,000` token must sit on a line that also carries `temper` or
    `delve` — it names their context cap, never change-sizing's own threshold."""
    errs = []
    for i, line in enumerate(lines):
        if I5_RE.search(line) and not any(r in line for r in I5_REQUIRE):
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

    # Case 14 — F2: word/symbol boundaries. `Nit` inside `Nitpick`, `5,000`
    # inside `15,000`/`25,000` do NOT trip I4/I5; bare tokens still do.
    check(i4_violations(["Nitpick review note"]) == [], "case14 Nitpick not I4")
    check(i4_violations(["FYI: fine"]) != [], "case14 FYI still I4 without §8")
    check(i4_violations(["note about Optional: in prose", "## 8.", "ok"]) != [],
          "case14 Optional: outside §8 still I4")
    check(i5_violations(["15,000 and 25,000 are caps"]) == [], "case14 15k/25k not I5")
    check(i5_violations(["5,000 is our threshold"]) != [], "case14 bare 5,000 still I5")

    # Case 15 — F3: whitespace inside `**Linked from:**` backticks stripped.
    padded = ("> **Linked from:** `skills/temper/SKILL.md `, ` skills/delve/SKILL.md`, "
              "`skills/finish/SKILL.md `")
    check(set(linked_from_paths([padded])) == three, "case15 padded backticks parsed")
    check(linked_from_violations(set(linked_from_paths([padded]))) == [],
          "case15 padded two-way pin passes")

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — all I6 + F2/F3 hardening cases behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())