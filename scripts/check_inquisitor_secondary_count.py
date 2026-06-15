#!/usr/bin/env python3
"""Static guard for the inquisitor secondary-pool arithmetic (#424, S2).

Invocation (from repo root):
    python3 scripts/check_inquisitor_secondary_count.py            # check the tree
    python3 scripts/check_inquisitor_secondary_count.py --selftest # built-in logic tests

`score` derives `graded_expectations` from the observed judge records at runtime
(correct — it cannot know the canonical pool without coupling to evals.json). But
the README, a unit test, and `_render_results`'s label all assert the documented
value **26 = total evals.json expectations (27) minus the single fixture-1 #8
exclusion**. NOTHING in code/CI guards that this documented 26 stays consistent
with evals.json: if someone adds/removes an expectation, the "26" silently goes
stale. This static check makes the arithmetic machine-verifiable at the check_*.py
layer (NOT inside `score`'s runtime, which would ripple through every score test).

It asserts:
  - evals.json's total expectation count across all fixtures == 27 (10+9+8), and
    fixture id 1 carries 10 expectations (so the single #8 exclusion is well-defined);
  - the README's secondary-pool description ties `graded_expectations` to 26; and
  - 26 == total − 1 (the single fixture-1 #8 exclusion).

If evals.json expectation counts change, this FAILS — forcing README / the
documented exclusion count to be updated. Stdlib only. Exit 0 clean / 1 on drift.
"""
from __future__ import annotations
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVALS_JSON = ROOT / "skills/inquisitor/evals/evals.json"
README = ROOT / "skills/inquisitor/evals/README.md"
RUN_EVALS = ROOT / "skills/inquisitor/evals/run_evals.py"

EXPECTED_TOTAL = 27          # 10 + 9 + 8 across the three fixtures
EXPECTED_FIXTURE1 = 10       # fixture id 1's expectation count (the #8 lives here)
DOCUMENTED_SECONDARY = 26    # total − 1 (the single fixture-1 #8 exclusion)


def expectation_counts(evals: dict) -> dict:
    """Map fixture id -> number of expectations for that fixture."""
    return {e["id"]: len(e.get("expectations", [])) for e in evals["evals"]}


def run_evals_pins_contracted_pool(run_evals_text: str) -> bool:
    """Anchor: run_evals.py's score reconciles against the same documented pool via
    a module-level `_CONTRACTED_SECONDARY_POOL = 26`. S-1 single-sources the two 26s
    (this guard's DOCUMENTED_SECONDARY and score's reconciliation anchor) so they
    cannot drift silently. Static source match — no runtime import of score."""
    return bool(re.search(
        r"_CONTRACTED_SECONDARY_POOL\s*=\s*%d\b" % DOCUMENTED_SECONDARY,
        run_evals_text))


def readme_ties_secondary_to_26(readme_text: str) -> bool:
    """Anchor: a README line tying the graded secondary expectations to 26 (the
    secondary-pool description), NOT any incidental '26' elsewhere. The committed
    wording is 'the judge grades **26** secondary expectations (10−1 + 9 + 8)'."""
    return bool(re.search(
        r"grades\s+\*{0,2}26\*{0,2}\s+secondary expectations", readme_text))


def check(counts: dict, readme_text: str, run_evals_text: str = "") -> list:
    """Return a list of failure descriptions (empty == consistent).

    `run_evals_text` is the run_evals.py source; when supplied, assert score's
    `_CONTRACTED_SECONDARY_POOL` matches DOCUMENTED_SECONDARY (S-1 single-sourcing).
    Defaults to "" so the in-memory count/README legs can be exercised standalone."""
    failures = []
    total = sum(counts.values())
    if total != EXPECTED_TOTAL:
        failures.append(
            f"evals.json total expectations = {total}, expected {EXPECTED_TOTAL} "
            f"(per-fixture: {counts}); the documented secondary pool "
            f"({DOCUMENTED_SECONDARY}) is now stale — update README and this guard.")
    if counts.get(1) != EXPECTED_FIXTURE1:
        failures.append(
            f"evals.json fixture id 1 has {counts.get(1)} expectations, expected "
            f"{EXPECTED_FIXTURE1}; the fixture-1 #8 exclusion is no longer "
            f"well-defined — update README and this guard.")
    if not readme_ties_secondary_to_26(readme_text):
        failures.append(
            f"README.md no longer ties graded secondary expectations to "
            f"{DOCUMENTED_SECONDARY} (expected a line like 'the judge grades "
            f"**26** secondary expectations'); the documented arithmetic is "
            f"unanchored.")
    if DOCUMENTED_SECONDARY != EXPECTED_TOTAL - 1:
        failures.append(
            f"documented secondary {DOCUMENTED_SECONDARY} != total "
            f"{EXPECTED_TOTAL} − 1 (the single fixture-1 #8 exclusion).")
    if run_evals_text and not run_evals_pins_contracted_pool(run_evals_text):
        failures.append(
            f"run_evals.py no longer pins `_CONTRACTED_SECONDARY_POOL = "
            f"{DOCUMENTED_SECONDARY}` (S-1's reconciliation anchor); score's "
            f"diagnostic 26 has drifted from this guard's DOCUMENTED_SECONDARY.")
    return failures


def main() -> int:
    evals = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
    counts = expectation_counts(evals)
    readme_text = README.read_text(encoding="utf-8")
    run_evals_text = RUN_EVALS.read_text(encoding="utf-8")
    failures = check(counts, readme_text, run_evals_text)
    if failures:
        print("INQUISITOR SECONDARY-COUNT DRIFT — the documented 26 is "
              "inconsistent with evals.json / README:")
        for f in failures:
            print(f"  {f}")
        print("\nIf evals.json expectation counts changed, update the documented "
              "secondary pool (README.md + score's label) and the constants in "
              "scripts/check_inquisitor_secondary_count.py.")
        return 1
    print(f"OK — evals.json totals {EXPECTED_TOTAL} expectations "
          f"(fixture 1 = {EXPECTED_FIXTURE1}); README ties graded secondary to "
          f"{DOCUMENTED_SECONDARY} == {EXPECTED_TOTAL} − 1 (the fixture-1 #8 "
          f"exclusion); run_evals.py pins _CONTRACTED_SECONDARY_POOL = "
          f"{DOCUMENTED_SECONDARY}.")
    return 0


def selftest() -> int:
    """Built-in logic tests (in-memory) for the count + README anchor checks."""
    good_counts = {1: 10, 2: 9, 3: 8}                       # total 27
    good_readme = ("...the judge grades **26** secondary expectations "
                   "(10−1 + 9 + 8) and ...")
    good_run_evals = "_CONTRACTED_SECONDARY_POOL = 26\n"
    failures = []

    # positive leg — current evals.json/README/run_evals shape passes
    res = check(good_counts, good_readme, good_run_evals)
    if res:
        failures.append(f"positive: clean shape unexpectedly failed: {res}")

    # negative leg A — a different expectation count (an added expectation) FAILS
    res = check({1: 10, 2: 9, 3: 9}, good_readme)           # total 28
    if not res:
        failures.append("negative-A: a changed expectation count was NOT caught")

    # negative leg B — README missing the 26 anchor FAILS
    res = check(good_counts, "...the judge grades the secondary expectations...")
    if not res:
        failures.append("negative-B: README missing the 26 anchor was NOT caught")

    # robustness — an incidental '26' elsewhere must NOT satisfy the anchor
    if readme_ties_secondary_to_26("we filed issue #426 and graded 5 expectations"):
        failures.append("robustness: an incidental 26 wrongly satisfied the anchor")

    # negative leg C (S-1) — run_evals.py missing/drifted _CONTRACTED_SECONDARY_POOL FAILS
    res = check(good_counts, good_readme, "_CONTRACTED_SECONDARY_POOL = 25\n")
    if not res:
        failures.append("negative-C: drifted _CONTRACTED_SECONDARY_POOL was NOT caught")

    # the real committed tree must pass too (catches anchor regex vs real wording)
    real_counts = expectation_counts(
        json.loads(EVALS_JSON.read_text(encoding="utf-8")))
    real_res = check(real_counts, README.read_text(encoding="utf-8"),
                     RUN_EVALS.read_text(encoding="utf-8"))
    if real_res:
        failures.append(f"real-tree: committed evals.json/README/run_evals failed: "
                        f"{real_res}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("SELFTEST OK — positive leg passes; a changed expectation count, a "
          "README missing the 26 anchor, and a drifted _CONTRACTED_SECONDARY_POOL "
          "all FAIL; an incidental 26 is rejected; and the real committed tree "
          "passes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
