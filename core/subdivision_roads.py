"""
Stage 1 subdivision road-tree layout.

Production rule: internal roads are a tree rooted in the public DROGA edge.
Branches stop before non-road parcel boundaries and exist only to serve rows
of detached single-family sub-plots.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from core.plot_model import Plot, PlotBoundary


@dataclass(frozen=True)
class RoadTreeSettings:
    """Tunable road-tree strategy for Stage 1 variant generation."""
    name: str = "road_tree_balanced"
    branch_row_group: int = 2
    trunk_position: float = 0.5
    edge_clearance_front_factor: float = 0.5
    shallow_depth_factor: float = 1.75

    # Optimal-ratio mode (port z FP4 CPP PlotSubdivider.cpp linia 192):
    # target_front = max(min_front, sqrt(target_area × target_ratio))
    # daje proporcje front/depth ≈ target_ratio dla optymalnego budynku.
    # 0.67 dla wolnostojących, 0.5 dla szeregowych/bliźniaczych.
    use_optimal_ratio: bool = False
    target_ratio: float = 0.67  # front × depth ratio (wolnostojący default)


def rotate_plot_to_droga_horizontal(
    plot: Plot,
) -> Tuple[Plot, float, Tuple[float, float]]:
    """Rotate plot so the public DROGA edge is horizontal in working space."""
    droga = plot.road_boundary()
    if droga is None or droga.geometry.length < 1e-6:
        return plot, 0.0, (0.0, 0.0)

    coords = list(droga.geometry.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    angle_deg = math.degrees(math.atan2(dy, dx))
    pivot = (
        (coords[0][0] + coords[-1][0]) / 2,
        (coords[0][1] + coords[-1][1]) / 2,
    )

    if abs(angle_deg) < 0.5:
        return plot, 0.0, pivot

    rotated_boundaries = [
        PlotBoundary(
            geometry=rotate(b.geometry, -angle_deg, origin=pivot),
            boundary_type=b.boundary_type,
            segment_index=b.segment_index,
            no_openings=b.no_openings,
        )
        for b in plot.boundaries
    ]
    return (
        Plot(
            number=plot.number,
            geometry=rotate(plot.geometry, -angle_deg, origin=pivot),
            boundaries=rotated_boundaries,
            mpzp=plot.mpzp,
            housing_type=plot.housing_type,
        ),
        angle_deg,
        pivot,
    )


def _horizontal_span_containing(
    geom: Polygon,
    y: float,
    x: float,
) -> Tuple[float, float] | None:
    """Return the horizontal polygon span at y, preferring the span with x."""
    minx, _, maxx, _ = geom.bounds
    line = LineString([(minx - geom.length, y), (maxx + geom.length, y)])
    cross = geom.intersection(line)
    segments: List[LineString] = []
    if isinstance(cross, LineString) and not cross.is_empty:
        segments = [cross]
    elif hasattr(cross, "geoms"):
        segments = [
            g for g in cross.geoms
            if isinstance(g, LineString) and g.length > 0.1
        ]
    if not segments:
        return None

    def score(seg: LineString) -> Tuple[int, float]:
        xs = [p[0] for p in seg.coords]
        return (1 if min(xs) <= x <= max(xs) else 0, seg.length)

    selected = max(segments, key=score)
    xs = [p[0] for p in selected.coords]
    return min(xs), max(xs)


def generate_road_tree_layout(
    plot: Plot,
    settings: RoadTreeSettings | None = None,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Generate cells and internal-road polygons for single-family subdivision.

    The layout is intentionally conservative:
    - one trunk starts at the public DROGA midpoint,
    - branches are perpendicular to the trunk,
    - branches are shortened inside the plot so they do not dead-end on
      neighbour/private boundaries,
    - cells are cut from the remaining row blocks and later filtered/scored by
      `plot_subdivider`.
    """
    settings = settings or RoadTreeSettings()
    max_area = plot.mpzp.max_sub_plot_area_m2
    target_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m

    # Optimal-ratio mode (FP4 CPP PlotSubdivider.cpp:192):
    # Zamiast wciskac min_front, uzyj target_front = max(min_front, sqrt(area × ratio))
    # → daje optymalne proporcje budynku, eliminuje "wciskane" wąskie pasy.
    if settings.use_optimal_ratio:
        avg_area = (plot.mpzp.min_sub_plot_area_m2 + max_area) / 2.0
        optimal_front = math.sqrt(avg_area * settings.target_ratio)
        target_front = max(target_front, optimal_front)

    rotated_plot, angle_deg, pivot = rotate_plot_to_droga_horizontal(plot)
    geom = rotated_plot.geometry
    minx, miny, maxx, maxy = geom.bounds
    plot_w = maxx - minx
    plot_h = maxy - miny

    target_depth = max(max_area / max(target_front, 1.0), 1.0)
    if plot_h <= target_depth * settings.shallow_depth_factor:
        min_area = plot.mpzp.min_sub_plot_area_m2
        cap_area = max_area * 1.05
        n_cols = max(1, math.ceil(geom.area / max_area))
        selected_cells: List[Polygon] = []
        for candidate_cols in range(n_cols, 80):
            candidate_w = plot_w / candidate_cols
            probe_cells: List[Polygon] = []
            for c in range(candidate_cols):
                probe = box(
                    minx + c * candidate_w,
                    miny,
                    minx + (c + 1) * candidate_w,
                    maxy,
                ).intersection(geom)
                if isinstance(probe, Polygon) and probe.area > 0.5:
                    probe_cells.append(probe)
                elif hasattr(probe, "geoms"):
                    probe_cells.extend([
                        g for g in probe.geoms
                        if isinstance(g, Polygon) and g.area > 0.5
                    ])
            if not probe_cells or max(c.area for c in probe_cells) > cap_area:
                continue

            grouped: List[Polygon] = []
            acc: Polygon | None = None
            valid = True
            for probe in probe_cells:
                acc = probe if acc is None else acc.union(probe)
                if not isinstance(acc, Polygon):
                    acc = max(acc.geoms, key=lambda p: p.area)
                if acc.area > cap_area:
                    valid = False
                    break
                if acc.area >= min_area:
                    grouped.append(acc)
                    acc = None
            if not valid:
                continue
            if acc is not None and acc.area > 0.01:
                if grouped and grouped[-1].area + acc.area <= cap_area:
                    merged = grouped[-1].union(acc)
                    grouped[-1] = (
                        merged if isinstance(merged, Polygon)
                        else max(merged.geoms, key=lambda p: p.area)
                    )
                else:
                    continue

            if grouped and all(min_area <= g.area <= cap_area for g in grouped):
                selected_cells = grouped
                break

        cells = selected_cells
        if not cells:
            col_w = plot_w / n_cols
            for c in range(n_cols):
                cell = box(
                    minx + c * col_w,
                    miny,
                    minx + (c + 1) * col_w,
                    maxy,
                ).intersection(geom)
                _append_polygons(cells, cell)
        if abs(angle_deg) > 0.01:
            cells = [rotate(c, angle_deg, origin=pivot) for c in cells]
        return cells, []

    n_lot_rows = max(1, math.ceil(plot_h / target_depth))
    branch_group = max(1, settings.branch_row_group)
    n_branches = max(0, math.ceil((n_lot_rows - 1) / branch_group))
    actual_row_depth = (
        (plot_h - n_branches * road_w) / n_lot_rows
        if n_lot_rows else plot_h
    )

    droga = rotated_plot.road_boundary()
    if droga is not None:
        droga_xs = [p[0] for p in droga.geometry.coords]
        droga_minx, droga_maxx = min(droga_xs), max(droga_xs)
        ratio = max(0.05, min(0.95, settings.trunk_position))
        trunk_x = droga_minx + (droga_maxx - droga_minx) * ratio
    else:
        trunk_x = (minx + maxx) / 2

    roads: List[Polygon] = []

    branch_after_rows = [
        min(branch_group + branch_group * i, n_lot_rows - 1)
        for i in range(n_branches)
    ]
    branch_ys = [
        miny + rows_before * actual_row_depth + i * road_w
        for i, rows_before in enumerate(branch_after_rows)
    ]
    trunk_end_y = min(maxy, max(miny + road_w, (branch_ys[-1] + road_w) if branch_ys else miny + road_w))
    trunk = box(
        trunk_x - road_w / 2,
        miny,
        trunk_x + road_w / 2,
        trunk_end_y,
    ).intersection(geom)
    _append_polygons(roads, trunk)

    min_clearance = (
        road_w * 0.2
        if settings.edge_clearance_front_factor <= 0.0
        else road_w * 1.1
    )
    edge_clearance = max(
        min_clearance,
        target_front * settings.edge_clearance_front_factor,
    )
    for y_road in branch_ys:
        span = _horizontal_span_containing(geom, y_road + road_w / 2, trunk_x)
        if span is None:
            continue
        rib_minx = span[0] + edge_clearance
        rib_maxx = span[1] - edge_clearance
        if rib_maxx <= rib_minx:
            continue
        branch = box(rib_minx, y_road, rib_maxx, y_road + road_w).intersection(geom)
        _append_polygons(roads, branch)

    if not roads:
        return [], []

    roads_union = unary_union(roads)
    block_pieces: List[Polygon] = []
    # Split land by the planned lot-row bands, not by Shapely connected
    # components. Shortened branches leave side passages around their ends;
    # using connected components would merge several bands into one huge
    # piece and then create oversized/no-road interior lots.
    for i in range(n_lot_rows):
        passed_branches = sum(1 for rows_before in branch_after_rows if rows_before <= i)
        y0 = miny + i * actual_row_depth + passed_branches * road_w
        y1 = min(y0 + actual_row_depth, maxy)
        band = geom.intersection(box(minx, y0, maxx, y1)).difference(roads_union)
        if isinstance(band, Polygon):
            block_pieces.append(band)
        elif hasattr(band, "geoms"):
            block_pieces.extend([
                g for g in band.geoms
                if isinstance(g, Polygon) and g.area > 1.0
            ])

    cells: List[Polygon] = []
    for piece in block_pieces:
        pminx, pminy, pmaxx, pmaxy = piece.bounds
        pw = pmaxx - pminx
        ph = pmaxy - pminy
        if pw < 1.0 or ph < 1.0:
            continue

        n_cols = max(1, math.ceil(pw / target_front))
        col_w = pw / n_cols
        min_col_w = target_front * 0.85
        while n_cols > 1 and col_w < min_col_w:
            n_cols -= 1
            col_w = pw / n_cols

        for c in range(n_cols):
            cell = box(
                pminx + c * col_w,
                pminy,
                pminx + (c + 1) * col_w,
                pmaxy,
            ).intersection(piece)
            _append_polygons(cells, cell)

    if abs(angle_deg) > 0.01:
        cells = [rotate(c, angle_deg, origin=pivot) for c in cells]
        roads = [rotate(r, angle_deg, origin=pivot) for r in roads]

    return cells, roads


def _append_polygons(out: List[Polygon], geom) -> None:
    if isinstance(geom, Polygon) and not geom.is_empty and geom.area > 0.5:
        out.append(geom)
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            if isinstance(g, Polygon) and not g.is_empty and g.area > 0.5:
                out.append(g)
