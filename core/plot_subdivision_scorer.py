"""Stage 1 subdivision scoring.

The top objective is usable/buildable land. Roads and waste are penalties:
they are necessary only insofar as they create legal access.
"""
from __future__ import annotations

from core.plot_subdivider import SubdivisionResult
from core.plot_subdivision_validator import validate


WEIGHTS = {
    "buildable_area": 0.35,
    "road_efficiency": 0.20,
    "waste_control": 0.20,
    "road_access": 0.10,
    "area_fit": 0.10,
    "regularity": 0.05,
}


def score(result: SubdivisionResult) -> SubdivisionResult:
    """Compute score 0..1 and attach score_breakdown to the result."""
    validate(result)

    breakdown = {
        "buildable_area": _score_buildable_area(result),
        "road_efficiency": _score_road_efficiency(result),
        "waste_control": _score_waste_control(result),
        "road_access": _score_road_access(result),
        "area_fit": _score_area_fit(result),
        "regularity": _score_regularity(result),
    }
    total = sum(WEIGHTS[k] * breakdown[k] for k in WEIGHTS)
    if result.validation_errors:
        total *= 0.25

    result.score = max(0.0, min(1.0, total))
    result.score_breakdown = breakdown
    return result


def _score_buildable_area(result: SubdivisionResult) -> float:
    # 50% parent area as buildable zone is very strong for single-family
    # subdivision with setbacks; higher values are capped.
    return max(0.0, min(1.0, result.buildable_area_percent / 50.0))


def _score_road_efficiency(result: SubdivisionResult) -> float:
    return max(0.0, 1.0 - min(result.road_area_percent / 12.0, 1.0))


def _score_waste_control(result: SubdivisionResult) -> float:
    return max(0.0, 1.0 - min(result.nieuzytek_percent / 5.0, 1.0))


def _score_road_access(result: SubdivisionResult) -> float:
    if not result.sub_plots:
        return 0.0
    missing = result.sub_plots_without_road_access
    return max(0.0, 1.0 - missing / len(result.sub_plots))


def _score_area_fit(result: SubdivisionResult) -> float:
    if not result.sub_plots:
        return 0.0
    mpzp = result.parent.mpzp
    ok = [
        s for s in result.sub_plots
        if (
            mpzp.min_sub_plot_area_m2 <= s.area
            <= mpzp.max_sub_plot_area_m2 * 1.05
        )
    ]
    return len(ok) / len(result.sub_plots)


def _score_regularity(result: SubdivisionResult) -> float:
    scores = []
    for sub in result.sub_plots:
        try:
            obb = sub.polygon.minimum_rotated_rectangle
            if obb.area > 0:
                scores.append(max(0.0, min(1.0, sub.area / obb.area)))
        except Exception:
            continue
    return sum(scores) / len(scores) if scores else 0.0
