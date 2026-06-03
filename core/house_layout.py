"""Two-storey single-family house layout (Phase 1).

Reserves a staircase core and runs the proven Stage 4 CP-SAT solver once per
storey (parter template, then pietro template) with the SAME reserved core, so
the staircase is vertically aligned by construction. See
docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from shapely.geometry import Polygon

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
_SINGLE_OPTIONAL = ["wc", "sypialnia_2", "spizarnia", "kotlownia", "sypialnia_3", "garderoba"]
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
        if rid not in by_id:
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


def _stair_core_dims(W: float, H: float) -> tuple[float, float, str]:
    """(sw, sh, kind) — geometria rdzenia schodów wg proporcji obrysu.

    Wydłużony obrys (aspect > próg) → bieg prosty: wąski, długi wzdłuż dłuższej osi.
    Kwadratowy → U/zabiegowe: zwarty kwadrat. Pole ≤ STAIR_MAX_AREA oraz ≤ 0.40·W × 0.40·H.
    """
    cap_w = 0.40 * W
    cap_h = 0.40 * H
    long_dim = max(W, H)
    short_dim = min(W, H)
    aspect = long_dim / short_dim if short_dim > 0 else 1.0
    if aspect > STAIR_ASPECT_THRESHOLD:
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


def _template(tid: str):
    return next((t for t in load_all_templates() if t.id == tid), None)


def _entry_side(bbox, entry_point) -> str:
    minx, miny, maxx, maxy = bbox
    ex, ey = entry_point
    d = {"south": abs(ey - miny), "north": abs(maxy - ey),
         "west": abs(ex - minx), "east": abs(maxx - ex)}
    return min(d, key=d.get)


def _reserve_core(bbox, entry_point) -> tuple[float, float, float, float]:
    """Rdzeń klatki schodowej (x, y, w, h), bbox-relative — Approach B.

    Geometria adaptacyjna (`_stair_core_dims`). Pozycja wg ARCHON: na ŚREDNIEJ
    GŁĘBOKOŚCI (cofnięta od fasady wejścia) i OBOK osi wejścia (przy ścianie bocznej
    po przeciwnej stronie niż drzwi). Dzięki temu HOL może zająć strefę wejścia
    (zawiera drzwi, dotyka ściany wejścia) i dotknąć schodów od ich strony holowej —
    schody NIE leżą na osi wejścia, więc nie blokują huba.
    """
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw, sh, _kind = _stair_core_dims(W, H)
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
    core = _reserve_core(boundary.bbox, entry_point)
    parter_tpl = _template("house_parter")
    pietro_tpl = _template("house_pietro")
    if parter_tpl is None or pietro_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonow domu (house_parter/house_pietro).")
    # Konfigurowalny program domu (cap-y ARCHON) — parter vs poddasze; master = sypialnia_1.
    parter_cfg = default_house_config(storey="parter")
    pietro_cfg = default_house_config(storey="poddasze", master_id="sypialnia_1")
    # Faza 2b: hol parteru L-capable — owija wiatrołap (przy wejściu) + WC (przy ścianie)
    # ramieniem o minimalnym polu, więc korytarz zostaje mały mimo poprawnego ich położenia.
    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=parter_cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap")
    # Piętro NIE ma drzwi zewnętrznych — podest łączy się ze schodami, nie z fasadą wejścia.
    r_pietro = solve_cpsat(pietro_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=pietro_cfg,
                           stair_room_id="schody", hub_at_entry=False)
    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core, boundary=boundary)
    return TwoStoreyLayout(ok=True, parter_rooms=r_parter.rooms, pietro_rooms=r_pietro.rooms,
                           stair_core=core, boundary=boundary)
