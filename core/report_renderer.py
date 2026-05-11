"""Report Renderer — matplotlib figures embedded into the PDF report.

Each figure is a Figure object. Caller (report_pdf.py) saves to PNG buffer,
embeds into reportlab Image flowable.

Convention:
    - All figures use figsize tuned for A4 portrait page width (8.27 in).
    - White background, dark text — PDF-print friendly.
    - No emoji icons in figures — pure ASCII / matplotlib markers (broader font compat).
"""
from __future__ import annotations

from typing import List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from shapely import wkt

from core.report_data import ComplianceRow, IndicatorRow, ReportData, VariantInfo

# A4 portrait usable width minus margins (in inches).
A4_WIDTH_IN = 7.0


def plot_zone_figure(rd: ReportData) -> Figure:
    """Plot polygon + buildable zone overlay + setback annotations.

    Page 4 of the report. Shows the plot outline (black), buildable zone
    (green fill), and labels for setback distances.
    """
    fig, ax = plt.subplots(figsize=(A4_WIDTH_IN, 5.0))

    if rd.plot_polygon_wkt:
        plot_poly = wkt.loads(rd.plot_polygon_wkt)
        x, y = plot_poly.exterior.xy
        ax.plot(x, y, color="black", linewidth=1.5, label="Granica działki")
        ax.fill(x, y, color="#FFFAF0", alpha=0.3)

    if rd.buildable_polygon_wkt:
        bz_poly = wkt.loads(rd.buildable_polygon_wkt)
        bx, by = bz_poly.exterior.xy
        ax.fill(bx, by, color="#C8E6C9", alpha=0.6, label="Buildable zone")
        ax.plot(bx, by, color="#2E7D32", linewidth=1.0, linestyle="--")

    # Setback annotations
    sb = rd.setbacks
    ax.text(
        0.02, 0.98,
        f"Linia zabudowy:\n  od drogi: {sb.front_m} m\n"
        f"  od boku: {sb.side_m} m\n  od tyłu: {sb.rear_m} m",
        transform=ax.transAxes,
        va="top", fontsize=9,
        bbox=dict(facecolor="white", edgecolor="gray", boxstyle="round,pad=0.5"),
    )

    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"Działka {rd.plot_id} — strefa zabudowy", fontsize=11)
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig
