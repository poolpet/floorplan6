"""Headless smoke — dom 2-kondygnacyjny Z MEBLAMI, oficjalny renderer.

Run:  PYTHONPATH=. MPLBACKEND=Agg python notebooks/sfh_furnished_smoke.py
"""
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)


def main(w=9.0, h=7.5):
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    layout = generate_house(poly, entry_point=(w / 2, 0.0), time_limit_s=30.0)
    print(f"ok={layout.ok} | msg: {layout.message} | stair_core={layout.stair_core}")
    if not layout.ok:
        return
    pf = place_furniture(layout.parter_rooms)
    gf = place_furniture(layout.pietro_rooms)
    print("parter meble:", [(f.piece_type, f.room_id) for f in pf])
    print("pietro meble:", [(f.piece_type, f.room_id) for f in gf])
    out = OUT / "sfh_furnished.png"
    render_two_storey(layout, parter_furniture=pf, pietro_furniture=gf,
                      title=f"Dom jednorodzinny 2-kond. + meble — obrys {w}x{h} m",
                      save_path=out, show=False)
    print("->", out)


if __name__ == "__main__":
    main()
