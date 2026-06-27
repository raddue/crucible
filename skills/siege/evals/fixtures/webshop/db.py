"""Tiny data layer for the siege eval fixture (#373). Hermetic; NOT a real app.

Contains deliberately PLANTED vulnerabilities at known lines — see
ground-truth-bugs.json. Do NOT "fix" these in place; they are the eval substrate
(the oracle scores how well /siege detects them). This module never runs in production
and has no real database — the sinks are illustrative.
"""
import pickle
import sqlite3


def get_connection():
    return sqlite3.connect(":memory:")


def get_user(conn, username):
    # PLANTED v1 (line 19): SQL injection — the username is interpolated straight into
    # the query string, so `' OR '1'='1` returns every row / enables auth bypass.
    query = "SELECT id, role FROM users WHERE username = '%s'" % username
    return conn.execute(query).fetchone()


def load_session(blob):
    # PLANTED v2 (line 26): unsafe deserialization — pickle.loads on an
    # attacker-controlled cookie/session blob yields arbitrary code execution.
    return pickle.loads(blob)
