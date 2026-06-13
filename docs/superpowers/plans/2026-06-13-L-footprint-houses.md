# L-footprinty domów 2-kond. (notch-aware rdzeń) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Domy 2-kondygnacyjne na obrysie L-kształtnym generują się — rdzeń klatki schodowej kotwiczony przy wewnętrznym (wklęsłym) narożniku skrzydeł zamiast lądować w wcięciu.

**Architecture:** Jedna zmiana w `core/house_layout._reserve_core`: nowy opcjonalny parametr `notch`. Gdy `notch is None` — logika bajt-w-bajt jak dziś (gwarancja braku regresji prostokątnych domów i mieszkań). Gdy notch obecny — rdzeń `sw×sh` (wymiary bez zmian) zakotwiony przy wklęsłym wierzchołku L, w litej części po przekątnej od wcięcia. `generate_house` przekazuje `boundary.notch`. Solver już trzyma notch jako przeszkodę dla pozostałych pokoi — nic więcej nie trzeba.

**Tech Stack:** Python 3.10, Shapely (geometria), OR-Tools CP-SAT (solver — nietknięty), pytest.

**Spec:** `docs/superpowers/specs/2026-06-13-L-footprint-houses-design.md`

---

> ⚠️ **REWIZJA wykonawcza 2026-06-13:** pierwotne „kotwiczenie na WKLĘSŁYM narożniku"
> okazało się INFEASIBLE (sonda `notebooks/lcore_placement_probe.py`: narożnik flush/
> pionowy/+offset = INFEASIBLE, róg przeciwny = OPTIMAL). Zaimplementowano **róg bbox
> DIAGONALNIE PRZECIWNY do notcha** (decyzja Dawida). Aktualna geometria + test
> `test_core_anchored_opposite_notch` — patrz zrewidowany spec (sekcja Geometria) i
> `core/house_layout._reserve_core`. Kroki niżej zachowane jako zapis intencji; kod
> faktyczny = wersja „róg przeciwny".

### Task 1: notch-aware `_reserve_core` (rdzeń w rogu przeciwnym do notcha)

**Files:**
- Modify: `core/house_layout.py` (funkcja `_reserve_core`, ok. linie 154-185)
- Test: `tests/test_house_lfootprint.py` (NOWY)

- [ ] **Step 1: Napisz failing testy geometrii rdzenia**

Utwórz `tests/test_house_lfootprint.py`:

```python
"""L-footprinty domów 2-kond. (S30, decyzja Dawida 2026-06-13): rdzeń klatki
kotwiczony przy WEWNĘTRZNYM narożniku skrzydeł, nie w wcięciu L.
Spec: docs/superpowers/specs/2026-06-13-L-footprint-houses-design.md"""
import pytest
from shapely.geometry import Polygon, box as shbox

from core.boundary_analyzer import analyze_boundary
from core.house_layout import _reserve_core, generate_house


def _L_bottom_right(W=12.0, H=10.0, nw=4.5, nh=4.0):
    """L z wcięciem w dolnym-prawym rogu [W-nw,W]×[0,nh]."""
    return Polygon([(0, 0), (W - nw, 0), (W - nw, nh), (W, nh), (W, H), (0, H)])


def _L_top_left(W=12.0, H=10.0, nw=4.5, nh=4.0):
    """L z wcięciem w górnym-lewym rogu [0,nw]×[H-nh,H]."""
    return Polygon([(0, 0), (W, 0), (W, H), (nw, H), (nw, H - nh), (0, H - nh)])


def _core_box(core):
    cx, cy, sw, sh = core
    return shbox(cx, cy, cx + sw, cy + sh)


def test_core_not_in_notch():
    """Rdzeń nie przecina wcięcia (dziś _reserve_core go tam wstawia → INFEASIBLE)."""
    poly = _L_bottom_right()
    b = analyze_boundary(poly, entry_point=(6.0, 10.0))
    assert b.notch is not None, "notch nie wykryty — test bez sensu"
    core = _reserve_core(b.bbox, (6.0, 10.0), force_straight=True, notch=b.notch)
    notch_box = shbox(b.notch.x, b.notch.y,
                      b.notch.x + b.notch.width, b.notch.y + b.notch.height)
    assert _core_box(core).intersection(notch_box).area < 1e-6, \
        f"rdzeń {core} wpada w notch {notch_box.bounds}"


@pytest.mark.parametrize("builder,corner", [
    (_L_bottom_right, lambda nf: (nf.x, nf.y + nf.height)),          # dolny-prawy → (nx, ny+nh)
    (_L_top_left,     lambda nf: (nf.x + nf.width, nf.y)),           # górny-lewy → (nx+nw, ny)
])
def test_core_at_inner_corner(builder, corner):
    """Jeden róg rdzenia styka się z wklęsłym wierzchołkiem L."""
    poly = builder()
    b = analyze_boundary(poly, entry_point=(6.0, 5.0))
    assert b.notch is not None
    cx, cy, sw, sh = _reserve_core(b.bbox, (6.0, 5.0), force_straight=True, notch=b.notch)
    ix, iy = corner(b.notch)
    corners = [(cx, cy), (cx + sw, cy), (cx, cy + sh), (cx + sw, cy + sh)]
    dmin = min((abs(px - ix) + abs(py - iy)) for px, py in corners)
    assert dmin < 0.05, f"żaden róg rdzenia {corners} nie przy wklęsłym wierzchołku ({ix},{iy})"


def test_reserve_core_rectangle_unchanged():
    """notch=None → wynik IDENTYCZNY jak bez parametru (gwarancja braku regresji)."""
    for bbox, entry in [((0, 0, 10, 8), (5, 0)), ((0, 0, 9, 7), (0, 3.5)),
                        ((0, 0, 11, 8), (5.5, 8)), ((0, 0, 8, 10), (8, 5))]:
        assert _reserve_core(bbox, entry, force_straight=True) == \
               _reserve_core(bbox, entry, force_straight=True, notch=None)
```

- [ ] **Step 2: Uruchom testy — potwierdź RED**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_lfootprint.py -k "not generates and not aligned and not single_storey" -q`
Expected: FAIL — `test_core_not_in_notch` + `test_core_at_inner_corner` rzucą `TypeError: _reserve_core() got an unexpected keyword argument 'notch'` (parametr jeszcze nie istnieje). `test_reserve_core_rectangle_unchanged` też (ten sam TypeError).

- [ ] **Step 3: Dodaj notch-aware gałąź do `_reserve_core`**

W `core/house_layout.py` zmień sygnaturę i dodaj gałąź notcha NA POCZĄTKU ciała (po obliczeniu `sw, sh`), przed istniejącą logiką prostokąta:

```python
def _reserve_core(bbox, entry_point, force_straight: bool = False,
                  notch=None) -> tuple[float, float, float, float]:
    """Rdzeń klatki schodowej (x, y, w, h), bbox-relative — Approach B.

    Geometria adaptacyjna (`_stair_core_dims`; force_straight → bieg prosty wzdłuż
    kalenicy, knee-wall S26). Pozycja wg ARCHON: na ŚREDNIEJ GŁĘBOKOŚCI (cofnięta
    od fasady wejścia) i OBOK osi wejścia (przy ścianie bocznej po przeciwnej
    stronie niż drzwi). Dzięki temu HOL może zająć strefę wejścia (zawiera drzwi,
    dotyka ściany wejścia) i dotknąć schodów od ich strony holowej — schody NIE
    leżą na osi wejścia, więc nie blokują huba.

    notch (S30): gdy obrys jest L-kształtny, rdzeń kotwiczony przy WKLĘSŁYM
    narożniku skrzydeł (w litej części po przekątnej od wcięcia) — inaczej
    przypięta klatka ląduje w wcięciu (przeszkoda solvera) → INFEASIBLE.
    notch=None → logika prostokąta bajt-w-bajt jak dawniej (zero regresji M-domów).
    """
    minx, miny, maxx, maxy = bbox
    W = maxx - minx
    H = maxy - miny
    sw, sh, _kind = _stair_core_dims(W, H, force_straight=force_straight)

    if notch is not None:
        # Wklęsły wierzchołek L = róg notcha WEWNĄTRZ bbox (nie na krawędzi).
        # Notch przylega do jednej krawędzi poziomej i jednej pionowej bbox.
        eps = 1e-6
        nx, ny, nw, nh = notch.x, notch.y, notch.width, notch.height
        on_left = nx < eps             # wcięcie przy lewej krawędzi bbox
        on_bottom = ny < eps           # wcięcie przy dolnej krawędzi bbox
        inner_x = (nx + nw) if on_left else nx
        inner_y = (ny + nh) if on_bottom else ny
        # Rozciągnij rdzeń w stronę litej części (po przekątnej od wcięcia):
        cx = inner_x if on_left else inner_x - sw
        cy = inner_y if on_bottom else inner_y - sh
        # Fallback: clamp do bbox (wąskie skrzydło). Kotwienie narożne jest
        # styczne do notcha (nie nachodzi), więc clamp wystarcza; degenerację
        # (lita część < program) i tak złapie solver (ok=False).
        cx = min(max(cx, 0.0), max(0.0, W - sw))
        cy = min(max(cy, 0.0), max(0.0, H - sh))
        return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))

    ex = entry_point[0] - minx
    ey = entry_point[1] - miny
    side = _entry_side(bbox, entry_point)
    if side in ("south", "north"):
        cx = (W - sw) if ex < W / 2 else 0.0
        if side == "south":
            cy = min(STAIR_FRONT_SETBACK, max(0.0, H - sh))
        else:  # north
            cy = max(H - sh - STAIR_FRONT_SETBACK, 0.0)
    else:  # west / east — pionowa ściana wejścia
        cy = (H - sh) if ey < H / 2 else 0.0
        if side == "west":
            cx = min(STAIR_FRONT_SETBACK, max(0.0, W - sw))
        else:  # east
            cx = max(W - sw - STAIR_FRONT_SETBACK, 0.0)
    return (round(cx, 3), round(cy, 3), round(sw, 3), round(sh, 3))
```

> Uwaga: zachowaj ISTNIEJĄCE ciało prostokąta dokładnie (od `ex = ...` w dół) — wklejasz tylko nową sygnaturę + blok `if notch is not None:` przed nim. Nie zmieniaj `_stair_core_dims`, `_entry_side`, stałych.

- [ ] **Step 4: Uruchom testy geometrii — potwierdź PASS**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_lfootprint.py -k "not generates and not aligned and not single_storey" -q`
Expected: PASS (3 testy: `test_core_not_in_notch`, `test_core_at_inner_corner[bottom_right]`, `test_core_at_inner_corner[top_left]`, `test_reserve_core_rectangle_unchanged`).

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py tests/test_house_lfootprint.py
git commit -m "feat(stage4): notch-aware _reserve_core — rdzeń klatki przy wklęsłym narożniku L

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Wpięcie w `generate_house` + integracja (L 2-kond. generuje się)

**Files:**
- Modify: `core/house_layout.py` (funkcja `generate_house`, wywołanie `_reserve_core`, ok. linia 347)
- Test: `tests/test_house_lfootprint.py` (dopisz testy integracyjne)

- [ ] **Step 1: Dopisz failing testy integracyjne**

Dopisz na końcu `tests/test_house_lfootprint.py`:

```python
def test_l_2storey_generates():
    """L 102 m² 2-kond. generuje oba piętra (dziś parter+pietro=UNKNOWN)."""
    poly = _L_bottom_right()  # 12×10 − 4.5×4 = 102 m²
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, f"L 2-kond. nie wygenerowana: {lay.message}"
    assert lay.parter_rooms and lay.pietro_rooms


def test_stairs_vertically_aligned_on_L():
    """Schody parteru i poddasza mają ten sam bbox (piony klatki)."""
    poly = _L_bottom_right()
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, lay.message
    sp = next(r for r in lay.parter_rooms if r.spec.id == "schody")
    spp = next(r for r in lay.pietro_rooms if r.spec.id == "schody")
    for a, b in zip(sp.polygon.bounds, spp.polygon.bounds):
        assert abs(a - b) < 0.05, f"piony schodów rozjechane: {sp.polygon.bounds} vs {spp.polygon.bounds}"


def test_single_storey_L_still_ok():
    """Regression-lock: parterowiec L (działał przed zmianą) nadal generuje program."""
    poly = _L_bottom_right()
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=1, time_limit_s=60.0)
    assert lay.ok, lay.message
    beds = [r for r in lay.parter_rooms if r.spec.id.startswith("sypialnia")]
    assert len(beds) >= 3, f"parterowiec L: tylko {len(beds)} sypialni"
```

- [ ] **Step 2: Uruchom — potwierdź RED na `test_l_2storey_generates` i `test_stairs_vertically_aligned_on_L`**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_lfootprint.py -k "generates or aligned or single_storey" -q`
Expected: `test_l_2storey_generates` + `test_stairs_vertically_aligned_on_L` FAIL (`generate_house` nie przekazuje jeszcze `notch` → rdzeń w wcięciu → `ok=False`, parter+pietro=UNKNOWN). `test_single_storey_L_still_ok` PASS (parterowiec nie używa rdzenia — już działa).

- [ ] **Step 3: Przekaż notch z `generate_house` do `_reserve_core`**

W `core/house_layout.py`, w `generate_house` (gałąź 2-kond.), zmień wywołanie:

```python
    boundary = analyze_boundary(polygon, entry_point=entry_point)
    # Knee-wall (S26): bieg prosty wzdłuż kalenicy — patrz _stair_core_dims(force_straight).
    # S30: notch-aware — dla L rdzeń ląduje przy wklęsłym narożniku, nie w wcięciu.
    core = _reserve_core(boundary.bbox, entry_point, force_straight=True,
                         notch=boundary.notch)
```

(To jedyna zmiana — `boundary.notch` jest `None` dla prostokąta → zachowanie bez zmian; obiekt `NotchInfo` dla L → nowa gałąź.)

- [ ] **Step 4: Uruchom testy integracyjne — potwierdź PASS**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_lfootprint.py -q`
Expected: PASS (wszystkie 7: 4 geometrii z Task 1 + 3 integracyjne). `test_l_2storey_generates` może chodzić ~30-60 s (solver).

- [ ] **Step 5: Render kontrolny (B8 — obejrzyj wynik)**

Run:
```bash
PYTHONPATH=. venv/bin/python -c "
import matplotlib; matplotlib.use('Agg')
from shapely.geometry import Polygon
from core.house_layout import generate_house
from viz.house_preview import render_house_figure
L = Polygon([(0,0),(7.5,0),(7.5,4),(12,4),(12,10),(0,10)])
lay = generate_house(L, entry_point=(6.0,10.0), num_storeys=2, time_limit_s=60.0)
print('ok:', lay.ok, lay.message)
if lay.ok:
    render_house_figure(lay, True, save_path='rzuty/renders_mvp/s30_L_2storey.png')
    print('zapisano rzuty/renders_mvp/s30_L_2storey.png')
    sc = next(r for r in lay.parter_rooms if r.spec.id=='schody')
    print('schody parter bbox:', tuple(round(v,2) for v in sc.polygon.bounds))
"
```
Expected: `ok: True`, PNG zapisany; obejrzyj — klatka przy zgięciu L (nie w wcięciu), hol na zgięciu, piony wyrównane.

- [ ] **Step 6: Commit**

```bash
git add core/house_layout.py tests/test_house_lfootprint.py
git commit -m "feat(stage4): L-footprinty domów 2-kond. — generate_house przekazuje notch do rdzenia

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Regresja domów (zero regresji prostokątnych) + sync docs

**Files:**
- Modify: `docs/STATE.md` (blok S30 — dopisz L-footprinty DONE)
- Test: istniejące moduły domów

- [ ] **Step 1: Batch regresji domów (prostokątne bez zmian)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_attic_shrink.py tests/test_house_staircase_b.py tests/test_house_staircase.py tests/test_house_single_storey.py tests/test_house_program.py tests/test_house_lroom_phase2b.py tests/test_house_lfootprint.py -q -p no:cacheprovider`
Expected: zielono (ewentualne fail-e `lroom_phase2b[*]` zweryfikuj W IZOLACJI — to znane flaki kontencji, NIE regresja: `pytest tests/test_house_lroom_phase2b.py -q`).

- [ ] **Step 2: Zaktualizuj `docs/STATE.md`**

Dopisz w bloku S30 (po wdrożeniu netto/brutto) zdanie:
„**L-FOOTPRINTY domów 2-kond. WDROŻONE** (`_reserve_core` notch-aware — rdzeń przy wklęsłym narożniku skrzydeł; `tests/test_house_lfootprint.py` 7/7; render `rzuty/renders_mvp/s30_L_2storey.png`). Prostokątne domy bez regresji (notch=None bajt-w-bajt). Poddasze dużych L (≥120 m²) zostaje osobną krawędzią room-count (świadomie poza zakresem)."

- [ ] **Step 3: Commit**

```bash
git add docs/STATE.md
git commit -m "docs(stage4): STATE sync — L-footprinty domów 2-kond. DONE (notch-aware rdzeń)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notatki wykonawcze

- **Delegacja modeli (Dawid 2026-06-13):** rutynowe kroki subagentów → Opus, nie Sonnet; Fable 5 trzymaj na architekturę/diagnozę.
- **Kontencja CP-SAT:** batch domowy flaczy ~kilka testów przy obciążeniu CPU; każdy fail solverowy weryfikuj W IZOLACJI zanim uznasz za regresję (pamięć `project_single_storey_11x11_flaky`).
- **B1:** 2 nieudane próby na zadaniu → STOP, diagnoza, nie 3-cia iteracja na ślepo.
- **Poza zakresem (nie rób):** poddasze dużych L, różnoboczne/T, mieszkania (działają).
