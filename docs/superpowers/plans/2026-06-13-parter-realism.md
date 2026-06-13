# Realizm parteru domów 2-kond. — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parter domu 2-kondygnacyjnego zyskuje sypialnię (pokój gościnny) + pełną łazienkę zamiast WC, zgodnie z korpusem; łączna liczba sypialni bez zmian (poddasze −1); spiżarnia bramkowana powierzchnią jako bufor perf.

**Architecture:** Szablon `house_parter.json` (wc→lazienka, +sypialnia_parter) + solver: reguła „łazienka nie landlocked" sparametryzowana (`external_bathroom_id`, domyślnie `"wc"` = zachowanie parterowca/poddasza, parter 2-kond. przekazuje `"lazienka"`) + selektory pokoi (`parter_room_ids` bramka spiżarni + flaga sypialni; `pietro_room_ids` `bedroom_offset`) + koordynacja budżetu sypialni w `generate_house` + 2 fixy uczciwości benchmarku. Parterowce i M1–M5 nietknięte.

**Tech Stack:** Python 3.10, OR-Tools CP-SAT, Shapely, pytest, JSON templates.

**Spec:** `docs/superpowers/specs/2026-06-13-parter-realism-design.md`

**WAŻNE (zależności istniejących testów):** zmiana wc→lazienka na parterze łamie testy
zakładające parterowe `wc` — aktualizacje są WPISANE w zadania (Task 1: corpus_adjacency;
Task 4: house_layout + lroom_phase2b). Nie pomijaj ich.

---

### Task 1: Szablon `house_parter.json` — wc→lazienka + sypialnia_parter

**Files:**
- Modify: `templates/house_parter.json`
- Modify: `tests/test_house_corpus_adjacency.py` (asercje parterowego wc)
- Test: `tests/test_house_parter_realism.py` (NOWY)

- [ ] **Step 1: Napisz failing test szablonu**

Utwórz `tests/test_house_parter_realism.py`:

```python
"""Realizm parteru domów 2-kond. (S30c): sypialnia + pełna łazienka na parterze,
łączna liczba sypialni zachowana (poddasze −1), spiżarnia wg powierzchni.
Spec: docs/superpowers/specs/2026-06-13-parter-realism-design.md"""
import pytest
from shapely.geometry import Polygon

from core.house_layout import (
    _template, parter_room_ids, pietro_room_ids, net_area, generate_house,
    attic_effective_area,
)


def test_parter_template_has_bedroom_and_bathroom():
    tpl = _template("house_parter")
    ids = {p.id for p in tpl.pokoje}
    assert "sypialnia_parter" in ids, "parter ma mieć sypialnię"
    assert "lazienka" in ids, "parter ma mieć pełną łazienkę"
    assert "wc" not in ids, "wc usunięte z parteru 2-kond. (łazienka zamiast)"
    syp = next(p for p in tpl.pokoje if p.id == "sypialnia_parter")
    assert syp.strefa.value == "NOCNA" and syp.wymaga_okna
    pairs = {frozenset((r.room_a, r.room_b)) for r in tpl.sasiedztwo}
    assert frozenset(("hub", "lazienka")) in pairs
    assert frozenset(("hub", "sypialnia_parter")) in pairs
    assert frozenset(("hub", "wc")) not in pairs
```

- [ ] **Step 2: Uruchom — potwierdź RED**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_parter_template_has_bedroom_and_bathroom -q`
Expected: FAIL (`sypialnia_parter`/`lazienka` nie istnieją; jest `wc`).

- [ ] **Step 3: Zmień `templates/house_parter.json`**

W `pokoje`: ZAMIEŃ cały obiekt pokoju `wc` na `lazienka`:
```json
    {"id": "lazienka", "nazwa": "Łazienka", "strefa": "USŁUGOWA", "wymaga_okna": false, "priorytet_fasady": null, "min_powierzchnia": 2.5, "opt_powierzchnia": 4.8, "min_szerokosc": 1.5, "max_proporcja": 2.0, "procent_powierzchni": [0.06, 0.12]}
```
DODAJ nowy pokój `sypialnia_parter` (np. po `gabinet`):
```json
    {"id": "sypialnia_parter", "nazwa": "Sypialnia (parter)", "strefa": "NOCNA", "wymaga_okna": true, "priorytet_fasady": 3, "preferowana_orientacja": [], "min_powierzchnia": 9.0, "opt_powierzchnia": 12.0, "min_szerokosc": 2.5, "max_proporcja": 2.0, "procent_powierzchni": [0.10, 0.18]}
```
W `sasiedztwo`: zamień `{"room_a": "hub", "room_b": "wc", "connection_type": "door"}`
na `{"room_a": "hub", "room_b": "lazienka", "connection_type": "door"}` i DODAJ
`{"room_a": "hub", "room_b": "sypialnia_parter", "connection_type": "door"}`.
Zachowaj poprawny JSON (przecinki). Reszta bez zmian.

- [ ] **Step 4: Zaktualizuj `tests/test_house_corpus_adjacency.py` (parterowe wc → lazienka)**

W `tests/test_house_corpus_adjacency.py`:
- w `test_big_parter_hub_keeps_core_star`, w krotce `("wiatrolap", "schody", "salon", "wc", "gabinet")`
  zmień `"wc"` → `"lazienka"`.
- w `test_rewrite_is_identity_without_garage`, w zbiorze `{"hub", "schody", "wiatrolap",
  "salon", "kuchnia", "spizarnia", "wc", "kotlownia"}` zmień `"wc"` → `"lazienka"`.

- [ ] **Step 5: Uruchom — potwierdź PASS (nowy + zaktualizowane)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_parter_template_has_bedroom_and_bathroom tests/test_house_corpus_adjacency.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/house_parter.json tests/test_house_parter_realism.py tests/test_house_corpus_adjacency.py
git commit -m "feat(stage4): house_parter wc→lazienka + sypialnia_parter (realizm parteru)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Solver — sparametryzuj regułę „łazienka nie landlocked" (`external_bathroom_id`)

**Files:**
- Modify: `core/cpsat_solver.py` (`solve_cpsat` sygnatura ~281; blok wc-external ~607-615)
- Test: `tests/test_house_parter_realism.py`

- [ ] **Step 1: Dopisz failing test solvera**

Dopisz do `tests/test_house_parter_realism.py`:

```python
def test_solver_external_bathroom_param_targets_given_room():
    """Reguła 'nie landlocked' celuje w pokój `external_bathroom_id` (domyślnie wc).
    Sprawdzamy, że lazienka jest dociśnięta do ściany zewnętrznej gdy o to poprosimy."""
    from core.cpsat_solver import solve_cpsat
    from core.boundary_analyzer import analyze_boundary
    from core.house_layout import _template, _filter_template
    from core.house_program import default_house_config, HouseProgramConfig
    poly = Polygon([(0, 0), (10, 0), (10, 9), (0, 9)])
    b = analyze_boundary(poly, entry_point=(5.0, 0.0))
    tpl = _filter_template(_template("house_parter"),
                           {"hub", "wiatrolap", "salon", "kuchnia", "lazienka", "kotlownia"})
    cfg = default_house_config(storey="parter")
    r = solve_cpsat(tpl, b, time_limit_s=30.0, program_config=cfg,
                    hub_at_entry=True, entry_room_id="wiatrolap",
                    l_capable_ids={"hub"}, external_bathroom_id="lazienka")
    assert r.status in ("OPTIMAL", "FEASIBLE"), r.status
    laz = next(x for x in r.rooms if x.spec.id == "lazienka")
    bnds = laz.polygon.bounds  # (minx,miny,maxx,maxy), świat = bbox 10×9
    touches = (abs(bnds[0]) < 0.05 or abs(bnds[2] - 10) < 0.05 or
               abs(bnds[1]) < 0.05 or abs(bnds[3] - 9) < 0.05)
    assert touches, f"lazienka landlocked: {bnds}"
```

- [ ] **Step 2: Uruchom — potwierdź RED**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_solver_external_bathroom_param_targets_given_room -q`
Expected: FAIL (`solve_cpsat` nie ma param `external_bathroom_id` → `TypeError`).

- [ ] **Step 3: Sparametryzuj solver**

W `core/cpsat_solver.py`, w sygnaturze `solve_cpsat` dodaj parametr (po `l_capable_ids`):
```python
    l_capable_ids: Optional[set] = None,
    external_bathroom_id: str = "wc",
) -> CpsatResult:
```
W bloku „WC domu dotyka ≥1 ściany ZEWNĘTRZNEJ" (ok. linie 607-615) zamień hardcode `"wc"`
na parametr i nazwy zmiennych na generyczne:
```python
    if program_config is not None and notch is None:
        bath_idx = next((i for i, s in enumerate(specs) if s.id == external_bathroom_id), None)
        if bath_idx is not None:
            bW = model.new_bool_var("bath_W"); model.add(x[bath_idx] == 0).only_enforce_if(bW)
            bE = model.new_bool_var("bath_E"); model.add(x_ends[bath_idx] == BW).only_enforce_if(bE)
            bS = model.new_bool_var("bath_S"); model.add(y[bath_idx] == 0).only_enforce_if(bS)
            bN = model.new_bool_var("bath_N"); model.add(y_ends[bath_idx] == BH).only_enforce_if(bN)
            model.add_bool_or([bW, bE, bS, bN])
```
Domyślne `"wc"` zachowuje zachowanie parterowca (`house_single_storey` ma `wc`) i poddasza
(brak `wc` → inert) bez zmiany ich wywołań.

- [ ] **Step 4: Uruchom — potwierdź PASS (+ smoke, że domyślne nie psuje)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_solver_external_bathroom_param_targets_given_room tests/test_cpsat_solver.py -q`
Expected: PASS (nowy test + smoke mieszkań M1-M5 bez regresji — blok i tak guarded `program_config is not None`).

- [ ] **Step 5: Commit**

```bash
git add core/cpsat_solver.py tests/test_house_parter_realism.py
git commit -m "feat(stage4): solver — external_bathroom_id (reguła nie-landlocked sparametryzowana)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `parter_room_ids` — spiżarnia ≥60 netto + flaga sypialni parteru

**Files:**
- Modify: `core/house_layout.py` (`parter_room_ids` ~248, `parter_template_for` ~283, stałe ~197)
- Test: `tests/test_house_parter_realism.py`

- [ ] **Step 1: Dopisz failing test selektora**

Dopisz do `tests/test_house_parter_realism.py`:

```python
def test_parter_selector_always_bedroom_bathroom_spizarnia_gated():
    tpl = _template("house_parter")
    small = parter_room_ids(tpl.pokoje, net_area(63.0))    # ~51 netto
    big = parter_room_ids(tpl.pokoje, net_area(110.0))     # ~89 netto
    for s in (small, big):
        assert "sypialnia_parter" in s and "lazienka" in s
        assert "wc" not in s
    assert "spizarnia" not in small, "spiżarnia dopiero ≥60 netto"
    assert "spizarnia" in big
    no_bed = parter_room_ids(tpl.pokoje, net_area(110.0), with_parter_bedroom=False)
    assert "sypialnia_parter" not in no_bed
```

- [ ] **Step 2: Uruchom — potwierdź RED**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_parter_selector_always_bedroom_bathroom_spizarnia_gated -q`
Expected: FAIL (`parter_room_ids` bez `with_parter_bedroom`; spiżarnia niebramkowana).

- [ ] **Step 3: Zmień stałą + `parter_room_ids` + `parter_template_for`**

Obok `_PARTER_GABINET_MIN_NET`/`_PARTER_GARAZ_MIN_NET` dodaj:
```python
_PARTER_SPIZARNIA_MIN_NET = 60.0  # korpus: spiżarnia tylko ≥~60 netto (osobie 65/a2-6 83 mają;
                                  # tropie 48/pb 51/pab2 44 nie) — bufor perf małego parteru
```
Zastąp `parter_room_ids` (cała funkcja):
```python
def parter_room_ids(specs: list, net_m2: float, with_parter_bedroom: bool = True) -> list[str]:
    """Zestaw pokoi parteru wg powierzchni NETTO (S30 — progi korpusowe netto-we).
    sypialnia_parter (S30c: pokój na parterze) zawsze gdy with_parter_bedroom;
    spiżarnia/gabinet/garaż bramkowane powierzchnią. Caller przelicza brutto przez net_area()."""
    by_id = {s.id for s in specs}
    gated = ("gabinet", "garaz", "spizarnia", "sypialnia_parter")
    ids = [s.id for s in specs if s.id not in gated]
    if with_parter_bedroom and "sypialnia_parter" in by_id:
        ids.append("sypialnia_parter")
    if net_m2 >= _PARTER_SPIZARNIA_MIN_NET and "spizarnia" in by_id:
        ids.append("spizarnia")
    if net_m2 >= _PARTER_GABINET_MIN_NET and "gabinet" in by_id:
        ids.append("gabinet")
    if net_m2 >= _PARTER_GARAZ_MIN_NET and "garaz" in by_id:
        ids.append("garaz")
    return ids
```
Zastąp `parter_template_for` (cała funkcja):
```python
def parter_template_for(gross_area_m2: float, with_parter_bedroom: bool = True):
    """Szablon parteru dla obrysu BRUTTO: zestaw pokoi wg netto (+sypialnia_parter
    gdy with_parter_bedroom) + sąsiedztwa korpusowe (gdy garaż). None gdy brak szablonu."""
    tpl = _template("house_parter")
    if tpl is None:
        return None
    keep = set(parter_room_ids(tpl.pokoje, net_area(gross_area_m2), with_parter_bedroom))
    tpl = _filter_template(tpl, keep)
    return _corpus_parter_adjacency(tpl)
```

- [ ] **Step 4: Uruchom — potwierdź PASS**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py::test_parter_selector_always_bedroom_bathroom_spizarnia_gated -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/house_layout.py tests/test_house_parter_realism.py
git commit -m "feat(stage4): parter_room_ids — spiżarnia ≥60 netto + flaga sypialni parteru

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Budżet sypialni + koordynacja `generate_house` (wiring łazienki-external)

**Files:**
- Modify: `core/house_layout.py` (`pietro_room_ids` ~218, `generate_house` ~303-321 + wywołanie parteru ~318)
- Modify: `tests/test_house_layout.py` (program parteru/poddasza), `tests/test_house_lroom_phase2b.py` (wc→lazienka)
- Test: `tests/test_house_parter_realism.py`

- [ ] **Step 1: Dopisz failing testy budżetu + integracji**

Dopisz do `tests/test_house_parter_realism.py`:

```python
def test_pietro_bedroom_offset_drops_one_keeps_min_one():
    tpl = _template("house_pietro")
    base = pietro_room_ids(tpl.pokoje, 70.0, bedroom_offset=0)
    off1 = pietro_room_ids(tpl.pokoje, 70.0, bedroom_offset=1)
    n_base = sum(1 for r in base if r.startswith("sypialnia"))
    n_off1 = sum(1 for r in off1 if r.startswith("sypialnia"))
    assert n_off1 == n_base - 1, f"offset=1 ma zdjąć 1 sypialnię ({n_base}→{n_off1})"
    assert n_off1 >= 1, "min 1 sypialnia zostaje na piętrze"


def test_bedroom_count_conserved_house_level():
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])  # 88 m²
    lay = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, lay.message
    parter_beds = sum(1 for r in lay.parter_rooms if r.spec.id.startswith("sypialnia"))
    pietro_beds = sum(1 for r in lay.pietro_rooms if r.spec.id.startswith("sypialnia"))
    old = pietro_room_ids(_template("house_pietro").pokoje, attic_effective_area(poly), bedroom_offset=0)
    old_beds = sum(1 for r in old if r.startswith("sypialnia"))
    assert parter_beds == 1, "1 sypialnia na parterze"
    assert parter_beds + pietro_beds == old_beds, f"total {parter_beds}+{pietro_beds} != stary {old_beds}"


def test_generate_2storey_parter_has_bedroom_bathroom():
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])
    lay = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, lay.message
    pids = [r.spec.id for r in lay.parter_rooms]
    assert sum(1 for i in pids if i.startswith("sypialnia")) == 1
    assert "lazienka" in pids and "wc" not in pids
```

- [ ] **Step 2: Uruchom — potwierdź RED**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py -k "offset or conserved or parter_has" -q`
Expected: FAIL (`pietro_room_ids` bez `bedroom_offset`; `generate_house` bez koordynacji → parter bez sypialni).

- [ ] **Step 3: Zmień `pietro_room_ids` (dodaj offset)**

Zastąp `pietro_room_ids` (cała funkcja):
```python
def pietro_room_ids(specs: list, eff_area_m2: float, bedroom_offset: int = 0) -> list[str]:
    """Zestaw pokoi poddasza wg powierzchni efektywnej (greedy po sumie minów).
    bedroom_offset (S30c): tyle sypialni schodzi na parter — poddasze dostaje o tyle
    mniej (od najwyższego numeru), min 1 sypialnia zostaje (strefa nocna na górze)."""
    by_id = {s.id: s for s in specs}
    chosen = [r for r in _PIETRO_CORE if r in by_id]
    cum = sum(by_id[r].min_powierzchnia for r in chosen)
    for rid in _PIETRO_OPTIONAL:
        if rid not in by_id:
            continue
        if rid == "lazienka_2" and eff_area_m2 < _PIETRO_LAZ2_MIN_EFF:
            continue
        if rid == "garderoba" and eff_area_m2 < _PIETRO_GARDEROBA_MIN_EFF:
            continue
        m = by_id[rid].min_powierzchnia
        if (cum + m) * _PACK_MARGIN <= eff_area_m2:
            chosen.append(rid)
            cum += m
    if bedroom_offset > 0:
        beds = [r for r in chosen if r.startswith("sypialnia")]
        n_drop = min(bedroom_offset, max(0, len(beds) - 1))   # zostaw ≥1
        drop = set(beds[len(beds) - n_drop:]) if n_drop else set()
        chosen = [r for r in chosen if r not in drop]
    return chosen
```

- [ ] **Step 4: Zmień `generate_house` — koordynacja budżetu + external_bathroom_id**

Znajdź blok (ok. linie 303-310):
```python
    parter_tpl = parter_template_for(polygon.area)
    pietro_tpl = _template("house_pietro")
    if parter_tpl is None or pietro_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonow domu (house_parter/house_pietro).")
    # Room-set scaling (S29/S30): poddasze wg powierzchni EFEKTYWNEJ (pełna −
    # 0.5·stref niskich ≈ netto-norma PL), parter wg NETTO (brutto·NET_FACTOR)
    # + sąsiedztwa korpusowe gdy jest garaż — patrz parter_template_for.
    eff = attic_effective_area(polygon)
    pietro_tpl = _filter_template(pietro_tpl, set(pietro_room_ids(pietro_tpl.pokoje, eff)))
```
ZASTĄP go:
```python
    pietro_tpl0 = _template("house_pietro")
    if pietro_tpl0 is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_pietro.")
    # Budżet sypialni na poziomie DOMU (S30c): jedna sypialnia schodzi na parter,
    # poddasze dostaje o 1 mniej → łączna liczba bez zmian. Fallback: gdy stary
    # model dałby <2 sypialni na piętrze, zostaw je na górze (parter bez sypialni).
    eff = attic_effective_area(polygon)
    old_beds = sum(1 for r in pietro_room_ids(pietro_tpl0.pokoje, eff, bedroom_offset=0)
                   if r.startswith("sypialnia"))
    parter_bedroom = old_beds >= 2
    offset = 1 if parter_bedroom else 0
    parter_tpl = parter_template_for(polygon.area, with_parter_bedroom=parter_bedroom)
    pietro_tpl = _filter_template(
        pietro_tpl0, set(pietro_room_ids(pietro_tpl0.pokoje, eff, bedroom_offset=offset)))
    if parter_tpl is None:
        return TwoStoreyLayout(ok=False, message="Brak szablonu house_parter.")
```
Następnie w wywołaniu `solve_cpsat` dla PARTERU (szukaj `r_parter = solve_cpsat(parter_tpl, ...`,
ok. linia 318) DODAJ argument `external_bathroom_id="lazienka"`:
```python
    r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                           reserved_core=core, program_config=parter_cfg,
                           stair_room_id="schody", hub_at_entry=True,
                           l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                           external_bathroom_id="lazienka")
```
(Wywołanie poddasza `r_pietro` BEZ zmian — domyślne `"wc"` → inert na piętrze.)

- [ ] **Step 5: Zaktualizuj łamane testy istniejące**

`tests/test_house_layout.py` w `test_generates_both_storeys_with_full_program` —
parter ma teraz lazienka+sypialnia_parter, poddasze o 1 sypialnię mniej. Zastąp dwie asercje:
```python
    assert {"salon", "kuchnia", "lazienka", "sypialnia_parter", "kotlownia"} <= parter_ids
    assert "wc" not in parter_ids
    assert {"sypialnia_1", "sypialnia_2", "lazienka"} <= pietro_ids
```
`tests/test_house_lroom_phase2b.py` w `test_wc_external_and_parter_hol_compact` —
parterowa łazienka (nie wc) jest dociśnięta do ściany. Zamień:
```python
    wc = _room(lay.parter_rooms, "wc")
    assert wc is not None
    assert _touches_any_wall(wc.polygon.bounds, W, H), \
        f"WC landlocked ({side}): bounds={wc.polygon.bounds}"
```
na:
```python
    laz = _room(lay.parter_rooms, "lazienka")
    assert laz is not None
    assert _touches_any_wall(laz.polygon.bounds, W, H), \
        f"łazienka landlocked ({side}): bounds={laz.polygon.bounds}"
```

- [ ] **Step 6: Uruchom — potwierdź PASS (nowe + zaktualizowane)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py tests/test_house_layout.py -q -p no:cacheprovider`
Expected: PASS (testy integracyjne ~30-60 s każdy; `test_house_lroom_phase2b` zostaw do Task 6 — wolny, 4 strony).

- [ ] **Step 7: Commit**

```bash
git add core/house_layout.py tests/test_house_parter_realism.py tests/test_house_layout.py tests/test_house_lroom_phase2b.py
git commit -m "feat(stage4): budżet sypialni domu (1 na parter, poddasze −1) + łazienka-external parteru

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Uczciwość benchmarku — schody poza F1 + master house-level

**Files:**
- Modify: `notebooks/reference_benchmark.py` (`score_project` ~160-192)
- Test: `tests/test_house_parter_realism.py`

- [ ] **Step 1: Dopisz test pomiaru (charakteryzujący kontrakt helperów)**

Dopisz do `tests/test_house_parter_realism.py`:

```python
def test_benchmark_room_f1_excludes_schody():
    from notebooks.reference_benchmark import room_set_f1, _room_multiset
    gen = [t for t in ["salon", "hol", "schody"] if t != "schody"]
    ref = ["salon", "hol"]
    assert room_set_f1(_room_multiset(gen), _room_multiset(ref)) == 1.0


def test_benchmark_master_is_house_level():
    from notebooks.reference_benchmark import _gen_room_type
    all_areas = {"sypialnia_parter": 9.0, "sypialnia_1": 16.0, "sypialnia_2": 11.0}
    master_id = max(all_areas, key=all_areas.get)
    assert master_id == "sypialnia_1"
    assert _gen_room_type("sypialnia_parter", "sypialnia_parter" == master_id) == "sypialnia"
    assert _gen_room_type("sypialnia_1", "sypialnia_1" == master_id) == "master_sypialnia"
```

- [ ] **Step 2: Uruchom (guard helperów — może przejść od razu)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py -k "benchmark" -q`
Expected: PASS (testują czyste funkcje `room_set_f1`/`_gen_room_type`; charakteryzują kontrakt
przed zmianą `score_project`). Jeśli `_room_multiset` nie jest importowalne — jest top-level w module, więc będzie.

- [ ] **Step 3: Zmień `score_project` — master house-level + schody poza F1**

W `notebooks/reference_benchmark.py`, w `score_project`, znajdź:
```python
    f1s, mapes, jacs = [], [], []
    for storey, ref, rooms in pairs:
        syp = [r for r in rooms if r.spec.id.startswith("sypialnia")]
        master_id = max(syp, key=lambda r: r.area).spec.id if syp else None
        gen_typed = [(_gen_room_type(r.spec.id, r.spec.id == master_id), r.area) for r in rooms]
        ref_typed = _storey_rooms(ref)
        f1 = room_set_f1(_room_multiset([t for t, _ in gen_typed]),
                         _room_multiset([t for t, _ in ref_typed]))
        mape, nm = area_deviation(gen_typed, ref_typed)
```
i ZASTĄP na:
```python
    # Master = największa sypialnia w CAŁYM domu (nie per-kondygnacja): inaczej
    # jedyna sypialnia_parter parteru fałszywie stałaby się 'master' (S30c).
    all_rooms = lay.parter_rooms + (lay.pietro_rooms if ref_g else [])
    all_syp = [r for r in all_rooms if r.spec.id.startswith("sypialnia")]
    master_id = max(all_syp, key=lambda r: r.area).spec.id if all_syp else None
    f1s, mapes, jacs = [], [], []
    for storey, ref, rooms in pairs:
        gen_typed = [(_gen_room_type(r.spec.id, r.spec.id == master_id), r.area) for r in rooms]
        ref_typed = _storey_rooms(ref)
        # schody wykluczone z F1 (ekstrakcja wzorców nie listuje ich jako pokój,
        # jak garaz/other) — inaczej nasz pokój schody zaniża precyzję.
        f1 = room_set_f1(_room_multiset([t for t, _ in gen_typed if t != "schody"]),
                         _room_multiset([t for t, _ in ref_typed if t != "schody"]))
        mape, nm = area_deviation(gen_typed, ref_typed)
```

- [ ] **Step 4: Uruchom test + import smoke**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py -k "benchmark" -q && PYTHONPATH=. venv/bin/python -c "import notebooks.reference_benchmark"`
Expected: PASS + import bez błędu.

- [ ] **Step 5: Commit**

```bash
git add notebooks/reference_benchmark.py tests/test_house_parter_realism.py
git commit -m "test(stage4): benchmark — schody poza F1 + master house-level (uczciwość pomiaru)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Regresja + re-pomiar benchmarku + sync docs

**Files:**
- Modify: `docs/STATE.md`
- Test: istniejące moduły domów + benchmark

- [ ] **Step 1: Regresja skupiona (domy + parterowiec + lroom + M-smoke)**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_parter_realism.py tests/test_house_single_storey.py tests/test_house_attic_shrink.py tests/test_house_lfootprint.py tests/test_house_program.py tests/test_house_lroom_phase2b.py tests/test_house_staircase_b.py -q -p no:cacheprovider`
Expected: zielono. Każdy fail solverowy (parter=UNKNOWN) zweryfikuj W IZOLACJI — to znany flak
perf parteru (pamięć `project_single_storey_11x11_flaky`), NIE regresja jeśli izolacja przechodzi.

- [ ] **Step 2: Re-pomiar benchmarku (efekt realizmu)**

Run: `PYTHONPATH=. venv/bin/python notebooks/reference_benchmark.py notebooks/reference_plans_rect7.json 2>&1 | grep -v Warning | tail -14`
Expected: parter F1 wyraźnie wyżej niż baseline (0.33-0.75); średnia > 53.5/100. Zanotuj liczby.

- [ ] **Step 3: Render kontrolny 2-kond. (B8)**

Run:
```bash
PYTHONPATH=. venv/bin/python -c "
import matplotlib; matplotlib.use('Agg')
from shapely.geometry import Polygon
from core.house_layout import generate_house
from viz.house_preview import render_house_figure
lay = generate_house(Polygon([(0,0),(11,0),(11,8),(0,8)]), (5.5,0.0), num_storeys=2, time_limit_s=60.0)
print('ok:', lay.ok)
if lay.ok:
    render_house_figure(lay, True, save_path='rzuty/renders_mvp/s30c_parter_realism.png')
    print('parter:', [(r.spec.id, round(r.area,1)) for r in lay.parter_rooms])
"
```
Expected: parter ma sypialnię + łazienkę (nie WC).

- [ ] **Step 4: Zaktualizuj `docs/STATE.md`**

Dopisz w bloku S30c: „**REALIZM PARTERU 2-kond. WDROŻONY** — house_parter wc→lazienka +
sypialnia_parter; solver `external_bathroom_id` (łazienka parteru nie landlocked); budżet sypialni
domu (1 na parter, poddasze −1, total zachowany); spiżarnia ≥60 netto (bufor perf); benchmark
uczciwszy (schody poza F1, master house-level). Benchmark rect7: <średnia>/100 (parter F1 <X>).
Parterowce/M1-M5 nietknięte." — z realnymi liczbami z Step 2.

- [ ] **Step 5: Commit**

```bash
git add docs/STATE.md
git commit -m "docs(stage4): STATE sync — realizm parteru 2-kond. DONE + benchmark re-pomiar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notatki wykonawcze

- **Delegacja modeli (Dawid 2026-06-13):** rutynowe kroki subagentów → Opus, nie Sonnet.
- **NIE odpalaj własnych monitorów/tail-follow** w subagencie — pytest w FOREGROUND, czekaj na podsumowanie (poprzedni agent utknął na monitorze).
- **Kontencja CP-SAT:** każdy fail solverowy weryfikuj W IZOLACJI zanim uznasz za regresję.
- **B1:** 2 nieudane próby na zadaniu → STOP, diagnoza, eskalacja (nie 3-cia iteracja na ślepo).
- **Poza zakresem (nie rób):** salon-overflow cap, parterowce (`house_single_storey`), M1-M5, osobne WC gościnne, perf parteru.
