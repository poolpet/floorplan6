"""
Wczytywanie danych rzutów z dwóch źródeł:
  - data/plans/PL_*.json  (27 obrysowanych rzutów z polygonami)
  - data/all_71_apartments.json  (71 mieszkań — metraże pokoi)

Mapowanie nazw pokoi na ujednolicone kategorie (RYZYKO 7 z CLAUDE.md).
"""
from __future__ import annotations

import json
import glob
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ============================================================
# Kategorie pokoi — ujednolicone
# ============================================================

class RoomCategory(str, Enum):
    """Ujednolicona kategoria pokoju."""
    HUB = "hub"
    SALON_ANEKS = "salon_aneks"
    SYPIALNIA = "sypialnia"
    LAZIENKA = "lazienka"
    WC = "wc"
    GARDEROBA = "garderoba"
    PRALNIA = "pralnia"


# Mapowanie room_type (numeryczny ID z PL_*.json) → kategoria
ROOM_TYPE_TO_CATEGORY: dict[int, RoomCategory] = {
    1: RoomCategory.SYPIALNIA,
    3: RoomCategory.LAZIENKA,
    4: RoomCategory.WC,
    5: RoomCategory.HUB,
    6: RoomCategory.HUB,         # Przedpokój = hub
    7: RoomCategory.GARDEROBA,
    10: RoomCategory.SYPIALNIA,  # POKÓJ/pokój = sypialnia
    13: RoomCategory.PRALNIA,
    17: RoomCategory.SALON_ANEKS,
}

# Mapowanie nazw tekstowych (all_71_apartments.json) → kategoria
# Klucze lowercase, porównanie case-insensitive
_NAME_TO_CATEGORY: dict[str, RoomCategory] = {
    "hol": RoomCategory.HUB,
    "przedpokój": RoomCategory.HUB,
    "łazienka": RoomCategory.LAZIENKA,
    "wc": RoomCategory.WC,
    "garderoba": RoomCategory.GARDEROBA,
    "pralnia": RoomCategory.PRALNIA,
    "pokój": RoomCategory.SYPIALNIA,
    "sypialnia": RoomCategory.SYPIALNIA,
    "pokój dz. + a. kuchenny": RoomCategory.SALON_ANEKS,
    "pokój z aneksem kuchennym": RoomCategory.SALON_ANEKS,
    "pokój z aneksem": RoomCategory.SALON_ANEKS,
    "salon z aneksem kuchennym": RoomCategory.SALON_ANEKS,
}


def name_to_category(name: str) -> RoomCategory:
    """Zamień nazwę tekstową pokoju na kategorię.

    Rzuca ValueError jeśli nazwa nieznana — żadnych cichych skip-ów.
    """
    key = name.strip().lower()
    cat = _NAME_TO_CATEGORY.get(key)
    if cat is None:
        raise ValueError(
            f"Nieznana nazwa pokoju: '{name}'. "
            f"Dodaj mapowanie do _NAME_TO_CATEGORY w dataset_loader.py"
        )
    return cat


def room_type_to_category(room_type: int) -> RoomCategory:
    """Zamień numeryczny room_type na kategorię.

    Rzuca ValueError jeśli typ nieznany.
    """
    cat = ROOM_TYPE_TO_CATEGORY.get(room_type)
    if cat is None:
        raise ValueError(
            f"Nieznany room_type: {room_type}. "
            f"Dodaj mapowanie do ROOM_TYPE_TO_CATEGORY w dataset_loader.py"
        )
    return cat


# ============================================================
# Struktury danych
# ============================================================

@dataclass
class LoadedRoom:
    """Pokój wczytany z datasetu — ujednolicony format."""
    category: RoomCategory
    original_name: str
    area_m2: float
    polygon: Optional[list[dict]] = None  # lista {"x": float, "y": float}
    room_type_id: Optional[int] = None


@dataclass
class LoadedPlan:
    """Rzut z polygonami (PL_*.json)."""
    id: str
    original_id: str
    copies: list[str]
    apartment_type: str
    total_area_m2: float
    width_m: float
    height_m: float
    aspect_ratio: float
    n_rooms: int
    rooms: list[LoadedRoom]
    edges: list[dict]
    source_file: str
    entry_position: Optional[tuple[float, float]] = None  # (x, y) w metrach
    boundary_edges: Optional[list[dict]] = None  # krawędzie obrysu z wall_type


@dataclass
class LoadedApartment:
    """Mieszkanie z metrażami (all_71_apartments.json)."""
    id: str
    mtype: str
    area_m2: float
    floor: str
    unit: str
    n_rooms: int
    rooms: list[LoadedRoom]


@dataclass
class Dataset:
    """Kompletny dataset — oba źródła."""
    plans: list[LoadedPlan]
    apartments: list[LoadedApartment]

    @property
    def all_rooms(self) -> list[LoadedRoom]:
        """Wszystkie pokoje z obu źródeł (do statystyk)."""
        rooms = []
        for p in self.plans:
            rooms.extend(p.rooms)
        for a in self.apartments:
            rooms.extend(a.rooms)
        return rooms

    def plans_by_type(self, mtype: str) -> list[LoadedPlan]:
        return [p for p in self.plans if p.apartment_type == mtype]

    def apartments_by_type(self, mtype: str) -> list[LoadedApartment]:
        return [a for a in self.apartments if a.mtype == mtype]


# ============================================================
# Ładowanie
# ============================================================

def _get_data_dir() -> Path:
    """Zwróć ścieżkę do katalogu data/."""
    return Path(__file__).parent


def load_plans(data_dir: Optional[Path] = None) -> list[LoadedPlan]:
    """Wczytaj wszystkie PL_*.json z data/plans/."""
    if data_dir is None:
        data_dir = _get_data_dir()
    plans_dir = data_dir / "plans"
    results = []

    for fp in sorted(plans_dir.glob("PL_*.json")):
        with open(fp, encoding="utf-8") as f:
            raw = json.load(f)

        rooms = []
        for r in raw["rooms"]:
            cat = room_type_to_category(r["room_type"])
            rooms.append(LoadedRoom(
                category=cat,
                original_name=r["label"],
                area_m2=r["area_m2"],
                polygon=r.get("polygon"),
                room_type_id=r["room_type"],
            ))

        # Entry position z JSON (jeśli zapisane)
        ep = raw.get("entry_position")
        entry_pos = (ep["x"], ep["y"]) if ep else None

        plan = LoadedPlan(
            id=raw["id"],
            original_id=raw.get("original_id", raw["id"]),
            copies=raw.get("copies", []),
            apartment_type=raw["apartment_type"],
            total_area_m2=raw["total_area_m2"],
            width_m=raw["width_m"],
            height_m=raw["height_m"],
            aspect_ratio=raw.get("aspect_ratio", 0),
            n_rooms=raw["n_rooms"],
            rooms=rooms,
            edges=raw.get("edges", []),
            source_file=fp.name,
            entry_position=entry_pos,
            boundary_edges=raw.get("boundary_edges"),
        )
        results.append(plan)

    return results


def load_apartments(data_dir: Optional[Path] = None) -> list[LoadedApartment]:
    """Wczytaj all_71_apartments.json."""
    if data_dir is None:
        data_dir = _get_data_dir()
    fp = data_dir / "all_71_apartments.json"

    with open(fp, encoding="utf-8") as f:
        raw_list = json.load(f)

    results = []
    for raw in raw_list:
        rooms = []
        for r in raw["rooms"]:
            cat = name_to_category(r["name"])
            rooms.append(LoadedRoom(
                category=cat,
                original_name=r["name"],
                area_m2=r["area_m2"],
            ))

        apt = LoadedApartment(
            id=raw["id"],
            mtype=raw["mtype"],
            area_m2=raw["area_m2"],
            floor=raw.get("floor", ""),
            unit=raw.get("unit", ""),
            n_rooms=raw["n_rooms"],
            rooms=rooms,
        )
        results.append(apt)

    return results


def _enrich_plans_with_entry_positions(plans: list[LoadedPlan], data_dir: Path):
    """Wzbogać plany o entry_position przeliczoną z pikseli (all_traced.json).

    Piksele → metry: skala = plan_dimension / pixel_bbox_dimension.
    Y w pikselach rośnie w dół, w metrach w górę — odwracamy.
    """
    traced_path = data_dir.parent / "rzuty" / "all_traced.json"
    if not traced_path.exists():
        return

    with open(traced_path, encoding="utf-8") as f:
        traced = json.load(f)

    plan_by_orig = {p.original_id.replace("PL_", ""): p for p in plans}

    for key, tdata in traced.items():
        plan = plan_by_orig.get(key)
        if plan is None or plan.entry_position is not None:
            continue

        rooms = tdata.get("rooms", [])
        all_pts = []
        for r in rooms:
            all_pts.extend(r.get("points", []))
        if not all_pts:
            continue

        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        px_w = max(xs) - min(xs)
        px_h = max(ys) - min(ys)
        if px_w == 0 or px_h == 0:
            continue

        scale_x = plan.width_m / px_w
        scale_y = plan.height_m / px_h

        entry_doors = [d for d in tdata.get("doors", []) if d["doorType"] == "entry"]
        if entry_doors:
            ed = entry_doors[0]
            entry_x_m = (ed["x"] - min(xs)) * scale_x
            entry_y_m = plan.height_m - (ed["y"] - min(ys)) * scale_y
            plan.entry_position = (round(entry_x_m, 2), round(entry_y_m, 2))


def load_dataset(data_dir: Optional[Path] = None) -> Dataset:
    """Wczytaj kompletny dataset z obu źródeł."""
    if data_dir is None:
        data_dir = _get_data_dir()
    plans = load_plans(data_dir)
    apartments = load_apartments(data_dir)
    _enrich_plans_with_entry_positions(plans, data_dir)
    return Dataset(plans=plans, apartments=apartments)


# ============================================================
# CLI — szybki test
# ============================================================

if __name__ == "__main__":
    ds = load_dataset()
    print(f"Wczytano {len(ds.plans)} rzutów z polygonami")
    print(f"Wczytano {len(ds.apartments)} mieszkań z metrażami")
    print()

    # Sprawdź pokrycie typów
    for mtype in ["M1", "M2", "M3", "M4", "M5"]:
        plans = ds.plans_by_type(mtype)
        apts = ds.apartments_by_type(mtype)
        print(f"  {mtype}: {len(plans)} rzutów, {len(apts)} mieszkań")

    # Test: żaden pokój nie został pominięty
    total_rooms = len(ds.all_rooms)
    print(f"\nŁącznie pokoi: {total_rooms}")
    print("Wszystkie pokoje zmapowane — OK")
