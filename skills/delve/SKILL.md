---
name: delve
description: Standalone instance-bug reviewer — runs a parallel finder fan-out + verify gate over a diff or a path and prints ranked, verified findings. Use when the user says "delve", "find bugs in this diff", "review this for bugs", "scan this file/subsystem for defects", "instance-bug sweep", or wants concrete reproducible defects (not a merge verdict, not systemic health). Works on a PR id, a base..head range, or a path, on any forge (GitHub, GitLab, Bitbucket, self-hosted).
---

# Delve

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/delve-engine.md -->
The finder angles, the verify gate, the effort tiers, and the output schema are NOT redefined here — they live in `shared/delve-engine.md`. `/delve` is the **thin standalone driver** of that engine: it resolves a scope, runs the engine **once**, and handles output (report / optional `--fix` / optional `--comment`).

<!-- CANONICAL: shared/severity-verdict-contract.md -->
The `severity` and `verdict` vocabularies the findings carry are the contract's, not delve's. See `shared/severity-verdict-contract.md`.

`/delve` is the **standalone instance reviewer** of the review trio. It owns ONE concrete defect with one reproduction (even across files); it does not own systemic patterns (that is `/audit`), the merge gate (that is `/temper`), or codebase exploration (that is `/recon` / `/prospector`).

**Authored fresh, clean retro slate.** delve is a freshly-authored fan-out wrapper — nothing is seeded from any existing skill, and it inherits **none** of the old `code_review` forge-retrospective lessons (that lineage forks to `temper`). On Claude Code the built-in `/code-review` still exists; there is no collision (different name), and the built-in stays an **optional accelerator**, never a dependency (I1).

## Non-Goals

`/delve` finds and reports **instance bugs**. Use a different skill for:

- **A merge verdict / iterative fix-loop** — use `/temper` (delve runs the engine once and reports; it never loops and never emits Clean / Issues-Found).
- **Systemic health** — subsystem-wide patterns, absences, structural drift with no single reproduction — use `/audit`. A finding with one concrete reproduction is delve's even when it spans multiple files; a no-single-repro pattern is audit's.
- **Codebase exploration / redesign** — "what should I refactor", architectural friction — use `/recon` or `/prospector`.
- **Iterative red-team of any artifact** (design docs, plans) — use `/quality-gate`.

## Dependencies

| Component | Required? | Purpose | Fallback if missing |
|---|---|---|---|
| `git` | Required (diff scope) | Diff resolution, SHA range, default-branch detection | None — abort with a clear error. Not required for a pure path scope. |
| `shared/delve-engine.md` | Required | The fan-out + verify gate this skill drives | None — abort; delve has no engine of its own. |
| Forge CLI (`gh` / `glab` / `bb`) | Optional | PR-metadata fetch (diff scope) + `--comment` post-back | Probe in order; fall back to git plumbing / paste-mode. Never a hard dependency (I1). |

## Invocation

```
/delve                            # auto-detect diff scope (origin default-branch..HEAD)
/delve 259                        # PR identifier on the current forge → its diff
/delve https://...                # PR URL on any forge → its diff
/delve main..HEAD                 # explicit SHA range
/delve src/session/               # path / subsystem sweep over standing code
/delve src/auth.ts effort=high    # path sweep, recall-biased
/delve 259 --fix                  # apply confirmed fixes to the working tree
/delve main..HEAD --comment       # post findings inline on the PR (or paste-fallback)
/delve src/ line-by-line,cross-file effort=max   # angle subset + exhaustive recall
```

**Argument shape:** `[PR-id | <base>..<head> | <path>] [angles] [effort=low|medium|high|max] [--fix] [--comment]`

- **`[PR-id | base..head | path]`** — the scope (Step 1). A diff scope (PR / range / auto-detect) OR a path/subsystem.
- **`[angles]`** — a comma-separated **subset** of the seven engine angles (`line-by-line`, `removed-behavior`, `cross-file`, `reuse`, `simplification`, `efficiency`, `altitude`). Default: **all seven**. Passed straight to the engine's `angles` input — delve never forks the angle set.
- **`effort`** — `low | medium | high | max`. Default **medium** (the engine default). Passed to the engine's `effort` input.
- **`--fix`** — after reporting, apply fixes to the **working tree only** (Step 4). Off by default.
- **`--comment`** — after reporting, post findings to the forge inline, or paste-fall-back (Step 5). Off by default.

`external_candidates` is **not** a delve input — it is empty for standalone delve (only `temper` with `external_review` enabled populates it). delve drives the engine with `scope`, `angles`, `effort`, and `cap`.

## How it works

### Step 1: Resolve the scope (forge-agnostic)

First decide whether the argument is a **diff scope** or a **path scope**. These rules are an **ordered precedence** — apply them top to bottom and stop at the first match (they are not an unordered set, so a bare integer that also names a path on disk is never silently misclassified):

1. **No argument** → **diff-scope auto-detect** (below).
2. **Token contains `..`** → **diff scope** (SHA range).
3. **Bare integer or a URL** → **diff scope** (PR) — even if a same-named path exists on disk.
4. **Otherwise, resolves to an existing path on disk** (file or directory) → **path scope**.
5. **Else** (argument present but unresolved) → **usage error**; report the unresolved argument and stop.

(Escape: to force a path that looks like a PR number, pass it with a `./` prefix or a trailing slash — e.g. `./259` or `259/` — so it matches rule 4 instead of rule 3.)

**Diff scope.** Resolve to a `<base>..<head>` SHA range following temper's Step 1 resolution — forge detection is **CLI-probe order, not hostname-literal**:

- **PR number / URL.** When the argument is a URL, parse the forge from the host and use **only** the matching CLI (`gh` for GitHub / GHE, `glab` for GitLab, `bb` for Bitbucket); unknown host → git plumbing, ask the user to paste the description. When it is a bare PR number, probe `gh` → `glab` → `bb` against the current `origin`; if none succeed, fall back to git plumbing (`git fetch <remote> pull/<id>/head` or `merge-requests/<id>/head`). Map the fetched `baseRef`/`headRef` to SHAs via `git rev-parse`.
- **SHA range** (`..` present). Use as-is.
- **Auto-detect (no argument).** (1) If HEAD is detached, **require** an explicit argument — abort with a one-line instruction. (2) Try forge-CLI detection of the current branch's PR; if found, treat as PR. This probe obeys the same error-vs-missing rule as below — a present-but-failing CLI (auth-fail / 403 / rate-limit / network) has its error surfaced and pauses; only an unambiguous "no PR for this branch" advances to the default-branch step. (3) Else resolve `git symbolic-ref refs/remotes/origin/HEAD` and use `<that-ref>..HEAD`. (4) If `origin/HEAD` is unset, fall back to the single existing `origin/{main,master,trunk}`; if more than one exists, **abort** and ask for an explicit range.

**Distinguish CLI errors from missing CLIs.** A CLI that exits non-zero with "404 / not found / auth required" is **not** a missing-CLI fallback path — surface the error and pause. Falling through silently would run against the wrong scope.

**Anti-rationalization:** never hardcode `gh` (or any single forge CLI) in the path. delve is forge-agnostic; the CLI used is whichever the environment provides.

**Path scope.** Use the path verbatim as the engine's `scope` — this is an **instance sweep over standing code**, not a diff. No SHA range, no PR metadata, no `git diff`. The engine's removed-behavior angle has no deletions to read in a pure path sweep; it simply contributes nothing rather than erroring.

### Step 1.5: Diff preflight (diff scope only)

For a diff scope, run `git diff --numstat <base>..<head>` and classify before spending a fan-out:

- **Empty diff:** report `No changes to review` and stop. Do not dispatch.
- **Binary-only diff:** note that content is uninspectable; do not report fabricated findings.
- **Mixed text + binary:** review the text portion; note the binary files were not read.
- **Oversized diff** (>5,000 added+deleted lines): warn and offer to narrow by path or commit; if the user proceeds, note the over-cap so the run carries a context-degradation caveat.

(Path scope has no diff to preflight; a path that resolves to nothing on disk is a usage error — abort with the resolved path.)

### Step 2: Run delve-engine once

Drive `shared/delve-engine.md` a **single** time with:

- `scope` = the resolved diff range **or** the path from Step 1 (echoed onto every output record by the engine).
- `angles` = the `[angles]` subset, default all seven.
- `effort` = the requested tier, default `medium`.
- `cap` = `10` by default. When `effort=max`, pass a deliberately **large ceiling** — well above any plausible kept-finding count — so the ranked output is never truncated. `cap` is an engine **input** (delve-engine §2), fixed before the single run; it cannot be sized to a same-run kept count (that count exists only after the verify gate, and delve drives the engine once). The engine ranks most-severe-first and `cap` truncates only that ranked output (delve-engine §6), so a `max` sweep left at the default `10` can drop a confirmed finding it paid to verify — choose a high ceiling at input time rather than rely on the default.

The fan-out (finder angles) and the per-candidate verify gate run as parallel subagents **through the harness-adapter dispatch mechanism** — delve issues **no harness-specific call inline** (I1). On a harness with no parallel-subagent primitive, the adapter's **sequential fallback** runs the angles as multiple sequential passes (one per angle), never collapsed into a single in-context pass; it warns once that recall may drop.

<!-- CANONICAL: shared/calibration-weighted-dispatch.md -->
**Calibration-weighted dispatch (advisory).** Before driving the engine, derive the file list from the resolved `scope` (`git diff --name-only` for a range, or the path's file set), resolve `scripts/brier_advisory.py` by absolute path from the plugin root, and run `python3 <script> advise delve <file list…>`. If it prints a DispatchAdvice block, attach it verbatim to the per-angle finder prompt context the engine dispatches (the same engine-dispatch boundary on both the parallel and sequential-fallback paths), as scrutiny hints (NOT as findings, NOT scored). Best-effort: on empty output or any error, dispatch normally. See `shared/calibration-weighted-dispatch.md`.

delve runs the engine **once**. There is no fix-verification loop and no second round — that cadence belongs to `temper`.

### Step 3: Report (always)

Print the engine's kept findings (CONFIRMED + PLAUSIBLE), ranked most-severe-first, capped. Each finding is the engine's eight-field record:

```
{file, line, summary, failure_scenario, severity, verdict, scope, effort}
```

The engine returns the **already-ranked, already-capped** set; delve re-groups by severity for **display only** (Critical → Important → Minor → Suggestion) and never re-truncates or re-caps per band. Within a band, **preserve the engine's returned order** (most-severe-first per delve-engine §6); delve adds no sort key of its own. Each line shows `file:line`, the summary, the verdict, and the failure scenario. State the run's `scope`/`effort` once at the top (they are identical on every record). When the kept Critical/Important count exceeds `cap`, surface a truncation caveat to the user (per delve-engine §6 — treat truncation of a gating finding as a signal) rather than presenting the capped list as complete; delve does not change the engine's cap, it only flags the condition. If the engine returns nothing, report `No verified findings` — not a Clean **verdict** (delve has no verdict; that distinction is temper's).

**Output policy:** report only. delve never emits a merge verdict and never gates. `--fix` and `--comment` below are optional add-ons, not part of the report contract.

### Step 4 (optional, `--fix`): Apply fixes to the working tree

When `--fix` is passed, apply fixes for the reported findings to the **working tree only** (I9):

- Edit files in place. **Never** commit, never push, never open a PR — the user reviews and commits.
- Fix priority follows **severity**, not verdict — Critical/Important first. A `PLAUSIBLE@{Critical,Important}` finding is a **real regression** per `shared/severity-verdict-contract.md` (PLAUSIBLE only because the verifier had no runnable repro, not because it is doubtful) and gets the **same fix treatment as a CONFIRMED one** — verdict does not down-weight it.
- The only reason to **surface rather than apply** is when the **fix itself is ambiguous** — the correct change is unclear, multiple valid repairs exist, or it would need a behavioral decision. That is a property of the repair, not of the verdict label; never withhold a fix merely because a finding is PLAUSIBLE.
- Do not touch quality-angle Minor/Suggestion findings unless they are trivially safe; surface them for the user to decide.
- After editing, summarize what changed (file + finding it addresses). The user sees a working-tree diff they can inspect, amend, or revert.

If `--fix` is combined with a path scope, the same rule holds: working tree only. `--fix` may edit **any file a kept finding names** (consistent with the cross-file angle, which can implicate a reader in another file) — still working-tree only, and not confined to files inside the path scope.

### Step 5 (optional, `--comment`): Post findings to the forge

`--comment` is an **output convenience**, not part of the report contract. It applies to a **diff scope with a resolvable PR** (a path sweep has no PR to comment on — if `--comment` is passed with a path scope, a bare SHA range with no PR, or an auto-detected range with no associated PR, fall straight through to paste-mode).

delve first writes the Step 3 formatted report body to a `findings.md` file, which the post-back commands below read. Post inline using whichever CLI fits the detected forge — **forge-agnostic**, mirroring temper Step 5 and backed by the harness-adapter forge-comment mapping:

- GitHub → `gh pr review <id> --comment --body-file <findings.md>`
- GitLab → `glab mr note <id> -m "$(cat findings.md)"`
- Bitbucket → `bb pr comment <id> --file findings.md` (or REST)
- No forge detected / unknown host / harness lacks a posting primitive → **paste-mode**: print the formatted body for the user to paste.

**Never silently drop the comment** (I9). On a non-zero exit, first **re-query PR state** via the matching forge CLI before classifying — `gh pr view <id> --json state,mergedAt` / `glab mr view <id>` / `bb pr view <id>` — and map the reported state onto a table row (open-but-failed → auth/rate-limit row; closed-without-merge → closed row; merged or absent → merged/deleted row). When the forge **cannot report state** (unknown host, Bitbucket/REST gap, or the probe itself errors), **default to paste-mode** and never silent-drop (I9) — a transient or unclassifiable error must surface the body, not swallow it — EXCEPT where state is positively classified as merged/deleted (the table's last row), which surfaces locally without paste. Then classify:

| Failure mode | Response |
|---|---|
| Auth-fail / token expired / rate-limit (403) / network error | Paste-mode with retry guidance: "Posting failed with `<error>` — re-authenticate / wait and retry, or paste the body manually below." |
| PR closed-without-merge | Paste-mode with conditional guidance: "PR is closed; paste the body if you intend to reopen, otherwise the findings remain in your session." |
| PR merged or deleted | Do **not** offer paste-mode; surface locally: "The PR is no longer postable (merged / deleted). Findings remain in your session." |

The findings are complete after Step 3 regardless of whether `--comment` succeeds.

## Dispatch

delve drives `shared/delve-engine.md` through the harness-adapter **fan-out mechanism** (`shared/harness-adapter.md` §4, §7) — never a harness-specific call inline (I1). Where a harness has no parallel-subagent primitive, the adapter's **sequential fallback** (§5) runs the angles as multiple sequential passes, warning once that recall may drop.

delve is one of the **exactly two** files that dispatch `delve-engine` directly (the other is `temper`). The canonical engine-dispatch marker line follows; the I2 allowlist test keys on it with the anchored pattern `grep -rn '^dispatch: delve-engine'`:

dispatch: delve-engine

## Example

```
/delve src/session/ effort=high

[Step 1] Path scope: src/session/ (instance sweep over standing code)
[Step 2] delve-engine — angles=all7, effort=high, cap=10 (via harness-adapter fan-out)
         fan-out → dedup → one verifier per candidate
[Step 3] Verified findings (scope=src/session/, effort=high):

  CRITICAL
  - middleware.ts:30  reader reads claims.expiresAt after writer renamed it to exp
      verdict CONFIRMED — every request after deploy reads undefined exp → total auth outage
  - token.ts:88       revoked-token check removed before acceptance
      verdict CONFIRMED — a revoked token is presented, the check is gone → revocation bypassed
  IMPORTANT
  - token.ts:42       boundary expiry uses < instead of <=
      verdict CONFIRMED — a token at its exact expiry second is accepted for one second
  SUGGESTION
  - token.ts:60       three-branch if/else collapsible to one ternary
      verdict PLAUSIBLE — readability only

  (REFUTED candidates, e.g. the JWKS re-parse, were dropped by the verify gate and never appear.)
```

With `--fix`, delve would edit `middleware.ts`, `token.ts` in the working tree and summarize the changes. With `--comment` on a PR scope, it would post the same ranked list inline or paste-fall-back.

## What delve never does

- Loop / re-review / emit a merge verdict (Clean / Issues-Found) — that is `temper`.
- Report a systemic pattern with no single reproduction — route it to `/audit`.
- Commit, push, or open a PR — `--fix` touches the working tree only.
- Silently drop a `--comment` — it always posts or paste-falls-back (I9).
- Hardcode a single forge CLI or depend on a harness built-in command (I1).
- Fork the engine — it selects `angles`/`effort`/`scope`/`cap` and drives the one shared engine.
