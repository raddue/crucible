"""Role / permission model.

A Role is a named bag of permission strings. New roles are created empty and
permissions are granted explicitly (default-deny).
"""


class Role:
    def __init__(self, name, permissions=None):
        self.name = name
        # rb-b1 (default lockout inverted): a freshly-created role with no
        # explicit permission set should start EMPTY (default-deny). Instead it
        # is seeded with a wildcard "*" that `has_permission` treats as
        # "grants everything", so brand-new roles wrongly allow protected
        # actions until someone narrows them. Manifests only when a Role is
        # built with permissions=None and then checked at runtime.
        if permissions is None:
            self.permissions = {"*"}
        else:
            self.permissions = set(permissions)

    def grant(self, permission):
        self.permissions.discard("*")
        self.permissions.add(permission)

    def revoke(self, permission):
        self.permissions.discard(permission)

    def has_permission(self, permission):
        if "*" in self.permissions:
            return True
        return permission in self.permissions

    def __repr__(self):
        return f"Role({self.name!r}, {sorted(self.permissions)!r})"
