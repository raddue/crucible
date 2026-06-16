from notify.db import Store, reset
from notify.scheduler import Scheduler


def test_negative_delay_is_clamped():
    reset()
    store = Store()
    sched = Scheduler(store, lambda: 1_700_000_000)
    # A caller-supplied negative delay would make the job fire in the past; the
    # stored, validated delay must never be negative.
    rec = sched.schedule("j-neg", -500)
    assert rec["delay"] == 0
