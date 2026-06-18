"""Benchmark podobieństwa do WZORCOWYCH rzutów Dawida (S28).

Wejście: notebooks/reference_plans.json — ground-truth wyekstrahowany (vision) z PDF-ów
(rzuty/domy, docelowo też schematics/dataset_raw): obrys + pokoje(+m²) + sąsiedztwa +
wejście + schody + open-plan, per kondygnacja.

Dla każdego wzorca: generator dostaje TEN obrys (parterowiec albo dom 2-kond. wg tego,
czy projekt ma parę parter+poddasze) i mierzymy bliskość do wzorca:
  - zestaw pokoi (F1 po typach, multiset — liczy się liczba sypialni),
  - powierzchnie dopasowanych pokoi (średnie |odchylenie| %),
  - graf sąsiedztw (Jaccard po krawędziach na dopasowanych typach),
  - strona wejścia / typ schodów / open-plan (zgodność).
Wynik: tabela per wzorzec + score zbiorczy. Rendery → rzuty/benchmark/.

Uruchomienie:  PYTHONPATH=. venv/bin/python notebooks/reference_benchmark.py [plans.json]
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from shapely.geometry import Polygon

from core.house_layout import generate_house
from viz.house_preview import render_house_figure
from viz.plan_renderer import render_floor_plan
from core.models import FloorPlan

OUT = Path("rzuty/benchmark")
OUT.mkdir(parents=True, exist_ok=True)

# generator-id → typ wzorca (mapped_id z ekstrakcji)
GEN_TO_REF = {
    "salon": "salon", "kuchnia": "kuchnia", "jadalnia": "jadalnia",
    "lazienka": "lazienka", "wc": "wc", "hub": "hol", "wiatrolap": "wiatrolap",
    "garderoba": "garderoba", "kotlownia": "kotlownia", "spizarnia": "spizarnia",
    "pralnia": "pralnia", "schody": "schody", "gabinet": "gabinet",
}


def _gen_room_type(rid: str, is_master: bool) -> str:
    base = rid.split("_")[0]
    if base == "sypialnia":
        return "master_sypialnia" if is_master else "sypialnia"
    return GEN_TO_REF.get(base, base)


def _ref_room_type(r: dict) -> str:
    t = r["mapped_id"]
    return {"podest": "hol"}.get(t, t)  # podest≈hol (komunikacja kondygnacji)


def _room_multiset(types: list[str]) -> Counter:
    return Counter(types)


def room_set_f1(gen: Counter, ref: Counter) -> float:
    tp = sum((gen & ref).values())
    if tp == 0:
        return 0.0
    prec = tp / sum(gen.values())
    rec = tp / sum(ref.values())
    return 2 * prec * rec / (prec + rec)


def area_deviation(gen_rooms, ref_rooms) -> tuple[float, int]:
    """Średnie |odchylenie|% UDZIAŁU powierzchni (area/Σareas kondygnacji) na pokojach
    dopasowanych po typie. Udziały, nie m² wprost: wzorce podają powierzchnie NETTO
    (suma pokoi ≈80% obrysu — grubość ścian), generator pokrywa 100% obrysu —
    bezwzględne m² miałyby systematyczny błąd ~+20%. Zwraca (mape_pct, n_matched)."""
    tot_gen = sum(a for _, a in gen_rooms) or 1.0
    tot_ref = sum(a for _, a in ref_rooms) or 1.0
    by_type_gen: dict[str, list[float]] = {}
    for t, a in gen_rooms:
        by_type_gen.setdefault(t, []).append(a / tot_gen)
    by_type_ref: dict[str, list[float]] = {}
    for t, a in ref_rooms:
        by_type_ref.setdefault(t, []).append(a / tot_ref)
    devs = []
    for t, ref_shares in by_type_ref.items():
        gen_shares = sorted(by_type_gen.get(t, []), reverse=True)
        for rs, gs in zip(sorted(ref_shares, reverse=True), gen_shares):
            if rs > 0:
                devs.append(abs(gs - rs) / rs * 100.0)
    return (sum(devs) / len(devs) if devs else 100.0), len(devs)


def room_iou(gen_typed_polys, ref_typed_polys):
    """Średni IoU pokoi dopasowanych po TYPIE. Argumenty: list[(type, shapely.Polygon)].
    Dla każdego pokoju WZORCA bierze najlepszy nakładający się generowany pokój tego
    samego typu (greedy, bez wykluczania — diagnostyka). None gdy brak dopasowań.
    Tylko dla wzorców z REALNĄ geometrią (refs_geo vector_traced = tropie)."""
    from collections import defaultdict
    gen_by_type = defaultdict(list)
    for t, p in gen_typed_polys:
        if p is not None:
            gen_by_type[t].append(p)
    ious = []
    for t, rp in ref_typed_polys:
        if rp is None:
            continue
        best = 0.0
        for gp in gen_by_type.get(t, []):
            uni = rp.union(gp).area
            if uni > 0:
                best = max(best, rp.intersection(gp).area / uni)
        if gen_by_type.get(t):
            ious.append(best)
    return sum(ious) / len(ious) if ious else None


def adjacency_jaccard(gen_edges: set, ref_edges: set) -> float:
    if not ref_edges:
        return 1.0
    inter = len(gen_edges & ref_edges)
    union = len(gen_edges | ref_edges)
    return inter / union if union else 1.0


STAIR_KIND_NORM = {"u": "u_winder", "straight": "straight"}


def stair_kind_match(gen_stair_kind: str, has_schody: bool, storeys: int, ref_kind) -> dict:
    """Zgodność typu schodów generator↔wzorzec (diagnostyka, waga 0 w score).

    Generator zwraca 'u'/'straight' → normalizujemy 'u'→'u_winder'. Parterowiec
    (storeys==1 bez pokoju 'schody') traktujemy jako 'none' (wzorce parterowca mają
    stairs.kind='none'). Zwraca {gen, ref, match}.
    """
    if storeys == 1 and not has_schody:
        gen = "none"
    else:
        gen = STAIR_KIND_NORM.get(gen_stair_kind, gen_stair_kind)
    return {"gen": gen, "ref": ref_kind, "match": 1.0 if gen == ref_kind else 0.0}


def _gen_edges(rooms) -> set:
    """Krawędzie sąsiedztwa wygenerowanego układu (po TYPACH, wspólna krawędź ≥0.9 m)."""
    # master = największa sypialnia
    syp = [r for r in rooms if r.spec.id.startswith("sypialnia")]
    master_id = max(syp, key=lambda r: r.area).spec.id if syp else None
    types = {r.spec.id: _gen_room_type(r.spec.id, r.spec.id == master_id) for r in rooms}
    edges = set()
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a.polygon is None or b.polygon is None:
                continue
            if a.polygon.boundary.intersection(b.polygon.boundary).length >= 0.9 - 1e-6:
                ta, tb = types[a.spec.id], types[b.spec.id]
                if ta != tb:
                    edges.add(tuple(sorted((ta, tb))))
    return edges


def _ref_edges(ref_rooms: list[dict]) -> set:
    name_to_type = {r["name_pl"]: _ref_room_type(r) for r in ref_rooms}
    edges = set()
    for r in ref_rooms:
        for adj in r.get("adjacent_rooms", []) or []:
            tb = name_to_type.get(adj)
            ta = _ref_room_type(r)
            if tb and ta != tb:
                edges.add(tuple(sorted((ta, tb))))
    return edges


def _outline_polygon(ref: dict) -> Polygon | None:
    o = ref["outline"]
    w, h = o.get("width_m"), o.get("height_m")
    if o.get("shape") == "rectangle" and w and h:
        return Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    if w and h:  # nie-prostokąt: na razie bbox (TODO: L z wymiarów)
        return Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    # fallback: prostokąt o polu = area i proporcji 1.5 (jak layout_suite)
    area = o.get("area_m2")
    if not area:
        return None
    import math
    h = math.sqrt(area / 1.5)
    return Polygon([(0, 0), (1.5 * h, 0), (1.5 * h, h), (0, h)])


ENTRY = {"south": lambda W, H: (W / 2, 0.0), "north": lambda W, H: (W / 2, H),
         "west": lambda W, H: (0.0, H / 2), "east": lambda W, H: (W, H / 2),
         "unknown": lambda W, H: (W / 2, 0.0)}


def _storey_rooms(ref_storey: dict) -> list[tuple[str, float]]:
    return [(_ref_room_type(r), float(r["area_m2"])) for r in ref_storey["rooms"]
            if _ref_room_type(r) not in ("taras", "garaz", "other")]


def _ref_f1_types(ref_storey: dict) -> list[str]:
    """Typy pokoi wzorca dla room-set F1. W ODRÓŻNIENIU od `_storey_rooms` (MAPE)
    LICZY `garaz` — przynależność do zestawu jest pewna, choć POLE garażu w tabelach
    bywa niepewne/brak (dlatego MAPE go wyklucza). Bez schody/taras/other (jak F1)."""
    return [_ref_room_type(r) for r in ref_storey["rooms"]
            if _ref_room_type(r) not in ("taras", "schody", "other")]


def score_project(project: dict, time_limit: float) -> dict:
    """project: {"name", "parter": <plan-json>, "poddasze": <plan-json|None>}"""
    name = project["name"]
    ref_p = project["parter"]
    ref_g = project.get("poddasze")
    poly = _outline_polygon(ref_p)
    if poly is None:
        return {"name": name, "status": "NO-OUTLINE"}
    W, H = poly.bounds[2], poly.bounds[3]
    entry = ENTRY[ref_p["entry"]["side"]](W, H)
    storeys = 2 if ref_g else 1
    t0 = time.time()
    lay = generate_house(poly, entry_point=entry, num_storeys=storeys, time_limit_s=time_limit)
    dt = time.time() - t0
    if not lay.ok:
        return {"name": name, "status": f"FAIL ({lay.message[:60]})", "t": dt}

    res = {"name": name, "status": "OK", "t": dt, "storeys": storeys}
    pairs = [("parter", ref_p, lay.parter_rooms)]
    if ref_g:
        pairs.append(("poddasze", ref_g, lay.pietro_rooms))
    # Master = największa sypialnia w CAŁYM domu (nie per-kondygnacja): inaczej
    # jedyna sypialnia_parter parteru fałszywie stałaby się 'master' (S30c).
    all_rooms = lay.parter_rooms + (lay.pietro_rooms if ref_g else [])
    all_syp = [r for r in all_rooms if r.spec.id.startswith("sypialnia")]
    master_id = max(all_syp, key=lambda r: r.area).spec.id if all_syp else None
    f1s, mapes, jacs = [], [], []
    for storey, ref, rooms in pairs:
        gen_typed = [(_gen_room_type(r.spec.id, r.spec.id == master_id), r.area) for r in rooms]
        ref_typed = _storey_rooms(ref)
        # schody wykluczone z F1 (ekstrakcja wzorców nie listuje ich jako pokój,
        # jak garaz/other) — inaczej nasz pokój schody zaniża precyzję.
        # B1: F1 liczy garaz przez _ref_f1_types (przynależność); MAPE zostaje na
        # ref_typed (_storey_rooms — garaz wykluczony, pole niepewne).
        f1 = room_set_f1(_room_multiset([t for t, _ in gen_typed if t != "schody"]),
                         _room_multiset(_ref_f1_types(ref)))
        mape, nm = area_deviation(gen_typed, ref_typed)
        jac = adjacency_jaccard(_gen_edges(rooms), _ref_edges(ref["rooms"]))
        res[storey] = {"room_f1": round(f1, 3), "area_mape_pct": round(mape, 1),
                       "n_matched": nm, "adj_jaccard": round(jac, 3)}
        f1s.append(f1); mapes.append(mape); jacs.append(jac)
    # Diagnostyka stair_kind (waga 0 w score) — waliduje winder default (S31b).
    # entry_side POMINIĘTY: benchmark wstrzykuje ref.side jako entry_point (line 167) →
    #   match byłby tautologią; realny wymaga zwrotu ZREALIZOWANEJ strony z generate_house.
    # open_plan POMINIĘTY: generator trzyma osobny pokój 'kuchnia' (rysowany open-plan),
    #   wzorce mają aneks (brak 'kuchnia') → proxy zawsze mismatch = różnica reprezentacji.
    has_schody = any(r.spec.id == "schody" for r in lay.parter_rooms)
    res["stair_kind"] = stair_kind_match(lay.stair_kind, has_schody, storeys,
                                         (ref_p.get("stairs") or {}).get("kind"))
    # score 0-100: pokoje 50% + powierzchnie 30% (100%→0 pkt przy MAPE≥50%) + sąsiedztwa 20%
    f1m = sum(f1s) / len(f1s); mapem = sum(mapes) / len(mapes); jacm = sum(jacs) / len(jacs)
    res["score"] = round(100 * (0.5 * f1m + 0.3 * max(0.0, 1 - mapem / 50.0) + 0.2 * jacm), 1)

    # render do oceny wzrokowej
    if storeys == 2:
        render_house_figure(lay, with_furniture=False, title=f"BENCH {name}",
                            save_path=OUT / f"{name}.png", show=False)
    else:
        plan = FloorPlan(boundary=lay.boundary, template=None, rooms=lay.parter_rooms)
        render_floor_plan(plan, title=f"BENCH {name}", save_path=OUT / f"{name}.png", show=False)
    return res


def main():
    plans_path = Path(sys.argv[1] if len(sys.argv) > 1 else "notebooks/reference_plans.json")
    data = json.loads(plans_path.read_text())
    results = [score_project(p, time_limit=float(data.get("time_limit_s", 60.0)))
               for p in data["projects"]]
    print(f"\n{'wzorzec':28s} {'status':28s} {'score':>5s}  szczegóły")
    print("-" * 110)
    for r in results:
        det = []
        for st in ("parter", "poddasze"):
            if st in r:
                d = r[st]
                det.append(f"{st}: F1={d['room_f1']} MAPE={d['area_mape_pct']}% adj={d['adj_jaccard']}")
        if "stair_kind" in r:
            sk = r["stair_kind"]
            det.append(f"stair={sk['gen']}/{sk['ref']}={sk['match']:.0f}")
        print(f"{r['name']:28s} {r['status']:28s} {r.get('score', '—'):>5}  {' | '.join(det)}")
    scored = [r["score"] for r in results if "score" in r]
    if scored:
        print(f"\nŚREDNI SCORE: {sum(scored)/len(scored):.1f}/100  ({len(scored)}/{len(results)} wygenerowanych)")
    print(f"Rendery → {OUT}/")


if __name__ == "__main__":
    main()
