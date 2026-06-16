"""Opaque cursor encode/decode.

A cursor carries the id of the last record returned on the previous page. The
store advances a page by returning records whose id is strictly greater than
the decoded cursor value, comparing integer ids. The producer encodes an
integer id, so the consumer MUST hand back an integer — not a string — or the
store's id comparison breaks.
"""
import base64
import binascii


class InvalidCursor(ValueError):
    """Raised when a caller-supplied cursor token is malformed."""


def encode_cursor(last_id):
    """Encode the last-seen record id into an opaque cursor token."""
    raw = str(int(last_id)).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token):
    """Decode an opaque cursor token back into an integer record id boundary.

    A malformed token is rejected with `InvalidCursor`.
    """
    if token is None:
        return None
    try:
        text = base64.urlsafe_b64decode(token.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidCursor("cursor is not valid base64")
    if not text.lstrip("-").isdigit():
        raise InvalidCursor("cursor payload is not an integer")
    # BUG pg-b1: the producer encodes an integer id, but the consumer returns
    # the raw decoded STRING instead of int(text). The store then compares
    # integer record ids against a string boundary, so the comparison never
    # advances correctly and the next page does not continue where this ended.
    return text
