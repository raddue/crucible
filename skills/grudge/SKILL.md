---
name: grudge
description: >
  The Book of Grudges — cross-session bug graveyard. Every fixed bug is recorded
  as a structured "grudge"; before touching code, skills query the grudgebook for
  the files in scope and surface past regressions as forced "DO NOT REPEAT"
  context. Read mode (pre-flight) and write mode (on bug resolution / fix(*) PR).
  Machine-local, per-repo, never committed. Triggers on /grudge, "check grudges",
  "record a grudge", "any past bugs here", "regression oracle", "bug graveyard".
---

# Grudge — the Book of Grudges (#271)

> Named for the dwarven Dammaz Kron: every wrong is written down and **never
> forgotten until it is settled.** A fixed bug becomes a grudge the toolchain
> holds against the files that caused it — and refuses to let happen again.

Stock Claude Code has no memory across sessions, so the same class of bug
re-ships. The grudgebook closes the loop: **write-on-resolution** +
**read-on-preflight**.

## Where grudges live (read this first)

The grudgebook is **machine-local and per-repo**, NEVER inside a git tree:

```
$CRUCIBLE_GRUDGE_DIR  (or ~/.claude/crucible/grudge)
  /<repo>/grudges/<hash>.md
```

Grudges carry private file paths + repro detail and crucible is PUBLIC, so the
live store must stay outside any repo (mirrors the calibration ledger central
store, PR #326). `scripts/grudge_append.py` **refuses** to write into the current
repo's tree. The committed `.crucible/grudge/grudges/*.md` are **synthetic
fixtures only**. Isolation is by `repo_root` (git toplevel realpath), so two
checkouts that share a basename never bleed into each other.

## Resolving the helpers (cwd-independent)

A gating skill runs with an arbitrary cwd, so locate the scripts by absolute path
from the plugin root (same convention as `shared/ledger-append.md`):

```
# plugin layout is invariant: <plugin_root>/skills/<name>/ and <plugin_root>/scripts/
plugin_root="$(realpath "<this-skill-base-dir>/../..")"
query="$plugin_root/scripts/grudge_query.py"
append="$plugin_root/scripts/grudge_append.py"
# If unresolved: emit a one-line stderr warning and SKIP. The grudgebook is
# advisory; a missing query/record must NEVER block or fail the host skill.
```

## Read mode (pre-flight — "what grudges do we hold here?")

Before writing/reviewing code, pass the in-scope files (absolute, `./`-prefixed,
or repo-relative — all normalized) to the query helper and inject any output into
your working context as a hard constraint:

```
python3 "$query" path/to/file1 path/to/file2 [--with-signatures] [--limit N]
```

- Path match is always on. Add `--with-signatures` when you already have file
  contents in hand (it greps `anti_pattern_signature` regexes against file bodies).
- Non-empty output = grudges held against these files. Treat each `☠` line as
  **DO NOT REPEAT** — do not re-introduce that bug.
- Maintenance: `--stats` (how many grudges held / recently written — spot
  starvation) and `--cull` (strike settled grudges whose files are all gone).
- A stderr line `grudge: scanned=… matched=… skipped_stale=…` always prints so a
  silent/empty grudgebook is visible.

## Write mode (record a grudge — on bug resolution / fix(*) PR)

When a bug is confirmed fixed, record it (best-effort; a failed record logs to
stderr and never fails the host skill):

```
python3 "$append" \
  --symptom "one-line observable failure" \
  --root-cause "one-line underlying cause" \
  --files "src/a.py,src/b.py" \
  --signature "optional regex or literal snippet that fingerprints the bug" \
  --commit "<fixing sha>" \
  --repro "minimal repro steps" \
  --why "why this kept happening"
```

## Grudge schema

```markdown
---
schema: 1
hash: <sha256(repo_root|sorted-normalized(files_touched)|discriminator)[:12]>
repo: <basename>            # cosmetic dir name
repo_root: <abs realpath>   # isolation key; reads filter on this
fixed_in_commit: <sha>      # recorded, NOT part of the key
symptom: <one-line>         # dedupe discriminator when no signature
root_cause: <one-line>
files_touched: ["repo/rel/path", ...]
anti_pattern_signature: "<regex or literal snippet>"   # optional
date_fixed: YYYY-MM-DD
---
## Repro
<steps>
## Why this kept happening
<expanded root cause>
```

**Dedupe:** key excludes `fixed_in_commit` (one bug can be fixed in many commits);
`discriminator = anti_pattern_signature` when non-empty else `symptom`. Same key →
overwrite (last write wins). A grudge with neither files nor a discriminator is
rejected.

## Consumers (where the wiring lives)

- **Pre-flight (read):** `build` (Phase 2, post-design/pre-implementation),
  `quality-gate` (round-1 dispatch), `debugging` (opening phase).
- **Write:** `debugging` (resolution phase), `merge-pr` (on `fix(*)` PRs).

## Non-goals (v1)

No semantic search (glob + regex only); no cross-**user** shared grudgebook
(sanitized community grudges — v1.1 candidate); no `settings.json` hook.
