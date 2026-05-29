# SFH 2-storey core generation — Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a 2-storey single-family-house room layout (parter + piętro) on a rectangular footprint, with the staircase vertically aligned, reusing the proven CP-SAT solver.

**Architecture:** Add an additive `reserved_core` parameter to `solve_cpsat` (no-op when `None`). A new `core/house_layout.py` reserves a staircase rectangle near the entry and runs `solve_cpsat` twice (parter template, then piętro template) with the **same** reserved core, so the staircase lands at the same `(x,y)` on both storeys.

**Tech Stack:** Python 3.13, OR-Tools CP-SAT (`ortools`), Shapely, existing `core/cpsat_solver.py`, `core/models.py`, `core/template_selector.py`, `core/boundary_analyzer.py`.

**Scope:** This is Plan 1 of 3 for Phase 1. Plan 2 = furniture (`core/furniture.py`). Plan 3 = visualization + Stage 4 UI mode. This plan delivers a headless, testable 2-storey generator. Design: `docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md`.

**Conventions verified in code:** solver room vars `x[i], y[i], x_ends[i], y_ends[i]` are in **bbox-relative centimetres** (0..BW, 0..BH); `SCALE` converts metres→cm; the hub is the room whose `spec.id` contains `"hub"`; `solve_cpsat(template, boundary, time_limit_s=30.0, forced_facade=None, blocked_arrangements=None) -> CpsatResult`; `CpsatResult.rooms: list[Room]`; `Room.polygon` is in metres; `Boundary` has `.bbox`, `.width`, `.height`, `.entry_point`.

---

### Task 1: Additive `reserved_core` parameter on `solve_cpsat`

**Files:**
- Modify: `core/cpsat_solver.py` (signature ~line 230; constraint after the hub-contains-entry block ~line 431)
- Test: `tests/test_cpsat_reserved_core.py`

- [ ] **Step 1: Write the failing regression + behaviour tests**

```python
# tests/test_cpsat_reserved_core.py
from core.cpsat_solver import solve_cpsat, SCALE
from core.template_selector import load_all_templates
from core.boundary_analyzer import analyze_boundary
from shapely.geometry import Polygon


def _rect_boundary(w=10.0, d=8.0):
    poly = Polygon([(0, 0), (w, 0), (w, d), (0, d)])
    return analyze_boundary(poly, entry_point=(w / 2, 0.0))


def _template(tid="M3_standard"):
    return next(t for t in load_all_templates() if t.id == tid)


def test_reserved_core_none_is_unchanged():
    """Regression: reserved_core=None must not change apartment results."""
    b = _rect_boundary()
    t = _template()
    r1 = solve_cpsat(t, b, time_limit_s=10.0)
    r2 = solve_cpsat(t, b, time_limit_s=10.0, reserved_core=None)
    assert r1.status == r2.status
    assert len(r1.rooms) == len(r2.rooms)


def test_reserved_core_is_inside_hub():
    """With reserved_core set, the hub rectangle must contain the core."""
    b = _rect_boundary()
    t = _template()
    core = (4.0, 0.0, 2.5, 3.0)  # x, y, w, h in metres, bbox-relative
    r = solve_cpsat(t, b, time_limit_s=15.0, reserved_core=core)
    assert r.status in ("OPTIMAL", "FEASIBLE")
    hub = next(room for room in r.rooms if "hub" in room.spec.id)
    hb = hub.polygon.bounds  # (minx, miny, maxx, maxy) in metres
    cx, cy, cw, ch = core
    tol = 0.05
    assert hb[0] <= cx + tol and hb[2] >= cx + cw - tol
    assert hb[1] <= cy + tol and hb[3] >= cy + ch - tol
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_cpsat_reserved_core.py -q`
Expected: FAIL — `solve_cpsat() got an unexpected keyword argument 'reserved_core'`.

- [ ] **Step 3: Add the parameter to the signature**

In `core/cpsat_solver.py`, change the `solve_cpsat` signature to add the new keyword (keep all existing params):

```python
def solve_cpsat(
    template: Template,
    boundary: Boundary,
    time_limit_s: float = 30.0,
    forced_facade: Optional[dict[str, str]] = None,
    blocked_arrangements: Optional[list[RoomArrangement]] = None,
    reserved_core: Optional[tuple[float, float, float, float]] = None,
) -> CpsatResult:
```

Update the docstring Args with:
```
reserved_core: Optional (x, y, w, h) in metres, bbox-relative, that the hub
    must fully contain (e.g. a staircase core shared across storeys). None = off.
```

- [ ] **Step 4: Add the hub-contains-core constraint**

Immediately AFTER the hub-contains-entry block (the `if notch is None: ...` entry-side block ending ~line 442), still inside `if hub_idx is not None:`, add:

```python
        # Reserved core (e.g. shared staircase): hub must fully contain it.
        if reserved_core is not None:
            cx, cy, cw, ch = reserved_core
            csx = round(cx * SCALE)
            csy = round(cy * SCALE)
            cex = round((cx + cw) * SCALE)
            cey = round((cy + ch) * SCALE)
            model.add(x[hub_idx] <= csx)
            model.add(x_ends[hub_idx] >= cex)
            model.add(y[hub_idx] <= csy)
            model.add(y_ends[hub_idx] >= cey)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_cpsat_reserved_core.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full solver regression**

Run: `venv/bin/python -m pytest tests/test_cpsat_solver.py -q`
Expected: PASS (no regression — apartment flows untouched because `reserved_core` defaults to `None`).

- [ ] **Step 7: Commit**

```bash
git add core/cpsat_solver.py tests/test_cpsat_reserved_core.py
git commit -m "feat(stage4): additive reserved_core constraint on solve_cpsat (hub contains a fixed rectangle)"
```

---

### Task 2: Single-family house templates (parter + piętro)

**Files:**
- Create: `templates/house_parter.json`
- Create: `templates/house_pietro.json`
- Test: `tests/test_house_templates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_house_templates.py
from core.template_selector import load_all_templates


def _by_id(tid):
    return next((t for t in load_all_templates() if t.id == tid), None)


def test_house_parter_loads_with_expected_rooms():
    t = _by_id("house_parter")
    assert t is not None
    ids = {r.id for r in t.pokoje}
    assert {"hub", "wiatrolap", "salon", "kuchnia", "spizarnia", "wc", "kotlownia"} <= ids
    hub = next(r for r in t.pokoje if r.id == "hub")
    assert hub.strefa.value == "KOMUNIKACJA" or hub.strefa == "KOMUNIKACJA"


def test_house_pietro_loads_with_three_bedrooms_and_bathroom():
    t = _by_id("house_pietro")
    assert t is not None
    ids = {r.id for r in t.pokoje}
    assert {"hub", "sypialnia_1", "sypialnia_2", "sypialnia_3", "lazienka", "garderoba"} <= ids
    laz = next(r for r in t.pokoje if r.id == "lazienka")
    assert laz.max_powierzchnia <= 5.0 or laz.opt_powierzchnia <= 5.0


def test_house_templates_not_selected_for_apartments():
    """House templates must NOT pollute apartment (M*) selection."""
    from core.boundary_analyzer import analyze_boundary
    from core.template_selector import select_templates
    from shapely.geometry import Polygon
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    chosen = select_templates("M3", b, load_all_templates())
    assert all(not t.id.startswith("house_") for t in chosen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_house_templates.py -q`
Expected: FAIL — `test_house_parter_loads_with_expected_rooms` returns `None`.

- [ ] **Step 3: Create `templates/house_parter.json`**

```json
{
  "id": "house_parter",
  "nazwa": "Dom jednorodzinny — parter",
  "typ_mieszkania": "DOM_PARTER",
  "source": "authored",
  "pokoje": [
    {"id": "hub", "nazwa": "Hol + schody", "strefa": "KOMUNIKACJA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 6.0, "opt_powierzchnia": 9.0, "min_szerokosc": 2.5, "max_proporcja": 2.5, "procent_powierzchni": [0.08, 0.18]},
    {"id": "wiatrolap", "nazwa": "Wiatrolap", "strefa": "KOMUNIKACJA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 3.0, "opt_powierzchnia": 4.0, "min_szerokosc": 1.4, "max_proporcja": 2.0, "procent_powierzchni": [0.03, 0.08]},
    {"id": "salon", "nazwa": "Salon", "strefa": "DZIENNA", "wymaga_okna": true, "priorytet_fasady": 1, "preferowana_orientacja": ["south", "west"], "min_powierzchnia": 22.0, "opt_powierzchnia": 28.0, "min_szerokosc": 3.5, "max_proporcja": 2.0, "procent_powierzchni": [0.28, 0.42]},
    {"id": "kuchnia", "nazwa": "Kuchnia", "strefa": "DZIENNA", "wymaga_okna": true, "priorytet_fasady": 2, "preferowana_orientacja": [], "min_powierzchnia": 8.0, "opt_powierzchnia": 12.0, "min_szerokosc": 2.4, "max_proporcja": 2.2, "procent_powierzchni": [0.10, 0.18]},
    {"id": "spizarnia", "nazwa": "Spizarnia", "strefa": "USLUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.0, "opt_powierzchnia": 3.0, "min_szerokosc": 1.2, "max_proporcja": 2.5, "procent_powierzchni": [0.02, 0.06]},
    {"id": "wc", "nazwa": "WC", "strefa": "USLUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 1.5, "opt_powierzchnia": 2.5, "min_szerokosc": 1.1, "max_proporcja": 2.0, "procent_powierzchni": [0.02, 0.05]},
    {"id": "kotlownia", "nazwa": "Kotlownia", "strefa": "USLUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 4.0, "opt_powierzchnia": 6.0, "min_szerokosc": 1.8, "max_proporcja": 2.2, "procent_powierzchni": [0.05, 0.10]}
  ],
  "sasiedztwo": [
    {"room_a": "wiatrolap", "room_b": "_outside", "connection_type": "entry_door"},
    {"room_a": "hub", "room_b": "wiatrolap", "connection_type": "door"},
    {"room_a": "hub", "room_b": "salon", "connection_type": "opening"},
    {"room_a": "hub", "room_b": "wc", "connection_type": "door"},
    {"room_a": "hub", "room_b": "kotlownia", "connection_type": "door"},
    {"room_a": "salon", "room_b": "kuchnia", "connection_type": "opening"},
    {"room_a": "kuchnia", "room_b": "spizarnia", "connection_type": "door"}
  ]
}
```

> NOTE: use the `strefa` spelling exactly as the other templates use it. Existing templates use `"USŁUGOWA"` (with Ł) — verify against `templates/M1_standard.json` and match it. If the loader maps to the `Strefa` enum, use the same literal the enum accepts. Replace the `USLUGOWA` placeholders above with the project's actual spelling before running tests.

- [ ] **Step 4: Create `templates/house_pietro.json`**

```json
{
  "id": "house_pietro",
  "nazwa": "Dom jednorodzinny — pietro",
  "typ_mieszkania": "DOM_PIETRO",
  "source": "authored",
  "pokoje": [
    {"id": "hub", "nazwa": "Hol/podest", "strefa": "KOMUNIKACJA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 5.0, "opt_powierzchnia": 8.0, "min_szerokosc": 2.5, "max_proporcja": 2.5, "procent_powierzchni": [0.07, 0.15]},
    {"id": "sypialnia_1", "nazwa": "Sypialnia 1", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 1, "preferowana_orientacja": ["south", "east"], "min_powierzchnia": 12.0, "opt_powierzchnia": 16.0, "min_szerokosc": 2.8, "max_proporcja": 2.0, "procent_powierzchni": [0.16, 0.26]},
    {"id": "sypialnia_2", "nazwa": "Sypialnia 2", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 2, "preferowana_orientacja": [], "min_powierzchnia": 10.0, "opt_powierzchnia": 13.0, "min_szerokosc": 2.6, "max_proporcja": 2.0, "procent_powierzchni": [0.13, 0.22]},
    {"id": "sypialnia_3", "nazwa": "Sypialnia 3", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 3, "preferowana_orientacja": [], "min_powierzchnia": 9.0, "opt_powierzchnia": 12.0, "min_szerokosc": 2.5, "max_proporcja": 2.0, "procent_powierzchni": [0.12, 0.20]},
    {"id": "lazienka", "nazwa": "Lazienka", "strefa": "USLUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 4.0, "opt_powierzchnia": 5.0, "min_szerokosc": 1.8, "max_proporcja": 2.0, "procent_powierzchni": [0.06, 0.10]},
    {"id": "garderoba", "nazwa": "Garderoba", "strefa": "USLUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.5, "opt_powierzchnia": 4.0, "min_szerokosc": 1.2, "max_proporcja": 2.5, "procent_powierzchni": [0.03, 0.07]}
  ],
  "sasiedztwo": [
    {"room_a": "hub", "room_b": "sypialnia_1", "connection_type": "door"},
    {"room_a": "hub", "room_b": "sypialnia_2", "connection_type": "door"},
    {"room_a": "hub", "room_b": "sypialnia_3", "connection_type": "door"},
    {"room_a": "hub", "room_b": "lazienka", "connection_type": "door"},
    {"room_a": "hub", "room_b": "garderoba", "connection_type": "door"}
  ]
}
```

> Same `strefa`-spelling note as Task 2 Step 3. The `lazienka` `opt_powierzchnia`/`max` must respect the F2 ≤ 5 m² cap (the solver enforces `WT_MAX_AREA`; keep template values ≤ 5).

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_house_templates.py -q`
Expected: PASS (3 passed). If `test_house_templates_not_selected_for_apartments` fails, `select_templates` is matching `DOM_*` types — add a guard in `select_templates` to skip ids starting with `house_` for `M*` requests (smallest fix).

- [ ] **Step 6: Commit**

```bash
git add templates/house_parter.json templates/house_pietro.json tests/test_house_templates.py
git commit -m "feat(stage4): single-family house templates (parter + pietro)"
```

---

### Task 3: `core/house_layout.py` orchestrator

**Files:**
- Create: `core/house_layout.py`
- Test: `tests/test_house_layout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_house_layout.py
from core.house_layout import generate_house
from shapely.geometry import Polygon


def test_generates_both_storeys_with_full_program():
    poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])  # 99 m²/storey
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2)
    assert layout.parter_rooms, "parter must have rooms"
    assert layout.pietro_rooms, "pietro must have rooms"
    parter_ids = {r.spec.id for r in layout.parter_rooms}
    pietro_ids = {r.spec.id for r in layout.pietro_rooms}
    assert {"salon", "kuchnia", "wc", "kotlownia"} <= parter_ids
    assert {"sypialnia_1", "sypialnia_2", "sypialnia_3", "lazienka"} <= pietro_ids


def test_staircase_core_identical_on_both_storeys():
    poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2)
    # The hub on each storey must contain the same stair core rectangle.
    sc = layout.stair_core  # (x, y, w, h) metres, bbox-relative
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        hub = next(r for r in rooms if "hub" in r.spec.id)
        hb = hub.polygon.bounds
        assert hb[0] <= sc[0] + 0.05 and hb[2] >= sc[0] + sc[2] - 0.05
        assert hb[1] <= sc[1] + 0.05 and hb[3] >= sc[1] + sc[3] - 0.05


def test_too_small_footprint_returns_clear_failure_not_crash():
    poly = Polygon([(0, 0), (5, 0), (5, 4), (0, 4)])  # 20 m² — too small
    layout = generate_house(poly, entry_point=(2.5, 0.0), num_storeys=2)
    assert layout.ok is False
    assert layout.message  # human-readable reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_house_layout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.house_layout'`.

- [ ] **Step 3: Implement `core/house_layout.py`**

```python
"""Two-storey single-family house layout (Phase 1).

Reserves a staircase core and runs the proven Stage 4 CP-SAT solver once per
storey (parter template, then pietro template) with the SAME reserved core, so
the staircase is vertically aligned by construction. See
docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.models import Room
from core.template_selector import load_all_templates

# Staircase core footprint (metres). U/L stair fits ~2.5 x 3.0 m.
STAIR_W = 2.5
STAIR_H = 3.0
# Minimum footprint per storey to fit the full program.
MIN_STOREY_AREA = 60.0


@dataclass
class TwoStoreyLayout:
    ok: bool = True
    message: str = ""
    parter_rooms: list[Room] = field(default_factory=list)
    pietro_rooms: list[Room] = field(default_factory=list)
    stair_core: tuple[float, float, float, float] = (0.0, 0.0, STAIR_W, STAIR_H)
    boundary: object = None


def _template(tid: str):
    return next((t for t in load_all_templates() if t.id == tid), None)


def _entry_side(bbox, entry_point) -> str:
    minx, miny, maxx, maxy = bbox
    ex, ey = entry_point
    d = {
        "south": abs(ey - miny),
        "north": abs(maxy - ey),
        "west": abs(ex - minx),
        "east": abs(maxx - ex),
    }
    return min(d, key=d.get)


def _reserve_core(bbox, entry_point) -> tuple[float, float, float, float]:
    """Place the stair core against the entry wall, centred on the entry x/y,
    in bbox-relative metres."""
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw = min(STAIR_W, W * 0.45)
    sh = min(STAIR_H, H * 0.45)
    ex = entry_point[0] - minx
    ey = entry_point[1] - miny
    side = _entry_side(bbox, entry_point)
    if side in ("south", "north"):
        cx = min(max(ex - sw / 2, 0.0), W - sw)
        cy = 0.0 if side == "south" else H - sh
    else:
        cy = min(max(ey - sh / 2, 0.0), H - sh)
        cx = 0.0 if side == "west" else W - sw
    return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))


def generate_house(
    polygon: Polygon,
    entry_point: tuple[float, float],
    num_storeys: int = 2,
    time_limit_s: float = 30.0,
) -> TwoStoreyLayout:
    if polygon.area < MIN_STOREY_AREA:
        return TwoStoreyLayout(
            ok=False,
            message=(
                f"Obrys {polygon.area:.0f} m2 za maly na program domu "
                f"(min ~{MIN_STOREY_AREA:.0f} m2/kondygnacje)."
            ),
        )

    boundary = analyze_boundary(polygon, entry_point=entry_point)
    core = _reserve_core(boundary.bbox, entry_point)

    parter_tpl = _template("house_parter")
    pietro_tpl = _template("house_pietro")
    if parter_tpl is None or pietro_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonow domu (house_parter/house_pietro).")

    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s, reserved_core=core)
    r_pietro = solve_cpsat(pietro_tpl, boundary, time_limit_s=time_limit_s, reserved_core=core)

    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(
            ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core,
            boundary=boundary,
        )

    return TwoStoreyLayout(
        ok=True,
        parter_rooms=r_parter.rooms,
        pietro_rooms=r_pietro.rooms,
        stair_core=core,
        boundary=boundary,
    )
```

> Verify `analyze_boundary(polygon, entry_point=...)`'s exact signature against `core/boundary_analyzer.py:186` before running; pass the same arguments the Stage 4 apartment flow uses. If `analyze_boundary` needs wall-type info, pass the default (all-FACADE) the way the Stage 4 "load outline" path does.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_house_layout.py -q`
Expected: PASS (3 passed). If a storey solve returns INFEASIBLE on 11×9, loosen the stair-core size (the `* 0.45` clamps) or the template `min_powierzchnia` values, then re-run — do NOT weaken F-rules (B3).

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py tests/test_house_layout.py
git commit -m "feat(stage4): house_layout.py — 2-storey SFH generator with aligned staircase"
```

---

### Task 4: Headless smoke + eyeball viz (temporary)

**Files:**
- Create: `notebooks/sfh_house_smoke.py` (temporary eyeball aid; proper render is Plan 3)

- [ ] **Step 1: Write the smoke script**

```python
# notebooks/sfh_house_smoke.py
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
from core.house_layout import generate_house

poly = Polygon([(0, 0), (11, 0), (11, 9), (0, 9)])
layout = generate_house(poly, entry_point=(5.5, 0.0))
print("ok:", layout.ok, "| stair_core:", layout.stair_core)
print("parter:", [(r.spec.id, round(r.area, 1)) for r in layout.parter_rooms])
print("pietro:", [(r.spec.id, round(r.area, 1)) for r in layout.pietro_rooms])

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
for ax, rooms, title in ((axes[0], layout.parter_rooms, "PARTER"), (axes[1], layout.pietro_rooms, "PIETRO")):
    for r in rooms:
        x, y = r.polygon.exterior.xy
        ax.fill(x, y, alpha=0.4, edgecolor="black")
        c = r.polygon.centroid
        ax.text(c.x, c.y, r.spec.id, ha="center", fontsize=7)
    sc = layout.stair_core
    ax.add_patch(plt.Rectangle((sc[0], sc[1]), sc[2], sc[3], fill=False, edgecolor="red", linewidth=2))
    ax.set_title(title); ax.set_aspect("equal")
fig.savefig("notebooks/output/sfh_house_smoke.png", dpi=110, bbox_inches="tight")
print("-> notebooks/output/sfh_house_smoke.png")
```

- [ ] **Step 2: Run it and eyeball the PNG (B8)**

Run: `venv/bin/python -m notebooks.sfh_house_smoke`
Expected: prints `ok: True`, both storeys list all program rooms, and `notebooks/output/sfh_house_smoke.png` shows a sensible parter + piętro with the red stair rectangle at the SAME position on both panels.

- [ ] **Step 3: Commit**

```bash
git add notebooks/sfh_house_smoke.py
git commit -m "chore(stage4): headless smoke for 2-storey SFH layout"
```

---

## Self-review notes

- **Spec coverage:** §3 templates → Task 2; §4 stair mechanism → Task 1 + Task 3 (`_reserve_core` + `reserved_core`); §6 `house_layout.py` → Task 3; §7/§8 success criteria + tests → Tasks 1/3 tests + Task 4 smoke. Furniture (§5) and viz/UI (§6 UI rows) are intentionally Plan 2 / Plan 3.
- **Placeholder scan:** the only soft spots are the two "verify exact spelling / signature" notes (strefa enum literal; `analyze_boundary` args). These are explicit verification steps, not hidden TODOs — the executor confirms against the cited file before running.
- **Type consistency:** `reserved_core` is `(x,y,w,h)` metres bbox-relative everywhere (Task 1 constraint, Task 3 `_reserve_core`, tests). `solve_cpsat(template, boundary, ...)` argument order matches the verified signature. `CpsatResult.rooms` / `Room.spec.id` / `Room.polygon` used consistently.
