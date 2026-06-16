"""Page assembly: glue between the cursor codec and the record store.

`Paginator.page` decodes the incoming cursor to a stable id boundary, asks the
store for the next slice, and assembles the response: the items plus a
`next_cursor` token that encodes the LAST returned record's id so the following
page continues from exactly where this one ended.
"""
from . import cursor as cursor_mod

DEFAULT_PAGE_SIZE = 5
MAX_PAGE_SIZE = 50


class Paginator:
    def __init__(self, store):
        self._store = store

    def page(self, token=None, limit=None):
        """Assemble one page from an opaque cursor token.

        Returns {"items": [...], "next_cursor": <token-or-None>}.
        """
        if limit is None:
            # BUG pg-b6: the documented default page size is DEFAULT_PAGE_SIZE
            # (5); this hardcodes 10, so a caller relying on the default walks
            # the collection in the wrong-sized pages.
            limit = 10
        boundary_id = cursor_mod.decode_cursor(token)
        return self.page_from_boundary(boundary_id, limit)

    def page_from_boundary(self, boundary_id, limit):
        """Assemble a page given an already-decoded id boundary (cursor-free)."""
        rows = self._store.records_after(boundary_id, limit)
        if not rows:
            return {"items": [], "next_cursor": None}
        # BUG pg-b5: off-by-one at the page boundary — the trailing record is
        # dropped from the emitted page (rows[:-1]) even though next_cursor
        # still advances past it, so that record is lost between pages.
        emitted = rows[:-1] if len(rows) > 1 else rows
        last = rows[-1]
        next_cursor = cursor_mod.encode_cursor(last["id"])
        return {"items": emitted, "next_cursor": next_cursor}
