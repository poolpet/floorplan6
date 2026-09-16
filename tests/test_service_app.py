import json
import urllib.request
import urllib.error
import pytest


@pytest.fixture
def server(monkeypatch):
    import service.app as app
    from service.results import ResultStore
    results = ResultStore()

    def fake_solve(req, progress=None, store=None):
        if progress:
            progress(1, 1)
        if store is not None and req.get("_job_id"):
            store.put(req["_job_id"], {"mode": "apartment", "boundary": {}, "plans": ["PLAN"]})
        return {"mode": req["mode"], "boundary": {}, "variants": []}

    monkeypatch.setattr(app, "solve_request", fake_solve)
    h = app.start_server(port=0, result_store=results)
    yield h
    h.stop()


def _done_job(server) -> str:
    """Job w stanie `done` z wariantem w ResultStore — punkt wyjścia dla /export."""
    from service.client import ServiceClient
    c = ServiceClient(server.url)
    jid = c.solve({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]],
                   "entry": [4, 0], "mtype": "M2"})
    c.wait(jid, timeout=5)
    return jid


def _post_export(server, body: dict):
    return urllib.request.Request(f"{server.url}/export", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")


def test_health(server):
    with urllib.request.urlopen(f"{server.url}/health", timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200 and body["status"] == "ok" and "version" in body


def test_solve_then_poll_job(server):
    from service.client import ServiceClient
    c = ServiceClient(server.url)
    jid = c.solve({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0], "mtype": "M2"})
    j = c.wait(jid, timeout=5)
    assert j["status"] == "done" and j["result"]["mode"] == "apartment"


def test_bad_json_is_400(server):
    r = urllib.request.Request(f"{server.url}/solve", data=b"{nie json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(r, timeout=5)
    assert ei.value.code == 400
    ei.value.close()


def test_unknown_job_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(f"{server.url}/jobs/xyz", timeout=5)
    assert ei.value.code == 404
    ei.value.close()


def test_export_without_archicad_is_503(server, monkeypatch):
    import service.app as app
    monkeypatch.setattr(app, "connect_to_ac",
                        lambda: (_ for _ in ()).throw(ConnectionError("brak AC")))
    r = _post_export(server, {"job_id": _done_job(server), "variant": 0})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(r, timeout=5)
    assert ei.value.code == 503
    ei.value.close()


def test_client_wait_raises_on_error(server, monkeypatch):
    import service.app as app
    from service.client import ServiceClient
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None, store=None: (_ for _ in ()).throw(ValueError("zły obrys")))
    c = ServiceClient(server.url)
    jid = c.solve({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0], "mtype": "M2"})
    with pytest.raises(RuntimeError, match="zły obrys"):
        c.wait(jid, timeout=5)


def test_unexpected_exception_is_500(server, monkeypatch):
    import service.app as app
    monkeypatch.setattr(app, "connect_to_ac",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    r = _post_export(server, {"job_id": _done_job(server), "variant": 0})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(r, timeout=5)
    assert ei.value.code == 500
    body = json.loads(ei.value.read())
    ei.value.close()
    assert body["error"] == "Błąd wewnętrzny serwisu."


@pytest.mark.parametrize("length", ["abc", "-5"])
def test_bad_content_length_is_400(server, length):
    r = urllib.request.Request(f"{server.url}/solve", data=b"{}", method="POST",
                               headers={"Content-Type": "application/json", "Content-Length": length})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(r, timeout=5)
    assert ei.value.code == 400
    body = json.loads(ei.value.read())
    ei.value.close()
    assert body["error"] == "Nagłówek Content-Length jest niepoprawny."


def test_health_ignores_query_string(server):
    with urllib.request.urlopen(f"{server.url}/health?x=1", timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200 and body["status"] == "ok"


def test_job_id_ignores_query_string(server):
    from service.client import ServiceClient
    c = ServiceClient(server.url)
    jid = c.solve({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0], "mtype": "M2"})
    c.wait(jid, timeout=5)
    with urllib.request.urlopen(f"{server.url}/jobs/{jid}?x=1", timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200 and body["id"] == jid
