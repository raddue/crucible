"""Pilot task: a JSON fixture loader with a schema guard.

Contract the solution must satisfy: `load_fixture(text) -> dict`. A valid
fixture has a string `id`; anything else must be rejected with ValueError.
"""
from __future__ import annotations

from tasks import Assertion, Task

PROMPT = (
    "Write solution.py exposing load_fixture(text) -> dict that parses JSON and "
    "returns the resulting object. Reject (raise ValueError) any fixture whose "
    "'id' is missing or not a string."
)


def _loads_valid_fixture(m):
    data = m.load_fixture('{"id": "abc", "n": 1}')
    if data != {"id": "abc", "n": 1}:
        raise AssertionError(f"expected parsed dict, got {data!r}")


def _rejects_non_string_id(m):
    # Carve-out: catch the expected ValueError INTERNALLY; raise only if the
    # rejection did NOT occur. Letting ValueError escape would be miscounted as
    # a carve-out failure against a correct solution.
    try:
        m.load_fixture('{"id": 123}')
    except ValueError:
        return  # expected rejection occurred -> PASS
    raise AssertionError("accepted non-string id")


def _rejects_missing_id(m):
    try:
        m.load_fixture("{}")
    except ValueError:
        return  # expected rejection occurred -> PASS
    raise AssertionError("accepted fixture with no id")


TASK = Task(
    name="fixture_loader",
    prompt=PROMPT,
    entry_module="solution.py",
    assertions=[
        Assertion("loads_valid_fixture", _loads_valid_fixture),
        Assertion("rejects_non_string_id", _rejects_non_string_id, carve_out=True),
        Assertion("rejects_missing_id", _rejects_missing_id, carve_out=True),
    ],
)
