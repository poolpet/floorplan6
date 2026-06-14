"""Sonda: czy U-rdzeń (schody ZABIEGOWE/2-biegowe, 2.4×2.4) jest feasible na obu
kondygnacjach domu 2-kond. teraz, gdy poddasze jest na PEŁNYM footprincie (knee-wall
v2, S29)? force_straight=True wymuszono w S27 bo U-rdzeń (2.4 m) zjadał połowę WĄSKIEGO
pasa poddasza — pas zniknął w S29, więc powód mógł odpaść. Dawid chce schody zabiegowe.

Po obrysie: (A) straight [obecne], (B) U/winder (force_straight=False).
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/winder_stair_probe.py
"""
from __future__ import annotations

import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import (
    _filter_template, _gross_config, _reserve_core, _stair_core_dims, _template,
    attic_effective_area, attic_low_strips, net_area, parter_template_for,
    parter_room_ids, pietro_room_ids,
)
from core.house_program import default_house_config

CASES = [("11x8 (88)", 11.0, 8.0), ("12.9x8.7 (112)", 12.9, 8.7), ("13x10 (130)", 13.0, 10.0)]
LIMIT = 60.0


def run(label, W, H, force_straight):
    poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    entry = (W / 2, 0.0)
    boundary = analyze_boundary(poly, entry_point=entry)
    sw, sh, kind = _stair_core_dims(W, H, force_straight=force_straight)
    core = _reserve_core(boundary.bbox, entry, force_straight=force_straight)
    eff = attic_effective_area(poly)
    old_beds = sum(1 for r in pietro_room_ids(_template("house_pietro").pokoje, eff, 0)
                   if r.startswith("sypialnia"))
    parter_bedroom = old_beds >= 2
    parter_tpl = parter_template_for(poly.area, with_parter_bedroom=parter_bedroom)
    pietro_tpl = _filter_template(_template("house_pietro"),
                                  set(pietro_room_ids(_template("house_pietro").pokoje, eff,
                                                      1 if parter_bedroom else 0)))
    pcfg = _gross_config(default_house_config(storey="parter"))
    gcfg = _gross_config(default_house_config(storey="poddasze", master_id="sypialnia_1"))
    bx0, by0 = boundary.bbox[0], boundary.bbox[1]
    low = [(s.bounds[0]-bx0, s.bounds[1]-by0, s.bounds[2]-bx0, s.bounds[3]-by0)
           for s in attic_low_strips(poly)]
    t0 = time.monotonic()
    rp = solve_cpsat(parter_tpl, boundary, time_limit_s=LIMIT, reserved_core=core,
                     program_config=pcfg, stair_room_id="schody", hub_at_entry=True,
                     l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                     external_bathroom_id="lazienka")
    rg = solve_cpsat(pietro_tpl, boundary, time_limit_s=LIMIT, reserved_core=core,
                     program_config=gcfg, stair_room_id="schody", hub_at_entry=False,
                     l_capable_ids={"hub"}, low_zones=low)
    dt = time.monotonic() - t0
    print(f"[{label:16s} {kind:8s} {sw}×{sh}] parter={rp.status:10s} poddasze={rg.status:10s} {dt:5.1f}s", flush=True)


if __name__ == "__main__":
    for label, W, H in CASES:
        run(label, W, H, force_straight=True)    # A: obecne (prosty)
        run(label, W, H, force_straight=False)   # B: U/zabiegowe
