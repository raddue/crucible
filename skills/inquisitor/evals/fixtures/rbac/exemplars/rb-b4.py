"""rb-b4: a revoked permission must take effect after cache invalidation.

The middleware has a warm cache entry for a principal; the underlying grant is
then revoked and the cache is invalidated. The next check must re-read the store
and DENY. Buggy base's invalidate() is a no-op, so the stale cached permission
still allows the revoked action.

The cache is primed directly (not via a store-backed authorize) so this exemplar
isolates the invalidation seam and does not depend on role-resolution behavior.
"""
from rbac.store import Store
from rbac.middleware import Middleware


def test_revoked_access_denied_after_invalidate():
    store = Store()
    store.add_user("carol", role_names=["editor"])
    mw = Middleware(store)

    # Warm the cache directly to isolate the invalidation seam.
    mw._perm_cache["carol"] = {"read", "write"}
    assert mw.authorize({"user_id": "carol"}, "write") is True   # served from cache

    editor = store._roles[store.role_id_for("editor")]
    editor.revoke("write")
    mw.invalidate("carol")

    # After invalidation the next check must re-resolve and deny.
    assert mw.authorize({"user_id": "carol"}, "write") is False
