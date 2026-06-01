# Spec — Tryb „Dom jednorodzinny" w UI Etapu 4 (Plan 3)

**Data:** 2026-06-01 (Sesja 16)
**Branch:** `feat/sfh-furniture`
**Roadmap:** `docs/ROADMAP_domy.md` — Plan 3 (viz + UI), krok 1: tryb „dom 2-kond." w Etapie 4.
**Powiązane:** `docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md` (Plan 1+2: `house_layout`, `furniture`, `render_two_storey`).

---

## 1. Cel i zasada

Dodać do zakładki **Stage 4** równoległą ścieżkę generowania **domów jednorodzinnych
2-kondygnacyjnych z meblami**, przełączaną radiem trybu. Ścieżka mieszkań w bloku
(M1–M5) pozostaje **funkcjonalnie nietknięta** — to dodanie funkcji, nie zamiana.

Decyzja użytkownika (Sesja 16): *„punkt 1, ale nie zastępujemy generatora rzutów
mieszkań w bloku, tylko dodajemy kolejną funkcję rozwiązywania domów"*.

## 2. Stan wyjściowy (gotowe klocki — bez zmian)

- `core.house_layout.generate_house(polygon, entry_point, num_storeys=2, time_limit_s=30.0)`
  → `TwoStoreyLayout(ok, message, parter_rooms, pietro_rooms, stair_core, boundary)`.
  Zwraca **jeden** układ (2 kondygnacje), nie N wariantów. Pole `ok=False` + `message`
  dla za małego obrysu (`< MIN_STOREY_AREA = 60 m²`) lub gdy solver nie znajdzie układu.
- `core.furniture.place_furniture(rooms) -> list[Furniture]` — czysta geometria, szybkie.
- `viz.plan_renderer.render_two_storey(layout, parter_furniture, pietro_furniture, title,
  save_path, show, figsize)` → figura **2-panelowa PARTER | PIĘTRO** (meble + klatka).

Obecna ścieżka mieszkań w `ui/main_window.py`:
`type_combo` (M1–M5) + `wc_check` → `_on_generate` → `GenerateWorker(QThread)` →
`generate_variants` (N wariantów ze `score`) → `_on_variants_ready` → `_show_variant`
→ `render_floor_plan` (1 panel) + nawigacja prev/next + Export PNG / To ArchiCAD.

## 3. Architektura zmian

### 3.1 Nowy moduł `viz/house_preview.py` (GUI-free, testowalny)

Cała NOWA logika orkiestracji trafia tu — `main_window.py` (już 1201 linii) ma zostać
cienki, a testy GUI padają w trybie headless (STATE.md), więc logika musi być testowalna
bez PyQt.

```python
def furnish_layout(layout, with_furniture: bool) -> tuple[list, list]:
    """(parter_furniture, pietro_furniture); puste listy gdy with_furniture=False."""

def house_details_text(layout) -> str:
    """Wielolinijkowy opis: obie kondygnacje + nazwy/powierzchnie pokoi + pole obrysu."""

def render_house_figure(layout, with_furniture: bool, title: str | None = None,
                        save_path=None, show: bool = False) -> "Figure":
    """furnish_layout + render_two_storey. Zwraca matplotlib Figure."""
```

Moduł importuje `core.furniture.place_furniture` i `viz.plan_renderer.render_two_storey`.
Generowanie (`generate_house`) wywołuje worker, nie ten moduł (separacja: generacja w
wątku, render w UI/teście).

### 3.2 Worker `HouseGenerateWorker(QThread)` w `main_window.py`

Wzorowany na `GenerateWorker`. Wejście: `polygon`, `entry_point`, `with_furniture`.
`run()`: woła `generate_house(...)`, emituje `TwoStoreyLayout` (+ flagę mebli) sygnałem
`finished`; błędy → `error`. (Furniture liczymy przy renderze przez `render_house_figure`,
żeby worker zwracał czysty layout — meble są szybkie i deterministyczne.)

### 3.3 UI — `ui/main_window.py`

- **Radio „Tryb"** na górze zakładki Stage 4: `Mieszkanie w bloku (M1–M5)` /
  `Dom jednorodzinny`. Handler `_on_mode_changed` przełącza widoczność kontrolek i
  podpięcie przycisku Generuj.
- **Krok 1 (Obrys)** — wspólny, bez zmian (W/H, Entry X/Y, import z AC, notch L/U).
- **Krok 2** — przełączany wg trybu:
  - Mieszkanie: `type_combo`, `wc_check`, `variants_spin`, `min_score_spin`,
    `facades_btn` (jak dziś).
  - Dom: powyższe ukryte; widoczne: etykieta „Program: dom 2-kond. (parter + piętro)" +
    **`QCheckBox „Meble"` (domyślnie zaznaczony)**.
- **Krok 3 (Generuj)** — ten sam przycisk; `_on_generate` rozgałęzia wg trybu. Tryb domu
  → `HouseGenerateWorker`.
- **Krok 4 (Wynik)** — w trybie domu: prev/next **wyłączone** (1 układ, 2 kondygnacje obok
  siebie w jednym renderze); **Export PNG działa** (zapis figury `render_house_figure`);
  **To ArchiCAD wyłączone** z tooltipem „eksport domu do AC — później (shell C++)".
- Render domu trafia w istniejący `image_label` przez `_fig_to_pixmap`.
- `ok=False` z `generate_house` → komunikat w `image_label` + status bar, analogicznie do
  ścieżki „brak wariantów" (`_on_variants_ready`).
- Przełączenie trybu czyści/wyłącza poprzedni wynik (prev/next/export, podgląd).

## 4. Zakres i domyślne (świadome decyzje)

- **Domyślny tryb na starcie:** `Mieszkanie` (zero zmian w obecnym pierwszym uruchomieniu).
- **Typ domu:** tylko **wolnostojący** (pełny obrys). Bliźniak/szeregowiec → osobna sesja.
- **Liczba kondygnacji:** stałe **2** (istnieją tylko szablony `house_parter`/`house_pietro`).
- **Meble w trybie mieszkania:** NIE dodajemy (zostają nietknięte).
- **GAP jakości (nadmiar F1 → salon ~130 m² na dużym footprincie):** będzie **widoczny**
  w renderze domu, ale **nie naprawiamy** go w tej sesji — to osobna decyzja architektoniczna.

## 5. Reguły, których nie wolno naruszyć

- F1–F10 i B1–B10 obowiązują. Ta zmiana jest **czysto UI/orkiestracyjna** — nie dotyka
  solvera (`cpsat_solver`), walidatora, ani capów WT (F2 łazienka ≤5 m²). House solver i
  meble są już zweryfikowane (17 testów zielonych).
- B1: 2 faile = rewrite, nie 3-cia próba.
- B8: weryfikacja przed „done" (pytest + manualne uruchomienie GUI + screenshot).

## 6. Testy (B8)

- `tests/test_house_preview.py` (NOWY, GUI-free):
  - `render_house_figure(layout, with_furniture=True)` zwraca `Figure` dla poprawnego obrysu.
  - `with_furniture=True` daje więcej mebli niż `with_furniture=False` (=0).
  - `house_details_text(layout)` zawiera obie kondygnacje (PARTER/PIĘTRO) i nazwy pokoi.
  - `furnish_layout` zwraca dwie listy zgodne z flagą.
- GUI (`ui/main_window.py`) — **weryfikacja manualna** (headless collection pada):
  uruchomienie `python -m ui.main_window`, przełączenie na „Dom", generacja 8×10 z meblami,
  screenshot 2-panelowy.
- Pełny `pytest` zielony (z deselektem wolnego testu 600-800 subdivision).

## 7. Pliki

- NOWY: `viz/house_preview.py`
- NOWY: `tests/test_house_preview.py`
- ZMIANA: `ui/main_window.py` (radio trybu, `HouseGenerateWorker`, handlery `_on_mode_changed`/
  `_on_generate` rozgałęzienie/`_show_house`, przełączanie widoczności kroku 2/4).
- ZMIANA (docs): `docs/STATE.md`, `NEXT_SESSION.md` po zakończeniu.

## 8. Poza zakresem (na później)

- Eksport domu do ArchiCAD (zony/ściany 2 kondygnacji) — „shell" C++/Tapir.
- Bliźniak / szeregowiec (typy domów ze ścianami wspólnymi).
- Dom parterowy (1 kondygnacja).
- Naprawa GAP-u jakości nadmiaru dla domów (osobna decyzja architektoniczna).
- Polish mebli (wezgłowie przy ścianie bez okna; długość blatu do realnej wolnej ściany).
