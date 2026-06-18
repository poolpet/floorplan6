"""
Ekstrakcja drzwi, otworów i orientacja ścian z wygenerowanego rzutu.

Logika zaimportowana z FloorPlan4_CPP/Src/PlanWriter.cpp:createDoorInWall.
F8 z FUNDAMENTAL_RULES.md: pokoje do wewnątrz, łazienki na zewnątrz.

Connection types:
  - "door"       → CreateDoors w Tapir; 0.90 × 2.10m; oblicza opens_inward + hinge
  - "opening"    → CreateDoors w Tapir z wymiarami FP4: (wall_len-thick) × 2.50m,
                   bez skrzydła wizualnie (user otrzymuje wide doorway)
  - "entry_door" → SKIP (drzwi wejściowe są już w AC w fasadzie)

Pozycja: środek ściany (FP4: objLoc = wall_len / 2.0).

Orientacja (F8 — wpływa na DoorSegment.opens_inward, ale Tapir 1.4.0
NIE eksponuje `oSide` ani `reflected` w CreateDoors). Pole `opens_inward`
i `hinge_at_beg` są policzone i zapisane do struktury — gotowe do użycia
gdy dorobimy custom Tapir build lub ModifyDoors z tymi parametrami.
Dziś drzwi w AC otrzymują domyślną orientację — architekt 1-klik flipuje.

Algorytm orientacji (port z C++ FP4):
  norm = (wall_dy, -wall_dx)   # normalna do ściany begC→endC, 90° w prawo
  dot_X = (centroid_X - wall_center) · norm
    dot > 0  → pokój X po "normalnej" stronie
    dot < 0  → po przeciwnej

  Jeśli łazienka (USLUGOWA) wśród room_a/room_b:
    target = hub               # drzwi otwierają się DO huba
  Inaczej (oba zwykłe pokoje, jeden to hub):
    target = pokój zwykły       # drzwi otwierają się DO pokoju

  opens_inward = target po normalnej stronie ściany?

Zawias (port z C++):
  hinge_at_beg = (dist(door_center, wall.begC) >= dist(door_center, wall.endC))
  → skrzydło zawiasem przy bliższym końcu ściany.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from shapely.geometry import Polygon

from core.models import FloorPlan, Room, Strefa
from core.wall_extractor import WallSegment

# Defaultowe wymiary drzwi (m) — typowy lokal mieszkalny PL
DEFAULT_DOOR_WIDTH = 0.90
DEFAULT_DOOR_HEIGHT = 2.10
DEFAULT_DOOR_SILL = 0.0

# Wymiary otworu bez skrzydła (FP4 PlanWriter.cpp:170-171)
OPENING_HEIGHT = 2.50
OPENING_WIDTH_MARGIN = 0.0  # opening width = wall_length - wall_thickness - margin

# Nazwa LibPart "pustego otworu" w bibliotece AC (FP4 PlanWriter.cpp:164).
# Używana w custom Tapir build z parametrem libraryPart w CreateDoors.
OPENING_LIB_PART_NAME = "Otwór drzwiowy, prostokątny"

# Typy adjacency
DOOR = "door"
OPENING = "opening"
ENTRY_DOOR = "entry_door"
SKIPPED_TYPES = (ENTRY_DOOR,)


@dataclass
class DoorSegment:
    """Drzwi (lub otwór) wewnętrzny między dwoma pokojami."""
    wall_guid: str
    center_offset: float                    # m wzdłuż ściany od begC
    width: float = DEFAULT_DOOR_WIDTH
    height: float = DEFAULT_DOOR_HEIGHT
    sill_height: float = DEFAULT_DOOR_SILL

    # Connection type — "door" lub "opening"
    connection_type: str = DOOR

    # Logika F8 (FP4 PlanWriter.cpp). Wykorzystywane przez custom Tapir
    # build z dodatkowymi parametrami oSide/reflected/libraryPart.
    opens_inward: bool = True               # True = drzwi otwierają się DO target
    hinge_at_beg: bool = False              # True = zawias przy begC

    # Tapir custom: parametry przekazywane do CreateDoors
    o_side: bool = False                    # API_OpeningBaseType.oSide
    reflected: bool = False                 # API_OpeningBaseType.reflected
    library_part: str = ""                  # nazwa LibPart, "" = default door

    # Diagnostyka
    room_a: str = ""
    room_b: str = ""
    target_room: str = ""


# Min wspólna krawędź uznawana za przejście (drzwi) — spójne z furniture._infer_door_zones.
DOOR_OPENING_MIN_OVERLAP = 0.90


@dataclass
class DoorOpening:
    """Otwór drzwiowy do RENDERU — wyprowadzony z samej geometrii (sąsiedztwo z komunikacją).

    `axis` = 'v' (pionowa ściana wspólna, otwór wzdłuż y) lub 'h' (pozioma, wzdłuż x).
    `into` = centroid pokoju, do którego drzwi się otwierają (skrzydło/łuk w tę stronę).
    `is_opening` = True → otwarcie bez skrzydła (strefa dzienna↔hol; rysowane jako sam otwór)."""
    room_a: str
    room_b: str
    center: tuple[float, float]
    axis: str
    width: float
    into: tuple[float, float]
    is_opening: bool = False


def _shared_edge_door(a: Room, b: Room) -> Optional[tuple[tuple[float, float], str, float]]:
    """(center, axis, width) REALNEJ wspólnej krawędzi a↔b (boundary∩boundary) ≥ MIN; inaczej None.

    Liczone z rzeczywistych krawędzi (nie z bbox) → poprawne dla L-pokoi (nie stawia drzwi
    na nieistniejącej ścianie we wnęce). Bierze najdłuższy osiowy segment styku."""
    inter = a.polygon.boundary.intersection(b.polygon.boundary)
    if inter.is_empty:
        return None
    if inter.geom_type == "LineString":
        segs = [inter]
    elif inter.geom_type == "MultiLineString":
        segs = list(inter.geoms)
    elif inter.geom_type == "GeometryCollection":
        segs = [g for g in inter.geoms if g.geom_type == "LineString"]
    else:
        return None
    best = None   # (center, axis, width, length)
    for s in segs:
        sx0, sy0, sx1, sy1 = s.bounds
        if abs(sx1 - sx0) < 1e-6:                       # styk pionowy → otwór wzdłuż y
            length = sy1 - sy0
            if length >= DOOR_OPENING_MIN_OVERLAP and (best is None or length > best[3]):
                best = ((sx0, (sy0 + sy1) / 2.0), "v", min(DEFAULT_DOOR_WIDTH, length), length)
        elif abs(sy1 - sy0) < 1e-6:                     # styk poziomy → otwór wzdłuż x
            length = sx1 - sx0
            if length >= DOOR_OPENING_MIN_OVERLAP and (best is None or length > best[3]):
                best = (((sx0 + sx1) / 2.0, sy0), "h", min(DEFAULT_DOOR_WIDTH, length), length)
    if best is None:
        return None
    return (best[0], best[1], best[2])


def infer_door_openings(rooms) -> list[DoorOpening]:
    """Otwory drzwiowe do renderu: REALNA krawędź wspólna pokój↔KOMUNIKACJA (hol/wiatrołap).

    F5: pokoje łączą się przez hol → drzwi są na styku z komunikacją. SCHODY pomijane (routing
    przez hol), para KOMUNIKACJA↔KOMUNIKACJA też (otwarta przestrzeń, bez drzwi). Strefa dzienna↔hol
    oznaczana jako otwarcie (`is_opening`). Pokój USŁUGOWY bez żadnego styku z komunikacją
    (śluzy z sąsiedztw korpusowych S30: kotłownia za garażem, spiżarnia za kuchnią) dostaje
    drzwi do sąsiada z najdłuższą wspólną krawędzią — każde pomieszczenie musi mieć wejście.
    AC-agnostyczne; JEDNO wejście na pokój (hol preferowany — F5; inaczej najdłuższa krawędź)."""
    valid = [r for r in rooms if r.polygon is not None]
    out: list[DoorOpening] = []
    for a in valid:
        if a.spec.strefa == Strefa.KOMUNIKACJA:   # drzwi liczymy od strony POKOJU, nie komunikacji
            continue
        # JEDNO wejście na pokój (reguła Dawida 2026-06-18): spośród sąsiadów-komunikacji
        # wybierz HOL (F5: wszystkie pokoje przez hol); gdy pokój nie dotyka holu —
        # komunikacja z NAJDŁUŻSZĄ wspólną krawędzią. Pokój przy holu I wiatrołapie
        # dostawał dotąd 2 drzwi (per-para), teraz dokładnie jedno.
        candidates = []   # (is_hub, edge_len, b, res)
        for b in valid:
            if b is a or b.spec.strefa != Strefa.KOMUNIKACJA or b.spec.id == "schody":
                continue
            res = _shared_edge_door(a, b)
            if res is None:
                continue
            edge_len = a.polygon.boundary.intersection(b.polygon.boundary).length
            candidates.append((b.spec.id == "hub", edge_len, b, res))
        if not candidates:
            continue
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)  # hol wygrywa, potem najdłuższa krawędź
        _, _, b, res = candidates[0]
        center, axis, width = res
        c = a.polygon.centroid
        out.append(DoorOpening(a.spec.id, b.spec.id, center, axis, width, (c.x, c.y),
                               is_opening=(a.spec.strefa == Strefa.DZIENNA)))

    # Fallback śluzy (S30): usługowy pokój bez drzwi od komunikacji → drzwi do
    # sąsiada z najdłuższą wspólną krawędzią (kotłownia↔garaż, spiżarnia↔kuchnia).
    doored = {d.room_a for d in out}
    pair_done = {frozenset((d.room_a, d.room_b)) for d in out}
    for a in valid:
        if a.spec.strefa != Strefa.USLUGOWA or a.spec.id in doored:
            continue
        best = None
        for b in valid:
            if b is a or b.spec.id == "schody":
                continue
            edge_len = a.polygon.intersection(b.polygon).length
            if edge_len > (best[0] if best else 0.0):
                best = (edge_len, b)
        if best is None or frozenset((a.spec.id, best[1].spec.id)) in pair_done:
            continue
        res = _shared_edge_door(a, best[1])
        if res is None:
            continue
        center, axis, width = res
        c = a.polygon.centroid
        pair_done.add(frozenset((a.spec.id, best[1].spec.id)))
        out.append(DoorOpening(a.spec.id, best[1].spec.id, center, axis, width,
                               (c.x, c.y), is_opening=False))
    return out


def extract_doors(
    plan: FloorPlan,
    wall_to_guid: dict[frozenset, str] | None = None,
    walls: list[WallSegment] | None = None,
    width: float = DEFAULT_DOOR_WIDTH,
    height: float = DEFAULT_DOOR_HEIGHT,
    sill_height: float = DEFAULT_DOOR_SILL,
    wall_thickness: float = 0.10,
) -> list[DoorSegment]:
    """Wyciągnij drzwi/otwory z adjacencies template'u.

    Args:
        plan: Wygenerowany FloorPlan (zawiera template.sasiedztwo).
        wall_to_guid: Mapa {frozenset({room_a_nazwa, room_b_nazwa}): wall_guid}
            zbudowana po CreateWalls.
        walls: Lista WallSegment użyta przy CreateWalls (długość, geometria).
        width, height, sill_height: Wymiary drzwi typu "door".
        wall_thickness: Grubość ściany — używana do liczenia szerokości
            otworu (opening = wall_len - thickness).

    Returns:
        Lista DoorSegment (mix "door" + "opening").
    """
    pair_to_wall: dict[frozenset, WallSegment] = {}
    for w in (walls or []):
        if w.room_a and w.room_b:
            pair_to_wall[frozenset({w.room_a, w.room_b})] = w

    id_to_name = {rs.id: rs.nazwa for rs in plan.template.pokoje}
    name_to_room = {r.spec.nazwa: r for r in plan.rooms}

    doors: list[DoorSegment] = []
    for adj in plan.template.sasiedztwo:
        if adj.connection_type in SKIPPED_TYPES:
            continue
        # Obsługujemy OBA typy: door (ze skrzydłem) i opening (LibPart "pusty otwór").
        # Custom Tapir build z libraryPart pozwala odróżnić w CreateDoors.
        if adj.connection_type not in (DOOR, OPENING):
            continue

        name_a = id_to_name.get(adj.room_a, adj.room_a)
        name_b = id_to_name.get(adj.room_b, adj.room_b)
        key = frozenset({name_a, name_b})

        wall_seg = pair_to_wall.get(key)
        if wall_seg is None:
            continue
        if wall_to_guid is None:           # tryb kontraktu (plan_contract) — bez GUID-ów AC
            wall_guid = ""
        else:
            wall_guid = wall_to_guid.get(key)
            if wall_guid is None:
                continue

        room_a = name_to_room.get(name_a)
        room_b = name_to_room.get(name_b)
        if room_a is None or room_b is None or room_a.polygon is None or room_b.polygon is None:
            continue

        wall_len = wall_seg.length
        if adj.connection_type == OPENING:
            door_width = max(0.3, wall_len - wall_thickness - OPENING_WIDTH_MARGIN)
            door_height = OPENING_HEIGHT
            library_part = OPENING_LIB_PART_NAME
        else:
            door_width = width
            door_height = height
            library_part = ""

        center_offset = wall_len / 2.0
        opens_inward, target_name, hinge_at_beg, o_side, reflected = \
            _compute_orientation(wall_seg, room_a, room_b)

        doors.append(DoorSegment(
            wall_guid=wall_guid,
            center_offset=center_offset,
            width=door_width,
            height=door_height,
            sill_height=sill_height,
            connection_type=adj.connection_type,
            opens_inward=opens_inward,
            hinge_at_beg=hinge_at_beg,
            o_side=o_side,
            reflected=reflected,
            library_part=library_part,
            room_a=name_a,
            room_b=name_b,
            target_room=target_name,
        ))

    return doors


def _compute_orientation(
    wall_seg: WallSegment,
    room_a: Room,
    room_b: Room,
) -> tuple[bool, str, bool, bool, bool]:
    """Logika F8 z FloorPlan4_CPP/Src/PlanWriter.cpp:177-221.

    Zwraca (opens_inward, target_room_name, hinge_at_beg, o_side, reflected).
    o_side i reflected zgodne z FP4: oSide = !target_on_normal_side,
    reflected = (dist_to_beg >= dist_to_end).

    Reguły:
        - Jeśli łazienka (USLUGOWA) wśród room_a/room_b → drzwi otwierają się
          DO HUBA (KOMUNIKACJA) lub do drugiego pokoju.
        - Inaczej (np. hub ↔ sypialnia) → drzwi otwierają się DO POKOJU
          (nie do huba).
        - Bez huba (czysta para pokój-pokój) → drzwi do room_a wg dot product.
        - Zawias: skrzydło w stronę bliższego końca ściany.
    """
    bx, by = wall_seg.p1
    ex, ey = wall_seg.p2
    wall_dx = ex - bx
    wall_dy = ey - by
    # Normalna do ściany (90° w prawo)
    norm_x = wall_dy
    norm_y = -wall_dx

    wall_cx = (bx + ex) / 2.0
    wall_cy = (by + ey) / 2.0

    # Centroidy pokoi
    a_center = room_a.polygon.centroid
    b_center = room_b.polygon.centroid
    dot_a = (a_center.x - wall_cx) * norm_x + (a_center.y - wall_cy) * norm_y
    dot_b = (b_center.x - wall_cx) * norm_x + (b_center.y - wall_cy) * norm_y

    is_bathroom_a = room_a.spec.strefa == Strefa.USLUGOWA
    is_bathroom_b = room_b.spec.strefa == Strefa.USLUGOWA
    is_hub_a = room_a.spec.strefa == Strefa.KOMUNIKACJA
    is_hub_b = room_b.spec.strefa == Strefa.KOMUNIKACJA

    # Wybór: który pokój jest "celem" otwarcia drzwi (FP4 lines 200-213)
    if is_bathroom_a or is_bathroom_b:
        # Łazienka → drzwi otwierają się NA ZEWNĄTRZ (do huba/drugiego pokoju)
        if is_hub_a:
            target_dot = dot_a
            target_name = room_a.spec.nazwa
        elif is_hub_b:
            target_dot = dot_b
            target_name = room_b.spec.nazwa
        elif is_bathroom_a:
            # bez huba: drzwi otwierają się do room_b (nie do łazienki)
            target_dot = dot_b
            target_name = room_b.spec.nazwa
        else:
            target_dot = dot_a
            target_name = room_a.spec.nazwa
    else:
        # Bez łazienki — drzwi otwierają się DO POKOJU (nie do huba)
        if is_hub_a:
            target_dot = dot_b
            target_name = room_b.spec.nazwa
        elif is_hub_b:
            target_dot = dot_a
            target_name = room_a.spec.nazwa
        else:
            # para pokój ↔ pokój — wybór dowolny (room_a jako default)
            target_dot = dot_a
            target_name = room_a.spec.nazwa

    target_on_normal_side = target_dot > 0
    opens_inward = True   # zawsze chcemy żeby drzwi się otwierały DO target (F8)

    # FP4 line 214: oSide = !target_on_normal_side
    # Tapir custom build przekazuje to bezpośrednio do API_OpeningBaseType.oSide
    o_side = not target_on_normal_side

    # Zawias: skrzydło w stronę bliższego końca ściany (FP4 lines 217-221).
    # Drzwi centrowane → dist_to_beg == dist_to_end → reflected=False (default).
    door_x = wall_cx
    door_y = wall_cy
    dist_to_beg = math.hypot(door_x - bx, door_y - by)
    dist_to_end = math.hypot(door_x - ex, door_y - ey)
    reflected = dist_to_beg >= dist_to_end
    hinge_at_beg = dist_to_beg < dist_to_end

    return opens_inward, target_name, hinge_at_beg, o_side, reflected


@dataclass
class OpeningSegment:
    """Pusty otwór w ścianie (bez skrzydła) — np. między hubem a salonem.
    Używany przez Tapir CreateOpenings (NIE CreateDoors)."""
    wall_guid: str
    base_point: tuple[float, float, float]  # (x, y, z) — dolny lewy róg otworu
    width: float
    height: float
    # Diagnostyka
    room_a: str = ""
    room_b: str = ""


def _pick_target_room_name(room_a: Room, room_b: Room) -> str:
    """F8: który pokój jest 'targetem' (drzwi się DO niego otwierają).

    - Łazienka (USLUGOWA) wśród → target = hub/drugi pokój (drzwi się otwierają
      NA ZEWNĄTRZ z łazienki)
    - Inaczej (hub ↔ pokój) → target = pokój (drzwi DO pokoju)
    - Para pokój ↔ pokój bez huba/łazienki → target = room_a (default)
    """
    is_bathroom_a = room_a.spec.strefa == Strefa.USLUGOWA
    is_bathroom_b = room_b.spec.strefa == Strefa.USLUGOWA
    is_hub_a = room_a.spec.strefa == Strefa.KOMUNIKACJA
    is_hub_b = room_b.spec.strefa == Strefa.KOMUNIKACJA

    if is_bathroom_a or is_bathroom_b:
        if is_hub_a:
            return room_a.spec.nazwa
        if is_hub_b:
            return room_b.spec.nazwa
        if is_bathroom_a:
            return room_b.spec.nazwa
        return room_a.spec.nazwa
    else:
        if is_hub_a:
            return room_b.spec.nazwa
        if is_hub_b:
            return room_a.spec.nazwa
        return room_a.spec.nazwa


def orient_walls_for_doors(
    walls: list[WallSegment],
    plan: FloorPlan,
) -> None:
    """Flip kierunku ścian (p1 ↔ p2) tak żeby Tapir default oSide=false dawał
    drzwi otwierające się DO TARGET ROOM (F8).

    Algorytm (per ściana z drzwiami):
      norm = (wall_dy, -wall_dx)   # 90° w prawo od p1 → p2
      dot = (target_centroid - wall_center) · norm
      Jeśli dot < 0 (target po anty-normalnej stronie) → flip ścianę.

    Po flip: normal wskazuje na target → AC default oSide=false otworzy
    drzwi w stronę target (= F8 reguła).

    Args:
        walls: Lista WallSegment z extract_internal_walls. **Modyfikowana
            in-place** (zmiany p1/p2).
        plan: FloorPlan ze strefami pokoi (Room.spec.strefa) i adjacencies.
    """
    name_to_room = {r.spec.nazwa: r for r in plan.rooms}
    id_to_name = {rs.id: rs.nazwa for rs in plan.template.pokoje}

    # Zbuduj target_name per parę pokoi mająca adjacency
    pair_to_target_name: dict[frozenset, str] = {}
    for adj in plan.template.sasiedztwo:
        # Bierzemy zarówno "door" jak "opening" — w przypadku opening
        # orientacja ściany nie ma znaczenia (brak skrzydła), ale flip
        # niczego nie zepsuje.
        if adj.connection_type == ENTRY_DOOR:
            continue
        name_a = id_to_name.get(adj.room_a, adj.room_a)
        name_b = id_to_name.get(adj.room_b, adj.room_b)
        room_a = name_to_room.get(name_a)
        room_b = name_to_room.get(name_b)
        if room_a is None or room_b is None:
            continue
        target = _pick_target_room_name(room_a, room_b)
        pair_to_target_name[frozenset({name_a, name_b})] = target

    # Flip ściany
    for w in walls:
        if not w.room_a or not w.room_b:
            continue
        key = frozenset({w.room_a, w.room_b})
        target_name = pair_to_target_name.get(key)
        if not target_name:
            continue
        target_room = name_to_room.get(target_name)
        if target_room is None or target_room.polygon is None:
            continue

        bx, by = w.p1
        ex, ey = w.p2
        norm_x = ey - by   # = wall_dy
        norm_y = bx - ex   # = -wall_dx
        c = target_room.polygon.centroid
        wcx = (bx + ex) / 2.0
        wcy = (by + ey) / 2.0
        dot = (c.x - wcx) * norm_x + (c.y - wcy) * norm_y

        if dot < 0:
            # Normal aktualnie wskazuje OD target → flip kierunek ściany
            w.p1, w.p2 = w.p2, w.p1


def extract_openings(
    plan: FloorPlan,
    wall_to_guid: dict[frozenset, str],
    walls: list[WallSegment],
    wall_thickness: float = 0.10,
    height: float = OPENING_HEIGHT,
) -> list[OpeningSegment]:
    """Wyciągnij otwory (bez skrzydła) z adjacencies type='opening'.

    Tapir 1.4.0 CreateOpenings wymaga: ownerElementId, basePoint (3D).
    basePoint = dolny lewy róg otworu w globalnych współrzędnych 3D.
    Liczymy go jako pozycję wzdłuż ściany od p1, gdzie zaczyna się otwór.
    """
    pair_to_wall: dict[frozenset, WallSegment] = {}
    for w in walls:
        if w.room_a and w.room_b:
            pair_to_wall[frozenset({w.room_a, w.room_b})] = w

    id_to_name = {rs.id: rs.nazwa for rs in plan.template.pokoje}

    openings: list[OpeningSegment] = []
    for adj in plan.template.sasiedztwo:
        if adj.connection_type != OPENING:
            continue

        name_a = id_to_name.get(adj.room_a, adj.room_a)
        name_b = id_to_name.get(adj.room_b, adj.room_b)
        key = frozenset({name_a, name_b})

        wall_guid = wall_to_guid.get(key)
        wall_seg = pair_to_wall.get(key)
        if wall_guid is None or wall_seg is None:
            continue

        wall_len = wall_seg.length
        opening_width = max(0.3, wall_len - wall_thickness - OPENING_WIDTH_MARGIN)

        # base_point = dolny lewy róg otworu wzdłuż ściany od wall.p1
        # Pozycja na środku ściany: start od ((wall_len - opening_width) / 2)
        bx, by = wall_seg.p1
        ex, ey = wall_seg.p2
        if wall_len < 1e-6:
            continue
        ux = (ex - bx) / wall_len
        uy = (ey - by) / wall_len
        start_offset = (wall_len - opening_width) / 2.0
        bp_x = bx + start_offset * ux
        bp_y = by + start_offset * uy
        bp_z = 0.0  # od podłogi

        openings.append(OpeningSegment(
            wall_guid=wall_guid,
            base_point=(bp_x, bp_y, bp_z),
            width=opening_width,
            height=height,
            room_a=name_a,
            room_b=name_b,
        ))

    return openings


def openings_to_tapir_payload(openings: list[OpeningSegment]) -> list[dict]:
    """Format Tapir CreateOpenings: ownerElementId, basePoint (3D), width, height."""
    return [
        {
            "ownerElementId": {"guid": o.wall_guid},
            "basePoint": {
                "x": round(o.base_point[0], 6),
                "y": round(o.base_point[1], 6),
                "z": round(o.base_point[2], 6),
            },
            "width": o.width,
            "height": o.height,
        }
        for o in openings
    ]


def doors_to_tapir_payload(doors: list[DoorSegment]) -> list[dict]:
    """Konwertuje do formatu Tapir CreateDoors (custom FP6 build).

    Pola standardowe (Tapir 1.4.0):
        ownerWallId, centerOffset, width, height, sillHeight
    Pola dodane w custom build (TapirAddOn_AC29_Mac.bundle z FP6):
        libraryPart: string — np. "Otwór drzwiowy, prostokątny" (pusty otwór)
        oSide:       bool   — kierunek otwarcia (F8)
        reflected:   bool   — strona zawiasu (mirror skrzydła)

    Pole libraryPart="" pomijamy (default LibPart).
    """
    out = []
    for d in doors:
        payload = {
            "ownerWallId": {"guid": d.wall_guid},
            "centerOffset": round(d.center_offset, 6),
            "width": d.width,
            "height": d.height,
            "sillHeight": d.sill_height,
            "oSide": d.o_side,
            "reflected": d.reflected,
        }
        if d.library_part:
            payload["libraryPart"] = d.library_part
        out.append(payload)
    return out
