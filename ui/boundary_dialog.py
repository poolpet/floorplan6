"""
Boundary classification dialog — Stage 1.

After Load from AC, the user assigns each plot edge a BoundaryType
(DROGA / SASIAD_ZABUDOWANY / SASIAD_NIEZABUDOWANY / WLASNA) plus an
optional `no_openings` flag for Polish §12 setbacks. Results are written
back to `plot.boundaries`.

Includes a live matplotlib preview that recolours edges as the user
changes types — so it's clear which edge is which.
"""
from __future__ import annotations

import math
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from core.plot_model import BoundaryType, Plot, PlotBoundary


BOUNDARY_LABEL_TO_TYPE = [
    ("DROGA — droga publiczna", BoundaryType.DROGA),
    ("SĄSIAD_ZABUDOWANY (3 m)", BoundaryType.SASIAD_ZABUDOWANY),
    ("SĄSIAD_NIEZABUDOWANY (1.5 m / 3 m)", BoundaryType.SASIAD_NIEZABUDOWANY),
    ("WŁASNA (tylna/boczna)", BoundaryType.WLASNA),
    ("NIEZNANA", BoundaryType.NIEZNANA),
]

BOUNDARY_COLOR = {
    BoundaryType.DROGA: "#e74c3c",
    BoundaryType.SASIAD_ZABUDOWANY: "#3498db",
    BoundaryType.SASIAD_NIEZABUDOWANY: "#2ecc71",
    BoundaryType.WLASNA: "#9b59b6",
    BoundaryType.NIEZNANA: "#7f8c8d",
}


def _compass(dx: float, dy: float) -> str:
    """Return compass label for an edge vector."""
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return "?"
    angle = math.degrees(math.atan2(dy, dx))   # 0=E, 90=N, 180=W, 270=S
    sectors = [
        (-22.5, 22.5, "E—W"),       # horizontal pointing east
        (22.5, 67.5, "NE—SW"),
        (67.5, 112.5, "N—S"),
        (112.5, 157.5, "NW—SE"),
        (157.5, 180.0, "E—W"),
        (-180.0, -157.5, "E—W"),
        (-157.5, -112.5, "NW—SE"),
        (-112.5, -67.5, "N—S"),
        (-67.5, -22.5, "NE—SW"),
    ]
    for mn, mx, name in sectors:
        if mn <= angle < mx:
            return name
    return "?"


class BoundaryClassificationDialog(QDialog):
    """Edit boundary types of a plot. Updates `plot.boundaries` on accept."""

    def __init__(self, plot: Plot, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Klasyfikacja granic działki")
        self.setMinimumSize(900, 600)
        self.plot = plot
        # Working copies (committed back on accept)
        self._types: List[BoundaryType] = [
            b.boundary_type for b in plot.boundaries
        ]
        self._no_openings: List[bool] = [
            b.no_openings for b in plot.boundaries
        ]
        self._build_ui()
        self._render_preview()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # Left: table of edges
        left = QVBoxLayout()
        info = QLabel(
            "Każdej krawędzi działki przypisz typ. Wymagana jest co najmniej "
            "jedna krawędź typu DROGA — od niej algorytm poprowadzi drogę "
            "wewnętrzną (sięgacz) w trybie B."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #444; padding: 4px;")
        left.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_inner = QWidget()
        grid = QGridLayout(scroll_inner)
        grid.addWidget(QLabel("<b>#</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Długość</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Kierunek</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Typ</b>"), 0, 3)
        grid.addWidget(QLabel("<b>Bez otworów</b>"), 0, 4)

        self._combos: List[QComboBox] = []
        self._checks: List[QCheckBox] = []

        for i, b in enumerate(self.plot.boundaries):
            coords = list(b.geometry.coords)
            dx = coords[-1][0] - coords[0][0]
            dy = coords[-1][1] - coords[0][1]

            grid.addWidget(QLabel(f"#{i + 1}"), i + 1, 0)
            grid.addWidget(QLabel(f"{b.geometry.length:.2f} m"), i + 1, 1)
            grid.addWidget(QLabel(_compass(dx, dy)), i + 1, 2)

            combo = QComboBox()
            for label, btype in BOUNDARY_LABEL_TO_TYPE:
                combo.addItem(label, btype)
            current_idx = next(
                (idx for idx, (_, btype) in enumerate(BOUNDARY_LABEL_TO_TYPE)
                 if btype == self._types[i]),
                0,
            )
            combo.setCurrentIndex(current_idx)
            combo.currentIndexChanged.connect(
                lambda _idx, ii=i: self._on_type_changed(ii)
            )
            self._combos.append(combo)
            grid.addWidget(combo, i + 1, 3)

            chk = QCheckBox()
            chk.setChecked(self._no_openings[i])
            chk.setToolTip("Ściana bez otworów — pozwala na 1.5 m setback")
            chk.toggled.connect(lambda _state, ii=i: self._on_no_openings_changed(ii))
            self._checks.append(chk)
            grid.addWidget(chk, i + 1, 4)

        scroll_inner.setLayout(grid)
        scroll.setWidget(scroll_inner)
        left.addWidget(scroll, stretch=1)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Auto-detect button (re-runs heuristic)
        self.autodetect_btn = QPushButton("Auto-wykryj (najniższy edge = DROGA)")
        self.autodetect_btn.clicked.connect(self._auto_detect)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.autodetect_btn)
        btn_row.addStretch()
        btn_row.addWidget(buttons)
        left.addLayout(btn_row)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(540)

        # Right: preview canvas
        self.fig = Figure(figsize=(6, 6))
        self.canvas = FigureCanvasQTAgg(self.fig)

        layout.addWidget(left_widget)
        layout.addWidget(self.canvas, stretch=1)

    def _on_type_changed(self, edge_index: int):
        idx = self._combos[edge_index].currentIndex()
        self._types[edge_index] = BOUNDARY_LABEL_TO_TYPE[idx][1]
        self._render_preview()

    def _on_no_openings_changed(self, edge_index: int):
        self._no_openings[edge_index] = self._checks[edge_index].isChecked()

    def _auto_detect(self):
        """Re-run the bottom-most-edge heuristic and update controls."""
        edges = [(i, b.geometry) for i, b in enumerate(self.plot.boundaries)]
        midys = []
        for i, geom in edges:
            coords = list(geom.coords)
            midy = (coords[0][1] + coords[-1][1]) / 2
            midys.append((i, midy))
        droga_idx = min(midys, key=lambda x: x[1])[0]
        for i in range(len(self._types)):
            new_type = BoundaryType.DROGA if i == droga_idx else BoundaryType.SASIAD_NIEZABUDOWANY
            self._types[i] = new_type
            target_idx = next(
                (idx for idx, (_, btype) in enumerate(BOUNDARY_LABEL_TO_TYPE)
                 if btype == new_type),
                0,
            )
            self._combos[i].blockSignals(True)
            self._combos[i].setCurrentIndex(target_idx)
            self._combos[i].blockSignals(False)
        self._render_preview()

    def _render_preview(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        px, py = self.plot.geometry.exterior.xy
        ax.fill(px, py, alpha=0.05, color="black")

        for i, b in enumerate(self.plot.boundaries):
            xs, ys = b.geometry.xy
            color = BOUNDARY_COLOR[self._types[i]]
            ax.plot(xs, ys, color=color, linewidth=4.0)
            mid_x = (xs[0] + xs[-1]) / 2
            mid_y = (ys[0] + ys[-1]) / 2
            ax.annotate(
                f"#{i + 1}",
                xy=(mid_x, mid_y),
                fontsize=8, ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.2", fc="white",
                          ec=color, linewidth=1.5),
            )

        # Legend
        from matplotlib.patches import Patch
        seen_types = list(set(self._types))
        legend = [
            Patch(color=BOUNDARY_COLOR[t], label=t.value)
            for t in seen_types
        ]
        ax.legend(handles=legend, loc="upper right", fontsize=8)

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_title(
            f"Działka {self.plot.geometry.area:.0f} m² — kliknij krawędź na liście",
            fontsize=10,
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def commit_to_plot(self) -> None:
        """Apply selected types + no_openings flags to plot.boundaries."""
        for i, b in enumerate(self.plot.boundaries):
            b.boundary_type = self._types[i]
            b.no_openings = self._no_openings[i]
