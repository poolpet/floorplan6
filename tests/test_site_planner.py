"""
Stage 1 regression tests — site planner (auxiliary element placement
and variant generation).

Covers:
  - Mode 1 (propose_max_buildup) variant generation
  - Mode 2 (place_building) success + failure messaging
  - Q13 gating — municipal infrastructure skips well/septic
  - Q17 gating — multi-family always skips well/septic, parking row scaled
  - Inscribed-rect fix (variants produce non-trivial footprints, not 4×4 floor)
"""
import pytest
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.site_element_model import SiteElementType
from core.site_planner import SitePlanner


def _plot(
    width: float = 40.0,
    depth: float = 30.0,
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    infrastructure_municipal: bool = True,
    parking_per_unit: float = 2.0,
    max_floors: int = 2,
) -> Plot:
    poly = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
    coords = [(0, 0), (width, 0), (width, depth), (0, depth), (0, 0)]
    types = [
        BoundaryType.DROGA,
        BoundaryType.SASIAD_ZABUDOWANY,
        BoundaryType.WLASNA,
        BoundaryType.SASIAD_NIEZABUDOWANY,
    ]
    boundaries = [
        PlotBoundary(LineString([coords[i], coords[i + 1]]), types[i], i)
        for i in range(4)
    ]
    plot = Plot(
        number="P-test",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            max_wiz=0.60,
            max_floors=max_floors,
            infrastructure_municipal=infrastructure_municipal,
            parking_spaces_per_unit=parking_per_unit,
        ),
        housing_type=housing_type,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def _types_in(elements):
    return {el.element_type for el in elements}


# ─────────────────────────────────────────────────────────────────────────────
# Mode 1 — propose_max_buildup
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeMaxBuildup:

    def test_returns_at_most_3_variants(self):
        plot = _plot(max_floors=3)
        variants = SitePlanner().propose_max_buildup(
            plot,
            requested_element_types=[SiteElementType.MIEJSCE_POSTOJOWE],
        )
        assert 1 <= len(variants) <= 3

    def test_variants_have_main_building(self):
        plot = _plot()
        variants = SitePlanner().propose_max_buildup(
            plot, [SiteElementType.MIEJSCE_POSTOJOWE]
        )
        assert all(v.main_building.element_type == SiteElementType.BUDYNEK_GLOWNY
                   for v in variants)

    def test_inscribe_rect_finds_substantial_footprint(self):
        """Source bug — inscribe broke on first 4m fit. Fixed: footprint > 30m²."""
        plot = _plot(width=40.0, depth=30.0)
        variants = SitePlanner().propose_max_buildup(plot, [])
        assert variants
        # Buildable zone for 40×30 with mixed setbacks ≈ 600 m²; first variant
        # should easily exceed 30 m² footprint (used to be 16 m² with the bug).
        assert variants[0].footprint_area > 30.0

    def test_variant_respects_wz_limit(self):
        plot = _plot()
        variants = SitePlanner().propose_max_buildup(plot, [])
        # 5% absolute tolerance is OK — we check that we don't massively overshoot
        assert all(v.wz <= plot.mpzp.max_wz * 1.05 for v in variants)

    def test_raises_without_buildable_zone(self):
        poly = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
        plot = Plot(number="No zone", geometry=poly)
        with pytest.raises(ValueError):
            SitePlanner().propose_max_buildup(plot, [])


# ─────────────────────────────────────────────────────────────────────────────
# Mode 2 — place_building
# ─────────────────────────────────────────────────────────────────────────────

class TestPlaceBuilding:

    def test_small_building_placed(self):
        plot = _plot(width=40.0, depth=30.0)
        building, msg = SitePlanner().place_building(plot, width=10.0, length=12.0)
        assert msg is None
        assert building is not None
        assert plot.buildable_zone.contains(building.geometry)

    def test_too_large_building_reports_failure(self):
        plot = _plot(width=20.0, depth=20.0)
        building, msg = SitePlanner().place_building(plot, width=18.0, length=18.0)
        assert building is None
        assert msg is not None
        assert "nie mieści" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Q13 / Q17 gating
# ─────────────────────────────────────────────────────────────────────────────

class TestGating:

    def test_q13_municipal_skips_well_septic(self):
        plot = _plot(infrastructure_municipal=True,
                     housing_type=HousingType.JEDNORODZINNA)
        variants = SitePlanner().propose_max_buildup(
            plot,
            [
                SiteElementType.STUDNIA,
                SiteElementType.SZAMBO,
                SiteElementType.MIEJSCE_POSTOJOWE,
            ],
        )
        for v in variants:
            types = _types_in(v.elements)
            assert SiteElementType.STUDNIA not in types
            assert SiteElementType.SZAMBO not in types

    def test_q13_rural_jednorodzinna_places_well_and_septic(self):
        # Use a larger plot so the building footprint doesn't crowd out the septic
        # placement zone (5m setback + 3×4 box at the rear boundary).
        plot = _plot(width=60.0, depth=50.0,
                     infrastructure_municipal=False,
                     housing_type=HousingType.JEDNORODZINNA)
        variants = SitePlanner().propose_max_buildup(
            plot,
            [
                SiteElementType.STUDNIA,
                SiteElementType.SZAMBO,
                SiteElementType.MIEJSCE_POSTOJOWE,
            ],
        )
        # First variant must include both well AND septic
        types = _types_in(variants[0].elements)
        assert SiteElementType.STUDNIA in types
        assert SiteElementType.SZAMBO in types

    def test_q17_multifamily_skips_well_septic_unconditionally(self):
        """Even with infrastructure_municipal=False, multi-family skips well/septic."""
        plot = _plot(infrastructure_municipal=False,
                     housing_type=HousingType.WIELORODZINNA)
        variants = SitePlanner().propose_max_buildup(
            plot,
            [
                SiteElementType.STUDNIA,
                SiteElementType.SZAMBO,
                SiteElementType.MIEJSCE_POSTOJOWE,
            ],
        )
        for v in variants:
            types = _types_in(v.elements)
            assert SiteElementType.STUDNIA not in types
            assert SiteElementType.SZAMBO not in types


# ─────────────────────────────────────────────────────────────────────────────
# Multi-family parking adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestMultifamilyParking:

    def test_parking_scales_with_units(self):
        """Multi-family building with N units → parking has at least N stalls."""
        plot = _plot(
            width=60.0, depth=40.0,                 # bigger plot for big parking row
            housing_type=HousingType.WIELORODZINNA,
            parking_per_unit=1.5,
            max_floors=3,
        )
        variants = SitePlanner().propose_max_buildup(
            plot, [SiteElementType.MIEJSCE_POSTOJOWE]
        )
        v = variants[0]
        building = v.main_building
        parking = next(
            (e for e in v.elements if e.element_type == SiteElementType.MIEJSCE_POSTOJOWE),
            None,
        )
        assert parking is not None
        # building.units = floors × 4 for multi-family in our heuristic
        expected_min = int(round(building.units * plot.mpzp.parking_spaces_per_unit))
        assert parking.metadata["space_count"] >= expected_min

    def test_single_family_parking_is_one_stall(self):
        plot = _plot(housing_type=HousingType.JEDNORODZINNA)
        variants = SitePlanner().propose_max_buildup(
            plot, [SiteElementType.MIEJSCE_POSTOJOWE]
        )
        parking = next(
            (e for e in variants[0].elements
             if e.element_type == SiteElementType.MIEJSCE_POSTOJOWE),
            None,
        )
        assert parking is not None
        assert parking.metadata["space_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
