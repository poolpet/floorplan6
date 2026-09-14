# Beta dystrybucyjna FloorForge (macOS + AC29) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeden zip (`FloorForge.app` + custom Tapir + instrukcja), z którego znajomy architekt na macOS/AC29 przechodzi ścieżkę obrys z AC → warianty → wstaw do AC bez Pythona i bez konsoli.

**Architecture:** Mózg (core/, bridge/) bez zmian algorytmicznych. Nowy pakiet `service/` wystawia mózg jako lokalny serwer HTTP za kontraktem JSON (`core/plan_contract.py`) z jobami i postępem. GUI PyQt5 dostaje tryb beta (jedna zakładka, polskie komunikaty, pasek statusu AC, log na dysku). Nowy katalog `packaging/` mrozi aplikację PyInstallerem (onedir → `.app`, podpis ad-hoc) i składa zip.

**Tech Stack:** Python 3.13 (venv), OR-Tools 9.15, Shapely 2.1, PyQt5 5.15.11, matplotlib 3.10, `archicad` 29.3000, PyInstaller 6.x, stdlib `http.server`/`threading`/`logging`, `codesign`, `sips`/`iconutil` (macOS).

**Spec:** `docs/superpowers/specs/2026-09-14-beta-dystrybucja-macos-design.md`

**Odstępstwo od spec §2 (świadome, do potwierdzenia przez Dawida):** GUI w becie generuje i renderuje w procesie jak dziś (obiekty `FloorPlan`/`TwoStoreyLayout`). Serwis HTTP powstaje równolegle, jest ćwiczony przez testy i `--selftest`, i jest interfejsem dla przyszłej powłoki. Przepięcie GUI na klienta HTTP wymaga deserializacji kontrakt→render, której nie ma; to osobne zadanie po becie.

## Global Constraints

- Mózg zamrożony: zero zmian w `core/cpsat_solver.py`, `core/house_layout.py`, `core/house_program.py`, szablonach i regułach F1–F10 (spec §1, CLAUDE.md B3).
- Bez flagi `FLOORFORGE_BETA` okno i zachowanie GUI identyczne jak dziś (spec §3).
- Wszystkie nowe stringi widoczne dla użytkownika po polsku (spec §3, CLAUDE.md B10).
- Log: `~/Library/Logs/FloorForge/floorforge.log`, `RotatingFileHandler` 5 × 2 MB, poziom INFO, bez wysyłki sieciowej (spec §4).
- Serwer HTTP nasłuchuje wyłącznie na `127.0.0.1`, losowy wolny port (spec §2).
- Nowe zależności runtime: żadne (stdlib). PyInstaller tylko w `packaging/`.
- Każdy task kończy się zielonym `pytest` dla dotkniętych plików + `tests/test_gui.py` gdy dotknięte `ui/` (CLAUDE.md B8).
- Uruchamianie testów: `cd FloorPlan6 && source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest <pliki> -q -p no:cacheprovider`.
- Commity po polsku, prefiksy `feat/fix/chore/docs/test`, stopka `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` + `Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8`.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `service/__init__.py` | pusty |
| `service/jobs.py` | `JobStore`: uruchamianie solve'ów w wątkach, postęp, wyniki częściowe, status |
| `service/app.py` | serwer HTTP (stdlib): `/health`, `/solve`, `/jobs/{id}`, `/export`; `start_server()` |
| `service/client.py` | `ServiceClient` (urllib) do `--selftest` i przyszłych powłok |
| `service/solve_adapter.py` | mapowanie żądania JSON → `generate_variants` / `generate_house` → kontrakt JSON |
| `ui/user_errors.py` | `describe(exc) -> (tytuł, treść)` — polskie komunikaty z wyjątków |
| `ui/app_logging.py` | `setup_logging() -> Path` — plik logu z rotacją |
| `ui/ac_status_widget.py` | `AcStatusWidget` — port, projekt, kondygnacja, „Odśwież" |
| `ui/main_window.py` | tryb beta (`_build_ui`), wpięcie `describe`/logu w `_on_error` i eksportach, „Wstaw cały dom" |
| `bridge/tapir_connection.py` | `story_navitems()`, `activate_story()` |
| `floorforge_app.py` | entry point zamrożonej aplikacji: flaga beta, log, `--selftest`, `run_gui()` |
| `packaging/floorforge.spec` | PyInstaller onedir → `.app` |
| `packaging/requirements-lock.txt` | zamrożone wersje |
| `packaging/build_release.sh` | build + podpis + zip |
| `packaging/smoke_frozen.sh` | `--selftest` na zamrożonej binarce |
| `packaging/make_icon.py` | PNG → `icon.icns` |
| `packaging/INSTALACJA.md`, `packaging/Uruchom.command` | dla użytkownika |
| `packaging/CHECKLIST_TEST.md` | test ręczny na czystym koncie |
| `tests/test_service_jobs.py`, `tests/test_service_app.py`, `tests/test_solve_adapter.py`, `tests/test_user_errors.py`, `tests/test_app_logging.py`, `tests/test_beta_mode.py`, `tests/test_ac_status_widget.py`, `tests/test_ac_targeting.py` (rozszerzenie), `tests/test_house_export_gui.py` (rozszerzenie), `tests/test_selftest.py` | testy |

---

### Task 0: Higiena repo — duplikaty, tag, push, README

**Files:**
- Delete: 27 plików `* 2.py` / `* 2.json` w `notebooks/` i `tests/` (lista niżej)
- Modify: `README.md` (tabela „What works today")

**Interfaces:** brak.

- [ ] **Step 1: Potwierdź, że duplikaty są identyczne z oryginałami (nie tracimy pracy)**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
for f in notebooks/*" 2."* tests/*" 2."*; do
  orig="${f/ 2./.}"
  if [ -f "$orig" ]; then
    cmp -s "$f" "$orig" && echo "IDENT  $f" || echo "DIFF   $f"
  else
    echo "NOORIG $f"
  fi
done
```

Oczekiwane: same linie `IDENT`. Jeśli jakiś `DIFF`/`NOORIG` → `diff` i pokaż Dawidowi przed usunięciem; nie usuwaj.

- [ ] **Step 2: Usuń duplikaty i cache**

```bash
find notebooks tests -name "* 2.*" -not -path "*/__pycache__/*" -print -delete
find tests/__pycache__ -name "* 2.*" -delete
git status --short | grep -c '" 2\.' ; echo "(oczekiwane 0)"
```

- [ ] **Step 3: Pełny pytest (potwierdzenie bazy). Czas ~30 min; uruchom w tle.**

```bash
source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest tests -q -p no:cacheprovider --deselect tests/test_subdivision_600_800.py 2>&1 | tail -5
```

Oczekiwane: `0 failed` (skipped/xpassed dopuszczalne). Znane flaki: `11×11 single-storey` (UNKNOWN@25s) — powtórz w izolacji przed uznaniem za regresję.

- [ ] **Step 4: README — zaktualizuj tabelę stanu**

W `README.md` zamień wiersze tabeli „What works today":

```markdown
| 1. Plot subdivision | `core/plot_subdivider.py` | ✅ MVP (Mode A + Mode B, PDF report) — **frozen** since 2026-05-31 |
| 2. Volumetric generator | — | ⏸️ dropped from roadmap (see `docs/ROADMAP_domy.md`) |
| 3. Floor layout | `core/floor_layout.py` | ✅ MVP for rectangular floors — frozen |
| 4. Apartment + house layout | `core/cpsat_solver.py`, `core/house_layout.py` | ✅ apartments M1–M5, houses (single/2-storey) with furniture, export to AC (zones, walls, doors, windows, labels) |
```

- [ ] **Step 5: Commit, tag, push**

```bash
git add -A notebooks tests README.md
git commit -m "chore: usunięcie duplikatów Findera (* 2.py), README stan etapów

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
git tag -a v0.6-baseline -m "Baseline przed betą dystrybucyjną (2026-09-14)"
git push origin main --tags
git status -sb | head -1   # oczekiwane: ## main...origin/main (bez ahead)
```

---

### Task 1: Dom → AC jednym klikiem (auto-switch kondygnacji) — z bramką live

> Kontynuacja `docs/superpowers/plans/2026-06-22-dom-ac-story-target-multi-instance.md` Task 3. Kształt parametru `ChangeWindow` nie jest znany offline; implementacja próbuje listy kształtów (jak `notebooks/ac_story_switch_probe.py`) i zapamiętuje zwycięzcę. Bramka: Dawid przy AC.

**Files:**
- Modify: `bridge/tapir_connection.py` (po `get_project_info`, ~linia 168)
- Modify: `ui/main_window.py:1101-1178` (`_export_house_to_archicad`)
- Test: `tests/test_ac_targeting.py`, `tests/test_house_export_gui.py`

**Interfaces:**
- Produces: `TapirConnection.story_navitems() -> dict[int, str]`, `TapirConnection.activate_story(target_index: int) -> bool`, `TapirConnection.CHANGE_WINDOW_SHAPES: list[tuple[str, Callable[[str], dict]]]`.
- GUI: nowy checkbox `self.house_both_storeys_check` („Wstaw obie kondygnacje (auto-przełączanie)") obok `house_storey_combo`.

- [ ] **Step 1: Failing tests — `story_navitems` i `activate_story`**

Dopisz do `tests/test_ac_targeting.py`:

```python
class _FakeNav:
    """Minimalny obiekt drzewa nawigatora: StoryItem'y top-down (Poddasze, Parter)."""
    def __init__(self, guids_top_down):
        self.rootItem = self
        self.type = "Root"
        self.navigatorItemId = None
        self.children = [
            type("N", (), {"navigatorItem": type("I", (), {
                "type": "StoryItem",
                "navigatorItemId": type("G", (), {"guid": g})(),
                "children": [],
            })()})()
            for g in guids_top_down
        ]


def _conn_with_stories(monkeypatch, act_story_seq):
    """TapirConnection z podmienionym połączeniem: GetStories zwraca kolejne actStory z listy."""
    import bridge.tapir_connection as tc
    conn = tc.TapirConnection()
    calls = {"change_window": []}
    seq = list(act_story_seq)

    class _Cmds:
        def GetNavigatorItemTree(self, tid):
            return _FakeNav(["guid-poddasze", "guid-parter"])
        def ExecuteAddOnCommand(self, cid, params):
            name = cid.name if hasattr(cid, "name") else str(cid)
            if "GetStories" in name:
                return {"actStory": seq[0] if len(seq) == 1 else seq.pop(0),
                        "firstStory": 0, "lastStory": 1}
            if "ChangeWindow" in name:
                calls["change_window"].append(params)
                return {}
            return {}

    class _Types:
        def NavigatorTreeId(self, type):
            return ("tree", type)
        def AddOnCommandId(self, ns, name):
            return type("Cid", (), {"name": name})()

    monkeypatch.setattr(conn, "_conn", type("C", (), {"commands": _Cmds(), "types": _Types()})(), raising=False)
    return conn, calls


def test_story_navitems_maps_index_to_guid_bottom_up(monkeypatch):
    conn, _ = _conn_with_stories(monkeypatch, [0])
    assert conn.story_navitems() == {0: "guid-parter", 1: "guid-poddasze"}


def test_activate_story_true_when_act_story_changes(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [0, 1])   # przed: 0, po ChangeWindow: 1
    assert conn.activate_story(1) is True
    assert calls["change_window"], "ChangeWindow powinno być wywołane"
    assert calls["change_window"][0]["navigatorItemId"]["guid"] == "guid-poddasze"


def test_activate_story_false_when_no_shape_switches(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [0])      # actStory nigdy się nie zmienia
    assert conn.activate_story(1) is False
    assert len(calls["change_window"]) == len(conn.CHANGE_WINDOW_SHAPES)


def test_activate_story_noop_when_already_active(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [1])
    assert conn.activate_story(1) is True
    assert calls["change_window"] == []
```

Sprawdź nazwę atrybutu połączenia w `TapirConnection.__init__` (grep `self._conn` / `self.conn`) i dopasuj `monkeypatch.setattr(conn, "<nazwa>", ...)` oraz to, czego używają `commands`/`types` property (linie 174–190).

- [ ] **Step 2: Run → FAIL**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ac_targeting.py -q -p no:cacheprovider -k "navitems or activate_story"
```

Oczekiwane: `AttributeError: 'TapirConnection' object has no attribute 'story_navitems'`.

- [ ] **Step 3: Implementacja w `bridge/tapir_connection.py`**

Dopisz w klasie `TapirConnection` (po `get_project_info`):

```python
    # Kandydaci na kształt param ChangeWindow (kolejność = notebooks/ac_story_switch_probe.py).
    # Zwycięzca z live-testu przesuwany na początek listy.
    CHANGE_WINDOW_SHAPES = [
        ("navigatorItemId:{guid}",      lambda g: {"navigatorItemId": {"guid": g}}),
        ("navigatorItemId:{guid,type}", lambda g: {"navigatorItemId": {"guid": g, "type": "StoryItem"}}),
        ("{guid}",                      lambda g: {"guid": g}),
        ("databaseId+FloorPlan",        lambda g: {"databaseId": {"guid": g}, "windowType": "FloorPlan"}),
    ]

    def story_navitems(self) -> dict[int, str]:
        """idx kondygnacji → navigatorItemId.guid. ProjectMap listuje story top-down,
        więc reversed = indeksy rosnące (Parter = 0)."""
        tree_id = self.types.NavigatorTreeId(type="ProjectMap")
        tree = self.commands.GetNavigatorItemTree(tree_id)
        guids_top_down: list[str] = []

        def walk(node):
            item = getattr(node, "navigatorItem", node)
            nid = getattr(getattr(item, "navigatorItemId", None), "guid", None)
            if getattr(item, "type", None) == "StoryItem" and nid:
                guids_top_down.append(str(nid))
            for ch in (getattr(item, "children", None) or []):
                walk(ch)

        walk(getattr(tree, "rootItem", tree))
        return {i: g for i, g in enumerate(reversed(guids_top_down))}

    def activate_story(self, target_index: int) -> bool:
        """Ustaw aktywną kondygnację AC na `target_index`. True gdy GetStories.actStory == target."""
        st = self.get_stories() or {}
        if int(st.get("actStory", -1)) == target_index:
            return True
        guid = self.story_navitems().get(target_index)
        if guid is None:
            logger.warning("activate_story: brak nav-itemu dla story %s", target_index)
            return False
        for label, build in self.CHANGE_WINDOW_SHAPES:
            try:
                self._tapir("ChangeWindow", build(guid))
            except Exception as e:
                logger.info("activate_story: kształt %s odrzucony: %r", label, e)
                continue
            now = int((self.get_stories() or {}).get("actStory", -1))
            if now == target_index:
                logger.info("activate_story: OK kształt=%s → actStory=%s", label, now)
                return True
        logger.warning("activate_story: żaden kształt nie przełączył na %s", target_index)
        return False
```

Sprawdź istniejący helper do komend Tapira (grep `AddOnCommandId(` w pliku) i użyj go zamiast `self._tapir`, jeśli nazywa się inaczej. Upewnij się, że na górze pliku jest `logger = logging.getLogger(__name__)`.

- [ ] **Step 4: Run → PASS**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_ac_targeting.py -q -p no:cacheprovider
```

- [ ] **Step 5: Failing test GUI — „obie kondygnacje"**

Dopisz do `tests/test_house_export_gui.py`:

```python
def test_house_export_both_storeys_switches_and_exports_twice(qapp, monkeypatch):
    """Checkbox 'obie' → activate_story(0)+export parter, activate_story(1)+export poddasze."""
    import bridge.tapir_connection as tc
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    switched = []
    monkeypatch.setattr(tc.TapirConnection, "activate_story",
                        lambda self, i: switched.append(i) or True)
    w = _mainwindow(monkeypatch, "Parter")
    w._house_layout = type("L", (), {"pietro_rooms": [object()]})()   # 2-kond.
    w.house_both_storeys_check.setChecked(True)
    w._export_to_archicad()
    assert switched == [0, 1]
    assert cap["export"] == 2


def test_house_export_both_storeys_falls_back_to_guard_when_switch_fails(qapp, monkeypatch):
    """activate_story False → NIE eksportuje na ślepo; pokazuje ostrzeżenie."""
    from PyQt5.QtWidgets import QMessageBox
    import bridge.tapir_connection as tc
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    monkeypatch.setattr(tc.TapirConnection, "activate_story", lambda self, i: False)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a) or QMessageBox.Cancel))
    w = _mainwindow(monkeypatch, "Parter")
    w._house_layout = type("L", (), {"pietro_rooms": [object()]})()
    w.house_both_storeys_check.setChecked(True)
    w._export_to_archicad()
    assert cap["export"] == 0
    assert warned
```

Uwaga: `_wire` wymaga `cap["export"]` liczonego per wywołanie — już tak jest.

- [ ] **Step 6: Run → FAIL** (`AttributeError: house_both_storeys_check`).

- [ ] **Step 7: Implementacja GUI**

W `_build_ui` obok `self.house_storey_combo` (grep `house_storey_combo` w `_build_ui`) dodaj:

```python
        self.house_both_storeys_check = QCheckBox("Wstaw obie kondygnacje (auto-przełączanie w AC)")
        self.house_both_storeys_check.setChecked(False)
        <ten_sam_layout>.addWidget(self.house_both_storeys_check)
```

W `_export_house_to_archicad` zastąp blok od komentarza `# 3. Story-guard` do końca `try` tym:

```python
            both = self.house_both_storeys_check.isChecked() and bool(getattr(layout, "pietro_rooms", None))
            st = tapir.get_stories() or {}
            first = int(st.get("firstStory", 0))
            plan_storeys = [("parter", first), ("poddasze", first + 1)] if both else [(storey, None)]

            totals = {"zones": 0, "walls": 0, "doors": 0, "windows": 0, "labels": 0}
            for st_name, target_idx in plan_storeys:
                if target_idx is not None:
                    if not tapir.activate_story(target_idx):
                        QMessageBox.warning(
                            self, "Kondygnacja AC",
                            f"Nie udało się automatycznie przełączyć AC na kondygnację {target_idx} "
                            f"('{st_name}').\n\nPrzełącz kondygnację ręcznie w AC, odznacz "
                            f"'Wstaw obie kondygnacje' i wstaw każdą osobno.",
                        )
                        return
                else:
                    ok, msg = check_active_story(
                        int(st.get("actStory", 0)), first, int(st.get("lastStory", 0)), st_name,
                    )
                    if not ok:
                        reply = QMessageBox.warning(
                            self, "Kondygnacja AC", f"{msg}\n\nWstawić MIMO TO?",
                            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
                        )
                        if reply != QMessageBox.Yes:
                            return
                result = export_house_to_archicad(
                    layout, storey=st_name, tapir=tapir, offset=self._archicad_offset,
                )
                for k in totals:
                    totals[k] += len(result.get(k, []))

            done = ", ".join(s for s, _ in plan_storeys)
            self.statusBar().showMessage(
                f"Dom [{done}] → port {port} ({name}): {totals['zones']} stref + {totals['walls']} ścian "
                f"+ {totals['doors']} drzwi + {totals['windows']} okien + {totals['labels']} etykiet"
            )
            QMessageBox.information(
                self, "ArchiCAD",
                f"Kondygnacje: {done} → {name} (port {port}):\n\n"
                f"{totals['zones']} stref + {totals['walls']} ścianek + {totals['doors']} drzwi "
                f"+ {totals['windows']} okien + {totals['labels']} etykiet."
                + ("" if both else "\n\nDruga kondygnacja: przełącz kondygnację w AC, wybierz ją tutaj, kliknij ponownie."),
            )
```

- [ ] **Step 8: Run → PASS + regresja**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_house_export_gui.py tests/test_ac_targeting.py tests/test_house_writer.py tests/test_gui.py -q -p no:cacheprovider
```

- [ ] **Step 9: Commit**

```bash
git add bridge/tapir_connection.py ui/main_window.py tests/test_ac_targeting.py tests/test_house_export_gui.py
git commit -m "feat(bridge+ui): activate_story (ChangeWindow, lista kształtów) + 'Wstaw obie kondygnacje'

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

- [ ] **Step 10: BRAMKA LIVE (Dawid przy AC, AC bezczynny, projekt 2-kond.)**

1. `PYTHONPATH=. venv/bin/python notebooks/ac_story_switch_probe.py` → wklej output. Jeśli `ZWYCIĘZCA` ≠ pierwszy kształt, przesuń zwycięzcę na początek `CHANGE_WINDOW_SHAPES` (commit `fix(bridge): kolejność kształtów ChangeWindow wg live`).
2. GUI: tryb Dom → generuj → zaznacz „Wstaw obie kondygnacje" → Wstaw do AC.
3. `PYTHONPATH=. venv/bin/python notebooks/ac_story_diag.py` → DOM-PARTER-* na story 0, DOM-PODDASZE-* na story 1, ten sam port.
4. Jeśli żaden kształt nie działa: zgłoś; alternatywa to retarget przez `SetDetailsOfElements.floorIndex` po eksporcie (ten sam interfejs `activate_story`, inna implementacja) — osobny mini-plan.

---

### Task 2: `service/` — adapter solve → kontrakt

**Files:**
- Create: `service/__init__.py`, `service/solve_adapter.py`
- Test: `tests/test_solve_adapter.py`

**Interfaces:**
- Produces: `solve_request(req: dict, progress=None) -> dict` gdzie `req = {"mode": "apartment"|"house", "polygon": [[x,y],...], "entry": [x,y], "mtype": "M2", "max_variants": 5, "min_score": 0.0, "template_filter": null|[...], "num_storeys": 2}`; wynik `{"mode":..., "variants": [contract, ...]}` dla apartment (`plan_to_contract(plan.rooms, plan.boundary, storey="single", template=plan.template)` + `"score"`), `{"mode":"house", "layout": house_to_contract(layout)}` dla house; `progress(current, total)` przekazywany do `generate_variants`.
- Błędy wejścia → `ValueError` z polskim komunikatem.

- [ ] **Step 1: Failing tests**

```python
# tests/test_solve_adapter.py
import pytest
from shapely.geometry import Polygon


def test_apartment_request_returns_contracts(monkeypatch):
    import service.solve_adapter as sa
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan
    from core.template_selector import load_all_templates

    tpl = next(t for t in load_all_templates() if t.id == "M2_standard")
    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    fake_plan = FloorPlan(boundary=analyze_boundary(poly, (4.0, 0.0)), template=tpl, rooms=[], score=0.9)
    seen = {}

    def fake_generate(polygon, entry_point, mtype, max_variants, progress_callback=None, **kw):
        seen.update(mtype=mtype, max_variants=max_variants, kw=kw)
        if progress_callback:
            progress_callback(1, 1)
        return [fake_plan]

    monkeypatch.setattr(sa, "generate_variants", fake_generate)
    ticks = []
    out = sa.solve_request(
        {"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0],
         "mtype": "M2", "max_variants": 3},
        progress=lambda c, t: ticks.append((c, t)),
    )
    assert out["mode"] == "apartment"
    assert len(out["variants"]) == 1
    assert out["variants"][0]["score"] == 0.9
    assert "rooms" in out["variants"][0] and "walls" in out["variants"][0]
    assert seen["mtype"] == "M2" and seen["max_variants"] == 3
    assert ticks == [(1, 1)]


def test_house_request_returns_layout_contract(monkeypatch):
    import service.solve_adapter as sa
    called = {}
    monkeypatch.setattr(sa, "generate_house", lambda p, e, **kw: called.setdefault("kw", kw) or "LAYOUT")
    monkeypatch.setattr(sa, "house_to_contract", lambda layout: {"parter": {"rooms": []}, "_src": layout})
    out = sa.solve_request({"mode": "house", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]],
                            "entry": [5, 0], "num_storeys": 2})
    assert out["mode"] == "house"
    assert out["layout"]["_src"] == "LAYOUT"
    assert called["kw"]["num_storeys"] == 2


@pytest.mark.parametrize("bad", [
    {"mode": "apartment", "entry": [0, 0], "mtype": "M2"},                      # brak polygon
    {"mode": "apartment", "polygon": [[0, 0], [1, 0]], "entry": [0, 0], "mtype": "M2"},  # <3 pkt
    {"mode": "xyz", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0]},      # zły mode
    {"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0], "mtype": "M9"},
])
def test_invalid_request_raises_value_error(bad):
    import service.solve_adapter as sa
    with pytest.raises(ValueError):
        sa.solve_request(bad)
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: service`).

- [ ] **Step 3: Implementacja**

```python
# service/__init__.py
"""FloorForge — mózg jako lokalny serwis HTTP (kontrakt JSON, patrz core/plan_contract.py)."""
```

```python
# service/solve_adapter.py
"""Żądanie JSON → generate_variants / generate_house → kontrakt JSON."""
from __future__ import annotations

from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.plan_contract import house_to_contract, plan_to_contract
from core.variant_generator import generate_variants

APARTMENT_TYPES = ("M1", "M2", "M3", "M4", "M5")


def _polygon(req: dict) -> Polygon:
    pts = req.get("polygon")
    if not isinstance(pts, list) or len(pts) < 3:
        raise ValueError("Obrys musi mieć co najmniej 3 punkty (pole 'polygon').")
    try:
        poly = Polygon([(float(x), float(y)) for x, y in pts])
    except (TypeError, ValueError):
        raise ValueError("Punkty obrysu muszą być parami liczb [x, y].")
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("Obrys jest niepoprawny (samoprzecięcia lub zerowe pole).")
    return poly


def _entry(req: dict) -> tuple[float, float]:
    e = req.get("entry")
    if not isinstance(e, (list, tuple)) or len(e) != 2:
        raise ValueError("Punkt wejścia 'entry' musi być parą [x, y].")
    return float(e[0]), float(e[1])


def solve_request(req: dict, progress=None) -> dict:
    mode = req.get("mode")
    if mode not in ("apartment", "house"):
        raise ValueError("Pole 'mode' musi być 'apartment' albo 'house'.")
    poly, entry = _polygon(req), _entry(req)

    if mode == "house":
        layout = generate_house(poly, entry, num_storeys=int(req.get("num_storeys", 2)))
        return {"mode": "house", "layout": house_to_contract(layout)}

    mtype = req.get("mtype")
    if mtype not in APARTMENT_TYPES:
        raise ValueError(f"Typ mieszkania musi być jednym z {', '.join(APARTMENT_TYPES)}.")
    plans = generate_variants(
        poly, entry, mtype, int(req.get("max_variants", 5)),
        progress_callback=progress,
        template_filter=req.get("template_filter"),
        min_score=float(req.get("min_score", 0.0)),
    )
    variants = []
    for p in plans:
        c = plan_to_contract(p.rooms, p.boundary, storey="single", template=p.template)
        c["score"] = p.score
        c["validation_errors"] = list(p.validation_errors)
        variants.append(c)
    return {"mode": "apartment", "variants": variants}
```

Jeśli `generate_house` przy `num_storeys` wymaga innego wywołania (sprawdź sygnaturę w `core/house_layout.py:390`), dopasuj.

- [ ] **Step 4: Run → PASS**

```bash
python -m pytest tests/test_solve_adapter.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```bash
git add service tests/test_solve_adapter.py
git commit -m "feat(service): solve_adapter — żądanie JSON → kontrakt (apartment/house)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 3: `service/jobs.py` — joby z postępem i wynikami częściowymi

**Files:**
- Create: `service/jobs.py`
- Test: `tests/test_service_jobs.py`

**Interfaces:**
- Produces: `JobStore.submit(fn, *args, **kwargs) -> str` (job_id), `JobStore.get(job_id) -> dict | None` o kształcie `{"id", "status": "queued"|"running"|"done"|"error", "progress": {"current": int, "total": int}, "result": dict|None, "error": str|None}`. `fn` otrzymuje kwarg `progress` (callable `(current, total)`).

- [ ] **Step 1: Failing tests**

```python
# tests/test_service_jobs.py
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
    assert j["error"] == "zły obrys" and j["result"] is None


def test_unknown_job_is_none():
    from service.jobs import JobStore
    assert JobStore().get("nope") is None
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implementacja**

```python
# service/jobs.py
"""Proste joby w wątkach: status, postęp, wynik. Bez kolejki — beta = 1 użytkownik."""
from __future__ import annotations

import copy
import logging
import threading
import uuid

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, fn, *args, **kwargs) -> str:
        jid = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[jid] = {"id": jid, "status": "queued",
                               "progress": {"current": 0, "total": 0},
                               "result": None, "error": None}

        def progress(current, total):
            with self._lock:
                self._jobs[jid]["progress"] = {"current": int(current), "total": int(total)}

        def run():
            with self._lock:
                self._jobs[jid]["status"] = "running"
            try:
                result = fn(*args, progress=progress, **kwargs)
                with self._lock:
                    self._jobs[jid].update(status="done", result=result)
            except Exception as e:
                logger.exception("job %s: błąd", jid)
                with self._lock:
                    self._jobs[jid].update(status="error", error=str(e))

        threading.Thread(target=run, name=f"job-{jid}", daemon=True).start()
        return jid

    def get(self, jid: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(jid)
            return copy.deepcopy(j) if j else None
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** `feat(service): JobStore — joby z postępem i statusem`.

---

### Task 4: `service/app.py` — serwer HTTP (stdlib) + `service/client.py`

**Files:**
- Create: `service/app.py`, `service/client.py`
- Test: `tests/test_service_app.py`

**Interfaces:**
- Produces: `start_server(host="127.0.0.1", port=0, job_store=None) -> ServiceHandle` z `.port`, `.url`, `.stop()`. Endpointy: `GET /health → {"status":"ok","version":str}`, `POST /solve` (body = req z Task 2) `→ 202 {"job_id": str}`, `GET /jobs/{id} → 200 job dict | 404`, `POST /export` (body `{"contract": {...}, "port": int|null}`) `→ 200 {"zones":n,...}` lub `503` gdy brak AC. Błędne JSON/ValueError → `400 {"error": "..."}`.
- `ServiceClient(url)`: `.health()`, `.solve(req) -> job_id`, `.job(job_id) -> dict`, `.wait(job_id, timeout=120.0, poll=0.2) -> dict` (rzuca `RuntimeError(error)` przy `status=="error"`).
- Wersja: `service.app.VERSION` = z env `FLOORFORGE_VERSION` lub `"dev"`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_service_app.py
import json
import urllib.request
import urllib.error
import pytest


@pytest.fixture
def server(monkeypatch):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: (progress and progress(1, 1)) or {"mode": req["mode"], "variants": []})
    h = app.start_server(port=0)
    yield h
    h.stop()


def _post(url, body):
    data = json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(r, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


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


def test_unknown_job_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(f"{server.url}/jobs/xyz", timeout=5)
    assert ei.value.code == 404


def test_export_without_archicad_is_503(server, monkeypatch):
    import service.app as app
    monkeypatch.setattr(app, "export_contract",
                        lambda contract, port=None: (_ for _ in ()).throw(ConnectionError("brak AC")))
    r = urllib.request.Request(f"{server.url}/export", data=json.dumps({"contract": {}}).encode(),
                               headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(r, timeout=5)
    assert ei.value.code == 503


def test_client_wait_raises_on_error(server, monkeypatch):
    import service.app as app
    from service.client import ServiceClient
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: (_ for _ in ()).throw(ValueError("zły obrys")))
    c = ServiceClient(server.url)
    jid = c.solve({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0], "mtype": "M2"})
    with pytest.raises(RuntimeError, match="zły obrys"):
        c.wait(jid, timeout=5)
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implementacja `service/app.py`**

```python
# service/app.py
"""Lokalny serwer HTTP mózgu FloorForge. Tylko 127.0.0.1. Stdlib — zero nowych zależności."""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from service.jobs import JobStore
from service.solve_adapter import solve_request

logger = logging.getLogger(__name__)
VERSION = os.environ.get("FLOORFORGE_VERSION", "dev")


def export_contract(contract: dict, port: int | None = None) -> dict:
    """Eksport kontraktu do AC. Beta: GUI eksportuje w procesie (plan_writer); ten endpoint
    jest dla przyszłych powłok. Wymaga uruchomionego AC — inaczej ConnectionError."""
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    ok = tapir.use_port(port) if port else tapir.connect()
    if not ok:
        raise ConnectionError("Nie znaleziono ArchiCADa z dodatkiem Tapir.")
    raise NotImplementedError("Eksport z kontraktu JSON: po becie (GUI eksportuje z obiektów).")


class _Handler(BaseHTTPRequestHandler):
    store: JobStore = None  # ustawiane w start_server

    def log_message(self, fmt, *args):
        logger.debug("http: " + fmt, *args)

    def _json(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Treść żądania nie jest poprawnym JSON.")
        if not isinstance(body, dict):
            raise ValueError("Treść żądania musi być obiektem JSON.")
        return body

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"status": "ok", "version": VERSION})
        if self.path.startswith("/jobs/"):
            job = self.store.get(self.path[len("/jobs/"):])
            return self._json(200, job) if job else self._json(404, {"error": "Nieznany job."})
        self._json(404, {"error": "Nieznana ścieżka."})

    def do_POST(self):
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        if self.path == "/solve":
            jid = self.store.submit(solve_request, body)
            return self._json(202, {"job_id": jid})
        if self.path == "/export":
            try:
                return self._json(200, export_contract(body.get("contract") or {}, body.get("port")))
            except ConnectionError as e:
                return self._json(503, {"error": str(e)})
            except NotImplementedError as e:
                return self._json(501, {"error": str(e)})
        self._json(404, {"error": "Nieznana ścieżka."})


class ServiceHandle:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self._server, self._thread = server, thread
        self.port = server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_server(host: str = "127.0.0.1", port: int = 0, job_store: JobStore | None = None) -> ServiceHandle:
    handler = type("Handler", (_Handler,), {"store": job_store or JobStore()})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, name="floorforge-service", daemon=True)
    t.start()
    logger.info("service: nasłuch %s:%s (wersja %s)", host, server.server_address[1], VERSION)
    return ServiceHandle(server, t)
```

`service/client.py`:

```python
# service/client.py
"""Minimalny klient HTTP mózgu (urllib). Używany przez --selftest i przyszłe powłoki."""
from __future__ import annotations

import json
import time
import urllib.request


class ServiceClient:
    def __init__(self, url: str, timeout: float = 10.0):
        self.url, self.timeout = url.rstrip("/"), timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        r = urllib.request.Request(self.url + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> dict:
        return self._req("GET", "/health")

    def solve(self, req: dict) -> str:
        return self._req("POST", "/solve", req)["job_id"]

    def job(self, job_id: str) -> dict:
        return self._req("GET", f"/jobs/{job_id}")

    def wait(self, job_id: str, timeout: float = 120.0, poll: float = 0.2) -> dict:
        t0 = time.time()
        while True:
            j = self.job(job_id)
            if j["status"] == "done":
                return j
            if j["status"] == "error":
                raise RuntimeError(j["error"])
            if time.time() - t0 > timeout:
                raise TimeoutError(f"Job {job_id} nie skończył się w {timeout:.0f} s.")
            time.sleep(poll)
```

- [ ] **Step 4: Run → PASS**

```bash
python -m pytest tests/test_service_app.py tests/test_service_jobs.py tests/test_solve_adapter.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit** `feat(service): serwer HTTP (health/solve/jobs/export) + klient`.

---

### Task 5: `ui/user_errors.py` + `ui/app_logging.py` + wpięcie w GUI

**Files:**
- Create: `ui/user_errors.py`, `ui/app_logging.py`
- Modify: `ui/main_window.py:753-759` (`_on_error`), `1049-1082` (`_export_to_archicad` except), `1101-1178` (`_export_house_to_archicad` excepty), `1255+` (`_import_from_archicad` except — grep `except` w tej metodzie)
- Test: `tests/test_user_errors.py`, `tests/test_app_logging.py`

**Interfaces:**
- Produces: `describe(exc: BaseException) -> tuple[str, str]` (tytuł, treść po polsku, treść kończy się linią `Szczegóły techniczne: <repr skrócony do 200 znaków>`); `setup_logging(app_name="FloorForge") -> Path` (idempotentne; zwraca ścieżkę logu; respektuje env `FLOORFORGE_LOG_DIR` — testy); `log_path() -> Path | None`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_user_errors.py
import pytest


@pytest.mark.parametrize("exc, expect_title, expect_frag", [
    (ConnectionRefusedError("[Errno 61] Connection refused"), "ArchiCAD", "Uruchom AC"),
    (ConnectionError("Nie znaleziono ArchiCADa"), "ArchiCAD", "Uruchom AC"),
    (TimeoutError("timed out"), "ArchiCAD", "nie odpowiada"),
    (RuntimeError("INFEASIBLE"), "Brak układu", "Spróbuj inny typ"),
    (ValueError("Obrys musi mieć co najmniej 3 punkty"), "Dane wejściowe", "co najmniej 3 punkty"),
    (KeyError("libraryPart"), "Dodatek Tapir", "Zainstaluj bundle z paczki FloorForge"),
    (ZeroDivisionError("x"), "Nieoczekiwany błąd", "Szczegóły techniczne"),
])
def test_describe_maps_to_polish(exc, expect_title, expect_frag):
    from ui.user_errors import describe
    title, text = describe(exc)
    assert title == expect_title
    assert expect_frag in text
    assert "Szczegóły techniczne:" in text


def test_describe_truncates_long_repr():
    from ui.user_errors import describe
    _, text = describe(RuntimeError("x" * 1000))
    assert len(text.split("Szczegóły techniczne:")[1]) < 260
```

```python
# tests/test_app_logging.py
import logging


def test_setup_logging_creates_rotating_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_LOG_DIR", str(tmp_path))
    import importlib
    import ui.app_logging as al
    importlib.reload(al)
    p = al.setup_logging()
    logging.getLogger("floorforge.test").info("hello")
    for h in logging.getLogger().handlers:
        h.flush()
    assert p == tmp_path / "floorforge.log"
    assert "hello" in p.read_text(encoding="utf-8")
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1 and handlers[0].maxBytes == 2 * 1024 * 1024 and handlers[0].backupCount == 5
    assert al.setup_logging() == p           # idempotentne — nie dubluje handlerów
    assert len([h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]) == 1
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implementacja**

```python
# ui/user_errors.py
"""Wyjątek → (tytuł, treść) po polsku. Jedno zdanie przyczyny + jedno zdanie porady.
Testowalne bez Qt."""
from __future__ import annotations

from ui.app_logging import log_path

_AC_PORTS = "19723–19730"


def _tail(exc: BaseException) -> str:
    r = repr(exc)
    if len(r) > 200:
        r = r[:197] + "..."
    lp = log_path()
    log_line = f"\nLog: {lp}" if lp else ""
    return f"\n\nSzczegóły techniczne: {r}{log_line}"


def describe(exc: BaseException) -> tuple[str, str]:
    msg = str(exc)
    low = msg.lower()

    if isinstance(exc, (ConnectionRefusedError, ConnectionError)) or "connection refused" in low \
            or "nie znaleziono archicad" in low:
        return ("ArchiCAD",
                f"Nie znaleziono ArchiCADa na portach {_AC_PORTS}. "
                "Uruchom AC z załadowanym dodatkiem Tapir i kliknij Odśwież." + _tail(exc))
    if isinstance(exc, TimeoutError) or "timed out" in low:
        return ("ArchiCAD",
                "ArchiCAD nie odpowiada. Zamknij otwarte okna dialogowe w AC i spróbuj ponownie." + _tail(exc))
    if isinstance(exc, KeyError) and "librarypart" in low or "additionalproperties" in low:
        return ("Dodatek Tapir",
                "Dodatek Tapir w AC nie obsługuje wymaganych parametrów (np. libraryPart w CreateDoors). "
                "Zainstaluj bundle z paczki FloorForge." + _tail(exc))
    if "infeasible" in low or "nie znaleziono układu" in low or "unknown" == low:
        return ("Brak układu",
                "Nie znaleziono układu dla tego obrysu i typu. "
                "Spróbuj inny typ lub powiększ obrys." + _tail(exc))
    if isinstance(exc, ValueError):
        return ("Dane wejściowe", f"{msg} Popraw dane i spróbuj ponownie." + _tail(exc))
    return ("Nieoczekiwany błąd",
            "Coś poszło nie tak. Prześlij plik logu autorowi aplikacji." + _tail(exc))
```

```python
# ui/app_logging.py
"""Log techniczny na dysku: ~/Library/Logs/FloorForge/floorforge.log, rotacja 5 × 2 MB."""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_LOG_PATH: Path | None = None


def _log_dir(app_name: str) -> Path:
    env = os.environ.get("FLOORFORGE_LOG_DIR")
    if env:
        return Path(env)
    return Path.home() / "Library" / "Logs" / app_name


def setup_logging(app_name: str = "FloorForge") -> Path:
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    d = _log_dir(app_name)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "floorforge.log"
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    _LOG_PATH = path
    return path


def log_path() -> Path | None:
    return _LOG_PATH
```

Wpięcie w `ui/main_window.py`:

1. Import na górze: `from ui.user_errors import describe` i `import logging` + `logger = logging.getLogger(__name__)`.
2. `_on_error(self, msg: str)`: workery emitują string; zmień oba workery tak, by emitowały wyjątek: `error = pyqtSignal(object)` i `self.error.emit(e)`; w `_on_error(self, exc)`:

```python
    def _on_error(self, exc):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        if not isinstance(exc, BaseException):
            exc = RuntimeError(str(exc))
        logger.error("generowanie: %r", exc)
        title, text = describe(exc)
        self.statusBar().showMessage(f"Błąd: {title}")
        QMessageBox.critical(self, title, text)
```

3. W trzech blokach `except Exception as e:` eksportu/importu AC zastąp treść `QMessageBox.warning(self, "ArchiCAD", f"...{e}...")` przez:

```python
            logger.exception("eksport do AC")
            title, text = describe(e)
            QMessageBox.warning(self, title, text)
```

- [ ] **Step 4: Run → PASS + regresja GUI**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_user_errors.py tests/test_app_logging.py tests/test_gui.py tests/test_house_export_gui.py -q -p no:cacheprovider
```

Jeśli `test_gui.py` sprawdza `error` jako `str` — zaktualizuj asercję na `isinstance(..., Exception)`.

- [ ] **Step 5: Commit** `feat(ui): polskie komunikaty błędów (user_errors) + log na dysku (app_logging)`.

---

### Task 6: Tryb beta w GUI + `AcStatusWidget`

**Files:**
- Create: `ui/ac_status_widget.py`
- Modify: `ui/main_window.py:225-265` (`_build_ui` — zakładki), tytuł okna (linia 207)
- Test: `tests/test_beta_mode.py`, `tests/test_ac_status_widget.py`

**Interfaces:**
- Produces: `ui.main_window.is_beta() -> bool` (env `FLOORFORGE_BETA` ∈ {"1","true"}); w becie: `tabs.count() == 1`, `tabs.tabText(0) == "Podział rzutu"`, tytuł `FloorForge {wersja}`; `MainWindow.ac_status: AcStatusWidget`.
- `AcStatusWidget(parent=None)`: `.refresh()` → etykieta `Brak połączenia z ArchiCAD` albo `AC port 19723 · <projekt> · kondygnacja <nazwa|idx>`; `.instances: list[dict]` po refresh; przycisk `Odśwież`. Bez auto-pollingu.

- [ ] **Step 1: Failing tests**

```python
# tests/test_beta_mode.py
import os
import subprocess
import sys
import pytest

pytest.importorskip("PyQt5")


def test_beta_mode_single_polish_tab(qapp, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    monkeypatch.setenv("FLOORFORGE_VERSION", "beta-test")
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() == 1
    assert w.tabs.tabText(0) == "Podział rzutu"
    assert w.windowTitle() == "FloorForge beta-test"
    assert hasattr(w, "ac_status")


def test_default_mode_unchanged(qapp, monkeypatch):
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() >= 2
    assert w.windowTitle() == "FloorPlan6 — Apartment Layout Generator"


def test_beta_mode_does_not_import_frozen_stages():
    """Osobny proces: w becie ui.stage1_window / floor_layout_window nie są importowane."""
    code = (
        "import os, sys; os.environ['FLOORFORGE_BETA']='1'; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
        "from PyQt5.QtWidgets import QApplication; app=QApplication([])\n"
        "from ui.main_window import MainWindow; w=MainWindow()\n"
        "bad=[m for m in ('ui.stage1_window','ui.floor_layout_window','ui.stage_placeholder','core.report_pdf') if m in sys.modules]\n"
        "print('BAD=' + ','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": "."})
    assert out.returncode == 0, out.stderr
    assert "BAD=\n" in out.stdout or out.stdout.strip().endswith("BAD=")
```

```python
# tests/test_ac_status_widget.py
import pytest

pytest.importorskip("PyQt5")


def test_status_no_archicad(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: []))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Brak połączenia" in w.label.text()
    assert w.instances == []


def test_status_shows_port_project_story(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19723, "projectName": "Dom K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "use_port", lambda self, p: True)
    monkeypatch.setattr(tc.TapirConnection, "get_stories",
                        lambda self: {"actStory": 1, "firstStory": 0, "lastStory": 1,
                                      "stories": [{"index": 0, "name": "Parter"}, {"index": 1, "name": "Poddasze"}]})
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    t = w.label.text()
    assert "19723" in t and "Dom K" in t and "Poddasze" in t


def test_status_survives_exception(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: (_ for _ in ()).throw(OSError("boom"))))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Brak połączenia" in w.label.text()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implementacja `ui/ac_status_widget.py`**

```python
# ui/ac_status_widget.py
"""Pasek statusu połączenia z ArchiCAD: port · projekt · aktywna kondygnacja + Odśwież."""
from __future__ import annotations

import logging

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

logger = logging.getLogger(__name__)


class AcStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[dict] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("ArchiCAD: nie sprawdzono")
        self.refresh_btn = QPushButton("Odśwież")
        self.refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.refresh_btn)

    def refresh(self):
        from bridge.tapir_connection import TapirConnection
        try:
            self.instances = TapirConnection.list_instances() or []
        except Exception as e:
            logger.warning("status AC: %r", e)
            self.instances = []
        if not self.instances:
            self.label.setText("Brak połączenia z ArchiCAD — uruchom AC z dodatkiem Tapir i kliknij Odśwież.")
            return
        inst = self.instances[0]
        story_txt = "?"
        try:
            t = TapirConnection()
            t.use_port(inst["port"])
            st = t.get_stories() or {}
            act = int(st.get("actStory", -1))
            names = {int(s.get("index", -1)): s.get("name") for s in st.get("stories", [])}
            story_txt = names.get(act) or f"idx {act}"
        except Exception as e:
            logger.warning("status AC (stories): %r", e)
        more = f" (+{len(self.instances) - 1} inne)" if len(self.instances) > 1 else ""
        self.label.setText(
            f"AC port {inst['port']} · {inst.get('projectName') or '?'} · kondygnacja {story_txt}{more}")
```

Implementacja trybu beta w `ui/main_window.py`:

```python
import os

def is_beta() -> bool:
    return os.environ.get("FLOORFORGE_BETA", "").lower() in ("1", "true")
```

W `__init__`: tytuł

```python
        if is_beta():
            self.setWindowTitle(f"FloorForge {os.environ.get('FLOORFORGE_VERSION', 'beta')}")
        else:
            self.setWindowTitle("FloorPlan6 — Apartment Layout Generator")
```

W `_build_ui`: cały blok od `# Stage 1 — plot analyser` do `# Stage 4 — apartment layout` opakuj w `if not is_beta():` (wcięcie o poziom; `self.stage1_widget = None` ustaw przed `if`). Zakładkę Stage 4:

```python
        self.apt_tab = QWidget()
        self.tabs.addTab(self.apt_tab, "Podział rzutu" if is_beta() else "Stage 4: Apartment Layout")
```

Na początku `left` (lewy panel), przed `mode_group`:

```python
        from ui.ac_status_widget import AcStatusWidget
        self.ac_status = AcStatusWidget(self)
        left.addWidget(self.ac_status)
```

W becie polskie etykiety kluczowych przycisków (tylko gdy `is_beta()`): `import_btn` → „Wczytaj obrys z ArchiCAD", `generate_btn` → „3. Generuj układy", `archicad_btn` → „Wstaw do ArchiCAD", `export_btn` → „Zapisz PNG". Uwaga: `_on_error`/`_on_variants_ready` ustawiają tekst przycisku na sztywno „3. Generate layouts" — wprowadź stałą `self._generate_label = "3. Generuj układy" if is_beta() else "3. Generate layouts"` i użyj jej we wszystkich `setText`.

- [ ] **Step 4: Run → PASS + regresja**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_beta_mode.py tests/test_ac_status_widget.py tests/test_gui.py tests/test_house_export_gui.py tests/test_stage1_stage4_integration.py -q -p no:cacheprovider
```

- [ ] **Step 5: Ręczny podgląd (B8/P3):** `FLOORFORGE_BETA=1 FLOORFORGE_VERSION=dev python ui/main_window.py` — jedna zakładka, pasek AC na górze, polskie przyciski. Zrób screenshot do `docs/images/beta_mode.png` (nie commituj PNG poza `docs/images/` — `.gitignore` wyjątek).

- [ ] **Step 6: Commit** `feat(ui): tryb beta (FLOORFORGE_BETA) — jedna zakładka 'Podział rzutu' + pasek statusu AC`.

---

### Task 7: Entry point `floorforge_app.py` z `--selftest`

**Files:**
- Create: `floorforge_app.py`
- Test: `tests/test_selftest.py`

**Interfaces:**
- Produces: `floorforge_app.main(argv) -> int`. Bez argumentów: ustawia `FLOORFORGE_BETA=1`, `setup_logging()`, `ui.main_window.run_gui()`. `--selftest`: startuje `service.app.start_server`, `ServiceClient.solve` M2 na 8×6 (`entry [4,0]`, `max_variants 1`), czeka ≤120 s, drukuje `SELFTEST OK: n wariantów, m pokoi, wersja X` i zwraca 0; przy błędzie drukuje `SELFTEST FAIL: ...` i zwraca 1. `--version` drukuje wersję.

- [ ] **Step 1: Failing test**

```python
# tests/test_selftest.py
def test_selftest_returns_zero_with_mocked_solver(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: {"mode": "apartment",
                                                    "variants": [{"rooms": [{"name": "salon"}, {"name": "hub"}], "score": 0.9}]})
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    out = capsys.readouterr().out
    assert rc == 0 and "SELFTEST OK" in out and "2 pokoi" in out


def test_selftest_returns_one_on_error(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: (_ for _ in ()).throw(RuntimeError("INFEASIBLE")))
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    assert rc == 1 and "SELFTEST FAIL" in capsys.readouterr().out


def test_selftest_real_solver_m2_8x6():
    """Prawdziwy solver, ~3 s. Bramka: mózg działa w tym środowisku."""
    import floorforge_app
    assert floorforge_app.main(["--selftest"]) == 0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implementacja**

```python
# floorforge_app.py
"""Entry point zamrożonej aplikacji FloorForge (beta). Patrz packaging/floorforge.spec."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SELFTEST_REQ = {"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]],
                "entry": [4, 0], "mtype": "M2", "max_variants": 1}


def _version() -> str:
    return os.environ.get("FLOORFORGE_VERSION", "dev")


def selftest() -> int:
    from service.app import start_server
    from service.client import ServiceClient
    h = start_server(port=0)
    try:
        c = ServiceClient(h.url)
        c.health()
        job = c.wait(c.solve(SELFTEST_REQ), timeout=120)
        variants = job["result"].get("variants", [])
        if not variants:
            print("SELFTEST FAIL: solver nie zwrócił wariantów")
            return 1
        n_rooms = len(variants[0].get("rooms", []))
        print(f"SELFTEST OK: {len(variants)} wariantów, {n_rooms} pokoi, wersja {_version()}")
        return 0
    except Exception as e:
        print(f"SELFTEST FAIL: {e!r}")
        return 1
    finally:
        h.stop()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    os.environ.setdefault("FLOORFORGE_BETA", "1")
    from ui.app_logging import setup_logging
    setup_logging()
    if "--version" in argv:
        print(_version())
        return 0
    if "--selftest" in argv:
        return selftest()
    from ui.main_window import run_gui
    run_gui()   # sys.exit wewnątrz
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Uwaga: `setup_logging()` w testach pisze do `~/Library/Logs/FloorForge` — w `tests/conftest.py` dodaj autouse fixture ustawiającą `FLOORFORGE_LOG_DIR=tmp_path` (żeby testy nie śmieciły w katalogu użytkownika):

```python
@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_LOG_DIR", str(tmp_path))
```

- [ ] **Step 4: Run → PASS**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_selftest.py tests/test_app_logging.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit** `feat: floorforge_app entry point (beta, --selftest przez serwis HTTP)`.

---

### Task 8: `packaging/` — spec, lock, ikona, build, smoke, instrukcja

**Files:**
- Create: `packaging/requirements-lock.txt`, `packaging/floorforge.spec`, `packaging/make_icon.py`, `packaging/build_release.sh`, `packaging/smoke_frozen.sh`, `packaging/INSTALACJA.md`, `packaging/Uruchom.command`
- Modify: `.gitignore` (+ `packaging/.venv/`, `packaging/build/`, `packaging/dist/`, `packaging/icon.iconset/`)

**Interfaces:**
- Produces: `packaging/dist/FloorForge-beta-<wersja>.zip`; `smoke_frozen.sh` zwraca 0 gdy `--selftest` binarki daje `SELFTEST OK`.

- [ ] **Step 1: Lock zależności**

```bash
source venv/bin/activate
pip freeze | grep -iE "^(ortools|shapely|numpy|matplotlib|PyQt5|PyQt5-Qt5|PyQt5_sip|archicad|networkx|pydantic|pydantic_core|protobuf|absl-py|pandas|immutabledict|typing_extensions|annotated-types|pillow|contourpy|cycler|fonttools|kiwisolver|packaging|pyparsing|python-dateutil|six)=" > packaging/requirements-lock.txt
echo "pyinstaller==6.11.1" >> packaging/requirements-lock.txt
cat packaging/requirements-lock.txt
```

Jeśli `pip freeze` nie pokazuje `protobuf`/`absl-py`/`pandas`/`immutabledict` (zależności OR-Tools), dopisz je z `pip show ortools | grep Requires` i `pip freeze | grep -i <nazwa>`. reportlab/pypdf/jupyter/pytest NIE wchodzą.

- [ ] **Step 2: Ikona**

```python
# packaging/make_icon.py
"""Generuje icon.icns z prostego renderu (kwadrat + 3 pokoje). Wymaga matplotlib + sips/iconutil (macOS)."""
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
png = HERE / "icon_1024.png"
fig = plt.figure(figsize=(10.24, 10.24), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
ax.add_patch(Rectangle((0.8, 0.8), 8.4, 8.4, facecolor="#F4F1EA", edgecolor="#1F2937", linewidth=18))
for (x, y, w, h, c) in [(0.8, 0.8, 5.0, 4.2, "#F6C453"), (5.8, 0.8, 3.4, 4.2, "#7FB3D5"),
                        (0.8, 5.0, 3.0, 4.2, "#B39DDB"), (3.8, 5.0, 5.4, 4.2, "#A5D6A7")]:
    ax.add_patch(Rectangle((x, y), w, h, facecolor=c, edgecolor="#1F2937", linewidth=10))
fig.savefig(png, transparent=True)

iconset = HERE / "icon.iconset"; iconset.mkdir(exist_ok=True)
for s in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        size = s * scale
        name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
        subprocess.run(["sips", "-z", str(size), str(size), str(png), "--out", str(iconset / name)],
                       check=True, capture_output=True)
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
print("OK", HERE / "icon.icns")
```

```bash
source venv/bin/activate && python packaging/make_icon.py && ls -la packaging/icon.icns
```

- [ ] **Step 3: Spec PyInstallera**

```python
# packaging/floorforge.spec
# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve().parent
VERSION = os.environ.get("FLOORFORGE_VERSION", "dev")

hiddenimports = (
    collect_submodules("ortools.sat")
    + collect_submodules("ortools.util")
    + ["ortools.sat.python.cp_model", "shapely._geos", "PyQt5.sip",
       "matplotlib.backends.backend_qt5agg", "matplotlib.backends.backend_agg",
       "archicad", "archicad.connection", "archicad.commands", "archicad.types"]
)
datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "rules"), "rules"),
    (str(ROOT / "data" / "plans"), "data/plans"),
] + collect_data_files("shapely") + collect_data_files("ortools")
binaries = collect_dynamic_libs("shapely") + collect_dynamic_libs("ortools")

a = Analysis(
    [str(ROOT / "floorforge_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["reportlab", "pypdf", "jupyter", "ipywidgets", "notebook", "pytest", "tkinter",
              "core.report_pdf", "core.report_renderer", "core.report_builder"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="FloorForge", console=False,
          icon=str(ROOT / "packaging" / "icon.icns"))
coll = COLLECT(exe, a.binaries, a.datas, name="FloorForge")
app = BUNDLE(
    coll, name="FloorForge.app", icon=str(ROOT / "packaging" / "icon.icns"),
    bundle_identifier="pl.floorforge.beta",
    info_plist={
        "CFBundleName": "FloorForge",
        "CFBundleDisplayName": "FloorForge",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
        "LSEnvironment": {"FLOORFORGE_BETA": "1", "FLOORFORGE_VERSION": VERSION},
    },
)
```

Uwaga do `rules`: `rules/_loader.py` używa `Path(__file__).resolve().parent` — w onedir moduł `rules/_loader.py` ląduje w `Contents/Frameworks/rules/` (PyInstaller ≥6 trzyma pure-Python w PYZ, `__file__` = `<_MEIPASS>/rules/_loader.py`), a `datas` `rules` → `<_MEIPASS>/rules`. Jeśli smoke pokaże `FileNotFoundError` dla `rules/PL` lub `templates`, dodaj `core/resources.py`:

```python
import sys
from pathlib import Path

def resource_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent.parent
```

i użyj `resource_root() / "templates"` w `core/template_selector.py:95`, `resource_root() / "rules"` w `rules/_loader.py:24`.

- [ ] **Step 4: `build_release.sh`**

```bash
#!/usr/bin/env bash
# packaging/build_release.sh — buduje FloorForge.app + zip bety (macOS, ad-hoc sign).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TAPIR_BUNDLE="$ROOT/../tapir-custom/archicad-addon/Build/RelWithDebInfo/TapirAddOn_AC29_Mac.bundle"
export FLOORFORGE_VERSION="${FLOORFORGE_VERSION:-$(cd "$ROOT" && git describe --tags --always --dirty)}"

echo "== FloorForge beta $FLOORFORGE_VERSION"
[ -d "$TAPIR_BUNDLE" ] || { echo "BRAK bundla Tapira: $TAPIR_BUNDLE — zbuduj tapir-custom (cmake) najpierw"; exit 2; }
[ -f "$HERE/icon.icns" ] || (cd "$ROOT" && "$ROOT/venv/bin/python" "$HERE/make_icon.py")

VENV="$HERE/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3.13 -m venv "$VENV" || python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$HERE/requirements-lock.txt"

rm -rf "$HERE/build" "$HERE/dist"
(cd "$ROOT" && "$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$HERE/dist" --workpath "$HERE/build" "$HERE/floorforge.spec")

APP="$HERE/dist/FloorForge.app"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "codesign OK (ad-hoc)"

STAGE="$HERE/dist/FloorForge-beta-$FLOORFORGE_VERSION"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
cp -R "$TAPIR_BUNDLE" "$STAGE/"
cp "$HERE/INSTALACJA.md" "$HERE/Uruchom.command" "$STAGE/"
chmod +x "$STAGE/Uruchom.command"
(cd "$HERE/dist" && rm -f "FloorForge-beta-$FLOORFORGE_VERSION.zip" && ditto -c -k --keepParent "FloorForge-beta-$FLOORFORGE_VERSION" "FloorForge-beta-$FLOORFORGE_VERSION.zip")
echo "== GOTOWE: $HERE/dist/FloorForge-beta-$FLOORFORGE_VERSION.zip"
```

`ditto` zamiast `zip` zachowuje atrybuty bundla `.app`.

- [ ] **Step 5: `smoke_frozen.sh`**

```bash
#!/usr/bin/env bash
# packaging/smoke_frozen.sh — --selftest na zamrożonej binarce (bez AC, bez okna).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/dist/FloorForge.app/Contents/MacOS/FloorForge"
[ -x "$BIN" ] || { echo "Brak binarki: $BIN — uruchom build_release.sh"; exit 2; }
OUT="$("$BIN" --selftest 2>&1 | tail -20)"
echo "$OUT"
echo "$OUT" | grep -q "SELFTEST OK" || { echo "SMOKE FAIL"; exit 1; }
echo "SMOKE OK"
```

- [ ] **Step 6: `INSTALACJA.md` i `Uruchom.command`**

```markdown
# FloorForge — beta (macOS, ArchiCAD 29)

## 1. Dodatek Tapir (jednorazowo)
1. Zamknij ArchiCAD.
2. Skopiuj `TapirAddOn_AC29_Mac.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`
   (jeśli masz tam już inny `TapirAddOn…bundle`, przenieś go gdzie indziej — FloorForge wymaga tej wersji).
3. Uruchom ArchiCAD i otwórz projekt.

## 2. Aplikacja
1. Przenieś `FloorForge.app` do `Programy` (lub gdziekolwiek).
2. Pierwsze otwarcie: **prawy klik → Otwórz → Otwórz** (aplikacja nie jest notaryzowana w Apple; to jednorazowe).
   Jeśli macOS mimo to blokuje: Ustawienia → Prywatność i ochrona → „Otwórz mimo to".
3. W oknie na górze zobaczysz „AC port 19723 · nazwa projektu · kondygnacja …". Jeśli „Brak połączenia": sprawdź, że AC działa i kliknij „Odśwież".

## 3. Praca
1. W AC zaznacz ściany obrysu mieszkania (albo strefę / płytę) → w FloorForge „Wczytaj obrys z ArchiCAD".
2. Wybierz tryb (mieszkanie M1–M5 / dom) → „Generuj układy" (mieszkanie kilka sekund, dom do ~2 min).
3. Przeglądaj warianty ‹ › → „Wstaw do ArchiCAD". Dom: zaznacz „Wstaw obie kondygnacje".

## 4. Gdy coś nie działa
- Okno błędu podaje przyczynę i ścieżkę logu. Prześlij plik `~/Library/Logs/FloorForge/floorforge.log` + zrzut ekranu.
- Awaryjnie: dwuklik `Uruchom.command` (uruchamia aplikację z terminalem — widać pełny komunikat).
```

```bash
#!/usr/bin/env bash
# Uruchom.command — awaryjne uruchomienie FloorForge z widocznym terminalem.
cd "$(dirname "$0")"
exec ./FloorForge.app/Contents/MacOS/FloorForge
```

- [ ] **Step 7: `.gitignore`**

```
# packaging (artefakty builda)
packaging/.venv/
packaging/build/
packaging/dist/
packaging/icon.iconset/
packaging/icon_1024.png
```

`packaging/icon.icns` commitujemy (mały, deterministyczny).

- [ ] **Step 8: Build + smoke (pierwszy przebieg, iteracja na hiddenimports)**

```bash
chmod +x packaging/build_release.sh packaging/smoke_frozen.sh
packaging/build_release.sh 2>&1 | tail -30
packaging/smoke_frozen.sh
```

Oczekiwane: `codesign OK`, `GOTOWE: …zip`, `SMOKE OK`. Typowe błędy i naprawy (jeden cykl = jedna poprawka w spec, potem rebuild; po 2 nieudanych cyklach w tym samym miejscu STOP i raport, reguła B1):
- `ModuleNotFoundError: ortools...` → dopisz moduł do `hiddenimports`.
- `OSError: Could not find lib geos_c` → `collect_dynamic_libs("shapely")` już jest; sprawdź `binaries` w logu builda.
- `FileNotFoundError: .../templates` → helper `core/resources.py` (Step 3).
- Qt plugin `cocoa` brak → dodaj `collect_data_files("PyQt5", subdir="Qt5/plugins/platforms")` do `datas`.

- [ ] **Step 9: Otwórz zamrożone GUI ręcznie**

```bash
open packaging/dist/FloorForge.app
```

Sprawdź: tytuł `FloorForge <wersja>`, jedna zakładka, pasek AC, generowanie M2 8×6 z podglądem PNG. Zamknij.

- [ ] **Step 10: Commit**

```bash
git add packaging .gitignore
git commit -m "build(packaging): PyInstaller spec + build_release + smoke + INSTALACJA (beta macOS)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 9: Test na czystym koncie + dokumentacja stanu

**Files:**
- Create: `packaging/CHECKLIST_TEST.md`
- Modify: `docs/STATE.md` (nowy wpis NEXT SESSION na górze), `README.md` (sekcja „Beta (macOS)")

- [ ] **Step 1: Checklist**

```markdown
# Test bety na czystym koncie (bramka wysyłki)

Przygotowanie (raz): Ustawienia → Użytkownicy → dodaj konto „beta-test" (standardowe). Zaloguj się na nie.
Na koncie NIE ma: Pythona z brew, venv, repo FloorPlan6. Jest: ArchiCAD 29.

| # | Krok | Oczekiwane | OK? |
|---|---|---|---|
| 1 | Skopiuj zip na konto, rozpakuj | 4 pozycje: .app, .bundle, INSTALACJA.md, Uruchom.command | |
| 2 | Wykonaj INSTALACJA.md §1 (Tapir) | AC startuje, menu Tapir widoczne | |
| 3 | INSTALACJA.md §2 — prawy klik → Otwórz | Okno FloorForge, tytuł z wersją, jedna zakładka | |
| 4 | Pasek AC bez otwartego projektu → Odśwież | „Brak połączenia…" (bez crasha) | |
| 5 | Otwórz projekt testowy w AC, Odśwież | „AC port 19723 · nazwa · kondygnacja Parter" | |
| 6 | Mieszkanie: zaznacz ściany obrysu M3 w AC → Wczytaj obrys | podgląd obrysu, typ auto M3 | |
| 7 | Generuj układy | ≥1 wariant, PNG podgląd, < 30 s | |
| 8 | Wstaw do ArchiCAD | strefy + ściany + drzwi + okna + etykiety widoczne w AC | |
| 9 | Dom: obrys 10×8 ręcznie, tryb Dom, Generuj | układ parter+poddasze, ≤ 2 min | |
| 10 | Zaznacz „Wstaw obie kondygnacje" → Wstaw | parter na story 0, poddasze na story 1, ten sam projekt | |
| 11 | Wyłącz AC → Wstaw do ArchiCAD | okno „ArchiCAD: Nie znaleziono…", ścieżka logu, bez crasha | |
| 12 | Otwórz `~/Library/Logs/FloorForge/floorforge.log` | wpisy INFO + traceback z kroku 11 | |
| 13 | Uruchom.command | aplikacja startuje z terminalem | |

Wynik: wszystkie OK → wysyłka. Dowolny FAIL → wpis w `docs/STATE.md`, poprawka, ponowny build, powtórz od kroku 1.
```

- [ ] **Step 2: STATE.md** — dodaj na górze wpis NEXT SESSION: „BETA DYSTRYBUCYJNA (2026-09-xx): Task 0–8 DONE (lista commitów), bramka Task 1 live (wynik probe), bramka Task 9 checklist (wynik per krok), co wysłano komu, znane luki (eksport z kontraktu = 501, GUI in-process)". Pełny format jak istniejące wpisy.

- [ ] **Step 3: README** — sekcja:

```markdown
## Beta (macOS + ArchiCAD 29)

Zamrożona aplikacja dla testerów: `packaging/build_release.sh` → `packaging/dist/FloorForge-beta-<ver>.zip`
(`FloorForge.app` + custom Tapir + `INSTALACJA.md`). Tryb beta = `FLOORFORGE_BETA=1` (jedna zakładka
„Podział rzutu", polskie komunikaty, log w `~/Library/Logs/FloorForge/`). Smoke: `packaging/smoke_frozen.sh`.
Spec: `docs/superpowers/specs/2026-09-14-beta-dystrybucja-macos-design.md`.
```

- [ ] **Step 4: Commit + push + tag**

```bash
git add packaging/CHECKLIST_TEST.md docs/STATE.md README.md
git commit -m "docs: checklist testu bety na czystym koncie + STATE + README (beta macOS)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
git tag -a v0.7-beta1 -m "Pierwsza beta dystrybucyjna macOS/AC29"
git push origin main --tags
```

- [ ] **Step 5: BRAMKA (Dawid):** przejdź `CHECKLIST_TEST.md` na czystym koncie. Wyniki do STATE.md. Dopiero po 13/13 OK → wysyłka zipa 2–3 osobom z prośbą: „przy błędzie prześlij log + zrzut".

---

## Self-Review

**Spec coverage:**
- §1 zakres (mieszkania + domy → AC, .app + Tapir, komunikaty PL, log, ad-hoc) → Task 1, 5, 6, 8. ✓
- §2 architektura wydania (zip, wersja z git describe w Info.plist i tytule) → Task 8 (`FLOORFORGE_VERSION`, `LSEnvironment`), Task 6 (tytuł). ✓
- §2 korekta: serwis HTTP, `/solve` z job_id + postęp, `/health`, `/export`, klient → Task 2–4. GUI przepięcie: **świadome odstępstwo** (nagłówek planu) — do potwierdzenia przez Dawida. ⚠
- §3 tryb beta (flaga, jedna zakładka, bez importu etapów 1–3, pasek AC, PL) → Task 6. ✓
- §4 komunikaty (`ui/user_errors.py` `describe`), log rotacja, ścieżka logu w oknie → Task 5. ✓
- §5 pakowanie (spec, lock, build_release z 7 krokami, `resources.py` warunkowo) → Task 8. ✓
- §6 testy: pytest (`test_beta_mode`, `test_user_errors`) → Task 5–6; smoke `--selftest` → Task 7–8; ręczny czyste konto → Task 9. ✓
- §7 kolejność 0→1→2→3→4→5 → Task 0, 1, 2–4, 5–6, 7–8, 9. ✓
- §8/§9 otwarte decyzje → poza planem (docs). ✓

**Placeholder scan:** brak TBD/TODO. Task 1 Step 10 i Task 9 Step 5 to bramki live z konkretnymi krokami, nie placeholdery. Task 8 Step 8 zawiera listę typowych błędów z konkretną naprawą, limit B1.

**Type consistency:** `solve_request(req, progress=None)` (T2) = wywołanie w `JobStore.submit(solve_request, body)` przekazującym kwarg `progress` (T3/T4). ✓ `ServiceHandle.url/.port/.stop()` (T4) = użycie w `floorforge_app.selftest` (T7) i testach. ✓ `describe(exc) -> (title, text)` (T5) = użycie w `_on_error` i excepty (T5). ✓ `is_beta()` (T6) = testy `test_beta_mode`. ✓ `activate_story(int) -> bool`, `CHANGE_WINDOW_SHAPES` (T1) = testy i GUI loop. ✓ `house_both_storeys_check` (T1 GUI) = testy T1. ✓ `FLOORFORGE_LOG_DIR` (T5 `app_logging`) = fixture conftest (T7). ✓
