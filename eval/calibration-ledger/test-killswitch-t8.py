#!/usr/bin/env python3
"""T-8: CRUCIBLE_CALIBRATION_DISABLED=1 silences the consumer-side advisories.

Covers the consumer-side kill-switch (L-6) added in Phase 6. The emit-side
enforcement already shipped in Phase 1's ledger-append.md; this pins that BOTH
consumer paths honor the switch.

Two layers:
  - PURE: advisory_line() and stale_advisory_line() return None when
    disabled=True, on inputs that WOULD otherwise print (proving the gate is
    the switch, not the data).
  - IO: an end-to-end CLI run with CRUCIBLE_CALIBRATION_DISABLED=1 against a
    populated central store (CRUCIBLE_LEDGER_DIR) emits NOTHING on stdout, and
    the same run WITHOUT the switch DOES emit (proving the fixture is live).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

SCRIPT = os.path.join(REPO_ROOT, "scripts", "brier_advisory.py")

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def test_pure_advisory_disabled():
    from scripts.brier_advisory import advisory_line
    brier = {"quality-gate": {"n": 9, "brier": 0.42}}  # would print
    on = advisory_line(brier, "quality-gate", falsification_exists=True,
                       staleness_days=0.0, disabled=False)
    off = advisory_line(brier, "quality-gate", falsification_exists=True,
                        staleness_days=0.0, disabled=True)
    _check("T-8.1 advisory_line: prints when enabled", on is not None, f"got {on!r}")
    _check("T-8.2 advisory_line: silent when disabled", off is None, f"got {off!r}")


def test_pure_stale_disabled():
    from scripts.brier_advisory import stale_advisory_line
    on = stale_advisory_line(falsification_exists=True, staleness_days=20.0,
                             disabled=False)
    off = stale_advisory_line(falsification_exists=True, staleness_days=20.0,
                              disabled=True)
    _check("T-8.3 stale_advisory_line: prints when enabled", on is not None, f"got {on!r}")
    _check("T-8.4 stale_advisory_line: silent when disabled", off is None, f"got {off!r}")


def _run(args, ledger_dir, disabled):
    env = dict(os.environ)
    env["CRUCIBLE_LEDGER_DIR"] = ledger_dir
    if disabled:
        env["CRUCIBLE_CALIBRATION_DISABLED"] = "1"
    else:
        env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    out = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, env=env,
    )
    return out.stdout.strip()


def test_cli_end_to_end():
    tmp = tempfile.mkdtemp(prefix="t8-cli-")
    try:
        # Populate a live central store: a fresh falsification.jsonl + a
        # brier-rolling.json that WOULD trip the advisory.
        with open(os.path.join(tmp, "falsification.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"ledger_entry_hash": "h", "falsified": True}) + "\n")
        with open(os.path.join(tmp, "brier-rolling.json"), "w", encoding="utf-8") as f:
            json.dump({"quality-gate": {"n": 8, "brier": 0.40,
                                        "last_updated": "2026-06-01T00:00:00Z"}}, f)
        # Make the falsification file recently modified so stale-check is fresh
        # but advisory still fires (advisory needs only n/brier + not->30d-stale).
        now = time.time()
        os.utime(os.path.join(tmp, "falsification.jsonl"), (now, now))

        adv_on = _run(["advisory", "quality-gate"], tmp, disabled=False)
        adv_off = _run(["advisory", "quality-gate"], tmp, disabled=True)
        _check("T-8.5 CLI advisory prints when enabled", adv_on != "", f"got {adv_on!r}")
        _check("T-8.6 CLI advisory silent when disabled", adv_off == "", f"got {adv_off!r}")

        # stale-check: backdate falsification.jsonl to 20 days so it WOULD nudge.
        old = now - 20 * 86400
        os.utime(os.path.join(tmp, "falsification.jsonl"), (old, old))
        st_on = _run(["stale-check"], tmp, disabled=False)
        st_off = _run(["stale-check"], tmp, disabled=True)
        _check("T-8.7 CLI stale-check prints when enabled", st_on != "", f"got {st_on!r}")
        _check("T-8.8 CLI stale-check silent when disabled", st_off == "", f"got {st_off!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_pure_advisory_disabled()
    test_pure_stale_disabled()
    test_cli_end_to_end()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
