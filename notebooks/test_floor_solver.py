"""
Test KROK 1 floor_solver — prosty scenariusz: piętro 20×10, klatka 4×4 w środku, mix M2+M2+M3+M3.

Renderuje PNG z mieszkaniami + klatką.
"""
from pathlib import Path
from shapely.geometry import Polygon, box as sbox
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from core.floor_solver import solve_floor

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def render(result, floor_polygon, stairwell, save_path):
    fig, ax = plt.subplots(figsize=(12, 7))
    fx, fy = floor_polygon.exterior.xy
    ax.fill(fx, fy, alpha=0.05, color="gray")
    ax.plot(fx, fy, color="black", linewidth=2)

    colors = {"M1": "#fce4a4", "M2": "#a8d8ea", "M3": "#aac9b1",
              "M4": "#d4b3d4", "M5": "#f0a6a0"}
    for ap in result.apartments:
        if ap.polygon is None:
            continue
        ax_, ay = ap.polygon.exterior.xy
        c = colors.get(ap.apartment_type, "#cccccc")
        ax.fill(ax_, ay, color=c, alpha=0.7, edgecolor="black", linewidth=1.5)
        cx, cy = ap.polygon.centroid.x, ap.polygon.centroid.y
        ax.text(cx, cy, f"{ap.apartment_type}\n{ap.area:.1f}m²",
                ha="center", va="center", fontsize=10, fontweight="bold")

    sx, sy = stairwell.exterior.xy
    ax.fill(sx, sy, color="#888", alpha=0.6, edgecolor="black", linewidth=1.5)
    cx, cy = stairwell.centroid.x, stairwell.centroid.y
    ax.text(cx, cy, "KLATKA\nschodowa", ha="center", va="center",
            fontsize=9, color="white", fontweight="bold")

    legend = [mpatches.Patch(facecolor=colors[t], label=t)
              for t in sorted(set(ap.apartment_type for ap in result.apartments))]
    legend.append(mpatches.Patch(facecolor="#888", label="klatka"))
    ax.legend(handles=legend, loc="upper right", fontsize=10)

    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"Etap 3: podział piętra ({result.status}, "
                 f"czas: {result.solve_time_s:.1f}s)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches="tight")
    print(f"  → {save_path}")
    plt.close()


SCENARIOS = [
    {
        # 240m² floor, klatka 4×4=16, usable 224. Mix M2+M2+M3+M3 = 210 → 14m² nadmiaru
        "name": "24x10_4apt",
        "floor": Polygon([(0, 0), (24, 0), (24, 10), (0, 10)]),
        "stairwell": sbox(10, 4, 14, 8),
        "mix": ["M2", "M2", "M3", "M3"],
    },
    {
        # 320m² floor, klatka 4×4=16, usable 304. Mix [M2,M2,M3,M3,M4] = 290
        "name": "32x10_5apt",
        "floor": Polygon([(0, 0), (32, 0), (32, 10), (0, 10)]),
        "stairwell": sbox(14, 4, 18, 8),
        "mix": ["M2", "M2", "M3", "M3", "M4"],
    },
    {
        # mała: 16×8=128, klatka 3×3=9, usable 119. Mix [M2,M2] = 90 → 29m² nadmiaru
        "name": "16x8_2apt",
        "floor": Polygon([(0, 0), (16, 0), (16, 8), (0, 8)]),
        "stairwell": sbox(6.5, 2.5, 9.5, 5.5),
        "mix": ["M2", "M2"],
    },
]


for sc in SCENARIOS:
    print(f"\n=== Scenariusz: {sc['name']} (mix: {sc['mix']}) ===")
    print(f"  Floor: {sc['floor'].area:.1f}m², Klatka: {sc['stairwell'].area:.1f}m²")
    print(f"  Suma min mieszkań: {sum([35, 45, 60, 80, 100]['M1M2M3M4M5'.index(t[0]+t[1])//2] if False else __import__('config').APARTMENT_MIN_AREA[t] for t in sc['mix']):.1f}m²")
    result = solve_floor(sc["floor"], sc["stairwell"], sc["mix"], time_limit_s=15.0)
    print(f"  Status: {result.status}, czas: {result.solve_time_s:.2f}s")
    if result.apartments:
        for i, ap in enumerate(result.apartments):
            b = ap.polygon.bounds
            print(f"    {ap.apartment_type:3s}  {ap.area:5.1f}m²  "
                  f"({b[0]:.1f},{b[1]:.1f})→({b[2]:.1f},{b[3]:.1f})  "
                  f"({b[2]-b[0]:.1f}×{b[3]-b[1]:.1f}m)")
        render(result, sc["floor"], sc["stairwell"],
               OUT_DIR / f"floor_{sc['name']}.png")
    else:
        print(f"    Brak rozwiązania!")
