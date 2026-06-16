"""pg-b3: a non-positive limit is passed through instead of being floored.

Through the route handler, a limit of 0 must yield a sane non-empty page (the
default), never an empty or reversed-slice page. Reads the page shape-agnostically
so an unrelated envelope-shape change does not mask this defect.
"""
from paginate.store import Store
from paginate.routes import list_records


def _items(resp):
    return resp["data"] if "data" in resp else resp["items"]


def test_zero_limit_is_floored_to_a_sane_page_not_empty():
    resp = list_records(Store(), token=None, limit=0)
    items = _items(resp)
    # floored to a sane page: non-empty and starting at the first record
    assert len(items) >= 1
    assert items[0]["id"] == 1
