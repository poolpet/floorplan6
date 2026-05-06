"""
CP-SAT solver dla generowania rzutów mieszkań.

Umieszcza pokoje z szablonu w prostokątnym obrysie z gwarancjami:
- NoOverlap2D — pokoje się nie nakładają
- Containment — pokoje wewnątrz obrysu
- Coverage — suma powierzchni == powierzchnia obrysu (brak dziur)
- Adjacency — pokoje sąsiadujące wg szablonu mają wspólną ścianę
- Facade — pokoje z oknami dotykają fasady
- Hub — kompaktowy, przy wejściu, nie korytarz-spine
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ortools.sat.python import cp_model
from shapely.geometry import Polygon, box

from core.models import (
    Boundary, Template, RoomSpec, Room, Strefa, WallType,
)
from config import WT_MAX_AREA


# Precyzja: 1 cm (wymiary w cm jako int dla CP-SAT)
SCALE = 100  # metry -> cm

# Minimalna wspólna krawędź do uznania sąsiedztwa [cm]
# 90cm = szerokość drzwi standardowych
MIN_SHARED_EDGE_CM = 90


@dataclass
class RoomArrangement:
    """Topologia rozwiązania — pozycje pokoi w gridzie (do blokowania duplikatów)."""
    # Dla każdego pokoju: (room_id, quadrant) gdzie quadrant to
    # pozycja środka pokoju w gridzie 2x2 boundary (0-3)
    room_quadrants: dict[str, int] = field(default_factory=dict)


@dataclass
class CpsatResult:
    """Wynik solvera CP-SAT."""
    status: str  # "OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"
    rooms: list[Room] = field(default_factory=list)
    solve_time_s: float = 0.0
    objective_value: float = 0.0
    arrangement: Optional[RoomArrangement] = None


def _detect_facade_sides(boundary: Boundary) -> dict[str, bool]:
    """Wykryj które strony prostokątnego boundary są fasadami.

    Zwraca dict: {"south": bool, "east": bool, "north": bool, "west": bool}
    mapujący na: y=0, x=BW, y=BH, x=0.
    """
    bx0, by0, bx2, by2 = boundary.bbox
    facades = {"south": True, "east": True, "north": True, "west": True}

    for edge in boundary.edges:
        if edge.wall_type != WallType.INTERNAL:
            continue
        sx, sy = edge.start
        ex, ey = edge.end
        tol = 0.05
        if abs(sy - by0) < tol and abs(ey - by0) < tol:
            facades["south"] = False
        elif abs(sy - by2) < tol and abs(ey - by2) < tol:
            facades["north"] = False
        elif abs(sx - bx0) < tol and abs(ex - bx0) < tol:
            facades["west"] = False
        elif abs(sx - bx2) < tol and abs(ex - bx2) < tol:
            facades["east"] = False

    return facades


def _detect_notch_facade_sides(boundary: Boundary) -> dict[str, bool]:
    """Klasyfikacja wewnętrznych krawędzi notch (te WIDOCZNE z polygonu).

    Klucze: "upper" (y = ny+nh), "lower" (y = ny), "left" (x = nx), "right" (x = nx+nw).
    Default False — krawędź notch zwykle nie jest fasadą (klatka schodowa, sąsiad).
    True jeśli wall_types Dawida oznaczyły krawędź jako FACADE.

    Krawędzie notch zlewające się z bbox boundary (np. dla notch w rogu) są
    pomijane — są obsługiwane przez `_detect_facade_sides` jako bbox sides.
    """
    if boundary.notch is None:
        return {}

    bx0, by0, _, _ = boundary.bbox
    nx = bx0 + boundary.notch.x
    ny = by0 + boundary.notch.y
    nx_end = nx + boundary.notch.width
    ny_end = ny + boundary.notch.height
    bx2, by2 = boundary.bbox[2], boundary.bbox[3]
    tol = 0.05

    # Realne (widoczne) krawędzie notch — te których linia NIE zlewa się z bbox
    notch_facades = {}
    if abs(ny_end - by2) > tol and abs(ny_end - by0) > tol:
        notch_facades["upper"] = False
    if abs(ny - by0) > tol and abs(ny - by2) > tol:
        notch_facades["lower"] = False
    if abs(nx - bx0) > tol and abs(nx - bx2) > tol:
        notch_facades["left"] = False
    if abs(nx_end - bx2) > tol and abs(nx_end - bx0) > tol:
        notch_facades["right"] = False

    # Sprawdź wall_types: dla każdej FACADE krawędzi pokrywającej linię notch → True
    for edge in boundary.edges:
        if edge.wall_type != WallType.FACADE:
            continue
        sx, sy = edge.start
        ex, ey = edge.end
        min_x, max_x = min(sx, ex), max(sx, ex)
        min_y, max_y = min(sy, ey), max(sy, ey)

        # upper: y = ny_end, x in [nx, nx_end]
        if "upper" in notch_facades and abs(sy - ny_end) < tol and abs(ey - ny_end) < tol:
            if min_x >= nx - tol and max_x <= nx_end + tol:
                notch_facades["upper"] = True
        # lower: y = ny
        elif "lower" in notch_facades and abs(sy - ny) < tol and abs(ey - ny) < tol:
            if min_x >= nx - tol and max_x <= nx_end + tol:
                notch_facades["lower"] = True
        # left: x = nx
        elif "left" in notch_facades and abs(sx - nx) < tol and abs(ex - nx) < tol:
            if min_y >= ny - tol and max_y <= ny_end + tol:
                notch_facades["left"] = True
        # right: x = nx_end
        elif "right" in notch_facades and abs(sx - nx_end) < tol and abs(ex - nx_end) < tol:
            if min_y >= ny - tol and max_y <= ny_end + tol:
                notch_facades["right"] = True

    return notch_facades


def _detect_entry_side(boundary: Boundary) -> str:
    """Wykryj po której stronie boundary jest entry_point.

    Zwraca: "south", "north", "east", "west".
    """
    bx0, by0, bx2, by2 = boundary.bbox
    ex, ey = boundary.entry_point
    tol = 0.05

    if abs(ey - by0) < tol:
        return "south"
    elif abs(ey - by2) < tol:
        return "north"
    elif abs(ex - bx0) < tol:
        return "west"
    elif abs(ex - bx2) < tol:
        return "east"

    # Fallback — najbliższa strona
    dists = {
        "south": abs(ey - by0),
        "north": abs(ey - by2),
        "west": abs(ex - bx0),
        "east": abs(ex - bx2),
    }
    return min(dists, key=dists.get)


def _compute_target_areas(
    specs: list[RoomSpec], usable_area_m2: float
) -> dict[str, float]:
    """Q6 (DECIDED 2026-04-30): rozkład powierzchni między pokoje.

    Reguły:
    - Pokoje usługowe (lazienka/wc, prefix matching): target = min(opt, WT_MAX_AREA)
    - Hub (KOMUNIKACJA): target = min(opt, 0.12 * usable) — F4 cap 15%, target 12%
    - Salon: target = min + 0.8 * excess
    - Sypialnie: target = min + 0.2 * excess * (min_i / sum(min_sypialnie))
    Edge cases: M1 (brak sypialni) — salon bierze całą resztę. Brak salonu — fallback opt.
    """
    targets: dict[str, float] = {}

    for spec in specs:
        key = spec.id.split("_")[0]
        if key in WT_MAX_AREA:
            opt = spec.opt_powierzchnia or spec.min_powierzchnia
            targets[spec.id] = min(opt, WT_MAX_AREA[key])
        elif spec.strefa == Strefa.KOMUNIKACJA:
            opt = spec.opt_powierzchnia or spec.min_powierzchnia
            targets[spec.id] = min(opt, 0.12 * usable_area_m2)

    salons = [s for s in specs if "salon" in s.id]
    sypialnie = [s for s in specs if "sypialnia" in s.id]
    fixed_sum = sum(targets.values())
    available = usable_area_m2 - fixed_sum

    if not salons:
        for spec in specs:
            if spec.id not in targets:
                targets[spec.id] = spec.opt_powierzchnia or spec.min_powierzchnia
        return targets

    salon = salons[0]

    if not sypialnie:
        targets[salon.id] = max(salon.min_powierzchnia, available)
        return targets

    syp_mins = [s.min_powierzchnia for s in sypialnie]
    min_total = salon.min_powierzchnia + sum(syp_mins)

    if available <= min_total:
        targets[salon.id] = salon.min_powierzchnia
        for s, smin in zip(sypialnie, syp_mins):
            targets[s.id] = smin
        return targets

    excess = available - min_total
    targets[salon.id] = salon.min_powierzchnia + 0.8 * excess
    sum_syp_min = sum(syp_mins)
    for s, smin in zip(sypialnie, syp_mins):
        targets[s.id] = smin + 0.2 * excess * (smin / sum_syp_min)

    return targets


def solve_cpsat(
    template: Template,
    boundary: Boundary,
    time_limit_s: float = 30.0,
    forced_facade: Optional[dict[str, str]] = None,
    blocked_arrangements: Optional[list[RoomArrangement]] = None,
) -> CpsatResult:
    """Solver CP-SAT — umieszcza pokoje szablonu w obrysie.

    Args:
        template: Szablon topologiczny z pokojami i sąsiedztwem.
        boundary: Obrys mieszkania (prostokąt).
        time_limit_s: Limit czasu solvera [s].
        forced_facade: Wymuszenie fasady per pokój, np. {"salon_aneks": "south"}.
            Klucz = room_id, wartość = "south"/"north"/"east"/"west".
        blocked_arrangements: Lista wcześniejszych rozwiązań do zablokowania.
            Solver wygeneruje topologicznie inny układ.

    Returns:
        CpsatResult z pokojami (Room z polygon w metrach).
    """
    t0 = time.monotonic()

    # --- Wymiary boundary w cm (int) ---
    BW = round(boundary.width * SCALE)
    BH = round(boundary.height * SCALE)
    B_AREA = BW * BH  # cm²

    n = len(template.pokoje)
    specs = template.pokoje

    # --- Facade info ---
    facade_sides = _detect_facade_sides(boundary)
    notch_facades = _detect_notch_facade_sides(boundary)
    entry_side = _detect_entry_side(boundary)

    # --- Model CP-SAT ---
    model = cp_model.CpModel()

    # Zmienne: x[i], y[i] (lewy dolny róg), w[i], h[i] (szerokość, wysokość)
    x = []
    y = []
    w = []
    h = []

    x_ends = []  # x[i] + w[i]
    y_ends = []  # y[i] + h[i]

    for i, spec in enumerate(specs):
        min_dim_cm = max(round(spec.min_szerokosc * SCALE), 100)  # min 1m
        min_area_cm2 = round(spec.min_powierzchnia * SCALE * SCALE)

        xi = model.new_int_var(0, BW, f"x_{i}")
        yi = model.new_int_var(0, BH, f"y_{i}")
        wi = model.new_int_var(min_dim_cm, BW, f"w_{i}")
        hi = model.new_int_var(min_dim_cm, BH, f"h_{i}")

        x.append(xi)
        y.append(yi)
        w.append(wi)
        h.append(hi)

        # --- Interval variables for NoOverlap2D ---
        x_end = model.new_int_var(0, BW, f"x_end_{i}")
        y_end = model.new_int_var(0, BH, f"y_end_{i}")
        model.add(x_end == xi + wi)
        model.add(y_end == yi + hi)
        x_ends.append(x_end)
        y_ends.append(y_end)

        # --- Containment: pokoje wewnątrz boundary ---
        model.add(x_end <= BW)
        model.add(y_end <= BH)

        # --- Aspect ratio <= 2:1 ---
        # w <= 2*h AND h <= 2*w
        max_ratio_num = round(spec.max_proporcja * 100)
        # w * 100 <= max_ratio * h  =>  w*100 <= max_ratio_num * h
        model.add(wi * 100 <= max_ratio_num * hi)
        model.add(hi * 100 <= max_ratio_num * wi)

        # --- Min area: w*h >= min_area ---
        # CP-SAT nie ma bezpośrednio produktu w ograniczeniu, używamy zmiennej pomocniczej
        # F2 (FUNDAMENTAL_RULES): twardy cap WT dla łazienki/WC ma pierwszeństwo nad procent_powierzchni
        upper_bound = BW * BH
        key = spec.id.split("_")[0]  # "lazienka_2" -> "lazienka"
        if key in WT_MAX_AREA:
            upper_bound = min(upper_bound, round(WT_MAX_AREA[key] * SCALE * SCALE))
        area_i = model.new_int_var(min_area_cm2, upper_bound, f"area_{i}")
        model.add_multiplication_equality(area_i, [wi, hi])

    # Zmienne area (referencja)
    areas = []
    for i in range(n):
        ai = model.new_int_var(0, BW * BH, f"area_ref_{i}")
        model.add_multiplication_equality(ai, [w[i], h[i]])
        areas.append(ai)

    # --- NoOverlap2D ---
    x_intervals = []
    y_intervals = []
    for i in range(n):
        x_iv = model.new_interval_var(x[i], w[i], x_ends[i], f"xiv_{i}")
        y_iv = model.new_interval_var(y[i], h[i], y_ends[i], f"yiv_{i}")
        x_intervals.append(x_iv)
        y_intervals.append(y_iv)

    # --- Notch jako przeszkoda (L-kształt) ---
    notch = boundary.notch
    if notch is not None:
        nx = round(notch.x * SCALE)
        ny = round(notch.y * SCALE)
        nw = round(notch.width * SCALE)
        nh = round(notch.height * SCALE)
        # Stałe zmienne — notch jest nieruchomy
        notch_sx = model.new_constant(nx)
        notch_sy = model.new_constant(ny)
        notch_ex = model.new_constant(nx + nw)
        notch_ey = model.new_constant(ny + nh)
        notch_wv = model.new_constant(nw)
        notch_hv = model.new_constant(nh)
        notch_x_iv = model.new_interval_var(notch_sx, notch_wv, notch_ex, "notch_x")
        notch_y_iv = model.new_interval_var(notch_sy, notch_hv, notch_ey, "notch_y")
        x_intervals.append(notch_x_iv)
        y_intervals.append(notch_y_iv)

    model.add_no_overlap_2d(x_intervals, y_intervals)

    # --- Coverage: suma area == usable area (boundary - notch) ---
    # WAŻNE: oblicz notch area z integer cm (spójne z obstacle w NoOverlap2D)
    if notch is not None:
        notch_area_cm2 = nw * nh  # integer cm, bez błędów zaokrąglenia
    else:
        notch_area_cm2 = 0
    usable_area = B_AREA - notch_area_cm2
    model.add(sum(areas) == usable_area)

    # ====================================================================
    # Stage B: Adjacency constraints
    # ====================================================================
    hub_idx = None
    for i, spec in enumerate(specs):
        if spec.strefa == Strefa.KOMUNIKACJA:
            hub_idx = i
            break

    # Zbuduj zbiór wymaganych sąsiedztw (pomijając _outside)
    required_adj: list[tuple[int, int]] = []
    for rule in template.sasiedztwo:
        if rule.room_a == "_outside" or rule.room_b == "_outside":
            continue
        idx_a = next((i for i, s in enumerate(specs) if s.id == rule.room_a), None)
        idx_b = next((i for i, s in enumerate(specs) if s.id == rule.room_b), None)
        if idx_a is not None and idx_b is not None:
            required_adj.append((idx_a, idx_b))

    # Adjacency constraint: dwa pokoje muszą współdzielić krawędź o długości >= MIN_SHARED_EDGE
    # 4 przypadki: a jest na lewo/prawo/poniżej/powyżej b
    for (a, b) in required_adj:
        _add_adjacency_constraint(model, a, b, x, y, w, h, x_ends, y_ends,
                                  BW, BH, MIN_SHARED_EDGE_CM)

    # ====================================================================
    # Stage B+: Hub musi dotykać KAŻDEGO pokoju (nawet jeśli nie jest explicite w sasiedztwo)
    # ====================================================================
    if hub_idx is not None:
        for i in range(n):
            if i == hub_idx:
                continue
            pair = (hub_idx, i)
            if pair not in required_adj and (i, hub_idx) not in required_adj:
                _add_adjacency_constraint(model, hub_idx, i, x, y, w, h,
                                          x_ends, y_ends, BW, BH, MIN_SHARED_EDGE_CM)

    # ====================================================================
    # Hub constraints: compact, at entry, not spine
    # ====================================================================
    if hub_idx is not None:
        # Hub nie-spine: oba wymiary < 60% boundary, ALE dla wąskich obrysów
        # pozwalamy na max 80% krótszego wymiaru (hub musi łączyć pokoje)
        max_w_hub = max(round(0.6 * BW), round(0.8 * min(BW, BH)))
        max_h_hub = max(round(0.6 * BH), round(0.8 * min(BW, BH)))
        model.add(w[hub_idx] <= max_w_hub)
        model.add(h[hub_idx] <= max_h_hub)
        # Hub nie może rozciągać się od ściany do ściany na OBU wymiarach (= spine)
        not_full_w = model.new_bool_var("hub_not_full_w")
        not_full_h = model.new_bool_var("hub_not_full_h")
        model.add(w[hub_idx] <= BW - 100).only_enforce_if(not_full_w)
        model.add(h[hub_idx] <= BH - 100).only_enforce_if(not_full_h)
        model.add_bool_or([not_full_w, not_full_h])

        # Hub musi obejmować entry_point (drzwi wejściowe)
        bx0 = boundary.bbox[0]
        by0 = boundary.bbox[1]
        entry_x_cm = round((boundary.entry_point[0] - bx0) * SCALE)
        entry_y_cm = round((boundary.entry_point[1] - by0) * SCALE)

        # Hub zawiera punkt drzwi
        model.add(x[hub_idx] <= entry_x_cm)
        model.add(x_ends[hub_idx] >= entry_x_cm)
        model.add(y[hub_idx] <= entry_y_cm)
        model.add(y_ends[hub_idx] >= entry_y_cm)

        # Hub dotyka ściany z drzwiami (jeśli drzwi nie są wewnątrz notch-a)
        if notch is None:
            if entry_side == "south":
                model.add(y[hub_idx] == 0)
            elif entry_side == "north":
                model.add(y_ends[hub_idx] == BH)
            elif entry_side == "west":
                model.add(x[hub_idx] == 0)
            elif entry_side == "east":
                model.add(x_ends[hub_idx] == BW)

    # ====================================================================
    # Stage C: Facade constraints — pokoje z oknami na fasadzie
    # ====================================================================
    for i, spec in enumerate(specs):
        if not spec.wymaga_okna:
            continue
        _add_facade_constraint(model, i, x, y, x_ends, y_ends, w, h,
                               BW, BH, facade_sides,
                               notch=boundary.notch, notch_facades=notch_facades)

    # ====================================================================
    # Stage C+: Forced facade assignments (dla generowania wariantów)
    # ====================================================================
    if forced_facade:
        for room_id, side in forced_facade.items():
            idx = next((i for i, s in enumerate(specs) if s.id == room_id), None)
            if idx is None:
                continue
            if side == "south":
                model.add(y[idx] == 0)
            elif side == "north":
                model.add(y_ends[idx] == BH)
            elif side == "west":
                model.add(x[idx] == 0)
            elif side == "east":
                model.add(x_ends[idx] == BW)

    # ====================================================================
    # Stage C++: Block previous arrangements (różnorodność wariantów)
    # ====================================================================
    # Dzielimy boundary na siatkę 2x2 (4 kwadranty). Dla każdego zablokowanego
    # rozwiązania wymuszamy, żeby przynajmniej jeden pokój okienny (salon/sypialnia)
    # był w INNYM kwadrancie niż w zablokowanym rozwiązaniu.
    half_w = BW // 2
    half_h = BH // 2

    # Zmienne kwadrantowe dla każdego pokoju
    quadrant_vars: dict[int, list] = {}  # idx -> [q0, q1, q2, q3]
    for i in range(n):
        qvars = []
        for q in range(4):
            qv = model.new_bool_var(f"quad_{i}_{q}")
            qvars.append(qv)
        # Środek pokoju (x + w/2, y + h/2) wyznacza kwadrant
        # q0 = lewy-dolny, q1 = prawy-dolny, q2 = lewy-górny, q3 = prawy-górny
        cx = model.new_int_var(0, BW, f"cx_{i}")
        cy = model.new_int_var(0, BH, f"cy_{i}")
        # cx = x + w/2 (approx: x*2 + w) / 2 — używamy 2*cx = 2*x + w
        cx2 = model.new_int_var(0, 2 * BW, f"cx2_{i}")
        cy2 = model.new_int_var(0, 2 * BH, f"cy2_{i}")
        model.add(cx2 == 2 * x[i] + w[i])
        model.add(cy2 == 2 * y[i] + h[i])

        # q0: cx < half_w AND cy < half_h (lewy-dolny)
        model.add(cx2 < 2 * half_w).only_enforce_if(qvars[0])
        model.add(cy2 < 2 * half_h).only_enforce_if(qvars[0])
        # q1: cx >= half_w AND cy < half_h (prawy-dolny)
        model.add(cx2 >= 2 * half_w).only_enforce_if(qvars[1])
        model.add(cy2 < 2 * half_h).only_enforce_if(qvars[1])
        # q2: cx < half_w AND cy >= half_h (lewy-górny)
        model.add(cx2 < 2 * half_w).only_enforce_if(qvars[2])
        model.add(cy2 >= 2 * half_h).only_enforce_if(qvars[2])
        # q3: cx >= half_w AND cy >= half_h (prawy-górny)
        model.add(cx2 >= 2 * half_w).only_enforce_if(qvars[3])
        model.add(cy2 >= 2 * half_h).only_enforce_if(qvars[3])

        model.add_exactly_one(qvars)
        quadrant_vars[i] = qvars

    if blocked_arrangements:
        for arr_idx, arr in enumerate(blocked_arrangements):
            # Przynajmniej jeden pokój musi być w innym kwadrancie
            different_bools = []
            for i, spec in enumerate(specs):
                if spec.id in arr.room_quadrants:
                    prev_q = arr.room_quadrants[spec.id]
                    # Ten pokój jest w innym kwadrancie niż poprzednio
                    not_same = model.new_bool_var(f"diff_{arr_idx}_{i}")
                    model.add(quadrant_vars[i][prev_q] == 0).only_enforce_if(not_same)
                    different_bools.append(not_same)
            if different_bools:
                model.add_bool_or(different_bools)

    # ====================================================================
    # Stage D: Objective function
    # ====================================================================
    # Cel: minimalizuj odchylenia od optymalnych powierzchni + kary za proporcje

    # Q6 (DECIDED 2026-04-30): salon 80% nadmiaru, sypialnie 20% proporcjonalnie
    # do min, hub i pokoje usługowe stoją na opt z capem WT/F4.
    usable_area_m2 = usable_area / (SCALE * SCALE)
    targets_m2 = _compute_target_areas(specs, usable_area_m2)
    target_areas_cm2 = [round(targets_m2[s.id] * SCALE * SCALE) for s in specs]

    # Korekta: upewnij się że suma targetów == usable_area
    diff = usable_area - sum(target_areas_cm2)
    # Dodaj resztę do największego targetu
    if target_areas_cm2:
        biggest_idx = max(range(n), key=lambda i: target_areas_cm2[i])
        target_areas_cm2[biggest_idx] += diff

    # Zmienne odchyleń
    obj_terms = []

    for i, spec in enumerate(specs):
        target = target_areas_cm2[i]

        # |area_i - target| = area_dev_plus + area_dev_minus
        dev_plus = model.new_int_var(0, B_AREA, f"dev_plus_{i}")
        dev_minus = model.new_int_var(0, B_AREA, f"dev_minus_{i}")
        model.add(areas[i] - target == dev_plus - dev_minus)

        # Waga: łazienki/WC ważone 2x
        weight = 2 if spec.strefa == Strefa.USLUGOWA else 1
        obj_terms.append(weight * (dev_plus + dev_minus))

    # Kara za proporcje — minimalizuj |w-h| (faworyzuje kwadratowe pokoje)
    for i in range(n):
        prop_dev = model.new_int_var(0, max(BW, BH), f"prop_dev_{i}")
        # |w[i] - h[i]|
        diff_wh = model.new_int_var(-max(BW, BH), max(BW, BH), f"diff_wh_{i}")
        model.add(diff_wh == w[i] - h[i])
        model.add_abs_equality(prop_dev, diff_wh)
        # Skaluj proporcjonalnie (mniejszy pokój = mniejsza kara absolutna)
        obj_terms.append(prop_dev)

    # Hub: kara za nadmiar powierzchni (>12%)
    if hub_idx is not None:
        hub_target_12pct = round(0.12 * usable_area)
        hub_excess = model.new_int_var(0, B_AREA, f"hub_excess")
        hub_diff = model.new_int_var(-B_AREA, B_AREA, f"hub_diff")
        model.add(hub_diff == areas[hub_idx] - hub_target_12pct)
        # Kara tylko za nadmiar (>12%), nie za niedostatek
        model.add_max_equality(hub_excess, [hub_diff, model.new_constant(0)])
        obj_terms.append(3 * hub_excess)

    model.minimize(sum(obj_terms))

    # ====================================================================
    # Solve
    # ====================================================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    # Zakończ wcześniej jeśli rozwiązanie jest bliskie optimum (gap < 5%)
    solver.parameters.relative_gap_limit = 0.05

    status = solver.solve(model)

    elapsed = time.monotonic() - t0

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, "UNKNOWN")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return CpsatResult(status=status_name, solve_time_s=elapsed)

    # --- Wyciągnij rozwiązanie ---
    bx0 = boundary.bbox[0]
    by0 = boundary.bbox[1]

    rooms = []
    for i, spec in enumerate(specs):
        rx0 = solver.value(x[i]) / SCALE + bx0
        ry0 = solver.value(y[i]) / SCALE + by0
        rx1 = solver.value(x_ends[i]) / SCALE + bx0
        ry1 = solver.value(y_ends[i]) / SCALE + by0

        poly = box(rx0, ry0, rx1, ry1)
        room = Room(spec=spec, polygon=poly)
        room.update_metrics()
        rooms.append(room)

    # --- Wyciągnij arrangement (topologię) do blokowania ---
    arrangement = RoomArrangement()
    for i, spec in enumerate(specs):
        for q in range(4):
            if solver.value(quadrant_vars[i][q]):
                arrangement.room_quadrants[spec.id] = q
                break

    return CpsatResult(
        status=status_name,
        rooms=rooms,
        solve_time_s=elapsed,
        objective_value=solver.objective_value if status == cp_model.OPTIMAL else 0.0,
        arrangement=arrangement,
    )


def _add_adjacency_constraint(
    model: cp_model.CpModel,
    a: int, b: int,
    x, y, w, h, x_ends, y_ends,
    BW: int, BH: int,
    min_shared: int,
):
    """Dodaj ograniczenie sąsiedztwa: pokoje a i b muszą współdzielić krawędź.

    4 przypadki (OR):
    - a na lewo od b: x_end[a] == x[b] AND overlap_y >= min_shared
    - a na prawo od b: x_end[b] == x[a] AND overlap_y >= min_shared
    - a poniżej b: y_end[a] == y[b] AND overlap_x >= min_shared
    - a powyżej b: y_end[b] == y[a] AND overlap_x >= min_shared
    """
    # Boolean dla każdego przypadku
    b_left = model.new_bool_var(f"adj_{a}_{b}_left")
    b_right = model.new_bool_var(f"adj_{a}_{b}_right")
    b_below = model.new_bool_var(f"adj_{a}_{b}_below")
    b_above = model.new_bool_var(f"adj_{a}_{b}_above")

    # Przynajmniej jeden przypadek musi być prawdziwy
    model.add_bool_or([b_left, b_right, b_below, b_above])

    # --- CASE: a na lewo od b ---
    # x_end[a] == x[b]
    model.add(x_ends[a] == x[b]).only_enforce_if(b_left)
    # overlap_y = min(y_end[a], y_end[b]) - max(y[a], y[b]) >= min_shared
    _add_overlap_constraint(model, y[a], y_ends[a], y[b], y_ends[b],
                            min_shared, BH, b_left, f"adj_{a}_{b}_left")

    # --- CASE: a na prawo od b ---
    model.add(x_ends[b] == x[a]).only_enforce_if(b_right)
    _add_overlap_constraint(model, y[a], y_ends[a], y[b], y_ends[b],
                            min_shared, BH, b_right, f"adj_{a}_{b}_right")

    # --- CASE: a poniżej b ---
    model.add(y_ends[a] == y[b]).only_enforce_if(b_below)
    _add_overlap_constraint(model, x[a], x_ends[a], x[b], x_ends[b],
                            min_shared, BW, b_below, f"adj_{a}_{b}_below")

    # --- CASE: a powyżej b ---
    model.add(y_ends[b] == y[a]).only_enforce_if(b_above)
    _add_overlap_constraint(model, x[a], x_ends[a], x[b], x_ends[b],
                            min_shared, BW, b_above, f"adj_{a}_{b}_above")


def _add_overlap_constraint(
    model: cp_model.CpModel,
    start_a, end_a, start_b, end_b,
    min_overlap: int,
    max_val: int,
    enforcer,
    prefix: str,
):
    """Dodaj ograniczenie: overlap(interval_a, interval_b) >= min_overlap.

    overlap = min(end_a, end_b) - max(start_a, start_b)
    """
    # min_end = min(end_a, end_b)
    min_end = model.new_int_var(0, max_val, f"{prefix}_min_end")
    model.add_min_equality(min_end, [end_a, end_b])

    # max_start = max(start_a, start_b)
    max_start = model.new_int_var(0, max_val, f"{prefix}_max_start")
    model.add_max_equality(max_start, [start_a, start_b])

    # overlap = min_end - max_start >= min_overlap
    model.add(min_end - max_start >= min_overlap).only_enforce_if(enforcer)


def _add_facade_constraint(
    model: cp_model.CpModel,
    i: int,
    x, y, x_ends, y_ends, w, h,
    BW: int, BH: int,
    facade_sides: dict[str, bool],
    notch=None, notch_facades: dict[str, bool] = None,
):
    """Pokój i musi dotykać przynajmniej jednej fasady.

    Fasady mogą być:
    - na bbox boundary (south/north/east/west) — pokój dotyka brzegu bbox
    - na krawędzi notch (upper/lower/left/right) — pokój dotyka wewnętrznej krawędzi
      L/U-shape (np. okno na "wcięciu" mieszkania)
    """
    facade_bools = []

    if facade_sides.get("south", False):
        b_s = model.new_bool_var(f"facade_{i}_south")
        model.add(y[i] == 0).only_enforce_if(b_s)
        facade_bools.append(b_s)

    if facade_sides.get("north", False):
        b_n = model.new_bool_var(f"facade_{i}_north")
        model.add(y_ends[i] == BH).only_enforce_if(b_n)
        facade_bools.append(b_n)

    if facade_sides.get("west", False):
        b_w = model.new_bool_var(f"facade_{i}_west")
        model.add(x[i] == 0).only_enforce_if(b_w)
        facade_bools.append(b_w)

    if facade_sides.get("east", False):
        b_e = model.new_bool_var(f"facade_{i}_east")
        model.add(x_ends[i] == BW).only_enforce_if(b_e)
        facade_bools.append(b_e)

    # Notch facades — okno na wewnętrznej krawędzi L/U-shape
    if notch is not None and notch_facades:
        nx_cm = round(notch.x * SCALE)
        ny_cm = round(notch.y * SCALE)
        nw_cm = round(notch.width * SCALE)
        nh_cm = round(notch.height * SCALE)
        nx_end_cm = nx_cm + nw_cm
        ny_end_cm = ny_cm + nh_cm

        # upper: krawędź notch na y=ny+nh, pokój NAD notch dotyka jej dolną krawędzią
        if notch_facades.get("upper", False):
            b = model.new_bool_var(f"facade_{i}_notch_upper")
            model.add(y[i] == ny_end_cm).only_enforce_if(b)
            # Pokój X-range w obrębie notch X-range (cały pokój nad notch)
            model.add(x[i] >= nx_cm).only_enforce_if(b)
            model.add(x_ends[i] <= nx_end_cm).only_enforce_if(b)
            facade_bools.append(b)

        # lower: krawędź notch na y=ny, pokój POD notch dotyka jej górną krawędzią
        if notch_facades.get("lower", False):
            b = model.new_bool_var(f"facade_{i}_notch_lower")
            model.add(y_ends[i] == ny_cm).only_enforce_if(b)
            model.add(x[i] >= nx_cm).only_enforce_if(b)
            model.add(x_ends[i] <= nx_end_cm).only_enforce_if(b)
            facade_bools.append(b)

        # left: krawędź notch na x=nx, pokój NA LEWO dotyka prawą krawędzią
        if notch_facades.get("left", False):
            b = model.new_bool_var(f"facade_{i}_notch_left")
            model.add(x_ends[i] == nx_cm).only_enforce_if(b)
            model.add(y[i] >= ny_cm).only_enforce_if(b)
            model.add(y_ends[i] <= ny_end_cm).only_enforce_if(b)
            facade_bools.append(b)

        # right: krawędź notch na x=nx+nw, pokój NA PRAWO dotyka lewą krawędzią
        if notch_facades.get("right", False):
            b = model.new_bool_var(f"facade_{i}_notch_right")
            model.add(x[i] == nx_end_cm).only_enforce_if(b)
            model.add(y[i] >= ny_cm).only_enforce_if(b)
            model.add(y_ends[i] <= ny_end_cm).only_enforce_if(b)
            facade_bools.append(b)

    if facade_bools:
        model.add_bool_or(facade_bools)
