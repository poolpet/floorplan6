"""Unit tests for core/building_to_apartment_input.py (Stage 1 → Stage 4 helper)."""
from __future__ import annotations

import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from core.building_to_apartment_input import building_to_apartment_input
from core.models import WallType
from core.plot_model import BoundaryType, PlotBoundary
from core.plot_subdivider import SubPlot


def _make_sub(
    building: Polygon,
    *,
    boundaries: list[PlotBoundary] | None = None,
    parent_droga_touch: float = 0.0,
    internal_road_touch: float = 0.0,
) -> SubPlot:
    """Factory for a SubPlot wired with a proposed_building and boundaries."""
    sub = SubPlot(
        polygon=box(*building.bounds) if not boundaries else
                Polygon([(0, 0), (12, 0), (12, 30), (0, 30)]),
        boundaries=boundaries or [],
        proposed_building=building,
        parent_droga_touch=parent_droga_touch,
        internal_road_touch=internal_road_touch,
    )
    return sub


def _rect_building(x0=2.0, y0=10.0, w=8.0, d=10.0) -> Polygon:
    """An 8x10 m building footprint at (x0, y0)."""
    return box(x0, y0, x0 + w, y0 + d)


def _droga_bottom_boundary(x0=0.0, x1=12.0, y=0.0) -> PlotBoundary:
    return PlotBoundary(
        geometry=LineString([(x0, y), (x1, y)]),
        boundary_type=BoundaryType.DROGA,
        segment_index=0,
        is_shared_wall=False,
    )


def _shared_side_boundary(x=12.0, y0=0.0, y1=30.0, segment_index=1) -> PlotBoundary:
    return PlotBoundary(
        geometry=LineString([(x, y0), (x, y1)]),
        boundary_type=BoundaryType.SASIAD_NIEZABUDOWANY,
        segment_index=segment_index,
        is_shared_wall=True,
    )


class TestDetached:
    def test_all_facade(self):
        sub = _make_sub(_rect_building(), boundaries=[_droga_bottom_boundary()])
        _, _, walls = building_to_apartment_input(sub)
        assert all(w == WallType.FACADE for w in walls)
        assert len(walls) == 4

    def test_entry_on_road_side(self):
        building = _rect_building(x0=2.0, y0=10.0, w=8.0, d=10.0)
        sub = _make_sub(building, boundaries=[_droga_bottom_boundary()])
        polygon, entry, _ = building_to_apartment_input(sub)
        # Road is at y=0; building bottom is y=10. Entry should be on the
        # building edge nearest the road — i.e. the bottom edge y=10, midpoint x.
        assert entry == pytest.approx((6.0, 10.0))
        assert polygon.equals(building)


class TestTwin:
    def test_one_internal_when_one_shared_wall(self):
        # Building shares its right edge (x=12) with the partner sub-plot.
        building = box(4.0, 10.0, 12.0, 20.0)
        sub = _make_sub(
            building,
            boundaries=[
                _droga_bottom_boundary(),
                _shared_side_boundary(x=12.0),
            ],
        )
        _, _, walls = building_to_apartment_input(sub)
        assert walls.count(WallType.INTERNAL) == 1
        assert walls.count(WallType.FACADE) == 3


class TestTerracedMiddle:
    def test_two_internal_when_two_shared_walls(self):
        # Building shares both side edges with chain neighbours.
        building = box(0.0, 10.0, 12.0, 20.0)
        sub = _make_sub(
            building,
            boundaries=[
                _droga_bottom_boundary(x0=0.0, x1=12.0),
                _shared_side_boundary(x=12.0, segment_index=1),
                PlotBoundary(
                    geometry=LineString([(0.0, 0.0), (0.0, 30.0)]),
                    boundary_type=BoundaryType.SASIAD_NIEZABUDOWANY,
                    segment_index=3,
                    is_shared_wall=True,
                ),
            ],
        )
        _, _, walls = building_to_apartment_input(sub)
        assert walls.count(WallType.INTERNAL) == 2
        assert walls.count(WallType.FACADE) == 2


class TestMultiPolygonBuilding:
    def test_picks_largest_part(self):
        big = box(0.0, 0.0, 10.0, 10.0)        # area 100
        small = box(20.0, 0.0, 22.0, 1.0)      # area 2
        sub = _make_sub(big)  # SubPlot factory takes the larger polygon shape
        sub.proposed_building = MultiPolygon([big, small])
        polygon, _, _ = building_to_apartment_input(sub)
        assert polygon.equals(big)


class TestFallbackEntry:
    def test_no_road_uses_longest_edge_midpoint(self):
        # No DROGA boundary, no roads passed → fallback path.
        building = box(0.0, 0.0, 12.0, 6.0)    # long edges of length 12
        sub = SubPlot(
            polygon=building,
            boundaries=[],
            proposed_building=building,
            parent_droga_touch=0.0,
            internal_road_touch=0.0,
        )
        _, entry, _ = building_to_apartment_input(sub, roads=None)
        # Longest edges are the two y=0 and y=6 sides (length 12).
        # Midpoint either (6, 0) or (6, 6). Function must pick deterministically
        # (first encountered in exterior coord order = bottom y=0).
        assert entry == pytest.approx((6.0, 0.0))
