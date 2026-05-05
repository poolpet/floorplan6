"""
Odczyt obrysu mieszkania z ArchiCAD.

Zaznacz ściany obrysu w ArchiCAD → uruchom → dostaniesz Boundary.
"""
from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon, Point, LineString

from bridge.tapir_connection import TapirConnection
from core.models import Boundary, WallType

SEGMENT_TOLERANCE = 0.05  # 5cm tolerancja łączenia segmentów


def read_boundary_from_archicad(
    tapir: Optional[TapirConnection] = None,
) -> tuple[Polygon, tuple[float, float], list[WallType]]:
    """Odczytaj obrys z zaznaczonych ścian w ArchiCAD.

    Wykrywa drzwi wejściowe (Door) wśród zaznaczonych elementów.
    Ściana z drzwiami = INTERNAL, reszta = FACADE.

    Returns:
        (polygon, entry_point, wall_types)
    """
    if tapir is None:
        tapir = TapirConnection()
        tapir.connect()

    # 1. Pobierz zaznaczone elementy
    selected = tapir.get_selected_elements()
    if not selected:
        raise ValueError(
            "Nie zaznaczono żadnych elementów w ArchiCAD.\n\n"
            "Wybierz JEDEN z trybów:\n"
            "  • Zone (auto-wykrywanie): Tools → Zone → metoda Inner Edge → "
            "klik wewnątrz mieszkania → zaznacz Zone\n"
            "  • Ręcznie: zaznacz ściany obrysu mieszkania"
        )

    guids = []
    for elem in selected:
        if isinstance(elem, dict):
            eid = elem.get("elementId", elem)
            guid = eid.get("guid") if isinstance(eid, dict) else str(eid)
        else:
            guid = str(elem)
        guids.append(guid)

    # 2. Pobierz szczegóły elementów
    details = tapir.get_element_details(guids)

    # Tryb "klik wewnątrz": jeśli zaznaczono Zone (utworzoną Inner Edge tool)
    # lub Slab — odczytaj polygon bezpośrednio bez chain-owania ścian.
    for d in details:
        if d.get("type") in ("Zone", "Slab"):
            return _read_boundary_from_zone_or_slab(tapir, d)

    # 3. Rozdziel ściany i drzwi
    segments = []
    wall_guids = []
    door_owner_guid = None

    for detail in details:
        elem_type = detail.get("type", "")

        if elem_type == "Door":
            # Drzwi — znajdź GUID ściany-właściciela
            owner = detail.get("details", {}).get("ownerElementId", {})
            door_owner_guid = owner.get("guid") if isinstance(owner, dict) else None
            continue

        # Ściana
        beg = detail.get("begCoordinate") or detail.get("details", {}).get("begCoordinate")
        end = detail.get("endCoordinate") or detail.get("details", {}).get("endCoordinate")
        if beg and end:
            p1 = (float(beg["x"]), float(beg["y"]))
            p2 = (float(end["x"]), float(end["y"]))
            segments.append((p1, p2))
            # GUID ściany — szukamy w oryginalnych danych
            guid = None
            for g, d in zip(guids, details):
                if d is detail:
                    guid = g
                    break
            wall_guids.append(guid)

    if len(segments) < 3:
        raise ValueError(
            f"Za mało segmentów ścian: {len(segments)}. "
            f"Potrzebuję min. 3 ścian tworzących zamknięty obrys."
        )

    # 4. Złóż segmenty w zamknięty polygon
    polygon_points = _chain_segments(segments)
    polygon = Polygon(polygon_points)

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    # 5. Wykryj drzwi wejściowe
    if door_owner_guid:
        entry_point, wall_types = _detect_entry_from_door(
            polygon_points, segments, wall_guids, door_owner_guid
        )
    else:
        # Fallback: heurystyka (najkrótsza krawędź)
        entry_point, wall_types = _detect_entry_and_wall_types(polygon_points)

    return polygon, entry_point, wall_types


def _read_boundary_from_zone_or_slab(
    tapir: TapirConnection,
    detail: dict,
) -> tuple[Polygon, tuple[float, float], list[WallType]]:
    """Odczyt obrysu z Zone (utworzonej "Inner Edge" tool) lub Slab.

    Auto-detect drzwi i ścian zewnętrznych z całego piętra:
    - Drzwi: każde Door ma `ownerElementId` (GUID ściany). Jeśli ta ściana jest
      na granicy Zone → entry_point = midpoint ściany.
    - Ściany: pobierz wszystkie Wall, filtruj te na granicy Zone, klasyfikuj
      po `compositeIndex` — composite ściany z drzwiami = INTERNAL (klatka),
      inny composite = FACADE.

    Fallback gdy brak drzwi w AC: heurystyka najkrótszej krawędzi.
    """
    inner = detail.get("details", {})
    outline = inner.get("polygonOutline") or inner.get("polygon") or []
    if not outline:
        raise ValueError(
            f"{detail.get('type')} nie ma polygonOutline. Sprawdź czy Zone "
            "została poprawnie utworzona (Tools → Zone → Inner Edge → klik wewnątrz)."
        )

    points = [(float(p["x"]), float(p["y"])) for p in outline]
    if len(points) > 2 and points[0] == points[-1]:
        points = points[:-1]

    # Usuń kolinearne wierzchołki — Tapir Zone z AC może wracać redundant
    # punkty (ślad podziału ścian). _detect_notch wymaga dokładnie 6 lub 8
    # wierzchołków dla L/U-shape, redundant punkty go psują.
    from core.boundary_analyzer import _remove_collinear_vertices
    points = _remove_collinear_vertices(points)

    if len(points) < 3:
        raise ValueError(f"Polygon {detail.get('type')} ma <3 punkty")

    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    # Auto-detect drzwi + ścian na granicy polygon
    entry_point, wall_types = _detect_entry_and_walls_from_archicad(
        tapir, polygon, points
    )
    return polygon, entry_point, wall_types


def _detect_entry_and_walls_from_archicad(
    tapir: TapirConnection,
    polygon: Polygon,
    points: list[tuple[float, float]],
) -> tuple[tuple[float, float], list[WallType]]:
    """Auto-detect entry_point (z drzwi) i wall_types (z composite) dla Zone."""
    n = len(points)

    try:
        all_walls = tapir.get_elements_by_type("Wall")
    except Exception:
        return _detect_entry_and_wall_types(points)
    if not all_walls:
        return _detect_entry_and_wall_types(points)

    def _gid(e):
        if isinstance(e, dict):
            eid = e.get("elementId", e)
            return eid.get("guid") if isinstance(eid, dict) else str(eid)
        return str(e)

    wall_guids = [_gid(w) for w in all_walls]
    wall_details = tapir.get_element_details(wall_guids)

    boundary = polygon.exterior
    boundary_walls = []  # ściany na granicy polygon
    for wd, gid in zip(wall_details, wall_guids):
        beg = wd.get("begCoordinate") or wd.get("details", {}).get("begCoordinate")
        end = wd.get("endCoordinate") or wd.get("details", {}).get("endCoordinate")
        if not beg or not end:
            continue
        bx, by = float(beg["x"]), float(beg["y"])
        ex, ey = float(end["x"]), float(end["y"])
        mx, my = (bx + ex) / 2, (by + ey) / 2
        if boundary.distance(Point(mx, my)) > 0.30:
            continue
        composite = (
            wd.get("details", {}).get("compositeIndex")
            or wd.get("compositeIndex")
            or wd.get("details", {}).get("buildingMaterialIndex")
            or -1
        )
        boundary_walls.append({
            "guid": gid, "midpoint": (mx, my),
            "length": math.hypot(ex - bx, ey - by),
            "composite": composite,
        })

    if not boundary_walls:
        return _detect_entry_and_wall_types(points)

    # Drzwi: znajdź ścianę-właściciela na granicy Zone
    entry_point = None
    door_wall_guid = None
    door_wall_composite = None
    try:
        all_doors = tapir.get_elements_by_type("Door")
    except Exception:
        all_doors = []
    if all_doors:
        door_guids = [_gid(d) for d in all_doors]
        door_details = tapir.get_element_details(door_guids)
        boundary_wall_guids = {w["guid"] for w in boundary_walls}
        for dd in door_details:
            owner = dd.get("details", {}).get("ownerElementId", {})
            owner_gid = owner.get("guid") if isinstance(owner, dict) else None
            if owner_gid and owner_gid in boundary_wall_guids:
                w = next(w for w in boundary_walls if w["guid"] == owner_gid)
                entry_point = w["midpoint"]
                door_wall_guid = owner_gid
                door_wall_composite = w["composite"]
                break

    if entry_point is None:
        # Brak drzwi — fallback heurystyka
        return _detect_entry_and_wall_types(points)

    # Clamp entry_point do granicy polygon — midpoint ściany z drzwiami jest często
    # 12-24cm poza Zone (grubość ściany), co powoduje INFEASIBLE w solverze
    # (entry_y_cm > BH).
    ep = Point(entry_point)
    if not polygon.covers(ep):
        nearest = polygon.exterior.interpolate(polygon.exterior.project(ep))
        entry_point = (nearest.x, nearest.y)
        ep = Point(entry_point)

    # Klasyfikacja krawędzi: krawędź najbliższa entry_point = ściana z drzwiami = INTERNAL,
    # reszta = FACADE.
    closest_edge_idx = min(
        range(n),
        key=lambda i: LineString([points[i], points[(i + 1) % n]]).distance(ep),
    )
    wall_types = [
        WallType.INTERNAL if i == closest_edge_idx else WallType.FACADE
        for i in range(n)
    ]
    return entry_point, wall_types


def _detect_entry_from_door(
    polygon_points: list[tuple[float, float]],
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    wall_guids: list[str],
    door_owner_guid: str,
) -> tuple[tuple[float, float], list[WallType]]:
    """Wykryj entry_point z drzwi ArchiCAD.

    Ściana z drzwiami = INTERNAL, reszta = FACADE.
    Entry point = środek ściany z drzwiami.
    """
    # Znajdź ścianę z drzwiami
    door_wall_idx = None
    for i, guid in enumerate(wall_guids):
        if guid == door_owner_guid:
            door_wall_idx = i
            break

    if door_wall_idx is None:
        # Fallback
        return _detect_entry_and_wall_types(polygon_points)

    door_seg = segments[door_wall_idx]
    entry_point = (
        (door_seg[0][0] + door_seg[1][0]) / 2,
        (door_seg[0][1] + door_seg[1][1]) / 2,
    )

    # Mapuj segmenty na krawędzie polygonu
    n = len(polygon_points)
    wall_types = []
    for i in range(n):
        p1 = polygon_points[i]
        p2 = polygon_points[(i + 1) % n]
        mid_poly = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

        # Sprawdź czy ta krawędź polygonu odpowiada ścianie z drzwiami
        mid_door = entry_point
        dist = math.hypot(mid_poly[0] - mid_door[0], mid_poly[1] - mid_door[1])
        if dist < SEGMENT_TOLERANCE * 10:
            wall_types.append(WallType.INTERNAL)
        else:
            wall_types.append(WallType.FACADE)

    return entry_point, wall_types


def _chain_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[float, float]]:
    """Połącz segmenty w zamknięty polygon przez proximity."""
    if not segments:
        return []

    remaining = list(segments)
    chain = [remaining.pop(0)]

    while remaining:
        last_end = chain[-1][1]
        best_idx = None
        best_dist = float("inf")
        best_reversed = False

        for i, (p1, p2) in enumerate(remaining):
            d1 = math.hypot(last_end[0] - p1[0], last_end[1] - p1[1])
            d2 = math.hypot(last_end[0] - p2[0], last_end[1] - p2[1])
            if d1 < best_dist:
                best_dist = d1
                best_idx = i
                best_reversed = False
            if d2 < best_dist:
                best_dist = d2
                best_idx = i
                best_reversed = True

        if best_dist > SEGMENT_TOLERANCE * 20:
            break  # zbyt daleko — przerwij

        seg = remaining.pop(best_idx)
        if best_reversed:
            seg = (seg[1], seg[0])
        chain.append(seg)

    return [seg[0] for seg in chain]


def _detect_entry_and_wall_types(
    points: list[tuple[float, float]],
) -> tuple[tuple[float, float], list[WallType]]:
    """Wykryj drzwi wejściowe i typy ścian (heurystyka).

    Heurystyka: najkrótsza krawędź = INTERNAL (ściana z sąsiadem / klatką).
    Drzwi wejściowe na środku tej krawędzi.
    """
    n = len(points)
    edges = []
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        edges.append((length, mid, i))

    # Najkrótsza krawędź → INTERNAL (reszta FACADE)
    edges.sort(key=lambda e: e[0])
    shortest_idx = edges[0][2]
    entry_point = edges[0][1]

    wall_types = []
    for i in range(n):
        if i == shortest_idx:
            wall_types.append(WallType.INTERNAL)
        else:
            wall_types.append(WallType.FACADE)

    return entry_point, wall_types
