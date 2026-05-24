# FloorForge / FloorPlan6 — Audit Report

> Audit przeprowadzony 2026-05-08. Punkt odniesienia: wymagania **FloorForge PRO Global** (anglojęzyczny generator wariantów rzutów dla małych biur i deweloperów rezydencyjnych, modularny system Code Packs PL/UK/DE/US, cena 19–29 USD/mc, target ARR 60–120k USD w roku 1).
>
> **Kontekst pracy (2026-05-08):** silnik rozwijany jest w Pythonie ze względu na szybkość iteracji. Port do C++ (natywny addon ArchiCAD 29) zaplanowany dopiero po ustabilizowaniu silnika. W tym audycie sekcje dotyczące C++/launch readiness (instalator, MDID, ACAPI primitive) są oznaczone jako **DEFER do C++ port** i nie są blokerami obecnej iteracji.

---

## 1. Stan kodu

**Stack:** Python 3.10+ (testowany na 3.11/3.12/3.13 w CI), shapely 2.x, OR-Tools CP-SAT, matplotlib, PyQt5, archicad/Tapir.

**Struktura katalogów:**

```
FloorPlan6/
├── core/                ← logika algorytmów (15 modułów)
│   ├── plot_model.py, plot_subdivider.py, plot_verifier.py
│   ├── plot_indicators.py, site_planner.py, site_element_model.py, site_wall_model.py
│   ├── boundary_analyzer.py, buildable_zone.py
│   ├── cpsat_solver.py, validator.py, scorer.py, variant_generator.py
│   ├── trapezoid_handler.py, template_selector.py
│   ├── floor_compute.py, floor_layout.py, floor_validation.py, floor_solver.py
│   └── models.py
├── bridge/              ← Tapir Add-On (port 19723)
│   ├── tapir_connection.py (singleton)
│   ├── boundary_reader.py (Wall/Slab/Zone → Polygon)
│   ├── plan_writer.py (Zones → AC, ZONES ONLY)
│   └── plot_reader.py (Plot wrapper)
├── ui/                  ← PyQt5 (4 zakładki)
│   ├── main_window.py (Stage 4 + tabs orchestrator)
│   ├── stage1_window.py (Stage 1 — Plot Analyser)
│   ├── floor_layout_window.py (Stage 3)
│   └── stage_placeholder.py (Stage 2 placeholder)
├── viz/plan_renderer.py
├── tests/               ← 134 testów zielone (Stage 1+3+4)
├── rules/               ← 19 reguł WT 2002 + user_rules.json (PL only)
├── templates/           ← M1-M5 constraint templates JSON (PL apartment types)
├── data/plans/          ← 27 referencyjnych rzutów PL z grafem sąsiedztwa
├── docs/                ← 9 dokumentów strategicznych
├── notebooks/           ← Jupyter prototypy (etap 1 v1, v2)
├── .github/workflows/test.yml ← CI: pytest na ubuntu, 3 wersje Python
├── CHANGELOG.md, CONTRIBUTING.md, LICENSE (AGPL-3.0)
├── config.py            ← stałe globalne (część reguł hard-coded tutaj)
├── main.py, run_archicad.py
└── requirements.txt
```

**Modele i ich zależności:**

```
ui/main_window.py ──┬─→ ui/stage1_window.py ──→ core/plot_subdivider.py ──→ core/plot_model.py
                    │                       └─→ core/site_planner.py    └─→ shapely
                    │                       └─→ core/plot_verifier.py
                    │                       └─→ core/plot_indicators.py
                    ├─→ ui/floor_layout_window.py ──→ core/floor_layout.py
                    └─→ Stage 4 inline ──→ core/cpsat_solver.py + variant_generator.py
                                       ──→ core/validator.py + scorer.py
                                       ──→ core/template_selector.py + boundary_analyzer.py

bridge/tapir_connection.py (singleton, port 19723)
   ├─ used by: bridge/boundary_reader.py, bridge/plan_writer.py, ui/*
   └─ Tapir AddOn commands: GetSelectedElements, GetDetailsOfElements, CreateZones, GetElementsByType

rules/wt_rules.json (19 reguł WT § 12, 14, 15, 18, 19, 22, 31, 36)
   └─ loaded by: core/plot_verifier.py
config.py
   └─ WT_MIN_AREA, WT_MAX_AREA, WT_MIN_WIDTH, HUB_*, ORIENTATION_QUALITY (HARD-CODED reguły)
   └─ używane przez: core/cpsat_solver.py, core/validator.py, core/scorer.py
templates/M*.json (PL apartment types)
   └─ loaded by: core/template_selector.py
data/plans/PL_*.json (27 reference plans)
   └─ loaded by: data/dataset_loader.py (training/regression)
```

**Brak / nie istnieje:**
- `Sources/` (C++ structure) — projekt jest Python, nie C++
- `MDID`, `.grc/.rc/DLG`, CMakeLists.txt — N/A dla Python
- Plik `EULA`, `PRIVACY.md` — brak
- Schema JSON dla rules — brak (ad-hoc JSON)
- Lokalizacja (.po, i18n) — brak, stringi hard-coded w `.py`

**Stan testów:** 134 passed, 30 skipped, 0 failures (full suite, 2026-05-08). Stage 1: 61 testów. Stage 3: ~30. Stage 4: ~40. Brak end-to-end UI tests (test_gui.py istnieje ale skip-uje na headless CI).

**SDK / API:** `archicad` Python library (oficjalny pip Graphisoft) + `TapirCommand` namespace przez `ExecuteAddOnCommand`. Nie ma bindingu do natywnego ACAPI — wszystkie operacje przez Tapir. Wersja AC: ≥25, target 29.

---

## 2. Audyt funkcjonalności (tabela checklist)

### A. Silnik geometrii i tworzenia ścian/otworów

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| A1 | Tworzenie natywnych ścian | **NIE** | `bridge/plan_writer.py:export_plan_to_archicad` | Generuje **Zones**, nie Walls. Tapir nie ma `CreateWalls` w aktualnym wrapperze; obsługa ACAPI Walls wymaga rozszerzenia `tapir_connection.py`. |
| A2 | Wstawianie drzwi w ścianach | **NIE** | — | Brak. Tapir wystawia tylko `GetDetailsOfElements` na drzwiach (read-only). Pisanie drzwi wymaga ACAPI w C++ porcie, lub rozszerzenia Tapir Add-On. |
| A3 | Wstawianie okien w ścianach | **NIE** | — | Jak A2. |
| A4 | Tworzenie stropów/płyt | **NIE** | — | Stage 2 jest placeholder. `bridge/tapir_connection` nie ma `CreateSlabs`. |
| A5 | Operacje undo/redo | **NIE** | — | Tapir `CreateZones` nie jest w transakcji `ACAPI_CallUndoableCommand`. Każde wywołanie tworzy zone niezależnie. |
| A6 | Multi-storey | **CZĘŚCIOWO** | `core/floor_compute.py`, `core/floor_layout.py` | Stage 3 oblicza `num_floors`, klasę budynku (N/SW/W/WW), klatki schodowe, ale eksport idzie do jednej kondygnacji w AC. |
| A7 | Łukowe / nieproste ściany | **NIE** | — | Cały silnik geometryczny axis-aligned (Shapely Polygon, box). `trapezoid_handler` obsługuje pochyłe boki ale nie łuki. |
| A8 | Mass-creation w transakcji | **CZĘŚCIOWO** | `bridge/plan_writer.py:55` | `tapir.create_zones(zones_data)` przyjmuje listę i tworzy je w jednym wywołaniu, ale nie jest opakowane w explicit ArchiCAD transaction (undoable command). |

### B. Silnik reguł i constraint-solver

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| B1 | Generuje N>1 wariantów | **TAK** | `core/variant_generator.py` | Stage 4 produkuje N wariantów z topology blocking. Stage 1 site_planner.propose_max_buildup → 3 warianty. Stage 1 Mode B → 1 wariant (variant generation TBD). |
| B2 | Reguły oddzielone od kodu | **CZĘŚCIOWO** | `rules/wt_rules.json`, `templates/M*.json`, `config.py` | 19 reguł WT 2002 jest external (`rules/wt_rules.json`). Templates M1–M5 też. **Ale**: F1–F10 są hard-coded w `core/cpsat_solver.py` i `core/validator.py`. `WT_MAX_AREA`, `WT_MIN_AREA`, `WT_MIN_WIDTH`, `HUB_*` w `config.py`. |
| B3 | Parametryzacja obrysu | **TAK** | `core/boundary_analyzer.py`, `core/plot_model.py` | `Boundary` dla mieszkań, `Plot/PlotBoundary` dla działek, `analyze_boundary` wykrywa wcięcia (notches), fasady, klasyfikuje krawędzie. |
| B4 | Constraint solver dla min powierzchni pokoi | **TAK** | `core/cpsat_solver.py:140+` | OR-Tools CP-SAT, scale=100 (cm), `Coverage equality`, F2 hard cap, F3 min, F7 aspect, hub adjacency ≥90 cm. |
| B5 | Walidacja doświetlenia | **NIE** | — | Brak weryfikacji `pow_okien / pow_podlogi ≥ 1/8` (WT § 57.2). Krytyczne dla PL i UK. |
| B6 | Walidacja min szerokości komunikacji | **CZĘŚCIOWO** | `core/floor_validation.py`, `config.py:WT_CORRIDOR_*` | Stage 3 sprawdza `corridor_width ≥ WT_CORRIDOR_PUBLIC_MIN=1.4` (WT §237). Stage 4 ma `min_szerokosc` per pokój w solverze. Brak walidacji ewakuacji w Stage 4. |
| B7 | Walidacja zgodności WT/BR/BauO/IBC | **CZĘŚCIOWO** | `core/plot_verifier.py`, `core/validator.py` | **Tylko PL.** 19 reguł WT 2002 w Stage 1 verifier + F1–F10 + WT_MAX_AREA w Stage 4 validator. UK BR / DE BauO / US IBC: brak. |
| B8 | Raport zgodności | **TAK** | `core/plot_verifier.py:VerificationResult` | dataclass z `rule_id`, `name`, `status`, `designed_value`, `required_value`, `description`, `legal_basis`, `plot_number`. UI wyświetla per pomieszczenie/wariant. |

### C. Modularyzacja Code Packs

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| C1 | Reguły external | **CZĘŚCIOWO** | `rules/*.json` | Jak B2: tylko **część** reguł (Stage 1 verifier 19 reguł) jest external. F1–F10, WT_MAX_AREA, templates są w kodzie/JSON ale tightly coupled z PL. |
| C2 | Dodanie nowego kraju bez rekompilacji | **NIE** | — | Niemożliwe obecnie. Powody: (1) `BoundaryType` enum hardcoded ("DROGA", "SASIAD_ZABUDOWANY" — PL terms); (2) `HousingType` enum hardcoded (JEDNORODZINNA/WIELORODZINNA — PL only); (3) `_verify_indicators` w plot_verifier hardcoded mapuje "wz", "wiz", "pbc"; (4) F1–F10 w solverze; (5) templates M1–M5 to PL apartment types. |
| C3 | Code-pack ma identyfikator + wersję + locale | **NIE** | `rules/wt_rules.json:wersja:"1.0"` | Jest `wersja:"1.0"` i `zrodlo` (cytat ustawy) na poziomie wholego pliku, ale brak `code_pack_id`, `country_code`, `locale`, `version_compat`. |
| C4 | Toggle UI | **NIE** | — | UI nie ma dropdown/listy code-packs. Wszystkie reguły ładowane zawsze. |
| C5 | ≥2 code-packi POC | **NIE** | — | Tylko PL. Brak nawet szkieletu UK/DE/US. |
| C6 | Dokumentacja reguł | **CZĘŚCIOWO** | `docs/WT_PARAMETERS.md`, `docs/FUNDAMENTAL_RULES.md` | Reguły WT mają cytaty paragrafów w JSON (`podstawa_prawna`). F1–F10 udokumentowane w `FUNDAMENTAL_RULES.md`. **Ale**: brak JSON Schema, brak formalnego "code pack contract". |

### D. Lokalizacja i UI

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| D1 | UI ma PL string table | **NIE** | — | Stringi PL są **hardcoded** w `.py` (np. `ui/stage1_window.py:107` `QLabel("Wskaźnik zabudowy max (WZ):")`). Brak external string table. |
| D2 | UI ma EN string table | **NIE** | — | Stringi EN też hardcoded w `.py` (np. Stage 3 widget używa "Floor outline", "Generate"). Brak external. |
| D3 | System lokalizacji skalowalny | **NIE** | — | Brak gettext, .po, JSON i18n. Każdy język = manual edit kodu. |
| D4 | Stringi wyciągnięte do zasobów | **NIE** | — | 100% stringów hardcoded w `.py`. Zarówno UI labels, tooltips, error messages, log strings. |
| D5 | Modeless palette na DPI ≥150% | **?** | — | Nie testowane systematycznie. Qt5 ma ogólnie dobry High-DPI support na macOS/Windows ale brak walidacji. |
| D6 | Dark mode AC | **CZĘŚCIOWO** | `ui/stage1_window.py:170-175` (info_lbl) | Naprawiono kontrast info_lbl (białe tło + czarny tekst, explicit). Reszta UI używa Qt Fusion style ze standardowymi kolorami — zgodność z dark mode AC nie testowana. |
| D7 | Zapisz/wczytaj preset | **NIE** | — | Brak save/load JSON z parametrami projektu. Każde uruchomienie = ręczne wpisywanie. |

### E. Eksport, integracje, ekosystem

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| E1 | Natywne BIM elements | **CZĘŚCIOWO** | `bridge/plan_writer.py` | Eksport jako **Zones** (natywne BIM) — TAK. Walls/Doors/Slabs — NIE. Architekt dostaje obrysy pomieszczeń, nie geometrię budowlaną. |
| E2 | Export PDF | **NIE** | — | Brak. Z Pythona to byłoby `reportlab` (~5 dni), w C++ porcie inne narzędzie. |
| E3 | Export Excel/CSV | **NIE** | — | Brak. Architekci żądają tabel powierzchni (PUM, mix M1–M5, summary). Generic Python solution szybki. |
| E4 | Twinmotion 1-click | **NIE** | — | Brak. To byłaby integracja przez ArchiCAD-Twinmotion live link albo direct export do `.tm` — krytyczne dla UK rynku ale nice-to-have w MVP. |
| E5 | AI Visualizer (AC 28+) | **NIE** | — | Brak. Wbudowane w AC, integracja przez ACAPI w C++ porcie. |
| E6 | Hook na zmianę elementu | **NIE** | — | Brak. To byłby ACAPI notification handler — domena C++ portu. |
| E7 | Schedule / karta mieszkania | **NIE** | — | Brak. Powiązane z E3 (CSV export). |

### F. Licencjonowanie, bezpieczeństwo, telemetria

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| F1–F7 | (wszystko) | **NIE / DEFER** | — | Brak licencjonowania, trial, telemetrii, crash reporter, auto-update. **Per decyzja produktowa: defer do C++ port** — w Pythonie prototyp dla developera, monetyzacja zaczyna się po porcie. |

### G. Build, DevOps, kompatybilność

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| G1 | macOS Apple Silicon | **TAK** | `requirements.txt` | Działa natywnie na Apple Silicon (Python 3.13, shapely 2.x, OR-Tools są dostępne arm64). Bieżące dev środowisko = M-series Mac. |
| G2 | Windows x64 | **?** | — | Nie testowane przez autora, ale Python+wszystkie dependencies są cross-platform. Wymaga walidacji w CI (obecnie tylko ubuntu). |
| G3 | AC 28 + AC 29 | **CZĘŚCIOWO** | `bridge/tapir_connection.py:ARCHICAD_PORT=19723` | Tapir Add-On używa stałego portu, kompatybilność zależy od wersji Tapir Add-On (instalowanego z AC). Powinno działać dla AC 28 + 29 jeśli Tapir wspiera. |
| G4 | MDID zarejestrowany | **NIE / DEFER** | — | MDID dotyczy C++ addonów. Python prototype nie wymaga. |
| G5 | CI/CD | **CZĘŚCIOWO** | `.github/workflows/test.yml` | GitHub Actions: `pytest` na 3 wersjach Python (3.11/3.12/3.13), tylko `ubuntu-latest`. Brak macOS/Windows runners. Brak release pipeline. |
| G6 | Versioning + changelog | **CZĘŚCIOWO** | `CHANGELOG.md` | Format Keep a Changelog. Aktualnie tylko `[Unreleased]` — brak tagged releases / semver tags. |
| G7 | Instalator | **NIE / DEFER** | — | Python prototype = `python -m venv` + `pip install -r requirements.txt`. Instalator (.dmg/.msi/Add-On Manager) dotyczy C++ portu. |

### H. Dokumentacja i support

| # | Funkcjonalność | Status | Plik/klasa | Komentarz |
|---|---|---|---|---|
| H1 | README EN | **TAK** | `README.md` (10kb) | README jest po angielsku — landing page, install, run instructions. |
| H2 | User documentation | **CZĘŚCIOWO** | `README.md`, `MASTER_PROMPT_etap4.md` | README zawiera "How to use" dla Stage 4. Stage 1/3 nie są opisane end-user. Brak step-by-step "Generate your first plan". |
| H3 | Developer documentation | **TAK** | `docs/ARCHITECTURE.md`, `docs/FUNDAMENTAL_RULES.md`, `docs/LESSONS_LEARNED.md`, `CONTRIBUTING.md` | Bardzo dobre dla developera (architektura, F1–F10, wzorce, lekcje). Brak natomiast "How to add a code-pack" tutorial. |
| H4 | Schema reguł | **NIE** | — | `rules/wt_rules.json` ma format ad-hoc. Brak JSON Schema (`$schema`, validation), brak typescript-ish IDL dla code-pack contract. |
| H5 | Sample code-pack referencyjny | **CZĘŚCIOWO** | `rules/wt_rules.json` | PL pack istnieje. Brak drugiego (UK/DE/US) jako wzór. Brak `rules/README.md` opisującego format. |
| H6 | EULA / licencja | **TAK** | `LICENSE` | AGPL-3.0. Plus brak osobnej EULA dla użytkownika końcowego (irrelewantne przy AGPL open source). |
| H7 | Privacy policy | **NIE / DEFER** | — | Nie potrzebne dopóki nie ma telemetrii (F4). Defer do C++ port. |

---

## 3. Analiza luk vs. priorytety

### 3.1 Co jest gotowe i mocne (5 punktów)

1. **Stage 4 apartment generator (CP-SAT) — 80/80 testów zielone.** OR-Tools, scale=100 (cm, eliminuje float bugs), F1 Coverage equality, F2 hard cap łazienki 5m², F3 min, F7 aspect 2.5, hub adjacency 90 cm. Solid foundation, kluczowy USP "generuje warianty natywnie w AC".
2. **Stage 1 plot verifier — 19 reguł WT 2002 z pełnymi paragrafami.** External JSON (`rules/wt_rules.json`), `VerificationResult` ze strukturą `legal_basis`, pasmo ostrzeżenia 5% z flag `strict` (Q14 decision), gating Q13/Q17 dla wielorodzinnej i kanalizacji miejskiej.
3. **Architektura 4-etapowa (1 plot → 2 volume → 3 floor → 4 apartment).** Logicznie spójna, moduły separated, każdy stage ma własne models/algorithms/UI. Skalowalna na nowe kraje (po refactoringu modularyzacji).
4. **Tapir bridge — działa end-to-end.** Read Wall/Slab/Zone → Polygon, Write Zones. Ścieżka AC → algorytm → AC potwierdzona, sesja interaktywna z architektem.
5. **134 testów + dokumentacja strategiczna.** `docs/FUNDAMENTAL_RULES.md` (F1–F10), `docs/LESSONS_LEARNED.md` (5 patterns + 6 mistakes), `docs/OPEN_QUESTIONS.md` (Q1–Q18 z DECIDED) — pozwala nowym contributorom (lub mi w przyszłej sesji) szybko wrócić w kontekst.

### 3.2 Czego krytycznie brakuje na 90-day MVP global

> Założenie: silnik nadal w Pythonie, port C++ po MVP. Effort w person-days.

| # | Luka | Effort | Blokuje launch | Refactor architektoniczny? |
|---|---|---|---|---|
| **L1** | **Modularyzacja Code Packs** — wszystkie reguły do `rules/{country}/*.json` (PL pack, UK pack POC). Wyciąć F1–F10 i `WT_MAX_AREA` z kodu. | 8–12 dni | **TAK** | TAK (refactor solver/validator żeby konsumowały rules, nie hardcoded) |
| **L2** | **Internationalization (i18n)** — wszystkie stringi do `locale/{lang}.json` (PL, EN min). Wsparcie dla gettext-ish lookup. | 5–7 dni | **TAK** | TAK (refactor wszystkich UI files) |
| **L3** | **Eksport ścian + drzwi do AC** — rozszerzenie `bridge/plan_writer` o `create_walls`, `create_doors`. Wymaga Tapir Add-On rozbudowy lub bezpośredniego ACAPI bypassa (problem: Python nie ma natywnego ACAPI). | 10–15 dni | **TAK** dla architektów (Zones-only output to "demo", nie produkcja) | TAK |
| **L4** | **Walidacja doświetlenia (B5)** — `pow_okien / pow_podlogi ≥ 1/8`. Krytyczna PL+UK reguła. | 4–6 dni | TAK dla pełnego compliance pack | NIE (dodatek do verifier) |
| **L5** | **JSON Schema dla code packs + dokumentacja "How to add a country pack"** | 2–3 dni | NIE strictly, ale wymagane dla społeczności contributor / drugich code-packów | NIE |
| **L6** | **Drugi code-pack POC (UK Building Regs)** — proof że modularność działa, równolegle ładowane PL + UK. | 7–10 dni (zakłada L1) | NIE bezpośrednio, ale wymagane dla "Global" roadmap | NIE |
| **L7** | **Schedule / CSV export** (powierzchnie M1–M5, mix, headroom). | 3 dni | NIE | NIE |
| **L8** | **Save/load presets** (parametry projektu jako JSON). | 2 dni | NIE | NIE |

**Suma effort krytyczny (L1+L2+L3+L4):** 27–40 dni dev. **Plus** L5+L6+L7+L8: 14–18 dni.

### 3.3 Co wymaga refactoru przed dodaniem Code Packs (UK/DE/US)

**Krytyczne wymuszone przez wymagania C2 (modularność bez rekompilacji):**

1. **Wyciąć F1–F10 z kodu Python do rules/{pack}/fundamental.yaml**
   - Obecnie: `core/cpsat_solver.py:140` ma `model.add(sum(areas) == usable_area)` (F1 Coverage), `cpsat_solver.py:~310` ma F2 cap (`area <= WT_MAX_AREA[room_id]`), `validator.py` ma F1/F2/F7 strict checks.
   - Po refactorze: solver konsumuje "constraints" listę z rules, applies them genericly. Reguły jak F1 są w pliku WT pack jako `{"id":"F1", "type":"coverage_equality", "scope":"all"}`.

2. **Wyciąć `config.py` consts (`WT_MIN_AREA`, `WT_MAX_AREA`, `WT_MIN_WIDTH`, `HUB_*`, `WT_CORRIDOR_*`, `WT_BUILDING_CLASS_THRESHOLDS`) do `rules/PL/*.json`**
   - Obecnie ~60 stałych w `config.py` to PL-specific, hardcoded.
   - Po refactorze: `config.py` ma tylko Python-runtime constants (np. `SCALE=100` dla cm). Wszystkie reguły w JSON pack.

3. **Refactor `BoundaryType` i `HousingType` enums → string-id z external locale**
   - Obecnie: `BoundaryType.DROGA = "DROGA"` (PL term wbudowany).
   - Po refactorze: `BoundaryType.PUBLIC_ROAD = "PUBLIC_ROAD"`, locale `{"PL": "Droga publiczna", "EN": "Public road"}`.

4. **Apartment types M1–M5 → pack-specific**
   - Obecnie: `templates/M1_standard.json` (PL "kawalerka"). UK używa "studio/1-bed/2-bed/3-bed". DE używa "1-Zi-Wohnung / 2-Zi-Wohnung".
   - Po refactorze: `rules/{pack}/apartment_types/*.json` z lokalnymi nazwami i WT-equivalents.

5. **Apartment mix defaults (`APARTMENT_MIX_DEFAULT` w config.py)**
   - Obecnie PL-specific (M1: 10%, M2: 30%, M3: 40%, ...). Każdy kraj ma inną typową mix-ę.
   - Po refactorze: pack-specific defaults w JSON.

**Mniej krytyczne:**

6. **PL paragraphy (`§ 12 WT`) w `legal_basis`** — zostają bezpośrednio w PL pack (cytaty oficjalne, nie tłumaczone). To OK — UK pack będzie mieć "Reg. K1 Building Regulations" itd.
7. **Komunikaty błędów po PL w `core/validator.py`** (np. `"F2: bathroom > 5m²"`) — wyciągnąć do i18n (L2).

### 3.4 Ryzyka techniczne

1. **Brak walidacji doświetlenia (B5)** — krytyczna reguła PL § 57.2 (`pow_okien / pow_podlogi ≥ 1/8`) + UK BR Part F. Bez tego raporty zgodności są niekompletne. Architekci zauważą natychmiast.
2. **Tapir Add-On dependency** — kompatybilność z AC 28/29 wymaga że Graphisoft utrzyma Tapir kompatybilny. Jeśli AC 30 zmieni Tapir API, FP6 broken. Mitigacja: w C++ porcie iść na natywny ACAPI, omijać Tapir.
3. **Eksport tylko Zones, brak Walls/Doors/Windows (A1–A3)** — z perspektywy architekta, "rzut" w AC bez ścian to nie rzut. To jest może największy gap relevant do USP "natywny generator w AC".
4. **CI tylko ubuntu** (G5) — brak walidacji macOS/Windows. PyQt5 czasem ma platform-specific bugi.
5. **CP-SAT dla nowych krajów** — UK BR ma mocno różne requirements niż PL (np. minimum apartment 37 m² UK vs 25 m² PL kawalerka). Solver może wymagać tuningu lub re-design dla niektórych code-packów. Risk: po L1 (modularyzacja) pierwsze próby UK pack mogą wykazać że "rules są modularne ale solver nie".
6. **CP-SAT performance** — Stage 4 dla M5 (8 pokoi) może być wolny (kilka sekund). Skalowanie na duże mieszkania (apartamenty 10+ pokoi w UK luxury) niepewne.
7. **Brak end-to-end UI tests** — `tests/test_gui.py` skip-uje na headless CI, więc UI nigdy nie testowany w CI. Regresje w UI łatwo prześlizgną.
8. **`config.py` jest mocno coupled** — jeśli ruszymy z modularyzacji (L1), wiele plików musi być poprawione równocześnie.

---

## 4. Rekomendacje (10 punktów, P0/P1/P2)

> Założenie: praca w Pythonie, C++ port deferred. Effort w person-days dla solo developera.

> **[P0]** **L1 — Modularyzacja Code Packs.** Wyciąć F1–F10, `WT_MAX_AREA`, `WT_MIN_*`, `HUB_*`, `APARTMENT_*` z `config.py` i kodu solver/validator do `rules/PL/*.json`. Effort: **8–12 dni**. Umożliwia: dodawanie krajów bez Python-edits.

> **[P0]** **L5a — JSON Schema dla code-pack contract.** Formalna specyfikacja co code-pack musi zawierać (id, version, locale, rules[], apartment_types[], boundary_types[], …). Effort: **2 dni**. Umożliwia: walidację code-packów przy load, dokumentację dla contributors.

> **[P0]** **L2 — i18n system.** Wszystkie stringi UI + komunikaty błędów do `locale/{en,pl}/messages.json`. Lookup helper w `core/i18n.py`. Default fallback EN. Effort: **5–7 dni**. Umożliwia: launch global, EN as default.

> **[P0]** **L3 — Eksport ścian + drzwi (Walls + Doors)** przez Tapir Add-On. Wymaga rozszerzenia samego Tapir Add-On o `CreateWalls` / `CreateDoors` (sprawdzić czy istnieje, jeśli nie — push do upstream lub napisać forka). Effort: **10–15 dni**. Umożliwia: prawdziwie BIM-native output, USP "natywny generator w AC".

> **[P0]** **L4 — Walidacja doświetlenia.** Per pomieszczenie sprawdza `pow_okien_z_template / pow_podlogi`. Dodaje regułę `wt_020_doswietlenie` do PL pack (1/8 dla mieszkalnych, 1/12 dla pomocniczych). Reguła przenośna na UK BR Part F. Effort: **4–6 dni**. Umożliwia: pełne compliance reports.

> **[P1]** **L6 — UK Building Regs code-pack POC** jako proof modularności. Min: front-of-house min sizes, min apartment area 37 m², minimum bedroom area 6.51 m² single / 10.22 m² double, kitchen-living standards. Effort: **7–10 dni** (po L1+L5). Umożliwia: drugi market validated, modularność technicznie potwierdzona.

> **[P1]** **L7 — Schedule + CSV export.** `core/exporter.py` → CSV z kolumnami: apartment_id, type (M1–M5 / studio / 1-bed), powierzchnia, mix, hub %, room areas. Effort: **3 dni**. Umożliwia: deweloperzy widzą bilans od razu, marketing.

> **[P1]** **L8 — Save/load preset.** Każdy projekt FP6 ma `project.json` z parametrami MPZP, mix, building params, paths. UI button "Save / Load preset". Effort: **2 dni**. Umożliwia: powtarzanie projektów, sharing presetów między architektami.

> **[P1]** **CI cross-platform + UI smoke tests.** Dodaj macOS-latest i windows-latest do GitHub Actions matrix. Stwórz minimalny `tests/test_ui_smoke.py` używający Qt Test framework + offscreen rendering. Effort: **3 dni**. Umożliwia: catching platform/UI regressions wcześnie.

> **[P2]** **PDF report (reportlab)** + **AI Visualizer / Twinmotion integration**. Zewnętrzne integracje. Effort: **5–10 dni each**. Defer do post-launch — najpierw pewność że core compliance działa.

---

## 5. Roadmapa wynikowa (90-day MVP, kolejność)

```
Dzień 1–14   ──→ L1 + L5a (modularyzacja + schema)            [P0]
Dzień 15–21  ──→ L2 (i18n)                                    [P0]
Dzień 22–25  ──→ L4 (doświetlenie)                            [P0]
Dzień 26–40  ──→ L3 (Walls + Doors export)                    [P0]
Dzień 41–50  ──→ L6 (UK BR POC pack)                          [P1] — proof of modularity
Dzień 51–55  ──→ L7 + L8 (CSV export + presets)               [P1]
Dzień 56–60  ──→ CI cross-platform + UI smoke tests           [P1]
Dzień 61–80  ──→ Buffer + bug bashing + UX polish + dokumentacja
Dzień 81–90  ──→ Beta testing z 5 architektami PL + 3 UK,
                  iteracja na podstawie feedback
```

**Po dniu 90:** Decyzja go/no-go na C++ port. Jeśli silnik Python jest stabilny + ma 2 code packi (PL+UK) + EN UI + Walls+Doors export — gotowość do C++ portu.

---

## 6. Open questions zostawione przez audyt

1. **Czy Tapir Add-On wystawia `CreateWalls` / `CreateDoors`?** Jeśli nie, alternatywy: (a) zgłosić feature do Tapir maintainers, (b) napisać forka, (c) bypass via natywny ACAPI w C++ porcie (ale to duplikuje pracę).
2. **Czy port C++ powinien dziedziczyć Python rules engine (load JSON same way) czy mieć własny?** Jeśli ten sam JSON, fewer reguly drift. Jeśli osobny, więcej swobody ale risk divergence.
3. **Jaki mechanizm licencji w C++ porcie?** (Paddle? Stripe? Własny serwer?) — wpływa na F1–F3, ale defer.
4. **Czy AGPL-3.0 (obecnie) zostanie dla wersji komercyjnej?** AGPL silnie ogranicza komercyjną re-dystrybucję. Dual-licensing (AGPL + commercial) jest typowy dla SaaS-like products.

---

*Audit wygenerowany 2026-05-08. Zakładał rozwój silnika w Pythonie z portem C++ deferred.*
