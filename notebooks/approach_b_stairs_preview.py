"""Sesja 18 — podgląd Approach B: schody jako osobny pokój + orientacja biegu.

Renderuje 9×7 i 8×8 do PNG, żeby Dawid mógł ocenić:
- schody jako osobny pokój (Schody) + osobny Hol (kompaktowy),
- orientację biegu (podest przy Holu, strzałka w głąb).
"""
import matplotlib
matplotlib.use("Agg")
from pathlib import Path

from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

for (W, H, e, tag) in [(9.0, 7.0, (4.5, 0.0), "9x7"), (8.0, 8.0, (4.0, 0.0), "8x8")]:
    layout = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), e,
                            num_storeys=2, time_limit_s=25.0)
    print(f"{tag}: ok={layout.ok} stair_core={layout.stair_core}")
    if not layout.ok:
        continue
    pf = place_furniture(layout.parter_rooms)
    gf = place_furniture(layout.pietro_rooms)
    render_two_storey(layout, parter_furniture=pf, pietro_furniture=gf,
                      title=f"Approach B — schody osobny pokój ({tag})",
                      save_path=OUT / f"approach_b_stairs_{tag}.png", show=False)
    print(f"  -> output/approach_b_stairs_{tag}.png")
