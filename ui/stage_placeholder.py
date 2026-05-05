"""
Placeholder widgets for stages not yet implemented.

Each placeholder shows what the stage is supposed to do, what's already
prepared in the codebase, and what a contributor would need to build.
Intended as an open invitation for collaboration.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


def _heading(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont(); f.setPointSize(16); f.setBold(True)
    lbl.setFont(f)
    lbl.setStyleSheet("color: #2266cc; padding: 8px;")
    return lbl


def _section(title: str, body: str) -> QTextEdit:
    box = QTextEdit()
    box.setReadOnly(True)
    box.setHtml(f"<h3>{title}</h3>{body}")
    box.setMaximumHeight(260)
    return box


class Stage1PlotPlaceholder(QWidget):
    """Stage 1 — plot subdivision, MPZP analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(_heading("Stage 1 — Plot Subdivision (planned)"))

        intro = QLabel(
            "Inputs: a building plot polygon (from ArchiCAD or DXF) and zoning "
            "rules (Polish MPZP — local development plan). Output: a set of "
            "sub-plots with the buildable zone and access roads marked."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("padding: 6px; color: #444;")
        layout.addWidget(intro)

        layout.addWidget(_section("Why this matters", """
            <p>An architect receives a parcel and zoning constraints (max
            coverage, max height, building line setbacks, road frontage
            requirement, etc.). Manually testing how many buildings fit is
            slow. This stage automates the search and proposes a
            sub-division compatible with MPZP.</p>
        """))

        layout.addWidget(_section("What's already in the repo", """
            <ul>
              <li>Reference C++ implementation: <code>FloorPlan4_CPP</code>
                  (MPZP analyzer numerical, plot subdivider with 4 known bugs
                  — see <code>docs/LESSONS_LEARNED.md</code>).</li>
              <li>Open architectural questions: Q1–Q5 in
                  <code>docs/OPEN_QUESTIONS.md</code> (clipping vs reject
                  sub-plots that overlap plot boundary, road layout, front
                  side rule, twin-house definition, grid orientation).</li>
              <li>Shapely + matplotlib stack ready (Stage 4 / Stage 3 use it).</li>
            </ul>
        """))

        layout.addWidget(_section("What a contributor would do", """
            <ol>
              <li>Decide Q1–Q5 with project owner (Dawid).</li>
              <li>Implement <code>core/plot_solver.py</code> using Shapely
                  for geometric operations and matplotlib for visual
                  iteration. Avoid jumping straight to C++ (lesson learned).</li>
              <li>Implement <code>core/mpzp.py</code> — read MPZP parameters
                  (max coverage %, max PUM, max height, frontage rules) and
                  apply as constraints.</li>
              <li>UI: replace this placeholder with an interactive widget
                  that loads a plot polygon, accepts MPZP parameters, runs
                  the solver, renders the sub-division.</li>
              <li>Tests: at least 5 reference plots with known good
                  sub-divisions, regression-tested.</li>
            </ol>
        """))

        layout.addWidget(_section("Estimated effort", """
            <p>Solo developer: 2–3 weeks for an MVP that handles rectangular
            plots and simple MPZP. L-shaped plots and complex frontage
            rules add another 1–2 weeks.</p>
        """))

        btn = QPushButton("Open OPEN_QUESTIONS.md (Q1–Q5)")
        btn.setEnabled(False)
        btn.setToolTip(
            "Q1–Q5 are documented in docs/OPEN_QUESTIONS.md. Read them and "
            "discuss with the project owner before coding."
        )
        layout.addWidget(btn)

        layout.addStretch()


class Stage2VolumePlaceholder(QWidget):
    """Stage 2 — volumetric (3D) generator from a footprint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(_heading("Stage 2 — Volumetric Generator (planned)"))

        intro = QLabel(
            "Inputs: a building footprint polygon (from Stage 1 or AC), the "
            "number of storeys, storey height, roof type. Output: a 3D mass "
            "model exportable to ArchiCAD as Slabs + Roof."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("padding: 6px; color: #444;")
        layout.addWidget(intro)

        layout.addWidget(_section("Why this matters", """
            <p>Once the footprint is known, the next decision is the
            volume: number of storeys, storey heights, roof shape (flat,
            gable, hip, mansard). This stage produces the building volume
            ready for energy analysis and detailed floor plans (Stage 3).</p>
        """))

        layout.addWidget(_section("What's already in the repo", """
            <ul>
              <li>Stage 3 (this app) consumes a floor outline; volumetric
                  generator would feed Stage 3 with one outline per storey
                  (some storeys may differ — e.g. attic).</li>
              <li>WT 2002 height parameters (storey height, total height
                  vs. building class N/SW/W/WW) already in
                  <code>config.py</code> and <code>docs/WT_PARAMETERS.md</code>.</li>
              <li>ArchiCAD bridge in <code>bridge/tapir_connection.py</code>
                  has <code>create_zones</code>; needs an analogous
                  <code>create_slabs</code> / <code>create_roof</code>.</li>
            </ul>
        """))

        layout.addWidget(_section("What a contributor would do", """
            <ol>
              <li>Implement <code>core/volume_generator.py</code> taking a
                  footprint and producing a list of <code>Storey</code>
                  objects (each with its own outline polygon + height).</li>
              <li>Implement <code>core/roof_generator.py</code> for common
                  roof types (flat, gable along long axis, hip).</li>
              <li>Extend <code>bridge/plan_writer.py</code> with
                  <code>create_slabs</code> and <code>create_roofs</code>
                  (ACAPI exposes <code>API_SlabType</code> and
                  <code>API_RoofType</code>; map to Tapir commands).</li>
              <li>UI: replace this placeholder with a widget that loads
                  the footprint, accepts storey count + heights + roof type,
                  renders a 3D preview (matplotlib 3D or pyvista) and exports
                  to AC.</li>
            </ol>
        """))

        layout.addWidget(_section("Estimated effort", """
            <p>Solo developer: 1–2 weeks for an MVP with flat roof and
            uniform storey heights. Pitched roofs and storey variations
            add 1 week.</p>
        """))

        layout.addStretch()
