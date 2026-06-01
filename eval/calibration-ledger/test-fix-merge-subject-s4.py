#!/usr/bin/env python3
"""S-4 regression: _is_fix_merge_subject anchors on a branch boundary.

True for fix/* and hotfix/* branch refs; False for prefix/, affix/, suffix/
where the token is mid-word. Pure — no git.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def test_subject_matching():
    from scripts.reconcile_ledger import _is_fix_merge_subject
    truthy = [
        "Merge branch 'fix/auth'",
        "Merge pull request #3 from o/hotfix/x",
        "fix/at-start",                       # start-of-string
        'Merge "fix/quoted"',                 # after a quote
        "Merge branch 'HOTFIX/Upper'",        # case-insensitive
    ]
    falsy = [
        "Merge ... from o/prefix/thing",      # 'e' before fix
        ".../feature/affix/x",                # 'f' before fix
        "Merge branch 'suffix/y'",            # 's' before fix
        "Merge branch 'feature/auth'",        # no fix at all
        "",                                   # empty
    ]
    for s in truthy:
        _check(f"S-4.T {s!r} -> True", _is_fix_merge_subject(s) is True,
               f"got {_is_fix_merge_subject(s)}")
    for s in falsy:
        _check(f"S-4.F {s!r} -> False", _is_fix_merge_subject(s) is False,
               f"got {_is_fix_merge_subject(s)}")


def main():
    test_subject_matching()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
