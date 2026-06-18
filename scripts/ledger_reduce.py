#!/usr/bin/env python3
"""L-9 latest-entry-wins reduction over falsification.jsonl.

File-position ordering is authoritative — NOT the `timestamp` field. A late-arriving
fix-up entry overwrites an earlier one with the same `ledger_entry_hash`.

Canonical executable form of the protocol-as-spec in skills/shared/ledger-reduce.md.
"""
import json
import os
import sys
from typing import Dict


def _warn(msg: str) -> None:
    print(f"[ledger_reduce WARN] {msg}", file=sys.stderr)


def reduce(falsification_path: str) -> Dict[str, dict]:
    """Return dict keyed by ledger_entry_hash with the latest entry per hash.

    Tolerant read: trailing partial line (no terminating newline) is silently skipped.
    Missing file → {}. Empty file → {}.
    """
    if not os.path.exists(falsification_path):
        return {}
    try:
        with open(falsification_path, "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    if not raw:
        return {}

    # Split on newline; if the file does NOT end with \n, the last element is a
    # partial trailing line and is dropped. Otherwise the trailing empty element
    # from the split is naturally falsy and skipped.
    parts = raw.split(b"\n")
    ends_with_newline = raw.endswith(b"\n")
    if not ends_with_newline:
        parts = parts[:-1]

    out: Dict[str, dict] = {}
    skipped = 0  # #400: surface corruption instead of degrading silently
    for chunk in parts:
        if not chunk:
            continue
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if not isinstance(obj, dict):
            # #400: a valid-JSON-but-non-object line (e.g. `[1,2,3]`, `42`) has
            # no `.get` — the obj.get below would AttributeError. Count it as
            # corruption, same as render_ledger.load_runs.
            skipped += 1
            continue
        key = obj.get("ledger_entry_hash")
        if key is None:
            continue
        out[key] = obj  # later positions overwrite earlier ones (L-9)
    if skipped:
        _warn(f"reduce: skipped {skipped} unparseable line(s) in {falsification_path}")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: ledger_reduce.py <falsification.jsonl>", file=sys.stderr)
        sys.exit(2)
    result = reduce(sys.argv[1])
    json.dump(result, sys.stdout, indent=2)
    print()
