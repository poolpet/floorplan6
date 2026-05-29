"""Stage 1 — notch monster fix sanity check (Session 14, 2026-05-29).

Visual verification of the oversized/road-less parcel rewrite that killed the
"monster" sub-plot on an irregular plot whose notch cuts a band off from the
road tree (Dawid's AC bug: S7 = 19 664 m² on a 284×166 irregular plot).

Before the fix `_absorb_leftover` glued the whole road-less band into one giant
parcel. After the fix the band is either rescued with a legal access spur or
demoted to explicit nieużytek (Q16(a)/Q1.1(d)); dead-ending roads are trimmed.

Renders the notch plot for DETACHED + TWIN. Expected:
  - NO sub-plot exceeds the MPZP cap (no monster)
  - every retained sub-plot touches a road
  - unreachable land shown as brown nieużytek hatch
  - no internal road dead-ending on the notch boundary

Output: notebooks/output/notch_sanity_*.png
"""
from __future__ import annotations

import matplotlib.pyplot as plt

from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_subdivider import BuildingType, subdivide
from shapely.geometry import LineString, Polygon

# Reuse the q21 sanity renderer so both sanity checks look identical.
from notebooks.stage1_q21_sanity import (
    OUT_DIR,
    _legend_handles,
    _print_summary,
    _render,
)


def _notch_road_right_plot() -> Plot:
    """Same fixture as tests/test_plot_subdivider.py::_notch_road_right_plot."""
    pts = [(0, 0), (284, 0), (284, 166), (0, 166),
           (0, 100), (60, 100), (60, 60), (0, 60)]
    btypes = [
        BoundaryType.SASIAD_NIEZABUDOWANY,  # bottom
        BoundaryType.DROGA,                 # right (only road)
        BoundaryType.SASIAD_NIEZABUDOWANY,  # top
        BoundaryType.WLASNA,                # left upper
        BoundaryType.SASIAD_NIEZABUDOWANY,  # notch
        BoundaryType.WLASNA,                # notch
        BoundaryType.SASIAD_NIEZABUDOWANY,  # notch
        BoundaryType.WLASNA,                # left lower
    ]
    geom = Polygon(pts)
    ring = list(geom.exterior.coords)
    boundaries = [
        PlotBoundary(geometry=LineString([ring[i], ring[i + 1]]),
                     boundary_type=btypes[i], segment_index=i)
        for i in range(len(btypes))
    ]
    plot = Plot(
        number="notch",
        geometry=geom,
        boundaries=boundaries,
        mpzp=MPZPParameters(min_front_m=18.0, min_road_width_m=4.5,
                            min_sub_plot_area_m2=400.0, max_sub_plot_area_m2=1000.0),
        housing_type=HousingType.JEDNORODZINNA,
    )
    return plot


def main() -> None:
    cases = [BuildingType.DETACHED, BuildingType.TWIN]
    fig, axes = plt.subplots(1, len(cases), figsize=(16, 7), squeeze=False)
    for ax, bt in zip(axes[0], cases):
        result = subdivide(_notch_road_right_plot(), building_type=bt)
        _print_summary("Notch 284×166 (road right + lower-left notch)", bt, result)
        _render(ax, result, "Notch 284×166 — single-side road", bt)
        out = OUT_DIR / f"notch_sanity_{bt.value}.png"
        single = plt.figure(figsize=(9, 7))
        _render(single.add_subplot(111), result, "Notch 284×166 — single-side road", bt)
        single.legend(handles=_legend_handles(), loc="lower right", fontsize=7)
        single.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(single)
        print(f"  -> {out}")

    fig.legend(handles=_legend_handles(), loc="lower center", ncol=6, fontsize=7)
    overview = OUT_DIR / "notch_sanity_overview.png"
    fig.savefig(overview, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\nOverview -> {overview}")


if __name__ == "__main__":
    main()
