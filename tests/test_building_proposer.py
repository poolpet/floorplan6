"""Stage 1 Mode B — building proposer per BuildingType (regression).

Regression for commit fixing `BuildingType.SEMI` → `BuildingType.TWIN`
in core/building_proposer.py. The original module referenced an
attribute that did not exist on the enum (TWIN is the canonical name),
so importing the module raised AttributeError at dict-construction time
and Mode B/TWIN/TERRACED in the GUI crashed.

These tests pin:
  1. The BUILDING_DIMENSIONS dict only references existing enum members.
  2. `propose_buildings(...)` runs end-to-end for each BuildingType
     and sets `proposed_building` on at least one sub-plot.
"""
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.building_proposer import BUILDING_DIMENSIONS, propose_buildings
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_subdivider import BuildingType, subdivide


def _rect_plot(w: float, d: float) -> Plot:
    poly = Polygon([(0, 0), (w, 0), (w, d), (0, d)])
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    cyc = pts + [pts[0]]
    plot = Plot(
        number="P",
        geometry=poly,
        boundaries=[
            PlotBoundary(
                geometry=LineString([cyc[i], cyc[i + 1]]),
                boundary_type=(
                    BoundaryType.DROGA if i == 0
                    else BoundaryType.SASIAD_NIEZABUDOWANY
                ),
                segment_index=i,
            )
            for i in range(4)
        ],
        mpzp=MPZPParameters(
            max_wz=0.30,
            min_front_m=18.0,
            min_road_width_m=4.5,
            min_sub_plot_area_m2=400.0,
            max_sub_plot_area_m2=1500.0,
        ),
        housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def test_building_dimensions_keys_match_enum_members():
    """Dict construction crashed when SEMI was used — TWIN is the canonical name."""
    assert BuildingType.DETACHED in BUILDING_DIMENSIONS
    assert BuildingType.TWIN in BUILDING_DIMENSIONS
    assert BuildingType.TERRACED in BUILDING_DIMENSIONS


def test_propose_buildings_detached_assigns_at_least_one_building():
    plot = _rect_plot(60, 80)
    result = subdivide(plot, building_type=BuildingType.DETACHED)
    propose_buildings(result, BuildingType.DETACHED)
    placed = sum(
        1 for s in result.sub_plots
        if getattr(s, "proposed_building", None) is not None
    )
    assert placed >= 1, "DETACHED: no sub-plot received a proposed building"


def test_propose_buildings_twin_runs_and_assigns():
    """Mode B/TWIN crashed before the SEMI→TWIN fix — covers _propose_semi_pairs path."""
    plot = _rect_plot(60, 80)
    result = subdivide(plot, building_type=BuildingType.TWIN)
    propose_buildings(result, BuildingType.TWIN)
    placed = sum(
        1 for s in result.sub_plots
        if getattr(s, "proposed_building", None) is not None
    )
    assert placed >= 1, "TWIN: no sub-plot received a proposed building"


def test_propose_buildings_terraced_runs_and_assigns():
    """Mode B/TERRACED — covers _propose_terraced_chain path."""
    plot = _rect_plot(60, 80)
    result = subdivide(plot, building_type=BuildingType.TERRACED)
    propose_buildings(result, BuildingType.TERRACED)
    placed = sum(
        1 for s in result.sub_plots
        if getattr(s, "proposed_building", None) is not None
    )
    assert placed >= 1, "TERRACED: no sub-plot received a proposed building"
