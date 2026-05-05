# Floor Layout Module — Design (REWRITE 2026-05-05)

> Replaces `core/floor_multistair.py` and `core/floor_corridor_solver.py`.
> Reason: 3 patch attempts on those modules, B1 rule (2 fails → rewrite).

## Goal

Divide a building floor into apartments + stairwells + corridors that satisfy
Polish Building Code (WT 2002, amended 2024-08-01). Output is a deterministic
floor layout suitable for input to Stage 4 (per-apartment room layout).

## Strategy: deterministic geometry (NOT CP-SAT for layout positions)

Earlier attempts used CP-SAT to position EVERYTHING (stairwells, corridor,
apartments). This produced unpredictable layouts and hard-to-debug edge cases
(e.g. "no access" false positives, M5 in too-narrow strips).

**New approach**: positions of stairwell + connector + corridor are computed
**deterministically** by direct geometry. CP-SAT (or simple grid splitting) is
used ONLY to distribute apartments inside pre-cut zones.

## Inputs

| Field | Type | Default | Source |
|---|---|---|---|
| `floor_polygon` | Polygon | — | from Tapir/AC |
| `floor_height_m` | float | 2.8 | UI |
| `num_floors` | int | 4 | UI |
| `mix_pct` | dict[str, float] | `APARTMENT_MIX_DEFAULT` | UI |
| `stairwell_facade` | "N"/"S"/"E"/"W" | "N" | UI |
| `corridor_width_m` | float | 1.4 (WT §237) | UI |
| `max_dojscie_m` | float | 40.0 (WT §256, 2-stair) | UI |
| `reserve_ratio` | float | 0.15 | UI |

## Geometry pipeline (deterministic)

```
1. Compute stairwell dims:
   stairwell_dims = compute_stairwell_dimensions(h, n_floors)
   → sw_w, sw_l, has_elevator, building_class

2. Detect main axis (longer side):
   main_axis = "horizontal" if width >= height else "vertical"

3. Compute number of stairwells:
   n_stairs = max(WT_min_for_class, ceil(main_axis_length / 80))
   (1 stairwell at center covers ±40m of corridor = 80m total)

4. Place stairwells centered along main axis, at chosen facade
   (depth ≤ floor_depth / 2 — fits in "first half" of building depth)

5. Place corridor centered along the shorter axis
   (full length along main axis)

6. Place connectors: vertical strips (corridor_width wide) from each
   stairwell to the main corridor, centered on the stairwell

7. Carve residential zones from floor_polygon:
   floor_polygon - stairwells - connectors - corridor = N rectangular zones
   - Zone A: opposite side of corridor from stairwells (full main_axis length)
   - Zones B_i: same side as stairwells, between/around stairwells
```

## Apartment distribution

```
For each zone:
  zone_area / floor_area * total_apartments → number of apartments in zone
  weight by zone shape: long thin zones get small apartments first

For each zone, divide along corridor edge into apartment slots:
  - Slot width = zone_length / n_apartments_in_zone
  - Each apartment = full_zone_depth × slot_width
  - Adjacency to corridor automatic (each slot touches corridor edge)

Validate per apartment:
  - area >= APARTMENT_MIN_AREA[type]
  - aspect_ratio <= APARTMENT_MAX_ASPECT (3.0)
  - has corridor adjacency >= DOOR_MIN_WIDTH (0.9m)
  - if violated → either swap with neighbor or report INFEASIBLE
```

## Walking distance validation (Dijkstra)

```
Build graph:
  Nodes:
    - corridor "rail" (sample every 1m along corridor centerline)
    - stairwell entry points (where stairwell touches corridor or connector)
    - apartment door points (mid of apartment-corridor shared edge)
  Edges:
    - rail-rail: 1m apart (sequential)
    - apt_door → nearest rail node: euclidean
    - stairwell → nearest rail node: euclidean

For each apartment:
  d = nx.shortest_path_length(G, apt_door, nearest_stair_door)
  if d > max_dojscie_m → violation
```

## Outputs

```python
@dataclass
class FloorLayoutResult:
    status: str  # "OK", "INFEASIBLE", "VIOLATIONS"
    apartments: list[Apartment]
    stairwells: list[Polygon]
    connectors: list[Polygon]
    corridor: Polygon
    walking_distances_m: list[float]  # one per apartment
    violations: list[str]  # WT non-compliances
    building_class: str
    has_elevator: bool
    solve_time_s: float
```

## Module split

- `core/floor_layout.py` — main entry `solve_floor_layout()` + geometry helpers
- `core/floor_validation.py` — Dijkstra walking distance + WT checks
- (delete: `core/floor_multistair.py`, `core/floor_corridor_solver.py`)

## Test scenarios

Reuse from earlier work, plus add stairwell_facade variants:
- 200m² 4-floor, facade="N"
- 800m² 4-floor, facade="N"
- 1200m² 4-floor, facade="N" (Dawid's screenshot reference)
- 600m² 5-floor SW, facade="N" (2 stairwells required by WT)
- 800m² 4-floor, facade="S" (mirror test)
