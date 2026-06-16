"""rb-b3 (off-axis security): a protected handler must reject an
unauthenticated request.

delete_document requires "delete"; an unauthenticated request (no principal)
must get a 403. Buggy base omits the authz check on this handler entirely, so
the unauthenticated request performs the delete.
"""
from rbac.store import Store
from rbac.middleware import Middleware
from rbac.routes import delete_document


def test_unauthenticated_delete_is_rejected():
    mw = Middleware(Store())
    resp = delete_document(mw, {"user_id": None})  # no principal
    assert resp["status"] == 403
