# STATE — current state of FloorPlan6

> Updated after every working session. If it doesn't reflect reality —
> Claude updates immediately.
>
> **Last update:** 2026-05-27 (Q21 visual sanity check on 265×202 + 60×80 — PASS; notebooks/stage1_q21_sanity.py added)
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

### Stage 1 — Phase 2 (Report Layer) — COMPLETED 2026-05-11

| Component | Status |
|---|---|
| `core/report_data.py` | ✅ ReportData + nested dataclasses + estimate_units + compute_hash + GLOSSARY |
| `core/report_renderer.py` | ✅ 3 matplotlib figures: plot_zone, indicators_bar, variants_grid |
| `core/report_pdf.py` | ✅ 9-page reportlab assembly + CLI (`python -m core.report_pdf`) + logo support + Polish font (Arial Unicode on macOS) |
| `tests/fixtures/sample_report.py` | ✅ Reusable test fixture + sample logo generator |
| `tests/test_report_data.py` | ✅ 13 tests pass |
| `tests/test_report_renderer.py` | ✅ 6 tests pass |
| `tests/test_report_pdf.py` | ✅ 8 tests pass (incl. logo + CLI) |
| `requirements.txt` | ✅ pypdf>=4.0 added |
| momepy evaluation | ✅ NO-GO documented in notebooks/momepy_eval.py |

**Tests:** 196 passed (172 Phase 1 baseline + 27 new Phase 2 tests; 31 skipped, 1 xpassed).
**Deliverable:** `python -m core.report_pdf --fixture sample --out X.pdf` produces 9-page ~165KB PDF.
**Known issue:** macOS-only Polish font (Arial Unicode TTF path). Cross-platform handling deferred to Phase 3.

---

### Stage 1 — Phase 3 (UI Integration) — COMPLETED 2026-05-24 (commit 9017bae)

UI wire-up Phase 2 PDF backend → Stage 1 Mode A pipeline. Shipped end-to-end:
"Mode A → Generate → Eksport PDF → 9-page report".

| Component | Status |
|---|---|
| `core/report_builder.py` | ✅ `build_report_data(plot, variants, indicators, verification, *, plot_id, plot_address, logo_path=None) → ReportData`. Q14 5% warning band (MAX-constrained WZ/WIZ, MIN-constrained PBC). VariantInfo detailed metrics (PUM, headroom, parking, height). Polish chars preserved. `data_hash` stable across runs, sensitive to plot_id changes. Empty variants → `ValueError`. |
| `ui/report_metadata_dialog.py` | ✅ `ReportMetadataDialog(QDialog)` collects `plot_id` / `plot_address` / `logo_path`. `QSettings("FloorPlan6", "Stage1Report")` persists last-used logo across sessions. |
| `ui/stage1_window.py` (Stage1Widget) | ✅ `export_pdf_btn` (disabled by default, enabled after Mode A success). `_mode_a_results` cache: `(plot, variants, indicators, verification)`. `_on_export_pdf` handler: metadata dialog → `build_report_data` → `QFileDialog` (prefilled `Raport_<plot_id>_<YYYY-MM-DD>.pdf`) → `generate_pdf`, sync with `Qt.WaitCursor` + `processEvents`. Cache invalidation in `_run_mode_b` (Mode B uses different pipeline). |
| `tests/conftest.py` | ✅ session-scoped `qapp` (manual, no `pytest-qt`); `isolated_qsettings` (IniFormat + `setPath` on `tmp_path` + clear/sync between tests); `make_minimal_plot` (40×30 m rectangle with buildable zone). |
| `tests/test_report_builder.py` | ✅ 14 tests pass (covers status mapping, Q14 band, hash stability, empty-variants ValueError) |
| `tests/test_report_metadata_dialog.py` | ✅ 5 tests pass (cancel returns None on Rejected, QSettings round-trip, Polish chars) |

**Subsequent enhancement (2026-05-?, commit `f7c923c`):**
report_builder + stage1_window extended for depth-aware building dimensions
and Mode B building proposals; not a regression of Phase 3 — same Eksport PDF
flow, richer VariantInfo metrics.

**Spec / plan (kept for history):**
- `docs/superpowers/specs/2026-05-13-stage1-phase3-ui-integration-design.md`
- `docs/superpowers/plans/2026-05-14-stage1-phase3-ui-integration.md` (19 tasks executed)

**Pytest (2026-05-27):** 19 Phase 3 tests pass; full non-GUI suite 287 pass / 31 skip / 1 xpass (Session 10 baseline).

**Outstanding from original spec (deferred phases):**
- Phase 3.1 — multi-persona views (architect / inwestor / klient końcowy).
- Phase 3.2 — macOS-only Polish font (Arial Unicode) → cross-platform handling.
- Phase 4 — Mode B report (currently `export_pdf_btn` is Mode A only; cache is invalidated on Mode B run).

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

   **Stage 1 Session 10 components (2026-05-25 → 2026-05-26) — segment-aware sub-plots:**

   Driven by Dawid's AC test on a 265×202 m plot where TWIN/TERRACED collapsed
   to 4 monster sub-plots (Q19), and a follow-up 60×80 m case where TWIN sub-plots
   were architecturally correct but produced 0 buildable footprints because the
   default 3 m side setback ate the entire frontage (Q21). Three connected
   owner decisions — Q19 (road access), Q20 (per-type MPZP scaling), Q21
   (shared walls).

   | Component | Status |
   |---|---|
   | `core/building_proposer.py` | ✅ `BuildingType.SEMI` → `BuildingType.TWIN` (the dict crashed at import — Mode B/TWIN+TERRACED GUI flow was unreachable); pair/chain detection refactored to call `core/subdivision_topology` so subdivider and proposer agree |
   | `core/plot_subdivider.py` (Q19) | ✅ `_filter_for_building_type` and `_wrap_valid_subplot` accept parent DROGA OR internal road for ALL building types (Q3 only mandates orientation, not location) |
   | `core/plot_subdivider.py` (Q20) | ✅ `_with_effective_mpzp` scales `min_front_m`/`min_sub_plot_area_m2`/`max_sub_plot_area_m2` per BuildingType so 1 sub-plot = 1 segment; `_min_short_dim(mpzp)` derives the `_is_buildable_shape` guard from `mpzp.min_front_m` (no longer hardcoded 12 m) |
   | `core/plot_subdivider.py` (Q21) | ✅ `_mark_shared_walls(sub_plots, building_type, plot)` runs AFTER absorb/split, sets `PlotBoundary.is_shared_wall=True` on the shared edge of every pair (TWIN) or chain neighbour (TERRACED), and rebuilds the affected sub-plots' buildable zones |
   | `core/plot_model.py` | ✅ `PlotBoundary.is_shared_wall: bool = False`; `min_setback` returns 0 when the flag is set |
   | `core/buildable_zone.py` | ✅ `_setback_distance` short-circuits to 0 for `is_shared_wall=True` boundaries (Mode A unaffected — flag defaults False) |
   | `core/subdivision_topology.py` | ✅ NEW shared helpers `find_adjacent_pairs`, `find_chains`, `longest_linestring`; one source of truth for both `building_proposer` and `plot_subdivider._mark_shared_walls` |
   | `tests/test_building_proposer.py` | ✅ NEW (4 tests): SEMI→TWIN regression + DETACHED/TWIN/TERRACED end-to-end smoke (TWIN unblocked by Q21) |
   | `tests/test_plot_subdivider.py` | ✅ `TestQ19RoadAccess` (5 tests) + `TestQ20SegmentScaling` (6 tests) + `TestQ21SharedWalls` (4 tests) |
   | `docs/OPEN_QUESTIONS.md` | ✅ Q19, Q20, Q21 added as DECIDED with owner reasoning |
   | `requirements.txt` | ✅ `reportlab>=4.0` added (Phase 2 dep that was missing) |

   **Stage 1 verification after Session 10 (2026-05-26):**

   - Full non-GUI suite (`pytest --ignore=notebooks --ignore=tests/test_gui.py`):
     ✅ **287 passed, 31 skipped, 1 xpassed** (exit 0, ~10 min)
   - Pre-Q21 baseline (modified-areas subset, briefing 2026-05-25):
     39 passed + 1 failed (`test_propose_buildings_twin_runs_and_assigns`)
   - Post-Q21 (same subset): all 5 GREEN (4 new `TestQ21SharedWalls` +
     previously-red TWIN regression).
   - Verified: TWIN on 60×80 m now places ≥1 building (was 0/7);
     `TestQ19RoadAccess` confirms TWIN/TERRACED on 265×202 m no longer collapse
     to monster sub-plots; Mode A unaffected (Q21 flag defaults False).

   **Stage 1 Session 10 visual sanity check (2026-05-27) — PASS:**

   | Component | Status |
   |---|---|
   | `notebooks/stage1_q21_sanity.py` | ✅ NEW: 5 scenarios (265×202 DETACHED/TWIN/TERRACED + 60×80 TWIN/TERRACED) rendered via production `subdivide()` + `propose_buildings()` |
   | `notebooks/output/q21_sanity_*.png` | ✅ 5 detail + 1 overview PNG |

   - 60×80 TWIN: **5/5 buildings** (regression vs pre-Q21 0/7) ✅
   - 265×202 TWIN: 70 sub-plots, 35 TWIN pairs, 100% coverage, Q21 shared walls visible between paired neighbours ✅
   - 265×202 TERRACED: 81 sub-plots in 6 chains, 100% coverage, every sub-plot has a building, shared walls along chain ✅
   - Q16 coverage: diff=0.00 m² in all 5 scenarios; nieużytek=0%
   - Architectural review (owner): pass — close Q21 visual validation, no further fixes required this session.
   - Outstanding open questions noted but not blocking: DETACHED `max_sub_plot_area_m2=2000` may be too generous (avg 1729 m² per sub-plot); TERRACED produces 81 not 120+ on 265×202; vertical road appears mid-plot in 265×202 layouts. None marked as bugs.

   **Stage 1 outstanding (after Session 10 + sanity check 2026-05-27):**

   - STATE.md Phase 3 section still says "PLAN READY, NOT IMPLEMENTED" — UI
     integration (Eksport PDF) shipped in commit `9017bae` 2026-05-?; sync needed.
   - Q1.1(c) push-neighbour mechanism — still deferred (Q1.1(d) drop-to-nieużytek
     fallback is in production).
   - ~~`core/plot_subdivider.py` legacy experimental algorithms~~ — DONE 2026-05-27:
     21 dead functions removed (file 2860 → 1731 lines, −39%); 287 non-GUI tests
     still pass, no regressions.

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
