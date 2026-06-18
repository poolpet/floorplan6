"""
Testy door_extractor — generacja drzwi z adjacencies template'u (V2).

Sprawdza:
  1. Adjacency type="door" + wspólna ściana → 1 DoorSegment z center_offset=L/2
  2. Adjacency type="entry_door" → pomijane (są już w AC)
  3. Adjacency type="opening" → pomijane (V2 MVP nie obsługuje)
  4. Adjacency dla par bez wspólnej ściany → pomijane bez błędu
  5. payload Tapir — wymagane pola obecne (ownerWallId, centerOffset)
  6. Empty plan → empty doors
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from core.door_extractor import (
    DEFAULT_DOOR_HEIGHT,
    DEFAULT_DOOR_WIDTH,
    OPENING_HEIGHT,
    DoorSegment,
    OpeningSegment,
    doors_to_tapir_payload,
    extract_doors,
    extract_openings,
    openings_to_tapir_payload,
    orient_walls_for_doors,
)
from core.models import (
    AdjacencyRule,
    Boundary,
    EdgeInfo,
    FloorPlan,
    Orientation,
    Room,
    RoomSpec,
    Strefa,
    Template,
    WallType,
)
from core.wall_extractor import WallSegment


def _room(
    room_id: str,
    nazwa: str,
    polygon: Polygon,
    strefa: Strefa = Strefa.DZIENNA,
) -> Room:
    spec = RoomSpec(
        id=room_id, nazwa=nazwa, strefa=strefa,
        wymaga_okna=False, priorytet_fasady=None,
    )
    r = Room(spec=spec, polygon=polygon)
    r.update_metrics()
    return r


def _plan(rooms: list[Room], adjacencies: list[AdjacencyRule]) -> FloorPlan:
    poly = box(0, 0, 20, 20)
    boundary = Boundary(
        polygon=poly,
        edges=[EdgeInfo(start=(0, 0), end=(20, 0),
                        wall_type=WallType.FACADE, orientation=Orientation.S)],
        entry_point=(10.0, 0.0),
    )
    template = Template(
        id="t", nazwa="test", typ_mieszkania="M2",
        pokoje=[r.spec for r in rooms],
        sasiedztwo=adjacencies,
    )
    return FloorPlan(boundary=boundary, template=template, rooms=rooms)


# ============================================================================
# Test 1: 2 pokoje, 1 ściana, adjacency type="door" → 1 drzwi
# ============================================================================
def test_door_between_two_rooms():
    room_a = _room("salon", "Salon", box(0, 0, 5, 5))
    room_b = _room("kuchnia", "Kuchnia", box(5, 0, 10, 5))
    adj = AdjacencyRule(room_a="salon", room_b="kuchnia", connection_type="door")
    plan = _plan([room_a, room_b], [adj])

    # Symuluj wynik wall_extractor + create_walls
    wall = WallSegment(
        p1=(5.0, 0.0), p2=(5.0, 5.0),
        room_a="Salon", room_b="Kuchnia",
    )
    wall_to_guid = {frozenset({"Salon", "Kuchnia"}): "wall-guid-1"}

    doors = extract_doors(plan, wall_to_guid, [wall])

    assert len(doors) == 1
    d = doors[0]
    assert d.wall_guid == "wall-guid-1"
    assert d.center_offset == pytest.approx(2.5, abs=0.01)  # ściana 5m → środek 2.5m
    assert d.width == DEFAULT_DOOR_WIDTH
    assert d.height == DEFAULT_DOOR_HEIGHT
    assert {d.room_a, d.room_b} == {"Salon", "Kuchnia"}


# ============================================================================
# Test 2: entry_door pomijany (są już w AC)
# ============================================================================
def test_entry_door_skipped():
    room_a = _room("hall", "Hall", box(0, 0, 5, 5))
    room_b = _room("salon", "Salon", box(5, 0, 10, 5))
    adj = AdjacencyRule(room_a="hall", room_b="salon", connection_type="entry_door")
    plan = _plan([room_a, room_b], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hall", room_b="Salon")
    wall_to_guid = {frozenset({"Hall", "Salon"}): "guid-1"}

    doors = extract_doors(plan, wall_to_guid, [wall])
    assert doors == []


# ============================================================================
# Test 3: opening — NIE wchodzi do extract_doors (obsługiwany przez extract_openings)
# ============================================================================
def test_opening_handled_as_door_with_library_part():
    """connection_type='opening' → DoorSegment z library_part='Otwór drzwiowy, prostokątny'."""
    room_a = _room("salon", "Salon", box(0, 0, 5, 5))
    room_b = _room("kuchnia", "Kuchnia", box(5, 0, 10, 5))
    adj = AdjacencyRule(room_a="salon", room_b="kuchnia", connection_type="opening")
    plan = _plan([room_a, room_b], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Salon", room_b="Kuchnia")
    wall_to_guid = {frozenset({"Salon", "Kuchnia"}): "guid-1"}

    doors = extract_doors(plan, wall_to_guid, [wall], wall_thickness=0.10)
    assert len(doors) == 1
    d = doors[0]
    assert d.connection_type == "opening"
    assert d.library_part == "Otwór drzwiowy, prostokątny"
    # FP4: opening width = wall_len - thick = 5.0 - 0.10 = 4.90
    assert d.width == pytest.approx(4.90, abs=0.01)
    assert d.height == pytest.approx(2.50, abs=0.01)


# ============================================================================
# Test 4: adjacency dla pokoi bez wspólnej ściany → skip (no error)
# ============================================================================
def test_adjacency_without_shared_wall_skipped():
    """Solver dał układ inny niż template adjacency oczekiwał — bez błędu."""
    room_a = _room("salon", "Salon", box(0, 0, 5, 5))
    room_b = _room("sypialnia", "Sypialnia", box(10, 0, 15, 5))  # daleko!
    adj = AdjacencyRule(room_a="salon", room_b="sypialnia", connection_type="door")
    plan = _plan([room_a, room_b], [adj])

    # Brak wspólnej ściany (pokoje izolowane) → wall_to_guid pusty
    wall_to_guid: dict = {}

    doors = extract_doors(plan, wall_to_guid, [])
    assert doors == []  # bez błędu, po prostu pomijamy


# ============================================================================
# Test 5: payload Tapir — wymagane pola
# ============================================================================
def test_tapir_payload_has_required_fields():
    doors = [DoorSegment(wall_guid="g1", center_offset=1.25)]
    payload = doors_to_tapir_payload(doors)

    assert len(payload) == 1
    p = payload[0]
    assert "ownerWallId" in p
    assert p["ownerWallId"] == {"guid": "g1"}
    assert "centerOffset" in p
    assert p["centerOffset"] == 1.25
    # width/height/sillHeight są opcjonalne ale my zawsze dajemy
    assert p["width"] > 0
    assert p["height"] > 0
    assert p["sillHeight"] >= 0


# ============================================================================
# Test 6: empty
# ============================================================================
def test_empty_inputs():
    plan = _plan([], [])
    assert extract_doors(plan, {}, []) == []
    assert doors_to_tapir_payload([]) == []


# ============================================================================
# Test 7: M3 style — hub + 3 sypialnie → 3 drzwi
# ============================================================================
def test_m3_hub_with_three_bedrooms():
    """Hub łączy się z 3 sypialniami → 3 drzwi (1 per sypialnia)."""
    hub = _room("hub", "Hub", box(2, 2, 8, 4))  # 6x2
    bed1 = _room("syp1", "Sypialnia 1", box(0, 4, 4, 8))   # góra-lewo
    bed2 = _room("syp2", "Sypialnia 2", box(4, 4, 8, 8))   # góra-prawo
    bed3 = _room("syp3", "Sypialnia 3", box(2, 0, 8, 2))   # dół

    adjs = [
        AdjacencyRule("hub", "syp1", "door"),
        AdjacencyRule("hub", "syp2", "door"),
        AdjacencyRule("hub", "syp3", "door"),
    ]
    plan = _plan([hub, bed1, bed2, bed3], adjs)

    walls = [
        WallSegment(p1=(2, 4), p2=(4, 4), room_a="Hub", room_b="Sypialnia 1"),
        WallSegment(p1=(4, 4), p2=(8, 4), room_a="Hub", room_b="Sypialnia 2"),
        WallSegment(p1=(2, 2), p2=(8, 2), room_a="Hub", room_b="Sypialnia 3"),
    ]
    wall_to_guid = {
        frozenset({"Hub", "Sypialnia 1"}): "guid-1",
        frozenset({"Hub", "Sypialnia 2"}): "guid-2",
        frozenset({"Hub", "Sypialnia 3"}): "guid-3",
    }

    doors = extract_doors(plan, wall_to_guid, walls)

    assert len(doors) == 3
    guids = {d.wall_guid for d in doors}
    assert guids == {"guid-1", "guid-2", "guid-3"}


# ============================================================================
# Test 8 (F8): drzwi do łazienki — target = hub (otwiera się do huba)
# ============================================================================
def test_f8_bathroom_door_opens_toward_hub():
    """Łazienka ↔ hub → target_room = hub (drzwi otwierają się NA ZEWNĄTRZ
    z łazienki = DO huba)."""
    hub = _room("hub", "Hub", box(0, 0, 5, 5), strefa=Strefa.KOMUNIKACJA)
    bath = _room("lazienka", "Łazienka", box(5, 0, 8, 5), strefa=Strefa.USLUGOWA)
    adj = AdjacencyRule(room_a="hub", room_b="lazienka", connection_type="door")
    plan = _plan([hub, bath], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hub", room_b="Łazienka")
    wall_to_guid = {frozenset({"Hub", "Łazienka"}): "g1"}

    doors = extract_doors(plan, wall_to_guid, [wall])
    assert len(doors) == 1
    d = doors[0]
    # F8: drzwi do łazienki → cel = hub (otwierają się DO huba)
    assert d.target_room == "Hub"


# ============================================================================
# Test 9 (F8): drzwi pokój ↔ hub → target = pokój (otwiera się do pokoju)
# ============================================================================
def test_f8_room_door_opens_toward_room():
    """Hub ↔ sypialnia (DZIENNA) → target = sypialnia (drzwi otwierają się
    DO pokoju, nie do huba)."""
    hub = _room("hub", "Hub", box(0, 0, 5, 5), strefa=Strefa.KOMUNIKACJA)
    bed = _room("syp", "Sypialnia", box(5, 0, 10, 5), strefa=Strefa.NOCNA)
    adj = AdjacencyRule(room_a="hub", room_b="syp", connection_type="door")
    plan = _plan([hub, bed], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hub", room_b="Sypialnia")
    wall_to_guid = {frozenset({"Hub", "Sypialnia"}): "g1"}

    doors = extract_doors(plan, wall_to_guid, [wall])
    assert len(doors) == 1
    d = doors[0]
    # F8: drzwi pokój ↔ hub → cel = pokój (otwierają się DO sypialni)
    assert d.target_room == "Sypialnia"


# ============================================================================
# Test 10 (hinge): skrzydło w stronę bliższego końca ściany
# ============================================================================
def test_hinge_at_closer_end():
    """Zawias przy bliższym końcu ściany (FP4 PlanWriter.cpp:217-221).
    Dla ściany pionowej 5m: door_center = (5, 2.5), dist do begC (5,0) == dist
    do endC (5,5) = 2.5m → przy równych dystansach hinge_at_beg=False (default).

    Dla ściany 5m ale niesymetrycznej (test pokazuje że hinge zależy od
    geometrii ściany — center_offset jest = wall_len/2 więc symetrycznie,
    test po prostu sprawdza że pole hinge_at_beg jest ustawione)."""
    room_a = _room("a", "A", box(0, 0, 5, 5))
    room_b = _room("b", "B", box(5, 0, 10, 5))
    adj = AdjacencyRule(room_a="a", room_b="b", connection_type="door")
    plan = _plan([room_a, room_b], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="A", room_b="B")
    wall_to_guid = {frozenset({"A", "B"}): "g1"}

    doors = extract_doors(plan, wall_to_guid, [wall])
    assert len(doors) == 1
    # Pole jest ustawione (boolean)
    assert isinstance(doors[0].hinge_at_beg, bool)
    # Pole opens_inward zawsze True dla regulararnego drzwi (F8 idea)
    assert doors[0].opens_inward is True


# ============================================================================
# Test 11 (orient_walls): flip ściany dla hub ↔ pokój — normalna na pokój
# ============================================================================
def test_orient_walls_room_normal_points_to_room():
    """Hub po lewej, pokój po prawej. Ściana p1=(5,0)→p2=(5,5) → normal
    wskazuje w PRAWO (do pokoju). NIE flipped — normal już wskazuje na pokój."""
    hub = _room("hub", "Hub", box(0, 0, 5, 5), strefa=Strefa.KOMUNIKACJA)
    bed = _room("syp", "Sypialnia", box(5, 0, 10, 5), strefa=Strefa.NOCNA)
    adj = AdjacencyRule(room_a="hub", room_b="syp", connection_type="door")
    plan = _plan([hub, bed], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hub", room_b="Sypialnia")
    orient_walls_for_doors([wall], plan)

    # Normal (wall_dy, -wall_dx) = (5, 0) → wskazuje w PRAWO (do pokoju at x>5)
    # → NIE flipped
    assert wall.p1 == (5, 0)
    assert wall.p2 == (5, 5)


# ============================================================================
# Test 12 (orient_walls): flip ściany gdy normal wskazuje na hub
# ============================================================================
def test_orient_walls_flips_when_normal_points_away_from_room():
    """Hub po prawej, pokój po lewej. Ściana p1=(5,0)→p2=(5,5) → normal
    wskazuje w PRAWO (do huba). Powinien flipped tak żeby normal wskazywał
    na pokój (w lewo)."""
    bed = _room("syp", "Sypialnia", box(0, 0, 5, 5), strefa=Strefa.NOCNA)
    hub = _room("hub", "Hub", box(5, 0, 10, 5), strefa=Strefa.KOMUNIKACJA)
    adj = AdjacencyRule(room_a="syp", room_b="hub", connection_type="door")
    plan = _plan([bed, hub], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Sypialnia", room_b="Hub")
    orient_walls_for_doors([wall], plan)

    # Powinien być flipped: p1↔p2
    assert wall.p1 == (5, 5)
    assert wall.p2 == (5, 0)


# ============================================================================
# Test 13 (orient_walls): łazienka — normal wskazuje NA HUB (nie na łazienkę)
# ============================================================================
def test_orient_walls_bathroom_normal_points_to_hub():
    """Łazienka po prawej, hub po lewej. F8: target = hub.
    Ściana p1=(5,0)→p2=(5,5) → normal wskazuje na łazienkę (x>5).
    Powinien flipped żeby normal wskazywał na hub."""
    hub = _room("hub", "Hub", box(0, 0, 5, 5), strefa=Strefa.KOMUNIKACJA)
    bath = _room("laz", "Łazienka", box(5, 0, 8, 5), strefa=Strefa.USLUGOWA)
    adj = AdjacencyRule(room_a="hub", room_b="laz", connection_type="door")
    plan = _plan([hub, bath], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hub", room_b="Łazienka")
    orient_walls_for_doors([wall], plan)

    # F8: target = hub → normal powinna wskazywać na hub (w lewo, x<5)
    # Current normal: (wall_dy, -wall_dx) = (5, 0) → w PRAWO (na łazienkę)
    # → flip
    assert wall.p1 == (5, 5)
    assert wall.p2 == (5, 0)


# ============================================================================
# Test 14 (extract_openings): pusty otwór hub ↔ salon
# ============================================================================
def test_extract_openings_hub_salon():
    """connection_type='opening' → OpeningSegment z width = wall_len - thick."""
    hub = _room("hub", "Hub", box(0, 0, 5, 5), strefa=Strefa.KOMUNIKACJA)
    salon = _room("salon", "Salon", box(5, 0, 10, 5))
    adj = AdjacencyRule(room_a="hub", room_b="salon", connection_type="opening")
    plan = _plan([hub, salon], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="Hub", room_b="Salon")
    wall_to_guid = {frozenset({"Hub", "Salon"}): "g-open"}

    openings = extract_openings(plan, wall_to_guid, [wall], wall_thickness=0.10)
    assert len(openings) == 1
    o = openings[0]
    assert o.wall_guid == "g-open"
    assert o.width == pytest.approx(4.90, abs=0.01)  # 5.0 - 0.10
    assert o.height == pytest.approx(OPENING_HEIGHT, abs=0.01)  # 2.50
    # basePoint = dolny lewy róg otworu, z=0
    assert o.base_point[2] == 0.0


# ============================================================================
# Test 15 (extract_openings): typu "door" NIE wchodzi do openings
# ============================================================================
def test_extract_openings_skips_door_type():
    room_a = _room("a", "A", box(0, 0, 5, 5))
    room_b = _room("b", "B", box(5, 0, 10, 5))
    adj = AdjacencyRule("a", "b", "door")
    plan = _plan([room_a, room_b], [adj])

    wall = WallSegment(p1=(5, 0), p2=(5, 5), room_a="A", room_b="B")
    wall_to_guid = {frozenset({"A", "B"}): "g"}

    openings = extract_openings(plan, wall_to_guid, [wall])
    assert openings == []


# ============================================================================
# Test 16 (payload openings): wymagane pola Tapir CreateOpenings
# ============================================================================
def test_openings_payload_required_fields():
    o = OpeningSegment(wall_guid="g1", base_point=(1.0, 2.0, 0.0),
                       width=1.5, height=2.5)
    payload = openings_to_tapir_payload([o])
    assert len(payload) == 1
    p = payload[0]
    assert "ownerElementId" in p
    assert p["ownerElementId"] == {"guid": "g1"}
    assert "basePoint" in p
    assert p["basePoint"] == {"x": 1.0, "y": 2.0, "z": 0.0}
    assert p["width"] == 1.5
    assert p["height"] == 2.5


# ====================================================================
# MVP — geometryczne otwory drzwiowe do renderu (z sąsiedztwa z komunikacją)
# ====================================================================

def test_infer_door_openings_room_to_hub():
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box

    def mk(rid, strefa, x0, y0, x1, y1):
        r = Room(spec=RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False, priorytet_fasady=None),
                 polygon=box(x0, y0, x1, y1)); r.update_metrics()
        return r

    syp = mk("sypialnia_1", Strefa.NOCNA, 0, 0, 3, 3)
    hub = mk("hub", Strefa.KOMUNIKACJA, 3, 0, 5, 3)        # styk pionowy x=3
    doors = infer_door_openings([syp, hub])
    assert len(doors) == 1, doors
    d = doors[0]
    assert {d.room_a, d.room_b} == {"sypialnia_1", "hub"}
    assert d.axis == "v"
    assert abs(d.center[0] - 3.0) < 1e-6
    assert d.width > 0
    # otwarcie do pokoju (nie do holu): wnętrze po stronie sypialni (x<3)
    assert d.into[0] < 3.0

    # schody (KOMUNIKACJA, ale klatka) NIE generują drzwi (F5: routing przez hol)
    schody = mk("schody", Strefa.KOMUNIKACJA, 0, 3, 3, 5)
    assert infer_door_openings([syp, schody]) == []

    # dwa pokoje bez komunikacji między nimi → brak drzwi (drzwi tylko z holu)
    syp2 = mk("sypialnia_2", Strefa.NOCNA, 3, 0, 6, 3)
    assert infer_door_openings([syp, syp2]) == []


def test_infer_door_openings_lroom_real_edge_not_bbox():
    # review: L-pokój — drzwi na REALNEJ wspólnej krawędzi, nie na bbox (nieistniejąca ściana)
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import Polygon, box
    # L: ściana x=3 istnieje tylko dla y∈[1,3]; wnęka x∈[2,3],y∈[0,1]
    lpoly = Polygon([(0, 0), (2, 0), (2, 1), (3, 1), (3, 3), (0, 3)])
    syp = Room(spec=RoomSpec(id="sypialnia_1", nazwa="S", strefa=Strefa.NOCNA, wymaga_okna=False, priorytet_fasady=None),
               polygon=lpoly); syp.update_metrics()
    hub = Room(spec=RoomSpec(id="hub", nazwa="Hol", strefa=Strefa.KOMUNIKACJA, wymaga_okna=False, priorytet_fasady=None),
               polygon=box(3, 0, 5, 3)); hub.update_metrics()   # pełna wysokość — bbox dałby środek y=1.5
    doors = infer_door_openings([syp, hub])
    assert len(doors) == 1, doors
    d = doors[0]
    assert abs(d.center[0] - 3.0) < 1e-6
    # realna krawędź y∈[1,3] → środek ~2.0; bbox (błąd) dałby ~1.5 (w niej nie ma ściany)
    assert abs(d.center[1] - 2.0) < 0.4, f"drzwi na bbox a nie realnej krawędzi: {d.center}"


def test_infer_door_openings_skips_circulation_pair():
    # review: dwie komunikacje (hol↔wiatrołap/korytarz) → brak drzwi (otwarta przestrzeń)
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box
    hub = Room(spec=RoomSpec(id="hub", nazwa="Hol", strefa=Strefa.KOMUNIKACJA, wymaga_okna=False, priorytet_fasady=None),
               polygon=box(0, 0, 3, 3)); hub.update_metrics()
    kor = Room(spec=RoomSpec(id="wiatrolap", nazwa="Wiatrołap", strefa=Strefa.KOMUNIKACJA, wymaga_okna=False, priorytet_fasady=None),
               polygon=box(3, 0, 5, 3)); kor.update_metrics()
    assert infer_door_openings([hub, kor]) == []


def test_infer_door_openings_dayzone_is_opening():
    # review: strefa dzienna↔hol = OTWARCIE (bez skrzydła); pokój↔hol = drzwi
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box
    hub = Room(spec=RoomSpec(id="hub", nazwa="Hol", strefa=Strefa.KOMUNIKACJA, wymaga_okna=False, priorytet_fasady=None),
               polygon=box(4, 0, 6, 3)); hub.update_metrics()
    salon = Room(spec=RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1),
                 polygon=box(0, 0, 4, 3)); salon.update_metrics()
    d = infer_door_openings([salon, hub])[0]
    assert d.is_opening is True, "strefa dzienna↔hol powinna być otwarciem"
    syp = Room(spec=RoomSpec(id="sypialnia_1", nazwa="S", strefa=Strefa.NOCNA, wymaga_okna=False, priorytet_fasady=None),
               polygon=box(0, 0, 4, 3)); syp.update_metrics()
    d2 = infer_door_openings([syp, hub])[0]
    assert d2.is_opening is False, "sypialnia↔hol powinna być drzwiami"


def test_infer_door_openings_service_sluice_fallback():
    """S30 (sąsiedztwa korpusowe): pokój USŁUGOWY bez styku z komunikacją
    (kotłownia za garażem, spiżarnia za kuchnią) dostaje drzwi do sąsiada
    z najdłuższą wspólną krawędzią — każde pomieszczenie musi mieć wejście.
    Sypialnie bez zmian (fallback tylko dla strefy usługowej)."""
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box

    def mk(rid, strefa, x0, y0, x1, y1):
        r = Room(spec=RoomSpec(id=rid, nazwa=rid, strefa=strefa,
                               wymaga_okna=False, priorytet_fasady=None),
                 polygon=box(x0, y0, x1, y1)); r.update_metrics()
        return r

    kot = mk("kotlownia", Strefa.USLUGOWA, 0, 0, 2, 3)
    gar = mk("garaz", Strefa.USLUGOWA, 2, 0, 6, 3)   # styk pionowy x=2, dł. 3 m
    doors = infer_door_openings([kot, gar])
    assert len(doors) == 1, doors
    assert {doors[0].room_a, doors[0].room_b} == {"kotlownia", "garaz"}
    assert doors[0].is_opening is False

    # gdy kotłownia MA styk z komunikacją → zwykłe drzwi od holu, BEZ fallbacku
    hub = mk("hub", Strefa.KOMUNIKACJA, 0, 3, 6, 5)
    doors2 = infer_door_openings([kot, gar, hub])
    pairs = {frozenset((d.room_a, d.room_b)) for d in doors2}
    assert frozenset(("kotlownia", "hub")) in pairs
    assert frozenset(("kotlownia", "garaz")) not in pairs

    # spiżarnia za kuchnią (DZIENNA) — fallback daje drzwi od kuchni
    spz = mk("spizarnia", Strefa.USLUGOWA, 0, 0, 2, 2)
    kuch = mk("kuchnia", Strefa.DZIENNA, 2, 0, 6, 4)
    d3 = infer_door_openings([spz, kuch])
    assert len(d3) == 1 and {d3[0].room_a, d3[0].room_b} == {"spizarnia", "kuchnia"}


def test_infer_door_openings_one_entrance_prefers_hub():
    """Bug 2026-06-18: pokój dotykający HOLU i WIATROŁAPU (oba KOMUNIKACJA) dostawał
    2 drzwi. Reguła Dawida: JEDNO wejście na pokój — z holu (F5), nawet gdy krawędź
    wiatrołapu jest dłuższa."""
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box

    def mk(rid, strefa, x0, y0, x1, y1):
        r = Room(spec=RoomSpec(id=rid, nazwa=rid, strefa=strefa,
                               wymaga_okna=False, priorytet_fasady=None),
                 polygon=box(x0, y0, x1, y1)); r.update_metrics()
        return r

    syp = mk("sypialnia_1", Strefa.NOCNA, 0, 0, 4, 3)
    hub = mk("hub", Strefa.KOMUNIKACJA, 4, 0, 6, 3)              # styk pionowy x=4, dł. 3
    wiatrolap = mk("wiatrolap", Strefa.KOMUNIKACJA, 0, 3, 4, 5)  # styk poziomy y=3, dł. 4 (DŁUŻSZY)
    doors = infer_door_openings([syp, hub, wiatrolap])
    syp_doors = [d for d in doors if d.room_a == "sypialnia_1"]
    assert len(syp_doors) == 1, f"jedno wejście na pokój, było: {[d.room_b for d in syp_doors]}"
    assert syp_doors[0].room_b == "hub", "wejście z holu (F5), nie z dłuższej krawędzi wiatrołapu"


def test_infer_door_openings_other_circulation_when_no_hub():
    """Pokój dotykający TYLKO wiatrołapu (brak holu) → jedno wejście z wiatrołapu."""
    from core.door_extractor import infer_door_openings
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box

    def mk(rid, strefa, x0, y0, x1, y1):
        r = Room(spec=RoomSpec(id=rid, nazwa=rid, strefa=strefa,
                               wymaga_okna=False, priorytet_fasady=None),
                 polygon=box(x0, y0, x1, y1)); r.update_metrics()
        return r

    syp = mk("sypialnia_1", Strefa.NOCNA, 0, 0, 4, 3)
    wiatrolap = mk("wiatrolap", Strefa.KOMUNIKACJA, 0, 3, 4, 5)
    doors = infer_door_openings([syp, wiatrolap])
    assert len(doors) == 1 and doors[0].room_b == "wiatrolap"
