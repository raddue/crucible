"""sessionkit — a tiny session/token utility (synthetic fixture, pre-change baseline).

A deliberately small, self-contained, dependency-free Python package used as the
multi-angle detection fixture for temper / delve-engine. The BASELINE (this
``before/`` tree) is correct and passes ``selftest.py``. The planted-bug change
lives in ``after/`` (and as a unified diff in ``planted.diff``); it introduces
exactly seven defects, one per finder angle.
"""

from .tokens import issue_token, verify_token, serialize_claims
from .store import SessionStore
from .config import load_config, DEFAULT_TTL

__all__ = [
    "issue_token",
    "verify_token",
    "serialize_claims",
    "SessionStore",
    "load_config",
    "DEFAULT_TTL",
]
