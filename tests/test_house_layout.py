import pytest
from core.house_layout import generate_house
from shapely.geometry import Polygon

# F2 (FUNDAMENTAL_RULES): twardy cap WT — łazienka ≤ 5 m², WC ≤ 3 m² ZAWSZE,
# niezależnie od wielkości obrysu. Guard dla pipeline'u domu (house_layout):
# solver capuje area przez WT_MAX_AREA (id-prefix), ale dotąd żaden test nie
# sprawdzał tego na WYNIKU generate_house (test_house_templates patrzy tylko na
# opt w szablonie). Na przewymiarowanym obrysie łazienka dociska się do capa
# (4.99) — bez capa uciekłaby >5, więc test realnie bije.
_F2_MAX_AREA = {"lazienka": 5.0, "wc": 3.0}


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


@pytest.mark.parametrize(
    "w,h",
    [
        (11.0, 9.0),    # realny dom ~99 m²/kondygnację
        (16.0, 13.0),   # przewymiarowany — cap dociska łazienkę do ~4.99
    ],
)
def test_house_wet_rooms_never_exceed_wt_cap(w, h):
    """F2: łazienka ≤ 5 m² i WC ≤ 3 m² na WYNIKU solvera, na obu kondygnacjach,
    nawet przy przewymiarowanym obrysie (gdzie F1 wpycha nadmiar w salon)."""
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    layout = generate_house(poly, entry_point=(w / 2, 0.0), time_limit_s=20.0)
    assert layout.ok, layout.message
    for room in (*layout.parter_rooms, *layout.pietro_rooms):
        cap = _F2_MAX_AREA.get(room.spec.id.split("_")[0])
        if cap is not None:
            assert room.area <= cap + 1e-3, (
                f"{room.spec.id} = {room.area:.3f} m² > cap {cap} m² na obrysie {w}x{h}"
            )
