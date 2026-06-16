from notify.db import Store, reset
from notify.notifier import Notifier


def test_default_channel_is_email():
    reset()
    store = Store()
    notifier = Notifier(store)
    # A job that names no channel falls back to the historical default.
    rec = {"job_id": "j-d"}
    assert notifier.choose_channel(rec) == "email"
