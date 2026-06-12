"""Sonda S30 (HISTORYCZNA — wynik NEGATYWNY, nie uruchamiać):
parametr solution_hint usunięty z solve_cpsat po tej sondzie; hint zgadywany
z targetów POGARSZAŁ (UNKNOWN vs FEASIBLE baseline). Zwycięzca = warm_start
(dwuetapowy solve), patrz parter_hints_probe3.py.

Oryginalny opis: solution hints dla dużych parterów (Tracja-gross 157 m², 10 pokoi).

Krawędź solvera z S29: parter ≥~120 m² gross z garażem+gabinetem = UNKNOWN @120 s
niezależnie od formulacji pasm. Hipoteza z kolejki: solver dostaje targety tylko
jako widełki — bez punktu startu. Mierzymy 3 warianty (sekwencyjnie, bez kontencji):

  A. baseline           — dzisiejszy kod, bez hintu,
  B. size-only          — hint w/h z targetów (aspekt ~1.3), pozycje wolne,
  C. shelf-seed         — pełny szkic pasowy: usługi przy ścianie wejściowej,
                          strefa dzienna przy ogrodzie, schody = rdzeń.

Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter_hints_probe.py
"""
from __future__ import annotations

import math
import time

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _filter_template, _reserve_core, _template, parter_room_ids
from core.house_program import compute_house_targets, default_house_config

TIME_LIMIT = 120.0

# Tracja 6 — parter brutto (suite: 15.94×9.94, wejście południe-środek)
W, H = 15.94, 9.94
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)

# Pasy szkicu: kto przy wejściu (południe), kto przy ogrodzie (północ).
ENTRY_SHELF = ["garaz", "kotlownia", "wc", "wiatrolap", "hub", "garderoba"]
DAY_SHELF = ["salon", "jadalnia", "kuchnia", "spizarnia", "gabinet"]


def _prepare():
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    tpl = _template("house_parter")
    tpl = _filter_template(tpl, set(parter_room_ids(tpl.pokoje, POLY.area)))
    cfg = default_house_config(storey="parter")
    targets = compute_house_targets(tpl.pokoje, POLY.area, cfg)
    return boundary, core, tpl, cfg, targets


def seed_size_only(specs, targets):
    """Hint tylko w/h: prostokąt o polu targetu, aspekt 1.3, pozycje wolne."""
    hint = {}
    for s in specs:
        t = targets.get(s.id)
        if not t:
            continue
        w = math.sqrt(t * 1.3)
        hint[s.id] = (None, None, w, t / w)
    return hint


def seed_shelf(specs, targets, core):
    """Pełny szkic: 2 pasy na całą szerokość; szer. pokoju = target / wys. pasa.

    Szkic NIE musi być feasible (aspekty/minima mogą polec) — to tylko start.
    Schody nadpisane rdzeniem (pin i tak wymusza równość).
    """
    ids = {s.id for s in specs}
    entry_rooms = [r for r in ENTRY_SHELF if r in ids]
    day_rooms = [r for r in DAY_SHELF if r in ids]
    h_entry = sum(targets[r] for r in entry_rooms) / W
    h_entry = min(max(h_entry, 2.0), H - 3.0)
    h_day = H - h_entry

    hint = {}
    cx = 0.0
    for r in entry_rooms:
        rw = targets[r] / h_entry
        hint[r] = (cx, 0.0, rw, h_entry)
        cx += rw
    cx = 0.0
    for r in day_rooms:
        rw = targets[r] / h_day
        hint[r] = (cx, h_entry, rw, h_day)
        cx += rw
    if "schody" in ids:
        hint["schody"] = core  # (x, y, w, h) bbox-relative — zgodne z pinem
    return hint


def run(label, hint):
    boundary, core, tpl, cfg, _ = _prepare()
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=TIME_LIMIT,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                    solution_hint=hint)
    dt = time.monotonic() - t0
    rooms = ""
    if r.rooms:
        rooms = "  " + ", ".join(f"{rm.spec.id}={rm.area:.1f}" for rm in r.rooms)
    print(f"[{label:9s}] status={r.status:9s} wall={dt:6.1f}s{rooms}", flush=True)
    return r


if __name__ == "__main__":
    boundary, core, tpl, cfg, targets = _prepare()
    print(f"Tracja parter {W}×{H} = {POLY.area:.1f} m², pokoje: "
          f"{[s.id for s in tpl.pokoje]}")
    print(f"targety: {{ {', '.join(f'{k}: {v:.1f}' for k, v in targets.items())} }}")
    print(f"rdzeń schodów: {tuple(round(v, 2) for v in core)}")
    run("baseline", None)
    run("size-only", seed_size_only(tpl.pokoje, targets))
    run("shelf", seed_shelf(tpl.pokoje, targets, core))
