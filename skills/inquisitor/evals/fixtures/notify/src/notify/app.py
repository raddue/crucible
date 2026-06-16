"""Application wiring: assembles Store + Scheduler + Notifier + routing.

This is the composition root the exemplars drive end-to-end. It owns the
hermetic defaults: a fake clock and an in-memory webhook transport.
"""
from notify.db import Store
from notify.scheduler import Scheduler
from notify.notifier import Notifier
from notify import routes


def fixed_clock(epoch=1_700_000_000):
    """A deterministic clock factory (no real wall-clock)."""
    return lambda: epoch


class FakeTransport:
    """In-memory webhook transport. Records calls; returns a canned status."""

    def __init__(self, status=200):
        self.status = status
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        return self.status


class App:
    """Composition root wiring the notification subsystem together."""

    def __init__(self, store=None, clock=None, transport=None):
        self.store = store if store is not None else Store()
        self.clock = clock if clock is not None else fixed_clock()
        self.transport = transport if transport is not None else FakeTransport()
        self.scheduler = Scheduler(self.store, self.clock)
        self.notifier = Notifier(self.store)

    def schedule(self, job_id, delay, channel=None):
        rec = self.scheduler.schedule_tracked(job_id, delay)
        if channel is not None:
            rec["channel"] = channel
            self.store.save_job(job_id, rec)
        return rec

    def cancel(self, job_id):
        return self.scheduler.cancel(job_id)

    def deliver(self, job_id, url):
        """Send a job's webhook through routing, recording the outcome."""
        payload = self.notifier.render(job_id)
        status = routes.dispatch(url, payload, self.transport)
        return self.store.record_delivery(job_id, status)
