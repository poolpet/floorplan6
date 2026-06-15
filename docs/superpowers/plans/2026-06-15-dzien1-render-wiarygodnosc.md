# Dzień 1 — Wiarygodność renderu (klamp mebli + poché ścian) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zabić dwa największe „fake tells" widoczne na renderach domów: meble wychodzące poza pokój oraz brak grubości ścian (rzut czyta się jak diagram, nie jak rzut architektoniczny).

**Architecture:** Dwie niezależne zmiany. (1) Defensywny klamp mebli **u źródła** (`core/furniture.py`), tak by RENDER i (w przyszłości) AC jadły tę samą sklampowaną geometrię — żaden mebel nie wystaje poza pokój-rodzica. (2) Warstwa poché ścian w `viz/plan_renderer.py` — czysto geometryczny wielokąt ścian (obrys − pokoje skurczone o pół grubości) rysowany jako szara masa; open-plan strefa dzienna scalona, więc bez ściany salon↔kuchnia.

**Tech Stack:** Python 3.10+, Shapely (geometria), matplotlib (render), pytest (TDD).

**Z czego wynika ten plan:** spec `docs/superpowers/specs/2026-06-15-reguly-nie-1to1-plan-tygodnia-design.md`, sekcja „Dzień 1". Wnioski wizualne audytu: meble (łóżka/szafy) straddle granic pokoi = #1 sygnał „wygenerowane"; ściany jako 1px kreski = „diagram vs plan".

---

## File Structure

- `core/furniture.py` — **modify**: nowa funkcja `clamp_furniture(...)`, wpięcie w `furnish_rooms`.
- `tests/test_furniture.py` — **modify**: testy klampa.
- `viz/plan_renderer.py` — **modify**: helpery `_wall_poche_polygon`, `_polygon_patch`, `_draw_walls`; wpięcie w `render_floor_plan` i `_draw_storey`; bump zorder etykiety pokoju.
- `tests/test_wall_poche.py` — **create**: test geometryczny `_wall_poche_polygon`.

Zasada: każda zmiana → `pytest` (PASS) → commit. Po obu zadaniach: bramka wizualna (re-render) + checkpoint z Dawidem (to jest część Dnia 2 w specu, ale render robimy teraz).

---

## Task 1: Klamp mebli do pokoju-rodzica (1a)

Defensywna gwarancja: po rozstawieniu mebli odrzucamy każdy mebel, którego pole leży istotnie poza poligonem pokoju (`room_id`). Poprawnie postawione meble (w 100% wewnątrz) przechodzą bez zmian — zerowe ryzyko regresji istniejących testów (one już asertują `container.contains`). Mebel-uciekinier → usunięty + warning (do diagnozy root-cause później).

**Files:**
- Modify: `core/furniture.py` (dodać funkcję po `place_furniture`, ~linia 158; wpiąć w `furnish_rooms` przed `return`, ~linia 151-152)
- Test: `tests/test_furniture.py`

- [ ] **Step 1: Napisz failing test (klamp usuwa mebel wystający + zachowuje wewnętrzny)**

W `tests/test_furniture.py` dopisz na końcu pliku (helper `_room`, `box`, `Furniture` już zaimportowane u góry):

```python
def test_clamp_drops_piece_straddling_wall():
    from core.furniture import clamp_furniture
    room = _room("sypialnia_1", Strefa.NOCNA, 4.0, 3.5)        # poligon (0,0)–(4,3.5)
    inside = Furniture("bed", box(0.2, 0.2, 1.8, 2.2), "sypialnia_1", "Łóżko")
    straddle = Furniture("wardrobe", box(3.5, 1.0, 4.6, 3.0), "sypialnia_1", "Szafa")  # wystaje 0.6 m za x=4
    kept, warns = clamp_furniture([inside, straddle], [room])
    assert inside in kept
    assert straddle not in kept
    assert warns and "sypialnia_1" in warns[0]


def test_clamp_keeps_correctly_placed_furniture():
    from core.furniture import clamp_furniture
    room = _room("salon", Strefa.DZIENNA, 5.0, 4.0)
    fs = furnish_rooms([room]).furniture
    kept, warns = clamp_furniture(fs, [room])
    assert kept == fs and not warns


def test_furnish_rooms_output_is_clamped():
    # furnish_rooms ma już zwracać meble po klampie (render/AC jedzą to samo)
    room = _room("sypialnia_1", Strefa.NOCNA, 4.0, 3.5)
    container = room.polygon.buffer(1e-6)
    for f in furnish_rooms([room]).furniture:
        assert container.contains(f.polygon), f"{f.piece_type} wystaje poza pokój po furnish_rooms"
```

- [ ] **Step 2: Uruchom test — ma FAILować**

Run: `pytest tests/test_furniture.py::test_clamp_drops_piece_straddling_wall -v`
Expected: FAIL — `ImportError: cannot import name 'clamp_furniture'`.

- [ ] **Step 3: Zaimplementuj `clamp_furniture` w `core/furniture.py`**

Dodaj zaraz po funkcji `place_furniture` (po ~linii 158):

```python
def clamp_furniture(furniture: list, rooms: list, area_tol: float = 0.02):
    """Odrzuć meble wystające istotnie poza poligon pokoju-rodzica.

    Gwarancja defensywna: render i (w przyszłości) eksport AC dostają tę samą
    geometrię, w której ŻADEN mebel nie straddle'uje ściany. Mebel w 100% wewnątrz
    przechodzi bez zmian; mebel z nadmiarem pola > max(1e-6, area_tol·pole) →
    usunięty + warning. Zwraca (kept, warnings).
    """
    by_id = {r.spec.id: r.polygon for r in rooms if r.polygon is not None}
    kept, warns = [], []
    for f in furniture:
        room_poly = by_id.get(f.room_id)
        if room_poly is None:                       # brak pokoju → zostaw (nie nasza sprawa)
            kept.append(f)
            continue
        inside = room_poly.buffer(1e-9).intersection(f.polygon).area
        outside = f.polygon.area - inside
        if outside <= max(1e-6, area_tol * f.polygon.area):
            kept.append(f)
        else:
            warns.append(f"{f.room_id}: mebel {f.piece_type} wystaje poza pokój — usunięto")
    return kept, warns
```

- [ ] **Step 4: Wepnij klamp w `furnish_rooms` (źródło prawdy)**

W `furnish_rooms`, znajdź końcówkę (po `_place_dining`, ~linia 151-152):

```python
    # stół jadalny w otwartej strefie dziennej (styk salon↔kuchnia) — po pokojach
    furniture += _place_dining(rooms, furniture, door_zones)
    return FurnishResult(furniture=furniture, warnings=warnings)
```

Zamień na:

```python
    # stół jadalny w otwartej strefie dziennej (styk salon↔kuchnia) — po pokojach
    furniture += _place_dining(rooms, furniture, door_zones)
    # klamp defensywny: żaden mebel nie straddle'uje ściany (render i AC = ta sama geometria)
    furniture, clamp_warns = clamp_furniture(furniture, rooms)
    warnings.extend(clamp_warns)
    return FurnishResult(furniture=furniture, warnings=warnings)
```

- [ ] **Step 5: Uruchom testy — mają PASSować (łącznie z całym furniture)**

Run: `pytest tests/test_furniture.py -v`
Expected: PASS (3 nowe + wszystkie istniejące zielone — poprawnie stawiane meble są w 100% wewnątrz, więc klamp ich nie rusza).

- [ ] **Step 6: Commit**

```bash
git add core/furniture.py tests/test_furniture.py
git commit -m "feat(stage4): klamp mebli do pokoju-rodzica (render/AC = ta sama geometria)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Poché ścian w rendererze (1b)

Czysto geometryczny wielokąt ścian = `obrys − unia(pokoje skurczone o pół grubości)` + osobny grubszy pierścień zewnętrzny. Rysowany jako szara masa nad wypełnieniem pokoi, pod meblami/etykietami. Strefa dzienna scalona przed liczeniem → brak ściany salon↔kuchnia (spójne z istniejącym open-plan). Testowalny rdzeń = `_wall_poche_polygon` (sama geometria); wpięcie do rysunku weryfikuje bramka wizualna.

**Files:**
- Create: `tests/test_wall_poche.py`
- Modify: `viz/plan_renderer.py` (import `Path`; helpery; wpięcie w `render_floor_plan` ~linia 69 i `_draw_storey` ~linia 255; bump zorder etykiety w `_draw_room` ~linia 461)

- [ ] **Step 1: Napisz failing test geometryczny**

Utwórz `tests/test_wall_poche.py`:

```python
"""Poché ścian — geometryczny rdzeń (viz/plan_renderer._wall_poche_polygon)."""
from shapely.geometry import box, Point

from viz.plan_renderer import _wall_poche_polygon


def test_wall_poche_has_seam_between_two_rooms():
    boundary = box(0, 0, 6, 4)
    left = box(0, 0, 3, 4)
    right = box(3, 0, 6, 4)
    wall = _wall_poche_polygon(boundary, [left, right], w_ext=0.30, w_int=0.12)
    assert wall.area > 0
    assert boundary.buffer(1e-6).contains(wall)
    # punkt na wewnętrznej fudze (x=3) leży w ścianie
    assert wall.buffer(1e-9).contains(Point(3.0, 2.0))
    # środek każdego pokoju NIE leży w ścianie (to wnętrze, nie ściana)
    assert not wall.contains(Point(1.5, 2.0))
    assert not wall.contains(Point(4.5, 2.0))


def test_wall_poche_exterior_ring_present():
    boundary = box(0, 0, 6, 4)
    room = box(0, 0, 6, 4)                       # jeden pokój = cały obrys
    wall = _wall_poche_polygon(boundary, [room], w_ext=0.30, w_int=0.12)
    # bez wewnętrznych fug zostaje sam pierścień zewnętrzny — punkt przy krawędzi w ścianie,
    # środek wolny
    assert wall.buffer(1e-9).contains(Point(0.10, 2.0))
    assert not wall.contains(Point(3.0, 2.0))
```

- [ ] **Step 2: Uruchom test — ma FAILować**

Run: `pytest tests/test_wall_poche.py -v`
Expected: FAIL — `ImportError: cannot import name '_wall_poche_polygon'`.

- [ ] **Step 3: Dodaj import `Path` na górze `viz/plan_renderer.py`**

Znajdź (linie 14-17):

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from shapely.geometry import Polygon
```

Zamień na:

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from matplotlib.path import Path as MplPath
from shapely.geometry import Polygon
from shapely.ops import unary_union
```

- [ ] **Step 4: Dodaj helpery poché (po stałych `STREFA_EDGE_COLORS`, ~linia 36)**

```python
# Poché ścian (MVP credibility): grubość zewn./wewn. w metrach + barwa masy ściany.
WALL_EXT = 0.30
WALL_INT = 0.12
POCHE_COLOR = "#9E9E9E"


def _wall_poche_polygon(boundary_poly, room_polys, w_ext: float = WALL_EXT,
                        w_int: float = WALL_INT):
    """Wielokąt masy ścian: (obrys − unia pokoi skurczonych o w_int/2) ∪ pierścień zewn. w_ext.

    Pokoje stykają się (F1=100%), więc każdy skurcza się o w_int/2 → między dwoma
    sąsiadami zostaje fuga w_int (ściana działowa); przy obrysie zostaje pierścień,
    pogrubiony osobno do w_ext (ściana zewnętrzna).
    """
    shrunk = []
    for p in room_polys:
        geoms = p.geoms if p.geom_type == "MultiPolygon" else [p]
        for g in geoms:
            s = g.buffer(-w_int / 2.0)
            if not s.is_empty:
                shrunk.append(s)
    inner = unary_union(shrunk) if shrunk else boundary_poly
    walls = boundary_poly.difference(inner)
    ext_ring = boundary_poly.difference(boundary_poly.buffer(-w_ext))
    return unary_union([walls, ext_ring])


def _polygon_patch(geom, **kw):
    """matplotlib PathPatch z wielokąta Shapely (z dziurami → wnętrza pokoi przebijają)."""
    verts, codes = [], []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.coords)
            if len(cs) < 3:
                continue
            verts.extend(cs)
            codes.append(MplPath.MOVETO)
            codes.extend([MplPath.LINETO] * (len(cs) - 2))
            codes.append(MplPath.CLOSEPOLY)
    return mpatches.PathPatch(MplPath(verts, codes), **kw)


def _draw_walls(ax, boundary_poly, rooms):
    """Narysuj masę ścian (poché). Strefa dzienna scalona → bez ściany salon↔kuchnia."""
    if boundary_poly is None:
        return
    polys = [r.polygon for r in rooms if r.polygon is not None]
    if not polys:
        return
    day = [r.polygon for r in rooms
           if r.polygon is not None and r.spec.strefa == Strefa.DZIENNA]
    other = [r.polygon for r in rooms
             if r.polygon is not None and r.spec.strefa != Strefa.DZIENNA]
    merged = other + ([unary_union(day)] if len(day) >= 2 else day)
    wall = _wall_poche_polygon(boundary_poly, merged)
    if wall.is_empty:
        return
    ax.add_patch(_polygon_patch(wall, facecolor=POCHE_COLOR, edgecolor="none", zorder=2.6))
```

- [ ] **Step 5: Uruchom test geometryczny — ma PASSować**

Run: `pytest tests/test_wall_poche.py -v`
Expected: PASS (2 testy zielone).

- [ ] **Step 6: Wepnij `_draw_walls` w `render_floor_plan` (mieszkania)**

Znajdź (linie 68-75):

```python
    for room in plan.rooms:
        _draw_room(ax, room, furniture_polys=furn_by_room.get(room.spec.id))

    # Meble + drzwi + okna (MVP)
    if furniture:
        _draw_furniture(ax, furniture)
```

Wstaw wywołanie `_draw_walls` między pętlą pokoi a meblami:

```python
    for room in plan.rooms:
        _draw_room(ax, room, furniture_polys=furn_by_room.get(room.spec.id))

    # Masa ścian (poché) — nad pokojami, pod meblami/etykietami
    _draw_walls(ax, getattr(plan.boundary, "polygon", None), plan.rooms)

    # Meble + drzwi + okna (MVP)
    if furniture:
        _draw_furniture(ax, furniture)
```

- [ ] **Step 7: Wepnij `_draw_walls` w `_draw_storey` (domy 2-kond.)**

Znajdź (linie ~254-255, tuż przed `_draw_furniture`):

```python
    else:
        _draw_stair(ax, core_abs)
    _draw_furniture(ax, furniture)
```

Zamień na:

```python
    else:
        _draw_stair(ax, core_abs)
    _draw_walls(ax, getattr(boundary, "polygon", None), rooms)
    _draw_furniture(ax, furniture)
```

- [ ] **Step 8: Podnieś zorder etykiety pokoju nad poché (`_draw_room`, ~linia 461)**

Znajdź:

```python
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold",
            color="#333333",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      alpha=0.7, edgecolor="none"))
```

Zamień na (dodaj `zorder=3.6`):

```python
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold",
            color="#333333", zorder=3.6,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      alpha=0.7, edgecolor="none"))
```

- [ ] **Step 9: Uruchom automatyczny render-test (nie może crashować)**

Run: `pytest tests/test_wall_poche.py tests/test_two_storey_render.py -v`
Expected: PASS (poché nie wywraca renderu domu 2-kond.).

- [ ] **Step 10: Commit**

```bash
git add viz/plan_renderer.py tests/test_wall_poche.py
git commit -m "feat(viz): poché ścian w rendererze (rzut zamiast diagramu); strefa dzienna scalona

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Bramka końcowa Dnia 1 (weryfikacja przed „done")

- [ ] **Step A: Pełny zielony zestaw testów dotkniętych modułów**

Run: `pytest tests/test_furniture.py tests/test_wall_poche.py tests/test_two_storey_render.py -v`
Expected: wszystko PASS.

- [ ] **Step B: Bramka wizualna — re-render umeblowanego domu**

Run: `python notebooks/sfh_furnished_smoke.py`
Expected: zapis PNG (do `rzuty/...` lub `notebooks/output/...`). Otwórz wynik i sprawdź wzrokowo:
1. żaden mebel nie wychodzi poza swój pokój (klamp),
2. ściany mają grubość (szara masa), rzut czyta się „jak rzut",
3. brak ściany na styku salon↔kuchnia (open-plan zachowany),
4. etykiety pokoi i meble są czytelne nad poché.

⚠️ Jeśli warstwy się zasłaniają (etykieta/mebel pod ścianą) → dostrój `zorder` (poché 2.6 < etykieta 3.6 < meble 4 < drzwi 5 < okna 6) lub grubość `WALL_EXT/WALL_INT`. To normalna iteracja wizualna — test geometryczny i tak chroni rdzeń.

- [ ] **Step C: Checkpoint z Dawidem** — pokaż „przed/po" (stary render vs nowy). Dopiero po jego OK ruszamy Dzień 2 (schody zabiegowe + higiena + smoke AC).

---

## Self-Review (autor planu)

- **Pokrycie specu (Dzień 1):** 1a klamp mebli → Task 1 ✓; 1b poché ścian → Task 2 ✓. Higiena labeli / schody zabiegowe / smoke AC = **Dzień 2** (osobny plan, świadomie poza tym dokumentem).
- **Placeholdery:** brak — każdy krok ma realny kod i komendę.
- **Spójność typów:** `clamp_furniture(furniture, rooms)` zwraca `(list, list[str])`, używane w `furnish_rooms` jako `furniture, clamp_warns`. `Furniture` ma `.room_id`, `.polygon`, `.piece_type` (zgodne z dataclass w `furniture.py:79`). `_wall_poche_polygon(boundary_poly, room_polys, w_ext, w_int)` — sygnatura zgodna w teście i wpięciu (`_draw_walls`). `room.spec.strefa`/`Strefa.DZIENNA` zgodne z `core/models`.
- **Ryzyko regresji:** istniejące testy mebli już asertują `container.contains` → klamp ich nie rusza. Poché nie zmienia geometrii pokoi (tylko warstwa rysunku).
