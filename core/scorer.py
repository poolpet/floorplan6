"""
Scoring jakości rzutu — Krok 7 algorytmu outside-in.

Score 0.0–1.0 z rozbiciem na składowe.
Wagi domyślne z config.py, docelowo optymalizowane z danych (RYZYKO 6).
"""
from __future__ import annotations

from core.models import FloorPlan, Room, Strefa
from config import (
    DEFAULT_SCORER_WEIGHTS,
    PROPORTION_OPTIMAL, PROPORTION_MAX,
    HUB_MIN_PERCENT, HUB_MAX_PERCENT,
    ORIENTATION_QUALITY,
)


def score(plan: FloorPlan) -> FloorPlan:
    """Oblicz score rzutu — wypełnij plan.score i plan.score_breakdown."""
    weights = DEFAULT_SCORER_WEIGHTS
    breakdown = {}

    breakdown["proporcje_pokoi"] = _score_proportions(plan)
    breakdown["efektywnosc_huba"] = _score_hub_efficiency(plan)
    breakdown["orientacja_salonu"] = _score_salon_orientation(plan)
    breakdown["powierzchnia_uzytkowa"] = _score_area_usage(plan)
    breakdown["separacja_stref"] = _score_zone_separation(plan)
    breakdown["regularnosc_geometrii"] = _score_geometry_regularity(plan)

    total = sum(
        weights.get(key, 0) * value
        for key, value in breakdown.items()
    )

    # Kary (score → 0) za krytyczne błędy
    if plan.validation_errors:
        total *= 0.3  # mocna kara za błędy walidacji

    plan.score = max(0.0, min(1.0, total))
    plan.score_breakdown = breakdown
    return plan


def _score_proportions(plan: FloorPlan) -> float:
    """Im bliżej optymalnej proporcji (1:1.3), tym lepiej."""
    scores = []
    for room in plan.rooms:
        if room.proportion <= 0:
            continue
        # Odchylenie od optimum
        deviation = abs(room.proportion - PROPORTION_OPTIMAL) / PROPORTION_OPTIMAL
        s = max(0.0, 1.0 - deviation)
        scores.append(s)
    return sum(scores) / len(scores) if scores else 0.5


def _score_hub_efficiency(plan: FloorPlan) -> float:
    """Hub powinien być 10-15% pow. i kompaktowy."""
    hub = plan.hub_room
    if hub is None:
        return 0.0

    pct = plan.hub_percent
    mtype = plan.template.typ_mieszkania
    min_pct = HUB_MIN_PERCENT.get(mtype, 0.10)
    max_pct = HUB_MAX_PERCENT

    # Score za procent powierzchni
    if min_pct <= pct <= max_pct:
        pct_score = 1.0
    elif pct < min_pct:
        pct_score = max(0.0, pct / min_pct)
    else:
        pct_score = max(0.0, 1.0 - (pct - max_pct) / 0.10)

    # Score za kompaktowość (proporcja bliska 1.0)
    compact_score = max(0.0, 1.0 - abs(hub.proportion - 1.0) / 1.5)

    return pct_score * 0.6 + compact_score * 0.4


def _score_salon_orientation(plan: FloorPlan) -> float:
    """Salon powinien mieć najlepszą orientację (S/SW/SE)."""
    # W MVP nie mamy przydziału orientacji per pokój — zwróć neutralne 0.7
    # TODO: użyć facade_segment_idx gdy wall_assigner go ustawi
    return 0.7


def _score_area_usage(plan: FloorPlan) -> float:
    """Im bliżej optymalnych proporcji strefowych, tym lepiej."""
    total = plan.usable_area
    if total <= 0:
        return 0.0

    # Sprawdź czy salon jest w rozsądnym zakresie
    salon = None
    for r in plan.rooms:
        if r.spec.strefa == Strefa.DZIENNA:
            salon = r
            break

    if salon is None:
        return 0.5

    salon_pct = salon.area / total
    # Optymalne: 35-55% (z danych)
    if 0.35 <= salon_pct <= 0.55:
        return 1.0
    elif 0.30 <= salon_pct <= 0.65:
        return 0.7
    return 0.4


def _score_zone_separation(plan: FloorPlan) -> float:
    """Strefa dzienna i nocna powinny być oddzielone hubem."""
    # Sprawdź bezpośrednie sąsiedztwa (z walidatora)
    # Jeśli nie ma warningów o sąsiedztwie → 1.0
    adjacency_warnings = [
        w for w in plan.validation_warnings
        if "sąsiedztwo" in w.lower() or "oddzielone hubem" in w.lower()
    ]
    if not adjacency_warnings:
        return 1.0
    return max(0.0, 1.0 - len(adjacency_warnings) * 0.3)


def _score_geometry_regularity(plan: FloorPlan) -> float:
    """Regularne prostokąty lepsze niż skomplikowane kształty.

    Nieregularne kształty (L, T) nie są koniecznie złe w prawdziwych rzutach,
    więc floor na 0.7 żeby nie karać nadmiernie.
    """
    scores = []
    for room in plan.rooms:
        if room.polygon is None:
            continue
        bounds = room.polygon.bounds
        bbox_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        if bbox_area > 0:
            regularity = max(room.area / bbox_area, 0.7)
        else:
            regularity = 0.7
        scores.append(regularity)
    return sum(scores) / len(scores) if scores else 0.5
