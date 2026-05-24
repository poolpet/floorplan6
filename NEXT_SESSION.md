# Briefing — następna sesja FP6 (po 2026-05-22)

> **Jak zacząć jutro:** otwórz terminal, wpisz:
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Następnie pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## Co zrobione w sesji 2026-05-22 (push'owane na GitHub)

1. **Faza 0** — commit/push 51 zaległych zmian: Stage 1 logic + Stage 4 V1-V4 + custom Tapir + docs (commity `678e561`, `39ba221`, `f21d5a1`)
2. **Faza 4 — Stage 1 Phase 3** — Eksport raportu PDF Mode A + Mode B (commit `9017bae`)
   - `core/report_builder.py`: `build_report_data()` + `build_report_data_mode_b()`
   - `ui/report_metadata_dialog.py`: plot_id/address/logo z QSettings IniFormat
   - `ui/stage1_window.py`: przycisk "Eksport raportu PDF" + cache `("A"/"B", ...)`
3. **Opcja A — port CPP `optimal_ratio`** (commit `f7c923c`)
   - `target_front = max(min_front, sqrt(area × 0.67))` z FP4_CPP
4. **Zadanie 1 — Mode A depth-aware** (commit `f7c923c`)
   - WIELORODZINNA: max_depth=16m (2-trakt z korytarzem, NIE kwadrat)
   - JEDNORODZINNA: max_depth=12m
5. **Zadanie 2 — Building proposals Mode B** (commit `f7c923c`)
   - `core/building_proposer.py` (NOWY): per typ zabudowy
   - **DETACHED**: prostokąt 9.5×11m w środku buildable_zone
   - **SEMI (bliźniacza)**: pary sub-działek z budynkami stykającymi się 1 ścianą
   - **TERRACED (szeregowa)**: łańcuchy z budynkami stykającymi się 2 ściany
6. **Strategia subdivider `road_tree_minimal_roads`** — pierwsza próbowana, fewer branches
7. **Scorer mocniejsza penalizacja dróg**: waga 0.30, 8% road = score 0

**Pytest:** 277 passed, 0 failed. 0 regresji.

---

## Stan końcowy GUI (po `python3 -m ui.main_window`)

| Tab | Co działa |
|---|---|
| **Stage 1 Plot Analyser** | Mode A (whole plot) z wielorodzinną prostokątną, Mode B (subdivision) z propozycjami budynków per typ, Eksport raportu PDF dla obu |
| **Stage 2 Volume Generator** | Placeholder — NIE rozpoczęte |
| **Stage 3 Floor Layout** | Działa (rectangular MVP) |
| **Stage 4 Apartment Layout** | Pełny V1-V4 export (zones + walls + doors z biblioteki + windows WT 1/8 + labels) — wymaga custom Tapir AC29 build (`tapir-custom/`) |

---

## Co dalej — kolejność TODO

### 🥇 Priorytet 1 — Test wizualny zadań 1+2
Przetestuj w GUI 4 scenariusze, daj feedback:
1. **Mode A wielorodzinna** → prostokąt 14-16m depth × max width (NIE kwadrat)
2. **Mode B → DETACHED** → budynki 9.5×11m w środku sub-działek
3. **Mode B → BLIŻNIACZA** → pary budynków stykających się ścianą
4. **Mode B → SZEREGOWA** → ciągi budynków stykających się 2 ścianami

### 🥈 Zadanie 3 — Drogi minimum (częściowo zrobione)
- `road_tree_minimal_roads` strategy + scorer fix już są
- Sprawdzić czy obecne wystarczy lub dopracować

### 🥉 Zadanie 4 — Eksport Stage 1 do AC
- Sub-plots jako Slabs (przez Tapir CreateSlabs)
- Budynki jako Slabs
- Drogi jako Polylines / Slabs
- Plus przycisk "Wstaw do ArchiCAD" w Stage 1 widget

### 🏅 Faza 3 — Stage 2 minimalny (formularz)
- Footprint ze Stage 1 → user wpisuje liczba pięter, wysokość kondygnacji, typ dachu
- "Dalej" → przekazanie footprint piętra do Stage 3

### Faza 2 — Wariant B Stage 3 ↔ Stage 4 split view
- Klik mieszkania na piętrze → automatyczny rzut w Stage 4
- Persystencja mapy `apartment_id → FloorPlan`
- Batch export "wszystkie mieszkania na raz"

### Faza 1 — Stage 4 dopinki
- Drzwi wejściowe automatycznie (entry_point z auto-detect)
- Wybór piętra przy eksporcie (floorIndex)
- Kategorie zon w AC (Mieszkalne/Komunikacyjne/Sanitarne)

---

## Reguły workflow do PAMIĘTANIA

**Z `docs/FUNDAMENTAL_RULES.md` (NIENARUSZALNE):**
- **F2**: łazienka ≤ 5m², WC ≤ 3m² ABSOLUTNIE
- **B1**: 2 fail = REWRITE, NIE 3-cia próba
- **B2**: Plan PRZED zmianą kodu, czekaj na OK
- **B6**: słuchaj user'a dosłownie
- **B7**: tłumacz architektonicznie nie programistycznie
- **B10**: po polsku, kolega-do-kolegi

**Z lekcji 2026-05-22:**
- Pytania STRATEGICZNE pytaj zanim implementujesz (B5) — np. głębokości traktów per typ
- QSettings TESTOWE potrafi wyciekać → `isolated_qsettings` fixture musi czyścić cache w setup/teardown
- Tapir 1.4.0 limits: brak GetUserPoint (workaround = Inner Edge polling), CreateDoors bez oSide/reflected (custom build dorobiony w `tapir-custom/`)

---

## Środowisko / komendy

```bash
# venv
source venv/bin/activate

# uruchom GUI
python3 -m ui.main_window

# uruchom pytest (pełny, ~3.5 min)
python3 -m pytest --ignore=notebooks -q

# uruchom tylko subdivider
python3 -m pytest tests/test_plot_subdivider.py tests/test_plot_variant_generator.py -q

# uruchom Stage 1 testy
python3 -m pytest tests/test_buildable_zone.py tests/test_plot_verifier.py tests/test_site_planner.py -q
```

**Custom Tapir Add-On** (potrzebny tylko dla Stage 4 export):
- Folder: `/Users/dawidcwiertniewicz/Desktop/claude code/tapir-custom/`
- Bundle: `/Applications/Graphisoft/Archicad 29/Dodatki/TapirAddOn_AC29_Mac.bundle`
- Backup oryginalnego: `.bundle.orig`
