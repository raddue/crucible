#!/usr/bin/env python3
"""Structural check for the graphify-consult dispatch convention (ai-rack#93).

Invocation (from repo root):
    python3 scripts/check_dispatch_graphify_consult.py            # gate the real files
    python3 scripts/check_dispatch_graphify_consult.py --selftest # in-memory logic test

Asserts, over two path-pinned files (no directory tree-walk, so the checker can
never self-match its own literal pin strings — see
`scripts/CHECKER_CONVENTIONS.md`):

  skills/shared/dispatch-convention.md — the canonical shared reference every
      orchestrator links via `<!-- CANONICAL: shared/dispatch-convention.md -->`.
      The convention must now carry a "Graphify Consult" section that names the
      staleness contract (`check-graph-staleness.sh`, the stable
      `graphify-staleness:` prefix, and the deliberately-distinct `no-graph` vs
      `stale:N` vs `fresh` states), instructs a graphify-query-first workflow
      (`graphify explain` / `graphify affected` / `graphify query`), and states
      the enforced-vs-recommended decision (`recommended, not enforced`).

  skills/cartographer-skill/SKILL.md — a "With Graphify" integration note that
      pins the division of labor (graphify = derived call graph; cartographer =
      curated prose), so a future reader sees the two as complementary rather than
      reading graphify as a third parallel structural-knowledge store.

Stdlib only (`pathlib`, `sys`). Exits 0 when every clause is present, 1 with a
`- <error>` list otherwise. Style mirrors `scripts/check_rt_receipt_contract.py`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DISPATCH_CONVENTION = ROOT / "skills/shared/dispatch-convention.md"
CARTOGRAPHER = ROOT / "skills/cartographer-skill/SKILL.md"

# label -> literal substring that MUST appear in dispatch-convention.md.
DISPATCH_REQUIRED: dict[str, str] = {
    "Graphify Consult section": "## Graphify Consult",
    "staleness script citation": "check-graph-staleness.sh",
    "stable staleness prefix": "graphify-staleness:",
    "no-graph state token": "no-graph",
    "stale:N state token": "stale:N",
    "fresh state token": "`fresh`",
    "query-first workflow: explain": "graphify explain",
    "query-first workflow: affected": "graphify affected",
    "query-first workflow: query": "graphify query",
    "enforced-vs-recommended decision": "recommended, not enforced",
    "script-absent handling": "not present in the target repo",
}

# label -> literal substring that MUST appear in cartographer-skill/SKILL.md.
CARTOGRAPHER_REQUIRED: dict[str, str] = {
    "With Graphify note": "### With Graphify",
    "complement (not redundant) decision": "complementary, not redundant",
    "call-graph framing": "call graph",
}


def check_required(text: str, required: dict[str, str]) -> list[str]:
    return [f"missing {label}: `{sub}`" for label, sub in required.items()
            if sub not in text]


def check_dispatch(text: str) -> list[str]:
    return check_required(text, DISPATCH_REQUIRED)


def check_cartographer(text: str) -> list[str]:
    return check_required(text, CARTOGRAPHER_REQUIRED)


def selftest() -> int:
    def good(required: dict[str, str]) -> str:
        return " ".join(required.values())

    for required in (DISPATCH_REQUIRED, CARTOGRAPHER_REQUIRED):
        assert check_required(good(required), required) == [], (
            f"GOOD sample (join of all required substrings) should pass, "
            f"got: {check_required(good(required), required)}")
        for label, sub in required.items():
            bad = good(required).replace(sub, "", 1)
            errs = check_required(bad, required)
            assert any(e == f"missing {label}: `{sub}`" for e in errs), (
                f"removing {label!r} should flag it, got: {errs}")

    print("selftest OK — GOOD passes; removing any single required clause flags "
          "exactly that clause.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    errs: list[str] = []
    if not DISPATCH_CONVENTION.is_file():
        errs.append(f"missing file: {DISPATCH_CONVENTION.relative_to(ROOT)}")
    else:
        errs += check_dispatch(DISPATCH_CONVENTION.read_text(encoding="utf-8"))
    if not CARTOGRAPHER.is_file():
        errs.append(f"missing file: {CARTOGRAPHER.relative_to(ROOT)}")
    else:
        errs += check_cartographer(CARTOGRAPHER.read_text(encoding="utf-8"))

    if errs:
        print("GRAPHIFY-CONSULT CONVENTION CHECK FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — dispatch-convention.md carries the Graphify Consult section and "
          "cartographer-skill documents the graphify division of labor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())