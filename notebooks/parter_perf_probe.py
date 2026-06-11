"""Sonda perf parteru (S28) — ground truth + ablacja komponentów modelu.

Parter ≥~130 m² = UNKNOWN @120 s (S27). Mierzymy: (a) czy w ogóle FEASIBLE i kiedy
(t=600), (b) który komponent modelu odpowiada za blowup (ablacja po jednym),
(c) czy samo znalezienie PIERWSZEGO rozwiązania jest wolne (stop_after_first).
Sekwencyjnie — CP-SAT i tak bierze 8 workerów.
"""
import time

from ortools.sat.python import cp_model
from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _reserve_core, _template
from core.house_program import default_house_config

PARTER = _template("house_parter")
CFG = default_house_config(storey="parter")


def parter_solve(W, H, t, first_only=False, **overrides):
    poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    entry = (W / 2, 0.0)
    b = analyze_boundary(poly, entry_point=entry)
    core = _reserve_core(b.bbox, entry, force_straight=True)
    kw = dict(time_limit_s=t, reserved_core=core, program_config=CFG,
              stair_room_id="schody", hub_at_entry=True,
              l_capable_ids={"hub"}, entry_room_id="wiatrolap")
    kw.update(overrides)

    orig = cp_model.CpSolver.solve
    if first_only:
        def patched(self, model, *a, **k):
            self.parameters.stop_after_first_solution = True
            return orig(self, model, *a, **k)
        cp_model.CpSolver.solve = patched
    t0 = time.time()
    try:
        r = solve_cpsat(PARTER, b, **kw)
    finally:
        cp_model.CpSolver.solve = orig
    return r.status, time.time() - t0


def run(label, W, H, t, first_only=False, **overrides):
    status, dt = parter_solve(W, H, t, first_only=first_only, **overrides)
    print(f"{label:48s} {W}x{H}  -> {status:10s} {dt:6.1f}s", flush=True)


if __name__ == "__main__":
    print("=== GROUND TRUTH (pelny model) ===", flush=True)
    run("baseline t=600", 13, 10, 600.0)

    print("=== ABLACJA @120 s (13x10) ===", flush=True)
    run("bez L-hub (l_capable=None)", 13, 10, 120.0, l_capable_ids=None)
    run("bez entry-pin (entry_room_id=None)", 13, 10, 120.0, entry_room_id=None)
    run("bez pinu schodow (core=None, stair=None)", 13, 10, 120.0,
        reserved_core=None, stair_room_id=None)
    run("bez hub_at_entry", 13, 10, 120.0, hub_at_entry=False)
    run("stop_after_first_solution", 13, 10, 120.0, first_only=True)

    print("=== TRACJA 15.9x9.9 ===", flush=True)
    run("baseline t=600", 15.9, 9.9, 600.0)
