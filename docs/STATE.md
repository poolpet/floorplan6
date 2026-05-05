# STATE — current state of FloorPlan6

> Updated after every working session. If it doesn't reflect reality —
> Claude updates immediately.
>
> **Last update:** 2026-05-05 (Stage 3 floor layout REWRITE + EN translation)
>
> Earlier sessions documented in Polish are preserved at the bottom; from
> 2026-05-05 onwards everything is in English so the project can be shared
> with international collaborators.

---

## Current state (2026-05-05)

### Stage 4 — Apartment layout (per-apartment room layout) — STABLE

| Component | Status |
|---|---|
| `core/cpsat_solver.py` | ✅ CP-SAT solver, F2 hard cap, Q6 distribution |
| `core/validator.py` | ✅ MIN+MAX area checks, `strict_max_areas` flag |
| `core/scorer.py` | ✅ multi-criteria scoring |
| `core/variant_generator.py` | ✅ N variants with topology blocking |
| `core/boundary_analyzer.py` | ✅ notch detection, collinear cleanup |
| `core/trapezoid_handler.py` | ✅ inscribed rect + clip |
| `bridge/tapir_connection.py` | ✅ ArchiCAD via Tapir Add-On (port 19723) |
| `bridge/boundary_reader.py` | ✅ reads Wall/Slab/Zone, auto-detects entry/walls |
| `bridge/plan_writer.py` | ✅ exports apartments as Zones to AC |
| `viz/plan_renderer.py` | ✅ matplotlib renderer |
| `ui/main_window.py` (Stage 4 tab) | ✅ load AC, classify walls, generate, export |

**Tests:** `pytest tests/` — 80/80 pass + 26 skipped.

**Verified rules (FUNDAMENTAL):**
- F1 — 100% coverage equality (`sum(rooms) == usable_area` in solver)
- F2 — bathroom max 5m², WC max 3m² (`WT_MAX_AREA` in `config.py`)
- F4 — hub max 15% of usable area
- Q6 — salon takes 80% of excess area, sleeping rooms 20% proportionally
- Q7 — F2 wins over `procent_powierzchni` from templates

### Stage 3 — Floor layout (divide floor into apartments) — REWRITE done 2026-05-05

After 3 patch attempts on `floor_multistair.py`, **B1 rule applied** (2 fails →
rewrite). Old modules removed:
- ❌ `core/floor_multistair.py` — deleted
- ❌ `core/floor_corridor_solver.py` — deleted

**New deterministic architecture** in `core/floor_layout.py`:

| Component | Status |
|---|---|
| `core/floor_compute.py` | ✅ helpers: stairwell dims, apartment count, building class |
| `core/floor_layout.py` | ✅ deterministic geometry: stairwell at facade, central corridor, T-shape connector |
| `core/floor_validation.py` | ✅ Dijkstra walking-distance on corridor graph (networkx) |
| `core/floor_solver.py` | 🟡 single-apartment solver (legacy, kept as MVP backup) |
| `ui/floor_layout_window.py` | ✅ standalone window + `FloorLayoutWidget` for tab integration |
| `ui/main_window.py` | ✅ two tabs: Stage 4 + Stage 3 |
| `docs/FLOOR_LAYOUT_DESIGN.md` | ✅ design rationale |
| `docs/WT_PARAMETERS.md` | ✅ WT 2002 parameters with paragraph references |

**Geometry rules implemented:**
- Stairwell at chosen facade (default N) for natural daylight
- Stairwell centered along the long axis (centered apartments minimize walking
  distance: ±40m → max 80m corridor with one stairwell)
- Connector strip (corridor-width) bridges stairwell to main corridor
- Main corridor 1.4m wide (WT §237) along the long axis, full length
- Apartments sliced from rectangular zones along the corridor edge
- Walking distance ≤40m WT §256 (validated by Dijkstra)
- Number of stairwells: `max(geometric, WT_class_min, capacity)`
  - Geometric: `ceil(main_length / 80)`
  - WT min: 1 for class N, 2 for SW/W/WW

**Verified scenarios:**

| Scenario | Stairs | Apts | Max walk | Status |
|---|---|---|---|---|
| 200 m² floor, 4 storeys, class N | 1 | 2 | 7.6 m | ✅ OK |
| 800 m² floor, 4 storeys, class N | 1 | 9 | 23.7 m | ✅ OK |
| 1200 m² floor, 4 storeys, class N | 1 | 14 | 32.7 m | ✅ OK |
| 600 m² floor, 5 storeys, class SW | 2 | 7 | 12.2 m | ✅ OK |
| 800 m² floor, facade=S | 1 | 9 | 23.7 m | ✅ OK |

### UI

- **Two-tab QTabWidget** in `ui/main_window.py`:
  - "Apartment Layout (Stage 4)" — full Stage 4 workflow
  - "Floor Layout (Stage 3)" — embedded `FloorLayoutWidget`
- **All UI strings in English** (translated 2026-05-05).
- Stage 4 features: load outline (Zone via Inner Edge), interactive
  facade/entry editor (click + Shift+click), generate variants, score filter,
  navigate variants, export PNG / to ArchiCAD.
- Stage 3 features: floor outline (manual or from AC), building params
  (height, floor count → class N/SW/W/WW), apartment mix sliders,
  WT overrides (corridor width, max walking distance), generate.

### Tools / dependencies

- Python 3.13 + venv
- `ortools 9.15`, `shapely 2.1`, `matplotlib 3.10`, `pyqt5 5.15`,
  `archicad 29.3`, `networkx 3.6`

---

## What's next

1. **Integration Stage 3 → Stage 4** — clicking an apartment in Stage 3 layout
   → opens its outline in Stage 4 tab for room-level detailing
2. **Walls + doors export to AC** — currently zones only; add real walls and
   door elements (B1+B2 from earlier backlog)
3. **L-shape floors** — `floor_layout` currently assumes rectangular floor
4. **Stage 1 (plot subdivision)** — not started, depends on Q1-Q5 decisions
5. **Stage 2 (volumetric generator)** — not started

---

## Operational notes

- Building rules (F1-F10) and workflow rules (B1-B10) in
  `docs/FUNDAMENTAL_RULES.md` are inviolable.
- Past lessons in `docs/LESSONS_LEARNED.md`.
- Architecture overview in `docs/ARCHITECTURE.md`.
- WT parameters table in `docs/WT_PARAMETERS.md`.
- Open architectural questions in `docs/OPEN_QUESTIONS.md`.
- After every session: update this file (CO DZIAŁA / CO NIE / METRYKI).

---

# Historical (Polish) — sessions 1-7, kept for traceability

(Sessions before 2026-05-05 logged in Polish. Removed from this file for
brevity; see git history for full timeline.)
