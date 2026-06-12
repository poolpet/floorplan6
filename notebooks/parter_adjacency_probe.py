"""Sonda S30 v4 (diagnoza, nie fix): sąsiedztwa wg KORPUSU na dużym parterze.

Hipoteza: krawędź solvera ≥120 m² to nie wydajność szukania, tylko topologia
szablonu — hol musi dotykać 7 pokoi (w tym garaż/kotłownia/gabinet), podczas gdy
realny parter ~121 m² z korpusu (AR.02.1) ma hol 3.2 m² dotykający 4 pomieszczeń:
garaż wchodzi przez PRZEDSIONEK, schowek/kuchnia przez salon.

Wariant korpusowy (TYLKO w tej sondzie — szablon na dysku nietknięty):
  hub: wiatrołap, schody, salon, wc, gabinet   (5 zamiast 7)
  garaż ↔ wiatrołap (przedsionek-śluza, korpus)
  kotłownia ↔ garaż (śluza techniczna)
  salon ↔ kuchnia (opening), kuchnia ↔ spiżarnia — bez zmian

Pomiar: 3 powtórzenia @60 s, zwykły solve (bez warm startu).
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter_adjacency_probe.py
"""
from __future__ import annotations

import time
from dataclasses import replace

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_layout import _filter_template, _reserve_core, _template, parter_room_ids
from core.house_program import default_house_config

W, H = 15.9, 9.9
POLY = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
ENTRY = (W / 2, 0.0)

CORPUS_ADJ = [
    ("wiatrolap", "_outside", "entry_door"),
    ("hub", "wiatrolap", "door"),
    ("hub", "schody", "door"),
    ("hub", "salon", "door"),
    ("hub", "wc", "door"),
    ("hub", "gabinet", "door"),
    ("garaz", "wiatrolap", "door"),
    ("kotlownia", "garaz", "door"),
    ("salon", "kuchnia", "opening"),
    ("kuchnia", "spizarnia", "door"),
]


def corpus_template():
    tpl = _template("house_parter")
    tpl = _filter_template(tpl, set(parter_room_ids(tpl.pokoje, POLY.area)))
    proto_rule = tpl.sasiedztwo[0]
    rules = [replace(proto_rule, room_a=a, room_b=b, connection_type=c)
             for a, b, c in CORPUS_ADJ]
    return replace(tpl, sasiedztwo=rules)


def run(label, tpl, limit=60.0):
    boundary = analyze_boundary(POLY, entry_point=ENTRY)
    core = _reserve_core(boundary.bbox, ENTRY, force_straight=True)
    cfg = default_house_config(storey="parter")
    t0 = time.monotonic()
    r = solve_cpsat(tpl, boundary, time_limit_s=limit,
                    reserved_core=core, program_config=cfg,
                    stair_room_id="schody", hub_at_entry=True,
                    l_capable_ids={"hub"}, entry_room_id="wiatrolap")
    dt = time.monotonic() - t0
    rooms = ""
    if r.rooms:
        rooms = "  " + ", ".join(f"{rm.spec.id}={rm.area:.1f}" for rm in r.rooms)
    print(f"[{label:14s}] status={r.status:9s} wall={dt:6.1f}s{rooms}", flush=True)


if __name__ == "__main__":
    tpl = corpus_template()
    for i in range(3):
        run(f"corpus-adj-{i}", tpl)
