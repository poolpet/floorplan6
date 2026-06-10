"""Two-storey single-family house layout (Phase 1).

Reserves a staircase core and runs the proven Stage 4 CP-SAT solver once per
storey (parter template, then pietro template) with the SAME reserved core, so
the staircase is vertically aligned by construction. See
docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from shapely.geometry import Point, Polygon, box

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.house_program import default_house_config
from core.models import Room
from core.template_selector import load_all_templates

STAIR_W = 2.5
STAIR_H = 3.0
MIN_STOREY_AREA = 60.0

# --- Parterowiec (single-storey) ---
MIN_SINGLE_STOREY_AREA = 45.0   # prowizoryczny; dostrajany przez feasibility-matrix (test_house_single_storey)
PRZEDSIONEK_MIN_AREA = 50.0     # D2: poniżej tego progu drzwi wprost do holu (bez wiatrołapu)

# Dobór pokoi parterowca wg powierzchni obrysu. Rdzeń zawsze; reszta greedy wg sumy
# minów z marginesem na upakowanie ((suma_min+m)·margin ≤ area). Wiatrołap wg progu D2.
_SINGLE_CORE = ["hub", "salon", "kuchnia", "lazienka", "sypialnia_1"]
# Priorytet: sypialnie WYSOKO (research archon.pl: bestseller = 4 syp + 2 łazienki na
# 85-130 m²; 63-85 m² → 3 syp). 2. łazienka + wc + kotłownia, luksusy (spiżarnia/garderoba)
# na końcu (i tak zwykle ucięte capem liczby pokoi).
_SINGLE_OPTIONAL = ["sypialnia_2", "sypialnia_3", "sypialnia_4", "lazienka_2",
                    "wc", "kotlownia", "spizarnia", "garderoba"]
# Cap liczby pokoi parterowca — CP-SAT robi się wolny/zawiesza powyżej ~12 pokoi
# (14 pokoi na 106 m² = timeout). 12 mieści realny program (4 syp + 2 łaz + usługowe).
_SINGLE_MAX_ROOMS = 12
_PACK_MARGIN = 1.12   # prowizoryczny; podnieś jeśli wybrany zestaw okaże się INFEASIBLE w macierzy


def single_storey_room_ids(specs: list, area_m2: float) -> list[str]:
    """Zwraca id pokoi parterowca dla danej powierzchni (kolejność = priorytet dodawania)."""
    by_id = {s.id: s for s in specs}
    chosen = [r for r in _SINGLE_CORE if r in by_id]
    cum = sum(by_id[r].min_powierzchnia for r in chosen)
    if area_m2 >= PRZEDSIONEK_MIN_AREA and "wiatrolap" in by_id:          # D2 — próg przedsionka
        chosen.append("wiatrolap")
        cum += by_id["wiatrolap"].min_powierzchnia
    for rid in _SINGLE_OPTIONAL:                                         # greedy wg sumy minów
        if rid not in by_id or len(chosen) >= _SINGLE_MAX_ROOMS:         # cap liczby pokoi
            continue
        m = by_id[rid].min_powierzchnia
        if (cum + m) * _PACK_MARGIN <= area_m2:
            chosen.append(rid)
            cum += m
    return chosen


def _filter_template(tpl, keep_ids: set):
    """Kopia szablonu z podzbiorem pokoi + sąsiedztwem dotyczącym tylko zachowanych pokoi."""
    pokoje = [p for p in tpl.pokoje if p.id in keep_ids]
    sasiedztwo = [r for r in tpl.sasiedztwo
                  if (r.room_a in keep_ids or r.room_a == "_outside")
                  and (r.room_b in keep_ids or r.room_b == "_outside")]
    return replace(tpl, pokoje=pokoje, sasiedztwo=sasiedztwo)

# Adaptive staircase core (Approach A — spec 2026-06-01)
STAIR_RUN_W = 1.1            # szerokość biegu prostego (m)
STAIR_RUN_LEN = 4.2         # docelowa długość biegu prostego (m)
STAIR_U_SIDE = 2.4          # bok klatki U/zabiegowej (m)
STAIR_MAX_AREA = 6.0        # sufit pola schodów (m²)
STAIR_ASPECT_THRESHOLD = 1.4  # powyżej → bieg prosty, poniżej → U
STAIR_SETBACK = 0.8         # (legacy Approach A) cofnięcie rdzenia od ściany wejścia
STAIR_FRONT_SETBACK = 1.8   # (Approach B) głębokość HOLU przed schodami (m): pas między ścianą
                            # wejścia a schodami. 1.8 daje feasible na 7×9..10×7 (1.5/1.6 zawieszał
                            # 10×7 straight-core); schody przy ścianie bocznej przeciwnej wejściu.

# Knee-wall (S26): poddasze UŻYTKOWE = pas przy kalenicy, nie pełny obrys.
# Pełna długość wzdłuż dłuższej osi obrysu (kalenica) × ATTIC_BAND_FACTOR
# krótszej osi (zakres decyzji Dawida: 0.55-0.65), wycentrowany; MUSI zawierać
# rdzeń schodów (piony zachowane).
ATTIC_BAND_FACTOR = 0.60
# Szczelina pas↔rdzeń wzdłuż osi pasa musi być 0 ALBO ≥ ten próg: węższej nic nie
# pokryje (F1 == + min_szerokosc pokoi ≥1.0; prostokąt nad szczeliną blokują pinned
# schody) → solver INFEASIBLE. Mniejsze szczeliny dosnapowujemy do krawędzi rdzenia.
ATTIC_CORE_SNAP = 1.5


def _stair_core_dims(W: float, H: float, force_straight: bool = False) -> tuple[float, float, str]:
    """(sw, sh, kind) — geometria rdzenia schodów wg proporcji obrysu.

    Wydłużony obrys (aspect > próg) → bieg prosty: wąski, długi wzdłuż dłuższej osi.
    Kwadratowy → U/zabiegowe: zwarty kwadrat. Pole ≤ STAIR_MAX_AREA oraz ≤ 0.40·W × 0.40·H.

    force_straight (knee-wall, S26): dom 2-kond. z poddaszem ZAWSZE dostaje bieg
    prosty wzdłuż kalenicy — pas poddasza ma proporcje ≥1/ATTIC_BAND_FACTOR>próg,
    a U-rdzeń (2.4 m głębokości = połowa pasa) zostawia martwą kieszeń nad schodami
    i dowodliwie (presolve INFEASIBLE) wysadza układ piętra.
    """
    cap_w = 0.40 * W
    cap_h = 0.40 * H
    long_dim = max(W, H)
    short_dim = min(W, H)
    aspect = long_dim / short_dim if short_dim > 0 else 1.0
    if force_straight or aspect > STAIR_ASPECT_THRESHOLD:
        run_len = min(STAIR_RUN_LEN, 0.6 * long_dim)
        if W >= H:                       # dłuższa oś = X → bieg poziomy
            sw, sh = run_len, STAIR_RUN_W
        else:                            # dłuższa oś = Y → bieg pionowy
            sw, sh = STAIR_RUN_W, run_len
        kind = "straight"
    else:
        side = min(STAIR_U_SIDE, cap_w, cap_h)
        sw = sh = side
        kind = "u"
    sw = min(sw, cap_w)
    sh = min(sh, cap_h)
    if sw * sh > STAIR_MAX_AREA:
        scale = (STAIR_MAX_AREA / (sw * sh)) ** 0.5
        sw *= scale
        sh *= scale
    return round(sw, 3), round(sh, 3), kind


@dataclass
class TwoStoreyLayout:
    ok: bool = True
    message: str = ""
    parter_rooms: list[Room] = field(default_factory=list)
    pietro_rooms: list[Room] = field(default_factory=list)
    stair_core: tuple[float, float, float, float] = (0.0, 0.0, STAIR_W, STAIR_H)
    boundary: object = None
    # Knee-wall (S26): boundary PODDASZA (pas przy kalenicy) — mniejszy niż parter.
    # None = kondygnacje o tym samym footprincie (parterowiec / stare ścieżki).
    attic_boundary: object = None


def _template(tid: str):
    return next((t for t in load_all_templates() if t.id == tid), None)


def _entry_side(bbox, entry_point) -> str:
    minx, miny, maxx, maxy = bbox
    ex, ey = entry_point
    d = {"south": abs(ey - miny), "north": abs(maxy - ey),
         "west": abs(ex - minx), "east": abs(maxx - ex)}
    return min(d, key=d.get)


def _reserve_core(bbox, entry_point, force_straight: bool = False) -> tuple[float, float, float, float]:
    """Rdzeń klatki schodowej (x, y, w, h), bbox-relative — Approach B.

    Geometria adaptacyjna (`_stair_core_dims`; force_straight → bieg prosty wzdłuż
    kalenicy, knee-wall S26). Pozycja wg ARCHON: na ŚREDNIEJ GŁĘBOKOŚCI (cofnięta
    od fasady wejścia) i OBOK osi wejścia (przy ścianie bocznej po przeciwnej
    stronie niż drzwi). Dzięki temu HOL może zająć strefę wejścia (zawiera drzwi,
    dotyka ściany wejścia) i dotknąć schodów od ich strony holowej — schody NIE
    leżą na osi wejścia, więc nie blokują huba.
    """
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw, sh, _kind = _stair_core_dims(W, H, force_straight=force_straight)
    ex = entry_point[0] - minx
    ey = entry_point[1] - miny
    side = _entry_side(bbox, entry_point)
    if side in ("south", "north"):
        # offset w X: schody przy ścianie bocznej po przeciwnej stronie niż wejście;
        # cofnięcie w Y o STAIR_FRONT_SETBACK od ściany wejścia (hol zajmuje pas frontu)
        cx = (W - sw) if ex < W / 2 else 0.0
        if side == "south":
            cy = min(STAIR_FRONT_SETBACK, max(0.0, H - sh))
        else:  # north
            cy = max(H - sh - STAIR_FRONT_SETBACK, 0.0)
    else:  # west / east — pionowa ściana wejścia
        cy = (H - sh) if ey < H / 2 else 0.0
        if side == "west":
            cx = min(STAIR_FRONT_SETBACK, max(0.0, W - sw))
        else:  # east
            cx = max(W - sw - STAIR_FRONT_SETBACK, 0.0)
    return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))


def _attic_band_polygon(polygon: Polygon, core: tuple[float, float, float, float]) -> Polygon:
    """Pas poddasza użytkowego (KNEE-WALL, S26). core = rdzeń schodów bbox-relative.

    Pas o pełnej długości wzdłuż kalenicy (dłuższa oś bboxa) i głębokości
    ATTIC_BAND_FACTOR krótszej osi, wycentrowany na krótszej osi; przesunięty
    minimalnie tak, by zawierał rdzeń schodów (rdzeń ≤0.4 krótszej osi < pas,
    więc zawsze się mieści); przycięty do obrysu (L/U-footprinty).
    """
    minx, miny, maxx, maxy = polygon.bounds
    W, H = maxx - minx, maxy - miny
    cx, cy, cw, ch = core

    def _place(axis_lo, axis_hi, depth, core_lo, core_hi):
        """Pozycja pasa na krótszej osi: wycentrowany → zawiera rdzeń → bez szczelin
        pas↔rdzeń węższych niż ATTIC_CORE_SNAP (niepokrywalne przy F1)."""
        lo = axis_lo + (axis_hi - axis_lo - depth) / 2.0
        lo = min(max(lo, core_hi - depth), core_lo)       # zawieraj rdzeń schodów
        lo = min(max(lo, axis_lo), axis_hi - depth)       # zostań w obrysie
        gap_lo = core_lo - lo
        gap_hi = (lo + depth) - core_hi
        if 0 < gap_lo < ATTIC_CORE_SNAP and core_lo + depth <= axis_hi + 1e-9:
            return core_lo                                # krawędź pasa na krawędzi rdzenia
        if 0 < gap_hi < ATTIC_CORE_SNAP and core_hi - depth >= axis_lo - 1e-9:
            return core_hi - depth
        return lo

    if W >= H:                       # kalenica wzdłuż X → pas ogranicza Y
        depth = ATTIC_BAND_FACTOR * H
        lo = _place(miny, maxy, depth, miny + cy, miny + cy + ch)
        band = box(minx, lo, maxx, lo + depth)
    else:                            # kalenica wzdłuż Y → pas ogranicza X
        depth = ATTIC_BAND_FACTOR * W
        lo = _place(minx, maxx, depth, minx + cx, minx + cx + cw)
        band = box(lo, miny, lo + depth, maxy)
    attic = band.intersection(polygon)
    if attic.geom_type == "MultiPolygon":
        # Egzotyczny obrys rozciął pas: bierz płat ZAWIERAJĄCY rdzeń schodów (bez niego
        # piętro nie ma klatki = zawsze INFEASIBLE); fallback — największy płat.
        core_box = box(minx + cx, miny + cy, minx + cx + cw, miny + cy + ch)
        with_core = [g for g in attic.geoms if g.contains(core_box.buffer(-1e-9))]
        attic = with_core[0] if with_core else max(attic.geoms, key=lambda g: g.area)
    return attic


def suggest_storeys(area_m2: float) -> int:
    """Podpowiedź liczby kondygnacji wg powierzchni obrysu (architekt nadpisuje)."""
    return 1 if area_m2 < 60.0 else 2


def _generate_single_storey(polygon: Polygon, entry_point: tuple[float, float],
                            time_limit_s: float) -> TwoStoreyLayout:
    """Parterowiec: jedna kondygnacja, BEZ schodów/rdzenia/piętra. Zestaw pokoi wg
    powierzchni; wiatrołap wg progu D2 (gdy jest — drzwi w nim, hol za nim)."""
    if polygon.area < MIN_SINGLE_STOREY_AREA:
        return TwoStoreyLayout(ok=False,
            message=f"Obrys {polygon.area:.0f} m2 za maly na parterowiec (min ~{MIN_SINGLE_STOREY_AREA:.0f} m2).")
    boundary = analyze_boundary(polygon, entry_point=entry_point)
    tpl = _template("house_single_storey")
    if tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_single_storey.")
    keep = set(single_storey_room_ids(tpl.pokoje, polygon.area))
    tpl_f = _filter_template(tpl, keep)
    cfg = default_house_config(storey="single", master_id="sypialnia_1")
    has_wiatrolap = "wiatrolap" in keep
    r = solve_cpsat(tpl_f, boundary, time_limit_s=time_limit_s,
                    program_config=cfg, hub_at_entry=True,
                    entry_room_id="wiatrolap" if has_wiatrolap else None,
                    l_capable_ids={"hub"})
    if r.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu parterowca (status={r.status}).", boundary=boundary)
    return TwoStoreyLayout(ok=True, parter_rooms=r.rooms, pietro_rooms=[], boundary=boundary)


def generate_house(polygon: Polygon, entry_point: tuple[float, float],
                   num_storeys: int = 2, time_limit_s: float = 30.0) -> TwoStoreyLayout:
    if num_storeys == 1:
        return _generate_single_storey(polygon, entry_point, time_limit_s)
    if polygon.area < MIN_STOREY_AREA:
        return TwoStoreyLayout(ok=False,
            message=f"Obrys {polygon.area:.0f} m2 za maly na program domu (min ~{MIN_STOREY_AREA:.0f} m2/kondygnacje).")
    boundary = analyze_boundary(polygon, entry_point=entry_point)
    # Knee-wall (S26): bieg prosty wzdłuż kalenicy — patrz _stair_core_dims(force_straight).
    core = _reserve_core(boundary.bbox, entry_point, force_straight=True)
    parter_tpl = _template("house_parter")
    pietro_tpl = _template("house_pietro")
    if parter_tpl is None or pietro_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonow domu (house_parter/house_pietro).")
    # Konfigurowalny program domu (cap-y ARCHON) — parter vs poddasze; master = sypialnia_1.
    parter_cfg = default_house_config(storey="parter")
    pietro_cfg = default_house_config(storey="poddasze", master_id="sypialnia_1")
    # Faza 2b: hol parteru L-capable — owija wiatrołap (przy wejściu) + WC (przy ścianie)
    # ramieniem o minimalnym polu, więc korytarz zostaje mały mimo poprawnego ich położenia.
    # Knee-wall (S26): poddasze użytkowe = pas przy kalenicy, NIE pełny obrys
    # (skos dachu zabiera pasy przy okapach). Piętro solvujemy na pasie.
    attic_poly = _attic_band_polygon(polygon, core)
    # Suma minów piętra z PRZYPIĘTYM polem schodów (pin > min szablonowy schodów).
    attic_min = (sum(p.min_powierzchnia for p in pietro_tpl.pokoje if p.id != "schody")
                 + core[2] * core[3]) * _PACK_MARGIN
    if attic_poly.area < attic_min:
        return TwoStoreyLayout(ok=False,
            message=(f"Poddasze uzytkowe (pas {attic_poly.area:.0f} m2 przy kalenicy) za male "
                     f"na program pietra (min ~{attic_min:.0f} m2) — powieksz obrys "
                     f"albo wybierz parterowiec."),
            stair_core=core, boundary=boundary)
    # entry_point zrzutowany na obrys pasa — piętro i tak go nie używa (hub_at_entry=False),
    # ale analyze_boundary wymaga sensownego punktu na obrysie. Jawne wall_types=FACADE:
    # poddasze NIE ma drzwi zewnętrznych, więc domyślna heurystyka „krawędź z entry =
    # INTERNAL" gasiłaby okna na całej ściance kolankowej/szczycie pod pseudo-entry.
    from core.models import WallType
    ep = attic_poly.exterior.interpolate(attic_poly.exterior.project(Point(entry_point)))
    n_edges = len(attic_poly.exterior.coords) - 1
    attic_boundary = analyze_boundary(attic_poly, entry_point=(ep.x, ep.y),
                                      wall_types=[WallType.FACADE] * n_edges)
    # rdzeń w układzie bbox PASA — ta sama pozycja świata co na parterze (piony schodów).
    bx0, by0 = boundary.bbox[0], boundary.bbox[1]
    ax0, ay0 = attic_boundary.bbox[0], attic_boundary.bbox[1]
    attic_core = (round(core[0] + bx0 - ax0, 3), round(core[1] + by0 - ay0, 3),
                  core[2], core[3])
    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=parter_cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap")
    # Piętro NIE ma drzwi zewnętrznych — podest łączy się ze schodami, nie z fasadą wejścia.
    # Podest L-capable: w wąskim pasie poddasza prostokątny podest nie domknie gwiazdy
    # F5 (hub ≤0.8 głębokości pasa + pinned schody ⇒ presolve INFEASIBLE); cienki L
    # opasuje klatkę — ta sama mechanika co „mini-korytarz" wąskich mieszkań (S26).
    r_pietro = solve_cpsat(pietro_tpl, attic_boundary, time_limit_s=time_limit_s,
                           reserved_core=attic_core, program_config=pietro_cfg,
                           stair_room_id="schody", hub_at_entry=False,
                           l_capable_ids={"hub"})
    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core, boundary=boundary, attic_boundary=attic_boundary)
    return TwoStoreyLayout(ok=True, parter_rooms=r_parter.rooms, pietro_rooms=r_pietro.rooms,
                           stair_core=core, boundary=boundary, attic_boundary=attic_boundary)
