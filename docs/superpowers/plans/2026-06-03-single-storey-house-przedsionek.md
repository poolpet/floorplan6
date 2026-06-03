# Single-storey houses + przedsionek-entry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate single-storey (parterowiec) houses ≥~45 m² and fix przedsionek-entry semantics (front door inside the wiatrołap, hol behind) for both 1- and 2-storey houses.

**Architecture:** Reuse the existing `solve_cpsat` + S17 `HouseProgramConfig`. Add a `house_single_storey` template (no stairs), an area-driven room-set selector, and a `num_storeys=1` branch in `generate_house`. Fix entry semantics by passing `entry_room_id="wiatrolap"` so the existing entry block constrains the wiatrołap (not the hub).

**Tech Stack:** Python 3.10+, OR-Tools CP-SAT, Shapely, pytest. Run tests with `./venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-03-single-storey-house-przedsionek-design.md`

**⚠️ Feasibility-delicate (session-18 lesson, B1):** CP-SAT changes here can turn footprints INFEASIBLE. Every behavior change is preceded by a RED feasibility test across the footprint × entry-side matrix. **2 fails on the same task ⇒ STOP and rewrite, not a 3rd patch.** Numeric thresholds (MIN_SINGLE_STOREY_AREA, PRZEDSIONEK_MIN_AREA, pack margin) are PROVISIONAL start values — Task 5's feasibility matrix is the authority that refines them.

---

## File Structure

- `core/house_layout.py` — MODIFY: `generate_house` gets a `num_storeys==1` branch; new `_generate_single_storey`, `single_storey_room_ids`, `_filter_template`, `suggest_storeys`; new `MIN_SINGLE_STOREY_AREA`, `PRZEDSIONEK_MIN_AREA` consts. Pass `entry_room_id="wiatrolap"` on the 2-storey parter solve.
- `core/cpsat_solver.py` — MODIFY: remove the redundant phase-2b wiatrołap-wall block (entry_room_id now drives it).
- `core/house_program.py` — MODIFY: `default_house_config` accepts `storey="single"` (bathroom cap = 5.0).
- `templates/house_single_storey.json` — CREATE: one-floor day+night program, no `schody`.
- `tests/test_house_przedsionek_entry.py` — CREATE: entry-in-wiatrołap (2- and 1-storey) + no-przedsionek small-house.
- `tests/test_house_single_storey.py` — CREATE: feasibility matrix, room-set scaling, invariants, suggest_storeys.

---

## Task 1: Przedsionek-entry fix (2-storey, foundational)

**Files:**
- Create: `tests/test_house_przedsionek_entry.py`
- Modify: `core/house_layout.py:139-142` (parter solve call)
- Modify: `core/cpsat_solver.py` (remove the phase-2b `wiat_idx` block added in `e0bcb23`, ~lines 559-573)

- [ ] **Step 1: Write the failing test** — the door must be INSIDE the wiatrołap on the entry wall.

In `tests/test_house_przedsionek_entry.py`:
```python
"""Przedsionek-entry: gdy wiatrołap istnieje, drzwi wejściowe są W NIM (zawiera punkt
wejścia + dotyka ściany wejścia), a hol jest za nim (sąsiaduje). Dotyczy 1- i 2-kondygnacyjnych."""
import pytest
from shapely.geometry import Polygon
from core.house_layout import generate_house


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


@pytest.mark.parametrize("W,H,ex,ey,side", [
    (9.0, 7.0, 4.5, 0.0, "south"),
    (9.0, 7.0, 0.0, 3.5, "west"),
    (9.0, 7.0, 9.0, 3.5, "east"),
    (9.0, 7.0, 4.5, 7.0, "north"),
])
def test_two_storey_door_is_inside_wiatrolap(W, H, ex, ey, side):
    layout = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), (ex, ey), num_storeys=2)
    assert layout.ok, layout.message
    wiat = _room(layout.parter_rooms, "wiatrolap")
    hub = _room(layout.parter_rooms, "hub")
    b = wiat.polygon.bounds  # (minx,miny,maxx,maxy)
    # wiatrołap zawiera punkt drzwi w poziomie/pionie wejściowej ściany
    if side in ("south", "north"):
        assert b[0] - 1e-6 <= ex <= b[2] + 1e-6, f"wiatrołap nie obejmuje drzwi x={ex}: {b}"
        assert (abs(b[1]) < 0.05) if side == "south" else (abs(b[3] - H) < 0.05)
    else:
        assert b[1] - 1e-6 <= ey <= b[3] + 1e-6, f"wiatrołap nie obejmuje drzwi y={ey}: {b}"
        assert (abs(b[0]) < 0.05) if side == "west" else (abs(b[2] - W) < 0.05)
    # hol za przedsionkiem: sąsiaduje wspólną krawędzią ≥0.9 m
    shared = wiat.polygon.boundary.intersection(hub.polygon.boundary).length
    assert shared >= 0.9 - 1e-6, f"hol nie za przedsionkiem (krawędź {shared:.2f} < 0.9)"
```

- [ ] **Step 2: Run the test to confirm it fails (or is flaky)**

Run: `./venv/bin/python -m pytest tests/test_house_przedsionek_entry.py -q`
Expected: FAIL on at least one side — currently the door is forced into the HUB (`entry_idx = hub_idx`), the wiatrołap only touches the entry wall and need not span the door point.

- [ ] **Step 3: Pass `entry_room_id="wiatrolap"` on the parter solve**

In `core/house_layout.py`, the parter solve (currently ~lines 139-142) — add the kwarg:
```python
    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=parter_cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap")
```

- [ ] **Step 4: Remove the now-redundant phase-2b wiatrołap-wall block**

In `core/cpsat_solver.py`, delete the block added in `e0bcb23` that finds `wiat_idx` and forces `model.add(y[wiat_idx] == 0)` etc. (the 4-way `entry_side` block right after the WC-external block, ~lines 559-573). Keep the WC-external block. Rationale: with `entry_room_id="wiatrolap"`, `entry_idx` resolves to the wiatrołap and the existing entry block (`cpsat_solver.py` ~516-537) already forces it to contain the door point AND touch the entry wall.

- [ ] **Step 5: Run the new test — expect PASS**

Run: `./venv/bin/python -m pytest tests/test_house_przedsionek_entry.py -q`
Expected: PASS (4/4 sides).

- [ ] **Step 6: Run the regression + phase-2b guards — must stay GREEN**

Run: `./venv/bin/python -m pytest tests/test_house_lroom_phase2b.py tests/test_house_staircase_b.py::test_feasible_across_footprints_and_entries tests/test_house_program.py -q`
Expected: ALL PASS. The wiatrołap-on-wall phase-2b test still passes (now via the entry block). If `test_feasible_across_footprints_and_entries` turns RED, the entry-room change broke feasibility — this is the B1 trigger: STOP, diagnose; a 2nd failed attempt ⇒ rewrite the approach (e.g. keep hub_at_entry semantics but add a separate wiatrołap-contains-door constraint instead of reassigning entry_idx).

- [ ] **Step 7: Commit**

```bash
git add core/house_layout.py core/cpsat_solver.py tests/test_house_przedsionek_entry.py
git commit -m "feat(stage4): przedsionek-entry — door inside wiatrołap (entry_room_id), hol behind

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `house_single_storey.json` template

**Files:**
- Create: `templates/house_single_storey.json`
- Modify: `tests/test_house_templates.py` (add a load assertion)

- [ ] **Step 1: Write the failing template-load test**

Append to `tests/test_house_templates.py`:
```python
def test_single_storey_template_loads():
    from core.template_selector import load_all_templates
    t = next((t for t in load_all_templates() if t.id == "house_single_storey"), None)
    assert t is not None, "brak szablonu house_single_storey"
    ids = {s.id for s in t.pokoje}
    assert {"hub", "wiatrolap", "salon", "kuchnia", "lazienka", "sypialnia_1"} <= ids
    assert "schody" not in ids, "parterowiec nie ma schodów"
    adj = {(r.room_a, r.room_b) for r in t.sasiedztwo}
    assert ("hub", "wiatrolap") in adj and ("wiatrolap", "_outside") in adj
    assert ("salon", "kuchnia") in adj  # otwarta strefa dzienna
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `./venv/bin/python -m pytest tests/test_house_templates.py::test_single_storey_template_loads -q`
Expected: FAIL (template missing).

- [ ] **Step 3: Create the template file**

Create `templates/house_single_storey.json` (full room set, no `schody`; mins/% copied from house_parter/house_pietro so existing calibration holds):
```json
{
  "id": "house_single_storey",
  "nazwa": "Dom jednorodzinny — parterowy",
  "typ_mieszkania": "DOM_PARTEROWY",
  "source": "manual",
  "n_source_plans": 0,
  "pokoje": [
    { "id": "hub", "nazwa": "Hol", "strefa": "KOMUNIKACJA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 4.0, "opt_powierzchnia": 6.0, "min_szerokosc": 1.5, "max_proporcja": 2.0, "procent_powierzchni": [0.04, 0.10] },
    { "id": "wiatrolap", "nazwa": "Wiatrołap", "strefa": "KOMUNIKACJA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.5, "opt_powierzchnia": 4.0, "min_szerokosc": 1.2, "max_proporcja": 2.0, "procent_powierzchni": [0.02, 0.06] },
    { "id": "salon", "nazwa": "Salon", "strefa": "DZIENNA", "wymaga_okna": true, "priorytet_fasady": 1, "preferowana_orientacja": [], "min_powierzchnia": 20.0, "opt_powierzchnia": 25.0, "min_szerokosc": 3.5, "max_proporcja": 2.0, "procent_powierzchni": [0.20, 0.35] },
    { "id": "kuchnia", "nazwa": "Kuchnia", "strefa": "DZIENNA", "wymaga_okna": true, "priorytet_fasady": 2, "preferowana_orientacja": [], "min_powierzchnia": 7.0, "opt_powierzchnia": 10.0, "min_szerokosc": 2.4, "max_proporcja": 2.0, "procent_powierzchni": [0.07, 0.14] },
    { "id": "spizarnia", "nazwa": "Spiżarnia", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.0, "opt_powierzchnia": 3.5, "min_szerokosc": 1.2, "max_proporcja": 2.5, "procent_powierzchni": [0.02, 0.05] },
    { "id": "wc", "nazwa": "WC", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 1.5, "opt_powierzchnia": 2.2, "min_szerokosc": 1.0, "max_proporcja": 2.0, "procent_powierzchni": [0.01, 0.04] },
    { "id": "lazienka", "nazwa": "Łazienka", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.5, "opt_powierzchnia": 4.8, "min_szerokosc": 1.5, "max_proporcja": 2.0, "procent_powierzchni": [0.06, 0.12] },
    { "id": "kotlownia", "nazwa": "Kotłownia", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 4.0, "opt_powierzchnia": 5.0, "min_szerokosc": 1.5, "max_proporcja": 2.0, "procent_powierzchni": [0.03, 0.07] },
    { "id": "sypialnia_1", "nazwa": "Sypialnia główna", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 1, "preferowana_orientacja": [], "min_powierzchnia": 11.0, "opt_powierzchnia": 14.0, "min_szerokosc": 3.0, "max_proporcja": 2.0, "procent_powierzchni": [0.15, 0.25] },
    { "id": "sypialnia_2", "nazwa": "Sypialnia 2", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 2, "preferowana_orientacja": [], "min_powierzchnia": 9.0, "opt_powierzchnia": 11.5, "min_szerokosc": 2.5, "max_proporcja": 2.0, "procent_powierzchni": [0.12, 0.22] },
    { "id": "sypialnia_3", "nazwa": "Sypialnia 3", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 3, "preferowana_orientacja": [], "min_powierzchnia": 8.0, "opt_powierzchnia": 10.5, "min_szerokosc": 2.4, "max_proporcja": 2.0, "procent_powierzchni": [0.10, 0.18] },
    { "id": "garderoba", "nazwa": "Garderoba", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.5, "opt_powierzchnia": 4.0, "min_szerokosc": 1.2, "max_proporcja": 2.5, "procent_powierzchni": [0.03, 0.07] }
  ],
  "sasiedztwo": [
    { "room_a": "wiatrolap", "room_b": "_outside", "connection_type": "entry_door" },
    { "room_a": "hub", "room_b": "wiatrolap", "connection_type": "door" },
    { "room_a": "hub", "room_b": "salon", "connection_type": "door" },
    { "room_a": "hub", "room_b": "wc", "connection_type": "door" },
    { "room_a": "hub", "room_b": "kotlownia", "connection_type": "door" },
    { "room_a": "hub", "room_b": "lazienka", "connection_type": "door" },
    { "room_a": "hub", "room_b": "garderoba", "connection_type": "door" },
    { "room_a": "hub", "room_b": "sypialnia_1", "connection_type": "door" },
    { "room_a": "hub", "room_b": "sypialnia_2", "connection_type": "door" },
    { "room_a": "hub", "room_b": "sypialnia_3", "connection_type": "door" },
    { "room_a": "salon", "room_b": "kuchnia", "connection_type": "opening" },
    { "room_a": "kuchnia", "room_b": "spizarnia", "connection_type": "door" }
  ]
}
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `./venv/bin/python -m pytest tests/test_house_templates.py::test_single_storey_template_loads -q`
Expected: PASS. (If the loader needs registering the new `typ_mieszkania`, check `core/template_selector.py` — the existing house templates load by globbing `templates/*.json`, so a new file should be picked up automatically; verify.)

- [ ] **Step 5: Commit**

```bash
git add templates/house_single_storey.json tests/test_house_templates.py
git commit -m "feat(stage4): house_single_storey template (one floor, no stairs)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Area-driven room-set selector + single-storey config

**Files:**
- Modify: `core/house_program.py` (`default_house_config` accepts `storey="single"`)
- Modify: `core/house_layout.py` (add consts + `single_storey_room_ids` + `_filter_template`)
- Test: `tests/test_house_single_storey.py` (new file; unit tests for the selector — fast, no CP-SAT)

- [ ] **Step 1: Write failing unit tests for the selector**

Create `tests/test_house_single_storey.py`:
```python
"""Parterowiec — dobór zestawu pokoi wg powierzchni + feasibility matrix + inwarianty."""
import pytest
from shapely.geometry import Polygon
from core.house_layout import single_storey_room_ids, MIN_SINGLE_STOREY_AREA, PRZEDSIONEK_MIN_AREA
from core.template_selector import load_all_templates


def _specs():
    t = next(t for t in load_all_templates() if t.id == "house_single_storey")
    return t.pokoje


def test_core_rooms_always_present():
    ids = set(single_storey_room_ids(_specs(), 46.0))
    assert {"hub", "salon", "kuchnia", "lazienka", "sypialnia_1"} <= ids


def test_no_przedsionek_below_threshold():
    ids = single_storey_room_ids(_specs(), PRZEDSIONEK_MIN_AREA - 1.0)
    assert "wiatrolap" not in ids


def test_przedsionek_appears_at_threshold():
    ids = single_storey_room_ids(_specs(), PRZEDSIONEK_MIN_AREA + 5.0)
    assert "wiatrolap" in ids


def test_bedrooms_scale_with_area():
    small = single_storey_room_ids(_specs(), 46.0)
    large = single_storey_room_ids(_specs(), 120.0)
    assert small.count("sypialnia_2") == 0 or "sypialnia_2" not in small
    assert "sypialnia_2" in large and "sypialnia_3" in large


def test_min_set_area_sum_fits():
    # zestaw przy MIN nie może wymagać więcej m² niż obrys (suma minów ≤ area)
    specs = {s.id: s for s in _specs()}
    ids = single_storey_room_ids(_specs(), MIN_SINGLE_STOREY_AREA)
    assert sum(specs[i].min_powierzchnia for i in ids) <= MIN_SINGLE_STOREY_AREA + 1e-6
```

- [ ] **Step 2: Run to confirm failure**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py -q`
Expected: FAIL (ImportError — symbols not defined yet).

- [ ] **Step 3: Implement the selector + config**

In `core/house_program.py`, make `default_house_config` accept `"single"` (treat like parter for the bathroom cap):
```python
def default_house_config(storey: str = "parter", master_id: str | None = None) -> HouseProgramConfig:
    """Domyślny program domu (cap-y ARCHON, łazienka parter/single ≤5 / poddasze ≤8)."""
    return HouseProgramConfig(
        caps=dict(DEFAULT_HOUSE_CAPS),
        bathroom_parter_max=5.0,
        bathroom_poddasze_max=8.0,
        storey=storey,
        master_id=master_id,
    )
```
And in `HouseProgramConfig.cap_for`, the bathroom branch already returns `bathroom_parter_max` for any storey != "poddasze", so `"single"` ⇒ 5.0 with no further change. (Verify this reading before relying on it.)

In `core/house_layout.py`, add near the top (after the existing consts):
```python
MIN_SINGLE_STOREY_AREA = 45.0   # provisional; refined by tests/test_house_single_storey.py feasibility matrix
PRZEDSIONEK_MIN_AREA = 50.0     # D2: poniżej tego progu drzwi wprost do holu (bez wiatrołapu)

# Dobór pokoi parterowca wg powierzchni obrysu. Rdzeń zawsze; reszta greedy wg sumy
# minów z marginesem na upakowanie (suma_min·margin ≤ area). Wiatrołap wg progu D2.
_SINGLE_CORE = ["hub", "salon", "kuchnia", "lazienka", "sypialnia_1"]
_SINGLE_OPTIONAL = ["wc", "sypialnia_2", "spizarnia", "kotlownia", "sypialnia_3", "garderoba"]
_PACK_MARGIN = 1.12   # provisional; bump if a chosen set proves INFEASIBLE in the matrix test


def single_storey_room_ids(specs: list, area_m2: float) -> list[str]:
    """Zwraca id pokoi parterowca dla danej powierzchni (kolejność = priorytet dodawania)."""
    by_id = {s.id: s for s in specs}
    chosen = [r for r in _SINGLE_CORE if r in by_id]
    cum = sum(by_id[r].min_powierzchnia for r in chosen)
    if area_m2 >= PRZEDSIONEK_MIN_AREA and "wiatrolap" in by_id:          # D2 — próg przedsionka
        chosen.append("wiatrolap"); cum += by_id["wiatrolap"].min_powierzchnia
    for rid in _SINGLE_OPTIONAL:                                         # greedy wg sumy minów
        if rid not in by_id:
            continue
        m = by_id[rid].min_powierzchnia
        if (cum + m) * _PACK_MARGIN <= area_m2:
            chosen.append(rid); cum += m
    return chosen
```
Add the template-filtering helper (used in Task 4):
```python
import dataclasses

def _filter_template(tpl, keep_ids: set):
    """Kopia szablonu z podzbiorem pokoi + sąsiedztwem dotyczącym tylko zachowanych pokoi."""
    pokoje = [p for p in tpl.pokoje if p.id in keep_ids]
    sasiedztwo = [r for r in tpl.sasiedztwo
                  if (r.room_a in keep_ids or r.room_a == "_outside")
                  and (r.room_b in keep_ids or r.room_b == "_outside")]
    return dataclasses.replace(tpl, pokoje=pokoje, sasiedztwo=sasiedztwo)
```

- [ ] **Step 4: Run the selector unit tests — expect PASS**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py -q -k "room or scale or threshold or fits"`
Expected: PASS. If `test_min_set_area_sum_fits` fails, the core min sum (~44.5) exceeds `MIN_SINGLE_STOREY_AREA` — raise `MIN_SINGLE_STOREY_AREA` until it holds.

- [ ] **Step 5: Commit**

```bash
git add core/house_program.py core/house_layout.py tests/test_house_single_storey.py
git commit -m "feat(stage4): single-storey room-set selector + storey=single config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `generate_house(num_storeys=1)` branch + `suggest_storeys`

**Files:**
- Modify: `core/house_layout.py` (`generate_house` branch + `_generate_single_storey` + `suggest_storeys`)

- [ ] **Step 1: Write the failing behavior tests**

Append to `tests/test_house_single_storey.py`:
```python
def _gen1(W, H, entry, t=25.0):
    return generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), entry,
                          num_storeys=1, time_limit_s=t)


def test_single_storey_generates_and_has_no_stairs():
    lay = _gen1(8.0, 8.0, (4.0, 0.0))
    assert lay.ok, lay.message
    ids = {r.spec.id for r in lay.parter_rooms}
    assert "schody" not in ids
    assert {"hub", "salon", "sypialnia_1", "lazienka"} <= ids
    assert lay.pietro_rooms == []   # jedna kondygnacja


def test_single_storey_too_small_clean_failure():
    lay = _gen1(5.0, 7.0, (2.5, 0.0))   # 35 m² < MIN_SINGLE_STOREY_AREA
    assert lay.ok is False and lay.message


def test_suggest_storeys_by_area():
    from core.house_layout import suggest_storeys
    assert suggest_storeys(48.0) == 1
    assert suggest_storeys(110.0) == 2
```

- [ ] **Step 2: Run to confirm failure**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py -q -k "no_stairs or too_small or suggest"`
Expected: FAIL (num_storeys=1 currently ignored → still solves 2 storeys / pietro non-empty; suggest_storeys missing).

- [ ] **Step 3: Implement the branch + helpers**

In `core/house_layout.py`, at the top of `generate_house`, before the existing 2-storey body:
```python
def generate_house(polygon: Polygon, entry_point: tuple[float, float],
                   num_storeys: int = 2, time_limit_s: float = 30.0) -> TwoStoreyLayout:
    if num_storeys == 1:
        return _generate_single_storey(polygon, entry_point, time_limit_s)
    # --- istniejąca ścieżka 2-kondygnacyjna (bez zmian poniżej) ---
    if polygon.area < MIN_STOREY_AREA:
        ...
```
Add the single-storey generator (mirrors the 2-storey one but no core/stairs/pietro):
```python
def suggest_storeys(area_m2: float) -> int:
    """Podpowiedź liczby kondygnacji wg powierzchni obrysu (architekt nadpisuje)."""
    return 1 if area_m2 < 60.0 else 2


def _generate_single_storey(polygon: Polygon, entry_point: tuple[float, float],
                            time_limit_s: float) -> TwoStoreyLayout:
    if polygon.area < MIN_SINGLE_STOREY_AREA:
        return TwoStoreyLayout(ok=False,
            message=f"Obrys {polygon.area:.0f} m2 za maly na parterowiec (min ~{MIN_SINGLE_STOREY_AREA:.0f} m2).")
    boundary = analyze_boundary(polygon, entry_point=entry_point)
    tpl = _template("house_single_storey")
    if tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_single_storey.")
    keep = set(single_storey_room_ids(tpl.pokoje, polygon.area))
    tpl_f = _filter_template(tpl, keep)
    cfg = default_house_config(storey="single", master_id="sypialnia_1")
    has_wiatrolap = "wiatrolap" in keep
    r = solve_cpsat(tpl_f, boundary, time_limit_s=time_limit_s,
                    program_config=cfg, hub_at_entry=True,
                    entry_room_id="wiatrolap" if has_wiatrolap else None,
                    l_capable_ids={"hub"})
    if r.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu parterowca (status={r.status}).", boundary=boundary)
    return TwoStoreyLayout(ok=True, parter_rooms=r.rooms, pietro_rooms=[], boundary=boundary)
```

- [ ] **Step 4: Run the behavior tests — expect PASS**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py -q -k "no_stairs or too_small or suggest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py
git commit -m "feat(stage4): generate_house num_storeys=1 branch + suggest_storeys

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Single-storey feasibility matrix + invariants (the authority on thresholds)

**Files:**
- Modify: `tests/test_house_single_storey.py` (matrix + invariant tests)

- [ ] **Step 1: Write the feasibility-matrix + invariant tests**

Append to `tests/test_house_single_storey.py`:
```python
_MATRIX = [
    (7.0, 7.0, (3.5, 0.0)), (8.0, 8.0, (4.0, 0.0)), (8.0, 8.0, (0.0, 4.0)),
    (8.0, 8.0, (8.0, 4.0)), (8.0, 8.0, (4.0, 8.0)),
    (9.0, 9.0, (4.5, 0.0)), (10.0, 10.0, (5.0, 0.0)), (11.0, 11.0, (5.5, 0.0)),
]


@pytest.mark.parametrize("W,H,entry", _MATRIX)
def test_single_storey_feasible_matrix(W, H, entry):
    lay = _gen1(W, H, entry)
    assert lay.ok, f"{W}x{H} entry {entry}: {lay.message}"


@pytest.mark.parametrize("W,H,entry", _MATRIX)
def test_single_storey_invariants(W, H, entry):
    lay = _gen1(W, H, entry)
    assert lay.ok, lay.message
    usable = W * H
    rooms = lay.parter_rooms
    # F1: pokrycie == usable + brak nakładania
    assert abs(sum(r.polygon.area for r in rooms) - usable) < 1e-2
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            assert rooms[i].polygon.intersection(rooms[j].polygon).area < 1e-3
    # F4: hol ≤ 15% usable; F2: lazienka ≤5, wc ≤3
    hub = next(r for r in rooms if r.spec.id == "hub")
    assert hub.area <= 0.15 * usable + 1.0, f"hol {hub.area:.1f} > F4 ({W}x{H})"
    for r in rooms:
        cap = {"lazienka": 5.0, "wc": 3.0}.get(r.spec.id.split("_")[0])
        if cap is not None:
            assert r.area <= cap + 1e-3, f"{r.spec.id}={r.area:.2f} > {cap}"
    # F5: każdy pokój (poza hub) dotyka holu ≥0.9 m
    for r in rooms:
        if r.spec.id == "hub":
            continue
        shared = hub.polygon.boundary.intersection(r.polygon.boundary).length
        assert shared >= 0.9 - 1e-6, f"{r.spec.id}↔hol {shared:.2f} < 0.9 ({W}x{H})"
```

- [ ] **Step 2: Run the matrix — diagnose any INFEASIBLE / invariant break**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py -q -k "matrix or invariants"`
Expected outcomes & responses:
- **All PASS** → thresholds are good; proceed.
- **An INFEASIBLE footprint** → the chosen room set is too dense for that area: raise `_PACK_MARGIN` (e.g. 1.12 → 1.20) and/or `MIN_SINGLE_STOREY_AREA`, re-run. This is tuning a provisional value, NOT relaxing a rule.
- **F4 hol > 15%** → the single-storey hol touches many rooms; confirm `l_capable_ids={"hub"}` is set (Task 4). If still over, this is a genuine finding (B3: do NOT relax F4) — STOP and report to Dawid (option: allow a 2nd L-capable circulation room, or cap rooms-per-storey).
- **2 distinct failed fix attempts on the same footprint ⇒ STOP, rewrite (B1).**

- [ ] **Step 3: Lock thresholds, full house regression**

Run: `./venv/bin/python -m pytest tests/test_house_single_storey.py tests/test_house_przedsionek_entry.py tests/test_house_lroom_phase2b.py tests/test_house_staircase_b.py tests/test_house_program.py tests/test_house_layout.py tests/test_open_plan_dayzone.py -q`
Expected: ALL PASS (single-storey + przedsionek + 2-storey regression).

- [ ] **Step 4: Manual visual check (B8)**

Run a single-storey render and eyeball it (door in przedsionek, hol behind, rooms off the hol, no stairs):
```bash
./venv/bin/python -c "
from shapely.geometry import Polygon
from core.house_layout import generate_house
from viz.plan_renderer import render_plan  # confirm the actual renderer entrypoint name
lay = generate_house(Polygon([(0,0),(10,0),(10,10),(0,10)]), (5.0,0.0), num_storeys=1)
print('ok=', lay.ok, lay.message)
for r in lay.parter_rooms: print(r.spec.id, round(r.polygon.area,1), r.polygon.bounds)
"
```
(If `viz/plan_renderer` exposes a single-storey-capable render, save a PNG and inspect; otherwise just inspect the room geometry printed above.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_house_single_storey.py core/house_layout.py
git commit -m "test(stage4): single-storey feasibility matrix + F1/F4/F5/F2 invariants; lock thresholds

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (for the implementer)
- **Spec coverage:** Task 1 = Section 1 (przedsionek fix); Task 2 = Section 2 (template); Task 3 = Section 3 (program/selector); Task 4 = Section 4 (num_storeys=1 branch + suggest_storeys + MIN); Task 5 = Section 5 (testing). D5 (≥45 m², micro-35 deferred) is encoded in `MIN_SINGLE_STOREY_AREA`.
- **Risk (single-storey hub touches many rooms vs F4):** addressed by `l_capable_ids={"hub"}` + Task 5 Step 2 explicit F4 branch (report, don't relax — B3).
- **Provisional numbers:** `MIN_SINGLE_STOREY_AREA=45`, `PRZEDSIONEK_MIN_AREA=50`, `_PACK_MARGIN=1.12`, `suggest_storeys` cutoff 60 — all tunable; Task 5 matrix is the authority.
- **Deferred:** micro-35 (reduced mins), furniture (phase 4), non-rectangular footprints.
