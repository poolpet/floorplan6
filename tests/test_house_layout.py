from core.house_layout import generate_house
from shapely.geometry import Polygon


def test_generates_both_storeys_with_full_program():
    poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2)
    assert layout.ok, layout.message
    parter_ids = {r.spec.id for r in layout.parter_rooms}
    pietro_ids = {r.spec.id for r in layout.pietro_rooms}
    assert {"salon", "kuchnia", "wc", "kotlownia"} <= parter_ids
    assert {"sypialnia_1", "sypialnia_2", "sypialnia_3", "lazienka"} <= pietro_ids


def test_staircase_core_identical_on_both_storeys():
    poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2)
    assert layout.ok, layout.message
    sc = layout.stair_core
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        hub = next(r for r in rooms if "hub" in r.spec.id)
        hb = hub.polygon.bounds
        assert hb[0] <= sc[0] + 0.05 and hb[2] >= sc[0] + sc[2] - 0.05
        assert hb[1] <= sc[1] + 0.05 and hb[3] >= sc[1] + sc[3] - 0.05


def test_too_small_footprint_returns_clear_failure_not_crash():
    poly = Polygon([(0, 0), (5, 0), (5, 4), (0, 4)])
    layout = generate_house(poly, entry_point=(2.5, 0.0), num_storeys=2)
    assert layout.ok is False
    assert layout.message
