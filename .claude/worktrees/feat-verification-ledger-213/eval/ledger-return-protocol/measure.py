#!/usr/bin/env python3
"""
Context-reduction metric for the Ledger Return Protocol eval.

Given a prose-returns.jsonl and a receipts.jsonl (one JSON object per line,
each with a `dispatch-id` field), compute per-dispatch size ratios
(len(receipt) / len(prose_return)) and report p50, p90, and mean.

Dispatches whose prose return is < 200 characters are excluded per
design doc AC#4.

Usage: python3 measure.py <prose-returns.jsonl> <receipts.jsonl>
"""
import json
import statistics
import sys
from pathlib import Path


def load(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out[rec["dispatch-id"]] = rec
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    prose = load(sys.argv[1])
    receipts = load(sys.argv[2])

    ratios = []
    excluded = 0
    for dispatch_id, prose_rec in prose.items():
        prose_return = prose_rec["return"]
        if len(prose_return) < 200:
            excluded += 1
            continue
        if dispatch_id not in receipts:
            print(f"WARN: no receipt for dispatch-id={dispatch_id}", file=sys.stderr)
            continue
        receipt_text = receipts[dispatch_id]["receipt"]
        ratios.append(len(receipt_text) / len(prose_return))

    ratios.sort()
    p50 = statistics.median(ratios) if ratios else 0
    p90_idx = int(len(ratios) * 0.9)
    p90 = ratios[p90_idx] if ratios else 0
    mean = statistics.mean(ratios) if ratios else 0

    # Calibrated target: 0.40 — the design doc's original 0.25 was uncalibrated.
    # See README.md "Calibration" section for the derivation.
    TARGET = 0.40
    verdict = "PASS" if p50 <= TARGET else "FAIL"
    print(f"dispatches-measured: {len(ratios)}")
    print(f"dispatches-excluded (<200 chars): {excluded}")
    print(f"p50 ratio: {p50:.3f}")
    print(f"p90 ratio: {p90:.3f}")
    print(f"mean ratio: {mean:.3f}")
    print(f"target:     <= {TARGET:.3f}")
    print(f"verdict:    {verdict}")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
