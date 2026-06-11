"""Tri-scenariusz (S28, prośba Dawida): każdy ZAZNACZONY obrys z AC wygenerowany
na 3 sposoby — (1) mieszkanie w bloku (M-typ wg powierzchni), (2) dom parterowy,
(3) dom piętrowy (poddasze knee-wall) — żeby porównać zachowanie algorytmu
w różnych scenariuszach na TYM SAMYM kształcie.

READ-ONLY (nic nie wstawia do AC). Rendery → rzuty/tri/, na końcu tabela statusów.

Z AC + Tapir (zaznacz obrysy: Zone/Slab albo zamknięte pętle ścian):
    PYTHONPATH=. venv/bin/python notebooks/ac_tri_scenarios.py
Offline smoke (3 syntetyczne obrysy, bez AC):
    PYTHONPATH=. venv/bin/python notebooks/ac_tri_scenarios.py --offline
Opcje: --time-limit 60 (s/kondygnację), --no-furniture
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from shapely.affinity import translate
from shapely.geometry import Polygon

from core.furniture import furnish_rooms
from core.house_layout import generate_house
from core.models import FloorPlan
from core.template_selector import suggest_mtype
from core.variant_generator import generate_variants
from viz.house_preview import render_house_figure
from viz.plan_renderer import render_floor_plan

OUT = Path("rzuty/tri")
OUT.mkdir(parents=True, exist_ok=True)

# fallback gdy M-typ z powierzchni okaże się INFEASIBLE na danym kształcie
MTYPE_FALLBACK = ["M3", "M2", "M4", "M1", "M5"]


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s)


def run_apartment(polygon, entry, wall_types, label, t, furniture):
    mtype0 = suggest_mtype(polygon.area)
    tried = [mtype0] + [m for m in MTYPE_FALLBACK if m != mtype0]
    for mtype in tried:
        try:
            plans = generate_variants(polygon, entry, mtype, max_variants=1,
                                      wall_types=wall_types)
        except Exception as e:
            return ("FAIL", f"{mtype}: {e}")
        if plans:
            plan = plans[0]
            fr = furnish_rooms(plan.rooms, plan.boundary) if furniture else None
            path = OUT / f"{label}_1_mieszkanie_{mtype}.png"
            render_floor_plan(plan, title=f"{label} — mieszkanie {mtype} ({polygon.area:.0f} m²)",
                              save_path=path, show=False,
                              furniture=fr.furniture if fr else None)
            note = f"{mtype}" + (" (fallback)" if mtype != mtype0 else "")
            return ("OK", f"{note}, pokoi {len(plan.rooms)} → {path.name}")
    return ("FAIL", f"INFEASIBLE dla {tried}")


def run_single_storey(polygon, entry, label, t, furniture):
    lay = generate_house(polygon, entry_point=entry, num_storeys=1, time_limit_s=t)
    if not lay.ok:
        return ("FAIL", lay.message)
    fr = furnish_rooms(lay.parter_rooms, boundary=lay.boundary) if furniture else None
    plan = FloorPlan(boundary=lay.boundary, template=None, rooms=lay.parter_rooms)
    path = OUT / f"{label}_2_parterowiec.png"
    render_floor_plan(plan, title=f"{label} — parterowiec ({polygon.area:.0f} m²)",
                      save_path=path, show=False,
                      furniture=fr.furniture if fr else None)
    return ("OK", f"pokoi {len(lay.parter_rooms)} → {path.name}")


def run_two_storey(polygon, entry, label, t, furniture):
    lay = generate_house(polygon, entry_point=entry, num_storeys=2, time_limit_s=t)
    if not lay.ok:
        return ("FAIL", lay.message)
    path = OUT / f"{label}_3_dom_pietrowy.png"
    attic = lay.attic_boundary.polygon.area if lay.attic_boundary is not None else None
    render_house_figure(lay, with_furniture=furniture,
                        title=f"{label} — dom z poddaszem ({polygon.area:.0f} m² + pas {attic:.0f} m²)",
                        save_path=path, show=False)
    n = len(lay.parter_rooms) + len(lay.pietro_rooms)
    return ("OK", f"pokoi {n} (poddasze-pas {attic:.0f} m²) → {path.name}")


def collect_from_ac():
    from bridge.tapir_connection import TapirConnection
    from notebooks.ac_export_multi import _collect_outlines, _guid
    tapir = TapirConnection()
    tapir.connect()
    print(f"Połączono z AC (port {tapir.active_port})")
    selected = tapir.get_selected_elements()
    if not selected:
        print("Brak zaznaczenia w AC."); return []
    guids = [_guid(e) for e in selected]
    details = tapir.get_element_details(guids)
    outlines, mode = _collect_outlines(tapir, details, guids)
    print(f"Tryb odczytu: {mode}; obrysów: {len(outlines)}")
    return outlines


def offline_outlines():
    """Syntetyczny smoke: 3 kontrastowe kształty (mały prostokąt / duży / L)."""
    rect = lambda w, h: Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    return [
        (rect(5.6, 7.9), (2.8, 0.0), None, "A_44m2_waski"),
        (rect(11, 8), (5.5, 0.0), None, "B_88m2"),
        (Polygon([(0, 0), (10, 0), (10, 8), (6, 8), (6, 5), (0, 5)]), (5.0, 0.0), None, "C_68m2_L"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--time-limit", type=float, default=60.0)
    ap.add_argument("--no-furniture", action="store_true")
    args = ap.parse_args()

    outlines = offline_outlines() if args.offline else collect_from_ac()
    if not outlines:
        sys.exit(1)
    furniture = not args.no_furniture

    rows = []
    for polygon, entry, wall_types, label in outlines:
        label = _slug(label)
        bx0, by0 = polygon.bounds[0], polygon.bounds[1]
        poly = translate(polygon, -bx0, -by0)            # jak flow GUI/AC: origin
        entry_s = (entry[0] - bx0, entry[1] - by0)
        print(f"\n=== {label} ({poly.area:.1f} m²) ===", flush=True)
        for scen, fn in (("mieszkanie", run_apartment),
                         ("parterowiec", run_single_storey),
                         ("dom piętrowy", run_two_storey)):
            t0 = time.time()
            if fn is run_apartment:
                status, info = fn(poly, entry_s, wall_types, label, args.time_limit, furniture)
            else:
                status, info = fn(poly, entry_s, label, args.time_limit, furniture)
            rows.append((label, f"{poly.area:.0f}", scen, status, info))
            print(f"  {scen:14s} {status:4s} {time.time()-t0:5.1f}s  {info}", flush=True)

    print("\n" + "=" * 78)
    print(f"{'obrys':24s} {'m²':>5s} {'scenariusz':14s} {'status':6s} info")
    print("-" * 78)
    for r in rows:
        print(f"{r[0]:24s} {r[1]:>5s} {r[2]:14s} {r[3]:6s} {r[4]}")
    print(f"\nRendery → {OUT}/")


if __name__ == "__main__":
    main()
