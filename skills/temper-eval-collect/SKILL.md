---
name: temper-eval-collect
description: Internal temper-eval harness — not auto-routed; invoke explicitly via /temper-eval-collect. Live-dispatch phase of temper eval harness. Reads stage-manifest.json from a pre-staged dispatch dir; fans Task-tool reviewer dispatches in parallel (max 6); writes per-seq result files; exits. Single bounded session. Pairs with `python -m skills.temper.evals.run_evals stage` and `score`.
model: opus
---

<!-- CANONICAL: shared/dispatch-convention.md -->

# Temper Eval Harness — Collect Phase

**Invocation:** `/temper-eval-collect <run-id> [--max-parallel N] [--timeout N]`

**Pre-conditions:**
- `python -m skills.temper.evals.run_evals stage <run-id>` has run successfully
- Dispatch dir exists at `${XDG_RUNTIME_DIR:-/tmp}/${USER:-$(id -u)}-crucible-dispatch-<run-id>/`
- `stage-manifest.json` is present

**Post-conditions:**
- Each `trials[].seq` in the manifest has either a `<NNN>-result.md` file OR an `<NNN>-result.md` whose first line begins `DISPATCH_STATUS: ERROR:`
- `.collect-status` exists with two lines: `complete` and `errors: <N>/<total>`

## Procedure

### Step 1: Validate run-id (I-9)

The run-id must match `^[A-Za-z0-9_][A-Za-z0-9_-]{0,31}$` (M-FE-3 R3: aligned with `_runid.py`'s `_RUN_ID_RE`; same shape disallows leading `-` to avoid argparse confusion). If not, refuse with explicit error and exit.

### Step 2: Resolve and stat the dispatch directory (SP-3 step 1)

Compute `dispatch_dir = ${XDG_RUNTIME_DIR:-/tmp}/${USER:-$(id -u)}-crucible-dispatch-<run-id>/`.

If `dispatch_dir` does NOT exist, refuse with the explicit error message `no staged run with id <X>` and exit. DO NOT proceed to the atomicity probe — this distinguishes "operator typo / not-yet-staged" from "filesystem cannot do atomic renames."

### Step 3: Behavioral atomicity probe (SP-3 step 2, F-1, SP-α, S-R4-4)

Inside `dispatch_dir`:
1. Write `.atomicity-probe.tmp` with content `probe`
2. Call `os.replace(.atomicity-probe.tmp, .atomicity-probe)`
3. If the rename raises `EXDEV`, `EPERM`, `PermissionError`, or any other `OSError`, refuse with explicit error naming the errno and exit
4. **S-R4-4 fsync structural probe:** open `.atomicity-probe` for read (or retain the fd from step 1's write), call `os.fsync(fd)`, and catch `OSError` / `EINVAL`. If fsync raises, refuse with the explicit error: `"filesystem rejects fsync (.collect-status happens-before barrier (I-12) cannot be guaranteed); refusing to proceed."` and exit. This catches the case where fsync is structurally rejected on certain FUSE/9P/drvfs mounts. The probe still does NOT prove crash-time durability (kernel/FS guarantee, outside Python introspection) — but it catches the structural-rejection case which would otherwise silently void I-12.
5. Delete `.atomicity-probe` on success.

This probe verifies same-directory rename returns success without errno AND that fsync is at least structurally accepted by the underlying FS. It does NOT prove crash-time atomicity or durability — those are kernel/FS guarantees outside Python introspection.

**M2 R6 — mixed errno/exception vocabulary is intentional:** the probe lists both Python exception classes (`PermissionError`, `OSError`) and POSIX errno names (`EXDEV`, `EPERM`, `EINVAL`). This is deliberate, not sloppy. Exception classes are what Python-side `except` clauses actually catch; errno names give documentation-side specificity (e.g. `EXDEV` is the precise signal for a cross-device rename, which `OSError` alone does not narrate). Keep both vocabularies side by side — operators reading this skill see the errno, code maintainers writing the catch see the exception class. Do not "normalize" to one or the other.

### Step 4: Clean stale `.tmp` files AND stale `.atomicity-probe` (SP4)

Glob `dispatch_dir/*.tmp` and delete any matches. Stale `.tmp` files are residue from prior crashed runs.

Also delete any stale `dispatch_dir/.atomicity-probe` file (residue from a prior probe that crashed before its cleanup step). The probe in Step 3 writes a fresh one; leaving a stale file behind could mask a probe-side write failure.

### Step 5: Read stage-manifest.json

Load `dispatch_dir / "stage-manifest.json"`. Extract:
- `trials` list
- `dispatch_timeout` (default 300)
- If `--timeout N` was passed on invocation, override dispatch_timeout to N and append `{"event": "timeout-override", "value": N}` to `manifest.jsonl`. Do NOT rewrite stage-manifest.json itself.

### Step 6: Determine missing seqs (idempotency)

For each `trial` in `trials`:
- If `dispatch_dir / trial.result_file` EXISTS, skip (idempotent resume)
- Otherwise add to the dispatch queue

If the queue is empty, jump to Step 8.

### Step 7: Dispatch in waves of max_parallel

**M-R7-4 cross-reference:** Task-tool parallel-dispatch limits at 6-way fanout for opus subagents are empirically untested within crucible — see the "Task-tool parallel-dispatch limits" entry in the "Risks + Mitigations" section near the end of this plan. The wave-based dispatch keeps surface bounded; `max_parallel` is operator-tunable via CLI flag without code changes if the 6-way default proves unreliable.

Default `max_parallel = 6`. For each wave (up to ceil(queue_size / max_parallel) waves):
1. Pre-allocate next `max_parallel` seqs from the queue
2. For each seq, dispatch a Task tool call:
   - `subagent_type: general-purpose`
   - `model: opus`
   - `prompt`: a pointer prompt of the form `You are a temper reviewer. Read your full instructions at <dispatch_dir>/<NNN>-reviewer.md. Begin by reading that file.`
   - Carry per-dispatch timeout: dispatch_timeout (default 300)
3. **Dispatch all in the wave in a single message with parallel tool calls.**
4. Await all wave results.
5. For each completed dispatch:
   - **Result-size check (I-10):** if the subagent's response exceeds 10 MB (10,485,760 bytes), write the ERROR sentinel below instead of the body.
   - Write the result file atomically:
     - On OK with non-empty body: write `dispatch_dir / "<NNN>-result.md.tmp"` with content `"DISPATCH_STATUS: OK\n\n" + body`, then `os.replace()` to `<NNN>-result.md`
     - On OK with EMPTY body (S1): if `body.strip() == ""` (empty OR whitespace-only — aligns with `_parse_result_file`'s strip-check, Task 7 S1 R10 alignment), promote to `"DISPATCH_STATUS: ERROR: empty-body\n\n"` — do NOT write a bare `OK\n\n` result. This ensures `_parse_result_file` sees an explicit ERROR sentinel rather than treating empty-body OK as ambiguous. Same `strip()` semantics on both sides; no silent-N/A whitespace path.
     - On timeout: write content `"DISPATCH_STATUS: ERROR: timeout\n\n"`
     - On other error: write content `"DISPATCH_STATUS: ERROR: <reason-token>\n\n"`
     - On oversize: write content `"DISPATCH_STATUS: ERROR: output-too-large\n\n"`
   - Append to `manifest.jsonl`: `{"seq": N, "file": "<NNN>-reviewer.md", "role": "temper-reviewer", "phase": "collect", "task": <N>, "status": "completed" | "failed", "duration_s": <s>, "summary": "<one-line>"}`

**S2 — manifest.jsonl serial-append discipline:**
- All `manifest.jsonl` appends are performed by the main agent SERIALLY after `await all wave dispatches` completes. Do NOT delegate appends to subagents — interleaved writes from N parallel processes corrupt JSONL.

**2P-FE-5 R3 / S-R4-5 — sanitize `summary` to prevent DISPATCH_STATUS confusion:**
- The `summary` field captures a one-line reviewer-output excerpt. Reviewer outputs may legitimately contain the literal substring `DISPATCH_STATUS:` (e.g. in a citation, a code review note about this very harness, or copy-pasted dispatch headers). If the substring survives into `manifest.jsonl`'s `summary` field, future audit tools that grep `manifest.jsonl` for `DISPATCH_STATUS:` will mis-attribute the summary text as a sentinel line.
- **Enforcement (S-R4-5):** the sanitize transform lives in `skills/temper/evals/_runid.py` as the pure-Python helper `sanitize_summary(s: str) -> str` (added in Task 1). The skill MUST invoke this helper before writing the `summary` field. Do NOT re-derive the transform inline in the skill body; the helper module is the single source of truth and is covered by `test_sanitize_summary_replaces_literal` in `test_runid.py`.
- **Concrete shell invocation (2P-5 R5):** when composing a manifest.jsonl entry from the skill body, sanitize the raw summary via:

  ```bash
  summary_sanitized=$(python -c 'from skills.temper.evals._runid import sanitize_summary; import sys; sys.stdout.write(sanitize_summary(sys.stdin.read()))' <<< "$raw_summary")
  ```

  Note: `sys.stdout.write(...)` (rather than `print(...)`) preserves the original string byte-for-byte without an appended newline, so the sanitized text round-trips cleanly into a JSON `summary` field. If the skill is composing manifest.jsonl inside a Python helper that already runs in the same process, prefer direct `from skills.temper.evals._runid import sanitize_summary` over shell-out (cheaper, no subprocess).
- The transform itself: replaces any literal `DISPATCH_STATUS:` substring (case-sensitive, since the sentinel is uppercase-only) with `[DISPATCH_STATUS_LITERAL]`. One-way and lossy by design — auditors who need the raw reviewer output should read the `<NNN>-result.md` file (where the sentinel is unambiguously on the FIRST LINE), not the `manifest.jsonl` summary field.

**S-1 — stage-manifest fingerprint concurrent-restage detection (replaces mtime rule):**

The original mtime-based rule ("refuse if `manifest.jsonl` mtime > start-of-run") self-conflicts because collect's own appends update manifest.jsonl's mtime. Replace with a fingerprint check against `stage-manifest.json` (which is only written by `stage`, never by `collect`):

1. At collect start, compute `stage_manifest_sha = sha256(stage-manifest.json bytes)` and retain in memory.
2. Before each `manifest.jsonl` append AND before each Task-tool dispatch, re-read `stage-manifest.json` and recompute its sha256. If the sha differs from the start-of-run fingerprint, refuse with the explicit error: `"stage-manifest.json mutated mid-collect (concurrent re-stage detected); aborting."` — and exit WITHOUT writing `.collect-status`.
3. This works because `stage-manifest.json` is only written by `stage`, never by `collect` — any mtime/content change reflects an external `stage --force` or manual edit.

Re-staging (`stage --force`) while a `/temper-eval-collect` invocation is mid-run is undefined behavior and the fingerprint check catches it loud.

### Step 8: Compute error ratio and write `.collect-status`

After all seqs have result files:
- Count seqs whose result file's first line begins with `DISPATCH_STATUS: ERROR:` → `errors`
- `total` = total number of trials in stage-manifest

Write `dispatch_dir / ".collect-status"` with content:
```
complete
errors: <errors>/<total>
```

Then `fsync(.collect-status)` — this serves as the happens-before barrier for `score` (I-12).

Exit cleanly.

## Failure Modes

- **Dispatch dir missing:** refuse with "no staged run with id <X>"; do NOT probe.
- **Non-atomic rename:** refuse with the errno reported by os.replace.
- **Subagent crash mid-wave:** the partial wave's missing seqs are picked up on re-invocation (idempotency).
- **Compaction during a wave:** orphaned subagent risk (Q-O4); resume re-dispatches missing seqs. Empirically unverified.

## Invariants

This skill enforces: I-7 (atomicity probe), I-8 (`.collect-status` written), I-9 (run-id regex), I-10 (10 MB result-size ceiling), I-12 (`.collect-status` fsync barrier).

## Note on wave-parallelism verification (2P-2)

Wave-parallelism is a skill-execution-time behavior — the Task tool fan-out happens inside an agentic loop and is not introspectable from pytest. AC-5 (collect produces result files) alone does NOT verify parallelism; it only verifies completeness. True parallelism verification requires manual post-merge inspection of an actual `/temper-eval-collect` run (e.g. wall-clock measurement: 6 dispatches at 60 s each should complete in ~60-90 s, not 360 s). Treat the manual measurement as a one-time post-merge validation, not as a per-PR gate.
