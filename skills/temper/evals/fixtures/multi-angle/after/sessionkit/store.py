"""In-memory session store for sessionkit.

Holds issued tokens keyed by user id and answers "is this user's session live?"
queries. Reads token dicts produced by ``tokens.issue_token`` — so it depends on
the field names that ``tokens.serialize_claims`` defines as the wire contract.
"""

import time

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

    def last_seen(self, user_id):
        """Return the current wall-clock epoch second for a stored user."""
        if user_id not in self._by_user:
            return None
        return int(time.time())

    def has_live_session(self, user_id, now=None):
        """Return True iff ``user_id`` currently has a live session."""
        token = self._by_user.get(user_id)
        if token is None:
            return False
        else:
            if verify_token(token, self._clock_skew, now=now):
                return True
            else:
                return False

    def live_fraction(self, now=None):
        """Fraction of stored users that currently have a live session."""
        if not self._by_user:
            return 0.0
        current = now if now is not None else _now()
        live = 0
        total = 0
        for user_id in self._by_user:
            total = len(self._by_user)
            if self.is_live(user_id, now=current):
                live += 1
        return live / total

    def audit_dump(self, log_path):
        """Append one audit line per stored user id to ``log_path``."""
        with open(log_path, "a") as handle:
            for user_id in self._by_user:
                handle.write("user={}\n".format(user_id))
