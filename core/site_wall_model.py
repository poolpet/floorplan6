"""
Stage 1 — site wall model (ported from claude code/archicad-checker/models/wall.py
on 2026-05-07).

A SiteWall is one external wall of a designed building, classified by
opening presence (windows/doors → 3m setback, no openings → 1.5m setback,
WT § 12). Used by Mode A verification of human-designed projects.

Renamed from `Sciana` to `SiteWall`. Enum value strings stay Polish to
match WT 2002 paragraph references in reports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Point


class WallOpeningType(str, Enum):
    """Wall classification by opening presence."""
    Z_OTWORAMI = "Z_OTWORAMI"        # with windows/doors → min 3.0m
    BEZ_OTWOROW = "BEZ_OTWOROW"      # blank wall → min 1.5m
    NIEZNANY = "NIEZNANY"


# Compass headings in degrees (clockwise from North).
COMPASS_HEADINGS = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}


def azimuth_to_direction(azimuth_deg: float) -> str:
    """Map azimuth (degrees) to compass direction name."""
    sectors = [
        (337.5, 360.0, "N"), (0.0, 22.5, "N"),
        (22.5, 67.5, "NE"), (67.5, 112.5, "E"),
        (112.5, 157.5, "SE"), (157.5, 202.5, "S"),
        (202.5, 247.5, "SW"), (247.5, 292.5, "W"),
        (292.5, 337.5, "NW"),
    ]
    az = azimuth_deg % 360
    for mn, mx, name in sectors:
        if mn <= az < mx:
            return name
    return "N"


@dataclass
class WallOpening:
    """One window or door opening in a wall."""
    opening_type: str               # "OKNO" or "DRZWI"
    width: float                    # [m]
    height: float                   # [m]
    position_along_wall: float      # offset from wall start [m]
    archicad_guid: Optional[str] = None


@dataclass
class SiteWall:
    """One external wall of a designed building."""
    geometry: LineString                 # wall centreline
    wall_type: WallOpeningType = WallOpeningType.NIEZNANY
    openings: List[WallOpening] = field(default_factory=list)
    archicad_guid: Optional[str] = None
    thickness: float = 0.25              # [m]
    index: int = 0
    near_boundary: bool = False
    distance_to_boundary: Optional[float] = None
    boundary_type_label: Optional[str] = None

    @property
    def has_openings(self) -> bool:
        return len(self.openings) > 0

    @property
    def length(self) -> float:
        return self.geometry.length

    @property
    def azimuth_deg(self) -> float:
        """Azimuth of the outward normal (perpendicular to wall, facing outside)."""
        coords = list(self.geometry.coords)
        if len(coords) < 2:
            return 0.0
        dx = coords[1][0] - coords[0][0]
        dy = coords[1][1] - coords[0][1]
        # Right-hand normal of CCW polygon points outward.
        angle = math.degrees(math.atan2(dx, dy))
        return (angle + 360) % 360

    @property
    def compass_direction(self) -> str:
        return azimuth_to_direction(self.azimuth_deg)

    @property
    def required_min_setback(self) -> float:
        """Minimum required setback per WT § 12."""
        if self.wall_type == WallOpeningType.BEZ_OTWOROW:
            return 1.5
        return 3.0

    @property
    def midpoint(self) -> Point:
        coords = list(self.geometry.coords)
        if len(coords) >= 2:
            sx = (coords[0][0] + coords[-1][0]) / 2
            sy = (coords[0][1] + coords[-1][1]) / 2
            return Point(sx, sy)
        return Point(coords[0])

    def classify_from_openings(self) -> WallOpeningType:
        """Set wall_type based on opening list."""
        if self.openings:
            self.wall_type = WallOpeningType.Z_OTWORAMI
        else:
            self.wall_type = WallOpeningType.BEZ_OTWOROW
        return self.wall_type

    def preview_color(self) -> Tuple[int, int, int]:
        """RGB for matplotlib preview: red=3m, green=1.5m, grey=unknown."""
        if self.wall_type == WallOpeningType.Z_OTWORAMI:
            return (220, 50, 50)
        if self.wall_type == WallOpeningType.BEZ_OTWOROW:
            return (50, 180, 50)
        return (150, 150, 150)

    def violates_setback(self) -> bool:
        if self.distance_to_boundary is None:
            return False
        return self.distance_to_boundary < self.required_min_setback
