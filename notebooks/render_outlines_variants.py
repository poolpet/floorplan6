"""Renderuje KAŻDY zaznaczony obrys z AC w DWÓCH wariantach: MIESZKANIE (M-typ wg
powierzchni) oraz DOM 2-KONDYGNACYJNY (parter + piętro) — matplotlib, BEZ wstawiania
do AC. Do porównania jakości układu na realnych obrysach Dawida.

Uruchom z AC + Tapir, MAJĄC ZAZNACZONE ściany obrysów:
    PYTHONPATH=. venv/bin/python notebooks/render_outlines_variants.py
Wyniki → rzuty/dawid_variants/*.png
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

from pathlib import Path
from shapely.affinity import translate

from core.variant_generator import generate_variants
from core.template_selector import suggest_mtype
from core.furniture import furnish_rooms
from core.house_layout import generate_house
from viz.plan_renderer import render_floor_plan
from viz.house_preview import render_house_figure
from notebooks.ac_export_multi import _collect_outlines, _guid

OUT = Path("rzuty/dawid_variants")
OUT.mkdir(parents=True, exist_ok=True)
APT_FALLBACK = ["M2", "M3", "M4", "M1", "M5"]


def _render_apartment(shifted, entry_s, area, label, idx):
    mt0 = suggest_mtype(area)
    tries = [mt0] + [m for m in APT_FALLBACK if m != mt0]
    for mt in tries:
        try:
            plans = generate_variants(shifted, entry_s, mt, max_variants=1)
        except Exception as e:  # noqa: BLE001
            continue
        if plans:
            plan = plans[0]
            fr = furnish_rooms(plan.rooms, plan.boundary)
            nbed = sum(1 for r in plan.rooms if "sypialnia" in r.spec.id)
            p = OUT / f"{idx}_{label}_MIESZKANIE_{mt}.png"
            render_floor_plan(plan, title=f"{label} {area:.0f} m² — MIESZKANIE {mt} ({nbed} syp.)",
                              save_path=p, show=False, furniture=fr.furniture)
            print(f"    MIESZKANIE → {mt} ({nbed} syp.)  {p.name}")
            return
    print(f"    MIESZKANIE → INFEASIBLE (żaden M-typ nie wszedł)")


def _render_house(shifted, entry_s, area, label, idx):
    try:
        lay = generate_house(shifted, entry_point=entry_s, num_storeys=2, time_limit_s=30.0)
    except Exception as e:  # noqa: BLE001
        print(f"    DOM 2-kond. → BŁĄD ({str(e)[:60]})")
        return
    if not getattr(lay, "ok", False):
        print(f"    DOM 2-kond. → INFEASIBLE ({getattr(lay,'message','')[:60]})")
        return
    p = OUT / f"{idx}_{label}_DOM_2kond.png"
    render_house_figure(lay, with_furniture=True,
                        title=f"{label} {area:.0f} m² — DOM 2-KONDYGNACYJNY",
                        save_path=p, show=False)
    print(f"    DOM 2-kond. → {p.name}")


def main():
    print("RENDER wariantów (mieszkanie + dom) z obrysów AC — łączę ...")
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    tapir.connect()
    print(f"  Połączono port {tapir.active_port}")

    sel = tapir.get_selected_elements()
    keep = [_guid(e) for e in sel if _guid(e)]
    if not keep:
        print("BRAK ZAZNACZENIA — zaznacz ściany obrysów i powtórz.")
        return
    details = tapir.get_element_details(keep)
    outlines, mode = _collect_outlines(tapir, details, keep)
    print(f"  Zaznaczenie: {len(keep)} elem; tryb={mode}; obrysów: {len(outlines)}\n")

    for idx, (poly, entry, wall_types, label) in enumerate(outlines):
        bx0, by0, bx1, by1 = poly.bounds
        shifted = translate(poly, -bx0, -by0)
        entry_s = (entry[0] - bx0, entry[1] - by0)
        area = poly.area
        print(f"[{idx}] {label}  {area:.0f} m²  ({bx1-bx0:.1f}×{by1-by0:.1f})")
        _render_apartment(shifted, entry_s, area, label, idx)
        _render_house(shifted, entry_s, area, label, idx)

    print(f"\nGOTOWE → {OUT}/  (mieszkanie + dom dla każdego obrysu)")


if __name__ == "__main__":
    main()
