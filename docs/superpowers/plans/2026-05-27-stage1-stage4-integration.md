# Stage 1 → Stage 4 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Mode B sub-plots (DETACHED/TWIN/TERRACED single-family) from the Stage 1 canvas to Stage 4 — click → highlight → "Otwórz w Stage 4" button → prefilled Stage 4 + auto-switched tab.

**Architecture:** New pure-Python helper `core/building_to_apartment_input.py` derives `(polygon, entry, wall_types)` from a `SubPlot`. `Stage1Widget` emits a Qt `pyqtSignal` carrying that payload; `MainWindow` connects a slot that populates `_imported_polygon` / `_imported_entry` / `_imported_wall_types`, renders the boundary preview, and switches the active tab. A `MainWindow`-level confirm dialog prevents accidental overwrite when Stage 4 already holds generated variants.

**Tech Stack:** Python 3.13, PyQt5, matplotlib 3.10 (Qt5Agg backend), shapely 2.1, pytest. Tests use the existing session-scoped `qapp` fixture in `tests/conftest.py` (no `pytest-qt`).

**Spec:** `docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md`

---

## File Structure

| File | Status | Purpose |
|---|---|---|
| `core/building_to_apartment_input.py` | CREATE | Pure function `building_to_apartment_input(sub, roads=None) → (Polygon, (x,y), list[WallType])`. No Qt, no IO. |
| `tests/test_building_to_apartment_input.py` | CREATE | Unit tests for the pure helper (DETACHED/TWIN/TERRACED, MultiPolygon, no-road fallback). |
| `ui/stage1_window.py` | MODIFY | Add `apartment_layout_requested` signal, canvas click hit-test, selection state, "Otwórz w Stage 4" button + handler, highlight rendering in `_render_mode_b`. |
| `ui/main_window.py` | MODIFY | Expose `self.stage1_widget` and `self.apt_tab`. Add `_populate_stage4_from_stage1` slot, signal wire-up, confirm-overwrite dialog. |
| `tests/test_stage1_stage4_integration.py` | CREATE | Qt smoke: signal emit → slot fills `_imported_*` → tab switched. Uses `qapp` fixture. |
| `docs/STATE.md`, `NEXT_SESSION.md` | MODIFY | Move integration from PRIO 2 (deferred) to DONE; update "Last update" date. |

---

### Task 1: Failing tests for `building_to_apartment_input`

**Files:**
- Create: `tests/test_building_to_apartment_input.py`

- [ ] **Step 1: Write the failing test file**

```python
"""Unit tests for core/building_to_apartment_input.py (Stage 1 → Stage 4 helper)."""
from __future__ import annotations

import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from core.building_to_apartment_input import building_to_apartment_input
from core.models import WallType
from core.plot_model import BoundaryType, PlotBoundary
from core.plot_subdivider import SubPlot


def _make_sub(
    building: Polygon,
    *,
    boundaries: list[PlotBoundary] | None = None,
    parent_droga_touch: float = 0.0,
    internal_road_touch: float = 0.0,
) -> SubPlot:
    """Factory for a SubPlot wired with a proposed_building and boundaries."""
    sub = SubPlot(
        polygon=box(*building.bounds) if not boundaries else
                Polygon([(0, 0), (12, 0), (12, 30), (0, 30)]),
        boundaries=boundaries or [],
        proposed_building=building,
        parent_droga_touch=parent_droga_touch,
        internal_road_touch=internal_road_touch,
    )
    return sub


def _rect_building(x0=2.0, y0=10.0, w=8.0, d=10.0) -> Polygon:
    """An 8×10 m building footprint at (x0, y0)."""
    return box(x0, y0, x0 + w, y0 + d)


def _droga_bottom_boundary(x0=0.0, x1=12.0, y=0.0) -> PlotBoundary:
    return PlotBoundary(
        geometry=LineString([(x0, y), (x1, y)]),
        boundary_type=BoundaryType.DROGA,
        segment_index=0,
        is_shared_wall=False,
    )


def _shared_side_boundary(x=12.0, y0=0.0, y1=30.0, segment_index=1) -> PlotBoundary:
    return PlotBoundary(
        geometry=LineString([(x, y0), (x, y1)]),
        boundary_type=BoundaryType.SASIAD_NIEZABUDOWANY,
        segment_index=segment_index,
        is_shared_wall=True,
    )


class TestDetached:
    def test_all_facade(self):
        sub = _make_sub(_rect_building(), boundaries=[_droga_bottom_boundary()])
        _, _, walls = building_to_apartment_input(sub)
        assert all(w == WallType.FACADE for w in walls)
        assert len(walls) == 4

    def test_entry_on_road_side(self):
        building = _rect_building(x0=2.0, y0=10.0, w=8.0, d=10.0)
        sub = _make_sub(building, boundaries=[_droga_bottom_boundary()])
        polygon, entry, _ = building_to_apartment_input(sub)
        # Road is at y=0; building bottom is y=10. Entry should be on the
        # building edge nearest the road — i.e. the bottom edge y=10, midpoint x.
        assert entry == pytest.approx((6.0, 10.0))
        assert polygon.equals(building)


class TestTwin:
    def test_one_internal_when_one_shared_wall(self):
        # Building shares its right edge (x=12) with the partner sub-plot.
        building = box(4.0, 10.0, 12.0, 20.0)
        sub = _make_sub(
            building,
            boundaries=[
                _droga_bottom_boundary(),
                _shared_side_boundary(x=12.0),
            ],
        )
        _, _, walls = building_to_apartment_input(sub)
        assert walls.count(WallType.INTERNAL) == 1
        assert walls.count(WallType.FACADE) == 3


class TestTerracedMiddle:
    def test_two_internal_when_two_shared_walls(self):
        # Building shares both side edges with chain neighbours.
        building = box(0.0, 10.0, 12.0, 20.0)
        sub = _make_sub(
            building,
            boundaries=[
                _droga_bottom_boundary(x0=0.0, x1=12.0),
                _shared_side_boundary(x=12.0, segment_index=1),
                PlotBoundary(
                    geometry=LineString([(0.0, 0.0), (0.0, 30.0)]),
                    boundary_type=BoundaryType.SASIAD_NIEZABUDOWANY,
                    segment_index=3,
                    is_shared_wall=True,
                ),
            ],
        )
        _, _, walls = building_to_apartment_input(sub)
        assert walls.count(WallType.INTERNAL) == 2
        assert walls.count(WallType.FACADE) == 2


class TestMultiPolygonBuilding:
    def test_picks_largest_part(self):
        big = box(0.0, 0.0, 10.0, 10.0)        # area 100
        small = box(20.0, 0.0, 22.0, 1.0)      # area 2
        sub = _make_sub(big)  # SubPlot factory takes the larger polygon shape
        sub.proposed_building = MultiPolygon([big, small])
        polygon, _, _ = building_to_apartment_input(sub)
        assert polygon.equals(big)


class TestFallbackEntry:
    def test_no_road_uses_longest_edge_midpoint(self):
        # No DROGA boundary, no roads passed → fallback path.
        building = box(0.0, 0.0, 12.0, 6.0)    # long edges of length 12
        sub = SubPlot(
            polygon=building,
            boundaries=[],
            proposed_building=building,
            parent_droga_touch=0.0,
            internal_road_touch=0.0,
        )
        _, entry, _ = building_to_apartment_input(sub, roads=None)
        # Longest edges are the two y=0 and y=6 sides (length 12).
        # Midpoint either (6, 0) or (6, 6). Function must pick deterministically
        # (first encountered in exterior coord order = bottom y=0).
        assert entry == pytest.approx((6.0, 0.0))
```

- [ ] **Step 2: Run the test file to verify it fails**

Run: `source venv/bin/activate && python3 -m pytest tests/test_building_to_apartment_input.py -v`
Expected: `ModuleNotFoundError: No module named 'core.building_to_apartment_input'` (all tests RED at collection).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_building_to_apartment_input.py
git commit -m "test(stage1): RED tests for building_to_apartment_input helper

Covers DETACHED (all FACADE), TWIN (1 INTERNAL), TERRACED middle (2 INTERNAL),
MultiPolygon defensive (pick largest), and no-road fallback (longest edge midpoint).
Module not yet implemented → ModuleNotFoundError at collection.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: GREEN implementation of `building_to_apartment_input`

**Files:**
- Create: `core/building_to_apartment_input.py`

- [ ] **Step 1: Write the implementation**

```python
"""Stage 1 → Stage 4 input adapter (pure-Python, no Qt).

Given a Mode B SubPlot with a `proposed_building` footprint, derive the
three values Stage 4 expects:
    polygon     — building footprint as a single shapely.Polygon
    entry       — (x, y) midpoint of the polygon edge nearest a road
    wall_types  — per-edge list[WallType] (FACADE / INTERNAL),
                  one entry per polygon exterior edge, in coord order.

See docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md.
"""
from __future__ import annotations

from typing import Optional

from shapely.geometry import LineString, MultiPolygon, Polygon

from core.models import WallType
from core.plot_model import BoundaryType
from core.plot_subdivider import SubPlot

_SHARED_WALL_TOLERANCE_M = 0.5    # how close a building edge must lie to a
                                  # sub-plot is_shared_wall boundary to count
                                  # as INTERNAL


def building_to_apartment_input(
    sub: SubPlot,
    roads: Optional[list[Polygon]] = None,
) -> tuple[Polygon, tuple[float, float], list[WallType]]:
    """Return (polygon, entry, wall_types) for Stage 4 from a SubPlot.

    See module docstring + spec section 4 for algorithm details.
    """
    polygon = _largest_polygon(sub.proposed_building)
    edges = _exterior_edges(polygon)

    entry_idx = _entry_edge_index(edges, sub, roads)
    entry = _midpoint(edges[entry_idx])

    wall_types = [_classify_edge(e, sub) for e in edges]

    return polygon, entry, wall_types


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _largest_polygon(geom) -> Polygon:
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda p: p.area)
    return geom


def _exterior_edges(polygon: Polygon) -> list[LineString]:
    coords = list(polygon.exterior.coords)
    # coords[-1] == coords[0] for closed rings; drop the closing duplicate.
    return [
        LineString([coords[i], coords[i + 1]])
        for i in range(len(coords) - 1)
    ]


def _midpoint(edge: LineString) -> tuple[float, float]:
    p = edge.interpolate(0.5, normalized=True)
    return (p.x, p.y)


def _entry_edge_index(
    edges: list[LineString],
    sub: SubPlot,
    roads: Optional[list[Polygon]],
) -> int:
    road_geoms: list = [
        b.geometry for b in sub.boundaries
        if b.boundary_type == BoundaryType.DROGA
    ]
    if roads:
        road_geoms.extend(r.boundary for r in roads if not r.is_empty)

    if road_geoms:
        def distance_to_any_road(edge: LineString) -> float:
            return min(edge.distance(r) for r in road_geoms)
        return min(range(len(edges)), key=lambda i: distance_to_any_road(edges[i]))

    # Fallback: longest edge. Ties broken by exterior order (lower index wins).
    return max(range(len(edges)), key=lambda i: edges[i].length if i == 0 else edges[i].length - 1e-9 * i)


def _classify_edge(edge: LineString, sub: SubPlot) -> WallType:
    for b in sub.boundaries:
        if not b.is_shared_wall:
            continue
        if edge.distance(b.geometry) <= _SHARED_WALL_TOLERANCE_M:
            return WallType.INTERNAL
    return WallType.FACADE
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_building_to_apartment_input.py -v`
Expected: 6 passed (TestDetached×2, TestTwin×1, TestTerracedMiddle×1, TestMultiPolygonBuilding×1, TestFallbackEntry×1).

- [ ] **Step 3: Run the full non-GUI suite for regression check**

Run: `python3 -m pytest --ignore=notebooks --ignore=tests/test_gui.py -q 2>&1 | tail -3`
Expected: 287 + 6 = 293 passed, 31 skipped, 1 xpassed.

- [ ] **Step 4: Commit**

```bash
git add core/building_to_apartment_input.py
git commit -m "feat(core): building_to_apartment_input helper for Stage 1→4

Pure-Python adapter from Mode B SubPlot to Stage 4 input contract:
  - polygon: SubPlot.proposed_building (largest part if MultiPolygon)
  - entry: midpoint of building edge nearest any road geometry
           (sub.boundaries DROGA + optional roads param), longest-edge fallback
  - wall_types: list[WallType], INTERNAL where building edge lies within 0.5m
                of a is_shared_wall=True boundary (Q21), FACADE otherwise

6 unit tests pass. No regressions in full suite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Expose `self.stage1_widget` and `self.apt_tab` on `MainWindow`

**Files:**
- Modify: `ui/main_window.py:210` (Stage 1 inline instance → `self.stage1_widget`)
- Modify: `ui/main_window.py:234-239` (`apt_tab` local → `self.apt_tab`)

- [ ] **Step 1: Refactor Stage 1 instance to a member**

In `ui/main_window.py`, find:

```python
try:
    from ui.stage1_window import Stage1Widget
    self.tabs.addTab(Stage1Widget(self), "Stage 1: Plot Analyser")
except Exception as e:
    print(f"[WARN] Stage 1 tab unavailable: {e}")
```

Replace the `addTab` call so the widget is reachable as `self.stage1_widget`:

```python
try:
    from ui.stage1_window import Stage1Widget
    self.stage1_widget = Stage1Widget(self)
    self.tabs.addTab(self.stage1_widget, "Stage 1: Plot Analyser")
except Exception as e:
    print(f"[WARN] Stage 1 tab unavailable: {e}")
    self.stage1_widget = None
```

- [ ] **Step 2: Refactor `apt_tab` local to `self.apt_tab`**

In `ui/main_window.py`, find the Stage 4 block (around line 233-239):

```python
# Stage 4 — apartment layout (this is the existing implementation)
apt_tab = QWidget()
self.tabs.addTab(apt_tab, "Stage 4: Apartment Layout")
# Default to Stage 4 (the working part) so users see results immediately
self.tabs.setCurrentWidget(apt_tab)

main_layout = QHBoxLayout(apt_tab)
```

Replace with:

```python
# Stage 4 — apartment layout (this is the existing implementation)
self.apt_tab = QWidget()
self.tabs.addTab(self.apt_tab, "Stage 4: Apartment Layout")
# Default to Stage 4 (the working part) so users see results immediately
self.tabs.setCurrentWidget(self.apt_tab)

main_layout = QHBoxLayout(self.apt_tab)
```

- [ ] **Step 3: Verify nothing else references the local `apt_tab`**

Run: `grep -n "\bapt_tab\b" ui/main_window.py`
Expected: only references through `self.apt_tab` (4 matches: assignment + 3 uses). If the grep finds bare `apt_tab` elsewhere, replace those too — there must be no local `apt_tab` left.

- [ ] **Step 4: Smoke import — make sure the file still parses**

Run: `python3 -c "from ui.main_window import MainWindow; print('import ok')"`
Expected: `import ok` (no exception).

- [ ] **Step 5: Commit**

```bash
git add ui/main_window.py
git commit -m "refactor(main_window): expose self.stage1_widget and self.apt_tab

Stage 1 widget and Stage 4 tab were local-only — making them members
enables Stage 1 → Stage 4 signal wiring (next task).

No behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `Stage1Widget` canvas click + selection state + highlight

**Files:**
- Modify: `ui/stage1_window.py` (Stage1Widget) — add state, mpl_connect, highlight rendering

- [ ] **Step 1: Add selection state and last-result cache to `__init__`**

In `ui/stage1_window.py`, find the `__init__` of `Stage1Widget`:

```python
self._poll_initial_guids: set = set()
self._build_ui()
self._refresh_outline_preview()
```

Insert two new lines before `self._build_ui()`:

```python
self._poll_initial_guids: set = set()
# Stage 1 → Stage 4 (Mode B only) selection state
self._mode_b_result = None         # last SubdivisionResult, for click hit-test
self._selected_sub_idx = None      # index into result.sub_plots
self._build_ui()
self._refresh_outline_preview()
```

- [ ] **Step 2: Wire matplotlib canvas click handler**

After the existing line `self.canvas = FigureCanvasQTAgg(self.fig)` (around line 257), add:

```python
self.canvas.mpl_connect("button_press_event", self._on_canvas_click)
```

- [ ] **Step 3: Add the click handler and helper**

Add a new method to `Stage1Widget` (place it just above `_render_mode_b`):

```python
def _on_canvas_click(self, event):
    """Mode B only: hit-test against sub_plots, set _selected_sub_idx."""
    if self._mode_b_result is None or event.xdata is None or event.ydata is None:
        return
    from shapely.geometry import Point
    pt = Point(event.xdata, event.ydata)
    for i, s in enumerate(self._mode_b_result.sub_plots):
        if s.polygon.contains(pt):
            self._selected_sub_idx = i
            self._render_mode_b(self._mode_b_result.parent, self._mode_b_result)
            self._update_open_in_stage4_btn()
            return
    # Click in empty space — clear selection.
    self._selected_sub_idx = None
    self._render_mode_b(self._mode_b_result.parent, self._mode_b_result)
    self._update_open_in_stage4_btn()
```

(`_update_open_in_stage4_btn` will be added in Task 5 — for this task, it can be a stub method on the same class:)

```python
def _update_open_in_stage4_btn(self):
    """Placeholder — implemented in Task 5."""
    pass
```

- [ ] **Step 4: Cache the result in `_run_mode_b` so the canvas click handler can hit-test**

In `_run_mode_b`, after `propose_buildings(result, building_type)` and BEFORE `self._render_mode_b(...)`, add:

```python
self._mode_b_result = result
self._selected_sub_idx = None
```

- [ ] **Step 5: Highlight rendering — modify `_render_mode_b`**

In `_render_mode_b`, find the loop:

```python
for i, s in enumerate(result.sub_plots):
    sx, sy = s.polygon.exterior.xy
    c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
    ax.fill(sx, sy, color=c, alpha=0.7, edgecolor="black", linewidth=0.8)
```

Change the `edgecolor`/`linewidth` to honour the selected index:

```python
for i, s in enumerate(result.sub_plots):
    sx, sy = s.polygon.exterior.xy
    c = SUBPLOT_COLORS[i % len(SUBPLOT_COLORS)]
    if i == self._selected_sub_idx:
        edge_color, edge_w = "#f1c40f", 3.0     # yellow highlight
    else:
        edge_color, edge_w = "black", 0.8
    ax.fill(sx, sy, color=c, alpha=0.7, edgecolor=edge_color, linewidth=edge_w)
```

- [ ] **Step 6: Manual smoke**

Run: `source venv/bin/activate && python3 -m ui.main_window`
In the GUI: switch to Stage 1 tab → set housing=Jednorodzinna, Mode=B → click Generate → click any sub-plot on the canvas → it should get a yellow highlight border. Click again in empty space → highlight clears.

- [ ] **Step 7: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1): canvas click selects sub-plot (yellow highlight)

Adds _mode_b_result + _selected_sub_idx state on Stage1Widget. Wires
matplotlib canvas button_press_event to a hit-test against the current
SubdivisionResult.sub_plots; selected sub-plot gets a 3-pt yellow border
in _render_mode_b. _update_open_in_stage4_btn stub for the next task.

Manual smoke: click a sub-plot on the Mode B canvas → highlight visible;
click empty space → highlight clears.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: "Otwórz w Stage 4" button + `apartment_layout_requested` signal

**Files:**
- Modify: `ui/stage1_window.py` (add signal, button, button-enable logic, emit handler)

- [ ] **Step 1a: Add `pyqtSignal` to the PyQt5.QtCore import**

In `ui/stage1_window.py`, find the module-level import:

```python
from PyQt5.QtCore import Qt, QTimer
```

Append `pyqtSignal`:

```python
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
```

- [ ] **Step 1b: Declare the signal as a class attribute on `Stage1Widget`**

Inside the `Stage1Widget` class body, immediately after the docstring `"""Stage 1 panel — embeddable in QTabWidget."""` and BEFORE `def __init__(self, parent=None):`, add:

```python
    # Stage 1 → Stage 4 integration (Mode B SF only)
    apartment_layout_requested = pyqtSignal(object, object, object)
    # args: (polygon: shapely.Polygon, entry: (x, y), wall_types: list[WallType])
```

(Class attribute — at indentation level 4, same level as `def __init__`.)

- [ ] **Step 2: Add the "Otwórz w Stage 4" button to the Mode B options panel**

In `_build_ui`, find the Mode B options box (around the line with `bt_combo`):

```python
bl.addWidget(self.bt_combo, 0, 1)
left.addWidget(modeb_box)
```

Insert a new button row before `left.addWidget(modeb_box)`:

```python
bl.addWidget(self.bt_combo, 0, 1)
self.open_in_stage4_btn = QPushButton("Otwórz wybraną sub-działkę w Stage 4")
self.open_in_stage4_btn.setEnabled(False)
self.open_in_stage4_btn.setToolTip(
    "Wybierz sub-działkę z proposed_building klikając ją na canvasie, "
    "potem otwórz jej obrys jako wejście do Stage 4."
)
self.open_in_stage4_btn.clicked.connect(self._on_open_in_stage4)
bl.addWidget(self.open_in_stage4_btn, 1, 0, 1, 2)
left.addWidget(modeb_box)
```

- [ ] **Step 3: Implement `_update_open_in_stage4_btn` (replace the Task-4 stub)**

Replace the placeholder body:

```python
def _update_open_in_stage4_btn(self):
    """Enable iff a sub-plot with proposed_building is currently selected."""
    if (self._mode_b_result is None
            or self._selected_sub_idx is None
            or self._selected_sub_idx >= len(self._mode_b_result.sub_plots)):
        self.open_in_stage4_btn.setEnabled(False)
        self.open_in_stage4_btn.setToolTip(
            "Kliknij sub-działkę na canvasie aby ją wybrać."
        )
        return
    sub = self._mode_b_result.sub_plots[self._selected_sub_idx]
    pb = getattr(sub, "proposed_building", None)
    if pb is None or pb.is_empty:
        self.open_in_stage4_btn.setEnabled(False)
        self.open_in_stage4_btn.setToolTip(
            "Brak proposed building — sprawdź strefę zabudowy tej sub-działki."
        )
        return
    self.open_in_stage4_btn.setEnabled(True)
    self.open_in_stage4_btn.setToolTip(
        f"Otwórz sub-działkę #{self._selected_sub_idx + 1} jako rzut w Stage 4."
    )
```

- [ ] **Step 4: Implement `_on_open_in_stage4`**

Add a new method right below `_update_open_in_stage4_btn`:

```python
def _on_open_in_stage4(self):
    """Emit apartment_layout_requested with derived (polygon, entry, walls)."""
    if self._mode_b_result is None or self._selected_sub_idx is None:
        return
    sub = self._mode_b_result.sub_plots[self._selected_sub_idx]
    pb = getattr(sub, "proposed_building", None)
    if pb is None or pb.is_empty:
        return
    from core.building_to_apartment_input import building_to_apartment_input
    polygon, entry, walls = building_to_apartment_input(
        sub, roads=self._mode_b_result.roads
    )
    self.apartment_layout_requested.emit(polygon, entry, walls)
```

- [ ] **Step 5: Manual smoke**

Run: `python3 -m ui.main_window`
Stage 1 → Mode B → Generate → click a sub-plot with a building → "Otwórz wybraną sub-działkę w Stage 4" button enables. Click → nothing visible yet (slot doesn't exist), but no exception in console.

- [ ] **Step 6: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1): 'Otwórz w Stage 4' button + apartment_layout_requested signal

Adds Stage1Widget.apartment_layout_requested = pyqtSignal(object, object, object)
emitting (polygon, entry, wall_types) for a selected Mode B sub-plot.
Button enables iff selection has proposed_building; tooltip explains state.
Click → call building_to_apartment_input(sub, roads=result.roads) → emit.

Slot side wired in next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `MainWindow` slot + signal wire-up

**Files:**
- Modify: `ui/main_window.py` — add `_populate_stage4_from_stage1` slot, connect signal in `_build_ui`

- [ ] **Step 1: Connect the signal after Stage 1 widget creation**

In `ui/main_window.py`, find the block from Task 3 step 1:

```python
try:
    from ui.stage1_window import Stage1Widget
    self.stage1_widget = Stage1Widget(self)
    self.tabs.addTab(self.stage1_widget, "Stage 1: Plot Analyser")
except Exception as e:
    print(f"[WARN] Stage 1 tab unavailable: {e}")
    self.stage1_widget = None
```

Add a signal connection inside the `try` block, after `addTab`:

```python
try:
    from ui.stage1_window import Stage1Widget
    self.stage1_widget = Stage1Widget(self)
    self.tabs.addTab(self.stage1_widget, "Stage 1: Plot Analyser")
    self.stage1_widget.apartment_layout_requested.connect(
        self._populate_stage4_from_stage1
    )
except Exception as e:
    print(f"[WARN] Stage 1 tab unavailable: {e}")
    self.stage1_widget = None
```

- [ ] **Step 2: Implement the slot**

Add a new method `_populate_stage4_from_stage1` to `MainWindow`. Place it right after `_import_from_archicad` (search for that method name; the new method goes immediately below it):

```python
def _populate_stage4_from_stage1(self, polygon, entry, wall_types):
    """Slot for Stage1Widget.apartment_layout_requested.

    Fills Stage 4 input fields, renders the boundary preview, and switches
    the active tab to Stage 4. If Stage 4 already has generated variants,
    asks for confirmation before overwriting.
    """
    if self.variants:
        if not self._confirm_stage4_overwrite():
            return
    self._imported_polygon = polygon
    self._imported_entry = entry
    self._imported_wall_types = list(wall_types)   # copy — slot owns the list
    self._show_boundary_preview(polygon, entry)
    self.tabs.setCurrentWidget(self.apt_tab)
    self._real_status_bar.showMessage(
        f"Załadowano sub-działkę ze Stage 1 ({polygon.area:.1f} m²). "
        f"Kliknij Generate aby wygenerować rzut.", 6000
    )
```

- [ ] **Step 3: Stub the confirm dialog method (full implementation in Task 7)**

Add directly below `_populate_stage4_from_stage1`:

```python
def _confirm_stage4_overwrite(self) -> bool:
    """Placeholder — Task 7 replaces this with a QMessageBox confirm.

    Returning True means "go ahead, overwrite Stage 4".
    """
    return True
```

- [ ] **Step 4: Manual smoke (end-to-end without confirm)**

Run: `python3 -m ui.main_window`
Stage 1 → Mode B → Generate → click sub-plot → "Otwórz w Stage 4" → tab switches to Stage 4; the building outline appears in the preview pane on the right; status bar shows "Załadowano sub-działkę". Click Generate in Stage 4 → room layout renders within ~10 s.

- [ ] **Step 5: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(main_window): _populate_stage4_from_stage1 slot + signal wire-up

Connects Stage1Widget.apartment_layout_requested to a slot that fills
_imported_polygon/_imported_entry/_imported_wall_types, renders the
boundary preview, and switches active tab to Stage 4. Status bar tells
the user to click Generate.

Confirm-overwrite is a stub returning True; Task 7 adds the real dialog.

End-to-end manual smoke: Mode B → click sub-plot → Otwórz → Stage 4
prefilled → Generate → room layout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Confirm overwrite dialog

**Files:**
- Modify: `ui/main_window.py` — replace `_confirm_stage4_overwrite` stub with QMessageBox dialog

- [ ] **Step 1: Replace the stub**

In `ui/main_window.py`, find `_confirm_stage4_overwrite` (added in Task 6). Replace its body:

```python
def _confirm_stage4_overwrite(self) -> bool:
    """Ask before overwriting an existing Stage 4 result with new data."""
    reply = QMessageBox.question(
        self,
        "Nadpisać obecny rzut?",
        "Stage 4 zawiera już wygenerowany rzut. Czy chcesz go zastąpić "
        "obrysem wybranej sub-działki?",
        QMessageBox.Yes | QMessageBox.Cancel,
        QMessageBox.Cancel,
    )
    return reply == QMessageBox.Yes
```

`QMessageBox` is already imported in `main_window.py` — verify with `grep`.

- [ ] **Step 2: Verify the import is present**

Run: `grep -n "QMessageBox" ui/main_window.py | head -3`
Expected: at least one import line matches.

- [ ] **Step 3: Manual smoke (with prior Stage 4 result)**

Run: `python3 -m ui.main_window`
Stage 4 → set W=8, H=6 manually → click Generate → variants appear. Now Stage 1 → Mode B → Generate → click a sub-plot → "Otwórz w Stage 4" → **expect confirm dialog** "Nadpisać obecny rzut?" — click Cancel → nothing changes; click Yes again → Stage 4 reloads with the sub-plot outline.

- [ ] **Step 4: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(main_window): confirm dialog when overwriting Stage 4 variants

Replaces the Task-6 stub with QMessageBox.question. Default button is
Cancel — accidental [Enter] does NOT lose user work.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Qt smoke integration test

**Files:**
- Create: `tests/test_stage1_stage4_integration.py`

- [ ] **Step 1: Write the test**

```python
"""Qt smoke test: Stage 1 → Stage 4 signal/slot wiring.

Uses qapp fixture from tests/conftest.py (session-scoped QApplication;
no pytest-qt needed).
"""
from __future__ import annotations

import pytest
from shapely.geometry import box

from core.models import WallType
from core.plot_subdivider import SubPlot
from core.plot_model import BoundaryType, PlotBoundary
from shapely.geometry import LineString
from ui.main_window import MainWindow


@pytest.fixture
def mw(qapp):
    """A fresh MainWindow; relies on Stage1Widget import succeeding."""
    win = MainWindow()
    yield win
    win.close()


def _fake_subdivision_result(parent_polygon=None):
    """A minimal stand-in for SubdivisionResult — just enough for the slot path."""
    from core.plot_subdivider import SubdivisionResult
    if parent_polygon is None:
        parent_polygon = box(0, 0, 12, 30)
    # Plot-like minimal wrapper: only `.parent` is touched by _render_mode_b,
    # and only `.geometry.exterior.xy`. So we use a duck-typed object.

    class _ParentStub:
        geometry = parent_polygon
        boundaries: list = []

    building = box(2, 10, 10, 20)
    sub = SubPlot(
        polygon=box(0, 0, 12, 30),
        boundaries=[
            PlotBoundary(
                geometry=LineString([(0, 0), (12, 0)]),
                boundary_type=BoundaryType.DROGA,
                segment_index=0,
                is_shared_wall=False,
            )
        ],
        proposed_building=building,
        parent_droga_touch=12.0,
        internal_road_touch=0.0,
    )
    result = SubdivisionResult(
        parent=_ParentStub(),                        # duck type
        sub_plots=[sub],
        roads=[],
        nieuzytek=None,
        orientation_name="smoke",
        rows=1,
        cols=1,
    )
    return result, sub


class TestSignalToSlotWiring:
    def test_slot_fills_stage4_fields_and_switches_tab(self, mw):
        assert mw.stage1_widget is not None, "Stage 1 widget must load"
        # Pre-state: Stage 4 has no imported outline.
        assert mw._imported_polygon is None
        # Simulate Mode B finishing — populate the cache the click handler reads.
        result, sub = _fake_subdivision_result()
        mw.stage1_widget._mode_b_result = result
        mw.stage1_widget._selected_sub_idx = 0
        # Now trigger the public action.
        mw.stage1_widget._on_open_in_stage4()
        # Slot should have filled the Stage 4 fields.
        assert mw._imported_polygon is not None
        assert mw._imported_polygon.equals(sub.proposed_building)
        assert mw._imported_entry == pytest.approx((6.0, 10.0))
        assert mw._imported_wall_types is not None
        assert all(w in (WallType.FACADE, WallType.INTERNAL)
                   for w in mw._imported_wall_types)
        # Active tab must be Stage 4.
        assert mw.tabs.currentWidget() is mw.apt_tab

    def test_no_signal_emit_without_proposed_building(self, mw):
        """Selection without proposed_building must not emit the signal."""
        result, sub = _fake_subdivision_result()
        sub.proposed_building = None
        mw.stage1_widget._mode_b_result = result
        mw.stage1_widget._selected_sub_idx = 0
        # Record receipt: Should not call the slot at all.
        received = []
        mw.stage1_widget.apartment_layout_requested.connect(
            lambda *args: received.append(args)
        )
        mw.stage1_widget._on_open_in_stage4()
        assert received == []
        # And Stage 4 fields stay untouched.
        assert mw._imported_polygon is None
```

- [ ] **Step 2: Run the test**

Run: `source venv/bin/activate && python3 -m pytest tests/test_stage1_stage4_integration.py -v`
Expected: 2 passed.

- [ ] **Step 3: Run the full non-GUI suite to confirm no regressions**

Run: `python3 -m pytest --ignore=notebooks --ignore=tests/test_gui.py -q 2>&1 | tail -3`
Expected: 295 passed (287 baseline + 6 from Task 2 + 2 from this task), 31 skipped, 1 xpassed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_stage1_stage4_integration.py
git commit -m "test(stage1): Qt smoke for signal→slot wiring

Two scenarios:
  - slot fills _imported_polygon/_imported_entry/_imported_wall_types
    and switches active tab to Stage 4
  - no signal emission when selected sub-plot has proposed_building=None

Uses the existing qapp session-scoped fixture from tests/conftest.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Final manual smoke + STATE/NEXT_SESSION docs update

**Files:**
- Modify: `docs/STATE.md` (update "Last update", append Session 11 entry)
- Modify: `NEXT_SESSION.md` (close PRIO 2 / Stage 1→Stage 4, promote next)

- [ ] **Step 1: Manual end-to-end smoke on a real scenario**

Run: `source venv/bin/activate && python3 -m ui.main_window`

Reproduce the golden flow:
1. Stage 1 tab → set W=60, D=80 → Housing: Jednorodzinna, Mode: B → Building type: TWIN
2. Click Generate → 5 sub-plots appear with footprints
3. Click S1 → yellow highlight, "Otwórz w Stage 4" enables
4. Click "Otwórz w Stage 4" → tab switches to Stage 4 with the 8×10 (approx) building footprint preview
5. Click Generate in Stage 4 → room layout appears within ~10 s
6. Stop the app

Document the result in the commit message of Step 4 below.

- [ ] **Step 2: Update `docs/STATE.md`**

Edit the `> **Last update:** ...` line (around line 7) to:

```markdown
> **Last update:** 2026-05-27 (Stage 1 → Stage 4 integration shipped — Mode B SF sub-plot opens directly in Stage 4 with auto-detected entry/walls)
```

Then add a new section at the end of the "Stage 1 outstanding (after Session 10 + sanity check 2026-05-27)" block:

```markdown
   **Stage 1 → Stage 4 integration (Session 11, 2026-05-27):**

   | Component | Status |
   |---|---|
   | `core/building_to_apartment_input.py` | ✅ NEW — pure-Python adapter SubPlot → (polygon, entry, list[WallType]). 6 unit tests pass. |
   | `ui/stage1_window.py` Stage1Widget | ✅ + `apartment_layout_requested` signal; canvas hit-test; yellow highlight on selected sub-plot; "Otwórz wybraną sub-działkę w Stage 4" button (disabled until selection with proposed_building). |
   | `ui/main_window.py` MainWindow | ✅ + `self.stage1_widget` / `self.apt_tab` exposed; `_populate_stage4_from_stage1` slot; `_confirm_stage4_overwrite` QMessageBox dialog. |
   | `tests/test_stage1_stage4_integration.py` | ✅ NEW — 2 Qt smoke tests via `qapp` fixture (slot fills fields + tab switch; no emit without proposed_building). |
   | `docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md` | ✅ design spec |
   | `docs/superpowers/plans/2026-05-27-stage1-stage4-integration.md` | ✅ implementation plan |

   **Scope (decided in brainstorm 2026-05-27):**
   - Mode B single-family only (DETACHED/TWIN/TERRACED).
   - Auto-detect: entry = midpoint of building edge nearest a road geometry; walls INTERNAL where edge lies within 0.5 m of a Q21 `is_shared_wall=True` boundary, FACADE otherwise.
   - User explicitly clicks Generate in Stage 4 (no auto-solver).
   - Confirm dialog when Stage 4 already holds variants.

   **Out of scope (still on backlog):**
   - Mode A → Stage 4 (different UX — choose variant first).
   - Wielorodzinna → multi-apartment in one building (needs Stage 3 floor layout first).
```

- [ ] **Step 3: Update `NEXT_SESSION.md`**

Edit the PRIO 2 list — strike through Stage 1→Stage 4 and promote remaining items:

In the `## PRIO 2 — kolejne kandydaty (do decyzji Dawida)` section, find:

```markdown
4. **Stage 1 → Stage 4 integration** — kliknięcie sub-działki w Stage 1 GUI →
   otwórz jej obrys jako wejście do Stage 4.
```

Replace with:

```markdown
4. ~~**Stage 1 → Stage 4 integration**~~ — DONE 2026-05-27 (Session 11):
   click sub-plot → "Otwórz w Stage 4" → prefilled Stage 4 with auto-detected
   entry/walls. Mode B SF only; Mode A and wielorodzinna deferred.
```

Also update the top "STAN:" header date to 2026-05-27 and append:

```markdown
Session 11 (2026-05-27):
- 254c9f6 chore(stage1): Q21 visual sanity check + STATE/NEXT_SESSION sync
- 12e6906 docs(state): sync Stage 1 Phase 3 — COMPLETED 2026-05-24
- 483d71f chore(plot_subdivider): remove 21 dead functions (−39% file size)
- cfdf314 docs(spec): Stage 1 → Stage 4 integration design
- 6a46498 docs(spec): fix wall_types contract — WallType enum, not list[str]
- (Stage 1→4 implementation commits from this plan)
```

- [ ] **Step 4: Commit docs and close**

```bash
git add docs/STATE.md NEXT_SESSION.md
git commit -m "docs: STATE+NEXT_SESSION sync — Stage 1→Stage 4 integration shipped (Session 11)

Manual smoke on 60x80 TWIN scenario passes end-to-end:
  Stage 1 Mode B Generate → click S1 → Otwórz w Stage 4 → tab
  switches with 8x10 building footprint preview → Stage 4 Generate
  → room layout renders within ~10s.

PRIO 2 Stage 1→4 integration closed. Next backlog: Q1.1(c) push-neighbour,
L-shape floors, walls+doors AC export, Stage 2 volumetric generator.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Done when

- All 9 tasks committed.
- Full non-GUI suite (`pytest --ignore=notebooks --ignore=tests/test_gui.py`) shows **295 passed, 31 skipped, 1 xpassed** (287 baseline + 6 from Task 2 + 2 from Task 8).
- Manual smoke on 60×80 TWIN passes the end-to-end flow described in Task 9 Step 1.
- `docs/STATE.md` and `NEXT_SESSION.md` reflect Session 11.
