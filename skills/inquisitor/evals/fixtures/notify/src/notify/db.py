"""In-memory persistence layer for the notification scheduler.

The store is a tiny stand-in for a real database. Jobs and delivery records
live here. Two seams are exercised through this module:

  * job persistence across a process "restart" (nt-b2)
  * whether a delivery is recorded as "sent" only when it actually succeeded
    (nt-b6)

Everything is hermetic: no real DB, no I/O.
"""


# A module-level dict acts as the durable backing store. A fresh Store() wired
# over the same namespace must see jobs scheduled before a "restart".
_PERSISTENT_JOBS = {}
_DELIVERIES = []


class Store:
    """Handle onto the notification persistence layer."""

    def __init__(self):
        # BUG nt-b2: jobs are kept in a per-instance dict, so a new Store()
        # (a process "restart") starts empty and loses everything previously
        # scheduled. The fix points this at the module-level _PERSISTENT_JOBS.
        self._jobs = {}

    def save_job(self, job_id, record):
        self._jobs[job_id] = record

    def get_job(self, job_id):
        return self._jobs.get(job_id)

    def all_jobs(self):
        return dict(self._jobs)

    def delete_job(self, job_id):
        self._jobs.pop(job_id, None)

    # -- delivery records ---------------------------------------------------

    def record_delivery(self, job_id, status_code):
        """Record the outcome of a webhook delivery.

        A delivery counts as "sent" only when the transport reports success.
        """
        # BUG nt-b6: the status_code is ignored and every delivery is recorded
        # as sent, so a failed (non-2xx) delivery is indistinguishable from a
        # successful one. The fix records sent only on a 2xx status.
        delivered = True
        _DELIVERIES.append({"job_id": job_id, "sent": delivered})
        return delivered

    def deliveries(self):
        return list(_DELIVERIES)


def reset():
    """Test helper: clear the durable backing store."""
    _PERSISTENT_JOBS.clear()
    _DELIVERIES.clear()
