# Round-by-round example

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request review before proceeding.

[Step 1: Resolve scope]
- No argument given; HEAD is on branch `feat/verify`
- gh pr view (current branch) → no PR yet
- origin/HEAD → main; resolved range: origin/main..HEAD
- BASE_SHA=$(git rev-parse origin/main)
- HEAD_SHA=$(git rev-parse HEAD)

[Step 1.5: Preflight]
- numstat: 4 files changed, 87 added, 12 deleted — text diff, in-cap, proceed

[Step 2: Round 1 — drive delve-engine (bug-angle subset, effort=high, cap=20), dispatch-id temper-20260603T150500-a7f3c2]
  Engine ran non-error; C/I kept-count (2) < cap → T genuine, not truncated.
  Enumerate T (2 members):
    t1  verify.py:40  CONFIRMED / Important  — no error handling for empty input
    t2  verify.py:55  PLAUSIBLE / Important  — progress callback may fire after cancellation (no runnable repro)
  Minor: 1 (magic number) — non-gating, not in T.
  Each member: readjudicated=false.

You: [Fix both members of T — t2 (PLAUSIBLE@Important) gets the same fix priority as t1 (CONFIRMED)]

[Step 4: Round 2 — Track A (delve-engine over fix delta + cheap full-diff sweep, cap=20) + Track B (one temper-reviewer per member, against the WHOLE fixed tree)]
  Track B — re-verify carried members:
    t1 → RESOLVED (empty-input guard now present)
    t2 → REFUTED-after-fix (DISCHARGE: the post-cancellation callback path is provably gone) — leaves T
  Track A — NEW gating finding admitted to T (readjudicated=false):
    t3  verify.py:48  CONFIRMED / Important  — the new guard swallows a real I/O error
  All carried members resolved/discharged, BUT a new gating finding entered this round.
  → Verdict: Issues-Found (NOT Clean — a new-admit round is never Clean). Loop continues.

You: [Fix t3]

[Step 4: Round 3 — Track A + Track B]
  Track B — re-verify carried member:
    t3 → RESOLVED (I/O error now re-raised)
  Track A — no new gating finding admitted; C/I kept-count (0) < cap (un-truncated).
  Every member of T resolved/discharged AND no new gating finding entered.
  → Verdict: Clean. Proceed to Task 3.
```

The Round-2 verdict is **Issues-Found, not Clean**, even though both carried members resolved — Track A admitted a new gating finding (`t3`), and a new-admit round is never Clean. Clean is reached only in Round 3, which resolves the carried member and admits no new gating finding.

