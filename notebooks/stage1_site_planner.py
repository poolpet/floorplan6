"""
Stage 1 — visual smoke test of the site planner (Mode A buildup variants).

Renders 3 cases side-by-side:
  1. Single-family rural (jednorodzinna + infrastructure_municipal=False)
     → building, parking, well, septic, green
  2. Single-family municipal (infrastructure_municipal=True)
     → building, parking, green (no well/septic per Q13)
  3. Multi-family (wielorodzinna)
     → building, parking row (N stalls), green (no well/septic per Q17)

Outputs land in `notebooks/output/stage1_site_planner.png`.
"""
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)
from core.site_element_model import SiteElementType
from core.site_planner import SitePlanner

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

ELEMENT_COLOR = {
    SiteElementType.BUDYNEK_GLOWNY: "#5b6d8a",
    SiteElementType.MIEJSCE_POSTOJOWE: "#3a3a3a",
    SiteElementType.STUDNIA: "#3498db",
    SiteElementType.SZAMBO: "#8b5e34",
    SiteElementType.STREFA_ZIELENI: "#88c082",
    SiteElementType.SMIETNIK: "#aa6644",
    SiteElementType.GARAZ: "#7f8c8d",
    SiteElementType.BUDYNEK_GOSPODARCZY: "#a8a8a8",
}

ELEMENT_LABEL = {
    SiteElementType.BUDYNEK_GLOWNY: "Budynek",
    SiteElementType.MIEJSCE_POSTOJOWE: "Parking",
    SiteElementType.STUDNIA: "Studnia",
    SiteElementType.SZAMBO: "Szambo",
    SiteElementType.STREFA_ZIELENI: "Zieleń",
}


def make_plot(housing_type, infrastructure_municipal,
              width=60.0, depth=50.0, max_floors=2, parking_per_unit=2.0):
    poly = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
    coords = [(0, 0), (width, 0), (width, depth), (0, depth), (0, 0)]
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
    plot = Plot(
        number=f"{housing_type.value} {'rural' if not infrastructure_municipal else 'urban'}",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            max_wiz=0.60,
            max_floors=max_floors,
            infrastructure_municipal=infrastructure_municipal,
            parking_spaces_per_unit=parking_per_unit,
        ),
        housing_type=housing_type,
    )
    BuildableZoneBuilder().compute(plot)
    return plot


def render_variant(ax, plot, variant, title):
    px, py = plot.geometry.exterior.xy
    ax.fill(px, py, alpha=0.04, color="black")
    ax.plot(px, py, color="black", linewidth=0.8)

    if plot.buildable_zone:
        zx, zy = plot.buildable_zone.exterior.xy
        ax.plot(zx, zy, color="#27ae60", linestyle="--", linewidth=0.8, alpha=0.7)

    for el in variant.elements:
        if not el.geometry or el.geometry.is_empty:
            continue
        try:
            ex, ey = el.geometry.exterior.xy
        except Exception:
            continue
        color = ELEMENT_COLOR.get(el.element_type, "#888888")
        alpha = 0.4 if el.element_type == SiteElementType.STREFA_ZIELENI else 0.85
        ax.fill(ex, ey, color=color, alpha=alpha,
                edgecolor="black", linewidth=0.6)

        if el.element_type == SiteElementType.MIEJSCE_POSTOJOWE:
            n = el.metadata.get("space_count", 1)
            cx, cy = el.geometry.centroid.x, el.geometry.centroid.y
            ax.annotate(f"P×{n}", xy=(cx, cy), fontsize=8, ha="center",
                        color="white", weight="bold")

    ax.set_title(
        f"{title}\nWZ={variant.wz:.2%}  WIZ={variant.wiz:.2%}  PBC={variant.pbc_percent:.0f}%",
        fontsize=10,
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)


def main():
    cases = [
        ("Jednorodzinna rural\n(well + septic ON)",
         make_plot(HousingType.JEDNORODZINNA, infrastructure_municipal=False)),
        ("Jednorodzinna municipal\n(Q13 — well/septic skipped)",
         make_plot(HousingType.JEDNORODZINNA, infrastructure_municipal=True)),
        ("Wielorodzinna\n(Q17 — well/septic skipped, parking row)",
         make_plot(HousingType.WIELORODZINNA, infrastructure_municipal=False,
                   max_floors=3, parking_per_unit=1.5)),
    ]

    planner = SitePlanner()
    requested = [
        SiteElementType.MIEJSCE_POSTOJOWE,
        SiteElementType.STUDNIA,
        SiteElementType.SZAMBO,
        SiteElementType.STREFA_ZIELENI,
    ]

    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    for ax, (title, plot) in zip(axes, cases):
        variants = planner.propose_max_buildup(plot, requested)
        if variants:
            render_variant(ax, plot, variants[0], title)
        else:
            ax.set_title(f"{title}\nNo variants generated")

    legend_handles = [
        mpatches.Patch(color=ELEMENT_COLOR[k], label=ELEMENT_LABEL.get(k, k.value))
        for k in [
            SiteElementType.BUDYNEK_GLOWNY,
            SiteElementType.MIEJSCE_POSTOJOWE,
            SiteElementType.STUDNIA,
            SiteElementType.SZAMBO,
            SiteElementType.STREFA_ZIELENI,
        ]
    ]
    fig.legend(handles=legend_handles, loc="lower center",
               ncol=len(legend_handles), bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(
        "Stage 1 — site planner (Mode A): jednorodzinna rural | jednorodzinna municipal | wielorodzinna",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out_path = OUT_DIR / "stage1_site_planner.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {out_path}")
    for title, plot in cases:
        variants = planner.propose_max_buildup(plot, requested)
        v = variants[0] if variants else None
        if v:
            elements = [el.element_type.value for el in v.elements]
            print(f"  {plot.number}: {v}; elements={elements}")


if __name__ == "__main__":
    main()
