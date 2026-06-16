"""pg-b5: an off-by-one at the page boundary drops the trailing record.

Cursor-free store<->paginator seam: a single page request for N records must
emit exactly those N records, including the boundary record (none dropped).
"""
from paginate.store import Store
from paginate.paginator import Paginator


def test_page_emits_every_requested_record_including_the_boundary():
    pg = Paginator(Store())
    page = pg.page_from_boundary(0, 4)
    ids = [r["id"] for r in page["items"]]
    # all four requested records present; the 4th (boundary) is not dropped
    assert ids == [1, 2, 3, 4]
