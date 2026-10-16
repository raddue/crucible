#!/usr/bin/env python3
"""Structural check for warden's single-call-site integration in build + finish (#464).

Invocation (from repo root):
    python3 scripts/check_warden_integration.py            # gate the real files
    python3 scripts/check_warden_integration.py --selftest # in-memory logic test

The warden cutover (Task 12) replaced the per-leg review dispatches in build's
Phase-4 workflow and finish's review path with a SINGLE `Use crucible:warden`
call each (design I-W5 / T-W4 / T-W5), killing the old double-temper (build
Phase 4 → finish both re-ran the reviewer set). This check asserts that
end-state holds on the real SKILL.md files — it does NOT edit them.

Six assertions (each has a BAD-sample `--selftest` case that trips it — the check
is proven non-tautological):

  build/SKILL.md, over the extracted Phase-4 WORKFLOW section:
    A1  exactly ONE `Use crucible:warden` imperative dispatch (the Step-3 gate).
    A2  ZERO residual leg dispatches (`Use crucible:{temper,inquisitor,siege,
        quality-gate,red-team}`) — warden replaced them (I-W4).
    A4  the finish-skip step instructs finish to `skip finish's warden call`
        (the structural double-temper kill).
  build/SKILL.md, over the `### Verdict Marker Verification` region (a SEPARATE
  locator — this line lives OUTSIDE the Phase-4 slice):
    A3  the recovery re-invoke names `warden`, NOT bare `quality-gate` (T-W12 /
        I-W7: a missing marker must not silently downgrade recovery to a
        red-team-only bare-quality-gate re-run — the fail-open guard).
  finish/SKILL.md, over the Step-2→Step-4 review region:
    A5  exactly ONE `Use crucible:warden` imperative dispatch (Step 2).
    A6  ZERO residual `Use crucible:{temper,red-team}` imperative dispatch (Step 3
        was deleted; the red-team leg lives inside warden).

CRITICAL: every assertion keys on the IMPERATIVE `Use crucible:<leg>` DISPATCH
form, never a descriptive `crucible:<leg>` / bare-name mention. Descriptive prose
legitimately survives — build's eval-gate pointer lists "temper, inquisitor,
optional siege, quality-gate" dispatches by name; build's warden step says "Do
NOT separately invoke temper / inquisitor / siege / quality-gate"; finish's
Step-2.75 note says "Run this BEFORE red-team"; finish's anti-pattern / Integration
lines name the retired `crucible:red-team` dispatch (Task 18 owns that disclosed-deferred prose). None
of those are `Use crucible:<leg>`, so keying on the dispatch form leaves them be.

SECTION-SCOPED, NOT WHOLE-FILE: build/SKILL.md carries the `## Phase 4: Completion`
heading TWICE (an early `pipeline-status.md` TEMPLATE block, then the real WORKFLOW
section) — the extractor takes the LAST match (mirrors
`check_build_clean_tree_contract.py`). Scoping to the Phase-4 workflow slice is
load-bearing for A2: the Phase-1 design gate (`Use crucible:quality-gate` ~L644)
and Phase-2 plan gate (~L794) are OUTSIDE the slice and correctly not counted — a
whole-file grep would false-positive on them.

Style mirrors `scripts/check_build_clean_tree_contract.py`: ROOT-from-`__file__`,
error accumulation, `sys.exit(main())`, stdlib only, no argparse.

NOTE: this file matches `scripts/check_warden_*.py`, so `check_warden_structure.py`'s
emission-surface scan greps it for an imperative ledger emit — it deliberately
carries no such token.
"""
from __future__ import annotations

import pathlib
import re
import sys

from build_source import read_runbook

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "skills/build/SKILL.md"
FINISH = ROOT / "skills/finish/SKILL.md"

# The residual reviewer legs warden replaced (A2). A descriptive mention of any of
# these is fine — only the imperative `Use crucible:<leg>` dispatch form counts.
_BUILD_RESIDUAL_LEGS = ("temper", "inquisitor", "siege", "quality-gate", "red-team")
# finish's Step 3 (red-team) and old code-review (temper) legs (A6).
_FINISH_RESIDUAL_LEGS = ("temper", "red-team")

# Extract the real `## Phase 4: Completion` WORKFLOW section: from that heading up
# to the next `## ` heading (or EOF), taking the LAST match — an earlier
# `pipeline-status.md` template block reuses the heading and must not shadow it.
# (Identical construction to check_build_clean_tree_contract.py, by design.)
_PHASE4_RE = re.compile(
    r"^## Phase 4: Completion\b.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)

# Extract the `### Verdict Marker Verification` region: from that heading up to the
# next `## ` or `### ` heading (or EOF). The recovery re-invoke line (A3) lives
# here, OUTSIDE the Phase-4 workflow slice, so it needs its own locator.
_MARKER_REGION_RE = re.compile(
    r"^### Verdict Marker Verification\b.*?(?=^#{2,3} |\Z)",
    re.DOTALL | re.MULTILINE)

# Extract finish's review region: `### Step 2: Review Gate` up to `### Step 4`
# (covers Step 2, 2.5, 2.75, 3.5 — the whole review path, before base-branch
# selection). A5/A6 are scoped here, not whole-file.
_FINISH_REVIEW_RE = re.compile(
    r"^### Step 2: Review Gate\b.*?(?=^### Step 4\b|\Z)",
    re.DOTALL | re.MULTILINE)

# A4 — build's finish-skip step must carry this literal skip instruction (the
# double-temper kill). Copied verbatim from build/SKILL.md (straight apostrophe).
_SKIP_WARDEN_LITERAL = "skip finish's warden call"

# A3 — the recovery re-invoke must name warden; a bare-quality-gate re-invoke is
# the I-W7 fail-open footgun. `re-invoke warden` (GOOD) vs `re-invoke quality-gate`
# (BAD). The GOOD line's "NOT bare `quality-gate`" is NOT preceded by "re-invoke ",
# so the forbidden pattern does not false-fire on it.
_RECOVERY_NAMES_WARDEN_RE = re.compile(r"re-invoke\s+warden\b")
_RECOVERY_BARE_QG_RE = re.compile(r"re-invoke\s+`?quality-gate\b")


def _last_section(pat: re.Pattern[str], text: str) -> str:
    matches = pat.findall(text)
    return matches[-1] if matches else ""


def _first_section(pat: re.Pattern[str], text: str) -> str:
    m = pat.search(text)
    return m.group(0) if m else ""


def count_dispatch(section: str, leg: str) -> int:
    """Count imperative `Use crucible:<leg>` dispatches in `section`. Keys on the
    dispatch form only (a trailing word boundary), so a descriptive `crucible:<leg>`
    or bare-name mention is not counted."""
    return len(re.findall(r"Use crucible:" + re.escape(leg) + r"\b", section))


def check_build(text: str) -> list[str]:
    """A1/A2/A4 over the Phase-4 workflow slice + A3 over the marker region."""
    errs: list[str] = []
    phase4 = _last_section(_PHASE4_RE, text)
    if not phase4:
        errs.append("A1/A2/A4: Phase 4 workflow section not found "
                    "(no `## Phase 4: Completion` heading)")
    else:
        # A1 — exactly ONE warden dispatch.
        n_warden = count_dispatch(phase4, "warden")
        if n_warden != 1:
            errs.append(f"A1: expected exactly 1 `Use crucible:warden` dispatch in "
                        f"build's Phase-4 workflow, found {n_warden}")
        # A2 — zero residual leg dispatches.
        for leg in _BUILD_RESIDUAL_LEGS:
            n = count_dispatch(phase4, leg)
            if n:
                errs.append(f"A2: residual `Use crucible:{leg}` dispatch in build's "
                            f"Phase-4 workflow ({n}) — warden replaced it (I-W4)")
        # A4 — finish-skip step kills the double-temper.
        if _SKIP_WARDEN_LITERAL not in phase4:
            errs.append(f"A4: build's finish-skip step must instruct finish to "
                        f"`{_SKIP_WARDEN_LITERAL}` (the double-temper kill)")
    # A3 — recovery re-invoke names warden (separate region locator).
    errs.extend(check_recovery_repoint(_first_section(_MARKER_REGION_RE, text)))
    return errs


def check_recovery_repoint(region: str) -> list[str]:
    """A3 (T-W12 / I-W7): the marker-verification recovery re-invoke must name
    `warden`, NOT bare `quality-gate` — else a missing marker silently downgrades
    recovery to a red-team-only re-run (the fail-open)."""
    if not region:
        return ["A3: `### Verdict Marker Verification` region not found"]
    errs: list[str] = []
    if not _RECOVERY_NAMES_WARDEN_RE.search(region):
        errs.append("A3: recovery re-invoke must name `warden` "
                    "(re-invoke warden on the same artifact)")
    if _RECOVERY_BARE_QG_RE.search(region):
        errs.append("A3: recovery re-invoke names bare `quality-gate` — the I-W7 "
                    "fail-open (a missing marker must not downgrade recovery to a "
                    "red-team-only bare-quality-gate re-run); must re-invoke warden")
    return errs


def check_finish(text: str) -> list[str]:
    """A5/A6 over finish's Step-2→Step-4 review region."""
    region = _first_section(_FINISH_REVIEW_RE, text)
    if not region:
        return ["A5/A6: finish review region not found "
                "(no `### Step 2: Review Gate` heading)"]
    errs: list[str] = []
    # A5 — exactly ONE warden dispatch.
    n_warden = count_dispatch(region, "warden")
    if n_warden != 1:
        errs.append(f"A5: expected exactly 1 `Use crucible:warden` dispatch in "
                    f"finish's review path, found {n_warden}")
    # A6 — zero residual temper/red-team dispatches.
    for leg in _FINISH_RESIDUAL_LEGS:
        n = count_dispatch(region, leg)
        if n:
            errs.append(f"A6: residual `Use crucible:{leg}` dispatch in finish's "
                        f"review path ({n}) — the leg lives inside warden now")
    return errs


# --------------------------------------------------------------------------
# selftest — self-contained GOOD/BAD samples (do NOT read the real files)
# --------------------------------------------------------------------------
# GOOD build sample. Structure mirrors the real file's load-bearing shape:
#   - a `pipeline-status.md` TEMPLATE `## Phase 4: Completion` block FIRST (the
#     extractor must take the LAST match);
#   - a `### Verdict Marker Verification` region with the warden recovery line;
#   - Phase-1 + Phase-2 sections carrying `Use crucible:quality-gate` (the design/
#     plan gates) — these must NOT be counted by A2 (they are OUTSIDE the Phase-4
#     slice). The real `## Phase 4: Completion` is the LAST heading, so `matches[-1]`
#     lands on the slice that excludes them.
_GOOD_BUILD = """\
## Phase 4: Completion
Status: NOT_STARTED
```

(template pipeline-status block above — reuses the heading; the extractor takes
the LAST match, so this block never shadows the real workflow section.)

### Verdict Marker Verification

6. If verification fails:
   - **Normal flow:** do NOT write PASS. Output warning and re-invoke warden on
     the same artifact (the full reviewer set — NOT bare `quality-gate`, else
     recovery downgrades to red-team-only and the I-W7 fail-open re-opens).

### Skip Escape Hatch

Some prose.

## Phase 1: Design

3. **REQUIRED SUB-SKILL:** Use crucible:quality-gate on the design doc.

## Phase 2: Plan

3. **REQUIRED SUB-SKILL:** Use crucible:quality-gate on the plan.

## Phase 4: Completion

After all tasks complete:

3. **REQUIRED SUB-SKILL:** Use crucible:warden on the full implementation. warden
   runs temper + delve + red-team + siege + inquisitor. Do NOT separately invoke
   temper / inquisitor / siege / quality-gate here — warden is the sole gate.
7. **RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`, retrospective mode).
8. **RECOMMENDED SUB-SKILL:** Use /recon persistent-map mode (record mode).
11. **REQUIRED SUB-SKILL:** Use crucible:finish — **skip finish's warden call**
    (warden already ran in build Phase 4 — the structural double-temper kill).

## Escalation Triggers (Any Phase)
"""

# GOOD finish sample. Step-2 warden dispatch; Step-2.75 carries the DESCRIPTIVE
# "BEFORE red-team" prose (must NOT trip A6, proving A6 keys on the dispatch form).
_GOOD_FINISH = """\
### Step 2: Review Gate (Mandatory)

**REQUIRED SUB-SKILL:** Use crucible:warden — the single review gate that runs the
full reviewer set (temper + delve + red-team + siege + inquisitor) as one
disjunction-of-native-gates. This subsumes the old separate code-review (temper)
and red-team steps.

### Step 2.5: Test Alignment Audit

**RECOMMENDED SUB-SKILL:** Use crucible:verify (test-alignment mode) — audit alignment.

### Step 2.75: Forge Retrospective

**RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`) — capture what happened. Run this
BEFORE red-team so the retrospective has the full execution state.

### Step 4: Determine Base Branch

Some prose.
"""


def selftest() -> int:
    # ------------------------------------------------------------------ build
    # GOOD: all four build assertions pass. This ALSO proves A2's no-false-
    # positive guard — the sample's Phase-1/Phase-2 `Use crucible:quality-gate`
    # dispatches sit OUTSIDE the Phase-4 slice and are NOT counted.
    good_build_errs = check_build(_GOOD_BUILD)
    assert good_build_errs == [], f"GOOD build should pass, got: {good_build_errs}"
    assert not any(e.startswith("A2") for e in check_build(_GOOD_BUILD)), (
        "A2 false-positive: Phase-1/2 `Use crucible:quality-gate` (outside the "
        "Phase-4 slice) must NOT be counted")

    # A1 BAD (zero): removing the warden dispatch → A1 fires.
    a1_zero = _GOOD_BUILD.replace(
        "Use crucible:warden on the full implementation", "run the reviewers")
    assert any(e.startswith("A1") for e in check_build(a1_zero)), (
        f"A1 (0 warden) should fire, got: {check_build(a1_zero)}")
    # A1 BAD (two): a second warden dispatch INSIDE the Phase-4 slice → A1 fires.
    a1_two = _GOOD_BUILD.replace(
        "7. **RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`, retrospective mode).",
        "7. **REQUIRED SUB-SKILL:** Use crucible:warden again.")
    assert any(e.startswith("A1") for e in check_build(a1_two)), (
        f"A1 (2 warden) should fire, got: {check_build(a1_two)}")

    # A2 BAD: a residual `Use crucible:temper` dispatch INSIDE the Phase-4 slice.
    a2_bad = _GOOD_BUILD.replace(
        "8. **RECOMMENDED SUB-SKILL:** Use /recon persistent-map mode (record mode).",
        "8. **REQUIRED SUB-SKILL:** Use crucible:temper on the implementation.")
    assert any(e.startswith("A2") for e in check_build(a2_bad)), (
        f"A2 (residual temper in Phase-4) should fire, got: {check_build(a2_bad)}")

    # A3 BAD: a `:241`-style recovery line that re-invokes bare quality-gate.
    a3_bad = _GOOD_BUILD.replace(
        "re-invoke warden on\n     the same artifact",
        "re-invoke quality-gate on\n     the same artifact")
    a3_errs = check_build(a3_bad)
    assert any(e.startswith("A3") for e in a3_errs), (
        f"A3 (bare-quality-gate recovery) should fire, got: {a3_errs}")

    # A4 BAD: a finish-skip step lacking the skip-warden instruction.
    a4_bad = _GOOD_BUILD.replace(
        "**skip finish's warden call**", "run finish normally")
    assert any(e.startswith("A4") for e in check_build(a4_bad)), (
        f"A4 (missing skip-warden) should fire, got: {check_build(a4_bad)}")

    # ----------------------------------------------------------------- finish
    good_finish_errs = check_finish(_GOOD_FINISH)
    assert good_finish_errs == [], f"GOOD finish should pass, got: {good_finish_errs}"
    # A6 no-false-positive: the Step-2.75 descriptive "BEFORE red-team" prose in the
    # GOOD sample does NOT trip A6 (proven by GOOD passing above; assert explicitly).
    assert not any(e.startswith("A6") for e in check_finish(_GOOD_FINISH)), (
        "A6 false-positive: descriptive 'BEFORE red-team' prose must NOT trip")

    # A5 BAD (zero): removing the warden dispatch → A5 fires.
    a5_zero = _GOOD_FINISH.replace(
        "Use crucible:warden — the single review gate", "review the changes")
    assert any(e.startswith("A5") for e in check_finish(a5_zero)), (
        f"A5 (0 warden) should fire, got: {check_finish(a5_zero)}")
    # A5 BAD (two): a second warden dispatch in the review region → A5 fires.
    a5_two = _GOOD_FINISH.replace(
        "**RECOMMENDED SUB-SKILL:** Use crucible:verify (test-alignment mode) — audit alignment.",
        "**REQUIRED SUB-SKILL:** Use crucible:warden a second time.")
    assert any(e.startswith("A5") for e in check_finish(a5_two)), (
        f"A5 (2 warden) should fire, got: {check_finish(a5_two)}")

    # A6 BAD: a residual `Use crucible:red-team` DISPATCH in the review region.
    a6_bad = _GOOD_FINISH.replace(
        "**RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`) — capture what happened.",
        "**REQUIRED SUB-SKILL:** Use crucible:red-team on the changes.")
    assert any(e.startswith("A6") for e in check_finish(a6_bad)), (
        f"A6 (residual red-team dispatch) should fire, got: {check_finish(a6_bad)}")

    print("selftest OK — build A1 (exactly-1 warden; 0-case and 2-case both fire), "
          "A2 (0 residual legs; the Phase-1/2 `Use crucible:quality-gate` OUTSIDE "
          "the slice does NOT false-positive, a `Use crucible:temper` INSIDE it "
          "does), A3 (recovery names warden; a bare-quality-gate re-invoke fires), "
          "A4 (finish-skip kills the double-temper; its absence fires); finish A5 "
          "(exactly-1 warden; 0- and 2-cases fire), A6 (0 residual temper/red-team "
          "dispatch; descriptive 'BEFORE red-team' prose does NOT trip, a "
          "`Use crucible:red-team` dispatch does) — each has an exercised BAD case.")
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    errs: list[str] = []
    for path, checker in ((BUILD, check_build), (FINISH, check_finish)):
        if not path.is_file():
            errs.append(f"{path.relative_to(ROOT)} does not exist")
            continue
        errs.extend(checker(read_runbook() if path == BUILD else path.read_text(encoding="utf-8")))

    if errs:
        print("WARDEN INTEGRATION CHECK FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — build + finish each carry exactly one warden call site, no residual "
          "leg dispatch, the double-temper kill, and a warden-named recovery.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
