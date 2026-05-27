# Briefing — następna sesja FP6 (po 2026-05-27, sesja 11)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## STAN: Sesja 11 (2026-05-27) — 3 PRIO zamknięte + spec/plan Stage 1→4 gotowy

Wszystko zacommitowane na `main`. Commits sesji 11:

```
4256997 docs(plan): Stage 1 → Stage 4 integration implementation plan
6a46498 docs(spec): fix wall_types contract — WallType enum, not list[str]
cfdf314 docs(spec): Stage 1 → Stage 4 integration design
483d71f chore(plot_subdivider): remove 21 dead functions (−39% file size)
12e6906 docs(state): sync Stage 1 Phase 3 — COMPLETED 2026-05-24 (commit 9017bae)
254c9f6 chore(stage1): Q21 visual sanity check + STATE/NEXT_SESSION sync
```

Co zrobione w sesji 11:
- Q21 visual sanity check PASS — 5 scenariuszy renderowanych przez prod `subdivide()` + `propose_buildings()`. Regresja 60×80 TWIN: 5/5 buildings (przed Q21: 0/7).
- Phase 3 STATE.md sync — sekcja "PLAN READY, NOT IMPLEMENTED" zaktualizowana do "COMPLETED 2026-05-24".
- Code health — 21 dead functions z `plot_subdivider.py` wyciętych (2860 → 1731 linii, −39%).
- Stage 1 → Stage 4 integration **spec + plan** gotowe (9 TDD tasków), **implementacja NIE rozpoczęta**.

Pytest (non-GUI suite): **287 passed, 31 skipped, 1 xpassed** (identyczne jak baseline sesji 10, zero regresji).

---

## 🎯 PRIO 1 — Wykonaj plan Stage 1 → Stage 4 integration

**Plan:** `docs/superpowers/plans/2026-05-27-stage1-stage4-integration.md` (9 tasków TDD, ~1.5h)
**Spec:** `docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md`

Co implementujemy: klik sub-działki w Stage 1 Mode B (SF: DETACHED/TWIN/TERRACED) → highlight → przycisk "Otwórz w Stage 4" → prefilled Stage 4 z auto-detekcją entry/walls → auto-switch tab → user klika Generate.

Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i wykonujemy plan stage1-stage4."**
Albo: **"Subagent-driven execution: superpowers:subagent-driven-development na plan stage1-stage4."**

Spodziewany wynik po wykonaniu: 295 passed (287 + 6 helper + 2 integration), end-to-end smoke na 60×80 TWIN pass.

---

## PRIO 2 — kolejne kandydaty (po Stage 1→4 integration)

W kolejności potencjalnej wartości:

1. **Q1.1(c) — push-neighbour mechanism** — deferred od Mode B port (Session 5, 2026-05-07). Obecnie Q1.1(d) drop-to-nieużytek fallback działa, ale push pozwoliłby utrzymać więcej sub-działek na L-shape z notchami.
2. **L-shape floors w Stage 3** — `floor_layout.py` zakłada prostokątne piętro; real-life pierwszego rzędu są L/U-shape.
3. **Walls + doors export do AC** — Stage 4 obecnie eksportuje tylko Zones.
4. **Stage 2 — volumetric generator** — jeszcze niezaczęty.
5. **DETACHED `max_sub_plot_area_m2` recalibration** — opcjonalna zmiana defaultu z 2000 → 1500 (lub 1200) m² po dyskusji architektonicznej.
6. **TERRACED 81 zamiast 120+ na 265×202** — diagnostyka `_is_buildable_shape` z `min_short_dim` — może ucina wąskie segmenty.

---

## PRIO 3 — code health (po cichu)

- ~~`core/plot_subdivider.py` legacy~~ — DONE 2026-05-27 (commit po PRIO 2):
  21 dead functions removed (2860 → 1731 linii, −39%).
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
