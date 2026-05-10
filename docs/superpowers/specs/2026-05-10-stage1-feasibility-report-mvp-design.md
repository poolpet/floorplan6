# Stage 1 — Feasibility Report MVP — Design Spec

> **Data:** 2026-05-10
> **Status:** Draft for owner review
> **Autor:** Claude (sesja brainstorming z Dawidem)
> **Kontekst:** rewizja kierunku po audycie Codexa (`AUDIT_REPORT.md`) + market research (TestFit/Archistar/Forma/Maket + opensource: momepy, zoning.space, procedural_city_generation)

---

## 1. Cel i tło biznesowe

### 1.1 Co budujemy
**Stage 1 PDF Feasibility Report MVP** dla małych biur architektonicznych w Polsce. Architekt zaznacza działkę w ArchiCAD (lub wpisuje parametry MPZP manualnie), klika "Generate PDF Report" i dostaje 9-stronicowy raport feasibility do przekazania klientowi/deweloperowi.

### 1.2 Decyzje strategiczne (potwierdzone z ownerem 2026-05-10)

| Wymiar | Wybór | Dlaczego |
|---|---|---|
| Geografia | **PL focus z modularną architekturą** | TestFit słaby na małych nieregularnych działkach (= polski rynek). Maket nie ma database-driven MPZP. Nikt nie ma ArchiCAD-native dla PL. Modularność (rules/PL/...) zostawia drogę dla UK/DE/US. |
| Monetyzacja | **Per-raport 49-99 PLN** | Najszybsze go-to-market. OnGeo PL już sprzedaje 99-299 PLN raporty (ale dla pośredników). Niski commitment od klienta = test rynku przed subskrypcją. |
| Target user | **Małe biuro architektoniczne PL (priorytet 1)**, wielo-personalny produkt | Już używają ArchiCAD, znają MPZP, gotowi płacić. Wąski rynek (~5-10k podmiotów PL), konkretny problem. Z czasem — różne views dla deweloperów/pośredników/urzędów. |
| Zakres MVP | **Mode A (jednolita działka) + PDF**. Mode B parcelacja DEFER. | Mode A jest w 80% gotowy (testy zielone). Mode B (`plot_subdivider.py` 2669 linii) jest przeinwestowany — nie blokuje sprzedaży, możemy dodać po MVP. |

### 1.3 Konkurencja i moat

- **TestFit** (~250+ USD/mc) — luka: małe nieregularne działki
- **Archistar** (95-595 USD/mc) — pivotuje do B2G compliance check
- **Autodesk Forma** (185 USD/mc) — large-scale dev
- **Maket** (30 USD/mc) — document-dependent, nie database-driven
- **Hypar** (25 USD/mc) — parametric BIM, B2D

**Nasz moat (3 differentiatory):**
1. MPZP-as-code structured DB dla PL (nikt tego nie ma)
2. ArchiCAD-native (Tapir bridge, większość PL biur)
3. Małe nieregularne działki (TestFit nie umie)

**Pricing slot:** 49-99 PLN per raport (low entry) → potem 29 USD/mc subskrypcja. Pomiędzy Maket (30 USD/mc) a Hypar (25 USD/mc), pod TestFit/Archistar/Forma.

---

## 2. Architektura wysokopoziomowa

```
┌─────────────────────────────────────────────────────────┐
│  INPUT LAYER                                            │
│  • ArchiCAD selection (Tapir) → Plot polygon            │
│  • Manual MPZP form (UI) → MPZPParameters               │
│  • [post-MVP] OnGeo API integration                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  CORE ENGINE (Mode A) — istnieje, polerujemy            │
│  buildable_zone.py    → BuildableZone                   │
│  plot_indicators.py   → PlotIndicators (WZ/WIZ/PBC)     │
│  plot_verifier.py     → VerificationResult[19 reguł WT] │
│  site_planner.py      → BuildupVariant[3]               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  ⭐ NEW: REPORT LAYER                                    │
│  core/report_data.py     → ReportData (zbiera wyniki)   │
│  core/report_renderer.py → matplotlib figures dla PDF   │
│  core/report_pdf.py      → PDF generation (reportlab)   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  ⭐ NEW: RULE PACK ARCHITECTURE (minimalna)              │
│  rules/PL/wt_rules.json   ← przeniesione z rules/       │
│  rules/PL/constants.yaml  ← extracted z config.py       │
│  rules/_loader.py         ← generic load/validate       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  UI LAYER (Stage 1 tab)                                 │
│  ui/stage1_window.py        → architect view (AC)       │
│  ui/stage1_report_dialog.py → "Generate Report" button  │
└─────────────────────────────────────────────────────────┘
```

### 2.1 Decyzje architektoniczne

1. **Report Layer jako 3 osobne moduły** (data → render → pdf), nie monolit. Powód: matplotlib rendering jest ciężki testowy, PDF assembly jest lekki — separacja pozwala testować osobno + reużyć rendery w UI.

2. **`rules/PL/` jako proof of concept code pack.** Nie budujemy generic rule engine pod 4 kraje — tylko struktura folderów i loader, żeby DODANIE UK packu było potem mechaniczne.

3. **Mode B (parcelacja) NIE jest dotykany w MVP.** `plot_subdivider.py` (2669 linii) zostaje jak jest, testy zielone, kod w produkcji ale niedostępny z PDF flow.

4. **Brak nowej zależności poza `reportlab` i (opcjonalnie) `momepy`.** PDF: reportlab. Indicators: momepy rozważone, wpinamy tylko jeśli oszczędza ≥30% kodu.

---

## 3. Komponenty — co nowe vs istniejące

### 3.1 Nowe pliki

| Plik | Linie (estymata) | Dependencies | Co robi |
|---|---|---|---|
| `core/report_data.py` | ~150 | shapely, dataclasses | `ReportData` POJO — zbiera wszystkie wyniki Mode A do jednej struktury serializable do JSON. Zawiera method `estimate_units()` (PUM ÷ avg M3). |
| `core/report_renderer.py` | ~250 | matplotlib | 5 figur PDF: plot+zone overlay, indicators bar chart, compliance table viz, buildup variants 3-up, glossary table |
| `core/report_pdf.py` | ~300 | reportlab | Składa PDF: cover, exec summary, dane wejściowe, buildable, indicators, compliance, variants+units, glossary, metadata footer |
| `rules/_loader.py` | ~80 | pydantic, json/yaml | Generic loader: `load_pack("PL")` → walidacja schema, fallback na defaults |
| `rules/_schema.yaml` | ~60 | - | Pydantic schema dla pack contract (id, locale, version, files) |
| `rules/PL/pack.yaml` | ~30 | - | Manifest packa PL |
| `rules/PL/constants.yaml` | ~100 | - | Extracted z `config.py`: WT_*, HUB_*, parking ratios, building class thresholds |
| `rules/README.md` | ~80 | - | "How to add a country pack" tutorial |
| `ui/stage1_report_dialog.py` | ~200 | PyQt5 | Modal dialog: "Generate Report" → progress bar → "Save PDF as..." → preview, logo upload |
| `tests/test_report_data.py` | ~150 | pytest | 12 testów: serializacja, edge cases (zero compliance issues, all-pass, plot bez MPZP) |
| `tests/test_report_renderer.py` | ~80 | pytest | 6 testów: figury bez błędów, smoke PNG output |
| `tests/test_report_pdf.py` | ~100 | pytest | 5 testów: PDF >5 stron, hash danych obecny, disclaimer obecny |
| `tests/test_pack_loader.py` | ~120 | pytest | 10 testów: pack PL ładuje się, manifest valid, missing file → error, schema validation |
| `tests/test_glossary_data.py` | ~40 | pytest | 3 testy: słowniczek keys, lokalizacja PL |
| `tests/test_potential_units.py` | ~60 | pytest | 4 testy: PUM ÷ avg M3, edge cases (PUM<55) |

**Razem nowe:** ~1830 linii kodu produkcyjnego + 550 linii testów = ~2380 LOC, ~40 testów.

### 3.2 Modyfikacje istniejących plików

| Plik | Zmiana | Ryzyko |
|---|---|---|
| `config.py` | Wyciągnąć WT_*, HUB_*, parking, building class do `rules/PL/constants.yaml`. Zostawić tylko Python-runtime (np. SCALE=100). | Wysokie — ~15 importów cross-codebase |
| `core/plot_verifier.py` | Ładowanie reguł przez `rules/_loader.py` zamiast bezpośrednio z `rules/wt_rules.json` | Średnie |
| `core/plot_indicators.py` | Opcjonalnie: jeśli `momepy` daje lepsze metryki, wpinamy. Decision Week 3. | Niskie (tylko jeśli go-decision) |
| `ui/stage1_window.py` | Dodać przycisk "Generate PDF Report" → otwiera `Stage1ReportDialog` | Niskie |
| `rules/wt_rules.json` | Przenieść do `rules/PL/wt_rules.json`. Stara ścieżka deprecated z deprecation warning. | Niskie (path change) |

### 3.3 Cleanup (P2, jeśli zostanie czas — Week 6)

| Plik | Cleanup |
|---|---|
| `core/plot_subdivider.py` | 2669 linii → przeniesienie legacy/experimental kodu (OBB, katana, pattern helpers) do `notebooks/archive/`. Active path zostaje, ale plik powinien spaść do ~1000-1500 linii. |
| `notebooks/stage1_*.py` | Konsolidacja: 7 plików → ~3 (buildable, site_planner, subdivision archive). |

### 3.4 NIE ruszamy w MVP

- `core/plot_subdivider.py` aktywny kod (Mode B) — zostaje jak jest, regression testy mają działać
- `core/cpsat_solver.py`, `validator.py`, `scorer.py` (Stage 4) — poza scope
- `core/floor_*` (Stage 3) — poza scope
- `bridge/plan_writer.py` Walls/Doors export — to L3 z audytu, defer do post-MVP

---

## 4. PDF Report — struktura (9 stron A4)

| Strona | Treść |
|---|---|
| 1 | **Cover:** adres, działka ID, thumbnail (plot+zone), powierzchnia, klasa MN/MW, data, wersja, **logo biura (white-label)** |
| 2 | **Executive summary:** top-line numbers ramka (max powierzchnia zabudowy / PUM / bio-czynna / liczba naruszeń), zalecane warianty, status compliance |
| 3 | **Dane wejściowe:** plot (powierzchnia, obwód, bbox, kształt), klasyfikacja granic, parametry MPZP |
| 4 | **Buildable zone:** matplotlib figure (obrys + linia zabudowy + zone + setbacks), tabelka |
| 5 | **Wskaźniki MPZP (WZ/WIZ/PBC):** bar chart designed vs limit, kolor zielony/żółty/czerwony, komentarz pasmo 5% (Q14) |
| 6 | **Compliance check:** tabela 19 reguł WT 2002 (ID/Reguła/Wartość/Wymóg/Status), legal_basis link |
| 7 | **Warianty zabudowy + potencjalne mieszkania:** 3 mini-figury (Wariant A/B/C), pod każdym powierzchnia + WZ + szacowana liczba mieszkań (PUM ÷ ~55m² avg M3) |
| 8 | **Słowniczek:** co to WZ/WIZ/PBC/MPZP/linia zabudowy — 1 strona dla niespecjalisty (deweloper czyta) |
| 9 | **Metadata + disclaimer:** wersja FloorPlan6, ścieżka rules pack, hash danych, disclaimer prawny |

### 4.1 Decyzje projektowe

1. **Compliance status: ✓/⚠/✗** (Q14 5% pasmo) — zielony/żółty/czerwony, plus tekstowy symbol dla print
2. **Wariantów 3** zgodnie z `site_planner.propose_max_buildup`, nie więcej
3. **Brak rozkładu pokoi w Stage 1 PDF** — to Stage 4 territory
4. **Hash danych** w metadata — architekt może dowieść klientowi że raport jest dla TEJ działki + TYCH parametrów MPZP
5. **Disclaimer prawny obowiązkowy** — "raport informacyjny, nie zastępuje decyzji urzędu"
6. **Logo białej etykiety:** PNG max 200×80px, wgrywany w UI, wstawiany na cover + footer
7. **Multi-persona:** "View as: Architect / Developer" — różny tekst exec summary, te same dane core. Architect → "WZ 0.30 zgodny z par. § 12 WT". Developer → "Możesz wybudować budynek o 320 m² powierzchni zabudowy".

---

## 5. Rule Pack Architecture

### 5.1 Struktura katalogów po refactorze

```
rules/
├── _loader.py              ← NEW (~80 linii)
├── _schema.yaml            ← NEW (pydantic schema dla pack contract)
├── PL/                     ← NEW (przeniesione + extracted)
│   ├── pack.yaml           ← NEW (manifest)
│   ├── wt_rules.json       ← MOVED z rules/wt_rules.json
│   ├── constants.yaml      ← NEW (extracted z config.py)
│   └── user_rules.json     ← MOVED z rules/user_rules.json
└── README.md               ← NEW ("How to add a country pack")

config.py                   ← cleaned (tylko Python-runtime: SCALE itd.)
```

### 5.2 Pack manifest (`rules/PL/pack.yaml`)

```yaml
code_pack_id: PL
country_code: PL
locale: pl_PL
version: "1.0"
version_compat: ">=0.4.0"
display_name: "Polska — Warunki Techniczne 2002"
display_name_en: "Poland — WT 2002"
description: "Polski pack: 19 reguł WT, MPZP defaults"
references:
  - id: WT_2002
    title: "Rozporządzenie Ministra Infrastruktury z 12 kwietnia 2002"
    url: "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20020750690"
files:
  rules: wt_rules.json
  constants: constants.yaml
  user_overrides: user_rules.json
```

### 5.3 Constants extraction (`rules/PL/constants.yaml`)

Wyciągnięte z `config.py` — tylko to co jest **rule-driven**, nie runtime:

```yaml
wt_max_area:
  bathroom_m2: 5.0
  wc_m2: 3.0
wt_min_area:
  bathroom_m2: 2.5
  wc_m2: 1.5

setback_defaults:
  front_m: 6.0           # WT § 12
  side_m: 4.0
  rear_m: 4.0
  well_to_boundary_m: 7.5  # WT § 31

parking_ratio_per_unit: 1.5

building_class:
  N_max_height_m: 12.0
  SW_max_height_m: 25.0
  W_max_height_m: 55.0
  WW_above_m: 55.0

min_subplot_front_m: 18.0  # Q15, Mode B
```

### 5.4 Loader interface (`rules/_loader.py`)

```python
@dataclass
class CodePack:
    pack_id: str
    locale: str
    version: str
    rules: dict          # parsed wt_rules.json
    constants: dict      # parsed constants.yaml
    user_overrides: dict # parsed user_rules.json

def load_pack(pack_id: str = "PL") -> CodePack:
    """
    Load pack from rules/{pack_id}/.
    Validates against _schema.yaml.
    Raises CodePackError if missing/invalid.
    """
```

**Kontrakt:** kod produkcyjny dostaje **jeden** `CodePack` na starcie sesji. Wszystkie odwołania do reguł idą przez `pack.rules['wt_001']` lub `pack.constants['wt_max_area']['bathroom_m2']`. **Zero hardcoded WT_*** w kodzie poza initial config.

### 5.5 Co to NIE jest

- **NIE** generic constraint engine (jak Sentinel/OPA). Reguły zostają w solver/validator hardcoded jako Python kod (F1-F10). Pack daje tylko **wartości** + **metadata**.
- **NIE** runtime hot-swap (PL ↔ UK w trakcie sesji). Pack ładowany na start, restart UI żeby zmienić.
- **NIE** UK pack content. Tylko `rules/PL/`. Manifest pokazuje że więcej krajów się da dodać.

### 5.6 Migracja step-by-step (Week 1-2)

| Krok | Zmiana | Ryzyko |
|---|---|---|
| 1 | Utwórz `rules/PL/`, przenieś `wt_rules.json` + `user_rules.json` | Małe (path change) |
| 2 | Stwórz `rules/PL/pack.yaml` + `constants.yaml` | Małe (nowe pliki) |
| 3 | Napisz `_loader.py` + testy schema validation | Średnie |
| 4 | Refactor `core/plot_verifier.py` żeby używał loadera | Średnie (testy mają przejść!) |
| 5 | Refactor `config.py` — usuń extracted constants, importuj z packu | Wysokie — ~15 importów cross-codebase |
| 6 | Run `pytest` — wszystkie 144 testów muszą przejść | Walidacja |

**Kluczowa zasada:** pack architecture **nie zmienia behawioru** systemu. To czysty refactor. Jeśli któryś test przed/po nie przechodzi tak samo — bug w refactorze.

---

## 6. Testy i CI

### 6.1 Nowe testy (per komponent)

| Test file | Coverage | Liczba |
|---|---|---|
| `tests/test_report_data.py` | Serializacja, edge cases | ~12 |
| `tests/test_report_renderer.py` | Smoke matplotlib | ~6 |
| `tests/test_report_pdf.py` | PDF page count, hash, disclaimer | ~5 |
| `tests/test_pack_loader.py` | Pack PL load, schema validation | ~10 |
| `tests/test_glossary_data.py` | Słowniczek keys, locale | ~3 |
| `tests/test_potential_units.py` | PUM ÷ avg M3, edge cases | ~4 |
| **Razem nowe** | | **~40** |

### 6.2 Regression tests (existing — muszą dalej zielone)

- 18 buildable_zone
- 14 plot_verifier
- 12 site_planner
- 19 plot_subdivider (Mode B, niedotykany)
- 9 plot_variant_generator (Mode B)
- 134 całe (Stage 4 + 3) — wszystko musi przejść po refactorze packa

**Total docelowo:** ~180 testów zielonych po MVP.

### 6.3 CI strategy

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest]    # NEW: macOS
    python-version: ["3.11", "3.12", "3.13"]
```

**Smoke test PDF w CI:**
- Generuj sample PDF z fixture data
- Sprawdź: plik istnieje, rozmiar > 50KB, ≥ 8 stron (pyPDF2)
- Upload artifact do GitHub Actions

### 6.4 Verification protocol per zmianę (B8 z FUNDAMENTAL_RULES)

Po **każdej** zmianie kodu:
1. `pytest tests/` lokalnie — wszystkie zielone
2. Manual run: uruchom UI, generuj PDF na test plot, **otwórz PDF wzrokiem**
3. `git diff --stat` — sprawdź że nie ruszyłem niczego poza scope
4. CI green na PR

### 6.5 Co NIE testujemy automatycznie

- **PDF visual regression** (czy fontki dobrze, czy figures w odpowiednich miejscach) — manual review wystarczy w MVP.
- **OnGeo API** (poza MVP).
- **Multi-locale UI** (post-MVP, gdy będzie i18n).

---

## 7. Roadmap 6 tygodni

### Week 1 — Pack Foundation
**Goal:** rules/PL/ struktura + loader działa, brak regresji testów.

| Day | Task |
|---|---|
| 1 | Utwórz `rules/PL/`, przenieś `wt_rules.json` + `user_rules.json` |
| 2 | Napisz `rules/PL/pack.yaml` (manifest) |
| 3-4 | Napisz `rules/_loader.py` + `_schema.yaml` + 10 testów |
| 5 | Refactor `core/plot_verifier.py` żeby używał loadera |

**Demo:** `from rules._loader import load_pack; pack = load_pack("PL")` działa, 144 testów dalej zielone.

### Week 2 — Constants Migration
**Goal:** config.py oczyszczony, constants w packu.

| Day | Task |
|---|---|
| 1-2 | Stwórz `rules/PL/constants.yaml` z extracted constants |
| 3-4 | Refactor importy w `core/cpsat_solver.py`, `validator.py`, `scorer.py`, `site_planner.py` |
| 5 | `config.py` cleanup — tylko Python-runtime stałe |

**Demo:** `config.py` < 50 linii, 180 testów zielonych.

**Decision point:** Jeśli refaktor wykazał test bug → STOP, fix root cause przed Week 3 (B1).

### Week 3 — Report Data + Renderer
**Goal:** Mode A end-to-end → ReportData → matplotlib figures.

| Day | Task |
|---|---|
| 1 | `core/report_data.py` + 12 unit testów |
| 2-3 | `core/report_renderer.py` — 5 figur |
| 4 | `estimate_units()` calc + 4 testy |
| 5 | momepy evaluation: spróbuj zastąpić `circular_compactness` → decyzja go/no-go |

**Demo:** `notebooks/preview_report_figures.py` generuje 5 PNG z fake data.

### Week 4 — PDF Assembly
**Goal:** PDF 9 stron generowany z fake data.

| Day | Task |
|---|---|
| 1 | Cover, exec summary, dane wejściowe |
| 2 | Buildable zone + indicators pages |
| 3 | Compliance + variants + potential units |
| 4 | Glossary + metadata + disclaimer |
| 5 | Logo upload support: footer slot dla PNG (max 200×80) |

**Demo:** `python -m core.report_pdf --fixture sample` → 9-stronicowy PDF w 5 sek.

### Week 5 — UI Integration
**Goal:** End-to-end z UI: AC selection → MPZP form → PDF.

| Day | Task |
|---|---|
| 1-2 | `ui/stage1_report_dialog.py` — modal, progress, save dialog |
| 3 | Wpięcie do `ui/stage1_window.py` — przycisk "Generate PDF Report" |
| 4 | Logo upload UI: drag-drop PNG |
| 5 | Multi-persona separator: "View as: Architect / Developer" |

**Demo:** Pełny flow architekt — ArchiCAD → klik → PDF na disku.

### Week 6 — Polish + Beta Ready
**Goal:** macOS CI zielony, dokumentacja end-user, 1-2 beta testerów.

| Day | Task |
|---|---|
| 1 | macOS-latest do GitHub Actions matrix + PDF smoke test w CI |
| 2 | `docs/USER_GUIDE_STAGE1.md` z screenshotami |
| 3 | `notebooks/archive/` cleanup (`plot_subdivider.py` < 1500 linii) |
| 4 | Bug bashing: 5 real plots z geoportal.gov.pl |
| 5 | Pierwszy beta-test: 1 architekt znajomy → feedback survey |

**Demo:** MVP gotowy do sprzedaży (Gumroad / landing page, 49-99 PLN/raport).

### 7.1 Decision points (co piątek)

- Czy demo działa? (jeśli nie → rewrite per B1, nie patch)
- Czy wszystkie testy zielone?
- Czy zakres tygodnia pokryty? (jeśli > 30% slip → renegocjacja zakresu)
- Update `docs/STATE.md`

### 7.2 Co celowo POMIJAMY (post-MVP)

- Mode B (parcelacja) UI integration z PDF
- API OnGeo
- Web standalone view (bez ArchiCAD)
- B2G compliance check
- UK pack content
- Walls/Doors export (L3 z audytu)

### 7.3 Total effort

**6 tygodni × 5 dni = 30 dni roboczych.** Cushion: 3-5 dni buffer wewnątrz tygodni.

---

## 8. Open questions zostawione (do rozwiązania w trakcie)

1. **Decyzja momepy go/no-go** — Week 3 day 5. Kryterium: oszczędza ≥30% kodu w `core/plot_indicators.py`.
2. **Jakie thumbnaile na cover?** — sam plot vs plot+zone overlay. Decyzja Week 4 day 1.
3. **Multi-persona — jak głęboka różnica?** — same data, różny tekst exec summary tylko? Czy ukrywamy compliance details dla developera? Decyzja Week 5 day 5 z testem na Dawidzie.
4. **Beta tester selection** — kogo z architektów Dawid zna? Określić w Week 6 day 5.

---

## 9. Sukces / definicja gotowości MVP

MVP jest gotowy do sprzedaży gdy:

- [ ] 180+ testów zielonych (40 nowe + 134 istniejące + 6 ekstra edge cases)
- [ ] CI green na ubuntu + macOS dla Python 3.11/3.12/3.13
- [ ] PDF flow działa end-to-end (AC → klik → PDF) z 5 real plots z geoportal.gov.pl
- [ ] PDF white-label (logo upload) działa
- [ ] `docs/USER_GUIDE_STAGE1.md` z screenshotami
- [ ] 1 beta tester architekt zaakceptował raport ("wyglądałby OK do podania klientowi")
- [ ] `rules/PL/` pack architecture zdokumentowana w `rules/README.md`
- [ ] `config.py` ma < 50 linii Python-runtime constants

---

*Spec gotowy do review owera. Po akceptacji → invoke `writing-plans` skill dla detail implementation plan.*
