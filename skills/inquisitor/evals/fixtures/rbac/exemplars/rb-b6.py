"""rb-b6: the canonical "auditor" role must still grant "read".

A working path (the reports view) depends on the auditor role granting "read".
The regression changed that default mapping, dropping the read grant. This
exercises the defaults -> roles producer seam directly (independent of store
role-id resolution) so it isolates the regressed mapping.
"""
from rbac.defaults import default_permissions_for
from rbac.roles import Role


def test_auditor_default_grants_read():
    role = Role("auditor", default_permissions_for("auditor"))
    assert role.has_permission("read") is True
