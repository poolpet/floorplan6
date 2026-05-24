"""
Stage 1 Mode B — OBB recursive subdivision (Vanegas/Aliaga/Müller 2012).

Per LESSONS_LEARNED W6 + B1: cul-de-sac approach failed twice → REWRITE.
This prototype implements the algorithm used by Esri CityEngine and
described in "Procedural Generation of Parcels in Urban Modeling"
(Eurographics 2012).

Algorithm:
  1. Force first split PERPENDICULAR to DROGA edge (creates the trunk
     road that connects to public street).
  2. Recursive OBB split on each half:
     - Compute polygon's minimum-area oriented bounding box (OBB).
     - Split perpendicular to the OBB's long axis at midpoint.
     - Reserve a road_w-wide strip along the cut line — that's the
       branch road, automatically touching the trunk on the half edge.
     - Recurse on each child until area ∈ [min_area, max_area] or
     - splitting would produce a child below min_area (stop, accept
       oversize).
  3. Absorption: any leftover (parent − sub_plots − roads) merged into
     the nearest sub-plot.

Result: every sub-plot has road access (its split road touches a
parent road, all the way up to the trunk which touches DROGA),
hierarchical road network forms naturally as a tree (T/L shapes
emerge for irregular plots), road area minimised because each road
serves the sub-tree below it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.affinity import rotate, translate
from shapely.geometry import (
    LineString, MultiPolygon, Point, Polygon, box,
)
from shapely.ops import split as shapely_split, unary_union

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# OBB primitives
# ─────────────────────────────────────────────────────────────────────────────

def obb_long_axis(poly: Polygon) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Return ((midpoint of long edge), (unit vector along long axis), long_length).

    Uses Shapely's minimum_rotated_rectangle as the OBB.
    """
    obb = poly.minimum_rotated_rectangle
    coords = list(obb.exterior.coords)[:-1]   # 4 corners
    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in edges]
    long_idx = max(range(4), key=lambda i: lengths[i])
    a, b = edges[long_idx]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    long_len = lengths[long_idx]
    if long_len < 1e-9:
        return mid, (1.0, 0.0), 0.0
    unit = ((b[0] - a[0]) / long_len, (b[1] - a[1]) / long_len)
    return mid, unit, long_len


def split_with_road(
    poly: Polygon,
    cut_point: Tuple[float, float],
    cut_direction: Tuple[float, float],
    road_w: float,
) -> Tuple[Optional[Polygon], Optional[Polygon], Optional[Polygon]]:
    """Split `poly` by an infinite line at cut_point with cut_direction.

    A strip of width road_w along the cut line is removed as the road.
    Returns (left_child, right_child, road_strip) or all None on failure.
    """
    # Build a long line through cut_point along cut_direction.
    diag = math.hypot(*[poly.bounds[2] - poly.bounds[0],
                        poly.bounds[3] - poly.bounds[1]]) * 2
    p_a = (cut_point[0] - cut_direction[0] * diag,
           cut_point[1] - cut_direction[1] * diag)
    p_b = (cut_point[0] + cut_direction[0] * diag,
           cut_point[1] + cut_direction[1] * diag)
    cut_line = LineString([p_a, p_b])

    # Road strip = cut_line buffered by road_w/2 on each side, intersected with poly.
    road_strip = cut_line.buffer(road_w / 2, cap_style=2).intersection(poly)
    if road_strip.is_empty:
        return None, None, None

    # Children = poly minus road strip
    children_geom = poly.difference(road_strip)
    if children_geom.is_empty:
        return None, None, None

    if isinstance(children_geom, Polygon):
        # Couldn't split (line missed the interior?) — accept poly as-is
        return None, None, None

    parts = [g for g in children_geom.geoms if isinstance(g, Polygon)]
    if len(parts) < 2:
        return None, None, None

    parts.sort(key=lambda p: -p.area)
    # Keep two largest pieces; smaller fragments will be absorbed later.
    return parts[0], parts[1], road_strip if isinstance(road_strip, Polygon) \
        else max(road_strip.geoms, key=lambda g: g.area)


def perpendicular(unit: Tuple[float, float]) -> Tuple[float, float]:
    return (-unit[1], unit[0])


# ─────────────────────────────────────────────────────────────────────────────
# OBB recursive subdivision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ObbResult:
    sub_plots: List[Polygon] = field(default_factory=list)
    roads: List[Polygon] = field(default_factory=list)
    leftover: Optional[Polygon] = None


def _has_road_access(
    child_poly: Polygon,
    droga_edges: List[LineString],
    road_polys: List[Polygon],
    min_overlap: float = 0.5,
) -> bool:
    """True if `child_poly` has any boundary segment lying on DROGA or
    on an existing road's boundary (≥ min_overlap shared length)."""
    boundary = child_poly.boundary

    def _length(g) -> float:
        if g.is_empty:
            return 0.0
        if hasattr(g, "length") and not hasattr(g, "geoms"):
            return g.length
        return sum(getattr(piece, "length", 0.0) for piece in getattr(g, "geoms", []))

    for d in droga_edges:
        try:
            if _length(boundary.intersection(d)) > min_overlap:
                return True
        except Exception:
            pass
    for r in road_polys:
        try:
            if _length(boundary.intersection(r.boundary)) > min_overlap:
                return True
        except Exception:
            pass
    return False


def _recursive_obb_split(
    poly: Polygon,
    min_area: float,
    max_area: float,
    road_w: float,
    droga_edges: List[LineString],
    all_roads: List[Polygon],
    *,
    depth: int = 0,
    max_depth: int = 10,
    forced_direction: Optional[Tuple[float, float]] = None,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Recursive OBB binary subdivision with smart road skipping (v2)."""
    if poly.area <= max_area or depth >= max_depth:
        return [poly], []

    obb_mid, long_unit, long_len = obb_long_axis(poly)
    obb_center = (
        poly.minimum_rotated_rectangle.centroid.x,
        poly.minimum_rotated_rectangle.centroid.y,
    )
    if long_len < 1e-9:
        return [poly], []

    if forced_direction is not None:
        cut_direction = forced_direction
    else:
        cut_direction = perpendicular(long_unit)
    cut_point = obb_center

    left, right, road = split_with_road(poly, cut_point, cut_direction, road_w)
    if left is None or right is None:
        return [poly], []
    if min(left.area, right.area) < min_area:
        return [poly], []

    # Smart road skipping — depth 0 (trunk) always adds road. Deeper levels
    # only add road if at least one child lacks access to existing roads/DROGA.
    if depth == 0:
        add_road = True
    else:
        add_road = not (
            _has_road_access(left, droga_edges, all_roads)
            and _has_road_access(right, droga_edges, all_roads)
        )

    if add_road:
        new_all_roads = all_roads + [road]
        emitted_roads = [road]
    else:
        new_all_roads = all_roads
        emitted_roads = []

    sp_l, rd_l = _recursive_obb_split(
        left, min_area, max_area, road_w, droga_edges, new_all_roads,
        depth=depth + 1, max_depth=max_depth, forced_direction=None,
    )
    sp_r, rd_r = _recursive_obb_split(
        right, min_area, max_area, road_w, droga_edges, new_all_roads,
        depth=depth + 1, max_depth=max_depth, forced_direction=None,
    )
    return sp_l + sp_r, emitted_roads + rd_l + rd_r


def subdivide_obb(
    plot_polygon: Polygon,
    droga_edge: Optional[LineString],
    min_area: float = 400.0,
    max_area: float = 2000.0,
    road_w: float = 4.5,
    max_depth: int = 10,
) -> ObbResult:
    """OBB recursive subdivision with DROGA-aligned trunk + smart skipping."""
    forced = None
    droga_edges: List[LineString] = []
    if droga_edge is not None and droga_edge.length > 0:
        coords = list(droga_edge.coords)
        dx = coords[-1][0] - coords[0][0]
        dy = coords[-1][1] - coords[0][1]
        droga_len = math.hypot(dx, dy)
        if droga_len > 1e-6:
            droga_unit = (dx / droga_len, dy / droga_len)
            forced = perpendicular(droga_unit)
            droga_edges = [droga_edge]

    sub_plots, roads = _recursive_obb_split(
        plot_polygon, min_area, max_area, road_w, droga_edges, all_roads=[],
        depth=0, max_depth=max_depth, forced_direction=forced,
    )

    # Absorption: any uncovered area → merged into nearest sub-plot.
    occupied = unary_union(sub_plots + roads)
    leftover = plot_polygon.difference(occupied)
    if not leftover.is_empty:
        sub_plots = _absorb(sub_plots, leftover)

    return ObbResult(sub_plots=sub_plots, roads=roads, leftover=None)


def _absorb(sub_plots: List[Polygon], leftover) -> List[Polygon]:
    """Merge each leftover piece into nearest sub-plot (longest shared edge)."""
    pieces = [leftover] if isinstance(leftover, Polygon) else list(leftover.geoms)
    pieces = [p for p in pieces if isinstance(p, Polygon) and p.area > 0.01]
    out = list(sub_plots)
    for piece in pieces:
        if not out:
            continue
        # Pick best target: longest shared boundary.
        best_i, best_score = 0, -1.0
        for i, sp in enumerate(out):
            try:
                shared = sp.boundary.intersection(piece.boundary)
                score = shared.length if hasattr(shared, "length") else 0.0
            except Exception:
                score = 0.0
            if score > best_score:
                best_score = score
                best_i = i
        merged = out[best_i].union(piece)
        if isinstance(merged, Polygon):
            out[best_i] = merged
        else:
            out[best_i] = max(merged.geoms, key=lambda p: p.area)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Test cases & rendering
# ─────────────────────────────────────────────────────────────────────────────

def case_regular():
    poly = Polygon([(0, 0), (60, 0), (60, 80), (0, 80)])
    droga = LineString([(0, 0), (60, 0)])
    return "Regular 60×80", poly, droga


def case_big_regular():
    poly = Polygon([(0, 0), (230, 0), (230, 211), (0, 211)])
    droga = LineString([(0, 0), (230, 0)])
    return "Big 230×211", poly, droga


def case_slanted():
    poly = Polygon([(0, 22), (200, 0), (200, 68), (75, 68), (75, 42), (0, 55)])
    droga = LineString([(0, 22), (200, 0)])
    return "Slanted 200×68 (irregular)", poly, droga


def case_irregular_polygon():
    poly = Polygon([(0, 0), (150, 0), (220, 65), (230, 230), (75, 250)])
    droga = LineString([(0, 0), (150, 0)])
    return "Irregular polygon (5 vertices)", poly, droga


def render(ax, name: str, poly: Polygon, droga: LineString, result: ObbResult):
    px, py = poly.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=1.0)

    # DROGA edge highlighted in red
    dx, dy = droga.xy
    ax.plot(dx, dy, color="#e74c3c", linewidth=4.0, label="DROGA (public)", zorder=2)

    palette = ["#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
               "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7"]
    for i, sp in enumerate(result.sub_plots):
        sx, sy = sp.exterior.xy
        ax.fill(sx, sy, color=palette[i % len(palette)], alpha=0.7,
                edgecolor="black", linewidth=0.6)
        cx, cy = sp.centroid.x, sp.centroid.y
        ax.annotate(f"S{i + 1}\n{sp.area:.0f} m²",
                    xy=(cx, cy), fontsize=6, ha="center", va="center")

    for road in result.roads:
        try:
            rx, ry = road.exterior.xy
            ax.fill(rx, ry, color="#3a3a3a", alpha=0.85)
        except Exception:
            pass

    n = len(result.sub_plots)
    sub_total = sum(s.area for s in result.sub_plots)
    road_total = sum(r.area for r in result.roads if isinstance(r, Polygon))
    coverage = (sub_total + road_total) / poly.area * 100
    ax.set_title(
        f"{name} — {n} sub-plots, road {road_total:.0f} m², "
        f"coverage {coverage:.1f}%",
        fontsize=10,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def main():
    cases = [case_regular(), case_big_regular(), case_slanted(),
             case_irregular_polygon()]

    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    for ax, (name, poly, droga) in zip(axes.flat, cases):
        result = subdivide_obb(poly, droga, min_area=400, max_area=2000)
        render(ax, name, poly, droga, result)
        n = len(result.sub_plots)
        sub_total = sum(s.area for s in result.sub_plots)
        road_total = sum(r.area for r in result.roads if isinstance(r, Polygon))
        cov = (sub_total + road_total) / poly.area * 100
        print(f"{name}: {n} sub-plots, road={road_total:.0f} m², "
              f"coverage={cov:.2f}%")

    fig.suptitle(
        "Stage 1 Mode B — OBB recursive subdivision prototype "
        "(Vanegas/Aliaga/Müller 2012)",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = OUT_DIR / "stage1_obb_v1.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
