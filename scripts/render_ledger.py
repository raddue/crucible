#!/usr/bin/env python3
"""`/ledger` weekly renderer — the testable render core (Phase 5).

Reads `.crucible/ledger/runs.jsonl`, groups entries by ISO week, computes
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

# Defaults are CWD-relative: /ledger is invoked from the repo root, and the
# ledger lives under that repo's working tree. Keeping these relative (rather
# than pinned to this file's REPO_ROOT) lets the tool operate on whatever repo
# it is run from, and lets tests isolate via a chdir into tmp_path.
LEDGER_PATH = os.path.join(".crucible", "ledger", "runs.jsonl")
FALSIFICATION_PATH = os.path.join(".crucible", "ledger", "falsification.jsonl")
REPORT_DIR = os.path.join("docs", "ledger")

# 3x the 4-week rolling median per §4a. Starting heuristic; re-evaluate after a
# quarter of forward data.
INFLATION_FACTOR = 3.0
MIN_BASELINE_WEEKS = 4


# --------------------------------------------------------------------------- #
# Loading                                                                     #
# --------------------------------------------------------------------------- #

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
    for chunk in parts:
        if not chunk:
            continue
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        key = (obj.get("run_id"), obj.get("skill"))
        if key not in by_key:
            order.append(key)
        by_key[key] = obj
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
    for e in entries:
        skill = e.get("skill") or "unknown"
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

    for slot in per_skill.values():
        total = slot["findings"]
        if total > 0:
            slot["significant_rate"] = slot["significant"] / total
            slot["fatal_rate"] = slot["fatal"] / total
        else:
            slot["significant_rate"] = 0.0
            slot["fatal_rate"] = 0.0

    return {
        "total_runs": len(entries),
        "verdicts": _verdict_breakdown(entries),
        "caught_count": caught_count(entries),
        "backfilled": backfilled,
        "per_skill": per_skill,
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
                falsified=0, is_first_of_month=False) -> str:
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
    if falsified == 0:
        lines.append("")
        lines.append(
            "_No falsification data yet (reconciler / Phase 4 not present, or "
            "no verdicts falsified)._"
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
        help="path to runs.jsonl (default: .crucible/ledger/runs.jsonl)",
    )
    parser.add_argument(
        "--falsification", default=FALSIFICATION_PATH,
        help="path to falsification.jsonl (default: .crucible/ledger/falsification.jsonl)",
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
        )
        out_path = os.path.join(args.out_dir, f"weekly-{wk}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        written.append(out_path)

    for p in written:
        print(f"[ledger] wrote {p}")
    print(f"[ledger] rendered {len(written)} week(s); "
          f"caught(total over rendered weeks)="
          f"{sum(caught_count(groups[w]) for w in selected)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
