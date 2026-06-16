"""Densyfikacja — CZYSTY diagnostyk room-setu vs wzorce (BEZ CP-SAT).

Teza S31b: realny driver bloatu (MAPE) = sparse room-set. Gdy kondygnacja ma dużo
powierzchni, ale MAŁO pokoi, capy się nasycają, a remainder F1 (`unabsorbed_leftover`)
ląduje na nielicznych pokojach (∝rozmiar sink) → puchną → udziały rozjeżdżają się
vs wzorzec.

Ten skrypt liczy WIERNIE to, co solver dostaje jako CEL: dla każdego projektu
replikuje dobór room-setu z selektorów `house_layout` (BEZ solve'a) → `compute_house_targets`
(= dokładnie objective solvera, `cpsat_solver.py:732`) → predykcja UDZIAŁÓW → ta sama
`area_deviation` co benchmark = PREDICTED-MAPE per kondygnacja. Plus:
  - liczba pokoi nasza (selektor) vs wzorzec (benchmark-view),
  - GAP typów (których typów wzorzec ma WIĘCEJ → cel densyfikacji),
  - `unabsorbed_leftover` (ile m² remainder F1 pompuje sink-pool = bloat),
  - F1 (room-set) — ta sama metryka co score.

To zamienia densyfikację z „zgadnij + 20-min benchmark/wariant" w „policz wariant w
sekundę". Finalni zwycięzcy walidowani realnym benchmarkiem.

Uruchomienie:  PYTHONPATH=. venv/bin/python notebooks/densyfikacja_diag.py [plans.json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from core.house_layout import (
    _gross_config, _template, attic_effective_area, net_area,
    parter_room_ids, pietro_room_ids, single_storey_room_ids,
)
from core.house_program import (
    compute_house_targets, default_house_config, unabsorbed_leftover,
)
from notebooks.reference_benchmark import (
    _gen_room_type, _outline_polygon, _storey_rooms, area_deviation,
    room_set_f1, _room_multiset,
)


def _select_floor(project: dict):
    """Replikuje generate_house (PRIMARY, bez fallbacków perf) → per kondygnacja:
    (storey, specs, usable_m2, cfg). storeys=1 → tylko parter (single)."""
    ref_p = project["parter"]
    ref_g = project.get("poddasze")
    poly = _outline_polygon(ref_p)
    if poly is None:
        return None
    area = poly.area
    if ref_g is None:
        tpl = _template("house_single_storey")
        keep = set(single_storey_room_ids(tpl.pokoje, area))
        specs = [p for p in tpl.pokoje if p.id in keep]
        cfg = default_house_config(storey="single", master_id="sypialnia_1")
        return [("parter", specs, area, cfg)]
    # 2-kond.: budżet sypialni na poziomie domu (S30c)
    eff = attic_effective_area(poly)
    p_tpl = _template("house_parter")
    g_tpl = _template("house_pietro")
    old_beds = sum(1 for r in pietro_room_ids(g_tpl.pokoje, eff, bedroom_offset=0)
                   if r.startswith("sypialnia"))
    parter_bedroom = old_beds >= 2
    offset = 1 if parter_bedroom else 0
    p_keep = set(parter_room_ids(p_tpl.pokoje, net_area(area), parter_bedroom))
    g_keep = set(pietro_room_ids(g_tpl.pokoje, eff, bedroom_offset=offset))
    p_specs = [p for p in p_tpl.pokoje if p.id in p_keep]
    g_specs = [p for p in g_tpl.pokoje if p.id in g_keep]
    p_cfg = _gross_config(default_house_config(storey="parter"))
    g_cfg = _gross_config(default_house_config(storey="poddasze", master_id="sypialnia_1"))
    return [("parter", p_specs, area, p_cfg), ("poddasze", g_specs, area, g_cfg)]


def _master_id(floors_targets):
    """Master = największa sypialnia (po TARGET) w całym domu (jak score_project)."""
    syp = []
    for _st, targets in floors_targets:
        for rid, t in targets.items():
            if rid.startswith("sypialnia"):
                syp.append((rid, t))
    return max(syp, key=lambda kv: kv[1])[0] if syp else None


def diag_project(project: dict) -> dict | None:
    sel = _select_floor(project)
    if sel is None:
        return None
    # 1) targety per kondygnacja
    floors = []
    for storey, specs, usable, cfg in sel:
        targets = compute_house_targets(specs, usable, cfg)
        left = unabsorbed_leftover(specs, usable, cfg)
        floors.append((storey, specs, usable, cfg, targets, left))
    master = _master_id([(st, t) for st, _sp, _u, _c, t, _l in floors])

    out = {"name": project["name"], "floors": []}
    for storey, specs, usable, cfg, targets, left in floors:
        ref = project[storey]
        gen_typed = [(_gen_room_type(rid, rid == master), targets[rid]) for rid in targets]
        ref_typed = _storey_rooms(ref)
        gen_ms = _room_multiset([t for t, _ in gen_typed if t != "schody"])
        ref_ms = _room_multiset([t for t, _ in ref_typed if t != "schody"])
        f1 = room_set_f1(gen_ms, ref_ms)
        mape, nm = area_deviation(gen_typed, ref_typed)
        missing = ref_ms - gen_ms      # typy, których wzorzec ma WIĘCEJ → densyfikacja
        excess = gen_ms - ref_ms       # nasze typy ponad wzorzec (np. garaz, osobna kuchnia)
        out["floors"].append({
            "storey": storey, "usable": round(usable, 1),
            "n_gen": sum(gen_ms.values()), "n_ref": sum(ref_ms.values()),
            "f1": round(f1, 3), "pred_mape": round(mape, 1),
            "leftover": round(left, 1),
            "missing": dict(missing), "excess": dict(excess),
            "gen_rooms": sorted(gen_ms.elements()),
            "ref_rooms": sorted(ref_ms.elements()),
        })
    return out


def main():
    plans_path = Path(sys.argv[1] if len(sys.argv) > 1 else "notebooks/reference_plans_full.json")
    data = json.loads(plans_path.read_text())
    results = [r for r in (diag_project(p) for p in data["projects"]) if r]

    print(f"\n{'projekt':12s} {'kond':9s} {'usable':>6s} {'pok g/r':>7s} "
          f"{'F1':>5s} {'pMAPE':>6s} {'left':>5s}  brakujące(densyfikacja) / nadmiar")
    print("-" * 118)
    agg_left = []
    for r in results:
        for i, f in enumerate(r["floors"]):
            miss = ",".join(f"{k}×{v}" for k, v in f["missing"].items()) or "—"
            exc = ",".join(f"{k}×{v}" for k, v in f["excess"].items()) or "—"
            name = r["name"] if i == 0 else ""
            print(f"{name:12s} {f['storey']:9s} {f['usable']:>6.0f} "
                  f"{f['n_gen']:>3d}/{f['n_ref']:<3d} {f['f1']:>5.2f} {f['pred_mape']:>5.0f}% "
                  f"{f['leftover']:>5.1f}  {miss}  |  {exc}")
            agg_left.append(f["leftover"])

    # podsumowanie: gdzie densyfikacja boli najbardziej
    print("\n=== KANDYDACI DENSYFIKACJI (leftover>2 m² LUB n_gen<n_ref) ===")
    flat = [(r["name"], f) for r in results for f in r["floors"]]
    flat.sort(key=lambda x: (x[1]["leftover"], x[1]["n_ref"] - x[1]["n_gen"]), reverse=True)
    for name, f in flat:
        if f["leftover"] > 2.0 or f["n_gen"] < f["n_ref"]:
            miss = ",".join(f"{k}×{v}" for k, v in f["missing"].items()) or "—"
            print(f"  {name:12s} {f['storey']:9s} leftover={f['leftover']:>5.1f} "
                  f"pok {f['n_gen']}/{f['n_ref']}  pMAPE={f['pred_mape']:.0f}%  brak: {miss}")
    print(f"\nΣ leftover (bloat pompowany na sink): {sum(agg_left):.0f} m² na {len(agg_left)} kondygnacjach")
    print(f"Średni predicted-MAPE: {sum(f['pred_mape'] for _n, f in flat)/len(flat):.1f}%")


if __name__ == "__main__":
    main()
