#!/usr/bin/env python3
"""Inquisitor fan-out eval harness — `stage` + `score` (#424).

Mirrors temper's module *layout* (D5): `_REPO_ROOT` / `_EVALS_DIR` /
`_EVALS_JSON`, package-relative helper imports, `if __name__ == "__main__":
sys.exit(main())`. Invoked as a module from repo root:

    python3 -m skills.inquisitor.evals.run_evals stage <run-id> [--trials N] [--fixture ID]
    python3 -m skills.inquisitor.evals.run_evals score <run-id> [--allow-incomplete]

`stage` renders the three-arm dispatch files (WITH = 5 dimension subagents + 1
aggregation subagent; MID = 1 all-lenses subagent; WITHOUT = 1 neutral subagent)
per fixture×trial, plus the two shared deterministic prompt files
(`aggregation-prompt.md`, `judge-prompt.md`), and writes `stage-manifest.json`.
There is no `collect` subcommand — collect is the live orchestrator procedure
documented in README.md. `score` reads the judge verdict files and computes the
three paired deltas (see the `score` section, added in build-order step 5).

Phase 1 only: identification breadth, execution stubbed. See the gated design
`docs/plans/2026-06-13-inquisitor-fanout-eval-harness-design.md`.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import math
import re
import shutil
import statistics
import sys
from pathlib import Path

from ._dispatch_paths import fixture_sha, resolve_dispatch_dir, template_sha
from ._runid import validate_run_id

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVALS_DIR = Path(__file__).resolve().parent
_EVALS_JSON = _EVALS_DIR / "evals.json"
_DIM_TEMPLATE = _EVALS_DIR / "inquisitor-dimension-prompt-eval.md"
_AGG_PROMPT = _EVALS_DIR / "aggregation-prompt.md"
_JUDGE_PROMPT = _EVALS_DIR / "judge-prompt.md"

# The WITHOUT-arm neutral instruction (design L143). The source-of-truth constant;
# `stage` writes it (plus the fixture diff) to the staged WITHOUT dispatch.
WITHOUT_PROMPT = (
    "Review this diff for cross-component bugs. List each issue you find with a "
    "specific proposed fix or test."
)

# The 5 dimension lens titles — the literal set the Dimension Reference parse must
# yield (S3: count alone is defeatable; the literal-title-set assertion is not).
DIMENSION_TITLES = ["Wiring", "Integration", "Edge Cases",
                    "State & Lifecycle", "Regression"]

_DEFAULT_TRIALS = 5  # decision-run default (design "Cost envelope")

# S-2 guard: a rendered WITH dispatch must carry NO residual [DIMENSION_*] slot.
# Scoped to the [DIMENSION_*] slot class ONLY (NOT arbitrary [...] tokens): the
# preserved Report-Format markers ([Title], [what to change...]) and bracket tokens
# inside the embedded fixture diff (fixture-3's [data.length - 1]) are expected.
_DIMENSION_SLOT_RE = re.compile(r"\[DIMENSION_[A-Z_]*\]")

# S1: a unique non-printable sentinel that stands in for the [PASTE: git diff …]
# slot WHILE _validate_rendered_prompt scans the slot-filled template. The validator
# must run on the slot-filled template BEFORE the fixture diff is embedded — a future
# fixture diff legitimately containing a `[DIMENSION_*]`- or `[PASTE:`-shaped token
# (plausible in a JS/TS or dispatch/template code-review fixture) would otherwise
# false-trip the validator and crash stage. The git-diff slot is itself a `[PASTE:`
# token, so it cannot simply be left in place during validation; it is consumed to
# this sentinel, validated around, then replaced LAST with the real diff via a literal
# str.replace (no backreference/escape interpretation — preserves S1's original
# guarantee). The NUL-wrapped marker cannot collide with any prompt or fixture byte.
_DIFF_SENTINEL = "\x00FIXTURE_DIFF\x00"
_DIFF_SLOT_RE = re.compile(r"\[PASTE: git diff[^\]]*\]")


# ---------------------------------------------------------------------------
# Dimension Reference parsing (the single lens source — D3)
# ---------------------------------------------------------------------------


def _dimension_reference_slice(template_text: str) -> str:
    """Return the text between the '## Dimension Reference' header and the next
    top-level '## ' header (or EOF). Scoping the lens parse to this slice (rather
    than a file-wide '### ' split) is the S3 mitigation."""
    m = re.search(r"^## Dimension Reference[ \t]*$", template_text, re.M)
    if not m:
        raise ValueError("template has no '## Dimension Reference' section")
    start = m.end()
    nxt = re.search(r"^## ", template_text[start:], re.M)
    return template_text[start: start + nxt.start()] if nxt else template_text[start:]


def parse_dimension_blocks(template_text: str) -> list:
    """Parse the Dimension Reference slice into exactly 5 (title, block_text)
    pairs in file order. block_text starts with the title line.

    Raises unless there are exactly 5 '### ' blocks AND their titles equal the
    literal set DIMENSION_TITLES (S3 — a header-count-preserving rewrite that nets
    5 headers with one non-dimension block is caught by the title-set assertion)."""
    sl = _dimension_reference_slice(template_text)
    raw = re.split(r"^### ", sl, flags=re.M)[1:]
    blocks = [(rb.splitlines()[0].strip(), rb) for rb in raw]
    titles = [t for t, _ in blocks]
    if len(blocks) != 5 or set(titles) != set(DIMENSION_TITLES):
        raise ValueError(
            f"Dimension Reference must have exactly 5 blocks titled "
            f"{DIMENSION_TITLES}; got {titles}"
        )
    return blocks


def extract_dimension_fields(title: str, block_text: str) -> dict:
    """Second parse layer (S-2): extract the WITH template's slot values from one
    '### <Dim>' block — name, core question, focus areas (label + nested bullets),
    test style."""
    lines = block_text.splitlines()
    question = teststyle = None
    focus_lines: list = []
    i = 1  # lines[0] is the title
    while i < len(lines):
        line = lines[i]
        if line.startswith("- **Core question:**"):
            question = line[len("- **Core question:**"):].strip().strip('"')
        elif line.startswith("- **Focus areas:**"):
            focus_lines = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                # nested bullets are indented; stop at the next top-level
                # "- **...:**" label or a blank line / block end.
                if re.match(r"^- \*\*", nxt) or nxt.strip() == "":
                    break
                focus_lines.append(nxt)
                j += 1
            i = j
            continue
        elif line.startswith("- **Test style:**"):
            teststyle = line[len("- **Test style:**"):].strip()
        i += 1
    focus = "\n".join(focus_lines)
    if not (question and focus and teststyle):
        raise ValueError(
            f"dimension {title!r} block is missing a Core question / Focus areas "
            f"/ Test style field"
        )
    return {"name": title, "question": question, "focus": focus,
            "teststyle": teststyle}


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

# S-3: every evals.json fixture `prompt` opens with the skill-naming lead-in
# "Run the inquisitor against this feature diff for …". Embedded raw, it would
# prime even the bare WITHOUT baseline with the methodology it is meant to lack —
# plausibly raising its floor and compressing WITH−WITHOUT toward zero (the
# false-green direction). The provenance build already neutralized this exact
# opener for the blind ground-truth author (ground-truth-bugs.provenance.md); the
# live measurement arms must get the SAME neutralization so the embedded fixture
# content is identical and skill-neutral across all three arms (the methodology
# difference comes only from the arm scaffold, not the fixture text).
_FIXTURE_OPENER = "Run the inquisitor against this feature diff for "
_FIXTURE_OPENER_NEUTRAL = "Feature under review: "


def _neutralize_fixture_opener(text: str) -> str:
    """Replace the leading skill-naming opener with the neutral provenance framing
    (anchored at the start only). Mirrors the provenance neutralization exactly:
    e.g. "Run the inquisitor against this feature diff for a new 'Scheduled
    Notifications' feature." → "Feature under review: a new 'Scheduled
    Notifications' feature." Leaves text without the opener untouched."""
    if text.startswith(_FIXTURE_OPENER):
        return _FIXTURE_OPENER_NEUTRAL + text[len(_FIXTURE_OPENER):]
    return text


def _template_region(template_text: str) -> str:
    """The WITH dimension template portion — everything before the Dimension
    Reference (which is only the lens source, not part of a dispatched prompt)."""
    m = re.search(r"^## Dimension Reference[ \t]*$", template_text, re.M)
    return template_text[:m.start()] if m else template_text


def _validate_rendered_prompt(rendered: str) -> None:
    """RAISE on any residual [DIMENSION_*] slot OR any residual `[PASTE:` token in a
    rendered WITH dimension / MID dispatch (S-2 + S1): a half-filled render fails
    loudly at stage time rather than dispatching a broken prompt. The `[PASTE:`
    guard catches any non-dimension placeholder block (e.g. a future template edit
    re-introducing a Project-Test-Conventions / Module-Context PASTE slot) that the
    [DIMENSION_*] scope alone would miss — the exact arm-asymmetric confound where
    WITH/MID carry a dangling unfulfillable PASTE instruction WITHOUT does not.

    NOTE: `render_with_aggregation` legitimately emits a `[PASTE: the 5 WITH
    dimension reports …]` collect-time slot filled live by the human collector; it
    does NOT route through this validator, and must not, or that slot would falsely
    trip this guard."""
    leftover = _DIMENSION_SLOT_RE.findall(rendered)
    if leftover:
        raise ValueError(
            f"rendered WITH dispatch has unfilled dimension slots: "
            f"{sorted(set(leftover))}"
        )
    if "[PASTE:" in rendered:
        raise ValueError(
            "rendered WITH/MID dispatch has a residual [PASTE: …] slot — every "
            "non-dimension placeholder must be filled or omitted at render time"
        )


def render_with_dimension(template_region: str, fields: dict, fixture: dict) -> str:
    """Fill the 5 [DIMENSION_*] slots for one dimension + embed the fixture diff."""
    r = template_region
    r = r.replace("[DIMENSION_NAME]", fields["name"])
    r = r.replace("[DIMENSION_QUESTION]", fields["question"])
    r = r.replace("[DIMENSION_FOCUS_AREAS]", fields["focus"])
    r = r.replace("[DIMENSION_TEST_STYLE]", fields["teststyle"])
    # Consume the "full feature diff" [PASTE: git diff …] slot with a sentinel
    # (regex avoids coupling to the em-dash in the slot text), THEN validate the
    # slot-filled template, THEN swap the sentinel for the real diff LAST (S1).
    # Validating before embedding ensures the guard scans only template/slot bytes —
    # never fixture bytes — so a fixture diff that happens to contain a
    # `[DIMENSION_*]`- or `[PASTE:`-shaped token cannot false-trip it; it still
    # catches a genuinely unfilled [DIMENSION_*] slot and any stray non-git-diff
    # [PASTE: slot. The sentinel is replaced via literal str.replace so the diff is
    # inserted LITERALLY — a regex replacement argument would interpret
    # backreferences/escapes (\1, \g<...>, \n) in the diff. The fixture opener is
    # neutralized first (S-3) so the embedded content is skill-neutral.
    r = _DIFF_SLOT_RE.sub(lambda _m: _DIFF_SENTINEL, r)
    _validate_rendered_prompt(r)
    diff = _neutralize_fixture_opener(fixture["prompt"])
    r = r.replace(_DIFF_SENTINEL, diff)
    return r


def render_with_aggregation(agg_text: str) -> str:
    """The WITH 6th aggregation dispatch — the shared aggregation framing
    (byte-identical substring, T3) + a slot for this cell's 5 dimension reports
    (produced at collect time)."""
    return (
        agg_text
        + "\n\n## The 5 dimension reports to aggregate\n\n"
        + "[PASTE: the 5 WITH dimension reports produced for this cell]\n"
    )


# The single-dimension lens block in the WITH procedural shell — from the
# "## Your Dimension:" header through the "**Test style:**" slot (4-space indented
# inside the template code fence). MID replaces this one-dimension block with an
# all-five-dimensions section; the surrounding procedural scaffold (persona, Steps,
# NOT-do, Report-Format) is kept verbatim so WITH−MID isolates only fan-out.
_MID_LENS_BLOCK_RE = re.compile(
    r"^[ \t]*## Your Dimension:.*?\*\*Test style:\*\* \[DIMENSION_TEST_STYLE\]",
    re.M | re.S,
)


def _all_lenses_section(blocks: list) -> str:
    """The MID replacement for the WITH single-dimension lens block: the same 5
    Dimension Reference blocks (the single lens source — D3) under an all-five
    header, 4-space indented to sit inside the template code fence."""
    body = "## All Five Dimensions\n\nApply every one of these five dimension lenses:\n\n"
    body += "\n".join("### " + b.rstrip() + "\n" for _t, b in blocks)
    # 4-space indent each line to match the surrounding code-fence body.
    return "\n".join(("    " + ln) if ln else ln for ln in body.splitlines())


def render_mid(blocks: list, agg_text: str, template_region: str,
               fixture: dict) -> str:
    """The MID dispatch — the SAME WITH per-dimension procedural shell
    (`_template_region`: relentless-hunter persona, the `## Your Job` steps,
    `## What You Must NOT Do`, `## Report Format`), but with the one-dimension lens
    block swapped for all 5 lenses and the residual single-dimension tokens
    neutralized to cross-dimension phrasing, plus the byte-identical WITH
    aggregation framing and the fixture diff. One sequential agent holds every lens.

    This holds the per-dimension procedural scaffold + lens content + aggregation
    framing CONSTANT with WITH; WITH−MID therefore varies ONLY the fan-out delivery
    mechanism (5 parallel fresh subagents vs 1 sequential agent), not the procedure.
    The lens text and the procedural text both come from `_template_region` /
    `blocks` — neither is duplicated as a string literal here (D3)."""
    r = template_region
    # Swap the single-dimension lens block for the all-five-dimensions section.
    r = _MID_LENS_BLOCK_RE.sub(lambda _m: _all_lenses_section(blocks), r, count=1)
    # Neutralize the remaining single-dimension tokens (persona line, Step 2,
    # Report header, code-fence description) to cross-dimension phrasing.
    r = r.replace("[DIMENSION_NAME]", "all five dimensions")
    # F1: rescope the WITH per-agent output budget to per-dimension / aggregate
    # scope. WITH's "3-5 vectors" / "top 3-5" / "no more than 5 tests" cap binds
    # each of 5 parallel agents independently (~25 total flow into aggregation); the
    # SAME string in MID binds the single all-dimensions agent (~5 total), capping
    # MID below WITH for reasons orthogonal to the fan-out mechanism WITH−MID
    # isolates. Rescope so MID's aggregate budget matches WITH's (~5 per dimension ×
    # 5 ≈ 25), and drop the now-incoherent single-lane line (an all-dimensions agent
    # cannot "stay in its lane"). Each replace is asserted to have fired (fail-loud,
    # consistent with _validate_rendered_prompt): an exact-substring no-op would
    # silently leave MID under-budgeted.
    _rescope = [
        ("**Identify 3-5 attack vectors** specific to your dimension.",
         "**Identify 3-5 attack vectors per dimension (up to ~25 total)** "
         "specific to each of the five dimensions."),
        ("Select your top 3-5.",
         "Select your top 3-5 per dimension (up to ~25 total)."),
        ("- Do NOT describe more than 5 tests",
         "- Do NOT describe more than 5 tests per dimension"),
        ("- Do NOT attack vectors that belong to a different dimension — stay in\n"
         "      your lane",
         "- Cross-dimension reasoning is expected — you hold every lens"),
    ]
    for old, new in _rescope:
        if old not in r:
            raise ValueError(
                f"render_mid budget-rescope substring not found verbatim in the "
                f"rendered MID prompt (silent no-op would under-budget MID vs "
                f"WITH): {old!r}"
            )
        r = r.replace(old, new)
    # Consume the same [PASTE: git diff …] slot WITH uses with a sentinel (NOT the
    # real diff yet — S1), opener neutralized identically to WITH/WITHOUT (S-3).
    r = _DIFF_SLOT_RE.sub(lambda _m: _DIFF_SENTINEL, r)
    # Append the byte-identical WITH aggregation framing AROUND the sentinel.
    r = r.rstrip() + "\n\n## Aggregation\n\n" + agg_text + "\n"
    # Validate the fully-assembled template (persona + all-five lens + rescope +
    # appended agg framing) with the git-diff slot sentinel-consumed, BEFORE the
    # fixture diff is embedded — so the guard never scans fixture bytes (S1). This
    # still catches a genuinely unfilled [DIMENSION_*] slot, any stray non-git-diff
    # [PASTE: slot, AND a future agg-prompt edit that reintroduced such a slot.
    _validate_rendered_prompt(r)
    # Swap the sentinel for the real diff LAST via literal str.replace (no
    # backreference/escape interpretation of the diff — S1).
    diff = _neutralize_fixture_opener(fixture["prompt"])
    r = r.replace(_DIFF_SENTINEL, diff)
    return r


def render_without(fixture: dict) -> str:
    """The WITHOUT dispatch — the neutral instruction + the fixture diff (skill
    opener neutralized — S-3, identical to WITH/MID)."""
    return (WITHOUT_PROMPT + "\n\n## Diff\n\n"
            + _neutralize_fixture_opener(fixture["prompt"]))


# ---------------------------------------------------------------------------
# stage()
# ---------------------------------------------------------------------------


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _load_fixtures() -> list:
    data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    return data["evals"]


def stage(run_id: str, *, trials: int = _DEFAULT_TRIALS,
          fixture: int | str | None = None, force: bool = False) -> Path:
    """Render the three-arm dispatch files + the two shared prompt files; write
    stage-manifest.json. Returns the dispatch directory path."""
    validate_run_id(run_id)
    if trials < 1:
        raise ValueError(f"--trials must be >= 1 (got {trials})")

    fixtures = _load_fixtures()
    if fixture is not None:
        fixtures = [f for f in fixtures if str(f["id"]) == str(fixture)]
        if not fixtures:
            raise ValueError(f"--fixture {fixture!r} not found in evals.json")
    for f in fixtures:
        if not f.get("prompt", "").strip():
            raise ValueError(f"fixture {f.get('id')!r} has an empty diff/prompt")

    template_text = _DIM_TEMPLATE.read_text(encoding="utf-8")
    blocks = parse_dimension_blocks(template_text)            # validates 5 + titles
    region = _template_region(template_text)
    agg_text = _AGG_PROMPT.read_text(encoding="utf-8")
    fields_by_title = {t: extract_dimension_fields(t, b) for t, b in blocks}

    dispatch_dir = resolve_dispatch_dir(run_id)
    if dispatch_dir.exists():
        if not force:
            raise FileExistsError(
                f"dispatch dir {dispatch_dir} already exists; pass force=True"
            )
        shutil.rmtree(dispatch_dir)
    dispatch_dir.mkdir(parents=True)

    # Two shared deterministic prompt files (S4): byte-identical across all
    # arms/cells, hashed so the invariant is machine-checkable.
    (dispatch_dir / "aggregation-prompt.md").write_text(agg_text, encoding="utf-8")
    judge_text = _JUDGE_PROMPT.read_text(encoding="utf-8")
    (dispatch_dir / "judge-prompt.md").write_text(judge_text, encoding="utf-8")

    ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cells: list = []
    for fix in fixtures:
        fsha = fixture_sha(fix)
        for trial in range(1, trials + 1):
            stem = f"f{fix['id']}-t{trial}"
            # WITH: 5 dimension dispatches + 1 aggregation dispatch
            with_files = []
            for n, (title, block) in enumerate(blocks, 1):
                fname = f"{stem}-with-dim{n}-{_slug(title)}.md"
                rendered = render_with_dimension(region, fields_by_title[title], fix)
                (dispatch_dir / fname).write_text(rendered, encoding="utf-8")
                with_files.append(fname)
            agg_fname = f"{stem}-with-agg.md"
            (dispatch_dir / agg_fname).write_text(
                render_with_aggregation(agg_text), encoding="utf-8")
            with_files.append(agg_fname)
            cells.append({
                "fixture_id": fix["id"], "trial": trial, "arm": "with",
                "dispatch_files": with_files,
                "result_file": f"{stem}-with-verdicts.jsonl",
                "fixture_sha": fsha,
            })
            # MID: 1 all-lenses dispatch
            mid_fname = f"{stem}-mid.md"
            (dispatch_dir / mid_fname).write_text(
                render_mid(blocks, agg_text, region, fix), encoding="utf-8")
            cells.append({
                "fixture_id": fix["id"], "trial": trial, "arm": "mid",
                "dispatch_files": [mid_fname],
                "result_file": f"{stem}-mid-verdicts.jsonl",
                "fixture_sha": fsha,
            })
            # WITHOUT: 1 neutral dispatch
            wo_fname = f"{stem}-without.md"
            (dispatch_dir / wo_fname).write_text(
                render_without(fix), encoding="utf-8")
            cells.append({
                "fixture_id": fix["id"], "trial": trial, "arm": "without",
                "dispatch_files": [wo_fname],
                "result_file": f"{stem}-without-verdicts.jsonl",
                "fixture_sha": fsha,
            })

    manifest = {
        "run_id": run_id,
        "stage_timestamp": ts,
        "trials": trials,
        "fixtures": len(fixtures),
        "judge_model": "opus",
        "template_shas": {
            "dimension_eval": template_sha(_DIM_TEMPLATE),
            "aggregation": template_sha(_AGG_PROMPT),
            "judge": template_sha(_JUDGE_PROMPT),
        },
        "shared_files": ["aggregation-prompt.md", "judge-prompt.md"],
        "cells": cells,
    }
    (dispatch_dir / "stage-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return dispatch_dir


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------

_EPS = 0.05           # beyond_spread magnitude floor (design "Statistical power")
_Z = 1.96             # fixed no-α constant for mde_heuristic (F2)
_ARMS = ("with", "mid", "without")

# S-1: the documented secondary pool — 27 total evals.json expectations minus the
# single fixture-1 #8 exclusion = 26. This is a DIAGNOSTIC reconciliation anchor
# only; score derives graded_expectations from observed records (round-3 decision)
# and never gates on it. The static drift guard for these two 26s lives in
# scripts/check_inquisitor_secondary_count.py (DOCUMENTED_SECONDARY).
_CONTRACTED_SECONDARY_POOL = 26


def _ground_truth_path() -> Path:
    """Resolved at CALL time from _EVALS_DIR (F1) — NOT a module-load constant, so
    a test patching _EVALS_DIR actually redirects this read."""
    return _EVALS_DIR / "ground-truth-bugs.json"


def _rate(passes: int, total: int) -> float:
    return passes / total if total else 0.0


def _majority_pass(outcomes: list) -> bool:
    """Strict-majority collapse across trials; an even-N tie resolves to FAIL (M1)."""
    return sum(1 for o in outcomes if o) * 2 > len(outcomes)


def _parse_verdict_file(path: Path) -> tuple:
    """Return ({(tag, id): passed_bool}, malformed_line_count, dispatch_failed).

    A line that fails to parse or carries a non-PASS/FAIL verdict is counted
    malformed and skipped (its item is then absent → graded FAIL by the caller,
    per the design's malformed-verdict rule + S2).

    Mirrors temper's `_parse_result_file` sentinel handling (surgical, not a
    wholesale copy): the README collect contract writes each result_file using the
    `DISPATCH_STATUS: OK\\n\\n<body>` dispatch-health sentinel. If the first
    non-blank line is that sentinel it is consumed (NOT counted malformed) and the
    JSONL body parses as today. A `DISPATCH_STATUS: ERROR` first line — or an `OK`
    sentinel followed by an empty/whitespace body — is a dispatch failure
    (`dispatch_failed=True`, no parsed records) so S-1's guard can refuse on it.
    Backward-compatible: a file with NO `DISPATCH_STATUS:` sentinel (pure JSONL, as
    the unit tests write) parses exactly as before."""
    parsed: dict = {}
    malformed = 0
    if not path.exists():
        return parsed, malformed, False
    lines = path.read_text(encoding="utf-8").splitlines()

    # Consume an optional leading DISPATCH_STATUS: sentinel (only the first
    # non-blank line is inspected, so a literal "DISPATCH_STATUS:" substring inside
    # a later JSONL body cannot collide). The body is the remaining lines.
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].lstrip().startswith("DISPATCH_STATUS:"):
        sentinel = lines[idx].lstrip()
        if sentinel.startswith("DISPATCH_STATUS: ERROR"):
            return parsed, malformed, True
        if not sentinel.startswith("DISPATCH_STATUS: OK"):
            # Malformed sentinel — treat as a dispatch failure (no claim on body).
            return parsed, malformed, True
        body_lines = lines[idx + 1:]
        if not any(ln.strip() for ln in body_lines):
            # OK sentinel but empty/whitespace body → dispatch failure.
            return parsed, malformed, True
        lines = body_lines

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            tag, vid, verdict = rec["tag"], rec["id"], rec["verdict"]
            if verdict not in ("PASS", "FAIL"):
                raise ValueError("bad verdict value")
            if tag not in ("primary", "secondary"):
                raise ValueError("bad tag value")
        except Exception:
            malformed += 1
            continue
        parsed[(tag, vid)] = (verdict == "PASS")
    return parsed, malformed, False


def _mde_heuristic(per_trial_deltas: list) -> float | None:
    """1.96 × sample-stdev(per-trial paired deltas, ddof=1) / sqrt(trials); null
    when trials < 2 (SE undefined). An explicitly no-α noise-floor figure (F2)."""
    n = len(per_trial_deltas)
    if n < 2:
        return None
    return _Z * statistics.stdev(per_trial_deltas) / math.sqrt(n)


def _beyond_spread(per_trial_deltas: list, mean: float) -> bool:
    """True iff the per-trial band excludes zero AND |mean| >= ε. Forced False for
    trials < 3 (S2): a 1-2 trial band is a degenerate point/pair that trivially
    excludes zero — the very re-run noise the band exists to bound."""
    if len(per_trial_deltas) < 3:
        return False
    lo, hi = min(per_trial_deltas), max(per_trial_deltas)
    excludes_zero = lo > 0 or hi < 0
    return excludes_zero and abs(mean) >= _EPS


def _delta_block(a_rates: list, b_rates: list, *, with_beyond: bool) -> dict:
    """Paired-delta block from two arms' per-trial rate lists (index-matched).
    `paired` = mean of per-trial paired deltas (M-b), NOT a majority-rate diff."""
    deltas = [a - b for a, b in zip(a_rates, b_rates)]
    paired = statistics.mean(deltas) if deltas else 0.0
    block = {
        "paired": paired,
        "trial_spread": [min(deltas), max(deltas)] if deltas else [0.0, 0.0],
        "mde_heuristic": _mde_heuristic(deltas),
    }
    if with_beyond:
        block["beyond_spread"] = _beyond_spread(deltas, paired)
    return block


def score(run_id: str, *, allow_incomplete: bool = False) -> int:
    """Read stage-manifest.json + judge verdict files; compute the three paired
    deltas + diagnostics; write last_run.json + results.md. Returns an exit code."""
    validate_run_id(run_id)
    dispatch_dir = resolve_dispatch_dir(run_id)
    manifest_path = dispatch_dir / "stage-manifest.json"
    if not manifest_path.exists():
        print(f"[fatal] no stage-manifest.json at {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # .collect-status gating (test 5): refuse without it unless --allow-incomplete.
    status_file = dispatch_dir / ".collect-status"
    if not status_file.exists() and not allow_incomplete:
        print(f"[fatal] no .collect-status in {dispatch_dir}; collect is "
              f"incomplete (pass --allow-incomplete for a smoke/debug score)",
              file=sys.stderr)
        return 1
    complete = not allow_incomplete

    cells = manifest["cells"]
    trials = manifest["trials"]
    fixtures_in_run = sorted({c["fixture_id"] for c in cells})

    # Ground-truth bug list (call-time read, F1) → per-fixture bug ids + off_axis.
    gt = json.loads(_ground_truth_path().read_text(encoding="utf-8"))
    gt_fixture_ids = {f["id"] for f in gt["fixtures"]}

    # Coverage guard (S1): every staged run fixture MUST be covered by ground-truth,
    # and the resulting graded-bug pool must be non-empty. Without this, a
    # misconfigured run (manifest stages fixture 1, GT lists only fixture 99 → K=0)
    # or a partial-coverage run (GT covers only a subset of staged fixtures, silently
    # dropping the rest from K) false-greens as a clean "no methodology effect" null
    # with complete:true. Assert BEFORE computing any rates / writing last_run.json.
    uncovered = [fid for fid in fixtures_in_run if fid not in gt_fixture_ids]
    if uncovered:
        print(f"[fatal] staged run fixtures {uncovered} are absent from "
              f"ground-truth ({sorted(gt_fixture_ids)}); refusing to score a "
              f"partially-covered run (it would silently drop those fixtures and "
              f"false-green as a null result)", file=sys.stderr)
        return 1

    bugs_by_fixture: dict = {}
    bug_off: dict = {}
    for f in gt["fixtures"]:
        if f["id"] not in fixtures_in_run:
            continue
        for b in f["bugs"]:
            bugs_by_fixture.setdefault(f["id"], []).append(b["bug_id"])
            bug_off[b["bug_id"]] = bool(b["off_axis"])
    all_bugs = [b for fid in fixtures_in_run for b in bugs_by_fixture.get(fid, [])]
    K = len(all_bugs)
    if K == 0:
        print(f"[fatal] graded-bug pool is empty (K=0) for staged fixtures "
              f"{fixtures_in_run}; ground-truth lists no bugs for them — refusing "
              f"to score (all deltas would be 0.0, false-greening as a clean null)",
              file=sys.stderr)
        return 1

    # Parse every cell's verdicts.
    # primary[arm][fid][trial] = {bug_id: passed}; secondary[arm][fid][trial] = {sid: passed}
    primary: dict = {a: {} for a in _ARMS}
    secondary: dict = {a: {} for a in _ARMS}
    malformed: dict = {a: 0 for a in _ARMS}
    secondary_universe: set = set()  # (fid, sid)
    total_parsed = 0                 # S-1: union of parsed records across all cells
    bad_cells: list = []             # S-1: cells with missing/empty/failed result_file
    undergraded_cells: list = []     # F-1/S-1: (rf, gt-matched primary, K) under budget
    for c in cells:
        arm, fid, trial = c["arm"], c["fixture_id"], c["trial"]
        result_path = dispatch_dir / c["result_file"]
        parsed, mal, dispatch_failed = _parse_verdict_file(result_path)
        # A cell is "bad" iff its result_file is MISSING, EMPTY (no content lines),
        # or a DISPATCH_STATUS dispatch failure (S-1 ∩ S-2). A present non-empty file
        # whose lines are all malformed is NOT bad — the judge ran and emitted
        # garbage; that is a real (mal-counted, FAIL-by-absence) collection, distinct
        # from "didn't collect" (which is what this guard refuses).
        is_empty = not result_path.exists() or not result_path.read_text(
            encoding="utf-8").strip()
        if is_empty or dispatch_failed:
            bad_cells.append(c["result_file"])
        # F-1: a present, non-empty, non-dispatch-failed cell can still UNDER-emit
        # its primary records — fewer than the fixture's ground-truth primary count.
        # The omitted bugs all default to FAIL-by-absence in every arm equally, so
        # the deltas collapse to 0.0 and the run false-greens as a clean null. Count
        # emitted records toward the primary budget (parsed primary records + this
        # cell's malformed lines, giving untaggable garbage the benefit of the doubt
        # so the round-5 malformed-but-present contract is preserved). A short cell
        # under-emitted.
        #
        # S-1 (id-matched budget): count only primary records whose id is a member of
        # this fixture's ground-truth bug_id set. A judge that echoes well-formed
        # primary records under DRIFTED ids (e.g. bug-1 instead of f1-b1) parses
        # cleanly (mal=0) but every ground-truth bug is looked up by id and found
        # absent → FAIL-by-absence in all arms equally → deltas collapse to 0.0 with
        # complete:true, rc 0, malformed 0. Anchoring the count to gt_ids makes
        # drifted (and cross-fixture, M4) ids stop satisfying the budget; extra
        # hallucinated ids are harmless (the blind-anchored K ignores them, so only
        # missing/drifted ids reduce the matched count). Malformed lines still count
        # toward the budget (round-5 contract preserved). gt_match records how many of
        # the budget the matched ids cover, for the operator diagnostic below.
        else:
            gt_ids = set(bugs_by_fixture.get(fid, []))
            prim_count = sum(
                1 for (tag, vid) in parsed if tag == "primary" and vid in gt_ids)
            if prim_count + mal < len(gt_ids):
                undergraded_cells.append((c["result_file"], prim_count, len(gt_ids)))
        total_parsed += len(parsed)
        malformed[arm] += mal
        primary[arm].setdefault(fid, {})[trial] = {
            vid: ok for (tag, vid), ok in parsed.items() if tag == "primary"}
        sec = {vid: ok for (tag, vid), ok in parsed.items() if tag == "secondary"}
        secondary[arm].setdefault(fid, {})[trial] = sec
        for sid in sec:
            secondary_universe.add((fid, sid))

    # Collection-presence guard (S-1): for a `complete` run (NOT --allow-incomplete),
    # the .collect-status flag is a content-free human-written stamp — it does not
    # prove any verdicts were collected. With every result_file missing/empty/failed,
    # every graded bug defaults to FAIL-by-absence and the run false-greens as a tidy
    # `complete:true` zero-delta "no methodology effect" null (the headline false-green
    # this harness exists to prevent). Mirror the K==0 / uncovered-fixture guards
    # exactly: fail loud BEFORE writing last_run.json, leaving no artifact behind.
    if complete:
        # S-1 (manifest cell-grid completeness): every other complete-run guard
        # iterates over the cells the manifest LISTS and the per-trial loops range
        # over manifest["trials"]; nothing asserts the cell set covers the full
        # (arm × fixture × trial) grid. A manifest that under-enumerates cells
        # (e.g. only the WITH cell for f1-t1) false-greens — the absent arms have
        # no cells to flag "bad" and primary_outcome defaults False for the whole
        # pool, yielding a maximal false headline delta with complete:true, rc 0.
        # An over-stated `trials` injects phantom all-FAIL trials that dilute the
        # delta; `trials:0` makes range(1,1) empty for an all-zero false-green.
        # Refuse a degenerate trial count, then assert exactly one cell per
        # (arm, fid, trial). Manifest-shape check, independent of parsed content;
        # fail loud BEFORE writing last_run.json (mirror the bad_cells pattern).
        if trials < 1:
            print(f"[fatal] manifest trials={trials} is degenerate (< 1) for "
                  f"{dispatch_dir}; range(1,{trials + 1}) is empty so every per-trial "
                  f"loop collapses to an all-zero false-green — refusing to score",
                  file=sys.stderr)
            return 1
        realized: dict = {}  # (arm, fid, trial) -> count
        for c in cells:
            key = (c["arm"], c["fixture_id"], c["trial"])
            realized[key] = realized.get(key, 0) + 1
        expected_grid = {(arm, fid, t)
                         for arm in _ARMS
                         for fid in fixtures_in_run
                         for t in range(1, trials + 1)}
        missing = sorted(expected_grid - set(realized))
        duplicates = sorted(k for k, n in realized.items() if n > 1)
        if missing or duplicates:
            print(f"[fatal] manifest cell-grid is incomplete for {dispatch_dir}: "
                  f"expected exactly one cell per (arm × fixture × trial) over "
                  f"arms {list(_ARMS)} × fixtures {fixtures_in_run} × "
                  f"trials 1..{trials}; missing={missing} duplicate={duplicates} — "
                  f"refusing to score (missing cells grade FAIL-by-absence in every "
                  f"arm with no cell to flag, false-greening a wrong delta as "
                  f"complete:true)", file=sys.stderr)
            return 1
        if total_parsed == 0:
            print(f"[fatal] no verdict records parsed across any cell in "
                  f"{dispatch_dir} (.collect-status is present but every result_file "
                  f"is missing/empty/dispatch-failed); refusing to score — a "
                  f"complete:true run with zero collected verdicts false-greens as a "
                  f"clean null", file=sys.stderr)
            return 1
        if bad_cells:
            print(f"[fatal] {len(bad_cells)} cell result_file(s) are "
                  f"missing/empty/dispatch-failed: {sorted(bad_cells)}; refusing to "
                  f"score a partially-collected complete run (the absent cells would "
                  f"grade FAIL-by-absence and bias the delta toward a null)",
                  file=sys.stderr)
            return 1
        # F-1: under-emission guard. A present, non-empty cell that emits fewer
        # records than its fixture's ground-truth primary budget (parsed primary +
        # malformed lines) leaves the omitted bugs FAIL-by-absence in ALL arms
        # equally → deltas collapse to 0.0 with complete:true, rc 0, malformed 0.
        # That is the toward-null false-green this harness exists to prevent, and no
        # existing guard flags it. Fail loud BEFORE writing last_run.json (mirror the
        # bad_cells pattern, separate list + distinct message).
        if undergraded_cells:
            detail = ", ".join(
                f"{rf} (gt-matched primary {m} of {k})"
                for (rf, m, k) in sorted(undergraded_cells))
            print(f"[fatal] {len(undergraded_cells)} cell result_file(s) under-emit "
                  f"OR id-drift their fixture's primary-record budget — parsed "
                  f"primary ids matching ground-truth fall short of K: {detail}; "
                  f"refusing to score (omitted OR id-drifted primary bugs grade "
                  f"FAIL-by-absence in every arm equally, collapsing the deltas to a "
                  f"false-green null)", file=sys.stderr)
            return 1

    def primary_outcome(arm, fid, bug, t):
        return primary[arm].get(fid, {}).get(t, {}).get(bug, False)

    def secondary_outcome(arm, fid, sid, t):
        return secondary[arm].get(fid, {}).get(t, {}).get(sid, False)

    # Per-trial per-arm primary pass-rate (for the paired deltas).
    per_trial_rate: dict = {a: [] for a in _ARMS}
    for arm in _ARMS:
        for t in range(1, trials + 1):
            passes = sum(1 for fid in fixtures_in_run
                         for bug in bugs_by_fixture.get(fid, [])
                         if primary_outcome(arm, fid, bug, t))
            per_trial_rate[arm].append(_rate(passes, K))

    # Majority-collapsed per-arm primary rate + per-fixture + off-axis.
    arm_pass: dict = {a: 0 for a in _ARMS}
    off_pass: dict = {a: 0 for a in _ARMS}
    per_fixture_pass: dict = {a: {fid: 0 for fid in fixtures_in_run} for a in _ARMS}
    off_total = sum(1 for b in all_bugs if bug_off.get(b))
    for arm in _ARMS:
        for fid in fixtures_in_run:
            for bug in bugs_by_fixture.get(fid, []):
                outs = [primary_outcome(arm, fid, bug, t)
                        for t in range(1, trials + 1)]
                if _majority_pass(outs):
                    arm_pass[arm] += 1
                    per_fixture_pass[arm][fid] += 1
                    if bug_off.get(bug):
                        off_pass[arm] += 1

    # Secondary diagnostic (majority-collapsed over the secondary universe).
    sec_universe = sorted(secondary_universe)
    sec_pass: dict = {a: 0 for a in _ARMS}
    for arm in _ARMS:
        for (fid, sid) in sec_universe:
            outs = [secondary_outcome(arm, fid, sid, t)
                    for t in range(1, trials + 1)]
            if _majority_pass(outs):
                sec_pass[arm] += 1
    graded_expectations = len(sec_universe)

    arm_rates = {a: {"pass": arm_pass[a], "total": K,
                     "rate": _rate(arm_pass[a], K)} for a in _ARMS}

    deltas = {
        "_note": ("paired = mean of per-trial deltas; does NOT equal "
                  "rate_with - rate_without (per-arm rate is the "
                  "majority-collapsed value)"),
        "with_without": _delta_block(per_trial_rate["with"],
                                     per_trial_rate["without"], with_beyond=True),
        "with_mid": _delta_block(per_trial_rate["with"],
                                 per_trial_rate["mid"], with_beyond=True),
        "mid_without": _delta_block(per_trial_rate["mid"],
                                    per_trial_rate["without"], with_beyond=False),
    }

    last_run = {
        "run_id": run_id,
        "trials": trials,
        "fixtures": len(fixtures_in_run),
        "complete": complete,
        "graded_bugs": K,
        "with": arm_rates["with"],
        "mid": arm_rates["mid"],
        "without": arm_rates["without"],
        "deltas": deltas,
        "malformed_verdicts": {a: malformed[a] for a in _ARMS},
        "per_fixture": [
            {"id": fid, **{a: _rate(per_fixture_pass[a][fid],
                                    len(bugs_by_fixture.get(fid, [])))
                           for a in _ARMS}}
            for fid in fixtures_in_run
        ],
        "secondary_diagnostic": {
            "graded_expectations": graded_expectations,
            **{a: _rate(sec_pass[a], graded_expectations) for a in _ARMS},
            # S-1: reconcile the OBSERVED secondary count against the documented
            # 26-pool, but ONLY for a complete run over the full fixture set (the
            # documented 26 = 27 − fixture-1 #8 is a whole-run construction). For a
            # partial/smoke run the observed count is not the 26-pool, so we do not
            # assert that provenance (contracted=None). Diagnostic only — never
            # changes rc; score does NOT gate on the secondary count (round-3).
            **(
                {"contracted": _CONTRACTED_SECONDARY_POOL,
                 "reconciled": graded_expectations == _CONTRACTED_SECONDARY_POOL}
                if (complete and set(fixtures_in_run) == gt_fixture_ids)
                else {"contracted": None}
            ),
        },
        "off_axis_diagnostic": {
            a: {"pass": off_pass[a], "total": off_total,
                "rate": _rate(off_pass[a], off_total)} for a in _ARMS
        },
    }

    (_EVALS_DIR / "last_run.json").write_text(
        json.dumps(last_run, indent=2), encoding="utf-8")
    (_EVALS_DIR / "results.md").write_text(_render_results(last_run), encoding="utf-8")
    return 0


def _render_results(lr: dict) -> str:
    """Human-readable summary mirror of last_run.json (the go/no-go reads from
    here too, so it carries the rate-vs-paired _note)."""
    d = lr["deltas"]

    def fmt(b):
        _mde = b['mde_heuristic']
        return (f"paired={b['paired']:+.3f} spread={b['trial_spread']} "
                f"mde={'null' if _mde is None else _mde} "
                + (f"beyond_spread={b['beyond_spread']}"
                   if "beyond_spread" in b else ""))

    lines = [
        f"# Inquisitor eval — run {lr['run_id']}",
        "",
        f"- trials: {lr['trials']} · fixtures: {lr['fixtures']} · "
        f"complete: {lr['complete']} · graded_bugs (K): {lr['graded_bugs']}",
        "",
        "## Per-arm pass rate (majority-collapsed)",
        f"- WITH: {lr['with']['rate']:.3f} ({lr['with']['pass']}/{lr['with']['total']})",
        f"- MID: {lr['mid']['rate']:.3f} ({lr['mid']['pass']}/{lr['mid']['total']})",
        f"- WITHOUT: {lr['without']['rate']:.3f} "
        f"({lr['without']['pass']}/{lr['without']['total']})",
        "",
        "## Paired deltas",
        f"> NOTE: {d['_note']}",
        f"- WITH-WITHOUT (primary): {fmt(d['with_without'])}",
        f"- WITH-MID (fan-out): {fmt(d['with_mid'])}",
        f"- MID-WITHOUT (scaffolding+procedure): {fmt(d['mid_without'])}",
        "",
        f"## Malformed verdicts (per arm): {lr['malformed_verdicts']}",
        "",
        "## Off-axis diagnostic (off_axis primary bugs only)",
        f"- WITH: {lr['off_axis_diagnostic']['with']}",
        f"- MID: {lr['off_axis_diagnostic']['mid']}",
        f"- WITHOUT: {lr['off_axis_diagnostic']['without']}",
        "",
        "## Secondary diagnostic (observed secondary union)",
        f"- graded_expectations: {_secondary_graded_label(lr)}",
        f"- WITH/MID/WITHOUT: {lr['secondary_diagnostic']['with']:.3f} / "
        f"{lr['secondary_diagnostic']['mid']:.3f} / "
        f"{lr['secondary_diagnostic']['without']:.3f}",
        "",
    ]
    return "\n".join(lines)


def _secondary_graded_label(lr: dict) -> str:
    """S-1: report the OBSERVED graded_expectations and, only when the run carries
    the documented-pool provenance (a complete full-fixture run → contracted set),
    surface reconciliation against the 26-pool. Never asserts the 26-provenance when
    it does not hold (a partial/smoke run shows the bare observed count)."""
    sd = lr["secondary_diagnostic"]
    n = sd["graded_expectations"]
    contracted = sd.get("contracted")
    if contracted is None:
        return str(n)
    state = "reconciled" if sd.get("reconciled") else "MISMATCH"
    return f"{n} (contracted {contracted}; {state})"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Inquisitor fan-out eval harness.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_stage = sub.add_parser("stage", help="Render three-arm dispatch files")
    sp_stage.add_argument("run_id")
    sp_stage.add_argument("--trials", type=int, default=_DEFAULT_TRIALS)
    sp_stage.add_argument("--fixture", default=None)
    sp_stage.add_argument("--force", action="store_true")

    sp_score = sub.add_parser("score", help="Aggregate verdicts + write last_run.json")
    sp_score.add_argument("run_id")
    sp_score.add_argument("--allow-incomplete", action="store_true")

    return p.parse_args(argv)


def main(argv: list | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.cmd == "stage":
        dispatch_dir = stage(args.run_id, trials=args.trials,
                             fixture=args.fixture, force=args.force)
        print(dispatch_dir)
        return 0
    if args.cmd == "score":
        rc = score(args.run_id, allow_incomplete=args.allow_incomplete)
        if rc == 0:
            print((_EVALS_DIR / "last_run.json").read_text(encoding="utf-8"))
        return rc
    print(f"[fatal] unknown command {args.cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
