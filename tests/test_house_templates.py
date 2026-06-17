"""Tests for single-family house templates (parter + pietro).

Verifies:
1. house_parter template loads with expected rooms.
2. house_pietro template loads with 3 bedrooms, bathroom, and F2 rule (lazienka <= 5.0 m²).
3. House templates are NOT selected when apartment type "M3" is requested.
"""
from core.template_selector import load_all_templates


def _by_id(tid):
    return next((t for t in load_all_templates() if t.id == tid), None)


def test_house_parter_loads_with_expected_rooms():
    t = _by_id("house_parter")
    assert t is not None
    ids = {r.id for r in t.pokoje}
    assert {"hub", "wiatrolap", "salon", "kuchnia", "spizarnia", "lazienka", "kotlownia"} <= ids


def test_house_pietro_loads_with_three_bedrooms_and_bathroom():
    t = _by_id("house_pietro")
    assert t is not None
    ids = {r.id for r in t.pokoje}
    assert {"hub", "sypialnia_1", "sypialnia_2", "sypialnia_3", "lazienka", "garderoba"} <= ids
    laz = next(r for r in t.pokoje if r.id == "lazienka")
    assert laz.opt_powierzchnia <= 5.0


def test_single_storey_template_loads():
    t = _by_id("house_single_storey")
    assert t is not None, "brak szablonu house_single_storey"
    ids = {s.id for s in t.pokoje}
    assert {"hub", "wiatrolap", "salon", "kuchnia", "lazienka", "sypialnia_1"} <= ids
    assert "schody" not in ids, "parterowiec nie ma schodów"
    adj = {(r.room_a, r.room_b) for r in t.sasiedztwo}
    assert ("hub", "wiatrolap") in adj and ("wiatrolap", "_outside") in adj
    assert ("salon", "kuchnia") in adj  # otwarta strefa dzienna


def test_house_templates_not_selected_for_apartments():
    from core.boundary_analyzer import analyze_boundary
    from core.template_selector import select_templates
    from shapely.geometry import Polygon
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    chosen = select_templates("M3", b, load_all_templates())
    assert all(not t.id.startswith("house_") for t in chosen)
