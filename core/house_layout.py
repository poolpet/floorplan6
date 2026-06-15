"""Two-storey single-family house layout (Phase 1).

Reserves a staircase core and runs the proven Stage 4 CP-SAT solver once per
storey (parter template, then pietro template) with the SAME reserved core, so
the staircase is vertically aligned by construction. See
docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from shapely.geometry import Polygon, box

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

# Knee-wall v2 (S29, decyzja Dawida po przeglądzie rzutów S27/28): poddasze ma
# PEŁNY footprint parteru (powierzchnia jak parter), ale wzdłuż DŁUŻSZYCH krawędzi
# (okapy; kalenica = dłuższa oś) biegną strefy NISKIEJ ścianki kolankowej:
#   - układ: żaden pokój piętra nie może być W CAŁOŚCI w strefie (solver, low_zones);
#     WYJĄTEK: schody — wchodzi się stopniowo, dolne stopnie nie potrzebują wysokości;
#   - meble: wysokie (szafa/regały/kocioł) poza strefą; niskie (łóżko, WC, wanna) mogą.
# Głębokość strefy = ATTIC_LOW_STRIP_FACTOR · krótsza oś (2×0.20 = komplement pasa
# 0.60 z S27; realna użyteczna szerokość wg korpusu wzorców 0.43-0.78 — kalibracja
# benchmarkiem).
ATTIC_LOW_STRIP_FACTOR = 0.20


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
    stair_kind: str = "straight"   # 'u' (zabiegowe) / 'straight' — wg proporcji obrysu
    boundary: object = None
    # (S27, wycofane w S29) boundary pasa poddasza — zostaje dla back-compat, zawsze None.
    attic_boundary: object = None
    # Knee-wall v2 (S29): strefy niskiej ścianki kolankowej poddasza (world coords).
    attic_low_strips: list = field(default_factory=list)


def _template(tid: str):
    return next((t for t in load_all_templates() if t.id == tid), None)


def _entry_side(bbox, entry_point) -> str:
    minx, miny, maxx, maxy = bbox
    ex, ey = entry_point
    d = {"south": abs(ey - miny), "north": abs(maxy - ey),
         "west": abs(ex - minx), "east": abs(maxx - ex)}
    return min(d, key=d.get)


def _reserve_core(bbox, entry_point, force_straight: bool = False,
                  notch=None) -> tuple[float, float, float, float]:
    """Rdzeń klatki schodowej (x, y, w, h), bbox-relative — Approach B.

    Geometria adaptacyjna (`_stair_core_dims`; force_straight → bieg prosty wzdłuż
    kalenicy, knee-wall S26). Pozycja wg ARCHON: na ŚREDNIEJ GŁĘBOKOŚCI (cofnięta
    od fasady wejścia) i OBOK osi wejścia (przy ścianie bocznej po przeciwnej
    stronie niż drzwi). Dzięki temu HOL może zająć strefę wejścia (zawiera drzwi,
    dotyka ściany wejścia) i dotknąć schodów od ich strony holowej — schody NIE
    leżą na osi wejścia, więc nie blokują huba.

    notch (S30): gdy obrys jest L-kształtny, rdzeń kotwiczony w litej GŁÓWNEJ
    BRYLE — w rogu bbox DIAGONALNIE PRZECIWNYM do wcięcia (zawsze lity dla
    pojedynczego notcha L). WKLĘSŁY narożnik (zgięcie skrzydeł) byłby gardłem
    cyrkulacji: przypięta tam klatka + notch zatykają jedyne przejście między
    skrzydłami → INFEASIBLE (dowód: notebooks/lcore_placement_probe.py — narożnik
    flush/pionowy/+offset = INFEASIBLE, róg przeciwny = OPTIMAL). Centralność daje
    hol L-capable owijający zgięcie; schody siedzą w bryle skrzydła (jak realne L).
    notch=None → logika prostokąta bajt-w-bajt jak dawniej (zero regresji M-domów).
    """
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw, sh, _kind = _stair_core_dims(W, H, force_straight=force_straight)

    if notch is not None:
        # Notch zajmuje jeden róg bbox (L). Rdzeń → róg diagonalnie przeciwny:
        # zawsze lity, z dala od gardła zgięcia. on_left/on_bottom = którą
        # krawędź bbox dotyka notch (przylega do jednej poziomej i jednej pionowej).
        eps = 1e-6
        on_left = notch.x < eps                 # wcięcie przy lewej krawędzi
        on_bottom = notch.y < eps               # wcięcie przy dolnej krawędzi
        cx = (W - sw) if on_left else 0.0        # notch lewy → rdzeń prawy (i odwrotnie)
        cy = (H - sh) if on_bottom else 0.0      # notch dolny → rdzeń górny (i odwrotnie)
        return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))

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


# --- Room-set scaling 2-kond. (S29, dane z korpusu wzorców reference_plans.json) ---
# Poddasze: A01_70 (54 m² netto) = 4 SYPIALNIE + 1 łazienka; A01_120 (86) = 3 syp
# + 2 ŁAZIENKI. Parter: A01_120 (97) ma GABINET. Nadmiar absorbują DODATKOWE pokoje,
# nie pompowanie mastera/salonu.
_PIETRO_CORE = ["hub", "schody", "sypialnia_1", "sypialnia_2", "lazienka"]
_PIETRO_OPTIONAL = ["sypialnia_3", "sypialnia_4", "lazienka_2", "garderoba"]
_PIETRO_LAZ2_MIN_EFF = 70.0     # 2. łazienka od ~70 m² efektywnych (korpus: 54→1, 86→2)
_PIETRO_GARDEROBA_MIN_EFF = 95.0  # garderoba = rzadki luksus: ŻADEN wzorcowy poddasze
                                  # (A01_70 i A01_120) jej nie ma; 9. pokój spowalniał piętro
# --- NETTO/BRUTTO (S30, decyzja Dawida 2026-06-12) ---
# Obrys wejściowy to BRUTTO; liczby korpusowe (capy ARCHON, progi, tabele rzutów)
# to NETTO. Kotwica przelicznika: A01_120 = 97 m² netto przy ~120 brutto → 0.81.
# Rekalibracja po pełnej ekstrakcji 36 PDF (wf_f8cab93b). Pokoje MOKRE (F2/WT)
# NIGDY nie są skalowane — to twarde capy prawne.
NET_FACTOR = 0.81

_PARTER_GABINET_MIN_NET = 93.0  # gabinet od ~93 m² NETTO (= dawne 115 gross; niżej
                                # 9-pokojowy parter spowalniał solver na macierzy 96-108)
_PARTER_GARAZ_MIN_NET = 97.0    # garaż od 97 m² NETTO (= korpusowe A01_120: parter
                                # 97 netto Z garażem; ≈ dawne 120 gross)
_PARTER_SPIZARNIA_MIN_NET = 60.0  # korpus: spiżarnia tylko ≥~60 netto (osobie 65/a2-6 83 mają;
                                  # tropie 48/pb 51/pab2 44 nie) — bufor perf małego parteru


def net_area(gross_m2: float) -> float:
    """Powierzchnia NETTO z brutto obrysu (ściany ~19%; kotwica A01_120 97/120)."""
    return NET_FACTOR * gross_m2


def attic_effective_area(polygon: Polygon) -> float:
    """Powierzchnia EFEKTYWNA poddasza do doboru programu: pełna − 0.5·strefy niskie
    (norma PL: wysokość 1.4-2.2 m liczona w 50%). Dla A01_70 daje ~55 vs 53.8 netto
    z tabeli rzutu — dobra korespondencja."""
    return polygon.area - 0.5 * sum(s.area for s in attic_low_strips(polygon))


def pietro_room_ids(specs: list, eff_area_m2: float, bedroom_offset: int = 0) -> list[str]:
    """Zestaw pokoi poddasza wg powierzchni efektywnej (greedy po sumie minów).
    bedroom_offset (S30c): tyle sypialni schodzi na parter — poddasze dostaje o tyle
    mniej (od najwyższego numeru), min 1 sypialnia zostaje (strefa nocna na górze)."""
    by_id = {s.id: s for s in specs}
    chosen = [r for r in _PIETRO_CORE if r in by_id]
    cum = sum(by_id[r].min_powierzchnia for r in chosen)
    for rid in _PIETRO_OPTIONAL:
        if rid not in by_id:
            continue
        if rid == "lazienka_2" and eff_area_m2 < _PIETRO_LAZ2_MIN_EFF:
            continue
        if rid == "garderoba" and eff_area_m2 < _PIETRO_GARDEROBA_MIN_EFF:
            continue
        m = by_id[rid].min_powierzchnia
        if (cum + m) * _PACK_MARGIN <= eff_area_m2:
            chosen.append(rid)
            cum += m
    if bedroom_offset > 0:
        beds = [r for r in chosen if r.startswith("sypialnia")]
        n_drop = min(bedroom_offset, max(0, len(beds) - 1))   # zostaw ≥1
        drop = set(beds[len(beds) - n_drop:]) if n_drop else set()
        chosen = [r for r in chosen if r not in drop]
    return chosen


def parter_room_ids(specs: list, net_m2: float, with_parter_bedroom: bool = True) -> list[str]:
    """Zestaw pokoi parteru wg powierzchni NETTO (S30 — progi korpusowe netto-we).
    sypialnia_parter (S30c: pokój na parterze) zawsze gdy with_parter_bedroom;
    gabinet/garaż bramkowane powierzchnią. Caller przelicza brutto przez net_area()."""
    by_id = {s.id for s in specs}
    gated = ("gabinet", "garaz", "spizarnia", "sypialnia_parter")
    ids = [s.id for s in specs if s.id not in gated]
    if with_parter_bedroom and "sypialnia_parter" in by_id:
        ids.append("sypialnia_parter")
    # Spiżarnia TYLKO w programie BEZ sypialni parteru (fallback). Z sypialnią parter
    # zostaje 8-pokojowy — perf (sonda parter8_bedroom_probe: 9 pokoi = loteria @60s,
    # 8 = niezawodne na obrysach ≥~100 m²). Sypialnia ma priorytet nad spiżarnią (S30c).
    if not with_parter_bedroom and net_m2 >= _PARTER_SPIZARNIA_MIN_NET and "spizarnia" in by_id:
        ids.append("spizarnia")
    if net_m2 >= _PARTER_GABINET_MIN_NET and "gabinet" in by_id:
        ids.append("gabinet")
    if net_m2 >= _PARTER_GARAZ_MIN_NET and "garaz" in by_id:
        ids.append("garaz")
    return ids


def _corpus_parter_adjacency(tpl):
    """Sąsiedztwa dużych parterów wg KORPUSU (S30, AR.02.1 — decyzja Dawida
    2026-06-12): hol NIE musi dotykać garażu ani kotłowni — garaż wchodzi przez
    wiatrołap (śluzę), kotłownia przez garaż (śluza techniczna). Hol zostaje
    przy: wiatrołap/schody/salon/WC/gabinet. Bez garażu w zestawie — identyczność
    (kotłownia przy holu to jej jedyne wejście). Mniejsza gwiazda holu = realniejsze
    plany (benchmark adjacency) i lżejsza wykonalność (sonda parter_adjacency_probe)."""
    ids = {p.id for p in tpl.pokoje}
    if "garaz" not in ids:
        return tpl
    rules = []
    for r in tpl.sasiedztwo:
        pair = {r.room_a, r.room_b}
        if pair == {"hub", "garaz"} and "wiatrolap" in ids:
            rules.append(replace(r, room_a="garaz", room_b="wiatrolap"))
        elif pair == {"hub", "kotlownia"}:
            rules.append(replace(r, room_a="kotlownia", room_b="garaz"))
        else:
            rules.append(r)
    return replace(tpl, sasiedztwo=rules)


def parter_template_for(gross_area_m2: float, with_parter_bedroom: bool = True):
    """Szablon parteru dla obrysu BRUTTO: zestaw pokoi wg netto (+sypialnia_parter
    gdy with_parter_bedroom) + sąsiedztwa korpusowe (gdy garaż). None gdy brak szablonu."""
    tpl = _template("house_parter")
    if tpl is None:
        return None
    keep = set(parter_room_ids(tpl.pokoje, net_area(gross_area_m2), with_parter_bedroom))
    tpl = _filter_template(tpl, keep)
    return _corpus_parter_adjacency(tpl)


def _gross_config(cfg):
    """Program domu egzekwowany na obrysie BRUTTO: capy netto-we (ARCHON) dzielone
    przez NET_FACTOR — z wyjątkiem pokoi MOKRYCH (wc w caps; łazienki w polach
    bathroom_*), których capy to twarde limity prawne F2/WT (B3: nie skalować)."""
    caps = {k: (v if k == "wc" else v / NET_FACTOR) for k, v in cfg.caps.items()}
    return replace(cfg, caps=caps, day_zone_cap_max=cfg.day_zone_cap_max / NET_FACTOR)


def attic_low_strips(polygon: Polygon) -> list[Polygon]:
    """Strefy niskiej ścianki kolankowej poddasza (world coords): dwa pasy wzdłuż
    DŁUŻSZYCH krawędzi bboxa (okapy), głębokość ATTIC_LOW_STRIP_FACTOR · krótsza oś."""
    minx, miny, maxx, maxy = polygon.bounds
    W, H = maxx - minx, maxy - miny
    if W >= H:                       # kalenica wzdłuż X → strefy przy y=min i y=max
        d = ATTIC_LOW_STRIP_FACTOR * H
        return [box(minx, miny, maxx, miny + d), box(minx, maxy - d, maxx, maxy)]
    d = ATTIC_LOW_STRIP_FACTOR * W   # kalenica wzdłuż Y → strefy przy x=min i x=max
    return [box(minx, miny, minx + d, maxy), box(maxx - d, miny, maxx, maxy)]


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
    # Winder default (S31b): force_straight ZDJĘTY. Po knee-wall v2 poddasze ma pełny
    # footprint i schody są zwolnione ze strefy niskiej ścianki, więc U-rdzeń jest
    # wykonalny (probe: parter FEASIBLE vs straight UNKNOWN na 88/130 m²). Obrysy aspect
    # > STAIR_ASPECT_THRESHOLD i tak dostają bieg prosty. S30: notch-aware (róg przeciwny wcięciu).
    core = _reserve_core(boundary.bbox, entry_point, notch=boundary.notch)
    _bw = boundary.bbox[2] - boundary.bbox[0]
    _bh = boundary.bbox[3] - boundary.bbox[1]
    _csw, _csh, stair_kind = _stair_core_dims(_bw, _bh)
    pietro_tpl0 = _template("house_pietro")
    if pietro_tpl0 is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_pietro.")
    # Budżet sypialni na poziomie DOMU (S30c): jedna sypialnia schodzi na parter,
    # poddasze dostaje o 1 mniej → łączna liczba bez zmian. Fallback: gdy stary
    # model dałby <2 sypialni na piętrze, zostaw je na górze (parter bez sypialni).
    eff = attic_effective_area(polygon)
    old_beds = sum(1 for r in pietro_room_ids(pietro_tpl0.pokoje, eff, bedroom_offset=0)
                   if r.startswith("sypialnia"))
    parter_bedroom = old_beds >= 2
    offset = 1 if parter_bedroom else 0
    parter_tpl = parter_template_for(polygon.area, with_parter_bedroom=parter_bedroom)
    pietro_tpl = _filter_template(
        pietro_tpl0, set(pietro_room_ids(pietro_tpl0.pokoje, eff, bedroom_offset=offset)))
    if parter_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_parter.")
    # Program domu (capy ARCHON są NETTO-we) egzekwowany na brutto: _gross_config.
    parter_cfg = _gross_config(default_house_config(storey="parter"))
    pietro_cfg = _gross_config(default_house_config(storey="poddasze", master_id="sypialnia_1"))
    # Faza 2b: hol parteru L-capable — owija wiatrołap (przy wejściu) + WC (przy ścianie)
    # ramieniem o minimalnym polu, więc korytarz zostaje mały mimo poprawnego ich położenia.
    # Knee-wall v2 (S29): poddasze na PEŁNYM obrysie (powierzchnia jak parter);
    # strefy niskiej ścianki kolankowej wzdłuż dłuższych krawędzi przekazujemy
    # solverowi (bbox-relative) — żaden pokój piętra nie może być w nich W CAŁOŚCI.
    # Schody ZWOLNIONE (Dawid: wchodzi się stopniowo, dolne stopnie nie potrzebują
    # wysokości) — solver i tak pomija pokój przypięty (stair_idx).
    strips = attic_low_strips(polygon)
    bx0, by0 = boundary.bbox[0], boundary.bbox[1]
    low_rel = [(s.bounds[0] - bx0, s.bounds[1] - by0,
                s.bounds[2] - bx0, s.bounds[3] - by0) for s in strips]
    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=parter_cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                           external_bathroom_id="lazienka")
    # Best-effort sypialni parteru (S30c, decyzja Dawida): na CIASNYM modalnym obrysie
    # (~88 m²) parter 8-pok z sypialnią to loteria perf (sonda parter8_bedroom_probe:
    # ~50% @60s; obrysy ≥~100 m² = 4/4 niezawodne). Gdy parter z sypialnią =
    # UNKNOWN/INFEASIBLE → FALLBACK na niezawodny program BEZ sypialni parteru
    # (poddasze odzyskuje wszystkie sypialnie, total zachowany). KAŻDY dom się generuje;
    # sypialnia parteru pojawia się gdy wykonalna.
    if parter_bedroom and r_parter.status not in ("OPTIMAL", "FEASIBLE"):
        parter_tpl = parter_template_for(polygon.area, with_parter_bedroom=False)
        pietro_tpl = _filter_template(
            pietro_tpl0, set(pietro_room_ids(pietro_tpl0.pokoje, eff, bedroom_offset=0)))
        r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                               reserved_core=core, program_config=parter_cfg,
                               stair_room_id="schody", hub_at_entry=True,
                               l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                               external_bathroom_id="lazienka")
    # Piętro NIE ma drzwi zewnętrznych — podest łączy się ze schodami, nie z fasadą
    # wejścia. Podest L-capable (mechanika „mini-korytarza" S26) — opasuje klatkę.
    r_pietro = solve_cpsat(pietro_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=pietro_cfg,
                           stair_room_id="schody", hub_at_entry=False,
                           l_capable_ids={"hub"}, low_zones=low_rel)
    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core, stair_kind=stair_kind, boundary=boundary, attic_low_strips=strips)
    for _rooms in (r_parter.rooms, r_pietro.rooms):
        for _r in _rooms:
            if _r.spec.id == "schody":
                _r.stair_kind = stair_kind
    return TwoStoreyLayout(ok=True, parter_rooms=r_parter.rooms, pietro_rooms=r_pietro.rooms,
                           stair_core=core, stair_kind=stair_kind, boundary=boundary,
                           attic_low_strips=strips)
