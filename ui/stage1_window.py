"""
Stage 1 — plot analyser GUI (PyQt5 widget).

Layout (Q18(a) — radio at start):
  1. Plot outline (manual rectangle or Load from AC)
  2. Housing type radio (JEDNORODZINNA / WIELORODZINNA)
  3. Mode radio (A whole-plot / B subdivision) — Mode B only enabled for jednorodzinna
  4. MPZP parameters form
  5. Building type combo (Mode B only — Q3(c) DETACHED/TWIN/TERRACED)
  6. Generate button
  7. Result info panel + matplotlib preview canvas

Run standalone: PYTHONPATH=. python ui/stage1_window.py
"""
from __future__ import annotations

import sys

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QRadioButton, QSpinBox, QStatusBar, QVBoxLayout, QWidget,
)

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from shapely.geometry import Polygon

from bridge.plot_reader import wrap_polygon_as_plot
from core.buildable_zone import BuildableZoneBuilder, BuildableZoneInfeasible
from core.plot_indicators import PlotIndicatorCalculator
from core.plot_model import HousingType, MPZPParameters
from core.plot_subdivider import (
    BuildingType,
    subdivide_with_orientation_search,
)
from core.plot_verifier import PlotVerifier, VerificationStatus
from core.site_element_model import SiteElementType
from core.site_planner import SitePlanner
from ui.boundary_dialog import BoundaryClassificationDialog


SUBPLOT_COLORS = ["#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
                  "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7"]

ELEMENT_COLOR = {
    SiteElementType.BUDYNEK_GLOWNY: "#5b6d8a",
    SiteElementType.MIEJSCE_POSTOJOWE: "#3a3a3a",
    SiteElementType.STUDNIA: "#3498db",
    SiteElementType.SZAMBO: "#8b5e34",
    SiteElementType.STREFA_ZIELENI: "#88c082",
}


class Stage1Widget(QWidget):
    """Stage 1 panel — embeddable in QTabWidget."""

    # Stage 1 -> Stage 4 integration (Mode B SF only)
    apartment_layout_requested = pyqtSignal(object, object, object)
    # args: (polygon: shapely.Polygon, entry: (x, y), wall_types: list[WallType])

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded_polygon: Polygon | None = None
        self._user_boundaries: list | None = None
        # AC polling state (so we can wait for the user to select something
        # in ArchiCAD without blocking the GUI).
        self._poll_timer: QTimer | None = None
        self._poll_attempts = 0
        self._poll_max_attempts = 60   # 60 × 1 s = 60 s
        self._poll_initial_guids: set = set()
        # Stage 1 -> Stage 4 (Mode B only) selection state
        self._mode_b_result = None         # last SubdivisionResult, for click hit-test
        self._selected_sub_idx = None      # index into result.sub_plots
        self._build_ui()
        self._refresh_outline_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        left = QVBoxLayout()

        # 1. Plot outline
        outline_box = QGroupBox("1. Plot outline")
        ol = QGridLayout(outline_box)
        ol.addWidget(QLabel("Width [m]:"), 0, 0)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(20.0, 500.0); self.width_spin.setValue(60.0)
        self.width_spin.setSingleStep(1.0)
        ol.addWidget(self.width_spin, 0, 1)
        ol.addWidget(QLabel("Depth [m]:"), 1, 0)
        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(20.0, 500.0); self.depth_spin.setValue(80.0)
        self.depth_spin.setSingleStep(1.0)
        ol.addWidget(self.depth_spin, 1, 1)
        self.load_ac_btn = QPushButton("Load from ArchiCAD")
        self.load_ac_btn.clicked.connect(self._load_from_ac)
        ol.addWidget(self.load_ac_btn, 2, 0, 1, 2)
        self.edit_boundaries_btn = QPushButton("Edytuj klasyfikację granic")
        self.edit_boundaries_btn.setEnabled(False)
        self.edit_boundaries_btn.setToolTip(
            "Otwórz dialog wyboru typu każdej krawędzi działki "
            "(DROGA, SĄSIAD, WŁASNA). Aktywne po Load from ArchiCAD."
        )
        self.edit_boundaries_btn.clicked.connect(self._edit_boundaries)
        ol.addWidget(self.edit_boundaries_btn, 3, 0, 1, 2)
        left.addWidget(outline_box)

        # 2. Housing type + mode (Q12 + Q18)
        flow_box = QGroupBox("2. Housing type and mode (Q12)")
        fl = QGridLayout(flow_box)
        fl.addWidget(QLabel("Housing:"), 0, 0)
        self.h_jednorodzinna = QRadioButton("Jednorodzinna")
        self.h_wielorodzinna = QRadioButton("Wielorodzinna")
        self.h_jednorodzinna.setChecked(True)
        self.h_group = QButtonGroup(self)
        self.h_group.addButton(self.h_jednorodzinna)
        self.h_group.addButton(self.h_wielorodzinna)
        fl.addWidget(self.h_jednorodzinna, 0, 1)
        fl.addWidget(self.h_wielorodzinna, 1, 1)

        fl.addWidget(QLabel("Mode:"), 2, 0)
        self.m_whole_plot = QRadioButton("A — whole-plot")
        self.m_subdivision = QRadioButton("B — subdivision (jednorodzinna only)")
        self.m_whole_plot.setChecked(True)
        self.m_group = QButtonGroup(self)
        self.m_group.addButton(self.m_whole_plot)
        self.m_group.addButton(self.m_subdivision)
        fl.addWidget(self.m_whole_plot, 2, 1)
        fl.addWidget(self.m_subdivision, 3, 1)
        left.addWidget(flow_box)

        # 3. MPZP parameters (Miejscowy Plan Zagospodarowania Przestrzennego)
        mpzp_box = QGroupBox("3. Parametry z planu miejscowego (MPZP)")
        ml = QGridLayout(mpzp_box)

        ml.addWidget(QLabel("Wskaźnik zabudowy max (WZ):"), 0, 0)
        self.wz_spin = QDoubleSpinBox()
        self.wz_spin.setRange(0.05, 0.95); self.wz_spin.setValue(0.30); self.wz_spin.setSingleStep(0.05)
        self.wz_spin.setToolTip("WZ = powierzchnia zabudowy / powierzchnia działki")
        ml.addWidget(self.wz_spin, 0, 1)

        ml.addWidget(QLabel("Wskaźnik intensywności max (WIZ):"), 1, 0)
        self.wiz_spin = QDoubleSpinBox()
        self.wiz_spin.setRange(0.10, 5.00); self.wiz_spin.setValue(0.60); self.wiz_spin.setSingleStep(0.10)
        self.wiz_spin.setToolTip("WIZ = łączna powierzchnia użytkowa wszystkich kondygnacji / powierzchnia działki")
        ml.addWidget(self.wiz_spin, 1, 1)

        ml.addWidget(QLabel("Pow. biologicznie czynna min (PBC) [%]:"), 2, 0)
        self.pbc_spin = QDoubleSpinBox()
        self.pbc_spin.setRange(0.0, 90.0); self.pbc_spin.setValue(40.0); self.pbc_spin.setSingleStep(5.0)
        self.pbc_spin.setToolTip("Minimalna powierzchnia biologicznie czynna jako % działki")
        ml.addWidget(self.pbc_spin, 2, 1)

        ml.addWidget(QLabel("Linia zabudowy od drogi [m]:"), 3, 0)
        self.setback_spin = QDoubleSpinBox()
        self.setback_spin.setRange(0.0, 30.0); self.setback_spin.setValue(5.0); self.setback_spin.setSingleStep(0.5)
        ml.addWidget(self.setback_spin, 3, 1)

        ml.addWidget(QLabel("Max liczba kondygnacji:"), 4, 0)
        self.floors_spin = QSpinBox()
        self.floors_spin.setRange(1, 30); self.floors_spin.setValue(2)
        ml.addWidget(self.floors_spin, 4, 1)

        ml.addWidget(QLabel("Min szerokość frontu działki [m]:"), 5, 0)
        self.front_spin = QDoubleSpinBox()
        self.front_spin.setRange(8.0, 50.0); self.front_spin.setValue(18.0); self.front_spin.setSingleStep(1.0)
        self.front_spin.setToolTip("Minimalny front pod-działki w trybie B (Q15)")
        ml.addWidget(self.front_spin, 5, 1)

        ml.addWidget(QLabel("Min szerokość drogi wewn. [m]:"), 6, 0)
        self.road_w_spin = QDoubleSpinBox()
        self.road_w_spin.setRange(3.0, 12.0); self.road_w_spin.setValue(4.5); self.road_w_spin.setSingleStep(0.5)
        self.road_w_spin.setToolTip("Minimalna szerokość drogi wewnętrznej (sięgacza) w trybie B (Q2)")
        ml.addWidget(self.road_w_spin, 6, 1)

        ml.addWidget(QLabel("Min powierzchnia pod-działki [m²]:"), 7, 0)
        self.min_area_spin = QDoubleSpinBox()
        self.min_area_spin.setRange(50.0, 5000.0); self.min_area_spin.setValue(400.0); self.min_area_spin.setSingleStep(50.0)
        self.min_area_spin.setToolTip("Pod-działki poniżej tej powierzchni trafiają do nieużytku")
        ml.addWidget(self.min_area_spin, 7, 1)

        ml.addWidget(QLabel("Max powierzchnia pod-działki [m²]:"), 8, 0)
        self.max_area_spin = QDoubleSpinBox()
        self.max_area_spin.setRange(200.0, 20000.0); self.max_area_spin.setValue(2000.0); self.max_area_spin.setSingleStep(100.0)
        self.max_area_spin.setToolTip("Algorytm zwiększa liczbę rzędów aż powierzchnia ≤ tej wartości")
        ml.addWidget(self.max_area_spin, 8, 1)

        self.infra_municipal = QCheckBox("Infrastruktura miejska (kanalizacja zbiorcza — pomija studnia/szambo)")
        self.infra_municipal.setChecked(True)
        ml.addWidget(self.infra_municipal, 9, 0, 1, 2)
        left.addWidget(mpzp_box)

        # 4. Mode B options
        modeb_box = QGroupBox("4. Tryb B — opcje (typ zabudowy)")
        bl = QGridLayout(modeb_box)
        bl.addWidget(QLabel("Typ zabudowy:"), 0, 0)
        self.bt_combo = QComboBox()
        self.bt_combo.addItems([
            "DETACHED — wolnostojący",
            "TWIN — bliźniak",
            "TERRACED — szeregowy",
        ])
        self.bt_combo.setToolTip(
            "TWIN i TERRACED wymagają bezpośredniego dostępu do publicznej drogi "
            "(parent's DROGA), DETACHED akceptuje tylko dostęp do drogi wewnętrznej"
        )
        bl.addWidget(self.bt_combo, 0, 1)
        self.open_in_stage4_btn = QPushButton("Otwórz wybraną sub-działkę w Stage 4")
        self.open_in_stage4_btn.setEnabled(False)
        self.open_in_stage4_btn.setToolTip(
            "Wybierz sub-działkę z proposed_building klikając ją na canvasie, "
            "potem otwórz jej obrys jako wejście do Stage 4."
        )
        self.open_in_stage4_btn.clicked.connect(self._on_open_in_stage4)
        bl.addWidget(self.open_in_stage4_btn, 1, 0, 1, 2)
        left.addWidget(modeb_box)

        # 5. Generate
        self.generate_btn = QPushButton("5. Generate")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #4a90d9; color: white; border-radius: 4px;"
        )
        self.generate_btn.clicked.connect(self._generate)
        left.addWidget(self.generate_btn)

        # 6. Result info — explicit colors so it's readable in both light/dark Qt themes
        self.info_lbl = QLabel("")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setTextFormat(Qt.RichText)
        self.info_lbl.setStyleSheet(
            "background-color: #ffffff; color: #1c1c1c; "
            "padding: 8px; font-size: 11px; "
            "border: 1px solid #b8b8b8; border-radius: 4px;"
        )
        self.info_lbl.setMinimumHeight(160)
        left.addWidget(self.info_lbl)

        # 7. Export PDF (Stage 1 Phase 3) — disabled until Mode A success
        self.export_pdf_btn = QPushButton("Eksport raportu PDF")
        self.export_pdf_btn.setMinimumHeight(32)
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setToolTip(
            "Wygeneruj 9-stronicowy raport PDF na podstawie wyników Mode A.\n"
            "Aktywny po wygenerowaniu wariantów (przycisk Generate)."
        )
        self.export_pdf_btn.clicked.connect(self._on_export_pdf)
        left.addWidget(self.export_pdf_btn)

        # Cache wyników do generacji raportu (Phase 3)
        # Mode A: tuple("A", plot, variants, indicators, verification)
        # Mode B: tuple("B", plot, subdivision_result)
        self._mode_a_results = None  # zachowana nazwa dla kompatybilnosci

        left.addStretch()
        left_widget = QWidget(); left_widget.setLayout(left)
        left_widget.setMaximumWidth(360)

        # Right: matplotlib canvas
        self.fig = Figure(figsize=(10, 8))
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_click)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.canvas, stretch=1)

        # Reactive UI state
        self.h_jednorodzinna.toggled.connect(self._update_mode_availability)
        self.h_wielorodzinna.toggled.connect(self._update_mode_availability)
        self.m_whole_plot.toggled.connect(self._update_modeb_box)
        self.m_subdivision.toggled.connect(self._update_modeb_box)
        self.width_spin.valueChanged.connect(self._refresh_outline_preview)
        self.depth_spin.valueChanged.connect(self._refresh_outline_preview)
        self._update_mode_availability()
        self._update_modeb_box()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _update_mode_availability(self):
        """Q12: Mode B is single-family only."""
        if self.h_wielorodzinna.isChecked():
            self.m_subdivision.setEnabled(False)
            self.m_subdivision.setToolTip(
                "Mode B (subdivision) is single-family only — Q12 decision"
            )
            self.m_whole_plot.setChecked(True)
        else:
            self.m_subdivision.setEnabled(True)
            self.m_subdivision.setToolTip("")

    def _update_modeb_box(self):
        self.bt_combo.setEnabled(self.m_subdivision.isChecked())

    def statusBar(self):
        win = self.window()
        if hasattr(win, "_real_status_bar") and win._real_status_bar:
            return win._real_status_bar
        class _Noop:
            def showMessage(self, msg): pass
        return _Noop()

    # ------------------------------------------------------------------
    # AC integration
    # ------------------------------------------------------------------

    def _load_from_ac(self):
        """Connect to AC and either load immediately (if selection exists)
        or start polling for the user to make a selection."""
        # Stop any in-flight Stage 4 polling timer so we don't compete for Tapir.
        try:
            mw = self.window()
            if hasattr(mw, "_poll_timer") and getattr(mw, "_poll_timer", None):
                if mw._poll_timer.isActive():
                    mw._poll_timer.stop()
        except Exception:
            pass

        try:
            from bridge.tapir_connection import TapirConnection
            tapir = TapirConnection()
            tapir.connect()
        except Exception as e:
            QMessageBox.warning(self, "ArchiCAD",
                                f"Cannot connect to ArchiCAD:\n{e}\n\n"
                                "Sprawdź czy AC jest uruchomiony i Tapir Add-On zainstalowany.")
            return

        # Snapshot current selection — so we can detect NEW elements via polling.
        try:
            initial = tapir.get_selected_elements()
            self._poll_initial_guids = {self._extract_guid(e) for e in initial}
        except Exception:
            initial = []
            self._poll_initial_guids = set()

        if initial:
            # Selection already present — load immediately.
            self._do_load_from_ac()
            return

        # Nothing selected — start polling. Change button to "Cancel".
        self.load_ac_btn.setText("Anuluj nasłuchiwanie (klik w AC żeby zaznaczyć)")
        try:
            self.load_ac_btn.clicked.disconnect()
        except Exception:
            pass
        self.load_ac_btn.clicked.connect(self._cancel_polling)

        self.statusBar().showMessage(
            "Nasłuchuję... W AC zaznacz Zone/Slab/Wall — "
            "auto-podpięcie po wykryciu (60s)"
        )

        self._poll_attempts = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_archicad_selection)
        self._poll_timer.start(1000)

    @staticmethod
    def _extract_guid(elem):
        if isinstance(elem, dict):
            eid = elem.get("elementId", elem)
            return eid.get("guid") if isinstance(eid, dict) else str(eid)
        return str(elem)

    def _poll_archicad_selection(self):
        """Check every 1s whether a new selection appeared in AC."""
        from bridge.tapir_connection import TapirConnection

        self._poll_attempts += 1
        if self._poll_attempts >= self._poll_max_attempts:
            self._cancel_polling()
            self.statusBar().showMessage(
                "Timeout 60s — w AC nie wykryto nowego zaznaczenia"
            )
            return

        try:
            tapir = TapirConnection()
            selected = tapir.get_selected_elements()
        except Exception:
            return

        if not selected:
            return

        current_guids = {self._extract_guid(e) for e in selected}
        new_guids = current_guids - self._poll_initial_guids
        if not new_guids:
            return  # same selection as at start (shouldn't happen but safety)

        # New selection — load it.
        self._poll_timer.stop()
        self._reset_load_button()
        self._do_load_from_ac()

    def _cancel_polling(self):
        if self._poll_timer is not None and self._poll_timer.isActive():
            self._poll_timer.stop()
        self._reset_load_button()
        self.statusBar().showMessage("Nasłuchiwanie anulowane")

    def _reset_load_button(self):
        self.load_ac_btn.setText("Load from ArchiCAD")
        try:
            self.load_ac_btn.clicked.disconnect()
        except Exception:
            pass
        self.load_ac_btn.clicked.connect(self._load_from_ac)

    def _do_load_from_ac(self):
        """Actually read the outline from ArchiCAD's current selection."""
        try:
            from bridge.tapir_connection import TapirConnection
            from bridge.boundary_reader import read_boundary_from_archicad
            from shapely.affinity import translate
            tapir = TapirConnection(); tapir.connect()
            polygon, _, _ = read_boundary_from_archicad(tapir)
            bx0, by0, bx1, by1 = polygon.bounds
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
            self.statusBar().showMessage(
                f"Załadowano działkę z AC: {shifted.area:.1f} m² "
                f"(bbox {w}×{d}m). Otwieram dialog klasyfikacji granic..."
            )
            self.edit_boundaries_btn.setEnabled(True)
            self._edit_boundaries()
        except Exception as e:
            QMessageBox.warning(self, "ArchiCAD",
                                f"Nie można wczytać obrysu:\n{e}")
            self._loaded_polygon = None

    def _edit_boundaries(self):
        """Open the BoundaryClassificationDialog and apply user's choices."""
        if self._loaded_polygon is None:
            QMessageBox.information(
                self, "Brak działki",
                "Najpierw wczytaj działkę z ArchiCAD lub przelicz "
                "z prostokąta (Generate)."
            )
            return
        try:
            plot = self._build_plot()
        except BuildableZoneInfeasible:
            QMessageBox.warning(self, "Działka za mała",
                                "Strefa zabudowy jest pusta — "
                                "edycja granic nie może pomóc.")
            return
        dialog = BoundaryClassificationDialog(plot, parent=self)
        if dialog.exec_() == dialog.Accepted:
            dialog.commit_to_plot()
            # Persist user-chosen classification so next _build_plot uses it.
            self._user_boundaries = [
                (b.boundary_type, b.no_openings) for b in plot.boundaries
            ]
            self.statusBar().showMessage(
                "Klasyfikacja granic zaktualizowana — kliknij Generate."
            )

    # ------------------------------------------------------------------
    # Pipeline build
    # ------------------------------------------------------------------

    def _build_plot(self):
        if self._loaded_polygon is not None:
            polygon = self._loaded_polygon
        else:
            w = self.width_spin.value(); d = self.depth_spin.value()
            polygon = Polygon([(0, 0), (w, 0), (w, d), (0, d)])

        mpzp = MPZPParameters(
            max_wz=self.wz_spin.value(),
            max_wiz=self.wiz_spin.value(),
            min_pbc_percent=self.pbc_spin.value(),
            setback_from_road=self.setback_spin.value(),
            max_floors=self.floors_spin.value(),
            infrastructure_municipal=self.infra_municipal.isChecked(),
            min_front_m=self.front_spin.value(),
            min_road_width_m=self.road_w_spin.value(),
            min_sub_plot_area_m2=self.min_area_spin.value(),
            max_sub_plot_area_m2=self.max_area_spin.value(),
        )
        housing = (
            HousingType.JEDNORODZINNA if self.h_jednorodzinna.isChecked()
            else HousingType.WIELORODZINNA
        )
        plot = wrap_polygon_as_plot(
            polygon, plot_number="UI-plot", housing_type=housing, mpzp=mpzp,
        )
        # Apply user's edge classification if they've used the dialog. Match
        # by edge index (boundaries are kept in input order by wrap_polygon_as_plot).
        if self._user_boundaries is not None and len(self._user_boundaries) == len(plot.boundaries):
            for b, (btype, no_openings) in zip(plot.boundaries, self._user_boundaries):
                b.boundary_type = btype
                b.no_openings = no_openings
        BuildableZoneBuilder().compute(plot)
        return plot

    def _generate(self):
        try:
            plot = self._build_plot()
        except BuildableZoneInfeasible as e:
            QMessageBox.warning(self, "Plot too small", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Plot build failed:\n{e}")
            return

        if self.m_subdivision.isChecked():
            self._run_mode_b(plot)
        else:
            self._run_mode_a(plot)

    # ------------------------------------------------------------------
    # Mode A — whole-plot
    # ------------------------------------------------------------------

    def _run_mode_a(self, plot):
        try:
            requested_elements = [
                SiteElementType.MIEJSCE_POSTOJOWE,
                SiteElementType.STUDNIA,
                SiteElementType.SZAMBO,
                SiteElementType.STREFA_ZIELENI,
            ]
            variants = SitePlanner().propose_max_buildup(plot, requested_elements)
            if not variants:
                self._mode_a_results = None
                self.export_pdf_btn.setEnabled(False)
                QMessageBox.warning(self, "No variants", "Site planner produced no variants.")
                return
            v = variants[0]
            indicators = PlotIndicatorCalculator().compute(plot, v.elements)
            verification = PlotVerifier().verify(plot, v.elements, walls=[],
                                                  indicators=indicators)
            self._render_mode_a(plot, v)
            self._show_mode_a_info(v, indicators, verification)
            # Cache dla Phase 3 PDF export — Mode A
            self._mode_a_results = ("A", plot, variants, indicators, verification)
            self.export_pdf_btn.setEnabled(True)
        except Exception as e:
            self._mode_a_results = None
            self.export_pdf_btn.setEnabled(False)
            QMessageBox.critical(self, "Mode A failed", f"{e}")

    def _render_mode_a(self, plot, variant):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        px, py = plot.geometry.exterior.xy
        # Plot outline — soft grey background
        ax.fill(px, py, alpha=0.05, color="#cccccc")
        ax.plot(px, py, color="black", linewidth=1.5)

        # Strefa dopuszczalnej zabudowy — wyraźna jasnozielona
        if plot.buildable_zone and not plot.buildable_zone.is_empty:
            zx, zy = plot.buildable_zone.exterior.xy
            ax.fill(zx, zy, color="#d4f1c5", alpha=0.45,
                    edgecolor="#27ae60", linewidth=1.2, linestyle="--")

        for el in variant.elements:
            if not el.geometry or el.geometry.is_empty:
                continue
            try:
                ex, ey = el.geometry.exterior.xy
            except Exception:
                continue
            color = ELEMENT_COLOR.get(el.element_type, "#888888")
            if el.element_type == SiteElementType.STREFA_ZIELENI:
                # Zielen renderowana TYLKO jeśli to NIE pokrywa się z buildable_zone
                # (otherwise it visually duplicates the zone). Skip the patch and
                # rely on the zone fill above.
                continue
            elif el.element_type == SiteElementType.BUDYNEK_GLOWNY:
                # Budynek — wyraźny kolor + etykieta
                ax.fill(ex, ey, color="#3a4f6e", alpha=0.92,
                        edgecolor="black", linewidth=1.5)
                cx, cy = el.geometry.centroid.x, el.geometry.centroid.y
                label = f"BUDYNEK\n{el.footprint_area:.0f} m²\n{el.floors} kondygnacji"
                ax.annotate(label, xy=(cx, cy), fontsize=10, ha="center", va="center",
                            color="white", weight="bold")
            else:
                ax.fill(ex, ey, color=color, alpha=0.85,
                        edgecolor="black", linewidth=0.6)
                if el.element_type == SiteElementType.MIEJSCE_POSTOJOWE:
                    n = el.metadata.get("space_count", 1)
                    cx, cy = el.geometry.centroid.x, el.geometry.centroid.y
                    ax.annotate(f"Parking ×{n}", xy=(cx, cy), fontsize=8, ha="center",
                                color="white", weight="bold")
                elif el.element_type == SiteElementType.STUDNIA:
                    cx, cy = el.geometry.centroid.x, el.geometry.centroid.y
                    ax.annotate("Studnia", xy=(cx, cy + 2), fontsize=8, ha="center",
                                color="black", weight="bold")
                elif el.element_type == SiteElementType.SZAMBO:
                    cx, cy = el.geometry.centroid.x, el.geometry.centroid.y
                    ax.annotate("Szambo", xy=(cx, cy), fontsize=8, ha="center",
                                color="white", weight="bold")

        legend = [
            mpatches.Patch(facecolor="#d4f1c5", alpha=0.45, edgecolor="#27ae60",
                           linestyle="--", label="Strefa dopuszczalnej zabudowy"),
            mpatches.Patch(color="#3a4f6e", label="Proponowany budynek"),
            mpatches.Patch(color=ELEMENT_COLOR[SiteElementType.MIEJSCE_POSTOJOWE], label="Parking"),
        ]
        if plot.housing_type == HousingType.JEDNORODZINNA and not plot.mpzp.infrastructure_municipal:
            legend += [
                mpatches.Patch(color=ELEMENT_COLOR[SiteElementType.STUDNIA], label="Studnia"),
                mpatches.Patch(color=ELEMENT_COLOR[SiteElementType.SZAMBO], label="Szambo"),
            ]
        ax.legend(handles=legend, loc="upper right", fontsize=9, framealpha=0.95)

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.set_title(
            f"Tryb A — {plot.housing_type.value}, wariant {variant.number}: "
            f"powierzchnia zabudowy {variant.footprint_area:.0f} m²    "
            f"WZ={variant.wz:.3f}    WIZ={variant.wiz:.3f}    "
            f"PBC={variant.pbc_percent:.1f}%",
            fontsize=10,
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _show_mode_a_info(self, variant, indicators, verification):
        violations = sum(1 for r in verification if r.status == VerificationStatus.NIEZGODNY)
        warnings = sum(1 for r in verification if r.status == VerificationStatus.OSTRZEZENIE)
        ok = sum(1 for r in verification if r.status == VerificationStatus.ZGODNY)

        lines = [
            f"<b>Variant 1 of 3</b>",
            f"Footprint: {variant.footprint_area:.1f} m²",
            f"WZ: {variant.wz:.3f} (limit {indicators.plot_area * 0.0:.0f}…)",
            f"WIZ: {variant.wiz:.3f}",
            f"PBC: {variant.pbc_percent:.1f}%",
            f"Headroom to max WZ: {variant.wz_headroom_percent:.1f}%",
            "",
            f"<b>Verification:</b> {ok} OK, {warnings} warning, {violations} violation",
        ]
        for r in verification:
            if r.status in (VerificationStatus.NIEZGODNY, VerificationStatus.OSTRZEZENIE):
                lines.append(f"{r.icon} {r.name}: {r.designed_value_str} vs {r.required_value_str}")
        self.info_lbl.setText("<br>".join(lines))

    # ------------------------------------------------------------------
    # Mode B — subdivision
    # ------------------------------------------------------------------

    def _run_mode_b(self, plot):
        # Invalidate cache na czas wykonania (bo Mode B uzywa innego pipeline)
        self._mode_a_results = None
        self.export_pdf_btn.setEnabled(False)
        bt_text = self.bt_combo.currentText().split(" ")[0]
        building_type = BuildingType[bt_text]
        try:
            result = subdivide_with_orientation_search(
                plot, building_type=building_type
            )
            # Mode B: propose building footprints per sub-plot (per building_type)
            from core.building_proposer import propose_buildings
            propose_buildings(result, building_type)
            self._mode_b_result = result
            self._selected_sub_idx = None
            self._render_mode_b(plot, result)
            self._show_mode_b_info(result)
            # Cache dla Phase 3 PDF export — Mode B
            self._mode_a_results = ("B", plot, result)
            self.export_pdf_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Mode B failed", f"{e}")

    # ------------------------------------------------------------------
    # Stage 1 Phase 3 — Export PDF report
    # ------------------------------------------------------------------

    def _on_export_pdf(self):
        """Open metadata dialog, build ReportData, generate PDF.

        Wymaga że Mode A został uruchomiony (_mode_a_results != None).
        """
        if self._mode_a_results is None:
            QMessageBox.warning(
                self, "Eksport PDF",
                "Najpierw wygeneruj warianty przyciskiem Generate (Mode A)."
            )
            return

        from datetime import date
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication, QDialog, QFileDialog

        from core.report_builder import build_report_data, build_report_data_mode_b
        from core.report_pdf import generate_pdf
        from ui.report_metadata_dialog import ReportMetadataDialog

        # Rozpoznaj tryb cache (Mode A vs Mode B)
        mode = self._mode_a_results[0]
        if mode == "A":
            plot = self._mode_a_results[1]
        elif mode == "B":
            plot = self._mode_a_results[1]
        else:
            QMessageBox.warning(self, "Eksport PDF", f"Nieznany tryb cache: {mode}")
            return

        # 1. Metadata dialog
        default_pid = f"Działka {date.today():%Y-%m-%d}"
        dlg = ReportMetadataDialog(self, default_plot_id=default_pid)
        if dlg.exec_() != QDialog.Accepted:
            self.statusBar().showMessage("Eksport PDF anulowany.", 3000)
            return
        meta = dlg.get_metadata()

        # 2. Save path picker
        suggested = f"Raport_{meta['plot_id'].replace('/', '-').replace(' ', '_')}_{date.today():%Y-%m-%d}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz raport jako…", suggested, "PDF (*.pdf)",
        )
        if not path:
            self.statusBar().showMessage("Eksport PDF anulowany.", 3000)
            return

        # 3. Build + render (synchronous z busy state)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if mode == "A":
                _, _, variants, indicators, verification = self._mode_a_results
                rd = build_report_data(
                    plot, variants, indicators, verification,
                    plot_id=meta["plot_id"],
                    plot_address=meta["plot_address"],
                    logo_path=meta["logo_path"],
                )
            else:  # mode == "B"
                _, _, subdivision_result = self._mode_a_results
                rd = build_report_data_mode_b(
                    plot, subdivision_result,
                    plot_id=meta["plot_id"],
                    plot_address=meta["plot_address"],
                    logo_path=meta["logo_path"],
                )
            generate_pdf(rd, output_path=path)
            self.statusBar().showMessage(f"PDF zapisany: {path}", 5000)
            QMessageBox.information(
                self, "Eksport PDF",
                f"Raport wygenerowany:\n{path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Eksport PDF — błąd",
                f"{type(e).__name__}: {e}",
            )
            self.statusBar().showMessage("Eksport PDF nieudany.", 5000)
        finally:
            QApplication.restoreOverrideCursor()

    def _on_canvas_click(self, event):
        """Mode B only: hit-test against sub_plots, set _selected_sub_idx."""
        if self._mode_b_result is None or event.xdata is None or event.ydata is None:
            return
        from shapely.geometry import Point
        pt = Point(event.xdata, event.ydata)
        for i, s in enumerate(self._mode_b_result.sub_plots):
            if s.polygon.contains(pt):
                self._selected_sub_idx = i
                self._render_mode_b(self._mode_b_result.parent, self._mode_b_result)
                self._update_open_in_stage4_btn()
                return
        # Click in empty space - clear selection.
        self._selected_sub_idx = None
        self._render_mode_b(self._mode_b_result.parent, self._mode_b_result)
        self._update_open_in_stage4_btn()

    def _update_open_in_stage4_btn(self):
        """Enable iff a sub-plot with proposed_building is currently selected."""
        if (self._mode_b_result is None
                or self._selected_sub_idx is None
                or self._selected_sub_idx >= len(self._mode_b_result.sub_plots)):
            self.open_in_stage4_btn.setEnabled(False)
            self.open_in_stage4_btn.setToolTip(
                "Kliknij sub-działkę na canvasie aby ją wybrać."
            )
            return
        sub = self._mode_b_result.sub_plots[self._selected_sub_idx]
        pb = getattr(sub, "proposed_building", None)
        if pb is None or pb.is_empty:
            self.open_in_stage4_btn.setEnabled(False)
            self.open_in_stage4_btn.setToolTip(
                "Brak proposed building — sprawdź strefę zabudowy tej sub-działki."
            )
            return
        self.open_in_stage4_btn.setEnabled(True)
        self.open_in_stage4_btn.setToolTip(
            f"Otwórz sub-działkę #{self._selected_sub_idx + 1} jako rzut w Stage 4."
        )

    def _on_open_in_stage4(self):
        """Emit apartment_layout_requested with derived (polygon, entry, walls)."""
        if self._mode_b_result is None or self._selected_sub_idx is None:
            return
        sub = self._mode_b_result.sub_plots[self._selected_sub_idx]
        pb = getattr(sub, "proposed_building", None)
        if pb is None or pb.is_empty:
            return
        from core.building_to_apartment_input import building_to_apartment_input
        polygon, entry, walls = building_to_apartment_input(
            sub, roads=self._mode_b_result.roads
        )
        self.apartment_layout_requested.emit(polygon, entry, walls)

    def _render_mode_b(self, plot, result):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        px, py = plot.geometry.exterior.xy
        ax.fill(px, py, alpha=0.04, color="black")
        ax.plot(px, py, color="black", linewidth=1.0)

        for i, s in enumerate(result.sub_plots):
            sx, sy = s.polygon.exterior.xy
            c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
            if i == self._selected_sub_idx:
                edge_color, edge_w = "#f1c40f", 3.0     # yellow highlight
            else:
                edge_color, edge_w = "black", 0.8
            ax.fill(sx, sy, color=c, alpha=0.7, edgecolor=edge_color, linewidth=edge_w)

            if s.has_buildable_zone:
                try:
                    zx, zy = s.buildable_zone.exterior.xy
                    ax.fill(zx, zy, color="#27ae60", alpha=0.18,
                            edgecolor="#27ae60", linewidth=0.5, linestyle="--")
                except Exception:
                    pass

            # Propozycja bryły budynku (Mode B per building_type)
            pb = getattr(s, "proposed_building", None)
            if pb is not None and not pb.is_empty:
                try:
                    bx, by = pb.exterior.xy
                    ax.fill(bx, by, color="#3a4f6e", alpha=0.85,
                            edgecolor="black", linewidth=1.0)
                except Exception:
                    pass

            cx, cy = s.polygon.centroid.x, s.polygon.centroid.y
            bz_area = s.buildable_zone.area if s.has_buildable_zone else 0
            ax.annotate(
                f"S{i+1}\n{s.area:.0f} m²\n(zone {bz_area:.0f})",
                xy=(cx, cy), fontsize=7, ha="center", va="center",
            )

        for road in result.roads:
            rx, ry = road.exterior.xy
            ax.fill(rx, ry, color="#3a3a3a", alpha=0.85)
            ax.annotate("ROAD", xy=(road.centroid.x, road.centroid.y),
                        color="white", fontsize=7, ha="center", weight="bold")

        if result.nieuzytek and not result.nieuzytek.is_empty:
            polys = [result.nieuzytek] if isinstance(result.nieuzytek, Polygon) \
                    else list(result.nieuzytek.geoms)
            for poly in polys:
                try:
                    wx, wy = poly.exterior.xy
                    ax.fill(wx, wy, color="#aa6644", alpha=0.45, hatch="\\\\",
                            edgecolor="#aa6644", linewidth=0.5)
                except Exception:
                    pass

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        title_ok = "OK" if result.coverage_ok() else f"DIFF={result.coverage_diff:.2f}m²"
        ax.set_title(
            f"Tryb B — {result.orientation_name}, "
            f"{len(result.sub_plots)} pod-działek, "
            f"zabudowa={result.buildable_area_percent:.1f}%, "
            f"droga={result.road_area_percent:.1f}%, "
            f"nieużytek={result.nieuzytek_percent:.1f}%    Q16: {title_ok}",
            fontsize=10,
        )

        legend = [
            mpatches.Patch(color=SUBPLOT_COLORS[0], label="Pod-działki (S1..SN)"),
            mpatches.Patch(facecolor="#27ae60", alpha=0.18,
                           edgecolor="#27ae60", linestyle="--",
                           label="Strefa zabudowy w pod-działce"),
            mpatches.Patch(color="#3a3a3a", label="Droga wewnętrzna (sięgacz)"),
            mpatches.Patch(facecolor="#aa6644", alpha=0.45, hatch="\\\\",
                           edgecolor="#aa6644", label="Nieużytek"),
        ]
        ax.legend(handles=legend, loc="upper right", fontsize=8, framealpha=0.95)

        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _show_mode_b_info(self, result):
        lines = [
            f"<b>Layout:</b> {result.orientation_name}, {result.rows} rows × {result.cols} cols",
            f"<b>Sub-plots:</b> {len(result.sub_plots)}",
            f"<b>Buildable zones:</b> {result.total_buildable_area:.1f} m² "
            f"({result.buildable_area_percent:.1f}%)",
            f"<b>Roads:</b> {result.total_road_area:.1f} m² "
            f"({result.road_area_percent:.1f}%)",
            f"<b>Nieużytek:</b> {result.nieuzytek_area:.1f} m² "
            f"({result.nieuzytek_percent:.1f}%)",
            f"<b>Sub-plots without road access:</b> "
            f"{result.sub_plots_without_road_access}",
            f"<b>Q16 coverage:</b> diff={result.coverage_diff:.2f} m² "
            f"({'OK' if result.coverage_ok() else 'FAIL'})",
            f"<b>All sub-plots have buildable zone:</b> "
            f"{'YES' if result.all_have_buildable_zone else 'NO'}",
            "",
            "<b>Per-sub-plot:</b>",
        ]
        for i, s in enumerate(result.sub_plots):
            bz = s.buildable_zone.area if s.has_buildable_zone else 0
            lines.append(
                f"S{i+1}: {s.area:.0f} m², zone {bz:.0f} m², "
                f"front {s.front_length:.1f} m"
            )
        self.info_lbl.setText("<br>".join(lines))

    # ------------------------------------------------------------------
    # Outline preview (before generation)
    # ------------------------------------------------------------------

    def _refresh_outline_preview(self):
        self._loaded_polygon = None
        self._render_outline_preview(self.width_spin.value(), self.depth_spin.value())

    def _render_outline_preview(self, w, d):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.fill([0, w, w, 0], [0, 0, d, d], alpha=0.10, color="lightgray")
        ax.plot([0, w, w, 0, 0], [0, 0, d, d, 0], color="black", linewidth=2)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.set_title(
            f"Plot {w:.1f} × {d:.1f} m  ({w*d:.0f} m²) — "
            "set parameters and click Generate"
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    def _render_polygon_preview(self, polygon):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        fx, fy = polygon.exterior.xy
        ax.fill(fx, fy, alpha=0.10, color="lightgray")
        ax.plot(fx, fy, color="black", linewidth=2)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.set_title(
            f"Plot from AC — {polygon.area:.1f} m² "
            f"({len(list(polygon.exterior.coords))-1} vertices)"
        )
        ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()


class Stage1Window(QMainWindow):
    """Standalone window wrapping Stage1Widget."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FloorPlan6 — Stage 1: Plot Analyser")
        self.setMinimumSize(1280, 800)
        self.setStatusBar(QStatusBar())
        self._real_status_bar = self.statusBar()
        self.setCentralWidget(Stage1Widget(self))
        self._real_status_bar.showMessage("Ready")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = Stage1Window()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
