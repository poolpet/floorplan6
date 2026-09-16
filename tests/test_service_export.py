"""`POST /export` (z ResultStore), `/shutdown`, `/health.ac_port` — bez ArchiCADa."""
import json, threading, time, urllib.request, urllib.error
import pytest


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b"{}"); e.close(); return e.code, body


@pytest.fixture
def server(monkeypatch):
    import service.app as app
    from service.results import ResultStore
    store = ResultStore()
    def fake_solve(req, progress=None, store=None):
        if store is not None and req.get("_job_id"):
            store.put(req["_job_id"], {"mode": "apartment", "boundary": {}, "plans": ["PLAN0", "PLAN1"]})
        return {"mode": "apartment", "boundary": {}, "variants": [{"index": 0, "score": 0.9, "contract": {}}]}
    monkeypatch.setattr(app, "solve_request", fake_solve)
    h = app.start_server(port=0, result_store=store)
    yield h, store
    if h.is_running():
        h.stop()


def _solve_done(h):
    from service.client import ServiceClient
    c = ServiceClient(h.url)
    jid = c.solve({"mode": "apartment", "source": "polygon", "polygon": [[0,0],[8,0],[8,6],[0,6]], "entry": [4,0]})
    c.wait(jid, timeout=10)
    return c, jid


def test_export_calls_writer_with_selected_plan(server, monkeypatch):
    import service.app as app
    h, store = server
    seen = {}
    monkeypatch.setattr(app, "export_plan_to_archicad", lambda plan, tapir=None, **kw: seen.update(plan=plan, kw=kw) or {"zones": ["a"], "walls": [], "doors": [], "windows": [], "labels": []})
    monkeypatch.setattr(app, "connect_to_ac", lambda: "TAPIR")
    c, jid = _solve_done(h)
    out = c.export({"job_id": jid, "variant": 1, "storeys": ["parter"], "furniture": False})
    assert seen["plan"] == "PLAN1" and seen["kw"]["include_furniture"] is False
    assert out == {"zones": 1, "walls": 0, "doors": 0, "windows": 0, "labels": 0, "storeys": ["parter"]}


def test_export_404_unknown_job_or_variant(server):
    h, _ = server
    code, body = _post(f"{h.url}/export", {"job_id": "nope", "variant": 0})
    assert code == 404 and "job" in body["error"].lower()
    c, jid = _solve_done(h)
    code, body = _post(f"{h.url}/export", {"job_id": jid, "variant": 7})
    assert code == 404


def test_export_409_when_job_running(server, monkeypatch):
    import service.app as app
    h, _ = server
    gate = threading.Event()
    monkeypatch.setattr(app, "solve_request", lambda req, progress=None, store=None: gate.wait(5) or {"mode": "apartment", "boundary": {}, "variants": []})
    from service.client import ServiceClient
    jid = ServiceClient(h.url).solve({"mode": "apartment", "source": "polygon", "polygon": [[0,0],[8,0],[8,6],[0,6]], "entry": [4,0]})
    code, _ = _post(f"{h.url}/export", {"job_id": jid, "variant": 0})
    gate.set()
    assert code == 409


def test_export_503_when_ac_unreachable(server, monkeypatch):
    import service.app as app
    h, _ = server
    monkeypatch.setattr(app, "connect_to_ac", lambda: (_ for _ in ()).throw(ConnectionError("no AC")))
    c, jid = _solve_done(h)
    with pytest.raises(RuntimeError, match="Archicad"):
        c.export({"job_id": jid, "variant": 0})


def test_export_422_on_writer_value_error(server, monkeypatch):
    import service.app as app
    h, _ = server
    monkeypatch.setattr(app, "connect_to_ac", lambda: "TAPIR")
    monkeypatch.setattr(app, "export_plan_to_archicad", lambda *a, **k: (_ for _ in ()).throw(ValueError("No rooms with geometry to export.")))
    c, jid = _solve_done(h)
    code, body = _post(f"{h.url}/export", {"job_id": jid, "variant": 0})
    assert code == 422 and "No rooms" in body["error"]


def test_health_reports_ac_port(server, monkeypatch):
    h, _ = server
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    with urllib.request.urlopen(f"{h.url}/health", timeout=5) as r:
        body = json.loads(r.read())
    assert body["ac_port"] == 19724


def test_shutdown_stops_server(server):
    h, _ = server
    code, _ = _post(f"{h.url}/shutdown", {})
    assert code == 200
    for _ in range(50):
        if not h.is_running():
            break
        time.sleep(0.05)
    assert not h.is_running()
