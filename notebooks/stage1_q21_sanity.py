"""Stage 1 Q21 sanity check — visual verification on real-size plots.

Q21 (2026-05-26) zerowała setback boczny na ścianach współdzielonych
TWIN/TERRACED. Jednostkowe testy są zielone (4 nowe `TestQ21SharedWalls`),
ale architektonicznej sanity check na realnych rozmiarach jeszcze nie było.

Scenariusze (z NEXT_SESSION.md):

  1. 265×202 DETACHED   — regresja Q19, oczekiwane ~50 sub-działek
  2. 265×202 TWIN        — regresja Q19, oczekiwane ~60-80, parami
  3. 265×202 TERRACED    — regresja Q19, oczekiwane ~120+, w ciągach
  4. 60×80 TWIN          — regresja Q21, przed Q21 było 0/7 budynków,
                          oczekiwane ≥1 (zone musi być >0 mimo wąskiego frontu)
  5. 60×80 TERRACED      — Q21 nie psuje (przed Q21 też działał)

Każdy scenariusz renderuje:
  - sub-działki kolorowane
  - per-sub-plot buildable zone (zielony hatch)
  - ściany współdzielone (CZERWONA gruba linia — Q21 marker)
  - footprinty budynków (BuildingProposer output, niebieski wypełniony)
  - drogi (ciemnoszary)
  - nieużytek (brązowy hatch)
  - summary w tytule + console log

Output: 5 PNG do `notebooks/output/q21_sanity_*.png`.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.building_proposer import propose_buildings
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.plot_subdivider import (
    BuildingType,
    SubdivisionResult,
    subdivide,
)

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Plot builders — same pattern as tests/test_plot_subdivider.py
# ─────────────────────────────────────────────────────────────────────────────

def _rectangular(width: float, depth: float) -> Plot:
    points = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    boundary_types = [
        BoundaryType.DROGA,                  # bottom (y=0)
        BoundaryType.SASIAD_NIEZABUDOWANY,   # right
        BoundaryType.WLASNA,                 # top
        BoundaryType.SASIAD_NIEZABUDOWANY,   # left
    ]
    coords = points + [points[0]]
    boundaries = [
        PlotBoundary(
            geometry=LineString([coords[i], coords[i + 1]]),
            boundary_type=boundary_types[i],
            segment_index=i,
        )
        for i in range(len(points))
    ]
    plot = Plot(
        number=f"{int(width)}x{int(depth)}",
        geometry=Polygon(points),
        boundaries=boundaries,
        mpzp=MPZPParameters(max_wz=0.30),
        housing_type=HousingType.JEDNORODZINNA,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────

SUBPLOT_COLORS = [
    "#a8d8ea", "#aac9b1", "#fce4a4", "#f7c1bb", "#d4a5e0",
    "#a8e6cf", "#ffd3b6", "#ffaaa5", "#dcedc1", "#ffd6e7",
]


def _render(ax, result: SubdivisionResult, title: str, building_type: BuildingType) -> None:
    plot = result.parent
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=1.0)

    # Sub-plots
    for i, s in enumerate(result.sub_plots):
        sx, sy = s.polygon.exterior.xy
        c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
        ax.fill(sx, sy, color=c, alpha=0.55, edgecolor="black", linewidth=0.4)

        # Per-sub-plot buildable zone
        if s.has_buildable_zone:
            zone = s.buildable_zone
            zones = [zone] if isinstance(zone, Polygon) else list(zone.geoms)
            for z in zones:
                try:
                    zx, zy = z.exterior.xy
                    ax.fill(
                        zx, zy,
                        color="#27ae60", alpha=0.18,
                        edgecolor="#27ae60", linewidth=0.4, linestyle="--",
                    )
                except Exception:
                    pass

        # Building footprint
        if s.proposed_building is not None and not s.proposed_building.is_empty:
            bx, by = s.proposed_building.exterior.xy
            ax.fill(bx, by, color="#1f4e79", alpha=0.85,
                    edgecolor="#0d2538", linewidth=0.6)

        # Shared-wall markers (Q21)
        for b in s.boundaries:
            if b.is_shared_wall:
                xs, ys = b.geometry.xy
                ax.plot(xs, ys, color="#c0392b", linewidth=2.2, solid_capstyle="round")

    # Roads
    for road in result.roads:
        rx, ry = road.exterior.xy
        ax.fill(rx, ry, color="#3a3a3a", alpha=0.85)

    # Nieużytek
    if result.nieuzytek and not result.nieuzytek.is_empty:
        polys = ([result.nieuzytek]
                 if isinstance(result.nieuzytek, Polygon)
                 else list(result.nieuzytek.geoms))
        for poly in polys:
            try:
                wx, wy = poly.exterior.xy
                ax.fill(wx, wy, color="#aa6644", alpha=0.45, hatch="\\\\",
                        edgecolor="#aa6644", linewidth=0.4)
            except Exception:
                pass

    # Summary
    n_subs = len(result.sub_plots)
    n_buildings = sum(
        1 for s in result.sub_plots
        if s.proposed_building is not None and not s.proposed_building.is_empty
    )
    n_shared = sum(
        1 for s in result.sub_plots for b in s.boundaries if b.is_shared_wall
    )
    ratio_road = result.total_road_area / plot.area * 100
    ratio_waste = result.nieuzytek_area / plot.area * 100
    cov = "OK" if result.coverage_ok() else f"DIFF={result.coverage_diff:.2f}m²"

    ax.set_title(
        f"{title} — {building_type.value}\n"
        f"sub={n_subs}  buildings={n_buildings}  shared-walls={n_shared}  "
        f"road={ratio_road:.0f}%  nieużytek={ratio_waste:.0f}%  Q16:{cov}",
        fontsize=10,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def _legend_handles():
    return [
        mpatches.Patch(color="#a8d8ea", label="Sub-działka"),
        mpatches.Patch(
            facecolor="#27ae60", alpha=0.18,
            edgecolor="#27ae60", linestyle="--",
            label="Per-sub-plot buildable zone",
        ),
        mpatches.Patch(color="#1f4e79", alpha=0.85, label="Footprint budynku"),
        mpatches.Patch(
            facecolor="none", edgecolor="#c0392b", linewidth=2.2,
            label="Q21 shared wall (setback=0)",
        ),
        mpatches.Patch(color="#3a3a3a", label="Droga wewnętrzna"),
        mpatches.Patch(
            facecolor="#aa6644", alpha=0.45, hatch="\\\\",
            edgecolor="#aa6644", label="Nieużytek",
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    ("265×202 m", 265.0, 202.0, BuildingType.DETACHED,  "q21_sanity_265x202_DETACHED.png"),
    ("265×202 m", 265.0, 202.0, BuildingType.TWIN,      "q21_sanity_265x202_TWIN.png"),
    ("265×202 m", 265.0, 202.0, BuildingType.TERRACED,  "q21_sanity_265x202_TERRACED.png"),
    ("60×80 m",    60.0,  80.0, BuildingType.TWIN,      "q21_sanity_60x80_TWIN.png"),
    ("60×80 m",    60.0,  80.0, BuildingType.TERRACED,  "q21_sanity_60x80_TERRACED.png"),
]


def _print_summary(title: str, bt: BuildingType, result: SubdivisionResult) -> None:
    n_subs = len(result.sub_plots)
    n_buildings = sum(
        1 for s in result.sub_plots
        if s.proposed_building is not None and not s.proposed_building.is_empty
    )
    shared_per_sub = [
        sum(1 for b in s.boundaries if b.is_shared_wall)
        for s in result.sub_plots
    ]
    n_with_shared = sum(1 for n in shared_per_sub if n > 0)
    avg_area = (sum(s.area for s in result.sub_plots) / n_subs) if n_subs else 0.0
    min_area = min((s.area for s in result.sub_plots), default=0.0)
    max_area = max((s.area for s in result.sub_plots), default=0.0)
    print(
        f"\n=== {title} — {bt.value} ===\n"
        f"  parent area:    {result.parent.area:.0f} m²\n"
        f"  sub-plots:      {n_subs} (avg {avg_area:.0f}, min {min_area:.0f}, max {max_area:.0f} m²)\n"
        f"  with shared:    {n_with_shared} / {n_subs}\n"
        f"  buildings:      {n_buildings} / {n_subs}\n"
        f"  roads:          {result.total_road_area:.0f} m² ({result.total_road_area / result.parent.area * 100:.1f}%)\n"
        f"  nieużytek:      {result.nieuzytek_area:.0f} m² ({result.nieuzytek_area / result.parent.area * 100:.1f}%)\n"
        f"  Q16 coverage:   diff={result.coverage_diff:.2f} m² ({'OK' if result.coverage_ok() else 'FAIL'})"
    )


def main():
    paths: List[Path] = []
    for title, w, d, bt, fname in SCENARIOS:
        plot = _rectangular(w, d)
        result = subdivide(plot, building_type=bt)
        propose_buildings(result, bt)

        _print_summary(title, bt, result)

        fig, ax = plt.subplots(figsize=(14, 10))
        _render(ax, result, title, bt)
        fig.legend(
            handles=_legend_handles(),
            loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.02),
        )
        fig.tight_layout(rect=[0, 0.04, 1, 1])
        out = OUT_DIR / fname
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        paths.append(out)
        print(f"  saved: {out.relative_to(Path(__file__).parent.parent)}")

    # Combined 2×3 overview for at-a-glance comparison.
    fig, axes = plt.subplots(2, 3, figsize=(24, 14))
    flat = axes.flatten()
    for ax, (title, w, d, bt, _) in zip(flat, SCENARIOS):
        plot = _rectangular(w, d)
        result = subdivide(plot, building_type=bt)
        propose_buildings(result, bt)
        _render(ax, result, title, bt)
    # Hide the unused 6th subplot.
    flat[-1].axis("off")
    fig.legend(handles=_legend_handles(), loc="lower center", ncol=6,
               bbox_to_anchor=(0.5, -0.01))
    fig.suptitle(
        "Stage 1 Q21 sanity — 265×202 (DETACHED/TWIN/TERRACED) + 60×80 (TWIN/TERRACED)",
        fontsize=14,
    )
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    overview = OUT_DIR / "q21_sanity_overview.png"
    fig.savefig(overview, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\nOverview: {overview.relative_to(Path(__file__).parent.parent)}")


if __name__ == "__main__":
    main()
