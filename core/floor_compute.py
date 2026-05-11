"""
Etap 3 — pure helpers (bez CP-SAT) do obliczeń wstępnych.

Każda funkcja oparta o WT 2002 + nowelizację 2024-08-01.
Zobacz `docs/WT_PARAMETERS.md` po pełną tabelę parametrów z odnośnikami.
"""
from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon

from rules._loader import get_default_pack

_PACK = get_default_pack()
APARTMENT_MIN_AREA = _PACK.constants["apartment_min_area"]
APARTMENT_OPT_AREA = _PACK.constants["apartment_opt_area"]
WT_BUILDING_CLASS_THRESHOLDS = {
    "N": _PACK.constants["building_class"]["N_max_height_m"],
    "SW": _PACK.constants["building_class"]["SW_max_height_m"],
    "W": _PACK.constants["building_class"]["W_max_height_m"],
}
WT_STAIR_BIEG_WIDTH = _PACK.constants["wt_stair_bieg_width"]
WT_STAIR_SPOCZNIK_WIDTH = _PACK.constants["wt_stair_spocznik_width"]
WT_STAIR_GAP_BIEGS = _PACK.constants["wt_stair_gap_biegs"]
WT_STAIR_STEP_HEIGHT_MAX = _PACK.constants["wt_stair_step_height_max"]
WT_STAIR_BLONDEL = _PACK.constants["wt_stair_blondel"]
WT_STAIR_STEP_WIDTH_MIN = _PACK.constants["wt_stair_step_width_min"]
WT_ELEVATOR_HEIGHT_THRESHOLD = _PACK.constants["wt_elevator_height_threshold"]
WT_ELEVATOR_SHAFT_W = _PACK.constants["wt_elevator_shaft_w"]
WT_ELEVATOR_SHAFT_L = _PACK.constants["wt_elevator_shaft_l"]
WT_ELEVATOR_FIRE_W = _PACK.constants["wt_elevator_fire_w"]
WT_ELEVATOR_FIRE_L = _PACK.constants["wt_elevator_fire_l"]
WT_ELEVATOR_WALL_GAP = _PACK.constants["wt_elevator_wall_gap"]
WT_PRZEDSIONEK_DEPTH = _PACK.constants["wt_przedsionek_depth"]
WT_DOJSCIE_MAX_1KLATKA = _PACK.constants["wt_dojscie_max_1klatka"]
WT_DOJSCIE_MAX_2KLATKI = _PACK.constants["wt_dojscie_max_2klatki"]
FLOOR_RESERVE_RATIO = _PACK.constants["floor_reserve_ratio"]


def compute_building_class(height_total_m: float) -> str:
    """Klasa wysokości WT: N / SW / W / WW."""
    if height_total_m <= WT_BUILDING_CLASS_THRESHOLDS["N"]:
        return "N"
    if height_total_m <= WT_BUILDING_CLASS_THRESHOLDS["SW"]:
        return "SW"
    if height_total_m <= WT_BUILDING_CLASS_THRESHOLDS["W"]:
        return "W"
    return "WW"


def compute_stairwell_dimensions(
    floor_height_m: float,
    num_floors: int,
    bieg_width_m: float = WT_STAIR_BIEG_WIDTH,
    spocznik_width_m: float = WT_STAIR_SPOCZNIK_WIDTH,
    has_elevator: Optional[bool] = None,
) -> dict:
    """Wylicz wymiary klatki schodowej 2-biegowej + opcjonalnie szyb windy.

    Wzory:
    - n_steps = ceil(h / max_step_h), parzysta dla 2-biegowej
    - h_step = h / n_steps  (rzeczywista wysokość stopnia)
    - s_step = Blondel - 2*h_step  (szerokość komfortowa)
    - bieg_length = (n_steps/2) * s_step
    - klatka_length = bieg + spocznik
    - klatka_width = 2 * bieg_width + szyb (gap między biegami)
    - winda obowiązkowa gdy h_total > 9.5m (WT §54)
    - dla klasy SW+ dodaj przedsionek o głębokości wg klasy
    """
    h_total = num_floors * floor_height_m
    klasa = compute_building_class(h_total)

    if has_elevator is None:
        has_elevator = h_total > WT_ELEVATOR_HEIGHT_THRESHOLD

    n_steps_raw = floor_height_m / WT_STAIR_STEP_HEIGHT_MAX
    n_steps = max(2, math.ceil(n_steps_raw))
    if n_steps % 2 != 0:
        n_steps += 1

    h_step = floor_height_m / n_steps
    s_step = max(WT_STAIR_STEP_WIDTH_MIN, WT_STAIR_BLONDEL - 2 * h_step)

    bieg_length = (n_steps / 2) * s_step
    klatka_length = bieg_length + spocznik_width_m
    klatka_width = 2 * bieg_width_m + WT_STAIR_GAP_BIEGS

    elevator_dims = None
    if has_elevator:
        if klasa in ("W", "WW"):
            ew, el = WT_ELEVATOR_FIRE_W, WT_ELEVATOR_FIRE_L
        else:
            ew, el = WT_ELEVATOR_SHAFT_W, WT_ELEVATOR_SHAFT_L
        klatka_width += ew + WT_ELEVATOR_WALL_GAP
        elevator_dims = (ew, el)

    przedsionek_depth = WT_PRZEDSIONEK_DEPTH.get(klasa, 0.0)
    if przedsionek_depth > 0:
        klatka_length += przedsionek_depth

    return {
        "h_total_m": h_total,
        "building_class": klasa,
        "has_elevator": has_elevator,
        "elevator_dims_m": elevator_dims,
        "n_steps": n_steps,
        "step_height_m": round(h_step, 4),
        "step_width_m": round(s_step, 4),
        "bieg_length_m": round(bieg_length, 3),
        "stairwell_width_m": round(klatka_width, 3),
        "stairwell_length_m": round(klatka_length, 3),
        "stairwell_area_m2": round(klatka_width * klatka_length, 2),
        "przedsionek_depth_m": przedsionek_depth,
    }


def compute_max_dojscie(num_stairwells: int, has_dso: bool = False) -> float:
    """Max długość dojścia wg WT §256 (ZL IV).

    1 klatka: 10m (lub 20m z DSO).
    ≥2 klatki: 40m (lub 80m z DSO).
    """
    if num_stairwells <= 1:
        base = WT_DOJSCIE_MAX_1KLATKA
    else:
        base = WT_DOJSCIE_MAX_2KLATKI
    return base * 2.0 if has_dso else base


def compute_apartment_count(
    floor_area_m2: float,
    mix_pct: dict,
    reserve_ratio: float = FLOOR_RESERVE_RATIO,
) -> dict:
    """Auto-compute liczbę mieszkań per typ z mix% + powierzchni.

    Args:
        floor_area_m2: pole obrysu piętra
        mix_pct: {"M1": 0.10, "M2": 0.30, ...} — sumują się do 1.0
        reserve_ratio: rezerwa na komunikację (0.15 = 15%)

    Returns:
        dict z kluczami:
            usable_m2: pole dostępne dla mieszkań (po rezerwie)
            avg_area_per_apt: średnia powierzchnia mieszkania ważona mixem
            total_count: ile mieszkań łącznie
            per_type: {"M1": n1, "M2": n2, ...}
            actual_pct: faktyczne % po zaokrągleniach
    """
    usable = floor_area_m2 * (1.0 - reserve_ratio)
    avg_area = sum(APARTMENT_OPT_AREA[t] * pct for t, pct in mix_pct.items())
    if avg_area <= 0:
        return {"usable_m2": usable, "avg_area_per_apt": 0,
                "total_count": 0, "per_type": {}, "actual_pct": {}}

    total_count = max(1, round(usable / avg_area))
    per_type_raw = {t: total_count * pct for t, pct in mix_pct.items()}
    per_type = {t: round(v) for t, v in per_type_raw.items()}

    diff = total_count - sum(per_type.values())
    if diff != 0:
        biggest = max(per_type, key=lambda t: per_type_raw[t])
        per_type[biggest] += diff

    actual = {t: per_type[t] / total_count for t in per_type}
    return {
        "usable_m2": round(usable, 1),
        "avg_area_per_apt": round(avg_area, 1),
        "total_count": total_count,
        "per_type": per_type,
        "actual_pct": {t: round(p, 3) for t, p in actual.items()},
    }


def compute_min_stairwells(
    floor_polygon: Polygon,
    floor_height_m: float = 2.8,
    num_floors: int = 4,
    max_dojscie_m: float = WT_DOJSCIE_MAX_2KLATKI,
    n_apartments: int = 0,
    max_apartments_per_stair: int = 6,
) -> dict:
    """Auto-compute MIN liczbę klatek wymagana przez WT + geometrię + liczbę mieszkań.

    Reguły:
    - WT klasa: N=1 min, SW/W/WW=2 min
    - Geometryczna: diagonal / (2 × max_dojscie)
    - Capacity: N_apartments / max_apartments_per_stair (limit praktyczny:
      bez korytarza ~4 na klatkę, z korytarzem 6-8). Default 6 dla typowego wyniku.
    """
    h_total = num_floors * floor_height_m
    klasa = compute_building_class(h_total)

    bx0, by0, bx1, by1 = floor_polygon.bounds
    diagonal = math.hypot(bx1 - bx0, by1 - by0)
    n_geometric = max(1, math.ceil(diagonal / (2 * max_dojscie_m)))

    n_wt = {"N": 1, "SW": 2, "W": 2, "WW": 2}[klasa]

    n_capacity = max(1, math.ceil(n_apartments / max_apartments_per_stair)) if n_apartments > 0 else 1

    n_required = max(n_geometric, n_wt, n_capacity)
    return {
        "building_class": klasa,
        "diagonal_m": round(diagonal, 2),
        "n_geometric": n_geometric,
        "n_wt_min": n_wt,
        "n_capacity": n_capacity,
        "n_required": n_required,
    }
