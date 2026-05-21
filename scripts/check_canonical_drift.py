#!/usr/bin/env python3
"""Drift check: canonical Targeted Lenses + Tenancy/Rollback disciplines
vs build-reviewer paraphrase.

Invocation (from repo root):
    python3 scripts/check_canonical_drift.py

Compares the `### Targeted Lenses` block AND the new Tenancy/Rollback
discipline sections + AI-Slop counter-rule in `skills/shared/reviewer-common.md`
(canonical) against their paraphrased counterparts in
`skills/build/build-reviewer-prompt.md`.

Asserts both files contain: the 4 lens subsection headings, the 6 co-fire
data-row conditions, the 4 pinned severity-ceiling sentences, the Tenancy
and Rollback discipline headings + Category values, and the AI-Slop
counter-rule paraphrase-resistant pins. Exits 0 if aligned, 1 with a
diff summary otherwise. Stdlib only.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON = ROOT / "skills/shared/reviewer-common.md"
BUILD = ROOT / "skills/build/build-reviewer-prompt.md"
TEMPER = ROOT / "skills/temper/temper-reviewer.md"

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

# Tenancy/Rollback discipline pinned phrases — must appear in BOTH canonical
# and build-paraphrase (file-level grep, not lens-block scoped).
DISCIPLINE_PINS = [
    "Category: Tenancy",
    "Category: Rollback",
    "defense-in-depth, not single-layer trust",
    "tenancy/auth",
    "intentional defense-in-depth",
    "RLS",
    "callback",
]

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

def check_disciplines(name: str, text: str) -> list[str]:
    """File-level pin check for Tenancy/Rollback disciplines + counter-rule."""
    errs = []
    # Subsection headings (canonical uses ### exactly; build-paraphrase
    # uses **bold** style — accept either form by checking the title text).
    for title in ("Tenancy & Isolation", "Production Readiness (Rollback Walk)"):
        if title not in text:
            errs.append(f"{name}: missing discipline title '{title}'")
    for pin in DISCIPLINE_PINS:
        if pin not in text:
            errs.append(f"{name}: missing pin '{pin}'")
    return errs

def main() -> int:
    canon_text = CANON.read_text(encoding="utf-8")
    build_text = BUILD.read_text(encoding="utf-8")
    temper_text = TEMPER.read_text(encoding="utf-8")
    canon_block = extract_canon(canon_text)
    build_block = extract_build(build_text)
    errs = (
        check("canonical", canon_block)
        + check("build-paraphrase", build_block)
        + check_disciplines("canonical", canon_text)
        + check_disciplines("build-paraphrase", build_text)
        + check_disciplines("temper-reviewer", temper_text)
    )
    if errs:
        print("DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — canonical, build paraphrase, and temper reviewer are aligned (lenses + disciplines).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
