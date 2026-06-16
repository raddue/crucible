"""Protected request handlers.

Each handler is `handler(mw, request) -> dict`. Every handler must consult the
middleware for the permission it requires before doing any work, and return a
403 envelope when denied.
"""

DENIED = {"status": 403, "body": "forbidden"}


def _ok(body):
    return {"status": 200, "body": body}


def read_document(mw, request):
    if not mw.authorize(request, "read"):
        return DENIED
    return _ok("document-contents")


def write_document(mw, request):
    if not mw.authorize(request, "write"):
        return DENIED
    return _ok("written")


def view_reports(mw, request):
    if not mw.authorize(request, "read"):
        return DENIED
    return _ok("reports")


def delete_document(mw, request):
    # rb-b3 (wiring gap / missing authz check -> unauthenticated reaches the
    # handler): every other handler gates on mw.authorize(...) before acting.
    # This one was wired up without its check, so any request — including one
    # with no principal — performs the delete.
    return _ok("deleted")
