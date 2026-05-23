"""F2: regression coverage for legacy --mock-reviewer and --replay paths.

The snapshot is generated OUT-OF-BAND via `python -m skills.temper.evals.bootstrap_snapshot`,
reviewed and committed. The test below ONLY asserts — it never writes the snapshot.
This prevents silent capture of local reviewer-output deltas as the canonical baseline.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

# 2P-R4-3: Both helpers use Path(__file__).resolve() to handle symlinked checkouts uniformly.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SNAPSHOT = _REPO_ROOT / "skills" / "temper" / "evals" / "mock_snapshot.json"
_MOCK_DIR = _REPO_ROOT / "skills" / "temper" / "evals" / "mock-fixtures"
_EVALS_JSON = _REPO_ROOT / "skills" / "temper" / "evals" / "evals.json"

def _run_mock(tmp_path: Path) -> dict:
    """Run --mock-reviewer and return per-fixture verdicts.

    2P-FE-2 R3: writes go to tmp_path, never to the repo-tracked last_run.json.
    """
    last_run_out = tmp_path / "last_run.json"
    env = {**os.environ, "TEMPER_LAST_RUN_OVERRIDE": str(last_run_out)}
    subprocess.run(
        # DEVIATION FROM PLAN: use sys.executable instead of literal "python".
        # The host CI/runtime does not symlink `python` → `python3` (Debian/Ubuntu
        # default without `python-is-python3`). sys.executable is the portable
        # form and matches the convention used inside bootstrap_snapshot.py.
        [sys.executable, "-m", "skills.temper.evals.run_evals",
         "--mock-reviewer", str(_MOCK_DIR)],
        check=True, capture_output=True, text=True, timeout=120,
        cwd=str(_REPO_ROOT), env=env,
    )
    out = json.loads(last_run_out.read_text())
    return {f["id"]: f["verdict"] for f in out["fixtures"]}

def test_legacy_mock_reviewer_matches_snapshot(tmp_path):
    """Assert ONLY — never bootstrap. Missing snapshot is a hard failure."""
    if not _SNAPSHOT.exists():
        pytest.fail(
            f"Snapshot missing at {_SNAPSHOT}. "
            f"Run bootstrap script locally: "
            f"`python -m skills.temper.evals.bootstrap_snapshot`. "
            f"Review the generated mock_snapshot.json, then `git add` and commit "
            f"BOTH bootstrap_snapshot.py and mock_snapshot.json before pushing."
        )
    snapshot = json.loads(_SNAPSHOT.read_text())
    # S-R7-2: snapshot is a structured envelope {"bootstrap_python": "X.Y", "verdicts": {...}}.
    # Pin the snapshot to the bootstrapping Python's MAJOR.MINOR so cross-env drift
    # surfaces loudly. If lens_runner output is empirically version-stable across
    # 3.10/3.11/3.12 (per AC-8), this check can be softened to a warning via a
    # follow-up issue once stability is empirically established.
    # TODO(S-R7-2): track cross-version stability; relax to warning once confirmed.
    expected_py = snapshot.get("bootstrap_python")
    runtime_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert expected_py == runtime_py, (
        f"snapshot was bootstrapped under Python {expected_py!r} but tests are running "
        f"under {runtime_py!r}. Either (a) re-bootstrap under Python {runtime_py} via "
        f"`python -m skills.temper.evals.bootstrap_snapshot`, or (b) if you have "
        f"empirically confirmed cross-version stability of lens_runner output, "
        f"update the snapshot's `bootstrap_python` field manually and document why."
    )
    expected = snapshot["verdicts"]
    # S-R4-2: sanity-floor assertions. If a prior bootstrap silently produced a
    # truncated/empty snapshot (e.g. subprocess error swallowed), the equality
    # assertion below would pass trivially — so explicitly floor the shape first.
    # `expected` is a flat {fixture_id: verdict} dict; assert both cardinality and
    # verdict-presence. Floor is derived from evals.json so it stays current as
    # fixtures are added.
    expected_n = len(json.loads(_EVALS_JSON.read_text())["evals"])
    assert len(expected) >= expected_n, (
        f"snapshot has <{expected_n} fixtures (expected N={expected_n}); re-bootstrap via "
        f"`python -m skills.temper.evals.bootstrap_snapshot`"
    )
    assert all(isinstance(v, str) and v for v in expected.values()), (
        "snapshot fixtures missing verdict strings (expected PASS/FAIL/N/A)"
    )
    actual = _run_mock(tmp_path)
    assert actual == expected, (
        f"legacy --mock-reviewer verdicts diverged from snapshot.\n"
        f"expected: {expected}\nactual:   {actual}\n"
        f"If this divergence is intentional, re-run "
        f"`python -m skills.temper.evals.bootstrap_snapshot` and review the diff."
    )
