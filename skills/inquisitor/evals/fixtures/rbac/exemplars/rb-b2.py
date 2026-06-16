"""rb-b2: an assigned role must resolve so a permitted user is ALLOWED.

A user assigned the "editor" role (which grants "write") must be authorized to
write. Buggy base looks role ids up by the wrong type -> the role never resolves
-> the legitimately-permitted user is wrongly denied.
"""
from rbac.store import Store
from rbac.middleware import Middleware


def test_assigned_role_allows_permitted_user():
    store = Store()
    store.add_user("alice", role_names=["editor"])
    mw = Middleware(store)
    assert mw.authorize({"user_id": "alice"}, "write") is True
