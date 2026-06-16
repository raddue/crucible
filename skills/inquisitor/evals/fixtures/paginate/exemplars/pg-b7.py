"""pg-b7: no upper bound on limit lets a caller request an unbounded page.

Through the route handler, an absurdly large limit must be capped at the server
maximum. Reads the page shape-agnostically and asserts the returned count never
exceeds the cap (independent of any off-by-one in the emitted slice).
"""
from paginate.store import Store
from paginate.routes import list_records
from paginate.paginator import MAX_PAGE_SIZE


def _items(resp):
    return resp["data"] if "data" in resp else resp["items"]


def test_oversized_limit_is_capped_at_the_server_maximum():
    # dataset deliberately larger than the cap so an uncapped limit would
    # return far more than MAX_PAGE_SIZE records.
    big = [{"id": i, "name": "r{}".format(i)} for i in range(1, 121)]
    resp = list_records(Store(big), token=None, limit=10_000)
    items = _items(resp)
    assert len(items) <= MAX_PAGE_SIZE  # capped at 50, never 120 / 10000
