#!/usr/bin/env python3
"""Delve eval harness — `stage` + `score` (#373).

Mirrors temper's/inquisitor's module layout: package-relative helper imports,
`if __name__ == "__main__": sys.exit(main())`. Invoked as a module from repo root
(relative imports require `-m`):

    python3 -m skills.delve.evals.run_evals stage <run-id> [--fixture ID]
    python3 -m skills.delve.evals.run_evals score <run-id> [--allow-incomplete]

This is the LEAN single-engine variant — NOT inquisitor's multi-arm A/B harness.
The oracle is the deterministic matcher (`_matcher.py`), not an LLM judge, so `score`
is fully deterministic and CI-gated; the live `/delve` run between stage and score is
manual (a human operator records the 8-field findings JSON per the README contract).

`stage` writes a `stage-manifest.json` enumerating one cell per fixture and a rendered
dispatch note. `score` reads the recorded findings per cell, runs the matcher against
each fixture's `ground-truth-bugs.json`, and writes `last_run.json` + `results.md`.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from ._dispatch_paths import resolve_dispatch_dir
from ._runid import validate_run_id
from ._matcher import match, parse_line

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVALS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _EVALS_DIR / "fixtures"

# The dispatch-health sentinel the operator prepends to each recorded result file
# (mirrors inquisitor's `DISPATCH_STATUS: OK\n\n<body>` handshake). An `OK` sentinel
# is consumed; an `ERROR` sentinel scores that cell as 0 findings (a recorded
# dispatch failure, not a clean "found nothing").
_STATUS_PREFIX = "DISPATCH_STATUS:"


def _fixture_dirs() -> list:
    """Every fixture dir under fixtures/ that carries a ground-truth-bugs.json."""
    if not _FIXTURES_DIR.exists():
        return []
    return sorted(d for d in _FIXTURES_DIR.iterdir()
                  if d.is_dir() and (d / "ground-truth-bugs.json").exists())


def _dispatch_note(fixture_id: str, scope: str, result_file: str) -> str:
    """The human-operator instruction rendered into the manifest for one cell."""
    return (
        f"# Delve eval — collect step for fixture {fixture_id!r}\n\n"
        f"1. Run `/delve {scope}` (the engine's normal invocation).\n"
        f"2. Save the engine's ranked 8-field findings JSON array to `{result_file}` "
        f"in this dispatch dir.\n"
        f"3. Prepend the line `{_STATUS_PREFIX} OK` then a blank line before the JSON "
        f"(use `{_STATUS_PREFIX} ERROR` if the dispatch failed — that cell scores 0).\n"
        f"4. When every cell is recorded, write an empty `.collect-status` file in "
        f"this dispatch dir.\n"
    )


def stage(run_id: str, *, fixture: str | None = None, force: bool = False) -> Path:
    """Render a stage-manifest.json enumerating one cell per fixture + the operator
    dispatch note. Returns the dispatch dir path."""
    validate_run_id(run_id)
    fixtures = _fixture_dirs()
    if fixture is not None:
        fixtures = [d for d in fixtures if d.name == fixture]
        if not fixtures:
            raise ValueError(f"--fixture {fixture!r} not found under {_FIXTURES_DIR}")
    if not fixtures:
        raise ValueError(f"no fixtures with ground-truth-bugs.json under {_FIXTURES_DIR}")

    dispatch_dir = resolve_dispatch_dir(run_id)
    if dispatch_dir.exists():
        if not force:
            raise FileExistsError(
                f"dispatch dir {dispatch_dir} already exists; pass force=True")
        import shutil
        shutil.rmtree(dispatch_dir)
    dispatch_dir.mkdir(parents=True)

    ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cells = []
    for d in fixtures:
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        scope = manifest.get("scope", str(d.relative_to(_REPO_ROOT)))
        result_file = f"{d.name}-findings.json"
        cells.append({
            "fixture_id": d.name,
            "scope": scope,
            "result_file": result_file,
            "dispatch_note": _dispatch_note(d.name, scope, result_file),
        })

    out = {
        "run_id": run_id,
        "stage_timestamp": ts,
        "engine": "delve",
        "fixtures": len(fixtures),
        "cells": cells,
    }
    (dispatch_dir / "stage-manifest.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    return dispatch_dir


def _parse_findings(path: Path) -> tuple:
    """Parse a recorded findings file → (findings_list, dispatch_failed).

    Strips an optional leading `DISPATCH_STATUS:` sentinel (inquisitor's pattern):
    an `OK` sentinel is consumed and the rest parses as a JSON findings array; an
    `ERROR` (or any non-OK) sentinel → ([], True) so the cell scores 0/empty. A file
    with no sentinel parses as a bare JSON array (backward-compatible, as the unit
    tests write). A missing file → ([], True)."""
    if not path.exists():
        return [], True
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith(_STATUS_PREFIX):
        first, _, rest = stripped.partition("\n")
        sentinel = first.strip()
        if sentinel.startswith(f"{_STATUS_PREFIX} ERROR"):
            return [], True
        if not sentinel.startswith(f"{_STATUS_PREFIX} OK"):
            return [], True  # malformed sentinel → dispatch failure
        text = rest
    text = text.strip()
    if not text:
        return [], True
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"recorded findings in {path} is not a JSON array")
    return data, False


def _reconcile_scope(findings: list, scope: str) -> list:
    """Anchor each recorded finding's `file` to fixture-root-relative form.

    Ground-truth `file`s are BARE fixture-relative names (`inventory.py`). The live
    `/delve <scope>` engine may emit a scope-relative or repo-relative path
    (`<scope>/inventory.py`) and the README contract says save it verbatim. Strip the
    fixture's known `scope` prefix (and a trailing slash) so a finding emitted as
    `<scope>/inventory.py` OR bare `inventory.py` both normalize to the GT form before
    the (deliberately generic) matcher's file gate runs. Generic — no hard-coded
    fixture names; `scope` comes from the manifest cell. Returns a new list (the
    recorded findings are not mutated)."""
    if not scope:
        return findings
    from ._matcher import normalize_file
    prefix = normalize_file(scope).rstrip("/") + "/"
    out = []
    for f in findings:
        nf = normalize_file(f.get("file", ""))
        if nf.startswith(prefix):
            f = {**f, "file": nf[len(prefix):]}
        out.append(f)
    return out


def score(run_id: str, *, allow_incomplete: bool = False) -> int:
    """Read stage-manifest.json + recorded findings; run the matcher per fixture;
    write last_run.json + results.md. Returns an exit code."""
    validate_run_id(run_id)
    dispatch_dir = resolve_dispatch_dir(run_id)
    manifest_path = dispatch_dir / "stage-manifest.json"
    if not manifest_path.exists():
        print(f"[fatal] no stage-manifest.json at {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not (dispatch_dir / ".collect-status").exists() and not allow_incomplete:
        print(f"[fatal] no .collect-status in {dispatch_dir}; collect is incomplete "
              f"(pass --allow-incomplete for a smoke/debug score)", file=sys.stderr)
        return 1
    complete = not allow_incomplete

    total_bugs = 0
    total_matched = 0
    total_findings = 0
    total_fp = 0
    off_total = 0
    off_matched = 0
    per_fixture = []
    for cell in manifest["cells"]:
        fixture_dir = _FIXTURES_DIR / cell["fixture_id"]
        gt = json.loads(
            (fixture_dir / "ground-truth-bugs.json").read_text(encoding="utf-8"))
        bugs = gt["bugs"]
        bug_ids = [b["bug_id"] for b in bugs]
        if len(bug_ids) != len(set(bug_ids)):
            dup = sorted({bid for bid in bug_ids if bug_ids.count(bid) > 1})
            raise ValueError(
                f"ground-truth-bugs.json for fixture {cell['fixture_id']!r} has "
                f"duplicate bug_id(s) {dup}; the matcher keys by bug_id so duplicates "
                f"collapse into one slot and silently corrupt recall")
        findings, dispatch_failed = _parse_findings(
            dispatch_dir / cell["result_file"])
        findings = _reconcile_scope(findings, cell.get("scope", ""))

        # Detect recorded findings whose `line` is unparseable. The matcher already
        # degrades them gracefully (no candidate edge → counted as kept-unmatched
        # false positives), so here we only WARN (naming the fixture + finding
        # indices) and report a per-cell `malformed_findings` count. Do not filter —
        # let `match` count them so they still land in findings/false_positives.
        malformed_idxs = []
        for i, f in enumerate(findings):
            try:
                parse_line(f.get("line"))
            except (ValueError, TypeError):
                malformed_idxs.append(i)
        if malformed_idxs:
            print(f"[warn] fixture {cell['fixture_id']!r}: {len(malformed_idxs)} "
                  f"recorded finding(s) with an unparseable `line` at index "
                  f"{malformed_idxs} — counted as unmatched false positive(s)",
                  file=sys.stderr)

        result = match(findings, bugs)

        matched_bug_ids = {b for (b, _f) in result.matched}
        off_ids = {b["bug_id"] for b in bugs if b.get("off_axis")}
        f_off_total = len(off_ids)
        f_off_matched = len(matched_bug_ids & off_ids)

        n_bugs = len(bugs)
        n_matched = len(result.matched)
        n_findings = len(findings)
        n_fp = len(result.unmatched_findings)

        total_bugs += n_bugs
        total_matched += n_matched
        total_findings += n_findings
        total_fp += n_fp
        off_total += f_off_total
        off_matched += f_off_matched

        per_fixture.append({
            "fixture_id": cell["fixture_id"],
            "bugs": n_bugs,
            "matched": n_matched,
            "recall": result.recall,
            "findings": n_findings,
            "false_positives": n_fp,
            "false_positive_rate": result.false_positive_rate,
            "unmatched_bugs": result.unmatched_bugs,
            "off_axis_recall": (f_off_matched / f_off_total) if f_off_total else None,
            "dispatch_failed": dispatch_failed,
            "malformed_findings": len(malformed_idxs),
        })

    last_run = {
        "run_id": run_id,
        "engine": "delve",
        "complete": complete,
        "fixtures": len(manifest["cells"]),
        "aggregate": {
            "bugs": total_bugs,
            "matched": total_matched,
            "recall": (total_matched / total_bugs) if total_bugs else 1.0,
            "findings": total_findings,
            "false_positives": total_fp,
            "false_positive_rate": (total_fp / total_findings) if total_findings else 0.0,
            "off_axis_recall": (off_matched / off_total) if off_total else None,
        },
        "per_fixture": per_fixture,
    }

    (_EVALS_DIR / "last_run.json").write_text(
        json.dumps(last_run, indent=2), encoding="utf-8")
    (_EVALS_DIR / "results.md").write_text(
        _render_results(last_run), encoding="utf-8")
    return 0


def _render_results(lr: dict) -> str:
    agg = lr["aggregate"]
    off = agg["off_axis_recall"]
    lines = [
        f"# Delve eval — run {lr['run_id']}",
        "",
        f"- engine: {lr['engine']} · fixtures: {lr['fixtures']} · "
        f"complete: {lr['complete']}",
        "",
        "## Aggregate",
        f"- recall: {agg['recall']:.3f} ({agg['matched']}/{agg['bugs']} planted bugs)",
        f"- false-positive rate: {agg['false_positive_rate']:.3f} "
        f"({agg['false_positives']}/{agg['findings']} findings)",
        f"- off-axis recall: {'n/a' if off is None else f'{off:.3f}'}",
        "",
        "## Per fixture",
    ]
    for pf in lr["per_fixture"]:
        off_pf = pf["off_axis_recall"]
        lines.append(
            f"- {pf['fixture_id']}: recall {pf['recall']:.3f} "
            f"({pf['matched']}/{pf['bugs']}) · FP {pf['false_positive_rate']:.3f} "
            f"({pf['false_positives']}/{pf['findings']}) · off-axis "
            f"{'n/a' if off_pf is None else f'{off_pf:.3f}'}"
            + (" · DISPATCH FAILED" if pf["dispatch_failed"] else ""))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run_evals", description="Delve eval harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("stage", help="render the dispatch manifest")
    ps.add_argument("run_id")
    ps.add_argument("--fixture", default=None, help="stage only this fixture dir name")
    ps.add_argument("--force", action="store_true",
                    help="overwrite an existing dispatch dir")

    pc = sub.add_parser("score", help="score recorded findings")
    pc.add_argument("run_id")
    pc.add_argument("--allow-incomplete", action="store_true",
                    help="score without .collect-status (stamps complete:false)")

    args = p.parse_args(argv)
    if args.cmd == "stage":
        dispatch_dir = stage(args.run_id, fixture=args.fixture, force=args.force)
        print(dispatch_dir)
        return 0
    if args.cmd == "score":
        return score(args.run_id, allow_incomplete=args.allow_incomplete)
    return 2  # pragma: no cover (argparse requires a subcommand)


if __name__ == "__main__":
    sys.exit(main())
