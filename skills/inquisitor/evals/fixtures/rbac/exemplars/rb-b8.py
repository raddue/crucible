"""rb-b8 (off-axis error-handling): a missing user must be safely DENIED.

A request whose principal the store has never registered must resolve to no
permissions and be denied every protected action. Buggy base's missing-user path
returns a wildcard set, so an unknown principal passes every check.
"""
from rbac.store import Store
from rbac.middleware import Middleware


def test_missing_user_is_denied():
    mw = Middleware(Store())  # empty store; "ghost" was never added
    assert mw.authorize({"user_id": "ghost"}, "read") is False
