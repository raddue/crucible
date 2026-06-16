"""Request authorization middleware.

`authorize(...)` is the single chokepoint: given the store, a request, and the
permission a route requires, it resolves the principal (honoring any requested
scope) and returns an allow/deny decision. It memoizes resolved permission sets
per user to avoid re-walking the store on every call.
"""

from rbac.lookup import resolve_permissions, principal_allows
from rbac.scopes import effective_permissions


class Middleware:
    def __init__(self, store):
        self.store = store
        self._perm_cache = {}   # user_id -> resolved permission set

    def _resolve(self, user_id):
        if user_id in self._perm_cache:
            return self._perm_cache[user_id]
        perms = resolve_permissions(self.store, user_id)
        self._perm_cache[user_id] = perms
        return perms

    def invalidate(self, user_id):
        """Drop a cached principal so the next check re-reads the store.

        Must be called whenever a user's roles/permissions change.
        """
        # rb-b4 (stale cached role after update -> revoked access still works):
        # invalidation should evict the user's cache entry so a revocation takes
        # effect on the next check. Instead this is a no-op, so a principal whose
        # permission was revoked keeps passing checks from the stale cache.
        return None

    def authorize(self, request, required_permission):
        """Return True iff the request's principal may perform the action."""
        user_id = request.get("user_id")
        if user_id is None:
            return False
        granted = self._resolve(user_id)
        effective = effective_permissions(granted, request.get("requested_scopes"))
        return principal_allows(effective, required_permission)
