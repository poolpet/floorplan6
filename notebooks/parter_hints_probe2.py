"""Sonda S30 v2: time-to-first + dwuetapowy warm-start (Tracja parter 157 m²).

Wynik v1: hinty zgadywane z targetów POGARSZAJĄ (UNKNOWN vs FEASIBLE baseline) —
szkic łamał twarde reguły (proporcje/minima/pin schodów), solver marnował budżet
na naprawę. v2 mierzy to, czego brakowało, i testuje warm-start bez zgadywania:

  A. baseline+cb   — dzisiejszy kod + callback: czas KAŻDEGO incumbenta,
  B. sat-only      — bez funkcji celu, stop po 1. rozwiązaniu (czysta wykonalność),
  C. two-stage     — etap 1 = B (≤30 s) → hint pełnym rozwiązaniem → etap 2 z celem,
  D. workers-12    — baseline na 12 workerach (mamy 12 P-rdzeni, kod używa 8).

Bez zmian w core/ — monkeypatch CpSolver.solve wyłącznie w tej sondzie.
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter_hints_probe2.py
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model
from shapely.geometry import Polygon

import core.cpsat_solver as cs
from core.boundary_analyzer import analyze_boundary
from core.house_layout import _filter_template, _reserve_core, _template, parter_room_ids
from core.house_program import default_house_config

TIME_LIMIT = 120.0
W, H = 15.94, 9.94
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)

_ORIG_SOLVE = cp_model.CpSolver.solve


class IncumbentLog(cp_model.CpSolverSolutionCallback):
    def __init__(self, t0):
        super().__init__()
        self.t0 = t0
        self.hits = []

    def on_solution_callback(self):
        self.hits.append((time.monotonic() - self.t0, self.objective_value))


def _run(label, patched_solve):
    """Odpala solve_cpsat z podmienionym CpSolver.solve; raportuje wynik."""
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    tpl = _template("house_parter")
    tpl = _filter_template(tpl, set(parter_room_ids(tpl.pokoje, POLY.area)))
    cfg = default_house_config(storey="parter")

    cp_model.CpSolver.solve = patched_solve
    try:
        t0 = time.monotonic()
        r = cs.solve_cpsat(tpl, boundary, time_limit_s=TIME_LIMIT,
                           reserved_core=core, program_config=cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap")
        dt = time.monotonic() - t0
    finally:
        cp_model.CpSolver.solve = _ORIG_SOLVE
    print(f"[{label:10s}] status={r.status:9s} wall={dt:6.1f}s", flush=True)
    return r


def variant_baseline_cb():
    def patched(self, model, callback=None):
        log = IncumbentLog(time.monotonic())
        st = _ORIG_SOLVE(self, model, log)
        traj = ", ".join(f"{t:.1f}s→{o:.0f}" for t, o in log.hits[:6])
        more = f" (+{len(log.hits) - 6})" if len(log.hits) > 6 else ""
        print(f"    incumbenty: {traj}{more}", flush=True)
        return st
    return patched


def variant_sat_only():
    def patched(self, model, callback=None):
        model.proto.ClearField("objective")
        self.parameters.stop_after_first_solution = True
        log = IncumbentLog(time.monotonic())
        st = _ORIG_SOLVE(self, model, log)
        traj = ", ".join(f"{t:.1f}s" for t, _ in log.hits)
        print(f"    sat-only pierwsze rozwiązanie: [{traj}]", flush=True)
        return st
    return patched


def variant_two_stage(stage1_limit=30.0):
    def patched(self, model, callback=None):
        proto = model.proto
        saved_obj = type(proto.objective)()
        saved_obj.CopyFrom(proto.objective)
        t0 = time.monotonic()

        # Etap 1: czysta wykonalność (bez celu), stop po pierwszym rozwiązaniu.
        proto.ClearField("objective")
        self.parameters.stop_after_first_solution = True
        self.parameters.max_time_in_seconds = stage1_limit
        st1 = _ORIG_SOLVE(self, model)
        dt1 = time.monotonic() - t0
        print(f"    etap1 (sat): {self.status_name(st1)} po {dt1:.1f}s", flush=True)
        if st1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            proto.objective.CopyFrom(saved_obj)
            self.parameters.stop_after_first_solution = False
            self.parameters.max_time_in_seconds = TIME_LIMIT - dt1
            return _ORIG_SOLVE(self, model, callback)

        # Etap 2: pełny cel + hint = KOMPLETNE rozwiązanie etapu 1 (per index).
        sol = list(self.response_proto.solution)
        proto.objective.CopyFrom(saved_obj)
        proto.ClearField("solution_hint")
        proto.solution_hint.vars.extend(range(len(sol)))
        proto.solution_hint.values.extend(sol)
        self.parameters.stop_after_first_solution = False
        self.parameters.max_time_in_seconds = max(5.0, TIME_LIMIT - dt1)
        log = IncumbentLog(time.monotonic())
        st2 = _ORIG_SOLVE(self, model, log)
        traj = ", ".join(f"{t:.1f}s→{o:.0f}" for t, o in log.hits[:6])
        more = f" (+{len(log.hits) - 6})" if len(log.hits) > 6 else ""
        print(f"    etap2 incumbenty: {traj}{more}", flush=True)
        return st2
    return patched


def variant_workers(n):
    def patched(self, model, callback=None):
        self.parameters.num_workers = n
        log = IncumbentLog(time.monotonic())
        st = _ORIG_SOLVE(self, model, log)
        traj = ", ".join(f"{t:.1f}s→{o:.0f}" for t, o in log.hits[:6])
        more = f" (+{len(log.hits) - 6})" if len(log.hits) > 6 else ""
        print(f"    incumbenty: {traj}{more}", flush=True)
        return st
    return patched


if __name__ == "__main__":
    _run("baseline", variant_baseline_cb())
    _run("sat-only", variant_sat_only())
    _run("two-stage", variant_two_stage())
    _run("workers-12", variant_workers(12))
