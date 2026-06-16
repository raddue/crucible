"""rb-b7 (off-axis security): a client-supplied scope must not self-elevate.

A viewer (granted only "read") sends a request requesting the "delete" scope.
The effective permission set must never exceed what the principal was granted, so
the delete must be DENIED. Buggy base unions the requested scopes onto the
granted set, letting the caller self-elevate.
"""
from rbac.store import Store
from rbac.middleware import Middleware


def test_client_cannot_self_elevate_via_requested_scope():
    store = Store()
    store.add_user("erin", role_names=["viewer"])  # granted only "read"
    mw = Middleware(store)
    request = {"user_id": "erin", "requested_scopes": ["delete"]}
    assert mw.authorize(request, "delete") is False
