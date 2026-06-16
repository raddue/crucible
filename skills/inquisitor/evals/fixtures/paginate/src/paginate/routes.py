"""The list endpoint — the HTTP-ish boundary in front of the paginator.

`list_records` is the request handler. It normalizes the caller-supplied
`limit`, caps it to a server maximum, drives the paginator, and returns the
documented response envelope:

    {"data": [...records...], "paging": {"next_cursor": <token-or-None>}}

Downstream consumers read `resp["data"]` and `resp["paging"]["next_cursor"]`.
"""
from .paginator import Paginator, MAX_PAGE_SIZE
from .validate import normalize_limit


def _cap_limit(limit):
    """Cap an already-normalized limit to the server maximum page size."""
    # BUG pg-b7: no upper bound is enforced — a caller can request an unbounded
    # page (resource exhaustion). The limit must be capped at MAX_PAGE_SIZE.
    return limit


def list_records(store, token=None, limit=None):
    """Handle a list request and return the documented response envelope."""
    eff_limit = _cap_limit(normalize_limit(limit))
    paginator = Paginator(store)
    page = paginator.page(token=token, limit=eff_limit)
    items = page["items"]
    next_cursor = page["next_cursor"]
    # BUG pg-b2: the response is emitted in a flat legacy shape
    # ({"items", "next_cursor"}) instead of the documented envelope
    # ({"data", "paging": {"next_cursor"}}), breaking downstream consumers
    # that read resp["data"] / resp["paging"]["next_cursor"].
    return {"items": items, "next_cursor": next_cursor}
