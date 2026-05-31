# Briefing — następna sesja FP6 (po 2026-05-29, sesja 15)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## ✅ STAN po sesji 15 (2026-05-31 — ROADMAP domów + MERGE do main + Plan 2 MEBLE)

**Roadmap (nadrzędny):** `docs/ROADMAP_domy.md` — Etapy 1/2/3 **ZAMROŻONE**, cała energia w
Etap 4 (CP-SAT) napędzany realnym przypadkiem: **rzuty domów** (wolnostojący → bliźniak →
szeregowiec). Mózg = Python na zawsze; C++ tylko jako powłoka (Tapir) do dystrybucji.

**Zrobione w sesji 15 (gałąź `feat/sfh-furniture`, odgałęziona od main):**
1. **F2 guard** — `tests/test_house_layout.py::test_house_wet_rooms_never_exceed_wt_cap`
   (parametryczny: 11×9, 16×13). Zweryfikowano: cap łazienki ≤5 m² działa strukturalnie
   (solver `upper_bound` po `WT_MAX_AREA`), na 16×13 dociska do 4.99; bez capa łazienka 7.76
   → test bije. Żadnej zmiany w solverze (cap już był poprawny). Commit `ca92621`.
2. **MERGE `feat/sfh-2storey-mvp` → main** (fast-forward, czysty; **BEZ push** — repo prywatne,
   decyzja o push odłożona). main = `ca92621` (cała praca SFH + F2 guard).
3. **Plan 2 — MEBLE** (`core/furniture.py`): kanoniczne zestawy PL per typ pokoju (spec §5),
   greedy pod ściany (inset 0.1), kolizje Shapely, skip jeśli nie mieści, większe pierwsze.
   **Drzwi inferowane tylko z krawędzi wspólnej z pokojem KOMUNIKACJA (F5)** — geometryczne
   sąsiedztwo samo dawało fałszywe strefy (łazienka↔garderoba) i wypychało wannę/półki.
4. **Renderer 2-kond.** — `viz/plan_renderer.py::render_two_storey(layout, furniture)`: panele
   PARTER|PIĘTRO, meble, symbol schodów (z poprawnym offsetem bbox: pokoje absolutne,
   `stair_core` bbox-relative). PNG: `notebooks/output/sfh_furnished.png`.
   Testy: `tests/test_furniture.py` (6), `tests/test_two_storey_render.py` (1). Commit `dc77773`.
   **Weryfikacja: 17 passed / 0 failed** (furniture+render+house+templates+reserved_core).

### 🔥 Następne kroki (wg `docs/ROADMAP_domy.md`)
1. **Plan 3 — UI**: tryb „dom 2-kond." w zakładce Stage 4 + routing JEDNORODZINNA →
   house templates (nie M1-M5) + przełącznik mebli on/off + wyświetlanie 2 kondygnacji.
   (Renderer 2-kond. już gotowy — zostaje wpięcie w `ui/main_window.py`.)
2. **GAP jakości (decyzja Dawida):** na za dużym footprincie nadmiar (F1) wpychany w salon
   (salon 90→130 m² na 16×13). Dla DOMU: cap rozsądnych rozmiarów pokoi albo „nadmiar →
   taras/hol/garaż". Nie zgadywać — zapytać.
3. **Bliźniak → szeregowiec** (kolejne typy domów; sąsiednie obrysy rysowane ręcznie w AC).
4. **Polish mebli (opcjonalnie):** wezgłowie łóżka preferuj ścianę bez okna (dziś bywa przy oknie);
   meble liniowe (blat) dopasuj długość do realnej wolnej ściany.
5. Później: Faza 2 (Stage 2/3 + pipeline 1→2→3→4) — ale wg roadmap to ZA zamrożeniem.

> ⚠️ Praca sesji 15 na gałęzi `feat/sfh-furniture` (commit `dc77773`), **NIE zmergowana do main,
> NIE pushnięta.** main = `ca92621`. Decyzja merge/push `feat/sfh-furniture` → Dawid.

---

## ✅ STAN po sesji 14 cz.2 (2026-05-29 — PIVOT MVP + Plan 1 domu zrobiony)

**Pivot MVP:** ze „raport PDF" na **pipeline domu jednorodzinnego (2 kondygnacje) + meble**
(decyzje właściciela 2026-05-29: 2 kondygnacje, pełne Stage 2/3, meble auto-kanoniczne).
Zapisane w pamięci projektu. Stary raport PDF odłożony.

**Faza 1 zaprojektowana + Plan 1 ZAIMPLEMENTOWANY** (gałąź `feat/sfh-2storey-mvp`):
- Spec: `docs/superpowers/specs/2026-05-29-sfh-2storey-stage4-furniture-design.md`
- Plan 1: `docs/superpowers/plans/2026-05-29-sfh-2storey-core-generation.md` — **ZROBIONY**:
  `solve_cpsat(reserved_core=…)` (addytywny) + `templates/house_parter.json`+`house_pietro.json`
  + `core/house_layout.py` (`generate_house` → 2 kondygnacje, klatka zgrana w pionie) +
  smoke `notebooks/sfh_house_smoke.py`. **16 passed / 1 xfailed**; viz `output/sfh_house_smoke.png`
  pokazuje sensowny dom (na footprincie ~9×7,5 m salon 28 / sypialnie 23/17/10 / łazienka 4,8≤5).
- Po drodze naprawiony pre-existing `KeyError` w `_compute_target_areas` (rozszerzone programy domu;
  addytywnie, M1-M5 nietknięte).

### 🔥 Następne kroki MVP domu (kolejność)
1. **Plan 2 — MEBLE** (`core/furniture.py`): regułowe zestawy per typ pokoju pod ściany,
   z dala od drzwi, render w `viz/plan_renderer.py`. Spec §5 to projektuje. Napisać plan → wykonać.
2. **Plan 3 — VIZ + UI** (render 2 kondygnacji + tryb „dom 2-kond." w Stage 4 + routing JEDNORODZINNA + przełącznik mebli).
3. **GAP jakości do naprawy:** na footprincie ZBYT DUŻYM dla programu nadmiar (F1 = 100% pokrycia)
   wpychany w jeden pokój (salon 48 m², sypialnia 44 m² na 99 m²/kondygnację). Dla DOMU dystrybucja
   nadmiaru ≠ apartament (Q6 dumpuje w salon) — przemyśleć (cap rozsądnych rozmiarów pokoi domowych
   albo „nadmiar → taras/ogród/większy hol"). Na realnym ~64 m²/kondygnację jest OK.
4. Potem: Faza 2 (pełny Stage 2/3 + płynne wpięcie 1→2→3→4).

> ⚠️ Praca jest na gałęzi `feat/sfh-2storey-mvp`, **NIE na main, NIE pushnięta**. 7 commitów
> (monster fix + docs + spec/plan + 4× implementacja Planu 1). Decyzja o merge/PR — patrz koniec.

---

## ✅ STAN po sesji 14 cz.1 (2026-05-29 — MONSTER BUG NAPRAWIONY)

Sesja 14 = **focused rewrite obsługi oversized/road-less parcel** (PRIO 1 z sesji 13).
Bug Dawida z AC (S7 = 19 664 m²) **rozwiązany**, zero regresji.

### Co zrobione (pełny opis w `docs/STATE.md` → "Stage 1 Session 14")
- **Root cause zabity u źródła:** `_absorb_leftover` już NIE skleja bezdrożnego
  pasa ≥ min_area w road-accessible sąsiada — zostawia go jako standalone
  road-less sub (drobne slivers nadal merge).
- **Nowy terminalny post-pass** `_resolve_oversized_parcels` (raz, po pętli →
  brak oscylacji absorb↔split): road-accessible oversized → split; bezdrożny/
  dziwny → legalny spur rescue (partial-accept); reszta → demote do nieużytku.
- **Decyzja właściciela (2026-05-29):** „rescue then demote" + „pełny clean"
  (trim ślepych dróg). `_trim_dead_end_roads` **gated** na `nieużytek > 1 m²` —
  czyste układy zero-nieużytku (w tym droga grazująca skośną krawędź) nietknięte.
- **Testy:** `test_no_roadless_monster_subplot` (DETACHED+TWIN, było xfail → GREEN),
  `test_rescue_spur_does_not_dead_end...` (nowy), `test_coverage_holds_with_nieuzytek`.
- **Viz:** `notebooks/stage1_notch_sanity.py` → `output/notch_sanity_*.png`.

### Weryfikacja
- Notch: DETACHED max 932 m² / TWIN max 427 m² (cap 1050) — **brak monstera**;
  każdy sub ma dostęp do drogi; Q16 diff=0.00; nieużytek 7% (odcięty róg).
- **Pełny non-GUI suite: 301 passed, 30 skipped, 1 xpassed, 0 failed** (exit 0).
  Baseline 295 passed / 3 xfailed → +6 passed, zero regresji.

> ⚠️ **Zmiany NIE zacommitowane** (czekają na decyzję Dawida o commit/PR).
> ⚠️ **Gotcha:** test 600-800 jest pre-existing wolny (~7 min) + niedeterministyczny
> — to NIE regresja. „Wiszący" test subdivision = ta powolność; weryfikuj timeoutem
> ≥900 s albo `git stash` baseline. (Zapisane też w pamięci projektu.)

---

## STAN po sesji 12 (2026-05-28, krótka — manual GUI smoke + identyfikacja gapów)

Sesja 12 była **manualnym smoke testem integracji Stage 1 → Stage 4** (PRIO 1 z poprzedniej sesji) + identyfikacją nowych priorytetów. **Zero zmian kodu.** Pytest baseline confirmed: **296 passed / 30 skipped / 1 xpassed** w 10:08 — zgodne z baseline po sesji 11.

### Co zweryfikowane manualnie (Dawid w GUI)

- **Stage 1 Mode B + prostokąt 284×109 m: PASS.** DETACHED 41 sub-działek, TWIN 72, TERRACED 110. Pokrycie 100%, sensowne wielkości, drogi OK, nieużytek=0%.
- **Klik canvas → Stage 4 działa.** Wstępnie Dawid myślał że nie działa, ale to było przeoczenie — nie wiedział że trzeba kliknąć sub-działkę żeby przycisk "Otwórz wybraną sub-działkę w Stage 4" się włączył.

### Co zidentyfikowane jako problemy

1. 🐛 **BUG: monster sub-działka na nieregularnym kształcie** (regresja zakresu Q19)
   - DETACHED na 284×166 nieregularny: **S7 = 19 664 m²** (zone 17 692 m²). `max_sub_plot_area_m2=1000` → 19× ponad limit.
   - TWIN na 284×166 nieregularny: **S11 = 16 769 m²** (zone 15 315 m²).
   - Pattern: lewa część plotu bez dostępu do drogi (droga tylko po prawej w pionie) → algorytm nie wyciąga drogi w lewo i nie demuje do nieużytku, tylko zostawia monstera.
   - Q19 z sesji 10 naprawiał TWIN/TERRACED monstery na prostokącie (collapse do 4 sub-plots) — ale nie obejmuje nieregularnych kształtów i DETACHED.
   - Łamie spec Q16 (strict coverage z legalnymi sub-działkami) i Q1.1(d) (za małe → nieużytek, nie monster).

2. 🎨 **UX: brak wskazówki kliknięcia sub-działki**
   - Przycisk "Otwórz wybraną sub-działkę w Stage 4" jest disabled domyślnie, włącza się dopiero po kliknięciu canvas. Brak tooltipu / status-bar hint.
   - Mała sprawa, ale zablokowała Dawida przy pierwszym smoke.

3. 📦 **GAP: brak eksportu Stage 1 → ArchiCAD**
   - Stage 4 ma `bridge/plan_writer.py` (apartamenty jako Zones), Stage 1 nigdy nie miał. Sub-działki/drogi/nieużytek po wygenerowaniu w UI nie da się wstawić do AC.
   - Nowa funkcja, nie regresja.

### Co dorzucone do `docs/OPEN_QUESTIONS.md` jako nowe pytania architektoniczne

- **Q22 — Templates dla domów jednorodzinnych** (szeregowiec / bliźniak / wolnostojący). Obecne `templates/M1_standard.json`-`M5_standard.json` są dla mieszkań w bloku wielorodzinnym (mały salon, brak kotłowni/garażu/tarasu, brak piętra). Dom jednorodzinny ma 2 kondygnacje + kotłownia + garaż + schody + taras. Stage 4 dla domów po Stage 1 Mode B SF generuje obrysy domów ale nie ma czym ich zapełnić sensownie. **Duże, na osobną sesję.**
- **Q23 — Full pipeline Mode A wielorodzinna → Stage 3 → Stage 4.** Dziś integracja jest tylko Mode B SF → Stage 4 (single apartment). Dla wielorodzinnej trzeba: (a) wybór wariantu budynku w Mode A, (b) przekazanie obrysu piętra do Stage 3, (c) podział piętra na mieszkania w Stage 3, (d) klik w mieszkanie → Stage 4 z jego obrysem. **Dwa nowe sygnały + UX, duże, na osobną sesję.**

---

## PRIO 1 dla sesji 15 — UX fix: hint "kliknij sub-działkę"

Drobnostka (monster fix z sesji 14 już zrobiony).
- Status bar w Stage 1 po Generate: "Kliknij sub-działkę aby zaznaczyć…"
- Tooltip na disabled "Otwórz wybraną sub-działkę w Stage 4": "Najpierw kliknij sub-działkę na podglądzie"

---

## PRIO 2 — wybór z większego backlogu

W kolejności potencjalnej wartości:

1. **Q22 — templates dla domów jednorodzinnych** (szeregowiec/bliźniak/wolnostojący). Pierwsza krok: brainstorm + spec design. Skala: nowy zestaw 3-6 templates + ewentualnie 2-kondygnacyjny solver wariant.
2. **Eksport Stage 1 → ArchiCAD** — sub-działki + drogi + nieużytek jako Zones. Analogicznie do `bridge/plan_writer.py` dla Stage 4.
3. **Q23 — Mode A wielorodzinna → Stage 3 → Stage 4 full pipeline.** Wymaga: (a) UX wyboru wariantu w Mode A, (b) signal Stage 1 → Stage 3, (c) signal Stage 3 → Stage 4. Patrz STATE.md "Out of scope still on backlog".
4. **Q1.1(c) — push-neighbour mechanism** — deferred od Session 5 (2026-05-07).
5. **L-shape floors w Stage 3** — `floor_layout.py` zakłada prostokątne piętro.
6. **Walls + doors export do AC** — Stage 4 obecnie eksportuje tylko Zones.
7. **Stage 2 — volumetric generator** — jeszcze niezaczęty.
8. **`test_hub_adjacency_m2` xfail-mark** — albo napraw root cause, albo xfail jak `m3`.

---

## Reguły workflow do PAMIĘTANIA

Jak w `docs/FUNDAMENTAL_RULES.md`:
- **F2** łazienka ≤ 5 m² (twarda Stage 4)
- **B1** 2 fail = REWRITE (nie 3-cia próba)
- **B2** plan w prostym języku PRZED zmianą kodu, czekaj na OK
- **B6** słuchaj dosłownie ("nie zmieniaj X" = nie zmieniaj X)
- **B8** verify before "done" (pytest + ja widzę wynik)
- **B10** kolega-do-kolegi, po polsku

---

## Środowisko / komendy

```bash
source venv/bin/activate
python3 -m ui.main_window                                    # GUI

python3 -m pytest --ignore=notebooks --ignore=tests/test_gui.py -q   # pełny (~10 min)

python3 -m pytest tests/test_plot_subdivider.py tests/test_plot_variant_generator.py \
                  tests/test_building_proposer.py -v                  # obszar monster bug

python3 -m pytest tests/test_building_to_apartment_input.py \
                  tests/test_stage1_stage4_integration.py -v          # Session 11 integration (~1s)
```

**Custom Tapir Add-On** dla Stage 4 export — bez zmian, `tapir-custom/`
w katalogu `claude code/`.

---

## Pytest baseline po sesji 14 (2026-05-29)

Pełny non-GUI suite (`pytest --ignore=notebooks --ignore=tests/test_gui.py -q`)
zweryfikowany do końca: **301 passed, 30 skipped, 1 xpassed, 0 failed** (exit 0,
~9 min). `tests/test_plot_subdivider.py`: **42 passed**.

Względem baseline na starcie sesji 14 (295 passed / 32 skipped / 3 xfailed):
+6 passed (2 monster un-xfailed po naprawie, 2 nowe testy dead-end, +2 szum
niedeterministyczny), 0 xfailed (monster zdjęte; `hub_adjacency_m3` flake → xpassed).

> ⚠️ Sesja 15 może potwierdzić baseline na starcie tym samym poleceniem
> (~9-10 min; wolne głównie przez pre-existing test 600-800, patrz gotcha wyżej).
