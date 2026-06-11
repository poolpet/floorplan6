# STATE — current state of FloorPlan6

> Updated after every working session. If it doesn't reflect reality —
> Claude updates immediately.
>
> **Last update:** 2026-06-11 (Session 29 — branch `feat/sfh-open-plan-day-zone`: **KNEE-WALL v2 — poddasze na
> PEŁNYM footprincie + strefy niskiej ścianki kolankowej**). Decyzja Dawida po przeglądzie rzutów S27/28:
> poddasze ma powierzchnię JAK PARTER; wzdłuż DŁUŻSZYCH krawędzi (okapy) strefy niskie
> (`ATTIC_LOW_STRIP_FACTOR=0.20`/strona, `attic_low_strips()` w `core/house_layout.py`). Reguły: **(układ)**
> żaden pokój piętra nie może być W CAŁOŚCI w strefie (`solve_cpsat(..., low_zones=)` — dyzjunkcja 4 ucieczek
> per pokój×strefa; **WYJĄTEK schody** — Dawid: po schodach wchodzi się stopniowo, dolne stopnie nie potrzebują
> wysokości); **(meble)** wysokie (`furniture.TALL_TYPES` = szafa/regały/półki/kocioł) omijają strefy
> (`furnish_rooms(..., low_zones=)`), niskie — łóżko/WC/wanna — MOGĄ pod skosem (klasyka poddasza).
> WYCOFANE z S27: pas poddasza (`attic_boundary` zostaje w dataclass jako None — back-compat), bramka minimum
> ~76 m² (**domy 60-76 m² z poddaszem wracają** — `test_two_storey_63m2_generates_again`), duch pełnego obrysu
> w rendererze (zamiast: przyciemnienie stref + przerywana linia ścianki). ZOSTAJE z S27/28: bieg prosty wzdłuż
> kalenicy + L-podest + cały perf-fix. Kontrakt: `poddasze.meta.attic_low_strips`. Testy: rewrite
> `test_house_attic_shrink.py` (10, RED-first; geometria stref + nie-zawieranie + meble + kontrakt + 63 m²);
> batch 106/108 → po fixach (fake `low_zones` w preview-teście; próg sypialni → ≤30% kondygnacji z odnośnikiem
> do kolejki) zielono. **BENCHMARK: A01_70 (dom 68.7 m² z poddaszem) GENERUJE SIĘ — 2/3 wzorców, średnia
> 52.2/100** (A01_70=53.7, A01_120=50.7; spadek A01_120 z 56.7 = bloat sypialni na pełnym poddaszu — dokładnie
> mierzy kolejkowy room-set scaling). Render `rzuty/renders_mvp/1_dwukondygnacyjny.png`: łóżka pod skosem,
> szafy w strefie wysokiej, schody przecinają linię ścianki (wyjątek), piony OK; master 24.9 = znany GAP.
> **NEXT (kolejność wg benchmarku):** (1) room-set scaling 2-kond. (4. sypialnia zamiast pompowania masteru —
> naprawia MAPE obu wzorców i Trację 3≠4 syp) + day-zone-overflow cap parteru (salon 40-61 > 35); (2) skala
> ekstrakcji wzorców (44 PDF + dataset_raw ~120 dok.); (3) micro-35 parterowiec (A01_35 FAIL na bramce 45 m²);
> (4) L-footprinty. Pamięć: [[project_layout_optimization_archon]].
>
> **Session 29 cz.2 (2026-06-11) — ROOM-SET SCALING 2-kond. (kolejność wg benchmarku).** Dane z korpusu:
> A01_70 poddasze 54 m² netto = **4 SYPIALNIE** + łazienka; A01_120 = 3 syp + **2 ŁAZIENKI**; A01_120 parter ma
> **GABINET + GARAŻ** (absorbery nadmiaru — salon realnie 42.9 ≈ cap 45); ŻADEN wzorcowy poddasze nie ma garderoby.
> Wdrożone: szablony +`sypialnia_4`/+`lazienka_2` (piętro), +`gabinet`/+`garaz` (parter, cap garaż 22);
> **selektory wg powierzchni** (`pietro_room_ids` po POWIERZCHNI EFEKTYWNEJ = pełna − 0.5·stref niskich ≈ norma
> PL — dla A01_70 daje 55 vs 53.8 netto z tabeli ✓; `parter_room_ids` gross: gabinet ≥115 — korpusowe 97 NETTO;
> garaż ≥120; garderoba poddasza ≥95 eff). **Program**: water-fill 2a NOCNE→DO CAPÓW przed proporcjonalnym 2b
> (2b przywrócone per reguła Dawida: dzień trzyma łączny cap póki nocne istnieją). **Solver**: pasma programu
> (dom): wszystkie pokoje ≤1.35·target (anty-pompowanie), SYPIALNIE dodatkowo ≥0.7·target (balans-od-dołu;
> max/min-equality nad polami = UNKNOWN — za drogie); nagroda ścienna kotłowni/garderoby 0.03→0.06 (pasma
> zmieniły skalę odchyleń — kotłownia deterministycznie lądowała w środku). **EFEKT BENCHMARK: A01_70
> 53.7 → 60.7** (poddasze F1 0.77→0.86, MAPE 28.5→14.0%). **KRAWĘDŹ SOLVERA (udokumentowana, 3 testy
> skip-as-spec):** parter ≥~120 m² gross z garażem+gabinetem (10 pokoi) = UNKNOWN @120 s niezależnie od
> formulacji → **A01_120 i Tracja-gross czekają na „solver perf II" (solution hints z targetów) — TOP kolejki**.
> Testy: `test_house_roomset_scaling.py` (6+3 skip), house_program units ✓, service/matrix/layout ✓ (flaki
> kontencji potwierdzane w izolacji). Ekstrakcja pełnego korpusu (36 PDF) padła na limicie sesji subagentów
> (resety 21:10/2:00) — `wf_f8cab93b` do wznowienia (resumeFromRunId; ~6 plików scache'owanych).
>
> **Previously — Session 28 (2026-06-11)** — branch `feat/sfh-open-plan-day-zone`: **solver perf NAPRAWIONY (~15×)
> + benchmark do wzorców Dawida + tri-scenariusze**. **PERF (ablacja → fix, `notebooks/parter_perf_probe.py`):**
> parter był feasible ale wolny (13×10: pierwsze rozwiązanie 79 s, OPTIMAL 285 s; Tracja-6 479 s; żaden pojedynczy
> pin nie był winowajcą — bez L-holu wręcz GORZEJ). Fix w `core/cpsat_solver.py` (semantyka nietknięta):
> **(1) `use_energetic_reasoning/timetabling/area_energetic_in_no_overlap_2d=True`** (główna dźwignia),
> (2) merge zdublowanych zmiennych pola (było 2× produkt w·h per pokój), (3) kwadranty budowane TYLKO przy
> `blocked_arrangements` (ekstrakcja post-hoc w Pythonie). **Wynik: 13×10 first-sol 6.3 s / OPTIMAL 53 s;
> Tracja-6 OPTIMAL 32 s, w limicie suite (45 s) = 14.5 s.** Regresja: batch domowy+e2e+contract 103/105
> (2 = flaki kontencji, w izolacji ✓), solver+narrow-M2 zielone. **Suite: Tracja-6 PO RAZ PIERWSZY SIĘ
> GENERUJE** — pozostałe flagi = znane kolejkowane GAPy (salon 61>cap35 day-zone-overflow; 3≠4 sypialnie
> room-set-scaling); L-140 nadal parter=UNKNOWN (L-ścieżka niepodparta: rdzeń notch-unaware).
> **NOWE NARZĘDZIA (prośby Dawida): (a) `notebooks/ac_tri_scenarios.py`** — każdy ZAZNACZONY obrys z AC
> generowany ×3 (mieszkanie / parterowiec / dom piętrowy), rendery `rzuty/tri/` + tabela statusów; tryb
> `--offline` smoke OK (B_88: wszystkie 3 scenariusze; fail-e z czytelnymi powodami).
> **(b) benchmark podobieństwa do WZORCÓW:** ekstrakcja ground-truth z PDF (vision workflow `wf_4a2dad06`,
> cross-checked per plik) → `notebooks/reference_plans.json` (pilot: kanoniczna seria A.01.1-5 z `rzuty/domy`;
> powierzchnie NETTO z tabel rzutów) → harness `notebooks/reference_benchmark.py` (zestaw pokoi F1 50% +
> UDZIAŁY powierzchni MAPE 30% (netto vs 100%-pokrycie → udziały, nie m²!) + sąsiedztwa Jaccard 20%;
> rendery `rzuty/benchmark/`). **PIERWSZE LICZBY: A01_120 = 56.7/100** (parter F1 0.57 / MAPE 24.6% / adj 0.21;
> poddasze F1 0.77 / 19.9% / 0.44); A01_35 = FAIL (bramka micro-45), **A01_70 = FAIL (pas 41 < program piętra
> — a realne poddasze tego domu ma 0.78 footprintu vs nasz sztywny ATTIC_BAND_FACTOR=0.60; realny zakres
> w korpusie 0.43-0.78!)** → twardy dowód na elastyczne szablony / konfigurowalny współczynnik pasa.
> **NEXT:** (1) skala ekstrakcji: pozostałe 44 PDF `rzuty/domy` + `~/Desktop/claude code/schematics/dataset_raw`
> (konopnickiej 25 / natura_life 50 / podręcznik 39 / domy jednorodzinne 6 projektów); (2) kolejność napraw WG
> BENCHMARKU (kandydaci: day-zone-overflow cap, room-set scaling 2-kond. + elastyczny pas, L-footprinty);
> (3) tri-scenariusze na realnych obrysach Dawida z AC (czeka na sesję z AC+Tapir). Pamięć:
> [[project_layout_optimization_archon]].
>
> **Previously — Session 27 (2026-06-10)** — branch `feat/sfh-open-plan-day-zone`: **domy 2-kond. „poddasze-shrink"
> (KNEE-WALL) WDROŻONE**. Piętro NIE solvuje się już na pełnym obrysie — dostaje **pas użytkowy przy kalenicy**:
> pełna długość wzdłuż dłuższej osi × `ATTIC_BAND_FACTOR=0.60` krótszej (zakres decyzji Dawida 0.55-0.65),
> wycentrowany, MUSI zawierać rdzeń schodów, przycięty do obrysu (`core/house_layout._attic_band_polygon`).
> **Dwie UDOWODNIONE (presolve) sprzeczności znalezione i rozwiązane po drodze:** (1) szczelina pas↔rdzeń < szer.
> pokoju jest niepokrywalna przy F1 (==) → krawędź pasa DOSNAPOWANA do krawędzi rdzenia (`ATTIC_CORE_SNAP=1.5`);
> (2) U-rdzeń 2.4 m zjada połowę pasa → **dom 2-kond. ma teraz ZAWSZE bieg prosty wzdłuż kalenicy**
> (`_stair_core_dims(force_straight)`) i **podest L-capable** (`l_capable_ids={"hub"}` — ta sama mechanika co
> „mini-korytarz" S26; U-w-pasie wolny/INFEASIBLE nawet przy głębokości 6.6, sondy w sesji). Rdzeń re-bazowany do
> bboxa pasa = ta sama pozycja świata → piony schodów z konstrukcji. Pre-check: pas ≥ (Σ minów piętra bez schodów
> + pole pinu)·1.12 → czytelny komunikat (min. footprint 2-kond. ≈ **76+ m², macierz testowa 80-108 m²**).
> Pas dostaje jawne `wall_types=FACADE` (pseudo-entry nie gasi okien ścianki kolankowej). Konsumenci: renderer
> (panel PODDASZE = pas + szary „duch" parteru, wspólne osie), `house_preview` (meble piętra na pasie, raport
> per kondygnacja), **`plan_contract.house_to_contract` (poddasze bbox/okna z pasa — bug złapany w tej sesji)**.
> `TwoStoreyLayout.attic_boundary` (None = parterowiec/stare ścieżki). RED-first: `tests/test_house_attic_shrink.py`
> (15: geometria pasa czysta + integracja CP-SAT + kontrakt + render); zaktualizowane: staircase_b (macierz
> 10×8/11×8/12×8/8×11 × 4 strony; 10×8 W/E świadomie poza — pas 48 m² + rdzeń środkowo-osiowy = granica modelu),
> open_plan_dayzone, lroom_phase2b, house_program (salon ≤ ŁĄCZNY cap 45 — odłożony day-zone-overflow GAP),
> przedsionek_entry, service_placement (garderoba poddasza vs krawędzie PASA; parterowa garderoba martwa od S25
> priorytetów — udokumentowane), stary test_house_staircase. Batch 73/81 + świeży re-run flaków 6/8 → realne fail-e
> = tylko `parter=UNKNOWN` na 96-108 m² (graniczne limity; podbite 60/120 s z komentarzem); smoke mieszkań
> (test_cpsat_solver + test_narrow_apartment_m2) zielony. **Render 11×8: master 15.5 m² (cap 16.5; BYŁO 61.8!),
> syp 9.6/8.8, łazienka 5.0, podest 6.3 (12%), schody w pionie** — `rzuty/renders_mvp/1_dwukondygnacyjny.png`.
> **ZNANE/NEXT:** (1) **parter ≥~130 m² = UNKNOWN nawet @120 s** (Tracja-6 157 m²/L-140 z suite nadal czerwone na
> PARTERZE; przed zmianą „działały" 90 s ale ze śmieciowym poddaszem; piętro = OPTIMAL w sekundy) → **NEXT = solver
> perf (kolejka S26)**; (2) potem area-scaling sypialni + cap day-zone-overflow parteru (render: salon 40.3/kuchnia
> 19.2 na 88 m²); (3) L-footprinty domów dalej niepodparte (rdzeń notch-unaware — pre-existing S18; band∩L
> zaimplementowane defensywnie: płat z rdzeniem); (4) kosmetyka z review: strzałka schodów przy L-podeście, kolizje
> etykiet usługowych, stare notebooki-sondy z obrysami < bramki pasa. Adversarial-review workflow uciął się na
> limicie sesji w fazie verify — 20 surowych findingów strijażowane ręcznie (realne naprawione: MultiPolygon-
> płat-z-rdzeniem, wall_types pasa, kontrakt poddasza, testy nie-origin + snap gap_hi). Pamięć:
> [[project_layout_optimization_archon]] [[project_session17_gap_fix]].
>
> **Previously — Session 26 (2026-06-10)** — branch `feat/sfh-open-plan-day-zone`: **apt-44 M2 lider rynku NAPRAWIONY
> + diagnoza domów 2-kond.** **DONE — wąskie mieszkanie 2-pok (M2, ~40% sprzedaży) renderowało się jako kawalerka.**
> Root cause (eksperymentalny, nie zgadnięty): prostokątny hol na wąskim obrysie (krótki bok <6 m) MUSI sięgnąć od salonu
> (góra) do łazienki/sypialni (dół) → minimum feasible holu = **24% (>F4 15%)**, a przy wejściu w CENTRUM krótkiej ściany
> wręcz INFEASIBLE (binary-search potwierdził floor 24%; pin hub-at-entry zmusza hub do straddle'owania środka). Relaksacja
> capa kompaktowości = NO-OP (caps niewiążące). **Fix (decyzja Dawida = "mini-korytarz"): hol L-kształtny dla wąskich
> mieszkań — auto `l_capable_ids={hub}` gdy `program_config is None` i `min(BW,BH)≤600cm`** (`core/cpsat_solver.py`
> `narrow_apt`; reużycie maszynerii Approach 2b). Cienki L owija łazienkę, dotyka wszystkich pokoi mniejszym polem →
> **14%, feasible przy KAŻDej pozycji drzwi** (też centrum). Auto-star uczyniony L-aware. Harness `notebooks/layout_suite.py`
> = wejście off-center dla wąskich (realny lokal z korytarza). **Commit `a09e637`** (branch 46 ahead, NIE pushowany).
> Weryfikacja: nowy `test_narrow_apartment_m2` 7/7 (RED-first); regresja mieszkań 41 passed+1 xpass; meble/drzwi/okna 98;
> `lroom_phase2b` 19; suite apartamenty **5/5 OK** (apt-44 = pełny 2-pok 1 syp). Domy bramkowane out → nietknięte.
> **NEXT (decyzja podjęta, NIE rozpoczęte) — domy 2-kond. „poddasze-shrink".** Diagnoza: `generate_house` (num_storeys==2,
> `core/house_layout.py:220`) solvuje OBIE kondygnacje na PEŁNYM obrysie (123 m²) ze STAŁYMI szablonami `house_parter`/
> `house_pietro` → 3 objawy z jednego źródła (F1 pokrycie upycha nadmiar): poddasze-bloat (master 61.8 m² na Tracja-6,
> podest 23.4 na L-140), parter day-zone-bloat (salon 61/kuchnia 25 >cap 35/13), 3≠4 syp, solve 90 s (>45 s suite→UNKNOWN
> „timeout"). **Dominujący root cause: poddasze użytkowe jest MNIEJSZE (skos dachu — Tracja-6 realnie 53/123 m²), kod robi
> je pełnowymiarowym.** Dawid wybrał: **model = KNEE-WALL** (poddasze użytkowe = pas przy kalenicy: pełna długość wzdłuż
> kalenicy × ~0.55-0.65 krótszej osi, wycentrowany; MUSI zawierać rdzeń schodów `reserved_core`) + **zakres tej sesji =
> TYLKO shrink poddasza** (RED-first; reszta — area-scaling sypialni jak `single_storey_room_ids` z `689c132` + cap overflow
> strefy dziennej parteru — osobno potem). Punkty wdrożenia: wyprowadź mniejszy attic-boundary, solvuj `pietro` na nim;
> renderer (`render_two_storey`/`viz/house_preview`) musi rysować 2 kondygnacje o RÓŻNYCH footprintach (attic = pas
> wycentrowany); `reserved_core` musi pozostać ważny w attic. Pamięć: [[project_layout_optimization_archon]]
> [[project_session17_gap_fix]].
>
> **Previously — Session 25 (2026-06-09)** — branch `feat/sfh-open-plan-day-zone`: **meble→AC pivot na pojedyncze
> meble + jakość układu mieszkań**). FURNITURE: realny rozmiar przez `SetGDLParametersOfElements(A,B)` — Tapir
> `dimensions`=MNOŻNIK domyślnego A/B (NIE metry, źródłowo potwierdzone w `ElementCreationCommands.cpp`); kuchnia
> rozbita na moduły 0.6 m (`Szafka podstawowa`+`Lodówka`, wyposażenie przez bSink/bCooktop/bCounter — wybór Dawida);
> ekstraktor odwzorowuje box solvera 1:1 (usunięto `_orient_to_box`/`_anchor` — to one rozjeżdżały lokalizację/skalę).
> **TWARDA BARIERA: ten build Tapira NIE obraca obiektów** (`AddOnMain.cpp`: brak RotateElements/ModifyObjects, kąt
> w CreateObjects=brak) → duże meble (sofa/łóżko) deformują się na pionowych ścianach. **Decyzja Dawida: meble-AC
> zamrożone, rotacja przez dokładkę C++ do Tapira (PR-upstream), robić ją gdy układ dopięty.** LAYOUT MIESZKAŃ
> (algorytm-first): `APARTMENT_DAY_ZONE_CAP=45` (cap salonu, nadmiar→sypialnie), `suggest_mtype(area)` (M1-M5 wg
> powierzchni: 124m²→M4=3syp), water-fill sypialni (równe). 124m² render: salon 63→32, 2→3 sypialnie. Domy OK dla
> REALNYCH obrysów (74m² zbalansowany; 124m²-dom bloat = obrys za duży na dom, nie bug). **OPTYMALIZACJA POD
> NAJCZĘSTSZE PL UKŁADY (dyrektywa Dawida, archon.pl):** research (workflow) → suite `notebooks/common_pl_suite.json`
> (10 obrysów + wzorce pokoi) + harness `notebooks/layout_suite.py` (generuje→renderuje→ocenia vs wzorce →
> `rzuty/suite/`). DONE: M-typ mieszkań POTWIERDZONY z rynkiem (keep); **parterowiec 4 syp + 2 łaz wg powierzchni**
> (85-130m²→4 syp; szablon +sypialnia_4/lazienka_2, `_SINGLE_OPTIONAL` priorytet sypialni, `_SINGLE_MAX_ROOMS=12`)
> → 106m² Bukowej-5 = zbalansowany 4-syp parterowiec (`689c132`). KOLEJKA: (1) mieszkanie 44m² (2-pok=market leader
> ~40%) → M2 infeasible na wąskim obrysie (priorytet); (2) domy 2-kond. — 123m² timeout, 140m² tylko 3 syp +
> salon-bloat (poddasze potrzebuje skalowania sypialni jak parter); (3) wydajność solvera (12 pokoi ~60s). Testy:
> 26+36+54 + test_house_single_storey 24 zielone. Pamięć: [[project_ac_export_apartment_confirmed]] [[project_layout_optimization_archon]].
>
> **Previously — Session 24 (2026-06-08)** — branch `feat/sfh-open-plan-day-zone`: **meble→AC bug-fix po ocenie Dawida;
> dane poprawne, ale wizualnie NADAL ŹLE — nieparametryczne części biblioteczne**). Dawid ocenił meble M3 w AC →
> 2 bugi: meble pływają + brak kuchni. **Diagnoza (grounded 15-agent workflow, adwersaryjnie zweryfikowana) +
> 4 fixy RED-first** w `core/furniture.py` + `core/furniture_extractor.py`: **(H2 pływanie)** `_orient_to_box` —
> eksport do AC (`extract_furniture`) re-derywował geometrię NIEZALEŻNIE od renderera matplotlib (renderer rysuje
> surowy box solvera, już dociśnięty → OK; AC podstawiał stałe wymiary biblioteczne w stałej osi → mebel przy ścianie
> W/E przekręcony, wybrzusza się). Rotacja niedostępna → zamiana dim_x↔dim_y. **(H1 kuchnia)** mieszkania M1-M5 NIE
> mają pokoju `kuchnia` — otwarty `salon_aneks` → `key="salon"` → `_furnish_living`, NIGDY `_furnish_kitchen` (jedyny
> producent `kitchen_counter`) → nowy `_furnish_kitchenette` (blat na ścianie aneksu; strażnik `not has_kuchnia` →
> domy bez zmian). **(blat)** `LINEAR_TYPES={kitchen_counter}` → footprint boxa (cienki), nie sztywny blok 1.92×2.52.
> **(stolik)** `CENTERED_TYPES={coffee_table}` → centrowany na boxie, nie dociskany do ściany. **Kotwica
> ROZSTRZYGNIĘTA** (`notebooks/ac_anchor_probe.py`): CreateObjects `coordinates` = origin obiektu 1:1 = LEWY-DOLNY
> RÓG (readback z czystego AC: 46 mebli → 0 floatujących); angle=0; brakująca część znika po cichu (H3);
> GetBoundingBoxes2D/3D niedostępne. Nowe runnery: `furniture_export_check.py` (offline dual-panel renderer-vs-AC),
> `ac_export_multi.py` (multi-obrys: grupuje zaznaczone ściany w komponenty spójności = osobne mieszkania),
> `ac_outlines_render.py` (read-only render realnych obrysów), `ac_clean_and_export.py` (kasuje wygenerowane śmieci
> zachowując zaznaczone ściany+drzwi → 1 czysty eksport). **Weryfikacja:** 85 testów zielonych (+5 nowych); pełna
> regresja 449 passed (4 znane flaki single-storey CP-SAT, potwierdzone w izolacji); offline render 4 realnych obrysów
> Dawida (prostokąt+L+trapez) = 0 AXIS/OUT/float, kuchnia wszędzie; live: dokument AC wyczyszczony (1263 śmieci z ~100
> runów) + 4/4 mieszkania wyeksportowane na czysto. **⚠️ NADAL ŹLE WIZUALNIE (Dawid wieczorem „nadal źle"):** mimo
> poprawnych danych (origin+dimensions w obrysie, 0 floating), **części biblioteczne AC rysują STAŁE 2D symbole
> ignorujące nasze `dimensions`** — zwłaszcza `Zestaw mebli kuchennych` rysuje wielki rząd AGD WYCHODZĄCY POZA ściany
> (najgorzej trapez + środkowy obrys). To NIE bug współrzędnych — to NIEodpowiednie (nieparametryczne) części.
> **NEXT (jutro, KONTYNUACJA): wybrać Z DAWIDEM PARAMETRYCZNE części respektujące `dimensions` (zwł. cienki blat
> ~0.6 m), ALBO zmienić reprezentację kuchni na Morph/2D fill/Slab — powrót do odłożonej decyzji „library objects vs
> Morph/2D".** LEKCJA: dokument AC kumuluje strefy/obiekty z każdego eksportu (brak auto-cleanup) → zawsze czyść przed
> oceną. **Kod NIE commitnięty** (working tree: `core/furniture.py`, `core/furniture_extractor.py`, `tests/test_furniture*.py`,
> + 4 nowe notebooks; gałąź lokalna). Reszta backlogu: rotacja 0° vs C++, domy→AC, 2 szafki nocne 0.15 m², GAP/realizm,
> phase 2c, micro-35, un-xfail M3, GUI 2-tab. Pamięć: [[project_ac_export_apartment_confirmed]].
>
> **Previously — Session 23 (2026-06-08)** — branch `feat/sfh-open-plan-day-zone`: **mieszkanie→AC potwierdzone
> LIVE + meble→AC jako obiekty biblioteczne (opcja A)**. Cel: zde-riskować rurę mieszkanie→AC i dowieźć meble do AC.
> **(1) De-risk rury — root cause + fix:** stary `notebooks/ac_export_check.py` wstawiał syntetyk 10×8 w origin świata
> (offset 0, brak ścian obwodowych) → strefy w pustce + komunikat „obrys nie zamknięty" + `windows=0` — to był artefakt
> HARNESSU, NIE bug produktu. Przepisany na REALNY flow (`read_boundary_from_archicad` → shift do origin → `generate_variants`
> → `export_plan_to_archicad(offset=róg-świata)`, jak GUI `_apply_imported_boundary`). Live na AC29: zones 5 / walls 7 /
> doors 4 / labels 5 / **windows 3** w zaznaczonym obrysie. Dawid: „jestem zadowolony". **(2) meble→AC = opcja A (decyzja
> Dawida): PRAWDZIWE obiekty biblioteczne AC.** Sonda `IsAddOnCommandAvailable`: `CreateObjects` ISTNIEJE w jego buildzie →
> A to CZYSTY PYTHON, zero C++ (analiza-brief myliła się — widziała tylko wrapper). Schemat poznany empirycznie:
> `{objectsData:[{libraryPartName, coordinates{x,y,z}, dimensions{x,y}}]}`, `additionalProperties:false`, **`angle` ODRZUCANE**.
> Mapowanie z obiektów wybranych przez Dawida (AC29 `BuiltInLibraryParts.libpack`: łóżka/sofa/garderoba/szafka RTV/stoliki/
> sanitariaty), REALNE wymiary z jego wyboru + centrowanie, reguła master→`Łóżko podwójne 01`/secondary→`Łóżko 01`.
> **`core/furniture_extractor.py`** (RED-first, 13 testów) + `tapir.create_objects()` + blok „6. Meble" w `plan_writer`
> (flaga `include_furniture`, `"furniture"` w return). Commit `a501c1e`. **(3) Iteracje wizualne (B8):** v1 rozciągało meble
> (forsowałem `dimensions`=box) → fix: realne wymiary; v2 meble pływały / WC za ścianą → fix: **dociśnięcie do ściany +
> clamp do pokoju** (`_anchor`), commit `ffca8d3`. Render `M3-B5C1` wstawiony — **ocena lokalizacji Dawida PENDING** (sesja
> zakończona, kontynuacja potem). **⚠️ TWARDY LIMIT: ten build Tapira NIE obraca obiektów** (brak `angle` w CreateObjects,
> brak `RotateElements`/`TransformElements`, `MoveElements`=tylko translacja) → meble pod 0° (część zwrócona domyślnie).
> **DECYZJA odłożona (Dawid): 0°-MVP vs rozszerzenie custom-buildu Tapira o rotację w C++** — ocenić po obejrzeniu M3-B5C1.
> Stan AC-export: **mieszkania** = strefy+ścianki+drzwi+okna+etykiety+**meble** ✅ (live); **domy** nadal wyłączone.
> 44 testy regresji zielone, zero regresji. Throwaway-sondy `_probe_*` usunięte. **NEXT:** (a) Dawid ocenia lokalizację
> `M3-B5C1`; (b) adwersaryjny review meble→AC; (c) decyzja rotacja (0° vs C++); (d) domy→AC (TwoStoreyLayout przez contract);
> reszta backlog (realizm układu / GAP salon, phase 2c, micro-35, un-xfail M3, GUI 2-tab). Pamięć: [[project_ac_export_apartment_confirmed]].
>
> **Previously — Session 22 (2026-06-07):** branch `feat/sfh-open-plan-day-zone`: **MVP render: meble do ścian +
> drzwi + okna**). Dawid: cel = jak najszybciej wypuścić MVP generujący rzuty MIESZKAŃ i DOMÓW z meblami, drzwiami
> i oknami; lokalizacje mebli były najsłabsze. Diagnoza 5-agentowa (grounded) → plan A+B, TDD RED-first, NIE
> commitnięte. **Zrobione:** (A1) świadomość ścian wspólnych — `core/furniture._room_shared_walls`; sofa/szafa
> preferują ściany nie-wspólne (sofa już nie pływa na otwartym styku salon↔kuchnia; szafa unika ściany działowej
> między sypialniami), fallbacki zachowują feasibility (szafa próbuje nie-wspólne POTEM wspólne — nie gubi się).
> (A3) `viz/plan_renderer._label_anchor` — etykieta pokoju odsunięta od mebli, odporna na L/U-pokoje
> (MultiPolygon→największy geom, representative_point gdy centroid w wycięciu). (B1) **drzwi rysowane** —
> `core/door_extractor.infer_door_openings`+`_shared_edge_door` (REALNA krawędź boundary∩boundary, nie bbox →
> poprawne dla L-pokoi; pomija schody i parę komunikacja↔komunikacja; strefa dzienna↔hol = `is_opening`);
> `viz._draw_doors/_draw_door_symbol` (otwór+skrzydło+łuk swingu, otwarcie bez skrzydła). (B2) **okna rysowane** —
> `core/window_extractor.extract_facade_windows`+`FacadeWindow` (geometria z fasady, reużywa `_room_facade_edges`+
> `_wt_compliant_dimensions`; margines 2·EDGE_MARGIN od narożnika); `viz._draw_windows` (niebieski odcinek).
> (B3) **okna w JSON contract** (`plan_contract` → `windows[]`). Render `render_floor_plan` rozszerzony o `furniture=`
> + rysuje drzwi/okna (mieszkania), `render_two_storey` też (domy); legenda przeniesiona POD rzut, info-box pod spód
> (nie zasłaniają etykiet/mebli). A2 (stół jadalny pływa) = fałszywy alarm (już omija meble via `zones`).
> **Weryfikacja:** TDD RED-first każdy element; adwersaryjny 25-agentowy review → 6 realnych błędów ZNALEZIONYCH I
> NAPRAWIONYCH (L-pokój bbox-drzwi, komunikacja↔komunikacja drzwi, dzienna↔hol skrzydło zamiast otwarcia, margines
> okna, regresja szafy w ciasnej sypialni, `_label_anchor` poza L/U-pokojem); 77 testów dotkniętych modułów zielone;
> 3 rzuty wizualne OK (`rzuty/renders_mvp/`: dom 2-kond., parterowiec, mieszkanie M3 — wyglądają jak realne rzuty).
> **MVP COMMITTED** `f71d4c3` (12 plików, +648/−25; `rzuty/` nadal untracked; branch NIE pushowany). Pełny suite:
> 429 passed, 3 „failed" = ZNANE flaki CP-SAT pod kontencją (`day_zone_contiguous` PASS w izolacji; 11×11 single-storey
> ×2 = timeout, `ok=True` przy 25s z wolnym CPU; `cpsat_solver`/`house_layout` NIE w diffie → moje zmiany nie mogą
> wpłynąć na `lay.ok`). Zero regresji.
> **DECYZJA kierunkowa (Dawid 2026-06-07): cel = NATYWNY dodatek do ArchiCAD.** Lokalny PyQt GUI = narzędzie dev/demo,
> NIE produkt (czysty Python nie może być natywny). Stan eksportu do AC (`bridge/plan_writer.py` przez Tapir, porty
> 19723-30): **mieszkania** dostają strefy+ścianki+drzwi+okna+etykiety ✅; **brak: meble** (nieeksportowane) i **domy**
> (wyłączone). **NEXT (kolejność uzgodniona):** (1) **[Dawid, wymaga AC+Tapir] odpalić `notebooks/ac_export_check.py`**
> (`! PYTHONPATH=. venv/bin/python notebooks/ac_export_check.py`) — zderiskować: czy pipe mieszkanie→AC żyje na jego
> maszynie. (2) **meble→AC** — serializacja `FurnishResult`→payload Tapir przez JSON contract (payload testowalny
> unit-owo; reprezentacja mebli w AC = obiekty biblioteczne vs Morph/2D — do decyzji z Dawidem). (3) **domy→AC**
> (TwoStoreyLayout przez contract). (4) skorupa C++ = osobny milestone produktyzacji. Świadomie NIE budujemy nic w
> bridge zanim (1) nie potwierdzi działania rury. Reszta (poza ścieżką AC): realizm punch-list (zlew, łazienka-linear,
> Neufert), GAP/overflow-rooms (salon nadyma się na ≥70m²/kondygnację), phase 2c, micro-35, un-xfail M3.
>
> **Poprzednio — Session 21 (2026-06-06):** branch `feat/sfh-open-plan-day-zone`: **phase-4 furniture DONE**).
> Executed the 9-task window-aware furniture plan RED-first (commits `bc0a18a`..`bb865df`): `FurnishResult` +
> `furnish_rooms(rooms, boundary=None)` (back-compat `place_furniture` wrapper); `_room_window_walls`
> (facade-edge→window, lazy-imports `_detect_facade_sides`, notch-gated); `_place_on_wall`; semantic placers
> `_furnish_bedroom` (bed→longest window-less wall + nightstands + wardrobe + 0.6 m front clearance),
> `_furnish_kitchen` (counter on window wall), `_furnish_living` (sofa internal / TV opposite / coffee),
> `_furnish_bathroom` (fixtures + key-piece warnings), `_place_dining` (table at salon↔kuchnia shared edge —
> junction-biased `_place_on_wall`, plan's `_place_fixed` would've failed the test). Tests strengthened to be
> genuinely discriminating (the plan's bedroom/kitchen/living/bathroom tests passed pre-impl on the greedy
> placer; rewrote with window-on-entry-edge geometry etc.). 17 furniture tests green; control renders OK
> (beds off windows, counter under window, sofa/TV opposite, dining at junction, hol empty).
> **Then an adversarial review (31-agent workflow) found 24 confirmed issues; fixed the critical+correctness
> set (`32c2490`):** (#18 CRITICAL) `viz/house_preview.furnish_layout` never passed `layout.boundary` → phase-4
> window-awareness was BYPASSED in the real product render — now forwarded (+regression test, +2 notebooks);
> (#2) kitchen counter was window-walls-only → spurious "brak blatu" when window blocked, now window-first
> across all walls; (#5/#14) `_place_dining` matched salon by exact id but kuchnia by prefix → `salon_1`
> dropped the table, now both prefix. **Realism punch-list → `docs/FURNITURE_REVIEW_PUNCHLIST.md`** — Dawid
> chose realism next; top 3 DONE RED-first: center-bed→2 nightstands (`e2a4ae2`), coffee between sofa/TV
> (`c25ac6c`), bathroom washbasin-before-bathtub so ≤5 m² keeps the washbasin (`1400c7d`); 21 furniture tests
> green, re-render OK. **ALSO safe-robustness batch DONE (`5e2bdfb`):** L/U-room cavity-as-keep-clear (#11),
> `_shared_wall` overlap-extent ≥0.9 m (#13), ortools-import guard in `_room_window_walls` (#15), wardrobe
> shrink 2.0→1.6→1.2 (#23) — 25 furniture tests + integration green. **TV: RESOLVED (Dawid) — stays opposite
> the sofa even on a window** (curtains solve glare; #19 won't-change). STILL DEFERRED: counter/bathroom Neufert
> clearances (tuning-risky — over-tightens small rooms), sink piece (`zlew` is docstring-only), bathroom-linear-
> one-wall, notch info-warning. See `docs/FURNITURE_REVIEW_PUNCHLIST.md`.
> **ALSO Session 21 — ArchiCAD distribution decision** (web-grounded 8-agent research, all claims verified;
> memory `project_archicad_bundle_distribution`): native copy-folder add-on = C++ only (`.apx`/`.bundle`,
> recompile per AC version × OS, mac notarize); pure Python can't be native; official AC Python API can't
> create geometry (only Tapir/C++ can); repo already on the Tapir-sidecar MVP path (`bridge/`). **Dawid chose:
> continue the algorithm + ONE cheap bundle-prep step (lock a JSON contract `core → {rooms,walls,doors,
> furniture,warnings}`); the native C++ shell is a separate "produktyzacja" milestone.** Key find: wall/door/
> window/label derivation already lives in `core/*_extractor.py` (with `*_to_tapir_payload`); the contract
> just needs furniture serialization + a pure aggregator (FloorPlan vs TwoStoreyLayout adapter is the one
> open question). Regression note: a batch of `test_house_single_storey`/`test_open_plan_dayzone` failures is
> pre-existing CP-SAT non-determinism (11×11 @25 s times out; CPU contention), NOT furniture — see memory.
> **JSON contract bundle-prep — DONE (`23483ab`):** `core/plan_contract.py` `plan_to_contract(...)` +
> `house_to_contract(layout)` → AC-agnostic `{meta, rooms, walls, doors, furniture, warnings}` (fully
> JSON-serializable), reusing `extract_internal_walls` + `extract_doors` (made `wall_to_guid` OPTIONAL =
> GUID-free contract mode; AC export unchanged, 22 door/wall tests green) + `FurnishResult`. RED-first, 4
> tests incl. real-house integration (12 rooms/26 walls/11 doors/21 furniture, ~10 KB JSON). Rooms/walls/
> doors reference rooms by NAME (rooms[] carries id+name). NEXT (bundle): package `core/` as a wheel + pin
> Python; wire GUI/bridge to call the contract. NEXT (algo): phase 2c (scaled 2-storey room-set), micro-35
> single-storey, un-xfail M3, GUI 2-tab; furniture realism punch-list leftovers (clearances, sink, bathroom-
> linear) in `docs/FURNITURE_REVIEW_PUNCHLIST.md`.
>
> **Previous (Session 20, 2026-06-03):** branch `feat/sfh-open-plan-day-zone`: **phase 2b DONE** —
> native L-capable hol committed (`e0bcb23`). Recovered the interrupted phase-2b WIP, retrofitted the
> RED test net the plan demanded (`tests/test_house_lroom_phase2b.py`, 19/19), confirmed it GREEN, then
> committed. L-hol wraps WC (external wall) + wiatrołap (entry wall) with a minimal arm → both Dawid bugs
> fixed WITHOUT corridor bloat (9×7 rectangular hol = 18% > F4; L = 12%). M1–M5 proven model-no-op
> (deterministic proto compare). Probe: feasible + both fixes + ≤F4 + cov== across 24 footprint×entry
> combos. Deferred per Dawid (option A): "L only when it minimizes corridor" — on 8×8 the hol goes L (7.0)
> where a rectangle (6.5) would suffice; tune the objective in the furniture phase.
> **ALSO Session 20 (committed `17eee67`..`13b04a4`, 5-task plan):** (1) **przedsionek-entry fix** —
> `entry_room_id="wiatrolap"` so the front door is INSIDE the wiatrołap and the hol is behind it (Dawid's
> correction; applies to 1- and 2-storey); removed the redundant phase-2b wiatrołap-wall block. (2)
> **single-storey houses (parterowce)** — new `house_single_storey` template (no stairs), area-driven
> room-set selector (`single_storey_room_ids`, bedrooms scale greedy + przedsionek by ~50 m² threshold D2),
> `generate_house(num_storeys=1)` branch, `suggest_storeys`, `MIN_SINGLE_STOREY_AREA=45` (micro-35 deferred,
> needs reduced mins — spec D5). (3) **cm-snap geometry fix** in `solve_cpsat` extraction (round coords to
> cm) — float-add `rx+rw` made adjacent rooms measure 0 shared edge on the L-hub; lossless, also fixes the
> M3 hub-adjacency xfail (now xpasses). F4 kept SOFT for single-storey (option A: hol touches ~9 rooms on
> one star → usually ~10-12%, rarely ~17%; test asserts ≤20% anti-spine, hardening deferred to furniture).
> (4) **room-placement preference (`7018ef2`)** — kotłownia + garderoba SOFT-prefer an external wall
> (kotłownia fresh-air, garderoba window; reward `-0.03·B_AREA·at_ext`, house-only); yields on tight
> footprints (Dawid: not obligatory). The hol stays central as a side effect (no explicit centering term).
> `test_house_service_placement` 2/2. The oversized F2 stress footprint reduced 16×13→14×11 (208 m² was
> beyond CP-SAT reliable-solve; 154 m² caps bind the same, 3/3 reliable).
> Tests: `test_house_przedsionek_entry` 4/4, `test_house_single_storey` 24/24, regression green.
> NEXT = **execute the phase-4 furniture plan** (brainstorm+spec+plan DONE this session, committed):
> spec `docs/superpowers/specs/2026-06-03-furniture-realism-design.md` + plan
> `docs/superpowers/plans/2026-06-03-furniture-realism.md` (9 tasks, RED-first, window-aware semantic
> placement — bedroom/day-zone/bathroom + Neufert clearances + best-effort warnings; extends
> `core/furniture.py`, back-compat `boundary=None`). Dawid chose a FRESH session to implement it. Then:
> phase 2c (scaled 2-storey room-set), micro-35 single-storey, un-xfail M3, GUI 2-tab.
> Previous: 2026-06-02 (Session 19 — branch `feat/sfh-open-plan-day-zone`:
> **open-plan day zone**
> (Approach B — salon+kuchnia render as one un-walled L-shaped DZIENNA space, combined cap, garden
> facade) + **minimal corridor** (re-enforced hub-minimal F4, overflow→bedrooms; reverses session-18's
> overflow→hub; podest 15.6→6.3). Grounded in all 49 Dawid PROJ-BUD plans + Neufert. NEXT = **phase 2b
> scoped NATIVE L-rooms** (hol + bedrooms; optional 2nd rect) to fix the WC-landlocked + wiatrołap-not-
> at-door bugs WITHOUT bloating the corridor. See Session 19 block + spec
> `docs/superpowers/specs/2026-06-02-stage4-open-plan-house-furniture-design.md`.) Previous: 2026-06-02
> (Session 18 — staircase Approach B, committed on `feat/sfh-staircase-approach-b`, 346 passed).
>
> Earlier sessions documented in Polish are preserved at the bottom; from
> 2026-05-05 onwards everything is in English so the project can be shared
> with international collaborators.

---

## Session 19 (2026-06-02 — open-plan day zone + minimal corridor; branch `feat/sfh-open-plan-day-zone`)

Drove the house layout from Dawid's real corpus: vision-analyzed **all 49 PROJ-BUD/Łącko reference
plans** (furniture + room-layout/dependencies) + a **Neufert** clearance pass (two design-panel
workflows). Headline finding: the day zone is **open-plan** (kitchen+dining+living = one space, often
**L-shaped**), and the corridor must be **minimal** (F4). Spec:
`docs/superpowers/specs/2026-06-02-stage4-open-plan-house-furniture-design.md` (approved decomposition
1→2→3→4; footprints 35/70/120; L/U/trapezoid footprints deferred).

**Phase 1 — open-plan day zone (Approach B, DONE):**
- `core/house_program.py`: `HouseProgramConfig.day_zone_cap` (pct 0.60 / max 45) — the DZIENNA group
  (salon+kuchnia) shares ONE combined cap (soft anti-bloat ceiling on big footprints), not per-room caps.
- Solver: salon lands on the **garden facade** (= wall opposite the entry) reliably (verified 9/9, no
  forcing needed) → day-zone is contiguous and free to form an **L**.
- `viz/plan_renderer.py`: DZIENNA rooms drawn with NO internal wall (one open space) — `draw_edge` flag +
  the DZIENNA union outline. `tests/test_open_plan_dayzone.py` + `test_day_zone_combined_cap`.

**Phase 2a — minimal corridor (Dawid's feedback, DONE):** re-enforced the hub-minimal (F4) penalty for
houses; F1 overflow now routes to **bedrooms** (poddasze) / **day-zone** (parter), NOT the hub —
**reverses session-18's overflow→hub** (which I'd added to keep bedrooms ≤ cap; wrong trade-off).
Result on 9×7: podest **15.6→6.3**, bedrooms grew to 12–15.5; all corridors ≤F4 across 8×8…10×12.
Bloat test reframed to `test_corridor_minimal_excess_to_bedrooms`; `test_house_program.py` unit tests
updated to the new model (bedrooms absorb; day-zone combined cap; F2 hard). See
[[feedback_corridor_minimal_lshaped_rooms]].

**Bugs Dawid flagged on the render (FIXED in phase 2b — `e0bcb23`):**
1. **WC landlocked** in the center — now touches an external wall (24/24 probe + 4-side test). ✅
2. **Wiatrołap not at the entry door** — now sits on the entry wall (4-side test). ✅ (Refinement deferred to
   the door phase: the entry POINT is in the hub, not the wiatrołap, so "enter THROUGH the wiatrołap" is
   only partially literal.)
Both had been ATTEMPTED and **reverted** on the rectangular model (forcing placement bloated the hol 7→11
>F4 — a genuine conflict with corridor-minimal). Phase 2b L-rooms resolved it cleanly (L hol = 12% on 9×7).

**Phase 2b — scoped NATIVE L-rooms (DONE, `e0bcb23`).** L-capable = **hol parteru** only so far
(`l_capable_ids={"hub"}`); each L-capable room may be a union of 2 rects (L) or stay rectangular.
Mechanism shipped: OPTIONAL 2nd rectangle per L-capable room (`new_optional_interval_var` + presence
literal); NoOverlap2D over primary+optional; coverage sums present areas (`sum(areas)+sum(eff2)==usable`);
adjacency via either rect (`_apply_adjacency`); the 2 rects contiguous (`_touches_bool`) → L; WC forced to
an external wall + wiatrołap to the entry wall (gated `program_config is not None and notch is None`).
Test net retrofitted AFTER the (interrupted) implementation: `tests/test_house_lroom_phase2b.py` 19/19,
mirroring the REAL model contract (no invented aspect≤1.5 / 60% caps — model uses
`max(0.6·B, 0.8·min(BW,BH))`). M1–M5 guarded by a deterministic proto-size no-op test (not flaky
solve-equality). **Deferred (Dawid, option A):** "L only when it minimizes the corridor" — currently the
objective pulls the hol toward 12% so it goes L even on 8×8 where a rectangle is smaller; refine in the
furniture phase. bedrooms-as-L (poddasze, exceptional) not yet wired.

**NEXT:** phase 2c (scaled room-set: 10×12 day-zone 83 / bedrooms 27–38 needs L), phase 3 (single-storey
35), phase 4 (furniture: Neufert+plans, window-aware). Also pending: GUI 2-tab restructure
([[project_gui_product_structure]]); door-phase refinement of wiatrołap-contains-entry.

> ⚠️ Session 19 work on branch `feat/sfh-open-plan-day-zone` (off `feat/sfh-staircase-approach-b`).
> Phase 1+2a committed as a clean checkpoint; phases 2b+ are a fresh start. NOT pushed (Dawid's call).
> Also pending: **GUI 2-tab restructure** ([[project_gui_product_structure.md]]) after the algorithm.

---

## Session 18 (2026-06-02 — staircase Approach B: separate Schody room + compact Hol)

Dawid (2026-06-01) accepted the GAP/cap fix visually but flagged the **staircase** as wrong
(merged "Hol+schody" hub, bad run orientation). B1 REWRITE → **Approach B** (owner-approved
2026-06-02: pinned schody, landing-at-hol orientation, schody adjacent to hol only). Designed via a
design-panel workflow, implemented TDD, then an adversarial-review workflow caught a real W/E-entry
blocker that the first feasibility test had masked — fixed and re-verified.

**Shipped (all house-only; M1-M5 apartment path byte-identical — gated on `program_config is None` /
`stair_idx is None` / `hub_at_entry` default):**
- **Templates** `house_parter.json` + `house_pietro.json`: added a `schody` room (KOMUNIKACJA) AFTER
  `hub` (ordering is load-bearing — first KOMUNIKACJA match stays = hol) + `hub↔schody` adjacency;
  renamed/tightened `hub`→"Hol".
- **`core/cpsat_solver.py`**: new params `stair_room_id` + `hub_at_entry`. When `reserved_core` +
  `stair_room_id` set, the schody room is PINNED to the core (4 equalities x/y/w/h) with the aspect
  rule skipped (straight 4.0×1.1 core would otherwise be INFEASIBLE); core containment reroutes from
  hub→schody (fallback to hub when `stair_idx is None` → M3 test still green); schody target = exact
  pinned area. For houses (`program_config is not None`) the **auto-star "hub touches every room" and
  the hub-12%-excess penalty are SKIPPED** (apartments keep both) so the small hol + pinned mid-plan
  stair are feasible and the hub can act as the elastic overflow sink. **`hub_at_entry=False`** for
  the upper storey: the podest connects to the stairs, NOT an external door — pinning the pietro hol
  to the entry wall made W/E entries on 9×7/10×7 INFEASIBLE (3 windowed bedrooms couldn't fit).
- **`core/house_program.py`**: overflow (F1 leftover) now fills the DAY-ZONE (salon/kuchnia) up to
  caps then dumps the remainder into the HUB (elastic hol/podest); bedrooms/services stay at %-target
  (was: spread over all headroom → leaked into bedrooms → master bloat). Added `schody:5.0` cap; hub
  intentionally uncapped (sink); no-hub fallback sink = largest room (keeps Σ==usable).
- **`core/house_layout.py`**: `STAIR_FRONT_SETBACK=1.8`; `_reserve_core` rewritten — core against the
  side wall opposite the entry, set back 1.8 m from the entry wall (hol takes the entry band);
  `generate_house` passes `stair_room_id="schody"` + `hub_at_entry=True/False` per storey.
- **`viz/plan_renderer.py`**: `stair_run_orientation()` (pure, tested) — run along the core's long
  axis, arrow AWAY from the hol; near-square U-core decided by the hol's dominant side (deterministic,
  not float noise). `_draw_stair_in_room()` draws treads+arrow inside the schody room; falls back to
  the core overlay when no schody room (keeps `test_two_storey_render` green).
- **`core/furniture.py`**: `_infer_door_zones` excludes `schody` as a door-zone source (rooms route to
  the stairs via the hol, not directly).

**Verification:**
- New `tests/test_house_staircase_b.py` (10 tests): separate schody room, pinned-to-core on both
  storeys, schody↔hol adjacency, hol doesn't contain the core, hol compact, **feasibility on
  8×8/9×7/10×7/7×9 × all 4 entry sides**, run-orientation, no door-zone-from-schody. Rewrote 4
  Approach-A tests (core placement + "hub contains core" → "schody is the core / hol compact").
- **M1-M5 byte-identical:** `test_reserved_core_none_is_unchanged` green; `test_cpsat_solver` +
  `test_e2e` 32 passed / 1 xpassed (known flake); empty adversarial m1-m5-safety review.
- **Full non-GUI suite: 346 passed, 30 skipped, 1 xpassed, 0 failed** (`pytest --ignore=notebooks
  --ignore=tests/test_gui.py`, ~15 min).
- Renders (Dawid eyeballed): `notebooks/output/approach_b_stairs_{9x7,10x7,9x7_W,10x7_W}.png`
  (`notebooks/approach_b_stairs_preview.py`).

**Known / deferred (from the adversarial review — none on a live path):**
- Soft caps overshoot mildly on bigger footprints (kuchnia ~15 on 10×7, garderoba ~8 on 9×7-W; the
  hub/podest balloons on oversized ≥99 m²/storey). This is the **Faza-2 overflow-rooms GAP** (add
  gabinet/4th bedroom), explicitly deferred. `unabsorbed_leftover` is inert while a hub exists
  (uncapped sink zeroes it) — Faza 2 should derive the overflow signal from the hub exceeding a hall
  ceiling instead.
- `_reserve_core` is **notch-unaware** — a pinned core can land in an L-shape notch → INFEASIBLE
  (pre-existing; legacy Approach A failed too; Stage-1 non-rectangular polygons are not wired into
  `generate_house` yet). **Make `_reserve_core` read `boundary.notch` + add an L-polygon regression
  test BEFORE wiring Stage-1 sub-plots into house mode.**
- Renderer nit: stair arrow can overlap the centred "Schody" label (cosmetic).

> ⚠️ Session 17 + 18 work is in the working tree, **NOT committed** (push/commit = Dawid's decision).

---

## Session 16 (2026-06-01 — Plan 3 UI: house mode in Stage 4)

Added a parallel **single-family house** path to the Stage 4 tab, toggled by a
"Tryb" radio (Mieszkanie w bloku M1-M5 / Dom jednorodzinny). The M1-M5 apartment
path is **behaviorally unchanged** — house mode is purely additive.

- **`viz/house_preview.py`** (NEW, GUI-free; 5 tests in `tests/test_house_preview.py`):
  `furnish_layout` / `house_details_text` / `render_house_figure` wrap the existing
  `generate_house` + `place_furniture` + `render_two_storey` engine so the UI logic is
  testable without PyQt (GUI tests abort headless).
- **`ui/main_window.py`**: mode radio (`mode_apartment_radio`/`mode_house_radio`);
  apartment options wrapped in an `apt_options` container, new hidden `house_options`
  (furniture toggle `furniture_check`, default ON); `HouseGenerateWorker` (QThread) →
  `generate_house` (1 layout, 2 storeys); `_on_house_ready`/`_show_house` render
  PARTER|PIĘTRO into the existing preview; **PNG export works**; **To-ArchiCAD disabled
  for houses** (AC export = later C++ shell). Shared outline helper `_input_polygon_entry`
  (DRY — both modes use it).
- **Verified:** new module 5 tests green; real end-to-end (CP-SAT `generate_house` on an
  8×10 outline → `render_house_figure`) produces a 2-panel PNG; **F2 holds in the real run**
  (bathroom 4.6 m² ≤ 5.0, WC 3.0 ≤ 3.0). GUI click-through = manual (headless GUI tests abort).
- **Known / deferred:** house excess-distribution GAP is VISIBLE (e.g. salon ~46 m² /
  master bedroom ~43 m² on an 80 m²/storey footprint) — Dawid's architectural call, NOT
  fixed this session. Minor: mode radios are not disabled mid-generation (pre-existing
  pattern, self-corrects). Branch `feat/sfh-furniture` still not merged/pushed (Dawid's call).
- Spec/plan: `docs/superpowers/specs/2026-06-01-stage4-house-mode-ui-design.md`,
  `docs/superpowers/plans/2026-06-01-stage4-house-mode-ui.md`.

**Session 16 cz.2 — wiarygodne schody + komunikacja (Approach A):** po tym jak Dawid
ocenił schody jako źle zlokalizowane (i dostarczył 8 wzorców ARCHON), poprawiono klatkę:

- `core/house_layout.py`: nowy `_stair_core_dims(W,H)` — **adaptacyjna geometria rdzenia**
  (bieg prosty dla wydłużonych `aspect>1.4`, U/zabiegowe dla kwadratowych; pole ~4–6 m²
  zamiast 7.5). `_reserve_core` ustawia rdzeń **cofnięty od wejścia** (`STAIR_SETBACK=0.8`,
  środkowy pas głębokości) zamiast przy ścianie frontowej.
- **Setback 1.3→0.8** po diagnozie: 1.3 łamało feasibility parteru na 9×7 (bezpośrednie
  uruchomienia solvera). 0.8 OK dla 8×8/9×7/10×7.
- **6×11 = INFEASIBLE** — nie regresja: stary kod też to wywalał (6 m za wąskie na 7-pokojowy
  parter). `generate_house` zwraca `ok=False`.
- **Hub geometry-bound:** próba przycięcia hubów przez `opt` w szablonach okazała się **no-op**
  (parter hub 10.91 m²=17%, pietro 8.64=13.5% — rozpychane przez containment rdzenia +
  pokrycie, niezależnie od `opt`); szablony bez zmian. Część czysto-holowa ~8%; mniejszy/osobny
  „Schody" = Approach B (fallback). Dawid zaakceptował wynik wizualnie.
- Testy: `tests/test_house_staircase.py` (8). Renders `notebooks/output/sfh_stairs_{8x8,9x7,10x7}.png`.
- Spec/plan: `docs/superpowers/specs/2026-06-01-house-staircase-circulation-design.md`,
  `docs/superpowers/plans/2026-06-01-house-staircase-circulation.md`.

---

## Session 15 (2026-05-31 — house ROADMAP + merge + furniture)

**Authoritative direction now `docs/ROADMAP_domy.md`:** freeze Stages 1/2/3 (mark legacy),
focus Stage 4 (CP-SAT) on real house plans (detached → twin → terraced). Brain = Python
forever; C++ only as the AC shell (Tapir).

- **Merged** `feat/sfh-2storey-mvp` → `main` (fast-forward `ca92621`, **not pushed**).
- **F2 guard** added (`test_house_wet_rooms_never_exceed_wt_cap`): verified the bathroom
  ≤5 m² cap holds structurally (solver `upper_bound` via `WT_MAX_AREA`); without the cap a
  16×13 footprint yields a 7.76 m² bathroom — test bites. No solver change needed.
- **Plan 2 — furniture** (`core/furniture.py`, branch `feat/sfh-furniture`, `dc77773`):
  canonical PL furniture sets per room type (spec §5), greedy wall placement, Shapely
  collision, skip-if-no-fit. **Doors inferred only from edges shared with a KOMUNIKACJA room
  (F5)** — pure geometric adjacency over-constrained placement (starved bathtub/shelves).
- **2-storey renderer** `viz/plan_renderer.py::render_two_storey` — PARTER|PIĘTRO panels,
  furniture, aligned staircase symbol (correct bbox offset: rooms absolute, `stair_core`
  bbox-relative). PNG `notebooks/output/sfh_furnished.png`.
- **NOT done / next (per roadmap):** ~~Plan 3 UI (JEDNORODZINNA mode + furniture toggle)~~
  ✅ **done in Session 16**; house excess-distribution quality gap (needs Dawid's call),
  twin/terraced types.

---

## Current state (2026-05-05)

### Stage 4 — Apartment layout (per-apartment room layout) — STABLE

| Component | Status |
|---|---|
| `core/cpsat_solver.py` | ✅ CP-SAT solver, F2 hard cap, Q6 distribution |
| `core/validator.py` | ✅ MIN+MAX area checks, `strict_max_areas` flag |
| `core/scorer.py` | ✅ multi-criteria scoring |
| `core/variant_generator.py` | ✅ N variants with topology blocking |
| `core/boundary_analyzer.py` | ✅ notch detection, collinear cleanup |
| `core/trapezoid_handler.py` | ✅ inscribed rect + clip |
| `bridge/tapir_connection.py` | ✅ ArchiCAD via Tapir Add-On (port 19723) |
| `bridge/boundary_reader.py` | ✅ reads Wall/Slab/Zone, auto-detects entry/walls |
| `bridge/plan_writer.py` | ✅ exports apartments as Zones to AC |
| `viz/plan_renderer.py` | ✅ matplotlib renderer |
| `ui/main_window.py` (Stage 4 tab) | ✅ load AC, classify walls, generate, export |

**Tests:** `pytest tests/` — 80/80 pass + 26 skipped.

**Verified rules (FUNDAMENTAL):**
- F1 — 100% coverage equality (`sum(rooms) == usable_area` in solver)
- F2 — bathroom max 5m², WC max 3m² (`WT_MAX_AREA` in `config.py`)
- F4 — hub max 15% of usable area
- Q6 — salon takes 80% of excess area, sleeping rooms 20% proportionally
- Q7 — F2 wins over `procent_powierzchni` from templates

### Stage 3 — Floor layout (divide floor into apartments) — REWRITE done 2026-05-05

After 3 patch attempts on `floor_multistair.py`, **B1 rule applied** (2 fails →
rewrite). Old modules removed:
- ❌ `core/floor_multistair.py` — deleted
- ❌ `core/floor_corridor_solver.py` — deleted

**New deterministic architecture** in `core/floor_layout.py`:

| Component | Status |
|---|---|
| `core/floor_compute.py` | ✅ helpers: stairwell dims, apartment count, building class |
| `core/floor_layout.py` | ✅ deterministic geometry: stairwell at facade, central corridor, T-shape connector |
| `core/floor_validation.py` | ✅ Dijkstra walking-distance on corridor graph (networkx) |
| `core/floor_solver.py` | 🟡 single-apartment solver (legacy, kept as MVP backup) |
| `ui/floor_layout_window.py` | ✅ standalone window + `FloorLayoutWidget` for tab integration |
| `ui/main_window.py` | ✅ two tabs: Stage 4 + Stage 3 |
| `docs/FLOOR_LAYOUT_DESIGN.md` | ✅ design rationale |
| `docs/WT_PARAMETERS.md` | ✅ WT 2002 parameters with paragraph references |

**Geometry rules implemented:**
- Stairwell at chosen facade (default N) for natural daylight
- Stairwell centered along the long axis (centered apartments minimize walking
  distance: ±40m → max 80m corridor with one stairwell)
- Connector strip (corridor-width) bridges stairwell to main corridor
- Main corridor 1.4m wide (WT §237) along the long axis, full length
- Apartments sliced from rectangular zones along the corridor edge
- Walking distance ≤40m WT §256 (validated by Dijkstra)
- Number of stairwells: `max(geometric, WT_class_min, capacity)`
  - Geometric: `ceil(main_length / 80)`
  - WT min: 1 for class N, 2 for SW/W/WW

**Verified scenarios:**

| Scenario | Stairs | Apts | Max walk | Status |
|---|---|---|---|---|
| 200 m² floor, 4 storeys, class N | 1 | 2 | 7.6 m | ✅ OK |
| 800 m² floor, 4 storeys, class N | 1 | 9 | 23.7 m | ✅ OK |
| 1200 m² floor, 4 storeys, class N | 1 | 14 | 32.7 m | ✅ OK |
| 600 m² floor, 5 storeys, class SW | 2 | 7 | 12.2 m | ✅ OK |
| 800 m² floor, facade=S | 1 | 9 | 23.7 m | ✅ OK |

### UI

- **Two-tab QTabWidget** in `ui/main_window.py`:
  - "Apartment Layout (Stage 4)" — full Stage 4 workflow
  - "Floor Layout (Stage 3)" — embedded `FloorLayoutWidget`
- **All UI strings in English** (translated 2026-05-05).
- Stage 4 features: load outline (Zone via Inner Edge), interactive
  facade/entry editor (click + Shift+click), generate variants, score filter,
  navigate variants, export PNG / to ArchiCAD.
- Stage 3 features: floor outline (manual or from AC), building params
  (height, floor count → class N/SW/W/WW), apartment mix sliders,
  WT overrides (corridor width, max walking distance), generate.

### Tools / dependencies

- Python 3.13 + venv
- `ortools 9.15`, `shapely 2.1`, `matplotlib 3.10`, `pyqt5 5.15`,
  `archicad 29.3`, `networkx 3.6`

---

### Stage 1 — Phase 1 (Pack Architecture) — COMPLETED 2026-05-11

| Component | Status |
|---|---|
| `rules/_loader.py` | ✅ `load_pack()` + `get_default_pack()` (memoized) |
| `rules/_schema.py` | ✅ Pydantic schemas (PackManifest, PackConstants) |
| `rules/PL/pack.yaml` | ✅ PL pack manifest (v1.0) |
| `rules/PL/constants.yaml` | ✅ All rule-driven constants extracted from config.py |
| `rules/PL/wt_rules.json` | ✅ 19 WT 2002 rules (moved from rules/) |
| `rules/PL/user_rules.json` | ✅ User MPZP overrides template (moved) |
| `rules/README.md` | ✅ "How to add a country pack" |
| `tests/test_pack_loader.py` | ✅ 12 tests pass |
| `tests/test_pack_constants.py` | ✅ 14 tests pass |
| `core/cpsat_solver.py`, `validator.py`, `scorer.py`, `site_planner.py`, `plot_indicators.py`, `floor_compute.py`, `floor_layout.py` | ✅ All load constants from pack |
| `config.py` | ✅ Reduced to 12 lines (SCALE only — Python-runtime, not rule-driven) |

**Tests:** 172 passed (up from 144 baseline). Behavior change: none — pure refactor.
**Next:** Phase 2 — Report Layer (PDF generation).

---

### Stage 1 — Phase 2 (Report Layer) — COMPLETED 2026-05-11

| Component | Status |
|---|---|
| `core/report_data.py` | ✅ ReportData + nested dataclasses + estimate_units + compute_hash + GLOSSARY |
| `core/report_renderer.py` | ✅ 3 matplotlib figures: plot_zone, indicators_bar, variants_grid |
| `core/report_pdf.py` | ✅ 9-page reportlab assembly + CLI (`python -m core.report_pdf`) + logo support + Polish font (Arial Unicode on macOS) |
| `tests/fixtures/sample_report.py` | ✅ Reusable test fixture + sample logo generator |
| `tests/test_report_data.py` | ✅ 13 tests pass |
| `tests/test_report_renderer.py` | ✅ 6 tests pass |
| `tests/test_report_pdf.py` | ✅ 8 tests pass (incl. logo + CLI) |
| `requirements.txt` | ✅ pypdf>=4.0 added |
| momepy evaluation | ✅ NO-GO documented in notebooks/momepy_eval.py |

**Tests:** 196 passed (172 Phase 1 baseline + 27 new Phase 2 tests; 31 skipped, 1 xpassed).
**Deliverable:** `python -m core.report_pdf --fixture sample --out X.pdf` produces 9-page ~165KB PDF.
**Known issue:** macOS-only Polish font (Arial Unicode TTF path). Cross-platform handling deferred to Phase 3.

---

### Stage 1 — Phase 3 (UI Integration) — COMPLETED 2026-05-24 (commit 9017bae)

UI wire-up Phase 2 PDF backend → Stage 1 Mode A pipeline. Shipped end-to-end:
"Mode A → Generate → Eksport PDF → 9-page report".

| Component | Status |
|---|---|
| `core/report_builder.py` | ✅ `build_report_data(plot, variants, indicators, verification, *, plot_id, plot_address, logo_path=None) → ReportData`. Q14 5% warning band (MAX-constrained WZ/WIZ, MIN-constrained PBC). VariantInfo detailed metrics (PUM, headroom, parking, height). Polish chars preserved. `data_hash` stable across runs, sensitive to plot_id changes. Empty variants → `ValueError`. |
| `ui/report_metadata_dialog.py` | ✅ `ReportMetadataDialog(QDialog)` collects `plot_id` / `plot_address` / `logo_path`. `QSettings("FloorPlan6", "Stage1Report")` persists last-used logo across sessions. |
| `ui/stage1_window.py` (Stage1Widget) | ✅ `export_pdf_btn` (disabled by default, enabled after Mode A success). `_mode_a_results` cache: `(plot, variants, indicators, verification)`. `_on_export_pdf` handler: metadata dialog → `build_report_data` → `QFileDialog` (prefilled `Raport_<plot_id>_<YYYY-MM-DD>.pdf`) → `generate_pdf`, sync with `Qt.WaitCursor` + `processEvents`. Cache invalidation in `_run_mode_b` (Mode B uses different pipeline). |
| `tests/conftest.py` | ✅ session-scoped `qapp` (manual, no `pytest-qt`); `isolated_qsettings` (IniFormat + `setPath` on `tmp_path` + clear/sync between tests); `make_minimal_plot` (40×30 m rectangle with buildable zone). |
| `tests/test_report_builder.py` | ✅ 14 tests pass (covers status mapping, Q14 band, hash stability, empty-variants ValueError) |
| `tests/test_report_metadata_dialog.py` | ✅ 5 tests pass (cancel returns None on Rejected, QSettings round-trip, Polish chars) |

**Subsequent enhancement (2026-05-?, commit `f7c923c`):**
report_builder + stage1_window extended for depth-aware building dimensions
and Mode B building proposals; not a regression of Phase 3 — same Eksport PDF
flow, richer VariantInfo metrics.

**Spec / plan (kept for history):**
- `docs/superpowers/specs/2026-05-13-stage1-phase3-ui-integration-design.md`
- `docs/superpowers/plans/2026-05-14-stage1-phase3-ui-integration.md` (19 tasks executed)

**Pytest (2026-05-27):** 19 Phase 3 tests pass; full non-GUI suite 287 pass / 31 skip / 1 xpass (Session 10 baseline).

**Outstanding from original spec (deferred phases):**
- Phase 3.1 — multi-persona views (architect / inwestor / klient końcowy).
- Phase 3.2 — macOS-only Polish font (Arial Unicode) → cross-platform handling.
- Phase 4 — Mode B report (currently `export_pdf_btn` is Mode A only; cache is invalidated on Mode B run).

---

## What's next

1. **Integration Stage 3 → Stage 4** — clicking an apartment in Stage 3 layout
   → opens its outline in Stage 4 tab for room-level detailing
2. **Walls + doors export to AC** — currently zones only; add real walls and
   door elements (B1+B2 from earlier backlog)
3. **L-shape floors** — `floor_layout` currently assumes rectangular floor
4. **Stage 1 (plot analyser)** — Mode A foundation imported. Q1–Q18
   decided 2026-05-07. **Session 1 done** (data model + buildable zone +
   indicators + 18 regression tests + L-shape/triangle viz). Next:
   Session 2 — port `verifier.py` to `core/plot_verifier.py` with Q13/Q17
   gating and Q14 5% band; Session 3 — port `optimizer.py` to
   `core/site_planner.py` with multi-family adapter; Sessions 4–5 — Mode B
   parcelacja prototype in `notebooks/` then port to `core/`.

   **Stage 1 Session 1 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/plot_model.py` | ✅ `Plot`, `PlotBoundary`, `BoundaryType`, `MPZPParameters`, `HousingType` (Q12, Q13, Q15, Q17 fields) |
   | `core/site_element_model.py` | ✅ `SiteElement`, `SiteElementType` |
   | `core/buildable_zone.py` | ✅ `BuildableZoneBuilder` (setback buffers via Shapely) |
   | `core/plot_indicators.py` | ✅ `PlotIndicatorCalculator`, `PlotIndicators` (WZ/WIZ/PBC) |
   | `rules/wt_rules.json` | ✅ 19 WT 2002 rules with paragraph references |
   | `rules/user_rules.json` | ✅ empty MPZP override template |
   | `tests/test_buildable_zone.py` | ✅ 18/18 pass (rectangle, L-shape, triangle, edge cases) |
   | `notebooks/stage1_buildable_zone.py` | ✅ matplotlib viz for rectangle + L-shape + triangle |

   **Stage 1 Session 2 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/site_wall_model.py` | ✅ `SiteWall`, `WallOpeningType`, `WallOpening` |
   | `core/plot_verifier.py` | ✅ `PlotVerifier`, `VerificationResult`, `VerificationStatus`. 5 categories with Q13/Q17 gating + Q14 5% band + `strict` flag |
   | `tests/test_plot_verifier.py` | ✅ 14/14 pass (indicators band, Q13/Q17 gating, walls, parking, conditional warnings, sort order) |

   **Stage 1 Session 3 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/site_planner.py` | ✅ `SitePlanner`, `BuildupVariant`. Mode 1 propose_max_buildup (3 variants) + Mode 2 place_building. Q13+Q17 gating. Multi-family parking row scaling. Inscribed-rect bug fix (source iterated min, fixed to max). |
   | `core/plot_model.py` | ✅ helper methods `road_boundary()`, `undeveloped_neighbour_boundaries()`, `bbox_dimensions`, `perimeter` |
   | `core/site_element_model.py` | ✅ `units: int` field added (multi-family parking scaling) |
   | `core/plot_indicators.py` | ✅ `_required_parking` now scales with `Σ building.units × MPZP coefficient` |
   | `tests/test_site_planner.py` | ✅ 12/12 pass (variants, gating, multi-family parking row, inscribe-rect fix) |
   | `notebooks/stage1_site_planner.py` | ✅ Mode A viz: rural / municipal / wielorodzinna side-by-side |

   **Stage 1 totals after Session 3:**

   - **44 tests** green (18 buildable_zone + 14 verifier + 12 site_planner)
   - Mode A logic complete end-to-end (read plot → zone → indicators → verify → propose buildup)
   - Missing: AC bridge wire-up, UI tab, Mode B parcelacja

   **Stage 1 Session 4 components (2026-05-07) — Mode B prototype, Jupyter only:**

   | Component | Status |
   |---|---|
   | `notebooks/stage1_subdivision_v1.py` | ✅ first iteration — exposed architectural error: setbacks were carved from parent, ~27% nieużytek |
   | `notebooks/stage1_subdivision_v2.py` | ✅ corrected — sub-plots tile entire parent; setbacks are per-sub-plot building constraints |
   | viz `stage1_subdivision_v2.png` | ✅ rectangle 60×80, L-shape, long narrow 30×100 — Q16 diff=0 in all cases |

   **Mode B prototype validates implemented decisions:**

   - Q1(a) clip — L-shape sub-plots clipped, notch becomes explicit nieużytek
   - Q5(c) orientation search — long-narrow 30×100 picks axis-aligned (2 valid sub-plots) over rotated (5 with road-access failure)
   - Q15 min_front — sub-plots ≥18m front enforced
   - Q16(a) strict coverage — `Σ sub + roads + nieużytek == parent` exactly (diff=0)
   - Per-sub-plot buildable zone — each sub-plot has its own non-empty zone (anti-bug-#3 from C++ Plot Subdivider)

   **Mode B prototype gaps (status after Session 5):**

   - Q1.1(c) push-neighbour mechanism — **deferred**, currently Q1.1(d) drop-to-nieużytek (within-spec since "no sub-plot below minimum" constraint is satisfied)
   - Q3(c) front-to-road enforcement for terraced/twin — ✅ **closed in Session 5**
   - Q4(a) twin-house pairs — confirmed concern lives at Stage 2/4, not subdivision (1 sub-plot = 1 segment per Q4(a) decision); **closed** by no-op
   - Variable column widths / row depths — deferred (current uniform tiling works for tested cases)
   - **Regression tests for 4 C++ Plot Subdivider bugs** — ✅ **closed in Session 5**

   **Stage 1 Session 5 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `core/plot_subdivider.py` | ✅ port from `notebooks/stage1_subdivision_v2.py` + Q3(c) enforcement + Q12 single-family validation |
   | `tests/test_plot_subdivider.py` | ✅ 17/17 pass: anti-bug regressions (#1/#2/#3/#4), Q12, Q15, Q16(a), Q3(c) terraced/twin/detached, Q5(c) orientation search |

   **Stage 1 totals after Session 5:**

   - **61 tests** green (18 buildable_zone + 14 verifier + 12 site_planner + 17 plot_subdivider)
   - **Mode A end-to-end logic:** ✅ complete
   - **Mode B end-to-end logic:** ✅ complete (with Q1.1(d) fallback for too-small clipped cells)
   - **Outstanding for full Stage 1 product:** AC bridge wire-up + UI tab + Q1.1(c) full push (deferred)

   **Stage 1 Session 6 components (2026-05-07):**

   | Component | Status |
   |---|---|
   | `bridge/plot_reader.py` | ✅ `read_plot_from_archicad()` + `wrap_polygon_as_plot()`; default-classifies bottom edge as DROGA, others as SASIAD_NIEZABUDOWANY |
   | `ui/stage1_window.py` | ✅ `Stage1Widget` + `Stage1Window`. Q12 enforcement (Mode B disabled for wielorodzinna). Mode A pipeline: site_planner.propose_max_buildup → indicators → verifier → render. Mode B pipeline: subdivide_with_orientation_search → render. |
   | `ui/main_window.py` | ✅ Stage 1 tab now `Stage1Widget` (was `Stage1PlotPlaceholder`) |

   **Stage 1 totals after Session 6:**

   - **61 tests** still green (no new tests in Session 6 — UI smoke test only)
   - **End-to-end usable from GUI:** ✅
   - **Outstanding:** AC zone export of sub-plots + Q1.1(c) push (deferred), edge-by-edge boundary classifier (defer)

   **Stage 1 Session 7 components (2026-05-10) — road-tree repair after AC tests:**

   | Component | Status |
   |---|---|
   | `core/subdivision_roads.py` | ✅ new active road-tree generator: one public-DROGA trunk + shortened branches; branches stop before non-DROGA parcel boundaries |
   | `core/plot_subdivider.py` | ✅ production flow now calls `generate_road_tree_layout()`; old OBB/pattern/katana helpers remain legacy-only and are not on active path |
   | `tests/test_plot_subdivider.py` | ✅ 19/19 pass; added urban regressions for dead-end roads and redundant road frontage |
   | `ui/stage1_window.py` | ✅ Mode B summary now shows buildable-zone %, road %, nieużytek %, and plots without road access |

   **Stage 1 verification after Session 7:**

   - `tests/test_plot_subdivider.py`: ✅ 19 passed
   - Stage 1 subset (`plot_subdivider`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 63 passed
   - Full non-GUI suite: ✅ 136 passed, 29 skipped, 1 xpassed
   - Full `pytest tests/`: ⚠️ aborts during `tests/test_gui.py` collection in headless PyQt import; verify GUI manually.

   **Known Stage 1 gaps still open:**

   - `core/plot_subdivider.py` still contains legacy experimental algorithms; active path is clean, but dead code should be moved to `notebooks/archive/`.
   - Road-tree is now structurally closer to the owner rule, but still needs visual AC validation on real selected plots before calling it product-ready.
   - Future model split: active frontage vs physical road-adjacent boundary, so corner/front-row plots are not over-penalized by setbacks.

   **Stage 1 Session 8 components (2026-05-10) — variant architecture MVP:**

   | Component | Status |
   |---|---|
   | `core/plot_variant_generator.py` | ✅ new Stage 4 style orchestration: generate subdivision candidates, validate, score, deduplicate, sort best-first |
   | `core/plot_subdivision_validator.py` | ✅ hard checks for no sub-plots, Q16 coverage, no nieużytek, road access, min/max sub-plot area, buildable zone |
   | `core/plot_subdivision_scorer.py` | ✅ weighted score breakdown: buildable area, road efficiency, waste control, road access, area fit, regularity |
   | `core/subdivision_roads.py` | ✅ `RoadTreeSettings` added so road-tree can be searched via deterministic strategies (`balanced`, `minimal`, left/right trunk, direct-bias) |
   | `core/plot_subdivider.py` | ✅ public `subdivide()` now preserves old API but returns the best scored variant |
   | `tests/test_plot_variant_generator.py` | ✅ RED→GREEN tests for scored sorted variants, multiple road strategies, and public API best-variant return |

   **Stage 1 verification after Session 8:**

   - `tests/test_plot_subdivider.py` + `tests/test_plot_variant_generator.py`: ✅ 27 passed
   - Stage 1 subset (`plot_subdivider`, `plot_variant_generator`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 71 passed
   - Full non-GUI suite (`pytest tests --ignore=tests/test_gui.py`): ✅ 143 passed, 30 skipped, 1 xpassed
   - Known test noise: Shapely `oriented_envelope` warnings remain; no failing assertions.

   **Stage 1 Session 9 components (2026-05-10) — tight 600/800 lots repair:**

   | Component | Status |
   |---|---|
   | `tests/test_plot_subdivider.py` | ✅ regression for wide top-road plot with `min_area=600`, `max_area=800`: no monster side/tail parcels, no tiny buildable zones |
   | `core/plot_subdivider.py` | ✅ oversized post-absorption plots are locally re-split; tight-area cases can add local access spurs when a side strip cannot be legally subdivided otherwise |
   | `core/plot_variant_generator.py` | ✅ tight-area strategy order so `subdivide()` finds a valid variant quickly |
   | `core/subdivision_roads.py` | ✅ tight-lot strategies may reduce branch edge clearance; normal strategies keep the previous safe clearance from non-road boundaries |

   **Stage 1 verification after Session 9:**

   - `tests/test_plot_subdivider.py` + `tests/test_plot_variant_generator.py`: ✅ 28 passed
   - Stage 1 subset (`plot_subdivider`, `plot_variant_generator`, `buildable_zone`, `plot_verifier`, `site_planner`): ✅ 72 passed
   - Reproduced tight top-road case: `road_tree_left_trunk`, 83 sub-plots, max parcel 797.1 m², min buildable zone 157.4 m², road 8.0%, waste 0.0%, validation errors 0.

   **Stage 1 Session 10 components (2026-05-25 → 2026-05-26) — segment-aware sub-plots:**

   Driven by Dawid's AC test on a 265×202 m plot where TWIN/TERRACED collapsed
   to 4 monster sub-plots (Q19), and a follow-up 60×80 m case where TWIN sub-plots
   were architecturally correct but produced 0 buildable footprints because the
   default 3 m side setback ate the entire frontage (Q21). Three connected
   owner decisions — Q19 (road access), Q20 (per-type MPZP scaling), Q21
   (shared walls).

   | Component | Status |
   |---|---|
   | `core/building_proposer.py` | ✅ `BuildingType.SEMI` → `BuildingType.TWIN` (the dict crashed at import — Mode B/TWIN+TERRACED GUI flow was unreachable); pair/chain detection refactored to call `core/subdivision_topology` so subdivider and proposer agree |
   | `core/plot_subdivider.py` (Q19) | ✅ `_filter_for_building_type` and `_wrap_valid_subplot` accept parent DROGA OR internal road for ALL building types (Q3 only mandates orientation, not location) |
   | `core/plot_subdivider.py` (Q20) | ✅ `_with_effective_mpzp` scales `min_front_m`/`min_sub_plot_area_m2`/`max_sub_plot_area_m2` per BuildingType so 1 sub-plot = 1 segment; `_min_short_dim(mpzp)` derives the `_is_buildable_shape` guard from `mpzp.min_front_m` (no longer hardcoded 12 m) |
   | `core/plot_subdivider.py` (Q21) | ✅ `_mark_shared_walls(sub_plots, building_type, plot)` runs AFTER absorb/split, sets `PlotBoundary.is_shared_wall=True` on the shared edge of every pair (TWIN) or chain neighbour (TERRACED), and rebuilds the affected sub-plots' buildable zones |
   | `core/plot_model.py` | ✅ `PlotBoundary.is_shared_wall: bool = False`; `min_setback` returns 0 when the flag is set |
   | `core/buildable_zone.py` | ✅ `_setback_distance` short-circuits to 0 for `is_shared_wall=True` boundaries (Mode A unaffected — flag defaults False) |
   | `core/subdivision_topology.py` | ✅ NEW shared helpers `find_adjacent_pairs`, `find_chains`, `longest_linestring`; one source of truth for both `building_proposer` and `plot_subdivider._mark_shared_walls` |
   | `tests/test_building_proposer.py` | ✅ NEW (4 tests): SEMI→TWIN regression + DETACHED/TWIN/TERRACED end-to-end smoke (TWIN unblocked by Q21) |
   | `tests/test_plot_subdivider.py` | ✅ `TestQ19RoadAccess` (5 tests) + `TestQ20SegmentScaling` (6 tests) + `TestQ21SharedWalls` (4 tests) |
   | `docs/OPEN_QUESTIONS.md` | ✅ Q19, Q20, Q21 added as DECIDED with owner reasoning |
   | `requirements.txt` | ✅ `reportlab>=4.0` added (Phase 2 dep that was missing) |

   **Stage 1 verification after Session 10 (2026-05-26):**

   - Full non-GUI suite (`pytest --ignore=notebooks --ignore=tests/test_gui.py`):
     ✅ **287 passed, 31 skipped, 1 xpassed** (exit 0, ~10 min)
   - Pre-Q21 baseline (modified-areas subset, briefing 2026-05-25):
     39 passed + 1 failed (`test_propose_buildings_twin_runs_and_assigns`)
   - Post-Q21 (same subset): all 5 GREEN (4 new `TestQ21SharedWalls` +
     previously-red TWIN regression).
   - Verified: TWIN on 60×80 m now places ≥1 building (was 0/7);
     `TestQ19RoadAccess` confirms TWIN/TERRACED on 265×202 m no longer collapse
     to monster sub-plots; Mode A unaffected (Q21 flag defaults False).

   **Stage 1 Session 10 visual sanity check (2026-05-27) — PASS:**

   | Component | Status |
   |---|---|
   | `notebooks/stage1_q21_sanity.py` | ✅ NEW: 5 scenarios (265×202 DETACHED/TWIN/TERRACED + 60×80 TWIN/TERRACED) rendered via production `subdivide()` + `propose_buildings()` |
   | `notebooks/output/q21_sanity_*.png` | ✅ 5 detail + 1 overview PNG |

   - 60×80 TWIN: **5/5 buildings** (regression vs pre-Q21 0/7) ✅
   - 265×202 TWIN: 70 sub-plots, 35 TWIN pairs, 100% coverage, Q21 shared walls visible between paired neighbours ✅
   - 265×202 TERRACED: 81 sub-plots in 6 chains, 100% coverage, every sub-plot has a building, shared walls along chain ✅
   - Q16 coverage: diff=0.00 m² in all 5 scenarios; nieużytek=0%
   - Architectural review (owner): pass — close Q21 visual validation, no further fixes required this session.
   - Outstanding open questions noted but not blocking: DETACHED `max_sub_plot_area_m2=2000` may be too generous (avg 1729 m² per sub-plot); TERRACED produces 81 not 120+ on 265×202; vertical road appears mid-plot in 265×202 layouts. None marked as bugs.

   **Stage 1 outstanding (after Session 10 + sanity check 2026-05-27):**

   - STATE.md Phase 3 section still says "PLAN READY, NOT IMPLEMENTED" — UI
     integration (Eksport PDF) shipped in commit `9017bae` 2026-05-?; sync needed.
   - Q1.1(c) push-neighbour mechanism — still deferred (Q1.1(d) drop-to-nieużytek
     fallback is in production).
   - ~~`core/plot_subdivider.py` legacy experimental algorithms~~ — DONE 2026-05-27:
     21 dead functions removed (file 2860 → 1731 lines, −39%); 287 non-GUI tests
     still pass, no regressions.

   **Stage 1 → Stage 4 integration (Session 11, 2026-05-27):**

   | Component | Status |
   |---|---|
   | `core/building_to_apartment_input.py` | ✅ NEW — pure-Python adapter SubPlot → (polygon, entry, list[WallType]); midpoint-based shared-wall classification (deviation from spec to prevent false-positive INTERNAL on edges that merely touch at endpoints). 6 unit tests pass. |
   | `ui/stage1_window.py` Stage1Widget | ✅ + `apartment_layout_requested` signal; canvas `button_press_event` hit-test → `_selected_sub_idx`; yellow 3pt highlight on selected sub-plot in `_render_mode_b`; "Otwórz wybraną sub-działkę w Stage 4" button (disabled until selection with `proposed_building`). |
   | `ui/main_window.py` MainWindow | ✅ + `self.stage1_widget` / `self.apt_tab` exposed as members; signal wired in `_build_ui`; `_populate_stage4_from_stage1` slot fills `_imported_polygon/_imported_entry/_imported_wall_types` and switches active tab; `_confirm_stage4_overwrite` QMessageBox.question with Cancel default. |
   | `tests/test_stage1_stage4_integration.py` | ✅ NEW — 2 Qt smoke tests via `qapp` fixture (slot fills fields + tab switch; no emit without proposed_building). |
   | `docs/superpowers/specs/2026-05-27-stage1-stage4-integration-design.md` | ✅ design spec |
   | `docs/superpowers/plans/2026-05-27-stage1-stage4-integration.md` | ✅ implementation plan (9 TDD tasks) |

   **End-to-end smoke (programmatic, 2026-05-27):** 60×80 TWIN → 5 sub-plots, 5/5 with proposed_building; clicking #1 → button enables → emit → `_imported_polygon` (76.5 m²), `_imported_entry` (7.75, 35.5), wall_types [INTERNAL, FACADE, FACADE, FACADE] — exactly TWIN expectation (1 INTERNAL + 3 FACADE) — active tab switched to Stage 4. PASS.

   **Suite after Session 11 (2026-05-27):** 296 passed, 29 skipped, 1 xpassed in the full non-GUI suite (target was 295: 287 baseline + 6 helper + 2 integration; 1 extra likely due to a previously-skipped test becoming runnable). One known-flake (`test_cpsat_solver::test_hub_adjacency_m2`) fails intermittently — sibling `test_hub_adjacency_m3` is already xfail-marked with the same root cause (CP-SAT non-determinism + Shapely clipping); passes in isolation; unrelated to this session.

   **Scope (decided in brainstorm 2026-05-27):**
   - Mode B single-family only (DETACHED/TWIN/TERRACED).
   - Auto-detect: entry = midpoint of building edge whose midpoint is nearest a road geometry; walls INTERNAL where midpoint lies within 0.5 m of a Q21 `is_shared_wall=True` boundary, FACADE otherwise.
   - User explicitly clicks Generate in Stage 4 (no auto-solver).
   - Confirm dialog when Stage 4 already holds variants.

   **Out of scope (still on backlog):**
   - Mode A → Stage 4 (different UX — choose variant first).
   - Wielorodzinna → multi-apartment in one building (needs Stage 3 floor layout first).

   **Stage 1 Session 14 (2026-05-29) — monster sub-plot fix (focused rewrite):**

   Fixed Dawid's AC bug (2026-05-28): on an irregular plot where a notch cuts a
   band off from the single-side road tree, `_absorb_leftover`'s unconditional
   scored-merge glued the whole road-less band into one giant parcel (S7 =
   19 664 m² / cap 1000 m²). B1 rewrite (not patch), one owner decision: **rescue
   then demote** (Dawid 2026-05-29) + **trim dead-end road tips** (full clean).

   | Component | Status |
   |---|---|
   | `core/plot_subdivider.py` `_absorb_leftover` | ✅ road-less leftover band ≥ min_area is kept as a STANDALONE road-less sub-plot (NOT glued into a road-accessible neighbour — that was the monster's root cause). Tiny road-less slivers still merge. |
   | `core/plot_subdivider.py` `_resolve_oversized_parcels` | ✅ NEW terminal post-pass, runs ONCE after the absorb/split loop converges (no absorb↔split oscillation). Per sub: road-accessible oversized → plain split; else (road-less or awkward) → legal-spur rescue (partial-accept); else → demote to nieużytek (Q16(a)/Q1.1(d)). Never keeps a monster. |
   | `core/plot_subdivider.py` `_rescue_or_demote` | ✅ carves an access spur into a cut-off band, cheap-selects the best legal spur by reachable area, then splits only the top-3 candidates (perf: splitting all 14 hung the suite). Partial-accept keeps legal children. |
   | `core/plot_subdivider.py` `_spur_is_legal_access` | ✅ a rescue spur is legal iff it connects to the road network AND does not dead-end on a non-DROGA boundary > `min_road_width*0.5` (owner urban rule 2026-05-10). |
   | `core/plot_subdivider.py` `_trim_dead_end_roads` | ✅ trims road end-caps that dead-end on a non-DROGA boundary, GATED on layouts that already carry waste (`nieużytek > 1 m²`). Clean zero-nieużytek layouts (incl. roads grazing a sloped edge) are left untouched → no waste invented, no regression. |
   | `tests/test_plot_subdivider.py` | ✅ `TestMonsterOnIrregularSingleSideRoad`: `test_no_roadless_monster_subplot` (DETACHED+TWIN — was xfail, now GREEN), `test_coverage_holds_with_nieuzytek`, `test_rescue_spur_does_not_dead_end_on_non_road_boundary` (DETACHED+TWIN, NEW). |
   | `notebooks/stage1_notch_sanity.py` + `output/notch_sanity_*.png` | ✅ NEW visual sanity check (reuses the q21 renderer). |

   **Verification (2026-05-29):**
   - Notch 284×166: DETACHED 48 sub-plots max 932 m² (cap 1050), TWIN 98 max 427 m²
     — NO monster; every retained sub-plot has road access; Q16 coverage diff=0.00;
     nieużytek 7.4% / 6.7% (the genuinely cut-off corner, dead-end roads trimmed).
   - `tests/test_plot_subdivider.py`: **42 passed, 0 failed**.
   - Full non-GUI suite (`pytest --ignore=notebooks --ignore=tests/test_gui.py`):
     **301 passed, 30 skipped, 1 xpassed, 0 failed** (exit 0, 9:03). Baseline was
     295 passed / 3 xfailed → +6 passed (2 monster un-xfailed, 2 new dead-end,
     +2 noise), 0 regressions.

   **Gotcha for future sessions:** the tight-bounds 600-800 subdivision test is
   pre-existing pathologically slow (~7 min) and non-deterministic (road-tree
   `oriented_envelope` degeneracies) — NOT a regression. Don't chase a "hanging"
   subdivision test; verify with a ≥900 s timeout or `git stash` the baseline first.

5. **Stage 2 (volumetric generator)** — not started

---

## Operational notes

- Building rules (F1-F10) and workflow rules (B1-B10) in
  `docs/FUNDAMENTAL_RULES.md` are inviolable.
- Past lessons in `docs/LESSONS_LEARNED.md`.
- Architecture overview in `docs/ARCHITECTURE.md`.
- WT parameters table in `docs/WT_PARAMETERS.md`.
- Open architectural questions in `docs/OPEN_QUESTIONS.md`.
- After every session: update this file (WHAT WORKS / WHAT DOESN'T / METRICS).

---

# Historical (Polish) — sessions 1-7, kept for traceability

(Sessions before 2026-05-05 logged in Polish. Removed from this file for
brevity; see git history for full timeline.)
