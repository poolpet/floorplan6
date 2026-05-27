# Stage 1 → Stage 4 Integration — Design Spec

**Status:** READY for plan
**Date:** 2026-05-27
**Owner:** Dawid Ćwiertniewicz
**Author:** Claude (brainstorm session)

## 1. Goal

For Mode B single-family sub-plots (DETACHED / TWIN / TERRACED), let the
user click a sub-plot in the Stage 1 canvas and open it in Stage 4 with
auto-detected entry point and wall classifications. This closes the
end-to-end workflow for single-family housing in one button click.

**Out of scope (deferred):**
- Mode A (3 buildup variants) — different UX, separate brainstorm
- Wielorodzinna (multi-family) — Mode B is already disabled for MW (Q12)
- Stage 2 / Stage 3 integration — separate end-to-end flow
- Walls + doors export to AC — orthogonal Stage 4 backlog

## 2. UX Flow

1. User generates Mode B subdivision in Stage 1 (existing flow)
2. User **clicks a sub-plot** on the matplotlib canvas → sub-plot gets a
   highlight outline (visible bright border)
3. The new **"Otwórz w Stage 4"** button below the Mode B panel becomes
   enabled iff the selected sub-plot has `proposed_building` (not None,
   not empty)
4. User clicks the button:
   - If Stage 4 currently has results (`MainWindow.variants` is non-empty)
     → confirm dialog: *"Nadpisać obecny rzut w Stage 4?"* [Tak] [Anuluj]
   - On confirm or empty-Stage-4: MainWindow populates Stage 4 fields
     (polygon, entry point, wall types) and switches the active tab to
     Stage 4
5. Stage 4 is now visible with prefilled input and the imported-outline
   preview rendered. The standard **"Generate"** button is yellow/ready;
   user clicks it when ready (~10s CP-SAT solver wait)
6. Standard Stage 4 flow continues (variants → scoring → export PNG/AC)

## 3. Architecture — Qt signal/slot

`Stage1Widget` emits a signal; `MainWindow` connects a slot. Decoupled
and idiomatic Qt — Stage1Widget does not need a reference to MainWindow.

```python
# ui/stage1_window.py
class Stage1Widget(QWidget):
    apartment_layout_requested = pyqtSignal(object, object, object)
    # args: (polygon: shapely.Polygon,
    #        entry: tuple[float, float],
    #        wall_types: list[WallType])   # core.models.WallType enum

    def _on_open_in_stage4(self) -> None:
        if self._selected_sub_idx is None:
            return
        sub = self._mode_b_result.sub_plots[self._selected_sub_idx]
        polygon, entry, walls = building_to_apartment_input(sub)
        self.apartment_layout_requested.emit(polygon, entry, walls)
```

```python
# ui/main_window.py
class MainWindow(QMainWindow):
    def _build_ui(self):
        ...
        self.stage1_widget = Stage1Widget(self)
        self.tabs.addTab(self.stage1_widget, "Stage 1: Plot Analyser")
        self.stage1_widget.apartment_layout_requested.connect(
            self._populate_stage4_from_stage1
        )
        ...

    def _populate_stage4_from_stage1(self, polygon, entry, walls):
        if self.variants and not self._confirm_overwrite():
            return
        self._imported_polygon = polygon
        self._imported_entry = entry
        self._imported_wall_types = walls
        self._show_boundary_preview(polygon, entry)  # existing method
        self.tabs.setCurrentWidget(self.apt_tab)
```

## 4. Auto-detect logic

New pure-Python module `core/building_to_apartment_input.py` (no Qt,
fully unit-testable):

```python
def building_to_apartment_input(
    sub: SubPlot,
    roads: list[Polygon] | None = None,   # result.roads, optional for fallback
) -> tuple[Polygon, tuple[float, float], list[WallType]]:
    """Derive Stage 4 input (polygon, entry, wall_types) from a Mode B sub-plot.

    Returns:
        polygon: sub.proposed_building (or its largest part if MultiPolygon).
        entry: midpoint of the building edge closest to a road edge
               (sub-plot's parent DROGA boundary or any internal road).
               Fallback: midpoint of the longest building edge.
        wall_types: per-edge classification, in the same order as the
                    polygon's exterior edges (one entry per edge, excluding
                    the closing duplicate vertex). Values from core.models.WallType:
                      WallType.INTERNAL if the building edge lies on a shared
                                        wall of the sub-plot (Q21 is_shared_wall=True),
                      WallType.FACADE   otherwise.
    """
```

### 4.1 Entry detection
- Identify sub-plot boundaries with road access: parent `boundary_type == DROGA`
  OR sub-plot edges that touch any element of `result.roads`.
- For each building exterior edge, compute the minimum Euclidean distance
  to any road-bearing boundary.
- Pick the building edge with the smallest such distance.
- If no road edge exists on the sub-plot → fallback: longest building edge.
- Entry point = midpoint of the chosen edge (on the polygon boundary).
  Stage 4 already accepts points on the polygon boundary via
  `MainWindow._closest_edge_to_point`, so no inward projection is needed.

### 4.2 Walls classification
For each building edge, in polygon exterior order:
- If the building edge lies within tolerance (≤ 0.5 m) of any sub-plot
  boundary with `is_shared_wall=True` → `WallType.INTERNAL`
- Else → `WallType.FACADE`

DETACHED → all 4 edges `WallType.FACADE`.
TWIN → 1 edge `INTERNAL` (paired neighbour), 3 edges `FACADE`.
TERRACED (middle of chain) → 2 edges `INTERNAL`, 2 edges `FACADE`.
TERRACED (end of chain) → 1 edge `INTERNAL`, 3 edges `FACADE`.

## 5. Components

| Component | Status | Notes |
|---|---|---|
| `core/building_to_apartment_input.py` | NEW | Pure function, no Qt. ~80 lines. |
| `tests/test_building_to_apartment_input.py` | NEW | 6+ tests: DETACHED (all facade), TWIN (1 inner), TERRACED middle (2 inner), TERRACED end (1 inner), MultiPolygon proposed_building, no road touch (fallback). |
| `ui/stage1_window.py` Stage1Widget | MOD | + `apartment_layout_requested` signal; + `_selected_sub_idx: Optional[int]` state; + `mpl_connect("button_press_event", self._on_canvas_click)`; + `_on_canvas_click` (hit-test against `result.sub_plots[i].polygon`); + `open_in_stage4_btn` widget in Mode B panel; + `_on_open_in_stage4` handler; + highlight rendering in `_render_mode_b` for `_selected_sub_idx` (thicker yellow border). |
| `ui/main_window.py` MainWindow | MOD | + `self.stage1_widget` instance member (was inline `Stage1Widget(self)`); + signal wire-up in `_build_ui`; + `_populate_stage4_from_stage1` slot; + `_confirm_overwrite_dialog` helper. |
| `tests/test_stage1_stage4_integration.py` | NEW | Qt signal smoke tests: signal emission, slot fills `_imported_polygon`/`_imported_entry`/`_imported_wall_types`, tab switch to apt_tab. Uses `qapp` fixture from `tests/conftest.py`. |

## 6. Data contract

The signal is emitted with three positional arguments
`(polygon, entry, wall_types)`:

| Field | Type | Semantics |
|---|---|---|
| `polygon` | `shapely.geometry.Polygon` | Building footprint, single Polygon. If proposed_building is MultiPolygon, the largest part is used. |
| `entry` | `tuple[float, float]` | `(x, y)` of entry point on or just inside the polygon. |
| `wall_types` | `list[WallType]` | One entry per polygon exterior edge, in coord order. Values from `core.models.WallType`: `WallType.FACADE` or `WallType.INTERNAL`. Matches `MainWindow._imported_wall_types` format. |

This matches Stage 4's existing input contract (see `MainWindow._imported_polygon` / `_imported_entry` / `_imported_wall_types`).

## 7. Edge cases

| Case | Behavior |
|---|---|
| `sub.proposed_building is None` | "Otwórz w Stage 4" button disabled. Tooltip: *"Brak proposed building — sprawdź strefę zabudowy"*. |
| `sub.proposed_building.is_empty` | Same as None (treat as no building). |
| MultiPolygon proposed_building | `building_to_apartment_input` picks largest part. |
| No road-adjacent edge | Fallback: midpoint of longest building edge. Tooltip warns *"Brak dostępu do drogi — entry domyślne"*. |
| User clicks empty area in canvas | No-op. `_selected_sub_idx` stays unchanged. |
| User clicks already-selected sub-plot | No-op (idempotent). |
| Stage 4 has existing variants | Confirm dialog before overwrite. |
| User cancels confirm dialog | Nothing changes. Stage 1 stays active. |
| `_mode_b_result is None` (no Mode B run yet) | Canvas click is no-op. Button stays disabled. |

## 8. Testing strategy

**Unit (pure-Python, fast):**
- `core/building_to_apartment_input.py` — 6+ tests covering all wall_types
  patterns + entry detection + fallback + MultiPolygon defense.

**Qt smoke (tests/conftest.py qapp fixture, no real solver):**
- `tests/test_stage1_stage4_integration.py` — signal emission, slot
  receives correct payload, fields populated, tab switch verified.

**Manual smoke (after merge, before close):**
- Run `python -m ui.main_window`, generate Mode B 60×80 TWIN, click a
  sub-plot, click "Otwórz w Stage 4", confirm tab switch + prefilled
  Stage 4, click Generate, see room layout.

**No regressions expected** in existing 287 non-GUI tests.

## 9. Implementation order (TDD)

1. `tests/test_building_to_apartment_input.py` (RED for all 6+ cases)
2. `core/building_to_apartment_input.py` (GREEN — pure logic)
3. `tests/test_stage1_stage4_integration.py` (RED — signal smoke)
4. `ui/stage1_window.py` — signal + click handler + button + highlight
5. `ui/main_window.py` — slot + wire-up + confirm dialog
6. Manual smoke check
7. STATE.md + NEXT_SESSION.md update
8. Single commit `feat(stage1): open sub-plot in Stage 4 (Mode B SF)`
