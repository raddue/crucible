"""Canonical snapshot bootstrap + verify for F2 regression coverage.

Reviewer outputs are deterministic via the committed mock-fixtures/, so the snapshot
encodes the verdict-tier of the pre-#297 legacy path. Commit BOTH this script and the
generated `mock_snapshot.json` in the same commit.

Modes (S1 R8):
  python -m skills.temper.evals.bootstrap_snapshot           # VERIFY: re-execute
                                                              # mock-reviewer, diff
                                                              # against existing
                                                              # snapshot, exit
                                                              # nonzero on drift.
                                                              # Bootstraps if file
                                                              # is absent.
  python -m skills.temper.evals.bootstrap_snapshot --force   # Overwrite existing
                                                              # snapshot (intentional
                                                              # re-bootstrap).
Verify-mode is the canonical pre-Task-9 invocation: idempotent + drift-detecting.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 2P-R4-3: Path(__file__).resolve() handles symlinked checkouts uniformly
# (matches the resolution used by test_legacy_modes.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SNAPSHOT = _REPO_ROOT / "skills" / "temper" / "evals" / "mock_snapshot.json"
_MOCK_DIR = _REPO_ROOT / "skills" / "temper" / "evals" / "mock-fixtures"
_EVALS_JSON = _REPO_ROOT / "skills" / "temper" / "evals" / "evals.json"

def main() -> int:
    # S1 R8: default behavior = VERIFY mode (idempotent re-run, compares against
    # existing snapshot). `--force` overwrites. Verify-mode is the canonical pre-
    # Task-9 invocation; it catches snapshot drift from environment/code changes
    # even when the Python-pin assertion would otherwise pass.
    force = "--force" in sys.argv[1:]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "last_run.json"
        env = {**os.environ, "TEMPER_LAST_RUN_OVERRIDE": str(out)}
        subprocess.run(
            [sys.executable, "-m", "skills.temper.evals.run_evals",
             "--mock-reviewer", str(_MOCK_DIR)],
            check=True, cwd=str(_REPO_ROOT), env=env,
        )
        data = json.loads(out.read_text())
        verdicts = {f["id"]: f["verdict"] for f in data["fixtures"]}

    expected_n = len(json.loads(_EVALS_JSON.read_text())["evals"])

    # S1 R8: VERIFY mode — snapshot exists and no --force. Re-execute mock-reviewer,
    # compare against the committed snapshot; exit nonzero with diff on mismatch.
    if _SNAPSHOT.exists() and not force:
        existing = json.loads(_SNAPSHOT.read_text())
        existing_verdicts = existing.get("verdicts", {})
        if existing_verdicts != verdicts:
            print(f"[bootstrap][drift] snapshot at {_SNAPSHOT} disagrees with "
                  f"freshly-executed mock-reviewer output.", file=sys.stderr)
            all_ids = sorted(set(existing_verdicts) | set(verdicts))
            for fid in all_ids:
                e, n = existing_verdicts.get(fid), verdicts.get(fid)
                if e != n:
                    print(f"  {fid}: snapshot={e!r} current={n!r}", file=sys.stderr)
            print(f"[bootstrap] investigate before re-bootstrapping. To overwrite "
                  f"intentionally, re-run with --force.", file=sys.stderr)
            return 3
        print(f"[bootstrap] verify-mode OK: snapshot matches current output.", file=sys.stderr)
        return 0
    # S-R7-2: pin the snapshot to the bootstrapping Python's MAJOR.MINOR so cross-env
    # drift surfaces loudly at test time rather than as a mysterious CI failure.
    snapshot_payload = {
        "bootstrap_python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "verdicts": verdicts,
    }
    # S-R4-2: refuse to write a hollow snapshot. If the subprocess silently
    # produced fewer fixtures than evals.json declares, the test would later pass
    # trivially — catch it at bootstrap time instead.
    if len(verdicts) < expected_n:
        print(f"[bootstrap][fatal] only {len(verdicts)} fixtures captured; expected >={expected_n}. "
              f"Refusing to write a hollow snapshot.", file=sys.stderr)
        return 2
    if not all(isinstance(v, str) and v for v in verdicts.values()):
        print(f"[bootstrap][fatal] one or more fixtures missing verdict strings. "
              f"Refusing to write a hollow snapshot.", file=sys.stderr)
        return 2
    _SNAPSHOT.write_text(json.dumps(snapshot_payload, indent=2, sort_keys=True))
    # Re-read and re-assert post-write (defense in depth against partial-write/IO truncation)
    reread = json.loads(_SNAPSHOT.read_text())
    reread_verdicts = reread.get("verdicts", {})
    # QG R1 Fix 5: `assert` is stripped under `python -O`, defeating the
    # defense-in-depth check the comment promises. Use explicit raise.
    if not (len(reread_verdicts) >= expected_n and all(reread_verdicts.values())):
        raise RuntimeError(
            "post-write snapshot validation failed; refuse to declare success"
        )
    if not reread.get("bootstrap_python"):
        raise RuntimeError("missing bootstrap_python pin in snapshot")
    print(f"[bootstrap] wrote {_SNAPSHOT}", file=sys.stderr)
    print(f"[bootstrap] REVIEW THE DIFF then `git add` and commit.", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
