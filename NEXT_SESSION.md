# Briefing — następna sesja FP6 (po 2026-05-27, sesja 12)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## STAN: Sesja 12 wchodzi z zamkniętą integracją Stage 1 → Stage 4

Sesja 11 (2026-05-27, druga część) zamknęła **PRIO 1 = Stage 1 → Stage 4 integration**.
Wszystko zacommitowane na `main`. Commity sesji 11 (cały zestaw):

```
7d72143 test(stage1): Qt smoke for signal->slot wiring
8d0beff feat(main_window): confirm dialog when overwriting Stage 4 variants
fc9547e feat(main_window): _populate_stage4_from_stage1 slot + signal wire-up
cfb5ac7 feat(stage1): 'Otwórz w Stage 4' button + apartment_layout_requested signal
61d8eae feat(stage1): canvas click selects sub-plot (yellow highlight)
fff45d2 refactor(main_window): expose self.stage1_widget and self.apt_tab
eedc4d4 feat(core): building_to_apartment_input helper for Stage 1->4
bbf56b8 test(stage1): RED tests for building_to_apartment_input helper
4eddd29 docs(next): session 11 close + PRIO 1 = execute stage1→4 plan
4256997 docs(plan): Stage 1 → Stage 4 integration implementation plan
6a46498 docs(spec): fix wall_types contract — WallType enum, not list[str]
cfdf314 docs(spec): Stage 1 → Stage 4 integration design
483d71f chore(plot_subdivider): remove 21 dead functions (−39% file size)
12e6906 docs(state): sync Stage 1 Phase 3 — COMPLETED 2026-05-24
254c9f6 chore(stage1): Q21 visual sanity check + STATE/NEXT_SESSION sync
```

Co dowiezione w sesji 11 (część integracyjna):

- Nowy pure-Python helper `core/building_to_apartment_input.py` — SubPlot → (polygon, entry, wall_types) z auto-detekcją entry (krawędź z midpointem najbliżej drogi) i wall_types (INTERNAL gdy midpoint krawędzi ≤ 0.5 m od Q21 `is_shared_wall=True`).
- **Deviation od spec/planu (świadoma):** plan zakładał `edge.distance(shared_wall)` jako kryterium — empirycznie powodowało false-positive INTERNAL na rogach budynku stykających się ze shared wall. Fix: midpoint krawędzi. Plan był RED dla TWIN test, midpoint daje GREEN.
- Stage1Widget: nowy sygnał `apartment_layout_requested(polygon, entry, walls)`, canvas click hit-test, żółty highlight, przycisk "Otwórz wybraną sub-działkę w Stage 4" włączający się tylko gdy zaznaczona sub-działka ma `proposed_building`.
- MainWindow: `self.stage1_widget` + `self.apt_tab` jako member, slot `_populate_stage4_from_stage1` (uzupełnia `_imported_*` + przełącza tab), confirm dialog z Cancel jako default.
- 6 unit testów helpera + 2 Qt smoke testy integracji.
- End-to-end smoke (programatic) na 60×80 TWIN: 5/5 sub-działek z budynkiem, klik #1 → polygon 76.5 m², entry (7.75, 35.5), walls [INTERNAL, FACADE, FACADE, FACADE] — dokładnie 1 INTERNAL + 3 FACADE jak oczekiwano dla TWIN.

Pytest non-GUI suite: **296 passed**, 29 skipped, 1 xpassed (target był 295: 287 baseline + 6 + 2). Jeden flake (`test_hub_adjacency_m2`) — siostra `test_hub_adjacency_m3` jest już xfail-marked z tego samego powodu (CP-SAT non-determinism + Shapely clipping); przechodzi w izolacji; niezwiązany z tą sesją.

---

## 🔥 PRIO 1 dla sesji 12 — manualny GUI smoke + ewentualne fixy UX

Implementacja przeszła test programatyczny, ale **żywy klik w GUI jeszcze nie zweryfikowany przez Dawida**. Sekwencja do sprawdzenia:

1. `source venv/bin/activate && python3 -m ui.main_window`
2. Stage 1 tab → Housing: Jednorodzinna, Mode: B → Building type: TWIN → W=60, D=80 (lub większy plot z AC)
3. Click **Generate** → 5+ sub-działek widocznych z propozycjami budynków
4. Click na dowolną sub-działkę na canvasie → **żółty highlight obwódki** + przycisk "Otwórz wybraną sub-działkę w Stage 4" enables
5. Click przycisk → tab przełącza się na Stage 4, preview obrysu budynku z entry pointem
6. Stage 4 → Click **Generate** → CP-SAT solver buduje rzut pokoi (~10 s)
7. (Edge case) Wygeneruj coś w Stage 4 ZANIM zrobisz krok 5 → przycisk "Otwórz" wywoła **confirm dialog "Nadpisać obecny rzut?"** z Cancel jako default

Co może wyjść nie tak (na co warto patrzeć):
- Highlight czy faktycznie żółty + widoczny — kolory matplotlib bywają jaśniejsze niż się wydaje
- Czy "Otwórz" jest enabled tylko gdy klik trafia w sub-działkę z `proposed_building` (TWIN sometimes prudko = 0 buildings na małych plotach)
- Czy status bar pokazuje "Załadowano sub-działkę…" z prawidłowym m²
- Czy entry point na preview wygląda sensownie (powinien być na krawędzi budynku najbliższej drodze)
- Czy walls są pokolorowane poprawnie w Stage 4 (INTERNAL vs FACADE)

---

## PRIO 2 — kolejne kandydaty (po manualnej weryfikacji PRIO 1)

W kolejności potencjalnej wartości:

1. **Q1.1(c) — push-neighbour mechanism** — deferred od Mode B port (Session 5, 2026-05-07). Obecnie Q1.1(d) drop-to-nieużytek fallback działa, ale push pozwoliłby utrzymać więcej sub-działek na L-shape z notchami.
2. **L-shape floors w Stage 3** — `floor_layout.py` zakłada prostokątne piętro; real-life pierwszego rzędu są L/U-shape.
3. **Walls + doors export do AC** — Stage 4 obecnie eksportuje tylko Zones.
4. **Stage 2 — volumetric generator** — jeszcze niezaczęty.
5. **Mode A → Stage 4 integration** — analogicznie do Mode B, ale UX inny (wybór wariantu propozycji budynku zamiast jednej sub-działki).
6. **DETACHED `max_sub_plot_area_m2` recalibration** — opcjonalna zmiana defaultu z 2000 → 1500 (lub 1200) m² po dyskusji architektonicznej.
7. **TERRACED 81 zamiast 120+ na 265×202** — diagnostyka `_is_buildable_shape` z `min_short_dim`.
8. **`test_hub_adjacency_m2` xfail-mark** — albo napraw root cause (Shapely clipping after MIN_SHARED_EDGE_CM constraint), albo oznacz xfail jak `m3`.

---

## PRIO 3 — code health (po cichu)

- Shapely `oriented_envelope` warnings (~11k per pytest run) — nie blokują, można zignorować w `pyproject.toml` filterwarnings.
- `_imported_wall_types` mainwindow code path — pozostaje wąskie miejsce typingu (np. `Optional[list[WallType]]` byłby cleaner niż `None | list[WallType]`).

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

python3 -m pytest tests/test_building_to_apartment_input.py \
                  tests/test_stage1_stage4_integration.py -v        # nowy obszar (~1s)

python3 -m pytest tests/test_plot_subdivider.py tests/test_building_proposer.py \
                  tests/test_plot_variant_generator.py -v             # zmienione obszary z poprzednich sesji
```

**Custom Tapir Add-On** dla Stage 4 export — bez zmian, `tapir-custom/`
w katalogu `claude code/`.
