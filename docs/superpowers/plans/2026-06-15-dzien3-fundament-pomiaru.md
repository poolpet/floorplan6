# Dzień 3 — Uczciwy fundament pomiaru — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Postawić uczciwy fundament pomiaru przed strojeniem bloatu (Dzień 4): oznaczyć prowenancję refs_geo i scommitować je; dodać REALNĄ diagnostykę `stair_kind` do benchmarku (waluje winder z Dnia 2); dodać diagnostyczną metrykę IoU pokoi — TYLKO dla `tropie` (jedyna realna geometria). Zero fałszywie-zielonych metryk.

**Architecture:** Trzy niezależne zadania. (1) Metadane prowenancji na 6 JSON-ach refs_geo + commit (nikt ich nie czyta → zero ryzyka). (2) Czysty człon binarny `stair_kind` w `reference_benchmark.py` (waga 0 w score; entry_side i open_plan ŚWIADOMIE pominięte — tautologia / niezgodność reprezentacji, udokumentowane). (3) Pure helper `room_iou` + probe `tropie_iou_probe.py` liczący baseline IoU dla tropie po sanity-checku ramki współrzędnych.

**Tech Stack:** Python, Shapely (geometria/IoU), pytest, matplotlib(Agg). Benchmark woła CP-SAT (wolny — integracja uruchamiana raz po baseline).

**Reality-checks z researchu (load-bearing):**
- refs_geo: `notebooks/refs_geo/*.json` to źródło prawdy (rzuty/refs_geo = tylko PNG, .gitignore). Tylko `tropie` = vector_traced (extract_pdf_rooms.py); pozostałe 5 = vision-guessed geometria (areas z tabeli). Wszystkie 6 untracked.
- `stair_kind`: REALNY sygnał. Ref kind ∈ {none,straight,u_winder}; gen `lay.stair_kind` ∈ {u,straight} → normalizacja `u→u_winder`, parterowiec→`none`.
- `entry_side`: TAUTOLOGIA (benchmark wstrzykuje `ref.side` jako entry_point, `reference_benchmark.py:167`) → pominięte.
- `open_plan`: generator trzyma OSOBNY pokój `kuchnia` (rysowany open-plan), wzorce mają aneks (brak 'kuchnia') → proxy "no kuchnia" zawsze mismatch = różnica reprezentacji, nie luka → pominięte (do Dnia 5/flagi open-plan).
- IoU: możliwy TYLKO przeciw refs_geo z polygonami; `reference_plans*.json` nie mają pozycji. Realna geometria = tylko tropie. Ryzyko: wyrównanie ramki (origin/y-flip) — sanity-check przed zaufaniem liczbie.

---

## File Structure
- `notebooks/refs_geo/{tropie,modlnica,kudowe,ligasy,osobie,rogoznik}.json` — +2 pola prowenancji.
- `notebooks/reference_benchmark.py` — +helper `stair_kind_match`, +helper `room_iou`, +wpięcie stair_kind do `score_project`/print; komentarz dlaczego entry/open pominięte.
- `notebooks/tropie_iou_probe.py` — NOWY diagnostyczny skrypt baseline IoU.
- `tests/test_benchmark_diagnostics.py` — NOWY: testy `stair_kind_match` + `room_iou` (pure, szybkie).

**Poza zakresem dziś:** entry_side realny (wymaga zwrotu zrealizowanej strony z generate_house), open_plan realny (wymaga flagi/szablonu aneksu), IoU dla 5 vision-plans (geometria zmyślona), wpięcie IoU/stair do `score` z niezerową wagą (faza „docisk", nie teraz).

---

## Task 1: Prowenancja refs_geo + commit (3a)

**Files:** Modify the 6 `notebooks/refs_geo/*.json`; commit. (Mechaniczne — bez TDD; weryfikacja: pliki nadal się parsują + render_ref_geo działa.)

- [ ] **Step 1: Dodaj 2 pola top-level po kluczu `"units"` w każdym z 6 JSON-ów.**
  Wartości per plik:
  - `notebooks/refs_geo/tropie.json` → `"geometry_source": "vector_traced", "areas_source": "traced"` (area_m2 liczone z otrace'owanych wektorów PDF, NIE z drukowanej tabeli).
  - `notebooks/refs_geo/modlnica.json`, `kudowe.json`, `ligasy.json`, `osobie.json`, `rogoznik.json` → `"geometry_source": "vision_approx", "areas_source": "table"` (geometria zgadnięta przez model; powierzchnie z drukowanej tabeli — autorytatywne).
  Wstaw oba klucze bezpośrednio po linii `"units": "m",` (zachowaj poprawny JSON — przecinki).

- [ ] **Step 2: Sanity — pliki nadal się parsują i renderują.**
  Run: `cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6" && for f in notebooks/refs_geo/*.json; do PYTHONPATH=. venv/bin/python -c "import json,sys; d=json.load(open(sys.argv[1])); print(sys.argv[1].split('/')[-1], d.get('geometry_source'), d.get('areas_source'))" "$f"; done`
  Expected: 6 linii, każda z poprawnym `geometry_source`/`areas_source` (tropie=vector_traced/traced, reszta=vision_approx/table). Brak wyjątku JSON.
  Run: `PYTHONPATH=. venv/bin/python notebooks/render_ref_geo.py 2>&1 | tail -3` (jeśli skrypt przyjmuje argument nazwy — sprawdź `--help`/nagłówek; cel: potwierdzić że nieznane pola nie psują renderu). Jeśli wymaga konkretnego wywołania, wystarczy sam parse z poprzedniej komendy.

- [ ] **Step 3: Commit (dane + pipeline reprodukowalny).**
```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
git add notebooks/refs_geo/ notebooks/render_ref_geo.py notebooks/extract_pdf_rooms.py notebooks/montage_refs_geo.py
git commit -m "data(stage4): refs_geo ground-truth + prowenancja (vector_traced=tropie, reszta vision_approx)

Oznaczone geometry_source/areas_source — żeby NIE stroić generatora do zmyślonej
geometrii 5 vision-plans jako 'ground truth'. Tylko tropie = realny wektor. Commit
dotąd untracked danych + skryptów pipeline (render/extract/montage).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(NIE dodawaj `rzuty/refs_geo/` — to PNG-i ignorowane przez `.gitignore`.)

---

## Task 2: Diagnostyka `stair_kind` w benchmarku (3c, uczciwie)

**Files:** Modify `notebooks/reference_benchmark.py`; Test `tests/test_benchmark_diagnostics.py` (new).

- [ ] **Step 1: Failing test.** Utwórz `tests/test_benchmark_diagnostics.py`:
```python
"""Diagnostyki benchmarku — pure helpery (bez CP-SAT, szybkie)."""
from notebooks.reference_benchmark import stair_kind_match


def test_stair_match_winder_2storey():
    r = stair_kind_match("u", has_schody=True, storeys=2, ref_kind="u_winder")
    assert r["gen"] == "u_winder" and r["match"] == 1.0


def test_stair_mismatch_straight_vs_winder():
    r = stair_kind_match("straight", has_schody=True, storeys=2, ref_kind="u_winder")
    assert r["gen"] == "straight" and r["match"] == 0.0


def test_stair_single_storey_is_none():
    r = stair_kind_match("straight", has_schody=False, storeys=1, ref_kind="none")
    assert r["gen"] == "none" and r["match"] == 1.0


def test_stair_winder_matches_winder_ref():
    assert stair_kind_match("u", True, 2, "u_winder")["match"] == 1.0
    assert stair_kind_match("u", True, 2, "straight")["match"] == 0.0
```

- [ ] **Step 2: Run, expect FAIL** (ImportError: cannot import name 'stair_kind_match'):
`PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_diagnostics.py::test_stair_match_winder_2storey -v`

- [ ] **Step 3: Dodaj helper `stair_kind_match` w `notebooks/reference_benchmark.py`** (po `adjacency_jaccard`, ~linia 100):
```python
STAIR_KIND_NORM = {"u": "u_winder", "straight": "straight"}


def stair_kind_match(gen_stair_kind: str, has_schody: bool, storeys: int, ref_kind) -> dict:
    """Zgodność typu schodów generator↔wzorzec (diagnostyka, waga 0 w score).

    Generator zwraca 'u'/'straight' → normalizujemy 'u'→'u_winder'. Parterowiec
    (storeys==1 bez pokoju 'schody') traktujemy jako 'none' (wzorce parterowca mają
    stairs.kind='none'). Zwraca {gen, ref, match}.
    """
    if storeys == 1 and not has_schody:
        gen = "none"
    else:
        gen = STAIR_KIND_NORM.get(gen_stair_kind, gen_stair_kind)
    return {"gen": gen, "ref": ref_kind, "match": 1.0 if gen == ref_kind else 0.0}
```

- [ ] **Step 4: Wepnij do `score_project` po pętli kondygnacji.** Znajdź (linie 196-199):
```python
        f1s.append(f1); mapes.append(mape); jacs.append(jac)
    # score 0-100: pokoje 50% + powierzchnie 30% (100%→0 pkt przy MAPE≥50%) + sąsiedztwa 20%
    f1m = sum(f1s) / len(f1s); mapem = sum(mapes) / len(mapes); jacm = sum(jacs) / len(jacs)
    res["score"] = round(100 * (0.5 * f1m + 0.3 * max(0.0, 1 - mapem / 50.0) + 0.2 * jacm), 1)
```
Wstaw diagnostykę stair_kind PRZED `f1m = ...` (score zostaje bajt-w-bajt):
```python
        f1s.append(f1); mapes.append(mape); jacs.append(jac)
    # Diagnostyka stair_kind (waga 0 w score) — waliduje winder default (S31b).
    # entry_side POMINIĘTY: benchmark wstrzykuje ref.side jako entry_point (line 167) →
    #   match byłby tautologią; realny wymaga zwrotu ZREALIZOWANEJ strony z generate_house.
    # open_plan POMINIĘTY: generator trzyma osobny pokój 'kuchnia' (rysowany open-plan),
    #   wzorce mają aneks (brak 'kuchnia') → proxy zawsze mismatch = różnica reprezentacji.
    has_schody = any(r.spec.id == "schody" for r in lay.parter_rooms)
    res["stair_kind"] = stair_kind_match(lay.stair_kind, has_schody, storeys,
                                         (ref_p.get("stairs") or {}).get("kind"))
    # score 0-100: pokoje 50% + powierzchnie 30% (100%→0 pkt przy MAPE≥50%) + sąsiedztwa 20%
    f1m = sum(f1s) / len(f1s); mapem = sum(mapes) / len(mapes); jacm = sum(jacs) / len(jacs)
    res["score"] = round(100 * (0.5 * f1m + 0.3 * max(0.0, 1 - mapem / 50.0) + 0.2 * jacm), 1)
```

- [ ] **Step 5: Pokaż stair_kind w tabeli `main()`.** Znajdź (linie 218-224):
```python
    for r in results:
        det = []
        for st in ("parter", "poddasze"):
            if st in r:
                d = r[st]
                det.append(f"{st}: F1={d['room_f1']} MAPE={d['area_mape_pct']}% adj={d['adj_jaccard']}")
        print(f"{r['name']:28s} {r['status']:28s} {r.get('score', '—'):>5}  {' | '.join(det)}")
```
Dodaj kolumnę stair (po pętli `st`, przed `print`):
```python
    for r in results:
        det = []
        for st in ("parter", "poddasze"):
            if st in r:
                d = r[st]
                det.append(f"{st}: F1={d['room_f1']} MAPE={d['area_mape_pct']}% adj={d['adj_jaccard']}")
        if "stair_kind" in r:
            sk = r["stair_kind"]
            det.append(f"stair={sk['gen']}/{sk['ref']}={sk['match']:.0f}")
        print(f"{r['name']:28s} {r['status']:28s} {r.get('score', '—'):>5}  {' | '.join(det)}")
```

- [ ] **Step 6: Run unit tests — PASS.**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_diagnostics.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit.**
```bash
git add notebooks/reference_benchmark.py tests/test_benchmark_diagnostics.py
git commit -m "feat(bench): diagnostyka stair_kind (waga 0) — waluje winder; entry/open-plan udokumentowane jako odłożone

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Diagnostyczny IoU pokoi dla tropie (3b)

**Files:** Modify `notebooks/reference_benchmark.py` (+`room_iou`); Create `notebooks/tropie_iou_probe.py`; Test `tests/test_benchmark_diagnostics.py` (extend).

- [ ] **Step 1: Failing test `room_iou`.** Dopisz w `tests/test_benchmark_diagnostics.py`:
```python
from shapely.geometry import box
from notebooks.reference_benchmark import room_iou


def test_room_iou_identical_is_one():
    g = [("salon", box(0, 0, 4, 3))]
    r = [("salon", box(0, 0, 4, 3))]
    assert abs(room_iou(g, r) - 1.0) < 1e-6


def test_room_iou_half_overlap():
    # ref [0,4]x[0,2]=8; gen [2,6]x[0,2]=8; przecięcie [2,4]x[0,2]=4; unia=12 → 1/3
    g = [("salon", box(2, 0, 6, 2))]
    r = [("salon", box(0, 0, 4, 2))]
    assert abs(room_iou(g, r) - (4.0 / 12.0)) < 1e-6


def test_room_iou_no_matching_type_is_none():
    g = [("kuchnia", box(0, 0, 4, 3))]
    r = [("salon", box(0, 0, 4, 3))]
    assert room_iou(g, r) is None
```

- [ ] **Step 2: Run, expect FAIL** (ImportError room_iou):
`PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_diagnostics.py::test_room_iou_identical_is_one -v`

- [ ] **Step 3: Dodaj `room_iou` w `notebooks/reference_benchmark.py`** (po `area_deviation`, ~linia 92):
```python
def room_iou(gen_typed_polys, ref_typed_polys):
    """Średni IoU pokoi dopasowanych po TYPIE. Argumenty: list[(type, shapely.Polygon)].
    Dla każdego pokoju WZORCA bierze najlepszy nakładający się generowany pokój tego
    samego typu (greedy, bez wykluczania — diagnostyka). None gdy brak dopasowań.
    Tylko dla wzorców z REALNĄ geometrią (refs_geo vector_traced = tropie)."""
    from collections import defaultdict
    gen_by_type = defaultdict(list)
    for t, p in gen_typed_polys:
        if p is not None:
            gen_by_type[t].append(p)
    ious = []
    for t, rp in ref_typed_polys:
        if rp is None:
            continue
        best = 0.0
        for gp in gen_by_type.get(t, []):
            uni = rp.union(gp).area
            if uni > 0:
                best = max(best, rp.intersection(gp).area / uni)
        if gen_by_type.get(t):
            ious.append(best)
    return sum(ious) / len(ious) if ious else None
```

- [ ] **Step 4: Run unit tests — PASS.**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_diagnostics.py -v`
Expected: 7 passed (4 stair + 3 iou).

- [ ] **Step 5: Utwórz `notebooks/tropie_iou_probe.py`** — diagnostyka baseline IoU dla tropie:
```python
"""Diagnostyczny baseline IoU pokoi: generator vs REALNA geometria tropie (refs_geo
vector_traced). Tylko tropie — pozostałe 5 refs_geo mają geometrię zgadniętą (vision).
Najpierw SANITY-CHECK ramki współrzędnych (origin/orientacja), potem IoU per kondygnacja.

Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/tropie_iou_probe.py
"""
import json
from pathlib import Path

from shapely.geometry import Polygon

from core.house_layout import generate_house
from notebooks.reference_benchmark import room_iou, _gen_room_type

GEO = json.loads(Path("notebooks/refs_geo/tropie.json").read_text())
assert GEO.get("geometry_source") == "vector_traced", "IoU tylko dla realnej geometrii"

# refs_geo room 'id' → typ w domenie generatora (_gen_room_type bazowy, bez rozróżnienia master)
def _ref_type(rid: str) -> str:
    base = rid.split("_")[0]
    return {"hol": "hol", "podest": "hol", "schody": "schody"}.get(base, base)

def _gen_base_type(rid: str) -> str:
    # bazowy typ generatora bez master (IoU dopasowuje po typie zgrubnym)
    t = _gen_room_type(rid, is_master=False)
    return "sypialnia" if t == "master_sypialnia" else t

storeys = GEO["storeys"]
parter_geo = next(s for s in storeys if s["storey"] == "parter")
outline = parter_geo["outline"]
poly = Polygon(outline)
bx0, by0, bx1, by1 = poly.bounds
entry = parter_geo.get("entry") or {}
ep = tuple(entry.get("point", [(bx0 + bx1) / 2, by0]))
n_storeys = 2 if any(s["storey"] in ("poddasze", "pietro") for s in storeys) else 1

lay = generate_house(poly, entry_point=ep, num_storeys=n_storeys, time_limit_s=60.0)
print(f"tropie outline bbox = ({bx0:.2f},{by0:.2f})-({bx1:.2f},{by1:.2f})  gen.ok={lay.ok} {lay.message[:50]}")
if not lay.ok:
    raise SystemExit("generator nie zbudował tropie — IoU pominięty")

# SANITY ramki: generator buduje pokoje w tej samej ramce co outline (origin (bx0,by0))?
gbx = lay.boundary.bbox
print(f"frame-check: gen.boundary.bbox={tuple(round(v,2) for v in gbx)} vs outline=({bx0:.2f},{by0:.2f},{bx1:.2f},{by1:.2f})")
if abs(gbx[0] - bx0) > 0.1 or abs(gbx[1] - by0) > 0.1 or abs(gbx[2] - bx1) > 0.1 or abs(gbx[3] - by1) > 0.1:
    print("⚠️ RAMKA NIESPÓJNA — IoU niżej może być nieufny (origin/skala/y-flip).")

def _iou_for(geo_storey, gen_rooms):
    ref_tp = [(_ref_type(r["id"]), Polygon(r["polygon"])) for r in geo_storey["rooms"]]
    gen_tp = [(_gen_base_type(r.spec.id), r.polygon) for r in gen_rooms]
    return room_iou(gen_tp, ref_tp)

print(f"PARTER room-IoU = {_iou_for(parter_geo, lay.parter_rooms)}")
pod = next((s for s in storeys if s["storey"] in ("poddasze", "pietro")), None)
if pod and lay.pietro_rooms:
    print(f"PODDASZE room-IoU = {_iou_for(pod, lay.pietro_rooms)}")
```

- [ ] **Step 6: Uruchom probe — baseline (wolny, generate_house ~1-2 min).**
`PYTHONPATH=. venv/bin/python notebooks/tropie_iou_probe.py`
Expected: drukuje `gen.ok=True`, frame-check (idealnie spójny; jeśli ⚠️ — zaraportuj, NIE ufaj liczbie), oraz `PARTER room-IoU = <0..1>` (+ poddasze). To jest BASELINE pozycyjny tropie. Zanotuj liczby do raportu.

- [ ] **Step 7: Commit.**
```bash
git add notebooks/reference_benchmark.py notebooks/tropie_iou_probe.py tests/test_benchmark_diagnostics.py
git commit -m "feat(bench): diagnostyczny room-IoU + tropie baseline probe (tylko vector_traced)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Bramka końcowa Dnia 3
- [ ] **Step A: Pure testy zielone.** `PYTHONPATH=. venv/bin/python -m pytest tests/test_benchmark_diagnostics.py -v` → 7 passed.
- [ ] **Step B: (opcjonalnie, wolne) baseline benchmark z nową kolumną stair.** `PYTHONPATH=. venv/bin/python notebooks/reference_benchmark.py notebooks/reference_plans_full.json 2>&1 | tail -25` — sprawdź, że kolumna `stair=gen/ref=match` się pokazuje i że winder (gen=u_winder) MATCHUJE u_winder-owe wzorce. (16 projektów × CP-SAT = wolne ~kilkanaście min; uruchom jeśli chcesz baseline, inaczej zanotuj że odłożone.)
- [ ] **Step C: Raport do Dawida** — prowenancja scommitowana, stair_kind waliduje winder, tropie IoU baseline = <liczba>, entry/open-plan udokumentowane jako odłożone z powodem.

## Self-Review (autor)
- **Pokrycie 3a/3b/3c:** prowenancja+commit → Task 1; stair_kind diagnostyka → Task 2; IoU tropie → Task 3. entry_side/open_plan świadomie pominięte z udokumentowanym powodem (uczciwy fundament, nie fałszywe metryki).
- **Placeholdery:** brak — pełny kod + komendy.
- **Spójność:** `stair_kind_match(gen_stair_kind, has_schody, storeys, ref_kind)` i `room_iou(gen_typed_polys, ref_typed_polys)` — sygnatury zgodne w testach, wpięciu i probe. `lay.stair_kind` ('u'/'straight') z Dnia 2. Score formula (`reference_benchmark.py:199`) NIETKNIĘTA.
- **Ryzyko:** IoU frame-alignment — probe robi sanity-check i ostrzega zamiast ufać; jeśli ⚠️, raportujemy zamiast commitować garbage baseline. refs_geo JSON edycja ręczna — Step 2 parsuje wszystkie 6 zanim commit.
