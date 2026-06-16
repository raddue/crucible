#!/usr/bin/env python3
"""Structural CI guard for the inquisitor Phase-1b exec harness (#424, design §9).

Invocation (from repo root):
    python3 scripts/check_inquisitor_phase1b_invariants.py            # check the repo
    python3 scripts/check_inquisitor_phase1b_invariants.py --selftest # logic tests

Static assertions over the staged-prompt files + a dry exec/pilot stage:
  - POOL prompt byte-identical to WITHOUT (hash equality).
  - MID scaffold hash == WITH dimension scaffold hash (scaffold parity, S1).
  - Neutral-proxy hash != WITH-scaffold AND != WITHOUT byte-hash (S4) PLUS a
    positive "framing removed" check (contains the shared exec body, does NOT
    contain the cross-component framing WITHOUT carries).
  - Uniform per-agent 5-test budget in every execution prompt; NO per-arm 25 ceiling.
  - `stage --pilot` emits neutral-proxy-only; full exec stage emits all four arms.
  - Every fixture bug_id has exactly one fixes/<id>.patch referenced by GT fix_patch;
    the patches compose into all-fixed.
  - The §7 KEEP statistic is `beyond_spread`, NOT `trial_spread` (score module).

Stdlib only. Exit 0 clean / 1 on any violation.
"""
from __future__ import annotations
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skills.inquisitor.evals import run_evals  # noqa: E402
from skills.inquisitor.evals import _fixtures  # noqa: E402


# --- pure predicates (selftest-covered) -----------------------------------

def framing_removed(without_text: str, neutral_text: str, marker: str) -> bool:
    """Neutral proxy drops the cross-component framing but keeps the exec body."""
    shared = "pytest"
    return (marker in without_text and marker not in neutral_text
            and shared in without_text and shared in neutral_text)


def budget_ok(text: str) -> bool:
    """Carries the uniform 5-test per-agent budget and NO per-arm 25 ceiling.

    M-2: match the standalone token ``25`` (a per-arm ceiling) via a word-boundary
    regex rather than the brittle ``"25" in text`` substring, so an incidental byte
    sequence like a line number or ``2025`` can't false-fail the guard.
    """
    return "5 tests" in text and not re.search(r"\b25\b", text)


# --- repo checks ----------------------------------------------------------

def _dry_stage_arms(pilot: bool) -> list:
    """Run a minimal exec/pilot stage in an isolated dispatch dir; return arms."""
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, XDG_RUNTIME_DIR=tmp, USER="invariant-check")
        old = {k: os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "USER")}
        os.environ.update(env)
        try:
            trials = run_evals._PILOT_MIN_TRIALS if pilot else 1
            dd = run_evals.stage("phase1b-invariant-check",
                                 repo="notify", trials=trials, pilot=pilot, force=True)
            import json
            m = json.loads((dd / "stage-manifest.json").read_text())
            return m["arms"], m["prompt_shas"]
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def check_repo() -> list:
    v = []
    ev = ROOT / "skills/inquisitor/evals"
    without = (ev / "without-prompt-eval.md").read_text()
    pool = (ev / "pool-prompt-eval.md").read_text()
    neutral = (ev / "neutral-proxy-prompt-eval.md").read_text()

    # framing-removed (positive) + budget on the bare exec prompts
    if not framing_removed(without, neutral, run_evals._FRAMING_MARKER):
        v.append("neutral-proxy framing-removed check failed (must drop "
                 f"{run_evals._FRAMING_MARKER!r}, keep the exec body)")
    for name, text in (("without", without), ("pool", pool),
                       ("neutral-proxy", neutral),
                       ("with-scaffold", run_evals._EXEC_SCAFFOLD)):
        if not budget_ok(text):
            v.append(f"{name} prompt fails the 5-test/no-25-ceiling budget check")

    # hash relationships via a dry exec stage
    arms, ph = _dry_stage_arms(pilot=False)
    if arms != ["with", "pool", "mid", "without"]:
        v.append(f"exec stage arms != 4-arm set: {arms}")
    if ph["pool"] != ph["without"]:
        v.append("POOL prompt hash != WITHOUT hash (parity broken)")
    if ph["with_scaffold"] != ph["mid_scaffold"]:
        v.append("MID scaffold hash != WITH scaffold hash (parity broken)")
    if ph["neutral_proxy"] in (ph["without"], ph["with_scaffold"]):
        v.append("neutral-proxy hash collides with WITHOUT or WITH-scaffold")

    pilot_arms, _ = _dry_stage_arms(pilot=True)
    if pilot_arms != ["neutral-proxy"]:
        v.append(f"pilot stage arms != ['neutral-proxy']: {pilot_arms}")

    # fixture bug_id <-> patch <-> GT fix_patch + composition into all-fixed
    import json
    fix_dir = ev / "fixtures"
    for repo in sorted(p.name for p in fix_dir.glob("*")
                       if (p / "manifest.json").exists()):
        rd = fix_dir / repo
        man = _fixtures.load_manifest(rd)
        gt = json.loads((rd / "ground-truth-bugs.json").read_text())
        gt_fix = {b["bug_id"]: b["fix_patch"] for b in gt["bugs"]}
        for bid in man["bug_ids"]:
            if not (rd / "fixes" / f"{bid}.patch").exists():
                v.append(f"{repo}: missing fixes/{bid}.patch")
            if gt_fix.get(bid) != f"fixes/{bid}.patch":
                v.append(f"{repo}: GT fix_patch for {bid} != fixes/{bid}.patch")
        try:  # patches compose into all-fixed (zero-fuzz)
            d = _fixtures.all_fixed(rd)
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        except Exception as e:  # noqa: BLE001
            v.append(f"{repo}: patches do not compose into all-fixed: {e}")

    # KEEP statistic is beyond_spread, not trial_spread (score module text)
    src = (ev / "run_evals.py").read_text()
    if '"statistic": "beyond_spread"' not in src:
        v.append("score_exec KEEP statistic is not pinned to beyond_spread")
    if "trial_spread is explicitly REJECTED" not in src:
        v.append("score_exec does not record trial_spread as the rejected gate")
    return v


def selftest() -> int:
    failures = []
    if not framing_removed("uses cross-component framing; run pytest",
                           "run pytest only", "cross-component"):
        failures.append("framing_removed should pass when marker dropped, body kept")
    if framing_removed("cross-component; pytest", "cross-component; pytest",
                       "cross-component"):
        failures.append("framing_removed should fail when marker NOT dropped")
    if framing_removed("cross-component; pytest", "no body here", "cross-component"):
        failures.append("framing_removed should fail when shared exec body dropped")
    if not budget_ok("at most 5 tests per agent"):
        failures.append("budget_ok should pass for a 5-test prompt")
    if budget_ok("up to 25 tests per arm"):
        failures.append("budget_ok should fail on a per-arm 25 ceiling")
    if budget_ok("no budget stated"):
        failures.append("budget_ok should fail when no 5-test budget present")
    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK — framing-removed and budget predicates behave.")
    return 0


def main() -> int:
    v = check_repo()
    if v:
        print("FAIL — Phase-1b invariants:")
        for s in v:
            print(f"  - {s}")
        return 1
    print("PASS — Phase-1b structural invariants hold "
          "(POOL/scaffold/neutral hashes, budget, arms, fixtures, KEEP stat).")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
