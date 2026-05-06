from core.cpsat_solver import solve_cpsat, CpsatResult
from core.template_selector import load_all_templates
from core.boundary_analyzer import analyze_boundary
from shapely.geometry import Polygon


def _make_boundary(w, h):
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    return analyze_boundary(poly, (w / 2, 0))


def test_basic_tiling_m2_8x6():
    boundary = _make_boundary(8.0, 6.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.rooms) == len(template.pokoje)
    total = sum(r.area for r in result.rooms)
    assert abs(total - 48.0) < 0.05


def test_basic_tiling_m1_6x7():
    boundary = _make_boundary(6.0, 7.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M1"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.rooms) == len(template.pokoje)
    total = sum(r.area for r in result.rooms)
    assert abs(total - 42.0) < 0.05


def test_all_rooms_inside_boundary():
    boundary = _make_boundary(8.0, 6.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    for room in result.rooms:
        b = room.polygon.bounds
        assert b[0] >= -0.01 and b[1] >= -0.01 and b[2] <= 8.01 and b[3] <= 6.01


def test_hub_adjacency_m2():
    boundary = _make_boundary(8.0, 6.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    hub = next(r for r in result.rooms if r.spec.strefa.value == "KOMUNIKACJA")
    for room in result.rooms:
        if room.spec.strefa.value == "KOMUNIKACJA":
            continue
        shared = hub.polygon.intersection(room.polygon).length
        assert shared >= 0.5, f"Hub nie dotyka {room.spec.id}: shared={shared:.2f}m"


def test_hub_adjacency_m3():
    boundary = _make_boundary(8.0, 9.0)
    template = [t for t in load_all_templates() if t.id == "M3_standard"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    hub = next(r for r in result.rooms if r.spec.strefa.value == "KOMUNIKACJA")
    for room in result.rooms:
        if room.spec.strefa.value == "KOMUNIKACJA":
            continue
        shared = hub.polygon.intersection(room.polygon).length
        assert shared >= 0.5, f"Hub nie dotyka {room.spec.id}: shared={shared:.2f}m"


def test_window_rooms_on_facade():
    boundary = _make_boundary(8.0, 6.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    for room in result.rooms:
        if not room.spec.wymaga_okna:
            continue
        b = room.polygon.bounds
        touches = (abs(b[0]) < 0.01 or abs(b[2] - 8.0) < 0.01 or abs(b[1]) < 0.01 or abs(b[3] - 6.0) < 0.01)
        assert touches, f"{room.spec.id} nie dotyka fasady: bounds={b}"


def test_room_dimensions_reasonable():
    boundary = _make_boundary(8.0, 6.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    for room in result.rooms:
        assert room.proportion <= 2.05, f"{room.spec.id}: proportion={room.proportion:.2f}"
        if room.spec.min_powierzchnia > 0:
            assert room.area >= room.spec.min_powierzchnia - 0.1


def test_m3_wc_6_rooms():
    """M3 z WC ma 6 pokoi — solver musi je wszystkie zmieścić."""
    boundary = _make_boundary(10.0, 8.0)
    template = [t for t in load_all_templates() if t.id == "M3_wc"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.rooms) == 6


def test_vertical_boundary():
    """Boundary pionowy (height > width) musi działać — jak PL_NL_01 (6x9m)."""
    boundary = _make_boundary(6.0, 9.0)
    template = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    result = solve_cpsat(template, boundary)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    total = sum(r.area for r in result.rooms)
    assert abs(total - 54.0) < 0.05
