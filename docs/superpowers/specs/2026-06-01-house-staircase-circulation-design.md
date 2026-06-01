# Spec — Wiarygodne schody + komunikacja w domu jednorodzinnym (Etap 4)

**Data:** 2026-06-01 (Sesja 16, cz. 2)
**Branch:** `feat/sfh-furniture`
**Geneza:** Dawid (architekt) ocenił wynik trybu domu jako jeszcze niewiarygodny —
schody są źle zlokalizowane (patrz [[feedback_house_output_quality]]). Reality-check
pokazał, że GAP nadmiaru to artefakt za dużego obrysu (na ~64 m²/kondygnację rozmiary
pokoi są sensowne) — więc **priorytetem są schody i komunikacja**, nie GAP.
Dawid dostarczył 8 wzorcowych rzutów ARCHON (domy wolnostojące, parter + poddasze).

---

## 1. Cel

Dosunąć generowane schody i komunikację domu do konwencji z rzutów ARCHON, **bez
pogarszania** reszty (F1–F10, zgranie pionowe klatki, M1–M5 nietknięte). Nie celujemy
w pikselowe dorównanie ręcznemu projektowi — CP-SAT z prostokątnymi pokojami ma granice
— ale wiarygodność ma wskoczyć o poziom.

## 2. Stan obecny (co jest źle)

- Schody = `reserved_core` (prostokąt x,y,w,h, bbox-relative). Ograniczenie w solverze:
  **hub musi w całości zawierać rdzeń** (`core/cpsat_solver.py:458`). Brak osobnego
  pokoju schodów.
- `core/house_layout.py::_reserve_core`: rdzeń `sw=min(2.5, W·0.40)`, `sh=min(3.0, H·0.40)`
  → na 8×8 daje **2.5×3 = 7.5 m²** (za szeroki), i ustawia go **przy ścianie wejściowej**
  (`cy=0` dla wejścia od południa) — czyli wepchnięty do frontu.
- Szablony: `templates/house_parter.json` hub „Hol + schody" `procent [0.06,0.14]`, opt 9;
  `house_pietro.json` hub „Hol / podest" `procent [0.05,0.12]`, opt 6. Hub musi zmieścić
  szeroki rdzeń → puchnie do ~10 m², zlewa schody z holem, komunikacja się fragmentuje.

## 3. Konwencje ze wzorców ARCHON (źródło reguł)

- **Schody:** kompaktowe, pole **~3.7–5.7 m²** (osobna pozycja, nie 7.5). Szerokość biegu
  ~1.0–1.4 m. Typ zależny od domu: bieg prosty (wydłużone) albo zabiegowe/U (kwadratowe).
- **Pozycja:** **cofnięte od wejścia** (za wiatrołapem/holem), **przy ścianie wewnętrznej**,
  **centralnie/w głębi** — sekwencja wejścia: drzwi → wiatrołap → hol → (schody) → salon
  od ogrodu. NIE przy ścianie frontowej.
- **Hierarchia komunikacji (zwarta):** parter Wiatrołap (3–5) → Hol (2–5, przy nim schody);
  poddasze Korytarz/Hol/podest (4–6) → sypialnie.
- **Zgranie pionowe** parter↔poddasze (już działa — `reserved_core` ten sam na obu).

## 4. Wybrane podejście: A — regułowe, zlokalizowane

Decyzja Dawida (2026-06-01): **robimy A; jeśli nie zadziała, wracamy do B.**

**A** = zmiany tylko w `core/house_layout.py::_reserve_core` + dostrojenie hubów w
`templates/house_parter.json` / `house_pietro.json`. **Bez zmian w solverze.** Niskie
ryzyko, duży zysk. Model „Hol ze schodami" zostaje scalony (jeden pokój KOMUNIKACJA
zawiera rdzeń).

**B (odłożone, fallback):** rozbicie szablonu na osobny pokój „Schody" (pokój o stałej
geometrii = rdzeń) + „Hol/Korytarz", z nowymi sąsiedztwami. Wierniejsze etykietom ARCHON,
ale wymaga obsługi pokoju o stałej geometrii w solverze → większe ryzyko. Wracamy do B
tylko jeśli A nie da wiarygodnego wyniku.

## 5. Reguły do zaimplementowania (Approach A)

### 5.1 Adaptacyjna geometria rdzenia (`_reserve_core`)

Niech `Lmax=max(W,H)`, `Lmin=min(W,H)`, `aspect=Lmax/Lmin`. Wejście wyznacza stronę jak dziś.

- **Wydłużony (`aspect > 1.4`) → bieg prosty:** rdzeń wąski i długi wzdłuż **długiej osi**;
  szerokość biegu `run_w ≈ 1.1 m`, długość `run_len ≈ clamp(4.0–4.5 m, ≤ 0.5·Lmax)`.
- **Kwadratowy (`aspect ≤ 1.4`) → U/zabiegowe:** rdzeń zwarty `≈ 2.5 × 2.5 m`
  (clamp do `≤ 0.40·W` × `≤ 0.40·H`).
- **Cel pola:** schody **~4–6 m²** (twardy sufit: rdzeń nie większy niż ~6 m² ani niż
  bieżące `0.40·W × 0.40·H`, żeby zawsze się mieścił w hubie i obrysie).

### 5.2 Reguła pozycji (clou poprawki)

Rdzeń **cofnięty od krawędzi wejścia** o `setback ≈ 1.3 m` (głębokość wiatrołapu/holu),
**wyśrodkowany** w osi równoległej do wejścia (z dopuszczalnym lekkim biasem ku x wejścia),
i **nie dotykający** krawędzi przeciwległej (ogrodowej) — czyli w **środkowym pasie głębokości**
rzutu. Dla wejścia od południa: `cy = setback` (zamiast `cy = 0`), `cx ≈ (W − sw)/2`.
Analogicznie (lustrzanie) dla północy/wschodu/zachodu. Rdzeń pozostaje wewnątrz obrysu
z marginesem; salon (`priorytet_fasady=1`) dzięki temu łapie pełną fasadę.

### 5.3 Dostrojenie hubów w szablonach

Po skompaktowaniu rdzenia hub może zmaleć. W `house_parter.json` (hub „Hol + schody") i
`house_pietro.json` (hub „Hol / podest") dostroić `opt_powierzchnia` i `procent_powierzchni`
tak, by hub ≈ **schody (~5) + realny hol (~3) = ~6–9 m²**, ale **nadal ≥ pole rdzenia**
(inaczej INFEASIBLE — hub musi zmieścić rdzeń). Wartości dobrać empirycznie pod walidację 5.5,
bez naruszania F4 (hub ≤15% usable, aspect ≤1.5).

### 5.4 Model komunikacji

Zostaje scalony „Hol ze schodami" (bez osobnego pokoju schodów). Reszta szablonu bez zmian.

### 5.5 Walidacja (B8)

Render + porównanie ze wzorcami na: **8×8** (kwadrat → U), **6×11** (wydłużony → prosty),
**9×7**. Sprawdzić wzrokowo: schody kompaktowe, cofnięte za hol, salon trzyma fasadę,
komunikacja mniej pofragmentowana. Twardo: F2 (łazienka ≤5, WC ≤3) i F3 (miny) trzymają,
zgranie pionowe klatki zachowane, `generate_house` `ok=True` na wszystkich trzech, istniejące
testy domu zielone.

## 6. Reguły nienaruszalne

- F1–F10 i B1–B10 obowiązują. Zmiana dotyka tylko geometrii rdzenia + parametrów szablonu —
  **nie zmienia solvera, walidatora, ani capów WT** (F2 łazienka ≤5). M1–M5 nietknięte.
- B1: 2 faile = rewrite (tu: jeśli A nie da rady → B). B8: weryfikacja (testy + render).

## 7. Pliki

- ZMIANA: `core/house_layout.py` (`_reserve_core` — adaptacyjna geometria + reguła pozycji;
  ewentualnie mały helper `_stair_dims(bbox)` dla testowalności).
- ZMIANA: `templates/house_parter.json`, `templates/house_pietro.json` (dostrojenie hubów).
- NOWE testy: `tests/test_house_staircase.py` (geometria rdzenia wg proporcji; cofnięcie od
  wejścia; pole 4–6 m²; rdzeń ⊆ obrys; zgranie pionowe).
- ZMIANA (po walidacji): `docs/STATE.md`, `NEXT_SESSION.md`.

## 8. Poza zakresem (na później)

- Podejście B (osobny pokój schodów) — fallback, jeśli A nie wystarczy.
- Realizm mebli (osobna runda).
- Naprawa fragmentacji komunikacji wynikającej z F4/F5 (hub-dotyka-każdego) — follow-up,
  jeśli pozostanie po dobrej pozycji schodów.
- GAP nadmiaru (zdeprioretyzowany — artefakt dużego obrysu).
- Eksport domu do AC ze ścianami+drzwiami, bliźniak/szeregowiec.
