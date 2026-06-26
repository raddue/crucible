---
version: 1
---

# Ledger Reduce Protocol (L-9 latest-entry-wins)

> Canonical reader-side reduction over `~/.claude/crucible/ledger/falsification.jsonl` (override `CRUCIBLE_LEDGER_DIR`).
> Cited via `<!-- CANONICAL: shared/ledger-reduce.md -->` from
> `/calibration-reconcile` (Phase 4) and `/ledger` (Phase 5). T-10b (Phase 5)
> grep-asserts both call-sites carry that citation.
>
> Protocol-as-spec. The importable single source of truth is
> `scripts/ledger_reduce.py`, inlined verbatim below.

## Polarity (load-bearing)

**File-position ordering is authoritative — NOT the `timestamp` field.**

A late-arriving entry (later byte position in `falsification.jsonl`) overwrites
an earlier entry with the same `ledger_entry_hash`. Out-of-order `timestamp`
fields (clock skew across machines, manual edits, batched backfill) do NOT
flip the precedence: the reader walks line-by-line and the **last fully-
terminated line per key wins**.

This polarity is testable as T-10a: `eval/calibration-ledger/test-l9-latest-t10.py`.

## Tolerant read rules

- **Missing file** → return `{}`.
- **Empty file** → return `{}`.
- **Trailing partial line** (file does not end with `\n`) → silently skipped;
  the last fully-terminated entry wins for that key. The next reconciler run
  will pick up the completed line after the writer flushes.
- **Unparseable line** (invalid JSON, decoding error) → skipped; reduction
  continues with subsequent lines.
- **Entry without `ledger_entry_hash`** → skipped.

## Reference Python — `scripts/ledger_reduce.py`

```python
#!/usr/bin/env python3
"""L-9 latest-entry-wins reduction over falsification.jsonl.

File-position ordering is authoritative — NOT the `timestamp` field.
"""
import json
import os
import sys
from typing import Dict


def reduce(falsification_path: str) -> Dict[str, dict]:
    """Return dict keyed by ledger_entry_hash with the latest entry per hash."""
    if not os.path.exists(falsification_path):
        return {}
    try:
        with open(falsification_path, "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    if not raw:
        return {}
    parts = raw.split(b"\n")
    ends_with_newline = raw.endswith(b"\n")
    if not ends_with_newline:
        parts = parts[:-1]
    out: Dict[str, dict] = {}
    for chunk in parts:
        if not chunk:
            continue
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        key = obj.get("ledger_entry_hash")
        if key is None:
            continue
        out[key] = obj  # later positions overwrite earlier ones (L-9)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: ledger_reduce.py <falsification.jsonl>", file=sys.stderr)
        sys.exit(2)
    result = reduce(sys.argv[1])
    json.dump(result, sys.stdout, indent=2)
    print()
```

The canonical importable module is `scripts/ledger_reduce.py`
(`scripts.ledger_reduce`). T-10a unit-tests `reduce()` directly.
Phase 4 (`/calibration-reconcile`) and Phase 5 (`/ledger`) invoke
`reduce()` from this module.
