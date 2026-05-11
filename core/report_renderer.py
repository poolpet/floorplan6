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


# Status color mapping (zielony/żółty/czerwony, plus text-friendly symbols).
STATUS_COLOR = {
    "OK": "#27AE60",
    "WARN": "#F39C12",
    "VIOLATION": "#E74C3C",
    "ZGODNY": "#27AE60",
    "OSTRZEZENIE": "#F39C12",
    "NIEZGODNY": "#E74C3C",
    "NIEWERYFIKOWANY": "#95A5A6",
}

STATUS_SYMBOL = {
    "OK": "+",
    "WARN": "!",
    "VIOLATION": "X",
    "ZGODNY": "+",
    "OSTRZEZENIE": "!",
    "NIEZGODNY": "X",
    "NIEWERYFIKOWANY": "?",
}


def indicators_bar_chart(rd: ReportData) -> Figure:
    """Horizontal bar chart: designed vs limit for WZ, WIZ, PBC.

    Page 5 of the report. Each row shows a colored bar (length = designed
    fraction of limit, capped at 1.0) plus the status icon and a numeric label.
    """
    fig, ax = plt.subplots(figsize=(A4_WIDTH_IN, 3.5))
    rows = rd.indicators or []

    if not rows:
        ax.text(0.5, 0.5, "Brak wskaźników", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    y_positions = list(range(len(rows)))
    fractions = [
        (row.designed / row.limit if row.limit > 0 else 0.0)
        for row in rows
    ]
    colors = [STATUS_COLOR.get(row.status, "#888") for row in rows]

    ax.barh(y_positions, fractions, color=colors, alpha=0.75, edgecolor="black")
    ax.axvline(x=1.0, color="red", linestyle="--", linewidth=1, label="Limit")
    ax.axvline(x=1.05, color="orange", linestyle=":", linewidth=1, label="Limit + 5% (Q14)")

    # Labels
    ax.set_yticks(y_positions)
    ax.set_yticklabels([row.name for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.20)
    ax.set_xlabel("Designed ÷ Limit")

    for i, row in enumerate(rows):
        symbol = STATUS_SYMBOL.get(row.status, "?")
        label = f"{row.designed:.2f}{row.unit} / {row.limit:.2f}{row.unit}  [{symbol}]"
        ax.text(1.21, i, label, va="center", fontsize=9)

    ax.set_title("Wskaźniki MPZP — designed vs limit", fontsize=11)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.tight_layout()
    return fig


def variants_grid_figure(rd: ReportData) -> Figure:
    """3-up grid showing each buildup variant with WZ + units estimate.

    Page 7 of the report. Each panel = one variant. Shows polygon shape,
    footprint area, WZ, and estimated apartment count.
    """
    variants = rd.buildup_variants or []
    n = max(1, len(variants))
    fig, axes = plt.subplots(1, n, figsize=(A4_WIDTH_IN, 3.5), squeeze=False)
    axes = axes.flatten()

    for i, variant in enumerate(variants):
        ax = axes[i]
        # Simple placeholder: draw a rectangle proportional to footprint area.
        # If we have an actual polygon WKT per variant in future, render that.
        side = (variant.footprint_area_m2) ** 0.5
        ax.add_patch(mpatches.Rectangle((0, 0), side, side,
                                          facecolor="#90CAF9", edgecolor="black"))
        ax.set_xlim(-5, side + 5)
        ax.set_ylim(-5, side + 5)
        ax.set_aspect("equal")
        ax.set_title(f"Wariant {chr(ord('A') + variant.number - 1)}", fontsize=10)
        ax.text(0.5, -0.15,
                f"{variant.footprint_area_m2:.0f} m²\n"
                f"WZ {variant.wz:.2f}\n"
                f"~{variant.estimated_units} mieszkań",
                transform=ax.transAxes, ha="center", va="top", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused panels
    for j in range(len(variants), n):
        axes[j].set_axis_off()

    fig.suptitle("Warianty zabudowy + szacunek liczby mieszkań", fontsize=11)
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    return fig
