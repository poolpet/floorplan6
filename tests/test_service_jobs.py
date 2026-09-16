import threading
import time


def _wait(store, jid, status, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = store.get(jid)
        if j and j["status"] == status:
            return j
        time.sleep(0.01)
    raise AssertionError(f"job {jid} nie osiągnął {status}: {store.get(jid)}")


def test_submit_runs_and_stores_result():
    from service.jobs import JobStore
    store = JobStore()
    jid = store.submit(lambda progress=None: {"ok": 1})
    j = _wait(store, jid, "done")
    assert j["result"] == {"ok": 1} and j["error"] is None


def test_progress_is_visible_while_running():
    from service.jobs import JobStore
    gate = threading.Event()

    def slow(progress=None):
        progress(1, 3)
        gate.wait(5)
        return {"done": True}

    store = JobStore()
    jid = store.submit(slow)
    t0 = time.time()
    while store.get(jid)["progress"] != {"current": 1, "total": 3} and time.time() - t0 < 5:
        time.sleep(0.01)
    assert store.get(jid)["status"] == "running"
    assert store.get(jid)["progress"] == {"current": 1, "total": 3}
    gate.set()
    _wait(store, jid, "done")


def test_exception_becomes_error_status():
    from service.jobs import JobStore
    store = JobStore()

    def boom(progress=None):
        raise ValueError("zły obrys")

    jid = store.submit(boom)
    j = _wait(store, jid, "error")
    # `error` idzie wprost do palety: angielski, przepuszczony przez service.errors.
    assert j["error"].startswith("Input data: zły obrys") and j["result"] is None
    assert "ValueError" in j["error_detail"] and "zły obrys" in j["error_detail"]


def test_unknown_job_is_none():
    from service.jobs import JobStore
    assert JobStore().get("nope") is None
