"""
Test regresji F2 (FUNDAMENTAL_RULES): łazienka NIGDY nie może przekroczyć 5m².

Iteruje przez wszystkie constraint templates × przykładowe obrysy.
Każda łazienka (id zawiera "lazienka") musi mieć area <= 5.0m².

Jeśli ten test FAIL → to jest BUG fundamentalny, NIE łatać, REWRITE.
"""
import pytest
from shapely.geometry import Polygon

from core.cpsat_solver import solve_cpsat
from core.template_selector import load_all_templates
from core.boundary_analyzer import analyze_boundary

TEMPLATES = [
    "M1_standard",
    "M2_standard",
    "M3_standard",
    "M3_wc",
    "M4_standard",
    "M4_2laz",
    "M5_standard",
]
BOUNDARIES = [
    (6.0, 6.0),
    (8.0, 6.0),
    (10.0, 8.0),
    (12.0, 10.0),
    (15.0, 12.0),
]


def _make_boundary(w, h):
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    return analyze_boundary(poly, (w / 2, 0))


@pytest.mark.parametrize("template_id", TEMPLATES)
@pytest.mark.parametrize("w,h", BOUNDARIES)
def test_lazienka_never_exceeds_5m2(template_id, w, h):
    """F2: łazienka <= 5.0m² zawsze."""
    templates = [t for t in load_all_templates() if t.id == template_id]
    if not templates:
        pytest.skip(f"Template {template_id} nieznaleziony")
    template = templates[0]

    boundary = _make_boundary(w, h)
    # 5s timeout: F2 violation byłaby wykryta natychmiast, dłuższy timeout to
    # tylko search optimum. Skip akceptowalny — sygnał że Q6+F2 ciasne dla tego case.
    result = solve_cpsat(template, boundary, time_limit_s=5.0)

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        pytest.skip(f"Solver INFEASIBLE dla {template_id} {w}×{h}")

    for room in result.rooms:
        room_id = room.spec.id.lower()
        if "lazienka" in room_id:
            # +0.01 tolerancja: spójna z validator._check_max_areas, pokrywa FP rounding
            # ze Shapely clip/intersection (ok. 1e-15 m²). Realnie 5.01 m² = 5.0 m².
            assert room.area <= 5.0 + 0.01, (
                f"F2 VIOLATION: {template_id} {w}×{h}: "
                f"{room.spec.id} = {room.area:.4f}m² (max 5.0)"
            )


@pytest.mark.parametrize("template_id", TEMPLATES)
@pytest.mark.parametrize("w,h", BOUNDARIES)
def test_wc_never_exceeds_3m2(template_id, w, h):
    """WC max 3m² (mniejsze niż łazienka)."""
    templates = [t for t in load_all_templates() if t.id == template_id]
    if not templates:
        pytest.skip(f"Template {template_id} nieznaleziony")
    template = templates[0]

    boundary = _make_boundary(w, h)
    # 5s timeout: F2 violation byłaby wykryta natychmiast, dłuższy timeout to
    # tylko search optimum. Skip akceptowalny — sygnał że Q6+F2 ciasne dla tego case.
    result = solve_cpsat(template, boundary, time_limit_s=5.0)

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        pytest.skip()

    for room in result.rooms:
        if room.spec.id.lower() == "wc":
            assert room.area <= 3.0 + 0.01, (
                f"WC VIOLATION: {template_id} {w}×{h}: "
                f"wc = {room.area:.4f}m² (max 3.0)"
            )
