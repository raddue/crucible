"""Per-fixture temper lens eval runner (Task 6).

Dispatches the temper-reviewer prompt against each fixture in
`evals.json`, collects reviewer outputs across N replicate trials, and
evaluates the fixture's structured expectations via `lens_runner`.

Supports three execution modes:
  - live: subprocess `claude -p <prompt>` per trial (default)
  - mock: read canned outputs from `--mock-reviewer <dir>/<id>.txt`
  - replay: re-evaluate cached outputs from a prior `last_run.json`

Stdlib only; produces human-readable stdout + machine-readable
`last_run.json` for downstream tooling.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import lens_runner

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVALS_DIR = Path(__file__).resolve().parent
_EVALS_JSON = _EVALS_DIR / "evals.json"
_REVIEWER_PROMPT = _REPO_ROOT / "skills" / "temper" / "temper-reviewer.md"
_LAST_RUN = _EVALS_DIR / "last_run.json"

_FIXTURE_CONTENT_HEADER = (
    "## Fixture content (synthetic — review this in lieu of running git commands):\n\n"
)


# ---------------------------------------------------------------------------
# Prompt assembly + dispatch
# ---------------------------------------------------------------------------


def _synth_plan_reference(fixture: dict) -> str:
    """Synthesize a PR-body-equivalent scope statement from fixture metadata.
    Ensures the reviewer is NOT in degraded mode (per Design D8) for fixtures
    that test gating behavior — Surgical Changes at Important requires a
    stated scope to gate against."""
    desc = fixture.get("expected_output", "")
    allowed = fixture.get("allowed_files", [])
    allowed_str = ", ".join(f"`{p}`" for p in allowed)
    return (
        f"## What was requested\n\n{desc}\n\n"
        f"## Scope\n\nChanges should be confined to: {allowed_str}. "
        f"Drive-by edits to other files or unrelated changes within these files "
        f"are out of scope.\n"
    )


def _render_prompt(template: str, fixture: dict) -> str:
    """Substitute placeholders and append fixture content."""
    rendered = (
        template.replace("{DESCRIPTION}", f"Synthetic lens eval fixture: {fixture['id']}")
        .replace("{PLAN_REFERENCE}", _synth_plan_reference(fixture))
        .replace("{BASE_SHA}", "FIXTURE_BASE")
        .replace("{HEAD_SHA}", "FIXTURE_HEAD")
    )
    return rendered + "\n\n" + _FIXTURE_CONTENT_HEADER + fixture["prompt"]


def _dispatch_live(prompt: str, fixture_id: str, trial: int, timeout: int) -> str | None:
    """Live-dispatch via `claude -p`. Returns stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"  [dispatch] timeout on {fixture_id} trial {trial}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("  [dispatch] `claude` CLI not found on PATH", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(
            f"  [dispatch] non-zero exit {result.returncode} on {fixture_id} trial {trial}: "
            f"{result.stderr[:200]}",
            file=sys.stderr,
        )
        return None
    return result.stdout


# ---------------------------------------------------------------------------
# Per-fixture orchestration
# ---------------------------------------------------------------------------


def _resolve_output(
    fixture: dict,
    trial: int,
    *,
    template: str | None,
    mock_dir: Path | None,
    replay_outputs: list[str] | None,
    timeout: int,
) -> str | None:
    if replay_outputs is not None:
        if trial - 1 < len(replay_outputs):
            return replay_outputs[trial - 1]
        return None
    if mock_dir is not None:
        path = mock_dir / f"{fixture['id']}.txt"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  [mock] cannot read {path}: {e}", file=sys.stderr)
            return None
    assert template is not None
    prompt = _render_prompt(template, fixture)
    return _dispatch_live(prompt, fixture["id"], trial, timeout)


def _run_fixture(
    fixture: dict,
    *,
    template: str | None,
    mock_dir: Path | None,
    replay_outputs: list[str] | None,
    trials_override: int | None,
    timeout: int,
) -> dict:
    rule = fixture.get("replicate_rule", {"trials": 1, "threshold": 1})
    n_trials = trials_override if trials_override is not None else rule.get("trials", 1)
    threshold = rule.get("threshold", 1)
    if trials_override is not None and threshold > n_trials:
        threshold = n_trials  # clamp

    reviewer_outputs: list[str | None] = []
    for trial in range(1, n_trials + 1):
        out = _resolve_output(
            fixture,
            trial,
            template=template,
            mock_dir=mock_dir,
            replay_outputs=replay_outputs,
            timeout=timeout,
        )
        reviewer_outputs.append(out)

    expectation_results: list[dict] = []
    for expectation in fixture.get("expectations", []):
        per_trial_verdicts: list[str] = []
        per_trial_rationales: list[str] = []
        for out in reviewer_outputs:
            if out is None:
                per_trial_verdicts.append("N/A")
                per_trial_rationales.append("dispatch failure: no reviewer output")
                continue
            verdict, rationale = lens_runner.evaluate_expectation(expectation, out, fixture)
            per_trial_verdicts.append(verdict)
            per_trial_rationales.append(rationale)
        aggregated = lens_runner.aggregate_replicates(per_trial_verdicts, threshold)  # type: ignore[arg-type]
        passes = sum(1 for v in per_trial_verdicts if v == "PASS")
        rationale = f"{passes}/{n_trials} trials PASS (threshold {threshold})"
        expectation_results.append(
            {
                "expectation": expectation,
                "per_trial_verdicts": per_trial_verdicts,
                "per_trial_rationales": per_trial_rationales,
                "aggregated_verdict": aggregated,
                "aggregated_rationale": rationale,
            }
        )

    # Fixture verdict: FAIL if any expectation FAIL; else PASS if ≥1 PASS; else N/A.
    verdicts = [r["aggregated_verdict"] for r in expectation_results]
    if any(v == "FAIL" for v in verdicts):
        fixture_verdict = "FAIL"
    elif any(v == "PASS" for v in verdicts):
        fixture_verdict = "PASS"
    else:
        fixture_verdict = "N/A"

    return {
        "id": fixture["id"],
        "verdict": fixture_verdict,
        "trials": n_trials,
        "threshold": threshold,
        "expectations": expectation_results,
        "reviewer_outputs": reviewer_outputs,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _format_expectation_label(expectation: dict) -> str:
    check = expectation.get("check", "?")
    params = expectation.get("params") or expectation.get("args") or {}
    if not params:
        return check
    inside = ", ".join(f"{k}={v}" for k, v in params.items())
    return f"{check} {{{inside}}}"


def _render_summary(fixture_results: list[dict]) -> str:
    lines: list[str] = []
    for fr in fixture_results:
        lines.append(f"Fixture {fr['id']} [trials={fr['trials']}/{fr['threshold']}]")
        for er in fr["expectations"]:
            label = _format_expectation_label(er["expectation"])
            lines.append(
                f"  [{er['aggregated_verdict']}] {label} — {er['aggregated_rationale']}"
            )
        lines.append(f"  VERDICT: {fr['verdict']}")
        lines.append("")
    n_pass = sum(1 for f in fixture_results if f["verdict"] == "PASS")
    n_fail = sum(1 for f in fixture_results if f["verdict"] == "FAIL")
    n_na = sum(1 for f in fixture_results if f["verdict"] == "N/A")
    lines.append("===")
    lines.append(
        f"{n_pass}/{len(fixture_results)} fixtures PASS, {n_fail} FAIL, {n_na} N/A"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run temper lens evals.")
    p.add_argument("--fixture", help="run only one fixture by id")
    p.add_argument("--mock-reviewer", help="dir containing <fixture-id>.txt canned outputs")
    p.add_argument("--replay", help="path to last_run.json to re-evaluate")
    p.add_argument("--trials-override", type=int, help="override replicate_rule.trials")
    p.add_argument("--timeout", type=int, default=120, help="per-dispatch timeout in seconds")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Load fixtures
    try:
        evals_data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[fatal] cannot load evals.json: {e}", file=sys.stderr)
        return 2

    fixtures = evals_data.get("evals", [])
    if args.fixture:
        fixtures = [f for f in fixtures if f["id"] == args.fixture]
        if not fixtures:
            print(f"[fatal] no fixture with id {args.fixture!r}", file=sys.stderr)
            return 2

    # Resolve mode
    template: str | None = None
    mock_dir: Path | None = None
    replay_by_fixture: dict[str, list[str]] = {}

    if args.replay:
        try:
            replay_data = json.loads(Path(args.replay).read_text(encoding="utf-8"))
            for entry in replay_data.get("fixtures", []):
                replay_by_fixture[entry["id"]] = entry.get("reviewer_outputs", [])
        except (OSError, json.JSONDecodeError) as e:
            print(f"[fatal] cannot load replay file: {e}", file=sys.stderr)
            return 2
    elif args.mock_reviewer:
        mock_dir = Path(args.mock_reviewer)
        if not mock_dir.is_dir():
            print(f"[fatal] mock-reviewer dir not found: {mock_dir}", file=sys.stderr)
            return 2
    else:
        try:
            template = _REVIEWER_PROMPT.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[fatal] cannot read reviewer template: {e}", file=sys.stderr)
            return 2

    # Run each fixture
    fixture_results: list[dict] = []
    for fixture in fixtures:
        replay_outputs = replay_by_fixture.get(fixture["id"]) if args.replay else None
        result = _run_fixture(
            fixture,
            template=template,
            mock_dir=mock_dir,
            replay_outputs=replay_outputs,
            trials_override=args.trials_override,
            timeout=args.timeout,
        )
        fixture_results.append(result)

    # Stdout summary
    print(_render_summary(fixture_results))

    # Persist last_run.json
    payload: dict[str, Any] = {
        "run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "args": vars(args),
        "fixtures": fixture_results,
    }
    try:
        _LAST_RUN.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[warn] cannot write last_run.json: {e}", file=sys.stderr)

    # Exit code
    if any(fr["verdict"] == "FAIL" for fr in fixture_results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
