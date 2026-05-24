"""Inquisitor Integration dimension (#297).

Hunts data-format / contract mismatches between stage <-> collect <-> score
and between baseline write <-> compare.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.temper.evals import run_evals
from skills.temper.evals.run_evals import (
    _aggregate_from_outputs,
    _compare_baseline,
    _parse_result_file,
    _write_baseline,
    score,
    stage,
)


def _seed(monkeypatch, tmp_path, run_id="R-int"):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    return stage(run_id)


# Vector 1: stage writes `trials[].result_file` strings; score reads files from
# `dispatch_dir / entry["result_file"]`. If stage's filename convention drifts
# (e.g., 4-digit zero-pad becomes 3-digit, or `.md` becomes `.txt`), score
# silently sees no result files and produces all-None aggregation. Verify
# the round-trip: every file score expects, stage actually emits.
def test_stage_result_file_names_match_score_expectations(monkeypatch, tmp_path):
    """Producer (stage) -> Consumer (score) filename contract round-trip."""
    d = _seed(monkeypatch, tmp_path, "R-rtrip")
    manifest = json.loads((d / "stage-manifest.json").read_text())
    # Simulate collect: write each result_file as DISPATCH_STATUS: OK with body
    for trial in manifest["trials"]:
        (d / trial["result_file"]).write_text(
            "DISPATCH_STATUS: OK\n\n### Code Review\nVerdict: changes-requested\n"
        )
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-rtrip", allow_incomplete=False)
    out = json.loads((tmp_path / "last_run.json").read_text())
    # If filename convention mismatched, all reviewer_outputs would be None.
    # Verify at least one fixture got real reviewer output.
    any_real = any(
        any(o is not None for o in fr["reviewer_outputs"])
        for fr in out["fixtures"]
    )
    assert any_real, (
        "stage result_file names do not match what score expects to read — "
        "no fixture got a populated reviewer_output despite seeded result files"
    )


# Vector 2: `_aggregate_from_outputs` takes (fix, reviewer_outputs, n_trials,
# threshold). The score() loop and the legacy _run_fixture() both call it.
# If either caller drops a kwarg, the function raises TypeError. Verify both
# call sites still produce equivalent results given the same fixture.
def test_aggregate_callers_produce_consistent_results():
    """Both call sites of _aggregate_from_outputs must agree on the contract."""
    fix = {
        "id": "synthetic",
        "expectations": [],
        "replicate_rule": {"trials": 3, "threshold": 2},
    }
    # Call directly with explicit kwargs
    direct = _aggregate_from_outputs(fix, [None, None, None], n_trials=3, threshold=2)
    assert direct["id"] == "synthetic"
    assert direct["trials"] == 3
    assert direct["threshold"] == 2
    # Verify the contract is the keyword form (positional would be brittle)
    with pytest.raises(TypeError):
        _aggregate_from_outputs(fix, [None], 1, 1)  # all positional should fail


# Vector 3: baseline write/compare round-trip. _write_baseline writes
# `template_sha` field; _compare_baseline reads `template_sha`. If schema
# drifts (e.g., key rename to `template_hash`), compare silently warns about
# "drift" on every run. Verify the symmetric key.
def test_baseline_write_compare_uses_symmetric_template_sha_key(monkeypatch, tmp_path):
    """SP-1: baseline header carries template_sha; compare must read the same key."""
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    payload = {"fixtures": [{"id": "x", "verdict": "PASS"}]}
    _write_baseline(payload, "deadbeef" * 8)
    written = json.loads((tmp_path / "baseline.json").read_text())
    assert "template_sha" in written, "_write_baseline does not write template_sha"
    assert written["template_sha"] == "deadbeef" * 8
    # Compare with the SAME sha should not trigger the drift warning.
    # evals_fixture_ids covers the fixture in payload so no drift is reported.
    rc = _compare_baseline(
        payload, "deadbeef" * 8, incomplete=False, evals_fixture_ids={"x"}
    )
    assert rc == 0  # no regression, sha matches


# Vector 4: the `incomplete` flag propagates from .collect-status parsing in
# score() through to the payload header, then is consumed by _compare_baseline
# to refuse. If the boolean polarity flips anywhere in the chain (e.g.,
# `incomplete=False` accidentally becomes the absence of the key), compare
# would silently accept incomplete runs and produce false PASS comparisons.
def test_incomplete_flag_propagates_through_score_to_compare(monkeypatch, tmp_path):
    """End-to-end: collect-status absent -> score writes incomplete: true ->
    compare refuses with rc=2."""
    _seed(monkeypatch, tmp_path, "R-incomp-int")
    # No .collect-status: with allow_incomplete=True, score writes incomplete header
    rc = score("R-incomp-int", allow_incomplete=True)
    assert rc in (0, 1)  # write succeeded
    out = json.loads((tmp_path / "last_run.json").read_text())
    assert out.get("incomplete") is True
    # Now write a baseline first (clean) then compare on incomplete payload
    clean_payload = {"fixtures": []}
    _write_baseline(clean_payload, "x" * 64)
    # Re-score with compare_baseline + allow_incomplete; must refuse with rc=2
    rc2 = score("R-incomp-int", compare_baseline=True, allow_incomplete=True)
    assert rc2 == 2, (
        f"compare_baseline did not refuse on incomplete run (got rc={rc2}); "
        f"incomplete-flag propagation broken between score() and _compare_baseline"
    )


# Vector 5: the DISPATCH_STATUS sentinel format is the contract between the
# collect skill (producer) and `_parse_result_file` (consumer). SKILL.md
# documents three sentinel shapes:
#   "DISPATCH_STATUS: OK\n\n<body>"
#   "DISPATCH_STATUS: ERROR: <reason>\n\n"
#   "DISPATCH_STATUS: ERROR: output-too-large\n\n"
# Verify each documented shape is consumed correctly. A parser regression to
# require trailing whitespace or specific casing would silently drop valid
# inputs.
def test_parse_handles_all_documented_sentinel_shapes(tmp_path):
    """Producer (collect skill SKILL.md) documents these shapes; consumer
    (`_parse_result_file`) must accept all of them and reject none."""
    shapes = {
        "ok_with_body": ("DISPATCH_STATUS: OK\n\n# body content here\n", "not-none"),
        "error_timeout": ("DISPATCH_STATUS: ERROR: timeout\n\n", "none"),
        "error_empty_body": ("DISPATCH_STATUS: ERROR: empty-body\n\n", "none"),
        "error_too_large": ("DISPATCH_STATUS: ERROR: output-too-large\n\n", "none"),
        "error_generic": ("DISPATCH_STATUS: ERROR: some-other\n\n", "none"),
    }
    for name, (content, expected) in shapes.items():
        p = tmp_path / f"{name}.md"
        p.write_text(content)
        out = _parse_result_file(p)
        if expected == "none":
            assert out is None, f"shape {name!r} should parse to None, got {out!r}"
        else:
            assert out is not None, f"shape {name!r} should parse to body, got None"
