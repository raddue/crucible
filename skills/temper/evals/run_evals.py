"""Per-fixture temper lens eval runner (Task 6).

Dispatches the temper-reviewer prompt against each fixture in
`evals.json`, collects reviewer outputs across N replicate trials, and
evaluates the fixture's structured expectations via `lens_runner`.

Supports two execution modes (live dispatch removed in #297 —
use `stage` + `/temper-eval-collect` + `score` subcommands instead):
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
import shutil
import sys
from pathlib import Path
from typing import Any

from . import lens_runner
from ._dispatch_paths import fixture_sha, resolve_dispatch_dir, template_sha
from ._runid import validate_run_id

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVALS_DIR = Path(__file__).resolve().parent
_EVALS_JSON = _EVALS_DIR / "evals.json"
_REVIEWER_PROMPT = _REPO_ROOT / "skills" / "temper" / "temper-reviewer.md"
_LAST_RUN = (
    Path(os.environ["TEMPER_LAST_RUN_OVERRIDE"])
    if os.environ.get("TEMPER_LAST_RUN_OVERRIDE")
    else _EVALS_DIR / "last_run.json"
)
# SP-R7-C: declared in Task 6 (not Task 8) so test_run_evals_score.py's
# `_seed_dispatch_dir` helper can `monkeypatch.setattr(run_evals, "_BASELINE_PATH", ...)`
# without raising AttributeError. The `_write_baseline` / `_compare_baseline` helper
# functions that USE this constant are still added in Task 8 (stubs added below in Task 6).
_BASELINE_PATH = _EVALS_DIR / "baseline.json"

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
    """Substitute placeholders, validate (template portion only), then append
    fixture content.

    I-T9 (M-4): validation applies to the substituted template — NOT the
    appended fixture body. Fixture diffs legitimately contain `{` (f-strings,
    dict literals); validating after concat would false-positive.
    """
    rendered = (
        template.replace("{DESCRIPTION}", f"Synthetic lens eval fixture: {fixture['id']}")
        .replace("{PLAN_REFERENCE}", _synth_plan_reference(fixture))
        .replace("{BASE_SHA}", "FIXTURE_BASE")
        .replace("{HEAD_SHA}", "FIXTURE_HEAD")
    )
    _validate_rendered_prompt(rendered)  # I-T9: validate BEFORE appending fixture body
    return rendered + "\n\n" + _FIXTURE_CONTENT_HEADER + fixture["prompt"]


# ---------------------------------------------------------------------------
# stage(): render dispatch files + manifest (Task 3 of #297)
# ---------------------------------------------------------------------------


_DISPATCH_HEADER_TEMPLATE = """\
# Dispatch: temper-reviewer
**Pipeline:** temper-eval | **Phase:** collect | **Task:** {seq}
**Timestamp:** {ts}
**Dispatch-Dir:** {dispatch_dir}

---

"""


def _validate_rendered_prompt(rendered: str) -> None:
    """I-T9 (M-4): length-floor + placeholder-residual check.

    Template-evolution-tolerant. Catches catastrophically-empty renders
    and unsubstituted placeholders without binding to specific placeholder names.
    """
    if len(rendered) <= 200:
        raise ValueError(
            f"rendered prompt has length {len(rendered)} ≤ 200 bytes "
            f"(I-T9 length-floor): suspect catastrophic-empty render"
        )
    if "{" in rendered:
        idx = rendered.index("{")
        context = rendered[max(0, idx - 20):idx + 40]
        raise ValueError(
            f"rendered prompt contains unsubstituted `{{` placeholder marker "
            f"at offset {idx} (I-T9 placeholder-residual): {context!r}"
        )


def stage(
    run_id: str,
    *,
    force: bool = False,
    source: str = "all",
    fixture: str | None = None,
    trials_override: int | None = None,
    timeout: int = 300,
) -> Path:
    """Render fixtures × trials to dispatch files; write stage-manifest.json.

    Returns: dispatch directory path.
    Raises:
        ValueError: invalid run_id (I-9) or source+fixture intersection (M-1)
        FileExistsError: dispatch dir exists and force=False
    """
    validate_run_id(run_id)

    # Load fixtures
    evals_data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    fixtures = evals_data.get("evals", [])

    # --source filter
    if source != "all":
        fixtures = [f for f in fixtures if f.get("source", "synthetic") == source]

    # --fixture filter + M-1 intersection check
    if fixture is not None:
        matching = [f for f in fixtures if f["id"] == fixture]
        if not matching:
            raise ValueError(
                f"--fixture {fixture!r} not found in --source {source!r} "
                f"(M-1: intersection produces zero trials)"
            )
        fixtures = matching

    # Resolve + prepare dispatch dir
    dispatch_dir = resolve_dispatch_dir(run_id)
    if dispatch_dir.exists():
        if not force:
            raise FileExistsError(
                f"dispatch dir {dispatch_dir} already exists; pass force=True to overwrite"
            )
        shutil.rmtree(dispatch_dir)
    dispatch_dir.mkdir(parents=True)

    # Read template once
    template = _REVIEWER_PROMPT.read_text(encoding="utf-8")
    tpl_sha = template_sha(_REVIEWER_PROMPT)
    ts = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # Render trials
    trials: list[dict] = []
    seq = 0
    for fix in fixtures:
        rule = fix.get("replicate_rule", {"trials": 1, "threshold": 1})
        n_trials = trials_override if trials_override is not None else rule.get("trials", 1)
        for trial_idx in range(1, n_trials + 1):
            seq += 1
            dispatch_file = f"{seq:03d}-reviewer.md"
            result_file = f"{seq:03d}-result.md"
            body = _render_prompt(template, fix)
            header = _DISPATCH_HEADER_TEMPLATE.format(
                seq=seq, ts=ts, dispatch_dir=dispatch_dir
            )
            rendered = header + body
            # I-T9 validation runs inside _render_prompt on the template-only portion
            (dispatch_dir / dispatch_file).write_text(rendered, encoding="utf-8")
            trials.append({
                "seq": seq,
                "fixture_id": fix["id"],
                "trial": trial_idx,
                "dispatch_file": dispatch_file,
                "result_file": result_file,
                "fixture_sha": fixture_sha(fix),
            })

    # Write stage-manifest.json
    # stage(): non-atomic writes accepted — see plan M-FE-1 R3
    manifest = {
        "run_id": run_id,
        "stage_timestamp": ts,
        "dispatch_timeout": timeout,
        "reviewer_model": "opus",
        "template_sha": tpl_sha,
        "trials": trials,
    }
    (dispatch_dir / "stage-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # Initial manifest.jsonl entries (stage-side).
    # S-R4-3: `manifest.jsonl` is informational/audit only — score does NOT consume it.
    # S-4 R5: `"w"` mode is safe ONLY because rmtree+mkdir above guarantees an
    # empty dispatch dir at this point. Do NOT relocate this open() call above
    # the rmtree without re-evaluating the truncation hazard.
    # stage(): non-atomic writes accepted — see plan M-FE-1 R3
    with (dispatch_dir / "manifest.jsonl").open("w", encoding="utf-8") as f:
        for t in trials:
            f.write(json.dumps({
                "seq": t["seq"], "file": t["dispatch_file"],
                "role": "temper-reviewer", "phase": "stage", "task": None,
                "status": "dispatched", "duration_s": None, "summary": None,
            }) + "\n")

    return dispatch_dir


# ---------------------------------------------------------------------------
# Per-fixture orchestration
# ---------------------------------------------------------------------------


def _resolve_output(
    fixture: dict,
    trial: int,
    *,
    template: str | None,  # noqa: ARG001 — kept for legacy callers post-#297
    mock_dir: Path | None,
    replay_outputs: list[str] | None,
    timeout: int,  # noqa: ARG001 — kept for legacy callers post-#297
) -> str | None:
    """Resolve a per-trial reviewer output from mock-dir or replay cache.

    Post-#297: subprocess-based live dispatch is removed. Live runs now go
    through the `stage` subcommand + `/temper-eval-collect` skill + `score`
    subcommand. When neither `replay_outputs` nor `mock_dir` applies this
    returns `None`; legacy callers should error out before calling.

    `template` and `timeout` are kept in the signature as vestigial kwargs
    so legacy `_run_fixture` callers don't need a parallel-edit; they are
    intentionally ignored.
    """
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
    return None


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

    return _aggregate_from_outputs(
        fixture, reviewer_outputs, n_trials=n_trials, threshold=threshold
    )


def _aggregate_from_outputs(
    fix: dict,
    reviewer_outputs: list[str | None],
    *,
    # S2 R8/R9: closure deps identified in Step 0 (/tmp/_aggregate_closure_deps.txt).
    # Explicit kwargs eliminate the implicit-lexical-capture footgun that would
    # surface as NameError at first call rather than a clean assertion failure.
    n_trials: int,
    threshold: int,
) -> dict:
    """Behavioral equivalent of _run_fixture's post-resolution aggregation.

    Takes already-resolved per-trial reviewer outputs (None for missing/ERROR).
    Returns the per-fixture result dict.
    """
    expectation_results: list[dict] = []
    for expectation in fix.get("expectations", []):
        per_trial_verdicts: list[str] = []
        per_trial_rationales: list[str] = []
        for out in reviewer_outputs:
            if out is None:
                per_trial_verdicts.append("N/A")
                per_trial_rationales.append("dispatch failure: no reviewer output")
                continue
            verdict, rationale = lens_runner.evaluate_expectation(expectation, out, fix)
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

    verdicts = [r["aggregated_verdict"] for r in expectation_results]
    if any(v == "FAIL" for v in verdicts):
        fixture_verdict = "FAIL"
    elif any(v == "PASS" for v in verdicts):
        fixture_verdict = "PASS"
    else:
        fixture_verdict = "N/A"

    return {
        "id": fix["id"],
        "verdict": fixture_verdict,
        "trials": n_trials,
        "threshold": threshold,
        "expectations": expectation_results,
        "reviewer_outputs": reviewer_outputs,
    }


# ---------------------------------------------------------------------------
# score() — Task 6 of #297
# ---------------------------------------------------------------------------


def _parse_result_file(path: Path) -> str | None:
    """Parse <NNN>-result.md. Returns reviewer markdown body or None on ERROR.

    Task 7 (S-1, I-T6): structural first-line prefix match. The body may
    contain literal `DISPATCH_STATUS:` substrings without collision because
    only line 0 is inspected for the sentinel.

    Layout assumed:
        DISPATCH_STATUS: <STATE>[: detail]
        <blank line>
        <reviewer markdown body...>

    Return value:
      - None when the sentinel is ERROR (or malformed / missing).
      - None when the sentinel is OK but the body is empty / whitespace-only
        (collect skill SHOULD have promoted this to ERROR upstream — defense
        in depth).
      - The body string when the sentinel is OK and the body is non-empty.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.split("\n", 2)  # split at most twice: first, blank, rest
    if not lines:
        return None
    first = lines[0]
    if first.startswith("DISPATCH_STATUS: ERROR"):
        return None
    if not first.startswith("DISPATCH_STATUS: OK"):
        # Malformed sentinel — treat as None (no claim about content)
        return None
    # Body starts after the blank line (lines[2] if present).
    # S1: empty body is treated as None (not empty string) — collect skill
    # should have promoted empty-body to DISPATCH_STATUS: ERROR: empty-body
    # before this point.
    if len(lines) < 3:
        return None
    body = lines[2]
    if body.strip() == "":
        return None
    return body


# Task 8: real impls. SP-1 baseline header carries template_sha so
# --compare-baseline can detect dispatch-template drift since baseline.
def _write_baseline(payload: dict, current_template_sha: str) -> None:
    """SP-1: baseline header carries template_sha."""
    baseline = dict(payload)
    baseline["template_sha"] = current_template_sha
    _BASELINE_PATH.write_text(json.dumps(baseline, indent=2), encoding="utf-8")


def _compare_baseline(payload: dict, current_template_sha: str, *, incomplete: bool) -> int:
    """Return 1 on regression, 2 if refused (incomplete / missing baseline), 0 if clean.

    M3 R6 caveat — fixture-set drift: this function compares verdicts by fixture id.
    If a fixture is DELETED from evals.json post-baseline, that fixture appears in
    `base_verdicts` but is absent from `current_verdicts.get(fid)` → resolves to
    `None`, which does not match the `("FAIL", "N/A")` regression set, so the
    deletion is currently SILENT. Conversely, fixtures ADDED post-baseline are
    not compared at all (no baseline entry). Operators changing the fixture set
    must re-baseline explicitly (`--write-baseline`) — otherwise comparisons
    drift apples-to-oranges without warning. Future work: emit an explicit
    `[warn] fixture-set drift` line when `set(base_verdicts) != set(current_verdicts)`.
    """
    if incomplete:
        print(
            "[fatal] --compare-baseline refuses to compare an incomplete run "
            "(last_run.json header has incomplete: true). Exit 2.",
            file=sys.stderr,
        )
        return 2
    if not _BASELINE_PATH.exists():
        print(f"[fatal] no baseline at {_BASELINE_PATH}", file=sys.stderr)
        return 2
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("template_sha") != current_template_sha:
        print(
            f"[warn] template_sha drift since baseline (baseline: "
            f"{baseline.get('template_sha', '?')[:12]}…, current: "
            f"{current_template_sha[:12]}…); verdict comparison may be apples-to-oranges",
            file=sys.stderr,
        )
    # Per-fixture verdict comparison
    current_verdicts = {f["id"]: f["verdict"] for f in payload["fixtures"]}
    base_verdicts = {f["id"]: f["verdict"] for f in baseline.get("fixtures", [])}
    regressions = []
    for fid, base_v in base_verdicts.items():
        cur_v = current_verdicts.get(fid)
        if base_v == "PASS" and cur_v in ("FAIL", "N/A"):
            regressions.append((fid, base_v, cur_v))
    if regressions:
        for fid, b, c in regressions:
            print(f"[regression] {fid}: baseline {b} → current {c}", file=sys.stderr)
        return 1
    return 0


def score(
    run_id: str,
    *,
    write_baseline: bool = False,
    compare_baseline: bool = False,
    force_rescore: bool = False,
    allow_incomplete: bool = False,
    per_iter: bool = False,
) -> int:
    """Read stage-manifest.json + result files; aggregate; write last_run.json.

    Returns: 0=PASS, 1=any FAIL, 2=fatal
    """
    validate_run_id(run_id)
    dispatch_dir = resolve_dispatch_dir(run_id)
    manifest_path = dispatch_dir / "stage-manifest.json"
    if not manifest_path.exists():
        print(f"[fatal] no stage-manifest.json at {manifest_path}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # I-8 + I-11 precedence (S-2)
    status_path = dispatch_dir / ".collect-status"
    incomplete = False
    incomplete_cause: str | None = None
    # 2P-2 R5: use `return 2` consistently (NOT sys.exit).
    if not status_path.exists():
        if not allow_incomplete:
            print(
                "[fatal] dispatch run incomplete: `.collect-status` absent. "
                "Pass --allow-incomplete to override.",
                file=sys.stderr,
            )
            return 2
        incomplete = True  # cause undetermined per S-2
    else:
        first = status_path.read_text(encoding="utf-8").splitlines()
        if not first or first[0].strip() != "complete":
            if not allow_incomplete:
                print("[fatal] .collect-status does not contain 'complete'", file=sys.stderr)
                return 2
            incomplete = True
        # Parse "errors: N/total" line if present (I-11)
        if len(first) >= 2 and first[1].startswith("errors:"):
            n_str, total_str = first[1].removeprefix("errors:").strip().split("/")
            n_err, total = int(n_str), int(total_str)
            if total > 0 and n_err == total:
                if not allow_incomplete:
                    print(
                        f"[fatal] all {total} dispatches errored (incomplete-cause: all-error). "
                        f"Pass --allow-incomplete to score anyway.",
                        file=sys.stderr,
                    )
                    return 2
                incomplete = True
                incomplete_cause = "all-error"
            # M-FE-2 R3: ceil-half threshold so exactly half also triggers.
            elif total > 0 and 2 * n_err >= total:
                print(
                    f"[warn] {n_err}/{total} dispatches errored (>= half)",
                    file=sys.stderr,
                )

    # Recompute per-trial fixture_sha; refuse mismatches unless --force-rescore
    evals_data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    fixtures_by_id = {f["id"]: f for f in evals_data.get("evals", [])}

    # Template_sha drift advisory (S-1)
    current_template_sha = template_sha(_REVIEWER_PROMPT)
    if current_template_sha != manifest.get("template_sha"):
        if not force_rescore:
            print(
                f"[warn] template_sha drift detected (manifest: {manifest['template_sha'][:12]}…, "
                f"current: {current_template_sha[:12]}…). ADVISORY ONLY — current run's prompts are "
                f"frozen at stage-time and unaffected. Pass --force-rescore to suppress.",
                file=sys.stderr,
            )

    # Reassemble per-fixture trials
    by_fixture: dict[str, list[tuple[int, dict, str | None]]] = {}
    for entry in manifest["trials"]:
        seq = entry["seq"]
        fid = entry["fixture_id"]
        fix = fixtures_by_id.get(fid)
        if fix is None:
            print(f"[fatal] unknown fixture id {fid!r} in manifest", file=sys.stderr)
            return 2

        # Per-trial fixture_sha refusal (I-3)
        current_fsha = fixture_sha(fix)
        if current_fsha != entry["fixture_sha"] and not force_rescore:
            print(
                f"[warn] fixture {fid!r} sha mismatch on seq {seq}: REFUSED. "
                f"Pass --force-rescore to override.",
                file=sys.stderr,
            )
            by_fixture.setdefault(fid, []).append((entry["trial"], entry, None))
            continue

        result_path = dispatch_dir / entry["result_file"]
        out = _parse_result_file(result_path) if result_path.exists() else None
        by_fixture.setdefault(fid, []).append((entry["trial"], entry, out))

    # Run lens_runner per fixture
    fixture_results: list[dict] = []
    for fid, trials_list in by_fixture.items():
        fix = fixtures_by_id[fid]
        trials_list.sort(key=lambda t: t[0])
        reviewer_outputs = [out for _, _, out in trials_list]
        rule = fix.get("replicate_rule", {"trials": 1, "threshold": 1})
        n_trials = rule.get("trials", 1)
        threshold = rule.get("threshold", 1)
        result = _aggregate_from_outputs(
            fix, reviewer_outputs, n_trials=n_trials, threshold=threshold
        )
        fixture_results.append(result)

    # Write last_run.json
    payload: dict[str, Any] = {
        "run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "run_id": run_id,
        "fixtures": fixture_results,
    }
    if incomplete:
        payload["incomplete"] = True
        if incomplete_cause:
            payload["incomplete-cause"] = incomplete_cause
    if force_rescore:
        payload["force_rescore"] = True

    # F1 / S-FE-5 R3: per-iter outputs under .calibrate-state/ (blanket-gitignored)
    if per_iter:
        per_iter_dir = _EVALS_DIR / ".calibrate-state"
        per_iter_dir.mkdir(parents=True, exist_ok=True)
        out_path = per_iter_dir / f"last_run-{run_id}.json"
        print(
            f"[info] writing per-iter output to {out_path} (gitignored via .calibrate-state/)",
            file=sys.stderr,
        )
    else:
        out_path = _LAST_RUN
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --write-baseline + --compare-baseline — see Task 8 (stubs raise NotImplementedError)
    if write_baseline:
        _write_baseline(payload, current_template_sha)
    if compare_baseline:
        return _compare_baseline(payload, current_template_sha, incomplete=incomplete)

    if any(fr["verdict"] == "FAIL" for fr in fixture_results):
        return 1
    return 0


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
    sub = p.add_subparsers(dest="cmd")

    # stage
    sp_stage = sub.add_parser("stage", help="Render fixtures × trials to dispatch files")
    sp_stage.add_argument("run_id")
    sp_stage.add_argument("--force", action="store_true")
    sp_stage.add_argument("--source", choices=["synthetic", "real-pr", "all"], default="all")
    sp_stage.add_argument("--fixture", default=None)
    sp_stage.add_argument("--trials-override", type=int, default=None)
    sp_stage.add_argument("--timeout", type=int, default=300)

    # score — Task 6
    sp_score = sub.add_parser("score", help="Aggregate results + write last_run.json")
    sp_score.add_argument("run_id")
    sp_score.add_argument("--write-baseline", action="store_true")
    sp_score.add_argument("--compare-baseline", action="store_true")
    sp_score.add_argument("--force-rescore", action="store_true")
    sp_score.add_argument("--allow-incomplete", action="store_true")
    sp_score.add_argument("--per-iter", action="store_true",
        help="Write last_run-<run_id>.json under .calibrate-state/ instead of shared last_run.json. Set by /temper-eval-calibrate.")

    # Legacy mock/replay paths (back-compat, no subcommand)
    # S3: All legacy flags use --legacy-* prefix to eliminate collision with subcommand flags.
    p.add_argument("--legacy-fixture", dest="legacy_fixture", help="(legacy) run one fixture by id (with mock/replay)")
    p.add_argument("--mock-reviewer", help="dir containing <fixture-id>.txt canned outputs")
    p.add_argument("--replay", help="path to last_run.json to re-evaluate")
    # S-3 R5: dest matches the flag's full name (`legacy_trials_override`) to
    # eliminate the prior `legacy_trials` vs `args.trials_override` naming confusion.
    p.add_argument("--legacy-trials-override", dest="legacy_trials_override", type=int, help="(legacy)")
    p.add_argument("--legacy-timeout", dest="legacy_timeout", type=int, default=120, help="(legacy)")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.cmd == "stage":
        try:
            stage(
                args.run_id,
                force=args.force,
                source=args.source,
                fixture=args.fixture,
                trials_override=args.trials_override,
                timeout=args.timeout,
            )
            return 0
        except (FileExistsError, ValueError) as e:
            print(f"[fatal] {e}", file=sys.stderr)
            return 2

    if args.cmd == "score":
        try:
            return score(
                args.run_id,
                write_baseline=args.write_baseline,
                compare_baseline=args.compare_baseline,
                force_rescore=args.force_rescore,
                allow_incomplete=args.allow_incomplete,
                per_iter=args.per_iter,
            )
        except ValueError as e:
            print(f"[fatal] {e}", file=sys.stderr)
            return 2

    # Legacy mock/replay path — preserved unchanged
    return _legacy_main(args)


def _legacy_main(args: argparse.Namespace) -> int:
    # Load fixtures
    try:
        evals_data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[fatal] cannot load evals.json: {e}", file=sys.stderr)
        return 2

    fixtures = evals_data.get("evals", [])
    if args.legacy_fixture:
        fixtures = [f for f in fixtures if f["id"] == args.legacy_fixture]
        if not fixtures:
            print(f"[fatal] no fixture with id {args.legacy_fixture!r}", file=sys.stderr)
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
        # Post-#297: subprocess-based live dispatch is removed. The legacy
        # entry point only supports `--mock-reviewer` or `--replay`. Live
        # runs go through `stage` + `/temper-eval-collect` + `score`.
        print(
            "[fatal] legacy entry point requires --mock-reviewer or --replay; "
            "live dispatch was removed in #297 — use the `stage` subcommand "
            "+ /temper-eval-collect + `score` for live runs.",
            file=sys.stderr,
        )
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
            trials_override=args.legacy_trials_override,
            timeout=args.legacy_timeout,
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
