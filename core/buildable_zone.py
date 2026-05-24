"""
Stage 1 — buildable zone calculation (ported from
claude code/archicad-checker/zone_builder.py on 2026-05-07).

For each plot boundary, compute a setback buffer; subtract the union of
buffers from the plot to obtain the polygon where a building may stand.

Boundary type → setback distance:
- DROGA: max(MPZP setback_from_road, 3.0) — usually 5m from MPZP
- SASIAD_NIEZABUDOWANY: 1.5m if no_openings else 3.0m
- SASIAD_ZABUDOWANY: 3.0m always
- WLASNA: 1.5m if no_openings else 3.0m
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from core.plot_model import BoundaryType, Plot, PlotBoundary

logger = logging.getLogger(__name__)


class BuildableZoneInfeasible(Exception):
    """Raised when a plot has no buildable zone (too small / too tight setbacks)."""


class BuildableZoneBuilder:
    """Computes the buildable zone polygon for a plot."""

    def __init__(self, precision_margin: float = 0.01):
        self._margin = precision_margin

    def compute(
        self,
        plot: Plot,
        no_openings_direction: Optional[str] = None,
    ) -> Polygon:
        """Compute the buildable zone and store it in plot.buildable_zone."""
        if not plot.boundaries:
            raise BuildableZoneInfeasible(
                f"Plot {plot.number} has no boundaries defined."
            )

        plot_area = plot.geometry
        if not plot_area.is_valid:
            plot_area = plot_area.buffer(0)

        excluded_buffers = []
        for boundary in plot.boundaries:
            buf = self._boundary_buffer(
                boundary,
                plot.mpzp.setback_from_road,
                no_openings_direction,
            )
            if buf and not buf.is_empty:
                excluded_buffers.append(buf)

        if excluded_buffers:
            excluded = unary_union(excluded_buffers)
            zone = plot_area.difference(excluded)
        else:
            zone = plot_area

        if not zone.is_valid:
            zone = zone.buffer(0)

        zone = self._largest_polygon(zone)

        if zone.is_empty or zone.area < 0.5:
            raise BuildableZoneInfeasible(
                f"Buildable zone for plot {plot.number} is empty. "
                "Check plot dimensions and required boundary setbacks."
            )

        plot.buildable_zone = zone
        logger.info(
            "Buildable zone for %s: %.1f m² (%.1f%% of plot)",
            plot.number,
            zone.area,
            zone.area / plot.area * 100,
        )
        return zone

    def _boundary_buffer(
        self,
        boundary: PlotBoundary,
        setback_from_road: float,
        no_openings_direction: Optional[str],
    ) -> Optional[Polygon]:
        """Build the exclusion polygon for one boundary segment."""
        distance = self._setback_distance(
            boundary, setback_from_road, no_openings_direction
        )
        if distance <= 0:
            return None

        try:
            return boundary.geometry.buffer(
                distance,
                cap_style=2,    # flat cap
                join_style=2,   # mitre join
                single_sided=False,
            )
        except Exception as e:
            logger.warning("Boundary buffer error: %s", e)
            return None

    def _setback_distance(
        self,
        boundary: PlotBoundary,
        setback_from_road: float,
        no_openings_direction: Optional[str],
    ) -> float:
        """Required setback distance for a single boundary [m]."""
        if boundary.boundary_type == BoundaryType.DROGA:
            return max(setback_from_road, 3.0)

        no_openings = boundary.no_openings

        if boundary.boundary_type == BoundaryType.SASIAD_NIEZABUDOWANY:
            return 1.5 if no_openings else 3.0

        if boundary.boundary_type == BoundaryType.SASIAD_ZABUDOWANY:
            return 3.0

        if boundary.boundary_type == BoundaryType.WLASNA:
            return 1.5 if no_openings else 3.0

        return 3.0

    @staticmethod
    def _largest_polygon(geom) -> Polygon:
        """Return the largest component if MultiPolygon, else the polygon itself."""
        if isinstance(geom, MultiPolygon):
            return max(geom.geoms, key=lambda p: p.area)
        if isinstance(geom, Polygon):
            return geom
        return Polygon()

    def max_buildable_footprint(self, plot: Plot) -> float:
        """Maximum allowed building footprint [m²], min(WZ × area, zone area)."""
        max_by_wz = plot.area * plot.mpzp.max_wz
        if plot.buildable_zone:
            return min(max_by_wz, plot.buildable_zone.area)
        return max_by_wz

    def building_inside_zone(self, plot: Plot, building_geometry: Polygon) -> bool:
        """Check whether a proposed building footprint fits inside the zone."""
        if not plot.buildable_zone:
            logger.warning("Buildable zone for %s not yet computed.", plot.number)
            return False
        return plot.buildable_zone.contains(building_geometry)

    def compute_for_many(self, plots: List[Plot]) -> None:
        """Compute the zone for a list of plots (in-place)."""
        for plot in plots:
            try:
                self.compute(plot)
            except BuildableZoneInfeasible as e:
                logger.error("Cannot compute zone for %s: %s", plot.number, e)
