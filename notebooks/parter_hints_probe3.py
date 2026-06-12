"""Sonda S30 v3 (HISTORYCZNA — wynik NEGATYWNY, nie uruchamiać):
parametr warm_start usunięty z solve_cpsat po sondach S30. Dwuetapowy solve
(etap 1 sat-only / ±8% pól / wymuszony L-hol) NIE odblokował parteru 157 m² —
etap 1 sam był UNKNOWN @30 s; prostokątny hol = INFEASIBLE (dowód 0.3 s).
Wyniki + wnioski: docs/STATE.md S30 i komentarz fixture lay_tracja w
tests/test_house_roomset_scaling.py. Root cause = room-set z brutto
(kolejka netto/brutto), nie wydajność solvera.

Oryginalny opis: warm_start (dwuetapowy solve) na Tracja-parter 157 m².
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _filter_template, _reserve_core, _template, parter_room_ids
from core.house_program import default_house_config

W, H = 15.9, 9.9
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)


def run(label, warm, limit=120.0):
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    tpl = _template("house_parter")
    tpl = _filter_template(tpl, set(parter_room_ids(tpl.pokoje, POLY.area)))
    cfg = default_house_config(storey="parter")
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=limit,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                    warm_start=warm)
    dt = time.monotonic() - t0
    rooms = ""
    if r.rooms:
        rooms = "  " + ", ".join(f"{rm.spec.id}={rm.area:.1f}" for rm in r.rooms)
    print(f"[{label:12s}] status={r.status:9s} wall={dt:6.1f}s{rooms}", flush=True)


if __name__ == "__main__":
    run("warm-120", True)
    run("warm-60", True, limit=60.0)
    run("warm-45", True, limit=45.0)   # budżet suite — czy Tracja wejdzie do harnessu?
    run("baseline-120", False)
