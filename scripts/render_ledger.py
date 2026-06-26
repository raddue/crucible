#!/usr/bin/env python3
"""`/ledger` weekly renderer — the testable render core (Phase 5).

Reads `~/.claude/crucible/ledger/runs.jsonl` (override `CRUCIBLE_LEDGER_DIR`), groups entries by ISO week, computes
per-week stats, and renders `docs/ledger/weekly-YYYY-Www.md`. The honest
"caught N silent bugs" headline counts forward `would_have_shipped_without_gate`
entries EXCLUDING backfilled ones (design §4 "Honest count" + L-3/L-5).

Structural inflation-detector (§4a "WHS Guard Rails"): per-skill
`significant_rate` / `fatal_rate` from forward-captured entries only, alerting
when a rate exceeds 3x its 4-week rolling median. Silent until 4 weeks of
forward data exist for a skill. Raw rates are printed from week 1.

The SKILL.md (`skills/ledger/SKILL.md`) is a thin prompt wrapper; THIS module is
the source of truth. Pure stdlib; no third-party deps.

Run: python3 scripts/render_ledger.py --weeks N
"""
import argparse
import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.ledger_reduce import reduce as _falsification_reduce  # noqa: E402
from scripts.ledger_append import default_ledger_dir, _valid_identity  # noqa: E402
from scripts.atomic_write import atomic_write_text  # noqa: E402
from scripts.reconcile_ledger import (  # noqa: E402
    parse_predicate,
    predicate_checkable,
    ledger_entry_hash,
    PREDICATE_SENTINEL,
    GRACE_DAYS,
    _parse_iso,
)

# Defaults point at the central machine-local store (#270): the live ledger
# aggregates every repo's gating runs into ~/.claude/crucible/ledger (override
# via CRUCIBLE_LEDGER_DIR). Tests / the committed in-repo fixture pass an
# explicit --ledger. falsification.jsonl lives beside runs.jsonl in that store.
LEDGER_PATH = os.path.join(default_ledger_dir(), "runs.jsonl")
FALSIFICATION_PATH = os.path.join(default_ledger_dir(), "falsification.jsonl")
REPORT_DIR = os.path.join("docs", "ledger")

# 3x the 4-week rolling median per §4a. Starting heuristic; re-evaluate after a
# quarter of forward data.
INFLATION_FACTOR = 3.0
MIN_BASELINE_WEEKS = 4

# Predicate-rate bootstrap: until this many parseable predicates exist for a
# skill, its hit/unparseable rates are not statistically meaningful and the
# steady-state vagueness-drift advisory is suppressed (design §3a / plan 7.5).
PREDICATE_BOOTSTRAP_MIN = 10
# One-shot Phase-7 regression gate: a first-report unparseable rate above this
# fires the vagueness advisory even before the bootstrap window fills.
VAGUENESS_RATE_THRESHOLD = 0.5


# --------------------------------------------------------------------------- #
# Loading                                                                     #
# --------------------------------------------------------------------------- #

def _warn(msg: str) -> None:
    print(f"[render_ledger WARN] {msg}", file=sys.stderr)


def load_runs(path: str) -> list:
    """Tolerant read of runs.jsonl, deduped by (run_id, skill) latest-wins.

    Skips blank lines, malformed JSON, and a partial trailing line (no
    terminating newline) — same tolerance as scripts/ledger_reduce.reduce.
    Missing file -> []. runs.jsonl is already deduped at write time (L-2), but
    we dedup defensively here: later file positions win.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return []
    if not raw:
        return []

    parts = raw.split(b"\n")
    if not raw.endswith(b"\n"):
        # Last element is a partial trailing line (crash-mid-append) — drop it.
        parts = parts[:-1]

    by_key = {}  # (run_id, skill) -> entry; later positions overwrite earlier
    order = []   # preserve first-seen order of keys for stable output
    skipped = 0  # #400: count corrupt lines instead of degrading silently
    for chunk in parts:
        if not chunk:
            continue
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if not isinstance(obj, dict):
            skipped += 1
            continue
        key = (obj.get("run_id"), obj.get("skill"))
        if key not in by_key:
            order.append(key)
        by_key[key] = obj
    if skipped:
        _warn(f"load_runs: skipped {skipped} unparseable line(s) in {path}")
    return [by_key[k] for k in order]


# --------------------------------------------------------------------------- #
# ISO week                                                                    #
# --------------------------------------------------------------------------- #

def iso_week(entry: dict) -> str:
    """Return "YYYY-Www" from the entry's ISO-8601 `timestamp`.

    Handles a trailing `Z` (UTC). Uses datetime.isocalendar(), whose week year
    can differ from the calendar year near year boundaries — that is correct
    ISO-8601 behavior.
    """
    ts = entry.get("timestamp") or ""
    dt = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    iso = dt.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


# --------------------------------------------------------------------------- #
# Headline + stats                                                            #
# --------------------------------------------------------------------------- #

def _is_forward(entry: dict) -> bool:
    """Forward-captured: not backfilled AND has a real severity_histogram.

    Per §4a the inflation baseline and raw rates use ONLY these entries.
    """
    return (entry.get("backfilled") is not True
            and entry.get("severity_histogram") is not None)


def caught_count(entries: list) -> int:
    """THE headline. Count of WHS==True entries, EXCLUDING backfilled ones.

    Per L-3/L-5: backfilled entries (WHS null by the mechanical histogram rule)
    are excluded; so are WHS-null/WHS-false forward entries. This is exactly
    what T-5 asserts. The exclusion keys on `backfilled` itself, not merely on
    WHS being null — a pathological backfilled entry with WHS forced True is
    still excluded.
    """
    n = 0
    for e in entries:
        if e.get("backfilled") is True:
            continue
        if e.get("would_have_shipped_without_gate") is True:
            n += 1
    return n


def _verdict_breakdown(entries: list) -> dict:
    counts = {}
    for e in entries:
        v = e.get("verdict") or "UNKNOWN"
        counts[v] = counts.get(v, 0) + 1
    return counts


def week_summary(entries: list) -> dict:
    """Per-week stats: totals, verdict breakdown, caught_count, per-skill rates.

    Per-skill `significant_rate` and `fatal_rate` are computed FROM
    FORWARD-CAPTURED ENTRIES ONLY (backfilled excluded, severity_histogram
    not null). The backfilled count is reported separately.
    """
    per_skill = {}
    backfilled = 0
    skipped_identityless = 0
    for e in entries:
        # #402 read-side: a row lacking a valid (run_id, skill) join key would
        # merge into a single "unknown" skill bucket, conflating unrelated runs
        # in the severity table. Skip + count it instead.
        if not (_valid_identity(e.get("run_id")) and _valid_identity(e.get("skill"))):
            skipped_identityless += 1
            continue
        skill = e["skill"]
        slot = per_skill.setdefault(
            skill,
            {"findings": 0, "fatal": 0, "significant": 0,
             "significant_rate": 0.0, "fatal_rate": 0.0, "forward_entries": 0},
        )
        if e.get("backfilled") is True:
            backfilled += 1
            continue
        if not _is_forward(e):
            # forward but null histogram (shouldn't happen for non-backfilled,
            # but be safe) — not a measurable severity sample.
            continue
        hist = e["severity_histogram"]
        f = int(hist.get("fatal", 0) or 0)
        s = int(hist.get("significant", 0) or 0)
        m = int(hist.get("minor", 0) or 0)
        nt = int(hist.get("nit", 0) or 0)
        slot["findings"] += f + s + m + nt
        slot["fatal"] += f
        slot["significant"] += s
        slot["forward_entries"] += 1

    if skipped_identityless:
        _warn(f"week_summary: skipped {skipped_identityless} ledger row(s) "
              f"lacking a valid (run_id, skill) identity (#402)")

    for slot in per_skill.values():
        total = slot["findings"]
        if total > 0:
            slot["significant_rate"] = slot["significant"] / total
            slot["fatal_rate"] = slot["fatal"] / total
        else:
            slot["significant_rate"] = 0.0
            slot["fatal_rate"] = 0.0

    # Per-repo provenance breakdown (schema v2 `repo` field). Counts all
    # non-backfilled runs (Tier A + Tier B stubs); v1 rows carry no `repo`
    # key and bucket under 'unknown'. `caught` is the WHS-true subset.
    per_repo = {}
    for e in entries:
        if e.get("backfilled") is True:
            continue
        repo = e.get("repo") or "unknown"
        rslot = per_repo.setdefault(repo, {"runs": 0, "caught": 0})
        rslot["runs"] += 1
        if e.get("would_have_shipped_without_gate") is True:
            rslot["caught"] += 1

    return {
        "total_runs": len(entries),
        "verdicts": _verdict_breakdown(entries),
        "caught_count": caught_count(entries),
        "backfilled": backfilled,
        "per_skill": per_skill,
        "per_repo": per_repo,
    }


# --------------------------------------------------------------------------- #
# Inflation detector (§4a)                                                    #
# --------------------------------------------------------------------------- #

def inflation_alert(per_skill_rates: dict, baseline_medians: dict) -> list:
    """§4a structural inflation-detector.

    Alert when a skill's `significant_rate` > 3x its 4-week rolling median, OR
    `fatal_rate` > 3x its rolling median. SILENT for a skill until 4 weeks of
    forward data exist for it (so for v1, with no forward history, this returns
    []). Raw rates are always computed and printed regardless — see
    render_week — but the ALERT only fires once the baseline is armed.

    `baseline_medians` maps skill -> {"significant_median", "fatal_median",
    "weeks"}. A skill missing from the dict, or with weeks < 4, stays silent.
    """
    alerts = []
    for skill, rates in per_skill_rates.items():
        base = baseline_medians.get(skill)
        if not base or base.get("weeks", 0) < MIN_BASELINE_WEEKS:
            continue  # silent bootstrap
        sig_med = base.get("significant_median", 0.0)
        fat_med = base.get("fatal_median", 0.0)
        sig = rates.get("significant_rate", 0.0)
        fat = rates.get("fatal_rate", 0.0)
        sig_hit = sig_med > 0 and sig > INFLATION_FACTOR * sig_med
        fat_hit = fat_med > 0 and fat > INFLATION_FACTOR * fat_med
        if sig_hit or fat_hit:
            alerts.append({
                "skill": skill,
                "significant_rate": sig,
                "fatal_rate": fat,
                "significant_median": sig_med,
                "fatal_median": fat_med,
            })
    return alerts


# --------------------------------------------------------------------------- #
# Falsification cross-link (graceful degradation)                            #
# --------------------------------------------------------------------------- #

def falsified_count(falsification_path: str) -> int:
    """Count of distinct falsified ledger entries via the L-9 reduction.

    GRACEFUL DEGRADATION: scripts.ledger_reduce.reduce() returns {} when
    falsification.jsonl is absent (Phase 4 not built yet) -> count 0. Never
    crashes on a missing file. Counts only entries whose reduced record has
    `falsified == True` (other records may be unfalsifiable / not-yet-checked).
    """
    reduced = _falsification_reduce(falsification_path)
    return sum(1 for rec in reduced.values() if rec.get("falsified") is True)


def falsified_breakdown(falsification_path: str) -> dict:
    """Per-source counts of falsified entries (#342), via the L-9 reduction.

    Source derivation: walkback/predicate entries carry a top-level `via`;
    manual entries do NOT — they carry `falsified_by.manual_override == true`
    and no `via`. A `bad_implementation` signal (top-level or nested
    `signal_type`) is counted as its own source. Precedence:
      via=="walkback"        -> walkback
      via=="predicate"       -> predicate
      signal_type=="bad_implementation" -> bad_implementation
      else (manual_override) -> manual_override
    The four counts sum to `falsified_count` (each falsified entry hits exactly
    one bucket).
    """
    return _breakdown_from_reduced(_falsification_reduce(falsification_path))


def _breakdown_from_reduced(reduced: dict) -> dict:
    """Core of `falsified_breakdown` over an already-reduced map (so the renderer
    doesn't re-read falsification.jsonl)."""
    out = {"walkback": 0, "predicate": 0, "manual_override": 0,
           "bad_implementation": 0}
    for rec in reduced.values():
        if rec.get("falsified") is not True:
            continue
        via = rec.get("via") or (rec.get("falsified_by") or {}).get("via")
        sig = rec.get("signal_type") \
            or (rec.get("falsified_by") or {}).get("signal_type")
        if via == "walkback":
            out["walkback"] += 1
        elif via == "predicate":
            out["predicate"] += 1
        elif sig == "bad_implementation":
            out["bad_implementation"] += 1
        else:
            out["manual_override"] += 1
    return out


# --------------------------------------------------------------------------- #
# Predicate calibration (predicted_falsifier — design §3a, Phase 7)           #
# --------------------------------------------------------------------------- #

def predicate_rates(entries: list, falsification_reduced: dict, *, now) -> dict:
    """Per-skill predicate hit-rate + unparseable-rate (design §3a).

    For each entry carrying a non-null `predicted_falsifier`:
      - the bootstrap sentinel is EXCLUDED from both denominators;
      - `total_non_null` counts every real (non-sentinel) predicate — the
        denominator for `unparseable_rate`;
      - `unparseable` counts free-form (non-grammar) predicates;
      - `parseable` counts grammar-valid predicates that are ALSO outside the
        30-day grace period — the denominator for `hit_rate` (a predicate still
        inside grace has not yet had a full chance to fire);
      - `hit_count` counts those parseable-outside-grace entries whose reduced
        falsification record carries `via == "predicate"` (a fired prediction).

    Returns {skill: {total_non_null, parseable, unparseable, hit_count,
    hit_rate, unparseable_rate}}.
    """
    now_dt = _parse_iso(now)
    grace_cutoff = (now_dt - _dt.timedelta(days=GRACE_DAYS)) if now_dt else None

    per_skill = {}
    skipped_identityless = 0
    for e in entries:
        pf = e.get("predicted_falsifier")
        if pf is None:
            continue
        # Bootstrap-window sentinel: excluded from BOTH denominators — and it must
        # not even materialize a per-skill slot (a sentinel-only skill has no
        # predicate data to report).
        if pf == PREDICATE_SENTINEL:
            continue
        # #402 read-side: an identity-less row has no stable join key into the
        # falsification map — skip + count rather than bucket it under "unknown".
        if not (_valid_identity(e.get("run_id")) and _valid_identity(e.get("skill"))):
            skipped_identityless += 1
            continue
        skill = e["skill"]
        slot = per_skill.setdefault(skill, {
            "total_non_null": 0, "parseable": 0, "uncheckable": 0,
            "unparseable": 0, "hit_count": 0,
        })
        slot["total_non_null"] += 1
        parsed = parse_predicate(pf)
        if parsed is None:
            slot["unparseable"] += 1
            continue
        # v1.1 auto-checks touching, referencing, and revert-verb `hash` forms
        # (single source of truth: `predicate_checkable`). A non-revert `hash`
        # predicate has no candidate population, so counting it in the hit-rate
        # DENOMINATOR would structurally drag the rate to 0. Track it as
        # `uncheckable`, excluded from hit_rate.
        if not predicate_checkable(parsed):
            slot["uncheckable"] += 1
            continue
        # Parseable + auto-checkable: counts toward the hit-rate denominator once
        # it is outside the grace window (it has had a full chance to fire).
        ts = _parse_iso(e.get("timestamp"))
        outside_grace = grace_cutoff is None or (ts is not None and ts < grace_cutoff)
        if not outside_grace:
            continue
        slot["parseable"] += 1
        h = ledger_entry_hash(e["run_id"], skill)
        fals = falsification_reduced.get(h)
        if fals is not None:
            via = fals.get("via") or (fals.get("falsified_by") or {}).get("via")
            if bool(fals.get("falsified")) and via == "predicate":
                slot["hit_count"] += 1

    if skipped_identityless:
        _warn(f"predicate_rates: skipped {skipped_identityless} predicate row(s) "
              f"lacking a valid (run_id, skill) identity (#402)")

    out = {}
    for skill, s in per_skill.items():
        hit_rate = (s["hit_count"] / s["parseable"]) if s["parseable"] else 0.0
        unp_rate = (s["unparseable"] / s["total_non_null"]) if s["total_non_null"] else 0.0
        out[skill] = {**s, "hit_rate": hit_rate, "unparseable_rate": unp_rate}
    return out


# --------------------------------------------------------------------------- #
# Commit citation (v1-schema limitation)                                      #
# --------------------------------------------------------------------------- #

def _commit_citation(entry: dict):
    """Return a human citation string for an entry, or None if unavailable.

    v1-schema LIMITATION: the schema has NO commit field — `artifact_hash` is
    null for backfilled entries, and forward entries carry a UUIDv7 run_id with
    no embedded commit. So:
      - Backfilled entries (`backfill-<PR>-quality-gate`) -> cite "PR #<PR>".
      - Forward (UUID run_id) entries -> no commit available in v1 -> None.
    We do NOT invent commit SHAs. A future schema rev that captures the gating
    commit can replace this with a real SHA citation.
    """
    run_id = entry.get("run_id") or ""
    if entry.get("backfilled") is True and run_id.startswith("backfill-"):
        rest = run_id[len("backfill-"):]
        pr = rest.split("-", 1)[0]
        if pr.isdigit():
            return f"PR #{pr}"
    return None


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #

def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_week(week: str, entries: list, *, baseline_medians=None,
                falsified=0, is_first_of_month=False,
                falsification_reduced=None, now=None) -> str:
    """Render the markdown report for one ISO week.

    Sections: honest "caught N" headline, verdict breakdown, raw per-skill
    rates (printed from week 1), inflation alerts (silent during bootstrap),
    a separate backfilled-historical-context section (kept OUT of the caught
    headline), the falsified cross-link count, and — if this is the first
    /ledger run of the month — a monthly spot-check checklist (§4a).
    """
    baseline_medians = baseline_medians or {}
    summary = week_summary(entries)
    caught = summary["caught_count"]
    per_skill = summary["per_skill"]
    alerts = inflation_alert(per_skill, baseline_medians)

    lines = []
    lines.append(f"# Crucible Calibration Ledger — {week}")
    lines.append("")
    lines.append(f"_Generated {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}_")
    lines.append("")

    # Inflation alert block goes at the TOP per §4a.
    if alerts:
        lines.append("## ⚠ Inflation alert")
        lines.append("")
        for a in alerts:
            lines.append(
                f"- **{a['skill']}**: significant_rate={_fmt_pct(a['significant_rate'])} "
                f"(4wk median {_fmt_pct(a['significant_median'])}), "
                f"fatal_rate={_fmt_pct(a['fatal_rate'])} "
                f"(4wk median {_fmt_pct(a['fatal_median'])})."
            )
        lines.append("")
        lines.append(
            "Review `highest_finding` quotes for this week to verify severities "
            "are calibrated."
        )
        lines.append("")

    # Headline.
    lines.append(f"## Crucible caught {caught} silent bug{'s' if caught != 1 else ''}")
    lines.append("")
    lines.append(
        f"Forward-captured runs with `would_have_shipped_without_gate: true`, "
        f"excluding backfilled entries (the honest count, per L-3/L-5)."
    )
    lines.append("")

    # Top-severity findings with commit citations (forward, WHS-true entries).
    caught_entries = [
        e for e in entries
        if e.get("backfilled") is not True
        and e.get("would_have_shipped_without_gate") is True
    ]
    if caught_entries:
        lines.append("### Findings")
        lines.append("")
        for e in caught_entries:
            hf = e.get("highest_finding") or "(no quote captured)"
            cite = _commit_citation(e)
            cite_str = f" — {cite}" if cite else ""
            lines.append(f"- `{e.get('skill')}`: {hf}{cite_str}")
        lines.append("")

    # Verdict breakdown.
    lines.append("## Verdict breakdown")
    lines.append("")
    lines.append(f"- Total runs this week: **{summary['total_runs']}**")
    for verdict in sorted(summary["verdicts"]):
        lines.append(f"- {verdict}: {summary['verdicts'][verdict]}")
    lines.append("")

    # Raw per-skill rates (printed from week 1; no alert threshold).
    lines.append("## Per-skill severity rates (forward-captured only)")
    lines.append("")
    forward_skills = {
        s: r for s, r in per_skill.items() if r["forward_entries"] > 0
    }
    if forward_skills:
        lines.append("| skill | forward runs | findings | significant_rate | fatal_rate |")
        lines.append("|-------|-------------:|---------:|-----------------:|-----------:|")
        for skill in sorted(forward_skills):
            r = forward_skills[skill]
            lines.append(
                f"| {skill} | {r['forward_entries']} | {r['findings']} | "
                f"{_fmt_pct(r['significant_rate'])} | {_fmt_pct(r['fatal_rate'])} |"
            )
    else:
        lines.append(
            "_No forward-captured entries this week — rates unavailable. "
            "(Backfilled entries carry `severity_histogram: null` by design.)_"
        )
    lines.append("")
    lines.append(
        "_Inflation detector is silent for a skill until 4 weeks of "
        "forward-captured data exist for it (§4a bootstrap)._"
    )
    lines.append("")

    # Per-repo provenance breakdown (schema v2 `repo`); all non-backfilled
    # runs, v1 rows with no `repo` bucket under 'unknown'.
    per_repo = summary.get("per_repo", {})
    active_repos = {r: v for r, v in per_repo.items() if v["runs"] > 0}
    if active_repos:
        # "runs" = all non-backfilled gating runs in that repo (Tier A + Tier B
        # stubs), NOT the strict severity-bearing forward set — a Tier-B-only
        # repo still shows its review activity here. "caught" is the WHS-true
        # subset, matching the honest headline.
        lines.append("## Per-repo breakdown")
        lines.append("")
        lines.append("| repo | runs | caught |")
        lines.append("|------|-----:|-------:|")
        # Sort by runs desc, then repo name for determinism.
        for repo in sorted(active_repos,
                           key=lambda r: (-active_repos[r]["runs"], r)):
            v = active_repos[repo]
            lines.append(f"| {repo} | {v['runs']} | {v['caught']} |")
        lines.append("")

    # Backfilled historical context — SEPARATE from the caught headline.
    backfilled_entries = [e for e in entries if e.get("backfilled") is True]
    if backfilled_entries:
        lines.append("## Backfilled historical context")
        lines.append("")
        lines.append(
            f"{len(backfilled_entries)} backfilled entr"
            f"{'y' if len(backfilled_entries) == 1 else 'ies'} this week "
            f"(excluded from the caught headline and from severity rates; "
            f"`severity_histogram: null` by design):"
        )
        lines.append("")
        for e in backfilled_entries:
            cite = _commit_citation(e)
            cite_str = cite if cite else "(no PR citation)"
            lines.append(f"- {cite_str} — `{e.get('skill')}` {e.get('verdict')}")
        lines.append("")

    # Falsified cross-link.
    lines.append("## Falsified verdicts (cross-link)")
    lines.append("")
    lines.append(
        f"Falsified ledger entries (all-time, via the L-9 reduction over "
        f"`falsification.jsonl`): **{falsified}**."
    )
    if falsified > 0:
        bd = _breakdown_from_reduced(falsification_reduced or {})
        parts = [f"{k.replace('_', ' ')} {bd[k]}"
                 for k in ("walkback", "predicate", "manual_override",
                           "bad_implementation") if bd[k]]
        if parts:
            lines.append("")
            lines.append(f"_By source: {', '.join(parts)}._")
    if falsified == 0:
        lines.append("")
        lines.append(
            "_No falsification data yet (reconciler / Phase 4 not present, or "
            "no verdicts falsified)._"
        )
    lines.append("")

    # Predicate calibration (predicted_falsifier — §3a, Phase 7).
    p_rates = predicate_rates(entries, falsification_reduced or {}, now=now)
    active = {s: r for s, r in p_rates.items() if r["total_non_null"] > 0}
    lines.append("## Predicate calibration (`predicted_falsifier`)")
    lines.append("")
    if active:
        lines.append("| skill | parseable | hit_rate | unparseable_rate |")
        lines.append("|-------|----------:|---------:|-----------------:|")
        for skill in sorted(active):
            r = active[skill]
            lines.append(
                f"| {skill} | {r['parseable']} | "
                f"{_fmt_pct(r['hit_rate'])} | {_fmt_pct(r['unparseable_rate'])} |"
            )
        lines.append("")
        for skill in sorted(active):
            r = active[skill]
            # Bootstrap bracket: rates not yet statistically meaningful.
            if r["parseable"] < PREDICATE_BOOTSTRAP_MIN:
                lines.append(
                    f"_[predicate-rate bootstrap: `{skill}` has only "
                    f"{r['parseable']} entr"
                    f"{'y' if r['parseable'] == 1 else 'ies'} with parseable "
                    f"predicates so far — rates not yet statistically meaningful; "
                    f"vagueness-drift advisory suppressed]_"
                )
            # One-shot regression gate (§3a risk-check): fires even pre-bootstrap.
            if r["unparseable_rate"] > VAGUENESS_RATE_THRESHOLD:
                lines.append(
                    f"- ⚠ **predicate vagueness** (`{skill}`): "
                    f"{_fmt_pct(r['unparseable_rate'])} of non-null predicates are "
                    f"unparseable (> {_fmt_pct(VAGUENESS_RATE_THRESHOLD)}). Tighten "
                    f"the emit prompt before relying on the hit-rate."
                )
            # Transparency: a non-revert `hash` predicate parses but has no
            # candidate population, so it's excluded from the hit-rate.
            # Self-suppresses when uncheckable == 0.
            if r.get("uncheckable"):
                lines.append(
                    f"_{r['uncheckable']} `{skill}` predicate"
                    f"{'' if r['uncheckable'] == 1 else 's'} use the non-revert "
                    f"`hash` form — parseable but not auto-checkable, so excluded "
                    f"from the hit-rate denominator._"
                )
        lines.append("")
    else:
        lines.append(
            "_No pre-registered predicates this week (Tier A code PASS/FAIL "
            "verdicts emit `predicted_falsifier`; pre-Phase-7 sentinel entries "
            "are excluded)._"
        )
        lines.append("")

    # Monthly spot-check checklist (§4a) — first /ledger run of the month.
    if is_first_of_month:
        lines.append("## Monthly spot-check")
        lines.append("")
        lines.append(
            "First `/ledger` run of the month — spot-check protocol (advisory, "
            "not blocking):"
        )
        lines.append("")
        lines.append(
            "- [ ] Spot-check 5 random `would_have_shipped_without_gate: true` "
            "entries — do their `highest_finding` quotes match the rubric in "
            "`skills/shared/severity-rubric.md`?"
        )
        lines.append(
            "- [ ] Review any inflation alerts above for calibration drift."
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def _group_by_week(entries: list) -> dict:
    groups = {}
    for e in entries:
        try:
            wk = iso_week(e)
        except (ValueError, TypeError):
            continue  # unparseable timestamp -> skip (tolerant)
        groups.setdefault(wk, []).append(e)
    return groups


def _week_month(week_key: str):
    """Return the "%Y-%m" calendar month of an ISO week's Monday, or None.

    The month is derived from the week's Monday (ISO weekday 1), matching how
    the rest of the renderer locates a week in the calendar.
    """
    try:
        year_s, wk_s = week_key.split("-W")
        monday = _dt.date.fromisocalendar(int(year_s), int(wk_s), 1)
    except (ValueError, TypeError):
        return None
    return monday.strftime("%Y-%m")


def first_of_month_weeks(week_keys) -> set:
    """Return the subset of `week_keys` that are the chronologically-EARLIEST
    selected week in their calendar month — DETERMINISTIC from the data being
    rendered in THIS invocation (no filesystem scan).

    §4a's monthly spot-check must be idempotent: re-rendering the same corpus
    must reproduce the same checklist placement. A mutable filesystem scan (does
    a weekly-*.md already exist this month?) silently dropped the checklist on
    re-render — a real regression, since the spot-check is the only drift guard
    during the 4-week bootstrap. We instead mark exactly one week per month: the
    earliest among the weeks selected in this invocation.
    """
    earliest_by_month = {}  # month -> earliest week_key seen this invocation
    for wk in week_keys:
        month = _week_month(wk)
        if month is None:
            continue
        cur = earliest_by_month.get(month)
        if cur is None or wk < cur:  # "YYYY-Www" sorts chronologically as text
            earliest_by_month[month] = wk
    return set(earliest_by_month.values())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the Crucible calibration ledger weekly report(s)."
    )
    parser.add_argument(
        "--weeks", type=int, default=1,
        help="number of most-recent ISO weeks to render (default: 1)",
    )
    parser.add_argument(
        "--ledger", default=LEDGER_PATH,
        help="path to runs.jsonl (default: central store "
             "~/.claude/crucible/ledger/runs.jsonl, override via CRUCIBLE_LEDGER_DIR)",
    )
    parser.add_argument(
        "--falsification", default=FALSIFICATION_PATH,
        help="path to falsification.jsonl (default: central store "
             "~/.claude/crucible/ledger/falsification.jsonl)",
    )
    parser.add_argument(
        "--out-dir", default=REPORT_DIR,
        help="output directory for weekly-*.md (default: docs/ledger/)",
    )
    args = parser.parse_args(argv)

    # First-time-ever: runs.jsonl MISSING -> notice + exit 0, write nothing.
    if not os.path.exists(args.ledger):
        print("no ledger data yet — runs.jsonl not found; nothing to render.")
        return 0

    entries = load_runs(args.ledger)
    if not entries:
        # File exists but is empty / all-malformed. Honest: nothing to render.
        print("no ledger data yet — runs.jsonl has no readable entries.")
        return 0

    groups = _group_by_week(entries)
    if not groups:
        print("no ledger data yet — no entries with a parseable timestamp.")
        return 0

    falsified = falsified_count(args.falsification)
    # Reduce once and reuse for the predicate hit-rate cross-reference.
    falsification_reduced = _falsification_reduce(args.falsification)
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    weeks_sorted = sorted(groups.keys(), reverse=True)  # most recent first
    selected = weeks_sorted[: max(args.weeks, 0)]

    # Deterministic, per-invocation: exactly the earliest selected week in each
    # calendar month gets the §4a monthly spot-check checklist. Re-rendering the
    # same corpus reproduces the same placement (no filesystem dependence).
    first_of_month = first_of_month_weeks(selected)

    os.makedirs(args.out_dir, exist_ok=True)
    written = []
    for wk in selected:
        md = render_week(
            wk, groups[wk],
            baseline_medians={},  # v1: no forward rolling history yet -> silent
            falsified=falsified,
            is_first_of_month=(wk in first_of_month),
            falsification_reduced=falsification_reduced,
            now=now,
        )
        out_path = os.path.join(args.out_dir, f"weekly-{wk}.md")
        atomic_write_text(out_path, md)  # #400: torn-write-safe whole-file write
        written.append(out_path)

    for p in written:
        print(f"[ledger] wrote {p}")
    print(f"[ledger] rendered {len(written)} week(s); "
          f"caught(total over rendered weeks)="
          f"{sum(caught_count(groups[w]) for w in selected)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
