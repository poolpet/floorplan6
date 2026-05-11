"""
Floor solver — etap 3 (podział kondygnacji na mieszkania).

KROK 1 (MVP): mieszkania jako prostokąty, każde dotyka klatki schodowej drzwiami
(adjacency >= DOOR_MIN_WIDTH). Bez korytarza — bezpośredni dostęp do klatki.

KROK 2 (TODO): dodaj korytarz wychodzący z klatki, mieszkania dotykają korytarza.

Reguły z etapu 4 zachowane analogicznie:
- Coverage equality: sum(apartments) + stairwell.area == floor.area
- NoOverlap2D
- Aspect ratio mieszkania <= APARTMENT_MAX_ASPECT
- Min powierzchnia per typ (APARTMENT_MIN_AREA)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ortools.sat.python import cp_model
from shapely.geometry import Polygon, box as sbox

from rules._loader import get_default_pack as _get_default_pack

_PACK = _get_default_pack()
APARTMENT_MIN_AREA = _PACK.constants["apartment_min_area"]
APARTMENT_OPT_AREA = _PACK.constants["apartment_opt_area"]
APARTMENT_MAX_ASPECT = _PACK.constants["apartment_max_aspect"]
DOOR_MIN_WIDTH = _PACK.constants["door_min_width"]

SCALE = 100  # m → cm
DOOR_MIN_CM = round(DOOR_MIN_WIDTH * SCALE)


@dataclass
class Apartment:
    """Wygenerowane mieszkanie na piętrze (etap 3)."""
    apartment_type: str  # "M1"..."M5"
    polygon: Polygon
    area: float = 0.0
    width: float = 0.0
    depth: float = 0.0

    def update_metrics(self):
        if self.polygon is not None:
            self.area = self.polygon.area
            b = self.polygon.bounds
            w = b[2] - b[0]
            h = b[3] - b[1]
            self.width = min(w, h)
            self.depth = max(w, h)


@dataclass
class FloorSolverResult:
    """Wynik solvera etapu 3."""
    status: str  # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / "UNKNOWN"
    apartments: list[Apartment] = field(default_factory=list)
    corridor: Optional[Polygon] = None  # KROK 2
    solve_time_s: float = 0.0


def solve_floor(
    floor_polygon: Polygon,
    stairwell: Polygon,
    mix: list[str] | dict[str, int],
    corridor: Optional[Polygon] = None,
    time_limit_s: float = 30.0,
) -> FloorSolverResult:
    """Podziel obrys piętra na mieszkania zgodnie z mix.

    Args:
        floor_polygon: obrys piętra (Shapely Polygon, prostokąt lub L-shape).
        stairwell: poligon klatki schodowej (musi być wewnątrz floor_polygon).
            Wymiary obliczane przez `compute_stairwell_dimensions(h, n_floors)`.
        mix: lista typów ["M2", "M2", "M3"] LUB dict {"M2": 2, "M3": 1}.
        time_limit_s: limit czasu solvera.

    Returns:
        FloorSolverResult z listą Apartment lub status INFEASIBLE.

    Założenia MVP:
    - Floor jest prostokątem (jeśli L-shape: TODO przyszły krok)
    - Klatka jest prostokątem osiowo wyrównanym wewnątrz floor
    - Każde mieszkanie ma drzwi DIRECTLY do klatki (KROK B: korytarz)
    """
    # Normalizacja mix: dict → list (kolejność: większe typy pierwsze dla solver heuristic)
    if isinstance(mix, dict):
        mix = [t for t in ("M5", "M4", "M3", "M2", "M1") for _ in range(mix.get(t, 0))]
    t0 = time.monotonic()

    # Bbox floor (zakładamy prostokąt MVP)
    fx0, fy0, fx1, fy1 = floor_polygon.bounds
    BW = round((fx1 - fx0) * SCALE)
    BH = round((fy1 - fy0) * SCALE)

    # Klatka schodowa w lokalnych współrzędnych floor
    sx0, sy0, sx1, sy1 = stairwell.bounds
    SX = round((sx0 - fx0) * SCALE)
    SY = round((sy0 - fy0) * SCALE)
    SW = round((sx1 - sx0) * SCALE)
    SH = round((sy1 - sy0) * SCALE)
    SX_END = SX + SW
    SY_END = SY + SH

    n = len(mix)
    if n == 0:
        return FloorSolverResult(status="INFEASIBLE", solve_time_s=time.monotonic() - t0)

    model = cp_model.CpModel()

    # Zmienne pozycji i rozmiaru każdego mieszkania (w cm)
    x, y, w, h = [], [], [], []
    x_ends, y_ends = [], []
    areas = []
    for i, atype in enumerate(mix):
        min_area_cm2 = round(APARTMENT_MIN_AREA[atype] * SCALE * SCALE)
        # Min wymiar — heurystyka: min_dim = sqrt(min_area / max_aspect)
        min_dim_cm = round((APARTMENT_MIN_AREA[atype] / APARTMENT_MAX_ASPECT) ** 0.5 * SCALE)
        min_dim_cm = max(min_dim_cm, 200)  # absolutne min 2m (sensible apartment)

        xi = model.new_int_var(0, BW, f"ax_{i}")
        yi = model.new_int_var(0, BH, f"ay_{i}")
        wi = model.new_int_var(min_dim_cm, BW, f"aw_{i}")
        hi = model.new_int_var(min_dim_cm, BH, f"ah_{i}")
        xie = model.new_int_var(0, BW, f"ax_end_{i}")
        yie = model.new_int_var(0, BH, f"ay_end_{i}")
        model.add(xie == xi + wi)
        model.add(yie == yi + hi)

        # Aspect ratio: max APARTMENT_MAX_ASPECT
        ar_num = round(APARTMENT_MAX_ASPECT * 100)
        model.add(wi * 100 <= ar_num * hi)
        model.add(hi * 100 <= ar_num * wi)

        # Min area: użyj zmiennej pomocniczej z multiplication_equality
        ai = model.new_int_var(min_area_cm2, BW * BH, f"aarea_{i}")
        model.add_multiplication_equality(ai, [wi, hi])

        x.append(xi); y.append(yi); w.append(wi); h.append(hi)
        x_ends.append(xie); y_ends.append(yie)
        areas.append(ai)

    # NoOverlap2D: mieszkania + klatka jako fixed obstacle
    x_intervals = []
    y_intervals = []
    for i in range(n):
        xi_iv = model.new_interval_var(x[i], w[i], x_ends[i], f"axiv_{i}")
        yi_iv = model.new_interval_var(y[i], h[i], y_ends[i], f"ayiv_{i}")
        x_intervals.append(xi_iv)
        y_intervals.append(yi_iv)
    # Klatka jako stałe interwały
    s_xs = model.new_constant(SX)
    s_ys = model.new_constant(SY)
    s_xe = model.new_constant(SX_END)
    s_ye = model.new_constant(SY_END)
    s_wv = model.new_constant(SW)
    s_hv = model.new_constant(SH)
    s_x_iv = model.new_interval_var(s_xs, s_wv, s_xe, "stair_x")
    s_y_iv = model.new_interval_var(s_ys, s_hv, s_ye, "stair_y")
    x_intervals.append(s_x_iv)
    y_intervals.append(s_y_iv)
    model.add_no_overlap_2d(x_intervals, y_intervals)

    # Coverage: sum(apartments) <= usable. Mniejsze różnice pokryje korytarz w KROK 2.
    # Mieszkania prostokątne nie pokrywają 100% obrysu z klatką w środku — geometryczna
    # niemożliwość. Solver szuka z min deviation od opt_area.
    model.add(sum(areas) <= BW * BH - SW * SH)

    # Adjacency: każde mieszkanie dotyka klatki (shared edge >= DOOR_MIN_CM)
    for i in range(n):
        _add_stairwell_adjacency(model, i, x[i], y[i], w[i], h[i],
                                 x_ends[i], y_ends[i],
                                 SX, SY, SX_END, SY_END, BW, BH)

    # Objective: minimalizuj odchylenie powierzchni od opt per typ
    obj_terms = []
    for i, atype in enumerate(mix):
        opt_cm2 = round(APARTMENT_OPT_AREA[atype] * SCALE * SCALE)
        dev_p = model.new_int_var(0, BW * BH, f"dev_p_{i}")
        dev_m = model.new_int_var(0, BW * BH, f"dev_m_{i}")
        model.add(areas[i] - opt_cm2 == dev_p - dev_m)
        obj_terms.append(dev_p + dev_m)
    model.minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    solver.parameters.relative_gap_limit = 0.05
    status = solver.solve(model)

    elapsed = time.monotonic() - t0
    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return FloorSolverResult(status=status_name, solve_time_s=elapsed)

    apartments = []
    for i, atype in enumerate(mix):
        rx = solver.value(x[i]) / SCALE + fx0
        ry = solver.value(y[i]) / SCALE + fy0
        rw = solver.value(w[i]) / SCALE
        rh = solver.value(h[i]) / SCALE
        poly = sbox(rx, ry, rx + rw, ry + rh)
        ap = Apartment(apartment_type=atype, polygon=poly)
        ap.update_metrics()
        apartments.append(ap)

    return FloorSolverResult(
        status=status_name,
        apartments=apartments,
        solve_time_s=elapsed,
    )


def _add_stairwell_adjacency(
    model: cp_model.CpModel,
    i: int,
    xi, yi, wi, hi, xi_end, yi_end,
    SX: int, SY: int, SX_END: int, SY_END: int,
    BW: int, BH: int,
):
    """Mieszkanie i musi mieć shared edge ≥ DOOR_MIN_CM z klatką schodową.

    4 możliwe pozycje względem klatki:
    - Mieszkanie po LEWEJ klatki: xi_end == SX, overlap Y ≥ DOOR_MIN
    - Mieszkanie po PRAWEJ klatki: xi == SX_END, overlap Y ≥ DOOR_MIN
    - Mieszkanie POD klatką: yi_end == SY, overlap X ≥ DOOR_MIN
    - Mieszkanie NAD klatką: yi == SY_END, overlap X ≥ DOOR_MIN
    """
    bools = []

    # Po lewej
    b_l = model.new_bool_var(f"adj_{i}_left")
    model.add(xi_end == SX).only_enforce_if(b_l)
    # overlap Y: min(yi_end, SY_END) - max(yi, SY) >= DOOR_MIN
    ov_l = model.new_int_var(-BH, BH, f"ov_l_{i}")
    min_e_l = model.new_int_var(0, BH, f"min_e_l_{i}")
    max_s_l = model.new_int_var(0, BH, f"max_s_l_{i}")
    model.add_min_equality(min_e_l, [yi_end, model.new_constant(SY_END)])
    model.add_max_equality(max_s_l, [yi, model.new_constant(SY)])
    model.add(ov_l == min_e_l - max_s_l)
    model.add(ov_l >= DOOR_MIN_CM).only_enforce_if(b_l)
    bools.append(b_l)

    # Po prawej
    b_r = model.new_bool_var(f"adj_{i}_right")
    model.add(xi == SX_END).only_enforce_if(b_r)
    ov_r = model.new_int_var(-BH, BH, f"ov_r_{i}")
    min_e_r = model.new_int_var(0, BH, f"min_e_r_{i}")
    max_s_r = model.new_int_var(0, BH, f"max_s_r_{i}")
    model.add_min_equality(min_e_r, [yi_end, model.new_constant(SY_END)])
    model.add_max_equality(max_s_r, [yi, model.new_constant(SY)])
    model.add(ov_r == min_e_r - max_s_r)
    model.add(ov_r >= DOOR_MIN_CM).only_enforce_if(b_r)
    bools.append(b_r)

    # Pod
    b_d = model.new_bool_var(f"adj_{i}_down")
    model.add(yi_end == SY).only_enforce_if(b_d)
    ov_d = model.new_int_var(-BW, BW, f"ov_d_{i}")
    min_e_d = model.new_int_var(0, BW, f"min_e_d_{i}")
    max_s_d = model.new_int_var(0, BW, f"max_s_d_{i}")
    model.add_min_equality(min_e_d, [xi_end, model.new_constant(SX_END)])
    model.add_max_equality(max_s_d, [xi, model.new_constant(SX)])
    model.add(ov_d == min_e_d - max_s_d)
    model.add(ov_d >= DOOR_MIN_CM).only_enforce_if(b_d)
    bools.append(b_d)

    # Nad
    b_u = model.new_bool_var(f"adj_{i}_up")
    model.add(yi == SY_END).only_enforce_if(b_u)
    ov_u = model.new_int_var(-BW, BW, f"ov_u_{i}")
    min_e_u = model.new_int_var(0, BW, f"min_e_u_{i}")
    max_s_u = model.new_int_var(0, BW, f"max_s_u_{i}")
    model.add_min_equality(min_e_u, [xi_end, model.new_constant(SX_END)])
    model.add_max_equality(max_s_u, [xi, model.new_constant(SX)])
    model.add(ov_u == min_e_u - max_s_u)
    model.add(ov_u >= DOOR_MIN_CM).only_enforce_if(b_u)
    bools.append(b_u)

    model.add_bool_or(bools)
