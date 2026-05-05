# ARCHITECTURE — FloorPlan6

> **Cel projektu:** ArchiCAD addon dla architektów. Workflow od działki do gotowego rzutu mieszkania, w 4 etapach.
>
> **Język:** Python 3.10+ (logika algorytmów). Po stabilizacji — port do C++ ArchiCAD addon (FloorPlan4_CPP jako referencja UI/AC bridge).

---

## WORKFLOW WYSOKOPOZIOMOWY (4 ETAPY)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ETAP 1: ANALIZATOR DZIAŁKI                                          │
│  Wejście:  działka z ArchiCAD (poligon) + parametry MPZP             │
│  Wyjście:  strefa budowlana, footprint(y) budynków, podział działek  │
│  Status:   ⏸️  ODŁOŻONE (czekamy na decyzje Q1-Q5)                    │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ETAP 2: GENERATOR BRYŁ                                              │
│  Wejście:  footprint + liczba pięter + dach                          │
│  Wyjście:  bryła 3D                                                  │
│  Status:   ⏸️  NIE ZACZĘTE                                            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ETAP 3: PODZIAŁ PIĘTRA NA MIESZKANIA                                │
│  Wejście:  obrys piętra + mix M1-M5 + klatka schodowa               │
│  Wyjście:  poligony mieszkań                                         │
│  Status:   ✅ DZIAŁA W C++ (etap 3 Floor mode, 6/6 testów)           │
│            🟡 W Pythonie nie zaczęty (port z C++ TBD)                │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ETAP 4: RZUTY MIESZKAŃ ⭐ FOCUS PIERWSZEJ SESJI                     │
│  Wejście:  poligon mieszkania + typ M1-M5 + entry_point              │
│  Wyjście:  rozkład pokoi (pokoje + drzwi + ściany)                   │
│  Status:   🟡 36/36 testów w FP4 Python (do weryfikacji)             │
│            ❌ Łazienka 13m² w C++ (do naprawy w pierwszej sesji FP6) │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  EKSPORT DO ARCHICAD                                                 │
│  Tapir Add-On (port 19723) → CreateZones → strefy w AC               │
│  (Python Palette w AC = nadbudowa Tapira, dla end-usera)             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## STRUKTURA FOLDERÓW FloorPlan6

```
FloorPlan6/
├── CLAUDE.md                  ← orientacja, kolejność czytania docs
├── MASTER_PROMPT_etap4.md     ← prompt do wklejenia w Claude Code (sesja 1)
├── requirements.txt
├── .gitignore
├── main.py                    ← entry point CLI
├── config.py                  ← stałe globalne
├── run_archicad.py            ← runner przez Tapir
│
├── core/                      ← logika algorytmów
│   ├── models.py              ← dataclasses: Boundary, Room, FloorPlan, Template, Strefa
│   ├── boundary_analyzer.py   ← detekcja notchy, fasad, entry
│   ├── template_selector.py   ← wybór szablonu (constraint M1-M5)
│   ├── cpsat_solver.py        ← OR-Tools CP-SAT, scale=100, Coverage==
│   ├── trapezoid_handler.py   ← inscribed_rect + stretch + clip
│   ├── variant_generator.py   ← topology blocking dla wariantowości
│   ├── validator.py           ← post-clip validation (F1-F10)
│   └── scorer.py              ← ocena wariantów
│
├── bridge/                    ← most do ArchiCAD
│   ├── tapir_connection.py    ← singleton ACConnection, port 19723
│   ├── boundary_reader.py     ← odczyt obrysu z AC
│   └── plan_writer.py         ← export rzutu jako strefy AC
│
├── viz/
│   └── plan_renderer.py       ← matplotlib rendering — KLUCZOWE dla debugu
│
├── ui/
│   └── main_window.py         ← PyQt5 — lokalny test bez AC
│
├── tests/
│   ├── test_cpsat_solver.py   ← 9 testów (basic_tiling, hub_adjacency, facade, vertical)
│   ├── test_e2e.py            ← end-to-end
│   └── test_gui.py            ← smoke test GUI
│
├── templates/                 ← constraint templates (CO ma być)
│   ├── M1_standard.json
│   ├── M2_standard.json
│   ├── M3_standard.json
│   ├── M3_wc.json
│   ├── M4_standard.json
│   ├── M4_2laz.json
│   └── M5_standard.json
│
├── data/                      ← dataset referencyjny
│   ├── all_71_apartments.json ← 71 mieszkań (metraże, bez geometrii)
│   ├── stats_cache.json
│   ├── dataset_loader.py
│   ├── dataset_stats.py
│   └── plans/                 ← 27 sparametryzowanych z grafem ⭐
│       ├── PL_NL_01.json
│       ├── PL_NL_02.json
│       ├── ... (27 plików)
│       └── PL_TVR_25.json
│
├── docs/                      ← dokumentacja strategiczna
│   ├── FUNDAMENTAL_RULES.md   ← F1-F10 + B1-B10 — ŚWIĘTE
│   ├── LESSONS_LEARNED.md     ← 5 wzorców + 6 błędów
│   ├── ARCHITECTURE.md        ← ten plik
│   ├── TEMPLATES_GUIDE.md     ← 3 zestawy szablonów — kiedy którego
│   ├── OPEN_QUESTIONS.md      ← Q1-Q5 + nowe
│   └── STATE.md               ← co działa/nie działa/odłożone
│
├── notebooks/                 ← Jupyter — iteracja algorytmów
│   └── (puste, do utworzenia per zadanie)
│
└── rzuty/                     ← (rezerwa na rzuty/templates niedokończone z FP4)
```

---

## MODUŁY — I/O I ZALEŻNOŚCI (ETAP 4)

### `core/models.py`
**Co zawiera:** dataclasses i enumy.
- `Strefa` (DZIENNA, NOCNA, USLUGOWA, KOMUNIKACJA)
- `RoomSpec` (id, nazwa, strefa, min_powierzchnia, min_szerokosc, wymaga_okna, …)
- `Template` (typ_mieszkania, pokoje: list[RoomSpec], sasiedztwo: list[dict])
- `Boundary` (polygon, entry_point, bbox, area, facade_edges, notches)
- `Room` (spec, polygon, area, proportion)
- `FloorPlan` (boundary, template, rooms, score, hub_percent)

### `core/boundary_analyzer.py`
**Wejście:** Shapely `Polygon` + `entry_point: tuple[float, float]`
**Wyjście:** `Boundary` z wykrytymi notchami i fasadami
**Funkcja:** `analyze_boundary(polygon, entry_point) → Boundary`

### `core/template_selector.py`
**Wejście:** typ mieszkania ("M2"/"M3"/...), `Boundary`
**Wyjście:** `list[Template]` — kandydaci do solvera
**Funkcja:** `select_templates(mtype, boundary) → list[Template]`, `load_all_templates() → list[Template]`

### `core/cpsat_solver.py` ⭐ NAJWAŻNIEJSZY
**Wejście:** `Template` + `Boundary`
**Wyjście:** `CpsatResult(status, rooms: list[Room])`
**Constraints:**
- `Coverage equality` — `sum(areas) == usable_area` (P1)
- Pokoje w bbox boundary
- Hub adjacency ≥ 90cm
- Window rooms touch facade
- Aspect ratio ≤ 2.5
- min_powierzchnia, min_szerokosc per pokój
- **MAX powierzchnia (łazienka 5m²)** ← TO MUSI BYĆ DODANE jeśli brakuje (F2)

### `core/trapezoid_handler.py`
**Wejście:** trapezowy `Boundary`
**Wyjście:** `inscribed_rect` + funkcje stretch/clip
**Algorytm:** wpisz prostokąt → solver → rozciągnij brzegowe → clip do obrysu

### `core/variant_generator.py`
**Wejście:** `Template`, `Boundary`, `n_variants: int`
**Wyjście:** `list[FloorPlan]` z różnymi rozkładami
**Mechanizm:** topology blocking — po każdym variant, blokuj kwadrant gdzie był salon → następny variant ma inny układ

### `core/validator.py`
**Wejście:** `FloorPlan`
**Wyjście:** `ValidationResult(is_valid: bool, violations: list[str])`
**Sprawdza:** F1 coverage, F2 łazienka 5m², F3 min, F7 proporcje, F10 max powierzchnia
**KLUCZOWE:** asercje na MAX (nie tylko MIN). Jeśli nie ma — dodaj.

### `core/scorer.py`
**Wejście:** `FloorPlan`
**Wyjście:** `score: float`
**Komponenty:** odchylenie od opt_powierzchnia, fasada, orientacja, hub compactness

### `bridge/tapir_connection.py`
**Co robi:** singleton połączenia AC. Komendy Tapir:
- `GetSelectedElements`
- `GetDetailsOfElements`
- `CreateZones`

### `bridge/boundary_reader.py`
**Wejście:** TapirConnection
**Wyjście:** Shapely `Polygon` z zaznaczonego elementu w AC

### `bridge/plan_writer.py`
**Wejście:** `FloorPlan` + offset
**Wyjście:** lista GUID-ów stref utworzonych w AC

---

## DATAFLOW PRZY GENEROWANIU 1 RZUTU

```
USER w AC: zaznacza poligon mieszkania, klika "Generuj M3"
   ↓
bridge/boundary_reader.py
   • TapirConnection.get_selected_elements()
   • → polygon: Shapely Polygon
   • → entry_point: (x, y)
   ↓
core/boundary_analyzer.analyze_boundary(polygon, entry_point)
   • detect notches (W4)
   • detect facades (F9)
   • → Boundary
   ↓
core/template_selector.select_templates("M3", boundary)
   • → [M3_standard, M3_wc] (2 kandydaci)
   ↓
core/variant_generator.generate(template, boundary, n=4)
   • dla każdego template:
     • dla każdego variant slot:
       • core/cpsat_solver.solve_cpsat(template, boundary)
         • Coverage equality (W1)
         • scale=100 (W2)
         • F1-F10 jako constraints
       • core/validator.validate(plan)
         • F1, F2 (max!), F3, F7, F10
       • core/scorer.score(plan)
       • topology blocking (W3) → następna iteracja
   • → [FloorPlan, FloorPlan, FloorPlan, FloorPlan] sortowane po score
   ↓
viz/plan_renderer.render_floor_plan(plans[0], save_path="preview.png")
   • matplotlib z legendą stref + pokój centroids
   • → preview.png
   ↓
USER patrzy na preview, akceptuje
   ↓
bridge/plan_writer.export_plan_to_archicad(plans[0], offset)
   • TapirConnection.create_zones(zones_data)
   • → list[guid]
```

---

## ROLE FLOORPLAN4_CPP W FloorPlan6

**FloorPlan4_CPP NIE jest wyrzucony.** Pozostaje jako:

1. **Referencja UI/AC bridge** — paleta przycisków, dialog MPZP (32720 GDLG), zone insertion patterns (BADPOLY fix). Po stabilizacji Pythona → port logiki Pythonowej do C++ z zachowanym UI.
2. **Etap 3 Floor mode** — działa, 6/6 testów. Można odpalić niezależnie.
3. **Etap 1 MPZP analyzer numeryczny** — działa, można cytować logikę przy reimplementacji w Python.
4. **Negative example** — Plot Subdivider buggy (4 bugi), łazienka 13m² — patrz `LESSONS_LEARNED.md`.

**Zasada:** kod C++ tylko do CZYTANIA. Jeśli musisz zmienić logikę — zmień w Pythonie, potem zport do C++.

---

## ZALEŻNOŚCI ZEWNĘTRZNE

| Pakiet | Wersja | Po co |
|--------|--------|-------|
| `or-tools` | ≥9.7 | CP-SAT solver |
| `shapely` | ≥2.0 | geometria 2D, intersection, buffer, clipping |
| `matplotlib` | ≥3.7 | wizualizacja rzutów (debug + preview) |
| `pyqt5` | ≥5.15 | lokalny GUI (test bez AC) |
| `archicad` | (pip oficjalny Graphisoft) | komunikacja z AC |
| `pytest` | ≥7.0 | testy |
| `numpy` | ≥1.24 | array math |

Dla iteracji algorytmów (etap 1 Plot Subdivision):
| `jupyter` | dowolna | notebook do iteracji |

---

## SUMMARY ONE-LINER

**4 etapy: działka→bryła→piętro→mieszkania→AC. FloorPlan6 startuje od etapu 4 (rzuty, naprawa łazienki). Coverage==, scale=100, F1-F10 święte. C++ jako referencja, port później.**
