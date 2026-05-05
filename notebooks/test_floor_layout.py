"""Test the deterministic floor_layout module (REWRITE 2026-05-05)."""
from pathlib import Path
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from core.floor_layout import solve_floor_layout

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def render(result, floor, save_path, title):
    fig, ax = plt.subplots(figsize=(14, 8))
    fx, fy = floor.exterior.xy
    ax.fill(fx, fy, alpha=0.04, color="gray")
    ax.plot(fx, fy, color="black", linewidth=2)

    # Corridor
    if result.corridor:
        cx, cy = result.corridor.exterior.xy
        ax.fill(cx, cy, color="#c8e6c9", alpha=0.7,
                edgecolor="#558b2f", linewidth=1.2, hatch="//")
    # Connectors
    for conn in result.connectors:
        cx, cy = conn.exterior.xy
        ax.fill(cx, cy, color="#c8e6c9", alpha=0.7,
                edgecolor="#558b2f", linewidth=1.2, hatch="//")

    colors = {"M1": "#fce4a4", "M2": "#a8d8ea", "M3": "#aac9b1",
              "M4": "#d4b3d4", "M5": "#f0a6a0"}
    for i, ap in enumerate(result.apartments):
        if ap.polygon is None:
            continue
        ax_, ay = ap.polygon.exterior.xy
        c = colors.get(ap.apartment_type, "#cccccc")
        ax.fill(ax_, ay, color=c, alpha=0.7, edgecolor="black", linewidth=1.0)
        cx, cy = ap.polygon.centroid.x, ap.polygon.centroid.y
        d = result.walking_distances_m[i] if i < len(result.walking_distances_m) else None
        d_str = f"\n{d:.1f}m" if d not in (None, float("inf")) else "\n!"
        ax.text(cx, cy, f"{ap.apartment_type} {ap.area:.0f}m²{d_str}",
                ha="center", va="center", fontsize=8, fontweight="bold")

    for i, stair in enumerate(result.stairwells):
        sx, sy = stair.exterior.xy
        ax.fill(sx, sy, color="#555", alpha=0.85, edgecolor="black", linewidth=1.5)
        cx, cy = stair.centroid.x, stair.centroid.y
        ax.text(cx, cy, f"S{i+1}", ha="center", va="center", fontsize=10,
                color="white", fontweight="bold")

    types = sorted(set(a.apartment_type for a in result.apartments))
    legend = [mpatches.Patch(facecolor=colors[t], label=t) for t in types]
    legend.append(mpatches.Patch(facecolor="#555", label="stairwell"))
    legend.append(mpatches.Patch(facecolor="#c8e6c9", hatch="//", label="corridor"))
    ax.legend(handles=legend, loc="upper right", fontsize=9)

    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches="tight")
    print(f"  -> {save_path}")
    plt.close()


SCENARIOS = [
    {"name": "200m2_4f_N", "floor": Polygon([(0,0),(14,0),(14,14),(0,14)]),
     "h": 2.8, "n": 4, "facade": "N"},
    {"name": "800m2_4f_N", "floor": Polygon([(0,0),(40,0),(40,20),(0,20)]),
     "h": 2.8, "n": 4, "facade": "N"},
    {"name": "1200m2_4f_N", "floor": Polygon([(0,0),(60,0),(60,20),(0,20)]),
     "h": 2.8, "n": 4, "facade": "N"},
    {"name": "600m2_5f_SW_N", "floor": Polygon([(0,0),(30,0),(30,20),(0,20)]),
     "h": 3.0, "n": 5, "facade": "N"},
    {"name": "800m2_4f_S", "floor": Polygon([(0,0),(40,0),(40,20),(0,20)]),
     "h": 2.8, "n": 4, "facade": "S"},
]

for sc in SCENARIOS:
    print(f"\n=== {sc['name']} (facade={sc['facade']}) ===")
    result = solve_floor_layout(
        sc["floor"], floor_height_m=sc["h"], num_floors=sc["n"],
        stairwell_facade=sc["facade"],
    )
    print(f"  Status: {result.status}, class: {result.building_class}, "
          f"stairs: {result.n_stairwells}, elevator: {result.has_elevator}")
    print(f"  Apartments: {len(result.apartments)}")
    if result.apartments:
        from collections import Counter
        ctr = Counter(a.apartment_type for a in result.apartments)
        print(f"  Mix: {dict(ctr)}")
        if result.walking_distances_m:
            mx = max(result.walking_distances_m)
            print(f"  Max walking distance: {mx:.1f}m")
    if result.violations:
        print(f"  Violations: {result.violations[:3]}")
    title = (f"{sc['name']}: {sc['floor'].area:.0f}m^2 floor, class {result.building_class}, "
             f"{result.n_stairwells} stair(s), {len(result.apartments)} apts | {result.status}")
    render(result, sc["floor"], OUT_DIR / f"layout_{sc['name']}.png", title)
