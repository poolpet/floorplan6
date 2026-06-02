# Briefing — następna sesja FP6 (po 2026-06-01, sesja 17)

> **Jak zacząć:**
>
> ```bash
> cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
> claude
> ```
>
> Pierwsza wiadomość: **"Czytaj NEXT_SESSION.md i kontynuujemy."**

---

## ✅ STAN po sesji 18 (2026-06-02 — SCHODY Approach B: osobny pokój „Schody" + kompaktowy „Hol")

**Zrobione (zatwierdzone przez Dawida 2026-06-02: pinned schody, podest przy Holu/bieg w głąb,
sąsiedztwo tylko Hol). Zaprojektowane przez workflow-panel, TDD, potem adwersaryjny przegląd złapał
realny bloker (W/E) → naprawiony.**

- **Schody = OSOBNY pokój** przypięty do rdzenia klatki (4 równości x/y/w/h), pomijana reguła
  proporcji (straight-core 4,0×1,1 inaczej INFEASIBLE); **Hol = osobny kompaktowy hub** (gwiazda F5),
  już NIE zawiera rdzenia. Wyrównanie pionowe parter↔piętro z konstrukcji.
- **Orientacja biegu naprawiona** (Twój flagowany błąd): bieg wzdłuż dłuższej osi, strzałka „w górę"
  odchodzi OD holu. Zweryfikowane wizualnie na S i W: `notebooks/output/approach_b_stairs_*.png`.
- **Routing nadmiaru** (`house_program`): nadmiar → strefa dzienna (salon/kuchnia) do cap-ów, RESZTA
  → hub (elastyczny hol/podest); sypialnie/usługowe zostają capowane (koniec bloatu mastera).
- **Piętro odpięte od ściany wejścia** (`hub_at_entry=False`) — podest łączy się ze schodami, nie z
  drzwiami; naprawia wejścia W/E na 9×7/10×7 (3 sypialnie z oknami).
- **M1-M5 byte-identical** (wszystko bramkowane). **Pełny non-GUI suite: 346 passed / 30 skip /
  1 xpass / 0 failed.** Szczegóły: `docs/STATE.md` → Session 18.

### 🔥 Następne kroki (sesja 19 — kolejność)
1. **🔴 MEBLE — realna aranżacja (PRIORYTET, druga rzecz flagowana przez Dawida):** `core/furniture.py`
   greedy „pod ścianę" → reguły z `memory/project_archon_house_adjacency.md` furniture_rules: łóżko
   wezgłowiem do pełnej ściany bez okna (poddasze: nie pod skosem) + szafki nocne; sofa w rogu do
   TV/kominka + stolik; stół jadalniany na granicy salon/kuchnia; blat L/liniowo, zlew pod oknem;
   łazienka liniowo przy ścianie instalacyjnej; hol/schody bez mebli. Kształty pokoi są już stabilne
   po Approach B. Plan → OK → TDD.
2. **Overflow rooms (Faza 2):** capy są MIĘKKIE — na obrysach ≥~70 m²/kondygn. nadmiar puchnie w
   hub/podest (i lekko w kuchnię/garderobę). Fix: gdy capowany zestaw nie wypełnia usable → dodaj
   gabinet → 4. sypialnię → garaż, aż wypełni. Graf z `_adjacency.md` (room_set_by_size, overflow_rooms).
   Sygnał overflow wyprowadź z hub_target > sufit holu (nie z `unabsorbed_leftover` — jest martwy przy
   istniejącym hubie).
3. **`_reserve_core` notch-aware (PRZED wpięciem Stage-1 do trybu Dom):** dziś rdzeń może wpaść w
   wcięcie L-kształtu → INFEASIBLE (pre-existing; stary kod też). Czytaj `boundary.notch`, clamp/fallback;
   dodaj test regresji L-polygon.
4. **Tryb parterowy / małe domy (35-55 m²):** szablon `house_single_storey` (bez schodów/wiatrołapu/
   osobnej kuchni), obniż `MIN_STOREY_AREA` ~32. Progi z `_adjacency.md` (low_end_thresholds).
5. **Open-plan cap salonu:** kuchnia scalona → cap day-zone = łączny ~0,30-0,36·usable.
6. **Suwaki UI** w Stage 4 (tryb Dom) podpięte do `HouseProgramConfig`.

> ⚠️ Praca sesji 17 + 18 w working tree, **NIEzacommitowana** (commit/push = decyzja Dawida).

---

## ✅ STAN po sesji 17 (2026-06-01 — GAP fix: konfigurowalny program domu, cap-y + %-podział)

**Problem flagowany:** przerost pokoi (master ~22,9 / salon ~47) — nadmiar powierzchni
wpychany w jeden pokój (reguła Q6 z mieszkań, błędna dla domów).

**Grounding (zrobiony w tej sesji):** przebadane wzorce ARCHON w `rzuty/domy/` (~25 czytelnych
PDF + 8 screenshotów + serie 35/70/120 i piwnice — wiele to projekty Dawida PROJ-BUD/Łącko).
Policzone cap-y (n=19–37 na typ) + graf sąsiedztwa (F5 hub-centryczny) + reguła open-plan + progi
dolne. Szczegóły w pamięci: `memory/project_archon_house_conventions.md`, `_adjacency.md`,
`_session17_gap_fix.md`. (4 PDF-y A.01/A.02 były wektorowe bez tabeli — skala odzyskiwalna z drzwi
0,900/schodów 0,278, ale per-pokój NIEwiarygodne; Dawid re-eksportował 35/70/120 ze stemplami stref.)

**Zrobione + zielone (TDD):**
- NOWY `core/house_program.py` — `HouseProgramConfig` (EDYTOWALNE cap-y + %-udziały + łazienka
  per kondygnacja parter≤5/poddasze≤8 + `master_id`) + `compute_house_targets` (clamp %-udział do
  [min,cap] + water-fill reszty do cap-ów; salon/master nigdy ponad cap) + `default_house_config`
  + `DEFAULT_HOUSE_CAPS` (z ARCHON). **7 testów** `tests/test_house_program.py`.
- Wpięte w `cpsat_solver.solve_cpsat(program_config=...)`: ścieżka DOMU używa nowych targetów,
  resztę F1 kieruje do HUBA (nie największego = salon/master). **M1-M5 NIETKNIĘTE** (program_config=None → Q6).
- `generate_house` przekazuje config per kondygnacja (master=sypialnia_1).
- **Weryfikacja: dom 23 ✓, apartamenty M1-M5 48 ✓ (zero regresji). Render 63/64 m²: master
  22,9→16,6, salon capowany. `notebooks/output/reality_realny_*.png` + `notebooks/reality_check_gap.py`.**

**Decyzje Dawida (sesja 17):** cap-y ARCHON; pomieszczenia gospodarcze/techniczne capowane jak
łazienka (edytowalne); przy przeroście dodaj gabinet/sypialnię; konfigurowalny %-udział + max
metraży; łazienka parter≤5/poddasze≤8; **Faza 1+2 razem**; **config od razu pod UI (suwaki)**;
generator MA też robić **małe/parterowe domy 35-55 m²**.

**Trade-off (świadomy):** cap-y są MIĘKKIE (przez targety), żeby nie zawiesić dużych obrysów
(twardy cap zawieszał solver na 99/208 m²). Trzymają w realnym zakresie (≤~70 m²/kondygn.); na
90+ nadmiar wraca w pokoje (master ~25), bo capowany STAŁY zestaw nie wypełnia usable → to
naprawiają overflow rooms (krok 1 niżej).

> ✅ **Dawid zweryfikował rendery (2026-06-01):** „układ i rozmieszczenie pomieszczeń wygląda
> dobrze" — **fix GAP/cap-y ZAAKCEPTOWANY**. Źle: (1) **schody** i (2) **meble**.

### 🔥 Następne kroki (sesja 18 — kolejność)
1. **🔴 SCHODY → Approach B (PRIORYTET, feedback Dawida):** schody mają być **osobnym pokojem**
   (osobna „Schody" klatka ~4-5 m² + osobny „Hol" hub), NIE scalony „Hol+schody"; oraz **zła
   orientacja/kierunek biegu** do poprawienia. Per B1 (setback już dłubany 1,3→0,8) = REWRITE na
   Approach B, nie kolejne dłubanie. Grunt: ARCHON (`memory/project_archon_house_adjacency.md`
   staircase: mid-depth, przy ścianie wewnętrznej, wychodzi na Hol, nigdy przy fasadzie).
   Dotyka: `house_parter/pietro.json` (rozdziel hub na schody+hol), `_reserve_core`/`generate_house`,
   renderer (orientacja symbolu schodów). Plan w prostym języku → OK → TDD.
2. **🔴 MEBLE — realna aranżacja (PO schodach, bo Approach B zmienia kształty pokoi):**
   `core/furniture.py` z greedy „pod ścianę" → reguły z `_adjacency.md` furniture_rules: łóżko
   wezgłowiem do pełnej ściany bez okna (poddasze: nie pod skosem) + szafki nocne; sofa w rogu
   zwrócona do TV/kominka + stolik na środku; stół jadalniany na granicy salon/kuchnia; blat
   liniowo/L, zlew pod oknem; łazienka liniowo przy ścianie instalacyjnej, drzwi na zewnątrz;
   hol bez mebli. To druga rzecz, którą Dawid wskazał jako złą — robić zaraz po schodach.
3. **Overflow rooms (Faza 2):** gdy obrys duży → dodaj gabinet → 4. sypialnię → garaż, aż
   capowany zestaw wypełni usable. Wtedy cap-y trzymają TWARDO na każdym rozmiarze. Graf z
   `_adjacency.md` (room_set_by_size, overflow_rooms).
4. **Tryb parterowy / małe domy (35-55 m²):** nowy szablon `house_single_storey` (bez schodów/
   wiatrołapu/osobnej kuchni; hol+salon+1-2 sypialnie+łazienka), obniż `MIN_STOREY_AREA` do ~32.
   Progi z `_adjacency.md` (low_end_thresholds). A.01 35/70/120 = kalibracja.
5. **Open-plan cap salonu:** gdy kuchnia scalona → cap day-zone = łączny ~0,30-0,36·usable
   (~30-43), nie salon-only. Patrz `_adjacency.md` open_plan_rule.
6. **Suwaki UI** w Stage 4 (tryb Dom) podpięte do `HouseProgramConfig` (cap-y + %).

> ⚠️ FAKTY (korekta nieaktualnych docs niżej): praca SFH (sesje 14-16, gałęzie feat/sfh-*) JEST
> zmergowana do `main`. `main` ~27 commitów przed `origin/main`, NIEpushnięte (push = decyzja Dawida).
> Praca sesji 17 w working tree, **NIEzacommitowana**.

---

## ✅ STAN po sesji 16 (2026-06-01 — Plan 3 UI: tryb DOM w Etapie 4)

**Zrobione (gałąź `feat/sfh-furniture`):** dodano do zakładki Stage 4 **równoległą ścieżkę
domu jednorodzinnego**, przełączaną radiem „Tryb" (Mieszkanie w bloku M1-M5 / Dom
jednorodzinny). Ścieżka mieszkań M1-M5 **bez zmian** — dom jest dodatkiem, nie zamianą.

1. **`viz/house_preview.py`** (NOWY, GUI-free; 5 testów w `tests/test_house_preview.py`):
   `furnish_layout` / `house_details_text` / `render_house_figure` — owijka na gotowy silnik
   `generate_house` + `place_furniture` + `render_two_storey`, żeby logika UI była testowalna
   bez PyQt (testy GUI padają headless).
2. **`ui/main_window.py`**: radio trybu; opcje mieszkania w kontenerze `apt_options`, nowy
   ukryty `house_options` (przełącznik `Meble`, domyślnie ON); `HouseGenerateWorker` (QThread)
   → `generate_house` (1 układ, 2 kondygnacje); `_on_house_ready`/`_show_house` renderują
   PARTER|PIĘTRO w istniejącym podglądzie; **Export PNG działa**; **To-ArchiCAD wyłączone dla
   domu** (eksport do AC = późniejsza powłoka C++). Wspólny helper `_input_polygon_entry`.
3. **Weryfikacja:** nowy moduł 5 testów zielonych; realny e2e (CP-SAT `generate_house` 8×10 →
   `render_house_figure`) daje 2-panelowy PNG; **F2 trzyma w realnym przebiegu** (łazienka
   4.6 m² ≤ 5.0, WC 3.0 ≤ 3.0). Klik-przez-GUI = manualnie (headless GUI padają).
   Spec: `docs/superpowers/specs/2026-06-01-stage4-house-mode-ui-design.md`;
   plan: `docs/superpowers/plans/2026-06-01-stage4-house-mode-ui.md`.

4. **Schody + komunikacja (Approach A) — ZROBIONE:** `_stair_core_dims` (adaptacyjny rdzeń:
   prosty/U wg proporcji), `_reserve_core` cofnięte od wejścia (setback 0.8). Reality-check
   pokazał, że **GAP nadmiaru to artefakt za dużego obrysu** (na ~64 m²/kond. rozmiary OK) —
   zdeprioretyzowany. Hub „Hol+schody" jest geometry-bound (~11–13%), mniejszy/osobny = Approach B.
   8 testów; spec+plan `2026-06-01-house-staircase-circulation*`.

### 🔥 Następne kroki (wg `docs/ROADMAP_domy.md`)
1. **Realizm mebli** (osobna runda): aranżacja zamiast „pod ścianę bez kolizji" — sofa vs RTV,
   wezgłowie do ściany bez okna + szafki nocne, stół w jadalni; dopasowanie do realnej ściany.
   Najbliżej widocznej poprawy po schodach. Oprzeć o wzorce ARCHON (brainstorm → spec).
2. **Bliźniak → szeregowiec** (kolejne typy domów; sąsiednie obrysy rysowane ręcznie w AC).
3. **Approach B (fallback schodów):** osobny pokój „Schody" + „Hol/Korytarz" — tylko jeśli
   uznamy, że scalony hub ~11 m² to za mało wiarygodne (Dawid zaakceptował A wizualnie 2026-06-01).
4. **Export domu do AC** (ściany + drzwi) — realna „ostatnia mila" produktu (dziś tylko zony).
5. **Drobiazg UX (opcjonalnie):** wyłączać radio trybu w Etapie 4 w trakcie generowania.
6. **GAP nadmiaru** — tylko gdyby ktoś podał za duży footprint; na realnym domu nieistotny.
7. Później: Faza 2 (Stage 2/3 + pipeline 1→2→3→4) — wg roadmap ZA zamrożeniem.

> ⚠️ Gałąź `feat/sfh-furniture` (Sesje 15+16) **NIE zmergowana do main, NIE pushnięta.**
> main = `ca92621`. Decyzja merge/push → Dawid.

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
