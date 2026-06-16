from notify.db import Store, reset
from notify.scheduler import Scheduler


def test_cancel_reaches_job_from_other_instance():
    reset()
    store = Store()
    # Two schedulers wired to the SAME store.
    sched_a = Scheduler(store, lambda: 1_700_000_000)
    sched_b = Scheduler(store, lambda: 1_700_000_000)
    sched_a.schedule_tracked("j-x", 10)
    # A cancel issued on the other instance must reach the job.
    ok = sched_b.cancel("j-x")
    assert ok is True
    assert store.get_job("j-x") is None
