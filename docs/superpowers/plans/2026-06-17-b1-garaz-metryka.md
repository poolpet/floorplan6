# B1 — fix metryki garaż w F1 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Policzyć `garaz` w room-set F1 benchmarku (przynależność do zestawu), bo `_storey_rooms` wyklucza ref-garaż → nasz generowany garaż zawsze false-positive nawet gdy wzorzec faktycznie ma garaż.

**Architecture:** Garaż zostaje WYKLUCZONY z `_storey_rooms` (używany przez MAPE — pole garażu w tabelach niepewne), ale dochodzi do osobnego multiset-u typów dla F1. Wydzielamy mały, testowalny helper `_ref_f1_types(ref_storey)` i podpinamy go w `score_project` tylko w ścieżce F1. Zero zmian generatora/solvera → zero ryzyka perf.

**Tech Stack:** Python 3.13, pytest, shapely (istniejące). Plik: `notebooks/reference_benchmark.py`.

**Spec:** `docs/superpowers/specs/2026-06-17-b1-densyfikacja-design.md` (Lewar 2). Sweep predicted-F1: garaż-w-ref daje +0.0030 śr. F1 sam, +0.0077 sparowany z progiem (próg ODŁOŻONY — decyzja Dawida, ryzyko perf). Drgają: a2-2/ar02-1b/pt parter (garaż TP).

---

### Task 1: Helper `_ref_f1_types` — typy ref do F1 z garażem

**Files:**
- Modify: `notebooks/reference_benchmark.py` (po `_storey_rooms`, ~linia 196)
- Test: `tests/test_benchmark_garaz_f1.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benchmark_garaz_f1.py
"""B1: garaz liczony w F1 (przynależność), ale NIE w MAPE (pole niepewne)."""
from notebooks.reference_benchmark import _ref_f1_types, _storey_rooms

def _storey(rooms):
    return {"rooms": [{"mapped_id": t, "name_pl": t, "area_m2": a} for t, a in rooms]}

def test_ref_f1_types_includes_garaz():
    s = _storey([("salon", 30.0), ("garaz", 18.0), ("lazienka", 5.0)])
    types = _ref_f1_types(s)
    assert "garaz" in types
    assert "salon" in types and "lazienka" in types

def test_ref_f1_types_excludes_schody_taras_other():
    s = _storey([("salon", 30.0), ("schody", 6.0), ("taras", 12.0), ("other", 4.0)])
    assert _ref_f1_types(s) == ["salon"]

def test_storey_rooms_still_excludes_garaz_for_mape():
    # MAPE path NIEzmieniona — garaz dalej wykluczony z _storey_rooms
    s = _storey([("salon", 30.0), ("garaz", 18.0)])
    types = [t for t, _ in _storey_rooms(s)]
    assert "garaz" not in types
    assert "salon" in types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd FloorPlan6 && PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_garaz_f1.py -q`
Expected: FAIL — `ImportError: cannot import name '_ref_f1_types'`

- [ ] **Step 3: Implement `_ref_f1_types`**

Wstaw po funkcji `_storey_rooms` (która kończy się ~linia 196). NIE zmieniaj `_storey_rooms`:

```python
def _ref_f1_types(ref_storey: dict) -> list[str]:
    """Typy pokoi wzorca dla room-set F1. W ODRÓŻNIENIU od `_storey_rooms` (MAPE)
    LICZY `garaz` — przynależność do zestawu jest pewna, choć POLE garażu w tabelach
    bywa niepewne/brak (dlatego MAPE go wyklucza). Bez schody/taras/other (jak F1)."""
    return [_ref_room_type(r) for r in ref_storey["rooms"]
            if _ref_room_type(r) not in ("taras", "schody", "other")]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd FloorPlan6 && PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_garaz_f1.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd FloorPlan6 && git add notebooks/reference_benchmark.py tests/test_benchmark_garaz_f1.py
git commit -m "feat(bench): _ref_f1_types — garaz liczony w F1 (nie w MAPE)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Podepnij `_ref_f1_types` w `score_project` (tylko ścieżka F1)

**Files:**
- Modify: `notebooks/reference_benchmark.py` (`score_project`, ~linie 231-233)

- [ ] **Step 1: Zlokalizuj obecny blok F1/MAPE**

Obecnie (~231-233):

```python
        f1 = room_set_f1(_room_multiset([t for t, _ in gen_typed if t != "schody"]),
                         _room_multiset([t for t, _ in ref_typed if t != "schody"]))
        mape, nm = area_deviation(gen_typed, ref_typed)
```

- [ ] **Step 2: Zamień ref-multiset F1 na `_ref_f1_types` (MAPE bez zmian)**

```python
        # B1: F1 liczy garaz przez _ref_f1_types (przynależność); MAPE zostaje na
        # ref_typed (_storey_rooms — garaz wykluczony, pole niepewne).
        f1 = room_set_f1(_room_multiset([t for t, _ in gen_typed if t != "schody"]),
                         _room_multiset(_ref_f1_types(ref)))
        mape, nm = area_deviation(gen_typed, ref_typed)
```

Uwaga: `gen_typed` po stronie generatora JUŻ zawiera garaż (jeśli wygenerowany) — strona ref była jedyną luką. `ref` to zmienna pętli `for storey, ref, rooms in pairs`.

- [ ] **Step 3: Smoke — moduł się importuje i F1 helper działa na realnym wzorcu**

Run:
```bash
cd FloorPlan6 && PYTHONPATH=. venv/bin/python -c "
import json
from notebooks.reference_benchmark import _ref_f1_types
d = json.load(open('notebooks/reference_plans_full.json'))
a22 = next(p for p in d['projects'] if p['name']=='a2-2')
print('a2-2 parter F1-types:', _ref_f1_types(a22['parter']))
assert 'garaz' in _ref_f1_types(a22['parter']), 'a2-2 ref-parter ma garaz'
print('OK')
"
```
Expected: lista typów z `garaz`, `OK`.

- [ ] **Step 4: Commit**

```bash
cd FloorPlan6 && git add notebooks/reference_benchmark.py
git commit -m "feat(bench): score_project F1 liczy garaz (ref) — MAPE niezmienione

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Walidacja realnym benchmarkiem (rozstrzygająca)

**Files:** (brak zmian — pomiar)

- [ ] **Step 1: Uruchom pełny benchmark w tle**

Run (run_in_background):
```bash
cd FloorPlan6 && PYTHONPATH=. venv/bin/python notebooks/reference_benchmark.py notebooks/reference_plans_full.json > /tmp/bench_b1.out 2>&1
```
Czekaj na zakończenie (~20-35 min, 16 proj × 90 s).

- [ ] **Step 2: Sprawdź wynik vs baseline**

Run: `grep -E "^a2-2|^ar02-1b|^pt|^a2-6|^modlnica|ŚREDNI" /tmp/bench_b1.out`

Expected (predicted-F1 sweep): `a2-2`/`ar02-1b`/`pt` parter F1 ↑ (garaż TP); `a2-6`/`modlnica` parter F1 ↓ niewiele (ref-garaż = recall-miss, bo próg ODŁOŻONY — znane, akceptowane). ŚREDNI SCORE ≈ 58.8-59.2 (zysk ~+0.15 pkt, w szumie). **BRAMKA: generation-rate ≥14/16, ZERO nowych FAILi, score nie spada poniżej 58.5.**

- [ ] **Step 3: Jeśli bramka OK — przejdź dalej. Jeśli NIE — STOP, diagnoza.**

Brak commitu (pomiar). Wynik zapisz do STATE w Task 4.

---

### Task 4: Update STATE + pamięć + finalizacja

**Files:**
- Modify: `docs/STATE.md` (nowy wpis B1)
- Modify: `~/.claude/.../memory/` (jeśli warte — finding „room-set już dopasowany")

- [ ] **Step 1: Dopisz wpis B1 do STATE.md** (na górze, demote poprzedni „NEXT SESSION")

Treść: B1 zawężone do fix-metryki-garaż (Lewar2). Sweep predicted-F1: jedyny czysty lewar = garaż sparowany +0.0077 (próg odłożony — ryzyko perf), garderoba/spiżarnia net-zero → DROP. Realized: [wstaw liczby z Task 3]. **Płaskowyż potwierdzony: room-set już dobrze dopasowany; F1-straty to architektonicznie-słuszne extra (keep) + artefakty. NEXT: inny lewar (adjacency 20% / jakość renderów / AC bridge domów) — target+selekcja-tweaki wyczerpane.**

- [ ] **Step 2: Update pamięci** (rozszerz `[[proxy_gap_target_vs_realized]]` lub dodaj notkę o płaskowyżu room-setu)

- [ ] **Step 3: Commit**

```bash
cd FloorPlan6 && git add docs/STATE.md
git commit -m "docs(b1): STATE — fix metryki garaż done, płaskowyż room-setu potwierdzony

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** Lewar 2 (garaż-w-ref F1, MAPE niezmienione) → Tasks 1-2 ✓. Walidacja realnym benchmarkiem (spec §5) → Task 3 ✓. Lewar 1 (próg) + garderoba/spiżarnia → świadomie POZA zakresem (sweep net-zero / decyzja perf) — udokumentowane w planie i Task 4. ✓

**Placeholder scan:** Task 4 Step 1 ma „[wstaw liczby z Task 3]" — to celowe (liczby znane dopiero po benchmarku), nie placeholder kodu. Reszta kroków ma pełny kod/komendy. ✓

**Type consistency:** `_ref_f1_types(ref_storey: dict) -> list[str]` zdefiniowane w Task 1, użyte identycznie w Task 2 (`_ref_f1_types(ref)`) i smoke-teście. `_room_multiset`, `room_set_f1`, `_ref_room_type`, `_storey_rooms`, `area_deviation` — istniejące, niezmienione. ✓

## Execution Handoff

Plan jest mały (1 plik, ~3 linie zmiany + test). Po zatwierdzeniu — wykonanie.
