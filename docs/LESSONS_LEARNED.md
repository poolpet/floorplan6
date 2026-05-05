# LESSONS_LEARNED — Wzorce do reuse + Błędy do unikania

> **Cel:** zebrać sprawdzone wzorce z FloorPlan2 (PyQt5+heurystyki), FloorPlan4 Python (CP-SAT, 36/36 testów pass) i FloorPlan4_CPP (etap 1 MPZP + Plot Subdivision). NIE kopiujemy bezmyślnie. Każdy wzorzec wymaga zastanowienia czy pasuje do FloorPlan6.

---

## ŹRÓDŁA

| Projekt | Lokalizacja | Status | Język | Co dało |
|---------|-------------|--------|-------|---------|
| FloorPlan2 | `claude code/FloorPlan2/floor_plan_generator/` | Porzucony | Python 3.10 PyQt5 + Shapely + NetworkX | Heurystyki, wczesna wizualizacja |
| FloorPlan4 (Python) | `claude code/FloorPlan4/` | Porzucony 2026-04-26 | Python 3.10 OR-Tools CP-SAT + Shapely | **36/36 testów pass, 27 sparametryzowanych rzutów z grafem** |
| FloorPlan4_CPP | `claude code/FloorPlan4_CPP/` | **Zachowany jako referencja UI/AC bridge** | C++20 OR-Tools + ACAPI | Floor mode (etap 3) działa, MPZP analyzer (etap 1) działa numerycznie, **łazienka 13m² i Plot Subdivider buggy — porzucone** |
| FloorPlan5 | `claude code/FloorPlan5/` | Tylko dokumentacja | — | Strategia + reguły (skonsolidowane tutaj) |
| **FloorPlan6** | `claude code/FloorPlan6/` | **Aktualny** | Python 3.10 OR-Tools + Shapely + matplotlib | TBD |

---

## 5 WZORCÓW DO ROZWAŻNEGO REUSE

### W1: Coverage equality `==` (gwarancja zero gaps)
**Skąd:** FloorPlan4 Python `core/cpsat_solver.py:140` — `model.Add(sum(areas) == usable_area_cm2)`

**Co to daje:** matematyczna gwarancja że pokoje wypełniają cały obrys. Brak dziur, brak overflow.

**Czy reuse?** TAK dla rzutów mieszkań — **już jest w skopiowanym kodzie**. Sprawdź że nie zmienione na `<=` po kopiowaniu. **ALE** uwaga: dla małych obrysów (M1 5.75×6) może dawać INFEASIBLE — trzeba mieć fallback (np. inny szablon, mniejszy hub).

**Decyzja przed użyciem:** czy nasz konkretny przypadek to "fill a polygon with rooms" (TAK→equality) czy "place objects with possible gaps" (NIE→inequality).

---

### W2: Scale=100 (centymetry zamiast metrów)
**Skąd:** FloorPlan4 Python `core/cpsat_solver.py` constants.

**Co to daje:** Wszystkie wartości CP-SAT to integer cm — zero zaokrągleń floating-point. Eliminuje klasę bug-ów typu "0.999 != 1.0".

**Czy reuse?** TAK absolutnie. Już w kodzie. NIE wracaj do floatów.

---

### W3: Topology blocking dla deduplikacji wariantów
**Skąd:** FloorPlan4 Python `core/variant_generator.py` linie ~95-110.

**Co to daje:** Po znalezieniu wariantu solver dostaje constraint "salon NIE w tym kwadrancie" → następne wywołanie generuje inny układ. Dostajemy 5 różnych wariantów zamiast 5 prawie identycznych.

**Czy reuse?** TAK dla rzutów (wariantowość). Dla działki/bryły niepotrzebne.

---

### W4: Notch detection osiowo-wyrównane
**Skąd:** FloorPlan4 Python `core/boundary_analyzer.py` — `_detect_notch()`.

**Co to daje:** L-shape/U-shape detection: bbox.difference(polygon) == prostokąt? Wtedy ten prostokąt jest "notch" i traktowany jako obstacle w solverze.

**Czy reuse?** TAK dla rzutów piętra i mieszkań. Dla działki — działki rzadko są L-shape, ale algorytm działa.

---

### W5: Trapez handler — inscribed_rect + stretch + clip
**Skąd:** FloorPlan4 Python `core/trapezoid_handler.py`.

**Co to daje:** Dla trapezowych obrysów:
1. Wpisz największy prostokąt (`inscribed_rectangle`)
2. Solver pracuje na prostokącie (proste, działa)
3. Pokoje brzegowe rozciągnij do skosu (interpolacja liniowa)
4. Final clip Shapely intersection

**Czy reuse?** TAK dla rzutów. **Już w kodzie jako `core/trapezoid_handler.py`**.

---

### W6: Zestaw 27 sparametryzowanych rzutów (`data/plans/`)
**Skąd:** FloorPlan4 Python `data/plans/PL_*.json`.

**Co to daje:** 27 rzeczywistych polskich mieszkań z geometrią pokoi (polygons), facades, stretch flags, **wypełnionym grafem sąsiedztwa** (room_a_idx, room_b_idx, edge_type), entry_position. Reference dataset do walidacji solvera i template_selector.

**Czy reuse?** TAK absolutnie. Już skopiowane do `FloorPlan6/data/plans/`. Patrz `docs/TEMPLATES_GUIDE.md` po szczegóły.

---

## 6 BŁĘDÓW DO UNIKANIA

### E1: NIE używać `absorbUncoveredPolygon`
**Co to było:** funkcja "wypełnij dziury" która przypisywała niepokryte komórki do najbliższego pokoju jako extra_rect.

**Dlaczego źle:**
- W FloorPlan4_CPP sesja 25.04 → "prostokąty z dupy" (extra_rect odłączony od głównego pokoju)
- Architektonicznie niedopuszczalne (pokój nie może mieć odłączonych części)
- W FloorPlan4 Python BRAK tej funkcji — nie była potrzebna bo Coverage equality gwarantuje 100%

**Wniosek:** jeśli Coverage equality działa → nie potrzebujesz absorb. Jeśli używasz inequality → MASZ problem architektoniczny, nie rozwiązuj go absorbem.

---

### E2: NIE zmniejszać MIN_SHARED_EDGE poniżej 90 cm
**Co to było:** próby zmiany 90cm → 50cm/60cm żeby solver znalazł rozwiązanie.

**Dlaczego źle:** 90cm to **wymiar standardowych drzwi**. Niżej = drzwi się nie otwierają. To nie jest threshold do tuningu — to fizyczny rozmiar drzwi.

**Wniosek:** 90cm zostaje. Jeśli solver INFEASIBLE → zmień szablon, nie threshold.

---

### E3: NIE zmieniać Coverage z `==` na `<=`
**Co to było:** w sesji C++ 25.04 zmieniłem na `<=` żeby solver miał luz dla M1 5.75×6.

**Dlaczego źle:** dało "dziury" 15% w polygonie. Łamie F1 (100% coverage).

**Wniosek:** jeśli equality jest INFEASIBLE → problem w szablonie/min_szerokosc, nie w constraint.

---

### E4: NIE iterować patcha więcej niż 2× w tym samym obszarze
**Co to było:** w C++ sesja 25.04 → 14 łatań pre-assign cells, 3 łatania facade threshold, 2 łatania łazienka cap.

**Dlaczego źle:** każda iteracja wprowadza regresję. Łatanie nie naprawia root cause.

**Wniosek:** **2 fail = STOP, rewrite modułu**. Reguła B1.

---

### E5: NIE robić huba jako spine/korytarz
**Co to było:** FloorPlan2 czasem produkował hub jako wąski długi pasek przez całe mieszkanie.

**Dlaczego źle:** hub to przedpokój, nie korytarz. Architektonicznie inny element.

**Wniosek:** hub max 60% BW, max 60% BH, aspect ≤ 1.5. Hard constraint w solverze. Patrz F4.

---

### E6: NIE pisać algorytmu geometrycznego od razu w C++ bez prototypu Pythonowego
**Co to było:** w C++ FloorPlan4_CPP sesja 29.04 — Plot Subdivider od zera w C++. 4 znane bugi po jednej sesji (sub-działki wystają poza granicę, drogi wystają, strefa budowlana ignorowana, 36 stref dla 10).

**Dlaczego źle:** debugging geometrii w C++ bez wizualizacji jest powolny. Każda iteracja = recompile + redeploy bundle + restart AC.

**Wniosek:** **geometryczne algorytmy iteruj w Python (Shapely + matplotlib).** C++ tylko dla finalnej, sprawdzonej wersji. Powód powrotu do Pythona w FloorPlan6.

---

## CHRONOLOGIA WERSJI — DLACZEGO ROBIMY FloorPlan6

```
FloorPlan2 → FloorPlan3 → FloorPlan4 (Python) → FloorPlan4_CPP → FloorPlan6 (Python)
   │             │              │                    │                  │
   │             │              │                    │                  │
heurystyki   porzucony      36/36 testow         etap 3 dziala     reuse z 4 + lekcje z CPP
PyQt5                       OR-Tools             etap 4 broken     algorytmy w Python
                            27 plans z grafem    Plot Sub buggy    C++ port pozniej
```

**FloorPlan5 = tylko dokumentacja** (zatwierdzono "wszystko w C++" 2026-04-26 — decyzja odwrócona 2026-04-29 po sesji z Plot Subdivider).

**FloorPlan6 = powrót do Pythona** żeby:
1. Naprawić łazienkę 13m² z testem regresji (etap 4)
2. Zaprojektować Plot Subdivision z Shapely + matplotlib (etap 1, w przyszłej sesji)
3. Mieć stabilną logikę zanim zacznie się port do C++

---

## LEKCJE Z SESJI 25.04 (C++ FloorPlan4_CPP)

### Co poszło źle
- **25+ commitów regresji** w jednym obszarze (PolygonFiller)
- **4 nieudane podejścia architektoniczne** do układu pokoi
- **Łazienka 13m² w trapezie** (262% przekroczenia limitu 5m²)
- Bez planu, bez OK, łatanie zamiast rewrite

### Co zadziałało (rzadko)
- Debug log do pliku tekstowego — pomógł znaleźć BADPOLY error
- Decoded hex error code (0x81060069 → APIErrorStart+105)

### Konkluzja
**FUNDAMENTAL_RULES były napisane PO tej sesji.** Były wynikiem analizy co poszło źle. **Nie powtarzaj.**

---

## LEKCJE Z SESJI 29.04 (C++ FloorPlan4_CPP — Plot Subdivider)

### Co zostało zrobione (działa)
- Reorganizacja palety
- BADPOLY fix (APIERR -2130313111) — `coords[nv+1] = coords[1]` + alokacja `nv+2`
- BLIZNIACZA fix (seg_w = min_front_m zamiast bw/2)
- Legenda preview + lokalizacja zabudowy

### Co poszło źle (Plot Subdivider — 4 bugi)
1. Sub-działki wystają poza granicę (siatka w lokalnym AABB, brak clipping)
2. Drogi wewnętrzne wystają poza działkę (rozciągnięte na pełną szerokość AABB)
3. Strefa budowlana ignorowana (sub-działki w obrysie działki nie w strefie budowlanej)
4. 36 stref wstawionych dla działki gdzie zmieści się ~10 (algorytm zachłanny)

### Wniosek
**Algorytm geometryczny napisany od razu w C++ bez wizualnego prototypu = bugi.** Reimplementacja w Pythonie z Shapely (clipping `intersection`) i matplotlib (debug rysunkowy) — w FloorPlan6, w osobnej sesji po decyzji Q1-Q5 (patrz `docs/OPEN_QUESTIONS.md`).

---

## SUMMARY ONE-LINER

**5 wzorców do reuse (Coverage==, scale=100, topology blocking, notch detection, trapez handler) + 6 błędów do unikania (absorb, MIN_SHARED 90cm, Coverage<=, łatanie, hub spine, C++ bez prototypu Python). Wszystkie udokumentowane w sesjach 25.04 i 29.04.**
