"""Tests asserting PL constants.yaml contains all values needed by code.

This is a contract check: when refactoring config.py, this guarantees the
constants are present in the pack BEFORE we delete them from config.py.
"""
from __future__ import annotations

import pytest

from rules._loader import load_pack


@pytest.fixture(scope="module")
def pl_pack():
    return load_pack("PL")


class TestWTAreas:
    def test_bathroom_max(self, pl_pack):
        assert pl_pack.constants["wt_max_area"]["bathroom_m2"] == 5.0

    def test_wc_max(self, pl_pack):
        assert pl_pack.constants["wt_max_area"]["wc_m2"] == 3.0

    def test_min_areas_have_all_room_types(self, pl_pack):
        expected = {"salon_kawalerka", "salon", "sypialnia_2os", "sypialnia_1os",
                    "kuchnia", "aneks_kuchenny", "lazienka_wanna", "lazienka_prysznic",
                    "wc", "hub"}
        assert set(pl_pack.constants["wt_min_area"].keys()) == expected


class TestHub:
    def test_hub_max_percent(self, pl_pack):
        assert pl_pack.constants["hub_max_percent"] == 0.15

    def test_hub_min_percent_keys(self, pl_pack):
        assert set(pl_pack.constants["hub_min_percent"].keys()) == {"M1", "M2", "M3", "M4", "M5"}


class TestApartments:
    def test_apartment_min_area_m1(self, pl_pack):
        assert pl_pack.constants["apartment_min_area"]["M1"] == 35.0

    def test_apartment_mix_sums_to_one(self, pl_pack):
        mix = pl_pack.constants["apartment_mix_default"]
        assert abs(sum(mix.values()) - 1.0) < 1e-9


class TestBuildingClass:
    def test_thresholds(self, pl_pack):
        bc = pl_pack.constants["building_class"]
        assert bc["N_max_height_m"] == 12.0
        assert bc["SW_max_height_m"] == 25.0
        assert bc["W_max_height_m"] == 55.0


class TestCorridors:
    def test_public_corridor(self, pl_pack):
        assert pl_pack.constants["wt_corridor_public_min"] == 1.4

    def test_internal_corridor(self, pl_pack):
        assert pl_pack.constants["wt_corridor_internal_min"] == 1.2


class TestProportions:
    def test_proportion_absolute_max(self, pl_pack):
        assert pl_pack.constants["proportion_absolute_max"] == 2.5


class TestOrientationQuality:
    def test_south_is_max(self, pl_pack):
        oq = pl_pack.constants["orientation_quality"]
        assert oq["S"] == 1.0

    def test_north_is_min(self, pl_pack):
        oq = pl_pack.constants["orientation_quality"]
        assert oq["N"] == 0.50


class TestModeBSubdivision:
    def test_min_subplot_front(self, pl_pack):
        assert pl_pack.constants["min_subplot_front_m"] == 18.0
