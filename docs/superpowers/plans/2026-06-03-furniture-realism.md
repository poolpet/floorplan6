# Realistic window-aware furniture (Phase 4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `core/furniture.py` from generic greedy packing to window-aware, semantically-arranged placement (bedroom / day-zone / bathroom) with Neufert clearances and best-effort warnings, keeping full backward-compatibility.

**Architecture:** Extend the existing engine in place. Add a `boundary` argument that yields per-room window-wall flags; dispatch the three "living" room types to semantic placers that reuse the proven `_place_fixed`/`_place_linear`/`_sweep`/`_valid` primitives + clearance zones; utility rooms keep the generic `_furnish_room`. `boundary=None` degrades to today's behaviour. A `furnish_rooms()→FurnishResult` carries warnings; `place_furniture()` stays a thin list-returning wrapper.

**Tech Stack:** Python 3.10+, Shapely (`box`, polygons), pytest. Run: `./venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-03-furniture-realism-design.md`

**Notes for the implementer:**
- Furniture is placed in ABSOLUTE coords (room.polygon.bounds), walls named `S`(miny)/`N`(maxy)/`W`(minx)/`E`(maxx).
- Reuse, don't reinvent: `_place_fixed(region,a,b,placed,zones)` tries S/N/W/E walls + both orientations; `_place_linear(region,depth,cap,placed,zones)` runs a counter along a wall; `_sweep`/`_valid` are the low-level helpers; `_infer_door_zones(rooms)` gives door keep-clear rects. `region` = `(minx+INSET, miny+INSET, maxx-INSET, maxy-INSET)`.
- The renderer `viz/plan_renderer._draw_furniture` is GENERIC (draws any `Furniture` polygon + label) — NO renderer change needed for new piece types.
- `_detect_facade_sides(boundary)` (in `core/cpsat_solver.py`) returns `{"south","east","north","west": bool}` (all True for a plain rectangle).

---

## File Structure
- `core/furniture.py` — MODIFY: `FurnishResult`, `furnish_rooms`, `_room_window_walls`, wall-aware variants of `_place_fixed` (a `prefer_walls`/`avoid_walls` filter), `_furnish_bedroom`, `_furnish_day_zone`, `_furnish_bathroom`, clearance helper, key-piece warnings. Keep `_furnish_room`, primitives, `FURNITURE_SETS`.
- `tests/test_furniture.py` — MODIFY: extend with window-aware, semantic, clearance, warning, back-compat tests.

---

## Task 1: Scaffold — `FurnishResult` + `furnish_rooms` + `boundary` param (back-compat, no behaviour change)

**Files:**
- Modify: `core/furniture.py`
- Test: `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_furniture.py`:
```python
def test_furnish_rooms_backcompat_shape():
    from core.furniture import furnish_rooms, place_furniture, FurnishResult
    hub = _room("hub", Strefa.KOMUNIKACJA, 1.5, 3.0, x=0.0)
    syp = _room("sypialnia_1", Strefa.NOCNA, 3.0, 4.0, x=3.0)
    res = furnish_rooms([hub, syp])               # bez boundary
    assert isinstance(res, FurnishResult)
    assert res.warnings == []
    # place_furniture nadal zwraca listę identyczną z res.furniture
    assert [f.piece_type for f in place_furniture([hub, syp])] == [f.piece_type for f in res.furniture]
```
(Reuse the file's existing `_room(...)` helper; check its signature at the top of `tests/test_furniture.py` and match it.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_furnish_rooms_backcompat_shape -q`
Expected: FAIL (ImportError: `furnish_rooms`/`FurnishResult` undefined).

- [ ] **Step 3: Implement the scaffold**

In `core/furniture.py`, add after the `Furniture` dataclass:
```python
@dataclass
class FurnishResult:
    """Wynik umeblowania: meble + ostrzeżenia (np. pokój za mały na kluczowy mebel)."""
    furniture: list  # list[Furniture]
    warnings: list   # list[str]
```
Refactor `place_furniture` into `furnish_rooms` + a thin wrapper:
```python
def furnish_rooms(rooms: list[Room], boundary=None) -> FurnishResult:
    """Rozstaw meble (spec phase 4). boundary=None → bez świadomości okien (back-compat)."""
    door_zones = _infer_door_zones(rooms)
    furniture: list[Furniture] = []
    warnings: list[str] = []
    for room in rooms:
        if room.polygon is None:
            continue
        key = room.spec.id.split("_")[0]
        if key in CIRCULATION_KEYS or key not in FURNITURE_SETS:
            continue
        furniture.extend(_furnish_room(room, key, door_zones.get(room.spec.id, [])))
    return FurnishResult(furniture=furniture, warnings=warnings)


def place_furniture(rooms: list[Room], boundary=None) -> list[Furniture]:
    """Back-compat: płaska lista mebli (bez ostrzeżeń). Patrz furnish_rooms."""
    return furnish_rooms(rooms, boundary).furniture
```

- [ ] **Step 4: Run tests — expect PASS (incl. the whole existing file)**

Run: `./venv/bin/python -m pytest tests/test_furniture.py -q`
Expected: PASS (back-compat preserved — the existing tests still pass against the wrapper).

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): FurnishResult + furnish_rooms scaffold (back-compat place_furniture)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `_room_window_walls` — which room walls are windows

**Files:**
- Modify: `core/furniture.py`
- Test: `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test**
```python
def test_room_window_walls_rectangle():
    from core.furniture import _room_window_walls
    from core.boundary_analyzer import analyze_boundary
    from shapely.geometry import Polygon
    from core.models import Room, RoomSpec, Strefa
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1)
    from shapely.geometry import box
    r = Room(spec=sp, polygon=box(0.0, 4.0, 4.0, 8.0)); r.update_metrics()  # dotyka W (x=0) i N (y=8)
    walls = _room_window_walls(r, b)
    assert walls == {"W", "N"}
    assert _room_window_walls(r, None) == set()   # bez boundary — brak okien
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_room_window_walls_rectangle -q`
Expected: FAIL (`_room_window_walls` undefined).

- [ ] **Step 3: Implement**

In `core/furniture.py` (import at top: `from core.cpsat_solver import _detect_facade_sides`):
```python
def _room_window_walls(room: Room, boundary) -> set:
    """Ściany pokoju (S/N/W/E) leżące na krawędzi-fasadzie obrysu (= potencjalne okna).
    boundary=None lub notch → set() (notch deferred). Tol 5 cm."""
    if boundary is None or getattr(boundary, "notch", None) is not None:
        return set()
    fac = _detect_facade_sides(boundary)
    bx0, by0, bx2, by2 = boundary.bbox
    rx0, ry0, rx1, ry1 = room.polygon.bounds
    t = 0.05
    walls = set()
    if fac["south"] and abs(ry0 - by0) < t: walls.add("S")
    if fac["north"] and abs(ry1 - by2) < t: walls.add("N")
    if fac["west"] and abs(rx0 - bx0) < t: walls.add("W")
    if fac["east"] and abs(rx1 - bx2) < t: walls.add("E")
    return walls
```

- [ ] **Step 4: Run — expect PASS**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_room_window_walls_rectangle -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): _room_window_walls (facade-edge → window walls)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wall-targeted placement primitive `_place_on_wall`

A primitive the semantic placers need: place a fixed piece against a SPECIFIC wall (so we can say "bed against this windowless wall"). Generalises `_place_fixed`.

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test**
```python
def test_place_on_wall_targets_wall():
    from core.furniture import _place_on_wall
    region = (0.0, 0.0, 4.0, 4.0)
    rect = _place_on_wall(region, 1.6, 2.0, "S", [], [])   # wzdłuż S (dół): szer 1.6 w x, głęb 2.0 w y
    assert rect is not None
    b = rect.bounds
    assert abs(b[1] - 0.0) < 1e-9            # przy ścianie S (y=0)
    assert abs((b[2] - b[0]) - 1.6) < 1e-9   # szerokość wzdłuż ściany
    assert abs((b[3] - b[1]) - 2.0) < 1e-9   # głębokość
```

- [ ] **Step 2: Run — expect FAIL** (`_place_on_wall` undefined).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_place_on_wall_targets_wall -q`

- [ ] **Step 3: Implement**
```python
def _place_on_wall(region, along: float, depth: float, wall: str, placed, zones):
    """Połóż prostokąt (along × depth) przy danej ścianie (S/N/W/E) regionu.
    Przesuwa wzdłuż ściany (_sweep) szukając wolnego miejsca. None gdy się nie mieści."""
    rx0, ry0, rx1, ry1 = region
    if wall in ("S", "N"):
        if depth > (ry1 - ry0) + 1e-9 or along > (rx1 - rx0) + 1e-9:
            return None
        y0 = ry0 if wall == "S" else ry1 - depth
        for x0 in _sweep(rx0, rx1, along):
            rect = box(x0, y0, x0 + along, y0 + depth)
            if _valid(rect, placed, zones):
                return rect
    else:  # W / E
        if depth > (rx1 - rx0) + 1e-9 or along > (ry1 - ry0) + 1e-9:
            return None
        x0 = rx0 if wall == "W" else rx1 - depth
        for y0 in _sweep(ry0, ry1, along):
            rect = box(x0, y0, x0 + depth, y0 + along)
            if _valid(rect, placed, zones):
                return rect
    return None
```

- [ ] **Step 4: Run — expect PASS.**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_place_on_wall_targets_wall -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): _place_on_wall (target a specific wall)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Bedroom placer — bed to windowless wall + nightstands + wardrobe

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test** — bed headboard wall must be windowless; nightstands beside the bed.
```python
def test_bedroom_bed_on_windowless_wall():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    from shapely.geometry import Polygon
    # 10x8; sypialnia w prawym-górnym rogu (dotyka N=okno i E=okno; W i S wewnętrzne)
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    from core.models import Room, RoomSpec, Strefa
    from shapely.geometry import box
    sp = RoomSpec(id="sypialnia_1", nazwa="Sypialnia", strefa=Strefa.NOCNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(6.0, 4.0, 10.0, 8.0)); r.update_metrics()  # okna: N, E
    res = furnish_rooms([r], boundary=b)
    bed = next(f for f in res.furniture if f.piece_type == "bed")
    bb = bed.polygon.bounds
    # wezgłowie NIE przy oknie: łóżko nie dosunięte do N (y=8) ani E (x=10)
    assert not (abs(bb[3] - 8.0) < 0.2) , f"łóżko pod oknem N: {bb}"
    assert not (abs(bb[2] - 10.0) < 0.2), f"łóżko pod oknem E: {bb}"
    assert any(f.piece_type == "nightstand" for f in res.furniture), "brak szafki nocnej"
```

- [ ] **Step 2: Run — expect FAIL** (no semantic bedroom placer yet; current greedy ignores windows + has no nightstand logic beyond generic).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_bedroom_bed_on_windowless_wall -q`

- [ ] **Step 3: Implement `_furnish_bedroom` + dispatch**

In `furnish_rooms`, before the generic call, dispatch by key:
```python
        windows = _room_window_walls(room, boundary)
        if key == "sypialnia":
            f, w = _furnish_bedroom(room, windows, door_zones.get(room.spec.id, []))
        else:
            f, w = _furnish_room(room, key, door_zones.get(room.spec.id, [])), []
        furniture.extend(f); warnings.extend(w)
```
(Replace the current `furniture.extend(_furnish_room(...))` line with the dispatch above. `_furnish_room` keeps returning a list; semantic placers return `(list, warnings)`.)

Add the placer (uses `_place_on_wall`; bed on the longest windowless wall; nightstands flank it):
```python
_WALL_OPP = {"S": "N", "N": "S", "W": "E", "E": "W"}

def _wall_len(region, wall):
    rx0, ry0, rx1, ry1 = region
    return (rx1 - rx0) if wall in ("S", "N") else (ry1 - ry0)

def _furnish_bedroom(room: Room, windows: set, zones):
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    bed = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "bed")
    # ściany bez okna, najdłuższa najpierw; gdy wszystkie z oknem → którakolwiek (best-effort)
    cand = [w for w in ("S", "N", "W", "E") if w not in windows] or ["S", "N", "W", "E"]
    cand.sort(key=lambda w: _wall_len(region, w), reverse=True)
    bed_rect = None; bed_wall = None
    for wall in cand:
        bed_rect = _place_on_wall(region, bed.a, bed.b, wall, placed, zones)
        if bed_rect is not None:
            bed_wall = wall; break
    if bed_rect is None:
        warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na łóżko + dojście")
        return out, warn
    placed.append(bed_rect)
    out.append(Furniture("bed", bed_rect, room.spec.id, bed.label))
    # szafki nocne po bokach łóżka (wzdłuż ściany wezgłowia)
    out += _flank_nightstands(bed_rect, bed_wall, region, placed, zones, room.spec.id)
    # szafa na innej ścianie bez okna
    ward = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "wardrobe")
    for wall in cand:
        if wall == bed_wall:
            continue
        wr = _place_on_wall(region, ward.b, ward.a, wall, placed, zones)
        if wr is not None:
            placed.append(wr); out.append(Furniture("wardrobe", wr, room.spec.id, ward.label)); break
    return out, warn
```
Add helpers `_inset` and `_flank_nightstands`:
```python
def _inset(poly):
    minx, miny, maxx, maxy = poly.bounds
    return (minx + INSET, miny + INSET, maxx - INSET, maxy - INSET)

def _flank_nightstands(bed_rect, bed_wall, region, placed, zones, room_id):
    ns = next(p for p in FURNITURE_SETS["sypialnia"] if p.type == "nightstand")
    bx0, by0, bx1, by1 = bed_rect.bounds
    out = []
    if bed_wall in ("S", "N"):                      # łóżko wzdłuż x → szafki po lewej/prawej (x)
        y0 = by0 if bed_wall == "S" else by1 - ns.b
        for x0 in (bx0 - ns.a, bx1):
            rect = box(x0, y0, x0 + ns.a, y0 + ns.b)
            if _valid(rect, placed, zones) and rect.within(box(*region).buffer(1e-6)):
                placed.append(rect); out.append(Furniture("nightstand", rect, room_id, ns.label))
    else:                                           # łóżko wzdłuż y → szafki góra/dół (y)
        x0 = bx0 if bed_wall == "W" else bx1 - ns.b
        for y0 in (by0 - ns.a, by1):
            rect = box(x0, y0, x0 + ns.b, y0 + ns.a)
            if _valid(rect, placed, zones) and rect.within(box(*region).buffer(1e-6)):
                placed.append(rect); out.append(Furniture("nightstand", rect, room_id, ns.label))
    return out
```

- [ ] **Step 4: Run — expect PASS** (bed off the window walls, nightstand present).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_bedroom_bed_on_windowless_wall -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): semantic bedroom — bed to windowless wall + nightstands + wardrobe

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Kitchen — counter + sink under the window

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test** — counter sits on a window wall.
```python
def test_kitchen_counter_under_window():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    from shapely.geometry import Polygon, box
    from core.models import Room, RoomSpec, Strefa
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 3.0, 4.0)); r.update_metrics()  # okna: S (y=0), W (x=0)
    res = furnish_rooms([r], boundary=b)
    counter = next(f for f in res.furniture if f.piece_type == "kitchen_counter")
    cb = counter.polygon.bounds
    on_S = abs(cb[1] - 0.0) < 0.2
    on_W = abs(cb[0] - 0.0) < 0.2
    assert on_S or on_W, f"blat nie pod oknem: {cb}"
```

- [ ] **Step 2: Run — expect FAIL** (generic `_place_linear` ignores windows; may land on an internal wall).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_kitchen_counter_under_window -q`

- [ ] **Step 3: Implement `_furnish_kitchen` + dispatch `key == "kuchnia"`**
```python
def _furnish_kitchen(room: Room, windows: set, zones):
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    counter = next(p for p in FURNITURE_SETS["kuchnia"] if p.type == "kitchen_counter")
    walls = list(windows) or ["S", "N", "W", "E"]            # preferuj ścianę z oknem
    walls.sort(key=lambda w: _wall_len(region, w), reverse=True)
    rect = None
    for wall in walls:
        length = min(counter.b, _wall_len(region, wall))
        if length < 0.5:
            continue
        rect = _place_on_wall(region, length, counter.a, wall, placed, zones)
        if rect is not None:
            break
    if rect is None:
        warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na blat kuchenny")
        return out, warn
    out.append(Furniture("kitchen_counter", rect, room.spec.id, counter.label))
    return out, warn
```
Add `elif key == "kuchnia": f, w = _furnish_kitchen(room, windows, ...)` to the dispatch.

- [ ] **Step 4: Run — expect PASS.**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_kitchen_counter_under_window -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): kitchen counter+sink under the window

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Living — sofa against internal wall, TV opposite, coffee table between

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test** — sofa and TV on opposite walls; coffee table present.
```python
def test_living_sofa_tv_opposite():
    from core.furniture import furnish_rooms, _WALL_OPP
    from core.boundary_analyzer import analyze_boundary
    from shapely.geometry import Polygon, box
    from core.models import Room, RoomSpec, Strefa
    b = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), entry_point=(5, 0))
    sp = RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1)
    r = Room(spec=sp, polygon=box(4.0, 0.0, 10.0, 6.0)); r.update_metrics()
    res = furnish_rooms([r], boundary=b)
    sofa = next(f for f in res.furniture if f.piece_type == "sofa")
    tv = next(f for f in res.furniture if f.piece_type == "tv_unit")
    # sofa i TV na przeciwległych ścianach (środki rozsunięte w jednej osi)
    sc, tc = sofa.polygon.centroid, tv.polygon.centroid
    assert (abs(sc.x - tc.x) > 1.5) or (abs(sc.y - tc.y) > 1.5), "sofa i TV nie naprzeciw siebie"
    assert any(f.piece_type == "coffee_table" for f in res.furniture)
```

- [ ] **Step 2: Run — expect FAIL** (no living placer; generic packs without facing relationship).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_living_sofa_tv_opposite -q`

- [ ] **Step 3: Implement `_furnish_living` + dispatch `key == "salon"`**
```python
def _furnish_living(room: Room, windows: set, zones):
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    sofa = next(p for p in FURNITURE_SETS["salon"] if p.type == "sofa")
    tv = next(p for p in FURNITURE_SETS["salon"] if p.type == "tv_unit")
    coffee = next(p for p in FURNITURE_SETS["salon"] if p.type == "coffee_table")
    # sofa pod ścianą wewnętrzną (nie okno), najdłuższą
    cand = [w for w in ("S", "N", "W", "E") if w not in windows] or ["S", "N", "W", "E"]
    cand.sort(key=lambda w: _wall_len(region, w), reverse=True)
    sofa_rect = sofa_wall = None
    for wall in cand:
        sofa_rect = _place_on_wall(region, sofa.b, sofa.a, wall, placed, zones)
        if sofa_rect is not None:
            sofa_wall = wall; break
    if sofa_rect is None:
        return out, warn   # salon zwykłada się rzadko; brak sofy nie jest "kluczowy" warning
    placed.append(sofa_rect); out.append(Furniture("sofa", sofa_rect, room.spec.id, sofa.label))
    # TV na ścianie naprzeciw sofy (preferuj bez okna)
    opp = _WALL_OPP[sofa_wall]
    tv_rect = _place_on_wall(region, tv.b, tv.a, opp, placed, zones)
    if tv_rect is not None:
        placed.append(tv_rect); out.append(Furniture("tv_unit", tv_rect, room.spec.id, tv.label))
    # stolik kawowy w środku między nimi
    cr = _place_fixed(region, coffee.a, coffee.b, placed, zones)
    if cr is not None:
        placed.append(cr); out.append(Furniture("coffee_table", cr, room.spec.id, coffee.label))
    return out, warn
```
Add `elif key == "salon": f, w = _furnish_living(room, windows, ...)` to the dispatch.

- [ ] **Step 4: Run — expect PASS.**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_living_sofa_tv_opposite -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): living — sofa internal wall, TV opposite, coffee table

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Dining table at the kitchen↔salon junction

The dining table belongs to the OPEN day-zone, placed at the shared edge between `kuchnia` and `salon`. It is not owned by a single room placer, so `furnish_rooms` handles it after per-room placement.

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing test** — a dining table appears near the salon/kuchnia shared edge when both exist and there is room.
```python
def test_dining_table_at_junction():
    from core.furniture import furnish_rooms
    from core.boundary_analyzer import analyze_boundary
    from shapely.geometry import Polygon, box
    from core.models import Room, RoomSpec, Strefa
    b = analyze_boundary(Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), entry_point=(6, 0))
    salon = Room(spec=RoomSpec(id="salon", nazwa="Salon", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=1),
                 polygon=box(0.0, 0.0, 7.0, 8.0)); salon.update_metrics()
    kuch = Room(spec=RoomSpec(id="kuchnia", nazwa="Kuchnia", strefa=Strefa.DZIENNA, wymaga_okna=True, priorytet_fasady=2),
                polygon=box(7.0, 0.0, 12.0, 8.0)); kuch.update_metrics()
    res = furnish_rooms([salon, kuch], boundary=b)
    dt = next((f for f in res.furniture if f.piece_type == "dining_table"), None)
    assert dt is not None, "brak stołu jadalnego"
    # stół blisko wspólnej krawędzi x=7
    assert abs(dt.polygon.centroid.x - 7.0) < 2.5, f"stół daleko od styku: {dt.polygon.bounds}"
```

- [ ] **Step 2: Run — expect FAIL** (no dining table type / no junction logic).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_dining_table_at_junction -q`

- [ ] **Step 3: Implement** — add a `dining_table` Piece + a `_place_dining` pass in `furnish_rooms`.

Add to `FURNITURE_SETS` a standalone piece constant (not in a room set):
```python
DINING_TABLE = Piece("dining_table", "Stół jadalny", 0.9, 1.4, False)
```
At the end of `furnish_rooms`, after the per-room loop, before `return`:
```python
    furniture += _place_dining(rooms, furniture, _infer_door_zones(rooms))
```
Implement (find salon+kuchnia, their shared edge, place the table straddling it in whichever room has room):
```python
def _place_dining(rooms, existing, door_zones):
    salon = next((r for r in rooms if r.spec.id == "salon" and r.polygon), None)
    kuch = next((r for r in rooms if r.spec.id.split("_")[0] == "kuchnia" and r.polygon), None)
    if salon is None or kuch is None:
        return []
    placed_by_room = {}
    for f in existing:
        placed_by_room.setdefault(f.room_id, []).append(f.polygon)
    # spróbuj umieścić stół po stronie SALONU blisko krawędzi z kuchnią; fallback: po stronie kuchni
    for host, other in ((salon, kuch), (kuch, salon)):
        region = _inset(host.polygon)
        zones = door_zones.get(host.spec.id, []) + placed_by_room.get(host.spec.id, [])
        # preferuj środek regionu (stół centralny); _place_fixed wystarcza dla małego stołu
        rect = _place_fixed(region, DINING_TABLE.a, DINING_TABLE.b, [], zones)
        if rect is not None:
            return [Furniture("dining_table", rect, host.spec.id, DINING_TABLE.label)]
    return []   # mała strefa dzienna → bez stołu (best-effort)
```

- [ ] **Step 4: Run — expect PASS.**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_dining_table_at_junction -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): dining table at the kitchen/salon junction (open day-zone)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Bathroom linear placer + Neufert clearances + key-piece warnings

**Files:** Modify `core/furniture.py`; Test `tests/test_furniture.py`

- [ ] **Step 1: Write the failing tests** — bathroom fixtures along one wall; clearance respected; tiny bedroom → warning.
```python
def test_bathroom_fixtures_on_one_wall_and_clear():
    from core.furniture import furnish_rooms
    from shapely.geometry import Polygon, box
    from core.models import Room, RoomSpec, Strefa
    sp = RoomSpec(id="lazienka", nazwa="Łazienka", strefa=Strefa.USLUGOWA, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 2.2, 2.3)); r.update_metrics()  # ~5 m²
    res = furnish_rooms([r], boundary=None)
    types = {f.piece_type for f in res.furniture}
    assert {"bathtub", "washbasin", "toilet"} <= types, f"brak armatury: {types}"
    # brak nakładania między meblami
    fs = res.furniture
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            assert fs[i].polygon.intersection(fs[j].polygon).area < 1e-6


def test_tiny_bedroom_warns_no_bed():
    from core.furniture import furnish_rooms
    from shapely.geometry import box
    from core.models import Room, RoomSpec, Strefa
    sp = RoomSpec(id="sypialnia_2", nazwa="Sypialnia", strefa=Strefa.NOCNA, wymaga_okna=True, priorytet_fasady=2)
    r = Room(spec=sp, polygon=box(0.0, 0.0, 1.5, 1.6)); r.update_metrics()  # 2.4 m² — łóżko się nie zmieści
    res = furnish_rooms([r], boundary=None)
    assert not any(f.piece_type == "bed" for f in res.furniture)
    assert any("łóżko" in w for w in res.warnings), res.warnings
```

- [ ] **Step 2: Run — expect FAIL** (no bathroom semantic placer returning warnings; bedroom warning path from Task 4 already exists but verify the message contains "łóżko").

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_bathroom_fixtures_on_one_wall_and_clear tests/test_furniture.py::test_tiny_bedroom_warns_no_bed -q`

- [ ] **Step 3: Implement `_furnish_bathroom` + clearance zones**

Bathroom placer (place fixtures along walls, prefer the same wall; reuse `_place_fixed`/`_place_on_wall`; emit warning if bathtub or washbasin missing):
```python
def _furnish_bathroom(room: Room, windows: set, zones):
    region = _inset(room.polygon)
    placed, out, warn = [], [], []
    key = room.spec.id.split("_")[0]
    for piece in FURNITURE_SETS[key]:            # lazienka: bathtub, washbasin, toilet
        rect = _place_fixed(region, piece.a, piece.b, placed, zones)
        if rect is not None:
            placed.append(rect); out.append(Furniture(piece.type, rect, room.spec.id, piece.label))
        elif piece.type in ("bathtub", "washbasin"):
            warn.append(f"{room.spec.id} ({room.polygon.area:.1f} m²): brak miejsca na {piece.label.lower()}")
    return out, warn
```
Add `elif key in ("lazienka", "wc"): f, w = _furnish_bathroom(room, windows, ...)` to the dispatch.

For clearances: add a front-clearance strip to `placed`-as-keep-clear when placing key pieces. Minimal v1: add a module constant and extend `_place_on_wall` callers to also reserve a clearance rect. Implement a helper and use it in the bedroom bed + kitchen counter:
```python
CLEARANCE = {"bed": 0.6, "kitchen_counter": 1.2, "toilet": 0.6, "washbasin": 0.6}

def _clearance_zone(rect, wall, depth):
    """Pas dostępu przed meblem (od strony pokoju, przeciwnej do ściany)."""
    x0, y0, x1, y1 = rect.bounds
    if wall == "S":   return box(x0, y1, x1, y1 + depth)
    if wall == "N":   return box(x0, y0 - depth, x1, y0)
    if wall == "W":   return box(x1, y0, x1 + depth, y1)
    if wall == "E":   return box(x0 - depth, y0, x0, y1)
    return None
```
In `_furnish_bedroom`, after appending the bed, add its clearance to `placed` so nightstands/wardrobe keep the access strip clear:
```python
    cz = _clearance_zone(bed_rect, bed_wall, CLEARANCE["bed"])
    if cz is not None: placed.append(cz)
```
(The clearance rect is added to `placed` only as a keep-clear obstacle — it is NOT emitted as Furniture.)

- [ ] **Step 4: Run — expect PASS.**

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_bathroom_fixtures_on_one_wall_and_clear tests/test_furniture.py::test_tiny_bedroom_warns_no_bed -q`

- [ ] **Step 5: Commit**
```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(furniture): bathroom placer + bed/counter clearances + key-piece warnings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Integration — furnish a real generated house + control render + full regression

**Files:** Test `tests/test_furniture.py`; (manual render — no committed code)

- [ ] **Step 1: Write the integration test** — furnish a generated single-storey house, window-aware, no overlaps, no crash.
```python
def test_furnish_generated_single_storey_no_overlap():
    from core.house_layout import generate_house
    from core.furniture import furnish_rooms
    from shapely.geometry import Polygon
    lay = generate_house(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), (5.0, 0.0),
                         num_storeys=1, time_limit_s=30)
    assert lay.ok, lay.message
    res = furnish_rooms(lay.parter_rooms, boundary=lay.boundary)
    assert res.furniture, "nic nie umeblowano"
    # meble mieszczą się w swoich pokojach i się nie nakładają (w obrębie pokoju)
    by_room = {}
    for f in res.furniture:
        by_room.setdefault(f.room_id, []).append(f.polygon)
    for rid, polys in by_room.items():
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                assert polys[i].intersection(polys[j]).area < 1e-6, f"nakładanie w {rid}"
    # bed istnieje i nie jest pod oknem (w którejś sypialni — single-storey ma sypialnia_1)
    beds = [f for f in res.furniture if f.piece_type == "bed"]
    assert beds, "brak łóżka w domu"
```

- [ ] **Step 2: Run — expect PASS** (all placers integrated; may surface a real bug → fix per systematic-debugging before proceeding).

Run: `./venv/bin/python -m pytest tests/test_furniture.py::test_furnish_generated_single_storey_no_overlap -q`

- [ ] **Step 3: Full furniture regression + back-compat**

Run: `./venv/bin/python -m pytest tests/test_furniture.py -q`
Expected: ALL PASS (new semantic tests + the original back-compat tests).

- [ ] **Step 4: Control render (B8 — visual check)**

```bash
MPLBACKEND=Agg PYTHONPATH=. ./venv/bin/python - <<'PY'
from pathlib import Path
from shapely.geometry import Polygon
from core.house_layout import generate_house
from core.furniture import furnish_rooms
from viz.plan_renderer import render_rooms_only, render_two_storey
OUT = Path("rzuty/renders_s20"); OUT.mkdir(parents=True, exist_ok=True)
l1 = generate_house(Polygon([(0,0),(10,0),(10,10),(0,10)]), (5.0,0.0), num_storeys=1, time_limit_s=30)
fr = furnish_rooms(l1.parter_rooms, boundary=l1.boundary)
print("single warnings:", fr.warnings)
f = render_rooms_only(l1.parter_rooms, l1.boundary, "Parterowiec 10x10 — umeblowany", show=False)
# narysuj meble na istniejących osiach
from viz.plan_renderer import _draw_furniture
_draw_furniture(f.axes[0], fr.furniture)
f.savefig(OUT/"4_parterowiec_umeblowany.png", dpi=150, bbox_inches="tight")
print("saved", OUT/"4_parterowiec_umeblowany.png")
PY
```
Then Read the PNG and eyeball: beds off windows, counter under a window, sofa↔TV opposite, dining near the kitchen/salon edge, fixtures along a bathroom wall. (If `render_rooms_only` already draws furniture via a param, prefer that; otherwise the `_draw_furniture` overlay above works.)

- [ ] **Step 5: Commit**
```bash
git add tests/test_furniture.py
git commit -m "test(furniture): integration on generated house (window-aware, no overlap)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes
- **Spec coverage:** §1 window-awareness = Task 2; §2 semantic placers = Tasks 4 (bedroom), 5 (kitchen), 6 (living), 7 (dining), 8 (bathroom); §3 clearances = Task 8; §4 best-effort+warnings = Tasks 4/8 + FurnishResult (Task 1); §5 renderer (no change — generic) + tests = each task + Task 9. D1–D4 covered.
- **Back-compat:** Task 1 keeps `place_furniture` list-returning; `boundary=None`/utility rooms keep `_furnish_room`; original `test_furniture` stays green (verified Task 1 Step 4, Task 9 Step 3).
- **Type consistency:** semantic placers return `(list[Furniture], list[str])`; `_furnish_room` returns `list` (wrapped `, []` in dispatch); `_place_on_wall(region, along, depth, wall, placed, zones)`; `Piece` fields `type,label,a,b,linear`; `Furniture(piece_type, polygon, room_id, label)`.
- **Provisional:** clearance values (0.6/1.2/0.45), dining table size (0.9×1.4) — Neufert start values, tunable; Task 9 render is the realism check.
- **Risk (open day-zone):** Task 7 degrades to placing the table host-side near the edge; if neither salon nor kuchnia has room → no table (best-effort).
- **Deferred:** utility semantic placement, notched footprints, ArchiCAD export.
```
