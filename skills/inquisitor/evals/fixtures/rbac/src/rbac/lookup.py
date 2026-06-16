"""Principal resolution.

Turns a request's user id into a resolved principal (its set of permissions),
consulting the store. This is the layer that decides what an *unknown* user
gets.
"""


def resolve_permissions(store, user_id):
    """Return the union of all permissions granted to user_id.

    A user the store has never seen is unknown and must resolve to NO
    permissions (default-deny) — the caller will then deny every protected
    action.
    """
    user = store.get_user(user_id)
    if user is None:
        # rb-b8 (missing-user error path mis-handled -> wrongful ALLOW): an
        # unknown user should resolve to an empty permission set. Instead the
        # missing case returns a wildcard set treated as "all permissions", so a
        # principal the store never registered passes every check.
        return {"*"}
    perms = set()
    for role in store.roles_for_user(user_id):
        if "*" in role.permissions:
            return {"*"}
        perms |= role.permissions
    return perms


def principal_allows(perms, permission):
    """True if a resolved permission set grants `permission`."""
    return "*" in perms or permission in perms
