# Stage-4 House: realistic, window-aware furniture (Phase 4)

**Status:** approved (brainstorm 2026-06-03, Dawid).
**Builds on:** existing `core/furniture.py` (greedy packer), S20 house layouts (single + two-storey,
przedsionek-entry, kotłownia/garderoba external), boundary facade detection in the solver.
**Expands:** the "Phase 4 — Realistic furniture" outline in `2026-06-02-stage4-open-plan-house-furniture-design.md`.

## Why
Dawid flagged the furniture as unrealistic (Session 16). The current engine
(`core/furniture.py:place_furniture`) is a GENERIC greedy packer: per-room `FURNITURE_SETS`, each piece
dropped into the first non-overlapping spot avoiding door zones. It has no notion of **windows** (beds can
land under a window, kitchen counters away from one), no **semantic arrangement** (sofa not facing a TV, no
nightstands beside the bed, no dining table), and no **Neufert clearances** (access room in front of
furniture). Phase 4 upgrades it to realistic, window-aware, semantically-arranged placement for the rooms
that make a plan read as real, keeping the proven primitives.

## Decisions (brainstorm 2026-06-03)
- **D1 — scope:** semantic placers for **bedroom + day-zone (kitchen/living/dining) + bathroom**; utility
  rooms (kotłownia/spiżarnia/garderoba) keep the generic greedy packer.
- **D2 — out of space:** **best-effort** placement (never fails the layout); when a KEY piece can't fit
  with clearance (bed in a bedroom, counter in a kitchen, bathtub+basin in a bathroom) emit a **warning**
  (room too small) — furniture doubles as a layout-quality validator.
- **D3 — arrangement rules (confirmed):**
  - **Bedroom:** bed headboard against the longest **window-less** wall + nightstands flanking it; wardrobe
    on another internal wall; ≥0.6 m clearance on accessible sides.
  - **Living (salon):** sofa against an internal wall (not under a window); TV on the wall **opposite** the
    sofa, preferably window-less (no glare); coffee table between, ~0.45 m gap.
  - **Kitchen:** linear counter + **sink under the window**.
  - **Dining:** table centred at the **kitchen↔living junction** (their shared edge); small day-zones skip it.
  - **Bathroom:** bathtub/shower + washbasin + WC linear along one installation wall; ≥0.6 m front clearance.
- **D4 — furniture is a post-layout layer:** it never changes room geometry and never makes the layout fail.

## Design

### Section 1 — Window / wall awareness
`place_furniture` gains a `boundary` argument. For each room, derive a per-wall flag set: which of the
room's 4 walls coincide with a **facade edge** of the boundary (= window / exterior) vs internal. Reuse the
solver's facade logic (`_detect_facade_sides` / edge geometry). A wall is "window" when it lies on the
boundary polygon AND that edge is a facade. `boundary=None` → all walls treated as internal → the engine
degrades to today's heuristics (existing `test_furniture` stays green).

Helper: `_room_window_walls(room, boundary) -> set[str]` returning a subset of `{"N","S","E","W"}`.

### Section 2 — Semantic placers (per room type)
A dispatch on room key chooses a semantic placer; unknown/utility keys fall back to the existing greedy
`_furnish_room`. Each semantic placer uses the window-wall flags + the existing `_place_fixed`/`_sweep`/
`_valid` primitives + clearance zones (Section 3):
- `_furnish_bedroom(room, windows, zones)` — bed on the longest window-less wall, headboard to wall;
  two nightstands flanking the bed (skip a side blocked by a door/too-narrow); wardrobe on another
  window-less wall.
- `_furnish_day_zone(rooms, windows, zones)` — operates on the salon + kuchnia pair (open-plan): counter
  along the kitchen's window wall with the sink segment under the window; sofa on an internal salon wall;
  TV opposite (window-less preferred); coffee table between; dining table at the salon↔kuchnia shared edge.
- `_furnish_bathroom(room, windows, zones)` — bathtub/shower + washbasin + WC linear along one wall
  (prefer an internal/installation wall).

### Section 3 — Neufert clearances
Each placed piece reserves a **clearance rectangle** (access strip) added to the keep-clear set the placer
respects (same mechanism as door zones in `_valid`): bed sides ≥0.6 m; in front of counter ≥1.2 m; in front
of WC/washbasin ≥0.6 m; sofa↔coffee-table gap ~0.45 m. Start values, tunable.

### Section 4 — Best-effort + warnings
Introduce `FurnishResult(furniture: list[Furniture], warnings: list[str])` and a primary
`furnish_rooms(rooms, boundary=None) -> FurnishResult`. Keep
`place_furniture(rooms, boundary=None) -> list[Furniture]` as a thin back-compat wrapper
(`furnish_rooms(...).furniture`) so existing callers/tests are unchanged. A KEY piece (bed / kitchen_counter
/ bathtub / washbasin) that fails to place appends a warning like `"sypialnia_2 (8.1 m²): brak miejsca na
łóżko + dojście"`. Never raises.

### Section 5 — Renderer + testing
`viz/plan_renderer._draw_furniture` already draws furniture; extend it for the new piece types/labels.
Tests (`tests/test_furniture.py` extended + new cases):
- **Window-aware:** bed's headboard wall is window-less; kitchen counter touches the window wall.
- **Semantic:** sofa and TV on opposite walls; nightstands adjacent to the bed; dining table near the
  salon↔kuchnia shared edge.
- **Clearance:** no furniture overlaps a clearance zone or a door zone.
- **Best-effort + warning:** an oversmall bedroom yields no bed + a warning, not a crash.
- **Back-compat:** `place_furniture(rooms)` (no boundary) returns the same shape as today; the existing
  `test_furniture` assertions stay green.
- **Visual:** render a furnished single-storey + two-storey house (control render).

## Risk
- **Open-plan day-zone** (salon + kuchnia as two polygons) — the window wall belongs to whichever polygon
  touches the facade; the dining "junction" is their shared edge. Needs both room polygons + their shared
  edge; if they don't share a clean edge (L-shapes), degrade to placing the table on the salon side near
  the kitchen.
- Window detection on **notched** footprints is deferred (gate on `boundary.notch is None`, like the solver
  rules); rectangles only for v1.

## Deferred (not in scope)
- Utility-room semantic placement (kotłownia/spiżarnia/garderoba stay generic).
- Notched/L/U/trapezoid footprints.
- Furniture feeding back into room sizing (D4: post-layout only).
- ArchiCAD export of furniture.

## Open — needs Dawid before touching
- None blocking. Clearance numbers (0.6 / 1.2 / 0.45 m) are Neufert-grounded start values, tunable.
