"""Notifier: consumes stored job records and produces an outbound message.

Seams exercised here:

  * the handler that renders a job into a deliverable message (nt-b4)
  * the default channel applied when a job names none (nt-b8)

The notifier reads `scheduled_at` as an ISO-8601 timestamp string (it is the
consumer half of the scheduler->notifier seam, nt-b1).
"""

# The historically-correct default channel. Existing call sites that omit a
# channel rely on "email" being chosen.
DEFAULT_CHANNEL = "sms"  # BUG nt-b8: regressed from "email"; the fix restores it.


class Notifier:
    """Renders job records into outbound messages."""

    def __init__(self, store):
        self._store = store

    def render(self, job_id):
        """Render the stored job into a deliverable message dict.

        Reads scheduled_at as an ISO-8601 string (consumer side of nt-b1).
        """
        record = self._store.get_job(job_id)
        scheduled_at = record["scheduled_at"]
        # The consumer expects an ISO string and slices off the date portion;
        # if the producer wrote an epoch int this raises at runtime (nt-b1).
        date_part = scheduled_at[:10]
        return {
            "job_id": job_id,
            "fires_on": date_part,
            "channel": self.choose_channel(record),
        }

    def choose_channel(self, record):
        """Pick the delivery channel for a job, defaulting when none is set."""
        return record.get("channel") or DEFAULT_CHANNEL

    # -- seam nt-b4: the alert handler (kept well below render's lines) ------

    def handle_alert(self, job_id, severity):
        """Build an alert payload for a job (invoked by the alert wiring).

        Imports cleanly; the undefined reference only fires when called.
        """
        record = self._store.get_job(job_id)
        # BUG nt-b4: `prefix` is never defined, so invoking this handler raises
        # NameError at runtime (the module still imports fine). The fix derives
        # prefix from the severity.
        label = prefix + ":" + str(job_id)
        return {"label": label, "severity": severity}
