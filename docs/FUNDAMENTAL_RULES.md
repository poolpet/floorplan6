# FUNDAMENTAL_RULES — ABSOLUTNY PRIORYTET

> **Te zasady są NIENARUSZALNE.** W sesji 24-25 kwietnia w C++ FloorPlan4_CPP były **notorycznie łamane** — to przyczyna katastrofy (25+ commitów regresji, 4 nieudane podejścia, łazienka 13m² zamiast 5m²).
>
> **PRZED KAŻDĄ zmianą w kodzie:** przeczytaj ten plik. Jeśli chcesz zmienić cokolwiek co narusza te zasady — STOP, zapytaj użytkownika EXPLICIT.

---

## REGUŁY ARCHITEKTONICZNE (WT i layout) — ABSOLUTNE

### F1: 100% COVERAGE OBRYSU
**Polygon użytkownika = mieszkanie. W CAŁOŚCI. Bez wyjątków.**

- Wynik solvera MUSI wypełnić cały polygon
- Coverage = `sum(rooms_areas) == usable_area_cm2` (RÓWNOŚĆ, nie nierówność!)
- ŻADNYCH "virtual obstacles" zmniejszających usable area
- ŻADNYCH gap > 0 m²
- ŻADNYCH "prostokątów z dupy" (extra_rect odłączonych od głównego pokoju)

**W sesji C++ NARUSZONE:** dziury 15%, odłączone prostokąty.

**W Pythonie:** `core/cpsat_solver.py:140` — `model.Add(sum(areas) == usable_area_cm2)`. To jest święte — nie zmieniaj na `<=`.

### F2: ŁAZIENKA MAX 5 m² (WT — twardy cap)
**Łazienka NIGDY nie może być większa niż 5 m². Niezależnie od typu mieszkania, wielkości obrysu, czy okoliczności.**

- WT min: 175×250 cm w świetle
- WT max: **5.0 m² absolute**
- WT max wymiar: 3 m
- Łazienka MUSI być prostokątna (instalacje sanitarne)
- Łazienka NIE absorbuje overflow / extra area

**W sesji C++ NARUSZONE:** wielokrotnie 5.4–13.1m². To jest BUG #1 do naprawy w pierwszej sesji FloorPlan6 — patrz `docs/STATE.md` i `MASTER_PROMPT_etap4.md`.

### F3: WT min_powierzchnia, min_szerokosc — NIGDY nie obniżać
**Reguły z WT 2002 są progu PRAWNE. Nie wolno ich obniżać "żeby solver znalazł rozwiązanie".**

- min_powierzchnia (np. salon M1: 25 m², sypialnia 2-os: 9 m²) — SZTYWNE
- min_szerokosc (np. salon: 3.2 m, łazienka: 1.5 m) — SZTYWNE
- Pokoje USŁUGOWE spełniają min łazienki (1.5m × 2.5m)

**Jeśli solver INFEASIBLE z tymi regułami → zmień szablon, NIE obniżaj progów.**

### F4: HUB — kompaktowy, NIE spine
**Hub to przedpokój centralny, NIE wąski korytarz.**

- Hub max 15% powierzchni użytkowej
- Hub max aspect ratio 1.5 (NIE wąski długi)
- Hub max 60% BW i max 60% BH (NIE pełna szerokość/wysokość)
- Hub zawiera entry_point
- Hub dotyka KAŻDEGO pokoju (adjacency edge ≥ 90 cm)

### F5: TOPOLOGIA PRZEZ HUB
**Wszystkie pokoje dostępne przez hub. Brak bezpośrednich połączeń pokój↔pokój.**

- Wyjątek: łazienka↔sypialnia tylko gdy >1 łazienka (M4+)
- Sąsiedztwo z szablonu = bezpośredni shared edge ≥ 90 cm

### F6: FACADE — pokoje wymagające okien dotykają polygon edge
**Pokoje z `wymaga_okna=true` muszą dotykać krawędzi FACADE polygonu (nie bbox side).**

- Salon, sypialnia, kuchnia → wymagają fasady
- Łazienka, hub, garderoba → mogą być wewnętrzne
- Detection: real polygon edge, NIE bbox approximation

### F7: PROPORCJE pokoi MAX 2.5 (aspect ratio)
**Żaden pokój nie może być dłuższy niż 2.5× szerokość.**

- Optymalne: 1.0-2.0
- Tolerowane: do 2.5
- Powyżej: pokój staje się "kanał" — niefunkcjonalny

### F8: DRZWI I ŚCIANY
- Jedna ściana na styku dwóch pokoi
- Linia odniesienia ściany = ŚRODEK
- Drzwi: pokoje otwierają się DO WEWNĄTRZ, łazienki NA ZEWNĄTRZ
- Drzwi wejściowe: NA ZEWNĄTRZ mieszkania
- Skrzydło drzwi w stronę najbliższej prostopadłej ściany
- Styk hub↔salon/aneks → pusty otwór na pełną szerokość
- 2 łazienki TYLKO w M4+

### F9: FACADE DETECTION
**Inny composite = ściana zewnętrzna (FACADE).** Detection per rzeczywistą krawędź polygonu, nie bbox side.

### F10: WALIDATOR POST-CLIP = 100% STRICT
**Walidator MUSI sprawdzać MIN i MAX. Brak miękkich tolerancji.**

- min_powierzchnia → odrzuc jeśli pokój < min
- min_szerokosc → odrzuc jeśli szerokość < min
- **MAX powierzchnia (lazienka 5m²) → odrzuc jeśli > max** ⚠️ TO BYŁO ZAPOMNIANE w C++
- pct_max × usable → odrzuc jeśli > limit
- Pokój 1 cm poniżej WT lub 1 cm powyżej max = odrzucenie wariantu

**W Pythonie:** `core/validator.py` — sprawdź czy są asserty na MAX. Jeśli nie, dodaj jako pierwsze zadanie.

---

## REGUŁY PRACY (CLAUDE behavior) — ABSOLUTNE

### B1: Po 2 nieudanych próbach → REWRITE, nie 3-cia iteracja
**To absolutne. Nie negocjowane.**

- 1 fail → diagnostyka root cause
- 2 fail → STOP, rewrite modułu od zera z innym podejściem
- 3-cia próba → ZAKAZANA

**W sesji C++ NARUSZONE:** 14 łatań w 1 obszarze (PolygonFiller). 4 nieudane podejścia architektoniczne.

### B2: Plan w prostym języku PRZED zmianą kodu
**Zawsze. Nawet 1 linia zmiany.**

- Co chcę zmienić (architektonicznie, nie programistycznie)
- Dlaczego (przyczyna)
- Jak się zmieni wynik (co user zobaczy)
- **Czekaj na OK użytkownika**

### B3: NIE zmieniaj reguł żeby solver działał
**Reguły WT, layout, scoring są SZTYWNE. Solver nie znajduje rozwiązania → zmień podejście, NIE regułę.**

- "Threshold za strict" → źle interpretujesz threshold, NIE obniżaj
- "Solver INFEASIBLE" → szukaj innego szablonu / podejścia, NIE rozluźniaj constraint
- "Cap pct_max za niski" → memory pozwala POZIOM 1 (fill) > POZIOM 2 (caps), ale ŁAZIENKA 5m² to twardy cap WT

### B4: NIE proponuj rule-violating opcji
**Nawet jako fallback / last resort.**

- Jeśli wszystkie opcje naruszają regułę → "nie widzę rozwiązania bez naruszenia X" + czekaj
- NIE listuj opcji typu "obniżyć threshold do X% jako kompromis"

### B5: Pytaj o decyzje architektoniczne, NIE o oczywistości
- NIE pytaj: "czy polygon to mieszkanie?" (TAK, zawsze, definicja)
- PYTAJ: "kto absorbuje nadmiar — salon czy sypialnia?"
- PYTAJ: "łazienka na fasadzie czy wewnętrzna w tym przypadku?"

### B6: Słuchaj użytkownika dosłownie
- "Wypełnij cały obrys" = WYPEŁNIJ CAŁY OBRYS, nie interpretuj że "tak naprawdę nie chciał"
- "Nie zmieniaj X" = NIE ZMIENIAJ X, koniec dyskusji

### B7: Tłumacz architektonicznie, nie programistycznie
- ❌ "AddEquality(area_sum, usable_area)"
- ✅ "Solver wymaga że suma powierzchni pokoi DOKŁADNIE równa się powierzchni obrysu"
- User jest architektem, ja programistą — komunikacja w jego języku

### B8: Verify before "done"
**Nigdy nie raportuj "naprawione" / "działa" bez:**
1. `pytest tests/` zielone
2. Manual run przez `python main.py` lub notebook
3. Wizualizacja matplotlib pokazująca wynik
4. User retest pokazuje wynik

### B9: Memory-driven — pamiętaj, nie wymyślaj
- Reguły są w docs/ FloorPlan6
- Czytaj `docs/` NA START każdej sesji
- Reguła jest w docs → respektuj. Reguła nie ma w docs ALE user ją podał → zapisz NATYCHMIAST do `docs/OPEN_QUESTIONS.md` lub odpowiedniego doc

### B10: Komunikacja kolega-do-kolegi (po polsku)
- Bez "Pan / Pani"
- Wspólnicy
- Profesjonalnie ale familiarnie
- Po polsku domyślnie (preferencja użytkownika)
- Zwięźle, szczerze, obiektywnie — nie mów co user chce usłyszeć

---

## ADAPTACJA DO PYTHONA

W FloorPlan6 (Python) szczególnie pamiętaj:

### P1: `Coverage equality` — `cpsat_solver.py`
W FP4 Python `core/cpsat_solver.py:140` było `model.Add(sum(areas) == usable_area_cm2)`. Sprawdź że nadal tak jest. NIE zmieniaj na `<=`.

### P2: `scale=100` (centymetry)
Wszystkie wartości CP-SAT to integer cm. NIE wracaj do floatów. Eliminuje klasę bug-ów typu "0.999 != 1.0".

### P3: Wizualizacja od pierwszej minuty
`viz/plan_renderer.py` istnieje. Po KAŻDEJ zmianie solvera — render PNG i obejrzyj. Geometryczny debug bez rysunku jest niemożliwy.

### P4: Testy regresji dla F2 i F10
W `tests/test_cpsat_solver.py` dodaj/upewnij się że istnieje:
```python
def test_lazienka_never_exceeds_5m2():
    """F2: łazienka NIGDY > 5m². Test musi przejść dla wszystkich szablonów × wszystkie obrysy."""
    for template_id in ["M2_standard", "M3_standard", "M3_wc", "M4_standard", "M4_2laz", "M5_standard"]:
        for (w, h) in [(6, 6), (8, 6), (10, 8), (12, 10), (15, 12)]:
            ...
            for room in result.rooms:
                if "lazienka" in room.spec.id.lower() or "wc" in room.spec.id.lower():
                    assert room.area <= 5.0, f"F2 violation: {template_id} {w}×{h}: {room.spec.id}={room.area:.2f}m²"
```

---

## CHECKLIST PRZED KAŻDĄ ZMIANĄ KODU

```
[ ] Czytałem ten plik FUNDAMENTAL_RULES.md TODAY
[ ] Sprawdziłem czy zmiana NIE narusza F1-F10 (architektura) ani B1-B10 (workflow)
[ ] Plan w prostym języku przedstawiony użytkownikowi (po polsku)
[ ] Otrzymałem OK explicite (lub zmiana jest trywialna w ramach jasnej zgody)
[ ] To pierwsza lub druga próba (NIE trzecia)
[ ] Mam diagnostykę root cause (jeśli to fix)
[ ] Wiem jak zweryfikuję wynik (pytest, manual run, viz)
```

**Jeśli którykolwiek punkt = NIE → STOP, nie zmieniaj kodu.**

---

## HIERARCHIA W KONFLIKTACH

Gdy reguły się wykluczają (rzadko, ale zdarza się):

1. **WT i layout (F1-F10)** — najwyższy priorytet (prawo + reguły architektoniczne)
2. **B1 (nie łatać)** — jeśli się powtarza, problem jest fundamentalny
3. **Decyzja użytkownika** — gdy F i B nie rozstrzygają, user decyduje
4. **POZIOM 1 (fill polygon) > POZIOM 2 (caps pct_max)** — autoryzowane 2026-04-22, ale **ŁAZIENKA 5m² jest cap WT, nie pct_max** — nadal absolute

---

## PRZYKŁADY NARUSZEŃ Z SESJI C++ (NIE POWTARZAĆ W PYTHONIE)

| # | Reguła naruszona | Co zrobiłem | Konsekwencja |
|---|------------------|-------------|--------------|
| 1 | F2 (5m²) + B3 (nie zmieniaj reguł) | Zmieniłem 70% facade ratio na "1m absolute" bez OK | Łazienka rosła do 13m² |
| 2 | B1 (2 fail rewrite) | 14 łatań pre-assign cells (ceil/floor → round → strict) | Marnotrawstwo czasu, regresje |
| 3 | F1 (100% coverage) | Zmieniłem `==` na `<=` w solverze | Dziury 15% w polygonie |
| 4 | F2 (łazienka prostokąt) + F1 | absorbUncoveredPolygon dawał extra_rect odłączony | "Prostokąty z dupy" |
| 5 | F10 (walidator MAX) | Walidator nie sprawdzał MAX | Łazienka 8-13m² przechodziła |
| 6 | B2 (plan przed zmianą) | Edytowałem kod bez planu | Wielokrotne regresje |
| 7 | B6 (słuchaj dosłownie) | Interpretowałem "nie ruszaj" jako "lekko zmodyfikuj" | User frustration |

---

## SUMMARY ONE-LINER

**Reguły są nienaruszalne. Jeśli czujesz pokusę by je zmienić — STOP, zapytaj. Łatanie nigdy nie działa. 2 fail = rewrite.**

— Te zasady ratują projekt. Ich łamanie zniszczyło sesję 25 kwietnia w C++.
