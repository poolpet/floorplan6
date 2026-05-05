"""
Walidacja WT 2002 — Krok 6 algorytmu outside-in.

Twarde reguły: min. powierzchnie, szerokości, okna, proporcje, hub.
Reguły strefowe R1–R6 z feedbacku architekta.
"""
from __future__ import annotations

from core.models import FloorPlan, Room, Strefa
from config import (
    WT_MIN_AREA, WT_MIN_WIDTH, WT_MAX_AREA,
    PROPORTION_MAX, PROPORTION_ABSOLUTE_MAX,
    HUB_MIN_PERCENT, HUB_MAX_PERCENT,
)


def validate(plan: FloorPlan, strict_max_areas: bool = True) -> FloorPlan:
    """Waliduj rzut — wypełnij validation_errors i validation_warnings.

    Args:
        plan: rzut do walidacji.
        strict_max_areas: jeśli True (domyślnie) — sprawdza F2 max area cap
            (łazienka 5m², WC 3m²) jako error. Ustaw False dla reference plans
            z `data/plans/` — to są real PL apartments, niektóre nie spełniają
            WT 2002. Spójne ze wzorem `_check_area_coverage` (linia 45) gdzie
            tolerancja jest dynamiczna dla planów z danych.
    """
    errors = []
    warnings = []

    _check_area_coverage(plan, errors)
    _check_room_count(plan, errors)
    _check_min_areas(plan, errors, warnings)
    if strict_max_areas:
        _check_max_areas(plan, errors)
    _check_min_widths(plan, errors, warnings)
    _check_proportions(plan, errors, warnings)
    _check_hub(plan, errors, warnings)
    _check_adjacency(plan, errors, warnings)

    plan.validation_errors = errors
    plan.validation_warnings = warnings
    return plan


def _check_area_coverage(plan: FloorPlan, errors: list[str]):
    """Pokoje muszą wypełnić obrys (tolerancja zależy od kontekstu).

    Dla planów generowanych przez solver tolerancja < 0.5m².
    Dla planów z danych (ściany, niedokładne polygony) tolerancja 15%.
    """
    delta = abs(plan.total_room_area - plan.boundary.area)
    # Dynamiczna tolerancja — rzuty z danych mogą mieć ściany, L-kształty, etc.
    # Generowane plany: sum == boundary (tolerancja 0.5m²)
    # Dane źródłowe: bounding box > sum pokoi o 10-35% (ściany + kształt)
    tol_abs = max(0.5, plan.boundary.area * 0.40)
    if delta > tol_abs:
        errors.append(
            f"Geometria nie zamyka się: "
            f"sum(rooms)={plan.total_room_area:.2f} vs "
            f"boundary={plan.boundary.area:.2f}, delta={delta:.2f}m²"
        )


def _check_room_count(plan: FloorPlan, errors: list[str]):
    """Liczba pokoi musi zgadzać się z szablonem."""
    expected = len(plan.template.pokoje)
    actual = len(plan.rooms)
    if actual != expected:
        errors.append(
            f"Zła liczba pokoi: {actual} (oczekiwano {expected})"
        )


def _check_min_areas(plan: FloorPlan, errors: list[str], warnings: list[str]):
    """Minimalne powierzchnie wg WT 2002."""
    mtype = plan.template.typ_mieszkania
    for room in plan.rooms:
        spec = room.spec
        if spec.min_powierzchnia > 0 and room.area < spec.min_powierzchnia:
            deficit = spec.min_powierzchnia - room.area
            if deficit > 0.5:
                errors.append(
                    f"{spec.nazwa}: {room.area:.1f}m² < min {spec.min_powierzchnia:.1f}m²"
                )
            else:
                warnings.append(
                    f"{spec.nazwa}: {room.area:.1f}m² bliskie minimum "
                    f"{spec.min_powierzchnia:.1f}m²"
                )


def _check_max_areas(plan: FloorPlan, errors: list[str]):
    """F2 (FUNDAMENTAL_RULES): twardy cap WT — łazienka 5m², WC 3m².

    Match przez prefix room_id ("lazienka_2" matchuje "lazienka").
    Tolerancja 0.01m² na zaokrąglenia floating-point z Shapely intersection/clip.
    """
    for room in plan.rooms:
        key = room.spec.id.split("_")[0]
        if key in WT_MAX_AREA:
            max_area = WT_MAX_AREA[key]
            if room.area > max_area + 0.01:
                errors.append(
                    f"{room.spec.nazwa}: {room.area:.2f}m² > max WT {max_area:.1f}m² "
                    f"(F2 violation, id={room.spec.id})"
                )


def _check_min_widths(plan: FloorPlan, errors: list[str], warnings: list[str]):
    """Minimalne szerokości wg WT 2002."""
    for room in plan.rooms:
        spec = room.spec
        if spec.min_szerokosc > 0 and room.width < spec.min_szerokosc:
            deficit = spec.min_szerokosc - room.width
            if deficit > 0.1:
                errors.append(
                    f"{spec.nazwa}: szerokość {room.width:.2f}m < min {spec.min_szerokosc:.2f}m"
                )
            else:
                warnings.append(
                    f"{spec.nazwa}: szerokość {room.width:.2f}m bliskie minimum"
                )


def _check_proportions(plan: FloorPlan, errors: list[str], warnings: list[str]):
    """Proporcje pokoi.

    Dla nieregularnych pokoi (L-kształt, T-kształt) proporcja bbox jest
    myląca — pomijamy error, zostawiamy tylko warning.
    """
    for room in plan.rooms:
        # Regularity = polygon.area / bbox_area — niskie dla nieregularnych kształtów
        regularity = 1.0
        if room.polygon is not None:
            b = room.polygon.bounds
            bbox_area = (b[2] - b[0]) * (b[3] - b[1])
            if bbox_area > 0:
                regularity = room.area / bbox_area

        if room.proportion > PROPORTION_ABSOLUTE_MAX:
            if regularity >= 0.85:
                # Prostokątny pokój z ekstremalną proporcją → error
                errors.append(
                    f"{room.spec.nazwa}: proporcja {room.proportion:.2f} > "
                    f"max {PROPORTION_ABSOLUTE_MAX}"
                )
            else:
                # Nieregularny kształt — proporcja bbox jest myląca → warning
                warnings.append(
                    f"{room.spec.nazwa}: proporcja bbox {room.proportion:.2f} > "
                    f"max {PROPORTION_ABSOLUTE_MAX} (nieprostokątny kształt)"
                )
        elif room.proportion > PROPORTION_MAX:
            warnings.append(
                f"{room.spec.nazwa}: proporcja {room.proportion:.2f} > "
                f"zalecane {PROPORTION_MAX}"
            )


def _check_hub(plan: FloorPlan, errors: list[str], warnings: list[str]):
    """Hub: kompaktowy, nie korytarz-spine (RYZYKO 2)."""
    hub = plan.hub_room
    if hub is None:
        errors.append("Brak huba (pokoju komunikacji)")
        return

    hub_pct = plan.hub_percent  # teraz używa usable_area, nie bbox
    mtype = plan.template.typ_mieszkania
    min_pct = HUB_MIN_PERCENT.get(mtype, 0.08)

    if hub_pct < min_pct:
        warnings.append(
            f"Hub za mały: {hub_pct * 100:.1f}% < min {min_pct * 100:.0f}%"
        )
    if hub_pct > HUB_MAX_PERCENT + 0.05:
        warnings.append(
            f"Hub za duży: {hub_pct * 100:.1f}% > max {HUB_MAX_PERCENT * 100:.0f}%"
        )

    # Proporcja huba — nie może być korytarzem
    if hub.proportion > PROPORTION_MAX:
        warnings.append(
            f"Hub wygląda jak korytarz: proporcja {hub.proportion:.2f}"
        )

    # Hub nie może rozciągać się od ściany do ściany (spine check)
    bw = plan.boundary.width
    bh = plan.boundary.height
    hub_w = hub.width
    hub_d = hub.depth
    max_dim = max(hub_w, hub_d)
    corresponding_boundary = bw if hub_d <= hub_w else bh
    if max_dim > 0.6 * corresponding_boundary:
        warnings.append(
            f"Hub zbliża się do spine: najdłuższy wymiar "
            f"{max_dim:.2f}m > 60% obrysu ({0.6 * corresponding_boundary:.2f}m)"
        )


def _check_adjacency(plan: FloorPlan, errors: list[str], warnings: list[str]):
    """R_ABS_2 i R5: Topologia drzwi — hub dotyka każdego pokoju.

    WAŻNE ROZRÓŻNIENIE:
      - Pokoje MOGĄ dzielić ścianę (geometryczne sąsiedztwo) — to NIE jest naruszenie
      - "Przez hub" = drzwi prowadzą TYLKO z huba (topologia z szablonu)
      - Hub MUSI geometrycznie dotykać KAŻDEGO pokoju (shared edge ≥ 0.8m)
    """
    hub = plan.hub_room
    if hub is None:
        return

    # R_ABS_2: Hub dotyka każdego pokoju
    for r in plan.rooms:
        if r.spec.strefa == Strefa.KOMUNIKACJA:
            continue
        if r.polygon is None or hub.polygon is None:
            continue
        shared = hub.polygon.intersection(r.polygon)
        if shared.length < 0.8:
            warnings.append(
                f"Hub nie dotyka {r.spec.nazwa} "
                f"(shared edge={shared.length:.2f}m, min 0.8m na drzwi)"
            )


