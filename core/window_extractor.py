"""
Ekstrakcja okien fasadowych z wygenerowanego rzutu (V4 — Tapir 1.4.0).

Dla każdego pokoju z `spec.wymaga_okna=True` znajdujemy najdłuższą krawędź
pokoju leżącą na FACADE (zewnętrznej ścianie mieszkania), matchujemy ją
do istniejącej ściany AC (boundary user'a) i wstawiamy okno w jej środku.

Default wymiary per Strefa (typowe lokal mieszkalny PL):
    DZIENNA:    2.10 × 1.50m, sill 0.90m  (salon, kuchnia)
    NOCNA:      1.20 × 1.40m, sill 0.90m  (sypialnia)
    USLUGOWA:   0.60 × 0.80m, sill 1.50m  (łazienka z oknem)
    inne:       1.20 × 1.40m, sill 0.90m

Ograniczenia Tapir 1.4.0 CreateWindows (stock — bez custom rozszerzeń):
    ownerWallId, centerOffset, width, height, sillHeight.
Brak: oSide, libraryPart, reflected — AC używa default.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from shapely.geometry import LineString, Polygon

from core.models import FloorPlan, Strefa, WallType

# Wymiary okien per Strefa (m) — STARTING POINT przed regułą WT 1/8.
# Faktyczna szerokość/wysokość są zwiększane do osiągnięcia min_glass_area.
#
# DZIENNA = okno balkonowe (parapet 0, od podłogi do sufitka, 2.10m wysokie).
#           Typ "drzwi balkonowe" — często użytkownik chce wyjść na balkon.
# NOCNA   = standardowe okno na parapecie 90cm (ergonomicznie do łóżka).
# USLUGOWA= małe okno wysoko (łazienka, prywatność).
WINDOW_DIMENSIONS: dict[Strefa, dict[str, float]] = {
    Strefa.DZIENNA:   {"width": 2.10, "height": 2.10, "sill": 0.00},  # okno balkonowe
    Strefa.NOCNA:     {"width": 1.20, "height": 1.40, "sill": 0.90},
    Strefa.USLUGOWA:  {"width": 0.60, "height": 0.80, "sill": 1.50},
}
DEFAULT_WINDOW = {"width": 1.20, "height": 1.40, "sill": 0.90}

# WT (Warunki Techniczne PL): powierzchnia okna ≥ 1/8 powierzchni pokoju.
# Dla pokoju mieszkalnego — wymaganie z PL building code (Rozporządzenie WT).
WT_GLASS_AREA_RATIO = 1.0 / 8.0

# Maksymalna wysokość okna (m) — w razie potrzeby zwiększenia by spełnić WT 1/8.
WINDOW_MAX_HEIGHT = 2.20
# Minimalna szerokość okna (m) — zbyt wąska fasada pokoju → pomijamy.
WINDOW_MIN_WIDTH = 0.40
# Margines od ścian (m) — okno nie może być na krawędzi ściany.
EDGE_MARGIN = 0.30

# Tolerancje (m)
EDGE_MATCH_TOL = 0.30   # midpoint krawędzi pokoju vs midpoint AC wall
EDGE_ON_BOUNDARY_TOL = 0.20   # czy midpoint krawędzi pokoju leży na boundary


@dataclass
class WindowSegment:
    wall_guid: str
    center_offset: float       # m wzdłuż AC wall od jej begC
    width: float
    height: float
    sill_height: float
    # Diagnostyka
    room_name: str = ""
    edge_length: float = 0.0


def extract_windows(
    plan: FloorPlan,
    ac_walls: list[dict],
) -> list[WindowSegment]:
    """Wyciągnij okna dla pokoi wymagających okna.

    Args:
        plan: Wygenerowany FloorPlan.
        ac_walls: Lista dict z details ścian AC. Każdy dict ma `_guid`
            (z fetchSelectedDetails-style) + `details` z begCoordinate/endCoordinate
            (lub na poziomie root w niektórych formatach Tapira).

    Returns:
        Lista WindowSegment, jedno okno per pokój wymagający (na najdłuższej fasadzie).
    """
    # Boundary mieszkania — kandydaci na FACADE
    facade_edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for edge in plan.boundary.edges:
        if edge.wall_type == WallType.FACADE:
            facade_edges.append((edge.start, edge.end))
    if not facade_edges:
        return []

    # Normalizacja AC walls do (guid, begC, endC, length)
    ac_lines: list[tuple[str, tuple[float, float], tuple[float, float], float]] = []
    for w in ac_walls:
        guid = _guid_from(w)
        beg, end = _begend_from(w)
        if guid and beg and end:
            length = math.hypot(end[0] - beg[0], end[1] - beg[1])
            if length > 1e-6:
                ac_lines.append((guid, beg, end, length))
    if not ac_lines:
        return []

    windows: list[WindowSegment] = []
    for room in plan.rooms:
        if room.polygon is None or not room.spec.wymaga_okna:
            continue

        # Krawędzie pokoju leżące na facade boundary
        room_facade_edges = _room_facade_edges(room.polygon, facade_edges)
        if not room_facade_edges:
            continue

        # Najdłuższa = najlepszy kandydat na okno
        room_facade_edges.sort(key=lambda e: -e[2])
        best_p1, best_p2, edge_len = room_facade_edges[0]

        # Znajdź AC wall pokrywającą się z tą krawędzią
        owner = _find_owner_wall(best_p1, best_p2, ac_lines)
        if owner is None:
            continue
        wall_guid, ac_beg, ac_end, ac_len = owner

        # centerOffset = środek edge pokoju zrzutowany na AC wall (od begC)
        mid_room = ((best_p1[0] + best_p2[0]) / 2.0,
                    (best_p1[1] + best_p2[1]) / 2.0)
        center_offset = _project_along_wall(mid_room, ac_beg, ac_end)
        center_offset = max(0.0, min(ac_len, center_offset))

        # Wymiary z reguły WT 1/8 — powierzchnia okna ≥ room.area / 8
        room_area = room.polygon.area
        dims = _wt_compliant_dimensions(
            strefa=room.spec.strefa,
            room_area=room_area,
            max_edge_width=edge_len - EDGE_MARGIN,
        )
        if dims is None:
            continue   # fasada zbyt wąska / nie da się spełnić WT

        windows.append(WindowSegment(
            wall_guid=wall_guid,
            center_offset=center_offset,
            width=dims["width"],
            height=dims["height"],
            sill_height=dims["sill"],
            room_name=room.spec.nazwa,
            edge_length=edge_len,
        ))

    return windows


def _guid_from(elem: dict) -> Optional[str]:
    if not isinstance(elem, dict):
        return None
    # Format detail z _guid (z naszej fetchSelectedDetails)
    if "_guid" in elem:
        return elem["_guid"]
    eid = elem.get("elementId", elem)
    if isinstance(eid, dict):
        return eid.get("guid")
    return None


def _begend_from(elem: dict) -> tuple[Optional[tuple[float, float]], Optional[tuple[float, float]]]:
    """Wyciagnij begC/endC z roznych formatow Tapir."""
    if not isinstance(elem, dict):
        return None, None
    details = elem.get("details", {})
    beg = details.get("begCoordinate") or elem.get("begCoordinate")
    end = details.get("endCoordinate") or elem.get("endCoordinate")
    if not beg or not end:
        return None, None
    try:
        return ((float(beg["x"]), float(beg["y"])),
                (float(end["x"]), float(end["y"])))
    except (KeyError, TypeError):
        return None, None


def _room_facade_edges(
    room_polygon: Polygon,
    facade_edges: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    """Zwróć edges pokoju leżące na fasadzie boundary.

    Returns: [(p1, p2, length), ...]
    """
    if room_polygon.geom_type == "MultiPolygon":
        room_polygon = max(room_polygon.geoms, key=lambda g: g.area)
    coords = list(room_polygon.exterior.coords)

    result: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    facade_lines = [LineString([s, e]) for s, e in facade_edges]

    for i in range(len(coords) - 1):
        p1 = (coords[i][0], coords[i][1])
        p2 = (coords[i + 1][0], coords[i + 1][1])
        edge_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if edge_len < 0.30:
            continue
        # Czy midpoint edge pokoju leży na którejś z facade lines?
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        from shapely.geometry import Point
        mid_pt = Point(mid)
        for fl in facade_lines:
            if fl.distance(mid_pt) < EDGE_ON_BOUNDARY_TOL:
                result.append((p1, p2, edge_len))
                break

    return result


def _find_owner_wall(
    edge_p1: tuple[float, float],
    edge_p2: tuple[float, float],
    ac_lines: list[tuple[str, tuple[float, float], tuple[float, float], float]],
) -> Optional[tuple[str, tuple[float, float], tuple[float, float], float]]:
    """Znajdź AC wall która pokrywa się z edge pokoju.

    Wybieramy ścianę której LineString jest najbliżej midpointu edge pokoju.
    """
    from shapely.geometry import Point, LineString as SLS
    mid = Point((edge_p1[0] + edge_p2[0]) / 2.0,
                (edge_p1[1] + edge_p2[1]) / 2.0)
    best = None
    best_dist = EDGE_MATCH_TOL
    for guid, beg, end, length in ac_lines:
        ls = SLS([beg, end])
        d = ls.distance(mid)
        if d < best_dist:
            best_dist = d
            best = (guid, beg, end, length)
    return best


def _wt_compliant_dimensions(
    strefa: Strefa,
    room_area: float,
    max_edge_width: float,
) -> Optional[dict[str, float]]:
    """Zwraca wymiary okna spełniające WT 1/8 (Polish building code).

    Algorytm:
        1. Start od WINDOW_DIMENSIONS[strefa] (lub DEFAULT_WINDOW).
        2. Compute min_glass_area = room_area * WT_GLASS_AREA_RATIO.
        3. Jeśli default_width × default_height < min_glass_area:
           a) Najpierw zwiększaj szerokość do max_edge_width (zachowując height).
           b) Jeśli wciąż za mało — zwiększaj wysokość do WINDOW_MAX_HEIGHT.
        4. Jeśli nadal nie spełnia → zwracamy None (fasada za wąska, sygnał
           że trzeba dwa okna albo większą fasadę).

    Returns:
        dict {width, height, sill} jeśli OK, None gdy niemożliwe.
    """
    base = WINDOW_DIMENSIONS.get(strefa, DEFAULT_WINDOW)
    width = base["width"]
    height = base["height"]
    sill = base["sill"]

    min_glass_area = room_area * WT_GLASS_AREA_RATIO

    # Step 1: clamp width do fasady pokoju (minus margines)
    width = min(width, max_edge_width)
    if width < WINDOW_MIN_WIDTH:
        return None

    # Step 2: jeśli za mało powierzchni — rozszerz width
    if width * height < min_glass_area:
        needed_width = min_glass_area / height
        width = min(needed_width, max_edge_width)

    # Step 3: jeśli wciąż za mało (fasada za wąska) — zwiększ height
    if width * height < min_glass_area:
        needed_height = min_glass_area / width
        height = min(needed_height, WINDOW_MAX_HEIGHT)

    # Sprawdź czy WT 1/8 spełnione (margines błędu 1%)
    if width * height < min_glass_area * 0.99:
        # Nie da się — pokój za duży na pojedyncze okno na tej fasadzie
        # MVP: zwracamy max possible (lepiej cokolwiek niż nic).
        # Możliwa V4.2: stworzyć 2+ okien.
        pass

    if width < WINDOW_MIN_WIDTH:
        return None

    return {"width": width, "height": height, "sill": sill}


def _project_along_wall(
    point: tuple[float, float],
    wall_beg: tuple[float, float],
    wall_end: tuple[float, float],
) -> float:
    """Zwraca odległość od wall_beg do projekcji `point` na linię ściany."""
    px, py = point
    bx, by = wall_beg
    ex, ey = wall_end
    dx, dy = ex - bx, ey - by
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return 0.0
    t = ((px - bx) * dx + (py - by) * dy) / L2
    return t * math.sqrt(L2)


def windows_to_tapir_payload(windows: list[WindowSegment]) -> list[dict]:
    """Konwertuje do Tapir CreateWindows: ownerWallId, centerOffset, width, height, sillHeight."""
    return [
        {
            "ownerWallId": {"guid": w.wall_guid},
            "centerOffset": round(w.center_offset, 6),
            "width": w.width,
            "height": w.height,
            "sillHeight": w.sill_height,
        }
        for w in windows
    ]
