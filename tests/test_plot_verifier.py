"""
Stage 1 regression tests — plot verifier.

Covers Q13/Q17 gating (well/septic skip rules), Q14 5% warning band +
strict flag, all 5 verification categories.
"""
import pytest
from shapely.geometry import LineString, Point, Polygon

from core.plot_indicators import PlotIndicatorCalculator, PlotIndicators
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_verifier import (
    PlotVerifier,
    VerificationStatus,
)
from core.site_element_model import SiteElement, SiteElementType
from core.site_wall_model import SiteWall, WallOpeningType


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _plot(
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    infrastructure_municipal: bool = True,
    max_wz: float = 0.30,
    min_pbc: float = 40.0,
) -> Plot:
    poly = Polygon([(0, 0), (40, 0), (40, 30), (0, 30)])  # 1200 m²
    coords = [(0, 0), (40, 0), (40, 30), (0, 30), (0, 0)]
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
    return Plot(
        number="P1",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=max_wz,
            max_wiz=0.60,
            min_pbc_percent=min_pbc,
            infrastructure_municipal=infrastructure_municipal,
        ),
        housing_type=housing_type,
    )


def _building(width=10.0, length=12.0, floors=2, x=20.0, y=15.0) -> SiteElement:
    el = SiteElement(
        element_type=SiteElementType.BUDYNEK_GLOWNY,
        position=Point(x, y),
        width=width,
        length=length,
        height=floors * 3.0,
        floors=floors,
    )
    el.set_geometry_from_position()
    return el


def _well(x=5.0, y=5.0) -> SiteElement:
    el = SiteElement(
        element_type=SiteElementType.STUDNIA,
        position=Point(x, y),
        width=1.5,
        length=1.5,
    )
    el.set_geometry_from_position()
    return el


def _septic(x=35.0, y=5.0) -> SiteElement:
    el = SiteElement(
        element_type=SiteElementType.SZAMBO,
        position=Point(x, y),
        width=3.0,
        length=4.0,
    )
    el.set_geometry_from_position()
    return el


def _indicators(plot: Plot, elements: list) -> PlotIndicators:
    return PlotIndicatorCalculator().compute(plot, elements)


def _result_by_id(results, rule_id):
    matches = [r for r in results if r.rule_id == rule_id]
    return matches[0] if matches else None


# ─────────────────────────────────────────────────────────────────────────────
# Indicators (WZ / WIZ / PBC) — Q14 band behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestIndicators:

    def test_wz_within_limit_is_zgodny(self):
        plot = _plot(max_wz=0.30)
        # Building 10×12 = 120 m² on a 1200 m² plot → WZ = 0.10
        elements = [_building(10, 12)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier().verify(plot, elements, walls=[], indicators=indicators)
        wz = _result_by_id(results, "wt_014")
        assert wz.status == VerificationStatus.ZGODNY

    def test_wz_in_5pct_band_is_warning(self):
        """WZ 1.7% over → in 5% band → OSTRZEZENIE (Q14a)."""
        plot = _plot(max_wz=0.30)
        # Building 12×30.5 = 366 m² on 1200 m² → WZ ≈ 0.305 (1.7% over 0.30)
        elements = [_building(12, 30.5)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier(strict=False).verify(plot, elements, [], indicators)
        wz = _result_by_id(results, "wt_014")
        assert wz.status == VerificationStatus.OSTRZEZENIE
        assert "5%" in wz.description

    def test_wz_far_over_limit_is_violation(self):
        """WZ 33% over → outside 5% band → NIEZGODNY."""
        plot = _plot(max_wz=0.30)
        # Building 20×24 = 480 m² → WZ = 0.40 (33% over 0.30)
        elements = [_building(20, 24)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier().verify(plot, elements, [], indicators)
        wz = _result_by_id(results, "wt_014")
        assert wz.status == VerificationStatus.NIEZGODNY

    def test_strict_flag_collapses_band_to_violation(self):
        """In strict mode, the same 1.7%-over case is NIEZGODNY (no band)."""
        plot = _plot(max_wz=0.30)
        elements = [_building(12, 30.5)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier(strict=True).verify(plot, elements, [], indicators)
        wz = _result_by_id(results, "wt_014")
        assert wz.status == VerificationStatus.NIEZGODNY


# ─────────────────────────────────────────────────────────────────────────────
# Q13 / Q17 gating for well/septic checks
# ─────────────────────────────────────────────────────────────────────────────

class TestWellSepticGating:

    def test_q13_municipal_infrastructure_skips_well_septic(self):
        """infrastructure_municipal=True → wt_004/wt_005/wt_006/wt_007 skipped."""
        plot = _plot(housing_type=HousingType.JEDNORODZINNA,
                     infrastructure_municipal=True)
        elements = [_building(), _well(x=1.0, y=1.0), _septic(x=2.0, y=1.0)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier().verify(plot, elements, [], indicators)
        ids = {r.rule_id for r in results}
        assert "wt_004" not in ids
        assert "wt_005" not in ids
        assert "wt_006" not in ids
        assert "wt_007" not in ids

    def test_q17_multifamily_always_skips_well_septic(self):
        """WIELORODZINNA + infrastructure_municipal=False → still skipped (Q17)."""
        plot = _plot(housing_type=HousingType.WIELORODZINNA,
                     infrastructure_municipal=False)
        elements = [_building(), _well(x=1.0, y=1.0)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier().verify(plot, elements, [], indicators)
        ids = {r.rule_id for r in results}
        assert "wt_004" not in ids
        assert "wt_005" not in ids

    def test_rural_jednorodzinna_runs_well_septic(self):
        """JEDNORODZINNA + infrastructure_municipal=False → checks active."""
        plot = _plot(housing_type=HousingType.JEDNORODZINNA,
                     infrastructure_municipal=False)
        # Place well at corner with 3m offset → less than 5m WT requires
        elements = [_building(), _well(x=3.0, y=3.0), _septic(x=37.0, y=3.0)]
        indicators = _indicators(plot, elements)

        results = PlotVerifier().verify(plot, elements, [], indicators)
        well_check = _result_by_id(results, "wt_004")
        assert well_check is not None
        assert well_check.status in (
            VerificationStatus.NIEZGODNY,
            VerificationStatus.OSTRZEZENIE,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wall setbacks
# ─────────────────────────────────────────────────────────────────────────────

class TestWallSetbacks:

    def test_wall_with_openings_3m_compliant(self):
        plot = _plot()
        wall = SiteWall(
            geometry=LineString([(10, 5), (20, 5)]),
            wall_type=WallOpeningType.Z_OTWORAMI,
            index=0,
            near_boundary=True,
            distance_to_boundary=5.0,
        )
        indicators = _indicators(plot, [_building()])
        results = PlotVerifier().verify(plot, [_building()], [wall], indicators)
        wall_result = _result_by_id(results, "sciana_0")
        assert wall_result.status == VerificationStatus.ZGODNY

    def test_wall_with_openings_too_close_violates(self):
        plot = _plot()
        wall = SiteWall(
            geometry=LineString([(10, 1), (20, 1)]),
            wall_type=WallOpeningType.Z_OTWORAMI,
            index=0,
            near_boundary=True,
            distance_to_boundary=1.0,   # below WT min 3.0m for openings
        )
        indicators = _indicators(plot, [_building()])
        results = PlotVerifier().verify(plot, [_building()], [wall], indicators)
        wall_result = _result_by_id(results, "sciana_0")
        assert wall_result.status == VerificationStatus.NIEZGODNY

    def test_wall_without_openings_1_5m_compliant(self):
        plot = _plot()
        wall = SiteWall(
            geometry=LineString([(10, 1.6), (20, 1.6)]),
            wall_type=WallOpeningType.BEZ_OTWOROW,
            index=0,
            near_boundary=True,
            distance_to_boundary=1.6,
        )
        indicators = _indicators(plot, [_building()])
        results = PlotVerifier().verify(plot, [_building()], [wall], indicators)
        wall_result = _result_by_id(results, "sciana_0")
        assert wall_result.status == VerificationStatus.ZGODNY


# ─────────────────────────────────────────────────────────────────────────────
# Parking
# ─────────────────────────────────────────────────────────────────────────────

class TestParking:

    def test_insufficient_parking_violates(self):
        """1 unit MN → 2 spaces required (default), 0 designed → NIEZGODNY."""
        plot = _plot()
        elements = [_building()]
        indicators = _indicators(plot, elements)
        # No parking elements → designed = 0
        assert indicators.designed_parking_spaces == 0

        results = PlotVerifier().verify(plot, elements, [], indicators)
        parking = _result_by_id(results, "mpzp_parkingi")
        assert parking.status == VerificationStatus.NIEZGODNY


# ─────────────────────────────────────────────────────────────────────────────
# Conditional warnings
# ─────────────────────────────────────────────────────────────────────────────

class TestConditionalWarnings:

    def test_wall_no_openings_under_3m_emits_project_requirement(self):
        plot = _plot()
        wall = SiteWall(
            geometry=LineString([(10, 2), (20, 2)]),
            wall_type=WallOpeningType.BEZ_OTWOROW,
            index=0,
            near_boundary=True,
            distance_to_boundary=2.0,
            boundary_type_label="SASIAD_NIEZABUDOWANY",
        )
        verifier = PlotVerifier()
        warnings = verifier.generate_conditional_warnings([wall], plot)
        assert len(warnings) == 1
        assert "BEZ otworów" in warnings[0]
        assert "2.00 m" in warnings[0]

    def test_wall_no_openings_at_3m_does_not_emit(self):
        plot = _plot()
        wall = SiteWall(
            geometry=LineString([(10, 3), (20, 3)]),
            wall_type=WallOpeningType.BEZ_OTWOROW,
            index=0,
            near_boundary=True,
            distance_to_boundary=3.0,
        )
        warnings = PlotVerifier().generate_conditional_warnings([wall], plot)
        assert warnings == []


# ─────────────────────────────────────────────────────────────────────────────
# Sorting
# ─────────────────────────────────────────────────────────────────────────────

class TestSorting:

    def test_results_sorted_violations_first(self):
        """NIEZGODNY < OSTRZEZENIE < ZGODNY in result order."""
        plot = _plot(max_wz=0.30)
        # Force WZ violation
        elements = [_building(20, 24)]   # WZ = 0.40 → NIEZGODNY
        indicators = _indicators(plot, elements)
        # Set PBC correct
        results = PlotVerifier().verify(plot, elements, [], indicators)

        statuses = [r.status for r in results]
        # First violation must come before any compliant result
        first_zgodny_idx = next(
            (i for i, s in enumerate(statuses) if s == VerificationStatus.ZGODNY),
            len(statuses),
        )
        first_niezgodny_idx = next(
            (i for i, s in enumerate(statuses) if s == VerificationStatus.NIEZGODNY),
            len(statuses),
        )
        assert first_niezgodny_idx < first_zgodny_idx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
