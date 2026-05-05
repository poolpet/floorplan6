"""
Wizualizacja rzutów mieszkań — matplotlib.

Renders FloorPlan as a colored diagram with room labels.
Implementowany WCZEŚNIE (BŁĄD #10 z CLAUDE.md) — debugowanie geometrii
bez rysunku jest NIEMOŻLIWE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from shapely.geometry import Polygon

from core.models import FloorPlan, Room, Boundary, Strefa


# Kolory stref
STREFA_COLORS = {
    Strefa.DZIENNA: "#FFE082",     # ciepły żółty
    Strefa.NOCNA: "#90CAF9",       # jasny niebieski
    Strefa.USLUGOWA: "#CE93D8",    # fioletowy
    Strefa.KOMUNIKACJA: "#A5D6A7", # zielony
}

STREFA_EDGE_COLORS = {
    Strefa.DZIENNA: "#F9A825",
    Strefa.NOCNA: "#1565C0",
    Strefa.USLUGOWA: "#7B1FA2",
    Strefa.KOMUNIKACJA: "#2E7D32",
}


def render_floor_plan(
    plan: FloorPlan,
    title: Optional[str] = None,
    save_path: Optional[Path] = None,
    show: bool = True,
    figsize: tuple[float, float] = (10, 8),
) -> plt.Figure:
    """Renderuj FloorPlan jako matplotlib figure.

    Args:
        plan: Wygenerowany rzut.
        title: Tytuł wykresu.
        save_path: Ścieżka do zapisu PNG (opcjonalna).
        show: Czy wyświetlić interaktywnie.
        figsize: Rozmiar figury.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize)

    # Rysuj obrys
    _draw_boundary(ax, plan.boundary)

    # Rysuj pokoje
    for room in plan.rooms:
        _draw_room(ax, room)

    # Tytuł
    if title is None:
        title = f"{plan.template.nazwa} — {plan.boundary.area:.1f} m²"
        if plan.score > 0:
            title += f" (score: {plan.score:.2f})"
    ax.set_title(title, fontsize=14, fontweight="bold")

    # Legenda stref
    legend_patches = []
    for strefa, color in STREFA_COLORS.items():
        if any(r.spec.strefa == strefa for r in plan.rooms):
            legend_patches.append(mpatches.Patch(
                facecolor=color, edgecolor="black",
                label=strefa.display,
            ))
    ax.legend(handles=legend_patches, loc="upper right", fontsize=9)

    info_text = (
        f"Outline area: {plan.boundary.area:.1f} m²\n"
        f"Rooms area: {plan.total_room_area:.1f} m²\n"
        f"Hub: {plan.hub_percent * 100:.1f}%"
    )
    ax.text(0.02, 0.02, info_text, transform=ax.transAxes,
            fontsize=8, verticalalignment="bottom",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    if show:
        plt.show()

    return fig


def render_rooms_only(
    rooms: list[Room],
    boundary: Boundary,
    title: str = "Pokoje",
    save_path: Optional[Path] = None,
    show: bool = True,
) -> plt.Figure:
    """Renderuj listę pokoi bez pełnego FloorPlan (do debugowania)."""
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    _draw_boundary(ax, boundary)
    for room in rooms:
        _draw_room(ax, room)
    ax.set_title(title, fontsize=14)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    return fig


def _draw_boundary(ax: plt.Axes, boundary: Boundary):
    """Rysuj obrys mieszkania."""
    x, y = boundary.polygon.exterior.xy
    ax.plot(x, y, color="black", linewidth=2.5)

    # Oznacz drzwi wejściowe
    ex, ey = boundary.entry_point
    ax.plot(ex, ey, "rv", markersize=12, label="Drzwi wejściowe")
    ax.annotate("ENTRY", (ex, ey), textcoords="offset points",
                xytext=(0, -15), ha="center", fontsize=8, color="red",
                fontweight="bold")

    # Marginesy
    bx0, by0, bx1, by1 = boundary.bbox
    margin = max(bx1 - bx0, by1 - by0) * 0.05
    ax.set_xlim(bx0 - margin, bx1 + margin)
    ax.set_ylim(by0 - margin, by1 + margin)


def _draw_room(ax: plt.Axes, room: Room):
    """Rysuj pojedynczy pokój."""
    if room.polygon is None:
        return

    color = STREFA_COLORS.get(room.spec.strefa, "#E0E0E0")
    edge_color = STREFA_EDGE_COLORS.get(room.spec.strefa, "#333333")

    # Obsługa MultiPolygon (L-kształtne pokoje po carving)
    if room.polygon.geom_type == "MultiPolygon":
        for geom in room.polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=1.5)
    else:
        x, y = room.polygon.exterior.xy
        ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=1.5)

    # Etykieta w centrum pokoju
    cx = room.polygon.centroid.x
    cy = room.polygon.centroid.y

    label = f"{room.spec.nazwa}\n{room.area:.1f} m²"
    fontsize = _auto_fontsize(room)

    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold",
            color="#333333",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      alpha=0.7, edgecolor="none"))


def _auto_fontsize(room: Room) -> float:
    """Dopasuj rozmiar czcionki do wielkości pokoju."""
    if room.area > 20:
        return 9
    elif room.area > 10:
        return 8
    elif room.area > 5:
        return 7
    return 6


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    from shapely.geometry import Polygon as SPoly
    from core.boundary_analyzer import analyze_boundary
    from core.template_selector import select_templates
    from core.wall_assigner import assign_facades
    from core.dimensioner import dimension_rooms

    # Test: M2 na prostokącie 8×6m
    poly = SPoly([(0, 0), (8, 0), (8, 6), (0, 6)])
    boundary = analyze_boundary(poly, (4.0, 0.0))
    template = select_templates("M2", boundary)[0]
    variants = assign_facades(template, boundary)
    rooms = dimension_rooms(template, boundary, variants[0])

    plan = FloorPlan(
        boundary=boundary,
        template=template,
        rooms=rooms,
    )

    render_floor_plan(
        plan,
        title="Test M2 — 8×6m",
        save_path=Path("test_render_m2.png"),
        show=False,
    )
    print("Zapisano test_render_m2.png")
