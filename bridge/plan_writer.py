"""
Eksport wygenerowanego rzutu do ArchiCAD jako strefy + ściany działowe + drzwi.

V1 (Tapir 1.4.0): CreateZones + CreateWalls
V2 (Tapir 1.4.0): + CreateDoors (drzwi wewnętrzne z template.sasiedztwo)
    - strefy (zones) = każdy pokój jako Zone z nazwą
    - ściany (walls) = wspólne krawędzie między pokojami (ścianki działowe)
    - drzwi (doors)  = dla każdego AdjacencyRule(type="door") drzwi w środku
                       wspólnej ściany działowej
"""
from __future__ import annotations

import uuid
from typing import Optional

from core.models import FloorPlan
from core.wall_extractor import (
    DEFAULT_WALL_HEIGHT_M,
    DEFAULT_WALL_THICKNESS_M,
    extract_internal_walls,
    walls_to_tapir_payload,
)
from core.door_extractor import (
    DEFAULT_DOOR_HEIGHT,
    DEFAULT_DOOR_WIDTH,
    extract_doors,
    doors_to_tapir_payload,
)
from core.label_extractor import (
    extract_labels,
    labels_to_tapir_payload,
)
from core.window_extractor import (
    extract_windows,
    windows_to_tapir_payload,
)
from core.furniture import furnish_rooms
from core.furniture_extractor import (
    extract_furniture,
    furniture_to_create_payload,
    furniture_to_gdl_payload,
)
from bridge.tapir_connection import TapirConnection


def export_plan_to_archicad(
    plan: FloorPlan,
    tapir: Optional[TapirConnection] = None,
    offset: tuple[float, float] = (0.0, 0.0),
    include_walls: bool = True,
    include_doors: bool = True,
    wall_height: float = DEFAULT_WALL_HEIGHT_M,
    wall_thickness: float = DEFAULT_WALL_THICKNESS_M,
    door_width: float = DEFAULT_DOOR_WIDTH,
    door_height: float = DEFAULT_DOOR_HEIGHT,
    zone_inset: Optional[float] = None,  # NOT USED in V2.4+ (auto-fill via referencePosition).
    include_labels: bool = True,
    include_windows: bool = True,
    include_furniture: bool = True,
    apartment_id: Optional[str] = None,
) -> dict[str, list[str]]:
    """Wyeksportuj rzut jako strefy + ścianki działowe + drzwi do ArchiCAD.

    Pipeline:
        1. CreateZones → strefy z nazwami pokoi
        2. CreateWalls → ścianki działowe między pokojami (V1)
        3. CreateDoors → drzwi w środku ścian między pokojami z
           adjacency type="door" (V2). Pomija "entry_door" i "opening".

    Args:
        plan: Wygenerowany rzut.
        tapir: Połączenie Tapir (opcjonalne).
        offset: Przesunięcie (x, y) w metrach — pozycja obrysu w ArchiCAD.
        include_walls: Czy generować ścianki działowe (V1).
        include_doors: Czy generować drzwi wewnętrzne (V2). Wymaga include_walls.
        wall_height, wall_thickness: Parametry ścianek działowych.
        door_width, door_height: Parametry drzwi.

    Returns:
        Dict z kluczami:
            zones: list GUID-ów utworzonych Zone
            walls: list GUID-ów utworzonych Wall (pusty jeśli include_walls=False)
            doors: list GUID-ów utworzonych Door (pusty jeśli include_doors=False)
    """
    if tapir is None:
        tapir = TapirConnection()
        tapir.connect()

    ox, oy = offset

    # Apartment ID — unikalne dla każdego mieszkania w projekcie AC.
    # Pozwala zestawiać zone w schedule AC po prefixie ("M3-A5F2-001",
    # "M3-A5F2-002", ...). Domyślnie: {typ_mieszkania}-{krótki UUID hex}.
    if apartment_id is None:
        apartment_id = f"{plan.template.typ_mieszkania}-{uuid.uuid4().hex[:4].upper()}"

    # ─────── 1. Ścianki działowe NAJPIERW (closed cells dla auto-zone) ───────
    wall_guids: list[str] = []
    wall_to_guid: dict = {}     # {frozenset({room_a, room_b}): wall_guid}
    walls: list = []

    if include_walls:
        walls = extract_internal_walls(
            plan, height=wall_height, thickness=wall_thickness,
        )

        # SNAP endpointow scianek do boundary mieszkania (lub innej scianki
        # dzialowej jesli krzyzowanie). Eliminuje szczeliny przez ktore strefy
        # "wyciekaja", bez wydluzania scian poza polygon mieszkania.
        #
        # Dla kazdego endpointa kazdej scianki:
        #   1. Znajdz najblizszy punkt na boundary mieszkania.
        #   2. Znajdz najblizsze punkty na innych sciankach dzialowych.
        #   3. Wybierz najblizszy z kandydatow (jesli w tolerancji).
        #   4. Snap endpoint dokladnie do tego punktu.
        from shapely.geometry import Point as _Point, LineString as _LS
        SNAP_TOL = 0.30  # 30cm
        boundary_line = plan.boundary.polygon.exterior
        wall_lines_data = [(w, _LS([w.p1, w.p2])) for w in walls]

        for w in walls:
            new_endpoints = []
            for endpoint in (w.p1, w.p2):
                pt = _Point(endpoint)
                best_pt = endpoint
                best_dist = SNAP_TOL  # nic gorszego niz tolerancja nie zaakceptujemy

                # 1. Boundary mieszkania
                bp = boundary_line.interpolate(boundary_line.project(pt))
                bdist = pt.distance(bp)
                if bdist < best_dist:
                    best_pt = (bp.x, bp.y)
                    best_dist = bdist

                # 2. Inne scianki dzialowe (poza ta sama)
                for other_w, other_line in wall_lines_data:
                    if other_w is w:
                        continue
                    op = other_line.interpolate(other_line.project(pt))
                    odist = pt.distance(op)
                    if odist < best_dist:
                        best_pt = (op.x, op.y)
                        best_dist = odist

                new_endpoints.append(best_pt)

            w.p1, w.p2 = new_endpoints[0], new_endpoints[1]

        walls_payload = walls_to_tapir_payload(walls)
        for w in walls_payload:
            w["begCoordinate"]["x"] = round(w["begCoordinate"]["x"] + ox, 6)
            w["begCoordinate"]["y"] = round(w["begCoordinate"]["y"] + oy, 6)
            w["endCoordinate"]["x"] = round(w["endCoordinate"]["x"] + ox, 6)
            w["endCoordinate"]["y"] = round(w["endCoordinate"]["y"] + oy, 6)

        wall_guids = tapir.create_walls(walls_payload)

        for wall_seg, guid in zip(walls, wall_guids):
            if wall_seg.room_a and wall_seg.room_b and guid:
                key = frozenset({wall_seg.room_a, wall_seg.room_b})
                wall_to_guid[key] = guid

    # ─────── 2. Strefy via referencePosition (AC auto-fill, jak Inner Edge) ───────
    # Po CreateWalls każdy pokój jest zamkniętą celką (boundary user'a + nasze
    # ścianki). Wskazujemy centroid pokoju → AC sam wykrywa obrys zamknięty
    # między ścianami, idealnie do ich wewnętrznej krawędzi (nie pod ścianami).
    zones_data = []
    for i, room in enumerate(plan.rooms):
        if room.polygon is None:
            continue

        geom = room.polygon
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        centroid = geom.centroid

        # Unikalne numberStr per pokój: "M3-A5F2-001" → zestawianie w AC schedule
        zone_number = f"{apartment_id}-{i + 1:03d}"
        zones_data.append({
            "name": room.spec.nazwa,
            "numberStr": zone_number,
            "geometry": {
                "referencePosition": {
                    "x": round(centroid.x + ox, 4),
                    "y": round(centroid.y + oy, 4),
                }
            },
        })

    if not zones_data:
        raise ValueError("Brak pokoi z geometrią do wyeksportowania")

    zone_guids = tapir.create_zones(zones_data)

    # ─────── 3. Drzwi + otwory (V2.3 — custom Tapir build) ───────
    # Z custom buildem CreateDoors akceptuje libraryPart="Otwór drzwiowy,
    # prostokątny" dla connection_type="opening" + oSide/reflected dla F8.
    # Wszystko leci przez jeden CreateDoors — bez osobnego CreateOpenings.
    door_guids: list[str] = []
    if include_doors and include_walls and wall_to_guid:
        doors = extract_doors(
            plan, wall_to_guid, walls,
            width=door_width, height=door_height,
            wall_thickness=wall_thickness,
        )
        doors_payload = doors_to_tapir_payload(doors)
        door_guids = tapir.create_doors(doors_payload)

    # ─────── 4. Etykiety pokoi (V3 — Tapir 1.4.0 CreateLabels) ───────
    label_guids: list[str] = []
    if include_labels and zone_guids:
        labels = extract_labels(plan, zone_guids=zone_guids)
        labels_payload = labels_to_tapir_payload(labels)
        for lbl in labels_payload:
            lbl["begCoordinate"]["x"] = round(lbl["begCoordinate"]["x"] + ox, 6)
            lbl["begCoordinate"]["y"] = round(lbl["begCoordinate"]["y"] + oy, 6)
        label_guids = tapir.create_labels(labels_payload)

    # ─────── 5. Okna fasadowe (V4 — Tapir 1.4.0 CreateWindows) ───────
    # Pobieramy istniejące ściany AC (boundary user'a) — to do nich
    # podpinamy okna. Matchujemy facade edges pokoju do AC walls.
    # Pokoje są w local coords plan; offset stosowany BEZ zmiany ac_walls
    # (które są już w world coords).
    window_guids: list[str] = []
    if include_windows:
        rooms_need_window = [r for r in plan.rooms
                             if r.polygon is not None and r.spec.wymaga_okna]
        print(f"[V4 windows] {len(rooms_need_window)} pokoi wymagających okna: "
              f"{[r.spec.nazwa for r in rooms_need_window]}")

        if rooms_need_window:
            try:
                ac_walls_summary = tapir.get_all_walls()
                print(f"[V4 windows] AC walls summary count: {len(ac_walls_summary)}")
                ac_wall_guids = []
                for w in ac_walls_summary:
                    if isinstance(w, dict):
                        eid = w.get("elementId", w)
                        guid = eid.get("guid") if isinstance(eid, dict) else None
                        if guid:
                            ac_wall_guids.append(guid)
                print(f"[V4 windows] AC wall GUIDs: {len(ac_wall_guids)}")

                ac_walls = tapir.get_element_details(ac_wall_guids) if ac_wall_guids else []
                for guid, d in zip(ac_wall_guids, ac_walls):
                    if isinstance(d, dict):
                        d["_guid"] = guid

                # Debug: pokaż pierwsze 3 ściany
                for d in ac_walls[:3]:
                    if isinstance(d, dict):
                        det = d.get("details", {})
                        beg = det.get("begCoordinate") or d.get("begCoordinate")
                        end = det.get("endCoordinate") or d.get("endCoordinate")
                        print(f"  AC wall {d.get('_guid','?')[:8]}.. type={d.get('type','?')} "
                              f"beg={beg} end={end}")
            except Exception as e:
                print(f"[V4 windows] EXCEPTION fetch walls: {e}")
                ac_walls = []

            if ac_walls:
                ac_walls_local = []
                for d in ac_walls:
                    if not isinstance(d, dict):
                        continue
                    d2 = dict(d)
                    details = dict(d2.get("details", {}))
                    beg = details.get("begCoordinate") or d2.get("begCoordinate")
                    end = details.get("endCoordinate") or d2.get("endCoordinate")
                    if beg and end:
                        details["begCoordinate"] = {
                            "x": float(beg["x"]) - ox,
                            "y": float(beg["y"]) - oy,
                        }
                        details["endCoordinate"] = {
                            "x": float(end["x"]) - ox,
                            "y": float(end["y"]) - oy,
                        }
                        d2["details"] = details
                        ac_walls_local.append(d2)
                print(f"[V4 windows] AC walls with beg/end coords: {len(ac_walls_local)}")

                windows = extract_windows(plan, ac_walls_local)
                print(f"[V4 windows] extract_windows zwrócił {len(windows)} kandydatów")
                for w in windows:
                    print(f"  - {w.room_name}: wall={w.wall_guid[:8]}.., "
                          f"centerOffset={w.center_offset:.2f}, "
                          f"{w.width:.2f}×{w.height:.2f}m")
                windows_payload = windows_to_tapir_payload(windows)
                if windows_payload:
                    try:
                        raw = tapir._execute_tapir("CreateWindows",
                                                    {"windowsData": windows_payload})
                        print(f"[V4 windows] CreateWindows raw response: {str(raw)[:300]}")
                        window_guids = tapir._extract_guids(raw)
                    except Exception as e:
                        print(f"[V4 windows] CreateWindows EXCEPTION: {e}")

    # ─────── 6. Meble jako obiekty biblioteczne (V6 — CreateObjects + SetGDL A/B) ───────
    # FurnishResult → obiekty biblioteczne AC (wybór Dawida). Kotwica = lewy-dolny róg
    # boxa; offset jak ściany/etykiety (współrzędne absolutne). Rozmiar: NIE przez
    # dimensions (AC czyta je jako mnożnik, nie metry — źródło Tapira), tylko 2-krokowo:
    # CreateObjects (rozmiar domyślny) → SetGDLParametersOfElements A/B w metrach.
    # Kuchnia = rozbita na pojedyncze moduły (lodówka+szafki) w extract_furniture.
    object_guids: list[str] = []
    if include_furniture:
        try:
            fr = furnish_rooms(plan.rooms, boundary=plan.boundary)
        except Exception:
            fr = furnish_rooms(plan.rooms)  # back-compat fallback (bez świadomości okien)
        furn_objects = extract_furniture(fr, plan.rooms)
        create_payload = furniture_to_create_payload(furn_objects, offset=(ox, oy))
        print(f"[V6 furniture] {len(create_payload)} obiektów do wstawienia")
        if create_payload:
            object_guids = tapir.create_objects(create_payload)
            gdl_payload = furniture_to_gdl_payload(furn_objects, object_guids)
            if gdl_payload:
                tapir.set_gdl_parameters(gdl_payload)
            print(f"[V6 furniture] wstawiono {len(object_guids)} obiektów, "
                  f"A/B ustawione dla {len(gdl_payload)}")

    return {
        "zones": zone_guids,
        "walls": wall_guids,
        "doors": door_guids,
        "openings": [],
        "labels": label_guids,
        "windows": window_guids,
        "furniture": object_guids,
        "apartment_id": apartment_id,  # dla diagnostyki / zestawiania
    }
