"""Outbound webhook routing.

Seam exercised here: validation of a caller-supplied webhook URL before the
notifier dials it (nt-b5). The transport is a pluggable callable so the module
stays hermetic — it never makes a real HTTP call.
"""

# Only these schemes/hosts are permitted webhook targets.
_ALLOWED_SCHEMES = ("https",)
_ALLOWED_HOSTS = ("hooks.internal", "hooks.example.com")


def _parse(url):
    """Crude scheme/host split (stdlib urllib would do, kept inline + hermetic)."""
    scheme = url.split("://", 1)[0] if "://" in url else ""
    rest = url.split("://", 1)[1] if "://" in url else url
    host = rest.split("/", 1)[0]
    return scheme, host


def dispatch(url, payload, transport):
    """Send `payload` to `url` via `transport`, returning the transport result.

    `transport` is a callable (url, payload) -> status_code; the default in
    app.py is an in-memory fake. A caller-supplied URL MUST be validated against
    the allowlist before it is dialed.
    """
    # BUG nt-b5: the URL is dialed without any scheme/host validation, so a
    # disallowed (e.g. file:// or attacker-controlled host) URL is sent to.
    # The fix refuses anything not on the allowlist before calling transport.
    return transport(url, payload)


def is_allowed(url):
    """Return True iff `url` is a permitted webhook target."""
    scheme, host = _parse(url)
    return scheme in _ALLOWED_SCHEMES and host in _ALLOWED_HOSTS
