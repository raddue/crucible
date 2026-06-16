"""rb-b1: a newly-created role must start with NO permissions (default-deny).

A fresh role with no explicit permissions granted must NOT grant a protected
action. Buggy base seeds new roles with a wildcard -> wrongful allow.
"""
from rbac.roles import Role


def test_new_role_denies_protected_action():
    fresh = Role("fresh")  # created with no explicit permissions
    assert fresh.has_permission("delete") is False
    assert fresh.has_permission("read") is False
