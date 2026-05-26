"""Stage 1 Mode B — propose building footprints per sub-plot.

For each SubPlot in a SubdivisionResult, propose a rectangular building
footprint inside its buildable_zone. Building dimensions depend on
BuildingType (per Polish architectural practice + Neufert):

    DETACHED (wolnostojaca):
        depth ~9-10m, width ~10-12m
        Free-standing, building centered in buildable_zone with 4-side setbacks.

    TWIN (bliżniacza):
        depth ~8-9m, width ~10-14m (2 segments share 1 wall)
        Each pair of adjacent sub-plots: buildings stick to their shared edge.

    TERRACED (szeregowa):
        depth ~7-8m, width ~6-8m per unit (multiple segments share 2 walls)
        Each sub-plot's building is "thread" with side walls at internal edges.

Output: SubPlot.proposed_building (Polygon) field set in-place.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from shapely.affinity import translate
from shapely.geometry import LineString, Point, Polygon, box

from core.plot_subdivider import BuildingType, SubdivisionResult, SubPlot


# Optymalne wymiary budynku per typ (depth × width), z PL praktyki + Neufert.
# depth = strona krótsza (perpendicular do drogi), width = wzdłuż drogi.
BUILDING_DIMENSIONS = {
    BuildingType.DETACHED: {
        "depth_opt": 9.5,    # 8-10m typowo
        "width_opt": 11.0,   # 10-12m typowo
        "depth_max": 12.0,
        "width_max": 14.0,
    },
    BuildingType.TWIN: {
        "depth_opt": 8.5,    # 8-9m
        "width_opt": 9.0,    # per segment (1 z pary)
        "depth_max": 11.0,
        "width_max": 12.0,
    },
    BuildingType.TERRACED: {
        "depth_opt": 7.5,    # 7-8m
        "width_opt": 6.5,    # per segment w ciągu
        "depth_max": 10.0,
        "width_max": 8.0,
    },
}


def propose_buildings(
    result: SubdivisionResult,
    building_type: BuildingType,
) -> SubdivisionResult:
    """Propose building footprints for all sub-plots in SubdivisionResult.

    Modifies SubPlot.proposed_building in-place + returns result for chaining.

    Args:
        result: SubdivisionResult z plot_subdivider.subdivide().
        building_type: DETACHED / TWIN / TERRACED — wpływa na geometrię.

    Returns: same result with proposed_building set per sub-plot.
    """
    if not result.sub_plots:
        return result

    dims = BUILDING_DIMENSIONS.get(building_type, BUILDING_DIMENSIONS[BuildingType.DETACHED])

    if building_type == BuildingType.DETACHED:
        for sub in result.sub_plots:
            sub.proposed_building = _propose_detached(sub, dims)
    elif building_type == BuildingType.TWIN:
        _propose_semi_pairs(result.sub_plots, dims)
    elif building_type == BuildingType.TERRACED:
        _propose_terraced_chain(result.sub_plots, dims)

    return result


def _propose_detached(sub: SubPlot, dims: dict) -> Optional[Polygon]:
    """Center a rectangle in buildable_zone.

    Wolnostojąca = budynek z 4 stronami z setbackiem, w środku buildable_zone.
    """
    if not sub.has_buildable_zone:
        return None
    bz = sub.buildable_zone

    # Initialize candidate dimensions
    minx, miny, maxx, maxy = bz.bounds
    bz_w = maxx - minx
    bz_d = maxy - miny

    # Wybór orientacji: front budynku (szerokość) wzdłuż dłuższego boku
    # buildable_zone (zwykle perpendicular do drogi).
    if bz_w > bz_d:
        building_w, building_d = dims["width_opt"], dims["depth_opt"]
    else:
        building_w, building_d = dims["depth_opt"], dims["width_opt"]

    # Clamp do dostępnej przestrzeni z 50cm marginesem
    building_w = min(building_w, bz_w - 0.5)
    building_d = min(building_d, bz_d - 0.5)
    if building_w < 4 or building_d < 4:
        return None  # zbyt mało miejsca

    # Centruj w centroidzie buildable_zone
    cx, cy = bz.centroid.x, bz.centroid.y
    rect = box(cx - building_w / 2, cy - building_d / 2,
               cx + building_w / 2, cy + building_d / 2)

    # Sanity: musi się mieścić w buildable_zone
    if bz.contains(rect):
        return rect
    # Próba intersekcji jeśli prawie pasuje
    inter = bz.intersection(rect)
    if isinstance(inter, Polygon) and inter.area > 0.8 * rect.area:
        return inter
    return None


def _propose_semi_pairs(sub_plots: List[SubPlot], dims: dict) -> None:
    """Bliźniacza: pary sub-działek, budynki stykają się 1 wspólną ścianą.

    Algorithm:
    1. Znajdź sąsiednie sub-plot pary (wspólna krawędź ≥ 6m typowo).
    2. Dla każdej pary: budynek "przyklejony" do wspólnej krawędzi.
    3. Sub-plot bez pary → fallback do detached.
    """
    pairs = _find_adjacent_pairs(sub_plots, min_shared_edge=6.0)
    paired_ids = set()

    for a, b, shared_edge in pairs:
        if id(a) in paired_ids or id(b) in paired_ids:
            continue
        _place_semi_pair(a, b, shared_edge, dims)
        paired_ids.add(id(a))
        paired_ids.add(id(b))

    # Niesparowane → detached
    detached_dims = BUILDING_DIMENSIONS[BuildingType.DETACHED]
    for sub in sub_plots:
        if id(sub) not in paired_ids and not getattr(sub, "proposed_building", None):
            sub.proposed_building = _propose_detached(sub, detached_dims)


def _propose_terraced_chain(sub_plots: List[SubPlot], dims: dict) -> None:
    """Szeregowa: ciągi sub-działek, budynki stykają się 2 ścianami bocznymi.

    Algorithm:
    1. Pogrupuj sub-plots w "łańcuchy" — kolejne sąsiadujące krawędziami pionowymi.
    2. W każdym łańcuchu: środkowe sub-plots mają budynki z 2 ścianami wspólnymi
       (boczne ściany 0m setback), skrajne 1 ścianą wspólną.
    """
    chains = _find_terraced_chains(sub_plots, min_shared_edge=4.0)
    chained_ids = set()

    for chain in chains:
        if len(chain) < 3:
            continue  # ciąg < 3 → traktuj jako bliźniacza
        _place_terraced_chain(chain, dims)
        for sub in chain:
            chained_ids.add(id(sub))

    # Pozostałe (≤2 sąsiadów) → semi/detached fallback
    detached_dims = BUILDING_DIMENSIONS[BuildingType.DETACHED]
    for sub in sub_plots:
        if id(sub) not in chained_ids and not getattr(sub, "proposed_building", None):
            sub.proposed_building = _propose_detached(sub, detached_dims)


def _find_adjacent_pairs(
    sub_plots: List[SubPlot],
    min_shared_edge: float,
) -> List[Tuple[SubPlot, SubPlot, LineString]]:
    """Znajdź pary sąsiednich sub-działek dzielących krawędź ≥ min_shared_edge."""
    pairs = []
    for i, a in enumerate(sub_plots):
        for b in sub_plots[i + 1:]:
            shared = a.polygon.boundary.intersection(b.polygon.boundary)
            if shared.is_empty:
                continue
            shared_line = _longest_linestring(shared)
            if shared_line is None or shared_line.length < min_shared_edge:
                continue
            pairs.append((a, b, shared_line))
    # Sortuj po długości wspólnej krawędzi malejąco
    pairs.sort(key=lambda p: -p[2].length)
    return pairs


def _find_terraced_chains(
    sub_plots: List[SubPlot],
    min_shared_edge: float,
) -> List[List[SubPlot]]:
    """Znajdź łańcuchy sąsiadujących sub-działek (szeregowa: 3+ w ciągu).

    Buduje graf sąsiedztwa per wspólna krawędź, traktuje łańcuch jako
    spójną komponentę grafu (sąsiedzi po lewej-prawej).
    """
    # adjacency map: id(sub) -> List[sub]
    adj = {id(s): [] for s in sub_plots}
    for i, a in enumerate(sub_plots):
        for b in sub_plots[i + 1:]:
            shared = a.polygon.boundary.intersection(b.polygon.boundary)
            if shared.is_empty:
                continue
            shared_line = _longest_linestring(shared)
            if shared_line is None or shared_line.length < min_shared_edge:
                continue
            adj[id(a)].append(b)
            adj[id(b)].append(a)

    # BFS spójnych komponentów
    visited = set()
    chains = []
    by_id = {id(s): s for s in sub_plots}
    for sub in sub_plots:
        if id(sub) in visited:
            continue
        # BFS
        chain = []
        stack = [sub]
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


def _longest_linestring(geom) -> Optional[LineString]:
    """Wyciągnij najdłuższy LineString z (Multi)LineString/Collection."""
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


def _place_semi_pair(
    a: SubPlot, b: SubPlot,
    shared_edge: LineString,
    dims: dict,
) -> None:
    """Bliźniacza: dwa budynki stykają się wspólną ścianą = shared_edge midpoint.

    Każdy budynek ma 1 stronę na shared_edge (depth = perpendicular do edge).
    """
    if not a.has_buildable_zone or not b.has_buildable_zone:
        return

    edge_coords = list(shared_edge.coords)
    if len(edge_coords) < 2:
        return
    # Wektor krawędzi
    p1, p2 = edge_coords[0], edge_coords[-1]
    edge_len = shared_edge.length
    if edge_len < 1e-6:
        return
    # Kierunek wzdłuż krawędzi (unit)
    ex, ey = (p2[0] - p1[0]) / edge_len, (p2[1] - p1[1]) / edge_len
    # Prostopadły (90° w prawo)
    px, py = ey, -ex

    width = min(dims["width_opt"], edge_len - 1.0)
    depth = dims["depth_opt"]
    if width < 4:
        return

    # Centroid shared edge
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2

    # Buduj prostokąt dla każdej sub-działki po przeciwnej stronie shared edge
    for sub in (a, b):
        bz = sub.buildable_zone
        # Wybierz kierunek "do środka sub-działki" (na podstawie centroidu)
        sub_centroid = sub.polygon.centroid
        # Wektor od midpoint edge do centroidu sub-plot
        to_sub_x = sub_centroid.x - mx
        to_sub_y = sub_centroid.y - my
        # Dot product z perpendicular — czy pozytywne (w stronę normal) czy negatywne
        dot = to_sub_x * px + to_sub_y * py
        sign = 1 if dot > 0 else -1

        # Budynek: od shared edge (na linii) w głąb sub-plot o depth/2 (centrum)
        # Rectangle corners (axis-aligned approximation):
        # Center: midpoint edge + sign * depth/2 * perpendicular
        bx = mx + sign * depth / 2 * px
        by = my + sign * depth / 2 * py
        # Buduj prostokąt zorientowany do krawędzi
        # Half-width along edge dir, half-depth perpendicular
        hw = width / 2
        hd = depth / 2
        corners = [
            (bx - hw * ex - hd * sign * px, by - hw * ey - hd * sign * py),
            (bx + hw * ex - hd * sign * px, by + hw * ey - hd * sign * py),
            (bx + hw * ex + hd * sign * px, by + hw * ey + hd * sign * py),
            (bx - hw * ex + hd * sign * px, by - hw * ey + hd * sign * py),
        ]
        rect = Polygon(corners)
        # Clamp do buildable_zone
        if bz.contains(rect):
            sub.proposed_building = rect
        else:
            inter = bz.intersection(rect)
            if isinstance(inter, Polygon) and inter.area > 0.7 * rect.area:
                sub.proposed_building = inter
            else:
                # Fallback: detached
                sub.proposed_building = _propose_detached(sub, BUILDING_DIMENSIONS[BuildingType.DETACHED])


def _place_terraced_chain(chain: List[SubPlot], dims: dict) -> None:
    """Szeregowa: ciąg N sub-działek. Środkowe mają 2 ściany wspólne (0 setback po bokach).

    Uproszczone: dla każdej sub-działki w ciągu budynek prostokątny pełna szerokość
    sub-działki (lub buildable_zone width), depth = dims["depth_opt"].
    """
    detached_fallback = BUILDING_DIMENSIONS[BuildingType.DETACHED]
    for sub in chain:
        if not sub.has_buildable_zone:
            sub.proposed_building = None
            continue
        bz = sub.buildable_zone
        minx, miny, maxx, maxy = bz.bounds
        bz_w = maxx - minx
        bz_d = maxy - miny

        # Budynek wypełnia szerokość sub-działki (lub buildable_zone), depth=opt
        building_w = bz_w - 0.5  # 25cm margines z każdej strony
        building_d = min(dims["depth_opt"], bz_d - 0.5)
        if building_w < 4 or building_d < 4:
            sub.proposed_building = _propose_detached(sub, detached_fallback)
            continue

        # Wybór y-pozycji: bliżej drogi (perdpendicular bottom) lub centroid
        # Dla MVP — centruj w bz
        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2
        rect = box(cx - building_w / 2, cy - building_d / 2,
                   cx + building_w / 2, cy + building_d / 2)
        if bz.contains(rect):
            sub.proposed_building = rect
        else:
            inter = bz.intersection(rect)
            if isinstance(inter, Polygon) and inter.area > 0.7 * rect.area:
                sub.proposed_building = inter
            else:
                sub.proposed_building = _propose_detached(sub, detached_fallback)
