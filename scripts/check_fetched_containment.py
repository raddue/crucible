#!/usr/bin/env python3
"""Fetched-content containment contract checker (#641 SDD scope-smuggling follow-up).

Path-pinned structural gate over the two shared rules the PR #638 merged diff
introduced and their two main consumers. Pins the *contract tokens* that drifted
in that merge (per scripts/CHECKER_CONVENTIONS.md — enum values, schema tokens,
and grep forms are contract; surrounding prose is free to re-word).

Invocation (from repo root):
    python3 scripts/check_fetched_containment.py            # check the tracked tree
    python3 scripts/check_fetched_containment.py --selftest # built-in logic tests

Covers the #641 code-review findings that were triaged mechanical:
  - F1  category-8 single-match rule propagated to action table + contract enum +
       siege activation heuristic (was dead on every consumer path);
  - F2  ledger-monotonicity guard present on siege's own self-commit write path
       (guard previously sat only on warden's commit path);
  - F3  "currently open" ledger grep is not fail-open (APPROVED no longer matches
       UNAPPROVED as a substring);
  - F4  host-token format admits dotted real hostnames (api.sentry.io);
  - F6  fetched-content-containment dependency declared as a column-0 CANONICAL
       link in both consumers, so check_canonical_links.py resolves it.
Stdlib only. Exit 0 clean / 1 with a `- <error>` list.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

FILES = {
    "fetched": "skills/shared/fetched-content-containment.md",
    "signals": "skills/shared/security-signals.md",
    "siege": "skills/siege/SKILL.md",
    "sdd": "skills/source-driven-development/SKILL.md",
}

CANONICAL_LINK = "<!-- CANONICAL: shared/fetched-content-containment.md -->"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def has_column0_link(text: str) -> bool:
    """The dependency is declared as a standalone column-0 CANONICAL line, the
    only form check_canonical_links.py's MATCH_RE resolves (mid-sentence /
    backtick placements are deliberate decoys)."""
    return any(line.strip() == CANONICAL_LINK for line in text.splitlines())


def check(texts: dict[str, str]) -> list[str]:
    errs: list[str] = []

    f = texts["fetched"]
    # F3 — corrected "currently open" grep (APPROVED- / REJECTED- carry the
    # mandatory trailing dash + initials, so UNAPPROVED is no longer a substring
    # match of the closed set).
    if "FE-<n>.*(APPROVED-|REJECTED-)" not in f:
        errs.append("- fetched: corrected open-set grep 'FE-<n>.*(APPROVED-|REJECTED-)' missing")
    # F4 — host token admits dotted real hostnames.
    if "[A-Za-z0-9.-]+" not in f:
        errs.append("- fetched: ERE host token lacks the dot ('[A-Za-z0-9.-]+')")

    s = texts["signals"]
    # F1 — eight categories (not the stale seven), with destination in the enum.
    if "Eight categories" not in s:
        errs.append("- signals: intro still says 'Seven categories'")
    if "`dependencies`, `destination`" not in s:
        errs.append("- signals: contract enum missing the 'destination' category-8 value")

    g = texts["siege"]
    # F1 — siege activation heuristic carries the category-8 single-match exception.
    if "CONTRACT:siege-activation-cat8-exception" not in g:
        errs.append("- siege: activation heuristic missing category-8 single-match exception")
    # F2 — siege self-commits; its own write path needs the monotonicity guard.
    if "CONTRACT:siege-ledger-monotonicity" not in g:
        errs.append("- siege: Phase 4 self-commit path missing ledger-monotonicity guard")
    # F6 — column-0 dependency link so the canonical-link checker resolves it.
    if not has_column0_link(g):
        errs.append("- siege: missing column-0 CANONICAL fetched-content-containment link")

    d = texts["sdd"]
    if not has_column0_link(d):
        errs.append("- sdd: missing column-0 CANONICAL fetched-content-containment link")

    return errs


def main() -> int:
    texts = {k: read(v) for k, v in FILES.items()}
    errs = check(texts)
    if errs:
        print("\n".join(errs))
        return 1
    print("OK — fetched-content containment contract holds.")
    return 0


def selftest() -> int:
    failures: list[str] = []

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    good = {
        "fetched": (
            "a grep for `FE-<n>.*UNAPPROVED` with no later "
            "`FE-<n>.*(APPROVED-|REJECTED-)` line\n"
            "[A-Za-z0-9.-]+\n"
        ),
        "signals": "Eight categories\n`dependencies`, `destination`\n",
        "siege": (
            CANONICAL_LINK + "\n"
            "CONTRACT:siege-activation-cat8-exception\n"
            "CONTRACT:siege-ledger-monotonicity\n"
        ),
        "sdd": CANONICAL_LINK + "\n",
    }
    expect(check(good) == [], "good text passes")

    for missing_key, err_frag in [
        ("fetched", "open-set grep"),
        ("fetched", "host token lacks the dot"),
        ("signals", "still says 'Seven categories'"),
        ("signals", "enum missing the 'destination'"),
        ("siege", "activation heuristic"),
        ("siege", "ledger-monotonicity"),
        ("siege", "column-0 CANONICAL"),
        ("sdd", "column-0 CANONICAL"),
    ]:
        bad = {k: v for k, v in good.items()}
        if missing_key == "fetched" and "grep" in err_frag:
            bad["fetched"] = good["fetched"].replace("(APPROVED-|REJECTED-)", "APPROVED|REJECTED")
        elif missing_key == "fetched" and err_frag == "host token lacks the dot":
            bad["fetched"] = "FE-<n>.*(APPROVED-|REJECTED-)\n[A-Za-z0-9-]+\n"
        elif missing_key == "signals":
            bad["signals"] = "Seven categories\n`dependencies`\n"
        elif missing_key == "siege" and err_frag == "activation heuristic":
            bad["siege"] = CANONICAL_LINK + "\nCONTRACT:siege-ledger-monotonicity\n"
        elif missing_key == "siege" and err_frag == "ledger-monotonicity":
            bad["siege"] = CANONICAL_LINK + "\nCONTRACT:siege-activation-cat8-exception\n"
        elif missing_key == "siege":
            bad["siege"] = "CONTRACT:siege-activation-cat8-exception\nCONTRACT:siege-ledger-monotonicity\n"
        else:  # sdd
            bad["sdd"] = "no link here\n"
        expect(any(err_frag in e for e in check(bad)), f"{err_frag!r} detected when absent")

    # F3 fail-open form is specifically rejected: the bare `APPROVED|REJECTED`
    # alternation (no mandatory dash) must not be the doc's open-set grep.
    failopen = dict(good)
    failopen["fetched"] = "FE-<n>.*UNAPPROVED with FE-<n>.*APPROVED|REJECTED\n[A-Za-z0-9.-]+\n"
    expect(any("open-set grep" in e for e in check(failopen)), "fail-open grep rejected")

    # Column-0 detection: a backtick-wrapped / mid-sentence placement must NOT
    # count as the dependency declaration.
    inline = dict(good)
    inline["sdd"] = "governed by `" + CANONICAL_LINK + "` — see note.\n"
    expect(any("column-0" in e for e in check(inline)), "inline link not a column-0 declaration")

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())