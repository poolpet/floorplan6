"""
Testy wall_extractor — ekstrakcja ścianek działowych z wygenerowanego rzutu.

Sprawdza:
  1. Dwa przylegające pokoje → 1 ściana o znanej długości.
  2. Trzy pokoje w rzędzie → 2 ściany.
  3. Pokoje niesąsiadujące → 0 ścian.
  4. Krótkie wspólne odcinki (<30 cm) odfiltrowane.
  5. Konwersja do payload Tapir CreateWalls — wymagane pola obecne.
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from core.models import (
    Boundary, EdgeInfo, FloorPlan, Orientation, Room, RoomSpec, Strefa,
    Template, WallType,
)
from core.wall_extractor import (
    DEFAULT_WALL_HEIGHT_M,
    DEFAULT_WALL_THICKNESS_M,
    MIN_WALL_LENGTH_M,
    extract_internal_walls,
    walls_to_tapir_payload,
)


def _make_room(name: str, polygon: Polygon, strefa: Strefa = Strefa.DZIENNA) -> Room:
    """Helper — tworzy minimalny Room z polygonem."""
    spec = RoomSpec(
        id=name.lower(),
        nazwa=name,
        strefa=strefa,
        wymaga_okna=False,
        priorytet_fasady=None,
    )
    r = Room(spec=spec, polygon=polygon)
    r.update_metrics()
    return r


def _make_plan(rooms: list[Room]) -> FloorPlan:
    """Helper — tworzy minimalny FloorPlan z pokojami."""
    # Boundary i Template są wymagane przez dataclass ale wall_extractor
    # ich nie czyta — wstawiamy zaślepkę.
    poly = box(0, 0, 10, 10)
    boundary = Boundary(
        polygon=poly,
        edges=[EdgeInfo(start=(0, 0), end=(10, 0),
                        wall_type=WallType.FACADE, orientation=Orientation.S)],
        entry_point=(5.0, 0.0),
    )
    template = Template(
        id="test", nazwa="test", typ_mieszkania="M1",
        pokoje=[r.spec for r in rooms],
        sasiedztwo=[],
    )
    return FloorPlan(boundary=boundary, template=template, rooms=rooms)


# ============================================================================
# Test 1: dwa pokoje przylegające → jedna ściana
# ============================================================================
def test_two_adjacent_rooms_one_wall():
    # Pokój A: kwadrat 5x5 z lewej, Pokój B: kwadrat 5x5 z prawej.
    # Dzielą krawędź pionową x=5, y∈[0,5] o długości 5.
    room_a = _make_room("A", box(0, 0, 5, 5))
    room_b = _make_room("B", box(5, 0, 10, 5))
    plan = _make_plan([room_a, room_b])

    walls = extract_internal_walls(plan)

    assert len(walls) == 1, f"Oczekiwano 1 ściany, jest {len(walls)}"
    w = walls[0]
    assert pytest.approx(w.length, abs=0.001) == 5.0
    # Sciana pionowa na x=5
    assert pytest.approx(w.p1[0], abs=0.001) == 5.0
    assert pytest.approx(w.p2[0], abs=0.001) == 5.0
    # Sprawdz domyslne wymiary
    assert w.height == DEFAULT_WALL_HEIGHT_M
    assert w.thickness == DEFAULT_WALL_THICKNESS_M
    # Diagnostyka — wiemy które pokoje są po stronach
    assert {w.room_a, w.room_b} == {"A", "B"}


# ============================================================================
# Test 2: trzy pokoje w rzędzie → dwie ściany
# ============================================================================
def test_three_rooms_in_row_two_walls():
    # A | B | C — trzy kwadraty 5x5 obok siebie
    room_a = _make_room("A", box(0, 0, 5, 5))
    room_b = _make_room("B", box(5, 0, 10, 5))
    room_c = _make_room("C", box(10, 0, 15, 5))
    plan = _make_plan([room_a, room_b, room_c])

    walls = extract_internal_walls(plan)

    assert len(walls) == 2, f"Oczekiwano 2 ścian, jest {len(walls)}"
    # Obie pionowe, długości 5m
    for w in walls:
        assert pytest.approx(w.length, abs=0.001) == 5.0
    # Pary pokoi: {A,B} i {B,C}, NIE {A,C}
    pairs = {frozenset({w.room_a, w.room_b}) for w in walls}
    assert pairs == {frozenset({"A", "B"}), frozenset({"B", "C"})}


# ============================================================================
# Test 3: pokoje niesąsiadujące → brak ścian
# ============================================================================
def test_isolated_rooms_no_walls():
    # A i B daleko od siebie (przerwa 5m)
    room_a = _make_room("A", box(0, 0, 5, 5))
    room_b = _make_room("B", box(10, 0, 15, 5))
    plan = _make_plan([room_a, room_b])

    walls = extract_internal_walls(plan)

    assert walls == []


# ============================================================================
# Test 4: krótki wspólny segment (<30 cm) odfiltrowany
# ============================================================================
def test_short_shared_segment_filtered():
    # Dwa pokoje stykające się tylko 20 cm — poniżej MIN_WALL_LENGTH_M (30 cm).
    # A: prostokąt 5x5, B: prostokąt 5x0.2 (przyklejony do dolnej krawędzi A).
    # Wait — shared edge to długość styku, nie wymiar pokoju B.
    # Zrobimy tak: A=box(0,0,5,5), B=box(5,0,10,0.2). Dzielą krawędź x=5, y∈[0,0.2]
    # o długości 0.2m (<30cm).
    room_a = _make_room("A", box(0, 0, 5, 5))
    room_b = _make_room("B", box(5, 0, 10, 0.2))
    plan = _make_plan([room_a, room_b])

    walls = extract_internal_walls(plan)
    assert walls == [], (
        f"Krótki segment (0.2m) powinien być odfiltrowany, jest {walls}"
    )

    # Sprawdz z mniejszym min_length że to działa gdy chcemy
    walls_low = extract_internal_walls(plan, min_length=0.1)
    assert len(walls_low) == 1


# ============================================================================
# Test 5: payload Tapir — wymagane pola obecne
# ============================================================================
def test_tapir_payload_has_required_fields():
    room_a = _make_room("A", box(0, 0, 5, 5))
    room_b = _make_room("B", box(5, 0, 10, 5))
    plan = _make_plan([room_a, room_b])
    walls = extract_internal_walls(plan)
    payload = walls_to_tapir_payload(walls)

    assert len(payload) == 1
    required = {"begCoordinate", "endCoordinate", "zCoordinate",
                "height", "thickness"}
    assert required.issubset(payload[0].keys()), (
        f"Brak wymaganych pól: {required - set(payload[0].keys())}"
    )
    assert payload[0]["begCoordinate"].keys() == {"x", "y"}
    assert payload[0]["endCoordinate"].keys() == {"x", "y"}
    assert payload[0]["height"] > 0
    assert payload[0]["thickness"] > 0


# ============================================================================
# Test 6: empty plan → empty walls
# ============================================================================
def test_empty_plan_no_walls():
    plan = _make_plan([])
    assert extract_internal_walls(plan) == []
    assert walls_to_tapir_payload([]) == []
