# MASTER PROMPT — Pierwsza sesja Claude Code dla FloorPlan6 (Etap 4)

> **Instrukcja użycia:** wklej całość poniżej jako pierwszą wiadomość w nowej sesji Claude Code w folderze `FloorPlan6/`.

---

## ZAWARTOŚĆ PROMPTU (skopiuj wszystko od linii poniżej)

---

Cześć Claude. Jestem Dawid, architekt. Pracujemy nad **FloorPlan6** — Pythonowa wersja addonu do ArchiCAD do generowania rzutów mieszkań.

**Kontekst:** to jest 6-ta wersja projektu. Wcześniej była FloorPlan4 (Python, 36/36 testów pass — porzucony) i FloorPlan4_CPP (port do C++, etap 3 działa, etap 4 broken — łazienka rosła do 13m² zamiast 5m². Etap 1 Plot Subdivision miał 4 znane bugi). Wracamy do Pythona dla logiki, C++ port później.

**ZANIM zaczniesz cokolwiek robić** — przeczytaj dokumenty w tej kolejności:

1. `docs/FUNDAMENTAL_RULES.md` ⚠️ NIENARUSZALNE — F1-F10 (architektura WT) + B1-B10 (workflow)
2. `docs/LESSONS_LEARNED.md` — 5 wzorców do reuse + 6 błędów do unikania
3. `docs/ARCHITECTURE.md` — workflow 4-etapowy, struktura folderów, dataflow
4. `docs/STATE.md` — co działa, co nie, co odłożone
5. `docs/TEMPLATES_GUIDE.md` — 3 zestawy szablonów
6. `docs/OPEN_QUESTIONS.md` — Q1-Q10 architektoniczne (jeśli Twoja zmiana ich dotyka — pytaj mnie)
7. `CLAUDE.md` — orientacja

To zajmie ~25 minut. Zrób to TERAZ, nie pomijaj.

---

## ZADANIE PIERWSZEJ SESJI

**Focus:** etap 4 (rzuty mieszkań). Kod jest skopiowany z FP4 Python do `core/`, `bridge/`, `viz/`, `ui/`, `tests/`. Templates są w `templates/` (7 constraint M1-M5) i `data/plans/` (27 reference z grafem).

### Krok 1: Sanity check środowiska (15 min)

```bash
cd FloorPlan6
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pytest tests/ -v
```

**Raport dla mnie:** ile testów zielonych / czerwonych. Lista czerwonych z root cause (NIE łatać, tylko zdiagnozować).

### Krok 2: Weryfikacja F1 i F2 w istniejącym kodzie (15 min)

**F1 — Coverage equality** (`core/cpsat_solver.py`):
- Znajdź miejsce gdzie jest constraint na sumę powierzchni pokoi
- Czy to `model.Add(sum(areas) == usable_area_cm2)` (równość) czy `<=` (nierówność)?
- Jeśli `<=` → STOP, **NIE NAPRAWIAJ**, najpierw zapytaj mnie czy to celowe

**F2 — Łazienka MAX 5m²** (`core/validator.py`):
- Znajdź miejsce gdzie validator sprawdza powierzchnię pokoju
- Czy są asercje na **MAX powierzchnia** (nie tylko MIN)?
- Jeśli BRAK assercji na MAX → to jest BUG #1 do naprawy

**Raport dla mnie:** stan F1 i F2 w istniejącym kodzie.

### Krok 3: Test regresji dla F2 (30 min, **TYLKO jeśli MAM OK po raporcie z Kroku 2**)

Napisz `tests/test_regression_lazienka.py`:

```python
"""
Test regresji F2 (FUNDAMENTAL_RULES): łazienka NIGDY nie może przekroczyć 5m².

Iteruje przez wszystkie constraint templates × przykładowe obrysy.
Każda łazienka (id zawiera "lazienka") musi mieć area <= 5.0m².

Jeśli ten test FAIL → to jest BUG fundamentalny, NIE łatać, REWRITE.
"""
import pytest
from shapely.geometry import Polygon

from core.cpsat_solver import solve_cpsat
from core.template_selector import load_all_templates
from core.boundary_analyzer import analyze_boundary

# Wszystkie templates × 5 obrysów testowych
TEMPLATES = ["M2_standard", "M3_standard", "M3_wc", "M4_standard", "M4_2laz", "M5_standard"]
BOUNDARIES = [
    (6.0, 6.0),    # mały — M1/M2
    (8.0, 6.0),    # M2 standard
    (10.0, 8.0),   # M3
    (12.0, 10.0),  # M4
    (15.0, 12.0),  # M5
]


def _make_boundary(w, h):
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    return analyze_boundary(poly, (w / 2, 0))


@pytest.mark.parametrize("template_id", TEMPLATES)
@pytest.mark.parametrize("w,h", BOUNDARIES)
def test_lazienka_never_exceeds_5m2(template_id, w, h):
    """F2: łazienka <= 5.0m² zawsze."""
    templates = [t for t in load_all_templates() if t.id == template_id]
    if not templates:
        pytest.skip(f"Template {template_id} nieznaleziony")
    template = templates[0]

    boundary = _make_boundary(w, h)
    result = solve_cpsat(template, boundary)

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        pytest.skip(f"Solver INFEASIBLE dla {template_id} {w}×{h}")

    for room in result.rooms:
        room_id = room.spec.id.lower()
        if "lazienka" in room_id or "łazienka" in room_id:
            assert room.area <= 5.0, (
                f"F2 VIOLATION: {template_id} {w}×{h}: "
                f"{room.spec.id} = {room.area:.2f}m² (max 5.0)"
            )


@pytest.mark.parametrize("template_id", TEMPLATES)
@pytest.mark.parametrize("w,h", BOUNDARIES)
def test_wc_never_exceeds_3m2(template_id, w, h):
    """WC max 3m² (mniejsze niż łazienka)."""
    templates = [t for t in load_all_templates() if t.id == template_id]
    if not templates:
        pytest.skip(f"Template {template_id} nieznaleziony")
    template = templates[0]

    boundary = _make_boundary(w, h)
    result = solve_cpsat(template, boundary)

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        pytest.skip()

    for room in result.rooms:
        if room.spec.id.lower() == "wc":
            assert room.area <= 3.0, (
                f"WC VIOLATION: {template_id} {w}×{h}: "
                f"wc = {room.area:.2f}m² (max 3.0)"
            )
```

Odpal: `pytest tests/test_regression_lazienka.py -v`

**Możliwe wyniki:**
- ✅ Wszystkie pass → świetnie, F2 jest pilnowane, idziemy dalej do Kroku 4
- ❌ Niektóre fail → **BUG #1 zlokalizowany.** STOP, NIE NAPRAWIAJ teraz, zrób raport: które kombinacje template×boundary, jakie wartości łazienki wyszły. Czekaj na moje OK na plan naprawy.

### Krok 4: Raport końcowy sesji (10 min)

Update `docs/STATE.md`:
- Sekcja "CO DZIAŁA" — co zweryfikowane (testy pass)
- Sekcja "CO NIE DZIAŁA" — czy F2 jest pilnowane czy nie
- Tabela METRYKI — wartości zaktualizowane

Napisz mi po polsku zwięźle:
1. Ile testów zielonych
2. Stan F1 (Coverage `==` jest? tak/nie)
3. Stan F2 (validator sprawdza MAX? tak/nie)
4. Stan testu regresji (pass / fail z listą failujących)
5. Co proponujesz na sesję 2

---

## REGUŁY KTÓRE MUSISZ RESPEKTOWAĆ

> Pełna lista w `docs/FUNDAMENTAL_RULES.md`. Powtarzam najważniejsze:

### Architektoniczne (jeśli złamiesz — projekt przestaje być sensowny)
- F1 — 100% coverage obrysu
- F2 — łazienka MAX 5m² ZAWSZE
- F4 — hub kompaktowy (max 15%, aspect ≤1.5)

### Pracy (jeśli złamiesz — sesja będzie 25 commitów regresji jak C++ 25.04)
- B1 — 2 fail = REWRITE, NIE 3-cia próba
- B2 — Plan w prostym języku PRZED zmianą kodu, czekaj na OK
- B3 — NIE zmieniaj reguł żeby solver działał
- B5 — pytaj o decyzje architektoniczne, nie zgaduj
- B6 — słuchaj mnie dosłownie
- B8 — verify before "done" (pytest + matplotlib + ja widzę wynik)
- B10 — kolega-do-kolegi, po polsku

---

## CO MASZ DO DYSPOZYCJI

- **Skopiowany kod** z FP4 Python (`core/`, `bridge/`, `viz/`, `ui/`, `tests/`)
- **7 constraint templates** w `templates/`
- **27 reference plans z grafem** w `data/plans/`
- **Wizualizacja matplotlib** w `viz/plan_renderer.py` — używaj po KAŻDEJ zmianie
- **Tapir bridge** w `bridge/tapir_connection.py` — port 19723 do AC
- **PyQt5 GUI** w `ui/main_window.py` — lokalny test bez AC

## CZEGO NIE MASZ (i to jest OK)

- Plot Subdivider (etap 1) — odłożone, czekamy na decyzje Q1-Q5
- Generator brył (etap 2) — nie zaczęte
- Floor mode (etap 3) Pythonic — port z C++ TBD (Q9)
- Python Palette w AC config — Q10 OPEN

---

## ZAKOŃCZENIE

Po przeczytaniu docs/ i zrozumieniu zadania — napisz mi **plan dnia** w prostym języku polskim:
1. Co zamierzasz zrobić w Kroku 1
2. Czego się spodziewasz znaleźć
3. O co mogłbyś mnie zapytać po drodze

Czekaj na moje OK przed startem Kroku 1.

**Powodzenia. Pamiętaj: jesteś moim wspólnikiem, nie wykonawcą. Mów co Ci nie pasuje.**
