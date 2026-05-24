"""
Stage 1 Mode B — REWRITE #4: katana algorithm + polyskel road skeleton.

Per B1 we keep failing reimplementation, so use battle-tested algorithms
from external sources:

  KATANA (snorfalorpagus, BSD-2): recursive shapely bisection along the
  longest dimension of the bbox. Handles ARBITRARY polygons (regular,
  L-shape, slanted, irregular). 25 lines. This is the "subdivideShapes"
  algorithm CityEngine uses.

  ROAD SKELETON: ladybug-geometry-polyskel for straight-skeleton based
  road network — generates the natural tree-shaped medial axis of the
  polygon, which matches the user's "single entry from DROGA, branches
  as needed" architectural model.

Pipeline:
  1. Subdivide plot polygon into cells via katana (target avg = max_area).
  2. For each cell, compute buildable_zone via existing setbacks logic.
  3. (Optional, v2) Add road skeleton from DROGA edge if some cells lack
     direct DROGA access.

Goal of this prototype: verify katana produces reasonable cells on
IRREGULAR plots — the case where my own implementations have failed
repeatedly.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, MultiPolygon, Polygon, box

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


# ─────────────────────────────────────────────────────────────────────────────
# Katana — Snorfalorpagus 2016 — BSD-2-clause, 25 lines
# https://snorfalorpagus.net/blog/2016/03/13/splitting-large-polygons-for-faster-intersections/
# ─────────────────────────────────────────────────────────────────────────────

def katana(geometry: Polygon, threshold: float, count: int = 0) -> List[Polygon]:
    """Split `geometry` into smaller polygons until max bbox dim ≤ threshold."""
    bounds = geometry.bounds
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    if max(width, height) <= threshold or count == 250:
        return [geometry]
    if height >= width:
        a = box(bounds[0], bounds[1], bounds[2], bounds[1] + height / 2)
        b = box(bounds[0], bounds[1] + height / 2, bounds[2], bounds[3])
    else:
        a = box(bounds[0], bounds[1], bounds[0] + width / 2, bounds[3])
        b = box(bounds[0] + width / 2, bounds[1], bounds[2], bounds[3])
    result = []
    for d in (a, b):
        c = geometry.intersection(d)
        if c.is_empty:
            continue
        if isinstance(c, MultiPolygon):
            pieces = list(c.geoms)
        else:
            pieces = [c]
        for piece in pieces:
            if not isinstance(piece, Polygon) or piece.is_empty:
                continue
            result.extend(katana(piece, threshold, count + 1))
    return result


def katana_to_target_area(geometry: Polygon, target_area: float) -> List[Polygon]:
    """Wrapper: pick threshold from target average area."""
    threshold = math.sqrt(target_area) * 1.4   # roughly: sqrt(area) × √2
    return katana(geometry, threshold)


# ─────────────────────────────────────────────────────────────────────────────
# Buildable zone computation per cell
# ─────────────────────────────────────────────────────────────────────────────

def _classify_cell_boundaries(
    cell: Polygon, parent: Plot, roads: List[Polygon] = (),
) -> List[PlotBoundary]:
    """Classify each cell edge by overlap with parent boundaries / roads."""
    boundaries: List[PlotBoundary] = []
    coords = list(cell.exterior.coords)
    for i, (a, b) in enumerate(zip(coords, coords[1:])):
        edge = LineString([a, b])
        if edge.length < 0.01:
            continue
        # Check overlap with each parent boundary
        best_type = BoundaryType.SASIAD_NIEZABUDOWANY
        best_overlap = 0.0
        for pb in parent.boundaries:
            try:
                ovl = edge.intersection(pb.geometry)
                length = (ovl.length if hasattr(ovl, "length")
                          and not hasattr(ovl, "geoms") else
                          sum(getattr(g, "length", 0.0) for g in getattr(ovl, "geoms", [])))
            except Exception:
                length = 0.0
            if length > best_overlap and length > 0.5:
                best_overlap = length
                best_type = pb.boundary_type
        # Check road overlap
        for r in roads:
            try:
                ovl = edge.intersection(r.boundary)
                length = (ovl.length if hasattr(ovl, "length")
                          and not hasattr(ovl, "geoms") else 0.0)
            except Exception:
                length = 0.0
            if length > 0.5:
                best_type = BoundaryType.DROGA
                break
        boundaries.append(PlotBoundary(geometry=edge, boundary_type=best_type, segment_index=i))
    return boundaries


def compute_buildable(cell: Polygon, parent: Plot, roads: List[Polygon] = ()) -> float:
    """Compute buildable_zone area for a cell, given parent's MPZP setbacks."""
    boundaries = _classify_cell_boundaries(cell, parent, roads)
    sub = Plot(
        number="cell", geometry=cell, boundaries=boundaries,
        mpzp=parent.mpzp, housing_type=parent.housing_type,
    )
    try:
        zone = BuildableZoneBuilder().compute(sub)
        return zone.area if zone and not zone.is_empty else 0.0
    except BuildableZoneInfeasible:
        return 0.0


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
        mpzp=MPZPParameters(min_sub_plot_area_m2=400, max_sub_plot_area_m2=1500),
        housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


CASES = [
    ("Regular 60×80", [(0, 0), (60, 0), (60, 80), (0, 80)]),
    ("Wide 230×211", [(0, 0), (230, 0), (230, 211), (0, 211)]),
    ("Slanted 200×68", [(0, 22), (200, 0), (200, 68), (75, 68), (75, 42), (0, 55)]),
    ("Tall irregular", [(25, 0), (25, 70), (150, 100), (195, 400), (10, 400), (0, 0)]),
]


def render(ax, plot: Plot, cells: List[Polygon], buildables: List[float], title: str):
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=1.0)

    droga = plot.road_boundary()
    if droga is not None:
        dx, dy = droga.geometry.xy
        ax.plot(dx, dy, color="#e74c3c", linewidth=4, zorder=2, label="DROGA")

    palette = ["#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
               "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7"]
    total_buildable = 0.0
    for i, (cell, b) in enumerate(zip(cells, buildables)):
        try:
            sx, sy = cell.exterior.xy
        except Exception:
            continue
        ax.fill(sx, sy, color=palette[i % len(palette)], alpha=0.7,
                edgecolor="black", linewidth=0.6)
        ax.annotate(
            f"S{i+1}\n{cell.area:.0f}m²\nbuild {b:.0f}",
            xy=(cell.centroid.x, cell.centroid.y),
            fontsize=6, ha="center", va="center",
        )
        total_buildable += b

    cell_areas = [c.area for c in cells]
    avg = sum(cell_areas) / max(1, len(cell_areas))
    in_range = sum(1 for a in cell_areas if 400 <= a <= 1500)
    ax.set_title(
        f"{title}\nkatana: {len(cells)} cells, avg {avg:.0f} m², "
        f"{in_range}/{len(cells)} in [400-1500]\n"
        f"buildable {total_buildable:.0f} m² = {total_buildable/plot.area*100:.1f}%",
        fontsize=9,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def main():
    fig, axes = plt.subplots(2, 2, figsize=(20, 14))
    for ax, (label, points) in zip(axes.flat, CASES):
        plot = _make_plot(label, points)
        target_area = (plot.mpzp.min_sub_plot_area_m2 + plot.mpzp.max_sub_plot_area_m2) / 2
        cells = katana_to_target_area(plot.geometry, target_area)
        buildables = [compute_buildable(c, plot) for c in cells]
        render(ax, plot, cells, buildables, label)
        in_range = sum(1 for c in cells if 400 <= c.area <= 1500)
        print(f"\n=== {label} ===")
        print(f"  parent area: {plot.area:.0f} m²")
        print(f"  cells:       {len(cells)} ({in_range} in [400-1500])")
        print(f"  buildable:   {sum(buildables):.0f} m² "
              f"({sum(buildables)/plot.area*100:.1f}%)")

    fig.suptitle(
        "Stage 1 Mode B — katana subdivision (Snorfalorpagus, BSD-2). "
        "No roads yet — just verifying subdivision works on irregular plots.",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = OUT_DIR / "stage1_katana_v1.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
