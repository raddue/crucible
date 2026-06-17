"""pg-b6: the caller-facing default page size regressed from the documented value.

When the caller omits the limit (relies on the default), the boundary the handler
advances by must be the documented DEFAULT_PAGE_SIZE-th record. Drive the PUBLIC
request path (list_records with no limit) and read next_cursor's encoded id via the
same codec the producer used. next_cursor keys on the last *fetched* id, so this is
independent of the off-by-one emit bug (which drops an emitted row, not the fetched
boundary). Envelope-shape-agnostic so the response-shape bug cannot mask it.
"""
import base64

from paginate.store import Store
from paginate.routes import list_records
from paginate.paginator import DEFAULT_PAGE_SIZE


def _decode_id(token):
    return int(base64.urlsafe_b64decode(token.encode("ascii")).decode("ascii"))


def _next_cursor(resp):
    return resp["paging"]["next_cursor"] if "paging" in resp else resp["next_cursor"]


def test_default_limit_advances_by_the_documented_default_size():
    resp = list_records(Store(), token=None, limit=None)  # no limit -> default
    assert DEFAULT_PAGE_SIZE == 5
    # the default page must end at the 5th record (id 5), not the 10th
    assert _decode_id(_next_cursor(resp)) == DEFAULT_PAGE_SIZE
