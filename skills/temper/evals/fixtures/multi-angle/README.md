# multi-angle fixture — `sessionkit`

A small, self-contained, dependency-free Python mini-project (`sessionkit`) used as
the **multi-angle detection fixture** for `temper` / `delve-engine`. It plants
**seven** defects — **one per finder angle** (`shared/delve-engine.md` §4) — each
designed to be catchable **only** by its intended angle, so the recorded
[`detection-matrix.md`](detection-matrix.md) is **diagonal** (`D = 7`, `D_bug = 3`).

This fixture is authored under #333 (AC3 / I7). #333 *authors* the fixture and *records*
the designed/intended diagonal matrix; **#335** *runs* the live recall floors on real
Claude Code + OpenCode harnesses. The matrix here is the diagonal **by construction**;
the per-harness recall validation is #335's job.

The spec's "public repo" requirement is satisfied by the crucible repo itself — the
fixture lives in-repo, runs as-is, and needs no external download.

## Layout

```
multi-angle/
├── README.md              ← this file
├── detection-matrix.md    ← the recorded 7×7 diagonal matrix + D / D_bug + bar statements
├── planted.diff           ← the seven plants as ONE unified diff (before/ → after/)
├── before/                ← correct baseline (selftest passes)
│   ├── selftest.py
│   └── sessionkit/        ← __init__.py, config.py, tokens.py, store.py
└── after/                 ← baseline + the seven plants (== before/ + planted.diff)
    ├── selftest.py
    └── sessionkit/
```

`after/` is exactly `before/` with `planted.diff` applied. The diff is the reviewable
artifact a finder angle runs against; `before/`+`after/` are kept as runnable trees so
the bug-angle reproductions can be executed.

## The mini-project

`sessionkit` is a tiny session/token utility, deliberately split across files so the
**cross-file** angle has a natural home:

- **`tokens.py`** — issue/verify a signed token (HMAC). Owns expiry, revocation,
  signature, and the on-the-wire field names (`serialize_claims` is the wire contract).
- **`store.py`** — an in-memory `SessionStore` that **reads** the token field names
  `tokens.py` writes, and answers liveness queries.
- **`config.py`** — the ONLY module that touches the filesystem (TTL / clock-skew
  config). Keeping disk IO here is what makes the **altitude** plant (disk IO inside
  the in-memory store) a genuine layer violation.

## How to run

Baseline (all behaviors hold → prints `OK`, exit 0):

```sh
cd before && python3 selftest.py
```

Planted-bug tree (the three **bug**-angle plants reproduce → assertions fail / KeyError):

```sh
cd after && python3 selftest.py     # exits non-zero; see the three failures below
```

Apply the diff yourself onto a fresh baseline copy:

```sh
cp -r before /tmp/sk && cd /tmp/sk && git apply <path>/planted.diff
python3 selftest.py                 # now fails on the three bug plants
```

`selftest.py` is identical in `before/` and `after/` and uses only the public API
(no direct field access), so it is a fair, behavior-level reproduction harness. It
covers the **three bug-angle plants only** — the four quality-angle plants are
behaviorally correct by design (pure Minor/Suggestion smells) and therefore do not
change observable behavior, so no runtime test can or should catch them.

## The seven plants (one per angle)

| # | Angle | Location (`after/`) | One-line |
|---|---|---|---|
| 1 | line-by-line | `sessionkit/tokens.py:66` | expiry boundary uses `<` where `<=` was intended (off-by-one) |
| 2 | removed-behavior | `sessionkit/tokens.py` (verify_token, deleted block) | the pre-acceptance `revoked` check was deleted |
| 3 | cross-file | writer `tokens.py:31,42` ↔ reader `store.py:26` | writer renamed `uid`→`user_id`; reader still reads `uid` → `KeyError` |
| 4 | reuse | `sessionkit/store.py:60` | `last_seen` reimplements `int(time.time())` instead of the `_now()` helper |
| 5 | simplification | `sessionkit/store.py:62` | `has_live_session` is a nested branch ladder collapsible to one boolean |
| 6 | efficiency | `sessionkit/store.py:81` | `live_fraction` recomputes the loop-invariant `len(...)` every iteration |
| 7 | altitude | `sessionkit/store.py:86` | `audit_dump` puts file-IO/log-transport inside the in-memory domain store |

See [`detection-matrix.md`](detection-matrix.md) for the full 7×7 matrix, the
separability argument for each plant, `D` / `D_bug`, and the floor / bar statements.
