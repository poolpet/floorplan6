"""
FloorPlanEngine — stałe konfiguracyjne.

Minimalne wymagania wg WT 2002, grubości ścian, parametry scorera.
Wagi scorera mogą być nadpisane przez statystyki z danych (dataset_stats).
"""
from __future__ import annotations

# === Grubości ścian [m] ===
WALL_THICKNESS_STRUCTURAL = 0.24   # ściany nośne (zewnętrzne, między lokalami)
WALL_THICKNESS_PARTITION = 0.12    # ściany działowe
WALL_THICKNESS_BATHROOM = 0.10     # ściany łazienkowe

# === WT 2002 — minimalne powierzchnie [m²] ===
WT_MIN_AREA = {
    "salon_kawalerka": 25.0,
    "salon": 16.0,
    "sypialnia_2os": 9.0,
    "sypialnia_1os": 6.0,
    "kuchnia": 6.0,
    "aneks_kuchenny": 4.0,
    "lazienka_wanna": 4.5,
    "lazienka_prysznic": 2.5,
    "wc": 1.5,
    "hub": 0.0,
}

# === WT 2002 — maksymalne powierzchnie [m²] (F2: NIENARUSZALNE) ===
# Klucz = prefix room_id (np. "lazienka_2" matchuje przez startswith).
# Patrz docs/FUNDAMENTAL_RULES.md F2 oraz docs/OPEN_QUESTIONS.md Q7 (DECIDED 2026-04-30).
WT_MAX_AREA = {
    "lazienka": 5.0,
    "wc": 3.0,
}

# === WT 2002 — minimalne szerokości [m] ===
WT_MIN_WIDTH = {
    "salon": 3.2,
    "sypialnia_2os": 2.4,
    "sypialnia_1os": 2.0,
    "kuchnia": 2.4,
    "lazienka": 1.5,
    "wc": 1.0,
    "hub": 1.2,
}

# === Proporcje pokoi ===
PROPORTION_OPTIMAL = 1.3
PROPORTION_MAX = 2.0
PROPORTION_ABSOLUTE_MAX = 2.5

# === Hub — % powierzchni użytkowej ===
HUB_MIN_PERCENT = {"M1": 0.08, "M2": 0.10, "M3": 0.10, "M4": 0.12, "M5": 0.12}
HUB_MAX_PERCENT = 0.15
HUB_MIN_AREA = {"M1": 4.0, "M2": 5.0, "M3": 6.0, "M4": 8.0, "M5": 10.0}

# === Orientacja fasad — współczynniki jakości ===
ORIENTATION_QUALITY = {
    "S": 1.0, "SW": 0.95, "SE": 0.90,
    "W": 0.85, "E": 0.80,
    "NW": 0.65, "NE": 0.60, "N": 0.50,
}

# === Scorer — wagi domyślne (nadpisywane z dataset_stats) ===
DEFAULT_SCORER_WEIGHTS = {
    "proporcje_pokoi": 0.25,
    "efektywnosc_huba": 0.20,
    "orientacja_salonu": 0.15,
    "powierzchnia_uzytkowa": 0.15,
    "separacja_stref": 0.15,
    "regularnosc_geometrii": 0.10,
}

# === Typy mieszkań ===
APARTMENT_TYPES = {
    "M1": {"nazwa": "Kawalerka", "min_pokoi": 2, "max_pokoi": 3},
    "M2": {"nazwa": "2-pokojowe", "min_pokoi": 3, "max_pokoi": 5},
    "M3": {"nazwa": "3-pokojowe", "min_pokoi": 4, "max_pokoi": 6},
    "M4": {"nazwa": "4-pokojowe", "min_pokoi": 5, "max_pokoi": 8},
    "M5": {"nazwa": "5-pokojowe", "min_pokoi": 6, "max_pokoi": 9},
}

# === Floor mode (etap 3): powierzchnie mieszkań [m²] ===
APARTMENT_MIN_AREA = {"M1": 35.0, "M2": 45.0, "M3": 60.0, "M4": 80.0, "M5": 100.0}
APARTMENT_OPT_AREA = {"M1": 40.0, "M2": 55.0, "M3": 75.0, "M4": 100.0, "M5": 130.0}
APARTMENT_MAX_ASPECT = 3.0  # max stosunek dł./szer. mieszkania
APARTMENT_MIX_DEFAULT = {"M1": 0.10, "M2": 0.30, "M3": 0.40, "M4": 0.10, "M5": 0.10}

# === Korytarze (WT §237 — Rozdział 7 mieszkania wielorodzinne) ===
WT_CORRIDOR_INTERNAL_MIN = 1.2   # korytarz wewnątrz mieszkania [m]
WT_CORRIDOR_PUBLIC_MIN = 1.4     # korytarz komunikacji ogólnej / ewakuacyjny [m]

# === Drogi ewakuacyjne (WT §256, ZL IV — mieszkalne wielorodzinne) ===
WT_DOJSCIE_MAX_1KLATKA = 10.0    # max długość dojścia gdy 1 klatka [m]
WT_DOJSCIE_MAX_2KLATKI = 40.0    # max długość krótszego dojścia gdy ≥2 klatki [m]
DOOR_MIN_WIDTH = 0.9             # min szer. drzwi mieszkanie/klatka (WT §239) [m]

# === Klatki schodowe (WT §66-69, mieszkalnictwo wielorodzinne) ===
WT_STAIR_BIEG_WIDTH = 0.9        # min szer. biegu (mieszk. wielorodz.) [m]
WT_STAIR_SPOCZNIK_WIDTH = 1.2    # spocznik typowy (≥ szer. biegu) [m]
WT_STAIR_GAP_BIEGS = 0.10        # szyb między biegami [m]
WT_STAIR_STEP_HEIGHT_MAX = 0.16  # max wys. stopnia (mieszk. wielorodz.) [m]
WT_STAIR_BLONDEL = 0.63          # wzór 2h + s = 0.63 (komfort) [m]
WT_STAIR_STEP_WIDTH_MIN = 0.25   # min szer. stopnia [m]

# === Winda (WT §54) ===
WT_ELEVATOR_HEIGHT_THRESHOLD = 9.5   # h_total > 9.5m → winda obowiązkowa [m]
WT_ELEVATOR_SHAFT_W = 1.5            # szyb windy mieszk. — szerokość [m]
WT_ELEVATOR_SHAFT_L = 1.7            # szyb windy mieszk. — głębokość [m]
WT_ELEVATOR_FIRE_W = 2.0             # winda ewakuacyjna (klasa W+) — szerokość [m]
WT_ELEVATOR_FIRE_L = 2.4             # winda ewakuacyjna — głębokość [m]
WT_ELEVATOR_WALL_GAP = 0.20          # ściana między klatką a szybem [m]

# === Klasy wysokości budynku (WT, dział VI) ===
# h_total = num_floors * h_kondygnacji
WT_BUILDING_CLASS_THRESHOLDS = {
    "N": 12.0,    # do 12 m (do 4 kondygnacji nadziemnych)
    "SW": 25.0,   # 12-25 m (5-9 kondygnacji)
    "W": 55.0,    # 25-55 m (10-18 kondygnacji)
    # WW: > 55m
}
WT_PRZEDSIONEK_DEPTH = {
    "N": 0.0,    # klatka otwarta dopuszczalna
    "SW": 1.0,   # klatka zamknięta drzwiami pożarowymi + przedsionek
    "W": 1.5,    # klatka przeciwpożarowa + DSO + większy przedsionek
    "WW": 1.5,   # jak W
}

# === Etap 3 — rezerwa powierzchni na komunikację ===
FLOOR_RESERVE_RATIO = 0.15  # 15% obrysu rezerwowane na korytarze + klatki
