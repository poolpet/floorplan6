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

# Kuchnia z POJEDYNCZYCH mebli (decyzja Dawida 2026-06-09): zamiast composite
# `Zestaw mebli kuchennych` (3 nieusuwalne blokady: długość 3 m na sztywno, pozycje AGD
# na sztywno=floatują, brak rotacji) rozbijamy blat na rząd modułów 0.6 m: lodówka +
# N szafek dolnych. Każdy moduł = zwykły obiekt z A/B (ścieżka która DZIAŁA).
KITCHEN_MODULE = 0.6

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
    "kitchen_counter": ("Zestaw mebli kuchennych", 1.92, 2.52),  # nieużywane (blat rozbijany)
    "base_cabinet": ("Szafka podstawowa", 0.6, 0.58),   # moduł kuchni (wybór Dawida 2026-06-09)
    "fridge": ("Lodówka", 0.6, 0.6),                    # moduł kuchni (wybór Dawida 2026-06-09)
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
    # dodatkowe parametry GDL do ustawienia poza A/B (np. wyposażenie szafki kuchennej:
    # bCounter/bSink/bCooktop). Tuple par (name, value) — domyślnie brak.
    gdl_extra: tuple = ()


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
    """FurnishResult -> lista obiektów bibliotecznych (pomija niezmapowane typy).

    AC odwzorowuje box solvera 1:1: kotwica = lewy-dolny róg boxa, A/B = wymiary boxa.
    Renderer matplotlib rysuje TEN SAM box → AC = render (zaakceptowany przez Dawida).
    BEZ re-derywacji orientacji/pozycji (dawne _orient_to_box/_anchor rozjeżdżały skalę
    sofy i lokalizację wszystkich mebli — sonda 2026-06-09: punkt odniesienia AC =
    lewy-dolny róg, więc box solvera ląduje 1:1). Mapa daje TYLKO nazwę biblioteczną.
    """
    master = _master_bedroom_id(furnish_result.furniture, rooms)
    out: list[FurnitureObject] = []
    for f in furnish_result.furniture:
        if f.piece_type == "kitchen_counter":
            # Kuchnia z pojedynczych mebli — rozbij blat na rząd modułów (lodówka+szafki).
            out.extend(_expand_kitchenette(f))
            continue
        entry = FURNITURE_LIBRARY_MAP.get(f.piece_type)
        if entry is None:
            continue
        name = entry[0]
        if f.piece_type == "bed":
            name = BED_DOUBLE if f.room_id == master else BED_SINGLE
        bx0, by0, bx1, by1 = f.polygon.bounds
        out.append(FurnitureObject(
            library_part_name=name,
            x=bx0, y=by0, z=0.0,
            dim_x=bx1 - bx0, dim_y=by1 - by0,
            piece_type=f.piece_type, room_id=f.room_id,
        ))
    return out


def _expand_kitchenette(f: Furniture) -> list[FurnitureObject]:
    """Blat (kitchen_counter box) -> rząd modułów 0.6 m wzdłuż ściany: lodówka + N szafek.

    Liczba modułów = ile 0.6 m zmieści się na biegu (floor, bez przepełnienia). Lodówka
    na początku biegu, reszta to szafki dolne („Szafka podstawowa"). Wyposażenie (wybór
    Dawida 2026-06-09): każda szafka ma blat (bCounter); JEDNA dostaje płytę (bCooktop, na
    końcu biegu), JEDNA zlew (bSink, ~środek) — w razie 1 szafki obie funkcje na niej.
    Orientacja przez przypisanie dim (moduł wzdłuż ściany, głębokość w poprzek) — działa
    dla pojedynczych obiektów (swap dim_x/y). Kotwica = lewy-dolny róg modułu (+X/+Y).
    """
    bx0, by0, bx1, by1 = f.polygon.bounds
    w, h = bx1 - bx0, by1 - by0
    horizontal = w >= h
    run, depth = max(w, h), min(w, h)
    n = max(1, int(run // KITCHEN_MODULE))
    fridge_name = FURNITURE_LIBRARY_MAP["fridge"][0]
    cab_name = FURNITURE_LIBRARY_MAP["base_cabinet"][0]
    cab_mods = list(range(1, n))                       # indeksy modułów-szafek (po lodówce)
    cooktop_mod = cab_mods[-1] if cab_mods else None   # płyta na końcu (daleko od lodówki)
    sink_mod = cab_mods[(len(cab_mods) - 1) // 2] if cab_mods else None  # zlew ~środek szafek
    out: list[FurnitureObject] = []
    for i in range(n):
        if horizontal:
            ax, ay = bx0 + i * KITCHEN_MODULE, by0
            dx, dy = KITCHEN_MODULE, depth      # moduł wzdłuż X, głębokość w Y
        else:
            ax, ay = bx0, by0 + i * KITCHEN_MODULE
            dx, dy = depth, KITCHEN_MODULE      # głębokość w X, moduł wzdłuż Y (swap)
        if i == 0:
            out.append(FurnitureObject(fridge_name, ax, ay, 0.0, dx, dy, "fridge", f.room_id))
        else:
            extra = (("bCounter", True),
                     ("bSink", i == sink_mod),
                     ("bCooktop", i == cooktop_mod))
            out.append(FurnitureObject(cab_name, ax, ay, 0.0, dx, dy, "base_cabinet",
                                       f.room_id, gdl_extra=extra))
    return out


def furniture_to_create_payload(
    objects: list[FurnitureObject],
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[dict]:
    """FurnitureObject -> payload CreateObjects (libraryPartName + coordinates).

    BEZ `dimensions`: AC czyta CreateObjects.dimensions jako MNOŻNIK domyślnego A/B
    (nie metry — źródło Tapira), więc obiekt tworzymy w rozmiarze domyślnym, a realny
    rozmiar ustawiamy potem przez A/B (furniture_to_gdl_payload + SetGDLParametersOfElements).
    offset (ox, oy) = przesunięcie do world coords (jak ściany/etykiety).
    BEZ pola 'angle' — schemat CreateObjects ma additionalProperties:false.
    """
    ox, oy = offset
    return [{
        "libraryPartName": o.library_part_name,
        "coordinates": {"x": round(o.x + ox, 6), "y": round(o.y + oy, 6), "z": round(o.z, 6)},
    } for o in objects]


def furniture_to_gdl_payload(
    objects: list[FurnitureObject],
    guids: list[str],
) -> list[dict]:
    """(objects, utworzone guids) -> payload SetGDLParametersOfElements (A/B w metrach).

    A = oś X (dim_x), B = oś Y (dim_y) — realny rozmiar każdego obiektu. Alignment
    guid↔obiekt po indeksie (CreateObjects zwraca guidy w kolejności); jeśli długości
    się nie zgadzają (AC pominęło część) → [] (nie ryzykuj cudzego A/B).
    """
    if len(guids) != len(objects):
        return []
    out: list[dict] = []
    for o, guid in zip(objects, guids):
        params = [
            {"name": "A", "value": round(o.dim_x, 6)},
            {"name": "B", "value": round(o.dim_y, 6)},
        ]
        params += [{"name": n, "value": v} for n, v in o.gdl_extra]
        out.append({"elementId": {"guid": guid}, "gdlParameters": params})
    return out
