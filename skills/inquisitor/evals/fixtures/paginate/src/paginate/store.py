"""In-memory record store with a deterministic, fixed dataset.

Records are dicts {"id": int, "name": str} kept sorted by id. The id is the
*stable key* a cursor pages on: `records_after(boundary_id, limit)` returns the
next `limit` records whose id is strictly greater than `boundary_id`. Paging on
the stable id (not a positional offset) is what keeps pages stable when records
are inserted or removed between requests.
"""


def seed_records():
    """Return the canonical fixed dataset: ids 1..20, deterministic."""
    return [{"id": i, "name": "rec-{:02d}".format(i)} for i in range(1, 21)]


class Store:
    def __init__(self, records=None):
        # sorted by id; the stable paging key
        self._records = sorted(
            (dict(r) for r in (records if records is not None else seed_records())),
            key=lambda r: r["id"],
        )

    def __len__(self):
        return len(self._records)

    def delete(self, rec_id):
        """Remove a record by id (mutates the store between page requests)."""
        self._records = [r for r in self._records if r["id"] != rec_id]

    def insert(self, rec_id, name):
        """Insert a record, keeping the list sorted by id."""
        self._records.append({"id": rec_id, "name": name})
        self._records.sort(key=lambda r: r["id"])

    def records_after(self, boundary_id, limit):
        """Return up to `limit` records with id strictly greater than boundary.

        Paging on the stable id keeps already-returned records from reappearing
        and not-yet-returned records from being skipped when the dataset
        mutates between page requests.
        """
        if boundary_id is None:
            boundary_id = 0
        # BUG pg-b4: pages by POSITION instead of by the stable id. It treats
        # the boundary value as a slice offset into the (contiguous) list. When
        # an earlier record is deleted between page requests, every later
        # record shifts down one position, so this offset overshoots and the
        # first record of the next page is skipped.
        offset = boundary_id  # treat the boundary value itself as the offset
        return [dict(r) for r in self._records[offset:offset + limit]]
