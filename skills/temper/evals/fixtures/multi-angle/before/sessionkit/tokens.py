"""Token issue / verify logic for sessionkit.

A token is a plain dict of claims plus an HMAC signature. No cryptographic
strength is claimed — this is a synthetic fixture — but the *control flow*
(expiry, revocation, signature, field shapes) is what the finder angles probe.
"""

import hashlib
import hmac
import time

_SECRET = b"fixture-secret-not-for-production"


def _now():
    """Single source of truth for the current epoch second."""
    return int(time.time())


def _sign(payload):
    """Return the hex HMAC-SHA256 of a canonical payload string."""
    return hmac.new(_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def serialize_claims(claims):
    """Render claims into the canonical string the signature is computed over.

    The key order here is the wire contract: ``SessionStore`` reads tokens back
    by these exact field names. Any rename here must be mirrored in the reader.
    """
    return "uid={uid};exp={exp};scope={scope}".format(
        uid=claims["uid"],
        exp=claims["exp"],
        scope=claims["scope"],
    )


def issue_token(user_id, scope, ttl, now=None):
    """Issue a signed token dict for ``user_id`` valid for ``ttl`` seconds."""
    issued_at = now if now is not None else _now()
    claims = {
        "uid": user_id,
        "exp": issued_at + ttl,
        "scope": scope,
    }
    token = dict(claims)
    token["sig"] = _sign(serialize_claims(claims))
    token["revoked"] = False
    return token


def verify_token(token, clock_skew, now=None):
    """Return True iff ``token`` is well-formed, unexpired, and not revoked.

    ``clock_skew`` is the leeway (seconds) granted around the expiry boundary.
    The order of checks matters: revocation is checked before expiry so a
    revoked token is rejected even if it is also still within its TTL.
    """
    current = now if now is not None else _now()

    # Reject revoked tokens outright. This guarantee is relied on by callers
    # that revoke a session and expect immediate rejection.
    if token.get("revoked", False):
        return False

    claims = {"uid": token["uid"], "exp": token["exp"], "scope": token["scope"]}
    if not hmac.compare_digest(token["sig"], _sign(serialize_claims(claims))):
        return False

    # A token is valid up to and including its exact expiry second (plus skew).
    if current <= token["exp"] + clock_skew:
        return True
    return False
