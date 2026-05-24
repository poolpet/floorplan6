"""
Stage 1 — visual smoke test of the buildable-zone calculation.

Per E6 (LESSONS_LEARNED): every geometric change ships with a matplotlib
render. This notebook draws the plot outline, boundary types and the
resulting buildable zone for three cases:

  1. Rectangular 20×30m with mixed boundary types
  2. L-shape 30×20 minus 10×10 corner
  3. Triangle 25×20 (acute corners stress the buffer math)

Outputs land in `notebooks/output/stage1_buildable_zone.png`.
"""
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

BOUNDARY_COLOR = {
    BoundaryType.DROGA: "#e74c3c",                   # red
    BoundaryType.SASIAD_ZABUDOWANY: "#3498db",       # blue
    BoundaryType.SASIAD_NIEZABUDOWANY: "#2ecc71",    # green
    BoundaryType.WLASNA: "#9b59b6",                  # purple
    BoundaryType.NIEZNANA: "#7f8c8d",                # grey
}


def render_plot(ax, plot: Plot, title: str) -> None:
    """Draw plot outline + classified boundaries + buildable zone."""
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.05, color="black")
    ax.plot(px, py, color="black", linewidth=0.8, linestyle=":")

    if plot.buildable_zone and not plot.buildable_zone.is_empty:
        zx, zy = plot.buildable_zone.exterior.xy
        ax.fill(zx, zy, color="#a8e6cf", alpha=0.55,
                edgecolor="#27ae60", linewidth=1.5, hatch="//")

    for b in plot.boundaries:
        bx, by = b.geometry.xy
        ax.plot(bx, by, color=BOUNDARY_COLOR[b.boundary_type], linewidth=3.0)
        mid_x = (bx[0] + bx[1]) / 2
        mid_y = (by[0] + by[1]) / 2
        ax.annotate(
            f"{b.boundary_type.value}\n{b.min_setback:.1f}m",
            xy=(mid_x, mid_y),
            fontsize=7, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="grey", alpha=0.85),
        )

    ratio = (plot.buildable_zone.area / plot.area * 100) if plot.buildable_zone else 0
    ax.set_title(
        f"{title}\nplot {plot.area:.0f} m² → zone "
        f"{(plot.buildable_zone.area if plot.buildable_zone else 0):.0f} m² ({ratio:.0f}%)",
        fontsize=10,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def case_rectangle() -> Plot:
    poly = Polygon([(0, 0), (20, 0), (20, 30), (0, 30)])
    coords = [(0, 0), (20, 0), (20, 30), (0, 30), (0, 0)]
    types = [
        BoundaryType.DROGA,
        BoundaryType.SASIAD_ZABUDOWANY,
        BoundaryType.WLASNA,
        BoundaryType.SASIAD_NIEZABUDOWANY,
    ]
    boundaries = [
        PlotBoundary(LineString([coords[i], coords[i + 1]]), types[i], i)
        for i in range(4)
    ]
    return Plot(
        number="Rectangle 20×30",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(setback_from_road=5.0),
    )


def case_l_shape() -> Plot:
    poly = Polygon([
        (0, 0), (30, 0), (30, 10), (20, 10), (20, 20), (0, 20),
    ])
    boundaries = [
        PlotBoundary(LineString([(0, 0), (30, 0)]), BoundaryType.DROGA, 0),
        PlotBoundary(LineString([(30, 0), (30, 10)]), BoundaryType.SASIAD_ZABUDOWANY, 1),
        PlotBoundary(LineString([(30, 10), (20, 10)]), BoundaryType.WLASNA, 2),
        PlotBoundary(LineString([(20, 10), (20, 20)]), BoundaryType.SASIAD_ZABUDOWANY, 3),
        PlotBoundary(LineString([(20, 20), (0, 20)]), BoundaryType.WLASNA, 4),
        PlotBoundary(LineString([(0, 20), (0, 0)]), BoundaryType.SASIAD_NIEZABUDOWANY, 5),
    ]
    return Plot(
        number="L-shape",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(setback_from_road=5.0),
    )


def case_triangle() -> Plot:
    poly = Polygon([(0, 0), (25, 0), (12.5, 20)])
    boundaries = [
        PlotBoundary(LineString([(0, 0), (25, 0)]), BoundaryType.DROGA, 0),
        PlotBoundary(LineString([(25, 0), (12.5, 20)]), BoundaryType.SASIAD_ZABUDOWANY, 1),
        PlotBoundary(LineString([(12.5, 20), (0, 0)]), BoundaryType.SASIAD_NIEZABUDOWANY, 2),
    ]
    return Plot(
        number="Triangle 25×20",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(setback_from_road=5.0),
    )


def main():
    builder = BuildableZoneBuilder()
    cases = [case_rectangle(), case_l_shape(), case_triangle()]
    for plot in cases:
        builder.compute(plot)

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    titles = ["Rectangle (mixed boundaries)", "L-shape (notch)", "Triangle (acute corners)"]
    for ax, plot, title in zip(axes, cases, titles):
        render_plot(ax, plot, title)

    legend_handles = [
        mpatches.Patch(color=color, label=btype.value)
        for btype, color in BOUNDARY_COLOR.items()
    ]
    legend_handles.append(mpatches.Patch(facecolor="#a8e6cf", edgecolor="#27ae60",
                                          hatch="//", label="Buildable zone"))
    fig.legend(handles=legend_handles, loc="lower center",
               ncol=len(legend_handles), bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Stage 1 — buildable zone (BuildableZoneBuilder smoke test)",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out_path = OUT_DIR / "stage1_buildable_zone.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {out_path}")
    for plot in cases:
        ratio = plot.buildable_zone.area / plot.area * 100
        print(f"  {plot.number}: plot {plot.area:.1f} m² → "
              f"zone {plot.buildable_zone.area:.1f} m² ({ratio:.1f}%)")


if __name__ == "__main__":
    main()
