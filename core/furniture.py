"""Stage 4 — rozstawianie kanonicznych mebli (spec §5).

Regułowy, greedy MVP: dla każdego pokoju bierzemy kanoniczny zestaw mebli
(`FURNITURE_SETS`) wg prefiksu id pokoju, stawiamy je pod ściany (inset ~0.1 m),
z dala od WNIOSKOWANYCH drzwi (środek krawędzi wspólnej z sąsiadem) i bez kolizji.
Drzwi nie są nigdzie zapisane — wynikają z krawędzi wspólnych pokoi (spec §5).

Czysta geometria (Shapely), bez CP-SAT — szybkie. Pokoje komunikacyjne
(`hub`, `wiatrolap`) nie dostają mebli.
"""
from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass

from shapely.geometry import Polygon, box

from core.models import Room, Strefa

# ---- stałe rozstawiania (metry) ----
INSET = 0.10        # odsunięcie mebla od ściany
DOOR_MIN_OVERLAP = 0.90   # min wspólna krawędź, by uznać ją za przejście (drzwi)
DOOR_HALF = 0.60    # połowa szerokości strefy drzwi (świa­tło + luz)
DOOR_DEPTH = 0.65   # głębokość strefy drzwi w głąb pokoju
LINEAR_CAP = 3.0    # max długość ciągu liniowego (blat, regały)
STEP = 0.10         # krok przesuwania mebla wzdłuż ściany

CIRCULATION_KEYS = {"hub", "wiatrolap"}

# Piece: type=klucz maszynowy, label=PL etykieta, a×b=wymiary (m),
# linear=True → ciąg pod ścianę o stałej głębokości a i długości do b (cap).
Piece = namedtuple("Piece", "type label a b linear")

FURNITURE_SETS: dict[str, list[Piece]] = {
    "sypialnia": [
        Piece("bed", "Łóżko", 1.6, 2.0, False),
        Piece("wardrobe", "Szafa", 0.6, 2.0, False),
        Piece("nightstand", "Szafka nocna", 0.4, 0.4, False),
    ],
    "salon": [
        Piece("sofa", "Sofa", 0.9, 2.4, False),
        Piece("coffee_table", "Stolik", 0.6, 1.1, False),
        Piece("tv_unit", "RTV", 0.4, 1.6, False),
    ],
    "kuchnia": [
        Piece("kitchen_counter", "Blat kuchenny", 0.6, LINEAR_CAP, True),
    ],
    "lazienka": [
        Piece("bathtub", "Wanna / prysznic", 0.8, 1.7, False),
        Piece("washbasin", "Umywalka", 0.6, 0.5, False),
        Piece("toilet", "WC", 0.4, 0.6, False),
    ],
    "wc": [
        Piece("toilet", "WC", 0.4, 0.6, False),
        Piece("basin", "Umywalka", 0.4, 0.4, False),
    ],
    "garderoba": [
        Piece("shelving", "Regały", 0.4, 2.5, True),
    ],
    "kotlownia": [
        Piece("boiler", "Kocioł", 0.6, 0.8, False),
    ],
    "spizarnia": [
        Piece("shelves", "Półki", 0.4, 2.0, True),
    ],
}

# Stół jadalny — należy do otwartej strefy dziennej (styk salon↔kuchnia),
# nie do pojedynczego pokoju; rozstawiany osobnym przebiegiem w furnish_rooms.
DINING_TABLE = Piece("dining_table", "Stół jadalny", 0.9, 1.4, False)


@dataclass
class Furniture:
    """Pojedynczy mebel umieszczony w pokoju."""
    piece_type: str
    polygon: Polygon
    room_id: str
    label: str


@dataclass
class FurnishResult:
    """Wynik umeblowania: meble + ostrzeżenia (np. pokój za mały na kluczowy mebel)."""
    furniture: list  # list[Furniture]
    warnings: list   # list[str]


def furnish_rooms(rooms: list[Room], boundary=None) -> FurnishResult:
    """Rozstaw meble (spec phase 4). boundary=None → bez świadomości okien (back-compat).

    Pokoje komunikacyjne i pokoje bez zdefiniowanego zestawu nie dostają mebli.
    """
    door_zones = _infer_door_zones(rooms)
    furniture: list[Furniture] = []
    warnings: list[str] = []
    for room in rooms:
        if room.polygon is None:
            continue
        key = room.spec.id.split("_")[0]
        if key in CIRCULATION_KEYS or key not in FURNITURE_SETS:
            continue
        windows = _room_window_walls(room, boundary)
        # L/U-pokój: wnęka (bbox − polygon) jako keep-clear → meble nie wpadają poza
        # rzeczywisty obrys pokoju (placery liczą region z bbox). review #11.
        bx0, by0, bx1, by1 = room.polygon.bounds
        if room.polygon.area < (bx1 - bx0) * (by1 - by0) - 1e-6:
            cavity = box(bx0, by0, bx1, by1).difference(room.polygon)
            if not cavity.is_empty:
                door_zones.setdefault(room.spec.id, []).append(cavity)
        rzones = door_zones.get(room.spec.id, [])
        if key == "sypialnia":
            f, w = _furnish_bedroom(room, windows, rzones)
        elif key == "kuchnia":
            f, w = _furnish_kitchen(room, windows, rzones)
        elif key == "salon":
            f, w = _furnish_living(room, windows, rzones)
        elif key in ("lazienka", "wc"):
            f, w = _furnish_bathroom(room, windows, rzones)
        else:
            f, w = _furnish_room(room, key, rzones), []
        furniture.extend(f)
        warnings.extend(w)
    # stół jadalny w otwartej strefie dziennej (styk salon↔kuchnia) — po pokojach
    furniture += _place_dining(rooms, furniture, door_zones)
    return FurnishResult(furniture=furniture, warnings=warnings)


def place_furniture(rooms: list[Room], boundary=None) -> list[Furniture]:
    """Back-compat: płaska lista mebli (bez ostrzeżeń). Patrz furnish_rooms."""
    return furnish_rooms(rooms, boundary).furniture


def _room_window_walls(room: Room, boundary) -> set:
    """Ściany pokoju (S/N/W/E) leżące na krawędzi-fasadzie obrysu (= potencjalne okna).

    boundary=None lub notch → set() (notch deferred — tylko prostokąty w v1). Tol 5 cm.
    """
    if boundary is None or getattr(boundary, "notch", None) is not None:
        return set()
    # lazy import: nie ciągnij ortools (cpsat_solver) do importu furniture.
    # Gdy ortools/helper niedostępny (np. lekki bundle bez solvera) → degraduj do
    # "brak okien" zamiast crashować (review #15).
    try:
        from core.cpsat_solver import _detect_facade_sides
    except ImportError:
        return set()
    fac = _detect_facade_sides(boundary)
    bx0, by0, bx2, by2 = boundary.bbox
    rx0, ry0, rx1, ry1 = room.polygon.bounds
    t = 0.05
    walls = set()
    if fac["south"] and abs(ry0 - by0) < t:
        walls.add("S")
    if fac["north"] and abs(ry1 - by2) < t:
        walls.add("N")
    if fac["west"] and abs(rx0 - bx0) < t:
        walls.add("W")
    if fac["east"] and abs(rx1 - bx2) < t:
        walls.add("E")
    return walls


def _furnish_room(room: Room, key: str, zones: list[Polygon]) -> list[Furniture]:
    minx, miny, maxx, maxy = room.polygon.bounds
    region = (minx + INSET, miny + INSET, maxx - INSET, maxy - INSET)
    placed: list[Polygon] = []
    out: list[Furniture] = []
    for piece in FURNITURE_SETS[key]:
        if piece.linear:
            rect = _place_linear(region, piece.a, piece.b, placed, zones)
        else:
            rect = _place_fixed(region, piece.a, piece.b, placed, zones)
        if rect is not None:
            placed.append(rect)
            out.append(Furniture(piece.type, rect, room.spec.id, piece.label))
    return out


# ---- semantyczne placery (spec phase 4 §2) ----
# Zwracają (list[Furniture], list[str]) — meble + ostrzeżenia (kluczowy mebel się nie zmieścił).

_WALL_OPP = {"S": "N", "N": "S", "W": "E", "E": "W"}


def _inset(poly):
    minx, miny, maxx, maxy = poly.bounds
    return (minx + INSET, miny + INSET, maxx - INSET, maxy - INSET)


def _wall_len(region, wall):
    rx0, ry0, rx1, ry1 = region
    return (rx1 - rx0) if wall in ("S", "N") else (ry1 - ry0)


# Pasy dostępu (Neufert, spec §3) — wartości startowe, strojone.
CLEARANCE = {"bed": 0.6, "kitchen_counter": 1.2, "toilet": 0.6, "washbasin": 0.6}


def _clearance_zone(rect, wall, depth):
    """Pas dostępu przed meblem (od strony pokoju, przeciwnej do ściany). Tylko keep-clear (nie mebel)."""
    x0, y0, x1, y1 = rect.bounds
    if wall == "S":
        return box(x0, y1, x1, y1 + depth)
    if wall == "N":
        return box(x0, y0 - depth, x1, y0)
    if wall == "W":
        return box(x1, y0, x1 + depth, y1)
    if wall == "E":
        return box(x0 - depth, y0, x0, y1)
    return None


def _flank_nightstands(bed_rect, bed_wall, region, placed, zones, room_id):
    """Szafki nocne po bokach łóżka (wzdłuż ściany wezgłowia). Best-effort: pomija bok poza regionem/zajęty."""
    ns = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "nightstand")
    bx0, by0, bx1, by1 = bed_rect.bounds
    region_box = box(*region).buffer(1e-6)
    out = []
    if bed_wall in ("S", "N"):                      # łóżko wzdłuż x → szafki po lewej/prawej (x)
        y0 = by0 if bed_wall == "S" else by1 - ns.b
        for x0 in (bx0 - ns.a, bx1):
            rect = box(x0, y0, x0 + ns.a, y0 + ns.b)
            if _valid(rect, placed, zones) and rect.within(region_box):
                placed.append(rect)
                out.append(Furniture("nightstand", rect, room_id, ns.label))
    else:                                           # łóżko wzdłuż y → szafki góra/dół (y)
        x0 = bx0 if bed_wall == "W" else bx1 - ns.b
        for y0 in (by0 - ns.a, by1):
            rect = box(x0, y0, x0 + ns.b, y0 + ns.a)
            if _valid(rect, placed, zones) and rect.within(region_box):
                placed.append(rect)
                out.append(Furniture("nightstand", rect, room_id, ns.label))
    return out


def _furnish_bedroom(room: Room, windows: set, zones):
    """Łóżko na najdłuższej ścianie bez okna (wezgłowie do ściany) + szafki nocne + szafa."""
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    bed = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "bed")
    # ściany bez okna, najdłuższa najpierw; gdy wszystkie z oknem → którakolwiek (best-effort)
    cand = [w for w in ("S", "N", "W", "E") if w not in windows] or ["S", "N", "W", "E"]
    cand.sort(key=lambda w: _wall_len(region, w), reverse=True)
    bed_rect = None
    bed_wall = None
    for wall in cand:
        # wyśrodkuj łóżko na ścianie → miejsce na szafkę nocną z OBU stron (review #21)
        bed_rect = _place_on_wall(region, bed.a, bed.b, wall, placed, zones, prefer_center=True)
        if bed_rect is not None:
            bed_wall = wall
            break
    if bed_rect is None:
        warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na łóżko + dojście")
        return out, warn
    placed.append(bed_rect)
    out.append(Furniture("bed", bed_rect, room.spec.id, bed.label))
    # pas dostępu przed łóżkiem (keep-clear, nie mebel) — szafki/szafa go omijają
    cz = _clearance_zone(bed_rect, bed_wall, CLEARANCE["bed"])
    if cz is not None:
        placed.append(cz)
    # szafki nocne po bokach łóżka
    out += _flank_nightstands(bed_rect, bed_wall, region, placed, zones, room.spec.id)
    # szafa na innej ścianie bez okna; skróć (2.0→1.6→1.2 — drzwi przesuwne) zanim
    # zrezygnujesz, by nie ginęła w ciasnych/przy-drzwiowych sypialniach (review #23)
    ward = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "wardrobe")
    walls_for_ward = [w for w in cand if w != bed_wall]
    done_ward = False
    for length in (ward.b, 1.6, 1.2):
        for wall in walls_for_ward:
            wr = _place_on_wall(region, length, ward.a, wall, placed, zones)
            if wr is not None:
                placed.append(wr)
                out.append(Furniture("wardrobe", wr, room.spec.id, ward.label))
                done_ward = True
                break
        if done_ward:
            break
    return out, warn


def _furnish_kitchen(room: Room, windows: set, zones):
    """Liniowy blat kuchenny wzdłuż ściany z oknem (zlew pod oknem). Preferuj najdłuższe okno."""
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    counter = next(p for p in FURNITURE_SETS["kuchnia"] if p.type == "kitchen_counter")
    # preferuj ścianę z oknem (zlew pod oknem), ale NIE porzucaj reszty: gdy okno
    # zablokowane/za krótkie, blat ma trafić na wolną ścianę wewnętrzną (best-effort D2).
    walls = sorted(("S", "N", "W", "E"), key=lambda w: (w not in windows, -_wall_len(region, w)))
    rect = None
    for wall in walls:
        length = min(counter.b, _wall_len(region, wall))
        if length < 0.5:
            continue
        rect = _place_on_wall(region, length, counter.a, wall, placed, zones)
        if rect is not None:
            break
    if rect is None:
        warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na blat kuchenny")
        return out, warn
    out.append(Furniture("kitchen_counter", rect, room.spec.id, counter.label))
    return out, warn


def _furnish_bathroom(room: Room, windows: set, zones):
    """Armatura przy ścianach (best-effort); ostrzeżenie gdy brak miejsca na wannę/umywalkę.

    F2: łazienki są małe (≤5 m²), więc „liniowo wzdłuż jednej ściany" degraduje się do
    „przy ścianach" — _place_fixed snapuje do S/N/W/E. Pas dostępu przed WC/umywalką.
    """
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    key = room.spec.id.split("_")[0]
    # Kolejność: umywalka + WC (małe, każda łazienka ich potrzebuje) PRZED wanną (duża,
    # w ciasnej ≤5 m² potrafi je wypchnąć). review #22 — umywalki nie poświęcamy dla wanny.
    _PRIO = {"washbasin": 0, "basin": 0, "toilet": 1, "shower": 2, "bathtub": 2}
    for piece in sorted(FURNITURE_SETS[key], key=lambda p: _PRIO.get(p.type, 1)):
        rect = _place_fixed(region, piece.a, piece.b, placed, zones)
        if rect is None:
            if piece.type in ("bathtub", "washbasin"):
                warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na {piece.label.lower()}")
            continue
        placed.append(rect)
        out.append(Furniture(piece.type, rect, room.spec.id, piece.label))
    return out, warn


def _furnish_living(room: Room, windows: set, zones):
    """Sofa pod ścianą wewnętrzną (nie okno), TV naprzeciw (preferuj bez okna), stolik między nimi."""
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    sofa = next(p for p in FURNITURE_SETS["salon"] if p.type == "sofa")
    tv = next(p for p in FURNITURE_SETS["salon"] if p.type == "tv_unit")
    coffee = next(p for p in FURNITURE_SETS["salon"] if p.type == "coffee_table")
    # sofa pod ścianą wewnętrzną (nie okno), najdłuższą
    cand = [w for w in ("S", "N", "W", "E") if w not in windows] or ["S", "N", "W", "E"]
    cand.sort(key=lambda w: _wall_len(region, w), reverse=True)
    sofa_rect = sofa_wall = None
    for wall in cand:
        sofa_rect = _place_on_wall(region, sofa.b, sofa.a, wall, placed, zones)
        if sofa_rect is not None:
            sofa_wall = wall
            break
    if sofa_rect is None:
        return out, warn   # salon składa się rzadko; brak sofy nie jest "kluczowy" warning
    placed.append(sofa_rect)
    out.append(Furniture("sofa", sofa_rect, room.spec.id, sofa.label))
    # TV na ścianie naprzeciw sofy (preferuj bez okna)
    opp = _WALL_OPP[sofa_wall]
    tv_rect = _place_on_wall(region, tv.b, tv.a, opp, placed, zones)
    if tv_rect is not None:
        placed.append(tv_rect)
        out.append(Furniture("tv_unit", tv_rect, room.spec.id, tv.label))
    # stolik kawowy MIĘDZY sofą a TV (review #20): cel = środek odcinka sofa↔TV,
    # długi bok równolegle do sofy; fallback _place_fixed gdy środek zajęty.
    cr = None
    if tv_rect is not None:
        sc, tc = sofa_rect.centroid, tv_rect.centroid
        mx, my = (sc.x + tc.x) / 2, (sc.y + tc.y) / 2
        long_side, short_side = max(coffee.a, coffee.b), min(coffee.a, coffee.b)
        cw, cd = (long_side, short_side) if sofa_wall in ("S", "N") else (short_side, long_side)
        target = box(mx - cw / 2, my - cd / 2, mx + cw / 2, my + cd / 2)
        if _valid(target, placed, zones) and target.within(box(*region).buffer(1e-6)):
            cr = target
    if cr is None:
        cr = _place_fixed(region, coffee.a, coffee.b, placed, zones)
    if cr is not None:
        placed.append(cr)
        out.append(Furniture("coffee_table", cr, room.spec.id, coffee.label))
    return out, warn


def _shared_wall(host: Room, other: Room) -> str | None:
    """Ściana host (S/N/W/E) na wspólnej krawędzi z other — tylko gdy krawędzie REALNIE
    się nakładają (≥ MIN_JUNCTION); styk narożny/pozorny → None (review #13)."""
    hx0, hy0, hx1, hy1 = host.polygon.bounds
    ox0, oy0, ox1, oy1 = other.polygon.bounds
    t = 0.02
    MIN_JUNCTION = 0.9   # użyteczny otwór ≥ ~90 cm
    if abs(hx1 - ox0) < t or abs(hx0 - ox1) < t:        # styk pionowy (E/W) → nakładanie w y
        if min(hy1, oy1) - max(hy0, oy0) >= MIN_JUNCTION:
            return "E" if abs(hx1 - ox0) < t else "W"
    if abs(hy1 - oy0) < t or abs(hy0 - oy1) < t:        # styk poziomy (N/S) → nakładanie w x
        if min(hx1, ox1) - max(hx0, ox0) >= MIN_JUNCTION:
            return "N" if abs(hy1 - oy0) < t else "S"
    return None


def _place_dining(rooms, existing, door_zones):
    """Stół jadalny przy wspólnej krawędzi salon↔kuchnia (otwarta strefa dzienna).

    Próbuje stronę salonu, potem kuchni; preferuje ścianę styku (spec §2). Gdy przy
    styku brak miejsca — gdziekolwiek w pokoju (best-effort). Brak salonu lub kuchni → []
    (mała/zamknięta strefa dzienna nie dostaje stołu).
    """
    salon = next((r for r in rooms if r.spec.id.split("_")[0] == "salon" and r.polygon is not None), None)
    kuch = next((r for r in rooms if r.spec.id.split("_")[0] == "kuchnia" and r.polygon is not None), None)
    if salon is None or kuch is None:
        return []
    placed_by_room: dict[str, list[Polygon]] = {}
    for f in existing:
        placed_by_room.setdefault(f.room_id, []).append(f.polygon)
    for host, other in ((salon, kuch), (kuch, salon)):
        region = _inset(host.polygon)
        zones = door_zones.get(host.spec.id, []) + placed_by_room.get(host.spec.id, [])
        wall = _shared_wall(host, other)
        rect = None
        if wall is not None:   # wzdłuż krawędzi styku: bok stołu równolegle do ściany, głębokość w głąb
            rect = _place_on_wall(region, DINING_TABLE.b, DINING_TABLE.a, wall, [], zones)
        if rect is None:       # przy styku brak miejsca → gdziekolwiek (best-effort)
            rect = _place_fixed(region, DINING_TABLE.a, DINING_TABLE.b, [], zones)
        if rect is not None:
            return [Furniture("dining_table", rect, host.spec.id, DINING_TABLE.label)]
    return []


def _valid(rect: Polygon, placed: list[Polygon], zones: list[Polygon]) -> bool:
    for p in placed:
        if rect.intersection(p).area > 1e-6:
            return False
    for z in zones:
        if rect.intersection(z).area > 1e-6:
            return False
    return True


def _sweep(lo: float, hi: float, size: float):
    """Pozycje bliższego rogu mebla wzdłuż ściany od lo do hi (długość size)."""
    if hi - lo < size - 1e-9:
        return []
    pos = []
    x = lo
    while x <= hi - size + 1e-9:
        pos.append(x)
        x += STEP
    far = hi - size
    if not pos or pos[-1] < far - 1e-9:
        pos.append(far)
    return pos


def _place_fixed(region, a: float, b: float, placed, zones) -> Polygon | None:
    rx0, ry0, rx1, ry1 = region
    orientations = [(a, b)] if abs(a - b) < 1e-9 else [(a, b), (b, a)]
    for aw, ad in orientations:           # aw = wzdłuż ściany, ad = głębokość
        # ściana S (dół) i N (góra): mebel rozciąga się w x (aw), głębokość w y (ad)
        for wall in ("S", "N"):
            if ad > (ry1 - ry0) + 1e-9:
                continue
            y0 = ry0 if wall == "S" else ry1 - ad
            for x0 in _sweep(rx0, rx1, aw):
                rect = box(x0, y0, x0 + aw, y0 + ad)
                if _valid(rect, placed, zones):
                    return rect
        # ściana W (lewa) i E (prawa): mebel rozciąga się w y (aw), głębokość w x (ad)
        for wall in ("W", "E"):
            if ad > (rx1 - rx0) + 1e-9:
                continue
            x0 = rx0 if wall == "W" else rx1 - ad
            for y0 in _sweep(ry0, ry1, aw):
                rect = box(x0, y0, x0 + ad, y0 + aw)
                if _valid(rect, placed, zones):
                    return rect
    return None


def _place_linear(region, depth: float, cap: float, placed, zones) -> Polygon | None:
    rx0, ry0, rx1, ry1 = region
    # ściany poziome (S/N): ciąg wzdłuż x; pionowe (W/E): ciąg wzdłuż y
    for wall in ("S", "N", "W", "E"):
        if wall in ("S", "N"):
            length = min(cap, rx1 - rx0)
            if length < 0.5 or depth > (ry1 - ry0) + 1e-9:
                continue
            y0 = ry0 if wall == "S" else ry1 - depth
            rect = box(rx0, y0, rx0 + length, y0 + depth)
        else:
            length = min(cap, ry1 - ry0)
            if length < 0.5 or depth > (rx1 - rx0) + 1e-9:
                continue
            x0 = rx0 if wall == "W" else rx1 - depth
            rect = box(x0, ry0, x0 + depth, ry0 + length)
        if _valid(rect, placed, zones):
            return rect
    return None


def _place_on_wall(region, along: float, depth: float, wall: str, placed, zones,
                   prefer_center: bool = False) -> Polygon | None:
    """Połóż prostokąt (along × depth) przy danej ścianie (S/N/W/E) regionu.

    Przesuwa wzdłuż ściany (_sweep) szukając wolnego miejsca. None gdy się nie mieści.
    prefer_center=True → najpierw próbuje pozycji wyśrodkowanej (np. łóżko z szafkami z obu stron).
    """
    rx0, ry0, rx1, ry1 = region
    if wall in ("S", "N"):
        if depth > (ry1 - ry0) + 1e-9 or along > (rx1 - rx0) + 1e-9:
            return None
        y0 = ry0 if wall == "S" else ry1 - depth
        offsets = list(_sweep(rx0, rx1, along))
        if prefer_center and offsets:
            offsets = [rx0 + (rx1 - rx0 - along) / 2] + offsets
        for x0 in offsets:
            rect = box(x0, y0, x0 + along, y0 + depth)
            if _valid(rect, placed, zones):
                return rect
    else:  # W / E
        if depth > (rx1 - rx0) + 1e-9 or along > (ry1 - ry0) + 1e-9:
            return None
        x0 = rx0 if wall == "W" else rx1 - depth
        offsets = list(_sweep(ry0, ry1, along))
        if prefer_center and offsets:
            offsets = [ry0 + (ry1 - ry0 - along) / 2] + offsets
        for y0 in offsets:
            rect = box(x0, y0, x0 + depth, y0 + along)
            if _valid(rect, placed, zones):
                return rect
    return None


def _infer_door_zones(rooms: list[Room]) -> dict[str, list[Polygon]]:
    """Strefy drzwi per pokój: środek krawędzi wspólnej z pokojem KOMUNIKACJA.

    F5: w programie domu wszystkie pokoje łączą się przez hub — realne drzwi są
    tylko na krawędzi z hubem/wiatrołapem. Inferowanie drzwi z KAŻDEJ wspólnej
    krawędzi (np. łazienka↔garderoba) dawałoby fałszywe strefy i blokowało meble.
    """
    zones: dict[str, list[Polygon]] = {r.spec.id: [] for r in rooms if r.polygon is not None}
    valid = [r for r in rooms if r.polygon is not None]
    for a in valid:
        ax0, ay0, ax1, ay1 = a.polygon.bounds
        for b in valid:
            # tylko HOL/wiatrołap są źródłem drzwi; SCHODY (Approach B, też KOMUNIKACJA)
            # są pominięte — pokój dotykający klatki nie dostaje drzwi do schodów (F5: routing przez hol)
            if b is a or b.spec.strefa != Strefa.KOMUNIKACJA or b.spec.id == "schody":
                continue
            bx0, by0, bx1, by1 = b.polygon.bounds
            # krawędź pionowa wspólna (prawa A = lewa B, lub lewa A = prawa B)
            for ax, side in ((ax1, "E"), (ax0, "W")):
                bx = bx0 if side == "E" else bx1
                if abs(ax - bx) > 1e-6:
                    continue
                lo, hi = max(ay0, by0), min(ay1, by1)
                if hi - lo < DOOR_MIN_OVERLAP:
                    continue
                cy = (lo + hi) / 2
                if side == "E":
                    zones[a.spec.id].append(box(ax - DOOR_DEPTH, cy - DOOR_HALF, ax, cy + DOOR_HALF))
                else:
                    zones[a.spec.id].append(box(ax, cy - DOOR_HALF, ax + DOOR_DEPTH, cy + DOOR_HALF))
            # krawędź pozioma wspólna (góra A = dół B, lub dół A = góra B)
            for ay, side in ((ay1, "N"), (ay0, "S")):
                by = by0 if side == "N" else by1
                if abs(ay - by) > 1e-6:
                    continue
                lo, hi = max(ax0, bx0), min(ax1, bx1)
                if hi - lo < DOOR_MIN_OVERLAP:
                    continue
                cx = (lo + hi) / 2
                if side == "N":
                    zones[a.spec.id].append(box(cx - DOOR_HALF, ay - DOOR_DEPTH, cx + DOOR_HALF, ay))
                else:
                    zones[a.spec.id].append(box(cx - DOOR_HALF, ay, cx + DOOR_HALF, ay + DOOR_DEPTH))
    return zones
