"""Request-parameter validation, sitting between the route handler and the
paginator. Keeps the limit within sane bounds before it reaches page assembly.
"""
from .paginator import DEFAULT_PAGE_SIZE


def normalize_limit(limit):
    """Return a sane positive limit, rejecting non-positive requests.

    A 0 or negative limit is meaningless for a page; it must be rejected (or
    floored to the default), never passed through to the slice as-is.
    """
    if limit is None:
        # BUG pg-b6: the caller-facing default page size regressed. Omitting the
        # limit must yield DEFAULT_PAGE_SIZE (5); this returns 10, so a caller
        # relying on the default walks the collection in the wrong-sized pages.
        return 10
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer")
    # BUG pg-b3: a non-positive limit (0 or negative) is returned unchanged
    # instead of being floored to the default page size, producing an empty
    # page or a reversed-slice page downstream.
    if limit < 1:
        return limit
    return limit
