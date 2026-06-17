# B1 — Fill genuine recall + fix metryki garaż (design)

> Data: 2026-06-17 (sesja S31d→B1). Branch `feat/sfh-open-plan-day-zone`.
> Status: zaakceptowany przez Dawida (brainstorm). Następny krok: writing-plans.

## Kontekst i przeformułowanie premisy

Premisa S31b brzmiała: „sparse room-set → densyfikacja (dodaj pokoje)". **Diagnostyka
F1 (precision/recall per kondygnacja, 32 kondygnacje) ją obaliła:**

- 18/32 kondygnacji ma F1<0.85, ale driver to **OVER-generacja (precision)**, nie braki:
  nadmiar wg typu — lazienka ×12, kotłownia ×7, gabinet ×6, sypialnia ×6, garaż ×6.
- Najgorsze F1 mają **wysoki recall, niski precision** (np. `modlnica parter` 8/5,
  prec 0.62, recall 1.0; `kudowe parter` prec 0.33 — bliźniak-artefakt danych).
- Genuine braki (recall) są nieliczne i małe: garderoba/spiżarnia/sypialnia ×1 na
  poddaszu + `pt` (300 m² outlier — ODŁOŻONY).

### Decyzje architektoniczne Dawida (brainstorm)

1. **Mieszane per typ/rozmiar** — nie ślepy pruning ani ślepe keep.
2. **2. łazienka przy ≥3 sypialniach jest POPRAWNA** (komfort) — tabele wzorców są
   niepełne (pomijają WC/2.łazienkę). NIE ścinać. Akceptujemy niższe F1 na tych
   kondygnacjach. (Korpus: 14/16 ma 1 łazienkę nawet przy 3-4 syp — uznane za
   ograniczenie tabel, nie błąd generatora.)
3. **Generator architektonicznie poprawny > wynik benchmarku.** Pruning słusznych
   pokoi (gabinet na dużych, kotłownia, 2.łazienka) — ODRZUCONY.
4. B1 zawęża się do **2 lewarów F1, oba bez crippl'owania generatora.**

### Powiązana lekcja (proxy-gap, S31d)

Predicted-MAPE z diagnostyka targetów okazał się LUŹNYM proxy realized benchmarku
(kalibracja B2 ruszyła targety, realized MAPE stał ±1-2% = szum solvera). **ALE F1 jest
INNE: liczy się na ZESTAWIE pokoi (selekcja), nie na powierzchniach — więc predicted-F1
z selektorów JEST wiarygodny** (realized F1 ≈ selected F1 dla kondygnacji, które
solve'ują w pełni). To uzasadnia sweep predicted-F1 jako narzędzie wyboru.

## Cel

Podnieść score benchmarku (`0.5·F1 + 0.3·(1−MAPE/50) + 0.2·adj`) przez F1, **tylko**
zmianami net-dodatnimi, bez regresji perf/generation-rate. Baseline: 58.8/100, 14/16.

## Metoda — data-driven, bramka net-F1

Każda kandydująca zmiana progu/metryki przechodzi przez **sweep predicted-F1**
(read-only, reużywa `reference_plans_full.json` + selektory bez solve'a):

1. Policz `net_predicted_F1 = Σ(zysk recall) − Σ(strata precision)` na 16 projektach.
2. Adoptuj **tylko zmiany net-dodatnie** (próg np. ≥ +0.01 śr. F1, by nie szumić).
3. Finalistów waliduj **realnym benchmarkiem** (rozstrzygający) + **sondą feasibility
   per nowy pokój** (czy kondygnacja nadal solve'uje @90 s).

Powód bramki: „fill recall" przez obniżenie progu często **over-adduje** (np. garderoba
eff 95→65 dodałaby ją na ~8 poddaszach, ref ma 3 → precision spada → net F1 UJEMNY).
Tylko sweep rozstrzyga, które zmiany realnie pomagają.

## Lewar 1 — fill genuine recall (selektory `core/house_layout.py`)

Kandydaci (każdy przez sweep, NIE przesądzony):

- **`garaz`**: `_PARTER_GARAZ_MIN_NET` 97→~90. CZYSTY: dodaje `modlnica`(net96) i
  `a2-6`(net91) — oba ref-mają garaż; pasmo netto 90-97 nie ma kondygnacji bez garażu
  w ref (najbliższa `a2-5` net87 < 90). Sparowane z Lewarem 2 (inaczej metryka i tak
  liczyła nasz garaż jako FP).
- **`garderoba`** (poddasze, `_PIETRO_GARDEROBA_MIN_EFF`): ref ma na `osobie`/`a2-base`/
  `a2-6`. OSTRZEŻENIE: gate metrażowy over-adduje → wchodzi TYLKO jeśli sweep pokaże
  net-dodatni (rozważyć lepszy sygnał niż eff, np. liczba sypialni/master; jeśli brak
  czystego — ODPUŚCIĆ, udokumentować).
- **`spizarnia`**: analogicznie — tylko jeśli sweep net-dodatni.

Każdy fill bramkowany feasibility: więcej pokoi = ryzyko INFEASIBLE (parter-gardło
udokumentowane S26/S30). INFEASIBLE → best-effort fallback (nie dodawaj tam).

## Lewar 2 — fix metryki garaż (`notebooks/reference_benchmark.py`)

`_storey_rooms` wyklucza `garaz` z ref → nasz generowany garaż zawsze false-positive
w F1, NAWET gdy ref faktycznie ma garaż (potwierdzone: `pt`/`ar02-1b`/`a2-2` mają garaż,
ukryty filtrem; `modlnica`/`a2-6` mają, my nie generujemy).

Zmiana: **policz `garaz` w ref-multiset dla F1** (`room_set_f1` w `score_project`), ale
**zostaw wykluczony z MAPE** (`area_deviation` — pole garażu w tabelach niepewne/często
brak). Efekt: `pt/ar02-1b/a2-2` garaż → TP (precision ↑); sparowane z Lewarem 1-garaz
żeby `modlnica/a2-6` nie stały się recall-miss.

## Strategia perf

- Sonda feasibility (`notebooks/`) na każdy nowy pokój: kondygnacja solve'uje @90 s?
- INFEASIBLE → best-effort (program bez tego pokoju na tej kondygnacji).
- Bramka regresji: generation-rate ≥14/16, ZERO nowych FAILi vs baseline.

## Walidacja / testy

1. Sweep predicted-F1 (read-only) — wybór net-dodatnich zmian.
2. Realny benchmark `reference_plans_full.json` — rozstrzygający (score, F1, gen-rate, perf).
3. Testy jednostkowe: zachowanie progów (garaz na modlnica/a2-6; brak fałszywych
   dodań) + regression-lock istniejących (`test_house_layout`, `test_house_roomset_scaling`).
4. Update `docs/STATE.md` + pamięć.

## Zakres plików

- `core/house_layout.py` — progi selekcji (Lewar 1).
- `notebooks/reference_benchmark.py` — metryka garaż F1 (Lewar 2).
- `notebooks/` — sweep predicted-F1 + sondy feasibility (nowe, narzędziowe).
- BEZ zmian solvera, reguł F1-F10, ścieżki mieszkań M1-M5.

## Poza zakresem (YAGNI)

- Pruning architektonicznie-słusznych pokoi (2.łazienka/gabinet/kotłownia) — decyzja
  Dawida „trzymaj standard".
- `pt` 300 m² — outlier, zweryfikować ekstrakcję obrysu osobno.
- Area-ważony MAPE (kandydat z S31d) — osobna iteracja, nie B1.
