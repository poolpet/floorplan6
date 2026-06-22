# Dom → ArchiCAD: target instancji + story-guard + okna — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development (RED→GREEN
> per task). Steps use checkbox (`- [ ]`) tracking. **Mózg ZAMROŻONY** — zmiany tylko w
> `bridge/` + `ui/` + `notebooks/`.

**Goal:** Eksport domu 2-kond. do JEDNEJ wybranej instancji AC, obie kondygnacje na właściwych
story. Determinizm instancji (picker) + story-guard + okna-robustness + diag. Spec:
`docs/superpowers/specs/2026-06-22-dom-ac-story-target-multi-instance-design.md`.

**Tech Stack:** Python 3.13, pytest (monkeypatch), PyQt5, `archicad` + Tapir Add-On.
Pliki: `bridge/tapir_connection.py`, `ui/main_window.py`, `notebooks/ac_story_diag.py`.

## Global Constraints

- **NIE dotykać** solvera/generatora/benchmarku/szablonów. NIE zmieniać `bridge/plan_writer.py`
  poza jednym logiem w `get_all_walls` (Task 1 Step 7). Ścieżka MIESZKAŃ (auto-`connect`) bez regresji.
- Komendy z roota: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest ...`
- Fakty API (zweryfikowane live 2026-06-22, nasz stack): Tapir `GetProjectInfo`→`{projectName,
  projectPath}`; Tapir `GetStories`→`{actStory, firstStory, lastStory, stories:[{index,name,level}]}`;
  `GetElementsByType("Wall")` = scope aktywnej bazy planu (NIE 0 gdy aktywne okno=właściwy plan).
- Każdy commit kończ: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Live-verify = Dawid (Claude bez AC) — patrz Execution Handoff.

---

### Task 1: `tapir_connection.py` — wybór instancji + story API + guard (czysta logika)

**Files:**
- Modify: `bridge/tapir_connection.py`
- Test: `tests/test_ac_targeting.py` (Create)

**Interfaces (Produces):**
- `TapirConnection.list_instances(port_range=range(19723,19731)) -> list[dict]` — `[{port, projectName,
  projectPath}]` dla odpowiadających portów. Świeże `ACConnection.connect(port)` per port (NIE
  mutuje singletona), nazwa via Tapir `GetProjectInfo`; martwy port pominięty; brak nazwy →
  `projectName="(nieznany)"`.
- `TapirConnection.use_port(port: int) -> bool` — połącz z JAWNYM portem (bez scan/prefer-selection),
  ustaw `_active_port=port`, `_conn`. Zwraca True/raise ConnectionError.
- `TapirConnection.get_stories() -> dict` — wrap `_execute_tapir("GetStories", {})`.
- `TapirConnection.get_project_info() -> dict` — wrap `_execute_tapir("GetProjectInfo", {})`.
- `check_active_story(act, first, last, gui_storey) -> tuple[bool, str]` — **wolna funkcja** (pure):
  - `gui_storey=="parter"`: ok ⟺ `act==first`.
  - `gui_storey=="poddasze"`: `last==first` → (False, „projekt jednokondygnacyjny — brak poddasza");
    `act>first` → ok; inaczej (False, „aktywna kondygnacja = parter, przełącz w AC na poddasze").
  - ok → (True, ""). Komunikat zawiera indeksy.

- [ ] **Step 1: Failing test** — `tests/test_ac_targeting.py`

```python
"""AC-targeting: wybór instancji (picker source), story API, guard (czysta logika)."""
import pytest
import bridge.tapir_connection as tc
from bridge.tapir_connection import TapirConnection, check_active_story


# ---- check_active_story (pure, bez AC) ----
@pytest.mark.parametrize("act,first,last,gui,ok", [
    (0, 0, 2, "parter", True),     # parter na story bazowej
    (1, 0, 2, "parter", False),    # parter, ale aktywne piętro
    (1, 0, 2, "poddasze", True),   # poddasze na piętrze
    (0, 0, 2, "poddasze", False),  # poddasze, ale aktywny parter
    (0, 0, 0, "poddasze", False),  # projekt 1-kondygnacyjny
    (0, 0, 0, "parter", True),     # parterowiec OK
])
def test_check_active_story(act, first, last, gui, ok):
    res, msg = check_active_story(act, first, last, gui)
    assert res is ok
    assert (msg == "") is ok


# ---- list_instances (monkeypatch ACConnection) ----
class _FakeConn:
    def __init__(self, name): self._name = name
    class _Types:
        def AddOnCommandId(self, ns, cmd): return (ns, cmd)
    class _Cmds:
        def __init__(self, name): self._name = name
        def ExecuteAddOnCommand(self, cid, params):
            return {"projectName": self._name, "projectPath": f"/p/{self._name}.pln"}
    @property
    def types(self): return self._Types()
    @property
    def commands(self): return self._Cmds(self._name)


def test_list_instances_returns_port_and_name(monkeypatch):
    def fake_connect(port):
        return {19723: _FakeConn("test"), 19724: _FakeConn("Kamienica")}.get(port)
    monkeypatch.setattr(tc.ACConnection, "connect", staticmethod(fake_connect))
    out = TapirConnection.list_instances()
    by_port = {d["port"]: d["projectName"] for d in out}
    assert by_port == {19723: "test", 19724: "Kamienica"}


def test_use_port_pins_explicit_port(monkeypatch):
    seen = {}
    monkeypatch.setattr(tc.ACConnection, "connect",
                        staticmethod(lambda port: seen.setdefault("port", port) or _FakeConn("x")))
    t = TapirConnection()
    assert t.use_port(19724) is True
    assert t.active_port == 19724 and seen["port"] == 19724


def test_get_stories_passthrough(monkeypatch):
    t = TapirConnection()
    monkeypatch.setattr(t, "_execute_tapir", lambda cmd, p: {"actStory": 1} if cmd == "GetStories" else {})
    assert t.get_stories()["actStory"] == 1
```

- [ ] **Step 2: Run → FAIL** (`ImportError: check_active_story` / brak metod).
  `PYTHONPATH=. venv/bin/python -m pytest tests/test_ac_targeting.py -q`

- [ ] **Step 3: Implement** w `bridge/tapir_connection.py`:
  - Wolna funkcja `check_active_story(act, first, last, gui_storey)` (na końcu modułu).
  - `list_instances(port_range=...)` jako `@classmethod`/`@staticmethod`: pętla po portach,
    `ACConnection.connect(port)`; jeśli conn → `cid = conn.types.AddOnCommandId("TapirCommand",
    "GetProjectInfo")`, `info = conn.commands.ExecuteAddOnCommand(cid, {}) or {}`; dołóż
    `{"port": port, "projectName": info.get("projectName") or "(nieznany)",
    "projectPath": info.get("projectPath", "")}`. Wyjątek per port → pomiń.
  - `use_port(port)`: `conn = self._try_connect(port)`; None → raise ConnectionError; ustaw
    `self._active_port=port`, `self._conn=conn`; return True.
  - `get_stories()`/`get_project_info()`: `return self._execute_tapir("GetStories"/"GetProjectInfo", {})`.

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Regresja połączenia mieszkań** — `connect()` (auto) nietknięty:
  `PYTHONPATH=. venv/bin/python -c "import bridge.tapir_connection, bridge.plan_writer, bridge.house_writer"`
  + `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_writer.py tests/test_house_export_gui.py -q` (6 passed).

- [ ] **Step 6: get_all_walls — log gdy 0 ścian** (robustness, secondary fix okien). W
  `get_all_walls`, po `elements = self.get_elements_by_type("Wall")`, gdy `not elements`:
  `print("[get_all_walls] 0 ścian na aktywnej kondygnacji/oknie (GetElementsByType active-DB scope) — okna pominięte")`
  przed `return []`. **Bez** zmiany logiki/sygnatury (mieszkania bez regresji).

- [ ] **Step 7: Commit**
```bash
git add bridge/tapir_connection.py tests/test_ac_targeting.py
git commit -m "feat(bridge): wybór instancji AC (list_instances/use_port) + GetStories/GetProjectInfo + story-guard

Deterministyczny target instancji (picker source) + czysta logika check_active_story
+ log gdy get_all_walls=0. Mieszkania (auto-connect) nietknięte.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: GUI — picker instancji + story-guard w `_export_house_to_archicad`

**Files:**
- Modify: `ui/main_window.py` (`_export_house_to_archicad` ~1083)
- Test: `tests/test_house_export_gui.py` (rozszerz)

**Interfaces (Consumes):** `TapirConnection.list_instances/use_port/get_stories`, `check_active_story`,
`export_house_to_archicad(layout, storey=, tapir=, offset=)`. **Produces:** `self._ac_target_port`
(zapamiętany wybór), zachowanie: 0 instancji→błąd; 1→użyj; >1→`QInputDialog.getItem` picker;
guard-mismatch→`QMessageBox` (Anuluj=abort, override=świadome potwierdzenie); status/komunikat z portem+nazwą.

- [ ] **Step 1: Failing tests** (dopisz do `tests/test_house_export_gui.py`):

```python
def test_house_export_guard_blocks_storey_mismatch(qapp, monkeypatch):
    """GUI='Poddasze' + aktywna story=parter → guard blokuje, eksport NIE woła."""
    from PyQt5.QtWidgets import QMessageBox
    import bridge.tapir_connection as tc
    import bridge.house_writer as hw
    from ui.main_window import MainWindow

    called = {"export": 0}
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19724, "projectName": "K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "use_port", lambda self, p: True)
    monkeypatch.setattr(tc.TapirConnection, "get_stories",
                        lambda self: {"actStory": 0, "firstStory": 0, "lastStory": 2})
    monkeypatch.setattr(hw, "export_house_to_archicad",
                        lambda *a, **k: called.__setitem__("export", called["export"] + 1) or {"zones": []})
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Cancel))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    w = MainWindow(); w._archicad_offset = (0.0, 0.0)
    w.mode_house_radio.setChecked(True); w._house_layout = object()
    w.house_storey_combo.setCurrentText("Poddasze")
    w._export_to_archicad()
    assert called["export"] == 0    # guard zablokował


def test_house_export_single_instance_dispatches(qapp, monkeypatch):
    """1 instancja + aktywna story zgodna → eksport woła z wybranym tapir + storey."""
    from PyQt5.QtWidgets import QMessageBox
    import bridge.tapir_connection as tc
    import bridge.house_writer as hw
    from ui.main_window import MainWindow

    cap = {}
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19724, "projectName": "K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "use_port", lambda self, p: cap.__setitem__("port", p) or True)
    monkeypatch.setattr(tc.TapirConnection, "get_stories",
                        lambda self: {"actStory": 1, "firstStory": 0, "lastStory": 2})
    monkeypatch.setattr(hw, "export_house_to_archicad",
                        lambda layout, storey="parter", **k: cap.update(storey=storey, has_tapir=("tapir" in k)) or {"zones": []})
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    w = MainWindow(); w._archicad_offset = (0.0, 0.0)
    w.mode_house_radio.setChecked(True); w._house_layout = object()
    w.house_storey_combo.setCurrentText("Poddasze")
    w._export_to_archicad()
    assert cap.get("storey") == "poddasze" and cap.get("port") == 19724 and cap.get("has_tapir")
```

- [ ] **Step 2: Run → FAIL** (stary handler nie woła list_instances/guard).

- [ ] **Step 3: Przepisz `_export_house_to_archicad`** (`ui/main_window.py:1083`):
  1. `layout = getattr(self,"_house_layout",None)`; None→return.
  2. `storey = "poddasze" if combo=="Poddasze" else "parter"`.
  3. `try: instances = TapirConnection.list_instances()` (except→`QMessageBox.warning` „AC nie odpowiada", return).
     `if not instances: warning; return`.
  4. Wybór portu: `len==1`→`instances[0]`; `>1`→`QInputDialog.getItem(self,"Instancja AC","Wybierz dokument:",
     [f"{i['port']} — {i['projectName']}" for i in instances], current=idx(_ac_target_port), editable=False)`;
     Anuluj→return. Zapamiętaj `self._ac_target_port=port`.
  5. `tapir = TapirConnection(); tapir.use_port(port)`.
  6. `st = tapir.get_stories()`; `ok, msg = check_active_story(st["actStory"], st["firstStory"], st["lastStory"], storey)`.
     `if not ok:` `r = QMessageBox.warning(self,"Kondygnacja", msg + "\n\nWstawić MIMO TO?", Yes|Cancel, Cancel)`;
     `if r != Yes: return`.
  7. `result = export_house_to_archicad(layout, storey=storey, tapir=tapir, offset=self._archicad_offset)`.
  8. Status/`information` jak dziś + **port+nazwa**: `f"Dom [{storey}] → port {port} ({name}): {n_zones} stref…"`.
  9. `except Exception as e:` `QMessageBox.warning` (jak dziś).
  Import na górze handlera: `from bridge.tapir_connection import TapirConnection, check_active_story`;
  `from PyQt5.QtWidgets import QInputDialog` (jeśli nieobecny). Init `self._ac_target_port = None` w `__init__`.

- [ ] **Step 4: Run → PASS** (2 nowe + `test_house_export_dispatches_selected_storey` musi
  dalej przejść — jeśli stary test zakładał brak pickera, zaktualizuj go o monkeypatch
  list_instances/use_port/get_stories jak wyżej; **udokumentuj zmianę** w komentarzu testu).

- [ ] **Step 5: Regresja** — `import ui.main_window` OK; `tests/test_house_writer.py` 5 passed;
  `tests/test_ac_targeting.py` passed.

- [ ] **Step 6: Commit**
```bash
git add ui/main_window.py tests/test_house_export_gui.py
git commit -m "feat(ui): picker instancji AC + story-guard przed eksportem domu

>1 instancja → wybór dokumentu; aktywna kondygnacja ≠ wybrana → twarde ostrzeżenie.
Eksport leci do JEDNEJ znanej instancji; status z portem+nazwą.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Auto-switch story + „Wstaw cały dom" (1-klik) — LIVE-validated

> Decyzja Dawida: 1-klik wstawia obie kondygnacje. Eksport sam ustawia aktywną story.
> **Mechanizm switch + „create-lands-on-target" walidowane W AC (handoff)** — offline tylko
> parsowanie/logika na mockach. Fallback: gdy `activate_story` zwróci False → story-guard warn
> (manual 2-pass) — NIGDY ślepy zaułek.

**Files:** Modify `bridge/tapir_connection.py`, `ui/main_window.py`. Test: `tests/test_ac_targeting.py`.

**Interfaces (Produces):**
- `TapirConnection.story_navitems() -> dict[int, str]` — idx_story→navigatorItemId.guid.
  Źródło: standard `GetNavigatorItemTree(NavigatorTreeId(type="ProjectMap"))` → węzły
  `type=="StoryItem"` (top-down) → `reversed` = idx rosnące (Parter=idx0). (Nazwy pomocniczo.)
- `TapirConnection.activate_story(target_index: int) -> bool` — `ChangeWindow` do nav-itemu story
  (**dokładny kształt param nailowany LIVE** — `{navigatorItemId:{guid}}` rzuca schema-reject;
  próbować warianty / id z `GetStoryNavigatorItems`); po przełączeniu `get_stories()["actStory"]
  == target_index` → True, inaczej False. ALT do rozważenia live: `SetDetailsOfElements floorIndex`
  retarget po eksporcie (jeśli ChangeWindow nie da się okiełznać).
- GUI: przycisk „Wstaw cały dom" (lub auto-switch na bazie `house_storey_combo` + opcja „obie").
  Pętla `storeys = ["parter"] + (["poddasze"] if not single else [])`; per storey: `target =
  firstStory` / `firstStory+1`; `if tapir.activate_story(target): export_house_to_archicad(..., storey)`
  `else: QMessageBox.warning(story-guard fallback)`.

- [ ] **Step 1: Failing offline tests** — `story_navitems` (mock `GetNavigatorItemTree`+
  `GetStoryNavigatorItems` → {0:guidParter,1:..}); `activate_story` True gdy mock get_stories
  zwraca actStory=target po ChangeWindow, False inaczej; GUI loop dispatch (mock activate_story
  True→export wołany per storey; False→export NIE wołany + warning).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `story_navitems` + `activate_story` (mechanizm jak wyżej; ChangeWindow
  param = best-guess + try/except, log surowego błędu dla nailingu live) + GUI loop „obie kondygnacje".
- [ ] **Step 4: Run → PASS** (offline, mocki).
- [ ] **Step 5: Regresja** (import + house_writer + ac_targeting).
- [ ] **Step 6: Commit** `feat(bridge+ui): auto-switch story (activate_story) + 1-klik obie kondygnacje`.
- [ ] **Step 7: LIVE handoff (Dawid):** nail kształt param `ChangeWindow` (wklej surowy błąd jeśli
  reject), potwierdź `actStory` zmienia się + strefy/ściany/okna lądują na właściwej story. Jeśli
  ChangeWindow nie do okiełznania → przełącz na `SetDetailsOfElements floorIndex` (ten sam interfejs
  `activate_story`/retarget, inna implementacja).

---

### Task 4: Diag `ac_story_diag.py` + STATE + handoff

**Files:** Modify `notebooks/ac_story_diag.py`, `docs/STATE.md`.

- [ ] **Step 1:** W `inventory(port)` dołóż na górze: `proj = _tapir(conn,"GetProjectInfo")` →
  print `projectName`; `st = _tapir(conn,"GetStories")` → print `actStory` + nazwy story. W
  sekcji DOM-* dołóż jawną linię: `>>> DOM-* na porcie {port} (proj '{name}'), story-z-zCoordinate`.
  (Helper `_tapir(conn,name,params={})` = `ExecuteAddOnCommand(AddOnCommandId("TapirCommand",name),params)`.)
  Notebook — **bez** pytest (Dawid odpala live).
- [ ] **Step 2:** Smoke offline: `PYTHONPATH=. venv/bin/python -c "import ast; ast.parse(open('notebooks/ac_story_diag.py').read())"` (składnia OK).
- [ ] **Step 3:** Update `docs/STATE.md` — nowy wpis NEXT SESSION: picker instancji + story-guard
  WDROŻONE (kod+offline-testy), okna-robustness log; **PENDING live Dawid** (2-pass + diag);
  OTWARTE PYTANIE okna-host poddasza; drzwi-poddasze MVP-gap.
- [ ] **Step 4: Commit** (`docs(state)` + `chore(notebooks)`).

---

## Self-Review

- Decyzja 1 (picker) → Task 1 `list_instances/use_port` + Task 2 QInputDialog + `_ac_target_port`. ✓
- Decyzja 2 (story-guard twardy) → `check_active_story` (Task 1, table-test) + Task 2 modal block/override. ✓
- Decyzja 3 (manual 2-pass zostaje; auto-switch poza MVP) → brak floorIndex/ChangeWindow w planie. ✓
- Decyzja 4 (okna) → primary=guard+instancja; secondary=log get_all_walls (Task 1 Step 6); OTWARTE PYTANIE = live (handoff). ✓
- Decyzja 5 (diag) → Task 3. ✓  Decyzja 6 (drzwi MVP-gap) → nieruszane. ✓
- Mózg/mieszkania nietknięte → Global Constraints + regresje (Task1 Step5, Task2 Step5). ✓

## Execution Handoff (Dawid, live w AC — bramka finalna)

1. Zostaw potrzebne instancje AC otwarte (test pickera: 2 instancje). Tryb „Dom", wygeneruj dom.
2. W AC ustaw aktywną kondygnację = PARTER. GUI „Parter" → „Wstaw do AC" → w pickerze wybierz
   właściwy dokument. (Guard przepuści, bo aktywna=parter.)
3. **Od razu** odpal `PYTHONPATH=. venv/bin/python notebooks/ac_story_diag.py` (PRZED undo) — wklej output.
4. W AC przełącz aktywną kondygnację = PODDASZE. GUI „Poddasze" → „Wstaw do AC" → ten sam dokument.
   (Guard: jeśli zapomnisz przełączyć → twarde ostrzeżenie.)
5. Odpal diag ponownie — potwierdź: DOM-PARTER-* na story 0 i DOM-PODDASZE-* na story 1, **ten sam port**.
6. Oceń okiem: strefy/ściany/okna/etykiety obu kondygnacji. **Okna poddasza** = jeśli 0 →
   log „get_all_walls 0" + OTWARTE PYTANIE (host okien) → wtedy systematic-debugging na żywo.
   Drzwi poddasza niepełne = znany MVP-gap.
