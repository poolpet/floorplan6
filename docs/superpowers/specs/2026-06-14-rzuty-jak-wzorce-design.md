# Spec: generator rzutów „jak wzorce" (dataset_raw)

**Data:** 2026-06-14 · **Autor sesji:** Claude + Dawid · **Status:** do akceptacji

## 1. Cel (po ludzku)

Algorytm ma dla **takich samych obrysów** jak wzorce z `schematics/dataset_raw`
generować **takie same układy** jak architekt. Cel etapowy (decyzja Dawida):
1. **Faza „typ"** — układ rozpoznawalny jako ten sam rodzaj rzutu (te same strefy,
   realna liczba i wielkość pokoi, schody zabiegowe, okna od właściwych stron).
2. **Faza „docisk"** — dokręcanie geometrii do konkretnego wzorca (miarą nakładania pokoi).

## 2. Co ustaliliśmy (decyzje z brainstormingu)

- **Najpierw fundament pomiaru** dla obu światów (domy + mieszkania), potem strojenie.
- **Ekstrakcja metodą wizji (Opus)** — model czyta PDF (etykiety, tabela powierzchni,
  łańcuchy wymiarowe, schody, okna), wynik = JSON z geometrią. Hybryda z parsowaniem
  wektorów dopiero w fazie „docisk", jeśli wizja okaże się za mało precyzyjna.
- **Brama jakości = render zwrotny.** Każdy odczytany wzorzec rysuję z powrotem jako PNG;
  Dawid porównuje z oryginałem i potwierdza. **Robimy to dla WSZYSTKICH rzutów** — Dawid
  chce mieć pewność co do każdego, nie tylko pilota.
- **Okna i światło są pierwszorzędne** (definiują układ — reguły F6/F9): wzorzec zapisuje
  pozycje okien oraz które ściany to fasada (światło) vs ściany wewnętrzne w bloku (bez
  światła). Grubość ścian / nośna-vs-działowa — drugorzędne.
- **Reguły F1–F10 i B1–B10 święte.** 2 faile = rewrite. Każda zmiana: pytest + render + benchmark.

## 3. Stan zastany (fakty z analizy)

- `dataset_raw`: ~50–70 unikalnych projektów. `domy jednorodzinne` = **6 domów** (PDF,
  focus etapu 4). `natura_life` ~49 + `konopnickiej` ~25 mieszkań (PDF). `podrecznik` =
  39 stron teorii (materiał poglądowy, NIE do reprodukcji 1:1).
- `data/plans` (27 JSON): wierne geometrycznie **mieszkania** (obrys + poligony pokoi +
  graf drzwi + `wall_type` fasada/wewnętrzna). Pokrywają 43/49 `natura_life`. **0 domów.**
  Uwaga: pole `area_m2` bywa błędne → liczyć powierzchnię z poligonu.
- `notebooks/reference_plans_full.json`: istniejąca ekstrakcja **16 domów**, ale tylko
  **agregaty** (powierzchnie + sąsiedztwa + typ schodów) — **bez pozycji pokoi**. Dlatego
  dzisiejsza miara sprawdza „podobny zestaw pokoi", a nie „ten sam rzut".
- Benchmark `notebooks/reference_benchmark.py`: score `0.5·F1 + 0.3·(1−MAPE) + 0.2·Jaccard`.
  Baseline **60.4/100** na 7 prostokątach. Parter słaby (F1 0.46–0.93), poddasze dobre.
- Trzy rzeczy zdradzają generator: **schody proste** (oryginały: zabiegowe), **rozdęte
  powierzchnie** (za mało pokoi → salon 55–74 m², sypialnie 30–45 m²), **brak garażu/obrysu L/T**.

## 4. Architektura rozwiązania

### 4.1. Wzorzec z geometrią — schemat `notebooks/refs_geo/<name>.json`  (NOWE, fundament)
Per kondygnacja (`storeys[]`):
- `outline` — obrys korpusu (poligon, metry).
- `rooms[]` — `id`, `label`, `polygon` (też L-kształty), `area_m2` (z wymiarów/tabeli), `on_facade`.
- `doors[]` — `between` (2 pokoje, `__outside__` = wejście), `point`, `wall` (v/h), `swing`, `type`.
- `stairs` — `kind` (`u_winder`/`l_winder`/`straight`…), `footprint`, `down`.
- `windows[]` — `seg` (odcinek na obrysie), `room`. **Gdzie wpada światło.**
- `facade_sides` / `internal_walls[]` — które ściany mają światło (dom: wszystkie; blok: część wewnętrzna).
- `entry` — `point`, `side` (parter); `null` dla poddasza.
- `open_plan_day_zone`, `roof_knee_wall` (poddasze).

### 4.2. `notebooks/render_ref_geo.py`  (NOWE, gotowe — brama jakości)
Rysuje wzorzec→PNG: obrys (masa ścian), pokoje (kolor wg funkcji + etykieta + m²),
**okna** (niebieskie, światło), **ściany wewnętrzne** (ciemne, bez światła — mieszkania),
schody (glif zabiegowych + kierunek), drzwi/wejście (łuki), legenda. Wynik → `rzuty/refs_geo/`.

### 4.3. Miara „1:1" — rozszerzenie `reference_benchmark.py`  (NOWE)
Dodać **IoU poligonów pomieszczeń** (po wyrównaniu obrysu, dopasowanie po typie) jako 4. metrykę.
Faza „typ": raportowana obok, waga niska. Faza „docisk": waga rośnie. Plus prawdziwe obrysy
L/T zamiast bbox (`_outline_polygon`).

### 4.4. Strojenie generatora  (`core/house_layout.py`, `core/house_program.py`, `core/cpsat_solver.py`)
- **Schody zabiegowe**: zdjąć `force_straight=True`; renderer rysuje wachlarz (winder).
- **Powierzchnie + liczba pokoi**: więcej, mniejszych pokoi; capy strefy dziennej/sypialni; koniec z „pęcznieniem".
- **Garaż + obrys L/T**: bryła garażu i footprinty L/T dla domów ≥110 m².

## 5. Dataflow

```
PDF wzorca ──(wizja Opus)──> refs_geo/<name>.json ──(render_ref_geo)──> PNG
                                                          │
                                          [BRAMA] Dawid potwierdza odczyt
                                                          │
generator(obrys wzorca) ──> układ ──(benchmark: F1/MAPE/Jaccard/IoU)──> wynik vs wzorzec
                                                          │
                                             pętla strojenia (Etap B)
```

## 6. Kolejność prac (bloki)

- **Blok 1 — Fundament + weryfikacja odczytu (ALL).** Odczytać z geometrią i wyrenderować
  PNG dla wszystkich wzorców: najpierw **6 domów** (≈13 rzutów), potem **mieszkania**
  (27 JSON mają już geometrię → render do weryfikacji + ew. domknąć 6 brakujących `natura_life`).
  Złożyć galerię do akceptacji; poprawić odczyty, które Dawid oznaczy. *Pilot tropie = DONE.*
- **Blok 2 — Miara 1:1.** IoU poligonów + obrysy L/T w benchmarku.
- **Blok 3 — Strojenie „typ".** Kolejno: schody zabiegowe → powierzchnie/liczba pokoi → garaż+L.
- **Blok 4 — Docisk.** Zwiększać wagę IoU, dociskać geometrię; raport postępu vs baseline.

## 7. Poza zakresem (YAGNI)

Meble (tor zamrożony do C++), eksport do ArchiCAD, dokładna grubość ścian / nośna-działowa,
reprodukcja 1:1 stron `podrecznik` (to materiał poglądowy, nie projekty).

## 8. Pytania otwarte

- **PL_TVR** (11 JSON) — z jakiego źródła? W `dataset_raw` brak pasującego folderu.
- 6 brakujących `natura_life` (1, 1-2, 2, 8, J7, K1) — dotrejsować czy pominąć?
- Import geometrii notcha dla obrysów L/T z wymiarów (dziś bbox).
- Czy weryfikację galerii robić partiami (np. po 6) czy całość naraz?
