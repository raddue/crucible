"""The deterministic matcher/oracle for the delve eval harness (#373).

LLM-free, pure, stdlib-only — this is the CI-gated half of the harness (the scorer),
so its arithmetic is pinned by test_matcher.py. It takes a recorded delve findings
list + a ground-truth planted-bug list and computes recall + false-positive rate.

A finding F matches a planted bug B iff ALL hold (design §"The deterministic matcher"):
  1. same file (repo-relative POSIX, normalized).
  2. line overlap: F's line (int or "lo-hi") ∩ [B.line_lo - slop, B.line_hi + slop].
  3. signature gate: ≥1 of B.signature (lowercased substring tokens) appears in F's
     summary (falling back to failure_scenario). This cuts positional false-positives
     — a finding at the right line about the WRONG defect does not score.

Matching is bipartite, one-to-one: each planted bug is credited at most once and each
finding consumed at most once, so two findings on one bug don't inflate recall and one
finding spanning two bugs doesn't double-count. Resolution is MAXIMUM-CARDINALITY
(augmenting-path / Kuhn's algorithm) so recall is never understated by a greedy choice
consuming a finding/bug that a unique edge needed. Determinism: candidate edges are
visited in the existing ranked order ((line-overlap size, signature-hit count)
descending, tie-broken by bug_id then finding index), so among all maximum matchings a
stable, high-weight, reproducible one is returned.
"""
from __future__ import annotations
from dataclasses import dataclass

_DEFAULT_LINE_SLOP = 2


@dataclass(frozen=True)
class MatchResult:
    matched: list            # list[(bug_id, finding_idx)]
    recall: float
    false_positive_rate: float
    unmatched_bugs: list     # list[bug_id]
    unmatched_findings: list  # list[int]


def normalize_file(path: str) -> str:
    """Normalize a file path to repo-relative POSIX form for comparison: backslashes
    → forward slashes, a leading `./` stripped. Pure string transform (no filesystem)."""
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def parse_line(v) -> tuple:
    """Parse a finding/bug line spec into an inclusive (lo, hi) int tuple. Accepts an
    int (12), a numeric string ("12"), or a range string ("12-15", whitespace ok)."""
    if isinstance(v, int):
        return (v, v)
    s = str(v).strip()
    if "-" in s:
        lo, _, hi = s.partition("-")
        return (int(lo.strip()), int(hi.strip()))
    n = int(s)
    return (n, n)


def _overlap(a_lo: int, a_hi: int, b_lo: int, b_hi: int) -> int:
    """Size of the inclusive integer overlap of [a_lo,a_hi] and [b_lo,b_hi]; 0 if
    disjoint. A single-line touch (a_lo==a_hi inside the range) counts as 1."""
    lo = max(a_lo, b_lo)
    hi = min(a_hi, b_hi)
    return (hi - lo + 1) if hi >= lo else 0


def _signature_hits(bug: dict, finding: dict) -> int:
    """Count how many of bug['signature'] tokens (lowercased substring) appear in the
    finding's summary OR its failure_scenario fallback. The two fields are searched as
    one lowercased haystack so a signature recorded only in failure_scenario still
    scores (design §"signature gate": present in summary and/or failure_scenario)."""
    text = ((finding.get("summary") or "") + "\n"
            + (finding.get("failure_scenario") or "")).lower()
    return sum(1 for tok in bug.get("signature", []) if str(tok).lower() in text)


def match(findings: list, ground_truth: list,
          line_slop: int = _DEFAULT_LINE_SLOP) -> MatchResult:
    """Bipartite one-to-one match of recorded findings against planted bugs.

    Returns a MatchResult with the matched (bug_id, finding_idx) pairs, recall,
    false-positive rate, and the unmatched bug ids + finding indices."""
    # Build every candidate edge (bug, finding) that satisfies all three gates,
    # carrying the overlap size + signature hit count for ranking.
    candidates = []  # (overlap, sig_hits, bug_id, finding_idx)
    for bug in ground_truth:
        b_lo = bug["line_lo"] - line_slop
        b_hi = bug["line_hi"] + line_slop
        b_file = normalize_file(bug["file"])
        for fi, finding in enumerate(findings):
            if normalize_file(finding.get("file", "")) != b_file:
                continue
            try:
                f_lo, f_hi = parse_line(finding.get("line"))
            except (ValueError, TypeError):
                # A recorded finding with an unparseable `line` (None, "", "abc",
                # "12-", "3.7", …) yields NO candidate edge here, so it is never
                # matched to any bug — the n_findings/used_findings arithmetic below
                # then counts it as a kept-but-unmatched finding (a false positive),
                # rather than crashing the whole score. `parse_line` stays fail-loud
                # for direct callers; only this candidate build degrades gracefully.
                continue
            ov = _overlap(f_lo, f_hi, b_lo, b_hi)
            if ov <= 0:
                continue
            hits = _signature_hits(bug, finding)
            if hits <= 0:
                continue
            candidates.append((ov, hits, bug["bug_id"], fi))

    # Maximum-cardinality bipartite matching by augmenting paths (Kuhn's algorithm).
    # Candidate edges are ranked best-first (largest overlap, then most signature
    # hits), deterministic tie-break by bug_id then finding index. Processing bugs in
    # that ranked order makes the result deterministic and high-weight among all
    # maximum matchings; the augmenting search guarantees the cardinality is maximal,
    # so a high-weight edge never starves a unique low-weight edge.
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2], c[3]))

    # Adjacency in ranked order: for each bug, its candidate finding indices, and the
    # bug visitation order — both first-seen order over the sorted candidate list.
    adj: dict = {}
    bug_order = []
    for _ov, _hits, bug_id, fi in candidates:
        if bug_id not in adj:
            adj[bug_id] = []
            bug_order.append(bug_id)
        adj[bug_id].append(fi)

    finding_to_bug: dict = {}  # finding_idx -> bug_id currently matched to it

    def _augment(bug_id, visited) -> bool:
        for fi in adj[bug_id]:
            if fi in visited:
                continue
            visited.add(fi)
            holder = finding_to_bug.get(fi)
            if holder is None or _augment(holder, visited):
                finding_to_bug[fi] = bug_id
                return True
        return False

    for bug_id in bug_order:
        _augment(bug_id, set())

    # Reconstruct matched pairs in the deterministic bug visitation order.
    bug_to_finding = {b: f for f, b in finding_to_bug.items()}
    matched = [(bug_id, bug_to_finding[bug_id])
               for bug_id in bug_order if bug_id in bug_to_finding]
    used_bugs = set(bug_to_finding)
    used_findings = set(finding_to_bug)

    n_bugs = len(ground_truth)
    n_findings = len(findings)
    recall = (len(matched) / n_bugs) if n_bugs else 1.0
    n_unmatched_findings = n_findings - len(used_findings)
    fp_rate = (n_unmatched_findings / n_findings) if n_findings else 0.0
    unmatched_bugs = [b["bug_id"] for b in ground_truth
                      if b["bug_id"] not in used_bugs]
    unmatched_findings = [i for i in range(n_findings) if i not in used_findings]

    return MatchResult(
        matched=matched,
        recall=recall,
        false_positive_rate=fp_rate,
        unmatched_bugs=unmatched_bugs,
        unmatched_findings=unmatched_findings,
    )
