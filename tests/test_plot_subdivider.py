"""
Stage 1 Mode B regression tests — plot subdivision.

Anti-bug regressions vs C++ Plot Subdivider session 2026-04-29:
  #1 sub-plots overflow parent boundary
  #2 internal roads overflow parent boundary
  #3 buildable zone ignored (sub-plots in parent outline, not respecting zone)
  #4 absurd sub-plot count (36 inserted where ~10 fit)

Plus tests for:
  Q12 — Mode B single-family only
  Q3(c) — TERRACED/TWIN requires direct parent's-DROGA touch
  Q15  — min_front threshold
  Q16(a) — strict coverage equality
"""
import pytest
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_subdivider import (
    BuildingType,
    subdivide,
    subdivide_with_orientation_search,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_plot(
    points,
    boundary_types,
    *,
    housing_type=HousingType.JEDNORODZINNA,
    min_front=18.0,
    min_road_width=4.5,
):
    poly = Polygon(points)
    coords = list(points) + [points[0]]
    boundaries = [
        PlotBoundary(
            geometry=LineString([coords[i], coords[i + 1]]),
            boundary_type=boundary_types[i],
            segment_index=i,
        )
        for i in range(len(points))
    ]
    plot = Plot(
        number="P",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            min_front_m=min_front,
            min_road_width_m=min_road_width,
        ),
        housing_type=housing_type,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def _rectangular(width=60, depth=80):
    return _make_plot(
        [(0, 0), (width, 0), (width, depth), (0, depth)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def _l_shape():
    return _make_plot(
        [(0, 0), (80, 0), (80, 30), (50, 30), (50, 60), (0, 60)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def _wide_trapezoid():
    """Irregular AC-like parcel: public road is the short bottom edge."""
    return _make_plot(
        [(0, 0), (62, 0), (188, 401), (-22, 384)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def _wide_screen_plot():
    plot = _make_plot(
        [(0, 0), (401.84, 0), (401.84, 188.04), (0, 188.04)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )
    plot.mpzp.min_sub_plot_area_m2 = 400.0
    plot.mpzp.max_sub_plot_area_m2 = 600.0
    return plot


def _wide_sloped_screen_plot():
    plot = _make_plot(
        [(0, 37), (401.84, 0), (401.84, 188.04), (0, 188.04)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )
    plot.mpzp.min_sub_plot_area_m2 = 400.0
    plot.mpzp.max_sub_plot_area_m2 = 800.0
    return plot


def _shallow_concave_plot():
    plot = _make_plot(
        [(0, 22), (200.73, 0), (185, 64), (72, 68.61), (66, 43), (8, 56)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )
    plot.mpzp.min_sub_plot_area_m2 = 400.0
    plot.mpzp.max_sub_plot_area_m2 = 800.0
    return plot


def _wide_parallel_top_road_plot():
    plot = _make_plot(
        [(0, 38), (401.84, 0), (401.84, 150), (0, 188.04)],
        [
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.DROGA,
            BoundaryType.WLASNA,
        ],
    )
    plot.mpzp.min_sub_plot_area_m2 = 400.0
    plot.mpzp.max_sub_plot_area_m2 = 800.0
    return plot


# ─────────────────────────────────────────────────────────────────────────────
# Q12 — Mode B single-family only
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleFamilyOnly:

    def test_multifamily_plot_raises(self):
        plot = _make_plot(
            [(0, 0), (60, 0), (60, 80), (0, 80)],
            [BoundaryType.DROGA, BoundaryType.SASIAD_NIEZABUDOWANY,
             BoundaryType.WLASNA, BoundaryType.SASIAD_NIEZABUDOWANY],
            housing_type=HousingType.WIELORODZINNA,
        )
        with pytest.raises(ValueError, match="single-family only"):
            subdivide(plot)


# ─────────────────────────────────────────────────────────────────────────────
# Anti-bug regressions (C++ Plot Subdivider 2026-04-29)
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiBugRegressions:

    def test_bug1_sub_plots_inside_parent(self):
        """#1: every sub-plot must be contained in parent.geometry."""
        for plot in [_rectangular(), _l_shape()]:
            result = subdivide(plot)
            for s in result.sub_plots:
                # Allow tiny floating-point overshoot via small tolerance
                assert plot.geometry.buffer(0.01).contains(s.polygon), \
                    f"Sub-plot overflows parent on {plot.number}"

    def test_bug2_roads_inside_parent(self):
        """#2: every internal road segment must be contained in parent.geometry."""
        for plot in [_rectangular(), _l_shape()]:
            result = subdivide(plot)
            for road in result.roads:
                assert plot.geometry.buffer(0.01).contains(road), \
                    f"Road overflows parent on {plot.number}"

    def test_bug3_every_sub_plot_has_buildable_zone(self):
        """#3: each kept sub-plot must have a non-empty per-sub-plot zone."""
        for plot in [_rectangular(), _l_shape()]:
            result = subdivide(plot)
            assert result.sub_plots, "Expected at least one sub-plot"
            for s in result.sub_plots:
                assert s.has_buildable_zone, \
                    f"Sub-plot in {plot.number} has empty buildable zone"
                assert s.buildable_zone.area > 0

    def test_bug4_no_excess_sub_plot_count(self):
        """#4: sanity bound — sub-plot count ≤ floor(area / (min_front × min_depth))."""
        plot = _rectangular(60, 80)
        result = subdivide(plot)
        # 60×80 plot, min_front 18m, min depth ~25m → upper bound ~10 sub-plots
        max_reasonable = int(plot.area / (18 * 25))   # = 10
        assert len(result.sub_plots) <= max_reasonable + 1, \
            f"Too many sub-plots: {len(result.sub_plots)} (expected ≤ {max_reasonable})"


# ─────────────────────────────────────────────────────────────────────────────
# Q16(a) strict coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestStrictCoverage:

    def test_rectangle_strict_coverage(self):
        plot = _rectangular(60, 80)
        result = subdivide(plot)
        assert result.coverage_ok(), \
            f"Coverage diff = {result.coverage_diff:.3f} m² (expected < 0.5)"

    def test_l_shape_strict_coverage(self):
        plot = _l_shape()
        result = subdivide(plot)
        assert result.coverage_ok(), \
            f"Coverage diff = {result.coverage_diff:.3f} m² (expected < 0.5)"

    def test_orientation_search_preserves_coverage(self):
        for plot in [_rectangular(), _l_shape(), _rectangular(30, 100)]:
            result = subdivide_with_orientation_search(plot)
            assert result.coverage_ok(), \
                f"Coverage diff = {result.coverage_diff:.3f} on {plot.number}"


# ─────────────────────────────────────────────────────────────────────────────
# Q15 min_front
# ─────────────────────────────────────────────────────────────────────────────

class TestMinFront:

    def test_default_18m_min_front(self):
        plot = _rectangular(60, 80)
        result = subdivide(plot)
        # 60 / 18 = 3 cols; each cell ≥ 18m wide pre-clip; allow some clip slack
        for s in result.sub_plots:
            cw = s.polygon.bounds[2] - s.polygon.bounds[0]
            ch = s.polygon.bounds[3] - s.polygon.bounds[1]
            assert min(cw, ch) >= 18 * 0.85, \
                f"Sub-plot dimension {min(cw, ch):.1f} < 0.85 × min_front"

    def test_mpzp_override_increases_min_front(self):
        """Increasing min_front to 25m should reduce sub-plot count."""
        plot_18 = _rectangular(60, 80)
        plot_25 = _make_plot(
            [(0, 0), (60, 0), (60, 80), (0, 80)],
            [BoundaryType.DROGA, BoundaryType.SASIAD_NIEZABUDOWANY,
             BoundaryType.WLASNA, BoundaryType.SASIAD_NIEZABUDOWANY],
            min_front=25.0,
        )
        r_18 = subdivide(plot_18)
        r_25 = subdivide(plot_25)
        # 60/18 = 3 cols, 60/25 = 2 cols → fewer sub-plots
        assert len(r_25.sub_plots) <= len(r_18.sub_plots)


# ─────────────────────────────────────────────────────────────────────────────
# Q3(c) — TERRACED/TWIN front-to-parent's-DROGA
# ─────────────────────────────────────────────────────────────────────────────

class TestQ3FrontToRoad:

    def test_terraced_drops_internal_road_only_sub_plots(self):
        """For TERRACED, sub-plots fronting internal road only are demoted."""
        plot = _rectangular(60, 80)
        r_detached = subdivide(plot, building_type=BuildingType.DETACHED)
        r_terraced = subdivide(plot, building_type=BuildingType.TERRACED)
        # Detached keeps both rows; terraced keeps only row touching parent's DROGA
        assert len(r_terraced.sub_plots) <= len(r_detached.sub_plots)
        for s in r_terraced.sub_plots:
            assert s.parent_droga_touch > 0, \
                "TERRACED sub-plot must touch parent's DROGA directly"

    def test_twin_same_constraint_as_terraced(self):
        plot = _rectangular(60, 80)
        r_twin = subdivide(plot, building_type=BuildingType.TWIN)
        for s in r_twin.sub_plots:
            assert s.parent_droga_touch > 0

    def test_detached_accepts_internal_road_sub_plots(self):
        """For DETACHED, sub-plots fronting internal road only are still OK."""
        plot = _rectangular(60, 260)
        r = subdivide(plot, building_type=BuildingType.DETACHED)
        # Should have sub-plots in both rows
        any_internal_only = any(
            s.parent_droga_touch == 0 and s.internal_road_touch > 0
            for s in r.sub_plots
        )
        assert any_internal_only, \
            "Expected at least one DETACHED sub-plot fronting only internal road"


# ─────────────────────────────────────────────────────────────────────────────
# Road tree invariants — owner feedback 2026-05-10
# ─────────────────────────────────────────────────────────────────────────────

class TestRoadTreeUrbanRules:

    def test_internal_roads_do_not_dead_end_on_non_road_boundary(self):
        """Internal road tree must not waste land by reaching non-DROGA edge."""
        plot = _wide_trapezoid()
        result = subdivide(plot)
        assert result.roads, "Expected internal roads for deep irregular plot"

        road_union = unary_union(result.roads)
        non_road_touch = sum(
            road_union.boundary.intersection(boundary.geometry.buffer(0.05)).length
            for boundary in plot.boundaries
            if boundary.boundary_type != BoundaryType.DROGA
        )

        assert non_road_touch < plot.mpzp.min_road_width_m * 0.5, (
            "Internal roads should not terminate on non-DROGA plot boundary; "
            f"touch length={non_road_touch:.2f}m"
        )

    def test_detached_sub_plots_do_not_have_many_redundant_fronts(self):
        """A plot is a leaf; only entry-corner plots may have two road sides."""
        plot = _wide_trapezoid()
        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.sub_plots, "Expected detached sub-plots"
        for sub in result.sub_plots:
            assert sub.front_length > 0.5, "Detached sub-plot has no road access"

        redundant_fronts = [
            sub for sub in result.sub_plots
            if sub.parent_droga_touch > 0.5 and sub.internal_road_touch > 0.5
        ]
        redundant_ratio = len(redundant_fronts) / len(result.sub_plots)
        assert redundant_ratio <= 0.15, (
            "Only a small entry/front-row minority may consume both parent "
            "DROGA and internal-road frontage; "
            f"ratio={redundant_ratio:.1%}"
        )

    def test_wide_small_lots_do_not_create_central_wasteland(self):
        """Regression for AC screenshot: max_area=600 must not dump center."""
        plot = _wide_screen_plot()
        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.coverage_ok(), (
            f"Coverage diff={result.coverage_diff:.2f}m²"
        )
        assert result.sub_plots_without_road_access == 0
        assert result.nieuzytek_percent < 5.0, (
            f"Nieużytek too high: {result.nieuzytek_percent:.1f}%"
        )
        assert result.nieuzytek_area < 0.5, (
            f"Small geometric leftovers should be absorbed, got "
            f"{result.nieuzytek_area:.2f}m²"
        )
        assert all(
            plot.mpzp.min_sub_plot_area_m2 <= s.area <= plot.mpzp.max_sub_plot_area_m2
            for s in result.sub_plots
        )

    def test_wide_medium_lots_minimize_internal_road_area(self):
        """Road-tree should not put most lots between two internal roads."""
        plot = _wide_screen_plot()
        plot.mpzp.max_sub_plot_area_m2 = 800.0

        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.sub_plots_without_road_access == 0
        assert result.road_area_percent < 6.5, (
            f"Road area too high: {result.road_area_percent:.1f}%"
        )

    def test_absorption_does_not_create_oversized_plots_on_sloped_edge(self):
        """Absorbing leftover must not glue a whole invalid band into one lot."""
        plot = _wide_sloped_screen_plot()
        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.nieuzytek_area < 0.5
        oversized = [
            s.area for s in result.sub_plots
            if s.area > plot.mpzp.max_sub_plot_area_m2 * 1.05
        ]
        assert not oversized, (
            "Absorption created oversized plots: "
            f"{[round(a, 1) for a in oversized]}"
        )

    def test_shallow_concave_plot_uses_direct_access_without_internal_roads(self):
        """Shallow parcel should not waste land on a road tree."""
        plot = _shallow_concave_plot()
        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.sub_plots, "Expected direct-access sub-plots"
        assert result.total_road_area < 1.0, (
            f"Shallow parcel should not need internal roads, got "
            f"{result.total_road_area:.1f}m²"
        )
        assert result.sub_plots_without_road_access == 0
        assert result.nieuzytek_area < 0.5
        assert all(
            s.area <= plot.mpzp.max_sub_plot_area_m2 * 1.05
            for s in result.sub_plots
        )

    def test_parallel_plot_with_top_road_absorbs_all_leftovers(self):
        """Different DROGA edge orientation must still have no nieużytek."""
        plot = _wide_parallel_top_road_plot()
        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.sub_plots_without_road_access == 0
        assert result.nieuzytek_area < 0.5, (
            f"Leftover should be absorbed, got {result.nieuzytek_area:.1f}m²"
        )

    def test_top_road_plot_with_600_800_area_bounds_has_no_monster_tail(self):
        """Regression for AC screenshot: right tail must be split, not glued."""
        plot = _wide_parallel_top_road_plot()
        plot.mpzp.min_sub_plot_area_m2 = 600.0
        plot.mpzp.max_sub_plot_area_m2 = 800.0

        result = subdivide(plot, building_type=BuildingType.DETACHED)

        assert result.sub_plots_without_road_access == 0
        assert result.nieuzytek_area < 0.5
        oversized = [
            s.area for s in result.sub_plots
            if s.area > plot.mpzp.max_sub_plot_area_m2 * 1.05
        ]
        assert not oversized, (
            "Right-side leftovers must be split into normal plots, got "
            f"{[round(a, 1) for a in oversized]}"
        )
        tiny_buildable = [
            (i + 1, s.buildable_zone.area if s.has_buildable_zone else 0.0)
            for i, s in enumerate(result.sub_plots)
            if not s.has_buildable_zone
            or s.buildable_zone.area < plot.mpzp.min_sub_plot_area_m2 * 0.20
        ]
        assert not tiny_buildable, (
            "Every kept plot needs a usable buildable zone, got "
            f"{[(i, round(a, 1)) for i, a in tiny_buildable]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Q5(c) orientation search
# ─────────────────────────────────────────────────────────────────────────────

class TestOrientationSearch:

    def test_long_narrow_picks_road_accessible(self):
        """30×100 plot — rotated layout would orphan sub-plots; search rejects it."""
        plot = _rectangular(30, 100)
        r = subdivide_with_orientation_search(plot)
        # Every sub-plot must have road access (no orphans)
        for s in r.sub_plots:
            assert s.front_length > 0, "Orphaned sub-plot returned"

    def test_search_picks_more_sub_plots_when_safe(self):
        """When both orientations valid, pick the higher count."""
        plot = _rectangular(60, 80)
        r_axis = subdivide(plot, rotated_90=False)
        r_rot = subdivide(plot, rotated_90=True)
        r_search = subdivide_with_orientation_search(plot)
        # Search result has at least as many as max of the two
        assert len(r_search.sub_plots) >= max(
            len(r_axis.sub_plots), len(r_rot.sub_plots)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass smoke
# ─────────────────────────────────────────────────────────────────────────────

class TestResultMetadata:

    def test_orientation_name_set(self):
        """Road-tree layout reports its active production strategy."""
        plot = _rectangular()
        r = subdivide(plot)
        assert r.orientation_name.startswith("road_tree")

    def test_rows_cols_recorded(self):
        plot = _rectangular(60, 80)
        r = subdivide(plot)
        # OBB has no row/col grid; rows/cols are repurposed to report
        # sub-plot count (cols) and "1" (rows) when at least one sub-plot exists.
        assert r.rows >= 1
        assert r.cols >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
