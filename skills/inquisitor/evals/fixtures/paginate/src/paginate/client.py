"""Downstream client for the list endpoint.

Reads the published response envelope: the records live under ``resp["data"]``
and the continuation token under ``resp["paging"]["next_cursor"]``. A consumer
that drives pagination relies on exactly this envelope shape.
"""


def page_records(app, token=None, limit=None):
    """Call the list endpoint and return ``(records, next_cursor)`` read from the
    response envelope (``resp["data"]`` / ``resp["paging"]["next_cursor"]``)."""
    resp = app.list(token=token, limit=limit)
    return resp["data"], resp["paging"]["next_cursor"]
