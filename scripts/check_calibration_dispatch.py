#!/usr/bin/env python3
"""Calibration-weighted-dispatch wiring invariant (#372).

Invocation (from repo root):
    python3 scripts/check_calibration_dispatch.py            # check the tree
    python3 scripts/check_calibration_dispatch.py --selftest # built-in logic tests

For each of the five consumer skills (siege, quality-gate, inquisitor, delve,
audit), asserts THREE things:
  1. the `<!-- CANONICAL: shared/calibration-weighted-dispatch.md -->` marker is
     present;
  2. the short invocation `advise <this-skill>` (the per-skill `brier_advisory.py
     advise <key>` call) is present;
  3. NONE of the convention's prose-body anchor lines are inlined — the net-new
     no-copy assertion (CLAUDE.md "link, never copy").

Why this is net-new and not free reuse: `check_canonical_drift.py` is a
hand-written 2-file block comparator (reviewer-common ↔ build-reviewer-prompt)
that does not iterate these five consumers, and `check_crossref.py` *explicitly
excludes* `<!-- CANONICAL: … -->` markers. Neither covers this invariant.

Exits 0 if all five wire correctly with no copied prose, 1 with a per-failure
list otherwise. Stdlib only.
"""
from __future__ import annotations
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
CONVENTION_REL = "shared/calibration-weighted-dispatch.md"
CONVENTION = SKILLS / "shared" / "calibration-weighted-dispatch.md"
MARKER = f"<!-- CANONICAL: {CONVENTION_REL} -->"

# skill-dir -> its calibration key (== the `advise <key>` argument it must carry)
CONSUMERS = {
    "siege": "siege",
    "quality-gate": "quality-gate",
    "inquisitor": "inquisitor",
    "delve": "delve",
    "audit": "audit",
}

# Prose-body anchor lines that live ONLY in the convention doc — never in the
# short consumer invocation. If any appears in a consumer SKILL.md, the prose
# was copied (a "link, never copy" violation). These are deliberately NOT the
# shared phrases ("Calibration-weighted dispatch (advisory)", "scrutiny hints
# (NOT as findings, NOT scored)") that legitimately appear in both the doc's
# consumer-obligation snippet and the consumers.
NO_COPY_ANCHORS = [
    "## 1. What it is",
    "## 2. The `advise` contract",
    "ADVICE_FILE_TOPK = 5",
    "the Book of Grudges (`#271`)",
    "Known v1 limitation",
]


def invocation_token(key: str) -> str:
    return f"advise {key}"


def check_consumer(name: str, key: str, text: str) -> list[str]:
    """Return a list of failure strings for one consumer (empty == OK)."""
    fails = []
    if MARKER not in text:
        fails.append(f"{name}: missing CANONICAL marker `{MARKER}`")
    if invocation_token(key) not in text:
        fails.append(
            f"{name}: missing invocation `{invocation_token(key)}` "
            f"(brier_advisory.py advise call)")
    copied = [a for a in NO_COPY_ANCHORS if a in text]
    if copied:
        fails.append(
            f"{name}: convention prose appears inlined (copy the LINK, not the "
            f"prose) — found anchor(s): {copied}")
    return fails


def main() -> int:
    errs: list[str] = []
    if not CONVENTION.is_file():
        print(f"MISSING CONVENTION DOC: {CONVENTION.relative_to(ROOT)}")
        return 1
    for name, key in CONSUMERS.items():
        path = SKILLS / name / "SKILL.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            errs.append(f"{name}: cannot read {path.relative_to(ROOT)}")
            continue
        errs.extend(check_consumer(name, key, text))
    if errs:
        print("CALIBRATION-DISPATCH WIRING BROKEN:")
        for e in errs:
            print(f"  {e}")
        return 1
    print("OK — all 5 consumers carry the marker + invocation, no copied prose.")
    return 0


def selftest() -> int:
    failures = []
    good = (
        f"{MARKER}\n"
        "**Calibration-weighted dispatch (advisory).** ... run "
        "`python3 <script> advise siege <files>` ... scrutiny hints.\n")
    if check_consumer("siege", "siege", good):
        failures.append("clean consumer should pass but did not")
    # missing marker
    if not check_consumer("siege", "siege", "advise siege only, no marker"):
        failures.append("missing-marker should fail but passed")
    # missing invocation
    if not check_consumer("siege", "siege", MARKER + "\nno call here"):
        failures.append("missing-invocation should fail but passed")
    # copied prose
    copied = f"{MARKER}\nadvise siege\n## 1. What it is\n"
    if not check_consumer("siege", "siege", copied):
        failures.append("copied-prose should fail but passed")
    # wrong key (audit invocation in siege file) must miss `advise siege`
    if not check_consumer("siege", "siege", MARKER + "\nadvise audit\n"):
        failures.append("wrong-key invocation should fail but passed")
    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("SELFTEST OK — marker / invocation / no-copy checks behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
