"""Stage 1 Mode B — sub-plot topology helpers.

Adjacency detection shared between `core.building_proposer` (where to place
buildings inside paired/chained sub-plots) and `core.plot_subdivider`
(Q21 — mark the shared boundary so setback drops to 0 on the shared side).

Both call sites need exactly the same notion of "two sub-plots are paired
through a shared edge", so the logic lives in one module rather than being
duplicated.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from shapely.geometry import LineString

from core.plot_subdivider import SubPlot


def longest_linestring(geom) -> Optional[LineString]:
    """Return the longest LineString inside a (Multi)LineString / collection.

    `Polygon.boundary.intersection(...)` can return a single LineString, a
    MultiLineString, or a GeometryCollection — pick the dominant linear
    component so callers can measure shared-edge length.
    """
    if geom.is_empty:
        return None
    if isinstance(geom, LineString):
        return geom
    if hasattr(geom, "geoms"):
        lines = [g for g in geom.geoms if isinstance(g, LineString)]
        if not lines:
            return None
        return max(lines, key=lambda g: g.length)
    return None


def find_adjacent_pairs(
    sub_plots: List[SubPlot],
    min_shared_edge: float,
) -> List[Tuple[SubPlot, SubPlot, LineString]]:
    """Return all unordered sub-plot pairs whose shared boundary is at least
    `min_shared_edge` metres long.

    Result is sorted by shared-edge length descending so callers that pick
    "best partner first" (TWIN) get the dominant pair on top.
    """
    pairs: List[Tuple[SubPlot, SubPlot, LineString]] = []
    for i, a in enumerate(sub_plots):
        for b in sub_plots[i + 1:]:
            shared = a.polygon.boundary.intersection(b.polygon.boundary)
            if shared.is_empty:
                continue
            shared_line = longest_linestring(shared)
            if shared_line is None or shared_line.length < min_shared_edge:
                continue
            pairs.append((a, b, shared_line))
    pairs.sort(key=lambda p: -p[2].length)
    return pairs


def find_chains(
    sub_plots: List[SubPlot],
    min_shared_edge: float,
) -> List[List[SubPlot]]:
    """Return connected components of the sub-plot adjacency graph (edges
    weighted by shared-edge length ≥ `min_shared_edge`).

    Used by TERRACED placement: a chain of N sub-plots → N units row-house
    where internal members share two walls and edge members share one.
    """
    adj = {id(s): [] for s in sub_plots}
    for i, a in enumerate(sub_plots):
        for b in sub_plots[i + 1:]:
            shared = a.polygon.boundary.intersection(b.polygon.boundary)
            if shared.is_empty:
                continue
            shared_line = longest_linestring(shared)
            if shared_line is None or shared_line.length < min_shared_edge:
                continue
            adj[id(a)].append(b)
            adj[id(b)].append(a)

    visited: set = set()
    chains: List[List[SubPlot]] = []
    for sub in sub_plots:
        if id(sub) in visited:
            continue
        chain: List[SubPlot] = []
        stack: List[SubPlot] = [sub]
        while stack:
            cur = stack.pop()
            if id(cur) in visited:
                continue
            visited.add(id(cur))
            chain.append(cur)
            for nb in adj[id(cur)]:
                if id(nb) not in visited:
                    stack.append(nb)
        chains.append(chain)
    return chains
