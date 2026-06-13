"""Sonda S30c — KANDYDAT NA FIX: parter 8 pokoi = sypialnia_parter + łazienka, BEZ
spiżarni. Hipoteza: 9 pokoi (z spiżarnią) = loteria; 8 (bez spiżarni, z sypialnią) =
niezawodny, a realizm headline (sypialnia+łazienka na parterze) dowieziony. Spiżarnia
to najmniej istotny pokój — poświęcamy ją na rzecz bedroom + perf.

Footprinty: 11×8 (88, modalny) i 12.9×8.7 (a2-6, 112 gross). Po 4 biegi @60s.
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter8_bedroom_probe.py
"""
from __future__ import annotations

import time
from dataclasses import replace

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _gross_config, _reserve_core, parter_template_for
from core.house_program import default_house_config

LIMIT = 60.0
CASES = [("11x8 (88)", 11.0, 8.0), ("12.9x8.7 (112)", 12.9, 8.7)]


def _tpl_no_spizarnia(poly):
    tpl = parter_template_for(poly.area, with_parter_bedroom=True)
    keep = [p for p in tpl.pokoje if p.id != "spizarnia"]
    sas = [r for r in tpl.sasiedztwo if "spizarnia" not in (r.room_a, r.room_b)]
    return replace(tpl, pokoje=keep, sasiedztwo=sas)


def run(label, W, H):
    poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    entry = (W / 2, 0.0)
    boundary = analyze_boundary(poly, entry_point=entry)
    core = _reserve_core(boundary.bbox, entry, force_straight=True)
    tpl = _tpl_no_spizarnia(poly)
    cfg = _gross_config(default_house_config(storey="parter"))
    n = len(tpl.pokoje)
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=LIMIT,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    entry_room_id="wiatrolap", external_bathroom_id="lazienka",
                    l_capable_ids={"hub"})
    dt = time.monotonic() - t0
    print(f"[{label:16s}] {r.status:11s} {dt:5.1f}s  ({n} pokoi)", flush=True)


if __name__ == "__main__":
    print(f"Parter z sypialnią BEZ spiżarni, limit {LIMIT}s")
    for label, W, H in CASES:
        for i in range(4):
            run(f"{label} #{i}", W, H)
