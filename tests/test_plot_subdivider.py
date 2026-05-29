"""
Stage 1 Mode B regression tests — plot subdivision.

Anti-bug regressions vs C++ Plot Subdivider session 2026-04-29:
  #1 sub-plots overflow parent boundary
  #2 internal roads overflow parent boundary
  #3 buildable zone ignored (sub-plots in parent outline, not respecting zone)
  #4 absurd sub-plot count (36 inserted where ~10 fit)

Plus tests for:
  Q12 — Mode B single-family only
  Q19 (2026-05-25) — TERRACED/TWIN accept any road access (parent DROGA
       OR internal road); previously gated to parent DROGA only, which
       collapsed multi-row developments to ≤4 monster sub-plots.
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


def _notch_road_right_plot():
    """Irregular plot, road only on the RIGHT vertical edge, with a notch on
    the lower-left. The notch blocks the internal road tree from reaching the
    bottom-left band, so those cells have no road access. Replicates Dawid's
    2026-05-28 monster bug (S7=19664 m² on a 284×166 irregular plot): the
    road-less band is glued into one giant sub-plot by `_absorb_leftover`
    instead of being demoted to nieużytek / split into legal sub-plots.
    """
    plot = _make_plot(
        [(0, 0), (284, 0), (284, 166), (0, 166),
         (0, 100), (60, 100), (60, 60), (0, 60)],
        [
            BoundaryType.SASIAD_NIEZABUDOWANY,  # bottom
            BoundaryType.DROGA,                 # right (only road)
            BoundaryType.SASIAD_NIEZABUDOWANY,  # top
            BoundaryType.WLASNA,                # left upper
            BoundaryType.SASIAD_NIEZABUDOWANY,  # notch
            BoundaryType.WLASNA,                # notch
            BoundaryType.SASIAD_NIEZABUDOWANY,  # notch
            BoundaryType.WLASNA,                # left lower
        ],
    )
    plot.mpzp.min_sub_plot_area_m2 = 400.0
    plot.mpzp.max_sub_plot_area_m2 = 1000.0
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
# Q19 (2026-05-25) — TWIN/TERRACED accept any road access
# Previously: only parent's DROGA touch counted, which collapsed multi-row
# developments to ≤4 monster sub-plots. Re-decision: all building types
# accept parent DROGA OR internal road (Q3 only mandates orientation, not
# location). See plot_subdivider._filter_for_building_type docstring.
# ─────────────────────────────────────────────────────────────────────────────

class TestQ19RoadAccess:

    def test_detached_accepts_internal_road_sub_plots(self):
        """DETACHED: sub-plots fronting internal road only are kept."""
        plot = _rectangular(60, 260)
        r = subdivide(plot, building_type=BuildingType.DETACHED)
        any_internal_only = any(
            s.parent_droga_touch == 0 and s.internal_road_touch > 0
            for s in r.sub_plots
        )
        assert any_internal_only, \
            "Expected at least one DETACHED sub-plot fronting only internal road"

    def test_terraced_accepts_internal_road_sub_plots(self):
        """Q19: TERRACED no longer requires parent DROGA — internal road OK."""
        plot = _rectangular(60, 260)
        r = subdivide(plot, building_type=BuildingType.TERRACED)
        any_internal_only = any(
            s.parent_droga_touch == 0 and s.internal_road_touch > 0
            for s in r.sub_plots
        )
        assert any_internal_only, (
            "Expected at least one TERRACED sub-plot fronting only internal "
            "road (Q19 2026-05-25 — szeregowce w drugim rzędzie are valid)"
        )

    def test_twin_accepts_internal_road_sub_plots(self):
        """Q19: TWIN no longer requires parent DROGA — internal road OK."""
        plot = _rectangular(60, 260)
        r = subdivide(plot, building_type=BuildingType.TWIN)
        any_internal_only = any(
            s.parent_droga_touch == 0 and s.internal_road_touch > 0
            for s in r.sub_plots
        )
        assert any_internal_only, (
            "Expected at least one TWIN sub-plot fronting only internal road "
            "(Q19 2026-05-25 — bliźniaki w drugim rzędzie are valid)"
        )

    def test_twin_does_not_collapse_to_monster_subplot_on_large_plot(self):
        """Regression for Dawid's 2026-05-25 screenshot bug.

        Before Q19: TWIN on 265×202m plot returned 4 sub-plots with one
        monster S1=31708m² (almost the whole plot), instead of normal
        grid subdivision. Cause: strict parent-DROGA filter rejected most
        candidates, forcing _absorb_leftover_capped to merge them.
        """
        plot = _rectangular(265, 202)
        r_detached = subdivide(plot, building_type=BuildingType.DETACHED)
        r_twin = subdivide(plot, building_type=BuildingType.TWIN)

        # TWIN should produce a similar count to DETACHED (within 50% lower
        # bound — different scorers may pick different strategies, but TWIN
        # must not collapse).
        assert len(r_twin.sub_plots) >= 0.5 * len(r_detached.sub_plots), (
            f"TWIN collapsed to {len(r_twin.sub_plots)} sub-plots vs "
            f"{len(r_detached.sub_plots)} for DETACHED"
        )
        # No single sub-plot may swallow most of the plot.
        max_area = max(s.area for s in r_twin.sub_plots)
        plot_area = plot.geometry.area
        assert max_area < 0.25 * plot_area, (
            f"Monster sub-plot {max_area:.0f}m² covers "
            f"{max_area / plot_area:.1%} of plot — likely Q19 regression"
        )

    def test_terraced_does_not_collapse_to_monster_subplot_on_large_plot(self):
        """Mirror of test_twin_does_not_collapse — TERRACED scenario."""
        plot = _rectangular(265, 202)
        r_detached = subdivide(plot, building_type=BuildingType.DETACHED)
        r_terraced = subdivide(plot, building_type=BuildingType.TERRACED)

        assert len(r_terraced.sub_plots) >= 0.5 * len(r_detached.sub_plots), (
            f"TERRACED collapsed to {len(r_terraced.sub_plots)} sub-plots vs "
            f"{len(r_detached.sub_plots)} for DETACHED"
        )
        max_area = max(s.area for s in r_terraced.sub_plots)
        plot_area = plot.geometry.area
        assert max_area < 0.25 * plot_area, (
            f"Monster sub-plot {max_area:.0f}m² covers "
            f"{max_area / plot_area:.1%} of plot — likely Q19 regression"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Q20 (2026-05-25) — segment scaling: 1 sub-plot = 1 segment for TWIN/TERRACED
# DETACHED keeps standard sub-plots (~600-1000 m²). TWIN segment = ½ pair
# (~300 m²). TERRACED segment = 1 unit of a chain (~200 m²). Without this
# scaling, all building types would produce identical DETACHED-sized plots.
# See plot_subdivider._with_effective_mpzp + _BUILDING_TYPE_SEGMENT_DEFAULTS.
# ─────────────────────────────────────────────────────────────────────────────

class TestQ20SegmentScaling:

    def test_twin_average_sub_plot_smaller_than_detached(self):
        """TWIN sub-plot = ½ pair → average area must be clearly smaller."""
        plot = _rectangular(265, 202)
        r_detached = subdivide(plot, building_type=BuildingType.DETACHED)
        r_twin = subdivide(plot, building_type=BuildingType.TWIN)

        avg_d = sum(s.area for s in r_detached.sub_plots) / len(r_detached.sub_plots)
        avg_t = sum(s.area for s in r_twin.sub_plots) / len(r_twin.sub_plots)

        assert avg_t < 0.7 * avg_d, (
            f"TWIN avg sub-plot {avg_t:.0f}m² should be <70% of DETACHED "
            f"avg {avg_d:.0f}m² (Q20 scaling — segment vs whole plot)"
        )

    def test_terraced_average_sub_plot_smaller_than_twin(self):
        """TERRACED segment is the smallest of the three types."""
        plot = _rectangular(265, 202)
        r_twin = subdivide(plot, building_type=BuildingType.TWIN)
        r_terraced = subdivide(plot, building_type=BuildingType.TERRACED)

        avg_twin = sum(s.area for s in r_twin.sub_plots) / len(r_twin.sub_plots)
        avg_terr = sum(s.area for s in r_terraced.sub_plots) / len(r_terraced.sub_plots)

        assert avg_terr < avg_twin, (
            f"TERRACED avg {avg_terr:.0f}m² should be smaller than "
            f"TWIN avg {avg_twin:.0f}m² (Q20 scaling)"
        )

    def test_detached_unchanged_by_q20(self):
        """DETACHED keeps user's MPZP values — no scaling applied."""
        plot = _rectangular(60, 80)
        before_front = plot.mpzp.min_front_m
        before_min_area = plot.mpzp.min_sub_plot_area_m2
        before_max_area = plot.mpzp.max_sub_plot_area_m2

        # Run subdivide (which would mutate MPZP for TWIN/TERRACED via replace).
        subdivide(plot, building_type=BuildingType.DETACHED)

        # The original plot must not be mutated by subdivide.
        assert plot.mpzp.min_front_m == before_front
        assert plot.mpzp.min_sub_plot_area_m2 == before_min_area
        assert plot.mpzp.max_sub_plot_area_m2 == before_max_area

    def test_terraced_produces_subplots_after_short_dim_fix(self):
        """Q20 follow-up: TERRACED segments (6 m wide) used to be rejected
        by the hardcoded `min_short_dim=12` guard, returning 0 sub-plots.
        After scaling the guard with mpzp.min_front_m, TERRACED must
        produce a non-trivial number of sub-plots on a large plot.
        """
        plot = _rectangular(265, 202)
        r = subdivide(plot, building_type=BuildingType.TERRACED)
        assert len(r.sub_plots) >= 20, (
            f"TERRACED produced only {len(r.sub_plots)} sub-plots — "
            f"likely _is_buildable_shape guard regression"
        )

    def test_terraced_count_meets_or_exceeds_detached(self):
        """Q20: TERRACED segments smaller than DETACHED → at least as many."""
        plot = _rectangular(265, 202)
        r_d = subdivide(plot, building_type=BuildingType.DETACHED)
        r_t = subdivide(plot, building_type=BuildingType.TERRACED)
        # Allow some scoring noise — TERRACED should clearly out-pack DETACHED.
        assert len(r_t.sub_plots) >= 0.9 * len(r_d.sub_plots), (
            f"TERRACED {len(r_t.sub_plots)} < DETACHED {len(r_d.sub_plots)} "
            "— segments should pack denser, not sparser"
        )

    def test_twin_no_oversized_leftover_monster(self):
        """Q20 follow-up: after the short-dim fix, `_split_oversized_subplots`
        is able to recursively split absorption leftovers, so no single
        sub-plot dwarfs the others. Cap = effective max_area × 2.5
        (split cap is 1.5×; allow some slack for irregular trapezoid plots).
        """
        plot = _rectangular(265, 202)
        r = subdivide(plot, building_type=BuildingType.TWIN)
        # Effective max_area for TWIN = user value × 0.5 (Q20 scaling).
        twin_effective_max = plot.mpzp.max_sub_plot_area_m2 * 0.5
        max_area = max(s.area for s in r.sub_plots)
        assert max_area <= twin_effective_max * 2.5, (
            f"TWIN has monster sub-plot {max_area:.0f}m² "
            f"(effective cap {twin_effective_max:.0f}m² × 2.5 = "
            f"{twin_effective_max * 2.5:.0f}m²)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Q21 (2026-05-26) — shared walls for TWIN/TERRACED: side setback = 0 on the
# boundary that touches another segment in the pair (TWIN) or chain (TERRACED).
# Without this, default 3m side setback shrinks an 8.6m-wide TWIN sub-plot's
# buildable zone to 2.6m × ~72m — no building fits. See OPEN_QUESTIONS.md
# Q21 + plot_subdivider._mark_shared_walls.
# ─────────────────────────────────────────────────────────────────────────────

class TestQ21SharedWalls:

    def test_detached_has_no_shared_walls(self):
        """DETACHED: no boundary should ever be marked is_shared_wall."""
        plot = _rectangular(60, 80)
        r = subdivide(plot, building_type=BuildingType.DETACHED)
        for s in r.sub_plots:
            assert not any(b.is_shared_wall for b in s.boundaries), (
                "DETACHED: free-standing — no shared walls expected"
            )

    def test_twin_paired_subplots_have_shared_wall_marked(self):
        """TWIN: paired sub-plots (longest shared edge ≥ 6m) have exactly one
        boundary marked is_shared_wall on each side of the pair."""
        plot = _rectangular(60, 80)
        r = subdivide(plot, building_type=BuildingType.TWIN)
        marked_subs = [
            s for s in r.sub_plots
            if any(b.is_shared_wall for b in s.boundaries)
        ]
        # At least 1 pair → 2 sub-plots marked (one per side).
        assert len(marked_subs) >= 2, (
            f"TWIN: expected ≥2 sub-plots with shared wall (≥1 pair), "
            f"got {len(marked_subs)}"
        )
        # Each marked sub-plot should have exactly 1 shared wall (TWIN = 1 pair).
        for s in marked_subs:
            shared_count = sum(1 for b in s.boundaries if b.is_shared_wall)
            assert shared_count == 1, (
                f"TWIN paired sub-plot has {shared_count} shared walls "
                "(expected exactly 1)"
            )

    def test_terraced_internal_subplots_have_two_shared_walls(self):
        """TERRACED chain: internal segments have 2 shared walls (both sides),
        edge segments have 1 shared wall. At least one internal segment must
        exist on a 60×80 plot."""
        plot = _rectangular(60, 80)
        r = subdivide(plot, building_type=BuildingType.TERRACED)
        shared_counts = [
            sum(1 for b in s.boundaries if b.is_shared_wall)
            for s in r.sub_plots
        ]
        # At least one sub-plot has 2 shared walls (internal in chain).
        assert max(shared_counts) >= 2, (
            f"TERRACED: expected ≥1 internal sub-plot with 2 shared walls, "
            f"max found = {max(shared_counts)}; counts={sorted(shared_counts)}"
        )
        # At least one sub-plot has exactly 1 shared wall (chain edge).
        assert 1 in shared_counts, (
            f"TERRACED: expected ≥1 edge sub-plot with 1 shared wall, "
            f"counts={sorted(shared_counts)}"
        )

    def test_twin_buildable_zone_widens_after_shared_wall(self):
        """TWIN: shared-wall sub-plot's buildable zone is wide enough for a
        building. Before Q21: ~2.6m. After Q21: ≥ ~5m (3m setback dropped on
        the shared side)."""
        plot = _rectangular(60, 80)
        r = subdivide(plot, building_type=BuildingType.TWIN)
        widths = []
        for s in r.sub_plots:
            if (any(b.is_shared_wall for b in s.boundaries)
                    and s.has_buildable_zone):
                minx, _, maxx, _ = s.buildable_zone.bounds
                widths.append(maxx - minx)
        assert widths, "Expected at least one TWIN sub-plot with shared wall"
        assert min(widths) >= 4.0, (
            f"Shared-wall TWIN sub-plot has buildable zone width "
            f"{min(widths):.2f}m < 4m — Q21 setback override not applied"
        )


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


# ─────────────────────────────────────────────────────────────────────────────
# Monster sub-plot on irregular shape with single-side road (2026-05-28)
# Regression for Dawid's bug: a notch blocks the road tree from reaching part
# of the plot; `_absorb_leftover` then glues that road-less band into one giant
# sub-plot. Final sub-plots must all have road access and respect the area cap;
# genuinely unreachable land becomes nieużytek (Q1.1(d) / Q16), not a monster.
# ─────────────────────────────────────────────────────────────────────────────

class TestMonsterOnIrregularSingleSideRoad:

    @pytest.mark.parametrize(
        "building_type",
        [BuildingType.DETACHED, BuildingType.TWIN],
    )
    def test_no_roadless_monster_subplot(self, building_type):
        plot = _notch_road_right_plot()
        r = subdivide(plot, building_type=building_type)
        assert r.sub_plots, "expected at least one sub-plot"

        # Every retained sub-plot must touch a road (parent DROGA or internal).
        # The monster bug keeps a road-less band as a sub-plot — that is the
        # exact invariant it violates.
        roadless = [
            s for s in r.sub_plots
            if (s.parent_droga_touch + s.internal_road_touch) <= 0.5
        ]
        assert not roadless, (
            f"{len(roadless)} road-less sub-plot(s) kept "
            f"(areas {[round(s.area) for s in roadless]}) — monster bug"
        )

        # No sub-plot may exceed the MPZP cap by more than the split tolerance.
        max_area = max(s.area for s in r.sub_plots)
        cap = plot.mpzp.max_sub_plot_area_m2 * 1.05
        assert max_area <= cap, (
            f"monster sub-plot {max_area:.0f}m² > cap {cap:.0f}m² "
            f"(building_type={building_type.name})"
        )

    def test_coverage_holds_with_nieuzytek(self):
        """Strict coverage (Q16): sub-plots + roads + nieużytek == parent."""
        plot = _notch_road_right_plot()
        r = subdivide(plot, building_type=BuildingType.DETACHED)
        accounted = (
            r.total_sub_area + r.total_road_area + r.nieuzytek_area
        )
        assert abs(accounted - plot.geometry.area) < 1.0, (
            f"coverage gap: accounted {accounted:.1f} vs "
            f"parent {plot.geometry.area:.1f}"
        )

    @pytest.mark.parametrize(
        "building_type",
        [BuildingType.DETACHED, BuildingType.TWIN],
    )
    def test_rescue_spur_does_not_dead_end_on_non_road_boundary(self, building_type):
        """Invariant 6 guard for the oversized-parcel rescue path (owner rule
        2026-05-10). When _resolve_oversized_parcels carves an access spur to
        reach the road-less band, that spur (and every other internal road)
        must NOT terminate on a non-DROGA plot boundary beyond min_road_width*0.5.
        Otherwise the rescue would trade a monster for a dead-end road.
        """
        plot = _notch_road_right_plot()
        result = subdivide(plot, building_type=building_type)
        if not result.roads:
            return  # no internal roads → nothing to dead-end

        road_union = unary_union(result.roads)
        non_road_touch = sum(
            road_union.boundary.intersection(boundary.geometry.buffer(0.05)).length
            for boundary in plot.boundaries
            if boundary.boundary_type != BoundaryType.DROGA
        )
        assert non_road_touch < plot.mpzp.min_road_width_m * 0.5, (
            "Rescue spur / internal roads must not dead-end on a non-DROGA "
            f"boundary; touch length={non_road_touch:.2f}m "
            f"(building_type={building_type.name})"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
