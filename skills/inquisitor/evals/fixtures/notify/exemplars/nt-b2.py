from notify.db import Store, reset


def test_job_survives_restart():
    reset()
    # Schedule a job through one store handle...
    s1 = Store()
    s1.save_job("j-keep", {"job_id": "j-keep", "delay": 30})
    # ...then simulate a process restart: a brand-new Store handle must still
    # see the previously-scheduled job (it is durable, not in-process-only).
    s2 = Store()
    assert s2.get_job("j-keep") == {"job_id": "j-keep", "delay": 30}
