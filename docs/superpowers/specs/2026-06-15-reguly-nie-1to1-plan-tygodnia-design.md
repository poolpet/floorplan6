# Spec: „Reguły, nie 1:1" — plan tygodnia (domy jednorodzinne)

**Data:** 2026-06-15 · **Autor sesji:** Claude + Dawid · **Status:** do akceptacji

> **Relacja do `2026-06-14-rzuty-jak-wzorce-design.md`:** ten spec **koryguje kierunek**
> tamtego. Po audycie (7 agentów) i decyzji Dawida przyjmujemy **reguły jako cel**, a wzorce
> jako **nauczyciela + miarkę regresji**. Faza „docisk 1:1 / IoU" z tamtego specu zostaje
> **zdemowana** z celu produktowego do **opcjonalnej diagnostyki regresji**. Reszta tamtego
> specu (refs_geo, render zwrotny, brama jakości) zostaje aktualna.

## 1. Decyzja kierunkowa (po ludzku)

Generator ma produkować rzuty **nieodróżnialne od realnego rzutu danego typu**, a nie
identyczne z konkretnym wzorcem. Powód jest twardy: produkt wypełnia **dowolny obrys**, który
architekt narysuje w ArchiCAD — „odtwórz wzorzec X" jest niezdefiniowane dla 99% inputów.
Wzorce to warianty **małego zestawu ~12 reguł** → reguły generalizują, 1:1 zapamiętuje szum.

**Decyzje Dawida (2026-06-15):**
1. **Reguły, nie 1:1.** Wzorce = nauczyciel + miarka, nie specyfikacja wyjścia.
2. **Kolejność: render-first.** Najpierw wizualna wiarygodność, potem fundament pomiaru,
   potem bloat powierzchni, potem reguły gramatyki.
3. **AC test: smoke wcześnie (dzień 2–3) + pełny na koniec (dzień 5).** Meble w AC zamrożone.
4. **Mieszkania: render za darmo + regresja AC; strojenie substancji tylko domy.** Poprawki
   renderu (wspólny `plan_renderer.py`) działają na mieszkania automatycznie; ich pipe AC
   (potwierdzony) pilnujemy regresją, by się nie zepsuł. Bloat/reguły mieszkań (Q6 salon-80%,
   M1–M5) **poza tygodniem** — focus substancji na domach per ROADMAP 2026-05-31.

## 2. Co ustalił audyt (fakty load-bearing)

- **Silnik CP-SAT jest mocny i to aktyw** — generuje poprawne, szczelne (F1), zgodne z WT
  rzuty z właściwym *zestawem* pokoi. **Wąskim gardłem NIE jest solver.**
- **Benchmark (58–60/100) nie mierzy pozycji.** Score = `0.5·F1 + 0.3·(1−MAPE/50) + 0.2·Jaccard`
  — kompozycja, nie geometria. Liczba nigdy nie mierzyła tego, co Dawid ocenia okiem.
- **refs_geo „ground truth" jest w 5/6 domów ZMYŚLONE.** Tylko powierzchnie realne (z tabeli);
  poligony model zgadł, by pasowały do obrysu (w plikach wprost: *„Geometria … dodana od siebie"*).
  Tylko `tropie` z realnego wektora (i to ręcznie kodowane). **Strojenie do tych plików =
  strojenie do wyobraźni modelu** — landmina, którą trzeba oznaczyć.
- **F2 (łazienka ≤5 m²) KONTRA wzorce:** 6 z 12 kondygnacji wzorcowych ma łazienki 5.38–9.09 m²
  (potwierdzony `tropie` = 5.38). „1:1" i „F2 święte" wykluczają się. **Rozwiązanie: trzymamy F2,
  nie obiecujemy odtworzenia łazienek >5 m².** Konflikt znika przez wybór reguł nad 1:1.
- **Trzy „fake tells" to RENDER, nie architektura:** meble wychodzą poza pokoje i pływają w
  korytarzu; ściany jako 1px kreski (brak poché); kolizje/duplikaty labeli; pokój poza obrysem.
  **`BESTSELLER_106_4syp.png` dowodzi, że silnik UMIE zrobić realny rzut** — luka to polish.
- **Raster vs PDF:** do geometrii PDF wektorowy wygrywa; raster/wizja dobre do labeli/reguł.
  **Przy runtime obrys przychodzi z AC jako czysty wektor (Tapir)** → problem PDF jest
  *offline'owy*, nie blokuje produktu.
- **`scorer.py` (6-wymiarowy) to dead code na ścieżce domów** — generator optymalizuje tylko
  area-fit + kwadratowość + mały hub. Brak obiektywu realizmu.

## 3. Stan eksportu do ArchiCAD (uczciwie)

- **Pokoje + ściany → AC:** pipe żyje i **potwierdzony dla MIESZKAŃ**; dla **domów**
  (2 kond., schody, parter+poddasze) **niezweryfikowany** — realne ryzyko, smoke test je zdejmie.
- **Meble → AC:** **zamrożone.** Tapir nie obraca obiektów ani nie ustawia absolutnego rozmiaru
  (nigdy nie pisze GDL A/B; `dimensions`→`xRatio/yRatio` to mnożnik defaultu). Pozycja na powłokę C++.
- Export odpala się z Pythona (`bridge/` przez Tapir), **wymaga AC otwartego u Dawida** —
  Claude przygotowuje skrypt, Dawid odpala (`! python …`).
- **Render matplotlib (poché, meble) = tylko podgląd.** AC konsumuje geometrię → realny zysk
  w AC daje substancja z Dnia 4–5, nie kosmetyka renderu.

## 4. Plan tygodnia (dzień po dniu)

Zasada: każdy krok → `pytest` + re-render + oko vs wzorzec → commit. Benchmark uśredniany po
**kilku seedach** (CP-SAT szumi ±2 pkt). F1–F10 i B1–B10 święte; zmiana reguły = jawny wyjątek (B3).

### Dzień 1 — Render: meble + ściany
- **1a. Klampowanie mebli do poligonu pokoju** — mebel przycięty/odrzucony, jeśli wychodzi poza
  parent room. ⚠️ ten sam bug może dotykać AC-export (anchor=CORNER) → render i AC mają jeść tę
  samą sklampowaną geometrię.
- **1b. Ściany z grubością (poché ~25–30 cm)** — obrys + przegrody jako wypełnione szare pasma.
- **Bramka:** re-render parterowiec / dom 2-kond / L, obok wzorca (modlnica, kudowe).

### Dzień 2 — Render: schody zabiegowe + higiena (+ smoke AC)
- **2a. Schody zabiegowe (winder) default** — zdjąć `force_straight=True`; odpalić
  `notebooks/winder_stair_probe.py` (feasibility na pełnym poddaszu); renderer rysuje wachlarz.
- **2b. Higiena renderu** — dedupe labeli, brak nakładania tekstu, nic poza obrysem.
- **2c. Smoke test AC (start)** — przygotować skrypt round-tripu JEDNEGO domu (parter+poddasze,
  ściany+pokoje+schody); Dawid odpala z otwartym AC. Cel: potwierdzić, że pipe domu w ogóle działa.
- **Bramka:** zestaw „przed/po" 4–5 renderów → **checkpoint z Dawidem** + wynik smoke AC.

### Dzień 3 — Uczciwy fundament pomiaru
- **3a. Oznaczyć prowenancję refs_geo** — pole `geometry_source: vision_approx|vector_traced`
  + `areas_source: table`. Commit refs_geo (teraz untracked).
- **3b. Metryka IoU jako diagnostyka** (waga ~0, sygnał trendu), tylko na `vector_traced` (`tropie`).
- **3c. Wpiąć darmowe sygnały** już w `reference_plans.json` a nieużywane: `entry_side`,
  `stair_kind`, `open_plan_day_zone` (tanie człony binarne).
- **Bramka:** nowy baseline benchmarku (multi-seed), zapisany w `STATE.md`.

### Dzień 4 — Bloat powierzchni *(Twój #1 z punch-listy)*
- **4a. `area→room-set scaling`** — korzeń bloatu: za mało pokoi na m². Nadmiar → WIĘCEJ/mniejszych
  pokoi (pralnia, garderoba, 2. łazienka), nie inflacja salonu/mastera.
- **4b. Dopasować capy** w `house_program.py DEFAULT_HOUSE_CAPS` do realnych powierzchni z **tabel**
  wzorców (wiarygodne, w odróżnieniu od poligonów). ⚠️ **soft targets**, nie hard — inaczej
  re-trigger perf/INFEASIBLE na dużym poddaszu (modlnica gardło).
- **Bramka:** spadek członu `0.3·MAPE`; re-render; multi-seed.

### Dzień 5 — Reguły gramatyki (runda 1) + AC + domknięcie
- **5a. Strefa dzienna jako jeden open-plan obiekt** (kuchnia‖jadalnia‖salon). ⚠️ świadomy wyjątek
  od F5 hub-star (B3).
- **5b. Łańcuch wejścia** — zewnątrz→wiatrołap/sień→hol→{strefa dzienna, schody}; zakaz
  zewnątrz→salon/sypialnia.
- **5c.** *(jeśli czas)* Garaż jako attached non-habitable, exempt z F6.
- **5d. Pełny test AC** — eksport 2–3 poprawionych domów (parter+poddasze) do oceny w AC.
- **5e. Regresja AC mieszkań** — eksport 1 mieszkania (M3), potwierdzić, że działający pipe
  ścian+pokoi się nie zepsuł po zmianach renderu/geometrii. To check, nie nowy kamień milowy.
- **Domknięcie:** update `STATE.md`, raport przed/po (benchmark + galeria renderów + screeny AC),
  lista co zostało.

## 5. Poza zakresem (YAGNI — w tym tygodniu)

Pikselowe 1:1 jako cel · pipeline raster · odmrażanie Stage 1/2/3 · meble w AC (zamrożone, C++) ·
**strojenie substancji mieszkań** (bloat Q6 salon-80%, reguły M1–M5 — mieszkania tylko render+regresja AC) ·
pełne strefowanie pięter · trzon instalacyjny (wet-room stacking) · L/T-footprint + garaż-bryła
dla ≥110 m² · perf dużych domów (≥120 m²) · dotrejsowanie pozostałych domów do pełnej geometrii.
→ **kolejny tydzień** (po fundamencie wszystko łatwiejsze).

## 6. Kryteria sukcesu (koniec tygodnia)

1. **Oko:** render 4–5 domów czyta się „jak rzut architektoniczny", nie „jak diagram"
   (meble w pokojach, ściany z grubością, schody zabiegowe, czyste labele) — potwierdza Dawid.
2. **Pomiar:** benchmark ma uczciwy baseline z nowymi członami; `0.3·MAPE` realnie spadł po Dniu 4.
3. **Prawda danych:** refs_geo oznaczone wg prowenancji i scommitowane; nikt nie stroi do zmyślonej geometrii.
4. **AC:** potwierdzony round-trip domu (ściany+pokoje) — wiemy, że pipe domu działa;
   regresja mieszkania (M3) zielona — działający pipe mieszkań nie zepsuty.

## 7. Ryzyka i mitygacje

- **Więcej/mniejszych pokoi → perf/INFEASIBLE** (duże poddasze): tylko soft targets; weryfikować w izolacji.
- **CP-SAT non-determinizm (±2 pkt):** benchmark zawsze multi-seed, nie gonić szumu.
- **Flaki testów** (11×11 single-storey timeout, 600–800 subdivision ~7 min): podejrzane regresje
  sprawdzać w izolacji, nie mylić z własnymi zmianami.
- **Furniture-clamp może być wspólny z bugiem AC-export** (anchor/multiplier): naprawić raz,
  na poziomie geometrii, którą jedzą oba.
- **Pipe domu do AC może nie działać** — dlatego smoke test wcześnie (Dzień 2), nie w piątek.

## 8. Pytania otwarte (nie blokują startu)

- Open-plan day-zone vs F5 hub-star — kształt wyjątku (B3): czy strefa dzienna liczy się jako
  jeden „pokój" przy huba, czy hub łączy się z klastrem jako całością?
- Czy capy z tabel wzorców (netto) wymagają przeliczenia netto→brutto przed wpięciem do `DEFAULT_HOUSE_CAPS`?
- Smoke AC: który dom na pierwszy ogień (najprościej round-trippujący — prostokąt 2-kond)?
