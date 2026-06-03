"""Tests for global_expectations Pre-flight matcher + mutex hard-fail wiring.

Covers (T2):
  - `_load_evals` folds top-level `global_expectations` into every eval, and is
    a clean no-op when the key is absent.
  - stage- and score-side `fixture_sha` match for the same fixture once the
    global expectations are folded in (the merged expectations list is
    identical across both load paths).
  - an invalid `global_expectations` entry (unknown check) raises
    `FixtureValidationError` at validation.
"""

import json

import pytest

from skills.temper.evals.run_evals import (
    FixtureValidationError,
    _load_evals,
    _validate_global_expectations,
)
from skills.temper.evals._dispatch_paths import fixture_sha


def _write_evals(tmp_path, payload: dict):
    p = tmp_path / "evals.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_load_evals_appends_global_expectations_to_every_eval(tmp_path):
    ge = {"type": "mechanical", "check": "all-findings-have-file-line"}
    payload = {
        "global_expectations": [ge],
        "evals": [
            {"id": "a", "expectations": [{"type": "mechanical", "check": "findings-count-at-least"}]},
            {"id": "b"},  # no expectations key — helper must create it
        ],
    }
    p = _write_evals(tmp_path, payload)
    evals, globals_returned = _load_evals(p)

    assert globals_returned == [ge]
    # eval "a": original expectation preserved + global appended
    assert evals[0]["expectations"][-1] == ge
    assert len(evals[0]["expectations"]) == 2
    # eval "b": expectations list created with the global appended
    assert evals[1]["expectations"] == [ge]


def test_load_evals_noop_when_key_absent(tmp_path):
    payload = {
        "evals": [
            {"id": "a", "expectations": [{"type": "mechanical", "check": "findings-count-at-least"}]},
            {"id": "b"},
        ],
    }
    p = _write_evals(tmp_path, payload)
    evals, globals_returned = _load_evals(p)

    assert globals_returned == []
    # eval "a" unchanged
    assert evals[0]["expectations"] == [{"type": "mechanical", "check": "findings-count-at-least"}]
    # eval "b" gained NO expectations key (clean no-op)
    assert "expectations" not in evals[1]


def test_real_evals_json_folds_preflight_global():
    """The live evals.json now carries the global Pre-flight matcher (T4).
    `_load_evals` must surface it and fold it into EVERY eval's expectations."""
    from skills.temper.evals.run_evals import _EVALS_JSON

    raw = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    evals, globals_returned = _load_evals(_EVALS_JSON)

    # The single global expectation is the Pre-flight report-has-block matcher.
    assert globals_returned == [
        {
            "type": "mechanical",
            "check": "report-has-block",
            "params": {"heading": "Pre-flight"},
        }
    ]

    # Every eval's loaded expectations = its on-disk expectations + each global.
    for raw_ev, loaded_ev in zip(raw["evals"], evals):
        expected = list(raw_ev.get("expectations") or []) + globals_returned
        assert loaded_ev.get("expectations") == expected
        # And the Pre-flight matcher is present on each eval.
        assert globals_returned[0] in loaded_ev["expectations"]


def test_stage_and_score_fixture_sha_match_with_global_expectations(tmp_path):
    """The merged expectations list (and thus fixture_sha) is identical across
    the two independent load paths a real stage/score pair would take."""
    ge = {"type": "mechanical", "check": "all-findings-have-file-line"}
    payload = {
        "global_expectations": [ge],
        "evals": [
            {"id": "a", "expectations": [{"type": "mechanical", "check": "findings-count-at-least"}]},
        ],
    }
    p = _write_evals(tmp_path, payload)

    # Two independent loads (stage path and score path both call _load_evals).
    stage_evals, _ = _load_evals(p)
    score_evals, _ = _load_evals(p)

    stage_fix = {f["id"]: f for f in stage_evals}["a"]
    score_fix = {f["id"]: f for f in score_evals}["a"]

    assert stage_fix["expectations"] == score_fix["expectations"]
    assert fixture_sha(stage_fix) == fixture_sha(score_fix)


def test_validate_global_expectations_rejects_unknown_check():
    bad = [{"type": "mechanical", "check": "no-such-check-xyz"}]
    with pytest.raises(FixtureValidationError, match="_CHECK_REGISTRY"):
        _validate_global_expectations(bad)


def test_validate_global_expectations_rejects_non_mechanical():
    bad = [{"type": "semantic", "check": "all-findings-have-file-line"}]
    with pytest.raises(FixtureValidationError, match="mechanical"):
        _validate_global_expectations(bad)


def test_validate_global_expectations_accepts_valid():
    good = [{"type": "mechanical", "check": "all-findings-have-file-line"}]
    _validate_global_expectations(good)  # no raise


def test_validate_global_expectations_accepts_snake_case_check():
    # snake_case must be normalized to kebab-case (as runtime dispatch does)
    # rather than rejected only to resolve fine when actually run.
    good = [{"type": "mechanical", "check": "report_has_block"}]
    _validate_global_expectations(good)  # no raise
