from notify.db import Store, reset
from notify.scheduler import Scheduler


def test_scheduled_at_is_iso_string():
    reset()
    store = Store()
    sched = Scheduler(store, lambda: 1_700_000_000)
    rec = sched.schedule("j1", 60)
    sa = rec["scheduled_at"]
    # The notifier consumes scheduled_at as an ISO-8601 timestamp string.
    assert isinstance(sa, str)
    assert sa[:10] == "2023-11-14"
