"""Sonda S30: które rozmieszczenie rdzenia klatki w L-domu jest FEASIBLE.

Opus (Task 2) odkrył: rdzeń flush na wklęsłym narożniku (pozioma) tworzy z notchem
barierę → parter INFEASIBLE. Stary (notch-nieświadomy) był feasible dla TEGO L.
Mierzymy kilka rozmieszczeń, by oprzeć decyzję Dawida na dowodach.

L: bbox 12×10, notch dolny-prawy [7.5,12]×[0,4] (102 m²). Parter 8 pokoi (bez garażu).
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/lcore_placement_probe.py
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _gross_config, parter_template_for
from core.house_program import default_house_config

W, H, NW, NH = 12.0, 10.0, 4.5, 4.0
POLY = Polygon([(0, 0), (W - NW, 0), (W - NW, NH), (W, NH), (W, H), (0, H)])
ENTRY = (6.0, 10.0)  # północ, główna bryła

# Rozmieszczenia rdzenia (cx, cy, sw, sh) bbox-relative:
PLACEMENTS = {
    "inner-corner-H (Task1)": (3.3, 4.0, 4.2, 1.1),   # flush, pozioma — Opus: INFEASIBLE
    "inner-corner-V":          (6.4, 4.0, 1.1, 4.2),   # pionowa wzdłuż ściany notcha, w górę
    "main-wing-left-V":        (0.0, 4.0, 1.1, 4.2),   # pionowa przy lewej ścianie, lita bryła
    "crossbar-top-H":          (0.0, 8.9, 4.2, 1.1),   # pozioma u góry (stary-podobny, z dala od notcha)
    "junction-offset-V":       (6.4, 4.5, 1.1, 4.2),   # pionowa, odsunięta 0.5 od krawędzi notcha
}


def run(label, core):
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    tpl = parter_template_for(POLY.area)
    cfg = _gross_config(default_house_config(storey="parter"))
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=45.0,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    l_capable_ids={"hub"}, entry_room_id="wiatrolap")
    dt = time.monotonic() - t0
    print(f"[{label:24s}] {r.status:11s} {dt:5.1f}s  core={core}", flush=True)


if __name__ == "__main__":
    print(f"L {W}×{H} − notch {NW}×{NH} = {POLY.area:.0f} m², parter 8 pokoi")
    for label, core in PLACEMENTS.items():
        run(label, core)
