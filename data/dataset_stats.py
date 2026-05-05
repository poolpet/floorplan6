"""
Ekstrakcja statystyk z datasetu → parametry LP solvera + scorera.

Oblicza rozkłady wymiarów pokoi, proporcje strefowe, wagi scorera.
Wynik zapisywany do stats_cache.json (regeneracja: `python main.py rebuild-stats`).
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from data.dataset_loader import (
    Dataset, LoadedPlan, LoadedApartment, LoadedRoom,
    RoomCategory, load_dataset,
)


# ============================================================
# Struktury wynikowe
# ============================================================

@dataclass
class RoomStats:
    """Statystyki dla jednej kategorii pokoju w danym typie mieszkania."""
    category: str
    count: int
    area_min: float
    area_max: float
    area_median: float
    area_p25: float
    area_p75: float
    percent_of_total_median: float  # % pow. mieszkania


@dataclass
class ApartmentTypeStats:
    """Statystyki dla jednego typu mieszkania (M1–M5)."""
    mtype: str
    count: int
    area_min: float
    area_max: float
    area_median: float
    n_rooms_median: float
    hub_percent_median: float
    room_stats: dict[str, RoomStats]  # klucz = RoomCategory.value


@dataclass
class DatasetStats:
    """Kompletne statystyki datasetu."""
    total_apartments: int
    total_plans: int
    by_type: dict[str, ApartmentTypeStats]

    def get_room_stats(self, mtype: str, category: RoomCategory) -> Optional[RoomStats]:
        """Pobierz statystyki pokoju dla danego typu mieszkania."""
        ts = self.by_type.get(mtype)
        if ts is None:
            return None
        return ts.room_stats.get(category.value)


# ============================================================
# Obliczanie statystyk
# ============================================================

def _percentile(data: list[float], p: float) -> float:
    """Percentyl z listy (0-100)."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(s):
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


def _compute_room_stats(
    rooms: list[tuple[LoadedRoom, float]],  # (pokój, pow. mieszkania)
    category: RoomCategory,
) -> RoomStats:
    """Oblicz statystyki dla grupy pokoi jednej kategorii."""
    areas = [r.area_m2 for r, _ in rooms]
    percents = [r.area_m2 / total * 100 for r, total in rooms if total > 0]

    return RoomStats(
        category=category.value,
        count=len(areas),
        area_min=min(areas) if areas else 0,
        area_max=max(areas) if areas else 0,
        area_median=statistics.median(areas) if areas else 0,
        area_p25=_percentile(areas, 25),
        area_p75=_percentile(areas, 75),
        percent_of_total_median=statistics.median(percents) if percents else 0,
    )


def compute_stats(ds: Dataset) -> DatasetStats:
    """Oblicz pełne statystyki z datasetu."""
    by_type: dict[str, ApartmentTypeStats] = {}

    for mtype in ["M1", "M2", "M3", "M4", "M5"]:
        # Zbierz dane z obu źródeł
        all_areas: list[float] = []
        all_n_rooms: list[int] = []
        rooms_by_cat: dict[str, list[tuple[LoadedRoom, float]]] = defaultdict(list)

        # Z plans (mają polygony)
        for plan in ds.plans_by_type(mtype):
            all_areas.append(plan.total_area_m2)
            all_n_rooms.append(plan.n_rooms)
            for room in plan.rooms:
                rooms_by_cat[room.category.value].append((room, plan.total_area_m2))

        # Z apartments (metraże)
        for apt in ds.apartments_by_type(mtype):
            all_areas.append(apt.area_m2)
            all_n_rooms.append(apt.n_rooms)
            for room in apt.rooms:
                rooms_by_cat[room.category.value].append((room, apt.area_m2))

        if not all_areas:
            continue

        # Hub percent
        hub_rooms = rooms_by_cat.get(RoomCategory.HUB.value, [])
        hub_percents = [r.area_m2 / total * 100 for r, total in hub_rooms if total > 0]

        # Statystyki per kategoria pokoju
        room_stats = {}
        for cat_val, room_list in rooms_by_cat.items():
            cat = RoomCategory(cat_val)
            room_stats[cat_val] = _compute_room_stats(room_list, cat)

        by_type[mtype] = ApartmentTypeStats(
            mtype=mtype,
            count=len(all_areas),
            area_min=min(all_areas),
            area_max=max(all_areas),
            area_median=statistics.median(all_areas),
            n_rooms_median=statistics.median(all_n_rooms),
            hub_percent_median=statistics.median(hub_percents) if hub_percents else 12.0,
            room_stats=room_stats,
        )

    return DatasetStats(
        total_apartments=len(ds.apartments),
        total_plans=len(ds.plans),
        by_type=by_type,
    )


def save_stats(stats: DatasetStats, path: Optional[Path] = None) -> Path:
    """Zapisz statystyki do JSON."""
    if path is None:
        path = Path(__file__).parent / "stats_cache.json"

    data = {
        "total_apartments": stats.total_apartments,
        "total_plans": stats.total_plans,
        "by_type": {},
    }
    for mtype, ts in stats.by_type.items():
        data["by_type"][mtype] = {
            "count": ts.count,
            "area_min": round(ts.area_min, 2),
            "area_max": round(ts.area_max, 2),
            "area_median": round(ts.area_median, 2),
            "n_rooms_median": round(ts.n_rooms_median, 1),
            "hub_percent_median": round(ts.hub_percent_median, 2),
            "room_stats": {
                cat: {
                    "count": rs.count,
                    "area_min": round(rs.area_min, 2),
                    "area_max": round(rs.area_max, 2),
                    "area_median": round(rs.area_median, 2),
                    "area_p25": round(rs.area_p25, 2),
                    "area_p75": round(rs.area_p75, 2),
                    "percent_median": round(rs.percent_of_total_median, 2),
                }
                for cat, rs in ts.room_stats.items()
            },
        }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_stats(path: Optional[Path] = None) -> Optional[dict]:
    """Wczytaj cached statystyki (surowy dict)."""
    if path is None:
        path = Path(__file__).parent / "stats_cache.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    ds = load_dataset()
    stats = compute_stats(ds)
    path = save_stats(stats)
    print(f"Statystyki zapisane do {path}")
    print()

    for mtype in ["M1", "M2", "M3", "M4", "M5"]:
        ts = stats.by_type.get(mtype)
        if ts is None:
            continue
        print(f"=== {mtype} ({ts.count} mieszkań) ===")
        print(f"  Pow: {ts.area_min:.0f}–{ts.area_max:.0f} m² (mediana: {ts.area_median:.1f})")
        print(f"  Hub: {ts.hub_percent_median:.1f}% pow.")
        for cat, rs in sorted(ts.room_stats.items()):
            print(f"  {cat:15s}: {rs.area_median:5.1f} m² "
                  f"({rs.area_min:.1f}–{rs.area_max:.1f}), "
                  f"{rs.percent_of_total_median:.0f}% pow., n={rs.count}")
        print()
