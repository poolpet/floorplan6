# Spec: Realizm parteru domów 2-kondygnacyjnych (sypialnia + łazienka na parterze)

> Data: 2026-06-13 · Branch: `feat/sfh-open-plan-day-zone` · Stage 4 (FloorPlan6)
> Decyzje Dawida (2026-06-13): sypialnia na parterze (total sypialni zachowany,
> poddasze −1); ZAWSZE dla domów 2-kond.; pełne (solidne) rozwiązanie z usługówką
> wg powierzchni jako bufor perf.

## Problem

Benchmark realizmu (`notebooks/parter_realism_diag.py`, 5 wzorców prostokątnych)
pokazuje, że nasz **parter** systematycznie odbiega od realnych rzutów — to słaby
punkt score'u (parter F1 0.33–0.75 vs poddasze 0.77–1.0):

| luka | wzorce | nasz stan |
|---|---|---|
| pełna **ŁAZIENKA** na parterze | 5/5 (4.7–11.2% pow.) | tylko `wc` (2.5%) |
| **SYPIALNIA**/pokój na parterze | 4/5 (11.6–17.4%) | 0 sypialni (wszystkie na piętrze) |
| salon za duży | osobie/pb/a2-6: +11…+20 pkt | ~46–49% (realne 28–35%) |
| `schody` liczone przeciw F1 | 0/5 (ekstrakcja nie listuje) | mamy pokój `schody` |

Konwencja PL domu 2-kond.: pokój gościnny/dostępny + łazienka na parterze, strefa
nocna (sypialnie) na piętrze. ŻADEN wzorzec nie ma `wc` + `lazienka` razem na
parterze — mają **pełną łazienkę ZAMIAST WC**.

## Zakres

**W zakresie:** rebalans programu parteru domów 2-kond. (`house_parter` template +
selektory + budżet sypialni na poziomie domu) + 2 fixy uczciwości benchmarku.

**Poza zakresem:** salon-overflow cap (osobny GAP, częściowo samonaprawi się gdy
parter zyska pokoje); parterowce (`house_single_storey` JUŻ ma lazienka+sypialnie —
nietknięte); mieszkania M1–M5 (inny program); osobne WC gościnne dla dużych domów
(ewentualny późniejszy refinement); perf parteru (kolejka — to rozwiązanie ma być
perf-NEUTRALNE, nie perf-fix).

## Projekt

### 1. Szablon `templates/house_parter.json`

- **`wc` → `lazienka`** (USŁUGOWA): pełna łazienka parteru (min 2.5 / opt 4.8 jak w
  `house_pietro`/`house_single_storey`). Cap F2 = 5 (parter) z `cap_for` (key
  `lazienka`). `wc` znika z parteru 2-kond. (wzorce nie mają WC obok łazienki).
- **+ `sypialnia_parter`** (NOCNA, `wymaga_okna=true`, min 9.0 / opt 12.0): pokój
  na parterze. Prefix `sypialnia` → mapuje się na typ `sypialnia` w benchmarku i
  cap `sypialnia` (13).
- **Sąsiedztwa:** `hub↔lazienka` (zamiast `hub↔wc`), **+`hub↔sypialnia_parter`**.
  Reszta grafu bez zmian (salon↔kuchnia opening, kuchnia↔spizarnia, hub↔reszta).

### 2. Selektor pokoi parteru (`core/house_layout.parter_room_ids`)

Bazowy zestaw parteru = wszystkie pokoje szablonu poza bramkowanymi. Nowe bramki
wg powierzchni NETTO (spójne z istniejącym netto/brutto, `net_area`):

- `sypialnia_parter`, `lazienka` — **zawsze** (część bazowa).
- **`spizarnia` — tylko `net ≥ 60`** (korpus: osobie 65/a2-6 83 mają; tropie 48/
  pb 51/pab2 44 nie). To bufor perf: mały parter traci spiżarnię, zyskuje
  sypialnię+łazienkę (wc→lazienka neutralne) → **liczba pokoi ~stała (8)**.
- `gabinet ≥93`, `garaz ≥97` — bez zmian (istniejące bramki).
- `kotlownia` — zostaje (potrzeba grzewcza; korpus: obecna w różnych metrażach).

Bilans pokoi parteru: mały ~41 netto = hub/schody/wiatrolap/salon/kuchnia/lazienka/
sypialnia_parter/kotlownia = **8 (jak dziś)** → perf-neutralny. Średni ≥60 = +spiżarnia = 9.

### 3. Budżet sypialni na poziomie DOMU (`core/house_layout.generate_house`)

Cel: **łączna liczba sypialni bez zmian** (1 schodzi na parter, NIE dodajemy).

- Parter zawsze ma `sypialnia_parter` (1 sypialnia na dole).
- `pietro_room_ids` dobiera o **JEDNĄ sypialnię MNIEJ** niż dotąd (parametr
  `bedroom_offset=1`): zachowuje `_PIETRO_CORE` minimum (musi zostać ≥1 sypialnia
  na piętrze — strefa nocna), reszta sypialni opcjonalnych zredukowana o 1.
- Niezmiennik: `(parter sypialnie=1) + (poddasze sypialnie) == (stare poddasze sypialnie)`.
- Skrajność: gdy poddasze miałoby 0 sypialni po odjęciu (dom z 1 sypialnią total) —
  zostaw 1 na piętrze, parter bez sypialni (fallback; rzadkie, < ~bramki 2-kond.).

### 4. Uczciwość benchmarku (`notebooks/reference_benchmark.py`)

Nie zmienia generatora — poprawia POMIAR:

- **`schody` wykluczone z F1** (jak `garaz`/`other` w `_storey_rooms`): ekstrakcja
  wzorców nie listuje schodów jako pokój, więc nasz `schody` fałszywie obniża
  precyzję. Filtr w `_storey_rooms` (ref) i analogicznie po stronie generatora
  (`gen_typed`) przed `room_set_f1`.
- **Master = największa sypialnia w CAŁYM domu** (nie per-kondygnacja): inaczej
  jedyna `sypialnia_parter` parteru fałszywie zostaje „master". `score_project`
  liczy `master_id` raz nad `parter_rooms + pietro_rooms`, używa go w obu typowaniach.

## Dane / przepływ

Bez nowych struktur. `RoomSpec`/`AdjacencyRule` istnieją. Przepływ:
`generate_house → parter_template_for(area) [+sypialnia_parter, lazienka, spiżarnia
wg netto] + pietro_room_ids(eff, bedroom_offset=1) → solve ×2 → TwoStoreyLayout`.

## Obsługa błędów

- Mały parter nie mieści sypialni+łazienki → solver `ok=False` z komunikatem
  (uczciwie; gating w odwodzie wg ryzyka).
- Dom z 1 sypialnią total → fallback: sypialnia zostaje na piętrze (pkt 3 skrajność).
- Parterowce / M1–M5 → ścieżki nietknięte (zmiana tylko `house_parter` + 2-kond.).

## Testowanie (RED-first)

Nowy `tests/test_house_parter_realism.py`:
1. **`test_parter_template_has_bedroom_and_bathroom`** — `house_parter` ma
   `sypialnia_parter` (NOCNA, okno) + `lazienka`, NIE ma `wc`.
2. **`test_parter_selector_always_bedroom_bathroom`** — `parter_room_ids` zawiera
   `sypialnia_parter`+`lazienka` dla małego i dużego; `spizarnia` tylko ≥60 netto.
3. **`test_bedroom_count_conserved`** — dla obrysu X: (sypialnie parteru=1) +
   (sypialnie poddasza) == sypialnie poddasza w starym modelu (`bedroom_offset=0`).
4. **`test_generate_2storey_parter_has_bedroom_bathroom`** (integracja) — realny dom
   2-kond.: parter ma dokładnie 1 `sypialnia*` + 1 `lazienka`, 0 `wc`.
5. **`test_single_storey_unchanged`** — parterowiec bez zmian (regression-lock).
6. **`test_benchmark_excludes_schody_and_houselevel_master`** — `schody` nie liczone
   w F1; master = największa sypialnia całego domu (jednostkowo na sztucznych pokojach).

Weryfikacja: testy + **re-run benchmarku** `reference_plans_rect7.json` (oczekiwane:
parter F1 ↑, średnia > 53.5) + render kontrolny 2-kond. (sypialnia+łazienka na parterze).

## Ryzyka

- **Perf parteru** — dodanie pokoi mogłoby pogorszyć UNKNOWN-flak; mitygacja =
  bufor usługówki (pkt 2, mały parter perf-neutralny @8 pokoi). Mierzymy na benchmarku.
- **`sypialnia_parter` wymaga fasady (F6)** na ciasnym parterze ze salonem+kuchnią —
  solver może mieć mniej miejsca; ujawni benchmark/regresja.
- **Budżet sypialni** może dać poddasze z 1 sypialnią na małych — akceptowalne
  (parter przejmuje drugą); niezmiennik testowany.
