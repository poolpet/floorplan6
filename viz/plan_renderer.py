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


def render_two_storey(
    layout,
    parter_furniture: Optional[list] = None,
    pietro_furniture: Optional[list] = None,
    title: Optional[str] = None,
    save_path: Optional[Path] = None,
    show: bool = True,
    figsize: tuple[float, float] = (16, 8),
) -> plt.Figure:
    """Renderuj dom 2-kondygnacyjny (TwoStoreyLayout) — 2 panele PARTER | PIĘTRO.

    Rysuje pokoje (wg strefy), wyrównaną klatkę schodową (ten sam (x,y) na obu
    panelach — z poprawnym offsetem bbox) oraz meble (jeśli podane).
    """
    fig, (ax_p, ax_g) = plt.subplots(1, 2, figsize=figsize)

    # stair_core jest bbox-relative (lokalny) → na absolutny frame pokoi dodaj origin bbox
    bx0, by0 = _frame_origin(layout)
    sx, sy, sw, sh = layout.stair_core
    core_abs = (sx + bx0, sy + by0, sw, sh)

    _draw_storey(ax_p, layout.parter_rooms, layout.boundary, core_abs,
                 parter_furniture or [], "PARTER")
    _draw_storey(ax_g, layout.pietro_rooms, layout.boundary, core_abs,
                 pietro_furniture or [], "PIĘTRO")

    if title is None:
        title = "Dom jednorodzinny 2-kondygnacyjny"
    fig.suptitle(title, fontsize=15, fontweight="bold")
    plt.tight_layout(rect=(0, 0, 1, 0.96))

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    return fig


def _frame_origin(layout) -> tuple[float, float]:
    """Origin (minx, miny) wspólnego frame pokoi. Z boundary, fallback z pokoi."""
    b = getattr(layout, "boundary", None)
    if b is not None and getattr(b, "polygon", None) is not None:
        bb = b.polygon.bounds
        return bb[0], bb[1]
    polys = [r.polygon for r in (*layout.parter_rooms, *layout.pietro_rooms) if r.polygon]
    if polys:
        return min(p.bounds[0] for p in polys), min(p.bounds[1] for p in polys)
    return 0.0, 0.0


def _draw_storey(ax, rooms, boundary, core_abs, furniture, title):
    # obrys
    if boundary is not None and getattr(boundary, "polygon", None) is not None:
        bx, by = boundary.polygon.exterior.xy
        ax.plot(bx, by, color="black", linewidth=2.5, zorder=2)
        bnds = boundary.polygon.bounds
    else:
        xs = [c for r in rooms if r.polygon for c in (r.polygon.bounds[0], r.polygon.bounds[2])]
        ys = [c for r in rooms if r.polygon for c in (r.polygon.bounds[1], r.polygon.bounds[3])]
        bnds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)

    for room in rooms:
        _draw_room(ax, room)
    # Approach B: schody to OSOBNY pokój — rysuj symbol biegu WEWNĄTRZ niego (orientacja
    # wg krawędzi z holem). Fallback (układ bez pokoju 'schody', np. smoke) → overlay rdzenia.
    schody = next((r for r in rooms if r.spec.id == "schody"), None)
    if schody is not None and schody.polygon is not None:
        hol = next((r for r in rooms if r.spec.id == "hub"), None)
        _draw_stair_in_room(ax, schody, hol)
    else:
        _draw_stair(ax, core_abs)
    _draw_furniture(ax, furniture)

    ax.set_title(title, fontsize=13, fontweight="bold")
    legend_patches = [
        mpatches.Patch(facecolor=color, edgecolor="black", label=strefa.display)
        for strefa, color in STREFA_COLORS.items()
        if any(r.spec.strefa == strefa for r in rooms)
    ]
    if furniture:
        legend_patches.append(mpatches.Patch(facecolor="#A1887F", edgecolor="#4E342E", label="Meble"))
    ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

    bx0, by0, bx1, by1 = bnds
    margin = max(bx1 - bx0, by1 - by0) * 0.05
    ax.set_xlim(bx0 - margin, bx1 + margin)
    ax.set_ylim(by0 - margin, by1 + margin)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")


def stair_run_orientation(schody_bounds, hol_bounds):
    """(run_axis, arrow_dir) dla symbolu schodów (Approach B).

    Bieg idzie wzdłuż DŁUŻSZEJ osi rdzenia (stopnie prostopadle). Strzałka 'w górę'
    odchodzi OD holu (podest/wejście na bieg po stronie holu — wspinasz się w głąb).
    run_axis: 'horizontal' | 'vertical'. arrow_dir: 'N'|'S'|'E'|'W'.
    schody_bounds/hol_bounds: (minx, miny, maxx, maxy); hol_bounds może być None.
    """
    sx0, sy0, sx1, sy1 = schody_bounds
    sw, sh = sx1 - sx0, sy1 - sy0
    scx, scy = (sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0
    if hol_bounds is not None:
        dx = (hol_bounds[0] + hol_bounds[2]) / 2.0 - scx
        dy = (hol_bounds[1] + hol_bounds[3]) / 2.0 - scy
    else:
        dx = dy = 0.0
    tol = 0.15  # rdzeń ~kwadratowy (U): oś biegu zależy od strony holu, nie szumu float
    if abs(sw - sh) <= tol:
        run_x = abs(dx) >= abs(dy)
    else:
        run_x = sw > sh  # wyraźny prostokąt → bieg wzdłuż dłuższej osi
    if run_x:  # bieg poziomy, strzałka 'w górę' odchodzi OD holu (W jeśli hol na E)
        return ("horizontal", "W" if dx > 0 else "E")
    return ("vertical", "S" if dy > 0 else "N")


def _draw_stair_in_room(ax, schody, hol):
    """Symbol biegu WEWNĄTRZ pokoju 'schody' — stopnie + strzałka 'w górę' (bez
    osobnego prostokąta/etykiety; pokój jest już narysowany i podpisany 'Schody')."""
    sx, sy, ex, ey = schody.polygon.bounds
    sw, sh = ex - sx, ey - sy
    color = "#B71C1C"
    hb = hol.polygon.bounds if (hol is not None and hol.polygon is not None) else None
    axis, arrow = stair_run_orientation(schody.polygon.bounds, hb)
    if axis == "vertical":                      # bieg ↕ — stopnie poziome
        n = max(3, int(sh / 0.28))
        for k in range(1, n):
            y = sy + sh * k / n
            ax.plot([sx, ex], [y, y], color=color, linewidth=0.5, zorder=5)
        x_mid = sx + sw / 2
        y0, y1 = (sy + sh * 0.12, sy + sh * 0.88) if arrow == "N" else (sy + sh * 0.88, sy + sh * 0.12)
        ax.annotate("", xy=(x_mid, y1), xytext=(x_mid, y0),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.2), zorder=6)
    else:                                       # bieg ↔ — stopnie pionowe
        n = max(3, int(sw / 0.28))
        for k in range(1, n):
            x = sx + sw * k / n
            ax.plot([x, x], [sy, ey], color=color, linewidth=0.5, zorder=5)
        y_mid = sy + sh / 2
        x0, x1 = (sx + sw * 0.12, sx + sw * 0.88) if arrow == "E" else (sx + sw * 0.88, sx + sw * 0.12)
        ax.annotate("", xy=(x1, y_mid), xytext=(x0, y_mid),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.2), zorder=6)


def _draw_stair(ax, core_abs):
    """Symbol klatki schodowej — czerwony prostokąt + stopnie + strzałka 'w górę'."""
    sx, sy, sw, sh = core_abs
    ax.add_patch(mpatches.Rectangle((sx, sy), sw, sh, fill=False,
                                    edgecolor="#D32F2F", linewidth=2.0, zorder=5))
    if sw >= sh:                                   # stopnie prostopadłe do dłuższego boku
        n = max(3, int(sw / 0.28))
        for k in range(1, n):
            x = sx + sw * k / n
            ax.plot([x, x], [sy, sy + sh], color="#D32F2F", linewidth=0.5, zorder=5)
        ax.annotate("", xy=(sx + sw * 0.88, sy + sh / 2), xytext=(sx + sw * 0.12, sy + sh / 2),
                    arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1.2), zorder=6)
    else:
        n = max(3, int(sh / 0.28))
        for k in range(1, n):
            y = sy + sh * k / n
            ax.plot([sx, sx + sw], [y, y], color="#D32F2F", linewidth=0.5, zorder=5)
        ax.annotate("", xy=(sx + sw / 2, sy + sh * 0.88), xytext=(sx + sw / 2, sy + sh * 0.12),
                    arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1.2), zorder=6)
    ax.text(sx + sw / 2, sy + sh * 0.5, "SCHODY", ha="center", va="center", fontsize=6,
            color="#B71C1C", fontweight="bold", zorder=7,
            bbox=dict(boxstyle="round,pad=0.1", facecolor="white", alpha=0.6, edgecolor="none"))


def _draw_furniture(ax, furniture):
    for f in furniture:
        x, y = f.polygon.exterior.xy
        ax.fill(x, y, facecolor="#A1887F", edgecolor="#4E342E",
                linewidth=0.8, alpha=0.85, zorder=4)
        if f.polygon.area >= 0.45:
            c = f.polygon.centroid
            ax.text(c.x, c.y, f.label, ha="center", va="center",
                    fontsize=5, color="#3E2723", zorder=6)


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
