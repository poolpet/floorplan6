"""
Stage 1 — plot data model (ported from claude code/archicad-checker/models/plot.py
on 2026-05-07 with Q12–Q18 additions).

Classes: BoundaryType, HousingType, PlotBoundary, MPZPParameters, Plot.

Enum values stay Polish where they map to MPZP/WT 2002 legal terminology
(DROGA, SASIAD_ZABUDOWANY etc.) — these strings are displayed in UI and
exported in reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Polygon


class BoundaryType(str, Enum):
    """Plot boundary types affecting setback distances."""
    DROGA = "DROGA"
    SASIAD_ZABUDOWANY = "SASIAD_ZABUDOWANY"
    SASIAD_NIEZABUDOWANY = "SASIAD_NIEZABUDOWANY"
    WLASNA = "WLASNA"
    NIEZNANA = "NIEZNANA"


class HousingType(str, Enum):
    """Housing type — drives Q17 multi-family adapter and Q12 mode availability."""
    JEDNORODZINNA = "JEDNORODZINNA"   # single-family — Mode A or Mode B
    WIELORODZINNA = "WIELORODZINNA"   # multi-family — Mode A only (Q12)


# Minimum setback distances [m] per boundary type.
# Format: (with_openings, without_openings)
BOUNDARY_SETBACK: dict[BoundaryType, Tuple[float, float]] = {
    BoundaryType.DROGA: (5.0, 5.0),                # MPZP-driven, 5m default
    BoundaryType.SASIAD_ZABUDOWANY: (3.0, 3.0),    # always 3m
    BoundaryType.SASIAD_NIEZABUDOWANY: (3.0, 1.5),
    BoundaryType.WLASNA: (3.0, 1.5),
    BoundaryType.NIEZNANA: (3.0, 3.0),
}


@dataclass
class PlotBoundary:
    """One segment of a plot boundary."""
    geometry: LineString
    boundary_type: BoundaryType = BoundaryType.NIEZNANA
    segment_index: int = 0
    no_openings: bool = False  # if True, 1.5m allowed on neighbour boundaries

    @property
    def min_setback(self) -> float:
        """Minimum required setback [m]."""
        with_openings, without_openings = BOUNDARY_SETBACK[self.boundary_type]
        return without_openings if self.no_openings else with_openings

    @property
    def length(self) -> float:
        return self.geometry.length

    def label(self) -> str:
        return f"{self.boundary_type.value} | min {self.min_setback:.1f} m"


@dataclass
class MPZPParameters:
    """Local zoning plan (MPZP) parameters."""
    # Existing (from archicad-checker)
    max_wz: float = 0.30                      # max building coverage ratio
    max_wiz: float = 0.60                     # max floor area ratio
    min_pbc_percent: float = 40.0             # min biologically active area [%]
    max_height: float = 9.0                   # max building height [m]
    setback_from_road: float = 5.0            # MPZP-mandated road setback [m]
    max_floors: int = 2
    przeznaczenie: str = "MN"                 # MPZP land-use code (MN/MW/U/...)
    parking_spaces_per_unit: float = 2.0
    notes: str = ""

    # Stage 1 additions (Q13/Q15/Q2 — DECIDED 2026-05-07)
    infrastructure_municipal: bool = True     # Q13: city water/sewer; skips wt_004-008
    min_front_m: float = 18.0                 # Q15: min sub-plot front (Mode B)
    min_road_width_m: float = 4.5             # Q2: min internal-road width (Mode B)

    # Sub-plot size bounds (Mode B) — DECIDED 2026-05-08
    min_sub_plot_area_m2: float = 400.0       # cells below this go to nieużytek
    max_sub_plot_area_m2: float = 2000.0      # cells above this also go to nieużytek

    @property
    def min_pbc_fraction(self) -> float:
        return self.min_pbc_percent / 100.0


@dataclass
class Plot:
    """A buildable plot with boundary segments and zoning parameters."""
    number: str
    geometry: Polygon
    boundaries: List[PlotBoundary] = field(default_factory=list)
    mpzp: MPZPParameters = field(default_factory=MPZPParameters)
    housing_type: HousingType = HousingType.JEDNORODZINNA  # Q17

    # Computed buildable zone (set by BuildableZoneBuilder)
    buildable_zone: Optional[Polygon] = None

    # Computed indicators (set by PlotIndicatorCalculator)
    wz_designed: float = 0.0
    wiz_designed: float = 0.0
    pbc_designed_percent: float = 0.0
    biologically_active_area: float = 0.0

    @property
    def area(self) -> float:
        return self.geometry.area

    @property
    def perimeter(self) -> float:
        return self.geometry.length

    @property
    def bbox_dimensions(self) -> Tuple[float, float]:
        """Approximate plot dimensions (width, depth) [m]."""
        minx, miny, maxx, maxy = self.geometry.bounds
        return (maxx - minx, maxy - miny)

    def road_boundary(self) -> Optional[PlotBoundary]:
        """First boundary tagged as DROGA (or None)."""
        for b in self.boundaries:
            if b.boundary_type == BoundaryType.DROGA:
                return b
        return None

    def undeveloped_neighbour_boundaries(self) -> List[PlotBoundary]:
        return [
            b for b in self.boundaries
            if b.boundary_type == BoundaryType.SASIAD_NIEZABUDOWANY
        ]
