"""
Stage 1 Mode B — buildable-area-maximizing subdivision (REWRITE #2).

Per owner spec 2026-05-08: PRIMARY GOAL of Stage 1 module = maximize total
buildable area (Σ sub_plot.buildable_zone.area / parent.area). Roads are
WASTE that consume buildable land twice over (road area + line zabudowy
setback from each road edge). Algorithm must therefore minimise roads.

Pattern selection:
  1. SHALLOW plot (perp_depth ≤ 50 m): single row of sub-plots facing
     DROGA. NO internal roads. Each sub-plot accesses DROGA directly.
  2. DEEP narrow (depth > 50, width ≤ ~80 m): single cul-de-sac road
     perpendicular to DROGA. Sub-plots flank both sides.
  3. DEEP wide (depth > 50, width > ~80 m): multiple parallel cul-de-sacs
     spaced across DROGA edge.

For each pattern, compute total buildable_zone and pick the layout with
the highest figure. Roads only added when geometrically required for
sub-plot road access (= not in row 1 facing DROGA).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from core.buildable_zone import BuildableZoneBuilder, BuildableZoneInfeasible
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


SHALLOW_THRESHOLD = 50.0
NARROW_THRESHOLD = 80.0


# ─────────────────────────────────────────────────────────────────────────────
# Sub-plot construction with boundary inference
# ─────────────────────────────────────────────────────────────────────────────

def _infer_sub_plot_boundaries(
    sub_polygon: Polygon,
    parent: Plot,
    roads: List[Polygon],
    *,
    tolerance: float = 0.5,
) -> List[PlotBoundary]:
    """For each edge of sub_polygon, classify by overlap with parent edges
    and roads."""
    coords = list(sub_polygon.exterior.coords)
    edges = list(zip(coords, coords[1:]))
    out: List[PlotBoundary] = []
    for i, (a, b) in enumerate(edges):
        edge = LineString([a, b])
        if edge.length < 0.01:
            continue
        # Overlap with internal roads → DROGA
        road_overlap = 0.0
        for r in roads:
            try:
                ovl = edge.intersection(r.boundary)
                if hasattr(ovl, "length"):
                    road_overlap += ovl.length
                elif hasattr(ovl, "geoms"):
                    road_overlap += sum(getattr(g, "length", 0.0) for g in ovl.geoms)
            except Exception:
                pass
        # Overlap with parent's DROGA boundaries
        droga_overlap = 0.0
        droga_boundary_type = None
        for pb in parent.boundaries:
            try:
                ovl = edge.intersection(pb.geometry)
                length = ovl.length if hasattr(ovl, "length") else (
                    sum(getattr(g, "length", 0.0) for g in getattr(ovl, "geoms", []))
                )
            except Exception:
                length = 0.0
            if length < tolerance:
                continue
            if pb.boundary_type == BoundaryType.DROGA:
                droga_overlap += length
            elif droga_boundary_type is None:
                droga_boundary_type = pb.boundary_type
        # Decide
        if road_overlap > tolerance or droga_overlap > tolerance:
            btype = BoundaryType.DROGA
        elif droga_boundary_type is not None:
            btype = droga_boundary_type
        else:
            btype = BoundaryType.SASIAD_NIEZABUDOWANY
        out.append(PlotBoundary(geometry=edge, boundary_type=btype, segment_index=i))
    return out


def _build_sub_plot(
    polygon: Polygon, parent: Plot, roads: List[Polygon],
) -> Tuple[Polygon, Optional[Polygon]]:
    """Compute (polygon, buildable_zone) for a sub-plot."""
    boundaries = _infer_sub_plot_boundaries(polygon, parent, roads)
    sub = Plot(
        number="sub", geometry=polygon, boundaries=boundaries,
        mpzp=parent.mpzp, housing_type=parent.housing_type,
    )
    try:
        zone = BuildableZoneBuilder().compute(sub)
    except BuildableZoneInfeasible:
        zone = None
    return polygon, zone


# ─────────────────────────────────────────────────────────────────────────────
# Pattern A — Single row, no roads (shallow plots)
# ─────────────────────────────────────────────────────────────────────────────

def _pattern_single_row(plot: Plot) -> Tuple[List[Polygon], List[Polygon]]:
    """Tile plot with a single row of sub-plots facing DROGA. No roads."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny

    min_front = plot.mpzp.min_front_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    cols = max(1, int(parent_w // min_front))
    cell_w = parent_w / cols
    if cell_w * parent_d > max_area * 1.5:
        # Very deep plot — pattern not suitable
        return [], []
    sub_polys = [
        box(minx + c * cell_w, miny, minx + (c + 1) * cell_w, maxy).intersection(plot.geometry)
        for c in range(cols)
    ]
    sub_polys = [p for p in sub_polys if isinstance(p, Polygon) and p.area > 1.0]
    return sub_polys, []


# ─────────────────────────────────────────────────────────────────────────────
# Pattern B — Single cul-de-sac perpendicular to DROGA
# ─────────────────────────────────────────────────────────────────────────────

def _pattern_single_culdesac(plot: Plot) -> Tuple[List[Polygon], List[Polygon]]:
    """Single cul-de-sac road perpendicular to DROGA midpoint, sub-plots
    on both sides in rows."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny

    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    droga = plot.road_boundary()
    if droga is not None:
        coords = list(droga.geometry.coords)
        cx = (coords[0][0] + coords[-1][0]) / 2
    else:
        cx = (minx + maxx) / 2

    road_xmin = cx - road_w / 2
    road_xmax = cx + road_w / 2
    left_w = road_xmin - minx
    right_w = maxx - road_xmax

    if left_w < min_front or right_w < min_front:
        return [], []

    # Pick row count to keep each sub-plot area ≤ max_area
    target_strip_w = max(left_w, right_w)
    target_row_d = max(min_front, max_area / target_strip_w)
    n_rows = max(1, round(parent_d / target_row_d))
    row_d = parent_d / n_rows

    # Road extends from DROGA up to last row
    if n_rows == 1:
        road_ymax = miny + min(road_w, row_d)
    else:
        road_ymax = miny + (n_rows - 1) * row_d + min(road_w, row_d / 2)

    road = box(road_xmin, miny, road_xmax, road_ymax).intersection(plot.geometry)
    if not isinstance(road, Polygon) or road.is_empty:
        return [], []

    sub_polys = []
    for r in range(n_rows):
        ry0 = miny + r * row_d
        ry1 = ry0 + row_d
        for x_range in [(minx, road_xmin), (road_xmax, maxx)]:
            cell = box(x_range[0], ry0, x_range[1], ry1).intersection(plot.geometry)
            if isinstance(cell, Polygon) and cell.area > 1.0:
                sub_polys.append(cell)

    return sub_polys, [road]


# ─────────────────────────────────────────────────────────────────────────────
# Pattern C — Multiple parallel cul-de-sacs (wide deep plots)
# ─────────────────────────────────────────────────────────────────────────────

def _pattern_multi_culdesac(
    plot: Plot, n_culdesacs: int,
) -> Tuple[List[Polygon], List[Polygon]]:
    """N parallel cul-de-sacs. Plot divided into N bays; each bay has its
    own cul-de-sac with sub-plots flanking on both sides."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny

    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    bay_w = parent_w / n_culdesacs
    strip_w = (bay_w - road_w) / 2
    if strip_w < min_front:
        return [], []

    # row count matches single cul-de-sac math
    target_row_d = max(min_front, max_area / strip_w)
    n_rows = max(1, round(parent_d / target_row_d))
    row_d = parent_d / n_rows
    if n_rows == 1:
        road_ymax_offset = min(road_w, row_d)
    else:
        road_ymax_offset = (n_rows - 1) * row_d + min(road_w, row_d / 2)
    road_ymax_abs = miny + road_ymax_offset

    sub_polys: List[Polygon] = []
    roads: List[Polygon] = []
    for cds_i in range(n_culdesacs):
        bay_xmin = minx + cds_i * bay_w
        bay_xmax = minx + (cds_i + 1) * bay_w
        cx = (bay_xmin + bay_xmax) / 2
        road_xmin = cx - road_w / 2
        road_xmax = cx + road_w / 2

        road = box(road_xmin, miny, road_xmax, road_ymax_abs).intersection(plot.geometry)
        if isinstance(road, Polygon) and not road.is_empty:
            roads.append(road)

        for r in range(n_rows):
            ry0 = miny + r * row_d
            ry1 = ry0 + row_d
            for x_range in [(bay_xmin, road_xmin), (road_xmax, bay_xmax)]:
                cell = box(x_range[0], ry0, x_range[1], ry1).intersection(plot.geometry)
                if isinstance(cell, Polygon) and cell.area > 1.0:
                    sub_polys.append(cell)

    return sub_polys, roads


# ─────────────────────────────────────────────────────────────────────────────
# Pattern selector — picks the layout with maximum total buildable area
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LayoutResult:
    name: str
    sub_polys: List[Polygon] = field(default_factory=list)
    roads: List[Polygon] = field(default_factory=list)
    sub_plots: List[Tuple[Polygon, Optional[Polygon]]] = field(default_factory=list)
    total_buildable: float = 0.0
    total_sub_area: float = 0.0
    total_road_area: float = 0.0

    @property
    def buildable_pct(self) -> float:
        return self.total_buildable / self.total_sub_area * 100 if self.total_sub_area else 0


def _evaluate_layout(
    name: str, plot: Plot, sub_polys: List[Polygon], roads: List[Polygon],
) -> LayoutResult:
    """Build sub-plots and compute total buildable area."""
    out = LayoutResult(name=name)
    out.roads = roads
    out.sub_polys = sub_polys
    out.total_road_area = sum(r.area for r in roads)
    for poly in sub_polys:
        _, zone = _build_sub_plot(poly, plot, roads)
        out.sub_plots.append((poly, zone))
        out.total_sub_area += poly.area
        if zone is not None and not zone.is_empty:
            out.total_buildable += zone.area
    return out


def select_best_layout(plot: Plot) -> LayoutResult:
    """Try all viable patterns, return the one with max total buildable area."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny

    candidates: List[LayoutResult] = []

    # Pattern A — single row (only viable for shallow plots)
    if parent_d <= SHALLOW_THRESHOLD * 1.2:
        sub_polys, roads = _pattern_single_row(plot)
        if sub_polys:
            candidates.append(_evaluate_layout("single_row_no_roads", plot, sub_polys, roads))

    # Pattern B — single cul-de-sac
    sub_polys, roads = _pattern_single_culdesac(plot)
    if sub_polys:
        candidates.append(_evaluate_layout("single_culdesac", plot, sub_polys, roads))

    # Pattern C — 2 / 3 / 4 cul-de-sacs (try a few counts)
    for n in (2, 3, 4):
        sub_polys, roads = _pattern_multi_culdesac(plot, n)
        if sub_polys:
            candidates.append(_evaluate_layout(f"culdesacs_{n}", plot, sub_polys, roads))

    if not candidates:
        return LayoutResult(name="none")

    # Pick layout with maximum total buildable area
    candidates.sort(key=lambda r: -r.total_buildable)
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Test cases & rendering
# ─────────────────────────────────────────────────────────────────────────────

def _make_plot(label, points, droga_idx=0):
    poly = Polygon(points)
    coords = list(points) + [points[0]]
    boundaries = [
        PlotBoundary(
            geometry=LineString([coords[i], coords[i + 1]]),
            boundary_type=BoundaryType.DROGA if i == droga_idx else BoundaryType.SASIAD_NIEZABUDOWANY,
            segment_index=i,
        )
        for i in range(len(points))
    ]
    plot = Plot(
        number=label, geometry=poly, boundaries=boundaries,
        mpzp=MPZPParameters(), housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


CASES = [
    ("Shallow 108×40", [(0, 0), (108, 0), (108, 40), (0, 40)]),
    ("Square 60×80", [(0, 0), (60, 0), (60, 80), (0, 80)]),
    ("Wide deep 230×211", [(0, 0), (230, 0), (230, 211), (0, 211)]),
    ("Slanted 200×68", [(0, 22), (200, 0), (200, 68), (75, 68), (75, 42), (0, 55)]),
]


def render(ax, plot: Plot, result: LayoutResult, title: str):
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=1.0)

    # Highlight DROGA edge
    droga = plot.road_boundary()
    if droga is not None:
        dx, dy = droga.geometry.xy
        ax.plot(dx, dy, color="#e74c3c", linewidth=4, zorder=2)

    palette = ["#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
               "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7"]
    for i, (poly, zone) in enumerate(result.sub_plots):
        sx, sy = poly.exterior.xy
        c = palette[i % len(palette)]
        ax.fill(sx, sy, color=c, alpha=0.6, edgecolor="black", linewidth=0.6)
        if zone is not None and not zone.is_empty:
            try:
                zx, zy = zone.exterior.xy
                ax.fill(zx, zy, color="#27ae60", alpha=0.35, hatch="//",
                        edgecolor="#27ae60", linewidth=0.5)
            except Exception:
                pass
        cx, cy = poly.centroid.x, poly.centroid.y
        z_area = zone.area if zone else 0
        ax.annotate(
            f"S{i+1}\n{poly.area:.0f}m²\nbuild {z_area:.0f}",
            xy=(cx, cy), fontsize=6, ha="center", va="center",
        )

    for r in result.roads:
        try:
            rx, ry = r.exterior.xy
            ax.fill(rx, ry, color="#3a3a3a", alpha=0.85)
        except Exception:
            pass

    cov_pct = (result.total_sub_area + result.total_road_area) / plot.area * 100
    build_pct = result.total_buildable / plot.area * 100
    ax.set_title(
        f"{title}\nLayout: {result.name}, {len(result.sub_plots)} sub-plots\n"
        f"BUILDABLE: {result.total_buildable:.0f} m² = {build_pct:.1f}% of plot   "
        f"road: {result.total_road_area:.0f} m²   coverage: {cov_pct:.0f}%",
        fontsize=9,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def main():
    fig, axes = plt.subplots(2, 2, figsize=(20, 14))
    for ax, (label, points) in zip(axes.flat, CASES):
        plot = _make_plot(label, points)
        result = select_best_layout(plot)
        render(ax, plot, result, label)
        print(f"\n=== {label} ===")
        print(f"  parent area:        {plot.area:.0f} m²")
        print(f"  selected layout:    {result.name}")
        print(f"  sub-plots:          {len(result.sub_plots)}")
        print(f"  total buildable:    {result.total_buildable:.0f} m² "
              f"({result.total_buildable / plot.area * 100:.1f}% of parent)")
        print(f"  total roads:        {result.total_road_area:.0f} m²")

    fig.suptitle(
        "Stage 1 Mode B — buildable-area-maximizing subdivision (REWRITE #2)",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = OUT_DIR / "stage1_buildable_max.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
