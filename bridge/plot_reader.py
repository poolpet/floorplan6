"""
Stage 1 — read a building plot polygon from ArchiCAD.

Reuses `bridge.boundary_reader` to get the outline (any closed shape:
walls chained, Slab or Zone). Wraps it in a `Plot` object with default
boundary classification (DROGA on bottom edge, others SASIAD_NIEZABUDOWANY)
which the user adjusts in the Stage 1 UI before running the analysis.
"""
from __future__ import annotations

from typing import Optional

from shapely.affinity import translate
from shapely.geometry import LineString, Polygon

from bridge.boundary_reader import read_boundary_from_archicad
from bridge.tapir_connection import TapirConnection
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)


def read_plot_from_archicad(
    plot_number: str = "AC-plot",
    tapir: Optional[TapirConnection] = None,
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    mpzp: Optional[MPZPParameters] = None,
) -> Plot:
    """Read a plot polygon from ArchiCAD and wrap it as `Plot`.

    Boundary classification defaults: bottom edge of bbox → DROGA,
    others → SASIAD_NIEZABUDOWANY. The user is expected to refine
    classifications via the UI.
    """
    if tapir is None:
        tapir = TapirConnection()
        tapir.connect()

    polygon, _entry_point, _wall_types = read_boundary_from_archicad(tapir)

    # Translate to origin so the UI bounds line up with x∈[0,W], y∈[0,D].
    bx0, by0, _, _ = polygon.bounds
    polygon = translate(polygon, -bx0, -by0)

    return wrap_polygon_as_plot(
        polygon,
        plot_number=plot_number,
        housing_type=housing_type,
        mpzp=mpzp,
    )


def wrap_polygon_as_plot(
    polygon: Polygon,
    plot_number: str = "plot",
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    mpzp: Optional[MPZPParameters] = None,
) -> Plot:
    """Build a `Plot` from a Shapely polygon with default boundary tags.

    Heuristic: the edge with the smallest midpoint-y (bottom-most edge,
    even if slanted) is tagged DROGA. All other edges default to
    SASIAD_NIEZABUDOWANY. The user is expected to refine in the UI.
    """
    coords = list(polygon.exterior.coords)
    edges = list(zip(coords, coords[1:]))
    if not edges:
        return Plot(
            number=plot_number, geometry=polygon, boundaries=[],
            mpzp=mpzp or MPZPParameters(), housing_type=housing_type,
        )

    midys = [((a[1] + b[1]) / 2) for a, b in edges]
    droga_idx = min(range(len(edges)), key=lambda i: midys[i])

    boundaries = []
    for i, (a, b) in enumerate(edges):
        edge = LineString([a, b])
        if edge.length < 0.01:
            continue
        btype = BoundaryType.DROGA if i == droga_idx else BoundaryType.SASIAD_NIEZABUDOWANY
        boundaries.append(PlotBoundary(
            geometry=edge,
            boundary_type=btype,
            segment_index=i,
        ))

    return Plot(
        number=plot_number,
        geometry=polygon,
        boundaries=boundaries,
        mpzp=mpzp or MPZPParameters(),
        housing_type=housing_type,
    )
