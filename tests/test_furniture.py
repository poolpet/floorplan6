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


def test_room_window_walls_rectangle():
    from core.furniture import _room_window_walls
    from core.boundary_analyzer import analyze_boundary
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(0.0, 4.0, 4.0, 8.0)); r.update_metrics()  # dotyka W (x=0) i N (y=8)
    walls = _room_window_walls(r, b)
    assert walls == {"W", "N"}
    assert _room_window_walls(r, None) == set()   # bez boundary — brak okien


def test_place_on_wall_targets_wall():
    from core.furniture import _place_on_wall
    region = (0.0, 0.0, 4.0, 4.0)
    rect = _place_on_wall(region, 1.6, 2.0, "S", [], [])   # wzdłuż S (dół): szer 1.6 w x, głęb 2.0 w y
    assert rect is not None
    b = rect.bounds
    assert abs(b[1] - 0.0) < 1e-9            # przy ścianie S (y=0)
    assert abs((b[2] - b[0]) - 1.6) < 1e-9   # szerokość wzdłuż ściany
    assert abs((b[3] - b[1]) - 2.0) < 1e-9   # głębokość


def test_bedroom_bed_on_windowless_wall():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    # 10x8; sypialnia dotyka TYLKO ściany S (okno na dole); N/W/E wewnętrzne.
    # Wejście na W (entry_point) — bo krawędź wejścia jest klasyfikowana jako INTERNAL
    # (nie-okno), więc okno na S wymaga wejścia po innej stronie.
    # Dyskryminuje: generic _place_fixed próbuje S jako PIERWSZĄ → łóżko pod oknem;
    # semantyczny placer musi je przenieść na ścianę bez okna.
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(0, 4))
    sp = RoomSpec(id="sypialnia_1", nazwa="Sypialnia", strefa=Strefa.NOCNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(3.0, 0.0, 7.0, 4.0)); r.update_metrics()  # okno: tylko S (y=0)
    res = furnish_rooms([r], boundary=b)
    bed = next(f for f in res.furniture if f.piece_type == "bed")
    bb = bed.polygon.bounds
    # wezgłowie NIE przy oknie S: łóżko nie dosunięte do dołu (y=0)
    assert not (abs(bb[1] - 0.0) < 0.2), f"łóżko pod oknem S: {bb}"
    assert any(f.piece_type == "nightstand" for f in res.furniture), "brak szafki nocnej"
    # kontrola: bez boundary (brak wiedzy o oknach) łóżko ląduje przy S (generic) — degradacja OK
    res0 = furnish_rooms([r])
    assert any(f.piece_type == "bed" for f in res0.furniture)


def test_kitchen_counter_under_window():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    # 10x8, wejście na S (entry edge = INTERNAL, nie-okno). Kuchnia box(0,0,3,4) dotyka
    # S (wejście) i W (okno). Generic _place_linear próbuje S jako PIERWSZĄ → blat poziomy
    # przy wejściu; semantyczny musi puścić blat PIONOWO wzdłuż okna W.
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 3.0, 4.0)); r.update_metrics()  # okno: tylko W (x=0)
    res = furnish_rooms([r], boundary=b)
    counter = next(f for f in res.furniture if f.piece_type == "kitchen_counter")
    cb = counter.polygon.bounds
    width_x, depth_y = cb[2] - cb[0], cb[3] - cb[1]
    on_W = abs(cb[0] - 0.0) < 0.2
    assert on_W and depth_y > width_x, f"blat nie biegnie wzdłuż okna W: {cb}"


def test_living_sofa_tv_opposite():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    # 10x8, wejście na S. Salon box(4,0,10,6): okno tylko na E (x=10); S/N/W wewnętrzne.
    # Semantyczny: sofa na ścianie wewnętrznej (S, najdłuższa), TV na PRZECIWLEGŁEJ (N).
    # Generic packuje meble przy S → TV ląduje OBOK sofy (nie naprzeciw).
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(4.0, 0.0, 10.0, 6.0)); r.update_metrics()
    res = furnish_rooms([r], boundary=b)
    sofa = next(f for f in res.furniture if f.piece_type == "sofa")
    tv = next(f for f in res.furniture if f.piece_type == "tv_unit")
    # sofa przy S (dół), TV przy PRZECIWLEGŁEJ N (góra) — naprzeciw, nie obok
    assert sofa.polygon.bounds[1] < 1.5, f"sofa nie przy ścianie S: {sofa.polygon.bounds}"
    assert tv.polygon.bounds[3] > 4.5, f"TV nie przy przeciwległej ścianie N: {tv.polygon.bounds}"
    assert any(f.piece_type == "coffee_table" for f in res.furniture)


def test_dining_table_at_junction():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    b = analyze_boundary(Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), entry_point=(6, 0))
    salon = Room(spec=RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1),
                 polygon=box(0.0, 0.0, 7.0, 8.0)); salon.update_metrics()
    kuch = Room(spec=RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2),
                polygon=box(7.0, 0.0, 12.0, 8.0)); kuch.update_metrics()
    res = furnish_rooms([salon, kuch], boundary=b)
    dt = next((f for f in res.furniture if f.piece_type == "dining_table"), None)
    assert dt is not None, "brak stołu jadalnego"
    # stół blisko wspólnej krawędzi x=7
    assert abs(dt.polygon.centroid.x - 7.0) < 2.5, f"stół daleko od styku: {dt.polygon.bounds}"


def test_bathroom_fixtures_on_one_wall_and_clear():
    from core.furniture import furnish_rooms
    sp = RoomSpec(id="lazienka", nazwa="Łazienka", strefa=Strefa.USLUGOWA, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 2.2, 2.3)); r.update_metrics()  # ~5 m²
    res = furnish_rooms([r], boundary=None)
    types = {f.piece_type for f in res.furniture}
    assert {"bathtub", "washbasin", "toilet"} <= types, f"brak armatury: {types}"
    # brak nakładania między meblami
    fs = res.furniture
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            assert fs[i].polygon.intersection(fs[j].polygon).area < 1e-6


def test_tiny_bedroom_warns_no_bed():
    from core.furniture import furnish_rooms
    sp = RoomSpec(id="sypialnia_2", nazwa="Sypialnia", strefa=Strefa.NOCNA, wymaga_okna=True, priorytet_fasady=2)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 1.5, 1.6)); r.update_metrics()  # 2.4 m² — łóżko się nie zmieści
    res = furnish_rooms([r], boundary=None)
    assert not any(f.piece_type == "bed" for f in res.furniture)
    assert any("łóżko" in w for w in res.warnings), res.warnings


def test_tiny_bathroom_warns_no_bathtub():
    # Dyskryminuje placer łazienki vs generic: generic milczy, semantyczny ostrzega o kluczowym meblu.
    from core.furniture import furnish_rooms
    sp = RoomSpec(id="lazienka", nazwa="Łazienka", strefa=Strefa.USLUGOWA, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 1.2, 1.2)); r.update_metrics()  # 1.44 m² — wanna się nie mieści
    res = furnish_rooms([r], boundary=None)
    assert not any(f.piece_type == "bathtub" for f in res.furniture)
    assert any("wann" in w.lower() for w in res.warnings), res.warnings


def test_furnish_generated_single_storey_no_overlap():
    from core.house_layout import generate_house
    from core.furniture import furnish_rooms
    lay = generate_house(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), (5.0, 0.0),
                         num_storeys=1, time_limit_s=30)
    assert lay.ok, lay.message
    res = furnish_rooms(lay.parter_rooms, boundary=lay.boundary)
    assert res.furniture, "nic nie umeblowano"
    # meble mieszczą się w swoich pokojach i się nie nakładają (w obrębie pokoju)
    by_room = {}
    for f in res.furniture:
        by_room.setdefault(f.room_id, []).append(f.polygon)
    for rid, polys in by_room.items():
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                assert polys[i].intersection(polys[j]).area < 1e-6, f"nakładanie w {rid}"
    # łóżko istnieje (single-storey ma sypialnia_1)
    beds = [f for f in res.furniture if f.piece_type == "bed"]
    assert beds, "brak łóżka w domu"


# ---- poprawki z adwersaryjnego review (phase 4) ----

def test_kitchen_counter_falls_back_off_blocked_window_wall():
    # review #2: okno zablokowane → blat MUSI trafić na wolną ścianę (nie fałszywe ostrzeżenie)
    from core.furniture import _furnish_kitchen
    sp = RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 3.0, 3.0)); r.update_metrics()
    block_w = box(0.0, 0.0, 0.8, 3.0)   # strefa drzwi zasłania całą ścianę-okno W
    out, warn = _furnish_kitchen(r, {"W"}, [block_w])
    assert any(f.piece_type == "kitchen_counter" for f in out), "blat nie postawiony mimo wolnych ścian"
    assert warn == [], f"fałszywe ostrzeżenie mimo wolnej ściany: {warn}"


def test_bathroom_keeps_washbasin_when_tight():
    # review #22: ciasna łazienka — umywalka (kluczowa) MUSI być, nawet kosztem wanny
    from core.furniture import furnish_rooms
    sp = RoomSpec(id="lazienka", nazwa="Łazienka", strefa=Strefa.USLUGOWA, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 1.0, 1.9)); r.update_metrics()  # wanna wypełnia region → konflikt
    res = furnish_rooms([r], boundary=None)
    types = {f.piece_type for f in res.furniture}
    assert "washbasin" in types, f"umywalka pominięta na rzecz wanny: {types}"


def test_coffee_table_between_sofa_and_tv():
    # review #20: stolik MIĘDZY sofą a TV, nie dosunięty obok sofy
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(4.0, 0.0, 10.0, 6.0)); r.update_metrics()
    res = furnish_rooms([r], boundary=b)
    sofa = next(f for f in res.furniture if f.piece_type == "sofa")
    tv = next(f for f in res.furniture if f.piece_type == "tv_unit")
    coffee = next(f for f in res.furniture if f.piece_type == "coffee_table")
    sc, tc, cc = sofa.polygon.centroid, tv.polygon.centroid, coffee.polygon.centroid
    mid_y = (sc.y + tc.y) / 2     # sofa S / TV N → oś naprzeciw to y
    assert abs(cc.y - mid_y) < 0.8, f"stolik nie między sofą a TV: sofa.y={sc.y:.2f} tv.y={tc.y:.2f} coffee.y={cc.y:.2f}"


def test_bedroom_two_nightstands_when_centered():
    # review #21: łóżko wyśrodkowane na ścianie → szafki nocne z OBU stron (nie 1 przez róg)
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(0, 4))
    sp = RoomSpec(id="sypialnia_1", nazwa="Sypialnia", strefa=Strefa.NOCNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(3.0, 0.0, 7.0, 4.0)); r.update_metrics()  # 4x4, okno tylko S
    res = furnish_rooms([r], boundary=b)
    ns = [f for f in res.furniture if f.piece_type == "nightstand"]
    assert len(ns) == 2, f"oczekiwano 2 szafek nocnych (łóżko wyśrodkowane), jest {len(ns)}"


def test_dining_table_with_salon_suffix_id():
    # review #5/#14: salon dopasowany prefiksem (salon_1), nie exact id — inaczej stół znika
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    b = analyze_boundary(Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), entry_point=(6, 0))
    salon = Room(spec=RoomSpec(id="salon_1", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1),
                 polygon=box(0.0, 0.0, 7.0, 8.0)); salon.update_metrics()
    kuch = Room(spec=RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2),
                polygon=box(7.0, 0.0, 12.0, 8.0)); kuch.update_metrics()
    res = furnish_rooms([salon, kuch], boundary=b)
    assert any(f.piece_type == "dining_table" for f in res.furniture), "salon_1 nie dostał stołu (id-drift)"
