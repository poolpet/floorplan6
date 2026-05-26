"""
Stage 1 Mode B — plot subdivision (port from notebooks/stage1_subdivision_v2.py
on 2026-05-07).

Subdivides a single-family plot (Q12 — Mode B is single-family only) into
N sub-plots tiled across the entire parent geometry. Each sub-plot
extends to the property line; setbacks (line zabudowy 5 m, side 1.5 m,
rear 5 m) are constraints on building placement WITHIN each sub-plot,
not on land extent.

Decisions implemented:
  Q1(a) — clip sub-plots that overflow parent boundary; result is a
          trapezoid via Shapely intersection.
  Q1.1(d) — too-small clipped sub-plots are demoted to explicit nieużytek
          (Q1.1(c) push-neighbour deferred to a future iteration).
  Q3 (orientation) — for TERRACED and TWIN the shorter sub-plot side is
          the front (towards the road); free orientation for DETACHED.
  Q4(a) — twin-house: 1 sub-plot = 1 segment. Pairing into twin houses
          is a Stage 2/Stage 4 concern, not a subdivision concern.
  Q5(c) — orientation search picks the layout with the most sub-plots
          that have road access; ties broken by total count.
  Q15   — `MPZPParameters.min_front_m` default 18 m, MPZP override.
  Q16(a) — strict coverage `Σ sub + roads + nieużytek == parent` with
          0.5 m² floating-point tolerance.
  Q19 (2026-05-25) — ALL building types accept any road access (parent
          DROGA OR internal road). Earlier strict "TWIN/TERRACED requires
          parent DROGA" collapsed multi-row developments to ≤4 monster
          sub-plots; reverted per owner.
  Q20 (2026-05-25) — auto-scale MPZP front/area per BuildingType so that
          1 sub-plot = 1 segment (PL practice). TWIN front=min(user, 9 m),
          area×0.5. TERRACED front=min(user, 6 m), area×1/3. DETACHED
          keeps user values.

Anti-bug regressions vs C++ Plot Subdivider session 2026-04-29:
  #1 sub-plots overflow parent boundary — fixed by Shapely intersection.
  #2 internal roads overflow — fixed by clipping roads to parent.
  #3 buildable zone ignored — fixed by per-sub-plot zone validation;
     sub-plots with empty buildable zone are demoted to nieużytek.
  #4 36 zones for ~10 — fixed by min_front + min_area + min_dim guards;
     uniform grid avoids absurd cell counts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import List, Optional, Tuple

from shapely.affinity import rotate
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import split as shapely_split, unary_union

from core.buildable_zone import BuildableZoneBuilder, BuildableZoneInfeasible
from core.plot_model import (
    BoundaryType,
    HousingType,
    Plot,
    PlotBoundary,
)
from core.subdivision_roads import RoadTreeSettings, generate_road_tree_layout


class BuildingType(str, Enum):
    """Sub-plot building type — drives Q20 per-type MPZP scaling."""
    DETACHED = "DETACHED"
    TWIN = "TWIN"
    TERRACED = "TERRACED"


# Q20 (2026-05-25): per-type defaults for "1 sub-plot = 1 segment".
# TWIN segment ≈ half a twin pair; TERRACED segment ≈ one unit of a chain.
# User's MPZP min_front_m acts as an upper bound — we never enlarge above
# what the user set, only shrink to the type-appropriate default.
_BUILDING_TYPE_SEGMENT_DEFAULTS = {
    BuildingType.TWIN: {
        "front_m": 9.0,            # ½ of standard 18 m detached front
        "area_scale": 0.5,         # ½ of user min/max area
    },
    BuildingType.TERRACED: {
        "front_m": 6.0,            # ⅓ of standard 18 m
        "area_scale": 1.0 / 3.0,   # ⅓ of user min/max area
    },
}


def _with_effective_mpzp(plot: Plot, building_type: "BuildingType") -> Plot:
    """Q20 (2026-05-25): return a Plot whose MPZP front/area are scaled to
    1 sub-plot = 1 segment for TWIN/TERRACED.

    DETACHED: returns the input plot unchanged.
    TWIN/TERRACED: returns a new Plot with `mpzp.min_front_m`,
    `mpzp.min_sub_plot_area_m2`, `mpzp.max_sub_plot_area_m2` scaled per
    `_BUILDING_TYPE_SEGMENT_DEFAULTS`. User's `min_front_m` is taken as
    upper bound (we never widen the front beyond what they configured).

    Why not just shrink in inner functions? Plot.mpzp is read by many
    subdivider helpers (`_subdivide_single`, road generation, buildable
    zone per cell). Replacing at the public entry point means every
    downstream read picks up the scaled value automatically.
    """
    defaults = _BUILDING_TYPE_SEGMENT_DEFAULTS.get(building_type)
    if defaults is None:
        return plot
    mpzp = plot.mpzp
    new_mpzp = replace(
        mpzp,
        min_front_m=min(mpzp.min_front_m, defaults["front_m"]),
        min_sub_plot_area_m2=mpzp.min_sub_plot_area_m2 * defaults["area_scale"],
        max_sub_plot_area_m2=mpzp.max_sub_plot_area_m2 * defaults["area_scale"],
    )
    return replace(plot, mpzp=new_mpzp)


@dataclass
class SubPlot:
    """One subdivided plot with inferred boundaries and per-sub-plot zone."""
    polygon: Polygon
    boundaries: List[PlotBoundary] = field(default_factory=list)
    buildable_zone: Optional[Polygon] = None
    parent_droga_touch: float = 0.0    # length of edge on parent's DROGA
    internal_road_touch: float = 0.0   # length of edge on an internal road
    # Mode B building proposal (z core/building_proposer.py)
    proposed_building: Optional[Polygon] = None

    @property
    def area(self) -> float:
        return self.polygon.area

    @property
    def has_buildable_zone(self) -> bool:
        return self.buildable_zone is not None and not self.buildable_zone.is_empty

    @property
    def front_length(self) -> float:
        """Total length of edges with road access (parent's DROGA + internal)."""
        return self.parent_droga_touch + self.internal_road_touch


@dataclass
class SubdivisionResult:
    parent: Plot
    sub_plots: List[SubPlot] = field(default_factory=list)
    roads: List[Polygon] = field(default_factory=list)
    nieuzytek: Optional[Polygon] = None
    orientation_name: str = ""
    rows: int = 0
    cols: int = 0
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    @property
    def total_sub_area(self) -> float:
        return sum(s.area for s in self.sub_plots)

    @property
    def total_road_area(self) -> float:
        if not self.roads:
            return 0.0
        return unary_union(self.roads).area

    @property
    def total_buildable_area(self) -> float:
        return sum(
            s.buildable_zone.area
            for s in self.sub_plots
            if s.has_buildable_zone
        )

    @property
    def road_area_percent(self) -> float:
        return 100.0 * self.total_road_area / self.parent.area if self.parent.area else 0.0

    @property
    def buildable_area_percent(self) -> float:
        return 100.0 * self.total_buildable_area / self.parent.area if self.parent.area else 0.0

    @property
    def nieuzytek_percent(self) -> float:
        return 100.0 * self.nieuzytek_area / self.parent.area if self.parent.area else 0.0

    @property
    def sub_plots_without_road_access(self) -> int:
        return sum(1 for s in self.sub_plots if s.front_length <= 0.5)

    @property
    def nieuzytek_area(self) -> float:
        if self.nieuzytek is None or self.nieuzytek.is_empty:
            return 0.0
        return self.nieuzytek.area

    @property
    def coverage_diff(self) -> float:
        return abs(
            self.parent.area
            - self.total_sub_area
            - self.total_road_area
            - self.nieuzytek_area
        )

    def coverage_ok(self, tolerance: float = 0.5) -> bool:
        """Q16(a) strict coverage check."""
        return self.coverage_diff < tolerance

    @property
    def all_have_buildable_zone(self) -> bool:
        return all(s.has_buildable_zone for s in self.sub_plots)


# ─────────────────────────────────────────────────────────────────────────────
# Boundary inference
# ─────────────────────────────────────────────────────────────────────────────

def _line_overlap(edge: LineString, target_geom) -> float:
    """Length of edge ∩ target_geom — handles partial overlaps correctly.

    Used to compute how much of a sub-plot edge actually lies on a road
    or parent boundary, even when the road does not span the full edge
    (e.g. shortened cul-de-sac touches only the first 4.5 m of a 40 m
    sub-plot side).

    NOTE 2026-05-08: shapely's LineString-vs-LineString intersection of
    two perfectly collinear lines often returns a 0-length geometry due
    to floating-point error — every per-edge overlap reported 0 even
    though the full cell.boundary ∩ road.boundary correctly reported 8 m
    (v2 polyskel road tree debugging). Workaround: buffer the target by
    a tiny epsilon (0.01 m) so the test becomes "edge inside a thin
    ribbon around target", which is robust to FP precision.
    """
    try:
        target_buf = target_geom.buffer(0.01, cap_style=2)
        overlap = edge.intersection(target_buf)
    except Exception:
        return 0.0
    if overlap.is_empty:
        return 0.0
    if hasattr(overlap, "length") and not hasattr(overlap, "geoms"):
        return overlap.length
    if hasattr(overlap, "geoms"):
        return sum(getattr(g, "length", 0.0) for g in overlap.geoms)
    return 0.0


def _infer_boundaries(
    polygon: Polygon,
    parent: Plot,
    internal_roads: List[Polygon],
    *,
    min_overlap: float = 0.1,
) -> Tuple[List[PlotBoundary], float, float]:
    """Build PlotBoundary list for a sub-plot polygon.

    Each edge is classified by the dominant overlap among:
      - parent's DROGA boundaries → DROGA (parent_droga_touch += overlap)
      - internal road boundaries → DROGA (internal_road_touch += overlap)
      - other parent boundaries (SASIAD_*, WLASNA) → inherit by midpoint
      - interior cut (no parent overlap) → SASIAD_NIEZABUDOWANY

    Returns (boundaries, parent_droga_touch, internal_road_touch). Touches
    are *actual* line-overlap lengths, not edge lengths — handles shortened
    cul-de-sac roads correctly.
    """
    coords = list(polygon.exterior.coords)
    edges = list(zip(coords, coords[1:]))
    boundaries: List[PlotBoundary] = []
    parent_droga_touch = 0.0
    internal_road_touch = 0.0

    for i, (a, b) in enumerate(edges):
        edge = LineString([a, b])
        if edge.length < 0.01:
            continue

        # Internal road overlap (use road's boundary, not the polygon, to
        # measure shared line length).
        internal_overlap = sum(
            _line_overlap(edge, road.boundary) for road in internal_roads
        )

        # Parent's DROGA overlap.
        parent_droga_overlap = sum(
            _line_overlap(edge, b_p.geometry)
            for b_p in parent.boundaries
            if b_p.boundary_type == BoundaryType.DROGA
        )

        if internal_overlap > min_overlap or parent_droga_overlap > min_overlap:
            btype = BoundaryType.DROGA
        else:
            # Fall back to closest parent boundary by midpoint.
            midpoint = edge.interpolate(0.5, normalized=True)
            best_b: Optional[PlotBoundary] = None
            best_d = float("inf")
            for b_p in parent.boundaries:
                d = midpoint.distance(b_p.geometry)
                if d < best_d:
                    best_d = d
                    best_b = b_p
            if best_b is not None and best_d < 0.5:
                btype = best_b.boundary_type
            else:
                btype = BoundaryType.SASIAD_NIEZABUDOWANY

        boundaries.append(PlotBoundary(
            geometry=edge,
            boundary_type=btype,
            segment_index=i,
        ))
        parent_droga_touch += parent_droga_overlap
        internal_road_touch += internal_overlap

    return boundaries, parent_droga_touch, internal_road_touch


# ─────────────────────────────────────────────────────────────────────────────
# Grid generation + clipping
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# OBB recursive subdivision — Vanegas/Aliaga/Müller 2012
# Algorithm REWRITE 2026-05-08 (B1: cul-de-sac approach failed twice).
# Prototype in notebooks/stage1_obb_v1.py validated 4 cases at 100% coverage
# with 6.5–7.5% road area before porting.
# ─────────────────────────────────────────────────────────────────────────────

SHALLOW_PLOT_DEPTH = 50.0   # legacy constant, retained for back-compat
DEFAULT_MAX_DEPTH = 12      # OBB recursion cap


def _obb_long_axis(poly: Polygon) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Return (long-edge midpoint, unit vector along long axis, long length)
    of the polygon's minimum-area oriented bounding box."""
    obb = poly.minimum_rotated_rectangle
    coords = list(obb.exterior.coords)[:-1]
    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in edges]
    long_idx = max(range(4), key=lambda i: lengths[i])
    a, b = edges[long_idx]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    long_len = lengths[long_idx]
    if long_len < 1e-9:
        return mid, (1.0, 0.0), 0.0
    unit = ((b[0] - a[0]) / long_len, (b[1] - a[1]) / long_len)
    return mid, unit, long_len


def _perpendicular(unit: Tuple[float, float]) -> Tuple[float, float]:
    return (-unit[1], unit[0])


def _split_with_road(
    poly: Polygon,
    cut_point: Tuple[float, float],
    cut_direction: Tuple[float, float],
    road_w: float,
) -> Tuple[Optional[Polygon], Optional[Polygon], Optional[Polygon]]:
    """Split `poly` by a road strip of width `road_w` along the line through
    `cut_point` in `cut_direction`.

    Fix 2026-05-08: when the split produces 3+ pieces (irregular polygon
    cut by a thin strip), the smaller pieces used to be silently dropped —
    causing the parent area to leak into nieużytek and then get re-absorbed
    into a neighbour, blowing it past max_area. Now every leaf piece is
    merged into whichever of the two largest pieces is closer (by centroid),
    so 100% of the parent area is preserved through the split.
    """
    diag = math.hypot(
        poly.bounds[2] - poly.bounds[0],
        poly.bounds[3] - poly.bounds[1],
    ) * 2
    p_a = (cut_point[0] - cut_direction[0] * diag,
           cut_point[1] - cut_direction[1] * diag)
    p_b = (cut_point[0] + cut_direction[0] * diag,
           cut_point[1] + cut_direction[1] * diag)
    cut_line = LineString([p_a, p_b])

    road_strip = cut_line.buffer(road_w / 2, cap_style=2).intersection(poly)
    if road_strip.is_empty:
        return None, None, None

    children = poly.difference(road_strip)
    if children.is_empty or isinstance(children, Polygon):
        return None, None, None

    parts = [g for g in children.geoms if isinstance(g, Polygon)]
    if len(parts) < 2:
        return None, None, None
    parts.sort(key=lambda p: -p.area)
    left, right = parts[0], parts[1]

    for extra in parts[2:]:
        try:
            d_left = extra.distance(left.centroid)
            d_right = extra.distance(right.centroid)
        except Exception:
            d_left, d_right = float("inf"), float("inf")
        if d_left <= d_right:
            merged = unary_union([left, extra])
            if isinstance(merged, Polygon):
                left = merged
            elif hasattr(merged, "geoms"):
                left = max(merged.geoms, key=lambda p: p.area)
        else:
            merged = unary_union([right, extra])
            if isinstance(merged, Polygon):
                right = merged
            elif hasattr(merged, "geoms"):
                right = max(merged.geoms, key=lambda p: p.area)

    road = road_strip if isinstance(road_strip, Polygon) \
        else max(road_strip.geoms, key=lambda g: g.area)
    return left, right, road


def _split_by_line(
    poly: Polygon,
    cut_direction: Tuple[float, float],
    cut_point: Tuple[float, float],
) -> Tuple[Optional[Polygon], Optional[Polygon]]:
    """Split poly by an infinite line (no buffer) — used when smart-skipping
    a road segment so the parent's full area is preserved."""
    diag = math.hypot(
        poly.bounds[2] - poly.bounds[0],
        poly.bounds[3] - poly.bounds[1],
    ) * 2
    p_a = (cut_point[0] - cut_direction[0] * diag,
           cut_point[1] - cut_direction[1] * diag)
    p_b = (cut_point[0] + cut_direction[0] * diag,
           cut_point[1] + cut_direction[1] * diag)
    cut_line = LineString([p_a, p_b])
    try:
        result = shapely_split(poly, cut_line)
    except Exception:
        return None, None
    parts = [g for g in getattr(result, "geoms", [])
             if isinstance(g, Polygon) and g.area > 1e-3]
    if len(parts) < 2:
        return None, None
    parts.sort(key=lambda p: -p.area)
    left, right = parts[0], parts[1]
    for extra in parts[2:]:
        try:
            d_left = extra.distance(left.centroid)
            d_right = extra.distance(right.centroid)
        except Exception:
            d_left, d_right = float("inf"), float("inf")
        if d_left <= d_right:
            merged = unary_union([left, extra])
            if isinstance(merged, Polygon):
                left = merged
            elif hasattr(merged, "geoms"):
                left = max(merged.geoms, key=lambda p: p.area)
        else:
            merged = unary_union([right, extra])
            if isinstance(merged, Polygon):
                right = merged
            elif hasattr(merged, "geoms"):
                right = max(merged.geoms, key=lambda p: p.area)
    return left, right


def _balanced_split(
    poly: Polygon,
    obb_centre: Tuple[float, float],
    cut_direction: Tuple[float, float],
    along_axis_unit: Tuple[float, float],
    axis_length: float,
    road_w: float,
) -> Tuple[Optional[Polygon], Optional[Polygon], Optional[Polygon]]:
    """Binary-search the cut offset along the OBB long axis so the split
    produces children with as-equal-as-possible areas.

    Without this, irregular polygons produce extremely imbalanced splits
    (e.g. 200/3373) and recursion runs out of `max_depth` before the
    oversized child reaches `max_area`.
    """
    if axis_length < 1e-6:
        return _split_with_road(poly, obb_centre, cut_direction, road_w)

    target = poly.area / 2.0
    # Parameterize cut offset along `along_axis_unit` from -L/2 to +L/2
    # relative to obb_centre.
    lo, hi = -axis_length / 2.0, axis_length / 2.0
    best = (None, None, None)
    best_imbalance = float("inf")

    for _ in range(20):
        mid = (lo + hi) / 2.0
        cut_point = (
            obb_centre[0] + along_axis_unit[0] * mid,
            obb_centre[1] + along_axis_unit[1] * mid,
        )
        l, r, road = _split_with_road(poly, cut_point, cut_direction, road_w)
        if l is None or r is None:
            # Cut missed the interior at this offset — try moving toward centre
            if mid < 0:
                lo = mid
            else:
                hi = mid
            continue

        imbalance = abs(l.area - r.area)
        if imbalance < best_imbalance:
            best_imbalance = imbalance
            best = (l, r, road)

        # Move toward whichever side has more area
        if l.area < target:
            lo = mid
        else:
            hi = mid

    return best


def _has_road_access(
    child_poly: Polygon,
    droga_edges: List[LineString],
    road_polys: List[Polygon],
    min_overlap: float = 0.5,
) -> bool:
    """True if child shares a boundary segment with DROGA or any existing road."""
    boundary = child_poly.boundary

    def _length(g) -> float:
        if g.is_empty:
            return 0.0
        if hasattr(g, "length") and not hasattr(g, "geoms"):
            return g.length
        return sum(getattr(piece, "length", 0.0) for piece in getattr(g, "geoms", []))

    for d in droga_edges:
        try:
            if _length(boundary.intersection(d)) > min_overlap:
                return True
        except Exception:
            pass
    for r in road_polys:
        try:
            if _length(boundary.intersection(r.boundary)) > min_overlap:
                return True
        except Exception:
            pass
    return False


def _recursive_obb_split(
    poly: Polygon,
    min_area: float,
    max_area: float,
    road_w: float,
    droga_edges: List[LineString],
    all_roads: List[Polygon],
    *,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_DEPTH,
    forced_direction: Optional[Tuple[float, float]] = None,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Recursive OBB binary subdivision with smart road skipping."""
    if poly.area <= max_area or depth >= max_depth:
        return [poly], []

    obb_mid, long_unit, long_len = _obb_long_axis(poly)
    if long_len < 1e-9:
        return [poly], []

    obb_centre = (
        poly.minimum_rotated_rectangle.centroid.x,
        poly.minimum_rotated_rectangle.centroid.y,
    )

    # Find the best cut: try perpendicular-to-long with binary-search on
    # the offset along the long axis to hit the area median, then fall back
    # to along-long if perpendicular doesn't yield a viable split. Without
    # area-median search, irregular polygons gave 200/3373-style splits and
    # recursion ran out of depth — the S1=3574 oversized bug 2026-05-08.
    primary = forced_direction if forced_direction is not None else _perpendicular(long_unit)
    secondary = long_unit if forced_direction is None else _perpendicular(long_unit)
    left = right = road = None
    for direction in (primary, secondary):
        candidate = _balanced_split(poly, obb_centre, direction, long_unit, long_len, road_w)
        if candidate[0] is not None and candidate[1] is not None:
            left, right, road = candidate
            break
    if left is None or right is None:
        return [poly], []

    # Smart skip ONLY at the terminal level (children won't recurse further)
    # AND only if both children have direct DROGA or existing-road access.
    # This avoids the floating-road bug from earlier smart-skip variants
    # (since terminal cuts have no descendants to disconnect) AND avoids
    # adding redundant roads on shallow plots where sub-plots already face
    # the public street directly. Owner spec 2026-05-08 ("plot 108×40 ma
    # 3 zbędne drogi wewnętrzne").
    children_terminal = max(left.area, right.area) <= max_area
    if children_terminal and depth > 0:
        emit_road = not (
            _has_road_access(left, droga_edges, all_roads)
            and _has_road_access(right, droga_edges, all_roads)
        )
    else:
        emit_road = True

    if emit_road:
        next_roads = all_roads + [road]
        emitted = [road]
    else:
        # When skipping the road, the road-buffer area was still subtracted
        # from `left`/`right` by `_split_with_road`. Re-split by the cut LINE
        # (no buffer) so 100% of parent area is preserved across left+right.
        # This was the source of the "5627 m² leftover → 3573 m² oversized"
        # bug observed 2026-05-08.
        line_left, line_right = _split_by_line(poly, primary, obb_centre)
        if line_left is not None and line_right is not None:
            left, right = line_left, line_right
        next_roads = all_roads
        emitted = []

    sp_l, rd_l = _recursive_obb_split(
        left, min_area, max_area, road_w, droga_edges, next_roads,
        depth=depth + 1, max_depth=max_depth, forced_direction=None,
    )
    sp_r, rd_r = _recursive_obb_split(
        right, min_area, max_area, road_w, droga_edges, next_roads,
        depth=depth + 1, max_depth=max_depth, forced_direction=None,
    )
    return sp_l + sp_r, emitted + rd_l + rd_r


def _merge_small_polys(
    polys: List[Polygon],
    min_area: float,
    max_area: Optional[float] = None,
) -> List[Polygon]:
    """Merge any polygon < min_area into its longest-shared-boundary neighbour.

    Iterates until all remaining polygons have area ≥ min_area or no more
    merges are possible (polygons isolated from each other).

    When `max_area` is supplied, candidates whose post-merge area would
    exceed `max_area` are skipped — a small cell is preferable to a bloated
    one. If no candidate fits, the small cell is left as-is (accepted
    below min_area) rather than dropped, to preserve coverage.
    """
    out = list(polys)
    iteration_guard = len(out) * 4 + 10   # cap loops for safety
    while iteration_guard > 0:
        iteration_guard -= 1
        small_idx = None
        for i, p in enumerate(out):
            if p.area < min_area:
                small_idx = i
                break
        if small_idx is None:
            return out
        small = out[small_idx]
        # Score every candidate: shared-edge length descending; if max_area
        # given, only consider candidates whose post-merge area ≤ max_area.
        best_j, best_score = -1, -1.0
        for j, other in enumerate(out):
            if j == small_idx:
                continue
            try:
                shared = small.boundary.intersection(other.boundary)
                score = (shared.length if hasattr(shared, "length")
                         and not hasattr(shared, "geoms") else
                         sum(getattr(g, "length", 0.0)
                             for g in getattr(shared, "geoms", [])))
            except Exception:
                score = 0.0
            if score <= 0.0:
                continue
            if max_area is not None and (other.area + small.area) > max_area:
                continue
            if score > best_score:
                best_score = score
                best_j = j
        if best_j < 0:
            # No candidate fits within max_area. Leave the small cell alone
            # (accept below-min) and continue to the next small cell. Mark
            # by promoting it past the loop's "first below-min" scan via
            # rotation: move it to the end so we don't re-examine it.
            out.append(out.pop(small_idx))
            # If after rotation we'd revisit the same cell, terminate.
            if all(p.area < min_area for p in out):
                return out
            continue
        merged = out[best_j].union(small)
        if not isinstance(merged, Polygon):
            merged = max(merged.geoms, key=lambda p: p.area)
        out[best_j] = merged
        out.pop(small_idx)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# REWRITE #2 (2026-05-08): pattern-selection layout maximising total
# buildable area. Replaces the OBB-recursive approach which produced too
# many roads and consequently low buildable area (owner spec: PRIMARY GOAL
# of Stage 1 is maximum buildable area, roads are waste).
#
# Patterns:
#   A. single_row_no_roads — for shallow plots (depth ≤ 50 m)
#   B. single_culdesac     — one cul-de-sac, sub-plots flank both sides
#   C. multi_culdesac      — N parallel cul-de-sacs (N=2,3,4)
#
# Selector evaluates buildable_zone for each pattern and picks the layout
# with the highest total buildable area.
# ─────────────────────────────────────────────────────────────────────────────

SHALLOW_THRESHOLD = 50.0


def _pattern_single_row(plot: Plot) -> Tuple[List[Polygon], List[Polygon]]:
    """Single row of sub-plots facing DROGA. NO internal roads."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny
    min_front = plot.mpzp.min_front_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    cols = max(1, int(parent_w // min_front))
    cell_w = parent_w / cols
    if cell_w * parent_d > max_area * 1.5:
        return [], []
    sub_polys = [
        box(minx + c * cell_w, miny, minx + (c + 1) * cell_w, maxy).intersection(plot.geometry)
        for c in range(cols)
    ]
    sub_polys = [p for p in sub_polys if isinstance(p, Polygon) and p.area > 1.0]
    return sub_polys, []


def _pattern_single_culdesac(plot: Plot) -> Tuple[List[Polygon], List[Polygon]]:
    """Single cul-de-sac perpendicular to DROGA. Sub-plots flank both sides."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny
    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    droga = plot.road_boundary()
    if droga is not None:
        coords = list(droga.geometry.coords)
        cx = (coords[0][0] + coords[-1][0]) / 2
    else:
        cx = (minx + maxx) / 2
    road_xmin = cx - road_w / 2
    road_xmax = cx + road_w / 2
    left_w = road_xmin - minx
    right_w = maxx - road_xmax
    if left_w < min_front or right_w < min_front:
        return [], []

    target_strip_w = max(left_w, right_w)
    target_row_d = max(min_front, max_area / target_strip_w)
    n_rows = max(1, math.ceil(parent_d / target_row_d))
    row_d = parent_d / n_rows
    if n_rows == 1:
        road_ymax = miny + min(road_w, row_d)
    else:
        road_ymax = miny + (n_rows - 1) * row_d + min(road_w, row_d / 2)

    road = box(road_xmin, miny, road_xmax, road_ymax).intersection(plot.geometry)
    if not isinstance(road, Polygon) or road.is_empty:
        return [], []

    sub_polys = []
    for r in range(n_rows):
        ry0 = miny + r * row_d
        ry1 = ry0 + row_d
        for x_range in [(minx, road_xmin), (road_xmax, maxx)]:
            cell = box(x_range[0], ry0, x_range[1], ry1).intersection(plot.geometry)
            if isinstance(cell, Polygon) and cell.area > 1.0:
                sub_polys.append(cell)
    return sub_polys, [road]


def _pattern_multi_culdesac(
    plot: Plot, n_culdesacs: int,
) -> Tuple[List[Polygon], List[Polygon]]:
    """N parallel cul-de-sacs. Sub-plots flank both sides of each."""
    minx, miny, maxx, maxy = plot.geometry.bounds
    parent_w = maxx - minx
    parent_d = maxy - miny
    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    bay_w = parent_w / n_culdesacs
    strip_w = (bay_w - road_w) / 2
    if strip_w < min_front:
        return [], []

    target_row_d = max(min_front, max_area / strip_w)
    n_rows = max(1, math.ceil(parent_d / target_row_d))
    row_d = parent_d / n_rows
    if n_rows == 1:
        road_ymax_offset = min(road_w, row_d)
    else:
        road_ymax_offset = (n_rows - 1) * row_d + min(road_w, row_d / 2)
    road_ymax_abs = miny + road_ymax_offset

    sub_polys: List[Polygon] = []
    roads: List[Polygon] = []
    for cds_i in range(n_culdesacs):
        bay_xmin = minx + cds_i * bay_w
        bay_xmax = minx + (cds_i + 1) * bay_w
        cx = (bay_xmin + bay_xmax) / 2
        road_xmin = cx - road_w / 2
        road_xmax = cx + road_w / 2
        road = box(road_xmin, miny, road_xmax, road_ymax_abs).intersection(plot.geometry)
        if isinstance(road, Polygon) and not road.is_empty:
            roads.append(road)
        for r in range(n_rows):
            ry0 = miny + r * row_d
            ry1 = ry0 + row_d
            for x_range in [(bay_xmin, road_xmin), (road_xmax, bay_xmax)]:
                cell = box(x_range[0], ry0, x_range[1], ry1).intersection(plot.geometry)
                if isinstance(cell, Polygon) and cell.area > 1.0:
                    sub_polys.append(cell)
    return sub_polys, roads


def _evaluate_buildable(
    plot: Plot, sub_polys: List[Polygon], roads: List[Polygon],
) -> float:
    """Sum of per-sub-plot buildable_zone areas — the metric that pattern
    selection optimises (owner spec: maximise buildable area)."""
    builder = BuildableZoneBuilder()
    total = 0.0
    for poly in sub_polys:
        boundaries, _, _ = _infer_boundaries(poly, plot, roads)
        sub = Plot(
            number="ev", geometry=poly, boundaries=boundaries,
            mpzp=plot.mpzp, housing_type=plot.housing_type,
        )
        try:
            zone = builder.compute(sub)
            if zone is not None and not zone.is_empty:
                total += zone.area
        except BuildableZoneInfeasible:
            pass
    return total


def _rotate_plot_to_droga_horizontal(
    plot: Plot,
) -> Tuple[Plot, float, Tuple[float, float]]:
    """Rotate the plot so that its DROGA edge becomes horizontal at the
    bottom of the rotated frame.

    Returns (rotated_plot, rotation_angle_deg, pivot). To map sub-plots
    back to the original frame, rotate by `+rotation_angle_deg` around
    `pivot`. If the plot has no DROGA edge, returns the plot unchanged.
    """
    droga = plot.road_boundary()
    if droga is None or droga.geometry.length < 1e-6:
        return plot, 0.0, (0.0, 0.0)

    coords = list(droga.geometry.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    angle_deg = math.degrees(math.atan2(dy, dx))
    pivot = ((coords[0][0] + coords[-1][0]) / 2,
             (coords[0][1] + coords[-1][1]) / 2)

    if abs(angle_deg) < 0.5:
        return plot, 0.0, pivot   # already horizontal — no rotation needed

    # Rotate plot polygon and boundaries by -angle_deg around pivot.
    rotated_geom = rotate(plot.geometry, -angle_deg, origin=pivot)
    rotated_boundaries = []
    for b in plot.boundaries:
        rotated_boundaries.append(PlotBoundary(
            geometry=rotate(b.geometry, -angle_deg, origin=pivot),
            boundary_type=b.boundary_type,
            segment_index=b.segment_index,
            no_openings=b.no_openings,
        ))
    rotated_plot = Plot(
        number=plot.number,
        geometry=rotated_geom,
        boundaries=rotated_boundaries,
        mpzp=plot.mpzp,
        housing_type=plot.housing_type,
    )
    return rotated_plot, angle_deg, pivot


# ─────────────────────────────────────────────────────────────────────────────
# REWRITE #4 (2026-05-08): katana algorithm (Snorfalorpagus 2016, BSD-2).
# Replaces pattern-selection layout — that approach failed on irregular
# plots because patterns assume bbox-rectangular plots, and the user's
# real input is "prawie nigdy nie zdarza się prostokąt idealny".
#
# Katana = recursive shapely bisection along the longest bbox dimension,
# until every cell's bbox max-dim ≤ threshold. Threshold derived from
# target area (mid of [min, max]). Validated in notebooks/stage1_katana_v1.py
# on 4 cases including irregular 188×400m: 72 cells, 71/72 in [400-1500],
# 60.5% buildable. v1 has NO roads — v2 will add polyskel road network on
# top.
# ─────────────────────────────────────────────────────────────────────────────


def _katana(geometry: Polygon, threshold: float, count: int = 0) -> List[Polygon]:
    """Recursively split `geometry` along its longest bbox dimension until
    every leaf's max bbox dim ≤ threshold. Snorfalorpagus 2016, BSD-2."""
    bounds = geometry.bounds
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    if max(width, height) <= threshold or count == 250:
        return [geometry]
    if height >= width:
        a = box(bounds[0], bounds[1], bounds[2], bounds[1] + height / 2)
        b = box(bounds[0], bounds[1] + height / 2, bounds[2], bounds[3])
    else:
        a = box(bounds[0], bounds[1], bounds[0] + width / 2, bounds[3])
        b = box(bounds[0] + width / 2, bounds[1], bounds[2], bounds[3])
    result: List[Polygon] = []
    for d in (a, b):
        c = geometry.intersection(d)
        if c.is_empty:
            continue
        if isinstance(c, MultiPolygon):
            pieces = list(c.geoms)
        else:
            pieces = [c]
        for piece in pieces:
            if not isinstance(piece, Polygon) or piece.is_empty:
                continue
            result.extend(_katana(piece, threshold, count + 1))
    return result


def _katana_oriented(
    geometry: Polygon,
    max_area: float,
    target_front: float,
    count: int = 0,
) -> List[Polygon]:
    """Directional katana — cuts perpendicular-to-x (vertical) first to
    create narrow strips of width ≤ target_front × 2, then cuts along x
    (horizontal) to bring each strip's area ≤ max_area.

    Caller rotates geometry to DROGA-horizontal frame first, so:
      - x axis runs along DROGA (street front direction)
      - y axis runs perpendicular to DROGA (lot depth direction)
      - vertical cut (x = midpoint) splits a wide strip into 2 narrower
        ones — gives each cell its own DROGA-parallel front
      - horizontal cut (y = midpoint) cuts a deep strip into 2 stacked
        sub-plots — needed when the column is too long

    Architecturally this is correct: lots are narrow & deep (front 18-25m
    along DROGA, depth 40-80m back), not square. Square katana made one
    horizontal road per row of cells (16 rows → 17.9% road area). Oriented
    katana makes few deep rows → fewer roads → ~5-8% road area, more
    buildable.
    """
    if geometry.area <= max_area or count == 250:
        return [geometry]

    bounds = geometry.bounds
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]

    # Cut vertical (reduce width) when width is still wide enough that a
    # halved piece would remain ≥ target_front. Else cut horizontal.
    if w > target_front * 2:
        a = box(bounds[0], bounds[1], bounds[0] + w / 2, bounds[3])
        b = box(bounds[0] + w / 2, bounds[1], bounds[2], bounds[3])
    else:
        a = box(bounds[0], bounds[1], bounds[2], bounds[1] + h / 2)
        b = box(bounds[0], bounds[1] + h / 2, bounds[2], bounds[3])

    result: List[Polygon] = []
    for d in (a, b):
        c = geometry.intersection(d)
        if c.is_empty:
            continue
        if isinstance(c, MultiPolygon):
            pieces = list(c.geoms)
        else:
            pieces = [c]
        for piece in pieces:
            if not isinstance(piece, Polygon) or piece.is_empty or piece.area < 1.0:
                continue
            result.extend(_katana_oriented(piece, max_area, target_front, count + 1))
    return result


def _shared_edge(a: Polygon, b: Polygon, eps: float = 0.01) -> Optional[LineString]:
    """Return shared boundary between two adjacent cells as a LineString,
    or None if they only touch at a point or not at all."""
    try:
        # Buffer one boundary slightly to absorb FP error in collinear lines.
        shared = a.boundary.intersection(b.boundary.buffer(eps, cap_style=2))
    except Exception:
        return None
    if shared.is_empty:
        return None
    if isinstance(shared, LineString):
        return shared if shared.length > 0.5 else None
    if hasattr(shared, "geoms"):
        # Multi-piece — pick longest
        lines = [g for g in shared.geoms if isinstance(g, LineString) and g.length > 0.5]
        if not lines:
            return None
        return max(lines, key=lambda g: g.length)
    return None


def _compute_road_tree_mst(
    plot: Plot,
    cells: List[Polygon],
    road_w: float,
) -> List[LineString]:
    """Compute road tree via max-spanning tree on cell adjacency dual graph.

    Approach (REWRITE 2026-05-08, after polyskel feedback "drogi rozchodzą
    się do granicy działki — marnują przestrzeń"):
      1. Build dual graph: nodes=cells, edges=shared boundaries between
         adjacent cell pairs, weighted by shared-edge length.
      2. Add virtual DROGA node connected (zero cost) to every cell
         touching parent's DROGA edge.
      3. Maximum spanning tree on this graph (Kruskal, picking longest
         shared edges first) — gives a TREE rooted at DROGA reaching
         every cell with no cycles, no redundant branches.
      4. Activated cell-cell edges = road segments. Roads NEVER touch
         non-DROGA plot boundary because they live BETWEEN cells.

    Returns the list of activated shared-edge LineStrings (not yet
    buffered to road polygons).
    """
    if not cells:
        return []
    droga = plot.road_boundary()
    if droga is None:
        return []

    n = len(cells)
    # Build adjacency
    edges: List[Tuple[float, int, int, LineString]] = []
    for i in range(n):
        for j in range(i + 1, n):
            shared = _shared_edge(cells[i], cells[j])
            if shared is None:
                continue
            edges.append((shared.length, i, j, shared))

    # Find cells touching parent's DROGA
    droga_geom = droga.geometry
    droga_buf = droga_geom.buffer(0.01, cap_style=2)
    droga_cells = []
    for i, c in enumerate(cells):
        try:
            overlap = c.boundary.intersection(droga_buf)
            length = (overlap.length if hasattr(overlap, "length")
                      and not hasattr(overlap, "geoms") else
                      sum(getattr(g, "length", 0.0)
                          for g in getattr(overlap, "geoms", [])))
        except Exception:
            length = 0.0
        if length > 0.5:
            droga_cells.append(i)

    if not droga_cells:
        return []

    # Kruskal max-spanning tree (sort by length descending — prefer longest
    # shared edges so roads run along natural cell boundaries, not corners).
    edges.sort(key=lambda e: -e[0])

    parent = list(range(n + 1))                          # +1 for virtual DROGA
    rank = [0] * (n + 1)
    DROGA_NODE = n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
        return True

    # First connect DROGA-cells to virtual node (zero-cost — always taken).
    for i in droga_cells:
        union(i, DROGA_NODE)

    activated: List[LineString] = []
    for length, i, j, shared in edges:
        if union(i, j):
            activated.append(shared)
        # Stop early when MST complete (all n+1 nodes connected).
        # Optimization: continue scanning is cheap on small N.

    return activated


def _compute_road_tree(
    plot: Plot,
    road_w: float,
) -> List[Polygon]:
    """v2 polyskel road tree — straight-skeleton medial axis rooted at DROGA.

    Pipeline:
      1. Compute straight skeleton via ladybug-geometry-polyskel.
      2. Keep skeleton edges that are either interior↔interior (spine) or
         interior↔exterior-on-DROGA (entry ramp from public road).
      3. Buffer kept edges by road_w/2 → road polygons.
      4. Clip to parent geometry.

    Returns [] if the plot has no DROGA edge or the skeleton fails.
    """
    droga = plot.road_boundary()
    if droga is None or droga.geometry.length < 1e-6:
        return []

    try:
        from ladybug_geometry.geometry2d.polygon import Polygon2D
        from ladybug_geometry.geometry2d.pointvector import Point2D
        from ladybug_geometry_polyskel import polysplit
    except ImportError:
        return []

    coords = list(plot.geometry.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    if len(coords) < 3:
        return []
    try:
        lb_poly = Polygon2D([Point2D(x, y) for x, y in coords])
        graph = polysplit.skeleton_as_directed_graph(lb_poly)
    except Exception:
        return []

    droga_geom = droga.geometry

    from shapely.geometry import Point as ShapelyPoint

    def _on_droga(pt2d, tol: float = 0.5) -> bool:
        return ShapelyPoint(pt2d.x, pt2d.y).distance(droga_geom) < tol

    edges_kept: List[LineString] = []
    seen = set()
    for node in list(graph.nodes):
        for adj in node.adj_lst:
            a = (round(node.pt.x, 3), round(node.pt.y, 3))
            b = (round(adj.pt.x, 3), round(adj.pt.y, 3))
            key = tuple(sorted([a, b]))
            if key in seen:
                continue
            seen.add(key)

            n_int = not node.exterior
            a_int = not adj.exterior
            keep = False
            if n_int and a_int:
                keep = True                                 # spine edge
            elif n_int and not a_int and _on_droga(adj.pt):
                keep = True                                 # entry ramp
            elif a_int and not n_int and _on_droga(node.pt):
                keep = True                                 # entry ramp

            if keep:
                edges_kept.append(LineString(
                    [(node.pt.x, node.pt.y), (adj.pt.x, adj.pt.y)]
                ))

    if not edges_kept:
        return []

    # Fishbone: for plots wider than ~80m along the spine, the medial axis
    # alone leaves rows of cells far from any road. Add perpendicular
    # branches every BRANCH_SPACING along each long spine segment so every
    # cell ends up adjacent to a road. Without this, a 401×188 plot keeps
    # ~80 of 125 cells without road access (AC test 2026-05-08).
    BRANCH_SPACING = 50.0
    LONG_SPINE_THRESHOLD = 80.0
    branches: List[LineString] = []
    diag = max(
        plot.geometry.bounds[2] - plot.geometry.bounds[0],
        plot.geometry.bounds[3] - plot.geometry.bounds[1],
    ) * 2
    for seg in edges_kept:
        (x0, y0), (x1, y1) = list(seg.coords)[0], list(seg.coords)[1]
        dx, dy = x1 - x0, y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len < LONG_SPINE_THRESHOLD:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        px, py = -uy, ux                                    # perpendicular
        n_branches = int(seg_len / BRANCH_SPACING)
        if n_branches < 1:
            continue
        for i in range(1, n_branches + 1):
            t = i * BRANCH_SPACING - BRANCH_SPACING / 2
            cx = x0 + ux * t
            cy = y0 + uy * t
            line = LineString([
                (cx - px * diag, cy - py * diag),
                (cx + px * diag, cy + py * diag),
            ])
            piece = line.intersection(plot.geometry)
            if piece.is_empty:
                continue
            if isinstance(piece, LineString):
                if piece.length > 1.0:
                    branches.append(piece)
            elif hasattr(piece, "geoms"):
                for g in piece.geoms:
                    if isinstance(g, LineString) and g.length > 1.0:
                        branches.append(g)

    all_segments = edges_kept + branches

    # Buffer each segment, union and clip.
    buffered = unary_union([
        ls.buffer(road_w / 2, cap_style=2) for ls in all_segments
    ])
    clipped = buffered.intersection(plot.geometry)
    out: List[Polygon] = []
    if isinstance(clipped, Polygon):
        if not clipped.is_empty:
            out.append(clipped)
    elif hasattr(clipped, "geoms"):
        for g in clipped.geoms:
            if isinstance(g, Polygon) and not g.is_empty and g.area > 0.5:
                out.append(g)
    return out


def _generate_obb_layout(
    plot: Plot,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Single-trunk + ribs + 2-row blocks (REWRITE #5 2026-05-08).

    Based on standard urban-planning rules for residential subdivisions
    derived from Polish/EU developer-built osiedla wolnostojące/szeregowe
    /bliźniacze:

      RULES:
      R1. Single entry from DROGA — one trunk perpendicular to public road,
          centred on DROGA midpoint.
      R2. Trunk extends inward to plot's deep boundary (with margin).
      R3. Inter-block roads (ribs) perpendicular to trunk, at intervals
          of 2× lot_depth + road_w. Each rib serves 2 rows of lots
          (one row in front, one in back, sharing rear fence).
      R4. Lots arranged in 2-row blocks; lots are RECTANGULAR with
          front along DROGA-parallel direction.
      R5. Lot front ≈ min_front_m (MPZP); lot depth = max_area / front.
      R6. Result is a STRICT TREE: trunk (root) → ribs (branches) → lots
          (leaves). No cycles, no roads to non-DROGA plot boundary.

    Pipeline:
      1. Rotate plot so DROGA edge runs along x at the bottom.
      2. Compute trunk position (centre of DROGA range).
      3. Compute number of blocks fitting plot depth, derive block_depth.
      4. Lay out trunk + ribs as rectangular road strips, clip to plot.
      5. Subtract roads from plot → "block half" pieces (left and right
         of trunk, between consecutive ribs).
      6. Each block half: subdivide into n_cols × n_rows_in_piece cells
         using a regular grid clipped to the piece.
      7. Rotate back.

    Replaces v3 oriented-katana + MST (rejected: roads still looked like
    a comb/grid not "branches from trunk") and earlier polyskel/square
    katana variants.
    """
    min_area = plot.mpzp.min_sub_plot_area_m2
    max_area = plot.mpzp.max_sub_plot_area_m2
    target_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m

    rotated_plot, angle_deg, pivot = _rotate_plot_to_droga_horizontal(plot)
    geom = rotated_plot.geometry
    minx, miny, maxx, maxy = geom.bounds
    plot_w = maxx - minx
    plot_h = maxy - miny

    # R5: lot dimensions — target_depth = max_area / target_front so a cell
    # of target_front × target_depth = max_area (upper bound).
    target_depth = max(max_area / max(target_front, 1.0), 1.0)

    # R3 (revised): one row of lots per "block", separated by ribs. Each
    # row has its FRONT touching the road below it (DROGA for row 0, ribs
    # for higher rows). Tried 2-row blocks (back-to-back, shared rear fence)
    # but on shallow plots (n_blocks=1) the back row had no rib above and
    # got dropped — losing 50% of the plot to nieużytek (AC test 2026-05-08).
    period = target_depth + road_w
    n_rows = max(1, math.ceil((plot_h + road_w) / period))
    actual_row_depth = (plot_h - max(0, n_rows - 1) * road_w) / n_rows

    # R1: trunk x = centre of DROGA (rotated frame)
    droga = rotated_plot.road_boundary()
    if droga is not None:
        droga_coords = list(droga.geometry.coords)
        droga_xs = [p[0] for p in droga_coords]
        trunk_x = (min(droga_xs) + max(droga_xs)) / 2
    else:
        trunk_x = (minx + maxx) / 2

    trunk_xmin = trunk_x - road_w / 2
    trunk_xmax = trunk_x + road_w / 2

    # R1, R2: trunk rectangle. It must connect DROGA to the last branch,
    # but it must NOT run to a non-road boundary. The previous full-height
    # trunk wasted land and produced exactly the "road to nowhere" failure
    # visible in AC tests.
    last_branch_top = miny
    if n_rows > 1:
        last_branch_y = miny + (n_rows - 1) * actual_row_depth + (n_rows - 2) * road_w
        last_branch_top = last_branch_y + road_w
    trunk_end_y = min(maxy, max(miny + road_w, last_branch_top))
    trunk_box = box(trunk_xmin, miny, trunk_xmax, trunk_end_y)
    trunk_clipped = trunk_box.intersection(geom)
    roads: List[Polygon] = []
    if isinstance(trunk_clipped, Polygon) and not trunk_clipped.is_empty:
        roads.append(trunk_clipped)
    elif hasattr(trunk_clipped, "geoms"):
        for g in trunk_clipped.geoms:
            if isinstance(g, Polygon) and not g.is_empty and g.area > 0.5:
                roads.append(g)

    # R3 (revised): ribs between consecutive rows. Rib i (i=1..n_rows-1)
    # sits between row i-1 (below) and row i (above). Row i's FRONT (its
    # bottom edge) faces rib i. Without the rib, row i has no road access.
    edge_clearance = max(road_w * 1.1, target_front * 0.5)

    for i in range(1, n_rows):
        y_road = miny + i * actual_row_depth + (i - 1) * road_w
        y_mid = y_road + road_w / 2
        cross = geom.intersection(LineString([
            (minx - plot_w * 2, y_mid),
            (maxx + plot_w * 2, y_mid),
        ]))
        segments = []
        if isinstance(cross, LineString) and not cross.is_empty:
            segments = [cross]
        elif hasattr(cross, "geoms"):
            segments = [g for g in cross.geoms
                        if isinstance(g, LineString) and g.length > 0.1]
        if not segments:
            continue

        def _seg_score(seg: LineString) -> Tuple[int, float]:
            xs = [p[0] for p in seg.coords]
            contains_trunk = min(xs) <= trunk_x <= max(xs)
            return (1 if contains_trunk else 0, seg.length)

        segment = max(segments, key=_seg_score)
        xs = [p[0] for p in segment.coords]
        rib_minx = min(xs) + edge_clearance
        rib_maxx = max(xs) - edge_clearance
        if rib_maxx <= rib_minx:
            continue
        # Branches serve lots on both sides and stop at the last served plot.
        # They intentionally stay off non-DROGA parcel boundaries; access is
        # by shared frontage along the branch, not by extending the road to
        # the cadastral edge.
        rib_box = box(rib_minx, y_road, rib_maxx, y_road + road_w)
        rib_clipped = rib_box.intersection(geom)
        if isinstance(rib_clipped, Polygon) and not rib_clipped.is_empty:
            roads.append(rib_clipped)
        elif hasattr(rib_clipped, "geoms"):
            for g in rib_clipped.geoms:
                if isinstance(g, Polygon) and not g.is_empty and g.area > 0.5:
                    roads.append(g)

    if not roads:
        return [], []

    roads_union = unary_union(roads)

    # R5, R7: subdivide each "block half" into 2 rows × n_cols of cells
    remaining = geom.difference(roads_union)
    if isinstance(remaining, Polygon):
        block_pieces = [remaining]
    elif hasattr(remaining, "geoms"):
        block_pieces = [g for g in remaining.geoms
                        if isinstance(g, Polygon) and g.area > 1.0]
    else:
        block_pieces = []

    cells: List[Polygon] = []
    for piece in block_pieces:
        pminx, pminy, pmaxx, pmaxy = piece.bounds
        pw = pmaxx - pminx
        ph = pmaxy - pminy
        if pw < 1.0 or ph < 1.0:
            continue
        # Cols: ceil for col_w ≤ target_front, but back off if it forces
        # col_w below 0.85 × target_front (MPZP min frontage).
        n_cols = max(1, math.ceil(pw / target_front))
        col_w = pw / n_cols
        min_col_w = target_front * 0.85
        while n_cols > 1 and col_w < min_col_w:
            n_cols -= 1
            col_w = pw / n_cols
        # Rows: solve for area constraint given col_w.
        # cell.area ≈ col_w × row_h; want ≤ max_area.
        n_rows = max(1, math.ceil(col_w * ph / max_area))
        row_h = ph / n_rows
        for c in range(n_cols):
            for r in range(n_rows):
                cell_box = box(
                    pminx + c * col_w,
                    pminy + r * row_h,
                    pminx + (c + 1) * col_w,
                    pminy + (r + 1) * row_h,
                )
                cell = cell_box.intersection(piece)
                if isinstance(cell, Polygon) and cell.area > 1.0:
                    cells.append(cell)
                elif hasattr(cell, "geoms"):
                    for g in cell.geoms:
                        if isinstance(g, Polygon) and g.area > 1.0:
                            cells.append(g)

    # Rotate back to original frame
    if abs(angle_deg) > 0.01:
        cells = [rotate(c, angle_deg, origin=pivot) for c in cells]
        roads = [rotate(r, angle_deg, origin=pivot) for r in roads]

    return cells, roads


def _generate_obb_layout_PATTERNS_LEGACY(
    plot: Plot,
) -> Tuple[List[Polygon], List[Polygon]]:
    """Pattern-selecting layout — kept for reference. NOT called.

    Picked among single_row / single_culdesac / multi_culdesac the layout
    with maximum total buildable area. Failed on irregular plots — replaced
    by katana 2026-05-08.
    """
    rotated_plot, angle_deg, pivot = _rotate_plot_to_droga_horizontal(plot)
    minx, miny, maxx, maxy = rotated_plot.geometry.bounds
    parent_d = maxy - miny

    candidates: List[Tuple[float, List[Polygon], List[Polygon]]] = []

    if parent_d <= SHALLOW_THRESHOLD * 1.2:
        sp, rd = _pattern_single_row(rotated_plot)
        if sp:
            candidates.append((_evaluate_buildable(rotated_plot, sp, rd), sp, rd))

    sp, rd = _pattern_single_culdesac(rotated_plot)
    if sp:
        candidates.append((_evaluate_buildable(rotated_plot, sp, rd), sp, rd))

    for n in (2, 3, 4):
        sp, rd = _pattern_multi_culdesac(rotated_plot, n)
        if sp:
            candidates.append((_evaluate_buildable(rotated_plot, sp, rd), sp, rd))

    if not candidates:
        return [], []

    candidates.sort(key=lambda c: -c[0])
    _, sub_polys, roads = candidates[0]

    if abs(angle_deg) > 0.01:
        sub_polys = [rotate(p, angle_deg, origin=pivot) for p in sub_polys]
        roads = [rotate(r, angle_deg, origin=pivot) for r in roads]

    return sub_polys, roads


def _generate_obb_layout_LEGACY(
    plot: Plot,
) -> Tuple[List[Polygon], List[Polygon]]:
    """OBB recursive layout — kept as legacy for reference. NOT called.

    Pipeline:
      1. Run recursive OBB split with smart road skipping.
      2. Merge any polygon < min_area into its largest neighbour
         (post-pass for imbalanced splits — see `_recursive_obb_split`).
    """
    min_area = plot.mpzp.min_sub_plot_area_m2
    max_area = plot.mpzp.max_sub_plot_area_m2
    road_w = plot.mpzp.min_road_width_m

    droga = plot.road_boundary()
    droga_edges: List[LineString] = []
    forced: Optional[Tuple[float, float]] = None
    if droga is not None and droga.geometry.length > 0:
        coords = list(droga.geometry.coords)
        dx = coords[-1][0] - coords[0][0]
        dy = coords[-1][1] - coords[0][1]
        droga_len = math.hypot(dx, dy)
        if droga_len > 1e-6:
            droga_unit = (dx / droga_len, dy / droga_len)
            forced = _perpendicular(droga_unit)
            droga_edges = [droga.geometry]

    sub_polys, roads = _recursive_obb_split(
        plot.geometry, min_area, max_area, road_w,
        droga_edges, all_roads=[],
        depth=0, max_depth=DEFAULT_MAX_DEPTH, forced_direction=forced,
    )
    sub_polys = _merge_small_polys(sub_polys, min_area)
    return sub_polys, roads


def _droga_extent_in_working(plot: Plot, rotated_90: bool):
    """Extent of DROGA edge along working-x axis (after rotated swap if any).

    Returns (xmin, xmax) or (None, None) if no DROGA boundary.
    """
    droga = plot.road_boundary()
    if droga is None:
        return None, None
    coords = list(droga.geometry.coords)
    if len(coords) < 2:
        return None, None
    if rotated_90:
        # Working-x = original-y after the (x,y)→(y,x) swap.
        xs = [pt[1] for pt in coords]
    else:
        xs = [pt[0] for pt in coords]
    return min(xs), max(xs)


def _generate_grid(
    plot: Plot,
    *,
    rotated_90: bool,
    min_col_w: float = 20.0,             # min sub-plot depth (perpendicular to road)
    max_col_w: float = 50.0,             # max sub-plot depth — drives cul-de-sac count
    max_row_depth: float = 50.0,         # max sub-plot front along road
) -> Tuple[List[Polygon], List[Polygon], int, int]:
    """Cul-de-sac road layout — perpendicular dead-end roads from DROGA.

    Pattern (working coords, DROGA on bottom):
      - Decide N_CDS (number of cul-de-sacs) so that strip width ≤ max_col_w
        but ≥ min_col_w. Strips are bays of width ``parent_w / N_CDS``.
      - Each cul-de-sac is a vertical road centred in its bay, extending from
        DROGA (y = 0) up to y = N_ROWS × row_d (it does NOT cross to the
        opposite boundary — Q-2026-05-08 owner spec).
      - Each cul-de-sac has 2 strips of sub-plots (left + right). Strip = N_ROWS
        sub-plots, each row_d × col_w.
      - row_d is the sub-plot front (along road), col_w is its depth.
      - N_ROWS grows until cell area ≤ MPZP.max_sub_plot_area_m2 and
        row_d ≤ max_row_depth, with row_d ≥ min_front_m.

    Every sub-plot fronts on its bay's cul-de-sac (Q3 hub-like contact);
    row 1 sub-plots additionally touch parent's DROGA on their bottom edge.
    """
    # REWRITE 2026-05-08 (B1: 2 fail → rewrite from scratch).
    #
    # Robust layout finder: for n_cds in 1..12 try
    #   - DROGA-constrained layout (cul-de-sacs span only DROGA range)
    #   - parent_w-constrained layout (cul-de-sacs span full bbox)
    # Pick the first n_cds where strip width col_w ∈ [min_col_w, max_col_w].
    # Always produces a non-empty layout — _absorb_leftover handles weird
    # plot shapes downstream. No more "0 sub-plots" empty returns.

    minx, miny, maxx, maxy = plot.geometry.bounds
    if rotated_90:
        minx, miny, maxx, maxy = miny, minx, maxy, maxx
    parent_w = maxx - minx
    parent_d = maxy - miny

    min_front = plot.mpzp.min_front_m
    road_w = plot.mpzp.min_road_width_m
    max_area = plot.mpzp.max_sub_plot_area_m2

    droga_xmin, droga_xmax = _droga_extent_in_working(plot, rotated_90)
    if droga_xmin is None:
        droga_xmin, droga_xmax = minx, maxx
    droga_w = max(0.0, droga_xmax - droga_xmin)

    raw_cells: List[Polygon] = []
    raw_roads: List[Polygon] = []

    # Layout finder.
    chosen_n_cds = None
    chosen_layout_w = parent_w
    chosen_origin = minx
    for n in range(1, 13):
        # Prefer DROGA-constrained when DROGA is wide enough to host n bays.
        if droga_w >= n * (2 * min_col_w + road_w):
            cw = (droga_w - n * road_w) / (2 * n)
            if min_col_w - 0.5 <= cw <= max_col_w + 0.5:
                chosen_n_cds = n
                chosen_layout_w = droga_w
                chosen_origin = droga_xmin
                break
        # Fall back to parent_w.
        cw = (parent_w - n * road_w) / (2 * n)
        if min_col_w - 0.5 <= cw <= max_col_w + 0.5:
            chosen_n_cds = n
            chosen_layout_w = parent_w
            chosen_origin = minx
            break

    if chosen_n_cds is None:
        # No bay count gives col_w in range — degrade to single cul-de-sac
        # using whichever layout width is bigger.
        chosen_n_cds = 1
        if droga_w >= 2 * min_col_w + road_w:
            chosen_layout_w = droga_w
            chosen_origin = droga_xmin
        else:
            chosen_layout_w = parent_w
            chosen_origin = minx

    n_cds = chosen_n_cds
    layout_w = chosen_layout_w
    layout_origin = chosen_origin
    col_w = max(min_col_w * 0.5, (layout_w - n_cds * road_w) / (2 * n_cds))

    # Pattern selection.
    if parent_d <= SHALLOW_PLOT_DEPTH + 0.01:
        # No internal road, single row. Tile parent's full width so absorption
        # has minimal work to do.
        cols = max(1, int(parent_w // min_front))
        cell_w = parent_w / cols
        for c in range(cols):
            x0 = minx + c * cell_w
            x1 = x0 + cell_w
            raw_cells.append(box(x0, miny, x1, maxy))
        n_rows, n_cols_total = 1, cols
    else:
        # Cul-de-sac pattern. Number of rows for max-area constraint.
        target_row_d = max(min_front, min(max_area / max(col_w, 1.0), max_row_depth))
        n_rows = max(1, round(parent_d / target_row_d))
        # Bump rows if cell area would still exceed max_area.
        while n_rows < 50 and (col_w * (parent_d / n_rows)) > max_area * 1.05:
            n_rows += 1
        row_d = parent_d / n_rows
        # Ensure row_d ≥ min_front; otherwise shrink rows.
        if row_d < min_front and n_rows > 1:
            n_rows = max(1, int(parent_d / min_front))
            row_d = parent_d / n_rows

        # Road extends from DROGA up to (n_rows-1)*row_d + 4.5m stub into
        # the last row — never reaches the back boundary.
        if n_rows == 1:
            road_ymax = miny + min(road_w, row_d)
        else:
            road_ymax = miny + (n_rows - 1) * row_d + min(road_w, row_d / 2)

        bay_w = layout_w / n_cds
        for cds_i in range(n_cds):
            bay_xmin = layout_origin + cds_i * bay_w
            bay_xmax = layout_origin + (cds_i + 1) * bay_w
            cx = (bay_xmin + bay_xmax) / 2
            road_xmin = cx - road_w / 2
            road_xmax = cx + road_w / 2
            raw_roads.append(box(road_xmin, miny, road_xmax, road_ymax))

            for r in range(n_rows):
                ry0 = miny + r * row_d
                ry1 = ry0 + row_d
                raw_cells.append(box(bay_xmin, ry0, road_xmin, ry1))
                raw_cells.append(box(road_xmax, ry0, bay_xmax, ry1))
        n_cols_total = 2 * n_cds

    if rotated_90:
        def _swap(p: Polygon) -> Polygon:
            return Polygon([(y, x) for x, y in p.exterior.coords])
        raw_cells = [_swap(p) for p in raw_cells]
        raw_roads = [_swap(p) for p in raw_roads]

    return raw_cells, raw_roads, n_rows, n_cols_total


def _clip_roads(plot: Plot, roads: List[Polygon]) -> List[Polygon]:
    """Clip road polygons to parent geometry (anti-bug #2)."""
    out: List[Polygon] = []
    for r in roads:
        c = r.intersection(plot.geometry)
        if c.is_empty:
            continue
        if isinstance(c, Polygon):
            out.append(c)
        else:
            for piece in c.geoms:
                if isinstance(piece, Polygon) and not piece.is_empty:
                    out.append(piece)
    return out


def _clip_and_evaluate(
    plot: Plot,
    raw_cells: List[Polygon],
    roads: List[Polygon],
    *,
    min_dim_factor: float = 0.85,
) -> Tuple[List[SubPlot], List[Polygon]]:
    """Clip each cell to parent, infer boundaries, compute per-sub-plot zone.

    A clipped cell is dropped to nieużytek (Q1.1(d) fallback) when:
      - clipped area < MPZP.min_sub_plot_area_m2, OR
      - clipped area > MPZP.max_sub_plot_area_m2, OR
      - shorter clipped dimension < min_front × min_dim_factor, OR
      - per-sub-plot buildable zone is infeasible.
    """
    builder = BuildableZoneBuilder()
    min_area = plot.mpzp.min_sub_plot_area_m2
    max_area = plot.mpzp.max_sub_plot_area_m2
    min_dim = plot.mpzp.min_front_m * min_dim_factor
    kept: List[SubPlot] = []
    dropped: List[Polygon] = []

    for raw in raw_cells:
        clipped = raw.intersection(plot.geometry)
        if clipped.is_empty:
            continue
        if not isinstance(clipped, Polygon):
            polys = list(clipped.geoms)
            largest = max(polys, key=lambda p: p.area)
            for p in polys:
                if p is not largest:
                    dropped.append(p)
            clipped = largest

        if clipped.area < min_area or clipped.area > max_area:
            dropped.append(clipped)
            continue

        cw = clipped.bounds[2] - clipped.bounds[0]
        ch = clipped.bounds[3] - clipped.bounds[1]
        if min(cw, ch) < min_dim:
            dropped.append(clipped)
            continue

        boundaries, droga_touch, internal_touch = _infer_boundaries(
            clipped, plot, roads
        )

        sub_plot_obj = Plot(
            number="sub",
            geometry=clipped,
            boundaries=boundaries,
            mpzp=plot.mpzp,
            housing_type=plot.housing_type,
        )
        try:
            zone = builder.compute(sub_plot_obj)
        except BuildableZoneInfeasible:
            dropped.append(clipped)
            continue

        kept.append(SubPlot(
            polygon=clipped,
            boundaries=boundaries,
            buildable_zone=zone,
            parent_droga_touch=droga_touch,
            internal_road_touch=internal_touch,
        ))

    return kept, dropped


def _filter_for_building_type(
    sub_plots: List[SubPlot],
    building_type: BuildingType,
) -> Tuple[List[SubPlot], List[SubPlot]]:
    """Q19 (2026-05-25): ALL building types accept any road access (parent
    DROGA OR internal road). Previous strict "TWIN/TERRACED requires parent
    DROGA only" was over-interpretation of Q3 — Q3 mandates only ORIENTATION
    (shorter side = front), not LOCATION. Multi-row developments with
    internal roads are standard PL deweloperka practice; the strict gate
    collapsed large plots to ≤4 monster sub-plots and made szeregowce in
    the second row impossible to design.

    Returns (kept, demoted) — demoted (no road access at all) go to nieużytek.
    """
    kept: List[SubPlot] = []
    demoted: List[SubPlot] = []
    for s in sub_plots:
        if s.parent_droga_touch > 0 or s.internal_road_touch > 0:
            kept.append(s)
        else:
            demoted.append(s)
    return kept, demoted


def _absorb_leftover_capped(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
    max_oversize_factor: float = 1.5,
) -> List[SubPlot]:
    """Absorb leftover into nearest sub-plot whose new area would NOT exceed
    max_sub_plot_area * factor. Avoids the bug where one sub-plot absorbs
    all leftover and becomes 50× max_area.
    """
    if not sub_plots:
        return sub_plots
    max_area = plot.mpzp.max_sub_plot_area_m2
    cap = max_area * max_oversize_factor

    builder = BuildableZoneBuilder()
    out = list(sub_plots)
    occupied = unary_union([s.polygon for s in out] + roads)
    leftover = plot.geometry.difference(occupied)
    if leftover.is_empty:
        return out

    pieces = [leftover] if isinstance(leftover, Polygon) else [
        g for g in getattr(leftover, "geoms", []) if isinstance(g, Polygon)
    ]
    pieces = [p for p in pieces if p.area > 0.01]
    pieces.sort(key=lambda p: -p.area)   # absorb largest first

    for piece in pieces:
        # Score candidates: prefer (1) longest shared boundary, (2) lowest
        # post-merge area (to avoid pushing one sub-plot past cap).
        scored = []
        for i, s in enumerate(out):
            try:
                shared = s.polygon.boundary.intersection(piece.boundary)
                shared_len = (shared.length if hasattr(shared, "length")
                              and not hasattr(shared, "geoms") else
                              sum(getattr(g, "length", 0.0)
                                  for g in getattr(shared, "geoms", [])))
            except Exception:
                shared_len = 0.0
            new_area = s.area + piece.area
            scored.append((shared_len, -new_area, i))

        scored.sort(reverse=True)
        chosen_idx = None
        for shared_len, _, i in scored:
            if shared_len <= 0.01:
                continue
            if out[i].area + piece.area <= cap:
                chosen_idx = i
                break
        if chosen_idx is None:
            # No candidate within cap — pick the smallest neighbour (least bad).
            for shared_len, neg_area, i in scored:
                if shared_len > 0.01:
                    chosen_idx = i
                    break
        if chosen_idx is None:
            continue

        merged = out[chosen_idx].polygon.union(piece)
        if not isinstance(merged, Polygon):
            merged = max(merged.geoms, key=lambda p: p.area)

        new_boundaries, droga_touch, road_touch = _infer_boundaries(merged, plot, roads)
        try:
            tmp_plot = Plot(
                number="merged", geometry=merged, boundaries=new_boundaries,
                mpzp=plot.mpzp, housing_type=plot.housing_type,
            )
            new_zone = builder.compute(tmp_plot)
        except BuildableZoneInfeasible:
            new_zone = out[chosen_idx].buildable_zone

        out[chosen_idx] = SubPlot(
            polygon=merged, boundaries=new_boundaries,
            buildable_zone=new_zone,
            parent_droga_touch=droga_touch,
            internal_road_touch=road_touch,
        )

    return out


def _absorb_leftover(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
) -> List[SubPlot]:
    """Owner spec 2026-05-08: NO nieużytek allowed. Every leftover sliver
    must be absorbed into the nearest sub-plot (longest shared edge, then
    closest centroid). After absorption, sub-plots may be non-rectangular
    (union of grid cell + leftover) but parent area is fully accounted for
    by sub-plots + roads.

    Re-infers boundaries and per-sub-plot buildable zone for each modified
    sub-plot (its setbacks may change after the merge).
    """
    if not sub_plots:
        return sub_plots

    occupied = unary_union([s.polygon for s in sub_plots] + roads)
    leftover = plot.geometry.difference(occupied)
    if leftover.is_empty:
        return sub_plots

    pieces: List[Polygon] = []
    if isinstance(leftover, Polygon):
        if leftover.area > 0.01:
            pieces.append(leftover)
    else:
        for g in getattr(leftover, "geoms", []):
            if isinstance(g, Polygon) and g.area > 0.01:
                pieces.append(g)

    if not pieces:
        return sub_plots

    builder = BuildableZoneBuilder()
    out = list(sub_plots)
    min_area = plot.mpzp.min_sub_plot_area_m2
    max_area = plot.mpzp.max_sub_plot_area_m2

    def merge_piece(target_idx: int, fragment: Polygon) -> None:
        merged = out[target_idx].polygon.union(fragment)
        if not isinstance(merged, Polygon):
            merged = max(merged.geoms, key=lambda p: p.area)

        new_boundaries, droga_touch, road_touch = _infer_boundaries(
            merged, plot, roads
        )
        try:
            tmp = Plot(
                number=f"sub_merged_{target_idx}",
                geometry=merged,
                boundaries=new_boundaries,
                mpzp=plot.mpzp,
                housing_type=plot.housing_type,
            )
            new_zone = builder.compute(tmp)
        except BuildableZoneInfeasible:
            new_zone = out[target_idx].buildable_zone

        out[target_idx] = SubPlot(
            polygon=merged,
            boundaries=new_boundaries,
            buildable_zone=new_zone,
            parent_droga_touch=droga_touch,
            internal_road_touch=road_touch,
        )

    def try_add_leftover_as_subplots(piece: Polygon) -> bool:
        if piece.area < min_area or piece.area < max_area * 1.05:
            return False
        _, droga_touch, road_touch = _infer_boundaries(piece, plot, roads)
        if droga_touch + road_touch <= 0.5:
            return False

        pb = piece.bounds
        split_along_x = (pb[2] - pb[0]) >= (pb[3] - pb[1])
        for n in range(max(2, math.ceil(piece.area / max_area)), 80):
            raw_parts: List[Polygon] = []
            if split_along_x:
                step = (pb[2] - pb[0]) / n
                cutters = [
                    box(pb[0] + i * step, pb[1] - 1.0,
                        pb[0] + (i + 1) * step, pb[3] + 1.0)
                    for i in range(n)
                ]
            else:
                step = (pb[3] - pb[1]) / n
                cutters = [
                    box(pb[0] - 1.0, pb[1] + i * step,
                        pb[2] + 1.0, pb[1] + (i + 1) * step)
                    for i in range(n)
                ]

            for cutter in cutters:
                fragment = piece.intersection(cutter)
                if isinstance(fragment, Polygon) and fragment.area > 0.01:
                    raw_parts.append(fragment)
                elif hasattr(fragment, "geoms"):
                    raw_parts.extend([
                        g for g in fragment.geoms
                        if isinstance(g, Polygon) and g.area > 0.01
                    ])
            if not raw_parts:
                continue
            raw_parts.sort(key=lambda p: p.centroid.x if split_along_x else p.centroid.y)

            groups: List[Polygon] = []
            acc: Optional[Polygon] = None
            valid_grouping = True
            for part in raw_parts:
                acc = part if acc is None else acc.union(part)
                if not isinstance(acc, Polygon):
                    acc = max(acc.geoms, key=lambda p: p.area)
                if acc.area > max_area * 1.05:
                    valid_grouping = False
                    break
                if acc.area >= min_area:
                    groups.append(acc)
                    acc = None
            if not valid_grouping:
                continue
            if acc is not None and acc.area > 0.01:
                if groups and groups[-1].area + acc.area <= max_area * 1.05:
                    merged_last = groups[-1].union(acc)
                    groups[-1] = (
                        merged_last if isinstance(merged_last, Polygon)
                        else max(merged_last.geoms, key=lambda p: p.area)
                    )
                else:
                    continue

            new_subplots: List[SubPlot] = []
            for group in groups:
                if group.area < min_area or group.area > max_area * 1.05:
                    valid_grouping = False
                    break
                boundaries, droga_touch, road_touch = _infer_boundaries(group, plot, roads)
                if droga_touch + road_touch <= 0.5:
                    valid_grouping = False
                    break
                try:
                    tmp = Plot(
                        number="leftover_split",
                        geometry=group,
                        boundaries=boundaries,
                        mpzp=plot.mpzp,
                        housing_type=plot.housing_type,
                    )
                    zone = builder.compute(tmp)
                except BuildableZoneInfeasible:
                    valid_grouping = False
                    break
                new_subplots.append(SubPlot(
                    polygon=group,
                    boundaries=boundaries,
                    buildable_zone=zone,
                    parent_droga_touch=droga_touch,
                    internal_road_touch=road_touch,
                ))
            if valid_grouping and new_subplots:
                out.extend(new_subplots)
                return True
        return False

    for piece in pieces:
        if try_add_leftover_as_subplots(piece):
            continue

        shared_candidates = []
        for i, s in enumerate(out):
            try:
                shared = s.polygon.boundary.intersection(piece.boundary)
                shared_len = shared.length if hasattr(shared, "length") else (
                    sum(getattr(g, "length", 0.0) for g in getattr(shared, "geoms", []))
                )
            except Exception:
                shared_len = 0.0
            sb = s.polygon.bounds
            pb = piece.bounds
            x_overlap = max(0.0, min(sb[2], pb[2]) - max(sb[0], pb[0]))
            near_parallel_row = (
                x_overlap > 0.5
                and s.polygon.distance(piece) <= plot.mpzp.min_road_width_m + 0.1
            )
            if shared_len > 0.01 or near_parallel_row:
                shared_candidates.append((s.polygon.bounds[0], i))

        if len(shared_candidates) > 1 and piece.area >= min_area:
            unassigned = piece
            pb = piece.bounds
            split_by_y = (pb[3] - pb[1]) > (pb[2] - pb[0]) * 1.25
            if split_by_y:
                shared_candidates.sort(key=lambda item: out[item[1]].polygon.bounds[1])
            else:
                shared_candidates.sort()

            for _, target_idx in shared_candidates:
                sb = out[target_idx].polygon.bounds
                if split_by_y:
                    strip = box(
                        pb[0] - 1.0, sb[1] - 0.01,
                        pb[2] + 1.0, sb[3] + 0.01,
                    )
                else:
                    strip = box(
                        sb[0] - 0.01, pb[1] - 1.0,
                        sb[2] + 0.01, pb[3] + 1.0,
                    )
                fragment = unassigned.intersection(strip)
                if isinstance(fragment, Polygon) and fragment.area > 0.01:
                    merge_piece(target_idx, fragment)
                    unassigned = unassigned.difference(fragment)
                elif hasattr(fragment, "geoms"):
                    for g in list(fragment.geoms):
                        if isinstance(g, Polygon) and g.area > 0.01:
                            merge_piece(target_idx, g)
                    unassigned = unassigned.difference(fragment)

            split_leftovers = []
            if isinstance(unassigned, Polygon) and unassigned.area > 0.01:
                split_leftovers = [unassigned]
            elif hasattr(unassigned, "geoms"):
                split_leftovers = [
                    g for g in unassigned.geoms
                    if isinstance(g, Polygon) and g.area > 0.01
                ]
            if not split_leftovers:
                continue
            # Tiny leftovers between vertical strips are handled by fallback.
            piece = max(split_leftovers, key=lambda p: p.area)

        # Pick best target: longest shared boundary, then closest centroid.
        scored = []
        for i, s in enumerate(out):
            try:
                shared = s.polygon.boundary.intersection(piece.boundary)
                shared_len = shared.length if hasattr(shared, "length") else (
                    sum(getattr(g, "length", 0.0) for g in getattr(shared, "geoms", []))
                )
            except Exception:
                shared_len = 0.0
            try:
                centroid_d = s.polygon.centroid.distance(piece.centroid)
            except Exception:
                centroid_d = float("inf")
            scored.append((-shared_len, centroid_d, i))
        scored.sort()
        target_idx = scored[0][2]
        merge_piece(target_idx, piece)

    return out


def _assemble_nieuzytek(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
) -> Polygon:
    """Compute residual nieużytek (should be empty after absorption)."""
    occupied = unary_union([s.polygon for s in sub_plots] + roads) \
        if (sub_plots or roads) else None
    if occupied is None:
        return plot.geometry
    return plot.geometry.difference(occupied)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _validate_single_family(plot: Plot) -> None:
    """Q12: Mode B is single-family only."""
    if plot.housing_type != HousingType.JEDNORODZINNA:
        raise ValueError(
            "Mode B (subdivision) is single-family only — set "
            "plot.housing_type = HousingType.JEDNORODZINNA. "
            "Multi-family plots use Mode A (whole-plot)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Q21 (2026-05-26) — shared walls for TWIN/TERRACED
# ─────────────────────────────────────────────────────────────────────────────

# Minimum overlap (m) when matching a SubPlot boundary segment against the
# shared-edge LineString returned by topology.find_adjacent_pairs.
_SHARED_EDGE_MIN_OVERLAP = 0.5

# Adjacency thresholds — mirror building_proposer's pair/chain detection so
# building placement and setback overrides agree on what "paired" means.
_TWIN_MIN_SHARED_EDGE = 6.0
_TERRACED_MIN_SHARED_EDGE = 4.0


def _segment_overlap_length(segment_geom, ribbon) -> float:
    """Length of the geometry returned by `segment_geom.intersection(ribbon)`,
    handling both LineString and (Multi)Geometry results."""
    try:
        overlap = segment_geom.intersection(ribbon)
    except Exception:
        return 0.0
    if overlap.is_empty:
        return 0.0
    if hasattr(overlap, "length") and not hasattr(overlap, "geoms"):
        return overlap.length
    if hasattr(overlap, "geoms"):
        return sum(getattr(g, "length", 0.0) for g in overlap.geoms)
    return 0.0


def _mark_segment_on_edge(sub: SubPlot, shared_edge: LineString) -> bool:
    """Set `is_shared_wall=True` on whichever PlotBoundary segment of `sub`
    overlaps `shared_edge` the most (must overlap at least the minimum).
    Returns True if a segment was marked."""
    ribbon = shared_edge.buffer(0.01, cap_style=2)
    best_bnd: Optional[PlotBoundary] = None
    best_overlap = _SHARED_EDGE_MIN_OVERLAP
    for bnd in sub.boundaries:
        length = _segment_overlap_length(bnd.geometry, ribbon)
        if length > best_overlap:
            best_overlap = length
            best_bnd = bnd
    if best_bnd is not None:
        best_bnd.is_shared_wall = True
        return True
    return False


def _mark_shared_walls(
    sub_plots: List[SubPlot],
    building_type: BuildingType,
    plot: Plot,
) -> None:
    """Mark the boundary segment shared with a pair/chain neighbour and rebuild
    each affected sub-plot's buildable_zone so the 0m side setback applies.

    DETACHED → no-op.
    TWIN → first-best pair per sub-plot (one shared wall per sub-plot).
    TERRACED → every neighbour pair above the chain threshold (internal
    sub-plots get 2 marks, edge sub-plots get 1).

    Must run AFTER `_absorb_leftover` / `_split_oversized_subplots` since those
    re-infer boundaries (they would overwrite the flag with a fresh
    `is_shared_wall=False`)."""
    if building_type == BuildingType.DETACHED:
        return

    from core.subdivision_topology import find_adjacent_pairs

    affected: set = set()

    if building_type == BuildingType.TWIN:
        pairs = find_adjacent_pairs(sub_plots, min_shared_edge=_TWIN_MIN_SHARED_EDGE)
        paired: set = set()
        for a, b, shared_edge in pairs:
            if id(a) in paired or id(b) in paired:
                continue
            if _mark_segment_on_edge(a, shared_edge):
                affected.add(id(a))
            if _mark_segment_on_edge(b, shared_edge):
                affected.add(id(b))
            paired.add(id(a))
            paired.add(id(b))
    else:  # TERRACED
        pairs = find_adjacent_pairs(
            sub_plots, min_shared_edge=_TERRACED_MIN_SHARED_EDGE
        )
        for a, b, shared_edge in pairs:
            if _mark_segment_on_edge(a, shared_edge):
                affected.add(id(a))
            if _mark_segment_on_edge(b, shared_edge):
                affected.add(id(b))

    if not affected:
        return

    builder = BuildableZoneBuilder()
    for sub in sub_plots:
        if id(sub) not in affected:
            continue
        tmp = Plot(
            number="q21_recompute",
            geometry=sub.polygon,
            boundaries=sub.boundaries,
            mpzp=plot.mpzp,
            housing_type=plot.housing_type,
        )
        try:
            new_zone = builder.compute(tmp)
        except BuildableZoneInfeasible:
            continue
        if new_zone is not None and not new_zone.is_empty:
            sub.buildable_zone = new_zone


def _is_buildable_shape(
    cell: Polygon,
    min_area: float,
    min_rectangularity: float = 0.65,
    min_short_dim: float = 12.0,
) -> bool:
    """Cell shape passes the "you can actually build a house here" test.

    Three criteria:
      1. area ≥ min_area (MPZP requirement, hard).
      2. rectangularity = cell.area / minimum_rotated_rectangle.area
         ≥ 0.65 — rejects L-shaped, pentagon, sliver geometries that
         look like cells but don't fit a building (owner spec 2026-05-08:
         "w takim ksztalcie ze sie tam nic nie da wybudowac").
      3. shorter side of OBB ≥ min_short_dim — rejects long-thin slivers.
    """
    if cell.area < min_area:
        return False
    try:
        obb = cell.minimum_rotated_rectangle
        if obb.is_empty or obb.area < 1e-6:
            return False
        rect = cell.area / obb.area
        if rect < min_rectangularity:
            return False
        # OBB short side
        coords = list(obb.exterior.coords)[:-1]
        dims = []
        for i in range(4):
            a, b = coords[i], coords[(i + 1) % 4]
            dims.append(math.hypot(b[0] - a[0], b[1] - a[1]))
        short = min(dims) if dims else 0.0
        if short < min_short_dim:
            return False
    except Exception:
        return False
    return True


def _build_subplots_from_cells(
    plot: Plot,
    cells: List[Polygon],
    roads: List[Polygon],
) -> List[SubPlot]:
    """Wrap raw cell polygons into SubPlot objects (boundaries + zone).

    Unlike `_clip_and_evaluate` this does NOT reject by area or dim — it
    trusts that callers (katana → _merge_small_polys) already produced
    cells in the right size band. Cells with infeasible buildable zone
    are still returned with `buildable_zone=None`; downstream filtering
    (Q3 building-type) decides what to do.
    """
    builder = BuildableZoneBuilder()
    out: List[SubPlot] = []
    for c in cells:
        if not isinstance(c, Polygon) or c.area < 1.0:
            continue
        boundaries, droga_touch, internal_touch = _infer_boundaries(c, plot, roads)
        sub_obj = Plot(
            number="sub", geometry=c, boundaries=boundaries,
            mpzp=plot.mpzp, housing_type=plot.housing_type,
        )
        try:
            zone = builder.compute(sub_obj)
        except BuildableZoneInfeasible:
            zone = None
        out.append(SubPlot(
            polygon=c, boundaries=boundaries,
            buildable_zone=zone if zone is not None and not zone.is_empty else None,
            parent_droga_touch=droga_touch,
            internal_road_touch=internal_touch,
        ))
    return out


def _min_buildable_zone_area(plot: Plot) -> float:
    """Minimum usable buildable zone for a kept sub-plot.

    A non-empty 20-40m2 sliver is mathematically a polygon, but it is not a
    realistic detached-house buildable zone. Keep this product rule modest:
    enough to reject pathological edge plots without forcing a building size.
    """
    return max(60.0, plot.mpzp.min_sub_plot_area_m2 * 0.20)


def _min_short_dim(mpzp, *, cap: float = 12.0, ratio: float = 0.67) -> float:
    """Q20 (2026-05-25): scale `_is_buildable_shape` short-dim guard with
    `mpzp.min_front_m` (which is already type-aware after
    `_with_effective_mpzp` at the public entry).

    DETACHED (front 18 m): `min(12, 18×0.67=12.06) = 12 m`.
    TWIN (front 9 m after Q20): `min(12, 9×0.67=6.03) = 6 m`.
    TERRACED (front 6 m after Q20): `min(12, 6×0.67=4.02) = 4 m`.

    Without this scaling, the hardcoded 12 m guard rejected every
    TERRACED segment (6 m wide) and most TWIN segments (9 m wide), so
    TERRACED returned 0 sub-plots and TWIN had a leftover-absorption
    explosion. `_split_oversized_subplots` uses a looser variant
    (`cap=8.0, ratio=0.45`) as a last-ditch attempt.
    """
    return min(cap, mpzp.min_front_m * ratio)


def _wrap_valid_subplot(
    plot: Plot,
    polygon: Polygon,
    roads: List[Polygon],
    building_type: BuildingType,
    builder: BuildableZoneBuilder,
) -> Optional[SubPlot]:
    boundaries, droga_touch, internal_touch = _infer_boundaries(
        polygon, plot, roads
    )
    # Q19 (2026-05-25): all building types accept any road access (see
    # _filter_for_building_type docstring for rationale).
    if droga_touch + internal_touch <= 0.5:
        return None

    tmp = Plot(
        number="split_oversized",
        geometry=polygon,
        boundaries=boundaries,
        mpzp=plot.mpzp,
        housing_type=plot.housing_type,
    )
    try:
        zone = builder.compute(tmp)
    except BuildableZoneInfeasible:
        return None
    if zone is None or zone.is_empty:
        return None
    if zone.area < _min_buildable_zone_area(plot):
        return None
    return SubPlot(
        polygon=polygon,
        boundaries=boundaries,
        buildable_zone=zone,
        parent_droga_touch=droga_touch,
        internal_road_touch=internal_touch,
    )


def _split_oversized_subplots(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
    building_type: BuildingType,
) -> List[SubPlot]:
    """Split post-absorption monster plots back into valid sub-plots.

    Absorption is correct for tiny leftovers, but with tight MPZP bounds
    (e.g. 600-800m2) it can glue an entire edge band into one huge parcel.
    This function re-runs a local strip split inside each oversized parcel
    and accepts it only if every child remains buildable and road-accessible.
    """
    min_area = plot.mpzp.min_sub_plot_area_m2
    cap_area = plot.mpzp.max_sub_plot_area_m2 * 1.05
    builder = BuildableZoneBuilder()
    out: List[SubPlot] = []

    for sub in sub_plots:
        zone_area = sub.buildable_zone.area if sub.has_buildable_zone else 0.0
        if sub.area <= cap_area and zone_area >= _min_buildable_zone_area(plot):
            out.append(sub)
            continue

        split = _split_polygon_to_valid_subplots(
            plot, sub.polygon, roads, building_type, builder,
            min_area=min_area, cap_area=cap_area,
        )
        tight_area_bounds = (
            plot.mpzp.min_sub_plot_area_m2 >= 500
            and plot.mpzp.max_sub_plot_area_m2 <= 900
        )
        if not split and tight_area_bounds:
            split = _service_oversized_subplot_with_road(
                plot, sub.polygon, roads, building_type, builder,
                min_area=min_area, cap_area=cap_area,
            )
        if split:
            out.extend(split)
        else:
            out.append(sub)
    return out


def _split_polygon_to_valid_subplots(
    plot: Plot,
    polygon: Polygon,
    roads: List[Polygon],
    building_type: BuildingType,
    builder: BuildableZoneBuilder,
    *,
    min_area: float,
    cap_area: float,
) -> List[SubPlot]:
    bounds = polygon.bounds
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    if width <= 0.1 or height <= 0.1:
        return []

    min_n = max(2, math.ceil(polygon.area / cap_area))
    max_n = min(96, max(min_n + 1, math.ceil(polygon.area / min_area) + 8))
    axis_order = ["x", "y"] if width >= height else ["y", "x"]

    for axis in axis_order:
        for n in range(min_n, max_n + 1):
            groups = _split_polygon_into_area_groups(
                polygon, axis, n, min_area, cap_area
            )
            if not groups:
                continue
            try:
                coverage = unary_union(groups).symmetric_difference(polygon).area
            except Exception:
                coverage = float("inf")
            if coverage > 0.5:
                continue

            wrapped: List[SubPlot] = []
            valid = True
            for group in groups:
                if group.area < min_area - 0.1 or group.area > cap_area:
                    valid = False
                    break
                if not _is_buildable_shape(
                    group,
                    min_area * 0.50,
                    min_rectangularity=0.45,
                    min_short_dim=_min_short_dim(plot.mpzp, cap=8.0, ratio=0.45),
                ):
                    valid = False
                    break
                sub = _wrap_valid_subplot(
                    plot, group, roads, building_type, builder
                )
                if sub is None:
                    valid = False
                    break
                wrapped.append(sub)
            if valid and wrapped:
                return wrapped
    return []


def _service_oversized_subplot_with_road(
    plot: Plot,
    polygon: Polygon,
    roads: List[Polygon],
    building_type: BuildingType,
    builder: BuildableZoneBuilder,
    *,
    min_area: float,
    cap_area: float,
    depth: int = 0,
) -> List[SubPlot]:
    """Add a local access spur inside an oversized edge plot, then split it.

    This is a last-resort repair for long side tails. If a tail cannot be
    subdivided while preserving road access, the real-world answer is a small
    spur connected to the existing road tree, not one 3000m2 parcel.
    """
    road_w = plot.mpzp.min_road_width_m
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    if width <= road_w * 2 or height <= road_w * 2:
        return []

    access_parts = list(roads)
    road_boundary = plot.road_boundary()
    if road_boundary is not None:
        access_parts.append(road_boundary.geometry.buffer(0.05, cap_style=2))
    access_geom = unary_union(access_parts) if access_parts else None
    clearance = max(road_w * 1.1, plot.mpzp.min_front_m * 0.25)

    road_boxes = []
    if height >= width:
        left_probe = LineString([(minx, miny), (minx, maxy)])
        right_probe = LineString([(maxx, miny), (maxx, maxy)])
        left_d = left_probe.distance(access_geom) if access_geom is not None else 0.0
        right_d = right_probe.distance(access_geom) if access_geom is not None else 0.0
        side_boxes = [
            (left_d, box(minx, miny, minx + road_w, maxy)),
            (right_d, box(maxx - road_w, miny, maxx, maxy)),
        ]
        road_boxes.extend([b for _, b in sorted(side_boxes, key=lambda item: item[0])])

        top_probe = LineString([(minx, maxy), (maxx, maxy)])
        bottom_probe = LineString([(minx, miny), (maxx, miny)])
        top_d = top_probe.distance(access_geom) if access_geom is not None else 0.0
        bottom_d = bottom_probe.distance(access_geom) if access_geom is not None else 0.0
        ratios = [0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75]
        for ratio in ratios:
            x = minx + width * ratio
            if top_d <= bottom_d:
                road_boxes.append(box(x - road_w / 2, miny + clearance,
                                      x + road_w / 2, maxy))
            else:
                road_boxes.append(box(x - road_w / 2, miny,
                                      x + road_w / 2, maxy - clearance))
    else:
        top_probe = LineString([(minx, maxy), (maxx, maxy)])
        bottom_probe = LineString([(minx, miny), (maxx, miny)])
        top_d = top_probe.distance(access_geom) if access_geom is not None else 0.0
        bottom_d = bottom_probe.distance(access_geom) if access_geom is not None else 0.0
        side_boxes = [
            (bottom_d, box(minx, miny, maxx, miny + road_w)),
            (top_d, box(minx, maxy - road_w, maxx, maxy)),
        ]
        road_boxes.extend([b for _, b in sorted(side_boxes, key=lambda item: item[0])])

        left_probe = LineString([(minx, miny), (minx, maxy)])
        right_probe = LineString([(maxx, miny), (maxx, maxy)])
        left_d = left_probe.distance(access_geom) if access_geom is not None else 0.0
        right_d = right_probe.distance(access_geom) if access_geom is not None else 0.0
        ratios = [0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75]
        for ratio in ratios:
            y = miny + height * ratio
            if left_d <= right_d:
                road_boxes.append(box(minx, y - road_w / 2,
                                      maxx - clearance, y + road_w / 2))
            else:
                road_boxes.append(box(minx + clearance, y - road_w / 2,
                                      maxx, y + road_w / 2))

    for road_box in road_boxes:
        spur = road_box.intersection(polygon)
        if spur.is_empty or spur.area < road_w * road_w:
            continue
        if not isinstance(spur, Polygon):
            spur = max(
                [g for g in spur.geoms if isinstance(g, Polygon)],
                key=lambda g: g.area,
                default=None,
            )
        if spur is None or spur.is_empty:
            continue

        trial_roads = roads + [spur]
        land = polygon.difference(spur)
        pieces = [land] if isinstance(land, Polygon) else [
            g for g in getattr(land, "geoms", [])
            if isinstance(g, Polygon) and g.area > 1.0
        ]
        if not pieces:
            continue

        wrapped: List[SubPlot] = []
        valid = True
        for piece in pieces:
            if piece.area < min_area:
                valid = False
                break
            if piece.area <= cap_area:
                sub = _wrap_valid_subplot(
                    plot, piece, trial_roads, building_type, builder
                )
                if sub is None:
                    valid = False
                    break
                wrapped.append(sub)
                continue

            split = _split_polygon_to_valid_subplots(
                plot, piece, trial_roads, building_type, builder,
                min_area=min_area, cap_area=cap_area,
            )
            if not split and depth < 2:
                split = _service_oversized_subplot_with_road(
                    plot, piece, trial_roads, building_type, builder,
                    min_area=min_area, cap_area=cap_area, depth=depth + 1,
                )
            if not split:
                valid = False
                break
            wrapped.extend(split)
        if not valid:
            continue

        try:
            covered = unary_union([s.polygon for s in wrapped] + trial_roads[len(roads):])
            if covered.symmetric_difference(polygon).area > 0.5:
                continue
        except Exception:
            continue

        roads.extend(trial_roads[len(roads):])
        return wrapped
    return []


def _split_polygon_into_area_groups(
    polygon: Polygon,
    axis: str,
    n: int,
    min_area: float,
    cap_area: float,
) -> List[Polygon]:
    bounds = polygon.bounds
    minx, miny, maxx, maxy = bounds
    raw_parts: List[Polygon] = []

    if axis == "x":
        step = (maxx - minx) / n
        cutters = [
            box(minx + i * step, miny - 1.0,
                minx + (i + 1) * step, maxy + 1.0)
            for i in range(n)
        ]
        sort_key = lambda p: p.centroid.x
    else:
        step = (maxy - miny) / n
        cutters = [
            box(minx - 1.0, miny + i * step,
                maxx + 1.0, miny + (i + 1) * step)
            for i in range(n)
        ]
        sort_key = lambda p: p.centroid.y

    for cutter in cutters:
        fragment = polygon.intersection(cutter)
        if isinstance(fragment, Polygon) and fragment.area > 0.01:
            raw_parts.append(fragment)
        elif hasattr(fragment, "geoms"):
            raw_parts.extend([
                g for g in fragment.geoms
                if isinstance(g, Polygon) and g.area > 0.01
            ])

    if not raw_parts:
        return []
    raw_parts.sort(key=sort_key)

    groups: List[Polygon] = []
    acc: Optional[Polygon] = None
    for part in raw_parts:
        acc = part if acc is None else acc.union(part)
        if not isinstance(acc, Polygon):
            acc = max(acc.geoms, key=lambda p: p.area)
        if acc.area > cap_area:
            return []
        if acc.area >= min_area:
            groups.append(acc)
            acc = None

    if acc is not None and acc.area > 0.01:
        if groups and groups[-1].area + acc.area <= cap_area:
            merged = groups[-1].union(acc)
            groups[-1] = (
                merged if isinstance(merged, Polygon)
                else max(merged.geoms, key=lambda p: p.area)
            )
        else:
            return []

    return groups


def _subdivide_single(
    plot: Plot,
    *,
    rotated_90: bool = False,                     # legacy, unused (katana picks orientation)
    building_type: BuildingType = BuildingType.DETACHED,
    road_settings: Optional[RoadTreeSettings] = None,
) -> SubdivisionResult:
    """Subdivide a single-family plot into N sub-plots via katana bisection.

    Pipeline:
      1. katana cuts plot into cells, max-bbox-dim ≤ √max_area, so every
         cell.area ≤ max_area by construction.
      2. _merge_small_polys merges any cell < min_area into its longest-
         shared-edge neighbour. Coverage stays 100% — no leftover.
      3. _build_subplots_from_cells wraps cells into SubPlots with boundary
         classification (DROGA / SASIAD_*) and per-cell buildable zone.
      4. Q19 filter — any road access (parent DROGA OR internal) kept.

    No `_absorb_leftover` step — katana cells already tile the parent.
    The earlier rejection-+-absorption pipeline blew up one sub-plot to
    8817 m² when min/max range was tight (AC test 2026-05-08).
    """
    _validate_single_family(plot)

    raw_polys, raw_roads = generate_road_tree_layout(plot, road_settings)
    roads = _clip_roads(plot, raw_roads)

    # Clip katana cells to parent geometry (defensive — _generate_obb_layout
    # already does this, but handle edge cases).
    clipped_cells: List[Polygon] = []
    for c in raw_polys:
        c2 = c.intersection(plot.geometry)
        if c2.is_empty:
            continue
        if isinstance(c2, Polygon):
            if c2.area > 1.0:
                clipped_cells.append(c2)
        elif hasattr(c2, "geoms"):
            for g in c2.geoms:
                if isinstance(g, Polygon) and g.area > 1.0:
                    clipped_cells.append(g)

    # HARD filters per owner spec 2026-05-08:
    #   - drop cells below min_area (no merging — earlier merge produced
    #     "weird shapes" by gluing slivers to neighbours)
    #   - drop non-rectangular shapes (L, pentagon) where buildings won't fit
    # Filtered fragments become nieużytek — accepted trade-off for shape
    # quality. Owner: "powydzielal dzialki za male ponizej minimum, no rany
    # boskie", "w takim ksztalcie ze sie tam nic nie da wybudowac".
    min_area = plot.mpzp.min_sub_plot_area_m2
    short_dim = _min_short_dim(plot.mpzp)
    viable_cells = [
        c for c in clipped_cells
        if _is_buildable_shape(c, min_area, min_short_dim=short_dim)
    ]

    subs = _build_subplots_from_cells(plot, viable_cells, roads)
    # Drop cells where buildable zone is infeasible (setbacks leave nothing).
    subs = [s for s in subs if s.has_buildable_zone]
    kept, _demoted = _filter_for_building_type(subs, building_type)
    for _ in range(4):
        before_leftover = _assemble_nieuzytek(plot, kept, roads).area
        if before_leftover < 0.5:
            break
        kept = _absorb_leftover(plot, kept, roads)
        kept = _split_oversized_subplots(plot, kept, roads, building_type)
        after_leftover = _assemble_nieuzytek(plot, kept, roads).area
        if abs(after_leftover - before_leftover) < 0.01:
            break
    kept = _split_oversized_subplots(plot, kept, roads, building_type)

    # Q21 (2026-05-26): TWIN/TERRACED sub-plots share a wall with their
    # pair/chain neighbour. Mark those boundary segments so the side setback
    # drops to 0 there (otherwise a 9m TWIN front gets 6m of setback and the
    # buildable zone shrinks to 3m — no building fits).
    _mark_shared_walls(kept, building_type, plot)

    nieuzytek = _assemble_nieuzytek(plot, kept, roads)

    return SubdivisionResult(
        parent=plot,
        sub_plots=kept,
        roads=roads,
        nieuzytek=nieuzytek,
        orientation_name=road_settings.name if road_settings else "road_tree_balanced",
        rows=1 if kept else 0,                     # katana has no row/col grid;
        cols=max(1, len(kept)) if kept else 0,     # report sub-plot count instead
    )


def subdivide(
    plot: Plot,
    *,
    rotated_90: bool = False,                     # legacy, kept for public API
    building_type: BuildingType = BuildingType.DETACHED,
) -> SubdivisionResult:
    """Return the best scored subdivision variant for the existing API."""
    _validate_single_family(plot)
    # Q20: scale MPZP front/area for TWIN/TERRACED so 1 sub-plot = 1 segment.
    plot = _with_effective_mpzp(plot, building_type)
    from core.plot_variant_generator import generate_subdivision_variants

    variants = generate_subdivision_variants(
        plot,
        building_type=building_type,
        max_variants=1,
    )
    if variants:
        return variants[0]
    return _subdivide_single(
        plot,
        rotated_90=rotated_90,
        building_type=building_type,
    )


def subdivide_with_orientation_search(
    plot: Plot,
    *,
    building_type: BuildingType = BuildingType.DETACHED,
) -> SubdivisionResult:
    """OBB picks orientation automatically — no orientation search needed."""
    return subdivide(plot, building_type=building_type)
