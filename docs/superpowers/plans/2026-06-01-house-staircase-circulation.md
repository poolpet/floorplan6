# House Staircase + Circulation (Approach A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. NOTE: this is geometry work whose quality is judged visually — inline execution (so renders can be eyeballed between steps) is preferable to fully-delegated subagents.

**Goal:** Make the generated house staircase compact, adaptively shaped (straight for elongated outlines, U for square), and set back from the entry behind the hall — instead of a fat 7.5 m² block glued to the front wall.

**Architecture:** Approach A (localized, no solver change): rewrite `core/house_layout.py::_reserve_core` to compute an aspect-adaptive, area-capped stair rectangle and place it in the middle depth band (set back from the entry); gently lower the hub `opt_powierzchnia` in the two house templates. The staircase stays a `reserved_core` rectangle that the hub room must contain (unchanged solver contract).

**Tech Stack:** Python 3.13, Shapely, OR-Tools CP-SAT (unchanged), matplotlib (Agg), pytest.

**Rules guard (CLAUDE.md):** No change to `cpsat_solver`/`validator`/WT caps. F2 (bathroom ≤5, WC ≤3), F3 (mins), F4 (hub ≤15%) must still hold; vertical staircase alignment preserved (same `reserved_core` feeds both storeys). M1-M5 untouched. B1: if A's renders aren't credible, fall back to Approach B (separate stair room) — out of scope here.

---

## File Structure

- **Modify** `core/house_layout.py` — add `_stair_core_dims(W, H)` helper + new stair constants; rewrite `_reserve_core` (adaptive geometry + set-back position). Keep `STAIR_W`/`STAIR_H` (still used by the `TwoStoreyLayout` default).
- **Modify** `templates/house_parter.json`, `templates/house_pietro.json` — lower hub `opt_powierzchnia` (gentle; keeps feasibility).
- **Create** `tests/test_house_staircase.py` — geometry + position unit tests + one integration guard.
- **Modify** `docs/STATE.md`, `NEXT_SESSION.md` — sync after visual review.

---

## Task 1: Adaptive stair-core geometry helper

**Files:**
- Modify: `core/house_layout.py` (constants block near line 20; add helper near `_reserve_core`)
- Test: `tests/test_house_staircase.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_house_staircase.py`:

```python
"""Adaptive staircase core geometry + position (Approach A, Session 16)."""
from core.house_layout import _stair_core_dims, STAIR_MAX_AREA


def test_square_outline_gives_u_stair():
    sw, sh, kind = _stair_core_dims(8.0, 8.0)
    assert kind == "u"
    assert abs(sw - sh) < 1e-6            # zwarty kwadrat
    assert 2.0 <= sw <= 2.6
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_wide_outline_gives_straight_run_along_x():
    sw, sh, kind = _stair_core_dims(11.0, 6.0)
    assert kind == "straight"
    assert sw > sh                        # bieg wzdłuż dłuższej osi (X)
    assert sh <= 1.3                      # wąski bieg
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_deep_outline_gives_straight_run_along_y():
    sw, sh, kind = _stair_core_dims(6.0, 11.0)
    assert kind == "straight"
    assert sh > sw                        # bieg wzdłuż dłuższej osi (Y)
    assert sw <= 1.3
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_core_area_never_exceeds_cap_or_40pct():
    for W, H in [(8, 8), (11, 6), (6, 11), (9, 7), (7.8, 7.8), (12, 7)]:
        sw, sh, _ = _stair_core_dims(W, H)
        assert sw * sh <= STAIR_MAX_AREA + 1e-6
        assert sw <= 0.40 * W + 1e-6
        assert sh <= 0.40 * H + 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_house_staircase.py -q`
Expected: FAIL — `ImportError: cannot import name '_stair_core_dims'` (and `STAIR_MAX_AREA`).

- [ ] **Step 3: Add constants + helper**

In `core/house_layout.py`, replace this exact block:

```python
STAIR_W = 2.5
STAIR_H = 3.0
MIN_STOREY_AREA = 60.0
```

with:

```python
STAIR_W = 2.5
STAIR_H = 3.0
MIN_STOREY_AREA = 60.0

# Adaptive staircase core (Approach A — spec 2026-06-01)
STAIR_RUN_W = 1.1            # szerokość biegu prostego (m)
STAIR_RUN_LEN = 4.2         # docelowa długość biegu prostego (m)
STAIR_U_SIDE = 2.4          # bok klatki U/zabiegowej (m)
STAIR_MAX_AREA = 6.0        # sufit pola schodów (m²)
STAIR_ASPECT_THRESHOLD = 1.4  # powyżej → bieg prosty, poniżej → U
STAIR_SETBACK = 1.3         # cofnięcie rdzenia od ściany wejścia (m)


def _stair_core_dims(W: float, H: float) -> tuple[float, float, str]:
    """(sw, sh, kind) — geometria rdzenia schodów wg proporcji obrysu.

    Wydłużony obrys (aspect > próg) → bieg prosty: wąski, długi wzdłuż dłuższej osi.
    Kwadratowy → U/zabiegowe: zwarty kwadrat. Pole ≤ STAIR_MAX_AREA oraz ≤ 0.40·W × 0.40·H.
    """
    cap_w = 0.40 * W
    cap_h = 0.40 * H
    long_dim = max(W, H)
    short_dim = min(W, H)
    aspect = long_dim / short_dim if short_dim > 0 else 1.0
    if aspect > STAIR_ASPECT_THRESHOLD:
        run_len = min(STAIR_RUN_LEN, 0.6 * long_dim)
        if W >= H:                       # dłuższa oś = X → bieg poziomy
            sw, sh = run_len, STAIR_RUN_W
        else:                            # dłuższa oś = Y → bieg pionowy
            sw, sh = STAIR_RUN_W, run_len
        kind = "straight"
    else:
        side = min(STAIR_U_SIDE, cap_w, cap_h)
        sw = sh = side
        kind = "u"
    sw = min(sw, cap_w)
    sh = min(sh, cap_h)
    if sw * sh > STAIR_MAX_AREA:
        scale = (STAIR_MAX_AREA / (sw * sh)) ** 0.5
        sw *= scale
        sh *= scale
    return round(sw, 3), round(sh, 3), kind
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_house_staircase.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py tests/test_house_staircase.py
git commit -m "feat(stage4): adaptive staircase core geometry (straight vs U by outline aspect)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Set-back position in `_reserve_core`

**Files:**
- Modify: `core/house_layout.py` (`_reserve_core`)
- Test: `tests/test_house_staircase.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_house_staircase.py`:

```python
from core.house_layout import _reserve_core, STAIR_SETBACK


def _core_for(W, H, entry):
    return _reserve_core((0.0, 0.0, W, H), entry)


def test_core_is_set_back_from_south_entry():
    cx, cy, sw, sh = _core_for(8.0, 8.0, (4.0, 0.0))
    assert cy > 0.5                       # NIE przy ścianie wejścia (dawniej cy=0)
    assert cy <= STAIR_SETBACK + 0.3
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_is_set_back_from_west_entry():
    cx, cy, sw, sh = _core_for(8.0, 8.0, (0.0, 4.0))
    assert cx > 0.5                       # cofnięte od ściany zachodniej
    assert cx <= STAIR_SETBACK + 0.3
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_inside_bbox_for_all_entries():
    for entry in [(4.0, 0.0), (4.0, 8.0), (0.0, 4.0), (8.0, 4.0)]:
        cx, cy, sw, sh = _core_for(8.0, 8.0, entry)
        assert cx >= -1e-6 and cy >= -1e-6
        assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_house_staircase.py -q`
Expected: FAIL — `test_core_is_set_back_from_south_entry` asserts `cy > 0.5`, but the current `_reserve_core` sets `cy = 0.0` for a south entry.

- [ ] **Step 3: Rewrite `_reserve_core`**

In `core/house_layout.py`, replace this exact block:

```python
def _reserve_core(bbox, entry_point) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw = min(STAIR_W, W * 0.40)
    sh = min(STAIR_H, H * 0.40)
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
```

with:

```python
def _reserve_core(bbox, entry_point) -> tuple[float, float, float, float]:
    """Rdzeń klatki schodowej (x, y, w, h), bbox-relative.

    Geometria adaptacyjna (`_stair_core_dims`), pozycja: cofnięta od ściany wejścia
    o STAIR_SETBACK (środkowy pas głębokości), wyśrodkowana w okolicy wejścia.
    """
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw, sh, _kind = _stair_core_dims(W, H)
    ex = entry_point[0] - minx
    ey = entry_point[1] - miny
    side = _entry_side(bbox, entry_point)
    if side in ("south", "north"):
        cx = min(max(ex - sw / 2, 0.0), W - sw)              # bias ku x wejścia
        if side == "south":
            cy = min(STAIR_SETBACK, max(0.0, H - sh))        # cofnij od frontu
        else:
            cy = max(H - STAIR_SETBACK - sh, 0.0)
    else:
        cy = min(max(ey - sh / 2, 0.0), H - sh)              # bias ku y wejścia
        if side == "west":
            cx = min(STAIR_SETBACK, max(0.0, W - sw))
        else:
            cx = max(W - STAIR_SETBACK - sw, 0.0)
    return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_house_staircase.py -q`
Expected: PASS — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py tests/test_house_staircase.py
git commit -m "feat(stage4): set staircase core back from entry (mid-depth, not front wall)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Gentle hub tuning in house templates

**Files:**
- Modify: `templates/house_parter.json`, `templates/house_pietro.json`
- Test: `tests/test_house_staircase.py` (append integration guard)

Rationale: with a compact, set-back core the hub no longer needs to puff toward `opt 9`. Lowering only `opt_powierzchnia` nudges the scorer toward a tighter hall without touching the hard bands (`min_powierzchnia`, `procent_powierzchni`, contain-core) — so feasibility is preserved.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_house_staircase.py`:

```python
def test_generate_house_hub_compact_and_feasible():
    from shapely.geometry import Polygon
    from core.house_layout import generate_house
    from core.models import Strefa
    layout = generate_house(Polygon([(0, 0), (8, 0), (8, 8), (0, 8)]), (4.0, 0.0))
    assert layout.ok, layout.message
    usable = 64.0
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        hub = next(r for r in rooms
                   if r.spec.id == "hub" and r.spec.strefa == Strefa.KOMUNIKACJA)
        assert hub.area <= 0.15 * usable + 1e-6        # F4: hub ≤ 15% usable
        assert hub.area >= _stair_core_dims(8.0, 8.0)[0] * _stair_core_dims(8.0, 8.0)[1] - 1e-6
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `python3 -m pytest tests/test_house_staircase.py::test_generate_house_hub_compact_and_feasible -q`
Expected: PASS already (the hub `procent_powierzchni` max is 0.14 < 0.15, so F4 holds even before tuning). This test is a regression guard that the template edit in Step 3 keeps `generate_house` feasible and F4-compliant. If it does NOT pass now, STOP and report (means the staircase change broke feasibility — investigate before tuning).

- [ ] **Step 3: Lower the hub `opt_powierzchnia` in both templates**

In `templates/house_parter.json`, inside the `"id": "hub"` room object, replace:

```json
      "min_powierzchnia": 6.0,
      "opt_powierzchnia": 9.0,
```

with:

```json
      "min_powierzchnia": 6.0,
      "opt_powierzchnia": 7.5,
```

In `templates/house_pietro.json`, inside the `"id": "hub"` room object, replace:

```json
      "min_powierzchnia": 4.0,
      "opt_powierzchnia": 6.0,
```

with:

```json
      "min_powierzchnia": 4.0,
      "opt_powierzchnia": 5.5,
```

- [ ] **Step 4: Re-run the integration guard + the staircase suite**

Run: `python3 -m pytest tests/test_house_staircase.py -q`
Expected: PASS — 8 passed (the 7 geometry/position tests + the integration guard; `generate_house` still `ok`, hub ≤ 15%).

- [ ] **Step 5: Commit**

```bash
git add templates/house_parter.json templates/house_pietro.json tests/test_house_staircase.py
git commit -m "feat(stage4): tighten house hub opt area to suit compact staircase core

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Visual validation (8×8 / 6×11 / 9×7) + suite + docs sync

**Files:**
- Modify: `docs/STATE.md`, `NEXT_SESSION.md`

- [ ] **Step 1: Render the three validation footprints**

Run (produces PNGs into the gitignored `notebooks/output/`):

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && python3 -c "
import matplotlib; matplotlib.use('Agg')
from shapely.geometry import Polygon
from core.house_layout import generate_house, _reserve_core
from viz.house_preview import render_house_figure
for W,H,tag in [(8,8,'8x8'),(6,11,'6x11'),(9,7,'9x7')]:
    layout = generate_house(Polygon([(0,0),(W,0),(W,H),(0,H)]), (W/2,0.0))
    core = _reserve_core((0,0,W,H),(W/2,0.0))
    print('%s ok=%s core(x,y,w,h)=%s area=%.2f'%(tag, layout.ok, core, core[2]*core[3]))
    if layout.ok:
        render_house_figure(layout, with_furniture=False,
            title='Dom %dx%d — schody'%(W,H),
            save_path='notebooks/output/sfh_stairs_%s.png'%tag, show=False)
"
```

Expected: all three print `ok=True`; stair-core area ~4–6 m²; `core[1]` (y) ≈ 1.3 for the 8×8/9×7 south-entry cases (set back, not 0). PNGs written.

- [ ] **Step 2: VISUAL REVIEW GATE (human)**

Open `notebooks/output/sfh_stairs_8x8.png`, `_6x11.png`, `_9x7.png`. Confirm with Dawid:
- staircase is compact and set back from the entry (behind the wiatrołap/hol), not glued to the front wall;
- 8×8/9×7 use a U-ish (square) core; 6×11 uses a straight (narrow, long) run;
- salon keeps a facade; circulation is less fragmented than before.

If the result is not credible (e.g. hub still bloated or circulation badly fragmented), STOP — this is the B1 trigger to consider Approach B (separate stair room). Do NOT iterate blindly more than twice.

- [ ] **Step 3: Run the fast full suite (no regressions)**

Run: `python3 -m pytest tests -q -p no:cacheprovider -k "not subdivision and not 600 and not 800"`
Expected: 0 failed; new `tests/test_house_staircase.py` (8) included; existing house/furniture/apartment tests still green.

- [ ] **Step 4: Update `docs/STATE.md`**

Add to the Session 16 block: staircase + circulation improved (Approach A) — `_reserve_core` now adaptive (`_stair_core_dims`: straight for elongated, U for square; area ~4–6 m²) and set back from the entry; house hub `opt` lowered; new `tests/test_house_staircase.py` (8). Note the GAP remains deprioritized (footprint artifact) and Approach B is the fallback if A proved insufficient.

- [ ] **Step 5: Update `NEXT_SESSION.md`**

In the "STAN po sesji 16" section, note the staircase/circulation fix (Approach A) is in; remaining next steps unchanged (furniture realism, twin/terraced, AC export); Approach B noted as fallback.

- [ ] **Step 6: Commit**

```bash
git add docs/STATE.md NEXT_SESSION.md
git commit -m "docs(stage4): house staircase + circulation (Approach A) done — STATE/NEXT_SESSION sync

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes (covered)

- **Spec §5.1 adaptive geometry** → Task 1 (`_stair_core_dims`). **§5.2 set-back position** → Task 2 (`_reserve_core`). **§5.3 hub tuning** → Task 3. **§5.5 validation (8×8/6×11/9×7 + F2/F3/align + suite)** → Task 4 (renders + integration guard + fast suite). **§4 no solver change** → file list touches only `house_layout.py` + 2 template JSONs + tests + docs. **§8 out of scope** (Approach B, furniture, GAP) → not implemented; B flagged as the B1 fallback in Task 4 Step 2.
- **Placeholder scan:** no TBD/TODO; the one human gate (Task 4 Step 2 visual review) is explicit and bounded by the B1 rule.
- **Type/name consistency:** `_stair_core_dims(W, H) -> (sw, sh, kind)`, `STAIR_MAX_AREA`, `STAIR_SETBACK`, `_reserve_core(bbox, entry_point)` used consistently across Tasks 1–4. `kind ∈ {"straight","u"}`. Constants `STAIR_RUN_W/RUN_LEN/U_SIDE/ASPECT_THRESHOLD` defined in Task 1, used only there.
- **F2/vertical-alignment:** unchanged — same `reserved_core` still feeds both storeys; solver/validator/WT caps untouched (verified by file list).
