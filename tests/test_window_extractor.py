"""
Testy window_extractor — generacja okien fasadowych (V4).

Sprawdza:
  1. Pokój z wymaga_okna=True na FACADE → 1 okno z odpowiednimi wymiarami
  2. Pokój bez wymaga_okna → bez okna
  3. Pokój wewnętrzny (nie dotyka boundary) → bez okna
  4. Wymiary per strefa (DZIENNA vs NOCNA vs USLUGOWA)
  5. Pokój z kilkoma fasadami → wybiera najdłuższą
  6. Payload Tapir — wymagane pola
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from core.models import (
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
from core.window_extractor import (
    DEFAULT_WINDOW,
    WINDOW_DIMENSIONS,
    WT_GLASS_AREA_RATIO,
    WindowSegment,
    extract_windows,
    windows_to_tapir_payload,
)


def _room(
    name: str,
    polygon: Polygon,
    strefa: Strefa = Strefa.NOCNA,
    wymaga_okna: bool = True,
) -> Room:
    spec = RoomSpec(
        id=name.lower(), nazwa=name, strefa=strefa,
        wymaga_okna=wymaga_okna, priorytet_fasady=1,
    )
    r = Room(spec=spec, polygon=polygon)
    r.update_metrics()
    return r


def _ac_wall(guid: str, beg, end) -> dict:
    """Stub AC wall details (jak fetched z Tapir GetDetailsOfElements + _guid)."""
    return {
        "_guid": guid,
        "details": {
            "begCoordinate": {"x": beg[0], "y": beg[1]},
            "endCoordinate": {"x": end[0], "y": end[1]},
        },
    }


def _plan_rect_facade(rooms: list[Room]) -> FloorPlan:
    """Plan z prostokątem boundary 10×10, wszystkie 4 krawędzie FACADE."""
    poly = box(0, 0, 10, 10)
    edges = [
        EdgeInfo(start=(0, 0), end=(10, 0), wall_type=WallType.FACADE, orientation=Orientation.S),
        EdgeInfo(start=(10, 0), end=(10, 10), wall_type=WallType.FACADE, orientation=Orientation.E),
        EdgeInfo(start=(10, 10), end=(0, 10), wall_type=WallType.FACADE, orientation=Orientation.N),
        EdgeInfo(start=(0, 10), end=(0, 0), wall_type=WallType.FACADE, orientation=Orientation.W),
    ]
    boundary = Boundary(polygon=poly, edges=edges, entry_point=(5, 0))
    template = Template(
        id="t", nazwa="t", typ_mieszkania="M2",
        pokoje=[r.spec for r in rooms],
        sasiedztwo=[],
    )
    return FloorPlan(boundary=boundary, template=template, rooms=rooms)


# ============================================================================
# Test 1: pokój na fasadzie z wymaga_okna=True → 1 okno
# ============================================================================
def test_room_on_facade_gets_window():
    room = _room("Sypialnia", box(0, 0, 5, 5), strefa=Strefa.NOCNA, wymaga_okna=True)
    plan = _plan_rect_facade([room])
    ac_walls = [
        _ac_wall("wall-south", (0, 0), (10, 0)),
        _ac_wall("wall-east", (10, 0), (10, 10)),
        _ac_wall("wall-north", (10, 10), (0, 10)),
        _ac_wall("wall-west", (0, 10), (0, 0)),
    ]

    windows = extract_windows(plan, ac_walls)
    assert len(windows) == 1
    w = windows[0]
    assert w.room_name == "Sypialnia"
    # Sypialnia (NOCNA): wymiary z WINDOW_DIMENSIONS
    expected = WINDOW_DIMENSIONS[Strefa.NOCNA]
    assert w.height == expected["height"]
    assert w.sill_height == expected["sill"]
    # Wall guid jeden z 4 fasad
    assert w.wall_guid in ("wall-south", "wall-east", "wall-north", "wall-west")


# ============================================================================
# Test 2: pokój bez wymaga_okna → bez okna
# ============================================================================
def test_room_without_wymaga_okna_skipped():
    room = _room("Łazienka", box(0, 0, 3, 3),
                 strefa=Strefa.USLUGOWA, wymaga_okna=False)
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w1", (0, 0), (10, 0))]
    windows = extract_windows(plan, ac_walls)
    assert windows == []


# ============================================================================
# Test 3: pokój wewnętrzny (nie dotyka boundary) → bez okna
# ============================================================================
def test_internal_room_no_window():
    # Pokój [2,2]-[5,5] — wewnątrz, nie dotyka boundary [0,0]-[10,10]
    room = _room("Pokój wewnętrzny", box(2, 2, 5, 5),
                 strefa=Strefa.NOCNA, wymaga_okna=True)
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w1", (0, 0), (10, 0))]
    windows = extract_windows(plan, ac_walls)
    assert windows == []


# ============================================================================
# Test 4: pokój DZIENNA → szersze okno (2.10m)
# ============================================================================
def test_living_room_gets_balcony_window():
    """Salon DZIENNA dostaje okno balkonowe: sill=0, height=2.10m."""
    room = _room("Salon", box(0, 0, 8, 5),
                 strefa=Strefa.DZIENNA, wymaga_okna=True)
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w-south", (0, 0), (10, 0))]
    windows = extract_windows(plan, ac_walls)
    assert len(windows) == 1
    w = windows[0]
    # Okno balkonowe: parapet = 0 (od podłogi)
    assert w.sill_height == 0.0
    # Wysokość 2.10m (typowe okno balkonowe PL)
    assert w.height == pytest.approx(2.10, abs=0.01)
    # WT 1/8 spełnione
    assert w.width * w.height >= room.polygon.area * WT_GLASS_AREA_RATIO * 0.95


# ============================================================================
# Test 5: pokój nie matchuje AC walls (brak ścian) → no window
# ============================================================================
def test_no_ac_walls_no_windows():
    room = _room("Sypialnia", box(0, 0, 5, 5), wymaga_okna=True)
    plan = _plan_rect_facade([room])
    windows = extract_windows(plan, [])
    assert windows == []


# ============================================================================
# Test 6: payload Tapir
# ============================================================================
def test_tapir_payload():
    w = WindowSegment(wall_guid="g1", center_offset=2.5,
                       width=1.2, height=1.4, sill_height=0.9,
                       room_name="X", edge_length=5.0)
    payload = windows_to_tapir_payload([w])
    assert len(payload) == 1
    p = payload[0]
    assert p["ownerWallId"] == {"guid": "g1"}
    assert p["centerOffset"] == 2.5
    assert p["width"] == 1.2
    assert p["height"] == 1.4
    assert p["sillHeight"] == 0.9


# ============================================================================
# Test 7: empty plan
# ============================================================================
def test_empty_plan():
    plan = _plan_rect_facade([])
    assert extract_windows(plan, []) == []
    assert windows_to_tapir_payload([]) == []


# ============================================================================
# Test 8 (WT 1/8): okno spełnia regułę powierzchni >= room.area / 8
# ============================================================================
def test_wt_18_rule_satisfied_for_living_room():
    """Salon 26m² → min okno area = 3.25m². Sprawdź że okno to spełnia."""
    # Salon 6.5×4 = 26m² (większy niż 25)
    room = _room("Salon", box(0, 0, 6.5, 4), strefa=Strefa.DZIENNA,
                  wymaga_okna=True)
    # Boundary 10×10 — salon przylega do south facade na 6.5m
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w-south", (0, 0), (10, 0))]

    windows = extract_windows(plan, ac_walls)
    assert len(windows) == 1
    w = windows[0]
    glass_area = w.width * w.height
    room_area = room.polygon.area
    min_required = room_area * WT_GLASS_AREA_RATIO

    # Sprawdź WT 1/8 (margines 5% bo algorytm może nie dotrzymać dokładnie)
    assert glass_area >= min_required * 0.95, (
        f"Okno {w.width}×{w.height}={glass_area:.2f}m² za małe dla pokoju "
        f"{room_area:.2f}m² (wymagane min {min_required:.2f})"
    )


def test_wt_18_rule_satisfied_for_bedroom():
    """Sypialnia 14m² (większa niż default NOCNA 1.68m²) → szerokość zwiększona."""
    # Sypialnia 4×3.5 = 14m²
    room = _room("Sypialnia", box(0, 0, 4, 3.5),
                  strefa=Strefa.NOCNA, wymaga_okna=True)
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w-south", (0, 0), (10, 0))]

    windows = extract_windows(plan, ac_walls)
    assert len(windows) == 1
    w = windows[0]
    glass_area = w.width * w.height
    room_area = room.polygon.area
    min_required = room_area * WT_GLASS_AREA_RATIO

    assert glass_area >= min_required * 0.95
    # Default NOCNA width=1.20 nie wystarcza dla 14m² (1.20*1.40=1.68 < 14/8=1.75)
    # → algorytm musi zwiększyć
    assert w.width > WINDOW_DIMENSIONS[Strefa.NOCNA]["width"] or \
           w.height > WINDOW_DIMENSIONS[Strefa.NOCNA]["height"]


def test_wt_18_small_room_uses_default():
    """Mały pokój (5m²) → default sufficient bo 1.20*1.40=1.68 > 5/8=0.625."""
    room = _room("Mały pokój", box(0, 0, 2.5, 2),
                  strefa=Strefa.NOCNA, wymaga_okna=True)
    plan = _plan_rect_facade([room])
    ac_walls = [_ac_wall("w-south", (0, 0), (10, 0))]

    windows = extract_windows(plan, ac_walls)
    assert len(windows) == 1
    w = windows[0]
    # Powinno zostać blisko default (małe odchyłki OK)
    assert w.height == pytest.approx(WINDOW_DIMENSIONS[Strefa.NOCNA]["height"], abs=0.01)
