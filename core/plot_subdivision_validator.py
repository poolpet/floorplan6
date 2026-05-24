"""Stage 1 subdivision validator.

This mirrors the Stage 4 validator pattern: hard product rules are attached
to the generated result before scoring and sorting variants.
"""
from __future__ import annotations

from core.plot_subdivider import SubdivisionResult


def validate(result: SubdivisionResult) -> SubdivisionResult:
    """Validate a subdivision result in-place and return it."""
    errors: list[str] = []
    warnings: list[str] = []
    mpzp = result.parent.mpzp

    if not result.sub_plots:
        errors.append("Brak pod-działek.")

    if not result.coverage_ok():
        errors.append(
            f"Q16 coverage diff={result.coverage_diff:.2f}m2 "
            "(sub-plots + roads + nieuzytek must equal parent)."
        )

    if result.nieuzytek_area > 0.5:
        errors.append(
            f"Nieużytek {result.nieuzytek_area:.2f}m2 > 0.5m2."
        )

    missing_access = result.sub_plots_without_road_access
    if missing_access:
        errors.append(
            f"{missing_access} pod-działek bez dostępu do drogi."
        )

    for idx, sub in enumerate(result.sub_plots, start=1):
        if sub.area < mpzp.min_sub_plot_area_m2 - 0.1:
            errors.append(
                f"S{idx}: {sub.area:.1f}m2 < min "
                f"{mpzp.min_sub_plot_area_m2:.1f}m2."
            )
        if sub.area > mpzp.max_sub_plot_area_m2 * 1.05:
            errors.append(
                f"S{idx}: {sub.area:.1f}m2 > max "
                f"{mpzp.max_sub_plot_area_m2:.1f}m2 + 5%."
            )
        if not sub.has_buildable_zone:
            errors.append(f"S{idx}: brak strefy zabudowy.")
        elif sub.buildable_zone.area < _min_buildable_zone_area(result):
            errors.append(
                f"S{idx}: strefa zabudowy "
                f"{sub.buildable_zone.area:.1f}m2 za mała."
            )

    if result.road_area_percent > 12.0:
        warnings.append(
            f"Drogi zajmują {result.road_area_percent:.1f}% działki."
        )

    result.validation_errors = errors
    result.validation_warnings = warnings
    return result


def _min_buildable_zone_area(result: SubdivisionResult) -> float:
    return max(60.0, result.parent.mpzp.min_sub_plot_area_m2 * 0.20)
