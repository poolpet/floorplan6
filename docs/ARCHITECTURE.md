# ARCHITECTURE — FloorPlan6

> **Project goal:** ArchiCAD add-on for architects. End-to-end workflow from a
> plot to a finished apartment floor plan, in 4 stages.
>
> **Language:** Python 3.10+ (algorithm logic). After stabilisation — port to
> a C++ ArchiCAD add-on (FloorPlan4_CPP retained as UI/AC bridge reference).

---

## HIGH-LEVEL WORKFLOW (4 STAGES)

```
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 1: PLOT ANALYSER                                              │
│  Input:   plot from ArchiCAD (polygon) + MPZP zoning parameters      │
│  Output:  building zone, building footprint(s), sub-plots            │
│  Status:  ⏸️  ON HOLD (waiting for decisions Q1–Q5)                  │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 2: VOLUMETRIC GENERATOR                                       │
│  Input:   footprint + number of storeys + roof type                  │
│  Output:  3D mass model                                              │
│  Status:  ⏸️  NOT STARTED                                            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 3: FLOOR LAYOUT (split storey into apartments)                │
│  Input:   storey outline + apartment mix M1–M5 + staircase           │
│  Output:  apartment polygons + corridor + stairwells                 │
│  Status:  ✅ MVP (rectangular floors only — see floor_layout.py)     │
│           🟡 L/U-shape support TODO                                  │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 4: APARTMENT LAYOUTS  (per-apartment room layout)             │
│  Input:   apartment polygon + type M1–M5 + entry_point               │
│  Output:  room layout (rooms + doors + walls)                        │
│  Status:  ✅ STABLE (80/80 unit tests pass, 0 violations)            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  EXPORT TO ARCHICAD                                                  │
│  Tapir Add-On (port 19723) → CreateZones → Zones in AC               │
│  (Python Palette in AC = wrapper around Tapir, for end-users)        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## FOLDER STRUCTURE

```
FloorPlan6/
├── README.md                  ← landing page (EN)
├── CONTRIBUTING.md            ← how to contribute (EN)
├── LICENSE                    ← AGPL-3.0
├── CLAUDE.md                  ← Claude Code orientation (PL — author's notes)
├── MASTER_PROMPT_etap4.md     ← prompt for Stage 4 work session
├── requirements.txt
├── .gitignore
├── main.py                    ← CLI entry point
├── config.py                  ← global constants (WT, mixes, thresholds)
├── run_archicad.py            ← Tapir runner
│
├── core/                      ← algorithm logic
│   ├── models.py              ← dataclasses: Boundary, Room, FloorPlan, Template, Strefa
│   ├── boundary_analyzer.py   ← notch / facade / entry detection
│   ├── template_selector.py   ← template selection (constraint M1–M5)
│   ├── cpsat_solver.py        ← OR-Tools CP-SAT, scale=100, Coverage==
│   ├── trapezoid_handler.py   ← inscribed_rect + stretch + clip
│   ├── variant_generator.py   ← topology blocking for variant generation
│   ├── validator.py           ← post-clip validation (F1–F10)
│   ├── scorer.py              ← variant scoring
│   ├── floor_compute.py       ← Stage 3 helpers: stairwell dims, mix, building class
│   ├── floor_layout.py        ← Stage 3 deterministic floor layout
│   ├── floor_validation.py    ← Stage 3 walking-distance Dijkstra
│   └── floor_solver.py        ← Stage 3 single-stairwell legacy solver
│
├── bridge/                    ← ArchiCAD bridge
│   ├── tapir_connection.py    ← singleton ACConnection, port 19723
│   ├── boundary_reader.py     ← read outline from AC (Wall, Slab, Zone)
│   └── plan_writer.py         ← export plan as AC Zones
│
├── viz/
│   └── plan_renderer.py       ← matplotlib rendering (key for debugging)
│
├── ui/
│   ├── main_window.py         ← PyQt5 — main window, 4-tab layout
│   ├── floor_layout_window.py ← Stage 3 widget + standalone window
│   └── stage_placeholder.py   ← Stage 1 / Stage 2 placeholder tabs
│
├── tests/
│   ├── test_cpsat_solver.py   ← Stage 4 solver tests
│   ├── test_e2e.py            ← end-to-end Stage 4
│   ├── test_gui.py            ← GUI smoke test
│   └── test_regression_lazienka.py  ← F2 hard-cap regression
│
├── templates/                 ← constraint templates (WHAT must be there)
│   ├── M1_standard.json
│   ├── M2_standard.json
│   ├── M3_standard.json
│   ├── M3_wc.json
│   ├── M4_standard.json
│   ├── M4_2laz.json
│   └── M5_standard.json
│
├── data/                      ← reference dataset
│   ├── all_71_apartments.json ← 71 apartments (areas, no geometry)
│   ├── stats_cache.json
│   ├── dataset_loader.py
│   ├── dataset_stats.py
│   └── plans/                 ← 27 parameterised plans with adjacency graph ⭐
│       ├── PL_NL_01.json
│       ├── …
│       └── PL_TVR_25.json
│
├── docs/                      ← strategic documentation
│   ├── FUNDAMENTAL_RULES.md   ← F1–F10 + B1–B10 — SACRED
│   ├── LESSONS_LEARNED.md     ← 5 patterns + 6 mistakes
│   ├── ARCHITECTURE.md        ← this file
│   ├── TEMPLATES_GUIDE.md     ← 3 template sets — when to use which
│   ├── WT_PARAMETERS.md       ← WT 2002 parameters with paragraph references
│   ├── FLOOR_LAYOUT_DESIGN.md ← Stage 3 design rationale
│   ├── OPEN_QUESTIONS.md      ← Q1–Q11 architectural decisions
│   └── STATE.md               ← what works / what doesn't / what's on hold
│
├── notebooks/                 ← Jupyter / Python — algorithm iteration
│   ├── output/                ← rendered PNGs (gitignored)
│   ├── test_floor_layout.py
│   ├── test_floor_autosize.py
│   ├── test_floor_solver.py
│   └── viz_distribution_check.py
│
└── rzuty/                     ← (reserved for plans/templates from FP4)
```

---

## MODULES — I/O AND DEPENDENCIES (STAGE 4)

### `core/models.py`
**Contents:** dataclasses and enums.
- `Strefa` (DZIENNA, NOCNA, USLUGOWA, KOMUNIKACJA) — internal Polish enum
  with `.display` returning English (DAY, NIGHT, SERVICE, CIRCULATION)
- `RoomSpec` (id, name, zone, min_area, min_width, requires_window, …)
- `Template` (apartment_type, rooms: list[RoomSpec], adjacency: list[dict])
- `Boundary` (polygon, entry_point, bbox, area, facade_edges, notches)
- `Room` (spec, polygon, area, proportion)
- `FloorPlan` (boundary, template, rooms, score, hub_percent)

### `core/boundary_analyzer.py`
- **In:** Shapely `Polygon` + `entry_point: (x, y)`
- **Out:** `Boundary` with detected notches and facades
- **Function:** `analyze_boundary(polygon, entry_point) → Boundary`

### `core/template_selector.py`
- **In:** apartment type ("M2"/"M3"/...), `Boundary`
- **Out:** `list[Template]` — solver candidates
- `select_templates(mtype, boundary) → list[Template]`,
  `load_all_templates() → list[Template]`

### `core/cpsat_solver.py` ⭐ MOST IMPORTANT
- **In:** `Template` + `Boundary`
- **Out:** `CpsatResult(status, rooms: list[Room])`
- **Constraints:**
  - `Coverage equality` — `sum(areas) == usable_area` (P1)
  - Rooms inside `boundary.bbox`
  - Hub adjacency ≥ 90 cm
  - Window-required rooms touch the facade
  - Aspect ratio ≤ 2.5
  - `min_powierzchnia`, `min_szerokosc` per room
  - **MAX area (bathroom 5 m²)** — hard cap (F2)

### `core/trapezoid_handler.py`
- **In:** trapezoidal `Boundary`
- **Out:** `inscribed_rect` + stretch/clip helpers
- **Algorithm:** inscribe a rectangle → solve → stretch boundary rooms → clip to outline

### `core/variant_generator.py`
- **In:** `Template`, `Boundary`, `n_variants: int`
- **Out:** `list[FloorPlan]` with different layouts
- **Mechanism:** topology blocking — after each variant, block the quadrant
  where the living room was placed → next variant has a different layout

### `core/validator.py`
- **In:** `FloorPlan`
- **Out:** `ValidationResult(is_valid: bool, violations: list[str])`
- **Checks:** F1 coverage, F2 bathroom 5 m², F3 mins, F7 ratios, F10 max area
- **KEY:** assertions on MAX (not just MIN). If missing — add.

### `core/scorer.py`
- **In:** `FloorPlan`
- **Out:** `score: float`
- **Components:** deviation from `opt_powierzchnia`, facade, orientation,
  hub compactness

### `bridge/tapir_connection.py`
- AC connection singleton. Tapir commands:
  - `GetSelectedElements`
  - `GetDetailsOfElements`
  - `CreateZones`

### `bridge/boundary_reader.py`
- **In:** TapirConnection
- **Out:** Shapely `Polygon` from the selected element in AC

### `bridge/plan_writer.py`
- **In:** `FloorPlan` + offset
- **Out:** list of GUIDs of zones created in AC

---

## DATAFLOW WHEN GENERATING ONE FLOOR PLAN

```
USER in AC: selects apartment polygon, clicks "Generate M3"
   ↓
bridge/boundary_reader.py
   • TapirConnection.get_selected_elements()
   • → polygon: Shapely Polygon
   • → entry_point: (x, y)
   ↓
core/boundary_analyzer.analyze_boundary(polygon, entry_point)
   • detect notches (W4)
   • detect facades (F9)
   • → Boundary
   ↓
core/template_selector.select_templates("M3", boundary)
   • → [M3_standard, M3_wc] (2 candidates)
   ↓
core/variant_generator.generate(template, boundary, n=4)
   • for each template:
     • for each variant slot:
       • core/cpsat_solver.solve_cpsat(template, boundary)
         • Coverage equality (W1)
         • scale=100 (W2)
         • F1–F10 as constraints
       • core/validator.validate(plan)
         • F1, F2 (max!), F3, F7, F10
       • core/scorer.score(plan)
       • topology blocking (W3) → next iteration
   • → [FloorPlan, FloorPlan, FloorPlan, FloorPlan] sorted by score
   ↓
viz/plan_renderer.render_floor_plan(plans[0], save_path="preview.png")
   • matplotlib with zone legend + room centroids
   • → preview.png
   ↓
USER reviews preview, accepts
   ↓
bridge/plan_writer.export_plan_to_archicad(plans[0], offset)
   • TapirConnection.create_zones(zones_data)
   • → list[guid]
```

---

## ROLE OF FloorPlan4_CPP IN FloorPlan6

**FloorPlan4_CPP is NOT thrown away.** It remains as:

1. **UI/AC bridge reference** — palette of buttons, MPZP dialog (32720 GDLG),
   zone insertion patterns (BADPOLY fix). After Python stabilises → port the
   Python logic to C++ keeping the UI.
2. **Stage 3 Floor mode** — works, 6/6 tests. Can be run standalone.
3. **Stage 1 numerical MPZP analyser** — works, can be cited when
   re-implementing in Python.
4. **Negative example** — Plot Subdivider buggy (4 bugs), bathroom 13 m² —
   see `LESSONS_LEARNED.md`.

**Rule:** C++ code is READ-ONLY. If you must change logic — change it in
Python first, then port to C++.

---

## EXTERNAL DEPENDENCIES

| Package | Version | What for |
|---------|---------|----------|
| `or-tools` | ≥ 9.7 | CP-SAT solver |
| `shapely` | ≥ 2.0 | 2D geometry, intersection, buffer, clipping |
| `matplotlib` | ≥ 3.7 | floor-plan visualisation (debug + preview) |
| `pyqt5` | ≥ 5.15 | local GUI (test without AC) |
| `archicad` | (Graphisoft official pip) | AC communication |
| `networkx` | ≥ 3.0 | shortest-path validation (Stage 3) |
| `pytest` | ≥ 7.0 | tests |
| `numpy` | ≥ 1.24 | array math |

For algorithm iteration (Stage 1 plot subdivision):
| `jupyter` | any | notebook for iteration |

---

## SUMMARY ONE-LINER

**4 stages: plot → mass → floor → apartments → AC. FloorPlan6 starts with
Stage 4 (apartment layout, bathroom fix). Coverage==, scale=100, F1–F10
sacred. C++ as reference, port later.**
