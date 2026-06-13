"""Sonda S30c: czy to OKNO sypialni_parter (F6 fasada), nie liczba pokoi, dusi
9-pokojowy parter? sypialnia_parter to NOCNA wymaga_okna=true → konkuruje o fasadę
z salonem+kuchnią. Test: ta sama konfiguracja, ale sypialnia_parter.wymaga_okna=False.

11×8 parter 9 pokoi, L-hol (obowiązkowy). Po 4 biegi each: (A) okno=true [obecne],
(B) okno=false. Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter9_window_probe.py
"""
from __future__ import annotations

import time
from dataclasses import replace

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import (
    _gross_config, _reserve_core, parter_template_for,
)
from core.house_program import default_house_config

W, H = 11.0, 8.0
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)
LIMIT = 90.0


def _tpl(window: bool):
    tpl = parter_template_for(POLY.area, with_parter_bedroom=True)
    if window:
        return tpl
    pokoje = [replace(p, wymaga_okna=False) if p.id == "sypialnia_parter" else p
              for p in tpl.pokoje]
    return replace(tpl, pokoje=pokoje)


def run(label, window):
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    tpl = _tpl(window)
    cfg = _gross_config(default_house_config(storey="parter"))
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=LIMIT,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    entry_room_id="wiatrolap", external_bathroom_id="lazienka",
                    l_capable_ids={"hub"})
    dt = time.monotonic() - t0
    print(f"[{label:22s}] {r.status:11s} {dt:5.1f}s", flush=True)


if __name__ == "__main__":
    print(f"11×8 parter 9 pokoi, limit {LIMIT}s")
    for i in range(4):
        run(f"A okno=true #{i}", True)
    for i in range(4):
        run(f"B okno=false #{i}", False)
