# Briefing — następna sesja FP6 (po 2026-05-27)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## STAN: Q19 + Q20 + Q21 DONE + visual sanity check PASS — wszystko na `main`

Q19/Q20/Q21 commits (2026-05-26):

```
913525d chore(requirements): add reportlab>=4.0 (Stage 1 Phase 2 dep)
b69d762 fix(building_proposer): rename BuildingType.SEMI to TWIN + regression tests
9db4684 feat(stage1): Q19 — TWIN/TERRACED accept any road access (Mode B)
1801f58 feat(stage1): Q20 — auto-scale MPZP per BuildingType (segment-aware)
d9d566d feat(stage1): Q21 — shared walls zero side setback for TWIN/TERRACED
```

Visual sanity check Q21 (2026-05-27):

- `notebooks/stage1_q21_sanity.py` — 5 scenariuszy renderowanych przez
  produkcyjne `subdivide()` + `propose_buildings()` (PNG w `notebooks/output/`).
- Regresja 60×80 TWIN: **5/5 buildings** (przed Q21 było 0/7) ✅
- 265×202 TWIN: 70 sub, 35 par TWIN, Q21 shared walls poprawne ✅
- 265×202 TERRACED: 81 sub w 6 ciągach, każda z budynkiem ✅
- Architectural review owner: PASS — Q21 zamknięte.

Pytest (non-GUI suite, `pytest --ignore=notebooks --ignore=tests/test_gui.py`):

- **287 passed, 31 skipped, 1 xpassed, exit 0** (~10 min, baseline z sesji 10)

Outstanding niepokoje (NIE bugi, raczej kalibracja na przyszłość):
- DETACHED 30 sub na 265×202 (avg 1729 m²) — `max_sub_plot_area_m2=2000` default może być za duży.
- TERRACED 81 sub zamiast oczekiwanych 120+ — `_is_buildable_shape` z `min_short_dim` może ucinać wąskie segmenty.
- Pionowa droga w środku 265×202 — algorytm dzieli na 4 kwadranty, alternatywą byłaby 1 droga wzdłuż dłuższej osi.

---

## 🎯 PRIO 1 — STATE.md Phase 3 sync (quick win)

Sekcja "Stage 1 Phase 3 — PLAN READY, NOT IMPLEMENTED" w `docs/STATE.md`
jest stale — Phase 3 (UI Eksport PDF) shipowała w commit `9017bae`.
Przeczytać Phase 3 PR/diff, zaktualizować sekcję. Bez kodu, bez testów.

---

## PRIO 2 — kolejne kandydaty (do decyzji Dawida)

W kolejności potencjalnej wartości:

1. **Q1.1(c) — push-neighbour mechanism** — deferred od Mode B port (Session 5,
   2026-05-07). Obecnie Q1.1(d) drop-to-nieużytek fallback działa, ale push
   pozwoliłby utrzymać więcej sub-działek na L-shape z notchami.
2. **L-shape floors w Stage 3** — `floor_layout.py` zakłada prostokątne piętro;
   real-life pierwszego rzędu są L/U-shape.
3. **Walls + doors export do AC** — Stage 4 obecnie eksportuje tylko Zones.
4. **Stage 1 → Stage 4 integration** — kliknięcie sub-działki w Stage 1 GUI →
   otwórz jej obrys jako wejście do Stage 4.
5. **Stage 2 — volumetric generator** — jeszcze niezaczęty.
6. **DETACHED `max_sub_plot_area_m2` recalibration** — opcjonalna zmiana
   defaultu z 2000 → 1500 (lub 1200) m² po dyskusji architektonicznej.

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
