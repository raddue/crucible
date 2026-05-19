---
version: 1
---

# Ledger Append Protocol (canonical)

> Canonical write-protocol prompt for the Crucible calibration ledger
> (`.crucible/ledger/runs.jsonl`). Referenced by every gating skill that emits a
> calibration entry via `<!-- CANONICAL: shared/ledger-append.md -->`.
>
> This file is the **protocol-as-spec**. The importable single source of truth
> is `scripts/ledger_append.py`, inlined verbatim below.

## When to emit

Emit one JSONL line to `.crucible/ledger/runs.jsonl` at terminal verdict
emission (after the verdict marker has been written; the two writes are
independent — marker durability and ledger durability are not interlocked).
Dedup by `(run_id, skill)` before append: callers MUST invoke
`scripts.ledger_append.caller_dedup(ledger_path, run_id, skill)` and skip
the emit if it returns True. The `append()` helper does **not** scan the
ledger for prior entries — honoring L-2 is the caller's responsibility.
Append is idempotent across retries only when callers honor this discipline.

Read in-process verdict state directly. Do **not** re-parse the on-disk marker
file: parse-roundtrip drift is a real failure mode and the dedup check makes
double-emit harmless.

## Kill-switch (L-6) — emit-side enforcement

`CRUCIBLE_CALIBRATION_DISABLED=1` ⇒ the emit path is a **no-op return BEFORE
any lock acquisition or filesystem state change**. No mkdir, no holder write,
no append. This is the first check in the protocol.

The kill-switch is a **fixture-isolation guard**, not a bootstrap-wide
silencer. Real Crucible runs against real artifacts during Phases 2–7 SHOULD
emit normally — that data is the entire point. Only set the env var when
running against test fixtures, eval corpora, or CI smoke tests that would
otherwise pollute the ledger. See `docs/CONTRIBUTING-CALIBRATION.md`.

## Schema v1 (22 fields)

```json
{
  "schema_version": 1,
  "run_id": "<UUIDv7 — sortable, millisecond-precision, unique>",
  "skill": "quality-gate | red-team | siege | inquisitor | audit",
  "tier": "A | B",
  "artifact_type": "code | design | plan | hypothesis | mockup | translation | other",
  "verdict": "PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION",
  "confidence": 0.00,
  "artifact_hash": "<sha256 hex64 of gated artifact, from existing ArtifactHash field>",
  "chunk_hash": "<sha256 or null>",
  "gated_files": ["path/relative/to/repo/root", "..."],
  "findings_count": 0,
  "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
  "highest_finding": "<one-line quote or null>",
  "would_have_shipped_without_gate": true,
  "rounds": 1,
  "timestamp": "<ISO-8601 utc>",
  "backfilled": false,
  "falsified": null,
  "falsified_by": null,
  "gated_files_truncated": 0,
  "comment": null,
  "predicted_falsifier": null
}
```

### `artifact_type` enum (canonical)

Exactly seven values: `['code', 'design', 'plan', 'hypothesis', 'mockup', 'translation', 'other']`.

### Tier-B null semantics

Tier B emitters (`red-team`, `audit`, `inquisitor`) emit the schema-required
keys **explicitly set to `null`** — not absent — so v1 readers do not have to
branch on missing keys. The required explicit-nulls on Tier B stubs are:

- `severity_histogram: null`
- `highest_finding: null`
- `would_have_shipped_without_gate: null`
- `findings_count: null`
- `confidence: null`
- `chunk_hash: null`
- `rounds: null`
- `predicted_falsifier: null`

Tier B stubs also set `gated_files_truncated: 0` (explicit) and `comment: null`.

### Mechanical WHS rule (L-3)

`would_have_shipped_without_gate = (severity_histogram.fatal + severity_histogram.significant) >= 1`
**when `severity_histogram != null`**. When the histogram is `null` (Tier B
stubs), WHS is also `null`. The headline "caught N" count in `/ledger`
excludes entries where WHS is `null`.

This rule is mechanical — emitters do not decide WHS; they emit the histogram
and the boolean follows from arithmetic. Tampering at emit is structurally
prevented.

### Marker → ledger field-name mapping

Quality-gate marker fields are `PascalCase`; ledger fields are `snake_case`.
The mapping at emit time:

| Marker field    | Ledger field      |
|-----------------|-------------------|
| `ArtifactHash`  | `artifact_hash`   |
| `ChunkHash`     | `chunk_hash`      |
| `Rounds`        | `rounds`          |
| `RunID`         | `run_id`          |
| `Verdict`       | `verdict`         |
| `Timestamp`     | `timestamp`       |

Severity-Histogram / Gated-Files / Highest-Finding ride alongside the marker
as additive fields (post-`MarkerVersion: 2`) and map 1:1 to the
corresponding `snake_case` ledger keys.

### `predicted_falsifier` deferred-sentinel protocol (Phase 1 → Phase 7 bridge)

The field is in the schema from Phase 1 but its real emit-rules ship in Phase 7.

- **Tier A emits write `predicted_falsifier: "<DEFERRED:pre-phase-7>"`** ONLY
  when both conditions hold: `verdict ∈ {PASS, FAIL}` AND `artifact_type ==
  "code"`. All other Tier A cases (escalation verdicts STAGNATION /
  ESCALATED / ARCHITECTURAL / SUSTAINED_REGRESSION; non-code artifact types
  design / plan / hypothesis / mockup / translation / other) write
  `predicted_falsifier: null`.
- **Tier B emits always write `null`.**
- **Backfilled entries always write `null`** (cannot be retroactively
  pre-registered).

Phase 7 parsers MUST early-return on the sentinel before any regex matching
(`if predicted_falsifier == "<DEFERRED:pre-phase-7>": return excluded`).

## L-2 uniqueness clarification

Uniqueness is on `(run_id, skill)` regardless of `run_id` format.

- Forward-captured entries: `run_id` is a **UUIDv7** (see `scripts/uuid7.py`,
  inlined below).
- Backfilled entries: `run_id` is the deterministic shape
  `backfill-<pr_number>-quality-gate` (or `<skill>` for non-QG backfills).

Dedup remains `(run_id, skill)` across both shapes. Idempotent re-runs of the
backfill script produce the same backfill IDs and skip on re-encounter.

## L-8 truncation rules + sidecar protocol

Hard caps enforced inside `scripts/ledger_append.py`:

- `gated_files`: maximum 500 entries in the ledger line. Overflow goes to a
  sidecar at `.crucible/ledger/overflow/<run_id>.<skill>.txt` (one path per
  line, complete list including the overflow). The ledger entry sets
  `gated_files_truncated` to the count of dropped paths.
- `highest_finding`: maximum 256 characters in the ledger line. Truncated
  to the first 256 chars if longer; the verdict marker (caller side) retains
  the untruncated quote.
- **16 KiB total line cap (post-truncation):** If, after the above truncations,
  the encoded JSONL line is still > 16384 bytes, the append is **rejected**
  (function returns `False`, warning logged to stderr including `run_id` and
  `skill`; the verdict marker still has the full data; `runs.jsonl` does NOT
  receive the oversize line).

**Reconciler fallback** (Phase 4 contract — preview): with sidecar present,
the reconciler reads the sidecar and uses the full file list. With sidecar
removed (deleted, gitignored away, FS error), the reconciler logs a warning
AND marks the entry **unfalsifiable** — it does NOT silently substitute the
truncated list.

## Mkdir-lock protocol (steps 1–6)

The naive `flock` approach is silently broken on 9p NTFS (WSL on `/mnt/...`),
unreliable on network mounts, and FS-pathway-dependent on macOS. We use a
portable scheme that does not rely on advisory locking. `mkdir` is atomic
across all supported filesystems and IS the mutex.

1. **Acquire:** `mkdir .crucible/ledger/.lock-runs-jsonl`
   - On success: continue to step 2.
   - On EEXIST: spin with 50 ms backoff up to 5 s.
   - If stale recovery applies (step 5), invoke before spinning further.

2. **Write identity:** open `.crucible/ledger/.lock-runs-jsonl/holder`,
   write `<run_id>:<skill>:<pid>:<acquired_ts_iso>`, close.

3. **Append:** open `runs.jsonl` with `O_APPEND | O_CREAT`; write one JSONL
   line (including trailing `\n`) **as a single `write()` syscall**; fsync;
   close. A `write()` of ≤16 KiB is atomic on ext4, APFS, and 9p — this is
   what the L-8 16 KiB cap guarantees. Single-syscall semantics close the
   crash-mid-append + next-writer concatenation window.

4. **Release:** `unlink` holder file, then `rmdir` lockdir. (Order matters —
   unlinking holder first prevents another writer mid-recovery from observing
   a present lockdir with no holder.)

5. **Stale recovery** (triggered when initial spin elapses past 5 s AND lockdir
   mtime is older than 60 s):
   - Read holder file inside the existing lockdir.
   - **Branch A — holder file EXISTS and parses:** extract pid.
     - `os.kill(pid, 0)` returns `0` (alive): continue spinning under the
       300 s extended cap. Do NOT rmdir.
     - `ProcessLookupError` (ESRCH, dead): unlink holder, rmdir lockdir,
       retry from step 1.
     - `PermissionError` (EPERM, alive under another uid): treat as alive,
       continue spinning. Do NOT rmdir.
   - **Branch B — holder file MISSING or malformed:** lockdir has been
     present > 60 s with no valid holder; rmdir and retry from step 1.

6. **Crash-window analysis:**
   - Crash after step 1, before step 2 → Branch B fires after 60 s; recovery rmdirs.
   - Crash after step 2, before step 3 → Branch A fires; ESRCH; recovery rmdirs.
   - Crash during step 3 → fsync may or may not complete; trailing partial
     line possible. JSONL readers skip partial trailing lines per the L-9
     reduction protocol (see `shared/ledger-reduce.md`).
   - Crash after step 3, before step 4 → Branch A fires after 60 s; recovery
     rmdirs; no data loss (append already committed).

**Spin-cap state transition:** the 5 s initial cap and 300 s recovery cap are
**sequential, not concurrent** — total max wait is 305 s per attempt.

The lock IS the correctness mechanism. `O_APPEND` is convenience (no offset
tracking); not relied upon for cross-writer atomicity.

## Invariants index (L-1..L-9)

| Inv. | Statement | Enforced where |
|------|-----------|----------------|
| L-1 | Append-only; never rewrite a line | `O_APPEND` in step 3 |
| L-2 | Unique `(run_id, skill)` | Caller dedup before append |
| L-3 | Mechanical WHS from histogram | Schema rule (above) |
| L-4 | Falsification hash-keyed (`ledger_entry_hash`) | `falsification.jsonl` (Phase 4) |
| L-6 | Emit-side kill-switch | Early return in `append()` |
| L-7 | Migration protocol (forward-compat / never-decrease) | `docs/ledger/MIGRATION-PROTOCOL.md` |
| L-8 | 16 KiB line cap + truncation + sidecar | `_truncate_payload` + line-bytes check |
| L-9 | Latest-entry-wins reduction (file-position) | `shared/ledger-reduce.md` |

L-5 (backfill exclusion from headline) and L-10 (Brier polarity) are encoded
in design/contract; no runtime call-sites in Phase 1.

Cross-link: see `docs/plans/2026-05-18-epistemics-stack-v1-design.md`
§"Invariants" for the canonical definitions.

## Reference Python — `scripts/uuid7.py`

```python
#!/usr/bin/env python3
"""UUIDv7 generator. 48-bit unix-ms timestamp + version 7 + random bits + variant 10."""
import secrets
import time


def uuid7() -> str:
    """Return a canonical UUIDv7 string: xxxxxxxx-xxxx-7xxx-yxxx-xxxxxxxxxxxx."""
    ms = time.time_ns() // 1_000_000
    ts = ms.to_bytes(6, "big")              # 48-bit timestamp
    rand = secrets.token_bytes(10)
    b = bytearray(ts + rand)
    b[6] = (b[6] & 0x0F) | 0x70             # version 7
    b[8] = (b[8] & 0x3F) | 0x80             # variant 10
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
```

## Reference Python — `scripts/ledger_append.py`

> **Canonical source:** `scripts/ledger_append.py`. The fenced block below is a reference snapshot; for the authoritative current implementation (including `caller_dedup`, S-3 reordered sidecar I/O, and S-2 short-write line-terminator behavior surfaced in 2026-05-19 review), **import from `scripts.ledger_append`**. A Phase-5 CI assertion will diff the two; for now, treat any divergence as a doc-side issue, not a code-side regression.

```python
#!/usr/bin/env python3
"""Canonical ledger append protocol — mkdir-lock + holder file + single-write() syscall."""
import datetime as _dt
import errno
import json
import os
import sys
import time
from typing import Optional

LOCK_DIRNAME = ".lock-runs-jsonl"
HOLDER_FILENAME = "holder"
SPIN_INTERVAL_S = 0.05
INITIAL_SPIN_CAP_S = 5.0
RECOVERY_SPIN_CAP_S = 300.0
STALE_THRESHOLD_S = 60.0


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kill_switch_active() -> bool:
    return os.environ.get("CRUCIBLE_CALIBRATION_DISABLED") == "1"


def _warn(msg: str) -> None:
    print(f"[ledger_append WARN] {msg}", file=sys.stderr)


def _truncate_payload(entry, max_gated_files, max_highest_finding_chars,
                       overflow_dir, run_id, skill):
    out = dict(entry)
    gated = out.get("gated_files")
    if isinstance(gated, list) and len(gated) > max_gated_files:
        full = list(gated)
        out["gated_files"] = full[:max_gated_files]
        out["gated_files_truncated"] = len(full) - max_gated_files
        if overflow_dir is not None:
            try:
                os.makedirs(overflow_dir, exist_ok=True)
                sidecar = os.path.join(overflow_dir, f"{run_id}.{skill}.txt")
                with open(sidecar, "w", encoding="utf-8") as f:
                    for p in full:
                        f.write(p + "\n")
            except OSError as e:
                _warn(f"sidecar write failed: {e}")
    else:
        out.setdefault("gated_files_truncated", 0)
    hf = out.get("highest_finding")
    if isinstance(hf, str) and len(hf) > max_highest_finding_chars:
        out["highest_finding"] = hf[:max_highest_finding_chars]
    return out


def _try_stale_recovery(lockdir):
    holder = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        with open(holder, "r", encoding="utf-8") as f:
            line = f.read().strip()
        parts = line.split(":")
        if len(parts) < 4:
            raise ValueError("malformed holder")
        pid = int(parts[2])
    except (OSError, ValueError):
        try:
            try: os.unlink(holder)
            except OSError: pass
            os.rmdir(lockdir)
            return True
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return False  # alive
    except ProcessLookupError:
        try: os.unlink(holder)
        except OSError: pass
        try:
            os.rmdir(lockdir)
            return True
        except OSError:
            return False
    except PermissionError:
        return False


def _acquire_lock(lockdir):
    spin_started = time.monotonic()
    while True:
        try:
            os.mkdir(lockdir)
            return True
        except FileExistsError:
            pass
        except OSError as e:
            if e.errno != errno.EEXIST:
                return False
        elapsed = time.monotonic() - spin_started
        try:
            st = os.stat(lockdir)
            lockdir_age = time.time() - st.st_mtime
        except FileNotFoundError:
            continue
        if lockdir_age > STALE_THRESHOLD_S:
            if _try_stale_recovery(lockdir):
                continue
            if elapsed > RECOVERY_SPIN_CAP_S:
                return False
        else:
            if elapsed > (INITIAL_SPIN_CAP_S + RECOVERY_SPIN_CAP_S):
                return False
        time.sleep(SPIN_INTERVAL_S)


def append(ledger_path, entry, *, max_line_bytes=16384, max_gated_files=500,
           max_highest_finding_chars=256, overflow_dir=None):
    if _kill_switch_active():
        return False
    run_id = entry.get("run_id", "unknown")
    skill = entry.get("skill", "unknown")
    if overflow_dir is None:
        overflow_dir = os.path.join(os.path.dirname(ledger_path) or ".", "overflow")
    payload = _truncate_payload(entry, max_gated_files, max_highest_finding_chars,
                                 overflow_dir, run_id, skill)
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    line_bytes = line.encode("utf-8")
    if len(line_bytes) > max_line_bytes:
        _warn(f"oversize line rejected (run_id={run_id} skill={skill} bytes={len(line_bytes)})")
        return False
    ledger_dir = os.path.dirname(ledger_path) or "."
    os.makedirs(ledger_dir, exist_ok=True)
    lockdir = os.path.join(ledger_dir, LOCK_DIRNAME)
    if not _acquire_lock(lockdir):
        return False
    holder_path = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        with open(holder_path, "w", encoding="utf-8") as hf:
            hf.write(f"{run_id}:{skill}:{os.getpid()}:{_now_iso()}")
        fd = os.open(ledger_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            written = os.write(fd, line_bytes)
            if written != len(line_bytes):
                return False
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        try: os.unlink(holder_path)
        except OSError: pass
        try: os.rmdir(lockdir)
        except OSError: pass
```

The canonical importable module is at `scripts/ledger_append.py` (also
`scripts.ledger_append` for Python import). T-1 subprocesses, the Phase 3
backfill script, and Tier A emit call-sites import and invoke `append()`
directly. The block above is the prompt-side reference copy.
