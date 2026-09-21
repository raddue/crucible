---
version: 1
---

# Ledger Append Protocol (canonical)

> Canonical write-protocol prompt for the Crucible calibration ledger
> (`~/.claude/crucible/ledger/runs.jsonl`). Referenced by every gating skill that emits a
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
`raddue/crucible-eval`'s `/ledger` (moved there — #460) can render one honest
cross-repo headline with a per-repo breakdown.
`scripts.ledger_append.default_ledger_path()` is the single source of truth for
this path; the weekly renderer (now in `raddue/crucible-eval`, #460) imports
it too.

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
caller-set, so direct callers like the v1 backfill (moved to
`raddue/crucible-eval`, #460) stay v1.

```json
{
  "schema_version": 2,
  "run_id": "<UUIDv7 — sortable, millisecond-precision, unique>",
  "skill": "<emitting skill name; open set — any skill carrying a CANONICAL shared/ledger-append.md emit block (e.g. quality-gate, siege, temper, red-team, audit, inquisitor, delve, review-feedback, test-coverage, verify)>",
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

Tier B emitters (e.g. `red-team`, `audit`, `inquisitor`, `delve`) emit the schema-required
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
stubs), WHS is also `null`. The headline "caught N" count in
`raddue/crucible-eval`'s `/ledger` (moved there — #460) excludes entries
where WHS is `null`.

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
market: every PASS/FAIL is a dated, falsifiable hypothesis. `raddue/crucible-eval`'s
reconciler runs a second pass that parses it and checks whether it fired;
its `/ledger` (moved there — #460) surfaces per-skill hit-rate and
unparseable-rate.

**When to emit (Tier A code gates only — e.g. `quality-gate`, `siege`, `temper`):**

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
  (surfaced in `raddue/crucible-eval`'s `/ledger` (moved there — #460)
  `unparseable_predicate_rate`, never rejected at emit).
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
`raddue/crucible-eval`'s reconciler and `/ledger` (moved there — #460)
early-return on it (`if predicted_falsifier ==
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
  JSONL shape live in `raddue/crucible-eval`'s `skills/calibration-reconcile/SKILL.md`
  (moved there — #460).

The reconciler threads `signal_type` onto both the top level of the derived
falsification entry and into its `falsified_by`.

## L-2 uniqueness clarification

Uniqueness is on `(run_id, skill)` regardless of `run_id` format.

- Forward-captured entries: `run_id` is a **UUIDv7** (see `scripts/uuid7.py`,
  inlined below).
- Backfilled entries: `run_id` is the deterministic shape
  `backfill-<pr_number>-quality-gate` (or `<skill>` for non-QG backfills).

Dedup remains `(run_id, skill)` across both shapes. Idempotent re-runs of the
backfill script (moved to `raddue/crucible-eval`, #460) produce the same
backfill IDs and skip on re-encounter.

## L-8 truncation rules + sidecar protocol

Hard caps enforced inside `scripts/ledger_append.py`:

- `gated_files`: maximum 500 entries in the ledger line. Overflow goes to a
  sidecar at `~/.claude/crucible/ledger/overflow/<run_id>.<skill>.txt` (one path per
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

1. **Acquire:** `mkdir ~/.claude/crucible/ledger/.lock-runs-jsonl`
   - On success: continue to step 2.
   - On EEXIST: spin with 50 ms backoff up to 5 s.
   - If stale recovery applies (step 5), invoke before spinning further.

2. **Write identity:** open `~/.claude/crucible/ledger/.lock-runs-jsonl/holder`,
   write one JSON object `{"run_id": ..., "skill": ..., "pid": ..., "acquired_ts": ...}`,
   close. (JSON, not a `:`-delimited line — SIEGE-FA-1/CA-5: `run_id`/`skill`
   are caller-supplied and unconstrained in character set, e.g. ISO-timestamp-
   shaped run ids this repo's own skills use; a delimited line lets a `:` in
   either field shift which token `pid` is parsed from, either wedging the
   lock permanently against a live holder or destroying a live holder's lock.
   A JSON encoding cannot be shifted this way regardless of field content.)

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
     reduction protocol (see "L-9 latest-entry-wins reduction (inlined, #460)"
     below).
   - Crash after step 3, before step 4 → Branch A fires after 60 s; recovery
     rmdirs; no data loss (append already committed).

**Spin-cap state transition:** the 5 s initial cap and 300 s recovery cap are
**sequential, not concurrent** — total max wait is 305 s per attempt.

The lock IS the correctness mechanism. `O_APPEND` is convenience (no offset
tracking); not relied upon for cross-writer atomicity.

## L-9 latest-entry-wins reduction (inlined, #460)

Reader-side reduction over `falsification.jsonl` (or any ledger-shaped JSONL).
**File-position ordering is authoritative — NOT the `timestamp` field.** A
late-arriving entry (later byte position) overwrites an earlier entry with the
same `ledger_entry_hash`; out-of-order `timestamp`s (clock skew, manual edits,
batched backfill) do not flip precedence — the reader walks line-by-line and
the last fully-terminated line per key wins.

Tolerant read rules: missing file → `{}`; empty file → `{}`; **an unreadable
file (any `OSError` — permissions, a directory in the path, a vanished mount)
→ `{}`, never a raised exception**; a trailing partial line (file does not end
with `\n`) is silently skipped, with the last fully-terminated entry winning
for that key; an unparseable line (invalid JSON) is counted as corruption and
skipped, and reduction continues; **a valid-JSON but non-object line (`[1,2,3]`,
`42`, `"x"`) is counted as corruption and skipped** — it has no `.get`, so
treating it as an entry would raise `AttributeError` on a torn store (#400);
an entry with no `ledger_entry_hash` is skipped (not counted as corruption);
and **skipped lines are surfaced once per read on stderr** as a single summary
line, `[ledger_reduce WARN] reduce: skipped N unparseable line(s) in <path>`,
never one line per bad line.

Reference implementation (inlined verbatim from `scripts/ledger_reduce.py`'s
body as of #460; that module has moved to `raddue/crucible-eval` and no longer
exists in this repo). **Transcribe this exactly — the `except OSError`
guard, the `isinstance(obj, dict)` guard, and the `skipped`/`_warn` corruption
surfacing are all #400 fixes, and an implementation missing any of them is a
regression, not a simplification.**

**No drift checker covers this block.** `scripts/check_ledger_append_doc_drift.py`
diffs each `## Reference Python — `scripts/<name>.py`` block below against its
live module — but there is deliberately no such module for this block:
`ledger_reduce.py` was deleted when it moved to `raddue/crucible-eval` (#460),
so this heading is intentionally worded differently (no `scripts/<name>.py`
in the heading) precisely so the checker's regex does NOT pick it up and fail
looking for a module that no longer exists. A future checker author extending
that script should NOT assume every Python block in this file has a
corresponding on-disk module to check against — this one never will again
unless the module is re-vendored into this repo.

```python
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
            # corruption, same as render_ledger.load_runs (moved to
            # raddue/crucible-eval, #460).
            skipped += 1
            continue
        key = obj.get("ledger_entry_hash")
        if key is None:
            continue
        out[key] = obj  # later positions overwrite earlier ones (L-9)
    if skipped:
        _warn(f"reduce: skipped {skipped} unparseable line(s) in {falsification_path}")
    return out
```

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
| L-9 | Latest-entry-wins reduction (file-position) | Defined inline above ("L-9 latest-entry-wins reduction"); `raddue/crucible-eval` carries the executable copy (#460) |

L-5 (backfill exclusion from headline; backfill script moved to
`raddue/crucible-eval`, #460) and L-10 (Brier polarity) are encoded in
design/contract; no runtime call-sites in Phase 1.

Cross-link: see `docs/plans/2026-05-18-epistemics-stack-v1-design.md`
§"Invariants" for the canonical definitions.

## Reference implementations

Authoritative source of truth: `scripts/ledger_append.py` (importable as
`scripts.ledger_append`) and `scripts/uuid7.py`. No prose copy is maintained —
the verbatim copies under `## Reference Python — `scripts/<name>.py`` headings
were removed in #643 (a prose copy of live code is the exact drift surface the
retired `check_ledger_append_doc_drift.py` canary policed, and the #460 round-4
S4 bug class). Read the module for the real code; the spec above pins behavior,
the script is the executable oracle.

