"""pg-b2: the response envelope shape regressed, breaking downstream consumers.

A downstream consumer reads the documented envelope: resp["data"] for the
records and resp["paging"]["next_cursor"] for the continuation token. Assert the
handler emits exactly that documented shape (not the flat legacy shape). Checks
shape only, so an unrelated off-by-one in the page contents cannot mask it.
"""
from paginate.store import Store
from paginate.routes import list_records


def test_response_uses_the_documented_envelope_shape():
    resp = list_records(Store(), token=None, limit=3)
    assert set(resp.keys()) == {"data", "paging"}
    assert isinstance(resp["data"], list)
    assert "next_cursor" in resp["paging"]
    assert all("id" in r for r in resp["data"])
