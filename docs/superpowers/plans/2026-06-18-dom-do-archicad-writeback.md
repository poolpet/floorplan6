# Dom → ArchiCAD write-back (MVP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wstawić wygenerowany dom (`TwoStoreyLayout`) do ArchiCAD — jedną kondygnację na aktywną kondygnację AC — reuse writera mieszkań; odblokować to z GUI.

**Architecture:** Nowy `bridge/house_writer.py::export_house_to_archicad(layout, storey)` buduje per-kondygnację `FloorPlan` z właściwym szablonem (`house_single_storey`/`house_parter`/`house_pietro`) i woła istniejący `export_plan_to_archicad` (reuse 1:1). GUI: przełącznik kondygnacji + odblokowany przycisk „Wstaw do AC" dyspozytorujący do nowego handlera.

**Tech Stack:** Python 3.13, pytest (monkeypatch), PyQt5, shapely. Pliki: `bridge/house_writer.py` (nowy), `ui/main_window.py`.

## Global Constraints

- Reuse istniejącego `bridge/plan_writer.export_plan_to_archicad` — ZERO zmian tego pliku.
- **MINA:** `export_plan_to_archicad` linia 94-95 sięga `plan.template.typ_mieszkania` TYLKO w gałęzi domyślnego `apartment_id`. Szablony domu tego pola nie mają → ZAWSZE przekazuj `apartment_id` jawnie.
- Meble WYŁĄCZONE dla domu (`include_furniture=False`).
- Wybór szablonu jak w `core/plan_contract.house_to_contract`: `single = not layout.pietro_rooms`; parter → `house_single_storey` (single) / `house_parter` (2-kond.); poddasze → `house_pietro`, boundary = `attic_boundary or boundary`.
- Komendy z roota: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest ...`
- Każdy commit kończ: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Weryfikacja na żywo w AC = Dawid (Claude nie ma AC) — patrz Execution Handoff.

---

### Task 1: `bridge/house_writer.py` — `export_house_to_archicad`

**Files:**
- Create: `bridge/house_writer.py`
- Test: `tests/test_house_writer.py` (Create)

**Interfaces:**
- Consumes: `export_plan_to_archicad(plan, tapir=None, offset=(0,0), include_furniture=True, apartment_id=None, ...) -> dict` (`bridge/plan_writer.py:46`); `load_all_templates()` (`core/template_selector.py`, zwraca obiekty z `.id`); `FloorPlan(boundary, template, rooms)` (`core/models.py`); `TwoStoreyLayout` z polami `parter_rooms`, `pietro_rooms`, `boundary`, opc. `attic_boundary`.
- Produces: `export_house_to_archicad(layout, storey="parter", tapir=None, offset=(0.0,0.0), include_furniture=False) -> dict` — dict z `export_plan_to_archicad` + klucz `"storey"`. `storey ∈ {"parter","poddasze"}`; poddasze na parterowcu → `ValueError`; nieznana kondygnacja → `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_house_writer.py
"""Dom → AC write-back: per-kondygnację FloorPlan z właściwym szablonem (reuse writera)."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import TwoStoreyLayout
from core.models import Room, RoomSpec, Strefa
import bridge.house_writer as hw


def _room(rid, strefa, w=3.0, h=3.0, x=0.0, y=0.0):
    spec = RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _two_storey():
    return TwoStoreyLayout(
        ok=True,
        parter_rooms=[_room("salon", Strefa.DZIENNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        pietro_rooms=[_room("sypialnia_1", Strefa.NOCNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        stair_core=(3.0, 0.0, 2.0, 3.0), boundary=None)


def _single_storey():
    return TwoStoreyLayout(
        ok=True,
        parter_rooms=[_room("salon", Strefa.DZIENNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        pietro_rooms=[], stair_core=(0.0, 0.0, 0.0, 0.0), boundary=None)


@pytest.fixture
def spy(monkeypatch):
    """Podmień writer mieszkań na szpiega — izoluje logikę house_writer od Tapira/AC."""
    captured = {}

    def fake(plan, **kw):
        captured["plan"] = plan
        captured["kw"] = kw
        return {"zones": ["z"], "walls": [], "doors": [], "labels": [], "windows": []}

    monkeypatch.setattr(hw, "export_plan_to_archicad", fake)
    return captured


def test_parter_uses_house_parter_template_and_rooms(spy):
    layout = _two_storey()
    res = hw.export_house_to_archicad(layout, storey="parter")
    assert spy["plan"].template.id == "house_parter"
    assert spy["plan"].rooms is layout.parter_rooms
    assert spy["kw"]["include_furniture"] is False
    assert spy["kw"]["apartment_id"] == "DOM-PARTER"
    assert res["storey"] == "parter"


def test_poddasze_uses_house_pietro_template_and_rooms(spy):
    layout = _two_storey()
    hw.export_house_to_archicad(layout, storey="poddasze")
    assert spy["plan"].template.id == "house_pietro"
    assert spy["plan"].rooms is layout.pietro_rooms
    assert spy["kw"]["apartment_id"] == "DOM-PODDASZE"


def test_single_storey_uses_house_single_storey_template(spy):
    hw.export_house_to_archicad(_single_storey(), storey="parter")
    assert spy["plan"].template.id == "house_single_storey"


def test_poddasze_on_parterowiec_raises(spy):
    with pytest.raises(ValueError):
        hw.export_house_to_archicad(_single_storey(), storey="poddasze")


def test_unknown_storey_raises(spy):
    with pytest.raises(ValueError):
        hw.export_house_to_archicad(_two_storey(), storey="garaz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_house_writer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bridge.house_writer'`

- [ ] **Step 3: Implement `bridge/house_writer.py`**

```python
"""Eksport domu (TwoStoreyLayout) do ArchiCAD — JEDNA kondygnacja na raz (2-pass).

Reuse writera mieszkań: buduje per-kondygnację FloorPlan z właściwym szablonem
(house_single_storey / house_parter / house_pietro) i woła export_plan_to_archicad.
Tapir tworzy na AKTYWNEJ kondygnacji AC — user przełącza kondygnację między przebiegami.
Meble domyślnie WYŁĄCZONE (Tapir nie obraca obiektów — zamrożone).
"""
from __future__ import annotations

from typing import Optional

from core.models import FloorPlan
from bridge.plan_writer import export_plan_to_archicad
from bridge.tapir_connection import TapirConnection


def export_house_to_archicad(
    layout,
    storey: str = "parter",
    tapir: Optional[TapirConnection] = None,
    offset: tuple[float, float] = (0.0, 0.0),
    include_furniture: bool = False,
) -> dict:
    """Wstaw JEDNĄ kondygnację domu do AC (na aktywną kondygnację AC).

    layout: TwoStoreyLayout. storey: "parter" | "poddasze". Parterowiec (brak
    pietro_rooms) → tylko "parter" (szablon house_single_storey).
    Zwraca dict z export_plan_to_archicad + klucz "storey".
    Reuse wyboru szablonu z core.plan_contract.house_to_contract.
    """
    from core.template_selector import load_all_templates  # lazy — jak w house_to_contract
    tpls = {t.id: t for t in load_all_templates()}
    single = not layout.pietro_rooms

    if storey == "parter":
        rooms = layout.parter_rooms
        boundary = layout.boundary
        template = tpls.get("house_single_storey") if single else tpls.get("house_parter")
    elif storey == "poddasze":
        if single:
            raise ValueError("Parterowiec nie ma poddasza — wybierz 'parter'.")
        rooms = layout.pietro_rooms
        boundary = getattr(layout, "attic_boundary", None) or layout.boundary
        template = tpls.get("house_pietro")
    else:
        raise ValueError(f"Nieznana kondygnacja: {storey!r} (parter|poddasze)")

    plan = FloorPlan(boundary=boundary, template=template, rooms=rooms)
    # apartment_id JAWNIE — szablon domu nie ma typ_mieszkania (export_plan_to_archicad:95).
    result = export_plan_to_archicad(
        plan,
        tapir=tapir,
        offset=offset,
        include_furniture=include_furniture,
        apartment_id=f"DOM-{storey.upper()}",
    )
    result["storey"] = storey
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_house_writer.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add bridge/house_writer.py tests/test_house_writer.py
git commit -m "feat(bridge): export_house_to_archicad — dom do AC per-kondygnację (reuse writera)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: GUI — odblokuj „Wstaw do AC" dla domu + przełącznik kondygnacji + dyspozytor

**Files:**
- Modify: `ui/main_window.py` (house_options ~424; `_on_mode_changed` 568/576; `_on_house_ready` 663/676-679; `_export_to_archicad` 1040)
- Modify: `docs/STATE.md`
- Test: `tests/test_house_export_gui.py` (Create)

**Interfaces:**
- Consumes: `export_house_to_archicad(layout, storey=, offset=) -> dict` (Task 1); `self._house_layout` (ustawiane w `_on_house_ready:675`); `self.mode_house_radio` (tryb dom); `self._archicad_offset` (offset eksportu, jak mieszkania:1047).
- Produces: `self.house_storey_combo` (QComboBox "Parter"/"Poddasze"); `self._export_house_to_archicad()` (handler); `_export_to_archicad` dyspozytoruje do niego w trybie dom.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_house_export_gui.py
"""GUI: przycisk 'Wstaw do AC' w trybie dom dyspozytoruje do export_house_to_archicad
z wybraną kondygnacją (bez AC — szpieg)."""
import pytest

pytest.importorskip("PyQt5")


def test_house_export_dispatches_selected_storey(qapp, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    import bridge.house_writer as hw
    from ui.main_window import MainWindow

    captured = {}
    monkeypatch.setattr(
        hw, "export_house_to_archicad",
        lambda layout, storey="parter", **kw: (captured.update(storey=storey),
                                               {"zones": [], "walls": [], "doors": [],
                                                "labels": [], "windows": []})[1],
    )
    # nie pokazuj modali w teście
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    w = MainWindow()
    w._archicad_offset = (0.0, 0.0)
    w.mode_house_radio.setChecked(True)          # tryb dom
    w._house_layout = object()                   # truthy „wygenerowany dom"
    w.house_storey_combo.setCurrentText("Poddasze")
    w._export_to_archicad()                       # przycisk „Wstaw do AC"
    assert captured.get("storey") == "poddasze"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_house_export_gui.py -q`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute 'house_storey_combo'` (lub dyspozytor nie woła house export).

- [ ] **Step 3a: Dodaj przełącznik kondygnacji do `house_options`**

W `_build_…` po `house_opt_lay.addWidget(self.furniture_check)` (linia 424), przed `step2_lay.addWidget(self.house_options)`:

```python
        self.furniture_check.setToolTip("Rozstaw kanoniczne meble w pokojach (parter + piętro).")
        house_opt_lay.addWidget(self.furniture_check)
        house_opt_lay.addWidget(QLabel("Kondygnacja → AC:"))
        self.house_storey_combo = QComboBox()
        self.house_storey_combo.addItems(["Parter", "Poddasze"])
        self.house_storey_combo.setToolTip(
            "Którą kondygnację wstawić. Ustaw TĘ SAMĄ aktywną kondygnację w ArchiCAD."
        )
        house_opt_lay.addWidget(self.house_storey_combo)
        step2_lay.addWidget(self.house_options)
```

(`QComboBox` i `QLabel` są już importowane — używane w `data_combo`/`house_program_label`.)

- [ ] **Step 3b: Odblokuj przycisk po wygenerowaniu domu (`_on_house_ready`)**

W gałęzi sukcesu (po `self._show_house()`, linia 679) dodaj odblokowanie:

```python
        self._house_layout = layout
        self.export_btn.setEnabled(True)
        self.archicad_btn.setEnabled(True)
        self.variant_label.setText("Dom (PARTER + PIĘTRO)")
        self.statusBar().showMessage("Wygenerowano dom 2-kondygnacyjny.")
        self._show_house()
```

(Linia 663 `self.archicad_btn.setEnabled(False)` na górze ZOSTAJE — to reset przed sukcesem/porażką.)

- [ ] **Step 3c: Popraw tooltip trybu dom (`_on_mode_changed`)**

Zamień blok tooltipa (576-578):

```python
        self.archicad_btn.setToolTip(
            "Wstaw wybraną kondygnację do AKTYWNEJ kondygnacji ArchiCAD." if house else ""
        )
```

- [ ] **Step 3d: Dyspozytor + handler w `_export_to_archicad`**

Na początku `_export_to_archicad` (linia 1040, przed `if not self.variants:`):

```python
    def _export_to_archicad(self):
        """Export current variant to ArchiCAD as zones."""
        if self.mode_house_radio.isChecked():
            self._export_house_to_archicad()
            return
        if not self.variants:
            return
```

Dodaj nowy handler (np. zaraz po `_export_to_archicad`):

```python
    def _export_house_to_archicad(self):
        """Wstaw wybraną kondygnację domu do AKTYWNEJ kondygnacji AC (2-pass)."""
        layout = getattr(self, "_house_layout", None)
        if layout is None:
            return
        storey = "poddasze" if self.house_storey_combo.currentText() == "Poddasze" else "parter"
        try:
            from bridge.house_writer import export_house_to_archicad
            result = export_house_to_archicad(layout, storey=storey, offset=self._archicad_offset)
            n_zones = len(result.get("zones", []))
            n_walls = len(result.get("walls", []))
            n_doors = len(result.get("doors", []))
            n_windows = len(result.get("windows", []))
            n_labels = len(result.get("labels", []))
            self.statusBar().showMessage(
                f"Dom [{storey}]: {n_zones} stref + {n_walls} ścian + {n_doors} drzwi "
                f"+ {n_windows} okien + {n_labels} etykiet"
            )
            QMessageBox.information(
                self, "ArchiCAD",
                f"Kondygnacja '{storey}' wstawiona na AKTYWNĄ kondygnację AC:\n\n"
                f"{n_zones} stref + {n_walls} ścianek + {n_doors} drzwi + {n_windows} okien "
                f"+ {n_labels} etykiet.\n\n"
                f"Druga kondygnacja: przełącz kondygnację w AC, wybierz ją tutaj, kliknij ponownie."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "ArchiCAD",
                f"Nie udało się wstawić domu do ArchiCAD:\n{e}\n\n"
                "Upewnij się, że ArchiCAD działa z Tapir Add-On."
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_house_export_gui.py -q`
Expected: PASS (1 passed). Jeśli `MainWindow()` pada na braku AC/zasobów w headless — udokumentuj i polegaj na weryfikacji Dawida (handler logic jest trywialny: combo→storey→export).

- [ ] **Step 5: Regression — GUI/import nie zepsute**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -c "import ui.main_window" && PYTHONPATH=. venv/bin/python -m pytest tests/test_house_writer.py -q`
Expected: import OK; 5 passed.

- [ ] **Step 6: Update `docs/STATE.md`** (nowy wpis: dom→AC write-back WDROŻONY na poziomie kodu, `bridge/house_writer.py` + GUI przełącznik kondygnacji + odblokowany przycisk; reuse writera mieszkań; meble off; **PENDING: weryfikacja na żywo Dawida w AC (2 przebiegi)**; to domyka lukę MVP #1).

- [ ] **Step 7: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add ui/main_window.py tests/test_house_export_gui.py docs/STATE.md
git commit -m "feat(ui): dom→AC z GUI — przełącznik kondygnacji + odblokowany eksport (2-pass)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Decyzja 1 (2-pass real stories) → `export_house_to_archicad` pisze JEDNĄ kondygnację; GUI combo + komunikat „przełącz kondygnację w AC" (Task 1+2). ✓
- Decyzja 2 (reuse writera Approach A) → buduje per-kondygnację FloorPlan → `export_plan_to_archicad` (Task 1). ✓
- Decyzja 3 (ręczny przełącznik) → `house_storey_combo` (Task 2). ✓
- Decyzja 4 (meble off / schody jako strefa / drzwi stock) → `include_furniture=False`; schody = zwykły pokój „schody" (strefa+ściany, brak osobnego kroku); drzwi przez `export_plan_to_archicad` template-path bez zmian. ✓
- Mina `typ_mieszkania` → `apartment_id="DOM-{storey}"` jawnie (Task 1 Step 3 + Global Constraints). ✓
- Weryfikacja offline (monkeypatch spy) + live Dawid → Task 1 testy + Execution Handoff. ✓
- Poza zakresem (kontrakt→Tapir, slaby, meble, auto-story) — niezaimplementowane, zgodnie ze spec. ✓

**Placeholder scan:** Task 2 Step 6 „update STATE" bez dosłownej treści — celowe (wpis redakcyjny), nie placeholder kodu. Cały kod (writer, test, GUI edits) podany w pełni. ✓

**Type consistency:** `export_house_to_archicad(layout, storey, tapir, offset, include_furniture) -> dict` identyczne w Task 1 (def + testy) i Task 2 (wywołanie `storey=`, `offset=`). `house_storey_combo` (QComboBox) spójne Task 2 Step 3a/3d + test. `apartment_id="DOM-PARTER"/"DOM-PODDASZE"` spójne (test asercje + impl `f"DOM-{storey.upper()}"`). ✓

## Execution Handoff

Plan: 2 taski, 1 nowy plik (`bridge/house_writer.py`) + 1 dotknięcie GUI + 2 nowe testy. Offline TDD pełne; **finalna bramka = Dawid na żywo w AC:**
1. Otwórz AC + Tapir; w GUI tryb „Dom jednorodzinny", wygeneruj dom.
2. W AC ustaw aktywną kondygnację = PARTER; w GUI wybierz „Parter" → „Wstaw do AC".
3. W AC przełącz aktywną kondygnację = PODDASZE; w GUI wybierz „Poddasze" → „Wstaw do AC".
4. Oceń: strefy/ściany/drzwi/okna/etykiety obu kondygnacji; zgłoś co źle (jak przy mieszkaniach S24-25).
