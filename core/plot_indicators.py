"""
Stage 1 — plot indicator calculator (ported from
claude code/archicad-checker/calculator.py on 2026-05-07).

Computes WZ, WIZ, PBC, parking requirements and surface balance for a
plot based on placed site elements.

WZ  = footprint_area / plot_area
WIZ = total_floor_area / plot_area
PBC = (plot_area - footprint - hard_surface) / plot_area * 100%
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Tuple

from core.plot_model import Plot
from core.site_element_model import SiteElement, SiteElementType
from rules._loader import get_default_pack

logger = logging.getLogger(__name__)

_PACK = get_default_pack()
# Floor area correction factor — usable area as fraction of footprint × floors.
# Accounts for wall thicknesses, shafts, etc. (rough estimate).
USABLE_AREA_FACTOR = _PACK.constants["usable_area_factor"]


@dataclass
class PlotIndicators:
    """Computed indicators for one plot."""
    plot_number: str

    plot_area: float = 0.0
    footprint_area: float = 0.0
    floor_count: int = 0
    total_usable_area: float = 0.0

    wz_designed: float = 0.0
    wiz_designed: float = 0.0
    pbc_m2: float = 0.0
    pbc_percent: float = 0.0

    hard_surface_area: float = 0.0      # roads + parking
    biologically_active_area: float = 0.0

    required_parking_spaces: int = 0
    designed_parking_spaces: int = 0

    errors: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Plot {self.plot_number}: "
            f"WZ={self.wz_designed:.3f}, "
            f"WIZ={self.wiz_designed:.3f}, "
            f"PBC={self.pbc_percent:.1f}%"
        )


class PlotIndicatorCalculator:
    """Computes building coverage, intensity and biologically-active area."""

    BUILDING_TYPES = {
        SiteElementType.BUDYNEK_GLOWNY,
        SiteElementType.BUDYNEK_GOSPODARCZY,
        SiteElementType.GARAZ,
    }

    HARD_SURFACE_TYPES = {
        SiteElementType.MIEJSCE_POSTOJOWE,
        SiteElementType.SMIETNIK,
    }

    def compute(self, plot: Plot, elements: List[SiteElement]) -> PlotIndicators:
        """Compute all indicators for a plot."""
        result = PlotIndicators(plot_number=plot.number)
        result.plot_area = plot.area

        if result.plot_area <= 0:
            result.errors.append("Plot area is zero or negative.")
            return result

        footprint, max_floors, usable = self._compute_buildup(elements)
        result.footprint_area = footprint
        result.floor_count = max_floors
        result.total_usable_area = usable

        result.wz_designed = footprint / result.plot_area
        result.wiz_designed = usable / result.plot_area

        hard = self._compute_hard_surface(elements)
        result.hard_surface_area = hard

        result.pbc_m2, result.pbc_percent = self._compute_pbc(
            result.plot_area, footprint, hard, elements
        )
        result.biologically_active_area = result.pbc_m2

        # Mirror back into the plot
        plot.wz_designed = result.wz_designed
        plot.wiz_designed = result.wiz_designed
        plot.pbc_designed_percent = result.pbc_percent
        plot.biologically_active_area = result.pbc_m2

        result.required_parking_spaces = self._required_parking(plot, elements)
        result.designed_parking_spaces = self._count_parking(elements)

        logger.info("Indicators: %s", result)
        return result

    def _compute_buildup(self, elements: List[SiteElement]) -> Tuple[float, int, float]:
        """Sum building footprint, find max floors, compute total usable area."""
        footprint = 0.0
        max_floors = 0
        usable = 0.0

        for el in elements:
            if el.element_type not in self.BUILDING_TYPES:
                continue
            area = self._element_area(el)
            footprint += area
            if el.floors > max_floors:
                max_floors = el.floors
            usable += area * el.floors * USABLE_AREA_FACTOR

        return footprint, max_floors, usable

    def _compute_hard_surface(self, elements: List[SiteElement]) -> float:
        return sum(
            self._element_area(el)
            for el in elements
            if el.element_type in self.HARD_SURFACE_TYPES
        )

    def _compute_pbc(
        self,
        plot_area: float,
        footprint: float,
        hard_surface: float,
        elements: List[SiteElement],
    ) -> Tuple[float, float]:
        """Compute biologically-active area in m² and as percent of plot."""
        green_zones = [
            el for el in elements if el.element_type == SiteElementType.STREFA_ZIELENI
        ]
        if green_zones:
            biological = sum(self._element_area(el) for el in green_zones)
        else:
            biological = plot_area - footprint - hard_surface

        biological = max(0.0, biological)
        percent = (biological / plot_area * 100.0) if plot_area > 0 else 0.0
        return biological, percent

    def _required_parking(self, plot: Plot, elements: List[SiteElement]) -> int:
        """Required parking spaces = sum of building units × MPZP coefficient."""
        coefficient = plot.mpzp.parking_spaces_per_unit
        total_units = sum(el.units for el in elements if el.is_building)
        if total_units == 0:
            total_units = 1   # fallback when no buildings placed yet
        return max(1, int(math.ceil(coefficient * total_units)))

    def _count_parking(self, elements: List[SiteElement]) -> int:
        total = 0
        for el in elements:
            if el.element_type in (
                SiteElementType.MIEJSCE_POSTOJOWE,
                SiteElementType.GARAZ,
            ):
                total += el.metadata.get("space_count", 1)
        return total

    @staticmethod
    def _element_area(el: SiteElement) -> float:
        if el.geometry and not el.geometry.is_empty:
            return el.geometry.area
        if el.width > 0 and el.length > 0:
            return el.width * el.length
        return 0.0

    @staticmethod
    def wz_from_areas(footprint: float, plot_area: float) -> float:
        if plot_area <= 0:
            return 0.0
        return round(footprint / plot_area, 4)

    @staticmethod
    def wiz_from_areas(usable: float, plot_area: float) -> float:
        if plot_area <= 0:
            return 0.0
        return round(usable / plot_area, 4)

    @staticmethod
    def pbc_percent_from_areas(pbc_m2: float, plot_area: float) -> float:
        if plot_area <= 0:
            return 0.0
        return round(pbc_m2 / plot_area * 100, 2)
