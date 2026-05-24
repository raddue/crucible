"""Inquisitor Edge Cases dimension (#297).

Hunts boundary-condition failures at the new public API surfaces.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.temper.evals import run_evals
from skills.temper.evals._dispatch_paths import fixture_sha, resolve_dispatch_dir
from skills.temper.evals._runid import sanitize_summary, validate_run_id
from skills.temper.evals.run_evals import _parse_result_file, score, stage


def _seed(monkeypatch, tmp_path, run_id="R-edge"):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    return stage(run_id)


# Vector 1: run-id at the exact length boundary (32 chars — the _RUN_ID_RE
# upper bound). Off-by-one in the regex would either reject valid IDs or
# accept oversized ones that overflow downstream filename buffers.
def test_run_id_exactly_32_chars_is_accepted():
    """32 = max length per _RUN_ID_RE `[A-Za-z0-9_-]{0,31}` after the leading char."""
    # 1 leading + 31 trailing = 32 total
    rid = "A" + ("a" * 31)
    assert len(rid) == 32
    validate_run_id(rid)  # must not raise


def test_run_id_33_chars_is_rejected():
    """33 chars must be rejected — proves the regex bound is inclusive."""
    rid = "A" + ("a" * 32)
    assert len(rid) == 33
    with pytest.raises(ValueError):
        validate_run_id(rid)


# Vector 2: dispatch-dir resolver with USER unset AND XDG_RUNTIME_DIR unset
# simultaneously. The implementation falls back to UID + /tmp, but if either
# fallback raises (e.g., os.getuid() fails inside a chroot), the entire stage
# pipeline crashes before any user-facing error.
def test_resolve_dispatch_dir_both_envs_unset(monkeypatch):
    """Container environment with neither XDG_RUNTIME_DIR nor USER set."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("USER", raising=False)
    p = resolve_dispatch_dir("R-x")
    # Must resolve to /tmp + <uid> + crucible-dispatch
    assert str(p).startswith("/tmp/"), f"unexpected fallback path: {p}"
    assert "crucible-dispatch-R-x" in str(p)


# Vector 3: sanitize_summary on extreme inputs: empty string, very long string,
# multiple sentinels in one summary, sentinel at the very start, sentinel at
# the very end. A regression that uses .replace() with maxreplace=1 would
# silently leave subsequent sentinels intact.
def test_sanitize_summary_replaces_all_occurrences():
    """Multiple literal sentinels must all be replaced — `.replace()` default
    is replace-all but a future maxreplace=1 regression would silently leak."""
    s = "DISPATCH_STATUS: OK then DISPATCH_STATUS: ERROR midway DISPATCH_STATUS: done"
    out = sanitize_summary(s)
    assert "DISPATCH_STATUS:" not in out, (
        f"sanitize_summary leaked sentinel(s): {out!r}"
    )
    assert out.count("[DISPATCH_STATUS_LITERAL]") == 3


def test_sanitize_summary_empty_string():
    """Empty input must not crash."""
    assert sanitize_summary("") == ""


# Vector 4: `_parse_result_file` on a result file that is entirely empty
# (zero bytes) — a plausible filesystem corruption / aborted write residue.
# Must not crash; must return None (treat as ERROR).
def test_parse_result_file_zero_byte_file(tmp_path):
    """Zero-byte result file (e.g. aborted atomic write left a truncated
    target) must return None, not crash."""
    p = tmp_path / "empty.md"
    p.write_text("")
    assert _parse_result_file(p) is None


def test_parse_result_file_only_sentinel_line_no_blank_no_body(tmp_path):
    """`DISPATCH_STATUS: OK` with NO trailing newline at all — common shell
    pipe artifact. Must not crash."""
    p = tmp_path / "no-trailing.md"
    p.write_text("DISPATCH_STATUS: OK")
    out = _parse_result_file(p)
    assert out is None  # no body present


# Vector 5: score() on an empty fixture set. `--fixture <nonexistent>` is
# already covered by stage()'s M-1 check, but what if evals.json itself is
# empty? The score loop must not divide-by-zero or crash on empty manifests.
def test_score_handles_empty_manifest(monkeypatch, tmp_path):
    """If stage somehow produces a manifest with zero trials, score must
    still write a valid empty last_run.json — not crash."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)

    # Hand-craft an empty dispatch dir + manifest
    d = resolve_dispatch_dir("R-empty")
    d.mkdir(parents=True)
    (d / "stage-manifest.json").write_text(json.dumps({
        "run_id": "R-empty",
        "stage_timestamp": "2026-01-01T00:00:00Z",
        "dispatch_timeout": 300,
        "reviewer_model": "opus",
        "template_sha": "a" * 64,
        "trials": [],
    }))
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-empty", allow_incomplete=False)
    assert rc == 0  # no fixtures → no failures
    out = json.loads((tmp_path / "last_run.json").read_text())
    assert out["fixtures"] == []
