"""Stage 1 -> Stage 4 input adapter (pure-Python, no Qt).

Given a Mode B SubPlot with a `proposed_building` footprint, derive the
three values Stage 4 expects:
    polygon     - building footprint as a single shapely.Polygon
    entry       - (x, y) midpoint of the polygon edge nearest a road
    wall_types  - per-edge list[WallType] (FACADE / INTERNAL),
                  one entry per polygon exterior edge, in coord order.

See docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md.
"""
from __future__ import annotations

from typing import Optional

from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from core.models import WallType
from core.plot_model import BoundaryType
from core.plot_subdivider import SubPlot

_SHARED_WALL_TOLERANCE_M = 0.5    # how close an edge midpoint must lie to a
                                  # sub-plot is_shared_wall boundary to count
                                  # as INTERNAL


def building_to_apartment_input(
    sub: SubPlot,
    roads: Optional[list[Polygon]] = None,
) -> tuple[Polygon, tuple[float, float], list[WallType]]:
    """Return (polygon, entry, wall_types) for Stage 4 from a SubPlot.

    See module docstring + spec section 4 for algorithm details.
    """
    polygon = _largest_polygon(sub.proposed_building)
    edges = _exterior_edges(polygon)

    entry_idx = _entry_edge_index(edges, sub, roads)
    entry = _midpoint(edges[entry_idx])

    wall_types = [_classify_edge(e, sub) for e in edges]

    return polygon, entry, wall_types


def _largest_polygon(geom) -> Polygon:
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda p: p.area)
    return geom


def _exterior_edges(polygon: Polygon) -> list[LineString]:
    coords = list(polygon.exterior.coords)
    # coords[-1] == coords[0] for closed rings; drop the closing duplicate.
    return [
        LineString([coords[i], coords[i + 1]])
        for i in range(len(coords) - 1)
    ]


def _midpoint(edge: LineString) -> tuple[float, float]:
    p = edge.interpolate(0.5, normalized=True)
    return (p.x, p.y)


def _entry_edge_index(
    edges: list[LineString],
    sub: SubPlot,
    roads: Optional[list[Polygon]],
) -> int:
    road_geoms: list = [
        b.geometry for b in sub.boundaries
        if b.boundary_type == BoundaryType.DROGA
    ]
    if roads:
        road_geoms.extend(r.boundary for r in roads if not r.is_empty)

    if road_geoms:
        def midpoint_to_any_road(i: int) -> float:
            mx, my = _midpoint(edges[i])
            p = Point(mx, my)
            return min(p.distance(r) for r in road_geoms)
        return min(range(len(edges)), key=midpoint_to_any_road)

    # Fallback: longest edge; tie-break by lowest midpoint Y (south-facing).
    return max(
        range(len(edges)),
        key=lambda i: (edges[i].length, -_midpoint(edges[i])[1]),
    )


def _classify_edge(edge: LineString, sub: SubPlot) -> WallType:
    mx, my = _midpoint(edge)
    p = Point(mx, my)
    for b in sub.boundaries:
        if not b.is_shared_wall:
            continue
        if p.distance(b.geometry) <= _SHARED_WALL_TOLERANCE_M:
            return WallType.INTERNAL
    return WallType.FACADE
