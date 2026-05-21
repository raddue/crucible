#!/usr/bin/env python3
"""Drift check: canonical Targeted Lenses vs build-reviewer paraphrase.

Invocation (from repo root):
    python3 scripts/check_canonical_drift.py

Compares the `### Targeted Lenses` block in `skills/shared/reviewer-common.md`
(canonical) against the paraphrased lens block in
`skills/build/build-reviewer-prompt.md` (between the
`<!-- CANONICAL: shared/reviewer-common.md — Targeted Lenses (Pass 1 — paraphrased) -->`
marker and the next `**Wiring:**` line).

Asserts both blocks contain: the 4 lens subsection headings, the 6 co-fire
data-row conditions, and the 4 pinned severity-ceiling sentences (with the
OCP-form ceiling appearing >=3x across DRY/SRP/OCP). Exits 0 if aligned,
1 with a diff summary otherwise. Stdlib only.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON = ROOT / "skills/shared/reviewer-common.md"
BUILD = ROOT / "skills/build/build-reviewer-prompt.md"

LENS_HEADINGS = ["#### Surgical Changes", "#### DRY", "#### SRP", "#### OCP"]
COFIRE_ROWS = [
    "Surgical Changes triggers", "Function-SRP fully contains",
    "Class-SRP fully contains", "Module-SRP overlaps DRY",
    "SRP and DRY apply, SRP unit does NOT contain", "OCP and any other lens",
]
PINNED_SENTENCES = [
    "Critical/Important when scope-bleed materially obscures",
    "DRY findings from this lens MUST NOT exceed Minor",
    "Function- and class-level SRP findings are primary",
]
CEILING_PHRASE = "Severity ceiling:** Minor (or Suggestion)."

def extract_canon(text: str) -> str:
    # Include Targeted Lenses + the sibling ### Lens precedence... section
    # (where the co-fire table lives), stopping at the next non-precedence ###.
    m = re.search(
        r"### Targeted Lenses\n(.*?)(?=\n### (?!Lens precedence))",
        text, re.DOTALL)
    return m.group(1) if m else ""

def extract_build(text: str) -> str:
    m = re.search(
        r"<!-- CANONICAL: shared/reviewer-common\.md — Targeted Lenses \(Pass 1 — paraphrased\) -->\n(.*?)\*\*Wiring:\*\*",
        text, re.DOTALL)
    return m.group(1) if m else ""

def check(name: str, block: str) -> list[str]:
    if not block:
        return [f"{name}: block not found / empty"]
    errs = [f"{name}: missing lens heading '{h}'" for h in LENS_HEADINGS if h not in block]
    rows = "\n".join(ln for ln in block.splitlines()
                     if ln.lstrip().lstrip(">").lstrip().startswith("|")
                     and "---" not in ln and "Co-fire condition" not in ln)
    errs += [f"{name}: missing co-fire row '{c}'" for c in COFIRE_ROWS if c not in rows]
    errs += [f"{name}: missing pinned sentence '{s}'" for s in PINNED_SENTENCES if s not in block]
    n = block.count(CEILING_PHRASE)
    if n < 3:
        errs.append(f"{name}: '{CEILING_PHRASE}' appears <3x (got {n})")
    return errs

def main() -> int:
    canon_block = extract_canon(CANON.read_text(encoding="utf-8"))
    build_block = extract_build(BUILD.read_text(encoding="utf-8"))
    errs = check("canonical", canon_block) + check("build-paraphrase", build_block)
    if errs:
        print("DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — canonical and build paraphrase are aligned.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
