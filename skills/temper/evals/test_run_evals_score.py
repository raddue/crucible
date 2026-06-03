"""Tests for score() subcommand (Task 6 of #297).

SP3 / F-1: All tests in this file MUST redirect output paths via monkeypatch —
never hardcode `skills/temper/evals/...` paths. The shared `_seed_dispatch_dir`
helper monkeypatches _LAST_RUN, _BASELINE_PATH, and _EVALS_DIR to tmp_path.

Post-Task-13.5: `_resolve_output_path()` reads `_EVALS_DIR` at call time, so
monkeypatching `_EVALS_DIR` alone is sufficient for both the shared and per-iter
output paths. `_LAST_RUN` is still monkeypatched by `_seed_dispatch_dir` only to
exercise the legacy `TEMPER_LAST_RUN_OVERRIDE` env-var path. Tests that read the
shared output file should use `tmp_path / "last_run.json"` directly — not
`run_evals._LAST_RUN` — since that attribute is not the routing source post-13.5.
"""
from __future__ import annotations

import json
from pathlib import Path

from skills.temper.evals import run_evals
from skills.temper.evals.run_evals import score, stage


def _seed_dispatch_dir(monkeypatch, tmp_path, run_id="R-score"):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    # SP3 / F-1: redirect last_run.json, baseline.json, AND _EVALS_DIR to tmp_path
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    dispatch_dir = stage(run_id)
    return dispatch_dir


def test_score_with_no_results_returns_n_a(monkeypatch, tmp_path):
    d = _seed_dispatch_dir(monkeypatch, tmp_path)
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-score", allow_incomplete=False)
    assert rc in (0, 1)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert "fixtures" in out
    for fr in out["fixtures"]:
        assert all(o is None for o in fr["reviewer_outputs"])


def test_score_refuses_when_collect_status_absent(monkeypatch, tmp_path):
    """2P-2 R5: score() returns rc (no sys.exit) — assert return-code."""
    _seed_dispatch_dir(monkeypatch, tmp_path)
    rc = score("R-score")
    assert rc == 2


def test_score_allow_incomplete_writes_incomplete_header(monkeypatch, tmp_path):
    _seed_dispatch_dir(monkeypatch, tmp_path)
    score("R-score", allow_incomplete=True)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert out.get("incomplete") is True
    assert "incomplete-cause" not in out  # cause undetermined per S-2


def test_score_all_error_sets_incomplete_cause(monkeypatch, tmp_path):
    """M-4 R5 / AC-14: when all dispatches errored, last_run.json header carries
    `incomplete-cause: all-error` AND score refuses to PASS.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-allerr")
    manifest = json.loads((d / "stage-manifest.json").read_text())
    total = len(manifest["trials"])
    (d / ".collect-status").write_text(f"complete\nerrors: {total}/{total}\n")
    rc = score("R-allerr", allow_incomplete=False)
    assert rc == 2
    score("R-allerr", allow_incomplete=True)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert out.get("incomplete") is True
    assert out.get("incomplete-cause") == "all-error", (
        f"AC-14: expected incomplete-cause: all-error, got {out.get('incomplete-cause')!r}"
    )


def test_score_no_stage_manifest_returns_fatal(monkeypatch, tmp_path):
    """No stage-manifest.json at dispatch dir → rc=2."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    rc = score("R-nonexistent")
    assert rc == 2


def test_write_baseline_produces_matching_baseline_json(monkeypatch, tmp_path):
    """Task 8 AC-10b: --write-baseline emits baseline.json mirroring last_run
    verdicts + a template_sha header (SP-1)."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-base")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-base", write_baseline=True)
    # F-1: read via module attributes (monkeypatched to tmp_path) — NOT via
    # hardcoded skills/temper/evals/ paths.
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    last_run = json.loads(run_evals._LAST_RUN.read_text())
    # Header carries template_sha (SP-1)
    assert "template_sha" in baseline
    # Verdicts match
    assert [f["verdict"] for f in baseline["fixtures"]] == [
        f["verdict"] for f in last_run["fixtures"]
    ]


def test_compare_baseline_exits_nonzero_on_regression(monkeypatch, tmp_path):
    """Task 8 AC-10c: --compare-baseline returns non-zero when current verdicts
    regress relative to baseline."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-cmp")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-cmp", write_baseline=True)
    # F-1: mutate via module-attribute path (monkeypatched to tmp_path)
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    if baseline["fixtures"]:
        baseline["fixtures"][0]["verdict"] = "PASS"  # claim baseline was PASS
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    # New run with all-N/A (no results) — compare should detect regression
    rc = score("R-cmp", compare_baseline=True)
    # rc==1 iff regression; rc==2 if incomplete-blocked; either signals nonzero
    assert rc != 0


def test_compare_baseline_refuses_incomplete(monkeypatch, tmp_path):
    """AC-13 + Override Flags: --compare-baseline refuses to compare incomplete."""
    _seed_dispatch_dir(monkeypatch, tmp_path, "R-incomplete")
    # Skip .collect-status
    score("R-incomplete", allow_incomplete=True)  # writes incomplete: true
    rc = score("R-incomplete", compare_baseline=True, allow_incomplete=True)
    assert rc == 2  # explicit refusal exit


def test_compare_baseline_warns_on_template_drift(monkeypatch, tmp_path, capsys):
    """SP2 R8: when current template_sha differs from baseline.template_sha,
    --compare-baseline emits a `[warn]` line to stderr (apples-to-oranges narration).

    Asserts the warn-not-refuse asymmetry documented in Task 8's M6 R6 note:
    template_sha drift is informational; the comparison still proceeds.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-drift")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-drift", write_baseline=True)
    # Mutate baseline.template_sha to a different value to simulate drift
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    baseline["template_sha"] = "0" * 64  # bogus sha, certain to differ from current
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    capsys.readouterr()  # clear prior output
    score("R-drift", compare_baseline=True)
    captured = capsys.readouterr()
    assert "[warn]" in captured.err
    assert "template_sha drift" in captured.err, (
        "SP2 R8: --compare-baseline must emit a template_sha drift warning"
    )


def test_dispatch_live_symbol_remains_deleted():
    """S-FE-2 R3: post-#297, `_dispatch_live` must not exist as a module attribute.

    Guards against accidental re-introduction (e.g. a future revert that doesn't
    cleanly remove the function, or a copy-paste from git history that re-adds it).
    If you genuinely need a subprocess-based dispatcher again, file a new issue
    and re-design the legacy boundary — do NOT silently re-add `_dispatch_live`.
    """
    import pytest
    from skills.temper.evals import run_evals
    with pytest.raises(AttributeError):
        run_evals._dispatch_live  # noqa: B018  (intentional attribute probe)


def test_aggregate_from_outputs_has_no_implicit_closure_leak():
    """S2 R8/R9: enumerate the kwargs `_aggregate_from_outputs` must carry
    explicitly so that closure-leak regressions surface as a signature mismatch
    rather than a NameError at first call.

    The canonical closure-dep set was captured by Task 6 Step 0 inspection and is
    inlined here so the test is reproducible on any fresh clone (the prior
    /tmp/_aggregate_closure_deps.txt artifact did not survive `/tmp` cleanup
    or CI).
    """
    import inspect

    from skills.temper.evals.run_evals import _aggregate_from_outputs

    # Canonical closure-dep set (Task 6 Step 0 inspection output, inlined for
    # reproducibility — see _aggregate_from_outputs docstring).
    expected = {"n_trials", "threshold"}
    sig = inspect.signature(_aggregate_from_outputs)
    params = set(sig.parameters)
    assert "fix" in params
    assert "reviewer_outputs" in params
    kwargs = params - {"fix", "reviewer_outputs"}
    assert kwargs == expected, (
        f"S2 R9: closure-dep mismatch: signature has {kwargs}, expected {expected}. "
        f"Update _aggregate_from_outputs signature OR update the expected set here."
    )


# ---------------------------------------------------------------------------
# Task 7: structural DISPATCH_STATUS sentinel parser (S-1, I-T6)
# ---------------------------------------------------------------------------


def test_parse_result_file_ok(tmp_path):
    """M-2: use tmp_path, not hardcoded /tmp/, to avoid parallel-test collisions."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-ok.md"
    p.write_text("DISPATCH_STATUS: OK\n\n### Code Review\nVerdict: Clean\n")
    out = _parse_result_file(p)
    assert out is not None
    assert "Code Review" in out
    assert "DISPATCH_STATUS" not in out  # stripped from body


def test_parse_result_file_error_returns_none(tmp_path):
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-err.md"
    p.write_text("DISPATCH_STATUS: ERROR: timeout\n\n")
    out = _parse_result_file(p)
    assert out is None


def test_parse_result_file_collision_safety(tmp_path):
    """I-T6: reviewer body containing literal 'DISPATCH_STATUS:' must not flip parse."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-collision.md"
    p.write_text(
        "DISPATCH_STATUS: OK\n\n"
        "### Code Review\nThe code mentions DISPATCH_STATUS: ERROR but that's a quote.\n"
    )
    out = _parse_result_file(p)
    assert out is not None
    assert "DISPATCH_STATUS: ERROR" in out  # body preserved


def test_parse_result_file_empty_body_returns_none(tmp_path):
    """S1: `OK\\n\\n` with empty body returns None, not empty string."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-empty.md"
    p.write_text("DISPATCH_STATUS: OK\n\n")
    out = _parse_result_file(p)
    assert out is None


def test_parse_result_file_whitespace_only_body_returns_none(tmp_path):
    """S1 R10: `OK` with whitespace-only body returns None — strip-check
    semantics align with SKILL.md Step 7's empty-body promotion gate."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-ws.md"
    p.write_text("DISPATCH_STATUS: OK\n\n   \n\t\n")
    out = _parse_result_file(p)
    assert out is None


def test_ac3_smoke_coverage_delegated_to_legacy_modes():
    """AC-3: `--mock-reviewer` end-to-end smoke.

    Per #297 plan Task 10, the AC-3 smoke is delegated to
    `test_legacy_modes.py::test_legacy_mock_reviewer_matches_snapshot`,
    which is strictly stronger than the original tautological "claude not in
    stderr" smoke: it asserts per-fixture verdict equality against the
    committed pre-#297 snapshot. This marker test enforces that the
    delegation target still exists.
    """
    from pathlib import Path
    legacy_modes = Path(__file__).parent / "test_legacy_modes.py"
    assert legacy_modes.exists(), (
        "AC-3 delegation target missing: test_legacy_modes.py was deleted "
        "or renamed. Either restore it or update AC-3 coverage here."
    )
    contents = legacy_modes.read_text()
    assert "def test_legacy_mock_reviewer_matches_snapshot" in contents, (
        "AC-3 delegation target test function was renamed; update marker test."
    )


# ---------------------------------------------------------------------------
# Task 13: wire --per-iter flag (F1, F-R4-1)
# ---------------------------------------------------------------------------


def test_score_per_iter_flag_writes_separate_file(monkeypatch, tmp_path):
    """F1: --per-iter routes output to last_run-<run_id>.json; shared file untouched.

    Post-Task-13.5: `_resolve_output_path()` reads `_EVALS_DIR` at call time, so
    monkeypatching `_EVALS_DIR` alone is sufficient for BOTH the shared and per-iter
    output paths. The `_LAST_RUN` monkeypatch in `_seed_dispatch_dir` is preserved
    only to exercise the legacy `TEMPER_LAST_RUN_OVERRIDE` env-var path.

    M-R4-1: `_EVALS_JSON` is bound at import time AND used by name at runtime —
    monkeypatching `_EVALS_DIR` does NOT retroactively redirect `_EVALS_JSON`. If a
    future test needs to redirect fixture data, it must monkeypatch `_EVALS_JSON`
    separately.

    M-5 R5: `_seed_dispatch_dir` already monkeypatches `_EVALS_DIR` to `tmp_path`,
    so no additional `_EVALS_DIR` monkeypatch is needed here.
    """
    import time
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "Rcalprefix-1")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")

    # Pre-populate the shared last_run.json with sentinel content, capture mtime
    shared = tmp_path / "last_run.json"  # _seed_dispatch_dir sets _EVALS_DIR → tmp_path
    shared.write_text('{"sentinel": "untouched"}')
    mtime_before = shared.stat().st_mtime
    time.sleep(0.01)  # ensure any write would change mtime

    score("Rcalprefix-1", per_iter=True, allow_incomplete=False)

    # S-FE-5 R3: per-iter file lives under .calibrate-state/
    per_iter_path = tmp_path / ".calibrate-state" / "last_run-Rcalprefix-1.json"
    assert per_iter_path.exists()
    # SP5: shared last_run.json MUST NOT be overwritten
    assert shared.stat().st_mtime == mtime_before
    assert json.loads(shared.read_text()) == {"sentinel": "untouched"}

def test_score_without_per_iter_writes_shared(monkeypatch, tmp_path):
    """F1 inverse: no --per-iter ⇒ shared last_run.json is written, no per-iter file.

    M-FE-4 R3: run-id ends in `-15` (digits) — this proves the new explicit
    `--per-iter` flag is the routing trigger, NOT run-id shape. Under the
    pre-F1 regex heuristic (`-\\d+$`), this run-id would have been MIS-ROUTED
    to a per-iter path; under the F1 explicit flag, it correctly writes shared.

    Post-Task-13.5: `_resolve_output_path()` reads `_EVALS_DIR` at call time, so
    monkeypatching `_EVALS_DIR` alone is sufficient. The redundant `_EVALS_DIR` and
    `_LAST_RUN` monkeypatches that previously appeared here have been removed —
    `_seed_dispatch_dir` already sets `_EVALS_DIR` to `tmp_path`.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-2026-04-15")  # run-id ends in -<digits>!
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    shared = tmp_path / "last_run.json"

    score("R-2026-04-15", per_iter=False, allow_incomplete=False)

    assert shared.exists()  # shared written
    # No per-iter file created — proves regex-heuristic would have wrongly routed this
    assert not (tmp_path / ".calibrate-state" / "last_run-R-2026-04-15.json").exists()

def test_per_iter_flag_not_silently_dropped(monkeypatch, tmp_path):
    """F-R4-1: argparse declaration + main() wiring land atomically in Task 13 (S-1 R5).

    Guards against a regression where `--per-iter` argparse declaration and main()
    wiring split across two commits — between them, `score R-x --per-iter` would
    parse the flag and silently drop it, clobbering shared last_run.json.

    This test exercises the CLI path (via main()) to prove the flag is honored:
    the per-iter file is written AND the shared last_run.json is left untouched.
    """
    import time
    from skills.temper.evals.run_evals import main
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-flag-drop")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    shared = tmp_path / "last_run.json"  # _seed_dispatch_dir sets _EVALS_DIR → tmp_path
    shared.write_text('{"sentinel": "untouched"}')
    mtime_before = shared.stat().st_mtime
    time.sleep(0.01)

    rc = main(["score", "R-flag-drop", "--per-iter"])
    assert rc in (0, 1)

    # Per-iter path written
    per_iter_path = tmp_path / ".calibrate-state" / "last_run-R-flag-drop.json"
    assert per_iter_path.exists(), \
        "--per-iter was parsed but silently dropped (F-R4-1 regression)"
    # Shared file untouched
    assert shared.stat().st_mtime == mtime_before
    assert json.loads(shared.read_text()) == {"sentinel": "untouched"}

def test_score_help_lists_per_iter():
    """F-R4-1: argparse declaration for --per-iter lives in Task 13 (S-1 R5), not Task 4.

    Asserted here (rather than in Task 4's argparse-help golden test) because
    the flag does not exist on the score subparser until this task lands.
    """
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "skills.temper.evals.run_evals", "score", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    assert "--per-iter" in out, "Task 13 must add --per-iter to score subparser"


# ---------------------------------------------------------------------------
# Task 13.5: _resolve_output_path() helper (S4 R6)
# ---------------------------------------------------------------------------


def test_score_handles_malformed_errors_line(monkeypatch, tmp_path, capsys):
    """QG R1 Fix 1: malformed `.collect-status` errors-line surfaces fatal+rc=2,
    not raw ValueError/IndexError traceback."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-malformed")
    (d / ".collect-status").write_text("complete\nerrors: garbage\n")
    rc = score("R-malformed", allow_incomplete=False)
    assert rc == 2
    captured = capsys.readouterr()
    assert "malformed" in captured.err
    assert ".collect-status" in captured.err


def test_score_honors_manifest_trials_override(monkeypatch, tmp_path):
    """QG R1 Fix 2: when stage runs with --trials-override 5, score must report
    `5` as the denominator (not the evals.json replicate_rule trials count)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    d = stage("R-toverride", trials_override=5)
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-toverride", allow_incomplete=False)
    out = json.loads((tmp_path / "last_run.json").read_text())
    # Every fixture must report n_trials=5 (denominator) and matching rationale
    assert out["fixtures"], "no fixtures in output"
    for fr in out["fixtures"]:
        assert fr["trials"] == 5, (
            f"fixture {fr['id']!r} reports trials={fr['trials']}, expected 5 "
            f"(manifest trials_override should be canonical)"
        )
        for er in fr["expectations"]:
            assert "/5 trials" in er["aggregated_rationale"], (
                f"expectation rationale {er['aggregated_rationale']!r} "
                f"does not honor manifest trials_override=5"
            )


def test_compare_baseline_handles_corrupt_baseline_json(monkeypatch, tmp_path, capsys):
    """QG R1 Fix 3: corrupt/truncated baseline.json surfaces fatal+rc=2,
    not raw JSONDecodeError traceback."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-corrupt")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    # Write a valid run first
    score("R-corrupt", allow_incomplete=False)
    # Now write a truncated baseline (simulates interrupted --write-baseline)
    run_evals._BASELINE_PATH.write_text('{"fixtures": [{"id":')
    rc = score("R-corrupt", compare_baseline=True, allow_incomplete=False)
    assert rc == 2
    captured = capsys.readouterr()
    assert "malformed" in captured.err
    assert "baseline.json" in captured.err


def test_score_write_is_atomic(monkeypatch, tmp_path):
    """QG R2 Fix 1: atomic write — no `.tmp` artifact survives, no truncated file."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-atomic")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-atomic", allow_incomplete=False)
    assert rc in (0, 1)
    # No tmp residue
    assert not any(p.name.endswith(".tmp") for p in tmp_path.rglob("*"))
    # File is valid JSON (not truncated)
    out = tmp_path / "last_run.json"
    json.loads(out.read_text())  # raises if malformed


def test_compare_baseline_warns_on_added_fixture(monkeypatch, tmp_path, capsys):
    """QG R2 Fix 3 / QG R3 Fix 1: fixtures added to evals.json since baseline emit
    a [warn] but don't block. Drift is now measured against the live evals.json keyset,
    not the manifest payload — so a fixture present in evals.json but not in baseline
    correctly appears as "added"."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-added")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-added", write_baseline=True)
    # Mutate baseline: drop all-but-first fixture so the remaining evals.json fixtures
    # appear "added to evals.json since baseline". The manifest scope is unchanged —
    # only the baseline is trimmed, so the drift is detected via the evals.json comparison.
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    assert len(baseline["fixtures"]) >= 2, "need >=2 fixtures to simulate addition"
    baseline["fixtures"] = baseline["fixtures"][:1]
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    capsys.readouterr()
    rc = score("R-added", compare_baseline=True, allow_incomplete=False)
    captured = capsys.readouterr()
    # additions don't block: rc must not be the "removed fixtures" refusal (rc=2)
    assert rc != 2, f"additions should not block compare; got rc={rc}, stderr={captured.err!r}"
    assert "added to evals.json since baseline" in captured.err


def test_compare_baseline_refuses_removed_fixture(monkeypatch, tmp_path, capsys):
    """QG R2 Fix 3 / QG R3 Fix 1: fixtures removed from evals.json post-baseline block
    compare with rc=2 unless --allow-fixture-drift is passed (prevents silent
    regression-laundering by fixture deletion). Drift is now measured against the live
    evals.json keyset — adding a ghost to baseline simulates a fixture deleted from
    evals.json."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-removed")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-removed", write_baseline=True)
    # Mutate baseline to ADD a fake fixture id that doesn't exist in evals.json
    # → simulates fixture being removed from evals.json since baseline was taken.
    # The live evals.json does not contain "ghost-fixture-id", so drift is detected.
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    baseline["fixtures"].append({"id": "ghost-fixture-id", "verdict": "PASS"})
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    # Without flag: refused
    capsys.readouterr()
    rc = score("R-removed", compare_baseline=True, allow_incomplete=False)
    captured = capsys.readouterr()
    assert rc == 2, f"removed fixtures should refuse without flag; got rc={rc}"
    assert "removed from evals.json" in captured.err
    # With flag: proceeds (rc=0 since remaining fixtures show no regression)
    rc2 = score(
        "R-removed",
        compare_baseline=True,
        allow_incomplete=False,
        allow_fixture_drift=True,
    )
    assert rc2 == 0, f"--allow-fixture-drift should allow comparison; got rc={rc2}"


def test_compare_baseline_allows_scoped_stage(monkeypatch, tmp_path, capsys):
    """QG R3 regression: stage --fixture <subset> + score --compare-baseline must NOT
    falsely report fixture drift; the manifest scope < evals.json scope is legitimate.

    Setup: write baseline against a full run, then score a subset manifest.
    The subset manifest has fewer fixtures than evals.json but that is NOT a deletion —
    evals.json still contains all fixtures. Assert: no fixture-drift warning, no rc=2,
    normal comparison on the subset.
    """
    # Seed a full dispatch dir and write baseline
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-scoped-full")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-scoped-full", write_baseline=True)

    # Now stage a SCOPED run (only the first fixture id from the real evals.json)
    evals_data = json.loads(run_evals._EVALS_JSON.read_text())
    all_fixture_ids = [f["id"] for f in evals_data.get("evals", [])]
    assert len(all_fixture_ids) >= 2, "need >=2 fixtures to test scoping"
    subset_id = all_fixture_ids[0]

    d2 = stage("R-scoped-sub", fixture=subset_id)
    (d2 / ".collect-status").write_text("complete\nerrors: 0/0\n")

    capsys.readouterr()
    rc = score("R-scoped-sub", compare_baseline=True, allow_incomplete=False)
    captured = capsys.readouterr()

    # The subset manifest has fewer fixtures than evals.json, but evals.json still
    # has all fixtures → no fixture-drift warning, no rc=2
    assert "removed from evals.json" not in captured.err, (
        f"R3 regression: false fixture-drift for scoped stage. stderr={captured.err!r}"
    )
    assert rc != 2, (
        f"R3 regression: scoped stage score rc=2 (should be 0 or 1). stderr={captured.err!r}"
    )


def test_resolve_output_path_uses_current_evals_dir(monkeypatch, tmp_path):
    """S4 R6: _resolve_output_path reads _EVALS_DIR at CALL TIME, not import time.

    Eliminates the asymmetry where tests previously had to monkeypatch _LAST_RUN
    AND _EVALS_DIR separately. After this refactor, monkeypatching _EVALS_DIR
    alone is sufficient for BOTH the shared and per-iter output paths.
    """
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    p_shared = run_evals._resolve_output_path("R-x", per_iter=False)
    p_iter = run_evals._resolve_output_path("R-x", per_iter=True)
    assert p_shared == tmp_path / "last_run.json"
    assert p_iter == tmp_path / ".calibrate-state" / "last_run-R-x.json"


# ---------------------------------------------------------------------------
# Task 10 (#290): --source CLI filter on score subcommand
# ---------------------------------------------------------------------------


def test_source_values_constant_exported():
    """Shared constant _SOURCE_VALUES exists and lists the three expected values."""
    from skills.temper.evals.run_evals import _SOURCE_VALUES
    assert set(_SOURCE_VALUES) == {"synthetic", "real-pr", "all"}


def test_score_source_filter_synthetic_scores_all_synthetic_fixtures(
    monkeypatch, tmp_path
):
    """--source synthetic: synthetic fixtures still scored (current evals.json
    is synthetic-only, so payload['fixtures'] is non-empty)."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-syn")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-syn", source="synthetic")
    assert rc in (0, 1)
    payload = json.loads(run_evals._LAST_RUN.read_text())
    assert len(payload["fixtures"]) > 0


def test_score_source_filter_real_pr_scores_only_real_pr_fixtures(
    monkeypatch, tmp_path
):
    """--source real-pr: synthetic-staged trials are filtered out → only real-PR
    fixtures appear in payload.

    Post-Task-7 the 5 real-PR fixtures exist (surgical-real, dry-real, srp-real,
    ocp-real, mixed-real). The dispatch dir seeded by `_seed_dispatch_dir` stages
    synthetic-side trials only; with `--source real-pr` filter, real-PR fixtures
    are scored with no staged trials → N/A aggregated verdicts.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-real")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-real", source="real-pr")
    # rc 0 = no FAILs (N/A verdicts don't count as failures)
    assert rc == 0
    payload = json.loads(run_evals._LAST_RUN.read_text())
    fixture_ids = {f["id"] for f in payload["fixtures"]}
    assert fixture_ids == {
        "surgical-real",
        "stagnation-real",
    }
    # No real-PR trials staged → all verdicts are N/A (not PASS/FAIL).
    for fx in payload["fixtures"]:
        for exp in fx["expectations"]:
            assert exp["aggregated_verdict"] == "N/A"


def test_score_source_filter_invalid_rejected():
    """argparse rejects --source frob with SystemExit(2)."""
    from skills.temper.evals.run_evals import main
    import pytest as _pytest
    with _pytest.raises(SystemExit) as excinfo:
        main(["score", "R-x", "--source", "frob"])
    assert excinfo.value.code == 2


def test_score_source_filter_all_is_default(monkeypatch, tmp_path):
    """--source all (and default) scores every staged fixture."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-all")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc_explicit = score("R-all", source="all")
    payload_explicit = json.loads(run_evals._LAST_RUN.read_text())

    d2 = _seed_dispatch_dir(monkeypatch, tmp_path, "R-all2")
    (d2 / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc_default = score("R-all2")
    payload_default = json.loads(run_evals._LAST_RUN.read_text())

    # Same fixture set in both
    assert [f["id"] for f in payload_explicit["fixtures"]] == [
        f["id"] for f in payload_default["fixtures"]
    ]
    assert rc_explicit == rc_default


def test_score_source_filter_cli_passthrough(monkeypatch, tmp_path):
    """`score R-x --source synthetic` via CLI wires through to score()."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-cli")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    from skills.temper.evals.run_evals import main
    rc = main(["score", "R-cli", "--source", "synthetic"])
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# Task 11 (#290 S3): grouped summary + by_source + drift_delta + per_trial_rates
# ---------------------------------------------------------------------------


def _seed_with_results(monkeypatch, tmp_path, run_id, outcomes_by_fixture):
    """Seed a dispatch dir AND write reviewer-output result files per fixture.

    outcomes_by_fixture: dict[fixture_id, list[str|None]] — one entry per trial.
        Use None to simulate ERROR (dispatch failure); a non-empty string emits
        a reviewer-shaped body. The body content drives convergence_runner's verdict.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, run_id)
    manifest = json.loads((d / "stage-manifest.json").read_text())
    # Group trial seqs by fixture_id (sorted by trial #)
    for entry in manifest["trials"]:
        fid = entry["fixture_id"]
        trial = entry["trial"]
        outputs = outcomes_by_fixture.get(fid)
        if outputs is None:
            continue
        if trial - 1 >= len(outputs):
            continue
        body = outputs[trial - 1]
        result_path = d / entry["result_file"]
        if body is None:
            # Simulate dispatch ERROR
            result_path.write_text("DISPATCH_STATUS: ERROR: simulated\n\n", encoding="utf-8")
        else:
            result_path.write_text(
                f"DISPATCH_STATUS: OK\n\n{body}", encoding="utf-8"
            )
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    return d


def test_last_run_has_by_source_block(monkeypatch, tmp_path):
    """Task 11: last_run.json contains a `by_source` block keyed by source."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-bysrc")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-bysrc", source="all")
    payload = json.loads(run_evals._LAST_RUN.read_text())
    assert "by_source" in payload
    assert "synthetic" in payload["by_source"]
    assert "real-pr" in payload["by_source"]
    # Synthetic fixtures (from evals.json) are present in by_source.synthetic.
    syn_ids = {e["id"] for e in payload["by_source"]["synthetic"]}
    assert "clean-after-resolve" in syn_ids  # known synthetic convergence fixture
    # Each entry carries id + verdict
    for entry in payload["by_source"]["synthetic"]:
        assert "id" in entry and "verdict" in entry


def test_last_run_has_drift_delta_block(monkeypatch, tmp_path):
    """#333: last_run.json contains a finding-level `drift_delta` (overall)."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-drift")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-drift", source="all")
    payload = json.loads(run_evals._LAST_RUN.read_text())
    assert "drift_delta" in payload
    assert "overall" in payload["drift_delta"]


def test_last_run_has_per_trial_rates_block(monkeypatch, tmp_path):
    """#333: last_run.json contains a finding-level `per_trial_rates` (overall)."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-rates")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-rates", source="all")
    payload = json.loads(run_evals._LAST_RUN.read_text())
    assert "per_trial_rates" in payload
    assert "overall" in payload["per_trial_rates"]
    block = payload["per_trial_rates"]["overall"]
    assert "synthetic" in block
    assert "real-pr" in block


def test_grouped_summary_overall_synthetic_rate():
    """#333: _compute_grouped_summary computes an overall synthetic PASS rate
    from the per-trial verdicts (no per-lens columns)."""
    from skills.temper.evals.run_evals import _compute_grouped_summary
    fixtures_by_id = {
        "fx-syn-a": {"id": "fx-syn-a", "source": "synthetic"},
        "fx-syn-b": {"id": "fx-syn-b", "source": "synthetic"},
    }
    fixture_results = [
        {
            "id": "fx-syn-a",
            "verdict": "PASS", "trials": 2, "threshold": 1,
            "expectations": [{"per_trial_verdicts": ["PASS", "PASS"]}],
            "reviewer_outputs": ["body", "body"],
        },
        {
            "id": "fx-syn-b",
            "verdict": "FAIL", "trials": 2, "threshold": 1,
            "expectations": [{"per_trial_verdicts": ["FAIL", "FAIL"]}],
            "reviewer_outputs": ["body", "body"],
        },
    ]
    summary = _compute_grouped_summary(fixture_results, fixtures_by_id)
    syn_ids = {e["id"] for e in summary["by_source"]["synthetic"]}
    assert syn_ids == {"fx-syn-a", "fx-syn-b"}
    # 2 PASS + 2 FAIL across both fixtures → overall synthetic rate = 2/4 = 0.5
    assert summary["per_trial_rates"]["overall"]["synthetic"] == 0.5
    # No real-pr fixtures → real rate None, drift None.
    assert summary["per_trial_rates"]["overall"]["real-pr"] is None
    assert summary["drift_delta"]["overall"] is None


def test_grouped_summary_error_excluded_from_denominator():
    """#333 (carries forward R1 M4): ERROR trials (None reviewer_output) are
    excluded from the per-trial-rate denominator."""
    from skills.temper.evals.run_evals import _compute_grouped_summary
    fixtures_by_id = {
        "fx-syn": {"id": "fx-syn", "source": "synthetic"},
        "fx-real": {"id": "fx-real", "source": "real-pr"},
    }
    fixture_results = [
        {
            "id": "fx-syn",
            "verdict": "PASS", "trials": 2, "threshold": 1,
            "expectations": [{"per_trial_verdicts": ["PASS", "PASS"]}],
            "reviewer_outputs": ["body", "body"],
        },
        {
            "id": "fx-real",
            "verdict": "PASS", "trials": 2, "threshold": 1,
            "expectations": [{"per_trial_verdicts": ["PASS", "N/A"]}],
            # 2nd trial: None reviewer_output → ERROR (excluded from denom)
            "reviewer_outputs": ["body", None],
        },
    ]
    summary = _compute_grouped_summary(fixture_results, fixtures_by_id)
    # Real-PR: 1 PASS, 0 FAIL, 1 ERROR → rate = 1/1 = 1.0
    assert summary["per_trial_rates"]["overall"]["real-pr"] == 1.0
    # drift_delta = synthetic_rate - real_rate = 1.0 - 1.0 = 0.0
    assert summary["drift_delta"]["overall"] == 0.0


def test_grouped_summary_na_maps_to_fail_not_error():
    """#333 (carries forward R3 SP1): ERROR maps ONLY from None reviewer_output;
    convergence_runner-inconclusive N/A trials are FAIL (counted in the denominator)."""
    from skills.temper.evals.run_evals import _compute_grouped_summary
    fixtures_by_id = {
        "fx-real": {"id": "fx-real", "source": "real-pr"},
    }
    fixture_results = [
        {
            "id": "fx-real",
            "verdict": "N/A", "trials": 2, "threshold": 1,
            "expectations": [{"per_trial_verdicts": ["N/A", "N/A"]}],
            # Both reviewer_outputs non-None → N/A maps to FAIL, not ERROR.
            "reviewer_outputs": ["body", "body"],
        },
    ]
    summary = _compute_grouped_summary(fixture_results, fixtures_by_id)
    # 0 PASS, 2 FAIL, 0 ERROR → rate = 0/2 = 0.0
    assert summary["per_trial_rates"]["overall"]["real-pr"] == 0.0


def test_summary_grouped_print(monkeypatch, tmp_path, capsys):
    """Task 11 Step 1: stdout summary shows grouped 'Synthetic: N/N' and 'Real-PR: N/N' lines."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-grp")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-grp", source="all")
    # The grouped summary is emitted from score()'s stdout writes (added in T11).
    captured = capsys.readouterr()
    # Both groups should be present (synthetic + real-pr fixtures exist in evals.json)
    assert "Synthetic:" in captured.out
    assert "Real-PR:" in captured.out
