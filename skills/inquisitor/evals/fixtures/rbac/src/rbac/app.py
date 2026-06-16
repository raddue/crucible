"""Application wiring.

Builds the store + middleware and exposes `dispatch(route, request)`. The app
maintains a route table mapping a route name to (handler, required_permission)
and enforces the required permission at the dispatch boundary *before* invoking
the handler — the app-level guard is the chokepoint for routes that delegate
their gating to it.
"""

from rbac.store import Store
from rbac.middleware import Middleware
from rbac import routes


DENIED = {"status": 403, "body": "forbidden"}


def admin_panel(mw, request):
    # Intentionally relies on the app-level dispatch guard for its
    # authorization (it requires "manage_users" via the route table); it does
    # no self-check.
    return {"status": 200, "body": "admin-panel"}


# route name -> (handler, required_permission_or_None)
ROUTE_TABLE = {
    "read_document": (routes.read_document, None),
    "write_document": (routes.write_document, None),
    "view_reports": (routes.view_reports, None),
    "delete_document": (routes.delete_document, None),
    "admin_panel": (admin_panel, "manage_users"),
}


class App:
    def __init__(self, store=None):
        self.store = store or Store()
        self.mw = Middleware(self.store)

    def dispatch(self, route, request):
        entry = ROUTE_TABLE.get(route)
        if entry is None:
            return {"status": 404, "body": "not found"}
        handler, required = entry
        if required is not None:
            allowed = self.mw.authorize(request, required)
            # rb-b5 (middleware result ignored -> denials don't take effect):
            # the decision is computed but the guard never returns DENIED on a
            # negative verdict, so the handler runs regardless of the verdict and
            # a denied principal still reaches the protected body.
            if allowed:
                return handler(self.mw, request)
            return handler(self.mw, request)
        return handler(self.mw, request)
