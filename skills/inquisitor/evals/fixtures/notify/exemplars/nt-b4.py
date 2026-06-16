from notify.db import Store, reset
from notify.notifier import Notifier


def test_alert_handler_builds_label():
    reset()
    store = Store()
    store.save_job("j-alert", {"job_id": "j-alert"})
    notifier = Notifier(store)
    # Invoking the alert handler must produce a severity-prefixed label, not
    # raise at runtime.
    out = notifier.handle_alert("j-alert", "warn")
    assert out["label"] == "WARN:j-alert"
    assert out["severity"] == "warn"
