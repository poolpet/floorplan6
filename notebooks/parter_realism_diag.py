"""Diagnostyka S30c: GDZIE rozjeżdża się realizm PARTERU vs wzorce (benchmark map:
parter F1 0.33-0.75, MAPE 26-58% — najsłabszy punkt). Per wzorzec prostokątny:
porównanie zestawu pokoi i UDZIAŁÓW powierzchni (wzorzec vs nasz generator), z
wytknięciem pokoi DODANYCH przez nas i POMINIĘTYCH względem wzorca.

Grounding PRZED zmianą generatora (nie zgadywać). Reużywa helperów benchmarku.
Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/parter_realism_diag.py
"""
from __future__ import annotations

import json
from collections import Counter

from notebooks.reference_benchmark import (
    ENTRY, _gen_room_type, _outline_polygon, _storey_rooms,
)
from core.house_layout import generate_house

PLANS = "notebooks/reference_plans_rect7.json"


def shares(typed: list[tuple[str, float]]) -> dict[str, float]:
    """typ → udział % sumy powierzchni kondygnacji (agreguje pokoje tego samego typu)."""
    tot = sum(a for _, a in typed) or 1.0
    agg: dict[str, float] = {}
    for t, a in typed:
        agg[t] = agg.get(t, 0.0) + a
    return {t: 100.0 * a / tot for t, a in agg.items()}


def main():
    data = json.load(open(PLANS))
    tl = float(data.get("time_limit_s", 60.0))
    for proj in data["projects"]:
        ref_p = proj["parter"]
        poly = _outline_polygon(ref_p)
        W, H = poly.bounds[2], poly.bounds[3]
        entry = ENTRY[ref_p["entry"]["side"]](W, H)
        storeys = 2 if proj.get("poddasze") else 1
        lay = generate_house(poly, entry_point=entry, num_storeys=storeys, time_limit_s=tl)
        print(f"\n=== {proj['name']} ({ref_p['outline'].get('area_m2')} m² netto, "
              f"{W:.1f}×{H:.1f} brutto, {storeys}-kond.) ===", flush=True)
        if not lay.ok:
            print(f"  FAIL: {lay.message}", flush=True)
            continue
        # typowanie generatora (master = największa sypialnia)
        syp = [r for r in lay.parter_rooms if r.spec.id.startswith("sypialnia")]
        mid = max(syp, key=lambda r: r.area).spec.id if syp else None
        gen_typed = [(_gen_room_type(r.spec.id, r.spec.id == mid), r.area) for r in lay.parter_rooms]
        ref_typed = _storey_rooms(ref_p)
        gs, rs = shares(gen_typed), shares(ref_typed)
        gset, rset = Counter(t for t, _ in gen_typed), Counter(t for t, _ in ref_typed)
        all_types = sorted(set(gs) | set(rs))
        print(f"  {'typ':16s} {'WZORZEC %':>10s} {'NASZ %':>8s}  {'Δ':>6s}  uwaga")
        for t in all_types:
            rv, gv = rs.get(t), gs.get(t)
            d = (gv - rv) if (rv is not None and gv is not None) else None
            note = ""
            if rv is None:
                note = "DODANE przez nas"
            elif gv is None:
                note = "POMINIĘTE (jest we wzorcu)"
            elif gset[t] != rset[t]:
                note = f"liczba: wzorzec {rset[t]} / nasz {gset[t]}"
            rstr = f"{rv:8.1f}" if rv is not None else "       —"
            gstr = f"{gv:6.1f}" if gv is not None else "     —"
            dstr = f"{d:+6.1f}" if d is not None else "     —"
            print(f"  {t:16s} {rstr:>10s} {gstr:>8s}  {dstr:>6s}  {note}", flush=True)


if __name__ == "__main__":
    main()
