"""
FloorPlan6 — PyQt5 GUI.

Main window with two tabs:
  - Apartment Layout (Stage 4): per-apartment room layout
  - Floor Layout (Stage 3): divide a building floor into apartments + circulation

All UI strings in English to allow international collaboration.
"""
from __future__ import annotations

import sys
import io
from pathlib import Path

# Allow `python3 ui/main_window.py` from project root without PYTHONPATH.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QStatusBar, QScrollArea, QSplitter, QTextEdit,
    QFileDialog, QMessageBox, QProgressBar, QCheckBox, QDialog,
    QDialogButtonBox, QGridLayout, QStackedWidget, QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QPixmap, QImage

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from shapely.geometry import Polygon

from core.variant_generator import generate_variants
from core.models import FloorPlan, WallType
from viz.plan_renderer import render_floor_plan


class FacadeDialog(QDialog):
    """Dialog for manual wall classification (FACADE/INTERNAL) and entry position."""

    def __init__(self, polygon, entry_point, wall_types, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wall classification (facade / internal)")
        self.setMinimumWidth(560)

        self.points = list(polygon.exterior.coords)[:-1]
        self.n = len(self.points)
        self.wall_types = list(wall_types)  # mutowalna kopia
        self.entry_point = entry_point
        self.entry_edge_idx = self._closest_edge_to_point(entry_point)

        layout = QVBoxLayout(self)
        info = QLabel(
            "Mark FACADE edges (with daylight access).\n"
            "Internal edges (staircase, neighbor) — uncheck.\n"
            "Entry is on the edge marked (E)."
        )
        info.setStyleSheet("color: #444; padding: 4px;")
        layout.addWidget(info)

        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Edge</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Length</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Orientation</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Facade?</b>"), 0, 3)
        grid.addWidget(QLabel("<b>Entry</b>"), 0, 4)

        self.facade_checks = []
        self.entry_radios = []  # checkboxy zachowujące się jak radio
        for i in range(self.n):
            p1, p2 = self.points[i], self.points[(i + 1) % self.n]
            length = ((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) ** 0.5
            orient = self._edge_orientation(p1, p2)
            label = QLabel(f"#{i + 1}{' (E)' if i == self.entry_edge_idx else ''}")
            grid.addWidget(label, i + 1, 0)
            grid.addWidget(QLabel(f"{length:.2f} m"), i + 1, 1)
            grid.addWidget(QLabel(orient), i + 1, 2)
            cb = QCheckBox()
            cb.setChecked(self.wall_types[i] == WallType.FACADE)
            self.facade_checks.append(cb)
            grid.addWidget(cb, i + 1, 3)
            entry_cb = QCheckBox()
            entry_cb.setChecked(i == self.entry_edge_idx)
            entry_cb.toggled.connect(lambda checked, idx=i: self._on_entry_changed(idx, checked))
            self.entry_radios.append(entry_cb)
            grid.addWidget(entry_cb, i + 1, 4)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_entry_changed(self, idx, checked):
        if checked:
            for j, cb in enumerate(self.entry_radios):
                if j != idx:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
            self.entry_edge_idx = idx
        else:
            # Zapobiegnij odznaczeniu wszystkich
            self.entry_radios[idx].blockSignals(True)
            self.entry_radios[idx].setChecked(True)
            self.entry_radios[idx].blockSignals(False)

    def _closest_edge_to_point(self, pt):
        from shapely.geometry import LineString, Point
        ep = Point(pt)
        return min(
            range(self.n),
            key=lambda i: LineString([self.points[i], self.points[(i + 1) % self.n]]).distance(ep),
        )

    @staticmethod
    def _edge_orientation(p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        if abs(dx) > abs(dy):
            return "horizontal" + (" (S)" if dy >= 0 else " (N)") if dy != 0 else "horizontal"
        else:
            return "vertical" + (" (E)" if dx >= 0 else " (W)") if dx != 0 else "vertical"

    def get_results(self):
        """Returns (wall_types, entry_point) — entry = midpoint of selected edge."""
        wall_types = [
            WallType.FACADE if cb.isChecked() else WallType.INTERNAL
            for cb in self.facade_checks
        ]
        # Wymuś że krawędź wejściowa jest INTERNAL
        wall_types[self.entry_edge_idx] = WallType.INTERNAL
        p1 = self.points[self.entry_edge_idx]
        p2 = self.points[(self.entry_edge_idx + 1) % self.n]
        entry = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        return wall_types, entry


class GenerateWorker(QThread):
    """Worker thread for variant generation (keeps GUI responsive)."""
    finished = pyqtSignal(list)  # lista FloorPlan
    error = pyqtSignal(str)
    progress = pyqtSignal(int)  # 0-100%

    def __init__(self, polygon, entry_point, mtype, max_variants,
                 wall_types=None, template_filter=None, min_score=0.7):
        super().__init__()
        self.polygon = polygon
        self.entry_point = entry_point
        self.mtype = mtype
        self.max_variants = max_variants
        self.wall_types = wall_types
        self.template_filter = template_filter
        self.min_score = min_score

    def run(self):
        try:
            def on_progress(current, total):
                pct = int(current / total * 100) if total > 0 else 0
                self.progress.emit(min(pct, 99))

            variants = generate_variants(
                self.polygon, self.entry_point,
                self.mtype, self.max_variants,
                progress_callback=on_progress,
                wall_types=self.wall_types,
                template_filter=self.template_filter,
                min_score=self.min_score,
            )
            self.progress.emit(100)
            self.finished.emit(variants)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FloorPlan6 — Apartment Layout Generator")
        self.setMinimumSize(1100, 700)

        self.variants: list[FloorPlan] = []
        self.current_idx = 0
        self.worker = None
        self._imported_polygon = None  # Polygon z ArchiCAD (L-kształt etc.)
        self._imported_entry = None
        self._imported_wall_types = None  # ustawione w dialogu po imporcie
        self._importing = False  # flaga blokująca _clear_import podczas importu
        self._archicad_offset = (0.0, 0.0)  # offset do eksportu stref

        self._build_ui()

    def _build_ui(self):
        # Four-tab layout following the building design pipeline:
        # Stage 1 → Stage 2 → Stage 3 → Stage 4
        self._real_status_bar = self.statusBar()
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Stage 1 — plot analyser (Mode A whole-plot + Mode B subdivision)
        try:
            from ui.stage1_window import Stage1Widget
            self.stage1_widget = Stage1Widget(self)
            self.tabs.addTab(self.stage1_widget, "Stage 1: Plot Analyser")
            self.stage1_widget.apartment_layout_requested.connect(
                self._populate_stage4_from_stage1
            )
        except Exception as e:
            print(f"[WARN] Stage 1 tab unavailable: {e}")
            self.stage1_widget = None
            try:
                from ui.stage_placeholder import Stage1PlotPlaceholder
                self.tabs.addTab(Stage1PlotPlaceholder(self), "Stage 1: Plot Subdivision")
            except Exception:
                pass

        # Stage 2 — volumetric generator (still placeholder)
        try:
            from ui.stage_placeholder import Stage2VolumePlaceholder
            self.tabs.addTab(Stage2VolumePlaceholder(self), "Stage 2: Volume Generator")
        except Exception as e:
            print(f"[WARN] Stage 2 placeholder unavailable: {e}")

        # Stage 3 — floor layout
        try:
            from ui.floor_layout_window import FloorLayoutWidget
            self.tabs.addTab(FloorLayoutWidget(self), "Stage 3: Floor Layout")
        except Exception as e:
            print(f"[WARN] Stage 3 tab unavailable: {e}")

        # Stage 4 — apartment layout (this is the existing implementation)
        self.apt_tab = QWidget()
        self.tabs.addTab(self.apt_tab, "Stage 4: Apartment Layout")
        # Default to Stage 4 (the working part) so users see results immediately
        self.tabs.setCurrentWidget(self.apt_tab)

        main_layout = QHBoxLayout(self.apt_tab)

        # --- Lewy panel ---
        left = QVBoxLayout()

        # ══════════ STEP 1: Load outline ══════════
        step1 = QGroupBox("1. Outline")
        step1_lay = QVBoxLayout(step1)

        self.import_btn = QPushButton("Load outline from ArchiCAD")
        self.import_btn.setMinimumHeight(36)
        self.import_btn.setStyleSheet("font-weight: bold;")
        self.import_btn.clicked.connect(self._import_from_archicad)
        step1_lay.addWidget(self.import_btn)

        self.click_pick_btn = QPushButton(
            "Auto-detect z Inner Edge w AC"
        )
        self.click_pick_btn.setMinimumHeight(32)
        self.click_pick_btn.setToolTip(
            "Native AC workflow:\n"
            "1. Naciśnij ten przycisk.\n"
            "2. W AC: skrót Z (Zone tool) → klik w pustym miejscu mieszkania.\n"
            "3. Wróć tutaj i potwierdź OK.\n"
            "Skrypt znajdzie tę nową Zone, zaimportuje polygon, "
            "usunie temp Zone."
        )
        self.click_pick_btn.clicked.connect(self._import_from_inner_edge)
        step1_lay.addWidget(self.click_pick_btn)

        sep = QLabel("— or enter manually —")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: gray; font-size: 11px;")
        step1_lay.addWidget(sep)

        dims = QHBoxLayout()
        dims.addWidget(QLabel("W:"))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(4.0, 20.0)
        self.width_spin.setValue(8.0)
        self.width_spin.setSingleStep(0.5)
        dims.addWidget(self.width_spin)
        dims.addWidget(QLabel("H:"))
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(4.0, 20.0)
        self.height_spin.setValue(6.0)
        self.height_spin.setSingleStep(0.5)
        dims.addWidget(self.height_spin)
        step1_lay.addLayout(dims)

        entry_row = QHBoxLayout()
        entry_row.addWidget(QLabel("Entry X:"))
        self.entry_x_spin = QDoubleSpinBox()
        self.entry_x_spin.setRange(0.0, 20.0)
        self.entry_x_spin.setValue(4.0)
        self.entry_x_spin.setSingleStep(0.5)
        entry_row.addWidget(self.entry_x_spin)
        entry_row.addWidget(QLabel("Y:"))
        self.entry_y_spin = QDoubleSpinBox()
        self.entry_y_spin.setRange(0.0, 20.0)
        self.entry_y_spin.setValue(0.0)
        self.entry_y_spin.setSingleStep(0.5)
        entry_row.addWidget(self.entry_y_spin)
        step1_lay.addLayout(entry_row)

        notch_group = QGroupBox("Cut-out (L/U shape)")
        notch_group.setCheckable(True)
        notch_group.setChecked(False)
        notch_lay = QHBoxLayout(notch_group)
        for label, attr, default in [("X:", "notch_x_spin", 6.0), ("Y:", "notch_y_spin", 4.0),
                                      ("W:", "notch_w_spin", 3.0), ("H:", "notch_h_spin", 3.0)]:
            notch_lay.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 20.0)
            spin.setValue(default)
            spin.setSingleStep(0.5)
            setattr(self, attr, spin)
            notch_lay.addWidget(spin)
        self.notch_group = notch_group
        step1_lay.addWidget(notch_group)

        left.addWidget(step1)

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

        # ══════════ STEP 3: Generate ══════════
        self.generate_btn = QPushButton("3. Generate layouts")
        self.generate_btn.setMinimumHeight(44)
        self.generate_btn.setStyleSheet(
            "font-size: 15px; font-weight: bold; "
            "background-color: #4a90d9; color: white; border-radius: 4px;"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        left.addWidget(self.generate_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% — generating variants...")
        self.progress_bar.setVisible(False)
        left.addWidget(self.progress_bar)

        # ══════════ STEP 4: Navigation + export ══════════
        step4 = QGroupBox("4. Result")
        step4_lay = QVBoxLayout(step4)

        nav_lay = QHBoxLayout()
        self.prev_btn = QPushButton("<<")
        self.prev_btn.clicked.connect(self._prev_variant)
        self.prev_btn.setEnabled(False)
        nav_lay.addWidget(self.prev_btn)

        self.variant_label = QLabel("—")
        self.variant_label.setAlignment(Qt.AlignCenter)
        nav_lay.addWidget(self.variant_label)

        self.next_btn = QPushButton(">>")
        self.next_btn.clicked.connect(self._next_variant)
        self.next_btn.setEnabled(False)
        nav_lay.addWidget(self.next_btn)
        step4_lay.addLayout(nav_lay)

        export_lay = QHBoxLayout()
        self.export_btn = QPushButton("Export PNG")
        self.export_btn.clicked.connect(self._export_png)
        self.export_btn.setEnabled(False)
        export_lay.addWidget(self.export_btn)

        self.archicad_btn = QPushButton("To ArchiCAD")
        self.archicad_btn.clicked.connect(self._export_to_archicad)
        self.archicad_btn.setEnabled(False)
        export_lay.addWidget(self.archicad_btn)
        step4_lay.addLayout(export_lay)

        left.addWidget(step4)

        data_group = QGroupBox("Reference data")
        data_lay = QVBoxLayout(data_group)
        self.data_combo = QComboBox()
        self.data_combo.addItem("— select plan —")
        self._load_data_plans()
        data_lay.addWidget(self.data_combo)
        show_data_btn = QPushButton("Show plan from data")
        show_data_btn.clicked.connect(self._show_data_plan)
        data_lay.addWidget(show_data_btn)
        left.addWidget(data_group)

        # Szczegóły
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(180)
        left.addWidget(self.details)

        left.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(280)

        # --- Prawy panel: stack [QLabel dla wariantów, FigureCanvas dla preview] ---
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(600, 500)
        self.image_label.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        self.image_label.setText("Click 'Load outline' or 'Generate layouts' to start")

        self.preview_fig = Figure(figsize=(10, 8))
        self.preview_canvas = FigureCanvasQTAgg(self.preview_fig)
        self.preview_canvas.mpl_connect("button_press_event", self._on_canvas_click)

        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.image_label)
        self.preview_stack.addWidget(self.preview_canvas)
        self.preview_stack.setCurrentIndex(0)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.preview_stack, stretch=1)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Aktualizuj entry_x gdy zmieni się width + wyczyść import
        def _on_width_changed(v):
            if not self._importing:
                self.entry_x_spin.setValue(v / 2)
            self._clear_import()

        self.width_spin.valueChanged.connect(_on_width_changed)
        self.height_spin.valueChanged.connect(lambda v: self._clear_import())

    def _edit_facades(self, auto_open=False):
        """Open manual wall classification dialog."""
        if self._imported_polygon is None or self._imported_wall_types is None:
            return
        polygon = self._imported_polygon
        entry = self._imported_entry
        wall_types = self._imported_wall_types
        dlg = FacadeDialog(polygon, entry, wall_types, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            new_wall_types, new_entry = dlg.get_results()
            self._imported_wall_types = new_wall_types
            self._imported_entry = new_entry
            self.entry_x_spin.setValue(round(new_entry[0], 2))
            self.entry_y_spin.setValue(round(new_entry[1], 2))
            self._show_boundary_preview(polygon, new_entry)
            n_facade = sum(1 for wt in new_wall_types if wt == WallType.FACADE)
            self.statusBar().showMessage(
                f"Facades: {n_facade}/{len(new_wall_types)} edges"
            )

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

    def _on_progress(self, pct: int):
        self.progress_bar.setValue(pct)

    def _on_variants_ready(self, variants: list[FloorPlan]):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setVisible(False)

        threshold = getattr(self, "_min_score_threshold", 0.8)
        all_count = len(variants)
        passed = [v for v in variants if v.score >= threshold]
        rejected = [v for v in variants if v.score < threshold]
        self.variants = passed
        self.current_idx = 0

        if not passed:
            best_rejected = max(rejected, key=lambda v: v.score) if rejected else None
            best_msg = (
                f" Highest score: {best_rejected.score:.3f}"
                if best_rejected else ""
            )
            self.statusBar().showMessage(
                f"No variants with score ≥ {threshold:.2f} "
                f"(solver returned {all_count}).{best_msg}"
            )
            self.image_label.setText(
                f"No variants with score ≥ {threshold:.2f}\n\n"
                f"Solver generated {all_count} solutions,\n"
                f"none met the minimum quality.\n"
                f"{best_msg.strip()}\n\n"
                f"Rules F1-F10 are inviolable — lower\n"
                f"'Min score' in Step 2 or change parameters."
            )
            self.preview_stack.setCurrentWidget(self.image_label)
            return

        self.prev_btn.setEnabled(len(passed) > 1)
        self.next_btn.setEnabled(len(passed) > 1)
        self.export_btn.setEnabled(True)
        self.archicad_btn.setEnabled(True)
        msg = f"Generated {len(passed)}/{all_count} variants (score ≥ {threshold:.2f})"
        if rejected:
            msg += f", rejected {len(rejected)} (max rejected: {max(v.score for v in rejected):.3f})"
        self.statusBar().showMessage(msg)
        self._show_variant(0)

    def _on_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("3. Generate layouts")
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _show_variant(self, idx: int):
        if not self.variants:
            return
        plan = self.variants[idx]
        self.current_idx = idx
        self.variant_label.setText(f"{idx + 1} / {len(self.variants)}")

        # Renderuj do pixmap
        fig = render_floor_plan(
            plan,
            title=f"Variant {idx + 1} (score: {plan.score:.3f})",
            show=False,
        )
        pixmap = self._fig_to_pixmap(fig)
        plt.close(fig)

        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.preview_stack.setCurrentWidget(self.image_label)

        # Variant details
        lines = [f"Variant {idx+1}/{len(self.variants)} — score: {plan.score:.3f}"]
        lines.append(f"Outline area: {plan.boundary.area:.1f} m²")
        lines.append("")
        for r in plan.rooms:
            lines.append(f"  {r.spec.nazwa:28s} {r.area:5.1f} m²  "
                         f"({r.width:.2f}×{r.depth:.2f}m)")
        if plan.validation_warnings:
            lines.append("")
            for w in plan.validation_warnings:
                lines.append(f"  ! {w}")
        self.details.setText("\n".join(lines))

    def _fig_to_pixmap(self, fig) -> QPixmap:
        """Convert matplotlib Figure to QPixmap."""
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        w, h = canvas.get_width_height()
        img = QImage(buf, w, h, QImage.Format_RGBA8888)
        return QPixmap.fromImage(img)

    def _prev_variant(self):
        if self.current_idx > 0:
            self._show_variant(self.current_idx - 1)

    def _next_variant(self):
        if self.current_idx < len(self.variants) - 1:
            self._show_variant(self.current_idx + 1)

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


    def _clear_import(self):
        if not self._importing:
            self._imported_polygon = None
            self._imported_entry = None

    def _show_boundary_preview(self, polygon, entry_point):
        """Interaktywny podgląd obrysu — klik na krawędź toggluje FACADE/INTERNAL,
        Shift+klik ustawia wejście na tej krawędzi.
        """
        self._preview_polygon = polygon
        self._preview_entry = entry_point

        self.preview_fig.clear()
        ax = self.preview_fig.add_subplot(111)

        x_coords, y_coords = polygon.exterior.xy
        ax.fill(x_coords, y_coords, alpha=0.10, color="lightgray")

        points = list(polygon.exterior.coords)[:-1]
        n = len(points)
        wall_types = self._imported_wall_types or [WallType.FACADE] * n
        entry_edge_idx = self._closest_edge_to_point(points, entry_point)

        for i in range(n):
            p1 = points[i]
            p2 = points[(i + 1) % n]
            if i == entry_edge_idx:
                color, lw = "#22aa22", 5  # zielony — wejście
                label = f"#{i+1} ENTRY"
            elif wall_types[i] == WallType.FACADE:
                color, lw = "#2266cc", 4  # niebieski — fasada
                label = f"#{i+1} FASADA"
            else:
                color, lw = "#cc4422", 4  # czerwony — wewnętrzna
                label = f"#{i+1} WEW"
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, linewidth=lw)
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            ax.annotate(label, (mx, my), fontsize=8, ha="center", va="center",
                        color=color, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2",
                                  facecolor="white", alpha=0.85, edgecolor=color))

        ex, ey = entry_point
        ax.plot(ex, ey, "v", color="#22aa22", markersize=18,
                markeredgecolor="black", markeredgewidth=1.5)

        bx0, by0, bx1, by1 = polygon.bounds
        margin = max(bx1 - bx0, by1 - by0) * 0.12
        ax.set_xlim(bx0 - margin, bx1 + margin)
        ax.set_ylim(by0 - margin, by1 + margin)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        n_facade = sum(1 for wt in wall_types if wt == WallType.FACADE)
        ax.set_title(
            f"Outline {polygon.area:.1f}m² — click edge to toggle type "
            f"| Shift+click = move entry\n"
            f"FASADA: {n_facade}, WEW: {n - n_facade}",
            fontsize=11,
        )
        ax.grid(True, alpha=0.3)
        self.preview_fig.tight_layout()
        self.preview_canvas.draw()
        self.preview_stack.setCurrentWidget(self.preview_canvas)

        self.details.setText(
            f"Outline: {polygon.area:.1f} m² | bbox {bx1-bx0:.2f}×{by1-by0:.2f} m\n"
            f"Entry: ({ex:.2f}, {ey:.2f})\n"
            f"Edges: {n} (FACADE: {n_facade}, INTERNAL: {n - n_facade})\n\n"
            f"Click edge = toggle FACADE/INTERNAL\n"
            f"Shift+click edge = move entry there\n"
            f"Then click 'Generate layouts'."
        )

    def _closest_edge_to_point(self, points, pt):
        from shapely.geometry import LineString, Point
        ep = Point(pt)
        n = len(points)
        return min(
            range(n),
            key=lambda i: LineString([points[i], points[(i + 1) % n]]).distance(ep),
        )

    def _on_canvas_click(self, event):
        """Click on edge in preview — toggle FACADE/INTERNAL or move entry."""
        if event.xdata is None or event.ydata is None:
            return
        if self._imported_polygon is None or self._imported_wall_types is None:
            return
        polygon = self._imported_polygon
        points = list(polygon.exterior.coords)[:-1]
        n = len(points)
        from shapely.geometry import LineString, Point
        click = Point(event.xdata, event.ydata)
        # Najbliższa krawędź
        distances = [
            (LineString([points[i], points[(i + 1) % n]]).distance(click), i)
            for i in range(n)
        ]
        distances.sort()
        min_dist, idx = distances[0]
        # Tolerance: ~10% długości obrysu (żeby uniknąć przypadkowych klików)
        bx0, by0, bx1, by1 = polygon.bounds
        tol = max(bx1 - bx0, by1 - by0) * 0.05
        if min_dist > tol:
            return  # za daleko od krawędzi

        shift_held = bool(event.guiEvent and event.guiEvent.modifiers() & Qt.ShiftModifier)
        if shift_held:
            # Przenieś wejście na tę krawędź
            p1 = points[idx]
            p2 = points[(idx + 1) % n]
            new_entry = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            self._imported_entry = new_entry
            # Wymuś INTERNAL na ścianie z drzwiami
            self._imported_wall_types[idx] = WallType.INTERNAL
            self.entry_x_spin.setValue(round(new_entry[0], 2))
            self.entry_y_spin.setValue(round(new_entry[1], 2))
        else:
            # Toggle FACADE/INTERNAL
            current = self._imported_wall_types[idx]
            self._imported_wall_types[idx] = (
                WallType.INTERNAL if current == WallType.FACADE else WallType.FACADE
            )
        self._show_boundary_preview(self._imported_polygon, self._imported_entry)

    def _load_data_plans(self):
        """Load list of dataset plans into combobox."""
        try:
            from data.dataset_loader import load_dataset
            ds = load_dataset()
            for p in ds.plans:
                self.data_combo.addItem(
                    f"{p.id} ({p.apartment_type}, {p.width_m:.1f}x{p.height_m:.1f}m)"
                )
            self._data_plans = ds.plans
        except Exception:
            self._data_plans = []

    def _show_data_plan(self):
        """Display selected plan from dataset."""
        idx = self.data_combo.currentIndex() - 1  # -1 bo "— wybierz —"
        if idx < 0 or idx >= len(self._data_plans):
            return

        p = self._data_plans[idx]

        from core.models import Room, RoomSpec, Strefa, FloorPlan, Template
        from core.boundary_analyzer import analyze_boundary
        from core.validator import validate
        from core.scorer import score as score_fn

        strefa_map = {"hub": Strefa.KOMUNIKACJA, "salon_aneks": Strefa.DZIENNA,
            "sypialnia": Strefa.NOCNA, "lazienka": Strefa.USLUGOWA,
            "wc": Strefa.USLUGOWA, "garderoba": Strefa.USLUGOWA, "pralnia": Strefa.USLUGOWA}

        rooms = []
        for r in p.rooms:
            if not r.polygon:
                continue
            pts = [(pt["x"], pt["y"]) for pt in r.polygon]
            poly = Polygon(pts)
            if poly.area < 0.1:
                continue
            spec = RoomSpec(id=r.category.value, nazwa=r.original_name,
                strefa=strefa_map.get(r.category.value, Strefa.KOMUNIKACJA),
                wymaga_okna=r.category.value in ("salon_aneks", "sypialnia"),
                priorytet_fasady=None)
            room = Room(spec=spec, polygon=poly)
            room.update_metrics()
            rooms.append(room)

        if not rooms:
            self.statusBar().showMessage(f"No rooms with polygons in {p.id}")
            return

        entry = p.entry_position or (p.width_m / 2, 0)
        boundary_poly = Polygon([(0, 0), (p.width_m, 0), (p.width_m, p.height_m), (0, p.height_m)])
        boundary = analyze_boundary(boundary_poly, entry)
        template = Template(id="data", nazwa=p.id, typ_mieszkania=p.apartment_type,
                            pokoje=[r.spec for r in rooms], sasiedztwo=[])
        fp = FloorPlan(boundary=boundary, template=template, rooms=rooms)
        validate(fp)
        score_fn(fp)

        self.variants = [fp]
        self.current_idx = 0
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.archicad_btn.setEnabled(True)
        self._show_variant(0)
        self.statusBar().showMessage(f"Plan {p.id} ({p.apartment_type}) — score: {fp.score:.3f}")

    def keyPressEvent(self, event):
        """Left/right arrows navigate between variants."""
        if event.key() == Qt.Key_Left:
            self._prev_variant()
        elif event.key() == Qt.Key_Right:
            self._next_variant()
        else:
            super().keyPressEvent(event)

    def _export_to_archicad(self):
        """Export current variant to ArchiCAD as zones."""
        if not self.variants:
            return
        plan = self.variants[self.current_idx]
        try:
            from bridge.plan_writer import export_plan_to_archicad
            result = export_plan_to_archicad(plan, offset=self._archicad_offset)
            n_zones = len(result["zones"])
            n_walls = len(result["walls"])
            n_doors = len(result["doors"])
            n_labels = len(result.get("labels", []))
            n_windows = len(result.get("windows", []))
            apt_id = result.get("apartment_id", "?")
            self.statusBar().showMessage(
                f"[{apt_id}] {n_zones} stref + {n_walls} ścian + "
                f"{n_doors} drzwi + {n_windows} okien + {n_labels} etykiet"
            )
            QMessageBox.information(
                self, "ArchiCAD",
                f"Mieszkanie {apt_id}:\n\n"
                f"{n_zones} stref + {n_walls} ścianek + {n_doors} drzwi "
                f"+ {n_windows} okien (WT 1/8) + {n_labels} etykiet.\n\n"
                f"Numery stref: {apt_id}-001…{apt_id}-{n_zones:03d}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "ArchiCAD",
                f"Cannot connect to ArchiCAD:\n{e}\n\n"
                "Make sure ArchiCAD is running with Tapir Add-On."
            )

    def _import_from_inner_edge(self):
        """Auto-detect z natywnego Inner Edge w AC.

        Workflow (2 akcje):
            1. Snapshot bieżących Zone GUIDs w AC.
            2. Dialog z instrukcją "W AC: Z + klik w mieszkaniu, potem OK".
            3. Po OK: szukamy nowej Zone, czytamy polygon, USUWAMY Zone.
        """
        from bridge.tapir_connection import TapirConnection
        from bridge.boundary_reader import read_boundary_from_new_zone

        try:
            tapir = TapirConnection()
            tapir.connect()
        except Exception as e:
            QMessageBox.warning(
                self, "ArchiCAD",
                f"Cannot connect to ArchiCAD:\n{e}\n\n"
                "Check that AC is running and Tapir Add-On is installed."
            )
            return

        # 1. Snapshot - jakie Zone juz istnieja PRZED user actions
        try:
            pre_zones = tapir.get_elements_by_type("Zone") or []
        except Exception as e:
            QMessageBox.warning(self, "ArchiCAD",
                                f"Nie udalo sie pobrac listy Zone:\n{e}")
            return

        pre_guids: set[str] = set()
        for z in pre_zones:
            if isinstance(z, dict):
                eid = z.get("elementId", z)
                guid = eid.get("guid") if isinstance(eid, dict) else str(eid)
                if guid:
                    pre_guids.add(guid)

        # 2. Modal: user wykonuje akcje w AC i naciska OK
        reply = QMessageBox.question(
            self, "Auto-detect z Inner Edge",
            f"<b>Wykonaj w ArchiCAD:</b><br><br>"
            f"1. Naciśnij <b>Z</b> (Zone tool, lub Tools → Zone)<br>"
            f"2. Klik w pustym miejscu wewnątrz mieszkania<br>"
            f"&nbsp;&nbsp;&nbsp;(AC sam wykryje obrys — Inner Edge)<br>"
            f"3. Wróć tutaj i kliknij <b>OK</b><br><br>"
            f"<i>Aktualnie w projekcie: {len(pre_guids)} Zone.<br>"
            f"Po imporcie nowa Zone zostanie usunięta z AC.</i>",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        if reply != QMessageBox.Ok:
            self.statusBar().showMessage("Auto-detect anulowany.")
            return

        # 3. Import: znajdź nową Zone, polygon, cleanup
        self.statusBar().showMessage("Szukam nowej Zone w AC…")
        try:
            polygon, entry_point, wall_types = read_boundary_from_new_zone(
                tapir, before_guids=pre_guids, cleanup=True,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Auto-detect", str(e))
            self.statusBar().showMessage("Auto-detect failed.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Auto-detect",
                                 f"Unexpected error:\n{type(e).__name__}: {e}")
            return

        self._apply_imported_boundary(polygon, entry_point, wall_types)
        self.statusBar().showMessage(
            f"Outline auto-detected ({len(list(polygon.exterior.coords)) - 1} vertices)."
        )

    def _import_from_archicad(self):
        """Start polling for new Zone/Slab in AC (every 1s)."""
        from PyQt5.QtCore import QTimer
        from bridge.tapir_connection import TapirConnection

        # Test połączenia
        try:
            tapir = TapirConnection()
            tapir.connect()
        except Exception as e:
            QMessageBox.warning(
                self, "ArchiCAD",
                f"Cannot connect to ArchiCAD:\n{e}\n\n"
                "Check that AC is running and Tapir Add-On is installed."
            )
            return

        # Snapshot aktualnie zaznaczonych — żeby wykryć NOWE elementy
        try:
            initial = tapir.get_selected_elements()
            self._poll_initial_guids = {self._extract_guid(e) for e in initial}
        except Exception:
            self._poll_initial_guids = set()

        # If a Zone/Slab/Wall is already selected — load immediately (no polling)
        if initial:
            self._do_import_from_archicad()
            return

        # Change button to "Cancel" and start polling
        self.import_btn.setText("Cancel listening (click in AC)")
        self.import_btn.clicked.disconnect()
        self.import_btn.clicked.connect(self._cancel_import_polling)

        self.statusBar().showMessage(
            "Listening... In AC: Tools → Zone → Inner Edge → click inside apartment"
        )

        self._poll_attempts = 0
        self._poll_max_attempts = 60  # 60 × 1s = 60s timeout
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_archicad_selection)
        self._poll_timer.start(1000)

    def _populate_stage4_from_stage1(self, polygon, entry, wall_types):
        """Slot for Stage1Widget.apartment_layout_requested.

        Fills Stage 4 input fields, renders the boundary preview, and switches
        the active tab to Stage 4. If Stage 4 already has generated variants,
        asks for confirmation before overwriting.
        """
        if self.variants:
            if not self._confirm_stage4_overwrite():
                return
        self._imported_polygon = polygon
        self._imported_entry = entry
        self._imported_wall_types = list(wall_types)
        self._show_boundary_preview(polygon, entry)
        self.tabs.setCurrentWidget(self.apt_tab)
        self._real_status_bar.showMessage(
            f"Załadowano sub-działkę ze Stage 1 ({polygon.area:.1f} m²). "
            f"Kliknij Generate aby wygenerować rzut.", 6000
        )

    def _confirm_stage4_overwrite(self) -> bool:
        """Placeholder — Task 7 replaces this with a QMessageBox confirm."""
        return True

    @staticmethod
    def _extract_guid(elem):
        if isinstance(elem, dict):
            eid = elem.get("elementId", elem)
            return eid.get("guid") if isinstance(eid, dict) else str(eid)
        return str(elem)

    def _poll_archicad_selection(self):
        """Check every 1s if a new Zone/Slab/Wall appeared in AC."""
        from bridge.tapir_connection import TapirConnection

        self._poll_attempts += 1
        if self._poll_attempts >= self._poll_max_attempts:
            self._cancel_import_polling()
            self.statusBar().showMessage("Timeout 60s — no new Zone detected in AC")
            return

        try:
            tapir = TapirConnection()
            selected = tapir.get_selected_elements()
        except Exception:
            return  # ignore transient errors, próbuj dalej

        if not selected:
            return  # nadal pusto

        # Coś jest zaznaczone — sprawdź czy NOWE (nie było w snapshot startowym)
        current_guids = {self._extract_guid(e) for e in selected}
        new_guids = current_guids - self._poll_initial_guids
        if not new_guids:
            return  # to samo zaznaczenie co na starcie

        # New element appeared — load it
        self._poll_timer.stop()
        self._reset_import_button()
        self._do_import_from_archicad()

    def _cancel_import_polling(self):
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        self._reset_import_button()
        self.statusBar().showMessage("Listening cancelled")

    def _reset_import_button(self):
        self.import_btn.setText("Load outline from ArchiCAD")
        try:
            self.import_btn.clicked.disconnect()
        except Exception:
            pass
        self.import_btn.clicked.connect(self._import_from_archicad)

    def _do_import_from_archicad(self):
        """Faktyczne wczytanie obrysu z aktualnego zaznaczenia w AC."""
        try:
            from bridge.boundary_reader import read_boundary_from_archicad
            polygon, entry_point, wall_types = read_boundary_from_archicad()
            self._apply_imported_boundary(polygon, entry_point, wall_types)

        except Exception as e:
            QMessageBox.warning(
                self, "ArchiCAD",
                f"Cannot load outline:\n{e}\n\n"
                "Select outline walls in ArchiCAD and try again."
            )

    def _apply_imported_boundary(self, polygon, entry_point, wall_types):
        """Aplikuje wczytany boundary do GUI — wspólne dla wszystkich źródeł
        (zaznaczenie w AC / click-to-pick auto-detect)."""
        from shapely.affinity import translate
        from core.boundary_analyzer import _detect_notch, is_rectangle

        bx0, by0, bx1, by1 = polygon.bounds
        w = bx1 - bx0
        h = by1 - by0

        # Przesuń do (0,0), zapamiętaj offset do późniejszego eksportu
        self._archicad_offset = (bx0, by0)
        shifted = translate(polygon, -bx0, -by0)
        entry_shifted = (entry_point[0] - bx0, entry_point[1] - by0)

        # Zablokuj _clear_import podczas ustawiania spinboxów
        self._importing = True
        self.width_spin.setValue(round(w, 1))
        self.height_spin.setValue(round(h, 1))
        self.entry_x_spin.setValue(round(entry_shifted[0], 1))
        self.entry_y_spin.setValue(round(entry_shifted[1], 1))

        self._imported_polygon = shifted
        self._imported_entry = entry_shifted
        self._importing = False

        # Wykryj kształt
        is_rect = is_rectangle(shifted)
        has_notch = False
        if not is_rect:
            if _detect_notch(shifted) is not None:
                has_notch = True
        self.notch_group.setChecked(has_notch)

        # Auto-typ z powierzchni
        area = shifted.area
        if area < 45:
            auto_type = "M1"
        elif area < 65:
            auto_type = "M2"
        elif area < 85:
            auto_type = "M3"
        elif area < 110:
            auto_type = "M4"
        else:
            auto_type = "M5"
        self.type_combo.setCurrentText(auto_type)

        self._imported_wall_types = list(wall_types)
        self.facades_btn.setEnabled(True)
        self._show_boundary_preview(shifted, entry_shifted)

        shape = "L/U-shape" if has_notch else (
            "rectangle" if is_rect else "trapezoid/other"
        )
        self.statusBar().showMessage(
            f"Loaded {shape} {w:.1f}x{h:.1f}m ({area:.0f}m²) → {auto_type}"
        )


def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    # Center on primary screen + force foreground (macOS Python framework workaround).
    primary = app.primaryScreen().geometry()
    win_w, win_h = 1200, 800
    window.setGeometry(
        primary.x() + (primary.width() - win_w) // 2,
        primary.y() + (primary.height() - win_h) // 2,
        win_w, win_h,
    )
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
