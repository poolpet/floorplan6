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
from core.house_program import HouseProgramConfig, compute_house_targets
from rules._loader import get_default_pack as _get_default_pack

_PACK = _get_default_pack()
WT_MAX_AREA = _PACK.constants["wt_max_area"]


# Precyzja: 1 cm (wymiary w cm jako int dla CP-SAT)
SCALE = 100  # metry -> cm

# Minimalna wspólna krawędź do uznania sąsiedztwa [cm]
# 90cm = szerokość drzwi standardowych
MIN_SHARED_EDGE_CM = 90

# Korytarz/komunikacja: min szerokość 1.2 m (Dawid S31b — realizm rzutu; ramię L huba
# schodziło do 0.8 m → za wąsko). Wyjątkowo 1.0 m, gdy 1.2 czyni układ INFEASIBLE
# (callery domu/parterowca robią retry z floor=MIN_CORRIDOR_EXCEPTIONAL_CM). NIGDY <1.0.
MIN_CORRIDOR_CM = 120
MIN_CORRIDOR_EXCEPTIONAL_CM = 100


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


# Cap otwartej strefy dziennej mieszkania (salon_aneks). Bez niego Q6 (salon = min +
# 80% nadmiaru) dawało gigant 84 m² na 124 m² (render Dawida 2026-06-09). Nadmiar ponad
# cap przepychany do sypialni. EDYTOWALNE — dostroić na rzutach (ARCHON: salon 35 + aneks).
# Tylko mieszkania (domy mają osobny compute_house_targets z DEFAULT_HOUSE_CAPS).
APARTMENT_DAY_ZONE_CAP = 45.0


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

    # Pozostałe pokoje (nie service/hub/salon/sypialnia, np. kuchnia, kotłownia,
    # spiżarnia, wiatrołap, garderoba w programie domu) stoją na opt/min — to ich
    # baseline w dystrybucji nadmiaru poniżej. Bez tego KeyError na rozszerzonych
    # szablonach (house_parter/house_pietro).
    others = [s for s in specs
              if s.id not in targets and s not in salons and s not in sypialnie]
    for spec in others:
        targets[spec.id] = spec.opt_powierzchnia or spec.min_powierzchnia

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
    # Q6: salon bierze 80% nadmiaru — ALE z capem (salon_aneks nie pęcznieje w nieskończoność).
    # Nadmiar ponad cap przepychany do sypialni.
    salon_cap = APARTMENT_DAY_ZONE_CAP if "aneks" in salon.id else float("inf")
    salon_take = min(0.8 * excess, max(0.0, salon_cap - salon.min_powierzchnia))
    targets[salon.id] = salon.min_powierzchnia + salon_take
    syp_excess = excess - salon_take
    # Sypialnie: water-filling do RÓWNEGO rozmiaru (nadmiar podnosi najmniejsze najpierw),
    # NIE proporcjonalnie do min — to dawało 7.5 vs 27 (render Dawida 2026-06-09).
    _water_fill(targets, sypialnie, syp_mins, sum(syp_mins) + syp_excess)
    return targets


def _water_fill(targets, specs, mins, total):
    """Rozdziel `total` m² na pokoje tak, by były jak najrówniejsze (każdy ≥ swój min).

    Szuka poziomu wody T (binsearch): pole pokoju = max(min_i, T), suma == total.
    Pokoje o dużym min zostają na min, mniejsze podnoszone do T → wyrównanie.
    """
    lo, hi = 0.0, total
    for _ in range(60):
        T = (lo + hi) / 2.0
        if sum(max(m, T) for m in mins) < total:
            lo = T
        else:
            hi = T
    T = (lo + hi) / 2.0
    for spec, m in zip(specs, mins):
        targets[spec.id] = max(m, T)


def solve_cpsat(
    template: Template,
    boundary: Boundary,
    time_limit_s: float = 30.0,
    forced_facade: Optional[dict[str, str]] = None,
    blocked_arrangements: Optional[list[RoomArrangement]] = None,
    reserved_core: Optional[tuple[float, float, float, float]] = None,
    low_zones: Optional[list[tuple[float, float, float, float]]] = None,
    program_config: Optional[HouseProgramConfig] = None,
    stair_room_id: Optional[str] = None,
    hub_at_entry: bool = True,
    entry_room_id: Optional[str] = None,
    l_capable_ids: Optional[set] = None,
    external_bathroom_id: str = "wc",
    corridor_min_cm: int = MIN_CORRIDOR_CM,
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
        reserved_core: (x, y, w, h) in metres, bbox-relative, that the hub must
            fully contain (e.g. shared staircase rectangle in a 2-storey house).
            None = off — zero behaviour change for existing apartment flows M1–M5.
        stair_room_id: id pokoju klatki schodowej (Approach B, dom). Gdy ustawione
            RAZEM z reserved_core, ten pokój jest PRZYPIĘTY do prostokąta rdzenia
            (4 równości x/y/w/h), z pominięciem reguły proporcji — a containment
            rdzenia przechodzi z huba na ten pokój. None = stary fallback (hub
            zawiera rdzeń); inert dla mieszkań M1–M5.

    Returns:
        CpsatResult z pokojami (Room z polygon w metrach).
    """
    t0 = time.monotonic()

    # --- Wymiary boundary w cm (int) ---
    BW = round(boundary.width * SCALE)
    BH = round(boundary.height * SCALE)
    B_AREA = BW * BH  # cm²

    # Wąskie mieszkanie (lokal z korytarza, krótki bok ≤6 m): hol dostaje kształt L
    # (patrz auto-l_capable niżej) — bez tego prostokątny hol na wąskim obrysie tyje/pada.
    # Tylko mieszkania (program_config is None); domy mają osobny model holu.
    NARROW_APT_CM = 600
    narrow_apt = program_config is None and min(BW, BH) <= NARROW_APT_CM

    n = len(template.pokoje)
    specs = template.pokoje

    # --- Klatka schodowa (Approach B): pokój przypięty do rdzenia ---
    stair_idx = None
    core_cm = None
    if reserved_core is not None:
        rc_x, rc_y, rc_w, rc_h = reserved_core
        core_cm = (round(rc_x * SCALE), round(rc_y * SCALE),
                   round(rc_w * SCALE), round(rc_h * SCALE))
        if stair_room_id is not None:
            stair_idx = next((i for i, s in enumerate(specs) if s.id == stair_room_id), None)

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
        # Korytarz (KOMUNIKACJA) ma podwyższony floor szerokości (S31b: 1.2 m default);
        # pozostałe pokoje min 1 m. Floor stosuje się do KAŻDEGO wymiaru, więc prostokąt
        # holu nie może być węższy niż korytarz.
        floor_cm = corridor_min_cm if spec.strefa == Strefa.KOMUNIKACJA else 100
        min_dim_cm = max(round(spec.min_szerokosc * SCALE), floor_cm)

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

        # --- Klatka schodowa (Approach B): przypnij do rdzenia, pomiń proporcję ---
        # Pin = 4 równości na rdzeń (gwarancja wyrównania pionowego parter↔piętro).
        # Bieg prosty (np. 4.0×1.1) ma proporcję > max_proporcja → MUSI pominąć aspect.
        if i == stair_idx and core_cm is not None:
            csx, csy, cw_cm, ch_cm = core_cm
            model.add(xi == csx)
            model.add(yi == csy)
            model.add(wi == cw_cm)
            model.add(hi == ch_cm)
        else:
            # --- Aspect ratio <= 2:1 ---
            # w <= 2*h AND h <= 2*w
            max_ratio_num = round(spec.max_proporcja * 100)
            # w * 100 <= max_ratio * h  =>  w*100 <= max_ratio_num * h
            model.add(wi * 100 <= max_ratio_num * hi)
            model.add(hi * 100 <= max_ratio_num * wi)

    # Zmienne area — JEDEN produkt w·h per pokój, z widełkami [min, cap-WT].
    # (Dawniej dublowane: area_{i} z widełkami + area_ref_{i} bez — 2× enkodowanie
    # produktu i utrata propagacji dolnej granicy w pokryciu; perf S28.)
    areas = []
    for i, spec in enumerate(specs):
        min_area_cm2 = round(spec.min_powierzchnia * SCALE * SCALE)
        # F2 (FUNDAMENTAL_RULES): twardy cap WT dla łazienki/WC ma pierwszeństwo nad procent_powierzchni
        upper_bound = BW * BH
        key = spec.id.split("_")[0]  # "lazienka_2" -> "lazienka"
        if key in WT_MAX_AREA:
            upper_bound = min(upper_bound, round(WT_MAX_AREA[key] * SCALE * SCALE))
        ai = model.new_int_var(min_area_cm2, upper_bound, f"area_{i}")
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

    # Wąskie mieszkanie → hol L-kształtny ("mini-korytarz", decyzja Dawida S26). Bez tego
    # na obrysie ≤6 m prostokątny hol musi sięgnąć od salonu (góra) do łazienki/sypialni
    # (dół) i rozdyma się do ~24% (>F4) — a przy wejściu w centrum krótkiej ściany jest
    # INFEASIBLE. Cienki L owija łazienkę, dotyka wszystkich pokoi mniejszym polem (~14%)
    # i jest feasible niezależnie od pozycji drzwi. Auto-włączenie nadpisywalne jawnym
    # l_capable_ids; tylko mieszkania (program_config is None → narrow_apt).
    if narrow_apt and not l_capable_ids:
        hub_spec_id = next((s.id for s in specs if s.strefa == Strefa.KOMUNIKACJA), None)
        if hub_spec_id is not None:
            l_capable_ids = {hub_spec_id}

    # === Approach 2b: opcjonalny 2. prostokąt dla pokoi L-capable (hol/sypialnie) ===
    # Każdy L-capable pokój może być unią 2 prostokątów (L) lub zostać prostokątem.
    # Bramkowane l_capable_ids — None/pusty ⇒ brak L, zachowanie IDENTYCZNE (mieszkania też).
    x2 = [None] * n; y2 = [None] * n; w2 = [None] * n; h2 = [None] * n
    x2e = [None] * n; y2e = [None] * n; has_L = [None] * n; eff2 = [None] * n
    if l_capable_ids:
        for i, spec in enumerate(specs):
            if spec.id not in l_capable_ids:
                continue
            p = model.new_bool_var(f"hasL_{i}"); has_L[i] = p
            xi2 = model.new_int_var(0, BW, f"x2_{i}"); yi2 = model.new_int_var(0, BH, f"y2_{i}")
            wi2 = model.new_int_var(0, BW, f"w2_{i}"); hi2 = model.new_int_var(0, BH, f"h2_{i}")
            xe2 = model.new_int_var(0, BW, f"x2e_{i}"); ye2 = model.new_int_var(0, BH, f"y2e_{i}")
            model.add(xe2 == xi2 + wi2); model.add(ye2 == yi2 + hi2)
            x2[i], y2[i], w2[i], h2[i], x2e[i], y2e[i] = xi2, yi2, wi2, hi2, xe2, ye2
            xiv2 = model.new_optional_interval_var(xi2, wi2, xe2, p, f"xiv2_{i}")
            yiv2 = model.new_optional_interval_var(yi2, hi2, ye2, p, f"yiv2_{i}")
            x_intervals.append(xiv2); y_intervals.append(yiv2)
            model.add(wi2 == 0).only_enforce_if(p.Not())     # brak L ⇒ rect2 = nic
            model.add(hi2 == 0).only_enforce_if(p.Not())
            model.add(wi2 >= corridor_min_cm).only_enforce_if(p)  # L ⇒ ramię korytarza ≥ 1.2 m (S31b)
            model.add(hi2 >= corridor_min_cm).only_enforce_if(p)
            t_contig = _touches_bool(model, x[i], y[i], x_ends[i], y_ends[i],
                                     xi2, yi2, xe2, ye2, MIN_SHARED_EDGE_CM, BW, BH, f"contig_{i}")
            model.add(t_contig == 1).only_enforce_if(p)       # L ⇒ 2 prostokąty ciągłe
            a2 = model.new_int_var(0, BW * BH, f"area2_{i}")
            model.add_multiplication_equality(a2, [wi2, hi2])
            ea2 = model.new_int_var(0, BW * BH, f"effarea2_{i}")
            model.add(ea2 == a2).only_enforce_if(p)
            model.add(ea2 == 0).only_enforce_if(p.Not())
            eff2[i] = ea2

    model.add_no_overlap_2d(x_intervals, y_intervals)

    # --- Coverage: suma area (+ obecne 2. prostokąty L) == usable area (boundary - notch) ---
    if notch is not None:
        notch_area_cm2 = nw * nh  # integer cm, bez błędów zaokrąglenia
    else:
        notch_area_cm2 = 0
    usable_area = B_AREA - notch_area_cm2
    model.add(sum(areas) + sum(e for e in eff2 if e is not None) == usable_area)

    # ====================================================================
    # Stage B: Adjacency constraints
    # ====================================================================
    hub_idx = None
    for i, spec in enumerate(specs):
        if spec.strefa == Strefa.KOMUNIKACJA:
            hub_idx = i
            break

    # Pokój przy wejściu (zawiera drzwi + dotyka ściany wejścia). Dom: WIATROŁAP
    # (przedsionek/airlock — przez niego się wchodzi), NIE hol. Mieszkania: hub (default).
    entry_idx = hub_idx
    if entry_room_id is not None:
        entry_idx = next((i for i, s in enumerate(specs) if s.id == entry_room_id), hub_idx)

    # Zbuduj zbiór wymaganych sąsiedztw (pomijając _outside)
    required_adj: list[tuple[int, int]] = []
    for rule in template.sasiedztwo:
        if rule.room_a == "_outside" or rule.room_b == "_outside":
            continue
        idx_a = next((i for i, s in enumerate(specs) if s.id == rule.room_a), None)
        idx_b = next((i for i, s in enumerate(specs) if s.id == rule.room_b), None)
        if idx_a is not None and idx_b is not None:
            required_adj.append((idx_a, idx_b))

    # Adjacency constraint: dwa pokoje muszą współdzielić krawędź o długości >= MIN_SHARED_EDGE.
    # Pokoje L-capable (2 prostokąty) → sąsiedztwo przez którykolwiek prostokąt; reszta bez zmian.
    for (a, b) in required_adj:
        if l_capable_ids and (has_L[a] is not None or has_L[b] is not None):
            _apply_adjacency(model, a, b, x, y, x_ends, y_ends,
                             x2, y2, x2e, y2e, has_L, BW, BH, MIN_SHARED_EDGE_CM)
        else:
            _add_adjacency_constraint(model, a, b, x, y, w, h, x_ends, y_ends,
                                      BW, BH, MIN_SHARED_EDGE_CM)

    # ====================================================================
    # Stage B+: Hub musi dotykać KAŻDEGO pokoju (nawet jeśli nie jest explicite w sasiedztwo)
    # ====================================================================
    # Mieszkania M1-M5 (program_config is None): zachowaj heurystykę auto-star
    # (hub dotyka wszystkich). DOM (program_config != None): polegaj na jawnym grafie
    # ARCHON z szablonu (hol-centryczny) — open-plan kuchnia idzie przez salon, nie hol,
    # więc nie wymuszamy hol↔kuchnia/spiżarnia (to zawieszało pinned schody na ciasnym
    # obrysie). F5 dalej spełnione: każdy pokój osiągalny przez graf sąsiedztwa.
    if hub_idx is not None and program_config is None:
        for i in range(n):
            if i == hub_idx:
                continue
            pair = (hub_idx, i)
            if pair not in required_adj and (i, hub_idx) not in required_adj:
                # L-aware gdy hol (lub pokój) jest L-capable — pokój może dotykać
                # KTÓREGOKOLWIEK ramienia L holu, nie tylko prostokąta podstawowego.
                if l_capable_ids and (has_L[hub_idx] is not None or has_L[i] is not None):
                    _apply_adjacency(model, hub_idx, i, x, y, x_ends, y_ends,
                                     x2, y2, x2e, y2e, has_L, BW, BH, MIN_SHARED_EDGE_CM)
                else:
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

        # Hub przy wejściu — TYLKO gdy ta kondygnacja MA drzwi zewnętrzne (parter,
        # mieszkania). Piętro domu (hub_at_entry=False) NIE ma drzwi: podest łączy się
        # ze schodami, nie z fasadą wejścia — wymuszanie hol↔ściana wejścia robiło
        # piętro INFEASIBLE dla wejść W/E na 9×7/10×7 (3 sypialnie z oknami nie mieściły się).
        if hub_at_entry and entry_idx is not None:
            bx0 = boundary.bbox[0]
            by0 = boundary.bbox[1]
            entry_x_cm = round((boundary.entry_point[0] - bx0) * SCALE)
            entry_y_cm = round((boundary.entry_point[1] - by0) * SCALE)

            # Pokój wejściowy (dom: WIATROŁAP) zawiera punkt drzwi...
            model.add(x[entry_idx] <= entry_x_cm)
            model.add(x_ends[entry_idx] >= entry_x_cm)
            model.add(y[entry_idx] <= entry_y_cm)
            model.add(y_ends[entry_idx] >= entry_y_cm)

            # ...i dotyka ściany z drzwiami (jeśli drzwi nie są wewnątrz notch-a)
            if notch is None:
                if entry_side == "south":
                    model.add(y[entry_idx] == 0)
                elif entry_side == "north":
                    model.add(y_ends[entry_idx] == BH)
                elif entry_side == "west":
                    model.add(x[entry_idx] == 0)
                elif entry_side == "east":
                    model.add(x_ends[entry_idx] == BW)

        # Reserved core: fallback (brak osobnego pokoju schodów) — hub zawiera rdzeń.
        # Gdy stair_idx ustawione (Approach B), rdzeń przejmuje przypięty pokój
        # "schody", więc tu NIE obciążamy huba — hol może być mały.
        if reserved_core is not None and stair_idx is None:
            cx, cy, cw, ch = reserved_core
            csx = round(cx * SCALE)
            csy = round(cy * SCALE)
            cex = round((cx + cw) * SCALE)
            cey = round((cy + ch) * SCALE)
            model.add(x[hub_idx] <= csx)
            model.add(x_ends[hub_idx] >= cex)
            model.add(y[hub_idx] <= csy)
            model.add(y_ends[hub_idx] >= cey)

    # WC domu dotyka ≥1 ściany ZEWNĘTRZNEJ (nie landlocked). Reguła Dawida — feasible bez
    # rozdęcia korytarza dzięki L-capable hub (faza 2b), który owija WC ramieniem o min. polu.
    # (Wiatrołap-przy-ścianie-wejścia obsługuje teraz blok entry_idx: gdy entry_room_id="wiatrolap"
    # to wiatrołap zawiera punkt drzwi I dotyka ściany wejścia — drzwi SĄ w przedsionku, hol za nim.)
    if program_config is not None and notch is None:
        bath_idx = next((i for i, s in enumerate(specs) if s.id == external_bathroom_id), None)
        if bath_idx is not None:
            bW = model.new_bool_var("bath_W"); model.add(x[bath_idx] == 0).only_enforce_if(bW)
            bE = model.new_bool_var("bath_E"); model.add(x_ends[bath_idx] == BW).only_enforce_if(bE)
            bS = model.new_bool_var("bath_S"); model.add(y[bath_idx] == 0).only_enforce_if(bS)
            bN = model.new_bool_var("bath_N"); model.add(y_ends[bath_idx] == BH).only_enforce_if(bN)
            model.add_bool_or([bW, bE, bS, bN])

    # Knee-wall v2 (S29): strefy niskiej ścianki kolankowej poddasza (low_zones,
    # bbox-relative metry). Żaden pokój nie może być W CAŁOŚCI w strefie (wysokość
    # < ~1.9 m wszędzie = pokój bezużyteczny) — musi wystawać poza nią z DOWOLNEJ
    # z 4 stron. WYJĄTEK: pokój schodów (stair_idx) — po schodach wchodzi się
    # stopniowo, dolne stopnie nie potrzebują pełnej wysokości (decyzja Dawida S29).
    if low_zones:
        for zi, (zx0, zy0, zx1, zy1) in enumerate(low_zones):
            zx0c, zy0c = round(zx0 * SCALE), round(zy0 * SCALE)
            zx1c, zy1c = round(zx1 * SCALE), round(zy1 * SCALE)
            for i in range(n):
                if i == stair_idx:
                    continue
                esc_l = model.new_bool_var(f"lz{zi}_{i}_l")
                model.add(x[i] <= zx0c - 1).only_enforce_if(esc_l)
                esc_r = model.new_bool_var(f"lz{zi}_{i}_r")
                model.add(x_ends[i] >= zx1c + 1).only_enforce_if(esc_r)
                esc_b = model.new_bool_var(f"lz{zi}_{i}_b")
                model.add(y[i] <= zy0c - 1).only_enforce_if(esc_b)
                esc_t = model.new_bool_var(f"lz{zi}_{i}_t")
                model.add(y_ends[i] >= zy1c + 1).only_enforce_if(esc_t)
                model.add_bool_or([esc_l, esc_r, esc_b, esc_t])

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

    # Zmienne kwadrantowe TYLKO gdy są zablokowane układy (warianty 2+). Pierwszy
    # wariant i domy nie mają blocked_arrangements — kwadranty wyniku liczone
    # post-hoc w Pythonie (_quadrant_of), bez 6 zmiennych + 10 reifikacji per pokój
    # w modelu (perf S28; semantyka blokowania bez zmian).
    quadrant_vars: dict[int, list] = {}  # idx -> [q0, q1, q2, q3]
    if blocked_arrangements:
        for i in range(n):
            qvars = []
            for q in range(4):
                qv = model.new_bool_var(f"quad_{i}_{q}")
                qvars.append(qv)
            # Środek pokoju (x + w/2, y + h/2) wyznacza kwadrant
            # q0 = lewy-dolny, q1 = prawy-dolny, q2 = lewy-górny, q3 = prawy-górny
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
    if program_config is not None:
        # Dom: cap + %-podział (ARCHON), resztę do huba — NIE do salonu/mastera (Q6 było błędne dla domów)
        targets_m2 = compute_house_targets(specs, usable_area_m2, program_config)
    else:
        targets_m2 = _compute_target_areas(specs, usable_area_m2)
    target_areas_cm2 = [round(targets_m2[s.id] * SCALE * SCALE) for s in specs]

    # Schody (Approach B): target = DOKŁADNE pole rdzenia (pin), żeby objective nie
    # walczył z przypięciem; resztę i tak przejmie hub w korekcie diff niżej.
    if stair_idx is not None and core_cm is not None:
        target_areas_cm2[stair_idx] = core_cm[2] * core_cm[3]

    # Korekta: upewnij się że suma targetów == usable_area
    diff = usable_area - sum(target_areas_cm2)
    if target_areas_cm2:
        if program_config is not None and hub_idx is not None:
            # Dom: korektę (zaokrąglenia) bierze największy pokój NIE-hub (korytarz minimalny).
            non_hub = [i for i in range(n) if i != hub_idx]
            biggest_idx = max(non_hub, key=lambda i: target_areas_cm2[i]) if non_hub else hub_idx
            target_areas_cm2[biggest_idx] += diff
        else:
            # Mieszkania (Q6): reszta do największego targetu
            biggest_idx = max(range(n), key=lambda i: target_areas_cm2[i])
            target_areas_cm2[biggest_idx] += diff

    # Pasma programu (S29): dom trzyma pokoje ≤1.35·TARGET (sufit anty-pompowanie;
    # poza hubem-sinkiem i pinned schodami), a SYPIALNIE dodatkowo ≥0.7·TARGET
    # (balans-od-dołu: bez tego solver na dużych obrysach oddawał 43.7 vs 12.4 mimo
    # zbalansowanych targetów). Dolne pasmo TYLKO dla sypialni — pełne pasma na
    # wszystkich pokojach usztywniały feasibility ≥120 m² (UNKNOWN); usługi/salon
    # zostają elastyczne. Korpus: balans sypialni max/min ≤ ~2 (A01_120: 1.83).
    if program_config is not None:
        for i, spec in enumerate(specs):
            if i in (hub_idx, stair_idx):
                continue
            t = target_areas_cm2[i]
            min_a = round(spec.min_powierzchnia * SCALE * SCALE)
            ub = max(round(1.35 * t), min_a)
            key = spec.id.split("_")[0]
            if key in WT_MAX_AREA:  # F2: twardy cap WT ma pierwszeństwo nad pasmem
                ub = min(ub, round(WT_MAX_AREA[key] * SCALE * SCALE))
            model.add(areas[i] <= ub)
            if key == "sypialnia":
                lb = min(max(min_a, round(0.7 * t)), ub)
                model.add(areas[i] >= lb)

    # Zmienne odchyleń
    obj_terms = []

    for i, spec in enumerate(specs):
        target = target_areas_cm2[i]

        # |area_i - target| = area_dev_plus + area_dev_minus (pokoje L: CAŁKOWITE pole)
        dev_plus = model.new_int_var(0, B_AREA, f"dev_plus_{i}")
        dev_minus = model.new_int_var(0, B_AREA, f"dev_minus_{i}")
        tot_area_i = areas[i] if eff2[i] is None else (areas[i] + eff2[i])
        model.add(tot_area_i - target == dev_plus - dev_minus)

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

    # Hub: kara za nadmiar powierzchni (>12%) — F4 "korytarz możliwie najmniejszy"
    # (reguła Dawida). Mieszkania M1-M5 ZAWSZE; DOM też — bo nadmiar idzie teraz do
    # SYPIALNI/strefy dziennej (house_program), NIE do huba, więc kara nie ma z czym walczyć
    # i utrzymuje korytarz minimalny (sesja 18 błędnie ją wyłączała, robiąc hub sinkiem).
    if hub_idx is not None:
        hub_target_12pct = round(0.12 * usable_area)
        hub_excess = model.new_int_var(0, B_AREA, f"hub_excess")
        hub_diff = model.new_int_var(-B_AREA, B_AREA, f"hub_diff")
        hub_tot = areas[hub_idx] if eff2[hub_idx] is None else (areas[hub_idx] + eff2[hub_idx])
        model.add(hub_diff == hub_tot - hub_target_12pct)
        # Kara tylko za nadmiar (>12%), nie za niedostatek
        model.add_max_equality(hub_excess, [hub_diff, model.new_constant(0)])
        obj_terms.append(3 * hub_excess)

    # Miękka preferencja (Dawid 2026-06-03): kotłownia + garderoba przy ścianie ZEWNĘTRZNEJ
    # (kotłownia — dopływ świeżego powietrza; garderoba — okno). NAGRODA w objective, NIE
    # twarde — solver woli ścianę, ale ustąpi gdy obrys każe inaczej ("w miarę możliwości").
    # Dom only (program_config) + brak notcha. Pozycja nie wpływa na area_dev, więc nagroda
    # konkuruje głównie z proporcjami/upakowaniem — nie zniekształca metraży. Hol BEZ wymogu.
    if program_config is not None and notch is None:
        # 0.06 (było 0.03): pasma programu (S29) zmniejszyły skalę odchyleń pól,
        # przez co nagroda 0.03 przegrywała z dopasowaniem i kotłownia lądowała
        # w środku NA PRZESTRONNYM obrysie. Nadal soft — ustępuje na ciasnych.
        w_ext = max(1, round(0.06 * B_AREA))
        for rid in ("kotlownia", "garderoba"):
            idx = next((i for i, s in enumerate(specs) if s.id == rid), None)
            if idx is None:
                continue
            bW = model.new_bool_var(f"{rid}_extW"); model.add(x[idx] == 0).only_enforce_if(bW)
            bE = model.new_bool_var(f"{rid}_extE"); model.add(x_ends[idx] == BW).only_enforce_if(bE)
            bS = model.new_bool_var(f"{rid}_extS"); model.add(y[idx] == 0).only_enforce_if(bS)
            bN = model.new_bool_var(f"{rid}_extN"); model.add(y_ends[idx] == BH).only_enforce_if(bN)
            at_ext = model.new_bool_var(f"{rid}_at_ext")
            model.add(at_ext <= bW + bE + bS + bN)   # =1 tylko gdy faktycznie przy ścianie
            obj_terms.append(-w_ext * at_ext)        # nagroda za ścianę zewnętrzną

    model.minimize(sum(obj_terms))

    # ====================================================================
    # Solve
    # ====================================================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    # Zakończ wcześniej jeśli rozwiązanie jest bliskie optimum (gap < 5%)
    solver.parameters.relative_gap_limit = 0.05
    # Pakowanie prostokątów: energetyczne wnioskowanie + timetabling w NoOverlap2D
    # drastycznie skracają czas-do-pierwszego-rozwiązania (perf S28: parter ~130 m²
    # pierwsze rozwiązanie ~79 s bez, patrz notebooks/parter_perf_probe.py).
    solver.parameters.use_energetic_reasoning_in_no_overlap_2d = True
    solver.parameters.use_timetabling_in_no_overlap_2d = True
    solver.parameters.use_area_energetic_reasoning_in_no_overlap_2d = True

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
        rx = solver.value(x[i]) / SCALE + bx0
        ry = solver.value(y[i]) / SCALE + by0
        rw = solver.value(w[i]) / SCALE
        rh = solver.value(h[i]) / SCALE

        # Snap do siatki cm (round 2) — model jest integer-cm, więc wszystkie współrzędne
        # są wielokrotnościami 0.01 m; bez snapu float-dodawanie rx+rw daje krawędzie
        # epsilon-różne od sąsiadów (np. 2.38+0.9=3.2800000000000002 vs 3.28), przez co
        # Shapely nie widzi wspólnej krawędzi (adjacency mierzona jako 0). Bezstratne tu.
        poly = box(round(rx, 2), round(ry, 2), round(rx + rw, 2), round(ry + rh, 2))
        # L-capable: dołącz 2. prostokąt gdy has_L (unia 2 stykających się prostokątów → L)
        if has_L[i] is not None and solver.value(has_L[i]):
            r2w = solver.value(w2[i]) / SCALE
            r2h = solver.value(h2[i]) / SCALE
            if r2w > 1e-6 and r2h > 1e-6:
                r2x = solver.value(x2[i]) / SCALE + bx0
                r2y = solver.value(y2[i]) / SCALE + by0
                poly = poly.union(box(round(r2x, 2), round(r2y, 2),
                                      round(r2x + r2w, 2), round(r2y + r2h, 2)))
        room = Room(spec=spec, polygon=poly)
        room.update_metrics()
        rooms.append(room)

    # --- Wyciągnij arrangement (topologię) do blokowania ---
    # Kwadrant = czysta funkcja rozwiązania (te same porównania co reifikacje
    # w bloku blocked_arrangements) — liczona z wartości, nie ze zmiennych modelu.
    arrangement = RoomArrangement()
    for i, spec in enumerate(specs):
        cx2_v = 2 * solver.value(x[i]) + solver.value(w[i])
        cy2_v = 2 * solver.value(y[i]) + solver.value(h[i])
        if cx2_v < 2 * half_w:
            arrangement.room_quadrants[spec.id] = 0 if cy2_v < 2 * half_h else 2
        else:
            arrangement.room_quadrants[spec.id] = 1 if cy2_v < 2 * half_h else 3

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


def _touches_bool(model, ax, ay, axe, aye, bx, by, bxe, bye,
                  min_shared: int, BW: int, BH: int, name: str):
    """Zreifikowane sąsiedztwo: zwraca BoolVar `touches` taki, że touches → prostokąty
    A i B współdzielą krawędź ≥ min_shared (jeden z 4 przypadków). Gdy touches=False —
    żadnego ograniczenia (prostokąty mogą, ale nie muszą się stykać). Pozwala składać
    'A dotyka B przez rect1 LUB rect2' dla pokoi L-kształtnych (Approach 2b)."""
    touches = model.new_bool_var(f"touch_{name}")
    cl = model.new_bool_var(f"touch_{name}_l")
    cr = model.new_bool_var(f"touch_{name}_r")
    cb = model.new_bool_var(f"touch_{name}_b")
    ct = model.new_bool_var(f"touch_{name}_t")
    for c in (cl, cr, cb, ct):
        model.add_implication(c, touches)          # przypadek aktywny tylko gdy touches
    model.add_bool_or([cl, cr, cb, ct]).only_enforce_if(touches)
    model.add(axe == bx).only_enforce_if(cl)        # A na lewo od B
    _add_overlap_constraint(model, ay, aye, by, bye, min_shared, BH, cl, f"touch_{name}_l")
    model.add(bxe == ax).only_enforce_if(cr)        # A na prawo od B
    _add_overlap_constraint(model, ay, aye, by, bye, min_shared, BH, cr, f"touch_{name}_r")
    model.add(aye == by).only_enforce_if(cb)        # A poniżej B
    _add_overlap_constraint(model, ax, axe, bx, bxe, min_shared, BW, cb, f"touch_{name}_b")
    model.add(bye == ay).only_enforce_if(ct)        # A powyżej B
    _add_overlap_constraint(model, ax, axe, bx, bxe, min_shared, BW, ct, f"touch_{name}_t")
    return touches


def _apply_adjacency(model, a, b, x, y, x_ends, y_ends,
                     x2, y2, x2e, y2e, has_L, BW, BH, min_shared):
    """Sąsiedztwo a↔b z obsługą pokoi L (2 prostokąty): a dotyka b PRZEZ KTÓRYKOLWIEK
    prostokąt którejkolwiek strony (rect1/rect2). Dla rect2 nieobecnego (¬has_L) opcja=0."""
    la, lb = has_L[a] is not None, has_L[b] is not None
    opts = [_touches_bool(model, x[a], y[a], x_ends[a], y_ends[a],
                          x[b], y[b], x_ends[b], y_ends[b], min_shared, BW, BH, f"adj{a}_{b}_11")]
    if lb:
        t = _touches_bool(model, x[a], y[a], x_ends[a], y_ends[a],
                          x2[b], y2[b], x2e[b], y2e[b], min_shared, BW, BH, f"adj{a}_{b}_12")
        model.add(t == 0).only_enforce_if(has_L[b].Not()); opts.append(t)
    if la:
        t = _touches_bool(model, x2[a], y2[a], x2e[a], y2e[a],
                          x[b], y[b], x_ends[b], y_ends[b], min_shared, BW, BH, f"adj{a}_{b}_21")
        model.add(t == 0).only_enforce_if(has_L[a].Not()); opts.append(t)
    if la and lb:
        t = _touches_bool(model, x2[a], y2[a], x2e[a], y2e[a],
                          x2[b], y2[b], x2e[b], y2e[b], min_shared, BW, BH, f"adj{a}_{b}_22")
        model.add(t == 0).only_enforce_if(has_L[a].Not())
        model.add(t == 0).only_enforce_if(has_L[b].Not()); opts.append(t)
    model.add_bool_or(opts)


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
