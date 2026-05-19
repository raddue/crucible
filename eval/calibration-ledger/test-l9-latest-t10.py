#!/usr/bin/env python3
"""T-10a: L-9 latest-entry-wins helper (file-position authoritative).

Direct unit test of scripts.ledger_reduce.reduce(). No subprocesses.

Assertions:
  1. Two entries, same hash, in append order entry-1 → entry-2 → reduce returns entry-2.
  2. Three entries (1 → 2 → 3) → returns entry-3.
  3. Distinct hashes do not collide; latest per key wins.
  4. Empty file → {}.
  5. Trailing partial line (no newline at EOF) → silently skipped; last terminated wins.
  6. Polarity: timestamp ordering is NOT used — file position is authoritative.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def _write_lines(path, entries, terminate_last=True):
    with open(path, "w", encoding="utf-8") as f:
        for i, e in enumerate(entries):
            f.write(json.dumps(e))
            if i < len(entries) - 1 or terminate_last:
                f.write("\n")


def test_two_entries_same_hash():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-1-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        e1 = {"ledger_entry_hash": "hash-A", "falsified_by": {"commit": "aaa"}}
        e2 = {"ledger_entry_hash": "hash-A", "falsified_by": {"commit": "bbb"}}
        _write_lines(p, [e1, e2])
        out = reduce(p)
        _check("T-10a.1 two entries same hash → returns entry-2",
               out["hash-A"]["falsified_by"]["commit"] == "bbb",
               f"got {out['hash-A']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_three_entries_same_hash():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-2-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        es = [
            {"ledger_entry_hash": "hash-B", "falsified_by": {"commit": "c1"}},
            {"ledger_entry_hash": "hash-B", "falsified_by": {"commit": "c2"}},
            {"ledger_entry_hash": "hash-B", "falsified_by": {"commit": "c3"}},
        ]
        _write_lines(p, es)
        out = reduce(p)
        _check("T-10a.2 three entries same hash → returns entry-3",
               out["hash-B"]["falsified_by"]["commit"] == "c3")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_distinct_hashes_no_collision():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-3-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        es = [
            {"ledger_entry_hash": "h1", "falsified_by": {"commit": "x1"}},
            {"ledger_entry_hash": "h2", "falsified_by": {"commit": "y1"}},
            {"ledger_entry_hash": "h1", "falsified_by": {"commit": "x2"}},
            {"ledger_entry_hash": "h2", "falsified_by": {"commit": "y2"}},
        ]
        _write_lines(p, es)
        out = reduce(p)
        cond = (len(out) == 2
                and out["h1"]["falsified_by"]["commit"] == "x2"
                and out["h2"]["falsified_by"]["commit"] == "y2")
        _check("T-10a.3 distinct hashes: latest per key wins", cond,
               f"got {out}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_empty_file():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-4-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        open(p, "w").close()
        _check("T-10a.4 empty file → {}", reduce(p) == {})
        # missing path also
        _check("T-10a.4 missing path → {}", reduce(os.path.join(tmp, "nope.jsonl")) == {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_partial_trailing_line():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-5-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        # First entry terminated; second is partial (no trailing newline) and intentionally broken.
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ledger_entry_hash": "h-part", "falsified_by": {"commit": "complete"}}))
            f.write("\n")
            f.write('{"ledger_entry_hash":"h-part","falsified_by":{"commit":"part')  # no newline, truncated
        out = reduce(p)
        _check("T-10a.5 trailing partial line skipped; last terminated wins",
               out.get("h-part", {}).get("falsified_by", {}).get("commit") == "complete",
               f"got {out}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_polarity_file_position_over_timestamp():
    from scripts.ledger_reduce import reduce
    tmp = tempfile.mkdtemp(prefix="t10a-6-")
    p = os.path.join(tmp, "f.jsonl")
    try:
        # entry-2 has LATER timestamp than entry-3, but entry-3 is later by file position.
        # File-position must win.
        es = [
            {"ledger_entry_hash": "hP", "falsified_by": {"commit": "first"},  "timestamp": "2026-01-01T00:00:00Z"},
            {"ledger_entry_hash": "hP", "falsified_by": {"commit": "middle"}, "timestamp": "2026-12-31T00:00:00Z"},  # latest TS
            {"ledger_entry_hash": "hP", "falsified_by": {"commit": "last"},   "timestamp": "2026-06-01T00:00:00Z"},  # earlier TS than middle
        ]
        _write_lines(p, es)
        out = reduce(p)
        _check("T-10a.6 file-position wins over timestamp",
               out["hP"]["falsified_by"]["commit"] == "last",
               f"got {out['hP']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_two_entries_same_hash()
    test_three_entries_same_hash()
    test_distinct_hashes_no_collision()
    test_empty_file()
    test_partial_trailing_line()
    test_polarity_file_position_over_timestamp()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
