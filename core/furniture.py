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
        furniture.extend(_furnish_room(room, key, door_zones.get(room.spec.id, [])))
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
    # lazy import: nie ciągnij ortools (cpsat_solver) do importu furniture
    from core.cpsat_solver import _detect_facade_sides
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


def _place_on_wall(region, along: float, depth: float, wall: str, placed, zones) -> Polygon | None:
    """Połóż prostokąt (along × depth) przy danej ścianie (S/N/W/E) regionu.

    Przesuwa wzdłuż ściany (_sweep) szukając wolnego miejsca. None gdy się nie mieści.
    """
    rx0, ry0, rx1, ry1 = region
    if wall in ("S", "N"):
        if depth > (ry1 - ry0) + 1e-9 or along > (rx1 - rx0) + 1e-9:
            return None
        y0 = ry0 if wall == "S" else ry1 - depth
        for x0 in _sweep(rx0, rx1, along):
            rect = box(x0, y0, x0 + along, y0 + depth)
            if _valid(rect, placed, zones):
                return rect
    else:  # W / E
        if depth > (rx1 - rx0) + 1e-9 or along > (ry1 - ry0) + 1e-9:
            return None
        x0 = rx0 if wall == "W" else rx1 - depth
        for y0 in _sweep(ry0, ry1, along):
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
