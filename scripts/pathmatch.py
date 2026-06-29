#!/usr/bin/env python3
"""Path-aware glob matching — the single source of truth (#401).

Extracted from the verbatim-duplicated `_glob_match` that lived in BOTH
`reconcile_ledger.py` and `grudge_query.py` (PR #340). Both copies feed the
central calibration ledger / grudge store, and reconcile's copy carries the
warning that wrong semantics silently flip a Brier `actual` value — so a fix
landing in one copy while the other drifted was a correctness hazard. There is
now one implementation; `test_pathmatch.py` pins its contract.

Pure stdlib. No third-party deps.
"""
import fnmatch


def glob_match(path: str, pattern: str) -> bool:
    """A `*` matches within ONE path segment and does NOT cross `/`
    (shell/git non-recursive semantics).

    `fnmatch` alone treats `/` as an ordinary character, so `src/auth/*` would
    over-match `src/auth/sub/deep/x.ts` and credit a verdict for an unrelated
    deep-tree fix — silently corrupting calibration (a fired predicate flips a
    FAIL's Brier `actual` 1->0). We require equal segment counts and fnmatch each
    segment pairwise, so `src/auth/*` matches `src/auth/token.ts` but not
    `src/auth/sub/x.ts`. Exact (glob-free) paths fall out as segment-wise equality.

    fnmatchcase (NOT fnmatch): case-SENSITIVE regardless of host OS. git paths
    are case-sensitive posix; plain fnmatch case-folds on macOS/Windows, which
    would make calibration non-reproducible across machines feeding one ledger.
    """
    p_seg = path.split("/")
    pat_seg = pattern.split("/")
    if len(p_seg) != len(pat_seg):
        return False
    return all(fnmatch.fnmatchcase(a, b) for a, b in zip(p_seg, pat_seg))
