"""Stage 4 — furniture placement (spec §5/§8). Pure geometry, no CP-SAT (fast)."""
from shapely.geometry import Polygon, box

from core.models import Room, RoomSpec, Strefa
from core.furniture import place_furniture, Furniture


def _room(room_id: str, strefa: Strefa, w: float, h: float, x: float = 0.0, y: float = 0.0) -> Room:
    spec = RoomSpec(
        id=room_id, nazwa=room_id, strefa=strefa,
        wymaga_okna=False, priorytet_fasady=None,
    )
    room = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    room.update_metrics()
    return room


def _types(furniture: list[Furniture]) -> set[str]:
    return {f.piece_type for f in furniture}


def _assert_inside_and_disjoint(furniture: list[Furniture], room: Room):
    container = room.polygon.buffer(1e-6)
    for f in furniture:
        assert container.contains(f.polygon), f"{f.piece_type} wystaje poza pokój {room.spec.id}"
    for i in range(len(furniture)):
        for j in range(i + 1, len(furniture)):
            inter = furniture[i].polygon.intersection(furniture[j].polygon).area
            assert inter < 1e-6, f"kolizja {furniture[i].piece_type} × {furniture[j].piece_type}"


def test_sypialnia_gets_bed_and_wardrobe():
    room = _room("sypialnia_1", Strefa.NOCNA, 4.0, 3.5)
    furniture = [f for f in place_furniture([room]) if f.room_id == room.spec.id]
    assert "bed" in _types(furniture)
    assert "wardrobe" in _types(furniture)
    _assert_inside_and_disjoint(furniture, room)


def test_salon_gets_sofa_and_table():
    room = _room("salon", Strefa.DZIENNA, 5.0, 4.0)
    furniture = [f for f in place_furniture([room]) if f.room_id == room.spec.id]
    assert "sofa" in _types(furniture)
    assert "coffee_table" in _types(furniture)
    _assert_inside_and_disjoint(furniture, room)


def test_lazienka_gets_three_fixtures():
    room = _room("lazienka", Strefa.USLUGOWA, 2.6, 2.2)
    furniture = [f for f in place_furniture([room]) if f.room_id == room.spec.id]
    assert {"bathtub", "washbasin", "toilet"} <= _types(furniture)
    _assert_inside_and_disjoint(furniture, room)


def test_too_small_room_skips_oversized_piece():
    room = _room("sypialnia_1", Strefa.NOCNA, 1.3, 1.3)  # bed 1.6×2.0 cannot fit
    furniture = [f for f in place_furniture([room]) if f.room_id == room.spec.id]
    assert "bed" not in _types(furniture)
    _assert_inside_and_disjoint(furniture, room)


def test_circulation_rooms_get_no_furniture():
    hub = _room("hub", Strefa.KOMUNIKACJA, 3.0, 3.0)
    wiatrolap = _room("wiatrolap", Strefa.KOMUNIKACJA, 1.5, 3.0, x=3.0)
    furniture = place_furniture([hub, wiatrolap])
    assert furniture == []


def test_furniture_avoids_inferred_door_zone():
    # sypialnia (left) sharing its right wall with the hub (right) → door inferred
    # at the shared edge midpoint; no piece may block it.
    sypialnia = _room("sypialnia_1", Strefa.NOCNA, 3.5, 3.0, x=0.0)
    hub = _room("hub", Strefa.KOMUNIKACJA, 2.0, 3.0, x=3.5)
    furniture = [f for f in place_furniture([sypialnia, hub]) if f.room_id == "sypialnia_1"]
    assert furniture, "sypialnia powinna dostać meble"
    # door zone: ~0.9 m wide opening centred on shared edge (x≈3.5, y≈1.5), 0.6 m deep into room
    door_zone = box(3.5 - 0.6, 1.5 - 0.55, 3.5, 1.5 + 0.55)
    for f in furniture:
        assert f.polygon.intersection(door_zone).area < 1e-6, f"{f.piece_type} blokuje drzwi"


# ====================================================================
# Phase 4 — realistic, window-aware furniture (spec 2026-06-03)
# ====================================================================

def test_furnish_rooms_backcompat_shape():
    from core.furniture import furnish_rooms, place_furniture, FurnishResult
    hub = _room("hub", Strefa.KOMUNIKACJA, 1.5, 3.0, x=0.0)
    syp = _room("sypialnia_1", Strefa.NOCNA, 3.0, 4.0, x=3.0)
    res = furnish_rooms([hub, syp])               # bez boundary
    assert isinstance(res, FurnishResult)
    assert res.warnings == []
    # place_furniture nadal zwraca listę identyczną z res.furniture
    assert [f.piece_type for f in place_furniture([hub, syp])] == [f.piece_type for f in res.furniture]
