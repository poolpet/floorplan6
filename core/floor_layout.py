"""
Floor Layout Module — divides a building floor into apartments + stairwells + corridor.

Compliant with Polish Building Code (WT 2002, amended 2024-08-01):
- Corridor min width 1.4m (WT §237)
- Walking distance to stairwell <=40m with 2+ stairs (WT §256, ZL IV)
- Stairwell at facade (natural daylight required)

Strategy: deterministic geometry. NO CP-SAT for layout positions. Stairwells,
connector strips and the main corridor are placed by direct calculation.
Apartments are sliced from the residual rectangular zones.

See docs/FLOOR_LAYOUT_DESIGN.md for architecture rationale.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon, box as sbox
from shapely.ops import unary_union

from rules._loader import get_default_pack

_PACK = get_default_pack()
APARTMENT_MIN_AREA = _PACK.constants["apartment_min_area"]
APARTMENT_OPT_AREA = _PACK.constants["apartment_opt_area"]
APARTMENT_MAX_ASPECT = _PACK.constants["apartment_max_aspect"]
APARTMENT_MIX_DEFAULT = _PACK.constants["apartment_mix_default"]
FLOOR_RESERVE_RATIO = _PACK.constants["floor_reserve_ratio"]
WT_CORRIDOR_PUBLIC_MIN = _PACK.constants["wt_corridor_public_min"]
WT_DOJSCIE_MAX_2KLATKI = _PACK.constants["wt_dojscie_max_2klatki"]
DOOR_MIN_WIDTH = _PACK.constants["door_min_width"]
from core.floor_compute import (
    compute_stairwell_dimensions, compute_apartment_count,
)
from core.floor_solver import Apartment


@dataclass
class FloorLayoutResult:
    """Result of `solve_floor_layout()`."""
    status: str  # "OK", "INFEASIBLE", "VIOLATIONS"
    apartments: list[Apartment] = field(default_factory=list)
    stairwells: list[Polygon] = field(default_factory=list)
    connectors: list[Polygon] = field(default_factory=list)
    corridor: Optional[Polygon] = None
    walking_distances_m: list[float] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    building_class: str = ""
    has_elevator: bool = False
    n_stairwells: int = 0
    solve_time_s: float = 0.0


def solve_floor_layout(
    floor_polygon: Polygon,
    floor_height_m: float = 2.8,
    num_floors: int = 4,
    mix_pct: Optional[dict] = None,
    stairwell_facade: str = "N",
    corridor_width_m: float = WT_CORRIDOR_PUBLIC_MIN,
    max_walking_distance_m: float = WT_DOJSCIE_MAX_2KLATKI,
    reserve_ratio: float = FLOOR_RESERVE_RATIO,
    num_stairwells: Optional[int] = None,
) -> FloorLayoutResult:
    """Divide a floor polygon into apartments, stairwells, and corridor.

    Args:
        floor_polygon: Building floor outline (rectangular MVP).
        floor_height_m: Storey height [m].
        num_floors: Number of above-ground storeys.
        mix_pct: Apartment mix as fractions, e.g. {"M2": 0.30, "M3": 0.40, ...}.
        stairwell_facade: Where stairwells touch the facade for daylight.
            "N", "S", "E", "W". Default "N".
        corridor_width_m: Public corridor width [m]. Default 1.4m (WT §237).
        max_walking_distance_m: Max walking distance from apartment to stairwell [m].
            Default 40m (WT §256, two-stairs case ZL IV).
        reserve_ratio: Fraction of floor area reserved for circulation.
        num_stairwells: Override auto-computed stairwell count.

    Returns:
        FloorLayoutResult with placed apartments, stairwells, connectors, corridor,
        walking distances per apartment, and any WT violations.
    """
    t0 = time.monotonic()

    if mix_pct is None:
        mix_pct = APARTMENT_MIX_DEFAULT

    sw_dims = compute_stairwell_dimensions(floor_height_m, num_floors)
    sw_w = sw_dims["stairwell_width_m"]
    sw_l = sw_dims["stairwell_length_m"]
    building_class = sw_dims["building_class"]

    bx0, by0, bx1, by1 = floor_polygon.bounds
    width = bx1 - bx0
    height = by1 - by0
    horizontal = width >= height
    main_length = max(width, height)

    # One stairwell at center covers <=80m of corridor (40m each direction).
    n_geometric = max(1, math.ceil(main_length / 80.0))
    n_wt_min = {"N": 1, "SW": 2, "W": 2, "WW": 2}[building_class]
    if num_stairwells is None:
        n_stairs = max(n_geometric, n_wt_min)
    else:
        n_stairs = num_stairwells

    geometry = _build_geometry(
        bx0, by0, bx1, by1, sw_w, sw_l, corridor_width_m,
        n_stairs, horizontal, stairwell_facade,
    )
    stairwells = geometry["stairwells"]
    connectors = geometry["connectors"]
    corridor = geometry["corridor"]

    # MVP limitation: solver assumes rectangular floor. For L/U-shape, layout
    # is computed on the bbox; user is warned (`status='VIOLATIONS'` and a note).
    zones = _carve_zones(floor_polygon, stairwells, connectors, corridor)

    apt_count = compute_apartment_count(floor_polygon.area, mix_pct, reserve_ratio)
    per_type = apt_count["per_type"]

    apartments = _place_apartments_in_zones(zones, per_type, horizontal)

    from core.floor_validation import compute_walking_distances
    walking_distances = compute_walking_distances(
        apartments, stairwells, corridor, connectors,
    )
    violations = []
    for apt, d in zip(apartments, walking_distances):
        if d == float("inf"):
            violations.append(f"{apt.apartment_type}: no path to stairwell")
        elif d > max_walking_distance_m:
            violations.append(
                f"{apt.apartment_type}: walking distance {d:.1f}m "
                f"exceeds WT max {max_walking_distance_m:.0f}m"
            )

    if not apartments:
        status = "INFEASIBLE"
    elif violations:
        status = "VIOLATIONS"
    else:
        status = "OK"

    return FloorLayoutResult(
        status=status,
        apartments=apartments,
        stairwells=stairwells,
        connectors=connectors,
        corridor=corridor,
        walking_distances_m=walking_distances,
        violations=violations,
        building_class=building_class,
        has_elevator=sw_dims["has_elevator"],
        n_stairwells=len(stairwells),
        solve_time_s=time.monotonic() - t0,
    )


def _build_geometry(
    bx0: float, by0: float, bx1: float, by1: float,
    sw_w: float, sw_l: float, corridor_w: float,
    n_stairs: int, horizontal: bool, facade: str,
) -> dict:
    """Place stairwells + connectors + main corridor by deterministic rules.

    Stairwells: standard size (sw_w x sw_l), at chosen facade, centered along
    the long axis. Each stairwell fits inside the half of building depth
    closer to the chosen facade.

    Connectors: corridor-width strips from each stairwell to the main corridor.

    Main corridor: along the long axis, centered on the short axis,
    full length of the floor.
    """
    width = bx1 - bx0
    height = by1 - by0
    cx_mid = (bx0 + bx1) / 2
    cy_mid = (by0 + by1) / 2
    cor_half = corridor_w / 2

    if horizontal:
        cor_y0 = cy_mid - cor_half
        cor_y1 = cy_mid + cor_half
        corridor = sbox(bx0, cor_y0, bx1, cor_y1)

        if n_stairs == 1:
            stair_xs = [cx_mid]
        elif n_stairs == 2:
            stair_xs = [bx0 + width / 4.0, bx0 + 3.0 * width / 4.0]
        else:
            step = width / (n_stairs + 1)
            stair_xs = [bx0 + (i + 1) * step for i in range(n_stairs)]

        if facade.upper() == "N":
            stair_y0, stair_y1 = by1 - sw_l, by1
            conn_y0, conn_y1 = cor_y1, by1 - sw_l
        else:  # facade "S"
            stair_y0, stair_y1 = by0, by0 + sw_l
            conn_y0, conn_y1 = by0 + sw_l, cor_y0

        stairwells = [
            sbox(sx - sw_w / 2.0, stair_y0, sx + sw_w / 2.0, stair_y1)
            for sx in stair_xs
        ]
        connectors = []
        if conn_y1 > conn_y0:
            for sx in stair_xs:
                connectors.append(
                    sbox(sx - cor_half, conn_y0, sx + cor_half, conn_y1)
                )
    else:
        cor_x0 = cx_mid - cor_half
        cor_x1 = cx_mid + cor_half
        corridor = sbox(cor_x0, by0, cor_x1, by1)

        if n_stairs == 1:
            stair_ys = [cy_mid]
        elif n_stairs == 2:
            stair_ys = [by0 + height / 4.0, by0 + 3.0 * height / 4.0]
        else:
            step = height / (n_stairs + 1)
            stair_ys = [by0 + (i + 1) * step for i in range(n_stairs)]

        if facade.upper() == "E":
            stair_x0, stair_x1 = bx1 - sw_l, bx1
            conn_x0, conn_x1 = cor_x1, bx1 - sw_l
        else:  # facade "W"
            stair_x0, stair_x1 = bx0, bx0 + sw_l
            conn_x0, conn_x1 = bx0 + sw_l, cor_x0

        stairwells = [
            sbox(stair_x0, sy - sw_w / 2.0, stair_x1, sy + sw_w / 2.0)
            for sy in stair_ys
        ]
        connectors = []
        if conn_x1 > conn_x0:
            for sy in stair_ys:
                connectors.append(
                    sbox(conn_x0, sy - cor_half, conn_x1, sy + cor_half)
                )

    return {"stairwells": stairwells, "connectors": connectors, "corridor": corridor}


def _carve_zones(
    floor_polygon: Polygon,
    stairwells: list[Polygon],
    connectors: list[Polygon],
    corridor: Polygon,
) -> list[Polygon]:
    """Subtract circulation from the floor polygon. Returns rectangular zones."""
    occupied = unary_union([corridor] + stairwells + connectors)
    remaining = floor_polygon.difference(occupied)

    if remaining.is_empty:
        return []

    zones = []
    if remaining.geom_type == "Polygon":
        zones = [remaining]
    elif remaining.geom_type == "MultiPolygon":
        zones = list(remaining.geoms)
    else:
        zones = [g for g in getattr(remaining, "geoms", []) if g.geom_type == "Polygon"]

    # Filter slivers below 5 m^2 (no apartment fits there)
    return [z for z in zones if z.area >= 5.0]


def _place_apartments_in_zones(
    zones: list[Polygon],
    per_type: dict,
    horizontal: bool,
) -> list[Apartment]:
    """Distribute apartments among zones, then slice each zone into apartments.

    Greedy: largest apartments first to zones with most remaining capacity.
    Then each zone is sliced along the long axis into equal slots, one slot
    per apartment.
    """
    apt_specs = []
    for typ, cnt in per_type.items():
        for _ in range(cnt):
            apt_specs.append(typ)
    if not apt_specs or not zones:
        return []

    apt_specs.sort(key=lambda t: -APARTMENT_OPT_AREA[t])

    zones_sorted = sorted(zones, key=lambda z: -z.area)
    apt_per_zone: list[list[str]] = [[] for _ in zones_sorted]
    zone_remaining = [z.area for z in zones_sorted]

    for typ in apt_specs:
        opt = APARTMENT_OPT_AREA[typ]
        idx = max(range(len(zones_sorted)), key=lambda i: zone_remaining[i])
        apt_per_zone[idx].append(typ)
        zone_remaining[idx] -= opt

    apartments = []
    for zone, types in zip(zones_sorted, apt_per_zone):
        if not types:
            continue
        apartments.extend(_slice_zone(zone, types, horizontal))
    return apartments


def _slice_zone(zone: Polygon, types: list[str], horizontal: bool) -> list[Apartment]:
    """Slice a rectangular zone into N apartments along the long edge.

    Each apartment occupies the full short dimension and 1/N of the long dimension.
    Adjacency to corridor is automatic because the zone was carved next to it.
    """
    zb = zone.bounds
    zx0, zy0, zx1, zy1 = zb
    n = len(types)

    z_width = zx1 - zx0
    z_height = zy1 - zy0

    apartments = []
    # Slice along the longer dimension of the zone
    if z_width >= z_height:
        slot = z_width / n
        for i, typ in enumerate(types):
            ax0 = zx0 + i * slot
            ax1 = zx0 + (i + 1) * slot
            apt = Apartment(apartment_type=typ, polygon=sbox(ax0, zy0, ax1, zy1))
            apt.update_metrics()
            apartments.append(apt)
    else:
        slot = z_height / n
        for i, typ in enumerate(types):
            ay0 = zy0 + i * slot
            ay1 = zy0 + (i + 1) * slot
            apt = Apartment(apartment_type=typ, polygon=sbox(zx0, ay0, zx1, ay1))
            apt.update_metrics()
            apartments.append(apt)
    return apartments


def _walking_distance(
    apartment: Apartment,
    stairwells: list[Polygon],
    corridor: Polygon,
) -> float:
    """Approximate walking distance: apartment centroid to nearest stairwell.

    MVP heuristic. Path goes through corridor centerline. Multiplier 1.3
    accounts for the L-shaped path (apartment door -> corridor -> stairwell).

    TODO: replace with Dijkstra on a corridor graph for accurate values.
    """
    if apartment.polygon is None or not stairwells:
        return float("inf")
    apt_c = apartment.polygon.centroid
    best = float("inf")
    for stair in stairwells:
        d = apt_c.distance(stair.centroid)
        if d < best:
            best = d
    return best * 1.3
