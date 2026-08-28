#!/usr/bin/env python3
"""Structural check: handoff must instruct a hard stop after writing (#556).

Invocation (from repo root):
    python3 scripts/check_handoff_stop_contract.py            # gate the real file
    python3 scripts/check_handoff_stop_contract.py --selftest # in-memory logic test

Sessions were observed writing the handoff doc and then continuing to work the
arc instead of ending the turn — defeating the point of `/handoff` (stopping now
to save tokens/context). This asserts `skills/handoff/SKILL.md`'s Output Contract
section carries an explicit, unambiguous stop directive strong enough to override
auto-mode's "bias toward continuing" — not an implicit or suggestion-shaped one.

CLAUSE-PRESENCE, NOT POSITIONAL: the three required clauses are asserted as
present anywhere within the `## Output Contract` section body; ordering among
them is not asserted.

Style mirrors `scripts/check_build_clean_tree_contract.py`: ROOT-from-`__file__`,
error accumulation, `sys.exit(main())`, stdlib only, no argparse. The three pins
are mutually disjoint (none a substring of another), so `--selftest` auto-generates
a per-clause RED case for free.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDOFF = ROOT / "skills/handoff/SKILL.md"

# label -> literal substring that MUST appear within the Output Contract section.
REQUIRED_SUBSTRINGS: dict[str, str] = {
    # 1. the hard-stop directive itself — end the turn, don't just fall silent.
    "end-the-turn directive": "END THE TURN",
    # 2. explicit anti-continuation clause — don't keep working the arc.
    "do-not-continue clause": "Do not continue",
    # 3. names the specific rationalization it must override (auto-mode's
    #    default bias), so the instruction reads as an override, not a nicety.
    "auto-mode override clause": "bias toward continuing",
}

# Extract the `## Output Contract` section body: everything from that heading up
# to the next `## ` heading (or EOF). Takes the LAST match in case of an earlier
# shadowing block (mirrors check_build_clean_tree_contract.py's defensive choice).
_OUTPUT_CONTRACT_RE = re.compile(
    r"^## Output Contract\b.*?(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)


def extract_output_contract(text: str) -> str:
    """Return the `## Output Contract` section body, or '' if absent."""
    matches = _OUTPUT_CONTRACT_RE.findall(text)
    return matches[-1] if matches else ""


def check_section(section: str) -> list[str]:
    """Assert every required clause is present in the Output Contract section.
    Pure (takes the slice) so `--selftest` can exercise it on in-memory samples."""
    if not section:
        return ["Output Contract section not found (no `## Output Contract` heading)"]
    return [
        f"missing {label} within Output Contract: `{sub}`"
        for label, sub in REQUIRED_SUBSTRINGS.items()
        if sub not in section
    ]


# --------------------------------------------------------------------------
# selftest — self-contained GOOD/BAD samples (do NOT read the real file)
# --------------------------------------------------------------------------
_GOOD_SAMPLE = """\
## Output Contract

The user explicitly asked for the file location in the response.

- Print a brief summary of what's in the file.
- End with `Read this doc and continue: <absolute path>`.
- **Stop after emitting that line. END THE TURN.** Do not continue executing the
  arc described in the handoff — auto-mode's default bias toward continuing does
  not apply here; writing the handoff IS the stopping point.

## Quality bar
"""

# A section missing exactly one clause (the auto-mode override clause) must FAIL.
_BAD_SAMPLE = _GOOD_SAMPLE.replace(
    "bias toward continuing", "the usual default")


def selftest() -> int:
    # 1. GOOD sample (an Output-Contract-shaped slice with all three clauses) passes.
    section = extract_output_contract(_GOOD_SAMPLE)
    assert section, "GOOD sample should yield an Output Contract section"
    good_errs = check_section(section)
    assert good_errs == [], f"GOOD sample should pass, got: {good_errs}"

    # 2. Per-clause RED: removing any single required substring flags exactly that
    #    clause. Auto-generated so every entry gets its own RED case; the three
    #    pins are mutually disjoint, so a single replace never collaterally hides
    #    another.
    for label, sub in REQUIRED_SUBSTRINGS.items():
        bad = extract_output_contract(_GOOD_SAMPLE.replace(sub, "‹removed›"))
        errs = check_section(bad)
        assert any(label in e for e in errs), (
            f"removing {label!r} (`{sub}`) should flag it, got: {errs}")

    # 3. The concrete BAD sample (one clause dropped) FAILS on that clause.
    bad_errs = check_section(extract_output_contract(_BAD_SAMPLE))
    assert any("auto-mode override" in e for e in bad_errs), (
        f"BAD sample (dropped auto-mode override clause) should flag it, got: {bad_errs}")

    # 4. A text with NO Output Contract heading yields the distinct 'not found'.
    nf_errs = check_section(extract_output_contract("## Process\n\nno output contract here\n"))
    assert any("section not found" in e for e in nf_errs), (
        f"missing Output Contract heading should give 'section not found', got: {nf_errs}")

    print("selftest OK — GOOD passes; each of the three clauses has an "
          "auto-generated per-clause RED case; the BAD sample (dropped auto-mode "
          "override clause) FAILS; and a text with no `## Output Contract` heading "
          "yields the distinct 'section not found' error.")
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    if not HANDOFF.is_file():
        print("HANDOFF STOP CONTRACT CHECK FAILED:")
        print(f"  - {HANDOFF.relative_to(ROOT)} does not exist")
        return 1

    section = extract_output_contract(HANDOFF.read_text(encoding="utf-8"))
    errs = check_section(section)
    if errs:
        print("HANDOFF STOP CONTRACT CHECK FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — handoff's Output Contract carries an explicit hard-stop directive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
