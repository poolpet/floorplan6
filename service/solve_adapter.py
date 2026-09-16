"""Żądanie JSON → obrys (zaznaczenie / punkt / polygon) → solver → kontrakt JSON."""
from __future__ import annotations

from shapely.geometry import Polygon

# Importy na górze modułu (nie lazy): paleta i testy podmieniają je monkeypatchem
# jako atrybuty tego modułu. `bridge.boundary_reader` ciągnie pakiet `archicad`.
from bridge.boundary_reader import read_boundary_from_archicad, read_boundary_from_point
from core.house_layout import generate_house
from core.plan_contract import house_to_contract, plan_to_contract
from core.variant_generator import generate_variants

APARTMENT_TYPES = ("M1", "M2", "M3", "M4", "M5")


def _float(v, what: str) -> float:
    """Koercja na float z polskim komunikatem błędu."""
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} musi być liczbą.") from None


def _int_field(req: dict, key: str, default: int) -> int:
    """Pole opcjonalne jako int; JSON null = 'nie podano' → default."""
    v = req.get(key, default)
    if v is None:
        v = default
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError(f"Pole '{key}' musi być liczbą całkowitą.") from None


def _float_field(req: dict, key: str, default: float) -> float:
    """Pole opcjonalne jako float; JSON null = 'nie podano' → default."""
    v = req.get(key, default)
    if v is None:
        v = default
    return _float(v, f"Pole '{key}'")


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
    what = "Punkt wejścia 'entry'"
    return _float(e[0], what), _float(e[1], what)


def auto_type_for_area(area_m2: float) -> str:
    """Typ mieszkania sugerowany z pola obrysu (paleta pokazuje go jako 'Auto')."""
    if area_m2 < 45:
        return "M1"
    if area_m2 < 65:
        return "M2"
    if area_m2 < 85:
        return "M3"
    if area_m2 < 110:
        return "M4"
    return "M5"


def _boundary_from_source(req: dict):
    """(polygon, entry, wall_types) ze źródła podanego w żądaniu."""
    source = req.get("source", "polygon")
    if source == "polygon":
        return _polygon(req), _entry(req), req.get("wall_types")
    if source == "selection":
        return read_boundary_from_archicad()
    if source == "point":
        pt = req.get("point")
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValueError("Field 'point' must be a pair [x, y].")
        return read_boundary_from_point(_float(pt[0], "point.x"), _float(pt[1], "point.y"))
    raise ValueError("Field 'source' must be 'selection', 'point' or 'polygon'.")


def _boundary_info(poly: Polygon, entry) -> dict:
    """Obrys dla podglądu w palecie — bez solve'a (Load outline)."""
    return {"polygon": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
            "entry": [float(entry[0]), float(entry[1])],
            "area": round(poly.area, 2),
            "auto_type": auto_type_for_area(poly.area)}


def _remember(store, req: dict, entry: dict) -> None:
    """Obiekty planów do ResultStore — /export wstawia je bez deserializacji kontraktu."""
    job_id = req.get("_job_id")
    if store is not None and job_id:
        store.put(job_id, entry)


def solve_request(req: dict, progress=None, store=None) -> dict:
    mode = req.get("mode")
    if mode not in ("apartment", "house"):
        raise ValueError("Pole 'mode' musi być 'apartment' albo 'house'.")
    poly, entry, wall_types = _boundary_from_source(req)
    boundary = _boundary_info(poly, entry)
    # Koercja PRZED wywołaniem solvera — złe wejście nie może odpalić liczenia.
    max_variants = _int_field(req, "max_variants", 5)
    if max_variants == 0:
        return {"mode": mode, "boundary": boundary, "variants": []}

    if mode == "house":
        layout = generate_house(poly, entry, num_storeys=_int_field(req, "num_storeys", 2))
        if not getattr(layout, "ok", True):
            raise RuntimeError(getattr(layout, "message", "") or "No layout for this outline.")
        _remember(store, req, {"mode": "house", "boundary": boundary, "layout": layout})
        return {"mode": "house", "boundary": boundary,
                "variants": [{"index": 0, "score": None, "contract": house_to_contract(layout)}]}

    mtype = req.get("mtype") or boundary["auto_type"]
    if mtype not in APARTMENT_TYPES:
        raise ValueError(f"Typ mieszkania musi być jednym z {', '.join(APARTMENT_TYPES)}.")
    min_score = _float_field(req, "min_score", 0.0)
    plans = generate_variants(
        poly, entry, mtype, max_variants,
        progress_callback=progress,
        wall_types=wall_types,
        template_filter=req.get("template_filter"),
        min_score=min_score,
    )
    _remember(store, req, {"mode": "apartment", "boundary": boundary, "plans": plans})
    variants = [{"index": i, "score": p.score,
                 "contract": plan_to_contract(p.rooms, p.boundary, storey="single", template=p.template),
                 "validation_errors": list(p.validation_errors)}
                for i, p in enumerate(plans)]
    return {"mode": "apartment", "boundary": boundary, "variants": variants}
