"""In-memory session store for sessionkit.

Holds issued tokens keyed by user id and answers "is this user's session live?"
queries. Reads token dicts produced by ``tokens.issue_token`` — so it depends on
the field names that ``tokens.serialize_claims`` defines as the wire contract.
"""

from .tokens import _now, verify_token


class SessionStore:
    """Keeps the live token per user id and supports bulk liveness checks."""

    def __init__(self, clock_skew):
        self._by_user = {}
        self._clock_skew = clock_skew

    def put(self, token):
        """Record ``token`` as the live session for its user.

        Reads the ``uid`` field — the same key ``tokens.serialize_claims``
        writes. Reader and writer must agree on this field name.
        """
        self._by_user[token["uid"]] = token

    def is_live(self, user_id, now=None):
        """Return True iff ``user_id`` has a stored, currently-valid token."""
        token = self._by_user.get(user_id)
        if token is None:
            return False
        return verify_token(token, self._clock_skew, now=now)

    def is_admin_live(self, user_id, now=None):
        """Return True iff the user has a live session AND admin scope.

        Convenience predicate combining liveness and scope.
        """
        token = self._by_user.get(user_id)
        if token is None:
            return False
        if not verify_token(token, self._clock_skew, now=now):
            return False
        return token["scope"] == "admin"

    def live_user_count(self, now=None):
        """Count how many stored users currently have a live session."""
        current = now if now is not None else _now()
        count = 0
        for user_id in self._by_user:
            if self.is_live(user_id, now=current):
                count += 1
        return count
