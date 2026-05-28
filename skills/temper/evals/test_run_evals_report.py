"""Tests for #291 lens-health telemetry: _append_history + report subcommand.

Isolation style (per #291 plan Task 5): monkeypatch `_EVALS_DIR` to `tmp_path`
ONLY. The history path is resolved at call time via `_resolve_history_path()`
(see run_evals.py), so the single `_EVALS_DIR` monkeypatch keeps history writes
inside the sandbox — exactly as the post-Task-13.5 score tests rely on for the
canonical/per-iter output paths. There is intentionally NO dedicated history
constant to patch.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from skills.temper.evals import run_evals
from skills.temper.evals.run_evals import _append_history, report, score, stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grouped(real_rate=None, syn_rate=1.0, by_source=None):
    """Build a minimal grouped-summary dict shaped like _compute_grouped_summary.

    per_trial_rates carries the four wired lens columns; only `Surgical`'s
    real-pr rate is parameterized (others default to None) so tests can drive
    the sunset window off one lens.
    """
    if by_source is None:
        by_source = {
            "synthetic": [{"id": "1a", "verdict": "PASS"}],
            "real-pr": [{"id": "surgical-real", "verdict": "PASS"}],
        }
    per = {}
    for lens in ("Surgical", "DRY", "SRP", "OCP"):
        per[lens] = {
            "synthetic": syn_rate,
            "real-pr": real_rate if lens == "Surgical" else None,
        }
    return {"by_source": by_source, "per_trial_rates": per, "drift_delta": {}}


def _seed_qualifying(history_path, *, n, real_rate, run_id_prefix="R-q"):
    """Append n qualifying (source=all) runs at a fixed Surgical real-pr rate."""
    for i in range(n):
        g = _grouped(real_rate=real_rate)
        _append_history(
            f"{run_id_prefix}{i}", f"2026-05-2{i}T00:00:00+00:00", g, "all",
            path=history_path,
        )


def _seed_dispatch_dir(monkeypatch, tmp_path, run_id="R-hist"):
    """Mirror test_run_evals_score.py isolation, but monkeypatch _EVALS_DIR only
    (which now also routes the history path via call-time resolution)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    return stage(run_id)


# ---------------------------------------------------------------------------
# (a) _append_history appends one line per call + caps at _HISTORY_CAP
# contract:telemetry:history-append-one-per-run
# ---------------------------------------------------------------------------


def test_append_history_one_per_call_and_caps(tmp_path):
    """contract:telemetry:history-append-one-per-run

    Writing cap+5 records leaves exactly cap lines, and the newest run_id is
    retained (oldest evicted)."""
    hp = tmp_path / "history.jsonl"
    cap = run_evals._HISTORY_CAP
    for i in range(cap + 5):
        _append_history(
            f"R-{i}", f"2026-01-01T00:00:0{i % 10}+00:00", _grouped(real_rate=0.5),
            "all", path=hp,
        )
    lines = [l for l in hp.read_text().splitlines() if l.strip()]
    assert len(lines) == cap, f"expected cap={cap} lines, got {len(lines)}"
    last = json.loads(lines[-1])
    assert last["run_id"] == f"R-{cap + 5 - 1}"
    # Oldest (R-0) evicted.
    ids = {json.loads(l)["run_id"] for l in lines}
    assert "R-0" not in ids


def test_append_history_record_shape(tmp_path):
    """One call → one well-formed record with run_id/run_at/source/per_lens/by_source."""
    hp = tmp_path / "history.jsonl"
    g = _grouped(
        real_rate=0.4,
        by_source={
            "synthetic": [
                {"id": "a", "verdict": "PASS"},
                {"id": "b", "verdict": "N/A"},
            ],
            "real-pr": [{"id": "c", "verdict": "FAIL"}],
        },
    )
    _append_history("R-shape", "2026-05-28T12:00:00+00:00", g, "all", path=hp)
    rec = json.loads(hp.read_text().splitlines()[0])
    assert rec["run_id"] == "R-shape"
    assert rec["run_at"] == "2026-05-28T12:00:00+00:00"
    assert rec["source"] == "all"
    assert rec["per_lens"]["Surgical"]["real-pr"] == 0.4
    # by_source: pass = PASS count, total = len(entries) (N/A counts in total).
    assert rec["by_source"]["synthetic"] == {"pass": 1, "total": 2}
    assert rec["by_source"]["real-pr"] == {"pass": 0, "total": 1}


# ---------------------------------------------------------------------------
# (b) append tolerates absent file + malformed prior line
# ---------------------------------------------------------------------------


def test_append_history_tolerates_absent_and_malformed(tmp_path):
    hp = tmp_path / "history.jsonl"
    # Absent file (first run): must not raise.
    _append_history("R-1", "2026-05-28T00:00:00+00:00", _grouped(real_rate=0.5), "all", path=hp)
    # Inject a malformed line, then append again — malformed line skipped.
    hp.write_text(hp.read_text() + "{ this is not json\n")
    _append_history("R-2", "2026-05-28T01:00:00+00:00", _grouped(real_rate=0.5), "all", path=hp)
    good = []
    for l in hp.read_text().splitlines():
        if not l.strip():
            continue
        try:
            good.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    ids = {r["run_id"] for r in good}
    assert ids == {"R-1", "R-2"}


# ---------------------------------------------------------------------------
# (c) report on empty/absent history prints 'no history yet' + returns 0
# ---------------------------------------------------------------------------


def test_report_absent_history(tmp_path, capsys):
    rc = report(history_path=tmp_path / "nope.jsonl")
    assert rc == 0
    assert "no history yet" in capsys.readouterr().out


def test_report_empty_history(tmp_path, capsys):
    hp = tmp_path / "history.jsonl"
    hp.write_text("")
    rc = report(history_path=hp)
    assert rc == 0
    assert "no history yet" in capsys.readouterr().out


def test_report_only_synthetic_runs_no_qualifying(tmp_path, capsys):
    """Records with source=='synthetic' do not qualify → 'no history yet'."""
    hp = tmp_path / "history.jsonl"
    for i in range(3):
        _append_history(f"R-s{i}", f"2026-05-2{i}T00:00:00+00:00",
                        _grouped(real_rate=None), "synthetic", path=hp)
    rc = report(history_path=hp)
    assert rc == 0
    assert "no history yet" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# (d) report renders a per-lens trend after 3 seeded qualifying runs
# ---------------------------------------------------------------------------


def test_report_renders_trend(tmp_path, capsys):
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=3, real_rate=0.9)
    rc = report(history_path=hp)
    assert rc == 0
    out = capsys.readouterr().out
    for lens in ("Surgical", "DRY", "SRP", "OCP"):
        assert lens in out
    assert "mean" in out
    assert "SUNSET?" in out


# ---------------------------------------------------------------------------
# (e) sunset full-window-only
# contract:telemetry:sunset-full-window-only
# ---------------------------------------------------------------------------


def test_sunset_fires_full_window_below_threshold(tmp_path, capsys):
    """contract:telemetry:sunset-full-window-only

    5 qualifying runs all at Surgical real-pr 0.5 (< 0.70) → SUNSET fires for
    Surgical; lenses with no real-pr data show n/a (need 5 runs)."""
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=5, real_rate=0.5)
    rc = report(window=5, sunset_threshold=0.70, history_path=hp)
    assert rc == 0
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" in surgical_line
    # A lens with no real-pr data must show the need-N-runs guard, not SUNSET.
    dry_line = [l for l in out.splitlines() if l.startswith("DRY")][0]
    assert "need 5 runs" in dry_line
    assert "SUNSET" not in dry_line


def test_sunset_does_not_fire_with_four_qualifying_runs(tmp_path, capsys):
    """contract:telemetry:sunset-full-window-only — partial window → no SUNSET."""
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=4, real_rate=0.5)
    report(window=5, sunset_threshold=0.70, history_path=hp)
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" not in surgical_line
    assert "need 5 runs" in surgical_line


def test_sunset_does_not_fire_with_null_run_in_window(tmp_path, capsys):
    """A null Surgical rate inside the window breaks lens-present-in-all → no SUNSET."""
    hp = tmp_path / "history.jsonl"
    # 4 qualifying runs below threshold + 1 qualifying run with null Surgical.
    _seed_qualifying(hp, n=4, real_rate=0.5)
    _append_history("R-null", "2026-05-29T00:00:00+00:00",
                    _grouped(real_rate=None,
                             by_source={"synthetic": [{"id": "x", "verdict": "PASS"}],
                                        "real-pr": [{"id": "y", "verdict": "PASS"}]}),
                    "all", path=hp)
    report(window=5, sunset_threshold=0.70, history_path=hp)
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" not in surgical_line
    assert "need 5 runs" in surgical_line


def test_sunset_does_not_fire_when_one_rate_above_threshold(tmp_path, capsys):
    """All 5 present but one rate >= threshold → no SUNSET (every rate must be below)."""
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=4, real_rate=0.5)
    _append_history("R-high", "2026-05-29T00:00:00+00:00",
                    _grouped(real_rate=0.95), "all", path=hp)
    report(window=5, sunset_threshold=0.70, history_path=hp)
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" not in surgical_line


# ---------------------------------------------------------------------------
# (f) source accounting: synthetic records do not consume a window slot
# ---------------------------------------------------------------------------


def test_synthetic_records_do_not_consume_window_slot(tmp_path, capsys):
    """Interleave synthetic records among 5 qualifying runs; sunset still fires
    off the 5 qualifying runs (synthetic ones are skipped, not counted)."""
    hp = tmp_path / "history.jsonl"
    for i in range(5):
        # synthetic noise before each qualifying run
        _append_history(f"R-syn{i}", f"2026-05-1{i}T00:00:00+00:00",
                        _grouped(real_rate=None), "synthetic", path=hp)
        _append_history(f"R-all{i}", f"2026-05-2{i}T00:00:00+00:00",
                        _grouped(real_rate=0.5), "all", path=hp)
    rc = report(window=5, sunset_threshold=0.70, history_path=hp)
    assert rc == 0
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" in surgical_line, (
        "synthetic records must not consume a window slot — 5 qualifying runs "
        "remain and SUNSET should fire"
    )


def test_real_pr_records_count_as_qualifying_window_runs(tmp_path, capsys):
    """source=='real-pr' records carry per-lens real-PR rates and MUST qualify,
    participating in the trend/sunset window (mirrors the synthetic-exclusion
    test, but real-pr DOES count)."""
    hp = tmp_path / "history.jsonl"
    for i in range(5):
        _append_history(f"R-rpr{i}", f"2026-05-2{i}T00:00:00+00:00",
                        _grouped(real_rate=0.5), "real-pr", path=hp)
    rc = report(window=5, sunset_threshold=0.70, history_path=hp)
    assert rc == 0
    out = capsys.readouterr().out
    surgical_line = [l for l in out.splitlines() if l.startswith("Surgical")][0]
    assert "SUNSET" in surgical_line, (
        "real-pr records carry real-PR data and must qualify — 5 such runs "
        "below threshold should fire SUNSET"
    )


# ---------------------------------------------------------------------------
# (f2) non-positive window is clamped to 1 (no false SUNSET on unmeasured lens)
# ---------------------------------------------------------------------------


def test_window_zero_clamps_to_one_no_false_sunset(tmp_path, capsys):
    """window==0 must clamp to 1; without the clamp `qualifying[-0:]` selects the
    whole list and `len(present) >= 0` fires a spurious SUNSET on lenses with
    ZERO real-PR data. One qualifying run with a null DRY rate → DRY must NOT
    show SUNSET (it has no real-PR data)."""
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=1, real_rate=0.5)  # Surgical present, DRY/SRP/OCP null
    rc = report(window=0, sunset_threshold=0.70, history_path=hp)
    assert rc == 0
    captured = capsys.readouterr()
    out = captured.out
    # Unmeasured lens must not be falsely sunset.
    dry_line = [l for l in out.splitlines() if l.startswith("DRY")][0]
    assert "SUNSET" not in dry_line
    assert "need 1 runs" in dry_line  # clamped window is 1
    # Clamp warning emitted to stderr.
    assert "clamped to 1" in captured.err


def test_window_negative_clamps_to_one(tmp_path, capsys):
    """window<0 also clamps to 1 (left-trim slice would otherwise mis-window)."""
    hp = tmp_path / "history.jsonl"
    _seed_qualifying(hp, n=1, real_rate=0.5)
    rc = report(window=-1, sunset_threshold=0.70, history_path=hp)
    assert rc == 0
    captured = capsys.readouterr()
    dry_line = [l for l in captured.out.splitlines() if l.startswith("DRY")][0]
    assert "SUNSET" not in dry_line
    assert "clamped to 1" in captured.err


# ---------------------------------------------------------------------------
# (g) per-iter gating regression: score(per_iter=True) appends zero history
# ---------------------------------------------------------------------------


def test_per_iter_score_appends_zero_history(monkeypatch, tmp_path):
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "Rcal-1")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("Rcal-1", per_iter=True, allow_incomplete=False)
    assert rc in (0, 1)
    hp = tmp_path / "history.jsonl"
    assert not hp.exists(), "per-iter score must NOT append to history.jsonl"


def test_canonical_score_appends_one_history_line(monkeypatch, tmp_path):
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "Rcanon-1")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("Rcanon-1", source="all", allow_incomplete=False)
    assert rc in (0, 1)
    hp = tmp_path / "history.jsonl"
    assert hp.exists()
    lines = [l for l in hp.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "Rcanon-1"


# ---------------------------------------------------------------------------
# (h) test-isolation regression: score() under _EVALS_DIR-only monkeypatch
# does NOT create/modify the real skills/temper/evals/history.jsonl
# ---------------------------------------------------------------------------


def test_score_does_not_touch_real_history_log(monkeypatch, tmp_path):
    real_history = Path(run_evals.__file__).resolve().parent / "history.jsonl"
    existed_before = real_history.exists()
    mtime_before = real_history.stat().st_mtime if existed_before else None
    lines_before = (
        len(real_history.read_text().splitlines()) if existed_before else None
    )

    d = _seed_dispatch_dir(monkeypatch, tmp_path, "Riso-1")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("Riso-1", source="all", allow_incomplete=False)

    if not existed_before:
        assert not real_history.exists(), (
            "score() under _EVALS_DIR-only monkeypatch created the REAL "
            "history.jsonl — call-time resolution failed test isolation"
        )
    else:
        assert real_history.stat().st_mtime == mtime_before
        assert len(real_history.read_text().splitlines()) == lines_before


# ---------------------------------------------------------------------------
# (i) report/_append_history code paths never write evals.json / remove lenses
# ---------------------------------------------------------------------------


def test_report_codepath_does_not_mutate_registry():
    """report-never-mutates-registry: scope the grep to report() and
    _append_history() bodies, NOT the whole module (which references evals.json
    elsewhere, e.g. _EVALS_JSON loads)."""
    for fn in (run_evals.report, run_evals._append_history):
        src = inspect.getsource(fn)
        assert "evals.json" not in src, (
            f"{fn.__name__} must not reference evals.json (advisory/read-only)"
        )
        assert "_EVALS_JSON" not in src
        # No lens-removal / disabling verbs in these bodies.
        for verb in ("del ", ".remove(", ".pop(", "disable"):
            assert verb not in src, f"{fn.__name__} contains mutation verb {verb!r}"
