"""pg-b1: a cursor decoded to the wrong type breaks page chaining.

Drive the cursor seam end to end through the paginator: take page 1, then follow
its next_cursor to page 2 and assert page 2 begins at exactly one past the id the
cursor encodes. The boundary is read from the cursor (not the emitted slice), so
this isolates the encode/decode <-> store id-comparison seam from any unrelated
slice off-by-one. With a string-typed decode the boundary comparison breaks and
page 2 does not continue from the cursor.
"""
from paginate.store import Store
from paginate.paginator import Paginator
from paginate.cursor import decode_cursor


def test_following_cursor_continues_from_the_encoded_boundary():
    pg = Paginator(Store())
    page1 = pg.page(limit=3)
    assert page1["items"][0]["id"] == 1
    boundary = decode_cursor(page1["next_cursor"])
    page2 = pg.page(token=page1["next_cursor"], limit=3)
    # page 2 must begin at the record immediately after the encoded boundary
    assert page2["items"][0]["id"] == boundary + 1
