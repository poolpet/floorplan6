# Design — Single-family 2-storey room generator + furniture (Stage 4, Phase 1)

> **Date:** 2026-05-29
> **Status:** design approved (brainstorm), pending implementation plan
> **Owner decisions:** two storeys; full Stage 2/3 later; automatic canonical furniture;
> Standard-PL program without integrated garage; only the staircase aligned vertically;
> solver approach A (reserve stair core + run the proven per-floor solver twice).

## 1. Goal & scope

Deliver the **core value** of the pivoted MVP (see memory `project_floorforge_mvp_direction`,
2026-05-29 pivot): **a simple rectangular footprint → a 2-storey single-family-house room
layout (parter + piętro) with furniture, rendered + PNG export.**

**Phase 1 is standalone-testable**: Stage 4 loads a footprint directly (as it does today for
apartments). It does NOT depend on the full pipeline. Wiring the smooth end-to-end flow
(Stage 1 → 2 → 3 → 4) and full Stage 2/3 is **Phase 2** (separate spec).

### In scope (Phase 1)
- New single-family house room templates (parter + piętro), reusing the existing template JSON schema.
- A `core/house_layout.py` orchestrator that reserves a staircase core and runs the existing
  `core/cpsat_solver.solve_cpsat` twice (once per storey) so the staircase aligns vertically.
- A small **additive** `reserved_core` parameter on `solve_cpsat` (no-op when `None` → apartment
  flows M1–M5 unchanged).
- Routing: `housing_type == JEDNORODZINNA` → house templates (NOT area-based M1–M5 selection).
- `core/furniture.py` — rule-based canonical furniture placement per room type.
- `viz/plan_renderer.py` extended to render two storeys + furniture + staircase symbol; PNG export.
- Stage 4 UI: a "single-family 2-storey" mode + furniture on/off toggle + two-floor display.

### Out of scope (deferred)
- Full Stage 2 (volume) and Stage 3 (floor) + smooth 1→2→3→4 wiring → **Phase 2**.
- Vertical alignment of wet stacks / load-bearing walls (only the staircase aligns).
- Per-type templates DETACHED/TWIN/TERRACED (one generic house program for Phase 1).
- Furniture editing/rotation; furniture export to ArchiCAD (PNG visualization only).
- PDF feasibility report (old MVP direction, deferred).

## 2. Data flow (Phase 1)

1. **Input:** one rectangular footprint (width × depth) + entry side + wall types — the existing
   Stage 4 input. Plus `housing_type = JEDNORODZINNA`, `num_storeys = 2`.
2. **Reserve staircase core:** choose a fixed rectangle (~2.5 × 3.0 m, U/L stair) heuristically
   near the entry, leaving room for surrounding rooms.
3. **Solve parter:** `solve_cpsat(footprint, house_parter_template, reserved_core=stair)` places the
   ground-floor program around the reserved core.
4. **Solve piętro:** `solve_cpsat(footprint, house_pietro_template, reserved_core=stair)` — **same**
   footprint, **same** reserved core → staircase aligned by construction.
5. **Furniture:** `place_furniture(rooms)` for every room on both storeys.
6. **Render:** two-panel plot (parter | piętro) with rooms, walls, inferred doors, furniture,
   staircase symbol; PNG export.

## 3. House templates (same JSON schema as M1–M5)

`templates/house_parter.json`:
- `hub` — *Hol + schody* (KOMUNIKACJA), no window. Contains the reserved staircase core.
- `wiatrolap` — entry vestibule (KOMUNIKACJA/USŁUGOWA), small, no window.
- `salon` — DZIENNA, window required, facade priority 1, large.
- `kuchnia` — DZIENNA, window, open to salon (connection `opening`).
- `spizarnia` — USŁUGOWA, small, no window.
- `wc` — USŁUGOWA, small. **Room id `wc` (not `lazienka`)** so the F2 5 m² bathroom cap does not
  apply; `wc` gets its own small max (~3 m²).
- `kotlownia` — USŁUGOWA / technical, no window.
- Adjacency: `wiatrolap↔_outside` (entry_door), `hub↔wiatrolap/salon/wc/kotlownia` (door),
  `salon↔kuchnia` (opening), `kuchnia↔spizarnia` (door).

`templates/house_pietro.json`:
- `hub` — *Hol/podest* (KOMUNIKACJA), no window. Contains the reserved staircase core (same position).
- `sypialnia_1`, `sypialnia_2`, `sypialnia_3` — NOCNA, windows required, facade priority.
- `lazienka` — USŁUGOWA, **F2 ≤ 5 m²**, window optional.
- `garderoba` — USŁUGOWA, small, no window.
- Adjacency: `hub↔` each bedroom + bathroom + garderoba (door).

Room field set per the existing schema: `id, nazwa, strefa, wymaga_okna, priorytet_fasady,
preferowana_orientacja, min_powierzchnia, opt_powierzchnia, min_szerokosc, max_proporcja,
procent_powierzchni`.

## 4. Staircase core mechanism

The CP-SAT solver is **continuous** (each room = rectangle `x, y, w, h` in cm; hub anchored at the
entry; non-overlap between rooms). Therefore:

- Pick a fixed staircase rectangle `(sx, sy, sw, sh)` near the entry (heuristic, see §6).
- Pass the **same** rectangle to both per-floor solves.
- Add a constraint: **the hub contains the staircase rectangle** (`hub.x ≤ sx`, `hub.x_end ≥ sx+sw`,
  `hub.y ≤ sy`, `hub.y_end ≥ sy+sh`). Because all other rooms must not overlap the hub, they
  automatically clear the staircase.
- Result: the staircase occupies the same `(x, y)` on both storeys — vertically aligned by construction.

`solve_cpsat` gains an optional `reserved_core: Optional[tuple[int,int,int,int]] = None`. When
`None`, behaviour is identical to today (apartment flows untouched → regression-tested).

## 5. Furniture (`core/furniture.py`)

**Available room metadata (verified):** `Room.polygon` (rectangle), room type (`spec.strefa` / id),
and which edges lie on the building facade (windows). **Door positions are NOT stored explicitly** —
they are inferred: an edge shared with an adjacent room (especially the hub) is treated as a likely
door location and avoided.

**`Furniture` dataclass:** `piece_type: str`, `polygon: Polygon` (placed), `room_id: str`, `label: str`.

**`FURNITURE_SETS` (canonical, PL dimensions in m):**
- `sypialnia`: bed 1.6×2.0, wardrobe 0.6×2.0, (nightstand 0.4×0.4 if it fits).
- `salon`: sofa 0.9×2.4, coffee table 0.6×1.1, TV unit 0.4×1.6.
- `kuchnia`: counter run 0.6×L along one wall (L = available wall length, capped).
- `lazienka`: bathtub/shower 0.8×1.7, washbasin 0.6×0.5, toilet 0.4×0.6.
- `wc`: toilet 0.4×0.6 + small basin 0.4×0.4.
- `garderoba`: shelving 0.4×L along walls.
- `kotlownia`: boiler/buffer block 0.6×0.8. `spizarnia`: shelves 0.4×L.
- `wiatrolap`, `hub` (hol/podest): no furniture (circulation).

**`place_furniture(rooms) -> list[Furniture]` rules (greedy, MVP):**
- Place each piece against a wall (inset ~0.1 m); the bed's headboard against a wall with no window
  and no inferred door.
- Avoid the door zone (centre of the edge shared with a neighbour, ~0.9 m + clearance).
- No collisions between pieces (Shapely intersection check); if a piece does not fit, skip it.
- Larger pieces placed first; try successive walls until one is collision-free.

**MVP limitations (accepted):** doors are approximate (from shared edges, not exact); no rotation
beyond axis alignment; no manual editing; no ArchiCAD export of furniture.

## 6. Components (new / changed)

| File | Change |
|---|---|
| `templates/house_parter.json` | NEW — ground-floor program (§3). |
| `templates/house_pietro.json` | NEW — upper-floor program (§3). |
| `core/cpsat_solver.py` | `solve_cpsat(..., reserved_core=None)` — additive hub-contains-core constraint; `None` = unchanged. |
| `core/house_layout.py` | NEW — `generate_house(footprint, entry, wall_types, num_storeys=2) -> TwoStoreyLayout`. Reserve stair core (heuristic: near entry, against a wall, sized ~2.5×3.0 m, biased so both programs fit around it), then `solve_cpsat` per storey. Returns per-storey room lists + the shared stair rectangle. |
| `core/furniture.py` | NEW — `Furniture`, `FURNITURE_SETS`, `place_furniture(rooms)`. |
| `viz/plan_renderer.py` | Render two storeys side by side + furniture rectangles/labels + staircase symbol; PNG export of the combined figure. |
| `ui/main_window.py` (Stage 4 tab) | "Single-family 2-storey" mode; furniture on/off toggle; two-floor display; route `JEDNORODZINNA` → house templates (not M1–M5). |

## 7. Success criteria

- On a house-sized rectangle (~10 × 8 m per storey): generates **parter + piętro** with the full
  program (all template rooms placed, no overlap, **100% coverage — F1**).
- **Staircase identical `(x, y)` on both storeys.**
- F2 (bathroom ≤ 5 m²), F4 (compact hub), F5 (rooms via hub), F6 (windowed rooms touch facade) hold.
- Each habitable room gets a sensible furniture set: in-bounds, no collisions, not blocking the
  inferred door. Two-panel render + PNG.
- A footprint too small for the program produces a clear failure (message / `None`), not a crash.

## 8. Tests (TDD: RED → GREEN → viz)

- `tests/test_house_layout.py`: parter + piętro generate on a rectangle; all template rooms present;
  F1 coverage; staircase rectangle identical on both storeys; F2 bathroom ≤ 5 m²; hub connects all
  rooms (F5); too-small footprint → clear failure, not a crash.
- `tests/test_furniture.py`: `sypialnia` → bed + wardrobe (inside room polygon, no collision);
  `salon` → sofa + table; `lazienka` → 3 fixtures; room too small → piece skipped; circulation rooms
  → no furniture.
- `tests/test_cpsat_solver.py`: **regression** — `reserved_core=None` leaves M1–M5 results unchanged.
- Smoke + viz PNG, reviewed by eye (B8).

## 9. Implementation order (additive; each step verified)

1. `reserved_core` parameter on `solve_cpsat` (additive, gated) + M1–M5 regression test.
2. `house_parter.json` + `house_pietro.json` + `JEDNORODZINNA` routing.
3. `core/house_layout.py` (reserve core → solve parter → solve piętro).
4. `core/furniture.py` + placement rules + tests.
5. `viz/plan_renderer.py` — two-storey + furniture render.
6. Stage 4 UI — 2-storey single-family mode + furniture toggle + two-floor display.
7. Smoke + viz.

Two failures of the same step → STOP / rewrite (B1).

## 10. Risks

- **Area-based template misclassification** (highest): the solver currently picks a template by area;
  a ~90 m² house floor would grab apartment template M4 (too dense). Mitigation: `housing_type`
  drives template choice, enforced before any area-based selection.
- **Footprint too small for the full program** → solver infeasible. Mitigation: clear failure
  message + minimum-footprint guidance (~7 × 9 m/storey); do not force a partial layout.
- **Inferred door positions imprecise** → furniture may occasionally sit near a real door.
  Accepted MVP limitation; exact doors are a future enhancement.
- **Stair-core position heuristic** may crowd a small footprint. Mitigation: bias the core toward a
  wall near the entry; if a per-floor solve is infeasible with the core, report it (do not silently
  drop rooms).
