"""
Wizualizacja rzutów mieszkań — matplotlib.

Renders FloorPlan as a colored diagram with room labels.
Implementowany WCZEŚNIE (BŁĄD #10 z CLAUDE.md) — debugowanie geometrii
bez rysunku jest NIEMOŻLIWE.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from matplotlib.path import Path as MplPath
from shapely.geometry import Polygon
from shapely.ops import unary_union

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


# Poché ścian (MVP credibility): grubość zewn./wewn. w metrach + barwa masy ściany.
WALL_EXT = 0.30
WALL_INT = 0.12
POCHE_COLOR = "#9E9E9E"


def _wall_poche_polygon(boundary_poly, room_polys, w_ext: float = WALL_EXT,
                        w_int: float = WALL_INT):
    """Wielokąt masy ścian: (obrys − unia pokoi skurczonych o w_int/2) ∪ pierścień zewn. w_ext.

    Pokoje stykają się (F1=100%), więc każdy skurcza się o w_int/2 → między dwoma
    sąsiadami zostaje fuga w_int (ściana działowa); przy obrysie zostaje pierścień,
    pogrubiony osobno do w_ext (ściana zewnętrzna).
    """
    shrunk = []
    for p in room_polys:
        geoms = p.geoms if p.geom_type == "MultiPolygon" else [p]
        for g in geoms:
            s = g.buffer(-w_int / 2.0)
            if not s.is_empty:
                shrunk.append(s)
    inner = unary_union(shrunk) if shrunk else boundary_poly
    walls = boundary_poly.difference(inner)
    ext_ring = boundary_poly.difference(boundary_poly.buffer(-w_ext))
    return unary_union([walls, ext_ring])


def _polygon_patch(geom, **kw):
    """matplotlib PathPatch z wielokąta Shapely (z dziurami → wnętrza pokoi przebijają)."""
    verts, codes = [], []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.coords)
            if len(cs) < 3:
                continue
            verts.extend(cs)
            codes.append(MplPath.MOVETO)
            codes.extend([MplPath.LINETO] * (len(cs) - 2))
            codes.append(MplPath.CLOSEPOLY)
    return mpatches.PathPatch(MplPath(verts, codes), **kw)


def _draw_walls(ax, boundary_poly, rooms):
    """Narysuj masę ścian (poché). Strefa dzienna scalona → bez ściany salon↔kuchnia."""
    if boundary_poly is None:
        return
    polys = [r.polygon for r in rooms if r.polygon is not None]
    if not polys:
        return
    day = [r.polygon for r in rooms
           if r.polygon is not None and r.spec.strefa == Strefa.DZIENNA]
    other = [r.polygon for r in rooms
             if r.polygon is not None and r.spec.strefa != Strefa.DZIENNA]
    merged = other + ([unary_union(day)] if len(day) >= 2 else day)
    wall = _wall_poche_polygon(boundary_poly, merged)
    if wall.is_empty:
        return
    ax.add_patch(_polygon_patch(wall, facecolor=POCHE_COLOR, edgecolor="none", zorder=2.6))


def render_floor_plan(
    plan: FloorPlan,
    title: Optional[str] = None,
    save_path: Optional[Path] = None,
    show: bool = True,
    figsize: tuple[float, float] = (10, 8),
    furniture: Optional[list] = None,
) -> plt.Figure:
    """Renderuj FloorPlan jako matplotlib figure.

    Args:
        plan: Wygenerowany rzut.
        title: Tytuł wykresu.
        save_path: Ścieżka do zapisu PNG (opcjonalna).
        show: Czy wyświetlić interaktywnie.
        figsize: Rozmiar figury.
        furniture: lista Furniture (MVP — rzut „z meblami"); None → bez mebli.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize)

    # Rysuj obrys
    _draw_boundary(ax, plan.boundary)

    # Rysuj pokoje (etykiety odsunięte od mebli)
    furn_by_room: dict[str, list] = {}
    for f in (furniture or []):
        furn_by_room.setdefault(f.room_id, []).append(f.polygon)
    for room in plan.rooms:
        _draw_room(ax, room, furniture_polys=furn_by_room.get(room.spec.id))

    # Masa ścian (poché) — nad pokojami, pod meblami/etykietami
    _draw_walls(ax, getattr(plan.boundary, "polygon", None), plan.rooms)

    # Meble + drzwi + okna (MVP)
    if furniture:
        _draw_furniture(ax, furniture)
    _draw_doors(ax, plan.rooms)
    _draw_windows(ax, plan.rooms, plan.boundary)

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
    if furniture:
        legend_patches.append(mpatches.Patch(facecolor="#A1887F", edgecolor="#4E342E", label="Meble"))
    # legenda POD rzutem (poziomo) — nie zasłania etykiet pokoi
    ax.legend(handles=legend_patches, loc="upper center", bbox_to_anchor=(0.5, -0.08),
              ncol=len(legend_patches) or 1, fontsize=9, framealpha=0.9)

    # info POD rzutem, z lewej (poza obszarem danych) — nie nachodzi na tytuł ani meble
    info_text = (
        f"Outline: {plan.boundary.area:.1f} m²   "
        f"Rooms: {plan.total_room_area:.1f} m²   "
        f"Hub: {plan.hub_percent * 100:.1f}%"
    )
    ax.text(0.0, -0.15, info_text, transform=ax.transAxes,
            fontsize=8, verticalalignment="top", horizontalalignment="left",
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

    # Knee-wall v2 (S29): poddasze = pełny footprint; na panelu PODDASZE rysujemy
    # strefy niskiej ścianki kolankowej (przyciemnienie + linia ścianki).
    strips = getattr(layout, "attic_low_strips", None) or []
    _draw_storey(ax_p, layout.parter_rooms, layout.boundary, core_abs,
                 parter_furniture or [], "PARTER")
    _draw_storey(ax_g, layout.pietro_rooms, layout.boundary, core_abs,
                 pietro_furniture or [],
                 "PODDASZE" if strips else "PIĘTRO",
                 low_strips=strips)

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


def _draw_storey(ax, rooms, boundary, core_abs, furniture, title, low_strips=None):
    # obrys
    if boundary is not None and getattr(boundary, "polygon", None) is not None:
        bx, by = boundary.polygon.exterior.xy
        ax.plot(bx, by, color="black", linewidth=2.5, zorder=2)
        bnds = boundary.polygon.bounds
    else:
        xs = [c for r in rooms if r.polygon for c in (r.polygon.bounds[0], r.polygon.bounds[2])]
        ys = [c for r in rooms if r.polygon for c in (r.polygon.bounds[1], r.polygon.bounds[3])]
        bnds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)
    # Knee-wall v2 (S29): strefy niskiej ścianki kolankowej — delikatne przyciemnienie
    # + przerywana LINIA ŚCIANKI (wewnętrzna krawędź strefy, h≈1.9 m).
    for s in (low_strips or []):
        sx0, sy0, sx1, sy1 = s.bounds
        ax.add_patch(mpatches.Rectangle((sx0, sy0), sx1 - sx0, sy1 - sy0,
                                        facecolor="black", alpha=0.07,
                                        edgecolor="none", zorder=3.5))
        eps = 1e-6
        if abs(sy0 - bnds[1]) < eps and sy1 < bnds[3] - eps:      # strefa przy dolnym okapie
            ax.plot([sx0, sx1], [sy1, sy1], color="#616161", lw=1.0, ls="--", zorder=3.6)
        elif abs(sy1 - bnds[3]) < eps and sy0 > bnds[1] + eps:    # przy górnym okapie
            ax.plot([sx0, sx1], [sy0, sy0], color="#616161", lw=1.0, ls="--", zorder=3.6)
        elif abs(sx0 - bnds[0]) < eps and sx1 < bnds[2] - eps:    # przy lewym okapie
            ax.plot([sx1, sx1], [sy0, sy1], color="#616161", lw=1.0, ls="--", zorder=3.6)
        elif abs(sx1 - bnds[2]) < eps and sx0 > bnds[0] + eps:    # przy prawym okapie
            ax.plot([sx0, sx0], [sy0, sy1], color="#616161", lw=1.0, ls="--", zorder=3.6)

    # Open-plan day-zone (faza 1): pokoje DZIENNA (salon+kuchnia) to JEDNA otwarta
    # przestrzeń — rysuj je bez krawędzi wewnętrznych, a potem jeden obrys ich unii
    # (brak linii ściany między salon↔kuchnia; ta sama barwa DZIENNA scala je wizualnie).
    day_rooms = [r for r in rooms if r.polygon is not None and r.spec.strefa == Strefa.DZIENNA]
    furn_by_room: dict[str, list] = {}
    for f in furniture:
        furn_by_room.setdefault(f.room_id, []).append(f.polygon)
    for room in rooms:
        _draw_room(ax, room, draw_edge=(room not in day_rooms),
                   furniture_polys=furn_by_room.get(room.spec.id))
    if len(day_rooms) >= 2:
        from shapely.ops import unary_union
        union = unary_union([r.polygon for r in day_rooms])
        geoms = union.geoms if union.geom_type == "MultiPolygon" else [union]
        edge = STREFA_EDGE_COLORS.get(Strefa.DZIENNA, "#333333")
        for g in geoms:
            gx, gy = g.exterior.xy
            ax.plot(gx, gy, color=edge, linewidth=1.5, zorder=3)
    # Approach B: schody to OSOBNY pokój — rysuj symbol biegu WEWNĄTRZ niego (orientacja
    # wg krawędzi z holem). Fallback (układ bez pokoju 'schody', np. smoke) → overlay rdzenia.
    schody = next((r for r in rooms if r.spec.id == "schody"), None)
    if schody is not None and schody.polygon is not None:
        hol = next((r for r in rooms if r.spec.id == "hub"), None)
        _draw_stair_in_room(ax, schody, hol)
    else:
        _draw_stair(ax, core_abs)
    _draw_walls(ax, getattr(boundary, "polygon", None), rooms)
    _draw_furniture(ax, furniture)
    _draw_doors(ax, rooms)
    _draw_windows(ax, rooms, boundary)

    ax.set_title(title, fontsize=13, fontweight="bold")
    legend_patches = [
        mpatches.Patch(facecolor=color, edgecolor="black", label=strefa.display)
        for strefa, color in STREFA_COLORS.items()
        if any(r.spec.strefa == strefa for r in rooms)
    ]
    if furniture:
        legend_patches.append(mpatches.Patch(facecolor="#A1887F", edgecolor="#4E342E", label="Meble"))
    # legenda POD panelem (poziomo) — nie zasłania etykiet pokoi (MVP credibility)
    ax.legend(handles=legend_patches, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              ncol=len(legend_patches) or 1, fontsize=8, framealpha=0.9)

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


def _draw_doors(ax, rooms):
    """Symbole drzwi (otwór + skrzydło + łuk swingu) na styku pokój↔komunikacja."""
    from core.door_extractor import infer_door_openings
    for d in infer_door_openings(rooms):
        _draw_door_symbol(ax, d)


def _draw_door_symbol(ax, d):
    cx, cy = d.center
    w = d.width
    if d.axis == "v":                                  # ściana pionowa x=cx, otwór wzdłuż y
        p1, p2 = (cx, cy - w / 2), (cx, cy + w / 2)
        sign = 1.0 if d.into[0] > cx else -1.0         # wnętrze pokoju po stronie ±x
        leaf_end = (cx + sign * w, p1[1])
    else:                                              # ściana pozioma y=cy, otwór wzdłuż x
        p1, p2 = (cx - w / 2, cy), (cx + w / 2, cy)
        sign = 1.0 if d.into[1] > cy else -1.0
        leaf_end = (p1[0], cy + sign * w)
    hinge = p1
    # "wytnij" otwór w ścianie (biały odcinek)
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="white", linewidth=2.6,
            solid_capstyle="butt", zorder=5)
    if getattr(d, "is_opening", False):
        return                       # otwarcie bez skrzydła (strefa dzienna↔hol) — sam otwór
    # skrzydło + łuk swingu
    ax.plot([hinge[0], leaf_end[0]], [hinge[1], leaf_end[1]], color="#5D4037",
            linewidth=1.0, zorder=6)
    a1 = math.degrees(math.atan2(p2[1] - hinge[1], p2[0] - hinge[0]))
    a2 = math.degrees(math.atan2(leaf_end[1] - hinge[1], leaf_end[0] - hinge[0]))
    ax.add_patch(mpatches.Arc(hinge, 2 * w, 2 * w, angle=0.0,
                              theta1=min(a1, a2), theta2=max(a1, a2),
                              color="#5D4037", linewidth=0.8, zorder=6))


def _draw_windows(ax, rooms, boundary):
    """Okna na fasadzie — gruba jasnoniebieska linia na ścianie pokoju z oknem (wymaga_okna)."""
    if boundary is None:
        return
    from core.window_extractor import extract_facade_windows
    for w in extract_facade_windows(rooms, boundary):
        (x1, y1), (x2, y2) = w.p1, w.p2
        ax.plot([x1, x2], [y1, y2], color="#1565C0", linewidth=3.2,
                solid_capstyle="butt", zorder=6)
        ax.plot([x1, x2], [y1, y2], color="#E3F2FD", linewidth=1.0,
                solid_capstyle="butt", zorder=7)


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


def _draw_room(ax: plt.Axes, room: Room, draw_edge: bool = True, furniture_polys=None):
    """Rysuj pojedynczy pokój. draw_edge=False → tylko wypełnienie bez krawędzi
    (dla pokoi open-plan, których wspólny obrys rysuje się osobno).
    furniture_polys → etykieta nazwy jest odsuwana od mebli (nie nachodzi na łóżko/szafę)."""
    if room.polygon is None:
        return

    color = STREFA_COLORS.get(room.spec.strefa, "#E0E0E0")
    edge_color = STREFA_EDGE_COLORS.get(room.spec.strefa, "#333333") if draw_edge else "none"
    lw = 1.5 if draw_edge else 0.0

    # Obsługa MultiPolygon (L-kształtne pokoje po carving)
    if room.polygon.geom_type == "MultiPolygon":
        for geom in room.polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=lw)
    else:
        x, y = room.polygon.exterior.xy
        ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=lw)

    # Etykieta — odsunięta od mebli (gdy podane), inaczej w centrum pokoju
    cx, cy = _label_anchor(room.polygon, furniture_polys or [])

    label = f"{room.spec.nazwa}\n{room.area:.1f} m²"
    fontsize = _auto_fontsize(room)

    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold",
            color="#333333", zorder=3.6,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      alpha=0.7, edgecolor="none"))


def _label_anchor(poly, furniture_polys) -> tuple[float, float]:
    """Punkt na etykietę nazwy pokoju — WEWNĄTRZ pokoju, jak najdalej od mebli.

    Odporne na pokoje L/U i MultiPolygon: centroid bywa w wycięciu (poza pokojem), więc
    fallback to representative_point (zawsze wewnątrz). Z meblami: spośród kandydatów
    (centroid + siatka 5×5) wybierz leżący w pokoju o największym dystansie do mebla."""
    from shapely.geometry import Point
    g = poly
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    c = g.centroid
    rep = g.representative_point()                 # gwarantowany punkt wewnątrz
    centroid_inside = g.contains(c)
    if not furniture_polys:
        return (c.x, c.y) if centroid_inside else (rep.x, rep.y)
    from shapely.ops import unary_union
    union = unary_union(list(furniture_polys))
    minx, miny, maxx, maxy = g.bounds
    cands = ([(c.x, c.y)] if centroid_inside else []) + [(rep.x, rep.y)]
    n = 5
    for i in range(n):
        for j in range(n):
            cands.append((minx + (maxx - minx) * (i + 0.5) / n,
                          miny + (maxy - miny) * (j + 0.5) / n))
    inner = g.buffer(-1e-6)
    if inner.is_empty:                             # cienki pokój → użyj samego polygonu
        inner = g
    best, best_d = (rep.x, rep.y), -1.0            # domyślnie gwarantowany punkt wewnątrz
    for x, y in cands:
        pt = Point(x, y)
        if not inner.contains(pt):
            continue
        d = pt.distance(union)                     # 0 gdy punkt na meblu
        if d > best_d:
            best_d, best = d, (x, y)
    return best


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
