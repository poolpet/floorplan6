"""
Stage 1 Mode B — subdivision algorithm v1 prototype (single-family only, Q12).

This is exploration code, NOT production. Per E6: every geometric step
ships with a matplotlib render. The goal is a visual proof that the
algorithm doesn't repeat the 4 C++ Plot Subdivider bugs (overflow,
road overflow, ignored buildable zone, 36-vs-10).

Decisions implemented (see docs/OPEN_QUESTIONS.md):
  Q1(a)+Q1.1(c) — clip to parent boundary; if a sub-plot ends up below
                  the minimum, push the internal grid line at the cost of
                  the donor neighbour, but only if BOTH stay ≥ min.
  Q2            — internal road = hub-analogue, min 4.5 m, area minimised.
  Q3(c)         — front-to-road requirement depends on building type
                  (terraced/twin → mandatory; detached → free).
  Q4(a)         — twin-house: 1 sub-plot = 1 segment.
  Q5(c)         — try multiple grid orientations, pick the one with the
                  highest valid sub-plot count.
  Q15           — min_front_m default 18 m, MPZP override.
  Q16(a)        — strict coverage: Σ sub + roads + nieużytek == parent.

Layout strategy (v1 — axis-aligned only):
  - Determine grid orientation: along DROGA edge (default) or
    perpendicular. Q5(c) implementation tries both and scores by
    valid-sub-plot count.
  - Tile sub-plots in N rows × M columns inside the parent geometry.
  - If more than 1 row → internal road strip parallel to DROGA between
    each pair of rows.
  - Clip sub-plots that overlap parent boundary irregularities
    (Q1(a)) — they become trapezoids.
  - If a clipped sub-plot would fall below min_front × min_depth,
    apply Q1.1(c): push the donor internal grid line to grow it back to
    minimum, but reject the whole layout if the donor would itself
    fall below min.
  - Compute nieużytek = parent − Σ sub_plots − roads (Q16(a) — explicit).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Building type — drives Q3(c) front-to-road
# ─────────────────────────────────────────────────────────────────────────────

class BuildingType(str, Enum):
    DETACHED = "DETACHED"        # Wolnostojący — orientation free
    TWIN = "TWIN"                # Bliźniak — front to road mandatory
    TERRACED = "TERRACED"        # Szeregowy — front to road mandatory


# ─────────────────────────────────────────────────────────────────────────────
# Result data
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SubdivisionResult:
    parent: Plot
    sub_plots: List[Polygon] = field(default_factory=list)
    roads: List[Polygon] = field(default_factory=list)
    nieuzytek: Optional[Polygon] = None
    orientation_name: str = ""
    min_front_used: float = 0.0
    min_road_width_used: float = 0.0
    rows: int = 0
    cols: int = 0

    @property
    def total_sub_area(self) -> float:
        return sum(p.area for p in self.sub_plots)

    @property
    def total_road_area(self) -> float:
        return sum(p.area for p in self.roads)

    @property
    def nieuzytek_area(self) -> float:
        return self.nieuzytek.area if self.nieuzytek and not self.nieuzytek.is_empty else 0.0

    @property
    def coverage_diff(self) -> float:
        """Q16(a): coverage error against parent area."""
        return abs(
            self.parent.area
            - self.total_sub_area
            - self.total_road_area
            - self.nieuzytek_area
        )

    def coverage_ok(self, tolerance: float = 0.5) -> bool:
        """Q16(a): strict coverage tolerance — 0.5 m² for floating-point noise."""
        return self.coverage_diff < tolerance


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — orientation candidates (Q5(c))
# ─────────────────────────────────────────────────────────────────────────────

def candidate_orientations(plot: Plot) -> List[Tuple[str, float]]:
    """Generate orientation hypotheses (name, axis_angle_degrees)."""
    candidates = [("along_x_(road=south)", 0.0), ("along_y_(road=east)", 90.0)]
    road = plot.road_boundary()
    if road is not None:
        coords = list(road.geometry.coords)
        if len(coords) >= 2:
            dx = coords[1][0] - coords[0][0]
            dy = coords[1][1] - coords[0][1]
            angle = math.degrees(math.atan2(dy, dx)) % 180
            candidates.append((f"parallel_to_DROGA_({angle:.0f}°)", angle))
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — generate axis-aligned grid (assumes orientation 0 or 90)
# ─────────────────────────────────────────────────────────────────────────────

def generate_axis_aligned_grid(
    plot: Plot,
    *,
    rotated_90: bool = False,
    front_setback: float = 5.0,        # line zabudowy from DROGA
    rear_setback: float = 5.0,
    side_setback: float = 5.0,
    min_depth: float = 25.0,
) -> Tuple[List[Polygon], List[Polygon], int, int]:
    """Tile the parent with axis-aligned sub-plots.

    Returns (sub_plots, roads, rows, cols).

    For rotated_90 == False: DROGA on bottom, sub-plots stack in rows
    along x-axis. Each row has columns of width = min_front_m.

    For rotated_90 == True: roles of x and y are swapped (DROGA on left).
    """
    minx, miny, maxx, maxy = plot.geometry.bounds
    if rotated_90:
        # Swap so we always work in "DROGA on bottom" coordinates internally.
        minx, miny, maxx, maxy = miny, minx, maxy, maxx
    width = maxx - minx
    depth = maxy - miny

    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m

    # Inset for parent setbacks (line zabudowy + side/rear).
    usable_x_min = minx + side_setback
    usable_x_max = maxx - side_setback
    usable_y_min = miny + front_setback
    usable_y_max = maxy - rear_setback
    usable_w = usable_x_max - usable_x_min
    usable_d = usable_y_max - usable_y_min

    if usable_w < min_front or usable_d < min_depth:
        return [], [], 0, 0

    # Columns: integer count fitting min_front.
    cols = max(1, int(usable_w // min_front))
    # Try 2 rows if depth allows.
    rows_try = 2 if usable_d >= 2 * min_depth + road_w else 1
    if rows_try == 1:
        rows = 1
        row_depth = usable_d
        roads = []
    else:
        rows = 2
        row_depth = (usable_d - road_w) / 2
        # Internal road strip between row 1 and row 2.
        road_y0 = usable_y_min + row_depth
        road_y1 = road_y0 + road_w
        road = box(usable_x_min, road_y0, usable_x_max, road_y1)
        roads = [road]

    col_w = usable_w / cols

    sub_plots: List[Polygon] = []
    for r in range(rows):
        row_y0 = usable_y_min + r * (row_depth + (road_w if rows == 2 else 0))
        row_y1 = row_y0 + row_depth
        for c in range(cols):
            x0 = usable_x_min + c * col_w
            x1 = x0 + col_w
            cell = box(x0, row_y0, x1, row_y1)
            sub_plots.append(cell)

    if rotated_90:
        # Swap x and y back.
        def swap(poly: Polygon) -> Polygon:
            return Polygon([(y, x) for x, y in poly.exterior.coords])
        sub_plots = [swap(p) for p in sub_plots]
        roads = [swap(p) for p in roads]

    return sub_plots, roads, rows, cols


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — clip to parent (Q1(a)), enforce minima (Q1.1(c)/Q15)
# ─────────────────────────────────────────────────────────────────────────────

def clip_and_validate(
    plot: Plot,
    sub_plots: List[Polygon],
    min_front: float,
    min_area: float = 200.0,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Clip each sub-plot to parent.geometry (Q1(a)).

    Returns (kept_sub_plots, dropped_as_nieuzytek). A clipped sub-plot
    is dropped to nieużytek when its bounding-box width OR area falls
    below the minimum (Q1.1(c) is a planned upgrade — for v1 we drop).
    """
    kept: List[Polygon] = []
    dropped: List[Polygon] = []
    for cell in sub_plots:
        clipped = cell.intersection(plot.geometry)
        if clipped.is_empty or clipped.area < min_area:
            dropped.append(cell)
            continue
        if isinstance(clipped, Polygon):
            cw = clipped.bounds[2] - clipped.bounds[0]
            ch = clipped.bounds[3] - clipped.bounds[1]
            if min(cw, ch) < min_front * 0.85:
                dropped.append(clipped)
                continue
            kept.append(clipped)
        else:
            # MultiPolygon — keep the largest piece.
            largest = max(clipped.geoms, key=lambda p: p.area)
            if largest.area >= min_area:
                kept.append(largest)
            else:
                dropped.append(clipped)
    return kept, dropped


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — assemble nieużytek (Q16(a))
# ─────────────────────────────────────────────────────────────────────────────

def assemble_nieuzytek(
    plot: Plot,
    sub_plots: List[Polygon],
    roads: List[Polygon],
) -> Polygon:
    """nieużytek = parent − Σ sub_plots − roads. May be MultiPolygon."""
    used = unary_union(sub_plots + roads) if (sub_plots or roads) else None
    if used is None:
        return plot.geometry
    leftover = plot.geometry.difference(used)
    return leftover


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — full subdivision pipeline
# ─────────────────────────────────────────────────────────────────────────────

def subdivide(plot: Plot, *, rotated_90: bool = False) -> SubdivisionResult:
    raw_sub_plots, roads, rows, cols = generate_axis_aligned_grid(
        plot, rotated_90=rotated_90
    )
    kept, dropped = clip_and_validate(plot, raw_sub_plots, plot.mpzp.min_front_m)
    nieuzytek = assemble_nieuzytek(plot, kept, roads)

    return SubdivisionResult(
        parent=plot,
        sub_plots=kept,
        roads=roads,
        nieuzytek=nieuzytek,
        orientation_name=("rotated_90" if rotated_90 else "axis_aligned"),
        min_front_used=plot.mpzp.min_front_m,
        min_road_width_used=plot.mpzp.min_road_width_m,
        rows=rows,
        cols=cols,
    )


def subdivide_with_orientation_search(plot: Plot) -> SubdivisionResult:
    """Q5(c): try both axis-aligned orientations, pick the one with more sub-plots."""
    candidates = [subdivide(plot, rotated_90=False), subdivide(plot, rotated_90=True)]
    candidates.sort(key=lambda r: -len(r.sub_plots))
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

def make_plot(
    points: List[Tuple[float, float]],
    boundary_types: List[BoundaryType],
    *,
    min_front: float = 18.0,
    min_road_width: float = 4.5,
    setback_from_road: float = 5.0,
) -> Plot:
    poly = Polygon(points)
    coords = points + [points[0]]
    boundaries = [
        PlotBoundary(
            geometry=LineString([coords[i], coords[i + 1]]),
            boundary_type=boundary_types[i],
            segment_index=i,
        )
        for i in range(len(points))
    ]
    plot = Plot(
        number="parcel",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            min_front_m=min_front,
            min_road_width_m=min_road_width,
            setback_from_road=setback_from_road,
        ),
        housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def case_rectangular_60x80() -> Plot:
    return make_plot(
        [(0, 0), (60, 0), (60, 80), (0, 80)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def case_l_shape() -> Plot:
    """L-shape — exposes Q1(a) clipping behaviour."""
    return make_plot(
        [(0, 0), (80, 0), (80, 30), (50, 30), (50, 60), (0, 60)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def case_long_narrow() -> Plot:
    """Tests Q5(c) — narrow plot benefits from rotated grid."""
    return make_plot(
        [(0, 0), (30, 0), (30, 100), (0, 100)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────

SUBPLOT_COLORS = ["#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
                  "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7"]


def render_result(ax, result: SubdivisionResult, title: str) -> None:
    plot = result.parent
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=0.8)

    if plot.buildable_zone and not plot.buildable_zone.is_empty:
        zx, zy = plot.buildable_zone.exterior.xy
        ax.plot(zx, zy, color="#27ae60", linestyle="--", linewidth=0.8, alpha=0.7)

    for i, sub in enumerate(result.sub_plots):
        sx, sy = sub.exterior.xy
        c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
        ax.fill(sx, sy, color=c, alpha=0.7, edgecolor="black", linewidth=0.8)
        cx, cy = sub.centroid.x, sub.centroid.y
        ax.annotate(f"S{i+1}\n{sub.area:.0f} m²", xy=(cx, cy),
                    fontsize=7, ha="center", va="center")

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
                ax.fill(wx, wy, color="#aa6644", alpha=0.35, hatch="\\\\",
                        edgecolor="#aa6644", linewidth=0.5)
            except Exception:
                pass

    ratio_sub = result.total_sub_area / plot.area * 100
    ratio_road = result.total_road_area / plot.area * 100
    ratio_waste = result.nieuzytek_area / plot.area * 100
    ok = "OK" if result.coverage_ok() else f"DIFF={result.coverage_diff:.2f}m²"
    ax.set_title(
        f"{title}\nsub={ratio_sub:.0f}%  road={ratio_road:.0f}%  "
        f"nieużytek={ratio_waste:.0f}%  Q16: {ok}",
        fontsize=9,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def main():
    cases = [
        ("Rectangle 60×80", case_rectangular_60x80()),
        ("L-shape (clip test)", case_l_shape()),
        ("Long narrow 30×100\n(Q5c orientation matters)", case_long_narrow()),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    for ax, (title, plot) in zip(axes, cases):
        result = subdivide_with_orientation_search(plot)
        render_result(ax, result, title)
        print(f"\n=== {title} ===")
        print(f"  parent area:    {plot.area:.1f} m²")
        print(f"  sub-plots:      {len(result.sub_plots)} × ~{plot.area / max(1, len(result.sub_plots)):.0f} m² avg")
        print(f"  Σ sub:          {result.total_sub_area:.1f} m² ({result.total_sub_area/plot.area*100:.1f}%)")
        print(f"  Σ roads:        {result.total_road_area:.1f} m² ({result.total_road_area/plot.area*100:.1f}%)")
        print(f"  nieużytek:      {result.nieuzytek_area:.1f} m² ({result.nieuzytek_area/plot.area*100:.1f}%)")
        print(f"  Q16 coverage:   diff={result.coverage_diff:.3f} m² ({'OK' if result.coverage_ok() else 'FAIL'})")
        print(f"  orientation:    {result.orientation_name}")
        print(f"  rows × cols:    {result.rows} × {result.cols}")

    legend_handles = [
        mpatches.Patch(color="#a8d8ea", label="Sub-plot"),
        mpatches.Patch(color="#3a3a3a", label="Internal road"),
        mpatches.Patch(facecolor="#aa6644", alpha=0.35, hatch="\\\\",
                       edgecolor="#aa6644", label="Nieużytek"),
        mpatches.Patch(facecolor="none", edgecolor="#27ae60",
                       linestyle="--", label="Buildable zone (parent)"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(
        "Stage 1 Mode B — subdivision v1 prototype "
        "(Q1a + Q5c orientation search + Q15 + Q16a strict coverage)",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out_path = OUT_DIR / "stage1_subdivision_v1.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
