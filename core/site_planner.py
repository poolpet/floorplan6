"""
Stage 1 — site planner / element layout (ported from
claude code/archicad-checker/optimizer.py on 2026-05-07).

Two modes:
  Mode 1 — propose_max_buildup: returns up to 3 maximum-buildup variants
           constrained by WZ, WIZ and the buildable zone.
  Mode 2 — place_building: places a building of given dimensions inside
           the buildable zone, or reports the maximum that would fit.

After the building is placed, auxiliary elements (parking, well, septic,
trash, green zone) are positioned in priority order, with Q13 + Q17
gating skipping well/septic for municipal-infrastructure or multi-family
plots.

Multi-family parking adapter: for HousingType.WIELORODZINNA, parking is
placed as a contiguous row of stalls sized to building.units × MPZP
coefficient (Q17 — well/septic always skipped per owner's decision).

Inscribed-rectangle search bug from the source was fixed during the
port (the original broke on the first fitting depth instead of finding
the largest).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple

import numpy as np
from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon, box

from core.plot_model import HousingType, Plot
from core.site_element_model import (
    STANDARD_DIMENSIONS,
    SiteElement,
    SiteElementType,
)
from rules._loader import get_default_pack

logger = logging.getLogger(__name__)

_PACK = get_default_pack()
# Usable area correction factor — loaded from pack (same value used in plot_indicators).
USABLE_AREA_FACTOR = _PACK.constants["usable_area_factor"]


@dataclass
class BuildupVariant:
    """One proposed buildup arrangement for a plot."""
    number: int
    main_building: SiteElement
    elements: List[SiteElement] = field(default_factory=list)

    wz: float = 0.0
    wiz: float = 0.0
    pbc_percent: float = 0.0
    footprint_area: float = 0.0
    wz_headroom_percent: float = 0.0   # remaining capacity vs MPZP max_wz
    description: str = ""

    def __str__(self) -> str:
        return (
            f"Variant {self.number}: footprint={self.footprint_area:.1f} m², "
            f"WZ={self.wz:.3f}, WIZ={self.wiz:.3f}, PBC={self.pbc_percent:.1f}%"
        )


class SitePlanner:
    """Greedy site planner — proposes building footprints + auxiliary elements."""

    GRID_STEP: float = 0.5
    VARIANT_COUNT: int = 3
    MIN_BUILDING_DIM: float = 4.0   # below 4m a building footprint isn't useful

    # ------------------------------------------------------------------
    # Mode 1 — propose maximum buildup
    # ------------------------------------------------------------------

    def propose_max_buildup(
        self,
        plot: Plot,
        requested_element_types: Iterable[SiteElementType],
        no_openings_direction: Optional[str] = None,
    ) -> List[BuildupVariant]:
        if not plot.buildable_zone:
            raise ValueError(
                f"Plot {plot.number} has no buildable zone — call "
                "BuildableZoneBuilder.compute() first."
            )

        zone = plot.buildable_zone
        max_wz = plot.mpzp.max_wz
        max_wiz = plot.mpzp.max_wiz
        max_floors = plot.mpzp.max_floors
        plot_area = plot.area
        max_footprint = plot_area * max_wz

        candidates = self._generate_building_candidates(
            zone, max_footprint, max_floors, max_wiz, plot_area, no_openings_direction
        )

        active_types = self._gate_element_types(plot, requested_element_types)

        variants: List[BuildupVariant] = []
        for i, (poly, floors) in enumerate(candidates[: self.VARIANT_COUNT], 1):
            building = self._building_from_polygon(plot, poly, floors)
            others = self._place_auxiliary_elements(plot, building, active_types)

            footprint = poly.area
            usable = footprint * floors * USABLE_AREA_FACTOR
            wz = footprint / plot_area
            wiz = usable / plot_area
            hard_surface = self._hard_surface_area(others)
            biological = max(0.0, plot_area - footprint - hard_surface)
            pbc_percent = biological / plot_area * 100

            variants.append(BuildupVariant(
                number=i,
                main_building=building,
                elements=[building] + others,
                wz=round(wz, 4),
                wiz=round(wiz, 4),
                pbc_percent=round(pbc_percent, 1),
                footprint_area=round(footprint, 2),
                wz_headroom_percent=round((max_wz - wz) / max_wz * 100, 1),
                description=self._variant_description(i, wz, floors, no_openings_direction),
            ))
            logger.info("Proposed %s", variants[-1])

        return variants

    def _generate_building_candidates(
        self,
        zone: Polygon,
        max_footprint: float,
        max_floors: int,
        max_wiz: float,
        plot_area: float,
        no_openings_direction: Optional[str],
    ) -> List[Tuple[Polygon, int]]:
        """Generate a small set of (footprint_polygon, floor_count) variants."""
        out: List[Tuple[Polygon, int]] = []

        poly_max = self._inscribe_max_rect(zone, max_footprint, scale=1.0)
        if poly_max:
            out.append((poly_max, 1))

        if max_floors >= 2:
            cap_2 = min(max_footprint, max_wiz * plot_area / (2 * USABLE_AREA_FACTOR))
            poly_2 = self._inscribe_max_rect(zone, cap_2, scale=0.75)
            if poly_2:
                out.append((poly_2, 2))

        if max_floors >= 3:
            cap_3 = min(max_footprint, max_wiz * plot_area / (3 * USABLE_AREA_FACTOR))
            poly_3 = self._inscribe_max_rect(zone, cap_3, scale=0.55)
            if poly_3:
                out.append((poly_3, 3))

        return out

    def _inscribe_max_rect(
        self, zone: Polygon, max_area: float, scale: float = 1.0
    ) -> Optional[Polygon]:
        """Largest axis-aligned rectangle fitting inside the zone, ≤ max_area.

        Searches a grid of (width, length) combinations centred on the zone
        centroid. Fix from the source: iterate length descending so we keep
        the LARGEST fitting rectangle for each width (the source broke on
        the smallest).
        """
        if zone.is_empty or zone.area < 1.0:
            return None

        minx, miny, maxx, maxy = zone.bounds
        max_w = (maxx - minx) * scale
        max_l = (maxy - miny) * scale

        if max_w * max_l > max_area:
            ratio = math.sqrt(max_area / (max_w * max_l))
            max_w *= ratio
            max_l *= ratio

        try:
            cx, cy = zone.centroid.x, zone.centroid.y
        except Exception:
            cx = (minx + maxx) / 2
            cy = (miny + maxy) / 2

        widths = np.arange(self.MIN_BUILDING_DIM, max_w + self.GRID_STEP, self.GRID_STEP)
        lengths = np.arange(self.MIN_BUILDING_DIM, max_l + self.GRID_STEP, self.GRID_STEP)

        best_area = 0.0
        best_rect: Optional[Polygon] = None

        for w in widths:
            for l in reversed(lengths):
                if w * l > max_area * 1.01:
                    continue
                rect = box(cx - w / 2, cy - l / 2, cx + w / 2, cy + l / 2)
                if zone.contains(rect):
                    if w * l > best_area:
                        best_area = w * l
                        best_rect = rect
                    break   # found the largest l for this w
        return best_rect

    # ------------------------------------------------------------------
    # Mode 2 — place a building of given dimensions
    # ------------------------------------------------------------------

    def place_building(
        self,
        plot: Plot,
        width: float,
        length: float,
        floors: int = 1,
        rotation_deg: float = 0.0,
    ) -> Tuple[Optional[SiteElement], Optional[str]]:
        """Try to place a building of given dimensions in the buildable zone.

        Returns (SiteElement, None) on success, or (None, message) when the
        building doesn't fit — message describes the maximum dimensions the
        zone admits.
        """
        if not plot.buildable_zone:
            return None, "Buildable zone not computed — call BuildableZoneBuilder first."

        zone = plot.buildable_zone
        rect = box(0, 0, width, length)
        if rotation_deg:
            rect = rotate(rect, rotation_deg, origin="centroid")

        position = self._find_position_in_zone(rect, zone)
        if position is not None:
            placed_rect = translate(
                rect,
                xoff=position.x - rect.centroid.x,
                yoff=position.y - rect.centroid.y,
            )
            building = self._building_from_polygon(plot, placed_rect, floors)
            building.width = width
            building.length = length
            building.rotation_deg = rotation_deg
            return building, None

        minx, miny, maxx, maxy = zone.bounds
        msg = (
            f"Budynek {width:.1f} × {length:.1f} m nie mieści się w strefie zabudowy. "
            f"Max przybliżone gabaryty: {(maxx - minx):.1f} × {(maxy - miny):.1f} m "
            f"(strefa {zone.area:.1f} m²)."
        )
        return None, msg

    def _find_position_in_zone(
        self, building: Polygon, zone: Polygon
    ) -> Optional[Point]:
        """Grid search for a centroid that places `building` fully inside `zone`."""
        minx, miny, maxx, maxy = zone.bounds
        dx = building.bounds[2] - building.bounds[0]
        dy = building.bounds[3] - building.bounds[1]
        step = self.GRID_STEP

        ys = np.arange(miny + dy / 2, maxy - dy / 2 + step, step)
        xs = np.arange(minx + dx / 2, maxx - dx / 2 + step, step)

        for y in ys:
            for x in xs:
                shifted = translate(
                    building,
                    xoff=x - building.centroid.x,
                    yoff=y - building.centroid.y,
                )
                if zone.contains(shifted):
                    return Point(x, y)
        return None

    # ------------------------------------------------------------------
    # Auxiliary element placement (Q13 + Q17 gated)
    # ------------------------------------------------------------------

    def _gate_element_types(
        self, plot: Plot, requested: Iterable[SiteElementType]
    ) -> List[SiteElementType]:
        """Filter requested element types per Q13 + Q17."""
        skip: Set[SiteElementType] = set()
        if plot.housing_type == HousingType.WIELORODZINNA:
            skip = {SiteElementType.STUDNIA, SiteElementType.SZAMBO}
        elif plot.mpzp.infrastructure_municipal:
            skip = {SiteElementType.STUDNIA, SiteElementType.SZAMBO}
        return [t for t in requested if t not in skip]

    def _place_auxiliary_elements(
        self,
        plot: Plot,
        building: SiteElement,
        active_types: List[SiteElementType],
    ) -> List[SiteElement]:
        """Greedy placement in priority order: parking → well → septic → trash → green."""
        placed: List[SiteElement] = []
        occupied: List[Polygon] = [building.geometry] if building.geometry else []

        priority = [
            SiteElementType.MIEJSCE_POSTOJOWE,
            SiteElementType.STUDNIA,
            SiteElementType.SZAMBO,
            SiteElementType.SMIETNIK,
            SiteElementType.BUDYNEK_GOSPODARCZY,
            SiteElementType.GARAZ,
            SiteElementType.STREFA_ZIELENI,    # last — fills the rest
        ]

        for kind in priority:
            if kind not in active_types:
                continue

            if kind == SiteElementType.MIEJSCE_POSTOJOWE:
                el = self._place_parking(plot, building, occupied)
            elif kind == SiteElementType.STUDNIA:
                el = self._place_well(plot, occupied)
            elif kind == SiteElementType.SZAMBO:
                el = self._place_septic(plot, building, occupied)
            elif kind == SiteElementType.STREFA_ZIELENI:
                el = self._build_green_zone(plot, occupied)
            else:
                el = self._place_standard_element(kind, plot, occupied)

            if el and el.geometry:
                placed.append(el)
                occupied.append(el.geometry)

        return placed

    # ------------------------------------------------------------------
    # Per-element placement
    # ------------------------------------------------------------------

    def _place_parking(
        self, plot: Plot, building: SiteElement, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        """Place parking. Single-family: 1 stall near road. Multi-family: row of stalls."""
        road = plot.road_boundary()
        if not road:
            return None

        if plot.housing_type == HousingType.WIELORODZINNA:
            return self._place_parking_row_multifamily(plot, building, occupied)
        return self._place_parking_single_stall(plot, occupied)

    def _place_parking_single_stall(
        self, plot: Plot, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        width, length = 2.5, 5.0
        minx, miny, maxx, maxy = plot.geometry.bounds
        target_y = miny + 3.0 + length / 2  # 3m setback from road

        for x in np.arange(minx + width / 2 + 0.5, maxx - width / 2, 0.5):
            rect = box(
                x - width / 2, target_y - length / 2,
                x + width / 2, target_y + length / 2,
            )
            if plot.geometry.contains(rect) and not any(o.intersects(rect) for o in occupied):
                el = SiteElement(
                    element_type=SiteElementType.MIEJSCE_POSTOJOWE,
                    geometry=rect,
                    position=Point(x, target_y),
                    width=width,
                    length=length,
                    metadata={"space_count": 1},
                )
                return el
        return None

    def _place_parking_row_multifamily(
        self, plot: Plot, building: SiteElement, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        """Multi-stall parking row (Q17 multi-family): N = units × coefficient."""
        coefficient = plot.mpzp.parking_spaces_per_unit
        total_units = max(1, building.units)
        n_stalls = max(1, int(math.ceil(coefficient * total_units)))

        stall_w, stall_l = 2.5, 5.0
        row_width = stall_w * n_stalls
        minx, miny, maxx, maxy = plot.geometry.bounds
        target_y = miny + 3.0 + stall_l / 2

        # Try centring the row on the plot first; fall back to scanning x.
        candidates_cx = [(minx + maxx) / 2]
        candidates_cx += list(
            np.arange(minx + row_width / 2 + 0.5, maxx - row_width / 2, 1.0)
        )

        for cx in candidates_cx:
            rect = box(
                cx - row_width / 2, target_y - stall_l / 2,
                cx + row_width / 2, target_y + stall_l / 2,
            )
            if plot.geometry.contains(rect) and not any(o.intersects(rect) for o in occupied):
                el = SiteElement(
                    element_type=SiteElementType.MIEJSCE_POSTOJOWE,
                    geometry=rect,
                    position=Point(cx, target_y),
                    width=row_width,
                    length=stall_l,
                    metadata={"space_count": n_stalls},
                )
                return el
        return None

    def _place_well(
        self, plot: Plot, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        minx, miny, maxx, maxy = plot.geometry.bounds
        radius = 0.75
        margin = 5.0 + radius
        candidates = [
            Point(maxx - margin, maxy - margin),    # NE corner
            Point(minx + margin, maxy - margin),    # NW corner
            Point(maxx - margin, (miny + maxy) / 2),
        ]
        for pt in candidates:
            circle = pt.buffer(radius)
            if plot.geometry.contains(circle) and not any(o.intersects(circle) for o in occupied):
                return SiteElement(
                    element_type=SiteElementType.STUDNIA,
                    geometry=circle,
                    position=pt,
                    width=radius * 2,
                    length=radius * 2,
                )
        return None

    def _place_septic(
        self, plot: Plot, building: SiteElement, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        minx, miny, maxx, maxy = plot.geometry.bounds
        w, l = 3.0, 4.0
        margin = 5.0
        target_y = maxy - margin - l / 2

        for x in np.arange(minx + margin + w / 2, maxx - margin - w / 2, 0.5):
            rect = box(x - w / 2, target_y - l / 2, x + w / 2, target_y + l / 2)
            if plot.geometry.contains(rect) and not any(o.intersects(rect) for o in occupied):
                return SiteElement(
                    element_type=SiteElementType.SZAMBO,
                    geometry=rect,
                    position=Point(x, target_y),
                    width=w,
                    length=l,
                )
        return None

    def _place_standard_element(
        self,
        element_type: SiteElementType,
        plot: Plot,
        occupied: List[Polygon],
    ) -> Optional[SiteElement]:
        w, l = STANDARD_DIMENSIONS.get(element_type, (2.0, 2.0))
        minx, miny, maxx, maxy = plot.geometry.bounds
        for x in np.arange(minx + w / 2 + 1, maxx - w / 2 - 1, 1.0):
            for y in np.arange(miny + l / 2 + 1, maxy - l / 2 - 1, 1.0):
                rect = box(x - w / 2, y - l / 2, x + w / 2, y + l / 2)
                if plot.geometry.contains(rect) and not any(o.intersects(rect) for o in occupied):
                    return SiteElement(
                        element_type=element_type,
                        geometry=rect,
                        position=Point(x, y),
                        width=w,
                        length=l,
                    )
        return None

    def _build_green_zone(
        self, plot: Plot, occupied: List[Polygon]
    ) -> Optional[SiteElement]:
        """Green zone fills whatever is left of the plot."""
        zone = plot.geometry
        for poly in occupied:
            try:
                zone = zone.difference(poly)
            except Exception:
                pass
        if zone.is_empty or zone.area < 1.0:
            return None
        return SiteElement(
            element_type=SiteElementType.STREFA_ZIELENI,
            geometry=zone,
            position=Point(zone.centroid.x, zone.centroid.y),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _building_from_polygon(
        plot: Plot, poly: Polygon, floors: int
    ) -> SiteElement:
        minx, miny, maxx, maxy = poly.bounds
        units = 1 if plot.housing_type == HousingType.JEDNORODZINNA else floors * 4
        return SiteElement(
            element_type=SiteElementType.BUDYNEK_GLOWNY,
            geometry=poly,
            position=Point(poly.centroid.x, poly.centroid.y),
            width=maxx - minx,
            length=maxy - miny,
            floors=floors,
            units=units,
        )

    @staticmethod
    def _hard_surface_area(elements: List[SiteElement]) -> float:
        hard_types = {SiteElementType.MIEJSCE_POSTOJOWE, SiteElementType.SMIETNIK}
        return sum(
            el.geometry.area for el in elements
            if el.element_type in hard_types and el.geometry
        )

    @staticmethod
    def _variant_description(
        number: int,
        wz: float,
        floors: int,
        no_openings: Optional[str],
    ) -> str:
        suffix = f", ściana bez otworów: {no_openings}" if no_openings else ""
        return f"Wariant {number}: WZ={wz:.0%}, {floors} kondygnacje{suffix}"
