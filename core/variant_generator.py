"""
Generowanie wariantów rzutów — orkiestracja CP-SAT solvera.

Źródła różnorodności:
1. Różne szablony topologiczne (M3_standard vs M3_wc)
2. Różne przypisania fasad (salon na S vs salon na W vs salon na E)
3. Lustrzane odbicia (flip_x, flip_y)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from shapely.geometry import Polygon, box as sbox

from core.models import Boundary, FloorPlan, Room, Template, WallType
from core.boundary_analyzer import analyze_boundary, is_rectangle
from core.template_selector import select_templates, load_all_templates
from core.cpsat_solver import solve_cpsat, _detect_facade_sides, RoomArrangement
from core.validator import validate
from core.scorer import score
from core.trapezoid_handler import detect_trapezoid, inscribed_rectangle, stretch_rooms_to_trapezoid


def generate_variants(
    polygon: Polygon,
    entry_point: tuple[float, float],
    mtype: str,
    max_variants: int = 5,
    templates_dir: Optional[Path] = None,
    solver_timeout: float = 15.0,
    progress_callback=None,
    wall_types: Optional[list[WallType]] = None,
    template_filter: Optional[list[str]] = None,
    min_score: float = 0.0,
) -> list[FloorPlan]:
    """Generuj warianty rzutów dla danego obrysu i typu mieszkania."""
    # Wykryj trapez — solver działa na wpisanym prostokącie, potem stretch
    trap_info = None
    trap_rect = None
    original_polygon = polygon  # zachowaj oryginalny obrys do clippingu

    if not is_rectangle(polygon):
        trap_info = detect_trapezoid(polygon)

    if trap_info is not None:
        trap_rect = inscribed_rectangle(trap_info)
        # Solver pracuje na wpisanym prostokącie
        solver_polygon = trap_rect
        # Entry point — rzutuj na prostokąt
        rb = trap_rect.bounds
        ep_x = max(rb[0], min(entry_point[0], rb[2]))
        ep_y = max(rb[1], min(entry_point[1], rb[3]))
        solver_entry = (ep_x, ep_y)
    else:
        solver_polygon = polygon
        solver_entry = entry_point

    boundary = analyze_boundary(solver_polygon, solver_entry, wall_types)
    all_templates = load_all_templates(templates_dir)
    templates = select_templates(mtype, boundary, all_templates)
    if template_filter:
        templates = [t for t in templates if t.id in template_filter]

    variants: list[FloorPlan] = []
    seen_layouts: set[str] = set()  # deduplikacja
    blocked: list[RoomArrangement] = []  # zablokowane topologie

    # Limit per szablon — daj szansę każdemu szablonowi
    n_templates = len(templates)
    per_template_limit = max(2, max_variants // n_templates) if n_templates > 1 else max_variants

    for template in templates:
        template_variants_count = 0

        # Znajdź salon (najwyższy priorytet fasady)
        salon_id = None
        for spec in template.pokoje:
            if spec.wymaga_okna and spec.priorytet_fasady == 1:
                salon_id = spec.id
                break

        # Generuj warianty z różnymi fasadami dla salonu
        facade_sides = _detect_facade_sides(boundary)
        available_facades = [s for s, is_facade in facade_sides.items() if is_facade]

        facade_configs: list[Optional[dict]] = [None]  # domyślny (solver wybiera)
        if salon_id:
            for side in available_facades:
                facade_configs.append({salon_id: side})

        for forced in facade_configs:
            if len(variants) >= max_variants or template_variants_count >= per_template_limit:
                break

            result = solve_cpsat(
                template, boundary,
                time_limit_s=solver_timeout,
                forced_facade=forced,
                blocked_arrangements=blocked if blocked else None,
            )
            if result.status not in ("OPTIMAL", "FEASIBLE"):
                continue

            # Zablokuj tę topologię dla następnych iteracji
            if result.arrangement:
                blocked.append(result.arrangement)

            # Deduplikacja — hash pozycji pokoi
            layout_key = _layout_hash(result.rooms)
            if layout_key in seen_layouts:
                continue
            seen_layouts.add(layout_key)

            plan = _build_plan(result.rooms, boundary, template)
            variants.append(plan)
            template_variants_count += 1
            if progress_callback:
                progress_callback(len(variants), max_variants)

            # Flip X (pomiń jeśli pokoje wchodzą w notch)
            if len(variants) < max_variants and template_variants_count < per_template_limit:
                flipped = _flip_x(result.rooms, boundary)
                fkey = _layout_hash(flipped)
                if fkey not in seen_layouts and _rooms_inside_boundary(flipped, boundary):
                    seen_layouts.add(fkey)
                    plan_fx = _build_plan(flipped, boundary, template)
                    variants.append(plan_fx)
                    template_variants_count += 1
                    if progress_callback:
                        progress_callback(len(variants), max_variants)

        # Dodatkowe rozwiązania z blokowanymi topologiami (bez forced_facade)
        # — solver szuka topologicznie różnych układów
        attempts = 0
        while len(variants) < max_variants and template_variants_count < per_template_limit and attempts < 3:
            attempts += 1
            result = solve_cpsat(
                template, boundary,
                time_limit_s=solver_timeout,
                blocked_arrangements=blocked if blocked else None,
            )
            if result.status not in ("OPTIMAL", "FEASIBLE"):
                break  # solver nie może znaleźć więcej różnych rozwiązań

            if result.arrangement:
                blocked.append(result.arrangement)

            layout_key = _layout_hash(result.rooms)
            if layout_key in seen_layouts:
                continue
            seen_layouts.add(layout_key)

            plan = _build_plan(result.rooms, boundary, template)
            variants.append(plan)
            template_variants_count += 1
            if progress_callback:
                progress_callback(len(variants), max_variants)

    # Post-processing: rozciągnij do trapezu
    if trap_info is not None and trap_rect is not None:
        for plan in variants:
            stretch_rooms_to_trapezoid(plan, trap_info, trap_rect)
            validate(plan)
            score(plan)
    elif not is_rectangle(original_polygon):
        # Fallback: docinaj pokoje do oryginalnego obrysu (trapez nieregularny itp.)
        for plan in variants:
            _clip_rooms_to_polygon(plan, original_polygon)
            validate(plan)
            score(plan)

    variants.sort(key=lambda p: p.score, reverse=True)
    if min_score > 0:
        variants = [v for v in variants if v.score >= min_score]
    return variants[:max_variants]


def _clip_rooms_to_polygon(plan: FloorPlan, clip_polygon: Polygon):
    """Docinaj pokoje do obrysu (fallback dla nieregularnych kształtów)."""
    clipped = []
    for room in plan.rooms:
        if room.polygon is None:
            clipped.append(room)
            continue
        cut = room.polygon.intersection(clip_polygon)
        if cut.is_empty or cut.area < 0.1:
            clipped.append(room)
            continue
        if cut.geom_type == "MultiPolygon":
            cut = max(cut.geoms, key=lambda g: g.area)
        elif cut.geom_type != "Polygon":
            clipped.append(room)
            continue
        r = Room(spec=room.spec, polygon=cut)
        r.update_metrics()
        clipped.append(r)
    plan.rooms = clipped
    plan.boundary.polygon = clip_polygon


def _rooms_inside_boundary(rooms: list[Room], boundary: Boundary) -> bool:
    """Sprawdź czy wszystkie pokoje mieszczą się w obrysie (ważne dla L-kształtów)."""
    buffered = boundary.polygon.buffer(0.02)
    return all(buffered.contains(r.polygon) for r in rooms if r.polygon is not None)


def _build_plan(rooms: list[Room], boundary: Boundary, template: Template) -> FloorPlan:
    """Zbuduj FloorPlan z pokoi, zwaliduj i oceń."""
    plan = FloorPlan(boundary=boundary, template=template, rooms=rooms)
    validate(plan)
    score(plan)
    return plan


def _layout_hash(rooms: list[Room]) -> str:
    """Hash układu pokoi — zaokrąglony do 10cm dla deduplikacji."""
    parts = []
    for r in sorted(rooms, key=lambda r: r.spec.id):
        b = r.polygon.bounds
        parts.append(f"{r.spec.id}:{b[0]:.1f},{b[1]:.1f},{b[2]:.1f},{b[3]:.1f}")
    return "|".join(parts)


def _flip_x(rooms: list[Room], boundary: Boundary) -> list[Room]:
    """Odbij pokoje względem osi Y (lustrzane lewo-prawo)."""
    bx0, by0, bx1, by1 = boundary.bbox
    flipped = []
    for room in rooms:
        rb = room.polygon.bounds
        poly = sbox(bx0 + (bx1 - rb[2]), rb[1], bx0 + (bx1 - rb[0]), rb[3])
        r = Room(spec=room.spec, polygon=poly)
        r.update_metrics()
        flipped.append(r)
    return flipped


def _flip_y(rooms: list[Room], boundary: Boundary) -> list[Room]:
    """Odbij pokoje względem osi X (lustrzane góra-dół)."""
    bx0, by0, bx1, by1 = boundary.bbox
    flipped = []
    for room in rooms:
        rb = room.polygon.bounds
        poly = sbox(rb[0], by0 + (by1 - rb[3]), rb[2], by0 + (by1 - rb[1]))
        r = Room(spec=room.spec, polygon=poly)
        r.update_metrics()
        flipped.append(r)
    return flipped
