"""Nieinwazyjny: wczytaj ZAZNACZONE obrysy z AC (read-only), wygeneruj rozkład +
meble i wyrenderuj OFFLINE (matplotlib) dwa panele per obrys (renderer vs AC-geometria
extract_furniture). Pozwala ocenić bieżący kod na TWOICH realnych kształtach (trapez,
L) bez śmieci nałożonych w dokumencie AC z ~100 poprzednich runów.

Uruchom z AC + Tapir, MAJĄC ZAZNACZONE obrysy:
    PYTHONPATH=. venv/bin/python notebooks/ac_outlines_render.py
NIC nie wstawia do AC. Zapisuje PNG do rzuty/diag/real_*.png + drukuje flagi.
"""
from __future__ import annotations

from shapely.affinity import translate

from core.variant_generator import generate_variants
from notebooks.ac_export_multi import _collect_outlines, _guid
from notebooks.furniture_export_check import analyze, render_case

MTYPE_FALLBACK = ["M3", "M2", "M4", "M1", "M5"]


def main():
    print("Read-only render zaznaczonych obrysów — łączę z AC ...")
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}")
        return

    selected = tapir.get_selected_elements()
    if not selected:
        print("Brak zaznaczenia.")
        return
    guids = [_guid(e) for e in selected]
    details = tapir.get_element_details(guids)
    outlines, mode = _collect_outlines(tapir, details, guids)
    print(f"Tryb: {mode}; obrysów: {len(outlines)}\n")

    for polygon, entry, wall_types, label in outlines:
        bx0, by0, bx1, by1 = polygon.bounds
        shifted = translate(polygon, -bx0, -by0)
        entry_s = (entry[0] - bx0, entry[1] - by0)
        plan = used = None
        for mtype in MTYPE_FALLBACK:
            try:
                plans = generate_variants(shifted, entry_s, mtype,
                                          max_variants=1, wall_types=wall_types)
            except Exception as e:
                print(f"  {label} {mtype}: {e}")
                continue
            if plans:
                plan, used = plans[0], mtype
                break
        if plan is None:
            print(f"=== {label} ({polygon.area:.1f} m²): POMINIĘTY (INFEASIBLE) ===\n")
            continue
        fr, objs, rows, kf = analyze(plan.rooms)
        path = render_case(f"real_{label}_{used}", plan.rooms, rows, objs, fr, kf)
        floats = sum(1 for r in rows if r["FLOAT"])
        print(f"=== {label} → {used} ({polygon.area:.1f} m²): {len(objs)} mebli, "
              f"pływa/AXIS/OUT={floats}, brak-kuchni={kf} ===")
        for r in rows:
            if r["FLOAT"]:
                print(f"    FLOAT: {r['room']}/{r['piece']} AXIS={r['AXIS']} OUT={r['OUT']} DRIFT={r['DRIFT']}")
        print(f"    → {path}")
    print("\nGotowe — panele w rzuty/diag/real_*.png (LEWO renderer / PRAWO AC-geometria).")


if __name__ == "__main__":
    main()
