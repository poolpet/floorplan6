"""Stage 1 subdivision variant generation.

Stage 4 already proved the pattern: generate candidates, validate, score,
deduplicate, sort. This module gives Stage 1 the same product-grade shape.
"""
from __future__ import annotations

from core.plot_model import Plot
from core.plot_subdivider import (
    BuildingType,
    SubdivisionResult,
    _subdivide_single,
)
from core.plot_subdivision_scorer import score
from core.subdivision_roads import RoadTreeSettings


def generate_subdivision_variants(
    plot: Plot,
    *,
    building_type: BuildingType = BuildingType.DETACHED,
    max_variants: int = 5,
) -> list[SubdivisionResult]:
    """Generate scored subdivision candidates and return best first."""
    candidates: list[SubdivisionResult] = []
    seen: set[str] = set()

    for settings in _road_tree_strategy_set(plot):
        result = _subdivide_single(
            plot,
            building_type=building_type,
            road_settings=settings,
        )
        score(result)
        key = _result_hash(result)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(result)
        if max_variants == 1 and result.is_valid:
            return [result]

    candidates.sort(key=lambda r: r.score, reverse=True)
    valid = [c for c in candidates if c.is_valid]
    return (valid or candidates)[:max_variants]


def _road_tree_strategy_set(plot: Plot) -> list[RoadTreeSettings]:
    """Small deterministic search space; no random magic in MVP."""
    balanced = RoadTreeSettings(
        name="road_tree_balanced",
        branch_row_group=2,
        trunk_position=0.50,
        edge_clearance_front_factor=0.50,
        shallow_depth_factor=1.75,
    )
    minimal = RoadTreeSettings(
        name="road_tree_minimal",
        branch_row_group=3,
        trunk_position=0.50,
        edge_clearance_front_factor=0.75,
        shallow_depth_factor=1.90,
    )
    left_trunk = RoadTreeSettings(
        name="road_tree_left_trunk",
        branch_row_group=2,
        trunk_position=0.35,
        edge_clearance_front_factor=0.60,
        shallow_depth_factor=1.75,
    )
    right_trunk = RoadTreeSettings(
        name="road_tree_right_trunk",
        branch_row_group=2,
        trunk_position=0.65,
        edge_clearance_front_factor=0.60,
        shallow_depth_factor=1.75,
    )
    direct_bias = RoadTreeSettings(
        name="road_tree_direct_bias",
        branch_row_group=3,
        trunk_position=0.50,
        edge_clearance_front_factor=0.50,
        shallow_depth_factor=2.10,
    )
    tight = RoadTreeSettings(
        name="road_tree_tight_lots",
        branch_row_group=1,
        trunk_position=0.65,
        edge_clearance_front_factor=0.0,
        shallow_depth_factor=1.75,
    )
    tight_alt = RoadTreeSettings(
        name="road_tree_tight_lots_alt",
        branch_row_group=1,
        trunk_position=0.35,
        edge_clearance_front_factor=0.0,
        shallow_depth_factor=1.75,
    )

    if (
        plot.mpzp.min_sub_plot_area_m2 >= 500
        and plot.mpzp.max_sub_plot_area_m2 <= 900
    ):
        return [
            left_trunk,
            right_trunk,
            tight_alt,
            tight,
            balanced,
            minimal,
            direct_bias,
        ]

    return [
        balanced,
        minimal,
        left_trunk,
        right_trunk,
        direct_bias,
        tight,
        tight_alt,
    ]


def _result_hash(result: SubdivisionResult) -> str:
    """Coarse geometry hash for deduplication of equivalent candidates."""
    return "|".join([
        str(len(result.sub_plots)),
        str(round(result.total_road_area, 1)),
        str(round(result.total_buildable_area, 1)),
        str(round(result.nieuzytek_area, 1)),
        result.orientation_name,
    ])
