"""In-memory user + role store.

Holds Role objects keyed by name, and users keyed by user id. Each user has a
list of assigned role *ids* (the integer the store handed out at registration).
"""

from rbac.roles import Role
from rbac.defaults import DEFAULT_ROLE_PERMISSIONS


class Store:
    def __init__(self):
        self._roles = {}            # role_id (int) -> Role
        self._role_ids = {}         # role_name (str) -> role_id (int)
        self._users = {}            # user_id (str) -> {"roles": [role_id, ...]}
        self._next_role_id = 1
        for name, perms in DEFAULT_ROLE_PERMISSIONS.items():
            self.define_role(name, perms)

    def define_role(self, name, permissions=None):
        rid = self._next_role_id
        self._next_role_id += 1
        self._roles[rid] = Role(name, permissions)
        self._role_ids[name] = rid
        return rid

    def add_user(self, user_id, role_names=()):
        rids = []
        for name in role_names:
            rid = self._role_ids.get(name)
            if rid is not None:
                rids.append(rid)
        self._users[user_id] = {"roles": rids}

    def role_id_for(self, name):
        return self._role_ids.get(name)

    def get_user(self, user_id):
        return self._users.get(user_id)

    def roles_for_user(self, user_id):
        """Resolve a user's assigned role ids to Role objects."""
        user = self._users.get(user_id)
        if user is None:
            return []
        resolved = []
        for rid in user["roles"]:
            # rb-b2 (type-mismatch lookup -> wrongful DENY): assigned ids are
            # ints (handed out by define_role), but here we look them up by the
            # str() form of the id, which never matches the int keys in
            # self._roles -> the assigned role resolves to nothing and a
            # legitimately-permitted user is denied.
            role = self._roles.get(str(rid))
            if role is not None:
                resolved.append(role)
        return resolved
