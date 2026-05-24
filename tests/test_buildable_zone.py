"""
Stage 1 regression tests — buildable zone calculation.

Ported from claude code/archicad-checker/tests/test_zone_builder.py on
2026-05-07. Verifies setback distances per boundary type, irregular-plot
support (L-shape, triangle), edge cases, and max-footprint helpers.
"""
import pytest
from shapely.geometry import LineString, Polygon, box as shapely_box

from core.buildable_zone import BuildableZoneBuilder, BuildableZoneInfeasible
from core.plot_model import (
    BoundaryType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)


def _rectangle_plot(
    width: float = 20.0,
    depth: float = 30.0,
    boundary_types: list = None,
    setback_from_road: float = 5.0,
) -> Plot:
    """
    Rectangular plot with boundaries:
        bottom → boundary_types[0]
        right  → boundary_types[1]
        top    → boundary_types[2]
        left   → boundary_types[3]
    """
    if boundary_types is None:
        boundary_types = [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_ZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ]

    poly = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
    coords = [(0, 0), (width, 0), (width, depth), (0, depth), (0, 0)]
    boundaries = [
        PlotBoundary(
            geometry=LineString([coords[i], coords[i + 1]]),
            boundary_type=boundary_types[i % len(boundary_types)],
            segment_index=i,
        )
        for i in range(4)
    ]

    return Plot(
        number="Plot T",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            setback_from_road=setback_from_road,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Basic
# ─────────────────────────────────────────────────────────────────────────────

class TestZoneBasic:

    def test_zone_not_empty(self):
        """20×30 m plot — buildable zone must be non-empty."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert not zone.is_empty
        assert zone.area > 0

    def test_zone_smaller_than_plot(self):
        """Setbacks consume area — zone must be smaller than plot."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.area < plot.area

    def test_zone_inside_plot(self):
        """Zone must be contained within plot outline."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert plot.geometry.contains(zone) or plot.geometry.covers(zone)

    def test_zone_stored_on_plot(self):
        """Result is mirrored to plot.buildable_zone."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        builder.compute(plot)
        assert plot.buildable_zone is not None
        assert plot.buildable_zone.area > 0


# ─────────────────────────────────────────────────────────────────────────────
# Setbacks per boundary type
# ─────────────────────────────────────────────────────────────────────────────

class TestSetbacks:

    def test_road_setback(self):
        """20×30 plot, MPZP setback 5m from road (bottom). Zone min y ≥ 5m."""
        plot = _rectangle_plot(20, 30, setback_from_road=5.0)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.bounds[1] >= 4.9   # 0.1m tolerance

    def test_developed_neighbour_3m(self):
        """Right boundary = SASIAD_ZABUDOWANY (x=20). Zone max x ≤ 17."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.bounds[2] <= 17.1

    def test_undeveloped_neighbour_with_openings_3m(self):
        """Left boundary = SASIAD_NIEZABUDOWANY without no_openings → 3m."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.bounds[0] >= 2.9

    def test_undeveloped_neighbour_no_openings_1_5m(self):
        """SASIAD_NIEZABUDOWANY + no_openings → 1.5m → larger zone than 3m case."""
        plot_3m = _rectangle_plot(20, 30)
        plot_15 = _rectangle_plot(20, 30)
        plot_15.boundaries[3].no_openings = True

        builder = BuildableZoneBuilder()
        zone_3m = builder.compute(plot_3m)
        zone_15 = builder.compute(plot_15)
        assert zone_15.area > zone_3m.area

    def test_smaller_setback_yields_larger_zone(self):
        """Reducing setback (1.5m vs 3m) gives a larger zone."""
        plot = _rectangle_plot(20, 30)

        builder = BuildableZoneBuilder()
        zone_1 = builder.compute(plot)
        area_1 = zone_1.area

        plot.boundaries[3].no_openings = True
        zone_2 = builder.compute(plot)
        area_2 = zone_2.area

        assert area_2 > area_1


# ─────────────────────────────────────────────────────────────────────────────
# Irregular plots
# ─────────────────────────────────────────────────────────────────────────────

class TestIrregularPlot:

    def test_l_shape_plot(self):
        """L-shape plot: 30×20 minus 10×10 top-right corner."""
        poly = Polygon([
            (0, 0), (30, 0), (30, 10), (20, 10),
            (20, 20), (0, 20),
        ])
        boundaries = [
            PlotBoundary(LineString([(0, 0), (30, 0)]), BoundaryType.DROGA, 0),
            PlotBoundary(LineString([(30, 0), (30, 10)]), BoundaryType.SASIAD_ZABUDOWANY, 1),
            PlotBoundary(LineString([(30, 10), (20, 10)]), BoundaryType.WLASNA, 2),
            PlotBoundary(LineString([(20, 10), (20, 20)]), BoundaryType.SASIAD_ZABUDOWANY, 3),
            PlotBoundary(LineString([(20, 20), (0, 20)]), BoundaryType.WLASNA, 4),
            PlotBoundary(LineString([(0, 20), (0, 0)]), BoundaryType.SASIAD_NIEZABUDOWANY, 5),
        ]
        plot = Plot(
            number="L-shape",
            geometry=poly,
            boundaries=boundaries,
            mpzp=MPZPParameters(setback_from_road=5.0),
        )
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)

        assert not zone.is_empty
        assert zone.area > 0
        assert zone.area < poly.area

    def test_triangle_plot(self):
        """Triangular plot — buildable zone must be non-empty."""
        poly = Polygon([(0, 0), (25, 0), (12.5, 20)])
        boundaries = [
            PlotBoundary(LineString([(0, 0), (25, 0)]), BoundaryType.DROGA, 0),
            PlotBoundary(LineString([(25, 0), (12.5, 20)]), BoundaryType.SASIAD_ZABUDOWANY, 1),
            PlotBoundary(LineString([(12.5, 20), (0, 0)]), BoundaryType.SASIAD_NIEZABUDOWANY, 2),
        ]
        plot = Plot(
            number="Triangle",
            geometry=poly,
            boundaries=boundaries,
            mpzp=MPZPParameters(setback_from_road=5.0),
        )
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.area > 0


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_no_boundaries_raises(self):
        """Plot without boundaries → BuildableZoneInfeasible."""
        poly = Polygon([(0, 0), (20, 0), (20, 30), (0, 30)])
        plot = Plot(number="No boundaries", geometry=poly, boundaries=[])
        builder = BuildableZoneBuilder()
        with pytest.raises(BuildableZoneInfeasible):
            builder.compute(plot)

    def test_plot_too_small(self):
        """4×4 m plot with 3m setbacks → empty zone → BuildableZoneInfeasible."""
        poly = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
        boundaries = [
            PlotBoundary(LineString([(0, 0), (4, 0)]), BoundaryType.DROGA, 0),
            PlotBoundary(LineString([(4, 0), (4, 4)]), BoundaryType.SASIAD_ZABUDOWANY, 1),
            PlotBoundary(LineString([(4, 4), (0, 4)]), BoundaryType.SASIAD_ZABUDOWANY, 2),
            PlotBoundary(LineString([(0, 4), (0, 0)]), BoundaryType.SASIAD_ZABUDOWANY, 3),
        ]
        plot = Plot(
            number="Small",
            geometry=poly,
            boundaries=boundaries,
            mpzp=MPZPParameters(setback_from_road=5.0),
        )
        builder = BuildableZoneBuilder()
        with pytest.raises(BuildableZoneInfeasible):
            builder.compute(plot)

    def test_mpzp_setback_overrides_wt(self):
        """MPZP setback (6m) > WT default (3m) → use 6m."""
        plot = _rectangle_plot(20, 30, setback_from_road=6.0)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        assert zone.bounds[1] >= 5.9

    def test_large_plot_has_large_zone(self):
        """Large plot (100×100m) — zone covers a substantial fraction."""
        plot = _rectangle_plot(100, 100, setback_from_road=5.0)
        builder = BuildableZoneBuilder()
        zone = builder.compute(plot)
        ratio = zone.area / plot.area
        assert ratio > 0.60


# ─────────────────────────────────────────────────────────────────────────────
# Max footprint helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxFootprint:

    def test_max_footprint_by_wz(self):
        """Max footprint = plot_area × max_wz."""
        plot = _rectangle_plot(20, 30)  # 600 m²
        builder = BuildableZoneBuilder()
        builder.compute(plot)
        max_area = builder.max_buildable_footprint(plot)
        assert max_area <= 180.0 + 0.1   # 600 × 0.30

    def test_building_inside_zone(self):
        """Small building inside zone → True."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        builder.compute(plot)
        zone = plot.buildable_zone
        minx, miny, maxx, maxy = zone.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        w = (maxx - minx) * 0.3
        h = (maxy - miny) * 0.3
        small_building = shapely_box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        assert builder.building_inside_zone(plot, small_building) is True

    def test_building_outside_zone(self):
        """Building near road (within setback) → False."""
        plot = _rectangle_plot(20, 30)
        builder = BuildableZoneBuilder()
        builder.compute(plot)
        building_near_road = shapely_box(5, 0, 15, 3)  # y 0-3, setback=5m
        assert builder.building_inside_zone(plot, building_near_road) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
