# WT_PARAMETERS — parametry przepisów dla etapu 3 (podział piętra)

> Wszystkie liczby zakodowane w `config.py` z odnośnikami do paragrafów.
> Źródło: Rozporządzenie Ministra Infrastruktury z 12.04.2002 ws. warunków technicznych
> jakim powinny odpowiadać budynki i ich usytuowanie (z nowelizacją 2024-08-01).
>
> User w GUI może każdą wartość nadpisać (defaulty są bezpieczne dla typowego budynku PL).

---

## Korytarze (WT §237 + Rozdział 7 mieszkania wielorodzinne)

| Parametr | Wartość | Stała w config | Uzasadnienie |
|---|---|---|---|
| Korytarz wewnątrz mieszkania | min **1.2 m** | `WT_CORRIDOR_INTERNAL_MIN` | dop. miejscowe zwężenie do 0.9m × 1.5m dł. |
| Korytarz komunikacji ogólnej (ewakuacyjny) | min **1.4 m** | `WT_CORRIDOR_PUBLIC_MIN` | wielorodzinne, na drogę ewakuacji |

## Drogi ewakuacyjne (WT §256, ZL IV — mieszkalne wielorodzinne)

| Parametr | Wartość | Stała |
|---|---|---|
| Max długość dojścia gdy 1 klatka | **10 m** | `WT_DOJSCIE_MAX_1KLATKA` |
| Max długość krótszego dojścia gdy ≥2 klatki | **40 m** | `WT_DOJSCIE_MAX_2KLATKI` |
| Z DSO/oddymianiem | +100% (×2) | runtime computed |
| Min szer. drzwi mieszkanie/klatka | **0.9 m** | `DOOR_MIN_WIDTH` |

## Klatki schodowe (WT §66-69, mieszkalnictwo wielorodzinne)

| Parametr | Wartość | Stała |
|---|---|---|
| Min szer. biegu | **0.9 m** | `WT_STAIR_BIEG_WIDTH` |
| Spocznik typowy | **1.2 m** | `WT_STAIR_SPOCZNIK_WIDTH` |
| Szyb między biegami | **0.10 m** | `WT_STAIR_GAP_BIEGS` |
| Max wys. stopnia | **0.16 m** | `WT_STAIR_STEP_HEIGHT_MAX` |
| Wzór Blondela 2h+s | **0.63 m** | `WT_STAIR_BLONDEL` |
| Min szer. stopnia | **0.25 m** | `WT_STAIR_STEP_WIDTH_MIN` |

### Auto-compute klatki (`compute_stairwell_dimensions`)
```
n_steps = ceil(h_kondygnacji / 0.16), parzysta
h_step = h_kondygnacji / n_steps
s_step = 0.63 - 2*h_step (min 0.25)
bieg = (n_steps/2) × s_step
klatka_length = bieg + spocznik (+ przedsionek wg klasy)
klatka_width = 2*bieg_width + szyb (+ szyb windy jeśli wymagana)
```

## Winda (WT §54)

| Parametr | Wartość | Stała |
|---|---|---|
| Próg wymagalności (h_total) | **9.5 m** | `WT_ELEVATOR_HEIGHT_THRESHOLD` |
| Szyb mieszkalny | **1.5 × 1.7 m** | `WT_ELEVATOR_SHAFT_W/L` |
| Szyb ewakuacyjny (klasa W+) | **2.0 × 2.4 m** | `WT_ELEVATOR_FIRE_W/L` |
| Ściana między klatką a szybem | **0.20 m** | `WT_ELEVATOR_WALL_GAP` |

## Klasy wysokości budynku (WT, dział VI)

| Klasa | Wysokość budynku | Kondygnacje | Klatka | Przedsionek |
|---|---|---|---|---|
| **N** | ≤12 m | ≤4 | otwarta dopuszczalna | 0 m |
| **SW** | 12-25 m | 5-9 | zamknięta drzwi p.poż. | +1.0 m |
| **W** | 25-55 m | 10-18 | przeciwpożarowa + DSO | +1.5 m |
| **WW** | >55 m | >18 | jak W + winda ewakuacyjna | +1.5 m |

Stała: `WT_BUILDING_CLASS_THRESHOLDS`, `WT_PRZEDSIONEK_DEPTH`.

## Mieszkania (WT §93+ i praktyka)

| Typ | Min powierzchnia | Opt powierzchnia | Default % w mixie |
|---|---|---|---|
| M1 (kawalerka) | 35 m² | 40 m² | 10% |
| M2 (2-pokojowe) | 45 m² | 55 m² | 30% |
| M3 (3-pokojowe) | 60 m² | 75 m² | 40% |
| M4 (4-pokojowe) | 80 m² | 100 m² | 10% |
| M5 (5-pokojowe) | 100 m² | 130 m² | 10% |

Stałe: `APARTMENT_MIN_AREA`, `APARTMENT_OPT_AREA`, `APARTMENT_MIX_DEFAULT`.
Średnia ważona dla domyślnego mixu: ~73.5 m²/mieszkanie.

## Rezerwa na komunikację

| Parametr | Wartość | Stała |
|---|---|---|
| Rezerwa korytarze + klatki | **15%** obrysu | `FLOOR_RESERVE_RATIO` |

User w GUI może to obniżyć (więcej mieszkań, ciaśniej) lub zwiększyć (luźniej).

---

## Algorytm etapu 3 (FAZA 3)

7 kroków zaimplementowanych w `core/floor_solver.py` + `core/floor_compute.py`:

1. **Compute mieszkań:** `compute_apartment_count(area, mix, reserve)` → `{M1: n1, M2: n2...}`
2. **Compute klatek:** `compute_min_stairwells(polygon, h_floor, n_floors, dojscie_max)` → `{n_required, building_class}`
3. **Compute klatki dim:** `compute_stairwell_dimensions(h_floor, n_floors)` → `{stairwell_w, stairwell_l, has_elevator...}`
4. **Pozycje klatek** (heurystyka K-means lub równomierne)
5. **Voronoi → regiony per klatka** (clip do floor_polygon)
6. **Solver per region** (mieszkania + korytarze, dotychczasowy `solve_floor` z rozszerzeniem o korytarz)
7. **Walidacja Dijkstra** długości dojścia per mieszkanie. Jeśli > max → dodaj klatkę i wróć do (2).

## Przykłady (z `compute_stairwell_dimensions`)

| h kond. | Kondyg. | h_total | Klasa | n stopni | h step | s step | Klatka W×L | Winda | Trzon m² |
|---|---|---|---|---|---|---|---|---|---|
| 2.6 | 4 | 10.4 | N | 18 | 14.4cm | 34.2cm | 1.9 × 4.28m | TAK | ~12.6 |
| 2.8 | 4 | 11.2 | N | 18 | 15.6cm | 31.9cm | 1.9 × 4.07m | TAK | ~14.0 |
| 2.8 | 3 | 8.4 | N | 18 | 15.6cm | 31.9cm | 1.9 × 4.07m | NIE | ~7.7 |
| 3.0 | 5 | 15.0 | SW | 20 | 15.0cm | 33.0cm | 1.9 × 4.50m | TAK | ~16.6 |
| 3.2 | 8 | 25.6 | W | 20 | 16.0cm | 31.0cm | 2.4 × 4.60m | TAK | ~22.6 |
