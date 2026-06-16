"""pg-b8: a malformed cursor is swallowed and silently restarts at page 1.

The app entry point must surface a malformed cursor as a clean InvalidCursor
rejection, never silently return the first page (which a caller cannot
distinguish from a legitimate first page).
"""
import pytest

from paginate.app import App
from paginate.cursor import InvalidCursor


def test_malformed_cursor_is_rejected_not_silently_reset():
    app = App()
    with pytest.raises(InvalidCursor):
        app.list(token="%%%not-a-valid-cursor%%%")
