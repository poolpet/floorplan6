"""
Testy label_extractor — generacja etykiet pokoi (V3).

Sprawdza:
  1. Dla każdego pokoju z polygon i area>0 → 1 LabelSegment
  2. Text format: "{nazwa}\\n{area:.1f} m²"
  3. begCoordinate = centroid pokoju
  4. parent_zone_guid = guid z zone_guids (associative)
  5. zone_guids=None → label free-standing (parent_zone_guid=None)
  6. Tapir payload — wymagane pola, format
  7. Empty plan / pokój bez polygon → empty
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from core.label_extractor import (
    LabelSegment,
    extract_labels,
    labels_to_tapir_payload,
)
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


def _room(name: str, polygon: Polygon, strefa: Strefa = Strefa.DZIENNA) -> Room:
    spec = RoomSpec(
        id=name.lower(), nazwa=name, strefa=strefa,
        wymaga_okna=False, priorytet_fasady=None,
    )
    r = Room(spec=spec, polygon=polygon)
    r.update_metrics()
    return r


def _plan(rooms: list[Room]) -> FloorPlan:
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
        sasiedztwo=[],
    )
    return FloorPlan(boundary=boundary, template=template, rooms=rooms)


# ============================================================================
# Test 1: 1 pokój → 1 etykieta z poprawnym tekstem
# ============================================================================
def test_single_room_label():
    room = _room("Salon", box(0, 0, 5, 5))  # area = 25 m²
    plan = _plan([room])

    labels = extract_labels(plan)

    assert len(labels) == 1
    lbl = labels[0]
    assert "Salon" in lbl.text
    assert "25.0" in lbl.text or "25" in lbl.text  # 25 m²
    assert "m²" in lbl.text
    # centroid box(0,0,5,5) = (2.5, 2.5)
    assert lbl.beg_x == pytest.approx(2.5, abs=0.01)
    assert lbl.beg_y == pytest.approx(2.5, abs=0.01)
    # Bez zone_guids → free-standing
    assert lbl.parent_zone_guid is None


# ============================================================================
# Test 2: kilka pokoi z zone_guids → associative labels
# ============================================================================
def test_multiple_rooms_associative_labels():
    rooms = [
        _room("Salon", box(0, 0, 5, 5)),
        _room("Sypialnia", box(5, 0, 10, 5)),
        _room("Łazienka", box(10, 0, 13, 5), strefa=Strefa.USLUGOWA),
    ]
    plan = _plan(rooms)
    zone_guids = ["zone-1", "zone-2", "zone-3"]

    labels = extract_labels(plan, zone_guids=zone_guids)

    assert len(labels) == 3
    assert labels[0].parent_zone_guid == "zone-1"
    assert labels[1].parent_zone_guid == "zone-2"
    assert labels[2].parent_zone_guid == "zone-3"
    assert "Salon" in labels[0].text
    assert "Sypialnia" in labels[1].text
    assert "Łazienka" in labels[2].text


# ============================================================================
# Test 3: Pokój bez polygon pomijany
# ============================================================================
def test_room_without_polygon_skipped():
    # _room z polygonem
    r1 = _room("A", box(0, 0, 5, 5))
    # _room bez polygon
    spec = RoomSpec(
        id="b", nazwa="B", strefa=Strefa.DZIENNA,
        wymaga_okna=False, priorytet_fasady=None,
    )
    r2 = Room(spec=spec, polygon=None)
    plan = _plan([r1, r2])

    labels = extract_labels(plan)
    assert len(labels) == 1
    assert labels[0].room_name == "A"


# ============================================================================
# Test 4: empty plan
# ============================================================================
def test_empty_plan():
    plan = _plan([])
    assert extract_labels(plan) == []
    assert labels_to_tapir_payload([]) == []


# ============================================================================
# Test 5: payload Tapir — wymagane pola
# ============================================================================
def test_tapir_payload_format():
    lbl = LabelSegment(
        text="Salon\n25.0 m²",
        beg_x=2.5, beg_y=2.5,
        parent_zone_guid="zone-1",
    )
    payload = labels_to_tapir_payload([lbl])

    assert len(payload) == 1
    p = payload[0]
    assert p["text"] == "Salon\n25.0 m²"
    assert p["begCoordinate"] == {"x": 2.5, "y": 2.5}
    assert p["parentElementId"] == {"guid": "zone-1"}


# ============================================================================
# Test 6: payload bez parentElementId (free-standing label)
# ============================================================================
def test_tapir_payload_no_parent():
    lbl = LabelSegment(text="X", beg_x=1.0, beg_y=2.0)
    payload = labels_to_tapir_payload([lbl])
    assert "parentElementId" not in payload[0]
    assert payload[0]["text"] == "X"
    assert payload[0]["begCoordinate"] == {"x": 1.0, "y": 2.0}


# ============================================================================
# Test 7: zone_guids krótszy niż liczba pokoi (defensive)
# ============================================================================
def test_zone_guids_partial():
    """Jeśli mamy 3 pokoje ale tylko 2 GUID-y → pierwsze 2 associative, 3-ci bez."""
    rooms = [_room(f"R{i}", box(i*5, 0, i*5+5, 5)) for i in range(3)]
    plan = _plan(rooms)
    labels = extract_labels(plan, zone_guids=["g1", "g2"])

    assert len(labels) == 3
    assert labels[0].parent_zone_guid == "g1"
    assert labels[1].parent_zone_guid == "g2"
    assert labels[2].parent_zone_guid is None
