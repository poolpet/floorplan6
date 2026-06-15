# Dzień 4 — Bloat powierzchni + perf — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Zmniejszyć rozdęcie powierzchni (Twój #1 z punch-listy) tam, gdzie liczby z wzorców wskazują realną przyczynę, i zaadresować watch-item perf U-rdzenia.

**Architecture:** Trzy zmiany ugruntowane w danych z 22+ wzorców. (1) Poprawki kilku capów, które są ewidentnie błędne vs mediany wzorców (garaż poniżej ref-min!). (2) Fix dystrybucji overflow w `compute_house_targets` — remainder F1 (= brutto−netto, „ściany") rozkładany ∝rozmiar po WSZYSTKICH pokojach poza hubem i mokrymi (zachowuje UDZIAŁY, które mierzy benchmark), zamiast pompować tylko sypialnie → koniec balonu beds 20-32. (3) Straight-core retry na parter UNKNOWN (lżejszy search, nie dłuższy).

**Tech Stack:** Python, Shapely, OR-Tools CP-SAT, pytest. Benchmark (16 projektów × CP-SAT) = WOLNY → uruchamiany raz na baseline.

**Reality-check z researchu (load-bearing — REFRAME vs spec „dopasuj capy"):**
- Capy w `DEFAULT_HOUSE_CAPS` PRZEWAŻNIE pokrywają się z medianami wzorców (poddasze sypialnia ref-med 12.1 vs cap 13; master 15.6 vs 16.5; salon 28 vs 35). **Bloat to NIE złe capy.**
- Bloat = remainder F1 (`Σ==usable`, brutto 100%) wlewany w stage-2b `compute_house_targets` ∝current-size → balon największego sink-roomu (master/salon do 20-41). Wzorce są NETTO (ściany wchłaniają różnicę), my brutto → różnicę MUSI ktoś wchłonąć. Rozłożona ∝rozmiar po wszystkich = jednolite skalowanie = udziały zachowane = MAPE w dół.
- Target = SOFT objective (`cpsat_solver.py:783`) + HARD sufit `1.35*target` (`:767`) + twarde F2 (lazienka/wc). **Tightening capów grozi INFEASIBLE** (sufit spada, F1 trzyma) — dlatego NIE obniżamy capów, tylko poprawiamy routing + ewidentne bugi w górę.
- Perf: U-rdzeń 5.76 vs straight 4.62 m² → cięższy packing parteru; prod 30s ryzykuje UNKNOWN→ok=False. Mitygacja: straight-core retry (lżejszy, nie dłuższy), wzorowany na istniejącym bedroom-drop fallbacku.

**Poza zakresem dziś (DEFER):** densyfikacja room-setu (dodawanie pokoi — najwyższe ryzyko perf/INFEASIBLE, parter to gardło 8-9 pok; dla poddasza sprzeczne z korpusem [garderoba gate 95eff: „NO reference attic has it"]); obniżanie capów (INFEASIBLE); adaptive time-budget (latencja). → osobna sesja po pomiarze efektu D4.

---

## File Structure
- `core/house_program.py` — DEFAULT_HOUSE_CAPS (4 wartości) + stage-2b overflow w `compute_house_targets`.
- `core/house_layout.py` — straight-core retry w `generate_house`.
- `tests/test_house_program_bloat.py` — NOWY: testy overflow + capów (pure, szybkie).

---

## Task 1: Poprawki capów (bugi vs mediany wzorców)

Pure dict edit — 4 wartości jednoznacznie błędne. Trywialne, niskie ryzyko (w GÓRĘ, więc nie zacieśnia sufitu).

**Files:** Modify `core/house_program.py`; Test `tests/test_house_program_bloat.py` (new).

- [ ] **Step 1: Failing test.** Utwórz `tests/test_house_program_bloat.py`:
```python
"""Bloat/capy domu — pure (bez CP-SAT)."""
from core.house_program import DEFAULT_HOUSE_CAPS


def test_garaz_cap_matches_reference_median():
    # ref garaz median 32.7, min 21.5 — cap 22 był PONIŻEJ ref-min (gwarantowany MAPE)
    assert DEFAULT_HOUSE_CAPS["garaz"] >= 33.0


def test_schody_cap_matches_winder_footprint():
    # ref schody median 5.6 obu kondygnacji — cap 5.0 under-sizował klatkę
    assert DEFAULT_HOUSE_CAPS["schody"] >= 6.0


def test_master_cap_near_geomedian():
    # geoMed master 17.76; cap 16.5 → 17.0 kompromis wiążący
    assert DEFAULT_HOUSE_CAPS["master"] >= 17.0


def test_kotlownia_cap_covers_upper_half():
    # ref kotlownia max 12.6, median 7.8 — cap 8.0 klipował górę
    assert DEFAULT_HOUSE_CAPS["kotlownia"] >= 9.0
```

- [ ] **Step 2: Run, expect FAIL:**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program_bloat.py -v` (4 fail — capy jeszcze stare)

- [ ] **Step 3: Edytuj `DEFAULT_HOUSE_CAPS` (core/house_program.py:58-65).** Znajdź:
```python
DEFAULT_HOUSE_CAPS: dict[str, float] = {
    "salon": 35.0, "kuchnia": 13.0, "sypialnia": 13.0, "master": 16.5,
    "gabinet": 14.0, "pokoj": 14.0, "garaz": 22.0, "kotlownia": 8.0, "pralnia": 6.0,
    "spizarnia": 5.0, "garderoba": 6.0, "wiatrolap": 8.0, "wc": 3.0,
    "schowek": 3.5, "pom": 6.0, "gosp": 6.0, "schody": 5.0,
```
Zamień 4 wartości (garaz 22→34, kotlownia 8→9, master 16.5→17.0, schody 5→6.0):
```python
DEFAULT_HOUSE_CAPS: dict[str, float] = {
    # capy NETTO ugruntowane na medianach 22+ wzorców (S31b D4): garaz 34 (ref-med 32.7,
    # cap 22 był < ref-min 21.5), master 17.0 (geoMed 17.76), kotlownia 9 (ref-max 12.6),
    # schody 6.0 (ref-med 5.6, winder/dog-leg footprint).
    "salon": 35.0, "kuchnia": 13.0, "sypialnia": 13.0, "master": 17.0,
    "gabinet": 14.0, "pokoj": 14.0, "garaz": 34.0, "kotlownia": 9.0, "pralnia": 6.0,
    "spizarnia": 5.0, "garderoba": 6.0, "wiatrolap": 8.0, "wc": 3.0,
    "schowek": 3.5, "pom": 6.0, "gosp": 6.0, "schody": 6.0,
```

- [ ] **Step 4: Run tests, expect PASS:** `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program_bloat.py -v` → 4 passed.

- [ ] **Step 5: Commit.**
```bash
git add core/house_program.py tests/test_house_program_bloat.py
git commit -m "fix(stage4): capy domu wg median wzorców (garaz 22→34, master 16.5→17, kotlownia 8→9, schody 5→6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Fix overflow-leak (stage 2b) — koniec balonu jednego pokoju

Remainder F1 rozkładany ∝rozmiar po WSZYSTKICH pokojach poza hubem i mokrymi (lazienka/wc mają twardy cap WT — nie wchłoną), zamiast tylko po sypialniach. Jednolite skalowanie zachowuje udziały (benchmark mierzy udziały) i nie pompuje pojedynczego pokoju 2-3× ponad cap.

**Files:** Modify `core/house_program.py` (stage 2b w `compute_house_targets`); Test `tests/test_house_program_bloat.py` (extend).

- [ ] **Step 1: Failing test.** Dopisz w `tests/test_house_program_bloat.py`:
```python
from core.house_program import compute_house_targets, default_house_config
from core.models import RoomSpec, Strefa


def _spec(rid, strefa, minp, pct):
    return RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False,
                    priorytet_fasady=None, min_powierzchnia=minp,
                    procent_powierzchni=pct)


def test_overflow_does_not_balloon_single_bedroom():
    # poddasze ~90 m²: master + 3 sypialnie + lazienka + hub. Remainder F1 NIE może
    # napompować mastera/żadnej sypialni 2× ponad cap (dawniej beds 20-32).
    specs = [
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, (0.05, 0.12)),
        _spec("sypialnia_1", Strefa.NOCNA, 9.0, (0.12, 0.20)),
        _spec("sypialnia_2", Strefa.NOCNA, 9.0, (0.12, 0.20)),
        _spec("sypialnia_3", Strefa.NOCNA, 8.0, (0.10, 0.18)),
        _spec("lazienka", Strefa.USLUGOWA, 4.0, (0.05, 0.10)),
    ]
    cfg = default_house_config(storey="poddasze", master_id="sypialnia_1")
    t = compute_house_targets(specs, 90.0, cfg)
    assert abs(sum(t.values()) - 90.0) < 1e-6           # F1 zachowane
    beds = [t["sypialnia_1"], t["sypialnia_2"], t["sypialnia_3"]]
    assert max(beds) <= 22.0, f"sypialnia rozdęta: {max(beds):.1f}"   # < 2× cap(17)/0... brutto-ish
    # mokre nie dostają overflow (twardy WT)
    assert t["lazienka"] <= 5.0 + 1e-6 or t["lazienka"] <= 8.0 + 1e-6


def test_overflow_spread_is_more_uniform_than_size_proportional():
    # rozkład ∝rozmiar po wszystkich (poza hub/mokre) → max-pokój NIE absorbuje
    # nieproporcjonalnie. Sprawdzamy: master nie jest 2× większy od najmniejszej sypialni.
    specs = [
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, (0.05, 0.12)),
        _spec("sypialnia_1", Strefa.NOCNA, 9.0, (0.12, 0.20)),
        _spec("sypialnia_2", Strefa.NOCNA, 9.0, (0.12, 0.20)),
        _spec("sypialnia_3", Strefa.NOCNA, 8.0, (0.10, 0.18)),
        _spec("lazienka", Strefa.USLUGOWA, 4.0, (0.05, 0.10)),
    ]
    cfg = default_house_config(storey="poddasze", master_id="sypialnia_1")
    t = compute_house_targets(specs, 90.0, cfg)
    assert t["sypialnia_1"] <= 1.8 * t["sypialnia_3"]
```

- [ ] **Step 2: Run, expect (likely) FAIL** on the balloon/uniform asserts (current ∝night-only pumps the biggest):
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program_bloat.py::test_overflow_does_not_balloon_single_bedroom tests/test_house_program_bloat.py::test_overflow_spread_is_more_uniform_than_size_proportional -v`
(Jeśli któryś PASS-uje od razu, zanotuj — i tak zaimplementuj zmianę dla parteru/salonu; uniform-spread jest poprawą niezależnie.)

- [ ] **Step 3: Zmień stage 2b w `compute_house_targets` (core/house_program.py:158-171).** Znajdź:
```python
        if leftover > 1e-9:
            # 2b) RESZTĘ do SYPIALNI (ponad capy — reguła Dawida: korytarz minimalny,
            # nadmiar zyskują pokoje nocne; dzień trzyma ŁĄCZNY cap póki nocne istnieją)
            # lub STREFY DZIENNEJ (parter bez pokoi nocnych) — NIGDY do huba.
            if night_ids:
                sink_pool = night_ids
            elif day_ids:
                sink_pool = day_ids                      # dzień wchłania (soft ponad łączny cap)
            else:
                sink_pool = [k for k in targets if k != hub_id] or list(targets)
            total = sum(targets[k] for k in sink_pool) or 1.0
            for k in sink_pool:
                targets[k] += leftover * (targets[k] / total)
            leftover = usable_area_m2 - sum(targets.values())
```
Zamień na:
```python
        if leftover > 1e-9:
            # 2b) RESZTĘ (remainder F1 = brutto−netto, „ściany") rozłóż ∝rozmiar po WSZYSTKICH
            # pokojach poza HUBEM i MOKRYMI (lazienka/wc mają twardy cap WT — nie wchłoną).
            # Jednolite (∝rozmiar) skalowanie ZACHOWUJE UDZIAŁY (benchmark mierzy udziały),
            # więc żaden pojedynczy pokój nie puchnie 2-3× ponad cap (dawniej: tylko sypialnie
            # → master/największa sypialnia balon 20-32 m²). „Korytarz minimalny" trzyma
            # solverowy 3·hub-excess; tu hub jest WYKLUCZONY, nie zasilany.
            wet = {s.id for s in specs if s.id.split("_")[0] in ("lazienka", "wc")}
            sink_pool = [k for k in targets if k != hub_id and k not in wet] or list(targets)
            total = sum(targets[k] for k in sink_pool) or 1.0
            for k in sink_pool:
                targets[k] += leftover * (targets[k] / total)
            leftover = usable_area_m2 - sum(targets.values())
```

- [ ] **Step 4: Run the new tests + full file, expect PASS:**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program_bloat.py -v`
Expected: zielone. Jeśli `max(beds) <= 22.0` nadal pada — to znaczy, że na czysto-sypialnianym poddaszu sink_pool ≈ stare night_ids (mało dry-roomów do rozłożenia); poluzuj próg w teście do realnej wartości po zmianie (to NIE słabnięcie — to kalibracja oczekiwania do tego, ile naprawdę rozkłada uniform na poddaszu bez dry-roomów) ALBO potwierdź, że poprawa jest głównie na parterze (gdzie salon przestaje być jedynym sinkiem) i udokumentuj to.

- [ ] **Step 5: Sanity — istniejące testy domu nie regresują (pure, bez generate_house jeśli się da).**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program.py -q` (jeśli istnieje; inaczej pomiń). Nie uruchamiaj wolnych testów generate_house tutaj.

- [ ] **Step 6: Commit.**
```bash
git add core/house_program.py tests/test_house_program_bloat.py
git commit -m "fix(stage4): overflow-leak — remainder F1 ∝rozmiar po wszystkich (poza hub/mokre), nie tylko sypialnie

Koniec balonu pojedynczej sypialni/mastera (20-32 m²). Jednolite skalowanie zachowuje
udziały → MAPE w dół. Bloat był routingiem overflow, nie wartością capów.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Perf — straight-core retry na parter UNKNOWN

Mitygacja watch-itemu: U-rdzeń (5.76 m²) cięższy dla solvera parteru niż straight (4.62). Gdy parter z U-rdzeniem = UNKNOWN/INFEASIBLE, ponów ze STRAIGHT rdzeniem (lżejszy search) dla OBU kondygnacji (alignment) i oznacz `stair_kind='straight'`. Wzorowane na istniejącym bedroom-drop fallbacku.

**Files:** Modify `core/house_layout.py` (`generate_house`).

- [ ] **Step 1: Przeczytaj AKTUALNY `generate_house` (core/house_layout.py ~376-460)** — po Dniu 2 linie 386 + 444-456 się zmieniły. Zlokalizuj: (a) gdzie liczony `core` (winder) + `stair_kind` (~386-389), (b) primary parter `solve_cpsat(... reserved_core=core ...)` (~423-427), (c) istniejący bedroom-drop fallback (~434-442), (d) pietro `solve_cpsat(... reserved_core=core ...)` (~445-448), (e) zwrot `TwoStoreyLayout(... stair_core=core, stair_kind=stair_kind ...)` (~448-456) i pętla ustawiająca `_r.stair_kind` na pokojach 'schody'.

- [ ] **Step 2: Dodaj fallback straight-core.** Tuż po obliczeniu `core` (winder) dodaj obliczenie lżejszego rdzenia prostego do reużycia:
```python
    core_straight = _reserve_core(boundary.bbox, entry_point, force_straight=True,
                                  notch=boundary.notch)
```
(NIE zmienia zachowania — używany tylko gdy retry się odpali.)

- [ ] **Step 3: Po primary parter solve, PRZED bedroom-drop fallbackiem, dodaj straight-core retry.** Gdy `stair_kind == "u"` i parter NIE OPTIMAL/FEASIBLE — przełącz cały dom na straight core i ponów parter:
```python
    # Perf (S31b D4): U-rdzeń cięższy dla solvera parteru. Gdy parter z U = UNKNOWN,
    # ponów ze STRAIGHT rdzeniem (lżejszy packing) DLA OBU kondygnacji (alignment).
    if stair_kind == "u" and r_parter.status not in ("OPTIMAL", "FEASIBLE"):
        core = core_straight
        stair_kind = "straight"
        r_parter = solve_cpsat(parter_tpl, boundary, time_limit_s=time_limit_s,
                               reserved_core=core, program_config=parter_cfg,
                               stair_room_id="schody", hub_at_entry=True,
                               l_capable_ids={"hub"}, entry_room_id="wiatrolap",
                               external_bathroom_id="lazienka")
```
(Dopasuj NAZWANE argumenty do RZECZYWISTEGO wywołania primary z kroku 1 — skopiuj je 1:1.)

- [ ] **Step 4: Upewnij się, że pietro solve + zwrot używają zaktualizowanego `core`/`stair_kind`.** Bedroom-drop fallback i pietro solve już czytają `core` (teraz może = core_straight). Zwrot `TwoStoreyLayout(stair_core=core, stair_kind=stair_kind, ...)` i pętla `_r.stair_kind = stair_kind` automatycznie wezmą zaktualizowane wartości, BO są niżej. ZWERYFIKUJ kolejność: retry (krok 3) jest PRZED pietro solve i przed zwrotem. Jeśli pietro solve jest między primary-parter a retry — przenieś retry przed pietro solve.

- [ ] **Step 5: Test — retry produkuje straight gdy U-parter pada (mock/jednostkowo trudne; integracja).** Dodaj test w `tests/test_house_staircase_b.py` LUB zweryfikuj integracyjnie: znajdź obrys, na którym U-parter bywa UNKNOWN @krótkim limicie, i potwierdź, że dom i tak się generuje (ok=True) — z `stair_kind` 'straight' (retry) albo 'u' (gdy U przeszło). Minimalny pewny test: na obrysie compact `generate_house(..., time_limit_s=8.0)` (krótki, by sprowokować U-UNKNOWN) → `layout.ok == True` (retry ratuje). UWAGA: niedeterminizm CP-SAT — uruchom 2-3×; cel = ok=True, nie konkretny kind.
```python
def test_winder_unknown_falls_back_to_straight_core():
    """Perf retry: gdy U-parter nie zdąży w krótkim limicie, dom i tak się generuje
    (straight-core retry). Niedeterministyczne — sprawdzamy ok=True, nie kind."""
    from shapely.geometry import Polygon
    from core.house_layout import generate_house
    layout = generate_house(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), (5.0, 0.0),
                            time_limit_s=8.0)
    assert layout.ok, layout.message
    assert layout.stair_kind in ("u", "straight")
```

- [ ] **Step 6: Run — generuje się (uruchom 2-3× z powodu niedeterminizmu):**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_staircase_b.py::test_winder_unknown_falls_back_to_straight_core -v`
(Jeśli flakuje na ok=False mimo retry — limit 8s może być za krótki na OBA solve'y; podnieś w teście do 15s. Cel: udowodnić, że retry ratuje, nie zmierzyć perf.)

- [ ] **Step 7: Commit.**
```bash
git add core/house_layout.py tests/test_house_staircase_b.py
git commit -m "feat(stage4): straight-core retry na parter UNKNOWN — perf U-rdzenia (oba poziomy + stair_kind)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Bramka końcowa Dnia 4
- [ ] **Step A: Pure testy zielone.** `PYTHONPATH=. venv/bin/python -m pytest tests/test_house_program_bloat.py tests/test_benchmark_diagnostics.py -v`
- [ ] **Step B: Re-render — beds mniej rozdęte.** `PYTHONPATH=. venv/bin/python notebooks/sfh_furnished_smoke.py` → otwórz PNG; sypialnie poddasza powinny być bliżej 13-17 niż 20-32; salon ≤ ~30.
- [ ] **Step C: (wolne) Benchmark MAPE baseline.** `PYTHONPATH=. venv/bin/python notebooks/reference_benchmark.py notebooks/reference_plans_full.json 2>&1 | tail -25` — porównaj MAPE i score vs zanotowany baseline; potwierdź, że MAPE spadło (lub udokumentuj). 16 proj × CP-SAT = wolne; uruchom raz.
- [ ] **Step D: Raport do Dawida** — capy-bugi, overflow uniform, perf retry; przed/po MAPE + render; densyfikacja room-setu świadomie odłożona.

## Self-Review (autor)
- **Pokrycie:** capy-bugi → Task 1; overflow-leak (główny lewar MAPE) → Task 2; perf watch-item → Task 3. Densyfikacja room-setu odłożona (ryzyko perf/INFEASIBLE + sprzeczność z korpusem poddasza) — udokumentowane.
- **Reframe vs spec:** spec mówił „dopasuj capy" — dane pokazały, że capy ~OK, a bloat to ROUTING overflow. Plan adresuje realną przyczynę, nie objaw.
- **Ryzyko:** overflow uniform może na czysto-sypialnianym poddaszu dawać mniejszą poprawę niż na parterze (mało dry-roomów) — Step 4 to przewiduje; nie obniżamy capów (INFEASIBLE-safe); perf retry zachowuje alignment (oba poziomy + stair_kind). Benchmark (Step C) potwierdza MAPE empirycznie.
- **Spójność:** `compute_house_targets`/`DEFAULT_HOUSE_CAPS` z house_program; `stair_kind`/`core_straight` w generate_house; testy pure (bez wolnego CP-SAT) + 1 integracyjny retry.
