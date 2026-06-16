"""Effective-scope computation.

A request may *ask* for an elevated scope (e.g. an admin tool requesting the
"manage_users" scope). The effective permission set the middleware enforces must
be the INTERSECTION of what the principal actually has and what it requested —
a request can only ever narrow, never widen, the principal's granted set.
"""


def effective_permissions(granted, requested=None):
    """Compute the permissions a request actually operates under.

    `granted` is the principal's real permission set (from the store).
    `requested` is the optional client-supplied scope list. The result must
    never exceed `granted`.
    """
    if requested is None:
        return set(granted)
    if "*" in granted:
        return set(requested)
    # rb-b7 (trusting client-supplied scope -> privilege escalation): the
    # effective set should be granted ∩ requested (a request can only narrow).
    # Instead it UNIONs the client-supplied scopes onto the granted set, so a
    # caller can self-elevate by simply asking for a permission it was never
    # granted.
    return set(granted) | set(requested)
