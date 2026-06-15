#!/usr/bin/env python3
"""Blind-boundary provenance check for the inquisitor ground-truth list (#424, S4).

Invocation (from repo root):
    python3 scripts/check_ground_truth_provenance.py            # check the tree
    python3 scripts/check_ground_truth_provenance.py --selftest # built-in logic tests

The PRIMARY recorded delta (acceptance #3) is graded against `ground-truth-bugs.json`,
which design T1 requires be authored BLIND to evals.json's dimension-bucketed
`expected_output` / `expectations` prose (authoring from that prose would re-import
the dimension-aligned content selection and bias the lensed arms). "Trust the
process" is what this repo's calibration ethos rejects, so the blind input is
committed as `ground-truth-bugs.provenance.md` and this check makes the de-biasing
machine-verifiable: it asserts the provenance artifact contains NONE of the
`expected_output` / `expectations` strings. If any appears, the blind boundary leaked
and the check fails.

Stdlib only. Exit 0 clean / 1 on a detected leak.
"""
from __future__ import annotations
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVALS_JSON = ROOT / "skills/inquisitor/evals/evals.json"
PROVENANCE = ROOT / "skills/inquisitor/evals/ground-truth-bugs.provenance.md"


def expectation_strings(evals: dict) -> list:
    """Every expectation/expected_output string the provenance must NOT contain."""
    out = []
    for e in evals["evals"]:
        if e.get("expected_output"):
            out.append(e["expected_output"])
        for s in e.get("expectations", []):
            if s:
                out.append(s)
    return out


def leaks(provenance_text: str, strings) -> list:
    """Return (string) entries that leaked into the provenance text."""
    return [s for s in strings if s in provenance_text]


def main() -> int:
    evals = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
    strings = expectation_strings(evals)
    text = PROVENANCE.read_text(encoding="utf-8")
    found = leaks(text, strings)
    if found:
        print(f"GROUND-TRUTH BLIND BOUNDARY LEAKED in "
              f"{PROVENANCE.relative_to(ROOT)}:")
        for s in found:
            print(f"  expectation string present: {s[:80]!r}...")
        print("\nThe provenance artifact must contain only the diffs + factual "
              "codebase context fed to the blind author — none of evals.json's "
              "expectation prose. A leak means the ground-truth list may be "
              "dimension-biased (design T1).")
        return 1
    print(f"OK — provenance contains none of the {len(strings)} evals.json "
          "expectation strings; the blind boundary held.")
    return 0


def selftest() -> int:
    """Built-in logic tests (in-memory) for the substring leak scan."""
    strings = ["Identifies the in-memory scheduler problem",
               "sent_at type mismatch"]
    clean = "## Fixture 1\n```diff\n+const x = 1;\n```\nExisting codebase facts.\n"
    leaky = clean + "Identifies the in-memory scheduler problem when restarted.\n"
    cases = [
        (clean, False, "diffs + context only → no leak"),
        (leaky, True, "an expectation string in the provenance is caught"),
    ]
    failures = []
    for text, expect_fail, reason in cases:
        got = bool(leaks(text, strings))
        if got != expect_fail:
            failures.append(f"  expected leak={expect_fail} ({reason}), got={got}")
    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — the substring leak scan fires on a seeded expectation "
          "string and passes a diffs-plus-context-only provenance.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
