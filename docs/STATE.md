# STATE — current state of FloorPlan6

> Updated after every working session. If it doesn't reflect reality —
> Claude updates immediately.
>
> **Last update:** 2026-05-07 (Stage 1 Sessions 1–6 — Mode A + Mode B logic + UI tab in `ui/main_window.py`)
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

### Stage 1 — Phase 1 (Pack Architecture) — COMPLETED 2026-05-11

| Component | Status |
|---|---|
| `rules/_loader.py` | ✅ `load_pack()` + `get_default_pack()` (memoized) |
| `rules/_schema.py` | ✅ Pydantic schemas (PackManifest, PackConstants) |
| `rules/PL/pack.yaml` | ✅ PL pack manifest (v1.0) |
| `rules/PL/constants.yaml` | ✅ All rule-driven constants extracted from config.py |
| `rules/PL/wt_rules.json` | ✅ 19 WT 2002 rules (moved from rules/) |
| `rules/PL/user_rules.json` | ✅ User MPZP overrides template (moved) |
| `rules/README.md` | ✅ "How to add a country pack" |
| `tests/test_pack_loader.py` | ✅ 12 tests pass |
| `tests/test_pack_constants.py` | ✅ 14 tests pass |
| `core/cpsat_solver.py`, `validator.py`, `scorer.py`, `site_planner.py`, `plot_indicators.py`, `floor_compute.py`, `floor_layout.py` | ✅ All load constants from pack |
| `config.py` | ✅ Reduced to 12 lines (SCALE only — Python-runtime, not rule-driven) |

**Tests:** 172 passed (up from 144 baseline). Behavior change: none — pure refactor.
**Next:** Phase 2 — Report Layer (PDF generation).

---

## What's next

1. **Integration Stage 3 → Stage 4** — clicking an apartment in Stage 3 layout
   → opens its outline in Stage 4 tab for room-level detailing
2. **Walls + doors export to AC** — currently zones only; add real walls and
   door elements (B1+B2 from earlier backlog)
3. **L-shape floors** — `floor_layout` currently assumes rectangular floor
4. **Stage 1 (plot analyser)** — Mode A foundation imported. Q1–Q18
   decided 2026-05-07. **Session 1 done** (data model + buildable zone +
   indicators + 18 regression tests + L-shape/triangle viz). Next:
   Session 2 — port `verifier.py` to `core/plot_verifier.py` with Q13/Q17
   gating and Q14 5% band; Session 3 — port `optimizer.py` to
   `core/site_planner.py` with multi-family adapter; Sessions 4–5 — Mode B
   parcelacja prototype in `notebooks/` then port to `core/`.

   **Stage 1 Session 1 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/plot_model.py` | ✅ `Plot`, `PlotBoundary`, `BoundaryType`, `MPZPParameters`, `HousingType` (Q12, Q13, Q15, Q17 fields) |
   | `core/site_element_model.py` | ✅ `SiteElement`, `SiteElementType` |
   | `core/buildable_zone.py` | ✅ `BuildableZoneBuilder` (setback buffers via Shapely) |
   | `core/plot_indicators.py` | ✅ `PlotIndicatorCalculator`, `PlotIndicators` (WZ/WIZ/PBC) |
   | `rules/wt_rules.json` | ✅ 19 WT 2002 rules with paragraph references |
   | `rules/user_rules.json` | ✅ empty MPZP override template |
   | `tests/test_buildable_zone.py` | ✅ 18/18 pass (rectangle, L-shape, triangle, edge cases) |
   | `notebooks/stage1_buildable_zone.py` | ✅ matplotlib viz for rectangle + L-shape + triangle |

   **Stage 1 Session 2 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/site_wall_model.py` | ✅ `SiteWall`, `WallOpeningType`, `WallOpening` |
   | `core/plot_verifier.py` | ✅ `PlotVerifier`, `VerificationResult`, `VerificationStatus`. 5 categories with Q13/Q17 gating + Q14 5% band + `strict` flag |
   | `tests/test_plot_verifier.py` | ✅ 14/14 pass (indicators band, Q13/Q17 gating, walls, parking, conditional warnings, sort order) |

   **Stage 1 Session 3 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/site_planner.py` | ✅ `SitePlanner`, `BuildupVariant`. Mode 1 propose_max_buildup (3 variants) + Mode 2 place_building. Q13+Q17 gating. Multi-family parking row scaling. Inscribed-rect bug fix (source iterated min, fixed to max). |
   | `core/plot_model.py` | ✅ helper methods `road_boundary()`, `undeveloped_neighbour_boundaries()`, `bbox_dimensions`, `perimeter` |
   | `core/site_element_model.py` | ✅ `units: int` field added (multi-family parking scaling) |
   | `core/plot_indicators.py` | ✅ `_required_parking` now scales with `Σ building.units × MPZP coefficient` |
   | `tests/test_site_planner.py` | ✅ 12/12 pass (variants, gating, multi-family parking row, inscribe-rect fix) |
   | `notebooks/stage1_site_planner.py` | ✅ Mode A viz: rural / municipal / wielorodzinna side-by-side |

   **Stage 1 totals after Session 3:**

   - **44 tests** green (18 buildable_zone + 14 verifier + 12 site_planner)
   - Mode A logic complete end-to-end (read plot → zone → indicators → verify → propose buildup)
   - Missing: AC bridge wire-up, UI tab, Mode B parcelacja

   **Stage 1 Session 4 components (2026-05-07) — Mode B prototype, Jupyter only:**

   | Component | Status |
   |---|---|
   | `notebooks/stage1_subdivision_v1.py` | ✅ first iteration — exposed architectural error: setbacks were carved from parent, ~27% nieużytek |
   | `notebooks/stage1_subdivision_v2.py` | ✅ corrected — sub-plots tile entire parent; setbacks are per-sub-plot building constraints |
   | viz `stage1_subdivision_v2.png` | ✅ rectangle 60×80, L-shape, long narrow 30×100 — Q16 diff=0 in all cases |

   **Mode B prototype validates implemented decisions:**

   - Q1(a) clip — L-shape sub-plots clipped, notch becomes explicit nieużytek
   - Q5(c) orientation search — long-narrow 30×100 picks axis-aligned (2 valid sub-plots) over rotated (5 with road-access failure)
   - Q15 min_front — sub-plots ≥18m front enforced
   - Q16(a) strict coverage — `Σ sub + roads + nieużytek == parent` exactly (diff=0)
   - Per-sub-plot buildable zone — each sub-plot has its own non-empty zone (anti-bug-#3 from C++ Plot Subdivider)

   **Mode B prototype gaps (status after Session 5):**

   - Q1.1(c) push-neighbour mechanism — **deferred**, currently Q1.1(d) drop-to-nieużytek (within-spec since "no sub-plot below minimum" constraint is satisfied)
   - Q3(c) front-to-road enforcement for terraced/twin — ✅ **closed in Session 5**
   - Q4(a) twin-house pairs — confirmed concern lives at Stage 2/4, not subdivision (1 sub-plot = 1 segment per Q4(a) decision); **closed** by no-op
   - Variable column widths / row depths — deferred (current uniform tiling works for tested cases)
   - **Regression tests for 4 C++ Plot Subdivider bugs** — ✅ **closed in Session 5**

   **Stage 1 Session 5 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/plot_subdivider.py` | ✅ port from `notebooks/stage1_subdivision_v2.py` + Q3(c) enforcement + Q12 single-family validation |
   | `tests/test_plot_subdivider.py` | ✅ 17/17 pass: anti-bug regressions (#1/#2/#3/#4), Q12, Q15, Q16(a), Q3(c) terraced/twin/detached, Q5(c) orientation search |

   **Stage 1 totals after Session 5:**

   - **61 tests** green (18 buildable_zone + 14 verifier + 12 site_planner + 17 plot_subdivider)
   - **Mode A end-to-end logic:** ✅ complete
   - **Mode B end-to-end logic:** ✅ complete (with Q1.1(d) fallback for too-small clipped cells)
   - **Outstanding for full Stage 1 product:** AC bridge wire-up + UI tab + Q1.1(c) full push (deferred)

   **Stage 1 Session 6 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `bridge/plot_reader.py` | ✅ `read_plot_from_archicad()` + `wrap_polygon_as_plot()`; default-classifies bottom edge as DROGA, others as SASIAD_NIEZABUDOWANY |
   | `ui/stage1_window.py` | ✅ `Stage1Widget` + `Stage1Window`. Q12 enforcement (Mode B disabled for wielorodzinna). Mode A pipeline: site_planner.propose_max_buildup → indicators → verifier → render. Mode B pipeline: subdivide_with_orientation_search → render. |
   | `ui/main_window.py` | ✅ Stage 1 tab now `Stage1Widget` (was `Stage1PlotPlaceholder`) |

   **Stage 1 totals after Session 6:**

   - **61 tests** still green (no new tests in Session 6 — UI smoke test only)
   - **End-to-end usable from GUI:** ✅
   - **Outstanding:** AC zone export of sub-plots + Q1.1(c) push (deferred), edge-by-edge boundary classifier (defer)

   **Stage 1 Session 7 components (2026-05-10) — road-tree repair after AC tests:**

   | Component | Status |
   |---|---|
   | `core/subdivision_roads.py` | ✅ new active road-tree generator: one public-DROGA trunk + shortened branches; branches stop before non-DROGA parcel boundaries |
   | `core/plot_subdivider.py` | ✅ production flow now calls `generate_road_tree_layout()`; old OBB/pattern/katana helpers remain legacy-only and are not on active path |
   | `tests/test_plot_subdivider.py` | ✅ 19/19 pass; added urban regressions for dead-end roads and redundant road frontage |
   | `ui/stage1_window.py` | ✅ Mode B summary now shows buildable-zone %, road %, nieużytek %, and plots without road access |

   **Stage 1 verification after Session 7:**

   - `tests/test_plot_subdivider.py`: ✅ 19 passed
   - Stage 1 subset (`plot_subdivider`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 63 passed
   - Full non-GUI suite: ✅ 136 passed, 29 skipped, 1 xpassed
   - Full `pytest tests/`: ⚠️ aborts during `tests/test_gui.py` collection in headless PyQt import; verify GUI manually.

   **Known Stage 1 gaps still open:**

   - `core/plot_subdivider.py` still contains legacy experimental algorithms; active path is clean, but dead code should be moved to `notebooks/archive/`.
   - Road-tree is now structurally closer to the owner rule, but still needs visual AC validation on real selected plots before calling it product-ready.
   - Future model split: active frontage vs physical road-adjacent boundary, so corner/front-row plots are not over-penalized by setbacks.

   **Stage 1 Session 8 components (2026-05-10) — variant architecture MVP:**

   | Component | Status |
   |---|---|
   | `core/plot_variant_generator.py` | ✅ new Stage 4 style orchestration: generate subdivision candidates, validate, score, deduplicate, sort best-first |
   | `core/plot_subdivision_validator.py` | ✅ hard checks for no sub-plots, Q16 coverage, no nieużytek, road access, min/max sub-plot area, buildable zone |
   | `core/plot_subdivision_scorer.py` | ✅ weighted score breakdown: buildable area, road efficiency, waste control, road access, area fit, regularity |
   | `core/subdivision_roads.py` | ✅ `RoadTreeSettings` added so road-tree can be searched via deterministic strategies (`balanced`, `minimal`, left/right trunk, direct-bias) |
   | `core/plot_subdivider.py` | ✅ public `subdivide()` now preserves old API but returns the best scored variant |
   | `tests/test_plot_variant_generator.py` | ✅ RED→GREEN tests for scored sorted variants, multiple road strategies, and public API best-variant return |

   **Stage 1 verification after Session 8:**

   - `tests/test_plot_subdivider.py` + `tests/test_plot_variant_generator.py`: ✅ 27 passed
   - Stage 1 subset (`plot_subdivider`, `plot_variant_generator`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 71 passed
   - Full non-GUI suite (`pytest tests --ignore=tests/test_gui.py`): ✅ 143 passed, 30 skipped, 1 xpassed
   - Known test noise: Shapely `oriented_envelope` warnings remain; no failing assertions.

   **Stage 1 Session 9 components (2026-05-10) — tight 600/800 lots repair:**

   | Component | Status |
   |---|---|
   | `tests/test_plot_subdivider.py` | ✅ regression for wide top-road plot with `min_area=600`, `max_area=800`: no monster side/tail parcels, no tiny buildable zones |
   | `core/plot_subdivider.py` | ✅ oversized post-absorption plots are locally re-split; tight-area cases can add local access spurs when a side strip cannot be legally subdivided otherwise |
   | `core/plot_variant_generator.py` | ✅ tight-area strategy order so `subdivide()` finds a valid variant quickly |
   | `core/subdivision_roads.py` | ✅ tight-lot strategies may reduce branch edge clearance; normal strategies keep the previous safe clearance from non-road boundaries |

   **Stage 1 verification after Session 9:**

   - `tests/test_plot_subdivider.py` + `tests/test_plot_variant_generator.py`: ✅ 28 passed
   - Stage 1 subset (`plot_subdivider`, `plot_variant_generator`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 72 passed
   - Reproduced tight top-road case: `road_tree_left_trunk`, 83 sub-plots, max parcel 797.1 m², min buildable zone 157.4 m², road 8.0%, waste 0.0%, validation errors 0.
5. **Stage 2 (volumetric generator)** — not started

---

## Operational notes

- Building rules (F1-F10) and workflow rules (B1-B10) in
  `docs/FUNDAMENTAL_RULES.md` are inviolable.
- Past lessons in `docs/LESSONS_LEARNED.md`.
- Architecture overview in `docs/ARCHITECTURE.md`.
- WT parameters table in `docs/WT_PARAMETERS.md`.
- Open architectural questions in `docs/OPEN_QUESTIONS.md`.
- After every session: update this file (WHAT WORKS / WHAT DOESN'T / METRICS).

---

# Historical (Polish) — sessions 1-7, kept for traceability

(Sessions before 2026-05-05 logged in Polish. Removed from this file for
brevity; see git history for full timeline.)
