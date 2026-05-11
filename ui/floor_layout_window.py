"""
Floor Layout window — Stage 3 GUI.

Standalone PyQt5 window for dividing a building floor into apartments,
stairwells, and a corridor according to Polish Building Code (WT 2002).

Run: PYTHONPATH=. python ui/floor_layout_window.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QStatusBar, QMessageBox, QCheckBox,
)
from PyQt5.QtCore import Qt
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

from shapely.geometry import Polygon

from rules._loader import get_default_pack as _get_default_pack

APARTMENT_MIX_DEFAULT = _get_default_pack().constants["apartment_mix_default"]
from core.floor_layout import solve_floor_layout
from core.floor_compute import compute_stairwell_dimensions, compute_apartment_count


APT_COLORS = {
    "M1": "#fce4a4", "M2": "#a8d8ea", "M3": "#aac9b1",
    "M4": "#d4b3d4", "M5": "#f0a6a0",
}


class FloorLayoutWidget(QWidget):
    """Stage 3 panel — embeddable in QTabWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded_polygon = None  # full polygon from AC (preserves L-shape)
        self._build_ui()
        self._update_preview_on_param_change()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # ── Left panel: inputs ──
        left = QVBoxLayout()

        # Floor outline
        outline_box = QGroupBox("1. Floor outline")
        ol = QGridLayout(outline_box)
        ol.addWidget(QLabel("Width [m]:"), 0, 0)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(8.0, 200.0); self.width_spin.setValue(40.0)
        self.width_spin.setSingleStep(1.0)
        ol.addWidget(self.width_spin, 0, 1)
        ol.addWidget(QLabel("Depth [m]:"), 1, 0)
        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(8.0, 60.0); self.depth_spin.setValue(20.0)
        self.depth_spin.setSingleStep(1.0)
        ol.addWidget(self.depth_spin, 1, 1)
        self.load_ac_btn = QPushButton("Load outline from ArchiCAD")
        self.load_ac_btn.clicked.connect(self._load_from_ac)
        ol.addWidget(self.load_ac_btn, 2, 0, 1, 2)
        left.addWidget(outline_box)

        # Building params
        bld_box = QGroupBox("2. Building")
        bl = QGridLayout(bld_box)
        bl.addWidget(QLabel("Floor height [m]:"), 0, 0)
        self.fh_spin = QDoubleSpinBox()
        self.fh_spin.setRange(2.4, 4.0); self.fh_spin.setValue(2.8)
        self.fh_spin.setSingleStep(0.1)
        bl.addWidget(self.fh_spin, 0, 1)
        bl.addWidget(QLabel("Num. floors:"), 1, 0)
        self.nf_spin = QSpinBox()
        self.nf_spin.setRange(1, 30); self.nf_spin.setValue(4)
        bl.addWidget(self.nf_spin, 1, 1)
        bl.addWidget(QLabel("Stairwell facade:"), 2, 0)
        self.facade_combo = QComboBox()
        self.facade_combo.addItems(["N", "S", "E", "W"])
        bl.addWidget(self.facade_combo, 2, 1)
        self.bld_info = QLabel("")
        self.bld_info.setStyleSheet("color: #555; font-size: 10px;")
        bl.addWidget(self.bld_info, 3, 0, 1, 2)
        left.addWidget(bld_box)

        # Mix
        mix_box = QGroupBox("3. Apartment mix [%]")
        ml = QGridLayout(mix_box)
        self.mix_spins = {}
        for i, t in enumerate(["M1", "M2", "M3", "M4", "M5"]):
            ml.addWidget(QLabel(t), i, 0)
            sp = QSpinBox()
            sp.setRange(0, 100); sp.setSuffix(" %")
            sp.setValue(int(APARTMENT_MIX_DEFAULT[t] * 100))
            self.mix_spins[t] = sp
            ml.addWidget(sp, i, 1)
        self.mix_total_lbl = QLabel("Total: 100%")
        ml.addWidget(self.mix_total_lbl, 5, 0, 1, 2)
        left.addWidget(mix_box)

        # WT overrides
        wt_box = QGroupBox("4. WT overrides")
        wl = QGridLayout(wt_box)
        wl.addWidget(QLabel("Corridor width [m]:"), 0, 0)
        self.cw_spin = QDoubleSpinBox()
        self.cw_spin.setRange(1.0, 3.0); self.cw_spin.setValue(1.4)
        self.cw_spin.setSingleStep(0.1)
        wl.addWidget(self.cw_spin, 0, 1)
        wl.addWidget(QLabel("Max walk dist [m]:"), 1, 0)
        self.maxd_spin = QDoubleSpinBox()
        self.maxd_spin.setRange(10.0, 80.0); self.maxd_spin.setValue(40.0)
        self.maxd_spin.setSingleStep(5.0)
        wl.addWidget(self.maxd_spin, 1, 1)
        wl.addWidget(QLabel("Reserve [%]:"), 2, 0)
        self.res_spin = QSpinBox()
        self.res_spin.setRange(0, 50); self.res_spin.setValue(15); self.res_spin.setSuffix(" %")
        wl.addWidget(self.res_spin, 2, 1)
        wl.addWidget(QLabel("Override stairs (0=auto):"), 3, 0)
        self.ns_spin = QSpinBox()
        self.ns_spin.setRange(0, 10); self.ns_spin.setValue(0)
        wl.addWidget(self.ns_spin, 3, 1)
        left.addWidget(wt_box)

        # Generate
        self.generate_btn = QPushButton("5. Generate Floor Layout")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #4a90d9; color: white; border-radius: 4px;"
        )
        self.generate_btn.clicked.connect(self._generate)
        left.addWidget(self.generate_btn)

        # Result info
        self.info_lbl = QLabel("")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet(
            "background: #f0f0f0; padding: 6px; font-size: 10px;"
        )
        self.info_lbl.setMinimumHeight(120)
        left.addWidget(self.info_lbl)

        left.addStretch()
        left_widget = QWidget(); left_widget.setLayout(left)
        left_widget.setMaximumWidth(330)

        # ── Right panel: matplotlib canvas ──
        self.fig = Figure(figsize=(10, 7))
        self.canvas = FigureCanvasQTAgg(self.fig)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.canvas, stretch=1)

        # Reactive updates
        for sp in [self.fh_spin, self.nf_spin]:
            sp.valueChanged.connect(self._update_preview_on_param_change)
        for sp in self.mix_spins.values():
            sp.valueChanged.connect(self._update_mix_total)
        # Live outline preview when width/depth change
        self.width_spin.valueChanged.connect(self._refresh_outline_preview)
        self.depth_spin.valueChanged.connect(self._refresh_outline_preview)
        # Initial preview
        self._refresh_outline_preview()

    def _refresh_outline_preview(self):
        # Manual W/D edit invalidates the loaded polygon (L/U from AC)
        self._loaded_polygon = None
        self._render_outline_preview(self.width_spin.value(), self.depth_spin.value())

    def statusBar(self):
        """Bridge to host window's status bar (or no-op)."""
        win = self.window()
        if hasattr(win, "_real_status_bar") and win._real_status_bar:
            return win._real_status_bar
        class _Noop:
            def showMessage(self, msg): pass
        return _Noop()

    def _update_mix_total(self):
        total = sum(s.value() for s in self.mix_spins.values())
        self.mix_total_lbl.setText(
            f"Total: {total}% {'(must = 100)' if total != 100 else '✓'}"
        )

    def _update_preview_on_param_change(self):
        h = self.fh_spin.value(); n = self.nf_spin.value()
        sw = compute_stairwell_dimensions(h, n)
        self.bld_info.setText(
            f"Building height: {sw['h_total_m']:.1f} m, class: {sw['building_class']}\n"
            f"Stairwell: {sw['stairwell_width_m']:.2f} × {sw['stairwell_length_m']:.2f} m "
            f"({sw['stairwell_area_m2']} m²)\n"
            f"Elevator: {'YES' if sw['has_elevator'] else 'NO'} "
            f"({sw['n_steps']} steps × {sw['step_height_m']*100:.1f}cm)"
        )

    def _gather_mix(self) -> dict:
        total = sum(s.value() for s in self.mix_spins.values())
        if total == 0:
            return APARTMENT_MIX_DEFAULT
        return {t: s.value() / total for t, s in self.mix_spins.items()}

    def _load_from_ac(self):
        try:
            from bridge.tapir_connection import TapirConnection
            from bridge.boundary_reader import read_boundary_from_archicad
            from shapely.affinity import translate
            tapir = TapirConnection(); tapir.connect()
            polygon, _, _ = read_boundary_from_archicad(tapir)
            bx0, by0, bx1, by1 = polygon.bounds
            # Translate to origin so width/depth spinboxes are 0..W and 0..D
            shifted = translate(polygon, -bx0, -by0)
            self._loaded_polygon = shifted
            w = round(bx1 - bx0, 2)
            d = round(by1 - by0, 2)
            self.width_spin.blockSignals(True)
            self.depth_spin.blockSignals(True)
            self.width_spin.setValue(w)
            self.depth_spin.setValue(d)
            self.width_spin.blockSignals(False)
            self.depth_spin.blockSignals(False)
            self._render_polygon_preview(shifted)
            shape = "L/U-shape" if len(list(shifted.exterior.coords)) > 5 else "rectangle"
            self.statusBar().showMessage(
                f"Loaded {shape} outline from AC: "
                f"{shifted.area:.1f} m² (bbox {w}×{d}m)"
            )
        except Exception as e:
            QMessageBox.warning(self, "ArchiCAD",
                                f"Cannot load outline:\n{e}")
            self._loaded_polygon = None

    def _render_outline_preview(self, w: float, d: float, area: float = None):
        """Draw outline rectangle on canvas (before generation, manual mode)."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.fill([0, w, w, 0], [0, 0, d, d], alpha=0.10, color="lightgray")
        ax.plot([0, w, w, 0, 0], [0, 0, d, d, 0], color="black", linewidth=2)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        a = area if area is not None else w * d
        ax.set_title(
            f"Outline {w:.1f} × {d:.1f} m  ({a:.1f} m²) — "
            f"set parameters and click Generate"
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _render_polygon_preview(self, polygon):
        """Draw an arbitrary outline polygon (preserves L/U-shape from AC)."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        fx, fy = polygon.exterior.xy
        ax.fill(fx, fy, alpha=0.10, color="lightgray")
        ax.plot(fx, fy, color="black", linewidth=2)
        bx0, by0, bx1, by1 = polygon.bounds
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.set_title(
            f"Outline {polygon.area:.1f} m² (bbox {bx1-bx0:.1f}×{by1-by0:.1f} m, "
            f"{len(list(polygon.exterior.coords))-1} vertices) — Generate to divide"
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _generate(self):
        # Use full loaded polygon (preserves L/U from AC) when available,
        # otherwise build a rectangle from the spinboxes.
        if self._loaded_polygon is not None:
            floor = self._loaded_polygon
        else:
            w = self.width_spin.value(); d = self.depth_spin.value()
            floor = Polygon([(0, 0), (w, 0), (w, d), (0, d)])
        mix = self._gather_mix()
        ns = self.ns_spin.value() if self.ns_spin.value() > 0 else None

        self.statusBar().showMessage("Solving...")
        QApplication.processEvents()

        try:
            result = solve_floor_layout(
                floor,
                floor_height_m=self.fh_spin.value(),
                num_floors=self.nf_spin.value(),
                mix_pct=mix,
                stairwell_facade=self.facade_combo.currentText(),
                corridor_width_m=self.cw_spin.value(),
                max_walking_distance_m=self.maxd_spin.value(),
                reserve_ratio=self.res_spin.value() / 100.0,
                num_stairwells=ns,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Solver failed:\n{e}")
            self.statusBar().showMessage("Error")
            return

        self._render(result, floor)
        self._show_result_info(result)
        self.statusBar().showMessage(
            f"Status: {result.status} ({result.solve_time_s:.2f}s)"
        )

    def _render(self, result, floor):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        fx, fy = floor.exterior.xy
        ax.fill(fx, fy, alpha=0.04, color="gray")
        ax.plot(fx, fy, color="black", linewidth=2)

        if result.corridor:
            cx, cy = result.corridor.exterior.xy
            ax.fill(cx, cy, color="#c8e6c9", alpha=0.7,
                    edgecolor="#558b2f", linewidth=1.0, hatch="//")
        for conn in result.connectors:
            cx, cy = conn.exterior.xy
            ax.fill(cx, cy, color="#c8e6c9", alpha=0.7,
                    edgecolor="#558b2f", linewidth=1.0, hatch="//")

        for i, ap in enumerate(result.apartments):
            if ap.polygon is None:
                continue
            ax_, ay = ap.polygon.exterior.xy
            c = APT_COLORS.get(ap.apartment_type, "#cccccc")
            ax.fill(ax_, ay, color=c, alpha=0.7, edgecolor="black", linewidth=1.0)
            cx, cy = ap.polygon.centroid.x, ap.polygon.centroid.y
            d = result.walking_distances_m[i] if i < len(result.walking_distances_m) else None
            d_str = f"\n{d:.1f}m" if d not in (None, float("inf")) else "\n!"
            color = "red" if (d and d > self.maxd_spin.value()) else "black"
            ax.text(cx, cy, f"{ap.apartment_type} {ap.area:.0f}m²{d_str}",
                    ha="center", va="center", fontsize=8, fontweight="bold",
                    color=color)

        for i, stair in enumerate(result.stairwells):
            sx, sy = stair.exterior.xy
            ax.fill(sx, sy, color="#555", alpha=0.85,
                    edgecolor="black", linewidth=1.5)
            cx, cy = stair.centroid.x, stair.centroid.y
            ax.text(cx, cy, f"S{i+1}", ha="center", va="center",
                    fontsize=10, color="white", fontweight="bold")

        types = sorted(set(a.apartment_type for a in result.apartments))
        legend = [mpatches.Patch(facecolor=APT_COLORS[t], label=t) for t in types]
        legend.append(mpatches.Patch(facecolor="#555", label="stairwell"))
        legend.append(mpatches.Patch(facecolor="#c8e6c9", hatch="//", label="corridor"))
        ax.legend(handles=legend, loc="upper right", fontsize=9)

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.set_title(
            f"{floor.area:.0f} m² floor, class {result.building_class}, "
            f"{result.n_stairwells} stair(s), {len(result.apartments)} apartments | "
            f"{result.status}"
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _show_result_info(self, result):
        from collections import Counter
        ctr = Counter(a.apartment_type for a in result.apartments)
        max_d = max(result.walking_distances_m) if result.walking_distances_m else 0
        lines = [
            f"<b>Status:</b> {result.status}",
            f"<b>Building class:</b> {result.building_class}, "
            f"elevator: {'YES' if result.has_elevator else 'NO'}",
            f"<b>Stairwells:</b> {result.n_stairwells}",
            f"<b>Apartments:</b> {sum(ctr.values())} — {dict(ctr)}",
            f"<b>Max walking distance:</b> {max_d:.1f} m",
        ]
        if result.violations:
            lines.append("<b>Violations:</b><br>" +
                         "<br>".join(f"• {v}" for v in result.violations[:5]))
        self.info_lbl.setText("<br>".join(lines))


class FloorLayoutWindow(QMainWindow):
    """Standalone window wrapper around FloorLayoutWidget."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FloorPlan6 — Stage 3: Floor Layout")
        self.setMinimumSize(1200, 750)
        self.setStatusBar(QStatusBar())
        self._real_status_bar = self.statusBar()
        self.setCentralWidget(FloorLayoutWidget(self))
        self._real_status_bar.showMessage("Ready")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = FloorLayoutWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
