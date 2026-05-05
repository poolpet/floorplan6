"""
Walking distance validation for floor layout (WT §256).

Builds a graph from corridor + connector centerlines and computes shortest path
from each apartment door to the nearest stairwell entry. Replaces the simple
Euclidean heuristic in `floor_layout._walking_distance()`.

Graph structure:
  Nodes:
    - Sample points along corridor centerline (every CORRIDOR_SAMPLE_STEP_M)
    - Sample points along each connector centerline
    - One node at each stairwell entry (where stairwell touches connector
      or corridor)
    - One node per apartment door (mid of apartment-corridor or
      apartment-connector shared edge)
  Edges:
    - Sequential rail nodes connected with their actual distance
    - Apartment doors and stairwell entries connected to nearest rail node
"""
from __future__ import annotations

import math
from typing import Optional

import networkx as nx
from shapely.geometry import LineString, Point, Polygon

CORRIDOR_SAMPLE_STEP_M = 1.0  # densify corridor every 1m
DOOR_MIN_OVERLAP_M = 0.9       # min shared edge to consider as door


def compute_walking_distances(
    apartments: list,
    stairwells: list[Polygon],
    corridor: Polygon,
    connectors: Optional[list[Polygon]] = None,
) -> list[float]:
    """Walking distance from each apartment to its nearest stairwell.

    Args:
        apartments: list of `Apartment` objects with `.polygon`.
        stairwells: list of stairwell polygons.
        corridor: main corridor polygon.
        connectors: optional connector polygons (vertical strips
            between stairwells and main corridor).

    Returns:
        List of distances [m], one per apartment. `inf` if no path exists.
    """
    if connectors is None:
        connectors = []

    G = nx.Graph()

    # 1. Sample rail nodes along corridor centerline
    corridor_rail = _sample_centerline(corridor, prefix="cor")
    _add_rail_to_graph(G, corridor_rail)

    # 2. Sample rail nodes along each connector
    connector_rails = []
    for ci, conn in enumerate(connectors):
        rail = _sample_centerline(conn, prefix=f"con{ci}")
        _add_rail_to_graph(G, rail)
        connector_rails.append(rail)
        # Connect connector rail ends to nearest corridor rail node
        if rail and corridor_rail:
            for end in (rail[0], rail[-1]):
                nearest = _nearest_node(corridor_rail, end[1])
                G.add_edge(end[0], nearest[0],
                           weight=Point(end[1]).distance(Point(nearest[1])))

    # 3. Add stairwell entry nodes
    stair_entry_nodes = []
    for si, stair in enumerate(stairwells):
        entry = _stairwell_entry_point(stair, corridor, connectors)
        if entry is None:
            continue
        node = f"stair{si}"
        G.add_node(node, pos=(entry.x, entry.y))
        # Connect to nearest rail node
        all_rails = corridor_rail + [n for r in connector_rails for n in r]
        nearest = _nearest_node(all_rails, (entry.x, entry.y))
        if nearest:
            G.add_edge(node, nearest[0],
                       weight=entry.distance(Point(nearest[1])))
        stair_entry_nodes.append(node)

    # 4. Per apartment: door node + edge to nearest rail node
    distances = []
    for ai, apt in enumerate(apartments):
        if apt.polygon is None:
            distances.append(float("inf"))
            continue
        door = _apartment_door_point(apt.polygon, corridor, connectors)
        if door is None:
            distances.append(float("inf"))
            continue
        node = f"apt{ai}"
        G.add_node(node, pos=(door.x, door.y))
        all_rails = corridor_rail + [n for r in connector_rails for n in r]
        nearest = _nearest_node(all_rails, (door.x, door.y))
        if nearest is None:
            distances.append(float("inf"))
            continue
        G.add_edge(node, nearest[0],
                   weight=door.distance(Point(nearest[1])))

        # Shortest path to nearest stairwell
        best = float("inf")
        for sn in stair_entry_nodes:
            try:
                d = nx.shortest_path_length(G, node, sn, weight="weight")
                if d < best:
                    best = d
            except nx.NetworkXNoPath:
                continue
        distances.append(best)

    return distances


def _sample_centerline(polygon: Polygon, prefix: str) -> list[tuple]:
    """Sample points along the longer centerline of a rectangular polygon.

    Returns list of (node_id, (x, y)) tuples ordered along the centerline.
    """
    if polygon is None or polygon.is_empty:
        return []
    bx0, by0, bx1, by1 = polygon.bounds
    width = bx1 - bx0
    height = by1 - by0
    if width >= height:
        # Horizontal centerline
        cy = (by0 + by1) / 2
        n = max(2, int(width / CORRIDOR_SAMPLE_STEP_M) + 1)
        return [(f"{prefix}_{i}", (bx0 + i * width / (n - 1), cy)) for i in range(n)]
    else:
        cx = (bx0 + bx1) / 2
        n = max(2, int(height / CORRIDOR_SAMPLE_STEP_M) + 1)
        return [(f"{prefix}_{i}", (cx, by0 + i * height / (n - 1))) for i in range(n)]


def _add_rail_to_graph(G: nx.Graph, rail: list[tuple]) -> None:
    """Add rail nodes + sequential edges (actual distance)."""
    for node_id, pos in rail:
        G.add_node(node_id, pos=pos)
    for i in range(len(rail) - 1):
        a_id, a_pos = rail[i]
        b_id, b_pos = rail[i + 1]
        d = math.hypot(b_pos[0] - a_pos[0], b_pos[1] - a_pos[1])
        G.add_edge(a_id, b_id, weight=d)


def _nearest_node(rail: list[tuple], pt: tuple) -> Optional[tuple]:
    """Find nearest rail node to a given (x, y) point."""
    if not rail:
        return None
    return min(rail, key=lambda n: math.hypot(n[1][0] - pt[0], n[1][1] - pt[1]))


def _apartment_door_point(
    apt_poly: Polygon,
    corridor: Polygon,
    connectors: list[Polygon],
) -> Optional[Point]:
    """Mid of apartment-corridor (or apartment-connector) shared edge.

    Tries main corridor first; if no sufficient shared edge, tries connectors.
    """
    shared = apt_poly.intersection(corridor)
    if hasattr(shared, "length") and shared.length >= DOOR_MIN_OVERLAP_M:
        if shared.geom_type == "LineString":
            return shared.centroid
        if shared.geom_type == "MultiLineString":
            longest = max(shared.geoms, key=lambda g: g.length)
            return longest.centroid
    for conn in connectors:
        s = apt_poly.intersection(conn)
        if hasattr(s, "length") and s.length >= DOOR_MIN_OVERLAP_M:
            if s.geom_type == "LineString":
                return s.centroid
            if s.geom_type == "MultiLineString":
                longest = max(s.geoms, key=lambda g: g.length)
                return longest.centroid
    return None


def _stairwell_entry_point(
    stair: Polygon,
    corridor: Polygon,
    connectors: list[Polygon],
) -> Optional[Point]:
    """Where the stairwell connects to circulation (corridor or connector)."""
    shared = stair.intersection(corridor)
    if hasattr(shared, "length") and shared.length >= DOOR_MIN_OVERLAP_M:
        if shared.geom_type == "LineString":
            return shared.centroid
        if shared.geom_type == "MultiLineString":
            return max(shared.geoms, key=lambda g: g.length).centroid
    for conn in connectors:
        s = stair.intersection(conn)
        if hasattr(s, "length") and s.length >= DOOR_MIN_OVERLAP_M:
            if s.geom_type == "LineString":
                return s.centroid
            if s.geom_type == "MultiLineString":
                return max(s.geoms, key=lambda g: g.length).centroid
    return None
