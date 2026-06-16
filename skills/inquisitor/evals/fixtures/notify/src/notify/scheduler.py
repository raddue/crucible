"""Job scheduler: turns a (job_id, delay) request into a stored job record.

Seams exercised here:

  * the timestamp it writes for the consumer (notifier) to read (nt-b1)
  * validation of the caller-supplied delay (nt-b3)
  * whether two wired schedulers share cancellation state (nt-b7)

A clock is injected so the module is hermetic (no real wall-clock).
"""
import datetime


def _iso_from_epoch(epoch_seconds):
    """Render an epoch-second value as a UTC ISO-8601 string."""
    return datetime.datetime.utcfromtimestamp(epoch_seconds).isoformat()


class Scheduler:
    """Schedules jobs into a shared Store, computing each job's fire time.

    `clock` is a zero-arg callable returning the current epoch seconds (int).
    """

    def __init__(self, store, clock):
        self._store = store
        self._clock = clock

    # -- seam nt-b1: the scheduled_at the notifier consumes -----------------

    def schedule(self, job_id, delay):
        now = self._clock()
        delay = self._validate_delay(delay)
        fire_at_epoch = now + delay
        # BUG nt-b1: scheduled_at is written as a raw epoch int, but the
        # notifier reads scheduled_at as an ISO-8601 timestamp string. The fix
        # stores the ISO rendering instead of the bare int.
        scheduled_at = fire_at_epoch
        record = {
            "job_id": job_id,
            "delay": delay,
            "scheduled_at": scheduled_at,
        }
        self._store.save_job(job_id, record)
        return record

    # -- seam nt-b3: delay validation (kept well below schedule's lines) ----

    def _validate_delay(self, delay):
        # BUG nt-b3: a None or negative delay is passed straight through, so a
        # job's effective delay can be negative (it would fire in the past).
        # The fix coerces None to 0 and clamps negatives up to 0.
        return delay

    # -- seam nt-b7: cancellation across wired instances --------------------

    def cancel(self, job_id):
        """Cancel a previously-scheduled job.

        A cancel issued on any scheduler wired to the same store must reach a
        job scheduled by any other such scheduler.
        """
        # BUG nt-b7: cancel consults a per-instance set of job_ids this exact
        # instance scheduled, so a cancel cannot reach a job another instance
        # scheduled into the shared store. The fix cancels through the store.
        if job_id in self._locally_scheduled():
            self._store.delete_job(job_id)
            return True
        return False

    def _locally_scheduled(self):
        if not hasattr(self, "_seen"):
            self._seen = set()
        return self._seen

    def schedule_tracked(self, job_id, delay):
        rec = self.schedule(job_id, delay)
        self._locally_scheduled().add(job_id)
        return rec
