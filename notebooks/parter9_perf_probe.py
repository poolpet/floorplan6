"""Sonda S30c: czy 9-pokojowy parter (z sypialnia_parter) jest wykonalny szybciej
BEZ L-holu? Parter call używa l_capable_ids={"hub"} (drogi: opcjonalny 2. prostokąt
+ reifikowane styki). Może niepotrzebny gdy parter ma sypialnię (nie wąskie mieszkanie).

11×8 (88 m²), parter 9 pokoi. Po 3 biegi: (A) z L-holem [obecne], (B) bez L-holu.
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter9_perf_probe.py
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import (
    _gross_config, _reserve_core, attic_effective_area, parter_template_for,
)
from core.house_program import default_house_config

W, H = 11.0, 8.0
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)
LIMIT = 90.0


def run(label, l_capable):
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    tpl = parter_template_for(POLY.area, with_parter_bedroom=True)
    cfg = _gross_config(default_house_config(storey="parter"))
    ids = [p.id for p in tpl.pokoje]
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=LIMIT,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    entry_room_id="wiatrolap", external_bathroom_id="lazienka",
                    l_capable_ids=({"hub"} if l_capable else None))
    dt = time.monotonic() - t0
    print(f"[{label:18s}] {r.status:11s} {dt:5.1f}s  ({len(ids)} pokoi)", flush=True)


if __name__ == "__main__":
    print(f"11×8 parter 9 pokoi (sypialnia_parter), limit {LIMIT}s")
    for i in range(3):
        run(f"A L-hol #{i}", True)
    for i in range(3):
        run(f"B bez L-hol #{i}", False)
