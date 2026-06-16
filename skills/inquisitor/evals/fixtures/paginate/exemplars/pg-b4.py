"""pg-b4: paging on a positional offset (not the stable id) skips a record when
the dataset shrinks between page requests.

Use the cursor-free store<->paginator seam (page_from_boundary with an explicit
id boundary) so this depends only on the store's paging key, not on the cursor
codec. Take page 1, delete an earlier record, then fetch the next page by the
last-seen id: the next page must *start* with the very next id, no skip.
"""
from paginate.store import Store
from paginate.paginator import Paginator


def test_no_record_skipped_when_earlier_record_deleted_between_pages():
    store = Store()
    pg = Paginator(store)
    page1 = pg.page_from_boundary(0, 3)
    assert [r["id"] for r in page1["items"]][:1] == [1]
    last_id = page1["items"][-1]["id"]  # 3
    store.delete(1)  # an earlier record disappears between requests
    page2 = pg.page_from_boundary(last_id, 3)
    # must continue from id 3 with no skip: next page starts at 4 (not 5)
    assert page2["items"][0]["id"] == last_id + 1
