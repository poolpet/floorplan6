"""Stage 1 subdivision variants — Stage 4 style orchestration.

These tests pin the product direction: Stage 1 should not return a single
opaque subdivision. It should generate candidate layouts, validate them,
score them, and let `subdivide()` return the best one while preserving the
old public API.
"""
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_subdivider import BuildingType, subdivide
from core.plot_variant_generator import generate_subdivision_variants


def _make_plot(points, boundary_types):
    poly = Polygon(points)
    coords = list(points) + [points[0]]
    plot = Plot(
        number="P",
        geometry=poly,
        boundaries=[
            PlotBoundary(
                geometry=LineString([coords[i], coords[i + 1]]),
                boundary_type=boundary_types[i],
                segment_index=i,
            )
            for i in range(len(points))
        ],
        mpzp=MPZPParameters(
            max_wz=0.30,
            min_front_m=18.0,
            min_road_width_m=4.5,
            min_sub_plot_area_m2=400.0,
            max_sub_plot_area_m2=800.0,
        ),
        housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def _wide_sloped_plot():
    return _make_plot(
        [(0, 38), (401.84, 0), (401.84, 150), (0, 188.04)],
        [
            BoundaryType.DROGA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
            BoundaryType.WLASNA,
            BoundaryType.SASIAD_NIEZABUDOWANY,
        ],
    )


def test_generate_subdivision_variants_returns_scored_sorted_candidates():
    plot = _wide_sloped_plot()

    variants = generate_subdivision_variants(
        plot,
        building_type=BuildingType.DETACHED,
        max_variants=4,
    )

    assert len(variants) >= 2
    assert [v.score for v in variants] == sorted(
        [v.score for v in variants],
        reverse=True,
    )
    for variant in variants:
        assert variant.is_valid, variant.validation_errors
        assert 0.0 <= variant.score <= 1.0
        assert {
            "buildable_area",
            "road_efficiency",
            "waste_control",
            "road_access",
            "area_fit",
            "regularity",
        }.issubset(variant.score_breakdown)


def test_variant_generator_explores_different_road_tree_strategies():
    plot = _wide_sloped_plot()

    variants = generate_subdivision_variants(
        plot,
        building_type=BuildingType.DETACHED,
        max_variants=6,
    )

    road_areas = {round(v.total_road_area, 1) for v in variants}
    strategy_names = {v.orientation_name for v in variants}

    assert len(strategy_names) >= 2
    assert len(road_areas) >= 2


def test_subdivide_returns_best_scored_variant_without_changing_public_api():
    plot = _wide_sloped_plot()

    best = subdivide(plot, building_type=BuildingType.DETACHED)

    assert best.is_valid, best.validation_errors
    assert best.score > 0
    assert "road_efficiency" in best.score_breakdown
    assert best.orientation_name.startswith("road_tree")
