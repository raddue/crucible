#!/usr/bin/env python3
"""
Reference implementation of the Verification Ledger assembler (issue #213).

This is an eval artifact — the canonical assembler lives as prose in
skills/recon/SKILL.md Phase 3 "Ledger Assembly". This Python version lets the
test suite confirm the assembly rules, dedup (Jaccard + union-find), and
Phase 5 grep behave as specified.

Per DEC-2 / AMB-1: the ledger is a reader-friendly markdown convention, NOT
a regex-enforced contract. The regexes in this scorer are INTERNAL to the
reference implementation; they are NOT a grammar/contract on the ledger
output format. The authoritative contract is the diff against the expected
fixture files plus the inline assertions in run-eval.sh.

Usage:
  python3 ledger_scorer.py assemble <scout-report-bundle.md>
  python3 ledger_scorer.py phase5-grep <directory>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Canonical Causal Keyword Set — mirrors skills/recon/SKILL.md "### Causal Keyword Set".
CAUSAL_KEYWORDS = [
    "fixes", "causes", "is the bug", "is the fix", "will resolve",
    "root cause is", "caused by", "resolved by", "because", "due to",
    "leads to", "responsible for", "the culprit", "breaks because",
    "stems from", "triggers", "originates", "accounts for",
    "cascades from", "propagates from", "results in", "arises from",
    "comes from", "introduced by", "source of", "→", "explains why",
]
# Phrase patterns with `*` allow up to 5 intervening words between the anchors.
PHRASE_PATTERNS = [("the reason", "is"), ("is why", "fails")]

# Small stoplist for token normalization used by Jaccard — keeps dedup robust
# against trivial articles/connectives without needing an NLP stack.
STOPLIST = {
    "a", "an", "the", "is", "are", "was", "were", "of", "for",
    "and", "or", "to", "in", "on", "with", "at", "by", "this", "that",
    "it", "its", "be", "been",
}

EVIDENCE_TAG = re.compile(r"\[evidence:\s*([a-z-]+)\s*:\s*([^\]]+?)\]", re.I)
DEMOTED_TAG = re.compile(r"\[demoted\]", re.I)
CONFIDENCE_TAG = re.compile(r"\[confidence:\s*[^\]]+\]", re.I)

PLACEHOLDER = (
    "<!-- Records causal claims made by this brief (populated this run). "
    "Falsifications flow via handoff-doc entries under docs/handoffs/ per "
    "the convention in skills/recon/SKILL.md. -->"
)


def normalize_tokens(text: str) -> set[str]:
    """Lowercase, strip punctuation, strip bracketed tags, split → token set."""
    # Strip bracketed tags so [evidence: ...] and [confidence: ...] don't
    # contaminate the Jaccard comparison (they are metadata, not claim).
    no_brackets = re.sub(r"\[[^\]]*\]", " ", text)
    tokens = re.findall(r"[a-z0-9]+", no_brackets.lower())
    return {t for t in tokens if t not in STOPLIST}


def jaccard_tokens(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a and not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def has_causal_keyword(text: str) -> bool:
    lower = text.lower()
    for kw in CAUSAL_KEYWORDS:
        if kw == "→":
            if "→" in lower:
                return True
            continue
        # word-boundary semantics; \b works for ASCII word chars (keywords here are ASCII).
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, lower):
            return True
    for a, b in PHRASE_PATTERNS:
        pattern = r"\b" + re.escape(a) + r"\b(?:\s+\w+){0,5}\s+\b" + re.escape(b) + r"\b"
        if re.search(pattern, lower):
            return True
    return False


def extract_claims(text: str, scout_name: str, start_idx: int = 0) -> list[dict]:
    """Parse scout report text → list of claim dicts.

    Each claim dict carries an explicit `_idx` (absolute ingestion index =
    start_idx + local bullet-position). This field is load-bearing for
    idempotent output ordering (Check 7).

    Why `_idx` exists: two byte-identical claim dicts compare equal under
    dict `__eq__`, so `list.index(c)` would collapse them to the first
    occurrence and produce unstable group ordering across runs. Stamping
    `_idx` at parse time keeps group sort keys deterministic even when a
    future fixture introduces identical-content claims from both scouts.
    """
    claims: list[dict] = []
    local_idx = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:]
        if not has_causal_keyword(body):
            continue
        m = EVIDENCE_TAG.search(body)
        method, anchor = (None, None)
        if m:
            method = m.group(1).lower()
            anchor = m.group(2).strip()
        demoted = bool(DEMOTED_TAG.search(body))
        # Produce display text: strip evidence/confidence/demoted tags.
        display = body
        display = EVIDENCE_TAG.sub("", display)
        display = CONFIDENCE_TAG.sub("", display)
        display = DEMOTED_TAG.sub("", display)
        display = re.sub(r"\s+", " ", display).strip()
        claims.append({
            "text": display,
            "scout": scout_name,
            "evidence_method": method,
            "evidence_anchor": anchor,
            "demoted": demoted,
            "_idx": start_idx + local_idx,
        })
        local_idx += 1
    return claims


def union_find_merge(claims: list[dict], threshold: float = 0.70) -> list[list[dict]]:
    """Union-find over pairwise token-Jaccard ≥ threshold. Return groups."""
    n = len(claims)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    tokens = [normalize_tokens(c["text"]) for c in claims]
    for i in range(n):
        for j in range(i + 1, n):
            if jaccard_tokens(tokens[i], tokens[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(claims[i])
    return list(groups.values())


def resolve_entry(group: list[dict], ordinal: int) -> dict:
    """Determine method, anchor, disposition for a merged claim group.

    Precedence (per skills/recon/SKILL.md Phase 3 Ledger Assembly step 3):
    1. any_structural_only → method=structural-only, disposition=awaiting
       (beats dual-scout override).
    2. dual_scout (both scouts present, no structural-only) →
       method=dual-scout, disposition=confirmed. Unconditional — no tag guard.
    3. single-scout tag available → method/anchor from pattern tag if present
       (else structure tag); disposition=demoted iff all group members are
       demoted, else confirmed. (Pattern-scout tag preferred as the
       richer-conventions anchor.)
    4. No tags → method=none, evidence=—, disposition per demoted-all rule.
    """
    any_structural_only = any(c["evidence_method"] == "structural-only" for c in group)
    scouts = {c["scout"] for c in group}
    dual_scout = len(scouts) == 2

    pattern_tag = next(
        (c for c in group
         if c["scout"] == "pattern" and c["evidence_method"]
         and c["evidence_method"] != "structural-only"),
        None,
    )
    structure_tag = next(
        (c for c in group
         if c["scout"] == "structure" and c["evidence_method"]
         and c["evidence_method"] != "structural-only"),
        None,
    )

    if any_structural_only:
        tag = next(c for c in group if c["evidence_method"] == "structural-only")
        method = "structural-only"
        anchor = tag["evidence_anchor"]
        disposition = "awaiting"
    elif dual_scout:
        method = "dual-scout"
        anchor = "structure-scout, pattern-scout"
        disposition = "confirmed"
    elif pattern_tag or structure_tag:
        chosen = pattern_tag or structure_tag
        method = chosen["evidence_method"]
        anchor = chosen["evidence_anchor"]
        disposition = "demoted" if all(c["demoted"] for c in group) else "confirmed"
    else:
        method = "none"
        anchor = "—"
        disposition = "demoted" if all(c["demoted"] for c in group) else "confirmed"

    # Canonical display text = first claim in group (by ingestion order).
    group_sorted = sorted(group, key=lambda c: c["_idx"])
    text = group_sorted[0]["text"]
    return {
        "ord": ordinal, "text": text, "method": method,
        "anchor": anchor, "disposition": disposition,
    }


def format_ordinal(n: int) -> str:
    # Zero-padded 2 digits for n ≤ 99, natural 3+ digits past 100
    # (informational overflow per SKILL.md).
    return f"{n:02d}" if n <= 99 else str(n)


def assemble_ledger(structure_text: str, pattern_text: str) -> str:
    structure_claims = extract_claims(structure_text, "structure", start_idx=0)
    pattern_claims = extract_claims(
        pattern_text, "pattern", start_idx=len(structure_claims)
    )
    claims = structure_claims + pattern_claims
    groups = union_find_merge(claims)
    groups.sort(key=lambda g: min(c["_idx"] for c in g))

    if not groups:
        return f"## Verification Ledger\n{PLACEHOLDER}\n"

    lines = ["## Verification Ledger", PLACEHOLDER, ""]
    for i, group in enumerate(groups, start=1):
        e = resolve_entry(group, i)
        lines.append(
            f"- **L-{format_ordinal(e['ord'])}** — {e['text']} — "
            f"method: `{e['method']}`, evidence: `{e['anchor']}`, "
            f"disposition: `{e['disposition']}`"
        )
    return "\n".join(lines) + "\n"


def split_scout_reports(text: str) -> tuple[str, str]:
    """Split a bundle file into (structure_body, pattern_body).

    Expects headings `## STRUCTURE SCOUT REPORT` and `## PATTERN SCOUT REPORT`.
    """
    parts = re.split(
        r"(?m)^## (?:STRUCTURE|PATTERN) SCOUT REPORT\s*$", text
    )
    structure = parts[1] if len(parts) > 1 else ""
    pattern = parts[2] if len(parts) > 2 else ""
    return structure, pattern


def cmd_assemble(inputs: list[Path]) -> str:
    if len(inputs) == 1:
        bundle = inputs[0].read_text(encoding="utf-8")
        structure, pattern = split_scout_reports(bundle)
    elif len(inputs) == 2:
        structure = inputs[0].read_text(encoding="utf-8")
        pattern = inputs[1].read_text(encoding="utf-8")
    else:
        raise SystemExit("assemble takes 1 (bundle) or 2 (structure+pattern) inputs")
    return assemble_ledger(structure, pattern)


def cmd_phase5_grep(directory: Path) -> list[str]:
    hits: list[str] = []
    for md in sorted(Path(directory).rglob("*.md")):
        try:
            content = md.read_text(encoding="utf-8")
        except OSError:
            continue
        in_fence = False
        for line in content.splitlines():
            if re.match(r"^\s*`{3,}", line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            cleaned = re.sub(r"^(\s*[-*+>]\s*)+", "", line).strip()
            if cleaned.startswith("Recon claim falsified:"):
                hits.append(f"LANDMINE: {cleaned}")
    return hits


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    ap = sub.add_parser("assemble")
    ap.add_argument("inputs", nargs="+", type=Path)
    gp = sub.add_parser("phase5-grep")
    gp.add_argument("directory", type=Path)
    args = p.parse_args(argv)
    if args.mode == "assemble":
        sys.stdout.write(cmd_assemble(args.inputs))
        return 0
    if args.mode == "phase5-grep":
        for line in cmd_phase5_grep(args.directory):
            print(line)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
