#!/usr/bin/env python3
"""Self-test for the sessionkit fixture baseline.

Run from the directory that contains the ``sessionkit`` package:

    python3 selftest.py

Exits 0 and prints "OK" when every behavior holds. On the BEFORE (baseline)
tree all assertions pass. On the AFTER (planted-bug) tree the assertions tied to
the three BUG-angle plants fail — that failure IS the reproduction for those
three plants (the four QUALITY-angle plants do not change observable behavior, by
design, so the selftest cannot and does not catch them).
"""

import sys

from sessionkit import (
    SessionStore,
    issue_token,
    load_config,
    verify_token,
)


def check(name, condition):
    if not condition:
        print("FAIL: {}".format(name))
        return False
    return True


def main():
    ok = True
    cfg = load_config()
    ttl = cfg["ttl"]
    skew = cfg["clock_skew"]

    # --- line-by-line plant repro: exact-boundary expiry ---------------------
    # A token issued at t=1000 with ttl expires at exp=1000+ttl. With skew it is
    # valid through exp+skew INCLUSIVE. The baseline accepts the exact boundary
    # second; the line-by-line plant flips <= to < and rejects it.
    tok = issue_token("alice", "user", ttl, now=1000)
    boundary = 1000 + ttl + skew
    ok &= check(
        "token valid at exact expiry-plus-skew boundary",
        verify_token(tok, skew, now=boundary) is True,
    )
    ok &= check(
        "token invalid one second past boundary",
        verify_token(tok, skew, now=boundary + 1) is False,
    )

    # --- removed-behavior plant repro: revoked tokens rejected ---------------
    # The baseline rejects a revoked token even while it is otherwise valid.
    # The removed-behavior plant deletes the revocation check, so a revoked but
    # unexpired token is wrongly accepted.
    revoked = issue_token("bob", "user", ttl, now=1000)
    revoked["revoked"] = True
    ok &= check(
        "revoked token is rejected",
        verify_token(revoked, skew, now=1000) is False,
    )

    # --- cross-file plant repro: writer/reader field agreement ---------------
    # issue_token writes the uid field; SessionStore.put reads the same field.
    # The cross-file plant renames the written field in tokens.py without
    # updating the reader in store.py, so put() raises KeyError.
    store = SessionStore(skew)
    live = issue_token("carol", "user", ttl, now=1000)
    store.put(live)
    ok &= check(
        "stored token reports live",
        store.is_live("carol", now=1000) is True,
    )
    ok &= check(
        "unknown user not live",
        store.is_live("nobody", now=1000) is False,
    )

    if ok:
        print("OK")
        return 0
    print("SELFTEST FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
