"""rb-b5: a denied dispatch must NOT execute the handler.

The admin_panel route requires "manage_users" and delegates its gating to the
app-level dispatch guard. A viewer (who lacks "manage_users") dispatching it must
get a 403. Buggy base computes the verdict but invokes the handler regardless, so
the denied principal still reaches the protected body.
"""
from rbac.app import App


def test_denied_dispatch_does_not_execute_handler():
    app = App()
    app.store.add_user("dave", role_names=["viewer"])  # no manage_users
    resp = app.dispatch("admin_panel", {"user_id": "dave"})
    assert resp["status"] == 403
