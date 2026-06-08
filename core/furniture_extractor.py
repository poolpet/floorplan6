"""Stage 4 — meble (FurnishResult) -> obiekty biblioteczne ArchiCAD (CreateObjects).

Każdy umieszczony Furniture (Shapely box, plan-local metry) → obiekt biblioteczny:
nazwa z FURNITURE_LIBRARY_MAP, kotwica = lewy-dolny róg boxa, wymiary = rozmiar
boxa (orientacja 0/90° zakodowana w bounds — CreateObjects NIE przyjmuje kąta,
patrz _probe_roundtrip). Wzorzec jak wall/door/window_extractor:
dataclass -> extract_* -> *_to_tapir_payload.

Mapowanie = obiekty wybrane przez Dawida z AC29 BuiltInLibraryParts.libpack
(2026-06-08). Typy bez mapowania (boiler/shelving/shelves) są pomijane.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.furniture import FurnishResult, Furniture
from core.models import Room

# Łóżka rozróżniane per-pokój: największa sypialnia = master = podwójne.
BED_DOUBLE = "Łóżko podwójne 01"
BED_SINGLE = "Łóżko 01"
_BED_DOUBLE_DIM = (1.8, 2.0)
_BED_SINGLE_DIM = (0.9, 2.0)

# type -> (libraryPartName, dim_x, dim_y) — REALNE wymiary z obiektów wybranych
# przez Dawida w AC (2026-06-08), NIE rozmiar naszego boxa (to dawało dystorsję).
# Obiekt centrowany na centroidzie boxa; kąt 0° (CreateObjects nie obraca).
FURNITURE_LIBRARY_MAP: dict[str, tuple[str, float, float]] = {
    "bed": (BED_DOUBLE, *_BED_DOUBLE_DIM),   # master; secondary nadpisywane regułą
    "nightstand": ("Stolik nocny 01", 0.5, 0.3),
    "wardrobe": ("Garderoba 01", 1.2, 0.6),
    "sofa": ("Sofa", 1.6, 0.85),
    "coffee_table": ("Stolik kawowy 09", 0.7, 0.7),
    "tv_unit": ("Szafka RTV wisząca", 1.8, 0.4),
    "kitchen_counter": ("Zestaw mebli kuchennych", 1.92, 2.52),
    "dining_table": ("Stół jadalniany prostokątny", 2.6, 1.8),
    "bathtub": ("Wanna", 1.7, 0.75),
    "washbasin": ("Szafka z umywalką", 0.9, 0.6),
    "toilet": ("WC", 0.35, 0.64),
    "basin": ("Szafka z umywalką", 0.9, 0.6),
}


@dataclass
class FurnitureObject:
    """Mebel jako obiekt biblioteczny AC (plan-local metry, PRZED offsetem)."""
    library_part_name: str
    x: float        # kotwica = lewy-dolny róg boxa (min corner)
    y: float
    z: float
    dim_x: float
    dim_y: float
    piece_type: str
    room_id: str


def _master_bedroom_id(furniture: list[Furniture], rooms: list[Room]) -> Optional[str]:
    """Pokój z łóżkiem o największej powierzchni = master (→ łóżko podwójne)."""
    bed_rooms = {f.room_id for f in furniture if f.piece_type == "bed"}
    if not bed_rooms:
        return None
    area = {r.spec.id: (r.polygon.area if r.polygon is not None else 0.0) for r in rooms}
    return max(bed_rooms, key=lambda rid: area.get(rid, 0.0))


def extract_furniture(
    furnish_result: FurnishResult,
    rooms: list[Room],
) -> list[FurnitureObject]:
    """FurnishResult -> lista obiektów bibliotecznych (pomija niezmapowane typy)."""
    master = _master_bedroom_id(furnish_result.furniture, rooms)
    room_poly = {r.spec.id: r.polygon for r in rooms if r.polygon is not None}
    out: list[FurnitureObject] = []
    for f in furnish_result.furniture:
        entry = FURNITURE_LIBRARY_MAP.get(f.piece_type)
        if entry is None:
            continue
        name, dim_x, dim_y = entry
        if f.piece_type == "bed":
            name, dim_x, dim_y = (
                (BED_DOUBLE, *_BED_DOUBLE_DIM) if f.room_id == master
                else (BED_SINGLE, *_BED_SINGLE_DIM)
            )
        # Realne wymiary obiektu (bez rozciągania); kąt 0° (rotacja niedostępna).
        x0, y0 = _anchor(f.polygon, dim_x, dim_y, room_poly.get(f.room_id))
        out.append(FurnitureObject(
            library_part_name=name,
            x=x0, y=y0, z=0.0,
            dim_x=dim_x, dim_y=dim_y,
            piece_type=f.piece_type, room_id=f.room_id,
        ))
    return out


def _anchor(box_poly, dim_x: float, dim_y: float, room):
    """Kotwica (lewy-dolny róg obiektu o wymiarach dim_x×dim_y).

    Z pokojem: DOCIŚNIĘTY do ściany, przy której stoi box (najmniejsza szczelina
    box↔bbox pokoju), wycentrowany WZDŁUŻ tej ściany, na końcu CLAMP do bounds
    pokoju (nie wystaje poza obrys). Bez pokoju: centrowanie na centroidzie boxa.
    """
    bx0, by0, bx1, by1 = box_poly.bounds
    bxc, byc = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    if room is None:
        return bxc - dim_x / 2.0, byc - dim_y / 2.0

    rx0, ry0, rx1, ry1 = room.bounds
    gaps = {
        "left": bx0 - rx0, "right": rx1 - bx1,
        "bottom": by0 - ry0, "top": ry1 - by1,
    }
    wall = min(gaps, key=gaps.get)
    if wall == "bottom":
        x0, y0 = bxc - dim_x / 2.0, by0
    elif wall == "top":
        x0, y0 = bxc - dim_x / 2.0, by1 - dim_y
    elif wall == "left":
        x0, y0 = bx0, byc - dim_y / 2.0
    else:  # right
        x0, y0 = bx1 - dim_x, byc - dim_y / 2.0

    # CLAMP do bounds pokoju (obiekt większy od pokoju → dosunięty do rogu min).
    x0 = max(rx0, min(x0, rx1 - dim_x))
    y0 = max(ry0, min(y0, ry1 - dim_y))
    return x0, y0


def furniture_to_tapir_payload(
    objects: list[FurnitureObject],
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[dict]:
    """FurnitureObject -> payload CreateObjects (libraryPartName+coordinates+dimensions).

    offset (ox, oy) = przesunięcie do world coords (jak ściany/etykiety) — meble mają
    współrzędne absolutne, więc kotwicę przesuwamy; dimensions NIE.
    BEZ pola 'angle' — schemat CreateObjects ma additionalProperties:false.
    """
    ox, oy = offset
    return [{
        "libraryPartName": o.library_part_name,
        "coordinates": {"x": round(o.x + ox, 6), "y": round(o.y + oy, 6), "z": round(o.z, 6)},
        "dimensions": {"x": round(o.dim_x, 6), "y": round(o.dim_y, 6)},
    } for o in objects]
