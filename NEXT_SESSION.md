# Briefing — następna sesja FP6 (po 2026-05-26)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## STAN: Q19 + Q20 + Q21 DONE — zacommitowane na `main` 2026-05-26

Sześć commitów (clean split, każdy z jasną wiadomością):

```
913525d chore(requirements): add reportlab>=4.0 (Stage 1 Phase 2 dep)
b69d762 fix(building_proposer): rename BuildingType.SEMI to TWIN + regression tests
9db4684 feat(stage1): Q19 — TWIN/TERRACED accept any road access (Mode B)
1801f58 feat(stage1): Q20 — auto-scale MPZP per BuildingType (segment-aware)
d9d566d feat(stage1): Q21 — shared walls zero side setback for TWIN/TERRACED
[ten] docs: NEXT_SESSION post-Q21 + STATE Session 10
```

Pytest (non-GUI suite, `pytest --ignore=notebooks --ignore=tests/test_gui.py`):

- **287 passed, 31 skipped, 1 xpassed, exit 0** (~10 min)
- Pre-Q21 baseline (subset zmienionych obszarów): 39 pass + 1 fail (`test_propose_buildings_twin_runs_and_assigns`)
- Post-Q21: ten test pass + 4 nowe `TestQ21SharedWalls` zielone

Dawid przeszedł na `main` bezpośrednio (bez feature/PR) zgodnie z decyzją sesji.

---

## 🎯 PRIO 1 — manualna weryfikacja AC

Q21 logika ma testy jednostkowe (5 GREEN), ale architektoniczna sanity check
na realnej działce z AC jeszcze nie była robiona.

```bash
source venv/bin/activate
python3 -m ui.main_window
```

Scenariusze do sprawdzenia:

1. **265×202 m (Dawid's AC test plot, regression dla Q19):**
   - DETACHED: powinno dać ~50 sub-działek równomiernie.
   - TWIN: ~60-80 sub-działek, **pary** budynków stykające jedną ścianą po stronie partnera.
   - TERRACED: ~120+ sub-działek, **ciągi** budynków stykające dwoma ścianami bocznymi (wewnątrz łańcucha).

2. **60×80 m (regression Q21):**
   - TWIN: ≥ 1 budynek uplasowany (przed Q21: 0/7).
   - TERRACED: nadal działa (przed Q21 też działał, ale Q21 nie psuje).

3. **Mode A (sanity):** dowolna jednorodzinna działka — sprawdzić że
   buildable_zone wygląda tak jak przed (`is_shared_wall=False` domyślnie,
   Q21 flag nie wpływa).

Jeśli któryś scenariusz daje wizualnie złe wyniki → diagnoza zanim
implementujemy Q22 cokolwiek (B1: 2 fail = REWRITE).

---

## PRIO 2 — kolejne kandydaty (do decyzji Dawida)

W kolejności potencjalnej wartości:

1. **STATE.md Phase 3 sync** — sekcja "Stage 1 Phase 3 — PLAN READY, NOT IMPLEMENTED"
   jest stale, bo Phase 3 (UI Eksport PDF) shipowała w commit `9017bae`.
   Przeczytać Phase 3 PR/diff, zaktualizować STATE.md sekcję.
2. **Q1.1(c) — push-neighbour mechanism** — deferred od Mode B port (Session 5,
   2026-05-07). Obecnie Q1.1(d) drop-to-nieużytek fallback działa, ale push
   pozwoliłby utrzymać więcej sub-działek na L-shape z notchami.
3. **L-shape floors w Stage 3** — `floor_layout.py` zakłada prostokątne piętro;
   real-life pierwszego rzędu są L/U-shape.
4. **Walls + doors export do AC** — Stage 4 obecnie eksportuje tylko Zones.
5. **Stage 1 → Stage 4 integration** — kliknięcie sub-działki w Stage 1 GUI →
   otwórz jej obrys jako wejście do Stage 4.
6. **Stage 2 — volumetric generator** — jeszcze niezaczęty.

---

## PRIO 3 — code health (po cichu)

- `core/plot_subdivider.py` — legacy experimental algorithms (`_pattern_*`,
  `_recursive_obb_split`, `_compute_road_tree`, `_generate_grid`, ...) są
  martwy kod (active path = `_generate_obb_layout` + `generate_road_tree_layout`).
  Przenieść do `notebooks/archive/`.
- Shapely `oriented_envelope` warnings (~10k per pytest run) — nie blokują,
  można zignorować w `pyproject.toml` filterwarnings.

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

python3 -m pytest tests/test_plot_subdivider.py tests/test_building_proposer.py \
                  tests/test_plot_variant_generator.py -v             # zmienione obszary (~7 min)

python3 -m pytest tests/test_plot_subdivider.py::TestQ21SharedWalls -v # Q21 alone (~1s)
```

**Custom Tapir Add-On** dla Stage 4 export — bez zmian, `tapir-custom/`
w katalogu `claude code/`.
