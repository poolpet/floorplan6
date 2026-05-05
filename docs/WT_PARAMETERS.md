# WT_PARAMETERS — Polish Building Code values used in Stage 3

> All numeric values are hard-coded in `config.py` with paragraph references
> back to the regulation. The user can override every value from the GUI;
> defaults are safe for a typical Polish multi-family residential building.
>
> **Source:** Regulation of the Minister of Infrastructure of 12 April 2002
> on the technical conditions to be met by buildings and their location
> (consolidated text, amended 2024-08-01). Abbreviated in this document as
> "WT" (*Warunki Techniczne*).

---

## Corridors (WT § 237 + Chapter 7 — multi-family dwellings)

| Parameter | Value | Constant in `config.py` | Notes |
|---|---|---|---|
| Corridor inside an apartment | min **1.2 m** | `WT_CORRIDOR_INTERNAL_MIN` | local narrowing to 0.9 m × 1.5 m allowed |
| Public / evacuation corridor | min **1.4 m** | `WT_CORRIDOR_PUBLIC_MIN` | multi-family, on the evacuation route |

## Evacuation routes (WT § 256, ZL IV — multi-family residential)

| Parameter | Value | Constant |
|---|---|---|
| Max walking distance with 1 stairwell | **10 m** | `WT_DOJSCIE_MAX_1KLATKA` |
| Max length of the shorter walk with ≥ 2 stairwells | **40 m** | `WT_DOJSCIE_MAX_2KLATKI` |
| With smoke-control system / DSO | +100 % (× 2) | computed at runtime |
| Min apartment-to-stairwell door width | **0.9 m** | `DOOR_MIN_WIDTH` |

## Stairwells (WT § 66–69, multi-family)

| Parameter | Value | Constant |
|---|---|---|
| Min flight width | **0.9 m** | `WT_STAIR_BIEG_WIDTH` |
| Standard landing depth | **1.2 m** | `WT_STAIR_SPOCZNIK_WIDTH` |
| Gap between flights | **0.10 m** | `WT_STAIR_GAP_BIEGS` |
| Max riser height | **0.16 m** | `WT_STAIR_STEP_HEIGHT_MAX` |
| Blondel formula 2h + s | **0.63 m** | `WT_STAIR_BLONDEL` |
| Min tread depth | **0.25 m** | `WT_STAIR_STEP_WIDTH_MIN` |

### Auto-computed stairwell (`compute_stairwell_dimensions`)
```
n_steps         = ceil(floor_height / 0.16), rounded up to an even number
h_step          = floor_height / n_steps
s_step          = 0.63 - 2 * h_step (min 0.25)
flight_length   = (n_steps / 2) * s_step
shaft_length    = flight_length + landing (+ vestibule per building class)
shaft_width     = 2 * flight_width + gap (+ elevator shaft width if required)
```

## Elevator (WT § 54)

| Parameter | Value | Constant |
|---|---|---|
| Mandatory above building height | **9.5 m** | `WT_ELEVATOR_HEIGHT_THRESHOLD` |
| Residential shaft | **1.5 × 1.7 m** | `WT_ELEVATOR_SHAFT_W/L` |
| Fire-evacuation shaft (class W or higher) | **2.0 × 2.4 m** | `WT_ELEVATOR_FIRE_W/L` |
| Wall between stairwell and shaft | **0.20 m** | `WT_ELEVATOR_WALL_GAP` |

## Building height classes (WT, Section VI)

| Class | Building height | Storeys | Stairwell type | Vestibule depth |
|---|---|---|---|---|
| **N** (low) | ≤ 12 m | ≤ 4 | open allowed | 0 m |
| **SW** (medium-low) | 12–25 m | 5–9 | enclosed, fire doors | + 1.0 m |
| **W** (medium-high) | 25–55 m | 10–18 | fire-rated + smoke control | + 1.5 m |
| **WW** (high) | > 55 m | > 18 | as W + fire-evacuation lift | + 1.5 m |

Constants: `WT_BUILDING_CLASS_THRESHOLDS`, `WT_PRZEDSIONEK_DEPTH`.

## Apartment sizes (WT § 93+ and common practice)

| Type | Min area | Optimal area | Default mix share |
|---|---|---|---|
| M1 (studio) | 35 m² | 40 m² | 10 % |
| M2 (2-room) | 45 m² | 55 m² | 30 % |
| M3 (3-room) | 60 m² | 75 m² | 40 % |
| M4 (4-room) | 80 m² | 100 m² | 10 % |
| M5 (5-room) | 100 m² | 130 m² | 10 % |

Constants: `APARTMENT_MIN_AREA`, `APARTMENT_OPT_AREA`, `APARTMENT_MIX_DEFAULT`.
Weighted average for the default mix: ≈ 73.5 m² per apartment.

## Circulation reserve

| Parameter | Value | Constant |
|---|---|---|
| Reserve for corridors + stairwells | **15 %** of the floor outline | `FLOOR_RESERVE_RATIO` |

The user can lower this in the GUI (more apartments, tighter packing) or
raise it (looser plan).

---

## Stage 3 algorithm

Seven steps implemented in `core/floor_layout.py` + `core/floor_compute.py`:

1. **Apartment count:** `compute_apartment_count(area, mix, reserve)` →
   `{M1: n1, M2: n2, ...}`
2. **Stairwell count:** `compute_min_stairwells(polygon, h_floor, n_floors,
   max_walk)` → `{n_required, building_class}`
3. **Stairwell dimensions:** `compute_stairwell_dimensions(h_floor, n_floors)`
   → `{stairwell_w, stairwell_l, has_elevator, ...}`
4. **Stairwell positions** (heuristic — k-means clustering or evenly spaced)
5. **Voronoi → per-stairwell regions** (clipped to the floor polygon)
6. **Solver per region** (apartments + corridor segment, the legacy
   `solve_floor` extended with a corridor strip)
7. **Dijkstra validation** of the walking distance per apartment. If any
   distance exceeds the WT § 256 cap → add a stairwell and return to step 2.

## Worked examples (from `compute_stairwell_dimensions`)

| Floor h | Storeys | Total h | Class | n steps | h step | s step | Stairwell W × L | Lift | Core m² |
|---|---|---|---|---|---|---|---|---|---|
| 2.6 m | 4 | 10.4 m | N | 18 | 14.4 cm | 34.2 cm | 1.9 × 4.28 m | YES | ≈ 12.6 |
| 2.8 m | 4 | 11.2 m | N | 18 | 15.6 cm | 31.9 cm | 1.9 × 4.07 m | YES | ≈ 14.0 |
| 2.8 m | 3 |  8.4 m | N | 18 | 15.6 cm | 31.9 cm | 1.9 × 4.07 m | NO  | ≈  7.7 |
| 3.0 m | 5 | 15.0 m | SW | 20 | 15.0 cm | 33.0 cm | 1.9 × 4.50 m | YES | ≈ 16.6 |
| 3.2 m | 8 | 25.6 m | W  | 20 | 16.0 cm | 31.0 cm | 2.4 × 4.60 m | YES | ≈ 22.6 |
