"""Seria testów układu na najpowszechniejszych polskich obrysach (archon.pl itp.).

Czyta suite z JSON: {"outlines":[{label,kind,width_m,height_m,expected_program,...}],
"room_targets":[{room,typical_m2,max_m2,min_m2}]}. Dla każdego obrysu generuje rzut
(mieszkanie wg suggest_mtype / dom 1- lub 2-kond.), renderuje do rzuty/suite/, i OCENIA
pokoje względem wzorców (flaguje przekroczenia max / poniżej min / złą liczbę sypialni).
Bez AC — czysty matplotlib. Służy do STROJENIA algorytmu pod realne, popularne układy.

    PYTHONPATH=. venv/bin/python notebooks/layout_suite.py [suite.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from shapely.geometry import Polygon

from core.variant_generator import generate_variants
from core.template_selector import suggest_mtype
from core.furniture import furnish_rooms
from core.house_layout import generate_house
from viz.plan_renderer import render_floor_plan
from viz.house_preview import render_house_figure

OUT = Path("rzuty/suite")
OUT.mkdir(parents=True, exist_ok=True)
APT_FALLBACK = ["M2", "M3", "M4", "M1", "M5"]


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-zĄąĆćĘꣳŃńÓ󌜏źŻż-]+", "_", s)[:50]


def _dims(o) -> tuple[float, float]:
    """Prostokąt o powierzchni = area_m2 z zadaną proporcją (footprint, nie surowe w×h —
    syntetyk mieszał bbox z usable dla domów)."""
    aspect = (o["width_m"] / o["height_m"]) if o.get("height_m") else 1.3
    h = (o["area_m2"] / aspect) ** 0.5
    return round(o["area_m2"] / h, 2), round(h, 2)


def _bed_count(expected_program: str) -> int | None:
    m = re.search(r"(\d+)\s*sypial", expected_program.lower())
    return int(m.group(1)) if m else None


def _target_for(room_id: str, targets: dict) -> tuple | None:
    key = room_id.split("_")[0]
    if "master" in room_id or "glown" in room_id or "główn" in room_id:
        return targets.get("master") or targets.get("sypialnia")
    return targets.get(key) or (targets.get("sypialnia") if "sypial" in room_id else None)


def _evaluate(rooms, expected_beds, targets) -> tuple[int, list[str]]:
    flags, nbed = [], 0
    for r in rooms:
        if r.polygon is None:
            continue
        if "sypial" in r.spec.id:
            nbed += 1
        a = r.polygon.area
        t = _target_for(r.spec.id, targets)
        if t:
            if a > t["max_m2"] + 3:
                flags.append(f"{r.spec.id}={a:.0f}>max{t['max_m2']:.0f}")
            elif a < t["min_m2"] - 1.5:
                flags.append(f"{r.spec.id}={a:.0f}<min{t['min_m2']:.0f}")
    if expected_beds is not None and nbed != expected_beds:
        flags.append(f"sypialnie {nbed}≠oczek.{expected_beds}")
    return nbed, flags


def _run_apartment(o, targets, idx):
    w, h = _dims(o)
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    # Wejście: realny lokal z korytarza ma drzwi POZA centrum krótkiej ściany (hol idzie
    # w narożnik), NIE w martwym środku. Dla wąskich obrysów (krótki bok < 6.5 m) kładziemy
    # drzwi off-center (~20% szerokości, min 0.9 m od rogu). Szersze = front-center.
    entry_x = max(0.9, w * 0.2) if min(w, h) < 6.5 else w / 2
    entry = (entry_x, 0.0)
    mt0 = suggest_mtype(poly.area)
    for mt in [mt0] + [m for m in APT_FALLBACK if m != mt0]:
        try:
            plans = generate_variants(poly, entry, mt, max_variants=1)
        except Exception:
            continue
        if plans:
            plan = plans[0]
            fr = furnish_rooms(plan.rooms, plan.boundary)
            render_floor_plan(plan, title=f"{o['label']} {poly.area:.0f}m² MIESZKANIE {mt}",
                              save_path=OUT / f"{idx}_{_slug(o['label'])}_apt_{mt}.png", show=False,
                              furniture=fr.furniture)
            nbed, flags = _evaluate(plan.rooms, _bed_count(o["expected_program"]), targets)
            status = "OK ✓" if not flags else " | ".join(flags)
            print(f"  MIESZKANIE {mt} ({nbed} syp): {status}")
            return
    print("  MIESZKANIE: INFEASIBLE")


def _run_house(o, targets, idx, storeys):
    w, h = _dims(o)
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    try:
        lay = generate_house(poly, entry_point=(w / 2, 0.0),
                             num_storeys=storeys, time_limit_s=45.0)
    except Exception as e:
        print(f"  DOM {storeys}-kond.: BŁĄD ({str(e)[:50]})")
        return
    if not getattr(lay, "ok", False):
        print(f"  DOM {storeys}-kond.: INFEASIBLE ({getattr(lay,'message','')[:50]})")
        return
    render_house_figure(lay, with_furniture=True,
                        title=f"{o['label']} {poly.area:.0f}m² DOM {storeys}-kond.",
                        save_path=OUT / f"{idx}_{_slug(o['label'])}_dom{storeys}.png", show=False)
    rooms = list(getattr(lay, "parter_rooms", []) or []) + list(getattr(lay, "pietro_rooms", []) or [])
    nbed, flags = _evaluate(rooms, _bed_count(o["expected_program"]), targets)
    status = "OK ✓" if not flags else " | ".join(flags)
    print(f"  DOM {storeys}-kond. ({nbed} syp): {status}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/suite.json"
    suite = json.loads(Path(path).read_text())
    targets = {t["room"]: t for t in suite.get("room_targets", [])}
    print(f"SUITE: {len(suite['outlines'])} obrysów; {len(targets)} wzorców pokoi\n")
    for idx, o in enumerate(suite["outlines"]):
        print(f"[{idx}] {o['label']} — {o['kind']} {o['width_m']}×{o['height_m']} "
              f"({o['area_m2']:.0f}m²) — oczek.: {o['expected_program']}")
        if o["kind"] == "apartment":
            _run_apartment(o, targets, idx)
        elif o["kind"] == "house_1storey":
            _run_house(o, targets, idx, 1)
        else:
            _run_house(o, targets, idx, 2)
        print()
    print(f"GOTOWE → {OUT}/  (renders + ocena vs wzorce)")


if __name__ == "__main__":
    main()
