"""pg-b6: the default page size regressed from the documented value.

When the caller relies on the default (limit omitted), the boundary advanced by
the page must be the documented DEFAULT_PAGE_SIZE-th record. Read next_cursor's
encoded id via the same codec the producer used (cursor-stable), and compare to
the documented default size. Independent of the off-by-one emit bug because
next_cursor keys on the last fetched id, not the emitted slice.
"""
import base64

from paginate.store import Store
from paginate.paginator import Paginator, DEFAULT_PAGE_SIZE


def _decode_id(token):
    return int(base64.urlsafe_b64decode(token.encode("ascii")).decode("ascii"))


def test_default_page_advances_by_the_documented_default_size():
    pg = Paginator(Store())
    page = pg.page()  # no limit -> documented default
    assert DEFAULT_PAGE_SIZE == 5
    # the cursor must point at the 5th record (id 5), not the 10th
    assert _decode_id(page["next_cursor"]) == 5
