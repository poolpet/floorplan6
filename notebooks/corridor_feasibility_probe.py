"""Probe: czy parter modalnego domu @korytarz 1.2m jest INFEASIBLE czy tylko WOLNY?

Rozstrzyga projekt fallbacku (Dawid S31b: korytarz 1.2m default, wyjątkowo 1.0m).
Replikuje DOKŁADNIE setup parteru z house_layout._generate_two_storey i solvuje
przy corridor_min_cm = 120 vs 100, z HOJNYM czasem (120s) — patrzymy status +
czas-do-rozwiązania. INFEASIBLE → fallback konieczny; FEASIBLE-ale-wolny @>60s →
1.2m słuszny, problem to perf (nie relaksować pochopnie).

Uruchomienie:  PYTHONPATH=. venv/bin/python notebooks/corridor_feasibility_probe.py
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import (
    _gross_config, _reserve_core, _stair_core_dims, attic_low_strips,
    parter_template_for,
)
from core.house_program import default_house_config


def probe_parter(W, H, corridor_min_cm, t=120.0):
    poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    entry = (W / 2.0, 0.0)
    boundary = analyze_boundary(poly, entry_point=entry)
    core = _reserve_core(boundary.bbox, entry, notch=boundary.notch)
    parter_tpl = parter_template_for(poly.area, with_parter_bedroom=True)
    parter_cfg = _gross_config(default_house_config(storey="parter"))
    t0 = time.monotonic()
    r = solve_cpsat(parter_tpl, boundary, time_limit_s=t,
                    reserved_core=core, program_config=parter_cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                    external_bathroom_id="lazienka", corridor_min_cm=corridor_min_cm)
    dt = time.monotonic() - t0
    n_rooms = len(r.rooms) if r.rooms else 0
    return r.status, dt, n_rooms


def main():
    cases = [(11.0, 8.0), (12.0, 8.0), (10.0, 8.0)]
    print(f"{'obrys':>10s} {'corridor':>9s} {'status':>10s} {'czas':>7s} {'pokoi':>6s}")
    print("-" * 50)
    for W, H in cases:
        for cm in (120, 100):
            st, dt, n = probe_parter(W, H, cm)
            print(f"{W:.0f}x{H:.0f} ({W*H:.0f})".rjust(10)
                  + f"{cm/100:.1f}m".rjust(10)
                  + f"{st:>10s}{dt:>6.1f}s{n:>6d}")


if __name__ == "__main__":
    main()
