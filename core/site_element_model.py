"""
Stage 1 — site element model (ported from claude code/archicad-checker/models/element.py
on 2026-05-07).

A SiteElement is something placed on a plot during site planning:
buildings, well, septic, parking spaces, trash, garage. Distinct from
Stage 4 Room/RoomSpec (apartment-level interiors).

Renamed from `Element` to `SiteElement` to avoid namespace clash with
Stage 4 entities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from shapely.geometry import Point, Polygon


class SiteElementType(str, Enum):
    """Site planning element types."""
    BUDYNEK_GLOWNY = "BUDYNEK_GLOWNY"
    BUDYNEK_GOSPODARCZY = "BUDYNEK_GOSPODARCZY"
    STUDNIA = "STUDNIA"
    SZAMBO = "SZAMBO"
    SMIETNIK = "SMIETNIK"
    MIEJSCE_POSTOJOWE = "MIEJSCE_POSTOJOWE"
    STREFA_ZIELENI = "STREFA_ZIELENI"
    GARAZ = "GARAZ"


class SiteElementStatus(str, Enum):
    ZGODNY = "ZGODNY"
    NIEZGODNY = "NIEZGODNY"
    OSTRZEZENIE = "OSTRZEZENIE"
    NIEZWERYFIKOWANY = "NIEZWERYFIKOWANY"


# Minimum boundary setback per element type [m].
MIN_SETBACK_FROM_BOUNDARY: Dict[SiteElementType, float] = {
    SiteElementType.BUDYNEK_GLOWNY: 3.0,        # walls dictate exact value
    SiteElementType.BUDYNEK_GOSPODARCZY: 3.0,
    SiteElementType.STUDNIA: 5.0,               # WT § 31
    SiteElementType.SZAMBO: 5.0,                # WT § 36
    SiteElementType.SMIETNIK: 3.0,
    SiteElementType.MIEJSCE_POSTOJOWE: 5.0,     # > 4 stalls
    SiteElementType.STREFA_ZIELENI: 0.0,
    SiteElementType.GARAZ: 3.0,
}

# Standard rectangle dimensions per element type [m] — (width, length).
STANDARD_DIMENSIONS: Dict[SiteElementType, tuple] = {
    SiteElementType.STUDNIA: (1.5, 1.5),
    SiteElementType.SZAMBO: (3.0, 4.0),
    SiteElementType.SMIETNIK: (2.0, 2.0),
    SiteElementType.MIEJSCE_POSTOJOWE: (2.5, 5.0),
    SiteElementType.GARAZ: (3.0, 5.5),
}


@dataclass
class SiteElement:
    """A single site planning element placed on a plot."""
    element_type: SiteElementType

    geometry: Optional[Polygon] = None
    position: Optional[Point] = None

    width: float = 0.0
    length: float = 0.0
    height: float = 0.0
    floors: int = 1
    units: int = 1                     # dwelling units in this building (multi-family scaling)
    rotation_deg: float = 0.0

    status: SiteElementStatus = SiteElementStatus.NIEZWERYFIKOWANY
    violations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    archicad_guid: Optional[str] = None
    plot_number: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def footprint_area(self) -> float:
        """Building footprint area [m²]."""
        if self.geometry:
            return self.geometry.area
        return self.width * self.length

    @property
    def is_building(self) -> bool:
        return self.element_type in (
            SiteElementType.BUDYNEK_GLOWNY,
            SiteElementType.BUDYNEK_GOSPODARCZY,
            SiteElementType.GARAZ,
        )

    def min_setback_from_boundary(self) -> float:
        return MIN_SETBACK_FROM_BOUNDARY.get(self.element_type, 3.0)

    def set_geometry_from_position(self) -> None:
        """Build a rectangle polygon from position + width + length."""
        if self.position and self.width > 0 and self.length > 0:
            x, y = self.position.x, self.position.y
            half_w, half_l = self.width / 2, self.length / 2
            self.geometry = Polygon([
                (x - half_w, y - half_l),
                (x + half_w, y - half_l),
                (x + half_w, y + half_l),
                (x - half_w, y + half_l),
            ])
