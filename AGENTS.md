# FloorPlan6 — orientacja dla Codex

> **Język rozwoju:** Python 3.10+ (logika algorytmów). C++ port później (FloorPlan4_CPP zachowany jako referencja UI/AC bridge).
>
> **Decyzja strategiczna 2026-04-29:** powrót z C++ do Pythona. Powód: algorytmy geometryczne łatwiej iterować w Pythonie (Shapely + matplotlib). Plot Subdivider w C++ był buggy (4 znane bugi w jednej sesji), łazienka 13m² w etapie 4 — patrz `docs/LESSONS_LEARNED.md`.

---

## ⚠️ PRZED ZROBIENIEM CZEGOKOLWIEK — PRZECZYTAJ DOCS W TEJ KOLEJNOŚCI

**W każdej nowej sesji Codex NA START:**

| # | Plik | Co tam jest | Czas |
|---|------|-------------|------|
| 1 | **`docs/FUNDAMENTAL_RULES.md`** ⚠️ | F1-F10 (architektura WT) + B1-B10 (workflow). NIENARUSZALNE. | 5 min |
| 2 | **`docs/LESSONS_LEARNED.md`** | 5 wzorców do reuse + 6 błędów do unikania. Czemu nie powtarzać błędów z C++ sesji 25.04 i 29.04. | 5 min |
| 3 | **`docs/ARCHITECTURE.md`** | Workflow 4-etapowy, struktura folderów, dataflow, role modułów. | 5 min |
| 4 | **`docs/STATE.md`** | Co działa, co nie, co odłożone. Aktualne priorytety. | 3 min |
| 5 | **`docs/TEMPLATES_GUIDE.md`** | 3 zestawy szablonów (constraint M1-M5 / data/plans z grafem / rzuty). Kiedy którego. | 3 min |
| 6 | **`docs/OPEN_QUESTIONS.md`** | Q1-Q10 — pytania architektoniczne. Jeśli Twoja zmiana ich dotyka — STOP, zapytaj Dawida. | 3 min |
| 7 | `MASTER_PROMPT_etap4.md` | Szczegółowy prompt dla pierwszej sesji (jeśli to jest pierwsza sesja). | — |
| 8 | `AGENTS.md` (ten plik) | Orientacja po dokumentach. | — |

**Łącznie ~25 minut na pełną orientację.** To inwestycja, nie strata czasu.

---

## CO TO ZA PROJEKT

ArchiCAD addon dla architektów. **4-etapowy workflow** od działki do gotowego rzutu mieszkania:

```
Działka (z AC) + parametry MPZP
     ↓
Generator brył zabudowy
     ↓
Podział piętra na mieszkania (mix M1-M5)
     ↓
Rzuty mieszkań (rozkład pokoi) ⭐ START TUTAJ (etap 4)
     ↓
Insert do ArchiCAD przez Tapir / Python Palette
```

**Cel końcowy:** architekt w AC zaznacza poligon, klika przycisk, dostaje gotowy rozkład pokoi z drzwiami i ścianami.

---

## STAN PROJEKTU (TL;DR)

- **Etap 4 (rzuty mieszkań)** ⭐ **AKTUALNY FOCUS**
  - Skopiowany kod z FP4 Python (działał: 36/36 testów)
  - Łazienka 13m² w C++ — do naprawy w pierwszej sesji jeśli również jest w Python
  - Patrz `MASTER_PROMPT_etap4.md`

- **Etap 3 (Floor mode)** — działa w C++, port do Pythona TBD (Q9)

- **Etap 1 (MPZP + Plot Subdivision)** — odłożone. Algorytm w Python czeka na decyzje Q1-Q5

- **Etap 2 (Generator brył)** — nie zaczęte

---

## REGUŁY W SKRÓCIE (przeczytaj `docs/FUNDAMENTAL_RULES.md` po pełną wersję)

### Architektoniczne (F1-F10)
- **F1** — 100% coverage obrysu (`sum(areas) == usable_area`)
- **F2** — łazienka MAX 5m² ZAWSZE
- **F3** — WT min nigdy nie obniżać
- **F4** — hub kompaktowy (max 15%, aspect ≤1.5, max 60% BW/BH)
- **F5** — wszystkie pokoje przez hub (wyjątek: M4+ łazienka↔sypialnia)
- **F6** — pokoje z oknami dotykają fasady polygonu
- **F7** — proporcje pokoi MAX 2.5
- **F8** — drzwi: pokoje do wewnątrz, łazienki na zewnątrz, wejście na zewnątrz
- **F9** — facade detection per krawędź polygonu (nie bbox)
- **F10** — walidator strict, sprawdza MIN i MAX (5m² łazienka!)

### Workflow (B1-B10)
- **B1** — 2 fail = REWRITE, NIE 3-cia próba
- **B2** — Plan PRZED zmianą kodu, czekaj na OK
- **B3** — NIE zmieniaj reguł żeby solver działał
- **B5** — pytaj o decyzje architektoniczne (NIE o oczywistości)
- **B6** — słuchaj dosłownie
- **B8** — verify before "done" (pytest + manual run + viz)
- **B10** — kolega-do-kolegi, po polsku

---

## ZASADA Z Codex — PRZED PIERWSZĄ ZMIANĄ KODU

```
[ ] Przeczytałem docs/ w kolejności (25 min)
[ ] Sprawdziłem aktualne testy: pytest tests/
[ ] Wiem co aktualnie działa (docs/STATE.md)
[ ] Wiem czego NIE robić (docs/LESSONS_LEARNED.md)
[ ] Wiem o jakie pytania mam pytać (docs/OPEN_QUESTIONS.md)
[ ] Mam plan w prostym języku → przedstawiłem Dawidowi → mam OK
```

**Jeśli którykolwiek punkt = NIE → zatrzymaj się, dokończ orientację.**

---

## NIE RÓB (z lekcji poprzednich wersji — pełna lista w `docs/LESSONS_LEARNED.md`)

❌ **NIE łataj** — po 2 fail próbach REWRITE
❌ **NIE zmieniaj reguł** żeby solver działał
❌ **NIE zmieniaj Coverage z `==` na `<=`**
❌ **NIE zmniejszaj MIN_SHARED_EDGE poniżej 90 cm**
❌ **NIE rób huba jako spine/korytarz**
❌ **NIE używaj `absorbUncoveredPolygon`** (powoduje "prostokąty z dupy")
❌ **NIE pisz algorytmu geometrycznego od razu w C++** bez prototypu Python
❌ **NIE skopiowuj 1:1 z C++** — Pythonic implementation
❌ **NIE pomijaj wizualizacji** — `viz/plan_renderer.py` po KAŻDEJ zmianie

---

## STRUKTURA FOLDERÓW (skrót — pełna w `docs/ARCHITECTURE.md`)

```
FloorPlan6/
├── core/         ← logika algorytmów (cpsat_solver, validator, scorer, …)
├── bridge/       ← Tapir → ArchiCAD
├── viz/          ← matplotlib rendering
├── ui/           ← PyQt5 (lokalny test)
├── tests/        ← pytest
├── templates/    ← 7 constraint templates M1-M5
├── data/plans/   ← 27 reference rzutów z grafem ⭐
├── docs/         ← dokumentacja strategiczna (CZYTAJ JAKO PIERWSZE)
└── notebooks/    ← Jupyter (per zadanie)
```

---

## WORKFLOW DLA NOWEJ SESJI

1. Wklej `MASTER_PROMPT_etap4.md` jako pierwszą wiadomość (jeśli pierwsza sesja)
2. Codex przeczyta `docs/` w kolejności
3. Sprawdzi aktualny stan (pytest, walidacja kodu)
4. Zaproponuje plan dnia w prostym języku po polsku
5. Czeka na twoje OK
6. Implementuje
7. Każda zmiana → verify (pytest + viz) → raport
8. Po fail → STOP, diagnostyka, NIE 2-ga próba bez analizy
9. Update `docs/STATE.md` na końcu sesji

---

**TL;DR:** docs/ czytaj na start, F1-F10 i B1-B10 święte, etap 4 to focus, łazienka 5m² to twardy cap, Coverage `==` zostaje, plan przed zmianą, 2 fail = rewrite, po polsku jak kolega.
