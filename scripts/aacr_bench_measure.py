#!/usr/bin/env python3
"""#631 — measure crucible review-gate precision/recall/F1 against AACR-Bench.

AACR-Bench (alibaba-open-code-review; Apache-2.0; also mirrored at
HuggingFace `Alibaba-Aone/aacr-bench`) annotates 2145 real review comments across
200 PRs / 50 repos / 10 languages: `label=1` = expert-verified CORRECT comment,
`label=0` = incorrect. This script measures the crucible review gate against that
ground truth:

  1. **sample** — pick a deterministic, seeded subset of PRs (reproducibility).
  2. **review** — fetch each PR's unified diff (`github.com/<repo>/pull/<N>.diff`)
     and run the review gate (the `delve` eight-field severity/verdict engine in
     the configured model) over it, keeping `CONFIRMED`/`PLAUSIBLE` findings and
     dropping `REFUTED` (shared/severity-verdict-contract.md §2).
  3. **match** — deterministically match each kept finding to the PR's label=1
     reference comments, four-stage, mirroring alibaba/aacr-bench
     `evaluation/judge.py`: path → side → line(k=1) → semantic (lexical, with a
     shared-signal-token fallback). One-to-one, order-stable.
  4. **report** — per-PR and pooled precision / recall / F1 / noise + model token
     usage, in a form docs/evals.md can quote.

The deterministic core here (subset selection, matching, arithmetic) is CI-gated
by `scripts/test_aacr_bench_measure.py`. The live review + the number it produces
are the manual/periodic half, exactly as the delve/siege/temper harnesses split
stage from live run — this script makes that live run ONE command.

Usage (run from repo root):
  # review a seeded subset with the configured model behind $NINEROUTER_URL
  python3 scripts/aacr_bench_measure.py run --dataset /path/dataset.json \
      --seed 631 --limit-prs 8 --out /tmp/aacr-results
"""
from __future__ import annotations

import difflib
import json
import os
import pathlib
import random
import re
import sys
import time

LINE_K = 1
LINE_SLOP = LINE_K

LEX_SEQ_RATIO = 0.4
LEX_JACCARD = 0.3

KEPT_VERDICTS = {"CONFIRMED", "PLAUSIBLE"}


# ── subset selection (deterministic) ───────────────────────────────────────────
def pick_prs(samples, seed: int, limit: int, max_change_lines: int = 10) -> list:
    """Seeded, reproducible PR subset. Rules (#631 plan §sample):
      1. only PRs that HAVE a label=1 sample are eligible (no expected set = no
         recall denominator — measuring it would fabricate a number);
      2. only PRs within `max_change_lines` diff size (the gate spans the diff;
         a 3000-line PR answer at 10x the token cost buys nothing for a sample);
      3. eligible PRs are shuffled with Random(seed) and the first `limit` taken.
    Determinism is the contract: same samples + seed + args ⇒ same PR list."""
    by_pr = {}
    for s in samples:
        url = s.get("pr_url") or ""
        by_pr.setdefault(url, []).append(s)
    eligible = sorted(
        url for url, ss in by_pr.items()
        if url and any(x.get("label") == 1 for x in ss)
        and min((x.get("pr_change_line_count") or 10**9) for x in ss) <= max_change_lines)
    rng = random.Random(seed)
    rng.shuffle(eligible)
    return eligible[:limit]


# ── ground-truth references ────────────────────────────────────────────────────
def reference_comments(samples: list) -> list:
    """The expected set — label=1 (expert-verified correct) comments only."""
    return [s for s in samples if s.get("label") == 1 and s.get("note")]


# ── four-stage deterministic matcher (mirrors aacr evaluation/judge.py) ─────────
def normalize_path(path) -> str:
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def parse_line(v) -> tuple:
    if v is None:
        return (None, None)
    if isinstance(v, int):
        return (v, v)
    s = str(v).strip()
    if "-" in s:
        lo, _, hi = s.partition("-")
        return (int(lo.strip()), int(hi.strip()))
    try:
        return (int(s), int(s))
    except ValueError:
        return (None, None)


def _line_edge(v, hi):
    """Resolve a line spec (int / "12" / "12-15" / (lo, hi) tuple) to one edge."""
    pair = v if isinstance(v, tuple) else parse_line(v)
    return pair[1] if hi else pair[0]


def diff_location_is_same(a_frm, a_to, b_frm, b_to, k: int = LINE_K) -> bool:
    """True iff [a_frm,a_to] overlaps [b_frm,b_to], or their min distance ≤ k.
    (AACR's `diff_location_is_same`.) Unparseable edges do not match."""
    a_lo, a_hi = _line_edge(a_frm, False), _line_edge(a_to, True)
    b_lo, b_hi = _line_edge(b_frm, False), _line_edge(b_to, True)
    if None in (a_lo, a_hi, b_lo, b_hi):
        return False
    if not (a_lo > b_hi or b_lo > a_hi):      # overlap
        return True
    return min(abs(a_lo - b_hi), abs(b_lo - a_hi)) <= k


def lexical_similar(note_a: str, note_b: str) -> bool:
    """AACR's mock semantics: SequenceMatcher(norm) >= 0.4 OR word-jaccard >= 0.3."""
    a, b = (note_a or "").lower(), (note_b or "").lower()
    if not a or not b:
        return False
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    if seq >= LEX_SEQ_RATIO:
        return True
    wa = set(re.findall(r"[a-zA-Z_]{3,}", a))
    wb = set(re.findall(r"[a-zA-Z_]{3,}", b))
    if wa and wb:
        if len(wa & wb) / len(wa | wb) >= LEX_JACCARD:
            return True
    return False


def _kept(findings: list) -> list:
    return [f for f in findings if f.get("verdict") in KEPT_VERDICTS]


# Signal tokens: identifiers long enough that a shared occurrence is unlikely
# accidental (function names, type names, error identifiers). Shorter words
# ("loop", "code", "this") co-occur by chance in any two code-review sentences.
def _signal_tokens(text) -> set:
    return {w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{4,}", (text or "").lower())}


def _shared_signal_token(ref_note, f_note) -> bool:
    return bool(_signal_tokens(ref_note) & _signal_tokens(f_note))


def match_results(references: list, findings: list) -> tuple:
    """Four-stage deterministic match of kept findings against references.
    Stage 4 is the semantic gate with a signature fallback:
      (a) AACR mock semantics (SequenceMatcher >= 0.4 OR jaccard >= 0.3), OR
      (b) a shared signal token (>=5-char identifier) — only among candidates
          that already passed path+side+line(k), so the fallback cannot bridge
          a finding at the right location about a DIFFERENT defect.
    Returns (matches, matched_count); matches is ordered per `references`, a
    reference matching more than one finding and a finding matching more than one
    reference are both forbidden (one-to-one). REFUTED findings are dropped first."""
    kept = _kept(findings)
    used = set()
    matches = []
    for ref in references:
        ref_path = normalize_path(ref.get("path"))
        ref_side = ref.get("side")
        ref_frm, ref_to = parse_line(ref.get("from_line")), parse_line(ref.get("to_line"))
        ref_note = ref.get("note") or ""
        best = None
        for idx, f in enumerate(kept):
            if idx in used:
                continue
            f_path = normalize_path(f.get("file"))
            if ref_path and f_path and ref_path != f_path:
                continue
            if ref_side is not None and f.get("side") is not None and ref_side != f.get("side"):
                continue
            f_frm, f_to = parse_line(f.get("from_line")), parse_line(f.get("to_line"))
            if not diff_location_is_same(ref_frm, ref_to, f_frm, f_to, LINE_K):
                continue
            f_note = f.get("summary") or f.get("note") or ""
            if not (lexical_similar(ref_note, f_note)
                    or _shared_signal_token(ref_note, f_note)):
                continue
            best = idx
            break
        if best is not None:
            used.add(best)
            matches.append((ref, kept[best], best))
    return matches, len(matches)


def metrics(references: list, findings: list, matched_count: int) -> dict:
    """Precision/recall/F1/noise per AACR-Bench formulas (docs/metrics.md):

    precision = matches / generated         (generated = KEPT findings only)
    recall    = matches / expected          (expected = label=1 references)
    f1        = 2pr/(p+r) (0 when p+r = 0)
    noise     = (generated − matches) / generated
    """
    generated = len(_kept(findings))
    expected = len(references)
    precision = (matched_count / generated) if generated else 0.0
    recall = (matched_count / expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    noise = ((generated - matched_count) / generated) if generated else 0.0
    return {"precision": precision, "recall": recall,
            "f1": f1, "noise": noise,
            "generated": generated, "expected": expected, "matched": matched_count}


def _f(x, nd=3):
    return f"{x:.{nd}f}"


def fmt_report(references: list, findings: list) -> str:
    matches, n_matched = match_results(references, findings)
    m = metrics(references, findings, n_matched)
    return (f"precision={_f(m['precision'])} recall={_f(m['recall'])} "
            f"f1={_f(m['f1'])} noise={_f(m['noise'])} "
            f"(matched {m['matched']}/{m['generated']} generated, "
            f"{m['matched']}/{m['expected']} expected)")


# ── live review + CLI (manual/periodic half) ───────────────────────────────────
import urllib.error
import urllib.request

GATE_PROMPT = """You must not use any thinking/reasoning; answer directly.
You are the crucible delve review-gate engine. Inspect the code \
diff below and report the genuine defects / issues a senior engineer would flag, \
using the crucible severity+verdict contract. For each issue emit a JSON object with \
exactly these keys: "file" (repo-relative path), "from_line" (int), "to_line" (int), \
"side" ("right"), "severity" ("Critical"|"Important"|"Minor"|"Suggestion"), \
"verdict" ("CONFIRMED"|"PLAUSIBLE"|"REFUTED"), "summary" (short technical \
explanation). Emit a JSON array of these objects — no prose around it. Do NOT invent \
issues the diff does not contain (no style nitpicks, no hypotheticals)."""

# Trailing user-content hammer for reasoning-capable backends (e.g. deepseek-v4*)
# that run away with the token budget otherwise. Experiment: without this line the
# model burns >5000 completion tokens on reasoning and never emits findings; with it,
# findings arrive inside the same budget. Measured on filament pull/15267 (dbg16).
GATE_NO_THINK_SUFFIX = "\n\nREPEAT: YOU MUST NOT THINK OR REASON. Output the JSON array only."


def fetch_pr_diff(pr_url: str, attempts: int = 4) -> str:
    """Fetch the PR's unified diff from github.com/pull/N.diff (no auth needed).
    Retries over HTTP 429 with exponential backoff (unauthenticated raw GitHub
    rate-limits on public `.diff` URLs)."""
    num = pr_url.rstrip("/").split("/pull/")[1]
    host = pr_url.split("/pull/")[0]
    url = f"{host}/pull/{num}.diff"
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and i < attempts - 1:
                time.sleep(2 ** i * 2)
                continue
            raise
    raise last or RuntimeError(f"unreachable: fetch {url}")


def ninerouter_client(base_url: str, key: str, model: str):
    """Return a `client(diff_text, model=model)` callable over the NINEROUTER
    OpenAI-compatible chat endpoint, including prompt/completion token usage.
    Retries over HTTP 429 (provider rate limits) with exponential backoff."""
    endpoint = f"{base_url}/v1/chat/completions"

    def client(diff_text, _model=None):
        body = json.dumps({
            "model": _model or model,
            "messages": [
                {"role": "system", "content": GATE_PROMPT},
                {"role": "user", "content": diff_text + GATE_NO_THINK_SUFFIX},
            ],
            "temperature": 0.0,
            "max_tokens": 12000,
        }).encode()
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})
        last = None
        for i in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    raw = r.read().decode("utf-8")
                resp = parse_chat_response(raw)
                text = resp["choices"][0]["message"]["content"] or ""
                usage = resp.get("usage") or {}
                return parse_findings_json(text), usage
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (429, 502) and i < 3:
                    time.sleep(2 ** i * 5)
                    continue
                raise
            except urllib.error.URLError as e:
                last = e
                # gateway blips: transient connect/reset, retry once
                if i < 3:
                    time.sleep(2 ** i * 4)
                    continue
                raise
        raise last or RuntimeError(f"unreachable: {endpoint}")  # pragma: no cover

    return client


def parse_chat_response(raw: str) -> dict:
    """Parse an OpenAI-compatible chat completion response. Some gateways append
    `data: [DONE]` / SSE-ish trailing lines; take the first complete JSON object."""
    raw = raw.strip()
    end = raw.find("data: [DONE]")
    if end != -1:
        raw = raw[:end].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start == -1:
            raise
        depth, i = 0, start
        while i < len(raw):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(raw[start:i + 1])
            i += 1
        raise


def parse_findings_json(text: str) -> list:
    """Extract the JSON findings array from a model reply, tolerating a bit of
    prose/```json fences around it. Unparseable ⇒ [] (counted, never crash)."""
    if not text:
        return []
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    start = t.find("[")
    end = t.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("summary")]


def aggregate(references: list, findings: list) -> dict:
    """Pooled metrics across PRs (same formulas as `metrics`)."""
    return metrics(references, findings, match_results(references, findings)[1])


def main(argv) -> int:
    args = argv[1:]
    if not args or args[0] != "run":
        sys.stderr.write(__doc__ or "")
        return 2
    opts = {"seed": None, "limit-prs": None, "model": None,
             "dataset": None, "out": None}
    it = iter(args[1:])
    for a in it:
        if not a.startswith("--") or a[2:] not in opts:
            sys.stderr.write(f"unknown argument {a!r}\n{__doc__}")
            return 2
        opts[a[2:]] = next(it, None)
    required = ("dataset", "out")
    if any(opts.get(k) is None for k in required):
        sys.stderr.write("run requires --dataset and --out\n")
        return 2
    seed = int(opts.get("seed") or 631)
    limit = int(opts.get("limit-prs") or 8)
    model = opts.get("model") or "cc/claude-opus-5"
    dataset_path = pathlib.Path(opts["dataset"] or "")
    out_dir = pathlib.Path(opts["out"] or "")
    base_url = os.environ.get("NINEROUTER_URL", "")
    key = os.environ.get("NINEROUTER_KEY", "")
    if not base_url or not key:
        sys.stderr.write("NINEROUTER_URL / NINEROUTER_KEY must be set\n")
        return 1

    samples = json.loads(dataset_path.read_text())
    prs = pick_prs(samples, seed=seed, limit=limit)
    if not prs:
        sys.stderr.write("no eligible PRs (need label=1 comments)\n")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_dir = out_dir / "diffs"
    diff_dir.mkdir(exist_ok=True)
    record_dir = out_dir / "records"
    record_dir.mkdir(exist_ok=True)
    client = ninerouter_client(base_url, key, model)
    sys.stdout.write(f"seed={seed} limit-prs={limit} model={model}\n")
    sys.stdout.write("reviewing: " + ", ".join(p.split("/pull/")[1] for p in prs) + "\n")
    agg_refs, agg_findings = [], []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    pr_results = {}

    def slug(url):
        return url.rstrip("/").split("/pull/")[1]

    for url in prs:
        refs = reference_comments([s for s in samples if s.get("pr_url") == url])
        record_path = record_dir / f"{slug(url)}.json"
        if record_path.exists():            # resume: PR already reviewed
            rec = json.loads(record_path.read_text())
            findings = rec["findings"]
            usage = rec["usage"]
        else:
            diff_path = diff_dir / f"{slug(url)}.diff"
            if diff_path.exists():
                diff = diff_path.read_text()
            else:
                try:
                    diff = fetch_pr_diff(url)
                except (urllib.error.URLError, urllib.error.HTTPError) as e:
                    sys.stderr.write(f"fetch {url} failed: {e}\n")
                    continue
                diff_path.write_text(diff)
            findings = []
            usage = {}
            try:
                findings, usage = client(diff, model)
            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                sys.stderr.write(f"review {url} failed: {e}\n")
            record_path.write_text(json.dumps(
                {"findings": findings, "usage": usage}, indent=2) + "\n")
        agg_refs += refs
        agg_findings += findings
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total_usage[k] += int(usage.get(k) or 0)
        m = metrics(refs, findings, match_results(refs, findings)[1])
        pr_results[url] = {
            "references": len(refs),
            "kept_findings": len([f for f in findings if f.get("verdict") in KEPT_VERDICTS]),
            "raw_findings": len(findings),
            "metrics": m,
            "usage": usage,
        }
        sys.stdout.write(f"{url}  refs={len(refs)} kept={m['generated']} "
                         f"{fmt_report(refs, findings)}\n")

    agg_m = aggregate(agg_refs, agg_findings)
    result = {
        "seed": seed, "model": model, "limit_prs": limit,
        "dataset": str(dataset_path),
        "aggregate": agg_m,
        "usage": total_usage,
        "per_pr": pr_results,
    }
    result_path = out_dir / "results.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    sys.stdout.write("\nAGGREGATE  " + fmt_report(agg_refs, agg_findings) + "\n")
    sys.stdout.write(f"token usage: {total_usage['total_tokens']} total "
                     f"({total_usage['prompt_tokens']} prompt, "
                     f"{total_usage['completion_tokens']} completion)\n")
    sys.stdout.write(f"written: {result_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))