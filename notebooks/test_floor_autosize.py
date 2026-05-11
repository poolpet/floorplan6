"""
KROK A: solver z auto-compute klatki i mix.

3 scenariusze:
- 200m² (~14×14m), 4 kondyg., domyślny mix
- 800m² (~32×25m), 4 kondyg., domyślny mix
- 600m² (~30×20m), 5 kondyg. (klasa SW)
"""
from pathlib import Path
from shapely.geometry import Polygon, box as sbox
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from rules._loader import get_default_pack as _get_default_pack
APARTMENT_MIX_DEFAULT = _get_default_pack().constants["apartment_mix_default"]
from core.floor_compute import (
    compute_stairwell_dimensions, compute_apartment_count, compute_min_stairwells,
)
from core.floor_solver import solve_floor

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def make_centered_stairwell(floor_polygon, sw_w, sw_l):
    bx0, by0, bx1, by1 = floor_polygon.bounds
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    return sbox(cx - sw_w / 2, cy - sw_l / 2, cx + sw_w / 2, cy + sw_l / 2)


def render(result, floor, stair, save_path, title):
    fig, ax = plt.subplots(figsize=(13, 8))
    fx, fy = floor.exterior.xy
    ax.fill(fx, fy, alpha=0.05, color="gray")
    ax.plot(fx, fy, color="black", linewidth=2)

    colors = {"M1": "#fce4a4", "M2": "#a8d8ea", "M3": "#aac9b1",
              "M4": "#d4b3d4", "M5": "#f0a6a0"}
    for ap in result.apartments:
        if ap.polygon is None:
            continue
        ax_, ay = ap.polygon.exterior.xy
        c = colors.get(ap.apartment_type, "#cccccc")
        ax.fill(ax_, ay, color=c, alpha=0.7, edgecolor="black", linewidth=1.2)
        cx, cy = ap.polygon.centroid.x, ap.polygon.centroid.y
        ax.text(cx, cy, f"{ap.apartment_type}\n{ap.area:.0f}m²",
                ha="center", va="center", fontsize=9, fontweight="bold")

    sx, sy = stair.exterior.xy
    ax.fill(sx, sy, color="#666", alpha=0.7, edgecolor="black", linewidth=1.5)
    cx, cy = stair.centroid.x, stair.centroid.y
    ax.text(cx, cy, "K1", ha="center", va="center", fontsize=10,
            color="white", fontweight="bold")

    types_used = sorted(set(ap.apartment_type for ap in result.apartments))
    legend = [mpatches.Patch(facecolor=colors[t], label=t) for t in types_used]
    legend.append(mpatches.Patch(facecolor="#666", label="klatka"))
    ax.legend(handles=legend, loc="upper right", fontsize=10)

    ax.set_aspect("equal"); ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(save_path, dpi=120, bbox_inches="tight")
    print(f"  → {save_path}"); plt.close()


SCENARIOS = [
    {"name": "200m2_4kond", "floor": Polygon([(0,0),(14,0),(14,14),(0,14)]),
     "h": 2.8, "n": 4},
    {"name": "800m2_4kond", "floor": Polygon([(0,0),(32,0),(32,25),(0,25)]),
     "h": 2.8, "n": 4},
    {"name": "600m2_5kond_SW", "floor": Polygon([(0,0),(30,0),(30,20),(0,20)]),
     "h": 3.0, "n": 5},
]

for sc in SCENARIOS:
    print(f"\n=== {sc['name']} ===")
    floor = sc["floor"]; h = sc["h"]; n = sc["n"]
    print(f"  Floor: {floor.area:.1f}m², h_kondyg={h}m, n_floors={n}")

    # Auto-compute klatki
    sw = compute_stairwell_dimensions(h, n)
    print(f"  Klasa: {sw['building_class']}, klatka {sw['stairwell_width_m']}×{sw['stairwell_length_m']}m "
          f"({sw['stairwell_area_m2']}m²), winda={sw['has_elevator']}")
    stair = make_centered_stairwell(floor, sw["stairwell_width_m"], sw["stairwell_length_m"])

    # Auto-compute liczby klatek (z geometrii + WT)
    stairs_required = compute_min_stairwells(floor, h, n)
    print(f"  Wymagane klatek: {stairs_required['n_required']} "
          f"(geo={stairs_required['n_geometric']}, WT_min={stairs_required['n_wt_min']})")
    if stairs_required['n_required'] > 1:
        print(f"  ⚠️  KROK A obsługuje tylko 1 klatkę. Multiple = KROK B.")

    # Auto-compute mieszkań
    apt = compute_apartment_count(floor.area, APARTMENT_MIX_DEFAULT, reserve_ratio=0.15)
    print(f"  Mieszkań: {apt['per_type']} (łącznie {apt['total_count']})")

    # Solver
    result = solve_floor(floor, stair, apt["per_type"], time_limit_s=20.0)
    print(f"  Status: {result.status}, czas: {result.solve_time_s:.2f}s")

    if result.apartments:
        for ap in result.apartments:
            b = ap.polygon.bounds
            print(f"    {ap.apartment_type}: {ap.area:.1f}m² ({b[2]-b[0]:.1f}×{b[3]-b[1]:.1f}m)")
        title = (f"{sc['name']}: {floor.area:.0f}m² piętro, klasa {sw['building_class']}, "
                 f"klatka {sw['stairwell_area_m2']}m² | {result.status}")
        render(result, floor, stair, OUT_DIR / f"floor_auto_{sc['name']}.png", title)
