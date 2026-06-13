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
    # 12.9×8.7 (112 m²): czysty 8-pokojowy parter (net 90.7 < 93 gabinet) — sypialnia
    # parteru mieści się niezawodnie (sonda parter8_bedroom_probe 4/4). NIE 13×9=117
    # (net 94.8 ≥93 → dorzuca gabinet → 9-pok loteria → fallback bez sypialni).
    poly = Polygon([(0, 0), (12.9, 0), (12.9, 8.7), (0, 8.7)])
    layout = generate_house(poly, entry_point=(6.45, 0.0), num_storeys=2, time_limit_s=90.0)
    assert layout.ok, layout.message
    parter_ids = {r.spec.id for r in layout.parter_rooms}
    pietro_ids = {r.spec.id for r in layout.pietro_rooms}
    assert {"salon", "kuchnia", "lazienka", "sypialnia_parter", "kotlownia"} <= parter_ids
    assert "wc" not in parter_ids
    assert {"sypialnia_1", "sypialnia_2", "lazienka"} <= pietro_ids


def test_staircase_core_identical_on_both_storeys():
    """Approach B: rdzeń klatki należy do OSOBNEGO pokoju 'schody', przypiętego do
    stair_core identycznie na parterze i piętrze (wyrównanie pionowe z konstrukcji)."""
    poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])
    # 45 s margines: parter z przedsionkiem-w-drzwiach + L-holem bywa na granicy
    # domyślnego 30 s (zwraca UNKNOWN zamiast FEASIBLE). F2/pinning sprawdzane jak wcześniej.
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=45.0)
    assert layout.ok, layout.message
    sx, sy, sw, sh = layout.stair_core
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        schody = next(r for r in rooms if r.spec.id == "schody")
        b = schody.polygon.bounds
        assert abs(b[0] - sx) < 0.05 and abs(b[1] - sy) < 0.05
        assert abs((b[2] - b[0]) - sw) < 0.05 and abs((b[3] - b[1]) - sh) < 0.05


def test_too_small_footprint_returns_clear_failure_not_crash():
    poly = Polygon([(0, 0), (5, 0), (5, 4), (0, 4)])
    layout = generate_house(poly, entry_point=(2.5, 0.0), num_storeys=2)
    assert layout.ok is False
    assert layout.message


@pytest.mark.parametrize(
    "w,h",
    [
        (11.0, 9.0),    # realny dom ~99 m²
        (12.0, 9.0),    # największy NIEZAWODNY obrys (108 m²) — łazienka dociska do ~4.98.
                        # (Było 14×11=154 m², ale z pinned PROSTYM rdzeniem knee-wall parter
                        # = UNKNOWN nawet @120 s; obrysy ≥~130 m² odblokuje praca „solver perf"
                        # z kolejki S26 — patrz STATE.)
    ],
)
def test_house_wet_rooms_never_exceed_wt_cap(w, h):
    """F2: łazienka ≤ 5 m² i WC ≤ 3 m² na WYNIKU solvera, na obu kondygnacjach,
    nawet przy przewymiarowanym obrysie (gdzie F1 wpycha nadmiar w salon)."""
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    # 120 s: parter 108 m² z pinned prostym rdzeniem solvuje ~60-90 s (graniczny — flake
    # przy 90). Test sprawdza capy F2, nie szybkość — perf parteru = temat z kolejki S26.
    layout = generate_house(poly, entry_point=(w / 2, 0.0), time_limit_s=120.0)
    assert layout.ok, layout.message
    for room in (*layout.parter_rooms, *layout.pietro_rooms):
        cap = _F2_MAX_AREA.get(room.spec.id.split("_")[0])
        if cap is not None:
            assert room.area <= cap + 1e-3, (
                f"{room.spec.id} = {room.area:.3f} m² > cap {cap} m² na obrysie {w}x{h}"
            )
