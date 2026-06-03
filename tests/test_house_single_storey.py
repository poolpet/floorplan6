"""Parterowiec — dobór zestawu pokoi wg powierzchni + (Task 4/5) feasibility matrix + inwarianty."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import (
    generate_house, single_storey_room_ids, MIN_SINGLE_STOREY_AREA, PRZEDSIONEK_MIN_AREA,
)
from core.template_selector import load_all_templates


def _specs():
    t = next(t for t in load_all_templates() if t.id == "house_single_storey")
    return t.pokoje


# --- Task 3: selektor zestawu pokoi (szybkie, bez CP-SAT) ---
def test_core_rooms_always_present():
    ids = set(single_storey_room_ids(_specs(), 46.0))
    assert {"hub", "salon", "kuchnia", "lazienka", "sypialnia_1"} <= ids


def test_no_przedsionek_below_threshold():
    ids = single_storey_room_ids(_specs(), PRZEDSIONEK_MIN_AREA - 1.0)
    assert "wiatrolap" not in ids


def test_przedsionek_appears_at_threshold():
    ids = single_storey_room_ids(_specs(), PRZEDSIONEK_MIN_AREA + 5.0)
    assert "wiatrolap" in ids


def test_bedrooms_scale_with_area():
    small = single_storey_room_ids(_specs(), 46.0)
    large = single_storey_room_ids(_specs(), 120.0)
    assert "sypialnia_2" not in small
    assert "sypialnia_2" in large and "sypialnia_3" in large


def test_min_set_area_sum_fits():
    # zestaw przy MIN nie może wymagać więcej m² niż obrys (suma minów ≤ area)
    specs = {s.id: s for s in _specs()}
    ids = single_storey_room_ids(_specs(), MIN_SINGLE_STOREY_AREA)
    assert sum(specs[i].min_powierzchnia for i in ids) <= MIN_SINGLE_STOREY_AREA + 1e-6


# --- Task 4/5: gałąź generate_house(num_storeys=1) ---
_CACHE = {}


def _gen1(W, H, entry, t=25.0):
    key = (W, H, entry)
    if key not in _CACHE:
        _CACHE[key] = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), entry,
                                     num_storeys=1, time_limit_s=t)
    return _CACHE[key]


def test_single_storey_generates_and_has_no_stairs():
    lay = _gen1(8.0, 8.0, (4.0, 0.0))
    assert lay.ok, lay.message
    ids = {r.spec.id for r in lay.parter_rooms}
    assert "schody" not in ids
    assert {"hub", "salon", "sypialnia_1", "lazienka"} <= ids
    assert lay.pietro_rooms == []   # jedna kondygnacja


def test_single_storey_too_small_clean_failure():
    lay = _gen1(5.0, 7.0, (2.5, 0.0))   # 35 m² < MIN_SINGLE_STOREY_AREA
    assert lay.ok is False and lay.message


def test_suggest_storeys_by_area():
    from core.house_layout import suggest_storeys
    assert suggest_storeys(48.0) == 1
    assert suggest_storeys(110.0) == 2


# --- Task 5: feasibility matrix + inwarianty (sędzia progów) ---
_MATRIX = [
    (7.0, 7.0, (3.5, 0.0)), (8.0, 8.0, (4.0, 0.0)), (8.0, 8.0, (0.0, 4.0)),
    (8.0, 8.0, (8.0, 4.0)), (8.0, 8.0, (4.0, 8.0)),
    (9.0, 9.0, (4.5, 0.0)), (10.0, 10.0, (5.0, 0.0)), (11.0, 11.0, (5.5, 0.0)),
]

# kuchnia/spiżarnia łączą się ze strefą dzienną (salon↔kuchnia "opening",
# kuchnia↔spiżarnia), NIE bezpośrednio z holem — wyłączone z reguły hub-touch (F5).
_HUB_EXEMPT = {"kuchnia", "spizarnia"}


@pytest.mark.parametrize("W,H,entry", _MATRIX)
def test_single_storey_feasible_matrix(W, H, entry):
    lay = _gen1(W, H, entry)
    assert lay.ok, f"{W}x{H} entry {entry}: {lay.message}"


@pytest.mark.parametrize("W,H,entry", _MATRIX)
def test_single_storey_invariants(W, H, entry):
    lay = _gen1(W, H, entry)
    assert lay.ok, lay.message
    usable = W * H
    rooms = lay.parter_rooms
    # F1: pokrycie == usable + brak nakładania
    assert abs(sum(r.polygon.area for r in rooms) - usable) < 1e-2, f"pokrycie != usable ({W}x{H})"
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            assert rooms[i].polygon.intersection(rooms[j].polygon).area < 1e-3, \
                f"nakładanie {rooms[i].spec.id}∩{rooms[j].spec.id} ({W}x{H})"
    # F4 jest MIĘKKIE (objective, nie twarde) — hol parterowca dotyka ~9 pokoi na jednej
    # gwieździe (dzienna+nocna razem), więc zwykle ~10-12% ale SPORADYCZNIE do ~17%.
    # Decyzja Dawida 2026-06-03 (opcja A): akceptuj miękkie F4, hardening odłożony do fazy
    # mebli. Tu sufit anty-spine (gross-bloat guard), nie twarde 15%. F2: lazienka ≤5, wc ≤3.
    hub = next(r for r in rooms if r.spec.id == "hub")
    assert hub.area <= 0.20 * usable, f"hol {hub.area:.1f} ({100*hub.area/usable:.0f}%) > 20% = spine? ({W}x{H})"
    for r in rooms:
        cap = {"lazienka": 5.0, "wc": 3.0}.get(r.spec.id.split("_")[0])
        if cap is not None:
            assert r.area <= cap + 1e-3, f"{r.spec.id}={r.area:.2f} > {cap} ({W}x{H})"
    # F5: każdy pokój sąsiadujący z holem (poza strefą dzienną) dotyka go ≥0.9 m
    for r in rooms:
        if r.spec.id == "hub" or r.spec.id in _HUB_EXEMPT:
            continue
        shared = hub.polygon.boundary.intersection(r.polygon.boundary).length
        assert shared >= 0.9 - 1e-6, f"{r.spec.id}↔hol {shared:.2f} < 0.9 ({W}x{H})"
