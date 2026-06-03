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


# --- Task 4: gałąź generate_house(num_storeys=1) ---
def _gen1(W, H, entry, t=25.0):
    return generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), entry,
                          num_storeys=1, time_limit_s=t)


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
