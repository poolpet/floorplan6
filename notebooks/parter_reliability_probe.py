"""Sonda S30 v5: niezawodność garażowych parterów PO netto/brutto + sąsiedztwach
korpusowych (główna ścieżka generate_house, sam parter).

Tło: przed zmianą parter ≥120 m² gross (10 pokoi, hol-gwiazda 7) = loteria
pierwszego rozwiązania (raz FEASIBLE @22 s, częściej UNKNOWN @120 s).
Po zmianie: hol dotyka 5, garaż przez wiatrołap, capy gross-owe (cap/0.81).

Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter_reliability_probe.py
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _gross_config, _reserve_core, parter_template_for
from core.house_program import default_house_config

CASES = [
    ("Tracja 15.9x9.9", 15.9, 9.9),
    ("13x10", 13.0, 10.0),
]
REPS = 3
LIMIT = 60.0


def run_case(label, W, H):
    poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    entry = (W / 2, 0.0)
    boundary = analyze_boundary(poly, entry_point=entry)
    core = _reserve_core(boundary.bbox, entry, force_straight=True)
    tpl = parter_template_for(poly.area)
    cfg = _gross_config(default_house_config(storey="parter"))
    for i in range(REPS):
        t0 = time.monotonic()
        r = solve_cpsat(tpl, boundary, time_limit_s=LIMIT,
                        reserved_core=core, program_config=cfg,
                        stair_room_id="schody", hub_at_entry=True,
                        l_capable_ids={"hub"}, entry_room_id="wiatrolap")
        dt = time.monotonic() - t0
        rooms = ""
        if r.rooms:
            rooms = "  " + ", ".join(f"{rm.spec.id}={rm.area:.1f}" for rm in r.rooms)
        print(f"[{label:16s} #{i}] status={r.status:9s} wall={dt:5.1f}s{rooms}",
              flush=True)


if __name__ == "__main__":
    for label, W, H in CASES:
        run_case(label, W, H)
