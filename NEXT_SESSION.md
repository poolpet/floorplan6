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

## ✅ STAN po sesji 14 (2026-05-29 — MONSTER BUG NAPRAWIONY)

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
