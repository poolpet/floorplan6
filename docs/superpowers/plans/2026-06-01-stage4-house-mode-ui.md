# House Mode UI (Stage 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a parallel "single-family house (2-storey, furnished)" path to the Stage 4 tab, toggled by a mode radio, without changing the existing M1–M5 apartment path.

**Architecture:** A new GUI-free module `viz/house_preview.py` orchestrates the already-built engine (`core.house_layout.generate_house` → `core.furniture.place_furniture` → `viz.plan_renderer.render_two_storey`) and is unit-tested without PyQt. `ui/main_window.py` gains a mode radio, a `HouseGenerateWorker(QThread)`, and branch methods; apartment widgets are wrapped in a container that hides in house mode. House generation produces ONE 2-storey layout (no variants/score); export is PNG only (To-ArchiCAD disabled).

**Tech Stack:** Python 3.13, PyQt5, OR-Tools CP-SAT (existing), Shapely, matplotlib (Agg in tests, Qt5Agg in app), pytest.

**Rules guard (CLAUDE.md):** This is UI/orchestration only — does NOT touch `cpsat_solver`, `validator`, WT caps (F2 łazienka ≤5 m²), or any F1–F10 constraint. B1 (2 fails = rewrite), B8 (verify before done: pytest + manual GUI run + screenshot).

---

## File Structure

- **Create** `viz/house_preview.py` — GUI-free orchestration: `furnish_layout`, `house_details_text`, `render_house_figure`.
- **Create** `tests/test_house_preview.py` — unit tests for the new module (Agg backend, no Qt).
- **Modify** `ui/main_window.py` — imports, `__init__` state, `HouseGenerateWorker`, mode radio, STEP 2 container restructure, `_on_mode_changed`, `_input_polygon_entry`, `_on_generate` branch, `_on_generate_house`/`_on_house_ready`/`_show_house`, `_export_png` branch, `_on_error` progress reset.
- **Modify** `docs/STATE.md`, `NEXT_SESSION.md` — sync after verification.

---

## Task 1: New GUI-free orchestration module `viz/house_preview.py`

**Files:**
- Create: `viz/house_preview.py`
- Test: `tests/test_house_preview.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_house_preview.py`:

```python
"""GUI-free tests for viz/house_preview.py (Plan 3 — house mode orchestration)."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from shapely.geometry import Polygon

from core.house_layout import TwoStoreyLayout
from core.models import Room, RoomSpec, Strefa
from viz.house_preview import furnish_layout, house_details_text, render_house_figure


def _room(room_id, nazwa, strefa, w, h, x=0.0, y=0.0):
    spec = RoomSpec(id=room_id, nazwa=nazwa, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _layout():
    parter = [
        _room("salon", "Salon", Strefa.DZIENNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", "Hol", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
    ]
    pietro = [
        _room("sypialnia_1", "Sypialnia 1", Strefa.NOCNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", "Hol", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
    ]
    return TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                           stair_core=(4.0, 0.0, 2.5, 3.0), boundary=None)


def test_furnish_layout_toggle():
    layout = _layout()
    pf_on, gf_on = furnish_layout(layout, with_furniture=True)
    pf_off, gf_off = furnish_layout(layout, with_furniture=False)
    assert len(pf_on) > 0          # salon dostaje meble
    assert len(gf_on) > 0          # sypialnia dostaje meble
    assert pf_off == [] and gf_off == []


def test_house_details_text_has_both_storeys():
    text = house_details_text(_layout())
    assert "PARTER" in text and "PIĘTRO" in text
    assert "Salon" in text and "Sypialnia 1" in text


def test_render_house_figure_two_panels():
    fig = render_house_figure(_layout(), with_furniture=True, show=False)
    assert len(fig.axes) >= 2
    plt.close(fig)


def test_render_house_figure_writes_png(tmp_path):
    out = tmp_path / "house.png"
    fig = render_house_figure(_layout(), with_furniture=False, save_path=out, show=False)
    assert out.exists() and out.stat().st_size > 0
    plt.close(fig)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_house_preview.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'viz.house_preview'`.

- [ ] **Step 3: Write the module**

Create `viz/house_preview.py`:

```python
"""Stage 4 — orkiestracja podglądu domu jednorodzinnego (GUI-free).

Składa gotowe klocki: generate_house (core, woła worker w UI) → place_furniture
(core) → render_two_storey (viz). Trzymane osobno od ui/main_window.py, żeby
logikę dało się testować bez PyQt — testy GUI padają headless (docs/STATE.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey


def furnish_layout(layout, with_furniture: bool) -> tuple[list, list]:
    """(parter_furniture, pietro_furniture). Puste listy gdy with_furniture=False."""
    if not with_furniture:
        return [], []
    return place_furniture(layout.parter_rooms), place_furniture(layout.pietro_rooms)


def house_details_text(layout) -> str:
    """Opis tekstowy domu: obie kondygnacje + pokoje/powierzchnie (panel UI)."""
    area = getattr(getattr(layout, "boundary", None), "area", None)
    if area is None:
        area = sum(r.area for r in layout.parter_rooms)
    lines = ["Dom jednorodzinny 2-kondygnacyjny", f"Obrys/kondygnacja: {area:.1f} m²"]
    for storey_title, rooms in (("PARTER", layout.parter_rooms),
                                ("PIĘTRO", layout.pietro_rooms)):
        lines.append("")
        lines.append(f"{storey_title}:")
        for r in rooms:
            lines.append(f"  {r.spec.nazwa:28s} {r.area:5.1f} m²")
    return "\n".join(lines)


def render_house_figure(layout, with_furniture: bool, title: Optional[str] = None,
                        save_path: Optional[Path] = None, show: bool = False):
    """Renderuj gotowy TwoStoreyLayout jako 2-panelowy rzut (PARTER | PIĘTRO)."""
    parter_furniture, pietro_furniture = furnish_layout(layout, with_furniture)
    return render_two_storey(
        layout,
        parter_furniture=parter_furniture,
        pietro_furniture=pietro_furniture,
        title=title,
        save_path=save_path,
        show=show,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_house_preview.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add viz/house_preview.py tests/test_house_preview.py
git commit -m "feat(stage4): viz/house_preview — GUI-free house render orchestration

furnish_layout / house_details_text / render_house_figure wrap the existing
generate_house+place_furniture+render_two_storey engine for the UI. 4 tests.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: UI plumbing — imports, state, `HouseGenerateWorker`

**Files:**
- Modify: `ui/main_window.py` (imports block ~21-27, `__init__` ~189-196, after `GenerateWorker` ~181)

- [ ] **Step 1: Add PyQt widgets to the imports**

In `ui/main_window.py`, replace this exact block:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QStatusBar, QScrollArea, QSplitter, QTextEdit,
    QFileDialog, QMessageBox, QProgressBar, QCheckBox, QDialog,
    QDialogButtonBox, QGridLayout, QStackedWidget, QTabWidget,
)
```

with:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QStatusBar, QScrollArea, QSplitter, QTextEdit,
    QFileDialog, QMessageBox, QProgressBar, QCheckBox, QDialog,
    QDialogButtonBox, QGridLayout, QStackedWidget, QTabWidget,
    QRadioButton, QButtonGroup,
)
```

- [ ] **Step 2: Add house engine imports**

Replace this exact block:

```python
from core.variant_generator import generate_variants
from core.models import FloorPlan, WallType
from viz.plan_renderer import render_floor_plan
```

with:

```python
from core.variant_generator import generate_variants
from core.house_layout import generate_house
from core.models import FloorPlan, WallType
from viz.plan_renderer import render_floor_plan
from viz.house_preview import render_house_figure, house_details_text
```

- [ ] **Step 3: Add `__init__` state**

Replace this exact block:

```python
        self.variants: list[FloorPlan] = []
        self.current_idx = 0
        self.worker = None
```

with:

```python
        self.variants: list[FloorPlan] = []
        self.current_idx = 0
        self.worker = None
        self.house_worker = None
        self._house_layout = None
        self._with_furniture = True
```

- [ ] **Step 4: Add the `HouseGenerateWorker` class**

Immediately after the `GenerateWorker` class (which ends with `self.error.emit(str(e))`), and before `class MainWindow(QMainWindow):`, insert:

```python
class HouseGenerateWorker(QThread):
    """Worker thread: generuje dom 2-kondygnacyjny (generate_house). 1 układ."""
    finished = pyqtSignal(object)  # TwoStoreyLayout
    error = pyqtSignal(str)

    def __init__(self, polygon, entry_point):
        super().__init__()
        self.polygon = polygon
        self.entry_point = entry_point

    def run(self):
        try:
            layout = generate_house(self.polygon, self.entry_point)
            self.finished.emit(layout)
        except Exception as e:
            self.error.emit(str(e))


```

- [ ] **Step 5: Verify the module still imports (syntax + names)**

Run: `python3 -c "import ui.main_window; print('import OK')"`
Expected: prints `import OK` (no SyntaxError / ImportError).

- [ ] **Step 6: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(stage4): UI plumbing for house mode (imports, state, HouseGenerateWorker)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Mode radio + STEP 2 container restructure

**Files:**
- Modify: `ui/main_window.py` (`_build_ui`: left panel ~246-247 and STEP 2 ~327-369)

- [ ] **Step 1: Insert the mode radio above STEP 1**

Replace this exact block:

```python
        # --- Lewy panel ---
        left = QVBoxLayout()

        # ══════════ STEP 1: Load outline ══════════
```

with:

```python
        # --- Lewy panel ---
        left = QVBoxLayout()

        # ══════════ Tryb: mieszkanie / dom ══════════
        mode_group = QGroupBox("Tryb")
        mode_lay = QVBoxLayout(mode_group)
        self.mode_apartment_radio = QRadioButton("Mieszkanie w bloku (M1-M5)")
        self.mode_house_radio = QRadioButton("Dom jednorodzinny (2-kond.)")
        self.mode_apartment_radio.setChecked(True)
        self.mode_btn_group = QButtonGroup(self)
        self.mode_btn_group.addButton(self.mode_apartment_radio)
        self.mode_btn_group.addButton(self.mode_house_radio)
        mode_lay.addWidget(self.mode_apartment_radio)
        mode_lay.addWidget(self.mode_house_radio)
        self.mode_apartment_radio.toggled.connect(self._on_mode_changed)
        left.addWidget(mode_group)

        # ══════════ STEP 1: Load outline ══════════
```

- [ ] **Step 2: Wrap apartment options in a container + add house options**

Replace this exact block (the whole STEP 2):

```python
        # ══════════ STEP 2: Type + options ══════════
        step2 = QGroupBox("2. Type and options")
        step2_lay = QVBoxLayout(step2)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["M1", "M2", "M3", "M4", "M5"])
        self.type_combo.setCurrentIndex(1)
        type_row.addWidget(self.type_combo)
        type_row.addWidget(QLabel("Variants:"))
        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 10)
        self.variants_spin.setValue(5)
        type_row.addWidget(self.variants_spin)
        step2_lay.addLayout(type_row)

        self.wc_check = QCheckBox("Separate WC (M3+, M4+)")
        self.wc_check.setChecked(False)
        self.wc_check.setToolTip(
            "Check for M3_wc/M4_2laz (separate WC). Unchecked = M*_standard."
        )
        step2_lay.addWidget(self.wc_check)

        score_row = QHBoxLayout()
        score_row.addWidget(QLabel("Min score:"))
        self.min_score_spin = QDoubleSpinBox()
        self.min_score_spin.setRange(0.0, 1.0)
        self.min_score_spin.setSingleStep(0.05)
        self.min_score_spin.setValue(0.5)
        self.min_score_spin.setToolTip(
            "Variant quality threshold — lower = more solutions but worse quality. "
            "Rules F1-F10 always respected."
        )
        score_row.addWidget(self.min_score_spin)
        step2_lay.addLayout(score_row)

        self.facades_btn = QPushButton("Edit facades and entry...")
        self.facades_btn.setEnabled(False)
        self.facades_btn.clicked.connect(self._edit_facades)
        step2_lay.addWidget(self.facades_btn)

        left.addWidget(step2)
```

with:

```python
        # ══════════ STEP 2: Type + options ══════════
        step2 = QGroupBox("2. Type and options")
        step2_lay = QVBoxLayout(step2)

        # --- Opcje mieszkania (kontener, przełączany trybem) ---
        self.apt_options = QWidget()
        apt_opt_lay = QVBoxLayout(self.apt_options)
        apt_opt_lay.setContentsMargins(0, 0, 0, 0)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["M1", "M2", "M3", "M4", "M5"])
        self.type_combo.setCurrentIndex(1)
        type_row.addWidget(self.type_combo)
        type_row.addWidget(QLabel("Variants:"))
        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 10)
        self.variants_spin.setValue(5)
        type_row.addWidget(self.variants_spin)
        apt_opt_lay.addLayout(type_row)

        self.wc_check = QCheckBox("Separate WC (M3+, M4+)")
        self.wc_check.setChecked(False)
        self.wc_check.setToolTip(
            "Check for M3_wc/M4_2laz (separate WC). Unchecked = M*_standard."
        )
        apt_opt_lay.addWidget(self.wc_check)

        score_row = QHBoxLayout()
        score_row.addWidget(QLabel("Min score:"))
        self.min_score_spin = QDoubleSpinBox()
        self.min_score_spin.setRange(0.0, 1.0)
        self.min_score_spin.setSingleStep(0.05)
        self.min_score_spin.setValue(0.5)
        self.min_score_spin.setToolTip(
            "Variant quality threshold — lower = more solutions but worse quality. "
            "Rules F1-F10 always respected."
        )
        score_row.addWidget(self.min_score_spin)
        apt_opt_lay.addLayout(score_row)

        self.facades_btn = QPushButton("Edit facades and entry...")
        self.facades_btn.setEnabled(False)
        self.facades_btn.clicked.connect(self._edit_facades)
        apt_opt_lay.addWidget(self.facades_btn)

        step2_lay.addWidget(self.apt_options)

        # --- Opcje domu (kontener, domyślnie ukryty) ---
        self.house_options = QWidget()
        house_opt_lay = QVBoxLayout(self.house_options)
        house_opt_lay.setContentsMargins(0, 0, 0, 0)
        self.house_program_label = QLabel("Program: dom 2-kond. (parter + piętro)")
        self.house_program_label.setStyleSheet("color: #555; font-style: italic;")
        house_opt_lay.addWidget(self.house_program_label)
        self.furniture_check = QCheckBox("Meble")
        self.furniture_check.setChecked(True)
        self.furniture_check.setToolTip("Rozstaw kanoniczne meble w pokojach (parter + piętro).")
        house_opt_lay.addWidget(self.furniture_check)
        step2_lay.addWidget(self.house_options)
        self.house_options.setVisible(False)

        left.addWidget(step2)
```

- [ ] **Step 3: Verify import (the `_on_mode_changed` slot does not exist yet — that is fine, it is only connected, not called at import)**

Run: `python3 -c "import ui.main_window; print('import OK')"`
Expected: prints `import OK`.

> Note: `_on_mode_changed` is added in Task 4. The `.toggled.connect(self._on_mode_changed)` line is only evaluated when `_build_ui` runs (GUI launch), not at import. Do NOT launch the GUI between Task 3 and Task 4.

- [ ] **Step 4: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(stage4): mode radio + apartment/house option containers in Stage 4 tab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Mode handler, generation branch, house display, export branch

**Files:**
- Modify: `ui/main_window.py` (replace `_on_generate` ~497-547; edit `_on_error` ~595-600; edit `_export_png` ~656-668)

- [ ] **Step 1: Replace `_on_generate` with the mode handler + helper + branch + house methods**

Replace this exact block (the entire current `_on_generate`):

```python
    def _on_generate(self):
        w = self.width_spin.value()
        h = self.height_spin.value()
        ex = self.entry_x_spin.value()
        ey = self.entry_y_spin.value()
        mtype = self.type_combo.currentText()
        max_v = self.variants_spin.value()
        wall_types = None
        template_filter = None

        # Filtr szablonów wg checkboxa "Osobny WC"
        if mtype == "M3":
            template_filter = ["M3_wc"] if self.wc_check.isChecked() else ["M3_standard"]
        elif mtype == "M4":
            template_filter = ["M4_2laz"] if self.wc_check.isChecked() else ["M4_standard"]

        if self._imported_polygon is not None:
            # Użyj oryginalnego polygonu z ArchiCAD
            polygon = self._imported_polygon
            ex, ey = self._imported_entry or (ex, ey)
            wall_types = self._imported_wall_types
        elif self.notch_group.isChecked():
            nx = self.notch_x_spin.value()
            ny = self.notch_y_spin.value()
            nw = self.notch_w_spin.value()
            nh = self.notch_h_spin.value()
            polygon = Polygon([
                (0, 0), (w, 0),
                (w, ny), (nx, ny),
                (nx, ny + nh), (0, ny + nh),
            ])
        else:
            polygon = Polygon([(0, 0), (w, 0), (w, h), (0, h)])

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.statusBar().showMessage(f"Generating {mtype} {w}x{h}m...")

        # min_score=0 w workerze — filtrujemy w UI żeby pokazać ile odrzucono
        self._min_score_threshold = self.min_score_spin.value()
        self.worker = GenerateWorker(
            polygon, (ex, ey), mtype, max_v,
            wall_types=wall_types, template_filter=template_filter,
            min_score=0.0,
        )
        self.worker.finished.connect(self._on_variants_ready)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.start()
```

with:

```python
    def _on_mode_changed(self, *args):
        """Przełącz UI między trybem mieszkania (M1-M5) a domu jednorodzinnego."""
        house = self.mode_house_radio.isChecked()
        self.apt_options.setVisible(not house)
        self.house_options.setVisible(house)
        # reset wyniku przy zmianie trybu
        self.variants = []
        self.current_idx = 0
        self._house_layout = None
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.archicad_btn.setEnabled(False)
        self.variant_label.setText("—")
        self.details.clear()
        self.image_label.setText(
            "Tryb domu — kliknij 'Generate' (obrys + entry z kroku 1)." if house
            else "Click 'Load outline' or 'Generate layouts' to start"
        )
        self.preview_stack.setCurrentWidget(self.image_label)
        self.archicad_btn.setToolTip(
            "Eksport domu do AC — później (shell C++)." if house else ""
        )

    def _input_polygon_entry(self):
        """(polygon, entry_point, wall_types) z aktualnych pól (import / notch / prostokąt)."""
        w = self.width_spin.value()
        h = self.height_spin.value()
        ex = self.entry_x_spin.value()
        ey = self.entry_y_spin.value()
        wall_types = None
        if self._imported_polygon is not None:
            polygon = self._imported_polygon
            ex, ey = self._imported_entry or (ex, ey)
            wall_types = self._imported_wall_types
        elif self.notch_group.isChecked():
            nx = self.notch_x_spin.value()
            ny = self.notch_y_spin.value()
            nw = self.notch_w_spin.value()
            nh = self.notch_h_spin.value()
            polygon = Polygon([
                (0, 0), (w, 0),
                (w, ny), (nx, ny),
                (nx, ny + nh), (0, ny + nh),
            ])
        else:
            polygon = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
        return polygon, (ex, ey), wall_types

    def _on_generate(self):
        if self.mode_house_radio.isChecked():
            self._on_generate_house()
            return

        w = self.width_spin.value()
        h = self.height_spin.value()
        mtype = self.type_combo.currentText()
        max_v = self.variants_spin.value()
        template_filter = None

        # Filtr szablonów wg checkboxa "Osobny WC"
        if mtype == "M3":
            template_filter = ["M3_wc"] if self.wc_check.isChecked() else ["M3_standard"]
        elif mtype == "M4":
            template_filter = ["M4_2laz"] if self.wc_check.isChecked() else ["M4_standard"]

        polygon, (ex, ey), wall_types = self._input_polygon_entry()

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.statusBar().showMessage(f"Generating {mtype} {w}x{h}m...")

        # min_score=0 w workerze — filtrujemy w UI żeby pokazać ile odrzucono
        self._min_score_threshold = self.min_score_spin.value()
        self.worker = GenerateWorker(
            polygon, (ex, ey), mtype, max_v,
            wall_types=wall_types, template_filter=template_filter,
            min_score=0.0,
        )
        self.worker.finished.connect(self._on_variants_ready)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.start()

    def _on_generate_house(self):
        polygon, entry, _wall_types = self._input_polygon_entry()
        self._with_furniture = self.furniture_check.isChecked()
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")
        self.progress_bar.setRange(0, 0)   # busy — generate_house nie ma callbacku
        self.progress_bar.setVisible(True)
        self.statusBar().showMessage("Generating house (parter + piętro)...")
        self.house_worker = HouseGenerateWorker(polygon, entry)
        self.house_worker.finished.connect(self._on_house_ready)
        self.house_worker.error.connect(self._on_error)
        self.house_worker.start()

    def _on_house_ready(self, layout):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.archicad_btn.setEnabled(False)
        if not getattr(layout, "ok", False):
            self._house_layout = None
            self.export_btn.setEnabled(False)
            self.variant_label.setText("—")
            self.statusBar().showMessage(f"Dom: {layout.message}")
            self.image_label.setText(
                f"Nie udało się wygenerować domu:\n\n{layout.message}"
            )
            self.preview_stack.setCurrentWidget(self.image_label)
            self.details.clear()
            return
        self._house_layout = layout
        self.export_btn.setEnabled(True)
        self.variant_label.setText("Dom (PARTER + PIĘTRO)")
        self.statusBar().showMessage("Wygenerowano dom 2-kondygnacyjny.")
        self._show_house()

    def _show_house(self):
        layout = self._house_layout
        if layout is None:
            return
        fig = render_house_figure(
            layout, with_furniture=self._with_furniture,
            title="Dom jednorodzinny 2-kondygnacyjny", show=False,
        )
        pixmap = self._fig_to_pixmap(fig)
        plt.close(fig)
        scaled = pixmap.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.preview_stack.setCurrentWidget(self.image_label)
        self.details.setText(house_details_text(layout))
```

- [ ] **Step 2: Reset progress range in `_on_error` (shared by both workers)**

Replace this exact block:

```python
    def _on_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)
```

with:

```python
    def _on_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)
```

- [ ] **Step 3: Branch `_export_png` for house mode**

Replace this exact block:

```python
    def _export_png(self):
        if not self.variants:
            return
        plan = self.variants[self.current_idx]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", f"floorplan_v{self.current_idx+1}.png",
            "PNG (*.png)",
        )
        if path:
            fig = render_floor_plan(plan, title=f"Variant {self.current_idx+1}", show=False)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            self.statusBar().showMessage(f"Saved: {path}")
```

with:

```python
    def _export_png(self):
        if self.mode_house_radio.isChecked():
            if self._house_layout is None:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Save PNG", "dom_2kond.png", "PNG (*.png)",
            )
            if path:
                fig = render_house_figure(
                    self._house_layout, with_furniture=self._with_furniture,
                    title="Dom jednorodzinny 2-kondygnacyjny", show=False,
                )
                fig.savefig(path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                self.statusBar().showMessage(f"Saved: {path}")
            return

        if not self.variants:
            return
        plan = self.variants[self.current_idx]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", f"floorplan_v{self.current_idx+1}.png",
            "PNG (*.png)",
        )
        if path:
            fig = render_floor_plan(plan, title=f"Variant {self.current_idx+1}", show=False)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            self.statusBar().showMessage(f"Saved: {path}")
```

- [ ] **Step 4: Verify import (all referenced slots now exist)**

Run: `python3 -c "import ui.main_window; print('import OK')"`
Expected: prints `import OK`.

- [ ] **Step 5: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(stage4): wire house generation, display and PNG export into Stage 4 tab

Mode radio routes Generate to generate_house (1 layout, 2 storeys, optional
furniture); result shown as PARTER|PIĘTRO; To-ArchiCAD disabled; PNG export
works. Apartment M1-M5 path unchanged (shared outline + extracted helper).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Full verification + manual GUI check + docs sync

**Files:**
- Modify: `docs/STATE.md`, `NEXT_SESSION.md`

- [ ] **Step 1: Run the new module tests**

Run: `python3 -m pytest tests/test_house_preview.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 2: Run the fast full suite (deselect slow subdivision test)**

Run: `python3 -m pytest tests -q -p no:cacheprovider -k "not subdivision and not 600 and not 800"`
Expected: all pass / xfail / skip as in baseline (319 passed, 29 skipped, 3 deselected, 1 xpassed, 0 failed — plus the 4 new = 323 passed). 0 failures.

- [ ] **Step 3: Manual GUI verification (headless GUI tests abort — must run with a display)**

Run: `python3 -m ui.main_window`
Then, by hand:
1. Stage 4 tab is shown. Mode = "Mieszkanie w bloku (M1-M5)" (default). Generate an M2 8×6 → variants render as today (regression check — apartment path intact).
2. Switch radio to "Dom jednorodzinny (2-kond.)". Confirm M-type/variants/score/facades controls disappear; "Program: dom 2-kond." label + "Meble" checkbox (checked) appear; preview resets.
3. Set W=8, H=10, Entry X=4, Y=0. Click "3. Generate layouts". After solve, a 2-panel PARTER | PIĘTRO render appears with furniture; details panel lists both storeys; prev/next disabled; "To ArchiCAD" disabled (hover shows tooltip).
4. Uncheck "Meble", Generate again → render has no furniture.
5. Click "Export PNG" → saves a 2-panel PNG. Open it to confirm.
6. Switch back to "Mieszkanie" → apartment controls return; preview resets.

Save a screenshot of step 3 to `notebooks/output/sfh_ui_house_mode.png` (window screenshot or the exported PNG).

- [ ] **Step 4: Update `docs/STATE.md`**

In `docs/STATE.md`, under "Session 15 additions" add a Session 16 note (keep style): Plan 3 UI done — Stage 4 tab has a mode radio (Mieszkanie / Dom jednorodzinny); house path wired to `generate_house` + `place_furniture` + `render_two_storey` via new GUI-free `viz/house_preview.py`; furniture toggle; PNG export; To-ArchiCAD disabled for houses; apartment M1-M5 path unchanged; 4 new tests (`tests/test_house_preview.py`). Move "Plan 3 UI NOT done" out of the "WHAT IS BROKEN / UNFINISHED" list. Update TEST STATUS count.

- [ ] **Step 5: Update `NEXT_SESSION.md`**

In `NEXT_SESSION.md`, add a "STAN po sesji 16" section: Plan 3 (UI house mode) done; remaining next steps = GAP jakości (decyzja Dawida), bliźniak/szeregowiec, polish mebli. Note branch `feat/sfh-furniture` still not merged/pushed (Dawid's decision).

- [ ] **Step 6: Commit**

```bash
git add docs/STATE.md NEXT_SESSION.md notebooks/output/sfh_ui_house_mode.png
git commit -m "docs(stage4): Plan 3 UI (house mode in Stage 4) done — STATE/NEXT_SESSION sync (Session 16)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes (covered)

- **Spec §3.1 module** → Task 1. **§3.2 worker** → Task 2. **§3.3 UI (radio/containers/branch/result/ok=False)** → Tasks 3–4. **§4 defaults** (default Mieszkanie, furniture default ON, no AC export, 2-storey fixed) → Tasks 3–4. **§6 tests** → Tasks 1 & 5. **§5 rules** → no solver/validator touched (verified by file list).
- **Out of scope (§8)** — twin/terraced, 1-storey, GAP fix, furniture polish, AC export: none implemented (correct).
- **Type consistency:** `render_house_figure(layout, with_furniture, title=, save_path=, show=)`, `house_details_text(layout)`, `furnish_layout(layout, with_furniture)`, `HouseGenerateWorker(polygon, entry_point)`, `generate_house(polygon, entry_point)` — consistent across tasks. State vars `self._house_layout`, `self._with_furniture`, `self.house_worker`, widgets `self.mode_house_radio`, `self.apt_options`, `self.house_options`, `self.furniture_check` — consistent.
```
