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
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

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

        # Session 14 (2026-05-29): a road-less band ≥ min_area must NOT be
        # glued into a road-accessible neighbour — that is exactly how the
        # notch monster formed (the band inherits the neighbour's road touch
        # and becomes one giant road-accessible parcel that nothing can later
        # undo). Keep it as a standalone road-less sub-plot so the terminal
        # post-pass (_resolve_oversized_parcels) can rescue it with a legal
        # access spur or demote it to nieużytek (Q16(a)/Q1.1(d)). Tiny road-less
        # slivers (< min_area) still fall through to the merge below.
        band_bnd, band_dt, band_rt = _infer_boundaries(piece, plot, roads)
        if band_dt + band_rt <= 0.5 and piece.area >= min_area:
            try:
                tmp_band = Plot(
                    number="roadless_band",
                    geometry=piece,
                    boundaries=band_bnd,
                    mpzp=plot.mpzp,
                    housing_type=plot.housing_type,
                )
                band_zone = builder.compute(tmp_band)
            except BuildableZoneInfeasible:
                band_zone = None
            out.append(SubPlot(
                polygon=piece,
                boundaries=band_bnd,
                buildable_zone=band_zone,
                parent_droga_touch=band_dt,
                internal_road_touch=band_rt,
            ))
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


# ─────────────────────────────────────────────────────────────────────────────
# Oversized / road-less parcel resolution (focused rewrite, Session 14
# 2026-05-29). Replaces the brittle in-loop "_service_oversized..." escape for
# the FINAL pass. Runs ONCE after the absorb/split loop has converged, so it
# cannot oscillate with _absorb_leftover.
#
# The monster bug: when a notch cuts a band off from the road tree, those cells
# are dropped by the road-access filter, become leftover, and _absorb_leftover's
# unconditional scored-merge glues the whole road-less band into one giant
# sub-plot. This pass fixes that: road-less / oversized sub-plots are split with
# an access spur where a *legal* one exists (owner rescue decision 2026-05-29),
# and the genuinely boxed-in remainder is demoted to nieużytek (Q16(a)/Q1.1(d)).
# ─────────────────────────────────────────────────────────────────────────────

def _spur_is_legal_access(
    spur: Polygon,
    access_geom,
    plot: Plot,
    *,
    tol: float,
) -> bool:
    """A rescue spur is legal iff it (a) connects to the existing road network
    or parent DROGA and (b) does NOT dead-end on a non-DROGA parent boundary
    beyond `tol` (owner urban rule 2026-05-10, tol = min_road_width*0.5).
    """
    if access_geom is None or spur.is_empty:
        return False
    if spur.distance(access_geom) > 0.1:
        return False
    non_droga_touch = sum(
        _line_overlap(spur.boundary, b.geometry)
        for b in plot.boundaries
        if b.boundary_type != BoundaryType.DROGA
    )
    return non_droga_touch <= tol


def _rescue_or_demote(
    plot: Plot,
    polygon: Polygon,
    roads: List[Polygon],
    building_type: BuildingType,
    builder: BuildableZoneBuilder,
    *,
    min_area: float,
    cap_area: float,
) -> Tuple[List[SubPlot], Optional[Polygon]]:
    """Carve a legal access spur into a road-less/oversized band and split it
    into road-accessible children (partial-accept: keep the legal children,
    let the boxed-in remainder fall through to nieużytek).

    Returns (children, spur). children == [] and spur is None means nothing
    could be rescued → the caller demotes the whole band to nieużytek.
    """
    road_w = plot.mpzp.min_road_width_m
    tol = road_w * 0.5
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    if width <= road_w or height <= road_w:
        return [], None

    access_parts = list(roads)
    rb = plot.road_boundary()
    if rb is not None:
        access_parts.append(rb.geometry.buffer(0.05, cap_style=2))
    access_geom = unary_union(access_parts) if access_parts else None
    if access_geom is None:
        return [], None

    margin = tol + 0.5  # keep spur ends this far short of a non-road boundary

    # Which end of each axis is nearest the road network — trim the FAR end so
    # the spur cannot dead-end on the opposite (non-road) boundary.
    left_d = LineString([(minx, miny), (minx, maxy)]).distance(access_geom)
    right_d = LineString([(maxx, miny), (maxx, maxy)]).distance(access_geom)
    bottom_d = LineString([(minx, miny), (maxx, miny)]).distance(access_geom)
    top_d = LineString([(minx, maxy), (maxx, maxy)]).distance(access_geom)

    ratios = [0.5, 0.4, 0.6, 0.33, 0.67, 0.25, 0.75]
    candidate_boxes: List[Polygon] = []
    for r in ratios:                                    # horizontal spurs
        y = miny + height * r
        if left_d <= right_d:
            candidate_boxes.append(box(minx, y - road_w / 2, maxx - margin, y + road_w / 2))
        else:
            candidate_boxes.append(box(minx + margin, y - road_w / 2, maxx, y + road_w / 2))
    for r in ratios:                                    # vertical spurs
        x = minx + width * r
        if bottom_d <= top_d:
            candidate_boxes.append(box(x - road_w / 2, miny, x + road_w / 2, maxy - margin))
        else:
            candidate_boxes.append(box(x - road_w / 2, miny + margin, x + road_w / 2, maxy))

    # Phase 1 — CHEAP selection: score each legal spur by the road-accessible
    # land area it exposes (pieces ≥ min_area that touch the spur), WITHOUT
    # running the expensive sub-plot splitter. Splitting all 14 candidates was
    # ~thousands of buildable-zone computes per band and hung the suite.
    scored: List[Tuple[float, Polygon, List[Polygon]]] = []
    for cbox in candidate_boxes:
        spur = cbox.intersection(polygon)
        if spur.is_empty or spur.area < road_w * road_w:
            continue
        if not isinstance(spur, Polygon):
            spur = max(
                (g for g in spur.geoms if isinstance(g, Polygon)),
                key=lambda g: g.area, default=None,
            )
            if spur is None:
                continue
        if not _spur_is_legal_access(spur, access_geom, plot, tol=tol):
            continue

        land = polygon.difference(spur)
        pieces = [land] if isinstance(land, Polygon) else [
            g for g in getattr(land, "geoms", [])
            if isinstance(g, Polygon) and g.area > 1.0
        ]
        reachable = sum(
            p.area for p in pieces
            if p.area >= min_area and p.distance(spur) < 0.1
        )
        if reachable <= 0.0:
            continue
        scored.append((reachable, spur, pieces))

    scored.sort(key=lambda t: -t[0])

    # Phase 2 — EXPENSIVE split, but only on the few most promising spurs.
    # Accept the first spur that yields at least one valid road-accessible
    # child (partial-accept: un-splittable pieces fall through to nieużytek).
    for _reach, spur, pieces in scored[:3]:
        trial_roads = roads + [spur]
        children: List[SubPlot] = []
        for piece in pieces:
            if piece.area < min_area:
                continue
            if piece.area <= cap_area:
                sub = _wrap_valid_subplot(
                    plot, piece, trial_roads, building_type, builder
                )
                if sub is not None:
                    children.append(sub)
            else:
                children.extend(_split_polygon_to_valid_subplots(
                    plot, piece, trial_roads, building_type, builder,
                    min_area=min_area, cap_area=cap_area,
                ))
        if children:
            return children, spur

    return [], None


def _resolve_oversized_parcels(
    plot: Plot,
    sub_plots: List[SubPlot],
    roads: List[Polygon],
    building_type: BuildingType,
) -> List[SubPlot]:
    """Single terminal post-pass (after the absorb/split loop has converged).

    For each sub-plot that is road-less OR oversized: try a road-accessible
    split, else a legal rescue spur (partial-accept), else demote to nieużytek
    (road-less) or keep as last resort (road-accessible un-splittable). Mutates
    `roads` in place when a rescue spur is accepted. Sub-plots that are both
    road-accessible AND within cap are passed through untouched — this is what
    keeps the zero-nieużytek absorption cases (600-800 etc.) unaffected.
    """
    cap_area = plot.mpzp.max_sub_plot_area_m2 * 1.05
    min_area = plot.mpzp.min_sub_plot_area_m2
    builder = BuildableZoneBuilder()
    out: List[SubPlot] = []

    for sub in sub_plots:
        roadless = (sub.parent_droga_touch + sub.internal_road_touch) <= 0.5
        oversized = sub.area > cap_area
        if not roadless and not oversized:
            out.append(sub)
            continue

        # 1. road-accessible oversized → plain local split (no new road needed).
        if not roadless:
            split = _split_polygon_to_valid_subplots(
                plot, sub.polygon, roads, building_type, builder,
                min_area=min_area, cap_area=cap_area,
            )
            if split:
                out.extend(split)
                continue

        # 2. split failed (awkward road-accessible shape) OR road-less band →
        #    rescue with a legal access spur (partial-accept keeps the legal
        #    children). On dense regular plots this rescue rarely fires (step 1
        #    already succeeds), so it adds negligible cost there.
        children, spur = _rescue_or_demote(
            plot, sub.polygon, roads, building_type, builder,
            min_area=min_area, cap_area=cap_area,
        )
        if children:
            if spur is not None:
                roads.append(spur)
            out.extend(children)
            continue

        # 3. nothing rescuable → demote to nieużytek (never keep a monster).
        #    The honest answer for un-subdividable land is waste (Q1.1(d)/
        #    Q16(a)); dropping the sub lets it fall into nieużytek via
        #    _assemble_nieuzytek (coverage stays exact).
        continue

    return out


def _trim_dead_end_roads(
    plot: Plot,
    roads: List[Polygon],
) -> List[Polygon]:
    """Trim road end-caps that dead-end on a non-DROGA boundary beyond
    min_road_width*0.5 (owner urban rule 2026-05-10; scope decision 2026-05-29).

    On an irregular plot the road-tree generator can run a branch right up to a
    concave (notch) boundary, leaving a stub that wastes land. This pulls every
    *violating* road back `tol` from the non-DROGA boundaries. Roads that do NOT
    breach the tolerance are returned untouched, so well-formed zero-nieużytek
    layouts are unaffected. Trimmed slivers fall into nieużytek (parent − subs −
    roads) — coverage stays exact.
    """
    if not roads:
        return roads
    tol = plot.mpzp.min_road_width_m * 0.5
    non_droga = [
        b.geometry for b in plot.boundaries
        if b.boundary_type != BoundaryType.DROGA
    ]
    if not non_droga:
        return roads
    non_droga_u = unary_union(non_droga)
    probe = non_droga_u.buffer(0.05, cap_style=2)
    pullback = non_droga_u.buffer(tol, cap_style=2)

    out: List[Polygon] = []
    for road in roads:
        try:
            touch = road.boundary.intersection(probe).length
        except Exception:
            touch = 0.0
        if touch <= tol:
            out.append(road)
            continue
        trimmed = road.difference(pullback)
        if isinstance(trimmed, Polygon):
            pieces = [] if trimmed.is_empty else [trimmed]
        else:
            pieces = [
                g for g in getattr(trimmed, "geoms", [])
                if isinstance(g, Polygon)
            ]
        out.extend(p for p in pieces if p.area > 1.0)
    return out


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
    # Terminal post-pass (Session 14): resolve road-less / oversized parcels
    # once, after the loop has converged. Kills the notch monster (rescue spur
    # or demote-to-nieużytek) without the absorb↔split oscillation that doomed
    # the in-loop attempts.
    kept = _resolve_oversized_parcels(plot, kept, roads, building_type)

    # Trim roads that dead-end on a non-DROGA boundary (owner scope decision
    # 2026-05-29) — but ONLY on layouts that already carry genuine waste
    # (irregular plots, e.g. the notch). On a clean zero-nieużytek layout the
    # road tree is correct and a road grazing a sloped boundary legitimately
    # tiles the diagonal edge; trimming there would invent waste and break the
    # zero-nieużytek invariant. Gating on existing waste keeps those layouts
    # untouched while still cleaning the irregular cases the rule targets.
    if _assemble_nieuzytek(plot, kept, roads).area > 1.0:
        roads = _trim_dead_end_roads(plot, roads)

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
