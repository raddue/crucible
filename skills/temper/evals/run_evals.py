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
import re
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


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomic write via tmp + os.replace. POSIX-atomic on same filesystem.

    QG R2 Fix 1: SIGINT/OOM/disk-full mid-write previously left truncated JSON,
    which the next `--compare-baseline` would crash on (R1 try/except converted
    crash to rc=2, but lost the baseline-correctness signal). This helper
    ensures readers never observe a partial file.

    Used for: score() out_path (last_run/per-iter), _write_baseline,
    _legacy_main's last_run write. NOT used for stage-manifest.json or
    reviewer dispatch files (different lifecycle — write-once-never-reread).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _resolve_output_path(run_id: str, *, per_iter: bool) -> Path:
    """S4 R6: resolves output path at call time using CURRENT _EVALS_DIR.

    Replaces direct `_LAST_RUN` / `_EVALS_DIR / ".calibrate-state" / ...` references
    in score(). Eliminates the import-time vs runtime asymmetry that previously
    required tests to monkeypatch _LAST_RUN AND _EVALS_DIR separately.

    Note: `TEMPER_LAST_RUN_OVERRIDE` (Task 4 Step 3.5 addendum) still wins for the
    SHARED path when set — preserved here for legacy test-isolation parity. The
    per-iter path is unaffected by the override (no test currently needs it).
    """
    if per_iter:
        return _EVALS_DIR / ".calibrate-state" / f"last_run-{run_id}.json"
    # Legacy override hook preserved (Task 4 Step 3.5 addendum)
    env_override = os.environ.get("TEMPER_LAST_RUN_OVERRIDE")
    if env_override:
        return Path(env_override)
    return _EVALS_DIR / "last_run.json"


def _resolve_history_path() -> Path:
    """#291: resolve the lens-health history log path at CALL TIME.

    Mirrors `_resolve_output_path`'s call-time `_EVALS_DIR` resolution rather
    than binding a module-level `_HISTORY_PATH` at import. The score-test
    harness (`test_run_evals_score.py::_seed_dispatch_dir`) monkeypatches
    `_EVALS_DIR` to `tmp_path`; resolving here means that single monkeypatch
    keeps history writes inside the test sandbox. An import-time constant would
    bind to the REAL `_EVALS_DIR` and existing score tests would silently
    append to the real `skills/temper/evals/history.jsonl`.
    """
    return _EVALS_DIR / "history.jsonl"
# SP-R7-C: declared in Task 6 (not Task 8) so test_run_evals_score.py's
# `_seed_dispatch_dir` helper can `monkeypatch.setattr(run_evals, "_BASELINE_PATH", ...)`
# without raising AttributeError. The `_write_baseline` / `_compare_baseline` helper
# functions that USE this constant are still added in Task 8 (stubs added below in Task 6).
_BASELINE_PATH = _EVALS_DIR / "baseline.json"

# #291: rolling lens-health history log cap (most-recent K records kept).
# The history.jsonl path itself is resolved at call time via
# `_resolve_history_path()` (NOT a module-level constant) so the `_EVALS_DIR`
# test monkeypatch covers it — see that helper's docstring.
_HISTORY_CAP = 50

# Task 2 (#290 S1): empirical-tolerance calibration artifact path. The header
# schema is enforced by `test_calibration_json_schema`. Mutations land via
# `scripts/calibrate_tolerance.py` after k=3 baseline runs through the post-#297
# 3-step protocol (NOT via `claude -p` — see feedback_no_claude_p).
_CALIBRATION_PATH = _EVALS_DIR / "calibration.json"

_FIXTURE_CONTENT_HEADER = (
    "## Fixture content (synthetic — review this in lieu of running git commands):\n\n"
)


# Task 10 (#290): shared --source filter values.
# Single source of truth for the `--source` argparse choices on both
# `stage` (post-#297) and `score` subcommands. Also imported by
# `lens_runner.py` separately (per #290 plan Task 10).
_SOURCE_VALUES = ("synthetic", "real-pr", "all")


# ---------------------------------------------------------------------------
# Task 4 (F2): pr_description leakage check (warning-only + fatal ^Lens:)
# Task 5 (S2): lens_column enum + forward-compat allowlist
# ---------------------------------------------------------------------------


class FixtureValidationError(Exception):
    """Raised when a fixture violates a load-time validation gate.

    Task 8 will wire this into _validate_fixtures; Tasks 4 and 5 raise it
    for fatal sub-gates (^Lens: line in pr_description; reserved-future
    lens_column values) so the exception class is the single source of
    truth for fixture-schema failures.
    """


# Substring patterns (case-insensitive) — Design Harness §2(f).
# WARNING-only per R1 demotion. Substring (not word-boundary) for these so
# `srp-related`, `over-defensive`, etc. trip the warning per design intent.
_LEAK_SUBSTR_PATTERNS = (
    "lens",
    "dry",
    "surgical",
    "srp",
    "ocp",
    "re-attribut",
    "scope bleed",
    "scope-bleed",
    "defense-in-depth",
    "defense in depth",
    "over-defensive",
)

# Word-boundary patterns (case-insensitive) — narrow set per R3 S3.
# Only `tenancy` / `rollback` themselves trip; `tenant_id`, `rollback_handler`
# (function name), `safe-undo flow` etc. pass cleanly.
_LEAK_WORDBOUNDARY_PATTERNS = (r"\btenancy\b", r"\brollback\b")

# Semantic-prime word-boundary patterns — Design Harness §2(f).
_LEAK_SEMANTIC_PRIMES = (
    r"\bduplicate\b",
    r"\bextract\b",
    r"\breformat\b",
    r"\bresponsibility\b",
    r"\bregistry\b",
    r"\belif\b",
    r"\bdispatch\b",
    r"\bunrelated\b",
    r"\bdrive-by\b",
)

# Fatal pattern: `^Lens:` line (case-insensitive, multiline) — direct
# collision with _LENS_RE parsing in lens_runner.
_LEAK_FATAL_LENS_LINE_RE = re.compile(r"^\s*Lens:", re.IGNORECASE | re.MULTILINE)


def _check_pr_description_leakage(
    pr_description: str, fixture_id: str = "<unknown>"
) -> list[str]:
    """Scan pr_description for lens-vocab leak.

    Returns: list of WARNING strings (substring + word-boundary + semantic-prime
    hits). Emits each warning to stderr as a side effect.

    Raises: FixtureValidationError if a `^Lens:` line is present — that
    pattern directly collides with `_LENS_RE` parsing downstream and is
    not survivable.

    Task 8 will call this from `_validate_fixtures` once per fixture.
    """
    if not isinstance(pr_description, str):
        return []

    # Fatal carve-out: ^Lens: line match — re-raise as FixtureValidationError.
    if _LEAK_FATAL_LENS_LINE_RE.search(pr_description):
        raise FixtureValidationError(
            f"pr_description for fixture {fixture_id!r} contains a literal "
            f"'Lens:' line, which collides with downstream `_LENS_RE` parsing"
        )

    warnings: list[str] = []
    lower = pr_description.lower()
    for pat in _LEAK_SUBSTR_PATTERNS:
        if pat in lower:
            warnings.append(pat)
    for regex_pat in _LEAK_WORDBOUNDARY_PATTERNS + _LEAK_SEMANTIC_PRIMES:
        if re.search(regex_pat, pr_description, re.IGNORECASE):
            # Strip regex anchors for display
            display = regex_pat.replace(r"\b", "")
            warnings.append(display)

    for w in warnings:
        print(
            f"WARNING: pr_description for fixture {fixture_id!r} contains "
            f"potentially-priming substring '{w}'",
            file=sys.stderr,
        )
    return warnings


# Task 5: lens_column enum + forward-compat
# Currently-wired lens columns (Design DEC-4 — Surgical/DRY/SRP/OCP +
# `none` sentinel for negative/defense-in-depth fixtures).
_LENS_COLUMN_VALUES = ("Surgical", "DRY", "SRP", "OCP", "none")

# Reserved for future lens-column widening. Fixtures carrying these values
# fail-loud today so the early-arriving Tenancy/Rollback fixture surfaces
# with an actionable error pointing at #267 follow-ups (#294/#295/#296)
# rather than being silently accepted under typo. Wire-in lands when
# Tenancy/Rollback real-PR fixtures arrive (see DEC-4 in #290 design).
_LENS_COLUMN_FUTURE = ("Tenancy", "Rollback")


def _validate_lens_column(value: Any, fixture_id: str = "<unknown>") -> None:
    """Validate a fixture's `lens_column` field.

    Accepts:
      - string in `_LENS_COLUMN_VALUES`
      - list of strings drawn from `_LENS_COLUMN_VALUES \\ {"none"}`
        (mixed fixtures; singleton "none" is non-mixed by definition)

    Raises:
      - FixtureValidationError on typo / unknown value
      - FixtureValidationError with a distinct reserved-future message
        when value matches `_LENS_COLUMN_FUTURE`
    """
    if isinstance(value, str):
        if value in _LENS_COLUMN_FUTURE:
            raise FixtureValidationError(
                f"lens_column {value!r} is reserved for future use; not yet wired."
            )
        if value not in _LENS_COLUMN_VALUES:
            raise FixtureValidationError(
                f"lens_column {value!r} for fixture {fixture_id!r} not in "
                f"{_LENS_COLUMN_VALUES}"
            )
        return
    if isinstance(value, list):
        if not value:
            raise FixtureValidationError(
                f"lens_column for fixture {fixture_id!r} is an empty list"
            )
        allowed_list = tuple(v for v in _LENS_COLUMN_VALUES if v != "none")
        for item in value:
            if not isinstance(item, str):
                raise FixtureValidationError(
                    f"lens_column list for fixture {fixture_id!r} contains "
                    f"non-string entry {item!r}"
                )
            if item in _LENS_COLUMN_FUTURE:
                raise FixtureValidationError(
                    f"lens_column {item!r} is reserved for future use; not yet wired."
                )
            if item not in allowed_list:
                raise FixtureValidationError(
                    f"lens_column entry {item!r} for fixture {fixture_id!r} "
                    f"not in {allowed_list} (singleton 'none' is non-mixed)"
                )
        return
    raise FixtureValidationError(
        f"lens_column for fixture {fixture_id!r} must be str or list, "
        f"got {type(value).__name__}"
    )


# ---------------------------------------------------------------------------
# Task 8 (#290 F2/S3): _validate_fixtures + BaselineQualityError
# Gates (a)-(m) per Design Harness §2.
# ---------------------------------------------------------------------------


class BaselineQualityError(FixtureValidationError):
    """Gate (l)/(m): baseline-quality refusal.

    Subclass of FixtureValidationError so existing rc=2 handlers
    (`except FixtureValidationError`) catch this without modification.
    Raised exclusively from the `score --write-baseline` path — never
    by `_validate_fixtures` directly.
    """


# Gate (b) SHA-format regex: `#NNN @ <7-40 lowercase hex>` (Design Harness §2(b)).
_SOURCE_PR_RE = re.compile(r"^#\d+ @ [0-9a-f]{7,40}$")


def _load_evals(path: Path) -> tuple[list[dict], list[dict]]:
    """Load evals.json and fold any top-level `global_expectations` into each eval.

    Reads the JSON at `path`, extracts the optional top-level
    `global_expectations` array (default `[]`), and appends EVERY global
    expectation entry to EACH eval's `expectations` list (creating the list if
    absent). The append mutates the eval dicts IN PLACE so that any subsequent
    `fixture_sha(fix)` reflects the merged expectations — and does so
    identically across the `stage` and `score` load paths (their shas match).

    On the current evals.json (no `global_expectations` key) this is a clean
    no-op: each eval is returned unchanged and `global_expectations` is `[]`.

    Returns: `(evals, global_expectations)`.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    evals = data.get("evals", [])
    global_expectations = data.get("global_expectations", []) or []
    if global_expectations:
        for ev in evals:
            if not isinstance(ev, dict):
                continue
            exps = ev.get("expectations")
            if not isinstance(exps, list):
                exps = []
                ev["expectations"] = exps
            for ge in global_expectations:
                exps.append(ge)
    return evals, global_expectations


def _validate_global_expectations(global_expectations: list[dict]) -> None:
    """Validate each top-level `global_expectations` entry (Pre-flight matcher).

    Every entry must be a dict with `type == "mechanical"` and a `check` present
    in `lens_runner._CHECK_REGISTRY`. Raises `FixtureValidationError` otherwise.
    """
    for idx, ge in enumerate(global_expectations):
        if not isinstance(ge, dict):
            raise FixtureValidationError(
                f"global_expectations[{idx}] is not an object: {ge!r}"
            )
        if ge.get("type") != "mechanical":
            raise FixtureValidationError(
                f"global_expectations[{idx}] must have type=='mechanical' "
                f"(got {ge.get('type')!r})"
            )
        # Normalize snake_case → kebab-case exactly as evaluate_expectation does
        # at runtime, so a global with check "report_has_block" is accepted here
        # rather than rejected only to resolve fine when actually dispatched.
        check = lens_runner._normalize_check_name(ge.get("check"))
        if check not in lens_runner._CHECK_REGISTRY:
            raise FixtureValidationError(
                f"global_expectations[{idx}] check {ge.get('check')!r} not in "
                f"lens_runner._CHECK_REGISTRY"
            )


def _validate_fixtures(
    evals_data: dict,
    *,
    strict_source_pr: bool = False,
) -> None:
    """Apply Design Harness §2 gates (a)-(m) (Task 8 / #290 F2).

    Gates implemented here (raise `FixtureValidationError`):
      (a) `source` field present and in {"synthetic", "real-pr"}
      (b) `real-pr` w/ malformed `source_pr` (regex `^#\\d+ @ [0-9a-f]{7,40}$`);
          also asserts top-level `evals` key (R1 M12).
      (c) `synthetic_pair` resolves AND its `lens_column` matches.
      (d) empty `pr_description`.
      (e) bad `lens_column` enum (delegated to `_validate_lens_column`).
      (f) lens-vocab `^Lens:` line in `pr_description` (delegated to
          `_check_pr_description_leakage` — substring + word-boundary +
          semantic-prime hits are warnings only; only `^Lens:` is fatal).
      (g) `^Lens:` substring in `prompt` (warning).
      (i) trials-uniformity: every non-`none` lens_column fixture MUST
          declare `replicate_rule.trials in {5, 10}`.
      (j) `--strict-source-pr` SHA-existence (opt-in; requires git env).
      (k) mixed-fixture cap: at most ONE real-PR fixture with list `lens_column`.

    Gates (l) and (m) live in `_write_baseline` / `score --write-baseline`
    paths (BaselineQualityError, not validation-time).

    Args:
        evals_data: parsed evals.json (must have top-level "evals" key).
        strict_source_pr: when True, runs gate (j) — `git cat-file -e` per SHA.
    """
    if not isinstance(evals_data, dict) or "evals" not in evals_data:
        raise FixtureValidationError(
            "evals.json missing top-level 'evals' array (R1 M12 / Design Harness §1)"
        )
    fixtures = evals_data["evals"]
    if not isinstance(fixtures, list):
        raise FixtureValidationError(
            "evals.json 'evals' field must be a list of fixture objects"
        )

    # Pre-compute id->fixture for gate (c) twin lookup
    by_id = {f.get("id"): f for f in fixtures if isinstance(f, dict)}

    # Gate (j) pre-condition: if strict, verify git env once up front.
    if strict_source_pr:
        import subprocess
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, check=False,
            )
            if r.returncode != 0:
                raise FixtureValidationError(
                    f"git-environment-unavailable: {r.stderr.strip()}"
                )
        except (FileNotFoundError, OSError) as e:
            raise FixtureValidationError(
                f"git-environment-unavailable: {e}"
            ) from e

    list_lens_column_offenders: list[str] = []

    for fix in fixtures:
        if not isinstance(fix, dict):
            raise FixtureValidationError(
                f"fixture entry is not an object: {fix!r}"
            )
        fid = fix.get("id", "<unknown>")

        # gap_documented carve-out (Step 3d): waives non-empty prompt + body
        # requirements but still validates schema fields.
        gap_documented = bool(fix.get("gap_documented", False))

        # (a) source presence + value
        source = fix.get("source")
        if source not in ("synthetic", "real-pr"):
            raise FixtureValidationError(
                f"fixture {fid!r} missing/invalid 'source' (got {source!r}; "
                f"expected 'synthetic' or 'real-pr')"
            )

        # (b) real-pr source_pr format
        if source == "real-pr":
            spr = fix.get("source_pr", "")
            if not isinstance(spr, str) or not _SOURCE_PR_RE.match(spr):
                raise FixtureValidationError(
                    f"fixture {fid!r} (source='real-pr') has malformed "
                    f"'source_pr' {spr!r}; expected '#NNN @ <7-40 hex sha>'"
                )

        # (d) empty pr_description (waived for gap_documented)
        pr_desc = fix.get("pr_description", "")
        if not gap_documented:
            if not isinstance(pr_desc, str) or not pr_desc.strip():
                raise FixtureValidationError(
                    f"fixture {fid!r} has empty/missing 'pr_description'"
                )

        # (e) lens_column enum
        lens_col = fix.get("lens_column")
        if lens_col is None:
            raise FixtureValidationError(
                f"fixture {fid!r} missing 'lens_column' field"
            )
        _validate_lens_column(lens_col, fid)  # raises on typo/reserved

        # (f) pr_description leak check — fatal carve-out on ^Lens: line only
        if isinstance(pr_desc, str) and pr_desc:
            _check_pr_description_leakage(pr_desc, fid)  # may raise

        # (g) ^Lens: substring in prompt → warning, not fatal
        prompt = fix.get("prompt", "")
        if isinstance(prompt, str) and prompt and not gap_documented:
            if _LEAK_FATAL_LENS_LINE_RE.search(prompt):
                print(
                    f"WARNING: fixture {fid!r} prompt contains '^Lens:' line; "
                    f"may collide with downstream parsing",
                    file=sys.stderr,
                )
            # gap_documented fixtures bypass the non-empty prompt requirement
        elif not gap_documented and not prompt:
            raise FixtureValidationError(
                f"fixture {fid!r} has empty/missing 'prompt' "
                f"(set gap_documented=true to waive)"
            )

        # (i) trials-uniformity: non-'none' lens columns must have trials in {5, 10}
        is_none_col = lens_col == "none"
        if not is_none_col:
            rule = fix.get("replicate_rule", {})
            trials = rule.get("trials") if isinstance(rule, dict) else None
            if trials not in (5, 10):
                raise FixtureValidationError(
                    f"fixture {fid!r} lens_column={lens_col!r} must declare "
                    f"replicate_rule.trials in {{5, 10}} (R1 M9 / gate (i)); "
                    f"got {trials!r}"
                )

        # (c) synthetic_pair resolution + lens_column match
        pair_id = fix.get("synthetic_pair")
        if pair_id is not None:
            # pair_id can be a string OR list (for mixed-real)
            pair_ids = pair_id if isinstance(pair_id, list) else [pair_id]
            for pid in pair_ids:
                twin = by_id.get(pid)
                if twin is None:
                    raise FixtureValidationError(
                        f"fixture {fid!r} synthetic_pair {pid!r} does not "
                        f"resolve to a known fixture id"
                    )
                twin_lc = twin.get("lens_column")
                if isinstance(lens_col, str):
                    if twin_lc != lens_col:
                        raise FixtureValidationError(
                            f"fixture {fid!r} synthetic_pair twin {pid!r} "
                            f"lens_column {twin_lc!r} does not match "
                            f"{lens_col!r}"
                        )
                elif isinstance(lens_col, list):
                    # Mixed: twin's lens_column must appear in the mixed list
                    if isinstance(twin_lc, str):
                        if twin_lc not in lens_col:
                            raise FixtureValidationError(
                                f"fixture {fid!r} (mixed) synthetic_pair twin "
                                f"{pid!r} lens_column {twin_lc!r} not in mixed "
                                f"set {lens_col!r}"
                            )
                    elif isinstance(twin_lc, list):
                        if not set(twin_lc) <= set(lens_col):
                            raise FixtureValidationError(
                                f"fixture {fid!r} (mixed) synthetic_pair twin "
                                f"{pid!r} lens_column {twin_lc!r} not subset of "
                                f"{lens_col!r}"
                            )

        # (j) strict source_pr existence check (opt-in)
        if strict_source_pr and source == "real-pr":
            import subprocess
            spr = fix.get("source_pr", "")
            # Parse "#NNN @ <sha>"
            m = re.match(r"^#\d+ @ ([0-9a-f]{7,40})$", spr)
            if m:
                sha = m.group(1)
                r = subprocess.run(
                    ["git", "cat-file", "-e", sha],
                    capture_output=True, text=True, check=False,
                )
                if r.returncode != 0:
                    raise FixtureValidationError(
                        f"fixture {fid!r} source_pr sha {sha!r} not present "
                        f"in current git repository (gate (j))"
                    )

        # (k) mixed-fixture cap: at most one real-pr fixture with list lens_column
        if source == "real-pr" and isinstance(lens_col, list):
            list_lens_column_offenders.append(fid)

    # Gate (k) check after loop
    if len(list_lens_column_offenders) > 1:
        raise FixtureValidationError(
            f"gate (k): at most one real-PR fixture may carry list-valued "
            f"lens_column; found: {list_lens_column_offenders}"
        )


# ---------------------------------------------------------------------------
# Task 9 (#290 S3): per-lens-column PASS for mixed fixtures
# ---------------------------------------------------------------------------


def _expectation_lens_tag(expectation: dict) -> str | None:
    """Extract the lens-column tag from an expectation's `params`.

    Returns the lens-column string (e.g. "Surgical", "DRY", "SRP", "OCP")
    if the expectation is tagged with one; returns `None` for "global"
    expectations (e.g. `lens-findings-in-allowed-files`, `all-findings-have-file-line`)
    that apply across all lens columns.

    Tag-source precedence (per Design Q5 resolution):
      1. `params.lens` (most common — `lens-finding-*` checks)
      2. `params.primary_lens` (`no-lens-findings-overlap-region`)
      3. `params.category` (Tenancy/Rollback category checks)
    """
    params = expectation.get("params") or expectation.get("args") or {}
    if not isinstance(params, dict):
        return None
    for key in ("lens", "primary_lens", "category"):
        val = params.get(key)
        if isinstance(val, str):
            return val
    return None


def _compute_per_lens_pass(
    fixture: dict,
    trial_outcomes: list[bool] | dict[int, bool],
) -> dict[str, bool]:
    """Compute per-lens-column PASS map for a fixture across one trial.

    Non-mixed (`lens_column` is a string): returns
        `{lens_column: all(trial_outcomes)}`

    Mixed (`lens_column` is a list): partitions expectations by their existing
    per-expectation lens tag (`_expectation_lens_tag`). For each lens in the
    fixture's `lens_column` list:
        `{lens: all(outcomes for expectations tagged with that lens OR untagged)}`

    Untagged (global) expectations contribute to ALL columns — they must pass
    for every column to PASS that column.

    Raises:
        ValueError: if any expectation's lens tag is non-None but does not
          appear in the fixture's `lens_column` list (cross-leakage guard).
    """
    expectations = fixture.get("expectations", [])

    # Normalize trial_outcomes to a list aligned with expectations
    if isinstance(trial_outcomes, dict):
        outcomes = [bool(trial_outcomes.get(i, False)) for i in range(len(expectations))]
    else:
        outcomes = [bool(v) for v in trial_outcomes]
    if len(outcomes) != len(expectations):
        raise ValueError(
            f"_compute_per_lens_pass: trial_outcomes length {len(outcomes)} "
            f"does not match expectations length {len(expectations)} "
            f"for fixture {fixture.get('id', '<?>')!r}"
        )

    lens_column = fixture.get("lens_column")

    # Non-mixed path (string)
    if isinstance(lens_column, str):
        return {lens_column: all(outcomes)}

    # Mixed path (list)
    if isinstance(lens_column, list):
        lens_set = set(lens_column)
        # Cross-leakage guard
        for idx, exp in enumerate(expectations):
            tag = _expectation_lens_tag(exp)
            if tag is not None and tag not in lens_set:
                # Only fail-loud on lens tags that are KNOWN lens-column values;
                # category tags (Tenancy/Rollback) for category-finding checks
                # are allowed when fixture is non-mixed-future. For mixed
                # fixtures (lens_column is list of Surgical/DRY/SRP/OCP only),
                # any tag outside that set is cross-leakage.
                if tag in _LENS_COLUMN_VALUES or tag in _LENS_COLUMN_FUTURE:
                    raise ValueError(
                        f"_compute_per_lens_pass: expectation #{idx} of "
                        f"fixture {fixture.get('id', '<?>')!r} has lens tag "
                        f"{tag!r} not in lens_column {lens_column!r} "
                        f"(cross-leakage)"
                    )

        result: dict[str, bool] = {}
        for lens in lens_column:
            passed = True
            for idx, exp in enumerate(expectations):
                tag = _expectation_lens_tag(exp)
                # Untagged (global) expectations apply to every column.
                # Tagged expectations apply only to their matching column.
                if tag is None or tag == lens:
                    if not outcomes[idx]:
                        passed = False
                        break
            result[lens] = passed
        return result

    # No lens_column → return empty (or treat as "none"). Schema validation
    # at Task 8 will reject missing lens_column; this is defense-in-depth.
    return {}


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


_PLACEHOLDER_RE = re.compile(r"\{[A-Z_][A-Z0-9_]*\}")


def _validate_rendered_prompt(rendered: str) -> None:
    """I-T9 (M-4): length-floor + placeholder-residual check.

    Template-evolution-tolerant. Catches catastrophically-empty renders
    and unsubstituted placeholders without binding to specific placeholder names.

    QG R1 Fix 6: narrowed to `{UPPER_SNAKE_CASE}` placeholder shape only —
    bare `{` characters (JSON examples, prose, `${VAR}` syntax) no longer
    false-positive.
    """
    if len(rendered) <= 200:
        raise ValueError(
            f"rendered prompt has length {len(rendered)} ≤ 200 bytes "
            f"(I-T9 length-floor): suspect catastrophic-empty render"
        )
    leftover = _PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise ValueError(
            f"rendered prompt contains unsubstituted placeholders "
            f"(I-T9 placeholder-residual): {leftover}"
        )


def stage(
    run_id: str,
    *,
    force: bool = False,
    source: str = "all",
    fixture: str | None = None,
    trials_override: int | None = None,
    timeout: int = 300,
    strict_source_pr: bool = False,
) -> Path:
    """Render fixtures × trials to dispatch files; write stage-manifest.json.

    Returns: dispatch directory path.
    Raises:
        ValueError: invalid run_id (I-9) or source+fixture intersection (M-1)
        FileExistsError: dispatch dir exists and force=False
        ValueError: trials_override < 1 or timeout < 1 (QG R1 Fix 4)
    """
    validate_run_id(run_id)
    # QG R1 Fix 4: reject zero/negative trials_override + timeout (false-green guard)
    if trials_override is not None and trials_override < 1:
        raise ValueError(
            f"--trials-override must be >= 1 (got {trials_override})"
        )
    if timeout < 1:
        raise ValueError(f"--timeout must be >= 1 (got {timeout})")

    # Load fixtures. `_load_evals` folds any top-level `global_expectations`
    # into each eval's `expectations` list IN PLACE before any fixture_sha is
    # computed, so stage- and score-side shas stay identical.
    fixtures, global_expectations = _load_evals(_EVALS_JSON)
    # Task 8 (#290 F2): schema gate at stage-time. Raises FixtureValidationError
    # for any (a)-(k) failure; rc=2 propagates via the main() handler. Pass the
    # post-merge fixtures so validation sees the same records that get hashed.
    _validate_fixtures({"evals": fixtures}, strict_source_pr=strict_source_pr)
    # Global Pre-flight matcher: validate each global_expectations entry.
    _validate_global_expectations(global_expectations)

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
        # QG R1 Fix 2: record trials_override so score() can honor manifest's
        # actual trial count, not recompute from evals.json replicate_rule.
        "trials_override": trials_override,
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
    mock_dir: Path | None,
    replay_outputs: list[str] | None,
) -> str | None:
    """Resolve a per-trial reviewer output from mock-dir or replay cache.

    Post-#297: subprocess-based live dispatch is removed. Live runs now go
    through the `stage` subcommand + `/temper-eval-collect` skill + `score`
    subcommand. When neither `replay_outputs` nor `mock_dir` applies this
    returns `None`; legacy callers error out in `_legacy_main` before reaching
    here.
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
    mock_dir: Path | None,
    replay_outputs: list[str] | None,
    trials_override: int | None,
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
            mock_dir=mock_dir,
            replay_outputs=replay_outputs,
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
            try:
                verdict, rationale = lens_runner.evaluate_expectation(expectation, out, fix)
            except lens_runner.MutexViolationError:
                # T1: a reviewer finding tagged with BOTH Lens: and Category:
                # is a mutex violation (Design D7). Score the trial FAIL with a
                # clear rationale instead of letting the raise crash the run.
                verdict, rationale = (
                    "FAIL",
                    "mutex violation: finding tagged both Lens and Category",
                )
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


# Task 2/3 (#290 S1): calibration loader. Returns the calibrated tolerance
# value for the drift-delta gate. Falls back to the analytic floor (0.447)
# if calibration.json is absent — never silently uses the legacy 0.7 literal.
_DEFAULT_TOLERANCE_FLOOR = 0.447


def _load_calibration() -> dict:
    """Load calibration.json. Returns {} if absent or malformed.

    The drift-delta gate uses `_load_calibration().get('tolerance', 0.447)`
    so a missing artifact degrades gracefully to the analytic floor rather
    than crashing the score path.
    """
    if not _CALIBRATION_PATH.exists():
        return {}
    try:
        return json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _drift_tolerance() -> float:
    """Return the drift-delta tolerance from calibration.json.

    Falls back to `_DEFAULT_TOLERANCE_FLOOR` (0.447) when calibration.json
    is absent or malformed. Task 3 wires this into the gate.
    """
    cal = _load_calibration()
    val = cal.get("tolerance")
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    return _DEFAULT_TOLERANCE_FLOOR


_CALIBRATION_PLACEHOLDER = {
    "calibrated_at": "PLACEHOLDER",
    "baseline_runs": 3,
    "per_lens_sigma_empirical": {
        "Surgical": 0.0,
        "DRY": 0.0,
        "SRP": 0.0,
        "OCP": 0.0,
    },
    "sigma_worst": 0.0,
    "t_emp": 0.0,
    "analytic_floor": _DEFAULT_TOLERANCE_FLOOR,
    "floor_binding": True,
    "tolerance": 0.45,
    "design_ceiling": 0.7,
    "ceiling_binding": False,
    "method": (
        "min(max(2x empirical sigma over k=3 synth-only baseline runs, "
        "0.447 analytic floor), 0.7 design ceiling)"
    ),
    "note": (
        "Placeholder header written by `score --write-calibration`. "
        "Run scripts/calibrate_tolerance.py after k=3 baseline runs for "
        "the real empirical artifact."
    ),
}


def _write_calibration_placeholder() -> bool:
    """(#290 Task 2) Write a placeholder calibration.json if absent.

    Returns True if a file was written, False if one already exists.

    Computing real empirical sigmas requires the 3-step protocol
    (stage / /temper-eval-collect / score, k=3) — see
    scripts/calibrate_tolerance.py for the full flow. This helper exists
    so the `--write-calibration` CLI flag has a coherent no-op when the
    artifact is missing in CI / clean checkouts.
    """
    if _CALIBRATION_PATH.exists():
        return False
    import datetime as _dt2
    payload = dict(_CALIBRATION_PLACEHOLDER)
    payload["calibrated_at"] = _dt2.datetime.now(_dt2.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    _atomic_write_text(_CALIBRATION_PATH, json.dumps(payload, indent=2) + "\n")
    return True


# Task 8: real impls. SP-1 baseline header carries template_sha so
# --compare-baseline can detect dispatch-template drift since baseline.
def _write_baseline(payload: dict, current_template_sha: str) -> None:
    """SP-1: baseline header carries template_sha."""
    baseline = dict(payload)
    baseline["template_sha"] = current_template_sha
    # QG R2 Fix 1: atomic write — prevents truncated baseline.json mid-write
    _atomic_write_text(_BASELINE_PATH, json.dumps(baseline, indent=2))


def _compare_baseline(
    payload: dict,
    current_template_sha: str,
    *,
    incomplete: bool,
    evals_fixture_ids: set[str],
    allow_fixture_drift: bool = False,
) -> int:
    """Return 1 on regression, 2 if refused (incomplete / missing baseline), 0 if clean.

    QG R3 Fix 1: fixture-set drift is now checked by the caller (score()) against
    the live evals.json keyset (evals_fixture_ids), not against the possibly-filtered
    manifest payload. This function receives the already-validated evals_fixture_ids
    and operates on the intersection of baseline keys + current manifest scope, which
    is the correct behavior — the drift gate has already passed at the outer scope.
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
    # QG R1 Fix 3: guard malformed/truncated baseline.json (e.g. interrupted
    # prior `--write-baseline`). Surface fatal-with-context not raw traceback.
    try:
        baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[fatal] baseline.json malformed or unreadable: {e}",
            file=sys.stderr,
        )
        return 2
    if baseline.get("template_sha") != current_template_sha:
        print(
            f"[warn] template_sha drift since baseline (baseline: "
            f"{baseline.get('template_sha', '?')[:12]}…, current: "
            f"{current_template_sha[:12]}…); verdict comparison may be apples-to-oranges",
            file=sys.stderr,
        )
    # Per-fixture verdict comparison against the current manifest scope.
    # Drift against evals.json has already been checked in score() before this call.
    current_verdicts = {f["id"]: f["verdict"] for f in payload["fixtures"]}
    base_verdicts = {f["id"]: f["verdict"] for f in baseline.get("fixtures", [])}

    regressions = []
    for fid, base_v in base_verdicts.items():
        cur_v = current_verdicts.get(fid)
        if base_v == "PASS" and cur_v in ("FAIL", "N/A"):
            regressions.append((fid, base_v, cur_v))

    # Task 3 (#290 S1): per-fixture PASS-rate drift-delta gate. Reads tolerance
    # from calibration.json (analytic floor 0.447 when absent — never the
    # legacy 0.7 literal). |cur_rate - base_rate| > tolerance flags as drift.
    tolerance = _drift_tolerance()
    cur_rates = _per_fixture_pass_rates(payload.get("fixtures", []))
    base_rates = _per_fixture_pass_rates(baseline.get("fixtures", []))
    drift_flags = []
    for fid, base_rate in base_rates.items():
        if fid not in cur_rates:
            continue
        delta = abs(cur_rates[fid] - base_rate)
        if delta > tolerance:
            drift_flags.append((fid, base_rate, cur_rates[fid], delta))
    if drift_flags:
        for fid, br, cr, dl in drift_flags:
            print(
                f"[drift] {fid}: baseline pass_rate={br:.2f} -> current={cr:.2f} "
                f"(delta={dl:.2f} > tolerance={tolerance:.2f})",
                file=sys.stderr,
            )

    if regressions or drift_flags:
        for fid, b, c in regressions:
            print(f"[regression] {fid}: baseline {b} -> current {c}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Task 11 (#290 S3): grouped summary + by_source + drift_delta + per_trial_rates
# ---------------------------------------------------------------------------


def _classify_trial_outcome(
    reviewer_output: str | None, per_trial_verdicts_at_idx: list[str]
) -> str:
    """Three-state classifier for a single trial (R1 M4 / R3 SP1).

    Returns one of 'PASS' | 'FAIL' | 'ERROR'.

    - ERROR: reviewer dispatch failed (`reviewer_output is None`). Excluded
      from the per-trial-rate denominator.
    - PASS:  reviewer output present, every expectation verdict at this trial
      index is 'PASS'.
    - FAIL:  reviewer output present, at least one expectation verdict is
      non-'PASS' (FAIL or N/A from lens_runner inconclusive aggregation).

    Per R3 S-1, lens_runner-inconclusive 'N/A' verdicts (reviewer output
    present, aggregation ambiguous) map to FAIL — NOT ERROR.
    """
    if reviewer_output is None:
        return "ERROR"
    if all(v == "PASS" for v in per_trial_verdicts_at_idx):
        return "PASS"
    return "FAIL"


def _as_lens_list(lens_column: Any) -> list[str]:
    """Normalize a fixture's lens_column to a list of lens-column strings.

    String 'none' → []  (zero-contribution per R1 S6).
    String lens → [lens].
    List → list (already normalized).
    """
    if isinstance(lens_column, str):
        if lens_column == "none":
            return []
        return [lens_column]
    if isinstance(lens_column, list):
        return [v for v in lens_column if isinstance(v, str) and v != "none"]
    return []


def _compute_grouped_summary(
    fixture_results: list[dict],
    fixtures_by_id: dict[str, dict],
) -> dict[str, Any]:
    """Compute the Task-11 emission block: by_source + drift_delta + per_trial_rates.

    R1 S6: lens_column=='none' fixtures appear in `by_source` but contribute
    ZERO to any lens column's drift_delta / per_trial_rates.
    R1 M4 / R3 SP1: ERROR trials (reviewer_output is None) are excluded from
    the denominator. Rates = PASS / (PASS + FAIL).
    R1 Q6: per-fixture trial sum — denominators are summed over each fixture's
    actual trial count, not scalar trials × fixture-count.

    Args:
        fixture_results: list of per-fixture aggregate dicts from
            `_aggregate_from_outputs`. Each entry must carry `id`,
            `reviewer_outputs`, and `expectations[*].per_trial_verdicts`.
        fixtures_by_id: live evals.json fixture map, used for `source` +
            `lens_column` lookup (the result dict does NOT carry these).

    Returns:
        dict with keys:
          - `by_source`: {synthetic: [{id, verdict}], real-pr: [{id, verdict}]}
          - `drift_delta`: {lens: float | None}  (synthetic_rate - real_rate)
          - `per_trial_rates`: {lens: {synthetic: float|None, real-pr: float|None}}
    """
    by_source: dict[str, list[dict[str, str]]] = {"synthetic": [], "real-pr": []}
    # Lens columns considered in drift_delta. Derived from _LENS_COLUMN_VALUES
    # minus 'none' per M-R6-5 — no hardcoded ('Surgical','DRY','SRP','OCP') tuple.
    lens_cols = tuple(v for v in _LENS_COLUMN_VALUES if v != "none")

    # Per-lens / per-source PASS + FAIL trial counts (ERROR excluded).
    counts: dict[str, dict[str, dict[str, int]]] = {
        lens: {
            "synthetic": {"PASS": 0, "FAIL": 0, "ERROR": 0},
            "real-pr": {"PASS": 0, "FAIL": 0, "ERROR": 0},
        }
        for lens in lens_cols
    }

    for fr in fixture_results:
        fid = fr.get("id")
        fix = fixtures_by_id.get(fid, {})
        source = fix.get("source", "synthetic")
        if source not in by_source:
            # Defense in depth — unknown source shouldn't appear post-validation
            by_source[source] = []
        by_source[source].append({"id": fid, "verdict": fr.get("verdict", "N/A")})

        lens_list = _as_lens_list(fix.get("lens_column"))
        if not lens_list:
            # R1 S6: lens_column=='none' (or unknown) → zero contribution to
            # any lens column. Still recorded in by_source above.
            continue

        reviewer_outputs = fr.get("reviewer_outputs", [])
        expectations = fr.get("expectations", [])
        # Align per-trial verdicts across all expectations (R1 Q6: per-fixture
        # trial sum). n_trials = len(reviewer_outputs).
        n_trials = len(reviewer_outputs)
        for t in range(n_trials):
            # Collect this trial's per-expectation verdicts.
            verdicts_at_t = [
                er.get("per_trial_verdicts", [])[t]
                for er in expectations
                if t < len(er.get("per_trial_verdicts", []))
            ]
            outcome = _classify_trial_outcome(reviewer_outputs[t], verdicts_at_t)
            # Mixed fixtures contribute to EACH lens column in their list.
            for lens in lens_list:
                if lens not in counts:
                    continue  # forward-compat / future lens columns
                counts[lens][source][outcome] += 1

    # Compute rates + drift_delta. Divide-by-zero guards per R2 Q5.
    per_trial_rates: dict[str, dict[str, float | None]] = {}
    drift_delta: dict[str, float | None] = {}
    for lens in lens_cols:
        syn_pass = counts[lens]["synthetic"]["PASS"]
        syn_fail = counts[lens]["synthetic"]["FAIL"]
        real_pass = counts[lens]["real-pr"]["PASS"]
        real_fail = counts[lens]["real-pr"]["FAIL"]
        syn_denom = syn_pass + syn_fail  # ERROR excluded (R1 M4)
        real_denom = real_pass + real_fail
        syn_rate = (syn_pass / syn_denom) if syn_denom else None
        real_rate = (real_pass / real_denom) if real_denom else None
        per_trial_rates[lens] = {"synthetic": syn_rate, "real-pr": real_rate}
        if syn_rate is None or real_rate is None:
            drift_delta[lens] = None
        else:
            drift_delta[lens] = syn_rate - real_rate

    return {
        "by_source": by_source,
        "drift_delta": drift_delta,
        "per_trial_rates": per_trial_rates,
    }


def _render_grouped_summary(by_source: dict[str, list[dict[str, str]]]) -> str:
    """Render the Task-11 grouped stdout summary.

    Format:
        Synthetic: P/N PASS
        Real-PR:   P/N PASS

    Where P = count of PASS verdicts, N = total fixtures in that group.
    """
    lines: list[str] = []
    for label, key in (("Synthetic", "synthetic"), ("Real-PR", "real-pr")):
        entries = by_source.get(key, [])
        n_pass = sum(1 for e in entries if e.get("verdict") == "PASS")
        lines.append(f"{label}: {n_pass}/{len(entries)} PASS")
    return "\n".join(lines)


def _per_fixture_pass_rates(fixtures: list[dict]) -> dict[str, float]:
    """Compute per-fixture PASS rate (PASS trials / total trials).

    Task 3 (#290 S1) drift-delta gate input. Returns 0.0 for fixtures with
    no expectations or no trials so the gate degrades gracefully on malformed
    baselines (and on synthetic schema variants used by tests).
    """
    rates: dict[str, float] = {}
    for fr in fixtures:
        fid = fr.get("id")
        if not fid:
            continue
        expectations = fr.get("expectations", [])
        if not expectations:
            rates[fid] = 0.0
            continue
        per_trial_lists = [er.get("per_trial_verdicts", []) for er in expectations]
        n_trials = max((len(lst) for lst in per_trial_lists), default=0)
        if n_trials == 0:
            rates[fid] = 0.0
            continue
        passes = 0
        for t in range(n_trials):
            if all(
                t < len(per_trial_lists[i])
                and per_trial_lists[i][t] == "PASS"
                for i in range(len(per_trial_lists))
            ):
                passes += 1
        rates[fid] = passes / n_trials
    return rates


def _append_history(
    run_id: str,
    run_at: str,
    grouped: dict[str, Any],
    source: str,
    *,
    path: Path | None = None,
    cap: int = _HISTORY_CAP,
) -> None:
    """#291 Task 2: append one per-run lens-health record to history.jsonl.

    Builds a single record from the already-computed `grouped` summary:
      - run_id, run_at (ISO-8601, copied from the run payload), source
        (score()'s --source scope: "all" | "synthetic" | "real-pr")
      - per_lens: copied from grouped["per_trial_rates"]
        (shape {lens: {synthetic, real-pr}})
      - by_source: {source: {pass, total}} rolled up from
        grouped["by_source"] using _render_grouped_summary's PASS-over-total
        convention — pass = count of PASS verdicts, total = len(entries), so
        N/A-verdict fixtures count in `total` and never in `pass`.

    Reads existing lines (tolerating an absent file on first run and skipping
    malformed lines rather than crashing — CI starts from an empty/absent
    history because the file is gitignored), appends the new record, keeps only
    the last `cap` records, and rewrites atomically via `_atomic_write_text`.

    When `path is None`, resolves it via `_resolve_history_path()` at call time
    so the `_EVALS_DIR` test monkeypatch covers isolation; `path` stays an
    injectable override for direct unit tests.
    """
    if path is None:
        path = _resolve_history_path()

    by_source_counts: dict[str, dict[str, int]] = {}
    for src_key, entries in (grouped.get("by_source") or {}).items():
        n_pass = sum(1 for e in entries if e.get("verdict") == "PASS")
        by_source_counts[src_key] = {"pass": n_pass, "total": len(entries)}

    record = {
        "run_id": run_id,
        "run_at": run_at,
        "source": source,
        "per_lens": grouped.get("per_trial_rates", {}),
        "by_source": by_source_counts,
    }

    existing: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed prior lines rather than crashing.
                continue
            existing.append(line)

    existing.append(json.dumps(record))
    kept = existing[-cap:] if cap and len(existing) > cap else existing
    _atomic_write_text(path, "\n".join(kept) + "\n")


def score(
    run_id: str,
    *,
    write_baseline: bool = False,
    compare_baseline: bool = False,
    force_rescore: bool = False,
    allow_incomplete: bool = False,
    per_iter: bool = False,
    allow_fixture_drift: bool = False,
    source: str = "all",
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
            # QG R1 Fix 1: guard malformed payload (e.g. `errors:`, `errors: abc/5`,
            # `errors: 1`). Surface fatal-with-context instead of raw traceback.
            try:
                n_str, total_str = first[1].removeprefix("errors:").strip().split("/")
                n_err, total = int(n_str), int(total_str)
            except (ValueError, IndexError):
                print(
                    f"[fatal] malformed .collect-status second line: {first[1]!r}",
                    file=sys.stderr,
                )
                return 2
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

    # Recompute per-trial fixture_sha; refuse mismatches unless --force-rescore.
    # `_load_evals` folds global_expectations into each eval IN PLACE before the
    # sha is recomputed below, mirroring stage() so the shas match.
    _evals_list, _global_expectations = _load_evals(_EVALS_JSON)
    # Validate globals here too: score may run against an evals.json edited after
    # stage, and a malformed global would otherwise fold a silent FAIL/N/A into
    # every fixture instead of being rejected loudly.
    _validate_global_expectations(_global_expectations)
    fixtures_by_id = {f["id"]: f for f in _evals_list}

    # Task 10 (#290): score-time --source filter. Restrict fixtures_by_id to
    # those matching the requested source. Trials referencing filtered-out
    # fixtures are skipped (not errored) so the same staged dispatch dir can
    # be re-scored against different source subsets without re-staging.
    if source != "all":
        fixtures_by_id = {
            fid: f
            for fid, f in fixtures_by_id.items()
            if f.get("source", "synthetic") == source
        }

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
    # Track fixture ids in the live evals.json (pre-filter) for distinguishing
    # "filtered-out" (skip silently) from "deleted-from-evals" (fatal).
    _all_evals_ids = {f["id"] for f in _evals_list}
    for entry in manifest["trials"]:
        seq = entry["seq"]
        fid = entry["fixture_id"]
        fix = fixtures_by_id.get(fid)
        if fix is None:
            # Task 10: if the fixture exists in evals.json but was filtered out
            # via --source, skip silently. Only fail-loud if the fixture is
            # missing entirely (deleted between stage and score).
            if source != "all" and fid in _all_evals_ids:
                continue
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
    # QG R1 Fix 2: honor manifest's trials_override header (if set) as the
    # canonical n_trials per fixture, not the evals.json replicate_rule. Falls
    # back to per-fixture manifest-trial count when no override was recorded
    # (e.g. legacy manifests). Threshold is clamped against the actual N.
    manifest_trials_override = manifest.get("trials_override")
    fixture_results: list[dict] = []
    for fid, trials_list in by_fixture.items():
        fix = fixtures_by_id[fid]
        trials_list.sort(key=lambda t: t[0])
        reviewer_outputs = [out for _, _, out in trials_list]
        rule = fix.get("replicate_rule", {"trials": 1, "threshold": 1})
        if manifest_trials_override is not None:
            n_trials = manifest_trials_override
        else:
            # Count actual trial entries the manifest staged for this fixture
            n_trials = len(trials_list) or rule.get("trials", 1)
        threshold = rule.get("threshold", 1)
        if threshold > n_trials:
            threshold = n_trials  # clamp
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

    # Task 11 (#290 S3): grouped emission block.
    # by_source + drift_delta + per_trial_rates derived from fixture_results
    # using the three-state PASS/FAIL/ERROR classifier (R1 M4 / R3 SP1).
    # lens_column=='none' fixtures contribute zero to any lens column (R1 S6).
    grouped = _compute_grouped_summary(fixture_results, fixtures_by_id)
    payload["by_source"] = grouped["by_source"]
    payload["drift_delta"] = grouped["drift_delta"]
    payload["per_trial_rates"] = grouped["per_trial_rates"]

    # Stdout grouped summary (Task 11 Step 1).
    print(_render_grouped_summary(grouped["by_source"]))

    # F1 / S-FE-5 R3: per-iter outputs under .calibrate-state/ (blanket-gitignored)
    out_path = _resolve_output_path(run_id, per_iter=per_iter)
    if per_iter:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"[info] writing per-iter output to {out_path} (gitignored via .calibrate-state/)",
            file=sys.stderr,
        )
    # QG R2 Fix 1: atomic write — prevents truncated last_run/per-iter on SIGINT/OOM/disk-full
    _atomic_write_text(out_path, json.dumps(payload, indent=2))

    # #291 Task 3: append one lens-health history record per CANONICAL run.
    # Gated on `not per_iter`: per-iter writes target .calibrate-state/ (one per
    # calibration baseline_runs iteration) and must NOT be logged as runs — they
    # would contaminate the trend series + the N-run sunset window. Telemetry is
    # advisory and must never gate: a history-write failure logs [warn] to stderr
    # and leaves score()'s return code unchanged.
    if not per_iter:
        try:
            _append_history(run_id, payload["run_at"], grouped, source)
        except Exception as e:  # noqa: BLE001 — telemetry must not gate score()
            print(f"[warn] lens-health history append failed: {e}", file=sys.stderr)

    # --write-baseline + --compare-baseline — see Task 8 (stubs raise NotImplementedError)
    if write_baseline:
        _write_baseline(payload, current_template_sha)
    if compare_baseline:
        # QG R3 Fix 1: fixture-set drift must be checked against the LIVE evals.json
        # keyset, not against the (possibly-filtered) manifest payload. A scoped
        # `stage R-x --fixture foo-id` run followed by `score R-x --compare-baseline`
        # against a full-scope baseline would previously trigger false rc=2 "removed
        # from baseline" for every fixture not in the subset. The correct threat model
        # is: was a fixture DELETED from evals.json? We detect that here using
        # fixtures_by_id (already loaded above from _EVALS_JSON) and pass the keyset
        # into _compare_baseline so it can operate on the manifest-scope intersection.
        if _BASELINE_PATH.exists():
            try:
                _base_data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
                _base_ids = {f["id"] for f in _base_data.get("fixtures", [])}
                _evals_ids = set(fixtures_by_id.keys())
                _removed = _base_ids - _evals_ids
                _added = _evals_ids - _base_ids
                if _removed:
                    print(
                        f"[warn] fixture-set drift: removed from evals.json: {sorted(_removed)}",
                        file=sys.stderr,
                    )
                if _added:
                    print(
                        f"[warn] fixture-set drift: added to evals.json since baseline: {sorted(_added)}",
                        file=sys.stderr,
                    )
                if _removed and not allow_fixture_drift:
                    print(
                        "[fatal] baseline regression-check refuses removed fixtures "
                        "without --allow-fixture-drift",
                        file=sys.stderr,
                    )
                    return 2
            except (json.JSONDecodeError, OSError):
                pass  # malformed baseline handled inside _compare_baseline
        return _compare_baseline(
            payload,
            current_template_sha,
            incomplete=incomplete,
            evals_fixture_ids=set(fixtures_by_id.keys()),
            allow_fixture_drift=allow_fixture_drift,
        )

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
# #291 Task 4: lens-health report subcommand (advisory; never gates)
# ---------------------------------------------------------------------------


def report(
    window: int = 5,
    sunset_threshold: float = 0.70,
    history_path: Path | None = None,
) -> int:
    """#291 Task 4: print a per-lens real-PR pass-rate trend + advisory SUNSET?.

    Read-only; ALWAYS returns 0. Loads history.jsonl, filters to QUALIFYING runs
    (records carrying real-PR data — source in {"all", "real-pr"}; source ==
    "synthetic" records are skipped so they never consume a window slot), takes the last
    `window` qualifying records, and renders a fixed-width table to stdout: one
    row per lens (Surgical/DRY/SRP/OCP, from _LENS_COLUMN_VALUES minus "none"),
    one column per qualifying windowed run, a `mean` column (over non-null runs),
    and a `SUNSET?` column.

    SUNSET? fires only when the lens has real-PR data in ALL `window` qualifying
    runs AND every such rate is < sunset_threshold; otherwise the cell shows
    `n/a (need {window} runs)`. The need-N guard fires on the PER-LENS-PRESENT
    qualifying-run count, not the raw record count. Prints `no history yet` and
    returns 0 when the file is absent/empty or has no qualifying runs.
    """
    # Clamp non-positive window to 1: window==0 makes qualifying[-0:] select the
    # WHOLE list and `len(present) >= 0` is always True, firing a false SUNSET on
    # lenses with zero real-PR data; window<0 left-trims. Report is advisory and
    # always returns 0, so clamp (not hard-error) and warn.
    if window < 1:
        print(f"[warn] non-positive window {window} clamped to 1", file=sys.stderr)
        window = 1

    if history_path is None:
        history_path = _resolve_history_path()

    if not history_path.exists():
        print("no history yet")
        return 0

    records: list[dict] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Filter to qualifying runs: carry real-PR data. source == "all" and
    # source == "real-pr" qualify (a real-pr-scoped score run carries per-lens
    # real-PR rates); source == "synthetic" never consumes a window slot.
    qualifying = [r for r in records if r.get("source") in ("all", "real-pr")]
    if not qualifying:
        print("no history yet")
        return 0

    windowed = qualifying[-window:]
    lens_cols = tuple(v for v in _LENS_COLUMN_VALUES if v != "none")

    # Per-lens real-PR rate series across the windowed qualifying runs.
    def _rate(rec: dict, lens: str):
        return ((rec.get("per_lens") or {}).get(lens) or {}).get("real-pr")

    # Column widths.
    n_cols = len(windowed)
    cell_w = 7  # fits "1.00" / "n/a"
    lens_w = max((len(l) for l in lens_cols), default=8)
    lens_w = max(lens_w, len("lens"))

    def _fmt_rate(v) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) else "n/a"

    # Header
    header = "lens".ljust(lens_w)
    for i in range(n_cols):
        header += " | " + f"r{i + 1}".rjust(cell_w)
    header += " | " + "mean".rjust(cell_w) + " | " + "SUNSET?"
    print(f"lens-health trend (last {n_cols} qualifying real-PR run(s), "
          f"sunset<{sunset_threshold:.2f} across full window of {window})")
    print(header)
    print("-" * len(header))

    for lens in lens_cols:
        series = [_rate(rec, lens) for rec in windowed]
        present = [v for v in series if isinstance(v, (int, float))]
        row = lens.ljust(lens_w)
        for v in series:
            row += " | " + _fmt_rate(v).rjust(cell_w)
        mean_val = (sum(present) / len(present)) if present else None
        row += " | " + (_fmt_rate(mean_val)).rjust(cell_w)

        # SUNSET? only when lens has real-PR data in ALL `window` qualifying
        # runs AND every rate < threshold. Guard fires on per-lens-present count.
        if len(present) >= window and all(v < sunset_threshold for v in present):
            sunset_cell = "SUNSET"
        else:
            sunset_cell = f"n/a (need {window} runs)"
        row += " | " + sunset_cell
        print(row)

    return 0


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
    sp_stage.add_argument("--source", choices=list(_SOURCE_VALUES), default="all")
    sp_stage.add_argument("--fixture", default=None)
    sp_stage.add_argument("--trials-override", type=int, default=None)
    sp_stage.add_argument("--timeout", type=int, default=300)
    # Task 8 (#290 F2 / gate (j)): opt-in `git cat-file -e` per source_pr sha.
    # Off by default — gate (j) does not invoke any `git rev-parse` /
    # `git cat-file` subprocess unless this flag is present.
    sp_stage.add_argument("--strict-source-pr", action="store_true",
        help="(#290 gate j) require every real-PR fixture's source_pr SHA to "
             "exist in the current git repo. Default OFF.")

    # score — Task 6
    sp_score = sub.add_parser("score", help="Aggregate results + write last_run.json")
    sp_score.add_argument("run_id")
    sp_score.add_argument("--write-baseline", action="store_true")
    sp_score.add_argument("--compare-baseline", action="store_true")
    sp_score.add_argument("--force-rescore", action="store_true")
    sp_score.add_argument("--allow-incomplete", action="store_true")
    sp_score.add_argument("--allow-fixture-drift", action="store_true",
        help="Permit --compare-baseline when fixtures have been removed from evals.json. "
             "Without this flag, removed fixtures cause rc=2 (prevents silent regression-laundering).")
    sp_score.add_argument("--per-iter", action="store_true",
        help="Write last_run-<run_id>.json under .calibrate-state/ instead of shared last_run.json. Set by /temper-eval-calibrate.")
    # Task 10 (#290): score-time --source filter. Limits scoring to fixtures
    # matching the given source (synthetic | real-pr | all). Default "all"
    # preserves prior behavior. Score-time filter is orthogonal to stage-time
    # --source; staged trials for filtered-out fixtures are simply skipped.
    sp_score.add_argument("--source", choices=list(_SOURCE_VALUES), default="all",
        help="Limit scoring to fixtures with this source (synthetic | real-pr | all). Default: all.")
    # Task 2 (#290 S1): writes a placeholder calibration.json header in-place
    # if missing. Actually computing empirical sigmas requires the 3-step
    # protocol (stage / /temper-eval-collect / score, k=3) followed by running
    # `scripts/calibrate_tolerance.py` against the k last_run.json artifacts.
    # See scripts/calibrate_tolerance.py for the full reproducible flow.
    sp_score.add_argument("--write-calibration", action="store_true",
        help="(#290 S1) emit a placeholder calibration.json header if absent. "
             "Full calibration is computed by scripts/calibrate_tolerance.py "
             "after k=3 baseline runs via the 3-step protocol.")

    # report — #291 Task 4 (advisory lens-health trend; always exits 0)
    sp_report = sub.add_parser(
        "report", help="Print per-lens real-PR pass-rate trend + advisory SUNSET? flag"
    )
    sp_report.add_argument("--window", type=int, default=5,
        help="Number of most-recent qualifying runs in the trend window (default 5).")
    sp_report.add_argument("--sunset-threshold", type=float, default=0.70,
        help="Real-PR pass-rate below which a lens is flagged for sunset across the full window (default 0.70).")
    sp_report.add_argument("--history", default=None,
        help="Path to history.jsonl (overridable for test isolation).")

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
                strict_source_pr=args.strict_source_pr,
            )
            return 0
        except (FileExistsError, ValueError, FixtureValidationError) as e:
            print(f"[fatal] {e}", file=sys.stderr)
            return 2

    if args.cmd == "score":
        try:
            rc = score(
                args.run_id,
                write_baseline=args.write_baseline,
                compare_baseline=args.compare_baseline,
                force_rescore=args.force_rescore,
                allow_incomplete=args.allow_incomplete,
                per_iter=args.per_iter,
                allow_fixture_drift=args.allow_fixture_drift,
                source=args.source,
            )
        except ValueError as e:
            print(f"[fatal] {e}", file=sys.stderr)
            return 2
        # Task 2 (#290 S1): --write-calibration emits a placeholder header if
        # calibration.json is absent. Runs after score() so a fatal score does
        # not silently bypass calibration writeout.
        if getattr(args, "write_calibration", False):
            wrote = _write_calibration_placeholder()
            if wrote:
                print(
                    f"[info] wrote placeholder calibration at {_CALIBRATION_PATH}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[info] calibration.json already present at {_CALIBRATION_PATH}; "
                    f"not overwriting",
                    file=sys.stderr,
                )
        return rc

    if args.cmd == "report":
        return report(
            window=args.window,
            sunset_threshold=args.sunset_threshold,
            history_path=Path(args.history) if args.history else None,
        )

    # Legacy mock/replay path — preserved unchanged
    return _legacy_main(args)


def _legacy_main(args: argparse.Namespace) -> int:
    # Load fixtures via the shared `_load_evals` path so any top-level
    # global_expectations are folded into each eval identically to stage/score.
    try:
        fixtures, _global_expectations = _load_evals(_EVALS_JSON)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[fatal] cannot load evals.json: {e}", file=sys.stderr)
        return 2
    try:
        _validate_global_expectations(_global_expectations)
    except FixtureValidationError as e:
        print(f"[fatal] {e}", file=sys.stderr)
        return 2

    if args.legacy_fixture:
        fixtures = [f for f in fixtures if f["id"] == args.legacy_fixture]
        if not fixtures:
            print(f"[fatal] no fixture with id {args.legacy_fixture!r}", file=sys.stderr)
            return 2

    # Resolve mode
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
            mock_dir=mock_dir,
            replay_outputs=replay_outputs,
            trials_override=args.legacy_trials_override,
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
    # QG R2 Fix 2: route via _resolve_output_path() to mirror score() — honors
    # TEMPER_LAST_RUN_OVERRIDE set after import AND uses the current _EVALS_DIR
    # (monkeypatchable in tests). Eliminates legacy-vs-score asymmetry.
    try:
        # Legacy invocation has no user-provided run-id; literal "legacy" steers env-override path,
        # never reaches the per-iter branch where run_id is used in the path. Validation intentionally skipped.
        out_path = _resolve_output_path("legacy", per_iter=False)
        _atomic_write_text(out_path, json.dumps(payload, indent=2, default=str))
    except OSError as e:
        print(f"[warn] cannot write last_run.json: {e}", file=sys.stderr)

    # Exit code
    if any(fr["verdict"] == "FAIL" for fr in fixture_results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
