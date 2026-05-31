#!/usr/bin/env python3
"""Phase 3 backfill smoke test (Step 3.1).

Fixture-based: feeds SYNTHETIC PR dicts (the shape `gh pr list --json
mergedAt,number,title,files` returns) through the backfill script's pure core
so no real `gh`/network is touched. Asserts the synthetic backfill entries
carry the correct Phase-3 null-semantics and idempotency.

The script under test is `scripts/backfill-ledger.py`. Its hyphenated filename
is not importable as a module by name, so we load it via importlib from its
file path. The script inserts the repo root on sys.path so it can
`from scripts.ledger_append import append, caller_dedup`.

Run: python3 -m pytest eval/calibration-ledger/test-backfill-smoke.py -v
"""
import importlib.util
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "backfill-ledger.py")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_backfill_module():
    """Load scripts/backfill-ledger.py as a module from its file path."""
    spec = importlib.util.spec_from_file_location("backfill_ledger", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bf = _load_backfill_module()


# Fixed "now" so the lookback window is deterministic. Window default 90 days.
NOW_ISO = "2026-05-30T00:00:00Z"


def _synthetic_prs():
    """12 in-window PRs (gh `--json files` uses key `path`) + 1 stale PR.

    The stale PR (mergedAt ~200 days before NOW_ISO) must be filtered out by
    the lookback window, so build_entries() yields 12, not 13.
    """
    prs = []
    for i in range(12):
        n = 1000 + i
        prs.append(
            {
                "number": n,
                "mergedAt": f"2026-04-{(i % 27) + 1:02d}T12:00:00Z",
                "title": f"fix: synthetic regression #{n}",
                "files": [
                    {"path": f"src/module_{i}.py"},
                    {"path": f"tests/test_module_{i}.py"},
                ],
            }
        )
    # Stale PR: merged ~200 days before NOW_ISO -> outside 90-day window.
    prs.append(
        {
            "number": 42,
            "mergedAt": "2025-11-10T12:00:00Z",
            "title": "fix: ancient regression",
            "files": [{"path": "src/ancient.py"}],
        }
    )
    return prs


def _entries():
    return bf.build_entries(_synthetic_prs(), lookback_days=90, now_iso=NOW_ISO)


def test_at_least_ten_entries():
    entries = _entries()
    assert len(entries) >= 10, f"expected >=10 in-window entries, got {len(entries)}"


def test_stale_pr_excluded_by_lookback():
    entries = _entries()
    # The 13th (stale, #42) PR must be dropped; only the 12 in-window survive.
    assert len(entries) == 12
    assert all(e["run_id"] != "backfill-42-quality-gate" for e in entries)


def test_every_entry_backfill_semantics():
    entries = _entries()
    assert entries, "no entries produced"
    for e in entries:
        assert e["backfilled"] is True
        assert e["skill"] == "quality-gate"
        assert e["artifact_type"] == "code"
        assert e["severity_histogram"] is None
        assert e["comment"] == "inferred-from-fix"
        assert e["falsified"] is None


def test_run_id_shape():
    pat = re.compile(r"^backfill-\d+-quality-gate$")
    for e in _entries():
        assert pat.match(e["run_id"]), f"bad run_id: {e['run_id']!r}"


def test_gated_files_nonempty_from_payload():
    for e in _entries():
        gf = e["gated_files"]
        assert isinstance(gf, list) and len(gf) > 0
        assert all(isinstance(p, str) for p in gf)


def test_schema_v1_22_fields():
    expected = {
        "schema_version", "run_id", "skill", "tier", "artifact_type", "verdict",
        "confidence", "artifact_hash", "chunk_hash", "gated_files",
        "findings_count", "severity_histogram", "highest_finding",
        "would_have_shipped_without_gate", "rounds", "timestamp", "backfilled",
        "falsified", "falsified_by", "gated_files_truncated", "comment",
        "predicted_falsifier",
    }
    assert len(expected) == 22
    for e in _entries():
        assert set(e.keys()) == expected, f"field mismatch: {set(e.keys()) ^ expected}"


def test_timestamp_is_verbatim_mergedat():
    # The entry timestamp must be the PR's real historical mergedAt.
    by_id = {e["run_id"]: e for e in _entries()}
    assert by_id["backfill-1000-quality-gate"]["timestamp"] == "2026-04-01T12:00:00Z"


def test_filename_key_fallback():
    # gh sometimes returns `filename`; pr_to_entry must handle both.
    pr = {
        "number": 7,
        "mergedAt": "2026-04-15T00:00:00Z",
        "title": "fix: filename-shaped payload",
        "files": [{"filename": "src/legacy.py"}],
    }
    entry = bf.pr_to_entry(pr)
    assert entry["gated_files"] == ["src/legacy.py"]


def test_filter_ignored_drops_gitignored_paths():
    """filter_ignored drops currently-gitignored paths, keeps real artifacts.

    Legitimately uses THIS repo's gitignore via REPO_ROOT (smoke-level, not the
    pure core). `.claude/settings.local.json` and `.envrc` are ignored here;
    `skills/build/SKILL.md` is a tracked real artifact.
    """
    paths = [
        ".claude/settings.local.json",
        "skills/build/SKILL.md",
        ".envrc",
        "scripts/backfill-ledger.py",
    ]
    kept = bf.filter_ignored(paths, REPO_ROOT)
    assert ".claude/settings.local.json" not in kept
    assert ".envrc" not in kept
    assert "skills/build/SKILL.md" in kept
    assert "scripts/backfill-ledger.py" in kept


def test_pr_to_entry_stays_pure_without_filter():
    """pr_to_entry must NOT touch git when no path_filter is injected.

    Synthetic ambient paths are returned verbatim (identity default), proving
    the pure core is independent of repo gitignore state.
    """
    pr = {
        "number": 999,
        "mergedAt": "2026-04-20T00:00:00Z",
        "title": "fix: purity check",
        "files": [{"path": ".claude/settings.local.json"}, {"path": "src/real.py"}],
    }
    entry = bf.pr_to_entry(pr)
    assert entry["gated_files"] == [".claude/settings.local.json", "src/real.py"]


def test_pr_to_entry_empty_after_filter_keeps_entry():
    """If a path_filter empties gated_files, the entry survives with []."""
    pr = {
        "number": 888,
        "mergedAt": "2026-04-21T00:00:00Z",
        "title": "fix: all-ambient payload",
        "files": [{"path": ".claude/x"}, {"path": ".claude/y"}],
    }
    entry = bf.pr_to_entry(pr, path_filter=lambda ps: [])
    assert entry["gated_files"] == []
    assert entry["run_id"] == "backfill-888-quality-gate"


def test_naive_timestamp_pr_skipped_not_crashed():
    """A timezone-naive but parseable mergedAt is skipped, not a crash.

    Without the fix, `merged_dt < cutoff` raises TypeError (naive vs aware) and
    aborts the whole run. Mix one naive PR with one valid in-window PR; expect
    only the valid one to survive.
    """
    prs = [
        {
            "number": 501,
            "mergedAt": "2026-04-15T12:00:00",  # naive: no Z / offset
            "title": "fix: naive timestamp",
            "files": [{"path": "src/naive.py"}],
        },
        {
            "number": 502,
            "mergedAt": "2026-04-16T12:00:00Z",  # valid, in-window
            "title": "fix: aware timestamp",
            "files": [{"path": "src/aware.py"}],
        },
    ]
    entries = bf.build_entries(prs, lookback_days=90, now_iso=NOW_ISO)
    ids = {e["run_id"] for e in entries}
    assert ids == {"backfill-502-quality-gate"}


def test_pr_missing_number_skipped_not_crashed():
    """A PR dict lacking `number` is skipped, not a KeyError abort."""
    prs = [
        {
            "mergedAt": "2026-04-15T12:00:00Z",  # no `number` key
            "title": "fix: missing number",
            "files": [{"path": "src/x.py"}],
        },
        {
            "number": 503,
            "mergedAt": "2026-04-16T12:00:00Z",
            "title": "fix: has number",
            "files": [{"path": "src/y.py"}],
        },
    ]
    entries = bf.build_entries(prs, lookback_days=90, now_iso=NOW_ISO)
    ids = {e["run_id"] for e in entries}
    assert ids == {"backfill-503-quality-gate"}


def test_in_batch_dedup_same_number():
    """fix∪hotfix overlap: two PR dicts with the SAME number yield ONE entry."""
    prs = [
        {
            "number": 600,
            "mergedAt": "2026-04-15T12:00:00Z",
            "title": "fix: from fix/ query",
            "files": [{"path": "src/a.py"}],
        },
        {
            "number": 600,
            "mergedAt": "2026-04-15T12:00:00Z",
            "title": "fix: same PR from hotfix/ query",
            "files": [{"path": "src/a.py"}],
        },
    ]
    entries = bf.build_entries(prs, lookback_days=90, now_iso=NOW_ISO)
    assert len(entries) == 1
    assert entries[0]["run_id"] == "backfill-600-quality-gate"


def test_idempotent_append(tmp_path, monkeypatch):
    """Appending the same entries twice must not duplicate lines (L-2)."""
    from scripts.ledger_append import append, caller_dedup

    # Ensure kill-switch is OFF for this isolated tmp ledger.
    monkeypatch.delenv("CRUCIBLE_CALIBRATION_DISABLED", raising=False)

    ledger = str(tmp_path / "runs.jsonl")
    overflow = str(tmp_path / "overflow")
    entries = _entries()

    def emit_all():
        for e in entries:
            if caller_dedup(ledger, e["run_id"], e["skill"]):
                continue
            append(ledger, e, overflow_dir=overflow)

    emit_all()
    with open(ledger) as f:
        first_count = sum(1 for line in f if line.strip())
    emit_all()  # re-run: dedup must skip all
    with open(ledger) as f:
        second_count = sum(1 for line in f if line.strip())

    assert first_count == len(entries)
    assert second_count == first_count, "re-run duplicated ledger lines"


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
