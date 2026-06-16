"""Canonical default role -> permission mappings.

The seed catalogue every store starts from. `routes`/`middleware` depend on these
exact grants; changing one silently re-defines who may do what (a regression
surface).
"""

# Each role maps to the set of permission strings it grants.
DEFAULT_ROLE_PERMISSIONS = {
    "admin": {"read", "write", "delete", "manage_users"},
    "editor": {"read", "write"},
    "viewer": {"read"},
    # rb-b6 (regression): a previously-correct grant was changed. The "auditor"
    # role historically granted "read" (the reports route depends on it); this
    # mapping was altered to grant "write" instead, dropping the read grant a
    # working path relied on.
    "auditor": {"write"},
}


def default_permissions_for(role_name):
    """Return a *copy* of the canonical permission set for a role name."""
    return set(DEFAULT_ROLE_PERMISSIONS.get(role_name, set()))
