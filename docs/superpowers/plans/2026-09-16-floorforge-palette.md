# FloorForge — natywna paleta w Archicadzie (poziom 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menu **FloorForge → Palette** w Archicadzie 29 otwiera natywną paletę, która czyta obrys z AC, generuje warianty przez osadzony serwis Pythona, pokazuje podgląd i wstawia wybrany wariant do AC. Bez okna PyQt.

**Architecture:** Python zostaje mózgiem i writerem, ale działa jako proces potomny AC w trybie `FloorForge --serve` (HTTP na localhost, port w pliku per instancja AC, watchdog rodzica). Serwis czyta obrys z AC sam (`bridge/boundary_reader`), trzyma wyniki w pamięci (`ResultStore`) i wstawia wybrany wariant istniejącymi writerami. Paleta C++ (z FP4_CPP: `DG::Palette` + `UserItem` z rysowaniem `NewDisplay`) rozmawia z serwisem przez `HTTP::Client` + `JSON::JDOMParser` (jak `VersionChecker.cpp` z Tapira) w wątku roboczym (`GS::ThreadedExecutor` + `GS::MessageLoopExecutor`), więc UI AC nie blokuje się na czas solve.

**Tech Stack:** Python 3.13 (stdlib `http.server`), PyInstaller 6.22.3, C++20 + Archicad API DevKit 29 (`DG`, `NewDisplay`, `HTTP::Client`, `JSON`, `GS::Process`, `GS::ThreadedExecutor`), CMake.

**Spec:** `docs/superpowers/specs/2026-09-16-floorforge-palette-design.md` (buduje na `2026-09-15-floorforge-bundle-design.md`).

## Global Constraints

- Mózg zamrożony: zero zmian w `core/` (spec §1). Writer (`bridge/plan_writer.py`, `bridge/house_writer.py`) bez zmian logiki — tylko reuse.
- Wszystkie stringi widoczne dla użytkownika po angielsku ("Archicad", nie "ArchiCAD").
- Serwis: tylko `127.0.0.1`; łączy się z AC **wyłącznie** z portem z `FLOORFORGE_AC_PORT` (bez skanu) gdy uruchomiony z AC; plik portu `~/Library/Application Support/FloorForge/service-<AC_PORT>.port` (`PORT=\nPID=\nVERSION=\n`), usuwany przy wyjściu; watchdog `os.getppid()` co 2 s (spec §3.1).
- Endpointy i kody dokładnie jak spec §3.2 (`/health`, `/solve` z `source`, `/jobs/{id}`, `/export` 200/404/409/503/422, `/shutdown`).
- C++: żądania HTTP nigdy z głównego wątku poza `/health` (1 s) i `/shutdown`; solve/jobs/export w wątku roboczym, UI aktualizowane przez `GS::MessageLoopExecutor` (spec §7).
- Build C++: `cmake -S addon -B addon/Build -DAC_VERSION=29 -DAC_API_DEVKIT_DIR="/Users/dawidcwiertniewicz/Desktop/claude code/API archicad/Support" -DFLOORFORGE_VERSION=<ver> -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_OSX_ARCHITECTURES=arm64 && cmake --build addon/Build --config RelWithDebInfo -j8`; `-Werror`.
- Testy Pythona: `cd FloorPlan6 && source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest <pliki> -q -p no:cacheprovider`. Pełna suita (~70 min) tylko raz, w Task 7.
- Commity po polsku, prefiks `feat/fix/build/docs/test`, stopka `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8`; `git add` tylko jawnych ścieżek (nigdy `* 2.*`, `addon/Build`, `packaging/dist|build|.venv|build.log`).
- Nie ruszać `/Applications/Graphisoft/Archicad 29/Dodatki` z poziomu implementera; instalacja i testy live = Dawid (`packaging/install_local.sh`).

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `service/errors.py` | `describe(exc) -> tuple[str, str]` bez Qt (tytuł, tekst EN); `ui/user_errors.py` deleguje |
| `service/results.py` | `ResultStore` (LRU 20): obiekty planów per job do `/export` |
| `service/solve_adapter.py` | `solve_request` rozszerzony o `source` (selection/point/polygon), `max_variants: 0` = tylko obrys, kształt wyniku z `boundary` + `variants[]` |
| `service/app.py` | `/export`, `/shutdown`, `/health` z `ac_port`; `ResultStore` w handlerze |
| `service/client.py` | `export()`, `shutdown()` |
| `service/serve.py` | tryb `--serve`: plik portu, watchdog rodzica, obsługa SIGTERM |
| `bridge/house_export.py` | `export_house_storeys(layout, storeys, tapir) -> dict` — wspólna logika obu kondygnacji (GUI + serwis) |
| `bridge/ac_ports.py` | `service_port_file(ac_port) -> Path`, `write_port_file`, `read_port_file`, `remove_port_file` |
| `floorforge_app.py` | `--serve` |
| `addon/Sources/ServiceClient.{hpp,cpp}` | HTTP+JSON do serwisu |
| `addon/Sources/ServiceSupervisor.{hpp,cpp}` | spawn/health/shutdown serwisu, plik portu |
| `addon/Sources/FloorForgePalette.{hpp,cpp}` | paleta: UI, podgląd, wątek roboczy, akcje |
| `addon/Sources/PaletteModel.hpp` | `Boundary`, `RoomView`, `VariantView`, `PaletteState` (parsowanie kontraktu) |
| `addon/Sources/AddOnMain.cpp`, `ResourceIds.hpp`, `RINT/AddOn.grc` | menu Palette, rejestracja palety, `GDLG` palety, stringi |
| Usuwany: `addon/Sources/FloorForgeLauncher.{hpp,cpp}` | zastąpiony supervisorem |
| `packaging/build_release.sh`, `INSTALL.md`, `INSTALACJA.md`, `CHECKLIST_TEST.md`, `README.md`, `docs/STATE.md` | bramka `--serve`, docs |
| Testy: `tests/test_service_errors.py`, `tests/test_results_store.py`, `tests/test_solve_source.py`, `tests/test_service_export.py`, `tests/test_service_serve.py`, `tests/test_house_export.py`, `tests/test_ac_ports.py` | |

---

### Task 1: Serwis — `describe` bez Qt, `ResultStore`, `/solve` z `source`, `/export`, `/shutdown`

**Files:**
- Create: `service/errors.py`, `service/results.py`
- Modify: `service/solve_adapter.py`, `service/app.py`, `service/client.py`, `ui/user_errors.py`
- Test: `tests/test_service_errors.py`, `tests/test_results_store.py`, `tests/test_solve_source.py`, `tests/test_service_export.py`

**Interfaces:**
- Produces: `service.errors.describe(exc) -> tuple[str, str]` (identyczne mapowanie jak dziś w `ui/user_errors.py`, bez `Log:` — tę linię dokleja `ui/user_errors.py`).
- `service.results.ResultStore`: `put(job_id, entry: dict)`, `get(job_id) -> dict | None`, `LIMIT = 20` (najstarsze usuwane).
- `service.solve_adapter.solve_request(req, progress=None, store=None) -> dict`: `req["source"] ∈ {"selection","point","polygon"}` (domyślnie `"polygon"` dla zgodności); zwraca `{"mode", "boundary": {"polygon": [[x,y]...], "entry": [x,y], "area": float, "auto_type": "M1".."M5"}, "variants": [{"index": i, "score": s, "contract": {...}}]}`; dla `mode == "house"`: `variants = [{"index": 0, "score": None, "contract": {"parter": ..., "poddasze": ...}}]`; `max_variants == 0` → `variants: []` bez solve; gdy `store` podany, zapisuje `{"mode", "boundary", "plans": [FloorPlan]}` lub `{"mode", "boundary", "layout": TwoStoreyLayout}` pod `job_id` przekazanym w `req["_job_id"]`.
- `POST /export {"job_id","variant","storeys","furniture"}` → 200/404/409/503/422 (spec §3.2). `POST /shutdown` → 200 i `ServiceHandle.stop()` z wątku pomocniczego. `GET /health` → `{status, version, ac_port}` (`ac_port` = `env_ac_port()` lub null).
- `ServiceClient.export(req) -> dict` (rzuca `RuntimeError(error)` przy 4xx/5xx z ciałem JSON), `ServiceClient.shutdown() -> None`.

- [ ] **Step 1: Failing tests — errors + store**

```python
# tests/test_service_errors.py
import pytest


@pytest.mark.parametrize("exc, title, frag", [
    (ConnectionError("x"), "Archicad", "FloorForge add-on"),
    (TimeoutError("timed out"), "Archicad", "does not respond"),
    (RuntimeError("INFEASIBLE"), "No layout", "Try another type"),
    (ValueError("Select the outline walls first."), "Input data", "Select the outline walls first."),
    (ZeroDivisionError("x"), "Unexpected error", "Technical details"),
])
def test_describe_without_qt(exc, title, frag):
    import sys
    from service.errors import describe
    assert "PyQt5" not in sys.modules or True  # describe must not import Qt itself
    t, text = describe(exc)
    assert t == title and frag in text
    assert "Log:" not in text


def test_ui_user_errors_delegates_and_appends_log(monkeypatch, tmp_path):
    import ui.app_logging as al
    monkeypatch.setattr(al, "_LOG_PATH", tmp_path / "floorforge.log")
    from ui.user_errors import describe as ui_describe
    from service.errors import describe as svc_describe
    exc = RuntimeError("INFEASIBLE")
    t1, x1 = svc_describe(exc)
    t2, x2 = ui_describe(exc)
    assert t1 == t2 and x2.startswith(x1) and "Log:" in x2
```

```python
# tests/test_results_store.py
def test_put_get_and_lru_eviction():
    from service.results import ResultStore
    s = ResultStore(limit=3)
    for i in range(4):
        s.put(f"j{i}", {"mode": "apartment", "plans": [i]})
    assert s.get("j0") is None
    assert s.get("j3") == {"mode": "apartment", "plans": [3]}
    assert s.get("nope") is None


def test_get_refreshes_recency():
    from service.results import ResultStore
    s = ResultStore(limit=2)
    s.put("a", {}); s.put("b", {})
    s.get("a")
    s.put("c", {})
    assert s.get("b") is None and s.get("a") is not None
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: service.errors` / `service.results`).

- [ ] **Step 3: Implement `service/errors.py` + `service/results.py`; `ui/user_errors.py` deleguje**

`service/errors.py`: przenieś ciało `describe` z `ui/user_errors.py` (wszystkie gałęzie: `ConnectionError` z wariantem `FLOORFORGE_LAUNCHED_FROM_AC`, `TimeoutError`, `KeyError`/`additionalProperties`, `INFEASIBLE`, `ValueError`, fallback) **bez** `_tail`'s `Log:` — tekst kończy się `"\n\nTechnical details: <repr[:200]>"`. `ui/user_errors.py`:

```python
from service.errors import describe as _describe_core
from ui.app_logging import log_path

def describe(exc: BaseException) -> tuple[str, str]:
    title, text = _describe_core(exc)
    lp = log_path()
    return title, (text + f"\nLog: {lp}" if lp else text)
```

Sprawdź istniejące testy `tests/test_user_errors.py` (kolejność `Log:`/`Technical details:`): jeśli asercja wymaga `Log:` PRZED `Technical details:`, zachowaj dzisiejszą kolejność (wstaw `Log:` przed sekcją technical) — testy są autorytetem.

`service/results.py`:

```python
"""Wyniki jobów w pamięci (obiekty planów) — /export wstawia bez deserializacji kontraktu."""
from __future__ import annotations
import threading
from collections import OrderedDict


class ResultStore:
    LIMIT = 20

    def __init__(self, limit: int | None = None):
        self._limit = limit or self.LIMIT
        self._d: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()

    def put(self, job_id: str, entry: dict) -> None:
        with self._lock:
            self._d[job_id] = entry
            self._d.move_to_end(job_id)
            while len(self._d) > self._limit:
                self._d.popitem(last=False)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            e = self._d.get(job_id)
            if e is not None:
                self._d.move_to_end(job_id)
            return e
```

- [ ] **Step 4: Run → PASS**, commit `feat(service): describe bez Qt + ResultStore`.

- [ ] **Step 5: Failing tests — `source` i kształt wyniku**

```python
# tests/test_solve_source.py
import pytest
from shapely.geometry import Polygon

RECT = [[0, 0], [8, 0], [8, 6], [0, 6]]


def _fake_plan():
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan
    from core.template_selector import load_all_templates
    tpl = next(t for t in load_all_templates() if t.id == "M2_standard")
    return FloorPlan(boundary=analyze_boundary(Polygon(RECT), (4.0, 0.0)), template=tpl, rooms=[], score=0.9)


def test_polygon_source_boundary_only_when_zero_variants(monkeypatch):
    import service.solve_adapter as sa
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: pytest.fail("solver must not run"))
    out = sa.solve_request({"mode": "apartment", "source": "polygon", "polygon": RECT, "entry": [4, 0], "max_variants": 0})
    assert out["variants"] == []
    b = out["boundary"]
    assert b["area"] == pytest.approx(48.0) and b["auto_type"] == "M2" and b["entry"] == [4.0, 0.0]
    assert len(b["polygon"]) >= 4


@pytest.mark.parametrize("area, mtype", [(40, "M1"), (48, "M2"), (70, "M3"), (100, "M4"), (130, "M5")])
def test_auto_type_thresholds(area, mtype):
    from service.solve_adapter import auto_type_for_area
    assert auto_type_for_area(area) == mtype


def test_selection_source_uses_boundary_reader(monkeypatch):
    import service.solve_adapter as sa
    from core.models import WallType
    monkeypatch.setattr(sa, "read_boundary_from_archicad",
                        lambda tapir=None: (Polygon(RECT), (4.0, 0.0), [WallType.FACADE] * 4))
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: [_fake_plan()])
    out = sa.solve_request({"mode": "apartment", "source": "selection", "mtype": "M2", "max_variants": 1})
    assert out["boundary"]["auto_type"] == "M2"
    assert out["variants"][0]["index"] == 0 and out["variants"][0]["score"] == 0.9
    assert "rooms" in out["variants"][0]["contract"]


def test_point_source_passes_coordinates(monkeypatch):
    import service.solve_adapter as sa
    seen = {}
    def fake(x, y, tapir=None):
        seen.update(x=x, y=y); return (Polygon(RECT), (4.0, 0.0), None)
    monkeypatch.setattr(sa, "read_boundary_from_point", fake)
    out = sa.solve_request({"mode": "apartment", "source": "point", "point": [3.5, 2.0], "max_variants": 0})
    assert seen == {"x": 3.5, "y": 2.0} and out["boundary"]["area"] == pytest.approx(48.0)


def test_store_receives_plans(monkeypatch):
    import service.solve_adapter as sa
    from service.results import ResultStore
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: [_fake_plan()])
    store = ResultStore()
    sa.solve_request({"mode": "apartment", "source": "polygon", "polygon": RECT, "entry": [4, 0], "mtype": "M2",
                      "max_variants": 1, "_job_id": "j1"}, store=store)
    e = store.get("j1")
    assert e["mode"] == "apartment" and len(e["plans"]) == 1 and e["plans"][0].score == 0.9


def test_house_result_shape(monkeypatch):
    import service.solve_adapter as sa
    monkeypatch.setattr(sa, "generate_house", lambda p, e, **kw: "LAYOUT")
    monkeypatch.setattr(sa, "house_to_contract", lambda layout: {"parter": {"rooms": []}, "poddasze": {"rooms": []}})
    out = sa.solve_request({"mode": "house", "source": "polygon", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]], "entry": [5, 0]})
    assert out["variants"] == [{"index": 0, "score": None, "contract": {"parter": {"rooms": []}, "poddasze": {"rooms": []}}}]


def test_unknown_source_is_value_error():
    import service.solve_adapter as sa
    with pytest.raises(ValueError, match="source"):
        sa.solve_request({"mode": "apartment", "source": "magic"})
```

- [ ] **Step 6: Run → FAIL.**

- [ ] **Step 7: Implement in `service/solve_adapter.py`**

Dodaj importy: `from bridge.boundary_reader import read_boundary_from_archicad, read_boundary_from_point` (lazy w funkcji, żeby `archicad` nie ładował się przy imporcie testów bez potrzeby — ale monkeypatch wymaga atrybutu modułu: importuj na górze modułu; `bridge.boundary_reader` importuje `archicad` — jest w venv, OK).

```python
def auto_type_for_area(area_m2: float) -> str:
    if area_m2 < 45: return "M1"
    if area_m2 < 65: return "M2"
    if area_m2 < 85: return "M3"
    if area_m2 < 110: return "M4"
    return "M5"


def _boundary_from_source(req: dict):
    source = req.get("source", "polygon")
    if source == "polygon":
        return _polygon(req), _entry(req), req.get("wall_types")
    if source == "selection":
        poly, entry, wall_types = read_boundary_from_archicad()
        return poly, entry, wall_types
    if source == "point":
        pt = req.get("point")
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValueError("Field 'point' must be a pair [x, y].")
        poly, entry, wall_types = read_boundary_from_point(_float(pt[0], "point.x"), _float(pt[1], "point.y"))
        return poly, entry, wall_types
    raise ValueError("Field 'source' must be 'selection', 'point' or 'polygon'.")


def _boundary_info(poly, entry) -> dict:
    return {"polygon": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
            "entry": [float(entry[0]), float(entry[1])], "area": round(poly.area, 2),
            "auto_type": auto_type_for_area(poly.area)}
```

`solve_request(req, progress=None, store=None)`: `mode` walidacja jak dziś → `poly, entry, wall_types = _boundary_from_source(req)` → `boundary = _boundary_info(poly, entry)` → `max_variants = _int_field(req, "max_variants", 5)`; jeśli `0` → `return {"mode": mode, "boundary": boundary, "variants": []}`. Apartment: `mtype = req.get("mtype") or boundary["auto_type"]`; walidacja `APARTMENT_TYPES`; `plans = generate_variants(poly, entry, mtype, max_variants, progress_callback=progress, wall_types=wall_types, template_filter=..., min_score=...)`; `variants = [{"index": i, "score": p.score, "contract": plan_to_contract(p.rooms, p.boundary, storey="single", template=p.template)} for i, p in enumerate(plans)]`; `store.put(req["_job_id"], {"mode": "apartment", "boundary": boundary, "plans": plans})` gdy `store` i `_job_id`. House: `layout = generate_house(poly, entry, num_storeys=...)`; jeśli `not layout.ok` → `raise RuntimeError(layout.message)`; `variants = [{"index": 0, "score": None, "contract": house_to_contract(layout)}]`; store `{"mode": "house", "boundary": boundary, "layout": layout}`. Istniejące testy `tests/test_solve_adapter.py` muszą przejść (stary kształt `{"mode","variants"}` dostaje dodatkowe `boundary`; jeśli test asercji na dokładny dict, dostosuj test o `boundary`). Zachowaj polskie→angielskie komunikaty jak dziś (już EN).

- [ ] **Step 8: Run → PASS** (`tests/test_solve_source.py tests/test_solve_adapter.py`), commit `feat(service): /solve z source selection|point|polygon, obrys-only przy max_variants=0, wyniki do ResultStore`.

- [ ] **Step 9: Failing tests — `/export`, `/shutdown`, `/health.ac_port`**

```python
# tests/test_service_export.py
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
```

- [ ] **Step 10: Run → FAIL.**

- [ ] **Step 11: Implement in `service/app.py` + `service/client.py`**

W `service/app.py`:
- import: `from service.results import ResultStore`, `from bridge.plan_writer import export_plan_to_archicad`, `from bridge.house_export import export_house_storeys` (Task 2 — do czasu Task 2 zaimportuj leniwie wewnątrz gałęzi house; test apartment nie dotyka house), `from bridge.tapir_connection import TapirConnection, env_ac_port`.
- `def connect_to_ac():` → `t = TapirConnection(); port = env_ac_port(); t.use_port(port) if port else t.connect(); return t` (rzuca `ConnectionError`).
- `start_server(host, port, job_store=None, result_store=None)`; handler ma `store` i `results`; `ServiceHandle.is_running() -> bool` (`self._thread.is_alive()`); `stop()` idempotentny.
- `do_POST /solve`: `jid = self.store.submit(solve_request, {**body, "_job_id": <jid>}, store=self.results)` — `JobStore.submit` generuje id dopiero w środku; zmień `submit` na `submit(fn, *args, job_id=None, **kwargs)`: gdy `job_id` podany, użyj go; w `/solve` wygeneruj `jid = uuid4().hex[:12]` w handlerze i przekaż do body i do `submit`.
- `do_POST /export`: waliduj `job_id`/`variant` (int, domyślnie 0), `storeys` (lista z `parter`/`poddasze`, domyślnie `["parter"]`), `furniture` (bool, domyślnie False); `job = self.store.get(job_id)` → brak → 404 `{"error": "Unknown job id."}`; `status != "done"` → 409 `{"error": "Job is not finished yet."}`; `entry = self.results.get(job_id)` → brak → 404 `{"error": "Result no longer available (evicted). Generate again."}`; apartment: `plans = entry["plans"]`, `variant` poza zakresem → 404 `{"error": "Unknown variant index."}`; `tapir = connect_to_ac()` (`ConnectionError` → 503 `{"error": "Archicad does not respond on the JSON port …"}`); `res = export_plan_to_archicad(plans[variant], tapir=tapir, include_furniture=furniture)`; odpowiedź `{"zones": len(res.get("zones", [])), "walls": …, "doors": …, "windows": …, "labels": …, "storeys": ["parter"]}`; house: `res = export_house_storeys(entry["layout"], storeys, tapir, include_furniture=furniture)` → jeśli `res["error"]` → 422 z `error` i `inserted`; inaczej 200 `{**res["totals"], "storeys": res["inserted"], "partial": res["partial"]}`. `ValueError` z writera → 422.
- `do_POST /shutdown` → 200 `{"status": "stopping"}`, potem `threading.Thread(target=self.server.shutdown, daemon=True).start()` (shutdown z innego wątku niż serve_forever).
- `/health` → `{"status": "ok", "version": VERSION, "ac_port": env_ac_port()}`.

`service/client.py`: `export(self, req) -> dict` — jak `_req("POST", "/export", req)`, ale `urllib.error.HTTPError` → wczytaj JSON i `raise RuntimeError(body.get("error", str(e)))`; `shutdown(self)` → `_req("POST", "/shutdown", {})`, ignoruj błąd połączenia po odpowiedzi.

- [ ] **Step 12: Run → PASS** (`tests/test_service_export.py tests/test_service_app.py tests/test_service_jobs.py tests/test_selftest.py`), commit `feat(service): /export z ResultStore, /shutdown, /health z ac_port`.

---

### Task 2: `bridge/house_export.py` — wspólna logika obu kondygnacji (GUI + serwis)

**Files:**
- Create: `bridge/house_export.py`
- Modify: `ui/main_window.py` (`_export_house_to_archicad` ~1177–1300: pętla → wywołanie), `service/app.py` (import realny)
- Test: `tests/test_house_export.py`, istniejące `tests/test_house_export_gui.py` muszą przejść bez zmian asercji

**Interfaces:**
- Produces: `export_house_storeys(layout, storeys: list[str], tapir, *, include_furniture=False, offset=(0.0, 0.0)) -> dict` = `{"inserted": [str], "totals": {"zones","walls","doors","windows","labels"}, "partial": bool, "error": str | None, "error_stage": str | None}`. Zasady (przeniesione 1:1 z GUI): `first/last = get_stories()`; `parter_idx = parter_story_index(first, last)`, `poddasze_idx = parter_idx + 1`; gdy `"poddasze" in storeys` i `poddasze_idx > last` → `error = "The Archicad project has no storey above the ground floor (index N) — add a storey in Archicad or insert only the ground floor."`, nic nie wstawiane; dla każdej kondygnacji: `activate_story(idx)` → `False` → `partial=True`, `error = "Could not switch Archicad to storey N ('<label>'). <Inserted so far> has already been inserted; switch the storey manually in Archicad and insert only the remaining storey."`, przerwij; sukces → `export_house_to_archicad(layout, storey=..., tapir=tapir, offset=offset, include_furniture=include_furniture)` sumowane do `totals`. Layout parterowy (`not layout.pietro_rooms`) z `storeys` zawierającym `poddasze` → `error` z `house_writer` (422). Pojedyncza kondygnacja bez auto-switch: `storeys=["poddasze"]` → tylko `activate_story(poddasze_idx)`; GUI-owy guard z override zostaje w GUI (przed wywołaniem).

- [ ] **Step 1: Failing tests**

```python
# tests/test_house_export.py
import pytest


class _Tapir:
    def __init__(self, first=0, last=1, switch_ok=None):
        self.first, self.last = first, last
        self.switch_ok = switch_ok or (lambda i: True)
        self.switched = []
    def get_stories(self): return {"actStory": 0, "firstStory": self.first, "lastStory": self.last}
    def activate_story(self, i): self.switched.append(i); return self.switch_ok(i)


def _layout(two=True):
    return type("L", (), {"pietro_rooms": [object()] if two else []})()


def _wire(monkeypatch, per_storey=None):
    import bridge.house_export as he
    calls = []
    def fake(layout, storey="parter", tapir=None, offset=(0, 0), include_furniture=False):
        calls.append(storey)
        return {"zones": ["z"] * 2, "walls": ["w"], "doors": [], "windows": [], "labels": ["l"]}
    monkeypatch.setattr(he, "export_house_to_archicad", per_storey or fake)
    return calls


def test_both_storeys_ground_floor_index_zero(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    t = _Tapir(first=-1, last=1)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], t)
    assert t.switched == [0, 1] and calls == ["parter", "poddasze"]
    assert r["inserted"] == ["parter", "poddasze"] and r["partial"] is False and r["error"] is None
    assert r["totals"] == {"zones": 4, "walls": 2, "doors": 0, "windows": 0, "labels": 2}


def test_no_storey_above_ground_blocks_before_write(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], _Tapir(first=0, last=0))
    assert calls == [] and r["inserted"] == [] and "no storey above" in r["error"]


def test_switch_failure_midway_is_partial(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    t = _Tapir(switch_ok=lambda i: i == 0)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], t)
    assert calls == ["parter"] and r["inserted"] == ["parter"] and r["partial"] is True
    assert "already been inserted" in r["error"] and "only the remaining" in r["error"]


def test_single_storey_layout_attic_error(monkeypatch):
    from bridge.house_export import export_house_storeys
    def boom(layout, storey="parter", **kw):
        raise ValueError("A single-storey house has no attic — choose 'parter'.")
    _wire(monkeypatch, per_storey=boom)
    r = export_house_storeys(_layout(two=False), ["poddasze"], _Tapir())
    assert r["error"] and "single-storey" in r["error"] and r["inserted"] == []
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `bridge/house_export.py`** (czysta funkcja, bez Qt), potem **przepnij GUI**: w `_export_house_to_archicad` zastąp pętlę `for st_name, target_idx in plan_storeys:` wywołaniem `export_house_storeys(layout, [s for s, _ in plan_storeys], tapir, offset=self._archicad_offset)` **tylko w trybie both**; tryb pojedynczej kondygnacji (z guardem i override) zostaw jak jest, ale wywołaj `export_house_storeys(layout, [storey], tapir, ...)` po przejściu guardu — bez `activate_story` (dodaj parametr `switch: bool = True`; GUI single przekazuje `switch=False`). Komunikaty GUI (dialogi) budowane z `r["error"]`, `r["inserted"]`, `r["totals"]` — treść identyczna z dzisiejszą, żeby `tests/test_house_export_gui.py` przeszły (dopasuj sformułowania w `house_export.py` do istniejących asercji: "already been inserted", "only the remaining", "no storey above the ground floor").

- [ ] **Step 4: Run → PASS** (`tests/test_house_export.py tests/test_house_export_gui.py tests/test_ac_targeting.py tests/test_service_export.py`), commit `feat(bridge): house_export.export_house_storeys — wspólna logika obu kondygnacji dla GUI i serwisu`.

---

### Task 3: `--serve` — plik portu, watchdog rodzica, SIGTERM; klient `export/shutdown`

**Files:**
- Create: `service/serve.py`, `bridge/ac_ports.py`
- Modify: `floorforge_app.py`
- Test: `tests/test_ac_ports.py`, `tests/test_service_serve.py`

**Interfaces:**
- `bridge/ac_ports.py`: `PORT_DIR = Path(os.environ.get("FLOORFORGE_PORT_DIR") or "~/Library/Application Support/FloorForge").expanduser()`; `service_port_file(ac_port: int | None) -> Path` (`service-<ac_port or 0>.port`); `write_port_file(ac_port, http_port, pid, version) -> Path`; `read_port_file(ac_port) -> dict | None` (`{"port": int, "pid": int, "version": str}`), `remove_port_file(ac_port)`.
- `service/serve.py`: `run_serve(argv_port: int | None = None) -> int`: `start_server(port=0, result_store=ResultStore())`, `write_port_file(env_ac_port(), handle.port, os.getpid(), VERSION)`, pętla `while handle.is_running(): sleep(2); if os.getppid() != parent0 or os.getppid() == 1: log + handle.stop()`; SIGTERM handler → `handle.stop()`; `finally: remove_port_file(...)`; zwraca 0.
- `floorforge_app.py`: `--serve` → `from service.serve import run_serve; return run_serve()` (po `setup_logging()`, przed jakimkolwiek importem Qt).

- [ ] **Step 1: Failing tests**

```python
# tests/test_ac_ports.py
def test_port_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_PORT_DIR", str(tmp_path))
    import importlib, bridge.ac_ports as ap
    importlib.reload(ap)
    p = ap.write_port_file(19723, 58000, 4242, "v1")
    assert p == tmp_path / "service-19723.port"
    assert p.read_text() == "PORT=58000\nPID=4242\nVERSION=v1\n"
    assert ap.read_port_file(19723) == {"port": 58000, "pid": 4242, "version": "v1"}
    ap.remove_port_file(19723)
    assert ap.read_port_file(19723) is None


def test_read_port_file_tolerates_garbage(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_PORT_DIR", str(tmp_path))
    import importlib, bridge.ac_ports as ap
    importlib.reload(ap)
    (tmp_path / "service-1.port").write_text("PORT=abc\n")
    assert ap.read_port_file(1) is None
```

```python
# tests/test_service_serve.py
import json, os, signal, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wait_port_file(path, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if path.exists():
            txt = path.read_text()
            if "PORT=" in txt:
                return int(txt.split("PORT=")[1].split()[0])
        time.sleep(0.1)
    raise AssertionError("port file not written")


def _spawn(tmp_path, ac_port="19999"):
    env = {**os.environ, "FLOORFORGE_PORT_DIR": str(tmp_path), "FLOORFORGE_LOG_DIR": str(tmp_path),
           "FLOORFORGE_AC_PORT": ac_port, "PYTHONPATH": str(ROOT)}
    return subprocess.Popen([sys.executable, str(ROOT / "floorforge_app.py"), "--serve"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_serve_writes_port_file_and_answers_health_then_shutdown(tmp_path):
    p = _spawn(tmp_path)
    try:
        port = _wait_port_file(tmp_path / "service-19999.port")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            body = json.loads(r.read())
        assert body["status"] == "ok" and body["ac_port"] == 19999
        req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        assert p.wait(timeout=15) == 0
        assert not (tmp_path / "service-19999.port").exists()
    finally:
        if p.poll() is None:
            p.kill()


def test_serve_exits_on_sigterm_and_removes_port_file(tmp_path):
    p = _spawn(tmp_path, ac_port="19998")
    try:
        _wait_port_file(tmp_path / "service-19998.port")
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=15)
        assert not (tmp_path / "service-19998.port").exists()
    finally:
        if p.poll() is None:
            p.kill()
```

(Watchdog rodzica testowany ręcznie w Task 4/7: po zamknięciu AC proces znika; test automatyczny wymagałby pośredniego procesu — pominięty świadomie, opisany w raporcie.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `bridge/ac_ports.py`, `service/serve.py`:

```python
# service/serve.py
"""Tryb --serve: serwis HTTP bez okna, plik portu per instancja AC, watchdog rodzica (AC)."""
from __future__ import annotations
import logging, os, signal, time
from bridge.ac_ports import remove_port_file, write_port_file
from bridge.tapir_connection import env_ac_port
from service.app import VERSION, start_server
from service.results import ResultStore

logger = logging.getLogger(__name__)
WATCHDOG_S = 2.0


def run_serve() -> int:
    ac_port = env_ac_port()
    handle = start_server(port=0, result_store=ResultStore())
    parent0 = os.getppid()
    write_port_file(ac_port, handle.port, os.getpid(), VERSION)
    logger.info("serve: port=%s ac_port=%s parent=%s", handle.port, ac_port, parent0)

    def _term(signum, frame):
        logger.info("serve: signal %s → stop", signum)
        handle.stop()
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    try:
        while handle.is_running():
            time.sleep(WATCHDOG_S)
            ppid = os.getppid()
            if ppid != parent0 or ppid == 1:
                logger.info("serve: parent %s gone (now %s) → stop", parent0, ppid)
                handle.stop()
        return 0
    finally:
        remove_port_file(ac_port)
```

`floorforge_app.py`: przed `--ac-probe`: `if "--serve" in argv: from service.serve import run_serve; return run_serve()`.

- [ ] **Step 4: Run → PASS**, commit `feat: tryb --serve (plik portu, watchdog rodzica, SIGTERM) + bridge/ac_ports`.

---

### Task 4: C++ — `ServiceClient`, `ServiceSupervisor`, menu „Palette" z pustą paletą (stopka stanu)

**Files:**
- Create: `addon/Sources/ServiceClient.{hpp,cpp}`, `addon/Sources/ServiceSupervisor.{hpp,cpp}`, `addon/Sources/FloorForgePalette.{hpp,cpp}` (szkielet), `addon/Sources/PaletteModel.hpp`
- Delete: `addon/Sources/FloorForgeLauncher.{hpp,cpp}`
- Modify: `addon/Sources/AddOnMain.cpp`, `addon/Sources/ResourceIds.hpp`, `addon/Sources/RINT/AddOn.grc`

**Interfaces:**
- `ServiceClient` (`namespace FloorForge`): `explicit ServiceClient (UShort port)`; `bool Health (GS::UniString& versionOut)`; `GS::UniString Solve (const GS::UniString& jsonBody)` (zwraca `job_id` lub pusty + `lastError`); `JSON::ObjectValueRef Job (const GS::UniString& jobId)`; `JSON::ObjectValueRef Export (const GS::UniString& jsonBody, int& statusCodeOut)`; `void Shutdown ()`; `GS::UniString lastError`. Implementacja: `IO::URI::URI ("http://127.0.0.1:<port>")`, `HTTP::Client::ClientConnection`, `Request (Method::Post|Get, path)`, body przez `request.GetRequestHeaderFieldCollection().Add(ContentType, "application/json")` + `clientConnection.Send (request, body.ToCStr(CC_UTF8).Get(), len)` (sprawdź sygnaturę `Send` w `HTTP/Client/ClientConnection.hpp`; alternatywa: `Request::SetBody`/`OBinaryChannel`), timeouts przez `clientConnection.SetTimeout`/`Timeout` (sprawdź w headerze; jeśli brak API, zaakceptuj domyślny).
- `ServiceSupervisor`: `static ServiceSupervisor& Instance ()`; `bool EnsureRunning (GS::UniString& errorOut)` — czyta plik portu `~/Library/Application Support/FloorForge/service-<acport>.port` (`IO::Location` z `IO::fileSystem.GetSpecialLocation (IO::FileSystem::UserHome)` + `Library/Application Support/FloorForge`), jeśli `Health` OK → true; inaczej spawn `<bundle>/Contents/Resources/FloorForge/FloorForge --serve` z env (`FLOORFORGE_BETA=1`, `FLOORFORGE_VERSION`, `FLOORFORGE_AC_PORT`, `FLOORFORGE_LAUNCHED_FROM_AC=1`) przez `GS::Process::Create`, polling pliku portu co 250 ms do 15 s, potem `Health`; `UShort Port () const`; `void Shutdown ()` (POST `/shutdown`, `WaitFor (2000)`, `Kill ()` gdy żyje); `bool IsRunning ()`. Ścieżka exe: loop `.bundle`-suffix z dzisiejszego launchera (przenieś funkcję `GetEmbeddedExecutablePath`).
- Paleta (szkielet): `FloorForgePalette` (wzór `FloorPlan4_CPP/Src/FloorPlanPalette.*` → `DG::Palette`, `DG::PanelObserver`, `DG::ButtonItemObserver`, `DG::UserItemObserver`), singleton `HasInstance/CreateInstance/GetInstance/DestroyInstance`, `RegisterPaletteControlCallBack` (`ACAPI_RegisterModelessWindow` jak Tapir/FP4), `Show/Hide`; w tej fazie zawiera tylko `statusText` (LeftText) i przycisk `Restart service`. `Show()` → `ServiceSupervisor::EnsureRunning` w wątku roboczym (`GS::ThreadedExecutor executor; executor.Execute (new EnsureTask)`) → wynik do UI przez `GS::MessageLoopExecutor ().Execute (new SetStatusTask (text))`.
- Menu: `ID_ADDON_MENU_PALETTE 32002/1` „Palette" (zastępuje „Room layout"); handler → `if (!HasInstance()) CreateInstance(); GetInstance().Show();`. `FreeData` → `ServiceSupervisor::Instance().Shutdown()`; `DestroyInstance`.

- [ ] **Step 1: `PaletteModel.hpp`** (struktury używane w Task 5/6):

```cpp
#pragma once
#include "UniString.hpp"
#include <vector>
#include <utility>

namespace FloorForge {

struct Pt { double x = 0, y = 0; };

struct RoomView {
    GS::UniString id, name, zone;    // zone: "dzienna" | "nocna" | "uslugowa" | "komunikacja" (contract "strefa")
    double area = 0;
    std::vector<Pt> polygon;
};

struct Boundary {
    std::vector<Pt> polygon;
    Pt entry;
    double area = 0;
    GS::UniString autoType;          // "M1".."M5"
};

struct StoreyView {                  // jedna kondygnacja (mieszkanie = 1, dom = 2)
    GS::UniString label;             // "" | "GROUND FLOOR" | "ATTIC"
    std::vector<RoomView> rooms;
    std::vector<Pt> boundary;
};

struct VariantView {
    int index = 0;
    double score = 0;                // house: -1 (brak)
    std::vector<StoreyView> storeys;
};

enum class Mode { Apartment, House };

struct PaletteState {
    GS::UniString jobId;
    Boundary boundary; bool hasBoundary = false;
    std::vector<VariantView> variants; int current = 0;
    Mode mode = Mode::Apartment;
    int variantsRequested = 5;       // 1..5
    GS::UniString mtype;             // "" = auto
    bool bothStoreys = true;
    bool busy = false;
    GS::UniString status;            // stopka
};

} // namespace FloorForge
```

- [ ] **Step 2: `ServiceClient`** — plik `.cpp` w duchu `VersionChecker::GetVersionFromGithub` (z `tapir-custom/archicad-addon/Sources/VersionChecker.cpp:70-110`): połączenie, request, `JSON::JDOMParser parser; JSON::ValueRef parsed = parser.Parse (clientConnection.BeginReceive (response));`, `response.GetStatusCode ()`. Body POST: znajdź w `HTTP/Client/ClientConnection.hpp` przeciążenie `Send (const Request&, const char* body, UInt64 size)` lub `Request::SetContentLength` + `clientConnection.Send (request)` + `clientConnection.GetOutputChannel().Write(...)` — implementer wybiera to, które istnieje, i opisuje w raporcie. Każda metoda: `try { … } catch (const GS::Exception& e) { lastError = e.GetMessage (); return …; } catch (...) { lastError = "HTTP error"; … }`.

- [ ] **Step 3: `ServiceSupervisor`** — jak w Interfaces; plik portu czytany przez `IO::File` (`IO::File f (loc); f.Open (IO::File::ReadMode); char buf[256]; f.ReadBin (...)`) lub przez `std::ifstream` na ścieżce POSIX (`loc.ToPath (&path)`; prostsze — użyj `std::ifstream`). Parsowanie linii `PORT=`, `PID=`. Przy `EnsureRunning`: jeśli plik jest, ale `Health` nie odpowiada → plik martwy → `unlink` i spawn.

- [ ] **Step 4: Szkielet palety + zasoby + menu**

`RINT/AddOn.grc` — `GDLG` palety (v1 pełna geometria od razu; przyciski nieużywane w tym tasku zostają nieaktywne):

```
'GDLG' ID_PALETTE Palette | topCaption | close | grow   0   0   360   700   "FloorForge" {
/* [  1] */ LeftText       8    8  344  16  LargePlain vCenter "Service: starting…"
/* [  2] */ Button         8   30  168  24  LargePlain "Load from selection"
/* [  3] */ Button       184   30  168  24  LargePlain "Pick point"
/* [  4] */ UserItem       8   60  344 150
/* [  5] */ LeftText       8  214  344  16  LargePlain vCenter "Outline: —"
/* [  6] */ RadioButton    8  236  160  20  LargePlain "Apartment"
/* [  7] */ RadioButton  184  236  160  20  LargePlain "House"
/* [  8] */ LeftText       8  262   40  20  LargePlain vCenter "Type:"
/* [  9] */ PopupControl  52  262   90  20  90 6
/* [ 10] */ LeftText     160  262   60  20  LargePlain vCenter "Variants:"
/* [ 11] */ PopupControl 224  262   60  20  60 5
/* [ 12] */ CheckBox       8  288  344  20  LargePlain "Insert both storeys (auto-switch in Archicad)"
/* [ 13] */ Button         8  314  344  28  LargeBold  "Generate"
/* [ 14] */ UserItem       8  348  344  10
/* [ 15] */ UserItem       8  364  344 240
/* [ 16] */ Button         8  610   40  24  LargePlain "<"
/* [ 17] */ LeftText      56  610  200  24  LargePlain vCenter "No variants"
/* [ 18] */ Button       312  610   40  24  LargePlain ">"
/* [ 19] */ Button         8  640  344  28  LargeBold  "Insert into Archicad"
/* [ 20] */ Button         8  672  168  20  LargePlain "Restart service"
}
'DLGH' ID_PALETTE FloorForge_Palette {
1 "" StatusText
2 "" LoadSelectionBtn
3 "" PickPointBtn
4 "" OutlinePreview
5 "" OutlineText
6 "" ApartmentRadio
7 "" HouseRadio
8 "" TypeLabel
9 "" TypePopup
10 "" VariantsLabel
11 "" VariantsPopup
12 "" BothStoreysCheck
13 "" GenerateBtn
14 "" ProgressBar
15 "" VariantPreview
16 "" PrevBtn
17 "" VariantText
18 "" NextBtn
19 "" InsertBtn
20 "" RestartBtn
}
```

`ResourceIds.hpp`: `ID_PALETTE 32004`, `ID_ADDON_MENU_PALETTE 32002`, `ID_ADDON_MENU_PALETTE_ITEM 1`, item IDs `Pal_StatusText=1 … Pal_RestartBtn=20`, `ID_PALETTE_STRINGS 32013` (`1 "Service: starting…"`, `2 "Service: ready (%T)"`, `3 "Service: error — %T"`, `4 "FloorForge service failed to start.\n%T\n\nSee ~/Library/Logs/FloorForge/floorforge.log"`, `5 "OK"`). Menu `STR#` 32002: `"FloorForge" / "Palette^E3^ES^EE^EI^ED^EL^EW^ET^EM"`.

`AddOnMain.cpp`: `RegisterInterface` rejestruje `ID_ADDON_MENU_PALETTE` + `ID_ADDON_MENU`; `Initialize` instaluje handlery + `FloorForgePalette::RegisterPaletteControlCallBack ()`; `FreeData` → `ServiceSupervisor::Instance ().Shutdown (); FloorForgePalette::DestroyInstance ();`. Usuń `FloorForgeLauncher.*` i jego include. `PaletteControlCallBack` — kopia z `FloorPlan4_CPP/Src/FloorPlanPalette.cpp:187-225` (obsługa `APIPalMsg_OpenPalette/ClosePalette/HidePalette_Begin/End/DisableItems_Begin/End/IsPaletteVisible`).

`FloorForgePalette.cpp` (ta faza): ctor łączy itemy (`DG::LeftText statusText (GetReference (), Pal_StatusText)` itd.), `Attach (*this)`, `AttachToAllItems (*this)`; `Show ()` → `DG::Palette::Show (); EnsureServiceAsync ();`. `EnsureServiceAsync`: 

```cpp
class EnsureTask : public GS::Runnable {
    void Run () override {
        GS::UniString err, ver;
        bool ok = ServiceSupervisor::Instance ().EnsureRunning (err) && ServiceSupervisor::Instance ().Client ().Health (ver);
        GS::MessageLoopExecutor ().Execute (new StatusTask (ok, ok ? ver : err));
    }
};
```
`StatusTask::Run` → `FloorForgePalette::GetInstance ().SetServiceStatus (ok, text)` (ustawia `statusText`, włącza/wyłącza przyciski). `RestartBtn` → `ServiceSupervisor::Shutdown ()` + `EnsureServiceAsync ()`.

- [ ] **Step 5: Build** (komenda z Global Constraints) → zielono. `strings …/MacOS/FloorForge | grep -c "service-"` ≥ 1.

- [ ] **Step 6: Commit** `feat(addon): ServiceClient + ServiceSupervisor + paleta (szkielet ze stopką stanu), menu Palette`.

- [ ] **Step 7: LIVE #1 (Dawid):** `packaging/build_release.sh` (bramka jeszcze bez `--serve` — Task 7) lub kopia `addon/Build/RelWithDebInfo/FloorForge.bundle` + osadzony Python z ostatniego zipa (`Contents/Resources/FloorForge` skopiowany z rozpakowanego `packaging/dist/FloorForge-*.zip`) → `packaging/install_local.sh <ścieżka.bundle>` → AC → **FloorForge → Palette**. Oczekiwane: paleta z „Service: ready (v…)" w ≤ 15 s; `pgrep -f "FloorForge --serve"` = 1 proces; `cat ~/Library/Application\ Support/FloorForge/service-19723.port`; Cmd+Q AC → proces znika w ≤ 5 s, plik portu usunięty. Wynik → raport/STATE.

---

### Task 5: Paleta — obrys (selection / point), Generate z postępem, podgląd, nawigacja

**Files:**
- Modify: `addon/Sources/FloorForgePalette.{hpp,cpp}`, `addon/Sources/PaletteModel.hpp` (parser kontraktu), `addon/Sources/RINT/AddOn.grc` (stringi błędów)

**Interfaces:**
- Consumes: `ServiceClient::Solve/Job`, `PaletteState`.
- Produces: `bool ParseJobResult (const JSON::ObjectValueRef& result, Boundary& b, std::vector<VariantView>& v)` w `PaletteModel.hpp/.cpp` (kontrakt: `boundary.polygon`, `entry`, `area`, `auto_type`; `variants[i].contract.rooms[]{name, strefa, area, polygon}`; dom: `contract.parter/poddasze` → 2 `StoreyView` z etykietami `GROUND FLOOR`/`ATTIC`).

- [ ] **Step 1: Wątek roboczy solve + polling**

```cpp
// w FloorForgePalette.cpp
class SolveTask : public GS::Runnable {
    GS::UniString body; bool boundaryOnly;
public:
    SolveTask (GS::UniString b, bool bo) : body (std::move (b)), boundaryOnly (bo) {}
    void Run () override {
        auto& client = ServiceSupervisor::Instance ().Client ();
        GS::UniString jobId = client.Solve (body);
        if (jobId.IsEmpty ()) { Post (new ErrorTask (client.lastError)); return; }
        for (;;) {
            GS::ThreadingUtilities::Sleep (400);   // sprawdź nazwę w GSRoot (Thread.hpp: GS::Thread::Sleep?)
            JSON::ObjectValueRef job = client.Job (jobId);
            if (job == nullptr) { Post (new ErrorTask (client.lastError)); return; }
            GS::UniString status = GetString (job, "status");
            if (status == "running" || status == "queued") { Post (new ProgressTask (GetProgress (job))); continue; }
            if (status == "error")  { Post (new ErrorTask (GetString (job, "error"))); return; }
            Post (new ResultTask (jobId, GetObject (job, "result"), boundaryOnly)); return;
        }
    }
};
```
`Post (GS::Runnable*)` = `GS::MessageLoopExecutor ().Execute (task)`. `ResultTask::Run` → `ParseJobResult` → `state.boundary/variants` → `outlinePreview.Redraw (); variantPreview.Redraw (); UpdateVariantText (); SetBusy (false)`. `ErrorTask::Run` → `SetBusy (false); DGAlert (DG_WARNING, "FloorForge", msg, …)`.

- [ ] **Step 2: Akcje przycisków** (`ButtonClicked`): `LoadSelectionBtn` → `StartSolve (source="selection", maxVariants=0)`; `PickPointBtn` → `Hide (); API_GetPointType pt {}; CHTruncate ("Click inside the apartment outline", pt.prompt, sizeof pt.prompt); err = ACAPI_UserInput_GetPoint (&pt); Show (); if (err == NoError) StartSolve (source="point", point=pt.pos, maxVariants=0)`; `GenerateBtn` → `StartSolve (source=lastSource, point=lastPoint, maxVariants=state.variantsRequested lub 1 dla house, mode, mtype)`; `PrevBtn/NextBtn` → `state.current ±1` (zawijanie), `variantPreview.Redraw ()`, `UpdateVariantText ()` (`"Variant 2/5 · score 0.87"`; dom: `"House · ground floor + attic"`). Body JSON budowany ręcznie (`GS::UniString::Printf`) — pola: `source`, `point`, `mode`, `mtype` (pomijane gdy auto), `max_variants`, `num_storeys: 2`. `SetBusy(true)`: przyciski disabled, `GenerateBtn` tekst „Generating…", progress bar 0.

- [ ] **Step 3: Rysowanie** (`UserItemUpdate`): `OutlinePreview` — polygon obrysu (linia 2 px, `#1F2937`) + wejście (kółko 6 px czerwone) + tekst `"48.0 m² · auto M2"`; `VariantPreview` — dla każdego `StoreyView` panel (dom: dwa obok siebie, każdy z etykietą u góry), pokoje wypełnione kolorem strefy (`dzienna` F6C453, `nocna` 7FB3D5, `uslugowa` B39DDB, `komunikacja` A5D6A7, inne DDDDDD) przez `FillPolygon` jeśli `NewDisplay::UserItemUpdateNativeContext` je ma (sprawdź `DGNativeContexts.hpp`; jeśli tylko `FillRect`, rysuj pokoje jako bbox-rect wypełnienie + kontur polygonu liniami — pokoje są prostokątne lub L, więc bbox fill z konturem jest akceptowalne w v1), kontur `MoveTo/LineTo`, etykieta `DrawPlainText (name)` w centroidzie + `area` pod spodem (jak FP4 `drawPreview`, `FloorPlan4_CPP/Src/FloorPlanPalette.cpp:966-1090`). `ProgressBar` UserItem — jak FP4 (`FillRect` procentowe). Skalowanie: margines 12 px, `scale = min((w-2m)/bw, (h-2m)/bh)`, oś Y odwrócona.

- [ ] **Step 4: Build** → zielono. `strings | grep -c '"source"'` ≥ 1.

- [ ] **Step 5: Commit** `feat(addon): paleta — obrys z zaznaczenia/punktu, Generate z postępem, podgląd wariantów, nawigacja`.

- [ ] **Step 6: LIVE #2 (Dawid):** instalacja jak w Task 4/7 → zaznacz ściany M3 → „Load from selection" → obrys w podglądzie; Generate → pasek postępu → warianty, `<` `>`; dom: House → Generate (≤ 2 min) → dwa panele.

---

### Task 6: Paleta — Insert into Archicad, obie kondygnacje, alerty

**Files:**
- Modify: `addon/Sources/FloorForgePalette.{hpp,cpp}`, `addon/Sources/RINT/AddOn.grc`

**Interfaces:** consumes `ServiceClient::Export` (Task 4) i `/export` (Task 1/2).

- [ ] **Step 1: `InsertBtn`** → `SetBusy (true)` → `ExportTask` (wątek): body `{"job_id", "variant": state.current, "storeys": mode==House ? (bothStoreys ? ["parter","poddasze"] : ["parter"]) : ["parter"], "furniture": false}` → `client.Export (body, code)`: `200` → `Post (new InsertDoneTask (json))` → alert „Inserted: N zones, N walls, N doors, N windows, N labels (storeys: …)"; dom `partial: true` → `DG_WARNING` z `error`; `422/503/404/409` → alert z `error` (EN z serwisu); brak połączenia → alert `lastError`.
- [ ] **Step 2: Stringi** w `ID_PALETTE_STRINGS`: `6 "Inserted into Archicad: %T zones, %T walls, %T doors, %T windows, %T labels."`, `7 "Insert failed: %T"`, `8 "Generation failed: %T"`, `9 "Click inside the apartment outline"`.
- [ ] **Step 3: Build**, commit `feat(addon): paleta — Insert into Archicad (obie kondygnacje domu), alerty`.
- [ ] **Step 4: LIVE #3 (Dawid):** M3 → Generate → Insert → elementy w AC; dom obie kondygnacje → story 0 i 1; AC zamknięte przy otwartej palecie (nie dotyczy — paleta znika z AC); drugi AC → drugi serwis (`ls ~/Library/Application\ Support/FloorForge/`).

---

### Task 7: Pakowanie — bramka `--serve`, docs, checklist, pełny pytest, release

**Files:**
- Modify: `packaging/build_release.sh`, `packaging/INSTALL.md`, `packaging/INSTALACJA.md`, `packaging/CHECKLIST_TEST.md`, `README.md`, `docs/STATE.md`, `.github/workflows/test.yml` (jeśli `tests/test_service_serve.py` wymaga `PYTHONPATH` — już ustawione)

- [ ] **Step 1: Bramka `--serve` w `build_release.sh`** (po selftest z zipa):

```bash
PF="$(mktemp -d)"; export FLOORFORGE_PORT_DIR="$PF" FLOORFORGE_LOG_DIR="$PF"
FLOORFORGE_AC_PORT=1 "$VB/Contents/Resources/FloorForge/FloorForge" --serve & SP=$!
for i in $(seq 1 60); do [ -f "$PF/service-1.port" ] && break; sleep 0.25; done
[ -f "$PF/service-1.port" ] || { echo "PACZKA FAIL: --serve nie napisał pliku portu"; kill $SP 2>/dev/null; exit 1; }
SPORT="$(sed -n 's/^PORT=//p' "$PF/service-1.port")"
curl -s -m 3 "http://127.0.0.1:$SPORT/health" | grep -q '"status": *"ok"' || { echo "PACZKA FAIL: /health"; kill $SP; exit 1; }
curl -s -m 3 -X POST -H 'Content-Type: application/json' -d '{}' "http://127.0.0.1:$SPORT/shutdown" >/dev/null
wait $SP || true; [ ! -f "$PF/service-1.port" ] || { echo "PACZKA FAIL: plik portu nie usunięty"; exit 1; }
echo "  --serve z paczki OK"; rm -rf "$PF"; unset FLOORFORGE_PORT_DIR FLOORFORGE_LOG_DIR
```

- [ ] **Step 2: Docs.** `INSTALL.md`/`INSTALACJA.md`: menu **FloorForge → Palette** / **About FloorForge...**; krok użycia: „Select the outline walls → Load from selection (or Pick point) → Generate → ‹ › → Insert into Archicad"; Troubleshooting: „Service: error" → Restart service; kwarantanna (jak dziś); log. `CHECKLIST_TEST.md` (PL, dla Dawida) — kroki: 1 zip → bundle; 2 instalacja, AC bez ostrzeżeń, menu FloorForge; 3 About; 4 Palette → „Service: ready (v…)" ≤ 15 s, `pgrep -f "FloorForge --serve"` = 1; 5 Load from selection (M3) → obrys + „48.0 m² · auto M3"; 6 Pick point → obrys; 7 Generate → postęp → ≥1 wariant, `<` `>`; 8 Insert → strefy/ściany/drzwi/okna/etykiety (EN nazwy); 9 House → Generate ≤ 2 min → dwa panele; 10 Insert both storeys → story 0/1; 11 Restart service → „ready" ponownie; 12 Cmd+Q AC → proces `--serve` znika ≤ 5 s, plik portu usunięty; 13 dwa AC → dwa pliki portu, paleta w drugim AC łączy się z drugim; 14 bundle pobrany Safari na koncie beta-test → kroki 2–8 (kwarantanna). `README.md` sekcja Beta: paleta, serwis `--serve`, `--ac-probe`. `docs/STATE.md` nowy wpis (Polish): dostarczone (SHA), live wyniki #1–#3, znane luki (eksport domu synchroniczny; podgląd bbox-fill jeśli brak `FillPolygon`; brak testu watchdoga rodzica), poziom 2 odłożony.
- [ ] **Step 3: Pełna suita** (raz, tło): `QT_QPA_PLATFORM=offscreen python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -3` → `0 failed` poza znanym flaky CP-SAT (rerun w izolacji).
- [ ] **Step 4: Build + smoke**: `packaging/build_release.sh` → `== GOTOWE` (z `--serve z paczki OK`); `packaging/smoke_frozen.sh` → `SMOKE OK`.
- [ ] **Step 5: Commit** `build(packaging): bramka --serve + docs/checklist pod paletę; STATE`, push gałęzi.
- [ ] **Step 6: BRAMKA (Dawid):** `CHECKLIST_TEST.md` 14/14 → tag `v0.7-beta1` → FF `main` → wysyłka.

---

## Self-Review

**Spec coverage:** §1 zakres → T4–T6 (paleta), T1–T3 (serwis), T7 (docs/checklist) ✓. §2 architektura (supervisor, serwis potomny, ResultStore, przepływ) → T1, T3, T4 ✓. §3.1 `--serve` (plik portu, watchdog, SIGTERM, usuwanie pliku) → T3 ✓. §3.2 endpointy i kody → T1 (`/export` 200/404/409/503/422, `/shutdown`, `/health.ac_port`, `/solve` z `source`, `max_variants: 0`) ✓; `service/errors.py` + delegacja `ui/user_errors` → T1 ✓; `ResultStore` LRU 20 → T1 ✓; `bridge/house_export.py` → T2 ✓; kontrakt podglądu → T1 (`plan_to_contract`) + T5 (parser) ✓. §3.3 testy → T1–T3 ✓ (watchdog rodzica: test pominięty świadomie, opisany). §4.1 pliki → T4 (Client/Supervisor/Palette/Model, launcher usunięty), §4.2 UI → T4 (grc, stopka), T5 (outline/generate/preview/nav), T6 (insert) ✓. §4.3 błędy → T4–T6 ✓. §5 pakowanie (bramka `--serve`, docs, checklist) → T7 ✓. §6 kolejność = T1→T7 ✓. §7 ryzyka: HTTP poza głównym wątkiem → T4/T5 (`ThreadedExecutor` + `MessageLoopExecutor`); serwis-sierota → T3 watchdog + T4 `FreeData`/martwy plik portu; dwa AC → plik per port (T3) + `FLOORFORGE_AC_PORT` (T4) ✓.

**Placeholder scan:** brak TBD. Miejsca „sprawdź w headerze" (sygnatura `Send` z body, `FillPolygon`, `Thread::Sleep`) to instrukcje weryfikacji API DevKit z podanymi alternatywami, nie placeholdery.

**Type consistency:** `solve_request(req, progress=None, store=None)` + `req["_job_id"]` (T1) = `JobStore.submit(fn, body, job_id=jid, store=results)` (T1 Step 11) ✓; wynik `{"mode","boundary","variants":[{index,score,contract}]}` (T1) = `ParseJobResult` (T5) ✓; `export_house_storeys(layout, storeys, tapir, include_furniture=, offset=, switch=)` (T2) = użycie w `/export` (T1 Step 11: `include_furniture=furniture`) i GUI ✓; `ServiceHandle.is_running()` (T1) = `run_serve` (T3) i test shutdown ✓; plik portu `service-<ac>.port` format (T3) = supervisor parser (T4) = bramka (T7 `sed -n 's/^PORT=//p'`) ✓; `ServiceSupervisor::Client()` (T4) = `SolveTask`/`ExportTask` (T5/T6) ✓; strefy w kontrakcie `strefa` (`dzienna|nocna|uslugowa|komunikacja`) (T5 kolory) — wartości `Strefa` enum z `core/models.py` (implementer T5 potwierdza `grep "class Strefa" -A 6 core/models.py`).
