"""Application wiring: build a store with the canonical dataset and expose a
single `list` entry point bound to it. The entry point is also where a
malformed cursor surfaces to the caller as a clean rejection.
"""
from .store import Store
from .routes import list_records
from .cursor import InvalidCursor


class App:
    def __init__(self, store=None):
        self.store = store if store is not None else Store()

    def list(self, token=None, limit=None):
        try:
            return list_records(self.store, token=token, limit=limit)
        except InvalidCursor:
            # BUG pg-b8: a malformed cursor is swallowed and the handler
            # silently restarts at page 1 instead of surfacing the rejection.
            # The caller can never tell a bad cursor from a real first page.
            return list_records(self.store, token=None, limit=limit)

    def records(self, token=None, limit=None):
        """Return one page's records via the downstream envelope consumer.

        Routes through `client.page_records`, which reads the published envelope
        (`resp["data"]` / `resp["paging"]["next_cursor"]`), so this exercises the
        documented envelope contract across the producer<->consumer seam.
        """
        from .client import page_records
        items, _next_cursor = page_records(self, token=token, limit=limit)
        return items
