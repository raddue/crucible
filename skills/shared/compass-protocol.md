---
version: 1
---

# Compass Protocol (canonical)

> Canonical write-protocol prompt for `docs/compass.md`, a per-repo arc-state
> file. Referenced by every skill that reads or writes compass state via
> `<!-- CANONICAL: shared/compass-protocol.md -->`.
>
> This file is the **protocol-as-spec**. The importable single source of truth
> is `scripts/compass.py`; on drift, the script wins.

## When to emit

Four integration points, in lifecycle order:

| Caller | Event | Fields written |
|--------|-------|----------------|
| `build` | After Gate Ledger Initialization completes AND resume decision resolves, BEFORE Phase 1 IN_PROGRESS transition. NOT during crash-recovery branches. SKIPPED if user chose resume (prior arc's `current_arc` already correct). | `current_arc` |
| `merge-pr` | After `gh pr merge` succeeds AND post-merge CI passes. | `last_meaningful_commit` |
| `finish` Option 1 | After local merge + tests pass. | `last_meaningful_commit` + arc-closure patch (`current_arc=''`, `next_move`) |
| `finish` Option 2 | After `gh pr checks --watch` returns green. Does NOT emit `last_meaningful_commit` — CI green != merged; the subsequent `/merge-pr` invocation writes the SHA. | provisional arc-closure patch only |

`finish` Options 3 and 4 emit nothing. `getting-started` reads (never writes)
via `compass read --compact` before the dispatch table.

**D14 invariant (best-effort):** compass updates fire only from skill
orchestrators, never from sub-agents inside those skills. No mechanical
enforcement in v1; auditable at PR time via call-site review.

## Schema — `docs/compass.md`

```markdown
# Compass

**Current arc:** #NNN: <one-line subject>
**Last meaningful commit:** `<sha>` — <one-line subject>
**Updated:** YYYY-MM-DD HH:MM

## Open loops
- <one line each, max 5>

## Next move
<one paragraph, max 5 lines>

## Don't forget
- <terse, max 3>
```

Five user-facing fields plus `Updated:` (minute-resolution UTC):

| Field | Type | Cap |
|-------|------|-----|
| `current_arc` | string | — |
| `last_meaningful_commit` | string | — |
| `open_loops` | list | 5 visible entries (10 hard-cap before `OpenLoopsCapError`) |
| `next_move` | string | 5 lines |
| `dont_forget` | list | 3 entries |

**40-line hard cap (D4):** any write producing >40 lines raises `CompassFullError`
(exit 2) and emits to stderr:
`[FULL] Compass at cap. Run 'compass compress' or edit docs/compass.md manually before retrying.`
No data is written. Caller surfaces the error to the user.

**`OpenLoopsCapError`:** raised post-op if `len(open_loops) > 10` (hard cap).
Recovery: re-acquire lock, revert the write, release. Exit 2, stderr advisory.
Note: the user-facing display cap is 5 entries; the hard-cap that raises
`OpenLoopsCapError` is 10. D8 paused-pushes accumulate in this headroom.

**C-9 invariant:** `docs/compass.md` is NOT gitignored. Verified via
`git check-ignore docs/compass.md` semantic check.

## Bootstrap sentinel `<pending>`

On first `compass update`, if `docs/compass.md` is missing, the script creates
it with sentinel values:

- `current_arc: <pending>`
- `last_meaningful_commit: <pending>`
- `Updated: <now>`
- `open_loops: []`, `next_move: ''`, `dont_forget: []`

`<pending>` means "never set". It is DISTINCT from empty string `''`, which
means "cleared by finish". **External callers CANNOT set `current_arc` to
`<pending>` directly — `compass update --field current_arc --value '<pending>'`
raises `ValueError` (R15-S2).** The sentinel is internal to bootstrap only.

`compass read` on a missing file: exit 0, empty stdout (~0.1ms — one
`os.path.exists()` check, no lock acquired). Non-Crucible repos are silent.

## Concurrency / lock protocol

Lock path: `/tmp/.lock-compass-<repo-hash>/` where `<repo-hash>` is the first
8 hex digits of `sha1(os.path.abspath(repo_root))`. Lock lives on the host's
local FS (`/tmp` is local ext4/APFS on WSL2 and macOS), independent of the
working-tree FS.

**Acquire steps:**

1. `mkdir /tmp/.lock-compass-<repo-hash>/`
   - Success: proceed to step 2 immediately.
   - `EEXIST`: spin with 50 ms backoff.
2. Write holder file `…/holder` with `<pid>:<acquired_ts_iso>` under the SAME
   mkdir that succeeded — holder write happens before any other work. (Writing
   holder AFTER mkdir is not a race because holder is identity evidence, not a
   secondary gate. The critical race that holder prevents is stale-recovery
   Branch B, which fires only after the 30s stale TTL.)
3. Read-modify-write `docs/compass.md` (see RMW flow below).
4. **Release:** `unlink` holder, then `rmdir` lockdir. Unlink-first order
   prevents a recovering writer from observing a present lockdir with no holder.

**Spin caps (compass-specific, tighter than ledger):**

- Inner spin: 2 s before stale check.
- Outer cap: 30 s total.

**Stale-holder TTL:** holder is stale if `pid:timestamp` is older than **30s**
OR the named pid is not alive on the local host (`os.kill(pid, 0)` raises
`ProcessLookupError` / ESRCH). On stale detection: remove holder, `rmdir`
lockdir, retry from step 1.

**PID-reuse trade-off:** the OR rule above can in principle evict a legitimate
holder if its PID was reused by an unrelated process AND the lock has been held
>30s. A legitimate compass write should never hold >30s, so the eviction is
correct in practice. When this combination is detected (alive-PID + mtime
>30s), `_try_recover_stale` writes a `[compass] warning: evicting lock held by
alive pid ...` line to stderr so the operator can investigate.

**Lock scope (cooperating writers only):** The mkdir lock protects against
concurrent `compass.py` invocations. It does NOT protect against editor saves,
manual `vim`/`echo > docs/compass.md`, or other non-cooperating writers. Such
writes may race with in-flight `compass update` calls and produce corrupt
state. Run `compass doctor` after suspected manual edits.

**Test hook:** `CRUCIBLE_COMPASS_TEST_SLEEP_MS` — bounded `[0, 5000]` ms,
default 0. Honored ONLY at well-defined sleep points inside `_acquire_lock` for
test-orchestrated contention. Leak-safe (no effect outside that function).
Document this env var before any future cleanup; its presence is intentional.

## RMW flow

1. Acquire lock.
2. Read entire `docs/compass.md` into memory (create from bootstrap template if
   missing).
3. Mutate named field via header-anchored regex.
4. Apply D8/D8.5 side-effect mutations (see below).
5. Validate: count lines; check `open_loops` length; check field invariants.
6. If any validation fails: release lock, raise appropriate error (no write).
7. Write back: single `write()` syscall for the entire file body. No partial
   flush — the file is small (<=40 lines), so one syscall covers it.
8. Release lock (unlink holder, rmdir lockdir).

**D11 idempotency:** same `update --field X --value Y` applied twice yields
the same final state. `Updated:` is bumped if and only if any field (including
side-effect fields) changed byte-for-byte. True no-ops (byte-identical body
excluding `Updated:` field) do NOT bump `Updated:`.

**Idempotent rendering:** same input state produces byte-identical output. List
elements preserve insertion order (no sort). `[CLOSED]` edge-case: when
`last_meaningful_commit == '<pending>'` AND `current_arc == ''` (Discard
followed by no merge), compact form prints `[CLOSED] No recorded commit` (omit
ticket-from-commit gracefully).

## Multi-arc collision — D8/D8.5 carve-out ordering

When `compass update --field current_arc --value <new>` fires, evaluate in
this exact order (R7-F3):

1. **D8.5 first — resume removal:** if `open_loops` contains a
   `[paused] #<ticket-of-new>:` entry (matched by ticket-id regex
   `^\[paused\] #<NNN>:`, not full-string), REMOVE it. Continue to step 2.
2. **No-op short-circuit:** if `<new>` == existing `current_arc` → idempotent
   no-op for `current_arc` itself. (D8.5 step 1 may still have produced an
   `open_loops` delta — D11 bumps `Updated:` if any field changed.)
3. **Empty-string carve-out:** if `<new>` == `''` → arc-closure path. D8 push
   is bypassed. See D10 arc-closure semantics.
4. **`<pending>` bootstrap:** if existing == `<pending>` → set new `current_arc`
   directly, no `[paused]` entry. Stderr: `[OPEN] First arc set: <new>`.
5. **Post-closure cleared state:** if existing == `''` → set new `current_arc`
   directly, no `[paused]` entry. Stderr: `[OPEN] New arc set: <new>`.
6. **Collision push:** existing is non-empty, non-`<pending>`, non-`''`, AND
   `<new>` != existing → push prior `current_arc` onto `open_loops` prefixed
   `[paused] `, set new `current_arc`. Stderr advisory:
   `[OPEN] Started new arc <new> with prior arc <old> still active — prior arc moved to open_loops`.

**Paused-entry grammar (formal):**
`[paused] #<NNN>: <subject> @ <YYYY-MM-DDTHH:MM>` (minute-resolution UTC).

**Dedup on thrash:** if a `[paused] #<old-id>:` entry already exists in
`open_loops`, UPDATE it in place (refresh subject + timestamp) rather than
appending a duplicate. A→B→A→B sequences accumulate at most one `[paused] #A:`
entry.

**D8.5 resume advisory:** stderr `[RESUME] Resuming paused arc <X>`.

**Known v1 grammar restriction (D8.5):** `current_arc` subjects cannot contain
the literal substring ` @ ` (space-at-space). D8.5 uses ` @ ` as the
timestamp delimiter when scanning paused entries. A subject such as "review @
noon" would corrupt D8.5 parsing. **This is a known limitation.** v1.1 will
relax D8.5 match to anchor on timestamp shape only. Do not silently remove this
restriction in cleanup — it is a tracked design debt.

## CLI surface

```
python scripts/compass.py <subcommand> [args]
```

| Subcommand | Description |
|------------|-------------|
| `read` | Print full `docs/compass.md` to stdout. |
| `read --compact` | Print 3-5 line summary (see D13 compact form below). |
| `update --field X --value Y [--value Y2 ...]` | Set field X to value Y (destructive for lists). |
| `update-many --field X --value Y [--field Z --value W ...]` | Atomic multi-field update under one lock acquisition. (D7 extension — convenience alias not listed in design D2.) |
| `append --field X --value Y` | Append one element to list field X with dedup. (D7 extension — convenience alias not listed in design D2.) |
| `doctor` | Self-diagnostic: validate schema, check line count, report stale status. (D7 extension — convenience alias not listed in design D2.) |
| `compress` | v1.1 stub — exits 0 with advisory to manually edit or wait for v1.1. |

**List-field semantics (D2):** list elements are passed as repeated `--value`
flags. Never delimiter-joined — entries may contain commas or newlines
naturally. `--append` switches to append-one with dedup.

**CLI mutex — `--set` vs `--append`:** `--set` and `--append` modes are mutually
exclusive. Violating this constraint raises `ValueError` (NOT
`argparse.ArgumentError`). T-C3 assertion #8 explicitly asserts `ValueError`.

**argparse pre-parser bypass:** `--set` and `--append` modes walk `sys.argv`
manually via an inside-value state machine with `--field` boundary detection
and a `--value '--field'` corner case handled with zero-or-one space tolerance.
This bypass is deliberate — standard argparse would mishandle list values that
themselves look like flags. Do not replace with argparse-style parsing without
first confirming the corner cases.

## D13 compact-form rendering

`compass read --compact` line order (pinned):

```
[ARC]   <arc line>
[NEXT]  <next_move>          (omit if empty)
[OPEN]  N loops (top: <first open_loop>)   (omit if no loops)
[STALE] last updated N days ago            (only if Updated > CRUCIBLE_COMPASS_STALE_DAYS)
[CLOSED]                                   (state-specific, replaces [ARC] when current_arc == '')
[RESUME] Resuming paused arc <X>           (stderr advisory only; NOT emitted to stdout compact form)
```

Examples:

```
[ARC] #273: Compass, designing
[NEXT] write design doc + plan + contract
[OPEN] 2 loops (top: dogfood on Crucible)
[STALE] last updated 18 days ago
```

Bootstrap state (`current_arc == '<pending>'`):

```
[ARC] No active arc — run any /build to set current_arc
```

Post-finish cleared state (`current_arc == ''`):

```
[CLOSED] Last arc closed: <ticket-from-last_meaningful_commit>
[NEXT] <next_move>
```

`CRUCIBLE_COMPASS_STALE_DAYS` (default 14): read per-call inside `read()` only.
`update()` does not emit stale advisories.

## Invariants index (C-1..C-9)

| Inv. | Statement | Enforced where |
|------|-----------|----------------|
| C-1 | mkdir is the mutex; flock never used | `_acquire_lock` in `scripts/compass.py` |
| C-2 | Holder written under the same mkdir that succeeded | Step 2 of acquire |
| C-3 | Single `write()` syscall for file body | `_write_compass` in script |
| C-4 | 40-line cap: reject-on-exceed | `CompassFullError` (exit 2) |
| C-5 | `<pending>` is internal-only; external set raises ValueError | `update()` validation |
| C-6 | D8.5 fires before D8.1 no-op short-circuit | Carve-out order above |
| C-7 | `Updated:` bumped iff any field delta (including side effects) | D11 rule in `_apply_patch` |
| C-8 | D14: compass emits from orchestrators only (best-effort, v1) | Call-site convention |
| C-9 | `docs/compass.md` NOT gitignored | `git check-ignore docs/compass.md` check |
