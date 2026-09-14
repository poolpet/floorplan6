"""Żądanie JSON → generate_variants / generate_house → kontrakt JSON."""
from __future__ import annotations

from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.plan_contract import house_to_contract, plan_to_contract
from core.variant_generator import generate_variants

APARTMENT_TYPES = ("M1", "M2", "M3", "M4", "M5")


def _polygon(req: dict) -> Polygon:
    pts = req.get("polygon")
    if not isinstance(pts, list) or len(pts) < 3:
        raise ValueError("Obrys musi mieć co najmniej 3 punkty (pole 'polygon').")
    try:
        poly = Polygon([(float(x), float(y)) for x, y in pts])
    except (TypeError, ValueError):
        raise ValueError("Punkty obrysu muszą być parami liczb [x, y].")
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("Obrys jest niepoprawny (samoprzecięcia lub zerowe pole).")
    return poly


def _entry(req: dict) -> tuple[float, float]:
    e = req.get("entry")
    if not isinstance(e, (list, tuple)) or len(e) != 2:
        raise ValueError("Punkt wejścia 'entry' musi być parą [x, y].")
    return float(e[0]), float(e[1])


def solve_request(req: dict, progress=None) -> dict:
    mode = req.get("mode")
    if mode not in ("apartment", "house"):
        raise ValueError("Pole 'mode' musi być 'apartment' albo 'house'.")
    poly, entry = _polygon(req), _entry(req)

    if mode == "house":
        layout = generate_house(poly, entry, num_storeys=int(req.get("num_storeys", 2)))
        return {"mode": "house", "layout": house_to_contract(layout)}

    mtype = req.get("mtype")
    if mtype not in APARTMENT_TYPES:
        raise ValueError(f"Typ mieszkania musi być jednym z {', '.join(APARTMENT_TYPES)}.")
    plans = generate_variants(
        poly, entry, mtype, int(req.get("max_variants", 5)),
        progress_callback=progress,
        template_filter=req.get("template_filter"),
        min_score=float(req.get("min_score", 0.0)),
    )
    variants = []
    for p in plans:
        c = plan_to_contract(p.rooms, p.boundary, storey="single", template=p.template)
        c["score"] = p.score
        c["validation_errors"] = list(p.validation_errors)
        variants.append(c)
    return {"mode": "apartment", "variants": variants}
