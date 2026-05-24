"""
Stage 1 Mode B — subdivision v2 prototype (Q12 single-family).

Iteration over v1: sub-plots now tile the ENTIRE parent (minus internal
road). Setbacks (line zabudowy 5 m, side 1.5 m / 3 m, rear 5 m) are
constraints on BUILDING placement WITHIN each sub-plot, not on land
extent. Architecturally correct: each sub-plot extends to the property
line (parent boundary or internal grid cut).

For each sub-plot we compute its OWN buildable zone (using the same
BuildableZoneBuilder we already have) and require it to be non-empty —
otherwise the sub-plot is rejected and the layout falls back per
Q1.1(c) escalation.

Key change vs v1: no parent-level perimeter `nieużytek` strip. The
nieużytek polygon now only contains genuinely unused fragments (e.g. an
L-shape notch corner that doesn't admit a viable sub-plot).

Decisions implemented unchanged: Q1(a), Q3(c), Q4(a), Q5(c), Q15, Q16(a).
Each sub-plot's per-sub-plot buildable zone is rendered too (for visual
proof that it isn't accidentally empty — the C++ Plot Subdivider bug #3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from core.buildable_zone import (
    BuildableZoneBuilder,
    BuildableZoneInfeasible,
)
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
# Building type — Q3(c) front-to-road
# ─────────────────────────────────────────────────────────────────────────────

class BuildingType(str, Enum):
    DETACHED = "DETACHED"
    TWIN = "TWIN"
    TERRACED = "TERRACED"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-plot — wraps a polygon with its inferred boundaries + buildable zone
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SubPlot:
    polygon: Polygon
    boundaries: List[PlotBoundary] = field(default_factory=list)
    buildable_zone: Optional[Polygon] = None
    front_length: float = 0.0           # length of side facing road

    @property
    def area(self) -> float:
        return self.polygon.area

    @property
    def has_buildable_zone(self) -> bool:
        return self.buildable_zone is not None and not self.buildable_zone.is_empty


@dataclass
class SubdivisionResult:
    parent: Plot
    sub_plots: List[SubPlot] = field(default_factory=list)
    roads: List[Polygon] = field(default_factory=list)
    nieuzytek: Optional[Polygon] = None
    orientation_name: str = ""
    rows: int = 0
    cols: int = 0

    @property
    def total_sub_area(self) -> float:
        return sum(s.area for s in self.sub_plots)

    @property
    def total_road_area(self) -> float:
        return sum(p.area for p in self.roads)

    @property
    def nieuzytek_area(self) -> float:
        return self.nieuzytek.area if self.nieuzytek and not self.nieuzytek.is_empty else 0.0

    @property
    def coverage_diff(self) -> float:
        return abs(
            self.parent.area
            - self.total_sub_area
            - self.total_road_area
            - self.nieuzytek_area
        )

    def coverage_ok(self, tol: float = 0.5) -> bool:
        return self.coverage_diff < tol

    @property
    def all_have_buildable_zone(self) -> bool:
        return all(s.has_buildable_zone for s in self.sub_plots)


# ─────────────────────────────────────────────────────────────────────────────
# Boundary inference — given a sub-plot polygon, classify its edges
# ─────────────────────────────────────────────────────────────────────────────

def infer_sub_plot_boundaries(
    sub_polygon: Polygon,
    parent: Plot,
    internal_road_geometries: List[Polygon],
) -> List[PlotBoundary]:
    """For each edge of the sub-plot, decide its boundary type.

    Heuristic:
      - Edge close to the parent's DROGA edge → DROGA (line zabudowy 5 m)
      - Edge close to an internal-road geometry → DROGA
      - Edge close to a parent's SASIAD/WLASNA edge → inherit that type
      - Otherwise (interior cut between two sub-plots) → SASIAD_NIEZABUDOWANY
        (under Q4(a) twin-house: shared wall, but inter-sub-plot boundaries
        for detached/twin developments are treated as undeveloped neighbour)
    """
    coords = list(sub_polygon.exterior.coords)
    edges = list(zip(coords, coords[1:]))
    boundaries: List[PlotBoundary] = []

    for i, (a, b) in enumerate(edges):
        edge_line = LineString([a, b])
        if edge_line.length < 0.01:
            continue

        btype = _closest_boundary_type(edge_line, parent, internal_road_geometries)
        boundaries.append(PlotBoundary(
            geometry=edge_line,
            boundary_type=btype,
            segment_index=i,
        ))
    return boundaries


def _closest_boundary_type(
    edge: LineString,
    parent: Plot,
    internal_road_geometries: List[Polygon],
    tolerance: float = 0.5,
) -> BoundaryType:
    midpoint = edge.interpolate(0.5, normalized=True)

    # Internal road touches → DROGA
    for road in internal_road_geometries:
        if midpoint.distance(road.boundary) < tolerance:
            return BoundaryType.DROGA

    # Parent boundary closest match
    closest_parent_b: Optional[PlotBoundary] = None
    closest_distance = float("inf")
    for b in parent.boundaries:
        d = midpoint.distance(b.geometry)
        if d < closest_distance:
            closest_distance = d
            closest_parent_b = b

    if closest_parent_b is not None and closest_distance < tolerance:
        return closest_parent_b.boundary_type

    # Interior cut between sub-plots
    return BoundaryType.SASIAD_NIEZABUDOWANY


# ─────────────────────────────────────────────────────────────────────────────
# Grid generation — sub-plots tile the entire parent
# ─────────────────────────────────────────────────────────────────────────────

def generate_grid(
    plot: Plot,
    *,
    rotated_90: bool = False,
    min_row_depth: float = 25.0,
) -> Tuple[List[Polygon], List[Polygon], int, int]:
    """Tile parent's bounding box. Sub-plots will be clipped to parent later."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    if rotated_90:
        minx, miny, maxx, maxy = miny, minx, maxy, maxx
    width = maxx - minx
    depth = maxy - miny

    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m

    # Columns at full width; pick count fitting the min_front.
    cols = max(1, int(width // min_front))
    # 2 rows if depth allows two rows of min_row_depth + road, else 1.
    if depth >= 2 * min_row_depth + road_w:
        rows = 2
        row_d = (depth - road_w) / 2
    else:
        rows = 1
        row_d = depth

    col_w = width / cols
    sub_polys: List[Polygon] = []
    roads: List[Polygon] = []

    for r in range(rows):
        if rows == 2:
            y0 = miny + r * (row_d + road_w)
        else:
            y0 = miny
        y1 = y0 + row_d
        for c in range(cols):
            x0 = minx + c * col_w
            x1 = x0 + col_w
            sub_polys.append(box(x0, y0, x1, y1))

    if rows == 2:
        road_y0 = miny + row_d
        roads.append(box(minx, road_y0, maxx, road_y0 + road_w))

    if rotated_90:
        def swap(p: Polygon) -> Polygon:
            return Polygon([(y, x) for x, y in p.exterior.coords])
        sub_polys = [swap(p) for p in sub_polys]
        roads = [swap(p) for p in roads]

    return sub_polys, roads, rows, cols


# ─────────────────────────────────────────────────────────────────────────────
# Clip sub-plots to parent + sanity-check buildable zone
# ─────────────────────────────────────────────────────────────────────────────

def clip_and_evaluate(
    plot: Plot,
    raw_polygons: List[Polygon],
    roads: List[Polygon],
    *,
    min_area: float = 200.0,
    min_dim: float = 14.0,        # 18 × 0.78 — accept slightly clipped trapezoids
) -> Tuple[List[SubPlot], List[Polygon]]:
    """Clip each sub-plot to parent.geometry, infer boundaries, compute zone.

    Returns (kept_sub_plots, dropped_polygons_for_nieuzytek).
    """
    builder = BuildableZoneBuilder()
    kept: List[SubPlot] = []
    dropped: List[Polygon] = []

    for raw in raw_polygons:
        clipped = raw.intersection(plot.geometry)
        if clipped.is_empty:
            continue
        if not isinstance(clipped, Polygon):
            # MultiPolygon — keep the largest piece, drop the rest.
            polys = list(clipped.geoms)
            largest = max(polys, key=lambda p: p.area)
            for p in polys:
                if p is not largest:
                    dropped.append(p)
            clipped = largest

        if clipped.area < min_area:
            dropped.append(clipped)
            continue

        cw = clipped.bounds[2] - clipped.bounds[0]
        ch = clipped.bounds[3] - clipped.bounds[1]
        if min(cw, ch) < min_dim:
            dropped.append(clipped)
            continue

        boundaries = infer_sub_plot_boundaries(clipped, plot, roads)

        # Sanity check: per-sub-plot buildable zone must be non-empty.
        sub_plot_obj = Plot(
            number="sub",
            geometry=clipped,
            boundaries=boundaries,
            mpzp=plot.mpzp,
            housing_type=plot.housing_type,
        )
        try:
            zone = builder.compute(sub_plot_obj)
        except BuildableZoneInfeasible:
            dropped.append(clipped)
            continue

        kept.append(SubPlot(
            polygon=clipped,
            boundaries=boundaries,
            buildable_zone=zone,
            front_length=_front_length(boundaries),
        ))

    return kept, dropped


def _front_length(boundaries: List[PlotBoundary]) -> float:
    return sum(
        b.geometry.length for b in boundaries
        if b.boundary_type == BoundaryType.DROGA
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def assemble_nieuzytek(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
) -> Polygon:
    occupied = unary_union([s.polygon for s in sub_plots] + roads) \
        if (sub_plots or roads) else None
    if occupied is None:
        return plot.geometry
    return plot.geometry.difference(occupied)


def _clip_roads_to_parent(plot: Plot, roads: List[Polygon]) -> List[Polygon]:
    """Clip every road polygon to the parent — fixes Q16 mis-counting in L-shapes."""
    clipped: List[Polygon] = []
    for r in roads:
        c = r.intersection(plot.geometry)
        if c.is_empty:
            continue
        if isinstance(c, Polygon):
            clipped.append(c)
        else:
            for piece in c.geoms:
                if isinstance(piece, Polygon) and not piece.is_empty:
                    clipped.append(piece)
    return clipped


def subdivide(plot: Plot, *, rotated_90: bool = False) -> SubdivisionResult:
    raw_polys, raw_roads, rows, cols = generate_grid(plot, rotated_90=rotated_90)
    roads = _clip_roads_to_parent(plot, raw_roads)
    kept, dropped = clip_and_evaluate(plot, raw_polys, roads)
    nieuzytek = assemble_nieuzytek(plot, kept, roads)
    return SubdivisionResult(
        parent=plot,
        sub_plots=kept,
        roads=roads,
        nieuzytek=nieuzytek,
        orientation_name=("rotated_90" if rotated_90 else "axis_aligned"),
        rows=rows,
        cols=cols,
    )


def _layout_score(r: SubdivisionResult) -> Tuple[int, int]:
    """Higher score wins.

    Primary: number of sub-plots with road access (front > 0).
    Tiebreak: total sub-plot count.

    Layouts where ANY sub-plot lacks road access are penalised heavily —
    those sub-plots would be inaccessible.
    """
    with_access = sum(1 for s in r.sub_plots if s.front_length > 0)
    if with_access != len(r.sub_plots):
        return (-1, with_access)
    return (with_access, len(r.sub_plots))


def subdivide_with_orientation_search(plot: Plot) -> SubdivisionResult:
    candidates = [subdivide(plot, rotated_90=False), subdivide(plot, rotated_90=True)]
    candidates.sort(key=_layout_score, reverse=True)
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Test cases (same as v1)
# ─────────────────────────────────────────────────────────────────────────────

def make_plot(
    points: List[Tuple[float, float]],
    boundary_types: List[BoundaryType],
    *,
    min_front: float = 18.0,
    min_road_width: float = 4.5,
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
    ax.plot(px, py, color="black", linewidth=1.0)

    for i, s in enumerate(result.sub_plots):
        sx, sy = s.polygon.exterior.xy
        c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
        ax.fill(sx, sy, color=c, alpha=0.7, edgecolor="black", linewidth=0.8)

        if s.has_buildable_zone:
            try:
                zx, zy = s.buildable_zone.exterior.xy
                ax.fill(zx, zy, color="#27ae60", alpha=0.18,
                        edgecolor="#27ae60", linewidth=0.5, linestyle="--")
            except Exception:
                pass

        cx, cy = s.polygon.centroid.x, s.polygon.centroid.y
        bz_area = s.buildable_zone.area if s.has_buildable_zone else 0
        ax.annotate(
            f"S{i+1}\n{s.area:.0f} m²\n(zone {bz_area:.0f})",
            xy=(cx, cy), fontsize=6.5, ha="center", va="center",
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

    ratio_sub = result.total_sub_area / plot.area * 100
    ratio_road = result.total_road_area / plot.area * 100
    ratio_waste = result.nieuzytek_area / plot.area * 100
    ok = "OK" if result.coverage_ok() else f"DIFF={result.coverage_diff:.2f}m²"
    bz_ok = "✓ all" if result.all_have_buildable_zone else "MISSING"
    ax.set_title(
        f"{title}\nsub={ratio_sub:.0f}% road={ratio_road:.0f}% nieużytek={ratio_waste:.0f}%\n"
        f"Q16: {ok}   per-sub-plot zone: {bz_ok}",
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
        print(f"  parent area: {plot.area:.1f} m²")
        print(f"  sub-plots:   {len(result.sub_plots)}")
        for i, s in enumerate(result.sub_plots):
            bz = s.buildable_zone.area if s.has_buildable_zone else 0
            print(f"    S{i+1}: area={s.area:.0f} m², zone={bz:.0f} m², front={s.front_length:.1f} m")
        print(f"  roads: {result.total_road_area:.1f} m² ({result.total_road_area/plot.area*100:.1f}%)")
        print(f"  nieużytek: {result.nieuzytek_area:.1f} m² ({result.nieuzytek_area/plot.area*100:.1f}%)")
        print(f"  Q16 coverage: diff={result.coverage_diff:.3f} m² ({'OK' if result.coverage_ok() else 'FAIL'})")
        print(f"  all sub-plots have buildable zone: {result.all_have_buildable_zone}")

    legend_handles = [
        mpatches.Patch(color="#a8d8ea", label="Sub-plot land"),
        mpatches.Patch(facecolor="#27ae60", alpha=0.18,
                       edgecolor="#27ae60", linestyle="--",
                       label="Per-sub-plot buildable zone"),
        mpatches.Patch(color="#3a3a3a", label="Internal road"),
        mpatches.Patch(facecolor="#aa6644", alpha=0.45, hatch="\\\\",
                       edgecolor="#aa6644", label="Nieużytek"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(
        "Stage 1 Mode B — subdivision v2 (sub-plots tile entire parent; "
        "setbacks are per-sub-plot building constraints, not land cuts)",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out_path = OUT_DIR / "stage1_subdivision_v2.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
