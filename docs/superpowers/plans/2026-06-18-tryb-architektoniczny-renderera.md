# Tryb architektoniczny renderera (#1-4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać do renderera flagę `architectural=False` (opt-in), która produkuje rzut „jak rysunek architektoniczny" zamiast diagramu: osie OFF, białe wnętrza, bez legendy, schody czarne.

**Architecture:** Flaga przepływa przez publiczne funkcje renderera (`render_house_figure`, `render_two_storey`, `render_floor_plan`) do wewnętrznych (`_draw_storey`, `_draw_room`, `_draw_boundary`, `_draw_stair*`). Każda zmiana bramkowana `if architectural:`; default = stara ścieżka kolorowa bajt-w-bajt. Podpięcie `architectural=True` tylko w benchmarku.

**Tech Stack:** Python 3.13, matplotlib (Agg w testach), shapely, pytest. Plik główny: `viz/plan_renderer.py` (+ `viz/house_preview.py`, `notebooks/reference_benchmark.py`).

## Global Constraints

- Zmiany TYLKO w `viz/` + `notebooks/reference_benchmark.py`. ZERO zmian core/solver/geometrii.
- Default `architectural=False` → ścieżka kolorowa NIEzmieniona (istniejące testy renderera zielone).
- Testy: `import matplotlib; matplotlib.use("Agg")` na górze (jak `tests/test_two_storey_render.py`).
- Komendy uruchamiać z roota repo z `PYTHONPATH=. venv/bin/python -m pytest`.
- Każdy commit kończ: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Kolory: białe wnętrze = `"white"`, krawędź pokoju arch = `"#BDBDBD"` lw 0.6, schody arch = `"#212121"`. Stałe stref `STREFA_COLORS`/`STREFA_EDGE_COLORS` (linie 25-37) NIEzmienione.

---

### Task 1: `_draw_room` — białe wnętrza w trybie architektonicznym

**Files:**
- Modify: `viz/plan_renderer.py` (`_draw_room`, linie 548-566)
- Test: `tests/test_architectural_mode.py` (Create)

**Interfaces:**
- Produces: `_draw_room(ax, room, draw_edge=True, furniture_polys=None, architectural=False)` — gdy `architectural=True`: facecolor `"white"` (alpha 1.0), krawędź `"#BDBDBD"` lw 0.6 (lub `"none"` gdy `draw_edge=False`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_architectural_mode.py
"""Tryb architektoniczny renderera (#1-4): osie off, białe wnętrza, bez legendy, schody czarne."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from shapely.geometry import box, Polygon

from core.models import Room, RoomSpec, Strefa
from viz.plan_renderer import _draw_room, STREFA_COLORS

ZONE_RGB = {tuple(round(v, 3) for v in mcolors.to_rgb(c)) for c in STREFA_COLORS.values()}


def _room(room_id, strefa, w, h, x=0.0, y=0.0):
    spec = RoomSpec(id=room_id, nazwa=room_id, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _fill_rgbs(ax):
    return [tuple(round(v, 3) for v in p.get_facecolor()[:3])
            for p in ax.patches if isinstance(p, mpatches.Polygon)]


def test_draw_room_architectural_is_white_not_zone_color():
    fig, ax = plt.subplots()
    _draw_room(ax, _room("salon", Strefa.DZIENNA, 4, 3), architectural=True)
    rgbs = _fill_rgbs(ax)
    assert (1.0, 1.0, 1.0) in rgbs, f"brak białego wypełnienia: {rgbs}"
    assert not (ZONE_RGB & set(rgbs)), f"kolor strefy w trybie arch: {rgbs}"
    plt.close(fig)


def test_draw_room_default_keeps_zone_color():
    fig, ax = plt.subplots()
    _draw_room(ax, _room("salon", Strefa.DZIENNA, 4, 3), architectural=False)
    assert ZONE_RGB & set(_fill_rgbs(ax)), "default musi mieć kolor strefy"
    plt.close(fig)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: FAIL — `TypeError: _draw_room() got an unexpected keyword argument 'architectural'`

- [ ] **Step 3: Implement — dodaj `architectural` do `_draw_room`**

Zamień nagłówek + blok kolorów/wypełnienia (548-566). Obecnie:

```python
def _draw_room(ax: plt.Axes, room: Room, draw_edge: bool = True, furniture_polys=None):
    """..."""
    if room.polygon is None:
        return

    color = STREFA_COLORS.get(room.spec.strefa, "#E0E0E0")
    edge_color = STREFA_EDGE_COLORS.get(room.spec.strefa, "#333333") if draw_edge else "none"
    lw = 1.5 if draw_edge else 0.0

    # Obsługa MultiPolygon (L-kształtne pokoje po carving)
    if room.polygon.geom_type == "MultiPolygon":
        for geom in room.polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=lw)
    else:
        x, y = room.polygon.exterior.xy
        ax.fill(x, y, alpha=0.6, facecolor=color, edgecolor=edge_color, linewidth=lw)
```

Na:

```python
def _draw_room(ax: plt.Axes, room: Room, draw_edge: bool = True, furniture_polys=None,
               architectural: bool = False):
    """..."""
    if room.polygon is None:
        return

    if architectural:                                   # tryb rzutu: białe wnętrze, cienka szara krawędź
        color, fill_alpha = "white", 1.0
        edge_color = "#BDBDBD" if draw_edge else "none"
        lw = 0.6 if draw_edge else 0.0
    else:
        color, fill_alpha = STREFA_COLORS.get(room.spec.strefa, "#E0E0E0"), 0.6
        edge_color = STREFA_EDGE_COLORS.get(room.spec.strefa, "#333333") if draw_edge else "none"
        lw = 1.5 if draw_edge else 0.0

    # Obsługa MultiPolygon (L-kształtne pokoje po carving)
    if room.polygon.geom_type == "MultiPolygon":
        for geom in room.polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=fill_alpha, facecolor=color, edgecolor=edge_color, linewidth=lw)
    else:
        x, y = room.polygon.exterior.xy
        ax.fill(x, y, alpha=fill_alpha, facecolor=color, edgecolor=edge_color, linewidth=lw)
```

(Reszta funkcji — etykieta, anchor — bez zmian; `docstring` zachowaj istniejący.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add viz/plan_renderer.py tests/test_architectural_mode.py
git commit -m "feat(viz): _draw_room białe wnętrza w trybie architektonicznym

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Ścieżka domu 2-kond. — flaga przez `render_two_storey` → `_draw_storey` (osie off + bez legendy + białe + day-edge)

**Files:**
- Modify: `viz/plan_renderer.py` (`render_two_storey` 215-244; `_draw_storey` 270-346)
- Modify: `viz/house_preview.py` (`render_house_figure` 54-65)
- Test: `tests/test_architectural_mode.py` (Append)

**Interfaces:**
- Consumes: `_draw_room(..., architectural=)` z Task 1.
- Produces: `render_two_storey(..., architectural=False)`, `_draw_storey(..., architectural=False)`, `render_house_figure(..., architectural=False)`. Gdy `architectural=True`: `ax.axis("off")`, brak `ax.legend`, day-zone union edge `"#616161"`.

- [ ] **Step 1: Write the failing test (append do `tests/test_architectural_mode.py`)**

```python
from core.house_layout import TwoStoreyLayout
from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey


def _house_layout():
    parter = [
        _room("salon", Strefa.DZIENNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
        _room("kuchnia", Strefa.DZIENNA, 6.5, 2.0, 0.0, 3.0),
    ]
    pietro = [
        _room("sypialnia_1", Strefa.NOCNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
        _room("lazienka", Strefa.USLUGOWA, 6.5, 2.0, 0.0, 3.0),
    ]
    return TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                           stair_core=(4.0, 0.0, 2.5, 3.0), boundary=None)


def test_two_storey_architectural_axes_off_no_legend_white(tmp_path):
    fig = render_two_storey(_house_layout(), architectural=True,
                            save_path=tmp_path / "arch.png", show=False)
    for ax in fig.axes:
        assert ax.get_legend() is None, "tryb arch: brak legendy"
        assert ax.axison is False, "tryb arch: osie wyłączone"
        assert not (ZONE_RGB & set(_fill_rgbs(ax))), "tryb arch: brak kolorów stref"
    plt.close(fig)


def test_two_storey_default_unchanged(tmp_path):
    fig = render_two_storey(_house_layout(), save_path=tmp_path / "color.png", show=False)
    ax = fig.axes[0]
    assert ax.get_legend() is not None, "default: legenda obecna"
    assert ax.axison is True, "default: osie włączone"
    assert ZONE_RGB & set(_fill_rgbs(ax)), "default: kolory stref obecne"
    plt.close(fig)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: FAIL — `TypeError: render_two_storey() got an unexpected keyword argument 'architectural'`

- [ ] **Step 3a: `_draw_storey` — sygnatura + przekazanie do `_draw_room`**

Nagłówek (270): `def _draw_storey(ax, rooms, boundary, core_abs, furniture, title, low_strips=None):`
→ `def _draw_storey(ax, rooms, boundary, core_abs, furniture, title, low_strips=None, architectural=False):`

W pętli pokoi (305-306) dołóż `architectural`:
```python
    for room in rooms:
        _draw_room(ax, room, draw_edge=(room not in day_rooms),
                   furniture_polys=furn_by_room.get(room.spec.id), architectural=architectural)
```

- [ ] **Step 3b: `_draw_storey` — day-zone union edge szary w trybie arch**

Obecnie (311): `edge = STREFA_EDGE_COLORS.get(Strefa.DZIENNA, "#333333")`
→ `edge = "#616161" if architectural else STREFA_EDGE_COLORS.get(Strefa.DZIENNA, "#333333")`

- [ ] **Step 3c: `_draw_storey` — legenda + osie bramkowane**

Zamień blok legendy (329-338) i osi (345-346). Obecnie:
```python
    ax.set_title(title, fontsize=13, fontweight="bold")
    legend_patches = [
        mpatches.Patch(facecolor=color, edgecolor="black", label=strefa.display)
        for strefa, color in STREFA_COLORS.items()
        if any(r.spec.strefa == strefa for r in rooms)
    ]
    if furniture:
        legend_patches.append(mpatches.Patch(facecolor="#A1887F", edgecolor="#4E342E", label="Meble"))
    # legenda POD panelem (poziomo) — nie zasłania etykiet pokoi (MVP credibility)
    ax.legend(handles=legend_patches, loc="upper center", bbox_to_anchor=(0.5, -0.10),
              ncol=len(legend_patches) or 1, fontsize=8, framealpha=0.9)

    bx0, by0, bx1, by1 = bnds
    margin = max(bx1 - bx0, by1 - by0) * 0.05
    ax.set_xlim(bx0 - margin, bx1 + margin)
    ax.set_ylim(by0 - margin, by1 + margin)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
```
Na:
```python
    ax.set_title(title, fontsize=13, fontweight="bold")
    if not architectural:
        legend_patches = [
            mpatches.Patch(facecolor=color, edgecolor="black", label=strefa.display)
            for strefa, color in STREFA_COLORS.items()
            if any(r.spec.strefa == strefa for r in rooms)
        ]
        if furniture:
            legend_patches.append(mpatches.Patch(facecolor="#A1887F", edgecolor="#4E342E", label="Meble"))
        # legenda POD panelem (poziomo) — nie zasłania etykiet pokoi (MVP credibility)
        ax.legend(handles=legend_patches, loc="upper center", bbox_to_anchor=(0.5, -0.10),
                  ncol=len(legend_patches) or 1, fontsize=8, framealpha=0.9)

    bx0, by0, bx1, by1 = bnds
    margin = max(bx1 - bx0, by1 - by0) * 0.05
    ax.set_xlim(bx0 - margin, bx1 + margin)
    ax.set_ylim(by0 - margin, by1 + margin)
    ax.set_aspect("equal")
    if architectural:
        ax.axis("off")
    else:
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
```

- [ ] **Step 3d: `render_two_storey` — sygnatura + przekazanie do obu paneli**

Nagłówek (215-223): dołóż `architectural: bool = False` przed `figsize` (lub po — byle keyword). Następnie zamień oba wywołania `_draw_storey` (239-244):
```python
    _draw_storey(ax_p, layout.parter_rooms, layout.boundary, core_abs,
                 parter_furniture or [], "PARTER", architectural=architectural)
    _draw_storey(ax_g, layout.pietro_rooms, layout.boundary, core_abs,
                 pietro_furniture or [],
                 "PODDASZE" if strips else "PIĘTRO",
                 low_strips=strips, architectural=architectural)
```

- [ ] **Step 3e: `render_house_figure` — przekazanie flagi (`viz/house_preview.py`)**

Nagłówek (54-55): dołóż `architectural: bool = False`. W `return render_two_storey(...)` (58-65) dołóż `architectural=architectural`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run renderer regression (default nietknięty)**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_two_storey_render.py tests/test_house_preview.py -q`
Expected: PASS (wszystkie istniejące — ścieżka kolorowa bajt-w-bajt)

- [ ] **Step 6: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add viz/plan_renderer.py viz/house_preview.py tests/test_architectural_mode.py
git commit -m "feat(viz): tryb architektoniczny dla domu 2-kond. (osie off + bez legendy + białe)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Schody czarne w trybie architektonicznym

**Files:**
- Modify: `viz/plan_renderer.py` (`_draw_storey` wywołania schodów 320/322; `_draw_winder_in_room` 375-412; `_draw_stair_in_room` 415-444; `_draw_stair` 447-468)
- Test: `tests/test_architectural_mode.py` (Append)

**Interfaces:**
- Produces: `_draw_stair(ax, core_abs, architectural=False)`, `_draw_stair_in_room(ax, schody, hol, architectural=False)`, `_draw_winder_in_room(ax, schody, hol, architectural=False)` — gdy `architectural=True`: kolor `"#212121"` zamiast `"#D32F2F"`/`"#B71C1C"`.

- [ ] **Step 1: Write the failing test (append)**

```python
RED = {"#D32F2F", "#B71C1C"}


def _stair_layout(stair_kind=None):
    # layout z OSOBNYM pokojem 'schody' (ścieżka _draw_stair_in_room)
    parter = [
        _room("salon", Strefa.DZIENNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", Strefa.KOMUNIKACJA, 2.0, 3.0, 4.0, 0.0),
        _room("schody", Strefa.KOMUNIKACJA, 2.5, 3.0, 6.0, 0.0),
    ]
    if stair_kind is not None:
        parter[-1].stair_kind = stair_kind
    pietro = [_room("sypialnia_1", Strefa.NOCNA, 4.0, 6.0, 0.0, 0.0)]
    return TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                           stair_core=(6.0, 0.0, 2.5, 3.0), boundary=None)


def _line_colors(ax):
    return {ln.get_color() for ln in ax.lines}


def test_stairs_black_in_architectural():
    # ścieżka _draw_stair (brak pokoju 'schody' → core overlay)
    fig = render_two_storey(_house_layout(), architectural=True, show=False)
    assert not (RED & _line_colors(fig.axes[0])), "schody czerwone w trybie arch (_draw_stair)"
    plt.close(fig)
    # ścieżka _draw_stair_in_room (pokój 'schody', bieg prosty)
    fig2 = render_two_storey(_stair_layout(), architectural=True, show=False)
    assert not (RED & _line_colors(fig2.axes[0])), "schody czerwone w trybie arch (_draw_stair_in_room)"
    plt.close(fig2)


def test_stairs_red_in_default():
    fig = render_two_storey(_house_layout(), show=False)  # default kolor
    assert RED & _line_colors(fig.axes[0]), "default: schody czerwone (regresja-lock)"
    plt.close(fig)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -k stairs -q`
Expected: FAIL — `test_stairs_black_in_architectural` (czerwień nadal obecna)

- [ ] **Step 3a: `_draw_stair` — kolor z flagi (447-468)**

Nagłówek: `def _draw_stair(ax, core_abs):` → `def _draw_stair(ax, core_abs, architectural=False):`
Na początku ciała (po `sx, sy, sw, sh = core_abs`) dodaj:
```python
    color = "#212121" if architectural else "#D32F2F"
```
Następnie zamień WSZYSTKIE literalne `"#D32F2F"` w tej funkcji (edgecolor Rectangle 451, `color=` w 456/458/463/465) na `color`, a `color="#B71C1C"` w `ax.text` (467) na `color=color`.

- [ ] **Step 3b: `_draw_stair_in_room` — kolor z flagi (415-444)**

Nagłówek: `def _draw_stair_in_room(ax, schody, hol):` → `def _draw_stair_in_room(ax, schody, hol, architectural=False):`
Linia 424 `color = "#B71C1C"` → `color = "#212121" if architectural else "#B71C1C"`.
W gałęzi winder (419-421) przekaż flagę:
```python
    if getattr(schody, "stair_kind", None) == "u":
        _draw_winder_in_room(ax, schody, hol, architectural=architectural)
        return
```

- [ ] **Step 3c: `_draw_winder_in_room` — kolor z flagi (375-382)**

Nagłówek: `def _draw_winder_in_room(ax, schody, hol):` → `def _draw_winder_in_room(ax, schody, hol, architectural=False):`
Linia 382 `color = "#B71C1C"` → `color = "#212121" if architectural else "#B71C1C"`.

- [ ] **Step 3d: `_draw_storey` — przekaż flagę do schodów (320/322)**

```python
    if schody is not None and schody.polygon is not None:
        hol = next((r for r in rooms if r.spec.id == "hub"), None)
        _draw_stair_in_room(ax, schody, hol, architectural=architectural)
    else:
        _draw_stair(ax, core_abs, architectural=architectural)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add viz/plan_renderer.py tests/test_architectural_mode.py
git commit -m "feat(viz): schody czarne w trybie architektonicznym (czerwień=debug)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Ścieżka `render_floor_plan` (parterowce + mieszkania) — osie off + bez legendy + bez info/ENTRY

**Files:**
- Modify: `viz/plan_renderer.py` (`render_floor_plan` 103-178; `_draw_boundary` 529-545)
- Test: `tests/test_architectural_mode.py` (Append)

**Interfaces:**
- Consumes: `_draw_room(..., architectural=)` z Task 1.
- Produces: `render_floor_plan(..., architectural=False)`, `_draw_boundary(ax, boundary, architectural=False)`. Gdy `architectural=True`: `ax.axis("off")`, brak legendy, brak `info_text` „Outline…", brak markera/etykiety ENTRY.

- [ ] **Step 1: Write the failing test (append)**

```python
from shapely.geometry import box as _box
from core.boundary_analyzer import analyze_boundary
from core.models import FloorPlan
from viz.plan_renderer import render_floor_plan


def _apt_plan():
    b = analyze_boundary(Polygon([(0, 0), (8, 0), (8, 4), (0, 4)]), entry_point=(4, 0))
    syp = _room("sypialnia_1", Strefa.NOCNA, 4.0, 4.0, 0.0, 0.0)
    hub = _room("hub", Strefa.KOMUNIKACJA, 4.0, 4.0, 4.0, 0.0)
    return FloorPlan(boundary=b, template=None, rooms=[syp, hub])


def _texts(ax):
    return [t.get_text() for t in ax.texts]


def test_floor_plan_architectural_clean(tmp_path):
    fig = render_floor_plan(_apt_plan(), architectural=True, show=False,
                            save_path=tmp_path / "apt_arch.png")
    ax = fig.axes[0]
    assert ax.get_legend() is None, "tryb arch: brak legendy"
    assert ax.axison is False, "tryb arch: osie off"
    assert not any(t.startswith("Outline:") for t in _texts(ax)), "tryb arch: brak info_text"
    assert "ENTRY" not in _texts(ax), "tryb arch: brak etykiety ENTRY"
    assert not (ZONE_RGB & set(_fill_rgbs(ax))), "tryb arch: brak kolorów stref"
    plt.close(fig)


def test_floor_plan_default_unchanged(tmp_path):
    fig = render_floor_plan(_apt_plan(), show=False, save_path=tmp_path / "apt_color.png")
    ax = fig.axes[0]
    assert ax.get_legend() is not None
    assert ax.axison is True
    assert any(t.startswith("Outline:") for t in _texts(ax))
    assert "ENTRY" in _texts(ax)
    plt.close(fig)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -k floor_plan -q`
Expected: FAIL — `TypeError: render_floor_plan() got an unexpected keyword argument 'architectural'`

- [ ] **Step 3a: `_draw_boundary` — pomiń marker ENTRY w trybie arch (529-539)**

Nagłówek: `def _draw_boundary(ax: plt.Axes, boundary: Boundary):` → `def _draw_boundary(ax: plt.Axes, boundary: Boundary, architectural: bool = False):`
Owiń marker + adnotację ENTRY (535-539) warunkiem (obrys + marginesy zostają):
```python
    # Oznacz drzwi wejściowe (dev — pomijane w trybie architektonicznym)
    if not architectural:
        ex, ey = boundary.entry_point
        ax.plot(ex, ey, "rv", markersize=12, label="Drzwi wejściowe")
        ax.annotate("ENTRY", (ex, ey), textcoords="offset points",
                    xytext=(0, -15), ha="center", fontsize=8, color="red",
                    fontweight="bold")
```

- [ ] **Step 3b: `render_floor_plan` — sygnatura + przekazania + bramki**

Nagłówek (103-110): dołóż `architectural: bool = False` (po `furniture`).
- `_draw_boundary(ax, plan.boundary)` (127) → `_draw_boundary(ax, plan.boundary, architectural=architectural)`
- pętla pokoi (133-134) → `_draw_room(ax, room, furniture_polys=furn_by_room.get(room.spec.id), architectural=architectural)`
- Owiń blok legendy (152-164) w `if not architectural:`.
- Owiń blok `info_text` (166-174) w `if not architectural:`.
- Osie (176-178):
```python
    ax.set_aspect("equal")
    if architectural:
        ax.axis("off")
    else:
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
    plt.tight_layout()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_architectural_mode.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Run renderer regression**

Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -m pytest tests/test_two_storey_render.py tests/test_house_preview.py tests/test_house_staircase_b.py tests/test_house_attic_shrink.py tests/test_wall_poche.py -q`
Expected: PASS (default ścieżka nietknięta; znane flaki perf wg pamięci — weryfikować w izolacji jeśli czerwone)

- [ ] **Step 6: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add viz/plan_renderer.py tests/test_architectural_mode.py
git commit -m "feat(viz): tryb architektoniczny dla render_floor_plan (parterowce + mieszkania)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Podpięcie `architectural=True` w benchmarku + walidacja wizualna + STATE

**Files:**
- Modify: `notebooks/reference_benchmark.py` (`score_project`, render-calls 251-256)
- Modify: `docs/STATE.md`

- [ ] **Step 1: Podepnij flagę w `score_project`**

Obecnie (251-256):
```python
    if storeys == 2:
        render_house_figure(lay, with_furniture=False, title=f"BENCH {name}",
                            save_path=OUT / f"{name}.png", show=False)
    else:
        plan = FloorPlan(boundary=lay.boundary, template=None, rooms=lay.parter_rooms)
        render_floor_plan(plan, title=f"BENCH {name}", save_path=OUT / f"{name}.png", show=False)
```
Na (dołóż `architectural=True` do obu):
```python
    if storeys == 2:
        render_house_figure(lay, with_furniture=False, title=f"BENCH {name}",
                            save_path=OUT / f"{name}.png", show=False, architectural=True)
    else:
        plan = FloorPlan(boundary=lay.boundary, template=None, rooms=lay.parter_rooms)
        render_floor_plan(plan, title=f"BENCH {name}", save_path=OUT / f"{name}.png",
                          show=False, architectural=True)
```

- [ ] **Step 2: Wygeneruj 1 render domu w trybie architektonicznym (CPU wolne)**

Run:
```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && PYTHONPATH=. venv/bin/python -c "
import matplotlib; matplotlib.use('Agg')
from shapely.geometry import Polygon
from core.house_layout import generate_house
from viz.house_preview import render_house_figure
lay = generate_house(Polygon([(0,0),(10,0),(10,8),(0,8)]), entry_point=(5,0), num_storeys=2, time_limit_s=90)
assert lay.ok, lay.message
render_house_figure(lay, with_furniture=False, title='ARCH 10x8', save_path='rzuty/renders_mvp/arch_mode_10x8.png', show=False, architectural=True)
print('OK render → rzuty/renders_mvp/arch_mode_10x8.png')
"
```
Expected: `OK render → …` (czas ~30-90 s).

- [ ] **Step 3: Walidacja wizualna — przegląd OKIEM (z Dawidem)**

Otwórz `rzuty/renders_mvp/arch_mode_10x8.png` i porównaj z oryginałem D7 (`rzuty/domy/A.01.4 Parter 120m.pdf`). BRAMKA wizualna: (a) brak osi/ticków/ramki, (b) białe wnętrza (nie kolorowe strefy), (c) brak legendy, (d) schody czarne, (e) poché/drzwi/etykiety wciąż czytelne, (f) białe wnętrza + szara krawędź nie gubią pokoi. Jeśli któryś punkt zawodzi → STOP, diagnoza (NIE druga próba na ślepo).

- [ ] **Step 4: Update `docs/STATE.md`** (wpis: tryb architektoniczny #1-4 WDROŻONY, flaga opt-in, podpięty w benchmarku; przykładowy render; pozostałe telle #5-7 w kolejce)

- [ ] **Step 5: Commit**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && git add notebooks/reference_benchmark.py docs/STATE.md rzuty/renders_mvp/arch_mode_10x8.png
git commit -m "feat(bench): benchmark renderuje w trybie architektonicznym + STATE

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- #1 osie off → Task 2 (Step 3c, _draw_storey) + Task 4 (Step 3b, render_floor_plan). ✓
- #2 białe wnętrza → Task 1 (`_draw_room`, wspólny dla obu ścieżek). ✓ Day-zone edge szary → Task 2 Step 3b. ✓ Strefy knee-wall ZOSTAJĄ (nietknięte — `_draw_storey` 282-295 bez zmian). ✓
- #3 bez legendy → Task 2 (Step 3c) + Task 4 (Step 3b). ✓
- #4 schody czarne → Task 3 (wszystkie 3 funkcje schodów). ✓
- info_text + marker ENTRY (dodatkowe telle render_floor_plan z §architektura speca) → Task 4. ✓
- Podpięcie benchmark + walidacja wizualna (spec §Walidacja) → Task 5. ✓
- Poza zakresem (okna-3-linie #5, tabela/wymiary #6, meble #7, MVP/AC wiring, render_rooms_only) — świadomie pominięte (YAGNI z speca). ✓

**Placeholder scan:** Task 5 Step 4 „update STATE" bez dosłownej treści — celowe (liczby/render znane po Step 2-3), nie placeholder kodu. Wszystkie kroki kodu mają pełny kod + komendy + expected. ✓

**Type consistency:** flaga nazwana `architectural: bool = False` we WSZYSTKICH sygnaturach (`_draw_room`, `_draw_storey`, `render_two_storey`, `render_house_figure`, `_draw_stair`, `_draw_stair_in_room`, `_draw_winder_in_room`, `render_floor_plan`, `_draw_boundary`). Kolory spójne: białe `"white"`, krawędź `"#BDBDBD"`, schody `"#212121"`, day-edge `"#616161"`. Helpery testowe (`_room`, `_fill_rgbs`, `ZONE_RGB`, `_line_colors`, `_texts`) zdefiniowane raz, reużywane. ✓

## Execution Handoff

Plan: 5 tasków, ~1 plik core (`viz/plan_renderer.py`) + 2 dotknięcia (`house_preview.py`, `reference_benchmark.py`) + 1 nowy test. TDD RED-first każdy task. CPU wolne → walidacja wizualna w Task 5.
