"""Parterowiec — dobór zestawu pokoi wg powierzchni + (Task 4/5) feasibility matrix + inwarianty."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import (
    single_storey_room_ids, MIN_SINGLE_STOREY_AREA, PRZEDSIONEK_MIN_AREA,
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
