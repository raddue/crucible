from notify.db import Store, reset


def test_failed_delivery_not_recorded_as_sent():
    reset()
    store = Store()
    # A non-2xx transport status means the delivery failed; it must NOT be
    # recorded as sent.
    store.record_delivery("j-fail", 500)
    rows = store.deliveries()
    assert len(rows) == 1
    assert rows[0]["job_id"] == "j-fail"
    assert rows[0]["sent"] is False
