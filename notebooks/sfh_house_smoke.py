# notebooks/sfh_house_smoke.py
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
from core.house_layout import generate_house

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

# Realistic single-family footprint ~ 9 x 7.5 m = 67.5 m2 / storey.
poly = Polygon([(0, 0), (9, 0), (9, 7.5), (0, 7.5)])
layout = generate_house(poly, entry_point=(4.5, 0.0), time_limit_s=45.0)
print("ok:", layout.ok, "| msg:", layout.message, "| stair_core:", layout.stair_core)
if not layout.ok:
    print("9x7.5 INFEASIBLE — retrying with 10x8 footprint...")
    poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
    layout = generate_house(poly, entry_point=(5, 0), time_limit_s=45.0)
    print("ok:", layout.ok, "| msg:", layout.message, "| stair_core:", layout.stair_core)

if layout.ok:
    print("parter:", [(r.spec.id, round(r.polygon.area, 1)) for r in layout.parter_rooms])
    print("pietro:", [(r.spec.id, round(r.polygon.area, 1)) for r in layout.pietro_rooms])

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, rooms, title in ((axes[0], layout.parter_rooms, "PARTER"),
                             (axes[1], layout.pietro_rooms, "PIETRO")):
        for r in rooms:
            xs, ys = r.polygon.exterior.xy
            ax.fill(xs, ys, alpha=0.4, edgecolor="black", linewidth=0.8)
            c = r.polygon.centroid
            ax.text(c.x, c.y, f"{r.spec.id}\n{r.polygon.area:.1f}m2",
                    ha="center", va="center", fontsize=7)
        sx, sy, sw, sh = layout.stair_core
        ax.add_patch(plt.Rectangle((sx, sy), sw, sh, fill=False,
                                   edgecolor="red", linewidth=2.0))
        ax.text(sx + sw / 2, sy + sh / 2, "schody", ha="center", va="center",
                fontsize=7, color="red")
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
    fig.suptitle(f"Dom jednorodzinny 2-kond. — obrys {poly.bounds[2]:.0f}x{poly.bounds[3]:.1f} m")
    out = OUT / "sfh_house_smoke.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print("->", out)
