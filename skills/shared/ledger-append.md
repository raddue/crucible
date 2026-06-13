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

Emit one JSONL line to the **central ledger** at terminal verdict emission
(after the verdict marker has been written; the two writes are independent —
marker durability and ledger durability are not interlocked).

Read in-process verdict state directly. Do **not** re-parse the on-disk marker
file: parse-roundtrip drift is a real failure mode and the dedup check makes
double-emit harmless.

## Where it writes — the central store (#270)

The live ledger is **machine-local and shared across every repo**:
`~/.claude/crucible/ledger/runs.jsonl` (override with `CRUCIBLE_LEDGER_DIR`).
It is deliberately **not** inside any git repo — entries carry private file
paths and verbatim finding quotes, and crucible is public. Gating skills run
in arbitrary repos (any project on the machine, …); they all aggregate here so
`/ledger` can render one honest cross-repo headline with a per-repo breakdown.
`scripts.ledger_append.default_ledger_path()` is the single source of truth for
this path; the renderer imports it too.

## How to emit — `emit` CLI by absolute path (cwd-independent)

A gating skill runs with an arbitrary cwd, so a bare `import
scripts.ledger_append` does **not** resolve. Locate the script by absolute path
from the plugin root and invoke its `emit` subcommand:

```
# 1. Resolve the script from THIS skill's base directory. The plugin layout is
#    invariant: <plugin_root>/skills/<name>/ and <plugin_root>/scripts/.
#    realpath resolves the ~/.claude/skills/<name> symlink BEFORE applying ../..,
#    so this works for both symlinked and native plugin installs.
plugin_root="$(realpath "<this-skill-base-dir>/../..")"
script="$plugin_root/scripts/ledger_append.py"

# 2. Fallback if the computed path is missing: try the native plugin install,
#    then any symlinked skill dir. (Pick the first that exists.)
#      ~/.claude/plugins/*/scripts/ledger_append.py
#      realpath of ~/.claude/skills/*/../../scripts/ledger_append.py
# 3. Still unresolved → emit a one-line stderr warning and SKIP. The ledger is
#    advisory; a missing emit must NEVER block or fail the gate.

# 4. Emit. '-' means the central default path; the CLI dedups, auto-fills
#    `repo` + `schema_version`, and appends. Pure stdlib + absolute path ⇒ no
#    PYTHONPATH and no cwd dependency.
python3 "$script" emit - '<json-entry>'
```

The `emit` subcommand is the canonical write path. It:

- resolves `-` to `default_ledger_path()` (the central store);
- honors `CRUCIBLE_CALIBRATION_DISABLED=1` as a **graceful skip** (no-op, exit 0);
- **dedups by `(run_id, skill)`** before appending (L-2) and skips on a hit
  (exit 0) — `append()` does not scan the ledger, so the CLI owns this;
- **fills `repo`** (git-toplevel basename, cwd-basename fallback) when the
  entry omits it, and **forces `schema_version`** to the current value (`emit`
  is always a current-schema forward capture);
- returns 0 on success / graceful skip, 1 only on a real append rejection.

Idempotent across retries because dedup runs first. (The `append()` library
function and the legacy positional `<ledger_path> <json>` CLI form remain for
in-process callers and back-compat; new emit sites use `emit`.)

## Kill-switch (L-6) — emit-side enforcement

`CRUCIBLE_CALIBRATION_DISABLED=1` ⇒ the emit path is a **no-op return BEFORE
any lock acquisition or filesystem state change**. No mkdir, no holder write,
no append. This is the first check in the protocol.

The kill-switch is a **fixture-isolation guard**, not a bootstrap-wide
silencer. Real Crucible runs against real artifacts during Phases 2–7 SHOULD
emit normally — that data is the entire point. Only set the env var when
running against test fixtures, eval corpora, or CI smoke tests that would
otherwise pollute the ledger. See `docs/CONTRIBUTING-CALIBRATION.md`.

## Schema v2 (23 fields)

v2 adds one nullable provenance field, `repo`, to v1 (#270). Readers stay
backward-compatible: v1 rows (no `repo`, `schema_version: 1`) read fine and
bucket under `repo: "unknown"` in the renderer. The `emit` CLI fills `repo`
when absent and forces `schema_version: 2` (it is always a current-schema
forward capture); the legacy positional `append` form leaves `schema_version`
caller-set, so direct callers like the v1 backfill stay v1.

```json
{
  "schema_version": 2,
  "run_id": "<UUIDv7 — sortable, millisecond-precision, unique>",
  "skill": "quality-gate | red-team | siege | inquisitor | audit",
  "repo": "<basename of git toplevel; cwd basename fallback; 'unknown' on v1 rows>",
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

### `predicted_falsifier` protocol (predicted-falsifier prediction market, Phase 7)

A pre-registered, machine-checkable predicate co-emitted with each Tier A
verdict (design §3a). It converts the ledger from a scorecard into a prediction
market: every PASS/FAIL is a dated, falsifiable hypothesis. The reconciler's
second pass parses it and checks whether it fired; `/ledger` surfaces per-skill
hit-rate and unparseable-rate.

**When to emit (Tier A only — `quality-gate`, `siege`):**

- **MANDATORY non-null** whenever `verdict ∈ {PASS, FAIL}` AND `artifact_type ==
  "code"`. In one sentence, describe the future evidence that would prove this
  verdict wrong. Prefer the **canonical grammar** so the reconciler can
  auto-check it:

  ```
  <predicate> ::= <verb> "touching" <file-list> "within" <N> "d"
                | <verb> "of" "artifact_hash=" <hex> ["without" "touching" <file-list>] "within" <N> "d"
                | <verb> "referencing" <token> "within" <N> "d"
  <verb>      ::= "fix" | "hotfix" | "revert" | "merge" | "CVE" | "postmortem"
  <file-list> ::= <path-or-glob> ("," <path-or-glob>)*
  <N>         ::= 1-365 (integer days)
  ```

  Examples: `fix touching src/auth/token.ts within 30d` ·
  `hotfix touching src/api/*,src/db/migrate.ts within 14d` ·
  `CVE referencing token-refresh within 90d`.

  Free-form prose is permitted but counts as **unparseable** for auto-checking
  (surfaced in `/ledger`'s `unparseable_predicate_rate`, never rejected at emit).
  Max 256 chars. Auto-checking covers the `touching` form at v1.
- **`null`** for all other Tier A cases: escalation verdicts (STAGNATION /
  ESCALATED / ARCHITECTURAL / SUSTAINED_REGRESSION — not predictions about
  artifact correctness) and all non-code artifact types (design / plan /
  hypothesis / mockup / translation / other — non-code calibration is deferred
  to v1.1).
- **Tier B emits always write `null`** (consistent with their stub posture).
- **Backfilled entries always write `null`** (cannot be retroactively
  pre-registered).

**Bootstrap sentinel (historical).** Between the Phase 1 and Phase 7 merges,
Tier A wrote the literal `"<DEFERRED:pre-phase-7>"` in place of a real predicate.
The reconciler and `/ledger` early-return on it (`if predicted_falsifier ==
"<DEFERRED:pre-phase-7>": exclude from both rate denominators`); it is neither
parseable nor unparseable. New emits MUST NOT write the sentinel — write a real
predicate or `null` per the rules above.

## Manual-attribution `signal_type` (reconcile-side; NOT a runs field)

`signal_type` is an **optional field on `manual-attribution.jsonl` entries** (and
the `falsification.jsonl` entry the reconciler derives from them) — it is **not** a
`runs.jsonl` field, so the `emit` CLI never writes it. Enum:

- `manual_override` (default when omitted) — a plain human override of the
  algorithm's attribution.
- `bad_implementation` — "a verdict accepted as PASS led to a bad implementation"
  (a design-level wrong call, downstream rework, or an abandoned approach that no
  path-touching fix captures). This is the seam that lets a **non-code** verdict be
  Brier-scored: `compute_brier` admits a non-code verdict into the sample only when
  it carries a `bad_implementation` falsification. PASS-side only. Full semantics +
  JSONL shape live in `skills/calibration-reconcile/SKILL.md`.

The reconciler threads `signal_type` onto both the top level of the derived
falsification entry and into its `falsified_by`.

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
| L-6 | Emit-side kill-switch | Early return in `append()` + `_cli_emit` graceful skip |
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
"""Canonical ledger append protocol — mkdir-lock + holder file + single-write() syscall.

Protocol-as-spec lives in skills/shared/ledger-append.md. This module is the
importable, executable single source of truth used by T-1 subprocesses, by Tier A
emit call-sites, and by the Phase 3 backfill script.

Invariants enforced here:
- L-1 append-only (O_APPEND, never rewrite a line)
- L-6 kill-switch (CRUCIBLE_CALIBRATION_DISABLED=1 → no-op return BEFORE any lock)
- L-8 16 KiB line cap + gated_files truncation at 500 + highest_finding cap at 256 chars
- Crash-window recovery (>60s stale lockdir with branch A live/dead, branch B malformed)

Pure stdlib. No third-party deps.
"""
import datetime as _dt
import errno
import json
import os
import sys
import time
from typing import Optional

LOCK_DIRNAME = ".lock-runs-jsonl"
HOLDER_FILENAME = "holder"
SPIN_INTERVAL_S = 0.05          # 50 ms backoff
INITIAL_SPIN_CAP_S = 5.0        # initial spin cap before stale-recovery
RECOVERY_SPIN_CAP_S = 300.0     # cap once we know holder is alive (branch A EPERM/0)
STALE_THRESHOLD_S = 60.0        # lockdir age past which we enter stale-recovery


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kill_switch_active() -> bool:
    return os.environ.get("CRUCIBLE_CALIBRATION_DISABLED") == "1"


# --------------------------------------------------------------------------- #
# Central-store path + provenance resolution (#270).                          #
#                                                                             #
# The live ledger is machine-local and aggregates EVERY repo's gating runs    #
# into one place — never inside any git repo, because entries carry private   #
# file paths and verbatim finding quotes and crucible is a public repo.       #
# These helpers are the single source of truth for the path; render_ledger    #
# imports them. default_repo() shells to git and is therefore CLI-only —      #
# append() stays free of git/subprocess side effects (INV-2).                 #
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = 2


def default_ledger_dir() -> str:
    """Directory holding the live ledger. A non-empty CRUCIBLE_LEDGER_DIR wins
    (tests, fixtures); an empty/unset value falls back to ~/.claude/crucible/
    ledger — a ~-rooted path that is never inside a git working tree (INV-1)."""
    env = os.environ.get("CRUCIBLE_LEDGER_DIR")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".claude", "crucible", "ledger")


def default_ledger_path() -> str:
    return os.path.join(default_ledger_dir(), "runs.jsonl")


def default_repo(start_dir: Optional[str] = None) -> str:
    """Provenance label for the repo a gating run happened in: the basename of
    the git toplevel, falling back to the basename of the start dir / cwd when
    not in a git repo (or git is absent). Never raises (INV-7). CLI-only — not
    reachable from append() (INV-2)."""
    base = start_dir or os.getcwd()
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "-C", base, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            return os.path.basename(top.rstrip("/")) or top
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        pass
    return os.path.basename(os.path.abspath(base)) or "unknown"


def _warn(msg: str) -> None:
    print(f"[ledger_append WARN] {msg}", file=sys.stderr)


def _truncate_payload(entry: dict, max_gated_files: int,
                       max_highest_finding_chars: int) -> tuple[dict, Optional[list]]:
    """Apply L-8 truncation in-place on a shallow copy.

    Returns (truncated_entry, overflow_list_or_None). Sidecar I/O is the caller's
    responsibility — deferred to AFTER the line-bytes size check passes to avoid
    orphan-sidecar leaks on oversize rejection (review finding S-3).
    """
    out = dict(entry)
    overflow: Optional[list] = None
    gated = out.get("gated_files")
    if isinstance(gated, list) and len(gated) > max_gated_files:
        overflow = list(gated)
        out["gated_files"] = overflow[:max_gated_files]
        out["gated_files_truncated"] = len(overflow) - max_gated_files
    else:
        out.setdefault("gated_files_truncated", 0)

    hf = out.get("highest_finding")
    if isinstance(hf, str) and len(hf) > max_highest_finding_chars:
        out["highest_finding"] = hf[:max_highest_finding_chars]
    return out, overflow


def caller_dedup(ledger_path: str, run_id: str, skill: str) -> bool:
    """L-2 caller-side dedup. Returns True if (run_id, skill) already in ledger.

    Callers MUST invoke this BEFORE append() to honor invariant L-2. The append
    helper does not scan for prior entries. Full-scan; bounded by current ledger
    size (acceptable while ledger is sub-MB; future rotation lands in v1.1).
    """
    if not os.path.exists(ledger_path):
        return False
    try:
        with open(ledger_path, "rb") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if obj.get("run_id") == run_id and obj.get("skill") == skill:
                    return True
    except OSError:
        return False
    return False


def _try_stale_recovery(lockdir: str) -> bool:
    """Returns True if recovery freed the lockdir (caller should retry mkdir).

    Branch A: holder file present and parses → check liveness via os.kill(pid, 0).
      - returns 0 (alive): keep waiting, do NOT rmdir.
      - ProcessLookupError (ESRCH): dead → unlink holder + rmdir + signal retry.
      - PermissionError (EPERM): alive under another uid → keep waiting.
    Branch B: holder missing or malformed → definitively crashed mid-acquire; rmdir.
    """
    holder = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        with open(holder, "r", encoding="utf-8") as f:
            line = f.read().strip()
        # holder format: <run_id>:<skill>:<pid>:<iso_ts>
        parts = line.split(":")
        if len(parts) < 4:
            raise ValueError("malformed holder")
        pid = int(parts[2])
    except (OSError, ValueError):
        # Branch B: missing or malformed holder
        try:
            try:
                os.unlink(holder)
            except OSError:
                pass
            os.rmdir(lockdir)
            return True
        except OSError:
            return False

    # Branch A: liveness probe
    try:
        os.kill(pid, 0)
        # Alive — do NOT rmdir
        return False
    except ProcessLookupError:
        # Dead (ESRCH) — recover
        try:
            os.unlink(holder)
        except OSError:
            pass
        try:
            os.rmdir(lockdir)
            return True
        except OSError:
            return False
    except PermissionError:
        # EPERM — alive under another uid; keep waiting
        return False


def _acquire_lock(lockdir: str) -> bool:
    """Block until lockdir is acquired or recovery escalation gives up.

    Returns True on acquisition. Returns False if all recovery paths exhausted.
    Total max wait: ~5s initial spin + ~300s recovery spin = 305s per attempt.
    """
    spin_started = time.monotonic()
    while True:
        try:
            os.mkdir(lockdir)
            return True
        except FileExistsError:
            pass
        except OSError as e:
            if e.errno != errno.EEXIST:
                _warn(f"mkdir lockdir errored: {e}")
                return False

        elapsed = time.monotonic() - spin_started
        # Check lockdir age for stale-recovery eligibility
        try:
            st = os.stat(lockdir)
            lockdir_age = time.time() - st.st_mtime
        except FileNotFoundError:
            # vanished between EEXIST and stat — retry immediately
            continue

        if lockdir_age > STALE_THRESHOLD_S:
            recovered = _try_stale_recovery(lockdir)
            if recovered:
                continue  # retry mkdir
            # alive-holder branch — keep spinning under the extended cap
            if elapsed > RECOVERY_SPIN_CAP_S:
                _warn(f"lock acquisition exhausted recovery cap at {lockdir}")
                return False
        else:
            if elapsed > INITIAL_SPIN_CAP_S:
                # Loop continues; we'll re-evaluate stale once lockdir_age crosses threshold
                pass
            if elapsed > (INITIAL_SPIN_CAP_S + RECOVERY_SPIN_CAP_S):
                _warn(f"lock acquisition timed out at {lockdir}")
                return False
        time.sleep(SPIN_INTERVAL_S)


def append(
    ledger_path: str,
    entry: dict,
    *,
    max_line_bytes: int = 16384,
    max_gated_files: int = 500,
    max_highest_finding_chars: int = 256,
    overflow_dir: Optional[str] = None,
) -> bool:
    """Append one JSONL line to ledger_path under the canonical lock protocol.

    Returns True on successful append; False on kill-switch no-op or rejection.
    """
    # L-6 kill-switch: BEFORE any lock acquisition or filesystem state change.
    if _kill_switch_active():
        return False

    run_id = entry.get("run_id", "unknown")
    skill = entry.get("skill", "unknown")

    if overflow_dir is None:
        overflow_dir = os.path.join(os.path.dirname(ledger_path) or ".", "overflow")

    # L-8 truncation. Sidecar I/O is deferred until after the size check (S-3 fix).
    payload, overflow_files = _truncate_payload(
        entry, max_gated_files, max_highest_finding_chars,
    )

    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    line_bytes = line.encode("utf-8")
    if len(line_bytes) > max_line_bytes:
        _warn(
            f"oversize line rejected after truncation (run_id={run_id} "
            f"skill={skill} bytes={len(line_bytes)} cap={max_line_bytes})"
        )
        return False

    ledger_dir = os.path.dirname(ledger_path) or "."
    try:
        os.makedirs(ledger_dir, exist_ok=True)
    except OSError as e:
        _warn(f"could not create ledger dir {ledger_dir}: {e}")
        return False

    lockdir = os.path.join(ledger_dir, LOCK_DIRNAME)
    if not _acquire_lock(lockdir):
        _warn(f"failed to acquire lock for {ledger_path} (run_id={run_id} skill={skill})")
        return False

    holder_path = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        # Step 2: write identity inside the lockdir
        with open(holder_path, "w", encoding="utf-8") as hf:
            hf.write(f"{run_id}:{skill}:{os.getpid()}:{_now_iso()}")

        # L-8 sidecar: write only AFTER the size check passed, inside the lock.
        # Avoids orphan-sidecar leaks when the ledger append itself is rejected.
        if overflow_files is not None:
            try:
                os.makedirs(overflow_dir, exist_ok=True)
                sidecar = os.path.join(overflow_dir, f"{run_id}.{skill}.txt")
                with open(sidecar, "w", encoding="utf-8") as f:
                    for p in overflow_files:
                        f.write(p + "\n")
            except OSError as e:
                _warn(f"sidecar write failed for run_id={run_id} skill={skill}: {e}")

        # Step 3: single-write() syscall append. ≤16 KiB ⇒ atomic on ext4/APFS/9p.
        fd = os.open(ledger_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            written = os.write(fd, line_bytes)
            if written != len(line_bytes):
                # L-1 hazard: a partial line is on disk. Terminate it with a
                # newline so the reducer's per-line JSON parse skips this
                # fragment cleanly rather than corrupting downstream lines.
                # We still report failure to the caller.
                try:
                    os.write(fd, b"\n")
                    os.fsync(fd)
                except OSError:
                    pass
                _warn(
                    f"short write detected; line terminator forced "
                    f"(wrote={written} expected={len(line_bytes)} "
                    f"run_id={run_id} skill={skill})"
                )
                return False
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        # Step 4: release — unlink holder first, then rmdir lockdir.
        try:
            os.unlink(holder_path)
        except OSError:
            pass
        try:
            os.rmdir(lockdir)
        except OSError:
            pass


def _cli_emit(ledger_arg: str, entry: dict) -> int:
    """`emit` subcommand: the canonical forward-capture write path.

    Resolves '-' to the central default, honors the kill-switch as a graceful
    skip, dedups by (run_id, skill), fills `repo` when absent and forces
    `schema_version` to the current value, then appends. Pure stdlib + invoked
    by absolute path ⇒ no PYTHONPATH and no cwd dependency (INV-5/INV-6).
    Graceful no-ops (kill-switch, duplicate) return 0; only a real append
    rejection returns 1 (INV-9)."""
    ledger_path = default_ledger_path() if ledger_arg == "-" else ledger_arg

    # L-6 graceful skip: kill-switch is a no-op, not a failure.
    if _kill_switch_active():
        print("[ledger_append] calibration disabled; emit skipped", file=sys.stderr)
        return 0

    # `emit` is always a current-schema forward capture: stamp schema_version
    # unconditionally (an emitter sending the stale `1` must not produce a
    # hybrid v1+repo row). Fill `repo` when absent OR explicitly null/empty —
    # setdefault would miss the null case, silently voiding provenance.
    if not entry.get("repo"):
        entry["repo"] = default_repo()
    entry["schema_version"] = SCHEMA_VERSION

    run_id = entry.get("run_id", "unknown")
    skill = entry.get("skill", "unknown")
    if caller_dedup(ledger_path, run_id, skill):
        print(f"[ledger_append] duplicate (run_id={run_id} skill={skill}); "
              f"emit skipped", file=sys.stderr)
        return 0

    return 0 if append(ledger_path, entry) else 1


if __name__ == "__main__":
    # Two CLI forms:
    #   emit <ledger_path|-> <json>   — dedup + auto-fill + append (canonical)
    #   <ledger_path> <json>          — legacy append-only (back-compat)
    argv = sys.argv
    if len(argv) >= 4 and argv[1] == "emit":
        sys.exit(_cli_emit(argv[2], json.loads(argv[3])))
    if len(argv) >= 3 and argv[1] != "emit":
        ok = append(argv[1], json.loads(argv[2]))
        sys.exit(0 if ok else 1)
    print("usage: ledger_append.py emit <ledger_path|-> <json-entry>\n"
          "       ledger_append.py <ledger_path> <json-entry>  (legacy, append-only)",
          file=sys.stderr)
    sys.exit(2)
```

The canonical importable module is at `scripts/ledger_append.py` (also
`scripts.ledger_append` for Python import). T-1 subprocesses, the Phase 3
backfill script, and Tier A emit call-sites import and invoke `append()`
directly. The block above is the prompt-side reference copy.
